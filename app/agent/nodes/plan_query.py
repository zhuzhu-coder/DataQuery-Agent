"""
查询规划节点

在确认用户意图是数据查询后，先让模型生成当前任务的结构化计划
本节点只负责计划，不召回、不生成 SQL，也不改变后续安全边界
"""

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate
from langgraph.runtime import Runtime

from app.agent.context import DataQueryAgentContext
from app.agent.llm import llm
from app.agent.observations import observation_update
from app.agent.state import AgentPlanState, DataQueryAgentState, ToolCallState
from app.agent.tools import available_tool_names, render_tool_specs
from app.agent.trace import emit_trace
from app.core.log import logger
from app.prompt.prompt_loader import load_prompt


async def plan_query(state: DataQueryAgentState, runtime: Runtime[DataQueryAgentContext]):
    """为本次数据查询生成结构化执行计划"""

    writer = runtime.stream_writer
    step = "制定查询计划"
    writer({"type": "progress", "step": step, "status": "running"})

    query = state["query"]
    try:
        try:
            raw_plan = await _plan_with_llm(query)
            agent_plan = _normalize_plan(raw_plan, query)
        except Exception as e:
            logger.warning(f"{step} failed, fallback to full recall: {e}")
            agent_plan = _fallback_plan(query)

        writer({"type": "progress", "step": step, "status": "success"})
        emit_trace(
            writer,
            step=step,
            title="完成查询计划",
            summary=agent_plan.get("reason", ""),
            items=[
                {"label": "目标", "detail": agent_plan.get("goal_summary", query)},
                {
                    "label": "工具",
                    "detail": ", ".join(_tool_names(agent_plan)),
                },
            ],
            metadata={
                "tool_names": _tool_names(agent_plan),
                "tool_call_count": len(agent_plan.get("tool_calls", [])),
                "need_clarification": agent_plan.get("need_clarification", False),
            },
        )
        return {
            "agent_plan": agent_plan,
            **observation_update(
                "plan_query",
                f"制定查询计划，选择工具：{', '.join(_tool_names(agent_plan))}",
                {
                    "goal_summary": agent_plan.get("goal_summary", query),
                    "tool_names": _tool_names(agent_plan),
                    "tool_call_count": len(agent_plan.get("tool_calls", [])),
                    "need_clarification": agent_plan.get(
                        "need_clarification", False
                    ),
                },
            ),
        }
    except Exception as e:
        logger.error(f"{step} failed: {e}")
        writer({"type": "progress", "step": step, "status": "error"})
        raise


async def _plan_with_llm(query: str) -> dict:
    """调用模型生成查询计划"""

    prompt = PromptTemplate(
        template=load_prompt("plan_query"),
        input_variables=["query", "tools"],
    )
    chain = prompt | llm | JsonOutputParser()
    return await chain.ainvoke({"query": query, "tools": render_tool_specs()})


def _normalize_plan(payload: object, query: str) -> AgentPlanState:
    """把模型输出规范化成稳定的 Planner State"""

    if not isinstance(payload, dict):
        raise ValueError("查询计划必须是 JSON 对象")
    
    
    tool_calls = _normalize_tool_calls(payload.get("tool_calls"))

    return AgentPlanState(
        goal_summary=str(payload.get("goal_summary") or query),
        metrics=_string_list(payload.get("metrics")),
        dimensions=_string_list(payload.get("dimensions")),
        filters=_string_list(payload.get("filters")),
        tool_calls=tool_calls,
        need_clarification=bool(payload.get("need_clarification", False)),
        clarification_question=str(payload.get("clarification_question") or ""),
        reason=str(payload.get("reason") or "已生成查询计划。"),
    )


def _fallback_plan(query: str) -> AgentPlanState:
    """Planner 失败时使用保守计划，保证旧链路可继续执行"""

    return AgentPlanState(
        goal_summary=query,
        metrics=[],
        dimensions=[],
        filters=[],
        tool_calls=_default_tool_calls(),
        need_clarification=False,
        clarification_question="",
        reason="Planner 输出不可用，使用三路召回兜底计划。",
    )


def _string_list(value: object) -> list[str]:
    """把对象转换为字符串列表，空值返回空列表"""
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item is not None]


def _normalize_tool_calls(value: object) -> list[ToolCallState]:
    """规范化 Planner 输出的工具调用计划"""

    if not isinstance(value, list):
        return _default_tool_calls()

    allowed_tool_names = set(available_tool_names())
    tool_calls: list[ToolCallState] = []
    seen_tool_names: set[str] = set()
    for item in value:
        if not isinstance(item, dict):
            continue
        tool_name = str(item.get("name") or "")
        if tool_name not in allowed_tool_names or tool_name in seen_tool_names:
            continue
        seen_tool_names.add(tool_name)
        args = item.get("args") if isinstance(item.get("args"), dict) else {}
        tool_calls.append(
            ToolCallState(
                id=str(item.get("id") or f"tool_{len(tool_calls) + 1}"),
                name=tool_name,
                args={"hints": _string_list(args.get("hints"))},
                reason=str(item.get("reason") or ""),
            )
        )

    return tool_calls or _default_tool_calls()


def _default_tool_calls() -> list[ToolCallState]:
    """Planner 输出不可用时，保守调用所有召回工具"""

    return [
        ToolCallState(
            id=f"tool_{index}",
            name=tool_name,
            args={"hints": []},
            reason="Planner 未给出有效工具调用，使用三路召回兜底。",
        )
        for index, tool_name in enumerate(available_tool_names(), start=1)
    ]


def _tool_names(agent_plan: AgentPlanState) -> list[str]:
    """从工具调用计划派生工具名列表"""

    return [
        str(tool_call.get("name"))
        for tool_call in agent_plan.get("tool_calls", [])
        if tool_call.get("name")
    ]
