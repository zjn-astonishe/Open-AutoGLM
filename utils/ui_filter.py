"""
Android UI元素过滤工具模块
用于解析和过滤Android UI XML结构中的可操作元素
并生成类似HTML XPath的语义路径
"""
import xml.etree.ElementTree as ET
from typing import List, Dict, Tuple

class AndroidElement:
    """Android UI元素类，表示一个可交互的UI元素"""
    def __init__(self,
                 elem_id: str,
                 bbox: Tuple[Tuple[int, int], Tuple[int, int]],
                 checked: bool,
                 center: Tuple[int, int],
                 raw_attrib: Dict[str, str],
                 ui_path: List[Dict[str, str]]):
        self.elem_id = elem_id
        self.bbox = bbox
        self.center = center
        self.checked = checked
        self.raw = raw_attrib
        self.ui_path = ui_path  # 父子路径信息，用于生成语义XPath
        # self.compressed_xpath = ""

    def __repr__(self) -> str:
        # return f"<UIElem {self.elem_id} @ {self.center}>"
        return f"<UIElem id={self.elem_id}>"

    def get_xpath(self) -> str:
        """生成类XPath字符串"""
        parts = []
        for step in self.ui_path:
            name = step["class"].split(".")[-1]
            conds = []
            for k in ("resource-id", "content-desc", "text"):
                if k in step:
                    conds.append(f'@{k}="{step[k]}"')
            if conds:
                name += "[" + " | ".join(conds) + "]"
            parts.append(name)
        return "/" + "/".join(parts)


def parse_bounds(elem: ET.Element) -> Tuple[Tuple[int, int], Tuple[int, int], Tuple[int, int]]:
    """解析元素bounds属性，返回(left_top, right_bottom, center)"""
    bounds = elem.attrib["bounds"][1:-1].split("][")
    x1, y1 = map(int, bounds[0].split(","))
    x2, y2 = map(int, bounds[1].split(","))
    return (x1, y1), (x2, y2), ((x1 + x2) // 2, (y1 + y2) // 2)


def is_actionable_u2(elem: ET.Element) -> bool:
    """判断uiautomator2元素是否可操作"""
    return (
        elem.attrib.get("enabled") == "true"
        and elem.attrib.get("visible-to-user") != "false"
        and (
            elem.attrib.get("clickable") == "true"
            or elem.attrib.get("long-clickable") == "true"
            or elem.attrib.get("scrollable") == "true"
        )
    )


def get_u2_element_id(elem: ET.Element) -> str:
    """生成元素ID"""
    parts = []
    for k in ("resource-id", "text", "content-desc"):
        v = elem.attrib.get(k)
        if v:
            parts.append(v.strip()[:20].replace("/", "_"))
    if not parts:
        (x1, y1), (x2, y2), _ = parse_bounds(elem)
        parts.append(f"{elem.attrib.get('class', 'node')}_{x2-x1}x{y2-y1}")
    return "_".join(parts)


def make_step(elem: ET.Element) -> Dict[str, str]:
    """生成语义路径的一步"""
    step = {"class": elem.attrib.get("class", "node")}
    for k in ("resource-id", "content-desc", "text"):
        v = elem.attrib.get(k)
        if v:
            step[k] = v
    return step


def ui_filter(xml_path: str, min_dist: int = 30) -> List[AndroidElement]:
    """
    过滤UI XML中的元素，提取可操作元素，并生成语义路径
    
    Args:
        xml_path: XML路径
        min_dist: 去重阈值
        
    Returns:
        List[AndroidElement]
    """
    elem_list: List[AndroidElement] = []
    path: List[ET.Element] = []

    for event, elem in ET.iterparse(xml_path, ["start", "end"]):
        if event == "start":
            path.append(elem)
            if elem.tag != "node" or not is_actionable_u2(elem):
                continue

            (x1, y1), (x2, y2), center = parse_bounds(elem)
            elem_id = get_u2_element_id(elem)

            # parent context
            if len(path) > 1 and path[-2].tag == "node":
                elem_id = f"{get_u2_element_id(path[-2])}__{elem_id}"

            # 距离去重
            if any(
                ((center[0] - e.center[0]) ** 2 + (center[1] - e.center[1]) ** 2) ** 0.5 <= min_dist
                for e in elem_list
            ):
                continue

            # 生成语义路径
            ui_path = [make_step(e) for e in path if e.tag == "node"]
            
            checked = "enabled" if elem.attrib.get("checked") == "true" and elem.attrib.get("checkable") == "true" else "disabled"

            elem_list.append(AndroidElement(
                elem_id=elem_id,
                bbox=((x1, y1), (x2, y2)),
                checked=checked,
                center=center,
                raw_attrib=elem.attrib,
                ui_path=ui_path
            ))

        elif event == "end":
            path.pop()
    
    # compress_all_xpaths(elem_list)
    return elem_list

# TODO: 压缩XPath功能，考虑动态问题，暂时注释掉
# def compress_all_xpaths(elements: List[AndroidElement]) -> None:
#     """对所有元素的XPath进行全局最大前缀去重，直接写入compressed_xpath属性"""
#     all_paths = [e.ui_path for e in elements]
#     if not all_paths:
#         return

#     # 找最长公共前缀
#     prefix_len = len(all_paths[0])
#     for path in all_paths[1:]:
#         i = 0
#         while i < min(prefix_len, len(path)) and all_paths[0][i] == path[i]:
#             i += 1
#         prefix_len = i

#     for e in elements:
#         unique_suffix = e.ui_path[prefix_len:]
#         parts = []
#         for step in unique_suffix:
#             name = step["class"].split(".")[-1]
#             conds = []
#             for k in ("resource-id", "content-desc", "text"):
#                 if k in step:
#                     conds.append(f'@{k}="{step[k]}"')
#             if conds:
#                 name += "[" + " | ".join(conds) + "]"
#             parts.append(name)
#         e.compressed_xpath = "/" + "/".join(parts) if parts else "/"


if __name__ == "__main__":
    # 测试用例
    xml_file = "tests/screen_ui.xml"
    elems = ui_filter(xml_file)

    print(f"Found {len(elems)} actionable elements\n")
    for i, e in enumerate(elems, 1):
        print(f"{i:02d}. {e}")
        print(f"    XPath: {e.get_xpath()}")
        # print(f"    Compress_XPath: {e.compressed_xpath}\n")
