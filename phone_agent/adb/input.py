"""Input utilities for Android device text input."""

import asyncio
import base64
import subprocess
from typing import Optional


async def type_text(text: str, device_id: str | None = None) -> None:
    """
    Type text into the currently focused input field using ADB Keyboard.

    Args:
        text: The text to type.
        device_id: Optional ADB device ID for multi-device setups.

    Note:
        Requires ADB Keyboard to be installed on the device.
        See: https://github.com/nicnocquee/AdbKeyboard
    """
    adb_prefix = await _get_adb_prefix(device_id)
    encoded_text = base64.b64encode(text.encode("utf-8")).decode("utf-8")

    process = await asyncio.create_subprocess_exec(
        *adb_prefix,
        "shell",
        "am",
        "broadcast",
        "-a",
        "ADB_INPUT_B64",
        "--es",
        "msg",
        encoded_text,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await process.wait()


async def clear_text(device_id: str | None = None) -> None:
    """
    Clear text in the currently focused input field.

    Args:
        device_id: Optional ADB device ID for multi-device setups.
    """
    adb_prefix = await _get_adb_prefix(device_id)

    process = await asyncio.create_subprocess_exec(
        *adb_prefix,
        "shell",
        "am",
        "broadcast",
        "-a",
        "ADB_CLEAR_TEXT",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await process.wait()


async def detect_and_set_adb_keyboard(device_id: str | None = None) -> str:
    """
    Detect current keyboard and switch to ADB Keyboard if needed.

    Args:
        device_id: Optional ADB device ID for multi-device setups.

    Returns:
        The original keyboard IME identifier for later restoration.
    """
    adb_prefix = await _get_adb_prefix(device_id)

    # Get current IME
    process = await asyncio.create_subprocess_exec(
        *adb_prefix,
        "shell",
        "settings",
        "get",
        "secure",
        "default_input_method",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    current_ime = (stdout.decode() + stderr.decode()).strip()

    # Switch to ADB Keyboard if not already set
    if "com.android.adbkeyboard/.AdbIME" not in current_ime:
        process = await asyncio.create_subprocess_exec(
            *adb_prefix,
            "shell",
            "ime",
            "set",
            "com.android.adbkeyboard/.AdbIME",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await process.wait()

    # Warm up the keyboard
    await type_text("", device_id)

    return current_ime


async def restore_keyboard(ime: str, device_id: str | None = None) -> None:
    """
    Restore the original keyboard IME.

    Args:
        ime: The IME identifier to restore.
        device_id: Optional ADB device ID for multi-device setups.
    """
    adb_prefix = await _get_adb_prefix(device_id)

    process = await asyncio.create_subprocess_exec(
        *adb_prefix,
        "shell",
        "ime",
        "set",
        ime,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await process.wait()


async def _get_adb_prefix(device_id: str | None) -> list:
    """Get ADB command prefix with optional device specifier."""
    if device_id:
        return ["adb", "-s", device_id]
    return ["adb"]
