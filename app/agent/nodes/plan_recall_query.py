"""
查询规划与召回策略节点

在确认用户意图是数据查询后，一次性生成当前任务的结构化计划和召回 hints。
后续召回工具只消费关键词抽取结果与这里产出的 hints，不再各自调用 LLM 扩词。
"""

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate
from langgraph.runtime import Runtime

from app.agent.context import DataQueryAgentContext
from app.agent.llm import llm
from app.agent.state import (
    AgentPlanState,
    DataQueryAgentState,
    ToolCallState,
    current_query,
)
from app.agent.tools import default_tool_calls, normalize_tool_calls, render_tool_specs
from app.agent.trace import emit_trace
from app.core.log import logger
from app.prompt.prompt_loader import load_prompt


async def plan_recall_query(
    state: DataQueryAgentState, runtime: Runtime[DataQueryAgentContext]
):
    """为本次数据查询生成结构化执行计划和召回策略"""

    writer = runtime.stream_writer
    step = "规划召回策略"
    writer({"type": "progress", "step": step, "status": "running"})

    query = current_query(state)
    try:
        try:
            raw_plan = await _plan_recall_with_llm(query)
            agent_plan: AgentPlanState = _normalize_plan(raw_plan, query)
        except Exception as e:
            logger.warning(f"{step} 失败，回退到全部工具： {e}")
            agent_plan = _fallback_plan(query)

        tool_names = _tool_names(agent_plan)
        writer({"type": "progress", "step": step, "status": "success"})
        emit_trace(
            writer,
            step=step,
            title="完成召回策略规划",
            summary="已选择本次查询需要执行的召回工具。",
            items=[
                {"label": "目标", "detail": agent_plan.get("goal_summary", query)},
                {
                    "label": "工具",
                    "detail": ", ".join(tool_names),
                },
            ],
            metadata={
                "tool_names": tool_names,
                "tool_call_count": len(agent_plan.get("tool_calls", [])),
                "need_clarification": agent_plan.get("need_clarification", False),
            },
        )
        return {
            "agent_plan": agent_plan,
        }
    except Exception as e:
        logger.error(f"{step} failed: {e}")
        writer({"type": "progress", "step": step, "status": "error"})
        raise


async def _plan_recall_with_llm(query: str) -> dict:
    """调用模型生成查询计划和召回 hints"""

    prompt = PromptTemplate(
        template=load_prompt("plan_recall_query"),
        input_variables=["query", "tools"],
    )
    chain = prompt | llm | JsonOutputParser()
    return await chain.ainvoke({"query": query, "tools": render_tool_specs()})


def _normalize_plan(payload: object, query: str) -> AgentPlanState:
    """把模型输出规范化成稳定的 Planner State"""

    if not isinstance(payload, dict):
        raise ValueError("查询计划必须是 JSON 对象")
    # 规范工具调用计划，确保只包含允许的工具
    tool_calls: list[ToolCallState] = normalize_tool_calls(payload.get("tool_calls"))

    return AgentPlanState(
        goal_summary=str(payload.get("goal_summary") or query),
        tool_calls=tool_calls,
        need_clarification=bool(payload.get("need_clarification", False)),
        clarification_question=str(payload.get("clarification_question") or ""),
    )


def _fallback_plan(query: str) -> AgentPlanState:
    """Planner 失败时使用保守计划，保证链路可继续执行"""

    return AgentPlanState(
        goal_summary=query,
        tool_calls=default_tool_calls(),
        need_clarification=False,
        clarification_question="",
    )


def _tool_names(agent_plan: AgentPlanState) -> list[str]:
    """从工具调用计划派生工具名列表"""

    return [
        str(tool_call.get("name"))
        for tool_call in agent_plan.get("tool_calls", [])
        if tool_call.get("name")
    ]
