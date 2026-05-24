from pathlib import Path
import unittest


class FrontendStopQueryTest(unittest.TestCase):
    def test_manual_stop_marks_query_end_as_stopped(self):
        source = (
            Path(__file__).resolve().parents[1] / "frontend" / "src" / "App.tsx"
        ).read_text(encoding="utf-8")

        self.assertIn("function markQueryStopped", source)
        self.assertIn('step: "查询终止"', source)
        self.assertIn('status: "stopped"', source)
        self.assertIn("steps: isAbort ? markQueryStopped(message.steps)", source)

    def test_stopped_step_has_clear_gray_style(self):
        source = (
            Path(__file__).resolve().parents[1]
            / "frontend"
            / "src"
            / "components"
            / "StepRail.tsx"
        ).read_text(encoding="utf-8")

        self.assertIn(
            'status === "stopped" && "border-slate-300 bg-slate-100 text-slate-500"',
            source,
        )


if __name__ == "__main__":
    unittest.main()
