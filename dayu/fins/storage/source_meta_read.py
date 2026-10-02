"""同一稳定根中的原始来源观察及严格完整性观察。

每份元数据来自本次独立 JSON 解析并提供顶层只读映射，独立于其他公开
读取与后续发布；嵌套 JSON 值由消费者只读使用，不承诺深冻结。
SourceMetaReadView 不承诺完整性，读取失败时保留有序成功前缀和首个原异常。
SourceMetaIntegrityReadEntry 由严格读取产生，绑定同根的既有完整性分类；
该读取遇错原样抛出，不返回部分观察或新增写入授权。
"""

from collections.abc import Mapping
from dataclasses import dataclass

from dayu.contracts.json_value import JsonValue
from dayu.fins.domain.enums import SourceKind
from .source_integrity import SourceIntegrityClassification


@dataclass(frozen=True, slots=True)
class SourceMetaReadEntry:
    """单份成功读取的元数据；document_id 为外部身份，source_meta 为只读观察。"""

    document_id: str
    source_meta: Mapping[str, JsonValue]


@dataclass(frozen=True, slots=True)
class SourceMetaReadView:
    """一次同窗读取；ticker/source_kind 标明范围，entries 为有序成功前缀。

    read_error 是首个元数据读取 ValueError/OSError 原对象；仅为 None 时
    entries 覆盖完整枚举。此观察不包含完整性结论或写入授权。
    """

    ticker: str
    source_kind: SourceKind
    entries: tuple[SourceMetaReadEntry, ...]
    read_error: ValueError | OSError | None


@dataclass(frozen=True, slots=True)
class SourceMetaIntegrityReadEntry:
    """稳定根内严格读取的原始元数据与同窗物理完整性分类；嵌套 JSON 只读。"""

    document_id: str
    source_meta: Mapping[str, JsonValue]
    integrity: SourceIntegrityClassification
