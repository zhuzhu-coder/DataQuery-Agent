"""
自动评测集与回归评测脚本

读取 eval/cases.yaml，逐条调用现有 QueryService，收集 SSE 事件并输出评测报告。
"""

import argparse
import asyncio
import sys
from pathlib import Path
from time import perf_counter

from app.clients.embedding_client_manager import embedding_client_manager
from app.clients.es_client_manager import es_client_manager
from app.clients.milvus_client_manager import milvus_client_manager
from app.clients.mysql_client_manager import (
    dw_mysql_client_manager,
    meta_mysql_client_manager,
)
from app.evaluation.runner import (
    build_report,
    collect_case_events,
    evaluate_case,
    load_cases,
    write_reports,
)
from app.repositories.es.value_es_repository import ValueESRepository
from app.repositories.mysql.dw.dw_mysql_repository import DWMySQLRepository
from app.repositories.mysql.meta.meta_mysql_repository import MetaMySQLRepository
from app.repositories.mysql.meta.query_audit_repository import QueryAuditRepository
from app.repositories.vector.column_vector_repository import ColumnVectorRepository
from app.repositories.vector.metric_vector_repository import MetricVectorRepository
from app.services.conversation_memory import ConversationMemoryStore
from app.services.query_service import QueryService


async def run_eval(
    case_path: Path,
    output_dir: Path,
    min_pass_rate: float,
    case_ids: set[str] | None = None,
) -> int:
    """
    执行评测并根据通过率返回进程退出码
    Args:
        case_path: 评测用例文件路径
        output_dir: 输出目录
        min_pass_rate: 最小通过率
        case_ids: 可选的用例 ID 集合，仅执行这些用例
    Returns:
        进程退出码，0 表示通过率符合要求，1 表示通过率不符合要求
    """

    cases = load_cases(case_path)
    if case_ids:
        cases = [case for case in cases if case.get("id") in case_ids]
    if not cases:
        raise ValueError("没有可执行的评测用例")
    
    # 初始化所有客户端
    _init_clients()
    try:
        async with (
            meta_mysql_client_manager.session_factory() as meta_session,
            dw_mysql_client_manager.session_factory() as dw_session,
        ):
            query_audit_repository = QueryAuditRepository(meta_session)
            await query_audit_repository.ensure_table()
            memory_store = ConversationMemoryStore()
            query_service = QueryService(
                meta_mysql_repository=MetaMySQLRepository(meta_session),
                embedding_client=embedding_client_manager.client,
                dw_mysql_repository=DWMySQLRepository(dw_session),
                column_vector_repository=ColumnVectorRepository(
                    milvus_client_manager.client
                ),
                metric_vector_repository=MetricVectorRepository(
                    milvus_client_manager.client
                ),
                value_es_repository=ValueESRepository(es_client_manager.client),
                query_audit_repository=query_audit_repository,
                conversation_memory_store=memory_store,
            )

            results = []
            for case in cases:
                print(f"RUN {case['id']} - {_case_question(case)}")
                start = perf_counter()
                events = await collect_case_events(query_service, case)# 所有事件
                duration_ms = int((perf_counter() - start) * 1000)
                result = evaluate_case(case, events, duration_ms)
                results.append(result)
                print(("PASS" if result["passed"] else "FAIL") + f" {case['id']}")
                for failure in result["failures"]:
                    print(f"  - {failure}")

        report = build_report(results) # 构建报告
        write_reports(report, output_dir) # 写报告
        _print_summary(report, output_dir) # 打印摘要
        return 0 if report["pass_rate"] >= min_pass_rate else 1
    finally:
        await _close_clients()


def _init_clients():
    """初始化所有客户端"""
    milvus_client_manager.init()
    embedding_client_manager.init()
    es_client_manager.init()
    meta_mysql_client_manager.init()
    dw_mysql_client_manager.init()


async def _close_clients():
    """关闭所有客户端"""
    await embedding_client_manager.close()
    await milvus_client_manager.close()
    await es_client_manager.close()
    await meta_mysql_client_manager.close()
    await dw_mysql_client_manager.close()


def _print_summary(report: dict, output_dir: Path):
    """打印评测摘要"""
    print()
    print(f"总用例：{report['total']}")
    print(f"通过：{report['passed']}")
    print(f"失败：{report['failed']}")
    print(f"通过率：{report['pass_rate']:.1%}")
    print(f"报告：{output_dir / 'latest.md'}")


def _case_question(case: dict) -> str:
    question = case.get("question")
    if question:
        return str(question)
    conversation = case.get("conversation")
    if isinstance(conversation, list):
        return " -> ".join(str(item) for item in conversation)
    return ""


def main():
    # 创建命令行参数解析器
    parser = argparse.ArgumentParser(description="运行自动评测集")
    # 添加参数
    # 定义评测用例文件路径参数
    parser.add_argument(
        "-c",
        "--cases",
        type=Path,
        default=Path("eval/cases.yaml"),
        help="评测用例 YAML 文件路径",
    )
    # 定义输出目录参数
    parser.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        default=Path("eval/reports"),
        help="评测报告输出目录",
    )
    # 定义最低通过率参数
    parser.add_argument(
        "--min-pass-rate",
        type=float,
        default=1.0,
        help="最低通过率，低于该值时退出码为 1",
    )
    # 定义用例 ID 参数
    parser.add_argument(
        "--case-id",
        action="append",
        default=[],
        help="只运行指定用例，可重复传入",
    )
    # 解析命令行参数
    args = parser.parse_args()

    exit_code = asyncio.run(
        run_eval(
            case_path=args.cases,
            output_dir=args.output_dir,
            min_pass_rate=args.min_pass_rate,
            case_ids=set(args.case_id) if args.case_id else None,
        )
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
