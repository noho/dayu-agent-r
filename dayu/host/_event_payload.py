"""Host 内部 EventLog payload 读取辅助函数。

本模块只承载 Host 层内部从 durable EventLog row 解析 JSON payload 的
通用逻辑。错误类型使用 Host durable error，不进入 ``dayu.runtime``，
也不表达 Engine / UI / Service 语义。
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import cast

from dayu.contracts.json_value import JsonValue
from dayu.contracts.tool_await import ToolAwaitSpec
from dayu.host.api import HostPayloadRef, WaitProviderStatusRef
from dayu.host.durable.errors import HostDurableError
from dayu.host.durable.event_log import EventLogRow
from dayu.host.durable.state import ExternalJobRef, WaitSnapshotRef


def tool_awaiting_payload(
    *,
    session_id: str,
    run_id: str,
    attempt_id: str,
    execution_id: str,
    iteration_id: str,
    wait_id: str,
    tool_call_id: str,
    tool_name: str,
    await_spec: ToolAwaitSpec,
    adapter_key: str,
    resume_policy: str,
    snapshot_ref: WaitSnapshotRef | None,
    external_job_ref: ExternalJobRef | None,
    accept_idempotency_key: str,
    semantic_input_digest: str,
) -> JsonValue:
    """构造 ``TOOL_AWAITING`` canonical fact 的 inline payload。

    :param session_id: Session id。
    :param run_id: Run id。
    :param attempt_id: Attempt id。
    :param execution_id: execution id。
    :param iteration_id: Engine iteration id。
    :param wait_id: Host wait record id。
    :param tool_call_id: 工具调用 id。
    :param tool_name: 工具名。
    :param await_spec: 工具等待规约。
    :param adapter_key: Host 选择的等待适配器键。
    :param resume_policy: wait resume policy 文本。
    :param snapshot_ref: 可选等待快照引用。
    :param external_job_ref: 可选外部 job 引用。
    :param accept_idempotency_key: awaiting accept 幂等键。
    :param semantic_input_digest: awaiting accept 语义 digest。
    :returns: 可写入 EventLog 的 JSON payload。
    """

    return {
        "session_id": session_id,
        "run_id": run_id,
        "attempt_id": attempt_id,
        "execution_id": execution_id,
        "iteration_id": iteration_id,
        "wait_id": wait_id,
        "tool_call_id": tool_call_id,
        "tool_name": tool_name,
        "await_spec": _await_spec_json(await_spec),
        "adapter_key": adapter_key,
        "resume_policy": resume_policy,
        "snapshot_ref": _snapshot_ref_json(snapshot_ref),
        "external_job_ref": _external_job_ref_json(external_job_ref),
        "accept_idempotency_key": accept_idempotency_key,
        "semantic_input_digest": semantic_input_digest,
    }


def run_waiting_payload(
    *,
    session_id: str,
    run_id: str,
    attempt_id: str,
    wait_id: str,
    tool_awaiting_event_ref: Mapping[str, JsonValue],
) -> JsonValue:
    """构造 ``RUN_WAITING`` canonical fact 的 inline payload。

    :param session_id: Session id。
    :param run_id: Run id。
    :param attempt_id: 当前 Attempt id。
    :param wait_id: Host wait record id。
    :param tool_awaiting_event_ref: 对应 ``TOOL_AWAITING`` event ref。
    :returns: 可写入 EventLog 的 JSON payload。
    """

    return {
        "session_id": session_id,
        "run_id": run_id,
        "attempt_id": attempt_id,
        "wait_id": wait_id,
        "tool_awaiting_event_ref": dict(tool_awaiting_event_ref),
    }


def attempt_suspended_payload(
    *,
    session_id: str,
    run_id: str,
    attempt_id: str,
    execution_id: str,
    wait_id: str,
    tool_call_id: str,
    run_waiting_event_ref: Mapping[str, JsonValue],
) -> JsonValue:
    """构造 ``ATTEMPT_SUSPENDED`` canonical fact 的 inline payload。

    :param session_id: Session id。
    :param run_id: Run id。
    :param attempt_id: 被挂起的 Attempt id。
    :param execution_id: execution id。
    :param wait_id: Host wait record id。
    :param tool_call_id: 导致等待的工具调用 id。
    :param run_waiting_event_ref: 对应 ``RUN_WAITING`` event ref。
    :returns: 可写入 EventLog 的 JSON payload。
    """

    return {
        "session_id": session_id,
        "run_id": run_id,
        "attempt_id": attempt_id,
        "execution_id": execution_id,
        "wait_id": wait_id,
        "tool_call_id": tool_call_id,
        "run_waiting_event_ref": dict(run_waiting_event_ref),
    }


def resume_requested_payload(
    *,
    session_id: str,
    run_id: str,
    wait_id: str,
    source_attempt_id: str,
    resume_attempt_id: str,
    resume_dispatch_record_id: str,
    resolution_source: str,
    resolution_kind: str,
    resolution_idempotency_key: str,
    observed_at: str,
    wait_created_event_ref: Mapping[str, JsonValue],
    wait_updated_event_ref: Mapping[str, JsonValue],
) -> JsonValue:
    """构造 ``RESUME_REQUESTED`` canonical fact 的 inline payload。

    :param session_id: Session id。
    :param run_id: Run id。
    :param wait_id: Host wait record id。
    :param source_attempt_id: 被等待挂起的 Attempt id。
    :param resume_attempt_id: 即将创建的 resume Attempt id。
    :param resume_dispatch_record_id: 即将创建的 dispatch record id。
    :param resolution_source: 等待结果来源。
    :param resolution_kind: 等待结果类别。
    :param resolution_idempotency_key: resolve wait 幂等键。
    :param observed_at: 外部结果观察时间。
    :param wait_created_event_ref: 创建 wait 的事件引用。
    :param wait_updated_event_ref: 进入等待时最后更新 wait 的事件引用。
    :returns: 可写入 EventLog 的 JSON payload。
    """

    return {
        "session_id": session_id,
        "run_id": run_id,
        "wait_id": wait_id,
        "source_attempt_id": source_attempt_id,
        "resume_attempt_id": resume_attempt_id,
        "resume_dispatch_record_id": resume_dispatch_record_id,
        "resolution_source": resolution_source,
        "resolution_kind": resolution_kind,
        "resolution_idempotency_key": resolution_idempotency_key,
        "observed_at": observed_at,
        "wait_created_event_ref": dict(wait_created_event_ref),
        "wait_updated_event_ref": dict(wait_updated_event_ref),
    }


def tool_result_wait_resolution_payload(
    *,
    tool_fact_id: str,
    session_id: str,
    run_id: str,
    attempt_id: str,
    execution_id: str,
    iteration_id: str,
    tool_call_id: str,
    tool_name: str,
    tool_schema_digest: str,
    tool_identity_digest: str,
    normalized_arguments_digest: str,
    tool_fact_kind: str,
    outcome_digest: str,
    payload_digest: str | None,
    payload_ref: HostPayloadRef | None,
    resolution_result: JsonValue,
    wait_id: str,
    resolution_source: str,
    resolution_kind: str,
    resolution_idempotency_key: str,
    observed_at: str,
    wait_record_status_before: str,
    wait_record_status_after: str,
    wait_created_event_ref: Mapping[str, JsonValue],
    wait_updated_event_ref: Mapping[str, JsonValue],
    adapter_key: str,
    external_job_ref: ExternalJobRef | None,
    snapshot_ref: WaitSnapshotRef | None,
    provider_status_ref: WaitProviderStatusRef | None,
    resume_attempt_id: str | None,
    resume_dispatch_record_id: str | None,
) -> JsonValue:
    """构造 resolve wait 产生的 ``TOOL_RESULT_ACCEPTED`` payload。

    :param tool_fact_id: Host 工具事实 id。
    :param session_id: Session id。
    :param run_id: Run id。
    :param attempt_id: 产生等待的 Attempt id。
    :param execution_id: 产生等待的 execution id。
    :param iteration_id: 产生等待的 Engine iteration id。
    :param tool_call_id: 工具调用 id。
    :param tool_name: 工具名。
    :param tool_schema_digest: 工具 schema digest。
    :param tool_identity_digest: 工具身份 digest。
    :param normalized_arguments_digest: 规范化参数 digest。
    :param tool_fact_kind: 工具事实类别。
    :param outcome_digest: 等待结果 digest。
    :param payload_digest: payload digest；无则为 ``None``。
    :param payload_ref: 可选 Host payload descriptor 引用。
    :param resolution_result: 结果 envelope 的 JSON 投影。
    :param wait_id: Host wait record id。
    :param resolution_source: 等待结果来源。
    :param resolution_kind: 等待结果类别。
    :param resolution_idempotency_key: resolve wait 幂等键。
    :param observed_at: 外部结果观察时间。
    :param wait_record_status_before: wait record 原状态。
    :param wait_record_status_after: wait record 新状态。
    :param wait_created_event_ref: 创建 wait 的事件引用。
    :param wait_updated_event_ref: 本次更新 wait 的事件引用。
    :param adapter_key: wait adapter key。
    :param external_job_ref: 外部 job 引用。
    :param snapshot_ref: 等待快照引用。
    :param provider_status_ref: provider 状态引用。
    :param resume_attempt_id: resume Attempt id；不恢复时为 ``None``。
    :param resume_dispatch_record_id: resume dispatch id；不恢复时为 ``None``。
    :returns: 可写入 EventLog 的 JSON payload。
    """

    return {
        "tool_fact_id": tool_fact_id,
        "session_id": session_id,
        "run_id": run_id,
        "attempt_id": attempt_id,
        "execution_id": execution_id,
        "iteration_id": iteration_id,
        "tool_call_id": tool_call_id,
        "tool_name": tool_name,
        "tool_schema_digest": tool_schema_digest,
        "tool_identity_digest": tool_identity_digest,
        "normalized_arguments_digest": normalized_arguments_digest,
        "tool_fact_kind": tool_fact_kind,
        "outcome_digest": outcome_digest,
        "payload_digest": payload_digest,
        "payload_ref": _payload_ref_json(payload_ref),
        "truncation": None,
        "duplicate_key": None,
        "duplicate_decision": None,
        "policy_decision": None,
        "tool_idempotency_key": resolution_idempotency_key,
        "diagnostic_refs": [],
        "accepted_event_refs": [],
        "result": resolution_result,
        "wait_id": wait_id,
        "resolution_source": resolution_source,
        "resolution_kind": resolution_kind,
        "resolution_idempotency_key": resolution_idempotency_key,
        "observed_at": observed_at,
        "wait_record_status_before": wait_record_status_before,
        "wait_record_status_after": wait_record_status_after,
        "wait_created_event_ref": dict(wait_created_event_ref),
        "wait_updated_event_ref": dict(wait_updated_event_ref),
        "adapter_key": adapter_key,
        "external_job_ref": _external_job_ref_json(external_job_ref),
        "snapshot_ref": _snapshot_ref_json(snapshot_ref),
        "provider_status_ref": _provider_status_ref_json(provider_status_ref),
        "resume_attempt_id": resume_attempt_id,
        "resume_dispatch_record_id": resume_dispatch_record_id,
    }


def wait_late_result_rejected_payload(
    *,
    wait_id: str,
    run_id: str,
    attempt_id: str,
    tool_call_id: str,
    tool_name: str,
    source: str,
    idempotency_key: str,
    observed_at: str,
    wait_status: str,
    rejection_reason: str,
    outcome_kind: str,
    outcome_digest: str,
    payload_ref: HostPayloadRef | None,
    provider_status_ref: WaitProviderStatusRef | None,
    external_job_ref: ExternalJobRef | None,
    adapter_key: str,
) -> JsonValue:
    """构造 ``WAIT_LATE_RESULT_REJECTED`` diagnostic payload。

    :param wait_id: Host wait record id。
    :param run_id: Run id。
    :param attempt_id: 产生 wait 的 Attempt id。
    :param tool_call_id: 工具调用 id。
    :param tool_name: 工具名。
    :param source: resolve wait 来源。
    :param idempotency_key: resolve wait 幂等键。
    :param observed_at: 外部结果观察时间。
    :param wait_status: 拒绝时 wait record 状态。
    :param rejection_reason: 拒绝原因码。
    :param outcome_kind: 等待结果类别。
    :param outcome_digest: 等待结果 digest。
    :param payload_ref: 可选 Host payload descriptor 引用。
    :param provider_status_ref: 可选 provider 状态引用。
    :param external_job_ref: 可选外部 job 引用。
    :param adapter_key: wait adapter key。
    :returns: 可写入 EventLog 的 JSON payload。
    """

    return {
        "wait_id": wait_id,
        "run_id": run_id,
        "attempt_id": attempt_id,
        "tool_call_id": tool_call_id,
        "tool_name": tool_name,
        "source": source,
        "idempotency_key": idempotency_key,
        "observed_at": observed_at,
        "wait_status": wait_status,
        "rejection_reason": rejection_reason,
        "outcome_kind": outcome_kind,
        "outcome_digest": outcome_digest,
        "payload_ref": _payload_ref_json(payload_ref),
        "provider_status_ref": _provider_status_ref_json(provider_status_ref),
        "external_job_ref": _external_job_ref_json(external_job_ref),
        "adapter_key": adapter_key,
    }


def payload_object(event: EventLogRow) -> Mapping[str, JsonValue]:
    """解析 EventLog payload JSON 映射。

    :param event: EventLog row。
    :returns: payload 映射。
    :raises HostDurableError: payload JSON 非法或不是 JSON 映射时抛出。
    """

    try:
        value = cast(JsonValue, json.loads(event.payload_json))
    except json.JSONDecodeError as exc:
        raise HostDurableError("EventLog payload_json is invalid") from exc
    if not isinstance(value, Mapping):
        raise HostDurableError("EventLog payload_json must be a JSON mapping")
    return cast(Mapping[str, JsonValue], value)


def required_payload_text(
    payload: Mapping[str, JsonValue], *, field_name: str
) -> str:
    """读取 payload 中的必填文本字段。

    :param payload: payload 映射。
    :param field_name: 字段名。
    :returns: 文本值。
    :raises HostDurableError: 字段缺失或不是非空文本时抛出。
    """

    value = payload.get(field_name)
    if not isinstance(value, str) or value.strip() == "":
        raise HostDurableError(f"payload field {field_name} must be non-empty text")
    return value


def optional_payload_text(
    payload: Mapping[str, JsonValue], *, field_name: str
) -> str | None:
    """读取 payload 中的可选文本字段。

    字段缺失或显式为 ``null`` 时返回 ``None``；字段存在但不是非空文本时
    抛出 durable error，避免 projection consumer 从非 typed 字段猜测语义。

    :param payload: payload 映射。
    :param field_name: 字段名。
    :returns: 文本值或 ``None``。
    :raises HostDurableError: 字段存在但不是非空文本时抛出。
    """

    value = payload.get(field_name)
    if value is None:
        return None
    if isinstance(value, str) and value.strip() != "":
        return value
    raise HostDurableError(f"payload field {field_name} must be non-empty text")


def _await_spec_json(await_spec: ToolAwaitSpec) -> JsonValue:
    """把工具等待规约投影为 JSON。

    :param await_spec: 工具等待规约。
    :returns: JSON mapping。
    """

    return {
        "await_kind": await_spec.await_kind.value,
        "deadline": (
            await_spec.deadline.isoformat()
            if await_spec.deadline is not None
            else None
        ),
        "resume_token": await_spec.resume_token,
    }


def _snapshot_ref_json(snapshot_ref: WaitSnapshotRef | None) -> JsonValue:
    """把等待快照引用投影为 JSON。

    :param snapshot_ref: 快照引用或 ``None``。
    :returns: JSON 值。
    """

    if snapshot_ref is None:
        return None
    return {
        "snapshot_id": snapshot_ref.snapshot_id,
        "captured_at": snapshot_ref.captured_at.isoformat(),
        "snapshot_digest": snapshot_ref.snapshot_digest,
    }


def _external_job_ref_json(external_job_ref: ExternalJobRef | None) -> JsonValue:
    """把外部 job 引用投影为 JSON。

    :param external_job_ref: 外部 job 引用或 ``None``。
    :returns: JSON 值。
    """

    if external_job_ref is None:
        return None
    return {
        "adapter_key": external_job_ref.adapter_key.value,
        "external_job_id": external_job_ref.external_job_id,
    }


def _payload_ref_json(payload_ref: HostPayloadRef | None) -> JsonValue:
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
    """把等待 provider 状态引用投影为 JSON。

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
