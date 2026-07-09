"""Host Outbox terminal delivery queue projection。

本模块实现 ``OutboxTerminalProjectionConsumer``。它只消费 committed
EventLog 的 terminal canonical facts，把可公开的 terminal notification 派生为
Outbox projection-owned queue item；不写 EventLog，不更新 Run / Attempt，也不
把 drain state 解释为 channel delivery success。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime

from dayu.contracts.json_value import JsonValue
from dayu.host._terminal_diagnostics import _append_terminal_diagnostic_suffix
from dayu.host._event_payload import optional_payload_text
from dayu.host.api import HostTerminalStatus
from dayu.host.lifecycle_events import (
    HOST_RUN_TERMINAL_EVENT_TYPES,
    HostRunEventType,
    event_type_values,
    host_terminal_status_for_terminal_event,
)
from dayu.host.durable.codec import (
    canonical_json_dumps,
    format_utc_timestamp,
    sha256_digest_json,
)
from dayu.host.durable.errors import HostDurableError
from dayu.host.durable.event_log import EventClass
from dayu.host.durable.outbox import (
    OutboxTerminalItemRow,
    OutboxTerminalItemWriteStatus,
    insert_outbox_terminal_item_if_absent,
)
from dayu.host.durable.transaction import HostTransaction, HostTransactionRunner
from dayu.host.projection import (
    ProjectionApplyResult,
    ProjectionApplyStatus,
    ProjectionConsumerId,
    ProjectionEventClassFilter,
    ProjectionEventFilter,
    ProjectionEventView,
    ProjectionRunner,
)

OUTBOX_TERMINAL_CONSUMER_ID = ProjectionConsumerId("host.outbox-terminal")
"""Outbox terminal projection consumer id。"""

DEFAULT_OUTBOX_TERMINAL_CATCHUP_BATCH_SIZE = 128
"""默认 Outbox terminal projection 单批 catch-up 扫描上限。"""

_EVENT_TYPE_RUN_FAILED = "RUN_FAILED"
_EVENT_TYPE_RUN_CANCELLED = "RUN_CANCELLED"
_DETAIL_CODE_RUN_LOST_SKIPPED = "run_lost_not_public_terminal_item"
_PAYLOAD_FIELD_RESULT_REF = "result_ref"
_PAYLOAD_FIELD_RESULT_DIGEST = "result_digest"
_PAYLOAD_FIELD_TERMINAL_SUMMARY_REF = "terminal_summary_ref"
_PAYLOAD_FIELD_TERMINAL_SUMMARY_DIGEST = "terminal_summary_digest"
_PAYLOAD_FIELD_FINAL_ANSWER = "final_answer"
_PAYLOAD_FIELD_CONTENT = "content"
_PAYLOAD_FIELD_FILTERED = "filtered"
_PAYLOAD_FIELD_DEGRADED = "degraded"
_PAYLOAD_FIELD_FINISH_REASON = "finish_reason"
_PAYLOAD_FIELD_TERMINAL_STATUS = "terminal_status"
_PAYLOAD_FIELD_MESSAGE = "message"
_PAYLOAD_FIELD_REASON = "reason"
_PAYLOAD_FIELD_PROVIDER_REQUEST_ID = "provider_request_id"
_PAYLOAD_FIELD_CLIENT_CORRELATION_ID = "client_correlation_id"
_IDENTITY_FIELD_TERMINAL_EVENT_ID = "terminal_event_id"
_IDENTITY_FIELD_RUN_ID = "run_id"
_IDENTITY_FIELD_RESULT_REF = "result_ref"
_IDENTITY_FIELD_RESULT_DIGEST = "result_digest"
_IDENTITY_FIELD_TERMINAL_SUMMARY_REF = "terminal_summary_ref"
_IDENTITY_FIELD_TERMINAL_SUMMARY_DIGEST = "terminal_summary_digest"
_OUTBOX_ITEM_ID_PREFIX = "outbox-terminal-"
_DIGEST_PREFIX = "sha256:"
_ITEM_STATE_PENDING = "pending"
_HOST_TERMINAL_EVENT_TYPE_VALUES = event_type_values(HOST_RUN_TERMINAL_EVENT_TYPES)


@dataclass(frozen=True, slots=True)
class OutboxTerminalItemIdentity:
    """Outbox terminal item identity。

    :param item_id: 稳定 Outbox item id。
    :param idempotency_key: 稳定 projection idempotency key。
    """

    item_id: str
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class OutboxTerminalCatchupResult:
    """Outbox terminal projection catch-up 汇总结果。

    :param consumer_id: Outbox terminal consumer id。
    :param started_cursor: 本次 catch-up 开始 cursor。
    :param finished_cursor: 本次 catch-up 结束 cursor。
    :param events_scanned: 扫描 EventLog row 数。
    :param events_applied: 新写 Outbox item 数。
    :param duplicates: 重复 terminal event 数。
    :param skipped: 跳过 terminal event 数。
    :param failures: projection runner 记录 failure 数。
    """

    consumer_id: ProjectionConsumerId
    started_cursor: int
    finished_cursor: int
    events_scanned: int
    events_applied: int
    duplicates: int
    skipped: int
    failures: int


class OutboxTerminalProjectionConsumer:
    """Outbox terminal delivery item projection consumer。"""

    @property
    def consumer_id(self) -> ProjectionConsumerId:
        """返回稳定 consumer id。

        :returns: ``host.outbox-terminal`` consumer id。
        """

        return OUTBOX_TERMINAL_CONSUMER_ID

    @property
    def event_filter(self) -> ProjectionEventFilter:
        """返回 Outbox 消费的 terminal canonical fact filter。

        :returns: EventLog class/type filter。
        """

        return ProjectionEventFilter(
            (
                ProjectionEventClassFilter(
                    event_class=EventClass.CANONICAL_FACT,
                    event_types=_HOST_TERMINAL_EVENT_TYPE_VALUES,
                ),
            )
        )

    def apply_event(
        self, transaction: HostTransaction, event: ProjectionEventView
    ) -> ProjectionApplyResult:
        """把单个 terminal canonical fact 投影为 Outbox item。

        :param transaction: 当前 Host durable transaction。
        :param event: typed projection event view。
        :returns: projection apply result。
        :raises HostDurableError: terminal event 缺少 Run id、payload 字段非法或引用不成对时抛出。
        """

        if not self.event_filter.matches(event):
            return ProjectionApplyResult(ProjectionApplyStatus.SKIPPED)
        if event.event_type == HostRunEventType.RUN_LOST.value:
            return ProjectionApplyResult(
                ProjectionApplyStatus.SKIPPED,
                idempotency_key=event.event_id,
                detail_code=_DETAIL_CODE_RUN_LOST_SKIPPED,
            )
        row = build_outbox_terminal_item_row(event)
        result = insert_outbox_terminal_item_if_absent(transaction, row)
        if result.status is OutboxTerminalItemWriteStatus.DUPLICATE:
            return ProjectionApplyResult(
                ProjectionApplyStatus.DUPLICATE,
                idempotency_key=result.row.idempotency_key,
                detail_code=event.event_type,
            )
        return ProjectionApplyResult(
            ProjectionApplyStatus.APPLIED,
            idempotency_key=result.row.idempotency_key,
            detail_code=event.event_type,
        )


def build_outbox_terminal_item_identity(
    *,
    terminal_event_id: str,
    run_id: str,
    result_ref: str | None,
    result_digest: str | None,
    terminal_summary_ref: str | None,
    terminal_summary_digest: str | None,
) -> OutboxTerminalItemIdentity:
    """构造稳定 Outbox terminal item identity。

    identity 只使用 terminal event identity、Run id 与结果 / summary refs，不使用
    final answer 文本作为主键，避免展示文本变化影响幂等语义。

    :param terminal_event_id: source terminal EventLog id。
    :param run_id: source Run id。
    :param result_ref: 可选结果 payload 引用。
    :param result_digest: 可选结果 payload digest。
    :param terminal_summary_ref: 可选 terminal summary 引用。
    :param terminal_summary_digest: 可选 terminal summary digest。
    :returns: 稳定 item id 与 idempotency key。
    :raises HostDurableError: 必填 identity 字段为空或引用不成对时抛出。
    """

    _require_non_empty_text(terminal_event_id, field_name="terminal_event_id")
    _require_non_empty_text(run_id, field_name="run_id")
    _require_ref_pair(result_ref, result_digest, field_name="result")
    _require_ref_pair(
        terminal_summary_ref,
        terminal_summary_digest,
        field_name="terminal_summary",
    )
    identity_json: JsonValue = {
        _IDENTITY_FIELD_TERMINAL_EVENT_ID: terminal_event_id,
        _IDENTITY_FIELD_RUN_ID: run_id,
        _IDENTITY_FIELD_RESULT_REF: result_ref,
        _IDENTITY_FIELD_RESULT_DIGEST: result_digest,
        _IDENTITY_FIELD_TERMINAL_SUMMARY_REF: terminal_summary_ref,
        _IDENTITY_FIELD_TERMINAL_SUMMARY_DIGEST: terminal_summary_digest,
    }
    idempotency_key = sha256_digest_json(identity_json)
    return OutboxTerminalItemIdentity(
        item_id=_OUTBOX_ITEM_ID_PREFIX + idempotency_key.removeprefix(_DIGEST_PREFIX),
        idempotency_key=idempotency_key,
    )


def build_outbox_terminal_item_row(
    event: ProjectionEventView,
) -> OutboxTerminalItemRow:
    """从 terminal projection event 构造 Outbox terminal item row。

    :param event: terminal projection event。
    :returns: 可写入 durable outbox table 的 item row。
    :raises HostDurableError: event 缺少 Run id、event type 不支持或 payload 字段非法时抛出。
    """

    if event.run_id is None:
        raise HostDurableError("outbox terminal event requires run_id")
    terminal_status = host_terminal_status_for_terminal_event(event.event_type)
    if terminal_status is None:
        raise HostDurableError("outbox terminal event type is unsupported")
    result_ref, result_digest = _payload_ref_pair(
        event.payload,
        ref_field_name=_PAYLOAD_FIELD_RESULT_REF,
        digest_field_name=_PAYLOAD_FIELD_RESULT_DIGEST,
        fallback_ref=event.payload_ref,
        fallback_digest=event.payload_digest,
    )
    summary_ref, summary_digest = _payload_ref_pair(
        event.payload,
        ref_field_name=_PAYLOAD_FIELD_TERMINAL_SUMMARY_REF,
        digest_field_name=_PAYLOAD_FIELD_TERMINAL_SUMMARY_DIGEST,
        fallback_ref=None,
        fallback_digest=None,
    )
    identity = build_outbox_terminal_item_identity(
        terminal_event_id=event.event_id,
        run_id=event.run_id,
        result_ref=result_ref,
        result_digest=result_digest,
        terminal_summary_ref=summary_ref,
        terminal_summary_digest=summary_digest,
    )
    now = _utc_now_text()
    return OutboxTerminalItemRow(
        item_id=identity.item_id,
        idempotency_key=identity.idempotency_key,
        terminal_event_id=event.event_id,
        event_sequence=event.event_sequence,
        session_id=event.session_id,
        run_id=event.run_id,
        terminal_status=terminal_status.value,
        dedupe_key=event.event_id,
        final_answer_json=_final_answer_json(event.payload, terminal_status),
        error_message=_error_message(event),
        cancel_reason=_cancel_reason(event),
        result_ref=result_ref,
        result_digest=result_digest,
        terminal_summary_ref=summary_ref,
        terminal_summary_digest=summary_digest,
        item_state=_ITEM_STATE_PENDING,
        projected_at=now,
        updated_at=now,
        drained_at=None,
        last_drain_request_id=None,
    )


def catch_up_outbox_terminal_projection(
    transaction_runner: HostTransactionRunner,
    *,
    batch_size: int = DEFAULT_OUTBOX_TERMINAL_CATCHUP_BATCH_SIZE,
    max_event_sequence: int | None = None,
) -> OutboxTerminalCatchupResult:
    """追平 Outbox terminal projection。

    :param transaction_runner: Host durable transaction runner。
    :param batch_size: 每批最多扫描 EventLog row 数，必须为正数。
    :param max_event_sequence: 可选最大 EventLog sequence。
    :returns: Outbox terminal catch-up 汇总结果。
    :raises HostDurableError: batch size 非法或 projection runner 初始化失败时抛出。
    """

    if batch_size <= 0:
        raise HostDurableError("outbox catch-up batch_size must be positive")
    consumer = OutboxTerminalProjectionConsumer()
    runner = ProjectionRunner(transaction_runner, (consumer,))
    started_cursor: int | None = None
    finished_cursor = 0
    events_scanned = 0
    events_applied = 0
    duplicates = 0
    skipped = 0
    failures = 0
    while True:
        batch_result = runner.run_once(
            consumer.consumer_id,
            limit=batch_size,
            max_event_sequence=max_event_sequence,
        )
        if started_cursor is None:
            started_cursor = batch_result.started_cursor
        finished_cursor = batch_result.finished_cursor
        events_scanned += batch_result.events_scanned
        events_applied += batch_result.events_applied
        duplicates += batch_result.duplicate_events
        skipped += batch_result.events_skipped
        failures += batch_result.failures
        if batch_result.failures > 0 or batch_result.events_scanned < batch_size:
            break
    if started_cursor is None:
        started_cursor = finished_cursor
    return OutboxTerminalCatchupResult(
        consumer_id=consumer.consumer_id,
        started_cursor=started_cursor,
        finished_cursor=finished_cursor,
        events_scanned=events_scanned,
        events_applied=events_applied,
        duplicates=duplicates,
        skipped=skipped,
        failures=failures,
    )


def _final_answer_json(
    payload: Mapping[str, JsonValue],
    terminal_status: HostTerminalStatus,
) -> str | None:
    """从 succeeded payload 构造可选 final answer JSON。

    :param payload: terminal EventLog payload。
    :param terminal_status: terminal 状态。
    :returns: canonical final answer JSON 文本；缺失时为 ``None``。
    :raises HostDurableError: final answer 相关字段类型非法时抛出。
    """

    if terminal_status is not HostTerminalStatus.SUCCEEDED:
        return None
    content = optional_payload_text(payload, field_name=_PAYLOAD_FIELD_FINAL_ANSWER)
    if content is None:
        return None
    final_answer_json: JsonValue = {
        _PAYLOAD_FIELD_CONTENT: content,
        _PAYLOAD_FIELD_FILTERED: _required_payload_bool(
            payload,
            field_name=_PAYLOAD_FIELD_FILTERED,
        ),
        _PAYLOAD_FIELD_DEGRADED: _required_payload_bool(
            payload,
            field_name=_PAYLOAD_FIELD_DEGRADED,
        ),
        _PAYLOAD_FIELD_FINISH_REASON: optional_payload_text(
            payload,
            field_name=_PAYLOAD_FIELD_FINISH_REASON,
        ),
        _PAYLOAD_FIELD_TERMINAL_STATUS: terminal_status.value,
    }
    return canonical_json_dumps(final_answer_json)


def _error_message(event: ProjectionEventView) -> str | None:
    """读取 failed terminal 展示消息。

    :param event: terminal projection event。
    :returns: 展示消息或 ``None``。
    :raises HostDurableError: 字段存在但不是非空文本时抛出。
    """

    if event.event_type != _EVENT_TYPE_RUN_FAILED:
        return None
    return _append_terminal_diagnostic_suffix(
        optional_payload_text(event.payload, field_name=_PAYLOAD_FIELD_MESSAGE),
        provider_request_id=optional_payload_text(
            event.payload,
            field_name=_PAYLOAD_FIELD_PROVIDER_REQUEST_ID,
        ),
        client_correlation_id=optional_payload_text(
            event.payload,
            field_name=_PAYLOAD_FIELD_CLIENT_CORRELATION_ID,
        ),
    )


def _cancel_reason(event: ProjectionEventView) -> str | None:
    """读取 cancelled terminal 原因。

    :param event: terminal projection event。
    :returns: 取消原因或 ``None``。
    :raises HostDurableError: 字段存在但不是非空文本时抛出。
    """

    if event.event_type != _EVENT_TYPE_RUN_CANCELLED:
        return None
    return optional_payload_text(event.payload, field_name=_PAYLOAD_FIELD_REASON)


def _payload_ref_pair(
    payload: Mapping[str, JsonValue],
    *,
    ref_field_name: str,
    digest_field_name: str,
    fallback_ref: str | None,
    fallback_digest: str | None,
) -> tuple[str | None, str | None]:
    """读取 payload 引用 / digest，并校验成对出现。

    :param payload: terminal EventLog payload。
    :param ref_field_name: ref 字段名。
    :param digest_field_name: digest 字段名。
    :param fallback_ref: typed 字段缺失时使用的 ref。
    :param fallback_digest: typed 字段缺失时使用的 digest。
    :returns: 引用 / digest pair。
    :raises HostDurableError: ref 与 digest 单边存在时抛出。
    """

    ref = optional_payload_text(payload, field_name=ref_field_name)
    digest = optional_payload_text(payload, field_name=digest_field_name)
    if ref is None and digest is None:
        ref = fallback_ref
        digest = fallback_digest
    _require_ref_pair(ref, digest, field_name=ref_field_name)
    return ref, digest


def _required_payload_bool(
    payload: Mapping[str, JsonValue],
    *,
    field_name: str,
) -> bool:
    """读取 payload 中的必填 bool 字段。

    :param payload: terminal EventLog payload。
    :param field_name: 字段名。
    :returns: bool 值。
    :raises HostDurableError: 字段缺失或不是 bool 时抛出。
    """

    value = payload.get(field_name)
    if not isinstance(value, bool):
        raise HostDurableError(f"payload field {field_name} must be bool")
    return value


def _require_ref_pair(
    ref: str | None,
    digest: str | None,
    *,
    field_name: str,
) -> None:
    """校验 ref / digest 必须成对。

    :param ref: 可选引用。
    :param digest: 可选 digest。
    :param field_name: 错误消息字段名。
    :returns: ``None``。
    :raises HostDurableError: 引用或 digest 只有单边存在时抛出。
    """

    _require_optional_non_empty_text(ref, field_name=f"{field_name}_ref")
    _require_optional_non_empty_text(digest, field_name=f"{field_name}_digest")
    if (ref is None) != (digest is None):
        raise HostDurableError(f"{field_name} ref and digest must pair")


def _require_non_empty_text(value: str, *, field_name: str) -> None:
    """校验必填文本非空。

    :param value: 待校验文本。
    :param field_name: 错误消息字段名。
    :returns: ``None``。
    :raises HostDurableError: 文本为空时抛出。
    """

    if value == "" or value.isspace():
        raise HostDurableError(f"{field_name} must be non-empty")


def _require_optional_non_empty_text(
    value: str | None,
    *,
    field_name: str,
) -> None:
    """校验 optional 文本存在时非空。

    :param value: 可选文本。
    :param field_name: 错误消息字段名。
    :returns: ``None``。
    :raises HostDurableError: 文本为空时抛出。
    """

    if value is not None and (value == "" or value.isspace()):
        raise HostDurableError(f"{field_name} must be non-empty")


def _utc_now_text() -> str:
    """生成当前 UTC timestamp 文本。

    :returns: 固定格式 UTC timestamp 文本。
    """

    return format_utc_timestamp(datetime.now(UTC))


__all__ = [
    "DEFAULT_OUTBOX_TERMINAL_CATCHUP_BATCH_SIZE",
    "OUTBOX_TERMINAL_CONSUMER_ID",
    "OutboxTerminalCatchupResult",
    "OutboxTerminalItemIdentity",
    "OutboxTerminalProjectionConsumer",
    "build_outbox_terminal_item_identity",
    "build_outbox_terminal_item_row",
    "catch_up_outbox_terminal_projection",
]
