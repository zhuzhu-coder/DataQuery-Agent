"""
召回类 Agent 工具核心逻辑

这些函数只负责执行检索并返回结构化结果，不直接写 progress 或 trace
LangGraph 节点和 StructuredTool 都复用这里的实现
"""

from typing import Any, TypedDict

from app.agent.context import DataQueryAgentContext
from app.core.log import logger
from app.entities.column_info import ColumnInfo
from app.entities.metric_info import MetricInfo
from app.entities.value_info import ValueInfo


class RecallToolResult(TypedDict, total=False):
    """召回工具返回结果"""

    retrieved_column_infos: list[ColumnInfo]
    retrieved_metric_infos: list[MetricInfo]
    retrieved_value_infos: list[ValueInfo]
    summary: str
    metadata: dict[str, Any]


async def run_recall_column(
    keywords: list[str],
    hints: list[str],
    context: DataQueryAgentContext,
) -> RecallToolResult:
    """
    召回和用户问题语义相关的字段元数据
    Args:
        keywords: 关键词
        hints: 提示
        context: 运行时依赖
    Returns:
        召回结果
    """

    search_keywords = _merge_keywords(keywords, hints)
    column_vector_repository = context["column_vector_repository"]
    embedding_client = context["embedding_client"]
    # 初始化空字典，用于存储召回的字段信息
    column_info_map: dict[str, ColumnInfo] = {}
    for keyword in search_keywords:
        try:
            embedding = await embedding_client.aembed_query(keyword)
            current_column_infos: list[
                ColumnInfo
            ] = await column_vector_repository.search(embedding)
        except Exception as e:
            logger.warning(f"召回字段时出错 {keyword!r}: {e}")
            continue
        for column_info in current_column_infos:
            if column_info.id not in column_info_map:
                column_info_map[column_info.id] = column_info

    retrieved_column_infos = list(column_info_map.values())
    return {
        "retrieved_column_infos": retrieved_column_infos, # 召回的字段信息
        "summary": f"召回 {len(retrieved_column_infos)} 个候选字段",
        "metadata": {
            "column_count": len(retrieved_column_infos), # 召回的字段数量
            "keyword_count": len(search_keywords), # 搜索关键词数量
        },
    }


async def run_recall_metric(
    keywords: list[str],
    hints: list[str],
    context: DataQueryAgentContext,
) -> RecallToolResult:
    """
    召回和用户问题语义相关的业务指标
    Args:
        keywords: 关键词
        hints: 提示
        context: 运行时依赖
    Returns:
        召回结果
    """

    search_keywords = _merge_keywords(keywords, hints)
    embedding_client = context["embedding_client"]
    metric_vector_repository = context["metric_vector_repository"]

    metric_info_map: dict[str, MetricInfo] = {}
    for keyword in search_keywords:
        try:
            embedding = await embedding_client.aembed_query(keyword)
            current_metric_infos: list[
                MetricInfo
            ] = await metric_vector_repository.search(embedding)
        except Exception as e:
            logger.warning(f"召回指标时出错 {keyword!r}: {e}")
            continue
        for metric_info in current_metric_infos:
            if metric_info.id not in metric_info_map:
                metric_info_map[metric_info.id] = metric_info

    retrieved_metric_infos = list(metric_info_map.values())
    logger.info(f"检索到指标信息：{list(metric_info_map.keys())}")
    return {
        "retrieved_metric_infos": retrieved_metric_infos, # 召回的指标信息
        "summary": f"召回 {len(retrieved_metric_infos)} 个候选指标",
        "metadata": {
            "metric_count": len(retrieved_metric_infos), # 召回的指标数量
            "keyword_count": len(search_keywords), # 搜索关键词数量
        },
    }


async def run_recall_value(
    keywords: list[str],
    hints: list[str],
    context: DataQueryAgentContext,
) -> RecallToolResult:
    """
    召回和用户问题相关的字段取值
    Args:
        keywords: 关键词
        hints: 提示
        context: 运行时依赖
    Returns:
        召回结果
    """

    search_keywords = _merge_keywords(keywords, hints)
    value_es_repository = context["value_es_repository"]

    value_infos_map: dict[str, ValueInfo] = {}
    for keyword in search_keywords:
        try:
            current_value_infos: list[ValueInfo] = await value_es_repository.search(
                keyword
            )
        except Exception as e:
            logger.warning(f"recall_value skipped keyword {keyword!r}: {e}")
            continue
        # 过滤出字段取值
        for current_value_info in current_value_infos:
            if current_value_info.id not in value_infos_map:
                value_infos_map[current_value_info.id] = current_value_info

    retrieved_value_infos = list(value_infos_map.values())
    logger.info(f"检索到字段取值：{list(value_infos_map.keys())}")
    return {
        "retrieved_value_infos": retrieved_value_infos, # 召回的字段取值信息
        "summary": f"召回 {len(retrieved_value_infos)} 个候选字段取值",
        "metadata": {
            "value_count": len(retrieved_value_infos), # 召回的字段取值数量
            "keyword_count": len(search_keywords), # 搜索关键词数量
        },
    }


def _merge_keywords(
    keywords: list[str],
    hints: list[str],
) -> list[str]:
    """合并原始关键词和提示并去重保序"""

    merged: list[str] = []
    seen: set[str] = set()
    for value in [*keywords, *hints]:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        merged.append(text)
    return merged
