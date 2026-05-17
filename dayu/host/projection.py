"""Host committed EventLog projection runner 与 typed consumer contract。

本模块定义 Host 内部 projection consumer 的强类型输入、filter、apply 结果
与 runner。Runner 只能使用注入的 ``HostTransactionRunner`` 读取已提交
EventLog 并推进 projection-local checkpoint；不得自建 SQLite connection，
不得调用 public command facade，也不得修改 Host governance truth。
"""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol

from dayu.contracts.json_value import JsonValue
from dayu.host._event_payload import payload_object
from dayu.host.durable.codec import format_utc_timestamp
from dayu.host.durable.errors import HostDurableError
from dayu.host.durable.event_log import EventClass, EventLogRow, read_events_after
from dayu.host.durable.projection import (
    advance_projection_checkpoint,
    clear_projection_failure,
    ensure_projection_checkpoint,
    write_projection_failure,
)
from dayu.host.durable.transaction import HostTransaction, HostTransactionRunner

PROJECTION_CONSUMER_ID_MAX_LENGTH = 128
"""projection consumer id 最大长度。"""

_CONSUMER_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]+$")
_MIN_BATCH_LIMIT = 1
_READ_ONE_EVENT_LIMIT = 1
_NO_EVENTS_CURSOR = 0
_EMPTY_ERROR_MESSAGE = "<empty projection error message>"
_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ProjectionConsumerId:
    """稳定 projection consumer id。

    :param value: consumer id 文本，只允许 ASCII 字母、数字、``_``、``.``、``:``、``-``。
    """

    value: str

    def __post_init__(self) -> None:
        """校验 consumer id 格式。

        :returns: ``None``。
        :raises HostDurableError: consumer id 为空、过长或包含非法字符时抛出。
        """

        _validate_consumer_id(self.value)


@dataclass(frozen=True, slots=True)
class ProjectionEventClassFilter:
    """单个 EventLog class 的 event type filter。

    :param event_class: 目标 EventLog class。
    :param event_types: ``None`` 表示消费该 class 下所有 event type；否则为非空 event type 元组。
    """

    event_class: EventClass
    event_types: tuple[str, ...] | None

    def __post_init__(self) -> None:
        """校验 class filter。

        :returns: ``None``。
        :raises HostDurableError: event class 或 event type 配置无效时抛出。
        """

        if not isinstance(self.event_class, EventClass):
            raise HostDurableError("projection event_class filter is invalid")
        if self.event_types is None:
            return
        if len(self.event_types) == 0:
            raise HostDurableError("projection event_types filter cannot be empty")
        seen: set[str] = set()
        for event_type in self.event_types:
            if not isinstance(event_type, str) or event_type.strip() == "":
                raise HostDurableError("projection event_type filter must be non-empty")
            if event_type in seen:
                raise HostDurableError("projection event_type filter is duplicated")
            seen.add(event_type)

    def matches(self, event_class: EventClass, event_type: str) -> bool:
        """判断 EventLog row 是否命中当前 class filter。

        :param event_class: EventLog row 的 class。
        :param event_type: EventLog row 的 type。
        :returns: 命中返回 ``True``，否则返回 ``False``。
        """

        if event_class != self.event_class:
            return False
        if self.event_types is None:
            return True
        return event_type in self.event_types


@dataclass(frozen=True, slots=True)
class ProjectionEventFilter:
    """projection consumer 的 EventLog filter。

    :param class_filters: 一个或多个 class filter；多个 filter 之间为 OR 关系。
    """

    class_filters: tuple[ProjectionEventClassFilter, ...]

    def __post_init__(self) -> None:
        """校验 projection event filter。

        :returns: ``None``。
        :raises HostDurableError: filter 为空或重复声明同一 EventClass 时抛出。
        """

        if len(self.class_filters) == 0:
            raise HostDurableError("projection event filter cannot be empty")
        seen: set[EventClass] = set()
        for class_filter in self.class_filters:
            if class_filter.event_class in seen:
                raise HostDurableError("projection event_class filter is duplicated")
            seen.add(class_filter.event_class)

    def matches(self, event: "ProjectionEventView") -> bool:
        """判断 typed projection event view 是否命中 filter。

        :param event: typed projection event view。
        :returns: 命中返回 ``True``，否则返回 ``False``。
        """

        return any(
            class_filter.matches(event.event_class, event.event_type)
            for class_filter in self.class_filters
        )


@dataclass(frozen=True, slots=True)
class ProjectionEventView:
    """传给 projection consumer 的 typed EventLog view。

    :param event_sequence: EventLog 全局 sequence。
    :param event_id: EventLog id。
    :param event_class: EventLog class。
    :param event_type: EventLog type。
    :param session_id: Session id。
    :param run_id: 可选 Run id。
    :param attempt_id: 可选 Attempt id。
    :param execution_id: 可选 execution id。
    :param occurred_at: 事件发生 UTC timestamp 文本。
    :param payload_ref: 可选 payload descriptor 引用。
    :param payload_digest: 可选 payload digest。
    :param payload: 已解析的 typed JSON mapping。
    """

    event_sequence: int
    event_id: str
    event_class: EventClass
    event_type: str
    session_id: str
    run_id: str | None
    attempt_id: str | None
    execution_id: str | None
    occurred_at: str
    payload_ref: str | None
    payload_digest: str | None
    payload: Mapping[str, JsonValue]


class ProjectionApplyStatus(StrEnum):
    """projection consumer 处理单个 event 后的封闭结果状态。"""

    APPLIED = "applied"
    SKIPPED = "skipped"
    DUPLICATE = "duplicate"


@dataclass(frozen=True, slots=True)
class ProjectionApplyResult:
    """projection consumer 处理单个 event 的结果。

    :param status: 处理结果状态。
    :param idempotency_key: 可选幂等 key，用于 consumer-local 诊断。
    :param detail_code: 可选结构化明细码。
    """

    status: ProjectionApplyStatus
    idempotency_key: str | None = None
    detail_code: str | None = None

    def __post_init__(self) -> None:
        """校验 apply result。

        :returns: ``None``。
        :raises HostDurableError: 状态或可选文本字段无效时抛出。
        """

        if not isinstance(self.status, ProjectionApplyStatus):
            raise HostDurableError("projection apply status is invalid")
        _validate_optional_text(self.idempotency_key, field_name="idempotency_key")
        _validate_optional_text(self.detail_code, field_name="detail_code")


class ProjectionConsumer(Protocol):
    """projection consumer 协议。

    consumer 可以在传入的 Host transaction 内写自己的 projection-owned table，
    但不得调用 command transition、admission、recovery、Run / Attempt mutator。
    """

    @property
    def consumer_id(self) -> ProjectionConsumerId:
        """返回稳定 consumer id。

        :returns: 稳定 consumer id。
        """

        ...

    @property
    def event_filter(self) -> ProjectionEventFilter:
        """返回 consumer 的 EventLog filter。

        :returns: EventLog filter。
        """

        ...

    def apply_event(
        self, transaction: HostTransaction, event: ProjectionEventView
    ) -> ProjectionApplyResult:
        """在调用方 transaction 内处理单个 projection event。

        :param transaction: 当前 Host durable transaction。
        :param event: typed projection event view。
        :returns: apply result。
        :raises Exception: consumer 处理失败时抛出，runner 会 rollback 并记录 failure。
        """

        ...


class ProjectionCatchupPort(Protocol):
    """committed EventLog projection catch-up 通用端口。

    该端口只允许连接 projection-local catch-up；实现不得参与调用方 command
    transaction，也不得修改 Run / Attempt / wait / dispatch 等治理状态。
    """

    def catch_up_projection(self) -> None:
        """追平已提交 EventLog 的 projection。

        :returns: ``None``。
        :raises Exception: 具体实现可在 catch-up 失败时抛出自身错误。
        """

        ...


class NoopProjectionCatchupPort:
    """默认 no-op projection catch-up port。"""

    def catch_up_projection(self) -> None:
        """忽略 projection catch-up。

        :returns: ``None``。
        """


def catch_up_projection_best_effort(
    projection_catchup_port: ProjectionCatchupPort | None,
) -> None:
    """best-effort 触发 projection catch-up 并记录失败。

    :param projection_catchup_port: 可选 projection catch-up 端口。
    :returns: ``None``。
    """

    if projection_catchup_port is None:
        return
    try:
        projection_catchup_port.catch_up_projection()
    except Exception:
        _LOGGER.exception("projection catch-up failed; continuing")


@dataclass(frozen=True, slots=True)
class ProjectionRunResult:
    """ProjectionRunner 单 consumer 单次 catch-up 结果。

    :param consumer_id: 本次运行的 consumer id。
    :param started_cursor: 本次运行开始时的 checkpoint cursor。
    :param finished_cursor: 本次运行结束时的 checkpoint cursor。
    :param events_scanned: 本次扫描的 EventLog row 数。
    :param events_matched: 命中 consumer filter 的 EventLog row 数。
    :param events_applied: consumer 返回 ``APPLIED`` 的数量。
    :param events_skipped: consumer 返回 ``SKIPPED`` 的数量。
    :param duplicate_events: consumer 返回 ``DUPLICATE`` 的数量。
    :param failures: 本次记录的 failure 数量。
    """

    consumer_id: ProjectionConsumerId
    started_cursor: int
    finished_cursor: int
    events_scanned: int
    events_matched: int
    events_applied: int
    events_skipped: int
    duplicate_events: int
    failures: int


@dataclass(frozen=True, slots=True)
class _ProjectionStepResult:
    """单个 EventLog row projection step 的内部结果。"""

    started_cursor: int
    finished_cursor: int
    scanned: bool
    matched: bool
    apply_status: ProjectionApplyStatus | None


class _ProjectionApplyFailed(Exception):
    """consumer apply 失败后的内部控制流异常。"""

    event: ProjectionEventView
    original_exception: BaseException

    def __init__(
        self, event: ProjectionEventView, original_exception: BaseException
    ) -> None:
        """初始化内部 apply failure。

        :param event: 失败的 typed projection event view。
        :param original_exception: consumer 抛出的原始异常。
        :returns: ``None``。
        """

        self.event = event
        self.original_exception = original_exception
        super().__init__(str(original_exception))


class _ProjectionEventViewFailed(Exception):
    """EventLog row 无法构造成 typed projection view 的内部控制流异常。"""

    event_row: EventLogRow
    original_exception: HostDurableError

    def __init__(
        self, event_row: EventLogRow, original_exception: HostDurableError
    ) -> None:
        """初始化内部 projection view failure。

        :param event_row: 失败的 EventLog durable row。
        :param original_exception: 构造 typed projection view 时抛出的异常。
        :returns: ``None``。
        """

        self.event_row = event_row
        self.original_exception = original_exception
        super().__init__(str(original_exception))


class ProjectionRunner:
    """基于 committed EventLog 的 projection runner。

    :param transaction_runner: 注入的 Host durable transaction runner。
    :param consumers: 本 runner 管理的 concrete consumers。
    """

    def __init__(
        self,
        transaction_runner: HostTransactionRunner,
        consumers: tuple[ProjectionConsumer, ...],
    ) -> None:
        """初始化 projection runner。

        :param transaction_runner: 注入的 Host durable transaction runner。
        :param consumers: concrete projection consumers。
        :returns: ``None``。
        :raises HostDurableError: consumer 集合为空或 consumer id 重复时抛出。
        """

        if len(consumers) == 0:
            raise HostDurableError("projection runner requires at least one consumer")
        consumer_by_id: dict[str, ProjectionConsumer] = {}
        for consumer in consumers:
            consumer_id = consumer.consumer_id.value
            if consumer_id in consumer_by_id:
                raise HostDurableError("projection consumer_id is duplicated")
            consumer_by_id[consumer_id] = consumer
        self._transaction_runner = transaction_runner
        self._consumer_by_id = consumer_by_id

    def run_once(
        self, consumer_id: ProjectionConsumerId, *, limit: int
    ) -> ProjectionRunResult:
        """按 checkpoint 为单个 consumer catch up 一批 EventLog rows。

        每个 EventLog row 都在独立 ``HostTransactionRunner.run_write()``
        transaction 内完成 consumer write 与 checkpoint advance。consumer
        失败时，该 row 的 consumer write 会 rollback，runner 随后只写
        projection-local failure row，并停止当前批次。EventLog payload 无法
        构造成 typed projection view 时同样记录 projection-local failure，
        不推进 checkpoint。

        :param consumer_id: 要运行的 consumer id。
        :param limit: 本次最多扫描的 EventLog row 数，必须为正数。
        :returns: 本次运行结果。
        :raises HostDurableError: consumer 不存在或 limit 无效时抛出。
        """

        if limit < _MIN_BATCH_LIMIT:
            raise HostDurableError("projection runner limit must be positive")
        consumer = self._consumer_for_id(consumer_id)
        started_cursor = self._ensure_checkpoint(consumer_id)
        finished_cursor = started_cursor
        events_scanned = 0
        events_matched = 0
        events_applied = 0
        events_skipped = 0
        duplicate_events = 0
        failures = 0
        for _index in range(limit):
            try:
                step = self._transaction_runner.run_write(
                    lambda transaction: self._process_next_event(
                        transaction, consumer
                    )
                )
            except _ProjectionApplyFailed as exc:
                self._record_failure(
                    consumer_id,
                    event_sequence=exc.event.event_sequence,
                    event_id=exc.event.event_id,
                    exception=exc.original_exception,
                )
                failures += 1
                break
            except _ProjectionEventViewFailed as exc:
                self._record_failure(
                    consumer_id,
                    event_sequence=exc.event_row.event_sequence,
                    event_id=exc.event_row.event_id,
                    exception=exc.original_exception,
                )
                failures += 1
                break
            finished_cursor = step.finished_cursor
            if not step.scanned:
                break
            events_scanned += 1
            if not step.matched:
                continue
            events_matched += 1
            if step.apply_status is ProjectionApplyStatus.APPLIED:
                events_applied += 1
            elif step.apply_status is ProjectionApplyStatus.SKIPPED:
                events_skipped += 1
            elif step.apply_status is ProjectionApplyStatus.DUPLICATE:
                duplicate_events += 1
        return ProjectionRunResult(
            consumer_id=consumer_id,
            started_cursor=started_cursor,
            finished_cursor=finished_cursor,
            events_scanned=events_scanned,
            events_matched=events_matched,
            events_applied=events_applied,
            events_skipped=events_skipped,
            duplicate_events=duplicate_events,
            failures=failures,
        )

    def run_all_once(self, *, limit_per_consumer: int) -> tuple[ProjectionRunResult, ...]:
        """按 consumer id 顺序为所有 consumers 各运行一次 catch-up。

        :param limit_per_consumer: 每个 consumer 最多扫描的 EventLog row 数，必须为正数。
        :returns: 每个 consumer 的运行结果元组。
        :raises HostDurableError: limit 无效时抛出。
        """

        if limit_per_consumer < _MIN_BATCH_LIMIT:
            raise HostDurableError("projection runner limit must be positive")
        return tuple(
            self.run_once(ProjectionConsumerId(consumer_id), limit=limit_per_consumer)
            for consumer_id in sorted(self._consumer_by_id)
        )

    def _consumer_for_id(self, consumer_id: ProjectionConsumerId) -> ProjectionConsumer:
        """按 consumer id 读取 consumer。

        :param consumer_id: 稳定 consumer id。
        :returns: 对应 consumer。
        :raises HostDurableError: consumer 不存在时抛出。
        """

        consumer = self._consumer_by_id.get(consumer_id.value)
        if consumer is None:
            raise HostDurableError("projection consumer is not registered")
        return consumer

    def _ensure_checkpoint(self, consumer_id: ProjectionConsumerId) -> int:
        """确保 checkpoint row 存在并返回当前 cursor。

        :param consumer_id: 稳定 consumer id。
        :returns: 当前 checkpoint cursor。
        :raises HostDurableError: checkpoint 初始化失败时抛出。
        """

        checkpoint = self._transaction_runner.run_write(
            lambda transaction: ensure_projection_checkpoint(
                transaction, consumer_id.value, now=_utc_now_text()
            )
        )
        return checkpoint.checkpoint_event_sequence

    def _process_next_event(
        self, transaction: HostTransaction, consumer: ProjectionConsumer
    ) -> _ProjectionStepResult:
        """在单个 write transaction 内处理 checkpoint 后的下一条 EventLog。

        :param transaction: 当前 Host durable transaction。
        :param consumer: concrete projection consumer。
        :returns: 单步处理结果。
        :raises _ProjectionApplyFailed: consumer apply 失败时抛出。
        :raises _ProjectionEventViewFailed: EventLog payload 无法构造 view 时抛出。
        :raises HostDurableError: checkpoint 或 EventLog 读取失败时抛出。
        """

        consumer_id = consumer.consumer_id.value
        checkpoint = ensure_projection_checkpoint(
            transaction, consumer_id, now=_utc_now_text()
        )
        rows = read_events_after(
            transaction,
            checkpoint.checkpoint_event_sequence,
            limit=_READ_ONE_EVENT_LIMIT,
        )
        if len(rows) == 0:
            return _ProjectionStepResult(
                started_cursor=checkpoint.checkpoint_event_sequence,
                finished_cursor=checkpoint.checkpoint_event_sequence,
                scanned=False,
                matched=False,
                apply_status=None,
            )
        row = rows[0]
        try:
            event = projection_event_view_from_row(row)
        except HostDurableError as exc:
            raise _ProjectionEventViewFailed(row, exc) from exc
        apply_status: ProjectionApplyStatus | None = None
        if consumer.event_filter.matches(event):
            try:
                apply_result = consumer.apply_event(transaction, event)
            except Exception as exc:
                raise _ProjectionApplyFailed(event, exc) from exc
            apply_status = apply_result.status
        now = _utc_now_text()
        advance_projection_checkpoint(
            transaction,
            consumer_id,
            event_sequence=event.event_sequence,
            event_id=event.event_id,
            now=now,
        )
        clear_projection_failure(transaction, consumer_id)
        return _ProjectionStepResult(
            started_cursor=checkpoint.checkpoint_event_sequence,
            finished_cursor=event.event_sequence,
            scanned=True,
            matched=apply_status is not None,
            apply_status=apply_status,
        )

    def _record_failure(
        self,
        consumer_id: ProjectionConsumerId,
        *,
        event_sequence: int,
        event_id: str,
        exception: BaseException,
    ) -> None:
        """记录 projection-local failure row。

        :param consumer_id: 稳定 consumer id。
        :param event_sequence: 失败 EventLog sequence。
        :param event_id: 失败 EventLog id。
        :param exception: consumer 或 view 构造抛出的异常。
        :returns: ``None``。
        :raises HostDurableError: failure row 写入失败时抛出。
        """

        error_message = str(exception)
        if error_message == "":
            error_message = _EMPTY_ERROR_MESSAGE
        error_code = exception.__class__.__name__
        self._transaction_runner.run_write(
            lambda transaction: write_projection_failure(
                transaction,
                consumer_id.value,
                failed_event_sequence=event_sequence,
                failed_event_id=event_id,
                error_code=error_code,
                error_message=error_message,
                now=_utc_now_text(),
            )
        )


def projection_event_view_from_row(row: EventLogRow) -> ProjectionEventView:
    """把 EventLogRow 转换为 typed ProjectionEventView。

    :param row: EventLog durable row。
    :returns: typed projection event view。
    :raises HostDurableError: EventLog payload JSON 非法或不是 JSON mapping 时抛出。
    """

    return ProjectionEventView(
        event_sequence=row.event_sequence,
        event_id=row.event_id,
        event_class=row.event_class,
        event_type=row.event_type,
        session_id=row.session_id,
        run_id=row.run_id,
        attempt_id=row.attempt_id,
        execution_id=row.execution_id,
        occurred_at=row.occurred_at,
        payload_ref=row.payload_ref,
        payload_digest=row.payload_digest,
        payload=payload_object(row),
    )


def _validate_consumer_id(value: str) -> None:
    """校验 projection consumer id。

    :param value: consumer id 文本。
    :returns: ``None``。
    :raises HostDurableError: consumer id 为空、过长或包含非法字符时抛出。
    """

    if not isinstance(value, str) or value.strip() == "":
        raise HostDurableError("projection consumer_id must be non-empty")
    if len(value) > PROJECTION_CONSUMER_ID_MAX_LENGTH:
        raise HostDurableError("projection consumer_id is too long")
    if _CONSUMER_ID_PATTERN.fullmatch(value) is None:
        raise HostDurableError("projection consumer_id contains invalid characters")


def _validate_optional_text(value: str | None, *, field_name: str) -> None:
    """校验 optional 文本字段。

    :param value: 待校验文本或 ``None``。
    :param field_name: 错误消息字段名。
    :returns: ``None``。
    :raises HostDurableError: 文本为空时抛出。
    """

    if value is not None and value.strip() == "":
        raise HostDurableError(f"projection {field_name} must be non-empty")


def _utc_now_text() -> str:
    """生成当前 UTC timestamp 文本。

    :returns: 固定格式 UTC timestamp 文本。
    """

    return format_utc_timestamp(datetime.now(UTC))
