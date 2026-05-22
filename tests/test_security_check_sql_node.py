import asyncio
import unittest

from app.agent.nodes.fail_query import fail_query
from app.agent.nodes.security_check_sql import security_check_sql


class FakeAuditRepository:
    def __init__(self):
        self.final_sql = None
        self.status = None
        self.error_message = None

    async def update_sql(self, audit_id: str, **kwargs):
        self.final_sql = kwargs.get("final_sql")

    async def finish(self, audit_id: str, **kwargs):
        self.status = kwargs.get("status")
        self.error_message = kwargs.get("error_message")


class FakeRuntime:
    def __init__(self):
        self.events = []
        self.context = {"query_audit_repository": FakeAuditRepository()}

    def stream_writer(self, event):
        self.events.append(event)


class SecurityCheckSQLNodeTest(unittest.TestCase):
    def setUp(self):
        self.table_infos = [
            {
                "name": "fact_order",
                "role": "fact",
                "description": "订单事实表",
                "columns": [
                    {"name": "order_id"},
                    {"name": "order_amount"},
                ],
            }
        ]

    def test_security_check_rewrites_safe_sql_and_updates_audit(self):
        runtime = FakeRuntime()
        state = {
            "audit_id": "audit-1",
            "sql": "SELECT SUM(order_amount) AS gmv FROM fact_order",
            "table_infos": self.table_infos,
        }

        result = asyncio.run(security_check_sql(state, runtime))

        self.assertIsNone(result["error"])
        self.assertTrue(result["sql"].endswith("LIMIT 200"))
        self.assertEqual(runtime.context["query_audit_repository"].final_sql, result["sql"])
        traces = [event for event in runtime.events if event["type"] == "trace"]
        self.assertEqual(traces[-1]["step"], "安全检查SQL")
        self.assertEqual(traces[-1]["title"], "安全检查通过")
        self.assertEqual(traces[-1]["metadata"]["max_rows"], 200)

    def test_security_check_rejects_unsafe_sql_and_finishes_audit(self):
        runtime = FakeRuntime()
        state = {
            "audit_id": "audit-1",
            "sql": "DROP TABLE fact_order",
            "table_infos": self.table_infos,
        }

        result = asyncio.run(security_check_sql(state, runtime))

        self.assertEqual(result["error_type"], "security")
        self.assertIn("SELECT", result["error"])
        self.assertIsNone(runtime.context["query_audit_repository"].status)
        traces = [event for event in runtime.events if event["type"] == "trace"]
        self.assertEqual(traces[-1]["title"], "安全检查未通过")
        self.assertIn("SELECT", traces[-1]["summary"])

        asyncio.run(fail_query({**state, **result}, runtime))

        self.assertEqual(runtime.context["query_audit_repository"].status, "rejected")
        self.assertEqual(
            [event["type"] for event in runtime.events if event["type"] == "error"],
            ["error"],
        )


if __name__ == "__main__":
    unittest.main()
