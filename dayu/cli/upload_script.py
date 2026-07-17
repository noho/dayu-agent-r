"""批量上传脚本的唯一平台 renderer 与安全 publisher。

本模块只消费已经定型的 argv，不识别文件业务类型、财期或 material。POSIX
与 Windows renderer 分别拥有平台 quoting；publisher 拥有 output containment、
symlink rejection 与同目录原子替换。
"""

from __future__ import annotations

import os
import shlex
import tempfile
from pathlib import Path
from typing import Final, Literal

UploadScriptPlatform = Literal["posix", "windows"]

_POSIX_HEADER: Final[tuple[str, ...]] = ("#!/usr/bin/env sh", "set -eu")
_WINDOWS_HEADER: Final[tuple[str, ...]] = (
    "@echo off",
    "chcp 65001 >nul",
    "setlocal DisableDelayedExpansion",
)
_POSIX_MODE: Final[int] = 0o755
_UTF8_ENCODING: Final[str] = "utf-8"
_WINDOWS_COMMENT_METACHARACTERS: Final[frozenset[str]] = frozenset(
    {'^', '&', '|', '<', '>', '(', ')', '"'}
)


class UploadScriptPublishError(RuntimeError):
    """脚本 output 路径或发布过程违反安全 contract。"""


def current_upload_script_platform() -> UploadScriptPlatform:
    """返回当前进程应生成的脚本平台。

    :returns: Windows 返回 ``"windows"``，其它系统返回 ``"posix"``。
    :raises Exception: 不主动抛出异常。
    """

    return "windows" if os.name == "nt" else "posix"


def default_upload_script_filename(
    canonical_ticker: str,
    *,
    platform: UploadScriptPlatform,
) -> str:
    """生成当前平台默认脚本文件名。

    :param canonical_ticker: 已规范化的 canonical ticker。
    :param platform: 目标脚本平台。
    :returns: ``upload_filings_<TICKER>.sh`` 或 ``.cmd``。
    :raises UploadScriptPublishError: ticker 不是安全单路径组件时抛出。
    """

    ticker = canonical_ticker.strip()
    if (
        ticker in ("", ".", "..")
        or Path(ticker).name != ticker
        or "/" in ticker
        or "\\" in ticker
    ):
        raise UploadScriptPublishError("canonical ticker cannot form a safe output filename")
    suffix = ".cmd" if platform == "windows" else ".sh"
    return f"upload_filings_{ticker}{suffix}"


def render_upload_script(
    commands: tuple[tuple[str, ...], ...],
    *,
    regeneration_argv: tuple[str, ...],
    platform: UploadScriptPlatform,
) -> str:
    """把 typed argv 渲染为平台可执行脚本文本。

    :param commands: 每个元素是一条已定型命令 argv。
    :param regeneration_argv: 不含 secret 的脚本再生成 argv。
    :param platform: POSIX 或 Windows。
    :returns: UTF-8 脚本文本；POSIX 使用 LF，Windows 使用 CRLF。
    :raises ValueError: commands、argv 或 platform 非法时抛出。
    """

    if not commands:
        raise ValueError("upload script requires at least one command")
    if not regeneration_argv or any(argument == "" for argument in regeneration_argv[:1]):
        raise ValueError("regeneration argv requires a non-empty executable")
    if any(not command or command[0] == "" for command in commands):
        raise ValueError("each upload command requires a non-empty executable")
    if platform == "posix":
        return _render_posix_script(commands, regeneration_argv=regeneration_argv)
    if platform == "windows":
        return _render_windows_script(commands, regeneration_argv=regeneration_argv)
    raise ValueError(f"unsupported upload script platform: {platform}")


def publish_upload_script(
    *,
    workspace_root: Path,
    output: Path | None,
    canonical_ticker: str,
    platform: UploadScriptPlatform,
    content: str,
) -> Path:
    """在 workspace 内安全、原子地发布脚本。

    :param workspace_root: CLI ``--base`` workspace root。
    :param output: 可选显式文件或既有目录。
    :param canonical_ticker: 默认文件名使用的 canonical ticker。
    :param platform: 目标脚本平台。
    :param content: renderer 已生成的完整文本。
    :returns: 发布后脚本的 resolved 绝对路径。
    :raises UploadScriptPublishError: containment、symlink 或目标类型非法时抛出。
    :raises OSError: 创建、写入、fsync、chmod 或 replace 失败时透传。
    :raises KeyboardInterrupt: 发布被中断时透传；临时文件会清理。
    """

    target = _resolve_publish_target(
        workspace_root=workspace_root,
        output=output,
        canonical_ticker=canonical_ticker,
        platform=platform,
    )
    temp_fd, temp_name = tempfile.mkstemp(
        prefix=f".{target.name}.",
        suffix=".tmp",
        dir=target.parent,
    )
    temp_path = Path(temp_name)
    descriptor_open = True
    try:
        with os.fdopen(
            temp_fd,
            mode="w",
            encoding=_UTF8_ENCODING,
            newline="",
        ) as stream:
            descriptor_open = False
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        if platform == "posix":
            os.chmod(temp_path, _POSIX_MODE)
        os.replace(temp_path, target)
    except BaseException:
        if descriptor_open:
            os.close(temp_fd)
        temp_path.unlink(missing_ok=True)
        raise
    return target.resolve(strict=True)


def _render_posix_script(
    commands: tuple[tuple[str, ...], ...],
    *,
    regeneration_argv: tuple[str, ...],
) -> str:
    """渲染 POSIX ``sh`` 脚本。

    :param commands: 已定型命令 argv。
    :param regeneration_argv: 再生成 argv。
    :returns: UTF-8/LF 脚本文本。
    :raises Exception: 不主动抛出异常。
    """

    lines = [*_POSIX_HEADER, f"# Regenerate: {shlex.join(regeneration_argv)}"]
    lines.extend(f'{shlex.join(command)} "$@"' for command in commands)
    return "\n".join(lines) + "\n"


def _render_windows_script(
    commands: tuple[tuple[str, ...], ...],
    *,
    regeneration_argv: tuple[str, ...],
) -> str:
    """渲染 Windows ``cmd.exe`` batch 脚本。

    :param commands: 已定型命令 argv。
    :param regeneration_argv: 再生成 argv。
    :returns: UTF-8/CRLF 脚本文本。
    :raises Exception: 不主动抛出异常。
    """

    regeneration_text = " ".join(regeneration_argv)
    lines = [
        *_WINDOWS_HEADER,
        f"REM Regenerate: {_escape_windows_comment(regeneration_text)}",
    ]
    for command in commands:
        fixed = " ".join(_quote_windows_batch_argument(argument) for argument in command)
        lines.append(f"{fixed} %*")
        lines.append("if errorlevel 1 exit /b %errorlevel%")
    lines.append("exit /b 0")
    return "\r\n".join(lines) + "\r\n"


def _quote_windows_batch_argument(argument: str) -> str:
    """同时满足 batch percent 与 Windows CRT 的单 argv quoting。

    :param argument: 原始 argv 元素。
    :returns: 可写入 ``.cmd`` executable body 的双引号参数。
    :raises Exception: 不主动抛出异常。
    """

    escaped_percent = argument.replace("%", "%%")
    rendered: list[str] = ['"']
    backslash_count = 0
    for character in escaped_percent:
        if character == "\\":
            backslash_count += 1
            continue
        if character == '"':
            rendered.append("\\" * (backslash_count * 2 + 1))
            rendered.append('"')
            backslash_count = 0
            continue
        rendered.append("\\" * backslash_count)
        rendered.append(character)
        backslash_count = 0
    rendered.append("\\" * (backslash_count * 2))
    rendered.append('"')
    return "".join(rendered)


def _escape_windows_comment(value: str) -> str:
    """让 regeneration 文本保持为单条无副作用 ``REM`` 注释。

    :param value: 不含 secret 的再生成命令文本。
    :returns: 已转义 batch percent 与 cmd metacharacter 的注释文本。
    :raises Exception: 不主动抛出异常。
    """

    rendered: list[str] = []
    for character in value:
        if character == "%":
            rendered.append("%%")
        elif character in _WINDOWS_COMMENT_METACHARACTERS:
            rendered.append(f"^{character}")
        else:
            rendered.append(character)
    return "".join(rendered)


def _resolve_publish_target(
    *,
    workspace_root: Path,
    output: Path | None,
    canonical_ticker: str,
    platform: UploadScriptPlatform,
) -> Path:
    """解析并验证最终 publish target。

    :param workspace_root: CLI workspace root。
    :param output: 显式文件或既有目录。
    :param canonical_ticker: 默认文件名 ticker。
    :param platform: 目标平台。
    :returns: lexical 绝对 target。
    :raises UploadScriptPublishError: root/target/parent 不满足 contract 时抛出。
    :raises OSError: 创建 workspace root 或读取路径失败时透传。
    """

    lexical_root = _lexical_absolute(workspace_root)
    if lexical_root.is_symlink():
        raise UploadScriptPublishError(
            f"workspace root must not be a symlink: {lexical_root}"
        )
    if lexical_root.exists() and not lexical_root.is_dir():
        raise UploadScriptPublishError(
            f"workspace root is not a directory: {lexical_root}"
        )
    lexical_root.mkdir(parents=True, exist_ok=True)
    resolved_root = lexical_root.resolve(strict=True)
    default_name = default_upload_script_filename(
        canonical_ticker,
        platform=platform,
    )
    if output is None:
        target = lexical_root / default_name
    else:
        lexical_output = _lexical_absolute(output)
        target = (
            lexical_output / default_name
            if lexical_output.exists() and lexical_output.is_dir()
            else lexical_output
        )
    if not _is_within(target, lexical_root):
        raise UploadScriptPublishError(f"output target escapes workspace root: {target}")
    if _has_internal_symlink(lexical_root, target):
        raise UploadScriptPublishError(
            f"output path contains an internal symlink: {target}"
        )
    if not target.parent.exists() or not target.parent.is_dir():
        raise UploadScriptPublishError(
            f"output parent is not an existing directory: {target.parent}"
        )
    resolved_parent = target.parent.resolve(strict=True)
    if not _is_within(resolved_parent, resolved_root):
        raise UploadScriptPublishError(
            f"resolved output parent escapes workspace root: {target.parent}"
        )
    if target.exists() and not target.is_file():
        raise UploadScriptPublishError(f"output target is not a regular file: {target}")
    resolved_target = target.resolve(strict=False)
    if not _is_within(resolved_target, resolved_root):
        raise UploadScriptPublishError(
            f"resolved output target escapes workspace root: {target}"
        )
    return target


def _lexical_absolute(path: Path) -> Path:
    """形成不解析 symlink 的 lexical 绝对路径。

    :param path: 输入路径。
    :returns: 已展开用户目录并规范 ``.``/``..`` 的绝对路径。
    :raises OSError: 获取绝对路径失败时透传。
    """

    return Path(os.path.abspath(path.expanduser()))


def _has_internal_symlink(root: Path, target: Path) -> bool:
    """检查 root 内部到 target 的任一现存组件是否为 symlink。

    :param root: lexical workspace root。
    :param target: lexical output target。
    :returns: 内部组件或现存 target 为 symlink 时返回 ``True``。
    :raises ValueError: target 不在 lexical root 时抛出。
    """

    relative = target.relative_to(root)
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            return True
    return False


def _is_within(path: Path, root: Path) -> bool:
    """判断 path 是否等于或位于 root 内。

    :param path: 待判断路径。
    :param root: containment root。
    :returns: containment 成立返回 ``True``。
    :raises Exception: 不主动抛出异常。
    """

    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


__all__: tuple[str, ...] = (
    "UploadScriptPlatform",
    "UploadScriptPublishError",
    "current_upload_script_platform",
    "default_upload_script_filename",
    "publish_upload_script",
    "render_upload_script",
)
