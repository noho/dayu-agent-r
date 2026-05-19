"""P10.5 Slice 5 public steer 控制命令测试。"""

from __future__ import annotations

import pathlib

import pytest

from dayu.host import (
    FollowupBehavior,
    HostApiError,
    HostApiErrorCode,
    RunStatus,
    SteerConflictDetail,
    SubmitFollowupRequest,
    open_host,
)
from tests.host.public_smoke_support import (
    AwaitingThenFinalWorkerFactory,
    awaiting_tooling_options,
    deterministic_runner_spec,
    open_host_options,
    wait_for_diagnostic_event_type_count,
    wait_for_public_waiting_run,
)
from tests.host.test_public_retry_replay import (
    _BLOCK,
    _FINAL,
    _SequencedWorkerFactory,
    _context,
    _ensure_request,
    _followup_request,
    _options,
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
        await wait_for_diagnostic_event_type_count(
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


@pytest.mark.asyncio
async def test_steer_waiting_run_creates_new_attempt_public_path(
    tmp_path: pathlib.Path,
) -> None:
    """submit_followup(steer) 支持 WAITING Run public path。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: WAITING steer 未创建新 Attempt 或未成功终态时抛出。
    """

    factory = AwaitingThenFinalWorkerFactory()
    options = open_host_options(
        tmp_path,
        runner_spec=deterministic_runner_spec("steer-waiting-model"),
        worker_factory=factory,
        allow_tool_calls=True,
        tooling_options=awaiting_tooling_options(),
    )
    async with open_host(options) as host:
        session = await host.ensure_session(_ensure_request("steer-waiting"))
        first = await host.submit_followup(
            session.session_id,
            _followup_request(session.session_id, "steer-waiting-source"),
        )
        waiting = await wait_for_public_waiting_run(
            host, options, first.accepted_run_id
        )

        steered = await host.submit_followup(
            waiting.session_id,
            SubmitFollowupRequest(
                context=_context("steer-waiting"),
                session_id=waiting.session_id,
                client_request_id="steer-waiting",
                system_prompt=None,
                user_prompt="replace waiting attempt",
                tool_names=None,
                runner_spec=None,
                runner_options=None,
                agent_policy=None,
                behavior=FollowupBehavior.STEER,
                target_run_id=waiting.run_id,
            ),
        )

        assert steered.accepted_run_id == waiting.run_id
        after = await host.get_run(waiting.run_id)
        assert after.current_attempt_id != waiting.attempt_id
        await _wait_for_run_status(host, waiting.run_id, RunStatus.SUCCEEDED)


@pytest.mark.asyncio
async def test_steer_replays_same_client_request_id_idempotently(
    tmp_path: pathlib.Path,
) -> None:
    """submit_followup(steer) 同 key 同语义重放返回同一 Run。"""

    factory = _SequencedWorkerFactory([_BLOCK, _FINAL])
    async with open_host(_options(tmp_path, factory)) as host:
        session = await host.ensure_session(_ensure_request("steer-idempotent"))
        first = await host.submit_followup(
            session.session_id,
            _followup_request(session.session_id, "steer-idempotent-source"),
        )
        await _wait_for_run_status(host, first.accepted_run_id, RunStatus.RUNNING)
        request = SubmitFollowupRequest(
            context=_context("steer-idempotent"),
            session_id=session.session_id,
            client_request_id="steer-idempotent",
            system_prompt=None,
            user_prompt="replace idempotently",
            tool_names=None,
            runner_spec=None,
            runner_options=None,
            agent_policy=None,
            behavior=FollowupBehavior.STEER,
            target_run_id=first.accepted_run_id,
        )

        steered = await host.submit_followup(session.session_id, request)
        await _wait_for_run_status(host, first.accepted_run_id, RunStatus.SUCCEEDED)
        replayed = await host.submit_followup(session.session_id, request)

    assert replayed.accepted_run_id == steered.accepted_run_id
    assert replayed.accepted_input_ref == steered.accepted_input_ref
    assert len(factory.accepted_requests) == 2


@pytest.mark.asyncio
async def test_steer_terminal_race_rejects_non_active_target(
    tmp_path: pathlib.Path,
) -> None:
    """terminal 已赢得竞争后 steer 返回 public INVALID_STATE。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: terminal Run 仍被 steer 接受时抛出。
    """

    factory = _SequencedWorkerFactory([_FINAL])
    async with open_host(_options(tmp_path, factory)) as host:
        session = await host.ensure_session(_ensure_request("steer-terminal"))
        source = await host.submit_followup(
            session.session_id,
            _followup_request(session.session_id, "steer-terminal-source"),
        )
        await _wait_for_run_status(host, source.accepted_run_id, RunStatus.SUCCEEDED)

        with pytest.raises(HostApiError) as exc_info:
            await host.submit_followup(
                session.session_id,
                SubmitFollowupRequest(
                    context=_context("steer-terminal"),
                    session_id=session.session_id,
                    client_request_id="steer-terminal",
                    system_prompt=None,
                    user_prompt="too late",
                    tool_names=None,
                    runner_spec=None,
                    runner_options=None,
                    agent_policy=None,
                    behavior=FollowupBehavior.STEER,
                    target_run_id=source.accepted_run_id,
                ),
            )

    assert exc_info.value.code == HostApiErrorCode.INVALID_STATE
    detail = exc_info.value.detail
    assert isinstance(detail, SteerConflictDetail)
    assert detail.target_run_id == source.accepted_run_id
    assert detail.target_run_status is RunStatus.SUCCEEDED
    assert detail.current_active_run_id is None
    assert detail.current_active_run_status is None
