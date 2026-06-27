"""
问数查询服务

负责把 API 层传入的自然语言问题转换成一次 LangGraph 工作流执行：
创建初始 State、组装 Runtime Context、消费 graph.astream 的流式输出，
并统一包装成 SSE 文本返回给路由层
"""

import json
from typing import Any

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.agent.context import DataQueryAgentContext
from app.agent.graph import graph
from app.agent.llm import llm
from app.agent.state import DataQueryAgentState
from app.clients.embedding_client_manager import EmbeddingClient
from app.core.context import request_id_ctx_var
from app.prompt.prompt_loader import load_prompt
from app.repositories.es.value_es_repository import ValueESRepository
from app.repositories.mysql.dw.dw_mysql_repository import DWMySQLRepository
from app.repositories.mysql.meta.meta_mysql_repository import MetaMySQLRepository
from app.repositories.mysql.meta.query_audit_repository import QueryAuditRepository
from app.repositories.vector.column_vector_repository import ColumnVectorRepository
from app.repositories.vector.metric_vector_repository import MetricVectorRepository
from app.services.conversation_memory import ConversationMemoryStore


class QueryService:
    """封装一次问数查询所需的业务编排逻辑"""

    def __init__(
        self,
        meta_mysql_repository: MetaMySQLRepository, # 元数据仓储
        embedding_client: EmbeddingClient, # 嵌入模型客户端
        dw_mysql_repository: DWMySQLRepository, # 数仓仓储
        column_vector_repository: ColumnVectorRepository, # 字段向量仓储
        metric_vector_repository: MetricVectorRepository, # 指标向量仓储
        value_es_repository: ValueESRepository, # 字段取值全文检索仓储
        query_audit_repository: QueryAuditRepository, # 查询审计仓储
        conversation_memory_store: ConversationMemoryStore | None = None, # 会话级短期记忆
    ):
        self.meta_mysql_repository = meta_mysql_repository
        self.dw_mysql_repository = dw_mysql_repository
        self.embedding_client = embedding_client
        self.column_vector_repository = column_vector_repository
        self.metric_vector_repository = metric_vector_repository
        self.value_es_repository = value_es_repository
        self.query_audit_repository = query_audit_repository
        self.conversation_memory_store = conversation_memory_store

    async def query(self, query: str, conversation_id: str | None = None):
        """执行一次问数工作流，并逐段产出 SSE 消息"""
        # 创建查询审计记录
        audit_id = await self.query_audit_repository.create_started(
            request_id=request_id_ctx_var.get(),
            query=query,
        )
        # 读取会话历史消息
        conversation_history = await self._conversation_history(conversation_id)
        # State 只放会被图节点读写和合并的业务数据，外部工具对象不塞进 State
        state = DataQueryAgentState(
            query=query,
            conversation_history=conversation_history,
            resolved_query="",
            intent_category="",
            agent_plan={},
            keywords=[],
            retrieved_column_infos=[],
            retrieved_metric_infos=[],
            retrieved_value_infos=[],
            table_infos=[],
            metric_infos=[],
            date_info={},
            db_info={},
            sql="",
            error=None,
            error_type=None,
            correction_attempts=0,
            evaluation_result={},
            evaluation_attempts=0,
            audit_id=audit_id,
        )
        # Context 保存本次图执行需要复用的外部依赖，节点通过 runtime.context 读取
        context = DataQueryAgentContext(
            column_vector_repository=self.column_vector_repository,
            embedding_client=self.embedding_client,
            metric_vector_repository=self.metric_vector_repository,
            value_es_repository=self.value_es_repository,
            meta_mysql_repository=self.meta_mysql_repository,
            dw_mysql_repository=self.dw_mysql_repository,
            query_audit_repository=self.query_audit_repository,
        )
        resolved_query = query
        assistant_memory_content = ""
        try:
            # stream_mode="custom" 对应节点内部 writer(...) 写出的进度消息
            async for chunk in graph.astream(
                input=state, context=context, stream_mode="custom"
            ):
                if isinstance(chunk, dict):
                    event_type = chunk.get("type")
                    # 入口解析阶段，更新 resolved_query
                    if event_type == "trace" and chunk.get("step") == "入口解析":
                        resolved_query = (
                            _resolved_query_from_event(chunk) or resolved_query
                        )
                    # SQL 生成阶段，更新 assistant_memory_content
                    elif event_type in {"result", "answer"}:
                        assistant_memory_content = _memory_content_from_event(chunk)
                # SSE 要求每条消息以 data: 开头，并以两个换行符结束
                # ensure_ascii=False 中文字符不转义，default=str 兜底处理日期等非 JSON 类型
                yield f"data: {json.dumps(chunk, ensure_ascii=False, default=str)}\n\n"
            if assistant_memory_content:
                await self._append_memory(
                    conversation_id=conversation_id,
                    query=query,
                    resolved_query=resolved_query,
                    assistant_content=assistant_memory_content,
                )
        except Exception as e:
            await self.query_audit_repository.finish(
                audit_id,
                status="failed",
                error_message=str(e),
            )
            # 流式接口已经开始返回后不能再改 HTTP 状态码，因此把异常也包装成一条 SSE 消息
            error = {"type": "error", "message": str(e)}
            yield f"data: {json.dumps(error, ensure_ascii=False, default=str)}\n\n"

    async def _conversation_history(
        self, conversation_id: str | None
    ) -> list[dict[str, Any]]:
        """读取会话历史并转换为 State 可序列化结构"""

        if not conversation_id or not self.conversation_memory_store:
            return []
        history = []
        for turn in await self.conversation_memory_store.get_history(conversation_id):
            history.append(
                {
                    "role": turn.role,
                    "content": turn.content,
                }
            )
        return history

    async def _append_memory(
        self,
        conversation_id: str | None,
        query: str,
        resolved_query: str,
        assistant_content: str,
    ) -> None:
        """将本轮成功响应写入会话短期记忆"""

        if not conversation_id or not self.conversation_memory_store:
            return
        await self.conversation_memory_store.append_message(
            conversation_id,
            role="user",
            content=query,
        )
        if resolved_query != query:
            assistant_content = f"补全后问题：{resolved_query}\n{assistant_content}"
        await self.conversation_memory_store.append_message(
            conversation_id,
            role="assistant",
            content=assistant_content,
        )
        await self.conversation_memory_store.compact_if_needed(
            conversation_id,
            _compress_conversation_context,
        )


def _resolved_query_from_event(event: Any) -> str | None:
    """从事件中提取补全后的查询语句"""
    if not isinstance(event, dict):
        return None
    if event.get("type") != "trace" or event.get("step") != "入口解析":
        return None
    metadata = event.get("metadata") or {}
    resolved_query = metadata.get("resolved_query")
    return str(resolved_query) if resolved_query else None


def _memory_content_from_event(event: Any) -> str:
    """从事件中提取可写入会话历史的助手消息"""
    if not isinstance(event, dict):
        return ""
    event_type = event.get("type")
    if event_type == "result":
        return f"查询完成，{_summarize_result(event.get('data'))}"
    if event_type == "answer":
        content = str(event.get("content") or "")
        return content[:200]
    return ""


def _summarize_result(data: Any) -> str:
    """根据查询结果的结构生成简要描述，供助手消息使用"""
    if isinstance(data, list):
        # 统计有效行数
        row_count = len([row for row in data if isinstance(row, dict)])
        # 提取所有字段名，去重并限制 8 个
        columns: list[str] = []
        for row in data:
            if not isinstance(row, dict):
                continue
            for column in row.keys():
                if str(column) not in columns:
                    columns.append(str(column))
        if columns:
            return f"返回 {row_count} 行，字段：{', '.join(columns[:8])}"
        return f"返回 {row_count} 行"
    if isinstance(data, dict):
        return f"返回 1 行，字段：{', '.join(str(key) for key in list(data.keys())[:8])}"
    return "查询完成"


async def _compress_conversation_context(old_context, messages) -> str:
    """将旧压缩上下文和较早消息滚动压缩成新的上下文"""

    prompt = ChatPromptTemplate.from_template(load_prompt("compress_conversation_context"))
    history = "\n".join(
        f"{message.role}: {message.content}" for message in messages
    )
    chain = prompt | llm | StrOutputParser()
    result = await chain.ainvoke(
        {
            "old_context": old_context or "无",
            "history": history,
        }
    )
    return str(result).strip()
