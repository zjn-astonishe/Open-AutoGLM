import time
from dataclasses import dataclass
from .device_factory import get_device_factory
from typing import List, Dict, Any, Callable
from .actions.handler import ActionHandler, finish
from code_generator import extract_element_id

@dataclass
class StepResult:
    """Result of a single agent step."""

    success: bool
    message: str | None = None

class SkillExecutor:
    
    def __init__(
            self, 
            device_id: str,
            confirmation_callback: Callable[[str], bool] | None = None,
            takeover_callback: Callable[[str], None] | None = None,
        ) -> None:
        self.device_id = device_id
        self.action_handler = ActionHandler(
            device_id=device_id,
            confirmation_callback=confirmation_callback,
            takeover_callback=takeover_callback,
        )
    
    def run(self, actions: List[Dict[str, Any]]) -> str:
        
        for action in actions:
            result = self._execute_step(action)

        if result.success:
            return "Success"
        
        return f"Error, {result.message}"

    def _execute_step(self, action_code: Dict[str, Any]) -> StepResult:
        
        device_factory = get_device_factory()
        screenshot = device_factory.get_screenshot(device_id=self.device_id)
        elements_info = []

        for e in screenshot.elements:
            elements_info.append({
                "bbox": e.bbox,
                "path": extract_element_id(e.get_xpath())
            })

        action = self._parse_action(action_code, elements_info)
        print(f"Action: {action}")

        try:
            result = self.action_handler.execute(action, screenshot.width, screenshot.height)
        except Exception as e:
            result = self.action_handler.execute(
                finish(message=str(e)), screenshot.width, screenshot.height
            )
            return StepResult(False, str(e))
        

        return StepResult(
            success=result.success,
            message=result.message or action.get("message"),
        )

    def _parse_action(self, action_code: Dict[str, Any], elements_info: List[Dict[str, Any]]) -> dict[str, Any]:
        action = {"_metadata": "do"}
        for key, value in action_code.items():
            if key == "element":
                for element in elements_info:
                    if element["path"] == value:
                        bbox = element["bbox"]
                        center_x = (bbox[0][0] + bbox[1][0]) // 2
                        center_y = (bbox[0][1] + bbox[1][1]) // 2
                        action[key] = [center_x, center_y]
                        break
            else:
                action[key] = value

        return action
