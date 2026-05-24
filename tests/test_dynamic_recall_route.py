import unittest
from pathlib import Path

from app.agent.graph import graph


class DynamicRecallRouteTest(unittest.TestCase):
    def test_extract_keywords_enters_tool_executor(self):
        graph_view = graph.get_graph()
        edges = {(edge.source, edge.target) for edge in graph_view.edges}

        self.assertIn("tool_executor", graph_view.nodes)
        self.assertIn(("extract_keywords", "tool_executor"), edges)
        self.assertIn(("tool_executor", "merge_retrieved_info"), edges)

    def test_graph_no_longer_routes_to_recall_nodes_directly(self):
        graph_view = graph.get_graph()
        recall_edges = [
            edge
            for edge in graph_view.edges
            if edge.source == "extract_keywords"
            and edge.target in {"recall_column", "recall_metric", "recall_value"}
        ]

        self.assertEqual(recall_edges, [])

    def test_legacy_recall_node_files_are_removed(self):
        nodes_dir = Path(__file__).resolve().parents[1] / "app" / "agent" / "nodes"

        for file_name in ("recall_column.py", "recall_metric.py", "recall_value.py"):
            self.assertFalse((nodes_dir / file_name).exists(), file_name)


if __name__ == "__main__":
    unittest.main()
