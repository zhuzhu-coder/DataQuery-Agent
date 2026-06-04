import asyncio
import unittest

from app.evaluation.runner import collect_case_events, evaluate_case, parse_sse_events


class FakeQueryService:
    def __init__(self):
        self.calls = []
        self.conversation_memory_store = None

    async def query(self, question, conversation_id=None):
        self.calls.append(
            {"question": question, "conversation_id": conversation_id}
        )
        yield (
            'data: {"type": "trace", "step": "上下文补全", '
            f'"metadata": {{"resolved_query": "{question}"}}}}\n\n'
        )


class FakeMemoryStore:
    def __init__(self):
        self.cleared = []

    async def clear(self, conversation_id):
        self.cleared.append(conversation_id)


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

    def test_evaluate_case_passes_trace_metadata_expectations(self):
        case = {
            "id": "region_gmv",
            "question": "统计各地区 GMV",
            "expect": {
                "status": "success",
                "trace_metadata": [
                    {
                        "step": "制定查询计划",
                        "key": "need_clarification",
                        "equals": False,
                    },
                    {
                        "step": "评估SQL答案",
                        "key": "decision",
                        "equals": "pass",
                    },
                ],
            },
        }
        events = [
            {
                "type": "trace",
                "step": "制定查询计划",
                "metadata": {"need_clarification": False},
            },
            {
                "type": "trace",
                "step": "评估SQL答案",
                "metadata": {"decision": "pass"},
            },
            {"type": "result", "data": [{"地区": "华东", "GMV": 100}]},
        ]

        result = evaluate_case(case, events, duration_ms=42)

        self.assertTrue(result["passed"])
        self.assertEqual(result["failures"], [])

    def test_evaluate_case_reports_trace_metadata_mismatch(self):
        case = {
            "id": "region_gmv",
            "question": "统计各地区 GMV",
            "expect": {
                "status": "success",
                "trace_metadata": [
                    {
                        "step": "评估SQL答案",
                        "key": "decision",
                        "equals": "pass",
                    }
                ],
            },
        }
        events = [
            {
                "type": "trace",
                "step": "评估SQL答案",
                "metadata": {"decision": "revise_sql"},
            },
            {"type": "result", "data": [{"地区": "华东", "GMV": 100}]},
        ]

        result = evaluate_case(case, events, duration_ms=42)

        self.assertFalse(result["passed"])
        self.assertIn(
            "轨迹元数据不匹配：节点 评估SQL答案 的 decision 期望 pass，实际 revise_sql",
            result["failures"],
        )

    def test_evaluate_case_passes_trace_metadata_contains_expectation(self):
        case = {
            "id": "follow_up",
            "question": "那华东呢",
            "expect": {
                "status": "success",
                "trace_metadata": [
                    {
                        "step": "上下文补全",
                        "key": "resolved_query",
                        "contains": "华东",
                    }
                ],
            },
        }
        events = [
            {
                "type": "trace",
                "step": "上下文补全",
                "metadata": {"resolved_query": "统计 2026 年第一季度华东地区 GMV"},
            },
            {"type": "result", "data": [{"GMV": 100}]},
        ]

        result = evaluate_case(case, events, duration_ms=42)

        self.assertTrue(result["passed"])

    def test_evaluate_case_reports_trace_metadata_contains_mismatch(self):
        case = {
            "id": "follow_up",
            "question": "那华东呢",
            "expect": {
                "status": "success",
                "trace_metadata": [
                    {
                        "step": "上下文补全",
                        "key": "resolved_query",
                        "contains": "华东",
                    }
                ],
            },
        }
        events = [
            {
                "type": "trace",
                "step": "上下文补全",
                "metadata": {"resolved_query": "统计 2026 年第一季度华北地区 GMV"},
            },
            {"type": "result", "data": [{"GMV": 100}]},
        ]

        result = evaluate_case(case, events, duration_ms=42)

        self.assertFalse(result["passed"])
        self.assertIn(
            "轨迹元数据不包含：节点 上下文补全 的 resolved_query 期望包含 华东",
            result["failures"][0],
        )

    def test_collect_case_events_runs_conversation_with_same_id(self):
        query_service = FakeQueryService()
        query_service.conversation_memory_store = FakeMemoryStore()
        case = {
            "id": "follow_up",
            "conversation": ["统计第一季度各大区 GMV", "那华东呢"],
        }

        events = asyncio.run(collect_case_events(query_service, case))

        self.assertEqual(
            query_service.calls,
            [
                {
                    "question": "统计第一季度各大区 GMV",
                    "conversation_id": "eval-follow_up",
                },
                {
                    "question": "那华东呢",
                    "conversation_id": "eval-follow_up",
                },
            ],
        )
        self.assertEqual(
            query_service.conversation_memory_store.cleared,
            ["eval-follow_up"],
        )
        self.assertEqual(events[-1]["metadata"]["resolved_query"], "那华东呢")


if __name__ == "__main__":
    unittest.main()
