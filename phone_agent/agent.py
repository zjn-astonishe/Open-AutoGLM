"""Main PhoneAgent class for orchestrating phone automation."""

import os
import time
import json
import traceback
from dataclasses import dataclass
from typing import Any, Callable

from phone_agent.actions import ActionHandler
from phone_agent.actions.handler import do, finish, parse_action
from phone_agent.config import get_messages, get_system_prompt
from phone_agent.device_factory import get_device_factory
from phone_agent.model import ModelClient, ModelConfig
from phone_agent.model.client import MessageBuilder
from phone_agent.planner import Planner
from phone_agent.skill_executor import SkillExecutor

from act_mem.act_mem import ActionMemory
from act_mem.workrecorder import WorkflowRecorder

@dataclass
class AgentConfig:
    """Configuration for the PhoneAgent."""

    max_steps: int = 100
    device_id: str | None = None
    lang: str = "cn"
    system_prompt: str | None = None
    verbose: bool = True
    memory_dir: str = "./output/memory"

    def __post_init__(self):
        if self.system_prompt is None:
            self.system_prompt = get_system_prompt(self.lang)


@dataclass
class StepResult:
    """Result of a single agent step."""

    success: bool
    finished: bool
    action: dict[str, Any] | None
    thinking: str
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

        self.planner = Planner(model_config=model_config)
        self.skill_executor = SkillExecutor(device_id=self.agent_config.device_id)

        self._context: list[dict[str, Any]] = []
        self._step_count = 0
        self._actions_executed: list[dict[str, Any]] = []

    def run(self, task: str) -> dict[str, Any]:
        """
        Run the agent to complete a task.

        Args:
            task: Natural language description of the task.

        Returns:
            Dictionary containing execution results with actions list.
        """
        self._context = []
        self._step_count = 0
        self._actions_executed = []
        # self.memory.from_json()

        start_time = time.time()
        plan = self.planner.plan_task(task)
        end_time = time.time()
        print(f"Planning taken: {end_time - start_time:.2f} seconds")
        if plan.decision == "use_skill":
            start_time = time.time()
            actions = self.planner.execute_skill(plan.skill_name, plan.skill_params)
            self.skill_executor.run(actions=actions)
            end_time = time.time()
            print(f"Execution taken: {end_time - start_time:.2f} seconds")

        workflow = self.memory.create_workflow(task)
        recorder = WorkflowRecorder(task=task, workflow=workflow)
        
        
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
        is_first = len(self._context) == 0

        if is_first and not task:
            raise ValueError("Task is required for the first step")

        return self._execute_step(task, is_first)

    def reset(self) -> None:
        """Reset the agent state for a new task."""
        self._context = []
        self._step_count = 0
        self._actions_executed = []

    def _execute_step(
        self, user_prompt: str, recorder: WorkflowRecorder, is_first: bool = False
    ) -> StepResult:
        """Execute a single step of the agent loop."""
        self._step_count += 1

        # Capture current screen state
        device_factory = get_device_factory()
        screenshot = device_factory.get_screenshot(device_id=self.agent_config.device_id)
        current_app = device_factory.get_current_app(self.agent_config.device_id)
        
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
            }
            
            elements_info.append({
                "id": f"R{i}",
                **common_fields,
                "bbox": e.bbox,
            })
            elements.append({
                **common_fields,
                "path": e.get_simple_xpath()
            })

        node = work_graph.create_node(elements)
        node.add_task(user_prompt)
        if not is_first:
            recorder.on_new_node(current_node_id=node.id)

        # Build messages
        if is_first:
            self._context.append(
                MessageBuilder.create_system_message(self.agent_config.system_prompt)
            )
            
            screen_info = MessageBuilder.build_screen_info(current_app, extra_info=elements_info)
            text_content = f"{user_prompt}\n\n{screen_info}"

            self._context.append(
                MessageBuilder.create_user_message(
                    text=text_content, image_base64=screenshot.base64_data
                )
            )
        else:
            screen_info = MessageBuilder.build_screen_info(current_app, extra_info=elements_info)
            text_content = f"** Screen Info **\n\n{screen_info}"

            self._context.append(
                MessageBuilder.create_user_message(
                    text=text_content, image_base64=screenshot.base64_data
                )
            )

        # Get model response
        try:
            msgs = get_messages(self.agent_config.lang)
            print("\n" + "=" * 50)
            print(f"💭 {msgs['thinking']}:")
            print("-" * 50)
            # print(f"+" * 50)
            # print(f"system_prompt: {self.agent_config.system_prompt}")
            # print(f"Context: {screen_info}")
            # print(f"+" * 50)
            start_time = time.time()
            response = self.model_client.request(self._context)
            end_time = time.time()
            node.add_tag(tag=response.tag)
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
        try:
            # Extract action string from response.action dict
            # action_str = list(response.action.values())[0]
            action, element_content = parse_action(action_code=list(response.action.values())[0], elements_info=elements_info)
            if element_content is None:
                node_action = node.add_action(action_type=action["action"], description=list(response.action.keys())[0])
            else:
                for e in elements:
                    if e["content"] == element_content:            
                        node_action = node.add_action(action_type=action["action"], description=list(response.action.keys())[0], zone_path=e["path"])
        except ValueError:
            if self.agent_config.verbose:
                traceback.print_exc()
            action = finish(message=response.action)

        if self.agent_config.verbose:
            # Print thinking process
            print("-" * 50)
            print(f"🎯 {msgs['action']}:")
            print(json.dumps(action, ensure_ascii=False, indent=2))
            print("=" * 50 + "\n")
                

        # Remove image from context to save space
        self._context[-1] = MessageBuilder.remove_images_from_message(self._context[-1])

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
        
        # Add executed action to the actions list
        self._actions_executed.append(action)

        # Add assistant response to context
        self._context.append(
            MessageBuilder.create_assistant_message(
                f"{response.thinking} {list(response.action.keys())[0]}"
            )
        )

        if is_first:
            recorder.set_tag(response.tag)
        
        recorder.on_action_executed(
            from_node_id=node.id,
            action=node_action,
            success=result.success,
        )

        # Check if finished
        finished = action.get("action") == "Finish" or result.should_finish
        # print(f"Step finished: {finished}")

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
            message=result.message or action.get("message"),
        )

    @property
    def context(self) -> list[dict[str, Any]]:
        """Get the current conversation context."""
        return self._context.copy()

    @property
    def step_count(self) -> int:
        """Get the current step count."""
        return self._step_count

    def reflect(self, action: dict[str, Any], before_screenshot: Any = None) -> dict[str, Any]:
        """
        Reflect on action execution by comparing before and after interface states.
        
        This method evaluates whether an action was successfully executed by analyzing
        the changes in the interface before and after the action.
        
        Args:
            action: The action that was executed
            before_screenshot: Screenshot before action execution (optional, will capture if not provided)
            after_screenshot: Screenshot after action execution (optional, will capture if not provided)
            
        Returns:
            Dictionary containing reflection results with:
            - action_successful: Boolean indicating if action was successful
            - interface_changes: Description of observed interface changes
            - expected_vs_actual: Comparison of expected vs actual results
            - confidence_score: Confidence level of the evaluation (0-1)
            - reflection_reasoning: Detailed reasoning for the evaluation
        """
        device_factory = get_device_factory()
        
        # Capture screenshots if not provided
        if before_screenshot is None:
            if self.agent_config.verbose:
                print("Warning: Preview Screenshot not provided.")
            
            return {
                'action_successful': None,
                'interface_changes': "Cannot evaluate - missing before screenshot",
                'expected_vs_actual': "Evaluation requires both before screenshot",
                'confidence_score': 0.0,
                'reflection_reasoning': "Insufficient data for reflection analysis"
            }
        current_screenshot = device_factory.get_screenshot(device_id=self.agent_config.device_id)
        
        # Extract elements info from both screenshots
        before_elements = []
        after_elements = []
        
        for i, e in enumerate(before_screenshot.elements, 1):
            before_elements.append({
                "content": e.elem_id,
                "option": e.checked,
                "bbox": e.bbox,
            })
            
        for i, e in enumerate(current_screenshot.elements, 1):
            after_elements.append({
                "content": e.elem_id,
                "option": e.checked,
                "bbox": e.bbox,
            })
        
        # Build reflection prompt
        action_type = action.get('action', 'unknown')
        action_description = action.get('message', 'No description')
        
        # First check if there are obvious interface changes
        interface_changes = self._extract_interface_changes(before_elements, after_elements)
        has_obvious_changes = self._has_obvious_changes(before_elements, after_elements)
        
        # If there are obvious changes, assume action was successful without model analysis
        if has_obvious_changes:
            if self.agent_config.verbose:
                print("\n" + "🤔 " + "=" * 48)
                print("🔍 REFLECTION ANALYSIS")
                print("-" * 50)
                print(f"Action: {action_type}")
                print(f"Description: {action_description}")
                print("Obvious interface changes detected - assuming success")
                print("=" * 50 + "\n")
            
            return {
                'action_successful': True,
                'interface_changes': interface_changes,
                'expected_vs_actual': "Obvious interface changes detected, action appears successful",
                'confidence_score': 0.9,
                'reflection_reasoning': f"Interface changes detected: {interface_changes}. No model analysis needed.",
                'action_analyzed': action,
                'elements_before': len(before_elements),
                'elements_after': len(after_elements),
                'used_model_analysis': False
            }
        
        # Only use model analysis when no obvious changes are detected
        if self.agent_config.verbose:
            print("\n" + "🤔 " + "=" * 48)
            print("🔍 REFLECTION ANALYSIS")
            print("-" * 50)
            print(f"Action: {action_type}")
            print(f"Description: {action_description}")
            print("No obvious changes detected - using model analysis")
            print("-" * 50)
        
        # Create comparison context for the model
        reflection_prompt = f"""
Please analyze the effectiveness of the following action execution:

Executed action: {action_type}
Action description: {action_description}

Please compare the interface changes before and after execution to evaluate if the action was successful.

Elements before execution: {len(before_elements)}
Elements after execution: {len(after_elements)}

Please analyze from the following aspects:
1. Whether the interface changed as expected
2. Whether the action goal was achieved
3. Whether any errors or abnormal states occurred
4. Overall execution effectiveness evaluation

Please provide:
- Whether the action was successful (success/failure/partial success)
- Observed interface changes
- Confidence level of evaluation (0-1)
- Detailed analysis reasoning
"""
        
        # Use model to analyze the interface changes
        try:
            reflection_context = [
                MessageBuilder.create_system_message("You are a professional interface analysis expert, skilled at evaluating action execution effectiveness by comparing before and after interface states."),
                MessageBuilder.create_user_message(
                    text=reflection_prompt,
                    image_base64=[before_screenshot.base64_data, current_screenshot.base64_data]
                )
            ]
            
            if self.agent_config.verbose:
                print("\n" + "🤔 " + "=" * 48)
                print("🔍 REFLECTION ANALYSIS")
                print("-" * 50)
                print(f"Analyzing action: {action_type}")
                print(f"Description: {action_description}")
                print("-" * 50)
            
            start_time = time.time()
            response = self.model_client.request(reflection_context)
            end_time = time.time()
            
            if self.agent_config.verbose:
                print(f"Reflection analysis time: {end_time - start_time:.2f} seconds")
                print(f"Analysis result: {response.thinking}")
                print("=" * 50 + "\n")
            
            # Parse the model response to extract evaluation results
            analysis_text = response.thinking.lower()
            
            # Determine success based on model response
            if "success" in analysis_text and "failure" not in analysis_text:
                action_successful = True
                confidence = 0.8
            elif "failure" in analysis_text or "failed" in analysis_text:
                action_successful = False
                confidence = 0.8
            elif "partial" in analysis_text:
                action_successful = None  # Partial success
                confidence = 0.6
            else:
                action_successful = None  # Uncertain
                confidence = 0.4
            
            # Extract interface changes description
            interface_changes = self._extract_interface_changes(before_elements, after_elements)
            
            reflection_result = {
                'action_successful': action_successful,
                'interface_changes': interface_changes,
                'expected_vs_actual': response.thinking,
                'confidence_score': confidence,
                'reflection_reasoning': response.thinking,
                'action_analyzed': action,
                'elements_before': len(before_elements),
                'elements_after': len(after_elements)
            }
            
            return reflection_result
            
        except Exception as e:
            if self.agent_config.verbose:
                print(f"Error during reflection analysis: {e}")
                traceback.print_exc()
            
            return {
                'action_successful': None,
                'interface_changes': "Analysis failed due to error",
                'expected_vs_actual': f"Error occurred: {str(e)}",
                'confidence_score': 0.0,
                'reflection_reasoning': f"Reflection analysis failed: {str(e)}",
                'action_analyzed': action,
                'elements_before': len(before_elements) if 'before_elements' in locals() else 0,
                'elements_after': len(after_elements) if 'after_elements' in locals() else 0
            }
    
    def _extract_interface_changes(self, before_elements: list, after_elements: list) -> str:
        """Extract and describe interface changes between before and after states."""
        changes = []
        
        # Compare element counts
        if len(after_elements) > len(before_elements):
            changes.append(f"Added {len(after_elements) - len(before_elements)} interface elements")
        elif len(after_elements) < len(before_elements):
            changes.append(f"Removed {len(before_elements) - len(after_elements)} interface elements")
        else:
            changes.append("Interface element count remained the same")
        
        # Compare element contents (simplified)
        before_contents = set(elem.get('content', '') for elem in before_elements)
        after_contents = set(elem.get('content', '') for elem in after_elements)
        
        new_contents = after_contents - before_contents
        removed_contents = before_contents - after_contents
        
        if new_contents:
            changes.append(f"New content appeared: {', '.join(list(new_contents)[:3])}")
        if removed_contents:
            changes.append(f"Content disappeared: {', '.join(list(removed_contents)[:3])}")
        
        return "; ".join(changes) if changes else "No obvious interface changes detected"

    def _has_obvious_changes(self, before_elements: list, after_elements: list) -> bool:
        """Check if there are obvious interface changes that indicate successful action execution."""
        
        # Significant change in element count
        element_count_diff = abs(len(after_elements) - len(before_elements))
        if element_count_diff > 2:  # More than 2 elements added/removed
            return True
        
        # Compare element contents
        before_contents = set(elem.get('content', '') for elem in before_elements if elem.get('content', '').strip())
        after_contents = set(elem.get('content', '') for elem in after_elements if elem.get('content', '').strip())
        
        new_contents = after_contents - before_contents
        removed_contents = before_contents - after_contents
        
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
        
        return False
