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

单轮用例使用 `question`：

```yaml
- id: east_top_products
  question: 查询华东地区 2026 年第一季度销售额最高的前 5 个商品
  expect:
    status: success
```

多轮追问用例使用 `conversation`。评测脚本会为同一个用例生成固定
`conversation_id`，按顺序执行每轮问题，并只对最后一轮事件做断言：

```yaml
- id: follow_up_region_best_product
  conversation:
    - 华东卖得最好的商品
    - 那华北呢
  expect:
    status: success
    trace_steps:
      - 上下文补全
      - 执行SQL
```

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

字符串类元数据可以使用 `contains` 做包含断言，适合检查上下文补全后的问题：

```yaml
trace_metadata:
  - step: 上下文补全
    key: resolved_query
    contains: 华北
```

这可以用来验证 Planner 和 Evaluator 是否按预期工作，而不只是验证最终有没有返回结果。
