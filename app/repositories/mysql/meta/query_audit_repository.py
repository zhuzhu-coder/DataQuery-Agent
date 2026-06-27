"""
查询审计仓储

记录一次问数从请求进入、SQL 生成、安全校验到执行结束的关键状态。
第一阶段不绑定用户和租户，只记录 request_id、自然语言问题、SQL 和执行结果。
"""

import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class QueryAuditRepository:
    """负责 query_audit_log 表的写入和更新"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def ensure_table(self):
        """确保审计表存在，兼容已有本地开发数据库"""
        await self.session.execute(
            text(
                """
                create table if not exists query_audit_log
                (
                    id            varchar(64) primary key,
                    request_id    varchar(64),
                    query         text,
                    generated_sql text,
                    final_sql     text,
                    status        varchar(32),
                    error_message text,
                    row_count     int,
                    duration_ms   int,
                    created_at    timestamp default current_timestamp,
                    updated_at    timestamp default current_timestamp on update current_timestamp
                )
                """
            )
        )
        await self._commit_if_available()

    async def create_started(self, request_id: str, query: str) -> str:
        """创建 running 状态的审计记录，并返回审计 id"""
        audit_id = str(uuid.uuid4())
        await self.session.execute(
            text(
                """
                insert into query_audit_log
                    (id, request_id, query, status)
                values
                    (:id, :request_id, :query, :status)
                """
            ),
            {
                "id": audit_id,
                "request_id": request_id,
                "query": query,
                "status": "running",
            },
        )
        await self._commit_if_available()
        return audit_id

    async def update_sql(
        self,
        audit_id: str,
        generated_sql: str | None = None,
        final_sql: str | None = None,
    ):
        """更新生成 SQL 或最终安全 SQL"""
        fields = []
        params = {"id": audit_id}
        # 有生成 SQL，更新生成 SQL 字段
        if generated_sql is not None:
            fields.append("generated_sql = :generated_sql")
            params["generated_sql"] = generated_sql
        # 有最终安全 SQL，更新最终安全 SQL 字段
        if final_sql is not None:
            fields.append("final_sql = :final_sql")
            params["final_sql"] = final_sql
        if not fields:
            return

        await self.session.execute(
            text(f"update query_audit_log set {', '.join(fields)} where id = :id"),
            params,
        )
        await self._commit_if_available()

    async def finish(
        self,
        audit_id: str,
        status: str,
        error_message: str | None = None,
        row_count: int | None = None,
        duration_ms: int | None = None,
    ):
        """标记审计记录的最终状态"""
        await self.session.execute(
            text(
                """
                update query_audit_log
                set status = :status,
                    error_message = :error_message,
                    row_count = :row_count,
                    duration_ms = :duration_ms
                where id = :id
                """
            ),
            {
                "id": audit_id,
                "status": status,
                "error_message": error_message,
                "row_count": row_count,
                "duration_ms": duration_ms,
            },
        )
        await self._commit_if_available()

    async def _commit_if_available(self):
        """如果会话支持提交，提交事务"""
        commit = getattr(self.session, "commit", None)
        if commit is not None:
            await commit()
