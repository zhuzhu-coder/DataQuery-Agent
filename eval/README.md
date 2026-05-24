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

## 断言能力

`cases.yaml` 中的 `expect.trace_steps` 用于检查是否出现指定执行节点。

如果需要检查某个 trace 节点的结构化元数据，可以使用 `trace_metadata`：

```yaml
trace_metadata:
  - step: 制定查询计划
    key: need_clarification
    equals: false
  - step: 评估SQL答案
    key: decision
    equals: pass
```

这可以用来验证 Planner 和 Evaluator 是否按预期工作，而不只是验证最终有没有返回结果。
