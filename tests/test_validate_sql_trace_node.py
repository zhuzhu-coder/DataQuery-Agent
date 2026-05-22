import asyncio
import unittest

from app.agent.nodes.validate_sql import validate_sql


class FakeDWRepository:
    def __init__(self, error: Exception | None = None):
        self.error = error

    async def validate(self, sql: str):
        if self.error:
            raise self.error


class FakeRuntime:
    def __init__(self, dw_repository):
        self.events = []
        self.context = {"dw_mysql_repository": dw_repository}

    def stream_writer(self, event):
        self.events.append(event)


class ValidateSQLTraceNodeTest(unittest.TestCase):
    def test_validate_sql_emits_success_trace(self):
        runtime = FakeRuntime(FakeDWRepository())

        result = asyncio.run(validate_sql({"sql": "SELECT 1"}, runtime))

        trace_events = [event for event in runtime.events if event["type"] == "trace"]
        self.assertEqual(result["error"], None)
        self.assertEqual(trace_events[-1]["step"], "校验SQL")
        self.assertEqual(trace_events[-1]["title"], "SQL 校验通过")
        self.assertTrue(trace_events[-1]["metadata"]["valid"])

    def test_validate_sql_emits_failure_trace(self):
        runtime = FakeRuntime(FakeDWRepository(ValueError("unknown column")))

        result = asyncio.run(validate_sql({"sql": "SELECT bad_column"}, runtime))

        trace_events = [event for event in runtime.events if event["type"] == "trace"]
        self.assertEqual(result["error_type"], "syntax")
        self.assertEqual(trace_events[-1]["step"], "校验SQL")
        self.assertEqual(trace_events[-1]["title"], "SQL 校验未通过")
        self.assertFalse(trace_events[-1]["metadata"]["valid"])
        self.assertIn("unknown column", trace_events[-1]["items"][0]["detail"])


if __name__ == "__main__":
    unittest.main()
