"""
Agent 执行轨迹事件工具

trace 事件用于向前端展示 Agent 做了什么、产出了什么，以及关键节点的可审计摘要。
它不包含模型隐藏推理，只输出业务操作轨迹。
"""

from collections.abc import Callable
from typing import Any

TraceItem = dict[str, str]


def emit_trace(
    writer: Callable[[dict[str, Any]], None],
    step: str,
    title: str,
    summary: str | None = None,
    items: list[TraceItem] | None = None,
    metadata: dict[str, Any] | None = None,
):
    """发送统一结构的 trace SSE 事件"""

    writer(
        {
            "type": "trace", # 事件类型
            "step": step, # 执行步骤
            "title": title, # 事件标题
            "summary": summary or "", # 事件摘要
            "items": items or [], # 事件详情
            "metadata": metadata or {}, # 事件元数据
        }
    )


def column_trace_items(column_infos: list[Any], limit: int = 5) -> list[TraceItem]:
    """把字段实体整理成前端可读的轨迹条目"""

    items: list[TraceItem] = []
    for column_info in column_infos[:limit]:
        table_id = _read_value(column_info, "table_id")
        name = _read_value(column_info, "name")
        description = _read_value(column_info, "description")
        label = f"{table_id}.{name}" if table_id else str(name)
        items.append({"label": label, "detail": str(description or "")})
    return items


def metric_trace_items(metric_infos: list[Any], limit: int = 5) -> list[TraceItem]:
    """把指标实体整理成前端可读的轨迹条目"""

    items: list[TraceItem] = []
    for metric_info in metric_infos[:limit]:
        items.append(
            {
                "label": str(_read_value(metric_info, "name")),
                "detail": str(_read_value(metric_info, "description") or ""),
            }
        )
    return items


def value_trace_items(value_infos: list[Any], limit: int = 5) -> list[TraceItem]:
    """把字段取值实体整理成前端可读的轨迹条目"""

    items: list[TraceItem] = []
    for value_info in value_infos[:limit]:
        items.append(
            {
                "label": str(_read_value(value_info, "value")),
                "detail": str(_read_value(value_info, "column_id") or ""),
            }
        )
    return items


def table_trace_items(
    table_infos: list[Any], limit: int = 5, column_limit: int = 4
) -> list[TraceItem]:
    """把表结构上下文整理成前端可读的轨迹条目"""

    items: list[TraceItem] = []
    for table_info in table_infos[:limit]:
        name = _read_value(table_info, "name")
        description = _read_value(table_info, "description")
        columns = _read_value(table_info, "columns") or []
        column_names = [
            str(_read_value(column, "name"))
            for column in columns[:column_limit]
            if _read_value(column, "name")
        ]
        column_summary = ", ".join(column_names)
        if len(columns) > column_limit:
            column_summary = f"{column_summary} 等 {len(columns)} 个字段"
        elif column_summary:
            column_summary = f"{column_summary}，共 {len(columns)} 个字段"

        detail_parts = [str(description or "")]
        if column_summary:
            detail_parts.append(f"字段：{column_summary}")

        items.append(
            {
                "label": str(name),
                "detail": "；".join(part for part in detail_parts if part),
            }
        )
    return items


def _read_value(item: Any, key: str) -> Any:
    if isinstance(item, dict):
        return item.get(key)
    return getattr(item, key, None)
