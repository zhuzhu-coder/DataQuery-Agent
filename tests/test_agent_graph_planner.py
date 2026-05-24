import unittest

from app.agent.graph import graph, route_conversation_entry


class AgentGraphPlannerTest(unittest.TestCase):
    def test_first_turn_skips_context_node(self):
        self.assertEqual(route_conversation_entry({}), "route_user_intent")
        self.assertEqual(
            route_conversation_entry({"conversation_history": []}),
            "route_user_intent",
        )

    def test_follow_up_enters_context_node_first(self):
        self.assertEqual(
            route_conversation_entry(
                {"conversation_history": [{"role": "user", "content": "统计 GMV"}]}
            ),
            "resolve_conversation_context",
        )

    def test_data_query_route_enters_planner_before_keyword_extraction(self):
        graph_view = graph.get_graph()
        edges = {(edge.source, edge.target) for edge in graph_view.edges}

        self.assertIn("resolve_conversation_context", graph_view.nodes)
        self.assertIn(("resolve_conversation_context", "route_user_intent"), edges)
        self.assertIn("plan_query", graph_view.nodes)
        self.assertIn(("route_user_intent", "plan_query"), edges)
        self.assertIn(("plan_query", "extract_keywords"), edges)
        self.assertNotIn(("route_user_intent", "extract_keywords"), edges)

    def test_planner_can_route_to_clarification_before_keyword_extraction(self):
        graph_view = graph.get_graph()
        edges = {(edge.source, edge.target) for edge in graph_view.edges}

        self.assertIn("ask_clarification", graph_view.nodes)
        self.assertIn(("plan_query", "ask_clarification"), edges)
        self.assertIn(("ask_clarification", "__end__"), edges)


if __name__ == "__main__":
    unittest.main()
