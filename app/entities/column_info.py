"""
字段元数据业务实体

字段配置中的业务语义、从数仓补齐的真实类型，以及抽样得到的示例值，
都会汇总到这个对象里，再继续流向元数据库与后续检索链路
"""

from dataclasses import dataclass
from typing import Any


@dataclass
class ColumnInfo:
    """系统内部统一使用的字段元数据表达"""

    id: str # 字段 ID
    name: str # 字段业务名称
    type: str # 字段真实类型
    role: str # 字段业务角色
    examples: list[Any] # 字段示例值
    description: str # 字段业务描述
    alias: list[str] # 字段别名
    table_id: str # 字段所属表 ID
