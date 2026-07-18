"""``dayu-cli init`` 的环境变量持久化 owner。

本模块把用户已确认的新环境变量作为一个不可变批次写入唯一 POSIX shell
profile 或 Windows 用户环境。结果与错误只携带变量名和安全目标，不携带
secret value；只有整个批次持久化成功后才更新当前进程 ``os.environ``。
"""

from __future__ import annotations

import os
import shlex
import stat
import subprocess
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Final, TypeAlias

from dayu.cli.init_catalog import INIT_MODEL_CHOICES

_DAYU_BLOCK_BEGIN: Final[str] = "# >>> dayu-cli init >>>"
_DAYU_BLOCK_END: Final[str] = "# <<< dayu-cli init <<<"
_EXPORT_PREFIX: Final[str] = "export "
_NEW_PROFILE_MODE: Final[int] = 0o600
_WINDOWS_SETX_TARGET: Final[str] = "setx"
_WINDOWS_PLATFORM: Final[str] = "Windows"
_LINUX_PLATFORM: Final[str] = "Linux"
_DARWIN_PLATFORM: Final[str] = "Darwin"
_ZSH_NAME: Final[str] = "zsh"
_BASH_NAME: Final[str] = "bash"

OPTIONAL_ENVIRONMENT_NAMES: Final[tuple[str, ...]] = (
    "TAVILY_API_KEY",
    "SERPER_API_KEY",
    "FMP_API_KEY",
    "HF_ENDPOINT",
    "HF_TOKEN",
)
"""Init 可选集成允许收集的固定环境变量名。"""

_CATALOG_SECRET_ENVIRONMENT_NAMES: Final[frozenset[str]] = frozenset(
    choice.required_secret_env_name
    for choice in INIT_MODEL_CHOICES
    if choice.required_secret_env_name is not None
)
ALLOWED_ENVIRONMENT_NAMES: Final[frozenset[str]] = (
    _CATALOG_SECRET_ENVIRONMENT_NAMES | frozenset(OPTIONAL_ENVIRONMENT_NAMES)
)
"""模型目录与可选集成共同产生的唯一允许变量名集合。"""


class EnvironmentPersistenceError(RuntimeError):
    """持久化计划、profile 结构或 OS 写入失败时抛出的脱敏错误。

    :param message: 不含环境变量值的失败说明。
    :param retained_paths: 仍存在或无法确认已清理的私有临时路径。
    """

    retained_paths: tuple[Path, ...]

    def __init__(self, message: str, *, retained_paths: tuple[Path, ...] = ()) -> None:
        """初始化带最小 retained-path 真值的持久化错误。

        :param message: 不含环境变量值的失败说明。
        :param retained_paths: 仍存在或无法确认已清理的私有临时路径。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        super().__init__(message)
        self.retained_paths = retained_paths


class EnvironmentPlatform(StrEnum):
    """Init 明确支持的标准 ``platform.system()`` 值。"""

    WINDOWS = _WINDOWS_PLATFORM
    LINUX = _LINUX_PLATFORM
    DARWIN = _DARWIN_PLATFORM


class EnvironmentPersistenceStatus(StrEnum):
    """环境变量批次持久化结果类别。"""

    SUCCESS = "success"
    FAILURE = "failure"
    PARTIAL_FAILURE = "partial_failure"
    INTERRUPTED = "interrupted"


@dataclass(frozen=True, slots=True)
class EnvironmentPersistenceEntry:
    """单个受限环境变量写入项。

    :param name: catalog/可选集成 owner 明确允许的变量名。
    :param value: secret 或敏感配置值；repr 永远省略。
    """

    name: str
    value: str = field(repr=False)

    def __post_init__(self) -> None:
        """校验变量名来源和值的本地安全边界。

        :returns: ``None``。
        :raises EnvironmentPersistenceError: 名称不受支持、值为空或含 NUL/CR/LF 时抛出。
        """

        _validate_environment_name(self.name)
        if not self.value:
            raise EnvironmentPersistenceError(f"environment value must be non-empty: {self.name}")
        if any(character in self.value for character in ("\x00", "\r", "\n")):
            raise EnvironmentPersistenceError(f"environment value contains a forbidden control character: {self.name}")


@dataclass(frozen=True, slots=True)
class PosixEnvironmentPersistencePlan:
    """写入单个 POSIX shell profile 的已确认批次。

    :param entries: 按用户确认顺序排列的新值。
    :param profile_path: 唯一目标 ``~/.zshrc`` 或 ``~/.bashrc``。
    :param confirmed: 用户是否已完成最终批次确认。
    """

    entries: tuple[EnvironmentPersistenceEntry, ...]
    profile_path: Path
    confirmed: bool

    def __post_init__(self) -> None:
        """校验批次非空且变量名不重复。

        :returns: ``None``。
        :raises EnvironmentPersistenceError: 批次为空、变量名重复或 profile 名称非法时抛出。
        """

        _validate_entry_batch(self.entries)
        if self.profile_path.name not in {".zshrc", ".bashrc"}:
            raise EnvironmentPersistenceError("POSIX persistence target must be .zshrc or .bashrc")


@dataclass(frozen=True, slots=True)
class WindowsEnvironmentPersistencePlan:
    """逐项调用 Windows ``setx`` 的已确认批次。

    :param entries: 按用户确认顺序排列的新值。
    :param confirmed: 用户是否已完成最终批次确认。
    """

    entries: tuple[EnvironmentPersistenceEntry, ...]
    confirmed: bool

    def __post_init__(self) -> None:
        """校验批次非空且变量名不重复。

        :returns: ``None``。
        :raises EnvironmentPersistenceError: 批次为空或变量名重复时抛出。
        """

        _validate_entry_batch(self.entries)


EnvironmentPersistencePlan: TypeAlias = PosixEnvironmentPersistencePlan | WindowsEnvironmentPersistencePlan
"""POSIX 与 Windows typed persistence plan 联合。"""


@dataclass(frozen=True, slots=True)
class EnvironmentPersistenceResult:
    """不携带环境变量值的批次持久化结果。

    :param status: 完整成功、完整失败、Windows 部分失败或中断。
    :param target: 安全目标描述；POSIX 为 profile 路径，Windows 为 ``setx``。
    :param written_names: 已由 OS store 成功写入的变量名。
    :param unwritten_names: 尚未获得 OS store 成功确认的变量名。
    :param retained_paths: 仍存在或无法确认已清理的私有临时路径。
    """

    status: EnvironmentPersistenceStatus
    target: str
    written_names: tuple[str, ...]
    unwritten_names: tuple[str, ...]
    retained_paths: tuple[Path, ...]

    @property
    def succeeded(self) -> bool:
        """返回整个批次是否成功。

        :returns: 只有 ``status=success`` 时返回 ``True``。
        :raises Exception: 不主动抛出异常。
        """

        return self.status is EnvironmentPersistenceStatus.SUCCESS


class EnvironmentPersistenceInterrupted(KeyboardInterrupt):
    """携带脱敏 OS store 写入真值的环境持久化中断。

    ``result`` 只包含目标与环境变量名，不包含值或 ``setx`` captured output。

    :param result: 中断时已经确认写入和尚未确认写入的名称真值。
    """

    result: EnvironmentPersistenceResult

    def __init__(self, result: EnvironmentPersistenceResult) -> None:
        """初始化仍保持 ``KeyboardInterrupt`` 退出语义的 typed interrupt。

        :param result: 中断时的脱敏持久化结果。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        super().__init__("environment persistence interrupted")
        self.result = result


@dataclass(frozen=True, slots=True)
class _ProfileState:
    """POSIX profile 的 no-symlink 读取快照。

    :param content: UTF-8 profile 文本。
    :param mode: 需要由原子替换保留的权限位。
    """

    content: str
    mode: int


@dataclass(frozen=True, slots=True)
class _ProfileTemporaryIdentity:
    """POSIX profile 私有临时文件的 no-follow identity。

    :param device: 创建时 ``st_dev``。
    :param inode: 创建时 ``st_ino``。
    """

    device: int
    inode: int


class _ProfilePathIdentityStatus(StrEnum):
    """私有 profile path 相对 owner identity 的 no-follow 分类。"""

    OWNED = "owned"
    ABSENT = "absent"
    DRIFTED = "drifted"
    UNREADABLE = "unreadable"


@dataclass(frozen=True, slots=True)
class _ManagedProfileBlock:
    """profile 中唯一 Dayu marker block 的结构位置。

    :param begin_line_index: begin marker 所在行。
    :param end_line_index: end marker 所在行。
    :param environment_names: block 内按顺序声明的变量名。
    """

    begin_line_index: int
    end_line_index: int
    environment_names: tuple[str, ...]


def has_non_empty_environment_value(name: str, environment: Mapping[str, str]) -> bool:
    """判断受支持变量在当前进程环境中是否已有非空值。

    :param name: 受支持环境变量名。
    :param environment: 当前进程环境的只读视图。
    :returns: 存在非空值时返回 ``True``。
    :raises EnvironmentPersistenceError: 名称不在固定 allowlist 时抛出。
    """

    _validate_environment_name(name)
    value = environment.get(name)
    return value is not None and bool(value)


def plan_environment_persistence(
    *,
    entries: tuple[EnvironmentPersistenceEntry, ...],
    platform_system: str,
    home_directory: Path,
    shell_path: str,
    confirmed: bool,
) -> EnvironmentPersistencePlan:
    """依据明确标准平台值构造单目标 typed persistence plan。

    :param entries: 用户已决定持久化的新值批次。
    :param platform_system: 标准 ``platform.system()`` 返回值。
    :param home_directory: 当前用户 HOME；POSIX profile 的唯一父目录。
    :param shell_path: 已检测的 shell 路径；POSIX 只接受 zsh/bash。
    :param confirmed: 用户是否已完成最终批次确认。
    :returns: POSIX 单 profile 或 Windows ``setx`` 计划。
    :raises EnvironmentPersistenceError: 平台/shell 不受支持或批次非法时抛出。
    """

    try:
        platform_value = EnvironmentPlatform(platform_system)
    except ValueError:
        raise EnvironmentPersistenceError(f"unsupported environment persistence platform: {platform_system}") from None
    if platform_value is EnvironmentPlatform.WINDOWS:
        return WindowsEnvironmentPersistencePlan(entries=entries, confirmed=confirmed)
    profile_path = _profile_path_for_shell(home_directory=home_directory, shell_path=shell_path)
    return PosixEnvironmentPersistencePlan(
        entries=entries,
        profile_path=profile_path,
        confirmed=confirmed,
    )


def persist_environment(plan: EnvironmentPersistencePlan) -> EnvironmentPersistenceResult:
    """执行已确认批次，并只在 whole-batch success 后注入当前进程环境。

    :param plan: POSIX 或 Windows typed persistence plan。
    :returns: 只包含目标与变量名的脱敏结果。
    :raises EnvironmentPersistenceError: 未确认、POSIX profile 或原子写入失败时抛出。
    :raises EnvironmentPersistenceInterrupted: OS store 或进程内注入中断时携带名称真值抛出。
    """

    if not plan.confirmed:
        raise EnvironmentPersistenceError("environment persistence plan was not confirmed")
    if isinstance(plan, PosixEnvironmentPersistencePlan):
        result = _persist_posix_environment(plan)
    else:
        result = _persist_windows_environment(plan)
    if result.succeeded:
        try:
            for entry in plan.entries:
                os.environ[entry.name] = entry.value
        except KeyboardInterrupt:
            raise EnvironmentPersistenceInterrupted(
                _interrupted_result(
                    target=result.target,
                    written_names=result.written_names,
                    unwritten_names=result.unwritten_names,
                    retained_paths=result.retained_paths,
                )
            ) from None
    return result


def _profile_path_for_shell(*, home_directory: Path, shell_path: str) -> Path:
    """按已检测 shell 选择唯一 POSIX profile。

    :param home_directory: 当前用户 HOME。
    :param shell_path: shell 可执行文件路径或名称。
    :returns: ``~/.zshrc`` 或 ``~/.bashrc``。
    :raises EnvironmentPersistenceError: shell 不是 zsh/bash 时抛出。
    """

    shell_name = Path(shell_path).name
    if shell_name == _ZSH_NAME:
        return home_directory / ".zshrc"
    if shell_name == _BASH_NAME:
        return home_directory / ".bashrc"
    raise EnvironmentPersistenceError(f"unsupported POSIX shell for environment persistence: {shell_name or '<empty>'}")


def _persist_posix_environment(plan: PosixEnvironmentPersistencePlan) -> EnvironmentPersistenceResult:
    """以唯一 marker block 原子写入 POSIX profile。

    :param plan: 已确认 POSIX 批次。
    :returns: whole-batch success 结果。
    :raises EnvironmentPersistenceError: profile shape、symlink、I/O 或写后校验失败时抛出。
    :raises EnvironmentPersistenceInterrupted: 原子写入或写后校验中断时携带名称真值抛出。
    """

    profile_state = _read_profile_state(plan.profile_path)
    next_content = _render_profile_content(content=profile_state.content, entries=plan.entries)
    names = tuple(entry.name for entry in plan.entries)
    _write_profile_atomically(
        profile_path=plan.profile_path,
        content=next_content,
        mode=profile_state.mode,
        expected_names=names,
    )
    try:
        _verify_written_profile(
            profile_path=plan.profile_path,
            expected_names=names,
            expected_mode=profile_state.mode,
        )
    except KeyboardInterrupt:
        raise EnvironmentPersistenceInterrupted(
            _interrupted_result(
                target=str(plan.profile_path),
                written_names=names,
                unwritten_names=(),
                retained_paths=(),
            )
        ) from None
    return EnvironmentPersistenceResult(
        status=EnvironmentPersistenceStatus.SUCCESS,
        target=str(plan.profile_path),
        written_names=names,
        unwritten_names=(),
        retained_paths=(),
    )


def _persist_windows_environment(plan: WindowsEnvironmentPersistencePlan) -> EnvironmentPersistenceResult:
    """用 argument-safe ``setx`` 顺序写入 Windows 用户环境。

    第一个失败项会停止后续写入，避免扩大不可回滚的 registry mutation；结果
    精确区分已经写入和尚未写入的变量名。

    :param plan: 已确认 Windows 批次。
    :returns: success、failure 或 partial-failure 脱敏结果。
    :raises EnvironmentPersistenceInterrupted: ``setx`` 中断时携带已确认/未确认名称抛出。
    """

    written_names: list[str] = []
    for index, entry in enumerate(plan.entries):
        try:
            completed = subprocess.run(
                ("setx", entry.name, entry.value),
                shell=False,
                capture_output=True,
                text=False,
                check=False,
            )
        except KeyboardInterrupt:
            raise EnvironmentPersistenceInterrupted(
                _interrupted_result(
                    target=_WINDOWS_SETX_TARGET,
                    written_names=tuple(written_names),
                    unwritten_names=tuple(item.name for item in plan.entries[index:]),
                    retained_paths=(),
                )
            ) from None
        except OSError:
            return _windows_failure_result(plan=plan, written_names=tuple(written_names), failed_index=index)
        if completed.returncode != 0:
            return _windows_failure_result(plan=plan, written_names=tuple(written_names), failed_index=index)
        written_names.append(entry.name)
    return EnvironmentPersistenceResult(
        status=EnvironmentPersistenceStatus.SUCCESS,
        target=_WINDOWS_SETX_TARGET,
        written_names=tuple(written_names),
        unwritten_names=(),
        retained_paths=(),
    )


def _windows_failure_result(
    *,
    plan: WindowsEnvironmentPersistencePlan,
    written_names: tuple[str, ...],
    failed_index: int,
) -> EnvironmentPersistenceResult:
    """构造不声称回滚的 Windows 失败结果。

    :param plan: 原始 Windows 批次。
    :param written_names: 失败前已成功写入的变量名。
    :param failed_index: 首个失败或未启动项索引。
    :returns: 只含已写/未写名称的 failure 或 partial-failure 结果。
    :raises Exception: 不主动抛出异常。
    """

    status = (
        EnvironmentPersistenceStatus.PARTIAL_FAILURE
        if written_names
        else EnvironmentPersistenceStatus.FAILURE
    )
    return EnvironmentPersistenceResult(
        status=status,
        target=_WINDOWS_SETX_TARGET,
        written_names=written_names,
        unwritten_names=tuple(entry.name for entry in plan.entries[failed_index:]),
        retained_paths=(),
    )


def _read_profile_state(profile_path: Path) -> _ProfileState:
    """读取 profile，并拒绝 symlink、dangling symlink 与非普通文件。

    :param profile_path: 唯一目标 profile。
    :returns: 现有内容/权限，或不存在时的空内容/``0600``。
    :raises EnvironmentPersistenceError: profile 非普通文件、不是 UTF-8 或读取失败时抛出。
    """

    if profile_path.is_symlink():
        raise EnvironmentPersistenceError(f"POSIX profile must not be a symlink: {profile_path}")
    try:
        profile_stat = profile_path.lstat()
    except FileNotFoundError:
        return _ProfileState(content="", mode=_NEW_PROFILE_MODE)
    except OSError:
        raise EnvironmentPersistenceError(f"unable to inspect POSIX profile: {profile_path}") from None
    if not stat.S_ISREG(profile_stat.st_mode):
        raise EnvironmentPersistenceError(f"POSIX profile must be a regular file: {profile_path}")
    try:
        content = profile_path.read_bytes().decode("utf-8")
    except (OSError, UnicodeError):
        raise EnvironmentPersistenceError(f"unable to read UTF-8 POSIX profile: {profile_path}") from None
    return _ProfileState(content=content, mode=stat.S_IMODE(profile_stat.st_mode))


def _render_profile_content(
    *,
    content: str,
    entries: tuple[EnvironmentPersistenceEntry, ...],
) -> str:
    """追加或整体替换唯一 Dayu marker block。

    :param content: 现有 profile 原文。
    :param entries: 已确认变量批次。
    :returns: 使用 ``shlex.quote`` 形成的新 profile 原文。
    :raises EnvironmentPersistenceError: marker 缺失配对、多块、重叠或 block 行非法时抛出。
    """

    block = _render_managed_block(entries)
    managed = _parse_managed_block(content)
    if managed is None:
        prefix = content
        if prefix and not prefix.endswith(("\n", "\r")):
            prefix = f"{prefix}\n"
        if prefix:
            prefix = f"{prefix}\n"
        return f"{prefix}{block}"
    lines = content.splitlines(keepends=True)
    return "".join(
        [
            *lines[: managed.begin_line_index],
            block,
            *lines[managed.end_line_index + 1 :],
        ]
    )


def _render_managed_block(entries: tuple[EnvironmentPersistenceEntry, ...]) -> str:
    """把批次渲染为唯一 marker block。

    :param entries: 已确认变量批次。
    :returns: 以换行结束的 marker block 文本。
    :raises Exception: 不主动抛出异常。
    """

    export_lines = tuple(f"{_EXPORT_PREFIX}{entry.name}={shlex.quote(entry.value)}" for entry in entries)
    return "\n".join((_DAYU_BLOCK_BEGIN, *export_lines, _DAYU_BLOCK_END, ""))


def _parse_managed_block(content: str) -> _ManagedProfileBlock | None:
    """严格解析 profile 中零个或唯一一个 Dayu marker block。

    :param content: profile 原文。
    :returns: marker 不存在时返回 ``None``，否则返回结构位置与变量名。
    :raises EnvironmentPersistenceError: marker 不配对、多块、嵌入或 export 行非法时抛出。
    """

    lines = content.splitlines(keepends=True)
    normalized_lines = tuple(line.rstrip("\r\n") for line in lines)
    begin_indexes = tuple(index for index, line in enumerate(normalized_lines) if line == _DAYU_BLOCK_BEGIN)
    end_indexes = tuple(index for index, line in enumerate(normalized_lines) if line == _DAYU_BLOCK_END)
    # 结构 marker 只由独立整行产生；export 的等号右侧是合法 value，不参与结构计数。
    for line in normalized_lines:
        if line in {_DAYU_BLOCK_BEGIN, _DAYU_BLOCK_END}:
            continue
        export_head, separator, _export_value = line.partition("=")
        marker_is_in_export_value = (
            bool(separator)
            and export_head.startswith(_EXPORT_PREFIX)
            and export_head != _EXPORT_PREFIX
            and _DAYU_BLOCK_BEGIN not in export_head
            and _DAYU_BLOCK_END not in export_head
        )
        if marker_is_in_export_value:
            continue
        if _DAYU_BLOCK_BEGIN in line or _DAYU_BLOCK_END in line:
            raise EnvironmentPersistenceError("POSIX profile contains an embedded Dayu init marker")
    if not begin_indexes and not end_indexes:
        return None
    if len(begin_indexes) != 1 or len(end_indexes) != 1 or begin_indexes[0] >= end_indexes[0]:
        raise EnvironmentPersistenceError("POSIX profile Dayu init markers are incomplete, overlapping, or repeated")
    names: list[str] = []
    for line in normalized_lines[begin_indexes[0] + 1 : end_indexes[0]]:
        names.append(_parse_export_name(line))
    if len(names) != len(set(names)):
        raise EnvironmentPersistenceError("POSIX profile Dayu init block contains duplicate environment names")
    return _ManagedProfileBlock(
        begin_line_index=begin_indexes[0],
        end_line_index=end_indexes[0],
        environment_names=tuple(names),
    )


def _parse_export_name(line: str) -> str:
    """只解析 marker block export 行的变量名，不解析或返回值。

    :param line: marker block 内单行文本。
    :returns: allowlist 中的环境变量名。
    :raises EnvironmentPersistenceError: 行格式或变量名非法时抛出。
    """

    if not line.startswith(_EXPORT_PREFIX) or "=" not in line:
        raise EnvironmentPersistenceError("POSIX profile Dayu init block contains an invalid export line")
    name, separator, _quoted_value = line[len(_EXPORT_PREFIX) :].partition("=")
    if not separator:
        raise EnvironmentPersistenceError("POSIX profile Dayu init block contains an invalid export line")
    _validate_environment_name(name)
    return name


def _write_profile_atomically(
    *,
    profile_path: Path,
    content: str,
    mode: int,
    expected_names: tuple[str, ...],
) -> None:
    """在 profile 同父目录用私有临时文件、fsync 与 replace 原子发布。

    :param profile_path: 唯一目标 profile。
    :param content: 完整新 profile 文本。
    :param mode: 现有权限位，或新文件固定 ``0600``。
    :param expected_names: 用于中断结果的已确认环境变量名。
    :returns: ``None``。
    :raises EnvironmentPersistenceError: 临时文件、fsync、chmod 或 replace 失败时抛出。
    :raises EnvironmentPersistenceInterrupted: 中断时携带 profile 是否已发布的名称真值。
    """

    file_descriptor = -1
    temporary_path: Path | None = None
    temporary_identity: _ProfileTemporaryIdentity | None = None
    try:
        file_descriptor, temporary_name = tempfile.mkstemp(
            prefix=".dayu-init-env-",
            dir=profile_path.parent,
        )
        temporary_path = Path(temporary_name)
        descriptor_stat = os.fstat(file_descriptor)
        temporary_identity = _ProfileTemporaryIdentity(
            device=descriptor_stat.st_dev,
            inode=descriptor_stat.st_ino,
        )
        os.fchmod(file_descriptor, mode)
        with os.fdopen(file_descriptor, "wb") as handle:
            file_descriptor = -1
            handle.write(content.encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, profile_path)
    except KeyboardInterrupt:
        profile_replaced = _profile_replace_applied(
            profile_path=profile_path,
            temporary_path=temporary_path,
            temporary_identity=temporary_identity,
        )
        if file_descriptor >= 0:
            os.close(file_descriptor)
        retained_paths = _cleanup_owned_profile_temporary(
            temporary_path=temporary_path,
            temporary_identity=temporary_identity,
        )
        raise EnvironmentPersistenceInterrupted(
            _interrupted_result(
                target=str(profile_path),
                written_names=expected_names if profile_replaced else (),
                unwritten_names=() if profile_replaced else expected_names,
                retained_paths=retained_paths,
            )
        ) from None
    except (OSError, UnicodeError):
        profile_replaced = _profile_replace_applied(
            profile_path=profile_path,
            temporary_path=temporary_path,
            temporary_identity=temporary_identity,
        )
        if file_descriptor >= 0:
            os.close(file_descriptor)
        retained_paths = _cleanup_owned_profile_temporary(
            temporary_path=temporary_path,
            temporary_identity=temporary_identity,
        )
        if profile_replaced:
            return
        raise EnvironmentPersistenceError(
            f"unable to atomically write POSIX profile: {profile_path}",
            retained_paths=retained_paths,
        ) from None


def _profile_replace_applied(
    *,
    profile_path: Path,
    temporary_path: Path | None,
    temporary_identity: _ProfileTemporaryIdentity | None,
) -> bool:
    """判断异常返回的 ``os.replace`` 是否已经发布 owner 临时文件。

    :param profile_path: public profile 目标。
    :param temporary_path: 本次创建的 private source path。
    :param temporary_identity: source 创建时 identity。
    :returns: source 已消失且 destination 精确持有该 identity 时返回 ``True``。
    :raises Exception: no-follow identity 读取错误按未证实发布处理，不主动抛出。
    """

    if temporary_path is None or temporary_identity is None:
        return False
    source_status = _classify_profile_path_identity(temporary_path, temporary_identity)
    if source_status is not _ProfilePathIdentityStatus.ABSENT:
        return False
    return (
        _classify_profile_path_identity(profile_path, temporary_identity)
        is _ProfilePathIdentityStatus.OWNED
    )


def _cleanup_owned_profile_temporary(
    *,
    temporary_path: Path | None,
    temporary_identity: _ProfileTemporaryIdentity | None,
) -> tuple[Path, ...]:
    """只删除仍由本次 writer identity 持有的 private temp。

    :param temporary_path: 本次 writer 创建的 private path。
    :param temporary_identity: 创建时 no-follow identity。
    :returns: 仍存在或无法确认已清理的最小路径 tuple；identity 漂移对象不删除。
    :raises Exception: 不主动抛出异常。
    """

    if temporary_path is None:
        return ()
    if temporary_identity is None:
        return (temporary_path,)
    identity_status = _classify_profile_path_identity(temporary_path, temporary_identity)
    if identity_status is _ProfilePathIdentityStatus.ABSENT:
        return ()
    if identity_status is not _ProfilePathIdentityStatus.OWNED:
        return (temporary_path,)
    try:
        os.unlink(temporary_path)
    except (OSError, KeyboardInterrupt):
        return (temporary_path,)
    return ()


def _classify_profile_path_identity(
    path: Path,
    expected: _ProfileTemporaryIdentity,
) -> _ProfilePathIdentityStatus:
    """以 no-follow stat 分类 private profile path identity。

    :param path: 待核验路径。
    :param expected: 本次 writer 创建时 identity。
    :returns: owned、absent、drifted 或 unreadable 的封闭分类。
    :raises Exception: no-follow stat 错误收敛为 ``unreadable``，不主动抛出。
    """

    try:
        current = os.lstat(path)
    except FileNotFoundError:
        return _ProfilePathIdentityStatus.ABSENT
    except (OSError, KeyboardInterrupt):
        return _ProfilePathIdentityStatus.UNREADABLE
    matches = (
        stat.S_ISREG(current.st_mode)
        and current.st_dev == expected.device
        and current.st_ino == expected.inode
    )
    if matches:
        return _ProfilePathIdentityStatus.OWNED
    return _ProfilePathIdentityStatus.DRIFTED


def _interrupted_result(
    *,
    target: str,
    written_names: tuple[str, ...],
    unwritten_names: tuple[str, ...],
    retained_paths: tuple[Path, ...],
) -> EnvironmentPersistenceResult:
    """构造不携带 value/captured output 的中断结果。

    :param target: POSIX profile path 或 Windows ``setx``。
    :param written_names: 已确认写入 OS store 的名称。
    :param unwritten_names: 未确认写入 OS store 的名称。
    :param retained_paths: 仍存在或无法确认已清理的私有临时路径。
    :returns: ``status=interrupted`` 的最小脱敏结果。
    :raises Exception: 不主动抛出异常。
    """

    return EnvironmentPersistenceResult(
        status=EnvironmentPersistenceStatus.INTERRUPTED,
        target=target,
        written_names=written_names,
        unwritten_names=unwritten_names,
        retained_paths=retained_paths,
    )


def _verify_written_profile(*, profile_path: Path, expected_names: tuple[str, ...], expected_mode: int) -> None:
    """从磁盘重读 profile，仅校验 marker/name 结构与权限。

    :param profile_path: 已原子发布的 profile。
    :param expected_names: 本批次按顺序写入的变量名。
    :param expected_mode: 应保留或新建的权限位。
    :returns: ``None``。
    :raises EnvironmentPersistenceError: 重读、结构或权限不匹配时抛出。
    """

    state = _read_profile_state(profile_path)
    managed = _parse_managed_block(state.content)
    if managed is None or managed.environment_names != expected_names:
        raise EnvironmentPersistenceError(f"POSIX profile post-write structure verification failed: {profile_path}")
    if state.mode != expected_mode:
        raise EnvironmentPersistenceError(f"POSIX profile post-write mode verification failed: {profile_path}")


def _validate_entry_batch(entries: tuple[EnvironmentPersistenceEntry, ...]) -> None:
    """校验 persistence plan 批次非空且名称唯一。

    :param entries: 待校验批次。
    :returns: ``None``。
    :raises EnvironmentPersistenceError: 批次为空或存在重复名称时抛出。
    """

    if not entries:
        raise EnvironmentPersistenceError("environment persistence plan must contain at least one entry")
    names = tuple(entry.name for entry in entries)
    if len(names) != len(set(names)):
        raise EnvironmentPersistenceError("environment persistence plan contains duplicate names")


def _validate_environment_name(name: str) -> None:
    """要求变量名来自 catalog/可选集成固定 allowlist。

    :param name: 待校验环境变量名。
    :returns: ``None``。
    :raises EnvironmentPersistenceError: 名称不在 allowlist 时抛出。
    """

    if name not in ALLOWED_ENVIRONMENT_NAMES:
        raise EnvironmentPersistenceError(f"unsupported environment variable name: {name}")
