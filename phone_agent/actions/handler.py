"""Action handler for processing AI model outputs."""

import ast
import asyncio
import re
import subprocess
import time
from dataclasses import dataclass
from typing import Any, Callable, List, Dict, Tuple

from phone_agent.config.timing import TIMING_CONFIG
from phone_agent.device_factory import get_device_factory


@dataclass
class ActionResult:
    """Result of an action execution."""

    success: bool
    should_finish: bool
    message: str | None = None
    requires_confirmation: bool = False


class ActionHandler:
    """
    Handles execution of actions from AI model output.

    Args:
        device_id: Optional ADB device ID for multi-device setups.
        confirmation_callback: Optional callback for sensitive action confirmation.
            Should return True to proceed, False to cancel.
        takeover_callback: Optional callback for takeover requests (login, captcha).
    """

    def __init__(
        self,
        device_id: str | None = None,
        confirmation_callback: Callable[[str], bool] | None = None,
        takeover_callback: Callable[[str], None] | None = None,
    ):
        self.device_id = device_id
        self.confirmation_callback = confirmation_callback or self._default_confirmation
        self.takeover_callback = takeover_callback or self._default_takeover

    async def execute(
        self, action: dict[str, Any], screen_width: int, screen_height: int
    ) -> ActionResult:
        """
        Execute an action from the AI model.

        Args:
            action: The action dictionary from the model.
            screen_width: Current screen width in pixels.
            screen_height: Current screen height in pixels.

        Returns:
            ActionResult indicating success and whether to finish.
        """
        action_type = action.get("_metadata")

        # if action_type == "finish":
        #     return ActionResult(
        #         success=True, should_finish=True, message=action.get("message")
        #     )

        # print(f"Action executing: {action_type}, {action}")

        if action_type != "do":
            return ActionResult(
                success=False,
                should_finish=True,
                message=f"Unknown action type: {action_type}",
            )

        action_name = action.get("action")
        # print(f"Action name: {action_name}")
        handler_method = self._get_handler(action_name)

        if handler_method is None:
            return ActionResult(
                success=False,
                should_finish=False,
                message=f"Unknown action: {action_name}",
            )

        try:
            return await handler_method(action, screen_width, screen_height)
        except Exception as e:
            return ActionResult(
                success=False, should_finish=False, message=f"Action failed: {e}"
            )

    def _get_handler(self, action_name: str) -> Callable | None:
        """Get the handler method for an action."""
        handlers = {
            "Launch": self._handle_launch,
            "Tap": self._handle_tap,
            "Type": self._handle_type,
            "Type_Name": self._handle_type,
            "Swipe": self._handle_swipe,
            "Back": self._handle_back,
            "Home": self._handle_home,
            "Double Tap": self._handle_double_tap,
            "Long Press": self._handle_long_press,
            "Wait": self._handle_wait,
            "Take_over": self._handle_takeover,
            "Note": self._handle_note,
            "Call_API": self._handle_call_api,
            "Interact": self._handle_interact,
            "Finish": self._handle_finish,
        }
        return handlers.get(action_name)

    def _convert_relative_to_absolute(
        self, element: list[int], screen_width: int, screen_height: int
    ) -> tuple[int, int]:
        """Convert relative coordinates (0-1000) to absolute pixels."""
        # x = int(element[0] / 1000 * screen_width)
        # y = int(element[1] / 1000 * screen_height)
        x = int(element[0])
        y = int(element[1])
        return x, y

    async def _handle_launch(self, action: dict, width: int, height: int) -> ActionResult:
        """Handle app launch action."""
        app_name = action.get("app")
        # print(f"Launching app: {app_name}")
        if not app_name:
            return ActionResult(False, False, "No app name specified")

        device_factory = await get_device_factory()
        success = await device_factory.launch_app(app_name, self.device_id)
        if success:
            return ActionResult(True, False)
        return ActionResult(False, False, f"App not found: {app_name}")

    async def _handle_tap(self, action: dict, width: int, height: int) -> ActionResult:
        """Handle tap action."""
        element = action.get("element")
        if not element:
            return ActionResult(False, False, "No element coordinates")

        x, y = self._convert_relative_to_absolute(element, width, height)
        # print(f"Tap coordinates: ({x}, {y}), element: {element}")

        # Check for sensitive operation
        if "message" in action:
            if not self.confirmation_callback(action["message"]):
                return ActionResult(
                    success=False,
                    should_finish=True,
                    message="User cancelled sensitive operation",
                )

        device_factory = await get_device_factory()
        await device_factory.tap(x, y, self.device_id)
        return ActionResult(True, False)

    async def _handle_type(self, action: dict, width: int, height: int) -> ActionResult:
        """Handle text input action."""
        text = action.get("text", "")
        element = action.get("element")
        if not element:
            return ActionResult(False, False, "No element coordinates")

        x, y = self._convert_relative_to_absolute(element, width, height)

        device_factory = await get_device_factory()
        await device_factory.tap(x, y, self.device_id)

        # Switch to ADB keyboard
        original_ime = await device_factory.detect_and_set_adb_keyboard(self.device_id)
        await asyncio.sleep(TIMING_CONFIG.action.keyboard_switch_delay)

        # Clear existing text and type new text
        await device_factory.clear_text(self.device_id)
        await asyncio.sleep(TIMING_CONFIG.action.text_clear_delay)

        # Handle multiline text by splitting on newlines
        await device_factory.type_text(text, self.device_id)
        await asyncio.sleep(TIMING_CONFIG.action.text_input_delay)

        # Restore original keyboard
        await device_factory.restore_keyboard(original_ime, self.device_id)
        await asyncio.sleep(TIMING_CONFIG.action.keyboard_restore_delay)

        return ActionResult(True, False)

    # def _handle_swipe(self, action: dict, width: int, height: int) -> ActionResult:
    #     """Handle swipe action."""
    #     start = action.get("start")
    #     end = action.get("end")

    #     if not start or not end:
    #         return ActionResult(False, False, "Missing swipe coordinates")

    #     start_x, start_y = self._convert_relative_to_absolute(start, width, height)
    #     end_x, end_y = self._convert_relative_to_absolute(end, width, height)

    #     device_factory = get_device_factory()
    #     device_factory.swipe(start_x, start_y, end_x, end_y, device_id=self.device_id)
    #     return ActionResult(True, False)
    
    async def _handle_swipe(self, action: dict, width: int, height: int) -> ActionResult:
        """Handle swipe action."""
        dist = action.get("distance", "medium")
        direction = action.get("direction")
        unit_dist = int(width / 10)
        if dist == "long":
            unit_dist *= 10
        elif dist == "medium":
            unit_dist *= 5
        elif dist == "short":
            unit_dist *= 2
        if direction == "up":
            offset = 0, -2 * unit_dist
        elif direction == "down":
            offset = 0, 2 * unit_dist
        elif direction == "left":
            offset = -1 * unit_dist, 0
        elif direction == "right":
            offset = unit_dist, 0
        else:
            return ActionResult(False, False, "Invalid swipe direction")
        start_x, start_y = action.get("element")
        device_factory = await get_device_factory()
        await device_factory.swipe(start_x, start_y, start_x+offset[0], start_y+offset[1], device_id=self.device_id)
        return ActionResult(True, False)

    async def _handle_back(self, action: dict, width: int, height: int) -> ActionResult:
        """Handle back button action."""
        device_factory = await get_device_factory()
        await device_factory.back(self.device_id)
        return ActionResult(True, False)

    async def _handle_home(self, action: dict, width: int, height: int) -> ActionResult:
        """Handle home button action."""
        device_factory = await get_device_factory()
        await device_factory.home(self.device_id)
        return ActionResult(True, False)

    async def _handle_double_tap(self, action: dict, width: int, height: int) -> ActionResult:
        """Handle double tap action."""
        element = action.get("element")
        if not element:
            return ActionResult(False, False, "No element coordinates")

        x, y = self._convert_relative_to_absolute(element, width, height)
        device_factory = await get_device_factory()
        await device_factory.double_tap(x, y, self.device_id)
        return ActionResult(True, False)

    async def _handle_long_press(self, action: dict, width: int, height: int) -> ActionResult:
        """Handle long press action."""
        element = action.get("element")
        if not element:
            return ActionResult(False, False, "No element coordinates")

        x, y = self._convert_relative_to_absolute(element, width, height)
        device_factory = await get_device_factory()
        await device_factory.long_press(x, y, device_id=self.device_id)
        return ActionResult(True, False)

    async def _handle_wait(self, action: dict, width: int, height: int) -> ActionResult:
        """Handle wait action."""
        duration_str = action.get("duration", "1 seconds")
        try:
            duration = float(duration_str.replace("seconds", "").strip())
        except ValueError:
            duration = 1.0

        await asyncio.sleep(duration)
        return ActionResult(True, False)

    async def _handle_takeover(self, action: dict, width: int, height: int) -> ActionResult:
        """Handle takeover request (login, captcha, etc.)."""
        message = action.get("message", "User intervention required")
        self.takeover_callback(message)
        return ActionResult(True, False)

    async def _handle_note(self, action: dict, width: int, height: int) -> ActionResult:
        """Handle note action (placeholder for content recording)."""
        # This action is typically used for recording page content
        # Implementation depends on specific requirements
        return ActionResult(True, False)

    async def _handle_call_api(self, action: dict, width: int, height: int) -> ActionResult:
        """Handle API call action (placeholder for summarization)."""
        # This action is typically used for content summarization
        # Implementation depends on specific requirements
        return ActionResult(True, False)

    async def _handle_interact(self, action: dict, width: int, height: int) -> ActionResult:
        """Handle interaction request (user choice needed)."""
        # This action signals that user input is needed
        return ActionResult(True, False, message="User interaction required")
    
    async def _handle_finish(self, action: dict, width: int, height: int) -> ActionResult:
        """Handle finish action."""
        return ActionResult(
            success=True, should_finish=True, message=action.get("message")
        )

    async def _send_keyevent(self, keycode: str) -> None:
        """Send a keyevent to the device."""
        from phone_agent.device_factory import DeviceType, get_device_factory
        from phone_agent.hdc.connection import _run_hdc_command

        device_factory = await get_device_factory()

        # Handle HDC devices with HarmonyOS-specific keyEvent command
        if device_factory.device_type == DeviceType.HDC:
            hdc_prefix = ["hdc", "-t", self.device_id] if self.device_id else ["hdc"]
            
            # Map common keycodes to HarmonyOS keyEvent codes
            # KEYCODE_ENTER (66) -> 2054 (HarmonyOS Enter key code)
            if keycode == "KEYCODE_ENTER" or keycode == "66":
                _run_hdc_command(
                    hdc_prefix + ["shell", "uitest", "uiInput", "keyEvent", "2054"],
                    capture_output=True,
                    text=True,
                )
            else:
                # For other keys, try to use the numeric code directly
                # If keycode is a string like "KEYCODE_ENTER", convert it
                try:
                    # Try to extract numeric code from string or use as-is
                    if keycode.startswith("KEYCODE_"):
                        # For now, only handle ENTER, other keys may need mapping
                        if "ENTER" in keycode:
                            _run_hdc_command(
                                hdc_prefix + ["shell", "uitest", "uiInput", "keyEvent", "2054"],
                                capture_output=True,
                                text=True,
                            )
                        else:
                            # Fallback to ADB-style command for unsupported keys
                            subprocess.run(
                                hdc_prefix + ["shell", "input", "keyevent", keycode],
                                capture_output=True,
                                text=True,
                            )
                    else:
                        # Assume it's a numeric code
                        _run_hdc_command(
                            hdc_prefix + ["shell", "uitest", "uiInput", "keyEvent", str(keycode)],
                            capture_output=True,
                            text=True,
                        )
                except Exception:
                    # Fallback to ADB-style command
                    subprocess.run(
                        hdc_prefix + ["shell", "input", "keyevent", keycode],
                        capture_output=True,
                        text=True,
                    )
        else:
            # ADB devices use standard input keyevent command
            cmd_prefix = ["adb", "-s", self.device_id] if self.device_id else ["adb"]
            subprocess.run(
                cmd_prefix + ["shell", "input", "keyevent", keycode],
                capture_output=True,
                text=True,
            )

    @staticmethod
    def _default_confirmation(message: str) -> bool:
        """Default confirmation callback using console input."""
        response = input(f"Sensitive operation: {message}\nConfirm? (Y/N): ")
        return response.upper() == "Y"

    @staticmethod
    def _default_takeover(message: str) -> None:
        """Default takeover callback using console input."""
        input(f"{message}\nPress Enter after completing manual operation...")


def parse_action(action_code: str, elements_info: List[Dict[str, str]], is_portal: bool = True) -> Tuple[dict[str, Any], str]:
    """
    Parse action from model response.

    Args:
        action_code: The raw action string from the model.

    Returns:
        Parsed action dictionary.

    Raises:
        ValueError: If the response cannot be parsed.
    """
    # print(f"Parsing action: {response}")
    try:
        action_code = action_code.strip()
        # if action_code.startswith('do(action="Type"') or action_code.startswith(
        #     'do(action="Type_Name"'
        # ):
        #     text = action_code.split("text=", 1)[1][1:-2]
        #     print(f"Extracted text for typing: {text}")
        #     action = {"_metadata": "do", "action": "Type", "text": text}
        #     return action, None
        # elif action_code.startswith("do"):
        if action_code.startswith("do"):
            # Use AST parsing instead of eval for safety
            try:
                # Escape special characters (newlines, tabs, etc.) for valid Python syntax
                action_code = action_code.replace('\n', '\\n')
                action_code = action_code.replace('\r', '\\r')
                action_code = action_code.replace('\t', '\\t')

                tree = ast.parse(action_code, mode="eval")
                if not isinstance(tree.body, ast.Call):
                    raise ValueError("Expected a function call")

                call = tree.body
                # Extract keyword arguments safely
                action = {"_metadata": "do"}
                for keyword in call.keywords:
                    key = keyword.arg
                    value = ast.literal_eval(keyword.value)
                    action[key] = value
                
                # Convert element ID to actual coordinates if needed
                if "element" in action and isinstance(action["element"], str):
                    element_id = action["element"]
                    # Find the element with matching ID in elements_info
                    for element in elements_info:
                        if element["id"] == element_id:
                            # Calculate center point of bounding box
                            bbox = element["bbox"]
                            # print(f"Found element bbox: {bbox} for id: {element_id}")
                            center_x = (bbox[0][0] + bbox[1][0]) // 2
                            center_y = (bbox[0][1] + bbox[1][1]) // 2
                            # Convert to relative coordinates (0-1000 scale)
                            action["element"] = [center_x, center_y]
                            if not is_portal:
                                return action, element["content"]
                            else:
                                return action, f"{element['resourceId']}/{element['className']}/{element['content']}"
                    return action, None
                    
                # print(f"Parsed do action....: {action}")
                return action, None
            except (SyntaxError, ValueError) as e:
                raise ValueError(f"Failed to parse do() action: {e}")

        # elif response.startswith("finish"):
        #     action = {
        #         "_metadata": "finish",
        #         "message": response.replace("finish(message=", "")[1:-2],
        #     }
        else:
            raise ValueError(f"Failed to parse action: {action_code}")
    except Exception as e:
        raise ValueError(f"Failed to parse action: {e}")


def do(**kwargs) -> dict[str, Any]:
    """Helper function for creating 'do' actions."""
    kwargs["_metadata"] = "do"
    return kwargs


def finish(**kwargs) -> dict[str, Any]:
    """Helper function for creating 'finish' actions."""
    kwargs["_metadata"] = "do"
    kwargs["action"] = "Finish"
    return kwargs
