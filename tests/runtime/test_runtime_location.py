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
    """workspace root 下 config 不存在时 config_overlay_dir 必须为 None。"""

    package_config_root = _create_package_prompts(tmp_path)

    locations = resolve_runtime_locations(
        workspace_root=tmp_path,
        package_config_root=package_config_root,
    )

    assert locations.config_overlay_dir is None
    assert locations.prompt_asset_root == package_config_root / "prompts"
    assert locations.scene_manifest_root == package_config_root / "prompts" / "manifests"


def test_workspace_config_exists_selects_overlay_and_workspace_prompts(
    tmp_path: Path,
) -> None:
    """workspace root 下 config 存在且含 prompts 时必须返回 workspace 资产路径。"""

    package_config_root = _create_package_prompts(tmp_path)
    workspace_config = tmp_path / "config"
    (workspace_config / "prompts" / "manifests").mkdir(parents=True)

    locations = resolve_runtime_locations(
        workspace_root=tmp_path,
        package_config_root=package_config_root,
    )

    assert locations.config_overlay_dir == workspace_config
    assert locations.prompt_asset_root == workspace_config / "prompts"
    assert locations.scene_manifest_root == workspace_config / "prompts" / "manifests"


def test_workspace_config_without_prompts_keeps_package_assets(
    tmp_path: Path,
) -> None:
    """workspace root 下 config 存在但没有 prompts 时只提供 config overlay。"""

    package_config_root = _create_package_prompts(tmp_path)
    workspace_config = tmp_path / "config"
    workspace_config.mkdir(parents=True)

    locations = resolve_runtime_locations(
        workspace_root=tmp_path,
        package_config_root=package_config_root,
    )

    assert locations.config_overlay_dir == workspace_config
    assert locations.prompt_asset_root == package_config_root / "prompts"
    assert locations.scene_manifest_root == package_config_root / "prompts" / "manifests"


def test_explicit_config_overlay_dir_selects_explicit_config(
    tmp_path: Path,
) -> None:
    """显式配置覆盖目录存在时必须作为 config overlay 使用。"""

    package_config_root = _create_package_prompts(tmp_path)
    explicit_config = tmp_path / "custom_config"
    (explicit_config / "prompts" / "manifests").mkdir(parents=True)

    locations = resolve_runtime_locations(
        workspace_root=tmp_path,
        package_config_root=package_config_root,
        explicit_config_overlay_dir=explicit_config,
    )

    assert locations.config_overlay_dir == explicit_config
    assert locations.prompt_asset_root == explicit_config / "prompts"
    assert locations.scene_manifest_root == explicit_config / "prompts" / "manifests"


def test_explicit_config_overlay_dir_without_prompts_keeps_package_assets(
    tmp_path: Path,
) -> None:
    """显式配置目录可以只作为配置 overlay，不强制包含 prompts。"""

    package_config_root = _create_package_prompts(tmp_path)
    explicit_config = tmp_path / "custom_config"
    explicit_config.mkdir()

    locations = resolve_runtime_locations(
        workspace_root=tmp_path,
        package_config_root=package_config_root,
        explicit_config_overlay_dir=explicit_config,
    )

    assert locations.config_overlay_dir == explicit_config
    assert locations.prompt_asset_root == package_config_root / "prompts"
    assert locations.scene_manifest_root == package_config_root / "prompts" / "manifests"


def test_explicit_config_overlay_dir_must_exist(tmp_path: Path) -> None:
    """显式配置覆盖路径不存在时必须 fail fast。"""

    package_config_root = _create_package_prompts(tmp_path)

    with pytest.raises(RuntimeLocationError, match="explicit config overlay dir"):
        resolve_runtime_locations(
            workspace_root=tmp_path,
            package_config_root=package_config_root,
            explicit_config_overlay_dir=tmp_path / "missing_config",
        )


def test_explicit_config_overlay_dir_must_be_directory(tmp_path: Path) -> None:
    """显式配置覆盖路径不是目录时必须 fail fast。"""

    package_config_root = _create_package_prompts(tmp_path)
    explicit_file = tmp_path / "config.json"
    explicit_file.write_text("{}", encoding="utf-8")

    with pytest.raises(RuntimeLocationError, match="explicit config overlay dir"):
        resolve_runtime_locations(
            workspace_root=tmp_path,
            package_config_root=package_config_root,
            explicit_config_overlay_dir=explicit_file,
        )


def test_missing_package_prompt_assets_fail_fast(tmp_path: Path) -> None:
    """包内默认 prompt 资产缺失时必须 fail fast。"""

    with pytest.raises(RuntimeLocationError, match="package prompt asset root"):
        resolve_runtime_locations(
            workspace_root=tmp_path,
            package_config_root=tmp_path / "missing_config",
        )
