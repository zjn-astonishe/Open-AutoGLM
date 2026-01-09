def bluetooth_disable(swipe_element="com.google.android.apps.nexuslauncher:id/workspace", 
                     bluetooth_tile_element="com.android.systemui:id/qqs_tile_layout|Bluetooth.|On",
                     swipe_direction="down", 
                     swipe_distance=500):
    """
    Abstract function to disable Bluetooth on mobile devices.
    
    This function handles the workflow of turning off Bluetooth by swiping down to access
    quick settings and then tapping the Bluetooth tile. The function is designed to be
    flexible by allowing customization of the elements and swipe parameters.
    
    Parameters:
    - swipe_element (str): The element to swipe on to open quick settings (default: workspace element)
    - bluetooth_tile_element (str): The element ID of the Bluetooth tile in quick settings (default: Bluetooth tile when on)
    - swipe_direction (str): Direction to swipe (default: "down")
    - swipe_distance (int): Distance to swipe in pixels (default: 500)
    
    Returns:
    - List of action dictionaries to execute the Bluetooth disable workflow
    """
    actions = []
    
    # Step 1: Swipe down from the top of the screen to open the quick settings panel
    actions.append({
        "action": "Swipe",
        "element": swipe_element,
        "direction": swipe_direction,
        "dist": swipe_distance
    })
    
    # Step 2: Tap the Bluetooth tile to turn it off
    actions.append({
        "action": "Tap",
        "element": bluetooth_tile_element
    })
    
    return actions