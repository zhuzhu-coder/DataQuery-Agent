"""
SQL 执行节点

负责执行最终 SQL，并记录查询结果。
它是当前 SQL 闭环的结束节点，执行完成后流程进入 END。
"""

from time import perf_counter

from langgraph.runtime import Runtime

from app.agent.context import DataQueryAgentContext
from app.agent.state import DataQueryAgentState
from app.agent.trace import emit_trace
from app.conf.app_config import app_config
from app.core.log import logger


async def run_sql(state: DataQueryAgentState, runtime: Runtime[DataQueryAgentContext]):
    """执行 SQL 并产出最终问数结果"""

    writer = runtime.stream_writer
    step = "执行SQL"
    writer({"type": "progress", "step": step, "status": "running"})

    try:
        # 这里拿到的可能是 generate_sql 直接通过校验的 SQL，也可能是 correct_sql 覆盖后的 SQL
        sql = state["sql"]
        dw_mysql_repository = runtime.context["dw_mysql_repository"]
        audit_repository = runtime.context.get("query_audit_repository")
        audit_id = state.get("audit_id")

        # 真实数据库访问统一封装在仓储层，节点只负责从状态取 SQL 并触发执行
        start = perf_counter()
        # 如果开启了 SQL 安全校验，执行安全模式
        if app_config.sql_security.enabled:
            result = await dw_mysql_repository.run_safe(
                sql,
                timeout_seconds=app_config.sql_security.timeout_seconds,
            )
        else:
            result = await dw_mysql_repository.run(sql)
        # 记录执行时间
        duration_ms = int((perf_counter() - start) * 1000)

        logger.info(f"SQL执行结果：{result}")
        if audit_id and audit_repository:
            await audit_repository.finish(
                audit_id,
                status="success",
                row_count=len(result),
                duration_ms=duration_ms,
            )
        writer({"type": "progress", "step": step, "status": "success"})
        emit_trace(
            writer,
            step=step,
            title=f"执行完成，返回 {len(result)} 行",
            summary=f"SQL 执行用时 {duration_ms}ms。",
            items=_result_trace_items(result),
            metadata={"row_count": len(result), "duration_ms": duration_ms},
        )
        writer({"type": "result", "data": result})

    except Exception as e:
        logger.error(f"{step} failed: {e}")
        if state.get("audit_id") and runtime.context.get("query_audit_repository"):
            await runtime.context["query_audit_repository"].finish(
                state["audit_id"],
                status="failed",
                error_message=str(e),
            )
        writer({"type": "progress", "step": step, "status": "error"})
        raise


def _result_trace_items(result: list[dict]) -> list[dict[str, str]]:
    if not result:
        return [{"label": "返回结果", "detail": "无数据"}]

    first_row = result[0]
    if not isinstance(first_row, dict):
        return [{"label": "返回结果", "detail": "已返回非字典结构结果"}]

    return [
        {
            "label": "返回字段",
            "detail": ", ".join(str(key) for key in first_row.keys()),
        }
    ]
