import asyncio
import unittest
from pathlib import Path
from unittest.mock import patch

from app.agent.nodes.plan_query import _normalize_plan, _plan_with_llm, plan_query


class FakeRuntime:
    def __init__(self):
        self.events = []
        self.context = {}

    def stream_writer(self, event):
        self.events.append(event)


class PlanQueryNodeTest(unittest.TestCase):
    def test_plan_query_writes_structured_plan_and_trace(self):
        runtime = FakeRuntime()
        model_plan = {
            "goal_summary": "统计 2026 年第一季度各大区 GMV",
            "metrics": ["GMV"],
            "dimensions": ["大区"],
            "filters": ["2026 年第一季度"],
            "tool_calls": [
                {
                    "id": "tool_1",
                    "name": "recall_column",
                    "args": {"hints": ["大区"]},
                    "reason": "需要定位大区字段",
                },
                {
                    "id": "tool_2",
                    "name": "recall_metric",
                    "args": {"hints": ["GMV"]},
                    "reason": "需要确认 GMV 口径",
                },
            ],
            "need_clarification": False,
            "clarification_question": "",
            "reason": "需要识别指标、维度和时间过滤条件",
        }

        async def fake_plan(query: str):
            self.assertEqual(query, "统计 2026 年第一季度各大区 GMV")
            return model_plan

        with patch("app.agent.nodes.plan_query._plan_with_llm", fake_plan):
            result = asyncio.run(
                plan_query({"query": "统计 2026 年第一季度各大区 GMV"}, runtime)
            )

        self.assertEqual(result["agent_plan"], model_plan)
        trace_events = [event for event in runtime.events if event["type"] == "trace"]
        self.assertEqual(trace_events[-1]["step"], "制定查询计划")
        self.assertEqual(
            trace_events[-1]["metadata"]["tool_names"],
            ["recall_column", "recall_metric"],
        )
        self.assertEqual(trace_events[-1]["metadata"]["tool_call_count"], 2)
        self.assertFalse(trace_events[-1]["metadata"]["need_clarification"])

    def test_plan_query_falls_back_to_full_recall_when_model_fails(self):
        runtime = FakeRuntime()

        async def broken_plan(query: str):
            raise ValueError("bad json")

        with patch("app.agent.nodes.plan_query._plan_with_llm", broken_plan):
            result = asyncio.run(plan_query({"query": "统计销售额"}, runtime))

        self.assertEqual(
            [tool_call["name"] for tool_call in result["agent_plan"]["tool_calls"]],
            ["recall_column", "recall_metric", "recall_value"],
        )
        self.assertFalse(result["agent_plan"]["need_clarification"])
        self.assertIn("兜底", result["agent_plan"]["reason"])

    def test_plan_query_prompt_uses_injected_tools_instead_of_hardcoded_names(self):
        prompt = Path("prompts/plan_query.prompt").read_text(encoding="utf-8")

        self.assertIn("{tools}", prompt)
        self.assertIn("tool_calls", prompt)
        self.assertNotIn("required_tools", prompt)

    def test_normalize_plan_filters_tool_calls_with_registry_names(self):
        plan = _normalize_plan(
            {
                "goal_summary": "统计销售额",
                "tool_calls": [
                    {
                        "id": "tool_1",
                        "name": "recall_metric",
                        "args": {"hints": ["销售额"]},
                        "reason": "需要指标",
                    },
                    {
                        "id": "tool_2",
                        "name": "made_up_tool",
                        "args": {"hints": ["忽略"]},
                        "reason": "非法工具",
                    },
                ],
            },
            "统计销售额",
        )

        self.assertEqual(
            [tool_call["name"] for tool_call in plan["tool_calls"]],
            ["recall_metric"],
        )
        self.assertEqual(plan["tool_calls"][0]["args"]["hints"], ["销售额"])

    def test_normalize_plan_defaults_to_registry_tools_when_tool_calls_missing(self):
        plan = _normalize_plan({"goal_summary": "统计销售额"}, "统计销售额")

        self.assertEqual(
            [tool_call["name"] for tool_call in plan["tool_calls"]],
            ["recall_column", "recall_metric", "recall_value"],
        )

    def test_plan_with_llm_injects_registered_tools_into_prompt_payload(self):
        captured = {}

        class FakeChain:
            async def ainvoke(self, payload):
                captured["payload"] = payload
                return {"goal_summary": "统计销售额"}

        class FakePrompt:
            def __or__(self, other):
                if isinstance(other, FakeParser):
                    return FakeChain()
                return self

        class FakeParser:
            def __ror__(self, other):
                return FakeChain()

        def fake_prompt_template(template, input_variables):
            captured["template"] = template
            captured["input_variables"] = input_variables
            return FakePrompt()

        with (
            patch("app.agent.nodes.plan_query.PromptTemplate", fake_prompt_template),
            patch("app.agent.nodes.plan_query.JsonOutputParser", return_value=FakeParser()),
            patch("app.agent.nodes.plan_query.load_prompt", return_value="{query}\n{tools}"),
        ):
            asyncio.run(_plan_with_llm("统计销售额"))

        self.assertEqual(captured["input_variables"], ["query", "tools"])
        self.assertEqual(captured["payload"]["query"], "统计销售额")
        self.assertIn("name: recall_column", captured["payload"]["tools"])
        self.assertIn("name: recall_metric", captured["payload"]["tools"])


if __name__ == "__main__":
    unittest.main()
