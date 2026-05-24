import unittest

from app.agent.graph import graph, route_sql_evaluation


class AgentGraphEvaluatorTest(unittest.TestCase):
    def test_validated_sql_enters_evaluator_before_execution(self):
        graph_view = graph.get_graph()
        edges = {(edge.source, edge.target) for edge in graph_view.edges}

        self.assertIn("evaluate_sql_answer", graph_view.nodes)
        self.assertIn(("validate_sql", "evaluate_sql_answer"), edges)
        self.assertNotIn(("validate_sql", "run_sql"), edges)

    def test_evaluator_routes_pass_to_execution(self):
        state = {
            "evaluation_result": {"decision": "pass"},
            "evaluation_attempts": 1,
        }

        self.assertEqual(route_sql_evaluation(state), "run_sql")

    def test_evaluator_routes_first_revision_to_correction(self):
        state = {
            "evaluation_result": {"decision": "revise_sql"},
            "evaluation_attempts": 1,
        }

        self.assertEqual(route_sql_evaluation(state), "correct_sql")

    def test_evaluator_routes_repeated_revision_to_failure(self):
        state = {
            "evaluation_result": {"decision": "revise_sql"},
            "evaluation_attempts": 2,
        }

        self.assertEqual(route_sql_evaluation(state), "fail_query")

    def test_evaluator_routes_clarification_to_ask_node(self):
        state = {
            "evaluation_result": {"decision": "need_clarification"},
            "evaluation_attempts": 1,
        }

        self.assertEqual(route_sql_evaluation(state), "ask_clarification")


if __name__ == "__main__":
    unittest.main()
