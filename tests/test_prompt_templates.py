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


if __name__ == "__main__":
    unittest.main()
