"""
普通回答节点

当用户问题不是查数问题时，直接给出自然语言回答，不进入召回、SQL 生成或数据库执行
"""

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate
from langgraph.runtime import Runtime

from app.agent.context import DataQueryAgentContext
from app.agent.llm import llm
from app.agent.state import DataQueryAgentState, current_query
from app.agent.trace import emit_trace
from app.core.log import logger
from app.prompt.prompt_loader import load_prompt


async def general_answer(
    state: DataQueryAgentState, runtime: Runtime[DataQueryAgentContext]
):
    """对非数据查询问题做普通回答"""

    writer = runtime.stream_writer
    step = "普通回答"
    writer({"type": "progress", "step": step, "status": "running"})

    try:
        query = current_query(state)
        answer = await _answer_with_llm(query)

        writer({"type": "progress", "step": step, "status": "success"})
        emit_trace(
            writer,
            step=step,
            title="已直接回答",
            summary="该问题不需要查询数据库，未进入 SQL 生成和执行流程。",
            items=[{"label": "回答", "detail": answer}],
            metadata={"intent_category": state.get("intent_category")},
        )

        audit_id = state.get("audit_id")
        audit_repository = runtime.context.get("query_audit_repository")
        if audit_id and audit_repository:
            await audit_repository.finish(audit_id, status="answered", row_count=0)

        writer({"type": "answer", "content": answer})
        return {}

    except Exception as e:
        logger.error(f"{step} failed: {e}")
        writer({"type": "progress", "step": step, "status": "error"})
        raise


async def _answer_with_llm(query: str) -> str:
    prompt = PromptTemplate(
        template=load_prompt("general_answer"),
        input_variables=["query"],
    )
    chain = prompt | llm | StrOutputParser()
    try:
        answer = (await chain.ainvoke({"query": query})).strip()
    except Exception as e:
        logger.warning(f"普通回答模型调用失败，使用兜底回复：{e}")
        answer = ""

    if answer:
        return answer
    return "你好，我是 Data Query Agent，可以帮你查询和分析电商数据。"
