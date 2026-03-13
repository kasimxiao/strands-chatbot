"""配置管理"""

import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


@dataclass
class AWSConfig:
    """AWS 配置"""
    region: str = field(default_factory=lambda: os.getenv("AWS_REGION", "us-east-1"))
    profile: str = field(default_factory=lambda: os.getenv("AWS_PROFILE", "default"))


@dataclass
class KnowledgeBaseConfig:
    """Knowledge Base 配置"""
    # AWS EC2 相关文档
    kb_aws: str = field(
        default_factory=lambda: os.getenv("KNOWLEDGE_BASE_ID_AWS", "KNWHSSCUVT")
    )
    # 扫地机器人文档
    kb_robot: str = field(
        default_factory=lambda: os.getenv("KNOWLEDGE_BASE_ID_ROBOT", "3KZDG0MTIV")
    )
    num_results: int = 5


@dataclass
class AgentCoreConfig:
    """AgentCore 配置"""
    agent_id: str = field(
        default_factory=lambda: os.getenv("AGENTCORE_AGENT_ID", "")
    )
    agent_alias_id: str = field(
        default_factory=lambda: os.getenv("AGENTCORE_AGENT_ALIAS_ID", "")
    )


@dataclass
class MemoryConfig:
    """Memory 配置"""
    enabled: bool = field(
        default_factory=lambda: os.getenv("AGENTCORE_MEMORY_ENABLED", "true").lower() == "true"
    )
    retention_days: int = field(
        default_factory=lambda: int(os.getenv("MEMORY_RETENTION_DAYS", "30"))
    )
    # 短期记忆：当前会话的滑动窗口大小
    short_term_window_size: int = 10


@dataclass
class ModelConfig:
    """模型配置"""
    model_id: str = field(
        default_factory=lambda: os.getenv(
            "MODEL_ID", "anthropic.claude-sonnet-4-20250514-v1:0"
        )
    )
    max_tokens: int = field(
        default_factory=lambda: int(os.getenv("MAX_TOKENS", "4096"))
    )
    streaming: bool = True


@dataclass
class Settings:
    """全局配置"""
    aws: AWSConfig = field(default_factory=AWSConfig)
    agentcore: AgentCoreConfig = field(default_factory=AgentCoreConfig)
    knowledge_base: KnowledgeBaseConfig = field(default_factory=KnowledgeBaseConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    model: ModelConfig = field(default_factory=ModelConfig)


settings = Settings()
