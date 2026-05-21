"""
应用主配置

定义 conf/app_config.yaml 在程序中的结构化配置对象
项目启动后会在这里一次性完成配置文件加载和类型化转换，其他模块只需要导入 app_config
就可以按属性方式读取日志 MySQL Milvus Embedding Elasticsearch 和 LLM 配置
"""

from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
from omegaconf import OmegaConf


@dataclass
class File:
    """文件日志配置"""

    enable: bool # 是否启用文件日志记录
    level: str # 日志级别
    path: str # 日志文件路径
    rotation: str # 日志文件滚动策略
    retention: str # 日志文件保留策略


@dataclass
class Console:
    """控制台日志配置"""

    enable: bool # 是否启用控制台日志记录
    level: str # 日志级别


@dataclass
class LoggingConfig:
    """日志总配置"""

    file: File # 文件日志配置
    console: Console # 控制台日志配置


@dataclass
class DBConfig:
    """MySQL 连接配置"""

    host: str # MySQL 主机地址
    port: int # MySQL 端口号
    user: str # MySQL 用户名
    password: str # MySQL 密码
    database: str # MySQL 数据库名


@dataclass
class MilvusConfig:
    """Milvus 连接与向量维度配置"""

    host: str # Milvus 主机地址
    port: int # Milvus 端口号
    embedding_size: int # 嵌入向量维度大小
    token: str # Milvus 认证令牌


@dataclass
class EmbeddingConfig:
    """Embedding 服务配置"""

    model: str # Embedding 模型名称
    dimension: int # 嵌入向量维度大小
    batch_size: int # 批量大小用于并行处理请求
    api_key: str # Embedding 服务 API 密钥
    base_url: str # Embedding 服务基础 URL


@dataclass
class ESConfig:
    """Elasticsearch 配置"""

    host: str # Elasticsearch 主机地址
    port: int # Elasticsearch 端口号
    index_name: str # Elasticsearch 索引名称


@dataclass
class LLMConfig:
    """大模型调用配置"""

    model_name: str # 大模型名称
    api_key: str # 大模型 API 密钥
    base_url: str # 大模型服务基础 URL


@dataclass
class SQLSecurityConfig:
    """SQL 安全治理配置"""

    enabled: bool # 是否启用 SQL 安全检查
    max_rows: int # 最大返回行数
    timeout_seconds: int # SQL 执行超时时间
    allowed_functions: list[str] # 允许使用的 SQL 函数
    forbid_cross_database: bool # 是否禁止跨库查询


@dataclass
class AppConfig:
    """项目级总配置入口"""

    logging: LoggingConfig # 日志配置
    db_meta: DBConfig # 元数据数据库配置
    db_dw: DBConfig # 数据写入数据库配置
    milvus: MilvusConfig # Milvus 配置配置
    embedding: EmbeddingConfig # Embedding 服务配置
    es: ESConfig # Elasticsearch 配置
    llm: LLMConfig # 大模型调用配置
    sql_security: SQLSecurityConfig # SQL 安全治理配置


# 从当前文件位置回到项目根目录，再定位到 conf/app_config.yaml
project_root = Path(__file__).parents[2]
config_file = project_root / "conf" / "app_config.yaml"

# 先读取本地 .env，让 YAML 中的 ${oc.env:...} 可以解析到敏感配置
load_dotenv(project_root / ".env")

# 读取 YAML 配置内容
context = OmegaConf.load(config_file)

# 根据 AppConfig 生成结构化配置 schema
schema = OmegaConf.structured(AppConfig)

# 把配置结构和配置值合并，再转换成可以直接按属性访问的对象
app_config: AppConfig = OmegaConf.to_object(OmegaConf.merge(schema, context))
