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
