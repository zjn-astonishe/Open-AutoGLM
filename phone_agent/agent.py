"""Main PhoneAgent class for orchestrating phone automation."""

import os
import time
import json
import traceback
from dataclasses import dataclass
from typing import Any, Callable, Dict, List

from phone_agent.actions import ActionHandler
from phone_agent.actions.handler import do, finish, parse_action
from phone_agent.config import get_messages, get_system_prompt
from phone_agent.context_manager import StructuredContext
from phone_agent.device_factory import get_device_factory
from phone_agent.model import ModelClient, ModelConfig
from phone_agent.model.client import MessageBuilder
from phone_agent.planner import Planner
from phone_agent.skill_executor import SkillExecutor
from phone_agent.speculative_executor import SpeculativeExecutor

from act_mem.act_mem import ActionMemory
from act_mem.workrecorder import WorkflowRecorder
from act_mem.worknode import WorkAction

from utils import extract_json
from phone_agent.error_analyzer import ErrorAnalyzer

@dataclass
class AgentConfig:
    """Configuration for the PhoneAgent."""

    max_steps: int = 100
    device_id: str | None = None
    lang: str = "cn"
    system_prompt: str | None = None
    verbose: bool = True
    memory_dir: str = "./output/memory"
    enable_reflection: bool = True
    reflection_on_failure_only: bool = False

    def __post_init__(self):
        if self.system_prompt is None:
            self.system_prompt = get_system_prompt(self.lang)


@dataclass
class StepResult:
    """Result of a single agent step."""

    success: bool
    finished: bool
    action: Dict[str, Any] | None
    thinking: str
    predict: Dict[str, str] | None = None
    tag: str | None = None
    message: str | None = None


class PhoneAgent:
    """
    AI-powered agent for automating Android phone interactions.

    The agent uses a vision-language model to understand screen content
    and decide on actions to complete user tasks.

    Args:
        model_config: Configuration for the AI model.
        agent_config: Configuration for the agent behavior.
        confirmation_callback: Optional callback for sensitive action confirmation.
        takeover_callback: Optional callback for takeover requests.

    Example:
        >>> from phone_agent import PhoneAgent
        >>> from phone_agent.model import ModelConfig
        >>>
        >>> model_config = ModelConfig(base_url="http://localhost:8000/v1")
        >>> agent = PhoneAgent(model_config)
        >>> agent.run("Open WeChat and send a message to John")
    """

    def __init__(
        self,
        model_config: ModelConfig | None = None,
        agent_config: AgentConfig | None = None,
        confirmation_callback: Callable[[str], bool] | None = None,
        takeover_callback: Callable[[str], None] | None = None,
    ):
        self.model_config = model_config or ModelConfig()
        self.agent_config = agent_config or AgentConfig()

        self.model_client = ModelClient(self.model_config)
        self.action_handler = ActionHandler(
            device_id=self.agent_config.device_id,
            confirmation_callback=confirmation_callback,
            takeover_callback=takeover_callback,
        )
        self.memory = ActionMemory(self.agent_config.memory_dir)
        self._context = StructuredContext()

        self.planner = Planner(model_config=model_config)
        self.skill_executor = SkillExecutor(device_id=self.agent_config.device_id)
        self.speculative_executor = SpeculativeExecutor(memory=self.memory, device_id=self.agent_config.device_id, context = self._context)

        self._predict = False
        self._step_count = 0
        self._actions_executed: list[dict[str, Any]] = []
        self._last_screenshot = None  # Cache for screenshot reuse
        
        # Skill执行状态跟踪
        self._post_skill_execution = False  # 标记是否刚执行完skill
        self._executed_skills = []  # 记录已执行的skill列表
        
        # 记忆加载缓存
        self._loaded_tags = set()  # 记录已加载的tag，避免重复加载
        
        
        # 错误分析器
        self.error_analyzer = ErrorAnalyzer()

    def run(self, task: str) -> dict[str, Any]:
        """
        Run the agent to complete a task.

        Args:
            task: Natural language description of the task.

        Returns:
            Dictionary containing execution results with actions list.
        """
        self._context.reset()
        self._context.set_system_prompt(self.agent_config.system_prompt)
        self._context.set_task(task)
        self._step_count = 0
        self._actions_executed = []
        workflow = self.memory.create_workflow(task)
        recorder = WorkflowRecorder(task=task, workflow=workflow)

        # 初始化skill执行状态跟踪
        self._post_skill_execution = False
        self._executed_skills = []
        
        # First step with user prompt
        result = self._execute_step(task, recorder, is_first=True)
        # time.sleep(1)
        

        if result.finished:
            self.memory.to_json()
            return {
                'finished': True,
                'actions': self._actions_executed,
                'result_message': result.message or "Task completed",
                'step_count': self._step_count
            }

        # Continue until finished or max steps reached
        while self._step_count < self.agent_config.max_steps:
            result = self._execute_step(task, recorder, is_first=False)

            if result.finished:
                self.memory.to_json()
                return {
                    'finished': True,
                    'actions': self._actions_executed,
                    'result_message': result.message or "Task completed",
                    'step_count': self._step_count
                }
            
            if result.success and result.predict is not None and self._predict:
                self.speculative_executor.executor(result.predict, result.tag)
                # Invalidate cached screenshot since speculative execution changed UI state
                self._last_screenshot = None
                if self.agent_config.verbose:
                    print("🔄 Cleared screenshot cache after speculative execution")

            # time.sleep(1)
        
        self.memory.to_json()

        return {
            'finished': False,
            'actions': self._actions_executed,
            'result_message': "Max steps reached",
            'step_count': self._step_count
        }

    def step(self, task: str | None = None) -> StepResult:
        """
        Execute a single step of the agent.

        Useful for manual control or debugging.

        Args:
            task: Task description (only needed for first step).

        Returns:
            StepResult with step details.
        """
        is_first = self._context.step_count == 0

        if is_first and not task:
            raise ValueError("Task is required for the first step")
            
        if is_first:
            self._context.set_system_prompt(self.agent_config.system_prompt)
            self._context.set_task(task)

        return self._execute_step(task, is_first)

    def reset(self) -> None:
        """Reset the agent state for a new task."""
        self._context.reset()
        self._step_count = 0
        self._actions_executed = []
        self._last_screenshot = None
        # 重置skill执行状态跟踪
        self._post_skill_execution = False
        self._executed_skills = []
        # 重置记忆加载缓存
        self._loaded_tags = set()

    def _execute_step(
        self, user_prompt: str, recorder: WorkflowRecorder, is_first: bool = False
    ) -> StepResult:
        """Execute a single step of the agent loop."""
        self._step_count += 1

        # Optimize screenshot capture - reuse cached screenshot if available
        device_factory = get_device_factory()
        
        # Use cached screenshot as before_screenshot if available (from previous step)
        if self._last_screenshot is not None and not is_first:
            before_screenshot = self._last_screenshot
            screenshot = before_screenshot  # Current screenshot is the cached one
            if self.agent_config.verbose:
                print("📸 Reusing cached screenshot to avoid redundant capture")
        else:
            screenshot = device_factory.get_screenshot(device_id=self.agent_config.device_id)
            before_screenshot = screenshot
            if self.agent_config.verbose and not is_first:
                print("📸 Capturing fresh screenshot (no cache available)")
        
        current_app = device_factory.get_current_app(self.agent_config.device_id)
        
        # 在每个步骤中进行planning，决定是否使用skill
        # 避免在skill执行后的验证步骤中重复planning
        if not self._post_skill_execution:
            try:
                start_time = time.time()
                plan = self.planner.plan_task(user_prompt)
                end_time = time.time()
                
                if self.agent_config.verbose:
                    print(f"🧠 Planning taken: {end_time - start_time:.2f} seconds")
                    # print(f"📋 Plan decision: {plan.decision}")
                
                # 根据planning结果加载相关记忆数据
                if plan.decision == "use_skill" and plan.skill_name:
                    # 将skill_name转换为tag格式
                    target_tag = plan.skill_name.replace("_", ".")
                    
                    # 检查是否已经加载过这个tag
                    if target_tag not in self._loaded_tags:
                        if self.agent_config.verbose:
                            print(f"🧠 Loading memory for skill: {plan.skill_name} (tag: {target_tag})")
                        
                        try:
                            # 使用双重筛选加载记忆：先tag筛选，再embedding筛选
                            memory_start_time = time.time()
                            self.memory.from_json(
                                task=user_prompt,
                                target_tag=target_tag,
                                similarity_threshold=0.5
                            )
                            memory_end_time = time.time()
                            
                            # 记录已加载的tag
                            self._loaded_tags.add(target_tag)
                            
                            if self.agent_config.verbose:
                                print(f"🧠 Memory loading taken: {memory_end_time - memory_start_time:.2f} seconds")
                                print(f"📚 Loaded {len(self.memory.workflows)} workflows, {len(self.memory.workgraphs)} workgraphs")
                                
                        except Exception as e:
                            if self.agent_config.verbose:
                                print(f"⚠️ Memory loading failed: {e}")
                            # 继续执行，不因为记忆加载失败而中断
                    else:
                        if self.agent_config.verbose:
                            print(f"🧠 Memory for tag '{target_tag}' already loaded, skipping")
                
                # 如果决定使用skill且该skill未被执行过
                if (plan.decision == "use_skill" and 
                    plan.skill_name not in self._executed_skills):
                    
                    if self.agent_config.verbose:
                        print(f"🔧 Executing skill: {plan.skill_name}")
                        print(f"📝 Skill params: {plan.skill_params}")
                    
                    start_time = time.time()
                    skill_res = self.skill_executor.execute_skill(plan.skill_name, plan.skill_params)
                    end_time = time.time()
                    
                    if self.agent_config.verbose:
                        print(f"⚡ Skill execution taken: {end_time - start_time:.2f} seconds")
                        print(f"✅ Skill result: {skill_res}")
                    
                    recorder.set_tag(plan.skill_name.replace("_", "."))
                    
                    # 记录技能执行到工作流中
                    from_node_id = f"skill_{plan.skill_name}_{int(start_time)}"
                    action_description = f"Executed skill '{plan.skill_name}' with params {plan.skill_params}"
                    action = WorkAction(
                        action_type="skill_execution", 
                        description=action_description,
                        zone_path=None
                    )
                    recorder.on_action_executed(
                        from_node_id, action, 
                        success=True if skill_res != "Error" else False
                    )
                    
                    # 记录已执行的skill
                    self._executed_skills.append(plan.skill_name)
                    
                    # 设置标志，下一步将是验证步骤
                    self._post_skill_execution = True
                    
                    # 如果skill执行成功，立即进行验证
                    if skill_res != "Error":
                        # 立即进行reflection验证
                        if self.agent_config.verbose:
                            print("🔍 Immediately verifying skill execution results")
                        
                        # 获取skill执行后的截图用于验证
                        try:
                            after_skill_screenshot = device_factory.get_screenshot(device_id=self.agent_config.device_id)
                        except Exception as e:
                            if self.agent_config.verbose:
                                print(f"Failed to capture post-skill screenshot: {e}")
                            after_skill_screenshot = screenshot
                        
                        # 立即进行reflection分析
                        reflection_result = None
                        if self.agent_config.enable_reflection:
                            try:
                                reflection_result = self.reflect(
                                    action_type="SkillExecution", 
                                    action_description=f"Executed skill '{plan.skill_name}' with params {plan.skill_params}", 
                                    before_screenshot=screenshot,
                                    is_skill_execution=True  # 标记这是skill执行的reflection
                                )
                                
                                if self.agent_config.verbose:
                                    if reflection_result and reflection_result.get('action_successful') is False:
                                        print(f"⚠️  Reflection indicates skill execution may have failed: {reflection_result.get('reflection_reasoning', 'Unknown reason')}")
                                    elif reflection_result and reflection_result.get('action_successful') is True:
                                        print(f"✅ Reflection confirms skill execution was successful")
                                    
                            except Exception as e:
                                if self.agent_config.verbose:
                                    print(f"Skill reflection analysis failed: {e}")
                        
                        # 缓存skill执行后的截图用于下一步
                        self._last_screenshot = after_skill_screenshot
                        if self.agent_config.verbose:
                            print("📸 Cached post-skill screenshot for next step")
                        
                        # 将简化的reflection结果添加到上下文
                        if reflection_result:
                            action_successful = reflection_result.get('action_successful')
                            confidence_score = reflection_result.get('confidence_score', 0.0)
                            
                            if action_successful is True and confidence_score >= 0.8:
                                skill_message = f"Skill {plan.skill_name} executed successfully"
                            elif action_successful is False:
                                reasoning = reflection_result.get('reflection_reasoning', 'Unknown reason')
                                skill_message = f"Skill {plan.skill_name} executed but may have failed: {reasoning}"
                            else:
                                skill_message = f"Skill {plan.skill_name} executed with uncertain result (confidence: {confidence_score:.2f})"
                        else:
                            skill_message = f"Skill {plan.skill_name} executed successfully"
                        
                        # 添加skill执行和验证结果到上下文
                        print(f"✅ {skill_message}")
                        self._context.add_history_entry(skill_message, tag=plan.skill_name.replace("_", "."))
                        
                        # 完全跳过后续的验证步骤，直接重置标志
                        self._post_skill_execution = False
                        
                        return StepResult(
                            success=reflection_result.get('action_successful', True) if reflection_result else True,
                            finished=False,  # 继续执行后续步骤
                            action={"action": "SkillExecution", "skill_name": plan.skill_name},
                            thinking=f"Executed and verified skill {plan.skill_name}",
                            tag=plan.skill_name.replace("_", "."),
                            message=skill_message
                        )
                    else:
                        if self.agent_config.verbose:
                            print(f"❌ Skill execution failed, falling back to atomic actions")
                        # Skill执行失败，重置标志，继续使用原子动作
                        self._post_skill_execution = False
                
            except Exception as e:
                if self.agent_config.verbose:
                    print(f"⚠️ Planning failed: {e}")
                    traceback.print_exc()
                # Planning失败，继续使用原子动作
        
        work_graph = self.memory.get_work_graph(current_app)
        if work_graph is None:
            work_graph = self.memory.add_work_graph(current_app)

        elements_info = []
        elements = []
        # for i, (e, crop_b64) in enumerate(zip(screenshot.elements, screenshot.crop_base64_data), 1):
        for i, e in enumerate(screenshot.elements, 1):
            
            common_fields = {
                "content": e.elem_id,
                "option": e.checked,
                "focused": e.focused,
            }
            
            elements_info.append({
                "id": f"A{i}",
                **common_fields,
                "bbox": e.bbox,
            })
            elements.append({
                **common_fields,
                "path": e.get_xpath()
            })

        node = work_graph.create_node(elements)
        node.add_task(user_prompt)
        if not is_first:
            recorder.on_new_node(current_node_id=node.id)

        print(f"📚 Context:\n {self._context.to_messages()}\n")

        screen_info_str = MessageBuilder.build_screen_info(current_app, extra_info=elements_info)
        screen_info = json.loads(screen_info_str)

        # Add screenshot and screen info to structured context
        self._context.add_screenshot(screenshot.base64_data)
        self._context.add_screen_info(screen_info)

        # TODO: Generate speculative context for future UI states
        try:
            if self.agent_config.verbose:
                print("🔮 Generating speculative context for future UI states...")
            
            speculative_start_time = time.time()
            speculative_context = self.speculative_executor.get_speculative_context(
                current_elements=elements,
                task=user_prompt,
                current_app=current_app
            )
            speculative_end_time = time.time()
            
            if speculative_context and speculative_context.strip():
                self._predict = True
                self._context.set_speculative_context(
                    context=speculative_context
                )
                
                if self.agent_config.verbose:
                    print(f"🔮 Speculative context generated in {speculative_end_time - speculative_start_time:.2f} seconds")
                    print(f"📝 Speculative context preview: {speculative_context}")
            else:
                # Clear any existing speculative context if no predictions available
                self._context.clear_speculative_context()
                self._predict = False
                if self.agent_config.verbose:
                    print("🔮 No speculative context generated (no suitable predictions found)")
                    
        except Exception as e:
            if self.agent_config.verbose:
                print(f"⚠️ Speculative context generation failed: {e}")
            # Clear speculative context on error
            self._context.clear_speculative_context()

        # Get model response
        try:
            msgs = get_messages(self.agent_config.lang)
            print("\n" + "=" * 50)
            print(f"💭 {msgs['thinking']}:")
            print("-" * 50)
            # print(f"+" * 50)
            # print(f"system_prompt: {self.agent_config.system_prompt}")
            # print(f"📚 Context:\n {self._context.to_messages()}\n")
            # print(f"+" * 50)
            start_time = time.time()
            response = self.model_client.request(self._context.to_messages())
            end_time = time.time()
            print(f"Inference Time taken: {end_time - start_time:.2f} seconds")
            
        except Exception as e:
            if self.agent_config.verbose:
                traceback.print_exc()
            return StepResult(
                success=False,
                finished=True,
                action=None,
                thinking="",
                message=f"Model error: {e}",
            )

        # Parse action from response
        # print(f"response.action: {list(response.action.values())[0]}, {type(response.action)}")
        if response.tag not in self._loaded_tags:
            if self.agent_config.verbose:
                print(f"🧠 Loading memory for tag: {response.tag}")
            
            try:
                # 使用双重筛选加载记忆：先tag筛选，再embedding筛选
                memory_start_time = time.time()
                self.memory.from_json(
                    task=user_prompt,
                    target_tag=response.tag,
                    similarity_threshold=0.5
                )
                memory_end_time = time.time()
                
                # 记录已加载的tag
                self._loaded_tags.add(response.tag)
                
                if self.agent_config.verbose:
                    print(f"🧠 Memory loading taken: {memory_end_time - memory_start_time:.2f} seconds")
                    print(f"📚 Loaded {len(self.memory.workflows)} workflows, {len(self.memory.workgraphs)} workgraphs")
                    
            except Exception as e:
                if self.agent_config.verbose:
                    print(f"⚠️ Memory loading failed: {e}")
                # 继续执行，不因为记忆加载失败而中断
        else:
            if self.agent_config.verbose:
                print(f"🧠 Memory for tag '{response.tag}' already loaded, skipping")
        
        
        try:
            # Extract action string from response.action dict
            # action_str = list(response.action.values())[0]
            action, element_content = parse_action(action_code=list(response.action.values())[0], elements_info=elements_info)
            if element_content is None:
                if action["action"] == "Type":
                    node_action = node.add_action(action_type=action["action"], description=list(response.action.keys())[0], text=action["text"])
                else:
                    node_action = node.add_action(action_type=action["action"], description=list(response.action.keys())[0])
            else:
                for e in elements:
                    if e["content"] == element_content:
                        if action["action"] == "Swipe":
                            node_action = node.add_action(action_type=action["action"], description=list(response.action.keys())[0], zone_path=e["path"], direction=action["direction"], distance=action["dist"])
                        else:
                            node_action = node.add_action(action_type=action["action"], description=list(response.action.keys())[0], zone_path=e["path"])
        except ValueError:
            if self.agent_config.verbose:
                traceback.print_exc()
            action = finish(message=response.action)

        # 在执行动作前进行错误预防检查
        if action.get("action") != "Finish":
            ui_context = {
                "current_app": current_app,
                "element_count": len(elements_info),
                "screenshot_size": (screenshot.width, screenshot.height)
            }
            
            prevention_guidance = self.error_analyzer.get_prevention_guidance(action, ui_context)
            if prevention_guidance and self.agent_config.verbose:
                print("🚨 Error Prevention Guidance:")
                print(prevention_guidance)
                print("-" * 50)

        if self.agent_config.verbose:
            # Print thinking process
            print("-" * 50)
            print(f"🎯 {msgs['action']}:")
            print(json.dumps(action, ensure_ascii=False, indent=2))
            print("=" * 50 + "\n")
                

        # Clear current step's screenshot and screen info to save space
        self._context.clear_current_step()
        self._context.clear_speculative_context()
        # print(f"📚 Context:\n {self._context.to_messages()}\n")

        # Execute action
        try:
            result = self.action_handler.execute(
                action, screenshot.width, screenshot.height
            )
        except Exception as e:
            if self.agent_config.verbose:
                traceback.print_exc()
            result = self.action_handler.execute(
                finish(message=str(e)), screenshot.width, screenshot.height
            )
        
        # Perform reflection analysis after action execution
        reflection_result = None
        if (self.agent_config.enable_reflection and 
            action.get("action") != "Finish" and 
            not result.should_finish):
            
            # Check if we should only reflect on failures
            should_reflect = True
            if self.agent_config.reflection_on_failure_only:
                should_reflect = not result.success
            
            if should_reflect:
                try:
                    reflection_result = self.reflect(action_type=action["action"], action_description=list(response.action.keys())[0], before_screenshot=before_screenshot)
                    
                    # Update node_action with reflection result
                    if reflection_result and 'node_action' in locals():
                        node_action.reflection_result = reflection_result
                        node_action.confidence_score = reflection_result.get('confidence_score')
                    
                    # Update result based on reflection if needed
                    if reflection_result and reflection_result.get('action_successful') is False:
                        if self.agent_config.verbose:
                            print(f"⚠️  Reflection indicates action may have failed: {reflection_result.get('reflection_reasoning', 'Unknown reason')}")
                        # Optionally modify result or add to context for next step
                    # print(f"reflection_result: {reflection_result}")

                except Exception as e:
                    if self.agent_config.verbose:
                        print(f"Reflection analysis failed: {e}")
        
        # 记录动作执行结果到错误分析器
        self.error_analyzer.record_action_result(action, result.success)
        
        # 如果动作失败且有reflection结果，进行错误模式分析
        if (not result.success and reflection_result and 
            reflection_result.get('action_successful') is False):
            
            ui_context = {
                "current_app": current_app,
                "element_count": len(elements_info),
                "screenshot_size": (screenshot.width, screenshot.height)
            }
            
            try:
                error_pattern = self.error_analyzer.analyze_failure(
                    action=action,
                    reflection_result=reflection_result,
                    ui_context=ui_context,
                    recent_history=self._actions_executed[-5:]  # 最近5个动作
                )
                
                if error_pattern and self.agent_config.verbose:
                    print(f"🔍 Error Pattern Detected: {error_pattern.pattern_type}")
                    print(f"📝 Description: {error_pattern.description}")
                    print(f"💡 Suggestions: {'; '.join(error_pattern.suggested_alternatives[:2])}")
                    print("-" * 50)
                    
            except Exception as e:
                if self.agent_config.verbose:
                    print(f"Error pattern analysis failed: {e}")
        
        # Add executed action to the actions list
        self._actions_executed.append(action)

        # Add assistant response to context
        self._context.add_history_entry(response.thinking, response.action, response.tag)
        
        # Include simplified reflection result in context if available and meaningful
        if reflection_result:
            # Only add reflection to context if it indicates failure or provides important insights
            action_successful = reflection_result.get('action_successful')
            confidence_score = reflection_result.get('confidence_score', 0.0)
            
            # Add to context only if:
            # 1. Action failed (action_successful is False)
            # 2. Low confidence (< 0.7) indicating uncertainty
            # 3. Has important improvement suggestions
            should_add_to_context = (
                action_successful is False or 
                confidence_score < 0.7 or
                (reflection_result.get('improvement_suggestions', '').strip() and 
                 reflection_result.get('execution_result') != 'success')
            )
            
            if should_add_to_context:
                # Create a simplified reflection message with only key information
                reflect_parts = []
                
                if action_successful is False:
                    reflect_parts.append(f"Action may have failed")
                elif confidence_score < 0.7:
                    reflect_parts.append(f"Action success uncertain (confidence: {confidence_score:.2f})")
                
                # Add key insights
                reasoning = reflection_result.get('reflection_reasoning', '').strip()
                if reasoning:
                    reflect_parts.append(f"Observation: {reasoning}")
                
                # Add improvement suggestions if action wasn't fully successful
                suggestions = reflection_result.get('improvement_suggestions', '').strip()
                if suggestions and reflection_result.get('execution_result') != 'success':
                    reflect_parts.append(f"Suggestion: {suggestions}")
                
                if reflect_parts:
                    self._context.add_reflection(
                        action_type=action["action"],
                        success=action_successful,
                        confidence=confidence_score,
                        reasoning=reasoning,
                        suggestions=suggestions
                    )
                    
                    if self.agent_config.verbose:
                        reflect_message = "Reflection: " + "; ".join(reflect_parts)
                        print(f"📝 Added simplified reflection to context: {reflect_message}")
            elif self.agent_config.verbose:
                # For successful actions, we can optionally add a simple success reflection
                # but keep it minimal to avoid context bloat
                print("✅ Reflection indicates success - not adding to context to contentkeep it clean")

            # print(f"📚 Context:\n {self._context.to_messages()}\n")

        if self.agent_config.verbose:
            print(f"Context length: {len(self._context.to_messages())} messages")

        if is_first:
            recorder.set_tag(response.tag)
        
        # Set the tag for the current node to enable proper memory loading
        if response.tag and response.tag.strip():
            node.add_tag(tag=response.tag)
        
        recorder.on_action_executed(
            from_node_id=node.id,
            action=node_action,
            success=result.success,
        )

        # Check if finished
        finished = action.get("action") == "Finish" or result.should_finish
        
        
        # Cache the after-action screenshot for next step's before_screenshot
        # This avoids redundant screenshot capture in consecutive steps
        if not finished:
            try:
                self._last_screenshot = device_factory.get_screenshot(device_id=self.agent_config.device_id)
                if self.agent_config.verbose:
                    print("📸 Cached after-action screenshot for next step")
            except Exception as e:
                if self.agent_config.verbose:
                    print(f"Failed to cache screenshot: {e}")
                self._last_screenshot = None

        if finished:
            recorder.flush()
            if self.agent_config.verbose:
                msgs = get_messages(self.agent_config.lang)
                print("\n" + "🎉 " + "=" * 48)
                print(
                    f"✅ {msgs['task_completed']}: {result.message or action.get('message', msgs['done'])}"
                )
                print("=" * 50 + "\n")
        
        return StepResult(
            success=result.success,
            finished=finished,
            action=action,
            thinking=response.thinking,
            predict=response.predict,
            tag=response.tag,
            message=result.message or action.get("message"),
        )

    @property
    def context(self) -> list[dict[str, Any]]:
        """Get the current conversation context."""
        return self._context.to_messages()

    @property
    def step_count(self) -> int:
        """Get the current step count."""
        return self._step_count

    def reflect(
        self,
        action_type: str,
        action_description: str,
        before_screenshot: Any = None,
        is_skill_execution: bool = False
    ) -> dict[str, Any]:
        """
        Reflect on action execution by comparing before and after interface states.

        Returns:
            {
                action_successful: True / False / None,
                execution_result: success / partial_success / failure,
                interface_changes: str,
                expected_vs_actual: str,
                abnormal_states: str,
                improvement_suggestions: str,
                confidence_score: float (0~1),
                reflection_reasoning: str,
                used_model_analysis: bool,
                elements_before: int,
                elements_after: int
            }
        """
        device_factory = get_device_factory()

        # ---------- 1. Validate input ----------
        if before_screenshot is None:
            if self.agent_config.verbose:
                print("⚠️ Reflect skipped: missing before screenshot")

            return {
                "action_successful": None,
                "execution_result": "failure",
                "interface_changes": "Missing before screenshot",
                "expected_vs_actual": "Reflection requires before and after UI states",
                "abnormal_states": "Insufficient data",
                "improvement_suggestions": "Capture UI state before executing the action.",
                "confidence_score": 0.0,
                "reflection_reasoning": "Before screenshot not provided",
                "used_model_analysis": False,
                "elements_before": 0,
                "elements_after": 0,
            }

        # ---------- 2. Capture after screenshot ----------
        current_screenshot = device_factory.get_screenshot(
            device_id=self.agent_config.device_id
        )

        # ---------- 3. Extract UI elements ----------
        before_elements = [
            {
                "content": e.elem_id,
                "checked": e.checked,
                "focused": e.focused,
                "bbox": e.bbox,
            }
            for e in before_screenshot.elements
        ]

        after_elements = [
            {
                "content": e.elem_id,
                "checked": e.checked,
                "focused": e.focused,
                "bbox": e.bbox,
            }
            for e in current_screenshot.elements
        ]

        # ---------- 4. Fast-path for atomic actions ----------
        changes_analysis = self._analyze_interface_changes(
            before_elements, after_elements
        )

        has_obvious_changes = changes_analysis.get("has_obvious_changes", False)
        interface_changes = changes_analysis.get("changes_description", "")

        if not is_skill_execution and has_obvious_changes:
            if self.agent_config.verbose:
                print("✅ Obvious UI changes detected — atomic action assumed successful")

            return {
                "action_successful": True,
                "execution_result": "success",
                "interface_changes": interface_changes,
                "expected_vs_actual": "UI changed consistently with atomic action",
                "abnormal_states": "None",
                "improvement_suggestions": "",
                "confidence_score": 0.9,
                "reflection_reasoning": interface_changes,
                "used_model_analysis": False,
                "elements_before": len(before_elements),
                "elements_after": len(after_elements),
            }
        elif not has_obvious_changes:
            print("⚠️ Reflect: no obvious UI changes detected")

        # ---------- 5. Build JSON-only reflect prompt ----------
        reflection_prompt = f"""
    You are an action execution evaluator for an Android UI agent.

    Executed action:
    - Type: {action_type}
    - Description: {action_description}

    UI state comparison:
    - Elements before execution: {len(before_elements)}
    - Elements after execution: {len(after_elements)}

    Analyze the action effectiveness by comparing the UI before and after execution.

    Return your evaluation STRICTLY in the following JSON format.
    Do NOT include any extra text.

    {{
    "execution_result": "success | partial_success | failure",
    "ui_changes": "Brief description of observed interface changes or lack thereof",
    "goal_achievement": "Whether and how the action goal was achieved",
    "abnormal_states": "Any detected errors, abnormal UI states, or unexpected behaviors",
    "reasoning": "Clear reasoning supporting the judgment",
    "improvement_suggestions": "Concrete suggestions to fix, retry, or re-plan if the action was not fully successful",
    "confidence": 0.0
    }}
    """.strip()

        # ---------- 6. Call model ----------
        reflection_context = [
            MessageBuilder.create_system_message(
                "You are a professional Android UI reflection module."
            ),
            MessageBuilder.create_user_message(
                text=f"{reflection_prompt}\n\nBefore screenshot:",
                image_base64=before_screenshot.base64_data,
            ),
            MessageBuilder.create_user_message(
                text="After screenshot:",
                image_base64=current_screenshot.base64_data,
            ),
        ]

        try:
            response = self.model_client.request(reflection_context, mode="reflect")
            raw_output = response.raw_content.strip()

            # ---------- 7. Robust JSON extraction ----------
            try:
                reflect_json = extract_json(raw_output)
            except Exception:
                if self.agent_config.verbose:
                    print("❌ Invalid JSON returned by reflect model")
                    print(raw_output)

                return {
                    "action_successful": None,
                    "execution_result": "failure",
                    "interface_changes": "Invalid reflection output",
                    "expected_vs_actual": raw_output,
                    "abnormal_states": "Model output not valid JSON",
                    "improvement_suggestions": "Retry reflection or enforce stricter output format.",
                    "confidence_score": 0.0,
                    "reflection_reasoning": "Model failed to follow JSON schema",
                    "used_model_analysis": True,
                    "elements_before": len(before_elements),
                    "elements_after": len(after_elements),
                }

            # ---------- 8. Normalize result ----------
            execution_result = reflect_json.get("execution_result", "failure")

            if execution_result == "success":
                action_successful = True
            elif execution_result == "failure":
                action_successful = False
            else:
                action_successful = None  # partial_success

            # Confidence
            confidence = reflect_json.get("confidence", 0.5)
            try:
                confidence = float(confidence)
                confidence = max(0.0, min(1.0, confidence))
            except Exception:
                confidence = 0.5


            return {
                "action_successful": action_successful,
                "execution_result": execution_result,
                "interface_changes": reflect_json.get("ui_changes", ""),
                "expected_vs_actual": reflect_json.get("goal_achievement", ""),
                "abnormal_states": reflect_json.get("abnormal_states", ""),
                "improvement_suggestions": reflect_json.get(
                    "improvement_suggestions", ""
                ),
                "confidence_score": confidence,
                "reflection_reasoning": reflect_json.get("reasoning", ""),
                "used_model_analysis": True,
                "elements_before": len(before_elements),
                "elements_after": len(after_elements),
            }

        except Exception as e:
            if self.agent_config.verbose:
                print("❌ Exception during reflection:", e)
                traceback.print_exc()

            return {
                "action_successful": None,
                "execution_result": "failure",
                "interface_changes": "Reflection crashed",
                "expected_vs_actual": str(e),
                "abnormal_states": "Runtime exception",
                "improvement_suggestions": "Retry action or re-plan from a stable UI state.",
                "confidence_score": 0.0,
                "reflection_reasoning": f"Reflection error: {e}",
                "used_model_analysis": True,
                "elements_before": len(before_elements),
                "elements_after": len(after_elements),
            }

    def _analyze_interface_changes(self, before_elements: list, after_elements: list) -> dict:
        """Analyze interface changes between before and after states.
        
        Returns:
            Dictionary containing:
            - element_count_diff: Difference in element count
            - new_contents: Set of new content
            - removed_contents: Set of removed content  
            - state_changes: List of state change descriptions
            - has_obvious_changes: Boolean indicating if changes are obvious
            - changes_description: String description of changes
        """
        # Compare element counts
        element_count_diff = len(after_elements) - len(before_elements)
        
        # Compare element contents (simplified)
        before_contents = set(elem.get('content', '') for elem in before_elements if elem.get('content', '').strip())
        after_contents = set(elem.get('content', '') for elem in after_elements if elem.get('content', '').strip())
        
        new_contents = after_contents - before_contents
        removed_contents = before_contents - after_contents
        
        # Compare element states
        state_changes = self._compare_element_states(before_elements, after_elements)
        
        # Determine if changes are obvious
        has_obvious_changes = self._determine_obvious_changes(
            element_count_diff, new_contents, removed_contents, state_changes
        )
        
        # Build description
        changes_description = self._build_changes_description(
            element_count_diff, new_contents, removed_contents, state_changes
        )
        
        return {
            'element_count_diff': element_count_diff,
            'new_contents': new_contents,
            'removed_contents': removed_contents,
            'state_changes': state_changes,
            'has_obvious_changes': has_obvious_changes,
            'changes_description': changes_description
        }

    def _compare_element_states(self, before_elements: list, after_elements: list) -> list:
        """Compare states of elements between before and after states."""
        changes = []
        
        # Create dictionaries for quick lookup using content and bbox for better matching
        def create_element_key(elem):
            content = elem.get('content', '')
            bbox = elem.get('bbox', [])
            # Use content and approximate position for matching
            if bbox and len(bbox) >= 4:
                return f"{content}_{int(bbox[0]/10)}_{int(bbox[1]/10)}"  # Approximate position
            return content
        
        before_dict = {create_element_key(elem): elem for elem in before_elements}
        after_dict = {create_element_key(elem): elem for elem in after_elements}
        
        # Find elements that exist in both lists and compare their states
        common_keys = set(before_dict.keys()) & set(after_dict.keys())
        # print(f"Common keys: {common_keys}")
        
        for key in common_keys:
            before_elem = before_dict[key]
            after_elem = after_dict[key]
            
            # Compare option state (this is the actual field used in the data structure)
            before_option = before_elem.get('checked', None)
            after_option = after_elem.get('checked', None)
            # print(f"before_option: {before_option}, after_option: {after_option}")
            
            
            if before_option != after_option:
                content = before_elem.get('content', 'Unknown element')
                # print(f"Content: {content}, before_option: {before_option}, after_option: {after_option}")
                if content.strip():  # Only report changes for elements with meaningful content
                    # if before_option is None and after_option is not None:
                    #     changes.append(f"Element '{content}' became active/selected")
                    # elif before_option is not None and after_option is None:
                    #     changes.append(f"Element '{content}' became inactive/deselected")
                    # elif before_option != after_option:
                    #     status = "activated" if after_option else "deactivated"
                    #     changes.append(f"Element '{content}' {status}")
                    changes.append(f"Element '{content}' {after_option}")
            
            # Compare focused state (this is the actual field used in the data structure)
            before_focused = before_elem.get('focused', None)
            after_focused = after_elem.get('focused', None)

            if before_focused != after_focused:
                if before_focused == "enabled" and after_focused == "disabled":
                    before_content = before_elem.get('content', 'Unknown element')
                    # print(f"Element '{before_content}' lost focus")
                    changes.append(f"Element '{before_content}' lost focus")
                elif before_focused == "disabled" and after_focused == "enabled":
                    after_content = after_elem.get('content', 'Unknown element')
                    # print(f"Element '{after_content}' gained focus")
                    changes.append(f"Element '{after_content}' gained focus")

        
        # Also check for elements that appeared or disappeared with specific states
        before_keys = set(before_dict.keys())
        after_keys = set(after_dict.keys())
        
        # New elements with active states
        new_keys = after_keys - before_keys
        for key in new_keys:
            elem = after_dict[key]
            if elem.get('checked') is not None:
                content = elem.get('content', 'Unknown element')
                if content.strip():
                    changes.append(f"New active element appeared: '{content}'")
        
        # Disappeared elements that were active
        removed_keys = before_keys - after_keys
        for key in removed_keys:
            elem = before_dict[key]
            if elem.get('checked') is not None:
                content = elem.get('content', 'Unknown element')
                if content.strip():
                    changes.append(f"Active element disappeared: '{content}'")
        # print(f"Changes: {changes}")
        return changes

    def _determine_obvious_changes(self, element_count_diff: int, new_contents: set, 
                                 removed_contents: set, state_changes: list) -> bool:
        """Determine if interface changes are obvious enough to indicate successful action."""
        
        # Significant change in element count
        if abs(element_count_diff) > 2:  # More than 2 elements added/removed
            return True
        
        # Significant content changes
        if len(new_contents) > 3 or len(removed_contents) > 3:
            return True
        
        # Check for specific indicators of successful actions
        new_content_text = ' '.join(new_contents).lower()
        removed_content_text = ' '.join(removed_contents).lower()
        
        # Common success indicators
        success_indicators = [
            'success', 'complete', 'done', 'sent', 'saved', 'created', 'deleted',
            'updated', 'confirmed', 'submitted', 'added', 'removed', 'opened',
            'closed', 'started', 'stopped', 'enabled', 'disabled'
        ]
        
        for indicator in success_indicators:
            if indicator in new_content_text:
                return True
        
        # Check for navigation changes (new screens, dialogs, etc.)
        navigation_indicators = [
            'back', 'next', 'continue', 'cancel', 'ok', 'yes', 'no',
            'menu', 'settings', 'home', 'profile', 'login', 'logout'
        ]
        
        for indicator in navigation_indicators:
            if indicator in new_content_text and indicator not in removed_content_text:
                return True
        
        
        # Check for state changes (e.g., toggles, checkboxes, buttons)
        if state_changes:
            return True
        
        return False

    def _build_changes_description(self, element_count_diff: int, new_contents: set, 
                                 removed_contents: set, state_changes: list) -> str:
        """Build a description of interface changes."""
        changes = []
        
        # Describe element count changes
        if element_count_diff > 0:
            changes.append(f"Added {element_count_diff} interface elements")
        elif element_count_diff < 0:
            changes.append(f"Removed {abs(element_count_diff)} interface elements")
        else:
            changes.append("Interface element count remained the same")
        
        # Describe content changes
        if new_contents:
            changes.append(f"New content appeared: {', '.join(list(new_contents)[:3])}")
        if removed_contents:
            changes.append(f"Content disappeared: {', '.join(list(removed_contents)[:3])}")
        
        # Add state changes
        if state_changes:
            changes.extend(state_changes)
        
        return "; ".join(changes) if changes else "No obvious interface changes detected"
