"""Host wait poller supervisor runtime 测试。"""

from __future__ import annotations

import logging
import math
import inspect
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TypedDict, cast

import pytest
from dayu.contracts.tool_result import ToolResultSuccess
from dayu.host import (
    ResolveWaitCompletedOutcome,
    ResolveWaitRequest,
    RunSnapshot,
    WaitAdapterKey,
    resolve_wait,
)
from dayu.host.api import HostCommandHandleOptions
from dayu.host.command import HostCommandHandle, create_host_command_handle, expire_wait
from dayu.host._wait_observation import WaitObservationRunner
from dayu.host.durable.state import WaitPollLastOutcome, WaitRecordRow, WaitRecordStatus
from dayu.host.wait_adapter import (
    WaitAdapterSnapshot,
    WaitExternalJobLifecycleAction,
    WaitExternalJobLifecycleApplied,
    WaitExternalJobLifecycleResult,
    WaitPollAdapter,
    WaitPollAdapterRegistration,
    WaitPollAdapterRegistry,
    WaitPollLifecycleGate,
    WaitPollOnceResult,
    WaitPoller,
    WaitPollerFactory,
    WaitPollerLoopStatus,
    WaitPollerRuntimePolicy,
    WaitPollerSupervisor,
    WaitPollNotReady,
    WaitPollClock,
    WaitPollReady,
    WaitPollResult,
)
from dayu.host.waiting import ExpireWaitInput, ExpireWaitResult
from tests.host.test_resolve_wait_command import (
    _context,
    _options,
    _read_wait,
    _seed_waiting_run,
)

_POLL_NOW = datetime(2026, 5, 16, 2, 0, 0, tzinfo=UTC)


class _PolicyKwargs(TypedDict):
    """测试用 runtime policy kwargs。"""

    poll_interval_seconds: float
    claim_ttl_seconds: float
    claim_batch_size: int
    backoff_initial_delay_seconds: float
    backoff_multiplier: float
    backoff_max_delay_seconds: float
    not_ready_observe_interval_seconds: float
    idle_poll_interval_seconds: float
    adapter_call_timeout_seconds: float
    close_drain_timeout_seconds: float
    max_outstanding_adapter_calls: int


class _FixedClock:
    """测试用固定 UTC 时钟。"""

    def now(self) -> datetime:
        """返回固定 UTC 时间。

        :returns: 固定时间。
        """

        return _POLL_NOW


class _ManualClock:
    """测试用可推进 UTC 时钟。"""

    def __init__(self) -> None:
        """初始化时钟。

        :returns: ``None``。
        """

        self._now = _POLL_NOW

    def now(self) -> datetime:
        """返回当前测试时间。

        :returns: 当前测试时间。
        """

        return self._now

    def advance(self, seconds: float) -> None:
        """推进测试时间。

        :param seconds: 推进秒数。
        :returns: ``None``。
        """

        self._now = self._now + timedelta(seconds=seconds)


class _RealtimeUtcClock:
    """测试用真实 UTC 时钟。"""

    def now(self) -> datetime:
        """返回当前真实 UTC 时间。

        :returns: 当前 UTC 时间。
        """

        return datetime.now(UTC)


class _PublicCommandResolver:
    """调用 public ``resolve_wait`` 的 resolver。"""

    def __init__(self, host: HostCommandHandle) -> None:
        """初始化 resolver。

        :param host: Host command handle。
        :returns: ``None``。
        """

        self._host = host

    def resolve_wait(self, wait_id: str, request: ResolveWaitRequest) -> RunSnapshot:
        """转发 poller 结果到 public resolve_wait。

        :param wait_id: wait id。
        :param request: resolve wait request。
        :returns: Run snapshot。
        """

        return resolve_wait(self._host, wait_id, request)

    def expire_wait(self, request: ExpireWaitInput) -> ExpireWaitResult:
        """执行 common expiry owner。

        :param request: expiry 输入。
        :returns: expiry transition。
        """

        return expire_wait(self._host, request)


class _ClosingWaitPoller(WaitPoller):
    """poll_once 后关闭私有 Host handle 的测试 poller。"""

    def __init__(self, *, host: HostCommandHandle, poller: WaitPoller) -> None:
        """初始化 poller wrapper。

        :param host: 当前 poller 私有 Host handle。
        :param poller: 实际 wait poller。
        :returns: ``None``。
        """

        self._host = host
        self._poller = poller

    def poll_once(self) -> WaitPollOnceResult:
        """执行 poll_once 并关闭私有 Host handle。

        :returns: 单轮 poll 结果。
        """

        try:
            return self._poller.poll_once()
        finally:
            self._host.close()


class _HandlePollerFactory:
    """在当前线程内创建 Host handle 和 wait poller 的测试 factory。"""

    def __init__(
        self,
        *,
        options: HostCommandHandleOptions,
        adapter_registry: WaitPollAdapterRegistry,
        policy: WaitPollerRuntimePolicy,
        clock: WaitPollClock,
        owner_id: str,
    ) -> None:
        """初始化 factory。

        :param options: Host command handle options。
        :param adapter_registry: poll adapter registry。
        :param policy: runtime policy。
        :param clock: 测试时钟。
        :param owner_id: poller owner id。
        :returns: ``None``。
        """

        self._options = options
        self._adapter_registry = adapter_registry
        self._policy = policy
        self._clock = clock
        self._owner_id = owner_id

    def create_wait_poller(
        self,
        lifecycle_gate: WaitPollLifecycleGate,
        observation_runner: WaitObservationRunner,
    ) -> WaitPoller:
        """在调用线程内创建 wait poller。

        :param lifecycle_gate: supervisor close gate。
        :param observation_runner: supervisor-owned observation runner。
        :returns: wait poller。
        """

        host = create_host_command_handle(self._options)
        poller = WaitPoller(
            transaction_runner=host._transaction_runner(),
            adapter_registry=self._adapter_registry,
            resolver=_PublicCommandResolver(host),
            context=_context("poller-runtime-thread"),
            policy=self._policy,
            clock=self._clock,
            lifecycle_gate=lifecycle_gate,
            observation_runner=observation_runner,
            owner_id=self._owner_id,
        )
        return _ClosingWaitPoller(host=host, poller=poller)


class _SequenceAdapter:
    """按预置序列返回 poll 结果的 adapter。"""

    def __init__(self, results: tuple[WaitPollResult, ...]) -> None:
        """初始化 adapter。

        :param results: poll 结果序列。
        :returns: ``None``。
        """

        self._results = results
        self.poll_count = 0
        self.poll_started_at: list[float] = []
        self.abandoned: list[str] = []

    def poll_wait(self, snapshot: WaitAdapterSnapshot) -> WaitPollResult:
        """返回下一项 poll 结果。

        :param snapshot: adapter snapshot。
        :returns: poll 结果。
        """

        del snapshot
        self.poll_started_at.append(time.monotonic())
        index = min(self.poll_count, len(self._results) - 1)
        self.poll_count += 1
        return self._results[index]

    def abandon_wait(
        self, snapshot: WaitAdapterSnapshot
    ) -> WaitExternalJobLifecycleResult:
        """记录 abandon wait。

        :param snapshot: adapter snapshot。
        :returns: applied lifecycle result。
        """

        self.abandoned.append(snapshot.resume_token)
        return WaitExternalJobLifecycleApplied(
            action=WaitExternalJobLifecycleAction.ABANDON,
            message="test_abandoned",
        )


class _BlockingReadyAdapter:
    """poll_wait 阻塞到测试释放后返回 ready。"""

    def __init__(self) -> None:
        """初始化同步事件。

        :returns: ``None``。
        """

        self.entered = threading.Event()
        self.release = threading.Event()
        self.poll_count = 0

    def poll_wait(self, snapshot: WaitAdapterSnapshot) -> WaitPollResult:
        """等待测试释放后返回 ready。

        :param snapshot: adapter snapshot。
        :returns: ready poll 结果。
        """

        del snapshot
        self.poll_count += 1
        self.entered.set()
        self.release.wait()
        return _ready_result()

    def abandon_wait(
        self, snapshot: WaitAdapterSnapshot
    ) -> WaitExternalJobLifecycleResult:
        """本测试 adapter 不处理 cancelled wait。

        :param snapshot: adapter snapshot。
        :returns: ``None``。
        :raises AssertionError: 被错误调用时抛出。
        """

        raise AssertionError(f"unexpected abandon {snapshot.resume_token}")


class _FailingAdapterRegistry(WaitPollAdapterRegistry):
    """resolve_adapter 时抛出 loop-level 异常的 registry。"""

    def __init__(self) -> None:
        """初始化 registry。

        :returns: ``None``。
        """

        super().__init__(())

    def resolve_adapter(self, adapter_key: WaitAdapterKey) -> WaitPollAdapter | None:
        """模拟 registry fatal failure。

        :param adapter_key: adapter key。
        :returns: 永不返回。
        :raises RuntimeError: 始终抛出。
        """

        del adapter_key
        raise RuntimeError("registry failed")


class _SelfClosingPoller(WaitPoller):
    """从 supervisor thread 内调用 close 的测试 poller。"""

    def __init__(
        self, *, close_call: Callable[[], None], entered: threading.Event
    ) -> None:
        """初始化测试 poller。

        :param close_call: supervisor close 调用。
        :param entered: poll_once 进入信号。
        :returns: ``None``。
        """

        self._close_call = close_call
        self._entered = entered

    def poll_once(self) -> WaitPollOnceResult:
        """在 poller thread 内调用 supervisor.close()。

        :returns: 不会正常返回；close 应抛出 ``RuntimeError``。
        :raises RuntimeError: supervisor 拒绝从自身线程 close 时抛出。
        """

        self._entered.set()
        self._close_call()
        return WaitPollOnceResult(
            observed=0,
            not_ready=0,
            resolved=0,
            lost=0,
            abandoned=0,
            adapter_errors=0,
        )


class _SelfClosingPollerFactory:
    """创建 self-close poller 的测试 factory。"""

    def __init__(self) -> None:
        """初始化 factory。

        :returns: ``None``。
        """

        self.entered = threading.Event()
        self._close_call: Callable[[], None] | None = None

    def bind_close_call(self, close_call: Callable[[], None]) -> None:
        """绑定 supervisor close 调用。

        :param close_call: supervisor close 调用。
        :returns: ``None``。
        """

        self._close_call = close_call

    def create_wait_poller(
        self,
        lifecycle_gate: WaitPollLifecycleGate,
        observation_runner: WaitObservationRunner,
    ) -> WaitPoller:
        """创建 self-close poller。

        :param lifecycle_gate: supervisor close gate，本测试不读取。
        :param observation_runner: supervisor-owned observation runner，本测试不读取。
        :returns: self-close poller。
        :raises RuntimeError: close 调用尚未绑定时抛出。
        """

        del lifecycle_gate, observation_runner
        if self._close_call is None:
            raise RuntimeError("close call is not bound")
        return _SelfClosingPoller(
            close_call=self._close_call,
            entered=self.entered,
        )


class _FailingOncePoller(WaitPoller):
    """第一次 poll 抛出异常，后续返回空轮结果的测试 poller。"""

    def __init__(self, factory: "_FailingOncePollerFactory") -> None:
        """初始化 poller。

        :param factory: 共享调用计数的 factory。
        :returns: ``None``。
        """

        self._factory = factory

    def poll_once(self) -> WaitPollOnceResult:
        """执行单轮 poll。

        :returns: 第二轮开始返回空 poll result。
        :raises RuntimeError: 第一轮抛出测试异常。
        """

        self._factory.calls += 1
        if self._factory.calls == 1:
            self._factory.failed_once.set()
            raise RuntimeError("single round failure")
        self._factory.recovered.set()
        return WaitPollOnceResult(
            observed=0,
            not_ready=0,
            resolved=0,
            lost=0,
            abandoned=0,
            adapter_errors=0,
        )


class _FailingOncePollerFactory:
    """创建单次失败 poller 的测试 factory。"""

    def __init__(self) -> None:
        """初始化 factory。

        :returns: ``None``。
        """

        self.calls = 0
        self.failed_once = threading.Event()
        self.recovered = threading.Event()

    def create_wait_poller(
        self,
        lifecycle_gate: WaitPollLifecycleGate,
        observation_runner: WaitObservationRunner,
    ) -> WaitPoller:
        """创建 poller。

        :param lifecycle_gate: supervisor close gate，本测试不需要读取。
        :param observation_runner: supervisor-owned observation runner，本测试不读取。
        :returns: 单次失败 poller。
        """

        del lifecycle_gate, observation_runner
        return _FailingOncePoller(self)


def test_supervisor_requires_explicit_poller_factory() -> None:
    """WaitPollerSupervisor 不再提供隐式 direct factory 默认路径。"""

    signature = inspect.signature(WaitPollerSupervisor)
    parameters = signature.parameters
    assert parameters["poller_factory"].default is inspect.Parameter.empty
    assert "transaction_runner" not in parameters
    assert "adapter_registry" not in parameters
    assert "resolver" not in parameters
    assert "context" not in parameters
    assert "clock" not in parameters


def test_runtime_policy_rejects_non_positive_values() -> None:
    """WaitPollerRuntimePolicy 拒绝非正数值。"""

    for field_name in (
        "poll_interval_seconds",
        "claim_ttl_seconds",
        "backoff_initial_delay_seconds",
        "backoff_multiplier",
        "backoff_max_delay_seconds",
        "not_ready_observe_interval_seconds",
        "idle_poll_interval_seconds",
        "adapter_call_timeout_seconds",
        "close_drain_timeout_seconds",
    ):
        values = _policy_kwargs()
        values[field_name] = 0.0
        try:
            WaitPollerRuntimePolicy(**values)
        except ValueError as exc:
            assert field_name in str(exc)
        else:
            raise AssertionError(f"{field_name} accepted non-positive value")
    values = _policy_kwargs()
    values["claim_batch_size"] = 0
    try:
        WaitPollerRuntimePolicy(**values)
    except ValueError as exc:
        assert "claim_batch_size" in str(exc)
    else:
        raise AssertionError("claim_batch_size accepted non-positive value")
    values = _policy_kwargs()
    values["max_outstanding_adapter_calls"] = 0
    with pytest.raises(ValueError, match="max_outstanding_adapter_calls"):
        WaitPollerRuntimePolicy(**values)


def test_runtime_policy_rejects_none_close_drain_timeout() -> None:
    """close_drain_timeout_seconds 不允许无界 ``None``。"""

    values = _policy_kwargs()
    values["close_drain_timeout_seconds"] = cast(float, None)

    with pytest.raises((TypeError, ValueError), match="close_drain_timeout_seconds"):
        WaitPollerRuntimePolicy(**values)


@pytest.mark.parametrize("invalid", (math.inf, -math.inf, math.nan))
def test_runtime_policy_rejects_non_finite_observation_budgets(
    invalid: float,
) -> None:
    """adapter 与 close budget 均拒绝 non-finite 数值。

    :param invalid: non-finite 测试值。
    """

    for field_name in (
        "adapter_call_timeout_seconds",
        "close_drain_timeout_seconds",
    ):
        values = _policy_kwargs()
        values[field_name] = invalid
        with pytest.raises(ValueError, match=field_name):
            WaitPollerRuntimePolicy(**values)


def test_drain_once_for_test_processes_ready_and_not_ready(
    tmp_path: Path,
) -> None:
    """drain_once_for_test 可处理 ready wait 与 not-ready wait。"""

    ready_options = _options(tmp_path / "ready")
    not_ready_options = _options(tmp_path / "not-ready")
    ready_host = create_host_command_handle(ready_options)
    not_ready_host = create_host_command_handle(not_ready_options)
    try:
        ready_seeded = _seed_waiting_run(ready_host)
        ready_adapter = _SequenceAdapter((_ready_result(),))
        ready_supervisor = _supervisor(
            ready_host, ready_adapter, ready_seeded.wait_id, options=ready_options
        )

        ready = ready_supervisor.drain_once_for_test()
        ready_wait = _read_wait(ready_host._transaction_runner(), ready_seeded.wait_id)

        not_ready_seeded = _seed_waiting_run(not_ready_host)
        not_ready_adapter = _SequenceAdapter((WaitPollNotReady(),))
        not_ready_supervisor = _supervisor(
            not_ready_host,
            not_ready_adapter,
            not_ready_seeded.wait_id,
            options=not_ready_options,
        )
        not_ready = not_ready_supervisor.drain_once_for_test()
        not_ready_wait = _read_wait(
            not_ready_host._transaction_runner(), not_ready_seeded.wait_id
        )

        assert ready.resolved == 1
        assert ready_wait.status is WaitRecordStatus.RESOLVED
        assert ready_supervisor.diagnostics_snapshot().resolved == 1
        assert not_ready.not_ready == 1
        assert not_ready_wait.status is WaitRecordStatus.WAITING
        assert not_ready_wait.poll_next_observe_at is not None
        assert not_ready_supervisor.diagnostics_snapshot().not_ready == 1
    finally:
        ready_host.close()
        not_ready_host.close()


def test_background_loop_respects_durable_backoff(tmp_path: Path) -> None:
    """background loop 重复运行但会跳过未到期 durable backoff。"""

    options = _options(tmp_path)
    host = create_host_command_handle(options)
    try:
        seeded = _seed_waiting_run(host)
        adapter = _SequenceAdapter((WaitPollNotReady(), WaitPollNotReady()))
        supervisor = _supervisor(host, adapter, seeded.wait_id, options=options)

        supervisor.open()
        _wait_until(lambda: adapter.poll_count == 1)
        time.sleep(0.05)
        supervisor.close()

        diagnostics = supervisor.diagnostics_snapshot()
        assert adapter.poll_count == 1
        assert diagnostics.poll_rounds >= 2
        assert diagnostics.not_ready == 1
    finally:
        host.close()


def test_close_wakes_idle_sleep_promptly(tmp_path: Path) -> None:
    """close 会唤醒 idle sleep，不等待完整 poll interval。"""

    options = _options(tmp_path)
    host = create_host_command_handle(options)
    try:
        supervisor = _supervisor_without_wait(
            host, _SequenceAdapter((WaitPollNotReady(),)), options=options
        )
        supervisor.open()
        _wait_until(lambda: supervisor.diagnostics_snapshot().poll_rounds >= 1)

        started = time.monotonic()
        supervisor.close()
        elapsed = time.monotonic() - started

        assert elapsed < 0.5
        assert supervisor.diagnostics_snapshot().status is WaitPollerLoopStatus.STOPPED
    finally:
        host.close()


def test_background_loop_uses_idle_interval_after_empty_round(tmp_path: Path) -> None:
    """background loop 空轮询后使用 idle 间隔，避免持续短间隔撞库。"""

    options = _options(tmp_path)
    policy_values = _policy_kwargs()
    policy_values["poll_interval_seconds"] = 0.01
    policy_values["idle_poll_interval_seconds"] = 0.2
    policy = WaitPollerRuntimePolicy(**policy_values)
    host = create_host_command_handle(options)
    supervisor: WaitPollerSupervisor | None = None
    try:
        supervisor = _supervisor_without_wait(
            host,
            _SequenceAdapter((WaitPollNotReady(),)),
            options=options,
            policy=policy,
        )

        supervisor.open()
        _wait_until(lambda: supervisor.diagnostics_snapshot().poll_rounds >= 1)
        time.sleep(0.05)

        assert supervisor.diagnostics_snapshot().poll_rounds == 1
    finally:
        if supervisor is not None:
            supervisor.close()
        host.close()


def test_wakeup_interrupts_idle_after_new_wait_is_created(tmp_path: Path) -> None:
    """新 wait 创建后 wakeup 可打断 idle sleep 并立即 observe。"""

    options = _options(tmp_path)
    policy_values = _policy_kwargs()
    policy_values["idle_poll_interval_seconds"] = 0.5
    policy = WaitPollerRuntimePolicy(**policy_values)
    host = create_host_command_handle(options)
    adapter = _SequenceAdapter((WaitPollNotReady(),))
    adapter_registry = WaitPollAdapterRegistry(
        (
            WaitPollAdapterRegistration(
                adapter_key=WaitAdapterKey("poll:long-tool"),
                adapter=adapter,
            ),
        )
    )
    supervisor = WaitPollerSupervisor(
        poller_factory=_handle_poller_factory(
            options=options,
            adapter_registry=adapter_registry,
            owner_id="poller-runtime-new-wait",
            policy=policy,
        ),
        policy=policy,
        owner_id="poller-runtime-new-wait",
    )
    try:
        supervisor.open()
        _wait_until(lambda: supervisor.diagnostics_snapshot().poll_rounds >= 1)

        _seed_waiting_run(host)
        started = time.monotonic()
        supervisor.wakeup()
        _wait_until(lambda: adapter.poll_count == 1)

        assert time.monotonic() - started < 0.3
    finally:
        supervisor.close()
        host.close()


def test_pure_poll_observes_ready_after_not_ready_policy_cadence(
    tmp_path: Path,
) -> None:
    """无 wakeup 时，not-ready 后也按 policy cadence 观察 ready。"""

    options = _options(tmp_path)
    policy_values = _policy_kwargs()
    policy_values["poll_interval_seconds"] = 0.2
    policy_values["not_ready_observe_interval_seconds"] = 0.03
    policy_values["idle_poll_interval_seconds"] = 0.5
    policy = WaitPollerRuntimePolicy(**policy_values)
    clock = _ManualClock()
    host = create_host_command_handle(options)
    supervisor: WaitPollerSupervisor | None = None
    try:
        seeded = _seed_waiting_run(host)
        adapter = _SequenceAdapter((WaitPollNotReady(), _ready_result()))
        supervisor = _supervisor(
            host,
            adapter,
            seeded.wait_id,
            options=options,
            policy=policy,
            clock=clock,
        )

        first = supervisor.drain_once_for_test()
        early = supervisor.drain_once_for_test()
        clock.advance(0.03)
        second = supervisor.drain_once_for_test()

        wait_record = _read_wait(host._transaction_runner(), seeded.wait_id)
        assert first.not_ready == 1
        assert first.next_poll_delay_seconds == pytest.approx(0.03)
        assert early.observed == 0
        assert adapter.poll_count == 2
        assert second.resolved == 1
        assert wait_record.status is WaitRecordStatus.RESOLVED
    finally:
        if supervisor is not None:
            supervisor.close()
        host.close()


def test_background_loop_uses_not_ready_due_before_poll_interval(
    tmp_path: Path,
) -> None:
    """not-ready cadence 小于 poll interval 时，后台 loop 按 next due 复查。"""

    options = _options(tmp_path)
    policy_values = _policy_kwargs()
    policy_values["poll_interval_seconds"] = 0.5
    policy_values["not_ready_observe_interval_seconds"] = 0.01
    policy_values["idle_poll_interval_seconds"] = 0.5
    policy = WaitPollerRuntimePolicy(**policy_values)
    host = create_host_command_handle(options)
    supervisor: WaitPollerSupervisor | None = None
    try:
        seeded = _seed_waiting_run(host)
        adapter = _SequenceAdapter((WaitPollNotReady(), _ready_result()))
        supervisor = _supervisor(
            host,
            adapter,
            seeded.wait_id,
            options=options,
            policy=policy,
            clock=_RealtimeUtcClock(),
        )

        supervisor.open()
        _wait_until(lambda: adapter.poll_count == 1)
        _wait_until(
            lambda: _read_wait(host._transaction_runner(), seeded.wait_id).status
            is WaitRecordStatus.RESOLVED
        )

        wait_record = _read_wait(host._transaction_runner(), seeded.wait_id)
        elapsed_seconds = adapter.poll_started_at[1] - adapter.poll_started_at[0]
        assert elapsed_seconds < 0.3
        assert wait_record.status is WaitRecordStatus.RESOLVED
    finally:
        if supervisor is not None:
            supervisor.close()
        host.close()


def test_close_is_idempotent(tmp_path: Path) -> None:
    """close 可重复调用。"""

    options = _options(tmp_path)
    host = create_host_command_handle(options)
    try:
        supervisor = _supervisor_without_wait(
            host, _SequenceAdapter((WaitPollNotReady(),)), options=options
        )

        supervisor.open()
        supervisor.close()
        first_closed = supervisor.diagnostics_snapshot()
        supervisor.close()
        second_closed = supervisor.diagnostics_snapshot()

        assert first_closed.status is WaitPollerLoopStatus.STOPPED
        assert second_closed.status is WaitPollerLoopStatus.STOPPED
    finally:
        host.close()


def test_close_before_resolve_skips_result_and_leaves_wait_retryable(
    tmp_path: Path,
) -> None:
    """adapter 返回后 close gate 已关闭时跳过 resolve 并释放为 retryable。"""

    options = _options(tmp_path)
    host = create_host_command_handle(options)
    try:
        seeded = _seed_waiting_run(host)
        adapter = _BlockingReadyAdapter()
        supervisor = _supervisor(host, adapter, seeded.wait_id, options=options)

        supervisor.open()
        assert adapter.entered.wait(1.0)
        close_thread = threading.Thread(target=supervisor.close)
        close_thread.start()
        _wait_until(supervisor.is_closed)
        adapter.release.set()
        close_thread.join(1.0)

        wait_record = _read_wait(host._transaction_runner(), seeded.wait_id)
        diagnostics = supervisor.diagnostics_snapshot()
        assert not close_thread.is_alive()
        assert wait_record.status is WaitRecordStatus.WAITING
        assert wait_record.poll_claim_id is None
        assert wait_record.poll_last_outcome is WaitPollLastOutcome.SHUTDOWN_SKIPPED
        assert wait_record.poll_next_observe_at is not None
        assert diagnostics.resolved == 0
        assert diagnostics.shutdown_skipped == 1
    finally:
        host.close()


def test_close_drain_timeout_records_and_waits_for_inflight_poll(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """close shared budget 到期后有界返回并保持 CLOSING。"""

    options = _options(tmp_path)
    host = create_host_command_handle(options)
    try:
        seeded = _seed_waiting_run(host)
        adapter = _BlockingReadyAdapter()
        supervisor = _supervisor(host, adapter, seeded.wait_id, options=options)

        supervisor.open()
        assert adapter.entered.wait(1.0)
        with caplog.at_level(logging.WARNING, logger="dayu.host.wait_adapter"):
            close_thread = threading.Thread(target=supervisor.close)
            close_thread.start()
            _wait_until(
                lambda: supervisor.diagnostics_snapshot().close_drain_timeouts == 1
            )
            close_thread.join(1.0)
            assert not close_thread.is_alive()
            assert (
                supervisor.diagnostics_snapshot().status
                is WaitPollerLoopStatus.CLOSING
            )
            _read_wait(host._transaction_runner(), seeded.wait_id)
            adapter.release.set()
            _wait_until(
                lambda: supervisor.diagnostics_snapshot().status
                is WaitPollerLoopStatus.STOPPED
            )

        assert "wait poller close drain timeout" in caplog.text
        assert supervisor.diagnostics_snapshot().status is WaitPollerLoopStatus.STOPPED
    finally:
        host.close()


def test_close_with_finite_budget_after_inflight_release_has_no_timeout_diagnostic(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """in-flight 已释放时 finite close budget 不产生 timeout diagnostic。"""

    options = _options(tmp_path)
    host = create_host_command_handle(options)
    try:
        seeded = _seed_waiting_run(host)
        adapter = _BlockingReadyAdapter()
        policy = _runtime_policy(close_drain_timeout_seconds=0.2)
        supervisor = _supervisor(
            host,
            adapter,
            seeded.wait_id,
            options=options,
            policy=policy,
        )

        supervisor.open()
        assert adapter.entered.wait(1.0)
        adapter.release.set()
        with caplog.at_level(logging.WARNING, logger="dayu.host.wait_adapter"):
            supervisor.close()

        diagnostics = supervisor.diagnostics_snapshot()
        assert diagnostics.status is WaitPollerLoopStatus.STOPPED
        assert diagnostics.close_drain_timeouts == 0
        assert "wait poller close drain timeout" not in caplog.text
    finally:
        host.close()


def test_close_from_supervisor_thread_marks_failed_diagnostics(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """supervisor thread 自身调用 close 时 fail fast 并记录 fatal diagnostics。"""

    factory = _SelfClosingPollerFactory()
    supervisor = WaitPollerSupervisor(
        poller_factory=factory,
        policy=_runtime_policy(),
        owner_id="poller-runtime-self-close",
    )
    factory.bind_close_call(supervisor.close)

    with caplog.at_level(logging.ERROR, logger="dayu.host.wait_adapter"):
        supervisor.open()
        assert factory.entered.wait(1.0)
        _wait_until(
            lambda: supervisor.diagnostics_snapshot().status
            is WaitPollerLoopStatus.FAILED
        )

    diagnostics = supervisor.diagnostics_snapshot()
    assert diagnostics.fatal_errors == 1
    assert diagnostics.round_errors == 0
    assert diagnostics.last_error_type == "_WaitPollerSelfCloseError"
    assert diagnostics.last_error_message is not None
    assert "cannot close from its own thread" in diagnostics.last_error_message
    assert "wait poller loop failed" in caplog.text
    supervisor.close()


def test_single_round_exception_is_diagnosed_and_next_round_continues(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """单轮 transient exception 只记录诊断，supervisor 继续下一轮。"""

    factory = _FailingOncePollerFactory()
    supervisor = WaitPollerSupervisor(
        poller_factory=factory,
        policy=_runtime_policy(),
        owner_id="poller-runtime-round-error",
    )

    with caplog.at_level(logging.ERROR, logger="dayu.host.wait_adapter"):
        supervisor.open()
        assert factory.failed_once.wait(1.0)
        assert factory.recovered.wait(1.0)

    diagnostics = supervisor.diagnostics_snapshot()
    assert diagnostics.status is WaitPollerLoopStatus.RUNNING
    assert diagnostics.round_errors == 1
    assert diagnostics.fatal_errors == 0
    assert diagnostics.last_error_type == "RuntimeError"
    assert "wait poller round failed; retrying" in caplog.text
    supervisor.close()


def _ready_result() -> WaitPollReady:
    """构造 ready poll result。

    :returns: ready result。
    """

    return WaitPollReady(
        ResolveWaitCompletedOutcome(
            result=ToolResultSuccess(ok=True, value={"ready": True}, meta=None),
            payload_ref=None,
        )
    )


def _supervisor(
    host: HostCommandHandle,
    adapter: WaitPollAdapter,
    wait_id: str,
    *,
    options: HostCommandHandleOptions,
    policy: WaitPollerRuntimePolicy | None = None,
    clock: WaitPollClock | None = None,
) -> WaitPollerSupervisor:
    """构造测试 supervisor。

    :param host: Host command handle。
    :param adapter: poll adapter。
    :param wait_id: wait record id。
    :param options: 线程内 Host handle factory 使用的 options。
    :param policy: runtime policy；缺省使用测试默认 policy。
    :param clock: 测试时钟；缺省使用固定测试时钟。
    :returns: supervisor。
    """

    resolved_policy = policy if policy is not None else _runtime_policy()
    adapter_registry = WaitPollAdapterRegistry(
        (
            WaitPollAdapterRegistration(
                adapter_key=_read_wait(host._transaction_runner(), wait_id).adapter_key,
                adapter=adapter,
            ),
        )
    )
    return WaitPollerSupervisor(
        poller_factory=_handle_poller_factory(
            options=options,
            adapter_registry=adapter_registry,
            owner_id="poller-runtime-test",
            policy=resolved_policy,
            clock=clock,
        ),
        policy=resolved_policy,
        owner_id="poller-runtime-test",
    )


def _supervisor_without_wait(
    host: HostCommandHandle,
    adapter: WaitPollAdapter,
    *,
    options: HostCommandHandleOptions,
    policy: WaitPollerRuntimePolicy | None = None,
) -> WaitPollerSupervisor:
    """构造没有可 poll wait 的测试 supervisor。

    :param host: Host command handle。
    :param adapter: poll adapter。
    :param options: 线程内 Host handle factory 使用的 options。
    :param policy: runtime policy；缺省使用测试默认 policy。
    :returns: supervisor。
    """

    resolved_policy = policy if policy is not None else _runtime_policy()
    adapter_registry = WaitPollAdapterRegistry(
        (
            WaitPollAdapterRegistration(
                adapter_key=WaitAdapterKey("poll:runtime-idle"),
                adapter=adapter,
            ),
        )
    )
    return WaitPollerSupervisor(
        poller_factory=_handle_poller_factory(
            options=options,
            adapter_registry=adapter_registry,
            owner_id="poller-runtime-idle",
            policy=resolved_policy,
        ),
        policy=resolved_policy,
        owner_id="poller-runtime-idle",
    )


def _handle_poller_factory(
    *,
    options: HostCommandHandleOptions,
    adapter_registry: WaitPollAdapterRegistry,
    owner_id: str,
    policy: WaitPollerRuntimePolicy,
    clock: WaitPollClock | None = None,
) -> WaitPollerFactory:
    """构造线程内 Host handle poller factory。

    :param options: Host command handle options。
    :param adapter_registry: poll adapter registry。
    :param owner_id: poller owner id。
    :param policy: runtime policy。
    :param clock: 测试时钟；缺省使用固定测试时钟。
    :returns: poller factory。
    """

    return _HandlePollerFactory(
        options=options,
        adapter_registry=adapter_registry,
        policy=policy,
        clock=clock if clock is not None else _FixedClock(),
        owner_id=owner_id,
    )


def _runtime_policy(
    *, close_drain_timeout_seconds: float = 0.02
) -> WaitPollerRuntimePolicy:
    """构造测试用 runtime policy。

    :param close_drain_timeout_seconds: finite-positive close shared budget 秒数。
    :returns: runtime policy。
    """

    values = _policy_kwargs()
    values["close_drain_timeout_seconds"] = close_drain_timeout_seconds
    return WaitPollerRuntimePolicy(**values)


def _policy_kwargs() -> _PolicyKwargs:
    """构造测试用 policy kwargs。

    :returns: policy kwargs。
    """

    return {
        "poll_interval_seconds": 0.01,
        "claim_ttl_seconds": 0.5,
        "claim_batch_size": 4,
        "backoff_initial_delay_seconds": 10.0,
        "backoff_multiplier": 2.0,
        "backoff_max_delay_seconds": 20.0,
        "not_ready_observe_interval_seconds": 0.01,
        "idle_poll_interval_seconds": 0.05,
        "adapter_call_timeout_seconds": 0.05,
        "close_drain_timeout_seconds": 0.02,
        "max_outstanding_adapter_calls": 4,
    }


def _wait_until(
    predicate: Callable[[], bool], *, timeout_seconds: float = 1.0
) -> None:
    """等待 predicate 在短时间内成立。

    :param predicate: 待观察条件。
    :param timeout_seconds: 最长等待秒数。
    :returns: ``None``。
    :raises AssertionError: 超时仍未成立时抛出。
    """

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.005)
    raise AssertionError("condition did not become true")
