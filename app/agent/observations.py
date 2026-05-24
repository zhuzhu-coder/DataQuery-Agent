"""
Agent 观察记录工具

节点把关键工具调用和评估结果写入 agent_observations，作为当前任务的短期执行记忆。
"""

from typing import Any

from app.agent.state import AgentObservationState


def observation_update(
    tool: str, summary: str, metadata: dict[str, Any] | None = None
) -> dict[str, list[AgentObservationState]]:
    """生成可被 LangGraph 合并进 State 的观察记录更新"""

    return {
        "agent_observations": [
            AgentObservationState(
                tool=tool,
                summary=summary,
                metadata=metadata or {},
            )
        ]
    }
