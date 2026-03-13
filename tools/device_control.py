"""设备控制工具 - 灯光控制等"""

from strands import tool
from typing import Literal
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class DeviceState:
    """设备状态管理（模拟）"""
    devices: dict = field(default_factory=lambda: {
        "living_room_light": {"name": "客厅灯", "status": "off", "brightness": 0},
        "bedroom_light": {"name": "卧室灯", "status": "off", "brightness": 0},
        "kitchen_light": {"name": "厨房灯", "status": "off", "brightness": 0},
        "bathroom_light": {"name": "浴室灯", "status": "off", "brightness": 0},
    })

    def get_device(self, device_id: str) -> dict | None:
        return self.devices.get(device_id)

    def set_status(self, device_id: str, status: str, brightness: int = 100):
        if device_id in self.devices:
            self.devices[device_id]["status"] = status
            self.devices[device_id]["brightness"] = brightness if status == "on" else 0
            return True
        return False


# 全局设备状态（实际应用中应连接 IoT 服务）
device_state = DeviceState()


DEVICE_ID_MAP = {
    "客厅": "living_room_light",
    "客厅灯": "living_room_light",
    "卧室": "bedroom_light",
    "卧室灯": "bedroom_light",
    "厨房": "kitchen_light",
    "厨房灯": "kitchen_light",
    "浴室": "bathroom_light",
    "浴室灯": "bathroom_light",
}


def resolve_device_id(location: str) -> str | None:
    """将用户输入的位置名称解析为设备 ID"""
    # 直接匹配
    if location in DEVICE_ID_MAP:
        return DEVICE_ID_MAP[location]
    # 尝试模糊匹配
    for key, device_id in DEVICE_ID_MAP.items():
        if key in location or location in key:
            return device_id
    return None


@tool
def turn_on_light(location: str, brightness: int = 100) -> str:
    """
    打开指定位置的灯。

    Args:
        location: 灯的位置，如 "客厅"、"卧室"、"厨房"、"浴室"
        brightness: 亮度百分比 (1-100)，默认 100

    Returns:
        操作结果消息
    """
    device_id = resolve_device_id(location)
    if not device_id:
        available = list(set(DEVICE_ID_MAP.keys()))
        return f"未找到位置 '{location}' 的灯。可用位置: {', '.join(available)}"

    device = device_state.get_device(device_id)
    if not device:
        return f"设备 {device_id} 不存在"

    brightness = max(1, min(100, brightness))  # 限制范围

    if device["status"] == "on":
        if device["brightness"] == brightness:
            return f"{device['name']}已经是开启状态，亮度 {brightness}%"
        device_state.set_status(device_id, "on", brightness)
        return f"已调整{device['name']}亮度至 {brightness}%"

    device_state.set_status(device_id, "on", brightness)
    return f"已打开{device['name']}，亮度 {brightness}%"


@tool
def turn_off_light(location: str) -> str:
    """
    关闭指定位置的灯。

    Args:
        location: 灯的位置，如 "客厅"、"卧室"、"厨房"、"浴室"

    Returns:
        操作结果消息
    """
    device_id = resolve_device_id(location)
    if not device_id:
        available = list(set(DEVICE_ID_MAP.keys()))
        return f"未找到位置 '{location}' 的灯。可用位置: {', '.join(available)}"

    device = device_state.get_device(device_id)
    if not device:
        return f"设备 {device_id} 不存在"

    if device["status"] == "off":
        return f"{device['name']}已经是关闭状态"

    device_state.set_status(device_id, "off")
    return f"已关闭{device['name']}"


@tool
def get_device_status(location: str | None = None) -> str:
    """
    获取设备状态。

    Args:
        location: 可选，指定位置。如果不指定则返回所有设备状态

    Returns:
        设备状态信息
    """
    if location:
        device_id = resolve_device_id(location)
        if not device_id:
            return f"未找到位置 '{location}' 的设备"

        device = device_state.get_device(device_id)
        if not device:
            return f"设备 {device_id} 不存在"

        status_text = "开启" if device["status"] == "on" else "关闭"
        if device["status"] == "on":
            return f"{device['name']}: {status_text}，亮度 {device['brightness']}%"
        return f"{device['name']}: {status_text}"

    # 返回所有设备状态
    lines = ["当前设备状态:"]
    for device_id, device in device_state.devices.items():
        status_text = "开启" if device["status"] == "on" else "关闭"
        if device["status"] == "on":
            lines.append(f"  - {device['name']}: {status_text}，亮度 {device['brightness']}%")
        else:
            lines.append(f"  - {device['name']}: {status_text}")

    return "\n".join(lines)


@tool
def set_scene(scene: Literal["日间", "夜间", "阅读", "影院", "全关"]) -> str:
    """
    设置场景模式，一键控制多个灯。

    Args:
        scene: 场景名称
            - 日间: 所有灯开启，亮度 100%
            - 夜间: 只开卧室灯，亮度 30%
            - 阅读: 客厅灯 80%，其他关闭
            - 影院: 所有灯关闭
            - 全关: 关闭所有灯

    Returns:
        场景设置结果
    """
    scene_configs = {
        "日间": {
            "living_room_light": ("on", 100),
            "bedroom_light": ("on", 100),
            "kitchen_light": ("on", 100),
            "bathroom_light": ("on", 100),
        },
        "夜间": {
            "living_room_light": ("off", 0),
            "bedroom_light": ("on", 30),
            "kitchen_light": ("off", 0),
            "bathroom_light": ("off", 0),
        },
        "阅读": {
            "living_room_light": ("on", 80),
            "bedroom_light": ("off", 0),
            "kitchen_light": ("off", 0),
            "bathroom_light": ("off", 0),
        },
        "影院": {
            "living_room_light": ("off", 0),
            "bedroom_light": ("off", 0),
            "kitchen_light": ("off", 0),
            "bathroom_light": ("off", 0),
        },
        "全关": {
            "living_room_light": ("off", 0),
            "bedroom_light": ("off", 0),
            "kitchen_light": ("off", 0),
            "bathroom_light": ("off", 0),
        },
    }

    config = scene_configs.get(scene)
    if not config:
        return f"未知场景: {scene}"

    for device_id, (status, brightness) in config.items():
        device_state.set_status(device_id, status, brightness)

    return f"已切换到「{scene}」模式"
