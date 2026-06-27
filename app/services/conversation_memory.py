"""
会话级短期记忆

基于 Redis 维护当前会话的滚动上下文。active messages 保存尚未压缩的
最近原始消息；compressed context 保存被折叠后的早期对话上下文
"""

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any


@dataclass
class ConversationTurn:
    """一条会话消息"""
    role: str
    content: str


ContextCompressor = Callable[[str, list[ConversationTurn]], Awaitable[str]]


class ConversationMemoryStore:
    """按 conversation_id 保存滚动压缩后的会话上下文"""

    def __init__(
        self,
        redis_client: Any,
        key_prefix: str,
        ttl_seconds: int,
        max_messages_before_compaction: int = 20,
        recent_messages_after_compaction: int = 6,
    ):
        self.redis = redis_client
        self.key_prefix = key_prefix.rstrip(":")
        self.ttl_seconds = ttl_seconds
        self.max_messages_before_compaction = max_messages_before_compaction
        self.recent_messages_after_compaction = recent_messages_after_compaction

    async def get_history(self, conversation_id: str) -> list[ConversationTurn]:
        """读取压缩上下文和当前活跃消息，供入口解析节点使用"""
        # 读取压缩上下文
        compressed_context = await self._get_compressed_context(conversation_id)
        # 读取当前活跃消息
        active_messages = await self._get_active_messages(conversation_id)
        if not compressed_context:
            return active_messages
        return [
            ConversationTurn(
                role="system",
                content=f"以下是之前对话的压缩上下文：\n{compressed_context}",
            ),
            *active_messages,
        ]

    async def append_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
    ) -> None:
        """追加一条尚未压缩的原始消息"""

        if not content:
            return
        await self.redis.rpush(
            self._messages_key(conversation_id),
            json.dumps(
                {"role": role, "content": content},
                ensure_ascii=False,  # 保持原始编码
            ),
        )
        await self._refresh_ttl(conversation_id)

    async def compact_if_needed(
        self,
        conversation_id: str,
        compressor: ContextCompressor,
    ) -> bool:
        """超过阈值时滚动压缩较早消息，只保留最近消息窗口"""

        # 消息数
        message_count = await self.redis.llen(self._messages_key(conversation_id))
        if message_count <= self.max_messages_before_compaction:
            return False

        active_messages = await self._get_active_messages(conversation_id)
        keep_count = max(1, self.recent_messages_after_compaction)
        # 压缩消息
        compact_messages = active_messages[:-keep_count]
        if not compact_messages:
            return False

        # 读取旧压缩上下文
        old_context = await self._get_compressed_context(conversation_id)
        # 生成新压缩上下文
        new_context = await compressor(old_context, compact_messages)
        if not new_context:
            return False

        context_key = self._context_key(conversation_id)
        messages_key = self._messages_key(conversation_id)
        # 写入新压缩上下文，覆盖旧上下文
        await self.redis.set(context_key, new_context, ex=self.ttl_seconds)
        # 只保留最近消息窗口，较早消息已进入压缩上下文
        await self.redis.ltrim(messages_key, -keep_count, -1)
        await self._refresh_ttl(conversation_id)
        return True

    async def clear(self, conversation_id: str) -> None:
        """清空指定会话记忆"""

        await self.redis.delete(
            self._messages_key(conversation_id),
            self._context_key(conversation_id),
        )

    async def _get_active_messages(
        self, conversation_id: str
    ) -> list[ConversationTurn]:
        """读取当前活跃消息"""
        # 读取所有消息
        items = await self.redis.lrange(self._messages_key(conversation_id), 0, -1)
        messages: list[ConversationTurn] = []
        for item in items:
            payload = _load_json(item)
            if not isinstance(payload, dict):
                continue
            role = str(payload.get("role") or "")
            content = str(payload.get("content") or "")
            if role and content:
                messages.append(ConversationTurn(role=role, content=content))
        return messages

    async def _get_compressed_context(self, conversation_id: str) -> str:
        """读取压缩上下文文本"""
        value = await self.redis.get(self._context_key(conversation_id))
        return _decode_text(value).strip()

    async def _refresh_ttl(self, conversation_id: str) -> None:
        """刷新会话记忆的过期时间"""
        await self.redis.expire(self._messages_key(conversation_id), self.ttl_seconds)
        await self.redis.expire(self._context_key(conversation_id), self.ttl_seconds)

    def _messages_key(self, conversation_id: str) -> str:
        """生成活跃消息的 Redis Key"""
        return f"{self.key_prefix}:{conversation_id}:messages"

    def _context_key(self, conversation_id: str) -> str:
        """生成压缩上下文的 Redis Key"""
        return f"{self.key_prefix}:{conversation_id}:context"


def _load_json(value: Any) -> Any:
    """安全地解析 JSON，失败时返回 None"""
    try:
        # 解码为字符串，再解析 JSON
        return json.loads(_decode_text(value))
    except (TypeError, ValueError):
        return None


def _decode_text(value: Any) -> str:
    """将 Redis 中的值解码为字符串，非字符串类型返回空字符串"""
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)
