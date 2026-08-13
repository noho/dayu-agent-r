"""文件系统 source snapshot 的稳定读取与资源生命周期实现。

该私有模块拥有 source snapshot 的单次 guard 采集、打开文件描述符复制、
publication 后验核对、临时树清理与 close 后不可读语义。它不向 consumer
暴露 published path、local URI、private storage key 或内部稳定读取次数。
"""

from __future__ import annotations

import hashlib
import os
import shutil
import stat
import tempfile
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from types import TracebackType
from typing import TYPE_CHECKING, BinaryIO, Final, Literal, Optional

from dayu.contracts.json_value import JsonValue
from dayu.documents.processors.source import Source
from dayu.fins.domain.document_models import (
    SourceDocumentProvenance,
    SourceDocumentRevision,
)
from dayu.fins.domain.enums import SourceKind

from ._fs_identity import _IDENTITY_DESCRIPTOR_FILENAME, _require_external_identity
from ._fs_storage_infra import (
    _source_meta_without_revision,
    _source_revision_from_meta,
)
from ._fs_storage_utils import (
    _append_secondary_error_note,
    _file_object_meta_from_dict,
    _guess_media_type,
    _list_directory,
    _local_path_from_uri,
    _normalize_filename,
    _normalize_source_kind,
    _open_binary_file,
    _project_filesystem_error,
    _raise_path_free_error,
    _read_file_bytes,
)
from .repository_protocols import (
    SourceSnapshotConsistencyError,
    SourceSnapshotFileDescriptor,
    SourceSnapshotProtocol,
)
from .source_meta_contract import require_source_meta_is_deleted

if TYPE_CHECKING:
    from ._fs_source_document_core import _FsSourceDocumentMixin


_STABLE_READ_ATTEMPT_LIMIT: Final[int] = 3
_COPY_CHUNK_SIZE: Final[int] = 1024 * 1024
_SNAPSHOT_CONTEXT_CLOSE_ACTION: Final[str] = "source snapshot lifecycle close failed"


class _SourcePublicationChanged(RuntimeError):
    """一次 snapshot attempt 的 published source marker 已变化。"""


@dataclass(frozen=True, slots=True)
class _StableFileState:
    """复制前后用于识别同一已打开 regular inode 的稳定属性。"""

    device: int
    inode: int
    mode: int
    size: int
    modified_ns: int
    changed_ns: int


@dataclass(slots=True)
class _OpenSnapshotFile:
    """一次 snapshot attempt 持有的业务文件描述符。"""

    descriptor: SourceSnapshotFileDescriptor
    stream: BinaryIO
    initial_state: _StableFileState


@dataclass(frozen=True, slots=True)
class _PublishedSnapshotMarker:
    """后验核对使用且不向 consumer 暴露的 publication marker。"""

    source_kind: SourceKind
    revision: SourceDocumentRevision
    is_deleted: bool
    ticker_descriptor: bytes
    document_descriptor: bytes


@dataclass(slots=True)
class _AcquiredSnapshotAttempt:
    """publication guard 内一次性取得的 snapshot attempt。"""

    ticker: str
    document_id: str
    source_kind: SourceKind
    source_meta: dict[str, JsonValue]
    provenance: SourceDocumentProvenance
    revision: SourceDocumentRevision
    files: tuple[SourceSnapshotFileDescriptor, ...]
    primary_filename: str
    marker: _PublishedSnapshotMarker
    open_files: list[_OpenSnapshotFile]


@dataclass(slots=True)
class _SnapshotResourceState:
    """snapshot 与其派生 Source 共享的最小可关闭状态。"""

    temp_root: Optional[Path]
    closed: bool = False
    lock: Lock = field(default_factory=Lock)

    def require_open_root(self) -> Path:
        """返回仍可读的 snapshot 临时根目录。

        Args:
            无。

        Returns:
            当前 full snapshot 私有临时根目录。

        Raises:
            RuntimeError: snapshot 已关闭或没有物化文件时抛出。
        """

        with self.lock:
            if self.closed:
                raise RuntimeError("source snapshot 已关闭")
            if self.temp_root is None:
                raise RuntimeError("light source snapshot 未物化文件")
            return self.temp_root

    def require_open(self) -> None:
        """确认 snapshot 资源仍处于可读状态。

        Args:
            无。

        Returns:
            无。

        Raises:
            RuntimeError: snapshot 已关闭时抛出。
        """

        with self.lock:
            if self.closed:
                raise RuntimeError("source snapshot 已关闭")

    def close(self) -> None:
        """幂等关闭资源并删除 full snapshot 临时树。

        Args:
            无。

        Returns:
            无。

        Raises:
            OSError: 临时树清理失败时抛出 path-free 文件系统异常。
        """

        with self.lock:
            # 复杂逻辑说明：closed 先阻止后续读取，但 cleanup locator 必须保留到
            # rmtree 真正成功；失败后的下一次 close 才能重试同一私有临时树。
            self.closed = True
            temp_root = self.temp_root
            if temp_root is None:
                return
            _remove_snapshot_temp_root(temp_root)
            self.temp_root = None


@dataclass(frozen=True, slots=True)
class _SnapshotFileSource:
    """只引用 snapshot 私有临时树且受共享 close 状态约束的 Source。"""

    state: _SnapshotResourceState
    descriptor: SourceSnapshotFileDescriptor

    @property
    def uri(self) -> str:
        """返回不含 filesystem locator 的 snapshot-local URI。"""

        return f"snapshot://source/{self.descriptor.name}"

    @property
    def media_type(self) -> Optional[str]:
        """返回文件声明或按业务文件名推断的媒体类型。"""

        if self.descriptor.content_type is not None:
            return self.descriptor.content_type
        return _guess_media_type(Path(self.descriptor.name))

    @property
    def content_length(self) -> Optional[int]:
        """返回文件声明的字节数。"""

        return self.descriptor.size

    @property
    def etag(self) -> Optional[str]:
        """返回文件声明的对象标识。"""

        return self.descriptor.etag

    def open(self) -> BinaryIO:
        """打开 snapshot 私有临时文件。

        Args:
            无。

        Returns:
            二进制只读流。

        Raises:
            RuntimeError: snapshot 已关闭或未物化时抛出。
            OSError: 临时文件打开失败时抛出 path-free 文件系统异常。
        """

        temp_root = self.state.require_open_root()
        return _open_binary_file(
            temp_root / self.descriptor.name,
            action="打开 source snapshot 临时文件",
        )

    def materialize(self, suffix: Optional[str] = None) -> Path:
        """返回 snapshot 私有临时文件路径。

        Args:
            suffix: 处理器可选后缀；snapshot 文件已按业务文件名落盘，因此忽略。

        Returns:
            snapshot 临时树中的可读文件路径。

        Raises:
            RuntimeError: snapshot 已关闭或未物化时抛出。
        """

        del suffix
        return self.state.require_open_root() / self.descriptor.name


class _FsSourceSnapshot(SourceSnapshotProtocol):
    """文件系统 source snapshot 的私有资源实现。"""

    def __init__(
        self,
        *,
        ticker: str,
        document_id: str,
        source_kind: SourceKind,
        source_meta: Mapping[str, JsonValue],
        provenance: SourceDocumentProvenance,
        revision: SourceDocumentRevision,
        files: tuple[SourceSnapshotFileDescriptor, ...],
        primary_filename: str,
        temp_root: Optional[Path],
    ) -> None:
        """初始化同版 descriptor 与可关闭资源。

        Args:
            ticker: exact external ticker。
            document_id: exact external document ID。
            source_kind: storage 已解析的 source kind。
            source_meta: 不含 storage 私有字段的 source business meta。
            provenance: 与 source meta 同版的 typed provenance。
            revision: persisted opaque revision。
            files: 完整有序业务文件描述符。
            primary_filename: 精确命中文件描述符的主文件名。
            temp_root: full snapshot 私有临时根；light snapshot 为 ``None``。

        Returns:
            无。

        Raises:
            无。
        """

        self._ticker = ticker
        self._document_id = document_id
        self._source_kind = source_kind
        self._source_meta = deepcopy(dict(source_meta))
        self._provenance = provenance
        self._revision = revision
        self._files = files
        self._primary_filename = primary_filename
        self._files_by_name = {item.name: item for item in files}
        self._state = _SnapshotResourceState(temp_root=temp_root)

    def __enter__(self) -> SourceSnapshotProtocol:
        """进入 snapshot 资源生命周期。

        Args:
            无。

        Returns:
            当前仍可读的 snapshot 资源。

        Raises:
            RuntimeError: snapshot 已关闭时抛出。
        """

        self._state.require_open()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> Literal[False]:
        """退出 snapshot 生命周期并按 owner 规则关闭资源。

        Args:
            exc_type: 生命周期内活动异常的类型；正常退出时为 ``None``。
            exc: 生命周期内活动异常；正常退出时为 ``None``。
            traceback: 生命周期内活动异常的 traceback；正常退出时为 ``None``。

        Returns:
            始终返回 ``False``，不压制生命周期内的活动异常。

        Raises:
            OSError: 无活动主异常且临时资源清理失败时抛出 path-free 文件系统异常。
            BaseException: 无活动主异常且私有 close 实现抛出其它失败时原样抛出。
        """

        del exc_type, traceback
        try:
            self.close()
        except BaseException as close_error:
            if exc is None:
                raise
            # 复杂逻辑说明：close failure 只投影为稳定的 action/type/errno note；
            # raw message、cause、context、traceback 与 locator 均不得进入主异常图。
            _append_secondary_error_note(
                exc,
                close_error,
                action=_SNAPSHOT_CONTEXT_CLOSE_ACTION,
            )
        return False

    @property
    def ticker(self) -> str:
        """返回 exact external ticker。

        Raises:
            RuntimeError: snapshot 已关闭时抛出。
        """

        self._state.require_open()
        return self._ticker

    @property
    def document_id(self) -> str:
        """返回 exact external document ID。

        Raises:
            RuntimeError: snapshot 已关闭时抛出。
        """

        self._state.require_open()
        return self._document_id

    @property
    def source_kind(self) -> SourceKind:
        """返回 snapshot source kind。

        Raises:
            RuntimeError: snapshot 已关闭时抛出。
        """

        self._state.require_open()
        return self._source_kind

    @property
    def source_meta(self) -> Mapping[str, JsonValue]:
        """返回独立 source business meta 副本。

        Raises:
            RuntimeError: snapshot 已关闭时抛出。
        """

        self._state.require_open()
        return deepcopy(self._source_meta)

    @property
    def provenance(self) -> SourceDocumentProvenance:
        """返回同版 typed provenance。

        Raises:
            RuntimeError: snapshot 已关闭时抛出。
        """

        self._state.require_open()
        return self._provenance

    @property
    def revision(self) -> SourceDocumentRevision:
        """返回同版 opaque revision。

        Raises:
            RuntimeError: snapshot 已关闭时抛出。
        """

        self._state.require_open()
        return self._revision

    @property
    def files(self) -> tuple[SourceSnapshotFileDescriptor, ...]:
        """返回完整有序业务文件描述符。

        Raises:
            RuntimeError: snapshot 已关闭时抛出。
        """

        self._state.require_open()
        return self._files

    @property
    def primary_filename(self) -> str:
        """返回精确主文件名。

        Raises:
            RuntimeError: snapshot 已关闭时抛出。
        """

        self._state.require_open()
        return self._primary_filename

    def get_source(self, filename: str) -> Source:
        """返回 full snapshot 中指定文件的临时 Source。

        Args:
            filename: exact 业务文件名。

        Returns:
            受 snapshot close 状态约束的 Source。

        Raises:
            FileNotFoundError: filename 不属于 snapshot 时抛出。
            RuntimeError: snapshot 已关闭或未物化文件时抛出。
        """

        self._state.require_open_root()
        descriptor = self._files_by_name.get(filename)
        if descriptor is None:
            raise FileNotFoundError(f"source snapshot 不包含业务文件: {filename}")
        return _SnapshotFileSource(self._state, descriptor)

    def get_primary_source(self) -> Source:
        """返回 full snapshot 主文件的临时 Source。

        Args:
            无。

        Returns:
            受 snapshot close 状态约束的主文件 Source。

        Raises:
            RuntimeError: snapshot 已关闭或未物化文件时抛出。
        """

        return self.get_source(self._primary_filename)

    def close(self) -> None:
        """幂等关闭 snapshot 并释放私有临时树。

        Args:
            无。

        Returns:
            无。

        Raises:
            OSError: 临时树清理失败时抛出 path-free 文件系统异常。
        """

        self._state.close()


def _read_source_snapshot(
    core: _FsSourceDocumentMixin,
    ticker: str,
    document_id: str,
    source_kind: Optional[SourceKind],
    *,
    materialize_files: bool,
) -> SourceSnapshotProtocol:
    """通过有界稳定 attempt 读取 storage-owned source snapshot。

    Args:
        core: 当前 filesystem repository 的共享 storage core。
        ticker: exact external ticker。
        document_id: exact external document ID。
        source_kind: 可选显式 source kind。
        materialize_files: 是否复制全部文件到 snapshot 私有临时树。

    Returns:
        light 或 full typed snapshot resource。

    Raises:
        FileNotFoundError: source 不存在、已删除或 reset 后抛出。
        ValueError: source kind 歧义或 source 完整性非法时抛出。
        SourceSnapshotConsistencyError: full snapshot 持续遇到真实 publication 变化时抛出。
        RuntimeError: publication guard 操作失败时抛出。
        OSError: published 或临时文件系统访问失败时抛出。
    """

    external_ticker = _require_external_identity(ticker, field_name="ticker")
    external_document_id = _require_external_identity(
        document_id,
        field_name="document_id",
    )
    normalized_source_kind = (
        None if source_kind is None else _normalize_source_kind(source_kind)
    )
    if not materialize_files:
        attempt = _acquire_snapshot_attempt(
            core,
            external_ticker,
            external_document_id,
            normalized_source_kind,
        )
        _cleanup_snapshot_attempt(
            attempt.open_files,
            temp_root=None,
            primary_error=None,
            retain_temp_on_success=False,
        )
        return _snapshot_from_attempt(attempt, temp_root=None)

    last_change: Optional[_SourcePublicationChanged] = None
    for _attempt_index in range(_STABLE_READ_ATTEMPT_LIMIT):
        attempt = _acquire_snapshot_attempt(
            core,
            external_ticker,
            external_document_id,
            normalized_source_kind,
        )
        temp_root: Optional[Path] = None
        try:
            temp_root = _create_snapshot_temp_root()
        except BaseException as create_error:
            _cleanup_snapshot_attempt(
                attempt.open_files,
                temp_root=None,
                primary_error=create_error,
                retain_temp_on_success=False,
            )
            raise
        copy_error: Optional[BaseException] = None
        try:
            _copy_snapshot_files(attempt.open_files, temp_root)
        except (OSError, ValueError) as exc:
            copy_error = exc
        except BaseException as unexpected_copy_error:
            _cleanup_snapshot_attempt(
                attempt.open_files,
                temp_root=temp_root,
                primary_error=unexpected_copy_error,
                retain_temp_on_success=False,
            )
            raise
        try:
            published_marker = _read_published_marker(
                core,
                external_ticker,
                external_document_id,
                attempt.source_kind,
            )
        except BaseException as marker_error:
            _cleanup_snapshot_attempt(
                attempt.open_files,
                temp_root=temp_root,
                primary_error=marker_error,
                retain_temp_on_success=False,
            )
            raise
        if published_marker != attempt.marker:
            last_change = _SourcePublicationChanged(
                "source publication marker changed during snapshot read"
            )
            _cleanup_snapshot_attempt(
                attempt.open_files,
                temp_root=temp_root,
                primary_error=None,
                retain_temp_on_success=False,
            )
            continue
        if copy_error is not None:
            _cleanup_snapshot_attempt(
                attempt.open_files,
                temp_root=temp_root,
                primary_error=copy_error,
                retain_temp_on_success=False,
            )
            _raise_path_free_error(copy_error)
        _cleanup_snapshot_attempt(
            attempt.open_files,
            temp_root=temp_root,
            primary_error=None,
            retain_temp_on_success=True,
        )
        return _snapshot_from_attempt(attempt, temp_root=temp_root)
    consistency_error = SourceSnapshotConsistencyError()
    consistency_error.__suppress_context__ = True
    raise consistency_error from last_change


def _snapshot_from_attempt(
    attempt: _AcquiredSnapshotAttempt,
    *,
    temp_root: Optional[Path],
) -> SourceSnapshotProtocol:
    """把已验证 attempt 收敛为唯一 private snapshot resource。

    Args:
        attempt: 已完成 guard 采集与必要后验核对的 attempt。
        temp_root: full snapshot 私有临时树；light snapshot 为 ``None``。

    Returns:
        typed snapshot protocol 实现。

    Raises:
        无。
    """

    return _FsSourceSnapshot(
        ticker=attempt.ticker,
        document_id=attempt.document_id,
        source_kind=attempt.source_kind,
        source_meta=attempt.source_meta,
        provenance=attempt.provenance,
        revision=attempt.revision,
        files=attempt.files,
        primary_filename=attempt.primary_filename,
        temp_root=temp_root,
    )


def _acquire_snapshot_attempt(
    core: _FsSourceDocumentMixin,
    ticker: str,
    document_id: str,
    source_kind: Optional[SourceKind],
) -> _AcquiredSnapshotAttempt:
    """在一次 publication guard 内读取 descriptor 并打开全部业务文件。

    Args:
        core: 当前 filesystem storage core。
        ticker: exact external ticker。
        document_id: exact external document ID。
        source_kind: 可选显式 source kind。

    Returns:
        持有全部已打开文件描述符的 snapshot attempt。

    Raises:
        FileNotFoundError: source 不存在或已删除时抛出。
        ValueError: source kind 歧义或 source 完整性非法时抛出。
        RuntimeError: publication guard 操作失败时抛出。
        OSError: descriptor、meta 或业务文件读取失败时抛出。
    """

    guard_token = core._acquire_publication_guard(ticker)
    attempt: Optional[_AcquiredSnapshotAttempt] = None
    acquire_error: Optional[BaseException] = None
    try:
        attempt = _acquire_snapshot_attempt_unguarded(
            core,
            ticker,
            document_id,
            source_kind,
        )
    except BaseException as exc:
        acquire_error = exc
    try:
        core._release_lock_token(guard_token)
    except BaseException as release_error:
        if acquire_error is not None:
            _append_secondary_error_note(
                acquire_error,
                release_error,
                action="source snapshot publication guard release failed",
            )
        else:
            if attempt is None:
                raise RuntimeError("source snapshot acquire state 非法")
            _cleanup_snapshot_attempt(
                attempt.open_files,
                temp_root=None,
                primary_error=release_error,
                retain_temp_on_success=False,
            )
            raise
    if acquire_error is not None:
        _raise_path_free_error(acquire_error)
    if attempt is None:
        raise RuntimeError("source snapshot acquire state 非法")
    return attempt


def _acquire_snapshot_attempt_unguarded(
    core: _FsSourceDocumentMixin,
    ticker: str,
    document_id: str,
    source_kind: Optional[SourceKind],
) -> _AcquiredSnapshotAttempt:
    """在 caller 已持 publication guard 时构造 snapshot attempt。

    Args:
        core: 当前 filesystem storage core。
        ticker: exact external ticker。
        document_id: exact external document ID。
        source_kind: 可选显式 source kind。

    Returns:
        同版 descriptor/meta/provenance/revision 与全部打开文件。

    Raises:
        FileNotFoundError: source 不存在或已删除时抛出。
        ValueError: source kind 歧义、meta、descriptor、primary 或文件声明非法时抛出。
        OSError: descriptor、meta 或业务文件读取失败时抛出。
    """

    resolved_source_kind = _resolve_snapshot_source_kind_unguarded(
        core,
        ticker,
        document_id,
        source_kind,
    )
    meta_path = core._source_meta_path_for_read(
        ticker,
        document_id,
        resolved_source_kind,
    )
    document_dir = meta_path.parent
    if meta_path.is_symlink() or not meta_path.is_file():
        raise ValueError("source snapshot meta 必须为 non-symlink regular file")
    persisted_meta = core._get_persisted_source_meta_unguarded(
        ticker,
        document_id,
        resolved_source_kind,
    )
    revision = _source_revision_from_meta(persisted_meta)
    provenance = SourceDocumentProvenance.from_meta(
        persisted_meta,
        resolved_source_kind,
    )
    if not provenance.ingest_complete:
        raise ValueError("source snapshot 只读取完成态 source")
    is_deleted = require_source_meta_is_deleted(persisted_meta)
    if is_deleted:
        raise FileNotFoundError(
            f"document_id={document_id} 的 {resolved_source_kind.value} source 已删除"
        )
    files, primary_filename = _parse_snapshot_files(
        core,
        ticker,
        resolved_source_kind,
        document_dir,
        persisted_meta,
    )
    marker = _build_published_marker(
        core,
        ticker,
        document_id,
        resolved_source_kind,
        revision,
        is_deleted,
    )
    open_files: list[_OpenSnapshotFile] = []
    try:
        for descriptor in files:
            physical_path = document_dir / descriptor.name
            core._require_contained_regular_file(
                physical_path,
                document_dir,
                label=f"source snapshot file {descriptor.name}",
            )
            stream = _open_binary_file(
                physical_path,
                action="打开 source snapshot published 文件",
            )
            try:
                initial_state = _read_stable_file_state(stream)
            except BaseException as initial_state_error:
                try:
                    stream.close()
                except BaseException as close_error:
                    _append_secondary_error_note(
                        initial_state_error,
                        close_error,
                        action=(
                            "source snapshot initial descriptor cleanup failed"
                        ),
                    )
                _raise_path_free_error(initial_state_error)
            open_files.append(
                _OpenSnapshotFile(
                    descriptor=descriptor,
                    stream=stream,
                    initial_state=initial_state,
                )
            )
    except BaseException as acquire_error:
        _cleanup_snapshot_attempt(
            open_files,
            temp_root=None,
            primary_error=acquire_error,
            retain_temp_on_success=False,
        )
        raise
    return _AcquiredSnapshotAttempt(
        ticker=ticker,
        document_id=document_id,
        source_kind=resolved_source_kind,
        source_meta=_source_meta_without_revision(persisted_meta),
        provenance=provenance,
        revision=revision,
        files=files,
        primary_filename=primary_filename,
        marker=marker,
        open_files=open_files,
    )


def _resolve_snapshot_source_kind_unguarded(
    core: _FsSourceDocumentMixin,
    ticker: str,
    document_id: str,
    source_kind: Optional[SourceKind],
) -> SourceKind:
    """在同一 publication guard 内解析 snapshot source kind。

    Args:
        core: 当前 filesystem storage core。
        ticker: exact external ticker。
        document_id: exact external document ID。
        source_kind: 可选显式 source kind。

    Returns:
        唯一存在的 source kind，或显式 source kind。

    Raises:
        FileNotFoundError: 没有匹配 source 时抛出。
        ValueError: source kind 缺省且 filing/material 同时存在时抛出。
        OSError: descriptor 或 meta locator 校验失败时抛出。
    """

    if source_kind is not None:
        meta_path = core._source_meta_path_for_read(ticker, document_id, source_kind)
        if not meta_path.exists() and not meta_path.is_symlink():
            raise FileNotFoundError(
                f"document_id={document_id} 的 {source_kind.value} source 不存在"
            )
        return source_kind
    existing_kinds = _existing_snapshot_source_kinds_unguarded(
        core,
        ticker,
        document_id,
    )
    if not existing_kinds:
        raise FileNotFoundError(f"document_id={document_id} 的 source 不存在")
    if len(existing_kinds) != 1:
        raise ValueError("source kind 不明确：filing 与 material 同时存在")
    return existing_kinds[0]


def _existing_snapshot_source_kinds_unguarded(
    core: _FsSourceDocumentMixin,
    ticker: str,
    document_id: str,
) -> tuple[SourceKind, ...]:
    """在 caller 已持 guard 时枚举 exact identity 对应的 source kinds。

    Args:
        core: 当前 filesystem storage core。
        ticker: exact external ticker。
        document_id: exact external document ID。

    Returns:
        具有 meta locator 的 source kind 元组。

    Raises:
        ValueError: descriptor 或 meta locator 非法时抛出。
        OSError: descriptor 读取失败时抛出。
    """

    result: list[SourceKind] = []
    for candidate in (SourceKind.FILING, SourceKind.MATERIAL):
        meta_path = core._source_meta_path_for_read(ticker, document_id, candidate)
        if meta_path.exists() or meta_path.is_symlink():
            result.append(candidate)
    return tuple(result)


def _parse_snapshot_files(
    core: _FsSourceDocumentMixin,
    ticker: str,
    source_kind: SourceKind,
    document_dir: Path,
    persisted_meta: Mapping[str, JsonValue],
) -> tuple[tuple[SourceSnapshotFileDescriptor, ...], str]:
    """解析 typed 文件描述符并验证 physical/meta 双向一致。

    Args:
        core: 当前 filesystem storage core。
        ticker: exact external ticker。
        source_kind: 已解析 source kind。
        document_dir: 已验证 identity directory。
        persisted_meta: 同版 persisted source meta。

    Returns:
        meta 顺序下的完整文件描述符与 exact primary filename。

    Raises:
        FileNotFoundError: primary 未命中 files 时抛出。
        ValueError: files、filename、URI、字段类型或 physical 集合非法时抛出。
        OSError: physical directory 枚举或 containment 校验失败时抛出。
    """

    raw_files = persisted_meta.get("files")
    if not isinstance(raw_files, list) or not raw_files:
        raise ValueError("source snapshot files 必须为非空数组")
    descriptors: list[SourceSnapshotFileDescriptor] = []
    file_names: set[str] = set()
    ticker_dir = core._ticker_dir_for_read(ticker)
    for raw_file in raw_files:
        if not isinstance(raw_file, Mapping):
            raise ValueError("source snapshot files 条目必须为 object")
        file_payload: dict[str, JsonValue] = dict(raw_file)
        raw_name = file_payload.get("name")
        if not isinstance(raw_name, str):
            raise ValueError("source snapshot file.name 必须为字符串")
        name = _normalize_filename(raw_name)
        if name != raw_name or name in file_names:
            raise ValueError("source snapshot file.name 非法或重复")
        file_names.add(name)
        file_meta = _file_object_meta_from_dict(file_payload)
        expected_path = document_dir / name
        resolved_uri_path = _local_path_from_uri(core.portfolio_root, file_meta.uri)
        if resolved_uri_path != expected_path:
            raise ValueError("source snapshot file URI 与 physical identity 不一致")
        core._require_contained_regular_file(
            expected_path,
            ticker_dir,
            label=f"source snapshot file {name}",
        )
        descriptors.append(
            SourceSnapshotFileDescriptor(
                name=name,
                etag=file_meta.etag,
                last_modified=file_meta.last_modified,
                size=file_meta.size,
                content_type=file_meta.content_type,
                sha256=file_meta.sha256,
            )
        )
    physical_names: set[str] = set()
    for child in _list_directory(
        document_dir,
        action="枚举 source snapshot published directory",
    ):
        if child.name in {"meta.json", _IDENTITY_DESCRIPTOR_FILENAME}:
            continue
        if child.is_symlink() or not child.is_file():
            raise ValueError("source snapshot 目录只允许已声明 regular file")
        physical_names.add(child.name)
    if physical_names != file_names:
        raise ValueError("source snapshot files 与 physical business files 不双向一致")
    raw_primary = persisted_meta.get("primary_document")
    if not isinstance(raw_primary, str) or not raw_primary:
        raise ValueError("source snapshot primary_document 必须为非空字符串")
    primary_filename = _normalize_filename(raw_primary)
    if primary_filename != raw_primary or primary_filename not in file_names:
        raise FileNotFoundError("source snapshot primary_document 未精确命中 files")
    return tuple(descriptors), primary_filename


def _build_published_marker(
    core: _FsSourceDocumentMixin,
    ticker: str,
    document_id: str,
    source_kind: SourceKind,
    revision: SourceDocumentRevision,
    is_deleted: bool,
) -> _PublishedSnapshotMarker:
    """读取已验证 mapping descriptor 内容并构造内部 marker。

    Args:
        core: 当前 filesystem storage core。
        ticker: exact external ticker。
        document_id: exact external document ID。
        source_kind: 已解析 source kind。
        revision: persisted opaque revision。
        is_deleted: persisted deletion flag。

    Returns:
        仅供后验 exact equality 比较的内部 marker。

    Raises:
        OSError: descriptor 文件读取失败时抛出。
    """

    ticker_dir = core._ticker_dir_for_read(ticker)
    document_dir = core._source_meta_path_for_read(
        ticker,
        document_id,
        source_kind,
    ).parent
    return _PublishedSnapshotMarker(
        source_kind=source_kind,
        revision=revision,
        is_deleted=is_deleted,
        ticker_descriptor=_read_file_bytes(
            ticker_dir / _IDENTITY_DESCRIPTOR_FILENAME,
            action="读取 source snapshot ticker descriptor marker",
        ),
        document_descriptor=_read_file_bytes(
            document_dir / _IDENTITY_DESCRIPTOR_FILENAME,
            action="读取 source snapshot document descriptor marker",
        ),
    )


def _read_published_marker(
    core: _FsSourceDocumentMixin,
    ticker: str,
    document_id: str,
    source_kind: SourceKind,
) -> Optional[_PublishedSnapshotMarker]:
    """在一次短 publication guard 内读取 attempt 已选 kind 的 marker。

    Args:
        core: 当前 filesystem storage core。
        ticker: exact external ticker。
        document_id: exact external document ID。
        source_kind: 首次 acquire 已经选定的 exact source kind。

    Returns:
        当前 kind 的 marker；source 已被 reset 时返回 ``None``。

    Raises:
        ValueError: descriptor、meta、revision 或 deletion 字段非法时抛出。
        RuntimeError: publication guard 操作失败时抛出。
        OSError: descriptor 或 meta 读取失败时抛出。
    """

    guard_token = core._acquire_publication_guard(ticker)
    marker: Optional[_PublishedSnapshotMarker] = None
    marker_error: Optional[BaseException] = None
    try:
        meta_path = core._source_meta_path_for_read(
            ticker,
            document_id,
            source_kind,
        )
        if not meta_path.exists() and not meta_path.is_symlink():
            marker = None
        else:
            if meta_path.is_symlink() or not meta_path.is_file():
                raise ValueError("source snapshot meta 必须为 non-symlink regular file")
            persisted_meta = core._get_persisted_source_meta_unguarded(
                ticker,
                document_id,
                source_kind,
            )
            revision = _source_revision_from_meta(persisted_meta)
            marker = _build_published_marker(
                core,
                ticker,
                document_id,
                source_kind,
                revision,
                require_source_meta_is_deleted(persisted_meta),
            )
    except BaseException as exc:
        marker_error = exc
    try:
        core._release_lock_token(guard_token)
    except BaseException as release_error:
        if marker_error is not None:
            _append_secondary_error_note(
                marker_error,
                release_error,
                action="source snapshot marker publication guard release failed",
            )
        else:
            raise
    if marker_error is not None:
        _raise_path_free_error(marker_error)
    return marker


def _read_stable_file_state(stream: BinaryIO) -> _StableFileState:
    """从已打开文件描述符读取 regular inode 稳定属性。

    Args:
        stream: publication guard 内打开的二进制文件流。

    Returns:
        不包含 path 的 inode 属性快照。

    Raises:
        ValueError: 文件描述符不指向 regular file 时抛出。
        OSError: ``fstat`` 失败时抛出 path-free 文件系统异常。
    """

    try:
        file_stat = os.fstat(stream.fileno())
    except OSError as exc:
        _raise_path_free_error(
            _project_filesystem_error(exc, action="读取 source snapshot 文件描述符属性")
        )
    if not stat.S_ISREG(file_stat.st_mode):
        raise ValueError("source snapshot 文件描述符必须指向 regular file")
    return _StableFileState(
        device=file_stat.st_dev,
        inode=file_stat.st_ino,
        mode=file_stat.st_mode,
        size=file_stat.st_size,
        modified_ns=file_stat.st_mtime_ns,
        changed_ns=file_stat.st_ctime_ns,
    )


def _copy_snapshot_files(
    open_files: list[_OpenSnapshotFile],
    temp_root: Path,
) -> None:
    """从一次 attempt 的全部已打开 descriptors 复制业务文件。

    Args:
        open_files: publication guard 内打开的完整业务文件集合。
        temp_root: 当前 attempt 私有临时根。

    Returns:
        无。

    Raises:
        ValueError: inode、EOF、size 或内容摘要与声明不一致时抛出。
        OSError: descriptor 读取或临时文件写入失败时抛出 path-free 异常。
    """

    for opened_file in open_files:
        _copy_snapshot_file(opened_file, temp_root)


def _copy_snapshot_file(
    opened_file: _OpenSnapshotFile,
    temp_root: Path,
) -> None:
    """复制单个已打开 inode 并验证 copy 前后静态完整性。

    Args:
        opened_file: 当前业务文件的 descriptor、stream 与初始 ``fstat``。
        temp_root: 当前 attempt 私有临时根。

    Returns:
        无。

    Raises:
        ValueError: inode、EOF、size 或内容摘要与声明不一致时抛出。
        OSError: descriptor 读取或临时文件写入失败时抛出 path-free 异常。
    """

    descriptor = opened_file.descriptor
    try:
        opened_file.stream.seek(0)
        target_stream = (temp_root / descriptor.name).open("xb")
    except OSError as exc:
        _raise_path_free_error(
            _project_filesystem_error(exc, action="准备 source snapshot 临时文件")
        )
    digest = hashlib.sha256()
    copied_size = 0
    try:
        with target_stream:
            while True:
                chunk = opened_file.stream.read(_COPY_CHUNK_SIZE)
                if not chunk:
                    break
                target_stream.write(chunk)
                digest.update(chunk)
                copied_size += len(chunk)
    except OSError as exc:
        _raise_path_free_error(
            _project_filesystem_error(exc, action="复制 source snapshot 文件")
        )
    final_state = _read_stable_file_state(opened_file.stream)
    if final_state != opened_file.initial_state:
        raise ValueError("source snapshot 已打开文件在复制期间发生静态 inode 变化")
    if copied_size != opened_file.initial_state.size:
        raise ValueError("source snapshot 文件 EOF 与已打开 inode 大小不一致")
    if descriptor.size is not None and copied_size != descriptor.size:
        raise ValueError("source snapshot 文件大小与 source meta 不一致")
    if descriptor.sha256 is not None and digest.hexdigest() != descriptor.sha256:
        raise ValueError("source snapshot 文件内容与 source meta 摘要不一致")


def _create_snapshot_temp_root() -> Path:
    """创建一次 full snapshot attempt 私有临时根。

    Args:
        无。

    Returns:
        新建且尚无业务文件的临时目录。

    Raises:
        OSError: 临时目录创建失败时抛出 path-free 文件系统异常。
    """

    try:
        return Path(tempfile.mkdtemp(prefix="dayu-source-snapshot-"))
    except OSError as exc:
        _raise_path_free_error(
            _project_filesystem_error(exc, action="创建 source snapshot 临时目录")
        )


def _remove_snapshot_temp_root(temp_root: Path) -> None:
    """删除一次 snapshot attempt 或 resource 的完整临时树。

    Args:
        temp_root: storage owner 创建的私有临时根。

    Returns:
        无。

    Raises:
        OSError: 临时树删除失败时抛出 path-free 文件系统异常。
    """

    try:
        shutil.rmtree(temp_root)
    except FileNotFoundError:
        return
    except OSError as exc:
        _raise_path_free_error(
            _project_filesystem_error(exc, action="删除 source snapshot 临时目录")
        )


def _cleanup_snapshot_attempt(
    open_files: list[_OpenSnapshotFile],
    *,
    temp_root: Optional[Path],
    primary_error: Optional[BaseException],
    retain_temp_on_success: bool,
) -> None:
    """按统一主次失败规则释放一次 snapshot attempt 的全部资源。

    Args:
        open_files: 当前 attempt 仍持有的 published 文件描述符。
        temp_root: 当前 attempt 已创建的私有临时树；尚未创建时为 ``None``。
        primary_error: copy、marker、corruption 等 authoritative 主失败；无主失败时为
            ``None``。
        retain_temp_on_success: FD cleanup 全部成功时是否把临时树交给返回的 snapshot。

    Returns:
        cleanup 全部成功，或次级失败已安全附加到既有主异常时返回。

    Raises:
        BaseException: 没有既有主失败时，以首个 cleanup 失败为主异常抛出。
    """

    cleanup_primary: Optional[BaseException] = None
    try:
        _close_open_snapshot_files(open_files)
    except BaseException as close_error:
        if primary_error is not None:
            _append_secondary_error_note(
                primary_error,
                close_error,
                action="source snapshot published descriptor cleanup failed",
            )
        else:
            cleanup_primary = close_error

    should_remove_temp = temp_root is not None and (
        not retain_temp_on_success
        or primary_error is not None
        or cleanup_primary is not None
    )
    if should_remove_temp and temp_root is not None:
        try:
            _remove_snapshot_temp_root(temp_root)
        except BaseException as remove_error:
            note_owner = primary_error or cleanup_primary
            if note_owner is None:
                cleanup_primary = remove_error
            else:
                _append_secondary_error_note(
                    note_owner,
                    remove_error,
                    action="source snapshot temporary tree cleanup failed",
                )

    if primary_error is None and cleanup_primary is not None:
        _raise_path_free_error(cleanup_primary)


def _close_open_snapshot_files(open_files: list[_OpenSnapshotFile]) -> None:
    """关闭一次 attempt 持有的全部 published 文件描述符。

    Args:
        open_files: 当前 attempt 的可变 descriptor 列表。

    Returns:
        无。

    Raises:
        OSError: 文件描述符关闭失败时抛出 path-free 文件系统异常。
    """

    first_error: Optional[OSError] = None
    while open_files:
        opened_file = open_files.pop()
        try:
            opened_file.stream.close()
        except OSError as exc:
            if first_error is None:
                first_error = _project_filesystem_error(
                    exc,
                    action="关闭 source snapshot published 文件描述符",
                )
    if first_error is not None:
        _raise_path_free_error(first_error)
