"""
字段召回节点

负责根据关键词从字段向量知识库中召回候选字段
它解决的是“用户问题可能对应哪些数据库字段”的问题
关键词扩展 -> Embedding -> 向量相似度检索 -> ColumnInfo 去重
"""

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate
from langgraph.runtime import Runtime

from app.agent.context import DataQueryAgentContext
from app.agent.llm import llm
from app.agent.state import DataQueryAgentState
from app.agent.trace import column_trace_items, emit_trace
from app.core.log import logger
from app.entities.column_info import ColumnInfo
from app.prompt.prompt_loader import load_prompt


async def recall_column(state: DataQueryAgentState, runtime: Runtime[DataQueryAgentContext]):
    """召回和用户问题语义相关的字段元数据"""

    writer = runtime.stream_writer
    step = "召回字段信息"
    writer({"type": "progress", "step": step, "status": "running"})

    try:
        # state 保存图内业务中间结果：原始问题和上游抽取出的关键词
        keywords = state["keywords"]
        query = state["query"]
        # context 保存外部运行时工具：向量仓储和 Embedding 客户端
        column_vector_repository = runtime.context["column_vector_repository"]
        embedding_client = runtime.context["embedding_client"]

        # 用 LLM 把用户问法扩展成“字段语义”列表，例如“销售总额”可扩展出“销售金额”
        prompt = PromptTemplate(
            template=load_prompt("extend_keywords_for_column_recall"), # 提示词模版内容
            input_variables=["query"], # 需要外部填充的变量名列表
        )
        # 提示词要求模型只输出 JSON 数组，解析后 result 就是 list[str]
        output_parser = JsonOutputParser()
        # LCEL 管道：填充提示词 -> 调用模型 -> 解析 JSON
        chain = prompt | llm | output_parser

        try:
            result: list[str] = await chain.ainvoke({"query": query})
        except Exception as e:
            logger.warning(f"{step} keyword expansion failed, fallback to extracted keywords: {e}")
            result = []

        # 原始关键词和 LLM 扩展词一起参与召回；set 去重，避免重复请求同一关键词
        keywords = set(keywords + result)

        # 用字段 id 做唯一键，因为多个关键词、同一字段的多个向量点都可能命中同一个字段
        column_info_map: dict[str, ColumnInfo] = {}
        for keyword in keywords:
            try:
                # 查询词必须先转成向量，才能和知识库中的字段向量做相似度检索
                embedding = await embedding_client.aembed_query(keyword)
                # 当前关键词召回的字段信息列表
                current_column_infos: list[
                    ColumnInfo
                ] = await column_vector_repository.search(embedding)
            except Exception as e:
                logger.warning(f"{step} skipped keyword {keyword!r}: {e}")
                continue
            for column_info in current_column_infos:
                if column_info.id not in column_info_map:
                    column_info_map[column_info.id] = column_info

        # 写回 state 的是去重后的 ColumnInfo 列表，不暴露向量库原始结构
        retrieved_column_infos: list[ColumnInfo] = list(column_info_map.values())

        writer({"type": "progress", "step": step, "status": "success"})
        emit_trace(
            writer,
            step=step,
            title=f"命中 {len(retrieved_column_infos)} 个相关字段",
            summary="围绕用户问题召回候选字段上下文。",
            items=column_trace_items(retrieved_column_infos),
            metadata={"column_count": len(retrieved_column_infos)},
        )
        return {"retrieved_column_infos": retrieved_column_infos} # 返回召回的字段信息列表
    except Exception as e:
        logger.error(f"{step} failed: {e}")
        writer({"type": "progress", "step": step, "status": "error"})
        raise
