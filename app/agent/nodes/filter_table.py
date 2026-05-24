"""
表信息过滤节点

负责在合并后的候选表结构中筛选出当前问题真正需要的表和字段
这里让大模型只返回“保留哪些表和字段”的选择结果，真正的结构裁剪仍由程序完成
"""

import yaml
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate
from langgraph.runtime import Runtime

from app.agent.context import DataQueryAgentContext
from app.agent.llm import llm
from app.agent.observations import observation_update
from app.agent.state import DataQueryAgentState, TableInfoState
from app.agent.trace import emit_trace, table_trace_items
from app.core.log import logger
from app.prompt.prompt_loader import load_prompt


async def filter_table(state: DataQueryAgentState, runtime: Runtime[DataQueryAgentContext]):
    """根据用户问题裁剪候选表结构上下文"""

    writer = runtime.stream_writer
    step = "过滤表信息"
    writer({"type": "progress", "step": step, "status": "running"})

    try:
        query = state["query"]
        table_infos: list[TableInfoState] = state["table_infos"]

        # table_infos 是嵌套结构，转成 YAML 后更适合放进提示词，也保留中文字段说明
        prompt = PromptTemplate(
            template=load_prompt("filter_table_info"),
            input_variables=["query", "table_infos"],
        )
        # filter_table_info prompt 要求模型只输出 JSON 对象：表名 -> 字段名列表
        output_parser = JsonOutputParser()
        # LCEL 管道：填充提示词 -> 调用模型 -> 解析 JSON
        chain = prompt | llm | output_parser

        result = await chain.ainvoke(
            {
                "query": query,
                "table_infos": yaml.dump(
                    table_infos, allow_unicode=True, sort_keys=False # 转换为 YAML 字符串，中文不转义，保留原始字段顺序
                ),
            }
        )
        # 模型只负责选择，程序根据选择结果从原始 TableInfoState 中裁剪，避免模型重写复杂结构出错
        filtered_table_infos: list[TableInfoState] = []
        for table_info in table_infos:
            if table_info["name"] in result:
                table_info["columns"] = [
                    column_info
                    for column_info in table_info["columns"]
                    if column_info["name"] in result[table_info["name"]]
                ]
                filtered_table_infos.append(table_info)

        logger.info(
            f"过滤后的表信息：{[filtered_table_info['name'] for filtered_table_info in filtered_table_infos]}"
        )
        writer({"type": "progress", "step": step, "status": "success"})
        column_count = sum(
            len(filtered_table_info["columns"])
            for filtered_table_info in filtered_table_infos
        )
        emit_trace(
            writer,
            step=step,
            title=f"保留 {len(filtered_table_infos)} 张表、{column_count} 个字段",
            summary="从候选表结构中裁剪出 SQL 生成真正需要的表和字段。",
            items=table_trace_items(filtered_table_infos),
            metadata={
                "table_count": len(filtered_table_infos),
                "field_count": column_count,
            },
        )
        return {
            "table_infos": filtered_table_infos,
            **observation_update(
                "filter_table",
                f"保留 {len(filtered_table_infos)} 张表、{column_count} 个字段",
                {
                    "table_count": len(filtered_table_infos),
                    "field_count": column_count,
                },
            ),
        }

    except Exception as e:
        logger.error(f"{step} failed: {e}")
        writer({"type": "progress", "step": step, "status": "error"})
        raise
