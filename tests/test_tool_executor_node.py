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


class FakeTool:
    def __init__(self, result):
        self.result = result
        self.payloads = []

    async def ainvoke(self, payload):
        self.payloads.append(payload)
        return self.result


class ToolExecutorNodeTest(unittest.TestCase):
    def test_tool_executor_runs_single_tool_and_writes_observation(self):
        runtime = FakeRuntime()
        fake_metric_tool = FakeTool(
            {
                "retrieved_metric_infos": [
                    {"id": "metric_gmv", "name": "GMV", "description": "成交总额"}
                ],
                "summary": "召回 1 个候选指标",
                "metadata": {"metric_count": 1, "keyword_count": 2},
            }
        )
        tools = {
            "recall_column": FakeTool({"retrieved_column_infos": []}),
            "recall_metric": fake_metric_tool,
            "recall_value": FakeTool({"retrieved_value_infos": []}),
        }
        state = {
            "query": "统计 GMV",
            "keywords": ["GMV"],
            "agent_plan": {
                "tool_calls": [
                    {
                        "id": "tool_1",
                        "name": "recall_metric",
                        "args": {"hints": ["销售额"]},
                        "reason": "需要确认指标口径",
                    }
                ]
            },
        }

        with patch("app.agent.nodes.tool_executor.build_agent_tools", return_value=tools):
            result = asyncio.run(tool_executor(state, runtime))

        self.assertEqual(result["retrieved_metric_infos"][0]["name"], "GMV")
        self.assertEqual(fake_metric_tool.payloads[0]["hints"], ["销售额"])
        observation = result["agent_observations"][0]
        self.assertEqual(observation["tool"], "recall_metric")
        self.assertEqual(observation["metadata"]["tool_call_id"], "tool_1")
        self.assertEqual(observation["metadata"]["tool_name"], "recall_metric")
        self.assertEqual(observation["metadata"]["reason"], "需要确认指标口径")

    def test_tool_executor_merges_multiple_tool_results(self):
        runtime = FakeRuntime()
        tools = {
            "recall_column": FakeTool(
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
            "recall_metric": FakeTool(
                {
                    "retrieved_metric_infos": [
                        {"id": "metric_gmv", "name": "GMV", "description": "成交总额"}
                    ],
                    "summary": "召回 1 个候选指标",
                    "metadata": {"metric_count": 1},
                }
            ),
            "recall_value": FakeTool(
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
                    {"id": "tool_1", "name": "recall_column", "args": {}, "reason": "字段"},
                    {"id": "tool_2", "name": "recall_metric", "args": {}, "reason": "指标"},
                    {"id": "tool_3", "name": "recall_value", "args": {}, "reason": "取值"},
                ]
            },
        }

        with patch("app.agent.nodes.tool_executor.build_agent_tools", return_value=tools):
            result = asyncio.run(tool_executor(state, runtime))

        self.assertEqual(len(result["retrieved_column_infos"]), 1)
        self.assertEqual(len(result["retrieved_metric_infos"]), 1)
        self.assertEqual(len(result["retrieved_value_infos"]), 1)
        self.assertEqual(len(result["agent_observations"]), 3)

    def test_tool_executor_falls_back_to_all_tools_when_plan_invalid(self):
        runtime = FakeRuntime()
        tools = {
            "recall_column": FakeTool({"retrieved_column_infos": [], "metadata": {}}),
            "recall_metric": FakeTool({"retrieved_metric_infos": [], "metadata": {}}),
            "recall_value": FakeTool({"retrieved_value_infos": [], "metadata": {}}),
        }
        state = {
            "query": "统计销售额",
            "keywords": ["销售额"],
            "agent_plan": {
                "tool_calls": [
                    {"id": "bad", "name": "made_up_tool", "args": {}, "reason": "非法"}
                ]
            },
        }

        with patch("app.agent.nodes.tool_executor.build_agent_tools", return_value=tools):
            result = asyncio.run(tool_executor(state, runtime))

        self.assertEqual(
            [observation["tool"] for observation in result["agent_observations"]],
            ["recall_column", "recall_metric", "recall_value"],
        )


if __name__ == "__main__":
    unittest.main()
