"""
SQL 答案评估节点

在 SQL 通过安全检查和数据库 EXPLAIN 校验后，执行前再判断它是否回答了原问题
评估结果只能让图进入执行、修正、澄清或失败分支，不直接接触数据库
"""

from typing import Any

import yaml
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate
from langgraph.runtime import Runtime

from app.agent.context import DataQueryAgentContext
from app.agent.llm import llm
from app.agent.observations import observation_update
from app.agent.state import DataQueryAgentState, EvaluationResultState
from app.agent.trace import emit_trace
from app.core.log import logger
from app.prompt.prompt_loader import load_prompt

ALLOWED_DECISIONS = {"pass", "revise_sql", "need_clarification", "fail"}


async def evaluate_sql_answer(
    state: DataQueryAgentState, runtime: Runtime[DataQueryAgentContext]
):
    """评估候选 SQL 是否完整回答用户问题"""

    writer = runtime.stream_writer
    step = "评估SQL答案"
    writer({"type": "progress", "step": step, "status": "running"})

    try:
        payload = _build_prompt_payload(state)
        try:
            raw_result = await _evaluate_with_llm(payload)
            evaluation_result = _normalize_evaluation(raw_result)
        except Exception as e:
            logger.warning(f"{step} failed, block execution: {e}")
            evaluation_result = EvaluationResultState(
                decision="fail",
                reason=f"SQL 语义评估失败：{e}",
                issues=["评估器输出不可用"],
                suggested_fix="",
                clarification_question="",
            )

        # 记录评估次数
        evaluation_attempts = state.get("evaluation_attempts", 0) + 1
        decision = evaluation_result["decision"]
        error = None
        error_type = None
        if decision != "pass":
            error = (
                evaluation_result.get("suggested_fix")
                or evaluation_result.get("reason")
                or "SQL 语义评估未通过"
            )
            error_type = "semantic"

        writer({"type": "progress", "step": step, "status": "success"})
        emit_trace(
            writer,
            step=step,
            title=_decision_title(decision),
            summary=evaluation_result.get("reason", ""),
            items=_trace_items(state["sql"], evaluation_result),
            metadata={
                "decision": decision,
                "evaluation_attempts": evaluation_attempts,
            },
        )
        return {
            "evaluation_result": evaluation_result,
            "evaluation_attempts": evaluation_attempts,
            "error": error,
            "error_type": error_type,
            **observation_update(
                "evaluate_sql_answer",
                f"SQL 语义评估结果：{decision}",
                {
                    "decision": decision,
                    "evaluation_attempts": evaluation_attempts,
                    "issue_count": len(evaluation_result.get("issues") or []),
                },
            ),
        }
    except Exception as e:
        logger.error(f"{step} failed: {e}")
        writer({"type": "progress", "step": step, "status": "error"})
        raise


async def _evaluate_with_llm(payload: dict[str, Any]) -> dict:
    """调用模型评估 SQL 是否满足原问题"""

    prompt = PromptTemplate(
        template=load_prompt("evaluate_sql_answer"),
        input_variables=[
            "query",
            "sql",
            "agent_plan",
            "table_infos",
            "metric_infos",
            "date_info",
            "db_info",
        ],
    )
    chain = prompt | llm | JsonOutputParser()
    return await chain.ainvoke(payload)


def _build_prompt_payload(state: DataQueryAgentState) -> dict[str, Any]:
    """构建评估 SQL 答案的 Prompt 输入"""
    return {
        "query": state["query"],
        "sql": state["sql"],
        "agent_plan": yaml.dump(
            state.get("agent_plan") or {}, allow_unicode=True, sort_keys=False
        ),
        "table_infos": yaml.dump(
            state.get("table_infos") or [], allow_unicode=True, sort_keys=False
        ),
        "metric_infos": yaml.dump(
            state.get("metric_infos") or [], allow_unicode=True, sort_keys=False
        ),
        "date_info": yaml.dump(
            state.get("date_info") or {}, allow_unicode=True, sort_keys=False
        ),
        "db_info": yaml.dump(
            state.get("db_info") or {}, allow_unicode=True, sort_keys=False
        ),
    }


def _normalize_evaluation(payload: object) -> EvaluationResultState:
    """归一化 SQL 评估结果"""
    if not isinstance(payload, dict):
        raise ValueError("SQL 评估结果必须是 JSON 对象")
    
    decision = str(payload.get("decision") or "fail")
    if decision not in ALLOWED_DECISIONS:
        decision = "fail"

    return EvaluationResultState(
        decision=decision,
        reason=str(payload.get("reason") or ""),
        issues=_string_list(payload.get("issues")),
        suggested_fix=str(payload.get("suggested_fix") or ""),
        clarification_question=str(payload.get("clarification_question") or ""),
    )


def _string_list(value: object) -> list[str]:
    """将对象转换为字符串列表"""
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item is not None]


def _decision_title(decision: str) -> str:
    return {
        "pass": "SQL 回答评估通过",
        "revise_sql": "SQL 需要语义修正",
        "need_clarification": "需要用户补充口径",
        "fail": "SQL 回答评估失败",
    }.get(decision, "SQL 回答评估失败")


def _trace_items(sql: str, evaluation_result: EvaluationResultState) -> list[dict[str, str]]:
    items = [{"label": "候选 SQL", "detail": sql}]
    issues = evaluation_result.get("issues") or []
    if issues:
        items.append({"label": "发现问题", "detail": "；".join(issues)})
    suggested_fix = evaluation_result.get("suggested_fix")
    if suggested_fix:
        items.append({"label": "修正建议", "detail": suggested_fix})
    clarification_question = evaluation_result.get("clarification_question")
    if clarification_question:
        items.append({"label": "澄清问题", "detail": clarification_question})
    return items
