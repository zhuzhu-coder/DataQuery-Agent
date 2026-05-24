import unittest

from langchain_core.tools import StructuredTool

from app.agent.tools import (
    available_tool_names,
    build_agent_tools,
    normalize_tool_calls,
    render_tool_specs,
)


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

    def test_tool_registry_normalizes_tool_calls(self):
        tool_calls = normalize_tool_calls(
            [
                {"id": "tool_1", "name": "recall_metric", "args": {"hints": ["GMV"]}},
                {"id": "bad", "name": "unknown_tool", "args": {"hints": ["忽略"]}},
                {"id": "dup", "name": "recall_metric", "args": {"hints": ["重复"]}},
            ]
        )

        self.assertEqual(
            [tool_call["name"] for tool_call in tool_calls], ["recall_metric"]
        )
        self.assertEqual(tool_calls[0]["args"]["hints"], ["GMV"])

    def test_tool_registry_defaults_to_all_tools_when_calls_invalid(self):
        tool_calls = normalize_tool_calls([])

        self.assertEqual(
            [tool_call["name"] for tool_call in tool_calls],
            ["recall_column", "recall_metric", "recall_value"],
        )


if __name__ == "__main__":
    unittest.main()
