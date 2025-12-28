ATOMIC_ACTION="""
- Launch
  Launch an app. Try to use launch action when you need to launch an app. Check the instruction to choose the right app before you use this action.
  **Example**:
  do(action="Launch", app="XXX")

- **Tap**
  Perform a tap action on an UI interactive element. 
  "element" is a string, representing the interactive UI element of the tap point.
  **Example**: 
  do(action="Tap", element="R1")

- Type
  Enter text into the currently focused input field.
  **Example**:
  do(action="Type", text="New York")

- Swipe
  Perform a swipe action on an UI interactive element shown on the smartphone screen, usually a scroll view or a slide bar.
  "element" is a string, representing the interactive UI element of the swipe point.
  "direction" is a string, representing the swipe direction, can be "up", "down", "left", or "right".
  "dist" is a string, representing the swipe distance, can be "short", "medium", or "long".
  **Example**:
  do(action="Swipe", element="R1", direction="up", dist="medium")

- Long Press
  Perform a long press action on an UI interactive element.
  "element" is a string, representing the interactive UI element of the long press point.
  **Example**:
  do(action="Long Press", element="R1")

- Back
  Press the Back button to navigate to the previous screen.
  **Example**:
  do(action="Back")

- Finish
  Terminate the program and optionally print a message.
  **Example**:
  do(action="Finish", message="Task completed.")
"""