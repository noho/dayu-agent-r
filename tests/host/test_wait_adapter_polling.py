"""Host wait poll adapter / poller 测试。"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from dayu.contracts.tool_result import ToolResultSuccess
from dayu.host import (
    CancelMode,
    CancelRunRequest,
    HostCommandHandle,
    ResolveWaitCompletedOutcome,
    ResolveWaitRequest,
    RunSnapshot,
    cancel_run,
    create_host_command_handle,
    resolve_wait,
)
from dayu.host.durable.state import WaitRecordRow, WaitRecordStatus
from dayu.host.wait_adapter import (
    WaitPollAdapter,
    WaitPollAdapterRegistration,
    WaitPollAdapterRegistry,
    WaitPollNotReady,
    WaitPollReady,
    WaitPollResult,
    WaitPoller,
)
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

    def poll_wait(self, wait_record: WaitRecordRow) -> WaitPollResult:
        """返回下一项 poll 结果。

        :param wait_record: wait record。
        :returns: poll 结果。
        """

        result = self._results[self.poll_count]
        self.poll_count += 1
        return result

    def abandon_wait(self, wait_record: WaitRecordRow) -> None:
        """记录被放弃 wait id。

        :param wait_record: wait record。
        :returns: ``None``。
        """

        self.abandoned.append(wait_record.wait_id)


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


def test_poll_adapter_not_ready_leaves_wait_active(
    tmp_path: Path,
) -> None:
    """poll adapter not-ready 不调用 resolve_wait。"""

    host = create_host_command_handle(_options(tmp_path))
    try:
        seeded = _seed_waiting_run(host)
        adapter = _SequenceAdapter((WaitPollNotReady(),))
        poller = _poller(host, adapter, seeded.wait_id)

        result = poller.poll_once()

        wait_record = _read_wait(host._transaction_runner(), seeded.wait_id)
        assert result.not_ready == 1
        assert adapter.poll_count == 1
        assert wait_record.status is WaitRecordStatus.WAITING
    finally:
        host.close()


def test_cancelled_poll_wait_is_abandoned_without_resolve(
    tmp_path: Path,
) -> None:
    """cancelled poll wait 只通知 adapter abandon，不调用 resolve_wait。"""

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

        wait_record = _read_wait(host._transaction_runner(), seeded.wait_id)
        assert result.abandoned == 1
        assert adapter.poll_count == 0
        assert adapter.abandoned == [seeded.wait_id]
        assert wait_record.status is WaitRecordStatus.CANCELLED
    finally:
        host.close()


def _poller(
    host: HostCommandHandle, adapter: WaitPollAdapter, wait_id: str
) -> WaitPoller:
    """构造测试 poller。

    :param host: Host command handle。
    :param adapter: poll adapter。
    :param wait_id: 测试 wait id。
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
    )
