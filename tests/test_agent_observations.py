import asyncio
import operator
import unittest
from typing import get_args, get_type_hints
from unittest.mock import patch

from app.agent.nodes.evaluate_sql_answer import evaluate_sql_answer
from app.agent.nodes.merge_retrieved_info import merge_retrieved_info
from app.agent.nodes.plan_query import plan_query
from app.agent.state import DataQueryAgentState


class FakeRuntime:
    def __init__(self, context=None):
        self.events = []
        self.context = context or {}

    def stream_writer(self, event):
        self.events.append(event)


class AgentObservationsTest(unittest.TestCase):
    def test_agent_observations_state_uses_append_reducer(self):
        hints = get_type_hints(DataQueryAgentState, include_extras=True)
        hint_args = get_args(hints["agent_observations"])

        self.assertEqual(hint_args[1], operator.add)

    def test_plan_query_records_planner_observation(self):
        runtime = FakeRuntime()
        model_plan = {
            "goal_summary": "统计销售额",
            "metrics": ["销售额"],
            "dimensions": [],
            "filters": [],
            "tool_calls": [
                {
                    "id": "tool_1",
                    "name": "recall_metric",
                    "args": {"hints": ["销售额"]},
                    "reason": "需要识别销售额指标。",
                }
            ],
            "need_clarification": False,
            "clarification_question": "",
            "reason": "需要识别销售额指标。",
        }

        async def fake_plan(query: str):
            return model_plan

        with patch("app.agent.nodes.plan_query._plan_with_llm", fake_plan):
            result = asyncio.run(plan_query({"query": "统计销售额"}, runtime))

        observation = result["agent_observations"][0]
        self.assertEqual(observation["tool"], "plan_query")
        self.assertIn("recall_metric", observation["summary"])
        self.assertEqual(observation["metadata"]["tool_names"], ["recall_metric"])
        self.assertEqual(observation["metadata"]["tool_call_count"], 1)

    def test_merge_retrieved_info_records_context_observation(self):
        runtime = FakeRuntime({"meta_mysql_repository": object()})

        result = asyncio.run(merge_retrieved_info({}, runtime))

        observation = result["agent_observations"][0]
        self.assertEqual(observation["tool"], "merge_retrieved_info")
        self.assertEqual(observation["metadata"]["table_count"], 0)
        self.assertEqual(observation["metadata"]["metric_count"], 0)

    def test_evaluate_sql_answer_records_evaluator_observation(self):
        runtime = FakeRuntime()
        state = {
            "query": "统计销售额",
            "sql": "SELECT SUM(order_amount) AS sales_amount FROM fact_order LIMIT 200",
            "table_infos": [],
            "metric_infos": [],
            "date_info": {},
            "db_info": {},
            "agent_plan": {},
            "evaluation_attempts": 0,
        }

        async def fake_evaluate(payload):
            return {
                "decision": "pass",
                "reason": "SQL 可以回答原问题。",
                "issues": [],
                "suggested_fix": "",
            }

        with patch("app.agent.nodes.evaluate_sql_answer._evaluate_with_llm", fake_evaluate):
            result = asyncio.run(evaluate_sql_answer(state, runtime))

        observation = result["agent_observations"][0]
        self.assertEqual(observation["tool"], "evaluate_sql_answer")
        self.assertEqual(observation["metadata"]["decision"], "pass")
        self.assertEqual(observation["metadata"]["evaluation_attempts"], 1)


if __name__ == "__main__":
    unittest.main()
