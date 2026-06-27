import unittest

import app.services.query_service as query_service_module
from app.services.conversation_memory import ConversationTurn
from app.services.query_service import QueryService


class FakeAuditRepository:
    async def create_started(self, request_id: str, query: str) -> str:
        return "audit-id"

    async def finish(self, *args, **kwargs):
        return None


class FakeGraph:
    def __init__(self):
        self.input = None
        self.context = None
        self.stream_mode = None

    async def astream(self, input, context, stream_mode):
        self.input = input
        self.context = context
        self.stream_mode = stream_mode
        yield {"type": "progress", "step": "测试", "status": "success"}


class FakeResultGraph(FakeGraph):
    async def astream(self, input, context, stream_mode):
        self.input = input
        self.context = context
        self.stream_mode = stream_mode
        yield {
            "type": "trace",
            "step": "入口解析",
            "title": "完成入口解析",
            "metadata": {"resolved_query": "统计 2026 年第一季度华东地区 GMV"},
        }
        yield {"type": "result", "data": [{"region_name": "华东", "gmv": 100}]}


class FakeMemoryStore:
    def __init__(self):
        self.appended = []
        self.compacted = []

    async def get_history(self, conversation_id: str):
        return [
            ConversationTurn(
                role="user",
                content="统计 2026 年第一季度各大区 GMV",
            )
        ]

    async def append_message(self, conversation_id: str, role: str, content: str):
        self.appended.append(
            {
                "conversation_id": conversation_id,
                "role": role,
                "content": content,
            }
        )

    async def compact_if_needed(self, conversation_id: str, compressor):
        self.compacted.append(conversation_id)
        return False


class QueryServiceStateTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.original_graph = query_service_module.graph
        self.fake_graph = FakeGraph()
        query_service_module.graph = self.fake_graph

    def tearDown(self):
        query_service_module.graph = self.original_graph

    async def test_query_initializes_agent_scratchpad_state(self):
        service = QueryService(
            meta_mysql_repository=object(),
            embedding_client=object(),
            dw_mysql_repository=object(),
            column_vector_repository=object(),
            metric_vector_repository=object(),
            value_es_repository=object(),
            query_audit_repository=FakeAuditRepository(),
        )

        chunks = [chunk async for chunk in service.query("统计 GMV")]

        self.assertEqual(len(chunks), 1)
        self.assertEqual(self.fake_graph.input["query"], "统计 GMV")
        self.assertIn("agent_plan", self.fake_graph.input)
        self.assertNotIn("agent_observations", self.fake_graph.input)
        self.assertNotIn("intent_reason", self.fake_graph.input)
        self.assertNotIn("answer", self.fake_graph.input)
        self.assertIn("evaluation_result", self.fake_graph.input)
        self.assertIn("evaluation_attempts", self.fake_graph.input)
        self.assertEqual(self.fake_graph.input["agent_plan"], {})
        self.assertEqual(self.fake_graph.input["evaluation_result"], {})
        self.assertEqual(self.fake_graph.input["evaluation_attempts"], 0)

    async def test_query_injects_and_updates_conversation_memory(self):
        self.fake_graph = FakeResultGraph()
        query_service_module.graph = self.fake_graph
        memory_store = FakeMemoryStore()
        service = QueryService(
            meta_mysql_repository=object(),
            embedding_client=object(),
            dw_mysql_repository=object(),
            column_vector_repository=object(),
            metric_vector_repository=object(),
            value_es_repository=object(),
            query_audit_repository=FakeAuditRepository(),
            conversation_memory_store=memory_store,
        )

        chunks = [
            chunk
            async for chunk in service.query("那华东呢？", conversation_id="conv-1")
        ]

        self.assertEqual(len(chunks), 2)
        self.assertEqual(
            self.fake_graph.input["conversation_history"][0]["content"],
            "统计 2026 年第一季度各大区 GMV",
        )
        self.assertEqual(len(memory_store.appended), 2)
        self.assertEqual(memory_store.appended[0]["role"], "user")
        self.assertNotIn("summary", memory_store.appended[0])
        self.assertEqual(memory_store.appended[0]["content"], "那华东呢？")
        self.assertEqual(memory_store.appended[1]["role"], "assistant")
        self.assertNotIn("summary", memory_store.appended[1])
        self.assertIn("补全后问题", memory_store.appended[1]["content"])
        self.assertIn("返回 1 行", memory_store.appended[1]["content"])
        self.assertEqual(memory_store.compacted, ["conv-1"])


if __name__ == "__main__":
    unittest.main()
