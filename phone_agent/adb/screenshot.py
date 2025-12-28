"""Screenshot utilities for capturing Android device screen."""

import base64
import os
import shutil
import subprocess
import tempfile
import uuid
from PIL import Image
from io import BytesIO
from typing import List
from dataclasses import dataclass
from utils.ui_xml import get_emulator_ui_xml
from utils.ui_filter import AndroidElement, ui_filter
# from utils.draw_bbox import draw_bbox_multi
from utils.crop_ui_elements import crop_ui_elements



@dataclass
class Screenshot:
    """Represents a captured screenshot."""

    elements: list[AndroidElement]
    base64_data: str
    crop_base64_data: List[str]
    width: int
    height: int
    is_sensitive: bool = False
    path: str | None = None


def get_screenshot(prefix: str | None = None, save_dir: str | None = None, device_id: str | None = None, timeout: int = 10) -> Screenshot:
    """
    Capture a screenshot from the connected Android device.

    Args:
        device_id: Optional ADB device ID for multi-device setups.
        timeout: Timeout in seconds for screenshot operations.

    Returns:
        Screenshot object containing base64 data and dimensions.

    Note:
        If the screenshot fails (e.g., on sensitive screens like payment pages),
        a black fallback image is returned with is_sensitive=True.
    """
    if not prefix and not save_dir:
        temp_id = str(uuid.uuid4())
        temp_path = os.path.join(tempfile.gettempdir(), f"screenshot_{temp_id}.png")
        # temp_bbox_path = os.path.join(os.path.dirname(temp_path), f"screenshot_bbox_{temp_id}.png")
        # temp_crop_dir = os.path.join(tempfile.gettempdir(), f"screenshot_crops_{temp_id}")
    elif not prefix or not save_dir:
        raise ValueError("Both prefix and save_dir must be provided together.")
    else:
        os.makedirs(save_dir, exist_ok=True)
        temp_path = os.path.join(save_dir, f"{prefix}_screenshot.png")
        # temp_bbox_path = os.path.join(os.path.dirname(temp_path), f"{prefix}_screenshot_bbox.png")
        # temp_crop_dir = os.path.join(save_dir, f"{prefix}_crops")
    
    adb_prefix = _get_adb_prefix(device_id)

    try:
        # Execute screenshot command
        result = subprocess.run(
            adb_prefix + ["shell", "screencap", "-p", "/sdcard/tmp.png"],
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        # Check for screenshot failure (sensitive screen)
        output = result.stdout + result.stderr
        if "Status: -1" in output or "Failed" in output:
            return _create_fallback_screenshot(is_sensitive=True)

        # Pull screenshot to local temp path
        subprocess.run(
            adb_prefix + ["pull", "/sdcard/tmp.png", temp_path],
            capture_output=True,
            text=True,
            timeout=5,
        )

        if not os.path.exists(temp_path):
            return _create_fallback_screenshot(is_sensitive=False)

        # Get XML corresponding to the screenshot
        xml_file = get_emulator_ui_xml("tmp", os.path.dirname(temp_path), emulator_device=device_id)
        elements = ui_filter(xml_file)
        # draw_bbox_multi(img_path=temp_path, output_path=temp_bbox_path, elem_list=elements)
        # crop_list = crop_ui_elements(
        #     img_path=temp_path, 
        #     output_dir=temp_crop_dir, 
        #     elem_list=elements
        # )

        # Read and encode image
        img = Image.open(temp_path)
        width, height = img.size

        buffered = BytesIO()
        img.save(buffered, format="PNG")
        base64_data = base64.b64encode(buffered.getvalue()).decode("utf-8")

        crop_base64_data = []
        # for crop in crop_list:
            # print(f"crop: {crop}")
            # crop_img = Image.open(crop)
            # buffered_crop = BytesIO()
            # crop_img.save(buffered_crop, format="PNG")
            # crop_base64 = base64.b64encode(buffered_crop.getvalue()).decode("utf-8")
            # crop_base64_data.append(crop_base64)

        # Cleanup
        if not (prefix and save_dir):
            os.remove(temp_path)
            # os.remove(temp_bbox_path)
            # shutil.rmtree(temp_crop_dir)
            os.remove(xml_file)
            return Screenshot(
                base64_data=base64_data, 
                crop_base64_data=crop_base64_data,
                width=width, 
                height=height, 
                elements=elements,
                is_sensitive=False
            )
        else:
            return Screenshot(
                base64_data=base64_data,
                crop_base64_data=crop_base64_data,
                width=width,
                height=height,
                elements=elements,
                is_sensitive=False,
                path=temp_path
            )

    except Exception as e:
        print(f"Screenshot error: {e}")
        return _create_fallback_screenshot(is_sensitive=False)


def _get_adb_prefix(device_id: str | None) -> list:
    """Get ADB command prefix with optional device specifier."""
    if device_id:
        return ["adb", "-s", device_id]
    return ["adb"]


def _create_fallback_screenshot(is_sensitive: bool) -> Screenshot:
    """Create a black fallback image when screenshot fails."""
    default_width, default_height = 1080, 2400

    black_img = Image.new("RGB", (default_width, default_height), color="black")
    buffered = BytesIO()
    black_img.save(buffered, format="PNG")
    base64_data = base64.b64encode(buffered.getvalue()).decode("utf-8")

    return Screenshot(
        base64_data=base64_data,
        crop_base64_data=[],
        width=default_width,
        height=default_height,
        elements=[],
        is_sensitive=is_sensitive,
    )
