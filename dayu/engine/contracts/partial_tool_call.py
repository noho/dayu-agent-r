"""Engine / Runner provider protocol failure partial tool-call summary。"""

from __future__ import annotations

from dataclasses import dataclass

PARTIAL_TOOL_CALL_ID_MAX_CHARS: int = 128
"""partial tool call 诊断中保留的 provider id 最大字符数。"""


@dataclass(frozen=True, slots=True)
class PartialToolCallSummary:
    """未完成 tool call 的有界诊断摘要。

    :param tool_call_index: provider tool call index。
    :param tool_call_id: provider 已给出的 tool call id 有界片段；未知为
        ``None``。
    :param name_fragment: 已解析工具名的有界片段；未知为 ``None``。
    :param arguments_byte_size: 已收到 arguments delta 的 UTF-8 字节数。
    :param arguments_sha256: 已收到 arguments delta 的 sha256；未收到为
        ``None``。本字段只用于比对，不含 raw argument payload。
    """

    tool_call_index: int
    tool_call_id: str | None
    name_fragment: str | None
    arguments_byte_size: int
    arguments_sha256: str | None


__all__ = ["PARTIAL_TOOL_CALL_ID_MAX_CHARS", "PartialToolCallSummary"]
