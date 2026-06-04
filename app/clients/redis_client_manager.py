"""
Redis 客户端管理器

统一创建和管理会话短期记忆使用的异步 Redis 客户端
"""

from typing import Any

from app.conf.app_config import RedisConfig, app_config


class RedisClientManager:
    """管理 Redis 客户端生命周期"""

    def __init__(self, redis_config: RedisConfig):
        self.redis_config = redis_config
        self.client: Any = None

    def init(self):
        """初始化异步 Redis 客户端"""

        try:
            from redis.asyncio import Redis
        except ImportError as e:
            raise RuntimeError("缺少 redis 依赖，请先执行 uv sync 安装依赖。") from e

        self.client = Redis(
            host=self.redis_config.host,
            port=self.redis_config.port,
            db=self.redis_config.db,
            password=self.redis_config.password or None,
            decode_responses=True, # 自动解码为字符串
        )

    async def close(self):
        """关闭 Redis 客户端连接"""

        if self.client is not None:
            await self.client.aclose()


redis_client_manager = RedisClientManager(app_config.redis)
