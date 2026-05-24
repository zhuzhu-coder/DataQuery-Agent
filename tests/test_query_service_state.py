import unittest

import app.services.query_service as query_service_module
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
        self.assertIn("agent_observations", self.fake_graph.input)
        self.assertIn("evaluation_result", self.fake_graph.input)
        self.assertIn("evaluation_attempts", self.fake_graph.input)
        self.assertEqual(self.fake_graph.input["agent_plan"], {})
        self.assertEqual(self.fake_graph.input["agent_observations"], [])
        self.assertEqual(self.fake_graph.input["evaluation_result"], {})
        self.assertEqual(self.fake_graph.input["evaluation_attempts"], 0)


if __name__ == "__main__":
    unittest.main()
