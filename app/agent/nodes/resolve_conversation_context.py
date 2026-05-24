"""
会话上下文补全节点

当当前请求带有会话历史时，将“那华东呢”“换成 3 月”等省略式追问
补全为可独立执行的问数问题
"""

from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langgraph.runtime import Runtime

from app.agent.context import DataQueryAgentContext
from app.agent.llm import llm
from app.agent.state import ConversationTurnState, DataQueryAgentState
from app.agent.trace import emit_trace
from app.core.log import logger
from app.prompt.prompt_loader import load_prompt


async def resolve_conversation_context(
    state: DataQueryAgentState, runtime: Runtime[DataQueryAgentContext]
):
    """根据最近会话历史补全当前问题"""

    writer = runtime.stream_writer
    step = "上下文补全"
    writer({"type": "progress", "step": step, "status": "running"})

    query = state["query"]
    history = state.get("conversation_history") or []
    try:
        if history:
            try:
                raw_result = await _resolve_with_llm(query, history)
                resolution = _normalize_resolution(raw_result, query)
            except Exception as e:
                logger.warning(f"{step} failed, use original query: {e}")
                resolution = _fallback_resolution(query, f"上下文补全失败：{e}")
        else:
            resolution = _fallback_resolution(query, "当前会话没有历史问题。")

        resolved_query = resolution["resolved_query"]
        writer({"type": "progress", "step": step, "status": "success"})
        emit_trace(
            writer,
            step=step,
            title="完成上下文补全"
            if resolution.get("is_follow_up")
            else "无需上下文补全",
            summary=resolution.get("reason", ""),
            items=[
                {"label": "原问题", "detail": query},
                {"label": "补全后问题", "detail": resolved_query},
                {
                    "label": "继承上下文",
                    "detail": "；".join(resolution.get("inherited_context") or []),
                },
                {
                    "label": "新增约束",
                    "detail": "；".join(resolution.get("new_constraints") or []),
                },
            ],
            metadata={
                "is_follow_up": resolution.get("is_follow_up", False),
                "resolved_query": resolved_query,
                "history_count": len(history),
            },
        )
        return {
            "resolved_query": resolved_query,
        }
    except Exception as e:
        logger.error(f"{step} failed: {e}")
        writer({"type": "progress", "step": step, "status": "error"})
        raise


async def _resolve_with_llm(
    query: str, history: list[ConversationTurnState]
) -> dict:
    """调用模型生成上下文补全结果"""

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", load_prompt("resolve_conversation_context")),
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
    """将会话摘要转换为 LangChain 消息对象"""

    messages: list[BaseMessage] = []
    for turn in history:
        role = str(turn.get("role") or "")
        content_parts = [str(turn.get("content") or "")]
        summary = turn.get("summary")
        if summary:
            content_parts.append(f"摘要：{summary}")
        content = "\n".join(part for part in content_parts if part)
        if not content:
            continue
        if role == "assistant":
            messages.append(AIMessage(content=content))
        else:
            messages.append(HumanMessage(content=content))
    return messages


def _normalize_resolution(payload: object, query: str) -> dict[str, Any]:
    """规范化模型输出的上下文补全结果"""

    if not isinstance(payload, dict):
        return _fallback_resolution(query, "上下文补全输出不可用。")

    resolved_query = str(payload.get("resolved_query") or "").strip() or query
    is_follow_up = bool(payload.get("is_follow_up", False)) and resolved_query != query
    return {
        "is_follow_up": is_follow_up,
        "resolved_query": resolved_query,
        "inherited_context": _string_list(payload.get("inherited_context")),
        "new_constraints": _string_list(payload.get("new_constraints")),
        "reason": str(payload.get("reason") or "已完成上下文补全。"),
    }


def _fallback_resolution(query: str, reason: str) -> dict[str, Any]:
    return {
        "is_follow_up": False,
        "resolved_query": query,
        "inherited_context": [],
        "new_constraints": [],
        "reason": reason,
    }


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item is not None]
