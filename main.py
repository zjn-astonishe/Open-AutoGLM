#!/usr/bin/env python3
"""
Phone Agent CLI - AI-powered phone automation.

Usage:
    python main.py [OPTIONS]

Environment Variables:
    PHONE_AGENT_BASE_URL: Model API base URL (default: http://localhost:8001/v1)
    PHONE_AGENT_MODEL: Model name (default: autoglm-phone-9b)
    PHONE_AGENT_API_KEY: API key for model authentication (default: EMPTY)
    PHONE_AGENT_MAX_STEPS: Maximum steps per task (default: 100)
    PHONE_AGENT_DEVICE_ID: ADB device ID for multi-device setups
"""

import argparse
import asyncio
import json
import os
import time
import shutil
import subprocess
import sys
from urllib.parse import urlparse

from openai import OpenAI

from phone_agent import PhoneAgent
from phone_agent.agent import AgentConfig
from phone_agent.agent_ios import IOSAgentConfig, IOSPhoneAgent
from phone_agent.config.apps import list_supported_apps
from phone_agent.config.apps_harmonyos import list_supported_apps as list_harmonyos_apps
from phone_agent.config.apps_ios import list_supported_apps as list_ios_apps
from phone_agent.device_factory import DeviceType, get_device_factory, set_device_type, DeviceFactory
from phone_agent.model import ModelConfig
from phone_agent.xctest import XCTestConnection
from phone_agent.xctest import list_devices as list_ios_devices
from utils.config import load_config
from utils.util import print_with_color
from phone_agent.portal import (
    PORTAL_PACKAGE_NAME,
    check_portal_accessibility,
    toggle_overlay,
    disable_keyboard,
    download_portal_apk,
    download_versioned_portal_apk,
    enable_portal_accessibility,
    get_compatible_portal_version,
    ping_portal,
    ping_portal_content,
    ping_portal_tcp,
)

async def _setup_portal(path: str | None, device_factory: DeviceFactory, debug: bool, latest: bool = False, specific_version: str | None = None):
    """Internal async function to install and enable the DroidRun Portal on a device."""
    try:
        # Get device 
        from async_adbutils import adb
        devices = await adb.list()
        if not devices:
            print_with_color("No devices found!", "red")
            return
        
        device = devices[0].serial
        print_with_color(f"Using device: {devices}", "blue")

        device_obj = await adb.device(device)
        if not device_obj:
            print_with_color("Error: Could not connect to device!", "red")
            return

        if path:
            print_with_color(f"Using provided APK:[/] {path}", "blue")
            from contextlib import nullcontext
            apk_context = nullcontext(path)
        elif specific_version:
            __version__ = specific_version.lstrip("v")
            __version__ = f"v{__version__}"
            download_base = "https://github.com/droidrun/droidrun-portal/releases/download"
            apk_context = download_versioned_portal_apk(__version__, download_base, debug)
        elif latest:
            print_with_color("Downloading latest Portal APK...", "blue")
            apk_context = download_portal_apk(debug)
        else:
            from importlib.metadata import version, PackageNotFoundError
            try:
                # Try to get version from installed package
                __version__ = version("phone-agent")
            except PackageNotFoundError:
                # If package not installed via pip, use a default version
                __version__ = "0.1.0"
                print_with_color(f"Package not installed, using default version: {__version__}", "yellow")
            
            portal_version, download_base, mapping_fetched = get_compatible_portal_version(__version__, debug)

            if portal_version:
                apk_context = download_versioned_portal_apk(portal_version, download_base, debug)
            else:
                if not mapping_fetched:
                    print_with_color("Could not fetch version mapping, falling back to latest...", "yellow")
                apk_context = download_portal_apk(debug)

        with apk_context as apk_path:
            if not os.path.exists(apk_path):
                print_with_color(f"Error: APK file not found at {apk_path}", "red")
                return

            print_with_color(f"Step 1/2: Installing APK: {apk_path}", "blue")
            try:
                await device_obj.install(
                    apk_path, uninstall=True, flags=["-g"], silent=not debug
                )
            except Exception as e:
                print_with_color(f"Installation failed: {e}", "red")
                return

            print_with_color("Installation successful!", "green")

            print_with_color("Step 2/2: Enabling accessibility service", "blue")

            try:
                await enable_portal_accessibility(device_factory)

                print_with_color("Accessibility service enabled successfully!", "green")
                print_with_color(
                    "\nSetup complete! The DroidRun Portal is now installed and ready to use.", 
                    "green"
                )

            except Exception as e:
                print_with_color(
                    f"Could not automatically enable accessibility service: {e}",
                    "yellow"
                )
                print_with_color(
                    "Opening accessibility settings for manual configuration...",
                    "yellow"
                )

                await device_factory.shell(
                    "am start -a android.settings.ACCESSIBILITY_SETTINGS"
                )

                print_with_color(
                    "\nPlease complete the following steps on your device:",
                    "yellow"
                )
                print_with_color(
                    f"1. Find {PORTAL_PACKAGE_NAME} in the accessibility services list"
                )
                print_with_color("2. Tap on the service name")
                print_with_color(
                    "3. Toggle the switch to ON to enable the service"
                )
                print_with_color("4. Accept any permission dialogs that appear")

                print_with_color(
                    "\nAPK installation complete![/] Please manually enable the accessibility service using the steps above.",
                    "green"
                )
        
        # Return to system home after setup
        print_with_color("\nReturning to system home...", "blue")
        await device_factory.shell("input keyevent KEYCODE_HOME")
        await asyncio.sleep(1.0)
        print_with_color("✓ Returned to home screen", "green")

    except Exception as e:
        print_with_color(f"Error: {e}", "red")

        if debug:
            import traceback

            traceback.print_exc()

async def get_portal_version(device_factory) -> str | None:
    try:
        version_output = await device_factory.shell(
            "content query --uri content://com.droidrun.portal/version"
        )

        if "result=" in version_output:
            json_str = version_output.split("result=", 1)[1].strip()
            version_data = json.loads(json_str)

            if version_data.get("status") == "success":
                # Check for 'result' first (new portal), then 'data' (legacy)
                return version_data.get("result") or version_data.get("data")
        return None
    except Exception:
        return None

async def check_system_requirements(
    device_type: DeviceType = DeviceType.ADB, wda_url: str = "http://localhost:8100"
) -> bool:
    """
    Check system requirements before running the agent.

    Checks:
    1. ADB/HDC/iOS tools installed
    2. At least one device connected
    3. ADB Keyboard installed on the device (for ADB only)
    4. WebDriverAgent running (for iOS only)

    Args:
        device_type: Type of device tool (ADB, HDC, or IOS).
        wda_url: WebDriverAgent URL (for iOS only).

    Returns:
        True if all checks pass, False otherwise.
    """
    print("🔍 Checking system requirements...")
    print("-" * 50)

    all_passed = True

    # Determine tool name and command
    if device_type == DeviceType.IOS:
        tool_name = "libimobiledevice"
        tool_cmd = "idevice_id"
    else:
        tool_name = "ADB" if device_type == DeviceType.ADB else "HDC"
        tool_cmd = "adb" if device_type == DeviceType.ADB else "hdc"

    # Check 1: Tool installed
    print(f"1. Checking {tool_name} installation...", end=" ")
    if shutil.which(tool_cmd) is None:
        print("❌ FAILED")
        print(f"   Error: {tool_name} is not installed or not in PATH.")
        print(f"   Solution: Install {tool_name}:")
        if device_type == DeviceType.ADB:
            print("     - macOS: brew install android-platform-tools")
            print("     - Linux: sudo apt install android-tools-adb")
            print(
                "     - Windows: Download from https://developer.android.com/studio/releases/platform-tools"
            )
        elif device_type == DeviceType.HDC:
            print(
                "     - Download from HarmonyOS SDK or https://gitee.com/openharmony/docs"
            )
            print("     - Add to PATH environment variable")
        else:  # IOS
            print("     - macOS: brew install libimobiledevice")
            print("     - Linux: sudo apt-get install libimobiledevice-utils")
        all_passed = False
    else:
        # Double check by running version command
        try:
            if device_type == DeviceType.ADB:
                version_cmd = [tool_cmd, "version"]
            elif device_type == DeviceType.HDC:
                version_cmd = [tool_cmd, "-v"]
            else:  # IOS
                version_cmd = [tool_cmd, "-ln"]

            result = subprocess.run(
                version_cmd, capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                version_line = result.stdout.strip().split("\n")[0]
                print(f"✅ OK ({version_line if version_line else 'installed'})")
            else:
                print("❌ FAILED")
                print(f"   Error: {tool_name} command failed to run.")
                all_passed = False
        except FileNotFoundError:
            print("❌ FAILED")
            print(f"   Error: {tool_name} command not found.")
            all_passed = False
        except subprocess.TimeoutExpired:
            print("❌ FAILED")
            print(f"   Error: {tool_name} command timed out.")
            all_passed = False

    # If ADB is not installed, skip remaining checks
    if not all_passed:
        print("-" * 50)
        print("❌ System check failed. Please fix the issues above.")
        return False

    # Check 2: Device connected
    print("2. Checking connected devices...", end=" ")
    try:
        if device_type == DeviceType.ADB:
            result = subprocess.run(
                ["adb", "devices"], capture_output=True, text=True, timeout=10
            )
            lines = result.stdout.strip().split("\n")
            # Filter out header and empty lines, look for 'device' status
            devices = [
                line for line in lines[1:] if line.strip() and "\tdevice" in line
            ]
        elif device_type == DeviceType.HDC:
            result = subprocess.run(
                ["hdc", "list", "targets"], capture_output=True, text=True, timeout=10
            )
            lines = result.stdout.strip().split("\n")
            devices = [line for line in lines if line.strip()]
        else:  # IOS
            ios_devices = list_ios_devices()
            devices = [d.device_id for d in ios_devices]

        if not devices:
            print("❌ FAILED")
            print("   Error: No devices connected.")
            print("   Solution:")
            if device_type == DeviceType.ADB:
                print("     1. Enable USB debugging on your Android device")
                print("     2. Connect via USB and authorize the connection")
                print(
                    "     3. Or connect remotely: python main.py --connect <ip>:<port>"
                )
            elif device_type == DeviceType.HDC:
                print("     1. Enable USB debugging on your HarmonyOS device")
                print("     2. Connect via USB and authorize the connection")
                print(
                    "     3. Or connect remotely: python main.py --device-type hdc --connect <ip>:<port>"
                )
            else:  # IOS
                print("     1. Connect your iOS device via USB")
                print("     2. Unlock device and tap 'Trust This Computer'")
                print("     3. Verify: idevice_id -l")
                print("     4. Or connect via WiFi using device IP")
            all_passed = False
        else:
            if device_type == DeviceType.ADB:
                device_ids = [d.split("\t")[0] for d in devices]
            elif device_type == DeviceType.HDC:
                device_ids = [d.strip() for d in devices]
            else:  # IOS
                device_ids = devices
            print(
                f"✅ OK ({len(devices)} device(s): {', '.join(device_ids[:2])}{'...' if len(device_ids) > 2 else ''})"
            )
    except subprocess.TimeoutExpired:
        print("❌ FAILED")
        print(f"   Error: {tool_name} command timed out.")
        all_passed = False
    except Exception as e:
        print("❌ FAILED")
        print(f"   Error: {e}")
        all_passed = False

    # If no device connected, skip ADB Keyboard check
    if not all_passed:
        print("-" * 50)
        print("❌ System check failed. Please fix the issues above.")
        return False

    # Check 3: ADB Keyboard installed (only for ADB) or WebDriverAgent (for iOS)
    if device_type == DeviceType.ADB:
        # print("3. Checking ADB Keyboard...", end=" ")
        # try:
        #     result = subprocess.run(
        #         ["adb", "shell", "ime", "list", "-s"],
        #         capture_output=True,
        #         text=True,
        #         timeout=10,
        #     )
        #     ime_list = result.stdout.strip()

        #     if "com.android.adbkeyboard/.AdbIME" in ime_list:
        #         print("✅ OK")
        #     else:
        #         print("❌ FAILED")
        #         print("   Error: ADB Keyboard is not installed on the device.")
        #         print("   Solution:")
        #         print("     1. Download ADB Keyboard APK from:")
        #         print(
        #             "        https://github.com/senzhk/ADBKeyBoard/blob/master/ADBKeyboard.apk"
        #         )
        #         print("     2. Install it on your device: adb install ADBKeyboard.apk")
        #         print(
        #             "     3. Enable it in Settings > System > Languages & Input > Virtual Keyboard"
        #         )
        #         all_passed = False
        # except subprocess.TimeoutExpired:
        #     print("❌ FAILED")
        #     print("   Error: ADB command timed out.")
        #     all_passed = False
        # except Exception as e:
        #     print("❌ FAILED")
        #     print(f"   Error: {e}")
        #     all_passed = False
        print("3. Checking Portal...", end=" ")
        device_factory = await get_device_factory()
        portal_version = await get_portal_version(device_factory)
        if not portal_version or portal_version < "0.4.1":
            print(f"⚠️  Portal version {portal_version} is outdated")
            print(f"Running setup...")
            await _setup_portal(
                path=None, 
                device_factory=device_factory,
                debug=False
            )
            
        else:
            print("✅ OK")
    elif device_type == DeviceType.HDC:
        # For HDC, skip keyboard check as it uses different input method
        print("3. Skipping keyboard check for HarmonyOS...", end=" ")
        print("✅ OK (using native input)")
    else:  # IOS
        # Check WebDriverAgent
        print(f"3. Checking WebDriverAgent ({wda_url})...", end=" ")
        try:
            conn = XCTestConnection(wda_url=wda_url)

            if conn.is_wda_ready():
                print("✅ OK")
                # Get WDA status for additional info
                status = conn.get_wda_status()
                if status:
                    session_id = status.get("sessionId", "N/A")
                    print(f"   Session ID: {session_id}")
            else:
                print("❌ FAILED")
                print("   Error: WebDriverAgent is not running or not accessible.")
                print("   Solution:")
                print("     1. Run WebDriverAgent on your iOS device via Xcode")
                print("     2. For USB: Set up port forwarding: iproxy 8100 8100")
                print(
                    "     3. For WiFi: Use device IP, e.g., --wda-url http://192.168.1.100:8100"
                )
                print("     4. Verify in browser: open http://localhost:8100/status")
                all_passed = False
        except Exception as e:
            print("❌ FAILED")
            print(f"   Error: {e}")
            all_passed = False

    print("-" * 50)

    if all_passed:
        print("✅ All system checks passed!\n")
    else:
        print("❌ System check failed. Please fix the issues above.")

    return all_passed


def check_model_api(base_url: str, model_name: str, api_key: str = "EMPTY") -> bool:
    """
    Check if the model API is accessible and the specified model exists.

    Checks:
    1. Network connectivity to the API endpoint
    2. Model exists in the available models list

    Args:
        base_url: The API base URL
        model_name: The model name to check
        api_key: The API key for authentication

    Returns:
        True if all checks pass, False otherwise.
    """
    print("🔍 Checking model API...")
    print("-" * 50)

    all_passed = True

    # Check 1: Network connectivity using chat API
    print(f"1. Checking API connectivity ({base_url})...", end=" ")
    try:
        # Create OpenAI client
        client = OpenAI(base_url=base_url, api_key=api_key, timeout=30.0)

        # Use chat completion to test connectivity (more universally supported than /models)
        response = client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": "Hi"}],
            max_tokens=5,
            temperature=0.0,
            stream=False,
        )

        # Check if we got a valid response
        if response.choices and len(response.choices) > 0:
            print("✅ OK")
        else:
            print("❌ FAILED")
            print("   Error: Received empty response from API")
            all_passed = False

    except Exception as e:
        print("❌ FAILED")
        error_msg = str(e)

        # Provide more specific error messages
        if "Connection refused" in error_msg or "Connection error" in error_msg:
            print(f"   Error: Cannot connect to {base_url}")
            print("   Solution:")
            print("     1. Check if the model server is running")
            print("     2. Verify the base URL is correct")
            print(f"     3. Try: curl {base_url}/chat/completions")
        elif "timed out" in error_msg.lower() or "timeout" in error_msg.lower():
            print(f"   Error: Connection to {base_url} timed out")
            print("   Solution:")
            print("     1. Check your network connection")
            print("     2. Verify the server is responding")
        elif (
            "Name or service not known" in error_msg
            or "nodename nor servname" in error_msg
        ):
            print(f"   Error: Cannot resolve hostname")
            print("   Solution:")
            print("     1. Check the URL is correct")
            print("     2. Verify DNS settings")
        else:
            print(f"   Error: {error_msg}")

        all_passed = False

    print("-" * 50)

    if all_passed:
        print("✅ Model API checks passed!\n")
    else:
        print("❌ Model API check failed. Please fix the issues above.")

    return all_passed


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Phone Agent - AI-powered phone automation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Run with default settings (Android)
    python main.py

    # Run with specific device
    python main.py --device-id emulator-5554

    # Connect to remote device
    python main.py --connect 192.168.1.100:5555

    # List connected devices
    python main.py --list-devices

    # Enable TCP/IP on USB device and get connection info
    python main.py --enable-tcpip

    # List supported apps
    python main.py --list-apps

    # iOS specific examples
    # Run with iOS device
    python main.py --device-type ios "Open Safari and search for iPhone tips"

    # Use WiFi connection for iOS
    python main.py --device-type ios --wda-url http://192.168.1.100:8100

    # List connected iOS devices
    python main.py --device-type ios --list-devices

    # Check WebDriverAgent status
    python main.py --device-type ios --wda-status

    # Pair with iOS device
    python main.py --device-type ios --pair
        """,
    )

    # Device options
    parser.add_argument(
        "--device-id",
        "-d",
        type=str,
        default=os.getenv("PHONE_AGENT_DEVICE_ID"),
        help="ADB device ID",
    )

    parser.add_argument(
        "--connect",
        "-c",
        type=str,
        metavar="ADDRESS",
        help="Connect to remote device (e.g., 192.168.1.100:5555)",
    )

    parser.add_argument(
        "--disconnect",
        type=str,
        nargs="?",
        const="all",
        metavar="ADDRESS",
        help="Disconnect from remote device (or 'all' to disconnect all)",
    )

    parser.add_argument(
        "--list-devices", action="store_true", help="List connected devices and exit"
    )

    parser.add_argument(
        "--enable-tcpip",
        type=int,
        nargs="?",
        const=5555,
        metavar="PORT",
        help="Enable TCP/IP debugging on USB device (default port: 5555)",
    )

    # iOS specific options
    parser.add_argument(
        "--wda-url",
        type=str,
        default=os.getenv("PHONE_AGENT_WDA_URL", "http://localhost:8100"),
        help="WebDriverAgent URL for iOS (default: http://localhost:8100)",
    )

    parser.add_argument(
        "--pair",
        action="store_true",
        help="Pair with iOS device (required for some operations)",
    )

    parser.add_argument(
        "--wda-status",
        action="store_true",
        help="Show WebDriverAgent status and exit (iOS only)",
    )

    # Other options
    # parser.add_argument(
    #     "--quiet", "-q", action="store_true", help="Suppress verbose output"
    # )

    parser.add_argument(
        "--list-apps", action="store_true", help="List supported apps and exit"
    )

    # Android World testing options
    parser.add_argument(
        "--android-world",
        action="store_true",
        help="Run Android World benchmark tests"
    )
    
    parser.add_argument(
        "--aw-task",
        type=str,
        help="Run specific Android World task (e.g., ContactsAddContact)"
    )
    
    parser.add_argument(
        "--aw-family",
        type=str,
        default="android_world",
        help="Android World task family (default: android_world)"
    )
    
    parser.add_argument(
        "--aw-tasks",
        type=str,
        nargs="+",
        help="List of specific Android World tasks to run"
    )
    
    parser.add_argument(
        "--aw-combinations",
        type=int,
        default=1,
        help="Number of parameter combinations per task (default: 1)"
    )
    
    parser.add_argument(
        "--aw-timeout",
        type=int,
        default=300,
        help="Timeout per task in seconds (default: 300)"
    )
    
    parser.add_argument(
        "--aw-list-tasks",
        action="store_true",
        help="List available Android World tasks and exit"
    )

    # Step recorder options
    parser.add_argument(
        "--record",
        action="store_true",
        help="Start step recorder to record user demonstrations"
    )
    
    parser.add_argument(
        "--record-app",
        type=str,
        help="App name for step recording (optional, will prompt if not provided)"
    )
    
    parser.add_argument(
        "--record-demo",
        type=str,
        help="Demo name for step recording (optional, will auto-generate if not provided)"
    )

    parser.add_argument(
        "--device-type",
        type=str,
        choices=["adb", "hdc", "ios"],
        default=os.getenv("PHONE_AGENT_DEVICE_TYPE", "adb"),
        help="Device type: adb for Android, hdc for HarmonyOS, ios for iPhone (default: adb)",
    )

    parser.add_argument(
        "task",
        nargs="?",
        type=str,
        help="Task to execute (interactive mode if not provided)",
    )

    return parser.parse_args()


def handle_ios_device_commands(args) -> bool:
    """
    Handle iOS device-related commands.

    Returns:
        True if a device command was handled (should exit), False otherwise.
    """
    conn = XCTestConnection(wda_url=args.wda_url)

    # Handle --list-devices
    if args.list_devices:
        devices = list_ios_devices()
        if not devices:
            print("No iOS devices connected.")
            print("\nTroubleshooting:")
            print("  1. Connect device via USB")
            print("  2. Unlock device and trust this computer")
            print("  3. Run: idevice_id -l")
        else:
            print("Connected iOS devices:")
            print("-" * 70)
            for device in devices:
                conn_type = device.connection_type.value
                model_info = f"{device.model}" if device.model else "Unknown"
                ios_info = f"iOS {device.ios_version}" if device.ios_version else ""
                name_info = device.device_name or "Unnamed"

                print(f"  ✓ {name_info}")
                print(f"    UUID: {device.device_id}")
                print(f"    Model: {model_info}")
                print(f"    OS: {ios_info}")
                print(f"    Connection: {conn_type}")
                print("-" * 70)
        return True

    # Handle --pair
    if args.pair:
        print("Pairing with iOS device...")
        success, message = conn.pair_device(args.device_id)
        print(f"{'✓' if success else '✗'} {message}")
        return True

    # Handle --wda-status
    if args.wda_status:
        print(f"Checking WebDriverAgent status at {args.wda_url}...")
        print("-" * 50)

        if conn.is_wda_ready():
            print("✓ WebDriverAgent is running")

            status = conn.get_wda_status()
            if status:
                print(f"\nStatus details:")
                value = status.get("value", {})
                print(f"  Session ID: {status.get('sessionId', 'N/A')}")
                print(f"  Build: {value.get('build', {}).get('time', 'N/A')}")

                current_app = value.get("currentApp", {})
                if current_app:
                    print(f"\nCurrent App:")
                    print(f"  Bundle ID: {current_app.get('bundleId', 'N/A')}")
                    print(f"  Process ID: {current_app.get('pid', 'N/A')}")
        else:
            print("✗ WebDriverAgent is not running")
            print("\nPlease start WebDriverAgent on your iOS device:")
            print("  1. Open WebDriverAgent.xcodeproj in Xcode")
            print("  2. Select your device")
            print("  3. Run WebDriverAgentRunner (Product > Test or Cmd+U)")
            print(f"  4. For USB: Run port forwarding: iproxy 8100 8100")

        return True

    return False


def handle_android_world_commands(args) -> bool:
    """
    Handle Android World testing commands.
    
    Returns:
        True if an Android World command was handled (should exit), False otherwise.
    """
    # Handle --aw-list-tasks
    if args.aw_list_tasks:
        try:
            from evaluator import AndroidWorldTaskLoader
            
            task_loader = AndroidWorldTaskLoader()
            families = task_loader.get_available_families()
            
            print("Available Android World task families:")
            print("-" * 50)
            for family in families:
                print(f"📁 {family}")
                tasks = task_loader.get_all_task_names(family)
                print(f"   Tasks: {len(tasks)}")
                if len(tasks) <= 10:
                    for task in sorted(tasks):
                        print(f"   - {task}")
                else:
                    for task in sorted(tasks)[:5]:
                        print(f"   - {task}")
                    print(f"   ... and {len(tasks) - 5} more")
                print()
            
            print(f"Total families: {len(families)}")
            total_tasks = sum(len(task_loader.get_all_task_names(f)) for f in families)
            print(f"Total tasks: {total_tasks}")
            
        except ImportError as e:
            print("❌ Android World integration not available.")
            print(f"Error: {e}")
            print("Please ensure android_world is properly installed.")
        except Exception as e:
            print(f"❌ Error listing Android World tasks: {e}")
        
        return True
    
    # Check if any Android World testing is requested
    if args.android_world or args.aw_task or args.aw_tasks:
        return False  # Continue to main function for actual testing
    
    return False


async def handle_device_commands(args) -> bool:
    """
    Handle device-related commands.

    Returns:
        True if a device command was handled (should exit), False otherwise.
    """
    device_type = (
        DeviceType.ADB
        if args.device_type == "adb"
        else (DeviceType.HDC if args.device_type == "hdc" else DeviceType.IOS)
    )
    
    # Handle --list-apps (no system check needed)
    if args.list_apps:
        if device_type == DeviceType.HDC:
            print("Supported HarmonyOS apps:")
            apps = list_harmonyos_apps()
        elif device_type == DeviceType.IOS:
            print("Supported iOS apps:")
            print("\nNote: For iOS apps, Bundle IDs are configured in:")
            print("  phone_agent/config/apps_ios.py")
            print("\nCurrently configured apps:")
            apps = list_ios_apps()
        else:
            print("Supported Android apps:")
            apps = list_supported_apps()

        for app in sorted(apps):
            print(f"  - {app}")

        if device_type == DeviceType.IOS:
            print(
                "\nTo add iOS apps, find the Bundle ID and add to APP_PACKAGES_IOS dictionary."
            )
        return True

    # Handle iOS-specific commands
    if device_type == DeviceType.IOS:
        return handle_ios_device_commands(args)

    device_factory = await get_device_factory()
    ConnectionClass = device_factory.get_connection_class()
    conn = ConnectionClass()

    # Handle --list-devices
    if args.list_devices:
        devices = await device_factory.list_devices()
        if not devices:
            print("No devices connected.")
        else:
            print("Connected devices:")
            print("-" * 60)
            for device in devices:
                status_icon = "✓" if device.status == "device" else "✗"
                conn_type = device.connection_type.value
                model_info = f" ({device.model})" if device.model else ""
                print(
                    f"  {status_icon} {device.device_id:<30} [{conn_type}]{model_info}"
                )
        return True

    # Handle --connect
    if args.connect:
        print(f"Connecting to {args.connect}...")
        success, message = conn.connect(args.connect)
        print(f"{'✓' if success else '✗'} {message}")
        if success:
            # Set as default device
            args.device_id = args.connect
        return not success  # Continue if connection succeeded

    # Handle --disconnect
    if args.disconnect:
        if args.disconnect == "all":
            print("Disconnecting all remote devices...")
            success, message = conn.disconnect()
        else:
            print(f"Disconnecting from {args.disconnect}...")
            success, message = conn.disconnect(args.disconnect)
        print(f"{'✓' if success else '✗'} {message}")
        return True

    # Handle --enable-tcpip
    if args.enable_tcpip:
        port = args.enable_tcpip
        print(f"Enabling TCP/IP debugging on port {port}...")

        success, message = conn.enable_tcpip(port, args.device_id)
        print(f"{'✓' if success else '✗'} {message}")

        if success:
            # Try to get device IP
            ip = conn.get_device_ip(args.device_id)
            if ip:
                print(f"\nYou can now connect remotely using:")
                print(f"  python main.py --connect {ip}:{port}")
                print(f"\nOr via ADB directly:")
                print(f"  adb connect {ip}:{port}")
            else:
                print("\nCould not determine device IP. Check device WiFi settings.")
        return True

    return False


async def main():
    """Main entry point."""
    args = parse_args()
    configs = load_config()

    # Set device type globally based on args
    if args.device_type == "adb":
        device_type = DeviceType.ADB
    elif args.device_type == "hdc":
        device_type = DeviceType.HDC
    else:  # ios
        device_type = DeviceType.IOS

    # Set device type globally for non-iOS devices
    if device_type != DeviceType.IOS:
        await set_device_type(device_type)

    # Enable HDC verbose mode if using HDC
    if device_type == DeviceType.HDC:
        from phone_agent.hdc import set_hdc_verbose

        set_hdc_verbose(True)

    # Handle Android World commands first
    if handle_android_world_commands(args):
        return

    # Handle device commands (these may need partial system checks)
    if await handle_device_commands(args):
        return

    # Handle step recorder
    if args.record:
        from learn.step_recorder import run_step_recorder
        
        print("🎬 Starting Step Recorder...")
        print("=" * 50)
        
        try:
            summary = run_step_recorder(
                app=args.record_app,
                demo_name=args.record_demo,
                root_dir="./"
            )
            
            print("\n" + "=" * 50)
            print("✅ Step Recording Complete!")
            print("=" * 50)
            
            if summary:
                print(f"📊 Recording Summary:")
                print(f"   App: {summary.get('app', 'N/A')}")
                print(f"   Demo: {summary.get('demo_name', 'N/A')}")
                print(f"   Steps recorded: {summary.get('steps', 0)}")
                print(f"   Task description: {summary.get('task_desc', 'N/A')}")
                if 'workflow_id' in summary:
                    print(f"   Workflow ID: {summary['workflow_id']}")
                if 'memory_dir' in summary:
                    print(f"   Memory saved to: {summary['memory_dir']}")
            
        except Exception as e:
            print(f"❌ Error during step recording: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
            
        return

    # Run system requirements check before proceeding
    if not await check_system_requirements(
        device_type,
        wda_url=args.wda_url
        if device_type == DeviceType.IOS
        else "http://localhost:8100",
    ):
        sys.exit(1)

    # Check model API connectivity and model availability
    if configs["MODEL"] == "OpenAI":
        base_url = configs["OPENAI_API_BASE"]
        model = configs["OPENAI_API_MODEL"]
        apikey = configs["OPENAI_API_KEY"]
    # TODO: Add support for Qwen
    # elif configs["MODEL"] == "Qwen":
    #     apikey = configs["DASHSCOPE_API_KEY"]
    #     model = configs["QWEN_MODEL"]
    else:
        print_with_color(f"ERROR: Unsupported model type {configs['MODEL']}!", "red")
        sys.exit(1)
    if not check_model_api(base_url, model, apikey):
        sys.exit(1)

    # Create configurations and agent based on device type
    model_config = ModelConfig(
        base_url=base_url,
        model_name=model,
        api_key=apikey,
        lang=configs["LANG"],
    )

    # dir
    # root_dir = configs["ROOT"]
    memory_dir = configs["MEMORY_DIR"]


    if device_type == DeviceType.IOS:
        # Create iOS agent
        agent_config = IOSAgentConfig(
            max_steps=configs["MAX_ROUNDS"],
            wda_url=args.wda_url,
            device_id=args.device_id,
            verbose=not configs["QUIET"],
            lang=configs["LANG"],
            memory_dir=memory_dir,
        )

        agent = IOSPhoneAgent(
            model_config=model_config,
            agent_config=agent_config,
        )
    else:
        # Create Android/HarmonyOS agent
        agent_config = AgentConfig(
            max_steps=configs["MAX_ROUNDS"],
            device_id=args.device_id,
            verbose=not configs["QUIET"],
            lang=configs["LANG"],
            memory_dir=memory_dir,
        )

        agent = PhoneAgent(
            model_config=model_config,
            agent_config=agent_config,
        )
    
    

    # Print header
    print("=" * 50)
    if device_type == DeviceType.IOS:
        print("Phone Agent iOS - AI-powered iOS automation")
    else:
        print("Phone Agent - AI-powered phone automation")
    print("=" * 50)
    print(f"Model: {model_config.model_name}")
    print(f"Base URL: {model_config.base_url}")
    print(f"Max Steps: {agent_config.max_steps}")
    print(f"Language: {agent_config.lang}")
    print(f"Device Type: {args.device_type.upper()}")

    # Show iOS-specific config
    if device_type == DeviceType.IOS:
        print(f"WDA URL: {args.wda_url}")

    # Show device info
    if device_type == DeviceType.IOS:
        devices = list_ios_devices()
        if agent_config.device_id:
            print(f"Device: {agent_config.device_id}")
        elif devices:
            device = devices[0]
            print(f"Device: {device.device_name or device.device_id[:16]}")
            if device.model and device.ios_version:
                print(f"        {device.model}, iOS {device.ios_version}")
    else:
        device_factory = await get_device_factory()
        devices = await device_factory.list_devices()
        if agent_config.device_id:
            print(f"Device: {agent_config.device_id}")
        elif devices:
            print(f"Device: {devices[0].device_id} (auto-detected)")

    print("=" * 50)

    # Check if Android World testing is requested
    if args.android_world or args.aw_task or args.aw_tasks:
        try:
            from evaluator import AndroidWorldTestRunner
            
            print("\n🤖 Starting Android World Testing...")
            print("=" * 50)
            
            # Create test runner with Open-AutoGLM agent
            # This will initialize Android World environment first
            test_runner = AndroidWorldTestRunner(
                agent=agent,
                timeout_per_task=args.aw_timeout,
                verbose=not configs["QUIET"]
            )
            
            # Re-check and setup Portal AFTER Android World environment initialization
            # This ensures Portal is properly configured after any Android World setup
            print("\n🔧 Verifying Portal after Android World initialization...")
            device_factory = await get_device_factory()
            
            portal_version = await get_portal_version(device_factory)
            if not portal_version or portal_version < "0.4.1":
                print(f"⚠️  Portal version {portal_version} needs setup")
                await _setup_portal(
                    path=None, 
                    device_factory=device_factory,
                    debug=False
                )
            else:
                # Verify Portal accessibility is still enabled
                if not await check_portal_accessibility(device_factory):
                    print("⚠️  Portal accessibility service was disabled, re-enabling...")
                    await enable_portal_accessibility(device_factory)
                print(f"✅ Portal {portal_version} is ready")
            
            start_time = time.time()
            
            if args.aw_task:
                # Run single task with multiple combinations if specified
                if args.aw_combinations > 1:
                    print(f"Running single task: {args.aw_task} with {args.aw_combinations} combinations")
                    result = test_runner.run_benchmark_suite(
                        family=args.aw_family,
                        task_names=[args.aw_task],
                        n_combinations=args.aw_combinations,
                        timeout_per_task=args.aw_timeout
                    )
                else:
                    print(f"Running single task: {args.aw_task}")
                    result = await test_runner.run_single_task(
                        task_name=args.aw_task,
                        family=args.aw_family,
                        timeout=args.aw_timeout
                    )
                
            elif args.aw_tasks:
                # Run specific task list
                print(f"Running {len(args.aw_tasks)} tasks: {', '.join(args.aw_tasks)}")
                result = await test_runner.run_task_list(
                    task_names=args.aw_tasks,
                    family=args.aw_family,
                    timeout_per_task=args.aw_timeout
                )
                
            else:
                # Run full benchmark suite
                print(f"Running full benchmark suite: {args.aw_family}")
                result = test_runner.run_benchmark_suite(
                    family=args.aw_family,
                    n_combinations=args.aw_combinations
                )
            
            end_time = time.time()
            
            print("\n" + "=" * 50)
            print("🎯 Android World Testing Complete!")
            print(f"⏱️  Total time: {end_time - start_time:.2f} seconds")
            print("=" * 50)
            
            # Print summary results
            if result and 'summary' in result:
                summary = result['summary']
                print(f"\n📊 Results Summary:")
                print(f"   Tasks completed: {summary.get('total_tasks', 0)}")
                print(f"   Tasks successful: {summary.get('successful_tasks', 0)}")
                print(f"   Success rate: {summary.get('success_rate', 0):.1%}")
                print(f"   Average time per task: {summary.get('average_time_per_task', 0):.1f}s")
                
                if 'output_dir' in result:
                    print(f"\n📁 Detailed results saved to: {result['output_dir']}")
            
        except ImportError as e:
            print("❌ Android World integration not available.")
            print(f"Error: {e}")
            print("Please ensure android_world is properly installed.")
            sys.exit(1)
        except Exception as e:
            print(f"❌ Error running Android World tests: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
            
        return
    
    # Run with provided task or enter interactive mode
    if args.task:
        print(f"\nTask: {args.task}\n")
        
        # start_time = time.time()
        result = await agent.run(args.task)
        # end_time = time.time()
        # print(f"\nTime taken: {end_time - start_time:.2f} seconds")
        # print(f"\nResult: {result}")
    else:
        # Interactive mode
        print("\nEntering interactive mode. Type 'quit' to exit.\n")

        while True:
            try:
                task = input("Enter your task: ").strip()

                if task.lower() in ("quit", "exit", "q"):
                    print("Goodbye!")
                    break

                if not task:
                    continue

                print()
                # start_time = time.time()
                result = await agent.run(task)
                # end_time = time.time()
                # print(f"Time taken: {end_time - start_time:.2f} seconds")
                # print(f"\nResult: {result}\n")
                agent.reset()

            except KeyboardInterrupt:
                print("\n\nInterrupted. Goodbye!")
                break
            except Exception as e:
                print(f"\nError: {e}\n")


if __name__ == "__main__":
    asyncio.run(main())
