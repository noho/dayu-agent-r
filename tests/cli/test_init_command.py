"""``dayu-cli init`` 工作区初始化测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

import dayu.cli.commands.init as init_command
import dayu.cli.main as cli_main
from dayu.cli.exit_codes import (
    EXIT_FAILURE,
    EXIT_KEYBOARD_INTERRUPT,
    EXIT_SUCCESS,
    EXIT_USAGE_ERROR,
)
from dayu.runtime.config_loader import (
    ConfigLoader,
    config_file_names,
)
from dayu.runtime.location import resolve_runtime_locations

_REMOVED_CONFIG_FILE_NAMES: frozenset[str] = frozenset(
    {"llm_models.json", "run.json"}
)


def test_init_empty_workspace_copies_current_config(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """验证空 workspace init 会复制当前 schema 配置和 prompts。

    :param tmp_path: pytest 临时目录。
    :param capsys: pytest 标准输出捕获夹具。
    :returns: ``None``。
    :raises AssertionError: 初始化结果不符合 current schema bootstrap 时抛出。
    """

    workspace_root = tmp_path / "workspace"

    exit_code = cli_main.main(("init", "--base", str(workspace_root)))
    captured = capsys.readouterr()

    assert exit_code == EXIT_SUCCESS
    assert "initialized workspace config" in captured.out
    workspace_config = workspace_root / "config"
    for file_name in config_file_names():
        assert (workspace_config / file_name).is_file()
    assert (workspace_config / "prompts" / "manifests" / "prompt.json").is_file()
    assert (workspace_config / "prompts" / "scenes" / "interactive.md").is_file()
    for legacy_name in _REMOVED_CONFIG_FILE_NAMES:
        assert not (workspace_config / legacy_name).exists()


def test_init_existing_files_without_overwrite_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """验证目标配置文件存在且未传 ``--overwrite`` 时失败。

    :param tmp_path: pytest 临时目录。
    :param capsys: pytest 标准输出捕获夹具。
    :returns: ``None``。
    :raises AssertionError: 退出码或文件内容不符合覆盖保护语义时抛出。
    """

    workspace_config = tmp_path / "workspace" / "config"
    workspace_config.mkdir(parents=True)
    target = workspace_config / "models.json"
    target.write_text("user content", encoding="utf-8")

    exit_code = cli_main.main(("init", "--base", str(tmp_path / "workspace")))
    captured = capsys.readouterr()

    assert exit_code == EXIT_FAILURE
    assert "pass --overwrite" in captured.err
    assert target.read_text(encoding="utf-8") == "user content"


def test_init_overwrite_replaces_existing_config_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """验证 ``--overwrite`` 会替换已有配置文件。

    :param tmp_path: pytest 临时目录。
    :param capsys: pytest 标准输出捕获夹具。
    :returns: ``None``。
    :raises AssertionError: 文件没有被 current schema 配置替换时抛出。
    """

    workspace_config = tmp_path / "workspace" / "config"
    workspace_config.mkdir(parents=True)
    target = workspace_config / "models.json"
    target.write_text("user content", encoding="utf-8")

    exit_code = cli_main.main(
        ("init", "--base", str(tmp_path / "workspace"), "--overwrite")
    )
    captured = capsys.readouterr()

    assert exit_code == EXIT_SUCCESS
    assert "initialized workspace config" in captured.out
    assert '"models"' in target.read_text(encoding="utf-8")
    assert target.read_text(encoding="utf-8") != "user content"


def test_init_reset_only_deletes_hardcoded_whitelist(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """验证 reset 只删除硬编码白名单路径并保留禁止删除路径。

    :param tmp_path: pytest 临时目录。
    :param capsys: pytest 标准输出捕获夹具。
    :returns: ``None``。
    :raises AssertionError: reset 删除越界或遗漏 current init 结果时抛出。
    """

    project_root = tmp_path
    workspace_root = project_root / "workspace"
    _write_text(workspace_root / "config" / "old.json", "old")
    _write_text(workspace_root / ".dayu" / "host" / "old.txt", "old")
    _write_text(workspace_root / ".dayu" / "artifacts" / "old.txt", "old")
    _write_text(
        workspace_root / ".dayu" / "web_tools_storage_states" / "old.txt",
        "old",
    )
    _write_text(
        workspace_root / ".dayu" / "runtime" / "runtime_lanes.sqlite3",
        "runtime",
    )
    _write_text(project_root / ".dayu" / "fins_ingestion" / "jobs" / "job.json", "job")
    _write_text(project_root / ".dayu" / "sec_cache" / "cache.txt", "cache")
    _write_text(workspace_root / "fins" / "raw.txt", "fins")
    _write_text(project_root / "fins" / "raw.txt", "root-fins")
    _write_text(workspace_root / "user.txt", "user")

    exit_code = cli_main.main(
        ("init", "--base", str(workspace_root), "--reset", "--overwrite")
    )
    captured = capsys.readouterr()

    assert exit_code == EXIT_SUCCESS
    assert "reset 4 workspace path" in captured.out
    assert (workspace_root / "config" / "models.json").is_file()
    assert not (workspace_root / ".dayu" / "host").exists()
    assert not (workspace_root / ".dayu" / "artifacts").exists()
    assert not (workspace_root / ".dayu" / "web_tools_storage_states").exists()
    assert (
        workspace_root / ".dayu" / "runtime" / "runtime_lanes.sqlite3"
    ).read_text(encoding="utf-8") == "runtime"
    assert (
        project_root / ".dayu" / "fins_ingestion" / "jobs" / "job.json"
    ).read_text(encoding="utf-8") == "job"
    assert (project_root / ".dayu" / "sec_cache" / "cache.txt").read_text(
        encoding="utf-8"
    ) == "cache"
    assert (workspace_root / "fins" / "raw.txt").read_text(encoding="utf-8") == "fins"
    assert (project_root / "fins" / "raw.txt").read_text(
        encoding="utf-8"
    ) == "root-fins"
    assert (workspace_root / "user.txt").read_text(encoding="utf-8") == "user"


def test_init_reset_symlink_escape_fails_fast_without_deleting(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """验证 reset 白名单路径为 symlink 时失败且不执行任何删除。

    :param tmp_path: pytest 临时目录。
    :param capsys: pytest 标准输出捕获夹具。
    :returns: ``None``。
    :raises AssertionError: symlink 逃逸未 fail fast 或其它白名单被删除时抛出。
    """

    workspace_root = tmp_path / "workspace"
    outside_config = tmp_path / "outside-config"
    outside_config.mkdir()
    workspace_root.mkdir()
    (workspace_root / "config").symlink_to(outside_config, target_is_directory=True)
    _write_text(workspace_root / ".dayu" / "host" / "old.txt", "old")

    exit_code = cli_main.main(("init", "--base", str(workspace_root), "--reset"))
    captured = capsys.readouterr()

    assert exit_code == EXIT_USAGE_ERROR
    assert "symlink" in captured.err
    assert (workspace_root / "config").is_symlink()
    assert (outside_config).is_dir()
    assert (workspace_root / ".dayu" / "host" / "old.txt").read_text(
        encoding="utf-8"
    ) == "old"


def test_init_reset_parent_symlink_containment_escape_fails_fast(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """验证 reset 白名单父目录 symlink 逃逸时失败且不执行删除。

    :param tmp_path: pytest 临时目录。
    :param capsys: pytest 标准输出捕获夹具。
    :returns: ``None``。
    :raises AssertionError: resolve 后逃逸未 fail fast 或 config 被删除时抛出。
    """

    workspace_root = tmp_path / "workspace"
    outside_dayu = tmp_path / "outside-dayu"
    workspace_root.mkdir()
    outside_dayu.mkdir()
    (workspace_root / ".dayu").symlink_to(outside_dayu, target_is_directory=True)
    _write_text(outside_dayu / "host" / "old.txt", "outside")
    _write_text(workspace_root / "config" / "old.json", "config")

    exit_code = cli_main.main(("init", "--base", str(workspace_root), "--reset"))
    captured = capsys.readouterr()

    assert exit_code == EXIT_USAGE_ERROR
    assert "escapes workspace" in captured.err
    assert (workspace_root / ".dayu").is_symlink()
    assert (outside_dayu / "host" / "old.txt").read_text(
        encoding="utf-8"
    ) == "outside"
    assert (workspace_root / "config" / "old.json").read_text(
        encoding="utf-8"
    ) == "config"


def test_init_generated_workspace_config_loads_with_config_loader(
    tmp_path: Path,
) -> None:
    """验证 init 生成的 workspace config 可被 ``ConfigLoader`` 加载。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: ConfigLoader 无法加载生成配置时抛出。
    """

    workspace_root = tmp_path / "workspace"

    assert cli_main.main(("init", "--base", str(workspace_root))) == EXIT_SUCCESS
    config = ConfigLoader().load(workspace_config_dir=workspace_root / "config")

    assert config.models.models
    assert config.execution_profiles.default_execution_profile_id
    assert config.host_runtime.default_host_runtime_id


def test_init_base_workspace_aligns_with_runtime_location_default(
    tmp_path: Path,
) -> None:
    """init 生成的 config 必须被 runtime location 默认 overlay 选中。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: resolver 未对齐 init 目录布局时抛出。
    """

    workspace_root = tmp_path / "workspace"

    assert cli_main.main(("init", "--base", str(workspace_root))) == EXIT_SUCCESS
    locations = resolve_runtime_locations(
        workspace_root=workspace_root,
        package_config_root=Path(__file__).resolve().parents[2] / "dayu" / "config",
    )

    assert locations.config_overlay_dir == workspace_root / "config"
    assert locations.prompt_asset_root == workspace_root / "config" / "prompts"
    assert not (workspace_root / "workspace").exists()


def test_init_does_not_generate_legacy_config_files(tmp_path: Path) -> None:
    """验证 init 不生成旧 ``llm_models.json`` / ``run.json``。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: 旧配置文件被生成时抛出。
    """

    workspace_root = tmp_path / "workspace"

    assert cli_main.main(("init", "--base", str(workspace_root))) == EXIT_SUCCESS

    for legacy_name in _REMOVED_CONFIG_FILE_NAMES:
        assert not (workspace_root / "config" / legacy_name).exists()


def test_init_rejects_legacy_top_level_config_asset(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """验证包内顶层旧配置文件不会被 init 复制到 workspace config。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: 旧顶层配置文件未被拒绝时抛出。
    """

    package_config_root = tmp_path / "package-config"
    _write_minimal_current_config_assets(package_config_root)
    _write_text(package_config_root / "llm_models.json", "{}")

    def config_names_with_removed_file() -> tuple[str, ...]:
        """模拟当前顶层配置白名单被错误加入旧 schema 文件。

        :returns: 包含旧配置文件名的顶层配置文件名元组。
        :raises Exception: 不主动抛出异常。
        """

        return (*config_file_names(), "llm_models.json")

    monkeypatch.setattr(
        init_command,
        "config_file_names",
        config_names_with_removed_file,
    )

    with pytest.raises(
        init_command.CliInitOperationError,
        match="legacy config file must not be generated: llm_models.json",
    ):
        init_command._collect_current_config_assets(
            workspace_config_dir=tmp_path / "workspace" / "config",
            package_config_root=package_config_root,
        )


def test_init_allows_prompt_asset_with_removed_config_file_name(
    tmp_path: Path,
) -> None:
    """验证旧配置名只拦截顶层配置资产，不误伤 prompt 子文件。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: prompt 子文件被错误拒绝时抛出。
    """

    package_config_root = tmp_path / "package-config"
    _write_minimal_current_config_assets(package_config_root)
    _write_text(package_config_root / "prompts" / "scenes" / "run.json", "{}")

    assets = init_command._collect_current_config_assets(
        workspace_config_dir=tmp_path / "workspace" / "config",
        package_config_root=package_config_root,
    )

    assert any(asset.destination.name == "run.json" for asset in assets)


def test_init_sigint_maps_to_130(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """验证复制阶段 ``KeyboardInterrupt`` 映射为 130 且不输出成功。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch 夹具。
    :param capsys: pytest 标准输出捕获夹具。
    :returns: ``None``。
    :raises AssertionError: SIGINT 退出码或输出不符合取消语义时抛出。
    """

    def raise_keyboard_interrupt(*, source: Path, destination: Path) -> None:
        """测试替身：模拟复制阶段用户中断。

        :param source: 源文件路径。
        :param destination: 目标文件路径。
        :returns: 正常路径不会返回。
        :raises KeyboardInterrupt: 始终抛出以模拟 SIGINT。
        """

        del source, destination
        raise KeyboardInterrupt

    monkeypatch.setattr(init_command, "_copy_file_atomic", raise_keyboard_interrupt)

    exit_code = cli_main.main(("init", "--base", str(tmp_path / "workspace")))
    captured = capsys.readouterr()

    assert exit_code == EXIT_KEYBOARD_INTERRUPT
    assert "initialized workspace config" not in captured.out


def _write_text(path: Path, value: str) -> None:
    """写入测试文本文件并创建父目录。

    :param path: 目标路径。
    :param value: 文件内容。
    :returns: ``None``。
    :raises OSError: 文件写入失败时抛出。
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def _write_minimal_current_config_assets(package_config_root: Path) -> None:
    """写入 init 资产收集所需的最小 current schema 文件集合。

    :param package_config_root: 测试包内配置根目录。
    :returns: ``None``。
    :raises OSError: 文件写入失败时抛出。
    """

    for file_name in config_file_names():
        _write_text(package_config_root / file_name, "{}")
    _write_text(package_config_root / "prompts" / "scenes" / "prompt.md", "prompt")
