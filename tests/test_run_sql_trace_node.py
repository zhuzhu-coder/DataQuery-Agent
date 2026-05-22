import asyncio
import unittest

from app.agent.nodes.run_sql import run_sql


class FakeAuditRepository:
    def __init__(self):
        self.status = None
        self.row_count = None
        self.duration_ms = None

    async def finish(self, audit_id: str, **kwargs):
        self.status = kwargs.get("status")
        self.row_count = kwargs.get("row_count")
        self.duration_ms = kwargs.get("duration_ms")


class FakeDWRepository:
    def __init__(self):
        self.safe_call = None

    async def run_safe(self, sql: str, timeout_seconds: int):
        self.safe_call = (sql, timeout_seconds)
        return [{"region_name": "华北", "gmv": 1000}]

    async def run(self, sql: str):
        return [{"region_name": "华北", "gmv": 1000}]


class FakeRuntime:
    def __init__(self):
        self.events = []
        self.context = {
            "dw_mysql_repository": FakeDWRepository(),
            "query_audit_repository": FakeAuditRepository(),
        }

    def stream_writer(self, event):
        self.events.append(event)


class RunSQLTraceNodeTest(unittest.TestCase):
    def test_run_sql_emits_execution_trace_before_result(self):
        runtime = FakeRuntime()
        state = {"audit_id": "audit-1", "sql": "SELECT region_name, gmv FROM t LIMIT 10"}

        asyncio.run(run_sql(state, runtime))

        trace_events = [event for event in runtime.events if event["type"] == "trace"]
        self.assertEqual(trace_events[-1]["step"], "执行SQL")
        self.assertEqual(trace_events[-1]["title"], "执行完成，返回 1 行")
        self.assertEqual(trace_events[-1]["metadata"]["row_count"], 1)
        self.assertIn("region_name, gmv", trace_events[-1]["items"][0]["detail"])

        event_types = [event["type"] for event in runtime.events]
        self.assertLess(event_types.index("trace"), event_types.index("result"))


if __name__ == "__main__":
    unittest.main()
