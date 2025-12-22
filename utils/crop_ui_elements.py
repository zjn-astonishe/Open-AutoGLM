import os
import cv2
from typing import List
from utils.ui_filter import AndroidElement

def crop_ui_elements(
    img_path: str,
    output_dir: str,
    elem_list: List[AndroidElement]
) -> List[str]:
    """
    Crop UI elements from a screenshot and save as separate images.

    Args:
        img_path: Path to input screenshot (can be RGBA or BGR).
        output_dir: Directory to save cropped element images.
        elem_list: List of AndroidElement objects with .bbox and .raw.

    Returns:
        List of file paths of cropped element images.
    """
    imgcv = cv2.imread(img_path, cv2.IMREAD_UNCHANGED)
    if imgcv is None:
        raise FileNotFoundError(f"Cannot read image at {img_path}")
    
    # Convert RGBA -> BGR if necessary
    if len(imgcv.shape) == 3 and imgcv.shape[2] == 4:
        imgcv = cv2.cvtColor(imgcv, cv2.COLOR_BGRA2BGR)
        print(f"[INFO] Converted RGBA -> BGR for {img_path}")

    os.makedirs(output_dir, exist_ok=True)
    cropped_paths = []

    for idx, elem in enumerate(elem_list, start=1):
        try:
            (left, top) = elem.bbox[0]
            (right, bottom) = elem.bbox[1]
            
            # Ensure coordinates are within image bounds
            left, top = max(left, 0), max(top, 0)
            right, bottom = min(right, imgcv.shape[1]), min(bottom, imgcv.shape[0])
            
            # Crop the element
            crop_img = imgcv[top:bottom, left:right]
            crop_path = os.path.join(output_dir, f"element_{idx}.png")
            cv2.imwrite(crop_path, crop_img)
            cropped_paths.append(crop_path)
        except Exception as e:
            print(f"[ERROR] Failed to crop element {idx}: {e}")

    print(f"[INFO] Cropped {len(cropped_paths)} elements to {output_dir}")
    return cropped_paths