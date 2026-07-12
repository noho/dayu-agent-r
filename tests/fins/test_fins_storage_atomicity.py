"""Fins storage identity、batch commit/recovery 与本地对象原子性测试。"""

from __future__ import annotations

import io
import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import BinaryIO, Literal

import pytest

import dayu.fins.storage._fs_storage_infra as storage_infra_module
import dayu.fins.storage._fs_storage_utils as storage_utils_module
import dayu.fins.storage.local_file_store as local_file_store_module
from dayu.fins.domain.document_models import (
    BatchToken,
    FileObjectMeta,
    ProcessedCreateRequest,
    ProcessedHandle,
    SourceDocumentUpsertRequest,
    SourceHandle,
)
from dayu.fins.domain.enums import SourceKind
from dayu.fins.storage import (
    FsDocumentBlobRepository,
    FsProcessedDocumentRepository,
    FsSourceDocumentRepository,
    LocalFileStore,
)
from dayu.fins.storage._fs_repository_factory import build_fs_repository_set
from dayu.fins.storage._fs_storage_core import FsStorageCore
from dayu.fins.storage._fs_storage_infra import (
    _PHASE_BACKED_UP_TARGET,
    _PHASE_COMMITTED,
    _PHASE_STARTED,
    _PHASE_SWAPPED_TARGET,
)
from dayu.fins.storage._fs_storage_utils import (
    _local_path_from_uri,
    _normalize_document_id,
    _normalize_entry_name,
    _normalize_filename,
    _normalize_object_key,
    _normalize_ticker,
)

_Normalizer = Callable[[str], str]
_CommitFailurePoint = Literal[
    "backup_rename",
    "backed_journal",
    "staging_rename",
    "swapped_journal",
    "committed_journal",
]
_ReplaceTargetKind = Literal["directory", "broken_symlink"]


@pytest.mark.parametrize(
    "normalizer",
    (_normalize_ticker, _normalize_document_id, _normalize_entry_name, _normalize_filename),
)
@pytest.mark.parametrize("value", ("", "   ", ".", "..", "a/b", "a\\b", "C:"))
def test_single_component_owners_reject_invalid_values(
    normalizer: _Normalizer,
    value: str,
) -> None:
    """ticker/document/entry/filename owner 应拒绝非法单路径组件。

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

    assert _normalize_ticker("brk.b") == "BRK-B"
    assert _normalize_ticker("test-1") == "TEST-1"
    key = "BRK.B/filings/annual-report/report-2024.md"
    store = LocalFileStore(tmp_path / "objects")

    meta = store.put_object(key, io.BytesIO(b"round-trip"), content_type="text/markdown")

    assert meta.uri == f"local://{key}"
    with store.get_object(key) as stream:
        assert stream.read() == b"round-trip"


@pytest.mark.parametrize(
    "handle",
    (
        SourceHandle(ticker="AAPL", document_id="missing-source", source_kind=SourceKind.FILING.value),
        ProcessedHandle(ticker="AAPL", document_id="missing-processed"),
    ),
)
def test_store_file_requires_source_or_processed_meta_before_file_store_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    handle: SourceHandle | ProcessedHandle,
) -> None:
    """两类 handle 不存在时 store_file 都不得调用 FileStore。

    Args:
        tmp_path: pytest 临时目录。
        monkeypatch: pytest monkeypatch fixture。
        handle: 不存在的 source/processed handle。

    Returns:
        无。

    Raises:
        AssertionError: FileStore 被调用或异常类型错误时由 pytest 抛出。
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

    with pytest.raises(FileNotFoundError):
        blob_repository.store_file(handle, "report.md", io.BytesIO(b"payload"))

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
    source_request = SourceDocumentUpsertRequest(
        ticker="AAPL",
        document_id="annual-report",
        internal_document_id="annual-report",
        form_type="10-K",
        primary_document="report.md",
        meta={"ingest_method": "upload", "ingest_complete": True},
    )
    source_repository.create_source_document(source_request, SourceKind.FILING)
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
        )
    )
    source_handle = source_repository.get_source_handle(
        "AAPL",
        "annual-report",
        SourceKind.FILING,
    )
    processed_handle = processed_repository.get_processed_handle("AAPL", "annual-report")

    source_file_meta = blob_repository.store_file(
        source_handle,
        "report.md",
        io.BytesIO(b"source"),
    )
    blob_repository.store_file(
        processed_handle,
        "analysis.json",
        io.BytesIO(b"processed"),
    )
    source_repository.update_source_document(
        SourceDocumentUpsertRequest(
            ticker="AAPL",
            document_id="annual-report",
            internal_document_id="annual-report",
            form_type="10-K",
            primary_document="report.md",
            meta={"ingest_method": "upload", "ingest_complete": True},
            files=[source_file_meta],
        ),
        SourceKind.FILING,
    )

    assert blob_repository.read_file_bytes(source_handle, "report.md") == b"source"
    assert blob_repository.read_file_bytes(processed_handle, "analysis.json") == b"processed"
    assert [entry.name for entry in blob_repository.list_entries(source_handle)] == [
        "meta.json",
        "report.md",
    ]
    assert blob_repository.list_files(source_handle) == [source_file_meta]
    blob_repository.delete_entry(processed_handle, "analysis.json")
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

    core, token = _begin_mutated_batch(tmp_path, old_target_exists=old_target_exists)
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

        if failure_point == "backup_rename" and source == token.target_ticker_dir:
            raise injected_error
        if failure_point == "staging_rename" and source == token.staging_ticker_dir:
            raise injected_error
        original_replace(source, target)

    def _write_journal(current_token: BatchToken, phase: str) -> None:
        """按phase语义注入journal失败。

        Args:
            current_token: 当前batch token。
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
        original_write_journal(current_token, phase)

    monkeypatch.setattr(core, "_replace_directory", _replace_directory)
    monkeypatch.setattr(core, "_write_batch_journal", _write_journal)

    with pytest.raises(OSError) as exc_info:
        core.commit_batch(token)

    assert exc_info.value is injected_error
    if old_target_exists:
        assert (token.target_ticker_dir / "state.txt").read_text(encoding="utf-8") == "old"
    else:
        assert not token.target_ticker_dir.exists()
    assert not token.staging_root_dir.exists()
    assert not token.backup_dir.exists()
    with pytest.raises(ValueError, match="无效的 batch token"):
        core.rollback_batch(token)


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

    core, token = _begin_mutated_batch(tmp_path, old_target_exists=True)
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

        if source == token.target_ticker_dir and target == token.staging_ticker_dir:
            raise rollback_error
        original_replace(source, target)

    def _write_journal(current_token: BatchToken, phase: str) -> None:
        """在SWAPPED_TARGET journal写入时注入primary failure。

        Args:
            current_token: 当前batch token。
            phase: 待写入phase。

        Returns:
            无。

        Raises:
            OSError: phase为SWAPPED_TARGET时抛出。
        """

        if phase == _PHASE_SWAPPED_TARGET:
            raise commit_error
        original_write_journal(current_token, phase)

    monkeypatch.setattr(core, "_replace_directory", _replace_directory)
    monkeypatch.setattr(core, "_write_batch_journal", _write_journal)

    with pytest.raises(OSError) as exc_info:
        core.commit_batch(token)

    assert exc_info.value is commit_error
    assert exc_info.value.__cause__ is rollback_error
    assert any("recovery evidence retained" in note for note in exc_info.value.__notes__)
    assert token.journal_path.exists()
    assert token.backup_dir.exists()
    assert token.staging_root_dir.exists()
    assert (token.target_ticker_dir / "state.txt").read_text(encoding="utf-8") == "new"
    with pytest.raises(ValueError, match="无效的 batch token"):
        core.rollback_batch(token)


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
    token = _seed_orphan_batch(core, token_id=f"token-{phase}", phase=phase, old_target_exists=True)

    core.recover_orphan_batches()

    expected = "new" if phase == _PHASE_COMMITTED else "old"
    assert (token.target_ticker_dir / "state.txt").read_text(encoding="utf-8") == expected
    assert not token.backup_dir.exists()
    assert not token.staging_root_dir.exists()


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
    token = _seed_orphan_batch(
        core,
        token_id="token-swapped-absent",
        phase=_PHASE_SWAPPED_TARGET,
        old_target_exists=False,
    )

    core.recover_orphan_batches()

    assert not token.target_ticker_dir.exists()
    assert not token.staging_root_dir.exists()


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

    core, token = _begin_mutated_batch(tmp_path, old_target_exists=True)
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

        if path == token.backup_dir:
            raise cleanup_error
        original_remove(path)

    monkeypatch.setattr(core, "_remove_directory", _remove_directory)

    core.commit_batch(token)

    assert (token.target_ticker_dir / "state.txt").read_text(encoding="utf-8") == "new"
    assert token.backup_dir.exists()
    assert token.journal_path.exists()
    journal = json.loads(token.journal_path.read_text(encoding="utf-8"))
    assert journal["phase"] == _PHASE_COMMITTED
    monkeypatch.setattr(core, "_remove_directory", original_remove)

    core.recover_orphan_batches()

    assert (token.target_ticker_dir / "state.txt").read_text(encoding="utf-8") == "new"
    assert not token.backup_dir.exists()
    assert not token.staging_root_dir.exists()


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

    core, token = _begin_mutated_batch(tmp_path, old_target_exists=True)
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

    def _record_journal(current_token: BatchToken, phase: str) -> None:
        """记录每个phase写入后最新directory sync。

        Args:
            current_token: 当前batch token。
            phase: 待写入phase。

        Returns:
            无。

        Raises:
            OSError: journal写入失败时透传。
        """

        before = len(synced_paths)
        original_write_journal(current_token, phase)
        if phase == _PHASE_COMMITTED:
            committed_sync_paths.extend(synced_paths[before:])

    monkeypatch.setattr(storage_utils_module, "_fsync_directory", _record_sync)
    monkeypatch.setattr(core, "_write_batch_journal", _record_journal)

    core.commit_batch(token)

    assert token.journal_path.parent in committed_sync_paths


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

    core, token = _begin_mutated_batch(tmp_path, old_target_exists=True)
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

    core.commit_batch(token)

    assert token.target_ticker_dir.parent in synced_paths
    assert token.backup_dir.parent in synced_paths
    assert token.staging_ticker_dir.parent in synced_paths


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

    def _record_replace(source: str | bytes | os.PathLike[str] | os.PathLike[bytes], target: str | bytes | os.PathLike[str] | os.PathLike[bytes]) -> None:
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
        monkeypatch.setattr(local_file_store_module.os, "fsync", lambda file_descriptor: _raise_os_error(file_descriptor, injected_error))
    else:
        monkeypatch.setattr(local_file_store_module.os, "replace", lambda source, target: _raise_replace_error(source, target, injected_error))

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
) -> tuple[FsStorageCore, BatchToken]:
    """构造包含new staging内容的active batch。

    Args:
        tmp_path: pytest临时目录。
        old_target_exists: 是否先创建旧正式target。

    Returns:
        storage core与active token。

    Raises:
        OSError: 目录或文件准备失败时抛出。
    """

    core = _build_core(tmp_path)
    target_dir = core.portfolio_root / "AAPL"
    if old_target_exists:
        target_dir.mkdir(parents=True)
        (target_dir / "state.txt").write_text("old", encoding="utf-8")
    token = core.begin_batch("AAPL")
    (token.staging_ticker_dir / "state.txt").write_text("new", encoding="utf-8")
    return core, token


def _seed_orphan_batch(
    core: FsStorageCore,
    *,
    token_id: str,
    phase: str,
    old_target_exists: bool,
) -> BatchToken:
    """按指定phase构造真实orphan目录与journal。

    Args:
        core: storage owner core。
        token_id: 测试token id。
        phase: journal phase。
        old_target_exists: 提交前是否有旧target。

    Returns:
        描述本次orphan物理路径的batch token。

    Raises:
        OSError: 测试目录或journal写入失败时抛出。
    """

    ticker = "AAPL"
    target_dir = core.portfolio_root / ticker
    staging_root_dir = core.batch_root / token_id
    staging_ticker_dir = staging_root_dir / ticker
    backup_dir = core.backup_root / f"{ticker}.bak.{token_id}"
    token = BatchToken(
        token_id=token_id,
        owner_token=f"owner-{token_id}",
        owner_scope_id="test-scope",
        ticker=ticker,
        target_ticker_dir=target_dir,
        staging_root_dir=staging_root_dir,
        staging_ticker_dir=staging_ticker_dir,
        backup_dir=backup_dir,
        journal_path=staging_root_dir / "transaction.json",
        ticker_lock_path=core.dayu_root / "batch_locks" / f"{ticker}.lock",
        created_at="2026-07-12T00:00:00+00:00",
    )
    staging_root_dir.mkdir(parents=True, exist_ok=True)
    if phase == _PHASE_STARTED:
        if old_target_exists:
            _write_state(target_dir, "old")
        _write_state(staging_ticker_dir, "new")
    elif phase == _PHASE_BACKED_UP_TARGET:
        if old_target_exists:
            _write_state(backup_dir, "old")
        _write_state(staging_ticker_dir, "new")
    else:
        if old_target_exists:
            _write_state(backup_dir, "old")
        _write_state(target_dir, "new")
    core._write_batch_journal(token, phase)
    return token


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
