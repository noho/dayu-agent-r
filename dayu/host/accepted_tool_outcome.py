"""Host accepted 工具 outcome canonical codec。

本模块是 Host 对 completed / failed / cancelled accepted tool outcome 的
唯一 JSON atom owner。ToolRuntime 普通结果、wait resolution 结果、
digest material 与 resume 消费路径必须复用这里的投影，避免同一工具业务
终态在不同入口出现不同 shape。
"""

from __future__ import annotations

from typing import TypeAlias

from dayu.contracts.json_value import JsonValue
from dayu.contracts.tool_outcome import (
    ToolCancelledOutcome,
    ToolCompletedOutcome,
    ToolFailedOutcome,
)
from dayu.contracts.tool_result import ToolResultMeta
from dayu.host.durable.codec import canonical_json_dumps, sha256_digest_json

AcceptedToolOutcome: TypeAlias = (
    ToolCompletedOutcome | ToolFailedOutcome | ToolCancelledOutcome
)
"""Host accepted 工具 outcome 封闭联合。"""


def accepted_tool_outcome_json(outcome: AcceptedToolOutcome) -> JsonValue:
    """把 accepted 工具 outcome 投影为 canonical JSON atom。

    :param outcome: completed / failed / cancelled 工具 outcome。
    :returns: 可写入 ``raw_tool_outcome`` 与 digest material 的 JSON atom。
    :raises TypeError: 收到封闭联合之外的 outcome 时抛出。
    """

    if isinstance(outcome, ToolCompletedOutcome):
        return {
            "kind": "completed",
            "result": {
                "ok": outcome.result.ok,
                "value": outcome.result.value,
                "meta": _tool_result_meta_json(outcome.result.meta),
            },
        }
    if isinstance(outcome, ToolFailedOutcome):
        return {
            "kind": "failed",
            "result": {
                "ok": outcome.result.ok,
                "error": outcome.result.error,
                "message": outcome.result.message,
                "hint": outcome.result.hint,
                "meta": _tool_result_meta_json(outcome.result.meta),
            },
        }
    if isinstance(outcome, ToolCancelledOutcome):
        return {
            "kind": "cancelled",
            "reason": outcome.reason,
            "message": outcome.message,
            "hint": outcome.hint,
            "meta": _tool_result_meta_json(outcome.meta),
        }
    raise TypeError("unsupported accepted tool outcome")


def accepted_tool_outcome_digest(outcome: AcceptedToolOutcome) -> str:
    """计算 accepted 工具 outcome canonical digest。

    :param outcome: completed / failed / cancelled 工具 outcome。
    :returns: Host canonical sha256 digest。
    :raises TypeError: 收到封闭联合之外的 outcome 时抛出。
    """

    return sha256_digest_json(accepted_tool_outcome_json(outcome))


def accepted_tool_outcome_inline_size_bytes(outcome: AcceptedToolOutcome) -> int:
    """估算 accepted 工具 outcome canonical atom 的 UTF-8 字节数。

    :param outcome: completed / failed / cancelled 工具 outcome。
    :returns: canonical JSON atom 的 UTF-8 字节数。
    :raises TypeError: 收到封闭联合之外的 outcome 时抛出。
    """

    return len(canonical_json_dumps(accepted_tool_outcome_json(outcome)).encode("utf-8"))


def _tool_result_meta_json(meta: ToolResultMeta | None) -> JsonValue:
    """把工具结果 meta 投影为 JSON。

    :param meta: 工具结果 meta。
    :returns: JSON 值。
    :raises Exception: 不主动抛出异常。
    """

    if meta is None:
        return None
    return {
        "tool_name": meta.tool_name,
        "started_at": meta.started_at.isoformat(),
        "finished_at": meta.finished_at.isoformat(),
    }
