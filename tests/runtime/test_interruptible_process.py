"""interruptible process runtime helper 测试。"""

from __future__ import annotations

import asyncio
import os
import signal
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TypeAlias, cast

import pytest

import dayu.runtime.interruptible_process as interruptible_process
from dayu.contracts.json_value import JsonValue
from dayu.runtime.interruptible_process import (
    InterruptibleProcessCompleted,
    InterruptibleProcessHandle,
    ProcessGroupCleanupReason,
    ProcessGroupCleanupResult,
)

_NESTED_CHILD_READY_TIMEOUT_SECONDS = 5.0
_NESTED_CHILD_EXIT_TIMEOUT_SECONDS = 5.0
_NESTED_CHILD_POLL_INTERVAL_SECONDS = 0.02
_LONG_RUNNING_SECONDS = 30.0
_PROCESS_INTERRUPT_GRACE_SECONDS = 1.0
_FALLBACK_INTERRUPT_GRACE_SECONDS = 1.0
_TEST_CHILD_PID = 12345
_TEST_PARENT_PID = 23456
_TEST_CURRENT_PGID = 34567
_TEST_CHILD_PGID = 45678
_TEST_PARENT_PGID = 56789
_NESTED_CHILD_SCRIPT = """
import os
import signal
import sys
import time

signal.signal(signal.SIGTERM, signal.SIG_IGN)
with open(sys.argv[1], "w", encoding="utf-8") as marker_file:
    marker_file.write(str(os.getpid()))
    marker_file.flush()
time.sleep(float(sys.argv[2]))
"""

_ProcessGroupResolver: TypeAlias = Callable[
    [int | None], interruptible_process._SafeProcessGroupLookup
]


@dataclass(frozen=True, slots=True)
class _ReturnTarget:
    """立即返回 JSON-like 结果的子进程目标。"""

    value: JsonValue

    def __call__(self) -> JsonValue:
        """返回预设值。

        :returns: JSON-like 结果。
        """

        return self.value


@dataclass(frozen=True, slots=True)
class _SleepTarget:
    """默认响应 SIGTERM 的阻塞目标。"""

    seconds: float

    def __call__(self) -> JsonValue:
        """阻塞指定秒数后返回。

        :returns: JSON-like 结果。
        """

        time.sleep(self.seconds)
        return {"completed": True}


@dataclass(frozen=True, slots=True)
class _IgnoreTerminateTarget:
    """忽略 SIGTERM 的阻塞目标。"""

    seconds: float

    def __call__(self) -> JsonValue:
        """忽略 SIGTERM 并阻塞指定秒数。

        :returns: JSON-like 结果。
        """

        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        time.sleep(self.seconds)
        return {"completed": True}


@dataclass(frozen=True, slots=True)
class _NestedChildTarget:
    """启动嵌套子进程后保持外层子进程存活的目标。"""

    marker_path: str
    seconds: float

    def __call__(self) -> JsonValue:
        """启动忽略 SIGTERM 的嵌套子进程并阻塞。

        :returns: JSON-like 结果。
        """

        subprocess.Popen(
            [
                sys.executable,
                "-c",
                _NESTED_CHILD_SCRIPT,
                self.marker_path,
                str(self.seconds),
            ],
            close_fds=True,
        )
        _wait_for_nested_pid(Path(self.marker_path))
        time.sleep(self.seconds)
        return {"completed": True}


class _FakeProcessCleanupHandle:
    """测试用 process cleanup handle。"""

    def __init__(
        self,
        *,
        pid_value: int | None,
        alive: bool,
        exitcode: int | None,
        pid_error: Exception | None = None,
        signal_error: OSError | None = None,
    ) -> None:
        """初始化 fake cleanup handle。

        :param pid_value: PID 属性返回值。
        :param alive: ``is_alive`` 返回值。
        :param exitcode: exitcode 属性返回值。
        :param pid_error: PID 属性读取时抛出的异常。
        :param signal_error: terminate / kill 调用时抛出的异常。
        :returns: ``None``。
        """

        self._pid_value = pid_value
        self._alive = alive
        self._exitcode = exitcode
        self._pid_error = pid_error
        self._signal_error = signal_error
        self.terminated = False
        self.killed = False
        self.joined = False

    @property
    def pid(self) -> int | None:
        """返回测试 PID。

        :returns: PID；若配置异常则抛出。
        :raises Exception: 按 ``pid_error`` 配置抛出。
        """

        if self._pid_error is not None:
            raise self._pid_error
        return self._pid_value

    @property
    def exitcode(self) -> int | None:
        """返回测试退出码。

        :returns: 退出码。
        """

        return self._exitcode

    def terminate(self) -> None:
        """记录 terminate 调用。

        :returns: ``None``。
        :raises OSError: 按 ``signal_error`` 配置抛出。
        """

        if self._signal_error is not None:
            raise self._signal_error
        self.terminated = True

    def kill(self) -> None:
        """记录 kill 调用。

        :returns: ``None``。
        :raises OSError: 按 ``signal_error`` 配置抛出。
        """

        if self._signal_error is not None:
            raise self._signal_error
        self.killed = True

    def join(self, timeout: float | None = None) -> None:
        """记录 join 调用。

        :param timeout: join timeout。
        :returns: ``None``。
        """

        self.joined = True

    def is_alive(self) -> bool:
        """返回测试存活状态。

        :returns: 存活状态。
        """

        return self._alive


@dataclass(frozen=True, slots=True)
class _FixedGetPgid:
    """测试用固定 getpgid callable。"""

    child_pgid: int
    parent_pgid: int

    def __call__(self, pid: int) -> int:
        """按 PID 返回测试 pgid。

        :param pid: 查询 PID。
        :returns: 测试 pgid。
        """

        if pid == _TEST_PARENT_PID:
            return self.parent_pgid
        return self.child_pgid


@dataclass(frozen=True, slots=True)
class _ParentGetPgidRaises:
    """测试用父进程 pgid 查询失败 callable。"""

    child_pgid: int

    def __call__(self, pid: int) -> int:
        """子 PID 返回 pgid，父 PID 抛出 OSError。

        :param pid: 查询 PID。
        :returns: 子进程 pgid。
        :raises OSError: 查询父进程 pgid 时抛出。
        """

        if pid == _TEST_PARENT_PID:
            raise OSError("parent pgid unavailable")
        return self.child_pgid


class _GetPgidRaisesProcessLookup:
    """测试用 child pgid 查询进程不存在 callable。"""

    def __call__(self, pid: int) -> int:
        """始终抛出 ProcessLookupError。

        :param pid: 查询 PID。
        :returns: 不返回。
        :raises ProcessLookupError: 始终抛出。
        """

        raise ProcessLookupError("child already exited")


class _KillpgRecorder:
    """记录 killpg 调用的测试 callable。"""

    def __init__(self) -> None:
        """初始化 recorder。

        :returns: ``None``。
        """

        self.called = False
        self.pgid: int | None = None
        self.signal_number: int | None = None

    def __call__(self, pgid: int, signal_number: int) -> None:
        """记录 killpg 参数。

        :param pgid: 进程组 ID。
        :param signal_number: signal number。
        :returns: ``None``。
        """

        self.called = True
        self.pgid = pgid
        self.signal_number = signal_number


class _KillpgRaisesOSError:
    """测试用 killpg 失败 callable。"""

    def __call__(self, pgid: int, signal_number: int) -> None:
        """始终抛出 OSError。

        :param pgid: 进程组 ID。
        :param signal_number: signal number。
        :returns: 不返回。
        :raises OSError: 始终抛出。
        """

        raise OSError("group signal failed")


def _get_test_current_pgid() -> int:
    """返回测试当前进程组 ID。

    :returns: 测试当前进程组 ID。
    """

    return _TEST_CURRENT_PGID


def _get_test_parent_pid() -> int:
    """返回测试父进程 PID。

    :returns: 测试父进程 PID。
    """

    return _TEST_PARENT_PID


def _raise_current_pgid_unavailable() -> int:
    """模拟当前进程组 ID 不可用。

    :returns: 不返回。
    :raises OSError: 始终抛出。
    """

    raise OSError("current pgid unavailable")


def _wait_for_nested_pid(marker_path: Path) -> int:
    """等待嵌套子进程写入 PID。

    :param marker_path: PID marker 文件路径。
    :returns: 嵌套子进程 PID。
    :raises AssertionError: 超时或 marker 内容非法时抛出。
    """

    deadline = time.monotonic() + _NESTED_CHILD_READY_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if marker_path.exists():
            content = marker_path.read_text(encoding="utf-8").strip()
            if content:
                return int(content)
        time.sleep(_NESTED_CHILD_POLL_INTERVAL_SECONDS)
    raise AssertionError("nested child pid marker was not written")


def _wait_for_pid_to_exit(pid: int) -> bool:
    """等待指定 PID 不再存在。

    :param pid: 进程 PID。
    :returns: PID 已不存在返回 ``True``；超时仍存在返回 ``False``。
    """

    deadline = time.monotonic() + _NESTED_CHILD_EXIT_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if not _pid_exists(pid):
            return True
        time.sleep(_NESTED_CHILD_POLL_INTERVAL_SECONDS)
    return not _pid_exists(pid)


def _pid_exists(pid: int) -> bool:
    """判断 PID 是否仍存在。

    :param pid: 进程 PID。
    :returns: 进程存在或权限不足无法确认时返回 ``True``。
    """

    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _force_kill_pid(pid: int) -> None:
    """尽力清理测试遗留 PID。

    :param pid: 进程 PID。
    :returns: ``None``。
    """

    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        return


def _resolve_process_group_unavailable(
    child_pid: int | None,
) -> interruptible_process._SafeProcessGroupLookup:
    """构造 pgid lookup 不可用的测试解析结果。

    :param child_pid: 直接子进程 PID。
    :returns: 测试用进程组解析结果。
    """

    return interruptible_process._SafeProcessGroupLookup(
        child_pgid=None,
        diagnostic=ProcessGroupCleanupResult(
            process_group_supported=True,
            direct_signal_sent=False,
            group_signal_sent=False,
            child_pid=child_pid,
            child_pgid=None,
            reason=ProcessGroupCleanupReason.PGID_UNAVAILABLE,
        ),
    )


def _resolve_process_group_matches_current(
    child_pid: int | None,
) -> interruptible_process._SafeProcessGroupLookup:
    """构造 pgid 与当前进程组相同的测试解析结果。

    :param child_pid: 直接子进程 PID。
    :returns: 测试用进程组解析结果。
    """

    current_pgid = os.getpgrp() if os.name == "posix" else None
    return interruptible_process._SafeProcessGroupLookup(
        child_pgid=None,
        diagnostic=ProcessGroupCleanupResult(
            process_group_supported=True,
            direct_signal_sent=False,
            group_signal_sent=False,
            child_pid=child_pid,
            child_pgid=current_pgid,
            reason=ProcessGroupCleanupReason.PGID_MATCHES_CURRENT_PROCESS_GROUP,
        ),
    )


@pytest.mark.asyncio
async def test_interruptible_process_returns_completed_value() -> None:
    """子进程正常完成时返回 JSON-like 值。"""

    handle = InterruptibleProcessHandle(_ReturnTarget({"ok": True}))
    try:
        handle.start()
        result = await handle.wait(timeout_seconds=2.0)
    finally:
        await handle.close()

    assert isinstance(result, InterruptibleProcessCompleted)
    assert result.value == {"ok": True}


@pytest.mark.asyncio
async def test_interruptible_process_terminate_exits_before_kill() -> None:
    """默认阻塞子进程可由 terminate 在 kill 前中止。"""

    handle = InterruptibleProcessHandle(_SleepTarget(seconds=10.0))
    try:
        handle.start()
        result = await handle.terminate(grace_seconds=1.0)
    finally:
        await handle.close()

    assert result.supported
    assert result.exited


@pytest.mark.asyncio
async def test_interruptible_process_hard_kill_exits_when_terminate_is_ignored() -> None:
    """忽略 SIGTERM 的子进程会走 hard kill 收口。"""

    handle = InterruptibleProcessHandle(_IgnoreTerminateTarget(seconds=10.0))
    try:
        handle.start()
        await asyncio.sleep(0.5)
        terminate = await handle.terminate(grace_seconds=0.2)
        kill = await handle.kill(grace_seconds=1.0)
    finally:
        await handle.close()

    assert terminate.supported
    assert not terminate.exited
    assert kill.supported
    assert kill.exited


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.name != "posix",
    reason="process-group cleanup is only supported on POSIX",
)
async def test_interruptible_process_group_kills_nested_child_on_posix(
    tmp_path: Path,
) -> None:
    """POSIX hard kill 会通过安全进程组 signal 清理嵌套子进程。"""

    marker_path = tmp_path / "nested.pid"
    nested_pid: int | None = None
    handle = InterruptibleProcessHandle(
        _NestedChildTarget(
            marker_path=str(marker_path),
            seconds=_LONG_RUNNING_SECONDS,
        )
    )
    try:
        handle.start()
        nested_pid = _wait_for_nested_pid(marker_path)
        kill = await handle.kill(grace_seconds=_PROCESS_INTERRUPT_GRACE_SECONDS)

        assert kill.supported
        assert kill.exited
        assert kill.cleanup.process_group_supported
        assert kill.cleanup.direct_signal_sent
        assert kill.cleanup.group_signal_sent
        assert kill.cleanup.reason is ProcessGroupCleanupReason.GROUP_SIGNALED
        assert _wait_for_pid_to_exit(nested_pid)
    finally:
        await handle.close()
        if nested_pid is not None and _pid_exists(nested_pid):
            _force_kill_pid(nested_pid)


@pytest.mark.asyncio
async def test_interruptible_process_group_reports_unsupported_when_not_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """进程组 cleanup 不可用时返回 unsupported 诊断并回退直接子进程 kill。"""

    monkeypatch.setattr(
        interruptible_process,
        "_PROCESS_GROUP_CLEANUP_SUPPORTED",
        False,
    )
    handle = InterruptibleProcessHandle(_SleepTarget(seconds=_LONG_RUNNING_SECONDS))
    try:
        handle.start()
        kill = await handle.kill(grace_seconds=_FALLBACK_INTERRUPT_GRACE_SECONDS)
    finally:
        await handle.close()

    assert kill.supported
    assert kill.exited
    assert not kill.cleanup.process_group_supported
    assert kill.cleanup.direct_signal_sent
    assert not kill.cleanup.group_signal_sent
    assert kill.cleanup.reason is ProcessGroupCleanupReason.UNSUPPORTED


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("resolver", "expected_reason"),
    (
        (
            _resolve_process_group_unavailable,
            ProcessGroupCleanupReason.PGID_UNAVAILABLE,
        ),
        (
            _resolve_process_group_matches_current,
            ProcessGroupCleanupReason.PGID_MATCHES_CURRENT_PROCESS_GROUP,
        ),
    ),
)
async def test_interruptible_process_group_fallback_reports_pgid_limitations(
    monkeypatch: pytest.MonkeyPatch,
    resolver: _ProcessGroupResolver,
    expected_reason: ProcessGroupCleanupReason,
) -> None:
    """pgid 不可用或不安全时 fallback direct-child cleanup 可观察。"""

    monkeypatch.setattr(
        interruptible_process,
        "_resolve_safe_child_process_group",
        resolver,
    )
    handle = InterruptibleProcessHandle(_SleepTarget(seconds=_LONG_RUNNING_SECONDS))
    try:
        handle.start()
        kill = await handle.kill(grace_seconds=_FALLBACK_INTERRUPT_GRACE_SECONDS)
    finally:
        await handle.close()

    assert kill.supported
    assert kill.exited
    assert kill.cleanup.process_group_supported
    assert kill.cleanup.direct_signal_sent
    assert not kill.cleanup.group_signal_sent
    assert kill.cleanup.reason is expected_reason


@pytest.mark.asyncio
async def test_interrupt_multiprocessing_process_reports_child_pid_unavailable_without_join() -> None:
    """raw process PID 不可用时返回诊断且不 signal / join。"""

    process = _FakeProcessCleanupHandle(
        pid_value=None,
        alive=False,
        exitcode=None,
        pid_error=ValueError("process has not started"),
    )

    result = await interruptible_process.interrupt_multiprocessing_process(
        process,
        signal_kind=interruptible_process.ProcessCleanupSignal.KILL,
        grace_seconds=_FALLBACK_INTERRUPT_GRACE_SECONDS,
    )

    assert result.supported
    assert result.exited
    assert result.cleanup.reason is ProcessGroupCleanupReason.CHILD_PID_UNAVAILABLE
    assert not result.cleanup.direct_signal_sent
    assert not result.cleanup.group_signal_sent
    assert not process.terminated
    assert not process.killed
    assert not process.joined


@pytest.mark.asyncio
async def test_interrupt_multiprocessing_process_reports_child_already_exited(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """child pgid 查询显示进程已退出时返回 CHILD_ALREADY_EXITED。"""

    monkeypatch.setattr(
        interruptible_process,
        "_PROCESS_GROUP_CLEANUP_SUPPORTED",
        True,
    )
    monkeypatch.setattr(
        interruptible_process.os,
        "getpgid",
        _GetPgidRaisesProcessLookup(),
    )
    process = _FakeProcessCleanupHandle(
        pid_value=_TEST_CHILD_PID,
        alive=False,
        exitcode=None,
    )

    result = await interruptible_process.interrupt_multiprocessing_process(
        process,
        signal_kind=interruptible_process.ProcessCleanupSignal.KILL,
        grace_seconds=_FALLBACK_INTERRUPT_GRACE_SECONDS,
    )

    assert result.cleanup.reason is ProcessGroupCleanupReason.CHILD_ALREADY_EXITED
    assert result.cleanup.direct_signal_sent
    assert not result.cleanup.group_signal_sent
    assert process.killed
    assert process.joined


@pytest.mark.asyncio
async def test_interrupt_multiprocessing_process_reports_current_pgid_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """当前进程组 ID 不可用时返回 CURRENT_PGID_UNAVAILABLE。"""

    monkeypatch.setattr(
        interruptible_process,
        "_PROCESS_GROUP_CLEANUP_SUPPORTED",
        True,
    )
    monkeypatch.setattr(
        interruptible_process.os,
        "getpgid",
        _FixedGetPgid(
            child_pgid=_TEST_CHILD_PGID,
            parent_pgid=_TEST_PARENT_PGID,
        ),
    )
    monkeypatch.setattr(
        interruptible_process.os,
        "getpgrp",
        _raise_current_pgid_unavailable,
        raising=False,
    )
    process = _FakeProcessCleanupHandle(
        pid_value=_TEST_CHILD_PID,
        alive=False,
        exitcode=None,
    )

    result = await interruptible_process.interrupt_multiprocessing_process(
        process,
        signal_kind=interruptible_process.ProcessCleanupSignal.KILL,
        grace_seconds=_FALLBACK_INTERRUPT_GRACE_SECONDS,
    )

    assert result.cleanup.reason is ProcessGroupCleanupReason.CURRENT_PGID_UNAVAILABLE
    assert result.cleanup.child_pgid == _TEST_CHILD_PGID
    assert result.cleanup.direct_signal_sent
    assert not result.cleanup.group_signal_sent


@pytest.mark.asyncio
async def test_interrupt_multiprocessing_process_reports_parent_pgid_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """父进程组 ID 不可用时返回 PARENT_PGID_UNAVAILABLE。"""

    monkeypatch.setattr(
        interruptible_process,
        "_PROCESS_GROUP_CLEANUP_SUPPORTED",
        True,
    )
    monkeypatch.setattr(
        interruptible_process.os,
        "getpgid",
        _ParentGetPgidRaises(child_pgid=_TEST_CHILD_PGID),
    )
    monkeypatch.setattr(
        interruptible_process.os,
        "getpgrp",
        _get_test_current_pgid,
        raising=False,
    )
    monkeypatch.setattr(
        interruptible_process.os,
        "getppid",
        _get_test_parent_pid,
    )
    process = _FakeProcessCleanupHandle(
        pid_value=_TEST_CHILD_PID,
        alive=False,
        exitcode=None,
    )

    result = await interruptible_process.interrupt_multiprocessing_process(
        process,
        signal_kind=interruptible_process.ProcessCleanupSignal.KILL,
        grace_seconds=_FALLBACK_INTERRUPT_GRACE_SECONDS,
    )

    assert result.cleanup.reason is ProcessGroupCleanupReason.PARENT_PGID_UNAVAILABLE
    assert result.cleanup.child_pgid == _TEST_CHILD_PGID
    assert result.cleanup.direct_signal_sent
    assert not result.cleanup.group_signal_sent


@pytest.mark.asyncio
async def test_interrupt_multiprocessing_process_reports_parent_pgid_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """child pgid 与父进程组相同时返回 unsafe fallback 诊断。"""

    monkeypatch.setattr(
        interruptible_process,
        "_PROCESS_GROUP_CLEANUP_SUPPORTED",
        True,
    )
    monkeypatch.setattr(
        interruptible_process.os,
        "getpgid",
        _FixedGetPgid(
            child_pgid=_TEST_CHILD_PGID,
            parent_pgid=_TEST_CHILD_PGID,
        ),
    )
    monkeypatch.setattr(
        interruptible_process.os,
        "getpgrp",
        _get_test_current_pgid,
        raising=False,
    )
    monkeypatch.setattr(
        interruptible_process.os,
        "getppid",
        _get_test_parent_pid,
    )
    process = _FakeProcessCleanupHandle(
        pid_value=_TEST_CHILD_PID,
        alive=False,
        exitcode=None,
    )

    result = await interruptible_process.interrupt_multiprocessing_process(
        process,
        signal_kind=interruptible_process.ProcessCleanupSignal.KILL,
        grace_seconds=_FALLBACK_INTERRUPT_GRACE_SECONDS,
    )

    assert (
        result.cleanup.reason
        is ProcessGroupCleanupReason.PGID_MATCHES_PARENT_PROCESS_GROUP
    )
    assert result.cleanup.child_pgid == _TEST_CHILD_PGID
    assert result.cleanup.direct_signal_sent
    assert not result.cleanup.group_signal_sent


@pytest.mark.asyncio
async def test_interrupt_multiprocessing_process_reports_group_signal_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """安全 pgid 的 group signal 失败时返回 GROUP_SIGNAL_FAILED。"""

    monkeypatch.setattr(
        interruptible_process,
        "_PROCESS_GROUP_CLEANUP_SUPPORTED",
        True,
    )
    monkeypatch.setattr(
        interruptible_process.os,
        "getpgid",
        _FixedGetPgid(
            child_pgid=_TEST_CHILD_PGID,
            parent_pgid=_TEST_PARENT_PGID,
        ),
    )
    monkeypatch.setattr(
        interruptible_process.os,
        "getpgrp",
        _get_test_current_pgid,
        raising=False,
    )
    monkeypatch.setattr(
        interruptible_process.os,
        "getppid",
        _get_test_parent_pid,
    )
    monkeypatch.setattr(
        interruptible_process.os,
        "killpg",
        _KillpgRaisesOSError(),
        raising=False,
    )
    process = _FakeProcessCleanupHandle(
        pid_value=_TEST_CHILD_PID,
        alive=False,
        exitcode=None,
    )

    result = await interruptible_process.interrupt_multiprocessing_process(
        process,
        signal_kind=interruptible_process.ProcessCleanupSignal.KILL,
        grace_seconds=_FALLBACK_INTERRUPT_GRACE_SECONDS,
    )

    assert result.cleanup.reason is ProcessGroupCleanupReason.GROUP_SIGNAL_FAILED
    assert result.cleanup.direct_signal_sent
    assert not result.cleanup.group_signal_sent
    assert process.killed
    assert process.joined


@pytest.mark.asyncio
async def test_interrupt_multiprocessing_process_direct_signal_oserror_still_joins_and_signals_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """直接子进程 signal 抛 OSError 时仍继续 group diagnostic 和 join。"""

    killpg = _KillpgRecorder()
    monkeypatch.setattr(
        interruptible_process,
        "_PROCESS_GROUP_CLEANUP_SUPPORTED",
        True,
    )
    monkeypatch.setattr(
        interruptible_process.os,
        "getpgid",
        _FixedGetPgid(
            child_pgid=_TEST_CHILD_PGID,
            parent_pgid=_TEST_PARENT_PGID,
        ),
    )
    monkeypatch.setattr(
        interruptible_process.os,
        "getpgrp",
        _get_test_current_pgid,
        raising=False,
    )
    monkeypatch.setattr(
        interruptible_process.os,
        "getppid",
        _get_test_parent_pid,
    )
    monkeypatch.setattr(
        interruptible_process.os,
        "killpg",
        killpg,
        raising=False,
    )
    process = _FakeProcessCleanupHandle(
        pid_value=_TEST_CHILD_PID,
        alive=False,
        exitcode=None,
        signal_error=OSError("direct signal failed"),
    )

    result = await interruptible_process.interrupt_multiprocessing_process(
        process,
        signal_kind=interruptible_process.ProcessCleanupSignal.KILL,
        grace_seconds=_FALLBACK_INTERRUPT_GRACE_SECONDS,
    )

    assert result.cleanup.reason is ProcessGroupCleanupReason.GROUP_SIGNALED
    assert not result.cleanup.direct_signal_sent
    assert result.cleanup.group_signal_sent
    assert killpg.called
    assert killpg.pgid == _TEST_CHILD_PGID
    assert process.joined


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("value", "expected_error"),
    (
        (cast(float, True), TypeError),
        (-0.1, ValueError),
        (float("nan"), ValueError),
        (float("inf"), ValueError),
        (float("-inf"), ValueError),
    ),
)
async def test_interruptible_process_rejects_invalid_grace_seconds(
    value: float,
    expected_error: type[Exception],
) -> None:
    """terminate / kill / close cleanup grace 必须拒绝 bool、负数、NaN 与无穷。"""

    handle = InterruptibleProcessHandle(_ReturnTarget({"ok": True}))
    try:
        with pytest.raises(expected_error):
            await handle.terminate(grace_seconds=value)
        with pytest.raises(expected_error):
            await handle.kill(grace_seconds=value)
        with pytest.raises(expected_error):
            await handle.close(kill_grace_seconds=value)
    finally:
        await handle.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "timeout_seconds",
    (-0.1, float("nan"), float("inf"), float("-inf")),
)
async def test_interruptible_process_wait_rejects_invalid_timeout(
    timeout_seconds: float,
) -> None:
    """process wait 必须在进入轮询前拒绝负数与非有限 timeout。

    :param timeout_seconds: 非法 wait timeout。
    :returns: ``None``。
    :raises AssertionError: 非法 timeout 未被拒绝时抛出。
    """

    handle = InterruptibleProcessHandle(_ReturnTarget({"ok": True}))
    with pytest.raises(ValueError, match="timeout_seconds"):
        await handle.wait(timeout_seconds=timeout_seconds)
