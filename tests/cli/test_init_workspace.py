"""dayu.cli.init_workspace 单一 transaction owner 测试。"""

from __future__ import annotations

import errno
import json
import os
import platform
import shutil
import stat
from collections.abc import Callable
from pathlib import Path
from typing import Protocol, cast
from unittest.mock import Mock

import pytest

import dayu.cli.init_workspace as init_workspace
from dayu.cli.init_catalog import (
    InitModelSelection,
    OllamaModelSettings,
    find_init_model_choice,
)
from dayu.cli.init_workspace import (
    InitMode,
    InitWorkspaceError,
    MANAGED_ROOT_MANIFEST,
    PathIdentity,
    WorkspaceTransactionRequest,
    abort_prepared_workspace_transaction,
    determine_init_mode,
    prepare_workspace_transaction,
    publish_workspace_transaction,
    snapshot_managed_roots,
)
from dayu.contracts.json_value import JsonValue
from dayu.runtime.config_loader import ToolDiscoveryProviderConfig
from dayu.service.host_assembly import ServiceDiscoveredTools

_PACKAGE_CONFIG_ROOT = Path(__file__).resolve().parents[2] / "dayu" / "config"
_PLATFORM = platform.system()


def _ollama_selection() -> InitModelSelection:
    """构造无需 secret 的真实 Ollama selection。

    :returns: 完整 typed selection。
    :raises Exception: catalog contract 漂移时由构造器抛出。
    """

    return InitModelSelection(
        choice=find_init_model_choice("ollama"),
        dynamic_settings=OllamaModelSettings(
            model_name="qwen3:8b",
            endpoint="http://localhost:11434/v1/chat/completions",
            context_window_tokens=32768,
        ),
    )


def _request(
    workspace_root: Path,
    *,
    mode: InitMode,
    package_config_root: Path | None = None,
) -> WorkspaceTransactionRequest:
    """为真实 package config 构造 transaction request。

    :param workspace_root: 已存在 workspace。
    :param mode: 当前四态。
    :param package_config_root: 可选测试 package config；None 使用生产真源。
    :returns: 完整 request。
    :raises InitWorkspaceError: snapshot 不安全时抛出。
    """

    snapshot = snapshot_managed_roots(
        workspace_root,
        platform_system=_PLATFORM,
    )
    return WorkspaceTransactionRequest(
        workspace_root=workspace_root.resolve(strict=True),
        package_config_root=(_PACKAGE_CONFIG_ROOT if package_config_root is None else package_config_root),
        mode=mode,
        selection=_ollama_selection(),
        expected_snapshot=snapshot,
        platform_system=_PLATFORM,
    )


def _package_config_with_fins_root(
    target_root: Path,
    *,
    raw_workspace_root: str | None,
) -> Path:
    """复制 package config 并设置四个 Fins provider 的 raw root。

    :param target_root: 测试 package config 目标。
    :param raw_workspace_root: None 表示不配置；字符串原样写入四个 provider。
    :returns: 独立 package config root。
    :raises OSError: 复制或写入失败时抛出。
    :raises KeyError: package tool discovery contract 漂移时抛出。
    """

    shutil.copytree(_PACKAGE_CONFIG_ROOT, target_root)
    discovery_path = target_root / "tool_discovery.json"
    payload = cast(
        dict[str, JsonValue],
        json.loads(discovery_path.read_text(encoding="utf-8")),
    )
    providers = cast(dict[str, JsonValue], payload["providers"])
    for provider_id in (
        "financial-read-tools",
        "financial-download-tools",
        "financial-preprocess-tools",
        "financial-upload-tools",
    ):
        provider = cast(dict[str, JsonValue], providers[provider_id])
        config = cast(dict[str, JsonValue], provider["config"])
        if raw_workspace_root is None:
            config.pop("workspace_root", None)
        else:
            config["workspace_root"] = raw_workspace_root
    discovery_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return target_root


def _write_text(path: Path, value: str) -> None:
    """创建 parent 并写入 UTF-8 测试文本。

    :param path: 目标路径。
    :param value: 文本。
    :returns: None。
    :raises OSError: mkdir/write 失败时抛出。
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def test_manifest_and_mode_precedence_are_single_source_of_truth(
    tmp_path: Path,
) -> None:
    """唯一 manifest 必须只含 .dayu/config，且 RESET 高于 OVERWRITE。

    :param tmp_path: pytest 临时目录。
    :returns: None。
    :raises AssertionError: manifest 或四态 drift 时抛出。
    """

    missing_workspace = tmp_path / "missing"
    first_snapshot = snapshot_managed_roots(
        missing_workspace,
        platform_system=_PLATFORM,
    )
    assert MANAGED_ROOT_MANIFEST.root_names == (".dayu", "config")
    assert (
        determine_init_mode(
            first_snapshot,
            reset=False,
            overwrite=False,
        )
        is InitMode.FIRST
    )
    assert (
        determine_init_mode(
            first_snapshot,
            reset=False,
            overwrite=True,
        )
        is InitMode.OVERWRITE
    )
    assert (
        determine_init_mode(
            first_snapshot,
            reset=True,
            overwrite=True,
        )
        is InitMode.RESET
    )

    _write_text(tmp_path / "existing" / "config" / "user.json", "{}")
    preserve_snapshot = snapshot_managed_roots(
        tmp_path / "existing",
        platform_system=_PLATFORM,
    )
    assert (
        determine_init_mode(
            preserve_snapshot,
            reset=False,
            overwrite=False,
        )
        is InitMode.PRESERVE
    )


def test_first_real_discovery_is_private_and_publishes_only_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """真实一次 discovery 的 Fins side effect 只落 private validation root。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch 夹具。
    :returns: None。
    :raises AssertionError: discovery 次数、13 catalog 或 public isolation 漂移。
    """

    workspace_root = (tmp_path / "workspace").resolve(strict=False)
    workspace_root.mkdir()
    public_portfolio = workspace_root / "portfolio"
    public_assets = workspace_root / "assets"
    _write_text(public_portfolio / "sentinel.txt", "portfolio")
    _write_text(public_assets / "sentinel.txt", "assets")
    observer = _DiscoveryObserver(init_workspace.discover_service_tools)
    monkeypatch.setattr(
        init_workspace,
        "discover_service_tools",
        observer,
    )
    prepared = prepare_workspace_transaction(_request(workspace_root, mode=InitMode.FIRST))

    assert observer.observed == [(True, True)]
    assert prepared.discovered_tool_count == 15
    assert len(prepared.validated_scene_ids) == 13
    assert not (prepared.transaction_root / "validation-workspace").exists()
    assert not (workspace_root / ".dayu").exists()
    assert (public_portfolio / "sentinel.txt").read_text(encoding="utf-8") == "portfolio"
    assert (public_assets / "sentinel.txt").read_text(encoding="utf-8") == "assets"

    result = publish_workspace_transaction(prepared)

    assert result.mode is InitMode.FIRST
    assert result.warnings == ()
    assert (workspace_root / "config" / "models.json").is_file()
    assert not (workspace_root / "config" / "README.md").exists()
    assert not (workspace_root / "config" / ".DS_Store").exists()
    assert not (workspace_root / ".dayu").exists()
    assert (public_portfolio / "sentinel.txt").read_text(encoding="utf-8") == "portfolio"
    assert (public_assets / "sentinel.txt").read_text(encoding="utf-8") == "assets"


@pytest.mark.parametrize(
    "raw_root_kind",
    ("unconfigured", "absolute", "relative"),
)
def test_legal_raw_fins_roots_use_one_real_private_discovery_without_rewrite(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    raw_root_kind: str,
) -> None:
    """三类合法 raw root 均由 private override 支配且不改写 raw config。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch 夹具。
    :param raw_root_kind: unconfigured、absolute 或 relative。
    :returns: None。
    :raises AssertionError: discovery 次数、override 或 raw bytes 漂移时抛出。
    """

    workspace_root = (tmp_path / "workspace").resolve(strict=False)
    workspace_root.mkdir()
    _write_text(workspace_root / "portfolio" / "sentinel.txt", "portfolio")
    _write_text(workspace_root / "assets" / "sentinel.txt", "assets")
    raw_workspace_root = {
        "unconfigured": None,
        "absolute": str((tmp_path / "configured-fins").resolve(strict=False)),
        "relative": "configured-relative-fins",
    }[raw_root_kind]
    package_config_root = _package_config_with_fins_root(
        tmp_path / "package-config",
        raw_workspace_root=raw_workspace_root,
    )
    raw_discovery_bytes = (package_config_root / "tool_discovery.json").read_bytes()
    observer = _DiscoveryObserver(init_workspace.discover_service_tools)
    monkeypatch.setattr(init_workspace, "discover_service_tools", observer)

    prepared = prepare_workspace_transaction(
        _request(
            workspace_root,
            mode=InitMode.FIRST,
            package_config_root=package_config_root,
        )
    )

    assert len(observer.fins_roots) == 1
    effective_roots = observer.fins_roots[0]
    assert len(effective_roots) == 4
    assert len(set(effective_roots)) == 1
    assert Path(effective_roots[0]).name == "validation-workspace"
    assert observer.observed == [(True, True)]
    assert (prepared.staged_config_root / "tool_discovery.json").read_bytes() == raw_discovery_bytes
    assert (package_config_root / "tool_discovery.json").read_bytes() == raw_discovery_bytes
    assert not (workspace_root / "config").exists()
    assert not (workspace_root / ".dayu").exists()
    assert (workspace_root / "portfolio" / "sentinel.txt").read_text(encoding="utf-8") == "portfolio"
    assert (workspace_root / "assets" / "sentinel.txt").read_text(encoding="utf-8") == "assets"

    result = publish_workspace_transaction(prepared)

    assert result.mode is InitMode.FIRST
    assert (workspace_root / "config" / "tool_discovery.json").read_bytes() == (raw_discovery_bytes)
    assert (package_config_root / "tool_discovery.json").read_bytes() == (raw_discovery_bytes)
    assert not (workspace_root / ".dayu").exists()
    assert (workspace_root / "portfolio" / "sentinel.txt").read_text(encoding="utf-8") == "portfolio"
    assert (workspace_root / "assets" / "sentinel.txt").read_text(encoding="utf-8") == "assets"


def test_preserve_overwrite_and_reset_have_distinct_tree_contracts(
    tmp_path: Path,
) -> None:
    """PRESERVE 保留 user file，OVERWRITE 删除它，RESET 移除旧 .dayu。

    :param tmp_path: pytest 临时目录。
    :returns: None。
    :raises AssertionError: 三态 whole-tree contract 漂移时抛出。
    """

    workspace_root = (tmp_path / "workspace").resolve(strict=False)
    workspace_root.mkdir()
    first = prepare_workspace_transaction(_request(workspace_root, mode=InitMode.FIRST))
    publish_workspace_transaction(first)
    user_file = workspace_root / "config" / "user-extension.json"
    _write_text(user_file, '{"owner":"user"}')
    dayu_state = workspace_root / ".dayu" / "state.txt"
    _write_text(dayu_state, "stable-state")
    dayu_identity = init_workspace._path_identity(
        workspace_root / ".dayu",
        platform_system=_PLATFORM,
    )
    _write_text(workspace_root / "assets" / "sentinel.txt", "assets")
    _write_text(workspace_root / "portfolio" / "sentinel.txt", "portfolio")
    user_manifest = workspace_root / "config" / "prompts" / "manifests" / "user-owned.json"
    user_manifest_bytes = b'{"owner":"user","model":{"opaque":true}}\n'
    user_manifest.write_bytes(user_manifest_bytes)
    missing_prompt = workspace_root / "config" / "prompts" / "scenes" / "fix.md"
    missing_prompt.unlink()

    preserve = prepare_workspace_transaction(_request(workspace_root, mode=InitMode.PRESERVE))
    publish_workspace_transaction(preserve)
    assert user_file.read_text(encoding="utf-8") == '{"owner":"user"}'
    assert missing_prompt.is_file()
    assert user_manifest.read_bytes() == user_manifest_bytes
    assert dayu_state.read_text(encoding="utf-8") == "stable-state"
    assert (
        init_workspace._path_identity(
            workspace_root / ".dayu",
            platform_system=_PLATFORM,
        )
        == dayu_identity
    )

    overwrite = prepare_workspace_transaction(_request(workspace_root, mode=InitMode.OVERWRITE))
    publish_workspace_transaction(overwrite)
    assert not user_file.exists()
    assert not user_manifest.exists()
    assert dayu_state.read_text(encoding="utf-8") == "stable-state"
    assert (
        init_workspace._path_identity(
            workspace_root / ".dayu",
            platform_system=_PLATFORM,
        )
        == dayu_identity
    )

    reset = prepare_workspace_transaction(_request(workspace_root, mode=InitMode.RESET))
    publish_workspace_transaction(reset)

    assert not (workspace_root / ".dayu").exists()
    assert (workspace_root / "config" / "models.json").is_file()
    assert (workspace_root / "portfolio" / "sentinel.txt").read_text(encoding="utf-8") == "portfolio"
    assert (workspace_root / "assets" / "sentinel.txt").read_text(encoding="utf-8") == "assets"


def test_abort_prepared_transaction_removes_only_private_container(
    tmp_path: Path,
) -> None:
    """Persistence failure 前 abort 只能删除 transaction-private container。

    :param tmp_path: pytest 临时目录。
    :returns: None。
    :raises AssertionError: abort 发布 config 或保留 private tree 时抛出。
    """

    workspace_root = (tmp_path / "workspace").resolve(strict=False)
    workspace_root.mkdir()
    _write_text(workspace_root / "portfolio" / "sentinel.txt", "keep")
    prepared = prepare_workspace_transaction(_request(workspace_root, mode=InitMode.FIRST))

    abort_prepared_workspace_transaction(prepared)

    assert not prepared.transaction_root.exists()
    assert not (workspace_root / "config").exists()
    assert (workspace_root / "portfolio" / "sentinel.txt").read_text(encoding="utf-8") == "keep"


def test_snapshot_rejects_root_and_nested_symlinks_without_following(
    tmp_path: Path,
) -> None:
    """Managed roots 的 root/nested symlink 都必须 pre-mutation fail closed。

    :param tmp_path: pytest 临时目录。
    :returns: None。
    :raises AssertionError: symlink 被跟随或外部 sentinel 被修改时抛出。
    """

    external = tmp_path / "external"
    _write_text(external / "sentinel.txt", "external")
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    (workspace_root / "config").symlink_to(external, target_is_directory=True)

    with pytest.raises(InitWorkspaceError, match="ordinary directory"):
        snapshot_managed_roots(workspace_root, platform_system=_PLATFORM)
    assert (external / "sentinel.txt").read_text(encoding="utf-8") == "external"

    (workspace_root / "config").unlink()
    (workspace_root / "config").mkdir()
    (workspace_root / "config" / "nested").symlink_to(
        external,
        target_is_directory=True,
    )
    with pytest.raises(InitWorkspaceError, match="symlink"):
        snapshot_managed_roots(workspace_root, platform_system=_PLATFORM)
    assert (external / "sentinel.txt").read_text(encoding="utf-8") == "external"

    (workspace_root / "config" / "nested").unlink()
    (workspace_root / "config" / "dangling").symlink_to(
        tmp_path / "missing-target",
        target_is_directory=True,
    )
    with pytest.raises(InitWorkspaceError, match="symlink"):
        snapshot_managed_roots(workspace_root, platform_system=_PLATFORM)
    assert not (tmp_path / "missing-target").exists()


def test_preserve_copy_race_symlink_is_rejected_before_staging_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PRESERVE 扫描后换入 symlink 时必须在模型 projection 前 fail closed。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch 夹具。
    :returns: None。
    :raises AssertionError: staging symlink 被跟随写入外部 target 时抛出。
    """

    workspace_root = (tmp_path / "workspace").resolve(strict=False)
    workspace_root.mkdir()
    first = prepare_workspace_transaction(_request(workspace_root, mode=InitMode.FIRST))
    publish_workspace_transaction(first)
    external = tmp_path / "external-models.json"
    external.write_text("external-sentinel", encoding="utf-8")
    injector = _StagingSymlinkInjector(
        real_builder=init_workspace._build_staged_config,
        external_target=external,
    )
    monkeypatch.setattr(init_workspace, "_build_staged_config", injector)

    with pytest.raises(InitWorkspaceError, match="symlink"):
        prepare_workspace_transaction(_request(workspace_root, mode=InitMode.PRESERVE))

    assert injector.triggered is True
    assert external.read_text(encoding="utf-8") == "external-sentinel"
    assert not tuple(workspace_root.glob(".dayu-init-transaction-*"))


def test_prepare_rejects_snapshot_identity_or_content_drift(
    tmp_path: Path,
) -> None:
    """Prepare 前 public root identity/content drift 必须停止。

    :param tmp_path: pytest 临时目录。
    :returns: None。
    :raises AssertionError: stale snapshot 仍进入 staging 时抛出。
    """

    workspace_root = (tmp_path / "workspace").resolve(strict=False)
    _write_text(workspace_root / "config" / "value.txt", "before")
    request = _request(workspace_root, mode=InitMode.PRESERVE)
    (workspace_root / "config" / "value.txt").write_text(
        "after",
        encoding="utf-8",
    )

    with pytest.raises(InitWorkspaceError) as raised:
        prepare_workspace_transaction(request)

    assert raised.value.stage == "managed_root_snapshot"
    assert not tuple(workspace_root.glob(".dayu-init-transaction-*"))


def test_publication_replace_failure_rolls_back_original_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Config publish replace fault 必须恢复原 config byte truth。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch 夹具。
    :returns: None。
    :raises AssertionError: replace fault 留下半发布 config 时抛出。
    """

    workspace_root = (tmp_path / "workspace").resolve(strict=False)
    workspace_root.mkdir()
    first = prepare_workspace_transaction(_request(workspace_root, mode=InitMode.FIRST))
    publish_workspace_transaction(first)
    original_models = (workspace_root / "config" / "models.json").read_bytes()
    overwrite = prepare_workspace_transaction(_request(workspace_root, mode=InitMode.OVERWRITE))
    fault = _ReplaceFault(
        real_replace=init_workspace.os.replace,
        boundary="config",
        after_effect=False,
        failure=OSError(errno.EIO, "fault"),
    )
    monkeypatch.setattr(init_workspace.os, "replace", fault)

    with pytest.raises(InitWorkspaceError) as raised:
        publish_workspace_transaction(overwrite)

    assert fault.triggered is True
    assert raised.value.stage == "publication"
    assert (workspace_root / "config" / "models.json").read_bytes() == original_models


@pytest.mark.parametrize(
    "failure",
    (OSError(errno.EPERM, "fault"), KeyboardInterrupt()),
)
@pytest.mark.parametrize(
    "cleanup_stage",
    (
        "post_publication_backup_cleanup",
        "post_publication_staging_cleanup",
    ),
)
def test_post_publication_cleanup_failure_is_truthful_warning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: OSError | KeyboardInterrupt,
    cleanup_stage: str,
) -> None:
    """Boundary 后 backup delete fault 只能 warning，不得 rollback 新 config。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch 夹具。
    :param failure: cleanup fault 或中断。
    :param cleanup_stage: backup 或 staging cleanup boundary。
    :returns: None。
    :raises AssertionError: cleanup fault 被报成 publication failure 时抛出。
    """

    workspace_root = (tmp_path / "workspace").resolve(strict=False)
    workspace_root.mkdir()
    first = prepare_workspace_transaction(_request(workspace_root, mode=InitMode.FIRST))
    publish_workspace_transaction(first)
    overwrite = prepare_workspace_transaction(_request(workspace_root, mode=InitMode.OVERWRITE))
    cleanup_fault = _BackupCleanupFault(
        real_cleanup=init_workspace._cleanup_private_path,
        failure=failure,
        target_stage=cleanup_stage,
    )
    monkeypatch.setattr(
        init_workspace,
        "_cleanup_private_path",
        cleanup_fault,
    )
    result = publish_workspace_transaction(overwrite)

    assert (workspace_root / "config" / "models.json").is_file()
    assert len(result.warnings) == 1
    warning = result.warnings[0]
    assert warning.stage == cleanup_stage
    assert warning.path_exists is True
    assert warning.partial_deletion is True


@pytest.mark.parametrize("boundary", ("identity", "quarantine", "delete"))
@pytest.mark.parametrize(
    "failure",
    (OSError(errno.EPERM, "fault"), KeyboardInterrupt()),
)
def test_post_publication_actual_cleanup_faults_become_truthful_warning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    boundary: str,
    failure: OSError | KeyboardInterrupt,
) -> None:
    """Post-publication identity/rename/delete fault 只能转 typed warning。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch 夹具。
    :param boundary: identity、quarantine rename 或 recursive delete。
    :param failure: OSError 或 KeyboardInterrupt。
    :returns: None。
    :raises AssertionError: warning path/type/partial truth 不准确时抛出。
    """

    parent = tmp_path / "owner"
    private = parent / "private"
    _write_text(private / "child.txt", "value")
    identity = init_workspace._path_identity(private, platform_system=_PLATFORM)
    if boundary == "identity":
        monkeypatch.setattr(
            init_workspace,
            "_path_identity",
            _IdentityFaultOnce(
                real_identity=init_workspace._path_identity,
                target=private,
                failure=failure,
            ),
        )
    elif boundary == "quarantine":
        monkeypatch.setattr(
            init_workspace.os,
            "replace",
            _ExactSourceReplaceFault(
                real_replace=init_workspace.os.replace,
                source_path=private,
                after_effect=False,
                failure=failure,
            ),
        )
    else:
        monkeypatch.setattr(
            init_workspace.shutil,
            "rmtree",
            _DeleteFailureRmtree(failure=failure),
        )

    warning = init_workspace._post_publication_cleanup(
        private,
        expected_identity=identity,
        private_parent=parent,
        platform_system=_PLATFORM,
        stage="post_publication_staging_cleanup",
    )

    assert warning is not None
    assert warning.stage == "post_publication_staging_cleanup"
    assert warning.path_exists is True
    assert warning.error_type == failure.__class__.__name__
    assert warning.partial_deletion is (boundary == "delete")
    assert warning.path.is_dir()


def test_post_publication_partial_delete_warning_uses_remaining_quarantine(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Post-publication partial delete warning 必须指向实际 remaining quarantine。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch 夹具。
    :returns: None。
    :raises AssertionError: partial warning 指向已消失 original path 时抛出。
    """

    parent = tmp_path / "owner"
    private = parent / "private"
    _write_text(private / "child.txt", "value")
    identity = init_workspace._path_identity(private, platform_system=_PLATFORM)
    monkeypatch.setattr(
        init_workspace.shutil,
        "rmtree",
        _PartialDeleteRmtree(),
    )

    warning = init_workspace._post_publication_cleanup(
        private,
        expected_identity=identity,
        private_parent=parent,
        platform_system=_PLATFORM,
        stage="post_publication_backup_cleanup",
    )

    assert warning is not None
    assert warning.partial_deletion is True
    assert warning.path_exists is True
    assert warning.path.name.startswith(".dayu-init-quarantine-")
    assert not private.exists()


def test_cleanup_identity_drift_fails_before_recursive_delete(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Quarantine 前 identity drift 不得调用 recursive delete。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch 夹具。
    :returns: None。
    :raises AssertionError: identity mismatch 对象被递归删除时抛出。
    """

    parent = tmp_path / "owner"
    private = parent / "private"
    private.mkdir(parents=True)
    actual = init_workspace._path_identity(private, platform_system=_PLATFORM)
    wrong = PathIdentity(
        device=actual.device,
        inode=actual.inode + 1,
        mode=actual.mode,
        file_attributes=actual.file_attributes,
        reparse_tag=actual.reparse_tag,
    )
    rmtree = Mock()
    monkeypatch.setattr(init_workspace.shutil, "rmtree", rmtree)

    with pytest.raises(InitWorkspaceError) as raised:
        init_workspace._cleanup_private_path(
            private,
            expected_identity=wrong,
            private_parent=parent,
            platform_system=_PLATFORM,
            stage="validation_cleanup",
        )

    assert raised.value.stage == "validation_cleanup_identity"
    assert private.is_dir()
    rmtree.assert_not_called()


def test_partial_recursive_delete_reports_retained_quarantine(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Recursive delete fault 必须报告 partial 与实际 quarantine path。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch 夹具。
    :returns: None。
    :raises AssertionError: partial deletion truth 被误报成完整 retained tree。
    """

    parent = tmp_path / "owner"
    private = parent / "private"
    _write_text(private / "child.txt", "value")
    identity = init_workspace._path_identity(private, platform_system=_PLATFORM)

    monkeypatch.setattr(
        init_workspace.shutil,
        "rmtree",
        _PartialDeleteRmtree(),
    )

    with pytest.raises(InitWorkspaceError) as raised:
        init_workspace._cleanup_private_path(
            private,
            expected_identity=identity,
            private_parent=parent,
            platform_system=_PLATFORM,
            stage="validation_cleanup",
        )

    assert raised.value.stage == "validation_cleanup_recursive_delete"
    assert raised.value.partial_deletion is True
    assert len(raised.value.retained_paths) == 1
    assert raised.value.retained_paths[0].is_dir()
    assert not private.exists()


@pytest.mark.parametrize("after_effect", (False, True))
@pytest.mark.parametrize(
    "failure",
    (OSError(errno.EPERM, "fault"), KeyboardInterrupt()),
)
def test_validation_quarantine_replace_fault_reports_actual_retained_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    after_effect: bool,
    failure: OSError | KeyboardInterrupt,
) -> None:
    """Quarantine replace 调用前后 fault 都必须报告实际 lexical path。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch 夹具。
    :param after_effect: 是否先完成真实 rename。
    :param failure: OSError 或 KeyboardInterrupt。
    :returns: None。
    :raises AssertionError: retained path 与 syscall effect 不一致时抛出。
    """

    parent = tmp_path / "owner"
    private = parent / "private"
    _write_text(private / "child.txt", "value")
    identity = init_workspace._path_identity(private, platform_system=_PLATFORM)
    fault = _ExactSourceReplaceFault(
        real_replace=init_workspace.os.replace,
        source_path=private,
        after_effect=after_effect,
        failure=failure,
    )
    monkeypatch.setattr(init_workspace.os, "replace", fault)

    with pytest.raises(InitWorkspaceError) as raised:
        init_workspace._cleanup_private_path(
            private,
            expected_identity=identity,
            private_parent=parent,
            platform_system=_PLATFORM,
            stage="validation_cleanup",
        )

    assert fault.triggered is True
    assert raised.value.stage == "validation_cleanup_quarantine"
    assert len(raised.value.retained_paths) == 1
    retained = raised.value.retained_paths[0]
    assert retained.is_dir()
    assert (retained / "child.txt").read_text(encoding="utf-8") == "value"
    assert retained == private if not after_effect else retained != private


@pytest.mark.parametrize(
    "failure",
    (OSError(errno.EIO, "fault"), KeyboardInterrupt()),
)
def test_validation_identity_read_fault_is_typed_and_retained(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: OSError | KeyboardInterrupt,
) -> None:
    """Cleanup 前 no-follow identity fault 不得退化为裸异常。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch 夹具。
    :param failure: OSError 或 KeyboardInterrupt。
    :returns: None。
    :raises AssertionError: identity fault 未携带 private retained truth 时抛出。
    """

    parent = tmp_path / "owner"
    private = parent / "private"
    private.mkdir(parents=True)
    identity = init_workspace._path_identity(private, platform_system=_PLATFORM)
    identity_fault = _IdentityFaultOnce(
        real_identity=init_workspace._path_identity,
        target=private,
        failure=failure,
    )
    monkeypatch.setattr(init_workspace, "_path_identity", identity_fault)

    with pytest.raises(InitWorkspaceError) as raised:
        init_workspace._cleanup_private_path(
            private,
            expected_identity=identity,
            private_parent=parent,
            platform_system=_PLATFORM,
            stage="validation_cleanup",
        )

    assert raised.value.stage == "validation_cleanup_identity"
    assert raised.value.retained_paths == (private,)
    assert private.is_dir()


def test_quarantine_identity_drift_and_posix_capability_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Quarantine identity drift 与缺失 fd-safe capability 均不得 rmtree。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch 夹具。
    :returns: None。
    :raises AssertionError: drift/capability boundary 删除 private tree 时抛出。
    """

    parent = tmp_path / "owner"
    drift_private = parent / "drift-private"
    drift_private.mkdir(parents=True)
    drift_identity = init_workspace._path_identity(
        drift_private,
        platform_system=_PLATFORM,
    )
    drift_provider = _QuarantineIdentityDrift(
        real_identity=init_workspace._path_identity,
    )
    monkeypatch.setattr(init_workspace, "_path_identity", drift_provider)
    with pytest.raises(InitWorkspaceError) as drift_error:
        init_workspace._cleanup_private_path(
            drift_private,
            expected_identity=drift_identity,
            private_parent=parent,
            platform_system=_PLATFORM,
            stage="validation_cleanup",
        )
    assert drift_error.value.stage == "validation_cleanup_quarantine_identity"
    assert drift_error.value.retained_paths[0].is_dir()

    monkeypatch.setattr(
        init_workspace,
        "_path_identity",
        drift_provider.real_identity,
    )
    capability_private = parent / "capability-private"
    capability_private.mkdir()
    capability_identity = init_workspace._path_identity(
        capability_private,
        platform_system="Darwin",
    )
    monkeypatch.setattr(
        init_workspace.shutil.rmtree,
        "avoids_symlink_attacks",
        False,
    )
    with pytest.raises(InitWorkspaceError) as capability_error:
        init_workspace._cleanup_private_path(
            capability_private,
            expected_identity=capability_identity,
            private_parent=parent,
            platform_system="Darwin",
            stage="validation_cleanup",
        )
    assert capability_error.value.stage == "validation_cleanup_capability"
    assert capability_error.value.retained_paths[0].is_dir()


@pytest.mark.parametrize(
    "failure",
    (OSError(errno.EIO, "fault"), KeyboardInterrupt()),
)
def test_recursive_delete_unstarted_fault_reports_quarantine(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: OSError | KeyboardInterrupt,
) -> None:
    """Recursive delete 未开始 fault 必须与 partial delete 分开报告 retained。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch 夹具。
    :param failure: OSError 或 KeyboardInterrupt。
    :returns: None。
    :raises AssertionError: quarantine/partial truth 被误报时抛出。
    """

    parent = tmp_path / "owner"
    private = parent / "private"
    _write_text(private / "child.txt", "value")
    identity = init_workspace._path_identity(private, platform_system=_PLATFORM)
    monkeypatch.setattr(
        init_workspace.shutil,
        "rmtree",
        _DeleteFailureRmtree(failure=failure),
    )

    with pytest.raises(InitWorkspaceError) as raised:
        init_workspace._cleanup_private_path(
            private,
            expected_identity=identity,
            private_parent=parent,
            platform_system=_PLATFORM,
            stage="validation_cleanup",
        )

    assert raised.value.stage == "validation_cleanup_recursive_delete"
    assert raised.value.partial_deletion is True
    assert len(raised.value.retained_paths) == 1
    assert (raised.value.retained_paths[0] / "child.txt").is_file()


def test_windows_reparse_identity_is_rejected_without_rmtree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Windows root reparse point 必须在 recursive delete 前拒绝。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch 夹具。
    :returns: None。
    :raises AssertionError: reparse root 被交给 rmtree 时抛出。
    """

    root = tmp_path / "root"
    root.mkdir()
    real_identity = init_workspace._path_identity(root, platform_system=_PLATFORM)
    reparse_identity = PathIdentity(
        device=real_identity.device,
        inode=real_identity.inode,
        mode=real_identity.mode,
        file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT,
        reparse_tag=1,
    )

    with pytest.raises(InitWorkspaceError, match="reparse"):
        init_workspace._require_ordinary_directory(
            root,
            reparse_identity,
            platform_system="Windows",
            stage="validation_identity",
        )


def test_windows_nested_reparse_simulation_preserves_external_sentinel(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Windows nested junction/reparse 模拟必须在 delete 前 fail closed。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch 夹具。
    :returns: None。
    :raises AssertionError: nested reparse 未被拒绝或外部 sentinel 改变时抛出。
    """

    external = tmp_path / "external"
    _write_text(external / "sentinel.txt", "external")
    root = tmp_path / "root"
    nested = root / "nested-junction"
    nested.mkdir(parents=True)
    identity_provider = _WindowsIdentityProvider(
        real_identity=init_workspace._path_identity,
        reparse_path=nested,
    )
    monkeypatch.setattr(
        init_workspace,
        "_path_identity",
        identity_provider,
    )

    with pytest.raises(InitWorkspaceError, match="reparse"):
        init_workspace._validate_ordinary_tree(
            root,
            platform_system="Windows",
        )

    assert (external / "sentinel.txt").read_text(encoding="utf-8") == "external"
    assert nested.is_dir()


def test_windows_ordinary_private_tree_cleanup_simulation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Windows capability flag 为 false 也不得永久拒绝 ordinary cleanup。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch 夹具。
    :returns: None。
    :raises AssertionError: ordinary Windows tree 未被安全删除时抛出。
    """

    parent = tmp_path / "owner"
    private = parent / "private"
    _write_text(private / "nested" / "value.txt", "value")
    identity_provider = _WindowsIdentityProvider(
        real_identity=init_workspace._path_identity,
        reparse_path=None,
    )
    monkeypatch.setattr(
        init_workspace,
        "_path_identity",
        identity_provider,
    )
    identity = identity_provider(private, platform_system="Windows")

    init_workspace._cleanup_private_path(
        private,
        expected_identity=identity,
        private_parent=parent,
        platform_system="Windows",
        stage="validation_cleanup",
    )

    assert not private.exists()


def test_windows_scan_delete_race_does_not_follow_replaced_nested_link(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Windows 扫描后 nested 被换成 link 时不得递归删除外部目标。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch 夹具。
    :returns: None。
    :raises AssertionError: 删除竞态跟随 link 或未完成 quarantine cleanup 时抛出。
    """

    external = tmp_path / "external"
    _write_text(external / "sentinel.txt", "external")
    parent = tmp_path / "owner"
    private = parent / "private"
    _write_text(private / "nested" / "value.txt", "value")
    identity_provider = _WindowsIdentityProvider(
        real_identity=init_workspace._path_identity,
        reparse_path=None,
    )
    monkeypatch.setattr(init_workspace, "_path_identity", identity_provider)
    identity = identity_provider(private, platform_system="Windows")
    race_rmtree = _WindowsScanDeleteRaceRmtree(
        real_rmtree=shutil.rmtree,
        external_root=external,
    )
    monkeypatch.setattr(init_workspace.shutil, "rmtree", race_rmtree)

    init_workspace._cleanup_private_path(
        private,
        expected_identity=identity,
        private_parent=parent,
        platform_system="Windows",
        stage="validation_cleanup",
    )

    assert race_rmtree.triggered is True
    assert not private.exists()
    assert (external / "sentinel.txt").read_text(encoding="utf-8") == "external"


def test_invalid_platform_and_relative_request_fail_closed(
    tmp_path: Path,
) -> None:
    """未知平台与 relative transaction root 均不得进入 mutation。

    :param tmp_path: pytest 临时目录。
    :returns: None。
    :raises AssertionError: 非法平台/路径未被 owner 拒绝时抛出。
    """

    with pytest.raises(InitWorkspaceError) as platform_error:
        snapshot_managed_roots(tmp_path, platform_system="UnknownOS")
    assert platform_error.value.stage == "platform"

    workspace_root = (tmp_path / "workspace").resolve(strict=False)
    workspace_root.mkdir()
    snapshot = snapshot_managed_roots(
        workspace_root,
        platform_system=_PLATFORM,
    )
    relative_request = WorkspaceTransactionRequest(
        workspace_root=Path("workspace"),
        package_config_root=_PACKAGE_CONFIG_ROOT,
        mode=InitMode.FIRST,
        selection=_ollama_selection(),
        expected_snapshot=snapshot,
        platform_system=_PLATFORM,
    )
    with pytest.raises(InitWorkspaceError) as path_error:
        prepare_workspace_transaction(relative_request)
    assert path_error.value.stage == "workspace_identity"


@pytest.mark.parametrize(
    "failure",
    (OSError(errno.EIO, "fault"), KeyboardInterrupt()),
)
@pytest.mark.parametrize("operation", ("open", "fsync"))
def test_sync_staged_config_propagates_file_fsync_failure_or_interrupt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: OSError | KeyboardInterrupt,
    operation: str,
) -> None:
    """Publication 前普通文件 open/fsync fault 必须向上抛出。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch 夹具。
    :param failure: 普通 I/O fault 或用户中断。
    :param operation: no-follow open 或 fsync。
    :returns: None。
    :raises AssertionError: fsync EIO 被吞掉时抛出。
    """

    config = tmp_path / "config"
    _write_text(config / "value.txt", "value")
    monkeypatch.setattr(
        init_workspace.os,
        operation,
        Mock(side_effect=failure),
    )

    with pytest.raises(failure.__class__):
        init_workspace._sync_staged_config(
            config,
            platform_system=_PLATFORM,
        )


@pytest.mark.parametrize("boundary", ("package-copy", "service-discovery"))
@pytest.mark.parametrize(
    "failure",
    (OSError(errno.ENOSPC, "fault"), KeyboardInterrupt()),
)
def test_staging_and_discovery_faults_have_zero_public_replace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    boundary: str,
    failure: OSError | KeyboardInterrupt,
) -> None:
    """Copy/真实 discovery boundary fault 均安全清理且不发布 public roots。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch 夹具。
    :param boundary: package copy 或 Service discovery。
    :param failure: ENOSPC 或 KeyboardInterrupt。
    :returns: None。
    :raises AssertionError: public root 变化或 transaction tree 遗留时抛出。
    """

    workspace_root = (tmp_path / "workspace").resolve(strict=False)
    workspace_root.mkdir()
    _write_text(workspace_root / "portfolio" / "sentinel.txt", "keep")
    if boundary == "package-copy":
        monkeypatch.setattr(
            init_workspace.shutil,
            "copy2",
            Mock(side_effect=failure),
        )
    else:
        monkeypatch.setattr(
            init_workspace,
            "discover_service_tools",
            Mock(side_effect=failure),
        )

    expected_error = KeyboardInterrupt if isinstance(failure, KeyboardInterrupt) else InitWorkspaceError
    with pytest.raises(expected_error):
        prepare_workspace_transaction(_request(workspace_root, mode=InitMode.FIRST))

    assert not (workspace_root / "config").exists()
    assert not (workspace_root / ".dayu").exists()
    assert (workspace_root / "portfolio" / "sentinel.txt").read_text(encoding="utf-8") == "keep"
    assert not tuple(workspace_root.glob(".dayu-init-transaction-*"))


@pytest.mark.parametrize(
    "failure",
    (OSError(errno.EIO, "fault"), KeyboardInterrupt()),
)
def test_posix_staging_directory_sync_fault_aborts_before_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: OSError | KeyboardInterrupt,
) -> None:
    """Staging config directory sync fault 必须清理 private tree 并 abort。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch 夹具。
    :param failure: OSError 或 KeyboardInterrupt。
    :returns: None。
    :raises AssertionError: directory sync fault 越过 publication 时抛出。
    """

    if _PLATFORM == "Windows":
        pytest.skip("Windows 不存在 POSIX staging directory fsync boundary")
    workspace_root = (tmp_path / "workspace").resolve(strict=False)
    workspace_root.mkdir()
    sync_fault = _StagingConfigSyncFault(
        real_sync=init_workspace._sync_directory,
        failure=failure,
    )
    monkeypatch.setattr(init_workspace, "_sync_directory", sync_fault)

    expected_error = KeyboardInterrupt if isinstance(failure, KeyboardInterrupt) else InitWorkspaceError
    with pytest.raises(expected_error):
        prepare_workspace_transaction(_request(workspace_root, mode=InitMode.FIRST))

    assert sync_fault.triggered is True
    assert not (workspace_root / "config").exists()
    assert not tuple(workspace_root.glob(".dayu-init-transaction-*"))


def test_real_config_loader_failure_aborts_private_staging(
    tmp_path: Path,
) -> None:
    """Malformed staging config 必须由真实 ConfigLoader 拒绝并零 publication。

    :param tmp_path: pytest 临时目录。
    :returns: None。
    :raises AssertionError: loader failure 留下 private/public mutation 时抛出。
    """

    workspace_root = (tmp_path / "workspace").resolve(strict=False)
    workspace_root.mkdir()
    package_config_root = _package_config_with_fins_root(
        tmp_path / "package-config",
        raw_workspace_root=None,
    )
    (package_config_root / "tool_discovery.json").write_text(
        "{invalid-json",
        encoding="utf-8",
    )

    with pytest.raises(InitWorkspaceError) as raised:
        prepare_workspace_transaction(
            _request(
                workspace_root,
                mode=InitMode.FIRST,
                package_config_root=package_config_root,
            )
        )

    assert raised.value.stage == "staging_validation"
    assert not (workspace_root / "config").exists()
    assert not tuple(workspace_root.glob(".dayu-init-transaction-*"))


def test_snapshot_rejects_special_file(
    tmp_path: Path,
) -> None:
    """Managed tree 中 special file 不得被 digest/copy。

    :param tmp_path: pytest 临时目录。
    :returns: None。
    :raises AssertionError: FIFO 被接受时抛出。
    """

    if os.name == "nt":
        pytest.skip("Windows runner 由 reparse contract 覆盖")
    config = tmp_path / "config"
    config.mkdir()
    os.mkfifo(config / "fifo")
    with pytest.raises(InitWorkspaceError, match="special file"):
        snapshot_managed_roots(tmp_path, platform_system=_PLATFORM)


@pytest.mark.parametrize(
    ("boundary", "after_effect"),
    (
        ("backup", False),
        ("backup", True),
        ("config", False),
        ("config", True),
    ),
)
@pytest.mark.parametrize(
    "failure",
    (OSError(errno.ENOSPC, "fault"), KeyboardInterrupt()),
)
def test_publication_replace_fault_matrix_restores_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    boundary: str,
    after_effect: bool,
    failure: OSError | KeyboardInterrupt,
) -> None:
    """Backup/config replace 调用前后 fault 都必须恢复原 snapshot。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch 夹具。
    :param boundary: backup 或 config publication。
    :param after_effect: 是否先执行真实 replace 再抛错。
    :param failure: OSError 或 KeyboardInterrupt。
    :returns: None。
    :raises AssertionError: rollback 后原 config byte truth 未恢复时抛出。
    """

    workspace_root = (tmp_path / "workspace").resolve(strict=False)
    workspace_root.mkdir()
    first = prepare_workspace_transaction(_request(workspace_root, mode=InitMode.FIRST))
    publish_workspace_transaction(first)
    user_file = workspace_root / "config" / "user.txt"
    _write_text(user_file, "original")
    before = snapshot_managed_roots(
        workspace_root,
        platform_system=_PLATFORM,
    )
    prepared = prepare_workspace_transaction(_request(workspace_root, mode=InitMode.OVERWRITE))
    fault = _ReplaceFault(
        real_replace=init_workspace.os.replace,
        boundary=boundary,
        after_effect=after_effect,
        failure=failure,
    )
    monkeypatch.setattr(init_workspace.os, "replace", fault)

    with pytest.raises(failure.__class__ if isinstance(failure, KeyboardInterrupt) else InitWorkspaceError):
        publish_workspace_transaction(prepared)

    after = snapshot_managed_roots(
        workspace_root,
        platform_system=_PLATFORM,
    )
    assert fault.triggered is True
    assert after == before
    assert user_file.read_text(encoding="utf-8") == "original"


@pytest.mark.parametrize("after_effect", (False, True))
@pytest.mark.parametrize(
    "failure",
    (OSError(errno.ENOSPC, "fault"), KeyboardInterrupt()),
)
def test_first_config_publish_fault_returns_to_absent_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    after_effect: bool,
    failure: OSError | KeyboardInterrupt,
) -> None:
    """FIRST config replace 调用前后 fault 均须回到 config absent。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch 夹具。
    :param after_effect: 是否先完成 staging→public rename。
    :param failure: OSError 或 KeyboardInterrupt。
    :returns: None。
    :raises AssertionError: FIRST rollback 留下 public/private config 时抛出。
    """

    workspace_root = (tmp_path / "workspace").resolve(strict=False)
    workspace_root.mkdir()
    prepared = prepare_workspace_transaction(_request(workspace_root, mode=InitMode.FIRST))
    fault = _ReplaceFault(
        real_replace=init_workspace.os.replace,
        boundary="config",
        after_effect=after_effect,
        failure=failure,
    )
    monkeypatch.setattr(init_workspace.os, "replace", fault)

    expected_error = KeyboardInterrupt if isinstance(failure, KeyboardInterrupt) else InitWorkspaceError
    with pytest.raises(expected_error):
        publish_workspace_transaction(prepared)

    assert fault.triggered is True
    assert not (workspace_root / "config").exists()
    assert not (workspace_root / ".dayu").exists()
    assert not tuple(workspace_root.glob(".dayu-init-transaction-*"))


@pytest.mark.parametrize("root_name", (".dayu", "config"))
@pytest.mark.parametrize("after_effect", (False, True))
@pytest.mark.parametrize(
    "failure",
    (OSError(errno.EIO, "fault"), KeyboardInterrupt()),
)
def test_reset_each_root_backup_fault_restores_both_roots(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    root_name: str,
    after_effect: bool,
    failure: OSError | KeyboardInterrupt,
) -> None:
    """RESET manifest 中每个实际 root 的 backup fault 都要恢复双根。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch 夹具。
    :param root_name: 注入 .dayu 或 config backup。
    :param after_effect: 是否先完成真实 replace。
    :param failure: OSError 或 KeyboardInterrupt。
    :returns: None。
    :raises AssertionError: 任一 public root 未恢复原 snapshot 时抛出。
    """

    workspace_root = (tmp_path / "workspace").resolve(strict=False)
    workspace_root.mkdir()
    first = prepare_workspace_transaction(_request(workspace_root, mode=InitMode.FIRST))
    publish_workspace_transaction(first)
    _write_text(workspace_root / ".dayu" / "state.txt", "state")
    before = snapshot_managed_roots(
        workspace_root,
        platform_system=_PLATFORM,
    )
    prepared = prepare_workspace_transaction(_request(workspace_root, mode=InitMode.RESET))
    fault = _ReplaceFault(
        real_replace=init_workspace.os.replace,
        boundary="backup",
        after_effect=after_effect,
        failure=failure,
        backup_root_name=root_name,
    )
    monkeypatch.setattr(init_workspace.os, "replace", fault)

    with pytest.raises(failure.__class__ if isinstance(failure, KeyboardInterrupt) else InitWorkspaceError):
        publish_workspace_transaction(prepared)

    assert fault.triggered is True
    assert (
        snapshot_managed_roots(
            workspace_root,
            platform_system=_PLATFORM,
        )
        == before
    )


@pytest.mark.parametrize("root_name", (".dayu", "config"))
@pytest.mark.parametrize("after_restore_effect", (False, True))
@pytest.mark.parametrize(
    "failure",
    (OSError(errno.EIO, "fault"), KeyboardInterrupt()),
)
def test_rollback_replace_failure_reports_current_truth_and_recovery_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    root_name: str,
    after_restore_effect: bool,
    failure: OSError | KeyboardInterrupt,
) -> None:
    """Rollback backup restore fault 必须报告 public truth 与可恢复 private path。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch 夹具。
    :param root_name: 注入 restore fault 的 manifest root。
    :param after_restore_effect: restore 是否已完成才抛错。
    :param failure: OSError 或 KeyboardInterrupt。
    :returns: None。
    :raises AssertionError: rollback failure 被吞掉或谎报完整恢复时抛出。
    """

    workspace_root = (tmp_path / "workspace").resolve(strict=False)
    workspace_root.mkdir()
    first = prepare_workspace_transaction(_request(workspace_root, mode=InitMode.FIRST))
    publish_workspace_transaction(first)
    _write_text(workspace_root / ".dayu" / "state.txt", "state")
    prepared = prepare_workspace_transaction(_request(workspace_root, mode=InitMode.RESET))
    fault = _PublicationAndRollbackReplaceFault(
        real_replace=init_workspace.os.replace,
        workspace_root=workspace_root,
        restore_root_name=root_name,
        after_restore_effect=after_restore_effect,
        failure=failure,
    )
    monkeypatch.setattr(init_workspace.os, "replace", fault)

    with pytest.raises(InitWorkspaceError) as raised:
        publish_workspace_transaction(prepared)

    error = raised.value
    assert error.stage == f"rollback_restore_{root_name}"
    assert len(error.public_root_states) == 2
    if after_restore_effect:
        assert f"{root_name}=present" in error.public_root_states
    else:
        assert f"{root_name}=absent" in error.public_root_states
        assert any(path.name.endswith(f"-{root_name}") for path in error.retained_paths)


@pytest.mark.parametrize(
    "failure",
    (OSError(errno.EIO, "fault"), KeyboardInterrupt()),
)
def test_scene_validation_fault_has_no_public_replace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: OSError | KeyboardInterrupt,
) -> None:
    """真实 validation boundary 抛错/中断时不得发生 public replace。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch 夹具。
    :param failure: Scene validation fault。
    :returns: None。
    :raises AssertionError: public roots 被修改或安全 cleanup 未完成时抛出。
    """

    workspace_root = (tmp_path / "workspace").resolve(strict=False)
    workspace_root.mkdir()
    monkeypatch.setattr(
        init_workspace,
        "prepare_scene",
        Mock(side_effect=failure),
    )

    expected_error = KeyboardInterrupt if isinstance(failure, KeyboardInterrupt) else InitWorkspaceError
    with pytest.raises(expected_error):
        prepare_workspace_transaction(_request(workspace_root, mode=InitMode.FIRST))

    assert not (workspace_root / "config").exists()
    assert not (workspace_root / ".dayu").exists()
    assert not tuple(workspace_root.glob(".dayu-init-transaction-*"))


@pytest.mark.parametrize(
    "failure",
    (OSError(errno.EIO, "fault"), KeyboardInterrupt()),
)
def test_validation_parent_sync_fault_retains_container_but_not_child(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: OSError | KeyboardInterrupt,
) -> None:
    """Validation child 已删后的 parent sync fault 必须报告唯一 retained truth。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch 夹具。
    :param failure: OSError 或 KeyboardInterrupt。
    :returns: None。
    :raises AssertionError: child/retained/durability truth 不准确时抛出。
    """

    workspace_root = (tmp_path / "workspace").resolve(strict=False)
    workspace_root.mkdir()
    sync_fault = _TransactionParentSyncFault(
        real_sync=init_workspace._sync_directory,
        failure=failure,
    )
    monkeypatch.setattr(init_workspace, "_sync_directory", sync_fault)

    with pytest.raises(InitWorkspaceError) as raised:
        prepare_workspace_transaction(_request(workspace_root, mode=InitMode.FIRST))

    error = raised.value
    assert error.stage == "validation_parent_directory_sync"
    assert error.deletion_durability_unconfirmed is True
    assert len(error.retained_paths) == 1
    transaction_root = error.retained_paths[0]
    assert transaction_root.is_dir()
    assert not (transaction_root / "validation-workspace").exists()
    assert not tuple(transaction_root.glob(".dayu-init-quarantine-*"))
    assert not (workspace_root / "config").exists()


@pytest.mark.parametrize(
    "failure",
    (OSError(errno.EIO, "fault"), KeyboardInterrupt()),
)
def test_posix_publication_sync_fault_rolls_back(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: OSError | KeyboardInterrupt,
) -> None:
    """POSIX publication workspace fsync fault 仍在 success boundary 前 rollback。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch 夹具。
    :param failure: OSError 或 KeyboardInterrupt。
    :returns: None。
    :raises AssertionError: publication sync fault 留下新 config 时抛出。
    """

    if _PLATFORM == "Windows":
        pytest.skip("Windows publication boundary 不含 parent-directory fsync")
    workspace_root = (tmp_path / "workspace").resolve(strict=False)
    workspace_root.mkdir()
    first = prepare_workspace_transaction(_request(workspace_root, mode=InitMode.FIRST))
    publish_workspace_transaction(first)
    _write_text(workspace_root / "config" / "user.txt", "original")
    before = snapshot_managed_roots(
        workspace_root,
        platform_system=_PLATFORM,
    )
    prepared = prepare_workspace_transaction(_request(workspace_root, mode=InitMode.OVERWRITE))
    sync_fault = _NthPathSyncFault(
        real_sync=init_workspace._sync_directory,
        target=workspace_root,
        fail_on_call=1,
        failure=failure,
    )
    monkeypatch.setattr(init_workspace, "_sync_directory", sync_fault)

    with pytest.raises(failure.__class__ if isinstance(failure, KeyboardInterrupt) else InitWorkspaceError):
        publish_workspace_transaction(prepared)

    assert (
        snapshot_managed_roots(
            workspace_root,
            platform_system=_PLATFORM,
        )
        == before
    )


@pytest.mark.parametrize(
    "failure",
    (OSError(errno.EIO, "fault"), KeyboardInterrupt()),
)
def test_posix_rollback_sync_fault_reports_durability_and_current_truth(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: OSError | KeyboardInterrupt,
) -> None:
    """Rollback restore 后 workspace fsync fault 必须保留 durability 真值。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch 夹具。
    :param failure: OSError 或 KeyboardInterrupt。
    :returns: None。
    :raises AssertionError: rollback sync 被误报成功或 public truth 错误时抛出。
    """

    if _PLATFORM == "Windows":
        pytest.skip("Windows rollback boundary 不含 parent-directory fsync")
    workspace_root = (tmp_path / "workspace").resolve(strict=False)
    workspace_root.mkdir()
    first = prepare_workspace_transaction(_request(workspace_root, mode=InitMode.FIRST))
    publish_workspace_transaction(first)
    before = snapshot_managed_roots(
        workspace_root,
        platform_system=_PLATFORM,
    )
    prepared = prepare_workspace_transaction(_request(workspace_root, mode=InitMode.OVERWRITE))
    replace_fault = _ReplaceFault(
        real_replace=init_workspace.os.replace,
        boundary="config",
        after_effect=False,
        failure=OSError(errno.EIO, "publication fault"),
    )
    sync_fault = _NthPathSyncFault(
        real_sync=init_workspace._sync_directory,
        target=workspace_root,
        fail_on_call=1,
        failure=failure,
    )
    monkeypatch.setattr(init_workspace.os, "replace", replace_fault)
    monkeypatch.setattr(init_workspace, "_sync_directory", sync_fault)

    with pytest.raises(InitWorkspaceError) as raised:
        publish_workspace_transaction(prepared)

    assert raised.value.stage == "rollback_workspace_directory_sync"
    assert raised.value.deletion_durability_unconfirmed is True
    assert "config=present" in raised.value.public_root_states
    assert (
        snapshot_managed_roots(
            workspace_root,
            platform_system=_PLATFORM,
        )
        == before
    )
    assert prepared.transaction_root in raised.value.retained_paths
    assert prepared.transaction_root.is_dir()


@pytest.mark.parametrize(
    "failure",
    (OSError(errno.EIO, "fault"), KeyboardInterrupt()),
)
def test_rollback_published_config_delete_fault_reports_quarantine_truth(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: OSError | KeyboardInterrupt,
) -> None:
    """Rollback 删除 transaction-published config 失败必须报告 quarantine。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch 夹具。
    :param failure: OSError 或 KeyboardInterrupt。
    :returns: None。
    :raises AssertionError: rollback cleanup fault 被吞掉或 retained path 错误时抛出。
    """

    workspace_root = (tmp_path / "workspace").resolve(strict=False)
    workspace_root.mkdir()
    prepared = prepare_workspace_transaction(_request(workspace_root, mode=InitMode.FIRST))
    replace_fault = _ReplaceFault(
        real_replace=init_workspace.os.replace,
        boundary="config",
        after_effect=True,
        failure=OSError(errno.EIO, "publication fault"),
    )
    monkeypatch.setattr(init_workspace.os, "replace", replace_fault)
    monkeypatch.setattr(
        init_workspace.shutil,
        "rmtree",
        _DeleteFailureRmtree(failure=failure),
    )

    with pytest.raises(InitWorkspaceError) as raised:
        publish_workspace_transaction(prepared)

    assert raised.value.stage == ("rollback_published_config_cleanup_recursive_delete")
    assert "config=absent" in raised.value.public_root_states
    assert any(path.name.startswith(".dayu-init-quarantine-") for path in raised.value.retained_paths)
    assert prepared.transaction_root in raised.value.retained_paths


@pytest.mark.parametrize(
    "failure",
    (OSError(errno.EIO, "fault"), KeyboardInterrupt()),
)
def test_post_publication_sync_fault_reports_deleted_cleanup_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: OSError | KeyboardInterrupt,
) -> None:
    """Boundary 后 parent sync fault 必须成功并报告 cleanup path 已不存在。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch 夹具。
    :param failure: OSError 或 KeyboardInterrupt。
    :returns: None。
    :raises AssertionError: warning 谎报 retained path 或触发 rollback 时抛出。
    """

    if _PLATFORM == "Windows":
        pytest.skip("Windows 不伪造 unsupported parent-directory sync")
    workspace_root = (tmp_path / "workspace").resolve(strict=False)
    workspace_root.mkdir()
    prepared = prepare_workspace_transaction(_request(workspace_root, mode=InitMode.FIRST))
    sync_fault = _NthPathSyncFault(
        real_sync=init_workspace._sync_directory,
        target=workspace_root,
        fail_on_call=2,
        failure=failure,
    )
    monkeypatch.setattr(init_workspace, "_sync_directory", sync_fault)

    result = publish_workspace_transaction(prepared)

    assert (workspace_root / "config").is_dir()
    assert len(result.warnings) == 1
    warning = result.warnings[0]
    assert warning.stage == "post_publication_workspace_directory_sync"
    assert warning.path_exists is False
    assert warning.deletion_durability_unconfirmed is True
    assert not warning.path.exists()


class _CleanupCallable(Protocol):
    """Private cleanup helper 的严格 callable contract。"""

    def __call__(
        self,
        path: Path,
        *,
        expected_identity: PathIdentity,
        private_parent: Path,
        platform_system: str,
        stage: str,
    ) -> None:
        """执行 identity-safe cleanup。

        :param path: cleanup path。
        :param expected_identity: owner identity。
        :param private_parent: owner parent。
        :param platform_system: 明确平台。
        :param stage: cleanup stage。
        :returns: None。
        :raises Exception: owner failure 时透传。
        """


class _IdentityCallable(Protocol):
    """Private no-follow identity helper 的严格 callable contract。"""

    def __call__(
        self,
        path: Path,
        *,
        platform_system: str,
    ) -> PathIdentity:
        """读取 path identity。

        :param path: 待读取路径。
        :param platform_system: 明确平台。
        :returns: PathIdentity。
        :raises Exception: owner 读取失败时透传。
        """

        raise NotImplementedError


class _StagingBuilderCallable(Protocol):
    """Workspace staging builder 的严格 callable contract。"""

    def __call__(
        self,
        request: WorkspaceTransactionRequest,
        *,
        staged_config_root: Path,
    ) -> None:
        """构造 staging config tree。

        :param request: 完整 transaction request。
        :param staged_config_root: staging config target。
        :returns: None。
        :raises Exception: owner staging failure 时透传。
        """

        raise NotImplementedError


class _StagingSymlinkInjector:
    """在 public config copy 完成后把 staging models 换成 symlink。"""

    def __init__(
        self,
        *,
        real_builder: _StagingBuilderCallable,
        external_target: Path,
    ) -> None:
        """初始化 copy race 注入器。

        :param real_builder: 真实 staging builder。
        :param external_target: staging symlink 外部目标。
        :returns: None。
        :raises Exception: 不主动抛出异常。
        """

        self._real_builder = real_builder
        self._external_target = external_target
        self.triggered = False

    def __call__(
        self,
        request: WorkspaceTransactionRequest,
        *,
        staged_config_root: Path,
    ) -> None:
        """真实 staging 后把 models 换成外部 symlink。

        :param request: 完整 transaction request。
        :param staged_config_root: staging config target。
        :returns: None。
        :raises OSError: 真实复制、unlink 或建 link 失败时抛出。
        """

        self._real_builder(
            request,
            staged_config_root=staged_config_root,
        )
        if not self.triggered:
            staged_models = staged_config_root / "models.json"
            staged_models.unlink()
            staged_models.symlink_to(self._external_target)
            self.triggered = True


class _WindowsIdentityProvider:
    """在非 Windows runner 上投影 Windows ordinary/reparse attributes。"""

    def __init__(
        self,
        *,
        real_identity: _IdentityCallable,
        reparse_path: Path | None,
    ) -> None:
        """初始化 provider。

        :param real_identity: 当前平台真实 no-follow identity owner。
        :param reparse_path: 需要投影成 reparse point 的 nested path。
        :returns: None。
        :raises Exception: 不主动抛出异常。
        """

        self._real_identity = real_identity
        self._reparse_path = reparse_path

    def __call__(
        self,
        path: Path,
        *,
        platform_system: str,
    ) -> PathIdentity:
        """返回保留真实 inode/type 的 Windows attributes 投影。

        :param path: 待读取路径。
        :param platform_system: 调用方平台值；测试要求 Windows。
        :returns: 模拟 Windows identity。
        :raises AssertionError: 调用方未传 Windows 时抛出。
        """

        assert platform_system == "Windows"
        real = self._real_identity(path, platform_system=_PLATFORM)
        is_reparse = self._reparse_path is not None and path == self._reparse_path
        return PathIdentity(
            device=real.device,
            inode=real.inode,
            mode=real.mode,
            file_attributes=(stat.FILE_ATTRIBUTE_REPARSE_POINT if is_reparse else 0),
            reparse_tag=1 if is_reparse else 0,
        )


class _DiscoveryObserver:
    """包装真实 discovery 并在 cleanup 前观察 Fins roots。"""

    def __init__(
        self,
        real_discover: Callable[
            [tuple[ToolDiscoveryProviderConfig, ...]],
            ServiceDiscoveredTools,
        ],
    ) -> None:
        """初始化 observer。

        :param real_discover: 真实 Service discovery。
        :returns: None。
        :raises Exception: 不主动抛出异常。
        """

        self._real_discover = real_discover
        self.observed: list[tuple[bool, bool]] = []
        self.fins_roots: list[tuple[str, ...]] = []

    def __call__(
        self,
        effective_provider_configs: tuple[ToolDiscoveryProviderConfig, ...],
    ) -> ServiceDiscoveredTools:
        """调用真实 discovery 并观察 private .dayu/portfolio。

        :param effective_provider_configs: Service effective configs。
        :returns: 真实 discovery result。
        :raises Exception: 真实 provider failure 时透传。
        """

        result = self._real_discover(effective_provider_configs)
        raw_fins_roots = tuple(
            config.config["workspace_root"]
            for config in effective_provider_configs
            if config.provider_id.startswith("financial-")
        )
        assert len(raw_fins_roots) == 4
        assert all(isinstance(root, str) for root in raw_fins_roots)
        fins_roots = cast(tuple[str, ...], raw_fins_roots)
        self.fins_roots.append(fins_roots)
        raw_fins_root = fins_roots[0]
        assert isinstance(raw_fins_root, str)
        fins_root = Path(raw_fins_root)
        self.observed.append(
            (
                (fins_root / ".dayu").is_dir(),
                (fins_root / "portfolio").is_dir(),
            )
        )
        return result


class _WindowsScanDeleteRaceRmtree:
    """模拟 Windows tree validation 后 nested path 被换成目录 link。"""

    def __init__(
        self,
        *,
        real_rmtree: Callable[[Path], None],
        external_root: Path,
    ) -> None:
        """初始化竞态注入器。

        :param real_rmtree: 当前 runner 的真实 rmtree。
        :param external_root: link 指向的外部目录。
        :returns: None。
        :raises Exception: 不主动抛出异常。
        """

        self._real_rmtree = real_rmtree
        self._external_root = external_root
        self.triggered = False

    def __call__(self, path: Path) -> None:
        """扫描后替换 nested，再调用 runner 的 fd-safe rmtree。

        :param path: 已 quarantine 的 private root。
        :returns: None。
        :raises OSError: 删除、建 link 或真实 rmtree 失败时抛出。
        """

        nested = path / "nested"
        self._real_rmtree(nested)
        nested.symlink_to(self._external_root, target_is_directory=True)
        self.triggered = True
        self._real_rmtree(path)


class _IdentityFaultOnce:
    """对一个精确 path 的首次 owner identity 读取注入 fault。"""

    def __init__(
        self,
        *,
        real_identity: _IdentityCallable,
        target: Path,
        failure: OSError | KeyboardInterrupt,
    ) -> None:
        """初始化一次性 identity fault。

        :param real_identity: 真实 no-follow identity owner。
        :param target: 精确 fault path。
        :param failure: OSError 或 KeyboardInterrupt。
        :returns: None。
        :raises Exception: 不主动抛出异常。
        """

        self._real_identity = real_identity
        self._target = target
        self._failure = failure
        self._triggered = False

    def __call__(
        self,
        path: Path,
        *,
        platform_system: str,
    ) -> PathIdentity:
        """首次命中 target 时抛错，否则转发真实 owner。

        :param path: identity path。
        :param platform_system: 明确平台。
        :returns: 未 fault 时的真实 identity。
        :raises OSError: 配置为 OSError 时抛出。
        :raises KeyboardInterrupt: 配置为中断时抛出。
        """

        if path == self._target and not self._triggered:
            self._triggered = True
            raise self._failure
        return self._real_identity(path, platform_system=platform_system)


class _QuarantineIdentityDrift:
    """把新 quarantine 的 identity 投影为不同 inode。"""

    def __init__(self, *, real_identity: _IdentityCallable) -> None:
        """初始化 drift provider。

        :param real_identity: 真实 identity owner。
        :returns: None。
        :raises Exception: 不主动抛出异常。
        """

        self.real_identity = real_identity

    def __call__(
        self,
        path: Path,
        *,
        platform_system: str,
    ) -> PathIdentity:
        """Quarantine 返回 drift identity，其它路径返回真实 identity。

        :param path: identity path。
        :param platform_system: 明确平台。
        :returns: 真实或 drift identity。
        :raises OSError: 真实 owner 失败时透传。
        """

        identity = self.real_identity(path, platform_system=platform_system)
        if not path.name.startswith(".dayu-init-quarantine-"):
            return identity
        return PathIdentity(
            device=identity.device,
            inode=identity.inode + 1,
            mode=identity.mode,
            file_attributes=identity.file_attributes,
            reparse_tag=identity.reparse_tag,
        )


class _ExactSourceReplaceFault:
    """对精确 source 的 replace 调用前或调用后注入 fault。"""

    def __init__(
        self,
        *,
        real_replace: Callable[[Path, Path], None],
        source_path: Path,
        after_effect: bool,
        failure: OSError | KeyboardInterrupt,
    ) -> None:
        """初始化精确 replace fault。

        :param real_replace: 真实 os.replace。
        :param source_path: 精确 source path。
        :param after_effect: 是否先执行真实 rename。
        :param failure: OSError 或 KeyboardInterrupt。
        :returns: None。
        :raises Exception: 不主动抛出异常。
        """

        self._real_replace = real_replace
        self._source_path = source_path
        self._after_effect = after_effect
        self._failure = failure
        self.triggered = False

    def __call__(self, source: Path, destination: Path) -> None:
        """命中精确 source 时注入 fault，否则转发。

        :param source: replace source。
        :param destination: replace destination。
        :returns: None。
        :raises OSError: 配置为 OSError 时抛出。
        :raises KeyboardInterrupt: 配置为中断时抛出。
        """

        if source == self._source_path and not self.triggered:
            self.triggered = True
            if self._after_effect:
                self._real_replace(source, destination)
            raise self._failure
        self._real_replace(source, destination)


class _DeleteFailureRmtree:
    """在 recursive delete 尚未开始时注入 fault。"""

    avoids_symlink_attacks = True

    def __init__(self, *, failure: OSError | KeyboardInterrupt) -> None:
        """初始化 delete fault。

        :param failure: OSError 或 KeyboardInterrupt。
        :returns: None。
        :raises Exception: 不主动抛出异常。
        """

        self._failure = failure

    def __call__(self, path: Path) -> None:
        """不修改 path 并立即抛错。

        :param path: quarantine root。
        :returns: 本函数不返回。
        :raises OSError: 配置为 OSError 时抛出。
        :raises KeyboardInterrupt: 配置为中断时抛出。
        """

        del path
        raise self._failure


class _BackupCleanupFault:
    """只在 post-publication backup cleanup 注入 fault。"""

    def __init__(
        self,
        *,
        real_cleanup: _CleanupCallable,
        failure: OSError | KeyboardInterrupt,
        target_stage: str,
    ) -> None:
        """初始化 cleanup fault。

        :param real_cleanup: 真实 cleanup owner。
        :param failure: 待抛 fault。
        :param target_stage: 需要注入 fault 的 post-publication stage。
        :returns: None。
        :raises Exception: 不主动抛出异常。
        """

        self._real_cleanup = real_cleanup
        self._failure = failure
        self._target_stage = target_stage

    def __call__(
        self,
        path: Path,
        *,
        expected_identity: PathIdentity,
        private_parent: Path,
        platform_system: str,
        stage: str,
    ) -> None:
        """命中 backup cleanup 时抛错，否则调用真实 owner。

        :param path: cleanup path。
        :param expected_identity: owner identity。
        :param private_parent: owner parent。
        :param platform_system: 明确平台。
        :param stage: cleanup stage。
        :returns: None。
        :raises OSError: 配置为 OSError 时抛出。
        :raises KeyboardInterrupt: 配置为中断时抛出。
        """

        if stage == self._target_stage:
            raise self._failure
        self._real_cleanup(
            path,
            expected_identity=expected_identity,
            private_parent=private_parent,
            platform_system=platform_system,
            stage=stage,
        )


class _ReplaceFault:
    """在指定 replace boundary 的调用前或调用后注入 fault。"""

    def __init__(
        self,
        *,
        real_replace: Callable[[Path, Path], None],
        boundary: str,
        after_effect: bool,
        failure: OSError | KeyboardInterrupt,
        backup_root_name: str | None = None,
    ) -> None:
        """初始化 replace fault。

        :param real_replace: 真实 os.replace。
        :param boundary: backup 或 config。
        :param after_effect: 是否先执行真实 syscall。
        :param failure: 待抛异常。
        :param backup_root_name: 只命中指定 managed-root backup；None 表示首个。
        :returns: None。
        :raises ValueError: boundary 非法时抛出。
        """

        if boundary not in {"backup", "config"}:
            raise ValueError("unsupported replace fault boundary")
        self._real_replace = real_replace
        self._boundary = boundary
        self._after_effect = after_effect
        self._failure = failure
        self._backup_root_name = backup_root_name
        self.triggered = False

    def __call__(self, source: Path, destination: Path) -> None:
        """执行或注入一次 replace fault。

        :param source: replace source。
        :param destination: replace destination。
        :returns: None。
        :raises OSError: 配置为 OSError 时抛出。
        :raises KeyboardInterrupt: 配置为中断时抛出。
        """

        is_backup = destination.name.startswith(".dayu-init-backup-")
        if self._backup_root_name is not None:
            is_backup = is_backup and destination.name.endswith(f"-{self._backup_root_name}")
        is_config = destination.name == "config" and source.parent.name.startswith(".dayu-init-transaction-")
        matches = self._boundary == "backup" and is_backup or self._boundary == "config" and is_config
        if matches and not self.triggered:
            self.triggered = True
            if self._after_effect:
                self._real_replace(source, destination)
            raise self._failure
        self._real_replace(source, destination)


class _TransactionParentSyncFault:
    """在 validation cleanup 后 transaction parent sync 注入 fault。"""

    def __init__(
        self,
        *,
        real_sync: Callable[[Path], None],
        failure: OSError | KeyboardInterrupt,
    ) -> None:
        """初始化 transaction sync fault。

        :param real_sync: 真实 directory sync helper。
        :param failure: 待抛异常。
        :returns: None。
        :raises Exception: 不主动抛出异常。
        """

        self._real_sync = real_sync
        self._failure = failure
        self._triggered = False

    def __call__(self, path: Path) -> None:
        """命中 transaction root 时抛出一次 fault。

        :param path: directory path。
        :returns: None。
        :raises OSError: 配置为 OSError 时抛出。
        :raises KeyboardInterrupt: 配置为中断时抛出。
        """

        if path.name.startswith(".dayu-init-transaction-") and not self._triggered:
            self._triggered = True
            raise self._failure
        self._real_sync(path)


class _StagingConfigSyncFault:
    """在 transaction-private config directory sync 注入一次 fault。"""

    def __init__(
        self,
        *,
        real_sync: Callable[[Path], None],
        failure: OSError | KeyboardInterrupt,
    ) -> None:
        """初始化 staging sync fault。

        :param real_sync: 真实 directory sync owner。
        :param failure: OSError 或 KeyboardInterrupt。
        :returns: None。
        :raises Exception: 不主动抛出异常。
        """

        self._real_sync = real_sync
        self._failure = failure
        self.triggered = False

    def __call__(self, path: Path) -> None:
        """首次命中 transaction/config 时抛错，否则转发。

        :param path: directory path。
        :returns: None。
        :raises OSError: 配置为 OSError 时抛出。
        :raises KeyboardInterrupt: 配置为中断时抛出。
        """

        if path.name == "config" and path.parent.name.startswith(".dayu-init-transaction-") and not self.triggered:
            self.triggered = True
            raise self._failure
        self._real_sync(path)


class _PublicationAndRollbackReplaceFault:
    """先让 config publication 失败，再让 backup restore 失败。"""

    def __init__(
        self,
        *,
        real_replace: Callable[[Path, Path], None],
        workspace_root: Path,
        restore_root_name: str,
        after_restore_effect: bool,
        failure: OSError | KeyboardInterrupt,
    ) -> None:
        """初始化双阶段 replace fault。

        :param real_replace: 真实 os.replace。
        :param workspace_root: public workspace。
        :param restore_root_name: 注入 restore fault 的 manifest root。
        :param after_restore_effect: restore 是否先执行真实 syscall。
        :param failure: OSError 或 KeyboardInterrupt。
        :returns: None。
        :raises Exception: 不主动抛出异常。
        """

        self._real_replace = real_replace
        self._workspace_root = workspace_root
        self._restore_root_name = restore_root_name
        self._after_restore_effect = after_restore_effect
        self._failure = failure
        self._publication_failed = False

    def __call__(self, source: Path, destination: Path) -> None:
        """按 publication/rollback 次序注入 fault。

        :param source: replace source。
        :param destination: replace destination。
        :returns: None。
        :raises OSError: config publication 或配置的 restore OSError。
        :raises KeyboardInterrupt: restore 配置为中断时抛出。
        """

        is_publication = destination == self._workspace_root / "config" and source.parent.name.startswith(
            ".dayu-init-transaction-"
        )
        is_restore = destination == self._workspace_root / self._restore_root_name and source.name.startswith(
            ".dayu-init-backup-"
        )
        if is_publication and not self._publication_failed:
            self._publication_failed = True
            raise OSError(errno.EIO, "publication fault")
        if is_restore and self._publication_failed:
            if self._after_restore_effect:
                self._real_replace(source, destination)
            raise self._failure
        self._real_replace(source, destination)


class _NthPathSyncFault:
    """对指定 path 的第 N 次 directory sync 注入 fault。"""

    def __init__(
        self,
        *,
        real_sync: Callable[[Path], None],
        target: Path,
        fail_on_call: int,
        failure: OSError | KeyboardInterrupt,
    ) -> None:
        """初始化 path sync fault。

        :param real_sync: 真实 sync helper。
        :param target: 只计数该 path。
        :param fail_on_call: 从一开始的失败序号。
        :param failure: 待抛异常。
        :returns: None。
        :raises ValueError: fail_on_call 非正时抛出。
        """

        if fail_on_call <= 0:
            raise ValueError("fail_on_call must be positive")
        self._real_sync = real_sync
        self._target = target
        self._fail_on_call = fail_on_call
        self._failure = failure
        self._count = 0

    def __call__(self, path: Path) -> None:
        """对 target 计数并在指定次序抛错。

        :param path: directory path。
        :returns: None。
        :raises OSError: 配置为 OSError 时抛出。
        :raises KeyboardInterrupt: 配置为中断时抛出。
        """

        if path == self._target:
            self._count += 1
            if self._count == self._fail_on_call:
                raise self._failure
        self._real_sync(path)


class _PartialDeleteRmtree:
    """模拟 fd-safe rmtree 在已删除一个 child 后失败。"""

    avoids_symlink_attacks = True

    def __call__(self, path: Path) -> None:
        """删除一个 child 后注入 EIO。

        :param path: quarantine root。
        :returns: None。
        :raises OSError: 始终注入 EIO。
        """

        (path / "child.txt").unlink()
        raise OSError(errno.EIO, "fault")
