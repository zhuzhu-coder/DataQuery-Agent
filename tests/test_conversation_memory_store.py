import unittest

from app.services.conversation_memory import ConversationMemoryStore


class ConversationMemoryStoreTest(unittest.TestCase):
    def test_keeps_recent_turns_by_conversation_id(self):
        store = ConversationMemoryStore(max_turns=3)

        store.append_turn("conv-1", role="user", content="第一轮")
        store.append_turn("conv-1", role="assistant", content="第一轮结果")
        store.append_turn("conv-1", role="user", content="第二轮")
        store.append_turn("conv-1", role="assistant", content="第二轮结果")
        store.append_turn("conv-2", role="user", content="其他会话")

        history = store.get_history("conv-1")

        self.assertEqual([turn.content for turn in history], ["第一轮结果", "第二轮", "第二轮结果"])
        self.assertEqual([turn.content for turn in store.get_history("conv-2")], ["其他会话"])

    def test_clear_removes_conversation_history(self):
        store = ConversationMemoryStore(max_turns=3)
        store.append_turn("conv-1", role="user", content="统计 GMV")

        store.clear("conv-1")

        self.assertEqual(store.get_history("conv-1"), [])


if __name__ == "__main__":
    unittest.main()
