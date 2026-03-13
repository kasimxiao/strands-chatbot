"""
Memory Manager - 基于 AWS Bedrock AgentCore 内置记忆

AgentCore Memory 工作原理:
1. 短期记忆: 同一 sessionId 内自动保持上下文
2. 长期记忆: 会话结束时 AgentCore 自动生成摘要，下次会话自动加载

关键参数:
- sessionId: 当前会话标识（同一会话保持相同）
- memoryId: 用户标识（同一用户保持相同，用于跨会话记忆）
- endSession: 设为 true 时触发 Memory Summarization
"""

import uuid
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional

import boto3
from botocore.exceptions import ClientError
from config.settings import settings


@dataclass
class Message:
    """对话消息"""
    role: str  # "user" | "assistant"
    content: str
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
        }


class ShortTermMemory:
    """
    短期记忆 - 当前会话的对话历史（本地缓存，用于 UI 显示）

    实际的短期记忆由 AgentCore 通过 sessionId 自动管理
    """

    def __init__(self, window_size: int = 10):
        self.window_size = window_size
        self.messages: list[Message] = []

    def add(self, role: str, content: str):
        """添加消息"""
        self.messages.append(Message(role=role, content=content))
        max_messages = self.window_size * 2
        if len(self.messages) > max_messages:
            self.messages = self.messages[-max_messages:]

    def get_history(self) -> list[dict]:
        """获取对话历史（Bedrock Converse API 格式）"""
        return [{"role": m.role, "content": [{"text": m.content.strip()}]} for m in self.messages]

    def clear(self):
        """清空"""
        self.messages = []

    def to_text(self) -> str:
        """转换为文本"""
        lines = []
        for m in self.messages:
            role_name = "用户" if m.role == "user" else "助手"
            lines.append(f"{role_name}: {m.content}")
        return "\n".join(lines)


class AgentCoreMemory:
    """
    AgentCore 内置长期记忆

    存储位置: AWS Bedrock 托管服务（按 memoryId 隔离）
    自动功能:
    - 会话结束时自动生成摘要
    - 新会话开始时自动加载历史摘要
    - 自动管理过期和清理
    """

    def __init__(self, memory_id: str):
        self.memory_id = memory_id
        self.client = boto3.client(
            "bedrock-agent-runtime",
            region_name=settings.aws.region,
        )

    def get_memory_contents(self) -> list[dict]:
        """
        获取 AgentCore 存储的长期记忆内容

        Returns:
            会话摘要列表
        """
        try:
            response = self.client.get_agent_memory(
                agentId=settings.agentcore.agent_id,
                agentAliasId=settings.agentcore.agent_alias_id,
                memoryId=self.memory_id,
                memoryType="SESSION_SUMMARY",
            )
            return response.get("memoryContents", [])
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            if error_code == "ResourceNotFoundException":
                return []
            print(f"[AgentCore] 获取记忆失败: {e}")
            return []
        except Exception as e:
            print(f"[AgentCore] 获取记忆失败: {e}")
            return []

    def get_summaries(self) -> list[dict]:
        """获取会话摘要列表"""
        contents = self.get_memory_contents()
        summaries = []
        for content in contents:
            session_summary = content.get("sessionSummary", {})
            if session_summary:
                summaries.append({
                    "session_id": session_summary.get("sessionId", ""),
                    "summary": session_summary.get("summaryText", ""),
                    "created_at": session_summary.get("sessionStartTime", ""),
                    "expires_at": session_summary.get("sessionExpiryTime", ""),
                })
        return summaries

    def get_context(self) -> str:
        """获取长期记忆上下文（用于显示）"""
        summaries = self.get_summaries()
        if not summaries:
            return ""

        lines = ["以下是之前的对话摘要:"]
        for i, s in enumerate(summaries[-5:], 1):
            lines.append(f"\n[会话 {i}]")
            lines.append(f"摘要: {s['summary']}")

        return "\n".join(lines)

    def delete_memory(self) -> bool:
        """删除该用户的所有记忆"""
        try:
            self.client.delete_agent_memory(
                agentId=settings.agentcore.agent_id,
                agentAliasId=settings.agentcore.agent_alias_id,
                memoryId=self.memory_id,
            )
            print(f"[AgentCore] 已删除 {self.memory_id} 的记忆")
            return True
        except Exception as e:
            print(f"[AgentCore] 删除记忆失败: {e}")
            return False

    def get_stats(self) -> dict:
        """获取记忆统计"""
        summaries = self.get_summaries()
        return {
            "total_count": len(summaries),
            "oldest": summaries[0]["created_at"] if summaries else None,
            "newest": summaries[-1]["created_at"] if summaries else None,
            "retention_days": settings.memory.retention_days,
        }


class MemoryManager:
    """
    Memory 管理器 - 封装 AgentCore Memory

    使用方式:
    ```python
    memory = MemoryManager(user_id="user123")

    # 开始会话
    session_id = memory.start_session()

    # 调用 Agent 时传入 session_id 和 memory_id
    response = bedrock_agent_runtime.invoke_agent(
        agentId=AGENT_ID,
        agentAliasId=ALIAS_ID,
        sessionId=session_id,
        memoryId=memory.user_id,  # memory_id = user_id
        inputText="你好"
    )

    # 结束会话（触发摘要生成）
    response = bedrock_agent_runtime.invoke_agent(
        ...
        endSession=True
    )
    ```
    """

    def __init__(self, user_id: str, session_id: Optional[str] = None):
        self.user_id = user_id
        self.session_id = session_id or str(uuid.uuid4())

        # 短期记忆（本地缓存，用于 UI）
        self.short_term = ShortTermMemory(
            window_size=settings.memory.short_term_window_size
        )

        # 长期记忆（AgentCore 托管）
        self.long_term = AgentCoreMemory(memory_id=user_id)

    def start_session(self, session_id: Optional[str] = None) -> str:
        """
        开始新会话

        Returns:
            新的 session_id
        """
        self.session_id = session_id or str(uuid.uuid4())
        self.short_term.clear()
        print(f"[Memory] 新会话: {self.session_id}")
        return self.session_id

    def add_message(self, role: str, content: str):
        """添加消息到短期记忆（本地缓存）"""
        self.short_term.add(role, content)

    def get_short_term_history(self) -> list[dict]:
        """获取短期记忆"""
        return self.short_term.get_history()

    def get_long_term_context(self) -> str:
        """获取长期记忆上下文"""
        return self.long_term.get_context()

    def get_long_term_summaries(self) -> list[dict]:
        """获取长期记忆摘要列表"""
        return self.long_term.get_summaries()

    def clear_all(self):
        """清空所有记忆"""
        self.short_term.clear()
        self.long_term.delete_memory()

    def get_invoke_params(self, end_session: bool = False) -> dict:
        """
        获取调用 AgentCore 的参数

        Returns:
            包含 sessionId, memoryId, endSession 的字典
        """
        return {
            "sessionId": self.session_id,
            "memoryId": self.user_id,
            "endSession": end_session,
        }
