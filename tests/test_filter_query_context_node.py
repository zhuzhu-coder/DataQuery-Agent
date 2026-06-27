import asyncio
import unittest
from unittest.mock import patch

from app.agent.nodes.filter_query_context import filter_query_context


class FakeRuntime:
    def __init__(self):
        self.events = []
        self.context = {}

    def stream_writer(self, event):
        self.events.append(event)


def _state():
    return {
        "query": "统计华东 GMV",
        "table_infos": [
            {
                "name": "fact_order",
                "role": "fact",
                "description": "订单事实表",
                "columns": [
                    {
                        "name": "order_amount",
                        "type": "decimal",
                        "role": "measure",
                        "examples": [],
                        "description": "订单金额",
                        "alias": ["销售额"],
                    },
                    {
                        "name": "region_id",
                        "type": "int",
                        "role": "foreign_key",
                        "examples": [],
                        "description": "地区外键",
                        "alias": [],
                    },
                    {
                        "name": "customer_id",
                        "type": "int",
                        "role": "foreign_key",
                        "examples": [],
                        "description": "客户外键",
                        "alias": [],
                    },
                ],
            },
            {
                "name": "dim_region",
                "role": "dim",
                "description": "地区维度表",
                "columns": [
                    {
                        "name": "region_id",
                        "type": "int",
                        "role": "primary_key",
                        "examples": [],
                        "description": "地区主键",
                        "alias": [],
                    },
                    {
                        "name": "region_name",
                        "type": "varchar",
                        "role": "dimension",
                        "examples": ["华东"],
                        "description": "大区名称",
                        "alias": ["地区"],
                    },
                ],
            },
        ],
        "metric_infos": [
            {
                "name": "GMV",
                "description": "成交总额",
                "relevant_columns": ["fact_order.order_amount"],
                "alias": ["销售额"],
            },
            {
                "name": "AOV",
                "description": "平均订单金额",
                "relevant_columns": ["fact_order.order_amount"],
                "alias": ["平均单价"],
            },
        ],
    }


class FilterQueryContextNodeTest(unittest.TestCase):
    def test_filter_query_context_filters_tables_fields_and_metrics(self):
        runtime = FakeRuntime()

        async def fake_filter(query, table_infos, metric_infos):
            self.assertEqual(query, "统计华东 GMV")
            self.assertEqual(len(table_infos), 2)
            self.assertEqual(len(metric_infos), 2)
            return {
                "tables": {
                    "fact_order": ["order_amount", "region_id"],
                    "dim_region": ["region_id", "region_name"],
                },
                "metrics": ["GMV"],
            }

        with patch("app.agent.nodes.filter_query_context._filter_with_llm", fake_filter):
            result = asyncio.run(filter_query_context(_state(), runtime))

        self.assertEqual(
            [table["name"] for table in result["table_infos"]],
            ["fact_order", "dim_region"],
        )
        self.assertEqual(
            [column["name"] for column in result["table_infos"][0]["columns"]],
            ["order_amount", "region_id"],
        )
        self.assertEqual([metric["name"] for metric in result["metric_infos"]], ["GMV"])
        trace_events = [event for event in runtime.events if event["type"] == "trace"]
        self.assertEqual(trace_events[-1]["step"], "过滤查询上下文")
        self.assertEqual(trace_events[-1]["metadata"]["table_count"], 2)
        self.assertEqual(trace_events[-1]["metadata"]["metric_count"], 1)

    def test_filter_query_context_allows_empty_metric_selection(self):
        runtime = FakeRuntime()

        async def fake_filter(query, table_infos, metric_infos):
            return {"tables": {"dim_region": ["region_name"]}, "metrics": []}

        with patch("app.agent.nodes.filter_query_context._filter_with_llm", fake_filter):
            result = asyncio.run(filter_query_context(_state(), runtime))

        self.assertEqual([table["name"] for table in result["table_infos"]], ["dim_region"])
        self.assertEqual(result["metric_infos"], [])

    def test_filter_query_context_ignores_model_output_outside_candidates(self):
        runtime = FakeRuntime()
        original_state = _state()

        async def fake_filter(query, table_infos, metric_infos):
            return {
                "tables": {
                    "fact_order": ["order_amount", "made_up_column"],
                    "made_up_table": ["order_amount"],
                },
                "metrics": ["GMV", "made_up_metric"],
            }

        with patch("app.agent.nodes.filter_query_context._filter_with_llm", fake_filter):
            result = asyncio.run(filter_query_context(original_state, runtime))

        self.assertEqual(
            [column["name"] for column in result["table_infos"][0]["columns"]],
            ["order_amount"],
        )
        self.assertEqual([metric["name"] for metric in result["metric_infos"]], ["GMV"])
        self.assertEqual(
            [column["name"] for column in original_state["table_infos"][0]["columns"]],
            ["order_amount", "region_id", "customer_id"],
        )


if __name__ == "__main__":
    unittest.main()
