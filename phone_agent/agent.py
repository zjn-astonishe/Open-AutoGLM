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

        self._context: list[dict[str, Any]] = []
        self._step_count = 0

    def run(self, task: str) -> str:
        """
        Run the agent to complete a task.

        Args:
            task: Natural language description of the task.

        Returns:
            Final message from the agent.
        """
        self._context = []
        self._step_count = 0
        self.memory.from_json()

        workflow = self.memory.create_workflow(task)
        recorder = WorkflowRecorder(task=task, workflow=workflow)
        
        
        # First step with user prompt
        result = self._execute_step(task, recorder, is_first=True)
        

        if result.finished:
            return result.message or "Task completed"

        # Continue until finished or max steps reached
        while self._step_count < self.agent_config.max_steps:
            result = self._execute_step(task, recorder, is_first=False)

            if result.finished:
                self.memory.to_json()
                return result.message or "Task completed"
        
        self.memory.to_json()

        return "Max steps reached"

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

    def _execute_step(
        self, user_prompt: str, recorder: WorkflowRecorder, is_first: bool = False
    ) -> StepResult:
        """Execute a single step of the agent loop."""
        self._step_count += 1

        # Capture current screen state
        device_factory = get_device_factory()
        screenshot = device_factory.get_screenshot(self.agent_config.device_id)
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
                "path": e.get_xpath()
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
