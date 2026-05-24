"""
Agent 工具注册表

集中声明 Planner 可以选择和 Tool Executor 可以执行的受控工具
"""

from typing import Any, Awaitable, Callable, TypedDict

import yaml
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.agent.context import DataQueryAgentContext
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


class RecallToolInput(BaseModel):
    """召回类工具统一输入"""

    query: str = Field(description="用户原始问题")
    keywords: list[str] = Field(default_factory=list, description="抽取后的关键词")
    hints: list[str] = Field(
        default_factory=list,
        description="Planner 为该工具提供的补充提示词",
    )

# 定义内部工具函数统一类型
ToolRunner = Callable[
    [str, list[str], list[str], DataQueryAgentContext],
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


def render_tool_specs() -> str:
    """渲染可注入 Planner Prompt 的工具清单"""

    return yaml.dump(AVAILABLE_TOOLS, allow_unicode=True, sort_keys=False)


def build_agent_tools(
    context: DataQueryAgentContext,
) -> dict[str, StructuredTool]:
    """构建 Tool Executor 可执行的 LangChain StructuredTool 注册表"""

    specs_by_name = {tool["name"]: tool for tool in AVAILABLE_TOOLS}
    return {
        tool_name: StructuredTool.from_function(
            coroutine=_build_tool_coroutine(tool_name, runner, context),
            name=tool_name,
            description=specs_by_name[tool_name]["description"],
            args_schema=RecallToolInput,
        )
        for tool_name, runner in TOOL_RUNNERS.items()
    }


def _build_tool_coroutine(
    tool_name: str,
    runner: ToolRunner,
    context: DataQueryAgentContext,
) -> Callable[..., Awaitable[dict[str, Any]]]:
    """把内部召回函数适配为 StructuredTool coroutine"""

    async def _tool(
        query: str,
        keywords: list[str] | None = None,
        hints: list[str] | None = None,
    ) -> dict[str, Any]:
        result = await runner(query, keywords or [], hints or [], context)
        return dict(result)

    _tool.__name__ = tool_name
    return _tool
