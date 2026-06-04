import unittest
from pathlib import Path


class FrontendStepRailTest(unittest.TestCase):
    def test_step_rail_shows_tool_executor_flow(self):
        source = (
            Path(__file__).resolve().parents[1]
            / "frontend"
            / "src"
            / "components"
            / "StepRail.tsx"
        ).read_text(encoding="utf-8")

        self.assertIn('step: "执行工具"', source)
        self.assertIn('label: "recall_column"', source)
        self.assertIn('label: "recall_metric"', source)
        self.assertIn('label: "recall_value"', source)
        self.assertIn('"M430 316 L430 362"', source)
        self.assertIn('"M430 408 L430 432', source)

    def test_tool_nodes_use_same_card_style_as_other_nodes(self):
        source = (
            Path(__file__).resolve().parents[1]
            / "frontend"
            / "src"
            / "components"
            / "StepRail.tsx"
        ).read_text(encoding="utf-8")

        self.assertNotIn("border-indigo-200", source)
        self.assertNotIn("border-sky-200", source)
        self.assertIn('caption: "字段召回"', source)
        self.assertIn('caption: "指标召回"', source)
        self.assertIn('caption: "取值召回"', source)

    def test_intent_node_uses_short_display_name(self):
        source = (
            Path(__file__).resolve().parents[1]
            / "frontend"
            / "src"
            / "components"
            / "StepRail.tsx"
        ).read_text(encoding="utf-8")

        self.assertIn('displayName: "意图识别"', source)


if __name__ == "__main__":
    unittest.main()
