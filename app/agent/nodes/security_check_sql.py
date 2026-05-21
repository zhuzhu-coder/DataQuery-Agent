"""
SQL 安全检查节点

在 SQL 进入数据库校验和执行前，做单条 SELECT、表字段白名单、函数白名单
和最大返回行数限制。
"""

from langgraph.runtime import Runtime

from app.agent.context import DataQueryAgentContext
from app.agent.state import DataQueryAgentState
from app.conf.app_config import app_config
from app.core.log import logger
from app.services.sql_security_service import SQLSecurityError, SQLSecurityService


async def security_check_sql(
    state: DataQueryAgentState, runtime: Runtime[DataQueryAgentContext]
):
    """校验并改写 SQL，失败时终止后续执行"""

    writer = runtime.stream_writer
    step = "安全检查SQL"
    writer({"type": "progress", "step": step, "status": "running"})

    try:
        sql = state["sql"]
        audit_id = state.get("audit_id")
        audit_repository = runtime.context.get("query_audit_repository")

        if not app_config.sql_security.enabled:
            writer({"type": "progress", "step": step, "status": "success"})
            return {"error": None, "error_type": None}

        service = SQLSecurityService(
            max_rows=app_config.sql_security.max_rows,
            allowed_functions=app_config.sql_security.allowed_functions,
            forbid_cross_database=app_config.sql_security.forbid_cross_database,
        )
        safe_sql = service.validate_and_rewrite(sql, state["table_infos"])

        if audit_id and audit_repository:
            await audit_repository.update_sql(audit_id, final_sql=safe_sql)

        logger.info(f"安全检查后的SQL：{safe_sql}")
        writer({"type": "progress", "step": step, "status": "success"})
        return {"sql": safe_sql, "error": None, "error_type": None}

    except SQLSecurityError as e:
        message = str(e)
        logger.info(f"SQL安全检查失败：{message}")
        writer({"type": "progress", "step": step, "status": "error"})
        return {"error": message, "error_type": "security"}

    except Exception as e:
        logger.error(f"{step} failed: {e}")
        writer({"type": "progress", "step": step, "status": "error"})
        raise
