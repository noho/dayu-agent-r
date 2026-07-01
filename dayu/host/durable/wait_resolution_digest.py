"""Host wait resolution digest material helper。

本模块集中维护 ``resolve_wait`` 幂等 digest 使用的 outcome JSON 投影。
callback adapter 与 direct resolve path 必须复用这里的实现，避免同一
wait resolution 语义在不同入口产生不同 digest。
"""

from __future__ import annotations

from dayu.contracts.json_value import JsonValue
from dayu.contracts.tool_outcome import ToolCancelledOutcome
from dayu.contracts.tool_result import ToolResultFailure, ToolResultMeta, ToolResultSuccess
from dayu.host.api import (
    HostPayloadRef,
    ResolveWaitCancelledOutcome,
    ResolveWaitCompletedOutcome,
    ResolveWaitFailedOutcome,
    ResolveWaitLostOutcome,
    ResolveWaitOutcome,
    WaitProviderStatusRef,
)
from dayu.host.durable.codec import sha256_digest_json

WAIT_RESOLUTION_OUTCOME_KIND_COMPLETED = "completed"
WAIT_RESOLUTION_OUTCOME_KIND_FAILED = "failed"
WAIT_RESOLUTION_OUTCOME_KIND_CANCELLED = "cancelled"
WAIT_RESOLUTION_OUTCOME_KIND_LOST = "lost"


def wait_resolution_digest(
    wait_id: str, idempotency_key: str, outcome: ResolveWaitOutcome
) -> str:
    """计算 wait resolution 语义 digest。

    :param wait_id: wait record id。
    :param idempotency_key: resolve wait 幂等键。
    :param outcome: resolve wait outcome。
    :returns: Host canonical sha256 digest。
    :raises TypeError: outcome 非封闭联合成员时抛出。
    """

    return sha256_digest_json(
        {
            "wait_id": wait_id,
            "idempotency_key": idempotency_key,
            "outcome": resolve_wait_outcome_json(outcome),
        }
    )


def resolve_wait_outcome_json(outcome: ResolveWaitOutcome) -> JsonValue:
    """把 resolve wait outcome 投影为 digest JSON。

    :param outcome: resolve wait outcome。
    :returns: JSON 值。
    :raises TypeError: outcome 非封闭联合成员时抛出。
    """

    if isinstance(outcome, ResolveWaitCompletedOutcome):
        return {
            "kind": WAIT_RESOLUTION_OUTCOME_KIND_COMPLETED,
            "result": resolve_wait_completed_result_json(outcome.result),
            "payload_ref": _host_payload_ref_json(outcome.payload_ref),
        }
    if isinstance(outcome, ResolveWaitFailedOutcome):
        return {
            "kind": WAIT_RESOLUTION_OUTCOME_KIND_FAILED,
            "result": resolve_wait_failed_result_json(outcome.result),
            "payload_ref": _host_payload_ref_json(outcome.payload_ref),
        }
    if isinstance(outcome, ResolveWaitCancelledOutcome):
        return {
            "kind": WAIT_RESOLUTION_OUTCOME_KIND_CANCELLED,
            "result": resolve_wait_cancelled_result_json(outcome.result),
            "payload_ref": _host_payload_ref_json(outcome.payload_ref),
        }
    if isinstance(outcome, ResolveWaitLostOutcome):
        return {
            "kind": WAIT_RESOLUTION_OUTCOME_KIND_LOST,
            "result": resolve_wait_lost_result_json(outcome),
        }
    raise TypeError("unsupported resolve wait outcome")


def resolve_wait_completed_result_json(result: ToolResultSuccess) -> JsonValue:
    """把工具成功结果投影为 JSON。

    :param result: 工具成功结果。
    :returns: JSON mapping。
    """

    return {
        "ok": result.ok,
        "value": result.value,
        "meta": _tool_result_meta_json(result.meta),
    }


def resolve_wait_failed_result_json(result: ToolResultFailure) -> JsonValue:
    """把工具失败结果投影为 JSON。

    :param result: 工具失败结果。
    :returns: JSON mapping。
    """

    return {
        "ok": result.ok,
        "error": result.error,
        "message": result.message,
        "hint": result.hint,
        "meta": _tool_result_meta_json(result.meta),
    }


def resolve_wait_cancelled_result_json(result: ToolCancelledOutcome) -> JsonValue:
    """把工具级取消结果投影为 JSON。

    :param result: 工具级取消结果。
    :returns: JSON mapping。
    """

    return {
        "reason": result.reason,
        "message": result.message,
        "hint": result.hint,
        "meta": _tool_result_meta_json(result.meta),
    }


def resolve_wait_lost_result_json(outcome: ResolveWaitLostOutcome) -> JsonValue:
    """把 lost 等待结果投影为 JSON。

    :param outcome: lost outcome。
    :returns: JSON mapping。
    """

    return {
        "reason_code": outcome.reason_code,
        "message": outcome.message,
        "provider_status_ref": _provider_status_ref_json(
            outcome.provider_status_ref
        ),
    }


def _tool_result_meta_json(meta: ToolResultMeta | None) -> JsonValue:
    """把工具结果 meta 投影为 JSON。

    :param meta: 工具结果 meta。
    :returns: JSON 值。
    """

    if meta is None:
        return None
    return {
        "tool_name": meta.tool_name,
        "started_at": meta.started_at.isoformat(),
        "finished_at": meta.finished_at.isoformat(),
    }


def _host_payload_ref_json(payload_ref: HostPayloadRef | None) -> JsonValue:
    """把 Host payload 引用投影为 JSON。

    :param payload_ref: payload 引用或 ``None``。
    :returns: JSON 值。
    """

    if payload_ref is None:
        return None
    return {
        "payload_ref": payload_ref.payload_ref,
        "payload_digest": payload_ref.payload_digest,
    }


def _provider_status_ref_json(
    provider_status_ref: WaitProviderStatusRef | None,
) -> JsonValue:
    """把 provider 状态引用投影为 JSON。

    :param provider_status_ref: provider 状态引用或 ``None``。
    :returns: JSON 值。
    """

    if provider_status_ref is None:
        return None
    return {
        "adapter_key": provider_status_ref.adapter_key.value,
        "status_ref": provider_status_ref.status_ref,
        "status_digest": provider_status_ref.status_digest,
    }
