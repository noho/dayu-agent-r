"""``dayu.cli.init_environment`` owner contract 测试。"""

from __future__ import annotations

import errno
import os
import secrets
import shlex
import stat
import subprocess
from pathlib import Path
from types import TracebackType
from typing import BinaryIO, NoReturn, cast

import pytest

from dayu.cli import init_environment
from dayu.cli.init_environment import (
    EnvironmentPersistenceEntry,
    EnvironmentPersistenceError,
    EnvironmentPersistenceInterrupted,
    EnvironmentPersistenceStatus,
    PosixEnvironmentPersistencePlan,
    WindowsEnvironmentPersistencePlan,
    has_non_empty_environment_value,
    persist_environment,
    plan_environment_persistence,
)


class _SetxRecorder:
    """记录 argument-safe ``setx`` 调用并提供确定返回码。"""

    def __init__(
        self,
        return_codes: tuple[int, ...],
        *,
        raise_at: int | None = None,
        interrupt_at: int | None = None,
    ) -> None:
        """初始化记录器。

        :param return_codes: 各次已执行调用的返回码。
        :param raise_at: 指定调用索引抛出 ``OSError``；``None`` 表示不抛出。
        :param interrupt_at: 指定调用索引抛出 ``KeyboardInterrupt``；``None`` 表示不抛出。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self._return_codes = return_codes
        self._raise_at = raise_at
        self._interrupt_at = interrupt_at
        self.calls: list[tuple[tuple[str, str, str], bool, bool, bool, bool]] = []
        self.environment_visible_during_calls: list[bool] = []

    def __call__(
        self,
        args: tuple[str, str, str],
        *,
        shell: bool,
        capture_output: bool,
        text: bool,
        check: bool,
    ) -> subprocess.CompletedProcess[bytes]:
        """模拟 ``subprocess.run`` 并记录不安全 flag 是否出现。

        :param args: ``setx`` argument tuple。
        :param shell: 是否启用 shell。
        :param capture_output: 是否捕获子进程输出。
        :param text: 是否按文本解码输出。
        :param check: 是否由 subprocess 自动抛错。
        :returns: 使用预设 return code 的 bytes ``CompletedProcess``。
        :raises OSError: 当前索引等于 ``raise_at`` 时抛出。
        :raises KeyboardInterrupt: 当前索引等于 ``interrupt_at`` 时抛出。
        """

        call_index = len(self.calls)
        self.calls.append((args, shell, capture_output, text, check))
        self.environment_visible_during_calls.append(args[1] in os.environ)
        if self._interrupt_at == call_index:
            raise KeyboardInterrupt
        if self._raise_at == call_index:
            raise OSError("setx unavailable")
        return subprocess.CompletedProcess(
            args=args,
            returncode=self._return_codes[call_index],
            stdout=b"ignored stdout",
            stderr=b"ignored stderr",
        )


class _FaultingBinaryHandle:
    """在真实 POSIX private temp write 前后注入一次故障。"""

    def __init__(self, handle: BinaryIO, *, fault_kind: str, timing: str) -> None:
        """初始化真实 binary handle wrapper。

        :param handle: ``os.fdopen`` 返回的真实 binary handle。
        :param fault_kind: ``os-error`` 或 ``interrupt``。
        :param timing: ``before`` 或 ``after`` write。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self._handle = handle
        self._fault_kind = fault_kind
        self._timing = timing

    def __enter__(self) -> _FaultingBinaryHandle:
        """进入 wrapper context。

        :returns: 当前 wrapper。
        :raises Exception: 不主动抛出异常。
        """

        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """关闭真实 handle。

        :param exc_type: context 内异常类型。
        :param exc_value: context 内异常实例。
        :param traceback: context 内 traceback。
        :returns: ``None``，不吞掉原异常。
        :raises OSError: 真实 handle close 失败时传播。
        """

        del exc_type, exc_value, traceback
        self._handle.close()

    def write(self, content: bytes) -> int:
        """在真实 write 前或后注入指定故障。

        :param content: 要写入 private temp 的 profile bytes。
        :returns: 未注入 before/after 故障时的真实写入长度。
        :raises OSError: ``fault_kind=os-error`` 时抛出。
        :raises KeyboardInterrupt: ``fault_kind=interrupt`` 时抛出。
        """

        if self._timing == "before":
            _raise_atomic_fault(self._fault_kind)
        written = self._handle.write(content)
        if self._timing == "after":
            _raise_atomic_fault(self._fault_kind)
        return written

    def flush(self) -> None:
        """刷新真实 handle。

        :returns: ``None``。
        :raises OSError: 真实 flush 失败时传播。
        """

        self._handle.flush()

    def fileno(self) -> int:
        """返回真实文件描述符。

        :returns: private temp 的文件描述符。
        :raises OSError: handle 已关闭时传播。
        """

        return self._handle.fileno()


class _InterruptingEnvironment(dict[str, str]):
    """在进程内环境注入阶段抛出一次中断。"""

    def __init__(self, *, interrupt_at: int) -> None:
        """初始化空环境与中断索引。

        :param interrupt_at: 第几个 ``__setitem__`` 调用抛出中断。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        super().__init__()
        self._interrupt_at = interrupt_at
        self._set_count = 0

    def __setitem__(self, name: str, value: str) -> None:
        """在指定位置中断，否则写入内存 mapping。

        :param name: 环境变量名。
        :param value: 环境变量值。
        :returns: ``None``。
        :raises KeyboardInterrupt: 当前调用命中中断索引时抛出。
        """

        current = self._set_count
        self._set_count += 1
        if current == self._interrupt_at:
            raise KeyboardInterrupt
        super().__setitem__(name, value)


def _raise_atomic_fault(fault_kind: str) -> NoReturn:
    """抛出 atomic writer 测试所需的 ordinary fault 或 interrupt。

    :param fault_kind: ``os-error`` 或 ``interrupt``。
    :returns: 本函数不返回。
    :raises OSError: ``fault_kind=os-error`` 时抛出。
    :raises KeyboardInterrupt: 其它受测值抛出中断。
    """

    if fault_kind == "os-error":
        raise OSError(errno.EIO, "atomic profile fault")
    raise KeyboardInterrupt


def _secret_value() -> str:
    """生成不会写入 tracked source/artifact 的运行期 secret sentinel。

    :returns: 随机 URL-safe secret 文本。
    :raises Exception: 系统随机源失败时传播异常。
    """

    return secrets.token_urlsafe(32)


def _entry(name: str = "OPENAI_API_KEY", *, value: str | None = None) -> EnvironmentPersistenceEntry:
    """构造测试 persistence entry。

    :param name: 固定 allowlist 中的环境变量名。
    :param value: 可选显式值；缺省生成运行期 sentinel。
    :returns: repr 脱敏的 entry。
    :raises EnvironmentPersistenceError: 名称或值不符合 owner contract 时抛出。
    """

    return EnvironmentPersistenceEntry(name=name, value=_secret_value() if value is None else value)


def _posix_plan(
    home_directory: Path,
    entries: tuple[EnvironmentPersistenceEntry, ...],
    *,
    shell_path: str = "/bin/zsh",
    confirmed: bool = True,
    platform_system: str = "Darwin",
) -> PosixEnvironmentPersistencePlan:
    """构造测试 POSIX typed plan。

    :param home_directory: 临时 HOME。
    :param entries: 新值批次。
    :param shell_path: 已检测 shell 路径。
    :param confirmed: 是否已完成最终确认。
    :param platform_system: ``Darwin`` 或 ``Linux``。
    :returns: POSIX persistence plan。
    :raises AssertionError: builder 未返回 POSIX plan 时抛出。
    :raises EnvironmentPersistenceError: 输入不受支持时抛出。
    """

    plan = plan_environment_persistence(
        entries=entries,
        platform_system=platform_system,
        home_directory=home_directory,
        shell_path=shell_path,
        confirmed=confirmed,
    )
    assert isinstance(plan, PosixEnvironmentPersistencePlan)
    return plan


def _windows_plan(
    home_directory: Path,
    entries: tuple[EnvironmentPersistenceEntry, ...],
    *,
    confirmed: bool = True,
) -> WindowsEnvironmentPersistencePlan:
    """构造测试 Windows typed plan。

    :param home_directory: builder 所需但 Windows 不消费的临时 HOME。
    :param entries: 新值批次。
    :param confirmed: 是否已完成最终确认。
    :returns: Windows persistence plan。
    :raises AssertionError: builder 未返回 Windows plan 时抛出。
    :raises EnvironmentPersistenceError: 输入不受支持时抛出。
    """

    plan = plan_environment_persistence(
        entries=entries,
        platform_system="Windows",
        home_directory=home_directory,
        shell_path="",
        confirmed=confirmed,
    )
    assert isinstance(plan, WindowsEnvironmentPersistencePlan)
    return plan


@pytest.mark.parametrize(
    ("platform_system", "shell_path", "profile_name"),
    [("Darwin", "/bin/zsh", ".zshrc"), ("Linux", "/usr/bin/bash", ".bashrc")],
)
def test_plan_selects_exactly_one_supported_posix_profile(
    tmp_path: Path,
    platform_system: str,
    shell_path: str,
    profile_name: str,
) -> None:
    """macOS/Linux 应根据已检测 shell 只选择一个 profile。

    :param tmp_path: pytest 提供的临时 HOME。
    :param platform_system: 要验证的受支持 POSIX 平台名。
    :param shell_path: 用于选择 profile 的已检测 shell 路径。
    :param profile_name: 当前平台与 shell 应选择的唯一 profile 名。
    :returns: None。
    :raises AssertionError: builder 类型或唯一 profile 选择不符合 contract 时抛出。
    :raises EnvironmentPersistenceError: 受支持的平台与 shell 被错误拒绝时传播。
    """

    plan = _posix_plan(
        tmp_path,
        (_entry(),),
        platform_system=platform_system,
        shell_path=shell_path,
    )

    assert plan.profile_path == tmp_path / profile_name


@pytest.mark.parametrize(
    ("platform_system", "shell_path", "message"),
    [("FreeBSD", "/bin/zsh", "platform"), ("Linux", "/usr/bin/fish", "shell")],
)
def test_plan_rejects_unsupported_platform_or_shell(
    tmp_path: Path,
    platform_system: str,
    shell_path: str,
    message: str,
) -> None:
    """不受支持的平台或 shell 必须在任何 profile mutation 前拒绝。

    :param tmp_path: pytest 提供的临时 HOME。
    :param platform_system: 要验证的受支持或不受支持平台名。
    :param shell_path: 要验证的受支持或不受支持 shell 路径。
    :param message: 预期错误信息中的边界关键词。
    :returns: None。
    :raises AssertionError: 输入未被拒绝或临时 HOME 出现 mutation 时抛出。
    :raises OSError: 临时 HOME 无法枚举时传播。
    """

    with pytest.raises(EnvironmentPersistenceError, match=message):
        plan_environment_persistence(
            entries=(_entry(),),
            platform_system=platform_system,
            home_directory=tmp_path,
            shell_path=shell_path,
            confirmed=True,
        )

    assert tuple(tmp_path.iterdir()) == ()


def test_direct_posix_plan_rejects_non_profile_target(tmp_path: Path) -> None:
    """直接构造 typed plan 也不得把 arbitrary path 变成 persistence target。

    :param tmp_path: pytest 提供的临时 HOME。
    :returns: None。
    :raises AssertionError: arbitrary target 未触发预期校验失败时抛出。
    """

    with pytest.raises(EnvironmentPersistenceError, match="persistence target"):
        PosixEnvironmentPersistencePlan(
            entries=(_entry(),),
            profile_path=tmp_path / "arbitrary-file",
            confirmed=True,
        )


def test_unconfirmed_posix_plan_does_not_create_profile_or_inject_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """未最终确认的 POSIX plan 必须零 profile mutation、零进程注入。

    :param tmp_path: pytest 提供的临时 HOME。
    :param monkeypatch: 隔离当前进程环境变量的 pytest fixture。
    :returns: None。
    :raises AssertionError: 未确认 plan 未被拒绝、创建 profile 或注入环境时抛出。
    """

    entry = _entry()
    monkeypatch.delenv(entry.name, raising=False)
    plan = _posix_plan(tmp_path, (entry,), confirmed=False)

    with pytest.raises(EnvironmentPersistenceError, match="not confirmed"):
        persist_environment(plan)

    assert not plan.profile_path.exists()
    assert entry.name not in os.environ


def test_absent_profile_is_private_atomic_quoted_and_injected_after_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """缺失 profile 只在确认后以 0600 创建，并用 shlex.quote 写入。

    :param tmp_path: pytest 提供的临时 HOME。
    :param monkeypatch: 隔离当前进程环境变量的 pytest fixture。
    :param capsys: 捕获并检查 stdout/stderr 脱敏的 pytest fixture。
    :returns: None。
    :raises AssertionError: 原子创建、权限、quote、注入或脱敏结果不符合 contract 时抛出。
    :raises EnvironmentPersistenceError: 合法 POSIX persistence plan 执行失败时传播。
    :raises OSError: profile 读取或权限检查失败时传播。
    """

    secret = f"{_secret_value()} with ' quotes $ and spaces"
    entry = _entry(value=secret)
    monkeypatch.delenv(entry.name, raising=False)
    plan = _posix_plan(tmp_path, (entry,))

    result = persist_environment(plan)
    content = plan.profile_path.read_text(encoding="utf-8")
    captured = capsys.readouterr()

    assert result.succeeded is True
    assert result.status is EnvironmentPersistenceStatus.SUCCESS
    assert result.written_names == (entry.name,)
    assert result.unwritten_names == ()
    assert stat.S_IMODE(plan.profile_path.stat().st_mode) == 0o600
    assert content.count("# >>> dayu-cli init >>>") == 1
    assert content.count("# <<< dayu-cli init <<<") == 1
    assert f"export {entry.name}={shlex.quote(secret)}" in content
    assert os.environ[entry.name] == secret
    assert secret not in repr(entry)
    assert secret not in repr(plan)
    assert secret not in repr(result)
    assert secret not in captured.out
    assert secret not in captured.err


def test_existing_marker_block_is_replaced_once_and_mode_is_preserved(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """恰好一对 marker 应整体替换，并保留 profile 原 mode 与外围文本。

    :param tmp_path: pytest 提供的临时 HOME。
    :param monkeypatch: 隔离当前进程环境变量的 pytest fixture。
    :returns: None。
    :raises AssertionError: marker 替换、外围文本、mode 或整批注入不符合 contract 时抛出。
    :raises EnvironmentPersistenceError: 合法已有 profile 的持久化执行失败时传播。
    :raises OSError: profile fixture 创建、读取或权限操作失败时传播。
    """

    old_secret = _secret_value()
    profile = tmp_path / ".bashrc"
    profile.write_text(
        "before\n"
        "# >>> dayu-cli init >>>\n"
        f"export OPENAI_API_KEY={shlex.quote(old_secret)}\n"
        "# <<< dayu-cli init <<<\n"
        "after\n",
        encoding="utf-8",
    )
    profile.chmod(0o640)
    first = _entry("OPENAI_API_KEY")
    second = _entry("HF_TOKEN")
    monkeypatch.delenv(first.name, raising=False)
    monkeypatch.delenv(second.name, raising=False)
    plan = _posix_plan(tmp_path, (first, second), shell_path="/bin/bash", platform_system="Linux")

    result = persist_environment(plan)
    content = profile.read_text(encoding="utf-8")

    assert result.succeeded is True
    assert content.startswith("before\n")
    assert content.endswith("after\n")
    assert content.count("# >>> dayu-cli init >>>") == 1
    assert content.count("# <<< dayu-cli init <<<") == 1
    assert old_secret not in content
    assert stat.S_IMODE(profile.stat().st_mode) == 0o640
    assert os.environ[first.name] == first.value
    assert os.environ[second.name] == second.value


@pytest.mark.parametrize(
    "marker_fragment",
    [
        pytest.param("# >>> dayu-cli init >>>", id="begin"),
        pytest.param("# <<< dayu-cli init <<<", id="end"),
        pytest.param(
            "# >>> dayu-cli init >>> and # <<< dayu-cli init <<<",
            id="begin-and-end",
        ),
    ],
)
@pytest.mark.parametrize("profile_state", ["absent", "existing"])
def test_marker_substrings_in_export_values_succeed_for_create_and_replace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    marker_fragment: str,
    profile_state: str,
) -> None:
    """合法 export value 含 marker 子串时，首次创建与已有替换都必须成功。

    :param tmp_path: pytest 提供的临时 HOME。
    :param monkeypatch: 隔离当前进程环境变量的 pytest fixture。
    :param marker_fragment: begin、end 或两者 marker 子串。
    :param profile_state: ``absent`` 或 ``existing`` profile 初态。
    :returns: ``None``。
    :raises AssertionError: 持久化结果、磁盘状态、mode 或进程注入不符合 contract 时抛出。
    :raises EnvironmentPersistenceError: 合法 value 被 persistence owner 错误拒绝时传播。
    """

    profile = tmp_path / ".zshrc"
    old_secret = _secret_value()
    if profile_state == "existing":
        profile.write_text(
            "before\n"
            "# >>> dayu-cli init >>>\n"
            f"export OPENAI_API_KEY={shlex.quote(old_secret)}\n"
            "# <<< dayu-cli init <<<\n"
            "after\n",
            encoding="utf-8",
        )
        profile.chmod(0o640)
    secret = f"{_secret_value()} {marker_fragment} {_secret_value()}"
    entry = _entry(value=secret)
    monkeypatch.delenv(entry.name, raising=False)

    result = persist_environment(_posix_plan(tmp_path, (entry,)))
    content = profile.read_text(encoding="utf-8")
    lines = content.splitlines()

    assert result.succeeded is True
    assert result.status is EnvironmentPersistenceStatus.SUCCESS
    assert result.written_names == (entry.name,)
    assert lines.count("# >>> dayu-cli init >>>") == 1
    assert lines.count("# <<< dayu-cli init <<<") == 1
    assert f"export {entry.name}={shlex.quote(secret)}" in lines
    assert os.environ[entry.name] == secret
    assert secret not in repr(result)
    if profile_state == "existing":
        assert content.startswith("before\n")
        assert content.endswith("after\n")
        assert old_secret not in content
        assert stat.S_IMODE(profile.stat().st_mode) == 0o640
    else:
        assert stat.S_IMODE(profile.stat().st_mode) == 0o600


@pytest.mark.parametrize(
    "malformed_content",
    [
        pytest.param(
            "# >>> dayu-cli init >>>\nexport OPENAI_API_KEY=value\n",
            id="missing-end",
        ),
        pytest.param("# <<< dayu-cli init <<<\n", id="missing-begin"),
        pytest.param(
            "# <<< dayu-cli init <<<\n# >>> dayu-cli init >>>\n",
            id="reverse-order",
        ),
        pytest.param(
            (
                "# >>> dayu-cli init >>>\nexport OPENAI_API_KEY=value\n# <<< dayu-cli init <<<\n"
                "# >>> dayu-cli init >>>\nexport HF_TOKEN=value\n# <<< dayu-cli init <<<\n"
            ),
            id="multiple-blocks",
        ),
        pytest.param(
            "prefix # >>> dayu-cli init >>> embedded\n",
            id="ordinary-text-embedded-marker",
        ),
        pytest.param(
            "# reference # <<< dayu-cli init <<< marker\n",
            id="comment-embedded-marker",
        ),
        pytest.param(
            "# >>> dayu-cli init >>>\ninvalid line\n# <<< dayu-cli init <<<\n",
            id="invalid-block-line",
        ),
        pytest.param(
            "# >>> dayu-cli init >>>\nexport OPENAI_API_KEY\n# <<< dayu-cli init <<<\n",
            id="invalid-block-export-shape",
        ),
        pytest.param(
            (
                "# >>> dayu-cli init >>>\n"
                "export USER_CONTROLLED_NAME='value # >>> dayu-cli init >>>'\n"
                "# <<< dayu-cli init <<<\n"
            ),
            id="invalid-block-export-name-with-marker-value",
        ),
    ],
)
def test_malformed_marker_structures_fail_closed_without_injection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    malformed_content: str,
) -> None:
    """缺配对、逆序、多块、嵌入和非法 export 均不得宽松修复。

    :param tmp_path: pytest 提供的临时 HOME。
    :param monkeypatch: 隔离当前进程环境变量的 pytest fixture。
    :param malformed_content: 应被 owner fail closed 的 profile 原文。
    :returns: ``None``。
    :raises AssertionError: profile 被改写、进程被注入或 secret 泄漏时抛出。
    """

    profile = tmp_path / ".zshrc"
    profile.write_text(malformed_content, encoding="utf-8")
    before = profile.read_bytes()
    entry = _entry()
    monkeypatch.delenv(entry.name, raising=False)

    with pytest.raises(EnvironmentPersistenceError) as error:
        persist_environment(_posix_plan(tmp_path, (entry,)))

    assert profile.read_bytes() == before
    assert entry.name not in os.environ
    assert entry.value not in repr(error.value)


@pytest.mark.parametrize("dangling", [False, True])
def test_profile_symlink_and_dangling_symlink_are_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    dangling: bool,
) -> None:
    """POSIX profile symlink 与 dangling symlink 都必须拒绝。

    :param tmp_path: pytest 提供的临时 HOME。
    :param monkeypatch: 隔离当前进程环境变量的 pytest fixture。
    :param dangling: 是否构造目标不存在的 dangling symlink。
    :returns: None。
    :raises AssertionError: symlink 未被拒绝、发生环境注入或 secret 泄漏时抛出。
    :raises OSError: symlink 或目标 fixture 创建、读取失败时传播。
    """

    target = tmp_path / "profile-target"
    if not dangling:
        target.write_text("target\n", encoding="utf-8")
    profile = tmp_path / ".zshrc"
    profile.symlink_to(target)
    entry = _entry()
    monkeypatch.delenv(entry.name, raising=False)

    with pytest.raises(EnvironmentPersistenceError, match="symlink") as error:
        persist_environment(_posix_plan(tmp_path, (entry,)))

    assert entry.name not in os.environ
    assert entry.value not in repr(error.value)
    if not dangling:
        assert target.read_text(encoding="utf-8") == "target\n"


def test_profile_directory_is_rejected_as_non_regular_file(tmp_path: Path) -> None:
    """同名目录不得被当作 profile 替换。

    :param tmp_path: pytest 提供的临时 HOME。
    :returns: None。
    :raises AssertionError: 同名目录未触发非普通文件校验失败时抛出。
    :raises OSError: profile 同名目录创建失败时传播。
    """

    (tmp_path / ".zshrc").mkdir()

    with pytest.raises(EnvironmentPersistenceError, match="regular file"):
        persist_environment(_posix_plan(tmp_path, (_entry(),)))


def test_atomic_replace_failure_preserves_profile_and_does_not_inject(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POSIX ``os.replace`` 故障必须保留旧 profile、清理私有临时文件且不注入。

    :param tmp_path: pytest 提供的临时 HOME。
    :param monkeypatch: 注入 replace 故障并隔离进程环境的 pytest fixture。
    :returns: None。
    :raises AssertionError: 旧 profile、临时文件清理、注入或脱敏结果不符合 contract 时抛出。
    :raises OSError: profile fixture 创建或读取失败时传播。
    """

    profile = tmp_path / ".zshrc"
    profile.write_text("user content\n", encoding="utf-8")
    before = profile.read_bytes()
    entry = _entry()
    monkeypatch.delenv(entry.name, raising=False)

    def raise_replace(source: Path, destination: Path) -> None:
        """注入原子 replace 故障。

        :param source: 私有临时文件路径。
        :param destination: profile 目标路径。
        :returns: 本函数不会返回。
        :raises OSError: 始终抛出测试故障。
        """

        raise OSError(f"replace blocked for {source.name} -> {destination.name}")

    monkeypatch.setattr(init_environment.os, "replace", raise_replace)

    with pytest.raises(EnvironmentPersistenceError, match="atomically write") as error:
        persist_environment(_posix_plan(tmp_path, (entry,)))

    assert profile.read_bytes() == before
    assert entry.name not in os.environ
    assert not tuple(tmp_path.glob(".dayu-init-env-*"))
    assert entry.value not in repr(error.value)


@pytest.mark.parametrize("operation", ("write", "fsync", "replace"))
@pytest.mark.parametrize("fault_kind", ("os-error", "interrupt"))
@pytest.mark.parametrize("timing", ("before", "after"))
def test_posix_atomic_faults_preserve_store_truth_and_remove_owned_secret_temp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
    fault_kind: str,
    timing: str,
) -> None:
    """write/fsync/replace 调用前后故障必须保留 store 真值并清理 owner temp。

    :param tmp_path: pytest 提供的临时 HOME。
    :param monkeypatch: 在真实 writer syscall lookup boundary 注入故障。
    :param operation: ``write``、``fsync`` 或 ``replace``。
    :param fault_kind: ``os-error`` 或 ``interrupt``。
    :param timing: 调用前或真实调用后抛错。
    :returns: ``None``。
    :raises AssertionError: durable truth、temp cleanup、环境注入或脱敏不符合 contract 时抛出。
    """

    entry = _entry(value=f"{_secret_value()}-atomic-fault")
    plan = _posix_plan(tmp_path, (entry,))
    monkeypatch.delenv(entry.name, raising=False)
    if operation == "write":
        real_fdopen = init_environment.os.fdopen

        def faulting_fdopen(file_descriptor: int, mode: str) -> _FaultingBinaryHandle:
            """返回只在真实 write 边界注入故障的 handle。

            :param file_descriptor: private temp 文件描述符。
            :param mode: owner 请求的 binary mode。
            :returns: faulting binary handle。
            :raises OSError: 真实 ``os.fdopen`` 失败时传播。
            """

            handle = cast(BinaryIO, real_fdopen(file_descriptor, mode))
            return _FaultingBinaryHandle(handle, fault_kind=fault_kind, timing=timing)

        monkeypatch.setattr(init_environment.os, "fdopen", faulting_fdopen)
    elif operation == "fsync":
        real_fsync = init_environment.os.fsync

        def faulting_fsync(file_descriptor: int) -> None:
            """在真实 file fsync 前或后抛出指定故障。

            :param file_descriptor: private temp 文件描述符。
            :returns: ``None``。
            :raises OSError: ``fault_kind=os-error`` 时抛出。
            :raises KeyboardInterrupt: ``fault_kind=interrupt`` 时抛出。
            """

            if timing == "before":
                _raise_atomic_fault(fault_kind)
            real_fsync(file_descriptor)
            _raise_atomic_fault(fault_kind)

        monkeypatch.setattr(init_environment.os, "fsync", faulting_fsync)
    else:
        real_replace = init_environment.os.replace

        def faulting_replace(source: Path, destination: Path) -> None:
            """在真实 profile replace 前或后抛出指定故障。

            :param source: owner private temp。
            :param destination: public profile。
            :returns: ``None``。
            :raises OSError: ``fault_kind=os-error`` 时抛出。
            :raises KeyboardInterrupt: ``fault_kind=interrupt`` 时抛出。
            """

            if timing == "before":
                _raise_atomic_fault(fault_kind)
            real_replace(source, destination)
            _raise_atomic_fault(fault_kind)

        monkeypatch.setattr(init_environment.os, "replace", faulting_replace)

    replace_after_effect = operation == "replace" and timing == "after"
    if replace_after_effect and fault_kind == "os-error":
        result = persist_environment(plan)
        assert result.status is EnvironmentPersistenceStatus.SUCCESS
        assert result.written_names == (entry.name,)
        assert os.environ[entry.name] == entry.value
    elif fault_kind == "os-error":
        with pytest.raises(EnvironmentPersistenceError) as captured:
            persist_environment(plan)
        assert entry.value not in repr(captured.value)
        assert entry.name not in os.environ
    else:
        with pytest.raises(EnvironmentPersistenceInterrupted) as captured:
            persist_environment(plan)
        result = captured.value.result
        assert result.status is EnvironmentPersistenceStatus.INTERRUPTED
        assert result.written_names == ((entry.name,) if replace_after_effect else ())
        assert result.unwritten_names == (() if replace_after_effect else (entry.name,))
        assert result.retained_paths == ()
        assert entry.value not in repr(captured.value)
        assert entry.value not in repr(result)
        assert entry.name not in os.environ

    assert not tuple(tmp_path.glob(".dayu-init-env-*"))
    if replace_after_effect:
        assert entry.value in plan.profile_path.read_text(encoding="utf-8")
    else:
        assert not plan.profile_path.exists()


@pytest.mark.parametrize("original_fault", ("os-error", "interrupt"))
@pytest.mark.parametrize("cleanup_fault", ("unlink", "identity-read"))
def test_posix_cleanup_failure_reports_retained_owner_temp_without_value(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    original_fault: str,
    cleanup_fault: str,
) -> None:
    """Owner temp 清理失败必须携带 retained path 且不泄漏其中的值。

    :param tmp_path: pytest 提供的临时 HOME。
    :param monkeypatch: 在 replace 与 cleanup owner lookup boundary 注入故障。
    :param original_fault: 原始写入边界抛普通错误或中断。
    :param cleanup_fault: cleanup 的 unlink 或 identity-read 故障。
    :returns: ``None``。
    :raises AssertionError: retained truth、identity-safe cleanup 或脱敏不符合 contract 时抛出。
    """

    entry = _entry(value=f"{_secret_value()}-retained-owner-temp")
    plan = _posix_plan(tmp_path, (entry,))
    temporary_paths: list[Path] = []
    monkeypatch.delenv(entry.name, raising=False)

    def fail_replace(source: Path, destination: Path) -> None:
        """在 public replace 前保存 owner temp path 并抛出原始故障。

        :param source: owner private temp path。
        :param destination: public profile path；本 fault 不消费。
        :returns: 本函数不返回。
        :raises OSError: ``original_fault=os-error`` 时抛出。
        :raises KeyboardInterrupt: ``original_fault=interrupt`` 时抛出。
        """

        del destination
        temporary_paths.append(source)
        _raise_atomic_fault(original_fault)

    monkeypatch.setattr(init_environment.os, "replace", fail_replace)
    if cleanup_fault == "unlink":

        def fail_unlink(path: Path) -> None:
            """拒绝删除精确 owner temp。

            :param path: cleanup 已核验的 owner temp path。
            :returns: 本函数不返回。
            :raises OSError: 始终注入 unlink 故障。
            """

            assert path == temporary_paths[0]
            raise OSError(errno.EIO, "profile temp unlink fault")

        monkeypatch.setattr(init_environment.os, "unlink", fail_unlink)
    else:
        real_lstat = init_environment.os.lstat
        owner_identity_reads = 0

        def fail_cleanup_identity_read(path: Path) -> os.stat_result:
            """只让 cleanup 阶段对 owner temp 的第二次 identity read 失败。

            :param path: no-follow identity 待读路径。
            :returns: replace 对账阶段的真实 stat。
            :raises OSError: cleanup 第二次读取 owner temp 时抛出。
            """

            nonlocal owner_identity_reads
            if temporary_paths and path == temporary_paths[0]:
                owner_identity_reads += 1
                if owner_identity_reads == 2:
                    raise OSError(errno.EIO, "profile temp identity fault")
            return real_lstat(path)

        monkeypatch.setattr(init_environment.os, "lstat", fail_cleanup_identity_read)

    if original_fault == "interrupt":
        with pytest.raises(EnvironmentPersistenceInterrupted) as captured_interrupt:
            persist_environment(plan)
        retained_paths = captured_interrupt.value.result.retained_paths
        rendered_exception = repr(captured_interrupt.value)
        rendered_truth = repr(captured_interrupt.value.result)
    else:
        with pytest.raises(EnvironmentPersistenceError) as captured_failure:
            persist_environment(plan)
        retained_paths = captured_failure.value.retained_paths
        rendered_exception = repr(captured_failure.value)
        rendered_truth = repr(captured_failure.value.retained_paths)

    retained = tuple(tmp_path.glob(".dayu-init-env-*"))
    assert retained_paths == retained
    assert len(retained) == 1
    assert retained[0].read_text(encoding="utf-8").find(entry.value) >= 0
    assert entry.value not in str(retained[0])
    assert entry.value not in rendered_exception
    assert entry.value not in rendered_truth
    assert not plan.profile_path.exists()
    assert entry.name not in os.environ


def test_posix_interrupt_does_not_delete_identity_drifted_temp_replacement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """中断清理不得按名称删除已不属于 writer identity 的 replacement。

    :param tmp_path: pytest 提供的临时 HOME。
    :param monkeypatch: 在 replace boundary 换入未知 identity 后中断。
    :returns: ``None``。
    :raises AssertionError: 未知文件被删除、secret temp 遗留或 store truth 错误时抛出。
    """

    entry = _entry(value=f"{_secret_value()}-identity-drift")
    plan = _posix_plan(tmp_path, (entry,))
    replacement_content = "not-owner-secret-material"
    monkeypatch.delenv(entry.name, raising=False)

    def replace_identity_then_interrupt(source: Path, destination: Path) -> None:
        """删除 owner temp 并在同名 path 换入未知普通文件后中断。

        :param source: owner private temp path。
        :param destination: public profile path；本 fault 不消费。
        :returns: 本函数不返回。
        :raises KeyboardInterrupt: identity 换入后始终抛出。
        """

        del destination
        source.unlink()
        source.write_text(replacement_content, encoding="utf-8")
        raise KeyboardInterrupt

    monkeypatch.setattr(init_environment.os, "replace", replace_identity_then_interrupt)

    with pytest.raises(EnvironmentPersistenceInterrupted) as captured:
        persist_environment(plan)

    retained = tuple(tmp_path.glob(".dayu-init-env-*"))
    assert captured.value.result.written_names == ()
    assert captured.value.result.unwritten_names == (entry.name,)
    assert captured.value.result.retained_paths == retained
    assert len(retained) == 1
    assert retained[0].read_text(encoding="utf-8") == replacement_content
    assert entry.value not in retained[0].read_text(encoding="utf-8")
    assert entry.value not in repr(captured.value)
    assert not plan.profile_path.exists()
    assert entry.name not in os.environ


def test_post_write_structure_verification_precedes_environment_injection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """写后结构校验失败时即使 profile 已替换也不得注入当前进程。

    :param tmp_path: pytest 提供的临时 HOME。
    :param monkeypatch: 注入写后校验故障并隔离进程环境的 pytest fixture。
    :returns: None。
    :raises AssertionError: profile 发布状态、零注入或脱敏结果不符合 contract 时抛出。
    """

    entry = _entry()
    monkeypatch.delenv(entry.name, raising=False)

    def reject_verification(*, profile_path: Path, expected_names: tuple[str, ...], expected_mode: int) -> None:
        """注入写后结构校验故障。

        :param profile_path: 已发布 profile 路径。
        :param expected_names: 预期变量名。
        :param expected_mode: 预期权限位。
        :returns: 本函数不会返回。
        :raises EnvironmentPersistenceError: 始终抛出测试故障。
        """

        raise EnvironmentPersistenceError(
            f"verification rejected: {profile_path.name}/{len(expected_names)}/{expected_mode:o}"
        )

    monkeypatch.setattr(init_environment, "_verify_written_profile", reject_verification)

    with pytest.raises(EnvironmentPersistenceError, match="verification rejected") as error:
        persist_environment(_posix_plan(tmp_path, (entry,)))

    assert (tmp_path / ".zshrc").exists()
    assert entry.name not in os.environ
    assert entry.value not in repr(error.value)


def test_windows_uses_argument_tuple_binary_capture_and_injects_only_after_all_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Windows 必须用安全 argv/flags，并在两个 setx 都成功后整批注入。

    :param tmp_path: pytest 提供给 Windows plan builder 的临时 HOME。
    :param monkeypatch: 替换 setx runner 并隔离进程环境的 pytest fixture。
    :param capsys: 捕获并检查 stdout/stderr 脱敏的 pytest fixture。
    :returns: None。
    :raises AssertionError: setx argv/flags、整批注入、结果名称或脱敏不符合 contract 时抛出。
    :raises EnvironmentPersistenceError: 合法 Windows persistence plan 被错误拒绝时传播。
    """

    first = _entry("OPENAI_API_KEY")
    second = _entry("HF_TOKEN")
    for entry in (first, second):
        monkeypatch.delenv(entry.name, raising=False)
    recorder = _SetxRecorder((0, 0))
    monkeypatch.setattr(init_environment.subprocess, "run", recorder)

    result = persist_environment(_windows_plan(tmp_path, (first, second)))
    captured = capsys.readouterr()

    assert result.status is EnvironmentPersistenceStatus.SUCCESS
    assert result.written_names == (first.name, second.name)
    assert result.unwritten_names == ()
    assert recorder.calls == [
        (("setx", first.name, first.value), False, True, False, False),
        (("setx", second.name, second.value), False, True, False, False),
    ]
    assert recorder.environment_visible_during_calls == [False, False]
    assert os.environ[first.name] == first.value
    assert os.environ[second.name] == second.value
    for entry in (first, second):
        assert entry.value not in repr(result)
        assert entry.value not in captured.out
        assert entry.value not in captured.err


@pytest.mark.parametrize("failure_mode", ["return-code", "os-error"])
def test_windows_partial_failure_reports_names_only_and_injects_nothing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_mode: str,
) -> None:
    """Windows 中途失败只报告已写/未写名称，不注入已成功的前缀。

    :param tmp_path: pytest 提供给 Windows plan builder 的临时 HOME。
    :param monkeypatch: 替换 setx runner 并隔离进程环境的 pytest fixture。
    :param failure_mode: 以非零返回码或 ``OSError`` 构造的中途失败模式。
    :returns: None。
    :raises AssertionError: partial failure 名称、调用次数、零注入或脱敏不符合 contract 时抛出。
    :raises EnvironmentPersistenceError: 合法 Windows persistence plan 构造失败时传播。
    """

    entries = (
        _entry("OPENAI_API_KEY"),
        _entry("HF_TOKEN"),
        _entry("FMP_API_KEY"),
    )
    for entry in entries:
        monkeypatch.delenv(entry.name, raising=False)
    recorder = (
        _SetxRecorder((0, 1, 0))
        if failure_mode == "return-code"
        else _SetxRecorder((0, 0, 0), raise_at=1)
    )
    monkeypatch.setattr(init_environment.subprocess, "run", recorder)

    result = persist_environment(_windows_plan(tmp_path, entries))

    assert result.status is EnvironmentPersistenceStatus.PARTIAL_FAILURE
    assert result.succeeded is False
    assert result.written_names == (entries[0].name,)
    assert result.unwritten_names == (entries[1].name, entries[2].name)
    assert len(recorder.calls) == 2
    for entry in entries:
        assert entry.name not in os.environ
        assert entry.value not in repr(result)


def test_windows_first_failure_has_failure_status_and_no_injection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Windows 首项失败应报告完整未写名称且不注入。

    :param tmp_path: pytest 提供给 Windows plan builder 的临时 HOME。
    :param monkeypatch: 替换 setx runner 并隔离进程环境的 pytest fixture。
    :returns: None。
    :raises AssertionError: failure 状态、完整未写名称、调用次数或零注入不符合 contract 时抛出。
    :raises EnvironmentPersistenceError: 合法 Windows persistence plan 构造失败时传播。
    """

    entries = (_entry("OPENAI_API_KEY"), _entry("HF_TOKEN"))
    for entry in entries:
        monkeypatch.delenv(entry.name, raising=False)
    recorder = _SetxRecorder((1, 0))
    monkeypatch.setattr(init_environment.subprocess, "run", recorder)

    result = persist_environment(_windows_plan(tmp_path, entries))

    assert result.status is EnvironmentPersistenceStatus.FAILURE
    assert result.written_names == ()
    assert result.unwritten_names == tuple(entry.name for entry in entries)
    assert len(recorder.calls) == 1
    assert all(entry.name not in os.environ for entry in entries)


@pytest.mark.parametrize("interrupt_at", (0, 1, 2), ids=("first", "middle", "last"))
def test_windows_interrupt_reports_written_and_unwritten_names_without_values(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    interrupt_at: int,
) -> None:
    """Windows first/middle/last setx 中断必须保留最小 names truth。

    :param tmp_path: pytest 提供给 Windows plan builder 的临时 HOME。
    :param monkeypatch: 替换 setx runner 并隔离当前进程环境。
    :param interrupt_at: 抛出中断的 setx 调用索引。
    :returns: ``None``。
    :raises AssertionError: written/unwritten、调用次数、零注入或脱敏不符合 contract 时抛出。
    """

    entries = (
        _entry("OPENAI_API_KEY"),
        _entry("HF_TOKEN"),
        _entry("FMP_API_KEY"),
    )
    for entry in entries:
        monkeypatch.delenv(entry.name, raising=False)
    recorder = _SetxRecorder((0, 0, 0), interrupt_at=interrupt_at)
    monkeypatch.setattr(init_environment.subprocess, "run", recorder)

    with pytest.raises(EnvironmentPersistenceInterrupted) as captured:
        persist_environment(_windows_plan(tmp_path, entries))

    result = captured.value.result
    assert result.status is EnvironmentPersistenceStatus.INTERRUPTED
    assert result.written_names == tuple(entry.name for entry in entries[:interrupt_at])
    assert result.unwritten_names == tuple(entry.name for entry in entries[interrupt_at:])
    assert len(recorder.calls) == interrupt_at + 1
    assert all(entry.name not in os.environ for entry in entries)
    for entry in entries:
        assert entry.value not in repr(captured.value)
        assert entry.value not in repr(result)


def test_windows_environment_injection_interrupt_keeps_completed_store_truth(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """全部 setx 完成后的进程内注入中断必须报告全部 durable names。

    :param tmp_path: pytest 提供给 Windows plan builder 的临时 HOME。
    :param monkeypatch: 替换 setx runner 与进程环境 mapping。
    :returns: ``None``。
    :raises AssertionError: completed store truth、调用次数或脱敏不符合 contract 时抛出。
    """

    entries = (_entry("OPENAI_API_KEY"), _entry("HF_TOKEN"))
    recorder = _SetxRecorder((0, 0))
    environment = _InterruptingEnvironment(interrupt_at=0)
    monkeypatch.setattr(init_environment.subprocess, "run", recorder)
    monkeypatch.setattr(init_environment.os, "environ", environment)

    with pytest.raises(EnvironmentPersistenceInterrupted) as captured:
        persist_environment(_windows_plan(tmp_path, entries))

    result = captured.value.result
    assert result.status is EnvironmentPersistenceStatus.INTERRUPTED
    assert result.written_names == tuple(entry.name for entry in entries)
    assert result.unwritten_names == ()
    assert len(recorder.calls) == len(entries)
    assert environment == {}
    for entry in entries:
        assert entry.value not in repr(captured.value)
        assert entry.value not in repr(result)


def test_unconfirmed_windows_plan_never_calls_setx(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """未最终确认的 Windows plan 必须零 setx 调用。

    :param tmp_path: pytest 提供给 Windows plan builder 的临时 HOME。
    :param monkeypatch: 替换 setx runner 的 pytest fixture。
    :returns: None。
    :raises AssertionError: 未确认 plan 未被拒绝或发生 setx 调用时抛出。
    """

    recorder = _SetxRecorder((0,))
    monkeypatch.setattr(init_environment.subprocess, "run", recorder)

    with pytest.raises(EnvironmentPersistenceError, match="not confirmed"):
        persist_environment(_windows_plan(tmp_path, (_entry(),), confirmed=False))

    assert recorder.calls == []


def test_entry_and_plan_validation_never_expose_secret_values() -> None:
    """非法 value、名称、空批次与重复名称错误都不得包含 secret。

    :returns: None。
    :raises AssertionError: 任一非法输入未被拒绝或错误/repr 泄漏 secret 时抛出。
    """

    secret = _secret_value()
    with pytest.raises(EnvironmentPersistenceError) as control_error:
        EnvironmentPersistenceEntry(name="OPENAI_API_KEY", value=f"{secret}\n")
    with pytest.raises(EnvironmentPersistenceError) as name_error:
        EnvironmentPersistenceEntry(name="USER_CONTROLLED_NAME", value=secret)
    with pytest.raises(EnvironmentPersistenceError, match="at least one"):
        WindowsEnvironmentPersistencePlan(entries=(), confirmed=True)
    duplicate = _entry(value=secret)
    with pytest.raises(EnvironmentPersistenceError, match="duplicate") as duplicate_error:
        WindowsEnvironmentPersistencePlan(entries=(duplicate, duplicate), confirmed=True)

    assert secret not in repr(control_error.value)
    assert secret not in repr(name_error.value)
    assert secret not in repr(duplicate_error.value)
    assert secret not in repr(duplicate)


def test_environment_presence_check_uses_non_empty_value_and_fixed_names() -> None:
    """已有非空变量可复用；空值与任意用户名称不得被误认。

    :returns: None。
    :raises AssertionError: 非空判断或固定名称 allowlist 行为不符合 contract 时抛出。
    """

    secret = _secret_value()

    assert has_non_empty_environment_value("OPENAI_API_KEY", {"OPENAI_API_KEY": secret}) is True
    assert has_non_empty_environment_value("OPENAI_API_KEY", {"OPENAI_API_KEY": ""}) is False
    assert has_non_empty_environment_value("OPENAI_API_KEY", {}) is False
    with pytest.raises(EnvironmentPersistenceError, match="unsupported"):
        has_non_empty_environment_value("USER_CONTROLLED_NAME", {"USER_CONTROLLED_NAME": secret})
