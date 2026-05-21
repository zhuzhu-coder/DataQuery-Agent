"""
查询失败终止节点

用于安全检查拒绝或 SQL 修正后仍无法通过校验时，向前端输出明确错误。
"""

from langgraph.runtime import Runtime

from app.agent.context import DataQueryAgentContext
from app.agent.state import DataQueryAgentState
from app.core.log import logger


async def fail_query(state: DataQueryAgentState, runtime: Runtime[DataQueryAgentContext]):
    """输出最终错误并更新审计状态"""

    writer = runtime.stream_writer
    message = state.get("error") or "查询未通过校验"
    logger.info(f"查询终止：{message}")

    audit_id = state.get("audit_id")
    audit_repository = runtime.context.get("query_audit_repository")
    if audit_id and audit_repository:
        await audit_repository.finish(
            audit_id,
            status="rejected" if state.get("error_type") == "security" else "failed",
            error_message=message,
        )

    writer({"type": "error", "message": message})
    return {}
