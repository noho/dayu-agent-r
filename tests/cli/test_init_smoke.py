"""``dayu-cli init`` 的真实 POSIX/Windows 进程级 smoke。

本模块只通过公开 CLI、真实文件锁和真实平台文件系统证明 S3 工作流；除明确的
prewarm import/network 观察 seam 外，不替换 production owner。
"""

from __future__ import annotations

import errno
import hashlib
import os
import platform
import secrets
import selectors
import shutil
import stat
import subprocess
import sys
import time
from pathlib import Path
from typing import Final, Protocol, cast

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


def _run_init(
    workspace_root: Path,
    environment: dict[str, str],
    *,
    flags: tuple[str, ...] = (),
    input_text: str = _OLLAMA_INPUT,
) -> subprocess.CompletedProcess[str]:
    """以真实 ``python -m dayu.cli`` 运行一次 init。

    :param workspace_root: 目标 workspace。
    :param environment: 隔离子进程环境。
    :param flags: init 追加 flags。
    :param input_text: 完整确定性 stdin。
    :returns: 捕获输出的完成结果。
    :raises subprocess.TimeoutExpired: CLI 超过 bounded test timeout 时抛出。
    """

    return subprocess.run(
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
        input=input_text,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        timeout=_PROCESS_TIMEOUT_SECONDS,
        check=False,
    )


def _assert_init_result(
    result: subprocess.CompletedProcess[str],
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
        raise AssertionError(
            f"init return code mismatch: expected={expected_returncode} actual={result.returncode}"
        )
    if expected_mode is not None and f"mode={expected_mode}" not in result.stdout:
        raise AssertionError(f"init did not report expected mode name: {expected_mode}")


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
        digest.update(
            f"|{path_stat.st_mode}|{path_stat.st_dev}|{path_stat.st_ino}|".encode("ascii")
        )
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
                raise AssertionError(
                    f"init exited before lock notification: returncode={process.poll()}"
                )
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
    script = r'''
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
'''

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
    missing_prompt = workspace_root / "config" / "prompts" / "base" / "fact_rules.md"
    _write_text(user_file, "user-file")
    _write_text(user_manifest, '{"owner":"user"}')
    missing_prompt.unlink()

    preserve = _run_init(workspace_root, environment)
    _assert_init_result(preserve, expected_returncode=0, expected_mode="preserve")
    assert user_file.read_text(encoding="utf-8") == "user-file"
    assert user_manifest.read_text(encoding="utf-8") == '{"owner":"user"}'
    assert missing_prompt.read_bytes() == (
        _REPOSITORY_ROOT / "dayu" / "config" / "prompts" / "base" / "fact_rules.md"
    ).read_bytes()

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
    sentinel = secrets.token_urlsafe(32)
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
