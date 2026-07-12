"""文件系统仓储基础设施层。

提供共享实例状态、批处理事务、路径方法、manifest 操作、handle 辅助等，
作为所有领域 mixin 的唯一基类。
"""

from __future__ import annotations

import asyncio
import os
import shutil
import socket
import uuid
from contextvars import ContextVar
from pathlib import Path
from threading import get_ident
from typing import Any, Callable, Optional, TypeVar

from dayu.fins._log import Log
from dayu.runtime.filelock import RuntimeFileLockTimeoutError, RuntimeFileLockToken, file_lock

from dayu.fins.domain.document_models import (
    BatchToken,
    CompanyMeta,
    FilingManifestItem,
    MaterialManifestItem,
    ProcessedHandle,
    ProcessedManifestItem,
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
    _fsync_directory,
    _normalize_document_id,
    _normalize_entry_name,
    _normalize_source_kind,
    _normalize_ticker,
    _read_json_object,
    _source_dir_name,
    _write_json,
)

_T = TypeVar("_T")

_DAYU_DIRNAME = ".dayu"
_BATCH_ROOT_DIRNAME = "repo_batches"
_BACKUP_ROOT_DIRNAME = "repo_backups"
_LOCK_ROOT_DIRNAME = "batch_locks"
_RECOVERY_LOCK_FILENAME = "batch_recovery.lock"
_JOURNAL_FILENAME = "transaction.json"
_PHASE_STARTED = "started"
_PHASE_BACKED_UP_TARGET = "backed_up_target"
_PHASE_SWAPPED_TARGET = "swapped_target"
_PHASE_COMMITTED = "committed"
_PHASE_ROLLED_BACK = "rolled_back"
_BATCH_OWNER_CONTEXT: ContextVar[dict[str, str]] = ContextVar(
    "fins_storage_batch_owner_context",
    default={},
)


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


def _current_execution_scope_id() -> str:
    """返回当前本地执行 scope 标识。

    Args:
        无。

    Returns:
        当前 asyncio task 或线程标识。

    Raises:
        无。
    """

    try:
        task = asyncio.current_task()
    except RuntimeError:
        task = None
    if task is not None:
        return f"async-task:{id(task)}"
    return f"thread:{get_ident()}"


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
        self._active_batches: dict[str, BatchToken] = {}
        self._ticker_lock_tokens: dict[str, RuntimeFileLockToken] = {}
        self._company_meta_by_ticker: Optional[dict[str, CompanyMeta]] = None
        self._alias_index: Optional[dict[str, list[str]]] = None
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
        """开启批处理事务。

        Args:
            ticker: 股票代码。

        Returns:
            批处理 token。

        Raises:
            RuntimeError: 同一 ticker 已存在活动事务时抛出。
            OSError: 暂存目录准备失败时抛出。
        """

        normalized_ticker = _normalize_ticker(ticker)
        if normalized_ticker in self._active_batches:
            raise RuntimeError(f"ticker={normalized_ticker} 已存在活动 batch")

        self._ensure_batch_storage_dirs()
        self.ensure_batch_recovery()
        lock_token = self._acquire_ticker_lock(normalized_ticker)
        token_id = uuid.uuid4().hex
        owner_token = uuid.uuid4().hex
        owner_scope_id = _current_execution_scope_id()
        target_ticker_dir = self._target_ticker_dir(normalized_ticker)
        staging_root_dir = self.batch_root / token_id
        staging_ticker_dir = staging_root_dir / normalized_ticker
        backup_dir = self.backup_root / f"{target_ticker_dir.name}.bak.{token_id}"
        journal_path = staging_root_dir / _JOURNAL_FILENAME
        token = BatchToken(
            token_id=token_id,
            owner_token=owner_token,
            owner_scope_id=owner_scope_id,
            ticker=normalized_ticker,
            target_ticker_dir=target_ticker_dir,
            staging_root_dir=staging_root_dir,
            staging_ticker_dir=staging_ticker_dir,
            backup_dir=backup_dir,
            journal_path=journal_path,
            ticker_lock_path=self._ticker_lock_path(normalized_ticker),
            created_at=now_iso8601(),
        )
        try:
            self._write_batch_journal(token, _PHASE_STARTED)
            if target_ticker_dir.exists():
                shutil.copytree(target_ticker_dir, staging_ticker_dir)
            else:
                self._ensure_ticker_structure(staging_ticker_dir)
        except Exception:
            shutil.rmtree(staging_root_dir, ignore_errors=True)
            self._release_ticker_lock(normalized_ticker, token=lock_token)
            raise

        self._active_batches[normalized_ticker] = token
        self._bind_batch_owner(token)
        return token

    def commit_batch(self, token: BatchToken) -> None:
        """提交批处理事务。

        Args:
            token: 批处理 token。

        Returns:
            无。

        Raises:
            ValueError: token 非当前活动事务时抛出。
            OSError: 提交失败时抛出。
        """

        current = self._active_batches.get(token.ticker)
        if current is None or current.token_id != token.token_id:
            raise ValueError("无效的 batch token，无法提交")
        self._require_batch_owner(token.ticker)

        target_dir = token.target_ticker_dir
        staging_dir = token.staging_ticker_dir
        backup_dir = token.backup_dir
        try:
            # 复杂逻辑说明：COMMITTED 写入成功前，target 切换始终只是可回滚的物理阶段。
            if target_dir.exists():
                self._replace_directory(target_dir, backup_dir)
            self._write_batch_journal(token, _PHASE_BACKED_UP_TARGET)
            self._replace_directory(staging_dir, target_dir)
            self._write_batch_journal(token, _PHASE_SWAPPED_TARGET)
            self._invalidate_company_meta_caches()
            self._write_batch_journal(token, _PHASE_COMMITTED)
        except Exception as commit_error:
            rollback_error: Exception | None = None
            try:
                self._rollback_precommit_batch(token)
            except Exception as exc:
                rollback_error = exc
            self._invalidate_company_meta_caches()
            if rollback_error is not None:
                commit_error.add_note(
                    "commit_batch rollback failed; journal/backup/staging recovery evidence retained"
                )
                Log.warn(
                    f"commit_batch 与 rollback 均失败，已保留恢复证据: ticker={token.ticker}",
                    module=self.MODULE,
                )
                raise commit_error from rollback_error
            Log.warn(f"commit_batch 失败，已恢复提交前状态: ticker={token.ticker}", module=self.MODULE)
            raise
        else:
            self._cleanup_committed_batch(token)
        finally:
            self._active_batches.pop(token.ticker, None)
            self._unbind_batch_owner(token)
            self._release_ticker_lock(token.ticker)

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

    def _rollback_precommit_batch(self, token: BatchToken) -> None:
        """把尚未到达 ``COMMITTED`` 的物理目录恢复到提交前状态。

        Args:
            token: 正在提交的 batch token。

        Returns:
            无。

        Raises:
            OSError: new target 撤回、backup 恢复、journal 写入或证据清理失败时抛出。
        """

        target_dir = token.target_ticker_dir
        staging_dir = token.staging_ticker_dir
        backup_dir = token.backup_dir
        if not staging_dir.exists() and target_dir.exists():
            # new target 尚未 committed；先移回 staging，既撤销可见状态又保留失败证据。
            self._replace_directory(target_dir, staging_dir)
        if backup_dir.exists():
            if target_dir.exists():
                raise OSError("rollback target 已存在，无法安全恢复 backup")
            self._replace_directory(backup_dir, target_dir)
        self._write_batch_journal(token, _PHASE_ROLLED_BACK)
        self._remove_directory(token.staging_root_dir)

    def _cleanup_committed_batch(self, token: BatchToken) -> None:
        """清理已提交 batch 的 backup 与 journal container。

        Args:
            token: 已 durable 写入 ``COMMITTED`` 的 batch token。

        Returns:
            无。cleanup 失败只记录诊断并保留恢复证据。

        Raises:
            无。
        """

        try:
            if token.backup_dir.exists():
                self._remove_directory(token.backup_dir)
            if token.staging_root_dir.exists():
                self._remove_directory(token.staging_root_dir)
        except OSError as cleanup_error:
            Log.warn(
                "commit_batch 已提交但 cleanup 失败，保留 orphan recovery 证据: "
                f"ticker={token.ticker} error_type={cleanup_error.__class__.__name__}",
                module=self.MODULE,
            )

    def rollback_batch(self, token: BatchToken) -> None:
        """回滚批处理事务。

        Args:
            token: 批处理 token。

        Returns:
            无。

        Raises:
            ValueError: token 非当前活动事务时抛出。
            OSError: 清理失败时抛出。
        """

        current = self._active_batches.get(token.ticker)
        if current is None or current.token_id != token.token_id:
            raise ValueError("无效的 batch token，无法回滚")
        self._require_batch_owner(token.ticker)
        self._active_batches.pop(token.ticker, None)
        self._unbind_batch_owner(token)
        self._invalidate_company_meta_caches()
        rollback_error: Exception | None = None
        try:
            self._write_batch_journal(token, _PHASE_ROLLED_BACK)
        except Exception as exc:
            rollback_error = exc
            Log.warn(
                f"rollback_batch 写入 journal 失败，但仍继续清理 staging 与释放锁: ticker={token.ticker}",
                module=self.MODULE,
            )
        finally:
            try:
                shutil.rmtree(token.staging_root_dir, ignore_errors=True)
            finally:
                self._release_ticker_lock(token.ticker)
        if rollback_error is not None:
            raise rollback_error

    def _execute_with_auto_batch(
        self,
        ticker: str,
        operation: Callable[..., _T],
        *args: Any,
        **kwargs: Any,
    ) -> _T:
        """在无活动事务时自动开启 batch 执行写操作。

        Args:
            ticker: 股票代码。
            operation: 具体执行函数。
            *args: 传给执行函数的位置参数。
            **kwargs: 传给执行函数的关键字参数。

        Returns:
            执行函数返回值。

        Raises:
            Exception: 执行或提交失败时透传原异常。
        """

        normalized_ticker = _normalize_ticker(ticker)
        if normalized_ticker in self._active_batches:
            self._require_batch_owner(normalized_ticker)
            return operation(*args, **kwargs)
        token = self.begin_batch(normalized_ticker)
        try:
            result = operation(*args, **kwargs)
        except Exception as operation_error:
            # 复杂逻辑说明：写操作失败时必须显式回滚 staging，避免留下半更新目录。
            Log.warn(f"写操作失败，已回滚 batch: ticker={token.ticker}", module=self.MODULE)
            rollback_error: Exception | None = None
            try:
                self.rollback_batch(token)
            except Exception as exc:
                rollback_error = exc
            if rollback_error is not None:
                operation_error.add_note(f"rollback_batch failed: {rollback_error}")
            raise
        self.commit_batch(token)
        return result

    def _bind_batch_owner(self, token: BatchToken) -> None:
        """把当前执行 scope 绑定为 batch owner。

        Args:
            token: 已创建的 batch token。

        Returns:
            无。

        Raises:
            无。
        """

        context = dict(_BATCH_OWNER_CONTEXT.get())
        context[token.ticker] = token.owner_token
        _BATCH_OWNER_CONTEXT.set(context)

    def _unbind_batch_owner(self, token: BatchToken) -> None:
        """移除当前执行 scope 对 batch owner token 的绑定。

        Args:
            token: 即将结束的 batch token。

        Returns:
            无。

        Raises:
            无。
        """

        context = dict(_BATCH_OWNER_CONTEXT.get())
        if context.get(token.ticker) == token.owner_token:
            context.pop(token.ticker)
            _BATCH_OWNER_CONTEXT.set(context)

    def _require_batch_owner(self, ticker: str) -> BatchToken:
        """确认当前执行 scope 持有 ticker 活动 batch。

        Args:
            ticker: 股票代码。

        Returns:
            当前活动 batch token。

        Raises:
            RuntimeError: 当前 scope 不是活动 batch owner 时抛出。
        """

        normalized_ticker = _normalize_ticker(ticker)
        token = self._active_batches.get(normalized_ticker)
        if token is None:
            raise RuntimeError(f"ticker={normalized_ticker} 不存在活动 batch")
        context_owner_token = _BATCH_OWNER_CONTEXT.get().get(normalized_ticker)
        current_scope_id = _current_execution_scope_id()
        if context_owner_token != token.owner_token or current_scope_id != token.owner_scope_id:
            raise RuntimeError(f"ticker={normalized_ticker} 活动 batch 属于其他 owner")
        return token

    def _invalidate_company_meta_caches(self) -> None:
        """清空公司级元数据与 alias 索引缓存。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        self._company_meta_by_ticker = None
        self._alias_index = None

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

        token = self._acquire_lock_token(self._ticker_lock_path(ticker), blocking=False)
        self._ticker_lock_tokens[ticker] = token
        return token

    def _release_ticker_lock(
        self,
        ticker: str,
        *,
        token: RuntimeFileLockToken | None = None,
    ) -> None:
        """释放某个 ticker 的跨进程事务锁。

        Args:
            ticker: 股票代码。
            token: 可选显式 runtime 文件锁 token；未提供时使用内部缓存 token。

        Returns:
            无。

        Raises:
            RuntimeFileLockError: 解锁失败时抛出。
        """

        cached_token = self._ticker_lock_tokens.pop(ticker, None)
        effective_token = cached_token or token
        if effective_token is None:
            return
        self._release_lock_token(effective_token)

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

    def _write_batch_journal(self, token: BatchToken, phase: str) -> None:
        """把事务 phase 写入 journal。

        Args:
            token: 批处理 token。
            phase: 当前事务阶段。

        Returns:
            无。

        Raises:
            OSError: journal 写入失败时抛出。
        """

        payload = {
            "token_id": token.token_id,
            "owner_token": token.owner_token,
            "owner_scope_id": token.owner_scope_id,
            "ticker": token.ticker,
            "created_at": token.created_at,
            "owner_pid": str(self._current_pid()),
            "hostname": socket.gethostname(),
            "phase": phase,
            "target_dir": str(token.target_ticker_dir),
            "staging_root_dir": str(token.staging_root_dir),
            "staging_ticker_dir": str(token.staging_ticker_dir),
            "backup_dir": str(token.backup_dir),
            "journal_path": str(token.journal_path),
            "ticker_lock_path": str(token.ticker_lock_path),
        }
        _write_json(token.journal_path, payload)

    def _current_pid(self) -> int:
        """返回当前进程 PID。

        Args:
            无。

        Returns:
            当前进程 PID。

        Raises:
            无。
        """
        return os.getpid()

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
            if not token_dir.is_dir():
                continue
            actions.extend(self._recover_single_batch_dir(token_dir, dry_run=dry_run))
        return actions

    def _recover_single_batch_dir(self, token_dir: Path, *, dry_run: bool) -> list[str]:
        """恢复单个 batch token 目录。

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
        journal_exists = journal_path.exists()
        journal = _read_json_object(journal_path) if journal_exists else {}
        ticker = str(journal.get("ticker", "")).strip() or self._infer_batch_ticker(token_dir)
        phase = str(journal.get("phase", "")).strip()
        if not ticker:
            reason = "missing ticker journal" if journal_exists else "missing journal"
            action = f"skip batch token={token_dir.name} phase={phase or 'unknown'} reason={reason}"
            actions.append(action)
            return actions
        normalized_ticker = _normalize_ticker(ticker)
        ticker_token = self._try_acquire_recovery_ticker_lock(normalized_ticker)
        if ticker_token is None:
            return actions
        try:
            target_dir = self._target_ticker_dir(normalized_ticker)
            backup_dir = Path(str(journal.get("backup_dir", "")).strip() or self.backup_root / f"{normalized_ticker}.bak.{token_dir.name}")
            staging_dir = Path(
                str(journal.get("staging_ticker_dir", "")).strip()
                or token_dir / normalized_ticker
            )
            if phase == _PHASE_COMMITTED:
                if not target_dir.exists():
                    actions.append(
                        f"preserve committed evidence ticker={normalized_ticker} "
                        f"token={token_dir.name} reason=missing_target"
                    )
                    return actions
                if backup_dir.exists():
                    actions.append(
                        f"delete backup ticker={normalized_ticker} token={token_dir.name} phase={phase}"
                    )
                    if not dry_run:
                        self._remove_directory(backup_dir)
            elif phase in {_PHASE_BACKED_UP_TARGET, _PHASE_SWAPPED_TARGET}:
                if target_dir.exists():
                    actions.append(
                        f"remove uncommitted target ticker={normalized_ticker} "
                        f"token={token_dir.name} phase={phase}"
                    )
                    if not dry_run:
                        if staging_dir.exists():
                            self._remove_directory(target_dir)
                        else:
                            self._replace_directory(target_dir, staging_dir)
                if backup_dir.exists():
                    actions.append(
                        f"restore backup ticker={normalized_ticker} token={token_dir.name} phase={phase}"
                    )
                    if not dry_run:
                        self._replace_directory(backup_dir, target_dir)
            elif backup_dir.exists() and not target_dir.exists():
                actions.append(
                    f"restore backup ticker={normalized_ticker} token={token_dir.name} "
                    f"phase={phase or 'unknown'}"
                )
                if not dry_run:
                    self._replace_directory(backup_dir, target_dir)
            elif backup_dir.exists() and target_dir.exists() and phase != _PHASE_STARTED:
                actions.append(
                    f"preserve ambiguous backup ticker={normalized_ticker} token={token_dir.name} "
                    f"phase={phase or 'unknown'}"
                )
                return actions
            actions.append(f"cleanup batch ticker={normalized_ticker} token={token_dir.name} phase={phase or 'unknown'}")
            if not dry_run:
                self._remove_directory(token_dir)
        finally:
            self._release_lock_token(ticker_token)
        return actions

    def _recover_orphan_backup_dirs(self, *, dry_run: bool) -> list[str]:
        """扫描并恢复孤儿备份目录。

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
            if not backup_dir.is_dir():
                continue
            parsed = _parse_backup_directory_name(backup_dir.name)
            if parsed is None:
                continue
            ticker, token_id = parsed
            token_dir = self.batch_root / token_id
            if token_dir.exists():
                continue
            normalized_ticker = _normalize_ticker(ticker)
            ticker_token = self._try_acquire_recovery_ticker_lock(normalized_ticker)
            if ticker_token is None:
                continue
            try:
                target_dir = self._target_ticker_dir(normalized_ticker)
                if target_dir.exists():
                    actions.append(f"delete backup ticker={normalized_ticker} token={token_id}")
                    if not dry_run:
                        self._remove_directory(backup_dir)
                    continue
                actions.append(f"restore backup ticker={normalized_ticker} token={token_id}")
                if not dry_run:
                    self._replace_directory(backup_dir, target_dir)
            finally:
                self._release_lock_token(ticker_token)
        return actions

    def _infer_batch_ticker(self, token_dir: Path) -> str:
        """从 token 目录结构推断 ticker。

        Args:
            token_dir: token 根目录。

        Returns:
            推断出的 ticker；无法推断时返回空字符串。

        Raises:
            OSError: 目录访问失败时抛出。
        """

        try:
            for child in token_dir.iterdir():
                if child.is_dir():
                    return child.name.strip()
        except FileNotFoundError:
            # 并发恢复场景下，live batch 可能在 recovery 扫描完 token 列表后、
            # 真正进入该 token 前已经完成提交并删掉 staging 根目录。
            # 此时应把它视为“无需恢复的已消失 token”，而不是让 ENOENT
            # 中断整个 recover_orphan_batches 流程。
            return ""
        return ""

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

    def _build_file_store(self, ticker: str) -> FileStore:
        """构建文件存储实例。

        Args:
            ticker: 股票代码。

        Returns:
            文件存储实例。

        Raises:
            OSError: 目录创建失败时抛出。
        """

        if self._file_store is not None:
            return self._file_store
        return LocalFileStore(root=self._file_store_root_for_ticker(ticker), scheme="local")

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
        current_file_names: list[str],
        previous_file_names: list[str],
    ) -> Optional[str]:
        """确定主文件名。

        Args:
            explicit_primary: 请求显式传入主文件名。
            previous_primary: 旧 meta 中主文件名。
            current_file_names: 本次写入文件名列表。
            previous_file_names: 上一次保存的文件名列表。

        Returns:
            主文件名；若无法确定则返回 `None`。

        Raises:
            无。
        """

        if isinstance(explicit_primary, str) and explicit_primary.strip():
            return explicit_primary
        if isinstance(previous_primary, str) and previous_primary.strip():
            return previous_primary
        if current_file_names:
            return current_file_names[0]
        if previous_file_names:
            return previous_file_names[0]
        return None

    # ========== manifest 操作 ==========

    def upsert_filing_manifest(self, ticker: str, items: list[FilingManifestItem]) -> None:
        """批量合并写入 filing manifest。

        Args:
            ticker: 股票代码。
            items: filing manifest 项目列表。

        Returns:
            无。

        Raises:
            OSError: 写入失败时抛出。
        """

        self._execute_with_auto_batch(
            ticker,
            self._upsert_filing_manifest_impl,
            ticker,
            items,
        )

    def _upsert_filing_manifest_impl(self, ticker: str, items: list[FilingManifestItem]) -> None:
        """执行 filing manifest 合并写入（内部实现）。

        Args:
            ticker: 股票代码。
            items: filing manifest 项目列表。

        Returns:
            无。

        Raises:
            OSError: 写入失败时抛出。
        """

        normalized_ticker = _normalize_ticker(ticker)
        payloads = [item.to_dict() for item in items]
        self._upsert_manifest_items(self._filing_manifest_path(normalized_ticker), normalized_ticker, payloads)

    def upsert_material_manifest(self, ticker: str, items: list[MaterialManifestItem]) -> None:
        """批量合并写入 material manifest。

        Args:
            ticker: 股票代码。
            items: material manifest 项目列表。

        Returns:
            无。

        Raises:
            OSError: 写入失败时抛出。
        """

        self._execute_with_auto_batch(
            ticker,
            self._upsert_material_manifest_impl,
            ticker,
            items,
        )

    def _upsert_material_manifest_impl(self, ticker: str, items: list[MaterialManifestItem]) -> None:
        """执行 material manifest 合并写入（内部实现）。

        Args:
            ticker: 股票代码。
            items: material manifest 项目列表。

        Returns:
            无。

        Raises:
            OSError: 写入失败时抛出。
        """

        normalized_ticker = _normalize_ticker(ticker)
        payloads = [item.to_dict() for item in items]
        self._upsert_manifest_items(self._material_manifest_path(normalized_ticker), normalized_ticker, payloads)

    def upsert_processed_manifest(self, ticker: str, items: list[ProcessedManifestItem]) -> None:
        """批量合并写入 processed manifest。

        Args:
            ticker: 股票代码。
            items: processed manifest 项目列表。

        Returns:
            无。

        Raises:
            OSError: 写入失败时抛出。
        """

        self._execute_with_auto_batch(
            ticker,
            self._upsert_processed_manifest_impl,
            ticker,
            items,
        )

    def _upsert_processed_manifest_impl(self, ticker: str, items: list[ProcessedManifestItem]) -> None:
        """执行 processed manifest 合并写入（内部实现）。

        Args:
            ticker: 股票代码。
            items: processed manifest 项目列表。

        Returns:
            无。

        Raises:
            OSError: 写入失败时抛出。
        """

        normalized_ticker = _normalize_ticker(ticker)
        payloads = [item.to_dict() for item in items]
        self._upsert_manifest_items(self._processed_manifest_path(normalized_ticker), normalized_ticker, payloads)

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

    def _ticker_dir_for_write(self, ticker: str) -> Path:
        """返回当前可写 ticker 目录（优先 batch staging）。

        Args:
            ticker: 股票代码。

        Returns:
            可写目录路径。

        Raises:
            OSError: 目录创建失败时抛出。
        """

        token = self._active_batches.get(ticker)
        if token is not None:
            self._require_batch_owner(ticker)
            self._ensure_ticker_structure(token.staging_ticker_dir)
            return token.staging_ticker_dir
        target = self._target_ticker_dir(ticker)
        self._ensure_ticker_structure(target)
        return target

    def _ticker_dir_for_read(self, ticker: str) -> Path:
        """返回当前可读 ticker 目录（优先 batch staging）。

        Args:
            ticker: 股票代码。

        Returns:
            可读目录路径。

        Raises:
            无。
        """

        token = self._active_batches.get(ticker)
        if token is not None:
            self._require_batch_owner(ticker)
            return token.staging_ticker_dir
        return self._target_ticker_dir(ticker)

    def _file_store_root_for_ticker(self, ticker: str) -> Path:
        """获取文件存储根目录（兼容 batch staging）。

        Args:
            ticker: 股票代码。

        Returns:
            文件存储根目录。

        Raises:
            OSError: 目录创建失败时抛出。
        """

        token = self._active_batches.get(ticker)
        if token is not None:
            self._require_batch_owner(ticker)
            self._ensure_ticker_structure(token.staging_ticker_dir)
            return token.staging_ticker_dir.parent
        self._ensure_ticker_structure(self._target_ticker_dir(ticker))
        return self.portfolio_root

    def _source_root(self, ticker: str, source_kind: SourceKind) -> Path:
        """返回来源目录根路径。

        Args:
            ticker: 股票代码。
            source_kind: 来源类型。

        Returns:
            来源目录路径。

        Raises:
            OSError: 目录创建失败时抛出。
        """

        ticker_dir = self._ticker_dir_for_write(ticker)
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

    def _source_meta_path(self, ticker: str, document_id: str, source_kind: SourceKind) -> Path:
        """返回源文档 meta 路径。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。
            source_kind: 来源类型。

        Returns:
            meta 文件路径。

        Raises:
            OSError: 路径构建失败时抛出。
        """

        normalized_document_id = _normalize_document_id(document_id)
        return self._source_root(ticker, source_kind) / normalized_document_id / _SOURCE_META_FILENAME

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

    def _company_meta_path(self, ticker: str) -> Path:
        """返回公司级 meta 路径。

        Args:
            ticker: 股票代码。

        Returns:
            公司级 meta 路径。

        Raises:
            OSError: 路径构建失败时抛出。
        """

        normalized_ticker = _normalize_ticker(ticker)
        return self._ticker_dir_for_write(normalized_ticker) / _SOURCE_META_FILENAME

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

    def _filing_manifest_path(self, ticker: str) -> Path:
        """返回 filing manifest 路径。

        Args:
            ticker: 股票代码。

        Returns:
            filing manifest 路径。

        Raises:
            OSError: 路径构建失败时抛出。
        """

        return self._ticker_dir_for_write(ticker) / "filings" / "filing_manifest.json"

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

    def _material_manifest_path(self, ticker: str) -> Path:
        """返回 material manifest 路径。

        Args:
            ticker: 股票代码。

        Returns:
            material manifest 路径。

        Raises:
            OSError: 路径构建失败时抛出。
        """

        return self._ticker_dir_for_write(ticker) / "materials" / "material_manifest.json"

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

    def _processed_manifest_path(self, ticker: str) -> Path:
        """返回 processed manifest 路径。

        Args:
            ticker: 股票代码。

        Returns:
            processed manifest 路径。

        Raises:
            OSError: 路径构建失败时抛出。
        """

        return self._ticker_dir_for_write(ticker) / "processed" / "manifest.json"

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

    def _processed_dir_for_write(self, ticker: str, document_id: str) -> Path:
        """获取解析产物目录路径（用于写入）。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。

        Returns:
            解析产物目录路径。

        Raises:
            OSError: 路径构建失败时抛出。
        """

        normalized_ticker = _normalize_ticker(ticker)
        normalized_document_id = _normalize_document_id(document_id)
        return self._ticker_dir_for_write(normalized_ticker) / "processed" / normalized_document_id

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

    def _processed_meta_path(self, ticker: str, document_id: str) -> Path:
        """获取解析产物 tool_snapshot_meta.json 路径。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。

        Returns:
            tool_snapshot_meta.json 路径。

        Raises:
            OSError: 路径构建失败时抛出。
        """

        return self._processed_dir_for_write(ticker, document_id) / _PROCESSED_META_FILENAME

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

    def _download_rejections_path(self, ticker: str) -> Path:
        """返回下载拒绝注册表路径。

        Args:
            ticker: 股票代码。

        Returns:
            拒绝注册表路径。

        Raises:
            OSError: 路径构建失败时抛出。
        """

        return self._ticker_dir_for_write(ticker) / "filings" / _DOWNLOAD_REJECTIONS_FILENAME

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

    def _rejected_filings_root(self, ticker: str) -> Path:
        """返回 rejected filings 根目录。

        Args:
            ticker: 股票代码。

        Returns:
            rejected filings 根目录。

        Raises:
            OSError: 路径构建失败时抛出。
        """

        return self._ticker_dir_for_write(ticker) / "filings" / _REJECTED_FILINGS_DIRNAME

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

    def _rejected_filing_dir(self, ticker: str, document_id: str) -> Path:
        """返回单个 rejected filing 目录。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。

        Returns:
            文档目录路径。

        Raises:
            OSError: 路径构建失败时抛出。
        """

        normalized_document_id = _normalize_document_id(document_id)
        return self._rejected_filings_root(ticker) / normalized_document_id

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

    def _rejected_filing_meta_path(self, ticker: str, document_id: str) -> Path:
        """返回 rejected filing meta 路径。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。

        Returns:
            meta.json 路径。

        Raises:
            OSError: 路径构建失败时抛出。
        """

        return self._rejected_filing_dir(ticker, document_id) / _SOURCE_META_FILENAME

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
