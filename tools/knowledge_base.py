"""
AWS Bedrock Knowledge Base 工具

支持两个知识库:
1. AWS KB: AWS EC2 相关文档
2. Robot KB: 扫地机器人文档
"""

import boto3
from strands import tool
from typing import Literal
from config.settings import settings


# 延迟初始化，避免冷启动超时
_bedrock_client = None


def get_bedrock_agent_runtime_client():
    """获取 Bedrock Agent Runtime 客户端（延迟初始化）"""
    global _bedrock_client
    if _bedrock_client is None:
        _bedrock_client = boto3.client(
            "bedrock-agent-runtime",
            region_name=settings.aws.region,
        )
    return _bedrock_client


@tool
def query_aws_docs(query: str, num_results: int = 5) -> str:
    """
    查询 AWS EC2 相关文档知识库。

    当用户询问 AWS、EC2、云服务器、实例类型、AMI、安全组、VPC 等相关问题时使用此工具。

    Args:
        query: 用户的查询问题
        num_results: 返回的结果数量，默认 5 条

    Returns:
        检索到的 AWS 相关知识内容
    """
    return _retrieve_from_kb(
        kb_id=settings.knowledge_base.kb_aws,
        query=query,
        num_results=num_results,
        kb_name="AWS EC2 文档"
    )


@tool
def query_robot_docs(query: str, num_results: int = 5) -> str:
    """
    查询扫地机器人文档知识库。

    当用户询问扫地机器人、吸尘器、清洁、拖地、充电、故障排除等相关问题时使用此工具。

    Args:
        query: 用户的查询问题
        num_results: 返回的结果数量，默认 5 条

    Returns:
        检索到的扫地机器人相关知识内容
    """
    return _retrieve_from_kb(
        kb_id=settings.knowledge_base.kb_robot,
        query=query,
        num_results=num_results,
        kb_name="扫地机器人文档"
    )


@tool
def search_knowledge(
    query: str,
    category: Literal["aws", "robot", "auto"] = "auto",
    num_results: int = 5
) -> str:
    """
    智能搜索知识库。

    根据问题类型自动选择合适的知识库，或手动指定类别。

    Args:
        query: 用户的查询问题
        category: 知识库类别
            - "aws": AWS EC2 相关文档
            - "robot": 扫地机器人文档
            - "auto": 自动根据问题内容选择
        num_results: 返回的结果数量，默认 5 条

    Returns:
        检索到的相关知识内容
    """
    if category == "auto":
        category = _detect_category(query)

    if category == "aws":
        return _retrieve_from_kb(
            kb_id=settings.knowledge_base.kb_aws,
            query=query,
            num_results=num_results,
            kb_name="AWS EC2 文档"
        )
    else:
        return _retrieve_from_kb(
            kb_id=settings.knowledge_base.kb_robot,
            query=query,
            num_results=num_results,
            kb_name="扫地机器人文档"
        )


def _detect_category(query: str) -> str:
    """根据查询内容检测知识库类别"""
    query_lower = query.lower()

    aws_keywords = [
        "aws", "ec2", "amazon", "云服务", "实例", "instance",
        "ami", "安全组", "security group", "vpc", "子网", "subnet",
        "ebs", "s3", "lambda", "iam", "弹性", "负载均衡", "elb",
        "auto scaling", "cloudwatch", "region", "可用区"
    ]

    robot_keywords = [
        "扫地机", "机器人", "吸尘", "拖地", "清洁", "充电",
        "尘盒", "滤网", "边刷", "主刷", "地图", "禁区",
        "定时", "噪音", "故障", "wifi", "app", "固件", "升级"
    ]

    aws_score = sum(1 for kw in aws_keywords if kw in query_lower)
    robot_score = sum(1 for kw in robot_keywords if kw in query_lower)

    if aws_score > robot_score:
        return "aws"
    elif robot_score > aws_score:
        return "robot"
    else:
        return "robot"  # 默认返回扫地机（智能家居场景）


def _retrieve_from_kb(kb_id: str, query: str, num_results: int, kb_name: str) -> str:
    """从指定知识库检索"""
    if not kb_id:
        return f"错误: {kb_name} 的 Knowledge Base ID 未配置"

    try:
        client = get_bedrock_agent_runtime_client()

        response = client.retrieve(
            knowledgeBaseId=kb_id,
            retrievalQuery={"text": query},
            retrievalConfiguration={
                "vectorSearchConfiguration": {
                    "numberOfResults": num_results
                }
            }
        )

        results = response.get("retrievalResults", [])

        if not results:
            return f"在 {kb_name} 中未找到与 '{query}' 相关的内容"

        formatted_results = [f"【{kb_name}】检索结果:\n"]
        for i, result in enumerate(results, 1):
            content = result.get("content", {})
            text = content.get("text", "无内容")
            score = result.get("score", 0)

            location = result.get("location", {})
            s3_location = location.get("s3Location", {})
            source = s3_location.get("uri", "未知来源")
            if source != "未知来源":
                source = source.split("/")[-1]

            formatted_results.append(
                f"[{i}] (相关度: {score:.2f})\n"
                f"来源: {source}\n"
                f"{text}\n"
            )

        return "\n---\n".join(formatted_results)

    except Exception as e:
        return f"{kb_name} 查询失败: {str(e)}"


@tool
def retrieve_knowledge(query: str, num_results: int = 5) -> str:
    """
    从知识库检索相关知识（自动选择知识库）。

    Args:
        query: 用户的查询问题
        num_results: 返回的结果数量，默认 5 条

    Returns:
        检索到的相关知识内容
    """
    return search_knowledge(query=query, category="auto", num_results=num_results)
