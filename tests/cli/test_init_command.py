"""dayu.cli.commands.init 四态 orchestrator 测试。"""

from __future__ import annotations

import builtins
import errno
import getpass
import importlib
import os
import platform
import secrets
import threading
from pathlib import Path
from types import ModuleType
from typing import Final, TextIO
from unittest.mock import Mock, call

import pytest

import dayu.cli.commands.init as init_command
import dayu.cli.main as cli_main
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
    monkeypatch.setattr(getpass, "getpass", _GetpassSequence())
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


def test_reset_eof_and_interrupt_have_zero_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RESET EOF 默认 No，SIGINT 返回 130，二者都不 bootstrap。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch 夹具。
    :returns: None。
    :raises AssertionError: 退出码或 zero-mutation contract 漂移时抛出。
    """

    eof_root = tmp_path / "eof"
    monkeypatch.setattr(builtins, "input", _EofInput())
    assert cli_main.main(("init", "--base", str(eof_root), "--reset")) == EXIT_SUCCESS
    assert not eof_root.exists()

    interrupt_root = tmp_path / "interrupt"
    monkeypatch.setattr(builtins, "input", _InterruptInput())
    assert cli_main.main(("init", "--base", str(interrupt_root), "--reset")) == EXIT_KEYBOARD_INTERRUPT
    assert not interrupt_root.exists()


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


def test_required_secret_refusal_stops_before_transaction_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Required secret 批次拒绝时不得 publish config 或泄漏 value。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch 夹具。
    :param capsys: pytest 输出捕获。
    :returns: None。
    :raises AssertionError: 拒绝后仍 publication 或输出 secret 时抛出。
    """

    secret = "sentinel-secret-value"
    workspace_root = tmp_path / "workspace"
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(builtins, "input", _InputSequence(("6", "n")))
    monkeypatch.setattr(
        getpass,
        "getpass",
        _GetpassSequence((secret, "", "", "", "", "")),
    )

    exit_code = cli_main.main(("init", "--base", str(workspace_root)))
    captured = capsys.readouterr()

    assert exit_code == EXIT_FAILURE
    assert not (workspace_root / "config").exists()
    assert secret not in captured.out
    assert secret not in captured.err
    assert os.environ.get("OPENAI_API_KEY") != secret


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
    monkeypatch.setattr(getpass, "getpass", _GetpassSequence((secret,)))
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
    monkeypatch.setattr(getpass, "getpass", _GetpassSequence((secret,)))
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
    monkeypatch.setattr(getpass, "getpass", _GetpassSequence((secret,)))
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
    monkeypatch.setattr(getpass, "getpass", _GetpassSequence((secret,)))
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


def test_model_choice_and_input_helpers_reject_invalid_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Selection/input helpers 必须拒绝空、越界、未知和非正 context。

    :param monkeypatch: pytest monkeypatch 夹具。
    :returns: None。
    :raises AssertionError: 非法交互输入被接受时抛出。
    """

    assert init_command._parse_model_choice("1").choice_id == "mimo-token-plan"
    assert init_command._parse_model_choice("ollama").choice_id == "ollama"
    for invalid in ("", "0", "16", "unknown"):
        with pytest.raises(init_command.CliInitOperationError):
            init_command._parse_model_choice(invalid)

    monkeypatch.setattr(builtins, "input", _InputSequence(("0",)))
    with pytest.raises(init_command.CliInitOperationError):
        init_command._read_positive_integer("context: ", default=1)
    monkeypatch.setattr(builtins, "input", _InputSequence(("",)))
    with pytest.raises(init_command.CliInitOperationError):
        init_command._read_non_empty_input("value: ", default=None)
    monkeypatch.setattr(builtins, "input", _InputSequence(("maybe",)))
    with pytest.raises(init_command.CliInitUsageError):
        init_command._confirm("confirm: ")


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
