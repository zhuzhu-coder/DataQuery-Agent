import asyncio
import unittest
from unittest.mock import patch

from app.agent.nodes.tool_executor import tool_executor


class FakeRuntime:
    def __init__(self):
        self.events = []
        self.context = {}

    def stream_writer(self, event):
        self.events.append(event)


class FakeRunner:
    def __init__(self, result):
        self.result = result
        self.calls = []

    async def __call__(self, keywords, hints, context):
        self.calls.append(
            {
                "keywords": keywords,
                "hints": hints,
                "context": context,
            }
        )
        return self.result


class ToolExecutorNodeTest(unittest.TestCase):
    def test_tool_executor_runs_single_tool_and_returns_retrieved_info(self):
        runtime = FakeRuntime()
        fake_metric_runner = FakeRunner(
            {
                "retrieved_metric_infos": [
                    {"id": "metric_gmv", "name": "GMV", "description": "成交总额"}
                ],
                "summary": "召回 1 个候选指标",
                "metadata": {"metric_count": 1, "keyword_count": 2},
            }
        )
        runners = {
            "recall_column": FakeRunner({"retrieved_column_infos": []}),
            "recall_metric": fake_metric_runner,
            "recall_value": FakeRunner({"retrieved_value_infos": []}),
        }
        state = {
            "query": "统计 GMV",
            "keywords": ["GMV"],
            "agent_plan": {
                "tool_calls": [
                    {
                        "name": "recall_metric",
                        "args": {"hints": ["销售额"]},
                    }
                ]
            },
        }

        with patch("app.agent.nodes.tool_executor.TOOL_RUNNERS", runners):
            result = asyncio.run(tool_executor(state, runtime))

        self.assertEqual(result["retrieved_metric_infos"][0]["name"], "GMV")
        self.assertEqual(fake_metric_runner.calls[0]["keywords"], ["GMV"])
        self.assertEqual(fake_metric_runner.calls[0]["hints"], ["销售额"])
        self.assertIs(fake_metric_runner.calls[0]["context"], runtime.context)
        self.assertNotIn("agent_observations", result)

    def test_tool_executor_merges_multiple_tool_results(self):
        runtime = FakeRuntime()
        runners = {
            "recall_column": FakeRunner(
                {
                    "retrieved_column_infos": [
                        {
                            "id": "col_region",
                            "table_id": "dim_region",
                            "name": "region_name",
                            "description": "地区",
                        }
                    ],
                    "summary": "召回 1 个候选字段",
                    "metadata": {"column_count": 1},
                }
            ),
            "recall_metric": FakeRunner(
                {
                    "retrieved_metric_infos": [
                        {"id": "metric_gmv", "name": "GMV", "description": "成交总额"}
                    ],
                    "summary": "召回 1 个候选指标",
                    "metadata": {"metric_count": 1},
                }
            ),
            "recall_value": FakeRunner(
                {
                    "retrieved_value_infos": [
                        {"id": "value_east", "value": "华东", "column_id": "dim_region.region_name"}
                    ],
                    "summary": "召回 1 个候选字段取值",
                    "metadata": {"value_count": 1},
                }
            ),
        }
        state = {
            "query": "查询华东 GMV",
            "keywords": ["华东", "GMV"],
            "agent_plan": {
                "tool_calls": [
                    {"name": "recall_column", "args": {}},
                    {"name": "recall_metric", "args": {}},
                    {"name": "recall_value", "args": {}},
                ]
            },
        }

        with patch("app.agent.nodes.tool_executor.TOOL_RUNNERS", runners):
            result = asyncio.run(tool_executor(state, runtime))

        self.assertEqual(len(result["retrieved_column_infos"]), 1)
        self.assertEqual(len(result["retrieved_metric_infos"]), 1)
        self.assertEqual(len(result["retrieved_value_infos"]), 1)
        self.assertNotIn("agent_observations", result)

    def test_tool_executor_falls_back_to_all_tools_when_plan_invalid(self):
        runtime = FakeRuntime()
        runners = {
            "recall_column": FakeRunner({"retrieved_column_infos": [], "metadata": {}}),
            "recall_metric": FakeRunner({"retrieved_metric_infos": [], "metadata": {}}),
            "recall_value": FakeRunner({"retrieved_value_infos": [], "metadata": {}}),
        }
        state = {
            "query": "统计销售额",
            "keywords": ["销售额"],
            "agent_plan": {
                "tool_calls": [{"name": "made_up_tool", "args": {}}]
            },
        }

        with patch("app.agent.nodes.tool_executor.TOOL_RUNNERS", runners):
            result = asyncio.run(tool_executor(state, runtime))

        self.assertNotIn("agent_observations", result)
        self.assertEqual(len(runners["recall_column"].calls), 1)
        self.assertEqual(len(runners["recall_metric"].calls), 1)
        self.assertEqual(len(runners["recall_value"].calls), 1)


if __name__ == "__main__":
    unittest.main()
