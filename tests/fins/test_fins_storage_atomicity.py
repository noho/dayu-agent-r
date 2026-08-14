"""Fins storage identity、batch commit/recovery 与本地对象原子性测试。"""

from __future__ import annotations

import errno
import io
import json
import multiprocessing
import os
import traceback
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, fields
from multiprocessing.connection import Connection
from pathlib import Path
from queue import Empty, Queue
from threading import Event
from typing import BinaryIO, Literal, NoReturn
from unittest.mock import patch

import pytest

from tests.fins.company_meta_test_support import stage_company_meta_fixture

import dayu.fins.storage._fs_storage_infra as storage_infra_module
import dayu.fins.storage._fs_source_snapshot as source_snapshot_module
import dayu.fins.storage._fs_storage_utils as storage_utils_module
import dayu.fins.storage.local_file_store as local_file_store_module
from dayu.fins.ticker_normalization import build_company_ticker_identity
from dayu.fins.domain.document_models import (
    BatchToken,
    CompanyMeta,
    DocumentQuery,
    FileObjectMeta,
    ProcessedCreateRequest,
    ProcessedDeleteRequest,
    ProcessedHandle,
    ProcessedUpdateRequest,
    RejectedFilingArtifactUpsertRequest,
    SourceFileEntry,
    SourceDocumentStateChangeRequest,
    SourceDocumentUpsertRequest,
    SourceDocumentRevision,
    SourceHandle,
    now_iso8601,
)
from dayu.fins.domain.enums import SourceKind
from dayu.fins.storage import (
    CompanyTickerIdentityCorruptionError,
    FsBatchingRepository,
    FsCompanyMetaRepository,
    FsDocumentBlobRepository,
    FsFilingMaintenanceRepository,
    FsFilingUploadStateRepository,
    FsProcessedDocumentRepository,
    FsSourceDocumentRepository,
    LocalFileStore,
    SourceIntegrityPreflightError,
    SourceIntegrityPreflightReason,
    SourceIntegrityReason,
    SourceIntegrityStatus,
    classify_source_integrity_preflight,
)
from dayu.fins.storage._fs_repository_factory import build_fs_repository_set
from dayu.fins.storage._fs_storage_core import FsStorageCore
from dayu.fins.storage._fs_storage_infra import (
    _PHASE_BACKED_UP_TARGET,
    _PHASE_COMMITTED,
    _PHASE_ROLLED_BACK,
    _PHASE_STARTED,
    _PHASE_SWAPPED_TARGET,
)
from dayu.fins.storage.repository_protocols import SourceSnapshotConsistencyError
from dayu.fins.storage._fs_storage_utils import (
    _local_path_from_uri,
    _normalize_entry_name,
    _normalize_filename,
    _normalize_object_key,
)
from dayu.runtime.filelock import RuntimeFileLockError, RuntimeFileLockToken

_Normalizer = Callable[[str], str]
_CommitFailurePoint = Literal[
    "backup_rename",
    "backed_journal",
    "staging_rename",
    "swapped_journal",
    "committed_journal",
]
_ReplaceTargetKind = Literal["directory", "broken_symlink"]
_PublicationBarrier = Literal["target_to_backup", "staging_to_target"]
_FilingCleanupCorruption = Literal[
    "filing_descriptor",
    "filing_manifest",
    "rejection_registry",
    "rejected_descriptor",
    "rejected_meta",
    "rejected_symlink",
    "rejected_unexpected",
    "filing_unexpected",
]
_ProcessedCleanupCorruption = Literal[
    "descriptor",
    "meta_missing",
    "meta_corrupt",
    "meta_mismatch",
    "manifest",
    "symlink",
    "unexpected",
]
_StaleMetaCorruption = Literal["missing", "corrupt", "mismatch"]
_BatchInitializationFailurePoint = Literal["journal", "descriptor", "copy"]
_SnapshotVersion = Literal["A", "B"]


def test_filing_upload_state_fresh_absent_is_pure_and_lock_free(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """fresh absent snapshot 必须在 publication guard 前返回且不创建目录。

    Args:
        tmp_path: pytest 临时目录。
        monkeypatch: pytest monkeypatch fixture。

    Returns:
        无。

    Raises:
        AssertionError: 读取创建目录、获取锁或返回非空成员时抛出。
    """

    workspace_root = tmp_path / "workspace"
    repository = FsFilingUploadStateRepository(workspace_root)
    core = repository._repository_set.core

    def fail_guard(ticker: str) -> NoReturn:
        """拒绝 fresh absent 分支获取 publication guard。

        Args:
            ticker: 请求 ticker。

        Returns:
            不返回。

        Raises:
            AssertionError: 始终抛出以暴露错误锁获取。
        """

        raise AssertionError(f"fresh absent 不得获取 publication guard: {ticker}")

    monkeypatch.setattr(core, "_acquire_publication_guard", fail_guard)

    assert repository.read_filing_upload_state("AAPL", "aapl-2024-fy").company_meta is None
    assert repository.read_filing_upload_state("AAPL", "aapl-2024-fy").source_meta is None
    assert not workspace_root.exists()


def test_filing_upload_state_reads_company_and_source_from_one_published_version(
    tmp_path: Path,
) -> None:
    """snapshot 必须返回同一 published version 中的 company 与 filing source。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: durable source 不完整或 snapshot 成员不一致时抛出。
    """

    workspace_root = tmp_path / "workspace"
    repository_set = build_fs_repository_set(workspace_root=workspace_root)
    batching = FsBatchingRepository(workspace_root, repository_set=repository_set)
    company = FsCompanyMetaRepository(workspace_root, repository_set=repository_set)
    source = FsSourceDocumentRepository(workspace_root, repository_set=repository_set)
    blob = FsDocumentBlobRepository(workspace_root, repository_set=repository_set)
    state = FsFilingUploadStateRepository(workspace_root, repository_set=repository_set)
    batch = batching.begin_batch("AAPL")
    stage_company_meta_fixture(
        company,
        CompanyMeta(
            company_id="company-aapl",
            company_name="Apple Inc.",
            ticker_identity=build_company_ticker_identity("AAPL", ()),
            resolver_version="test",
            updated_at=now_iso8601(),
        ),
        batch=batch,
    )
    handle = SourceHandle("AAPL", "aapl-2024-fy", SourceKind.FILING.value)
    file_meta = blob.store_file(
        handle,
        "report.md",
        io.BytesIO(b"report"),
        batch=batch,
        content_type="text/markdown",
    )
    source.create_source_document(
        SourceDocumentUpsertRequest(
            ticker="AAPL",
            document_id="aapl-2024-fy",
            internal_document_id="aapl-2024-fy",
            form_type="10-K",
            primary_document="report.md",
            meta={"ingest_method": "upload", "source_provider": "user_upload"},
            files=[file_meta],
        ),
        SourceKind.FILING,
        batch=batch,
    )
    batching.commit_batch(batch)

    snapshot = state.read_filing_upload_state("AAPL", "aapl-2024-fy")

    assert snapshot.company_meta is not None
    assert snapshot.company_meta.company_name == "Apple Inc."
    assert snapshot.source_meta is not None
    assert snapshot.source_meta["primary_document"] == "report.md"


class _FailingCloseBytesIO(io.BytesIO):
    """为 initial-fstat owner test 提供首轮 close 失败的 typed 二进制流。"""

    def __init__(self, close_error: OSError) -> None:
        """初始化可观测 close 失败流。

        Args:
            close_error: 第一次 close 必须抛出的次级文件系统失败。

        Returns:
            无。

        Raises:
            无。
        """

        super().__init__()
        self.close_error = close_error
        self.close_calls = 0

    def fileno(self) -> int:
        """返回只供已 monkeypatch fstat 消费的测试描述符。

        Args:
            无。

        Returns:
            固定测试描述符整数。

        Raises:
            无。
        """

        return -1

    def close(self) -> None:
        """第一次抛出注入失败，之后执行真实 BytesIO close。

        Args:
            无。

        Returns:
            无。

        Raises:
            OSError: 第一次调用时抛出注入的次级失败。
        """

        self.close_calls += 1
        if self.close_calls == 1:
            raise self.close_error
        super().close()


def _exception_graph_nodes(error: BaseException) -> tuple[BaseException, ...]:
    """返回 cause/context 可达的完整异常对象图。

    Args:
        error: public storage boundary 抛出的顶层异常。

    Returns:
        去重后的异常节点元组。

    Raises:
        无。
    """

    pending = [error]
    visited_ids: set[int] = set()
    nodes: list[BaseException] = []
    while pending:
        node = pending.pop()
        node_id = id(node)
        if node_id in visited_ids:
            continue
        visited_ids.add(node_id)
        nodes.append(node)
        if node.__cause__ is not None:
            pending.append(node.__cause__)
        if node.__context__ is not None:
            pending.append(node.__context__)
    return tuple(nodes)


def _assert_exception_graph_path_free(
    error: BaseException,
    *,
    forbidden_locators: tuple[str, ...],
) -> None:
    """递归断言异常 graph、notes 与格式化 traceback 不含 private locator。

    Args:
        error: public storage boundary 抛出的顶层异常。
        forbidden_locators: workspace、private key 或 transaction/lock locator。

    Returns:
        无。

    Raises:
        AssertionError: 任一异常节点或 traceback 泄漏 locator 时抛出。
    """

    serialized_parts: list[str] = []
    for node in _exception_graph_nodes(error):
        try:
            notes = tuple(node.__notes__)
        except AttributeError:
            notes = ()
        serialized_parts.extend(
            (
                node.__class__.__name__,
                str(node),
                repr(node.args),
                repr(notes),
                "".join(traceback.format_exception(node)),
            )
        )
    serialized = "\n".join(serialized_parts)
    for locator in forbidden_locators:
        assert locator
        assert locator not in serialized


@dataclass(frozen=True)
class _BatchPaths:
    """测试侧从 storage-owned active state 取得的 transaction 物理路径快照。"""

    target_ticker_dir: Path
    staging_root_dir: Path
    staging_ticker_dir: Path
    backup_dir: Path
    journal_path: Path


class _PublicationGuardAcquireSignal:
    """在真实 public reader 获取 publication guard 前向父进程发信号。"""

    def __init__(
        self,
        connection: Connection,
        acquire: Callable[[str], RuntimeFileLockToken],
    ) -> None:
        """初始化 acquire 包装器。

        Args:
            connection: 与父进程通信的 pipe 连接。
            acquire: storage core 的真实 blocking publication guard acquire。

        Returns:
            无。

        Raises:
            无。
        """

        self._connection = connection
        self._acquire = acquire

    def __call__(self, ticker: str) -> RuntimeFileLockToken:
        """报告真实 acquire 调用点后进入原 blocking acquire。

        Args:
            ticker: public reader 即将读取的 ticker。

        Returns:
            真实 storage acquire 返回的 publication lock token。

        Raises:
            OSError: pipe 发信号失败时抛出。
            RuntimeFileLockError: 真实 publication guard 获取失败时抛出。
        """

        self._connection.send_bytes(b"publication_acquire_entered")
        return self._acquire(ticker)


def test_batch_token_fields_and_minimal_journal_are_closed_owner_contract(tmp_path: Path) -> None:
    """public token 只含 opaque identity；journal 只持 recovery 最小事实。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: public capability 或 journal 泄漏 internal locator 时抛出。
    """

    assert tuple(field.name for field in fields(BatchToken)) == ("transaction_id", "ticker")
    core = _build_core(tmp_path)
    batch = core.begin_batch("AAPL")
    state = _only_active_batch_state(core)
    journal = json.loads(state.journal_path.read_text(encoding="utf-8"))

    assert journal == {
        "transaction_id": batch.transaction_id,
        "ticker": "AAPL",
        "phase": _PHASE_STARTED,
    }
    core.rollback_batch(batch)


@pytest.mark.parametrize("failure_point", ("journal", "descriptor", "copy"))
def test_begin_batch_preserves_initialization_primary_when_lock_release_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_point: _BatchInitializationFailurePoint,
) -> None:
    """begin_batch 必须保留 journal/descriptor/copy 主失败并仅附加 release 诊断。

    Args:
        tmp_path: pytest 临时目录。
        monkeypatch: pytest monkeypatch fixture。
        failure_point: 初始化主失败注入点。

    Returns:
        无。

    Raises:
        AssertionError: 主异常被替换、次级诊断缺失或 active maps 被发布时抛出。
    """

    core = _build_core(tmp_path)
    seed_batch = core.begin_batch("AAPL")
    core.commit_batch(seed_batch)
    primary_error = RuntimeError(f"{failure_point} initialization primary")
    target_dir = core._target_ticker_dir("AAPL")

    if failure_point == "journal":

        def _fail_journal(
            state: storage_infra_module._ActiveBatchState,
            phase: str,
        ) -> None:
            """注入 journal authoritative 主失败。

            Args:
                state: 当前 batch state。
                phase: 待写入 phase。

            Returns:
                无。

            Raises:
                RuntimeError: 始终抛出固定主异常。
            """

            del state, phase
            raise primary_error

        monkeypatch.setattr(core, "_write_batch_journal", _fail_journal)
    elif failure_point == "descriptor":
        _identity_descriptor_file(target_dir).write_text("{}", encoding="utf-8")
    else:

        def _fail_copytree(source_path: Path, target_path: Path) -> None:
            """注入 copy authoritative 主失败。

            Args:
                source_path: published source tree。
                target_path: staging target tree。

            Returns:
                无。

            Raises:
                RuntimeError: 始终抛出固定主异常。
            """

            del source_path, target_path
            raise primary_error

        monkeypatch.setattr(storage_infra_module.shutil, "copytree", _fail_copytree)

    release_lock_token = core._release_lock_token

    def _release_then_fail(token: RuntimeFileLockToken) -> None:
        """真实释放 writer lock 后注入次级失败。

        Args:
            token: 已持有的 writer lock token。

        Returns:
            无。

        Raises:
            RuntimeFileLockError: 始终在真实 release 后抛出。
        """

        release_lock_token(token)
        raise RuntimeFileLockError("secondary release failure")

    monkeypatch.setattr(core, "_release_lock_token", _release_then_fail)

    with pytest.raises((RuntimeError, ValueError)) as exc_info:
        core.begin_batch("AAPL")

    if failure_point == "descriptor":
        assert isinstance(exc_info.value, CompanyTickerIdentityCorruptionError)
        assert exc_info.value.kind == "invalid_descriptor"
    else:
        assert exc_info.value is primary_error
    assert any("writer mutex release failed during batch initialization" in note for note in exc_info.value.__notes__)
    assert core._active_batches == {}
    assert core._active_transaction_by_ticker == {}
    assert list(core.batch_root.iterdir()) == []


def test_begin_batch_preserves_primary_with_staging_cleanup_and_release_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """staging cleanup 与 lock release 同时失败时也不得替换 begin_batch 主异常。

    Args:
        tmp_path: pytest 临时目录。
        monkeypatch: pytest monkeypatch fixture。

    Returns:
        无。

    Raises:
        AssertionError: 主异常、safe notes、active maps 或尽力 cleanup 状态不符合契约时抛出。
    """

    core = _build_core(tmp_path)
    seed_batch = core.begin_batch("AAPL")
    core.commit_batch(seed_batch)
    primary_error = RuntimeError("copy initialization primary")
    original_copytree = storage_infra_module.shutil.copytree
    original_rmtree = storage_infra_module.shutil.rmtree
    release_lock_token = core._release_lock_token

    def _copy_then_fail(source_path: Path, target_path: Path) -> None:
        """完成真实 copy 后注入 authoritative 主失败。

        Args:
            source_path: published source tree。
            target_path: staging target tree。

        Returns:
            无。

        Raises:
            RuntimeError: 真实 copy 后抛出固定主异常。
        """

        storage_infra_module.shutil.copytree = original_copytree
        try:
            original_copytree(source_path, target_path)
        finally:
            storage_infra_module.shutil.copytree = _copy_then_fail
        raise primary_error

    def _fail_staging_cleanup(path: Path) -> None:
        """注入携带私有 staging locator 的 cleanup 失败。

        Args:
            path: 待删除 staging root。

        Returns:
            无。

        Raises:
            PermissionError: 始终抛出携物理路径的底层异常。
        """

        raise PermissionError(errno.EACCES, "cleanup denied", str(path))

    def _release_then_fail(token: RuntimeFileLockToken) -> None:
        """真实释放 writer lock 后注入次级失败。

        Args:
            token: 已持有的 writer lock token。

        Returns:
            无。

        Raises:
            RuntimeFileLockError: 始终在真实 release 后抛出。
        """

        release_lock_token(token)
        raise RuntimeFileLockError("secondary release failure")

    monkeypatch.setattr(storage_infra_module.shutil, "copytree", _copy_then_fail)
    monkeypatch.setattr(storage_infra_module.shutil, "rmtree", _fail_staging_cleanup)
    monkeypatch.setattr(core, "_release_lock_token", _release_then_fail)

    try:
        with pytest.raises(RuntimeError) as exc_info:
            core.begin_batch("AAPL")
        staging_roots = list(core.batch_root.iterdir())
        notes = exc_info.value.__notes__
        assert exc_info.value is primary_error
        assert any("batch staging cleanup failed" in note for note in notes)
        assert any("writer mutex release failed during batch initialization" in note for note in notes)
        assert all(str(core.workspace_root) not in note for note in notes)
        assert all(root.name not in " ".join(notes) for root in staging_roots)
        assert core._active_batches == {}
        assert core._active_transaction_by_ticker == {}
        assert staging_roots
    finally:
        monkeypatch.setattr(storage_infra_module.shutil, "rmtree", original_rmtree)
        for staging_root in core.batch_root.iterdir():
            original_rmtree(staging_root)


def test_begin_batch_projects_pathful_journal_oserror_graph_without_publishing_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """begin_batch 必须以 path-free cause 保留 journal OSError 类别且不发布 state。

    Args:
        tmp_path: pytest 临时目录。
        monkeypatch: pytest monkeypatch fixture。

    Returns:
        无。

    Raises:
        AssertionError: 异常或 active-map non-leak contract 回退时抛出。
    """

    core = _build_core(tmp_path)
    states: list[storage_infra_module._ActiveBatchState] = []
    raw_error: PermissionError | None = None

    def _fail_journal(
        state: storage_infra_module._ActiveBatchState,
        phase: str,
    ) -> None:
        """注入携带 journal 物理 locator 的 raw permission failure。

        Args:
            state: 当前 batch state。
            phase: 待写入 phase。

        Returns:
            无。

        Raises:
            PermissionError: 始终抛出携 journal 路径的原始异常。
        """

        nonlocal raw_error
        del phase
        states.append(state)
        raw_error = PermissionError(
            errno.EACCES,
            "journal denied",
            str(state.journal_path),
        )
        raise raw_error

    monkeypatch.setattr(core, "_write_batch_journal", _fail_journal)

    with pytest.raises(PermissionError) as exc_info:
        core.begin_batch("AAPL")

    assert states
    state = states[0]
    error = exc_info.value
    assert error.errno == errno.EACCES
    assert error.filename is None
    assert error.filename2 is None
    assert raw_error is not None
    assert isinstance(error.__cause__, PermissionError)
    assert error.__cause__.errno == errno.EACCES
    assert error.__cause__ is not raw_error
    assert error.__context__ is None
    assert all(node is not raw_error for node in _exception_graph_nodes(error))
    _assert_exception_graph_path_free(
        error,
        forbidden_locators=(
            str(core.workspace_root),
            state.staging_root_dir.name,
            state.backup_dir.name,
            core._ticker_lock_path(state.token.ticker).name,
            "journal denied",
        ),
    )
    assert core._active_batches == {}
    assert core._active_transaction_by_ticker == {}


def test_runtime_lock_acquire_error_graph_is_path_free_at_public_batch_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """runtime lock acquire 的 nested raw cause 不得跨 storage public boundary。

    测试优先用真实目录权限制造 acquire failure；root-like 平台无法执行时，
    在同一 runtime ``file_lock`` seam 注入等价 pathful nested cause。

    Args:
        tmp_path: pytest 临时目录。
        monkeypatch: pytest monkeypatch fixture。

    Returns:
        无。

    Raises:
        AssertionError: exception graph/traceback 泄漏 lock locator 或类别丢失时抛出。
    """

    core = _build_core(tmp_path)
    core.ensure_batch_recovery()
    ticker = "AAPL"
    lock_path = core._ticker_lock_path(ticker)
    lock_root_mode = core._batch_lock_root.stat().st_mode & 0o777
    acquired_batch: BatchToken | None = None
    acquire_error: RuntimeFileLockError | None = None
    core._batch_lock_root.chmod(0)
    try:
        try:
            acquired_batch = core.begin_batch(ticker)
        except RuntimeFileLockError as exc:
            acquire_error = exc
    finally:
        core._batch_lock_root.chmod(lock_root_mode)

    if acquired_batch is not None:
        core.rollback_batch(acquired_batch)

    if acquire_error is None:

        def _fail_runtime_file_lock(lock_locator: str | Path) -> NoReturn:
            """root-like 平台上注入 runtime lock constructor 的 pathful cause。

            Args:
                lock_locator: storage 传入的 private lock locator。

            Returns:
                永不返回。

            Raises:
                RuntimeFileLockError: 始终从 pathful ``PermissionError`` 链出。
            """

            raw_error = PermissionError(
                errno.EACCES,
                "runtime acquire denied",
                str(lock_locator),
            )
            try:
                raise raw_error
            except PermissionError as exc:
                raise RuntimeFileLockError("runtime acquire wrapper failed") from exc

        with monkeypatch.context() as patch_context:
            patch_context.setattr(storage_infra_module, "file_lock", _fail_runtime_file_lock)
            with pytest.raises(RuntimeFileLockError) as exc_info:
                core.begin_batch(ticker)
        acquire_error = exc_info.value

    assert isinstance(acquire_error.__cause__, PermissionError)
    assert acquire_error.__cause__.errno == errno.EACCES
    assert acquire_error.__context__ is None
    _assert_exception_graph_path_free(
        acquire_error,
        forbidden_locators=(
            str(core.workspace_root),
            lock_path.name,
            "runtime acquire denied",
        ),
    )
    assert core._active_batches == {}
    assert core._active_transaction_by_ticker == {}


def test_runtime_lock_release_error_graph_is_path_free_at_public_batch_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """runtime lock release 的 nested raw cause 不得跨 storage public boundary。

    Args:
        tmp_path: pytest 临时目录。
        monkeypatch: pytest monkeypatch fixture。

    Returns:
        无。

    Raises:
        AssertionError: exception graph/traceback 泄漏 lock locator 或类别丢失时抛出。
    """

    core = _build_core(tmp_path)
    ticker = "AAPL"
    batch = core.begin_batch(ticker)
    state = _only_active_batch_state(core)
    lock_path = state.writer_lock_token.lock_path
    original_release = RuntimeFileLockToken.release
    raw_release_errors: list[PermissionError] = []

    def _release_then_fail(token: RuntimeFileLockToken) -> None:
        """真实释放 token 后注入携 lock locator 的 runtime nested cause。

        Args:
            token: 待释放的 writer token。

        Returns:
            无。

        Raises:
            RuntimeFileLockError: 始终从 pathful ``PermissionError`` 链出。
        """

        original_release(token)
        raw_error = PermissionError(
            errno.EACCES,
            "runtime release denied",
            str(token.lock_path),
        )
        raw_release_errors.append(raw_error)
        try:
            raise raw_error
        except PermissionError as exc:
            raise RuntimeFileLockError("runtime release wrapper failed") from exc

    monkeypatch.setattr(RuntimeFileLockToken, "release", _release_then_fail)

    with pytest.raises(RuntimeFileLockError) as exc_info:
        core.rollback_batch(batch)

    error = exc_info.value
    assert raw_release_errors
    assert isinstance(error.__cause__, PermissionError)
    assert error.__cause__.errno == errno.EACCES
    assert error.__cause__ is not raw_release_errors[0]
    assert error.__context__ is None
    assert all(node is not raw_release_errors[0] for node in _exception_graph_nodes(error))
    _assert_exception_graph_path_free(
        error,
        forbidden_locators=(
            str(core.workspace_root),
            lock_path.name,
            "runtime release denied",
        ),
    )
    assert core._active_batches == {}
    assert core._active_transaction_by_ticker == {}


def test_batch_registry_rejects_unknown_altered_closed_ticker_and_cross_core_tokens(
    tmp_path: Path,
) -> None:
    """只有当前 core registry 中 canonical open capability 才能授权 mutation。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 任一伪造、错 scope、跨 core 或已关闭 token 被接受时抛出。
    """

    workspace_root = tmp_path / "workspace"
    repository_set = build_fs_repository_set(workspace_root=workspace_root)
    batching = FsBatchingRepository(workspace_root, repository_set=repository_set)
    source = FsSourceDocumentRepository(workspace_root, repository_set=repository_set)
    batch = batching.begin_batch("AAPL")
    request = _source_request("registry-owner")

    with pytest.raises(ValueError, match="未在当前 storage core 登记"):
        source.create_source_document(
            request,
            SourceKind.FILING,
            batch=BatchToken(transaction_id="unknown", ticker="AAPL"),
        )
    with pytest.raises(ValueError, match="canonical capability 不匹配"):
        source.create_source_document(
            request,
            SourceKind.FILING,
            batch=BatchToken(transaction_id=batch.transaction_id, ticker="MSFT"),
        )
    with pytest.raises(ValueError, match="ticker 与 mutation scope 不匹配"):
        source.create_source_document(
            _source_request("wrong-ticker", ticker="MSFT"),
            SourceKind.FILING,
            batch=batch,
        )

    independent_set = build_fs_repository_set(workspace_root=workspace_root)
    independent_source = FsSourceDocumentRepository(
        workspace_root,
        repository_set=independent_set,
    )
    with pytest.raises(ValueError, match="未在当前 storage core 登记"):
        independent_source.create_source_document(
            request,
            SourceKind.FILING,
            batch=batch,
        )

    batching.rollback_batch(batch)
    with pytest.raises(ValueError, match="未在当前 storage core 登记"):
        source.create_source_document(request, SourceKind.FILING, batch=batch)


def test_writer_and_publication_lock_tokens_do_not_authorize_mutation(tmp_path: Path) -> None:
    """writer mutex 与 publication guard 都只是互斥机制，不是 mutation authority。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 仅持物理锁即可绕过 active registry 时抛出。
    """

    workspace_root = tmp_path / "workspace"
    repository_set = build_fs_repository_set(workspace_root=workspace_root)
    core = repository_set.core
    source = FsSourceDocumentRepository(workspace_root, repository_set=repository_set)
    writer_token = core._acquire_ticker_lock("AAPL")
    publication_token = core._acquire_publication_guard("AAPL")
    try:
        with pytest.raises(ValueError, match="未在当前 storage core 登记"):
            source.create_source_document(
                _source_request("lock-is-not-authority"),
                SourceKind.FILING,
                batch=BatchToken(transaction_id="unregistered", ticker="AAPL"),
            )
    finally:
        core._release_lock_token(publication_token)
        core._release_lock_token(writer_token)


def test_company_owner_reads_only_published_meta_inventory_and_aliases(tmp_path: Path) -> None:
    """company owner 应从 guarded published meta 统一提供 get/inventory/alias 语义。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: company public read 之间的 published 事实不一致时抛出。
    """

    workspace_root = tmp_path / "workspace"
    repository_set = build_fs_repository_set(workspace_root=workspace_root)
    batching = FsBatchingRepository(workspace_root, repository_set=repository_set)
    company = FsCompanyMetaRepository(workspace_root, repository_set=repository_set)
    batches = {ticker: batching.begin_batch(ticker) for ticker in ("AAPL", "MSFT")}
    for ticker, aliases in (
        ("AAPL", ["APPLE"]),
        ("MSFT", ["MSFT-A"]),
    ):
        stage_company_meta_fixture(
            company,
            CompanyMeta(
                company_id=f"company-{ticker}",
                company_name=f"{ticker} Inc.",
                ticker_identity=build_company_ticker_identity(ticker, aliases),
                resolver_version="test",
                updated_at=now_iso8601(),
            ),
            batch=batches[ticker],
        )
    for batch in batches.values():
        batching.commit_batch(batch)

    assert company.get_company_meta("AAPL").company_name == "AAPL Inc."
    with pytest.raises(ValueError, match="canonical ticker"):
        company.get_company_meta("aapl")
    assert company.resolve_company_ticker("aapl") == "AAPL"
    assert company.resolve_company_ticker("aapl.us") == "AAPL"
    assert company.resolve_company_ticker("apple") == "AAPL"
    assert company.resolve_company_ticker("not-listed") is None
    with pytest.raises(FileNotFoundError):
        company.get_company_meta("NONE")

    (repository_set.core.portfolio_root / ".hidden").mkdir()
    missing_batch = batching.begin_batch("MISSING")
    batching.commit_batch(missing_batch)
    invalid_batch = batching.begin_batch("INVALID")
    batching.commit_batch(invalid_batch)
    invalid_dir = repository_set.core._target_ticker_dir("INVALID")
    (invalid_dir / "meta.json").write_text("{}", encoding="utf-8")

    status_by_name = {
        item.ticker: item.status for item in company.scan_company_meta_inventory() if item.ticker is not None
    }
    assert status_by_name["AAPL"] == "available"
    assert status_by_name["MISSING"] == "missing_meta"
    assert status_by_name["INVALID"] == "invalid_meta"
    assert any(
        item.ticker is None and item.status == "hidden_directory" for item in company.scan_company_meta_inventory()
    )


def test_processed_owner_public_crud_mark_list_delete_and_clear(tmp_path: Path) -> None:
    """processed owner 的 mutation/read 组合应共享显式 transaction 与 published 事实。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: processed CRUD、mark、list 或 clear 状态不一致时抛出。
    """

    workspace_root = tmp_path / "workspace"
    repository_set = build_fs_repository_set(workspace_root=workspace_root)
    batching = FsBatchingRepository(workspace_root, repository_set=repository_set)
    processed = FsProcessedDocumentRepository(workspace_root, repository_set=repository_set)
    create_batch = batching.begin_batch("AAPL")
    for document_id in ("processed-one", "processed-two"):
        processed.create_processed(
            ProcessedCreateRequest(
                ticker="AAPL",
                document_id=document_id,
                internal_document_id=document_id,
                source_kind=SourceKind.FILING.value,
                form_type="10-K",
                meta={"fiscal_year": 2024, "fiscal_period": "FY"},
                sections=[],
                tables=[],
            ),
            batch=create_batch,
        )
    batching.commit_batch(create_batch)

    assert processed.get_processed_handle("AAPL", "processed-one") == ProcessedHandle(
        ticker="AAPL",
        document_id="processed-one",
    )
    assert processed.get_processed_meta("AAPL", "processed-one")["document_id"] == ("processed-one")
    assert [
        item.document_id for item in processed.list_processed_documents("AAPL", DocumentQuery(form_type="10-K"))
    ] == ["processed-one", "processed-two"]

    unchanged_meta = processed.get_processed_meta("AAPL", "processed-one")
    no_op_batch = batching.begin_batch("AAPL")
    assert (
        repository_set.core.mark_processed_reprocess_required(
            "AAPL",
            "processed-one",
            False,
            batch=no_op_batch,
        )
        is None
    )
    batching.commit_batch(no_op_batch)
    assert processed.get_processed_meta("AAPL", "processed-one") == unchanged_meta

    update_batch = batching.begin_batch("AAPL")
    processed.update_processed(
        ProcessedUpdateRequest(
            ticker="AAPL",
            document_id="processed-one",
            internal_document_id="processed-one",
            source_kind=SourceKind.FILING.value,
            form_type="10-Q",
            meta={"fiscal_year": 2025, "fiscal_period": "Q1"},
            sections=[{"section_id": "part-1"}],
            tables=[],
        ),
        batch=update_batch,
    )
    assert (
        repository_set.core.mark_processed_reprocess_required(
            "AAPL",
            "processed-one",
            True,
            batch=update_batch,
        )
        is None
    )
    assert (
        repository_set.core.mark_processed_reprocess_required(
            "AAPL",
            "missing",
            True,
            batch=update_batch,
        )
        is None
    )
    assert (
        repository_set.core._mark_processed_reprocess_required_impl(
            "AAPL",
            "processed-two",
            _only_active_batch_state(repository_set.core),
        )
        is None
    )
    batching.commit_batch(update_batch)
    assert processed.get_processed_meta("AAPL", "processed-one")["reprocess_required"] is True
    assert processed.get_processed_meta("AAPL", "processed-two")["reprocess_required"] is True
    with pytest.raises(FileNotFoundError):
        processed.get_processed_meta("AAPL", "missing")

    delete_batch = batching.begin_batch("AAPL")
    processed.delete_processed(
        ProcessedDeleteRequest(ticker="AAPL", document_id="processed-one"),
        batch=delete_batch,
    )
    batching.commit_batch(delete_batch)
    with pytest.raises(FileNotFoundError):
        processed.get_processed_meta("AAPL", "processed-one")

    tool_meta_path = repository_set.core._processed_meta_path_for_read("AAPL", "processed-two")
    valid_tool_meta = json.loads(tool_meta_path.read_text(encoding="utf-8"))
    assert isinstance(valid_tool_meta, dict)
    mismatched_tool_meta = dict(valid_tool_meta)
    mismatched_tool_meta["document_id"] = "processed-other"
    tool_meta_path.write_text(json.dumps(mismatched_tool_meta), encoding="utf-8")
    with pytest.raises(ValueError, match="identity descriptor"):
        processed.get_processed_meta("AAPL", "processed-two")
    with pytest.raises(ValueError, match="identity descriptor"):
        processed.list_processed_documents("AAPL", DocumentQuery())
    tool_meta_path.write_text(json.dumps(valid_tool_meta), encoding="utf-8")
    legacy_meta_path = tool_meta_path.with_name("meta.json")
    legacy_meta_path.write_text(
        json.dumps({"document_id": "legacy-meta-must-not-be-read"}),
        encoding="utf-8",
    )
    assert processed.get_processed_meta("AAPL", "processed-two")["document_id"] == ("processed-two")
    tool_meta_path.unlink()
    with pytest.raises(FileNotFoundError, match="processed 元数据不存在"):
        processed.get_processed_meta("AAPL", "processed-two")
    tool_meta_path.write_text(json.dumps(valid_tool_meta), encoding="utf-8")

    clear_batch = batching.begin_batch("AAPL")
    processed.clear_processed_documents("AAPL", batch=clear_batch)
    batching.commit_batch(clear_batch)
    assert processed.list_processed_documents("AAPL", DocumentQuery()) == []


def test_maintenance_owner_artifact_reads_cleanup_and_clear_are_guarded(tmp_path: Path) -> None:
    """maintenance owner 应显式写 staging，并从 published tree 组合读取 artifact。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: artifact、stale cleanup 或 filing clear 状态错误时抛出。
    """

    workspace_root = tmp_path / "workspace"
    repository_set = build_fs_repository_set(workspace_root=workspace_root)
    batching = FsBatchingRepository(workspace_root, repository_set=repository_set)
    source = FsSourceDocumentRepository(workspace_root, repository_set=repository_set)
    blob = FsDocumentBlobRepository(workspace_root, repository_set=repository_set)
    maintenance = FsFilingMaintenanceRepository(workspace_root, repository_set=repository_set)
    batch = batching.begin_batch("AAPL")
    for document_id in ("fil_keep", "fil_stale"):
        _create_complete_source(
            source,
            blob,
            batch=batch,
            document_id=document_id,
        )
    file_meta = maintenance.store_rejected_filing_file(
        "AAPL",
        "fil_rejected",
        "rejected.htm",
        io.BytesIO(b"rejected payload"),
        batch=batch,
        content_type="text/html",
    )
    request = RejectedFilingArtifactUpsertRequest(
        ticker="AAPL",
        document_id="fil_rejected",
        internal_document_id="fil_rejected",
        accession_number="0000320193-25-000001",
        company_id="0000320193",
        form_type="10-K",
        filing_date="2025-01-02",
        report_date="2024-12-31",
        primary_document="rejected.htm",
        selected_primary_document="rejected.htm",
        rejection_reason="policy",
        rejection_category="test",
        classification_version="v1",
        source_fingerprint="fingerprint",
        files=[
            SourceFileEntry(
                name="rejected.htm",
                uri=file_meta.uri,
                size=file_meta.size,
                content_type=file_meta.content_type,
                sha256=file_meta.sha256,
            )
        ],
    )
    first_artifact = maintenance.upsert_rejected_filing_artifact(request, batch=batch)
    second_artifact = maintenance.upsert_rejected_filing_artifact(request, batch=batch)
    assert second_artifact.created_at == first_artifact.created_at
    batching.commit_batch(batch)

    assert maintenance.get_rejected_filing_artifact("AAPL", "fil_rejected").document_id == ("fil_rejected")
    assert [artifact.document_id for artifact in maintenance.list_rejected_filing_artifacts("AAPL")] == ["fil_rejected"]
    assert (
        maintenance.read_rejected_filing_file_bytes(
            "AAPL",
            "fil_rejected",
            "rejected.htm",
        )
        == b"rejected payload"
    )
    with pytest.raises(FileNotFoundError, match="rejected filing 文件不存在"):
        maintenance.read_rejected_filing_file_bytes(
            "AAPL",
            "fil_rejected",
            "missing.htm",
        )
    directory_path = repository_set.core._rejected_filing_file_path_for_read(
        "AAPL",
        "fil_rejected",
        "directory-entry",
    )
    directory_path.mkdir()
    with pytest.raises(IsADirectoryError, match="目标是目录"):
        maintenance.read_rejected_filing_file_bytes(
            "AAPL",
            "fil_rejected",
            "directory-entry",
        )
    directory_path.rmdir()

    corrupt_dir = repository_set.core._rejected_filings_root_for_read("AAPL") / "corrupt-private-locator"
    corrupt_dir.mkdir()
    with pytest.raises(ValueError, match="identity descriptor"):
        maintenance.list_rejected_filing_artifacts("AAPL")
    corrupt_dir.rmdir()
    rejected_meta_path = repository_set.core._rejected_filing_meta_path_for_read(
        "AAPL",
        "fil_rejected",
    )
    rejected_meta = json.loads(rejected_meta_path.read_text(encoding="utf-8"))
    assert isinstance(rejected_meta, dict)
    mismatched_rejected_meta = dict(rejected_meta)
    mismatched_rejected_meta["document_id"] = "fil_other"
    rejected_meta_path.write_text(
        json.dumps(mismatched_rejected_meta),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="identity descriptor"):
        maintenance.list_rejected_filing_artifacts("AAPL")
    rejected_meta_path.write_text(json.dumps(rejected_meta), encoding="utf-8")

    cleanup_batch = batching.begin_batch("AAPL")
    assert (
        maintenance.cleanup_stale_filing_documents(
            "AAPL",
            batch=cleanup_batch,
            active_form_types={"10-K"},
            valid_document_ids={"fil_keep"},
        )
        == 1
    )
    batching.commit_batch(cleanup_batch)
    assert source.list_source_document_ids("AAPL", SourceKind.FILING) == ["fil_keep"]

    clear_batch = batching.begin_batch("AAPL")
    maintenance.clear_filing_documents("AAPL", batch=clear_batch)
    batching.commit_batch(clear_batch)
    assert source.list_source_document_ids("AAPL", SourceKind.FILING) == []


@pytest.mark.parametrize(
    "corruption",
    (
        "filing_descriptor",
        "filing_manifest",
        "rejection_registry",
        "rejected_descriptor",
        "rejected_meta",
        "rejected_symlink",
        "rejected_unexpected",
        "filing_unexpected",
    ),
)
def test_filing_clear_preflight_rejects_all_invalid_evidence_before_deletion(
    tmp_path: Path,
    corruption: _FilingCleanupCorruption,
) -> None:
    """filing clear 必须在任何删除前验证 source/control/rejected 完整集合。

    Args:
        tmp_path: pytest 临时目录。
        corruption: 待注入的 filing tree 损坏类型。

    Returns:
        无。

    Raises:
        AssertionError: 验证失败后任一 staging 条目被部分删除时抛出。
    """

    workspace_root = tmp_path / f"filing-clear-{corruption}"
    repository_set = build_fs_repository_set(workspace_root=workspace_root)
    batching = FsBatchingRepository(workspace_root, repository_set=repository_set)
    source = FsSourceDocumentRepository(workspace_root, repository_set=repository_set)
    blob = FsDocumentBlobRepository(workspace_root, repository_set=repository_set)
    maintenance = FsFilingMaintenanceRepository(
        workspace_root,
        repository_set=repository_set,
    )
    batch = batching.begin_batch("AAPL")
    for document_id in ("fil_first", "fil_second"):
        _create_complete_source(
            source,
            blob,
            batch=batch,
            document_id=document_id,
        )
    _create_complete_rejected_artifact(
        maintenance,
        batch=batch,
        document_id="fil_rejected",
    )
    maintenance.save_download_rejection_registry(
        "AAPL",
        {},
        batch=batch,
    )

    state = _only_active_batch_state(repository_set.core)
    filings_root = state.staging_ticker_dir / "filings"
    filing_dir = repository_set.core._source_meta_path(
        "AAPL",
        "fil_second",
        SourceKind.FILING,
        state,
    ).parent
    rejected_root = repository_set.core._rejected_filings_root("AAPL", state)
    rejected_dir = repository_set.core._rejected_filing_meta_path(
        "AAPL",
        "fil_rejected",
        state,
    ).parent
    outside_target = tmp_path / "outside-rejected-target"
    outside_target.mkdir()

    if corruption == "filing_descriptor":
        _identity_descriptor_file(filing_dir).write_text("{}", encoding="utf-8")
    elif corruption == "filing_manifest":
        (filings_root / "filing_manifest.json").write_text("{", encoding="utf-8")
    elif corruption == "rejection_registry":
        (filings_root / "_download_rejections.json").write_text("[]", encoding="utf-8")
    elif corruption == "rejected_descriptor":
        _identity_descriptor_file(rejected_dir).write_text("{}", encoding="utf-8")
    elif corruption == "rejected_meta":
        (rejected_dir / "meta.json").write_text("{", encoding="utf-8")
    elif corruption == "rejected_symlink":
        (rejected_root / "unexpected-link").symlink_to(
            outside_target,
            target_is_directory=True,
        )
    elif corruption == "rejected_unexpected":
        (rejected_root / "unexpected-file").write_text("unexpected", encoding="utf-8")
    else:
        (filings_root / "unexpected-control").write_text("unexpected", encoding="utf-8")

    entries_before = {entry.name for entry in filings_root.iterdir()}
    with pytest.raises((ValueError, OSError)):
        maintenance.clear_filing_documents("AAPL", batch=batch)

    assert {entry.name for entry in filings_root.iterdir()} == entries_before
    assert repository_set.core._source_meta_path(
        "AAPL",
        "fil_first",
        SourceKind.FILING,
        state,
    ).parent.exists()
    assert filing_dir.exists()
    assert rejected_dir.exists()
    batching.rollback_batch(batch)


@pytest.mark.parametrize(
    "corruption",
    (
        "descriptor",
        "meta_missing",
        "meta_corrupt",
        "meta_mismatch",
        "manifest",
        "symlink",
        "unexpected",
    ),
)
def test_processed_clear_preflight_rejects_all_invalid_evidence_before_deletion(
    tmp_path: Path,
    corruption: _ProcessedCleanupCorruption,
) -> None:
    """processed clear 必须在任何删除前验证 identity/meta/control 完整集合。

    Args:
        tmp_path: pytest 临时目录。
        corruption: 待注入的 processed tree 损坏类型。

    Returns:
        无。

    Raises:
        AssertionError: 验证失败后任一 staging 条目被部分删除时抛出。
    """

    workspace_root = tmp_path / f"processed-clear-{corruption}"
    repository_set = build_fs_repository_set(workspace_root=workspace_root)
    batching = FsBatchingRepository(workspace_root, repository_set=repository_set)
    processed = FsProcessedDocumentRepository(workspace_root, repository_set=repository_set)
    batch = batching.begin_batch("AAPL")
    for document_id in ("processed-first", "processed-second"):
        processed.create_processed(
            ProcessedCreateRequest(
                ticker="AAPL",
                document_id=document_id,
                internal_document_id=document_id,
                source_kind=SourceKind.FILING.value,
                form_type="10-K",
                sections=[],
                tables=[],
            ),
            batch=batch,
        )

    state = _only_active_batch_state(repository_set.core)
    processed_root = state.staging_ticker_dir / "processed"
    processed_dir = repository_set.core._processed_dir_for_write(
        "AAPL",
        "processed-second",
        state,
    )
    meta_path = processed_dir / "tool_snapshot_meta.json"
    outside_target = tmp_path / "outside-processed-target"
    outside_target.mkdir()

    if corruption == "descriptor":
        _identity_descriptor_file(processed_dir).write_text("{}", encoding="utf-8")
    elif corruption == "meta_missing":
        meta_path.unlink()
    elif corruption == "meta_corrupt":
        meta_path.write_text("{", encoding="utf-8")
    elif corruption == "meta_mismatch":
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        assert isinstance(meta, dict)
        meta["document_id"] = "processed-other"
        meta_path.write_text(json.dumps(meta), encoding="utf-8")
    elif corruption == "manifest":
        (processed_root / "manifest.json").write_text("{", encoding="utf-8")
    elif corruption == "symlink":
        (processed_root / "unexpected-link").symlink_to(
            outside_target,
            target_is_directory=True,
        )
    else:
        (processed_root / "unexpected-file").write_text("unexpected", encoding="utf-8")

    entries_before = {entry.name for entry in processed_root.iterdir()}
    with pytest.raises((ValueError, OSError)):
        processed.clear_processed_documents("AAPL", batch=batch)

    assert {entry.name for entry in processed_root.iterdir()} == entries_before
    assert repository_set.core._processed_dir_for_write(
        "AAPL",
        "processed-first",
        state,
    ).exists()
    assert processed_dir.exists()
    batching.rollback_batch(batch)


@pytest.mark.parametrize("corruption", ("missing", "corrupt", "mismatch"))
def test_stale_cleanup_meta_failure_is_fail_closed_without_partial_deletion(
    tmp_path: Path,
    corruption: _StaleMetaCorruption,
) -> None:
    """stale cleanup 对缺失、损坏或不匹配 meta 必须在删除前 fail closed。

    Args:
        tmp_path: pytest 临时目录。
        corruption: source meta 损坏类型。

    Returns:
        无。

    Raises:
        AssertionError: 其它 stale source 或 manifest 被部分删除时抛出。
    """

    workspace_root = tmp_path / f"stale-meta-{corruption}"
    repository_set = build_fs_repository_set(workspace_root=workspace_root)
    batching = FsBatchingRepository(workspace_root, repository_set=repository_set)
    source = FsSourceDocumentRepository(workspace_root, repository_set=repository_set)
    blob = FsDocumentBlobRepository(workspace_root, repository_set=repository_set)
    maintenance = FsFilingMaintenanceRepository(
        workspace_root,
        repository_set=repository_set,
    )
    batch = batching.begin_batch("AAPL")
    for document_id in ("fil_stale_first", "fil_stale_second"):
        _create_complete_source(
            source,
            blob,
            batch=batch,
            document_id=document_id,
        )
    state = _only_active_batch_state(repository_set.core)
    meta_path = repository_set.core._source_meta_path(
        "AAPL",
        "fil_stale_second",
        SourceKind.FILING,
        state,
    )
    if corruption == "missing":
        meta_path.unlink()
    elif corruption == "corrupt":
        meta_path.write_text("{", encoding="utf-8")
    else:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        assert isinstance(meta, dict)
        meta["document_id"] = "fil_other"
        meta_path.write_text(json.dumps(meta), encoding="utf-8")

    filings_root = state.staging_ticker_dir / "filings"
    entries_before = {entry.name for entry in filings_root.iterdir()}
    manifest_path = filings_root / "filing_manifest.json"
    manifest_before = manifest_path.read_text(encoding="utf-8")
    with pytest.raises((ValueError, OSError)):
        maintenance.cleanup_stale_filing_documents(
            "AAPL",
            batch=batch,
            active_form_types={"10-K"},
            valid_document_ids=set(),
        )

    assert {entry.name for entry in filings_root.iterdir()} == entries_before
    assert manifest_path.read_text(encoding="utf-8") == manifest_before
    assert repository_set.core._source_meta_path(
        "AAPL",
        "fil_stale_first",
        SourceKind.FILING,
        state,
    ).parent.exists()
    batching.rollback_batch(batch)


def test_maintenance_public_file_read_delegates_to_unguarded_helper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """maintenance public read 应校验 canonical ticker 后委托 unguarded helper。

    Args:
        tmp_path: pytest 临时目录。
        monkeypatch: pytest monkeypatch fixture。

    Returns:
        无。

    Raises:
        AssertionError: public entry 未按精确参数委托 helper 时抛出。
    """

    workspace_root = tmp_path / "workspace"
    repository_set = build_fs_repository_set(workspace_root=workspace_root)
    maintenance = FsFilingMaintenanceRepository(workspace_root, repository_set=repository_set)
    calls: list[tuple[str, str, str]] = []

    def _read_rejected_filing_file_bytes_unguarded(
        normalized_ticker: str,
        normalized_document_id: str,
        filename: str,
    ) -> bytes:
        """记录 public entry 向 private helper 的 exact identity 委托参数。

        Args:
            normalized_ticker: canonical ticker。
            normalized_document_id: exact external document ID。
            filename: 原始文件名。

        Returns:
            固定测试字节。

        Raises:
            无。
        """

        calls.append((normalized_ticker, normalized_document_id, filename))
        return b"delegated"

    monkeypatch.setattr(
        repository_set.core,
        "_read_rejected_filing_file_bytes_unguarded",
        _read_rejected_filing_file_bytes_unguarded,
    )

    assert (
        maintenance.read_rejected_filing_file_bytes(
            "AAPL",
            " fil_rejected ",
            "rejected.htm",
        )
        == b"delegated"
    )
    assert calls == [("AAPL", " fil_rejected ", "rejected.htm")]


def test_source_owner_material_update_delete_restore_replace_and_reset(tmp_path: Path) -> None:
    """source owner 的 material lifecycle 必须全部消费同一显式 transaction state。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: material mutation 或 published projection 不一致时抛出。
    """

    workspace_root = tmp_path / "workspace"
    repository_set = build_fs_repository_set(workspace_root=workspace_root)
    batching = FsBatchingRepository(workspace_root, repository_set=repository_set)
    source = FsSourceDocumentRepository(workspace_root, repository_set=repository_set)
    blob = FsDocumentBlobRepository(workspace_root, repository_set=repository_set)
    create_batch = batching.begin_batch("AAPL")
    handle = SourceHandle("AAPL", "material-owner", SourceKind.MATERIAL.value)
    file_meta = blob.store_file(
        handle,
        "material-owner.txt",
        io.BytesIO(b"material"),
        batch=create_batch,
    )
    created_handle = source.create_source_document(
        SourceDocumentUpsertRequest(
            ticker="AAPL",
            document_id="material-owner",
            internal_document_id="material-owner",
            form_type="EX-99",
            primary_document="material-owner.txt",
            meta={
                "ingest_method": "upload",
                "source_provider": "user_upload",
                "material_name": "Investor presentation",
            },
            files=[file_meta],
        ),
        SourceKind.MATERIAL,
        batch=create_batch,
    )
    assert created_handle.primary_file_uri == file_meta.uri
    batching.commit_batch(create_batch)
    assert repository_set.core.get_document_meta("AAPL", "material-owner")["material_name"] == "Investor presentation"

    update_batch = batching.begin_batch("AAPL")
    source.update_source_document(
        SourceDocumentUpsertRequest(
            ticker="AAPL",
            document_id="material-owner",
            internal_document_id="material-owner",
            form_type="EX-99.1",
            primary_document="material-owner.txt",
            meta={
                "ingest_method": "upload",
                "source_provider": "user_upload",
                "material_name": "Updated presentation",
            },
        ),
        SourceKind.MATERIAL,
        batch=update_batch,
    )
    state_change = SourceDocumentStateChangeRequest(
        ticker="AAPL",
        document_id="material-owner",
        source_kind=SourceKind.MATERIAL.value,
    )
    source.delete_source_document(state_change, batch=update_batch)
    source.restore_source_document(state_change, batch=update_batch)
    replacement_meta = source.get_source_meta(
        "AAPL",
        "material-owner",
        SourceKind.MATERIAL,
    )
    replacement_meta.update(
        {
            "form_type": "EX-99.1",
            "material_name": "Replaced presentation",
            "is_deleted": False,
        }
    )
    source.replace_source_meta(
        "AAPL",
        "material-owner",
        SourceKind.MATERIAL,
        replacement_meta,
        batch=update_batch,
    )
    batching.commit_batch(update_batch)
    assert (
        source.get_source_meta("AAPL", "material-owner", SourceKind.MATERIAL)["material_name"]
        == "Replaced presentation"
    )

    reset_batch = batching.begin_batch("AAPL")
    source.reset_source_document(
        "AAPL",
        "material-owner",
        SourceKind.MATERIAL,
        batch=reset_batch,
    )
    batching.commit_batch(reset_batch)
    with pytest.raises(FileNotFoundError):
        source.get_source_meta("AAPL", "material-owner", SourceKind.MATERIAL)


def test_primary_uri_owner_requires_exact_explicit_primary_name() -> None:
    """主文件 URI owner 只允许显式主文件名精确命中。

    Returns:
        无。

    Raises:
        AssertionError: 缺失或错误主文件名仍投影第一文件 URI 时抛出。
    """

    file_payloads = [
        {"name": "first.txt", "uri": "local://private-ticker/materials/private-document/first.txt"},
        {"name": "primary.txt", "uri": "local://private-ticker/materials/private-document/primary.txt"},
    ]

    assert (
        storage_utils_module._resolve_primary_uri(file_payloads, "primary.txt")
        == "local://private-ticker/materials/private-document/primary.txt"
    )
    assert storage_utils_module._resolve_primary_uri(file_payloads, "missing.txt") is None
    assert storage_utils_module._resolve_primary_uri(file_payloads, None) is None


@pytest.mark.parametrize(
    "normalizer",
    (_normalize_entry_name, _normalize_filename),
)
@pytest.mark.parametrize("value", ("", "   ", ".", "..", "a/b", "a\\b", "C:"))
def test_filename_and_entry_names_still_reject_path_components(
    normalizer: _Normalizer,
    value: str,
) -> None:
    """filename/entry owner 应继续拒绝非法单路径组件。

    Args:
        normalizer: 当前被验证的 owner normalizer。
        value: 非法输入。

    Returns:
        无。

    Raises:
        AssertionError: owner 未 fail closed 时由 pytest 抛出。
    """

    with pytest.raises(ValueError):
        normalizer(value)


@pytest.mark.parametrize(
    ("key", "expected"),
    (
        ("AAPL/filings/report.md", "AAPL/filings/report.md"),
        (" BRK.B / reports-2024 / annual.report.pdf ", "BRK.B/reports-2024/annual.report.pdf"),
    ),
)
def test_object_key_owner_normalizes_valid_values(key: str, expected: str) -> None:
    """object-key owner应逐组件规范化合法多组件key。

    Args:
        key: 合法原始对象key。
        expected: 预期canonical key。

    Returns:
        无。

    Raises:
        AssertionError: owner normalization结果错误时由pytest抛出。
    """

    assert _normalize_object_key(key) == expected


@pytest.mark.parametrize(
    "key",
    ("", "   ", "/absolute", "a//b", "a/../b", "a/./b", "a\\b", "C:/b"),
)
def test_object_key_owner_rejects_invalid_values(key: str) -> None:
    """object-key owner应直接拒绝非法多组件key。

    Args:
        key: 非法对象key。

    Returns:
        无。

    Raises:
        AssertionError: owner未fail closed时由pytest抛出。
    """

    with pytest.raises(ValueError):
        _normalize_object_key(key)


@pytest.mark.parametrize(
    "key",
    ("", "   ", "/absolute", "a//b", "a/../b", "a/./b", "a\\b", "C:/b"),
)
def test_local_file_store_rejects_invalid_object_keys_without_external_writes(
    tmp_path: Path,
    key: str,
) -> None:
    """非法对象 key 应在构造路径前失败且不得写到 root 外。

    Args:
        tmp_path: pytest 临时目录。
        key: 非法对象 key。

    Returns:
        无。

    Raises:
        AssertionError: key 被接受或文件系统发生越界变化时由 pytest 抛出。
    """

    outside = tmp_path / "outside.txt"
    outside.write_text("sentinel", encoding="utf-8")
    store_root = tmp_path / "objects"
    store = LocalFileStore(store_root)

    with pytest.raises(ValueError):
        store.put_object(key, io.BytesIO(b"payload"))

    assert outside.read_text(encoding="utf-8") == "sentinel"
    assert tuple(store_root.rglob("*")) == ()


@pytest.mark.parametrize(
    "uri",
    (
        "",
        "https://example.com/a.pdf",
        "local://",
        "local:///absolute",
        "local://a//b",
        "local://a/../b",
        "local://a\\b",
    ),
)
def test_local_uri_owner_rejects_invalid_keys(tmp_path: Path, uri: str) -> None:
    """local URI 应复用对象 key owner并拒绝非法或越界表达。

    Args:
        tmp_path: pytest 临时目录。
        uri: 非法 URI。

    Returns:
        无。

    Raises:
        AssertionError: URI 被错误解析时由 pytest 抛出。
    """

    portfolio_root = tmp_path / "portfolio"
    portfolio_root.mkdir()
    with pytest.raises(ValueError):
        _local_path_from_uri(portfolio_root, uri)


def test_local_uri_owner_rejects_symlink_escape(tmp_path: Path) -> None:
    """local URI resolve 后越出 portfolio root 时应 fail closed。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: symlink escape 未被 containment check 拒绝时由 pytest 抛出。
        OSError: 测试环境无法创建 symlink 时由 pytest 抛出。
    """

    portfolio_root = tmp_path / "portfolio"
    outside_root = tmp_path / "outside"
    portfolio_root.mkdir()
    outside_root.mkdir()
    (portfolio_root / "escape").symlink_to(outside_root, target_is_directory=True)

    with pytest.raises(ValueError, match="越界"):
        _local_path_from_uri(portfolio_root, "local://escape/report.pdf")


def test_valid_dot_hyphen_identity_and_object_key_round_trip(tmp_path: Path) -> None:
    """合法点号/连字符 identity 与普通文件名应继续 round-trip。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 合法 identity 被过窄规则拒绝或内容不一致时由 pytest 抛出。
    """

    key = "BRK.B/filings/annual-report/report-2024.md"
    store = LocalFileStore(tmp_path / "objects")

    meta = store.put_object(key, io.BytesIO(b"round-trip"), content_type="text/markdown")

    assert meta.uri == f"local://{key}"
    with store.get_object(key) as stream:
        assert stream.read() == b"round-trip"


@pytest.mark.parametrize(
    ("handle", "expects_store"),
    (
        (
            SourceHandle(ticker="AAPL", document_id="blob-first", source_kind=SourceKind.FILING.value),
            True,
        ),
        (ProcessedHandle(ticker="AAPL", document_id="missing-processed"), False),
    ),
)
def test_store_file_allows_blob_first_source_but_requires_processed_meta(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    handle: SourceHandle | ProcessedHandle,
    expects_store: bool,
) -> None:
    """source handle 不需 meta ack；processed handle 仍由其自身 meta 授权目录。

    Args:
        tmp_path: pytest 临时目录。
        monkeypatch: pytest monkeypatch fixture。
        handle: 不存在的 source/processed handle。
        expects_store: 当前 handle 是否应进入 FileStore。

    Returns:
        无。

    Raises:
        AssertionError: blob-first 或 processed meta contract 错误时由 pytest 抛出。
    """

    file_store = LocalFileStore(tmp_path / "objects")
    put_keys: list[str] = []

    def _record_put(
        key: str,
        data: BinaryIO,
        *,
        content_type: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> FileObjectMeta:
        """记录意外的 put 调用。

        Args:
            key: 对象 key。
            data: 二进制流。
            content_type: 可选内容类型。
            metadata: 可选元数据。

        Returns:
            不应被使用的占位元数据。

        Raises:
            无。
        """

        del data, content_type, metadata
        put_keys.append(key)
        return FileObjectMeta(uri=f"local://{key}")

    monkeypatch.setattr(file_store, "put_object", _record_put)
    repository_set = build_fs_repository_set(
        workspace_root=tmp_path / "workspace",
        file_store=file_store,
    )
    blob_repository = FsDocumentBlobRepository(
        tmp_path / "workspace",
        repository_set=repository_set,
    )
    batching_repository = FsBatchingRepository(
        tmp_path / "workspace",
        repository_set=repository_set,
    )
    batch = batching_repository.begin_batch(handle.ticker)

    try:
        if expects_store:
            blob_repository.store_file(
                handle,
                "report.md",
                io.BytesIO(b"payload"),
                batch=batch,
            )
        else:
            with pytest.raises(FileNotFoundError):
                blob_repository.store_file(
                    handle,
                    "report.md",
                    io.BytesIO(b"payload"),
                    batch=batch,
                )
    finally:
        batching_repository.rollback_batch(batch)

    if expects_store:
        assert len(put_keys) == 1
        object_key_parts = put_keys[0].split("/")
        assert len(object_key_parts) == 4
        assert object_key_parts[0] == "AAPL"
        assert object_key_parts[1] == "filings"
        assert object_key_parts[3] == "report.md"
        assert "blob-first" not in put_keys[0]
    else:
        assert put_keys == []


def test_existing_source_and_processed_handles_share_blob_contract(tmp_path: Path) -> None:
    """存在的source/processed handle应复用同一blob读写与entry contract。

    Args:
        tmp_path: pytest临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 两类handle行为不一致时由pytest抛出。
    """

    workspace_root = tmp_path / "workspace"
    repository_set = build_fs_repository_set(workspace_root=workspace_root)
    source_repository = FsSourceDocumentRepository(workspace_root, repository_set=repository_set)
    processed_repository = FsProcessedDocumentRepository(workspace_root, repository_set=repository_set)
    blob_repository = FsDocumentBlobRepository(workspace_root, repository_set=repository_set)
    batching_repository = FsBatchingRepository(workspace_root, repository_set=repository_set)
    source_request = SourceDocumentUpsertRequest(
        ticker="AAPL",
        document_id="annual-report",
        internal_document_id="annual-report",
        form_type="10-K",
        primary_document="report.md",
        meta={
            "ingest_method": "upload",
            "source_provider": "user_upload",
        },
    )
    batch = batching_repository.begin_batch("AAPL")
    source_handle = SourceHandle(
        ticker="AAPL",
        document_id="annual-report",
        source_kind=SourceKind.FILING.value,
    )
    processed_handle = ProcessedHandle(ticker="AAPL", document_id="annual-report")
    try:
        processed_repository.create_processed(
            ProcessedCreateRequest(
                ticker="AAPL",
                document_id="annual-report",
                internal_document_id="annual-report",
                source_kind=SourceKind.FILING.value,
                form_type="10-K",
                meta={},
                sections=[],
                tables=[],
            ),
            batch=batch,
        )
        source_file_meta = blob_repository.store_file(
            source_handle,
            "report.md",
            io.BytesIO(b"source"),
            batch=batch,
        )
        blob_repository.store_file(
            processed_handle,
            "analysis.json",
            io.BytesIO(b"processed"),
            batch=batch,
        )
        source_repository.create_source_document(
            SourceDocumentUpsertRequest(
                ticker=source_request.ticker,
                document_id=source_request.document_id,
                internal_document_id=source_request.internal_document_id,
                form_type=source_request.form_type,
                primary_document=source_request.primary_document,
                meta=source_request.meta,
                files=[source_file_meta],
            ),
            SourceKind.FILING,
            batch=batch,
        )
    except Exception:
        batching_repository.rollback_batch(batch)
        raise
    batching_repository.commit_batch(batch)

    assert blob_repository.read_file_bytes(source_handle, "report.md") == b"source"
    assert blob_repository.read_file_bytes(processed_handle, "analysis.json") == b"processed"
    assert [entry.name for entry in blob_repository.list_entries(source_handle)] == [
        "meta.json",
        "report.md",
    ]
    assert blob_repository.list_files(source_handle) == [source_file_meta]
    delete_batch = batching_repository.begin_batch("AAPL")
    blob_repository.delete_entry(processed_handle, "analysis.json", batch=delete_batch)
    batching_repository.commit_batch(delete_batch)
    with pytest.raises(FileNotFoundError):
        blob_repository.read_file_bytes(processed_handle, "analysis.json")


@pytest.mark.parametrize(
    ("failure_point", "old_target_exists"),
    (
        ("backup_rename", True),
        ("backed_journal", True),
        ("backed_journal", False),
        ("staging_rename", True),
        ("staging_rename", False),
        ("swapped_journal", True),
        ("swapped_journal", False),
        ("committed_journal", True),
        ("committed_journal", False),
    ),
)
def test_each_precommit_failure_restores_original_observable_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_point: _CommitFailurePoint,
    old_target_exists: bool,
) -> None:
    """每个 pre-commit phase failure 都应恢复旧 target或保持不存在。

    Args:
        tmp_path: pytest 临时目录。
        monkeypatch: pytest monkeypatch fixture。
        failure_point: 按phase/path命名的注入点。
        old_target_exists: 提交前是否存在正式target。

    Returns:
        无。

    Raises:
        AssertionError: rollback后的物理状态或token生命周期错误时由pytest抛出。
    """

    core, batch, paths = _begin_mutated_batch(tmp_path, old_target_exists=old_target_exists)
    original_replace = core._replace_directory
    original_write_journal = core._write_batch_journal
    injected_error = OSError(f"injected {failure_point}")

    def _replace_directory(source: Path, target: Path) -> None:
        """按source/target语义注入rename失败。

        Args:
            source: rename源目录。
            target: rename目标目录。

        Returns:
            无。

        Raises:
            OSError: 命中指定phase path时抛出。
        """

        if failure_point == "backup_rename" and source == paths.target_ticker_dir:
            raise injected_error
        if failure_point == "staging_rename" and source == paths.staging_ticker_dir:
            raise injected_error
        original_replace(source, target)

    def _write_journal(
        current_state: storage_infra_module._ActiveBatchState,
        phase: str,
    ) -> None:
        """按phase语义注入journal失败。

        Args:
            current_state: 当前内部 transaction state。
            phase: 待写入phase。

        Returns:
            无。

        Raises:
            OSError: 命中指定phase时抛出。
        """

        phase_by_failure: dict[_CommitFailurePoint, str] = {
            "backup_rename": "",
            "backed_journal": _PHASE_BACKED_UP_TARGET,
            "staging_rename": "",
            "swapped_journal": _PHASE_SWAPPED_TARGET,
            "committed_journal": _PHASE_COMMITTED,
        }
        if phase == phase_by_failure[failure_point]:
            raise injected_error
        original_write_journal(current_state, phase)

    monkeypatch.setattr(core, "_replace_directory", _replace_directory)
    monkeypatch.setattr(core, "_write_batch_journal", _write_journal)

    with pytest.raises(OSError) as exc_info:
        core.commit_batch(batch)

    assert exc_info.value is injected_error
    if old_target_exists:
        assert (paths.target_ticker_dir / "state.txt").read_text(encoding="utf-8") == "old"
    else:
        assert not paths.target_ticker_dir.exists()
    assert not paths.staging_root_dir.exists()
    assert not paths.backup_dir.exists()
    with pytest.raises(ValueError, match="无效的 batch token"):
        core.rollback_batch(batch)


def test_commit_and_rollback_failure_preserve_primary_cause_and_recovery_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """commit与rollback双失败应保留primary、cause及物理恢复证据。

    Args:
        tmp_path: pytest 临时目录。
        monkeypatch: pytest monkeypatch fixture。

    Returns:
        无。

    Raises:
        AssertionError: 异常chain或evidence被覆盖/清理时由pytest抛出。
    """

    core, batch, paths = _begin_mutated_batch(tmp_path, old_target_exists=True)
    original_replace = core._replace_directory
    original_write_journal = core._write_batch_journal
    commit_error = OSError("injected swapped journal failure")
    rollback_error = OSError("injected target restore failure")

    def _replace_directory(source: Path, target: Path) -> None:
        """在rollback撤回new target时注入失败。

        Args:
            source: rename源目录。
            target: rename目标目录。

        Returns:
            无。

        Raises:
            OSError: 命中target到staging撤回时抛出。
        """

        if source == paths.target_ticker_dir and target == paths.staging_ticker_dir:
            raise rollback_error
        original_replace(source, target)

    def _write_journal(
        current_state: storage_infra_module._ActiveBatchState,
        phase: str,
    ) -> None:
        """在SWAPPED_TARGET journal写入时注入primary failure。

        Args:
            current_state: 当前内部 transaction state。
            phase: 待写入phase。

        Returns:
            无。

        Raises:
            OSError: phase为SWAPPED_TARGET时抛出。
        """

        if phase == _PHASE_SWAPPED_TARGET:
            raise commit_error
        original_write_journal(current_state, phase)

    monkeypatch.setattr(core, "_replace_directory", _replace_directory)
    monkeypatch.setattr(core, "_write_batch_journal", _write_journal)

    with pytest.raises(OSError) as exc_info:
        core.commit_batch(batch)

    assert exc_info.value is commit_error
    assert exc_info.value.__cause__ is rollback_error
    assert any("recovery evidence retained" in note for note in exc_info.value.__notes__)
    assert paths.journal_path.exists()
    assert paths.backup_dir.exists()
    assert paths.staging_root_dir.exists()
    assert (paths.target_ticker_dir / "state.txt").read_text(encoding="utf-8") == "new"
    with pytest.raises(ValueError, match="无效的 batch token"):
        core.rollback_batch(batch)


def test_commit_primary_failure_survives_writer_release_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """commit 主失败与 writer release 双失败时必须保留 commit 主因并消费 capability。

    Args:
        tmp_path: pytest 临时目录。
        monkeypatch: pytest monkeypatch fixture。

    Returns:
        无。

    Raises:
        AssertionError: writer release failure 覆盖主因或 registry 未进入终态时抛出。
    """

    core, batch, paths = _begin_mutated_batch(tmp_path, old_target_exists=True)
    state = _only_active_batch_state(core)
    original_replace = core._replace_directory
    original_release = core._release_lock_token
    commit_error = OSError("injected commit primary failure")
    publication_release_error = PermissionError(
        errno.EACCES,
        "publication release private message",
        str(core._publication_lock_path("AAPL")),
    )
    writer_release_error = PermissionError(
        errno.EACCES,
        "writer release private message",
        str(state.writer_lock_token.lock_path),
    )
    publication_token: RuntimeFileLockToken | None = None

    def _replace_directory(source: Path, target: Path) -> None:
        """在 target-to-backup rename 注入 commit 主失败。

        Args:
            source: rename 源目录。
            target: rename 目标目录。

        Returns:
            无。

        Raises:
            OSError: 命中 commit 第一个 rename 时抛出。
        """

        if source == paths.target_ticker_dir and target == paths.backup_dir:
            raise commit_error
        original_replace(source, target)

    def _release_lock_token(token: RuntimeFileLockToken) -> None:
        """在 publication 与 terminal writer release 注入 pathful 次级失败。

        Args:
            token: 待释放的 runtime 文件锁 token。

        Returns:
            无。

        Raises:
            PermissionError: publication 或 writer token release 时抛出。
        """

        nonlocal publication_token
        if token is state.writer_lock_token:
            raise writer_release_error
        publication_token = token
        raise publication_release_error

    monkeypatch.setattr(core, "_replace_directory", _replace_directory)
    monkeypatch.setattr(core, "_release_lock_token", _release_lock_token)

    try:
        with pytest.raises(OSError) as exc_info:
            core.commit_batch(batch)

        assert exc_info.value is commit_error
        notes = exc_info.value.__notes__
        assert f"publication guard release failed: error_type=PermissionError errno={errno.EACCES}" in notes
        assert (
            "writer mutex release failed during terminal cleanup: "
            f"error_type=PermissionError errno={errno.EACCES}" in notes
        )
        _assert_exception_graph_path_free(
            exc_info.value,
            forbidden_locators=(
                str(core.workspace_root),
                core._publication_lock_path("AAPL").name,
                state.writer_lock_token.lock_path.name,
                "publication release private message",
                "writer release private message",
            ),
        )
        assert batch.transaction_id not in core._active_batches
        assert "AAPL" not in core._active_transaction_by_ticker
    finally:
        if publication_token is not None:
            original_release(publication_token)
        original_release(state.writer_lock_token)


def test_commit_batch_publication_release_failure_preserves_committed_truth(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """COMMITTED 后 publication release 主失败必须抛出且不得回滚新 published tree。

    Args:
        tmp_path: pytest 临时目录。
        monkeypatch: pytest monkeypatch fixture。

    Returns:
        无。

    Raises:
        AssertionError: post-commit 主因被覆盖、durable tree 回滚或 capability 未终态时抛出。
    """

    core, batch, paths = _begin_mutated_batch(tmp_path, old_target_exists=True)
    state = _only_active_batch_state(core)
    original_release = core._release_lock_token
    publication_release_error = RuntimeFileLockError("injected publication guard release failure")
    cleanup_error = PermissionError(
        errno.EACCES,
        "post-commit cleanup private message",
        str(paths.backup_dir),
    )
    writer_release_error = PermissionError(
        errno.EACCES,
        "writer cleanup private message",
        str(state.writer_lock_token.lock_path),
    )
    publication_token: RuntimeFileLockToken | None = None
    rollback_called = False

    def _release_lock_token(token: RuntimeFileLockToken) -> None:
        """按真实 terminal 顺序注入 publication 与 writer release failure。

        Args:
            token: 待释放的 runtime 文件锁 token。

        Returns:
            无。

        Raises:
            RuntimeFileLockError: publication guard token 释放时抛出。
            PermissionError: writer token 释放时抛出。
        """

        nonlocal publication_token
        if token is state.writer_lock_token:
            raise writer_release_error
        publication_token = token
        raise publication_release_error

    def _cleanup_committed_batch(
        current_state: storage_infra_module._ActiveBatchState,
    ) -> None:
        """在 publication release 主失败后注入 cleanup 次级失败。

        Args:
            current_state: 已进入 COMMITTED 的 internal transaction state。

        Returns:
            无。

        Raises:
            PermissionError: 始终抛出注入的 cleanup failure。
        """

        assert current_state is state
        raise cleanup_error

    def _rollback_precommit_batch(
        current_state: storage_infra_module._ActiveBatchState,
    ) -> None:
        """记录错误实现是否误入 pre-commit rollback。

        Args:
            current_state: 被错误交给 rollback 的 internal transaction state。

        Returns:
            无。

        Raises:
            无。
        """

        nonlocal rollback_called
        assert current_state is state
        rollback_called = True

    monkeypatch.setattr(core, "_release_lock_token", _release_lock_token)
    monkeypatch.setattr(core, "_cleanup_committed_batch", _cleanup_committed_batch)
    monkeypatch.setattr(core, "_rollback_precommit_batch", _rollback_precommit_batch)

    try:
        with pytest.raises(RuntimeFileLockError) as exc_info:
            core.commit_batch(batch)

        assert exc_info.value is publication_release_error
        notes = exc_info.value.__notes__
        assert (
            "post-commit cleanup failed after publication guard release failure: "
            f"error_type=PermissionError errno={errno.EACCES}" in notes
        )
        assert (
            "writer mutex release failed during terminal cleanup: "
            f"error_type=PermissionError errno={errno.EACCES}" in notes
        )
        _assert_exception_graph_path_free(
            exc_info.value,
            forbidden_locators=(
                str(core.workspace_root),
                paths.backup_dir.name,
                state.writer_lock_token.lock_path.name,
                "post-commit cleanup private message",
                "writer cleanup private message",
            ),
        )
        assert not rollback_called
        assert state.phase == _PHASE_COMMITTED
        assert (paths.target_ticker_dir / "state.txt").read_text(encoding="utf-8") == "new"
        assert batch.transaction_id not in core._active_batches
        assert "AAPL" not in core._active_transaction_by_ticker
        with pytest.raises(ValueError, match="未在当前 storage core 登记"):
            core.commit_batch(batch)
    finally:
        if publication_token is not None:
            original_release(publication_token)
        original_release(state.writer_lock_token)


def test_rollback_journal_failure_survives_writer_release_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """rollback journal 主失败与 writer release 双失败时必须保留 journal 主因。

    Args:
        tmp_path: pytest 临时目录。
        monkeypatch: pytest monkeypatch fixture。

    Returns:
        无。

    Raises:
        AssertionError: writer release failure 覆盖 journal 主因或 registry 未消费时抛出。
    """

    core, batch, _paths = _begin_mutated_batch(tmp_path, old_target_exists=True)
    state = _only_active_batch_state(core)
    original_write_journal = core._write_batch_journal
    original_release = core._release_lock_token
    rollback_error = OSError("injected rollback journal failure")
    release_error = RuntimeError("injected writer release failure")

    def _write_batch_journal(
        current_state: storage_infra_module._ActiveBatchState,
        phase: str,
    ) -> None:
        """在 ROLLED_BACK journal 写入注入 rollback 主失败。

        Args:
            current_state: 当前 internal transaction state。
            phase: 待写入的 journal phase。

        Returns:
            无。

        Raises:
            OSError: phase 是 ROLLED_BACK 时抛出。
        """

        if phase == _PHASE_ROLLED_BACK:
            raise rollback_error
        original_write_journal(current_state, phase)

    def _release_lock_token(token: RuntimeFileLockToken) -> None:
        """只在 terminal writer token release 注入次级失败。

        Args:
            token: 待释放的 runtime 文件锁 token。

        Returns:
            无。

        Raises:
            RuntimeError: token 是当前 transaction writer token 时抛出。
        """

        if token is state.writer_lock_token:
            raise release_error
        original_release(token)

    monkeypatch.setattr(core, "_write_batch_journal", _write_batch_journal)
    monkeypatch.setattr(core, "_release_lock_token", _release_lock_token)

    try:
        with pytest.raises(OSError) as exc_info:
            core.rollback_batch(batch)

        assert exc_info.value is rollback_error
        assert any("writer mutex release failed" in note for note in exc_info.value.__notes__)
        assert batch.transaction_id not in core._active_batches
        assert "AAPL" not in core._active_transaction_by_ticker
    finally:
        original_release(state.writer_lock_token)


@pytest.mark.parametrize(
    "phase",
    (_PHASE_STARTED, _PHASE_BACKED_UP_TARGET, _PHASE_SWAPPED_TARGET, _PHASE_COMMITTED),
)
def test_orphan_recovery_follows_journal_commit_point(tmp_path: Path, phase: str) -> None:
    """STARTED/BACKED/SWAPPED应回滚，只有COMMITTED保留new target。

    Args:
        tmp_path: pytest临时目录。
        phase: 要构造的orphan journal phase。

    Returns:
        无。

    Raises:
        AssertionError: recovery对phase解释错误时由pytest抛出。
    """

    core = _build_core(tmp_path)
    paths = _seed_orphan_batch(
        core,
        phase=phase,
        old_target_exists=True,
    )

    core.recover_orphan_batches()

    expected = "new" if phase == _PHASE_COMMITTED else "old"
    assert (paths.target_ticker_dir / "state.txt").read_text(encoding="utf-8") == expected
    assert not paths.backup_dir.exists()
    assert not paths.staging_root_dir.exists()


def test_swapped_target_recovery_without_old_target_deletes_new_target(tmp_path: Path) -> None:
    """原状态不存在时SWAPPED_TARGET recovery必须删除未提交new target。

    Args:
        tmp_path: pytest临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 未提交target被错误保留时由pytest抛出。
    """

    core = _build_core(tmp_path)
    paths = _seed_orphan_batch(
        core,
        phase=_PHASE_SWAPPED_TARGET,
        old_target_exists=False,
    )

    core.recover_orphan_batches()

    assert not paths.target_ticker_dir.exists()
    assert not paths.staging_root_dir.exists()


def test_recovery_rejects_nonminimal_journal_fields_without_touching_evidence(
    tmp_path: Path,
) -> None:
    """recovery journal 字段必须闭集，额外 lock/layout 字段应 fail closed。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 非最小 journal 被消费或 recovery evidence 被改动时抛出。
    """

    core = _build_core(tmp_path)
    paths = _seed_orphan_batch(
        core,
        phase=_PHASE_STARTED,
        old_target_exists=True,
    )
    journal = json.loads(paths.journal_path.read_text(encoding="utf-8"))
    journal["publication_lock"] = "AAPL.publication.lock"
    storage_utils_module._write_json(paths.journal_path, journal)

    actions = core.recover_orphan_batches()

    assert actions == (f"skip batch transaction={paths.staging_root_dir.name} reason=invalid_journal_fields",)
    assert paths.staging_root_dir.exists()
    assert (paths.target_ticker_dir / "state.txt").read_text(encoding="utf-8") == "old"


@pytest.mark.parametrize("raw_journal", ("{", "", "[]"))
def test_unparseable_journal_preserves_evidence_and_later_orphan_recovers(
    tmp_path: Path,
    raw_journal: str,
) -> None:
    """不可解析或非 object journal 应保留 evidence，并继续同轮合法 recovery。

    Args:
        tmp_path: pytest 临时目录。
        raw_journal: 截断、空或非 object 的 transaction journal 文本。

    Returns:
        无。

    Raises:
        AssertionError: malformed evidence 被消费或后续合法 orphan 未恢复时抛出。
        OSError: fixture 文件读写或 recovery 失败时抛出。
    """

    core = _build_core(tmp_path)
    invalid_transaction_dir = core.batch_root / "000-unparseable-journal"
    invalid_transaction_dir.mkdir(parents=True)
    invalid_journal_path = invalid_transaction_dir / "transaction.json"
    invalid_journal_path.write_text(raw_journal, encoding="utf-8")
    valid_paths = _seed_orphan_batch(
        core,
        phase=_PHASE_BACKED_UP_TARGET,
        old_target_exists=True,
    )

    actions = core.recover_orphan_batches()

    assert f"skip batch transaction={invalid_transaction_dir.name} reason=unparseable_journal" in actions
    assert any(
        action.startswith(f"restore backup ticker=AAPL transaction={valid_paths.staging_root_dir.name}")
        for action in actions
    )
    assert invalid_transaction_dir.is_dir()
    assert invalid_journal_path.read_text(encoding="utf-8") == raw_journal
    assert (valid_paths.target_ticker_dir / "state.txt").read_text(encoding="utf-8") == "old"
    assert not valid_paths.staging_root_dir.exists()


def test_invalid_journal_ticker_cannot_escape_canonical_recovery_locator(
    tmp_path: Path,
) -> None:
    """路径形态 journal ticker 必须被拒绝且不能逃逸 canonical locator。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 非法 ticker 逃逸、改写他方 target 或阻断合法恢复时抛出。
    """

    core = _build_core(tmp_path)
    protected_target = core._target_ticker_dir("MSFT")
    core._ensure_ticker_structure(protected_target, "MSFT")
    _write_state(protected_target, "published")
    invalid_transaction_dir = core.batch_root / "000-invalid-journal"
    invalid_transaction_dir.mkdir(parents=True)
    storage_utils_module._write_json(
        invalid_transaction_dir / "transaction.json",
        {
            "transaction_id": invalid_transaction_dir.name,
            "ticker": "../MSFT",
            "phase": _PHASE_STARTED,
        },
    )
    valid_paths = _seed_orphan_batch(
        core,
        phase=_PHASE_BACKED_UP_TARGET,
        old_target_exists=True,
    )

    actions = core.recover_orphan_batches()

    assert invalid_transaction_dir.exists()
    assert f"skip batch transaction={invalid_transaction_dir.name} reason=invalid_journal_ticker" in actions
    assert any(
        action.startswith(f"restore backup ticker=AAPL transaction={valid_paths.staging_root_dir.name}")
        for action in actions
    )
    assert (protected_target / "state.txt").read_text(encoding="utf-8") == "published"
    assert (valid_paths.target_ticker_dir / "state.txt").read_text(encoding="utf-8") == "old"
    assert not valid_paths.staging_root_dir.exists()


def test_orphan_backup_requires_descriptor_and_recovers_canonical_ticker(
    tmp_path: Path,
) -> None:
    """orphan backup 必须由 descriptor 恢复 canonical ticker，损坏项 fail closed。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 非法 backup 被消费、published tree 被误写或合法 backup 未恢复时抛出。
    """

    core = _build_core(tmp_path)
    protected_target = core._target_ticker_dir("AAPL")
    core._ensure_ticker_structure(protected_target, "AAPL")
    _write_state(protected_target, "published")
    invalid_backup = core.backup_root / "corrupt-private-key.bak.000-invalid-backup"
    _write_state(invalid_backup, "invalid")
    ticker = "MSFT"
    valid_target = core._target_ticker_dir(ticker)
    core._ensure_ticker_structure(valid_target, ticker)
    _write_state(valid_target, "valid")
    valid_backup = core.backup_root / f"{valid_target.name}.bak.999-valid-backup"
    core._replace_directory(valid_target, valid_backup)

    actions = core.recover_orphan_batches()

    assert "preserve backup transaction=000-invalid-backup reason=invalid_identity_descriptor" in actions
    assert f"restore backup ticker={ticker} transaction=999-valid-backup" in actions
    assert invalid_backup.exists()
    assert (invalid_backup / "state.txt").read_text(encoding="utf-8") == "invalid"
    assert (protected_target / "state.txt").read_text(encoding="utf-8") == "published"
    assert not valid_backup.exists()
    assert (valid_target / "state.txt").read_text(encoding="utf-8") == "valid"


@pytest.mark.parametrize(
    "phase",
    (_PHASE_STARTED, _PHASE_BACKED_UP_TARGET, _PHASE_SWAPPED_TARGET, _PHASE_COMMITTED),
)
def test_recovery_round_trips_canonical_ticker_from_journal_and_descriptor(
    tmp_path: Path,
    phase: str,
) -> None:
    """每个 crash phase 均应由 journal/descriptor 恢复 canonical ticker old/new。

    Args:
        tmp_path: pytest 临时目录。
        phase: R06 transaction journal crash phase。

    Returns:
        无。

    Raises:
        AssertionError: recovery 从路径名反推 ticker 或恢复出混合状态时抛出。
    """

    core = _build_core(tmp_path)
    ticker = "AAPL"
    paths = _seed_orphan_batch(
        core,
        phase=phase,
        old_target_exists=True,
        ticker=ticker,
    )

    actions = core.recover_orphan_batches()

    expected = "new" if phase == _PHASE_COMMITTED else "old"
    assert (paths.target_ticker_dir / "state.txt").read_text(encoding="utf-8") == expected
    assert not paths.backup_dir.exists()
    assert not paths.staging_root_dir.exists()
    assert any("ticker=AAPL" in action for action in actions)


def test_recovery_rejects_symlinked_transaction_directory_without_escape(tmp_path: Path) -> None:
    """recovery 不得跟随 batch root 下的 transaction symlink 访问外部目录。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: recovery 跟随 symlink 或改写外部 sentinel 时抛出。
        OSError: 测试环境无法创建 symlink 时抛出。
    """

    core = _build_core(tmp_path)
    outside = tmp_path / "outside-transaction"
    outside.mkdir()
    sentinel = outside / "sentinel.txt"
    sentinel.write_text("outside", encoding="utf-8")
    (core.batch_root / "symlinked-transaction").symlink_to(
        outside,
        target_is_directory=True,
    )

    core.recover_orphan_batches()

    assert sentinel.read_text(encoding="utf-8") == "outside"
    assert (core.batch_root / "symlinked-transaction").is_symlink()


def test_postcommit_cleanup_failure_returns_success_and_recovery_cleans_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """COMMITTED后的cleanup failure不得伪装成commit failure。

    Args:
        tmp_path: pytest临时目录。
        monkeypatch: pytest monkeypatch fixture。

    Returns:
        无。

    Raises:
        AssertionError: commit返回、target或后续recovery行为错误时由pytest抛出。
    """

    core, batch, paths = _begin_mutated_batch(tmp_path, old_target_exists=True)
    original_remove = core._remove_directory
    cleanup_error = OSError("injected committed backup cleanup failure")

    def _remove_directory(path: Path) -> None:
        """在COMMITTED后的backup cleanup注入失败。

        Args:
            path: 待删除目录。

        Returns:
            无。

        Raises:
            OSError: path为本batch backup时抛出。
        """

        if path == paths.backup_dir:
            raise cleanup_error
        original_remove(path)

    monkeypatch.setattr(core, "_remove_directory", _remove_directory)

    core.commit_batch(batch)

    assert (paths.target_ticker_dir / "state.txt").read_text(encoding="utf-8") == "new"
    assert paths.backup_dir.exists()
    assert paths.journal_path.exists()
    journal = json.loads(paths.journal_path.read_text(encoding="utf-8"))
    assert journal["phase"] == _PHASE_COMMITTED
    monkeypatch.setattr(core, "_remove_directory", original_remove)

    core.recover_orphan_batches()

    assert (paths.target_ticker_dir / "state.txt").read_text(encoding="utf-8") == "new"
    assert not paths.backup_dir.exists()
    assert not paths.staging_root_dir.exists()


def test_commit_cleanup_exception_still_consumes_token_and_releases_writer_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """commit 已成功后即使 cleanup helper 异常也必须关闭 registry 与 writer mutex。

    Args:
        tmp_path: pytest 临时目录。
        monkeypatch: pytest monkeypatch fixture。

    Returns:
        无。

    Raises:
        AssertionError: cleanup 异常留下 active capability 或 writer lock 时抛出。
    """

    core, batch, _paths = _begin_mutated_batch(tmp_path, old_target_exists=True)
    cleanup_error = RuntimeError("injected cleanup helper failure")

    def _raise_cleanup(current_state: storage_infra_module._ActiveBatchState) -> None:
        """模拟已 commit 后的非文件系统 cleanup 异常。

        Args:
            current_state: 已提交的内部 transaction state。

        Returns:
            无。

        Raises:
            RuntimeError: 始终抛出测试异常。
        """

        del current_state
        raise cleanup_error

    monkeypatch.setattr(core, "_cleanup_committed_batch", _raise_cleanup)

    with pytest.raises(RuntimeError) as exc_info:
        core.commit_batch(batch)

    assert exc_info.value is cleanup_error
    with pytest.raises(ValueError, match="未在当前 storage core 登记"):
        core.rollback_batch(batch)
    replacement_batch = core.begin_batch("AAPL")
    core.rollback_batch(replacement_batch)


def test_committed_journal_write_syncs_parent_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """COMMITTED journal必须走atomic JSON并刷新journal parent directory。

    Args:
        tmp_path: pytest临时目录。
        monkeypatch: pytest monkeypatch fixture。

    Returns:
        无。

    Raises:
        AssertionError: COMMITTED未触发parent directory sync时由pytest抛出。
    """

    core, batch, paths = _begin_mutated_batch(tmp_path, old_target_exists=True)
    original_sync = storage_utils_module._fsync_directory
    original_write_journal = core._write_batch_journal
    synced_paths: list[Path] = []
    committed_sync_paths: list[Path] = []

    def _record_sync(path: Path) -> None:
        """记录JSON owner执行的directory sync。

        Args:
            path: 被刷新的目录。

        Returns:
            无。

        Raises:
            无。
        """

        synced_paths.append(path)
        original_sync(path)

    def _record_journal(
        current_state: storage_infra_module._ActiveBatchState,
        phase: str,
    ) -> None:
        """记录每个phase写入后最新directory sync。

        Args:
            current_state: 当前内部 transaction state。
            phase: 待写入phase。

        Returns:
            无。

        Raises:
            OSError: journal写入失败时透传。
        """

        before = len(synced_paths)
        original_write_journal(current_state, phase)
        if phase == _PHASE_COMMITTED:
            committed_sync_paths.extend(synced_paths[before:])

    monkeypatch.setattr(storage_utils_module, "_fsync_directory", _record_sync)
    monkeypatch.setattr(core, "_write_batch_journal", _record_journal)

    core.commit_batch(batch)

    assert paths.journal_path.parent in committed_sync_paths


def test_commit_critical_directory_renames_sync_both_parents(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """target/backup/staging关键rename后应刷新source与target parent。

    Args:
        tmp_path: pytest临时目录。
        monkeypatch: pytest monkeypatch fixture。

    Returns:
        无。

    Raises:
        AssertionError: 任一关键rename父目录未刷新时由pytest抛出。
    """

    core, batch, paths = _begin_mutated_batch(tmp_path, old_target_exists=True)
    original_sync = storage_infra_module._fsync_directory
    synced_paths: list[Path] = []

    def _record_sync(path: Path) -> None:
        """记录batch directory sync并调用真实helper。

        Args:
            path: 被刷新的目录。

        Returns:
            无。

        Raises:
            无。
        """

        synced_paths.append(path)
        original_sync(path)

    monkeypatch.setattr(storage_infra_module, "_fsync_directory", _record_sync)

    core.commit_batch(batch)

    assert paths.target_ticker_dir.parent in synced_paths
    assert paths.backup_dir.parent in synced_paths
    assert paths.staging_ticker_dir.parent in synced_paths


def test_concurrent_published_read_ignores_long_writer_staging_and_sees_old(
    tmp_path: Path,
) -> None:
    """长 staging 只持 writer mutex；独立进程 published reader 应立即读到 old。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: reader 被 writer mutex 阻塞或看见 staging 时抛出。
    """

    workspace_root = tmp_path / "workspace"
    repository_set = build_fs_repository_set(workspace_root=workspace_root)
    batching = FsBatchingRepository(workspace_root, repository_set=repository_set)
    source = FsSourceDocumentRepository(workspace_root, repository_set=repository_set)
    blob = FsDocumentBlobRepository(workspace_root, repository_set=repository_set)
    initial_batch = batching.begin_batch("AAPL")
    _create_complete_source(
        source,
        blob,
        batch=initial_batch,
        document_id="published-old",
    )
    batching.commit_batch(initial_batch)
    active_batch = batching.begin_batch("AAPL")
    _create_complete_source(
        source,
        blob,
        batch=active_batch,
        document_id="staged-new",
    )

    assert source.list_source_document_ids("AAPL", SourceKind.FILING) == ["published-old"]
    context = multiprocessing.get_context("spawn")
    parent_connection, child_connection = context.Pipe(duplex=True)
    process = context.Process(
        target=_read_source_ids_in_process,
        args=(str(workspace_root), child_connection),
    )
    process.start()
    child_connection.close()
    try:
        assert parent_connection.poll(5)
        assert parent_connection.recv_bytes() == b"publication_acquire_entered"
        assert parent_connection.poll(2)
        assert parent_connection.recv_bytes() == b"published-old"
    finally:
        process.join(timeout=5)
        if process.is_alive():
            process.terminate()
            process.join(timeout=5)
        parent_connection.close()
        batching.rollback_batch(active_batch)
    assert process.exitcode == 0


def test_complete_source_validator_barrier_does_not_hold_publication_guard(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """长 validator barrier 期间 published reader 应及时读取 old 完整 source。

    Args:
        tmp_path: pytest 临时目录。
        monkeypatch: pytest monkeypatch fixture。

    Returns:
        无。

    Raises:
        AssertionError: validator 错误持有 publication guard 或 reader 看到 staging 时抛出。
    """

    workspace_root = tmp_path / "workspace"
    repository_set = build_fs_repository_set(workspace_root=workspace_root)
    core = repository_set.core
    batching = FsBatchingRepository(workspace_root, repository_set=repository_set)
    source = FsSourceDocumentRepository(workspace_root, repository_set=repository_set)
    blob = FsDocumentBlobRepository(workspace_root, repository_set=repository_set)
    old_batch = batching.begin_batch("AAPL")
    _create_complete_source(
        source,
        blob,
        batch=old_batch,
        document_id="old_source",
    )
    batching.commit_batch(old_batch)
    new_batch = batching.begin_batch("AAPL")
    _create_complete_source(
        source,
        blob,
        batch=new_batch,
        document_id="new_source",
    )
    original_validator = core._validate_complete_source_tree
    validator_entered = Event()
    allow_validator = Event()

    def _blocked_validator(state: storage_infra_module._ActiveBatchState) -> None:
        """在真实 validator 调用前建立长时间测试 barrier。

        Args:
            state: 当前 storage-owned active batch state。

        Returns:
            无。

        Raises:
            TimeoutError: 测试未及时释放 barrier 时抛出。
            ValueError: 真实 validator 拒绝 staged tree 时抛出。
            OSError: 真实 validator I/O 失败时抛出。
        """

        validator_entered.set()
        if not allow_validator.wait(timeout=5):
            raise TimeoutError("complete source validator barrier 未释放")
        original_validator(state)

    monkeypatch.setattr(core, "_validate_complete_source_tree", _blocked_validator)
    with ThreadPoolExecutor(max_workers=2) as executor:
        commit_future = executor.submit(batching.commit_batch, new_batch)
        assert validator_entered.wait(timeout=5)
        read_future = executor.submit(
            source.list_source_document_ids,
            "AAPL",
            SourceKind.FILING,
        )
        assert read_future.result(timeout=1) == ["old_source"]
        allow_validator.set()
        commit_future.result(timeout=5)

    assert source.list_source_document_ids("AAPL", SourceKind.FILING) == [
        "new_source",
        "old_source",
    ]


def test_complete_source_rollback_and_precommit_recovery_keep_source_absent(
    tmp_path: Path,
) -> None:
    """caller rollback 与 STARTED orphan recovery 都不得发布半个或完整 staging source。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: rollback/recovery 后 source 或 blob 变得可见时抛出。
    """

    workspace_root = tmp_path / "workspace"
    repository_set = build_fs_repository_set(workspace_root=workspace_root)
    core = repository_set.core
    batching = FsBatchingRepository(workspace_root, repository_set=repository_set)
    source = FsSourceDocumentRepository(workspace_root, repository_set=repository_set)
    blob = FsDocumentBlobRepository(workspace_root, repository_set=repository_set)
    rollback_batch = batching.begin_batch("AAPL")
    rollback_handle = _create_complete_source(
        source,
        blob,
        batch=rollback_batch,
        document_id="rolled_back_source",
    )
    batching.rollback_batch(rollback_batch)
    with pytest.raises(FileNotFoundError):
        source.get_source_meta("AAPL", "rolled_back_source", SourceKind.FILING)
    with pytest.raises(FileNotFoundError):
        blob.read_file_bytes(rollback_handle, "rolled_back_source.txt")

    orphan_batch = batching.begin_batch("AAPL")
    orphan_handle = _create_complete_source(
        source,
        blob,
        batch=orphan_batch,
        document_id="orphan_source",
    )
    state = _only_active_batch_state(core)
    core._close_active_batch(state)
    actions = core.recover_orphan_batches()
    fresh_source = FsSourceDocumentRepository(workspace_root)
    fresh_blob = FsDocumentBlobRepository(workspace_root)

    assert any("cleanup batch ticker=AAPL" in action and "phase=started" in action for action in actions)
    with pytest.raises(FileNotFoundError):
        fresh_source.get_source_meta("AAPL", "orphan_source", SourceKind.FILING)
    with pytest.raises(FileNotFoundError):
        fresh_blob.read_file_bytes(orphan_handle, "orphan_source.txt")


@pytest.mark.parametrize("barrier", ("target_to_backup", "staging_to_target"))
def test_concurrent_reader_blocks_at_each_publication_rename_barrier(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    barrier: _PublicationBarrier,
) -> None:
    """两个 physical rename barrier 内 reader 都应等待 publication guard 后只见 new。

    Args:
        tmp_path: pytest 临时目录。
        monkeypatch: pytest monkeypatch fixture。
        barrier: target->backup 或 staging->target 注入点。

    Returns:
        无。

    Raises:
        AssertionError: 独立进程未共享 guard、进入 missing window 或终态错误时抛出。
    """

    workspace_root = tmp_path / "workspace"
    repository_set = build_fs_repository_set(workspace_root=workspace_root)
    core = repository_set.core
    batching = FsBatchingRepository(workspace_root, repository_set=repository_set)
    source = FsSourceDocumentRepository(workspace_root, repository_set=repository_set)
    blob = FsDocumentBlobRepository(workspace_root, repository_set=repository_set)
    initial_batch = batching.begin_batch("AAPL")
    _create_complete_source(
        source,
        blob,
        batch=initial_batch,
        document_id="published-old",
    )
    batching.commit_batch(initial_batch)
    active_batch = batching.begin_batch("AAPL")
    _create_complete_source(
        source,
        blob,
        batch=active_batch,
        document_id="published-new",
    )
    paths = _active_batch_paths(core)
    original_replace = core._replace_directory
    rename_entered = Event()
    allow_rename = Event()

    def _block_selected_rename(source_path: Path, target_path: Path) -> None:
        """在指定 publication rename 前建立真实在线 reader barrier。

        Args:
            source_path: rename 源目录。
            target_path: rename 目标目录。

        Returns:
            无。

        Raises:
            TimeoutError: 测试未及时释放 rename barrier 时抛出。
            OSError: 真实 rename 失败时抛出。
        """

        selected = (barrier == "target_to_backup" and source_path == paths.target_ticker_dir) or (
            barrier == "staging_to_target" and source_path == paths.staging_ticker_dir
        )
        if selected:
            rename_entered.set()
            if not allow_rename.wait(timeout=5):
                raise TimeoutError("publication rename barrier 未释放")
        original_replace(source_path, target_path)

    monkeypatch.setattr(core, "_replace_directory", _block_selected_rename)
    context = multiprocessing.get_context("spawn")
    parent_connection, child_connection = context.Pipe(duplex=True)
    process = context.Process(
        target=_read_source_ids_in_process,
        args=(str(workspace_root), child_connection),
    )
    with ThreadPoolExecutor(max_workers=1) as executor:
        commit_future = executor.submit(batching.commit_batch, active_batch)
        assert rename_entered.wait(timeout=5)
        process.start()
        child_connection.close()
        try:
            assert parent_connection.poll(5)
            assert parent_connection.recv_bytes() == b"publication_acquire_entered"
            with pytest.raises(RuntimeError, match="已存在跨进程活动 batch"):
                core._acquire_lock_token(
                    core._publication_lock_path("AAPL"),
                    blocking=False,
                )
            allow_rename.set()
            commit_future.result(timeout=5)
            assert parent_connection.poll(5)
            assert parent_connection.recv_bytes() == b"published-new\0published-old"
        finally:
            allow_rename.set()
            process.join(timeout=5)
            if process.is_alive():
                process.terminate()
                process.join(timeout=5)
            parent_connection.close()
    assert process.exitcode == 0


def test_batch_explicit_staged_xbrl_read_is_separate_from_published_read(tmp_path: Path) -> None:
    """staged XBRL 读取必须显式 batch；默认 published 读取不得看见 staging。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: staged/published read scope 混淆时抛出。
    """

    workspace_root = tmp_path / "workspace"
    repository_set = build_fs_repository_set(workspace_root=workspace_root)
    batching = FsBatchingRepository(workspace_root, repository_set=repository_set)
    source = FsSourceDocumentRepository(workspace_root, repository_set=repository_set)
    blob = FsDocumentBlobRepository(workspace_root, repository_set=repository_set)
    batch = batching.begin_batch("AAPL")
    handle = SourceHandle(
        ticker="AAPL",
        document_id="staged-xbrl",
        source_kind=SourceKind.FILING.value,
    )
    blob.store_file(
        handle,
        "instance.xml",
        io.BytesIO(b"<xbrl />"),
        batch=batch,
        content_type="application/xml",
    )

    assert source.has_staged_filing_xbrl_instance("AAPL", "staged-xbrl", batch=batch)
    with pytest.raises(FileNotFoundError):
        source.has_filing_xbrl_instance("AAPL", "staged-xbrl")
    batching.rollback_batch(batch)


def test_concurrent_composed_source_read_and_delayed_open_do_not_self_deadlock(
    tmp_path: Path,
) -> None:
    """outer/private read graph 与 delayed opener 应各只在自己的短窗获取一次 guard。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: public-to-public 嵌套锁或 opener 未释放 guard 时抛出。
    """

    workspace_root = tmp_path / "workspace"
    repository_set = build_fs_repository_set(workspace_root=workspace_root)
    core = repository_set.core
    batching = FsBatchingRepository(workspace_root, repository_set=repository_set)
    source = FsSourceDocumentRepository(workspace_root, repository_set=repository_set)
    blob = FsDocumentBlobRepository(workspace_root, repository_set=repository_set)
    batch = batching.begin_batch("AAPL")
    request = _source_request("composed-read")
    handle = SourceHandle(
        ticker="AAPL",
        document_id="composed-read",
        source_kind=SourceKind.FILING.value,
    )
    file_meta = blob.store_file(
        handle,
        "composed-read.txt",
        io.BytesIO(b"stable descriptor"),
        batch=batch,
        content_type="text/plain",
    )
    source.create_source_document(
        SourceDocumentUpsertRequest(
            ticker=request.ticker,
            document_id=request.document_id,
            internal_document_id=request.internal_document_id,
            form_type=request.form_type,
            primary_document=request.primary_document,
            meta=request.meta,
            files=[file_meta],
        ),
        SourceKind.FILING,
        batch=batch,
    )
    batching.commit_batch(batch)

    with ThreadPoolExecutor(max_workers=1) as executor:
        read_future = executor.submit(_read_primary_source_bytes, source)
        assert read_future.result(timeout=5) == b"stable descriptor"

    delayed_source = source.get_primary_source("AAPL", "composed-read", SourceKind.FILING)
    stream = delayed_source.open()
    try:
        publication_token = core._acquire_lock_token(
            core._publication_lock_path("AAPL"),
            blocking=False,
        )
        core._release_lock_token(publication_token)
        assert stream.read() == b"stable descriptor"
    finally:
        stream.close()

    published_path = _local_path_from_uri(core.portfolio_root, file_meta.uri)
    published_path.unlink()
    with pytest.raises(FileNotFoundError):
        delayed_source.open()
    publication_token = core._acquire_lock_token(
        core._publication_lock_path("AAPL"),
        blocking=False,
    )
    core._release_lock_token(publication_token)


@pytest.mark.parametrize("target_kind", ("directory", "broken_symlink"))
def test_replace_directory_rejects_existing_or_broken_symlink_target(
    tmp_path: Path,
    target_kind: _ReplaceTargetKind,
) -> None:
    """directory replace target已存在时应fail closed且两端内容不变。

    Args:
        tmp_path: pytest临时目录。
        target_kind: 已存在普通目录或broken symlink。

    Returns:
        无。

    Raises:
        AssertionError: target被覆盖或source发生变化时由pytest抛出。
        OSError: fixture symlink创建失败时抛出。
    """

    core = _build_core(tmp_path)
    source = tmp_path / "source"
    target = tmp_path / "target"
    _write_state(source, "source")
    expected_link_target: str | None = None
    if target_kind == "directory":
        _write_state(target, "target")
    else:
        missing_target = tmp_path / "missing-target"
        target.symlink_to(missing_target, target_is_directory=True)
        expected_link_target = os.readlink(target)

    with pytest.raises(OSError, match="target 已存在"):
        core._replace_directory(source, target)

    assert (source / "state.txt").read_text(encoding="utf-8") == "source"
    if target_kind == "directory":
        assert (target / "state.txt").read_text(encoding="utf-8") == "target"
    else:
        assert target.is_symlink()
        assert os.readlink(target) == expected_link_target


def test_local_file_store_put_orders_file_sync_replace_and_directory_sync(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """put_object应按file fsync -> atomic replace -> directory sync顺序提交。

    Args:
        tmp_path: pytest临时目录。
        monkeypatch: pytest monkeypatch fixture。

    Returns:
        无。

    Raises:
        AssertionError: durable ordering、unique temp或内容摘要错误时由pytest抛出。
    """

    store = LocalFileStore(tmp_path / "objects")
    original_fsync = os.fsync
    original_replace = os.replace
    events: list[str] = []
    temp_paths: list[Path] = []

    def _record_fsync(file_descriptor: int) -> None:
        """记录file fsync并执行真实系统调用。

        Args:
            file_descriptor: 文件描述符。

        Returns:
            无。

        Raises:
            OSError: 真实fsync失败时抛出。
        """

        events.append("file_fsync")
        original_fsync(file_descriptor)

    def _record_replace(
        source: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        target: str | bytes | os.PathLike[str] | os.PathLike[bytes],
    ) -> None:
        """记录atomic replace并执行真实系统调用。

        Args:
            source: 临时文件路径。
            target: 正式对象路径。

        Returns:
            无。

        Raises:
            OSError: 真实replace失败时抛出。
        """

        events.append("replace")
        temp_paths.append(Path(os.fsdecode(source)))
        original_replace(source, target)

    def _record_directory_sync(path: Path) -> None:
        """记录directory sync并执行真实helper。

        Args:
            path: 被刷新的目录。

        Returns:
            无。

        Raises:
            无。
        """

        events.append("directory_sync")
        del path

    monkeypatch.setattr(local_file_store_module.os, "fsync", _record_fsync)
    monkeypatch.setattr(local_file_store_module.os, "replace", _record_replace)
    monkeypatch.setattr(local_file_store_module, "_fsync_directory", _record_directory_sync)

    first = store.put_object("AAPL/report.md", io.BytesIO(b"first"))
    second = store.put_object("AAPL/report.md", io.BytesIO(b"second"))

    assert events == [
        "file_fsync",
        "replace",
        "directory_sync",
        "file_fsync",
        "replace",
        "directory_sync",
    ]
    assert len(set(temp_paths)) == 2
    assert all(path.name.startswith(".report.md.") and path.suffix == ".tmp" for path in temp_paths)
    assert first.sha256 is not None
    assert second.sha256 is not None
    assert first.sha256 != second.sha256
    with store.get_object("AAPL/report.md") as stream:
        assert stream.read() == b"second"


@pytest.mark.parametrize("failure_point", ("fsync", "replace"))
def test_local_file_store_put_failure_preserves_old_object_and_cleans_temp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_point: str,
) -> None:
    """写入/fsync/replace失败应保留旧object并清理unique temp。

    Args:
        tmp_path: pytest临时目录。
        monkeypatch: pytest monkeypatch fixture。
        failure_point: 要注入的filesystem阶段。

    Returns:
        无。

    Raises:
        AssertionError: 旧内容或temp cleanup不符合contract时由pytest抛出。
    """

    store_root = tmp_path / "objects"
    store = LocalFileStore(store_root)
    store.put_object("AAPL/report.md", io.BytesIO(b"old"))
    injected_error = OSError(f"injected {failure_point} failure")

    if failure_point == "fsync":
        monkeypatch.setattr(
            local_file_store_module.os,
            "fsync",
            lambda file_descriptor: _raise_os_error(file_descriptor, injected_error),
        )
    else:
        monkeypatch.setattr(
            local_file_store_module.os,
            "replace",
            lambda source, target: _raise_replace_error(source, target, injected_error),
        )

    with pytest.raises(OSError) as exc_info:
        store.put_object("AAPL/report.md", io.BytesIO(b"new"))

    assert exc_info.value is injected_error
    with store.get_object("AAPL/report.md") as stream:
        assert stream.read() == b"old"
    assert list((store_root / "AAPL").glob(".report.md.*.tmp")) == []


def test_local_file_store_read_stat_list_delete_and_missing_contract(tmp_path: Path) -> None:
    """LocalFileStore其余public方法应复用同一canonical key与metadata真源。

    Args:
        tmp_path: pytest临时目录。

    Returns:
        无。

    Raises:
        AssertionError: stat/list/delete或missing语义错误时由pytest抛出。
    """

    with pytest.raises(ValueError, match="scheme"):
        LocalFileStore(tmp_path / "invalid", scheme=" ")
    store = LocalFileStore(tmp_path / "objects")
    written = store.put_object("AAPL/reports/report.md", io.BytesIO(b"payload"))

    stat = store.stat_object("AAPL/reports/report.md")
    listed = store.list_objects("AAPL/reports")

    assert stat.uri == written.uri
    assert stat.sha256 == written.sha256
    assert stat.size == len(b"payload")
    assert listed == [stat]
    assert store.list_objects("AAPL/missing") == []
    with pytest.raises(NotImplementedError):
        store.get_presigned_url("AAPL/reports/report.md", 60)
    store.delete_object("AAPL/reports/report.md")
    with pytest.raises(FileNotFoundError):
        store.get_object("AAPL/reports/report.md")
    with pytest.raises(FileNotFoundError):
        store.stat_object("AAPL/reports/report.md")
    with pytest.raises(FileNotFoundError):
        store.delete_object("AAPL/reports/report.md")


def test_local_file_store_rejects_symlink_key_escape(tmp_path: Path) -> None:
    """LocalFileStore key经symlink resolve越界时也必须fail closed。

    Args:
        tmp_path: pytest临时目录。

    Returns:
        无。

    Raises:
        AssertionError: symlink key escape未被拒绝时由pytest抛出。
        OSError: 测试环境无法创建symlink时由pytest抛出。
    """

    store_root = tmp_path / "objects"
    outside_root = tmp_path / "outside"
    store = LocalFileStore(store_root)
    outside_root.mkdir()
    (store_root / "escape").symlink_to(outside_root, target_is_directory=True)

    with pytest.raises(ValueError, match="越界"):
        store.put_object("escape/report.md", io.BytesIO(b"payload"))
    assert tuple(outside_root.iterdir()) == ()


@pytest.mark.parametrize("corruption", ("symlink", "mismatch"))
def test_complete_validator_rejects_identity_descriptor_symlink_and_mismatch(
    tmp_path: Path,
    corruption: str,
) -> None:
    """complete validator 应拒绝 source descriptor symlink 与 identity mismatch。

    Args:
        tmp_path: pytest 临时目录。
        corruption: descriptor 破坏方式。

    Returns:
        无。

    Raises:
        AssertionError: 损坏 descriptor 被发布或 capability 未消费时抛出。
    """

    workspace_root = tmp_path / corruption
    repository_set = build_fs_repository_set(workspace_root=workspace_root)
    batching = FsBatchingRepository(workspace_root, repository_set=repository_set)
    source = FsSourceDocumentRepository(workspace_root, repository_set=repository_set)
    blob = FsDocumentBlobRepository(workspace_root, repository_set=repository_set)
    ticker = "AAPL"
    document_id = "fil_文档/descriptor"
    batch = batching.begin_batch(ticker)
    handle = SourceHandle(
        ticker=ticker,
        document_id=document_id,
        source_kind=SourceKind.FILING.value,
    )
    file_meta = blob.store_file(
        handle,
        "report.htm",
        io.BytesIO(b"descriptor payload"),
        batch=batch,
    )
    source.create_source_document(
        SourceDocumentUpsertRequest(
            ticker=ticker,
            document_id=document_id,
            internal_document_id=document_id,
            form_type="10-K",
            primary_document="report.htm",
            files=[file_meta],
            meta={
                "ingest_method": "download",
                "source_provider": "sec_edgar",
                "source_fingerprint": "descriptor-fingerprint",
            },
        ),
        SourceKind.FILING,
        batch=batch,
    )
    state = _only_active_batch_state(repository_set.core)
    source_dir = repository_set.core._source_meta_path(
        ticker,
        document_id,
        SourceKind.FILING,
        state,
    ).parent
    descriptor_path = next(
        path for path in source_dir.iterdir() if path.name.startswith(".") and path.suffix == ".json"
    )
    outside_descriptor: Path | None = None
    if corruption == "symlink":
        outside_descriptor = tmp_path / "outside-descriptor.json"
        outside_descriptor.write_text(
            descriptor_path.read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        descriptor_path.unlink()
        descriptor_path.symlink_to(outside_descriptor)
    else:
        payload = json.loads(descriptor_path.read_text(encoding="utf-8"))
        assert isinstance(payload, dict)
        payload["external_identity"] = "fil_other"
        descriptor_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="identity descriptor"):
        batching.commit_batch(batch)
    with pytest.raises(ValueError, match="transaction 未在当前 storage core 登记"):
        batching.commit_batch(batch)
    assert not repository_set.core._target_ticker_dir(ticker).exists()
    if outside_descriptor is not None:
        assert json.loads(outside_descriptor.read_text(encoding="utf-8"))["external_identity"] == document_id


def test_filename_absolute_and_local_uri_attacks_remain_rejected_for_opaque_documents(
    tmp_path: Path,
) -> None:
    """opaque document identity 不得放宽 filename 与 local URI containment 边界。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: filename/URI 攻击进入 published tree 时抛出。
    """

    workspace_root = tmp_path / "opaque-security"
    repository_set = build_fs_repository_set(workspace_root=workspace_root)
    batching = FsBatchingRepository(workspace_root, repository_set=repository_set)
    source = FsSourceDocumentRepository(workspace_root, repository_set=repository_set)
    blob = FsDocumentBlobRepository(workspace_root, repository_set=repository_set)
    ticker = "AAPL"
    document_id = "fil_../文档\\层级"
    batch = batching.begin_batch(ticker)
    handle = SourceHandle(
        ticker=ticker,
        document_id=document_id,
        source_kind=SourceKind.FILING.value,
    )
    for filename in ("/tmp/escape.htm", "../escape.htm", "C:\\escape.htm"):
        with pytest.raises(ValueError):
            blob.store_file(handle, filename, io.BytesIO(b"escape"), batch=batch)
    file_meta = blob.store_file(
        handle,
        "report.htm",
        io.BytesIO(b"safe payload"),
        batch=batch,
    )
    source.create_source_document(
        SourceDocumentUpsertRequest(
            ticker=ticker,
            document_id=document_id,
            internal_document_id=document_id,
            form_type="10-K",
            primary_document="report.htm",
            files=[
                FileObjectMeta(
                    uri="local:///etc/passwd",
                    etag=file_meta.etag,
                    last_modified=file_meta.last_modified,
                    size=file_meta.size,
                    content_type=file_meta.content_type,
                    sha256=file_meta.sha256,
                )
            ],
            meta={
                "ingest_method": "download",
                "source_provider": "sec_edgar",
                "source_fingerprint": "security-fingerprint",
            },
        ),
        SourceKind.FILING,
        batch=batch,
    )

    with pytest.raises(ValueError):
        batching.commit_batch(batch)
    with pytest.raises(ValueError, match="transaction 未在当前 storage core 登记"):
        batching.commit_batch(batch)
    assert not repository_set.core._target_ticker_dir(ticker).exists()


def test_snapshot_concurrent_ab_publication_never_mixes_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """真实 A/B commit 穿过多文件复制时 snapshot 只能返回完整单版。

    Args:
        tmp_path: pytest 临时目录。
        monkeypatch: pytest monkeypatch fixture。

    Returns:
        无。

    Raises:
        AssertionError: snapshot 混合 A/B descriptor、meta、provenance、primary 或内容时抛出。
    """

    workspace_root = tmp_path / "snapshot-ab"
    repository_set = build_fs_repository_set(workspace_root=workspace_root)
    source_repository = FsSourceDocumentRepository(workspace_root, repository_set=repository_set)
    blob_repository = FsDocumentBlobRepository(workspace_root, repository_set=repository_set)
    batching = FsBatchingRepository(workspace_root, repository_set=repository_set)
    _publish_snapshot_version(
        source_repository,
        blob_repository,
        batching,
        version="A",
        replace_existing=False,
    )
    batch_b = batching.begin_batch("AAPL")
    _stage_snapshot_version(
        source_repository,
        blob_repository,
        batch=batch_b,
        version="B",
        replace_existing=True,
    )

    first_file_copied = Event()
    allow_second_file = Event()
    blocked = False
    original_copy = source_snapshot_module._copy_snapshot_file

    def _copy_then_block(
        opened_file: source_snapshot_module._OpenSnapshotFile,
        temp_root: Path,
    ) -> None:
        """复制首个真实 fd 后阻塞，让 B publication 穿过同一 attempt。

        Args:
            opened_file: production snapshot 已打开的业务文件。
            temp_root: 当前 production attempt 私有临时根。

        Returns:
            无。

        Raises:
            TimeoutError: 测试未按 barrier 释放复制时抛出。
            OSError: production copy 失败时抛出。
            ValueError: production 静态完整性校验失败时抛出。
        """

        nonlocal blocked
        original_copy(opened_file, temp_root)
        if blocked:
            return
        blocked = True
        first_file_copied.set()
        if not allow_second_file.wait(timeout=10):
            raise TimeoutError("A/B snapshot copy barrier 未释放")

    monkeypatch.setattr(source_snapshot_module, "_copy_snapshot_file", _copy_then_block)
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(
            source_repository.read_source_snapshot,
            "AAPL",
            "snapshot-doc",
            SourceKind.FILING,
            materialize_files=True,
        )
        assert first_file_copied.wait(timeout=10)
        batching.commit_batch(batch_b)
        allow_second_file.set()
        snapshot = future.result(timeout=10)
    try:
        assert snapshot.source_meta["version_marker"] == "B"
        assert snapshot.provenance.source_provider.value == "sec_edgar"
        assert snapshot.primary_filename == "b-primary.txt"
        assert tuple(item.name for item in snapshot.files) == (
            "b-primary.txt",
            "b-related.txt",
        )
        with snapshot.get_source("b-primary.txt").open() as primary_stream:
            assert primary_stream.read() == b"B-primary-content"
        with snapshot.get_source("b-related.txt").open() as related_stream:
            assert related_stream.read() == b"B-related-content"
    finally:
        snapshot.close()


def test_snapshot_transient_change_recovers_and_cleans_discarded_attempt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """一次真实 publication 变化应由 storage 内部恢复并清理废弃 attempt。

    Args:
        tmp_path: pytest 临时目录。
        monkeypatch: pytest monkeypatch fixture。

    Returns:
        无。

    Raises:
        AssertionError: transient change 未恢复或废弃临时树仍存在时抛出。
    """

    workspace_root = tmp_path / "snapshot-transient"
    repository_set = build_fs_repository_set(workspace_root=workspace_root)
    source_repository = FsSourceDocumentRepository(workspace_root, repository_set=repository_set)
    blob_repository = FsDocumentBlobRepository(workspace_root, repository_set=repository_set)
    batching = FsBatchingRepository(workspace_root, repository_set=repository_set)
    _publish_snapshot_version(
        source_repository,
        blob_repository,
        batching,
        version="A",
        replace_existing=False,
    )
    revision_a = _read_snapshot_revision(
        source_repository,
        "AAPL",
        "snapshot-doc",
        SourceKind.FILING,
    )
    batch_b = batching.begin_batch("AAPL")
    _stage_snapshot_version(
        source_repository,
        blob_repository,
        batch=batch_b,
        version="B",
        replace_existing=True,
    )

    copy_entered = Event()
    allow_copy = Event()
    observed_roots: set[Path] = set()
    blocked = False
    original_copy = source_snapshot_module._copy_snapshot_file

    def _block_first_attempt_copy(
        opened_file: source_snapshot_module._OpenSnapshotFile,
        temp_root: Path,
    ) -> None:
        """在首个 production copy seam 协调一次真实 B commit。

        Args:
            opened_file: production snapshot 已打开的业务文件。
            temp_root: 当前 production attempt 私有临时根。

        Returns:
            无。

        Raises:
            TimeoutError: 测试未释放 barrier 时抛出。
            OSError: production copy 失败时抛出。
            ValueError: production 静态完整性校验失败时抛出。
        """

        nonlocal blocked
        observed_roots.add(temp_root)
        if not blocked:
            blocked = True
            copy_entered.set()
            if not allow_copy.wait(timeout=10):
                raise TimeoutError("transient snapshot copy barrier 未释放")
        original_copy(opened_file, temp_root)

    monkeypatch.setattr(
        source_snapshot_module,
        "_copy_snapshot_file",
        _block_first_attempt_copy,
    )
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(
            source_repository.read_source_snapshot,
            "AAPL",
            "snapshot-doc",
            SourceKind.FILING,
            materialize_files=True,
        )
        assert copy_entered.wait(timeout=10)
        batching.commit_batch(batch_b)
        allow_copy.set()
        snapshot = future.result(timeout=10)
    snapshot_root = snapshot.get_primary_source().materialize().parent
    discarded_roots = {root for root in observed_roots if root != snapshot_root}
    try:
        assert snapshot.revision != revision_a
        assert snapshot.source_meta["version_marker"] == "B"
        assert discarded_roots
        assert all(not root.exists() for root in discarded_roots)
    finally:
        snapshot.close()
    assert not snapshot_root.exists()


def test_snapshot_sustained_change_raises_typed_consistency_failure_and_cleans_resources(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """每个 attempt 都遇到真实 commit 时应 typed fail 且不遗留临时资源。

    Args:
        tmp_path: pytest 临时目录。
        monkeypatch: pytest monkeypatch fixture。

    Returns:
        无。

    Raises:
        AssertionError: sustained churn 未 typed fail 或资源未清理时抛出。
    """

    workspace_root = tmp_path / "snapshot-sustained"
    repository_set = build_fs_repository_set(workspace_root=workspace_root)
    source_repository = FsSourceDocumentRepository(workspace_root, repository_set=repository_set)
    blob_repository = FsDocumentBlobRepository(workspace_root, repository_set=repository_set)
    batching = FsBatchingRepository(workspace_root, repository_set=repository_set)
    _publish_snapshot_version(
        source_repository,
        blob_repository,
        batching,
        version="A",
        replace_existing=False,
    )

    copy_barriers: Queue[tuple[Path, Event]] = Queue()
    observed_roots: set[Path] = set()
    original_copy = source_snapshot_module._copy_snapshot_file

    def _block_each_attempt_copy(
        opened_file: source_snapshot_module._OpenSnapshotFile,
        temp_root: Path,
    ) -> None:
        """每个新 attempt 首次进入 copy 时请求一次真实 publication。

        Args:
            opened_file: production snapshot 已打开的业务文件。
            temp_root: 当前 production attempt 私有临时根。

        Returns:
            无。

        Raises:
            TimeoutError: 测试未释放当前 attempt barrier 时抛出。
            OSError: production copy 失败时抛出。
            ValueError: production 静态完整性校验失败时抛出。
        """

        if temp_root not in observed_roots:
            observed_roots.add(temp_root)
            release = Event()
            copy_barriers.put((temp_root, release))
            if not release.wait(timeout=10):
                raise TimeoutError("sustained snapshot copy barrier 未释放")
        original_copy(opened_file, temp_root)

    monkeypatch.setattr(
        source_snapshot_module,
        "_copy_snapshot_file",
        _block_each_attempt_copy,
    )
    next_version: _SnapshotVersion = "B"
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(
            source_repository.read_source_snapshot,
            "AAPL",
            "snapshot-doc",
            SourceKind.FILING,
            materialize_files=True,
        )
        while not future.done():
            try:
                _temp_root, release = copy_barriers.get(timeout=10)
            except Empty:
                assert future.done()
                break
            try:
                _publish_snapshot_version(
                    source_repository,
                    blob_repository,
                    batching,
                    version=next_version,
                    replace_existing=True,
                )
                next_version = "A" if next_version == "B" else "B"
            finally:
                release.set()
        with pytest.raises(SourceSnapshotConsistencyError) as exc_info:
            future.result(timeout=10)
    assert observed_roots
    assert all(not root.exists() for root in observed_roots)
    _assert_exception_graph_path_free(
        exc_info.value,
        forbidden_locators=(str(workspace_root),),
    )


@pytest.mark.parametrize("corruption", ("symlink", "meta_size"))
def test_snapshot_rejects_symlink_containment_and_file_meta_mismatch(
    tmp_path: Path,
    corruption: str,
) -> None:
    """静态 symlink 与 meta/physical mismatch 必须 fail closed 而非 source changed。

    Args:
        tmp_path: pytest 临时目录。
        corruption: 当前注入的真实 filesystem corruption 类型。

    Returns:
        无。

    Raises:
        AssertionError: corruption 未被 owner 拒绝或被误分类为 consistency failure 时抛出。
    """

    workspace_root = tmp_path / f"snapshot-corruption-{corruption}"
    repository_set = build_fs_repository_set(workspace_root=workspace_root)
    source_repository = FsSourceDocumentRepository(workspace_root, repository_set=repository_set)
    blob_repository = FsDocumentBlobRepository(workspace_root, repository_set=repository_set)
    batching = FsBatchingRepository(workspace_root, repository_set=repository_set)
    _publish_snapshot_version(
        source_repository,
        blob_repository,
        batching,
        version="A",
        replace_existing=False,
    )
    core = repository_set.core
    meta_path = core._source_meta_path_for_read(
        "AAPL",
        "snapshot-doc",
        SourceKind.FILING,
    )
    outside_file: Path | None = None
    if corruption == "symlink":
        outside_file = tmp_path / "outside-sentinel.txt"
        outside_file.write_bytes(b"outside-safe")
        business_file = meta_path.parent / "a-primary.txt"
        business_file.unlink()
        business_file.symlink_to(outside_file)
    else:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        raw_files = meta["files"]
        assert isinstance(raw_files, list)
        first_file = raw_files[0]
        assert isinstance(first_file, dict)
        raw_size = first_file["size"]
        assert isinstance(raw_size, int)
        first_file["size"] = raw_size + 1
        meta_path.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError):
        source_repository.read_source_snapshot(
            "AAPL",
            "snapshot-doc",
            SourceKind.FILING,
            materialize_files=True,
        )
    if corruption == "symlink":
        assert outside_file is not None
        assert outside_file.read_bytes() == b"outside-safe"


def test_snapshot_fd_copy_silent_mutation_is_corruption_without_revision_change(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """已打开 inode 的静默原地变更应是 corruption，不得伪装 publication change。

    Args:
        tmp_path: pytest 临时目录。
        monkeypatch: pytest monkeypatch fixture。

    Returns:
        无。

    Raises:
        AssertionError: 静态 inode mutation 被重试或映射为 consistency failure 时抛出。
    """

    workspace_root = tmp_path / "snapshot-silent-mutation"
    repository_set = build_fs_repository_set(workspace_root=workspace_root)
    source_repository = FsSourceDocumentRepository(workspace_root, repository_set=repository_set)
    blob_repository = FsDocumentBlobRepository(workspace_root, repository_set=repository_set)
    batching = FsBatchingRepository(workspace_root, repository_set=repository_set)
    _publish_snapshot_version(
        source_repository,
        blob_repository,
        batching,
        version="A",
        replace_existing=False,
    )
    revision = _read_snapshot_revision(
        source_repository,
        "AAPL",
        "snapshot-doc",
        SourceKind.FILING,
    )
    business_file = (
        repository_set.core._source_meta_path_for_read(
            "AAPL",
            "snapshot-doc",
            SourceKind.FILING,
        ).parent
        / "a-primary.txt"
    )
    copy_entered = Event()
    allow_copy = Event()
    observed_roots: set[Path] = set()
    blocked = False
    original_copy = source_snapshot_module._copy_snapshot_file

    def _block_before_silent_mutation_copy(
        opened_file: source_snapshot_module._OpenSnapshotFile,
        temp_root: Path,
    ) -> None:
        """在 production 已 fstat/open 后协调同 inode 原地变更。

        Args:
            opened_file: production snapshot 已打开的业务文件。
            temp_root: 当前 production attempt 私有临时根。

        Returns:
            无。

        Raises:
            TimeoutError: 测试未释放 barrier 时抛出。
            OSError: production copy 失败时抛出。
            ValueError: production 静态完整性校验失败时抛出。
        """

        nonlocal blocked
        observed_roots.add(temp_root)
        if not blocked:
            blocked = True
            copy_entered.set()
            if not allow_copy.wait(timeout=10):
                raise TimeoutError("silent mutation snapshot copy barrier 未释放")
        original_copy(opened_file, temp_root)

    monkeypatch.setattr(
        source_snapshot_module,
        "_copy_snapshot_file",
        _block_before_silent_mutation_copy,
    )
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(
            source_repository.read_source_snapshot,
            "AAPL",
            "snapshot-doc",
            SourceKind.FILING,
            materialize_files=True,
        )
        assert copy_entered.wait(timeout=10)
        business_file.write_bytes(b"X" * len(b"A-primary-content"))
        allow_copy.set()
        with pytest.raises(ValueError) as exc_info:
            future.result(timeout=10)
    assert not isinstance(exc_info.value, SourceSnapshotConsistencyError)
    assert (
        _read_snapshot_revision(
            source_repository,
            "AAPL",
            "snapshot-doc",
            SourceKind.FILING,
        )
        == revision
    )
    assert observed_roots
    assert all(not root.exists() for root in observed_roots)


def test_snapshot_acquire_primary_survives_guard_release_secondary_without_locator(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """acquire 主失败不得被 publication guard release 次失败覆盖或污染。

    Args:
        tmp_path: pytest 临时目录。
        monkeypatch: pytest monkeypatch fixture。

    Returns:
        无。

    Raises:
        AssertionError: 主因、safe note 或 exception graph path-free 合同回退时抛出。
    """

    workspace_root = tmp_path / "snapshot-acquire-release-double-failure"
    repository_set = build_fs_repository_set(workspace_root=workspace_root)
    source_repository = FsSourceDocumentRepository(workspace_root, repository_set=repository_set)
    primary_error = ValueError("snapshot acquire authoritative failure")
    original_release = RuntimeFileLockToken.release
    release_paths: list[Path] = []

    def _fail_acquire(
        core: FsStorageCore,
        ticker: str,
        document_id: str,
        source_kind: SourceKind | None,
    ) -> source_snapshot_module._AcquiredSnapshotAttempt:
        """在 guard 内注入确定的 acquire authoritative failure。"""

        del core, ticker, document_id, source_kind
        raise primary_error

    def _release_then_fail(token: RuntimeFileLockToken) -> None:
        """真实释放 guard 后从携 locator 的 runtime cause 注入失败。"""

        original_release(token)
        release_paths.append(token.lock_path)
        raw_error = PermissionError(
            errno.EACCES,
            "snapshot release private message",
            str(token.lock_path),
        )
        try:
            raise raw_error
        except PermissionError as exc:
            raise RuntimeFileLockError("snapshot release wrapper failed") from exc

    monkeypatch.setattr(
        source_snapshot_module,
        "_acquire_snapshot_attempt_unguarded",
        _fail_acquire,
    )
    monkeypatch.setattr(RuntimeFileLockToken, "release", _release_then_fail)

    with pytest.raises(ValueError) as exc_info:
        source_repository.read_source_snapshot(
            "AAPL",
            "snapshot-doc",
            SourceKind.FILING,
            materialize_files=False,
        )

    assert exc_info.value is primary_error
    assert release_paths
    assert (
        "source snapshot publication guard release failed: error_type=RuntimeFileLockError"
    ) in exc_info.value.__notes__
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None
    _assert_exception_graph_path_free(
        exc_info.value,
        forbidden_locators=(
            str(workspace_root),
            release_paths[0].name,
            "snapshot release private message",
        ),
    )


def test_snapshot_guard_release_primary_survives_fd_close_secondary_without_locator(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """acquire 成功后 release 应为主，FD close 失败只能追加安全诊断。

    Args:
        tmp_path: pytest 临时目录。
        monkeypatch: pytest monkeypatch fixture。

    Returns:
        无。

    Raises:
        AssertionError: release 主因、FD cleanup 或 exception graph 合同回退时抛出。
    """

    workspace_root = tmp_path / "snapshot-release-close-double-failure"
    repository_set = build_fs_repository_set(workspace_root=workspace_root)
    source_repository = FsSourceDocumentRepository(workspace_root, repository_set=repository_set)
    blob_repository = FsDocumentBlobRepository(workspace_root, repository_set=repository_set)
    batching = FsBatchingRepository(workspace_root, repository_set=repository_set)
    _publish_snapshot_version(
        source_repository,
        blob_repository,
        batching,
        version="A",
        replace_existing=False,
    )
    published_path = (
        repository_set.core._source_meta_path_for_read(
            "AAPL",
            "snapshot-doc",
            SourceKind.FILING,
        ).parent
        / "a-primary.txt"
    )
    original_release = RuntimeFileLockToken.release
    original_close = source_snapshot_module._close_open_snapshot_files
    release_paths: list[Path] = []
    closed_descriptor_counts: list[int] = []

    def _release_then_fail(token: RuntimeFileLockToken) -> None:
        """真实释放 guard 后从携 locator 的 runtime cause 注入主失败。"""

        original_release(token)
        release_paths.append(token.lock_path)
        raw_error = PermissionError(
            errno.EACCES,
            "snapshot release primary private message",
            str(token.lock_path),
        )
        try:
            raise raw_error
        except PermissionError as exc:
            raise RuntimeFileLockError("snapshot release wrapper failed") from exc

    def _close_then_fail(
        open_files: list[source_snapshot_module._OpenSnapshotFile],
    ) -> None:
        """关闭全部真实 FD 后注入携 published locator 的次级失败。"""

        closed_descriptor_counts.append(len(open_files))
        original_close(open_files)
        raise PermissionError(
            errno.EIO,
            "snapshot fd close private message",
            str(published_path),
        )

    monkeypatch.setattr(RuntimeFileLockToken, "release", _release_then_fail)
    monkeypatch.setattr(
        source_snapshot_module,
        "_close_open_snapshot_files",
        _close_then_fail,
    )

    with pytest.raises(RuntimeFileLockError) as exc_info:
        source_repository.read_source_snapshot(
            "AAPL",
            "snapshot-doc",
            SourceKind.FILING,
            materialize_files=False,
        )

    assert release_paths
    assert closed_descriptor_counts == [2]
    assert (
        f"source snapshot published descriptor cleanup failed: error_type=PermissionError errno={errno.EIO}"
    ) in exc_info.value.__notes__
    assert isinstance(exc_info.value.__cause__, PermissionError)
    assert exc_info.value.__cause__.errno == errno.EACCES
    assert exc_info.value.__context__ is None
    _assert_exception_graph_path_free(
        exc_info.value,
        forbidden_locators=(
            str(workspace_root),
            published_path.name,
            release_paths[0].name,
            "snapshot release primary private message",
            "snapshot fd close private message",
        ),
    )


def test_snapshot_marker_read_primary_survives_guard_release_secondary_without_locator(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """marker read 主失败不得被其 publication guard release 次失败覆盖。

    Args:
        tmp_path: pytest 临时目录。
        monkeypatch: pytest monkeypatch fixture。

    Returns:
        无。

    Raises:
        AssertionError: marker 主因、safe note 或 path-free graph 合同回退时抛出。
    """

    workspace_root = tmp_path / "snapshot-marker-release-double-failure"
    repository_set = build_fs_repository_set(workspace_root=workspace_root)
    source_repository = FsSourceDocumentRepository(
        workspace_root,
        repository_set=repository_set,
    )
    blob_repository = FsDocumentBlobRepository(
        workspace_root,
        repository_set=repository_set,
    )
    batching = FsBatchingRepository(workspace_root, repository_set=repository_set)
    _publish_snapshot_version(
        source_repository,
        blob_repository,
        batching,
        version="A",
        replace_existing=False,
    )
    primary_error = ValueError("snapshot marker descriptor authoritative failure")
    original_build_marker = source_snapshot_module._build_published_marker
    original_release = RuntimeFileLockToken.release
    build_calls = 0
    release_calls = 0
    release_paths: list[Path] = []

    def _fail_post_marker_build(
        core: FsStorageCore,
        ticker: str,
        document_id: str,
        source_kind: SourceKind,
        revision: SourceDocumentRevision,
        is_deleted: bool,
    ) -> source_snapshot_module._PublishedSnapshotMarker:
        """只在 post-copy marker build 阶段注入 authoritative failure。"""

        nonlocal build_calls
        build_calls += 1
        if build_calls == 2:
            raise primary_error
        return original_build_marker(
            core,
            ticker,
            document_id,
            source_kind,
            revision,
            is_deleted,
        )

    def _release_post_marker_then_fail(token: RuntimeFileLockToken) -> None:
        """真实释放第二个 guard 后注入携带 lock locator 的次级失败。"""

        nonlocal release_calls
        release_calls += 1
        original_release(token)
        if release_calls != 2:
            return
        release_paths.append(token.lock_path)
        raw_error = PermissionError(
            errno.EACCES,
            "snapshot marker release private message",
            str(token.lock_path),
        )
        try:
            raise raw_error
        except PermissionError as exc:
            raise RuntimeFileLockError("snapshot marker release wrapper failed") from exc

    monkeypatch.setattr(
        source_snapshot_module,
        "_build_published_marker",
        _fail_post_marker_build,
    )
    monkeypatch.setattr(
        RuntimeFileLockToken,
        "release",
        _release_post_marker_then_fail,
    )

    with pytest.raises(ValueError) as exc_info:
        source_repository.read_source_snapshot(
            "AAPL",
            "snapshot-doc",
            SourceKind.FILING,
            materialize_files=True,
        )

    assert exc_info.value is primary_error
    assert build_calls == 2
    assert release_calls == 2
    assert release_paths
    assert (
        "source snapshot marker publication guard release failed: error_type=RuntimeFileLockError"
    ) in exc_info.value.__notes__
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None
    _assert_exception_graph_path_free(
        exc_info.value,
        forbidden_locators=(
            str(workspace_root),
            release_paths[0].name,
            "snapshot marker release private message",
        ),
    )


def test_snapshot_close_failure_retains_cleanup_root_for_concurrent_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """close 删除失败后保持不可读并允许并发重试完成同一临时树清理。

    Args:
        tmp_path: pytest 临时目录。
        monkeypatch: pytest monkeypatch fixture。

    Returns:
        无。

    Raises:
        AssertionError: locator 丢失、关闭后可读、重试或幂等合同回退时抛出。
    """

    workspace_root = tmp_path / "snapshot-close-retry"
    repository_set = build_fs_repository_set(workspace_root=workspace_root)
    source_repository = FsSourceDocumentRepository(
        workspace_root,
        repository_set=repository_set,
    )
    blob_repository = FsDocumentBlobRepository(
        workspace_root,
        repository_set=repository_set,
    )
    batching = FsBatchingRepository(workspace_root, repository_set=repository_set)
    _publish_snapshot_version(
        source_repository,
        blob_repository,
        batching,
        version="A",
        replace_existing=False,
    )
    snapshot = source_repository.read_source_snapshot(
        "AAPL",
        "snapshot-doc",
        SourceKind.FILING,
        materialize_files=True,
    )
    primary_source = snapshot.get_primary_source()
    temp_root = primary_source.materialize().parent
    original_rmtree = source_snapshot_module.shutil.rmtree
    remove_calls: list[Path] = []

    def _fail_first_remove(path: Path) -> None:
        """第一次保留真实临时树并抛 pathful failure，后续真实删除。"""

        remove_calls.append(path)
        if len(remove_calls) == 1:
            raise PermissionError(
                errno.EACCES,
                "snapshot close private message",
                str(path),
            )
        original_rmtree(path)

    monkeypatch.setattr(
        source_snapshot_module.shutil,
        "rmtree",
        _fail_first_remove,
    )

    with pytest.raises(PermissionError) as exc_info:
        snapshot.close()

    assert temp_root.exists()
    assert remove_calls == [temp_root]
    with pytest.raises(RuntimeError, match="已关闭"):
        primary_source.open()
    with pytest.raises(RuntimeError, match="已关闭"):
        snapshot.get_primary_source()
    assert exc_info.value.errno == errno.EACCES
    assert exc_info.value.__context__ is None
    _assert_exception_graph_path_free(
        exc_info.value,
        forbidden_locators=(
            str(temp_root),
            temp_root.name,
            "snapshot close private message",
        ),
    )

    with ThreadPoolExecutor(max_workers=2) as executor:
        retry_futures = tuple(executor.submit(snapshot.close) for _ in range(2))
        for future in retry_futures:
            future.result(timeout=10)

    assert remove_calls == [temp_root, temp_root]
    assert not temp_root.exists()
    snapshot.close()
    assert remove_calls == [temp_root, temp_root]


def test_snapshot_context_preserves_active_primary_when_close_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """context exit 双失败时保留活动主异常且只追加 path-free close note。

    Args:
        tmp_path: pytest 临时目录。
        monkeypatch: pytest monkeypatch fixture。

    Returns:
        无。

    Raises:
        AssertionError: 主异常 identity、secondary note、异常图或重试合同漂移时抛出。
    """

    workspace_root = tmp_path / "snapshot-context-active-primary"
    repository_set = build_fs_repository_set(workspace_root=workspace_root)
    source_repository = FsSourceDocumentRepository(
        workspace_root,
        repository_set=repository_set,
    )
    blob_repository = FsDocumentBlobRepository(
        workspace_root,
        repository_set=repository_set,
    )
    batching = FsBatchingRepository(workspace_root, repository_set=repository_set)
    _publish_snapshot_version(
        source_repository,
        blob_repository,
        batching,
        version="A",
        replace_existing=False,
    )
    snapshot = source_repository.read_source_snapshot(
        "AAPL",
        "snapshot-doc",
        SourceKind.FILING,
        materialize_files=True,
    )
    temp_root = snapshot.get_primary_source().materialize().parent
    primary_error = ValueError("snapshot consumer business primary")
    raw_close_error = PermissionError(
        errno.EACCES,
        "snapshot context close private message",
        str(temp_root),
    )
    original_rmtree = source_snapshot_module.shutil.rmtree

    def _fail_remove(path: Path) -> None:
        """为 context exit 注入携 locator 的临时树删除失败。

        Args:
            path: snapshot 私有临时树。

        Returns:
            永不正常返回。

        Raises:
            PermissionError: 始终抛出注入的 raw close failure。
        """

        assert path == temp_root
        raise raw_close_error

    monkeypatch.setattr(source_snapshot_module.shutil, "rmtree", _fail_remove)

    with pytest.raises(ValueError) as exc_info:
        with snapshot:
            raise primary_error

    assert exc_info.value is primary_error
    assert _exception_graph_nodes(exc_info.value) == (primary_error,)
    assert exc_info.value.__notes__ == [
        f"source snapshot lifecycle close failed: error_type=PermissionError errno={errno.EACCES}"
    ]
    assert temp_root.exists()
    _assert_exception_graph_path_free(
        exc_info.value,
        forbidden_locators=(
            str(workspace_root),
            temp_root.name,
            "snapshot context close private message",
        ),
    )

    monkeypatch.setattr(source_snapshot_module.shutil, "rmtree", original_rmtree)
    snapshot.close()
    assert not temp_root.exists()


def test_snapshot_context_propagates_close_failure_without_active_primary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """context 正常退出时 close failure 必须作为 path-free 主异常传播。

    Args:
        tmp_path: pytest 临时目录。
        monkeypatch: pytest monkeypatch fixture。

    Returns:
        无。

    Raises:
        AssertionError: close 主异常被吞、异常图泄漏或失败后不可重试时抛出。
    """

    workspace_root = tmp_path / "snapshot-context-close-primary"
    repository_set = build_fs_repository_set(workspace_root=workspace_root)
    source_repository = FsSourceDocumentRepository(
        workspace_root,
        repository_set=repository_set,
    )
    blob_repository = FsDocumentBlobRepository(
        workspace_root,
        repository_set=repository_set,
    )
    batching = FsBatchingRepository(workspace_root, repository_set=repository_set)
    _publish_snapshot_version(
        source_repository,
        blob_repository,
        batching,
        version="A",
        replace_existing=False,
    )
    snapshot = source_repository.read_source_snapshot(
        "AAPL",
        "snapshot-doc",
        SourceKind.FILING,
        materialize_files=True,
    )
    temp_root = snapshot.get_primary_source().materialize().parent
    raw_close_error = PermissionError(
        errno.EACCES,
        "snapshot context primary close private message",
        str(temp_root),
    )
    original_rmtree = source_snapshot_module.shutil.rmtree

    def _fail_remove(path: Path) -> None:
        """为无活动主异常的 context exit 注入 raw close failure。

        Args:
            path: snapshot 私有临时树。

        Returns:
            永不正常返回。

        Raises:
            PermissionError: 始终抛出注入的 raw close failure。
        """

        assert path == temp_root
        raise raw_close_error

    monkeypatch.setattr(source_snapshot_module.shutil, "rmtree", _fail_remove)

    with pytest.raises(PermissionError) as exc_info:
        with snapshot:
            assert snapshot.get_primary_source().materialize().exists()

    assert exc_info.value is not raw_close_error
    assert exc_info.value.errno == errno.EACCES
    assert exc_info.value.__context__ is None
    assert temp_root.exists()
    _assert_exception_graph_path_free(
        exc_info.value,
        forbidden_locators=(
            str(workspace_root),
            temp_root.name,
            "snapshot context primary close private message",
        ),
    )

    monkeypatch.setattr(source_snapshot_module.shutil, "rmtree", original_rmtree)
    snapshot.close()
    assert not temp_root.exists()


def test_snapshot_initial_fstat_primary_survives_stream_close_secondary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """initial fstat 主失败不得被尚未登记 stream 的 close 次失败覆盖。

    Args:
        tmp_path: pytest 临时目录。
        monkeypatch: pytest monkeypatch fixture。

    Returns:
        无。

    Raises:
        AssertionError: fstat 主因、safe note、close 调用或 path-free graph 回退时抛出。
    """

    workspace_root = tmp_path / "snapshot-initial-fstat-close-double-failure"
    repository_set = build_fs_repository_set(workspace_root=workspace_root)
    source_repository = FsSourceDocumentRepository(
        workspace_root,
        repository_set=repository_set,
    )
    blob_repository = FsDocumentBlobRepository(
        workspace_root,
        repository_set=repository_set,
    )
    batching = FsBatchingRepository(workspace_root, repository_set=repository_set)
    _publish_snapshot_version(
        source_repository,
        blob_repository,
        batching,
        version="A",
        replace_existing=False,
    )
    published_path = (
        repository_set.core._source_meta_path_for_read(
            "AAPL",
            "snapshot-doc",
            SourceKind.FILING,
        ).parent
        / "a-primary.txt"
    )
    raw_fstat_error = OSError(
        errno.EIO,
        "snapshot initial fstat private message",
        str(published_path),
    )
    raw_close_error = PermissionError(
        errno.EACCES,
        "snapshot initial close private message",
        str(published_path),
    )
    failing_stream = _FailingCloseBytesIO(raw_close_error)
    original_fstat = source_snapshot_module.os.fstat

    def _open_failing_stream(path: Path, *, action: str) -> BinaryIO:
        """返回 initial-fstat 前尚未加入统一 cleanup list 的测试流。"""

        del path, action
        return failing_stream

    def _fail_initial_fstat(file_descriptor: int) -> os.stat_result:
        """对测试流的首次 initial fstat 注入携 locator 的 authoritative failure。"""

        if file_descriptor == -1:
            raise raw_fstat_error
        return original_fstat(file_descriptor)

    monkeypatch.setattr(
        source_snapshot_module,
        "_open_binary_file",
        _open_failing_stream,
    )
    monkeypatch.setattr(source_snapshot_module.os, "fstat", _fail_initial_fstat)

    with pytest.raises(OSError) as exc_info:
        source_repository.read_source_snapshot(
            "AAPL",
            "snapshot-doc",
            SourceKind.FILING,
            materialize_files=False,
        )

    assert exc_info.value is not raw_fstat_error
    assert exc_info.value.errno == errno.EIO
    assert failing_stream.close_calls == 1
    assert (
        f"source snapshot initial descriptor cleanup failed: error_type=PermissionError errno={errno.EACCES}"
    ) in exc_info.value.__notes__
    assert exc_info.value.__context__ is None
    _assert_exception_graph_path_free(
        exc_info.value,
        forbidden_locators=(
            str(workspace_root),
            published_path.name,
            "snapshot initial fstat private message",
            "snapshot initial close private message",
        ),
    )
    failing_stream.close()


def test_snapshot_marker_primary_survives_fd_and_temp_cleanup_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """post-marker 主失败时 FD 与 temp cleanup 都执行且只追加安全诊断。

    Args:
        tmp_path: pytest 临时目录。
        monkeypatch: pytest monkeypatch fixture。

    Returns:
        无。

    Raises:
        AssertionError: 主因被覆盖、cleanup 被跳过或 exception graph 泄漏时抛出。
    """

    workspace_root = tmp_path / "snapshot-marker-cleanup-double-failure"
    repository_set = build_fs_repository_set(workspace_root=workspace_root)
    source_repository = FsSourceDocumentRepository(workspace_root, repository_set=repository_set)
    blob_repository = FsDocumentBlobRepository(workspace_root, repository_set=repository_set)
    batching = FsBatchingRepository(workspace_root, repository_set=repository_set)
    _publish_snapshot_version(
        source_repository,
        blob_repository,
        batching,
        version="A",
        replace_existing=False,
    )
    published_path = (
        repository_set.core._source_meta_path_for_read(
            "AAPL",
            "snapshot-doc",
            SourceKind.FILING,
        ).parent
        / "a-primary.txt"
    )
    primary_error = ValueError("snapshot marker authoritative failure")
    original_create = source_snapshot_module._create_snapshot_temp_root
    original_close = source_snapshot_module._close_open_snapshot_files
    original_remove = source_snapshot_module._remove_snapshot_temp_root
    observed_roots: list[Path] = []
    close_calls = 0
    remove_calls = 0

    def _observe_create() -> Path:
        """记录 production 创建的真实 attempt 临时树。"""

        temp_root = original_create()
        observed_roots.append(temp_root)
        return temp_root

    def _fail_marker(
        core: FsStorageCore,
        ticker: str,
        document_id: str,
        source_kind: SourceKind,
    ) -> source_snapshot_module._PublishedSnapshotMarker | None:
        """在真实 copy 后注入确定的 post-marker 主失败。"""

        del core, ticker, document_id, source_kind
        raise primary_error

    def _close_then_fail(
        open_files: list[source_snapshot_module._OpenSnapshotFile],
    ) -> None:
        """关闭全部真实 FD 后注入 pathful 次级失败。"""

        nonlocal close_calls
        close_calls += 1
        original_close(open_files)
        raise PermissionError(
            errno.EIO,
            "snapshot marker close private message",
            str(published_path),
        )

    def _remove_then_fail(temp_root: Path) -> None:
        """删除真实 attempt tree 后注入 pathful 次级失败。"""

        nonlocal remove_calls
        remove_calls += 1
        original_remove(temp_root)
        raise OSError(
            errno.ENOSPC,
            "snapshot marker remove private message",
            str(temp_root),
        )

    monkeypatch.setattr(source_snapshot_module, "_create_snapshot_temp_root", _observe_create)
    monkeypatch.setattr(source_snapshot_module, "_read_published_marker", _fail_marker)
    monkeypatch.setattr(source_snapshot_module, "_close_open_snapshot_files", _close_then_fail)
    monkeypatch.setattr(source_snapshot_module, "_remove_snapshot_temp_root", _remove_then_fail)

    with pytest.raises(ValueError) as exc_info:
        source_repository.read_source_snapshot(
            "AAPL",
            "snapshot-doc",
            SourceKind.FILING,
            materialize_files=True,
        )

    assert exc_info.value is primary_error
    assert close_calls == 1
    assert remove_calls == 1
    assert observed_roots and all(not root.exists() for root in observed_roots)
    assert (
        f"source snapshot published descriptor cleanup failed: error_type=PermissionError errno={errno.EIO}"
    ) in exc_info.value.__notes__
    assert (
        f"source snapshot temporary tree cleanup failed: error_type=OSError errno={errno.ENOSPC}"
    ) in exc_info.value.__notes__
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None
    _assert_exception_graph_path_free(
        exc_info.value,
        forbidden_locators=(
            str(workspace_root),
            published_path.name,
            observed_roots[0].name,
            "snapshot marker close private message",
            "snapshot marker remove private message",
        ),
    )


def test_snapshot_transient_discard_cleanup_preserves_first_failure_and_attempts_all(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """transient discard 无既有主因时首个 cleanup 失败为主且后续仍执行。

    Args:
        tmp_path: pytest 临时目录。
        monkeypatch: pytest monkeypatch fixture。

    Returns:
        无。

    Raises:
        AssertionError: 首个 cleanup 主因、后续安全 note 或资源清理回退时抛出。
    """

    workspace_root = tmp_path / "snapshot-transient-cleanup-double-failure"
    repository_set = build_fs_repository_set(workspace_root=workspace_root)
    source_repository = FsSourceDocumentRepository(workspace_root, repository_set=repository_set)
    blob_repository = FsDocumentBlobRepository(workspace_root, repository_set=repository_set)
    batching = FsBatchingRepository(workspace_root, repository_set=repository_set)
    _publish_snapshot_version(
        source_repository,
        blob_repository,
        batching,
        version="A",
        replace_existing=False,
    )
    published_path = (
        repository_set.core._source_meta_path_for_read(
            "AAPL",
            "snapshot-doc",
            SourceKind.FILING,
        ).parent
        / "a-primary.txt"
    )
    original_create = source_snapshot_module._create_snapshot_temp_root
    original_close = source_snapshot_module._close_open_snapshot_files
    original_remove = source_snapshot_module._remove_snapshot_temp_root
    observed_roots: list[Path] = []
    remove_calls = 0
    raw_close_error = PermissionError(
        errno.EIO,
        "snapshot transient close private message",
        str(published_path),
    )
    projected_close_error = storage_utils_module._project_filesystem_error(
        raw_close_error,
        action="关闭 source snapshot published 文件描述符",
    )

    def _observe_create() -> Path:
        """记录 production 创建的真实 attempt 临时树。"""

        temp_root = original_create()
        observed_roots.append(temp_root)
        return temp_root

    def _report_publication_change(
        core: FsStorageCore,
        ticker: str,
        document_id: str,
        source_kind: SourceKind,
    ) -> source_snapshot_module._PublishedSnapshotMarker | None:
        """让当前真实 attempt 进入 transient discard cleanup。"""

        del core, ticker, document_id, source_kind
        return None

    def _close_then_fail(
        open_files: list[source_snapshot_module._OpenSnapshotFile],
    ) -> None:
        """关闭全部真实 FD 后抛出已由 storage owner 投影的首个失败。"""

        original_close(open_files)
        storage_utils_module._raise_path_free_error(projected_close_error)

    def _remove_then_fail(temp_root: Path) -> None:
        """删除真实 attempt tree 后注入 pathful 后续 cleanup 失败。"""

        nonlocal remove_calls
        remove_calls += 1
        original_remove(temp_root)
        raise OSError(
            errno.ENOSPC,
            "snapshot transient remove private message",
            str(temp_root),
        )

    monkeypatch.setattr(source_snapshot_module, "_create_snapshot_temp_root", _observe_create)
    monkeypatch.setattr(source_snapshot_module, "_read_published_marker", _report_publication_change)
    monkeypatch.setattr(source_snapshot_module, "_close_open_snapshot_files", _close_then_fail)
    monkeypatch.setattr(source_snapshot_module, "_remove_snapshot_temp_root", _remove_then_fail)

    with pytest.raises(PermissionError) as exc_info:
        source_repository.read_source_snapshot(
            "AAPL",
            "snapshot-doc",
            SourceKind.FILING,
            materialize_files=True,
        )

    assert exc_info.value is projected_close_error
    assert remove_calls == 1
    assert observed_roots and all(not root.exists() for root in observed_roots)
    assert (
        f"source snapshot temporary tree cleanup failed: error_type=OSError errno={errno.ENOSPC}"
    ) in exc_info.value.__notes__
    assert isinstance(exc_info.value.__cause__, PermissionError)
    assert exc_info.value.__cause__.errno == errno.EIO
    assert exc_info.value.__context__ is None
    _assert_exception_graph_path_free(
        exc_info.value,
        forbidden_locators=(
            str(workspace_root),
            published_path.name,
            observed_roots[0].name,
            "snapshot transient close private message",
            "snapshot transient remove private message",
        ),
    )


def _source_request(document_id: str, *, ticker: str = "AAPL") -> SourceDocumentUpsertRequest:
    """构造 storage owner tests 使用的最小 source mutation 请求。

    Args:
        document_id: source document ID。
        ticker: transaction ticker。

    Returns:
        具备稳定主文件 identity 的 source upsert 请求。

    Raises:
        无。
    """

    return SourceDocumentUpsertRequest(
        ticker=ticker,
        document_id=document_id,
        internal_document_id=document_id,
        form_type="10-K",
        primary_document=f"{document_id}.txt",
        meta={
            "ingest_method": "upload",
            "source_provider": "user_upload",
        },
    )


def _identity_descriptor_file(identity_directory: Path) -> Path:
    """从已知 identity directory 黑盒枚举唯一隐藏 JSON descriptor。

    Args:
        identity_directory: storage owner 已创建的 identity directory。

    Returns:
        唯一隐藏 JSON descriptor 路径。

    Raises:
        AssertionError: descriptor 候选不唯一时抛出。
    """

    candidates = [path for path in identity_directory.iterdir() if path.name.startswith(".") and path.suffix == ".json"]
    assert len(candidates) == 1
    return candidates[0]


def _create_complete_rejected_artifact(
    maintenance: FsFilingMaintenanceRepository,
    *,
    batch: BatchToken,
    document_id: str,
) -> None:
    """在当前 batch 中创建 descriptor、meta 与物理文件一致的 rejected artifact。

    Args:
        maintenance: rejected artifact storage owner。
        batch: 显式 transaction capability。
        document_id: exact external rejected document ID。

    Returns:
        无。

    Raises:
        OSError: 文件或 meta 写入失败时抛出。
        ValueError: 请求字段或 identity 不合法时抛出。
    """

    file_meta = maintenance.store_rejected_filing_file(
        batch.ticker,
        document_id,
        "rejected.htm",
        io.BytesIO(b"rejected payload"),
        batch=batch,
        content_type="text/html",
    )
    maintenance.upsert_rejected_filing_artifact(
        RejectedFilingArtifactUpsertRequest(
            ticker=batch.ticker,
            document_id=document_id,
            internal_document_id=document_id,
            accession_number="0000320193-25-000001",
            company_id="0000320193",
            form_type="10-K",
            filing_date="2025-01-02",
            report_date="2024-12-31",
            primary_document="rejected.htm",
            selected_primary_document="rejected.htm",
            rejection_reason="policy",
            rejection_category="test",
            classification_version="v1",
            source_fingerprint="fingerprint",
            files=[
                SourceFileEntry(
                    name="rejected.htm",
                    uri=file_meta.uri,
                    size=file_meta.size,
                    content_type=file_meta.content_type,
                    sha256=file_meta.sha256,
                )
            ],
        ),
        batch=batch,
    )


def _create_complete_source(
    source_repository: FsSourceDocumentRepository,
    blob_repository: FsDocumentBlobRepository,
    *,
    batch: BatchToken,
    document_id: str,
    source_kind: SourceKind = SourceKind.FILING,
    ticker: str = "AAPL",
    payload: bytes | None = None,
) -> SourceHandle:
    """通过 blob-first + 单次 final source mutation 构造完整 source。

    Args:
        source_repository: source 业务事实仓储。
        blob_repository: 与 source 仓储共享 core 的 blob 仓储。
        batch: 当前显式 transaction capability。
        document_id: source 文档 ID。
        source_kind: filing 或 material。
        ticker: transaction ticker。
        payload: 可选测试文件内容。

    Returns:
        完整 source 的业务 handle。

    Raises:
        OSError: blob 或 final source staging 写入失败时抛出。
        ValueError: identity 或完整 source 输入非法时抛出。
    """

    filename = f"{document_id}.txt"
    handle = SourceHandle(
        ticker=ticker,
        document_id=document_id,
        source_kind=source_kind.value,
    )
    file_meta = blob_repository.store_file(
        handle,
        filename,
        io.BytesIO(payload if payload is not None else document_id.encode("utf-8")),
        batch=batch,
        content_type="text/plain",
    )
    source_repository.create_source_document(
        SourceDocumentUpsertRequest(
            ticker=ticker,
            document_id=document_id,
            internal_document_id=document_id,
            form_type="10-K" if source_kind is SourceKind.FILING else "EX-99",
            primary_document=filename,
            meta={
                "ingest_method": "upload",
                "source_provider": "user_upload",
            },
            files=[file_meta],
        ),
        source_kind,
        batch=batch,
    )
    return handle


def test_source_integrity_classifies_published_staged_and_whole_tree(
    tmp_path: Path,
) -> None:
    """typed integrity 必须区分 missing/complete/三类物理 corruption 并单 guard 枚举。"""

    repository_set = build_fs_repository_set(workspace_root=tmp_path)
    batching = FsBatchingRepository(tmp_path, repository_set=repository_set)
    source = FsSourceDocumentRepository(tmp_path, repository_set=repository_set)
    blob = FsDocumentBlobRepository(tmp_path, repository_set=repository_set)
    missing = source.classify_source_integrity(
        "AAPL",
        "missing",
        SourceKind.FILING,
    )
    assert missing.status is SourceIntegrityStatus.MISSING
    assert missing.revision is None

    batch = batching.begin_batch("AAPL")
    _create_complete_source(source, blob, batch=batch, document_id="filing-a")
    _create_complete_source(
        source,
        blob,
        batch=batch,
        document_id="material-a",
        source_kind=SourceKind.MATERIAL,
    )
    staged = source.classify_staged_source_integrity(
        "AAPL",
        "filing-a",
        SourceKind.FILING,
        batch=batch,
    )
    assert staged.status is SourceIntegrityStatus.COMPLETE
    batching.commit_batch(batch)

    inventory = source.list_source_integrity("AAPL")
    assert [(item.source_kind, item.document_id) for item in inventory] == [
        (SourceKind.FILING, "filing-a"),
        (SourceKind.MATERIAL, "material-a"),
    ]
    locator = source.get_source_document_locator(
        "AAPL",
        "filing-a",
        SourceKind.FILING,
    )
    source_dir = tmp_path / locator
    payload_path = source_dir / "filing-a.txt"
    original_payload = payload_path.read_bytes()

    payload_path.write_bytes(original_payload + b"-size")
    size_corrupt = source.classify_source_integrity(
        "AAPL",
        "filing-a",
        SourceKind.FILING,
    )
    assert size_corrupt.status is SourceIntegrityStatus.REPAIR_REQUIRED
    assert SourceIntegrityReason.SIZE_MISMATCH in size_corrupt.reasons
    assert SourceIntegrityReason.DIGEST_MISMATCH in size_corrupt.reasons

    payload_path.write_bytes(b"X" * len(original_payload))
    digest_corrupt = source.classify_source_integrity(
        "AAPL",
        "filing-a",
        SourceKind.FILING,
    )
    assert digest_corrupt.reasons == (SourceIntegrityReason.DIGEST_MISMATCH,)

    payload_path.unlink()
    missing_file = source.classify_source_integrity(
        "AAPL",
        "filing-a",
        SourceKind.FILING,
    )
    assert missing_file.reasons == (SourceIntegrityReason.PHYSICAL_FILE_MISSING,)
    payload_path.write_bytes(original_payload)

    meta_path = source_dir / "meta.json"
    original_meta = meta_path.read_text(encoding="utf-8")
    meta = json.loads(original_meta)
    meta["files"][0]["sha256"] = "malformed"
    meta_path.write_text(json.dumps(meta), encoding="utf-8")
    with pytest.raises(ValueError, match="64位小写十六进制"):
        source.classify_source_integrity(
            "AAPL",
            "filing-a",
            SourceKind.FILING,
        )
    with pytest.raises(ValueError, match="64位小写十六进制"):
        source.list_source_integrity("AAPL")
    meta_path.write_text(original_meta, encoding="utf-8")


def test_source_integrity_preflight_fails_closed_for_multiple_and_unselected(
    tmp_path: Path,
) -> None:
    """完整 inventory 的 multiple/material/unselected corruption 必须 typed fail closed。"""

    repository_set = build_fs_repository_set(workspace_root=tmp_path)
    batching = FsBatchingRepository(tmp_path, repository_set=repository_set)
    source = FsSourceDocumentRepository(tmp_path, repository_set=repository_set)
    blob = FsDocumentBlobRepository(tmp_path, repository_set=repository_set)
    batch = batching.begin_batch("AAPL")
    _create_complete_source(source, blob, batch=batch, document_id="selected")
    _create_complete_source(source, blob, batch=batch, document_id="unselected")
    batching.commit_batch(batch)
    for document_id in ("selected", "unselected"):
        locator = source.get_source_document_locator(
            "AAPL",
            document_id,
            SourceKind.FILING,
        )
        (tmp_path / locator / f"{document_id}.txt").unlink()
    with pytest.raises(SourceIntegrityPreflightError) as multiple_error:
        classify_source_integrity_preflight(
            source.list_source_integrity("AAPL"),
            accepted_filing_ids=frozenset({"selected"}),
            rejected_filing_ids=frozenset(),
        )
    assert multiple_error.value.reason is SourceIntegrityPreflightReason.MULTIPLE_REPAIR_REQUIRED

    unselected_path = (
        tmp_path
        / source.get_source_document_locator(
            "AAPL",
            "unselected",
            SourceKind.FILING,
        )
        / "unselected.txt"
    )
    unselected_path.write_bytes(b"unselected")
    with pytest.raises(SourceIntegrityPreflightError) as unselected_error:
        classify_source_integrity_preflight(
            source.list_source_integrity("AAPL"),
            accepted_filing_ids=frozenset(),
            rejected_filing_ids=frozenset(),
        )
    assert unselected_error.value.reason is SourceIntegrityPreflightReason.UNSELECTED_REPAIR_REQUIRED


def _publish_snapshot_version(
    source_repository: FsSourceDocumentRepository,
    blob_repository: FsDocumentBlobRepository,
    batching: FsBatchingRepository,
    *,
    version: _SnapshotVersion,
    replace_existing: bool,
) -> None:
    """通过真实 batch commit 发布一版双文件 snapshot fixture。

    Args:
        source_repository: source 业务事实仓储。
        blob_repository: 与 source 仓储共享 core 的 blob 仓储。
        batching: 真实 filesystem batch owner。
        version: 当前发布的 A/B 版本标签。
        replace_existing: 是否先 reset 已有同 ID source。

    Returns:
        无。

    Raises:
        OSError: staging 或 commit 文件系统操作失败时抛出。
        ValueError: source 完整性或 batch capability 非法时抛出。
    """

    batch = batching.begin_batch("AAPL")
    commit_started = False
    try:
        _stage_snapshot_version(
            source_repository,
            blob_repository,
            batch=batch,
            version=version,
            replace_existing=replace_existing,
        )
        commit_started = True
        batching.commit_batch(batch)
    finally:
        if not commit_started:
            batching.rollback_batch(batch)


def _read_snapshot_revision(
    repository: FsSourceDocumentRepository,
    ticker: str,
    document_id: str,
    source_kind: SourceKind,
) -> SourceDocumentRevision:
    """从 light snapshot 读取同版 opaque published revision。

    Args:
        repository: source repository。
        ticker: exact external ticker。
        document_id: exact external document ID。
        source_kind: 显式 source kind。

    Returns:
        snapshot 同版 revision。

    Raises:
        FileNotFoundError: source 不存在或已删除时抛出。
        ValueError: snapshot descriptor 非法时抛出。
        OSError: snapshot I/O 或 close 失败时抛出。
    """

    with repository.read_source_snapshot(
        ticker,
        document_id,
        source_kind,
        materialize_files=False,
    ) as snapshot:
        return snapshot.revision


def _stage_snapshot_version(
    source_repository: FsSourceDocumentRepository,
    blob_repository: FsDocumentBlobRepository,
    *,
    batch: BatchToken,
    version: _SnapshotVersion,
    replace_existing: bool,
) -> None:
    """在 caller-owned batch 中准备一版双文件 source publication。

    Args:
        source_repository: source 业务事实仓储。
        blob_repository: 与 source 仓储共享 core 的 blob 仓储。
        batch: caller 持有的显式 batch capability。
        version: 当前准备的 A/B 版本标签。
        replace_existing: 是否先 reset 已有同 ID source。

    Returns:
        无。

    Raises:
        OSError: source/blob staging 写入失败时抛出。
        ValueError: source 完整性或 batch capability 非法时抛出。
    """

    if replace_existing:
        source_repository.reset_source_document(
            "AAPL",
            "snapshot-doc",
            SourceKind.FILING,
            batch=batch,
        )
    lower_version = version.lower()
    handle = SourceHandle(
        ticker="AAPL",
        document_id="snapshot-doc",
        source_kind=SourceKind.FILING.value,
    )
    primary_name = f"{lower_version}-primary.txt"
    related_name = f"{lower_version}-related.txt"
    primary_meta = blob_repository.store_file(
        handle,
        primary_name,
        io.BytesIO(f"{version}-primary-content".encode("utf-8")),
        batch=batch,
        content_type="text/plain",
    )
    related_meta = blob_repository.store_file(
        handle,
        related_name,
        io.BytesIO(f"{version}-related-content".encode("utf-8")),
        batch=batch,
        content_type="text/plain",
    )
    source_repository.create_source_document(
        SourceDocumentUpsertRequest(
            ticker="AAPL",
            document_id="snapshot-doc",
            internal_document_id=f"snapshot-doc-{version}",
            form_type="10-K",
            primary_document=primary_name,
            meta={
                "ingest_method": "upload" if version == "A" else "download",
                "source_provider": "user_upload" if version == "A" else "sec_edgar",
                "version_marker": version,
            },
            files=[primary_meta, related_meta],
        ),
        SourceKind.FILING,
        batch=batch,
    )


def _blocking_batch_writer_in_process(
    workspace_root: str,
    connection: Connection,
) -> None:
    """在子进程记录 blocking acquire 前后并按父进程指令释放 batch。

    Args:
        workspace_root: 共享 workspace 字符串路径。
        connection: 与父进程同步的 duplex pipe。

    Returns:
        无。

    Raises:
        Exception: storage 或 pipe 失败时让子进程非零退出。
    """

    repository = FsBatchingRepository(Path(workspace_root))
    connection.send_bytes(b"acquire_entered")
    token = repository.begin_batch("AAPL")
    connection.send_bytes(b"acquired")
    if connection.recv_bytes() != b"release":
        raise RuntimeError("父进程未发送预期 release 指令")
    repository.rollback_batch(token)
    connection.close()


def test_cross_process_writer_blocks_then_acquires_after_release(tmp_path: Path) -> None:
    """跨进程同 ticker 后 writer 必须真实等待并在统一 release 后成功。"""

    workspace_root = tmp_path / "workspace"
    repository = FsBatchingRepository(workspace_root)
    first_token = repository.begin_batch("AAPL")
    context = multiprocessing.get_context("spawn")
    parent_connection, child_connection = context.Pipe(duplex=True)
    process = context.Process(
        target=_blocking_batch_writer_in_process,
        args=(str(workspace_root), child_connection),
    )
    process.start()
    child_connection.close()
    try:
        assert parent_connection.poll(5)
        assert parent_connection.recv_bytes() == b"acquire_entered"
        assert parent_connection.poll(0) is False
        repository.rollback_batch(first_token)
        assert parent_connection.poll(5)
        assert parent_connection.recv_bytes() == b"acquired"
        parent_connection.send_bytes(b"release")
        process.join(timeout=5)
    finally:
        if process.is_alive():
            process.terminate()
            process.join(timeout=5)
        parent_connection.close()
    assert process.exitcode == 0


def test_same_core_local_reservation_waits_then_notifies_on_release(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """同 core 同 ticker 后 writer 必须先等 local reservation，再被统一 notify。"""

    repository_set = build_fs_repository_set(workspace_root=tmp_path)
    repository = FsBatchingRepository(tmp_path, repository_set=repository_set)
    core = repository_set.core
    first_token = repository.begin_batch("AAPL")
    second_started = Event()
    file_lock_acquire_entered = Event()
    original_acquire = core._acquire_ticker_lock

    def observe_file_lock_acquire(ticker: str) -> RuntimeFileLockToken:
        """记录 local reservation 释放后的 file-lock acquire。"""

        file_lock_acquire_entered.set()
        return original_acquire(ticker)

    def begin_second() -> BatchToken:
        """报告线程已启动后尝试同 ticker batch。"""

        second_started.set()
        return repository.begin_batch("AAPL")

    monkeypatch.setattr(core, "_acquire_ticker_lock", observe_file_lock_acquire)
    with ThreadPoolExecutor(max_workers=1) as executor:
        waiting = executor.submit(begin_second)
        assert second_started.wait(timeout=5)
        assert waiting.done() is False
        assert file_lock_acquire_entered.is_set() is False
        repository.rollback_batch(first_token)
        second_token = waiting.result(timeout=5)
    assert file_lock_acquire_entered.is_set() is True
    repository.rollback_batch(second_token)


def test_recovery_try_lock_stays_nonblocking_while_writer_is_active(tmp_path: Path) -> None:
    """独立 core recovery 遇到活动 writer 时必须立即跳过且不改变 staging。"""

    first_set = build_fs_repository_set(workspace_root=tmp_path)
    first_repository = FsBatchingRepository(tmp_path, repository_set=first_set)
    active_token = first_repository.begin_batch("AAPL")
    staging_dir = first_set.core._active_batches[active_token.transaction_id].staging_ticker_dir
    second_set = build_fs_repository_set(workspace_root=tmp_path)

    with ThreadPoolExecutor(max_workers=1) as executor:
        recovery = executor.submit(second_set.core.ensure_batch_recovery)
        recovery.result(timeout=5)

    assert staging_dir.is_dir()
    assert active_token.transaction_id in first_set.core._active_batches
    first_repository.rollback_batch(active_token)


def _read_source_ids_in_process(workspace_root: str, connection: Connection) -> None:
    """在独立进程通过独立 repository core 读取 published source IDs。

    Args:
        workspace_root: 共享 workspace 的绝对路径字符串。
        connection: 向父进程报告 barrier 与读取结果的连接。

    Returns:
        无。

    Raises:
        OSError: repository 初始化、publication lock 或 pipe 写入失败时抛出。
    """

    try:
        repository_set = build_fs_repository_set(workspace_root=Path(workspace_root))
        repository = FsSourceDocumentRepository(
            Path(workspace_root),
            repository_set=repository_set,
        )
        core = repository_set.core
        signalling_acquire = _PublicationGuardAcquireSignal(
            connection,
            core._acquire_publication_guard,
        )
        with patch.object(core, "_acquire_publication_guard", signalling_acquire):
            document_ids = repository.list_source_document_ids("AAPL", SourceKind.FILING)
        connection.send_bytes("\0".join(document_ids).encode("utf-8"))
    finally:
        connection.close()


def _read_primary_source_bytes(repository: FsSourceDocumentRepository) -> bytes:
    """执行 composed primary-source public read 并消费 delayed opener。

    Args:
        repository: source repository。

    Returns:
        主文件字节。

    Raises:
        OSError: public read、文件打开或读取失败时抛出。
    """

    source = repository.get_primary_source("AAPL", "composed-read", SourceKind.FILING)
    with source.open() as stream:
        return stream.read()


def _build_core(tmp_path: Path) -> FsStorageCore:
    """构造测试用shared filesystem storage core。

    Args:
        tmp_path: pytest临时目录。

    Returns:
        新建workspace对应的storage core。

    Raises:
        OSError: 仓储初始化失败时抛出。
    """

    return build_fs_repository_set(workspace_root=tmp_path / "workspace").core


def _begin_mutated_batch(
    tmp_path: Path,
    *,
    old_target_exists: bool,
) -> tuple[FsStorageCore, BatchToken, _BatchPaths]:
    """构造包含new staging内容的active batch。

    Args:
        tmp_path: pytest临时目录。
        old_target_exists: 是否先创建旧正式target。

    Returns:
        storage core、active public token 与 storage owner state 中的物理路径。

    Raises:
        OSError: 目录或文件准备失败时抛出。
    """

    core = _build_core(tmp_path)
    target_dir = core._target_ticker_dir("AAPL")
    if old_target_exists:
        core._ensure_ticker_structure(target_dir, "AAPL")
        (target_dir / "state.txt").write_text("old", encoding="utf-8")
    batch = core.begin_batch("AAPL")
    paths = _active_batch_paths(core)
    (paths.staging_ticker_dir / "state.txt").write_text("new", encoding="utf-8")
    return core, batch, paths


def _seed_orphan_batch(
    core: FsStorageCore,
    *,
    phase: str,
    old_target_exists: bool,
    ticker: str = "AAPL",
) -> _BatchPaths:
    """按指定phase构造真实orphan目录与journal。

    Args:
        core: storage owner core。
        phase: journal phase。
        old_target_exists: 提交前是否有旧target。
        ticker: exact external ticker。

    Returns:
        描述本次 orphan 物理路径的测试路径对象。

    Raises:
        OSError: 测试目录或journal写入失败时抛出。
    """

    target_dir = core._target_ticker_dir(ticker)
    if old_target_exists:
        core._ensure_ticker_structure(target_dir, ticker)
        _write_state(target_dir, "old")
    core.begin_batch(ticker)
    state = _only_active_batch_state(core)
    paths = _active_batch_paths(core)
    _write_state(paths.staging_ticker_dir, "new")
    if phase in {_PHASE_BACKED_UP_TARGET, _PHASE_SWAPPED_TARGET, _PHASE_COMMITTED}:
        if old_target_exists:
            core._replace_directory(paths.target_ticker_dir, paths.backup_dir)
    if phase in {_PHASE_SWAPPED_TARGET, _PHASE_COMMITTED}:
        core._replace_directory(paths.staging_ticker_dir, paths.target_ticker_dir)
    core._write_batch_journal(state, phase)
    core._close_active_batch(state)
    return paths


def _only_active_batch_state(core: FsStorageCore) -> storage_infra_module._ActiveBatchState:
    """取得测试 core 唯一的 storage-owned active state。

    Args:
        core: storage core。

    Returns:
        唯一 active transaction 的内部 owner state。

    Raises:
        AssertionError: active state 数量不是一时抛出。
    """

    states = tuple(core._active_batches.values())
    assert len(states) == 1
    return states[0]


def _active_batch_paths(core: FsStorageCore) -> _BatchPaths:
    """从 storage owner state 读取 failure-injection 所需物理路径。

    Args:
        core: storage core。

    Returns:
        唯一 active transaction 的内部物理路径快照。

    Raises:
        AssertionError: active state 数量不是一时抛出。
    """

    state = _only_active_batch_state(core)
    return _BatchPaths(
        target_ticker_dir=state.target_ticker_dir,
        staging_root_dir=state.staging_root_dir,
        staging_ticker_dir=state.staging_ticker_dir,
        backup_dir=state.backup_dir,
        journal_path=state.journal_path,
    )


def _write_state(directory: Path, value: str) -> None:
    """写入测试目录的可观察状态文件。

    Args:
        directory: 目标目录。
        value: 状态文本。

    Returns:
        无。

    Raises:
        OSError: 目录或文件写入失败时抛出。
    """

    directory.mkdir(parents=True, exist_ok=True)
    (directory / "state.txt").write_text(value, encoding="utf-8")


def _raise_os_error(file_descriptor: int, error: OSError) -> None:
    """测试用fsync failure注入helper。

    Args:
        file_descriptor: 被忽略的文件描述符。
        error: 要抛出的预构造异常。

    Returns:
        无。

    Raises:
        OSError: 始终抛出传入异常。
    """

    del file_descriptor
    raise error


def _raise_replace_error(
    source: str | bytes | os.PathLike[str] | os.PathLike[bytes],
    target: str | bytes | os.PathLike[str] | os.PathLike[bytes],
    error: OSError,
) -> None:
    """测试用atomic replace failure注入helper。

    Args:
        source: 被忽略的源路径。
        target: 被忽略的目标路径。
        error: 要抛出的预构造异常。

    Returns:
        无。

    Raises:
        OSError: 始终抛出传入异常。
    """

    del source, target
    raise error
