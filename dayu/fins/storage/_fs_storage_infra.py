"""文件系统仓储基础设施层。

提供共享实例状态、批处理事务、路径方法、manifest 操作、handle 辅助等，
作为所有领域 mixin 的唯一基类。
"""

from __future__ import annotations

import hashlib
import os
import shutil
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO, Final, Optional, cast

from dayu.contracts.json_value import JsonValue
from dayu.fins._log import Log
from dayu.runtime.filelock import RuntimeFileLockTimeoutError, RuntimeFileLockToken, file_lock

from dayu.fins.domain.document_models import (
    BatchToken,
    FileObjectMeta,
    FilingManifestItem,
    MaterialManifestItem,
    ProcessedHandle,
    ProcessedManifestItem,
    SourceDocumentProvenance,
    SourceHandle,
    now_iso8601,
)
from dayu.fins.domain.enums import SourceKind

from .file_store import FileStore
from .local_file_store import LocalFileStore
from ._fs_storage_utils import (
    _DOWNLOAD_REJECTIONS_FILENAME,
    _PROCESSED_META_FILENAME,
    _REJECTED_FILINGS_DIRNAME,
    _SOURCE_META_FILENAME,
    _file_object_meta_from_dict,
    _fsync_directory,
    _normalize_document_id,
    _normalize_entry_name,
    _normalize_filename,
    _normalize_source_kind,
    _normalize_ticker,
    _read_json_object,
    _source_dir_name,
    _write_json,
)

_DAYU_DIRNAME = ".dayu"
_BATCH_ROOT_DIRNAME = "repo_batches"
_BACKUP_ROOT_DIRNAME = "repo_backups"
_LOCK_ROOT_DIRNAME = "batch_locks"
_RECOVERY_LOCK_FILENAME = "batch_recovery.lock"
_PUBLICATION_LOCK_SUFFIX = ".publication.lock"
_JOURNAL_FILENAME = "transaction.json"
_PHASE_STARTED = "started"
_PHASE_BACKED_UP_TARGET = "backed_up_target"
_PHASE_SWAPPED_TARGET = "swapped_target"
_PHASE_COMMITTED = "committed"
_PHASE_ROLLED_BACK = "rolled_back"
_BATCH_LIFECYCLE_OPEN = "open"
_BATCH_LIFECYCLE_COMMIT_STARTED = "commit_started"
_BATCH_LIFECYCLE_CLOSED = "closed"
_JOURNAL_FIELDS: Final[frozenset[str]] = frozenset({"transaction_id", "ticker", "phase"})
_RECOVERY_PHASES: Final[frozenset[str]] = frozenset(
    {
        _PHASE_STARTED,
        _PHASE_BACKED_UP_TARGET,
        _PHASE_SWAPPED_TARGET,
        _PHASE_COMMITTED,
        _PHASE_ROLLED_BACK,
    }
)


@dataclass(slots=True)
class _ActiveBatchState:
    """单个活动 filesystem transaction 的内部唯一状态。"""

    token: BatchToken
    lifecycle: str
    writer_lock_token: RuntimeFileLockToken
    target_ticker_dir: Path
    staging_root_dir: Path
    staging_ticker_dir: Path
    backup_dir: Path
    journal_path: Path
    phase: str


@dataclass(frozen=True, slots=True)
class _PublicationGuardedBinaryOpener:
    """在 publication guard 内打开稳定文件描述符的延迟 opener。"""

    lock_path: Path

    def __call__(self, path: Path, /) -> BinaryIO:
        """在 publication guard 内打开文件并立即释放 guard。

        Args:
            path: 待打开的 published 文件路径。

        Returns:
            已打开的二进制只读流。

        Raises:
            OSError: 文件打开失败时抛出。
            RuntimeFileLockError: publication guard 获取或释放失败时抛出。
        """

        guard_token = file_lock(self.lock_path).acquire()
        try:
            return path.open("rb")
        finally:
            guard_token.release()


def _hash_regular_file_sha256(path: Path) -> str:
    """流式计算 physical regular file 的 SHA-256。

    Args:
        path: 已通过 containment 与 regular-file 校验的文件路径。

    Returns:
        64 位小写十六进制摘要。

    Raises:
        OSError: 文件打开或读取失败时抛出。
    """

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(64 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _parse_backup_directory_name(name: str) -> tuple[str, str] | None:
    """解析备份目录名中的 ticker 与 token。

    Args:
        name: 备份目录名。

    Returns:
        成功时返回 `(ticker, token_id)`，否则返回 `None`。

    Raises:
        无。
    """

    ticker, separator, token_id = name.rpartition(".bak.")
    if not separator or not ticker or not token_id:
        return None
    return ticker, token_id


def _is_contained_recovery_path(path: Path, root: Path) -> bool:
    """判断 recovery locator 是否位于固定 root 内且路径链不含 symlink。

    Args:
        path: 待校验的派生 locator。
        root: storage owner 固定根目录。

    Returns:
        locator 受 root containment 约束且现存路径链不含 symlink 时返回 ``True``。

    Raises:
        OSError: 路径解析或 symlink 检查失败时抛出。
    """

    normalized_root = root.resolve(strict=False)
    normalized_path = path.resolve(strict=False)
    try:
        normalized_path.relative_to(normalized_root)
    except ValueError:
        return False
    current = path
    while current != root:
        if current.is_symlink():
            return False
        parent = current.parent
        if parent == current:
            return False
        current = parent
    return not root.is_symlink()


class _FsStorageInfra:
    """文件系统仓储基础设施基类。

    提供共享状态、批处理事务、路径解析、manifest 操作与 handle 辅助，
    所有领域 mixin 均继承自此类。
    """

    MODULE = "FINS.FS_REPOSITORY"

    def __init__(
        self,
        workspace_root: Path,
        file_store: Optional[FileStore] = None,
        *,
        create_directories: bool = True,
    ) -> None:
        """初始化仓储基础设施。

        Args:
            workspace_root: 工作区根目录。
            file_store: 可选文件存储实现（默认本地文件系统）。
            create_directories: 是否在初始化时创建仓储根目录。

        Returns:
            无。

        Raises:
            OSError: 目录创建失败时抛出。
        """

        self.workspace_root = workspace_root.resolve()
        self.portfolio_root = self.workspace_root / "portfolio"
        self.dayu_root = self.workspace_root / _DAYU_DIRNAME
        self.batch_root = self.dayu_root / _BATCH_ROOT_DIRNAME
        self.backup_root = self.dayu_root / _BACKUP_ROOT_DIRNAME
        self._batch_lock_root = self.dayu_root / _LOCK_ROOT_DIRNAME
        self._recovery_lock_path = self.dayu_root / _RECOVERY_LOCK_FILENAME
        self._create_directories = create_directories
        self._batch_recovery_completed = False
        self._active_batches: dict[str, _ActiveBatchState] = {}
        self._active_transaction_by_ticker: dict[str, str] = {}
        self._file_store = file_store
        if create_directories:
            self.portfolio_root.mkdir(parents=True, exist_ok=True)
            self._ensure_batch_storage_dirs()

    def ensure_batch_recovery(self) -> tuple[str, ...]:
        """确保当前工作区的 batch 孤儿状态已完成一次恢复。

        Args:
            无。

        Returns:
            本次恢复执行的动作摘要。

        Raises:
            OSError: 恢复过程访问文件系统失败时抛出。
        """

        if self._batch_recovery_completed:
            return ()
        actions = self.recover_orphan_batches()
        self._batch_recovery_completed = True
        return actions

    # ========== 批处理事务 ==========

    def begin_batch(self, ticker: str) -> BatchToken:
        """开启 ticker 级批处理事务并取得唯一 writer capability。

        Args:
            ticker: 股票代码。

        Returns:
            批处理 token。

        Raises:
            ValueError: ticker 非法时抛出。
            RuntimeError: 同一 ticker 已存在活动事务时抛出。
            RuntimeFileLockError: writer lock 获取或初始化失败后的释放失败时抛出。
            OSError: 暂存目录准备失败时抛出。
        """

        normalized_ticker = _normalize_ticker(ticker)
        if normalized_ticker in self._active_transaction_by_ticker:
            raise RuntimeError(f"ticker={normalized_ticker} 已存在活动 batch")

        self._ensure_batch_storage_dirs()
        self.ensure_batch_recovery()
        lock_token = self._acquire_ticker_lock(normalized_ticker)
        transaction_id = uuid.uuid4().hex
        target_ticker_dir = self._target_ticker_dir(normalized_ticker)
        staging_root_dir = self.batch_root / transaction_id
        staging_ticker_dir = staging_root_dir / normalized_ticker
        backup_dir = self.backup_root / f"{target_ticker_dir.name}.bak.{transaction_id}"
        journal_path = staging_root_dir / _JOURNAL_FILENAME
        token = BatchToken(
            transaction_id=transaction_id,
            ticker=normalized_ticker,
        )
        state = _ActiveBatchState(
            token=token,
            lifecycle=_BATCH_LIFECYCLE_OPEN,
            writer_lock_token=lock_token,
            target_ticker_dir=target_ticker_dir,
            staging_root_dir=staging_root_dir,
            staging_ticker_dir=staging_ticker_dir,
            backup_dir=backup_dir,
            journal_path=journal_path,
            phase=_PHASE_STARTED,
        )
        try:
            self._write_batch_journal(state, _PHASE_STARTED)
            if target_ticker_dir.exists():
                shutil.copytree(target_ticker_dir, staging_ticker_dir)
            else:
                self._ensure_ticker_structure(staging_ticker_dir)
        except Exception:
            shutil.rmtree(staging_root_dir, ignore_errors=True)
            self._release_lock_token(lock_token)
            raise

        self._active_batches[transaction_id] = state
        self._active_transaction_by_ticker[normalized_ticker] = transaction_id
        return token

    def commit_batch(self, batch: BatchToken) -> None:
        """提交批处理事务，并在任一 terminal 路径消费 capability。

        Args:
            batch: 显式批处理 capability。

        Returns:
            无。

        Raises:
            ValueError: token 非当前活动事务时抛出。
            OSError: physical swap、journal 或 pre-commit restore 失败时抛出。
            RuntimeFileLockError: 没有更早 operation error 且 publication/writer lock
                获取或释放失败时抛出；``COMMITTED`` 后 publication release failure
                作为 post-commit 主异常抛出且不回滚 durable tree，后续 cleanup/writer
                release failure 只附着为诊断。
        """

        state = self._resolve_active_batch(batch, batch.ticker)
        state.lifecycle = _BATCH_LIFECYCLE_COMMIT_STARTED
        commit_error: Exception | None = None
        rollback_error: Exception | None = None
        post_commit_error: Exception | None = None
        publication_token: RuntimeFileLockToken | None = None
        try:
            # 复杂逻辑说明：完整性校验只读 transaction staging，必须先于 publication guard。
            self._validate_complete_source_tree(state)
            publication_token = self._acquire_publication_guard(state.token.ticker)
            try:
                # 复杂逻辑说明：publication guard 只覆盖 published tree 的物理切换与失败恢复。
                if state.target_ticker_dir.exists():
                    self._replace_directory(state.target_ticker_dir, state.backup_dir)
                self._write_batch_journal(state, _PHASE_BACKED_UP_TARGET)
                self._replace_directory(state.staging_ticker_dir, state.target_ticker_dir)
                self._write_batch_journal(state, _PHASE_SWAPPED_TARGET)
                self._write_batch_journal(state, _PHASE_COMMITTED)
            except Exception as exc:
                commit_error = exc
                try:
                    self._rollback_precommit_batch(state)
                except Exception as rollback_exc:
                    rollback_error = rollback_exc
            finally:
                if publication_token is not None:
                    try:
                        self._release_lock_token(publication_token)
                    except Exception as release_error:
                        if commit_error is not None:
                            commit_error.add_note(
                                "publication guard release failed: "
                                f"{release_error.__class__.__name__}: {release_error}"
                            )
                        elif state.phase == _PHASE_COMMITTED:
                            post_commit_error = release_error
                            Log.warn(
                                "commit_batch 已 durable 提交但 publication guard 释放失败，"
                                "将作为 post-commit terminal error 抛出: "
                                f"ticker={state.token.ticker}",
                                module=self.MODULE,
                            )
                        else:
                            commit_error = release_error
        except Exception as exc:
            commit_error = exc
            try:
                self._rollback_precommit_batch(state)
            except Exception as rollback_exc:
                rollback_error = rollback_exc
        if commit_error is not None:
            self._close_active_batch(state, primary_error=commit_error)
            if rollback_error is not None:
                commit_error.add_note(
                    "commit_batch rollback failed; journal/backup/staging recovery evidence retained"
                )
                Log.warn(
                    f"commit_batch 与 rollback 均失败，已保留恢复证据: ticker={state.token.ticker}",
                    module=self.MODULE,
                )
                raise commit_error from rollback_error
            Log.warn(
                f"commit_batch 失败，已恢复提交前状态: ticker={state.token.ticker}",
                module=self.MODULE,
            )
            raise commit_error
        cleanup_error: Exception | None = None
        try:
            self._cleanup_committed_batch(state)
        except Exception as exc:
            cleanup_error = exc
        terminal_error = post_commit_error
        if cleanup_error is not None:
            if terminal_error is None:
                terminal_error = cleanup_error
            else:
                terminal_error.add_note(
                    "post-commit cleanup failed after publication guard release failure: "
                    f"{cleanup_error.__class__.__name__}: {cleanup_error}"
                )
                Log.warn(
                    "publication guard 释放主异常后 post-commit cleanup 失败，"
                    "已保留最早主异常: "
                    f"ticker={state.token.ticker} "
                    f"error_type={cleanup_error.__class__.__name__}",
                    module=self.MODULE,
                )
        # cleanup 属于已提交后的非权威收尾；无论其是否异常，capability 都必须进入终态。
        self._close_active_batch(state, primary_error=terminal_error)
        if terminal_error is not None:
            raise terminal_error

    def _validate_complete_source_tree(self, state: _ActiveBatchState) -> None:
        """校验完整 staged ticker tree 中全部 source publication facts。

        Args:
            state: 已进入 commit-started 的内部 transaction state。

        Returns:
            无。

        Raises:
            ValueError: source meta、provenance、files、primary 或 manifest 不满足完整发布契约时抛出。
            OSError: staging tree 读取或文件摘要计算失败时抛出。
        """

        staging_ticker_dir = state.staging_ticker_dir
        if staging_ticker_dir.is_symlink() or not staging_ticker_dir.is_dir():
            raise ValueError("complete source staging ticker root 必须为非 symlink 目录")
        self._require_contained_path(
            staging_ticker_dir,
            state.staging_root_dir,
            label="staging ticker root",
        )
        if staging_ticker_dir.name != state.token.ticker:
            raise ValueError("complete source staging ticker 目录与 transaction ticker 不一致")
        for source_kind in (SourceKind.FILING, SourceKind.MATERIAL):
            self._validate_complete_source_kind_tree(state, source_kind)

    def _validate_complete_source_kind_tree(
        self,
        state: _ActiveBatchState,
        source_kind: SourceKind,
    ) -> None:
        """校验一种 source kind 的目录、manifest 与完整 source 双向关系。

        Args:
            state: 当前 commit 的内部 transaction state。
            source_kind: filing 或 material。

        Returns:
            无。

        Raises:
            ValueError: source root、manifest 或 source 业务事实非法时抛出。
            OSError: staging tree 读取失败时抛出。
        """

        source_root = state.staging_ticker_dir / _source_dir_name(source_kind)
        if not source_root.exists() and not source_root.is_symlink():
            return
        if source_root.is_symlink() or not source_root.is_dir():
            raise ValueError(f"{source_kind.value} source root 必须为非 symlink 目录")
        self._require_contained_path(
            source_root,
            state.staging_ticker_dir,
            label=f"{source_kind.value} source root",
        )
        manifest_name = (
            "filing_manifest.json"
            if source_kind is SourceKind.FILING
            else "material_manifest.json"
        )
        manifest_path = source_root / manifest_name
        source_directories: dict[str, Path] = {}
        for child in source_root.iterdir():
            if child.is_symlink():
                raise ValueError(f"source root 禁止 symlink 条目: {child.name}")
            if child.name == manifest_name:
                continue
            if (
                source_kind is SourceKind.FILING
                and child.name == _DOWNLOAD_REJECTIONS_FILENAME
            ):
                continue
            if (
                source_kind is SourceKind.FILING
                and child.name == _REJECTED_FILINGS_DIRNAME
            ):
                continue
            if not child.is_dir():
                raise ValueError(f"source root 存在非法非目录条目: {child.name}")
            document_id = _normalize_document_id(child.name)
            if document_id != child.name:
                raise ValueError(f"source 目录名不是 canonical document_id: {child.name}")
            source_directories[document_id] = child

        manifest_items = self._read_complete_source_manifest(
            manifest_path,
            state.token.ticker,
        )
        source_ids = set(source_directories)
        manifest_ids = set(manifest_items)
        missing_manifest_ids = sorted(source_ids - manifest_ids)
        if missing_manifest_ids:
            raise ValueError(
                f"source 缺少 manifest 项目: {','.join(missing_manifest_ids)}"
            )
        dangling_manifest_ids = sorted(manifest_ids - source_ids)
        if dangling_manifest_ids:
            raise ValueError(
                f"manifest 存在 dangling source: {','.join(dangling_manifest_ids)}"
            )

        for document_id, source_dir in source_directories.items():
            meta = self._validate_complete_source_directory(
                state,
                source_kind,
                document_id,
                source_dir,
            )
            expected_manifest_item = (
                FilingManifestItem.from_source_meta(meta).to_dict()
                if source_kind is SourceKind.FILING
                else MaterialManifestItem.from_source_meta(meta).to_dict()
            )
            if manifest_items[document_id] != expected_manifest_item:
                raise ValueError(
                    "source 与 manifest 的 identity/provenance/completion 投影不一致: "
                    f"{source_kind.value}/{document_id}"
                )

    def _read_complete_source_manifest(
        self,
        manifest_path: Path,
        ticker: str,
    ) -> dict[str, dict[str, JsonValue]]:
        """读取并校验 commit validator 使用的 ticker manifest。

        Args:
            manifest_path: filing 或 material manifest 路径。
            ticker: 当前 transaction ticker。

        Returns:
            以 canonical document ID 为键的 manifest 项目。

        Raises:
            ValueError: manifest 路径、ticker、documents 或条目非法时抛出。
            OSError: manifest 读取失败时抛出。
        """

        if not manifest_path.exists():
            return {}
        if manifest_path.is_symlink() or not manifest_path.is_file():
            raise ValueError(f"source manifest 必须为 regular file: {manifest_path.name}")
        manifest = cast(dict[str, JsonValue], _read_json_object(manifest_path))
        if manifest.get("ticker") != ticker:
            raise ValueError("source manifest ticker 与 transaction ticker 不一致")
        raw_documents = manifest.get("documents")
        if not isinstance(raw_documents, list):
            raise ValueError("source manifest documents 必须为数组")
        items: dict[str, dict[str, JsonValue]] = {}
        for raw_item in raw_documents:
            if not isinstance(raw_item, Mapping):
                raise ValueError("source manifest documents 条目必须为 object")
            item = dict(raw_item)
            raw_document_id = item.get("document_id")
            if not isinstance(raw_document_id, str):
                raise ValueError("source manifest document_id 必须为字符串")
            document_id = _normalize_document_id(raw_document_id)
            if document_id != raw_document_id:
                raise ValueError("source manifest document_id 必须为 canonical identity")
            if document_id in items:
                raise ValueError(f"source manifest document_id 重复: {document_id}")
            items[document_id] = cast(dict[str, JsonValue], item)
        return items

    def _validate_complete_source_directory(
        self,
        state: _ActiveBatchState,
        source_kind: SourceKind,
        document_id: str,
        source_dir: Path,
    ) -> dict[str, JsonValue]:
        """校验单个 staged source 的 meta、provenance、files 与 primary。

        Args:
            state: 当前 commit 的内部 transaction state。
            source_kind: source 目录类型。
            document_id: 目录对应的 canonical document ID。
            source_dir: staged source 目录。

        Returns:
            已解析且完成态为真的 source meta。

        Raises:
            ValueError: source 业务事实、物理文件或 containment 非法时抛出。
            OSError: meta 或业务文件读取失败时抛出。
        """

        self._require_contained_path(
            source_dir,
            state.staging_ticker_dir,
            label=f"{source_kind.value} source directory",
        )
        meta_path = source_dir / _SOURCE_META_FILENAME
        if not meta_path.exists():
            raise ValueError(f"complete source 缺少 meta.json: {source_kind.value}/{document_id}")
        if meta_path.is_symlink() or not meta_path.is_file():
            raise ValueError(f"complete source meta 必须为 regular file: {document_id}")
        meta = cast(dict[str, JsonValue], _read_json_object(meta_path))
        if meta.get("ticker") != state.token.ticker:
            raise ValueError(f"source meta ticker 与目录不一致: {document_id}")
        if meta.get("document_id") != document_id:
            raise ValueError(f"source meta document_id 与目录不一致: {document_id}")
        if meta.get("source_kind") != source_kind.value:
            raise ValueError(f"source meta source_kind 与目录不一致: {document_id}")
        provenance = SourceDocumentProvenance.from_meta(meta, source_kind)
        if not provenance.ingest_complete:
            raise ValueError(f"source meta 禁止 false completion: {document_id}")
        file_names = self._validate_complete_source_files(
            state,
            source_kind,
            document_id,
            source_dir,
            meta,
        )
        primary_document = meta.get("primary_document")
        if not isinstance(primary_document, str) or not primary_document.strip():
            raise ValueError(f"complete source primary_document 不能为空: {document_id}")
        normalized_primary = _normalize_filename(primary_document)
        if normalized_primary != primary_document or normalized_primary not in file_names:
            raise ValueError(f"primary_document 未精确命中 files: {document_id}")
        return meta

    def _validate_complete_source_files(
        self,
        state: _ActiveBatchState,
        source_kind: SourceKind,
        document_id: str,
        source_dir: Path,
        meta: Mapping[str, JsonValue],
    ) -> set[str]:
        """校验 source files manifest 与同目录 physical regular files 同源。

        Args:
            state: 当前 commit 的内部 transaction state。
            source_kind: source 目录类型。
            document_id: 当前 source 文档 ID。
            source_dir: staged source 目录。
            meta: 已解析 source meta。

        Returns:
            已校验且唯一的业务文件名集合。

        Raises:
            ValueError: files 为空、重复、dangling、越界或元数据不匹配时抛出。
            OSError: 文件 stat 或摘要计算失败时抛出。
        """

        raw_files = meta.get("files")
        if not isinstance(raw_files, list) or not raw_files:
            raise ValueError(f"complete source files 必须为非空数组: {document_id}")
        file_names: set[str] = set()
        for raw_file in raw_files:
            if not isinstance(raw_file, Mapping):
                raise ValueError(f"source files 条目必须为 object: {document_id}")
            raw_name = raw_file.get("name")
            if not isinstance(raw_name, str):
                raise ValueError(f"source file.name 必须为字符串: {document_id}")
            name = _normalize_filename(raw_name)
            if name != raw_name or name == _SOURCE_META_FILENAME:
                raise ValueError(f"source file.name 非法: {document_id}/{raw_name}")
            if name in file_names:
                raise ValueError(f"source files 业务文件名重复: {document_id}/{name}")
            file_names.add(name)
            physical_path = source_dir / name
            self._require_contained_regular_file(
                physical_path,
                source_dir,
                label=f"source file {document_id}/{name}",
            )
            expected_uri = (
                f"local://{state.token.ticker}/{_source_dir_name(source_kind)}/"
                f"{document_id}/{name}"
            )
            if raw_file.get("uri") != expected_uri:
                raise ValueError(f"source file.uri 与 staged physical file 不一致: {document_id}/{name}")
            raw_size = raw_file.get("size")
            if raw_size is not None:
                if isinstance(raw_size, bool) or not isinstance(raw_size, int) or raw_size < 0:
                    raise ValueError(f"source file.size 必须为非负整数: {document_id}/{name}")
                if physical_path.stat().st_size != raw_size:
                    raise ValueError(f"source file.size 与 physical file 不一致: {document_id}/{name}")
            raw_sha256 = raw_file.get("sha256")
            if raw_sha256 is not None:
                if not isinstance(raw_sha256, str) or not raw_sha256:
                    raise ValueError(f"source file.sha256 必须为非空字符串: {document_id}/{name}")
                if _hash_regular_file_sha256(physical_path) != raw_sha256:
                    raise ValueError(f"source file.sha256 与 physical file 不一致: {document_id}/{name}")

        physical_file_names: set[str] = set()
        for child in source_dir.iterdir():
            if child.name == _SOURCE_META_FILENAME:
                continue
            if child.is_symlink() or not child.is_file():
                raise ValueError(f"source 目录只允许 manifest 声明的 regular file: {child.name}")
            self._require_contained_path(
                child,
                state.staging_ticker_dir,
                label=f"source physical file {document_id}/{child.name}",
            )
            physical_file_names.add(child.name)
        if physical_file_names != file_names:
            raise ValueError(f"source files 与 physical business files 不双向一致: {document_id}")
        return file_names

    def _require_contained_regular_file(
        self,
        path: Path,
        root: Path,
        *,
        label: str,
    ) -> None:
        """要求路径是 root 内非 symlink 的 physical regular file。

        Args:
            path: 待校验文件路径。
            root: storage owner 预期根目录。
            label: 错误信息中的业务定位标签。

        Returns:
            无。

        Raises:
            ValueError: 路径越界、缺失、为 symlink 或非 regular file 时抛出。
        """

        self._require_contained_path(path, root, label=label)
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"{label} 必须为存在的 non-symlink regular file")

    def _require_contained_path(
        self,
        path: Path,
        root: Path,
        *,
        label: str,
    ) -> None:
        """要求解析后的路径仍位于 storage owner 指定 root 内。

        Args:
            path: 待校验路径。
            root: storage owner 根目录。
            label: 错误信息中的业务定位标签。

        Returns:
            无。

        Raises:
            ValueError: root 或 path 经解析后发生 containment escape 时抛出。
            OSError: 路径解析失败时抛出。
        """

        if root.is_symlink():
            raise ValueError(f"{label} root 禁止 symlink")
        resolved_root = root.resolve(strict=False)
        resolved_path = path.resolve(strict=False)
        try:
            resolved_path.relative_to(resolved_root)
        except ValueError as exc:
            raise ValueError(f"{label} 越出 staging root") from exc

    def _replace_directory(self, source: Path, target: Path) -> None:
        """原子移动目录并刷新受影响的父目录。

        Args:
            source: 当前存在的源目录。
            target: 尚不存在的目标目录。

        Returns:
            无。

        Raises:
            OSError: target已存在、目标目录准备、原子移动或目录访问失败时抛出。
        """

        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() or target.is_symlink():
            raise OSError(f"directory replace target 已存在: {target}")
        source_parent = source.parent
        target_parent = target.parent
        os.replace(source, target)
        _fsync_directory(source_parent)
        if target_parent != source_parent:
            _fsync_directory(target_parent)

    def _remove_directory(self, path: Path) -> None:
        """删除目录并刷新其父目录。

        Args:
            path: 要删除的目录。

        Returns:
            无。

        Raises:
            OSError: 目录删除失败时抛出。
        """

        parent = path.parent
        shutil.rmtree(path)
        _fsync_directory(parent)

    def _rollback_precommit_batch(self, state: _ActiveBatchState) -> None:
        """把尚未到达 ``COMMITTED`` 的物理目录恢复到提交前状态。

        Args:
            state: 正在提交的内部 batch state。

        Returns:
            无。

        Raises:
            OSError: new target 撤回、backup 恢复、journal 写入或证据清理失败时抛出。
        """

        target_dir = state.target_ticker_dir
        staging_dir = state.staging_ticker_dir
        backup_dir = state.backup_dir
        if not staging_dir.exists() and target_dir.exists():
            # new target 尚未 committed；先移回 staging，既撤销可见状态又保留失败证据。
            self._replace_directory(target_dir, staging_dir)
        if backup_dir.exists():
            if target_dir.exists():
                raise OSError("rollback target 已存在，无法安全恢复 backup")
            self._replace_directory(backup_dir, target_dir)
        self._write_batch_journal(state, _PHASE_ROLLED_BACK)
        self._remove_directory(state.staging_root_dir)

    def _cleanup_committed_batch(self, state: _ActiveBatchState) -> None:
        """清理已提交 batch 的 backup 与 journal container。

        Args:
            state: 已 durable 写入 ``COMMITTED`` 的内部 batch state。

        Returns:
            无。cleanup 失败只记录诊断并保留恢复证据。

        Raises:
            无。
        """

        try:
            if state.backup_dir.exists():
                self._remove_directory(state.backup_dir)
            if state.staging_root_dir.exists():
                self._remove_directory(state.staging_root_dir)
        except OSError as cleanup_error:
            Log.warn(
                "commit_batch 已提交但 cleanup 失败，保留 orphan recovery 证据: "
                f"ticker={state.token.ticker} error_type={cleanup_error.__class__.__name__}",
                module=self.MODULE,
            )

    def rollback_batch(self, batch: BatchToken) -> None:
        """回滚批处理事务，并在任一 terminal 路径消费 capability。

        Args:
            batch: 显式批处理 capability。

        Returns:
            无。

        Raises:
            ValueError: token 非当前活动事务时抛出。
            OSError: rollback journal 写入失败时抛出；staging 仍清理且 capability
                仍终态消费。
            RuntimeFileLockError: 没有更早 rollback error 且 writer lock 释放失败时
                抛出；已有主异常时 release failure 只附着为诊断。
        """

        state = self._resolve_active_batch(batch, batch.ticker)
        state.lifecycle = _BATCH_LIFECYCLE_CLOSED
        rollback_error: Exception | None = None
        try:
            self._write_batch_journal(state, _PHASE_ROLLED_BACK)
        except Exception as exc:
            rollback_error = exc
            Log.warn(
                "rollback_batch 写入 journal 失败，但仍继续清理 staging 与释放锁: "
                f"ticker={state.token.ticker}",
                module=self.MODULE,
            )
        finally:
            try:
                shutil.rmtree(state.staging_root_dir, ignore_errors=True)
            finally:
                self._close_active_batch(state, primary_error=rollback_error)
        if rollback_error is not None:
            raise rollback_error

    def _resolve_active_batch(
        self,
        batch: BatchToken,
        ticker: str,
    ) -> _ActiveBatchState:
        """解析并校验显式 batch capability。

        Args:
            batch: 调用方显式传入的 batch capability。
            ticker: 本次 mutation 或 lifecycle 请求的 ticker。

        Returns:
            当前 core 登记且仍开放的内部 transaction state。

        Raises:
            ValueError: transaction 未登记、已关闭、ticker 不匹配或来自其它 core 时抛出。
        """

        normalized_ticker = _normalize_ticker(ticker)
        normalized_batch_ticker = _normalize_ticker(batch.ticker)
        transaction_id = batch.transaction_id.strip()
        if not transaction_id:
            raise ValueError("无效的 batch token：transaction_id 不能为空")
        state = self._active_batches.get(transaction_id)
        if state is None:
            raise ValueError("无效的 batch token：transaction 未在当前 storage core 登记")
        canonical_token = BatchToken(
            transaction_id=state.token.transaction_id,
            ticker=state.token.ticker,
        )
        supplied_token = BatchToken(
            transaction_id=transaction_id,
            ticker=normalized_batch_ticker,
        )
        if canonical_token != supplied_token:
            raise ValueError("无效的 batch token：canonical capability 不匹配")
        if normalized_batch_ticker != normalized_ticker:
            raise ValueError("无效的 batch token：ticker 与 mutation scope 不匹配")
        if state.lifecycle != _BATCH_LIFECYCLE_OPEN:
            raise ValueError("无效的 batch token：transaction 已进入终态")
        return state

    def _close_active_batch(
        self,
        state: _ActiveBatchState,
        *,
        primary_error: Exception | None = None,
    ) -> None:
        """关闭 transaction registry 并释放 writer mutex。

        Args:
            state: 已被 lifecycle 消费的内部 transaction state。
            primary_error: terminal operation 已产生的 authoritative 主异常；存在时 release
                failure 只作为附加诊断保留。

        Returns:
            无。

        Raises:
            RuntimeFileLockError: writer mutex 释放失败且没有更早主异常时抛出。
        """

        state.lifecycle = _BATCH_LIFECYCLE_CLOSED
        self._active_batches.pop(state.token.transaction_id, None)
        indexed_transaction_id = self._active_transaction_by_ticker.get(state.token.ticker)
        if indexed_transaction_id == state.token.transaction_id:
            self._active_transaction_by_ticker.pop(state.token.ticker, None)
        try:
            self._release_lock_token(state.writer_lock_token)
        except Exception as release_error:
            if primary_error is None:
                raise
            primary_error.add_note(
                "writer mutex release failed during terminal cleanup: "
                f"{release_error.__class__.__name__}: {release_error}"
            )
            Log.warn(
                "transaction 主异常后 writer mutex 释放失败，已消费 capability 并保留主异常: "
                f"ticker={state.token.ticker} error_type={release_error.__class__.__name__}",
                module=self.MODULE,
            )

    def recover_orphan_batches(self, *, dry_run: bool = False) -> tuple[str, ...]:
        """恢复异常退出后遗留的孤儿 batch/backup。

        Args:
            dry_run: 是否仅返回将执行的动作，不真正修改文件系统。

        Returns:
            动作摘要元组。

        Raises:
            OSError: 文件系统访问失败时抛出。
        """

        if not self._should_manage_batch_state():
            return ()
        self._ensure_batch_storage_dirs()
        recovery_token = self._acquire_recovery_lock()
        try:
            actions = self._recover_orphan_batch_dirs(dry_run=dry_run)
            actions.extend(self._recover_orphan_backup_dirs(dry_run=dry_run))
        finally:
            self._release_lock_token(recovery_token)
        return tuple(actions)

    def _should_manage_batch_state(self) -> bool:
        """判断当前是否需要接触 batch 持久化状态。

        Args:
            无。

        Returns:
            若应访问 `.dayu` 下的 batch 状态则返回 `True`。

        Raises:
            无。
        """

        return self._create_directories or self.dayu_root.exists() or self.batch_root.exists() or self.backup_root.exists()

    def _ensure_batch_storage_dirs(self) -> None:
        """确保 `.dayu` 下的 batch 基础目录存在。

        Args:
            无。

        Returns:
            无。

        Raises:
            OSError: 目录创建失败时抛出。
        """

        self.dayu_root.mkdir(parents=True, exist_ok=True)
        self.batch_root.mkdir(parents=True, exist_ok=True)
        self.backup_root.mkdir(parents=True, exist_ok=True)
        self._batch_lock_root.mkdir(parents=True, exist_ok=True)

    def _ticker_lock_path(self, ticker: str) -> Path:
        """返回指定 ticker 的事务锁路径。

        Args:
            ticker: 股票代码。

        Returns:
            锁文件路径。

        Raises:
            无。
        """

        return self._batch_lock_root / f"{ticker}.lock"

    def _publication_lock_path(self, ticker: str) -> Path:
        """返回指定 ticker 的 publication guard 路径。

        Args:
            ticker: 股票代码。

        Returns:
            独立于 writer mutex 的 publication lock 路径。

        Raises:
            ValueError: ticker 非法时抛出。
        """

        normalized_ticker = _normalize_ticker(ticker)
        return self._batch_lock_root / f"{normalized_ticker}{_PUBLICATION_LOCK_SUFFIX}"

    def _acquire_lock_token(self, lock_path: Path, *, blocking: bool) -> RuntimeFileLockToken:
        """获取并持有 runtime 文件锁 token。

        Args:
            lock_path: 锁文件路径。
            blocking: 是否阻塞等待锁。

        Returns:
            已持锁的 runtime 文件锁 token。

        Raises:
            RuntimeError: 非阻塞模式下锁已被占用时抛出。
            RuntimeFileLockError: 锁文件访问或加锁失败时抛出。
        """

        try:
            if blocking:
                return file_lock(lock_path).acquire()
            return file_lock(lock_path).acquire(timeout_seconds=0)
        except RuntimeFileLockTimeoutError as exc:
            if not blocking:
                raise RuntimeError(f"ticker={lock_path.stem} 已存在跨进程活动 batch") from exc
            raise

    def _release_lock_token(self, token: RuntimeFileLockToken) -> None:
        """释放 runtime 文件锁 token。

        Args:
            token: 已持锁的 runtime 文件锁 token。

        Returns:
            无。

        Raises:
            RuntimeFileLockError: 解锁失败时抛出。
        """

        token.release()

    def _acquire_ticker_lock(self, ticker: str) -> RuntimeFileLockToken:
        """获取某个 ticker 的跨进程事务锁。

        Args:
            ticker: 股票代码。

        Returns:
            已持锁的 runtime 文件锁 token。

        Raises:
            RuntimeError: 锁已被其他进程持有时抛出。
            RuntimeFileLockError: 锁文件访问失败时抛出。
        """

        return self._acquire_lock_token(self._ticker_lock_path(ticker), blocking=False)

    def _acquire_publication_guard(self, ticker: str) -> RuntimeFileLockToken:
        """获取 ticker 级跨进程 publication guard。

        Args:
            ticker: 股票代码。

        Returns:
            已持有 publication guard 的 runtime lock token。

        Raises:
            RuntimeFileLockError: guard 获取失败时抛出。
            ValueError: ticker 非法时抛出。
        """

        return self._acquire_lock_token(self._publication_lock_path(ticker), blocking=True)

    def _publication_guarded_binary_opener(self, ticker: str) -> _PublicationGuardedBinaryOpener:
        """构造绑定 ticker publication lock 的延迟 opener。

        Args:
            ticker: 股票代码。

        Returns:
            只在文件描述符打开短窗持 publication guard 的 opener。

        Raises:
            ValueError: ticker 非法时抛出。
        """

        return _PublicationGuardedBinaryOpener(self._publication_lock_path(ticker))

    def _acquire_recovery_lock(self) -> RuntimeFileLockToken:
        """获取全局 batch 恢复锁。

        Args:
            无。

        Returns:
            已持锁的 runtime 文件锁 token。

        Raises:
            RuntimeFileLockError: 锁文件访问失败时抛出。
        """

        return self._acquire_lock_token(self._recovery_lock_path, blocking=True)

    def _write_batch_journal(self, state: _ActiveBatchState, phase: str) -> None:
        """把事务 phase 写入 journal。

        Args:
            state: storage 内部 transaction state。
            phase: 当前事务阶段。

        Returns:
            无。

        Raises:
            OSError: journal 写入失败时抛出。
        """

        payload = {
            "transaction_id": state.token.transaction_id,
            "ticker": state.token.ticker,
            "phase": phase,
        }
        _write_json(state.journal_path, payload)
        state.phase = phase

    def _recover_orphan_batch_dirs(self, *, dry_run: bool) -> list[str]:
        """扫描并恢复 batch 暂存目录。

        Args:
            dry_run: 是否仅返回将执行的动作。

        Returns:
            动作摘要列表。

        Raises:
            OSError: 文件系统访问失败时抛出。
        """

        actions: list[str] = []
        if not self.batch_root.exists():
            return actions
        for token_dir in sorted(self.batch_root.iterdir(), key=lambda item: item.name):
            if token_dir.is_symlink() or not token_dir.is_dir():
                continue
            actions.extend(self._recover_single_batch_dir(token_dir, dry_run=dry_run))
        return actions

    def _recover_single_batch_dir(self, token_dir: Path, *, dry_run: bool) -> list[str]:
        """恢复单个合法 batch 目录，并 fail-closed 保留 malformed evidence。

        Args:
            token_dir: token 根目录。
            dry_run: 是否仅返回将执行的动作。

        Returns:
            动作摘要列表。

        Raises:
            OSError: 文件系统访问失败时抛出。
        """

        actions: list[str] = []
        journal_path = token_dir / _JOURNAL_FILENAME
        if not _is_contained_recovery_path(token_dir, self.batch_root):
            actions.append(f"skip batch transaction={token_dir.name} reason=invalid_token_dir")
            return actions
        if not journal_path.exists() or journal_path.is_symlink():
            actions.append(f"skip batch transaction={token_dir.name} reason=missing_journal")
            return actions
        try:
            journal = _read_json_object(journal_path)
        except ValueError:
            actions.append(
                f"skip batch transaction={token_dir.name} reason=unparseable_journal"
            )
            return actions
        if frozenset(journal) != _JOURNAL_FIELDS:
            actions.append(f"skip batch transaction={token_dir.name} reason=invalid_journal_fields")
            return actions
        transaction_id_value = journal["transaction_id"]
        ticker_value = journal["ticker"]
        phase_value = journal["phase"]
        if not all(
            isinstance(value, str)
            for value in (transaction_id_value, ticker_value, phase_value)
        ):
            actions.append(f"skip batch transaction={token_dir.name} reason=invalid_journal_values")
            return actions
        transaction_id = transaction_id_value.strip()
        ticker = ticker_value.strip()
        phase = phase_value.strip()
        if transaction_id != token_dir.name or not ticker:
            actions.append(f"skip batch transaction={token_dir.name} reason=identity_mismatch")
            return actions
        try:
            normalized_ticker = _normalize_ticker(ticker)
        except ValueError:
            actions.append(
                f"skip batch transaction={token_dir.name} reason=invalid_journal_ticker"
            )
            return actions
        if ticker != normalized_ticker or phase not in _RECOVERY_PHASES:
            actions.append(f"skip batch transaction={token_dir.name} reason=invalid_journal_values")
            return actions
        ticker_token = self._try_acquire_recovery_ticker_lock(normalized_ticker)
        if ticker_token is None:
            return actions
        try:
            target_dir = self._target_ticker_dir(normalized_ticker)
            backup_dir = self.backup_root / f"{normalized_ticker}.bak.{transaction_id}"
            staging_dir = token_dir / normalized_ticker
            if not all(
                (
                    _is_contained_recovery_path(target_dir, self.portfolio_root),
                    _is_contained_recovery_path(backup_dir, self.backup_root),
                    _is_contained_recovery_path(staging_dir, token_dir),
                    _is_contained_recovery_path(journal_path, token_dir),
                )
            ):
                actions.append(
                    f"skip batch transaction={transaction_id} reason=invalid_recovery_locator"
                )
                return actions
            publication_token = self._acquire_publication_guard(normalized_ticker)
            try:
                if phase == _PHASE_COMMITTED:
                    if not target_dir.exists():
                        actions.append(
                            f"preserve committed evidence ticker={normalized_ticker} "
                            f"transaction={transaction_id} reason=missing_target"
                        )
                        return actions
                    if backup_dir.exists():
                        actions.append(
                            f"delete backup ticker={normalized_ticker} "
                            f"transaction={transaction_id} phase={phase}"
                        )
                        if not dry_run:
                            self._remove_directory(backup_dir)
                elif phase in {_PHASE_BACKED_UP_TARGET, _PHASE_SWAPPED_TARGET}:
                    if target_dir.exists():
                        actions.append(
                            f"remove uncommitted target ticker={normalized_ticker} "
                            f"transaction={transaction_id} phase={phase}"
                        )
                        if not dry_run:
                            if staging_dir.exists():
                                self._remove_directory(target_dir)
                            else:
                                self._replace_directory(target_dir, staging_dir)
                    if backup_dir.exists():
                        actions.append(
                            f"restore backup ticker={normalized_ticker} "
                            f"transaction={transaction_id} phase={phase}"
                        )
                        if not dry_run:
                            self._replace_directory(backup_dir, target_dir)
                elif backup_dir.exists() and not target_dir.exists():
                    actions.append(
                        f"restore backup ticker={normalized_ticker} transaction={transaction_id} "
                        f"phase={phase or 'unknown'}"
                    )
                    if not dry_run:
                        self._replace_directory(backup_dir, target_dir)
                elif backup_dir.exists() and target_dir.exists() and phase != _PHASE_STARTED:
                    actions.append(
                        f"preserve ambiguous backup ticker={normalized_ticker} "
                        f"transaction={transaction_id} phase={phase or 'unknown'}"
                    )
                    return actions
            finally:
                self._release_lock_token(publication_token)
            actions.append(
                f"cleanup batch ticker={normalized_ticker} transaction={transaction_id} "
                f"phase={phase or 'unknown'}"
            )
            if not dry_run:
                self._remove_directory(token_dir)
        finally:
            self._release_lock_token(ticker_token)
        return actions

    def _recover_orphan_backup_dirs(self, *, dry_run: bool) -> list[str]:
        """扫描并恢复合法孤儿备份，保留非法 ticker evidence 后继续扫描。

        Args:
            dry_run: 是否仅返回将执行的动作。

        Returns:
            动作摘要列表。

        Raises:
            OSError: 文件系统访问失败时抛出。
        """

        actions: list[str] = []
        if not self.backup_root.exists():
            return actions
        for backup_dir in sorted(self.backup_root.iterdir(), key=lambda item: item.name):
            if backup_dir.is_symlink() or not backup_dir.is_dir():
                continue
            parsed = _parse_backup_directory_name(backup_dir.name)
            if parsed is None:
                continue
            ticker, token_id = parsed
            token_dir = self.batch_root / token_id
            if token_dir.exists():
                continue
            try:
                normalized_ticker = _normalize_ticker(ticker)
            except ValueError:
                actions.append(
                    f"preserve backup directory={backup_dir.name} reason=invalid_backup_ticker"
                )
                continue
            ticker_token = self._try_acquire_recovery_ticker_lock(normalized_ticker)
            if ticker_token is None:
                continue
            try:
                target_dir = self._target_ticker_dir(normalized_ticker)
                if not (
                    _is_contained_recovery_path(backup_dir, self.backup_root)
                    and _is_contained_recovery_path(target_dir, self.portfolio_root)
                ):
                    actions.append(
                        f"preserve backup ticker={normalized_ticker} transaction={token_id} "
                        "reason=invalid_recovery_locator"
                    )
                    continue
                publication_token = self._acquire_publication_guard(normalized_ticker)
                try:
                    if target_dir.exists():
                        actions.append(
                            f"delete backup ticker={normalized_ticker} transaction={token_id}"
                        )
                        if not dry_run:
                            self._remove_directory(backup_dir)
                        continue
                    actions.append(
                        f"restore backup ticker={normalized_ticker} transaction={token_id}"
                    )
                    if not dry_run:
                        self._replace_directory(backup_dir, target_dir)
                finally:
                    self._release_lock_token(publication_token)
            finally:
                self._release_lock_token(ticker_token)
        return actions

    def _try_acquire_recovery_ticker_lock(self, ticker: str) -> RuntimeFileLockToken | None:
        """尝试在恢复流程中获取某个 ticker 的锁。

        Args:
            ticker: 股票代码。

        Returns:
            成功时返回已持锁的 runtime 文件锁 token；若锁正被活跃事务持有则返回 `None`。

        Raises:
            RuntimeFileLockError: 锁文件访问失败时抛出。
        """

        try:
            return self._acquire_lock_token(self._ticker_lock_path(ticker), blocking=False)
        except RuntimeError:
            return None

    # ========== handle 辅助 ==========

    def _handle_dir_path(self, handle: SourceHandle | ProcessedHandle) -> Path:
        """返回句柄对应的文档目录路径。

        Args:
            handle: 源文档/解析产物句柄。

        Returns:
            文档目录路径。

        Raises:
            ValueError: 来源类型非法时抛出。
            OSError: 路径构建失败时抛出。
        """

        normalized_ticker = _normalize_ticker(handle.ticker)
        if isinstance(handle, ProcessedHandle):
            return self._processed_dir_for_read(normalized_ticker, handle.document_id)
        source_kind = _normalize_source_kind(handle.source_kind)
        normalized_document_id = _normalize_document_id(handle.document_id)
        return self._source_root_for_read(normalized_ticker, source_kind) / normalized_document_id

    def _resolve_handle_child_path(self, handle: SourceHandle | ProcessedHandle, name: str) -> Path:
        """解析句柄目录下的直系条目路径。

        Args:
            handle: 源文档/解析产物句柄。
            name: 直系条目名称。

        Returns:
            解析后的绝对路径。

        Raises:
            ValueError: 名称为空、包含路径分隔或越界时抛出。
        """

        normalized_name = _normalize_entry_name(name)
        base_dir = self._handle_dir_path(handle)
        candidate = (base_dir / normalized_name).resolve()
        try:
            candidate.relative_to(base_dir.resolve())
        except ValueError as exc:
            raise ValueError("条目名称越界，禁止访问文档目录外路径") from exc
        return candidate

    def _handle_dir_path_for_state(
        self,
        handle: SourceHandle | ProcessedHandle,
        state: _ActiveBatchState,
    ) -> Path:
        """返回显式 transaction staging 中的句柄目录。

        Args:
            handle: 源文档或 processed 句柄。
            state: 已解析的内部 transaction state。

        Returns:
            staging 中的文档目录路径。

        Raises:
            ValueError: handle ticker 与 transaction ticker 不匹配时抛出。
        """

        normalized_ticker = _normalize_ticker(handle.ticker)
        self._require_state_ticker(state, normalized_ticker)
        normalized_document_id = _normalize_document_id(handle.document_id)
        if isinstance(handle, ProcessedHandle):
            return state.staging_ticker_dir / "processed" / normalized_document_id
        source_kind = _normalize_source_kind(handle.source_kind)
        return (
            state.staging_ticker_dir
            / _source_dir_name(source_kind)
            / normalized_document_id
        )

    def _resolve_handle_child_path_for_state(
        self,
        handle: SourceHandle | ProcessedHandle,
        name: str,
        state: _ActiveBatchState,
    ) -> Path:
        """解析显式 transaction staging 中的句柄直系条目。

        Args:
            handle: 源文档或 processed 句柄。
            name: 直系条目名称。
            state: 已解析的内部 transaction state。

        Returns:
            contained staging 条目路径。

        Raises:
            ValueError: ticker、名称或 containment 校验失败时抛出。
        """

        normalized_name = _normalize_entry_name(name)
        base_dir = self._handle_dir_path_for_state(handle, state)
        candidate = (base_dir / normalized_name).resolve()
        try:
            candidate.relative_to(base_dir.resolve())
        except ValueError as exc:
            raise ValueError("条目名称越界，禁止访问文档目录外路径") from exc
        return candidate

    def _get_handle_meta(self, handle: SourceHandle | ProcessedHandle) -> dict[str, Any]:
        """读取句柄对应的 meta.json。

        Args:
            handle: 文档句柄。

        Returns:
            meta.json 内容。

        Raises:
            FileNotFoundError: meta.json 不存在时抛出。
            ValueError: JSON 内容非法时抛出。
        """

        normalized_ticker = _normalize_ticker(handle.ticker)
        if isinstance(handle, ProcessedHandle):
            meta_path = self._processed_meta_path_for_read(normalized_ticker, handle.document_id)
        else:
            source_kind = _normalize_source_kind(handle.source_kind)
            meta_path = self._source_meta_path_for_read(normalized_ticker, handle.document_id, source_kind)
        if not meta_path.exists():
            raise FileNotFoundError(f"meta.json 不存在: {meta_path}")
        return _read_json_object(meta_path)

    def _get_handle_meta_for_state(
        self,
        handle: SourceHandle | ProcessedHandle,
        state: _ActiveBatchState,
    ) -> dict[str, Any]:
        """读取显式 transaction staging 中的句柄 meta。

        Args:
            handle: 文档句柄。
            state: 已解析的内部 transaction state。

        Returns:
            staging meta 内容。

        Raises:
            FileNotFoundError: staging meta 不存在时抛出。
            ValueError: ticker 或 JSON 内容非法时抛出。
        """

        directory = self._handle_dir_path_for_state(handle, state)
        filename = _PROCESSED_META_FILENAME if isinstance(handle, ProcessedHandle) else _SOURCE_META_FILENAME
        meta_path = directory / filename
        if not meta_path.exists():
            raise FileNotFoundError(f"meta.json 不存在: {meta_path}")
        return _read_json_object(meta_path)

    def _list_handle_files_unguarded(
        self,
        handle: SourceHandle | ProcessedHandle,
    ) -> list[FileObjectMeta]:
        """在 caller 已持 publication guard 时读取句柄文件元数据。

        Args:
            handle: 源文档或 processed 句柄。

        Returns:
            文件元数据列表。

        Raises:
            FileNotFoundError: 文档 meta 不存在时抛出。
            ValueError: meta.files 格式非法时抛出。
        """

        meta = self._get_handle_meta(handle)
        files = meta.get("files", [])
        if not isinstance(files, list):
            raise ValueError("meta.files 必须为 list")
        result: list[FileObjectMeta] = []
        for item in files:
            if isinstance(item, dict):
                result.append(_file_object_meta_from_dict(item))
        return result

    # ========== core 辅助 ==========

    def _ensure_ticker_structure(self, ticker_dir: Path) -> None:
        """确保 ticker 目录结构存在。

        Args:
            ticker_dir: ticker 目录路径。

        Returns:
            无。

        Raises:
            OSError: 目录创建失败时抛出。
        """

        (ticker_dir / "filings").mkdir(parents=True, exist_ok=True)
        (ticker_dir / "materials").mkdir(parents=True, exist_ok=True)
        (ticker_dir / "processed").mkdir(parents=True, exist_ok=True)

    def _build_file_store(self, ticker: str, state: _ActiveBatchState) -> FileStore:
        """构建文件存储实例。

        Args:
            ticker: 股票代码。
            state: 已解析的内部 transaction state。

        Returns:
            文件存储实例。

        Raises:
            OSError: 目录创建失败时抛出。
        """

        if self._file_store is not None:
            return self._file_store
        return LocalFileStore(root=self._file_store_root_for_ticker(ticker, state), scheme="local")

    def _require_state_ticker(self, state: _ActiveBatchState, ticker: str) -> str:
        """校验内部 state 与请求 ticker 同源。

        Args:
            state: 已解析的内部 transaction state。
            ticker: 请求 ticker。

        Returns:
            规范化 ticker。

        Raises:
            ValueError: state 与请求 ticker 不匹配时抛出。
        """

        normalized_ticker = _normalize_ticker(ticker)
        if state.token.ticker != normalized_ticker:
            raise ValueError("内部 transaction state 与 ticker 不匹配")
        return normalized_ticker

    def _build_store_key_from_normalized_filename(
        self,
        handle: SourceHandle | ProcessedHandle,
        normalized_filename: str,
    ) -> str:
        """使用已校验文件名构建对象存储 key。

        Args:
            handle: 文档句柄。
            normalized_filename: 已由 filename owner 校验的单组件文件名。

        Returns:
            逻辑 key。

        Raises:
            ValueError: 来源类型非法时抛出。
        """

        normalized_ticker = _normalize_ticker(handle.ticker)
        normalized_document_id = _normalize_document_id(handle.document_id)
        if isinstance(handle, ProcessedHandle):
            return f"{normalized_ticker}/processed/{normalized_document_id}/{normalized_filename}"
        source_kind = _normalize_source_kind(handle.source_kind)
        return (
            f"{normalized_ticker}/{_source_dir_name(source_kind)}/"
            f"{normalized_document_id}/{normalized_filename}"
        )

    def _select_primary_document(
        self,
        explicit_primary: Optional[str],
        previous_primary: Any,
    ) -> Optional[str]:
        """确定主文件名。

        Args:
            explicit_primary: 请求显式传入主文件名。
            previous_primary: 旧 meta 中主文件名。

        Returns:
            主文件名；若无法确定则返回 `None`。

        Raises:
            无。
        """

        if isinstance(explicit_primary, str) and explicit_primary.strip():
            return explicit_primary
        if isinstance(previous_primary, str) and previous_primary.strip():
            return previous_primary
        return None

    # ========== manifest 操作 ==========

    def _upsert_filing_manifest(
        self,
        state: _ActiveBatchState,
        items: list[FilingManifestItem],
    ) -> None:
        """在显式 transaction staging 中合并 filing manifest。

        Args:
            state: 已解析的内部 transaction state。
            items: filing manifest 项目列表。

        Returns:
            无。

        Raises:
            OSError: 写入失败时抛出。
        """

        normalized_ticker = state.token.ticker
        payloads = [item.to_dict() for item in items]
        self._upsert_manifest_items(
            self._filing_manifest_path(normalized_ticker, state),
            normalized_ticker,
            payloads,
        )

    def _upsert_material_manifest(
        self,
        state: _ActiveBatchState,
        items: list[MaterialManifestItem],
    ) -> None:
        """在显式 transaction staging 中合并 material manifest。

        Args:
            state: 已解析的内部 transaction state。
            items: material manifest 项目列表。

        Returns:
            无。

        Raises:
            OSError: 写入失败时抛出。
        """

        normalized_ticker = state.token.ticker
        payloads = [item.to_dict() for item in items]
        self._upsert_manifest_items(
            self._material_manifest_path(normalized_ticker, state),
            normalized_ticker,
            payloads,
        )

    def _upsert_processed_manifest(
        self,
        state: _ActiveBatchState,
        items: list[ProcessedManifestItem],
    ) -> None:
        """在显式 transaction staging 中合并 processed manifest。

        Args:
            state: 已解析的内部 transaction state。
            items: processed manifest 项目列表。

        Returns:
            无。

        Raises:
            OSError: 写入失败时抛出。
        """

        normalized_ticker = state.token.ticker
        payloads = [item.to_dict() for item in items]
        self._upsert_manifest_items(
            self._processed_manifest_path(normalized_ticker, state),
            normalized_ticker,
            payloads,
        )

    def _upsert_manifest_items(self, path: Path, ticker: str, items: list[dict[str, Any]]) -> None:
        """合并并写入 manifest 项目。

        Args:
            path: manifest 文件路径。
            ticker: 股票代码。
            items: 待写入项目列表。

        Returns:
            无。

        Raises:
            OSError: 写入失败。
        """

        manifest = self._read_manifest(path, ticker)
        documents_map = {doc["document_id"]: doc for doc in manifest["documents"] if "document_id" in doc}
        for item in items:
            normalized_document_id = _normalize_document_id(str(item["document_id"]))
            normalized_item = dict(item)
            normalized_item["document_id"] = normalized_document_id
            documents_map[normalized_document_id] = normalized_item
        manifest["documents"] = sorted(documents_map.values(), key=lambda x: x["document_id"])
        manifest["updated_at"] = now_iso8601()
        _write_json(path, manifest)

    def _remove_manifest_item(self, path: Path, ticker: str, document_id: str) -> None:
        """从 manifest 中移除一个文档项目。

        Args:
            path: manifest 文件路径。
            ticker: 股票代码。
            document_id: 文档 ID。

        Returns:
            无。

        Raises:
            OSError: 写入失败。
        """

        normalized_document_id = _normalize_document_id(document_id)
        manifest = self._read_manifest(path, ticker)
        manifest["documents"] = [
            doc for doc in manifest["documents"] if doc.get("document_id") != normalized_document_id
        ]
        manifest["updated_at"] = now_iso8601()
        _write_json(path, manifest)

    def _remove_manifest_items(self, path: Path, ticker: str, document_ids: list[str]) -> None:
        """从 manifest 中批量移除文档项目。

        Args:
            path: manifest 文件路径。
            ticker: 股票代码。
            document_ids: 待移除的文档 ID 列表。

        Returns:
            无。

        Raises:
            OSError: 写入失败时抛出。
        """

        stale_set = {_normalize_document_id(document_id) for document_id in document_ids}
        manifest = self._read_manifest(path, ticker)
        manifest["documents"] = [doc for doc in manifest["documents"] if doc.get("document_id") not in stale_set]
        manifest["updated_at"] = now_iso8601()
        _write_json(path, manifest)

    def _read_manifest(self, path: Path, ticker: str) -> dict[str, Any]:
        """读取 manifest，不存在则返回默认结构。

        Args:
            path: manifest 路径。
            ticker: 股票代码。

        Returns:
            manifest 字典。

        Raises:
            ValueError: JSON 内容非法时抛出。
            OSError: 文件读取失败时抛出。
        """

        if path.exists():
            return _read_json_object(path)
        return {"ticker": ticker, "updated_at": now_iso8601(), "documents": []}

    # ========== 路径方法 ==========

    def _target_ticker_dir(self, ticker: str) -> Path:
        """返回正式 ticker 目录。

        Args:
            ticker: 股票代码。

        Returns:
            正式目录路径。

        Raises:
            无。
        """

        return self.portfolio_root / ticker

    def _ticker_dir_for_write(self, ticker: str, state: _ActiveBatchState) -> Path:
        """返回显式 transaction staging 的可写 ticker 目录。

        Args:
            ticker: 股票代码。
            state: 已解析的内部 transaction state。

        Returns:
            可写目录路径。

        Raises:
            OSError: 目录创建失败时抛出。
        """

        self._require_state_ticker(state, ticker)
        self._ensure_ticker_structure(state.staging_ticker_dir)
        return state.staging_ticker_dir

    def _ticker_dir_for_read(self, ticker: str) -> Path:
        """返回 published ticker 目录。

        Args:
            ticker: 股票代码。

        Returns:
            可读目录路径。

        Raises:
            无。
        """

        return self._target_ticker_dir(_normalize_ticker(ticker))

    def _file_store_root_for_ticker(self, ticker: str, state: _ActiveBatchState) -> Path:
        """获取显式 transaction staging 的文件存储根目录。

        Args:
            ticker: 股票代码。
            state: 已解析的内部 transaction state。

        Returns:
            文件存储根目录。

        Raises:
            OSError: 目录创建失败时抛出。
        """

        self._require_state_ticker(state, ticker)
        self._ensure_ticker_structure(state.staging_ticker_dir)
        return state.staging_ticker_dir.parent

    def _source_root(
        self,
        ticker: str,
        source_kind: SourceKind,
        state: _ActiveBatchState,
    ) -> Path:
        """返回来源目录根路径。

        Args:
            ticker: 股票代码。
            source_kind: 来源类型。
            state: 已解析的内部 transaction state。

        Returns:
            来源目录路径。

        Raises:
            OSError: 目录创建失败时抛出。
        """

        ticker_dir = self._ticker_dir_for_write(ticker, state)
        if source_kind == SourceKind.FILING:
            return ticker_dir / "filings"
        return ticker_dir / "materials"

    def _source_root_for_read(self, ticker: str, source_kind: SourceKind) -> Path:
        """返回来源目录根路径（用于读取）。

        Args:
            ticker: 股票代码。
            source_kind: 来源类型。

        Returns:
            来源目录路径。

        Raises:
            无。
        """

        ticker_dir = self._ticker_dir_for_read(ticker)
        if source_kind == SourceKind.FILING:
            return ticker_dir / "filings"
        return ticker_dir / "materials"

    def _source_meta_path(
        self,
        ticker: str,
        document_id: str,
        source_kind: SourceKind,
        state: _ActiveBatchState,
    ) -> Path:
        """返回源文档 meta 路径。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。
            source_kind: 来源类型。
            state: 已解析的内部 transaction state。

        Returns:
            meta 文件路径。

        Raises:
            OSError: 路径构建失败时抛出。
        """

        normalized_document_id = _normalize_document_id(document_id)
        return (
            self._source_root(ticker, source_kind, state)
            / normalized_document_id
            / _SOURCE_META_FILENAME
        )

    def _source_meta_path_for_read(self, ticker: str, document_id: str, source_kind: SourceKind) -> Path:
        """返回源文档 meta 路径（用于读取）。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。
            source_kind: 来源类型。

        Returns:
            meta 文件路径。

        Raises:
            无。
        """

        normalized_document_id = _normalize_document_id(document_id)
        return self._source_root_for_read(ticker, source_kind) / normalized_document_id / _SOURCE_META_FILENAME

    def _company_meta_path(self, ticker: str, state: _ActiveBatchState) -> Path:
        """返回公司级 meta 路径。

        Args:
            ticker: 股票代码。
            state: 已解析的内部 transaction state。

        Returns:
            公司级 meta 路径。

        Raises:
            OSError: 路径构建失败时抛出。
        """

        normalized_ticker = _normalize_ticker(ticker)
        return self._ticker_dir_for_write(normalized_ticker, state) / _SOURCE_META_FILENAME

    def _company_meta_path_for_read(self, ticker: str) -> Path:
        """返回公司级 meta 路径（用于读取）。

        Args:
            ticker: 股票代码。

        Returns:
            公司级 meta 路径。

        Raises:
            无。
        """

        normalized_ticker = _normalize_ticker(ticker)
        return self._ticker_dir_for_read(normalized_ticker) / _SOURCE_META_FILENAME

    def _filing_manifest_path(self, ticker: str, state: _ActiveBatchState) -> Path:
        """返回 filing manifest 路径。

        Args:
            ticker: 股票代码。
            state: 已解析的内部 transaction state。

        Returns:
            filing manifest 路径。

        Raises:
            OSError: 路径构建失败时抛出。
        """

        return self._ticker_dir_for_write(ticker, state) / "filings" / "filing_manifest.json"

    def _filing_manifest_path_for_read(self, ticker: str) -> Path:
        """返回 filing manifest 路径（用于读取）。

        Args:
            ticker: 股票代码。

        Returns:
            filing manifest 路径。

        Raises:
            无。
        """

        return self._ticker_dir_for_read(ticker) / "filings" / "filing_manifest.json"

    def _material_manifest_path(self, ticker: str, state: _ActiveBatchState) -> Path:
        """返回 material manifest 路径。

        Args:
            ticker: 股票代码。
            state: 已解析的内部 transaction state。

        Returns:
            material manifest 路径。

        Raises:
            OSError: 路径构建失败时抛出。
        """

        return self._ticker_dir_for_write(ticker, state) / "materials" / "material_manifest.json"

    def _material_manifest_path_for_read(self, ticker: str) -> Path:
        """返回 material manifest 路径（用于读取）。

        Args:
            ticker: 股票代码。

        Returns:
            material manifest 路径。

        Raises:
            无。
        """

        return self._ticker_dir_for_read(ticker) / "materials" / "material_manifest.json"

    def _processed_manifest_path(self, ticker: str, state: _ActiveBatchState) -> Path:
        """返回 processed manifest 路径。

        Args:
            ticker: 股票代码。
            state: 已解析的内部 transaction state。

        Returns:
            processed manifest 路径。

        Raises:
            OSError: 路径构建失败时抛出。
        """

        return self._ticker_dir_for_write(ticker, state) / "processed" / "manifest.json"

    def _processed_manifest_path_for_read(self, ticker: str) -> Path:
        """返回 processed manifest 路径（用于读取）。

        Args:
            ticker: 股票代码。

        Returns:
            processed manifest 路径。

        Raises:
            无。
        """

        return self._ticker_dir_for_read(ticker) / "processed" / "manifest.json"

    def _processed_dir_for_write(
        self,
        ticker: str,
        document_id: str,
        state: _ActiveBatchState,
    ) -> Path:
        """获取解析产物目录路径（用于写入）。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。
            state: 已解析的内部 transaction state。

        Returns:
            解析产物目录路径。

        Raises:
            OSError: 路径构建失败时抛出。
        """

        normalized_ticker = _normalize_ticker(ticker)
        normalized_document_id = _normalize_document_id(document_id)
        return (
            self._ticker_dir_for_write(normalized_ticker, state)
            / "processed"
            / normalized_document_id
        )

    def _processed_dir_for_read(self, ticker: str, document_id: str) -> Path:
        """获取解析产物目录路径（用于读取）。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。

        Returns:
            解析产物目录路径。

        Raises:
            无。
        """

        normalized_ticker = _normalize_ticker(ticker)
        normalized_document_id = _normalize_document_id(document_id)
        return self._ticker_dir_for_read(normalized_ticker) / "processed" / normalized_document_id

    def _processed_meta_path(
        self,
        ticker: str,
        document_id: str,
        state: _ActiveBatchState,
    ) -> Path:
        """获取解析产物 tool_snapshot_meta.json 路径。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。
            state: 已解析的内部 transaction state。

        Returns:
            tool_snapshot_meta.json 路径。

        Raises:
            OSError: 路径构建失败时抛出。
        """

        return self._processed_dir_for_write(ticker, document_id, state) / _PROCESSED_META_FILENAME

    def _processed_meta_path_for_read(self, ticker: str, document_id: str) -> Path:
        """获取解析产物 tool_snapshot_meta.json 路径（用于读取）。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。

        Returns:
            tool_snapshot_meta.json 路径。

        Raises:
            无。
        """

        return self._processed_dir_for_read(ticker, document_id) / _PROCESSED_META_FILENAME

    def _download_rejections_path(self, ticker: str, state: _ActiveBatchState) -> Path:
        """返回下载拒绝注册表路径。

        Args:
            ticker: 股票代码。
            state: 已解析的内部 transaction state。

        Returns:
            拒绝注册表路径。

        Raises:
            OSError: 路径构建失败时抛出。
        """

        return (
            self._ticker_dir_for_write(ticker, state)
            / "filings"
            / _DOWNLOAD_REJECTIONS_FILENAME
        )

    def _download_rejections_path_for_read(self, ticker: str) -> Path:
        """返回下载拒绝注册表路径（用于读取）。

        Args:
            ticker: 股票代码。

        Returns:
            拒绝注册表路径。

        Raises:
            无。
        """

        return self._ticker_dir_for_read(ticker) / "filings" / _DOWNLOAD_REJECTIONS_FILENAME

    def _rejected_filings_root(self, ticker: str, state: _ActiveBatchState) -> Path:
        """返回 rejected filings 根目录。

        Args:
            ticker: 股票代码。
            state: 已解析的内部 transaction state。

        Returns:
            rejected filings 根目录。

        Raises:
            OSError: 路径构建失败时抛出。
        """

        return (
            self._ticker_dir_for_write(ticker, state)
            / "filings"
            / _REJECTED_FILINGS_DIRNAME
        )

    def _rejected_filings_root_for_read(self, ticker: str) -> Path:
        """返回 rejected filings 根目录（用于读取）。

        Args:
            ticker: 股票代码。

        Returns:
            rejected filings 根目录。

        Raises:
            无。
        """

        return self._ticker_dir_for_read(ticker) / "filings" / _REJECTED_FILINGS_DIRNAME

    def _rejected_filing_dir(
        self,
        ticker: str,
        document_id: str,
        state: _ActiveBatchState,
    ) -> Path:
        """返回单个 rejected filing 目录。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。
            state: 已解析的内部 transaction state。

        Returns:
            文档目录路径。

        Raises:
            OSError: 路径构建失败时抛出。
        """

        normalized_document_id = _normalize_document_id(document_id)
        return self._rejected_filings_root(ticker, state) / normalized_document_id

    def _rejected_filing_dir_for_read(self, ticker: str, document_id: str) -> Path:
        """返回单个 rejected filing 目录（用于读取）。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。

        Returns:
            文档目录路径。

        Raises:
            无。
        """

        normalized_document_id = _normalize_document_id(document_id)
        return self._rejected_filings_root_for_read(ticker) / normalized_document_id

    def _rejected_filing_meta_path(
        self,
        ticker: str,
        document_id: str,
        state: _ActiveBatchState,
    ) -> Path:
        """返回 rejected filing meta 路径。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。
            state: 已解析的内部 transaction state。

        Returns:
            meta.json 路径。

        Raises:
            OSError: 路径构建失败时抛出。
        """

        return self._rejected_filing_dir(ticker, document_id, state) / _SOURCE_META_FILENAME

    def _rejected_filing_meta_path_for_read(self, ticker: str, document_id: str) -> Path:
        """返回 rejected filing meta 路径（用于读取）。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。

        Returns:
            meta.json 路径。

        Raises:
            无。
        """

        return self._rejected_filing_dir_for_read(ticker, document_id) / _SOURCE_META_FILENAME

    def _rejected_filing_file_path_for_read(self, ticker: str, document_id: str, filename: str) -> Path:
        """返回 rejected filing 文件路径（用于读取）。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。
            filename: 文件名。

        Returns:
            文件路径。

        Raises:
            ValueError: 文件名为空或越界时抛出。
        """

        normalized_name = _normalize_entry_name(filename)
        base_dir = self._rejected_filing_dir_for_read(ticker, document_id)
        candidate = (base_dir / normalized_name).resolve()
        try:
            candidate.relative_to(base_dir.resolve())
        except ValueError as exc:
            raise ValueError("条目名称越界，禁止访问文档目录外路径") from exc
        return candidate
