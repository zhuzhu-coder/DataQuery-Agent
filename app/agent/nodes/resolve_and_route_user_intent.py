"""
入口意图解析节点

一次性完成会话追问补全、普通/数据查询意图分类和危险意图拦截。
解析失败时按普通回答处理，避免误进入数据库查询流程。
"""

import re
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langgraph.runtime import Runtime

from app.agent.context import DataQueryAgentContext
from app.agent.intent import IntentCategory, IntentDecision, parse_intent_payload
from app.agent.llm import llm
from app.agent.state import ConversationTurnState, DataQueryAgentState
from app.agent.trace import emit_trace
from app.core.log import logger
from app.prompt.prompt_loader import load_prompt

SECURITY_ERROR_MESSAGE = (
    "当前系统只允许只读 SELECT 数据查询，"
    "不允许删除、修改、写入、清空或绕过权限。"
)
DEFAULT_GENERAL_ANSWER = "你好，我是 Data Query Agent，可以帮你查询和分析电商数据。"

UNSAFE_PATTERNS = [
    r"\bdrop\s+(table|database|schema|view)\b",
    r"\btruncate\s+table\b",
    r"\bdelete\s+from\b",
    r"\binsert\s+into\b",
    r"\bupdate\s+\w+\s+set\b",
    r"\balter\s+table\b",
    r"\bcreate\s+(table|database|schema|view)\b",
    r"\bgrant\b",
    r"\brevoke\b",
    r"\bexec(ute)?\b",
    r"删除",
    r"修改",
    r"写入",
    r"清空",
    r"建表",
    r"删表",
    r"改表",
    r"授权",
    r"绕过权限",
    r"忽略安全",
    r"危险\s*SQL",
]


async def resolve_and_route_user_intent(
    state: DataQueryAgentState, runtime: Runtime[DataQueryAgentContext]
):
    """解析入口问题并判断后续应该进入哪条分支"""

    writer = runtime.stream_writer
    step = "入口解析"
    writer({"type": "progress", "step": step, "status": "running"})

    query = state["query"]
    history = state.get("conversation_history") or []
    try:
        try:
            raw_result = await _resolve_and_classify_with_llm(query, history)
            result = _normalize_entry_result(raw_result, query)
        except Exception as e:
            logger.warning(f"{step} failed, answer as general chat: {e}")
            result = _fallback_entry_result(
                query,
                "模型无法完成入口解析，为避免误查数据库，本次不进入数据库查询流程，按普通问题回答。",
            )

        resolved_query = result["resolved_query"]
        decision = _decision_from_entry_result(result)
        # 检查是否包含危险意图线索
        unsafe_terms = _unsafe_terms([query, resolved_query])
        if unsafe_terms:
            decision = IntentDecision(
                category=IntentCategory.UNSAFE,
                reason="原始问题或补全问题包含危险操作或非只读 SQL 意图。",
                matched_terms=unsafe_terms,
            )
        is_unsafe = decision.category == IntentCategory.UNSAFE
        writer(
            {
                "type": "progress",
                "step": step,
                "status": "error" if is_unsafe else "success",
            }
        )
        emit_trace(
            writer,
            step=step,
            title="入口安全检查未通过" if is_unsafe else _trace_title(decision.category),
            summary=decision.reason,
            items=_trace_items(query, result, decision),
            metadata={
                "resolved_query": resolved_query,
                "history_count": len(history),
                "is_follow_up": bool(history),
                "intent_category": decision.category.value,
            },
        )
        logger.info(
            f"入口解析：{decision.category.value}，resolved_query={resolved_query}"
        )

        # 普通聊天生成回答
        answer = _answer_from_entry_result(result, decision)
        if answer:
            await _finish_entry_answer(state, runtime)
            writer({"type": "answer", "content": answer})

        return {
            "resolved_query": resolved_query,
            "intent_category": decision.category.value,
            "error": SECURITY_ERROR_MESSAGE if is_unsafe else None,
            "error_type": "security" if is_unsafe else None,
        }
    except Exception as e:
        logger.error(f"{step} failed: {e}")
        writer({"type": "progress", "step": step, "status": "error"})
        raise


async def _resolve_and_classify_with_llm(
    query: str,
    history: list[ConversationTurnState],
) -> dict:
    """调用模型同时生成上下文补全结果和入口意图分类"""

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", load_prompt("resolve_and_classify_user_intent")),
            MessagesPlaceholder("history"),
            ("human", "当前用户问题：{query}"),
        ]
    )
    chain = prompt | llm | JsonOutputParser()
    return await chain.ainvoke(
        {
            "query": query,
            "history": _build_history_messages(history),
        }
    )


def _build_history_messages(history: list[ConversationTurnState]) -> list[BaseMessage]:
    """将会话历史转换为 LangChain 消息对象"""

    messages: list[BaseMessage] = []
    for turn in history:
        role = str(turn.get("role") or "")
        content = str(turn.get("content") or "")
        if not content:
            continue
        if role == "system":
            messages.append(SystemMessage(content=content))
        elif role == "assistant":
            messages.append(AIMessage(content=content))
        else:
            messages.append(HumanMessage(content=content))
    return messages


def _normalize_entry_result(payload: object, query: str) -> dict[str, Any]:
    """规范化模型输出的入口解析结果"""

    if not isinstance(payload, dict):
        return _fallback_entry_result(query, "入口解析输出不可用。")

    resolved_query = str(payload.get("resolved_query") or "").strip() or query
    try:
        decision: IntentDecision = parse_intent_payload(
            {
                "category": payload.get("category"),
                "reason": payload.get("reason"),
            }
        )
    except ValueError:
        fallback = _fallback_entry_result(query, "入口意图分类结果不可用。")
        fallback["resolved_query"] = resolved_query
        fallback["answer"] = _entry_answer(payload.get("answer"))
        return fallback

    return {
        "resolved_query": resolved_query,
        "category": decision.category.value,
        "reason": decision.reason,
        "answer": (
            _entry_answer(payload.get("answer"))
            if decision.category == IntentCategory.GENERAL_CHAT
            else ""
        ),
    }


def _fallback_entry_result(query: str, reason: str) -> dict[str, Any]:
    """返回默认入口解析结果，用于处理模型输出异常情况"""
    return {
        "resolved_query": query,
        "category": IntentCategory.GENERAL_CHAT.value,
        "reason": reason,
        "answer": DEFAULT_GENERAL_ANSWER,
    }


def _decision_from_entry_result(result: dict[str, Any]) -> IntentDecision:
    return IntentDecision(
        category=IntentCategory(str(result["category"])),
        reason=str(result.get("reason") or "模型完成入口解析。"),
        matched_terms=[],
    )


def _trace_title(category: IntentCategory) -> str:
    if category == IntentCategory.GENERAL_CHAT:
        return "识别为普通问题"
    return "识别为数据查询"


def _trace_items(
    query: str,
    result: dict[str, Any],
    decision: IntentDecision,
) -> list[dict[str, str]]:
    """生成入口解析结果的跟踪项列表"""
    items = [
        {"label": "原问题", "detail": query},
        {"label": "补全后问题", "detail": str(result["resolved_query"])},
        {"label": "分类原因", "detail": decision.reason},
    ]
    if decision.matched_terms:
        items.append({"label": "危险线索", "detail": ", ".join(decision.matched_terms)})
    if decision.category == IntentCategory.GENERAL_CHAT:
        answer = _entry_answer(result.get("answer"))
        if answer:
            items.append({"label": "回答", "detail": answer})
    return items


async def _finish_entry_answer(
    state: DataQueryAgentState,
    runtime: Runtime[DataQueryAgentContext],
) -> None:
    """普通聊天在入口节点直接完成审计"""

    audit_id = state.get("audit_id")
    audit_repository = runtime.context.get("query_audit_repository")
    if audit_id and audit_repository:
        await audit_repository.finish(audit_id, status="answered", row_count=0)


def _answer_from_entry_result(
    result: dict[str, Any],
    decision: IntentDecision,
) -> str:
    """只有普通聊天才允许入口节点直接输出 answer"""

    if decision.category != IntentCategory.GENERAL_CHAT:
        return ""
    return _entry_answer(result.get("answer"))


def _entry_answer(value: object) -> str:
    answer = str(value or "").strip()
    return answer or DEFAULT_GENERAL_ANSWER


def _unsafe_terms(values: list[str]) -> list[str]:
    """从原始问题和补全问题中提取危险意图线索"""

    matched_terms: list[str] = []
    for value in values:
        text = str(value or "")
        for pattern in UNSAFE_PATTERNS:
            # 正则匹配危险意图线索，忽略大小写
            if re.search(pattern, text, flags=re.IGNORECASE):
                matched_terms.append(pattern)
    return list(dict.fromkeys(matched_terms))
