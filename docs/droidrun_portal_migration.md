# Droidrun Portal 移植指南

本文档说明如何将 droidrun 项目中的 Droidrun Portal UI 处理方式移植到 Open-AutoGLM 项目，替代现有的 `utils/ui_xml.py` 和 `utils/ui_filter.py`。

## 目录
1. [架构对比](#架构对比)
2. [核心差异](#核心差异)
3. [移植方案](#移植方案)
4. [实施步骤](#实施步骤)
5. [代码示例](#代码示例)

---

## 架构对比

### 现有方案 (Open-AutoGLM)

```
┌─────────────────┐
│  ui_xml.py      │  → 使用 uiautomator2 获取 XML
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  ui_filter.py   │  → 解析 XML，过滤可操作元素
└────────┬────────┘
         │
         ▼
     AndroidElement
     (elem_id, bbox, xpath)
```

**特点**：
- ✅ 简单直接，易于理解
- ✅ 无需额外应用安装
- ❌ 性能较慢（XML 解析开销大）
- ❌ 信息有限（只有 UI 层级）
- ❌ 无设备状态信息

### Droidrun Portal 方案

```
┌──────────────────────┐
│  Portal App          │  → 在设备上运行的应用
│  (AccessibilityService)
└──────────┬───────────┘
           │ HTTP/ContentProvider
           ▼
┌──────────────────────┐
│  PortalClient        │  → 统一通信层 (TCP/ContentProvider fallback)
└──────────┬───────────┘
           │
           ▼
    ┌──────┴──────┐
    │             │
    ▼             ▼
┌─────────┐  ┌──────────┐
│ Filter  │  │Formatter │  → 可插拔的过滤和格式化
└─────────┘  └──────────┘
           │
           ▼
    Structured Data
    (a11y_tree, phone_state, device_context)
```

**特点**：
- ✅ 性能优异（原生 AccessibilityService）
- ✅ 信息丰富（UI + 设备状态 + 上下文）
- ✅ 灵活的过滤和格式化机制
- ✅ TCP 通信速度快
- ❌ 需要安装 Portal APK
- ❌ 架构更复杂

---

## 核心差异

### 1. 数据获取方式

| 方面 | 现有方案 | Droidrun Portal |
|------|---------|----------------|
| 数据源 | uiautomator2 XML dump | AccessibilityService |
| 格式 | XML 字符串 | JSON (a11y_tree + phone_state) |
| 性能 | 慢 (XML 解析) | 快 (原生 JSON) |
| 信息量 | UI 层级 | UI + 设备状态 + 焦点信息 |

### 2. 元素表示

**现有方案 (AndroidElement)**:
```python
class AndroidElement:
    elem_id: str          # 语义 ID
    bbox: Tuple           # 边界框
    center: Tuple         # 中心坐标
    checked: bool         # 选中状态
    raw: Dict            # 原始属性
    ui_path: List        # 父子路径（用于 XPath）
```

**Droidrun Portal**:
```python
{
    "index": 1,                    # 索引（用于点击）
    "className": "Button",         # 类名
    "resourceId": "com.app:id/btn",
    "text": "Submit",
    "bounds": "100,200,300,400",   # left,top,right,bottom
    "children": [],                # 子元素
    "boundsInScreen": {            # 原始边界（在 filter 前）
        "left": 100, "top": 200,
        "right": 300, "bottom": 400
    }
}
```

### 3. 过滤逻辑

**现有方案**:
- 基于 XML 属性过滤（clickable, focusable, scrollable）
- 使用 XPath 表示元素路径
- 去重基于中心点距离

**Droidrun Portal**:
- 可插拔的 Filter 系统（ConciseFilter, DetailedFilter）
- 基于屏幕边界和最小尺寸过滤
- 保留层级结构
- 支持 Vision 和 Non-Vision 模式

---

## 移植方案

### 方案 A: 完全替换（推荐）

**优点**：
- 获得 Droidrun Portal 的全部优势
- 代码更现代化、可维护
- 性能显著提升

**缺点**：
- 需要安装 Portal APK
- 改动较大

**适用场景**：
- 追求性能和功能完整性
- 愿意部署 Portal 应用
- 长期维护项目

### 方案 B: 混合方案

**实现方式**：
- 保留现有的 ui_xml.py 和 ui_filter.py 作为备选
- 添加 Portal 支持作为可选模式
- 运行时根据配置选择使用哪种方式

**优点**：
- 向后兼容
- 灵活切换
- 风险较低

**缺点**：
- 维护两套代码
- 代码复杂度增加

**适用场景**：
- 需要兼容性
- 逐步迁移
- 多环境支持

### 方案 C: 借鉴设计，自主实现

**实现方式**：
- 学习 Portal 的 Filter/Formatter 设计模式
- 改进现有的 ui_filter.py，采用类似架构
- 保持 uiautomator2 作为数据源

**优点**：
- 无需额外依赖
- 改进代码架构
- 保持简单性

**缺点**：
- 性能提升有限
- 无法获得设备状态信息

---

## 实施步骤

### 阶段 1: 准备工作

1. **安装 Portal APK**
   ```bash
   # 从 droidrun 项目构建或下载 Portal APK
   adb install -r droidrun_portal.apk
   
   # 授予必要权限
   adb shell pm grant com.droidrun.portal android.permission.SYSTEM_ALERT_WINDOW
   ```

2. **创建项目结构**
   ```
   phone_agent/
   ├── portal/
   │   ├── __init__.py
   │   ├── portal_client.py      # Portal 通信客户端
   │   ├── filters/
   │   │   ├── __init__.py
   │   │   ├── base.py
   │   │   ├── concise_filter.py
   │   │   └── detailed_filter.py
   │   └── formatters/
   │       ├── __init__.py
   │       ├── base.py
   │       └── indexed_formatter.py
   ```

### 阶段 2: 核心组件移植

1. **移植 PortalClient**
   - 复制 `droidrun/tools/android/portal_client.py`
   - 适配项目的 ADB 客户端（可能需要从 async_adbutils 改为 uiautomator2）

2. **移植 Filter 系统**
   - 复制 `droidrun/tools/filters/` 目录
   - 根据需要调整过滤逻辑

3. **移植 Formatter 系统**
   - 复制 `droidrun/tools/formatters/` 目录
   - 适配输出格式

### 阶段 3: 集成到现有代码

1. **创建适配器层**
   ```python
   # phone_agent/portal/adapter.py
   class PortalUIProvider:
       """适配 Portal 到现有接口"""
       
       def get_ui_elements(self) -> List[AndroidElement]:
           """获取 UI 元素（兼容现有接口）"""
           pass
   ```

2. **更新 Agent**
   ```python
   # phone_agent/agent.py
   class Agent:
       def __init__(self, use_portal=True):
           if use_portal:
               self.ui_provider = PortalUIProvider()
           else:
               self.ui_provider = LegacyUIProvider()  # 现有方案
   ```

3. **配置支持**
   ```yaml
   # config/config.yaml
   ui_provider:
     type: portal  # or legacy
     portal:
       use_tcp: true
       port: 8080
   ```

### 阶段 4: 测试和优化

1. **功能测试**
   - 测试基本的 UI 获取和过滤
   - 测试点击、输入等操作
   - 对比新旧方案的输出

2. **性能测试**
   - 测量 UI 获取速度
   - 测量内存占用
   - 优化瓶颈

3. **兼容性测试**
   - 测试不同 Android 版本
   - 测试不同设备型号
   - 测试 TCP/ContentProvider fallback

---

## 代码示例

### 示例 1: PortalClient 使用

```python
from phone_agent.portal.portal_client import PortalClient
import asyncio

async def main():
    # 初始化 Portal 客户端
    portal = PortalClient(device, prefer_tcp=True)
    await portal.connect()
    
    # 获取设备状态
    state = await portal.get_state()
    
    # state 包含：
    # - a11y_tree: UI 层级树
    # - phone_state: 设备状态（当前应用、焦点等）
    # - device_context: 设备上下文（屏幕尺寸等）
    
    print(f"Current app: {state['phone_state']['currentApp']}")
    print(f"UI elements: {len(state['a11y_tree'])}")
    
    # 输入文本
    await portal.input_text("Hello, World!", clear=True)
    
    # 截图
    screenshot_bytes = await portal.take_screenshot(hide_overlay=True)

asyncio.run(main())
```

### 示例 2: Filter 使用

```python
from phone_agent.portal.filters import ConciseFilter, DetailedFilter

# 选择过滤器（基于是否使用 Vision）
filter = ConciseFilter() if vision_enabled else DetailedFilter()

# 过滤 UI 树
filtered_tree = filter.filter(
    a11y_tree=state['a11y_tree'],
    device_context=state['device_context']
)
```

### 示例 3: Formatter 使用

```python
from phone_agent.portal.formatters import IndexedFormatter

formatter = IndexedFormatter()
formatter.screen_width = 1080
formatter.screen_height = 2400

# 格式化为文本和结构化数据
formatted_text, focused_text, elements_list, phone_state = formatter.format(
    filtered_tree=filtered_tree,
    phone_state=state['phone_state']
)

# formatted_text: Markdown 格式的文本描述
# focused_text: 当前焦点元素的文本
# elements_list: 带索引的元素列表（用于点击）
# phone_state: 设备状态字典
```

### 示例 4: 兼容层实现

```python
from typing import List
from utils.ui_filter import AndroidElement

class PortalUIAdapter:
    """将 Portal 输出适配为 AndroidElement 格式"""
    
    def __init__(self, portal_client):
        self.portal = portal_client
        self.filter = ConciseFilter()
        self.formatter = IndexedFormatter()
    
    async def get_elements(self) -> List[AndroidElement]:
        """获取 UI 元素（兼容旧接口）"""
        # 获取原始状态
        state = await self.portal.get_state()
        
        # 过滤
        filtered = self.filter.filter(
            state['a11y_tree'],
            state['device_context']
        )
        
        # 格式化
        _, _, elements, _ = self.formatter.format(filtered, state['phone_state'])
        
        # 转换为 AndroidElement
        result = []
        for elem in self._flatten_elements(elements):
            result.append(self._to_android_element(elem))
        
        return result
    
    def _to_android_element(self, elem: dict) -> AndroidElement:
        """转换为 AndroidElement"""
        bounds_str = elem['bounds']
        left, top, right, bottom = map(int, bounds_str.split(','))
        
        return AndroidElement(
            elem_id=elem.get('resourceId') or elem.get('text') or f"idx_{elem['index']}",
            bbox=((left, top), (right, bottom)),
            center=((left + right) // 2, (top + bottom) // 2),
            checked='enabled' if elem.get('checked') else 'disabled',
            raw_attrib={'index': elem['index']},
            ui_path=[{
                'class': elem['className'],
                'resource-id': elem.get('resourceId', ''),
                'text': elem.get('text', '')
            }],
            focused=False
        )
    
    def _flatten_elements(self, elements: List[dict]) -> List[dict]:
        """扁平化元素树"""
        result = []
        for elem in elements:
            result.append(elem)
            if elem.get('children'):
                result.extend(self._flatten_elements(elem['children']))
        return result
```

---

## 配置文件示例

```yaml
# config/config.yaml
ui_provider:
  # 选择 UI 提供者: portal 或 legacy
  type: portal
  
  # Portal 配置
  portal:
    # 是否优先使用 TCP（更快）
    use_tcp: true
    
    # Portal 服务端口
    port: 8080
    
    # 过滤器类型: concise 或 detailed
    # concise: 用于 Vision 模式（元素更少，依赖视觉理解）
    # detailed: 用于 Non-Vision 模式（元素更多，包含更多信息）
    filter: concise
    
    # 格式化器类型
    formatter: indexed
    
    # 是否隐藏截图中的 Portal overlay
    hide_overlay: true
    
    # 过滤参数
    filtering:
      # 最小元素尺寸（像素）
      min_element_size: 5
  
  # Legacy 配置（备用）
  legacy:
    # XML 保存目录
    xml_dir: tests
    
    # 去重阈值（像素）
    min_dist: 30
```

---

## 迁移检查清单

### 必需步骤
- [ ] 安装 Portal APK 到测试设备
- [ ] 授予 Portal 必要的权限（Accessibility, Overlay）
- [ ] 复制 Portal 相关代码到项目
- [ ] 适配 ADB 客户端接口
- [ ] 创建配置文件
- [ ] 实现基本的 get_state 功能
- [ ] 测试 TCP 和 ContentProvider 两种模式

### 集成步骤
- [ ] 创建兼容层（PortalUIAdapter）
- [ ] 更新 Agent 使用新的 UI 提供者
- [ ] 更新点击、输入等操作使用 Portal
- [ ] 添加配置切换支持
- [ ] 编写单元测试
- [ ] 编写集成测试

### 优化步骤
- [ ] 性能基准测试
- [ ] 内存使用优化
- [ ] 错误处理和重试机制
- [ ] 日志和调试支持
- [ ] 文档更新

### 可选步骤
- [ ] 支持自定义 Filter
- [ ] 支持自定义 Formatter
- [ ] 添加 UI 元素缓存
- [ ] 添加截图对比功能
- [ ] 集成 trajectory 记录

---

## 常见问题

### Q1: Portal APK 从哪里获取？
A: 需要从 droidrun 项目构建，或联系 droidrun 团队获取预编译版本。

### Q2: Portal 需要什么权限？
A: 主要需要 Accessibility Service 和 System Alert Window 权限。

### Q3: 如何处理 Portal 崩溃？
A: 实现 fallback 机制，当 Portal 不可用时自动切换到 legacy 方案。

### Q4: TCP 模式和 ContentProvider 模式如何选择？
A: PortalClient 会自动选择。TCP 更快但需要端口转发；ContentProvider 更稳定但稍慢。

### Q5: 是否需要完全替换现有代码？
A: 不需要，建议采用混合方案，保留现有代码作为备选。

---

## 总结

Droidrun Portal 提供了一个更现代、更高性能的 UI 处理方案。建议采用**混合方案（方案 B）**进行逐步迁移：

1. **短期**：添加 Portal 支持，与现有方案并存
2. **中期**：在新功能中优先使用 Portal
3. **长期**：逐步淘汰 legacy 方案

这样可以在保持兼容性的同时，逐步享受 Portal 带来的性能和功能优势。
