"""
智能家居客服 - Strands Agent

本地运行: python agent.py test
部署到 AgentCore: agentcore launch
"""

from strands import Agent
from strands.models.bedrock import BedrockModel
from bedrock_agentcore.runtime import BedrockAgentCoreApp

# 导入配置
from config.settings import settings

# 导入工具
from tools.knowledge_base import query_aws_docs, query_robot_docs
from tools.device_control import (
    turn_on_light,
    turn_off_light,
    get_device_status,
    set_scene,
)


# ==================== Agent 配置 ====================

SYSTEM_PROMPT = """你是智能家居客服助手。

## 能力
1. 知识查询 - 查询 AWS EC2 或扫地机器人文档
2. 设备控制 - 控制灯光开关、亮度、场景

## 工具
- query_aws_docs: AWS EC2 相关问题
- query_robot_docs: 扫地机器人相关问题
- turn_on_light: 开灯
- turn_off_light: 关灯
- get_device_status: 查看设备状态
- set_scene: 设置场景模式

## 规则
- 用中文回复，简洁友好
- 知识库查询时，严格基于检索结果回答，不编造
- 设备控制后确认执行结果"""

TOOLS = [
    query_aws_docs,
    query_robot_docs,
    turn_on_light,
    turn_off_light,
    get_device_status,
    set_scene,
]


def create_agent() -> Agent:
    """创建 Agent"""
    model = BedrockModel(
        model_id=settings.model.model_id,
        region_name=settings.aws.region
    )
    return Agent(model=model, tools=TOOLS, system_prompt=SYSTEM_PROMPT)


# ==================== AgentCore Runtime ====================

app = BedrockAgentCoreApp()


@app.entrypoint
def invoke(payload: dict, context: dict) -> dict:
    """AgentCore 入口函数"""
    prompt = payload.get("prompt", "你好")
    agent = create_agent()
    result = agent(prompt)
    return {"response": str(result)}


# ==================== 本地运行 ====================

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        print("=" * 50)
        print("本地测试模式")
        print(f"模型: {settings.model.model_id}")
        print(f"区域: {settings.aws.region}")
        print("=" * 50)
        agent = create_agent()
        while True:
            try:
                user_input = input("\n你: ").strip()
                if user_input.lower() in ["quit", "exit", "/quit"]:
                    break
                response = agent(user_input)
                print(f"\n助手: {response}")
            except KeyboardInterrupt:
                break
        print("\n再见！")
    else:
        # 启动 AgentCore Runtime 服务
        app.run()
