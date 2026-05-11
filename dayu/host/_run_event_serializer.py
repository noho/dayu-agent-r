"""Host P6 RunEventData 序列化注册表。

本模块为 durable EventLog 提供 ``RunEventType -> RunEventData`` 的封闭
强类型 serializer / deserializer。它不是开放 dict / asdict / 字符串化
payload；遇到未知类型、缺失 schema version 或字段不匹配时必须 fail-fast。

每个 payload 形如：

```
{
    "schema_version": 1,
    "type_name": "<RunEventType>.<DataClass>",
    "fields": {...}
}
```

``type_name`` 携带 ``RunEventType`` 与 dataclass 名称作为稳定 discriminator；
``fields`` 是该 dataclass 各字段的 JSON 表达。schema_version 当前固定为
``1``；schema 变化时必须按全新起库处理，禁止旧库兼容读取。
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime
from typing import TypeAlias

from dayu.contracts.json_value import JsonValue
from dayu.contracts.tool_await import ToolAwaitKind, ToolAwaitSnapshot, ToolAwaitSpec
from dayu.contracts.tool_call import GeminiToolCallState, ToolCallProviderState
from dayu.contracts.tool_outcome import (
    ToolAwaitingOutcome,
    ToolCompletedOutcome,
    ToolExecutionOutcome,
    ToolFailedOutcome,
)
from dayu.contracts.tool_result import (
    ToolResultFailure,
    ToolResultMeta,
    ToolResultSuccess,
    ToolTruncationInfo,
)
from dayu.engine.contracts.agent_run import ContextBudgetSnapshot, RunResumeHint
from dayu.engine.contracts.engine_events import (
    ContentCompleteData,
    ContentDeltaData,
    ContextCompactionRequestedData,
    FinalAnswerData,
    IterationStartedData,
    ProviderProtocolErrorData,
    ReasoningDeltaData,
    RunCancelledData,
    RunFailedData,
    RunSuspendedData,
    RunnerDoneEngineData,
    RunnerUsageData,
    ToolAwaitingData,
    ToolCallRequestedData,
    ToolResultAcceptedData,
)
from dayu.engine.contracts.finish_reason import FinishReason
from dayu.host._credential_scrub import (
    scrub_tool_arguments,
    scrub_tool_execution_outcome,
)
from dayu.host.contracts import (
    ContextCompactFailureReason,
    HostContextAttemptRetryData,
    HostContextCompactCompletedData,
    HostContextCompactFailedData,
    HostContextCompactRequestedData,
    HostContextOverflowObservedData,
    HostRunFailedData,
    RunEventData,
    RunEventType,
    RunInputContextMeta,
    RunInputContextSnapshotBuiltData,
    RunInputMessageSummary,
    RunInputToolSchemaSummary,
    UserInputAcceptedData,
    UserInputScope,
)

CURRENT_SCHEMA_VERSION: int = 1
_ERROR_UNKNOWN_TYPE: str = "unknown_run_event_data_type"
_ERROR_TYPE_MISMATCH: str = "run_event_type_data_mismatch"
_ERROR_MISSING_SCHEMA_VERSION: str = "missing_schema_version"
_ERROR_UNSUPPORTED_SCHEMA_VERSION: str = "unsupported_schema_version"
_ERROR_MISSING_TYPE_NAME: str = "missing_type_name"
_ERROR_INVALID_FIELDS: str = "invalid_fields_payload"
_ERROR_INVALID_AWAIT_KIND: str = "invalid_tool_await_kind"
_ERROR_INVALID_FINISH_REASON: str = "invalid_finish_reason"
_ERROR_INVALID_USER_INPUT_SCOPE: str = "invalid_user_input_scope"
_ERROR_INVALID_FAILURE_REASON: str = "invalid_context_compact_failure_reason"
_ERROR_INVALID_OUTCOME_TYPE: str = "invalid_tool_outcome_type"
_ERROR_INVALID_PROVIDER_STATE: str = "invalid_tool_call_provider_state"


_PayloadFields: TypeAlias = Mapping[str, JsonValue]


def serialize_run_event_data(
    *,
    event_type: RunEventType,
    data: RunEventData,
) -> str:
    """将 ``RunEventData`` 序列化为 JSON 字符串。

    :param event_type: RunEvent 类型，用于校验与 ``data`` 类型匹配。
    :param data: 强类型 RunEventData。
    :returns: JSON 字符串。
    :raises ValueError: ``data`` 类型与 ``event_type`` 不匹配时抛出。
    """

    expected_cls = _DATA_CLASS_BY_TYPE.get(event_type)
    allowed_classes: tuple[type, ...]
    if event_type is RunEventType.RUN_FAILED:
        # RUN_FAILED 既允许 Engine 的 RunFailedData，也允许 Host append 的
        # HostRunFailedData，靠 ``exception_type`` 字段在 deserialize 时区分。
        allowed_classes = (RunFailedData, HostRunFailedData)
    elif expected_cls is None:
        raise ValueError(
            f"{_ERROR_UNKNOWN_TYPE}: {event_type.value}"
        )
    else:
        allowed_classes = (expected_cls,)
    if not isinstance(data, allowed_classes):
        raise ValueError(
            f"{_ERROR_TYPE_MISMATCH}: type={event_type.value}; "
            f"data={type(data).__name__}"
        )
    fields = _encode_fields(event_type=event_type, data=data)
    payload: dict[str, JsonValue] = {
        "schema_version": CURRENT_SCHEMA_VERSION,
        "type_name": _type_name(event_type=event_type, data=data),
        "fields": fields,
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def deserialize_run_event_data(
    *,
    event_type: RunEventType,
    raw: str,
) -> RunEventData:
    """将 JSON 字符串还原为 ``RunEventData``。

    :param event_type: RunEvent 类型。
    :param raw: 序列化字符串。
    :returns: 强类型 RunEventData。
    :raises ValueError: schema 版本缺失 / 不支持，type_name 缺失或与
        ``event_type`` 不匹配，字段不合法时抛出。
    """

    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError(_ERROR_INVALID_FIELDS)
    schema_version_raw = parsed.get("schema_version")
    if not isinstance(schema_version_raw, int):
        raise ValueError(_ERROR_MISSING_SCHEMA_VERSION)
    if schema_version_raw != CURRENT_SCHEMA_VERSION:
        raise ValueError(
            f"{_ERROR_UNSUPPORTED_SCHEMA_VERSION}: {schema_version_raw}"
        )
    type_name = parsed.get("type_name")
    if not isinstance(type_name, str):
        raise ValueError(_ERROR_MISSING_TYPE_NAME)
    expected_cls = _DATA_CLASS_BY_TYPE.get(event_type)
    if expected_cls is None:
        raise ValueError(f"{_ERROR_UNKNOWN_TYPE}: {event_type.value}")
    allowed_type_names: tuple[str, ...]
    if event_type is RunEventType.RUN_FAILED:
        allowed_type_names = (
            _expected_type_name(
                event_type=event_type, cls_name=RunFailedData.__name__
            ),
            _expected_type_name(
                event_type=event_type, cls_name=HostRunFailedData.__name__
            ),
        )
    else:
        allowed_type_names = (
            _expected_type_name(
                event_type=event_type, cls_name=expected_cls.__name__
            ),
        )
    if type_name not in allowed_type_names:
        raise ValueError(
            f"{_ERROR_TYPE_MISMATCH}: type={event_type.value}; "
            f"type_name={type_name}"
        )
    fields = parsed.get("fields")
    if not isinstance(fields, dict):
        raise ValueError(_ERROR_INVALID_FIELDS)
    return _decode_fields(event_type=event_type, fields=fields)


def _type_name(*, event_type: RunEventType, data: RunEventData) -> str:
    """构造稳定 type_name discriminator。

    :param event_type: RunEvent 类型。
    :param data: RunEventData 实例。
    :returns: 形如 ``"<event_type>::<DataClass>"`` 的字符串。
    :raises Exception: 不主动抛出异常。
    """

    return f"{event_type.value}::{type(data).__name__}"


def _expected_type_name(*, event_type: RunEventType, cls_name: str) -> str:
    """计算指定 RunEventType 的预期 type_name。

    :param event_type: RunEvent 类型。
    :param cls_name: dataclass 名称。
    :returns: type_name discriminator。
    :raises Exception: 不主动抛出异常。
    """

    return f"{event_type.value}::{cls_name}"


def _encode_fields(
    *,
    event_type: RunEventType,
    data: RunEventData,
) -> Mapping[str, JsonValue]:
    """根据 RunEventType 编码 dataclass 字段。

    :param event_type: RunEvent 类型。
    :param data: RunEventData 实例。
    :returns: JSON 字段映射。
    :raises ValueError: 类型分派失败时抛出。
    """

    if isinstance(data, IterationStartedData):
        return {
            "iteration_id": data.iteration_id,
            "iteration_index": data.iteration_index,
            "message_count": data.message_count,
        }
    if isinstance(data, ContentDeltaData) or isinstance(data, ReasoningDeltaData):
        return {"iteration_id": data.iteration_id, "delta": data.delta}
    if isinstance(data, ContentCompleteData):
        return {
            "iteration_id": data.iteration_id,
            "content": data.content,
            "reasoning_content": data.reasoning_content,
            "finish_reason": data.finish_reason.value,
        }
    if isinstance(data, ToolCallRequestedData):
        return {
            "iteration_id": data.iteration_id,
            "tool_call_id": data.tool_call_id,
            "name": data.name,
            "arguments": dict(scrub_tool_arguments(data.arguments)),
            "index_in_iteration": data.index_in_iteration,
            "provider_state": _encode_provider_state(data.provider_state),
        }
    if isinstance(data, ToolResultAcceptedData):
        return {
            "iteration_id": data.iteration_id,
            "tool_call_id": data.tool_call_id,
            "name": data.name,
            "index_in_iteration": data.index_in_iteration,
            "outcome": _encode_outcome(
                scrub_tool_execution_outcome(data.outcome)
            ),
        }
    if isinstance(data, ToolAwaitingData):
        return {
            "iteration_id": data.iteration_id,
            "tool_call_id": data.tool_call_id,
            "await_spec": _encode_await_spec(data.await_spec),
        }
    if isinstance(data, ContextCompactionRequestedData):
        return {
            "iteration_id": data.iteration_id,
            "budget_state": _encode_budget(data.budget_state),
            "reason": data.reason,
        }
    if isinstance(data, RunnerUsageData):
        return {
            "iteration_id": data.iteration_id,
            "prompt_tokens": data.prompt_tokens,
            "completion_tokens": data.completion_tokens,
            "total_tokens": data.total_tokens,
        }
    if isinstance(data, ProviderProtocolErrorData):
        return {
            "iteration_id": data.iteration_id,
            "error_code": data.error_code,
            "message": data.message,
            "provider_request_id": data.provider_request_id,
            "raw_payload": data.raw_payload,
        }
    if isinstance(data, RunnerDoneEngineData):
        return {
            "iteration_id": data.iteration_id,
            "finish_reason": data.finish_reason.value,
        }
    if isinstance(data, FinalAnswerData):
        return {
            "content": data.content,
            "filtered": data.filtered,
            "degraded": data.degraded,
            "finish_reason": data.finish_reason.value,
        }
    if isinstance(data, RunSuspendedData):
        return {
            "reason": data.reason,
            "resume_hint": (
                None if data.resume_hint is None else data.resume_hint.message
            ),
        }
    if isinstance(data, RunCancelledData):
        return {
            "reason": data.reason,
            "requested_at": data.requested_at.isoformat(),
            "accepted_at": data.accepted_at.isoformat(),
            "finished_at": data.finished_at.isoformat(),
        }
    if isinstance(data, RunFailedData):
        return {
            "error_code": data.error_code,
            "message": data.message,
            "recoverable": data.recoverable,
        }
    if isinstance(data, HostRunFailedData):
        return {
            "error_code": data.error_code,
            "message": data.message,
            "recoverable": data.recoverable,
            "exception_type": data.exception_type,
        }
    if isinstance(data, UserInputAcceptedData):
        return {
            "turn_id": data.turn_id,
            "content": data.content,
            "scope": data.scope.value,
        }
    if isinstance(data, HostContextOverflowObservedData):
        return {
            "attempt_index": data.attempt_index,
            "engine_event_type": data.engine_event_type,
            "engine_error_code": data.engine_error_code,
            "recoverable": data.recoverable,
            "reason": data.reason,
        }
    if isinstance(data, HostContextCompactRequestedData):
        return {
            "attempt_index": data.attempt_index,
            "policy_id": data.policy_id,
            "before_token_estimate": data.before_token_estimate,
            "before_char_size": data.before_char_size,
            "estimator_id": data.estimator_id,
        }
    if isinstance(data, HostContextCompactCompletedData):
        return {
            "attempt_index": data.attempt_index,
            "policy_id": data.policy_id,
            "before_token_estimate": data.before_token_estimate,
            "after_token_estimate": data.after_token_estimate,
            "before_char_size": data.before_char_size,
            "after_char_size": data.after_char_size,
            "reduced": data.reduced,
            "preserved_current_user": data.preserved_current_user,
            "preserved_pinned_state": data.preserved_pinned_state,
            "preserved_evidence_anchors": data.preserved_evidence_anchors,
            "preserved_source_cursors": data.preserved_source_cursors,
            "preserved_tool_facts": data.preserved_tool_facts,
            "dropped_item_count": data.dropped_item_count,
            "degraded_item_count": data.degraded_item_count,
            "estimator_id": data.estimator_id,
        }
    if isinstance(data, HostContextCompactFailedData):
        return {
            "attempt_index": data.attempt_index,
            "policy_id": data.policy_id,
            "reason": data.reason.value,
            "message": data.message,
            "before_token_estimate": data.before_token_estimate,
            "after_token_estimate": data.after_token_estimate,
            "before_char_size": data.before_char_size,
            "after_char_size": data.after_char_size,
            "estimator_id": data.estimator_id,
        }
    if isinstance(data, HostContextAttemptRetryData):
        return {
            "from_attempt_index": data.from_attempt_index,
            "next_attempt_index": data.next_attempt_index,
            "policy_id": data.policy_id,
            "reason": data.reason,
        }
    if isinstance(data, RunInputContextSnapshotBuiltData):
        return _encode_run_input_context_snapshot(data)
    raise ValueError(f"{_ERROR_UNKNOWN_TYPE}: {type(data).__name__}")


def _decode_fields(
    *,
    event_type: RunEventType,
    fields: Mapping[str, JsonValue],
) -> RunEventData:
    """根据 RunEventType 解码字段。

    :param event_type: RunEvent 类型。
    :param fields: JSON 字段映射。
    :returns: 强类型 RunEventData。
    :raises ValueError: 类型未知或字段非法时抛出。
    """

    if event_type is RunEventType.ITERATION_STARTED:
        return IterationStartedData(
            iteration_id=_get_str(fields, "iteration_id"),
            iteration_index=_get_int(fields, "iteration_index"),
            message_count=_get_int(fields, "message_count"),
        )
    if event_type is RunEventType.RUNNER_CONTENT_DELTA:
        return ContentDeltaData(
            iteration_id=_get_str(fields, "iteration_id"),
            delta=_get_str(fields, "delta"),
        )
    if event_type is RunEventType.RUNNER_REASONING_DELTA:
        return ReasoningDeltaData(
            iteration_id=_get_str(fields, "iteration_id"),
            delta=_get_str(fields, "delta"),
        )
    if event_type is RunEventType.RUNNER_CONTENT_COMPLETED:
        return ContentCompleteData(
            iteration_id=_get_str(fields, "iteration_id"),
            content=_get_optional_str(fields, "content"),
            reasoning_content=_get_optional_str(fields, "reasoning_content"),
            finish_reason=_decode_finish_reason(fields, "finish_reason"),
        )
    if event_type is RunEventType.TOOL_CALL_REQUESTED:
        arguments = _get_mapping(fields, "arguments")
        return ToolCallRequestedData(
            iteration_id=_get_str(fields, "iteration_id"),
            tool_call_id=_get_str(fields, "tool_call_id"),
            name=_get_str(fields, "name"),
            arguments=arguments,
            index_in_iteration=_get_int(fields, "index_in_iteration"),
            provider_state=_decode_provider_state(fields.get("provider_state")),
        )
    if event_type is RunEventType.TOOL_RESULT_ACCEPTED:
        outcome = _decode_outcome(fields.get("outcome"))
        if isinstance(outcome, ToolAwaitingOutcome):
            raise ValueError(_ERROR_INVALID_OUTCOME_TYPE)
        return ToolResultAcceptedData(
            iteration_id=_get_str(fields, "iteration_id"),
            tool_call_id=_get_str(fields, "tool_call_id"),
            name=_get_str(fields, "name"),
            index_in_iteration=_get_int(fields, "index_in_iteration"),
            outcome=outcome,
        )
    if event_type is RunEventType.TOOL_AWAITING:
        return ToolAwaitingData(
            iteration_id=_get_str(fields, "iteration_id"),
            tool_call_id=_get_str(fields, "tool_call_id"),
            await_spec=_decode_await_spec(fields.get("await_spec")),
        )
    if event_type is RunEventType.CONTEXT_COMPACTION_REQUESTED:
        return ContextCompactionRequestedData(
            iteration_id=_get_str(fields, "iteration_id"),
            budget_state=_decode_budget(fields.get("budget_state")),
            reason=_get_str(fields, "reason"),
        )
    if event_type is RunEventType.RUNNER_USAGE_RECORDED:
        return RunnerUsageData(
            iteration_id=_get_str(fields, "iteration_id"),
            prompt_tokens=_get_int(fields, "prompt_tokens"),
            completion_tokens=_get_int(fields, "completion_tokens"),
            total_tokens=_get_int(fields, "total_tokens"),
        )
    if event_type is RunEventType.PROVIDER_PROTOCOL_ERROR:
        return ProviderProtocolErrorData(
            iteration_id=_get_str(fields, "iteration_id"),
            error_code=_get_str(fields, "error_code"),
            message=_get_str(fields, "message"),
            provider_request_id=_get_optional_str(fields, "provider_request_id"),
            raw_payload=fields.get("raw_payload"),
        )
    if event_type is RunEventType.RUNNER_DONE:
        return RunnerDoneEngineData(
            iteration_id=_get_str(fields, "iteration_id"),
            finish_reason=_decode_finish_reason(fields, "finish_reason"),
        )
    if event_type is RunEventType.FINAL_ANSWER:
        return FinalAnswerData(
            content=_get_str(fields, "content"),
            filtered=_get_bool(fields, "filtered"),
            degraded=_get_bool(fields, "degraded"),
            finish_reason=_decode_finish_reason(fields, "finish_reason"),
        )
    if event_type is RunEventType.RUN_SUSPENDED:
        hint_msg = _get_optional_str(fields, "resume_hint")
        return RunSuspendedData(
            reason=_get_str(fields, "reason"),
            resume_hint=None if hint_msg is None else RunResumeHint(message=hint_msg),
        )
    if event_type is RunEventType.RUN_CANCELLED:
        return RunCancelledData(
            reason=_get_str(fields, "reason"),
            requested_at=datetime.fromisoformat(_get_str(fields, "requested_at")),
            accepted_at=datetime.fromisoformat(_get_str(fields, "accepted_at")),
            finished_at=datetime.fromisoformat(_get_str(fields, "finished_at")),
        )
    if event_type is RunEventType.RUN_FAILED:
        # RUN_FAILED 既可能由 Engine 派发（``RunFailedData``），也可能由
        # Host append（``HostRunFailedData``）。通过 ``exception_type``
        # 字段是否存在来辨识；不存在时默认还原 Engine 变体。
        if "exception_type" in fields:
            return HostRunFailedData(
                error_code=_get_str(fields, "error_code"),
                message=_get_str(fields, "message"),
                recoverable=_get_bool(fields, "recoverable"),
                exception_type=_get_str(fields, "exception_type"),
            )
        return RunFailedData(
            error_code=_get_str(fields, "error_code"),
            message=_get_str(fields, "message"),
            recoverable=_get_bool(fields, "recoverable"),
        )
    if event_type is RunEventType.USER_INPUT_ACCEPTED:
        scope_value = _get_str(fields, "scope")
        try:
            scope = UserInputScope(scope_value)
        except ValueError as exc:
            raise ValueError(_ERROR_INVALID_USER_INPUT_SCOPE) from exc
        return UserInputAcceptedData(
            turn_id=_get_str(fields, "turn_id"),
            content=_get_str(fields, "content"),
            scope=scope,
        )
    if event_type is RunEventType.CONTEXT_OVERFLOW_OBSERVED:
        return HostContextOverflowObservedData(
            attempt_index=_get_int(fields, "attempt_index"),
            engine_event_type=_get_str(fields, "engine_event_type"),
            engine_error_code=_get_optional_str(fields, "engine_error_code"),
            recoverable=_get_bool(fields, "recoverable"),
            reason=_get_str(fields, "reason"),
        )
    if event_type is RunEventType.CONTEXT_COMPACT_REQUESTED:
        return HostContextCompactRequestedData(
            attempt_index=_get_int(fields, "attempt_index"),
            policy_id=_get_str(fields, "policy_id"),
            before_token_estimate=_get_int(fields, "before_token_estimate"),
            before_char_size=_get_int(fields, "before_char_size"),
            estimator_id=_get_str(fields, "estimator_id"),
        )
    if event_type is RunEventType.CONTEXT_COMPACT_COMPLETED:
        return HostContextCompactCompletedData(
            attempt_index=_get_int(fields, "attempt_index"),
            policy_id=_get_str(fields, "policy_id"),
            before_token_estimate=_get_int(fields, "before_token_estimate"),
            after_token_estimate=_get_int(fields, "after_token_estimate"),
            before_char_size=_get_int(fields, "before_char_size"),
            after_char_size=_get_int(fields, "after_char_size"),
            reduced=_get_bool(fields, "reduced"),
            preserved_current_user=_get_bool(fields, "preserved_current_user"),
            preserved_pinned_state=_get_bool(fields, "preserved_pinned_state"),
            preserved_evidence_anchors=_get_bool(fields, "preserved_evidence_anchors"),
            preserved_source_cursors=_get_bool(fields, "preserved_source_cursors"),
            preserved_tool_facts=_get_bool(fields, "preserved_tool_facts"),
            dropped_item_count=_get_int(fields, "dropped_item_count"),
            degraded_item_count=_get_int(fields, "degraded_item_count"),
            estimator_id=_get_str(fields, "estimator_id"),
        )
    if event_type is RunEventType.CONTEXT_COMPACT_FAILED:
        reason_value = _get_str(fields, "reason")
        try:
            reason = ContextCompactFailureReason(reason_value)
        except ValueError as exc:
            raise ValueError(_ERROR_INVALID_FAILURE_REASON) from exc
        return HostContextCompactFailedData(
            attempt_index=_get_int(fields, "attempt_index"),
            policy_id=_get_str(fields, "policy_id"),
            reason=reason,
            message=_get_str(fields, "message"),
            before_token_estimate=_get_int(fields, "before_token_estimate"),
            after_token_estimate=_get_optional_int(fields, "after_token_estimate"),
            before_char_size=_get_int(fields, "before_char_size"),
            after_char_size=_get_optional_int(fields, "after_char_size"),
            estimator_id=_get_str(fields, "estimator_id"),
        )
    if event_type is RunEventType.CONTEXT_ATTEMPT_RETRYING:
        return HostContextAttemptRetryData(
            from_attempt_index=_get_int(fields, "from_attempt_index"),
            next_attempt_index=_get_int(fields, "next_attempt_index"),
            policy_id=_get_str(fields, "policy_id"),
            reason=_get_str(fields, "reason"),
        )
    if event_type is RunEventType.RUN_INPUT_CONTEXT_SNAPSHOT_BUILT:
        return _decode_run_input_context_snapshot(fields)
    raise ValueError(f"{_ERROR_UNKNOWN_TYPE}: {event_type.value}")


def _encode_provider_state(
    state: ToolCallProviderState | None,
) -> JsonValue:
    """编码 provider 私有续航状态。

    :param state: provider state；为 ``None`` 时返回 ``None``。
    :returns: JSON 表达。
    :raises Exception: 不主动抛出异常。
    """

    if state is None:
        return None
    return {"kind": "gemini", "thought_signature": state.thought_signature}


def _decode_provider_state(value: JsonValue) -> ToolCallProviderState | None:
    """解码 provider 私有续航状态。

    :param value: JSON 表达。
    :returns: provider state 或 ``None``。
    :raises ValueError: payload 非法时抛出。
    """

    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError(_ERROR_INVALID_PROVIDER_STATE)
    kind = value.get("kind")
    if kind != "gemini":
        raise ValueError(_ERROR_INVALID_PROVIDER_STATE)
    signature = value.get("thought_signature")
    if not isinstance(signature, str):
        raise ValueError(_ERROR_INVALID_PROVIDER_STATE)
    return GeminiToolCallState(thought_signature=signature)


def _encode_outcome(
    outcome: ToolExecutionOutcome,
) -> Mapping[str, JsonValue]:
    """编码 ToolExecutionOutcome。

    :param outcome: 工具执行 outcome。
    :returns: JSON 表达。
    :raises ValueError: 类型未知时抛出。
    """

    if isinstance(outcome, ToolCompletedOutcome):
        return {
            "kind": "completed",
            "result": _encode_result_success(outcome.result),
        }
    if isinstance(outcome, ToolFailedOutcome):
        return {
            "kind": "failed",
            "result": _encode_result_failure(outcome.result),
        }
    if isinstance(outcome, ToolAwaitingOutcome):
        snapshot = outcome.snapshot
        return {
            "kind": "awaiting",
            "await_spec": _encode_await_spec(outcome.await_spec),
            "snapshot": (
                None
                if snapshot is None
                else {
                    "snapshot_id": snapshot.snapshot_id,
                    "captured_at": snapshot.captured_at.isoformat(),
                }
            ),
        }
    raise ValueError(_ERROR_INVALID_OUTCOME_TYPE)


def _decode_outcome(value: JsonValue) -> ToolExecutionOutcome:
    """解码 ToolExecutionOutcome。

    :param value: JSON 表达。
    :returns: ToolExecutionOutcome。
    :raises ValueError: 类型非法时抛出。
    """

    if not isinstance(value, dict):
        raise ValueError(_ERROR_INVALID_OUTCOME_TYPE)
    kind = value.get("kind")
    if kind == "completed":
        return ToolCompletedOutcome(
            result=_decode_result_success(value.get("result"))
        )
    if kind == "failed":
        return ToolFailedOutcome(result=_decode_result_failure(value.get("result")))
    if kind == "awaiting":
        snapshot_payload = value.get("snapshot")
        snapshot: ToolAwaitSnapshot | None = None
        if snapshot_payload is not None:
            if not isinstance(snapshot_payload, dict):
                raise ValueError(_ERROR_INVALID_OUTCOME_TYPE)
            captured_at_raw = snapshot_payload.get("captured_at")
            snapshot_id_raw = snapshot_payload.get("snapshot_id")
            if not isinstance(captured_at_raw, str) or not isinstance(
                snapshot_id_raw, str
            ):
                raise ValueError(_ERROR_INVALID_OUTCOME_TYPE)
            snapshot = ToolAwaitSnapshot(
                snapshot_id=snapshot_id_raw,
                captured_at=datetime.fromisoformat(captured_at_raw),
            )
        return ToolAwaitingOutcome(
            await_spec=_decode_await_spec(value.get("await_spec")),
            snapshot=snapshot,
        )
    raise ValueError(_ERROR_INVALID_OUTCOME_TYPE)


def _encode_result_success(result: ToolResultSuccess) -> Mapping[str, JsonValue]:
    """编码 ToolResultSuccess。

    :param result: 成功结果。
    :returns: JSON 表达。
    :raises Exception: 不主动抛出异常。
    """

    truncation = result.truncation
    meta = result.meta
    return {
        "ok": True,
        "value": result.value,
        "truncation": (
            None
            if truncation is None
            else {
                "cursor": truncation.cursor,
                "scope_token": truncation.scope_token,
                "scope_hash": truncation.scope_hash,
                "has_more": truncation.has_more,
                "limit": truncation.limit,
                "ttl_seconds": truncation.ttl_seconds,
            }
        ),
        "meta": (
            None
            if meta is None
            else {
                "tool_name": meta.tool_name,
                "started_at": meta.started_at.isoformat(),
                "finished_at": meta.finished_at.isoformat(),
            }
        ),
    }


def _decode_result_success(value: JsonValue) -> ToolResultSuccess:
    """解码 ToolResultSuccess。

    :param value: JSON 表达。
    :returns: ToolResultSuccess。
    :raises ValueError: 字段非法时抛出。
    """

    if not isinstance(value, dict):
        raise ValueError(_ERROR_INVALID_OUTCOME_TYPE)
    truncation_payload = value.get("truncation")
    truncation: ToolTruncationInfo | None = None
    if truncation_payload is not None:
        if not isinstance(truncation_payload, dict):
            raise ValueError(_ERROR_INVALID_OUTCOME_TYPE)
        truncation = ToolTruncationInfo(
            cursor=_get_str(truncation_payload, "cursor"),
            scope_token=_get_str(truncation_payload, "scope_token"),
            scope_hash=_get_str(truncation_payload, "scope_hash"),
            has_more=_get_bool(truncation_payload, "has_more"),
            limit=_get_optional_int(truncation_payload, "limit"),
            ttl_seconds=_get_optional_int(truncation_payload, "ttl_seconds"),
        )
    meta_payload = value.get("meta")
    meta: ToolResultMeta | None = None
    if meta_payload is not None:
        if not isinstance(meta_payload, dict):
            raise ValueError(_ERROR_INVALID_OUTCOME_TYPE)
        meta = ToolResultMeta(
            tool_name=_get_str(meta_payload, "tool_name"),
            started_at=datetime.fromisoformat(_get_str(meta_payload, "started_at")),
            finished_at=datetime.fromisoformat(
                _get_str(meta_payload, "finished_at")
            ),
        )
    return ToolResultSuccess(
        ok=True,
        value=value.get("value"),
        truncation=truncation,
        meta=meta,
    )


def _decode_result_failure(value: JsonValue) -> ToolResultFailure:
    """解码 ToolResultFailure。

    :param value: JSON 表达。
    :returns: ToolResultFailure。
    :raises ValueError: 字段非法时抛出。
    """

    if not isinstance(value, dict):
        raise ValueError(_ERROR_INVALID_OUTCOME_TYPE)
    meta_payload = value.get("meta")
    meta: ToolResultMeta | None = None
    if meta_payload is not None:
        if not isinstance(meta_payload, dict):
            raise ValueError(_ERROR_INVALID_OUTCOME_TYPE)
        meta = ToolResultMeta(
            tool_name=_get_str(meta_payload, "tool_name"),
            started_at=datetime.fromisoformat(_get_str(meta_payload, "started_at")),
            finished_at=datetime.fromisoformat(
                _get_str(meta_payload, "finished_at")
            ),
        )
    return ToolResultFailure(
        ok=False,
        error=_get_str(value, "error"),
        message=_get_str(value, "message"),
        hint=_get_optional_str(value, "hint"),
        meta=meta,
    )


def _encode_result_failure(result: ToolResultFailure) -> Mapping[str, JsonValue]:
    """编码 ToolResultFailure。

    :param result: 失败结果。
    :returns: JSON 表达。
    :raises Exception: 不主动抛出异常。
    """

    meta = result.meta
    return {
        "ok": False,
        "error": result.error,
        "message": result.message,
        "hint": result.hint,
        "meta": (
            None
            if meta is None
            else {
                "tool_name": meta.tool_name,
                "started_at": meta.started_at.isoformat(),
                "finished_at": meta.finished_at.isoformat(),
            }
        ),
    }


def _encode_await_spec(spec: ToolAwaitSpec) -> Mapping[str, JsonValue]:
    """编码 ToolAwaitSpec。

    :param spec: await 规约。
    :returns: JSON 表达。
    :raises Exception: 不主动抛出异常。
    """

    return {
        "await_kind": spec.await_kind.value,
        "deadline": None if spec.deadline is None else spec.deadline.isoformat(),
        "resume_token": spec.resume_token,
    }


def _decode_await_spec(value: JsonValue) -> ToolAwaitSpec:
    """解码 ToolAwaitSpec。

    :param value: JSON 表达。
    :returns: ToolAwaitSpec。
    :raises ValueError: 字段非法时抛出。
    """

    if not isinstance(value, dict):
        raise ValueError(_ERROR_INVALID_AWAIT_KIND)
    kind_value = _get_str(value, "await_kind")
    try:
        kind = ToolAwaitKind(kind_value)
    except ValueError as exc:
        raise ValueError(_ERROR_INVALID_AWAIT_KIND) from exc
    deadline_raw = value.get("deadline")
    deadline = (
        None if deadline_raw is None else datetime.fromisoformat(_must_str(deadline_raw))
    )
    return ToolAwaitSpec(
        await_kind=kind,
        deadline=deadline,
        resume_token=_get_str(value, "resume_token"),
    )


def _encode_budget(budget: ContextBudgetSnapshot) -> Mapping[str, JsonValue]:
    """编码 ContextBudgetSnapshot。

    :param budget: 上下文预算快照。
    :returns: JSON 表达。
    :raises Exception: 不主动抛出异常。
    """

    return {
        "prompt_tokens": budget.prompt_tokens,
        "completion_tokens": budget.completion_tokens,
        "total_tokens": budget.total_tokens,
    }


def _decode_budget(value: JsonValue) -> ContextBudgetSnapshot:
    """解码 ContextBudgetSnapshot。

    :param value: JSON 表达。
    :returns: ContextBudgetSnapshot。
    :raises ValueError: 字段非法时抛出。
    """

    if not isinstance(value, dict):
        raise ValueError(_ERROR_INVALID_FIELDS)
    return ContextBudgetSnapshot(
        prompt_tokens=_get_int(value, "prompt_tokens"),
        completion_tokens=_get_int(value, "completion_tokens"),
        total_tokens=_get_int(value, "total_tokens"),
    )


def _encode_run_input_message_summary(
    summary: RunInputMessageSummary,
) -> Mapping[str, JsonValue]:
    """编码 RunInputMessageSummary。

    :param summary: 单条消息摘要。
    :returns: JSON 表达。
    :raises Exception: 不主动抛出异常。
    """

    return {
        "role": summary.role,
        "source_kind": summary.source_kind,
        "excerpt": summary.excerpt,
        "content_hash": summary.content_hash,
        "char_size": summary.char_size,
        "token_estimate": summary.token_estimate,
    }


def _decode_run_input_message_summary(
    value: JsonValue,
) -> RunInputMessageSummary:
    """解码 RunInputMessageSummary。

    :param value: JSON 表达。
    :returns: RunInputMessageSummary。
    :raises ValueError: 字段非法时抛出。
    """

    if not isinstance(value, dict):
        raise ValueError(_ERROR_INVALID_FIELDS)
    return RunInputMessageSummary(
        role=_get_str(value, "role"),
        source_kind=_get_str(value, "source_kind"),
        excerpt=_get_str(value, "excerpt"),
        content_hash=_get_str(value, "content_hash"),
        char_size=_get_int(value, "char_size"),
        token_estimate=_get_int(value, "token_estimate"),
    )


def _encode_run_input_tool_schema_summary(
    summary: RunInputToolSchemaSummary,
) -> Mapping[str, JsonValue]:
    """编码 RunInputToolSchemaSummary。

    :param summary: 工具 schema 摘要。
    :returns: JSON 表达。
    :raises Exception: 不主动抛出异常。
    """

    return {"name": summary.name, "schema_hash": summary.schema_hash}


def _decode_run_input_tool_schema_summary(
    value: JsonValue,
) -> RunInputToolSchemaSummary:
    """解码 RunInputToolSchemaSummary。

    :param value: JSON 表达。
    :returns: RunInputToolSchemaSummary。
    :raises ValueError: 字段非法时抛出。
    """

    if not isinstance(value, dict):
        raise ValueError(_ERROR_INVALID_FIELDS)
    return RunInputToolSchemaSummary(
        name=_get_str(value, "name"),
        schema_hash=_get_str(value, "schema_hash"),
    )


def _encode_run_input_context_meta(
    meta: RunInputContextMeta,
) -> Mapping[str, JsonValue]:
    """编码 RunInputContextMeta。

    :param meta: 上下文摘要。
    :returns: JSON 表达。
    :raises Exception: 不主动抛出异常。
    """

    return {
        "message_count": meta.message_count,
        "role_sequence": list(meta.role_sequence),
        "total_char_size": meta.total_char_size,
        "total_token_estimate": meta.total_token_estimate,
        "memory_item_count": meta.memory_item_count,
        "current_user_run_id": meta.current_user_run_id,
    }


def _decode_run_input_context_meta(value: JsonValue) -> RunInputContextMeta:
    """解码 RunInputContextMeta。

    :param value: JSON 表达。
    :returns: RunInputContextMeta。
    :raises ValueError: 字段非法时抛出。
    """

    if not isinstance(value, dict):
        raise ValueError(_ERROR_INVALID_FIELDS)
    raw_seq = value.get("role_sequence")
    if not isinstance(raw_seq, list):
        raise ValueError(_ERROR_INVALID_FIELDS)
    role_sequence = tuple(_must_str(item) for item in raw_seq)
    return RunInputContextMeta(
        message_count=_get_int(value, "message_count"),
        role_sequence=role_sequence,
        total_char_size=_get_int(value, "total_char_size"),
        total_token_estimate=_get_int(value, "total_token_estimate"),
        memory_item_count=_get_int(value, "memory_item_count"),
        current_user_run_id=_get_str(value, "current_user_run_id"),
    )


def _encode_run_input_context_snapshot(
    data: RunInputContextSnapshotBuiltData,
) -> Mapping[str, JsonValue]:
    """编码 RunInputContextSnapshotBuiltData。

    :param data: Host-owned context snapshot fact data。
    :returns: JSON 字段映射。
    :raises Exception: 不主动抛出异常。
    """

    return {
        "iteration_id": data.iteration_id,
        "iteration_index": data.iteration_index,
        "attempt_index": data.attempt_index,
        "current_user_excerpt": data.current_user_excerpt,
        "current_user_content_hash": data.current_user_content_hash,
        "current_user_source_cursor": data.current_user_source_cursor,
        "message_summaries": [
            _encode_run_input_message_summary(item)
            for item in data.message_summaries
        ],
        "tool_schema_summaries": [
            _encode_run_input_tool_schema_summary(item)
            for item in data.tool_schema_summaries
        ],
        "context_meta": _encode_run_input_context_meta(data.context_meta),
        "raw_input_messages_json": data.raw_input_messages_json,
        "raw_tool_schemas_json": data.raw_tool_schemas_json,
        "raw_input_blob_id": data.raw_input_blob_id,
        "raw_tool_schemas_blob_id": data.raw_tool_schemas_blob_id,
    }


def _decode_run_input_context_snapshot(
    fields: Mapping[str, JsonValue],
) -> RunInputContextSnapshotBuiltData:
    """解码 RunInputContextSnapshotBuiltData。

    :param fields: JSON 字段映射。
    :returns: RunInputContextSnapshotBuiltData。
    :raises ValueError: 字段非法时抛出。
    """

    raw_messages = fields.get("message_summaries")
    if not isinstance(raw_messages, list):
        raise ValueError(_ERROR_INVALID_FIELDS)
    raw_schemas = fields.get("tool_schema_summaries")
    if not isinstance(raw_schemas, list):
        raise ValueError(_ERROR_INVALID_FIELDS)
    return RunInputContextSnapshotBuiltData(
        iteration_id=_get_str(fields, "iteration_id"),
        iteration_index=_get_int(fields, "iteration_index"),
        attempt_index=_get_int(fields, "attempt_index"),
        current_user_excerpt=_get_str(fields, "current_user_excerpt"),
        current_user_content_hash=_get_str(fields, "current_user_content_hash"),
        current_user_source_cursor=_get_optional_int(
            fields, "current_user_source_cursor"
        ),
        message_summaries=tuple(
            _decode_run_input_message_summary(item) for item in raw_messages
        ),
        tool_schema_summaries=tuple(
            _decode_run_input_tool_schema_summary(item) for item in raw_schemas
        ),
        context_meta=_decode_run_input_context_meta(fields.get("context_meta")),
        raw_input_messages_json=_get_str(fields, "raw_input_messages_json"),
        raw_tool_schemas_json=_get_str(fields, "raw_tool_schemas_json"),
        raw_input_blob_id=_get_str(fields, "raw_input_blob_id"),
        raw_tool_schemas_blob_id=_get_str(fields, "raw_tool_schemas_blob_id"),
    )


def _decode_finish_reason(
    fields: Mapping[str, JsonValue],
    key: str,
) -> FinishReason:
    """从字段映射解码 FinishReason。

    :param fields: JSON 字段映射。
    :param key: 键名。
    :returns: FinishReason。
    :raises ValueError: 值非法时抛出。
    """

    raw = _get_str(fields, key)
    try:
        return FinishReason(raw)
    except ValueError as exc:
        raise ValueError(_ERROR_INVALID_FINISH_REASON) from exc


def _get_str(fields: Mapping[str, JsonValue], key: str) -> str:
    """从字段中读取必填字符串。

    :param fields: JSON 字段映射。
    :param key: 键名。
    :returns: 字符串值。
    :raises ValueError: 字段缺失或类型不符时抛出。
    """

    value = fields.get(key)
    if not isinstance(value, str):
        raise ValueError(f"{_ERROR_INVALID_FIELDS}: missing string {key}")
    return value


def _must_str(value: JsonValue) -> str:
    """强制 JsonValue 为字符串。

    :param value: 任意 JSON 值。
    :returns: 字符串值。
    :raises ValueError: 类型不符时抛出。
    """

    if not isinstance(value, str):
        raise ValueError(_ERROR_INVALID_FIELDS)
    return value


def _get_optional_str(
    fields: Mapping[str, JsonValue],
    key: str,
) -> str | None:
    """从字段中读取可选字符串。

    :param fields: JSON 字段映射。
    :param key: 键名。
    :returns: 字符串值或 ``None``。
    :raises ValueError: 字段类型不符时抛出。
    """

    value = fields.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{_ERROR_INVALID_FIELDS}: invalid optional string {key}")
    return value


def _get_int(fields: Mapping[str, JsonValue], key: str) -> int:
    """从字段中读取必填整数。

    :param fields: JSON 字段映射。
    :param key: 键名。
    :returns: 整数值。
    :raises ValueError: 字段缺失或类型不符时抛出。
    """

    value = fields.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{_ERROR_INVALID_FIELDS}: missing int {key}")
    return value


def _get_optional_int(
    fields: Mapping[str, JsonValue],
    key: str,
) -> int | None:
    """从字段中读取可选整数。

    :param fields: JSON 字段映射。
    :param key: 键名。
    :returns: 整数值或 ``None``。
    :raises ValueError: 字段类型不符时抛出。
    """

    value = fields.get(key)
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{_ERROR_INVALID_FIELDS}: invalid optional int {key}")
    return value


def _get_bool(fields: Mapping[str, JsonValue], key: str) -> bool:
    """从字段中读取必填布尔。

    :param fields: JSON 字段映射。
    :param key: 键名。
    :returns: 布尔值。
    :raises ValueError: 字段缺失或类型不符时抛出。
    """

    value = fields.get(key)
    if not isinstance(value, bool):
        raise ValueError(f"{_ERROR_INVALID_FIELDS}: missing bool {key}")
    return value


def _get_float(fields: Mapping[str, JsonValue], key: str) -> float:
    """从字段中读取必填浮点。

    :param fields: JSON 字段映射。
    :param key: 键名。
    :returns: 浮点值。
    :raises ValueError: 字段缺失或类型不符时抛出。
    """

    value = fields.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{_ERROR_INVALID_FIELDS}: missing float {key}")
    return float(value)


def _get_mapping(
    fields: Mapping[str, JsonValue],
    key: str,
) -> Mapping[str, JsonValue]:
    """从字段中读取必填映射。

    :param fields: JSON 字段映射。
    :param key: 键名。
    :returns: 映射值。
    :raises ValueError: 字段缺失或类型不符时抛出。
    """

    value = fields.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"{_ERROR_INVALID_FIELDS}: missing mapping {key}")
    return value


_DATA_CLASS_BY_TYPE: Mapping[RunEventType, type] = {
    RunEventType.ITERATION_STARTED: IterationStartedData,
    RunEventType.RUNNER_CONTENT_DELTA: ContentDeltaData,
    RunEventType.RUNNER_REASONING_DELTA: ReasoningDeltaData,
    RunEventType.RUNNER_CONTENT_COMPLETED: ContentCompleteData,
    RunEventType.TOOL_CALL_REQUESTED: ToolCallRequestedData,
    RunEventType.TOOL_RESULT_ACCEPTED: ToolResultAcceptedData,
    RunEventType.TOOL_AWAITING: ToolAwaitingData,
    RunEventType.CONTEXT_COMPACTION_REQUESTED: ContextCompactionRequestedData,
    RunEventType.RUNNER_USAGE_RECORDED: RunnerUsageData,
    RunEventType.PROVIDER_PROTOCOL_ERROR: ProviderProtocolErrorData,
    RunEventType.RUNNER_DONE: RunnerDoneEngineData,
    RunEventType.FINAL_ANSWER: FinalAnswerData,
    RunEventType.RUN_SUSPENDED: RunSuspendedData,
    RunEventType.RUN_CANCELLED: RunCancelledData,
    # ``RUN_FAILED`` 既可能携带 Engine ``RunFailedData``，也可能携带 Host
    # ``HostRunFailedData``；这里登记 Engine 端，对 Host 端的检查通过
    # ``serialize_run_event_data`` 的多分支 isinstance 实现。
    RunEventType.RUN_FAILED: RunFailedData,
    RunEventType.USER_INPUT_ACCEPTED: UserInputAcceptedData,
    RunEventType.CONTEXT_OVERFLOW_OBSERVED: HostContextOverflowObservedData,
    RunEventType.CONTEXT_COMPACT_REQUESTED: HostContextCompactRequestedData,
    RunEventType.CONTEXT_COMPACT_COMPLETED: HostContextCompactCompletedData,
    RunEventType.CONTEXT_COMPACT_FAILED: HostContextCompactFailedData,
    RunEventType.CONTEXT_ATTEMPT_RETRYING: HostContextAttemptRetryData,
    RunEventType.RUN_INPUT_CONTEXT_SNAPSHOT_BUILT: (
        RunInputContextSnapshotBuiltData
    ),
}
"""RunEventType 到强类型 data 的封闭映射。"""


def is_known_run_event_type(event_type: RunEventType) -> bool:
    """判断 RunEventType 是否在 serializer registry 内。

    :param event_type: RunEvent 类型。
    :returns: 已注册返回 ``True``。
    :raises Exception: 不主动抛出异常。
    """

    return event_type in _DATA_CLASS_BY_TYPE


__all__ = [
    "CURRENT_SCHEMA_VERSION",
    "deserialize_run_event_data",
    "is_known_run_event_type",
    "serialize_run_event_data",
]
