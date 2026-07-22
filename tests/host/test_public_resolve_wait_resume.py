"""P10.5 Slice 5 public resolve_wait resume 测试。"""

from __future__ import annotations

import pathlib
from contextlib import AsyncExitStack

import pytest

from dayu.host import RunStatus, open_host
from tests.host.public_smoke_support import (
    AwaitingThenFinalWorkerFactory,
    awaiting_tooling_options,
    close_attachment_shielded,
    completed_wait_request,
    deterministic_runner_spec,
    open_host_options,
    wait_for_public_waiting_run,
)
from tests.host.test_public_retry_replay import (
    _ensure_request,
    _followup_request,
    _wait_for_run_status,
)


@pytest.mark.asyncio
async def test_resolve_wait_resumes_through_open_host_and_terminal_event(
    tmp_path: pathlib.Path,
) -> None:
    """public opener 下 resolve_wait commit 后自动唤醒 scheduler 并恢复执行。"""

    factory = AwaitingThenFinalWorkerFactory()
    options = open_host_options(
        tmp_path,
        runner_spec=deterministic_runner_spec("resolve-wait-model"),
        worker_factory=factory,
        allow_tool_calls=True,
        tooling_options=awaiting_tooling_options(),
    )
    async with (
        open_host(options) as host,
        AsyncExitStack() as attachment_stack,
    ):
        session = await host.ensure_session(_ensure_request("resolve-wait-public"))
        attachment = await host.attach_session(session.session_id)
        attachment_stack.push_async_callback(
            close_attachment_shielded, attachment
        )
        first = await host.submit_followup(
            session.session_id,
            _followup_request(session.session_id, "resolve-wait-source"),
        )
        waiting = await wait_for_public_waiting_run(
            host, options, first.accepted_run_id
        )

        resolved = await host.resolve_wait(
            waiting.wait_id, completed_wait_request("public-resolve")
        )
        assert resolved.status is RunStatus.RUNNING
        assert resolved.current_attempt_id != waiting.attempt_id
        await _wait_for_run_status(host, waiting.run_id, RunStatus.SUCCEEDED)
