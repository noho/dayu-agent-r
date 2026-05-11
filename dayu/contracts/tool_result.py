"""工具结果信封强类型契约。

本模块定义 :data:`ToolResultEnvelope` 联合：

- :class:`ToolResultSuccess`：成功结果，``ok`` 字面量为 ``True``。
- :class:`ToolResultFailure`：失败结果，``ok`` 字面量为 ``False``。

``ok`` 字段是判别字段，pyright 通过 ``Literal[True/False]`` 辨识两端。
辅助类型 :class:`ToolTruncationInfo` / :class:`ToolResultMeta` 仅承载
非治理性中性事实；本 Phase 不预留任意属性袋。

注意：等待型工具结果不进入本信封，而是通过 :class:`ToolAwaitingOutcome`
显式承载（见 ``tool_outcome`` 模块）。本信封不应包含 ``await_spec`` /
``await`` 等指向 :class:`ToolAwaitSpec` 的字段。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, TypeAlias

from dayu.contracts.json_value import JsonValue


@dataclass(frozen=True, slots=True)
class ToolTruncationInfo:
    """工具级截断元信息（中性事实）。

    ``ToolTruncationInfo`` 是普通 LLM-facing 工具结果载荷的一部分。
    Host EventLog / trace 可按普通工具结果保留该载荷；Conversation
    Memory 与下一轮 RunInput 只摄取不可复用摘要，不持久复用 cursor、
    ``scope_token`` 或完整 ``fetch_more_args``。

    :param cursor: 截断补读 cursor 原文；只用于短期 LLM roundtrip。
    :param scope_token: 截断 scope 唯一 token。
    :param scope_hash: 截断 scope 内容 hash。
    :param has_more: 是否还有未取回数据。
    :param limit: 建议 ``fetch_more`` 单次读取上限；``None`` 表示不投影。
    :param ttl_seconds: scope 的有效期秒数；``None`` 表示由 Host 决定。
    """

    cursor: str
    scope_token: str
    scope_hash: str
    has_more: bool
    limit: int | None
    ttl_seconds: int | None


@dataclass(frozen=True, slots=True)
class ToolResultMeta:
    """工具结果中性元信息。

    :param tool_name: 工具名。
    :param started_at: 工具执行开始时间。
    :param finished_at: 工具执行结束时间。
    """

    tool_name: str
    started_at: datetime
    finished_at: datetime


@dataclass(frozen=True, slots=True)
class ToolResultSuccess:
    """工具调用成功结果。

    :param ok: 判别字段，固定 ``True``。
    :param value: 成功载荷，强类型 JSON 值。
    :param truncation: 工具级截断信息；无截断为 ``None``。
    :param meta: 中性元信息；无元信息为 ``None``。
    """

    ok: Literal[True]
    value: JsonValue
    truncation: ToolTruncationInfo | None
    meta: ToolResultMeta | None


@dataclass(frozen=True, slots=True)
class ToolResultFailure:
    """工具调用失败结果。

    :param ok: 判别字段，固定 ``False``。
    :param error: 错误码（中性字符串，由工具发布方约定）。
    :param message: 人类可读错误描述。
    :param hint: 可选的恢复提示文本；无为 ``None``。
    :param meta: 中性元信息；无元信息为 ``None``。
    """

    ok: Literal[False]
    error: str
    message: str
    hint: str | None
    meta: ToolResultMeta | None


ToolResultEnvelope: TypeAlias = ToolResultSuccess | ToolResultFailure
"""工具结果信封封闭联合。"""

__all__ = [
    "ToolTruncationInfo",
    "ToolResultMeta",
    "ToolResultSuccess",
    "ToolResultFailure",
    "ToolResultEnvelope",
]
