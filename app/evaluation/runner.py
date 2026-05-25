"""
自动评测核心逻辑

这里保持和外部服务解耦：输入是用例和 Agent SSE 事件，输出是结构化评测结果
脚本层负责真正调用 QueryService 和写报告
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml


def load_cases(path: Path) -> list[dict[str, Any]]:
    """从 YAML 文件读取评测用例列表"""

    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    cases = data.get("cases", [])
    if not isinstance(cases, list):
        raise ValueError("评测文件中的 cases 必须是列表")
    return cases


def parse_sse_events(chunks: list[str]) -> list[dict[str, Any]]:
    """解析 QueryService 产出的 SSE 文本块"""

    events: list[dict[str, Any]] = []
    for chunk in chunks:
        payload = "\n".join(
            line.replace("data:", "", 1).strip()
            for line in chunk.splitlines()
            if line.startswith("data:")
        ).strip()
        if not payload:
            continue
        events.append(json.loads(payload))
    return events


async def collect_query_events(
    query_service: Any, question: str, conversation_id: str | None = None
) -> list[dict[str, Any]]:
    """执行一次 QueryService 查询并收集结构化 SSE 事件"""
    # 收集所有事件
    chunks = []
    async for chunk in query_service.query(question, conversation_id=conversation_id):
        chunks.append(chunk)
    return parse_sse_events(chunks)


async def collect_case_events(query_service: Any, case: dict[str, Any]) -> list[dict[str, Any]]:
    """执行单轮或多轮评测用例，并返回最后一轮的事件"""

    conversation = case.get("conversation")
    if not conversation:
        return await collect_query_events(query_service, str(case["question"]))
    if not isinstance(conversation, list) or not conversation:
        raise ValueError(f"用例 {case.get('id')} 的 conversation 必须是非空列表")

    conversation_id = f"eval-{case.get('id')}"
    events: list[dict[str, Any]] = []
    for question in conversation:
        events = await collect_query_events(
            query_service,
            str(question),
            conversation_id=conversation_id,
        )
    return events


def evaluate_case(
    case: dict[str, Any],
    events: list[dict[str, Any]],
    duration_ms: int,
) -> dict[str, Any]:
    """根据期望规则评估单个用例是否通过"""
    # 期望的预期结果
    expect = case.get("expect", {})
    # 最后一次 result 事件
    result_event = _last_event(events, "result")
    # 最后一次普通回答事件
    answer_event = _last_event(events, "answer")
    # 最后一次 error 事件
    error_event = _last_event(events, "error")
    # 所有 trace 步骤
    trace_steps = [
        str(event.get("step"))
        for event in events
        if event.get("type") == "trace" and event.get("step")
    ]
    # 返回的数据行标准化
    rows = _normalize_rows(result_event.get("data") if result_event else None)
    # 实际返回的字段列表
    actual_columns = _result_columns(rows)
    # 最终状态
    status = _actual_status(events, result_event, answer_event, error_event)
    # 失败原因列表
    failures: list[str] = []

    _check_status(expect, status, failures)       # 检查状态是否符合预期
    _check_rows(expect, rows, failures)           # 检查返回行数是否符合预期
    _check_columns(expect, actual_columns, failures)  # 检查返回列是否符合预期
    _check_error(expect, error_event, failures)   # 检查报错是否符合预期
    _check_answer(expect, answer_event, failures)  # 检查普通回答是否符合预期
    _check_trace_steps(expect, trace_steps, failures)  # 检查执行步骤是否符合预期
    _check_trace_metadata(expect, events, failures)  # 检查关键轨迹元数据是否符合预期
    _check_duration(expect, duration_ms, failures)  # 检查耗时是否在允许范围内

    return {
        "id": case.get("id"),
        "question": _case_question(case),
        "passed": not failures,
        "status": status,
        "duration_ms": duration_ms,
        "row_count": len(rows),
        "columns": actual_columns,
        "answer": answer_event.get("content") if answer_event else "",
        "trace_steps": trace_steps,
        "error_message": error_event.get("message") if error_event else "",
        "failures": failures,
    }


def build_report(case_results: list[dict[str, Any]]) -> dict[str, Any]:
    """汇总所有用例结果"""

    total = len(case_results)
    passed = sum(1 for result in case_results if result["passed"])
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate": passed / total if total else 0,
        "cases": case_results,
    }


def write_reports(report: dict[str, Any], output_dir: Path):
    """写 JSON 和 Markdown 两种报告，方便机器和人阅读"""

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "latest.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "latest.md").write_text(render_markdown_report(report), encoding="utf-8")


def render_markdown_report(report: dict[str, Any]) -> str:
    """生成简洁 Markdown 评测报告"""

    lines = [
        "# 自动评测报告",
        "",
        f"- 生成时间：{report['generated_at']}",
        f"- 总用例：{report['total']}",
        f"- 通过：{report['passed']}",
        f"- 失败：{report['failed']}",
        f"- 通过率：{report['pass_rate']:.1%}",
        "",
        "## 用例结果",
        "",
    ]
    for result in report["cases"]:
        mark = "PASS" if result["passed"] else "FAIL"
        lines.append(f"### {mark} {result['id']}")
        lines.append("")
        lines.append(f"- 问题：{result['question']}")
        lines.append(f"- 状态：{result['status']}")
        lines.append(f"- 行数：{result['row_count']}")
        lines.append(f"- 耗时：{result['duration_ms']}ms")
        if result.get("answer"):
            lines.append(f"- 回答：{result['answer']}")
        if result["failures"]:
            lines.append("- 失败原因：")
            for failure in result["failures"]:
                lines.append(f"  - {failure}")
        lines.append("")
    return "\n".join(lines)


def _actual_status(
    events: list[dict[str, Any]],
    result_event: dict[str, Any] | None,
    answer_event: dict[str, Any] | None,
    error_event: dict[str, Any] | None,
) -> str:
    """根据事件判断实际状态"""
    if result_event:
        return "success"
    if answer_event:
        return "answered"
    if not error_event:
        return "failed"

    for event in events:
        if (
            event.get("type") == "trace"
            and event.get("step") == "查询终止"
            and (event.get("metadata") or {}).get("error_type") == "security"
        ):
            return "rejected"
    return "failed"


def _last_event(events: list[dict[str, Any]], event_type: str) -> dict[str, Any] | None:
    """返回指定类型的最后一个事件"""
    for event in reversed(events):
        if event.get("type") == event_type:
            return event
    return None


def _normalize_rows(data: Any) -> list[dict[str, Any]]:
    """将数据转换为行列表"""
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        return [data]
    return []


def _result_columns(rows: list[dict[str, Any]]) -> list[str]:
    """提取结果中的所有字段"""
    columns: list[str] = []
    for row in rows:
        for key in row.keys():
            if key not in columns:
                columns.append(str(key))
    return columns


def _check_status(expect: dict[str, Any], status: str, failures: list[str]):
    """检查状态是否匹配"""
    expected = expect.get("status")
    if expected and status != expected:
        failures.append(f"状态不匹配：期望 {expected}，实际 {status}")


def _check_rows(expect: dict[str, Any], rows: list[dict[str, Any]], failures: list[str]):
    row_count = len(rows)
    """检查返回行数是否符合预期"""
    if "row_count" in expect and row_count != expect["row_count"]:
        failures.append(f"行数不匹配：期望 {expect['row_count']}，实际 {row_count}")
    if "min_rows" in expect and row_count < expect["min_rows"]:
        failures.append(f"行数过少：至少 {expect['min_rows']}，实际 {row_count}")
    if "max_rows" in expect and row_count > expect["max_rows"]:
        failures.append(f"行数过多：最多 {expect['max_rows']}，实际 {row_count}")


def _check_columns(
    expect: dict[str, Any], actual_columns: list[str], failures: list[str]
):
    """检查字段是否匹配"""
    for column in expect.get("columns", []):
        if column not in actual_columns:
            failures.append(f"缺少字段：{column}")

    for group in expect.get("column_any", []):
        if not any(_column_matches(candidate, actual_columns) for candidate in group):
            failures.append(f"缺少字段之一：{' / '.join(group)}")


def _column_matches(candidate: str, actual_columns: list[str]) -> bool:
    """检查字段是否匹配"""
    candidate_lower = candidate.lower()
    for column in actual_columns:
        column_lower = column.lower()
        if candidate_lower == column_lower:
            return True
        if candidate_lower in column_lower or column_lower in candidate_lower:
            return True
    return False


def _check_error(
    expect: dict[str, Any],
    error_event: dict[str, Any] | None,
    failures: list[str],
):
    """检查错误信息是否包含指定文本"""
    expected_text = expect.get("error_contains")
    if not expected_text:
        return
    message = error_event.get("message", "") if error_event else ""
    if expected_text not in message:
        failures.append(f"错误信息不包含：{expected_text}")


def _check_answer(
    expect: dict[str, Any],
    answer_event: dict[str, Any] | None,
    failures: list[str],
):
    """检查普通回答是否包含指定文本"""
    expected_text = expect.get("answer_contains")
    if not expected_text:
        return
    content = answer_event.get("content", "") if answer_event else ""
    if expected_text not in content:
        failures.append(f"普通回答不包含：{expected_text}")


def _check_trace_steps(
    expect: dict[str, Any],
    trace_steps: list[str],
    failures: list[str],
):
    """检查执行步骤是否符合预期"""
    for step in expect.get("trace_steps", []):
        if step not in trace_steps:
            failures.append(f"缺少轨迹节点：{step}")


def _check_trace_metadata(
    expect: dict[str, Any],
    events: list[dict[str, Any]],
    failures: list[str],
):
    """检查指定 trace 节点的 metadata 是否符合预期"""

    trace_events = [
        event
        for event in events
        if event.get("type") == "trace" and event.get("step")
    ]
    for rule in expect.get("trace_metadata", []):
        step = rule.get("step")
        key = rule.get("key")
        if not step or not key:
            continue

        matched_events = [
            event for event in trace_events if event.get("step") == step
        ]
        if not matched_events:
            failures.append(f"缺少轨迹元数据节点：{step}")
            continue

        expected_value = rule.get("equals")
        expected_contains = rule.get("contains")
        actual_value = None
        key_found = False
        for event in reversed(matched_events):
            metadata = event.get("metadata") or {}
            if key in metadata:
                actual_value = metadata.get(key)
                key_found = True
                break

        if not key_found:
            failures.append(f"轨迹元数据缺少字段：节点 {step} 的 {key}")
            continue

        if "equals" in rule and actual_value != expected_value:
            failures.append(
                "轨迹元数据不匹配："
                f"节点 {step} 的 {key} 期望 {expected_value}，实际 {actual_value}"
            )
        if expected_contains is not None and expected_contains not in str(actual_value):
            failures.append(
                "轨迹元数据不包含："
                f"节点 {step} 的 {key} 期望包含 {expected_contains}，实际 {actual_value}"
            )


def _check_duration(expect: dict[str, Any], duration_ms: int, failures: list[str]):
    max_duration_ms = expect.get("max_duration_ms")
    """检查耗时是否在允许范围内"""
    if max_duration_ms is not None and duration_ms > max_duration_ms:
        failures.append(f"耗时过长：最多 {max_duration_ms}ms，实际 {duration_ms}ms")


def _case_question(case: dict[str, Any]) -> str:
    question = case.get("question")
    if question:
        return str(question)
    conversation = case.get("conversation")
    if isinstance(conversation, list):
        return " -> ".join(str(item) for item in conversation)
    return ""
