"""``dayu-cli init`` 的真实 POSIX/Windows 进程级 smoke。

本模块只通过公开 CLI、真实文件锁和真实平台文件系统证明 S3 工作流；除明确的
prewarm import/network 观察 seam 外，不替换 production owner。
"""

from __future__ import annotations

import errno
import hashlib
import io
import os
import platform
import secrets
import selectors
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from collections.abc import Mapping
from dataclasses import dataclass, fields
from pathlib import Path
from typing import BinaryIO, Final, Literal, Protocol, TypeAlias, cast

import pytest

import dayu.cli.commands.init as init_command
import dayu.cli.init_workspace as init_workspace
from dayu.cli.init_catalog import PRODUCTION_RUNTIME_MANIFEST_BASENAMES
from dayu.runtime.config_loader import ConfigLoader
from dayu.runtime.filelock import file_lock
from dayu.runtime.scene_prepare import ScenePrepareRequest, SceneToolCatalog, prepare_scene
from dayu.service.host_assembly import (
    assemble_effective_tool_provider_configs,
    discover_service_tools,
)

_REPOSITORY_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
_OLLAMA_INPUT: Final[str] = "14\n\n\n\n"
_WAIT_TIMEOUT_SECONDS: Final[float] = 30.0
_PROCESS_TIMEOUT_SECONDS: Final[float] = 180.0
_CURRENT_TIME_SLOT: Final[str] = "current_time"
_FINS_DEFAULT_SUBJECT_SLOT: Final[str] = "fins_default_subject"
_DAYU_BLOCK_BEGIN: Final[str] = "# >>> dayu-cli init >>>"
_DAYU_BLOCK_END: Final[str] = "# <<< dayu-cli init <<<"
_OPENAI_ENV_NAME: Final[str] = "OPENAI_API_KEY"
_OPTIONAL_ENVIRONMENT_NAMES: Final[tuple[str, ...]] = (
    "TAVILY_API_KEY",
    "SERPER_API_KEY",
    "FMP_API_KEY",
    "HF_ENDPOINT",
    "HF_TOKEN",
)
_WINDOWS_PRIVILEGE_NOT_HELD: Final[int] = 1314
_GITHUB_ACTIONS_ENV_NAME: Final[str] = "GITHUB_ACTIONS"
_GITHUB_RUN_ID_ENV_NAME: Final[str] = "GITHUB_RUN_ID"
_GITHUB_ACTIONS_ENABLED: Final[str] = "true"
_WINDOWS_CANARY_PREFIX: Final[str] = "sk-dayu-test-"
_WINDOWS_CANARY_DOMAIN: Final[bytes] = b"dayu-ar-f07-win4-r12-canary-v1\x00"


@dataclass(frozen=True, slots=True)
class _InitProcessResult:
    """真实 init 外层进程的最小可消费结果。"""

    returncode: int
    stdout: str
    stderr: str


class _WindowsOSError(Protocol):
    """Windows ``OSError`` 的精确 privilege error 视图。"""

    winerror: int


class _RegistryCommandRunner(Protocol):
    """Windows registry test command runner 协议。"""

    def __call__(
        self,
        arguments: tuple[str, ...],
    ) -> subprocess.CompletedProcess[str]:
        """执行一个不投影 value 的 registry command。

        :param arguments: ``reg.exe`` 后的参数。
        :returns: 捕获输出的完成结果。
        :raises OSError: 进程创建失败时抛出。
        """

        ...


class _ScriptedRegistryCommandRunner:
    """按顺序返回指定退出码的 registry owner-test runner。"""

    calls: list[tuple[str, ...]]

    def __init__(self, returncodes: tuple[int, ...]) -> None:
        """初始化 scripted runner。

        :param returncodes: 每次调用依次返回的 exit codes。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self._returncodes = list(returncodes)
        self.calls = []

    def __call__(
        self,
        arguments: tuple[str, ...],
    ) -> subprocess.CompletedProcess[str]:
        """记录参数并返回下一结果。

        :param arguments: ``reg.exe`` 后的参数。
        :returns: 带测试 secret 输出的完成结果，用于证明错误不回显命令输出。
        :raises AssertionError: 调用次数超过脚本时抛出。
        """

        if not self._returncodes:
            raise AssertionError("unexpected registry command invocation")
        self.calls.append(arguments)
        return subprocess.CompletedProcess(
            args=("reg.exe", *arguments),
            returncode=self._returncodes.pop(0),
            stdout="test-secret-value",
            stderr="test-secret-error",
        )


_WaitOutcome: TypeAlias = int | Literal["timeout"]


class _TrackedTemporaryHandle(io.BytesIO):
    """记录 read/flush/seek 且由 context 自动关闭的 anonymous binary handle。"""

    def __init__(self) -> None:
        """初始化空 binary handle 与调用计数。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        super().__init__()
        self.read_count = 0
        self.flush_count = 0
        self.seek_calls: list[tuple[int, int]] = []

    def read(self, size: int | None = -1) -> bytes:
        """从底层 handle 读取 bytes 并记录读取次数。

        :param size: 最大读取字节数；``-1`` 表示读到结尾。
        :returns: 读取到的 bytes。
        :raises OSError: 底层读取失败时抛出。
        """

        self.read_count += 1
        return super().read(size)

    def flush(self) -> None:
        """flush 底层 handle 并记录调用。

        :returns: ``None``。
        :raises OSError: flush 失败时抛出。
        """

        self.flush_count += 1
        super().flush()

    def seek(self, offset: int, whence: int = 0) -> int:
        """移动底层 handle offset 并记录调用。

        :param offset: 目标相对 offset。
        :param whence: offset 参考点。
        :returns: 移动后的绝对 offset。
        :raises OSError: seek 失败时抛出。
        """

        self.seek_calls.append((offset, whence))
        return super().seek(offset, whence)


class _TemporaryHandleRecorder:
    """记录 `_run_init` 创建的三个 anonymous handle 与精确 mode。"""

    def __init__(self) -> None:
        """初始化 mode 与 handle 记录。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.modes: list[str] = []
        self.handles: list[_TrackedTemporaryHandle] = []

    def __call__(self, *, mode: str) -> _TrackedTemporaryHandle:
        """创建并记录一个真实 anonymous handle wrapper。

        :param mode: 调用者显式选择的 temporary file mode。
        :returns: tracked anonymous binary handle。
        :raises Exception: 不主动抛出异常。
        """

        self.modes.append(mode)
        tracked = _TrackedTemporaryHandle()
        self.handles.append(tracked)
        return tracked


class _ScriptedInitProcess:
    """按脚本模拟 Popen wait/poll/kill，并验证 handles 生命周期。"""

    def __init__(
        self,
        *,
        wait_outcomes: tuple[_WaitOutcome, ...],
        poll_outcomes: tuple[int | None, ...],
        stdout: bytes,
        stderr: bytes,
        sensitive_value: str,
    ) -> None:
        """初始化 deterministic process state machine。

        :param wait_outcomes: 每次 wait 的 returncode 或 timeout。
        :param poll_outcomes: 每次 poll 的 returncode 或仍运行状态。
        :param stdout: 模拟 child 写入的 stdout bytes。
        :param stderr: 模拟 child 写入的 stderr bytes。
        :param sensitive_value: 只放进 raw TimeoutExpired 的泄漏探针。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self._wait_outcomes = list(wait_outcomes)
        self._poll_outcomes = list(poll_outcomes)
        self._stdout = stdout
        self._stderr = stderr
        self._sensitive_value = sensitive_value
        self._stdin_handle: BinaryIO | None = None
        self._stdout_handle: BinaryIO | None = None
        self._stderr_handle: BinaryIO | None = None
        self._output_written = False
        self.wait_calls: list[float] = []
        self.poll_calls = 0
        self.kill_calls = 0
        self.timeout_exceptions: list[subprocess.TimeoutExpired] = []

    def attach_handles(
        self,
        *,
        stdin: BinaryIO,
        stdout: BinaryIO,
        stderr: BinaryIO,
    ) -> None:
        """绑定 factory 收到的三个 binary handles。

        :param stdin: child stdin handle。
        :param stdout: child stdout handle。
        :param stderr: child stderr handle。
        :returns: ``None``。
        :raises AssertionError: handles 在绑定前已经关闭时抛出。
        """

        if stdin.closed or stdout.closed or stderr.closed:
            raise AssertionError("init handles closed before process creation")
        self._stdin_handle = stdin
        self._stdout_handle = stdout
        self._stderr_handle = stderr

    def _require_open_handles(self) -> tuple[BinaryIO, BinaryIO, BinaryIO]:
        """返回已绑定且仍打开的三个 handles。

        :returns: ``(stdin, stdout, stderr)``。
        :raises AssertionError: handles 未绑定或提前关闭时抛出。
        """

        if self._stdin_handle is None or self._stdout_handle is None or self._stderr_handle is None:
            raise AssertionError("init handles were not attached")
        if self._stdin_handle.closed or self._stdout_handle.closed or self._stderr_handle.closed:
            raise AssertionError("init handles closed during process lifecycle")
        return self._stdin_handle, self._stdout_handle, self._stderr_handle

    def _write_output_once(self) -> None:
        """模拟 child 最多一次写入 stdout/stderr。

        :returns: ``None``。
        :raises OSError: handle 写入或 flush 失败时抛出。
        """

        _, stdout, stderr = self._require_open_handles()
        if self._output_written:
            return
        stdout.write(self._stdout)
        stdout.flush()
        stderr.write(self._stderr)
        stderr.flush()
        self._output_written = True

    def wait(self, timeout: float) -> int:
        """返回下一 scripted wait 结果或抛出含探针的 raw timeout。

        :param timeout: 调用者的 bounded wait 秒数。
        :returns: scripted process returncode。
        :raises subprocess.TimeoutExpired: 当前 scripted outcome 为 timeout 时抛出。
        :raises AssertionError: wait 次数超出脚本时抛出。
        """

        self._require_open_handles()
        self._write_output_once()
        self.wait_calls.append(timeout)
        if not self._wait_outcomes:
            raise AssertionError("unexpected second init process wait")
        outcome = self._wait_outcomes.pop(0)
        if outcome == "timeout":
            timeout_error = subprocess.TimeoutExpired(
                cmd=("sensitive-cli-argv", self._sensitive_value),
                timeout=timeout,
                output=self._sensitive_value.encode("utf-8", errors="strict"),
                stderr=self._sensitive_value.encode("utf-8", errors="strict"),
            )
            self.timeout_exceptions.append(timeout_error)
            raise timeout_error
        return outcome

    def poll(self) -> int | None:
        """返回下一 scripted nonblocking process observation。

        :returns: scripted returncode 或 ``None``。
        :raises AssertionError: poll 次数超出脚本时抛出。
        """

        self._require_open_handles()
        self.poll_calls += 1
        if not self._poll_outcomes:
            raise AssertionError("unexpected second init process poll")
        return self._poll_outcomes.pop(0)

    def kill(self) -> None:
        """记录 direct-process kill 并验证 handles 仍存活。

        :returns: ``None``。
        :raises AssertionError: handles 提前关闭时抛出。
        """

        self._require_open_handles()
        self.kill_calls += 1


class _ScriptedInitPopenFactory:
    """记录 `_run_init` Popen contract 并返回单个 scripted process。"""

    def __init__(self, process: _ScriptedInitProcess) -> None:
        """保存本次唯一 scripted process。

        :param process: 待返回的 deterministic process。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self._process = process
        self.call_count = 0
        self.arguments: tuple[str, ...] | None = None
        self.cwd: Path | None = None
        self.environment: dict[str, str] | None = None
        self.stdin_payload: bytes | None = None
        self.shell: bool | None = None
        self.close_fds: bool | None = None
        self.text: bool | None = None

    def __call__(
        self,
        arguments: tuple[str, ...],
        *,
        cwd: Path,
        env: dict[str, str],
        stdin: BinaryIO,
        stdout: BinaryIO,
        stderr: BinaryIO,
        shell: bool,
        close_fds: bool,
        text: bool,
    ) -> _ScriptedInitProcess:
        """记录精确 Popen 输入并返回 scripted process。

        :param arguments: outer real CLI argv。
        :param cwd: 保留的 repository cwd。
        :param env: 保留的隔离环境。
        :param stdin: anonymous binary stdin handle。
        :param stdout: anonymous binary stdout handle。
        :param stderr: anonymous binary stderr handle。
        :param shell: 必须为 ``False``。
        :param close_fds: 必须为 ``True``。
        :param text: 必须为 ``False``，保持 binary mode。
        :returns: 本次唯一 scripted process。
        :raises AssertionError: factory 被重复调用或 stdin 未 rewind 时抛出。
        """

        self.call_count += 1
        if self.call_count != 1:
            raise AssertionError("unexpected second init Popen call")
        if stdin.tell() != 0:
            raise AssertionError("init stdin was not rewound before Popen")
        self.arguments = arguments
        self.cwd = cwd
        self.environment = env
        self.stdin_payload = stdin.read()
        stdin.seek(0)
        self.shell = shell
        self.close_fds = close_fds
        self.text = text
        self._process.attach_handles(stdin=stdin, stdout=stdout, stderr=stderr)
        return self._process


class _ScriptedTokenFactory:
    """为 local-random owner test 返回顺序固定但互异的测试值。"""

    def __init__(self, tokens: tuple[str, ...]) -> None:
        """初始化 scripted token 序列。

        :param tokens: 后续调用依次返回的 token。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self._tokens = list(tokens)
        self.calls: list[int] = []

    def __call__(self, byte_count: int) -> str:
        """记录请求字节数并返回下一 token。

        :param byte_count: ``token_urlsafe`` 请求的随机字节数。
        :returns: 下一 scripted token。
        :raises AssertionError: 调用次数超过脚本时抛出。
        """

        self.calls.append(byte_count)
        if not self._tokens:
            raise AssertionError("unexpected extra local token request")
        return self._tokens.pop(0)


class _ForbiddenTokenFactory:
    """证明 GitHub Actions 路径不会回退到随机 token。"""

    def __init__(self) -> None:
        """初始化零调用计数。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.calls = 0

    def __call__(self, byte_count: int) -> str:
        """拒绝任何 random fallback。

        :param byte_count: 意外请求的随机字节数。
        :returns: 本实现不会返回。
        :raises AssertionError: 每次调用都抛出。
        """

        del byte_count
        self.calls += 1
        raise AssertionError("GitHub Actions canary attempted random fallback")


def _write_text(path: Path, value: str) -> None:
    """创建 parent 并写入 UTF-8 文本。

    :param path: 目标路径。
    :param value: 文本内容。
    :returns: ``None``。
    :raises OSError: mkdir/write 失败时抛出。
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def _subprocess_environment(
    home_directory: Path,
    *,
    absent_names: tuple[str, ...] = (),
) -> dict[str, str]:
    """构造隔离 HOME/temp 且关闭 bytecode 的真实 CLI 环境。

    :param home_directory: 子进程 HOME/USERPROFILE。
    :param absent_names: 必须从继承环境删除的变量名。
    :returns: 子进程环境副本。
    :raises OSError: 隔离目录创建失败时抛出。
    """

    home_directory.mkdir(parents=True, exist_ok=True)
    temp_directory = home_directory / "tmp"
    temp_directory.mkdir()
    environment = dict(os.environ)
    environment["HOME"] = str(home_directory)
    environment["USERPROFILE"] = str(home_directory)
    environment["SHELL"] = "/bin/zsh"
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTHONUNBUFFERED"] = "1"
    environment["TMPDIR"] = str(temp_directory)
    environment["TMP"] = str(temp_directory)
    environment["TEMP"] = str(temp_directory)
    non_secret_marker = secrets.token_urlsafe(12)
    for name in _OPTIONAL_ENVIRONMENT_NAMES:
        environment[name] = non_secret_marker
    for name in absent_names:
        environment.pop(name, None)
    return environment


def _github_actions_canary(raw_run_id: str) -> str:
    """从公开 GitHub Actions run id 派生固定的非秘密测试 canary。

    :param raw_run_id: 未 canonicalize 的 ``GITHUB_RUN_ID``。
    :returns: 带测试前缀与 64 位小写 SHA-256 hex 的 canary。
    :raises AssertionError: run id 不是正 ASCII 十进制整数时抛出安全错误。
    """

    if not raw_run_id.isascii() or not raw_run_id.isdecimal():
        raise AssertionError("GITHUB_RUN_ID must be a positive ASCII decimal integer")
    run_id = int(raw_run_id)
    if run_id <= 0:
        raise AssertionError("GITHUB_RUN_ID must be a positive ASCII decimal integer")
    canonical_run_id = str(run_id)
    digest = hashlib.sha256(_WINDOWS_CANARY_DOMAIN + canonical_run_id.encode("ascii", errors="strict")).hexdigest()
    return f"{_WINDOWS_CANARY_PREFIX}{digest}"


def _select_windows_test_canary(environment: Mapping[str, str]) -> str:
    """按运行环境选择 Windows real-setx 的非秘密测试 canary。

    :param environment: 只读取 GitHub Actions 开关与公开 run id 的环境映射。
    :returns: GitHub Actions 确定性 canary，或本地随机测试值。
    :raises AssertionError: GitHub Actions 开启但 run id 缺失或非法时抛出安全错误。
    """

    if environment.get(_GITHUB_ACTIONS_ENV_NAME) == _GITHUB_ACTIONS_ENABLED:
        raw_run_id = environment.get(_GITHUB_RUN_ID_ENV_NAME)
        if raw_run_id is None:
            raise AssertionError("GITHUB_RUN_ID must be set in GitHub Actions")
        return _github_actions_canary(raw_run_id)
    return secrets.token_urlsafe(32)


def _render_init_timeout(
    *,
    returncode_at_timeout: int | None,
    cleanup: Literal["completed", "timeout"],
    cleanup_returncode: int | None,
    process_state_after_cleanup_timeout: Literal["running", "exited"] | None,
) -> str:
    """渲染唯一的 outer init timeout 安全失败文本。

    :param returncode_at_timeout: deadline 后首次非阻塞观察到的退出码。
    :param cleanup: direct process 清理完成或超时。
    :param cleanup_returncode: 清理阶段可用的退出码。
    :param process_state_after_cleanup_timeout: 仅 cleanup timeout 后的单次 poll 投影。
    :returns: 不含 argv、路径、输入或进程输出的安全失败文本。
    :raises AssertionError: cleanup 与 post-timeout state 组合不符合状态机时抛出。
    """

    if cleanup == "completed" and process_state_after_cleanup_timeout is not None:
        raise AssertionError("completed cleanup cannot have a post-timeout process state")
    if cleanup == "timeout" and process_state_after_cleanup_timeout is None:
        raise AssertionError("timed-out cleanup requires a post-timeout process state")
    deadline_returncode = "not_exited" if returncode_at_timeout is None else str(returncode_at_timeout)
    rendered_cleanup_returncode = "not_available" if cleanup_returncode is None else str(cleanup_returncode)
    message = (
        "category=dayu_cli_init_timeout "
        f"timeout_seconds={_PROCESS_TIMEOUT_SECONDS:g} "
        f"returncode_at_timeout={deadline_returncode} "
        f"cleanup={cleanup} "
        f"cleanup_returncode={rendered_cleanup_returncode}"
    )
    if process_state_after_cleanup_timeout is not None:
        message = f"{message} process_state_after_cleanup_timeout={process_state_after_cleanup_timeout}"
    return message


def _run_init(
    workspace_root: Path,
    environment: dict[str, str],
    *,
    flags: tuple[str, ...] = (),
    input_text: str = _OLLAMA_INPUT,
) -> _InitProcessResult:
    """以真实 ``python -m dayu.cli`` 运行一次 init。

    :param workspace_root: 目标 workspace。
    :param environment: 隔离子进程环境。
    :param flags: init 追加 flags。
    :param input_text: 完整确定性 stdin。
    :returns: 只包含 returncode/stdout/stderr 的严格 UTF-8 结果。
    :raises UnicodeEncodeError: stdin 不是可编码的严格 UTF-8 文本时抛出。
    :raises UnicodeDecodeError: stdout/stderr 不是严格 UTF-8 时抛出。
    :raises pytest.fail.Exception: CLI 超时且完成 bounded direct-process cleanup 后抛出安全失败。
    """

    with (
        tempfile.TemporaryFile(mode="w+b") as stdin_handle,
        tempfile.TemporaryFile(mode="w+b") as stdout_handle,
        tempfile.TemporaryFile(mode="w+b") as stderr_handle,
    ):
        input_bytes = input_text.encode("utf-8", errors="strict")
        stdin_handle.write(input_bytes)
        stdin_handle.flush()
        stdin_handle.seek(0)

        # timeout failure 前主动清空 helper frame 中唯一的 input 文本与 bytes 所有者。
        input_text = ""
        input_bytes = b""
        process: subprocess.Popen[bytes] = subprocess.Popen(
            (
                sys.executable,
                "-u",
                "-m",
                "dayu.cli",
                "init",
                "--base",
                str(workspace_root),
                *flags,
            ),
            cwd=_REPOSITORY_ROOT,
            env=environment,
            stdin=stdin_handle,
            stdout=stdout_handle,
            stderr=stderr_handle,
            shell=False,
            close_fds=True,
            text=False,
        )
        try:
            returncode = process.wait(timeout=_PROCESS_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            returncode_at_timeout = process.poll()
            cleanup: Literal["completed", "timeout"] = "completed"
            cleanup_returncode = returncode_at_timeout
            process_state_after_cleanup_timeout: Literal["running", "exited"] | None = None
            if returncode_at_timeout is None:
                process.kill()
                try:
                    cleanup_returncode = process.wait(timeout=_PROCESS_TIMEOUT_SECONDS)
                except subprocess.TimeoutExpired:
                    cleanup = "timeout"
                    cleanup_returncode = process.poll()
                    process_state_after_cleanup_timeout = "running" if cleanup_returncode is None else "exited"
            safe_message = _render_init_timeout(
                returncode_at_timeout=returncode_at_timeout,
                cleanup=cleanup,
                cleanup_returncode=cleanup_returncode,
                process_state_after_cleanup_timeout=process_state_after_cleanup_timeout,
            )
            pytest.fail(safe_message, pytrace=False)

        stdout_handle.seek(0)
        stderr_handle.seek(0)
        stdout_bytes = stdout_handle.read()
        stderr_bytes = stderr_handle.read()
        stdout = stdout_bytes.decode("utf-8", errors="strict")
        stderr = stderr_bytes.decode("utf-8", errors="strict")
        return _InitProcessResult(
            returncode=returncode,
            stdout=stdout,
            stderr=stderr,
        )


def _assert_init_result(
    result: _InitProcessResult,
    *,
    expected_returncode: int,
    expected_mode: str | None,
) -> None:
    """断言 init 退出码与可选公开 mode，不回显 captured output。

    :param result: CLI 完成结果。
    :param expected_returncode: 预期退出码。
    :param expected_mode: 成功时预期 mode；``None`` 表示不检查。
    :returns: ``None``。
    :raises AssertionError: 退出码或 mode 不匹配时抛出安全错误。
    """

    if result.returncode != expected_returncode:
        raise AssertionError(f"init return code mismatch: expected={expected_returncode} actual={result.returncode}")
    if expected_mode is not None and f"mode={expected_mode}" not in result.stdout:
        raise AssertionError(f"init did not report expected mode name: {expected_mode}")


def _install_scripted_init_process(
    monkeypatch: pytest.MonkeyPatch,
    process: _ScriptedInitProcess,
) -> tuple[_ScriptedInitPopenFactory, _TemporaryHandleRecorder]:
    """安装 deterministic Popen 与 tracked anonymous TemporaryFile owners。

    :param monkeypatch: pytest 属性替换夹具。
    :param process: 本次 `_run_init` 使用的 scripted process。
    :returns: ``(Popen recorder, temporary-handle recorder)``。
    :raises Exception: monkeypatch 安装失败时透传。
    """

    handle_recorder = _TemporaryHandleRecorder()
    process_factory = _ScriptedInitPopenFactory(process)
    monkeypatch.setattr(tempfile, "TemporaryFile", handle_recorder)
    monkeypatch.setattr(subprocess, "Popen", process_factory)
    return process_factory, handle_recorder


def test_run_init_uses_binary_anonymous_handles_and_returns_typed_utf8_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """成功路径保留 argv/cwd/env、binary Popen 与 strict UTF-8 output contract。

    :param monkeypatch: pytest 属性替换夹具。
    :returns: ``None``。
    :raises AssertionError: process、handle、typed result 或 UTF-8 contract 漂移时抛出。
    """

    process = _ScriptedInitProcess(
        wait_outcomes=(0,),
        poll_outcomes=(),
        stdout="初始化成功 mode=first\n".encode("utf-8", errors="strict"),
        stderr="严格错误通道\n".encode("utf-8", errors="strict"),
        sensitive_value="unused-sensitive-probe",
    )
    process_factory, handle_recorder = _install_scripted_init_process(
        monkeypatch,
        process,
    )
    workspace_root = Path("/owner-test/workspace")
    environment = {"OWNER_TEST": "1"}
    input_text = "14\n输入\n"

    result = _run_init(
        workspace_root,
        environment,
        flags=("--overwrite",),
        input_text=input_text,
    )

    assert result == _InitProcessResult(
        returncode=0,
        stdout="初始化成功 mode=first\n",
        stderr="严格错误通道\n",
    )
    assert tuple(field.name for field in fields(_InitProcessResult)) == (
        "returncode",
        "stdout",
        "stderr",
    )
    assert process_factory.arguments == (
        sys.executable,
        "-u",
        "-m",
        "dayu.cli",
        "init",
        "--base",
        str(workspace_root),
        "--overwrite",
    )
    assert process_factory.cwd == _REPOSITORY_ROOT
    assert process_factory.environment is environment
    assert process_factory.stdin_payload == input_text.encode("utf-8", errors="strict")
    assert process_factory.shell is False
    assert process_factory.close_fds is True
    assert process_factory.text is False
    assert process.wait_calls == [_PROCESS_TIMEOUT_SECONDS]
    assert process.poll_calls == 0
    assert process.kill_calls == 0
    assert handle_recorder.modes == ["w+b", "w+b", "w+b"]
    assert len(handle_recorder.handles) == 3
    stdin_handle, stdout_handle, stderr_handle = handle_recorder.handles
    assert stdin_handle.flush_count == 1
    assert stdin_handle.seek_calls[0] == (0, 0)
    assert stdout_handle.read_count == 1
    assert stderr_handle.read_count == 1
    assert all(handle.closed for handle in handle_recorder.handles)


def test_run_init_returns_ordinary_nonzero_as_typed_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ordinary nonzero 不得被投影成 timeout 或丢弃 stdout/stderr。

    :param monkeypatch: pytest 属性替换夹具。
    :returns: ``None``。
    :raises AssertionError: ordinary process result 被错误重分类时抛出。
    """

    process = _ScriptedInitProcess(
        wait_outcomes=(7,),
        poll_outcomes=(),
        stdout=b"ordinary-output",
        stderr=b"ordinary-error",
        sensitive_value="unused-sensitive-probe",
    )
    _, handle_recorder = _install_scripted_init_process(monkeypatch, process)

    result = _run_init(Path("/owner-test/nonzero"), {"OWNER_TEST": "1"})

    assert result == _InitProcessResult(
        returncode=7,
        stdout="ordinary-output",
        stderr="ordinary-error",
    )
    with pytest.raises(AssertionError, match="expected=0 actual=7") as raised:
        _assert_init_result(result, expected_returncode=0, expected_mode=None)
    assert "ordinary-output" not in str(raised.value)
    assert "ordinary-error" not in str(raised.value)
    assert all(handle.closed for handle in handle_recorder.handles)


def test_run_init_strict_utf8_rejects_invalid_input_before_popen(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """stdin strict UTF-8 encode 失败必须发生在 CLI 启动前并关闭三个 handles。

    :param monkeypatch: pytest 属性替换夹具。
    :returns: ``None``。
    :raises AssertionError: 非法 input 启动 process 或遗留 handle 时抛出。
    """

    process = _ScriptedInitProcess(
        wait_outcomes=(0,),
        poll_outcomes=(),
        stdout=b"",
        stderr=b"",
        sensitive_value="unused-sensitive-probe",
    )
    process_factory, handle_recorder = _install_scripted_init_process(
        monkeypatch,
        process,
    )

    with pytest.raises(UnicodeEncodeError):
        _run_init(
            Path("/owner-test/invalid-input"),
            {"OWNER_TEST": "1"},
            input_text="\ud800",
        )

    assert process_factory.call_count == 0
    assert handle_recorder.modes == ["w+b", "w+b", "w+b"]
    assert all(handle.closed for handle in handle_recorder.handles)


def test_run_init_strict_utf8_rejects_invalid_output_after_reading_both_channels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """stdout/stderr 都从 handles 读取后按 strict UTF-8 解码，禁止 replacement。

    :param monkeypatch: pytest 属性替换夹具。
    :returns: ``None``。
    :raises AssertionError: invalid UTF-8 被接受、漏读 channel 或遗留 handle 时抛出。
    """

    input_sentinel = secrets.token_urlsafe(32)
    process = _ScriptedInitProcess(
        wait_outcomes=(0,),
        poll_outcomes=(),
        stdout=b"\xff",
        stderr=b"valid-stderr",
        sensitive_value=input_sentinel,
    )
    _, handle_recorder = _install_scripted_init_process(monkeypatch, process)

    with pytest.raises(UnicodeDecodeError) as raised:
        _run_init(
            Path("/owner-test/invalid-output"),
            {"OWNER_TEST": "1"},
            input_text=f"6\n{input_sentinel}\ny\n",
        )

    if input_sentinel in repr(raised.value):
        raise AssertionError("strict UTF-8 failure retained the input sentinel")
    _, stdout_handle, stderr_handle = handle_recorder.handles
    assert stdout_handle.read_count == 1
    assert stderr_handle.read_count == 1
    assert all(handle.closed for handle in handle_recorder.handles)


@pytest.mark.parametrize(
    (
        "wait_outcomes",
        "poll_outcomes",
        "expected_wait_calls",
        "expected_poll_calls",
        "expected_kill_calls",
        "expected_message",
    ),
    (
        (
            ("timeout",),
            (1,),
            1,
            1,
            0,
            "category=dayu_cli_init_timeout timeout_seconds=180 "
            "returncode_at_timeout=1 cleanup=completed cleanup_returncode=1",
        ),
        (
            ("timeout", -9),
            (None,),
            2,
            1,
            1,
            "category=dayu_cli_init_timeout timeout_seconds=180 "
            "returncode_at_timeout=not_exited cleanup=completed cleanup_returncode=-9",
        ),
        (
            ("timeout", "timeout"),
            (None, None),
            2,
            2,
            1,
            "category=dayu_cli_init_timeout timeout_seconds=180 "
            "returncode_at_timeout=not_exited cleanup=timeout cleanup_returncode=not_available "
            "process_state_after_cleanup_timeout=running",
        ),
        (
            ("timeout", "timeout"),
            (None, 23),
            2,
            2,
            1,
            "category=dayu_cli_init_timeout timeout_seconds=180 "
            "returncode_at_timeout=not_exited cleanup=timeout cleanup_returncode=23 "
            "process_state_after_cleanup_timeout=exited",
        ),
    ),
)
def test_run_init_timeout_has_safe_projection_and_single_bounded_cleanup(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    wait_outcomes: tuple[_WaitOutcome, ...],
    poll_outcomes: tuple[int | None, ...],
    expected_wait_calls: int,
    expected_poll_calls: int,
    expected_kill_calls: int,
    expected_message: str,
) -> None:
    """timeout 状态机锁定 deadline/cleanup事实且不泄漏 raw process material。

    :param monkeypatch: pytest 属性替换夹具。
    :param capsys: pytest stdout/stderr 捕获夹具。
    :param wait_outcomes: initial/cleanup wait 的 scripted 结果。
    :param poll_outcomes: deadline/post-cleanup poll 的 scripted 结果。
    :param expected_wait_calls: 预期 bounded wait 次数。
    :param expected_poll_calls: 预期 nonblocking poll 次数。
    :param expected_kill_calls: 预期 direct process kill 次数。
    :param expected_message: 精确的唯一 safe timeout projection。
    :returns: ``None``。
    :raises AssertionError: 状态投影、调用次数、handle lifetime 或 non-disclosure 漂移时抛出。
    """

    sentinel = secrets.token_urlsafe(32)
    canary = _github_actions_canary("1")
    sensitive_input = f"{canary}:{sentinel}"
    process = _ScriptedInitProcess(
        wait_outcomes=wait_outcomes,
        poll_outcomes=poll_outcomes,
        stdout=f"stdout-{sensitive_input}".encode("utf-8", errors="strict"),
        stderr=f"stderr-{sensitive_input}".encode("utf-8", errors="strict"),
        sensitive_value=sensitive_input,
    )
    _, handle_recorder = _install_scripted_init_process(monkeypatch, process)
    workspace_root = Path(f"/owner-test/path-{sentinel}")

    with pytest.raises(pytest.fail.Exception) as raised:
        _run_init(
            workspace_root,
            {"SENSITIVE_ENV": sensitive_input},
            flags=(f"--sensitive-{sentinel}",),
            input_text=f"6\n{sensitive_input}\ny\n",
        )

    message = str(raised.value)
    assert message == expected_message
    forbidden_material = (
        sentinel,
        canary,
        sensitive_input,
        str(workspace_root),
        str(_REPOSITORY_ROOT),
        "sensitive-cli-argv",
        "stdin",
        "stdout",
        "stderr",
        "TimeoutExpired",
    )
    for forbidden in forbidden_material:
        if forbidden in message or forbidden in repr(raised.value):
            raise AssertionError("safe timeout projection exposed forbidden process material")
    captured = capsys.readouterr()
    if sentinel in captured.out or sentinel in captured.err or canary in captured.out or canary in captured.err:
        raise AssertionError("timeout failure capture exposed the input sentinel")
    assert process.wait_calls == [_PROCESS_TIMEOUT_SECONDS] * expected_wait_calls
    assert process.poll_calls == expected_poll_calls
    assert process.kill_calls == expected_kill_calls
    assert len(process.timeout_exceptions) == sum(outcome == "timeout" for outcome in wait_outcomes)
    for raw_timeout in process.timeout_exceptions:
        raw_output = raw_timeout.output
        if (
            sentinel not in str(raw_timeout)
            or canary not in str(raw_timeout)
            or not isinstance(raw_output, bytes)
            or sensitive_input.encode("utf-8", errors="strict") not in raw_output
        ):
            raise AssertionError("raw timeout probe did not contain the sensitive process material")
    assert len(handle_recorder.handles) == 3
    _, stdout_handle, stderr_handle = handle_recorder.handles
    assert stdout_handle.read_count == 0
    assert stderr_handle.read_count == 0
    assert all(handle.closed for handle in handle_recorder.handles)


def test_github_actions_canary_freezes_domain_vector_determinism_and_shape() -> None:
    """冻结完整 domain bytes、single NUL、run-id canonicalization 与已知向量。

    :returns: ``None``。
    :raises AssertionError: canary bytes、算法、canonicalization、prefix 或 shape 漂移时抛出。
    """

    assert len(_WINDOWS_CANARY_DOMAIN) == 31
    assert _WINDOWS_CANARY_DOMAIN[:-1] == ("dayu-ar-f07-win4-r12-canary-v1".encode("ascii", errors="strict"))
    assert _WINDOWS_CANARY_DOMAIN[-1] == 0
    assert _WINDOWS_CANARY_DOMAIN.count(bytes((0,))) == 1
    known_vector = _github_actions_canary("1")
    assert known_vector == ("sk-dayu-test-b8f2210d1ead3aac3a52408adb9de03c4e848d4c101f790e218ecc76e3350b97")
    assert _github_actions_canary("0001") == known_vector
    assert _github_actions_canary("1") == known_vector
    second_vector = _github_actions_canary("2")
    assert second_vector != known_vector
    assert second_vector.startswith(_WINDOWS_CANARY_PREFIX)
    digest = second_vector.removeprefix(_WINDOWS_CANARY_PREFIX)
    assert len(digest) == 64
    assert set(digest) <= set("0123456789abcdef")


@pytest.mark.parametrize(
    "environment",
    (
        {_GITHUB_ACTIONS_ENV_NAME: _GITHUB_ACTIONS_ENABLED},
        {
            _GITHUB_ACTIONS_ENV_NAME: _GITHUB_ACTIONS_ENABLED,
            _GITHUB_RUN_ID_ENV_NAME: "",
        },
        {
            _GITHUB_ACTIONS_ENV_NAME: _GITHUB_ACTIONS_ENABLED,
            _GITHUB_RUN_ID_ENV_NAME: "abc",
        },
        {
            _GITHUB_ACTIONS_ENV_NAME: _GITHUB_ACTIONS_ENABLED,
            _GITHUB_RUN_ID_ENV_NAME: "0",
        },
        {
            _GITHUB_ACTIONS_ENV_NAME: _GITHUB_ACTIONS_ENABLED,
            _GITHUB_RUN_ID_ENV_NAME: "-1",
        },
        {
            _GITHUB_ACTIONS_ENV_NAME: _GITHUB_ACTIONS_ENABLED,
            _GITHUB_RUN_ID_ENV_NAME: "１２",
        },
    ),
)
def test_github_actions_canary_fails_closed_without_random_fallback(
    monkeypatch: pytest.MonkeyPatch,
    environment: dict[str, str],
) -> None:
    """GitHub Actions 缺失/空/非十进制/非正 run id 必须在 CLI 前 fail closed。

    :param monkeypatch: pytest 属性替换夹具。
    :param environment: 当前 invalid workflow environment。
    :returns: ``None``。
    :raises AssertionError: selector 随机 fallback、暴露 raw value 或接受非法值时抛出。
    """

    forbidden_random = _ForbiddenTokenFactory()
    monkeypatch.setattr(secrets, "token_urlsafe", forbidden_random)

    with pytest.raises(AssertionError, match="GITHUB_RUN_ID") as raised:
        _select_windows_test_canary(environment)

    raw_run_id = environment.get(_GITHUB_RUN_ID_ENV_NAME)
    if raw_run_id and raw_run_id in str(raised.value):
        raise AssertionError("workflow canary validation exposed the invalid run id")
    assert forbidden_random.calls == 0


def test_github_actions_canary_uses_public_run_id_without_random_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """合法 workflow path 只使用公开 run id 的 deterministic canary。

    :param monkeypatch: pytest 属性替换夹具。
    :returns: ``None``。
    :raises AssertionError: workflow path 使用 random fallback 或结果不确定时抛出。
    """

    forbidden_random = _ForbiddenTokenFactory()
    monkeypatch.setattr(secrets, "token_urlsafe", forbidden_random)
    environment = {
        _GITHUB_ACTIONS_ENV_NAME: _GITHUB_ACTIONS_ENABLED,
        _GITHUB_RUN_ID_ENV_NAME: "0001",
    }

    selected = _select_windows_test_canary(environment)

    assert selected == _github_actions_canary("1")
    assert forbidden_random.calls == 0


def test_local_windows_canary_remains_random_and_ignores_run_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """非 GitHub Actions local path 每次继续请求 32 bytes 的随机 token。

    :param monkeypatch: pytest 属性替换夹具。
    :returns: ``None``。
    :raises AssertionError: local path 使用 run id 或不再请求随机 token 时抛出。
    """

    token_factory = _ScriptedTokenFactory(("local-token-one", "local-token-two"))
    monkeypatch.setattr(secrets, "token_urlsafe", token_factory)
    environment = {
        _GITHUB_ACTIONS_ENV_NAME: "false",
        _GITHUB_RUN_ID_ENV_NAME: "1",
    }

    first = _select_windows_test_canary(environment)
    second = _select_windows_test_canary(environment)

    assert first == "local-token-one"
    assert second == "local-token-two"
    assert first != second
    assert token_factory.calls == [32, 32]


def _tree_digest(root: Path) -> str:
    """计算 ordinary tree 的 path/type/identity/content digest。

    :param root: ordinary tree 根；允许不存在。
    :returns: SHA-256 hex digest。
    :raises OSError: 遍历、stat 或读取失败时抛出。
    """

    digest = hashlib.sha256()
    if not root.exists():
        digest.update(b"ABSENT")
        return digest.hexdigest()
    paths = (root, *sorted(root.rglob("*")))
    for path in paths:
        path_stat = path.lstat()
        relative = "." if path == root else path.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(f"|{path_stat.st_mode}|{path_stat.st_dev}|{path_stat.st_ino}|".encode("ascii"))
        if stat.S_ISREG(path_stat.st_mode):
            digest.update(path.read_bytes())
    return digest.hexdigest()


def _path_identity(path: Path) -> tuple[int, int, int]:
    """读取 no-follow filesystem identity。

    :param path: 已存在路径。
    :returns: ``(device, inode, mode)``。
    :raises OSError: lstat 失败时抛出。
    """

    path_stat = path.lstat()
    return path_stat.st_dev, path_stat.st_ino, path_stat.st_mode


def _validate_published_config(workspace_root: Path, validation_root: Path) -> None:
    """用真实 ConfigLoader、Service discovery 与 13-scene contract 重载配置。

    :param workspace_root: 已发布 workspace。
    :param validation_root: Fins side effect 专用 test-private root。
    :returns: ``None``。
    :raises Exception: 任一 production config/discovery/scene contract 失败时透传。
    """

    validation_root.mkdir()
    runtime_config = ConfigLoader().load(workspace_config_dir=workspace_root / "config")
    if runtime_config.models.models["ollama"].model != "qwen3:8b":
        raise AssertionError("published Ollama model selection mismatch")
    effective_configs = assemble_effective_tool_provider_configs(
        tuple(runtime_config.tool_discovery.providers.values()),
        workspace_root=workspace_root,
        fins_workspace_root_override=validation_root.resolve(strict=True),
    )
    discovered = discover_service_tools(effective_configs)
    catalog = SceneToolCatalog.from_tool_bundle(discovered.tool_bundle)
    for scene_id in sorted(PRODUCTION_RUNTIME_MANIFEST_BASENAMES):
        prepare_scene(
            ScenePrepareRequest(
                scene_id=scene_id,
                scene_manifest_root=workspace_root / "config" / "prompts" / "manifests",
                prompt_asset_root=workspace_root / "config" / "prompts",
                context_slot_values={
                    _CURRENT_TIME_SLOT: "",
                    _FINS_DEFAULT_SUBJECT_SLOT: "",
                },
                available_tools=catalog,
            )
        )


def _start_init_process(
    workspace_root: Path,
    environment: dict[str, str],
) -> subprocess.Popen[str]:
    """启动已写入完整 stdin 的真实 init Popen。

    :param workspace_root: 目标 workspace。
    :param environment: 隔离子进程环境。
    :returns: 仍在运行的 text-mode Popen。
    :raises OSError: 子进程创建或 stdin 写入失败时抛出。
    """

    process = subprocess.Popen(
        (
            sys.executable,
            "-u",
            "-m",
            "dayu.cli",
            "init",
            "--base",
            str(workspace_root),
        ),
        cwd=_REPOSITORY_ROOT,
        env=environment,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="strict",
    )
    if process.stdin is None:
        raise AssertionError("init subprocess stdin pipe is missing")
    process.stdin.write(_OLLAMA_INPUT)
    process.stdin.close()
    process.stdin = None
    return process


def _wait_for_lock_notification(process: subprocess.Popen[str]) -> None:
    """在 bounded timeout 内读取公开 waiting notification。

    :param process: 已启动且 stdout 为 pipe 的 init。
    :returns: ``None``。
    :raises AssertionError: 通知前进程退出、EOF 或 timeout 时抛出。
    """

    stdout = process.stdout
    if stdout is None:
        raise AssertionError("init subprocess stdout pipe is missing")
    deadline = time.monotonic() + _WAIT_TIMEOUT_SECONDS
    selector = selectors.DefaultSelector()
    selector.register(stdout, selectors.EVENT_READ)
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise AssertionError("timed out waiting for public workspace lock notification")
            if not selector.select(remaining):
                raise AssertionError("timed out waiting for public workspace lock notification")
            line = stdout.readline()
            if line == "":
                raise AssertionError(f"init exited before lock notification: returncode={process.poll()}")
            if "正在等待此 workspace lock" in line:
                return
    finally:
        selector.close()


def _finish_init_process(process: subprocess.Popen[str]) -> None:
    """等待 init 子进程成功并排空剩余 pipes。

    :param process: waiting notification 后的真实 init。
    :returns: ``None``。
    :raises subprocess.TimeoutExpired: 进程未在 bounded timeout 内结束时抛出。
    :raises AssertionError: 进程失败时抛出安全错误。
    """

    return_code = process.wait(timeout=_PROCESS_TIMEOUT_SECONDS)
    if process.stdout is not None:
        process.stdout.read()
    if process.stderr is not None:
        process.stderr.read()
    if return_code != 0:
        raise AssertionError(f"queued init failed: returncode={return_code}")


@pytest.mark.skipif(os.name != "posix", reason="真实 POSIX init smoke")
def test_prewarm_subprocess_has_exact_imports_and_zero_external_mutation(
    tmp_path: Path,
) -> None:
    """隔离进程证明 exact transitive imports、连续稳定、零网络与零外部 mutation。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: subprocess 或任一 prewarm contract 失败时抛出。
    """

    sentinel_root = tmp_path / "sentinel-workspace"
    _write_text(sentinel_root / "nested" / "value.txt", "unchanged")
    environment = _subprocess_environment(tmp_path / "home")
    script = r"""
import hashlib
import importlib
import os
import socket
import sys
from pathlib import Path
from unittest import mock

import dayu.cli.commands.init as init_command

root = Path(sys.argv[1])

def digest_tree() -> str:
    digest = hashlib.sha256()
    for path in (root, *sorted(root.rglob("*"))):
        path_stat = path.lstat()
        relative = "." if path == root else path.relative_to(root).as_posix()
        digest.update(f"{relative}|{path_stat.st_mode}|{path_stat.st_dev}|{path_stat.st_ino}|".encode())
        if path.is_file():
            digest.update(path.read_bytes())
    return digest.hexdigest()

roots = (
    "dayu.cli.commands.interactive",
    "dayu.cli.commands.prompt",
)
deleted = (
    "dayu.cli.dependency_setup",
    "dayu.cli.interactive_ui",
    "dayu.cli.commands.write",
)
assert all(name not in sys.modules for name in (*roots, *deleted))
assert "dayu.cli.session_execution" not in sys.modules
assert "dayu.service.entrypoint_runtime" not in sys.modules
before_tree = digest_tree()
before_environment = dict(os.environ)
calls = []
real_import = importlib.import_module

def record_import(name: str):
    calls.append(name)
    return real_import(name)

network_connect = mock.Mock(side_effect=AssertionError("network connect attempted"))
network_create = mock.Mock(side_effect=AssertionError("network create attempted"))
network_resolve = mock.Mock(side_effect=AssertionError("network resolve attempted"))
with (
    mock.patch.object(init_command.importlib, "import_module", side_effect=record_import),
    mock.patch.object(socket.socket, "connect", network_connect),
    mock.patch.object(socket, "create_connection", network_create),
    mock.patch.object(socket, "getaddrinfo", network_resolve),
):
    init_command._run_init_prewarm()
    init_command._run_init_prewarm()

assert calls == [*roots, *roots]
assert all(name in sys.modules for name in roots)
assert "dayu.cli.session_execution" in sys.modules
assert "dayu.service.entrypoint_runtime" in sys.modules
assert all(name not in sys.modules for name in deleted)
assert network_connect.call_count == 0
assert network_create.call_count == 0
assert network_resolve.call_count == 0
assert before_tree == digest_tree()
assert before_environment == dict(os.environ)
print("PREWARM_SMOKE_PASS")
"""

    result = subprocess.run(
        (sys.executable, "-u", "-c", script, str(sentinel_root)),
        cwd=_REPOSITORY_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=_PROCESS_TIMEOUT_SECONDS,
        check=False,
    )

    if result.returncode != 0 or result.stdout.strip() != "PREWARM_SMOKE_PASS":
        raise AssertionError(f"isolated prewarm smoke failed: returncode={result.returncode}")


@pytest.mark.skipif(os.name != "posix", reason="真实 POSIX init smoke")
def test_posix_real_four_state_config_scene_and_reset_sentinels(tmp_path: Path) -> None:
    """真实 POSIX FIRST→PRESERVE→OVERWRITE→RESET No/Yes 保持完整契约。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises Exception: CLI、ConfigLoader、scene 或 sentinel contract 失败时抛出。
    """

    workspace_root = tmp_path / "workspace"
    environment = _subprocess_environment(tmp_path / "home")

    first = _run_init(workspace_root, environment)
    _assert_init_result(first, expected_returncode=0, expected_mode="first")
    assert not (workspace_root / "portfolio").exists()
    assert not (workspace_root / "assets").exists()
    _validate_published_config(workspace_root, tmp_path / "first-validation")

    user_file = workspace_root / "config" / "user-owned.txt"
    user_manifest = workspace_root / "config" / "prompts" / "manifests" / "user-owned.json"
    missing_root_config = workspace_root / "config" / "tool_discovery.json"
    missing_prompt = workspace_root / "config" / "prompts" / "base" / "fact_rules.md"
    _write_text(user_file, "user-file")
    _write_text(user_manifest, '{"owner":"user"}')
    missing_root_config.unlink()
    missing_prompt.unlink()

    preserve = _run_init(workspace_root, environment)
    _assert_init_result(preserve, expected_returncode=0, expected_mode="preserve")
    assert user_file.read_text(encoding="utf-8") == "user-file"
    assert user_manifest.read_text(encoding="utf-8") == '{"owner":"user"}'
    assert missing_root_config.read_bytes() == (
        _REPOSITORY_ROOT / "dayu" / "config" / "tool_discovery.json"
    ).read_bytes()
    assert (
        missing_prompt.read_bytes()
        == (_REPOSITORY_ROOT / "dayu" / "config" / "prompts" / "base" / "fact_rules.md").read_bytes()
    )

    (workspace_root / "config" / "execution_profiles.json").write_bytes(b"{")
    overwrite = _run_init(workspace_root, environment, flags=("--overwrite",))
    _assert_init_result(overwrite, expected_returncode=0, expected_mode="overwrite")
    assert not user_file.exists()
    assert not user_manifest.exists()
    assert missing_prompt.is_file()
    assert not (workspace_root / "assets").exists()

    portfolio_sentinel = workspace_root / "portfolio" / "sentinel.bin"
    assets_sentinel = workspace_root / "assets" / "sentinel.bin"
    _write_text(portfolio_sentinel, "portfolio-sentinel")
    _write_text(assets_sentinel, "assets-sentinel")
    _write_text(workspace_root / ".dayu" / "state.bin", "reset-me")
    portfolio_identity = _path_identity(portfolio_sentinel)
    assets_identity = _path_identity(assets_sentinel)
    before_reset_no = _tree_digest(workspace_root)

    reset_no = _run_init(
        workspace_root,
        environment,
        flags=("--reset",),
        input_text="n\n",
    )
    _assert_init_result(reset_no, expected_returncode=0, expected_mode=None)
    assert "reset cancelled" in reset_no.stdout
    assert _tree_digest(workspace_root) == before_reset_no

    reset_yes = _run_init(
        workspace_root,
        environment,
        flags=("--reset",),
        input_text=f"y\n{_OLLAMA_INPUT}",
    )
    _assert_init_result(reset_yes, expected_returncode=0, expected_mode="reset")
    assert not (workspace_root / ".dayu").exists()
    assert portfolio_sentinel.read_text(encoding="utf-8") == "portfolio-sentinel"
    assert assets_sentinel.read_text(encoding="utf-8") == "assets-sentinel"
    assert _path_identity(portfolio_sentinel) == portfolio_identity
    assert _path_identity(assets_sentinel) == assets_identity
    _validate_published_config(workspace_root, tmp_path / "reset-validation")


@pytest.mark.skipif(os.name != "posix", reason="真实 POSIX init smoke")
def test_posix_real_ordinary_root_overwrite_reset_matrix(
    tmp_path: Path,
) -> None:
    """真实 CLI 以精确 destructive mode 修复 ordinary-file managed roots。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises Exception: mode、最终 tree、ConfigLoader 或非 init-owned 保留失败时抛出。
    """

    environment = _subprocess_environment(tmp_path / "home")
    overwrite_root = tmp_path / "overwrite-workspace"
    overwrite_root.mkdir()
    _write_text(overwrite_root / "config", "ordinary-config-file")
    dayu_state = overwrite_root / ".dayu" / "state.bin"
    _write_text(dayu_state, "stable-state")
    dayu_identity = _path_identity(overwrite_root / ".dayu")

    overwrite = _run_init(
        overwrite_root,
        environment,
        flags=("--overwrite",),
    )
    _assert_init_result(
        overwrite,
        expected_returncode=0,
        expected_mode="overwrite",
    )
    assert (overwrite_root / "config").is_dir()
    assert dayu_state.read_text(encoding="utf-8") == "stable-state"
    assert _path_identity(overwrite_root / ".dayu") == dayu_identity
    _validate_published_config(
        overwrite_root,
        tmp_path / "overwrite-ordinary-validation",
    )

    reset_root = tmp_path / "reset-workspace"
    reset_root.mkdir()
    _write_text(reset_root / "config", "ordinary-config-file")
    _write_text(reset_root / ".dayu", "ordinary-dayu-file")
    portfolio_sentinel = reset_root / "portfolio" / "sentinel.bin"
    assets_sentinel = reset_root / "assets" / "sentinel.bin"
    _write_text(portfolio_sentinel, "portfolio")
    _write_text(assets_sentinel, "assets")
    portfolio_identity = _path_identity(portfolio_sentinel)
    assets_identity = _path_identity(assets_sentinel)

    reset = _run_init(
        reset_root,
        environment,
        flags=("--reset",),
        input_text=f"y\n{_OLLAMA_INPUT}",
    )
    _assert_init_result(reset, expected_returncode=0, expected_mode="reset")
    assert (reset_root / "config").is_dir()
    assert not (reset_root / ".dayu").exists()
    assert portfolio_sentinel.read_text(encoding="utf-8") == "portfolio"
    assert assets_sentinel.read_text(encoding="utf-8") == "assets"
    assert _path_identity(portfolio_sentinel) == portfolio_identity
    assert _path_identity(assets_sentinel) == assets_identity
    _validate_published_config(
        reset_root,
        tmp_path / "reset-ordinary-validation",
    )


@pytest.mark.skipif(os.name != "posix", reason="真实 POSIX profile smoke")
def test_posix_real_profile_mode_marker_and_redaction(tmp_path: Path) -> None:
    """真实 POSIX secret persistence 保持 0600、单 marker block 与输出脱敏。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: profile、publication 或 redaction contract 漂移时抛出。
    """

    home_directory = tmp_path / "home"
    workspace_root = tmp_path / "workspace"
    environment = _subprocess_environment(
        home_directory,
        absent_names=(_OPENAI_ENV_NAME,),
    )
    first_secret = secrets.token_urlsafe(32)
    first = _run_init(
        workspace_root,
        environment,
        input_text=f"6\n{first_secret}\ny\n",
    )
    _assert_init_result(first, expected_returncode=0, expected_mode="first")
    profile_path = home_directory / ".zshrc"
    profile_content = profile_path.read_text(encoding="utf-8")
    if first_secret not in profile_content:
        raise AssertionError("confirmed environment value was not persisted")
    assert stat.S_IMODE(profile_path.stat().st_mode) == 0o600
    assert profile_content.count(_DAYU_BLOCK_BEGIN) == 1
    assert profile_content.count(_DAYU_BLOCK_END) == 1
    assert first_secret not in first.stdout
    assert first_secret not in first.stderr

    second_secret = secrets.token_urlsafe(32)
    second = _run_init(
        workspace_root,
        environment,
        input_text=f"6\n{second_secret}\ny\n",
    )
    _assert_init_result(second, expected_returncode=0, expected_mode="preserve")
    replaced_content = profile_path.read_text(encoding="utf-8")
    if second_secret not in replaced_content or first_secret in replaced_content:
        raise AssertionError("profile marker block was not replaced atomically")
    assert stat.S_IMODE(profile_path.stat().st_mode) == 0o600
    assert replaced_content.count(_DAYU_BLOCK_BEGIN) == 1
    assert replaced_content.count(_DAYU_BLOCK_END) == 1
    assert second_secret not in second.stdout
    assert second_secret not in second.stderr


@pytest.mark.skipif(os.name != "posix", reason="真实 POSIX file_lock smoke")
def test_posix_real_file_lock_waiting_notification_and_two_publishers(tmp_path: Path) -> None:
    """真实 file_lock 以公开通知协调单进程等待和双 queued publisher 串行成功。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises Exception: notification、零提前发布或串行成功 contract 失败时抛出。
    """

    environment = _subprocess_environment(tmp_path / "home")
    first_workspace = tmp_path / "single-waiter"
    first_workspace.mkdir()
    first_lock_path = first_workspace / ".dayu-init.lock"
    first_process: subprocess.Popen[str] | None = None
    try:
        with file_lock(
            first_lock_path,
            timeout_seconds=None,
            create_parent_dirs=False,
        ):
            first_process = _start_init_process(first_workspace, environment)
            _wait_for_lock_notification(first_process)
            assert not (first_workspace / "config").exists()
    finally:
        if first_process is not None:
            _finish_init_process(first_process)
    ConfigLoader().load(workspace_config_dir=first_workspace / "config")

    queued_workspace = tmp_path / "two-waiters"
    initial = _run_init(queued_workspace, environment)
    _assert_init_result(initial, expected_returncode=0, expected_mode="first")
    queued_lock_path = queued_workspace / ".dayu-init.lock"
    before_queue = _tree_digest(queued_workspace / "config")
    first_queued: subprocess.Popen[str] | None = None
    second_queued: subprocess.Popen[str] | None = None
    try:
        with file_lock(
            queued_lock_path,
            timeout_seconds=None,
            create_parent_dirs=False,
        ):
            first_queued = _start_init_process(queued_workspace, environment)
            second_queued = _start_init_process(queued_workspace, environment)
            _wait_for_lock_notification(first_queued)
            _wait_for_lock_notification(second_queued)
            assert _tree_digest(queued_workspace / "config") == before_queue
    finally:
        if first_queued is not None:
            _finish_init_process(first_queued)
        if second_queued is not None:
            _finish_init_process(second_queued)
    ConfigLoader().load(workspace_config_dir=queued_workspace / "config")


@pytest.mark.skipif(platform.system() != "Windows", reason="真实 Windows 四态 smoke")
def test_windows_real_four_state_and_config_reload(tmp_path: Path) -> None:
    """真实 Windows 普通目录在无 POSIX directory fsync 时完成四态与重载。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises Exception: Windows transaction、reset sentinel 或配置重载失败时抛出。
    """

    workspace_root = tmp_path / "workspace"
    environment = _subprocess_environment(tmp_path / "home")
    first = _run_init(workspace_root, environment)
    _assert_init_result(first, expected_returncode=0, expected_mode="first")
    preserve = _run_init(workspace_root, environment)
    _assert_init_result(preserve, expected_returncode=0, expected_mode="preserve")
    overwrite = _run_init(workspace_root, environment, flags=("--overwrite",))
    _assert_init_result(overwrite, expected_returncode=0, expected_mode="overwrite")
    portfolio_sentinel = workspace_root / "portfolio" / "sentinel.txt"
    assets_sentinel = workspace_root / "assets" / "sentinel.txt"
    _write_text(portfolio_sentinel, "portfolio")
    _write_text(assets_sentinel, "assets")
    _write_text(workspace_root / ".dayu" / "state.txt", "reset")
    before_no = _tree_digest(workspace_root)
    reset_no = _run_init(
        workspace_root,
        environment,
        flags=("--reset",),
        input_text="n\n",
    )
    _assert_init_result(reset_no, expected_returncode=0, expected_mode=None)
    assert _tree_digest(workspace_root) == before_no
    reset_yes = _run_init(
        workspace_root,
        environment,
        flags=("--reset",),
        input_text=f"y\n{_OLLAMA_INPUT}",
    )
    _assert_init_result(reset_yes, expected_returncode=0, expected_mode="reset")
    assert not (workspace_root / ".dayu").exists()
    assert portfolio_sentinel.read_text(encoding="utf-8") == "portfolio"
    assert assets_sentinel.read_text(encoding="utf-8") == "assets"
    _validate_published_config(workspace_root, tmp_path / "post-validation")


@pytest.mark.skipif(platform.system() != "Windows", reason="真实 Windows junction smoke")
def test_windows_real_preseeded_junction_fails_closed(tmp_path: Path) -> None:
    """预置 nested junction 必须在发布前 fail closed 且保持外部 sentinel identity。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises Exception: junction 创建、reparse 分类或 fail-closed contract 失败时抛出。
    """

    workspace_root = tmp_path / "workspace"
    config_root = workspace_root / "config"
    junction_parent = config_root / "nested"
    junction_parent.mkdir(parents=True)
    _write_text(config_root / "owner.txt", "public-before")
    external_root = tmp_path / "external"
    external_sentinel = external_root / "sentinel.txt"
    _write_text(external_sentinel, "external-before")
    junction_path = junction_parent / "linked"
    junction_create = subprocess.run(
        ("cmd.exe", "/d", "/c", "mklink", "/J", str(junction_path), str(external_root)),
        capture_output=True,
        text=True,
        check=False,
    )
    if junction_create.returncode != 0:
        raise AssertionError("directory junction creation failed on Windows runner")
    public_identity = _path_identity(config_root)
    external_identity = _path_identity(external_sentinel)
    junction_identity = init_workspace._path_identity(
        junction_path,
        platform_system="Windows",
    )
    assert junction_identity.file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT
    assert junction_identity.reparse_tag != 0
    environment = _subprocess_environment(tmp_path / "home")
    try:
        result = _run_init(workspace_root, environment)
        _assert_init_result(result, expected_returncode=1, expected_mode=None)
        assert "stage=tree_identity" in result.stderr
        assert "retained=none" in result.stderr
        assert _path_identity(config_root) == public_identity
        assert (config_root / "owner.txt").read_text(encoding="utf-8") == "public-before"
        assert _path_identity(external_sentinel) == external_identity
        assert external_sentinel.read_text(encoding="utf-8") == "external-before"
        assert not tuple(workspace_root.glob(".dayu-init-transaction-*"))
    finally:
        if junction_path.exists():
            os.rmdir(junction_path)


@pytest.mark.skipif(platform.system() != "Windows", reason="真实 Windows symlink smoke")
def test_windows_real_symlink_privilege_or_fail_closed(tmp_path: Path) -> None:
    """普通 Windows symlink 仅在精确 1314 privilege error 时 skip，否则 fail closed。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises Exception: 非 privilege 创建错误或 symlink 安全 contract 失败时抛出。
    """

    workspace_root = tmp_path / "workspace"
    config_root = workspace_root / "config"
    external_root = tmp_path / "external"
    external_sentinel = external_root / "sentinel.txt"
    _write_text(external_sentinel, "external")
    linked = config_root / "nested" / "linked"
    linked.parent.mkdir(parents=True)
    try:
        linked.symlink_to(external_root, target_is_directory=True)
    except OSError as exc:
        windows_error = cast(_WindowsOSError, exc)
        if windows_error.winerror == _WINDOWS_PRIVILEGE_NOT_HELD:
            pytest.skip("Windows runner lacks ordinary symlink privilege (winerror=1314)")
        raise
    environment = _subprocess_environment(tmp_path / "home")
    result = _run_init(workspace_root, environment)
    _assert_init_result(result, expected_returncode=1, expected_mode=None)
    assert "stage=tree_identity" in result.stderr
    assert external_sentinel.read_text(encoding="utf-8") == "external"


@pytest.mark.skipif(platform.system() != "Windows", reason="真实 Windows identity smoke")
def test_windows_real_workspace_root_identity_drift_is_rejected(tmp_path: Path) -> None:
    """真实 Windows workspace root 被替换后必须由 orchestrator identity owner 拒绝。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises OSError: 真实 rename/mkdir 失败时透传。
    :raises AssertionError: identity 漂移未拒绝时抛出。
    """

    workspace_root = tmp_path / "workspace"
    identity = init_command._bootstrap_workspace_root(workspace_root)
    displaced_root = tmp_path / "workspace-displaced"
    os.replace(workspace_root, displaced_root)
    workspace_root.mkdir()

    with pytest.raises(init_command.CliInitUsageError, match="identity changed"):
        init_command._require_workspace_identity(identity)


def _run_registry_command(arguments: tuple[str, ...]) -> subprocess.CompletedProcess[str]:
    """运行不打印 registry value 的 Windows ``reg.exe`` 子命令。

    :param arguments: ``reg.exe`` 后的 argument tuple。
    :returns: 捕获输出的完成结果。
    :raises OSError: 进程创建失败时抛出。
    """

    return subprocess.run(
        ("reg.exe", *arguments),
        capture_output=True,
        text=True,
        check=False,
    )


def _delete_registry_value_and_verify_absent(
    *,
    registry_key: str,
    value_name: str,
    command_runner: _RegistryCommandRunner = _run_registry_command,
) -> None:
    """幂等删除 Windows registry value 并证明精确名称已不存在。

    ``reg delete`` 对原本不存在的 value 返回 1，因此最终 cleanup truth 必须由
    delete 后的精确 value query 与父 key 可访问 probe 共同决定，而不能只读取
    delete return code 或把任意 query failure 当作 absent。

    :param registry_key: 目标 registry key。
    :param value_name: 只允许进入诊断的环境变量名。
    :param command_runner: registry command owner；默认使用真实 ``reg.exe``。
    :returns: ``None``。
    :raises AssertionError: 命令返回未分类状态或 value 仍存在时抛出。
    """

    deletion = command_runner(("delete", registry_key, "/v", value_name, "/f"))
    if deletion.returncode not in {0, 1}:
        raise AssertionError(f"registry cleanup command failed for env name: {value_name}")
    verification = command_runner(("query", registry_key, "/v", value_name))
    if verification.returncode == 0:
        raise AssertionError(f"registry cleanup left env name present: {value_name}")
    if verification.returncode != 1:
        raise AssertionError(f"registry cleanup verification failed for env name: {value_name}")
    key_access = command_runner(("query", registry_key))
    if key_access.returncode != 0:
        raise AssertionError(f"registry cleanup key access failed for env name: {value_name}")


@pytest.mark.parametrize("deletion_returncode", (0, 1))
def test_registry_cleanup_accepts_deleted_or_already_absent_value(
    deletion_returncode: int,
) -> None:
    """Cleanup 以 query absent 为真源，兼容实际删除与原本不存在。

    :param deletion_returncode: ``reg delete`` 的成功或 missing exit code。
    :returns: ``None``。
    :raises AssertionError: helper 未执行精确 delete/query 或错误拒绝 absent 时抛出。
    """

    runner = _ScriptedRegistryCommandRunner((deletion_returncode, 1, 0))

    _delete_registry_value_and_verify_absent(
        registry_key=r"HKCU\Environment",
        value_name=_OPENAI_ENV_NAME,
        command_runner=runner,
    )

    assert runner.calls == [
        ("delete", r"HKCU\Environment", "/v", _OPENAI_ENV_NAME, "/f"),
        ("query", r"HKCU\Environment", "/v", _OPENAI_ENV_NAME),
        ("query", r"HKCU\Environment"),
    ]


@pytest.mark.parametrize(
    ("returncodes", "expected_message"),
    (
        ((2,), "registry cleanup command failed"),
        ((0, 0), "registry cleanup left env name present"),
        ((0, 2), "registry cleanup verification failed"),
        ((0, 1, 1), "registry cleanup key access failed"),
    ),
)
def test_registry_cleanup_rejects_unproved_absence_without_command_output(
    returncodes: tuple[int, ...],
    expected_message: str,
) -> None:
    """Cleanup 拒绝未分类状态或仍存在 value，且只投影变量名。

    :param returncodes: scripted delete/query exit codes。
    :param expected_message: 预期安全错误类别。
    :returns: ``None``。
    :raises AssertionError: helper 接受未证明 cleanup 或回显 command output 时抛出。
    """

    runner = _ScriptedRegistryCommandRunner(returncodes)

    with pytest.raises(AssertionError) as raised:
        _delete_registry_value_and_verify_absent(
            registry_key=r"HKCU\Environment",
            value_name=_OPENAI_ENV_NAME,
            command_runner=runner,
        )

    message = str(raised.value)
    assert expected_message in message
    assert _OPENAI_ENV_NAME in message
    assert "test-secret" not in message


@pytest.mark.skipif(platform.system() != "Windows", reason="真实 Windows setx smoke")
def test_windows_real_setx_round_trip_is_name_safe_and_cleaned(tmp_path: Path) -> None:
    """真实 setx/user-env read/cleanup 只向 CLI diagnostic 暴露变量名。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises Exception: setx、registry round-trip、cleanup 或脱敏失败时抛出。
    """

    registry_key = r"HKCU\Environment"
    _delete_registry_value_and_verify_absent(
        registry_key=registry_key,
        value_name=_OPENAI_ENV_NAME,
    )
    sentinel = _select_windows_test_canary(os.environ)
    environment = _subprocess_environment(
        tmp_path / "home",
        absent_names=(_OPENAI_ENV_NAME,),
    )
    try:
        result = _run_init(
            tmp_path / "workspace",
            environment,
            input_text=f"6\n{sentinel}\ny\n",
        )
        _assert_init_result(result, expected_returncode=0, expected_mode="first")
        assert _OPENAI_ENV_NAME in result.stdout
        assert sentinel not in result.stdout
        assert sentinel not in result.stderr
        query = _run_registry_command(("query", registry_key, "/v", _OPENAI_ENV_NAME))
        if query.returncode != 0 or sentinel not in query.stdout:
            raise AssertionError(f"setx round-trip failed for env name: {_OPENAI_ENV_NAME}")
    finally:
        _delete_registry_value_and_verify_absent(
            registry_key=registry_key,
            value_name=_OPENAI_ENV_NAME,
        )


def test_platform_capability_is_explicit() -> None:
    """Smoke profile 只接受计划锁定的 POSIX/Windows 平台。

    :returns: ``None``。
    :raises AssertionError: 本地平台不在锁定集合时抛出。
    """

    assert platform.system() in {"Darwin", "Linux", "Windows"}
    assert isinstance(shutil.rmtree.avoids_symlink_attacks, bool)
    assert errno.EPERM > 0
