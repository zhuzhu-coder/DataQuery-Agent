"""
查询上下文过滤节点

负责在合并后的候选表结构和指标集合中，筛选出当前问题真正需要的表、字段和指标。
模型只返回选择结果，真正的结构裁剪仍由程序完成，避免模型重写复杂上下文。
"""

from typing import Any

import yaml
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate
from langgraph.runtime import Runtime

from app.agent.context import DataQueryAgentContext
from app.agent.llm import llm
from app.agent.state import (
    ColumnInfoState,
    DataQueryAgentState,
    MetricInfoState,
    TableInfoState,
    current_query,
)
from app.agent.trace import emit_trace, metric_trace_items, table_trace_items
from app.core.log import logger
from app.prompt.prompt_loader import load_prompt


async def filter_query_context(
    state: DataQueryAgentState, runtime: Runtime[DataQueryAgentContext]
):
    """根据用户问题裁剪候选表字段和指标上下文"""

    writer = runtime.stream_writer
    step = "过滤查询上下文"
    writer({"type": "progress", "step": step, "status": "running"})

    try:
        query = current_query(state)
        table_infos: list[TableInfoState] = state.get("table_infos", [])
        metric_infos: list[MetricInfoState] = state.get("metric_infos", [])

        result = await _filter_with_llm(query, table_infos, metric_infos)
        filtered_table_infos = _filter_tables(table_infos, result)
        filtered_metric_infos = _filter_metrics(metric_infos, result)

        logger.info(
            f"过滤后的表信息：{[table_info['name'] for table_info in filtered_table_infos]}"
        )
        logger.info(
            f"过滤后的指标信息：{[metric_info['name'] for metric_info in filtered_metric_infos]}"
        )

        column_count = sum(
            len(filtered_table_info["columns"])
            for filtered_table_info in filtered_table_infos
        )
        writer({"type": "progress", "step": step, "status": "success"})
        emit_trace(
            writer,
            step=step,
            title=(
                f"保留 {len(filtered_table_infos)} 张表、"
                f"{column_count} 个字段、{len(filtered_metric_infos)} 个指标"
            ),
            summary="从候选上下文中裁剪出 SQL 生成真正需要的表、字段和指标。",
            items=[
                *table_trace_items(filtered_table_infos),
                *metric_trace_items(filtered_metric_infos),
            ],
            metadata={
                "table_count": len(filtered_table_infos),
                "field_count": column_count,
                "metric_count": len(filtered_metric_infos),
            },
        )
        return {
            "table_infos": filtered_table_infos,
            "metric_infos": filtered_metric_infos,
        }
    except Exception as e:
        logger.error(f"{step} failed: {e}")
        writer({"type": "progress", "step": step, "status": "error"})
        raise


async def _filter_with_llm(
    query: str,
    table_infos: list[TableInfoState],
    metric_infos: list[MetricInfoState],
) -> dict[str, Any]:
    """调用模型选择本次查询需要保留的表字段和指标"""

    prompt = PromptTemplate(
        template=load_prompt("filter_query_context"),
        input_variables=["query", "table_infos", "metric_infos"],
    )
    chain = prompt | llm | JsonOutputParser()
    return await chain.ainvoke(
        {
            "query": query,
            "table_infos": yaml.dump(
                table_infos,
                allow_unicode=True,
                sort_keys=False,
            ),
            "metric_infos": yaml.dump(
                metric_infos,
                allow_unicode=True,
                sort_keys=False,
            ),
        }
    )


def _filter_tables(
    table_infos: list[TableInfoState], result: object
) -> list[TableInfoState]:
    """按模型选择结果裁剪表字段，忽略候选外表和字段"""

    if not isinstance(result, dict):
        return []
    selected_tables = result.get("tables")
    if not isinstance(selected_tables, dict):
        return []

    filtered_table_infos: list[TableInfoState] = []
    for table_info in table_infos:
        table_name = table_info["name"]
        # 选中的字段
        selected_columns = selected_tables.get(table_name)
        # 没选中该表，跳过
        if not isinstance(selected_columns, list):
            continue
        # 选中的字段名称
        selected_column_names = {
            str(column_name) for column_name in selected_columns if column_name is not None
        }
        # 过滤出选中的字段上下文
        columns = [
            _copy_column_info(column_info)
            for column_info in table_info["columns"]
            if column_info["name"] in selected_column_names
        ]
        if not columns:
            continue
        filtered_table_infos.append(
            TableInfoState(
                name=table_info["name"],
                role=table_info["role"],
                description=table_info["description"],
                columns=columns,
            )
        )

    return filtered_table_infos


def _filter_metrics(
    metric_infos: list[MetricInfoState], result: object
) -> list[MetricInfoState]:
    """按模型选择结果裁剪指标，忽略候选外指标"""

    if not isinstance(result, dict):
        return []
    # 选中的指标
    selected_metrics = result.get("metrics")
    # 没选中任何指标，返回空列表
    if not isinstance(selected_metrics, list):
        return []
    # 选中的指标名称
    selected_metric_names = {
        str(metric_name) for metric_name in selected_metrics if metric_name is not None
    }
    # 过滤出选中的指标上下文
    return [
        MetricInfoState(
            name=metric_info["name"],
            description=metric_info["description"],
            relevant_columns=list(metric_info["relevant_columns"]),
            alias=list(metric_info["alias"]),
        )
        for metric_info in metric_infos
        if metric_info["name"] in selected_metric_names
    ]


def _copy_column_info(column_info: ColumnInfoState) -> ColumnInfoState:
    """复制字段上下文，避免过滤节点原地修改候选结构"""

    return ColumnInfoState(
        name=column_info["name"],
        type=column_info["type"],
        role=column_info["role"],
        examples=list(column_info["examples"]),
        description=column_info["description"],
        alias=list(column_info["alias"]),
    )
