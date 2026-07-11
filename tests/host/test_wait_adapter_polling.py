"""Host wait poll adapter / poller 测试。"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

import pytest

from dayu.contracts.tool_result import ToolResultSuccess
from dayu.host import (
    CancelMode,
    CancelRunRequest,
    ResolveWaitCompletedOutcome,
    ResolveWaitLostOutcome,
    ResolveWaitRequest,
    RunSnapshot,
    RunStatus,
    WaitProviderStatusRef,
    cancel_run,
    get_run,
    resolve_wait,
)
from dayu.host.command import HostCommandHandle, create_host_command_handle
from dayu.host.durable.codec import format_utc_timestamp, sha256_digest_json
from dayu.host.durable.schema import TABLE_HOST_WAIT_RECORDS
from dayu.host.durable.state import WaitPollLastOutcome, WaitRecordRow, WaitRecordStatus
from dayu.host.durable.transaction import (
    HostTransaction,
    HostTransactionOperation,
    HostTransactionRunner,
)
from dayu.host.wait_adapter import (
    WaitExternalJobLifecycleAction,
    WaitExternalJobLifecycleApplied,
    WaitExternalJobLifecycleNoop,
    WaitExternalJobLifecycleResult,
    WaitExternalJobLifecycleUnsupported,
    WaitPollAdapter,
    WaitPollAdapterRegistration,
    WaitPollAdapterRegistry,
    WaitPollLifecycleGate,
    WaitPollLost,
    WaitPollNotReady,
    WaitPollReady,
    WaitPollResult,
    WaitPoller,
    WaitResolvePort,
)
from dayu.runtime.log_levels import VERBOSE_LOG_LEVEL
from tests.host.test_resolve_wait_command import (
    _context,
    _options,
    _read_wait,
    _seed_waiting_run,
)

_POLL_NOW = datetime(2026, 5, 16, 2, 0, 0, tzinfo=UTC)


class _FixedClock:
    """测试用固定 UTC 时钟。"""

    def now(self) -> datetime:
        """返回固定 UTC 时间。

        :returns: 固定时间。
        """

        return _POLL_NOW


class _PublicCommandResolver:
    """调用 public ``resolve_wait`` 的 resolver。"""

    def __init__(self, host: HostCommandHandle) -> None:
        """初始化 resolver。

        :param host: Host command handle。
        :returns: ``None``。
        """

        self._host = host

    def resolve_wait(self, wait_id: str, request: ResolveWaitRequest) -> RunSnapshot:
        """接收 poller 结果。

        :param wait_id: wait id。
        :param request: resolve wait request。
        :returns: Run snapshot。
        """

        return resolve_wait(self._host, wait_id, request)


class _FailingResolveResolver:
    """测试用始终抛出 resolve_wait 异常的 resolver。"""

    def __init__(self) -> None:
        """初始化调用记录。

        :returns: ``None``。
        """

        self.calls: list[str] = []
        self.idempotency_keys: list[str] = []

    def resolve_wait(self, wait_id: str, request: ResolveWaitRequest) -> RunSnapshot:
        """记录调用并模拟 resolve_wait 失败。

        :param wait_id: wait id。
        :param request: resolve wait request。
        :returns: 永不返回。
        :raises RuntimeError: 始终抛出，用于验证 poller 异常隔离。
        """

        self.calls.append(wait_id)
        self.idempotency_keys.append(request.idempotency_key)
        raise RuntimeError("resolve wait failed")


class _NoResolveResolver:
    """测试用禁止调用 resolve_wait 的 resolver。"""

    def __init__(self) -> None:
        """初始化调用记录。

        :returns: ``None``。
        """

        self.calls: list[str] = []

    def resolve_wait(self, wait_id: str, request: ResolveWaitRequest) -> RunSnapshot:
        """记录错误调用并中断测试。

        :param wait_id: wait id。
        :param request: resolve wait request。
        :returns: 永不返回。
        :raises AssertionError: 任何调用都表示 cancelled lifecycle path 错误。
        """

        del request
        self.calls.append(wait_id)
        raise AssertionError(f"unexpected resolve_wait for {wait_id}")


class _RecordingPublicCommandResolver:
    """记录 idempotency key 后调用 public ``resolve_wait`` 的 resolver。"""

    def __init__(self, host: HostCommandHandle) -> None:
        """初始化 resolver。

        :param host: Host command handle。
        :returns: ``None``。
        """

        self._host = host
        self.idempotency_keys: list[str] = []

    def resolve_wait(self, wait_id: str, request: ResolveWaitRequest) -> RunSnapshot:
        """记录调用并转发给 public resolve_wait。

        :param wait_id: wait id。
        :param request: resolve wait request。
        :returns: Run snapshot。
        """

        self.idempotency_keys.append(request.idempotency_key)
        return resolve_wait(self._host, wait_id, request)


class _SequenceAdapter:
    """按预置序列返回 poll 结果的 adapter。"""

    def __init__(self, results: tuple[WaitPollResult, ...]) -> None:
        """初始化 adapter。

        :param results: poll 结果序列。
        :returns: ``None``。
        """

        self._results = results
        self.poll_count = 0
        self.abandoned: list[str] = []
        self.lifecycle_results: list[WaitExternalJobLifecycleResult] = []

    def poll_wait(self, wait_record: WaitRecordRow) -> WaitPollResult:
        """返回下一项 poll 结果。

        :param wait_record: wait record。
        :returns: poll 结果。
        """

        result = self._results[self.poll_count]
        self.poll_count += 1
        return result

    def abandon_wait(
        self, wait_record: WaitRecordRow
    ) -> WaitExternalJobLifecycleResult:
        """记录被放弃 wait id。

        :param wait_record: wait record。
        :returns: applied lifecycle result。
        """

        self.abandoned.append(wait_record.wait_id)
        lifecycle_result = WaitExternalJobLifecycleApplied(
            action=WaitExternalJobLifecycleAction.ABANDON,
            message="test_abandoned",
        )
        self.lifecycle_results.append(lifecycle_result)
        return lifecycle_result


class _AbandonValueErrorThenNotReadyAdapter:
    """先在 abandon 抛 ValueError，再对后续 poll 返回 not-ready 的 adapter。"""

    def __init__(self) -> None:
        """初始化调用记录。

        :returns: ``None``。
        """

        self.abandoned: list[str] = []
        self.polled: list[str] = []

    def poll_wait(self, wait_record: WaitRecordRow) -> WaitPollResult:
        """记录 poll wait 并返回 not-ready。

        :param wait_record: wait record。
        :returns: not-ready poll 结果。
        """

        self.polled.append(wait_record.wait_id)
        return WaitPollNotReady()

    def abandon_wait(
        self, wait_record: WaitRecordRow
    ) -> WaitExternalJobLifecycleResult:
        """记录 abandon wait 并抛出普通异常。

        :param wait_record: wait record。
        :returns: 不返回；始终抛出 ``ValueError``。
        :raises ValueError: 始终抛出，用于验证普通异常隔离。
        """

        self.abandoned.append(wait_record.wait_id)
        raise ValueError("adapter abandon failed")


class _FailingPollAdapter:
    """poll_wait 始终抛出异常的测试 adapter。"""

    def __init__(self) -> None:
        """初始化调用记录。

        :returns: ``None``。
        """

        self.polled: list[str] = []
        self.abandoned: list[str] = []

    def poll_wait(self, wait_record: WaitRecordRow) -> WaitPollResult:
        """记录 poll wait 并抛出异常。

        :param wait_record: wait record。
        :returns: 不返回。
        :raises RuntimeError: 始终抛出测试异常。
        """

        self.polled.append(wait_record.wait_id)
        raise RuntimeError("provider transient failure")

    def abandon_wait(
        self, wait_record: WaitRecordRow
    ) -> WaitExternalJobLifecycleResult:
        """记录异常的 abandon 调用。

        :param wait_record: wait record。
        :returns: 不返回。
        :raises AssertionError: 本测试 adapter 不应进入 abandon path。
        """

        self.abandoned.append(wait_record.wait_id)
        raise AssertionError(f"unexpected abandon {wait_record.wait_id}")


class _StaticLifecycleAdapter:
    """返回固定 cancelled wait lifecycle result 的 adapter。"""

    def __init__(self, lifecycle_result: WaitExternalJobLifecycleResult) -> None:
        """初始化 adapter。

        :param lifecycle_result: abandon_wait 返回的 lifecycle result。
        :returns: ``None``。
        """

        self._lifecycle_result = lifecycle_result
        self.abandoned: list[str] = []

    def poll_wait(self, wait_record: WaitRecordRow) -> WaitPollResult:
        """本 adapter 不应处理 waiting poll。

        :param wait_record: wait record。
        :returns: 永不返回。
        :raises AssertionError: 被错误调用时抛出。
        """

        raise AssertionError(f"unexpected poll for {wait_record.wait_id}")

    def abandon_wait(
        self, wait_record: WaitRecordRow
    ) -> WaitExternalJobLifecycleResult:
        """记录 abandon wait 并返回固定 lifecycle result。

        :param wait_record: wait record。
        :returns: 固定 lifecycle result。
        """

        self.abandoned.append(wait_record.wait_id)
        return self._lifecycle_result


class _AbandonClaimStealingAdapter:
    """abandon 调用中制造 stale claim CAS 冲突的 adapter。"""

    def __init__(
        self,
        transaction_runner: HostTransactionRunner,
        lifecycle_result: WaitExternalJobLifecycleResult | None = None,
    ) -> None:
        """初始化 adapter。

        :param transaction_runner: Host transaction runner。
        :param lifecycle_result: adapter 返回的 lifecycle result。
        :returns: ``None``。
        """

        self._transaction_runner = transaction_runner
        self._lifecycle_result = (
            lifecycle_result
            if lifecycle_result is not None
            else WaitExternalJobLifecycleApplied(
                action=WaitExternalJobLifecycleAction.ABANDON,
                message="test_abandoned",
            )
        )
        self.abandoned: list[str] = []

    def poll_wait(self, wait_record: WaitRecordRow) -> WaitPollResult:
        """本 adapter 不应处理 waiting poll。

        :param wait_record: wait record。
        :returns: 永不返回。
        :raises AssertionError: 被错误调用时抛出。
        """

        raise AssertionError(f"unexpected poll for {wait_record.wait_id}")

    def abandon_wait(
        self, wait_record: WaitRecordRow
    ) -> WaitExternalJobLifecycleResult:
        """篡改当前 row claim，模拟另一路 poller 先写入。

        :param wait_record: wait record。
        :returns: 预置 lifecycle result。
        """

        self.abandoned.append(wait_record.wait_id)

        def operation(transaction: HostTransaction) -> None:
            """替换 wait row claim。

            :param transaction: Host transaction。
            :returns: ``None``。
            """

            transaction.execute(
                f"""
                UPDATE {TABLE_HOST_WAIT_RECORDS}
                SET poll_claim_id = ?,
                    poll_claim_owner_id = ?,
                    poll_claimed_at = ?,
                    poll_claim_expires_at = ?
                WHERE wait_id = ?
                """,
                (
                    "claim-stolen",
                    "poller-stolen",
                    "2026-05-16T02:00:00.000000Z",
                    "2026-05-16T02:05:00.000000Z",
                    wait_record.wait_id,
                ),
            )

        self._transaction_runner.run_write(operation)
        return self._lifecycle_result


class _AbandonAlreadyMarkedAdapter:
    """abandon 调用中保留当前 claim 但制造 abandoned marker CAS 冲突。"""

    def __init__(self, transaction_runner: HostTransactionRunner) -> None:
        """初始化 adapter。

        :param transaction_runner: Host transaction runner。
        :returns: ``None``。
        """

        self._transaction_runner = transaction_runner
        self.abandoned: list[str] = []

    def poll_wait(self, wait_record: WaitRecordRow) -> WaitPollResult:
        """本 adapter 不应处理 waiting poll。

        :param wait_record: wait record。
        :returns: 永不返回。
        :raises AssertionError: 被错误调用时抛出。
        """

        raise AssertionError(f"unexpected poll for {wait_record.wait_id}")

    def abandon_wait(
        self, wait_record: WaitRecordRow
    ) -> WaitExternalJobLifecycleResult:
        """写入 abandoned marker 并保留当前 claim。

        :param wait_record: wait record。
        :returns: applied lifecycle result。
        """

        self.abandoned.append(wait_record.wait_id)

        def operation(transaction: HostTransaction) -> None:
            """写入 abandoned marker。

            :param transaction: Host transaction。
            :returns: ``None``。
            """

            transaction.execute(
                f"""
                UPDATE {TABLE_HOST_WAIT_RECORDS}
                SET poll_abandoned_at = ?
                WHERE wait_id = ?
                """,
                ("2026-05-16T02:00:01.000000Z", wait_record.wait_id),
            )

        self._transaction_runner.run_write(operation)
        return WaitExternalJobLifecycleApplied(
            action=WaitExternalJobLifecycleAction.ABANDON,
            message="test_abandoned",
        )


class _MutableLifecycleGate:
    """测试用可变 lifecycle gate。"""

    def __init__(self) -> None:
        """初始化为未关闭状态。

        :returns: ``None``。
        """

        self.closed = False

    def is_closed(self) -> bool:
        """返回当前关闭状态。

        :returns: 已关闭时返回 ``True``。
        """

        return self.closed


class _CloseGateDuringAbandonAdapter:
    """abandon 成功返回前关闭 lifecycle gate 的 adapter。"""

    def __init__(self, lifecycle_gate: _MutableLifecycleGate) -> None:
        """初始化 adapter。

        :param lifecycle_gate: 将在 abandon 成功期间关闭的 gate。
        :returns: ``None``。
        """

        self._lifecycle_gate = lifecycle_gate
        self.abandoned: list[str] = []

    def poll_wait(self, wait_record: WaitRecordRow) -> WaitPollResult:
        """本 adapter 不应处理 waiting poll。

        :param wait_record: wait record。
        :returns: 永不返回。
        :raises AssertionError: 被错误调用时抛出。
        """

        raise AssertionError(f"unexpected poll for {wait_record.wait_id}")

    def abandon_wait(
        self, wait_record: WaitRecordRow
    ) -> WaitExternalJobLifecycleResult:
        """记录 abandon 成功并关闭 lifecycle gate。

        :param wait_record: wait record。
        :returns: applied lifecycle result。
        """

        self.abandoned.append(wait_record.wait_id)
        self._lifecycle_gate.closed = True
        return WaitExternalJobLifecycleApplied(
            action=WaitExternalJobLifecycleAction.ABANDON,
            message="test_abandoned",
        )


def test_poll_adapter_ready_result_resolves_wait(
    tmp_path: Path,
) -> None:
    """poll adapter ready 结果通过 resolve_wait 恢复 Run。"""

    host = create_host_command_handle(_options(tmp_path))
    try:
        seeded = _seed_waiting_run(host)
        adapter = _SequenceAdapter(
            (
                WaitPollReady(
                    ResolveWaitCompletedOutcome(
                        result=ToolResultSuccess(ok=True, value={"ready": True}, meta=None),
                        payload_ref=None,
                    )
                ),
            )
        )
        poller = _poller(host, adapter, seeded.wait_id)

        result = poller.poll_once()

        wait_record = _read_wait(host._transaction_runner(), seeded.wait_id)
        assert result.resolved == 1
        assert result.lost == 0
        assert wait_record.status is WaitRecordStatus.RESOLVED
    finally:
        host.close()


def test_poll_adapter_ready_result_logs_status_chain_without_payload(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """poller 在正常 ready 路径输出排障状态链且不记录结果正文。"""

    host = create_host_command_handle(_options(tmp_path))
    try:
        seeded = _seed_waiting_run(host)
        adapter = _SequenceAdapter(
            (
                WaitPollReady(
                    ResolveWaitCompletedOutcome(
                        result=ToolResultSuccess(
                            ok=True,
                            value={"payload_secret": "do-not-log"},
                            meta=None,
                        ),
                        payload_ref=None,
                    )
                ),
            )
        )
        poller = _poller(host, adapter, seeded.wait_id)

        with caplog.at_level(VERBOSE_LOG_LEVEL, logger="dayu.host.wait_adapter"):
            result = poller.poll_once()

        assert result.resolved == 1
        assert "host.wait_poller.poll_once.claimed" in caplog.text
        assert "host.wait_poller.observe" in caplog.text
        assert "outcome=ready" in caplog.text
        assert "host.wait_poller.resolve" in caplog.text
        assert "resolve_status=updated" in caplog.text
        assert "host.wait_poller.poll_once.done" in caplog.text
        assert seeded.wait_id in caplog.text
        assert "payload_secret" not in caplog.text
        assert "do-not-log" not in caplog.text
    finally:
        host.close()


def test_poll_adapter_not_ready_leaves_wait_active(
    tmp_path: Path,
) -> None:
    """poll adapter not-ready 不调用 resolve_wait，并安排短间隔复查。"""

    host = create_host_command_handle(_options(tmp_path))
    try:
        seeded = _seed_waiting_run(host)
        adapter = _SequenceAdapter((WaitPollNotReady(),))
        poller = _poller(host, adapter, seeded.wait_id)

        result = poller.poll_once()

        wait_record = _read_wait(host._transaction_runner(), seeded.wait_id)
        second = poller.poll_once()
        assert result.not_ready == 1
        assert second.observed == 0
        assert adapter.poll_count == 1
        assert wait_record.status is WaitRecordStatus.WAITING
        assert wait_record.poll_next_observe_at is not None
        assert wait_record.poll_backoff_attempt == 0
        assert wait_record.poll_last_outcome is WaitPollLastOutcome.NOT_READY
    finally:
        host.close()


def test_poll_adapter_empty_round_does_not_log_poll_summary(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """poller 无可处理 wait 时不刷逐轮空摘要日志。"""

    host = create_host_command_handle(_options(tmp_path))
    try:
        poller = WaitPoller(
            transaction_runner=host._transaction_runner(),
            adapter_registry=WaitPollAdapterRegistry(()),
            resolver=_NoResolveResolver(),
            context=_context("poller"),
            clock=_FixedClock(),
        )

        with caplog.at_level(VERBOSE_LOG_LEVEL, logger="dayu.host.wait_adapter"):
            result = poller.poll_once()

        assert result.observed == 0
        assert "host.wait_poller.poll_once.claimed" not in caplog.text
        assert "host.wait_poller.poll_once.done" not in caplog.text
    finally:
        host.close()


def test_poll_adapter_lost_result_closes_run(
    tmp_path: Path,
) -> None:
    """poll adapter lost 结果通过 resolve_wait 收口 Run。"""

    host = create_host_command_handle(_options(tmp_path))
    try:
        seeded = _seed_waiting_run(host)
        adapter = _SequenceAdapter(
            (
                WaitPollLost(
                    ResolveWaitLostOutcome(
                        reason_code="adapter_lost",
                        message="external job status is no longer observable",
                        provider_status_ref=WaitProviderStatusRef(
                            adapter_key=_read_wait(
                                host._transaction_runner(), seeded.wait_id
                            ).adapter_key,
                            status_ref="provider-status-lost",
                            status_digest=sha256_digest_json(
                                {"status": "poll-lost"}
                            ),
                        ),
                    )
                ),
            )
        )
        poller = _poller(host, adapter, seeded.wait_id)

        result = poller.poll_once()

        wait_record = _read_wait(host._transaction_runner(), seeded.wait_id)
        snapshot = get_run(host, seeded.run_id)
        assert result.resolved == 0
        assert result.lost == 1
        assert adapter.poll_count == 1
        assert wait_record.status is WaitRecordStatus.LOST
        assert snapshot.status is RunStatus.LOST
    finally:
        host.close()


def test_cancelled_poll_wait_is_abandoned_once_without_resolve(
    tmp_path: Path,
) -> None:
    """cancelled poll wait durable abandon 后新 poller 不重复 abandon。"""

    host = create_host_command_handle(_options(tmp_path))
    try:
        seeded = _seed_waiting_run(host)
        cancel_run(
            host,
            seeded.run_id,
            CancelRunRequest(
                context=_context("poll-cancel"),
                client_request_id="poll-cancel",
                reason="user_cancel",
                mode=CancelMode.GRACEFUL,
            ),
        )
        adapter = _SequenceAdapter((WaitPollNotReady(),))
        poller = _poller(host, adapter, seeded.wait_id)

        result = poller.poll_once()
        second = _poller(host, adapter, seeded.wait_id).poll_once()

        wait_record = _read_wait(host._transaction_runner(), seeded.wait_id)
        assert result.abandoned == 1
        assert second.abandoned == 0
        assert second.observed == 0
        assert adapter.poll_count == 0
        assert adapter.abandoned == [seeded.wait_id]
        assert len(adapter.lifecycle_results) == 1
        assert isinstance(
            adapter.lifecycle_results[0], WaitExternalJobLifecycleApplied
        )
        assert (
            adapter.lifecycle_results[0].action
            is WaitExternalJobLifecycleAction.ABANDON
        )
        assert wait_record.status is WaitRecordStatus.CANCELLED
        assert wait_record.poll_abandoned_at is not None
        assert wait_record.poll_last_outcome is WaitPollLastOutcome.ABANDONED
    finally:
        host.close()


def test_cancelled_poll_wait_unsupported_marks_terminal_without_resolve(
    tmp_path: Path,
) -> None:
    """unsupported lifecycle result 写入 terminal diagnostic 且不调用 resolve_wait。"""

    host = create_host_command_handle(_options(tmp_path))
    try:
        seeded = _seed_waiting_run(host)
        cancel_run(
            host,
            seeded.run_id,
            CancelRunRequest(
                context=_context("poll-cancel-unsupported"),
                client_request_id="poll-cancel-unsupported",
                reason="user_cancel",
                mode=CancelMode.GRACEFUL,
            ),
        )
        adapter = _StaticLifecycleAdapter(
            WaitExternalJobLifecycleUnsupported(reason="provider_unsupported")
        )
        resolver = _NoResolveResolver()
        poller = _poller_with_resolver(host, adapter, seeded.wait_id, resolver)

        result = poller.poll_once()
        second = _poller_with_resolver(
            host, adapter, seeded.wait_id, resolver
        ).poll_once()

        wait_record = _read_wait(host._transaction_runner(), seeded.wait_id)
        assert result.abandoned == 1
        assert second.observed == 0
        assert adapter.abandoned == [seeded.wait_id]
        assert resolver.calls == []
        assert wait_record.status is WaitRecordStatus.CANCELLED
        assert wait_record.poll_abandoned_at is not None
        assert wait_record.poll_last_outcome is WaitPollLastOutcome.ABANDON_UNSUPPORTED
    finally:
        host.close()


def test_cancelled_poll_wait_noop_marks_terminal_without_resolve(
    tmp_path: Path,
) -> None:
    """noop lifecycle result 写入 terminal diagnostic 且不调用 resolve_wait。"""

    host = create_host_command_handle(_options(tmp_path))
    try:
        seeded = _seed_waiting_run(host)
        cancel_run(
            host,
            seeded.run_id,
            CancelRunRequest(
                context=_context("poll-cancel-noop"),
                client_request_id="poll-cancel-noop",
                reason="user_cancel",
                mode=CancelMode.GRACEFUL,
            ),
        )
        adapter = _StaticLifecycleAdapter(
            WaitExternalJobLifecycleNoop(reason="external_ref_missing")
        )
        resolver = _NoResolveResolver()
        poller = _poller_with_resolver(host, adapter, seeded.wait_id, resolver)

        result = poller.poll_once()
        second = _poller_with_resolver(
            host, adapter, seeded.wait_id, resolver
        ).poll_once()

        wait_record = _read_wait(host._transaction_runner(), seeded.wait_id)
        assert result.abandoned == 1
        assert second.observed == 0
        assert adapter.abandoned == [seeded.wait_id]
        assert resolver.calls == []
        assert wait_record.status is WaitRecordStatus.CANCELLED
        assert wait_record.poll_abandoned_at is not None
        assert wait_record.poll_last_outcome is WaitPollLastOutcome.ABANDON_NOOP
    finally:
        host.close()


def test_cancelled_abandon_success_marks_abandoned_when_close_gate_closes(
    tmp_path: Path,
) -> None:
    """abandon 外部成功后 close gate 关闭也必须先写 durable abandoned mark。"""

    host = create_host_command_handle(_options(tmp_path))
    try:
        seeded = _seed_waiting_run(host)
        cancel_run(
            host,
            seeded.run_id,
            CancelRunRequest(
                context=_context("poll-cancel-close-after-abandon"),
                client_request_id="poll-cancel-close-after-abandon",
                reason="user_cancel",
                mode=CancelMode.GRACEFUL,
            ),
        )
        lifecycle_gate = _MutableLifecycleGate()
        adapter = _CloseGateDuringAbandonAdapter(lifecycle_gate)
        poller = _poller(
            host,
            adapter,
            seeded.wait_id,
            lifecycle_gate=lifecycle_gate,
        )

        result = poller.poll_once()
        second = _poller(host, adapter, seeded.wait_id).poll_once()

        wait_record = _read_wait(host._transaction_runner(), seeded.wait_id)
        assert result.abandoned == 1
        assert result.shutdown_skipped == 0
        assert result.claim_conflicts == 0
        assert second.observed == 0
        assert adapter.abandoned == [seeded.wait_id]
        assert wait_record.poll_abandoned_at is not None
        assert wait_record.poll_last_outcome is WaitPollLastOutcome.ABANDONED
        assert wait_record.poll_claim_id is None
    finally:
        host.close()


def test_missing_poll_adapter_registration_logs_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """poll adapter 未注册时记录 wait id 与 adapter key。"""

    host = create_host_command_handle(_options(tmp_path))
    try:
        seeded = _seed_waiting_run(host)
        wait_record = _read_wait(host._transaction_runner(), seeded.wait_id)
        poller = WaitPoller(
            transaction_runner=host._transaction_runner(),
            adapter_registry=WaitPollAdapterRegistry(()),
            resolver=_PublicCommandResolver(host),
            context=_context("poller-missing-adapter"),
            clock=_FixedClock(),
        )

        with caplog.at_level(logging.WARNING, logger="dayu.host.wait_adapter"):
            result = poller.poll_once()

        assert result.observed == 1
        assert result.adapter_errors == 1
        updated_wait_record = _read_wait(host._transaction_runner(), seeded.wait_id)
        assert "wait poll adapter not registered; retrying" in caplog.text
        assert seeded.wait_id in caplog.text
        assert wait_record.adapter_key.value in caplog.text
        assert updated_wait_record.poll_next_observe_at is not None
        assert updated_wait_record.poll_backoff_attempt == 1
        assert updated_wait_record.poll_last_outcome is WaitPollLastOutcome.MISSING_ADAPTER
        assert updated_wait_record.poll_last_error_code == "missing_adapter"
    finally:
        host.close()


def test_cancelled_poll_wait_missing_adapter_stays_retryable(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """cancelled wait 缺失 poll adapter 时只写 retry backoff。"""

    host = create_host_command_handle(_options(tmp_path))
    try:
        seeded = _seed_waiting_run(host)
        cancel_run(
            host,
            seeded.run_id,
            CancelRunRequest(
                context=_context("poll-cancel-missing-adapter"),
                client_request_id="poll-cancel-missing-adapter",
                reason="user_cancel",
                mode=CancelMode.GRACEFUL,
            ),
        )
        wait_record = _read_wait(host._transaction_runner(), seeded.wait_id)
        poller = WaitPoller(
            transaction_runner=host._transaction_runner(),
            adapter_registry=WaitPollAdapterRegistry(()),
            resolver=_NoResolveResolver(),
            context=_context("poller-cancelled-missing-adapter"),
            clock=_FixedClock(),
        )

        with caplog.at_level(logging.WARNING, logger="dayu.host.wait_adapter"):
            result = poller.poll_once()

        updated_wait_record = _read_wait(host._transaction_runner(), seeded.wait_id)
        assert result.observed == 1
        assert result.adapter_errors == 1
        assert result.abandoned == 0
        assert "wait poll adapter not registered; retrying cancelled" in caplog.text
        assert seeded.wait_id in caplog.text
        assert wait_record.adapter_key.value in caplog.text
        assert updated_wait_record.status is WaitRecordStatus.CANCELLED
        assert updated_wait_record.poll_abandoned_at is None
        assert updated_wait_record.poll_claim_id is None
        assert updated_wait_record.poll_next_observe_at is not None
        assert updated_wait_record.poll_backoff_attempt == 1
        assert updated_wait_record.poll_last_outcome is WaitPollLastOutcome.MISSING_ADAPTER
        assert updated_wait_record.poll_last_error_code == "missing_adapter"
    finally:
        host.close()


def test_adapter_non_runtime_exception_isolated_per_wait_record(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """adapter 普通异常只影响单条 wait record，后续记录继续处理。"""

    host = create_host_command_handle(_options(tmp_path))
    try:
        seeded = _seed_waiting_run(host)
        cancel_run(
            host,
            seeded.run_id,
            CancelRunRequest(
                context=_context("poll-cancel-for-error"),
                client_request_id="poll-cancel-for-error",
                reason="user_cancel",
                mode=CancelMode.GRACEFUL,
            ),
        )
        followup_wait_id = "zz-wait-followup"
        _insert_followup_wait_record(host, seeded.wait_id, followup_wait_id)
        adapter = _AbandonValueErrorThenNotReadyAdapter()
        poller = _poller(host, adapter, seeded.wait_id)

        with caplog.at_level(logging.WARNING, logger="dayu.host.wait_adapter"):
            result = poller.poll_once()

        assert result.observed == 2
        assert result.adapter_errors == 1
        assert result.not_ready == 1
        assert result.abandoned == 0
        assert adapter.abandoned == [seeded.wait_id]
        assert adapter.polled == [followup_wait_id]
        assert "wait adapter abandon failed; continuing" in caplog.text
    finally:
        host.close()


def test_resolve_wait_exception_isolated_per_wait_record(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """resolve_wait 普通异常只影响单条 wait record，后续记录继续处理。"""

    host = create_host_command_handle(_options(tmp_path))
    try:
        seeded = _seed_waiting_run(host)
        adapter = _SequenceAdapter(
            (
                WaitPollReady(
                    ResolveWaitCompletedOutcome(
                        result=ToolResultSuccess(
                            ok=True, value={"ready": True}, meta=None
                        ),
                        payload_ref=None,
                    )
                ),
            )
        )
        resolver = _FailingResolveResolver()
        poller = WaitPoller(
            transaction_runner=host._transaction_runner(),
            adapter_registry=WaitPollAdapterRegistry(
                (
                    WaitPollAdapterRegistration(
                        adapter_key=_read_wait(
                            host._transaction_runner(), seeded.wait_id
                        ).adapter_key,
                        adapter=adapter,
                    ),
                )
            ),
            resolver=resolver,
            context=_context("poller-resolve-failure"),
            clock=_FixedClock(),
        )

        with caplog.at_level(logging.WARNING, logger="dayu.host.wait_adapter"):
            result = poller.poll_once()

        first_wait = _read_wait(host._transaction_runner(), seeded.wait_id)
        assert result.observed == 1
        assert result.adapter_errors == 1
        assert result.not_ready == 0
        assert result.resolved == 0
        assert first_wait.status is WaitRecordStatus.WAITING
        assert resolver.calls == [seeded.wait_id]
        assert "wait poll resolve failed; continuing" in caplog.text
        assert seeded.wait_id in caplog.text
    finally:
        host.close()


def test_resolve_wait_exception_readback_failure_isolated(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """resolve_wait 失败后的 read-back 再失败也不能冒泡到 supervisor。"""

    host = create_host_command_handle(_options(tmp_path))
    try:
        seeded = _seed_waiting_run(host)
        adapter = _SequenceAdapter(
            (
                WaitPollReady(
                    ResolveWaitCompletedOutcome(
                        result=ToolResultSuccess(
                            ok=True, value={"ready": True}, meta=None
                        ),
                        payload_ref=None,
                    )
                ),
            )
        )
        resolver = _FailingResolveResolver()
        runner = host._transaction_runner()
        adapter_key = _read_wait(runner, seeded.wait_id).adapter_key
        original_run_read = runner.run_read

        def _failing_recovery_read(
            operation: HostTransactionOperation[WaitRecordRow | None],
        ) -> WaitRecordRow | None:
            """只让 resolve error recovery 的 wait record 读回失败。

            :param operation: transaction read operation。
            :returns: 正常 read operation 的返回值。
            :raises RuntimeError: 读回 wait record 时抛出。
            """

            if operation.__class__.__name__ == "_ReadWaitRecordOperation":
                raise RuntimeError("readback failed")
            return original_run_read(operation)

        monkeypatch.setattr(runner, "run_read", _failing_recovery_read)
        poller = WaitPoller(
            transaction_runner=runner,
            adapter_registry=WaitPollAdapterRegistry(
                (
                    WaitPollAdapterRegistration(
                        adapter_key=adapter_key,
                        adapter=adapter,
                    ),
                )
            ),
            resolver=resolver,
            context=_context("poller-resolve-readback-failure"),
            clock=_FixedClock(),
        )

        with caplog.at_level(logging.WARNING, logger="dayu.host.wait_adapter"):
            result = poller.poll_once()

        monkeypatch.setattr(runner, "run_read", original_run_read)
        wait_record = _read_wait(runner, seeded.wait_id)
        assert result.observed == 1
        assert result.adapter_errors == 1
        assert result.resolved == 0
        assert wait_record.status is WaitRecordStatus.WAITING
        assert wait_record.poll_claim_id is None
        assert wait_record.poll_last_outcome is WaitPollLastOutcome.RESOLVE_ERROR
        assert "wait poll resolve recovery read failed; continuing" in caplog.text
    finally:
        host.close()


def test_failed_cancelled_wait_abandon_is_retried_next_poll(
    tmp_path: Path,
) -> None:
    """cancelled wait abandon 失败时不写入已 abandon 记忆，下一轮继续重试。"""

    host = create_host_command_handle(_options(tmp_path))
    try:
        seeded = _seed_waiting_run(host)
        cancel_run(
            host,
            seeded.run_id,
            CancelRunRequest(
                context=_context("poll-cancel-retry"),
                client_request_id="poll-cancel-retry",
                reason="user_cancel",
                mode=CancelMode.GRACEFUL,
            ),
        )
        adapter = _AbandonValueErrorThenNotReadyAdapter()
        poller = _poller(host, adapter, seeded.wait_id)

        first = poller.poll_once()
        second = poller.poll_once()

        assert first.abandoned == 0
        assert second.abandoned == 0
        assert first.adapter_errors == 1
        assert second.adapter_errors == 0
        assert second.observed == 0
        assert adapter.abandoned == [seeded.wait_id]
    finally:
        host.close()


def test_active_poll_claim_suppresses_second_poller_adapter_call(
    tmp_path: Path,
) -> None:
    """未过期 poll claim 存在时，另一个 poller 不调用 adapter。"""

    host = create_host_command_handle(_options(tmp_path))
    try:
        seeded = _seed_waiting_run(host)
        _set_poll_claim(
            host,
            wait_id=seeded.wait_id,
            claim_id="claim-active",
            expires_at="2026-05-16T02:05:00.000000Z",
        )
        adapter = _SequenceAdapter((WaitPollNotReady(),))
        poller = _poller(host, adapter, seeded.wait_id)

        result = poller.poll_once()

        assert result.observed == 0
        assert adapter.poll_count == 0
    finally:
        host.close()


def test_expired_poll_claim_allows_retry(tmp_path: Path) -> None:
    """已过期 poll claim 可被新 poller 接管并调用 adapter。"""

    host = create_host_command_handle(_options(tmp_path))
    try:
        seeded = _seed_waiting_run(host)
        _set_poll_claim(
            host,
            wait_id=seeded.wait_id,
            claim_id="claim-expired",
            expires_at="2026-05-16T01:59:00.000000Z",
        )
        adapter = _SequenceAdapter((WaitPollNotReady(),))
        poller = _poller(host, adapter, seeded.wait_id)

        result = poller.poll_once()

        assert result.observed == 1
        assert result.not_ready == 1
        assert adapter.poll_count == 1
    finally:
        host.close()


def test_resolve_failure_releases_with_backoff_and_reuses_idempotency_key(
    tmp_path: Path,
) -> None:
    """resolve 失败释放 claim；到期后重试使用同一 poll idempotency key。"""

    host = create_host_command_handle(_options(tmp_path))
    try:
        seeded = _seed_waiting_run(host)
        adapter = _SequenceAdapter(
            (
                WaitPollReady(
                    ResolveWaitCompletedOutcome(
                        result=ToolResultSuccess(ok=True, value={"ready": True}, meta=None),
                        payload_ref=None,
                    )
                ),
                WaitPollReady(
                    ResolveWaitCompletedOutcome(
                        result=ToolResultSuccess(ok=True, value={"ready": True}, meta=None),
                        payload_ref=None,
                    )
                ),
            )
        )
        failing_resolver = _FailingResolveResolver()
        failing_poller = WaitPoller(
            transaction_runner=host._transaction_runner(),
            adapter_registry=WaitPollAdapterRegistry(
                (
                    WaitPollAdapterRegistration(
                        adapter_key=_read_wait(host._transaction_runner(), seeded.wait_id).adapter_key,
                        adapter=adapter,
                    ),
                )
            ),
            resolver=failing_resolver,
            context=_context("poller-resolve-failure"),
            clock=_FixedClock(),
        )

        failed = failing_poller.poll_once()
        wait_after_failure = _read_wait(host._transaction_runner(), seeded.wait_id)
        _force_wait_poll_due(host, seeded.wait_id)
        recording_resolver = _RecordingPublicCommandResolver(host)
        retry_poller = WaitPoller(
            transaction_runner=host._transaction_runner(),
            adapter_registry=WaitPollAdapterRegistry(
                (
                    WaitPollAdapterRegistration(
                        adapter_key=wait_after_failure.adapter_key,
                        adapter=adapter,
                    ),
                )
            ),
            resolver=recording_resolver,
            context=_context("poller-resolve-retry"),
            clock=_FixedClock(),
        )
        retried = retry_poller.poll_once()

        assert failed.adapter_errors == 1
        assert wait_after_failure.poll_claim_id is None
        assert wait_after_failure.poll_next_observe_at is not None
        assert wait_after_failure.poll_last_outcome is WaitPollLastOutcome.RESOLVE_ERROR
        assert retried.resolved == 1
        assert failing_resolver.idempotency_keys == recording_resolver.idempotency_keys
    finally:
        host.close()


@pytest.mark.parametrize(
    "adapter",
    (
        _SequenceAdapter(
            (
                WaitPollReady(
                    ResolveWaitCompletedOutcome(
                        result=ToolResultSuccess(
                            ok=True, value={"ready": True}, meta=None
                        ),
                        payload_ref=None,
                    )
                ),
            )
        ),
        _SequenceAdapter((WaitPollNotReady(),)),
        _FailingPollAdapter(),
    ),
)
def test_expired_poll_wait_is_released_before_provider_observation(
    tmp_path: Path,
    adapter: WaitPollAdapter,
) -> None:
    """expired wait 由 Host poll owner 拦截，ready/pending/error 不分裂终态。"""

    host = create_host_command_handle(_options(tmp_path))
    try:
        seeded = _seed_waiting_run(host)
        _set_wait_deadline(
            host,
            seeded.wait_id,
            datetime(2026, 5, 16, 1, 59, 59, tzinfo=UTC),
        )
        poller = _poller(host, adapter, seeded.wait_id)

        result = poller.poll_once()
        wait_record = _read_wait(host._transaction_runner(), seeded.wait_id)

        assert result.observed == 1
        assert result.adapter_errors == 0
        assert result.boundary_rejections == 1
        assert result.resolved == 0
        assert result.lost == 0
        assert result.not_ready == 0
        assert wait_record.status is WaitRecordStatus.WAITING
        assert wait_record.poll_claim_id is None
        assert wait_record.poll_last_outcome is WaitPollLastOutcome.BOUNDARY_REJECTED
        assert wait_record.poll_last_error_code == "wait_expired"
        if isinstance(adapter, _SequenceAdapter):
            assert adapter.poll_count == 0
        if isinstance(adapter, _FailingPollAdapter):
            assert adapter.polled == []
    finally:
        host.close()


def test_invalid_poll_deadline_fails_closed_without_business_lost(
    tmp_path: Path,
) -> None:
    """非法 poll deadline fail closed，不调用 provider，也不写业务 LOST。"""

    host = create_host_command_handle(_options(tmp_path))
    try:
        seeded = _seed_waiting_run(host)
        _set_wait_deadline_text(host, seeded.wait_id, "not-a-timestamp")
        adapter = _SequenceAdapter(
            (
                WaitPollLost(
                    ResolveWaitLostOutcome(
                        reason_code="provider_lost",
                        message="provider lost",
                        provider_status_ref=None,
                    )
                ),
            )
        )
        poller = _poller(host, adapter, seeded.wait_id)

        result = poller.poll_once()
        wait_record = _read_wait(host._transaction_runner(), seeded.wait_id)

        assert result.adapter_errors == 0
        assert result.boundary_rejections == 1
        assert result.lost == 0
        assert adapter.poll_count == 0
        assert wait_record.status is WaitRecordStatus.WAITING
        assert wait_record.poll_last_outcome is WaitPollLastOutcome.BOUNDARY_REJECTED
        assert wait_record.poll_last_error_code == "invalid_wait_time_boundary"
    finally:
        host.close()


def test_abandon_cas_conflict_leaves_cancelled_wait_retryable(
    tmp_path: Path,
) -> None:
    """abandon CAS 冲突不写 poll_abandoned_at，后续仍可重试 cancelled wait。"""

    host = create_host_command_handle(_options(tmp_path))
    try:
        seeded = _seed_waiting_run(host)
        cancel_run(
            host,
            seeded.run_id,
            CancelRunRequest(
                context=_context("poll-cancel-abandon-conflict"),
                client_request_id="poll-cancel-abandon-conflict",
                reason="user_cancel",
                mode=CancelMode.GRACEFUL,
            ),
        )
        adapter = _AbandonClaimStealingAdapter(host._transaction_runner())
        poller = _poller(host, adapter, seeded.wait_id)

        result = poller.poll_once()
        wait_record = _read_wait(host._transaction_runner(), seeded.wait_id)

        assert result.abandoned == 0
        assert result.claim_conflicts == 1
        assert adapter.abandoned == [seeded.wait_id]
        assert wait_record.poll_abandoned_at is None
        assert wait_record.poll_claim_id == "claim-stolen"
    finally:
        host.close()


def test_abandon_cas_lost_releases_current_claim(
    tmp_path: Path,
) -> None:
    """abandon marker CAS_LOST 时释放当前 claim，避免等待 claim TTL。"""

    host = create_host_command_handle(_options(tmp_path))
    try:
        seeded = _seed_waiting_run(host)
        cancel_run(
            host,
            seeded.run_id,
            CancelRunRequest(
                context=_context("poll-cancel-abandon-release"),
                client_request_id="poll-cancel-abandon-release",
                reason="user_cancel",
                mode=CancelMode.GRACEFUL,
            ),
        )
        adapter = _AbandonAlreadyMarkedAdapter(host._transaction_runner())
        poller = _poller(host, adapter, seeded.wait_id)

        result = poller.poll_once()
        wait_record = _read_wait(host._transaction_runner(), seeded.wait_id)

        assert result.abandoned == 0
        assert result.claim_conflicts == 0
        assert adapter.abandoned == [seeded.wait_id]
        assert wait_record.poll_abandoned_at is not None
        assert wait_record.poll_claim_id is None
        assert wait_record.poll_last_outcome is WaitPollLastOutcome.ABANDON_ERROR
    finally:
        host.close()


@pytest.mark.parametrize(
    ("lifecycle_result", "expected_terminal_outcome"),
    (
        (
            WaitExternalJobLifecycleUnsupported(reason="provider_unsupported"),
            WaitPollLastOutcome.ABANDON_UNSUPPORTED,
        ),
        (
            WaitExternalJobLifecycleNoop(reason="external_ref_missing"),
            WaitPollLastOutcome.ABANDON_NOOP,
        ),
    ),
)
def test_terminal_abandon_cas_conflict_leaves_cancelled_wait_retryable(
    tmp_path: Path,
    lifecycle_result: WaitExternalJobLifecycleResult,
    expected_terminal_outcome: WaitPollLastOutcome,
) -> None:
    """unsupported / noop terminal marker CAS 冲突时不终止 wait retry。"""

    host = create_host_command_handle(_options(tmp_path))
    try:
        seeded = _seed_waiting_run(host)
        cancel_run(
            host,
            seeded.run_id,
            CancelRunRequest(
                context=_context(
                    f"poll-cancel-{expected_terminal_outcome.value}-conflict"
                ),
                client_request_id=(
                    f"poll-cancel-{expected_terminal_outcome.value}-conflict"
                ),
                reason="user_cancel",
                mode=CancelMode.GRACEFUL,
            ),
        )
        adapter = _AbandonClaimStealingAdapter(
            host._transaction_runner(),
            lifecycle_result=lifecycle_result,
        )
        poller = _poller(host, adapter, seeded.wait_id)

        result = poller.poll_once()
        wait_record = _read_wait(host._transaction_runner(), seeded.wait_id)

        assert result.abandoned == 0
        assert result.claim_conflicts == 1
        assert adapter.abandoned == [seeded.wait_id]
        assert wait_record.poll_abandoned_at is None
        assert wait_record.poll_last_outcome is None
        assert wait_record.poll_claim_id == "claim-stolen"
    finally:
        host.close()


def _poller(
    host: HostCommandHandle,
    adapter: WaitPollAdapter,
    wait_id: str,
    *,
    lifecycle_gate: WaitPollLifecycleGate | None = None,
) -> WaitPoller:
    """构造测试 poller。

    :param host: Host command handle。
    :param adapter: poll adapter。
    :param wait_id: 测试 wait id。
    :param lifecycle_gate: 可选 lifecycle gate。
    :returns: poller。
    """

    return WaitPoller(
        transaction_runner=host._transaction_runner(),
        adapter_registry=WaitPollAdapterRegistry(
            (
                WaitPollAdapterRegistration(
                    adapter_key=_read_wait(
                        host._transaction_runner(), wait_id
                    ).adapter_key,
                    adapter=adapter,
                ),
            )
        ),
        resolver=_PublicCommandResolver(host),
        context=_context("poller"),
        clock=_FixedClock(),
        lifecycle_gate=lifecycle_gate,
    )


def _poller_with_resolver(
    host: HostCommandHandle,
    adapter: WaitPollAdapter,
    wait_id: str,
    resolver: WaitResolvePort,
) -> WaitPoller:
    """构造使用指定 resolver 的测试 poller。

    :param host: Host command handle。
    :param adapter: poll adapter。
    :param wait_id: 测试 wait id。
    :param resolver: 测试 resolver。
    :returns: poller。
    """

    return WaitPoller(
        transaction_runner=host._transaction_runner(),
        adapter_registry=WaitPollAdapterRegistry(
            (
                WaitPollAdapterRegistration(
                    adapter_key=_read_wait(
                        host._transaction_runner(), wait_id
                    ).adapter_key,
                    adapter=adapter,
                ),
            )
        ),
        resolver=resolver,
        context=_context("poller"),
        clock=_FixedClock(),
    )


def _set_wait_deadline(
    host: HostCommandHandle,
    wait_id: str,
    deadline: datetime,
) -> None:
    """更新测试 wait record deadline。

    :param host: Host command handle。
    :param wait_id: wait id。
    :param deadline: deadline UTC datetime。
    :returns: ``None``。
    """

    _set_wait_deadline_text(host, wait_id, format_utc_timestamp(deadline))


def _set_wait_deadline_text(
    host: HostCommandHandle,
    wait_id: str,
    deadline_text: str,
) -> None:
    """更新测试 wait record deadline 原始文本。

    :param host: Host command handle。
    :param wait_id: wait id。
    :param deadline_text: deadline 原始文本。
    :returns: ``None``。
    """

    def _operation(transaction: HostTransaction) -> None:
        """执行 deadline 文本更新。

        :param transaction: 当前 Host transaction。
        :returns: ``None``。
        """

        transaction.execute(
            f"UPDATE {TABLE_HOST_WAIT_RECORDS} SET deadline_at = ? WHERE wait_id = ?",
            (deadline_text, wait_id),
        )

    host._transaction_runner().run_write(_operation)


def _insert_followup_wait_record(
    host: HostCommandHandle, source_wait_id: str, followup_wait_id: str
) -> None:
    """复制一条 waiting poll record，用于验证 poller 单条异常隔离。

    :param host: Host command handle。
    :param source_wait_id: 已存在的 wait id。
    :param followup_wait_id: 新 waiting wait id。
    :returns: ``None``。
    """

    def operation(transaction: HostTransaction) -> None:
        """执行 wait record 复制。

        :param transaction: Host transaction。
        :returns: ``None``。
        """

        transaction.execute(
            f"""
            INSERT INTO {TABLE_HOST_WAIT_RECORDS} (
              wait_id,
              session_id,
              run_id,
              attempt_id,
              execution_id,
              tool_call_id,
              tool_name,
              adapter_key,
              await_kind,
              resume_policy,
              resume_token,
              snapshot_ref,
              snapshot_captured_at,
              snapshot_digest,
              external_job_id,
              accept_idempotency_key,
              resolve_idempotency_key,
              resolve_semantic_digest,
              deadline_at,
              expires_at,
              status,
              created_event_id,
              created_event_sequence,
              updated_event_id,
              updated_event_sequence,
              created_at,
              updated_at,
              terminal_at
            )
            SELECT
              ?,
              session_id,
              run_id,
              attempt_id,
              execution_id,
              tool_call_id || '-followup',
              tool_name,
              adapter_key,
              await_kind,
              resume_policy,
              resume_token || '-followup',
              snapshot_ref,
              snapshot_captured_at,
              snapshot_digest,
              external_job_id || '-followup',
              accept_idempotency_key || '-followup',
              NULL,
              NULL,
              deadline_at,
              expires_at,
              ?,
              created_event_id,
              created_event_sequence,
              created_event_id,
              created_event_sequence,
              created_at,
              created_at,
              NULL
            FROM {TABLE_HOST_WAIT_RECORDS}
            WHERE wait_id = ?
            """,
            (
                followup_wait_id,
                WaitRecordStatus.WAITING.value,
                source_wait_id,
            ),
        )

    host._transaction_runner().run_write(operation)


def _set_poll_claim(
    host: HostCommandHandle,
    *,
    wait_id: str,
    claim_id: str,
    expires_at: str,
) -> None:
    """直接设置 wait row poll claim，用于构造 claim takeover 场景。

    :param host: Host command handle。
    :param wait_id: wait record id。
    :param claim_id: poll claim id。
    :param expires_at: claim 过期时间。
    :returns: ``None``。
    """

    def operation(transaction: HostTransaction) -> None:
        """写入 poll claim 字段。

        :param transaction: Host transaction。
        :returns: ``None``。
        """

        transaction.execute(
            f"""
            UPDATE {TABLE_HOST_WAIT_RECORDS}
            SET poll_claim_id = ?,
                poll_claim_owner_id = ?,
                poll_claimed_at = ?,
                poll_claim_expires_at = ?
            WHERE wait_id = ?
            """,
            (
                claim_id,
                "poller-test-owner",
                "2026-05-16T02:00:00.000000Z",
                expires_at,
                wait_id,
            ),
        )

    host._transaction_runner().run_write(operation)


def _force_wait_poll_due(host: HostCommandHandle, wait_id: str) -> None:
    """清理 poll_next_observe_at，让 wait 可立即重试。

    :param host: Host command handle。
    :param wait_id: wait record id。
    :returns: ``None``。
    """

    def operation(transaction: HostTransaction) -> None:
        """清理 next observe 时间。

        :param transaction: Host transaction。
        :returns: ``None``。
        """

        transaction.execute(
            f"""
            UPDATE {TABLE_HOST_WAIT_RECORDS}
            SET poll_next_observe_at = NULL
            WHERE wait_id = ?
            """,
            (wait_id,),
        )

    host._transaction_runner().run_write(operation)
