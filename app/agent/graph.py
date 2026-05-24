"""
Data Query Agent 图编排

使用 LangGraph 把各个节点串成一条可观测的执行链路
当前链路先由 Planner 制定查询计划，再由 Tool Executor 执行受控召回工具，
随后合并工具观察结果，过滤候选表和指标，补充额外上下文，最后生成 校验 评估 修正并执行 SQL
"""

from langgraph.constants import END, START
from langgraph.graph import StateGraph

from app.agent.context import DataQueryAgentContext
from app.agent.nodes.add_extra_context import add_extra_context
from app.agent.nodes.ask_clarification import ask_clarification
from app.agent.nodes.correct_sql import correct_sql
from app.agent.nodes.evaluate_sql_answer import evaluate_sql_answer
from app.agent.nodes.extract_keywords import extract_keywords
from app.agent.nodes.fail_query import fail_query
from app.agent.nodes.filter_metric import filter_metric
from app.agent.nodes.filter_table import filter_table
from app.agent.nodes.general_answer import general_answer
from app.agent.nodes.generate_sql import generate_sql
from app.agent.nodes.merge_retrieved_info import merge_retrieved_info
from app.agent.nodes.plan_query import plan_query
from app.agent.nodes.resolve_conversation_context import resolve_conversation_context
from app.agent.nodes.route_user_intent import route_user_intent
from app.agent.nodes.run_sql import run_sql
from app.agent.nodes.security_check_sql import security_check_sql
from app.agent.nodes.tool_executor import tool_executor
from app.agent.nodes.validate_sql import validate_sql
from app.agent.state import DataQueryAgentState


def route_conversation_entry(state: DataQueryAgentState) -> str:
    """第一轮直接识别意图，有历史时先做上下文补全"""

    if state.get("conversation_history"):
        return "resolve_conversation_context"
    return "route_user_intent"


def route_sql_evaluation(state: DataQueryAgentState) -> str:
    """根据 SQL 语义评估结果选择执行、修正、澄清或失败"""

    decision = (state.get("evaluation_result") or {}).get("decision")
    if decision == "pass":
        return "run_sql"
    if decision == "revise_sql":
        if state.get("evaluation_attempts", 0) >= 2:
            return "fail_query"
        if state.get("correction_attempts", 0) >= 1:
            return "fail_query"
        return "correct_sql"
    if decision == "need_clarification":
        return "ask_clarification"
    return "fail_query"


# StateGraph 声明整张图使用的状态结构和运行时上下文结构
graph_builder = StateGraph(
    state_schema=DataQueryAgentState, context_schema=DataQueryAgentContext
)

# 注册节点：每个节点负责问数链路中的一个清晰步骤
graph_builder.add_node("route_user_intent", route_user_intent) # 意图安全检查和话题路由
graph_builder.add_node("resolve_conversation_context", resolve_conversation_context) # 多轮上下文补全
graph_builder.add_node("general_answer", general_answer) # 普通回答
graph_builder.add_node("plan_query", plan_query) # 制定查询计划
graph_builder.add_node("ask_clarification", ask_clarification) # 澄清查询口径
graph_builder.add_node("extract_keywords", extract_keywords) # 抽取用户问题关键词
graph_builder.add_node("tool_executor", tool_executor) # 执行 Planner 工具调用
graph_builder.add_node("merge_retrieved_info", merge_retrieved_info) # 合并召回信息
graph_builder.add_node("filter_metric", filter_metric) # 过滤指标信息
graph_builder.add_node("filter_table", filter_table) # 过滤候选表
graph_builder.add_node("add_extra_context", add_extra_context) # 添加额外上下文
graph_builder.add_node("generate_sql", generate_sql) # 生成 SQL
graph_builder.add_node("security_check_sql", security_check_sql) # SQL 安全检查
graph_builder.add_node("validate_sql", validate_sql) # 校验 SQL
graph_builder.add_node("evaluate_sql_answer", evaluate_sql_answer) # 评估 SQL 是否回答原问题
graph_builder.add_node("correct_sql", correct_sql) # 修正 SQL
graph_builder.add_node("run_sql", run_sql) # 执行 SQL
graph_builder.add_node("fail_query", fail_query) # 失败终止

# 从用户问题开始：第一轮直接识别意图；有会话历史时先补全省略式追问
graph_builder.add_conditional_edges(
    source=START,
    path=route_conversation_entry,
    path_map={
        "resolve_conversation_context": "resolve_conversation_context",
        "route_user_intent": "route_user_intent",
    },
)
graph_builder.add_edge("resolve_conversation_context", "route_user_intent")

graph_builder.add_conditional_edges(
    source="route_user_intent",
    path=lambda state: "fail_query" # 失败意图直接终止
    if state.get("error_type") == "security"
    else (
        "general_answer" # 普通意图直接普通回答
        if state.get("intent_category") == "general_chat"
        else "plan_query" # 数据查询先制定计划
    ),
    path_map={
        "plan_query": "plan_query",
        "general_answer": "general_answer",
        "fail_query": "fail_query",
    },
)

# 查询计划完成后，如果问题口径不完整则先向用户澄清，否则继续抽取关键词
graph_builder.add_conditional_edges(
    source="plan_query",
    path=lambda state: "ask_clarification" # 有澄清问题则先向用户澄清
    if (state.get("agent_plan") or {}).get("need_clarification")
    else "extract_keywords",  # 否则抽取关键词
    path_map={
        "ask_clarification": "ask_clarification",
        "extract_keywords": "extract_keywords",
    },
)

# 关键词抽取后由统一 Tool Executor 执行 Planner 生成的工具调用计划
graph_builder.add_edge("extract_keywords", "tool_executor")
graph_builder.add_edge("tool_executor", "merge_retrieved_info")

# 合并后的候选信息继续拆成表过滤和指标过滤两条线
graph_builder.add_edge("merge_retrieved_info", "filter_table")
graph_builder.add_edge("merge_retrieved_info", "filter_metric")

# 表和指标都过滤完成后，统一补充生成 SQL 所需的上下文
graph_builder.add_edge("filter_table", "add_extra_context")
graph_builder.add_edge("filter_metric", "add_extra_context")
graph_builder.add_edge("add_extra_context", "generate_sql")
graph_builder.add_edge("generate_sql", "security_check_sql")

# SQL 安全检查失败则终止，通过后再交给数据库做语法和环境校验
graph_builder.add_conditional_edges(
    source="security_check_sql",
    path=lambda state: "fail_query" if state.get("error_type") == "security" else "validate_sql",
    path_map={"validate_sql": "validate_sql", "fail_query": "fail_query"},
)

# SQL 校验通过后先评估是否回答原问题；校验失败时只允许修正一次
graph_builder.add_conditional_edges( # 添加校验 SQL 条件分支
    source="validate_sql", # 从该节点开始判断
    path=lambda state: "evaluate_sql_answer"
    if state["error"] is None
    else ("fail_query" if state.get("correction_attempts", 0) >= 1 else "correct_sql"),
    path_map={
        "evaluate_sql_answer": "evaluate_sql_answer",
        "correct_sql": "correct_sql",
        "fail_query": "fail_query",
    },
)

# 评估结果只能进入执行、修正、澄清或失败；修正后仍必须重新经过安全检查
graph_builder.add_conditional_edges(
    source="evaluate_sql_answer",
    path=route_sql_evaluation,
    path_map={
        "run_sql": "run_sql",
        "correct_sql": "correct_sql",
        "ask_clarification": "ask_clarification",
        "fail_query": "fail_query",
    },
)
graph_builder.add_edge("correct_sql", "security_check_sql")
graph_builder.add_edge("run_sql", END)
graph_builder.add_edge("fail_query", END)
graph_builder.add_edge("general_answer", END)
graph_builder.add_edge("ask_clarification", END)

# 编译后的 graph 是对外使用的 Agent 执行入口
graph = graph_builder.compile()
