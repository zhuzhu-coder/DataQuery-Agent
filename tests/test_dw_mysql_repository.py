import asyncio
import unittest

from app.repositories.mysql.dw.dw_mysql_repository import DWMySQLRepository


class FakeMappings:
    def fetchall(self):
        return [{"order_id": "ORD001"}]


class FakeResult:
    def mappings(self):
        return FakeMappings()


class FakeSession:
    bind = None

    def __init__(self):
        self.executed_sql = []

    async def execute(self, statement):
        self.executed_sql.append(str(statement))
        return FakeResult()


class DWMySQLRepositoryTest(unittest.TestCase):
    def test_run_safe_sets_statement_timeout_before_query(self):
        session = FakeSession()
        repository = DWMySQLRepository(session)

        result = asyncio.run(
            repository.run_safe(
                "SELECT order_id FROM fact_order LIMIT 10",
                timeout_seconds=3,
            )
        )

        self.assertEqual(result, [{"order_id": "ORD001"}])
        self.assertEqual(
            session.executed_sql[0],
            "SET SESSION MAX_EXECUTION_TIME = 3000",
        )
        self.assertEqual(
            session.executed_sql[1],
            "SELECT order_id FROM fact_order LIMIT 10",
        )


if __name__ == "__main__":
    unittest.main()
