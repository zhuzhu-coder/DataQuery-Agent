import unittest

from app.services.sql_security_service import SQLSecurityError, SQLSecurityService


class SQLSecurityServiceTest(unittest.TestCase):
    def setUp(self):
        self.table_infos = [
            {
                "name": "fact_order",
                "role": "fact",
                "description": "订单事实表",
                "columns": [
                    {"name": "order_id"},
                    {"name": "order_amount"},
                    {"name": "region_id"},
                ],
            },
            {
                "name": "dim_region",
                "role": "dim",
                "description": "地区维度表",
                "columns": [
                    {"name": "region_id"},
                    {"name": "region_name"},
                ],
            },
        ]
        self.service = SQLSecurityService(
            max_rows=200,
            allowed_functions=["SUM", "COUNT", "AVG", "MIN", "MAX"],
            forbid_cross_database=True,
        )

    def test_allows_known_select_and_adds_default_limit(self):
        sql = (
            "SELECT r.region_name AS region_name, "
            "SUM(o.order_amount) AS gmv "
            "FROM fact_order o "
            "JOIN dim_region r ON o.region_id = r.region_id "
            "GROUP BY r.region_name"
        )

        safe_sql = self.service.validate_and_rewrite(sql, self.table_infos)

        self.assertIn("FROM fact_order AS o", safe_sql)
        self.assertIn("JOIN dim_region AS r", safe_sql)
        self.assertTrue(safe_sql.endswith("LIMIT 200"))

    def test_clamps_existing_limit_to_max_rows(self):
        safe_sql = self.service.validate_and_rewrite(
            "SELECT order_id FROM fact_order LIMIT 1000",
            self.table_infos,
        )

        self.assertTrue(safe_sql.endswith("LIMIT 200"))

    def test_keeps_existing_limit_below_max_rows(self):
        safe_sql = self.service.validate_and_rewrite(
            "SELECT order_id FROM fact_order LIMIT 50",
            self.table_infos,
        )

        self.assertTrue(safe_sql.endswith("LIMIT 50"))

    def test_rejects_non_select_statement(self):
        with self.assertRaises(SQLSecurityError):
            self.service.validate_and_rewrite(
                "DELETE FROM fact_order",
                self.table_infos,
            )

    def test_rejects_multiple_statements(self):
        with self.assertRaises(SQLSecurityError):
            self.service.validate_and_rewrite(
                "SELECT order_id FROM fact_order; DROP TABLE fact_order",
                self.table_infos,
            )

    def test_rejects_cross_database_table(self):
        with self.assertRaises(SQLSecurityError):
            self.service.validate_and_rewrite(
                "SELECT user FROM mysql.user",
                self.table_infos,
            )

    def test_rejects_unknown_table(self):
        with self.assertRaises(SQLSecurityError):
            self.service.validate_and_rewrite(
                "SELECT id FROM unknown_table",
                self.table_infos,
            )

    def test_rejects_unknown_column(self):
        with self.assertRaises(SQLSecurityError):
            self.service.validate_and_rewrite(
                "SELECT password FROM fact_order",
                self.table_infos,
            )

    def test_rejects_star_projection(self):
        with self.assertRaises(SQLSecurityError):
            self.service.validate_and_rewrite(
                "SELECT * FROM fact_order",
                self.table_infos,
            )

    def test_allows_count_star(self):
        safe_sql = self.service.validate_and_rewrite(
            "SELECT COUNT(*) AS order_count FROM fact_order",
            self.table_infos,
        )

        self.assertTrue(safe_sql.endswith("LIMIT 200"))

    def test_rejects_disallowed_function(self):
        with self.assertRaises(SQLSecurityError):
            self.service.validate_and_rewrite(
                "SELECT SLEEP(1) FROM fact_order",
                self.table_infos,
            )


if __name__ == "__main__":
    unittest.main()
