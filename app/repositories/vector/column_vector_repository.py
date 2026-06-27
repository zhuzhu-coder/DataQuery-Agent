"""
字段向量仓储

管理字段向量集合并把已经准备好的 point 批量写入 Milvus
"""

from typing import Any

from pymilvus import AsyncMilvusClient, DataType, MilvusClient

from app.conf.app_config import app_config
from app.entities.column_info import ColumnInfo


class ColumnVectorRepository:
    """负责字段向量集合的创建 写入和基础检索"""

    collection_name = "column_info_collection"

    def __init__(self, client: AsyncMilvusClient):
        self.client = client

    async def ensure_collection(self):
        """确保字段向量集合存在，并按配置中的维度初始化"""
        # 检查集合是否存在
        if await self.client.has_collection(self.collection_name):
            return

        schema = MilvusClient.create_schema(
            auto_id=False, enable_dynamic_field=False  # 主键不自动生成，不允许插入 schema 之外的额外字段
        )
        schema.add_field("id", DataType.VARCHAR, is_primary=True, max_length=128)
        schema.add_field(
            "vector",
            DataType.FLOAT_VECTOR,
            dim=app_config.milvus.embedding_size,  # 向量维度
        )
        schema.add_field("payload", DataType.JSON)  # 用来保存该向量对应的原始字段元数据
        # 创建索引
        index_params = MilvusClient.prepare_index_params()  # 索引参数
        index_params.add_index(
            field_name="vector",  # 索引字段
            index_type="AUTOINDEX",  # 自动选择索引方式
            metric_type="COSINE",  # 余弦相似度
        )

        await self.client.create_collection(
            collection_name=self.collection_name,
            schema=schema,
            index_params=index_params,
        )

    async def upsert(
        self,
        ids: list[str],
        embeddings: list[list[float]],
        payloads: list[dict],
        batch_size: int = 100,
    ):
        """
        分批 upsert 字段向量点，避免一次提交过多 point
        Args:
            ids: 字段 ID 列表
            embeddings: 字段向量列表
            payloads: 字段元数据列表
            batch_size: 每批 upsert 的 point 数量，默认 100 个
        """
        rows: list[dict[str, Any]] = [
            {"id": str(id_), "vector": embedding, "payload": payload}
            for id_, embedding, payload in zip(ids, embeddings, payloads)
        ]
        for i in range(0, len(rows), batch_size):
            await self.client.upsert(
                collection_name=self.collection_name,
                data=rows[i : i + batch_size],
            )
        await self.client.flush(collection_name=self.collection_name) # 刷新集合，确保所有 point 都写入

    async def search(
        self, embedding: list[float], score_threshold: float = 0.6, limit: int = 20
    ) -> list[ColumnInfo]:
        """
        按向量相似度检索字段元数据，并还原为 ColumnInfo 实体
        Args:
            embedding: 查询向量
            score_threshold: 相似度阈值，仅返回大于等于该值的字段
            limit: 最大返回字段数量
        """
        results = await self.client.search(
            collection_name=self.collection_name,
            data=[embedding],
            limit=limit,
            output_fields=["payload"], # 还要返回 payload 字段（包含字段元数据）
            search_params={"metric_type": "COSINE"}, # 使用余弦相似度
        )
        return [
            ColumnInfo(**hit["entity"]["payload"])
            for hit in results[0]
            if hit["distance"] >= score_threshold # 仅返回相似度大于等于阈值的字段
        ]
