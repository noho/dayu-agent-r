"""``dayu-cli init`` 工作区初始化命令实现。

本模块只负责 filesystem bootstrap：创建 workspace root、复制当前
``dayu/config`` 下的配置文件与 prompt assets，并按硬编码白名单执行 reset。
它不打开 Host，不创建 Fins job，不执行旧 workspace migration。
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
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
from dayu.runtime.config_loader import config_file_names
from dayu.runtime.workspace_paths import WorkspacePaths, workspace_paths

_BASE_OPTION: Final[str] = "--base"
_PACKAGE_CONFIG_ROOT: Final[Path] = Path(__file__).resolve().parents[2] / "config"
_PROMPTS_DIR_NAME: Final[str] = "prompts"
_LEGACY_CONFIG_FILE_NAMES: Final[frozenset[str]] = frozenset({"llm_models.json", "run.json"})
_STAGING_DIR_PREFIX: Final[str] = ".dayu-init-stage-"
_BACKUP_DIR_PREFIX: Final[str] = ".dayu-init-backup-"
_WRITE_DESTINATION_ROLE: Final[str] = "write destination"
_RESET_DESTINATION_ROLE: Final[str] = "reset whitelist"
_CONTAINMENT_ERROR_TEMPLATE: Final[str] = "dayu-cli init: {role} path escapes workspace: {path}"
_SYMLINK_ERROR_TEMPLATE: Final[str] = "dayu-cli init: {role} path must not contain a symlink: {path}"
_EXISTING_FILE_ERROR_TEMPLATE: Final[str] = (
    "dayu-cli init: target config file exists; pass --overwrite to replace it: {path}"
)
_COPY_FAILURE_TEMPLATE: Final[str] = "dayu-cli init: failed to copy config asset: {error}"
_WORKSPACE_PATH_ERROR_TEMPLATE: Final[str] = "dayu-cli init: workspace path is invalid: {error}"
_SUCCESS_TEMPLATE: Final[str] = "dayu-cli init: initialized workspace config at {config_dir}"
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
        paths = workspace_paths(workspace_root)
        if args.reset:
            removed_count = _reset_workspace_paths(paths=paths)
            print(_RESET_TEMPLATE.format(count=removed_count))
        config_dir = paths.config_dir
        _copy_current_config_assets(
            workspace_root=workspace_root,
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
    workspace_root: Path,
    workspace_config_dir: Path,
    package_config_root: Path,
    overwrite: bool,
) -> None:
    """复制当前 schema 配置文件与 prompt assets 到 workspace。

    :param workspace_root: 已解析的 workspace root。
    :param workspace_config_dir: workspace root 下的 config 目标目录。
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
    _validate_config_write_destination(
        workspace_root=workspace_root,
        workspace_config_dir=workspace_config_dir,
    )
    _raise_for_existing_assets(assets=assets, overwrite=overwrite)
    staging_dir = Path(tempfile.mkdtemp(prefix=_STAGING_DIR_PREFIX, dir=workspace_root))
    try:
        if workspace_config_dir.exists():
            shutil.copytree(
                workspace_config_dir,
                staging_dir,
                dirs_exist_ok=True,
            )
        for asset in assets:
            relative_path = asset.destination.relative_to(workspace_config_dir)
            _copy_asset_to_staging(
                source=asset.source,
                destination=staging_dir / relative_path,
            )
        _install_staged_config_tree(
            workspace_root=workspace_root,
            workspace_config_dir=workspace_config_dir,
            staging_dir=staging_dir,
        )
    finally:
        _delete_path_without_following_symlink(staging_dir)


def _collect_current_config_assets(
    *,
    workspace_config_dir: Path,
    package_config_root: Path,
) -> tuple[_CopyAsset, ...]:
    """收集当前 schema 需要复制的配置资产。

    :param workspace_config_dir: workspace root 下的 config 目标目录。
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
    _raise_if_legacy_top_level_config_asset_selected(
        assets=assets,
        workspace_config_dir=workspace_config_dir,
    )
    return tuple(assets)


def _raise_if_legacy_top_level_config_asset_selected(
    *, assets: Sequence[_CopyAsset], workspace_config_dir: Path
) -> None:
    """防止旧 schema 顶层配置文件进入 init 复制集合。

    :param assets: 待复制文件列表。
    :param workspace_config_dir: workspace root 下的 config 目标目录。
    :returns: ``None``。
    :raises CliInitOperationError: 复制集合包含旧顶层配置文件时抛出。
    """

    for asset in assets:
        if asset.destination.parent == workspace_config_dir and asset.destination.name in _LEGACY_CONFIG_FILE_NAMES:
            raise CliInitOperationError(f"legacy config file must not be generated: {asset.destination.name}")


def _raise_for_existing_assets(*, assets: tuple[_CopyAsset, ...], overwrite: bool) -> None:
    """在复制前检查目标文件冲突。

    :param assets: 待复制文件列表。
    :param overwrite: 是否允许覆盖已有目标文件。
    :returns: ``None``。
    :raises CliInitOperationError: 目标存在且不允许覆盖，或目标是目录时抛出。
    """

    for asset in assets:
        if asset.destination.is_dir():
            raise CliInitOperationError(f"target path is a directory, expected file: {asset.destination}")
        if asset.destination.exists() and not overwrite:
            raise CliInitOperationError(_EXISTING_FILE_ERROR_TEMPLATE.format(path=asset.destination))


def _validate_config_write_destination(*, workspace_root: Path, workspace_config_dir: Path) -> None:
    """校验 init config 写入树没有 symlink 或 containment 逃逸。

    :param workspace_root: 已解析的 workspace root。
    :param workspace_config_dir: init config 目标目录。
    :returns: ``None``。
    :raises CliInitUsageError: 目标逃逸、包含 symlink 或不是目录时抛出。
    :raises OSError: 遍历已有目标树失败时抛出。
    """

    _validate_workspace_path(
        workspace_root=workspace_root,
        path=workspace_config_dir,
        role=_WRITE_DESTINATION_ROLE,
    )
    if workspace_config_dir.exists() and not workspace_config_dir.is_dir():
        raise CliInitUsageError(f"{workspace_config_dir} is not a config directory")
    if not workspace_config_dir.exists():
        return
    for current_root, directory_names, file_names in os.walk(
        workspace_config_dir,
        followlinks=False,
    ):
        current_path = Path(current_root)
        for entry_name in (*directory_names, *file_names):
            candidate = current_path / entry_name
            if candidate.is_symlink():
                raise CliInitUsageError(
                    _SYMLINK_ERROR_TEMPLATE.format(
                        role=_WRITE_DESTINATION_ROLE,
                        path=candidate,
                    )
                )


def _copy_asset_to_staging(*, source: Path, destination: Path) -> None:
    """把单个包内资产复制到私有 staging tree。

    :param source: 包内源文件。
    :param destination: 私有 staging tree 内目标文件。
    :returns: ``None``。
    :raises OSError: 目录创建或复制失败时抛出。
    """

    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def _install_staged_config_tree(
    *,
    workspace_root: Path,
    workspace_config_dir: Path,
    staging_dir: Path,
) -> None:
    """把完整 staging tree 安装为 workspace config。

    已有 config 会先移动到同一 workspace 下的私有 backup。安装失败时恢复
    backup，避免逐文件覆盖留下半更新配置；顶层 rename 不会跟随 config
    symlink 写入其目标。

    :param workspace_root: 已解析的 workspace root。
    :param workspace_config_dir: 最终 config 目录。
    :param staging_dir: 已完成复制的私有 staging 目录。
    :returns: ``None``。
    :raises CliInitUsageError: 安装前目标重新变成不安全路径时抛出。
    :raises OSError: rename、回滚或 backup 清理失败时抛出。
    :raises KeyboardInterrupt: 安装阶段被用户中断时，完成回滚后重新抛出。
    """

    _validate_config_write_destination(
        workspace_root=workspace_root,
        workspace_config_dir=workspace_config_dir,
    )
    backup_dir = workspace_root / (f"{_BACKUP_DIR_PREFIX}{uuid.uuid4().hex}-{workspace_config_dir.name}")
    existing_moved = False
    try:
        if workspace_config_dir.exists():
            os.replace(workspace_config_dir, backup_dir)
            existing_moved = True
        os.replace(staging_dir, workspace_config_dir)
    except (OSError, KeyboardInterrupt):
        if existing_moved and not workspace_config_dir.exists():
            os.replace(backup_dir, workspace_config_dir)
        raise
    if existing_moved:
        _delete_path_without_following_symlink(backup_dir)


def _validate_workspace_path(*, workspace_root: Path, path: Path, role: str) -> None:
    """校验 workspace 内路径的 lexical/resolved containment 与祖先 symlink。

    :param workspace_root: 已解析的 workspace root。
    :param path: 待校验路径。
    :param role: 错误信息中的路径职责名称。
    :returns: ``None``。
    :raises CliInitUsageError: 路径逃逸或任一现存祖先为 symlink 时抛出。
    """

    resolved_workspace = workspace_root.resolve(strict=True)
    try:
        relative_path = path.relative_to(workspace_root)
    except ValueError as exc:
        raise CliInitUsageError(_CONTAINMENT_ERROR_TEMPLATE.format(role=role, path=path)) from exc
    current_path = workspace_root
    for component in relative_path.parts:
        current_path /= component
        if current_path.is_symlink():
            raise CliInitUsageError(_SYMLINK_ERROR_TEMPLATE.format(role=role, path=current_path))
    resolved_path = path.resolve(strict=False)
    try:
        resolved_path.relative_to(resolved_workspace)
    except ValueError as exc:
        raise CliInitUsageError(_CONTAINMENT_ERROR_TEMPLATE.format(role=role, path=path)) from exc


def _delete_path_without_following_symlink(path: Path) -> None:
    """删除私有 staging/backup 路径且绝不跟随最终 symlink。

    :param path: 待删除的私有路径。
    :returns: ``None``。
    :raises OSError: unlink 或递归删除失败时抛出。
    """

    if path.is_symlink():
        path.unlink()
        return
    if not path.exists():
        return
    if path.is_dir():
        shutil.rmtree(path)
        return
    path.unlink()


def _reset_workspace_paths(*, paths: WorkspacePaths) -> int:
    """按硬编码白名单删除 workspace 内可重建路径。

    :param paths: workspace 路径公共契约。
    :returns: 实际删除的路径数量。
    :raises CliInitUsageError: 白名单路径 symlink 或 resolve 后逃逸时抛出。
    :raises OSError: 删除失败时抛出。
    """

    reset_paths = _reset_whitelist_paths(paths)
    _validate_reset_whitelist_paths(
        workspace_root=paths.workspace_root,
        reset_paths=reset_paths,
    )
    removed_count = 0
    for path in reset_paths:
        if not path.exists() and not path.is_symlink():
            continue
        _delete_reset_path(workspace_root=paths.workspace_root, path=path)
        removed_count += 1
    return removed_count


def _reset_whitelist_paths(paths: WorkspacePaths) -> tuple[Path, ...]:
    """返回 reset 允许删除的硬编码路径。

    :param paths: workspace 路径公共契约。
    :returns: reset 白名单路径元组。
    :raises Exception: 不主动抛出异常。
    """

    return (
        paths.config_dir,
        paths.host_dir,
        paths.artifact_root,
        paths.web_tools_storage_state_dir,
    )


def _validate_reset_whitelist_paths(*, workspace_root: Path, reset_paths: tuple[Path, ...]) -> None:
    """预检 reset 白名单路径的 symlink 与 containment。

    :param workspace_root: 已解析的 workspace root。
    :param reset_paths: reset 白名单路径。
    :returns: ``None``。
    :raises CliInitUsageError: 任何白名单路径不安全时抛出。
    """

    for path in reset_paths:
        _validate_workspace_path(
            workspace_root=workspace_root,
            path=path,
            role=_RESET_DESTINATION_ROLE,
        )


def _delete_reset_path(*, workspace_root: Path, path: Path) -> None:
    """删除已通过预检的 reset 白名单路径。

    :param workspace_root: 已解析的 workspace root。
    :param path: 待删除路径。
    :returns: ``None``。
    :raises CliInitUsageError: 删除前路径重新变得不安全时抛出。
    :raises OSError: 删除失败时抛出。
    """

    _validate_workspace_path(
        workspace_root=workspace_root,
        path=path,
        role=_RESET_DESTINATION_ROLE,
    )
    _delete_path_without_following_symlink(path)


__all__: tuple[str, ...] = ("run_init_command",)
