import asyncio
import unittest

from app.agent.nodes.ask_clarification import ask_clarification


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


class AskClarificationNodeTest(unittest.TestCase):
    def test_ask_clarification_emits_answer_trace_and_finishes_audit(self):
        runtime = FakeRuntime()
        state = {
            "query": "看一下销售额",
            "audit_id": "audit-1",
            "agent_plan": {
                "need_clarification": True,
                "clarification_question": "你想查看哪个时间范围的销售额？",
                "reason": "缺少时间范围。",
            },
        }

        asyncio.run(ask_clarification(state, runtime))

        answer_events = [event for event in runtime.events if event["type"] == "answer"]
        trace_events = [event for event in runtime.events if event["type"] == "trace"]

        self.assertEqual(answer_events[-1]["content"], "你想查看哪个时间范围的销售额？")
        self.assertEqual(trace_events[-1]["step"], "需要澄清")
        self.assertIn("缺少时间范围", trace_events[-1]["summary"])
        self.assertEqual(runtime.context["query_audit_repository"].status, "answered")
        self.assertEqual(runtime.context["query_audit_repository"].row_count, 0)

    def test_ask_clarification_uses_fallback_question_when_plan_question_missing(self):
        runtime = FakeRuntime()
        state = {
            "query": "看一下销售额",
            "audit_id": "audit-1",
            "agent_plan": {"need_clarification": True},
        }

        asyncio.run(ask_clarification(state, runtime))

        answer_events = [event for event in runtime.events if event["type"] == "answer"]
        self.assertIn("请补充", answer_events[-1]["content"])

    def test_ask_clarification_can_use_evaluation_question(self):
        runtime = FakeRuntime()
        state = {
            "query": "统计销售额",
            "audit_id": "audit-1",
            "agent_plan": {},
            "evaluation_result": {
                "decision": "need_clarification",
                "reason": "SQL 评估发现时间口径不明确。",
                "clarification_question": "你想按下单时间还是支付时间统计？",
            },
        }

        asyncio.run(ask_clarification(state, runtime))

        answer_events = [event for event in runtime.events if event["type"] == "answer"]
        trace_events = [event for event in runtime.events if event["type"] == "trace"]
        self.assertEqual(answer_events[-1]["content"], "你想按下单时间还是支付时间统计？")
        self.assertIn("时间口径不明确", trace_events[-1]["summary"])


if __name__ == "__main__":
    unittest.main()
