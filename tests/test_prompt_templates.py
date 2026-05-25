import unittest

from langchain_core.prompts import PromptTemplate

from app.prompt.prompt_loader import load_prompt


class PromptTemplatesTest(unittest.TestCase):
    def test_classify_user_intent_prompt_formats_with_only_query_variable(self):
        prompt = PromptTemplate(
            template=load_prompt("classify_user_intent"),
            input_variables=["query"],
        )

        formatted = prompt.format(query="你好")

        self.assertIn("用户问题：\n你好", formatted)
        self.assertIn('{"category":"general_chat"', formatted)

    def test_generate_sql_prompt_constrains_dates_and_qualified_columns(self):
        prompt = load_prompt("generate_sql")

        self.assertIn("字段必须使用表别名限定", prompt)
        self.assertIn("date_id BETWEEN 20260301 AND 20260331", prompt)
        self.assertIn("不要为了日期过滤生成 `YEAR`、`MONTH`、`DATE`、`CONCAT`", prompt)

    def test_correct_sql_prompt_prevents_ambiguous_date_fix(self):
        prompt = load_prompt("correct_sql")

        self.assertIn("禁止输出未限定表别名的裸字段", prompt)
        self.assertIn("禁止输出 `date_id BETWEEN ...` 这种歧义字段", prompt)
        self.assertIn("月份和季度优先转成 `date_id BETWEEN yyyymmdd AND yyyymmdd`", prompt)


if __name__ == "__main__":
    unittest.main()
