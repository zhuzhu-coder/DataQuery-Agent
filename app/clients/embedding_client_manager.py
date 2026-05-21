"""
Embedding 客户端管理器

负责按配置初始化云端 Embedding 客户端，并为字段、指标和用户问题的向量化
提供统一访问入口
"""

from typing import Optional

from openai import AsyncOpenAI

from app.conf.app_config import EmbeddingConfig, app_config


class EmbeddingClient:
    """提供和原 LangChain Embedding 类兼容的异步调用方法"""

    def __init__(self, config: EmbeddingConfig):
        self.config = config
        self.client = AsyncOpenAI(api_key=config.api_key, base_url=config.base_url)

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        """批量生成文档向量，内部按配置拆分请求大小"""
        embeddings: list[list[float]] = []
        for i in range(0, len(texts), self.config.batch_size):
            # 当前批次的文本列表
            batch = texts[i : i + self.config.batch_size]
            # 调用 OpenAI 服务生成向量
            response = await self.client.embeddings.create(
                model=self.config.model,
                input=batch,
                dimensions=self.config.dimension,
            )
            # 添加当前批次的向量
            embeddings.extend([item.embedding for item in response.data])
        return embeddings

    async def aembed_query(self, text: str) -> list[float]:
        """生成单条查询文本向量"""
        embeddings = await self.aembed_documents([text])
        return embeddings[0]

    async def close(self):
        """关闭 OpenAI 兼容客户端的底层 HTTP 连接"""
        await self.client.close()


class EmbeddingClientManager:
    """管理 Embedding 服务客户端的初始化与复用"""

    def __init__(self, config: EmbeddingConfig):
        self.client: Optional[EmbeddingClient] = None
        self.config = config

    def init(self):
        """显式初始化客户端，避免模块导入时立即建立外部连接"""
        self.client = EmbeddingClient(self.config)

    async def close(self):
        """关闭 Embedding 客户端连接"""
        if self.client is not None:
            await self.client.close()


# 模块级单例，供整个项目复用同一套 Embedding 客户端管理器
embedding_client_manager = EmbeddingClientManager(app_config.embedding)
