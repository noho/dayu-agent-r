"""Host Tool Trace 结构化 signal 的共享契约。

本模块只承载 Host 内部多生产者/消费者共享的 Tool Trace signal 字段值、
schema version 与 bounded text 裁剪规则，不参与 ToolRuntime 治理、
Engine ingest 状态迁移或 Tool Trace projection 写入。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

CONTEXT_PRESSURE_SCHEMA_VERSION = 1
"""context_pressure signal schema version。"""

TOOL_TIMING_SCHEMA_VERSION = 1
"""tool_timing signal schema version。"""

TOOL_TIMING_STATUS_AVAILABLE = "available"
"""ToolResultMeta 可用时的 tool_timing status。"""

TOOL_TIMING_STATUS_MISSING_META = "missing_tool_result_meta"
"""ToolResultMeta 缺失时的 tool_timing status。"""

TOOL_TIMING_DURATION_SOURCE_META = "tool_result_meta"
"""tool_timing.duration_ms 的唯一合法来源。"""

FAILURE_METADATA_SCHEMA_VERSION = 1
"""failure_metadata signal schema version。"""

PARTIAL_TOOL_CALL_SIGNAL_SCHEMA_VERSION = 1
"""partial_tool_call_signal schema version。"""

PARTIAL_TOOL_CALL_SIGNAL_STATUS_NONE = "none"
"""没有 partial tool-call summary 时的 status。"""

PARTIAL_TOOL_CALL_SIGNAL_STATUS_PRESENT = "present"
"""存在 partial tool-call summary 时的 status。"""

TRACE_SIGNAL_BOUNDED_TEXT_MAX_CHARS = 512
"""failure_metadata 中 LLM-readable 文本字段的最大字符数。"""

FAILURE_KIND_TOOL_FAILED = "tool_failed"
"""工具执行失败 failure kind。"""

FAILURE_KIND_TOOL_CANCELLED = "tool_cancelled"
"""工具执行取消 failure kind。"""

FAILURE_KIND_POLICY_BLOCKED = "policy_blocked"
"""工具治理阻断 failure kind。"""

FAILURE_KIND_PROVIDER_PROTOCOL_ERROR = "provider_protocol_error"
"""provider protocol error failure kind。"""

FAILURE_KIND_CONTEXT_COMPACTION_ATTEMPT_REJECTED = "context_compaction_attempt_rejected"
"""context compaction attempt rejected failure kind。"""

FAILURE_KIND_CONTEXT_COMPACTION_FAILED = "context_compaction_failed"
"""context compaction failed failure kind。"""

FAILURE_METADATA_ALLOWED_KINDS = frozenset(
    {
        FAILURE_KIND_TOOL_FAILED,
        FAILURE_KIND_TOOL_CANCELLED,
        FAILURE_KIND_POLICY_BLOCKED,
        FAILURE_KIND_PROVIDER_PROTOCOL_ERROR,
        FAILURE_KIND_CONTEXT_COMPACTION_ATTEMPT_REJECTED,
        FAILURE_KIND_CONTEXT_COMPACTION_FAILED,
    }
)
"""failure_metadata.failure_kind 的完整闭集。"""


@dataclass(frozen=True, slots=True)
class BoundedTraceSignalText:
    """failure_metadata 中 bounded text 的标准投影。

    :param value: bounded 文本；原文为 ``None`` 时为 ``None``。
    :param sha256_digest: full original UTF-8 文本 digest；原文为 ``None`` 时为
        ``None``。
    :param truncated: 原文是否超过 bounded 字符上限。
    """

    value: str | None
    sha256_digest: str | None
    truncated: bool


def bound_trace_signal_text(value: str | None) -> BoundedTraceSignalText:
    """按 Tool Trace signal 规则裁剪失败文本。

    :param value: 原始文本；可为 ``None``。
    :returns: bounded 文本、full original digest 与截断标志。
    :raises Exception: 不主动抛出异常。
    """

    if value is None:
        return BoundedTraceSignalText(
            value=None,
            sha256_digest=None,
            truncated=False,
        )
    digest = f"sha256:{hashlib.sha256(value.encode('utf-8')).hexdigest()}"
    return BoundedTraceSignalText(
        value=value[:TRACE_SIGNAL_BOUNDED_TEXT_MAX_CHARS],
        sha256_digest=digest,
        truncated=len(value) > TRACE_SIGNAL_BOUNDED_TEXT_MAX_CHARS,
    )
