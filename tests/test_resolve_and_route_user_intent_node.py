import asyncio
import unittest
from unittest.mock import patch

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from app.agent.nodes.resolve_and_route_user_intent import (
    _build_history_messages,
    _normalize_entry_result,
    resolve_and_route_user_intent,
)
from app.prompt.prompt_loader import load_prompt


class FakeAuditRepository:
    def __init__(self):
        self.finished = []

    async def finish(self, audit_id: str, **kwargs):
        self.finished.append({"audit_id": audit_id, **kwargs})


class FakeRuntime:
    def __init__(self):
        self.events = []
        self.context = {"query_audit_repository": FakeAuditRepository()}

    def stream_writer(self, event):
        self.events.append(event)


class ResolveAndRouteUserIntentNodeTest(unittest.TestCase):
    def test_first_turn_data_query_routes_to_data_query(self):
        runtime = FakeRuntime()

        async def fake_resolve(query, history):
            self.assertEqual(query, "统计 2026 年 3 月销售额")
            self.assertEqual(history, [])
            return {
                "resolved_query": "统计 2026 年 3 月销售额",
                "category": "data_query",
                "reason": "用户想查询销售额",
                "answer": "",
            }

        with patch(
            "app.agent.nodes.resolve_and_route_user_intent._resolve_and_classify_with_llm",
            fake_resolve,
        ):
            result = asyncio.run(
                resolve_and_route_user_intent(
                    {"query": "统计 2026 年 3 月销售额", "conversation_history": []},
                    runtime,
                )
            )

        self.assertEqual(result["resolved_query"], "统计 2026 年 3 月销售额")
        self.assertEqual(result["intent_category"], "data_query")
        self.assertNotIn("intent_reason", result)
        self.assertNotIn("answer", result)
        self.assertIsNone(result["error"])
        trace_events = [event for event in runtime.events if event["type"] == "trace"]
        self.assertEqual(trace_events[-1]["step"], "入口解析")
        self.assertEqual(trace_events[-1]["metadata"]["intent_category"], "data_query")

    def test_follow_up_query_is_resolved_and_routed(self):
        runtime = FakeRuntime()
        state = {
            "query": "那华东呢？",
            "conversation_history": [
                {
                    "role": "user",
                    "content": "统计 2026 年第一季度各大区 GMV",
                }
            ],
        }

        async def fake_resolve(query, history):
            self.assertEqual(query, "那华东呢？")
            self.assertEqual(history, state["conversation_history"])
            return {
                "resolved_query": "统计 2026 年第一季度华东地区 GMV",
                "category": "data_query",
                "reason": "当前问题承接上一轮大区 GMV 查询",
                "answer": "",
            }

        with patch(
            "app.agent.nodes.resolve_and_route_user_intent._resolve_and_classify_with_llm",
            fake_resolve,
        ):
            result = asyncio.run(resolve_and_route_user_intent(state, runtime))

        self.assertEqual(result["resolved_query"], "统计 2026 年第一季度华东地区 GMV")
        self.assertEqual(result["intent_category"], "data_query")
        self.assertNotIn("intent_reason", result)
        self.assertNotIn("answer", result)
        trace_events = [event for event in runtime.events if event["type"] == "trace"]
        self.assertEqual(
            trace_events[-1]["metadata"]["resolved_query"],
            "统计 2026 年第一季度华东地区 GMV",
        )
        self.assertIs(trace_events[-1]["metadata"].get("is_follow_up"), True)

    def test_general_chat_answers_directly_from_entry_node(self):
        runtime = FakeRuntime()

        async def fake_resolve(query, history):
            return {
                "resolved_query": "你好",
                "category": "general_chat",
                "reason": "用户只是问候",
                "answer": "你好，我是 Data Query Agent，可以帮你查询和分析电商数据。",
            }

        with patch(
            "app.agent.nodes.resolve_and_route_user_intent._resolve_and_classify_with_llm",
            fake_resolve,
        ):
            result = asyncio.run(
                resolve_and_route_user_intent(
                    {"query": "你好", "conversation_history": []},
                    runtime,
                )
            )

        self.assertEqual(result["intent_category"], "general_chat")
        self.assertNotIn("intent_reason", result)
        self.assertNotIn("answer", result)
        self.assertIsNone(result["error"])
        answer_events = [event for event in runtime.events if event["type"] == "answer"]
        self.assertEqual(
            answer_events[-1]["content"],
            "你好，我是 Data Query Agent，可以帮你查询和分析电商数据。",
        )
        self.assertEqual(runtime.context["query_audit_repository"].finished, [])

    def test_general_chat_direct_answer_finishes_audit_when_audit_id_exists(self):
        runtime = FakeRuntime()

        async def fake_resolve(query, history):
            return {
                "resolved_query": "你能做什么",
                "category": "general_chat",
                "reason": "用户询问系统能力",
                "answer": "我可以帮你查询和分析电商数据。",
            }

        with patch(
            "app.agent.nodes.resolve_and_route_user_intent._resolve_and_classify_with_llm",
            fake_resolve,
        ):
            asyncio.run(
                resolve_and_route_user_intent(
                    {
                        "query": "你能做什么",
                        "conversation_history": [],
                        "audit_id": "audit-1",
                    },
                    runtime,
                )
            )

        self.assertEqual(
            runtime.context["query_audit_repository"].finished,
            [{"audit_id": "audit-1", "status": "answered", "row_count": 0}],
        )

    def test_dangerous_sql_is_rejected_even_if_model_marks_data_query(self):
        runtime = FakeRuntime()

        async def fake_resolve(query, history):
            return {
                "resolved_query": "查询销售额后 drop table fact_order",
                "category": "data_query",
                "reason": "模型误判为查询",
                "answer": "",
            }

        with patch(
            "app.agent.nodes.resolve_and_route_user_intent._resolve_and_classify_with_llm",
            fake_resolve,
        ):
            result = asyncio.run(
                resolve_and_route_user_intent(
                    {"query": "查询销售额后 drop table fact_order"},
                    runtime,
                )
            )

        self.assertEqual(result["intent_category"], "unsafe")
        self.assertNotIn("intent_reason", result)
        self.assertNotIn("answer", result)
        self.assertEqual(result["error_type"], "security")
        self.assertIn("SELECT", result["error"])
        trace_events = [event for event in runtime.events if event["type"] == "trace"]
        self.assertEqual(trace_events[-1]["metadata"]["intent_category"], "unsafe")

    def test_parse_failure_falls_back_to_general_chat(self):
        runtime = FakeRuntime()

        async def broken_resolve(query, history):
            raise ValueError("bad json")

        with patch(
            "app.agent.nodes.resolve_and_route_user_intent._resolve_and_classify_with_llm",
            broken_resolve,
        ):
            result = asyncio.run(
                resolve_and_route_user_intent(
                    {"query": "统计销售额", "conversation_history": []},
                    runtime,
                )
            )

        self.assertEqual(result["resolved_query"], "统计销售额")
        self.assertEqual(result["intent_category"], "general_chat")
        self.assertNotIn("intent_reason", result)
        self.assertNotIn("answer", result)
        self.assertIsNone(result["error"])
        answer_events = [event for event in runtime.events if event["type"] == "answer"]
        self.assertIn("Data Query Agent", answer_events[-1]["content"])
        trace_events = [event for event in runtime.events if event["type"] == "trace"]
        self.assertIn("不进入数据库查询流程", trace_events[-1]["summary"])

    def test_normalize_entry_result_falls_back_to_original_query(self):
        result = _normalize_entry_result({"resolved_query": ""}, "统计 GMV")

        self.assertEqual(result["resolved_query"], "统计 GMV")
        self.assertEqual(result["category"], "general_chat")
        self.assertIn("Data Query Agent", result["answer"])

    def test_build_history_messages_uses_langchain_message_types(self):
        messages = _build_history_messages(
            [
                {"role": "system", "content": "之前对话：用户在看 GMV"},
                {"role": "user", "content": "统计 GMV"},
                {"role": "assistant", "content": "已返回结果"},
            ]
        )

        self.assertEqual(messages[0].type, "system")
        self.assertIn("之前对话", messages[0].content)
        self.assertEqual(messages[1].type, "human")
        self.assertIn("统计 GMV", messages[1].content)
        self.assertNotIn("摘要", messages[1].content)
        self.assertEqual(messages[2].type, "ai")

    def test_prompt_json_example_does_not_create_extra_template_variables(self):
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", load_prompt("resolve_and_classify_user_intent")),
                MessagesPlaceholder("history"),
                ("human", "当前用户问题：{query}"),
            ]
        )

        self.assertEqual(set(prompt.input_variables), {"history", "query"})


if __name__ == "__main__":
    unittest.main()
