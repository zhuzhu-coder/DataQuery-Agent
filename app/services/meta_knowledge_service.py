"""
元数据知识构建服务

负责组织元数据知识库构建的核心业务流程，位于脚本入口和仓储层之间
一方面接收配置文件，另一方面协调元数据库和数仓查询仓储

当前这条主线已经覆盖表字段入库 字段向量索引 字段取值全文索引
以及指标入库和指标向量索引构建逻辑
"""

import uuid
from dataclasses import asdict
from pathlib import Path

from omegaconf import OmegaConf

from app.clients.embedding_client_manager import EmbeddingClient
from app.conf.meta_config import MetaConfig
from app.core.log import logger
from app.entities.column_info import ColumnInfo
from app.entities.column_metric import ColumnMetric
from app.entities.metric_info import MetricInfo
from app.entities.table_info import TableInfo
from app.entities.value_info import ValueInfo
from app.repositories.es.value_es_repository import ValueESRepository
from app.repositories.mysql.dw.dw_mysql_repository import DWMySQLRepository
from app.repositories.mysql.meta.meta_mysql_repository import MetaMySQLRepository
from app.repositories.vector.column_vector_repository import ColumnVectorRepository
from app.repositories.vector.metric_vector_repository import MetricVectorRepository


class MetaKnowledgeService:
    """负责串联元数据知识库构建流程的应用服务"""

    def __init__(
        self,
        meta_mysql_repository: MetaMySQLRepository,
        dw_mysql_repository: DWMySQLRepository,
        column_vector_repository: ColumnVectorRepository,
        embedding_client: EmbeddingClient,
        value_es_repository: ValueESRepository,
        metric_vector_repository: MetricVectorRepository,
    ):
        # 元数据库仓储
        self.meta_mysql_repository: MetaMySQLRepository = meta_mysql_repository
        # 数仓仓储
        self.dw_mysql_repository: DWMySQLRepository = dw_mysql_repository
        # 字段向量仓储
        self.column_vector_repository: ColumnVectorRepository = column_vector_repository
        # 嵌入模型客户端
        self.embedding_client: EmbeddingClient = embedding_client
        # 字段取值全文索引仓储
        self.value_es_repository: ValueESRepository = value_es_repository
        # 指标向量仓储
        self.metric_vector_repository: MetricVectorRepository = metric_vector_repository

    async def _save_tables_to_meta_db(
        self, meta_config: MetaConfig
    ) -> list[ColumnInfo]:
        """把配置里的表字段信息补齐后写入 Meta MySQL"""
        table_infos: list[TableInfo] = []
        column_infos: list[ColumnInfo] = []

        for table in meta_config.tables:
            # 先把配置里的表定义整理成业务实体，后面统一交给 Meta Repository 落库
            table_info = TableInfo(
                id=table.name,
                name=table.name,
                role=table.role,
                description=table.description,
            )
            table_infos.append(table_info)

            # 字段类型属于数仓里的真实信息，所以这里仍然要回到 DW 查询
            column_types = await self.dw_mysql_repository.get_column_types(table.name)

            for column in table.columns:
                # 这里只拿少量示例值，目的是让字段元数据更容易被人和模型理解
                column_values = await self.dw_mysql_repository.get_column_values(
                    table.name, column.name
                )
                # 字段 id 使用 table.column 形式，后续在向量索引和全文索引里都会复用
                column_info = ColumnInfo(
                    id=f"{table.name}.{column.name}",
                    name=column.name,
                    type=column_types[column.name],
                    role=column.role,
                    examples=column_values,
                    description=column.description,
                    alias=column.alias,
                    table_id=table.name,
                )
                column_infos.append(column_info)

        # 将所有表和字段信息批量写入 Meta MySQL 数据库
        async with self.meta_mysql_repository.session.begin():
            self.meta_mysql_repository.save_table_infos(table_infos)
            self.meta_mysql_repository.save_column_infos(column_infos)

        return column_infos

    async def _save_column_info_to_vector_store(self, column_infos: list[ColumnInfo]):
        """把字段元数据继续推进成可语义检索的向量点"""
        await self.column_vector_repository.ensure_collection()
        # 初始化向量点列表
        points: list[dict] = []
        for column_info in column_infos:
            # 一个字段不会只生成一个向量点，而是把名字 描述 别名都拆开建立语义入口
            # 把字段名作为一条可检索文本
            points.append(
                {
                    "id": uuid.uuid4(),
                    "embedding_text": column_info.name,
                    "payload": asdict(column_info),
                }
            )
            # 把字段描述作为一条可检索文本
            points.append(
                {
                    "id": uuid.uuid4(),
                    "embedding_text": column_info.description,
                    "payload": asdict(column_info),
                }
            )
            # 把字段别名作为一条可检索文本
            for alia in column_info.alias:
                points.append(
                    {
                        "id": uuid.uuid4(),
                        "embedding_text": alia,
                        "payload": asdict(column_info),
                    }
                )

        # 先把待向量化文本抽出来，再分批调用 Embedding 服务
        # 这样更容易控制单次请求大小
        embeddings: list[list[float]] = []
        # 所有要向量化的文本
        embedding_texts = [point["embedding_text"] for point in points]
        # 每批处理 1 条文本
        embedding_batch_size = 1
        for i in range(0, len(embedding_texts), embedding_batch_size):
            batch_embedding_texts = embedding_texts[i : i + embedding_batch_size]
            batch_embeddings = await self.embedding_client.aembed_documents(
                batch_embedding_texts
            )
            embeddings.extend(batch_embeddings)

        ids = [point["id"] for point in points]
        payloads = [point["payload"] for point in points]

        # 批量写入字段向量点
        await self.column_vector_repository.upsert(ids, embeddings, payloads)

    async def _save_value_info_to_es(
        self, meta_config: MetaConfig, column_infos: list[ColumnInfo]
    ):
        """把允许同步的字段真实取值写入 Elasticsearch 全文索引"""
        await self.value_es_repository.ensure_index()

        # 初始化字段同步映射
        column2sync: dict[str, bool] = {}
        for table in meta_config.tables:
            for column in table.columns:
                column2sync[f"{table.name}.{column.name}"] = column.sync
        # 初始化值信息列表
        value_infos: list[ValueInfo] = []
        for column_info in column_infos:
            # 检查字段是否需要同步真实值
            sync = column2sync[column_info.id]
            if sync:
                # 这里拿的是字段真实取值，最多拿 100000 条
                current_column_values = (
                    await self.dw_mysql_repository.get_column_values(
                        column_info.table_id, column_info.name, 100000
                    )
                )
                current_values_infos = [
                    ValueInfo(
                        id=f"{column_info.id}.{current_column_value}",
                        value=current_column_value,
                        column_id=column_info.id,
                    )
                    for current_column_value in current_column_values
                ]
                value_infos.extend(current_values_infos)

        await self.value_es_repository.index(value_infos)

    async def _save_metrics_to_meta_db(
        self, meta_config: MetaConfig
    ) -> list[MetricInfo]:
        """把配置里的指标信息和字段依赖关系写入 Meta MySQL"""
        # 指标信息列表
        metric_infos: list[MetricInfo] = []
        # 字段指标依赖关系列表
        column_metrics: list[ColumnMetric] = []

        for metric in meta_config.metrics:
            # MetricInfo 表达指标本身，当前直接用指标名作为稳定业务 id
            metric_info = MetricInfo(
                id=metric.name,
                name=metric.name,
                description=metric.description,
                relevant_columns=metric.relevant_columns,
                alias=metric.alias,
            )
            metric_infos.append(metric_info)
            for column in metric.relevant_columns:
                # ColumnMetric 单独表达“某个指标依赖某个字段”这层关系
                column_metric = ColumnMetric(column_id=column, metric_id=metric.name)
                column_metrics.append(column_metric)

        # 指标本身和字段关系要放在同一笔事务里，避免只写入其中一部分
        async with self.meta_mysql_repository.session.begin():
            self.meta_mysql_repository.save_metric_infos(metric_infos)
            self.meta_mysql_repository.save_column_metrics(column_metrics)

        return metric_infos

    async def _save_metrics_to_vector_store(self, metric_infos: list[MetricInfo]):
        """把指标元数据继续推进成可语义检索的向量点"""
        await self.metric_vector_repository.ensure_collection()

        points: list[dict] = []
        for metric_info in metric_infos:
            # 和字段一样，一个指标也会拆成名字 描述 别名这几类语义入口
            # 把指标名作为一条可检索文本
            points.append(
                {
                    "id": uuid.uuid4(),
                    "embedding_text": metric_info.name,
                    "payload": asdict(metric_info),
                }
            )
            # 把指标描述作为一条可检索文本
            points.append(
                {
                    "id": uuid.uuid4(),
                    "embedding_text": metric_info.description,
                    "payload": asdict(metric_info),
                }
            )
            # 把指标别名作为一条可检索文本
            for alia in metric_info.alias:
                points.append(
                    {
                        "id": uuid.uuid4(),
                        "embedding_text": alia,
                        "payload": asdict(metric_info),
                    }
                )

        # 先把待向量化文本抽出来，再分批调用 Embedding 服务
        # 返回的 embeddings 要继续和前面的 id payload 按顺序对齐
        embeddings: list[list[float]] = []
        # 所有要向量化的文本
        embedding_texts = [point["embedding_text"] for point in points]
        # 每批处理 1 条文本
        embedding_batch_size = 1
        for i in range(0, len(embedding_texts), embedding_batch_size):
            batch_embedding_texts = embedding_texts[i : i + embedding_batch_size]
            batch_embeddings = await self.embedding_client.aembed_documents(
                batch_embedding_texts
            )
            embeddings.extend(batch_embeddings)

        ids = [point["id"] for point in points]
        payloads = [point["payload"] for point in points]

        await self.metric_vector_repository.upsert(ids, embeddings, payloads)

    async def build(self, config_path: Path):
        """读取配置并依次构建 Meta MySQL 向量库和 ES 中的元数据索引"""

        # 将 YAML 配置文件解析并映射为 MetaConfig 类型的 Python 对象
        context = OmegaConf.load(config_path)
        schema = OmegaConf.structured(MetaConfig)
        meta_config: MetaConfig = OmegaConf.to_object(OmegaConf.merge(schema, context))

        # 根据配置文件判断后续要进入哪条构建链路
        if meta_config.tables:
            # 将表信息和字段信息保存到 Meta MySQL
            column_infos = await self._save_tables_to_meta_db(meta_config)
            logger.info("保存表信息和字段信息到 Meta MySQL")
            # 对字段信息建立向量索引
            await self._save_column_info_to_vector_store(column_infos)
            logger.info("为字段信息建立向量索引")
            # 对指定的维度字段取值建立全文索引
            await self._save_value_info_to_es(meta_config, column_infos)
            logger.info("为字段取值建立全文索引")

        # 根据配置文件同步指定的指标信息
        if meta_config.metrics:
            # 将指标信息和字段依赖关系保存到 Meta MySQL
            metric_infos = await self._save_metrics_to_meta_db(meta_config)
            logger.info("保存指标信息到 Meta MySQL 成功")

            # 对指标信息建立向量索引
            await self._save_metrics_to_vector_store(metric_infos)
            logger.info("为指标信息建立向量索引成功")
