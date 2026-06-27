import asyncio
import unittest

from app.agent.toolkits.recall import run_recall_column


class FakeColumnInfo:
    def __init__(self, item_id: str):
        self.id = item_id


class FakeEmbeddingClient:
    def __init__(self):
        self.queries = []

    async def aembed_query(self, query: str):
        self.queries.append(query)
        return [query]


class FakeColumnVectorRepository:
    def __init__(self):
        self.embeddings = []

    async def search(self, embedding):
        self.embeddings.append(embedding)
        return [FakeColumnInfo(f"col_{embedding[0]}")]


class RecallToolkitTest(unittest.TestCase):
    def test_recall_column_uses_keywords_and_planner_hints_without_llm_expansion(self):
        embedding_client = FakeEmbeddingClient()
        column_repository = FakeColumnVectorRepository()
        context = {
            "embedding_client": embedding_client,
            "column_vector_repository": column_repository,
        }

        result = asyncio.run(
            run_recall_column(
                keywords=["GMV", "统计华东 GMV"],
                hints=["华东", "GMV"],
                context=context,
            )
        )

        self.assertEqual(embedding_client.queries, ["GMV", "统计华东 GMV", "华东"])
        self.assertEqual(result["metadata"]["keyword_count"], 3)
        self.assertEqual(result["metadata"]["column_count"], 3)


if __name__ == "__main__":
    unittest.main()
