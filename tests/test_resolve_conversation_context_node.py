import asyncio
import unittest
from unittest.mock import patch

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from app.agent.nodes.resolve_conversation_context import (
    _build_history_messages,
    _normalize_resolution,
    resolve_conversation_context,
)
from app.prompt.prompt_loader import load_prompt


class FakeRuntime:
    def __init__(self):
        self.events = []
        self.context = {}

    def stream_writer(self, event):
        self.events.append(event)


class ResolveConversationContextNodeTest(unittest.TestCase):
    def test_resolve_context_rewrites_follow_up_query(self):
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
                "is_follow_up": True,
                "resolved_query": "统计 2026 年第一季度华东地区 GMV",
                "inherited_context": ["时间：2026Q1", "指标：GMV"],
                "new_constraints": ["地区：华东"],
                "reason": "当前问题承接上一轮大区 GMV 查询",
            }

        with patch(
            "app.agent.nodes.resolve_conversation_context._resolve_with_llm",
            fake_resolve,
        ):
            result = asyncio.run(resolve_conversation_context(state, runtime))

        self.assertEqual(result["resolved_query"], "统计 2026 年第一季度华东地区 GMV")
        trace_events = [event for event in runtime.events if event["type"] == "trace"]
        self.assertEqual(trace_events[-1]["step"], "上下文补全")
        self.assertTrue(trace_events[-1]["metadata"]["is_follow_up"])
        self.assertEqual(
            trace_events[-1]["metadata"]["resolved_query"],
            "统计 2026 年第一季度华东地区 GMV",
        )

    def test_normalize_resolution_falls_back_to_original_query(self):
        result = _normalize_resolution({"resolved_query": ""}, "统计 GMV")

        self.assertFalse(result["is_follow_up"])
        self.assertEqual(result["resolved_query"], "统计 GMV")

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
                ("system", load_prompt("resolve_conversation_context")),
                MessagesPlaceholder("history"),
                ("human", "当前用户问题：{query}"),
            ]
        )

        self.assertEqual(set(prompt.input_variables), {"history", "query"})


if __name__ == "__main__":
    unittest.main()
