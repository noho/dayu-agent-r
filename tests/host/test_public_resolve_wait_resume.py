"""P10.5 Slice 5 public resolve_wait resume 测试。"""

from __future__ import annotations

import pathlib

import pytest

from dayu.host import RunStatus, open_host
from dayu.host.command import create_host_command_handle
from tests.host.test_public_retry_replay import (
    _FINAL,
    _SequencedWorkerFactory,
    _options as _open_host_options,
    _wait_for_run_status,
)
from tests.host.test_resolve_wait_command import (
    _completed_request,
    _options as _command_options,
    _seed_waiting_run,
)


@pytest.mark.asyncio
async def test_resolve_wait_resumes_through_open_host_and_terminal_event(
    tmp_path: pathlib.Path,
) -> None:
    """public opener 下 resolve_wait commit 后自动唤醒 scheduler 并恢复执行。"""

    seed_handle = create_host_command_handle(_command_options(tmp_path))
    try:
        seeded = _seed_waiting_run(seed_handle)
    finally:
        seed_handle.close()

    factory = _SequencedWorkerFactory([_FINAL])
    async with open_host(_open_host_options(tmp_path, factory)) as host:
        resolved = await host.resolve_wait(
            seeded.wait_id, _completed_request("public-resolve")
        )
        assert resolved.status is RunStatus.RUNNING
        assert resolved.current_attempt_id != seeded.attempt_id
        await _wait_for_run_status(host, seeded.run_id, RunStatus.SUCCEEDED)
