import os
import cv2
import pyshine as ps
from typing import List
from .ui_filter import AndroidElement
from .util import print_with_color

def draw_bbox_multi(
    img_path: str,
    output_path: str,
    elem_list: List[AndroidElement],
    record_mode: bool = False,
    dark_mode: bool = False
) -> cv2.Mat:
    """
    Draw bounding boxes and labels on UI elements in an image.

    Args:
        img_path: Path to input screenshot (can be RGBA or BGR).
        output_path: Path to save output image.
        elem_list: List of AndroidElement objects with .bbox and .raw.
        record_mode: If True, color boxes based on element attributes.
        dark_mode: If True, use dark background for labels.
    Returns:
        The image with drawn bounding boxes (BGR numpy array).
    """
    imgcv = cv2.imread(img_path, cv2.IMREAD_UNCHANGED)
    if imgcv is None:
        raise FileNotFoundError(f"Cannot read image at {img_path}")
    
    # Convert RGBA -> BGR if necessary
    if len(imgcv.shape) == 3 and imgcv.shape[2] == 4:
        imgcv = cv2.cvtColor(imgcv, cv2.COLOR_BGRA2BGR)
        print(f"[INFO] Converted RGBA -> BGR for {img_path}")

    count = 1
    for elem in elem_list:
        try:
            top_left = elem.bbox[0]
            bottom_right = elem.bbox[1]
            left, top = top_left[0], top_left[1]
            right, bottom = bottom_right[0], bottom_right[1]
            label = str(count)

            # Determine label and background color
            if record_mode:
                if elem.raw.get("clickable") == "true":
                    color = (250, 0, 0)  # red
                elif elem.raw.get("focusable") == "true":
                    color = (0, 0, 250)  # blue
                else:
                    color = (0, 250, 0)  # green
                text_color = (255, 250, 250)
            else:
                text_color = (10, 10, 10) if dark_mode else (255, 250, 250)
                color = (255, 250, 250) if dark_mode else (10, 10, 10)

            # Draw rectangle
            # cv2.rectangle(imgcv, (left, top), (right, bottom), color, 2)

            # Draw label using pyshine.putBText
            imgcv = ps.putBText(
                imgcv,
                label,
                text_offset_x=(left + right) // 2 + 10,
                text_offset_y=(top + bottom) // 2 + 10,
                vspace=10,
                hspace=10,
                font_scale=1,
                thickness=2,
                background_RGB=color,
                text_RGB=text_color,
                alpha=0.5
            )
        except Exception as e:
            print_with_color(f"ERROR: An exception occurs while labeling the image\n{e}", "red")
        count += 1

    # Save output image
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    cv2.imwrite(output_path, imgcv)
    print(f"[INFO] Labeled image saved to {output_path}")
    return imgcv