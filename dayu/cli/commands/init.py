"""``dayu-cli init`` 工作区初始化命令实现。

本模块只负责 filesystem bootstrap：创建 workspace root、复制当前
``dayu/config`` 下的配置文件与 prompt assets，并按硬编码白名单执行 reset。
它不打开 Host，不创建 Fins job，不执行旧 workspace migration。
"""

from __future__ import annotations

import os
import shutil
import sys
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from dayu.cli.arg_parsing import ParsedCliArgs
from dayu.cli.exit_codes import (
    EXIT_FAILURE,
    EXIT_KEYBOARD_INTERRUPT,
    EXIT_SUCCESS,
    EXIT_USAGE_ERROR,
)
from dayu.runtime.config_loader import config_file_names, legacy_config_file_names

_BASE_OPTION: Final[str] = "--base"
_PACKAGE_CONFIG_ROOT: Final[Path] = Path(__file__).resolve().parents[2] / "config"
_WORKSPACE_CONFIG_DIR_NAME: Final[str] = "config"
_PROMPTS_DIR_NAME: Final[str] = "prompts"
_DAYU_DIR_NAME: Final[str] = ".dayu"
_HOST_DIR_NAME: Final[str] = "host"
_ARTIFACTS_DIR_NAME: Final[str] = "artifacts"
_WEB_TOOLS_STORAGE_STATES_DIR_NAME: Final[str] = "web_tools_storage_states"
_TEMP_FILE_PREFIX: Final[str] = ".dayu-init-"
_RESET_CONTAINMENT_ERROR_TEMPLATE: Final[str] = (
    "dayu-cli init: reset whitelist path escapes workspace: {path}"
)
_RESET_SYMLINK_ERROR_TEMPLATE: Final[str] = (
    "dayu-cli init: reset whitelist path must not be a symlink: {path}"
)
_EXISTING_FILE_ERROR_TEMPLATE: Final[str] = (
    "dayu-cli init: target config file exists; pass --overwrite to replace it: {path}"
)
_COPY_FAILURE_TEMPLATE: Final[str] = "dayu-cli init: failed to copy config asset: {error}"
_WORKSPACE_PATH_ERROR_TEMPLATE: Final[str] = (
    "dayu-cli init: workspace path is invalid: {error}"
)
_SUCCESS_TEMPLATE: Final[str] = (
    "dayu-cli init: initialized workspace config at {config_dir}"
)
_RESET_TEMPLATE: Final[str] = "dayu-cli init: reset {count} workspace path(s)"


class CliInitUsageError(ValueError):
    """init 命令用法错误。"""


class CliInitOperationError(RuntimeError):
    """init 命令执行错误。"""


@dataclass(frozen=True, slots=True)
class _CopyAsset:
    """待复制配置资产。

    :param source: 包内源文件路径。
    :param destination: workspace 内目标文件路径。
    """

    source: Path
    destination: Path


def run_init_command(args: ParsedCliArgs) -> int:
    """执行 ``dayu-cli init`` 命令。

    :param args: argparse 已解析的 init 命令参数。
    :returns: CLI 退出码。
    :raises OSError: stdout / stderr 写入失败时由底层 ``print`` 透传。
    """

    try:
        workspace_root = _resolve_workspace_root(args.workspace_root)
        _ensure_workspace_root(workspace_root)
        if args.reset:
            removed_count = _reset_workspace_paths(workspace_root=workspace_root)
            print(_RESET_TEMPLATE.format(count=removed_count))
        config_dir = workspace_root / _WORKSPACE_CONFIG_DIR_NAME
        _copy_current_config_assets(
            workspace_config_dir=config_dir,
            package_config_root=_PACKAGE_CONFIG_ROOT,
            overwrite=args.overwrite,
        )
        print(_SUCCESS_TEMPLATE.format(config_dir=config_dir))
        return EXIT_SUCCESS
    except CliInitUsageError as exc:
        print(_WORKSPACE_PATH_ERROR_TEMPLATE.format(error=exc), file=sys.stderr)
        return EXIT_USAGE_ERROR
    except KeyboardInterrupt:
        return EXIT_KEYBOARD_INTERRUPT
    except CliInitOperationError as exc:
        print(f"dayu-cli init: {exc}", file=sys.stderr)
        return EXIT_FAILURE
    except OSError as exc:
        print(_COPY_FAILURE_TEMPLATE.format(error=exc), file=sys.stderr)
        return EXIT_FAILURE


def _resolve_workspace_root(raw_value: str) -> Path:
    """解析并校验 workspace root。

    :param raw_value: ``--base`` / ``--workspace`` 原始值。
    :returns: 解析后的绝对 workspace root。
    :raises CliInitUsageError: 路径为空或无法解析时抛出。
    """

    stripped = raw_value.strip()
    if stripped == "":
        raise CliInitUsageError(f"{_BASE_OPTION} must not be empty")
    return Path(stripped).expanduser().resolve(strict=False)


def _ensure_workspace_root(workspace_root: Path) -> None:
    """创建并校验 workspace root。

    :param workspace_root: 已解析的 workspace root。
    :returns: ``None``。
    :raises CliInitUsageError: 路径无法创建或不是目录时抛出。
    """

    try:
        workspace_root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise CliInitUsageError(str(exc)) from exc
    if not workspace_root.is_dir():
        raise CliInitUsageError(f"{workspace_root} is not a directory")


def _copy_current_config_assets(
    *,
    workspace_config_dir: Path,
    package_config_root: Path,
    overwrite: bool,
) -> None:
    """复制当前 schema 配置文件与 prompt assets 到 workspace。

    :param workspace_config_dir: workspace/config 目标目录。
    :param package_config_root: 包内 dayu/config 根目录。
    :param overwrite: 是否允许覆盖已有目标文件。
    :returns: ``None``。
    :raises CliInitOperationError: 目标文件冲突或源资产缺失时抛出。
    :raises OSError: 文件复制失败时抛出。
    """

    assets = _collect_current_config_assets(
        workspace_config_dir=workspace_config_dir,
        package_config_root=package_config_root,
    )
    _raise_for_existing_assets(assets=assets, overwrite=overwrite)
    workspace_config_dir.mkdir(parents=True, exist_ok=True)
    for asset in assets:
        _copy_file_atomic(source=asset.source, destination=asset.destination)


def _collect_current_config_assets(
    *,
    workspace_config_dir: Path,
    package_config_root: Path,
) -> tuple[_CopyAsset, ...]:
    """收集当前 schema 需要复制的配置资产。

    :param workspace_config_dir: workspace/config 目标目录。
    :param package_config_root: 包内 dayu/config 根目录。
    :returns: 待复制文件列表。
    :raises CliInitOperationError: 必需源文件或 prompts 目录缺失时抛出。
    """

    assets: list[_CopyAsset] = []
    for file_name in config_file_names():
        source = package_config_root / file_name
        if not source.is_file():
            raise CliInitOperationError(f"required package config missing: {source}")
        assets.append(
            _CopyAsset(
                source=source,
                destination=workspace_config_dir / file_name,
            )
        )
    prompts_root = package_config_root / _PROMPTS_DIR_NAME
    if not prompts_root.is_dir():
        raise CliInitOperationError(f"required package prompts missing: {prompts_root}")
    for source in sorted(prompts_root.rglob("*")):
        if source.is_dir():
            continue
        relative_path = source.relative_to(package_config_root)
        assets.append(
            _CopyAsset(
                source=source,
                destination=workspace_config_dir / relative_path,
            )
        )
    _raise_if_legacy_asset_selected(assets)
    return tuple(assets)


def _raise_if_legacy_asset_selected(assets: Sequence[_CopyAsset]) -> None:
    """防止旧 schema 文件进入 init 复制集合。

    :param assets: 待复制文件列表。
    :returns: ``None``。
    :raises CliInitOperationError: 复制集合包含旧配置文件时抛出。
    """

    legacy_names = legacy_config_file_names()
    for asset in assets:
        if asset.destination.name in legacy_names:
            raise CliInitOperationError(
                f"legacy config file must not be generated: {asset.destination.name}"
            )


def _raise_for_existing_assets(
    *, assets: tuple[_CopyAsset, ...], overwrite: bool
) -> None:
    """在复制前检查目标文件冲突。

    :param assets: 待复制文件列表。
    :param overwrite: 是否允许覆盖已有目标文件。
    :returns: ``None``。
    :raises CliInitOperationError: 目标存在且不允许覆盖，或目标是目录时抛出。
    """

    for asset in assets:
        if asset.destination.is_dir():
            raise CliInitOperationError(
                f"target path is a directory, expected file: {asset.destination}"
            )
        if asset.destination.exists() and not overwrite:
            raise CliInitOperationError(
                _EXISTING_FILE_ERROR_TEMPLATE.format(path=asset.destination)
            )


def _copy_file_atomic(*, source: Path, destination: Path) -> None:
    """用临时文件和原子替换复制单个文件。

    :param source: 源文件路径。
    :param destination: 目标文件路径。
    :returns: ``None``。
    :raises OSError: 创建目录、复制或替换失败时抛出。
    """

    destination.parent.mkdir(parents=True, exist_ok=True)
    temp_path = destination.with_name(
        f"{_TEMP_FILE_PREFIX}{uuid.uuid4().hex}-{destination.name}"
    )
    try:
        shutil.copy2(source, temp_path)
        os.replace(temp_path, destination)
    except BaseException:
        if temp_path.exists():
            temp_path.unlink()
        raise


def _reset_workspace_paths(*, workspace_root: Path) -> int:
    """按硬编码白名单删除 workspace 内可重建路径。

    :param workspace_root: 已解析的 workspace root。
    :returns: 实际删除的路径数量。
    :raises CliInitUsageError: 白名单路径 symlink 或 resolve 后逃逸时抛出。
    :raises OSError: 删除失败时抛出。
    """

    reset_paths = _reset_whitelist_paths(workspace_root)
    _validate_reset_whitelist_paths(
        workspace_root=workspace_root,
        reset_paths=reset_paths,
    )
    removed_count = 0
    for path in reset_paths:
        if not path.exists():
            continue
        _delete_reset_path(path)
        removed_count += 1
    return removed_count


def _reset_whitelist_paths(workspace_root: Path) -> tuple[Path, ...]:
    """返回 reset 允许删除的硬编码路径。

    :param workspace_root: workspace root。
    :returns: reset 白名单路径元组。
    :raises Exception: 不主动抛出异常。
    """

    dayu_root = workspace_root / _DAYU_DIR_NAME
    return (
        workspace_root / _WORKSPACE_CONFIG_DIR_NAME,
        dayu_root / _HOST_DIR_NAME,
        dayu_root / _ARTIFACTS_DIR_NAME,
        dayu_root / _WEB_TOOLS_STORAGE_STATES_DIR_NAME,
    )


def _validate_reset_whitelist_paths(
    *, workspace_root: Path, reset_paths: tuple[Path, ...]
) -> None:
    """预检 reset 白名单路径的 symlink 与 containment。

    :param workspace_root: 已解析的 workspace root。
    :param reset_paths: reset 白名单路径。
    :returns: ``None``。
    :raises CliInitUsageError: 任何白名单路径不安全时抛出。
    """

    resolved_workspace = workspace_root.resolve(strict=False)
    for path in reset_paths:
        if path.is_symlink():
            raise CliInitUsageError(
                _RESET_SYMLINK_ERROR_TEMPLATE.format(path=path)
            )
        resolved_path = path.resolve(strict=False)
        try:
            resolved_path.relative_to(resolved_workspace)
        except ValueError as exc:
            raise CliInitUsageError(
                _RESET_CONTAINMENT_ERROR_TEMPLATE.format(path=path)
            ) from exc


def _delete_reset_path(path: Path) -> None:
    """删除已通过预检的 reset 白名单路径。

    :param path: 待删除路径。
    :returns: ``None``。
    :raises OSError: 删除失败时抛出。
    """

    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()


__all__: tuple[str, ...] = ("run_init_command",)
