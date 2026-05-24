"""
会话级短期记忆

使用进程内缓存维护最近几轮问数摘要。当前实现面向开发和单进程部署，
后续可以在保持接口不变的情况下替换为 Redis
"""

from collections import defaultdict, deque
from dataclasses import dataclass


@dataclass
class ConversationTurn:
    """一条会话历史摘要"""

    role: str
    content: str
    summary: str = ""


class ConversationMemoryStore:
    """按 conversation_id 保存最近 N 条会话摘要"""

    def __init__(self, max_turns: int = 6):
        self._store: dict[str, deque[ConversationTurn]] = defaultdict(
            lambda: deque(maxlen=max_turns)
        )

    def get_history(self, conversation_id: str) -> list[ConversationTurn]:
        """读取指定会话的历史摘要"""

        return list(self._store.get(conversation_id, []))

    def append_turn(
        self,
        conversation_id: str,
        role: str,
        content: str,
        summary: str = "",
    ) -> None:
        """追加一条会话摘要"""

        self._store[conversation_id].append(
            ConversationTurn(role=role, content=content, summary=summary)
        )

    def clear(self, conversation_id: str) -> None:
        """清空指定会话历史"""

        self._store.pop(conversation_id, None)


conversation_memory_store = ConversationMemoryStore()
