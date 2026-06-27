"""
SQL 校验节点

负责在真正执行查询前，用数据库解析一次生成的 SQ
校验结果不在这里决定流程走向，而是通过 state["error"] 交给 graph.py 的条件边判断
"""

from langgraph.runtime import Runtime

from app.agent.context import DataQueryAgentContext
from app.agent.state import DataQueryAgentState
from app.agent.trace import emit_trace
from app.core.log import logger
from app.repositories.mysql.dw.dw_mysql_repository import DWMySQLRepository


async def validate_sql(state: DataQueryAgentState, runtime: Runtime[DataQueryAgentContext]):
    """校验 SQL，并返回 error 字段控制后续条件分支"""

    writer = runtime.stream_writer
    step = "校验SQL"
    writer({"type": "progress", "step": step, "status": "running"})

    try:
        # 读取 generate_sql 或 correct_sql 写入状态的候选 SQL
        sql = state["sql"]

        # SQL 可用性必须交给真实数仓判断，这里从运行时上下文取 DW Repository
        dw_mysql_repository: DWMySQLRepository = runtime.context["dw_mysql_repository"]

        try:
            # validate 内部使用 explain <sql>，只关心数据库能否成功解析这条 SQL
            await dw_mysql_repository.validate(sql)
            writer({"type": "progress", "step": step, "status": "success"})
            emit_trace(
                writer,
                step=step,
                title="SQL 校验通过",
                summary="数据库 EXPLAIN 校验通过，SQL 可以进入执行阶段。",
                items=[{"label": "校验 SQL", "detail": sql}],
                metadata={"valid": True},
            )
            logger.info("SQL语法正确")
            return {
                "error": None,
                "error_type": None,
            }
        except Exception as e:
            # 不抛出异常中断图执行，而是把错误写入状态，供条件分支进入 correct_sql
            message = str(e)
            logger.info(f"SQL语法错误：{message}")
            writer({"type": "progress", "step": step, "status": "success"})
            emit_trace(
                writer,
                step=step,
                title="SQL 校验未通过",
                summary="数据库 EXPLAIN 返回错误，后续会尝试修正 SQL。",
                items=[
                    {"label": "错误信息", "detail": message},
                    {"label": "待校验 SQL", "detail": sql},
                ],
                metadata={"valid": False},
            )
            return {
                "error": message,
                "error_type": "syntax",
            }

    except Exception as e:
        logger.error(f"{step} failed: {e}")
        writer({"type": "progress", "step": step, "status": "error"})
        raise
