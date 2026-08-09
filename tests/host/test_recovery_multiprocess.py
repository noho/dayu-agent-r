"""Phase 11 Slice 5 recovery 多进程行为测试。

本模块通过真实 ``open_host(options)``、public command 与
``watch_session_events(session_id)`` 验证 recovery 在多进程边界下的
行为。测试中的 durable 读取只用于制造进程死亡证据与核对 canonical facts，
不把 projection、read model、memory、trace、outbox 或 lane token 当作
recovery truth。
"""

from __future__ import annotations

import asyncio
import json
import pathlib
import signal
import sqlite3
import sys
import time
from multiprocessing import Process

import pytest

from dayu.host import HostEventKind, RunStatus, open_host
from tests.host.public_smoke_support import (
    close_attachment_shielded,
    next_terminal_for_run,
)
from tests.host.recovery_support import (
    AcceptedAttemptMarker,
    AsyncControlledFinalAnswerWorkerFactory,
    assert_process_exited_successfully,
    attempt_count_for_run,
    close_host_event_iterator,
    current_attempt_id_for_run,
    event_type_count,
    force_memory_projection_lag,
    force_owner_pid_missing_and_heartbeat_stale,
    projection_checkpoint_sequence,
    recovery_open_host_options,
    run_blocking_owner_process,
    run_open_probe_process,
    terminate_process,
    wait_for_accepted_marker,
    wait_for_runtime_lane_claim_ttl_to_expire,
    write_result_marker,
)

_PROCESS_START_TIMEOUT_SECONDS = 5.0
_PROCESS_JOIN_TIMEOUT_SECONDS = 5.0
_DELAYED_RECOVERY_TIMEOUT_SECONDS = 45.0
_LIVE_SLOT_KEY = "phase11-s5-live-owner"
_CRASH_SLOT_KEY = "phase11-s5-crash-owner"
_LAG_SLOT_KEY = "phase11-s5-projection-lag"


def test_live_second_process_open_does_not_recover_or_harm_owner(
    tmp_path: pathlib.Path,
) -> None:
    """第二个 live 进程打开同库时不得误杀仍存活 owner。"""

    accepted_marker = tmp_path / "owner-accepted"
    release_marker = tmp_path / "owner-release"
    owner_result_marker = tmp_path / "owner-result"
    probe_result_marker = tmp_path / "probe-result"
    owner_process = Process(
        target=run_blocking_owner_process,
        args=(
            str(tmp_path),
            str(accepted_marker),
            str(release_marker),
            str(owner_result_marker),
            _LIVE_SLOT_KEY,
            "live-owner-followup",
            "keep the first process alive",
        ),
    )
    owner_process.start()
    try:
        accepted = wait_for_accepted_marker(
            accepted_marker, _PROCESS_START_TIMEOUT_SECONDS
        )
        assert attempt_count_for_run(tmp_path, accepted.run_id) == 1

        probe_process = Process(
            target=run_open_probe_process,
            args=(str(tmp_path), str(probe_result_marker)),
        )
        probe_process.start()
        assert_process_exited_successfully(probe_process)

        assert owner_process.is_alive()
        assert event_type_count(tmp_path, "ATTEMPT_LOST") == 0
        assert event_type_count(tmp_path, "RUN_RECOVERING") == 0
        assert attempt_count_for_run(tmp_path, accepted.run_id) == 1
        assert current_attempt_id_for_run(tmp_path, accepted.run_id) == (
            accepted.attempt_id
        )

        write_result_marker(release_marker, "release\n")
        owner_process.join(_PROCESS_JOIN_TIMEOUT_SECONDS)
        assert_process_exited_successfully(owner_process)
    finally:
        terminate_process(owner_process)


@pytest.mark.asyncio
async def test_crashed_owner_reopens_and_final_answer_is_public_streamed(
    tmp_path: pathlib.Path,
) -> None:
    """owner pid missing 且 heartbeat stale 后，reopen 通过 public stream 产出 answer。"""

    accepted = _start_and_crash_owner(
        tmp_path,
        slot_key=_CRASH_SLOT_KEY,
        client_request_id="crash-owner-followup",
        user_prompt="recover this interrupted prompt",
    )

    recovery_factory = AsyncControlledFinalAnswerWorkerFactory("recovered-final")
    async with open_host(recovery_open_host_options(tmp_path, recovery_factory)) as host:
        attachment = await host.attach_session(accepted.session_id)
        watcher = await host.watch_session_events(accepted.session_id)
        await asyncio.wait_for(
            recovery_factory.accepted_event.wait(),
            timeout=_PROCESS_START_TIMEOUT_SECONDS,
        )
        terminal_task = asyncio.create_task(
            next_terminal_for_run(watcher, accepted.run_id)
        )
        recovery_factory.release_event.set()
        terminal = await asyncio.wait_for(
            terminal_task,
            timeout=_PROCESS_START_TIMEOUT_SECONDS,
        )
        await close_host_event_iterator(watcher)
        final_snapshot = await host.get_run(accepted.run_id)
        await close_attachment_shielded(attachment)

    assert terminal.kind is HostEventKind.SUCCEEDED
    assert terminal.final_answer is not None
    assert terminal.final_answer.content == f"recovered-final:{accepted.run_id}"
    assert final_snapshot.status is RunStatus.SUCCEEDED
    assert len(recovery_factory.snapshots) == 1
    assert recovery_factory.snapshots[0].run_id == accepted.run_id
    assert recovery_factory.snapshots[0].attempt_id != accepted.attempt_id
    assert event_type_count(tmp_path, "ATTEMPT_LOST") == 1
    assert event_type_count(tmp_path, "RUN_RECOVERING") == 1
    assert event_type_count(tmp_path, "RUN_STARTED") == 2
    assert attempt_count_for_run(tmp_path, accepted.run_id) == 2


@pytest.mark.asyncio
async def test_projection_lag_does_not_block_durable_recovery(
    tmp_path: pathlib.Path,
) -> None:
    """projection checkpoint 落后时 recovery 仍只依赖 durable governance rows。"""

    accepted = _start_and_crash_owner(
        tmp_path,
        slot_key=_LAG_SLOT_KEY,
        client_request_id="projection-lag-followup",
        user_prompt="recover without projection truth",
    )
    force_memory_projection_lag(tmp_path)
    assert projection_checkpoint_sequence(tmp_path) == 0

    recovery_factory = AsyncControlledFinalAnswerWorkerFactory("lag-recovered-final")
    async with open_host(recovery_open_host_options(tmp_path, recovery_factory)) as host:
        attachment = await host.attach_session(accepted.session_id)
        watcher = await host.watch_session_events(accepted.session_id)
        await asyncio.wait_for(
            recovery_factory.accepted_event.wait(),
            timeout=_PROCESS_START_TIMEOUT_SECONDS,
        )
        terminal_task = asyncio.create_task(
            next_terminal_for_run(watcher, accepted.run_id)
        )
        recovery_factory.release_event.set()
        terminal = await asyncio.wait_for(
            terminal_task,
            timeout=_PROCESS_START_TIMEOUT_SECONDS,
        )
        await close_host_event_iterator(watcher)
        final_snapshot = await host.get_run(accepted.run_id)
        await close_attachment_shielded(attachment)

    assert terminal.kind is HostEventKind.SUCCEEDED
    assert terminal.final_answer is not None
    assert terminal.final_answer.content == f"lag-recovered-final:{accepted.run_id}"
    assert final_snapshot.status is RunStatus.SUCCEEDED
    assert event_type_count(tmp_path, "ATTEMPT_LOST") == 1
    assert event_type_count(tmp_path, "RUN_RECOVERING") == 1
    assert attempt_count_for_run(tmp_path, accepted.run_id) == 2


@pytest.mark.skipif(sys.platform == "win32", reason="SIGKILL requires POSIX")
@pytest.mark.asyncio
async def test_sigkill_then_immediate_fresh_attach_recovers_without_second_restart(
    tmp_path: pathlib.Path,
) -> None:
    """owner SIGKILL 后 immediate fresh RW attach 在 stale 时自动恢复。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: 需要第二次重启、identity 复用或执行次数越界时抛出。
    """

    accepted_marker = tmp_path / "sigkill-immediate-accepted"
    release_marker = tmp_path / "sigkill-immediate-owner-release"
    result_marker = tmp_path / "sigkill-immediate-owner-result"
    owner_process = Process(
        target=run_blocking_owner_process,
        args=(
            str(tmp_path),
            str(accepted_marker),
            str(release_marker),
            str(result_marker),
            "phase11-s3-sigkill-immediate",
            "sigkill-immediate-followup",
            "recover after immediate reconnect",
        ),
    )
    owner_process.start()
    try:
        accepted = wait_for_accepted_marker(
            accepted_marker,
            _PROCESS_START_TIMEOUT_SECONDS,
        )
        old_execution_id = _execution_id_for_attempt(
            tmp_path,
            accepted.attempt_id,
        )
        owner_process.kill()
        owner_process.join(_PROCESS_JOIN_TIMEOUT_SECONDS)
        assert owner_process.is_alive() is False
        assert owner_process.exitcode == -signal.SIGKILL

        recovery_factory = AsyncControlledFinalAnswerWorkerFactory(
            "sigkill-delayed-recovered"
        )
        attach_started_at = time.monotonic()
        async with open_host(
            recovery_open_host_options(tmp_path, recovery_factory)
        ) as host:
            attachment = await host.attach_session(accepted.session_id)
            attach_elapsed = time.monotonic() - attach_started_at
            watcher = await host.watch_session_events(accepted.session_id)
            try:
                immediate_snapshot = await host.get_run(accepted.run_id)
                assert attach_elapsed < 10.0
                assert immediate_snapshot.status is RunStatus.RUNNING
                assert event_type_count(tmp_path, "ATTEMPT_LOST") == 0
                assert attempt_count_for_run(tmp_path, accepted.run_id) == 1

                await asyncio.wait_for(
                    recovery_factory.accepted_event.wait(),
                    timeout=_DELAYED_RECOVERY_TIMEOUT_SECONDS,
                )
                terminal_task = asyncio.create_task(
                    next_terminal_for_run(watcher, accepted.run_id)
                )
                recovery_factory.release_event.set()
                terminal = await asyncio.wait_for(
                    terminal_task,
                    timeout=_PROCESS_START_TIMEOUT_SECONDS,
                )
                final_snapshot = await host.get_run(accepted.run_id)
            finally:
                recovery_factory.release_event.set()
                await close_host_event_iterator(watcher)
                await close_attachment_shielded(attachment)

        assert terminal.kind is HostEventKind.SUCCEEDED
        assert final_snapshot.status is RunStatus.SUCCEEDED
        assert len(recovery_factory.snapshots) == 1
        new_snapshot = recovery_factory.snapshots[0]
        assert new_snapshot.run_id == accepted.run_id
        assert new_snapshot.attempt_id != accepted.attempt_id
        assert new_snapshot.execution_id != old_execution_id
        assert event_type_count(tmp_path, "ATTEMPT_LOST") == 1
        assert event_type_count(tmp_path, "RUN_RECOVERING") == 1
        assert event_type_count(tmp_path, "RUN_STARTED") == 2
        assert attempt_count_for_run(tmp_path, accepted.run_id) == 2
        event_types, recovery_reason = _run_event_order_and_recovery_reason(
            tmp_path,
            accepted.run_id,
        )
        attempt_lost_index = event_types.index("ATTEMPT_LOST")
        recovering_index = event_types.index("RUN_RECOVERING")
        recovery_started_index = max(
            index
            for index, event_type in enumerate(event_types)
            if event_type == "RUN_STARTED"
        )
        assert attempt_lost_index < recovering_index < recovery_started_index
        assert recovery_reason == "recovery"
    finally:
        terminate_process(owner_process)


def _start_and_crash_owner(
    tmp_path: pathlib.Path,
    *,
    slot_key: str,
    client_request_id: str,
    user_prompt: str,
) -> AcceptedAttemptMarker:
    """启动 owner 子进程，等待 worker accepted 后终止并制造 stale heartbeat。

    :param tmp_path: pytest 临时目录。
    :param slot_key: ensure_session slot key。
    :param client_request_id: follow-up 幂等 id。
    :param user_prompt: 用户输入。
    :returns: 被中断的 Attempt marker。
    """

    accepted_marker = tmp_path / f"{client_request_id}-accepted"
    release_marker = tmp_path / f"{client_request_id}-release"
    result_marker = tmp_path / f"{client_request_id}-result"
    owner_process = Process(
        target=run_blocking_owner_process,
        args=(
            str(tmp_path),
            str(accepted_marker),
            str(release_marker),
            str(result_marker),
            slot_key,
            client_request_id,
            user_prompt,
        ),
    )
    owner_process.start()
    accepted = wait_for_accepted_marker(
        accepted_marker, _PROCESS_START_TIMEOUT_SECONDS
    )
    terminate_process(owner_process)
    wait_for_runtime_lane_claim_ttl_to_expire()
    force_owner_pid_missing_and_heartbeat_stale(tmp_path, accepted.run_id)
    assert attempt_count_for_run(tmp_path, accepted.run_id) == 1
    return accepted


def _execution_id_for_attempt(
    tmp_path: pathlib.Path,
    attempt_id: str,
) -> str:
    """读取指定 Attempt 的 durable execution id。

    :param tmp_path: recovery 测试根目录。
    :param attempt_id: 目标 Attempt id。
    :returns: 非空 execution id。
    :raises AssertionError: Attempt 不存在或 execution id 非法时抛出。
    :raises sqlite3.Error: durable 查询失败时抛出。
    """

    with sqlite3.connect(tmp_path / "host.sqlite3") as connection:
        row = connection.execute(
            "SELECT execution_id FROM host_attempts WHERE attempt_id = ?",
            (attempt_id,),
        ).fetchone()
    assert row is not None
    execution_id = row[0]
    assert isinstance(execution_id, str)
    assert execution_id.strip() != ""
    return execution_id


def _run_event_order_and_recovery_reason(
    tmp_path: pathlib.Path,
    run_id: str,
) -> tuple[tuple[str, ...], str]:
    """读取指定 Run 的 canonical event 顺序与 recovery reason。

    :param tmp_path: recovery 测试根目录。
    :param run_id: 目标 Run id。
    :returns: event type 序列与最后一条 RUN_STARTED 的 start reason。
    :raises AssertionError: start event 数量或 payload 不合法时抛出。
    :raises Exception: SQLite 查询或 JSON 解析失败时透传。
    """

    with sqlite3.connect(tmp_path / "host.sqlite3") as connection:
        rows = connection.execute(
            """
            SELECT event_type, payload_json
            FROM event_log
            WHERE run_id = ?
            ORDER BY event_sequence ASC
            """,
            (run_id,),
        ).fetchall()
    event_types = tuple(str(row[0]) for row in rows)
    started_payloads = tuple(
        json.loads(str(row[1]))
        for row in rows
        if str(row[0]) == "RUN_STARTED"
    )
    assert len(started_payloads) == 2
    recovery_payload = started_payloads[-1]
    assert isinstance(recovery_payload, dict)
    recovery_reason = recovery_payload.get("start_reason")
    assert isinstance(recovery_reason, str)
    return event_types, recovery_reason
