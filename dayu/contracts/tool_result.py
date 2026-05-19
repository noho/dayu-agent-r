"""工具结果信封强类型契约。

本模块定义 :data:`ToolResultEnvelope` 联合：

- :class:`ToolResultSuccess`：成功结果，``ok`` 字面量为 ``True``。
- :class:`ToolResultFailure`：失败结果，``ok`` 字面量为 ``False``。

``ok`` 字段是判别字段，pyright 通过 ``Literal[True/False]`` 辨识两端。
辅助类型 :class:`ToolResultMeta` 仅承载非治理性中性事实；本 Phase
不预留任意属性袋。

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
class ToolResultMeta:
    """工具结果中性元信息。

    :param tool_name: 工具名。
    :param started_at: 工具执行开始时间。
    :param finished_at: 工具执行结束时间。
    """

    tool_name: str
    started_at: datetime
    finished_at: datetime

    def __post_init__(self) -> None:
        """校验工具结果元信息的最小完整性。

        :returns: ``None``。
        :raises ValueError: ``tool_name`` 为空 / 纯空白，或结束时间早于开始时间时抛出。
        """

        if self.tool_name.strip() == "":
            raise ValueError("ToolResultMeta.tool_name must be non-empty")
        if self.finished_at < self.started_at:
            raise ValueError(
                "ToolResultMeta.finished_at must be greater than or equal "
                "to started_at"
            )


@dataclass(frozen=True, slots=True)
class ToolResultSuccess:
    """工具调用成功结果。

    :param ok: 判别字段，固定 ``True``。
    :param value: 成功载荷，强类型 JSON 值。
    :param meta: 中性元信息；无元信息为 ``None``。
    """

    ok: Literal[True]
    value: JsonValue
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

    def __post_init__(self) -> None:
        """校验失败结果的最小完整性。

        :returns: ``None``。
        :raises ValueError: ``error`` 或 ``message`` 为空 / 纯空白时抛出。
        """

        if self.error.strip() == "":
            raise ValueError("ToolResultFailure.error must be non-empty")
        if self.message.strip() == "":
            raise ValueError("ToolResultFailure.message must be non-empty")


ToolResultEnvelope: TypeAlias = ToolResultSuccess | ToolResultFailure
"""工具结果信封封闭联合。"""

__all__ = [
    "ToolResultMeta",
    "ToolResultSuccess",
    "ToolResultFailure",
    "ToolResultEnvelope",
]
