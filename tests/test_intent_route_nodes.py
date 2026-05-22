import asyncio
import unittest
from unittest.mock import patch

from app.agent.intent import IntentCategory, IntentDecision
from app.agent.nodes.general_answer import general_answer
from app.agent.nodes.route_user_intent import route_user_intent


class FakeAuditRepository:
    def __init__(self):
        self.status = None
        self.row_count = None

    async def finish(self, audit_id: str, **kwargs):
        self.status = kwargs.get("status")
        self.row_count = kwargs.get("row_count")


class FakeRuntime:
    def __init__(self):
        self.events = []
        self.context = {"query_audit_repository": FakeAuditRepository()}

    def stream_writer(self, event):
        self.events.append(event)


class IntentRouteNodesTest(unittest.TestCase):
    def test_route_user_intent_rejects_destructive_question_from_model(self):
        runtime = FakeRuntime()
        calls = []

        async def fake_classify(query: str):
            calls.append(query)
            return IntentDecision(
                category=IntentCategory.UNSAFE,
                reason="模型判断用户要求删除数据",
                matched_terms=["删除订单表"],
            )

        with patch("app.agent.nodes.route_user_intent._classify_with_llm", fake_classify):
            result = asyncio.run(route_user_intent({"query": "删除订单表"}, runtime))

        self.assertEqual(result["intent_category"], "unsafe")
        self.assertEqual(calls, ["删除订单表"])
        self.assertEqual(result["error_type"], "security")
        self.assertIn("SELECT", result["error"])
        trace_events = [event for event in runtime.events if event["type"] == "trace"]
        self.assertEqual(trace_events[-1]["step"], "意图安全检查")
        self.assertEqual(trace_events[-1]["metadata"]["intent_category"], "unsafe")

    def test_route_user_intent_routes_simple_chat_from_model(self):
        runtime = FakeRuntime()
        calls = []

        async def fake_classify(query: str):
            calls.append(query)
            return IntentDecision(
                category=IntentCategory.GENERAL_CHAT,
                reason="模型判断用户是在打招呼",
            )

        with patch("app.agent.nodes.route_user_intent._classify_with_llm", fake_classify):
            result = asyncio.run(route_user_intent({"query": "你好"}, runtime))

        self.assertEqual(result["intent_category"], "general_chat")
        self.assertEqual(calls, ["你好"])
        self.assertIsNone(result["error"])

    def test_route_user_intent_routes_data_query_from_model(self):
        runtime = FakeRuntime()

        async def fake_classify(query: str):
            return IntentDecision(
                category=IntentCategory.DATA_QUERY,
                reason="模型判断用户在查询销售额",
            )

        with patch("app.agent.nodes.route_user_intent._classify_with_llm", fake_classify):
            result = asyncio.run(
                route_user_intent({"query": "统计 2026 年 3 月销售额"}, runtime)
            )

        self.assertEqual(result["intent_category"], "data_query")
        self.assertIsNone(result["error"])

    def test_general_answer_emits_model_answer_event_and_finishes_audit(self):
        runtime = FakeRuntime()

        async def fake_answer(query: str):
            return "你好，我是 Data Query Agent，可以帮你查询和分析电商数据。"

        with patch("app.agent.nodes.general_answer._answer_with_llm", fake_answer):
            asyncio.run(
                general_answer(
                    {
                        "query": "你好",
                        "audit_id": "audit-1",
                        "intent_category": "general_chat",
                    },
                    runtime,
                )
            )

        answer_events = [event for event in runtime.events if event["type"] == "answer"]
        self.assertEqual(len(answer_events), 1)
        self.assertIn("Data Query Agent", answer_events[0]["content"])
        self.assertEqual(runtime.context["query_audit_repository"].status, "answered")
        self.assertEqual(runtime.context["query_audit_repository"].row_count, 0)

    def test_general_answer_uses_model_for_content(self):
        runtime = FakeRuntime()

        async def fake_answer(query: str):
            return f"模型回答：{query}"

        with patch("app.agent.nodes.general_answer._answer_with_llm", fake_answer):
            asyncio.run(
                general_answer(
                    {
                        "query": "随便聊聊",
                        "audit_id": "audit-1",
                        "intent_category": "general_chat",
                    },
                    runtime,
                )
            )

        answer_events = [event for event in runtime.events if event["type"] == "answer"]
        self.assertEqual(answer_events[0]["content"], "模型回答：随便聊聊")

    def test_classification_failure_routes_to_general_answer_without_querying_data(self):
        from app.agent.nodes.route_user_intent import _classify_with_llm

        class BrokenChain:
            async def ainvoke(self, payload):
                raise ValueError("boom")

        class BrokenPrompt:
            def __or__(self, other):
                return self

        with (
            patch("app.agent.nodes.route_user_intent.PromptTemplate") as prompt_template,
            patch("app.agent.nodes.route_user_intent.JsonOutputParser") as output_parser,
        ):
            prompt_template.return_value = BrokenPrompt()
            output_parser.return_value = BrokenChain()
            decision = asyncio.run(_classify_with_llm("统计销售额"))

        self.assertEqual(decision.category, IntentCategory.GENERAL_CHAT)
        self.assertIn("不进入数据库查询流程", decision.reason)


if __name__ == "__main__":
    unittest.main()
