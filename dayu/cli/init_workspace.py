"""dayu-cli init 的单一 workspace transaction owner。

本模块拥有 .dayu/config 两个 managed roots 的快照、四态、私有
staging/validation/backup、真实 Service discovery 校验、跨平台 no-follow
cleanup、发布、回滚与如实 cleanup 结果。它不接触 secret，也不创建或删除
workspace root。
"""

from __future__ import annotations

import hashlib
import os
import shutil
import stat
import tempfile
import uuid
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Final, Protocol, cast

from dayu.cli.init_catalog import (
    PRODUCTION_RUNTIME_MANIFEST_BASENAMES,
    InitModelSelection,
    apply_model_selection,
    project_known_manifest_models,
)
from dayu.runtime.config_loader import ConfigLoader, RuntimeConfig, config_file_names
from dayu.runtime.scene_prepare import (
    ScenePrepareRequest,
    SceneToolCatalog,
    prepare_scene,
)
from dayu.service.host_assembly import (
    assemble_effective_tool_provider_configs,
    discover_service_tools,
)

_DAYU_ROOT_NAME: Final[str] = ".dayu"
_CONFIG_ROOT_NAME: Final[str] = "config"
_PROMPTS_ROOT_NAME: Final[str] = "prompts"
_MANIFESTS_ROOT_NAME: Final[str] = "manifests"
_VALIDATION_ROOT_NAME: Final[str] = "validation-workspace"
_TRANSACTION_PREFIX: Final[str] = ".dayu-init-transaction-"
_BACKUP_PREFIX: Final[str] = ".dayu-init-backup-"
_QUARANTINE_PREFIX: Final[str] = ".dayu-init-quarantine-"
_CURRENT_TIME_SLOT: Final[str] = "current_time"
_FINS_DEFAULT_SUBJECT_SLOT: Final[str] = "fins_default_subject"
_WINDOWS_PLATFORM: Final[str] = "Windows"
_POSIX_PLATFORMS: Final[frozenset[str]] = frozenset({"Darwin", "Linux"})
_READ_ONLY_OPEN_FLAGS: Final[int] = os.O_RDONLY
_FILE_READ_CHUNK_BYTES: Final[int] = 1024 * 1024


class _WindowsStatResult(Protocol):
    """Windows stat_result 的 no-follow reparse 字段视图。"""

    st_file_attributes: int
    st_reparse_tag: int


class InitWorkspaceError(RuntimeError):
    """Workspace transaction 在明确阶段失败且携带 retained truth。"""

    stage: str
    retained_paths: tuple[Path, ...]
    public_root_states: tuple[str, ...]
    partial_deletion: bool
    deletion_durability_unconfirmed: bool

    def __init__(
        self,
        *,
        stage: str,
        message: str,
        retained_paths: tuple[Path, ...] = (),
        public_root_states: tuple[str, ...] = (),
        partial_deletion: bool = False,
        deletion_durability_unconfirmed: bool = False,
    ) -> None:
        """初始化不含 secret 的 transaction failure。

        :param stage: 失败的唯一 transaction 阶段。
        :param message: 安全错误摘要。
        :param retained_paths: 仍可定位的 transaction-private 路径。
        :param public_root_states: public managed roots 的真值摘要。
        :param partial_deletion: 私有树是否可能已部分删除。
        :param deletion_durability_unconfirmed: 删除目录项 durability 是否未确认。
        :returns: None。
        :raises Exception: 不主动抛出异常。
        """

        super().__init__(message)
        self.stage = stage
        self.retained_paths = retained_paths
        self.public_root_states = public_root_states
        self.partial_deletion = partial_deletion
        self.deletion_durability_unconfirmed = deletion_durability_unconfirmed


class InitMode(StrEnum):
    """dayu-cli init 的四个唯一 workspace 状态。"""

    FIRST = "first"
    PRESERVE = "preserve"
    OVERWRITE = "overwrite"
    RESET = "reset"


@dataclass(frozen=True, slots=True)
class ManagedRootManifest:
    """Workspace transaction 的唯一 managed-root manifest。

    :param root_names: 相对 workspace 的 whole-tree 根名称。
    """

    root_names: tuple[str, ...]

    def __post_init__(self) -> None:
        """校验根名称唯一且为直接子目录。

        :returns: None。
        :raises ValueError: 名称为空、重复或包含路径层级时抛出。
        """

        if len(set(self.root_names)) != len(self.root_names):
            raise ValueError("managed root names must be unique")
        for root_name in self.root_names:
            if not root_name or Path(root_name).name != root_name:
                raise ValueError("managed root names must be direct non-empty children")


MANAGED_ROOT_MANIFEST: Final[ManagedRootManifest] = ManagedRootManifest(root_names=(_DAYU_ROOT_NAME, _CONFIG_ROOT_NAME))


@dataclass(frozen=True, slots=True)
class PathIdentity:
    """No-follow 文件系统对象 identity。

    :param device: st_dev。
    :param inode: st_ino。
    :param mode: st_mode。
    :param file_attributes: Windows file attributes；POSIX 为零。
    :param reparse_tag: Windows reparse tag；POSIX 为零。
    """

    device: int
    inode: int
    mode: int
    file_attributes: int
    reparse_tag: int


@dataclass(frozen=True, slots=True)
class ManagedRootSnapshot:
    """单个 public managed root 的 identity 与逐字节摘要。

    :param name: manifest 根名称。
    :param path: canonical public path。
    :param identity: 根不存在时为 None。
    :param content_digest: 根不存在时为 None。
    """

    name: str
    path: Path
    identity: PathIdentity | None
    content_digest: str | None

    @property
    def exists(self) -> bool:
        """返回 snapshot 中该根是否存在。

        :returns: 根存在时返回 True。
        :raises Exception: 不主动抛出异常。
        """

        return self.identity is not None


@dataclass(frozen=True, slots=True)
class WorkspaceSnapshot:
    """同一 canonical workspace 下两个 managed roots 的 snapshot。

    :param workspace_root: canonical absolute workspace root。
    :param roots: 严格按 manifest 顺序排列的 root snapshots。
    """

    workspace_root: Path
    roots: tuple[ManagedRootSnapshot, ...]

    def root(self, name: str) -> ManagedRootSnapshot:
        """按 manifest 名称返回 root snapshot。

        :param name: managed root 名称。
        :returns: 对应 snapshot。
        :raises KeyError: 名称不在唯一 manifest 时抛出。
        """

        for root_snapshot in self.roots:
            if root_snapshot.name == name:
                return root_snapshot
        raise KeyError(name)


@dataclass(frozen=True, slots=True)
class WorkspaceTransactionRequest:
    """准备 workspace transaction 所需的完整 typed request。

    :param workspace_root: 已创建、canonical 且在 init lock 内复核的 workspace。
    :param package_config_root: 当前 package config 真源。
    :param mode: 已由四态 owner 决定的模式。
    :param selection: 已完成交互的模型选择。
    :param expected_snapshot: 锁内确认的 public snapshot。
    :param platform_system: 明确的标准平台值。
    """

    workspace_root: Path
    package_config_root: Path
    mode: InitMode
    selection: InitModelSelection
    expected_snapshot: WorkspaceSnapshot
    platform_system: str


@dataclass(frozen=True, slots=True)
class PreparedWorkspaceTransaction:
    """已完成真实校验、等待环境持久化后发布的 transaction state。

    :param request: 原始 typed request。
    :param transaction_root: transaction-private container。
    :param transaction_identity: container 创建时 identity。
    :param staged_config_root: 已校验、已同步的待发布 config root。
    :param staged_config_identity: config root 发布前 identity。
    :param discovered_tool_count: 唯一真实 discovery 产生的工具数。
    :param validated_scene_ids: 已通过的 13 个 production scene ids。
    """

    request: WorkspaceTransactionRequest
    transaction_root: Path
    transaction_identity: PathIdentity
    staged_config_root: Path
    staged_config_identity: PathIdentity
    discovered_tool_count: int
    validated_scene_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class WorkspaceCleanupWarning:
    """Publication boundary 后不会反向回滚的 cleanup warning。

    :param stage: cleanup 失败阶段。
    :param path: 相关 private path。
    :param path_exists: 报告时路径是否仍存在。
    :param partial_deletion: 是否可能已部分删除。
    :param deletion_durability_unconfirmed: POSIX directory sync 是否未确认。
    :param error_type: 底层异常类型名。
    """

    stage: str
    path: Path
    path_exists: bool
    partial_deletion: bool
    deletion_durability_unconfirmed: bool
    error_type: str


@dataclass(frozen=True, slots=True)
class WorkspaceTransactionResult:
    """Workspace transaction 的 truthful publication 结果。

    :param mode: 已发布四态。
    :param config_root: public config root。
    :param warnings: publication boundary 后 cleanup warnings。
    :param discovered_tool_count: validation 唯一 discovery 的工具数。
    :param validated_scene_ids: validation 通过的 13 个 scene ids。
    """

    mode: InitMode
    config_root: Path
    warnings: tuple[WorkspaceCleanupWarning, ...]
    discovered_tool_count: int
    validated_scene_ids: tuple[str, ...]


def snapshot_managed_roots(
    workspace_root: Path,
    *,
    platform_system: str,
) -> WorkspaceSnapshot:
    """读取唯一 manifest 的 no-follow identity 与逐字节快照。

    :param workspace_root: canonical workspace root；可尚未存在。
    :param platform_system: 明确的标准平台值。
    :returns: 按 manifest 顺序排列的 workspace snapshot。
    :raises InitWorkspaceError: workspace/tree 不安全或无法读取时抛出。
    """

    _validate_platform(platform_system)
    canonical_workspace = workspace_root.expanduser().resolve(strict=False)
    if not workspace_root.exists():
        if workspace_root.is_symlink():
            raise InitWorkspaceError(
                stage="workspace_identity",
                message="workspace root must not be a symlink",
            )
        return WorkspaceSnapshot(
            workspace_root=canonical_workspace,
            roots=tuple(
                ManagedRootSnapshot(
                    name=root_name,
                    path=canonical_workspace / root_name,
                    identity=None,
                    content_digest=None,
                )
                for root_name in MANAGED_ROOT_MANIFEST.root_names
            ),
        )
    workspace_identity = _path_identity(workspace_root, platform_system=platform_system)
    _require_ordinary_directory(
        workspace_root,
        workspace_identity,
        platform_system=platform_system,
        stage="workspace_identity",
    )
    roots: list[ManagedRootSnapshot] = []
    for root_name in MANAGED_ROOT_MANIFEST.root_names:
        path = canonical_workspace / root_name
        if not path.exists() and not path.is_symlink():
            roots.append(
                ManagedRootSnapshot(
                    name=root_name,
                    path=path,
                    identity=None,
                    content_digest=None,
                )
            )
            continue
        identity = _path_identity(path, platform_system=platform_system)
        _require_ordinary_directory(
            path,
            identity,
            platform_system=platform_system,
            stage="managed_root_identity",
        )
        _validate_ordinary_tree(path, platform_system=platform_system)
        roots.append(
            ManagedRootSnapshot(
                name=root_name,
                path=path,
                identity=identity,
                content_digest=_tree_digest(path, platform_system=platform_system),
            )
        )
    return WorkspaceSnapshot(workspace_root=canonical_workspace, roots=tuple(roots))


def determine_init_mode(
    snapshot: WorkspaceSnapshot,
    *,
    reset: bool,
    overwrite: bool,
) -> InitMode:
    """按 RESET > OVERWRITE > config existence 决定唯一四态。

    :param snapshot: 当前 managed-root snapshot。
    :param reset: 用户是否显式传入 --reset。
    :param overwrite: 用户是否显式传入 --overwrite。
    :returns: 唯一 InitMode。
    :raises KeyError: snapshot 不含 config root 时抛出。
    """

    if reset:
        return InitMode.RESET
    if overwrite:
        return InitMode.OVERWRITE
    if snapshot.root(_CONFIG_ROOT_NAME).exists:
        return InitMode.PRESERVE
    return InitMode.FIRST


def prepare_workspace_transaction(
    request: WorkspaceTransactionRequest,
) -> PreparedWorkspaceTransaction:
    """构造、真实发现/scene 校验并同步 private staging config。

    :param request: 完整 typed transaction request。
    :returns: 可在环境持久化成功后发布的 transaction state。
    :raises InitWorkspaceError: snapshot/staging/validation/cleanup 失败时抛出。
    :raises KeyboardInterrupt: 中断且安全 cleanup 成功时重新抛出。
    """

    _validate_request(request)
    _require_snapshot_unchanged(request)
    try:
        transaction_root = Path(
            tempfile.mkdtemp(
                prefix=_TRANSACTION_PREFIX,
                dir=request.workspace_root,
            )
        )
    except OSError as exc:
        raise InitWorkspaceError(
            stage="transaction_create",
            message=(f"transaction container creation failed: {exc.__class__.__name__}"),
        ) from exc
    try:
        transaction_identity = _path_identity(
            transaction_root,
            platform_system=request.platform_system,
        )
        workspace_identity = _path_identity(
            request.workspace_root,
            platform_system=request.platform_system,
        )
    except (OSError, KeyboardInterrupt) as exc:
        raise InitWorkspaceError(
            stage="transaction_identity",
            message=(f"transaction/workspace identity could not be read: {exc.__class__.__name__}"),
            retained_paths=(transaction_root,),
        ) from exc
    if transaction_identity.device != workspace_identity.device:
        raise InitWorkspaceError(
            stage="transaction_filesystem",
            message="transaction container must share the workspace filesystem",
            retained_paths=(transaction_root,),
        )
    staged_config_root = transaction_root / _CONFIG_ROOT_NAME
    validation_root = transaction_root / _VALIDATION_ROOT_NAME
    try:
        _build_staged_config(request, staged_config_root=staged_config_root)
        initial_staged_identity = _path_identity(
            staged_config_root,
            platform_system=request.platform_system,
        )
        if initial_staged_identity.device != transaction_identity.device:
            raise InitWorkspaceError(
                stage="staging_filesystem",
                message="staged config must share the transaction filesystem",
                retained_paths=(transaction_root,),
            )
        _validate_ordinary_tree(
            staged_config_root,
            platform_system=request.platform_system,
        )
        apply_model_selection(staged_config_root, request.selection)
        project_known_manifest_models(
            staged_config_root / _PROMPTS_ROOT_NAME / _MANIFESTS_ROOT_NAME,
            request.selection,
        )
        validation_root.mkdir()
        validation_identity = _path_identity(
            validation_root,
            platform_system=request.platform_system,
        )
        if validation_identity.device != transaction_identity.device:
            raise InitWorkspaceError(
                stage="validation_filesystem",
                message="validation root must share the transaction filesystem",
                retained_paths=(transaction_root,),
            )
        _require_ordinary_directory(
            validation_root,
            validation_identity,
            platform_system=request.platform_system,
            stage="validation_identity",
        )
        runtime_config = ConfigLoader(package_config_dir=staged_config_root).load()
        tool_count, scene_ids = _validate_staged_runtime(
            runtime_config,
            public_workspace_root=request.workspace_root,
            private_validation_root=validation_root.resolve(strict=True),
            staged_config_root=staged_config_root,
        )
        _cleanup_private_path(
            validation_root,
            expected_identity=validation_identity,
            private_parent=transaction_root,
            platform_system=request.platform_system,
            stage="validation_cleanup",
        )
        if request.platform_system in _POSIX_PLATFORMS:
            try:
                _sync_directory(transaction_root)
            except (OSError, KeyboardInterrupt) as exc:
                raise InitWorkspaceError(
                    stage="validation_parent_directory_sync",
                    message="validation child deleted but parent sync failed",
                    retained_paths=(transaction_root,),
                    deletion_durability_unconfirmed=True,
                ) from exc
        _sync_staged_config(
            staged_config_root,
            platform_system=request.platform_system,
        )
        staged_config_identity = _path_identity(
            staged_config_root,
            platform_system=request.platform_system,
        )
        return PreparedWorkspaceTransaction(
            request=request,
            transaction_root=transaction_root,
            transaction_identity=transaction_identity,
            staged_config_root=staged_config_root,
            staged_config_identity=staged_config_identity,
            discovered_tool_count=tool_count,
            validated_scene_ids=scene_ids,
        )
    except InitWorkspaceError as exc:
        if exc.retained_paths:
            raise InitWorkspaceError(
                stage=exc.stage,
                message=str(exc),
                retained_paths=tuple(dict.fromkeys((transaction_root, *exc.retained_paths))),
                public_root_states=exc.public_root_states,
                partial_deletion=exc.partial_deletion,
                deletion_durability_unconfirmed=(exc.deletion_durability_unconfirmed),
            ) from exc
        try:
            _discard_private_container_or_raise(
                transaction_root,
                expected_identity=transaction_identity,
                platform_system=request.platform_system,
                stage="staging_contract_cleanup",
            )
        except InitWorkspaceError as cleanup_error:
            raise cleanup_error from exc
        raise
    except KeyboardInterrupt:
        _discard_private_container_or_raise(
            transaction_root,
            expected_identity=transaction_identity,
            platform_system=request.platform_system,
            stage="staging_interrupt_cleanup",
        )
        raise
    except Exception as exc:
        try:
            _discard_private_container_or_raise(
                transaction_root,
                expected_identity=transaction_identity,
                platform_system=request.platform_system,
                stage="staging_failure_cleanup",
            )
        except InitWorkspaceError as cleanup_error:
            raise cleanup_error from exc
        raise InitWorkspaceError(
            stage="staging_validation",
            message=f"staging validation failed: {exc.__class__.__name__}",
        ) from exc


def abort_prepared_workspace_transaction(
    prepared: PreparedWorkspaceTransaction,
) -> None:
    """在环境持久化未成功时安全丢弃未发布 transaction。

    :param prepared: 已完成 publication 前校验的 transaction state。
    :returns: None。
    :raises InitWorkspaceError: identity drift 或 cleanup 失败时抛出。
    """

    _discard_private_container_or_raise(
        prepared.transaction_root,
        expected_identity=prepared.transaction_identity,
        platform_system=prepared.request.platform_system,
        stage="pre_publication_abort_cleanup",
    )


def publish_workspace_transaction(
    prepared: PreparedWorkspaceTransaction,
) -> WorkspaceTransactionResult:
    """发布 staged config，并在 success boundary 后如实清理 private paths。

    :param prepared: 已校验且环境持久化已由调用方成功完成的 transaction。
    :returns: 已发布结果与不会触发 rollback 的 cleanup warnings。
    :raises InitWorkspaceError: snapshot、replace、durability 或 rollback 失败。
    :raises KeyboardInterrupt: publication fault 完整 rollback 后重新抛出。
    """

    request = prepared.request
    _require_prepared_identity(prepared)
    try:
        _require_snapshot_unchanged(request)
    except KeyboardInterrupt:
        abort_prepared_workspace_transaction(prepared)
        raise
    except OSError as exc:
        try:
            abort_prepared_workspace_transaction(prepared)
        except InitWorkspaceError as cleanup_error:
            raise cleanup_error from exc
        raise InitWorkspaceError(
            stage="managed_root_snapshot",
            message=(f"managed-root snapshot could not be read before publication: {exc.__class__.__name__}"),
            public_root_states=_public_root_truth(request),
        ) from exc
    except InitWorkspaceError as exc:
        if exc.retained_paths:
            raise
        try:
            abort_prepared_workspace_transaction(prepared)
        except InitWorkspaceError as cleanup_error:
            raise cleanup_error from exc
        raise
    backup_records: list[tuple[ManagedRootSnapshot, Path, PathIdentity]] = []
    public_config = request.workspace_root / _CONFIG_ROOT_NAME
    published_config = False
    try:
        for root_snapshot in _roots_replaced_by_mode(request):
            if not root_snapshot.exists:
                continue
            backup_path = request.workspace_root / (f"{_BACKUP_PREFIX}{uuid.uuid4().hex}-{root_snapshot.name}")
            try:
                os.replace(root_snapshot.path, backup_path)
            except (OSError, KeyboardInterrupt):
                if not _path_exists_no_follow(root_snapshot.path) and _path_exists_no_follow(backup_path):
                    moved_identity = _path_identity(
                        backup_path,
                        platform_system=request.platform_system,
                    )
                    if moved_identity == root_snapshot.identity:
                        backup_records.append((root_snapshot, backup_path, moved_identity))
                raise
            try:
                backup_identity = _path_identity(
                    backup_path,
                    platform_system=request.platform_system,
                )
            except (OSError, KeyboardInterrupt):
                if root_snapshot.identity is not None:
                    backup_records.append((root_snapshot, backup_path, root_snapshot.identity))
                raise
            backup_records.append((root_snapshot, backup_path, backup_identity))
            if backup_identity != root_snapshot.identity:
                raise InitWorkspaceError(
                    stage="publication_backup_identity",
                    message=("public managed-root identity changed at backup boundary"),
                    retained_paths=(backup_path, prepared.transaction_root),
                    public_root_states=_public_root_truth(request),
                )
        try:
            os.replace(prepared.staged_config_root, public_config)
        except (OSError, KeyboardInterrupt):
            if (
                not _path_exists_no_follow(prepared.staged_config_root)
                and _path_exists_no_follow(public_config)
                and _path_identity(
                    public_config,
                    platform_system=request.platform_system,
                )
                == prepared.staged_config_identity
            ):
                published_config = True
            raise
        published_config = True
        published_identity = _path_identity(
            public_config,
            platform_system=request.platform_system,
        )
        if published_identity != prepared.staged_config_identity:
            raise InitWorkspaceError(
                stage="publication_config_identity",
                message="published config identity changed at publication boundary",
                retained_paths=(public_config, prepared.transaction_root),
                public_root_states=_public_root_truth(request),
            )
        if request.platform_system in _POSIX_PLATFORMS:
            _sync_directory(request.workspace_root)
    except InitWorkspaceError as exc:
        _rollback_or_raise(
            prepared,
            backup_records=tuple(backup_records),
            published_config=published_config,
        )
        abort_prepared_workspace_transaction(prepared)
        raise InitWorkspaceError(
            stage=exc.stage,
            message=str(exc),
            public_root_states=_public_root_truth(request),
        ) from exc
    except KeyboardInterrupt:
        _rollback_or_raise(
            prepared,
            backup_records=tuple(backup_records),
            published_config=published_config,
        )
        abort_prepared_workspace_transaction(prepared)
        raise
    except OSError as exc:
        _rollback_or_raise(
            prepared,
            backup_records=tuple(backup_records),
            published_config=published_config,
        )
        abort_prepared_workspace_transaction(prepared)
        raise InitWorkspaceError(
            stage="publication",
            message=f"workspace publication failed: {exc.__class__.__name__}",
            public_root_states=_public_root_truth(request),
        ) from exc

    warnings: list[WorkspaceCleanupWarning] = []
    for _root_snapshot, backup_path, backup_identity in backup_records:
        warning = _post_publication_cleanup(
            backup_path,
            expected_identity=backup_identity,
            private_parent=request.workspace_root,
            platform_system=request.platform_system,
            stage="post_publication_backup_cleanup",
        )
        if warning is not None:
            warnings.append(warning)
    transaction_warning = _post_publication_cleanup(
        prepared.transaction_root,
        expected_identity=prepared.transaction_identity,
        private_parent=request.workspace_root,
        platform_system=request.platform_system,
        stage="post_publication_staging_cleanup",
    )
    if transaction_warning is not None:
        warnings.append(transaction_warning)
    if request.platform_system in _POSIX_PLATFORMS:
        try:
            _sync_directory(request.workspace_root)
        except (OSError, KeyboardInterrupt) as exc:
            warnings.append(
                WorkspaceCleanupWarning(
                    stage="post_publication_workspace_directory_sync",
                    path=prepared.transaction_root,
                    path_exists=False,
                    partial_deletion=False,
                    deletion_durability_unconfirmed=True,
                    error_type=exc.__class__.__name__,
                )
            )
    return WorkspaceTransactionResult(
        mode=request.mode,
        config_root=public_config,
        warnings=tuple(warnings),
        discovered_tool_count=prepared.discovered_tool_count,
        validated_scene_ids=prepared.validated_scene_ids,
    )


def _validate_request(request: WorkspaceTransactionRequest) -> None:
    """校验 transaction request 的 canonical identity 与平台。

    :param request: 待校验 request。
    :returns: None。
    :raises InitWorkspaceError: 平台、路径或 snapshot 不一致时抛出。
    """

    _validate_platform(request.platform_system)
    if not request.workspace_root.is_absolute():
        raise InitWorkspaceError(
            stage="workspace_identity",
            message="workspace root must be absolute",
        )
    if request.workspace_root.resolve(strict=True) != request.expected_snapshot.workspace_root:
        raise InitWorkspaceError(
            stage="workspace_identity",
            message="workspace root does not match the confirmed snapshot",
        )


def _validate_platform(platform_system: str) -> None:
    """限制 transaction 使用 fixed plan 明确支持的平台。

    :param platform_system: 标准平台值。
    :returns: None。
    :raises InitWorkspaceError: 平台不是 Windows/Linux/Darwin 时抛出。
    """

    if platform_system != _WINDOWS_PLATFORM and platform_system not in _POSIX_PLATFORMS:
        raise InitWorkspaceError(
            stage="platform",
            message=f"unsupported init workspace platform: {platform_system}",
        )


def _require_snapshot_unchanged(request: WorkspaceTransactionRequest) -> None:
    """在 mutation boundary 前重取并比较完整 managed-root snapshot。

    :param request: transaction request。
    :returns: None。
    :raises InitWorkspaceError: identity/content/type 发生漂移时抛出。
    """

    current = snapshot_managed_roots(
        request.workspace_root,
        platform_system=request.platform_system,
    )
    if current != request.expected_snapshot:
        raise InitWorkspaceError(
            stage="managed_root_snapshot",
            message="managed-root snapshot changed; rerun dayu-cli init",
            public_root_states=_snapshot_truth(current),
        )


def _build_staged_config(
    request: WorkspaceTransactionRequest,
    *,
    staged_config_root: Path,
) -> None:
    """按四态构造 private staging config tree。

    :param request: transaction request。
    :param staged_config_root: transaction-private config target。
    :returns: None。
    :raises InitWorkspaceError: package/public config 含不安全对象时抛出。
    :raises OSError: copy/mkdir/ENOSPC 等底层错误时抛出。
    """

    if request.mode is InitMode.PRESERVE:
        public_config = request.workspace_root / _CONFIG_ROOT_NAME
        _validate_ordinary_tree(
            public_config,
            platform_system=request.platform_system,
        )
        shutil.copytree(
            public_config,
            staged_config_root,
            symlinks=True,
        )
        _copy_missing_prompt_files(
            package_config_root=request.package_config_root,
            staged_config_root=staged_config_root,
            platform_system=request.platform_system,
        )
        return
    _copy_package_config_defaults(
        package_config_root=request.package_config_root,
        staged_config_root=staged_config_root,
        platform_system=request.platform_system,
    )


def _copy_package_config_defaults(
    *,
    package_config_root: Path,
    staged_config_root: Path,
    platform_system: str,
) -> None:
    """复制当前五配置文件与 prompt assets，不复制 package 开发文档。

    :param package_config_root: 当前 package config 真源。
    :param staged_config_root: transaction-private config target。
    :param platform_system: 明确平台值。
    :returns: None。
    :raises InitWorkspaceError: 必需源不是 ordinary file/tree 时抛出。
    :raises OSError: mkdir/copy 失败时抛出。
    """

    staged_config_root.mkdir()
    for file_name in config_file_names():
        source = package_config_root / file_name
        identity = _path_identity(source, platform_system=platform_system)
        if not stat.S_ISREG(identity.mode):
            raise InitWorkspaceError(
                stage="staging_copy",
                message=f"package config must be a regular file: {source}",
            )
        shutil.copy2(source, staged_config_root / file_name)
    package_prompts = package_config_root / _PROMPTS_ROOT_NAME
    _validate_ordinary_tree(package_prompts, platform_system=platform_system)
    shutil.copytree(
        package_prompts,
        staged_config_root / _PROMPTS_ROOT_NAME,
        symlinks=True,
    )


def _copy_missing_prompt_files(
    *,
    package_config_root: Path,
    staged_config_root: Path,
    platform_system: str,
) -> None:
    """PRESERVE 只补 package prompts 中缺失的普通文件。

    :param package_config_root: package config 真源。
    :param staged_config_root: 已复制的用户 config staging tree。
    :param platform_system: 明确平台值。
    :returns: None。
    :raises InitWorkspaceError: package prompt 含不安全对象时抛出。
    :raises OSError: 目录创建或文件复制失败时抛出。
    """

    package_prompts = package_config_root / _PROMPTS_ROOT_NAME
    _validate_ordinary_tree(package_prompts, platform_system=platform_system)
    for source in sorted(package_prompts.rglob("*")):
        source_identity = _path_identity(source, platform_system=platform_system)
        if stat.S_ISDIR(source_identity.mode):
            continue
        if not stat.S_ISREG(source_identity.mode):
            raise InitWorkspaceError(
                stage="staging_copy",
                message=f"package prompt asset must be a regular file: {source}",
            )
        relative_path = source.relative_to(package_config_root)
        destination = staged_config_root / relative_path
        if destination.exists() or destination.is_symlink():
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def _validate_staged_runtime(
    runtime_config: RuntimeConfig,
    *,
    public_workspace_root: Path,
    private_validation_root: Path,
    staged_config_root: Path,
) -> tuple[int, tuple[str, ...]]:
    """执行一次真实 Service discovery 并复用 catalog 校验 13 个 scenes。

    :param runtime_config: 真实 ConfigLoader 产出的 staging config。
    :param public_workspace_root: ordinary 非 Fins/Web effective 路径基准。
    :param private_validation_root: Fins side effect 的 canonical private root。
    :param staged_config_root: staging prompt/manifests 根。
    :returns: 工具数量与排序后的 13 个 scene ids。
    :raises Exception: Service discovery 或 scene public contract 失败时透传。
    """

    effective_configs = assemble_effective_tool_provider_configs(
        tuple(runtime_config.tool_discovery.providers.values()),
        workspace_root=public_workspace_root,
        fins_workspace_root_override=private_validation_root,
    )
    discovered_tools = discover_service_tools(effective_configs)
    catalog = SceneToolCatalog.from_tool_bundle(discovered_tools.tool_bundle)
    scene_ids = tuple(sorted(PRODUCTION_RUNTIME_MANIFEST_BASENAMES))
    for scene_id in scene_ids:
        prepare_scene(
            ScenePrepareRequest(
                scene_id=scene_id,
                scene_manifest_root=(staged_config_root / _PROMPTS_ROOT_NAME / _MANIFESTS_ROOT_NAME),
                prompt_asset_root=staged_config_root / _PROMPTS_ROOT_NAME,
                context_slot_values={
                    _CURRENT_TIME_SLOT: "",
                    _FINS_DEFAULT_SUBJECT_SLOT: "",
                },
                available_tools=catalog,
            )
        )
    return len(discovered_tools.tool_bundle.definitions), scene_ids


def _sync_staged_config(
    staged_config_root: Path,
    *,
    platform_system: str,
) -> None:
    """提交 staging 普通文件内容与 POSIX directory entries。

    :param staged_config_root: 待发布 config tree。
    :param platform_system: 明确平台值。
    :returns: None。
    :raises InitWorkspaceError: tree 含不安全对象时抛出。
    :raises OSError: open/fsync 失败时抛出。
    """

    _validate_ordinary_tree(staged_config_root, platform_system=platform_system)
    directories: list[Path] = [staged_config_root]
    regular_files: list[Path] = []
    for current_root, directory_names, file_names in os.walk(
        staged_config_root,
        topdown=True,
        followlinks=False,
    ):
        current_path = Path(current_root)
        directories.extend(current_path / name for name in directory_names)
        regular_files.extend(current_path / name for name in file_names)
    file_open_flags = _staged_file_sync_open_flags(platform_system)
    for file_path in sorted(regular_files):
        file_descriptor = os.open(file_path, file_open_flags)
        try:
            if not stat.S_ISREG(os.fstat(file_descriptor).st_mode):
                raise InitWorkspaceError(
                    stage="staging_file_sync",
                    message=f"staging file type changed before fsync: {file_path}",
                )
            os.fsync(file_descriptor)
        finally:
            os.close(file_descriptor)
    if platform_system in _POSIX_PLATFORMS:
        for directory in sorted(
            directories,
            key=lambda path: len(path.parts),
            reverse=True,
        ):
            _sync_directory(directory)


def _staged_file_sync_open_flags(platform_system: str) -> int:
    """返回当前平台可执行真实 staged-file flush 的打开标志。

    Windows 的 ``os.fsync`` 需要可写 descriptor；POSIX 继续以 no-follow
    只读 descriptor 提交普通文件内容，避免沿链接打开。

    :param platform_system: 明确的标准平台值。
    :returns: 传给 ``os.open`` 的平台专属标志。
    :raises InitWorkspaceError: 平台不受 init transaction 支持时抛出。
    """

    _validate_platform(platform_system)
    if platform_system == _WINDOWS_PLATFORM:
        return os.O_RDWR
    return _READ_ONLY_OPEN_FLAGS | os.O_NOFOLLOW


def _roots_replaced_by_mode(
    request: WorkspaceTransactionRequest,
) -> tuple[ManagedRootSnapshot, ...]:
    """返回当前模式需要移动到 backup 的 public roots。

    :param request: transaction request。
    :returns: 严格按 manifest 顺序排列的 roots。
    :raises Exception: 不主动抛出异常。
    """

    if request.mode is InitMode.RESET:
        return request.expected_snapshot.roots
    return (request.expected_snapshot.root(_CONFIG_ROOT_NAME),)


def _rollback_or_raise(
    prepared: PreparedWorkspaceTransaction,
    *,
    backup_records: tuple[tuple[ManagedRootSnapshot, Path, PathIdentity], ...],
    published_config: bool,
) -> None:
    """逆序恢复 publication 前 snapshot；失败时报告 public truth。

    :param prepared: transaction state。
    :param backup_records: 已成功移动的 roots 与 backup identity。
    :param published_config: staged config 是否已经到达 public path。
    :returns: None。
    :raises InitWorkspaceError: cleanup、restore 或 POSIX sync 失败时抛出。
    """

    request = prepared.request
    public_config = request.workspace_root / _CONFIG_ROOT_NAME
    try:
        if published_config:
            _cleanup_private_path(
                public_config,
                expected_identity=prepared.staged_config_identity,
                private_parent=request.workspace_root,
                platform_system=request.platform_system,
                stage="rollback_published_config_cleanup",
            )
        for root_snapshot, backup_path, backup_identity in reversed(backup_records):
            current_backup_identity = _path_identity(
                backup_path,
                platform_system=request.platform_system,
            )
            if current_backup_identity != backup_identity:
                raise InitWorkspaceError(
                    stage="rollback_backup_identity",
                    message=f"backup identity changed: {backup_path}",
                    retained_paths=(backup_path, prepared.transaction_root),
                    public_root_states=_public_root_truth(request),
                )
            try:
                os.replace(backup_path, root_snapshot.path)
            except (OSError, KeyboardInterrupt) as exc:
                raise InitWorkspaceError(
                    stage=f"restore_{root_snapshot.name}",
                    message=(f"managed-root restore failed: {exc.__class__.__name__}"),
                    retained_paths=(backup_path, prepared.transaction_root),
                    public_root_states=_public_root_truth(request),
                ) from exc
        if request.platform_system in _POSIX_PLATFORMS:
            try:
                _sync_directory(request.workspace_root)
            except (OSError, KeyboardInterrupt) as exc:
                raise InitWorkspaceError(
                    stage="workspace_directory_sync",
                    message=(f"rollback directory sync failed: {exc.__class__.__name__}"),
                    retained_paths=(prepared.transaction_root,),
                    public_root_states=_public_root_truth(request),
                    deletion_durability_unconfirmed=True,
                ) from exc
    except InitWorkspaceError as exc:
        retained = tuple(
            dict.fromkeys(
                (
                    *exc.retained_paths,
                    *(record[1] for record in backup_records),
                    prepared.transaction_root,
                )
            )
        )
        raise InitWorkspaceError(
            stage=(exc.stage if exc.stage.startswith("rollback_") else f"rollback_{exc.stage}"),
            message=str(exc),
            retained_paths=tuple(path for path in retained if _path_exists_no_follow(path)),
            public_root_states=_public_root_truth(request),
            partial_deletion=exc.partial_deletion,
            deletion_durability_unconfirmed=(exc.deletion_durability_unconfirmed),
        ) from exc
    except (OSError, KeyboardInterrupt) as exc:
        retained = tuple(
            path
            for path in (
                *(record[1] for record in backup_records),
                prepared.transaction_root,
            )
            if path.exists() or path.is_symlink()
        )
        raise InitWorkspaceError(
            stage="rollback",
            message=f"workspace rollback failed: {exc.__class__.__name__}",
            retained_paths=retained,
            public_root_states=_public_root_truth(request),
        ) from exc


def _require_prepared_identity(
    prepared: PreparedWorkspaceTransaction,
) -> None:
    """发布前复核 transaction container 与 staged config identity。

    :param prepared: transaction state。
    :returns: None。
    :raises InitWorkspaceError: identity/type/containment 漂移时抛出。
    """

    request = prepared.request
    try:
        transaction_identity = _path_identity(
            prepared.transaction_root,
            platform_system=request.platform_system,
        )
        staged_identity = _path_identity(
            prepared.staged_config_root,
            platform_system=request.platform_system,
        )
    except (OSError, KeyboardInterrupt) as exc:
        raise InitWorkspaceError(
            stage="prepared_identity",
            message=(f"prepared transaction identity could not be read: {exc.__class__.__name__}"),
            retained_paths=(prepared.transaction_root,),
        ) from exc
    if transaction_identity != prepared.transaction_identity or staged_identity != prepared.staged_config_identity:
        raise InitWorkspaceError(
            stage="prepared_identity",
            message="prepared transaction identity changed before publication",
            retained_paths=(prepared.transaction_root,),
        )
    _require_ordinary_directory(
        prepared.transaction_root,
        transaction_identity,
        platform_system=request.platform_system,
        stage="prepared_identity",
    )
    _require_ordinary_directory(
        prepared.staged_config_root,
        staged_identity,
        platform_system=request.platform_system,
        stage="prepared_identity",
    )
    _require_private_child(
        prepared.staged_config_root,
        private_parent=prepared.transaction_root,
        stage="prepared_identity",
    )


def _discard_private_container_or_raise(
    transaction_root: Path,
    *,
    expected_identity: PathIdentity,
    platform_system: str,
    stage: str,
) -> None:
    """安全删除未发布 transaction container，并保留失败真值。

    :param transaction_root: transaction-private root。
    :param expected_identity: 创建时 identity。
    :param platform_system: 明确平台值。
    :param stage: 调用方失败阶段。
    :returns: None。
    :raises InitWorkspaceError: identity/cleanup/durability 失败时抛出。
    """

    workspace_root = transaction_root.parent
    _cleanup_private_path(
        transaction_root,
        expected_identity=expected_identity,
        private_parent=workspace_root,
        platform_system=platform_system,
        stage=stage,
    )
    if platform_system in _POSIX_PLATFORMS:
        try:
            _sync_directory(workspace_root)
        except (OSError, KeyboardInterrupt) as exc:
            raise InitWorkspaceError(
                stage=f"{stage}_parent_directory_sync",
                message="private transaction deleted but parent sync failed",
                deletion_durability_unconfirmed=True,
            ) from exc


def _post_publication_cleanup(
    path: Path,
    *,
    expected_identity: PathIdentity,
    private_parent: Path,
    platform_system: str,
    stage: str,
) -> WorkspaceCleanupWarning | None:
    """执行 publication 后 cleanup，并把失败转成 warning。

    :param path: private backup/staging path。
    :param expected_identity: 创建/移动时 identity。
    :param private_parent: path 必须直接位于其中的 parent。
    :param platform_system: 明确平台值。
    :param stage: cleanup 阶段。
    :returns: 成功为 None；失败为 truthful warning。
    :raises Exception: cleanup 异常被投影成 warning，不主动抛出。
    """

    try:
        _cleanup_private_path(
            path,
            expected_identity=expected_identity,
            private_parent=private_parent,
            platform_system=platform_system,
            stage=stage,
        )
    except (InitWorkspaceError, OSError, KeyboardInterrupt) as exc:
        warning_path = path
        if isinstance(exc, InitWorkspaceError) and exc.retained_paths:
            warning_path = exc.retained_paths[0]
        return WorkspaceCleanupWarning(
            stage=stage,
            path=warning_path,
            path_exists=_path_exists_no_follow(warning_path),
            partial_deletion=(exc.partial_deletion if isinstance(exc, InitWorkspaceError) else True),
            deletion_durability_unconfirmed=(
                exc.deletion_durability_unconfirmed if isinstance(exc, InitWorkspaceError) else False
            ),
            error_type=_underlying_error_type(exc),
        )
    return None


def _underlying_error_type(exc: BaseException) -> str:
    """返回显式 exception cause chain 的最底层类型名。

    :param exc: transaction cleanup 捕获的异常。
    :returns: 最底层显式 cause 的类型名。
    :raises Exception: 不主动抛出异常。
    """

    current = exc
    while current.__cause__ is not None:
        current = current.__cause__
    return current.__class__.__name__


def _cleanup_private_path(
    path: Path,
    *,
    expected_identity: PathIdentity,
    private_parent: Path,
    platform_system: str,
    stage: str,
) -> None:
    """Identity-lock 后同父 quarantine 并 no-follow 删除 private tree。

    :param path: transaction 自己创建或移动的 private ordinary tree。
    :param expected_identity: owner 记录的精确 identity。
    :param private_parent: path 与 quarantine 的共同 parent。
    :param platform_system: 明确平台值。
    :param stage: diagnostic 阶段。
    :returns: None。
    :raises InitWorkspaceError: containment/identity/reparse/capability 或
        partial deletion 失败时抛出。
    """

    try:
        _require_private_child(path, private_parent=private_parent, stage=stage)
        actual_identity = _path_identity(path, platform_system=platform_system)
    except InitWorkspaceError:
        raise
    except (OSError, KeyboardInterrupt) as exc:
        raise InitWorkspaceError(
            stage=f"{stage}_identity",
            message=(f"private path identity could not be read: {exc.__class__.__name__}"),
            retained_paths=(path,) if _path_exists_no_follow(path) else (),
        ) from exc
    if actual_identity != expected_identity:
        raise InitWorkspaceError(
            stage=f"{stage}_identity",
            message=f"private path identity changed: {path}",
            retained_paths=(path,),
        )
    _require_ordinary_directory(
        path,
        actual_identity,
        platform_system=platform_system,
        stage=f"{stage}_identity",
    )
    quarantine = private_parent / f"{_QUARANTINE_PREFIX}{uuid.uuid4().hex}"
    try:
        os.replace(path, quarantine)
    except (OSError, KeyboardInterrupt) as exc:
        if not _path_exists_no_follow(path) and _path_exists_no_follow(quarantine):
            try:
                quarantine_identity = _path_identity(
                    quarantine,
                    platform_system=platform_system,
                )
            except (OSError, KeyboardInterrupt) as identity_error:
                raise InitWorkspaceError(
                    stage=f"{stage}_quarantine_identity",
                    message=(
                        f"quarantine completed but identity could not be read: {identity_error.__class__.__name__}"
                    ),
                    retained_paths=(quarantine,),
                ) from identity_error
            if quarantine_identity == expected_identity:
                raise InitWorkspaceError(
                    stage=f"{stage}_quarantine",
                    message=(f"private quarantine completed but boundary reported failure: {exc.__class__.__name__}"),
                    retained_paths=(quarantine,),
                ) from exc
        raise InitWorkspaceError(
            stage=f"{stage}_quarantine",
            message=f"private quarantine failed: {exc.__class__.__name__}",
            retained_paths=(path,),
        ) from exc
    try:
        quarantine_identity = _path_identity(
            quarantine,
            platform_system=platform_system,
        )
    except (OSError, KeyboardInterrupt) as exc:
        raise InitWorkspaceError(
            stage=f"{stage}_quarantine_identity",
            message=(f"quarantine identity could not be read: {exc.__class__.__name__}"),
            retained_paths=(quarantine,),
        ) from exc
    if quarantine_identity != expected_identity or path.exists() or path.is_symlink():
        raise InitWorkspaceError(
            stage=f"{stage}_quarantine_identity",
            message="quarantine identity or original-name absence check failed",
            retained_paths=(quarantine,),
        )
    try:
        if platform_system in _POSIX_PLATFORMS:
            if shutil.rmtree.avoids_symlink_attacks is not True:
                raise InitWorkspaceError(
                    stage=f"{stage}_capability",
                    message="POSIX fd-safe shutil.rmtree capability unavailable",
                    retained_paths=(quarantine,),
                )
        else:
            _validate_ordinary_tree(
                quarantine,
                platform_system=platform_system,
            )
        shutil.rmtree(quarantine)
    except InitWorkspaceError:
        raise
    except (OSError, KeyboardInterrupt) as exc:
        raise InitWorkspaceError(
            stage=f"{stage}_recursive_delete",
            message=f"private recursive delete failed: {exc.__class__.__name__}",
            retained_paths=(quarantine,) if quarantine.exists() else (),
            partial_deletion=True,
        ) from exc


def _require_private_child(
    path: Path,
    *,
    private_parent: Path,
    stage: str,
) -> None:
    """要求 private path 是 canonical parent 的直接 lexical/resolved child。

    :param path: 待校验 private path。
    :param private_parent: owner 记录的 parent。
    :param stage: diagnostic 阶段。
    :returns: None。
    :raises InitWorkspaceError: 非直接 child 或 containment 逃逸时抛出。
    """

    if path.parent != private_parent:
        raise InitWorkspaceError(
            stage=stage,
            message=f"private path must be direct child of owner parent: {path}",
        )
    resolved_parent = private_parent.resolve(strict=True)
    try:
        path.resolve(strict=True).relative_to(resolved_parent)
    except ValueError as exc:
        raise InitWorkspaceError(
            stage=stage,
            message=f"private path escapes owner parent: {path}",
        ) from exc


def _path_identity(path: Path, *, platform_system: str) -> PathIdentity:
    """读取单一路径的 no-follow identity。

    :param path: 待读取路径。
    :param platform_system: 明确平台值。
    :returns: 平台完整 identity。
    :raises OSError: 路径无法 no-follow stat 时抛出。
    """

    path_stat = os.stat(path, follow_symlinks=False)
    if platform_system == _WINDOWS_PLATFORM:
        windows_stat = cast(_WindowsStatResult, path_stat)
        return PathIdentity(
            device=path_stat.st_dev,
            inode=path_stat.st_ino,
            mode=path_stat.st_mode,
            file_attributes=windows_stat.st_file_attributes,
            reparse_tag=windows_stat.st_reparse_tag,
        )
    return PathIdentity(
        device=path_stat.st_dev,
        inode=path_stat.st_ino,
        mode=path_stat.st_mode,
        file_attributes=0,
        reparse_tag=0,
    )


def _path_exists_no_follow(path: Path) -> bool:
    """判断 lexical path 是否存在且不跟随最终 symlink。

    :param path: 待检查路径。
    :returns: ordinary/symlink/dangling symlink 存在时返回 True。
    :raises Exception: 权限或 I/O 错误按 fail-closed 的存在返回，不向上抛出。
    """

    try:
        os.stat(path, follow_symlinks=False)
    except FileNotFoundError:
        return False
    except OSError:
        return True
    return True


def _require_ordinary_directory(
    path: Path,
    identity: PathIdentity,
    *,
    platform_system: str,
    stage: str,
) -> None:
    """拒绝 root symlink/reparse 与非目录对象。

    :param path: 待校验路径。
    :param identity: no-follow identity。
    :param platform_system: 明确平台值。
    :param stage: diagnostic 阶段。
    :returns: None。
    :raises InitWorkspaceError: 对象不是 ordinary directory 时抛出。
    """

    if stat.S_ISLNK(identity.mode) or not stat.S_ISDIR(identity.mode):
        raise InitWorkspaceError(
            stage=stage,
            message=f"path must be an ordinary directory: {path}",
        )
    if platform_system == _WINDOWS_PLATFORM and identity.file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
        raise InitWorkspaceError(
            stage=stage,
            message=f"Windows reparse directory is not allowed: {path}",
        )


def _validate_ordinary_tree(root: Path, *, platform_system: str) -> None:
    """No-follow 扫描 ordinary tree，拒绝 nested link/reparse/special file。

    :param root: 已存在 tree root。
    :param platform_system: 明确平台值。
    :returns: None。
    :raises InitWorkspaceError: root/descendant 不安全时抛出。
    :raises OSError: scandir/stat 失败时抛出。
    """

    root_identity = _path_identity(root, platform_system=platform_system)
    _require_ordinary_directory(
        root,
        root_identity,
        platform_system=platform_system,
        stage="tree_identity",
    )
    pending: list[Path] = [root]
    while pending:
        directory = pending.pop()
        with os.scandir(directory) as entries:
            for entry in entries:
                entry_path = Path(entry.path)
                identity = _path_identity(
                    entry_path,
                    platform_system=platform_system,
                )
                if stat.S_ISLNK(identity.mode):
                    raise InitWorkspaceError(
                        stage="tree_identity",
                        message=(f"symlink is not allowed in managed/private tree: {entry_path}"),
                    )
                if (
                    platform_system == _WINDOWS_PLATFORM
                    and identity.file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT
                ):
                    raise InitWorkspaceError(
                        stage="tree_identity",
                        message=f"Windows reparse entry is not allowed: {entry_path}",
                    )
                if stat.S_ISDIR(identity.mode):
                    pending.append(entry_path)
                elif not stat.S_ISREG(identity.mode):
                    raise InitWorkspaceError(
                        stage="tree_identity",
                        message=(f"special file is not allowed in managed/private tree: {entry_path}"),
                    )


def _tree_digest(root: Path, *, platform_system: str) -> str:
    """计算 ordinary tree 的稳定路径/内容摘要。

    :param root: 已通过 no-follow tree 校验的根。
    :param platform_system: 明确平台值。
    :returns: lowercase SHA-256。
    :raises InitWorkspaceError: 读取期间对象类型漂移时抛出。
    :raises OSError: 文件读取失败时抛出。
    """

    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        identity = _path_identity(path, platform_system=platform_system)
        relative = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(identity.mode.to_bytes(8, "big", signed=False))
        if stat.S_ISREG(identity.mode):
            with path.open("rb") as stream:
                while chunk := stream.read(_FILE_READ_CHUNK_BYTES):
                    digest.update(chunk)
        elif not stat.S_ISDIR(identity.mode):
            raise InitWorkspaceError(
                stage="managed_root_digest",
                message=f"managed tree type changed during digest: {path}",
            )
    return digest.hexdigest()


def _sync_directory(path: Path) -> None:
    """POSIX fsync 单个 directory entry owner。

    :param path: 待提交 directory。
    :returns: None。
    :raises OSError: open/fsync 失败时抛出。
    """

    file_descriptor = os.open(
        path,
        _READ_ONLY_OPEN_FLAGS | os.O_NOFOLLOW | os.O_DIRECTORY,
    )
    try:
        if not stat.S_ISDIR(os.fstat(file_descriptor).st_mode):
            raise OSError(f"directory type changed before fsync: {path}")
        os.fsync(file_descriptor)
    finally:
        os.close(file_descriptor)


def _snapshot_truth(snapshot: WorkspaceSnapshot) -> tuple[str, ...]:
    """把 snapshot 投影为不含内容的 public root truth。

    :param snapshot: workspace snapshot。
    :returns: name=present/absent 元组。
    :raises Exception: 不主动抛出异常。
    """

    return tuple(f"{root.name}={'present' if root.exists else 'absent'}" for root in snapshot.roots)


def _public_root_truth(
    request: WorkspaceTransactionRequest,
) -> tuple[str, ...]:
    """失败路径读取当前 public managed-root existence truth。

    :param request: transaction request。
    :returns: 每个 manifest root 的存在性或 unknown。
    :raises Exception: 读取错误被投影为 unknown，不主动抛出。
    """

    truth: list[str] = []
    for root_name in MANAGED_ROOT_MANIFEST.root_names:
        path = request.workspace_root / root_name
        try:
            present = path.exists() or path.is_symlink()
        except OSError:
            truth.append(f"{root_name}=unknown")
        else:
            truth.append(f"{root_name}={'present' if present else 'absent'}")
    return tuple(truth)


__all__: tuple[str, ...] = (
    "InitMode",
    "InitWorkspaceError",
    "MANAGED_ROOT_MANIFEST",
    "ManagedRootManifest",
    "ManagedRootSnapshot",
    "PathIdentity",
    "PreparedWorkspaceTransaction",
    "WorkspaceCleanupWarning",
    "WorkspaceSnapshot",
    "WorkspaceTransactionRequest",
    "WorkspaceTransactionResult",
    "abort_prepared_workspace_transaction",
    "determine_init_mode",
    "prepare_workspace_transaction",
    "publish_workspace_transaction",
    "snapshot_managed_roots",
)
