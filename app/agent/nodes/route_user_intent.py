"""
用户意图安全检查节点

这是问数链路的入口门卫：先判断用户原始问题是否是安全的数据查询
危险意图直接拒绝，普通聊天走普通回答，只有数据查询才进入后续召回和 SQL 生成
"""

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate
from langgraph.runtime import Runtime

from app.agent.context import DataQueryAgentContext
from app.agent.intent import (
    IntentCategory,
    IntentDecision,
    parse_intent_payload,
)
from app.agent.llm import llm
from app.agent.state import DataQueryAgentState, current_query
from app.agent.trace import emit_trace
from app.core.log import logger
from app.prompt.prompt_loader import load_prompt


async def route_user_intent(
    state: DataQueryAgentState, runtime: Runtime[DataQueryAgentContext]
):
    """判断用户问题后续应该进入哪条分支"""

    writer = runtime.stream_writer
    step = "意图安全检查"
    writer({"type": "progress", "step": step, "status": "running"})

    try:
        query = _intent_query(state)
        decision = await _classify_with_llm(query)

        # 危险意图
        if decision.category == IntentCategory.UNSAFE:
            message = (
                "当前系统只允许只读 SELECT 数据查询，"
                "不允许删除、修改、写入、清空或绕过权限。"
            )
            writer({"type": "progress", "step": step, "status": "error"})
            emit_trace(
                writer,
                step=step,
                title="意图安全检查未通过",
                summary=decision.reason,
                items=[{"label": "命中风险词", "detail": ", ".join(decision.matched_terms)}]
                if decision.matched_terms
                else [],
                metadata={
                    "intent_category": decision.category.value,
                    "matched_terms": decision.matched_terms,
                },
            )
            logger.info(f"用户意图安全检查失败：{decision.reason}")
            return {
                "intent_category": decision.category.value,
                "intent_reason": decision.reason,
                "error": message,
                "error_type": "security",
            }

        # 普通意图
        writer({"type": "progress", "step": step, "status": "success"})
        emit_trace(
            writer,
            step=step,
            title=_trace_title(decision.category),
            summary=decision.reason,
            items=[{"label": "命中线索", "detail": ", ".join(decision.matched_terms)}]
            if decision.matched_terms
            else [],
            metadata={
                "intent_category": decision.category.value,
                "matched_terms": decision.matched_terms,
            },
        )
        logger.info(f"用户意图分类：{decision.category.value}，原因：{decision.reason}")
        return {
            "intent_category": decision.category.value,
            "intent_reason": decision.reason,
            "error": None,
            "error_type": None,
        }

    except Exception as e:
        logger.error(f"{step} failed: {e}")
        writer({"type": "progress", "step": step, "status": "error"})
        raise


async def _classify_with_llm(query: str) -> IntentDecision:
    """使用 LLM 分类用户意图"""
    prompt = PromptTemplate(
        template=load_prompt("classify_user_intent"),
        input_variables=["query"],
    )
    chain = prompt | llm | JsonOutputParser()
    try:
        result = await chain.ainvoke({"query": query})
        return parse_intent_payload(result) # 解析 JSON 输出
    except Exception as e:
        logger.warning(f"模型意图分类失败，按普通回答处理且不查询数据库：{e}")
        return IntentDecision(
            category=IntentCategory.GENERAL_CHAT,
            reason="模型无法完成意图分类，为避免误查数据库，本次不进入数据库查询流程，按普通问题回答。",
        )


def _trace_title(category: IntentCategory) -> str:
    if category == IntentCategory.GENERAL_CHAT:
        return "识别为普通问题"
    return "识别为数据查询"


def _intent_query(state: DataQueryAgentState) -> str:
    """意图识别同时保留原始问题和补全后问题，避免追问夹带危险意图"""

    resolved_query = current_query(state)
    original_query = state["query"]
    if resolved_query == original_query:
        return original_query
    return f"原始问题：{original_query}\n上下文补全问题：{resolved_query}"
