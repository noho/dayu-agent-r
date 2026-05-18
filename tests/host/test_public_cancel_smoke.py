"""P10.5 Slice 5 public cancel smoke 测试。"""

from __future__ import annotations

import pathlib

import pytest

from dayu.host import (
    CancelMode,
    CancelRunRequest,
    CancelSessionRunsRequest,
    RunStatus,
    open_host,
)
from tests.host.test_public_retry_replay import (
    _BLOCK,
    _SequencedWorkerFactory,
    _context,
    _ensure_request,
    _followup_request,
    _options,
    _wait_for_event_type_count,
    _wait_for_run_status,
)


@pytest.mark.asyncio
async def test_cancel_accepted_queued_and_active_public_path(
    tmp_path: pathlib.Path,
) -> None:
    """public cancel 覆盖 queued 与 active，并通过 shared registry 可见。"""

    factory = _SequencedWorkerFactory([_BLOCK])
    async with open_host(_options(tmp_path, factory)) as host:
        session = await host.ensure_session(_ensure_request("cancel"))
        active = await host.submit_followup(
            session.session_id,
            _followup_request(session.session_id, "cancel-active"),
        )
        await _wait_for_run_status(host, active.accepted_run_id, RunStatus.RUNNING)
        await _wait_for_event_type_count(
            tmp_path / "host.sqlite3", "ATTEMPT_RUNNING", 1
        )
        queued = await host.submit_followup(
            session.session_id,
            _followup_request(session.session_id, "cancel-queued"),
        )
        assert queued.accepted_run_status is RunStatus.QUEUED

        cancelled_queued = await host.cancel_run(
            queued.accepted_run_id,
            CancelRunRequest(
                context=_context("cancel-queued"),
                client_request_id="cancel-queued",
                reason="user_cancel_queued",
                mode=CancelMode.GRACEFUL,
            ),
        )
        assert cancelled_queued.status is RunStatus.CANCELLED

        await host.cancel_session_runs(
            session.session_id,
            CancelSessionRunsRequest(
                context=_context("cancel-session"),
                client_request_id="cancel-session",
                reason="user_cancel_session",
                mode=CancelMode.GRACEFUL,
            ),
        )
        cancelling = await host.get_run(active.accepted_run_id)
        assert cancelling.status in (RunStatus.CANCELLING, RunStatus.CANCELLED)
        assert factory.handles[0].cancel_reasons == ["user_cancel_session"]
