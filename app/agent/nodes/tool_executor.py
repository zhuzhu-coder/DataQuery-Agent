"""
工具执行节点

根据 Planner 生成的 tool_calls 调用 LangChain StructuredTool，
并把工具 observation 与召回结果写回 State
"""

from typing import Any

from langgraph.runtime import Runtime

from app.agent.context import DataQueryAgentContext
from app.agent.state import (
    AgentObservationState,
    DataQueryAgentState,
    ToolCallState,
    current_query,
)
from app.agent.tools import build_agent_tools, normalize_tool_calls
from app.agent.trace import (
    column_trace_items,
    emit_trace,
    metric_trace_items,
    value_trace_items,
)
from app.core.log import logger

TOOL_STEPS = {
    "recall_column": {
        "step": "召回字段信息",
        "result_key": "retrieved_column_infos",
        "count_key": "column_count",
        "trace_items": column_trace_items,
        "title": "命中 {count} 个相关字段",
        "summary": "围绕用户问题召回候选字段上下文。",
    },
    "recall_metric": {
        "step": "召回指标信息",
        "result_key": "retrieved_metric_infos",
        "count_key": "metric_count",
        "trace_items": metric_trace_items,
        "title": "命中 {count} 个相关指标",
        "summary": "将用户问题中的业务表达映射到系统内已定义指标。",
    },
    "recall_value": {
        "step": "召回字段取值",
        "result_key": "retrieved_value_infos",
        "count_key": "value_count",
        "trace_items": value_trace_items,
        "title": "命中 {count} 个字段取值",
        "summary": "从字段值索引中召回可能用于 WHERE 条件的真实业务取值。",
    },
}


async def tool_executor(
    state: DataQueryAgentState, runtime: Runtime[DataQueryAgentContext]
):
    """执行 Planner 产出的工具调用计划"""

    writer = runtime.stream_writer
    step = "执行工具"
    writer({"type": "progress", "step": step, "status": "running"})

    try:
        tools = build_agent_tools(runtime.context)
        tool_calls = normalize_tool_calls(
            (state.get("agent_plan") or {}).get("tool_calls")
        )

        updates: dict[str, Any] = {
            "retrieved_column_infos": [],
            "retrieved_metric_infos": [],
            "retrieved_value_infos": [],
            "agent_observations": [],
        }

        for tool_call in tool_calls:
            tool_name = str(tool_call["name"])
            tool = tools[tool_name]
            config = TOOL_STEPS[tool_name]
            tool_step = str(config["step"])
            writer({"type": "progress", "step": tool_step, "status": "running"})

            result = await tool.ainvoke(
                {
                    "query": current_query(state),
                    "keywords": state.get("keywords", []),
                    "hints": _hints_from_tool_call(tool_call),
                }
            )
            result_items = result.get(config["result_key"], [])
            updates[config["result_key"]] = _merge_by_id(
                updates[config["result_key"]], result_items
            )

            metadata = {
                **(result.get("metadata") or {}),
                "tool_call_id": tool_call["id"],
                "tool_name": tool_name,
                "reason": tool_call.get("reason", ""),
            }
            count = len(result_items)
            writer({"type": "progress", "step": tool_step, "status": "success"})
            emit_trace(
                writer,
                step=tool_step,
                title=str(config["title"]).format(count=count),
                summary=str(config["summary"]),
                items=config["trace_items"](result_items),
                metadata=metadata,
            )
            updates["agent_observations"].append(
                AgentObservationState(
                    tool=tool_name,
                    summary=str(result.get("summary") or f"{tool_name} 执行完成"),
                    metadata=metadata,
                )
            )

        writer({"type": "progress", "step": step, "status": "success"})
        emit_trace(
            writer,
            step=step,
            title=f"完成 {len(tool_calls)} 次工具调用",
            summary="根据 Planner 的工具调用计划完成受控召回工具执行。",
            metadata={
                "tool_names": [tool_call["name"] for tool_call in tool_calls],
                "tool_call_count": len(tool_calls),
            },
        )
        return updates
    except Exception as e:
        logger.error(f"{step} failed: {e}")
        writer({"type": "progress", "step": step, "status": "error"})
        raise

def _hints_from_tool_call(tool_call: ToolCallState) -> list[str]:
    """从工具调用中提取提示词"""
    args = tool_call.get("args") or {}
    hints = args.get("hints")
    return list(hints) if isinstance(hints, list) else []


def _merge_by_id(existing: list[Any], incoming: list[Any]) -> list[Any]:
    """合并两个列表，根据 ID 去重"""
    merged: list[Any] = []
    seen: set[str] = set()
    for item in [*existing, *incoming]:
        item_id = _read_id(item)
        if item_id in seen:
            continue
        seen.add(item_id)
        merged.append(item)
    return merged


def _read_id(item: Any) -> str:
    """从对象中读取 ID 字段"""
    if isinstance(item, dict):
        return str(item.get("id") or item)
    return str(getattr(item, "id", item))
