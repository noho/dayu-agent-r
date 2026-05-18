"""P10.5 Slice 5 public steer 控制命令测试。"""

from __future__ import annotations

import pathlib

import pytest

from dayu.host import FollowupBehavior, RunStatus, SubmitFollowupRequest, open_host
from tests.host.test_public_retry_replay import (
    _BLOCK,
    _FINAL,
    _SequencedWorkerFactory,
    _context,
    _ensure_request,
    _followup_request,
    _options,
    _wait_for_event_type_count,
    _wait_for_run_status,
)


@pytest.mark.asyncio
async def test_steer_running_run_creates_new_attempt_public_path(
    tmp_path: pathlib.Path,
) -> None:
    """submit_followup(steer) 在同一 Run 上创建新 Attempt 并取消旧 worker。"""

    factory = _SequencedWorkerFactory([_BLOCK, _FINAL])
    async with open_host(_options(tmp_path, factory)) as host:
        session = await host.ensure_session(_ensure_request("steer"))
        first = await host.submit_followup(
            session.session_id,
            _followup_request(session.session_id, "steer-source"),
        )
        await _wait_for_run_status(host, first.accepted_run_id, RunStatus.RUNNING)
        await _wait_for_event_type_count(
            tmp_path / "host.sqlite3", "ATTEMPT_RUNNING", 1
        )
        first_attempt_id = (await host.get_run(first.accepted_run_id)).current_attempt_id

        steered = await host.submit_followup(
            session.session_id,
            SubmitFollowupRequest(
                context=_context("steer-control"),
                session_id=session.session_id,
                client_request_id="steer-control",
                system_prompt=None,
                user_prompt="replace the running attempt",
                tool_names=None,
                runner_spec=None,
                runner_options=None,
                agent_policy=None,
                behavior=FollowupBehavior.STEER,
                target_run_id=first.accepted_run_id,
            ),
        )

        assert steered.accepted_run_id == first.accepted_run_id
        assert steered.target_run_id == first.accepted_run_id
        after = await host.get_run(first.accepted_run_id)
        assert after.current_attempt_id != first_attempt_id
        await _wait_for_run_status(host, first.accepted_run_id, RunStatus.SUCCEEDED)
        assert factory.handles[0].cancel_reasons == ["steered"]
