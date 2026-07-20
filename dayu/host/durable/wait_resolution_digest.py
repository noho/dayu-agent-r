"""Host wait resolution digest material helper。

本模块集中维护 ``resolve_wait`` 幂等 digest 使用的 outcome JSON 投影。
callback adapter 与 direct resolve path 必须复用这里的实现，避免同一
wait resolution 语义在不同入口产生不同 digest。
"""

from __future__ import annotations

from dayu.contracts.json_value import JsonValue
from dayu.contracts.tool_outcome import (
    ToolCancelledOutcome,
    ToolCompletedOutcome,
    ToolFailedOutcome,
)
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
from dayu.host.accepted_tool_outcome import accepted_tool_outcome_json

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
            "tool_outcome": accepted_tool_outcome_json(
                ToolCompletedOutcome(outcome.result)
            ),
            "payload_ref": _host_payload_ref_json(outcome.payload_ref),
        }
    if isinstance(outcome, ResolveWaitFailedOutcome):
        return {
            "kind": WAIT_RESOLUTION_OUTCOME_KIND_FAILED,
            "tool_outcome": accepted_tool_outcome_json(
                ToolFailedOutcome(outcome.result)
            ),
            "payload_ref": _host_payload_ref_json(outcome.payload_ref),
        }
    if isinstance(outcome, ResolveWaitCancelledOutcome):
        return {
            "kind": WAIT_RESOLUTION_OUTCOME_KIND_CANCELLED,
            "tool_outcome": accepted_tool_outcome_json(outcome.result),
            "payload_ref": _host_payload_ref_json(outcome.payload_ref),
        }
    if isinstance(outcome, ResolveWaitLostOutcome):
        return {
            "kind": WAIT_RESOLUTION_OUTCOME_KIND_LOST,
            "result": resolve_wait_lost_result_json(outcome),
        }
    raise TypeError("unsupported resolve wait outcome")


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
