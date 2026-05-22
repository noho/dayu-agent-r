"""``dayu.runtime.location`` 位置解析测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from dayu.runtime.location import (
    RuntimeLocationError,
    resolve_runtime_locations,
)


def _create_package_prompts(root: Path) -> Path:
    """创建包内 prompt fixture。

    :param root: 测试根目录。
    :returns: 包内配置根目录。
    :raises OSError: 目录创建失败时抛出。
    """

    package_config_root = root / "package_config"
    (package_config_root / "prompts" / "manifests").mkdir(parents=True)
    return package_config_root


def test_workspace_config_absent_returns_none_overlay(tmp_path: Path) -> None:
    """workspace/config 不存在时 config_overlay_dir 必须为 None。"""

    package_config_root = _create_package_prompts(tmp_path)

    locations = resolve_runtime_locations(
        project_root=tmp_path,
        package_config_root=package_config_root,
    )

    assert locations.config_overlay_dir is None
    assert locations.prompt_asset_root == package_config_root / "prompts"
    assert locations.scene_manifest_root == package_config_root / "prompts" / "manifests"


def test_workspace_config_exists_selects_overlay_and_workspace_prompts(
    tmp_path: Path,
) -> None:
    """workspace/config 存在且含 prompts 时必须返回 workspace 资产路径。"""

    package_config_root = _create_package_prompts(tmp_path)
    workspace_config = tmp_path / "workspace" / "config"
    (workspace_config / "prompts" / "manifests").mkdir(parents=True)

    locations = resolve_runtime_locations(
        project_root=tmp_path,
        package_config_root=package_config_root,
    )

    assert locations.config_overlay_dir == workspace_config
    assert locations.prompt_asset_root == workspace_config / "prompts"
    assert locations.scene_manifest_root == workspace_config / "prompts" / "manifests"


def test_workspace_config_without_prompts_keeps_package_assets(
    tmp_path: Path,
) -> None:
    """workspace/config 存在但没有 prompts 时只提供 config overlay。"""

    package_config_root = _create_package_prompts(tmp_path)
    workspace_config = tmp_path / "workspace" / "config"
    workspace_config.mkdir(parents=True)

    locations = resolve_runtime_locations(
        project_root=tmp_path,
        package_config_root=package_config_root,
    )

    assert locations.config_overlay_dir == workspace_config
    assert locations.prompt_asset_root == package_config_root / "prompts"
    assert locations.scene_manifest_root == package_config_root / "prompts" / "manifests"


def test_missing_package_prompt_assets_fail_fast(tmp_path: Path) -> None:
    """包内默认 prompt 资产缺失时必须 fail fast。"""

    with pytest.raises(RuntimeLocationError, match="package prompt asset root"):
        resolve_runtime_locations(
            project_root=tmp_path,
            package_config_root=tmp_path / "missing_config",
        )
