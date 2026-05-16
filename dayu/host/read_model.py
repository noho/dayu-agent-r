"""Host minimal RunResult / Session timeline projection。

本模块实现 Phase 8 内部 read model consumer 与 repair helper。它只从
committed EventLog 读取 canonical facts，经由注入的 ``ProjectionRunner`` 与
``HostTransactionRunner`` 写入 projection-owned tables；不调用 public command
facade，也不把 read model 作为 Host governance truth。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime

from dayu.contracts.json_value import JsonValue
from dayu.host._event_payload import optional_payload_text
from dayu.host.durable.codec import format_utc_timestamp
from dayu.host.durable.errors import HostDurableError
from dayu.host.durable.event_log import EventClass
from dayu.host.durable.read_model import (
    ReadModelWriteStatus,
    RunResultRow,
    SessionTimelineItemRow,
    insert_run_result_if_absent,
    insert_session_timeline_item_if_absent,
    reset_minimal_read_model_projection,
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

MINIMAL_READ_MODEL_CONSUMER_ID = ProjectionConsumerId("host.minimal-read-model")
"""minimal read model projection consumer id。"""

_EVENT_TYPE_USER_INPUT_ACCEPTED = "USER_INPUT_ACCEPTED"
_EVENT_TYPE_RUN_ACCEPTED = "RUN_ACCEPTED"
_EVENT_TYPE_RUN_QUEUED = "RUN_QUEUED"
_EVENT_TYPE_RUN_STARTED = "RUN_STARTED"
_EVENT_TYPE_RUN_WAITING = "RUN_WAITING"
_EVENT_TYPE_RUN_CANCELLING = "RUN_CANCELLING"
_EVENT_TYPE_RUN_SUCCEEDED = "RUN_SUCCEEDED"
_EVENT_TYPE_RUN_FAILED = "RUN_FAILED"
_EVENT_TYPE_RUN_CANCELLED = "RUN_CANCELLED"
_EVENT_TYPE_RUN_LOST = "RUN_LOST"
_ITEM_KIND_USER_INPUT = "user_input"
_ITEM_KIND_RUN_LIFECYCLE = "run_lifecycle"
_ITEM_KIND_RUN_TERMINAL = "run_terminal"
_PAYLOAD_FIELD_DISPLAY_TEXT = "display_text"
_PAYLOAD_FIELD_PAYLOAD_REF = "payload_ref"
_PAYLOAD_FIELD_PAYLOAD_DIGEST = "payload_digest"
_PAYLOAD_FIELD_RESULT_REF = "result_ref"
_PAYLOAD_FIELD_RESULT_DIGEST = "result_digest"
_PAYLOAD_FIELD_TERMINAL_SUMMARY_REF = "terminal_summary_ref"
_PAYLOAD_FIELD_TERMINAL_SUMMARY_DIGEST = "terminal_summary_digest"
_MIN_REPAIR_BATCH_SIZE = 1

_TERMINAL_STATUS_BY_EVENT_TYPE: Mapping[str, str] = {
    _EVENT_TYPE_RUN_SUCCEEDED: "succeeded",
    _EVENT_TYPE_RUN_FAILED: "failed",
    _EVENT_TYPE_RUN_CANCELLED: "cancelled",
    _EVENT_TYPE_RUN_LOST: "lost",
}
_TIMELINE_EVENT_TYPES: tuple[str, ...] = (
    _EVENT_TYPE_USER_INPUT_ACCEPTED,
    _EVENT_TYPE_RUN_ACCEPTED,
    _EVENT_TYPE_RUN_QUEUED,
    _EVENT_TYPE_RUN_STARTED,
    _EVENT_TYPE_RUN_WAITING,
    _EVENT_TYPE_RUN_CANCELLING,
    _EVENT_TYPE_RUN_SUCCEEDED,
    _EVENT_TYPE_RUN_FAILED,
    _EVENT_TYPE_RUN_CANCELLED,
    _EVENT_TYPE_RUN_LOST,
)


@dataclass(frozen=True, slots=True)
class ProjectionRepairResult:
    """minimal read model repair 结果。

    :param consumer_id: repair 使用的 projection consumer id。
    :param started_cursor: 本次 repair 开始 cursor。
    :param finished_cursor: 本次 repair 结束 cursor。
    :param events_scanned: replay 扫描的 EventLog row 数。
    :param events_applied: consumer 返回 applied 的事件数。
    :param duplicates: consumer 返回 duplicate 的事件数。
    :param failures: runner 记录的 failure 数。
    """

    consumer_id: ProjectionConsumerId
    started_cursor: int
    finished_cursor: int
    events_scanned: int
    events_applied: int
    duplicates: int
    failures: int


class MinimalReadModelProjectionConsumer:
    """minimal RunResult / Session timeline projection consumer。"""

    @property
    def consumer_id(self) -> ProjectionConsumerId:
        """返回稳定 consumer id。

        :returns: minimal read model consumer id。
        """

        return MINIMAL_READ_MODEL_CONSUMER_ID

    @property
    def event_filter(self) -> ProjectionEventFilter:
        """返回 consumer 关心的 canonical facts。

        :returns: EventLog class/type filter。
        """

        return ProjectionEventFilter(
            (
                ProjectionEventClassFilter(
                    event_class=EventClass.CANONICAL_FACT,
                    event_types=_TIMELINE_EVENT_TYPES,
                ),
            )
        )

    def apply_event(
        self, transaction: HostTransaction, event: ProjectionEventView
    ) -> ProjectionApplyResult:
        """投影单个 committed EventLog fact。

        :param transaction: 当前 Host durable transaction。
        :param event: typed projection event view。
        :returns: projection apply result。
        :raises HostDurableError: terminal identity 冲突、payload 类型非法或引用不成对时抛出。
        """

        if not self.event_filter.matches(event):
            return ProjectionApplyResult(ProjectionApplyStatus.SKIPPED)
        statuses = [_project_timeline_item(transaction, event)]
        if event.event_type in _TERMINAL_STATUS_BY_EVENT_TYPE:
            statuses.append(_project_run_result(transaction, event))
        if ReadModelWriteStatus.INSERTED in statuses:
            return ProjectionApplyResult(
                ProjectionApplyStatus.APPLIED,
                idempotency_key=event.event_id,
                detail_code=event.event_type,
            )
        return ProjectionApplyResult(
            ProjectionApplyStatus.DUPLICATE,
            idempotency_key=event.event_id,
            detail_code=event.event_type,
        )


def repair_minimal_read_models(
    transaction_runner: HostTransactionRunner,
    *,
    reset_checkpoint: bool,
    batch_size: int,
) -> ProjectionRepairResult:
    """重建或追平 minimal read model projection。

    ``reset_checkpoint=True`` 时先用一个短写事务清空 read model rows、
    consumer checkpoint 与 failure row；事务提交后再经由 ``ProjectionRunner``
    从 EventLog cursor 0 分批 replay。``reset_checkpoint=False`` 时从当前
    checkpoint 继续 catch up。

    :param transaction_runner: Host durable transaction runner，由宿主注入。
    :param reset_checkpoint: 是否先清空 read model 与 cursor。
    :param batch_size: 每次 runner catch-up 的扫描上限，必须为正数。
    :returns: repair 汇总结果。
    :raises HostDurableError: batch size 非法或 projection runner 初始化失败时抛出。
    """

    if batch_size < _MIN_REPAIR_BATCH_SIZE:
        raise HostDurableError("minimal read model repair batch_size must be positive")
    consumer = MinimalReadModelProjectionConsumer()
    consumer_id = consumer.consumer_id
    if reset_checkpoint:
        transaction_runner.run_write(
            lambda transaction: reset_minimal_read_model_projection(
                transaction, consumer_id=consumer_id.value
            )
        )
    runner = ProjectionRunner(transaction_runner, (consumer,))
    started_cursor: int | None = None
    finished_cursor = 0
    events_scanned = 0
    events_applied = 0
    duplicates = 0
    failures = 0
    while True:
        batch_result = runner.run_once(consumer_id, limit=batch_size)
        if started_cursor is None:
            started_cursor = batch_result.started_cursor
        finished_cursor = batch_result.finished_cursor
        events_scanned += batch_result.events_scanned
        events_applied += batch_result.events_applied
        duplicates += batch_result.duplicate_events
        failures += batch_result.failures
        if batch_result.failures > 0 or batch_result.events_scanned < batch_size:
            break
    if started_cursor is None:
        started_cursor = finished_cursor
    return ProjectionRepairResult(
        consumer_id=consumer_id,
        started_cursor=started_cursor,
        finished_cursor=finished_cursor,
        events_scanned=events_scanned,
        events_applied=events_applied,
        duplicates=duplicates,
        failures=failures,
    )


def _project_run_result(
    transaction: HostTransaction, event: ProjectionEventView
) -> ReadModelWriteStatus:
    """把 terminal canonical fact 投影为 RunResult。

    :param transaction: 当前 Host durable transaction。
    :param event: terminal projection event。
    :returns: read model 写入状态。
    :raises HostDurableError: event 缺少 Run id 或 payload 引用不成对时抛出。
    """

    if event.run_id is None:
        raise HostDurableError("terminal RunResult event requires run_id")
    now = _utc_now_text()
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
    return insert_run_result_if_absent(
        transaction,
        RunResultRow(
            run_id=event.run_id,
            session_id=event.session_id,
            terminal_status=_TERMINAL_STATUS_BY_EVENT_TYPE[event.event_type],
            terminal_event_id=event.event_id,
            terminal_event_sequence=event.event_sequence,
            result_ref=result_ref,
            result_digest=result_digest,
            summary_ref=summary_ref,
            summary_digest=summary_digest,
            projected_at=now,
            updated_at=now,
        ),
    )


def _project_timeline_item(
    transaction: HostTransaction, event: ProjectionEventView
) -> ReadModelWriteStatus:
    """把 canonical fact 投影为 Session timeline item。

    :param transaction: 当前 Host durable transaction。
    :param event: projection event。
    :returns: read model 写入状态。
    :raises HostDurableError: payload 引用不成对或 display_text 类型非法时抛出。
    """

    payload_ref, payload_digest = _payload_ref_pair(
        event.payload,
        ref_field_name=_PAYLOAD_FIELD_PAYLOAD_REF,
        digest_field_name=_PAYLOAD_FIELD_PAYLOAD_DIGEST,
        fallback_ref=event.payload_ref,
        fallback_digest=event.payload_digest,
    )
    return insert_session_timeline_item_if_absent(
        transaction,
        SessionTimelineItemRow(
            timeline_item_id=event.event_id,
            session_id=event.session_id,
            run_id=event.run_id,
            event_id=event.event_id,
            event_sequence=event.event_sequence,
            item_kind=_timeline_item_kind(event.event_type),
            event_type=event.event_type,
            display_text=_display_text(event),
            payload_ref=payload_ref,
            payload_digest=payload_digest,
            projected_at=_utc_now_text(),
        ),
    )


def _timeline_item_kind(event_type: str) -> str:
    """把 EventLog type 映射为 timeline item kind。

    :param event_type: EventLog event type。
    :returns: timeline item kind。
    """

    if event_type == _EVENT_TYPE_USER_INPUT_ACCEPTED:
        return _ITEM_KIND_USER_INPUT
    if event_type in _TERMINAL_STATUS_BY_EVENT_TYPE:
        return _ITEM_KIND_RUN_TERMINAL
    return _ITEM_KIND_RUN_LIFECYCLE


def _display_text(event: ProjectionEventView) -> str | None:
    """读取 timeline display_text。

    第一版只有 ``USER_INPUT_ACCEPTED`` 允许携带 typed ``display_text``；
    字段缺失时返回 ``None``，不得从 raw payload 拼接展示文本。

    :param event: projection event。
    :returns: 展示文本或 ``None``。
    :raises HostDurableError: 字段存在但类型非法时抛出。
    """

    if event.event_type != _EVENT_TYPE_USER_INPUT_ACCEPTED:
        return None
    return optional_payload_text(event.payload, field_name=_PAYLOAD_FIELD_DISPLAY_TEXT)


def _payload_ref_pair(
    payload: Mapping[str, JsonValue],
    *,
    ref_field_name: str,
    digest_field_name: str,
    fallback_ref: str | None,
    fallback_digest: str | None,
) -> tuple[str | None, str | None]:
    """读取 typed payload 引用 / digest，并校验成对出现。

    :param payload: typed payload 映射。
    :param ref_field_name: 引用字段名。
    :param digest_field_name: digest 字段名。
    :param fallback_ref: typed 字段缺失时使用的引用。
    :param fallback_digest: typed 字段缺失时使用的 digest。
    :returns: 引用 / digest pair。
    :raises HostDurableError: 引用或 digest 只有单边存在时抛出。
    """

    ref = optional_payload_text(payload, field_name=ref_field_name)
    digest = optional_payload_text(payload, field_name=digest_field_name)
    if ref is None and digest is None:
        ref = fallback_ref
        digest = fallback_digest
    if (ref is None) != (digest is None):
        raise HostDurableError(f"{ref_field_name} and {digest_field_name} must pair")
    return ref, digest


def _utc_now_text() -> str:
    """生成当前 UTC timestamp 文本。

    :returns: 固定格式 UTC timestamp 文本。
    """

    return format_utc_timestamp(datetime.now(UTC))


__all__ = [
    "MINIMAL_READ_MODEL_CONSUMER_ID",
    "MinimalReadModelProjectionConsumer",
    "ProjectionRepairResult",
    "repair_minimal_read_models",
]
