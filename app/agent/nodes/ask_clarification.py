"""
澄清问题节点

当 Planner 判断当前问数目标缺少必要口径时，本节点直接向用户返回澄清问题，
避免在目标不完整时继续召回、生成和执行 SQL
"""

from langgraph.runtime import Runtime

from app.agent.context import DataQueryAgentContext
from app.agent.state import DataQueryAgentState
from app.agent.trace import emit_trace
from app.core.log import logger

DEFAULT_CLARIFICATION_QUESTION = (
    "请补充这次查询的关键口径，例如时间范围、指标口径或分析维度。"
)


async def ask_clarification(
    state: DataQueryAgentState, runtime: Runtime[DataQueryAgentContext]
):
    """向用户返回澄清问题，并结束本次图执行"""

    writer = runtime.stream_writer
    step = "需要澄清"
    writer({"type": "progress", "step": step, "status": "running"})

    try:
        agent_plan = state.get("agent_plan") or {}
        evaluation_result = state.get("evaluation_result") or {}
        if evaluation_result.get("decision") == "need_clarification":
            question = (
                evaluation_result.get("clarification_question")
                or DEFAULT_CLARIFICATION_QUESTION
            )
            reason = (
                evaluation_result.get("reason")
                or "SQL 评估判断当前问题需要补充查询口径。"
            )
        else:
            question = (
                agent_plan.get("clarification_question")
                or DEFAULT_CLARIFICATION_QUESTION
            )
            reason = agent_plan.get("reason") or "Planner 判断当前问题需要补充查询口径。"

        emit_trace(
            writer,
            step=step,
            title="需要补充查询条件",
            summary=reason,
            items=[{"label": "澄清问题", "detail": question}],
            metadata={"need_clarification": True},
        )

        audit_id = state.get("audit_id")
        audit_repository = runtime.context.get("query_audit_repository")
        if audit_id and audit_repository:
            await audit_repository.finish(
                audit_id,
                status="answered",
                row_count=0,
            )

        writer({"type": "progress", "step": step, "status": "success"})
        writer({"type": "answer", "content": question})
        logger.info(f"需要用户澄清：{question}")
        return {}
    except Exception as e:
        logger.error(f"{step} failed: {e}")
        writer({"type": "progress", "step": step, "status": "error"})
        raise
