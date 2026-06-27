"""
Agent 工具注册表

集中声明 Planner 可以选择和 Tool Executor 可以执行的受控工具
"""

from typing import Awaitable, Callable, TypedDict

import yaml

from app.agent.context import DataQueryAgentContext
from app.agent.state import ToolCallState
from app.agent.toolkits.recall import (
    RecallToolResult,
    run_recall_column,
    run_recall_metric,
    run_recall_value,
)


class AgentToolSpec(TypedDict):
    """Planner 可选择工具的最小描述"""

    name: str
    description: str


# 定义内部工具函数统一类型
ToolRunner = Callable[
    [list[str], list[str], DataQueryAgentContext],
    Awaitable[RecallToolResult],
]

# 可用工具清单
AVAILABLE_TOOLS: list[AgentToolSpec] = [
    {
        "name": "recall_column",
        "description": "定位问题涉及的表、字段、维度字段、事实字段、时间字段和 Join 相关字段。",
    },
    {
        "name": "recall_metric",
        "description": "定位系统中已定义的业务指标、指标别名、指标口径和指标依赖字段。",
    },
    {
        "name": "recall_value",
        "description": "定位可能真实存在于字段中的枚举值或业务取值，例如地区、品类、商品名、品牌、会员等级、性别等。",
    },
]

# 工具函数注册表
TOOL_RUNNERS: dict[str, ToolRunner] = {
    "recall_column": run_recall_column,
    "recall_metric": run_recall_metric,
    "recall_value": run_recall_value,
}


def available_tool_names() -> list[str]:
    """返回当前 Planner 可选择的工具名称"""

    return [tool["name"] for tool in AVAILABLE_TOOLS]


def normalize_tool_calls(value: object) -> list[ToolCallState]:
    """规范化工具调用计划，非法或为空时回退到全部工具"""

    if not isinstance(value, list):
        return default_tool_calls()
    # 筛选出允许的工具名称
    allowed_tool_names = set(available_tool_names())
    # 初始化空列表，用于存储有效工具调用
    tool_calls: list[ToolCallState] = []
    # 记录已处理的工具名称，避免重复调用
    seen_tool_names: set[str] = set()
    for item in value:
        if not isinstance(item, dict):
            continue
        tool_name = str(item.get("name") or "")
        if tool_name not in allowed_tool_names or tool_name in seen_tool_names:
            continue
        seen_tool_names.add(tool_name)
        args = item.get("args") if isinstance(item.get("args"), dict) else {}
        tool_calls.append(
            ToolCallState(
                name=tool_name,
                args={"hints": _string_list(args.get("hints"))},
            )
        )

    return tool_calls or default_tool_calls()


def default_tool_calls() -> list[ToolCallState]:
    """Planner 输出不可用时，保守调用全部注册工具"""

    return [
        ToolCallState(
            name=tool_name,
            args={"hints": []},
        )
        for tool_name in available_tool_names()
    ]


def render_tool_specs() -> str:
    """渲染可注入 Planner Prompt 的工具清单，用于描述可用工具"""
    # 转换为 YAML 格式，允许中文字符，不排序键
    return yaml.dump(AVAILABLE_TOOLS, allow_unicode=True, sort_keys=False)


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item is not None]
