# 智能问数助手 / Data Query Agent

Data Query Agent 是一个面向业务数仓的自然语言问数项目。用户用中文提出分析问题，系统会召回相关表字段、指标和值域信息，组织上下文生成 SQL，完成校验、修正、执行，并通过 SSE 把执行进度和查询结果返回给前端。

## 项目能力

- 自然语言查询：将业务问题转换为结构化 SQL 查询。
- 混合检索：使用 Milvus 召回字段和指标语义信息，使用 Elasticsearch 召回字段真实取值。
- 元数据知识库：用 MySQL 保存表、字段、指标和字段指标关系。
- 工作流编排：用 LangGraph 串联关键词抽取、召回、过滤、SQL 生成、校验、修正和执行。
- 流式响应：后端通过 SSE 返回节点进度、最终结果和错误信息。
- 前端交互：React + Vite + Tailwind CSS 提供聊天式问数界面。

## 系统架构

| 模块      | 技术                         | 作用                             |
| --------- | ---------------------------- | -------------------------------- |
| 示例数仓  | MySQL                        | 保存业务查询用的事实表和维度表   |
| 元数据库  | MySQL / SQLAlchemy           | 保存表、字段、指标等结构化元数据 |
| 向量检索  | Milvus                       | 支持字段和指标语义召回           |
| 全文检索  | Elasticsearch                | 支持字段值关键词检索             |
| Embedding | DashScope text-embedding-v4  | 生成向量表示                     |
| 智能编排  | LangGraph                    | 组织多阶段问数流程               |
| 后端接口  | FastAPI                      | 提供查询接口和生命周期管理       |
| 前端      | React / Vite / Tailwind CSS  | 展示对话、流程和结果表格         |

## 项目结构

```text
data-query-agent/
├── app/
│   ├── agent/            # LangGraph 图、状态、上下文和节点
│   ├── api/              # FastAPI 路由、依赖注入和生命周期
│   ├── clients/          # MySQL、Milvus、Elasticsearch、Embedding 客户端管理
│   ├── conf/             # 配置 dataclass 与配置加载
│   ├── core/             # 日志和 request_id 上下文
│   ├── entities/         # 业务语义数据对象
│   ├── models/           # SQLAlchemy ORM 模型
│   ├── prompt/           # Prompt 加载工具
│   ├── repositories/     # 数据访问层
│   ├── scripts/          # 元数据知识库构建脚本
│   └── services/         # 查询服务和元数据构建服务
├── conf/                 # app_config.yaml、meta_config.yaml
├── docker/               # Docker Compose、MySQL 初始化 SQL、ES 插件
├── docs/images/          # README 使用的项目截图和架构图
├── frontend/             # React 前端项目
├── prompts/              # SQL 生成、修正、过滤等 Prompt 模板
├── main.py               # FastAPI 应用入口
└── pyproject.toml        # Python 项目依赖与工具配置
```

## 快速开始

### 1. 准备环境

- Python `>= 3.12`
- `uv`
- Docker 与 Docker Compose
- Node.js 与 `pnpm`

### 2. 安装后端依赖

```bash
uv sync
```

### 3. 配置大模型密钥

```bash
cp .env.example .env
```

编辑 `.env`：

```bash
LLM_API_KEY=your_real_api_key
```

默认大模型和 Embedding 配置在 [conf/app_config.yaml](conf/app_config.yaml)：

```yaml
embedding:
  model: text-embedding-v4
  dimension: 1024
  batch_size: 10
  api_key: ${oc.env:LLM_API_KEY}
  base_url: https://dashscope.aliyuncs.com/compatible-mode/v1

llm:
  model_name: qwen3.6-plus
  api_key: ${oc.env:LLM_API_KEY}
  base_url: https://dashscope.aliyuncs.com/api/v1
```

如需更换兼容 OpenAI 接口的模型服务，调整 `model_name` 和 `base_url`。

### 4. 启动基础服务

```bash
docker compose -f docker/docker-compose.yaml up -d
```

默认端口：

| 服务          | 端口     |
| ------------- | -------- |
| MySQL         | `3307` |
| Elasticsearch | `9201` |
| Kibana        | `5602` |
| Milvus        | `19530` |

MySQL 默认开发账号来自 Docker 配置：

```text
user: data_query_agent
password: data_query_123
```

### 5. 构建元数据知识库

```bash
uv run python -m app.scripts.build_meta_knowledge -c conf/meta_config.yaml
```

这一步会把表字段元数据写入 MySQL，把字段和指标向量写入 Milvus，并把字段真实取值写入 Elasticsearch。

### 6. 启动后端

```bash
uv run fastapi dev main.py
```

后端接口：

```text
POST http://127.0.0.1:8000/api/query
```

请求示例：

```json
{
  "query": "统计华北地区的销售总额"
}
```

SSE 消息类型：

| 类型         | 含义         |
| ------------ | ------------ |
| `progress` | 节点执行进度 |
| `result`   | 最终查询结果 |
| `error`    | 异常消息     |

### 7. 启动前端

```bash
cd frontend
pnpm install
pnpm dev
```

前端默认通过 Vite 代理把 `/api` 转发到 `http://127.0.0.1:8000`。如需修改：

```bash
cp .env.example .env
```

```bash
VITE_DEV_PROXY_TARGET=http://127.0.0.1:8000
```

如果前端与后端不在同一域部署，可设置：

```bash
VITE_API_BASE_URL=http://127.0.0.1:8000
```

## 能力边界

当前项目聚焦可运行的智能问数主链路，暂不包含用户登录、角色权限、数据权限、SQL 白名单、查询缓存、系统化评测、监控告警和灰度发布等生产治理能力。
