import unittest

from app.agent.graph import graph


class AgentGraphPlannerTest(unittest.TestCase):
    def test_data_query_route_enters_planner_before_keyword_extraction(self):
        graph_view = graph.get_graph()
        edges = {(edge.source, edge.target) for edge in graph_view.edges}

        self.assertIn("resolve_and_route_user_intent", graph_view.nodes)
        self.assertIn("plan_recall_query", graph_view.nodes)
        self.assertIn(("__start__", "resolve_and_route_user_intent"), edges)
        self.assertIn(("resolve_and_route_user_intent", "plan_recall_query"), edges)
        self.assertIn(("plan_recall_query", "extract_keywords"), edges)
        self.assertNotIn(("resolve_and_route_user_intent", "extract_keywords"), edges)
        self.assertNotIn("general_answer", graph_view.nodes)
        self.assertIn(("resolve_and_route_user_intent", "__end__"), edges)

    def test_planner_can_route_to_clarification_before_keyword_extraction(self):
        graph_view = graph.get_graph()
        edges = {(edge.source, edge.target) for edge in graph_view.edges}

        self.assertIn("ask_clarification", graph_view.nodes)
        self.assertIn(("plan_recall_query", "ask_clarification"), edges)
        self.assertIn(("ask_clarification", "__end__"), edges)

    def test_merge_retrieved_info_enters_single_query_context_filter(self):
        graph_view = graph.get_graph()
        edges = {(edge.source, edge.target) for edge in graph_view.edges}

        self.assertIn("filter_query_context", graph_view.nodes)
        self.assertIn(("merge_retrieved_info", "filter_query_context"), edges)
        self.assertIn(("filter_query_context", "add_extra_context"), edges)
        self.assertNotIn("filter_table", graph_view.nodes)
        self.assertNotIn("filter_metric", graph_view.nodes)


if __name__ == "__main__":
    unittest.main()
