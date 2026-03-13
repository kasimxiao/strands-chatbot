"""
智能客服后端 API

云端模式 - 调用 AWS Bedrock AgentCore Runtime
设备状态通过解析 Agent 响应自动同步
"""

import re
import uuid
import json
import boto3
from datetime import datetime
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel


# ============ AgentCore 配置 ============

AGENT_RUNTIME_ARN = "arn:aws:bedrock-agentcore:us-east-1:671067840733:runtime/smart_home_assistant-nBHKspHdLI"
AWS_REGION = "us-east-1"

# boto3 客户端
agentcore_client = boto3.client('bedrock-agentcore', region_name=AWS_REGION)


# ============ 设备状态管理 ============

device_state = {
    "living_room_light": {"name": "客厅灯", "status": "off", "brightness": 0},
    "bedroom_light": {"name": "卧室灯", "status": "off", "brightness": 0},
    "kitchen_light": {"name": "厨房灯", "status": "off", "brightness": 0},
    "bathroom_light": {"name": "浴室灯", "status": "off", "brightness": 0},
}

LOCATION_MAP = {
    "客厅": "living_room_light",
    "卧室": "bedroom_light",
    "厨房": "kitchen_light",
    "浴室": "bathroom_light",
}

SCENE_CONFIG = {
    "日间": {"客厅": 100, "卧室": 100, "厨房": 100, "浴室": 100},
    "夜间": {"客厅": 0, "卧室": 30, "厨房": 0, "浴室": 0},
    "阅读": {"客厅": 80, "卧室": 0, "厨房": 0, "浴室": 0},
    "影院": {"客厅": 0, "卧室": 0, "厨房": 0, "浴室": 0},
    "全关": {"客厅": 0, "卧室": 0, "厨房": 0, "浴室": 0},
}


def parse_device_actions(response: str) -> list[dict]:
    """解析 Agent 响应中的设备控制动作"""
    actions = []

    # 先尝试提取亮度信息
    brightness_match = re.search(r'亮度[为：:\s]*(\d+)%?', response)
    default_brightness = int(brightness_match.group(1)) if brightness_match else 100

    # 匹配开灯: 多种表达方式 (位置只匹配:客厅/卧室/厨房/浴室)
    location_pattern = r"(客厅|卧室|厨房|浴室)"
    on_patterns = [
        rf"已(?:为您)?(?:成功)?打开{location_pattern}灯",
        rf"{location_pattern}灯已(?:为您|经|成功)?打开",
        rf"打开了{location_pattern}灯",
        rf"为您打开{location_pattern}灯",
    ]

    for pattern in on_patterns:
        for match in re.finditer(pattern, response):
            location = match.group(1)
            if not any(a.get("location") == location and a.get("action") == "on" for a in actions):
                actions.append({"action": "on", "location": location, "brightness": default_brightness})

    # 匹配关灯: 多种表达方式
    off_patterns = [
        rf"已(?:为您)?(?:成功)?关闭{location_pattern}灯",
        rf"{location_pattern}灯已(?:为您|经|成功)?关闭",
        rf"关闭了{location_pattern}灯",
    ]

    for pattern in off_patterns:
        for match in re.finditer(pattern, response):
            location = match.group(1)
            if not any(a.get("location") == location and a.get("action") == "off" for a in actions):
                actions.append({"action": "off", "location": location})

    # 匹配场景: 多种表达方式
    scene_patterns = [
        r"[「「]?(\S+?)[」」]?模式已(?:启用|设置|切换)",
        r"已(?:切换到|设置为|启用)[「「]?(\S+?)[」」]?模式",
        r"已(?:为您)?(?:切换|设置|启用)(?:到|为)?[「「]?(\S+?)[」」]?模式",
        r"切换到[「「]?(\S+?)[」」]?模式",
    ]

    for pattern in scene_patterns:
        match = re.search(pattern, response)
        if match:
            scene = match.group(1)
            actions.append({"action": "scene", "scene": scene})
            break  # 场景只取第一个匹配

    return actions


def apply_device_actions(actions: list[dict]) -> bool:
    """应用设备控制动作到本地状态"""
    changed = False

    for action in actions:
        if action["action"] == "on":
            device_id = LOCATION_MAP.get(action["location"])
            if device_id and device_id in device_state:
                device_state[device_id]["status"] = "on"
                device_state[device_id]["brightness"] = action.get("brightness", 100)
                changed = True

        elif action["action"] == "off":
            device_id = LOCATION_MAP.get(action["location"])
            if device_id and device_id in device_state:
                device_state[device_id]["status"] = "off"
                device_state[device_id]["brightness"] = 0
                changed = True

        elif action["action"] == "scene":
            scene = action["scene"]
            if scene in SCENE_CONFIG:
                for loc, brightness in SCENE_CONFIG[scene].items():
                    device_id = LOCATION_MAP.get(loc)
                    if device_id:
                        device_state[device_id]["status"] = "on" if brightness > 0 else "off"
                        device_state[device_id]["brightness"] = brightness
                changed = True

    return changed


# ============ 会话管理 ============

class UserSession:
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.session_id = str(uuid.uuid4())
        self.messages = []
        self.created_at = datetime.now()

    def chat(self, message: str) -> tuple[str, bool]:
        """调用 AgentCore Runtime，返回 (响应, 是否有设备变化)"""
        self.messages.append({"role": "user", "content": message})
        device_changed = False

        try:
            # 调用 AgentCore Runtime
            response = agentcore_client.invoke_agent_runtime(
                agentRuntimeArn=AGENT_RUNTIME_ARN,
                contentType='application/json',
                accept='application/json',
                payload=json.dumps({"prompt": message}).encode('utf-8')
            )

            # 读取响应
            response_body = response['response'].read()
            result = json.loads(response_body.decode('utf-8'))
            reply = result.get('response', str(result))

            # 解析并应用设备控制动作
            actions = parse_device_actions(reply)
            if actions:
                device_changed = apply_device_actions(actions)
                print(f"[设备同步] 检测到动作: {actions}, 状态已更新: {device_changed}")

        except Exception as e:
            reply = f"调用 AgentCore 失败: {e}"

        self.messages.append({"role": "assistant", "content": reply})
        return reply, device_changed

    def chat_stream(self, message: str):
        """流式调用（模拟），返回生成器和设备变化标志"""
        reply, device_changed = self.chat(message)

        # 先返回设备变化通知
        if device_changed:
            yield "[DEVICE_CHANGED]"

        # 逐字符返回
        for char in reply:
            yield char


user_sessions: dict[str, UserSession] = {}


def get_or_create_session(user_id: str) -> UserSession:
    if user_id not in user_sessions:
        user_sessions[user_id] = UserSession(user_id)
    return user_sessions[user_id]


# ============ FastAPI 应用 ============

@asynccontextmanager
async def lifespan(app: FastAPI):
    print(f"[API] 智能客服后端启动 (AgentCore 云端模式)")
    print(f"[API] Agent ARN: {AGENT_RUNTIME_ARN}")
    yield
    print("[API] 关闭")


app = FastAPI(
    title="智能客服 API",
    description="基于 AWS Bedrock AgentCore 的智能客服系统",
    version="6.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============ 数据模型 ============

class ChatRequest(BaseModel):
    user_id: str
    message: str


class ChatResponse(BaseModel):
    user_id: str
    session_id: str
    message: str
    response: str
    timestamp: str
    device_changed: bool = False


# ============ API 端点 ============

@app.get("/")
async def root():
    return {
        "message": "智能客服 API",
        "status": "running",
        "mode": "cloud (AgentCore Runtime)",
        "agent_arn": AGENT_RUNTIME_ARN,
        "version": "6.0.0",
    }


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """同步聊天"""
    session = get_or_create_session(request.user_id)
    device_changed = False

    try:
        reply, device_changed = session.chat(request.message)
    except Exception as e:
        reply = f"抱歉，处理请求时出错: {e}"

    return ChatResponse(
        user_id=request.user_id,
        session_id=session.session_id,
        message=request.message,
        response=reply,
        timestamp=datetime.now().isoformat(),
        device_changed=device_changed,
    )


@app.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """流式聊天"""
    session = get_or_create_session(request.user_id)

    async def generate():
        try:
            for chunk in session.chat_stream(request.message):
                if chunk == "[DEVICE_CHANGED]":
                    yield f"data: [DEVICE_CHANGED]\n\n"
                else:
                    escaped = chunk.replace('\n', '\\n')
                    yield f"data: {escaped}\n\n"
        except Exception as e:
            yield f"data: [错误] {e}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
    )


# ============ 用户 API ============

@app.get("/users")
async def list_users():
    return {"users": [
        {
            "user_id": uid,
            "session_id": s.session_id,
            "created_at": s.created_at.isoformat(),
            "message_count": len(s.messages),
        }
        for uid, s in user_sessions.items()
    ]}


@app.get("/users/{user_id}/history")
async def get_chat_history(user_id: str):
    session = get_or_create_session(user_id)
    return {
        "user_id": user_id,
        "session_id": session.session_id,
        "history": session.messages,
    }


@app.post("/users/{user_id}/new-session")
async def new_session(user_id: str):
    """创建新会话"""
    user_sessions[user_id] = UserSession(user_id)
    return {
        "user_id": user_id,
        "session_id": user_sessions[user_id].session_id,
        "message": "新会话已创建",
    }


@app.get("/users/{user_id}/memory")
async def get_memory(user_id: str):
    """获取用户记忆信息"""
    session = get_or_create_session(user_id)
    return {
        "user_id": user_id,
        "session_id": session.session_id,
        "short_term_count": len(session.messages),
        "long_term_count": 0,
        "memory_enabled": False,
    }


@app.delete("/users/{user_id}/memory")
async def clear_memory(user_id: str):
    """清除用户记忆"""
    session = get_or_create_session(user_id)
    session.messages = []
    return {"message": "记忆已清除"}


@app.get("/users/{user_id}/memory/stats")
async def get_memory_stats(user_id: str):
    """获取记忆统计"""
    session = get_or_create_session(user_id)
    return {
        "short_term_count": len(session.messages),
        "long_term_count": 0,
        "total_tokens": 0,
    }


@app.post("/users/{user_id}/end-session")
async def end_session(user_id: str):
    """结束会话"""
    if user_id in user_sessions:
        del user_sessions[user_id]
    return {"message": "会话已结束"}


# ============ 设备 API ============

@app.get("/devices")
async def get_devices():
    """获取设备状态"""
    return {"devices": device_state}


@app.post("/devices/{location}/on")
async def turn_device_on(location: str, brightness: int = 100):
    """手动开灯"""
    device_id = LOCATION_MAP.get(location)
    if device_id and device_id in device_state:
        device_state[device_id]["status"] = "on"
        device_state[device_id]["brightness"] = brightness
    return {"message": f"已打开{location}灯", "devices": device_state}


@app.post("/devices/{location}/off")
async def turn_device_off(location: str):
    """手动关灯"""
    device_id = LOCATION_MAP.get(location)
    if device_id and device_id in device_state:
        device_state[device_id]["status"] = "off"
        device_state[device_id]["brightness"] = 0
    return {"message": f"已关闭{location}灯", "devices": device_state}


@app.post("/devices/scene/{scene}")
async def set_device_scene(scene: str):
    """设置场景"""
    if scene in SCENE_CONFIG:
        for loc, brightness in SCENE_CONFIG[scene].items():
            device_id = LOCATION_MAP.get(loc)
            if device_id:
                device_state[device_id]["status"] = "on" if brightness > 0 else "off"
                device_state[device_id]["brightness"] = brightness
    return {"message": f"已设置{scene}模式", "devices": device_state}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
