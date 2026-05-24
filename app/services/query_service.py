"""
问数查询服务

负责把 API 层传入的自然语言问题转换成一次 LangGraph 工作流执行：
创建初始 State、组装 Runtime Context、消费 graph.astream 的流式输出，
并统一包装成 SSE 文本返回给路由层
"""

import json

from app.agent.context import DataQueryAgentContext
from app.agent.graph import graph
from app.agent.state import DataQueryAgentState
from app.clients.embedding_client_manager import EmbeddingClient
from app.core.context import request_id_ctx_var
from app.repositories.es.value_es_repository import ValueESRepository
from app.repositories.mysql.dw.dw_mysql_repository import DWMySQLRepository
from app.repositories.mysql.meta.meta_mysql_repository import MetaMySQLRepository
from app.repositories.mysql.meta.query_audit_repository import QueryAuditRepository
from app.repositories.vector.column_vector_repository import ColumnVectorRepository
from app.repositories.vector.metric_vector_repository import MetricVectorRepository


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
    ):
        # MySQL 仓储分别负责元数据补全和真实数仓环境信息读取
        self.meta_mysql_repository = meta_mysql_repository
        self.dw_mysql_repository = dw_mysql_repository

        # 召回链路依赖的向量检索、Embedding 和全文检索能力由依赖层注入
        self.embedding_client = embedding_client
        self.column_vector_repository = column_vector_repository
        self.metric_vector_repository = metric_vector_repository
        self.value_es_repository = value_es_repository
        self.query_audit_repository = query_audit_repository

    async def query(self, query: str):
        """执行一次问数工作流，并逐段产出 SSE 消息"""
        # 创建查询审计记录
        audit_id = await self.query_audit_repository.create_started(
            request_id=request_id_ctx_var.get(),
            query=query,
        )
        # State 只放会被图节点读写和合并的业务数据，外部工具对象不塞进 State
        state = DataQueryAgentState(
            query=query,
            audit_id=audit_id,
            correction_attempts=0,
            agent_plan={},
            agent_observations=[],
            evaluation_result={},
            evaluation_attempts=0,
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
        try:
            # stream_mode="custom" 对应节点内部 writer(...) 写出的进度消息
            async for chunk in graph.astream(
                input=state, context=context, stream_mode="custom"
            ):
                # SSE 要求每条消息以 data: 开头，并以两个换行符结束
                # ensure_ascii=False 中文字符不转义，default=str 兜底处理日期等非 JSON 类型
                yield f"data: {json.dumps(chunk, ensure_ascii=False, default=str)}\n\n"
        except Exception as e:
            await self.query_audit_repository.finish(
                audit_id,
                status="failed",
                error_message=str(e),
            )
            # 流式接口已经开始返回后不能再改 HTTP 状态码，因此把异常也包装成一条 SSE 消息
            error = {"type": "error", "message": str(e)}
            yield f"data: {json.dumps(error, ensure_ascii=False, default=str)}\n\n"
