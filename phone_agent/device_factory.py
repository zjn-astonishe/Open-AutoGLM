"""Device factory for selecting ADB or HDC based on device type."""

from enum import Enum
from typing import Any


class DeviceType(Enum):
    """Type of device connection tool."""

    ADB = "adb"
    HDC = "hdc"
    IOS = "ios"


class DeviceFactory:
    """
    Factory class for getting device-specific implementations.

    This allows the system to work with both Android (ADB) and HarmonyOS (HDC) devices.
    """

    def __init__(self, device_type: DeviceType = DeviceType.ADB):
        """
        Initialize the device factory.

        Args:
            device_type: The type of device to use (ADB or HDC).
        """
        self.device_type = device_type
        self._module = None

    @property
    def module(self):
        """Get the appropriate device module (adb or hdc)."""
        if self._module is None:
            if self.device_type == DeviceType.ADB:
                from phone_agent import adb

                self._module = adb
            elif self.device_type == DeviceType.HDC:
                from phone_agent import hdc

                self._module = hdc
            else:
                raise ValueError(f"Unknown device type: {self.device_type}")
        return self._module

    async def get_screenshot(self, prefix: str | None = None, save_dir: str | None = None, device_id: str | None = None, timeout: int = 10):
        """Get screenshot from device."""
        return await self.module.get_screenshot(prefix, save_dir, device_id, timeout)

    async def get_current_app(self, device_id: str | None = None) -> str:
        """Get current app name."""
        return await self.module.get_current_app(device_id)

    async def tap(
        self, x: int, y: int, device_id: str | None = None, delay: float | None = None
    ):
        """Tap at coordinates."""
        return await self.module.tap(x, y, device_id, delay)

    async def double_tap(
        self, x: int, y: int, device_id: str | None = None, delay: float | None = None
    ):
        """Double tap at coordinates."""
        return await self.module.double_tap(x, y, device_id, delay)

    async def long_press(
        self,
        x: int,
        y: int,
        duration_ms: int = 3000,
        device_id: str | None = None,
        delay: float | None = None,
    ):
        """Long press at coordinates."""
        return await self.module.long_press(x, y, duration_ms, device_id, delay)

    async def swipe(
        self,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        duration_ms: int | None = None,
        device_id: str | None = None,
        delay: float | None = None,
    ):
        """Swipe from start to end."""
        return await self.module.swipe(
            start_x, start_y, end_x, end_y, duration_ms, device_id, delay
        )

    async def back(self, device_id: str | None = None, delay: float | None = None):
        """Press back button."""
        return await self.module.back(device_id, delay)

    async def home(self, device_id: str | None = None, delay: float | None = None):
        """Press home button."""
        return await self.module.home(device_id, delay)

    async def launch_app(
        self, app_name: str, device_id: str | None = None, delay: float | None = None
    ) -> bool:
        """Launch an app."""
        return await self.module.launch_app(app_name, device_id, delay)

    async def type_text(self, text: str, device_id: str | None = None):
        """Type text."""
        return await self.module.type_text(text, device_id)

    async def clear_text(self, device_id: str | None = None):
        """Clear text."""
        return await self.module.clear_text(device_id)

    async def detect_and_set_adb_keyboard(self, device_id: str | None = None) -> str:
        """Detect and set keyboard."""
        return await self.module.detect_and_set_adb_keyboard(device_id)

    async def restore_keyboard(self, ime: str, device_id: str | None = None):
        """Restore keyboard."""
        return await self.module.restore_keyboard(ime, device_id)

    async def list_devices(self):
        """List connected devices."""
        return await self.module.list_devices()

    async def shell(self, command: str, device_id: str | None = None) -> str:
        """Execute shell command on device."""
        import asyncio
        adb_prefix = ["adb"]
        if device_id:
            adb_prefix = ["adb", "-s", device_id]
        
        process = await asyncio.create_subprocess_exec(
            *adb_prefix, "shell", command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        return stdout.decode("utf-8").strip()

    async def list_packages(self, device_id: str | None = None) -> list[str]:
        """List installed packages on device."""
        output = await self.shell("pm list packages", device_id)
        packages = []
        for line in output.split("\n"):
            if line.startswith("package:"):
                packages.append(line.replace("package:", "").strip())
        return packages

    def get_connection_class(self):
        """Get the connection class (ADBConnection or HDCConnection)."""
        if self.device_type == DeviceType.ADB:
            from phone_agent.adb import ADBConnection

            return ADBConnection
        elif self.device_type == DeviceType.HDC:
            from phone_agent.hdc import HDCConnection

            return HDCConnection
        else:
            raise ValueError(f"Unknown device type: {self.device_type}")

    

# Global device factory instance
_device_factory: DeviceFactory | None = None


async def set_device_type(device_type: DeviceType):
    """
    Set the global device type.

    Args:
        device_type: The device type to use (ADB or HDC).
    """
    global _device_factory
    _device_factory = DeviceFactory(device_type)


async def get_device_factory() -> DeviceFactory:
    """
    Get the global device factory instance.

    Returns:
        The device factory instance.
    """
    global _device_factory
    if _device_factory is None:
        _device_factory = DeviceFactory(DeviceType.ADB)  # Default to ADB
    return _device_factory
