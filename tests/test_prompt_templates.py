import unittest

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from app.prompt.prompt_loader import load_prompt


class PromptTemplatesTest(unittest.TestCase):
    def test_resolve_and_classify_prompt_formats_with_history_and_query_variables(self):
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", load_prompt("resolve_and_classify_user_intent")),
                MessagesPlaceholder("history"),
                ("human", "当前用户问题：{query}"),
            ]
        )

        formatted = prompt.format_messages(history=[], query="你好")
        system_content = formatted[0].content

        self.assertEqual(set(prompt.input_variables), {"history", "query"})
        self.assertIn('"category":"general_chat"', system_content)
        self.assertIn("resolved_query", system_content)
        self.assertIn("answer", system_content)
        self.assertNotIn("is_follow_up", system_content)
        self.assertNotIn("inherited_context", system_content)
        self.assertNotIn("new_constraints", system_content)
        self.assertNotIn("matched_terms", system_content)

    def test_evaluate_sql_prompt_uses_compact_feedback_schema(self):
        prompt = load_prompt("evaluate_sql_answer")

        self.assertIn("decision", prompt)
        self.assertIn("suggested_fix", prompt)
        self.assertIn("clarification_question", prompt)
        self.assertNotIn("issues", prompt)
        self.assertNotIn("{agent_plan}", prompt)
        self.assertNotIn("{table_infos}", prompt)
        self.assertNotIn("{metric_infos}", prompt)
        self.assertNotIn("{date_info}", prompt)
        self.assertNotIn("{db_info}", prompt)

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
