"""dayu.cli.commands.init 四态 orchestrator 测试。"""

from __future__ import annotations

import builtins
import errno
import getpass
import importlib
import io
import json
import os
import platform
import secrets
import shutil
import threading
from collections.abc import Mapping
from pathlib import Path
from types import ModuleType
from typing import Final, TextIO, cast
from unittest.mock import Mock, call

import pytest

import dayu.cli.commands.init as init_command
import dayu.cli.main as cli_main
from dayu.contracts import JsonValue
from dayu.cli.exit_codes import (
    EXIT_FAILURE,
    EXIT_KEYBOARD_INTERRUPT,
    EXIT_SUCCESS,
    EXIT_USAGE_ERROR,
)
from dayu.cli.init_environment import (
    EnvironmentPersistenceEntry,
    EnvironmentPersistenceError,
    EnvironmentPersistenceInterrupted,
    EnvironmentPersistenceResult,
    EnvironmentPersistenceStatus,
    PosixEnvironmentPersistencePlan,
    WindowsEnvironmentPersistencePlan,
)
from dayu.cli.init_workspace import PreparedWorkspaceTransaction
from dayu.runtime.config_loader import ConfigLoader
from dayu.runtime.filelock import file_lock

_WAIT_TIMEOUT_SECONDS: Final[float] = 30.0


class _BrokenStderr:
    """记录诊断尝试并以 ``OSError`` 拒绝 stderr 写入。"""

    def __init__(self, events: list[str]) -> None:
        """初始化 broken stderr。

        :param events: 与 abort wrapper 共用的顺序记录。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self._events = events

    def write(self, text: str) -> int:
        """记录非空写入并抛出 diagnostic I/O 错误。

        :param text: ``print`` 尝试写入的文本。
        :returns: 本函数不返回。
        :raises OSError: 始终模拟 broken stderr。
        """

        if text:
            self._events.append("diagnostic")
        raise OSError(errno.EIO, "stderr write fault")

    def flush(self) -> None:
        """提供 ``print``/解释器要求的无副作用 flush。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        return


class _PrewarmImportFailure:
    """只在 prewarm exact root 上失败的真实 import wrapper。"""

    def __init__(self, secret: str) -> None:
        """初始化 wrapper。

        :param secret: 只能进入异常对象、不得进入 diagnostic 的 sentinel。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self._secret = secret
        self._real_import_module = importlib.import_module

    def __call__(self, name: str, package: str | None = None) -> ModuleType:
        """真实导入其它模块，只拒绝第一个 prewarm root。

        :param name: import root。
        :param package: relative import package。
        :returns: 真实导入模块。
        :raises RuntimeError: 命中 exact prewarm root 时抛出 sentinel 异常。
        """

        if name == "dayu.cli.commands.interactive":
            raise RuntimeError(self._secret)
        return self._real_import_module(name, package)


class _InputSequence:
    """按顺序返回 input 响应并记录 prompts。"""

    def __init__(self, responses: tuple[str, ...]) -> None:
        """初始化响应序列。

        :param responses: 按调用顺序返回的文本。
        :returns: None。
        :raises Exception: 不主动抛出异常。
        """

        self._responses = list(responses)
        self.prompts: list[str] = []

    def __call__(self, prompt: str) -> str:
        """返回下一项响应。

        :param prompt: 用户可见 prompt。
        :returns: 下一项响应。
        :raises EOFError: 响应耗尽时抛出。
        """

        self.prompts.append(prompt)
        if not self._responses:
            raise EOFError
        return self._responses.pop(0)


class _GetpassSequence:
    """按顺序返回隐藏输入；耗尽后默认返回空字符串。"""

    def __init__(self, responses: tuple[str, ...] = ()) -> None:
        """初始化隐藏输入。

        :param responses: 显式响应。
        :returns: None。
        :raises Exception: 不主动抛出异常。
        """

        self._responses = list(responses)
        self.prompts: list[str] = []

    def __call__(
        self,
        prompt: str = "Password: ",
        stream: TextIO | None = None,
    ) -> str:
        """返回下一隐藏值或空字符串。

        :param prompt: 用户可见变量名提示。
        :param stream: getpass 兼容输出流；测试不消费。
        :returns: 隐藏值。
        :raises Exception: 不主动抛出异常。
        """

        del stream
        self.prompts.append(prompt)
        if self._responses:
            return self._responses.pop(0)
        return ""


class _TtySecretInput(io.StringIO):
    """只允许 capability 检查、禁止 secret owner 读取明文行的 TTY fake。"""

    def isatty(self) -> bool:
        """声明当前 test-owned stream 具有 TTY 能力。

        :returns: 始终返回 ``True``。
        :raises Exception: 不主动抛出异常。
        """

        return True

    def readline(self, size: int = -1, /) -> str:
        """拒绝 TTY secret owner 误入明文逐行读取路径。

        :param size: 兼容文本流协议的最大读取长度；测试不消费。
        :returns: 本方法不返回。
        :raises AssertionError: 任何调用都表示 TTY owner path 漂移。
        """

        del size
        raise AssertionError("TTY secret input must not call stdin.readline")


class _FlushRecordingStderr(io.StringIO):
    """记录 redirected secret prompt 的显式 flush 次数。"""

    def __init__(self) -> None:
        """初始化内存 stderr 与 flush 计数。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        super().__init__()
        self.flush_count = 0

    def flush(self) -> None:
        """记录一次 flush 并刷新内存文本流。

        :returns: ``None``。
        :raises OSError: 底层内存文本流刷新失败时透传。
        """

        self.flush_count += 1
        super().flush()


class _InterruptingRedirectedSecretInput(io.StringIO):
    """在 redirected readline 边界抛出指定 KeyboardInterrupt。"""

    def __init__(self, interrupt: KeyboardInterrupt) -> None:
        """初始化中断输入流。

        :param interrupt: 必须保持 identity 透传的用户中断。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        super().__init__()
        self._interrupt = interrupt

    def readline(self, size: int = -1, /) -> str:
        """在首次逐行读取时抛出用户中断。

        :param size: 兼容文本流协议的最大读取长度；测试不消费。
        :returns: 本方法不返回。
        :raises KeyboardInterrupt: 始终抛出初始化时提供的中断。
        """

        del size
        raise self._interrupt


class _EofInput:
    """所有 input 调用都抛 EOF。"""

    def __call__(self, prompt: str) -> str:
        """模拟 stdin EOF。

        :param prompt: 用户可见 prompt。
        :returns: 本函数不返回。
        :raises EOFError: 始终抛出。
        """

        del prompt
        raise EOFError


class _InterruptInput:
    """所有 input 调用都抛 KeyboardInterrupt。"""

    def __call__(self, prompt: str) -> str:
        """模拟用户中断。

        :param prompt: 用户可见 prompt。
        :returns: 本函数不返回。
        :raises KeyboardInterrupt: 始终抛出。
        """

        del prompt
        raise KeyboardInterrupt


class _WaitingPrint:
    """观察 public waiting notification，同时保持真实 print。"""

    def __init__(self) -> None:
        """初始化 waiting event。

        :returns: None。
        :raises Exception: 不主动抛出异常。
        """

        self.waiting = threading.Event()
        self._real_print = builtins.print

    def __call__(self, *values: str, file: TextIO | None = None) -> None:
        """转发 print 并在 waiting 文本出现时置 event。

        :param values: print 文本项。
        :param file: 可选输出流。
        :returns: None。
        :raises OSError: 真实 print 写入失败时透传。
        """

        if any("正在等待此 workspace lock" in value for value in values):
            self.waiting.set()
        self._real_print(*values, file=file)


class _CompetingInitRunner:
    """在线程中执行一个真实 init 并记录退出码。"""

    def __init__(self, workspace_root: Path) -> None:
        """初始化 runner。

        :param workspace_root: 竞争同一 lock 的 workspace。
        :returns: None。
        :raises Exception: 不主动抛出异常。
        """

        self._workspace_root = workspace_root
        self.results: list[int] = []

    def __call__(self) -> None:
        """执行真实 CLI init。

        :returns: None。
        :raises Exception: CLI 未捕获异常时由线程框架报告。
        """

        self.results.append(cli_main.main(("init", "--base", str(self._workspace_root))))


def _install_tty_getpass(
    monkeypatch: pytest.MonkeyPatch,
    responses: tuple[str, ...] = (),
) -> _GetpassSequence:
    """安装确定性 TTY stdin 与隐藏输入序列。

    :param monkeypatch: pytest monkeypatch 夹具。
    :param responses: getpass 按顺序返回的隐藏值。
    :returns: 可检查 prompt 与消费顺序的 getpass 序列。
    :raises Exception: monkeypatch 失败时抛出。
    """

    getpass_sequence = _GetpassSequence(responses)
    monkeypatch.setattr(init_command.sys, "stdin", _TtySecretInput())
    monkeypatch.setattr(getpass, "getpass", getpass_sequence)
    return getpass_sequence


def _install_ollama_inputs(
    monkeypatch: pytest.MonkeyPatch,
    *,
    reset_answer: str | None = None,
) -> _InputSequence:
    """安装 Ollama 选择与空 optional integrations 输入。

    :param monkeypatch: pytest monkeypatch 夹具。
    :param reset_answer: RESET 时先返回的确认输入。
    :returns: 可检查 prompts 的 input sequence。
    :raises Exception: monkeypatch 失败时抛出。
    """

    responses = (
        *((reset_answer,) if reset_answer is not None else ()),
        "14",
        "",
        "",
        "",
    )
    input_sequence = _InputSequence(responses)
    monkeypatch.setattr(builtins, "input", input_sequence)
    _install_tty_getpass(monkeypatch)
    return input_sequence


def _write_text(path: Path, value: str) -> None:
    """创建 parent 并写入 UTF-8 文本。

    :param path: 目标文件。
    :param value: 文本。
    :returns: None。
    :raises OSError: mkdir/write 失败时抛出。
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def _read_json_object(path: Path) -> dict[str, JsonValue]:
    """读取测试 JSON object 的可修改浅复制。

    :param path: JSON 文件路径。
    :returns: string-keyed JSON object。
    :raises AssertionError: 顶层不是 mapping 时抛出。
    :raises OSError: 文件读取失败时抛出。
    """

    value = cast(
        JsonValue,
        json.loads(path.read_text(encoding="utf-8")),
    )
    assert isinstance(value, Mapping)
    return dict(value)


def _write_json(path: Path, value: JsonValue) -> None:
    """写入测试 JSON 值。

    :param path: 目标 JSON 文件。
    :param value: 严格 JSON 值。
    :returns: ``None``。
    :raises OSError: 写入失败时抛出。
    :raises TypeError: fixture 不是 JSON 值时抛出。
    """

    path.write_text(
        f"{json.dumps(value, ensure_ascii=False, indent=2)}\n",
        encoding="utf-8",
    )


def _set_default_execution_profile(
    config_root: Path,
    execution_profile_id: str,
) -> None:
    """修改 workspace 默认 execution profile 引用。

    :param config_root: workspace config 根目录。
    :param execution_profile_id: 已存在的 target profile id。
    :returns: ``None``。
    :raises AssertionError: package fixture shape 非法时抛出。
    :raises OSError: JSON 读写失败时抛出。
    """

    path = config_root / "execution_profiles.json"
    root = _read_json_object(path)
    raw_profiles = root["execution_profiles"]
    assert isinstance(raw_profiles, Mapping)
    assert execution_profile_id in raw_profiles
    root["default_execution_profile_id"] = execution_profile_id
    _write_json(path, root)


def _set_all_environment_values(monkeypatch: pytest.MonkeyPatch) -> None:
    """让模型 required 与所有 optional 环境值都无需交互。

    :param monkeypatch: pytest monkeypatch 夹具。
    :returns: ``None``。
    :raises Exception: monkeypatch 写环境失败时抛出。
    """

    for name in (
        "CUSTOM_OPENAI_API_KEY",
        *init_command.OPTIONAL_ENVIRONMENT_NAMES,
    ):
        monkeypatch.setenv(name, "configured")


def _copy_package_config(tmp_path: Path) -> Path:
    """复制 package config 供 fail-closed 测试隔离修改。

    :param tmp_path: pytest 临时目录。
    :returns: 私有 package config 副本。
    :raises OSError: copytree 失败时抛出。
    """

    destination = tmp_path / "package-config"
    shutil.copytree(init_command._PACKAGE_CONFIG_ROOT, destination)
    return destination


def test_read_secret_input_uses_hidden_getpass_for_tty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """TTY secret 必须只经隐藏输入读取且不得触碰 stdin.readline。

    :param monkeypatch: pytest monkeypatch 夹具。
    :returns: ``None``。
    :raises AssertionError: capability 分流、prompt 或返回值漂移时抛出。
    """

    secret = secrets.token_urlsafe(24)
    prompt = "PROVIDER_API_KEY（输入隐藏，不写日志）: "
    getpass_sequence = _install_tty_getpass(monkeypatch, (secret,))

    assert init_command._read_secret_input(prompt) == secret
    assert getpass_sequence.prompts == [prompt]


@pytest.mark.parametrize(
    ("line_ending", "expected_trailer", "remaining"),
    (
        ("\n", "", "next-line\n"),
        ("\r\n", "", "next-line\n"),
        ("\r", "\r", ""),
        (" \t\n", " \t", "next-line\n"),
    ),
    ids=("lf", "crlf", "bare-cr", "other-trailing-whitespace"),
)
def test_read_secret_input_redirected_reads_exactly_one_logical_line(
    monkeypatch: pytest.MonkeyPatch,
    line_ending: str,
    expected_trailer: str,
    remaining: str,
) -> None:
    """Redirected secret 只读一行、条件移除 CRLF 并立即刷新 prompt。

    :param monkeypatch: pytest monkeypatch 夹具。
    :param line_ending: 当前 case 的尾随字符。
    :param expected_trailer: logical line ending 移除后应保留的尾随字符。
    :param remaining: helper 返回后仍应留在 stdin 的内容。
    :returns: ``None``。
    :raises AssertionError: 读取次数、字符保留、prompt、flush 或 getpass 分流漂移时抛出。
    """

    secret = secrets.token_urlsafe(24)
    prompt = "PROVIDER_API_KEY（重定向输入）: "
    redirected_stdin = io.StringIO(f"{secret}{line_ending}{remaining}")
    redirected_stderr = _FlushRecordingStderr()
    hidden_input = Mock(side_effect=AssertionError("redirected input must not call getpass"))
    monkeypatch.setattr(init_command.sys, "stdin", redirected_stdin)
    monkeypatch.setattr(init_command.sys, "stderr", redirected_stderr)
    monkeypatch.setattr(getpass, "getpass", hidden_input)

    value = init_command._read_secret_input(prompt)

    assert value == f"{secret}{expected_trailer}"
    assert redirected_stdin.read() == remaining
    assert redirected_stderr.getvalue() == prompt
    assert redirected_stderr.flush_count == 1
    assert secret not in redirected_stderr.getvalue()
    hidden_input.assert_not_called()


def test_redirected_secret_owner_is_reused_for_required_and_optional_values(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Required 与 optional 两个调用点必须复用 redirected owner 并保持确认顺序。

    :param monkeypatch: pytest monkeypatch 夹具。
    :param capsys: pytest 输出捕获夹具。
    :returns: ``None``。
    :raises AssertionError: 调用点、输入顺序、typed plan 或 non-disclosure 漂移时抛出。
    """

    required_secret = secrets.token_urlsafe(24)
    optional_secret = secrets.token_urlsafe(24)
    required_name = "OPENAI_API_KEY"
    optional_name = init_command.OPTIONAL_ENVIRONMENT_NAMES[0]
    for name in init_command.OPTIONAL_ENVIRONMENT_NAMES:
        monkeypatch.setenv(name, "already-configured")
    monkeypatch.delenv(required_name, raising=False)
    monkeypatch.delenv(optional_name, raising=False)
    redirected_stdin = io.StringIO(f"{required_secret}\n{optional_secret}\n")
    redirected_stderr = _FlushRecordingStderr()
    confirmation = _InputSequence(("y",))
    hidden_input = Mock(side_effect=AssertionError("redirected input must not call getpass"))
    monkeypatch.setattr(init_command.sys, "stdin", redirected_stdin)
    monkeypatch.setattr(init_command.sys, "stderr", redirected_stderr)
    monkeypatch.setattr(builtins, "input", confirmation)
    monkeypatch.setattr(getpass, "getpass", hidden_input)
    monkeypatch.setattr(init_command.platform, "system", Mock(return_value="Windows"))
    selection = init_command.InitModelSelection(choice=init_command.INIT_MODEL_CHOICES[5])

    plan = init_command._collect_environment_persistence_plan(selection)
    captured = capsys.readouterr()

    assert isinstance(plan, WindowsEnvironmentPersistencePlan)
    assert plan.confirmed is True
    assert plan.entries == (
        EnvironmentPersistenceEntry(name=required_name, value=required_secret),
        EnvironmentPersistenceEntry(name=optional_name, value=optional_secret),
    )
    assert redirected_stdin.read() == ""
    assert redirected_stderr.flush_count == 2
    assert required_name in redirected_stderr.getvalue()
    assert optional_name in redirected_stderr.getvalue()
    assert confirmation.prompts == ["确认持久化这一批环境变量? [y/N]: "]
    assert required_name in captured.out
    assert optional_name in captured.out
    assert required_secret not in captured.out
    assert optional_secret not in captured.out
    assert required_secret not in redirected_stderr.getvalue()
    assert optional_secret not in redirected_stderr.getvalue()
    hidden_input.assert_not_called()


@pytest.mark.parametrize("is_tty", (True, False), ids=("tty", "redirected"))
def test_secret_input_eof_paths_share_value_free_owner_error(
    monkeypatch: pytest.MonkeyPatch,
    is_tty: bool,
) -> None:
    """TTY EOFError 与 redirected empty read 必须收敛为同一 value-free 错误。

    :param monkeypatch: pytest monkeypatch 夹具。
    :param is_tty: 是否验证 TTY hidden-getpass 路径。
    :returns: ``None``。
    :raises AssertionError: EOF 类型、错误文本或 capability 分流漂移时抛出。
    """

    raw_exception_value = secrets.token_urlsafe(24)
    if is_tty:
        monkeypatch.setattr(init_command.sys, "stdin", _TtySecretInput())
        monkeypatch.setattr(
            getpass,
            "getpass",
            Mock(side_effect=EOFError(raw_exception_value)),
        )
    else:
        monkeypatch.setattr(init_command.sys, "stdin", io.StringIO())
        monkeypatch.setattr(
            getpass,
            "getpass",
            Mock(side_effect=AssertionError("redirected input must not call getpass")),
        )

    with pytest.raises(init_command.CliInitOperationError) as raised:
        init_command._read_secret_input("PROVIDER_API_KEY: ")

    assert str(raised.value) == "secret input ended before completion"
    assert raw_exception_value not in str(raised.value)


@pytest.mark.parametrize("is_tty", (True, False), ids=("tty", "redirected"))
def test_secret_input_eof_is_publicly_value_free_and_stops_before_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    is_tty: bool,
) -> None:
    """Secret EOF 的公开失败文本不得泄值，且不得发布 config/trace/audit state。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch 夹具。
    :param capsys: pytest 输出捕获夹具。
    :param is_tty: 是否验证 TTY hidden-getpass 路径。
    :returns: ``None``。
    :raises AssertionError: 退出码、公开文本、后续输入或 publication 漂移时抛出。
    """

    raw_exception_value = secrets.token_urlsafe(24)
    workspace_root = tmp_path / "workspace"
    model_input = _InputSequence(("6",))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(builtins, "input", model_input)
    if is_tty:
        monkeypatch.setattr(init_command.sys, "stdin", _TtySecretInput())
        hidden_input = Mock(side_effect=EOFError(raw_exception_value))
    else:
        monkeypatch.setattr(init_command.sys, "stdin", io.StringIO())
        hidden_input = Mock(side_effect=AssertionError("redirected input must not call getpass"))
    monkeypatch.setattr(getpass, "getpass", hidden_input)

    exit_code = cli_main.main(("init", "--base", str(workspace_root)))
    captured = capsys.readouterr()

    assert exit_code == EXIT_FAILURE
    assert "secret input ended before completion" in captured.err
    assert raw_exception_value not in captured.out
    assert raw_exception_value not in captured.err
    assert len(model_input.prompts) == 1
    assert not (workspace_root / "config").exists()
    assert not (workspace_root / ".dayu").exists()
    if is_tty:
        hidden_input.assert_called_once()
    else:
        hidden_input.assert_not_called()


@pytest.mark.parametrize("is_tty", (True, False), ids=("tty", "redirected"))
def test_secret_input_keyboard_interrupt_preserves_identity(
    monkeypatch: pytest.MonkeyPatch,
    is_tty: bool,
) -> None:
    """TTY 与 redirected secret 输入必须原样传播 KeyboardInterrupt。

    :param monkeypatch: pytest monkeypatch 夹具。
    :param is_tty: 是否验证 TTY hidden-getpass 路径。
    :returns: ``None``。
    :raises AssertionError: interrupt identity 或 capability 分流漂移时抛出。
    """

    interrupt = KeyboardInterrupt()
    if is_tty:
        monkeypatch.setattr(init_command.sys, "stdin", _TtySecretInput())
        monkeypatch.setattr(getpass, "getpass", Mock(side_effect=interrupt))
    else:
        monkeypatch.setattr(
            init_command.sys,
            "stdin",
            _InterruptingRedirectedSecretInput(interrupt),
        )
        monkeypatch.setattr(
            getpass,
            "getpass",
            Mock(side_effect=AssertionError("redirected input must not call getpass")),
        )

    with pytest.raises(KeyboardInterrupt) as raised:
        init_command._read_secret_input("PROVIDER_API_KEY: ")

    assert raised.value is interrupt


@pytest.mark.parametrize("is_tty", (True, False), ids=("tty", "redirected"))
def test_secret_input_keyboard_interrupt_maps_to_cli_exit_130(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    is_tty: bool,
) -> None:
    """Secret 输入中断必须映射 exit 130 且停止 confirmation/persistence/publication。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch 夹具。
    :param is_tty: 是否验证 TTY hidden-getpass 路径。
    :returns: ``None``。
    :raises AssertionError: 退出码、后续调用或 publication 漂移时抛出。
    """

    workspace_root = tmp_path / "workspace"
    model_input = _InputSequence(("6",))
    persistence = Mock(side_effect=AssertionError("persistence must not run after interrupt"))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(builtins, "input", model_input)
    monkeypatch.setattr(init_command, "persist_environment", persistence)
    if is_tty:
        monkeypatch.setattr(init_command.sys, "stdin", _TtySecretInput())
        monkeypatch.setattr(getpass, "getpass", Mock(side_effect=KeyboardInterrupt()))
    else:
        monkeypatch.setattr(
            init_command.sys,
            "stdin",
            _InterruptingRedirectedSecretInput(KeyboardInterrupt()),
        )
        monkeypatch.setattr(
            getpass,
            "getpass",
            Mock(side_effect=AssertionError("redirected input must not call getpass")),
        )

    exit_code = cli_main.main(("init", "--base", str(workspace_root)))

    assert exit_code == EXIT_KEYBOARD_INTERRUPT
    assert len(model_input.prompts) == 1
    persistence.assert_not_called()
    assert not (workspace_root / "config").exists()
    assert not (workspace_root / ".dayu").exists()


def test_first_cli_flow_uses_real_lock_discovery_and_current_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """FIRST 必须经真实 lock/transaction 生成可加载当前配置。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch 夹具。
    :param capsys: pytest 输出捕获。
    :returns: None。
    :raises AssertionError: FIRST 路径或 ConfigLoader 校验失败时抛出。
    """

    workspace_root = tmp_path / "workspace"
    _install_ollama_inputs(monkeypatch)
    prewarm = Mock()
    monkeypatch.setattr(init_command, "_run_init_prewarm", prewarm)

    exit_code = cli_main.main(("init", "--base", str(workspace_root)))
    captured = capsys.readouterr()

    assert exit_code == EXIT_SUCCESS
    assert "正在等待此 workspace lock" in captured.out
    assert "mode=first" in captured.out
    assert (workspace_root / ".dayu-init.lock").is_file()
    assert not (workspace_root / ".dayu").exists()
    assert not (workspace_root / "portfolio").exists()
    prewarm.assert_called_once_with()
    config = ConfigLoader().load(workspace_config_dir=workspace_root / "config")
    assert config.models.models["ollama"].model == "qwen3:8b"


@pytest.mark.parametrize(
    ("expected_mode", "flags", "existing_config"),
    (
        (init_command.InitMode.FIRST, (), False),
        (init_command.InitMode.PRESERVE, (), True),
        (init_command.InitMode.OVERWRITE, ("--overwrite",), True),
        (init_command.InitMode.RESET, ("--reset",), True),
    ),
)
def test_locked_target_mode_loads_typed_profile_once_and_passes_minimum(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    expected_mode: init_command.InitMode,
    flags: tuple[str, ...],
    existing_config: bool,
) -> None:
    """四态在首个 model prompt 前按锁内 mode 单次加载并显式下传 minimum。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch 夹具。
    :param expected_mode: 锁内 target mode。
    :param flags: 构造该 mode 的 CLI flags。
    :param existing_config: 是否预置 workspace config。
    :returns: ``None``。
    :raises AssertionError: loader source、次数、顺序或显式下传漂移时抛出。
    :raises OSError: fixture 配置复制失败时抛出。
    """

    workspace_root = tmp_path / expected_mode.value
    workspace_root.mkdir()
    if existing_config:
        shutil.copytree(
            init_command._PACKAGE_CONFIG_ROOT,
            workspace_root / "config",
        )
    typed_profiles = ConfigLoader(
        package_config_dir=init_command._PACKAGE_CONFIG_ROOT
    ).load_execution_profiles()
    expected_minimum = typed_profiles.execution_profiles[
        typed_profiles.default_execution_profile_id
    ].min_context_window_tokens
    loader = Mock()
    loader.load_execution_profiles.return_value = typed_profiles
    loader_factory = Mock(return_value=loader)
    selection = Mock(
        side_effect=init_command.CliInitOperationError(
            "stop after target minimum"
        )
    )
    monkeypatch.setattr(init_command, "ConfigLoader", loader_factory)
    monkeypatch.setattr(init_command, "_select_model", selection)
    snapshot = Mock(wraps=init_command.snapshot_managed_roots)
    monkeypatch.setattr(init_command, "snapshot_managed_roots", snapshot)
    if expected_mode is init_command.InitMode.RESET:
        monkeypatch.setattr(builtins, "input", _InputSequence(("y",)))

    exit_code = cli_main.main(
        ("init", "--base", str(workspace_root), *flags)
    )

    assert exit_code == EXIT_FAILURE
    loader_factory.assert_called_once_with(
        package_config_dir=init_command._PACKAGE_CONFIG_ROOT
    )
    expected_workspace_config_dir = (
        workspace_root.resolve(strict=True) / "config"
        if expected_mode is init_command.InitMode.PRESERVE
        else None
    )
    loader.load_execution_profiles.assert_called_once_with(
        workspace_config_dir=expected_workspace_config_dir
    )
    selection.assert_called_once_with(
        min_context_window_tokens=expected_minimum
    )
    expected_repair_mode = (
        expected_mode
        if expected_mode
        in (init_command.InitMode.OVERWRITE, init_command.InitMode.RESET)
        else None
    )
    expected_workspace_root = workspace_root.resolve(strict=True)
    assert snapshot.call_args_list == [
        call(
            expected_workspace_root,
            platform_system=platform.system(),
            repair_mode=expected_repair_mode,
        ),
        call(
            expected_workspace_root,
            platform_system=platform.system(),
            repair_mode=expected_repair_mode,
        ),
    ]


def test_preserve_overwrite_and_reset_cli_matrix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """PRESERVE/OVERWRITE/RESET 与 reset+overwrite 按唯一 precedence 执行。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch 夹具。
    :param capsys: pytest 输出捕获。
    :returns: None。
    :raises AssertionError: 四态 tree contract 或 precedence 漂移时抛出。
    """

    workspace_root = tmp_path / "workspace"
    _install_ollama_inputs(monkeypatch)
    prewarm = Mock()
    monkeypatch.setattr(init_command, "_run_init_prewarm", prewarm)
    assert cli_main.main(("init", "--base", str(workspace_root))) == EXIT_SUCCESS
    assert prewarm.call_count == 1
    capsys.readouterr()
    user_file = workspace_root / "config" / "user-extension.json"
    _write_text(user_file, '{"owner":"user"}')

    _install_ollama_inputs(monkeypatch)
    assert cli_main.main(("init", "--base", str(workspace_root))) == EXIT_SUCCESS
    assert "mode=preserve" in capsys.readouterr().out
    assert user_file.is_file()
    assert prewarm.call_count == 1

    _install_ollama_inputs(monkeypatch)
    assert cli_main.main(("init", "--base", str(workspace_root), "--overwrite")) == EXIT_SUCCESS
    assert "mode=overwrite" in capsys.readouterr().out
    assert not user_file.exists()
    assert prewarm.call_count == 1
    _write_text(workspace_root / ".dayu" / "state.txt", "state")
    _write_text(workspace_root / "portfolio" / "sentinel.txt", "keep")

    _install_ollama_inputs(monkeypatch, reset_answer="y")
    assert (
        cli_main.main(
            (
                "init",
                "--base",
                str(workspace_root),
                "--reset",
                "--overwrite",
            )
        )
        == EXIT_SUCCESS
    )
    captured = capsys.readouterr()
    assert "active Dayu" in captured.out
    assert str(workspace_root / ".dayu") in captured.out
    assert "mode=reset" in captured.out
    assert not (workspace_root / ".dayu").exists()
    assert (workspace_root / "portfolio" / "sentinel.txt").read_text(encoding="utf-8") == "keep"
    assert prewarm.call_count == 2


def test_invalid_choice_and_dynamic_fields_retry_in_original_steps(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Choice/model/endpoint/context 的 recoverable 错误必须逐步原地重试。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch 夹具。
    :param capsys: pytest 输出捕获夹具。
    :returns: ``None``。
    :raises AssertionError: prompt 顺序、成功 publication 或敏感 endpoint 脱敏漂移时抛出。
    """

    workspace_root = tmp_path / "workspace"
    invalid_endpoint = "https://bad endpoint/sensitive-query?token=secret"
    package_minimum = init_command._load_target_min_context_window(
        locked_mode=init_command.InitMode.FIRST,
        workspace_root=workspace_root,
    )
    input_sequence = _InputSequence(
        (
            "unknown-choice",
            "15",
            " invalid-model",
            "valid-model",
            invalid_endpoint,
            "",
            "1",
            str(package_minimum),
        )
    )
    monkeypatch.setattr(builtins, "input", input_sequence)
    _install_tty_getpass(monkeypatch)
    _set_all_environment_values(monkeypatch)

    exit_code = cli_main.main(("init", "--base", str(workspace_root)))
    captured = capsys.readouterr()

    assert exit_code == EXIT_SUCCESS
    assert input_sequence.prompts[0:2] == [
        "模型组合编号或 choice id: ",
        "模型组合编号或 choice id: ",
    ]
    assert input_sequence.prompts[2:4] == [
        "Custom model name: ",
        "Custom model name: ",
    ]
    assert input_sequence.prompts[4:6] == [
        f"Custom endpoint [{init_command._DEFAULT_CUSTOM_ENDPOINT}]: ",
        f"Custom endpoint [{init_command._DEFAULT_CUSTOM_ENDPOINT}]: ",
    ]
    assert input_sequence.prompts[6:8] == [
        f"Custom context window [{package_minimum}]: ",
        f"Custom context window [{package_minimum}]: ",
    ]
    assert invalid_endpoint not in captured.out
    assert invalid_endpoint not in captured.err
    assert (
        ConfigLoader()
        .load_models(workspace_config_dir=workspace_root / "config")
        .models["custom-openai"]
        .context_window_tokens
        == package_minimum
    )


@pytest.mark.parametrize("choice_id", ("14", "15"), ids=("ollama", "custom"))
def test_preserve_workspace_minimum_retries_low_dynamic_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    choice_id: str,
) -> None:
    """PRESERVE 更高 workspace minimum 必须让低 context 在当前步骤重试。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch 夹具。
    :param choice_id: Ollama 或 Custom 的 catalog 编号。
    :returns: ``None``。
    :raises AssertionError: layered minimum、prompt 次数或最终 model context 漂移时抛出。
    :raises OSError: fixture 配置读写失败时抛出。
    """

    workspace_root = tmp_path / f"workspace-{choice_id}"
    _install_ollama_inputs(monkeypatch)
    assert cli_main.main(("init", "--base", str(workspace_root))) == EXIT_SUCCESS
    workspace_minimum = 1_000_000
    _set_default_execution_profile(
        workspace_root / "config",
        "standard-1m",
    )
    _set_all_environment_values(monkeypatch)
    if choice_id == "14":
        responses = (
            choice_id,
            "",
            "",
            "262144",
            str(workspace_minimum),
        )
        model_id = "ollama"
    else:
        responses = (
            choice_id,
            "custom-model",
            "",
            "262144",
            str(workspace_minimum),
        )
        model_id = "custom-openai"
    input_sequence = _InputSequence(responses)
    monkeypatch.setattr(builtins, "input", input_sequence)
    _install_tty_getpass(monkeypatch)

    exit_code = cli_main.main(("init", "--base", str(workspace_root)))

    assert exit_code == EXIT_SUCCESS
    context_prompts = [
        prompt
        for prompt in input_sequence.prompts
        if "context window" in prompt
    ]
    assert len(context_prompts) == 2
    model = ConfigLoader().load_models(
        workspace_config_dir=workspace_root / "config"
    ).models[model_id]
    assert model.context_window_tokens == workspace_minimum


def test_preserve_missing_workspace_profile_uses_package_layer(
    tmp_path: Path,
) -> None:
    """PRESERVE 缺失 execution profile 文件时必须由 typed loader 取得 package layer。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: layered typed minimum 不等于 package owner 值时抛出。
    """

    package_profiles = ConfigLoader(
        package_config_dir=init_command._PACKAGE_CONFIG_ROOT
    ).load_execution_profiles()
    expected_minimum = package_profiles.execution_profiles[
        package_profiles.default_execution_profile_id
    ].min_context_window_tokens
    workspace_root = tmp_path / "workspace-without-profile"
    (workspace_root / "config").mkdir(parents=True)

    minimum = init_command._load_target_min_context_window(
        locked_mode=init_command.InitMode.PRESERVE,
        workspace_root=workspace_root,
    )

    assert minimum == expected_minimum


@pytest.mark.parametrize(
    "profile_shape",
    (
        "symlink",
        "dangling-symlink",
        "directory",
        "fifo",
    ),
)
def test_preserve_non_regular_workspace_profile_stops_before_all_consumers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    profile_shape: str,
) -> None:
    """PRESERVE 非普通 profile 必须在 loader 与全部下游消费者前失败。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch 夹具。
    :param capsys: pytest 输出捕获夹具。
    :param profile_shape: symlink、dangling、目录或代表 special file 的 FIFO。
    :returns: ``None``。
    :raises AssertionError: no-follow 分类、脱敏、零副作用或外部 target 保持漂移时抛出。
    :raises OSError: fixture 文件、symlink 或 FIFO 创建失败时抛出。
    """

    if profile_shape == "fifo" and os.name == "nt":
        pytest.skip("Windows special path 由 reparse owner contract 覆盖")
    workspace_root = tmp_path / f"workspace-{profile_shape}"
    shutil.copytree(
        init_command._PACKAGE_CONFIG_ROOT,
        workspace_root / "config",
    )
    profile_path = workspace_root / "config" / "execution_profiles.json"
    models_path = workspace_root / "config" / "models.json"
    models_before = models_path.read_bytes()
    dayu_sentinel = workspace_root / ".dayu" / "sentinel.txt"
    _write_text(dayu_sentinel, "durable-state")
    external_secret = "external-profile-secret"
    external_target = tmp_path / f"external-{profile_shape}.json"
    external_target.write_text(external_secret, encoding="utf-8")
    external_before = external_target.read_bytes()
    dangling_target = tmp_path / f"missing-{profile_shape}.json"
    real_snapshot_check = init_command._require_confirmed_snapshot

    def replace_profile_after_snapshot(
        *,
        unlocked_snapshot: init_command.WorkspaceSnapshot,
        locked_snapshot: init_command.WorkspaceSnapshot,
        requested_mode: init_command.InitMode,
        locked_mode: init_command.InitMode,
    ) -> None:
        """先执行真实 snapshot 复核，再注入待分类的静态路径 shape。

        :param unlocked_snapshot: lock 前 managed-root snapshot。
        :param locked_snapshot: lock 内 managed-root snapshot。
        :param requested_mode: lock 前目标模式。
        :param locked_mode: lock 内目标模式。
        :returns: ``None``。
        :raises AssertionError: snapshot contract 或 profile shape 名非法时抛出。
        :raises OSError: profile 替换或 special path 创建失败时抛出。
        """

        real_snapshot_check(
            unlocked_snapshot=unlocked_snapshot,
            locked_snapshot=locked_snapshot,
            requested_mode=requested_mode,
            locked_mode=locked_mode,
        )
        profile_path.unlink()
        if profile_shape == "symlink":
            profile_path.symlink_to(external_target)
        elif profile_shape == "dangling-symlink":
            profile_path.symlink_to(dangling_target)
        elif profile_shape == "directory":
            profile_path.mkdir()
        elif profile_shape == "fifo":
            os.mkfifo(profile_path)
        else:
            raise AssertionError("unknown profile shape fixture")

    loader_factory = Mock(
        side_effect=AssertionError("profile loader must not start")
    )
    select_model = Mock(
        side_effect=AssertionError("model prompt must not start")
    )
    collect_secrets = Mock(
        side_effect=AssertionError("secret collection must not start")
    )
    prepare_transaction = Mock(
        side_effect=AssertionError("transaction prepare must not start")
    )
    publish_transaction = Mock(
        side_effect=AssertionError("publication must not start")
    )
    secret_input = Mock(
        side_effect=AssertionError("secret input must not start")
    )
    monkeypatch.setattr(
        init_command,
        "_require_confirmed_snapshot",
        replace_profile_after_snapshot,
    )
    monkeypatch.setattr(init_command, "ConfigLoader", loader_factory)
    monkeypatch.setattr(init_command, "_select_model", select_model)
    monkeypatch.setattr(
        init_command,
        "_collect_environment_persistence_plan",
        collect_secrets,
    )
    monkeypatch.setattr(
        init_command,
        "prepare_workspace_transaction",
        prepare_transaction,
    )
    monkeypatch.setattr(
        init_command,
        "publish_workspace_transaction",
        publish_transaction,
    )
    monkeypatch.setattr(getpass, "getpass", secret_input)
    monkeypatch.setattr(builtins, "input", _InterruptInput())

    exit_code = cli_main.main(("init", "--base", str(workspace_root)))
    captured = capsys.readouterr()

    assert exit_code == EXIT_FAILURE
    assert "workspace execution profile path must be an ordinary file" in captured.err
    assert "rerun with --overwrite" in captured.err
    assert external_secret not in captured.out
    assert external_secret not in captured.err
    loader_factory.assert_not_called()
    select_model.assert_not_called()
    collect_secrets.assert_not_called()
    secret_input.assert_not_called()
    prepare_transaction.assert_not_called()
    publish_transaction.assert_not_called()
    assert external_target.read_bytes() == external_before
    assert models_path.read_bytes() == models_before
    assert dayu_sentinel.read_text(encoding="utf-8") == "durable-state"
    assert not tuple(workspace_root.glob(".dayu-init-transaction-*"))


@pytest.mark.parametrize(
    "invalid_kind",
    ("malformed", "schema", "default-id"),
)
def test_preserve_invalid_workspace_profile_fails_closed_without_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    invalid_kind: str,
) -> None:
    """PRESERVE 已存在但非法的 profile 必须脱敏失败且保持 managed roots。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch 夹具。
    :param capsys: pytest 输出捕获夹具。
    :param invalid_kind: malformed/schema/default-id-invalid 场景。
    :returns: ``None``。
    :raises AssertionError: fallback、prompt、退出码、脱敏或零 mutation 漂移时抛出。
    :raises OSError: fixture 配置读写失败时抛出。
    """

    workspace_root = tmp_path / f"workspace-{invalid_kind}"
    workspace_root.mkdir()
    shutil.copytree(
        init_command._PACKAGE_CONFIG_ROOT,
        workspace_root / "config",
    )
    dayu_sentinel = workspace_root / ".dayu" / "sentinel.txt"
    _write_text(dayu_sentinel, "durable-state")
    profile_path = workspace_root / "config" / "execution_profiles.json"
    secret_sentinel = "profile-secret-sentinel"
    if invalid_kind == "malformed":
        profile_path.write_text(
            f'{{"secret":"{secret_sentinel}"',
            encoding="utf-8",
        )
    elif invalid_kind == "schema":
        _write_json(
            profile_path,
            {
                "unexpected": secret_sentinel,
            },
        )
    else:
        root = _read_json_object(profile_path)
        root["default_execution_profile_id"] = secret_sentinel
        _write_json(profile_path, root)
    before_profile = profile_path.read_bytes()
    select_model = Mock(
        side_effect=AssertionError("model prompt must not start")
    )
    monkeypatch.setattr(init_command, "_select_model", select_model)
    monkeypatch.setattr(builtins, "input", _InterruptInput())

    exit_code = cli_main.main(("init", "--base", str(workspace_root)))
    captured = capsys.readouterr()

    assert exit_code == EXIT_FAILURE
    assert "workspace execution profile config is invalid" in captured.err
    assert "rerun with --overwrite" in captured.err
    assert secret_sentinel not in captured.out
    assert secret_sentinel not in captured.err
    assert profile_path.read_bytes() == before_profile
    assert dayu_sentinel.read_text(encoding="utf-8") == "durable-state"
    assert not tuple(workspace_root.glob(".dayu-init-transaction-*"))
    select_model.assert_not_called()


@pytest.mark.parametrize(
    "invalid_kind",
    ("missing", "malformed", "default-id"),
)
def test_package_profile_failure_is_actionable_and_has_zero_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    invalid_kind: str,
) -> None:
    """Package profile 缺失/非法/default-id-invalid 必须在交互前失败。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch 夹具。
    :param capsys: pytest 输出捕获夹具。
    :param invalid_kind: package typed load failure 场景。
    :returns: ``None``。
    :raises AssertionError: fallback、prompt、诊断或零 publication 漂移时抛出。
    :raises OSError: package fixture 复制或修改失败时抛出。
    """

    package_config = _copy_package_config(tmp_path)
    profile_path = package_config / "execution_profiles.json"
    secret_sentinel = "package-profile-secret"
    if invalid_kind == "missing":
        profile_path.unlink()
    elif invalid_kind == "malformed":
        profile_path.write_text(
            f'{{"secret":"{secret_sentinel}"',
            encoding="utf-8",
        )
    else:
        root = _read_json_object(profile_path)
        root["default_execution_profile_id"] = secret_sentinel
        _write_json(profile_path, root)
    monkeypatch.setattr(init_command, "_PACKAGE_CONFIG_ROOT", package_config)
    monkeypatch.setattr(
        init_command,
        "_PACKAGE_MANIFEST_ROOT",
        package_config / "prompts" / "manifests",
    )
    select_model = Mock(
        side_effect=AssertionError("model prompt must not start")
    )
    monkeypatch.setattr(init_command, "_select_model", select_model)
    monkeypatch.setattr(builtins, "input", _InterruptInput())
    workspace_root = tmp_path / "workspace"

    exit_code = cli_main.main(("init", "--base", str(workspace_root)))
    captured = capsys.readouterr()

    assert exit_code == EXIT_FAILURE
    assert "package execution profile config is invalid" in captured.err
    assert "repair or reinstall package config" in captured.err
    assert secret_sentinel not in captured.out
    assert secret_sentinel not in captured.err
    assert not (workspace_root / "config").exists()
    assert not (workspace_root / ".dayu").exists()
    assert not tuple(workspace_root.glob(".dayu-init-transaction-*"))
    select_model.assert_not_called()


def test_prewarm_imports_exact_roots_without_inputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Prewarm helper 只能按顺序调用 exact two import roots。

    :param monkeypatch: pytest monkeypatch 夹具。
    :returns: ``None``。
    :raises AssertionError: root、顺序、调用次数或 helper 入参漂移时抛出。
    """

    import_module = Mock()
    monkeypatch.setattr(init_command.importlib, "import_module", import_module)

    init_command._run_init_prewarm()

    assert init_command._PREWARM_IMPORT_ROOTS == (
        "dayu.cli.commands.interactive",
        "dayu.cli.commands.prompt",
    )
    assert import_module.call_args_list == [
        call("dayu.cli.commands.interactive"),
        call("dayu.cli.commands.prompt"),
    ]


def test_prewarm_failure_warns_safely_after_successful_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Import failure 只能给出脱敏 warning，不能回滚已发布 FIRST config。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch 夹具。
    :param capsys: pytest 输出捕获。
    :returns: ``None``。
    :raises AssertionError: publication、退出码或 warning 脱敏语义漂移时抛出。
    """

    secret = "prewarm-exception-secret"
    workspace_root = tmp_path / "workspace"
    _install_ollama_inputs(monkeypatch)
    monkeypatch.setattr(
        init_command.importlib,
        "import_module",
        _PrewarmImportFailure(secret),
    )

    exit_code = cli_main.main(("init", "--base", str(workspace_root)))
    captured = capsys.readouterr()

    assert exit_code == EXIT_SUCCESS
    assert (workspace_root / "config" / "models.json").is_file()
    assert "prewarm warning" in captured.err
    assert "error_type=RuntimeError" in captured.err
    assert "normal command import remains available" in captured.err
    assert secret not in captured.out
    assert secret not in captured.err


@pytest.mark.parametrize("answer", ("n", ""))
def test_reset_default_no_has_zero_bootstrap_or_managed_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    answer: str,
) -> None:
    """RESET No/empty 不得创建 fresh workspace 或调用后续选择。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch 夹具。
    :param answer: No 或默认空输入。
    :returns: None。
    :raises AssertionError: 取消 RESET 留下 workspace 时抛出。
    """

    workspace_root = tmp_path / "fresh"
    monkeypatch.setattr(builtins, "input", _InputSequence((answer,)))

    exit_code = cli_main.main(("init", "--base", str(workspace_root), "--reset"))

    assert exit_code == EXIT_SUCCESS
    assert not workspace_root.exists()


def test_reset_eof_and_interrupt_map_to_failure_and_interrupt_without_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RESET EOF 返回 1、SIGINT 返回 130，二者都不 bootstrap。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch 夹具。
    :returns: None。
    :raises AssertionError: 退出码或 zero-mutation contract 漂移时抛出。
    """

    eof_root = tmp_path / "eof"
    monkeypatch.setattr(builtins, "input", _EofInput())
    assert cli_main.main(("init", "--base", str(eof_root), "--reset")) == EXIT_FAILURE
    assert not eof_root.exists()

    interrupt_root = tmp_path / "interrupt"
    monkeypatch.setattr(builtins, "input", _InterruptInput())
    assert cli_main.main(("init", "--base", str(interrupt_root), "--reset")) == EXIT_KEYBOARD_INTERRUPT
    assert not interrupt_root.exists()


def test_reset_invalid_confirmation_retries_same_prompt_then_cancels(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RESET 非法确认必须原步骤重试，Enter 仍按取消成功处理。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch 夹具。
    :returns: ``None``。
    :raises AssertionError: prompt 次数、退出码或零 mutation contract 漂移时抛出。
    """

    workspace_root = tmp_path / "workspace"
    input_sequence = _InputSequence(("maybe", ""))
    monkeypatch.setattr(builtins, "input", input_sequence)

    exit_code = cli_main.main(
        ("init", "--base", str(workspace_root), "--reset")
    )

    assert exit_code == EXIT_SUCCESS
    assert input_sequence.prompts == [
        "确认 RESET? [y/N]: ",
        "确认 RESET? [y/N]: ",
    ]
    assert not workspace_root.exists()


def test_reset_confirmation_snapshot_drift_requires_rerun(
    tmp_path: Path,
) -> None:
    """RESET 确认后 managed-root identity/content 漂移必须停止。

    :param tmp_path: pytest 临时目录。
    :returns: None。
    :raises AssertionError: 锁内继续消费旧确认时抛出。
    """

    workspace_root = (tmp_path / "workspace").resolve(strict=False)
    _write_text(workspace_root / "config" / "value.txt", "before")
    unlocked = init_command.snapshot_managed_roots(
        workspace_root,
        platform_system=platform.system(),
    )
    (workspace_root / "config" / "value.txt").write_text(
        "after",
        encoding="utf-8",
    )
    locked = init_command.snapshot_managed_roots(
        workspace_root,
        platform_system=platform.system(),
    )

    with pytest.raises(init_command.CliInitOperationError, match="changed"):
        init_command._require_confirmed_snapshot(
            unlocked_snapshot=unlocked,
            locked_snapshot=locked,
            requested_mode=init_command.InitMode.RESET,
            locked_mode=init_command.InitMode.RESET,
        )


@pytest.mark.parametrize(
    ("confirmation_kind", "expected_exit"),
    (
        ("no", EXIT_FAILURE),
        ("enter", EXIT_FAILURE),
        ("eof", EXIT_FAILURE),
        ("interrupt", EXIT_KEYBOARD_INTERRUPT),
    ),
)
def test_required_secret_persistence_incomplete_paths_have_zero_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    confirmation_kind: str,
    expected_exit: int,
) -> None:
    """Required persistence No/Enter/EOF/SIGINT 必须按 contract 零写入。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch 夹具。
    :param capsys: pytest 输出捕获。
    :param confirmation_kind: persistence confirmation terminal input。
    :param expected_exit: 对应业务完成态退出码。
    :returns: None。
    :raises AssertionError: 退出码、环境值或 managed publication 漂移时抛出。
    """

    secret = "sentinel-secret-value"
    workspace_root = tmp_path / "workspace"
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    if confirmation_kind == "no":
        input_reader: _InputSequence | Mock = _InputSequence(("6", "n"))
    elif confirmation_kind == "enter":
        input_reader = _InputSequence(("6", ""))
    elif confirmation_kind == "eof":
        input_reader = _InputSequence(("6",))
    else:
        input_reader = Mock(side_effect=("6", KeyboardInterrupt()))
    monkeypatch.setattr(builtins, "input", input_reader)
    _install_tty_getpass(monkeypatch, (secret,))

    exit_code = cli_main.main(("init", "--base", str(workspace_root)))
    captured = capsys.readouterr()

    assert exit_code == expected_exit
    assert not (workspace_root / "config").exists()
    assert not (workspace_root / ".dayu").exists()
    assert not tuple(workspace_root.glob(".dayu-init-transaction-*"))
    assert secret not in captured.out
    assert secret not in captured.err
    assert os.environ.get("OPENAI_API_KEY") != secret


@pytest.mark.parametrize("invalid_value", ("", "bad\nvalue"))
def test_required_secret_validation_retries_without_rendering_values(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    invalid_value: str,
) -> None:
    """Required secret 空值/control 必须在隐藏输入原步骤重试且不泄值。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch 夹具。
    :param capsys: pytest 输出捕获夹具。
    :param invalid_value: owner 必须拒绝的 secret 值。
    :returns: ``None``。
    :raises AssertionError: 重试、退出码、脱敏或零 publication 漂移时抛出。
    """

    valid_secret = secrets.token_urlsafe(24)
    workspace_root = tmp_path / "workspace"
    input_sequence = _InputSequence(("6", "n"))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(builtins, "input", input_sequence)
    getpass_sequence = _install_tty_getpass(
        monkeypatch,
        (invalid_value, valid_secret),
    )

    exit_code = cli_main.main(("init", "--base", str(workspace_root)))
    captured = capsys.readouterr()

    assert exit_code == EXIT_FAILURE
    required_prompts = [
        prompt
        for prompt in getpass_sequence.prompts
        if prompt.startswith("OPENAI_API_KEY")
    ]
    assert len(required_prompts) == 2
    if invalid_value:
        assert invalid_value not in captured.out
        assert invalid_value not in captured.err
    assert valid_secret not in captured.out
    assert valid_secret not in captured.err
    assert not (workspace_root / "config").exists()
    assert not (workspace_root / ".dayu").exists()


def test_optional_secret_validation_retries_then_allows_skip(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Optional secret control 值必须原步骤重试，随后空输入可跳过。

    :param monkeypatch: pytest monkeypatch 夹具。
    :param capsys: pytest 输出捕获夹具。
    :returns: ``None``。
    :raises AssertionError: owner retry 或 optional skip 语义漂移时抛出。
    """

    optional_name = init_command.OPTIONAL_ENVIRONMENT_NAMES[0]
    invalid_value = "bad\rvalue"
    getpass_sequence = _install_tty_getpass(
        monkeypatch,
        (invalid_value, ""),
    )

    entry = init_command._read_environment_persistence_entry(
        name=optional_name,
        prompt=f"可选 {optional_name}: ",
        required=False,
    )
    captured = capsys.readouterr()

    assert entry is None
    assert getpass_sequence.prompts == [
        f"可选 {optional_name}: ",
        f"可选 {optional_name}: ",
    ]
    assert invalid_value not in captured.out
    assert invalid_value not in captured.err


@pytest.mark.parametrize("failure_kind", ("posix-error", "windows-partial"))
def test_environment_persistence_failure_never_publishes_workspace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    failure_kind: str,
) -> None:
    """POSIX writer error 与 Windows partial result 均停在 publication 前。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch 夹具。
    :param capsys: pytest 输出捕获。
    :param failure_kind: POSIX exception 或 Windows partial result。
    :returns: None。
    :raises AssertionError: config 被发布、private tree 残留或 secret 泄漏时抛出。
    """

    secret = "persistence-failure-secret"
    workspace_root = tmp_path / "workspace"
    retained_path = tmp_path / ".dayu-init-env-retained"
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(builtins, "input", _InputSequence(("6", "y")))
    _install_tty_getpass(monkeypatch, (secret,))
    if failure_kind == "posix-error":
        retained_path.write_text(secret, encoding="utf-8")
        persistence = Mock(
            side_effect=EnvironmentPersistenceError(
                "profile replace failed",
                retained_paths=(retained_path,),
            )
        )
    else:
        persistence = Mock(
            return_value=EnvironmentPersistenceResult(
                status=EnvironmentPersistenceStatus.PARTIAL_FAILURE,
                target="setx",
                written_names=("OPENAI_API_KEY",),
                unwritten_names=("HF_TOKEN",),
                retained_paths=(),
            )
        )
    monkeypatch.setattr(init_command, "persist_environment", persistence)

    exit_code = cli_main.main(("init", "--base", str(workspace_root)))
    captured = capsys.readouterr()

    assert exit_code == EXIT_FAILURE
    assert not (workspace_root / "config").exists()
    assert not (workspace_root / ".dayu").exists()
    assert not tuple(workspace_root.glob(".dayu-init-transaction-*"))
    assert secret not in captured.out
    assert secret not in captured.err
    if failure_kind == "windows-partial":
        assert "OPENAI_API_KEY" in captured.err
        assert "HF_TOKEN" in captured.err
    else:
        assert str(retained_path) in captured.err


@pytest.mark.parametrize("typed_interrupt", (False, True), ids=("plain", "typed"))
def test_persistence_interrupt_aborts_real_prepared_transaction_and_exits_130(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    typed_interrupt: bool,
) -> None:
    """真实 staging 后 plain/typed persistence interrupt 必须清理并保持 exit 130。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: 注入 persistence interrupt 与隔离 secret 的 fixture。
    :param capsys: 捕获 names-only CLI diagnostic。
    :param typed_interrupt: 是否携带 Windows written/unwritten typed truth。
    :returns: ``None``。
    :raises AssertionError: exit、private cleanup、names truth 或脱敏不符合 contract 时抛出。
    """

    secret = "persistence-interrupt-secret"
    workspace_root = tmp_path / "workspace"
    retained_path = tmp_path / ".dayu-init-env-retained"
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(builtins, "input", _InputSequence(("6", "y")))
    _install_tty_getpass(monkeypatch, (secret,))
    if typed_interrupt:
        retained_path.write_text(secret, encoding="utf-8")
        side_effect: KeyboardInterrupt = EnvironmentPersistenceInterrupted(
            EnvironmentPersistenceResult(
                status=EnvironmentPersistenceStatus.INTERRUPTED,
                target="setx",
                written_names=("OPENAI_API_KEY",),
                unwritten_names=("HF_TOKEN",),
                retained_paths=(retained_path,),
            )
        )
    else:
        side_effect = KeyboardInterrupt()
    monkeypatch.setattr(init_command, "persist_environment", Mock(side_effect=side_effect))

    exit_code = cli_main.main(("init", "--base", str(workspace_root)))
    captured = capsys.readouterr()

    assert exit_code == EXIT_KEYBOARD_INTERRUPT
    assert not (workspace_root / "config").exists()
    assert not (workspace_root / ".dayu").exists()
    assert not tuple(workspace_root.glob(".dayu-init-transaction-*"))
    assert secret not in captured.out
    assert secret not in captured.err
    if typed_interrupt:
        assert "workspace 未发布" in captured.err
        assert "OPENAI_API_KEY" in captured.err
        assert "不能自动回滚" in captured.err
        assert str(retained_path) in captured.err
        assert retained_path.exists()
    else:
        assert "不能自动回滚" not in captured.err


def test_persistence_interrupt_abort_failure_reports_retained_truth_and_exits_130(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Abort 失败必须保留 retained path truth，同时原中断仍映射 exit 130。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: 注入 typed interrupt 与 identity-safe abort failure。
    :param capsys: 捕获 written names 与 retained transaction diagnostic。
    :returns: ``None``。
    :raises AssertionError: retained truth、exit、written names 或脱敏不符合 contract 时抛出。
    """

    secret = "abort-failure-secret"
    workspace_root = tmp_path / "workspace"
    interrupt = EnvironmentPersistenceInterrupted(
        EnvironmentPersistenceResult(
            status=EnvironmentPersistenceStatus.INTERRUPTED,
            target="setx",
            written_names=("OPENAI_API_KEY",),
            unwritten_names=(),
            retained_paths=(),
        )
    )
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(builtins, "input", _InputSequence(("6", "y")))
    _install_tty_getpass(monkeypatch, (secret,))
    monkeypatch.setattr(init_command, "persist_environment", Mock(side_effect=interrupt))

    def fail_abort(prepared: PreparedWorkspaceTransaction) -> None:
        """保留真实 prepared transaction 并返回现有 typed retained truth。

        :param prepared: 已完成真实 staging/validation 的 transaction。
        :returns: 本函数不返回。
        :raises InitWorkspaceError: 始终报告真实 retained path。
        """

        raise init_command.InitWorkspaceError(
            stage="pre_publication_abort_cleanup",
            message="identity-safe abort failed",
            retained_paths=(prepared.transaction_root,),
            public_root_states=(".dayu=absent", "config=absent"),
        )

    monkeypatch.setattr(init_command, "abort_prepared_workspace_transaction", fail_abort)

    exit_code = cli_main.main(("init", "--base", str(workspace_root)))
    captured = capsys.readouterr()
    retained = tuple(workspace_root.glob(".dayu-init-transaction-*"))

    assert exit_code == EXIT_KEYBOARD_INTERRUPT
    assert len(retained) == 1
    assert "pre_publication_abort_cleanup" in captured.err
    assert str(retained[0]) in captured.err
    assert "OPENAI_API_KEY" in captured.err
    assert ".dayu=absent" in captured.err
    assert "config=absent" in captured.err
    assert secret not in captured.out
    assert secret not in captured.err
    assert not (workspace_root / "config").exists()


@pytest.mark.parametrize("typed_interrupt", (False, True), ids=("plain", "typed"))
@pytest.mark.parametrize("abort_failure", (False, True), ids=("abort-success", "abort-failure"))
def test_persistence_interrupt_aborts_before_broken_stderr_and_exits_130(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    typed_interrupt: bool,
    abort_failure: bool,
) -> None:
    """Broken stderr 不得先于 abort 或覆盖 plain/typed 原始中断。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: 注入真实 prepared transaction 后的中断、abort 与 broken stderr。
    :param typed_interrupt: 是否使用携带 retained path 的 typed interrupt。
    :param abort_failure: 是否让 abort 返回 typed retained transaction truth。
    :returns: ``None``。
    :raises AssertionError: abort 顺序、private truth 或 exit 130 漂移时抛出。
    """

    secret = secrets.token_urlsafe(24)
    workspace_root = tmp_path / "workspace"
    retained_environment_path = tmp_path / ".dayu-init-env-retained"
    retained_environment_path.write_text(secret, encoding="utf-8")
    events: list[str] = []
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(builtins, "input", _InputSequence(("6", "y")))
    _install_tty_getpass(monkeypatch, (secret,))
    if typed_interrupt:
        side_effect: KeyboardInterrupt = EnvironmentPersistenceInterrupted(
            EnvironmentPersistenceResult(
                status=EnvironmentPersistenceStatus.INTERRUPTED,
                target=str(tmp_path / ".zshrc"),
                written_names=("OPENAI_API_KEY",),
                unwritten_names=(),
                retained_paths=(retained_environment_path,),
            )
        )
    else:
        side_effect = KeyboardInterrupt()
    monkeypatch.setattr(init_command, "persist_environment", Mock(side_effect=side_effect))
    real_abort = init_command.abort_prepared_workspace_transaction

    def record_abort(prepared: PreparedWorkspaceTransaction) -> None:
        """记录 abort 顺序，并按参数完成或拒绝真实 transaction cleanup。

        :param prepared: 已完成真实 staging/validation 的 transaction。
        :returns: abort 成功时返回 ``None``。
        :raises InitWorkspaceError: ``abort_failure=True`` 时保留真实 transaction。
        """

        events.append("abort")
        if abort_failure:
            raise init_command.InitWorkspaceError(
                stage="pre_publication_abort_cleanup",
                message="identity-safe abort fault",
                retained_paths=(prepared.transaction_root,),
                public_root_states=(".dayu=absent", "config=absent"),
            )
        real_abort(prepared)

    monkeypatch.setattr(init_command, "abort_prepared_workspace_transaction", record_abort)
    monkeypatch.setattr(init_command.sys, "stderr", _BrokenStderr(events))

    exit_code = cli_main.main(("init", "--base", str(workspace_root)))
    retained_transactions = tuple(workspace_root.glob(".dayu-init-transaction-*"))

    assert exit_code == EXIT_KEYBOARD_INTERRUPT
    assert events[0] == "abort"
    assert retained_environment_path.exists()
    assert not (workspace_root / "config").exists()
    if abort_failure:
        assert len(retained_transactions) == 1
        assert "diagnostic" in events[1:]
    else:
        assert retained_transactions == ()
        if typed_interrupt:
            assert "diagnostic" in events[1:]


def test_invalid_workspace_file_and_symlink_are_usage_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Workspace 普通文件/symlink 必须在交互前按 usage error 拒绝。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch 夹具。
    :returns: None。
    :raises AssertionError: 非目录或 symlink 被 bootstrap 时抛出。
    """

    file_root = tmp_path / "file-root"
    file_root.write_text("file", encoding="utf-8")
    monkeypatch.setattr(builtins, "input", _InterruptInput())
    assert cli_main.main(("init", "--base", str(file_root))) == EXIT_USAGE_ERROR

    target = tmp_path / "target"
    target.mkdir()
    symlink_root = tmp_path / "symlink-root"
    symlink_root.symlink_to(target, target_is_directory=True)
    assert cli_main.main(("init", "--base", str(symlink_root))) == EXIT_USAGE_ERROR


def test_fresh_root_bootstrap_handles_concurrent_create_and_os_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fresh root owner 接受 concurrent directory，拒绝 type race 与 ENOSPC。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch 夹具。
    :returns: None。
    :raises AssertionError: bootstrap 未复核 identity/type 或吞掉 ENOSPC 时抛出。
    """

    concurrent_root = tmp_path / "concurrent"
    concurrent_root.mkdir()
    identity = init_command._bootstrap_workspace_root(concurrent_root)
    assert identity.canonical_path == concurrent_root.resolve(strict=True)

    type_race = tmp_path / "type-race"
    type_race.write_text("file", encoding="utf-8")
    with pytest.raises(init_command.CliInitUsageError):
        init_command._bootstrap_workspace_root(type_race)

    missing_root = tmp_path / "no-space"
    monkeypatch.setattr(
        init_command.Path,
        "mkdir",
        Mock(side_effect=OSError(errno.ENOSPC, "fault")),
    )
    with pytest.raises(init_command.CliInitUsageError, match="OSError"):
        init_command._bootstrap_workspace_root(missing_root)


def test_lock_path_rejects_symlink_dangling_symlink_and_directory(
    tmp_path: Path,
) -> None:
    """Init lock path 的 root type contract 必须在 acquire 前 fail closed。

    :param tmp_path: pytest 临时目录。
    :returns: None。
    :raises AssertionError: 非普通 lock 文件被接受时抛出。
    """

    target = tmp_path / "target"
    target.write_text("lock", encoding="utf-8")
    linked = tmp_path / "linked-lock"
    linked.symlink_to(target)
    with pytest.raises(init_command.CliInitUsageError, match="ordinary"):
        init_command._validate_lock_path(linked, allow_absent=True)

    dangling = tmp_path / "dangling-lock"
    dangling.symlink_to(tmp_path / "missing")
    with pytest.raises(init_command.CliInitUsageError, match="dangling"):
        init_command._validate_lock_path(dangling, allow_absent=True)

    directory = tmp_path / "directory-lock"
    directory.mkdir()
    with pytest.raises(init_command.CliInitUsageError, match="ordinary"):
        init_command._validate_lock_path(directory, allow_absent=True)


def test_real_lock_competition_waits_without_early_publish(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """真实 workspace lock 竞争必须在 release 前零 publish，之后成功。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch 夹具。
    :returns: None。
    :raises AssertionError: init 未等待、提前发布或释放后未完成时抛出。
    """

    workspace_root = (tmp_path / "workspace").resolve(strict=False)
    workspace_root.mkdir()
    lock_path = workspace_root / ".dayu-init.lock"
    _install_ollama_inputs(monkeypatch)
    waiting_print = _WaitingPrint()
    monkeypatch.setattr(builtins, "print", waiting_print)
    runner = _CompetingInitRunner(workspace_root)

    parent_lock = file_lock(
        lock_path,
        timeout_seconds=None,
        create_parent_dirs=False,
    )
    token = parent_lock.acquire()
    thread = threading.Thread(target=runner)
    thread.start()
    assert waiting_print.waiting.wait(_WAIT_TIMEOUT_SECONDS)
    assert not (workspace_root / "config").exists()
    token.release()
    thread.join(_WAIT_TIMEOUT_SECONDS)

    assert not thread.is_alive()
    assert runner.results == [EXIT_SUCCESS]
    assert (workspace_root / "config" / "models.json").is_file()


def test_model_choice_and_input_helpers_retry_recoverable_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Selection/input helpers 必须拒绝非法值并在当前步骤重试。

    :param monkeypatch: pytest monkeypatch 夹具。
    :returns: None。
    :raises AssertionError: 非法交互输入被接受时抛出。
    """

    assert init_command._parse_model_choice("1").choice_id == "mimo-token-plan"
    assert init_command._parse_model_choice("ollama").choice_id == "ollama"
    for invalid in ("", "0", "16", "unknown"):
        with pytest.raises(init_command.CliInitOperationError):
            init_command._parse_model_choice(invalid)

    context_input = _InputSequence(("0", "100"))
    monkeypatch.setattr(builtins, "input", context_input)
    assert (
        init_command._read_context_window(
            "context: ",
            default=100,
            minimum=100,
        )
        == 100
    )
    assert context_input.prompts == ["context: ", "context: "]

    model_input = _InputSequence(("", "valid-model"))
    monkeypatch.setattr(builtins, "input", model_input)
    assert (
        init_command._read_dynamic_model_name("model: ", default=None)
        == "valid-model"
    )
    assert model_input.prompts == ["model: ", "model: "]

    confirmation_input = _InputSequence(("maybe", "yes"))
    monkeypatch.setattr(builtins, "input", confirmation_input)
    assert init_command._confirm("confirm: ") is True
    assert confirmation_input.prompts == ["confirm: ", "confirm: "]


def test_unexpected_input_os_error_is_not_retried(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """非 owner validation 的 OSError 必须原样传播，不能进入 retry loop。

    :param monkeypatch: pytest monkeypatch 夹具。
    :returns: ``None``。
    :raises AssertionError: OSError 被捕获或 input 被重复调用时抛出。
    """

    reader = Mock(side_effect=OSError(errno.EIO, "input fault"))
    monkeypatch.setattr(builtins, "input", reader)

    with pytest.raises(OSError, match="input fault"):
        init_command._read_dynamic_endpoint(
            "endpoint: ",
            default="https://example.test/v1",
        )

    reader.assert_called_once_with("endpoint: ")


def test_persistence_target_and_failure_message_use_names_only(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Typed plan target 与 partial failure 文本不得读取 secret values。

    :param tmp_path: pytest 临时目录。
    :param capsys: pytest 输出捕获。
    :returns: None。
    :raises AssertionError: target/diagnostic 泄漏 value 时抛出。
    """

    secret = "never-render-this-secret"
    entry = EnvironmentPersistenceEntry(name="OPENAI_API_KEY", value=secret)
    posix = PosixEnvironmentPersistencePlan(
        entries=(entry,),
        profile_path=tmp_path / ".zshrc",
        confirmed=False,
    )
    windows = WindowsEnvironmentPersistencePlan(
        entries=(entry,),
        confirmed=False,
    )
    result = EnvironmentPersistenceResult(
        status=EnvironmentPersistenceStatus.PARTIAL_FAILURE,
        target="setx",
        written_names=("OPENAI_API_KEY",),
        unwritten_names=("HF_TOKEN",),
        retained_paths=(),
    )

    assert init_command._persistence_target(posix) == str(tmp_path / ".zshrc")
    assert init_command._persistence_target(windows) == "setx"
    message = init_command._environment_failure_message(result)
    assert "OPENAI_API_KEY" in message
    assert "HF_TOKEN" in message
    assert secret not in message
    success = EnvironmentPersistenceResult(
        status=EnvironmentPersistenceStatus.SUCCESS,
        target="setx",
        written_names=("OPENAI_API_KEY",),
        unwritten_names=(),
        retained_paths=(),
    )
    init_command._report_persisted_environment_names(success)
    rendered = capsys.readouterr().err
    assert "workspace 未发布" in rendered
    assert "OPENAI_API_KEY" in rendered
    assert secret not in rendered
    init_command._report_persisted_environment_names(None)


def test_operation_error_formats_truthful_retained_state(
    tmp_path: Path,
) -> None:
    """Workspace error 输出必须包含 stage/retained/public/durability truth。

    :param tmp_path: pytest 临时目录。
    :returns: None。
    :raises AssertionError: retained state 被省略或误报时抛出。
    """

    retained = tmp_path / "private"
    error = init_command.InitWorkspaceError(
        stage="validation_parent_directory_sync",
        message="sync failed",
        retained_paths=(retained,),
        public_root_states=(".dayu=absent", "config=present"),
        deletion_durability_unconfirmed=True,
    )

    rendered = init_command._format_operation_error(error)

    assert "validation_parent_directory_sync" in rendered
    assert str(retained) in rendered
    assert ".dayu=absent" in rendered
    assert "deletion_durability_unconfirmed=True" in rendered


def test_empty_base_is_usage_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """空白 --base 必须在 filesystem/interaction 前失败。

    :param monkeypatch: pytest monkeypatch 夹具。
    :returns: None。
    :raises AssertionError: 空路径未返回 usage error 时抛出。
    """

    monkeypatch.setattr(builtins, "input", _InterruptInput())
    assert cli_main.main(("init", "--base", "   ")) == EXIT_USAGE_ERROR


def test_platform_value_is_current_runtime() -> None:
    """测试 profile 必须在 fixed plan 支持的平台上运行。

    :returns: None。
    :raises AssertionError: 本地平台不在明确集合时抛出。
    """

    assert platform.system() in {"Darwin", "Linux", "Windows"}
