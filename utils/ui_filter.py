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
                 ui_path: List[Dict[str, str]],
                 focused: bool = False):
        self.elem_id = elem_id
        self.bbox = bbox
        self.center = center
        self.checked = checked
        self.focused = focused
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
    
    def get_simple_xpath(self) -> str:
        """生成简化的XPath字符串，只包含当前元素的关键标识信息"""
        if not self.ui_path:
            return "/"
        
        # 只取最后一个元素（当前元素）的信息
        current_step = self.ui_path[-1]
        name = current_step["class"].split(".")[-1]
        conds = []
        
        for k in ("resource-id", "content-desc", "text"):
            if k in current_step:
                conds.append(f'@{k}="{current_step[k]}"')
        
        if conds:
            name += "[" + " | ".join(conds) + "]"
        
        return "/" + name


def parse_bounds(elem: ET.Element) -> Tuple[Tuple[int, int], Tuple[int, int], Tuple[int, int]]:
    """解析元素bounds属性，返回(left_top, right_bottom, center)"""
    bounds = elem.attrib["bounds"][1:-1].split("][")
    x1, y1 = map(int, bounds[0].split(","))
    x2, y2 = map(int, bounds[1].split(","))
    return (x1, y1), (x2, y2), ((x1 + x2) // 2, (y1 + y2) // 2)


def is_clickable_u2(elem: ET.Element) -> bool:
    """判断uiautomator2元素是否可点击"""
    return (
        elem.attrib.get("enabled") == "true"
        and elem.attrib.get("visible-to-user") != "false"
        and (
            elem.attrib.get("clickable") == "true"
            or elem.attrib.get("long-clickable") == "true"
            or elem.attrib.get("scrollable") == "true"
        )
    )


def is_focusable_u2(elem: ET.Element) -> bool:
    """判断uiautomator2元素是否可聚焦"""
    return (
        elem.attrib.get("enabled") == "true"
        and elem.attrib.get("visible-to-user") != "false"
        and elem.attrib.get("focusable") == "true"
    )


def is_actionable_u2(elem: ET.Element) -> bool:
    """判断uiautomator2元素是否可操作（可点击或可聚焦）"""
    return is_clickable_u2(elem) or is_focusable_u2(elem)


def get_semantic_info_from_children(elem: ET.Element) -> Dict[str, str]:
    """从子元素中提取语义信息"""
    semantic_info = {}
    
    # 递归查找子元素中的语义信息
    def extract_from_element(element):
        for k in ("resource-id", "text", "content-desc"):
            v = element.attrib.get(k)
            if v and v.strip():
                if k not in semantic_info:
                    semantic_info[k] = v.strip()
                elif k == "text" and len(v.strip()) > len(semantic_info[k]):
                    # 如果找到更长的文本，使用更长的
                    semantic_info[k] = v.strip()
        
        # 递归处理子元素
        for child in element:
            if child.tag == "node":
                extract_from_element(child)
    
    # 从直接子元素开始查找
    for child in elem:
        if child.tag == "node":
            extract_from_element(child)
    
    return semantic_info


def get_u2_element_id_without_children(elem: ET.Element) -> str:
    """生成元素ID，但不从子元素中提取语义信息"""
    parts = []
    
    # 只从当前元素获取语义信息
    for k in ("resource-id", "text", "content-desc"):
        v = elem.attrib.get(k)
        if v and v.strip():
            parts.append(v.strip().replace("/", "_"))
    
    if not parts:
        (x1, y1), (x2, y2), _ = parse_bounds(elem)
        parts.append(f"{elem.attrib.get('class', 'node')}_{x2-x1}x{y2-y1}")
    
    return "_".join(parts)


def get_u2_element_id(elem: ET.Element) -> str:
    """生成元素ID"""
    parts = []
    
    # 首先尝试从当前元素获取语义信息
    for k in ("resource-id", "text", "content-desc"):
        v = elem.attrib.get(k)
        if v and v.strip():
            parts.append(v.strip().replace("/", "_"))
    
    # 如果当前元素没有足够的语义信息，从子元素中查找
    if not parts or (len(parts) == 1 and parts[0].startswith("com.")):
        child_semantic = get_semantic_info_from_children(elem)
        for k in ("text", "content-desc", "resource-id"):
            v = child_semantic.get(k)
            if v and v not in [p.replace("_", "/") for p in parts]:
                parts.append(v.replace("/", "_"))
    
    if not parts:
        (x1, y1), (x2, y2), _ = parse_bounds(elem)
        parts.append(f"{elem.attrib.get('class', 'node')}_{x2-x1}x{y2-y1}")
    
    return "_".join(parts)


def make_step(elem: ET.Element, is_target_element: bool = False) -> Dict[str, str]:
    """生成语义路径的一步"""
    step = {"class": elem.attrib.get("class", "node")}
    
    # 首先从当前元素获取属性
    has_semantic_info = False
    for k in ("resource-id", "content-desc", "text"):
        v = elem.attrib.get(k)
        if v and v.strip():
            step[k] = v
            if k in ("content-desc", "text"):
                has_semantic_info = True
    
    # 只有当这是目标元素（可操作元素）且缺少语义信息时，才从子元素中补充
    if is_target_element and not has_semantic_info:
        child_semantic = get_semantic_info_from_children(elem)
        for k in ("text", "content-desc"):
            if k not in step and child_semantic.get(k):
                step[k] = child_semantic[k]
    
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
    clickable_list: List[AndroidElement] = []
    focusable_list: List[AndroidElement] = []
    
    def process_element(elem: ET.Element, path: List[ET.Element]) -> AndroidElement:
        """处理单个元素，生成AndroidElement对象"""
        (x1, y1), (x2, y2), center = parse_bounds(elem)
        elem_id = get_u2_element_id(elem)

        # parent context - 但不要让父元素从子元素中提取语义信息
        if len(path) > 1 and path[-2].tag == "node":
            parent_id = get_u2_element_id_without_children(path[-2])
            elem_id = f"{parent_id}__{elem_id}"

        # 生成语义路径
        ui_path = []
        for i, e in enumerate(path):
            if e.tag == "node":
                # 只有最后一个元素（目标元素）才允许从子元素中提取语义信息
                is_target = (i == len(path) - 1)
                ui_path.append(make_step(e, is_target_element=is_target))
        
        checked = "enabled" if elem.attrib.get("checked") == "true" and elem.attrib.get("checkable") == "true" else "disabled"
        focused = "enabled" if elem.attrib.get("focused") == "true" and elem.attrib.get("focusable") == "true" else "disabled"
        # Keep checked as the primary state indicator for backwards compatibility
        checked = checked or focused

        return AndroidElement(
            elem_id=elem_id,
            bbox=((x1, y1), (x2, y2)),
            checked=checked,
            center=center,
            raw_attrib=elem.attrib,
            ui_path=ui_path,
            focused=focused
        )

    # 第一遍：收集所有可点击元素
    path: List[ET.Element] = []
    for event, elem in ET.iterparse(xml_path, ["start", "end"]):
        if event == "start":
            path.append(elem)
            if elem.tag == "node" and is_clickable_u2(elem):
                android_elem = process_element(elem, path.copy())
                clickable_list.append(android_elem)
        elif event == "end":
            path.pop()

    # 第二遍：收集所有可聚焦元素
    path = []
    for event, elem in ET.iterparse(xml_path, ["start", "end"]):
        if event == "start":
            path.append(elem)
            if elem.tag == "node" and is_focusable_u2(elem):
                android_elem = process_element(elem, path.copy())
                focusable_list.append(android_elem)
        elif event == "end":
            path.pop()

    # 合并列表：先添加所有可点击元素
    elem_list = clickable_list.copy()
    
    # 然后添加不与可点击元素重复的可聚焦元素
    for focusable_elem in focusable_list:
        bbox = focusable_elem.bbox
        center = (bbox[0][0] + bbox[1][0]) // 2, (bbox[0][1] + bbox[1][1]) // 2
        close = False
        
        for clickable_elem in clickable_list:
            clickable_bbox = clickable_elem.bbox
            clickable_center = (clickable_bbox[0][0] + clickable_bbox[1][0]) // 2, (clickable_bbox[0][1] + clickable_bbox[1][1]) // 2
            dist = (abs(center[0] - clickable_center[0]) ** 2 + abs(center[1] - clickable_center[1]) ** 2) ** 0.5
            
            if dist <= min_dist:
                # 检查是否有不同的语义信息
                focusable_resource_id = focusable_elem.raw.get("resource-id", "")
                focusable_content_desc = focusable_elem.raw.get("content-desc", "")
                focusable_text = focusable_elem.raw.get("text", "")
                
                clickable_resource_id = clickable_elem.raw.get("resource-id", "")
                clickable_content_desc = clickable_elem.raw.get("content-desc", "")
                clickable_text = clickable_elem.raw.get("text", "")
                
                # 如果有不同的语义标识，则不认为是重复
                if (focusable_resource_id and clickable_resource_id and focusable_resource_id != clickable_resource_id) or \
                   (focusable_content_desc and clickable_content_desc and focusable_content_desc != clickable_content_desc) or \
                   (focusable_text and clickable_text and focusable_text != clickable_text):
                    continue
                
                close = True
                break
        
        if not close:
            elem_list.append(focusable_elem)
    
    return elem_list


if __name__ == "__main__":
    # 测试用例
    xml_file = "tests/test_ui.xml"
    elems = ui_filter(xml_file)

    print(f"Found {len(elems)} actionable elements\n")
    for i, e in enumerate(elems, 1):
        print(f"{i:02d}. {e}")
        print(f"    XPath: {e.get_xpath()}")
        # print(f"    Compress_XPath: {e.compressed_xpath}\n")
