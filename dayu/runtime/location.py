"""层中立 runtime 位置解析器。

本模块只根据调用方显式传入的项目根目录与包内配置根目录解析 runtime
assembly 所需位置。它不读取配置 schema、不解释 scene manifest、不创建
Host / Engine 对象，也不导入任何业务层。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


class RuntimeLocationError(ValueError):
    """runtime 位置解析失败时抛出的结构化错误。"""


@dataclass(frozen=True, slots=True)
class RuntimeLocations:
    """runtime assembly 位置解析结果。

    :param config_overlay_dir: workspace 覆盖配置目录；不存在时为 ``None``。
    :param prompt_asset_root: 实际可用 prompt asset 根目录。
    :param scene_manifest_root: 实际可用 scene manifest 根目录。
    """

    config_overlay_dir: Path | None
    prompt_asset_root: Path
    scene_manifest_root: Path


def resolve_runtime_locations(
    *, project_root: Path, package_config_root: Path
) -> RuntimeLocations:
    """解析 runtime assembly 默认位置。

    :param project_root: 项目根目录；workspace 覆盖目录固定为其下
        ``workspace/config``。
    :param package_config_root: 包内默认配置根目录。
    :returns: runtime assembly 位置解析结果。
    :raises RuntimeLocationError: 包内 prompt 或 manifest 默认资产不存在时抛出。
    """

    workspace_config = project_root / "workspace" / "config"
    config_overlay_dir = workspace_config if workspace_config.exists() else None
    package_prompt_root = package_config_root / "prompts"
    package_manifest_root = package_prompt_root / "manifests"
    _require_directory(package_prompt_root, label="package prompt asset root")
    _require_directory(package_manifest_root, label="package scene manifest root")
    prompt_asset_root = _resolve_prompt_asset_root(
        config_overlay_dir=config_overlay_dir,
        package_prompt_root=package_prompt_root,
    )
    scene_manifest_root = _resolve_scene_manifest_root(
        config_overlay_dir=config_overlay_dir,
        package_manifest_root=package_manifest_root,
    )
    return RuntimeLocations(
        config_overlay_dir=config_overlay_dir,
        prompt_asset_root=prompt_asset_root,
        scene_manifest_root=scene_manifest_root,
    )


def _resolve_prompt_asset_root(
    *, config_overlay_dir: Path | None, package_prompt_root: Path
) -> Path:
    """解析 prompt asset 根目录。

    :param config_overlay_dir: workspace 覆盖配置目录；不存在时为 ``None``。
    :param package_prompt_root: 包内 prompt asset 根目录。
    :returns: 实际可用 prompt asset 根目录。
    :raises Exception: 不主动抛出异常。
    """

    if config_overlay_dir is None:
        return package_prompt_root
    workspace_prompt_root = config_overlay_dir / "prompts"
    if workspace_prompt_root.exists():
        return workspace_prompt_root
    return package_prompt_root


def _resolve_scene_manifest_root(
    *, config_overlay_dir: Path | None, package_manifest_root: Path
) -> Path:
    """解析 scene manifest 根目录。

    :param config_overlay_dir: workspace 覆盖配置目录；不存在时为 ``None``。
    :param package_manifest_root: 包内 scene manifest 根目录。
    :returns: 实际可用 scene manifest 根目录。
    :raises Exception: 不主动抛出异常。
    """

    if config_overlay_dir is None:
        return package_manifest_root
    workspace_manifest_root = config_overlay_dir / "prompts" / "manifests"
    if workspace_manifest_root.exists():
        return workspace_manifest_root
    return package_manifest_root


def _require_directory(path: Path, *, label: str) -> None:
    """校验路径是已存在目录。

    :param path: 待校验路径。
    :param label: 错误消息中的路径职责标签。
    :returns: ``None``。
    :raises RuntimeLocationError: 路径不存在或不是目录时抛出。
    """

    if not path.is_dir():
        raise RuntimeLocationError(f"{label} is not a directory: {path}")
