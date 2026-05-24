import unittest

from langchain_core.tools import StructuredTool

from app.agent.tools import available_tool_names, build_agent_tools, render_tool_specs


class AgentToolRegistryTest(unittest.TestCase):
    def test_tool_registry_exposes_planner_tool_names_and_specs(self):
        self.assertEqual(
            available_tool_names(),
            ["recall_column", "recall_metric", "recall_value"],
        )

        specs = render_tool_specs()

        self.assertIn("name: recall_column", specs)
        self.assertIn("name: recall_metric", specs)
        self.assertIn("name: recall_value", specs)
        self.assertIn("description:", specs)

    def test_tool_registry_builds_structured_tools(self):
        tools = build_agent_tools({})

        self.assertEqual(
            list(tools.keys()),
            ["recall_column", "recall_metric", "recall_value"],
        )
        self.assertTrue(
            all(isinstance(tool, StructuredTool) for tool in tools.values())
        )


if __name__ == "__main__":
    unittest.main()
