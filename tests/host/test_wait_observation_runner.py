"""Host bounded wait observation runner 的确定性并发测试。"""

from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

from dayu.contracts.tool_result import ToolResultSuccess
from dayu.host import (
    CancelMode,
    CancelRunRequest,
    ResolveWaitCompletedOutcome,
    RunStatus,
    cancel_run,
    get_run,
)
from dayu.host._wait_observation import (
    WaitObservationCapacityExceeded,
    WaitObservationPublished,
    WaitObservationRunner,
    WaitObservationTimedOut,
)
from dayu.host.command import HostCommandHandle, create_host_command_handle
from dayu.host.durable.codec import format_utc_timestamp
from dayu.host.durable.state import WaitPollLastOutcome, WaitRecordStatus
from dayu.host.wait_adapter import (
    WaitAdapterSnapshot,
    WaitExternalJobLifecycleApplied,
    WaitExternalJobLifecycleAction,
    WaitExternalJobLifecycleResult,
    WaitPollAdapterRegistration,
    WaitPollAdapterRegistry,
    WaitPollClock,
    WaitPollLifecycleGate,
    WaitPollOnceResult,
    WaitPollReady,
    WaitPollResult,
    WaitPoller,
    WaitPollerFactory,
    WaitPollerLoopStatus,
    WaitPollerRuntimePolicy,
    WaitPollerSupervisor,
    WaitResolvePort,
)
from tests.host.test_resolve_wait_command import (
    _context,
    _options,
    _read_wait,
    _seed_waiting_run,
)
from tests.host.test_wait_adapter_polling import (
    _FixedClock,
    _NoResolveResolver,
    _RecordingPublicCommandResolver,
)


class _BlockingAdapter:
    """poll/abandon 都由显式 barrier 控制的同步 adapter。"""

    def __init__(self) -> None:
        """初始化 barrier 与调用计数。

        :returns: ``None``。
        """

        self.poll_entered = threading.Event()
        self.poll_release = threading.Event()
        self.abandon_entered = threading.Event()
        self.abandon_release = threading.Event()
        self.poll_calls = 0
        self.abandon_calls = 0

    def poll_wait(self, snapshot: WaitAdapterSnapshot) -> WaitPollResult:
        """阻塞 poll 直到测试释放。

        :param snapshot: adapter snapshot。
        :returns: ready 结果；首轮超时后的迟到结果必须被 dropped。
        """

        del snapshot
        self.poll_calls += 1
        self.poll_entered.set()
        self.poll_release.wait()
        return WaitPollReady(
            ResolveWaitCompletedOutcome(
                result=ToolResultSuccess(
                    ok=True,
                    value={"ready": True},
                    meta=None,
                ),
                payload_ref=None,
            )
        )

    def abandon_wait(
        self, snapshot: WaitAdapterSnapshot
    ) -> WaitExternalJobLifecycleResult:
        """阻塞 abandon 直到测试释放。

        :param snapshot: adapter snapshot。
        :returns: applied 结果；超时后该结果必须被 dropped。
        """

        del snapshot
        self.abandon_calls += 1
        self.abandon_entered.set()
        self.abandon_release.wait()
        return WaitExternalJobLifecycleApplied(
            action=WaitExternalJobLifecycleAction.ABANDON,
            message="released after Host timeout",
        )


class _MutableClock:
    """可显式推进的 wait poll 测试时钟。"""

    def __init__(self) -> None:
        """以既有 fixed clock 的时点初始化。

        :returns: ``None``。
        """

        self._now = _FixedClock().now()

    def now(self) -> datetime:
        """返回当前测试时间。

        :returns: 当前 UTC aware 时间。
        """

        return self._now

    def advance(self, seconds: float) -> None:
        """推进测试时间。

        :param seconds: 推进秒数。
        :returns: ``None``。
        :raises ValueError: 秒数不是正数时抛出。
        """

        if seconds <= 0.0:
            raise ValueError("seconds must be positive")
        self._now += timedelta(seconds=seconds)


class _SharedDeadlinePoller(WaitPoller):
    """同时阻塞 poll loop 与两个 observation provider 的测试 poller。"""

    def __init__(self, observation_runner: WaitObservationRunner) -> None:
        """初始化三组 barrier。

        :param observation_runner: supervisor-owned runner。
        :returns: ``None``。
        """

        self._observation_runner = observation_runner
        self.poller_entered = threading.Event()
        self.poller_release = threading.Event()
        self.provider_entered = (threading.Event(), threading.Event())
        self.provider_release = (threading.Event(), threading.Event())

    def poll_once(self) -> WaitPollOnceResult:
        """启动两个 provider observation 后阻塞 poller barrier。

        :returns: release 后的空 poll result。
        """

        coordinators = (
            threading.Thread(target=self._observe_first, daemon=True),
            threading.Thread(target=self._observe_second, daemon=True),
        )
        for coordinator in coordinators:
            coordinator.start()
        assert self.provider_entered[0].wait(1.0)
        assert self.provider_entered[1].wait(1.0)
        self.poller_entered.set()
        self.poller_release.wait()
        for coordinator in coordinators:
            coordinator.join(1.0)
        return WaitPollOnceResult(
            observed=0,
            not_ready=0,
            resolved=0,
            lost=0,
            abandoned=0,
            adapter_errors=0,
        )

    def _observe_first(self) -> None:
        """等待第一个 provider barrier。

        :returns: ``None``。
        """

        self._observation_runner.observe(
            self._block_first,
            timeout_seconds=10.0,
        )

    def _observe_second(self) -> None:
        """等待第二个 provider barrier。

        :returns: ``None``。
        """

        self._observation_runner.observe(
            self._block_second,
            timeout_seconds=10.0,
        )

    def _block_first(self) -> str:
        """阻塞第一个 provider invocation。

        :returns: release 后结果。
        """

        self.provider_entered[0].set()
        self.provider_release[0].wait()
        return "first"

    def _block_second(self) -> str:
        """阻塞第二个 provider invocation。

        :returns: release 后结果。
        """

        self.provider_entered[1].set()
        self.provider_release[1].wait()
        return "second"


class _SharedDeadlineFactory(WaitPollerFactory):
    """创建共享 observation runner poller 的测试 factory。"""

    def __init__(self) -> None:
        """初始化 created poller 引用。

        :returns: ``None``。
        """

        self.poller: _SharedDeadlinePoller | None = None

    def create_wait_poller(
        self,
        lifecycle_gate: WaitPollLifecycleGate,
        observation_runner: WaitObservationRunner,
    ) -> WaitPoller:
        """创建 barrier poller。

        :param lifecycle_gate: supervisor gate，本测试由 supervisor 直接治理。
        :param observation_runner: supervisor-owned runner。
        :returns: barrier poller。
        """

        del lifecycle_gate
        poller = _SharedDeadlinePoller(observation_runner)
        self.poller = poller
        return poller


def test_timeout_invalidates_token_and_late_result_cannot_publish() -> None:
    """timeout 先撤销 token，迟到 READY 只增加 dropped 计数。"""

    entered = threading.Event()
    release = threading.Event()
    runner = WaitObservationRunner(
        max_outstanding_adapter_calls=1,
        thread_name_prefix="wait-observation-test",
    )

    def operation() -> str:
        """等待显式 release 后返回结果。

        :returns: 测试结果文本。
        """

        entered.set()
        release.wait()
        return "late-ready"

    result = runner.observe(operation, timeout_seconds=0.01)
    assert entered.is_set()
    assert isinstance(result, WaitObservationTimedOut)
    timed_out = runner.diagnostics_snapshot()
    assert timed_out.live_count == 1
    assert timed_out.active_count == 0
    assert timed_out.invalidated_count == 1

    release.set()
    _wait_for_runner_count(runner, expected=0)
    finished = runner.diagnostics_snapshot()
    assert finished.dropped_count == 1
    assert finished.published_count == 0


def test_outstanding_cap_does_not_spawn_second_thread() -> None:
    """cap=1 时首个迟到线程存活期间第二次 observation 不 spawn。"""

    entered = threading.Event()
    release = threading.Event()
    second_called = threading.Event()
    runner = WaitObservationRunner(
        max_outstanding_adapter_calls=1,
        thread_name_prefix="wait-observation-cap",
    )

    def first_operation() -> str:
        """阻塞首个 invocation。

        :returns: 释放后的结果。
        """

        entered.set()
        release.wait()
        return "first"

    def second_operation() -> str:
        """记录错误 spawn。

        :returns: 第二个结果。
        """

        second_called.set()
        return "second"

    assert isinstance(
        runner.observe(first_operation, timeout_seconds=0.01),
        WaitObservationTimedOut,
    )
    assert entered.is_set()
    second = runner.observe(second_operation, timeout_seconds=0.01)
    assert isinstance(second, WaitObservationCapacityExceeded)
    assert not second_called.is_set()
    assert runner.diagnostics_snapshot().live_count == 1

    release.set()
    _wait_for_runner_count(runner, expected=0)
    third = runner.observe(second_operation, timeout_seconds=0.1)
    assert isinstance(third, WaitObservationPublished)
    assert third.value == "second"
    assert second_called.is_set()


def test_poll_observation_timeout_releases_with_backoff_and_late_result_cannot_resolve(
    tmp_path: Path,
) -> None:
    """poll observation timeout 释放 claim，迟到 Ready 无 durable authority。"""

    host = create_host_command_handle(_options(tmp_path))
    runner = WaitObservationRunner(
        max_outstanding_adapter_calls=1,
        thread_name_prefix="wait-observation-poll-timeout",
    )
    adapter = _BlockingAdapter()
    clock = _MutableClock()
    resolver = _RecordingPublicCommandResolver(host)
    try:
        seeded = _seed_waiting_run(host)
        poller = _poller(
            host,
            seeded.wait_id,
            adapter,
            runner,
            clock=clock,
            resolver=resolver,
        )

        result = poller.poll_once()
        wait = _read_wait(host._transaction_runner(), seeded.wait_id)
        assert adapter.poll_entered.is_set()
        assert result.lost == 0
        assert result.adapter_errors == 1
        assert wait.status is WaitRecordStatus.WAITING
        assert get_run(host, seeded.run_id).status is RunStatus.WAITING
        assert wait.poll_claim_id is None
        assert wait.poll_claim_owner_id is None
        assert wait.poll_claimed_at is None
        assert wait.poll_claim_expires_at is None
        assert wait.poll_backoff_attempt == 1
        assert wait.poll_next_observe_at == format_utc_timestamp(
            clock.now() + timedelta(seconds=0.01)
        )
        assert wait.poll_last_outcome is WaitPollLastOutcome.ADAPTER_ERROR
        assert wait.poll_last_error_code == "wait_observation_timeout"
        assert resolver.idempotency_keys == []
        assert runner.diagnostics_snapshot().invalidated_count == 1

        adapter.poll_release.set()
        _wait_for_runner_count(runner, expected=0)
        assert runner.diagnostics_snapshot().dropped_count == 1
        assert resolver.idempotency_keys == []
        assert (
            _read_wait(host._transaction_runner(), seeded.wait_id).status
            is WaitRecordStatus.WAITING
        )

        clock.advance(0.01)
        next_round = poller.poll_once()
        resolved_wait = _read_wait(host._transaction_runner(), seeded.wait_id)
        assert next_round.resolved == 1
        assert next_round.lost == 0
        assert len(resolver.idempotency_keys) == 1
        assert resolved_wait.status is WaitRecordStatus.RESOLVED
        assert get_run(host, seeded.run_id).status is RunStatus.RUNNING
    finally:
        adapter.poll_release.set()
        host.close()


def test_cancelled_abandon_timeout_releases_with_backoff_and_late_result_cannot_mark_terminal(
    tmp_path: Path,
) -> None:
    """abandon timeout 保持 CANCELLED retryable，迟到 Applied 不写终态。"""

    host = create_host_command_handle(_options(tmp_path))
    runner = WaitObservationRunner(
        max_outstanding_adapter_calls=1,
        thread_name_prefix="wait-observation-abandon-timeout",
    )
    adapter = _BlockingAdapter()
    clock = _MutableClock()
    resolver = _NoResolveResolver()
    try:
        seeded = _seed_waiting_run(host)
        cancel_run(
            host,
            seeded.run_id,
            CancelRunRequest(
                context=_context("cancel-before-abandon-timeout"),
                client_request_id="cancel-before-abandon-timeout",
                reason="user_cancel",
                mode=CancelMode.GRACEFUL,
            ),
        )
        poller = _poller(
            host,
            seeded.wait_id,
            adapter,
            runner,
            clock=clock,
            resolver=resolver,
        )

        first = poller.poll_once()
        wait = _read_wait(host._transaction_runner(), seeded.wait_id)
        assert adapter.abandon_entered.is_set()
        assert first.abandoned == 0
        assert first.adapter_errors == 1
        assert wait.status is WaitRecordStatus.CANCELLED
        assert wait.poll_abandoned_at is None
        assert wait.poll_claim_id is None
        assert wait.poll_claim_owner_id is None
        assert wait.poll_claimed_at is None
        assert wait.poll_claim_expires_at is None
        assert wait.poll_backoff_attempt == 1
        assert wait.poll_next_observe_at == format_utc_timestamp(
            clock.now() + timedelta(seconds=0.01)
        )
        assert wait.poll_last_outcome is WaitPollLastOutcome.ABANDON_ERROR
        assert wait.poll_last_error_code == "wait_abandon_timeout"
        assert poller.poll_once().observed == 0
        assert adapter.abandon_calls == 1
        assert resolver.calls == []

        adapter.abandon_release.set()
        _wait_for_runner_count(runner, expected=0)
        assert runner.diagnostics_snapshot().dropped_count == 1
        late_wait = _read_wait(host._transaction_runner(), seeded.wait_id)
        assert late_wait.status is WaitRecordStatus.CANCELLED
        assert late_wait.poll_abandoned_at is None

        clock.advance(0.01)
        next_round = poller.poll_once()
        terminal_wait = _read_wait(host._transaction_runner(), seeded.wait_id)
        assert next_round.abandoned == 1
        assert adapter.abandon_calls == 2
        assert terminal_wait.status is WaitRecordStatus.CANCELLED
        assert terminal_wait.poll_abandoned_at is not None
        assert terminal_wait.poll_last_outcome is WaitPollLastOutcome.ABANDONED
        assert resolver.calls == []
    finally:
        adapter.abandon_release.set()
        host.close()


def test_supervisor_close_uses_one_shared_deadline_and_stays_closing() -> None:
    """poller 与两个 provider 均阻塞时 close 预算不按线程数倍增。"""

    factory = _SharedDeadlineFactory()
    supervisor = WaitPollerSupervisor(
        poller_factory=factory,
        policy=_wait_poller_policy(
            poll_interval_seconds=1.0,
            adapter_call_timeout_seconds=10.0,
            close_drain_timeout_seconds=0.03,
            max_outstanding_adapter_calls=2,
        ),
        owner_id="shared-close-deadline",
    )
    supervisor.open()
    while factory.poller is None:
        threading.Event().wait(0.001)
    poller = factory.poller
    assert poller.poller_entered.wait(1.0)

    started = time.monotonic()
    supervisor.close()
    elapsed = time.monotonic() - started
    assert elapsed < 0.15
    assert supervisor.diagnostics_snapshot().status is WaitPollerLoopStatus.CLOSING
    assert supervisor.observation_diagnostics_snapshot().live_count == 2

    poller.poller_release.set()
    _wait_for_status(supervisor, WaitPollerLoopStatus.CLOSING)
    poller.provider_release[0].set()
    _wait_for_observation_count(supervisor, expected=1)
    assert supervisor.diagnostics_snapshot().status is WaitPollerLoopStatus.CLOSING
    poller.provider_release[1].set()
    _wait_for_status(supervisor, WaitPollerLoopStatus.STOPPED)
    assert supervisor.observation_diagnostics_snapshot().live_count == 0
    supervisor.close()


def _poller(
    host: HostCommandHandle,
    wait_id: str,
    adapter: _BlockingAdapter,
    runner: WaitObservationRunner,
    *,
    clock: WaitPollClock | None = None,
    resolver: WaitResolvePort | None = None,
) -> WaitPoller:
    """构造使用显式 observation runner 的 poller。

    :param host: 测试 Host command handle。
    :param wait_id: wait id。
    :param adapter: blocking adapter。
    :param runner: observation owner。
    :param clock: 可选测试时钟。
    :param resolver: 可选 wait resolve port。
    :returns: configured poller。
    """

    wait = _read_wait(host._transaction_runner(), wait_id)
    return WaitPoller(
        transaction_runner=host._transaction_runner(),
        adapter_registry=WaitPollAdapterRegistry(
            (
                WaitPollAdapterRegistration(
                    adapter_key=wait.adapter_key,
                    adapter=adapter,
                ),
            )
        ),
        resolver=resolver or _RecordingPublicCommandResolver(host),
        context=_context("bounded-observation-poller"),
        clock=clock or _FixedClock(),
        policy=_wait_poller_policy(
            adapter_call_timeout_seconds=0.01,
            close_drain_timeout_seconds=0.02,
            max_outstanding_adapter_calls=1,
        ),
        observation_runner=runner,
    )


def _wait_poller_policy(
    *,
    poll_interval_seconds: float = 0.01,
    adapter_call_timeout_seconds: float = 0.05,
    close_drain_timeout_seconds: float = 0.05,
    max_outstanding_adapter_calls: int = 2,
) -> WaitPollerRuntimePolicy:
    """构造字段完整的 bounded observation 测试 policy。

    :param poll_interval_seconds: supervisor 轮询间隔秒数。
    :param adapter_call_timeout_seconds: 单次 adapter 调用预算秒数。
    :param close_drain_timeout_seconds: close 共享预算秒数。
    :param max_outstanding_adapter_calls: 最大并发 adapter 调用数。
    :returns: 显式包含十二个部署字段的 policy。
    """

    return WaitPollerRuntimePolicy(
        enabled=True,
        poll_interval_seconds=poll_interval_seconds,
        claim_ttl_seconds=0.5,
        claim_batch_size=4,
        backoff_initial_delay_seconds=0.01,
        backoff_multiplier=2.0,
        backoff_max_delay_seconds=0.05,
        not_ready_observe_interval_seconds=0.01,
        idle_poll_interval_seconds=0.01,
        adapter_call_timeout_seconds=adapter_call_timeout_seconds,
        close_drain_timeout_seconds=close_drain_timeout_seconds,
        max_outstanding_adapter_calls=max_outstanding_adapter_calls,
    )


def _wait_for_runner_count(
    runner: WaitObservationRunner,
    *,
    expected: int,
) -> None:
    """等待 observation finally 移除 registry token。

    :param runner: observation runner。
    :param expected: 期望 live count。
    :returns: ``None``。
    :raises AssertionError: bounded deadline 内未达到目标时抛出。
    """

    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline:
        if runner.diagnostics_snapshot().live_count == expected:
            return
        threading.Event().wait(0.001)
    raise AssertionError("observation registry did not reach expected live count")


def _wait_for_observation_count(
    supervisor: WaitPollerSupervisor,
    *,
    expected: int,
) -> None:
    """等待 supervisor observation registry 达到目标 live count。

    :param supervisor: wait poller supervisor。
    :param expected: 目标 live count。
    :returns: ``None``。
    :raises AssertionError: bounded deadline 内未达到时抛出。
    """

    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline:
        if supervisor.observation_diagnostics_snapshot().live_count == expected:
            return
        threading.Event().wait(0.001)
    raise AssertionError("supervisor observation count did not converge")


def _wait_for_status(
    supervisor: WaitPollerSupervisor,
    expected: WaitPollerLoopStatus,
) -> None:
    """等待 supervisor status 收敛。

    :param supervisor: wait poller supervisor。
    :param expected: 期望状态。
    :returns: ``None``。
    :raises AssertionError: bounded deadline 内未达到时抛出。
    """

    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline:
        if supervisor.diagnostics_snapshot().status is expected:
            return
        threading.Event().wait(0.001)
    raise AssertionError(f"supervisor did not reach {expected.value}")
