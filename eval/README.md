# 自动评测集与回归评测

这个目录保存端到端问数评测用例和评测报告

## 运行

先确保基础服务、后端依赖和元数据知识库已经准备好：

```powershell
docker compose -f docker/docker-compose.yaml up -d
uv run python -m app.scripts.build_meta_knowledge -c conf/meta_config.yaml
```

运行完整评测：

```powershell
uv run python -m app.scripts.run_eval -c eval/cases.yaml
```

只运行单个用例：

```powershell
uv run python -m app.scripts.run_eval -c eval/cases.yaml --case-id east_top_products
```

允许最低通过率，例如 CI 里要求 80%：

```powershell
uv run python -m app.scripts.run_eval -c eval/cases.yaml --min-pass-rate 0.8
```

## 报告

脚本会生成：

```text
eval/reports/latest.json
eval/reports/latest.md
```

`latest.json` 适合机器读取，`latest.md` 适合人工排查
