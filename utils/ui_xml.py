import os
import pkg_resources
import uiautomator2 as u2


def get_emulator_ui_xml(prefix: str, save_dir: str, emulator_device: str = "emulator-5554") -> str:
    """
    连接 Android Studio 模拟器，获取含 View 类型的 UI XML（适配所有 uiautomator2 版本）
    :param prefix: XML 保存前缀
    :param save_path: XML 保存路径
    :param emulator_device: 模拟器设备名（通过 adb devices 查看，默认 emulator-5554）
    :return: UI XML 文件路径
    """
    # 1. 连接模拟器（核心：指定模拟器设备名）
    try:
        d = u2.connect(emulator_device)  # 适配模拟器的连接方式
    except Exception as e:
        raise RuntimeError(f"连接模拟器失败：{e}\n请检查：1.模拟器是否启动 2.adb devices 是否能识别模拟器")
    
    # 2. 检查模拟器连接状态（适配 uiautomator2 新旧版本）
    try:
        # 优先尝试新版方法 is_alive()
        if not d.is_alive():
            raise RuntimeError("模拟器连接失败，请确认模拟器已启动且 adb 能识别")
    except AttributeError:
        # 兼容旧版 alive 属性
        try:
            if not d.alive:
                raise RuntimeError("模拟器连接失败，请确认模拟器已启动且 adb 能识别")
        except AttributeError:
            # 终极兜底：通过获取设备信息检查连接
            try:
                d.device_info  # 调用设备信息，触发连接检查
            except Exception as e:
                raise RuntimeError(f"设备连接检查失败：{e}")
    
    # 3. 获取包含 View 类型的 UI 层级（dump_hierarchy 返回完整 XML，含 class 属性）
    try:
        ui_xml = d.dump_hierarchy()
    except Exception as e:
        raise RuntimeError(f"获取 UI 层级失败：{e}\n可能原因：模拟器未授权 ATX 应用，或 adb 权限不足")
    
    save_path = os.path.join(save_dir, f"{prefix}_ui.xml")
    try:
        # 4. 保存 XML 到本地
        with open(save_path, "w", encoding="utf-8") as f:
            f.write(ui_xml)
    except Exception as e:
        raise RuntimeError(f"保存 UI XML 失败：{e}")    

    return save_path




# ========== 主执行逻辑 ==========
if __name__ == "__main__":
    # 可选：查看当前 uiautomator2 版本（便于排查问题）
    try:
        u2_version = pkg_resources.get_distribution("uiautomator2").version
        print(f"当前 uiautomator2 版本：{u2_version}")
    except:
        print("无法获取 uiautomator2 版本")
    
    # 1. 连接模拟器，获取 XML（设备名默认 emulator-5554，可根据 adb devices 结果修改）
    xml_path = "tests"
    get_emulator_ui_xml(emulator_device="emulator-5554", save_dir=xml_path, prefix="test")