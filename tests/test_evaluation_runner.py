import unittest

from app.evaluation.runner import evaluate_case, parse_sse_events


class EvaluationRunnerTest(unittest.TestCase):
    def test_parse_sse_events_reads_data_chunks(self):
        chunks = [
            'data: {"type": "trace", "step": "生成SQL", "title": "生成候选 SQL"}\n\n',
            'data: {"type": "result", "data": [{"地区": "华东", "GMV": 100}]}\n\n',
        ]

        self.assertEqual(
            parse_sse_events(chunks),
            [
                {"type": "trace", "step": "生成SQL", "title": "生成候选 SQL"},
                {"type": "result", "data": [{"地区": "华东", "GMV": 100}]},
            ],
        )

    def test_evaluate_case_passes_success_expectations(self):
        case = {
            "id": "region_gmv",
            "question": "统计各地区 GMV",
            "expect": {
                "status": "success",
                "min_rows": 1,
                "column_any": [["region_name", "地区"], ["GMV", "销售额"]],
                "trace_steps": ["生成SQL", "安全检查SQL", "执行SQL"],
            },
        }
        events = [
            {"type": "trace", "step": "生成SQL"},
            {"type": "trace", "step": "安全检查SQL"},
            {"type": "trace", "step": "执行SQL"},
            {"type": "result", "data": [{"地区": "华东", "GMV": 100}]},
        ]

        result = evaluate_case(case, events, duration_ms=42)

        self.assertTrue(result["passed"])
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["row_count"], 1)
        self.assertEqual(result["failures"], [])

    def test_evaluate_case_reports_missing_expected_column_group(self):
        case = {
            "id": "region_gmv",
            "question": "统计各地区 GMV",
            "expect": {
                "status": "success",
                "column_any": [["GMV", "销售额"]],
            },
        }
        events = [{"type": "result", "data": [{"地区": "华东"}]}]

        result = evaluate_case(case, events, duration_ms=42)

        self.assertFalse(result["passed"])
        self.assertIn("缺少字段之一：GMV / 销售额", result["failures"])

    def test_evaluate_case_passes_security_rejection(self):
        case = {
            "id": "unsafe_delete",
            "question": "删除订单表",
            "expect": {
                "status": "rejected",
                "error_contains": "SELECT",
                "trace_steps": ["安全检查SQL", "查询终止"],
            },
        }
        events = [
            {"type": "trace", "step": "安全检查SQL"},
            {
                "type": "trace",
                "step": "查询终止",
                "metadata": {"error_type": "security"},
            },
            {"type": "error", "message": "仅允许执行 SELECT 查询"},
        ]

        result = evaluate_case(case, events, duration_ms=42)

        self.assertTrue(result["passed"])
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(result["error_message"], "仅允许执行 SELECT 查询")

    def test_evaluate_case_passes_general_answer_expectations(self):
        case = {
            "id": "hello",
            "question": "你好",
            "expect": {
                "status": "answered",
                "answer_contains": "Data Query Agent",
                "trace_steps": ["意图安全检查", "普通回答"],
            },
        }
        events = [
            {"type": "trace", "step": "意图安全检查"},
            {"type": "trace", "step": "普通回答"},
            {
                "type": "answer",
                "content": "你好，我是 Data Query Agent，可以帮你查询电商数据。",
            },
        ]

        result = evaluate_case(case, events, duration_ms=42)

        self.assertTrue(result["passed"])
        self.assertEqual(result["status"], "answered")
        self.assertEqual(result["answer"], "你好，我是 Data Query Agent，可以帮你查询电商数据。")


if __name__ == "__main__":
    unittest.main()
