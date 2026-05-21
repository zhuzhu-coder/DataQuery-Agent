import asyncio
import unittest

from app.repositories.mysql.meta.query_audit_repository import QueryAuditRepository


class FakeSession:
    def __init__(self):
        self.executions = []

    async def execute(self, statement, params=None):
        self.executions.append((str(statement), params or {}))


class QueryAuditRepositoryTest(unittest.TestCase):
    def test_create_started_inserts_audit_record(self):
        session = FakeSession()
        repository = QueryAuditRepository(session)

        audit_id = asyncio.run(
            repository.create_started(
                request_id="req-1",
                query="统计销售额",
            )
        )

        sql, params = session.executions[0]
        self.assertIn("insert into query_audit_log", sql.lower())
        self.assertEqual(params["id"], audit_id)
        self.assertEqual(params["request_id"], "req-1")
        self.assertEqual(params["query"], "统计销售额")
        self.assertEqual(params["status"], "running")

    def test_finish_updates_audit_status(self):
        session = FakeSession()
        repository = QueryAuditRepository(session)

        asyncio.run(
            repository.finish(
                audit_id="audit-1",
                status="success",
                row_count=2,
                duration_ms=123,
            )
        )

        sql, params = session.executions[0]
        self.assertIn("update query_audit_log", sql.lower())
        self.assertEqual(params["id"], "audit-1")
        self.assertEqual(params["status"], "success")
        self.assertEqual(params["row_count"], 2)
        self.assertEqual(params["duration_ms"], 123)


if __name__ == "__main__":
    unittest.main()
