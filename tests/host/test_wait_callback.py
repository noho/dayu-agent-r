"""Host wait callback adapter 测试。"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

from dayu.contracts.tool_result import ToolResultSuccess
from dayu.host import (
    AuthorizationClaim,
    CancelMode,
    CancelRunRequest,
    ResolveWaitCompletedOutcome,
    ResolveWaitOutcome,
    ResolveWaitRequest,
    WaitCallbackAdapterStatus,
    WaitCallbackAuthAccepted,
    WaitCallbackAuthInput,
    WaitCallbackAuthRejected,
    WaitCallbackAuthResult,
    WaitCallbackCompletionEnvelope,
    WaitCallbackStoredWaitState,
    WaitCallbackStoredWaitStatus,
    callback_payload_digest,
    cancel_run,
    resolve_wait,
)
from dayu.host.admission import PendingDispatchRecord, create_host_admission_service
from dayu.host.api import HostCallContext
from dayu.host.command import (
    HostCommandHandle,
    HostCommandWaitCallbackPort,
    create_host_command_handle,
)
from dayu.host.durable.codec import format_utc_timestamp
from dayu.host.durable.schema import TABLE_HOST_WAIT_RECORDS
from dayu.host.durable.state import (
    WaitRecordRow,
    WaitRecordStatus,
    read_wait_record_by_id,
)
from dayu.host.durable.transaction import HostTransaction
from dayu.host.wait_callback import (
    CallbackWaitResolvePort,
    CallbackWaitResolveResult,
    DefaultWaitCallbackAdapter,
    WaitCallbackStateReadPort,
)
from dayu.host.waiting import _wait_resolution_digest
from tests.host.test_resolve_wait_command import (
    _OBSERVED,
    _OBSERVED_REPLAY,
    _completed_request,
    _context,
    _events,
    _events_by_type,
    _lost_request,
    _options,
    _seed_waiting_run,
)

_COMPLETED_AT = datetime(2026, 5, 16, 1, 5, 6, tzinfo=UTC)
_COMPLETED_AT_REPLAY = datetime(2026, 5, 16, 1, 7, 9, tzinfo=UTC)
_ZERO_DIGEST = "sha256:0000000000000000000000000000000000000000000000000000000000000000"


@dataclass(slots=True)
class _AcceptingAuthenticator:
    """测试用认证通过器。"""

    calls: int = 0

    def authenticate_callback(
        self, request: WaitCallbackAuthInput
    ) -> WaitCallbackAuthResult:
        """记录认证调用并返回通过。

        :param request: 认证输入。
        :returns: 认证通过结果。
        """

        self.calls += 1
        return WaitCallbackAuthAccepted(
            actor="callback-provider",
            authorization_claims=request.presented_claims,
        )


@dataclass(slots=True)
class _RejectingAuthenticator:
    """测试用认证拒绝器。"""

    calls: int = 0

    def authenticate_callback(
        self, request: WaitCallbackAuthInput
    ) -> WaitCallbackAuthResult:
        """记录认证调用并返回拒绝。

        :param request: 认证输入。
        :returns: 认证拒绝结果。
        """

        del request
        self.calls += 1
        return WaitCallbackAuthRejected(
            reason_code="invalid_credential",
            message="callback credential is invalid",
            retryable=False,
        )


@dataclass(slots=True)
class _CountingWakeupPort:
    """测试用 dispatch wakeup 计数器。"""

    dispatch_wakes: int = 0
    queue_wakes: int = 0

    def wake_dispatch(self, record: PendingDispatchRecord) -> None:
        """记录 dispatch wakeup。

        :param record: pending dispatch 摘要。
        :returns: ``None``。
        """

        del record
        self.dispatch_wakes += 1

    def wake_queue_promotion(self, session_id: str) -> None:
        """记录 queue promotion wakeup。

        :param session_id: Session id。
        :returns: ``None``。
        """

        del session_id
        self.queue_wakes += 1


@dataclass(slots=True)
class _FakeStateReader(WaitCallbackStateReadPort):
    """测试用 wait state reader。"""

    state: WaitCallbackStoredWaitState | None
    calls: int = 0

    def read_wait_state(self, wait_id: str) -> WaitCallbackStoredWaitState | None:
        """返回预置 wait state。

        :param wait_id: wait id。
        :returns: 预置 wait state。
        """

        del wait_id
        self.calls += 1
        return self.state


@dataclass(slots=True)
class _FailIfCalledResolver(CallbackWaitResolvePort):
    """被调用即失败的 resolver。"""

    calls: int = 0

    def resolve_callback_wait(
        self,
        wait_id: str,
        request: ResolveWaitRequest,
        context: HostCallContext,
    ) -> CallbackWaitResolveResult:
        """记录错误调用并失败。

        :param wait_id: wait id。
        :param request: resolve request。
        :param context: Host call context。
        :returns: 不返回。
        :raises AssertionError: 始终抛出。
        """

        del wait_id, request, context
        self.calls += 1
        raise AssertionError("resolver should not be called")


def test_callback_completed_resumes_with_same_event_sequence_as_direct_resolve(
    tmp_path: Path,
) -> None:
    """completed callback 复用 direct resolve 的 resume 事件序列。"""

    direct_host = create_host_command_handle(_options(tmp_path / "direct"))
    callback_host = create_host_command_handle(_options(tmp_path / "callback"))
    try:
        direct_seeded = _seed_waiting_run(direct_host)
        callback_seeded = _seed_waiting_run(callback_host)

        direct_snapshot = resolve_wait(
            direct_host,
            direct_seeded.wait_id,
            _completed_request("same-sequence"),
        )
        callback_result = _real_adapter(callback_host).resolve_callback(
            _envelope(callback_seeded.wait_id, "same-sequence")
        )

        direct_events = _events(direct_host._transaction_runner())
        callback_events = _events(callback_host._transaction_runner())
        assert callback_result.status is WaitCallbackAdapterStatus.ACCEPTED
        assert callback_result.run is not None
        assert callback_result.run.current_attempt_id != callback_seeded.attempt_id
        assert direct_snapshot.current_attempt_id != direct_seeded.attempt_id
        assert [event.event_type for event in callback_events[-4:]] == [
            event.event_type for event in direct_events[-4:]
        ]
    finally:
        direct_host.close()
        callback_host.close()


def test_callback_digest_matches_resolve_wait_digest_for_completed_and_lost() -> None:
    """callback digest 与 resolve_wait digest 对 completed/lost outcome 保持同源。"""

    completed_wait_id = "wait-digest-completed"
    completed_request = _completed_request("digest-completed")
    completed_envelope = _envelope(
        completed_wait_id,
        completed_request.idempotency_key,
        outcome=completed_request.outcome,
    )
    lost_wait_id = "wait-digest-lost"
    lost_request = _lost_request("digest-lost")
    lost_envelope = _envelope(
        lost_wait_id,
        lost_request.idempotency_key,
        outcome=lost_request.outcome,
    )

    assert callback_payload_digest(completed_envelope) == _wait_resolution_digest(
        completed_wait_id,
        completed_request,
    )
    assert callback_payload_digest(lost_envelope) == _wait_resolution_digest(
        lost_wait_id,
        lost_request,
    )


def test_callback_accept_wakes_dispatch_once_and_replay_does_not_wake_again(
    tmp_path: Path,
) -> None:
    """accepted callback 唤醒一次 dispatch，replay 不重复唤醒。"""

    host = create_host_command_handle(_options(tmp_path))
    wakeup = _install_counting_wakeup(host)
    try:
        seeded = _seed_waiting_run(host)
        adapter = _real_adapter(host)
        envelope = _envelope(seeded.wait_id, "callback-replay")

        first = adapter.resolve_callback(envelope)
        before_events = _events(host._transaction_runner())
        replay = adapter.resolve_callback(
            replace(
                envelope,
                observed_at=_OBSERVED_REPLAY,
                completed_at=_COMPLETED_AT_REPLAY,
            )
        )
        after_events = _events(host._transaction_runner())

        assert first.status is WaitCallbackAdapterStatus.ACCEPTED
        assert replay.status is WaitCallbackAdapterStatus.REPLAYED
        assert replay.idempotent_replay is True
        assert after_events == before_events
        assert wakeup.dispatch_wakes == 1
    finally:
        host.close()


def test_callback_same_key_changed_outcome_returns_idempotency_conflict(
    tmp_path: Path,
) -> None:
    """同幂等键不同 outcome 返回 idempotency conflict。"""

    host = create_host_command_handle(_options(tmp_path))
    try:
        seeded = _seed_waiting_run(host)
        adapter = _real_adapter(host)
        envelope = _envelope(seeded.wait_id, "callback-conflict")
        conflict = _envelope(
            seeded.wait_id,
            "callback-conflict",
            outcome=ResolveWaitCompletedOutcome(
                result=ToolResultSuccess(
                    ok=True,
                    value={"answer": "changed"},
                    meta=None,
                ),
                payload_ref=None,
            ),
        )

        accepted = adapter.resolve_callback(envelope)
        before_events = _events(host._transaction_runner())
        result = adapter.resolve_callback(conflict)

        assert accepted.status is WaitCallbackAdapterStatus.ACCEPTED
        assert result.status is WaitCallbackAdapterStatus.IDEMPOTENCY_CONFLICT
        assert _events(host._transaction_runner()) == before_events
    finally:
        host.close()


def test_unknown_wait_returns_unknown_wait_without_resolver_call() -> None:
    """unknown wait 在预读阶段返回 UNKNOWN_WAIT。"""

    resolver = _FailIfCalledResolver()
    adapter = DefaultWaitCallbackAdapter(
        authenticator=_AcceptingAuthenticator(),
        state_reader=_FakeStateReader(None),
        resolver=resolver,
    )

    result = adapter.resolve_callback(_envelope("wait-missing", "unknown"))

    assert result.status is WaitCallbackAdapterStatus.UNKNOWN_WAIT
    assert resolver.calls == 0


def test_pre_existing_cancelled_wait_maps_to_late_cancelled(tmp_path: Path) -> None:
    """稳定预读到 cancelled wait 时 late callback 返回 LATE_WAIT_CANCELLED。"""

    host = create_host_command_handle(_options(tmp_path))
    try:
        seeded = _seed_waiting_run(host)
        cancel_run(
            host,
            seeded.run_id,
            CancelRunRequest(
                context=_context("cancel-before-callback"),
                client_request_id="cancel-before-callback",
                reason="user_cancel",
                mode=CancelMode.GRACEFUL,
            ),
        )

        result = _real_adapter(host).resolve_callback(
            _envelope(seeded.wait_id, "late-cancelled")
        )

        assert result.status is WaitCallbackAdapterStatus.LATE_WAIT_CANCELLED
    finally:
        host.close()


def test_pre_existing_lost_wait_maps_to_late_lost(tmp_path: Path) -> None:
    """稳定预读到 lost wait 时 late callback 返回 LATE_WAIT_LOST。"""

    host = create_host_command_handle(_options(tmp_path))
    try:
        seeded = _seed_waiting_run(host)
        resolve_wait(host, seeded.wait_id, _lost_request("lost-original"))

        result = _real_adapter(host).resolve_callback(
            _envelope(seeded.wait_id, "late-lost")
        )

        assert result.status is WaitCallbackAdapterStatus.LATE_WAIT_LOST
    finally:
        host.close()


def test_expired_callback_is_rejected_by_resolve_owner(
    tmp_path: Path,
) -> None:
    """deadline 已过的 callback 由 resolve owner 拒绝并记录 late diagnostic。"""

    host = create_host_command_handle(_options(tmp_path))
    try:
        seeded = _seed_waiting_run(host)
        _set_wait_deadline(
            host,
            seeded.wait_id,
            datetime(2026, 5, 16, 1, 5, 5, tzinfo=UTC),
        )
        result = _real_adapter(host).resolve_callback(
            _envelope(seeded.wait_id, "stale-callback")
        )

        wait_record = host._transaction_runner().run_read(
            lambda transaction: _read_wait_row(transaction, seeded.wait_id)
        )
        late_events = _events_by_type(
            _events(host._transaction_runner()), "WAIT_LATE_RESULT_REJECTED"
        )
        assert result.status is WaitCallbackAdapterStatus.INVALID_WAIT_STATE
        assert wait_record is not None
        assert wait_record.status is WaitRecordStatus.FAILED
        assert len(late_events) == 1
    finally:
        host.close()


def test_wait_without_deadline_or_expires_is_not_stale(tmp_path: Path) -> None:
    """无 deadline/expires 的 wait 不因 completed_at 被判 stale。"""

    host = create_host_command_handle(_options(tmp_path))
    try:
        seeded = _seed_waiting_run(host)

        result = _real_adapter(host).resolve_callback(
            _envelope(seeded.wait_id, "no-deadline")
        )

        assert result.status is WaitCallbackAdapterStatus.ACCEPTED
    finally:
        host.close()


def test_invalid_stored_deadline_is_failed_closed_by_resolve_owner(
    tmp_path: Path,
) -> None:
    """非法持久化 deadline 由 resolve owner fail closed，不由 callback 预解析。"""

    host = create_host_command_handle(_options(tmp_path))
    try:
        seeded = _seed_waiting_run(host)
        _set_wait_deadline_text(host, seeded.wait_id, "not-a-timestamp")
        before_events = _events(host._transaction_runner())

        result = _real_adapter(host).resolve_callback(
            _envelope(seeded.wait_id, "invalid-deadline")
        )

        wait_record = host._transaction_runner().run_read(
            lambda transaction: _read_wait_row(transaction, seeded.wait_id)
        )
        assert result.status is WaitCallbackAdapterStatus.INVALID_WAIT_STATE
        assert wait_record is not None
        assert wait_record.status is WaitRecordStatus.WAITING
        assert _events(host._transaction_runner()) == before_events
    finally:
        host.close()


def test_digest_mismatch_returns_without_resolver_call() -> None:
    """payload digest mismatch 不调用 resolver。"""

    resolver = _FailIfCalledResolver()
    adapter = DefaultWaitCallbackAdapter(
        authenticator=_AcceptingAuthenticator(),
        state_reader=_FakeStateReader(
            WaitCallbackStoredWaitState(
                status=WaitCallbackStoredWaitStatus.WAITING,
                deadline_at=None,
                expires_at=None,
            )
        ),
        resolver=resolver,
    )

    result = adapter.resolve_callback(
        replace(_envelope("wait-digest", "digest-mismatch"), payload_digest=_ZERO_DIGEST)
    )

    assert result.status is WaitCallbackAdapterStatus.DIGEST_MISMATCH
    assert resolver.calls == 0


def test_auth_rejection_returns_auth_failed_without_resolver_call() -> None:
    """认证拒绝返回 AUTH_FAILED 且不调用 resolver。"""

    resolver = _FailIfCalledResolver()
    reader = _FakeStateReader(
        WaitCallbackStoredWaitState(
            status=WaitCallbackStoredWaitStatus.WAITING,
            deadline_at=None,
            expires_at=None,
        )
    )
    adapter = DefaultWaitCallbackAdapter(
        authenticator=_RejectingAuthenticator(),
        state_reader=reader,
        resolver=resolver,
    )

    result = adapter.resolve_callback(_envelope("wait-auth", "auth-failed"))

    assert result.status is WaitCallbackAdapterStatus.AUTH_FAILED
    assert reader.calls == 0
    assert resolver.calls == 0


def test_callback_replay_does_not_append_new_event_log(tmp_path: Path) -> None:
    """同 callback replay 不追加新的 EventLog。"""

    host = create_host_command_handle(_options(tmp_path))
    try:
        seeded = _seed_waiting_run(host)
        adapter = _real_adapter(host)
        envelope = _envelope(seeded.wait_id, "eventlog-replay")

        first = adapter.resolve_callback(envelope)
        before_events = _events(host._transaction_runner())
        replay = adapter.resolve_callback(envelope)

        assert first.status is WaitCallbackAdapterStatus.ACCEPTED
        assert replay.status is WaitCallbackAdapterStatus.REPLAYED
        assert _events(host._transaction_runner()) == before_events
        assert len(_events_by_type(before_events, "TOOL_RESULT_ACCEPTED")) == 1
    finally:
        host.close()


def _real_adapter(host: HostCommandHandle) -> DefaultWaitCallbackAdapter:
    """构造真实 command port 的 callback adapter。

    :param host: Host command handle。
    :returns: 默认 callback adapter。
    """

    port = HostCommandWaitCallbackPort(host)
    return DefaultWaitCallbackAdapter(
        authenticator=_AcceptingAuthenticator(),
        state_reader=port,
        resolver=port,
    )


def _install_counting_wakeup(host: HostCommandHandle) -> _CountingWakeupPort:
    """给 Host command handle 安装计数 wakeup port。

    :param host: Host command handle。
    :returns: wakeup 计数器。
    """

    wakeup = _CountingWakeupPort()
    host._admission_service = create_host_admission_service(
        host._transaction_runner(),
        wakeup_port=wakeup,
    )
    return wakeup


def _envelope(
    wait_id: str,
    idempotency_key: str,
    *,
    outcome: ResolveWaitOutcome | None = None,
) -> WaitCallbackCompletionEnvelope:
    """构造带正确 digest 的 callback envelope。

    :param wait_id: wait id。
    :param idempotency_key: 幂等键。
    :param outcome: 可选 completed outcome；未提供时使用默认成功结果。
    :returns: callback envelope。
    """

    raw = WaitCallbackCompletionEnvelope(
        wait_id=wait_id,
        idempotency_key=idempotency_key,
        payload_digest=_ZERO_DIGEST,
        observed_at=_OBSERVED,
        completed_at=_COMPLETED_AT,
        outcome=(
            outcome
            if outcome is not None
            else ResolveWaitCompletedOutcome(
                result=ToolResultSuccess(ok=True, value={"answer": 42}, meta=None),
                payload_ref=None,
            )
        ),
        auth=WaitCallbackAuthInput(
            auth_source="callback-test",
            credential_ref="credential:test",
            presented_claims=(AuthorizationClaim(name="role", value="callback"),),
        ),
        request_id=f"request-{idempotency_key}",
        correlation_id=None,
    )
    return replace(raw, payload_digest=callback_payload_digest(raw))


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

        :param transaction: Host transaction。
        :returns: ``None``。
        """

        transaction.execute(
            f"UPDATE {TABLE_HOST_WAIT_RECORDS} SET deadline_at = ? WHERE wait_id = ?",
            (deadline_text, wait_id),
        )

    host._transaction_runner().run_write(_operation)


def _read_wait_row(
    transaction: HostTransaction, wait_id: str
) -> WaitRecordRow | None:
    """读取 wait record row。

    :param transaction: 当前 Host transaction。
    :param wait_id: wait id。
    :returns: wait record；不存在时为 ``None``。
    """

    return read_wait_record_by_id(transaction, wait_id)
