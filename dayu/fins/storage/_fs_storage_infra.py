"""文件系统仓储基础设施层。

提供共享实例状态、批处理事务、路径方法、manifest 操作、handle 辅助等，
作为所有领域 mixin 的唯一基类。
"""

from __future__ import annotations

import errno
import os
import stat
import shutil
import threading
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO, Final, Optional, cast

from dayu.contracts.json_value import JsonValue
from dayu.fins._log import Log
from dayu.runtime.filelock import (
    RuntimeFileLockError,
    RuntimeFileLockTimeoutError,
    RuntimeFileLockToken,
    file_lock,
)

from dayu.fins.domain.document_models import (
    BatchToken,
    CompanyMeta,
    FileObjectMeta,
    FilingManifestItem,
    MaterialManifestItem,
    ProcessedHandle,
    ProcessedManifestItem,
    SourceHandle,
    now_iso8601,
)
from dayu.fins.domain.company_meta_contract import (
    CompanyMetaCommitIntent,
    merge_company_meta_for_commit,
)
from dayu.fins.domain.enums import SourceKind

from ._fs_identity import (
    _FILING_IDENTITY_NAMESPACE,
    _IDENTITY_DESCRIPTOR_FILENAME,
    _MATERIAL_IDENTITY_NAMESPACE,
    _PROCESSED_IDENTITY_NAMESPACE,
    _REJECTED_FILING_IDENTITY_NAMESPACE,
    _TICKER_IDENTITY_NAMESPACE,
    _IdentityNamespace,
    _derive_storage_key,
    _ensure_identity_directory,
    _identity_directory_for_read,
    _identity_directory_if_present_for_read,
    _identity_directory_path,
    _identity_descriptor_path,
    _read_identity_descriptor,
    _require_external_identity,
)
from .file_store import FileStore
from ._fs_source_integrity import (
    _SourcePublicationInspection,
    _inspect_source_kind_unguarded,
)
from .local_file_store import LocalFileStore
from .repository_protocols import (
    CompanyTickerAliasConflictError,
    CompanyTickerIdentityCorruptionError,
)
from ._fs_storage_utils import (
    _DOWNLOAD_REJECTIONS_FILENAME,
    _PROCESSED_META_FILENAME,
    _REJECTED_FILINGS_DIRNAME,
    _SOURCE_META_FILENAME,
    _append_secondary_error_note,
    _file_object_meta_from_dict,
    _fsync_directory,
    _list_directory,
    _normalize_entry_name,
    _normalize_filename,
    _normalize_source_kind,
    _open_binary_file,
    _project_filesystem_error,
    _raise_path_free_error,
    _read_json_object,
    _source_dir_name,
    _write_json,
)
from .source_integrity import SourceIntegrityStatus

_DAYU_DIRNAME = ".dayu"
_BATCH_ROOT_DIRNAME = "repo_batches"
_BACKUP_ROOT_DIRNAME = "repo_backups"
_LOCK_ROOT_DIRNAME = "batch_locks"
_RECOVERY_LOCK_FILENAME = "batch_recovery.lock"
_COMPANY_IDENTITY_LOCK_FILENAME = "company_identity.lock"
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
    company_meta_intent: CompanyMetaCommitIntent | None
    publishes_new_corpus: bool


@dataclass(frozen=True, slots=True)
class _PublishedCompanyIdentity:
    """一次 authoritative scan 得到的 published corpus identity。"""

    canonical_ticker: str
    company_meta: CompanyMeta | None


def _project_runtime_lock_error(
    error: RuntimeFileLockError,
    *,
    action: str,
) -> RuntimeFileLockError:
    """投影 runtime-lock 异常并移除 raw nested cause locator。

    Args:
        error: runtime layer 抛出的 lock 异常。
        action: 不含 lock path/private key 的 storage 操作说明。

    Returns:
        同 runtime-lock subclass、完整 exception graph 均 path-free 的异常。

    Raises:
        无。
    """

    projected_error = type(error)(f"{action}失败")
    raw_cause = error.__cause__ if error.__cause__ is not None else error.__context__
    if isinstance(raw_cause, OSError):
        projected_error.__cause__ = _project_filesystem_error(
            raw_cause,
            action=f"{action}底层文件系统",
        )
    elif raw_cause is not None:
        projected_error.__cause__ = RuntimeError(f"{action}底层失败: error_type={raw_cause.__class__.__name__}")
    projected_error.__suppress_context__ = True
    return projected_error


def _acquire_storage_lock_token(
    lock_path: Path,
    *,
    blocking: bool,
) -> RuntimeFileLockToken:
    """获取 runtime lock 并在 storage owner boundary 投影失败。

    Args:
        lock_path: storage owner 已派生的 private lock locator。
        blocking: 是否阻塞等待锁。

    Returns:
        已持锁的 runtime token。

    Raises:
        RuntimeError: 非阻塞模式下 lock 已被占用时抛出。
        RuntimeFileLockError: acquire 失败时抛出 path-free runtime-lock 异常。
    """

    try:
        if blocking:
            return file_lock(lock_path).acquire()
        return file_lock(lock_path).acquire(timeout_seconds=0)
    except RuntimeFileLockTimeoutError as exc:
        projected_error = _project_runtime_lock_error(
            exc,
            action="获取 storage lock",
        )
        if not blocking:
            busy_error = RuntimeError("storage identity 已存在跨进程活动 batch")
            busy_error.__cause__ = projected_error
            busy_error.__suppress_context__ = True
            _raise_path_free_error(busy_error)
        _raise_path_free_error(projected_error)
    except RuntimeFileLockError as exc:
        _raise_path_free_error(_project_runtime_lock_error(exc, action="获取 storage lock"))


def _release_storage_lock_token(token: RuntimeFileLockToken) -> None:
    """释放 runtime lock 并在 storage owner boundary 投影失败。

    Args:
        token: 已持锁的 runtime token。

    Returns:
        无。

    Raises:
        RuntimeFileLockError: runtime release 失败时抛出 path-free lock 异常。
        OSError: 非 runtime 实现的文件系统 release 失败时抛出 path-free 异常。
    """

    try:
        token.release()
    except RuntimeFileLockError as exc:
        _raise_path_free_error(_project_runtime_lock_error(exc, action="释放 storage lock"))
    except OSError as exc:
        _raise_path_free_error(_project_filesystem_error(exc, action="释放 storage lock"))


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

        guard_token = _acquire_storage_lock_token(self.lock_path, blocking=True)
        try:
            return _open_binary_file(path, action="打开 published source 文件")
        finally:
            _release_storage_lock_token(guard_token)


def _parse_backup_directory_name(name: str) -> tuple[str, str] | None:
    """解析备份目录名中的 private ticker key 与 token。

    Args:
        name: 备份目录名。

    Returns:
        成功时返回 `(private_ticker_key, token_id)`，否则返回 `None`。

    Raises:
        无。
    """

    ticker_key, separator, token_id = name.rpartition(".bak.")
    if not separator or not ticker_key or not token_id:
        return None
    return ticker_key, token_id


def _source_identity_namespace(source_kind: SourceKind) -> _IdentityNamespace:
    """返回 source kind 对应的 storage identity namespace。

    Args:
        source_kind: filing 或 material 来源类型。

    Returns:
        对应的私有 document identity namespace。

    Raises:
        ValueError: source kind 非法时抛出。
    """

    if source_kind is SourceKind.FILING:
        return _FILING_IDENTITY_NAMESPACE
    if source_kind is SourceKind.MATERIAL:
        return _MATERIAL_IDENTITY_NAMESPACE
    raise ValueError(f"source_kind 非法: {source_kind}")


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

    try:
        normalized_root = root.resolve(strict=False)
        normalized_path = path.resolve(strict=False)
        normalized_path.relative_to(normalized_root)
    except ValueError:
        return False
    except OSError as exc:
        _raise_path_free_error(_project_filesystem_error(exc, action="校验 recovery locator"))
    try:
        current = path
        while current != root:
            if current.is_symlink():
                return False
            parent = current.parent
            if parent == current:
                return False
            current = parent
        return not root.is_symlink()
    except OSError as exc:
        _raise_path_free_error(_project_filesystem_error(exc, action="校验 recovery symlink 链"))


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

        try:
            self.workspace_root = workspace_root.resolve()
        except OSError as exc:
            _raise_path_free_error(_project_filesystem_error(exc, action="解析 storage workspace"))
        self.portfolio_root = self.workspace_root / "portfolio"
        self.dayu_root = self.workspace_root / _DAYU_DIRNAME
        self.batch_root = self.dayu_root / _BATCH_ROOT_DIRNAME
        self.backup_root = self.dayu_root / _BACKUP_ROOT_DIRNAME
        self._batch_lock_root = self.dayu_root / _LOCK_ROOT_DIRNAME
        self._recovery_lock_path = self.dayu_root / _RECOVERY_LOCK_FILENAME
        self._company_identity_lock_path = self.dayu_root / _COMPANY_IDENTITY_LOCK_FILENAME
        self._create_directories = create_directories
        self._batch_recovery_completed = False
        self._active_batches: dict[str, _ActiveBatchState] = {}
        self._active_transaction_by_ticker: dict[str, str] = {}
        self._batch_condition = threading.Condition()
        self._reserved_batch_tickers: set[str] = set()
        self._file_store = file_store
        if create_directories:
            try:
                self.portfolio_root.mkdir(parents=True, exist_ok=True)
                self._ensure_batch_storage_dirs()
            except OSError as exc:
                _raise_path_free_error(_project_filesystem_error(exc, action="初始化 storage workspace"))

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
            CompanyTickerIdentityCorruptionError: existing target、descriptor、meta
                或 tree durable state 损坏时抛出。
            RuntimeError: 本地 reservation 或跨进程 writer lock 失败时抛出。
            RuntimeFileLockError: writer lock 获取或初始化失败后的释放失败时抛出。
            OSError: 暂存目录准备失败时抛出。
        """

        external_ticker = _require_external_identity(ticker, field_name="ticker")
        self._reserve_batch_ticker(external_ticker)
        lock_token: RuntimeFileLockToken | None = None
        registered = False
        transaction_id = uuid.uuid4().hex
        ticker_key = _derive_storage_key(_TICKER_IDENTITY_NAMESPACE, external_ticker)
        target_ticker_dir = self._target_ticker_dir(external_ticker)
        staging_root_dir = self.batch_root / transaction_id
        staging_ticker_dir = staging_root_dir / ticker_key
        backup_dir = self.backup_root / f"{ticker_key}.bak.{transaction_id}"
        journal_path = staging_root_dir / _JOURNAL_FILENAME
        token = BatchToken(
            transaction_id=transaction_id,
            ticker=external_ticker,
        )
        try:
            self._ensure_batch_storage_dirs()
            self.ensure_batch_recovery()
            # 复杂逻辑说明：跨进程 writer 必须阻塞等待；本地 Condition 只串行化同实例。
            lock_token = self._acquire_ticker_lock(external_ticker)
            target_stat = self._lstat_optional_storage_path(
                target_ticker_dir,
                action="检查 batch target ticker directory",
            )
            target_is_published = target_stat is not None
            if target_stat is not None and not stat.S_ISDIR(target_stat.st_mode):
                raise CompanyTickerIdentityCorruptionError(kind="invalid_descriptor")
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
                company_meta_intent=None,
                publishes_new_corpus=not target_is_published,
            )
            self._write_batch_journal(state, _PHASE_STARTED)
            if target_is_published:
                assert target_stat is not None
                published_identity = self._read_published_company_identity(
                    target_ticker_dir,
                    expected_storage_key=target_ticker_dir.name,
                    known_directory_stat=target_stat,
                )
                if published_identity.canonical_ticker != external_ticker:
                    raise CompanyTickerIdentityCorruptionError(kind="invalid_descriptor")
                self._require_copyable_ticker_tree(target_ticker_dir)
                shutil.copytree(target_ticker_dir, staging_ticker_dir)
                _read_identity_descriptor(
                    staging_ticker_dir,
                    _TICKER_IDENTITY_NAMESPACE,
                    expected_external_identity=external_ticker,
                )
            else:
                self._ensure_ticker_structure(staging_ticker_dir, external_ticker)
        except Exception as raw_primary_error:
            primary_error: Exception = raw_primary_error
            if isinstance(raw_primary_error, OSError):
                primary_error = _project_filesystem_error(
                    raw_primary_error,
                    action="初始化 storage batch",
                )
            try:
                if staging_root_dir.exists() or staging_root_dir.is_symlink():
                    shutil.rmtree(staging_root_dir)
            except Exception as cleanup_error:
                _append_secondary_error_note(
                    primary_error,
                    cleanup_error,
                    action="batch staging cleanup failed",
                )
            if lock_token is not None:
                try:
                    self._release_lock_token(lock_token)
                except Exception as release_error:
                    _append_secondary_error_note(
                        primary_error,
                        release_error,
                        action="writer mutex release failed during batch initialization",
                    )
            if primary_error is raw_primary_error:
                raise
            _raise_path_free_error(primary_error)
        else:
            with self._batch_condition:
                self._active_batches[transaction_id] = state
                self._active_transaction_by_ticker[external_ticker] = transaction_id
                self._reserved_batch_tickers.discard(external_ticker)
                registered = True
            return token
        finally:
            if not registered:
                self._release_batch_ticker_reservation(external_ticker)

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
        try:
            # 复杂逻辑说明：完整性校验只读 transaction staging，必须先于 publication guard。
            self._validate_complete_source_tree(state)
            if state.company_meta_intent is not None or state.publishes_new_corpus:
                self._commit_batch_with_identity_guards(state)
            else:
                self._commit_batch_with_publication_guard(state)
        except Exception as exc:
            commit_error = exc
            if state.phase not in {_PHASE_COMMITTED, _PHASE_ROLLED_BACK}:
                try:
                    self._rollback_precommit_batch(state)
                except Exception as rollback_exc:
                    rollback_error = rollback_exc
        if commit_error is not None and state.phase != _PHASE_COMMITTED:
            self._close_active_batch(state, primary_error=commit_error)
            if rollback_error is not None:
                commit_error.add_note("commit_batch rollback failed; journal/backup/staging recovery evidence retained")
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
        terminal_error = commit_error if state.phase == _PHASE_COMMITTED else None
        if cleanup_error is not None:
            if terminal_error is None:
                terminal_error = cleanup_error
            else:
                _append_secondary_error_note(
                    terminal_error,
                    cleanup_error,
                    action=("post-commit cleanup failed after publication guard release failure"),
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

    def _commit_batch_with_identity_guards(self, state: _ActiveBatchState) -> None:
        """按固定全局锁序准备 identity 并提交 batch。

        Args:
            state: 已进入 commit-started 的活动 batch state。

        Returns:
            无。

        Raises:
            CompanyTickerAliasConflictError: incoming lookup ticker 已被其它 corpus 占用时抛出。
            CompanyTickerIdentityCorruptionError: published identity durable state 损坏时抛出。
            CompanyMetaConcurrentUpdateError: CompanyMeta 乐观前置条件失效时抛出。
            RuntimeFileLockError: recovery、identity 或 publication guard 操作失败时抛出。
            OSError: recovery、扫描、staging 写入或 physical commit 失败时抛出。
            ValueError: staged descriptor 或 intent 不符合契约时抛出。
        """

        recovery_token = self._acquire_recovery_lock()
        primary_error: Exception | None = None
        try:
            self._recover_orphan_state_under_recovery_guard(dry_run=False)
            identity_token = self._acquire_company_identity_guard()
            identity_error: Exception | None = None
            try:
                self._prepare_company_identity_commit(state)
                self._commit_batch_with_publication_guard(state)
            except Exception as exc:
                identity_error = exc
                raise
            finally:
                try:
                    self._release_lock_token(identity_token)
                except Exception as release_error:
                    if identity_error is not None:
                        _append_secondary_error_note(
                            identity_error,
                            release_error,
                            action="company identity guard release failed",
                        )
                    else:
                        raise
        except Exception as exc:
            primary_error = exc
            raise
        finally:
            try:
                self._release_lock_token(recovery_token)
            except Exception as release_error:
                if primary_error is not None:
                    _append_secondary_error_note(
                        primary_error,
                        release_error,
                        action="recovery guard release failed during identity commit",
                    )
                else:
                    raise

    def _commit_batch_with_publication_guard(self, state: _ActiveBatchState) -> None:
        """在 target publication guard 内执行 physical swap 与 precommit restore。

        Args:
            state: 已完成 staging 校验的活动 batch state。

        Returns:
            无。

        Raises:
            RuntimeFileLockError: publication guard 获取或释放失败时抛出。
            OSError: swap、journal 或 restore 失败时抛出。
            CompanyTickerIdentityCorruptionError: commit-time target 存在但不是
                non-symlink directory 时抛出。
        """

        publication_token = self._acquire_publication_guard(state.token.ticker)
        primary_error: Exception | None = None
        try:
            target_stat = self._lstat_optional_storage_path(
                state.target_ticker_dir,
                action="检查 commit backup target ticker directory",
            )
            if target_stat is not None and not stat.S_ISDIR(target_stat.st_mode):
                raise CompanyTickerIdentityCorruptionError(kind="invalid_descriptor")
            if target_stat is not None:
                self._replace_directory(state.target_ticker_dir, state.backup_dir)
            self._write_batch_journal(state, _PHASE_BACKED_UP_TARGET)
            self._replace_directory(state.staging_ticker_dir, state.target_ticker_dir)
            self._write_batch_journal(state, _PHASE_SWAPPED_TARGET)
            self._write_batch_journal(state, _PHASE_COMMITTED)
        except Exception as exc:
            primary_error = exc
            try:
                self._rollback_precommit_batch(state)
            except Exception as rollback_error:
                primary_error.add_note(
                    "commit_batch rollback failed; journal/backup/staging recovery evidence retained"
                )
                raise primary_error from rollback_error
            raise
        finally:
            try:
                self._release_lock_token(publication_token)
            except Exception as release_error:
                if primary_error is not None:
                    _append_secondary_error_note(
                        primary_error,
                        release_error,
                        action="publication guard release failed",
                    )
                else:
                    if state.phase == _PHASE_COMMITTED:
                        Log.warn(
                            "commit_batch 已 durable 提交但 publication guard 释放失败，"
                            "将作为 post-commit terminal error 抛出: "
                            f"ticker={state.token.ticker}",
                            module=self.MODULE,
                        )
                    raise

    def _prepare_company_identity_commit(self, state: _ActiveBatchState) -> None:
        """权威合并 CompanyMeta 并在 physical publication 前校验唯一性。

        Args:
            state: 已持 writer、recovery 与 company identity guards 的 batch state。

        Returns:
            无。

        Raises:
            CompanyTickerAliasConflictError: incoming lookup ticker 属于另一 corpus 时抛出。
            CompanyTickerIdentityCorruptionError: published descriptor/meta/index 损坏时抛出。
            CompanyMetaConcurrentUpdateError: intent 的乐观前置条件失效时抛出。
            RuntimeFileLockError: publication guard 获取或释放失败时抛出。
            OSError: descriptor/meta 读取或最终 meta staging 写入失败时抛出。
            ValueError: staged descriptor 或 intent 不匹配时抛出。
        """

        staged_canonical = _read_identity_descriptor(
            state.staging_ticker_dir,
            _TICKER_IDENTITY_NAMESPACE,
            expected_external_identity=state.token.ticker,
        )
        final_meta: CompanyMeta | None = None
        if state.company_meta_intent is not None:
            current_published = self._read_current_company_meta_for_commit(state)
            final_meta = merge_company_meta_for_commit(
                current_published=current_published,
                intent=state.company_meta_intent,
                committed_at=now_iso8601(),
            )
            _write_json(
                state.staging_ticker_dir / _SOURCE_META_FILENAME,
                final_meta.to_dict(),
            )
        published_identities = self._scan_actual_published_company_identities()
        unique_index = self._build_unique_company_identity_index(published_identities)
        incoming_lookup_tickers = (
            final_meta.ticker_identity.lookup_tickers() if final_meta is not None else (staged_canonical,)
        )
        for lookup_ticker in incoming_lookup_tickers:
            existing_owner = unique_index.get(lookup_ticker)
            if existing_owner is None or existing_owner == staged_canonical:
                continue
            raise CompanyTickerAliasConflictError(
                alias=lookup_ticker,
                existing_canonical_ticker=existing_owner,
                incoming_canonical_ticker=staged_canonical,
            )

    def _read_current_company_meta_for_commit(
        self,
        state: _ActiveBatchState,
    ) -> CompanyMeta | None:
        """在 incoming publication guard 内读取 authoritative current CompanyMeta。

        Args:
            state: 已持 writer、recovery 与 company identity guards 的 batch state。

        Returns:
            descriptor 合法但 meta 缺失时返回 ``None``；否则返回 strict CompanyMeta。

        Raises:
            CompanyTickerIdentityCorruptionError: descriptor、meta 或 identity mismatch 时抛出。
            RuntimeFileLockError: publication guard 获取或释放失败时抛出。
            OSError: filesystem 访问失败时抛出。
        """

        publication_token = self._acquire_publication_guard(state.token.ticker)
        primary_error: Exception | None = None
        try:
            directory_stat = self._lstat_optional_storage_path(
                state.target_ticker_dir,
                action="检查 authoritative ticker directory",
            )
            if directory_stat is None:
                return None
            identity = self._read_published_company_identity(
                state.target_ticker_dir,
                expected_storage_key=state.target_ticker_dir.name,
                known_directory_stat=directory_stat,
            )
            return identity.company_meta
        except Exception as exc:
            primary_error = exc
            raise
        finally:
            self._release_lock_after_operation(
                publication_token,
                primary_error=primary_error,
                action="authoritative publication guard release",
            )

    def _scan_actual_published_company_identities(
        self,
    ) -> tuple[_PublishedCompanyIdentity, ...]:
        """扫描实际 published corpus 并严格读取 descriptor 与可选 CompanyMeta。

        Caller 必须先持 workspace company identity guard；本方法按 candidate key
        排序逐一取得 publication guard，绝不枚举 backup、staging 或 lock locator。

        Args:
            无。

        Returns:
            按 private candidate key 排序的 published identity tuple。

        Raises:
            CompanyTickerIdentityCorruptionError: descriptor、meta 或 identity mismatch 时抛出。
            RuntimeFileLockError: publication guard 获取或释放失败时抛出。
            OSError: portfolio 枚举或 filesystem 访问失败时抛出。
        """

        portfolio_stat = self._lstat_optional_storage_path(
            self.portfolio_root,
            action="检查 published ticker root",
        )
        if portfolio_stat is None:
            return ()
        if not stat.S_ISDIR(portfolio_stat.st_mode):
            raise CompanyTickerIdentityCorruptionError(kind="invalid_descriptor")
        identities: list[_PublishedCompanyIdentity] = []
        candidates = sorted(
            (
                candidate
                for candidate in _list_directory(
                    self.portfolio_root,
                    action="枚举 actual published ticker root",
                )
                if not candidate.name.startswith(".")
            ),
            key=lambda item: item.name,
        )
        for candidate in candidates:
            publication_token = self._acquire_publication_guard_for_key(candidate.name)
            primary_error: Exception | None = None
            try:
                directory_stat = self._lstat_optional_storage_path(
                    candidate,
                    action="检查 published ticker directory",
                )
                if directory_stat is None:
                    continue
                identities.append(
                    self._read_published_company_identity(
                        candidate,
                        expected_storage_key=candidate.name,
                        known_directory_stat=directory_stat,
                    )
                )
            except Exception as exc:
                primary_error = exc
                raise
            finally:
                self._release_lock_after_operation(
                    publication_token,
                    primary_error=primary_error,
                    action="published corpus publication guard release",
                )
        return tuple(identities)

    def _read_published_company_identity(
        self,
        directory: Path,
        *,
        expected_storage_key: str,
        known_directory_stat: os.stat_result,
    ) -> _PublishedCompanyIdentity:
        """分类并读取单个 published corpus identity。

        Args:
            directory: actual portfolio 直系条目。
            expected_storage_key: 枚举得到的 exact locator key。
            known_directory_stat: 通过显式 ``os.lstat`` 取得的目录状态。

        Returns:
            descriptor canonical 与可选 strict CompanyMeta。

        Raises:
            CompanyTickerIdentityCorruptionError: descriptor、meta 或 identity mismatch 时抛出。
            OSError: permission 或普通 filesystem I/O 失败时抛出。
        """

        if not stat.S_ISDIR(known_directory_stat.st_mode):
            raise CompanyTickerIdentityCorruptionError(kind="invalid_descriptor")
        descriptor_path = _identity_descriptor_path(directory)
        descriptor_stat = self._lstat_optional_storage_path(
            descriptor_path,
            action="检查 ticker identity descriptor",
        )
        if descriptor_stat is None or not stat.S_ISREG(descriptor_stat.st_mode):
            raise CompanyTickerIdentityCorruptionError(kind="invalid_descriptor")
        try:
            canonical_ticker = _read_identity_descriptor(
                directory,
                _TICKER_IDENTITY_NAMESPACE,
                expected_storage_key=expected_storage_key,
            )
        except (FileNotFoundError, KeyError, TypeError, ValueError) as exc:
            raise CompanyTickerIdentityCorruptionError(
                kind="invalid_descriptor",
            ) from exc

        meta_path = directory / _SOURCE_META_FILENAME
        meta_stat = self._lstat_optional_storage_path(
            meta_path,
            action="检查 published CompanyMeta",
        )
        if meta_stat is None:
            return _PublishedCompanyIdentity(
                canonical_ticker=canonical_ticker,
                company_meta=None,
            )
        if not stat.S_ISREG(meta_stat.st_mode):
            raise CompanyTickerIdentityCorruptionError(
                kind="invalid_meta",
                lookup_ticker=canonical_ticker,
            )
        try:
            company_meta = CompanyMeta.from_dict(_read_json_object(meta_path))
        except (FileNotFoundError, KeyError, TypeError, ValueError) as exc:
            raise CompanyTickerIdentityCorruptionError(
                kind="invalid_meta",
                lookup_ticker=canonical_ticker,
            ) from exc
        meta_identity = company_meta.ticker_identity
        if meta_identity.canonical_ticker != canonical_ticker:
            raise CompanyTickerIdentityCorruptionError(
                kind="identity_mismatch",
                lookup_ticker=canonical_ticker,
            )
        return _PublishedCompanyIdentity(
            canonical_ticker=canonical_ticker,
            company_meta=company_meta,
        )

    def _build_unique_company_identity_index(
        self,
        identities: tuple[_PublishedCompanyIdentity, ...],
    ) -> dict[str, str]:
        """从 descriptor canonicals 与 valid CompanyMeta aliases 派生唯一 index。

        Args:
            identities: authoritative published identity scan 结果。

        Returns:
            normalized lookup ticker 到唯一 canonical corpus 的映射。

        Raises:
            CompanyTickerIdentityCorruptionError: 任一 lookup ticker 有多个 owner 时抛出。
        """

        index: dict[str, str] = {}
        for identity in identities:
            self._register_company_identity_owner(
                index,
                lookup_ticker=identity.canonical_ticker,
                canonical_ticker=identity.canonical_ticker,
            )
        for identity in identities:
            if identity.company_meta is None:
                continue
            for alias in identity.company_meta.ticker_identity.accepted_aliases:
                self._register_company_identity_owner(
                    index,
                    lookup_ticker=alias,
                    canonical_ticker=identity.canonical_ticker,
                )
        return index

    def _register_company_identity_owner(
        self,
        index: dict[str, str],
        *,
        lookup_ticker: str,
        canonical_ticker: str,
    ) -> None:
        """向唯一 index 登记一个 owner。

        Args:
            index: 正在构建的单值 index。
            lookup_ticker: canonical 或 accepted alias。
            canonical_ticker: corpus owner。

        Returns:
            无。

        Raises:
            CompanyTickerIdentityCorruptionError: lookup ticker 已属于另一 owner 时抛出。
        """

        existing_owner = index.get(lookup_ticker)
        if existing_owner is not None and existing_owner != canonical_ticker:
            raise CompanyTickerIdentityCorruptionError(
                kind="duplicate_owner",
                lookup_ticker=lookup_ticker,
            )
        index[lookup_ticker] = canonical_ticker

    def _lstat_optional_storage_path(
        self,
        path: Path,
        *,
        action: str,
    ) -> os.stat_result | None:
        """用显式 ``os.lstat`` 区分缺失、结构状态与 operational I/O。

        Args:
            path: storage owner 已派生的 locator。
            action: 不含 path 的操作说明。

        Returns:
            路径存在时的 lstat；``ENOENT`` 时返回 ``None``。

        Raises:
            OSError: permission 或其它普通 filesystem failure 时抛出 path-free 异常。
        """

        try:
            return os.lstat(path)
        except OSError as exc:
            if exc.errno == errno.ENOENT:
                return None
            _raise_path_free_error(_project_filesystem_error(exc, action=action))

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
        _read_identity_descriptor(
            staging_ticker_dir,
            _TICKER_IDENTITY_NAMESPACE,
            expected_external_identity=state.token.ticker,
        )
        for source_kind in (SourceKind.FILING, SourceKind.MATERIAL):
            self._validate_complete_source_kind_tree(state, source_kind)

    def _validate_complete_source_kind_tree(
        self,
        state: _ActiveBatchState,
        source_kind: SourceKind,
    ) -> dict[str, dict[str, JsonValue]]:
        """校验一种 source kind 的目录、manifest 与完整 source 双向关系。

        Args:
            state: 当前 commit 的内部 transaction state。
            source_kind: filing 或 material。

        Returns:
            以 exact external document ID 为键的已验证 complete source meta。

        Raises:
            ValueError: source root、manifest 或 source 业务事实非法时抛出。
            OSError: staging tree 读取失败时抛出。
        """

        source_root = state.staging_ticker_dir / _source_dir_name(source_kind)
        self._require_contained_path(
            source_root,
            state.staging_ticker_dir,
            label=f"{source_kind.value} source root",
        )
        inspection = _inspect_source_kind_unguarded(
            ticker=state.token.ticker,
            source_kind=source_kind,
            ticker_dir=state.staging_ticker_dir,
            source_root=source_root,
            requested_document_id=None,
        )
        if (
            inspection.shared_manifest_reasons
            or inspection.repair_blocked_reason is not None
            or len(inspection.canonical_manifest_items) != len(inspection.inventory)
        ):
            raise ValueError(
                f"{source_kind.value} source publication 不满足 complete canonical manifest contract"
            )
        validated_meta: dict[str, dict[str, JsonValue]] = {}
        for source_inspection in inspection.inventory:
            if (
                source_inspection.content_classification.status
                is not SourceIntegrityStatus.COMPLETE
                or source_inspection.classification.status
                is not SourceIntegrityStatus.COMPLETE
                or source_inspection.persisted_meta is None
                or source_inspection.canonical_manifest_item is None
            ):
                raise ValueError(
                    f"{source_kind.value} source publication 只允许 COMPLETE source"
                )
            self._validate_staging_source_uri_and_containment(
                state,
                source_kind,
                source_inspection,
            )
            validated_meta[source_inspection.classification.document_id] = dict(
                source_inspection.persisted_meta
            )
        return validated_meta

    def _validate_staging_source_uri_and_containment(
        self,
        state: _ActiveBatchState,
        source_kind: SourceKind,
        inspection: _SourcePublicationInspection,
    ) -> None:
        """校验 inspector 之外由 commit owner 保留的 staging locator 资格。

        Args:
            state: 当前 commit 的内部 transaction state。
            source_kind: filing 或 material。
            inspection: 同一次 whole-kind payload 中的 complete source inspection。

        Returns:
            无。

        Raises:
            ValueError: staging URI 不等于 exact physical identity，或 locator 越出
                staging ticker/source root 时抛出。
            RuntimeError: inspector 的 complete payload 违反内部 files 不变量时抛出。
            OSError: containment operational I/O 失败时抛出 path-free 异常。
        """

        persisted_meta = inspection.persisted_meta
        if persisted_meta is None:
            raise RuntimeError("COMPLETE source inspection 缺少 persisted meta")
        raw_files = persisted_meta.get("files")
        if not isinstance(raw_files, list) or len(raw_files) != len(inspection.files):
            raise RuntimeError("COMPLETE source inspection files payload 不一致")
        source_root = state.staging_ticker_dir / _source_dir_name(source_kind)
        for raw_file, inspected_file in zip(raw_files, inspection.files, strict=True):
            if not isinstance(raw_file, Mapping):
                raise RuntimeError("COMPLETE source inspection file entry 非 object")
            descriptor = inspected_file.descriptor
            physical_path = inspected_file.physical_path
            source_dir = physical_path.parent
            self._require_contained_path(
                source_dir,
                source_root,
                label=f"{source_kind.value} staging source directory",
            )
            self._require_contained_regular_file(
                physical_path,
                state.staging_ticker_dir,
                label=f"{source_kind.value} staging source file",
            )
            expected_uri = (
                f"local://{state.staging_ticker_dir.name}/"
                f"{_source_dir_name(source_kind)}/{source_dir.name}/{descriptor.name}"
            )
            if raw_file.get("uri") != expected_uri:
                raise ValueError("source file.uri 与 staged physical file 不一致")

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

        try:
            if root.is_symlink():
                raise ValueError(f"{label} root 禁止 symlink")
            resolved_root = root.resolve(strict=False)
            resolved_path = path.resolve(strict=False)
            resolved_path.relative_to(resolved_root)
        except ValueError:
            _raise_path_free_error(ValueError(f"{label} 越出 staging root"))
        except OSError as exc:
            _raise_path_free_error(_project_filesystem_error(exc, action="校验 storage containment"))

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

        try:
            target.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            _raise_path_free_error(
                _project_filesystem_error(
                    exc,
                    action="准备 storage directory replace target",
                )
            )
        if target.exists() or target.is_symlink():
            raise OSError("directory replace target 已存在")
        source_parent = source.parent
        target_parent = target.parent
        try:
            os.replace(source, target)
        except OSError as exc:
            _raise_path_free_error(_project_filesystem_error(exc, action="原子替换 storage directory"))
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
        try:
            shutil.rmtree(path)
        except OSError as exc:
            _raise_path_free_error(_project_filesystem_error(exc, action="删除 storage directory"))
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
                f"rollback_batch 写入 journal 失败，但仍继续清理 staging 与释放锁: ticker={state.token.ticker}",
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

        external_ticker = _require_external_identity(ticker, field_name="ticker")
        batch_ticker = _require_external_identity(batch.ticker, field_name="batch ticker")
        transaction_id = batch.transaction_id.strip()
        if not transaction_id:
            raise ValueError("无效的 batch token：transaction_id 不能为空")
        with self._batch_condition:
            state = self._active_batches.get(transaction_id)
        if state is None:
            raise ValueError("无效的 batch token：transaction 未在当前 storage core 登记")
        canonical_token = BatchToken(
            transaction_id=state.token.transaction_id,
            ticker=state.token.ticker,
        )
        supplied_token = BatchToken(
            transaction_id=transaction_id,
            ticker=batch_ticker,
        )
        if canonical_token != supplied_token:
            raise ValueError("无效的 batch token：canonical capability 不匹配")
        if batch_ticker != external_ticker:
            raise ValueError("无效的 batch token：ticker 与 mutation scope 不匹配")
        if state.lifecycle != _BATCH_LIFECYCLE_OPEN:
            raise ValueError("无效的 batch token：transaction 已进入终态")
        return state

    def _reserve_batch_ticker(self, ticker: str) -> None:
        """阻塞取得当前 repository instance 的 ticker writer reservation。

        Args:
            ticker: 已校验的 exact external ticker。

        Returns:
            无；返回时当前线程独占本地 reservation。

        Raises:
            无。
        """

        with self._batch_condition:
            while ticker in self._reserved_batch_tickers or ticker in self._active_transaction_by_ticker:
                self._batch_condition.wait()
            self._reserved_batch_tickers.add(ticker)

    def _release_batch_ticker_reservation(self, ticker: str) -> None:
        """释放未登记为 active batch 的本地 reservation 并通知等待者。

        Args:
            ticker: 已校验的 exact external ticker。

        Returns:
            无。

        Raises:
            无。
        """

        with self._batch_condition:
            self._reserved_batch_tickers.discard(ticker)
            self._batch_condition.notify_all()

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
        release_error: Exception | None = None
        try:
            self._release_lock_token(state.writer_lock_token)
        except Exception as exc:
            release_error = exc
            if primary_error is None:
                pass
            else:
                _append_secondary_error_note(
                    primary_error,
                    release_error,
                    action="writer mutex release failed during terminal cleanup",
                )
                Log.warn(
                    "transaction 主异常后 writer mutex 释放失败，已消费 capability并保留主异常: "
                    f"ticker={state.token.ticker} error_type={release_error.__class__.__name__}",
                    module=self.MODULE,
                )
        finally:
            # 复杂逻辑说明：先释放跨进程锁，再清除本地 active 标记并统一唤醒等待者。
            with self._batch_condition:
                self._active_batches.pop(state.token.transaction_id, None)
                indexed_transaction_id = self._active_transaction_by_ticker.get(state.token.ticker)
                if indexed_transaction_id == state.token.transaction_id:
                    self._active_transaction_by_ticker.pop(state.token.ticker, None)
                self._reserved_batch_tickers.discard(state.token.ticker)
                self._batch_condition.notify_all()
        if release_error is not None and primary_error is None:
            raise release_error

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
        primary_error: Exception | None = None
        try:
            actions = self._recover_orphan_state_under_recovery_guard(dry_run=dry_run)
        except Exception as exc:
            primary_error = exc
            raise
        finally:
            self._release_lock_after_operation(
                recovery_token,
                primary_error=primary_error,
                action="orphan recovery guard release",
            )
        return tuple(actions)

    def _recover_orphan_state_under_recovery_guard(self, *, dry_run: bool) -> list[str]:
        """在 caller 已持 recovery guard 时恢复全部 orphan state。

        Args:
            dry_run: 是否只返回拟执行动作。

        Returns:
            按扫描顺序记录的恢复动作列表。

        Raises:
            RuntimeFileLockError: writer、identity 或 publication guard 操作失败时抛出。
            OSError: evidence 枚举、读取或 physical restore 失败时抛出。
        """

        actions = self._recover_orphan_batch_dirs(dry_run=dry_run)
        actions.extend(self._recover_orphan_backup_dirs(dry_run=dry_run))
        return actions

    def _should_manage_batch_state(self) -> bool:
        """判断当前是否需要接触 batch 持久化状态。

        Args:
            无。

        Returns:
            若应访问 `.dayu` 下的 batch 状态则返回 `True`。

        Raises:
            无。
        """

        return (
            self._create_directories or self.dayu_root.exists() or self.batch_root.exists() or self.backup_root.exists()
        )

    def _ensure_batch_storage_dirs(self) -> None:
        """确保 `.dayu` 下的 batch 基础目录存在。

        Args:
            无。

        Returns:
            无。

        Raises:
            OSError: 目录创建失败时抛出。
        """

        try:
            self.dayu_root.mkdir(parents=True, exist_ok=True)
            self.batch_root.mkdir(parents=True, exist_ok=True)
            self.backup_root.mkdir(parents=True, exist_ok=True)
            self._batch_lock_root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            _raise_path_free_error(_project_filesystem_error(exc, action="准备 batch storage directory"))

    def _ticker_lock_path(self, ticker: str) -> Path:
        """返回指定 ticker 的事务锁路径。

        Args:
            ticker: 股票代码。

        Returns:
            锁文件路径。

        Raises:
            ValueError: ticker identity 非法时抛出。
        """

        ticker_key = _derive_storage_key(
            _TICKER_IDENTITY_NAMESPACE,
            _require_external_identity(ticker, field_name="ticker"),
        )
        return self._ticker_lock_path_for_key(ticker_key)

    def _ticker_lock_path_for_key(self, ticker_key: str) -> Path:
        """返回 private ticker key 对应的事务锁路径。

        Args:
            ticker_key: storage identity owner 已派生或从受控 locator 解析的 private key。

        Returns:
            writer mutex 文件路径。

        Raises:
            ValueError: private key 不是单一路径组件时抛出。
        """

        return self._batch_lock_root / f"{_normalize_entry_name(ticker_key)}.lock"

    def _publication_lock_path(self, ticker: str) -> Path:
        """返回指定 ticker 的 publication guard 路径。

        Args:
            ticker: 股票代码。

        Returns:
            独立于 writer mutex 的 publication lock 路径。

        Raises:
            ValueError: ticker 非法时抛出。
        """

        ticker_key = _derive_storage_key(
            _TICKER_IDENTITY_NAMESPACE,
            _require_external_identity(ticker, field_name="ticker"),
        )
        return self._publication_lock_path_for_key(ticker_key)

    def _publication_lock_path_for_key(self, ticker_key: str) -> Path:
        """返回 private ticker key 对应的 publication guard 路径。

        Args:
            ticker_key: storage identity owner 已派生或从受控 locator 解析的 private key。

        Returns:
            publication guard 文件路径。

        Raises:
            ValueError: private key 不是单一路径组件时抛出。
        """

        return self._batch_lock_root / f"{_normalize_entry_name(ticker_key)}{_PUBLICATION_LOCK_SUFFIX}"

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

        return _acquire_storage_lock_token(lock_path, blocking=blocking)

    def _release_lock_token(self, token: RuntimeFileLockToken) -> None:
        """释放 runtime 文件锁 token。

        Args:
            token: 已持锁的 runtime 文件锁 token。

        Returns:
            无。

        Raises:
            RuntimeFileLockError: 解锁失败时抛出。
        """

        _release_storage_lock_token(token)

    def _release_lock_after_operation(
        self,
        token: RuntimeFileLockToken,
        *,
        primary_error: BaseException | None,
        action: str,
    ) -> None:
        """释放锁，并在已有主异常时保留原始失败语义。

        Args:
            token: 已持有的 runtime 文件锁 token。
            primary_error: 受锁操作已经抛出的主异常；成功时为 ``None``。
            action: 不包含 filesystem locator 的释放动作说明。

        Returns:
            无。

        Raises:
            RuntimeFileLockError: 操作成功但释放锁失败时抛出。
        """

        try:
            self._release_lock_token(token)
        except Exception as release_error:
            if primary_error is None:
                raise
            primary_error.add_note(f"{action}失败：{release_error}")

    def _acquire_ticker_lock(self, ticker: str) -> RuntimeFileLockToken:
        """获取某个 ticker 的跨进程事务锁。

        Args:
            ticker: 股票代码。

        Returns:
            已持锁的 runtime 文件锁 token。

        Raises:
            ValueError: ticker identity 非法时抛出。
            RuntimeFileLockError: 锁文件访问失败时抛出。
        """

        external_ticker = _require_external_identity(ticker, field_name="ticker")
        return self._acquire_lock_token(
            self._ticker_lock_path(external_ticker),
            blocking=True,
        )

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

    def _acquire_publication_guard_for_key(
        self,
        ticker_key: str,
    ) -> RuntimeFileLockToken:
        """按 private ticker candidate 获取 publication guard。

        该入口只供 company inventory 在尚未从 descriptor 恢复 external ticker 时使用。

        Args:
            ticker_key: 从 published/backup/lock locator 枚举到的 private candidate key。

        Returns:
            已持有 publication guard 的 runtime lock token。

        Raises:
            ValueError: private key 不是单一路径组件时抛出。
            RuntimeFileLockError: guard 获取失败时抛出。
        """

        return self._acquire_lock_token(
            self._publication_lock_path_for_key(ticker_key),
            blocking=True,
        )

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

    def _acquire_company_identity_guard(self) -> RuntimeFileLockToken:
        """获取 workspace company identity guard。

        Args:
            无。

        Returns:
            已持有的 runtime lock token。

        Raises:
            RuntimeFileLockError: identity guard 获取失败时抛出。
        """

        return self._acquire_lock_token(
            self._company_identity_lock_path,
            blocking=True,
        )

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
        for token_dir in sorted(
            _list_directory(self.batch_root, action="枚举 batch staging root"),
            key=lambda item: item.name,
        ):
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
        with self._batch_condition:
            if token_dir.name in self._active_batches:
                return actions
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
            actions.append(f"skip batch transaction={token_dir.name} reason=unparseable_journal")
            return actions
        if frozenset(journal) != _JOURNAL_FIELDS:
            actions.append(f"skip batch transaction={token_dir.name} reason=invalid_journal_fields")
            return actions
        transaction_id_value = journal["transaction_id"]
        ticker_value = journal["ticker"]
        phase_value = journal["phase"]
        if not all(isinstance(value, str) for value in (transaction_id_value, ticker_value, phase_value)):
            actions.append(f"skip batch transaction={token_dir.name} reason=invalid_journal_values")
            return actions
        transaction_id = transaction_id_value.strip()
        ticker = ticker_value
        phase = phase_value.strip()
        if transaction_id != token_dir.name or not ticker:
            actions.append(f"skip batch transaction={token_dir.name} reason=identity_mismatch")
            return actions
        try:
            external_ticker = _require_external_identity(ticker, field_name="journal ticker")
            ticker_key = _derive_storage_key(
                _TICKER_IDENTITY_NAMESPACE,
                external_ticker,
            )
        except ValueError:
            actions.append(f"skip batch transaction={token_dir.name} reason=invalid_journal_ticker")
            return actions
        if phase not in _RECOVERY_PHASES:
            actions.append(f"skip batch transaction={token_dir.name} reason=invalid_journal_values")
            return actions
        ticker_token = self._try_acquire_recovery_ticker_lock(external_ticker)
        if ticker_token is None:
            return actions
        ticker_error: Exception | None = None
        try:
            target_dir = self._target_ticker_dir(external_ticker)
            backup_dir = self.backup_root / f"{ticker_key}.bak.{transaction_id}"
            staging_dir = token_dir / ticker_key
            if not all(
                (
                    _is_contained_recovery_path(target_dir, self.portfolio_root),
                    _is_contained_recovery_path(backup_dir, self.backup_root),
                    _is_contained_recovery_path(staging_dir, token_dir),
                    _is_contained_recovery_path(journal_path, token_dir),
                )
            ):
                actions.append(f"skip batch transaction={transaction_id} reason=invalid_recovery_locator")
                return actions
            try:
                for identity_directory, expected_storage_key in (
                    (target_dir, None),
                    (backup_dir, ticker_key),
                    (staging_dir, None),
                ):
                    if not (identity_directory.exists() or identity_directory.is_symlink()):
                        continue
                    _read_identity_descriptor(
                        identity_directory,
                        _TICKER_IDENTITY_NAMESPACE,
                        expected_external_identity=external_ticker,
                        expected_storage_key=expected_storage_key,
                    )
            except (FileNotFoundError, ValueError, OSError):
                actions.append(f"skip batch transaction={transaction_id} reason=invalid_identity_descriptor")
                return actions
            identity_token = self._acquire_company_identity_guard()
            identity_error: Exception | None = None
            try:
                publication_token = self._acquire_publication_guard(external_ticker)
                publication_error: Exception | None = None
                try:
                    if phase == _PHASE_COMMITTED:
                        if not target_dir.exists():
                            actions.append(
                                f"preserve committed evidence ticker={external_ticker} "
                                f"transaction={transaction_id} reason=missing_target"
                            )
                            return actions
                        if backup_dir.exists():
                            actions.append(
                                f"delete backup ticker={external_ticker} transaction={transaction_id} phase={phase}"
                            )
                            if not dry_run:
                                self._remove_directory(backup_dir)
                    elif phase in {_PHASE_BACKED_UP_TARGET, _PHASE_SWAPPED_TARGET}:
                        if target_dir.exists():
                            actions.append(
                                f"remove uncommitted target ticker={external_ticker} "
                                f"transaction={transaction_id} phase={phase}"
                            )
                            if not dry_run:
                                if staging_dir.exists():
                                    self._remove_directory(target_dir)
                                else:
                                    self._replace_directory(target_dir, staging_dir)
                        if backup_dir.exists():
                            actions.append(
                                f"restore backup ticker={external_ticker} transaction={transaction_id} phase={phase}"
                            )
                            if not dry_run:
                                self._replace_directory(backup_dir, target_dir)
                    elif backup_dir.exists() and not target_dir.exists():
                        actions.append(
                            f"restore backup ticker={external_ticker} transaction={transaction_id} "
                            f"phase={phase or 'unknown'}"
                        )
                        if not dry_run:
                            self._replace_directory(backup_dir, target_dir)
                    elif backup_dir.exists() and target_dir.exists() and phase != _PHASE_STARTED:
                        actions.append(
                            f"preserve ambiguous backup ticker={external_ticker} "
                            f"transaction={transaction_id} phase={phase or 'unknown'}"
                        )
                        return actions
                except Exception as exc:
                    publication_error = exc
                    raise
                finally:
                    self._release_lock_after_operation(
                        publication_token,
                        primary_error=publication_error,
                        action="orphan batch publication guard release",
                    )
                actions.append(
                    f"cleanup batch ticker={external_ticker} transaction={transaction_id} phase={phase or 'unknown'}"
                )
                if not dry_run:
                    self._remove_directory(token_dir)
            except Exception as exc:
                identity_error = exc
                raise
            finally:
                self._release_lock_after_operation(
                    identity_token,
                    primary_error=identity_error,
                    action="orphan batch identity guard release",
                )
        except Exception as exc:
            ticker_error = exc
            raise
        finally:
            self._release_lock_after_operation(
                ticker_token,
                primary_error=ticker_error,
                action="orphan batch writer guard release",
            )
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
        for backup_dir in sorted(
            _list_directory(self.backup_root, action="枚举 batch backup root"),
            key=lambda item: item.name,
        ):
            if backup_dir.is_symlink() or not backup_dir.is_dir():
                continue
            parsed = _parse_backup_directory_name(backup_dir.name)
            if parsed is None:
                continue
            ticker_key, token_id = parsed
            token_dir = self.batch_root / token_id
            if token_dir.exists():
                continue
            try:
                external_ticker = _read_identity_descriptor(
                    backup_dir,
                    _TICKER_IDENTITY_NAMESPACE,
                    expected_storage_key=ticker_key,
                )
                expected_ticker_key = _derive_storage_key(
                    _TICKER_IDENTITY_NAMESPACE,
                    external_ticker,
                )
                if ticker_key != expected_ticker_key:
                    raise ValueError("backup locator 与 identity descriptor 不一致")
            except (FileNotFoundError, ValueError, OSError):
                actions.append(f"preserve backup transaction={token_id} reason=invalid_identity_descriptor")
                continue
            ticker_token = self._try_acquire_recovery_ticker_lock(external_ticker)
            if ticker_token is None:
                continue
            ticker_error: Exception | None = None
            try:
                target_dir = self._target_ticker_dir(external_ticker)
                if not (
                    _is_contained_recovery_path(backup_dir, self.backup_root)
                    and _is_contained_recovery_path(target_dir, self.portfolio_root)
                ):
                    actions.append(
                        f"preserve backup ticker={external_ticker} transaction={token_id} "
                        "reason=invalid_recovery_locator"
                    )
                    continue
                if target_dir.exists() or target_dir.is_symlink():
                    try:
                        _read_identity_descriptor(
                            target_dir,
                            _TICKER_IDENTITY_NAMESPACE,
                            expected_external_identity=external_ticker,
                        )
                    except (FileNotFoundError, ValueError, OSError):
                        actions.append(
                            f"preserve backup ticker={external_ticker} "
                            f"transaction={token_id} reason=target_identity_mismatch"
                        )
                        continue
                identity_token = self._acquire_company_identity_guard()
                identity_error: Exception | None = None
                try:
                    publication_token = self._acquire_publication_guard(external_ticker)
                    publication_error: Exception | None = None
                    try:
                        if target_dir.exists():
                            actions.append(f"delete backup ticker={external_ticker} transaction={token_id}")
                            if not dry_run:
                                self._remove_directory(backup_dir)
                            continue
                        actions.append(f"restore backup ticker={external_ticker} transaction={token_id}")
                        if not dry_run:
                            self._replace_directory(backup_dir, target_dir)
                    except Exception as exc:
                        publication_error = exc
                        raise
                    finally:
                        self._release_lock_after_operation(
                            publication_token,
                            primary_error=publication_error,
                            action="orphan backup publication guard release",
                        )
                except Exception as exc:
                    identity_error = exc
                    raise
                finally:
                    self._release_lock_after_operation(
                        identity_token,
                        primary_error=identity_error,
                        action="orphan backup identity guard release",
                    )
            except Exception as exc:
                ticker_error = exc
                raise
            finally:
                self._release_lock_after_operation(
                    ticker_token,
                    primary_error=ticker_error,
                    action="orphan backup writer guard release",
                )
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

        external_ticker = _require_external_identity(handle.ticker, field_name="ticker")
        external_document_id = _require_external_identity(
            handle.document_id,
            field_name="document_id",
        )
        if isinstance(handle, ProcessedHandle):
            return self._processed_dir_for_read(external_ticker, external_document_id)
        source_kind = _normalize_source_kind(handle.source_kind)
        return _identity_directory_for_read(
            self._source_root_for_read(external_ticker, source_kind),
            _source_identity_namespace(source_kind),
            external_document_id,
        )

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
        try:
            candidate = (base_dir / normalized_name).resolve()
            candidate.relative_to(base_dir.resolve())
        except ValueError:
            _raise_path_free_error(ValueError("条目名称越界，禁止访问文档目录外路径"))
        except OSError as exc:
            _raise_path_free_error(_project_filesystem_error(exc, action="解析 published document 条目"))
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

        external_ticker = _require_external_identity(handle.ticker, field_name="ticker")
        self._require_state_ticker(state, external_ticker)
        external_document_id = _require_external_identity(
            handle.document_id,
            field_name="document_id",
        )
        if isinstance(handle, ProcessedHandle):
            return _ensure_identity_directory(
                state.staging_ticker_dir / "processed",
                _PROCESSED_IDENTITY_NAMESPACE,
                external_document_id,
            )
        source_kind = _normalize_source_kind(handle.source_kind)
        return _ensure_identity_directory(
            state.staging_ticker_dir / _source_dir_name(source_kind),
            _source_identity_namespace(source_kind),
            external_document_id,
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
        try:
            candidate = (base_dir / normalized_name).resolve()
            candidate.relative_to(base_dir.resolve())
        except ValueError:
            _raise_path_free_error(ValueError("条目名称越界，禁止访问文档目录外路径"))
        except OSError as exc:
            _raise_path_free_error(_project_filesystem_error(exc, action="解析 staging document 条目"))
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

        external_ticker = _require_external_identity(handle.ticker, field_name="ticker")
        if isinstance(handle, ProcessedHandle):
            meta_path = self._processed_meta_path_for_read(external_ticker, handle.document_id)
        else:
            source_kind = _normalize_source_kind(handle.source_kind)
            meta_path = self._source_meta_path_for_read(
                external_ticker,
                handle.document_id,
                source_kind,
            )
        if not meta_path.exists():
            raise FileNotFoundError(f"meta.json 不存在: ticker={handle.ticker} document_id={handle.document_id}")
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
            raise FileNotFoundError(f"staging meta 不存在: ticker={handle.ticker} document_id={handle.document_id}")
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

    def _ensure_ticker_structure(self, ticker_dir: Path, ticker: str) -> None:
        """确保 ticker 目录结构存在。

        Args:
            ticker_dir: private ticker 目录路径。
            ticker: exact external ticker。

        Returns:
            无。

        Raises:
            ValueError: ticker identity 与 private locator 不一致时抛出。
            OSError: 目录创建失败时抛出。
        """

        external_ticker = _require_external_identity(ticker, field_name="ticker")
        expected_dir = _identity_directory_path(
            ticker_dir.parent,
            _TICKER_IDENTITY_NAMESPACE,
            external_ticker,
        )
        if expected_dir != ticker_dir:
            raise ValueError("ticker identity directory 与 private locator 不一致")
        _ensure_identity_directory(
            ticker_dir.parent,
            _TICKER_IDENTITY_NAMESPACE,
            external_ticker,
        )
        for directory_name in ("filings", "materials", "processed"):
            directory = ticker_dir / directory_name
            if directory.is_symlink():
                raise ValueError("ticker storage 子目录禁止 symlink")
            directory.mkdir(parents=True, exist_ok=True)
            if not directory.is_dir():
                raise ValueError("ticker storage 子目录必须为 directory")
            self._require_contained_path(
                directory,
                ticker_dir,
                label=f"ticker storage {directory_name}",
            )

    def _require_copyable_ticker_tree(self, ticker_dir: Path) -> None:
        """在 transaction copy 前验证 published ticker tree 不含 symlink/特殊文件。

        Args:
            ticker_dir: 已由 ticker descriptor 校验的 published private directory。

        Returns:
            无。

        Raises:
            CompanyTickerIdentityCorruptionError: tree 含 symlink、特殊文件、
                missing race 或 containment escape 时抛出。
            OSError: 文件系统枚举或路径解析失败时抛出。
        """

        for path in ticker_dir.rglob("*"):
            path_stat = self._lstat_optional_storage_path(
                path,
                action="检查 published ticker tree entry",
            )
            if path_stat is None or not (stat.S_ISDIR(path_stat.st_mode) or stat.S_ISREG(path_stat.st_mode)):
                raise CompanyTickerIdentityCorruptionError(kind="invalid_descriptor")
            try:
                self._require_contained_path(
                    path,
                    ticker_dir,
                    label="published ticker tree entry",
                )
            except ValueError as exc:
                raise CompanyTickerIdentityCorruptionError(kind="invalid_descriptor") from exc

    def _storage_subdirectory_for_read(
        self,
        ticker_dir: Path,
        directory_name: str,
    ) -> Path:
        """返回并校验 ticker 下固定 storage 子目录。

        Args:
            ticker_dir: 已通过 ticker descriptor 校验的 private directory。
            directory_name: storage owner 固定子目录名。

        Returns:
            ticker private directory 下的子目录路径；不存在时返回预期路径。

        Raises:
            ValueError: 子目录是 symlink、非目录或越出 ticker root 时抛出。
            OSError: 路径解析失败时抛出。
        """

        normalized_name = _normalize_entry_name(directory_name)
        directory = ticker_dir / normalized_name
        if directory.exists() or directory.is_symlink():
            if directory.is_symlink() or not directory.is_dir():
                raise ValueError("ticker storage 子目录必须为 non-symlink directory")
            self._require_contained_path(
                directory,
                ticker_dir,
                label=f"ticker storage {normalized_name}",
            )
        return directory

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

        external_ticker = _require_external_identity(ticker, field_name="ticker")
        if state.token.ticker != external_ticker:
            raise ValueError("内部 transaction state 与 ticker 不匹配")
        return external_ticker

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

        ticker_key = _derive_storage_key(
            _TICKER_IDENTITY_NAMESPACE,
            _require_external_identity(handle.ticker, field_name="ticker"),
        )
        external_document_id = _require_external_identity(
            handle.document_id,
            field_name="document_id",
        )
        if isinstance(handle, ProcessedHandle):
            document_key = _derive_storage_key(
                _PROCESSED_IDENTITY_NAMESPACE,
                external_document_id,
            )
            return f"{ticker_key}/processed/{document_key}/{normalized_filename}"
        source_kind = _normalize_source_kind(handle.source_kind)
        document_key = _derive_storage_key(
            _source_identity_namespace(source_kind),
            external_document_id,
        )
        return f"{ticker_key}/{_source_dir_name(source_kind)}/{document_key}/{normalized_filename}"

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

        external_ticker = state.token.ticker
        payloads = [item.to_dict() for item in items]
        self._upsert_manifest_items(
            self._filing_manifest_path(external_ticker, state),
            external_ticker,
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

        external_ticker = state.token.ticker
        payloads = [item.to_dict() for item in items]
        self._upsert_manifest_items(
            self._material_manifest_path(external_ticker, state),
            external_ticker,
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

        external_ticker = state.token.ticker
        payloads = [item.to_dict() for item in items]
        self._upsert_manifest_items(
            self._processed_manifest_path(external_ticker, state),
            external_ticker,
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
            ValueError: ticker、manifest 或 document identity 不合法时抛出。
            OSError: 写入失败。
        """

        manifest = self._read_manifest(path, ticker)
        documents_map = {doc["document_id"]: doc for doc in manifest["documents"] if "document_id" in doc}
        for item in items:
            raw_document_id = item["document_id"]
            if not isinstance(raw_document_id, str):
                raise ValueError("manifest document_id 必须为字符串")
            external_document_id = _require_external_identity(
                raw_document_id,
                field_name="manifest document_id",
            )
            normalized_item = dict(item)
            normalized_item["document_id"] = external_document_id
            documents_map[external_document_id] = normalized_item
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
            ValueError: ticker、manifest 或 document identity 不合法时抛出。
            OSError: 写入失败。
        """

        external_document_id = _require_external_identity(
            document_id,
            field_name="document_id",
        )
        manifest = self._read_manifest(path, ticker)
        manifest["documents"] = [doc for doc in manifest["documents"] if doc.get("document_id") != external_document_id]
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
            ValueError: ticker、manifest 或任一 document identity 不合法时抛出。
            OSError: 写入失败时抛出。
        """

        stale_set = {_require_external_identity(document_id, field_name="document_id") for document_id in document_ids}
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

        external_ticker = _require_external_identity(ticker, field_name="ticker")
        if path.exists():
            manifest = _read_json_object(path)
            if manifest.get("ticker") != external_ticker:
                raise ValueError("manifest ticker 与请求 external ticker 不一致")
            if not isinstance(manifest.get("documents"), list):
                raise ValueError("manifest documents 必须为数组")
            return manifest
        return {
            "ticker": external_ticker,
            "updated_at": now_iso8601(),
            "documents": [],
        }

    # ========== 路径方法 ==========

    def _target_ticker_dir(self, ticker: str) -> Path:
        """返回正式 ticker 目录。

        Args:
            ticker: 股票代码。

        Returns:
            正式目录路径。

        Raises:
            ValueError: ticker identity 非法时抛出。
        """

        external_ticker = _require_external_identity(ticker, field_name="ticker")
        return _identity_directory_path(
            self.portfolio_root,
            _TICKER_IDENTITY_NAMESPACE,
            external_ticker,
        )

    def _target_ticker_dir_for_key(self, ticker_key: str) -> Path:
        """返回 private ticker key 对应的 published locator。

        Args:
            ticker_key: 从受控 published/lock/backup locator 枚举的 private key。

        Returns:
            portfolio root 下的 candidate path。

        Raises:
            ValueError: private key 不是单一路径组件时抛出。
        """

        return self.portfolio_root / _normalize_entry_name(ticker_key)

    def _ticker_identity_from_candidate_key(self, ticker_key: str) -> str:
        """从 published target 或 backup descriptor 恢复 external ticker。

        caller 必须先按同一 private key 持有 publication guard，确保 target/backup
        视图不会在恢复期间切换。lock stem 只用于发现 candidate，不能作为业务值。

        Args:
            ticker_key: published/lock/backup 扫描得到的 private candidate key。

        Returns:
            descriptor 唯一确认的 exact external ticker。

        Raises:
            FileNotFoundError: target 与 backup 都没有可验证 descriptor 时抛出。
            ValueError: descriptor、private locator 或多个 evidence 不一致时抛出。
            OSError: descriptor 或目录扫描失败时抛出。
        """

        normalized_key = _normalize_entry_name(ticker_key)
        candidate_directories: list[Path] = []
        target_dir = self._target_ticker_dir_for_key(normalized_key)
        if target_dir.exists() or target_dir.is_symlink():
            candidate_directories.append(target_dir)
        if self.backup_root.exists():
            for backup_dir in _list_directory(
                self.backup_root,
                action="枚举 ticker backup evidence",
            ):
                parsed = _parse_backup_directory_name(backup_dir.name)
                if parsed is None or parsed[0] != normalized_key:
                    continue
                if backup_dir.exists() or backup_dir.is_symlink():
                    candidate_directories.append(backup_dir)
        if not candidate_directories:
            raise FileNotFoundError("ticker candidate 缺少 identity descriptor evidence")
        identities = {
            _read_identity_descriptor(
                directory,
                _TICKER_IDENTITY_NAMESPACE,
                expected_storage_key=normalized_key,
            )
            for directory in candidate_directories
        }
        if len(identities) != 1:
            raise ValueError("ticker target/backup identity descriptor 不一致")
        external_ticker = identities.pop()
        if _derive_storage_key(_TICKER_IDENTITY_NAMESPACE, external_ticker) != normalized_key:
            raise ValueError("ticker descriptor 与 candidate private locator 不一致")
        return external_ticker

    def _ticker_dir_for_write(self, ticker: str, state: _ActiveBatchState) -> Path:
        """返回显式 transaction staging 的可写 ticker 目录。

        Args:
            ticker: 股票代码。
            state: 已解析的内部 transaction state。

        Returns:
            可写目录路径。

        Raises:
            ValueError: ticker、capability 或 identity directory 不一致时抛出。
            OSError: 目录创建失败时抛出。
        """

        external_ticker = self._require_state_ticker(state, ticker)
        self._ensure_ticker_structure(state.staging_ticker_dir, external_ticker)
        return state.staging_ticker_dir

    def _ticker_dir_for_read(self, ticker: str) -> Path:
        """返回 published ticker 目录。

        Args:
            ticker: 股票代码。

        Returns:
            可读目录路径。

        Raises:
            CompanyTickerIdentityCorruptionError: published target、descriptor、meta
                或 identity durable state 损坏时抛出。
            ValueError: ticker 非法时抛出。
            OSError: descriptor 读取失败时抛出。
        """

        external_ticker = _require_external_identity(ticker, field_name="ticker")
        ticker_dir = self._target_ticker_dir(external_ticker)
        directory_stat = self._lstat_optional_storage_path(
            ticker_dir,
            action="检查 published ticker directory for read",
        )
        if directory_stat is None:
            return ticker_dir
        identity = self._read_published_company_identity(
            ticker_dir,
            expected_storage_key=ticker_dir.name,
            known_directory_stat=directory_stat,
        )
        if identity.canonical_ticker != external_ticker:
            raise CompanyTickerIdentityCorruptionError(kind="invalid_descriptor")
        return ticker_dir

    def _ticker_dir_if_present_for_read(self, ticker: str) -> Path | None:
        """返回已存在且合法的 published ticker directory。

        Args:
            ticker: canonical 股票代码。

        Returns:
            ticker identity directory 存在时返回 canonical locator，否则返回
            ``None``。

        Raises:
            ValueError: ticker、identity root 或 descriptor 不合法时抛出。
            OSError: descriptor 读取失败时抛出。
        """

        external_ticker = _require_external_identity(ticker, field_name="ticker")
        return _identity_directory_if_present_for_read(
            self.portfolio_root,
            _TICKER_IDENTITY_NAMESPACE,
            external_ticker,
        )

    def _file_store_root_for_ticker(self, ticker: str, state: _ActiveBatchState) -> Path:
        """获取显式 transaction staging 的文件存储根目录。

        Args:
            ticker: 股票代码。
            state: 已解析的内部 transaction state。

        Returns:
            文件存储根目录。

        Raises:
            ValueError: ticker、capability 或 identity directory 不一致时抛出。
            OSError: 目录创建失败时抛出。
        """

        external_ticker = self._require_state_ticker(state, ticker)
        self._ensure_ticker_structure(state.staging_ticker_dir, external_ticker)
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
            ValueError: ticker、capability 或 ticker descriptor 不合法时抛出。
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
            ValueError: ticker、descriptor 或固定 source 子目录不合法时抛出。
            OSError: descriptor 或路径读取失败时抛出。
        """

        ticker_dir = self._ticker_dir_for_read(ticker)
        directory_name = "filings" if source_kind == SourceKind.FILING else "materials"
        return self._storage_subdirectory_for_read(ticker_dir, directory_name)

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
            ValueError: ticker、document identity、namespace 或 descriptor 不合法时抛出。
            OSError: 路径构建失败时抛出。
        """

        external_document_id = _require_external_identity(
            document_id,
            field_name="document_id",
        )
        document_dir = _ensure_identity_directory(
            self._source_root(ticker, source_kind, state),
            _source_identity_namespace(source_kind),
            external_document_id,
        )
        return document_dir / _SOURCE_META_FILENAME

    def _source_meta_path_for_read(self, ticker: str, document_id: str, source_kind: SourceKind) -> Path:
        """返回源文档 meta 路径（用于读取）。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。
            source_kind: 来源类型。

        Returns:
            meta 文件路径。

        Raises:
            ValueError: ticker、document identity、namespace 或 descriptor 不合法时抛出。
            OSError: descriptor 或路径读取失败时抛出。
        """

        external_document_id = _require_external_identity(
            document_id,
            field_name="document_id",
        )
        document_dir = _identity_directory_for_read(
            self._source_root_for_read(ticker, source_kind),
            _source_identity_namespace(source_kind),
            external_document_id,
        )
        return document_dir / _SOURCE_META_FILENAME

    def _company_meta_path_for_read(self, ticker: str) -> Path:
        """返回公司级 meta 路径（用于读取）。

        Args:
            ticker: 股票代码。

        Returns:
            公司级 meta 路径。

        Raises:
            ValueError: ticker 或 descriptor 不合法时抛出。
            OSError: descriptor 或路径读取失败时抛出。
        """

        external_ticker = _require_external_identity(ticker, field_name="ticker")
        return self._ticker_dir_for_read(external_ticker) / _SOURCE_META_FILENAME

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

        return self._source_root_for_read(ticker, SourceKind.FILING) / "filing_manifest.json"

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

        return self._source_root_for_read(ticker, SourceKind.MATERIAL) / "material_manifest.json"

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

        ticker_dir = self._ticker_dir_for_read(ticker)
        processed_root = self._storage_subdirectory_for_read(ticker_dir, "processed")
        return processed_root / "manifest.json"

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
            ValueError: ticker、document identity、capability 或 descriptor 不合法时抛出。
            OSError: 路径构建失败时抛出。
        """

        external_ticker = _require_external_identity(ticker, field_name="ticker")
        external_document_id = _require_external_identity(
            document_id,
            field_name="document_id",
        )
        return _ensure_identity_directory(
            self._ticker_dir_for_write(external_ticker, state) / "processed",
            _PROCESSED_IDENTITY_NAMESPACE,
            external_document_id,
        )

    def _processed_dir_for_read(self, ticker: str, document_id: str) -> Path:
        """获取解析产物目录路径（用于读取）。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。

        Returns:
            解析产物目录路径。

        Raises:
            ValueError: ticker、document identity、descriptor 或 processed root 不合法时抛出。
            OSError: descriptor 或路径读取失败时抛出。
        """

        external_ticker = _require_external_identity(ticker, field_name="ticker")
        external_document_id = _require_external_identity(
            document_id,
            field_name="document_id",
        )
        ticker_dir = self._ticker_dir_for_read(external_ticker)
        processed_root = self._storage_subdirectory_for_read(ticker_dir, "processed")
        return _identity_directory_for_read(
            processed_root,
            _PROCESSED_IDENTITY_NAMESPACE,
            external_document_id,
        )

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

        return self._ticker_dir_for_write(ticker, state) / "filings" / _DOWNLOAD_REJECTIONS_FILENAME

    def _download_rejections_path_for_read(self, ticker: str) -> Path:
        """返回下载拒绝注册表路径（用于读取）。

        Args:
            ticker: 股票代码。

        Returns:
            拒绝注册表路径。

        Raises:
            无。
        """

        return self._source_root_for_read(ticker, SourceKind.FILING) / _DOWNLOAD_REJECTIONS_FILENAME

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

        return self._ticker_dir_for_write(ticker, state) / "filings" / _REJECTED_FILINGS_DIRNAME

    def _rejected_filings_root_for_read(self, ticker: str) -> Path:
        """返回 rejected filings 根目录（用于读取）。

        Args:
            ticker: 股票代码。

        Returns:
            rejected filings 根目录。

        Raises:
            无。
        """

        return self._source_root_for_read(ticker, SourceKind.FILING) / _REJECTED_FILINGS_DIRNAME

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
            ValueError: ticker、document identity、capability 或 descriptor 不合法时抛出。
            OSError: 路径构建失败时抛出。
        """

        external_document_id = _require_external_identity(
            document_id,
            field_name="document_id",
        )
        return _ensure_identity_directory(
            self._rejected_filings_root(ticker, state),
            _REJECTED_FILING_IDENTITY_NAMESPACE,
            external_document_id,
        )

    def _rejected_filing_dir_for_read(self, ticker: str, document_id: str) -> Path:
        """返回单个 rejected filing 目录（用于读取）。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。

        Returns:
            文档目录路径。

        Raises:
            ValueError: ticker、document identity 或 descriptor 不合法时抛出。
            OSError: descriptor 或路径读取失败时抛出。
        """

        external_document_id = _require_external_identity(
            document_id,
            field_name="document_id",
        )
        return _identity_directory_for_read(
            self._rejected_filings_root_for_read(ticker),
            _REJECTED_FILING_IDENTITY_NAMESPACE,
            external_document_id,
        )

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
        try:
            candidate = (base_dir / normalized_name).resolve()
            candidate.relative_to(base_dir.resolve())
        except ValueError:
            _raise_path_free_error(ValueError("条目名称越界，禁止访问文档目录外路径"))
        except OSError as exc:
            _raise_path_free_error(_project_filesystem_error(exc, action="解析 rejected filing 条目"))
        return candidate
