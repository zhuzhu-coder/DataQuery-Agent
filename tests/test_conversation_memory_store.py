import unittest

from app.services.conversation_memory import ConversationMemoryStore


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.expires = {}

    async def rpush(self, key, *values):
        self.values.setdefault(key, [])
        self.values[key].extend(values)

    async def lrange(self, key, start, end):
        items = list(self.values.get(key, []))
        if end == -1:
            return items[start:]
        return items[start : end + 1]

    async def llen(self, key):
        return len(self.values.get(key, []))

    async def ltrim(self, key, start, end):
        items = list(self.values.get(key, []))
        length = len(items)
        start = start + length if start < 0 else start
        end = end + length if end < 0 else end
        start = max(start, 0)
        end = min(end, length - 1)
        self.values[key] = items[start : end + 1] if start <= end else []

    async def delete(self, *keys):
        for key in keys:
            self.values.pop(key, None)
            self.expires.pop(key, None)

    async def get(self, key):
        return self.values.get(key)

    async def set(self, key, value, ex=None):
        self.values[key] = value
        if ex is not None:
            self.expires[key] = ex

    async def expire(self, key, seconds):
        self.expires[key] = seconds


class ConversationMemoryStoreTest(unittest.IsolatedAsyncioTestCase):
    async def test_appends_and_reads_role_content_messages_without_summary(self):
        redis = FakeRedis()
        store = ConversationMemoryStore(redis, key_prefix="test", ttl_seconds=60)

        await store.append_message("conv-1", role="user", content="第一轮")
        await store.append_message("conv-1", role="assistant", content="第一轮结果")
        await store.append_message("conv-2", role="user", content="其他会话")

        history = await store.get_history("conv-1")

        self.assertEqual([turn.role for turn in history], ["user", "assistant"])
        self.assertEqual([turn.content for turn in history], ["第一轮", "第一轮结果"])
        self.assertFalse(hasattr(history[0], "summary"))
        self.assertEqual(
            [turn.content for turn in await store.get_history("conv-2")],
            ["其他会话"],
        )

    async def test_compacts_old_active_messages_and_keeps_recent_window(self):
        redis = FakeRedis()
        store = ConversationMemoryStore(
            redis,
            key_prefix="test",
            ttl_seconds=60,
            max_messages_before_compaction=4,
            recent_messages_after_compaction=2,
        )
        for index in range(1, 6):
            await store.append_message("conv-1", role="user", content=f"消息{index}")

        calls = []

        async def compressor(old_context, messages):
            calls.append((old_context, [message.content for message in messages]))
            return "压缩：消息1-消息3"

        compacted = await store.compact_if_needed("conv-1", compressor)
        history = await store.get_history("conv-1")

        self.assertTrue(compacted)
        self.assertEqual(calls, [("", ["消息1", "消息2", "消息3"])])
        self.assertEqual(history[0].role, "system")
        self.assertIn("压缩：消息1-消息3", history[0].content)
        self.assertEqual([turn.content for turn in history[1:]], ["消息4", "消息5"])

    async def test_compaction_rolls_previous_context_into_next_context(self):
        redis = FakeRedis()
        store = ConversationMemoryStore(
            redis,
            key_prefix="test",
            ttl_seconds=60,
            max_messages_before_compaction=4,
            recent_messages_after_compaction=2,
        )
        for index in range(1, 6):
            await store.append_message("conv-1", role="user", content=f"消息{index}")

        async def first_compressor(old_context, messages):
            return "第一段压缩"

        await store.compact_if_needed("conv-1", first_compressor)
        for index in range(6, 9):
            await store.append_message("conv-1", role="user", content=f"消息{index}")

        calls = []

        async def second_compressor(old_context, messages):
            calls.append((old_context, [message.content for message in messages]))
            return "第二段压缩"

        await store.compact_if_needed("conv-1", second_compressor)
        history = await store.get_history("conv-1")

        self.assertEqual(calls, [("第一段压缩", ["消息4", "消息5", "消息6"])])
        self.assertIn("第二段压缩", history[0].content)
        self.assertEqual([turn.content for turn in history[1:]], ["消息7", "消息8"])

    async def test_clear_removes_messages_and_compressed_context(self):
        redis = FakeRedis()
        store = ConversationMemoryStore(redis, key_prefix="test", ttl_seconds=60)
        await store.append_message("conv-1", role="user", content="统计 GMV")
        await redis.set("test:conv-1:context", "压缩上下文")

        await store.clear("conv-1")

        self.assertEqual(await store.get_history("conv-1"), [])


if __name__ == "__main__":
    unittest.main()
