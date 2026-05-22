import unittest

from app.agent.trace import (
    column_trace_items,
    emit_trace,
    metric_trace_items,
    table_trace_items,
    value_trace_items,
)
from app.entities.column_info import ColumnInfo
from app.entities.metric_info import MetricInfo
from app.entities.value_info import ValueInfo


class TraceHelperTest(unittest.TestCase):
    def test_emit_trace_uses_stable_event_shape(self):
        events = []

        emit_trace(
            events.append,
            step="召回字段信息",
            title="命中 1 个相关字段",
            summary="围绕用户问题召回候选字段",
            items=[{"label": "fact_order.order_amount", "detail": "订单金额"}],
            metadata={"count": 1},
        )

        self.assertEqual(
            events,
            [
                {
                    "type": "trace",
                    "step": "召回字段信息",
                    "title": "命中 1 个相关字段",
                    "summary": "围绕用户问题召回候选字段",
                    "items": [
                        {
                            "label": "fact_order.order_amount",
                            "detail": "订单金额",
                        }
                    ],
                    "metadata": {"count": 1},
                }
            ],
        )

    def test_emit_trace_defaults_optional_fields(self):
        events = []

        emit_trace(events.append, step="执行SQL", title="执行完成")

        self.assertEqual(events[0]["summary"], "")
        self.assertEqual(events[0]["items"], [])
        self.assertEqual(events[0]["metadata"], {})

    def test_entity_trace_items_are_limited_and_readable(self):
        columns = [
            ColumnInfo(
                id="col-1",
                name="order_amount",
                type="decimal",
                role="measure",
                examples=[100],
                description="订单金额",
                alias=["GMV"],
                table_id="fact_order",
            ),
            ColumnInfo(
                id="col-2",
                name="region_name",
                type="varchar",
                role="dimension",
                examples=["华北"],
                description="地区名称",
                alias=[],
                table_id="dim_region",
            ),
        ]
        metrics = [
            MetricInfo(
                id="metric-1",
                name="销售额",
                description="订单金额汇总",
                relevant_columns=["fact_order.order_amount"],
                alias=["GMV"],
            )
        ]
        values = [
            ValueInfo(id="value-1", value="华北", column_id="dim_region.region_name")
        ]

        self.assertEqual(
            column_trace_items(columns, limit=1),
            [{"label": "fact_order.order_amount", "detail": "订单金额"}],
        )
        self.assertEqual(
            metric_trace_items(metrics),
            [{"label": "销售额", "detail": "订单金额汇总"}],
        )
        self.assertEqual(
            value_trace_items(values),
            [{"label": "华北", "detail": "dim_region.region_name"}],
        )

    def test_table_trace_items_summarize_table_and_columns(self):
        table_infos = [
            {
                "name": "fact_order",
                "description": "订单事实表",
                "columns": [
                    {"name": "order_id"},
                    {"name": "product_id"},
                    {"name": "date_id"},
                    {"name": "order_amount"},
                    {"name": "order_quantity"},
                ],
            }
        ]

        self.assertEqual(
            table_trace_items(table_infos, limit=1, column_limit=4),
            [
                {
                    "label": "fact_order",
                    "detail": "订单事实表；字段：order_id, product_id, date_id, order_amount 等 5 个字段",
                }
            ],
        )


if __name__ == "__main__":
    unittest.main()
