import os
import time
import importlib.util
from dataclasses import dataclass
from .device_factory import get_device_factory
from typing import List, Dict, Any, Callable, Optional
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
    
    def execute_skill(self, skill_name: str, skill_params: Dict[str, Any]) -> str:
        """Execute a skill by name with given parameters."""
        try:
            # Get skill file path
            skill_path = self._get_skill_path(skill_name)
            if not skill_path:
                return f"Error: Skill '{skill_name}' not found"
            
            # Load skill module
            spec = importlib.util.spec_from_file_location(skill_name, skill_path)
            if spec is None or spec.loader is None:
                return f"Error: Could not load skill '{skill_name}'"
            
            skill_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(skill_module)
            
            # Execute skill function
            if hasattr(skill_module, skill_name):
                skill_function = getattr(skill_module, skill_name)
                actions = skill_function(**skill_params)
                
                # Execute actions using existing run method
                return self.run(actions)
            else:
                return f"Error: Function '{skill_name}' not found in skill module"
                
        except Exception as e:
            return f"Error executing skill '{skill_name}': {str(e)}"
    
    def _get_skill_path(self, skill_name: str) -> Optional[str]:
        """Get the file path for a skill."""
        skill_dir = "code_generator/skills"
        skill_file = f"{skill_name}.py"
        skill_path = os.path.join(skill_dir, skill_file)
        
        if os.path.exists(skill_path):
            return skill_path
        return None
    
    def run(self, actions: List[Dict[str, Any]]) -> str:
        
        if not actions:
            return "Error, No actions provided"
        
        result = None
        for action in actions:
            result = self._execute_step(action)
            # If any action fails, return immediately
            if not result.success:
                return f"Error, {result.message}"

        # All actions succeeded
        if result and result.success:
            return "Success"
        
        return "Error, Unknown error occurred"

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
