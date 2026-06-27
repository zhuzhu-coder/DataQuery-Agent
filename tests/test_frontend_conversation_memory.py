import unittest
from pathlib import Path


class FrontendConversationMemoryTest(unittest.TestCase):
    def test_frontend_sends_conversation_id_with_query(self):
        api_source = (
            Path(__file__).resolve().parents[1]
            / "frontend"
            / "src"
            / "lib"
            / "agentApi.ts"
        ).read_text(encoding="utf-8")
        app_source = (
            Path(__file__).resolve().parents[1] / "frontend" / "src" / "App.tsx"
        ).read_text(encoding="utf-8")

        self.assertIn("conversationId?: string", api_source)
        self.assertIn("conversation_id: options.conversationId", api_source)
        self.assertIn("conversationIdRef", app_source)
        self.assertIn("conversationId: conversationIdRef.current", app_source)

    def test_step_rail_shows_entry_resolution_node(self):
        source = (
            Path(__file__).resolve().parents[1]
            / "frontend"
            / "src"
            / "components"
            / "StepRail.tsx"
        ).read_text(encoding="utf-8")

        self.assertIn('step: "入口解析"', source)
        self.assertIn('"M430 48 L430 86"', source)
        self.assertIn('"M342 28 L48 28 L48 1008 L132 1008"', source)


if __name__ == "__main__":
    unittest.main()
