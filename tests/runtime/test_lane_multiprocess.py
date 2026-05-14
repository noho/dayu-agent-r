"""``dayu.runtime.lane`` 跨进程行为测试。

父进程通过 ``tmp_path`` 创建共享 runtime lane DB 路径，并把该路径作为 CLI
参数传给子进程。测试只断言 capacity invariant、non-blocking timeout、
release 后可 acquire、crash 后 TTL stale cleanup eventual acquire，不断言
acquire ordering。
"""

from __future__ import annotations

import asyncio
import os
import selectors
import subprocess
import sys
from pathlib import Path
from typing import TypeAlias

import pytest

from dayu.runtime.lane import (
    LaneAcquired,
    LaneAcquireTimedOut,
    LaneConfig,
    LaneController,
    SQLiteLaneCoordinatorConfig,
)

_LANE_NAME = "shared-llm"
_TTL_SECONDS = 0.3
_HEARTBEAT_SECONDS = 0.05
_POLL_SECONDS = 0.02
_BUSY_TIMEOUT_SECONDS = 1.0
_CHILD_TIMEOUT_SECONDS = 4.0
_PARENT_ACQUIRE_TIMEOUT_SECONDS = 2.0
_CAPACITY = 2
_CHILD_COUNT = 5
_CRASH_EXIT_CODE = 17

_ChildAcquireOutcome: TypeAlias = (
    tuple[LaneAcquired, LaneController]
    | tuple[LaneAcquireTimedOut, LaneController]
)


def _coordinator(db_path: Path) -> SQLiteLaneCoordinatorConfig:
    """构造多进程测试共享的 SQLite coordinator 配置。

    :param db_path: runtime lane DB 路径。
    :returns: SQLite coordinator 配置。
    """

    return SQLiteLaneCoordinatorConfig(
        db_path=db_path,
        busy_timeout_seconds=_BUSY_TIMEOUT_SECONDS,
        poll_interval_seconds=_POLL_SECONDS,
    )


def _lane_config(capacity: int) -> LaneConfig:
    """构造多进程测试 lane 配置。

    :param capacity: lane 容量。
    :returns: lane 配置。
    """

    return LaneConfig(
        name=_LANE_NAME,
        capacity=capacity,
        claim_ttl_seconds=_TTL_SECONDS,
        heartbeat_interval_seconds=_HEARTBEAT_SECONDS,
    )


def _child_command(
    mode: str,
    db_path: Path,
    *,
    capacity: int,
    timeout_seconds: float,
) -> list[str]:
    """构造子进程命令。

    :param mode: 子进程模式。
    :param db_path: 共享 DB 路径。
    :param capacity: lane 容量。
    :param timeout_seconds: acquire timeout。
    :returns: subprocess 命令参数。
    """

    return [
        sys.executable,
        str(Path(__file__).resolve()),
        mode,
        str(db_path),
        str(capacity),
        str(timeout_seconds),
    ]


def _start_child(
    mode: str,
    db_path: Path,
    *,
    capacity: int = 1,
    timeout_seconds: float = 0.0,
) -> subprocess.Popen[str]:
    """启动一个测试子进程。

    :param mode: 子进程模式。
    :param db_path: 共享 DB 路径。
    :param capacity: lane 容量。
    :param timeout_seconds: acquire timeout。
    :returns: 子进程 handle。
    """

    return subprocess.Popen(
        _child_command(
            mode,
            db_path,
            capacity=capacity,
            timeout_seconds=timeout_seconds,
        ),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def _read_line(process: subprocess.Popen[str]) -> str:
    """带 timeout 读取子进程 stdout 一行。

    :param process: 子进程 handle。
    :returns: 去掉换行后的 stdout 行。
    :raises AssertionError: 子进程未及时输出时抛出。
    """

    assert process.stdout is not None
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    try:
        events = selector.select(_CHILD_TIMEOUT_SECONDS)
        if not events:
            stderr_text = _read_stderr(process)
            raise AssertionError(f"child stdout timeout, stderr={stderr_text!r}")
        return process.stdout.readline().strip()
    finally:
        selector.close()


def _read_stderr(process: subprocess.Popen[str]) -> str:
    """读取子进程 stderr 文本。

    :param process: 子进程 handle。
    :returns: stderr 文本；stderr 不可用时返回空字符串。
    """

    if process.stderr is None:
        return ""
    return process.stderr.read()


def _send_line(process: subprocess.Popen[str], line: str) -> None:
    """向子进程 stdin 写入一行。

    :param process: 子进程 handle。
    :param line: 不含换行的文本。
    :returns: ``None``。
    """

    assert process.stdin is not None
    process.stdin.write(line + "\n")
    process.stdin.flush()


def _wait_child(process: subprocess.Popen[str]) -> int:
    """等待子进程退出。

    :param process: 子进程 handle。
    :returns: 子进程退出码。
    """

    return process.wait(timeout=_CHILD_TIMEOUT_SECONDS)


def _cleanup_child(process: subprocess.Popen[str]) -> None:
    """清理仍存活的测试子进程。

    :param process: 子进程 handle。
    :returns: ``None``。
    """

    if process.poll() is None:
        process.terminate()
        process.wait(timeout=_CHILD_TIMEOUT_SECONDS)


def _run_try_child(db_path: Path, *, timeout_seconds: float) -> str:
    """运行一次 acquire-and-release 子进程并返回 stdout。

    :param db_path: 共享 DB 路径。
    :param timeout_seconds: acquire timeout。
    :returns: 子进程 stdout。
    """

    completed = subprocess.run(
        _child_command(
            "try",
            db_path,
            capacity=1,
            timeout_seconds=timeout_seconds,
        ),
        check=False,
        capture_output=True,
        text=True,
        timeout=_CHILD_TIMEOUT_SECONDS,
    )
    assert completed.returncode == 0, completed.stderr
    return completed.stdout.strip()


def test_capacity_invariant_across_processes(tmp_path: Path) -> None:
    """多个独立进程共享 DB 时 successful claims 不得超过 capacity。"""

    db_path = tmp_path / "runtime_lanes.sqlite3"
    asyncio.run(
        LaneController.open(
            [_lane_config(capacity=_CAPACITY)],
            coordinator=_coordinator(db_path),
        )
    )
    children = [
        _start_child(
            "barrier_hold",
            db_path,
            capacity=_CAPACITY,
            timeout_seconds=0.0,
        )
        for _ in range(_CHILD_COUNT)
    ]
    try:
        for child in children:
            _send_line(child, "go")
        lines = [_read_line(child) for child in children]
        acquired_children = [
            child for child, line in zip(children, lines, strict=True) if line == "acquired"
        ]
        assert len(acquired_children) <= _CAPACITY
        assert lines.count("timed_out") + len(acquired_children) == _CHILD_COUNT

        for child in acquired_children:
            _send_line(child, "release")
            assert _read_line(child) == "released"
        for child in children:
            assert _wait_child(child) == 0
    finally:
        for child in children:
            _cleanup_child(child)


def test_nonblocking_timeout_when_held_and_release_allows_other_process(
    tmp_path: Path,
) -> None:
    """持有 claim 时其它进程 non-blocking timed out，release 后可 acquire。"""

    db_path = tmp_path / "runtime_lanes.sqlite3"
    holder = _start_child("hold", db_path, capacity=1, timeout_seconds=0.0)
    try:
        assert _read_line(holder) == "acquired"
        assert _run_try_child(db_path, timeout_seconds=0.0) == "timed_out"

        _send_line(holder, "release")
        assert _read_line(holder) == "released"
        assert _wait_child(holder) == 0

        assert _run_try_child(db_path, timeout_seconds=0.0) == "acquired"
    finally:
        _cleanup_child(holder)


@pytest.mark.asyncio
async def test_crashed_holder_is_cleaned_by_ttl_and_other_process_can_acquire(
    tmp_path: Path,
) -> None:
    """持有 claim 的进程崩溃后，TTL stale cleanup 允许其它 owner acquire。"""

    db_path = tmp_path / "runtime_lanes.sqlite3"
    crasher = _start_child("crash", db_path, capacity=1, timeout_seconds=0.0)
    try:
        assert _read_line(crasher) == "acquired"
        assert _wait_child(crasher) == _CRASH_EXIT_CODE
    finally:
        _cleanup_child(crasher)

    controller = await LaneController.open(
        [_lane_config(capacity=1)],
        coordinator=_coordinator(db_path),
    )
    outcome = await controller.acquire(
        _LANE_NAME,
        timeout_seconds=_PARENT_ACQUIRE_TIMEOUT_SECONDS,
    )
    assert isinstance(outcome, LaneAcquired)
    await outcome.token.release()
    await controller.close()


async def _child_acquire(
    *,
    db_path: Path,
    capacity: int,
    timeout_seconds: float,
) -> _ChildAcquireOutcome:
    """子进程执行一次 acquire。

    :param db_path: 共享 DB 路径。
    :param capacity: lane 容量。
    :param timeout_seconds: acquire timeout。
    :returns: acquire 结果与对应 controller。
    """

    controller = await LaneController.open(
        [_lane_config(capacity=capacity)],
        coordinator=_coordinator(db_path),
    )
    outcome = await controller.acquire(_LANE_NAME, timeout_seconds=timeout_seconds)
    if isinstance(outcome, LaneAcquired):
        return outcome, controller
    if isinstance(outcome, LaneAcquireTimedOut):
        return outcome, controller
    raise AssertionError(f"unexpected child acquire outcome: {type(outcome).__name__}")


async def _child_hold(
    *,
    db_path: Path,
    capacity: int,
    timeout_seconds: float,
    wait_for_barrier: bool,
) -> int:
    """子进程 acquire 成功后等待父进程 release 指令。

    :param db_path: 共享 DB 路径。
    :param capacity: lane 容量。
    :param timeout_seconds: acquire timeout。
    :param wait_for_barrier: 是否先等待父进程 ``go``。
    :returns: 进程退出码。
    """

    if wait_for_barrier:
        await asyncio.to_thread(sys.stdin.readline)
    outcome, controller = await _child_acquire(
        db_path=db_path,
        capacity=capacity,
        timeout_seconds=timeout_seconds,
    )
    if isinstance(outcome, LaneAcquireTimedOut):
        print("timed_out", flush=True)
        await controller.close()
        return 0
    print("acquired", flush=True)
    line = await asyncio.to_thread(sys.stdin.readline)
    if line.strip() == "release":
        await outcome.token.release()
        print("released", flush=True)
    await controller.close()
    return 0


async def _child_try(
    *,
    db_path: Path,
    capacity: int,
    timeout_seconds: float,
) -> int:
    """子进程尝试 acquire，成功后立即 release。

    :param db_path: 共享 DB 路径。
    :param capacity: lane 容量。
    :param timeout_seconds: acquire timeout。
    :returns: 进程退出码。
    """

    outcome, controller = await _child_acquire(
        db_path=db_path,
        capacity=capacity,
        timeout_seconds=timeout_seconds,
    )
    if isinstance(outcome, LaneAcquireTimedOut):
        print("timed_out", flush=True)
        await controller.close()
        return 0
    print("acquired", flush=True)
    await outcome.token.release()
    await controller.close()
    return 0


async def _child_crash(
    *,
    db_path: Path,
    capacity: int,
    timeout_seconds: float,
) -> int:
    """子进程 acquire 成功后直接退出，模拟未 release 的 crash。

    :param db_path: 共享 DB 路径。
    :param capacity: lane 容量。
    :param timeout_seconds: acquire timeout。
    :returns: 进程退出码；实际路径用 ``os._exit`` 结束。
    """

    outcome, controller = await _child_acquire(
        db_path=db_path,
        capacity=capacity,
        timeout_seconds=timeout_seconds,
    )
    assert isinstance(outcome, LaneAcquired)
    assert controller is not None
    print("acquired", flush=True)
    os._exit(_CRASH_EXIT_CODE)


def _child_main(argv: list[str]) -> int:
    """测试文件作为子进程脚本执行时的入口。

    :param argv: 命令行参数。
    :returns: 进程退出码。
    """

    mode = argv[1]
    db_path = Path(argv[2])
    capacity = int(argv[3])
    timeout_seconds = float(argv[4])
    if mode == "hold":
        return asyncio.run(
            _child_hold(
                db_path=db_path,
                capacity=capacity,
                timeout_seconds=timeout_seconds,
                wait_for_barrier=False,
            )
        )
    if mode == "barrier_hold":
        return asyncio.run(
            _child_hold(
                db_path=db_path,
                capacity=capacity,
                timeout_seconds=timeout_seconds,
                wait_for_barrier=True,
            )
        )
    if mode == "try":
        return asyncio.run(
            _child_try(
                db_path=db_path,
                capacity=capacity,
                timeout_seconds=timeout_seconds,
            )
        )
    if mode == "crash":
        return asyncio.run(
            _child_crash(
                db_path=db_path,
                capacity=capacity,
                timeout_seconds=timeout_seconds,
            )
        )
    raise AssertionError(f"unknown child mode: {mode}")


if __name__ == "__main__":
    raise SystemExit(_child_main(sys.argv))
