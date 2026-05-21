"""
Milvus 客户端管理器

统一创建和管理 Milvus 异步客户端，负责字段和指标向量索引的连接生命周期
"""

import inspect
from typing import Optional

from pymilvus import AsyncMilvusClient

from app.conf.app_config import MilvusConfig, app_config


class MilvusClientManager:
    """管理 Milvus 客户端的初始化与关闭"""

    def __init__(self, milvus_config: MilvusConfig):
        self.milvus_config = milvus_config # Milvus 配置
        self.client: Optional[AsyncMilvusClient] = None # Milvus 客户端

    def _get_uri(self) -> str:
        """拼接 Milvus 服务地址"""
        return f"http://{self.milvus_config.host}:{self.milvus_config.port}"

    def init(self):
        """显式初始化 Milvus 客户端"""
        kwargs = {"uri": self._get_uri()}
        if self.milvus_config.token:
            kwargs["token"] = self.milvus_config.token
        # 初始化 Milvus 客户端
        self.client = AsyncMilvusClient(**kwargs)

    async def close(self):
        """关闭 Milvus 客户端连接"""
        if self.client is None:
            return
        result = self.client.close()
        if inspect.isawaitable(result):
            await result

# 全局 Milvus 客户端管理器实例
milvus_client_manager = MilvusClientManager(app_config.milvus)
