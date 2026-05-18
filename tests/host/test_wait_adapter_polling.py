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
from dayu.host.durable.codec import sha256_digest_json
from dayu.host.durable.schema import TABLE_HOST_WAIT_RECORDS
from dayu.host.durable.state import WaitRecordRow, WaitRecordStatus
from dayu.host.durable.transaction import HostTransaction
from dayu.host.wait_adapter import (
    WaitPollAdapter,
    WaitPollAdapterRegistration,
    WaitPollAdapterRegistry,
    WaitPollLost,
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

    def abandon_wait(self, wait_record: WaitRecordRow) -> None:
        """记录 abandon wait 并抛出普通异常。

        :param wait_record: wait record。
        :returns: 不返回；始终抛出 ``ValueError``。
        :raises ValueError: 始终抛出，用于验证普通异常隔离。
        """

        self.abandoned.append(wait_record.wait_id)
        raise ValueError("adapter abandon failed")


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
        assert "wait poll adapter not registered; skipping" in caplog.text
        assert seeded.wait_id in caplog.text
        assert wait_record.adapter_key.value in caplog.text
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
