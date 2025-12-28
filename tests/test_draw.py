import os
from phone_agent.adb.screenshot import get_screenshot
from utils.ui_xml import get_emulator_ui_xml
from utils.ui_filter import ui_filter
from utils.draw_bbox import draw_bbox_multi
from utils.config import load_config
from utils.crop_ui_elements import crop_ui_elements


# ========== Main Test ==========

if __name__ == "__main__":
    xml_path = get_emulator_ui_xml("screen", "./tests", "emulator-5554")
    img_path = get_screenshot("screen", "./tests", "emulator-5554").path
    out_path = "output/out.png"

    assert os.path.exists(xml_path), "ui.xml not found"
    assert os.path.exists(img_path), "screen.png not found"
    print(f"img_path: {img_path}")

    elements = ui_filter(xml_path)

    print(f"[INFO] Found {len(elements)} actionable elements\n")
    for i, e in enumerate(elements, 1):
        print(f"{i:02d}. {e}")
    # configs = load_config()

    # draw_bbox_multi(img_path, out_path, elements, dark_mode=configs["DARK_MODE"])
    # crop_ui_elements(
    #     img_path,
    #     output_dir="output/crops",
    #     elem_list=elements
    # )
    print(f"\n[OK] Visualization saved to {out_path}")
