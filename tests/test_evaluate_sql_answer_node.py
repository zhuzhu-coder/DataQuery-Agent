import asyncio
import unittest
from unittest.mock import patch

from app.agent.nodes.evaluate_sql_answer import evaluate_sql_answer


class FakeRuntime:
    def __init__(self):
        self.events = []
        self.context = {}

    def stream_writer(self, event):
        self.events.append(event)


class EvaluateSQLAnswerNodeTest(unittest.TestCase):
    def test_evaluate_sql_answer_writes_pass_result_and_trace(self):
        runtime = FakeRuntime()
        state = {
            "query": "统计 2026 年第一季度各大区 GMV",
            "sql": "SELECT region_name, SUM(order_amount) AS gmv FROM fact_order GROUP BY region_name LIMIT 200",
            "table_infos": [],
            "metric_infos": [],
            "date_info": {},
            "db_info": {},
            "agent_plan": {
                "goal_summary": "统计 2026 年第一季度各大区 GMV",
            },
            "evaluation_attempts": 0,
        }
        model_result = {
            "decision": "pass",
            "reason": "SQL 覆盖了指标和维度。",
            "suggested_fix": "",
            "clarification_question": "",
        }

        async def fake_evaluate(payload):
            self.assertEqual(set(payload), {"query", "sql"})
            self.assertEqual(payload["query"], state["query"])
            self.assertEqual(payload["sql"], state["sql"])
            return model_result

        with patch("app.agent.nodes.evaluate_sql_answer._evaluate_with_llm", fake_evaluate):
            result = asyncio.run(evaluate_sql_answer(state, runtime))

        self.assertEqual(result["evaluation_result"]["decision"], "pass")
        self.assertEqual(result["evaluation_attempts"], 1)
        self.assertIsNone(result["error"])
        trace_events = [event for event in runtime.events if event["type"] == "trace"]
        self.assertEqual(trace_events[-1]["step"], "评估SQL答案")
        self.assertEqual(trace_events[-1]["metadata"]["decision"], "pass")

    def test_evaluate_sql_answer_normalizes_revise_result(self):
        runtime = FakeRuntime()
        state = {
            "query": "统计华东地区销售额",
            "sql": "SELECT SUM(order_amount) AS sales_amount FROM fact_order LIMIT 200",
            "table_infos": [],
            "metric_infos": [],
            "date_info": {},
            "db_info": {},
            "agent_plan": {"goal_summary": "统计华东地区销售额"},
            "evaluation_attempts": 0,
        }

        async def fake_evaluate(payload):
            return {
                "decision": "revise_sql",
                "reason": "缺少华东地区过滤条件。",
                "suggested_fix": "补充华东地区 WHERE 条件。",
            }

        with patch("app.agent.nodes.evaluate_sql_answer._evaluate_with_llm", fake_evaluate):
            result = asyncio.run(evaluate_sql_answer(state, runtime))

        self.assertEqual(result["evaluation_result"]["decision"], "revise_sql")
        self.assertEqual(result["error_type"], "semantic")
        self.assertIn("华东地区", result["error"])


if __name__ == "__main__":
    unittest.main()
