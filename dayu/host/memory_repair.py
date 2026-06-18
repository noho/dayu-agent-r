"""Host conversation memory projection repair service。

本模块是 Host 内部 memory projection rebuild / catch-up 编排入口。它只组合
``ProjectionRunner``、``ConversationMemoryProjectionConsumer`` 与 durable
transaction runner；不追加 EventLog，不修改 Run / Attempt / wait / dispatch
治理状态，也不导入 UI / Service / Engine / Fins。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum

from dayu.host.durable.errors import HostDurableError
from dayu.host.durable.memory import (
    ConversationMemoryProjectionConsumer,
    reset_conversation_memory_projection,
)
from dayu.host.durable.transaction import HostTransactionRunner
from dayu.host.memory import (
    CONVERSATION_MEMORY_CONSUMER_ID,
    MemoryProjectionPolicy,
)
from dayu.host.projection import ProjectionConsumerId, ProjectionRunner
from dayu.runtime.log_levels import VERBOSE_LOG_LEVEL

_MIN_REPAIR_BATCH_SIZE = 1
_INITIAL_CURSOR = 0
_LOGGER = logging.getLogger(__name__)


class MemoryProjectionRepairStopReason(StrEnum):
    """memory projection repair 循环停止原因。"""

    IDLE = "idle"
    TARGET_REACHED = "target_reached"
    FAILURE = "failure"


@dataclass(frozen=True, slots=True)
class ConversationMemoryProjectionRepairResult:
    """conversation memory projection repair 汇总结果。

    :param consumer_id: repair 使用的 projection consumer id。
    :param reset_checkpoint: 本次是否先清空 memory projection 与 checkpoint。
    :param started_cursor: 本次 runner 开始 cursor。
    :param finished_cursor: 本次 runner 结束 cursor。
    :param events_scanned: 扫描的 EventLog row 数。
    :param events_matched: 命中 memory consumer filter 的 EventLog row 数。
    :param events_applied: consumer 返回 applied 的事件数。
    :param duplicates: consumer 返回 duplicate 的事件数。
    :param failures: runner 记录的 projection failure 数。
    :param batches_used: 本次已执行 projection batch 数。
    :param stop_reason: repair 循环停止原因。
    :param target_reached: 是否已覆盖调用方要求的 EventLog cursor。
    :param max_event_sequence: 本次目标 EventLog cursor。
    """

    consumer_id: ProjectionConsumerId
    reset_checkpoint: bool
    started_cursor: int
    finished_cursor: int
    events_scanned: int
    events_matched: int
    events_applied: int
    duplicates: int
    failures: int
    batches_used: int = 0
    stop_reason: MemoryProjectionRepairStopReason = MemoryProjectionRepairStopReason.IDLE
    target_reached: bool = False
    max_event_sequence: int | None = None


def rebuild_conversation_memory_projection(
    transaction_runner: HostTransactionRunner,
    *,
    policy: MemoryProjectionPolicy,
    batch_size: int,
    max_event_sequence: int | None,
    consumer_id: str = CONVERSATION_MEMORY_CONSUMER_ID,
) -> ConversationMemoryProjectionRepairResult:
    """从 committed EventLog 全量重建 conversation memory projection。

    rebuild 会先在一个短写事务内清空 memory projection-owned tables、目标
    consumer checkpoint 与 failure row，然后复用 ``ProjectionRunner`` 从
    EventLog cursor 0 重新 catch up。每个 EventLog row 的 snapshot 写入与
    checkpoint 推进仍由现有 runner 放在同一个 write transaction 内完成。

    :param transaction_runner: Host durable transaction runner。
    :param policy: 固定 memory projection policy。
    :param batch_size: 每批 projection page size，必须为正数。
    :param max_event_sequence: 必须覆盖的最大 EventLog sequence。
    :param consumer_id: memory projection consumer id。
    :returns: rebuild 汇总结果。
    :raises HostDurableError: batch size 非法、reset 或 projection runner 失败时抛出。
    """

    _validate_batch_size(batch_size)
    projection_consumer_id = ProjectionConsumerId(consumer_id)
    _LOGGER.log(
        VERBOSE_LOG_LEVEL,
        "host.memory_repair.rebuild.start consumer_id=%s batch_size=%s "
        "max_event_sequence=%s",
        projection_consumer_id.value,
        batch_size,
        max_event_sequence,
    )
    transaction_runner.run_write(
        lambda transaction: reset_conversation_memory_projection(
            transaction,
            consumer_id=projection_consumer_id.value,
        )
    )
    result = _run_memory_projection_until_stop(
        transaction_runner,
        policy=policy,
        batch_size=batch_size,
        consumer_id=projection_consumer_id,
        reset_checkpoint=True,
        max_event_sequence=max_event_sequence,
    )
    _log_memory_projection_result("rebuild", result)
    return result


def catch_up_conversation_memory_projection(
    transaction_runner: HostTransactionRunner,
    *,
    policy: MemoryProjectionPolicy,
    batch_size: int,
    consumer_id: str = CONVERSATION_MEMORY_CONSUMER_ID,
    max_event_sequence: int | None = None,
) -> ConversationMemoryProjectionRepairResult:
    """从当前 checkpoint 追平 conversation memory projection。

    本函数只复用 ``ProjectionRunner`` 读取 committed EventLog 并写
    projection-owned rows。consumer 抛出的异常由 runner 记录到现有
    projection failure row。required correctness path 调用本函数时会追到目标
    cursor、idle 或 failure；``batch_size`` 只表达 page size。

    :param transaction_runner: Host durable transaction runner。
    :param policy: 固定 memory projection policy。
    :param batch_size: 每批 projection page size，必须为正数。
    :param consumer_id: memory projection consumer id。
    :param max_event_sequence: 可选最大 EventLog sequence；下一条事件超过
        该值时停止，不推进 projection checkpoint。
    :returns: catch-up 汇总结果。
    :raises HostDurableError: batch size 非法或 projection runner 初始化失败时抛出。
    """

    _validate_batch_size(batch_size)
    projection_consumer_id = ProjectionConsumerId(consumer_id)
    _LOGGER.log(
        VERBOSE_LOG_LEVEL,
        (
            "host.memory_repair.catch_up.start consumer_id=%s "
            "batch_size=%s max_event_sequence=%s"
        ),
        projection_consumer_id.value,
        batch_size,
        max_event_sequence,
    )
    result = _run_memory_projection_until_stop(
        transaction_runner,
        policy=policy,
        batch_size=batch_size,
        consumer_id=projection_consumer_id,
        reset_checkpoint=False,
        max_event_sequence=max_event_sequence,
    )
    _log_memory_projection_result("catch_up", result)
    return result


def _run_memory_projection_until_stop(
    transaction_runner: HostTransactionRunner,
    *,
    policy: MemoryProjectionPolicy,
    batch_size: int,
    consumer_id: ProjectionConsumerId,
    reset_checkpoint: bool,
    max_event_sequence: int | None = None,
) -> ConversationMemoryProjectionRepairResult:
    """运行 memory projection runner 直到目标、idle 或 failure。

    :param transaction_runner: Host durable transaction runner。
    :param policy: 固定 memory projection policy。
    :param batch_size: 每批 projection page size。
    :param consumer_id: memory projection consumer id。
    :param reset_checkpoint: 本次是否为 reset 后 rebuild。
    :param max_event_sequence: 可选最大 EventLog sequence。
    :returns: repair 汇总结果。
    """

    runner = ProjectionRunner(
        transaction_runner,
        (
            ConversationMemoryProjectionConsumer(
                policy,
                consumer_id=consumer_id.value,
            ),
        ),
    )
    started_cursor: int | None = None
    finished_cursor = _INITIAL_CURSOR
    events_scanned = 0
    events_matched = 0
    events_applied = 0
    duplicates = 0
    failures = 0
    batches_used = 0
    stop_reason = MemoryProjectionRepairStopReason.IDLE
    while True:
        batch_result = runner.run_once(
            consumer_id,
            limit=batch_size,
            max_event_sequence=max_event_sequence,
        )
        batches_used += 1
        if started_cursor is None:
            started_cursor = batch_result.started_cursor
        finished_cursor = batch_result.finished_cursor
        events_scanned += batch_result.events_scanned
        events_matched += batch_result.events_matched
        events_applied += batch_result.events_applied
        duplicates += batch_result.duplicate_events
        failures += batch_result.failures
        if batch_result.failures > 0:
            stop_reason = MemoryProjectionRepairStopReason.FAILURE
            break
        if _target_reached(finished_cursor, max_event_sequence):
            stop_reason = MemoryProjectionRepairStopReason.TARGET_REACHED
            break
        if batch_result.events_scanned < batch_size:
            stop_reason = MemoryProjectionRepairStopReason.IDLE
            break
    if started_cursor is None:
        started_cursor = finished_cursor
    target_reached = _target_reached(finished_cursor, max_event_sequence)
    return ConversationMemoryProjectionRepairResult(
        consumer_id=consumer_id,
        reset_checkpoint=reset_checkpoint,
        started_cursor=started_cursor,
        finished_cursor=finished_cursor,
        events_scanned=events_scanned,
        events_matched=events_matched,
        events_applied=events_applied,
        duplicates=duplicates,
        failures=failures,
        batches_used=batches_used,
        stop_reason=stop_reason,
        target_reached=target_reached,
        max_event_sequence=max_event_sequence,
    )


def _log_memory_projection_result(
    operation: str, result: ConversationMemoryProjectionRepairResult
) -> None:
    """记录 memory projection repair / catch-up 汇总。

    :param operation: ``rebuild`` 或 ``catch_up`` 操作名称。
    :param result: projection runner 汇总结果。
    :returns: ``None``。
    """

    if result.failures > 0:
        _LOGGER.warning(
            (
                "host.memory_repair.%s.failed consumer_id=%s "
                "started_cursor=%s finished_cursor=%s events_scanned=%s "
                "events_matched=%s events_applied=%s duplicates=%s failures=%s "
                "batches_used=%s stop_reason=%s max_event_sequence=%s"
            ),
            operation,
            result.consumer_id.value,
            result.started_cursor,
            result.finished_cursor,
            result.events_scanned,
            result.events_matched,
            result.events_applied,
            result.duplicates,
            result.failures,
            result.batches_used,
            result.stop_reason.value,
            result.max_event_sequence,
        )
        return
    _LOGGER.log(
        VERBOSE_LOG_LEVEL,
        (
            "host.memory_repair.%s.committed consumer_id=%s "
            "started_cursor=%s finished_cursor=%s events_scanned=%s "
            "events_matched=%s events_applied=%s duplicates=%s "
            "batches_used=%s stop_reason=%s target_reached=%s "
            "max_event_sequence=%s"
        ),
        operation,
        result.consumer_id.value,
        result.started_cursor,
        result.finished_cursor,
        result.events_scanned,
        result.events_matched,
        result.events_applied,
        result.duplicates,
        result.batches_used,
        result.stop_reason.value,
        result.target_reached,
        result.max_event_sequence,
    )


def _validate_batch_size(batch_size: int) -> None:
    """校验 repair batch size。

    :param batch_size: 每次 projection 读取使用的 page size。
    :returns: ``None``。
    :raises HostDurableError: batch size 非正数时抛出。
    """

    if batch_size < _MIN_REPAIR_BATCH_SIZE:
        raise HostDurableError("conversation memory repair batch_size must be positive")


def _target_reached(
    finished_cursor: int,
    max_event_sequence: int | None,
) -> bool:
    """判断 projection checkpoint 是否已覆盖目标 cursor。

    :param finished_cursor: 当前 projection checkpoint cursor。
    :param max_event_sequence: 调用方要求覆盖的最大 EventLog sequence。
    :returns: 有目标且已覆盖目标时返回 ``True``。
    """

    return max_event_sequence is not None and finished_cursor >= max_event_sequence
