import unittest

from app.agent import intent
from app.agent.intent import (
    IntentCategory,
    parse_intent_payload,
)


class UserIntentTest(unittest.TestCase):
    def test_parse_intent_payload_reads_parser_dict(self):
        decision = parse_intent_payload(
            {"category": "general_chat", "reason": "用户在打招呼"}
        )

        self.assertEqual(decision.category, IntentCategory.GENERAL_CHAT)
        self.assertEqual(decision.reason, "用户在打招呼")

    def test_parse_intent_payload_rejects_unknown_category(self):
        with self.assertRaises(ValueError):
            parse_intent_payload({"category": "other", "reason": "未知分类"})

    def test_parse_intent_payload_rejects_non_object_payload(self):
        with self.assertRaises(ValueError):
            parse_intent_payload(["general_chat"])

    def test_intent_module_does_not_keep_keyword_rule_tables(self):
        self.assertFalse(hasattr(intent, "UNSAFE_TERMS"))
        self.assertFalse(hasattr(intent, "GENERAL_CHAT_TERMS"))
        self.assertFalse(hasattr(intent, "DATA_QUERY_TERMS"))
        self.assertFalse(hasattr(intent, "classify_intent_by_rules"))
        self.assertFalse(hasattr(intent, "_extract_json_payload"))
        self.assertFalse(hasattr(intent, "parse_intent_response"))


if __name__ == "__main__":
    unittest.main()
