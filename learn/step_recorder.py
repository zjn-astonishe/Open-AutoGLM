import datetime
import cv2
import os
import sys
import time

from phone_agent.device_factory import DeviceType, get_device_factory
from utils.config import load_config
from utils.draw_bbox import draw_bbox_multi
from utils.util import print_with_color
from utils.ui_xml import get_emulator_ui_xml
from utils.ui_filter import ui_filter
from act_mem import ActionMemory, WorkflowRecorder


def run_step_recorder(app=None, demo_name=None, root_dir="./", device_type="adb", device_id=None):
    """
    Run the step recorder for human demonstration.
    
    Args:
        app: Name of the app to demo
        demo_name: Name of the demo session
        root_dir: Root directory for output
        device_type: Device type ("adb" or "hdc")
        device_id: Specific device ID to use
    
    Returns:
        dict: Summary of recorded data
    """
    print("=" * 50)
    print("Phone Agent - Human Demonstration Recorder")
    print("=" * 50)
    
    device_type_enum = DeviceType.ADB if device_type == "adb" else DeviceType.HDC
    configs = load_config()

    if not app:
        print_with_color("What is the name of the app you are going to demo?", "blue")
        app = input()
        app = app.replace(" ", "")
    
    if not demo_name:
        demo_timestamp = int(time.time())
        demo_name = datetime.datetime.fromtimestamp(demo_timestamp).strftime(f"demo_{app}_%Y-%m-%d_%H-%M-%S")

    # Create temporary directories for screenshots and XML (for visualization only)
    temp_dir = os.path.join(root_dir, "output", "temp", demo_name)
    os.makedirs(temp_dir, exist_ok=True)
    raw_ss_dir = os.path.join(temp_dir, "screenshots")
    xml_dir = os.path.join(temp_dir, "xml")
    os.makedirs(raw_ss_dir, exist_ok=True)
    os.makedirs(xml_dir, exist_ok=True)

    # Initialize device factory
    device_factory = get_device_factory()
    device_factory.device_type = device_type_enum

    # Get device list
    device_list = device_factory.list_devices()
    if not device_list:
        print_with_color("ERROR: No device found!", "red")
        return None

    # Convert device info objects to device IDs for display
    device_ids = [device.device_id for device in device_list]
    print_with_color("List of devices attached:\n" + str(device_ids), "yellow")

    # Select device
    if device_id:
        device = device_id
        print_with_color(f"Using specified device: {device}", "yellow")
    elif len(device_list) == 1:
        device = device_list[0].device_id
        print_with_color(f"Device selected: {device}", "yellow")
    else:
        print_with_color("Please choose the device to start demo by entering its ID:", "blue")
        device = input()

    # Get device size using screenshot
    try:
        screenshot = device_factory.get_screenshot(device_id=device)
        width, height = screenshot.width, screenshot.height
        if not width and not height:
            print_with_color("ERROR: Invalid device size!", "red")
            return None
        print_with_color(f"Screen resolution of {device}: {width}x{height}", "yellow")
    except Exception as e:
        print_with_color(f"ERROR: Could not get device size: {e}", "red")
        return None

    print_with_color("Please state the goal of your following demo actions clearly, e.g. send a message to John", "blue")
    task_desc = input()

    # Initialize ActionMemory and WorkflowRecorder
    memory_dir = configs["MEMORY_DIR"]
    action_memory = ActionMemory(memory_dir)
    work_graph = action_memory.add_work_graph(app)
    workflow = action_memory.create_workflow(task_desc)
    workflow_recorder = WorkflowRecorder(task_desc, workflow)
    workflow_recorder.set_tag(app)

    # Variables to track current and previous nodes
    current_node = None
    previous_node = None

    print_with_color("All interactive elements on the screen are labeled with red and blue numeric tags. Elements "
                     "labeled with red tags are clickable elements; elements labeled with blue tags are scrollable "
                     "elements.", "blue")

    step = 0
    while True:
        step += 1
        
        # Get screenshot
        try:
            screenshot = device_factory.get_screenshot(prefix=f"{demo_name}_{step}", save_dir=raw_ss_dir, device_id=device)
            screenshot_path = screenshot.path
            if not screenshot_path or not os.path.exists(screenshot_path):
                print_with_color("ERROR: Failed to capture screenshot", "red")
                break
        except Exception as e:
            print_with_color(f"ERROR: Screenshot capture failed: {e}", "red")
            break
        
        # Get XML
        try:
            xml_path = get_emulator_ui_xml(f"{demo_name}_{step}", xml_dir, emulator_device=device)
            if not xml_path or not os.path.exists(xml_path):
                print_with_color("ERROR: Failed to get UI XML", "red")
                break
        except Exception as e:
            print_with_color(f"ERROR: UI XML capture failed: {e}", "red")
            break
        
        # Filter UI elements
        try:
            elem_list = ui_filter(xml_path, min_dist=configs.get("MIN_DIST", 30))
        except Exception as e:
            print_with_color(f"ERROR: UI filtering failed: {e}", "red")
            break
        
        # Create or update current node based on UI elements
        elements_info = []
        for elem in elem_list:
            elem_info = {
                "elem_id": elem.elem_id,
                "xpath": elem.get_simple_xpath(),
                "center": elem.center,
                "bbox": elem.bbox
            }
            elements_info.append(elem_info)
        
        # Update node tracking
        previous_node = current_node
        current_node = work_graph.create_node(elements_info)
        current_node.add_task(task_desc)
        current_node.add_tag(app)
        
        # If we have a previous node, record the transition
        if previous_node and previous_node != current_node:
            workflow_recorder.on_new_node(current_node.id)
        
        # Draw bounding boxes for visualization
        try:
            labeled_img = draw_bbox_multi(screenshot_path, None, elem_list, True)
            cv2.imshow("image", labeled_img)
            cv2.waitKey(0)
            cv2.destroyAllWindows()
        except Exception as e:
            print_with_color(f"ERROR: Failed to draw bounding boxes: {e}", "red")
            break
        
        user_input = "xxx"
        print_with_color("Choose one of the following actions you want to perform on the current screen:\ntap, text, long "
                         "press, swipe, stop", "blue")
        while user_input.lower() not in ["tap", "text", "long press", "swipe", "stop"]:
            user_input = input()
        
        if user_input.lower() == "tap":
            print_with_color(f"Which element do you want to tap? Choose a numeric tag from 1 to {len(elem_list)}:", "blue")
            user_input = "xxx"
            while not user_input.isnumeric() or int(user_input) > len(elem_list) or int(user_input) < 1:
                user_input = input()
            
            selected_elem = elem_list[int(user_input) - 1]
            x, y = selected_elem.center
            
            try:
                # Record action in workflow
                action = current_node.add_action(
                    action_type="tap",
                    description=f"Tap on element {selected_elem.elem_id}",
                    zone_path=selected_elem.get_simple_xpath()
                )
                workflow_recorder.on_action_executed(current_node.id, action, True)
                
                device_factory.tap(x, y, device_id=device)
            except Exception as e:
                print_with_color(f"ERROR: tap execution failed: {e}", "red")
                break
                
        elif user_input.lower() == "text":
            print_with_color(f"Which element do you want to input the text string? Choose a numeric tag from 1 to "
                             f"{len(elem_list)}:", "blue")
            input_area = "xxx"
            while not input_area.isnumeric() or int(input_area) > len(elem_list) or int(input_area) < 1:
                input_area = input()
            print_with_color("Enter your input text below:", "blue")
            user_input = ""
            while not user_input:
                user_input = input()
            
            try:
                selected_elem = elem_list[int(input_area) - 1]
                
                # Record action in workflow
                action = current_node.add_action(
                    action_type="text",
                    description=f"Input text '{user_input}' on element {selected_elem.elem_id}",
                    zone_path=selected_elem.get_simple_xpath(),
                    text=user_input
                )
                workflow_recorder.on_action_executed(current_node.id, action, True)
                
                device_factory.type_text(user_input, device_id=device)
            except Exception as e:
                print_with_color(f"ERROR: text input failed: {e}", "red")
                break
                
        elif user_input.lower() == "long press":
            print_with_color(f"Which element do you want to long press? Choose a numeric tag from 1 to {len(elem_list)}:",
                             "blue")
            user_input = "xxx"
            while not user_input.isnumeric() or int(user_input) > len(elem_list) or int(user_input) < 1:
                user_input = input()
            
            selected_elem = elem_list[int(user_input) - 1]
            x, y = selected_elem.center
            
            try:
                # Record action in workflow
                action = current_node.add_action(
                    action_type="long_press",
                    description=f"Long press on element {selected_elem.elem_id}",
                    zone_path=selected_elem.get_simple_xpath()
                )
                workflow_recorder.on_action_executed(current_node.id, action, True)
                
                device_factory.long_press(x, y, device_id=device)
            except Exception as e:
                print_with_color(f"ERROR: long press execution failed: {e}", "red")
                break
                
        elif user_input.lower() == "swipe":
            print_with_color(f"What is the direction of your swipe? Choose one from the following options:\nup, down, left,"
                             f" right", "blue")
            user_input = ""
            while user_input not in ["up", "down", "left", "right"]:
                user_input = input()
            swipe_dir = user_input
            
            print_with_color(f"Which element do you want to swipe? Choose a numeric tag from 1 to {len(elem_list)}:", "blue")
            user_input = "xxx"
            while not user_input.isnumeric() or int(user_input) > len(elem_list) or int(user_input) < 1:
                user_input = input()
            
            selected_elem = elem_list[int(user_input) - 1]
            start_x, start_y = selected_elem.center
            
            # Calculate swipe end coordinates based on direction
            swipe_distance = 200  # pixels
            if swipe_dir == "up":
                end_x, end_y = start_x, start_y - swipe_distance
            elif swipe_dir == "down":
                end_x, end_y = start_x, start_y + swipe_distance
            elif swipe_dir == "left":
                end_x, end_y = start_x - swipe_distance, start_y
            else:  # right
                end_x, end_y = start_x + swipe_distance, start_y
            
            try:
                # Record action in workflow
                action = current_node.add_action(
                    action_type="swipe",
                    description=f"Swipe {swipe_dir} on element {selected_elem.elem_id}",
                    zone_path=selected_elem.get_simple_xpath(),
                    direction=swipe_dir,
                    distance=swipe_distance
                )
                workflow_recorder.on_action_executed(current_node.id, action, True)
                
                device_factory.swipe(start_x, start_y, end_x, end_y, device_id=device)
            except Exception as e:
                print_with_color(f"ERROR: swipe execution failed: {e}", "red")
                break
                
        elif user_input.lower() == "stop":
            break
        else:
            break
        
        time.sleep(3)

    # Flush workflow recorder and save memory data
    workflow_recorder.flush()
    action_memory.to_json()

    print_with_color(f"Demonstration phase completed. {step} steps were recorded.", "yellow")
    print_with_color(f"Workflow and memory data saved to {memory_dir}", "green")

    # Print summary of recorded data
    print_with_color("\n=== Recorded Data Summary ===", "cyan")
    print_with_color(f"App: {app}", "white")
    print_with_color(f"Task: {task_desc}", "white")
    print_with_color(f"Workflow ID: {workflow.id}", "white")
    print_with_color(f"Total nodes in graph: {len(work_graph.nodes)}", "white")
    print_with_color(f"Total transitions in workflow: {len(workflow.path)}", "white")
    
    # Return summary data
    return {
        "app": app,
        "task_desc": task_desc,
        "workflow_id": workflow.id,
        "total_nodes": len(work_graph.nodes),
        "total_transitions": len(workflow.path),
        "steps_recorded": step,
        "memory_dir": memory_dir
    }


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Phone Agent - Human Demonstration Recorder",
        formatter_class=argparse.RawDescriptionHelpFormatter, 
    )
    parser.add_argument("--app", help="Name of the app to demo")
    parser.add_argument("--demo", help="Name of the demo session")
    parser.add_argument("--root_dir", default="./", help="Root directory for output")
    parser.add_argument("--device_type", default="adb", choices=["adb", "hdc"], 
                       help="Device type (adb for Android, hdc for HarmonyOS)")
    parser.add_argument("--device_id", help="Specific device ID to use")
    
    args = parser.parse_args()
    
    run_step_recorder(
        app=args.app,
        demo_name=args.demo,
        root_dir=args.root_dir,
        device_type=args.device_type,
        device_id=args.device_id
    )
