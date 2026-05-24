import asyncio
import unittest
from unittest.mock import patch

from app.agent.nodes.correct_sql import correct_sql


class FakeRuntime:
    def __init__(self):
        self.events = []
        self.context = {}

    def stream_writer(self, event):
        self.events.append(event)


class CorrectSQLFeedbackTest(unittest.TestCase):
    def test_correct_sql_uses_evaluation_feedback_when_validation_error_missing(self):
        runtime = FakeRuntime()
        captured = {}

        class FakeChain:
            def __or__(self, other):
                return self

            async def ainvoke(self, payload):
                captured["payload"] = payload
                return "SELECT SUM(order_amount) AS sales_amount FROM fact_order WHERE region_name = '华东' LIMIT 200"

        def fake_prompt_template(template, input_variables):
            captured["input_variables"] = input_variables
            return FakeChain()

        state = {
            "query": "统计华东地区销售额",
            "sql": "SELECT SUM(order_amount) AS sales_amount FROM fact_order LIMIT 200",
            "error": None,
            "evaluation_result": {
                "reason": "SQL 缺少地区过滤条件。",
                "suggested_fix": "补充华东地区 WHERE 条件。",
            },
            "table_infos": [],
            "metric_infos": [],
            "date_info": {},
            "db_info": {},
            "correction_attempts": 0,
        }

        with (
            patch("app.agent.nodes.correct_sql.PromptTemplate", fake_prompt_template),
            patch("app.agent.nodes.correct_sql.load_prompt", return_value="{error}"),
        ):
            result = asyncio.run(correct_sql(state, runtime))

        self.assertIn("华东地区", captured["payload"]["error"])
        self.assertEqual(result["correction_attempts"], 1)
        self.assertIsNone(result["error"])


if __name__ == "__main__":
    unittest.main()
