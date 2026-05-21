"""
SQL 安全白名单服务

负责在数据库执行前对模型生成的 SQL 做结构化校验和受控改写
这里依赖 sqlglot 解析 SQL AST，避免用字符串规则承担核心安全判断
"""

from dataclasses import dataclass
from typing import Any

import sqlglot
from sqlglot import exp


class SQLSecurityError(ValueError):
    """SQL 安全校验失败"""


@dataclass(frozen=True)
class SQLSecurityService:
    """校验 SQL 是否只访问允许的表字段，并统一限制返回行数"""

    max_rows: int # 最大返回行数
    allowed_functions: list[str] # 允许的函数
    forbid_cross_database: bool = True # 是否禁止跨数据库查询，默认禁止
    dialect: str = "mysql" # 数据库方言，默认 MySQL

    def validate_and_rewrite(self, sql: str, table_infos: list[dict[str, Any]]) -> str:
        """校验 SQL 并返回带安全 LIMIT 的 SQL"""
        # 1.拒绝注释
        self._reject_comment_tokens(sql)
        # 将 SQL 解析为 AST 结构树
        expressions = sqlglot.parse(sql, read=self.dialect)
        # 2.只允许单条 SQL
        if len(expressions) != 1:
            raise SQLSecurityError("仅允许执行单条 SQL")
        # 3.只允许 SELECT 
        expression = expressions[0]
        if not isinstance(expression, exp.Select):
            raise SQLSecurityError("仅允许执行 SELECT 查询")
        # 生成表和字段白名单
        allowed_columns_by_table = self._allowed_columns_by_table(table_infos)
        # 5.检查表
        alias_to_table = self._validate_tables(expression, allowed_columns_by_table)
        # 6.检查字段
        self._validate_columns(expression, allowed_columns_by_table, alias_to_table)
        # 7.检查函数
        self._validate_functions(expression)
        # 8.补 LIMIT
        self._apply_limit(expression)
        return expression.sql(dialect=self.dialect)

    def _reject_comment_tokens(self, sql: str):
        """拒绝 SQL 注释，避免通过注释隐藏多语句或危险片段"""

        if "--" in sql or "#" in sql or "/*" in sql or "*/" in sql:
            raise SQLSecurityError("SQL 中不允许包含注释")

    def _allowed_columns_by_table(
        self, table_infos: list[dict[str, Any]]
    ) -> dict[str, set[str]]:
        """根据表信息生成表字段白名单"""
        allowed: dict[str, set[str]] = {}
        for table_info in table_infos:
            table_name = table_info["name"]
            columns = table_info.get("columns", [])
            allowed[table_name] = {
                column["name"] if isinstance(column, dict) else column.name
                for column in columns
            }
        return allowed

    def _validate_tables(
        self,
        expression: exp.Expression,
        allowed_columns_by_table: dict[str, set[str]],
    ) -> dict[str, str]:
        """检查 SQL 中的表是否在白名单中"""
        alias_to_table: dict[str, str] = {}
        for table in expression.find_all(exp.Table):
            if self.forbid_cross_database and table.db:
                raise SQLSecurityError("不允许跨库查询")

            table_name = table.name
            if table_name not in allowed_columns_by_table:
                raise SQLSecurityError(f"表不在白名单中：{table_name}")

            alias_to_table[table_name] = table_name
            # 记录表别名
            if table.alias:
                alias_to_table[table.alias] = table_name
        return alias_to_table

    def _validate_columns(
        self,
        expression: exp.Expression,
        allowed_columns_by_table: dict[str, set[str]],
        alias_to_table: dict[str, str],
    ):
        """检查 SQL 中的字段是否在白名单中"""
        for star in expression.find_all(exp.Star):
            if not isinstance(star.parent, exp.Count):
                raise SQLSecurityError("不允许使用 SELECT *")

        for column in expression.find_all(exp.Column):
            column_name = column.name
            table_qualifier = column.table
            # 字段带表名或别名
            if table_qualifier:
                table_name = alias_to_table.get(table_qualifier)
                if not table_name:
                    raise SQLSecurityError(f"字段表别名不在白名单中：{table_qualifier}")
                if column_name not in allowed_columns_by_table[table_name]:
                    raise SQLSecurityError(f"字段不在白名单中：{column.sql()}")
                continue
            # 字段不带表名或别名，检查是否在白名单中
            candidate_tables = [
                table_name
                for table_name, columns in allowed_columns_by_table.items()
                if column_name in columns
            ]
            if not candidate_tables:
                raise SQLSecurityError(f"字段不在白名单中：{column_name}")
            if len(candidate_tables) > 1:
                raise SQLSecurityError(f"字段引用不明确：{column_name}")

    def _validate_functions(self, expression: exp.Expression):
        """检查 SQL 中的函数是否在白名单中"""
        allowed_functions = {name.upper() for name in self.allowed_functions}
        for function in expression.find_all(exp.Func):
            function_name = function.sql_name().upper()
            if function_name not in allowed_functions:
                raise SQLSecurityError(f"函数不在白名单中：{function_name}")

    def _apply_limit(self, expression: exp.Select):
        """检查 LIMIT 子句是否有效，若无效则补 LIMIT，有效判断是否超过最大行数"""
        limit = expression.args.get("limit")
        # LIMIT 子句不存在
        if limit is None:
            expression.set("limit", exp.Limit(expression=exp.Literal.number(self.max_rows)))
            return
        # LIMIT 子句存在，检查是否有效
        current_limit = self._literal_limit_value(limit)
        if current_limit is None or current_limit > self.max_rows:
            expression.set("limit", exp.Limit(expression=exp.Literal.number(self.max_rows)))

    def _literal_limit_value(self, limit: exp.Limit) -> int | None:
        """从 LIMIT 子句中提取整数值，返回 None 表示无效"""
        limit_expression = limit.expression
        if not isinstance(limit_expression, exp.Literal):
            return None
        try:
            return int(limit_expression.this)
        except (TypeError, ValueError):
            return None
