"""共享文档处理器的轻量确定性 fixture 测试。"""

from __future__ import annotations

import io
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import BinaryIO

import pytest

from docling_core.types.doc.document import (
    DoclingDocument,
    ProvenanceItem,
    RefItem,
    SectionHeaderItem,
    TableCell,
    TableData,
    TableItem,
    TextItem,
)
from docling_core.types.doc.base import BoundingBox
from docling_core.types.doc.labels import DocItemLabel

from dayu.documents.processors import build_documents_processor_registry
from dayu.documents.processors._doc_processor_factory import create_doc_file_processor
from dayu.documents.processors.bs_processor import BSProcessor
from dayu.documents.processors.docling_processor import DoclingProcessor
from dayu.documents.processors.local_file_source import LocalFileSource
from dayu.documents.processors.markdown_processor import MarkdownProcessor
from dayu.documents.processors.source_snapshot import SourceSnapshot

_THREAD_SYNC_TIMEOUT_SECONDS = 5.0
_MATERIALIZE_TEST_CHUNK_BYTES = 4


@dataclass(slots=True)
class _MemorySource:
    """测试用内存 Source。"""

    payload: bytes
    uri: str = "memory.md"
    media_type: str | None = "text/markdown"
    content_length: int | None = None
    etag: str | None = None
    open_count: int = 0

    def open(self) -> BinaryIO:
        """打开 payload 的独立二进制流。

        Args:
            无。

        Returns:
            内存二进制流。

        Raises:
            无。
        """

        self.open_count += 1
        return io.BytesIO(self.payload)

    def materialize(self, suffix: str | None = None) -> Path:
        """拒绝绕过 ``open`` 的测试路径。

        Args:
            suffix: 可选后缀。

        Returns:
            不返回。

        Raises:
            AssertionError: 始终抛出，确保 snapshot 只使用 ``open``。
        """

        del suffix
        raise AssertionError("source snapshot must only depend on Source.open()")


class _FailingBinaryStream(io.BytesIO):
    """首次读取后抛出资源异常的测试流。"""

    def __init__(self) -> None:
        """初始化测试流。

        Returns:
            无。

        Raises:
            无。
        """

        super().__init__(b"prefix")
        self._read_count = 0

    def read(self, size: int | None = -1) -> bytes:
        """首次返回字节，后续模拟资源失败。

        Args:
            size: 最大读取字节数。

        Returns:
            首次读取的字节。

        Raises:
            OSError: 第二次读取时抛出。
        """

        self._read_count += 1
        if self._read_count > 1:
            raise OSError("synthetic source failure")
        return super().read(-1 if size is None else size)


@dataclass(frozen=True, slots=True)
class _FailingSource:
    """测试用资源失败 Source。"""

    uri: str = "failing.md"
    media_type: str | None = "text/markdown"
    content_length: int | None = None
    etag: str | None = None

    def open(self) -> BinaryIO:
        """打开会在第二次读取失败的流。

        Returns:
            测试二进制流。

        Raises:
            无。
        """

        return _FailingBinaryStream()

    def materialize(self, suffix: str | None = None) -> Path:
        """拒绝非 ``open`` 路径。

        Args:
            suffix: 可选后缀。

        Returns:
            不返回。

        Raises:
            AssertionError: 始终抛出。
        """

        del suffix
        raise AssertionError("unexpected materialize")


class _SyntheticCancellation(Exception):
    """测试用协作取消信号。"""


@dataclass(frozen=True, slots=True)
class _FailingOpenSource:
    """打开流时直接抛出指定 ``OSError`` 的测试 Source。"""

    error: OSError
    uri: str = "failing-open.md"
    media_type: str | None = "text/markdown"
    content_length: int | None = None
    etag: str | None = None

    def open(self) -> BinaryIO:
        """模拟 ``Source.open`` 失败；参数：无；返回：不返回；异常：原样抛出指定 ``OSError``。"""

        raise self.error

    def materialize(self, suffix: str | None = None) -> Path:
        """拒绝非 ``open`` 路径；参数：可选 ``suffix``；返回：不返回；异常：始终抛出 ``AssertionError``。"""

        del suffix
        raise AssertionError("unexpected materialize")


@dataclass(slots=True)
class _CancelAfterChecks:
    """达到指定检查次数后取消。"""

    remaining: int

    def __call__(self) -> None:
        """递减检查次数并在归零时抛出。

        Returns:
            无。

        Raises:
            _SyntheticCancellation: 检查次数归零时抛出。
        """

        self.remaining -= 1
        if self.remaining <= 0:
            raise _SyntheticCancellation("cancel source snapshot copy")


@dataclass(slots=True)
class _SpoolRecorder:
    """记录测试中唯一创建的内存 spool。"""

    spool: io.BytesIO | None = None

    def __call__(self, *, max_size: int, mode: str) -> io.BytesIO:
        """创建 spool；参数：内存阈值 ``max_size`` 与模式 ``mode``；返回：可观察的内存流；异常：无。"""

        del max_size, mode
        self.spool = io.BytesIO()
        return self.spool


class _ConcurrentSpoolProbe(io.BytesIO):
    """只为 reader/close 串行化测试提供锁与 spool 观察点。"""

    def __init__(self) -> None:
        """初始化同步状态；参数：无；返回：无；异常：无。"""

        super().__init__()
        self._lock = threading.Lock()
        self._acquire_count = 0
        self._owner_ident: int | None = None
        self.second_acquire_started = threading.Event()
        self.read_entered = threading.Event()
        self.allow_read = threading.Event()
        self.close_under_owner_lock: bool | None = None

    def __call__(self, *, max_size: int, mode: str) -> _ConcurrentSpoolProbe:
        """返回 probe；参数：内存阈值 ``max_size`` 与模式 ``mode``；返回：自身；异常：无。"""

        del max_size, mode
        return self

    def __enter__(self) -> _ConcurrentSpoolProbe:
        """进入 owner 锁；参数：无；返回：自身；异常：无。"""

        self._acquire_count += 1
        if self._acquire_count == 2:
            self.second_acquire_started.set()
        self._lock.acquire()
        self._owner_ident = threading.get_ident()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """释放 owner 锁；参数：异常类型、实例与 traceback；返回：无；异常：无。"""

        del exc_type, exc, traceback
        self._owner_ident = None
        self._lock.release()

    def read(self, size: int | None = -1) -> bytes:
        """阻塞读取；参数：最大字节数 ``size``；返回：放行后的字节；异常：超时或提前关闭时抛出。"""

        self.read_entered.set()
        if not self.allow_read.wait(_THREAD_SYNC_TIMEOUT_SECONDS):
            raise AssertionError("timed out waiting to release snapshot read")
        return super().read(-1 if size is None else size)

    def close(self) -> None:
        """记录并关闭；参数：无；返回：无；异常：无。"""

        if not self.closed:
            self.close_under_owner_lock = self._owner_ident == threading.get_ident()
        super().close()


class _FailingMaterializedOutput:
    """仅为 output.write 失败测试写入部分字节后抛错。"""

    def __init__(self, path: Path, write_error: OSError) -> None:
        """保存失败写入；参数：输出 ``path`` 与 ``write_error``；返回：无；异常：无。"""

        self.name = str(path)
        self.bytes_written = 0
        self._path = path
        self._write_error = write_error
        self._stream: BinaryIO | None = None

    def __call__(
        self,
        *,
        mode: str,
        prefix: str,
        suffix: str,
        delete: bool,
    ) -> _FailingMaterializedOutput:
        """打开固定路径；参数：NamedTemporaryFile 四个显式参数；返回：自身；异常：打开失败时抛出 ``OSError``。"""

        del mode, prefix, suffix, delete
        self._stream = self._path.open("w+b")
        return self

    def __enter__(self) -> _FailingMaterializedOutput:
        """进入输出上下文；参数：无；返回：自身；异常：无。"""

        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """关闭输出；参数：异常类型、实例与 traceback；返回：无；异常：关闭失败时抛出 ``OSError``。"""

        del exc_type, exc, traceback
        if self._stream is not None:
            self._stream.close()

    def write(self, data: bytes) -> int:
        """写入 partial；参数：字节 ``data``；返回：不返回；异常：未打开时 ``RuntimeError``，否则指定 ``OSError``。"""

        stream = self._stream
        if stream is None:
            raise RuntimeError("failing materialized output is not open")
        partial_length = max(1, len(data) // 2)
        written = stream.write(data[:partial_length])
        stream.flush()
        self.bytes_written += written
        raise self._write_error


def _source_for(path: Path, media_type: str) -> LocalFileSource:
    """构造本地文件 Source。

    :param path: fixture 文件路径。
    :param media_type: 文件媒体类型。
    :returns: 本地文件 Source。
    """

    return LocalFileSource(path=path, uri=str(path), media_type=media_type)


def _ref_item(ref: str) -> RefItem:
    """按 Docling JSON alias 构造引用对象。

    :param ref: Docling 内部引用，例如 ``#/body``。
    :returns: 引用对象。
    """

    return RefItem.model_validate({"$ref": ref})


def _caption_text_item(index: int, text: str) -> TextItem:
    """构造真实 Docling caption 文本项。

    Args:
        index: 文本项在 ``DoclingDocument.texts`` 中的索引。
        text: caption 原始文本。

    Returns:
        带稳定内部引用的 Docling 文本项。

    Raises:
        pydantic.ValidationError: 输入不能构成合法 Docling 文本项时抛出。
    """

    return TextItem(
        self_ref=f"#/texts/{index}",
        parent=_ref_item("#/body"),
        orig=text,
        text=text,
        label=DocItemLabel.CAPTION,
    )


def _caption_test_table_data() -> TableData:
    """构造 caption 公共契约测试共用的真实表格数据。

    Args:
        无。

    Returns:
        包含表头和一行数据的 Docling 表格数据。

    Raises:
        pydantic.ValidationError: 固定表格数据不符合 Docling 模型时抛出。
    """

    return TableData(
        num_rows=2,
        num_cols=2,
        table_cells=[
            TableCell(
                start_row_offset_idx=0,
                end_row_offset_idx=1,
                start_col_offset_idx=0,
                end_col_offset_idx=1,
                text="Metric",
                column_header=True,
            ),
            TableCell(
                start_row_offset_idx=0,
                end_row_offset_idx=1,
                start_col_offset_idx=1,
                end_col_offset_idx=2,
                text="2025",
                column_header=True,
            ),
            TableCell(
                start_row_offset_idx=1,
                end_row_offset_idx=2,
                start_col_offset_idx=0,
                end_col_offset_idx=1,
                text="Revenue",
            ),
            TableCell(
                start_row_offset_idx=1,
                end_row_offset_idx=2,
                start_col_offset_idx=1,
                end_col_offset_idx=2,
                text="100",
            ),
        ],
    )


def _save_docling_caption_document(
    tmp_path: Path,
    *,
    name: str,
    caption_items: list[TextItem],
    caption_refs: list[RefItem],
    table_provenance: list[ProvenanceItem] | None = None,
) -> Path:
    """通过公开 Docling 模型保存 caption 测试文档。

    Args:
        tmp_path: pytest 临时目录。
        name: 文档与输出文件的稳定名称。
        caption_items: 保存在文档文本集合中的 caption 文本项。
        caption_refs: 按作者顺序写入表格的 caption 引用。
        table_provenance: 可选的真实表格页级来源信息。

    Returns:
        由 ``DoclingDocument.save_as_json`` 写出的 JSON 路径。

    Raises:
        OSError: 保存测试文档失败时抛出。
        pydantic.ValidationError: 输入不能构成合法 Docling 文档时抛出。
    """

    docling_path = tmp_path / f"{name}_docling.json"
    parent_ref = _ref_item("#/body")
    header = SectionHeaderItem(
        self_ref="#/texts/0",
        parent=parent_ref,
        orig="Financial Review",
        text="Financial Review",
        level=1,
    )
    table = TableItem(
        self_ref="#/tables/0",
        parent=parent_ref,
        captions=caption_refs,
        prov=[] if table_provenance is None else table_provenance,
        data=_caption_test_table_data(),
    )
    document = DoclingDocument(
        name=name,
        texts=[header, *caption_items],
        tables=[table],
    )
    document.body.children = [
        _ref_item("#/texts/0"),
        _ref_item("#/tables/0"),
    ]
    document.save_as_json(docling_path)
    return docling_path


def _caption_from_public_views(docling_path: Path) -> tuple[str | None, str | None]:
    """从两个公开表格视图读取同一 caption 投影。

    Args:
        docling_path: 真实 Docling JSON 文档路径。

    Returns:
        ``list_tables`` 与 ``read_table`` 返回的 caption 二元组。

    Raises:
        RuntimeError: Docling 文档加载或公开表格读取失败时抛出。
    """

    processor = DoclingProcessor(_source_for(docling_path, "application/json"))
    return (
        processor.list_tables()[0]["caption"],
        processor.read_table("t_0001")["caption"],
    )


def test_documents_processor_registry_registers_default_processors() -> None:
    """documents 默认注册表应保持通用处理器注册行为不变。"""

    registry = build_documents_processor_registry()

    assert registry.list_processors() == [
        {"name": "docling_processor", "class": "DoclingProcessor", "priority": 10},
        {"name": "markdown_processor", "class": "MarkdownProcessor", "priority": 10},
        {"name": "bs_processor", "class": "BSProcessor", "priority": 10},
    ]


def test_source_snapshot_copies_unknown_length_to_eof_with_independent_cursors() -> None:
    """验证未知长度来源复制到真实 EOF，并提供位置互不影响的独立游标。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 快照长度、游标、生命周期或打开次数不符合约定时抛出。
    """

    payload = b"0123456789" * 20_000
    source = _MemorySource(payload=payload)
    snapshot = SourceSnapshot(source)

    assert snapshot.content_length is None
    with snapshot:
        assert snapshot.content_length == len(payload)
        assert snapshot.snapshot_size == len(payload)
        with snapshot.open() as first, snapshot.open() as second:
            assert first.read(17) == payload[:17]
            assert second.read(9) == payload[:9]
            assert first.tell() == 17
            assert second.tell() == 9
            assert second.seek(-10, io.SEEK_END) == len(payload) - 10
            assert second.read() == payload[-10:]
            assert first.read() == payload[17:]

    assert source.open_count == 1
    with pytest.raises(ValueError, match="not active"):
        snapshot.open()
    with pytest.raises(RuntimeError, match="cannot be reused"):
        snapshot.__enter__()
    snapshot.close()
    snapshot.close()


def test_source_snapshot_close_serializes_inflight_read_and_actual_close(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """验证 read、active detach 与实际 close 由同一把锁确定性串行化。

    Args:
        monkeypatch: pytest monkeypatch fixture。

    Returns:
        无。

    Raises:
        AssertionError: close 未等待临界区读取、未持锁关闭或关闭后错误不稳定时抛出。
    """

    payload = b"deterministic concurrent snapshot read"
    spool = _ConcurrentSpoolProbe()
    monkeypatch.setattr(
        "dayu.documents.processors.source_snapshot.tempfile.SpooledTemporaryFile",
        spool,
    )
    snapshot = SourceSnapshot(_MemorySource(payload=payload))
    snapshot.__enter__()
    monkeypatch.setattr(snapshot, "_lock", spool)
    reader = snapshot.open()
    with ThreadPoolExecutor(max_workers=2) as executor:
        read_future = executor.submit(reader.read)
        assert spool.read_entered.wait(_THREAD_SYNC_TIMEOUT_SECONDS)
        close_future = executor.submit(snapshot.close)
        try:
            assert spool.second_acquire_started.wait(_THREAD_SYNC_TIMEOUT_SECONDS)
            assert close_future.done() is False
            assert spool.closed is False
        finally:
            spool.allow_read.set()
        assert read_future.result(timeout=_THREAD_SYNC_TIMEOUT_SECONDS) == payload
        close_future.result(timeout=_THREAD_SYNC_TIMEOUT_SECONDS)

    snapshot.close()
    assert spool.close_under_owner_lock is True
    with pytest.raises(ValueError, match="source snapshot is not active"):
        reader.read(1)
    reader.close()


def test_source_snapshot_empty_source_has_exact_eof_and_materialization() -> None:
    """验证空 Source 的精确长度、EOF、SEEK_END、空物化文件与清理。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 空快照的读取、物化或清理语义不符合约定时抛出。
    """

    snapshot = SourceSnapshot(_MemorySource(payload=b"", content_length=0))
    with snapshot:
        assert snapshot.snapshot_size == 0
        assert snapshot.content_length == 0
        with snapshot.open() as reader:
            assert reader.read() == b""
            assert reader.seek(0, io.SEEK_END) == 0
            assert reader.tell() == 0
            assert reader.read(1) == b""
        materialized_path = snapshot.materialize(suffix=".empty")
        assert materialized_path.read_bytes() == b""

    assert not materialized_path.exists()


def test_source_snapshot_ignores_declared_length_and_feeds_processor() -> None:
    """验证声明长度只作 metadata，完整快照进入处理器且不重开来源。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: metadata、处理器结果或打开次数不符合约定时抛出。
    """

    payload = b"# Overview\nRevenue grew.\n"
    declared_length = len(payload) * 100_000
    source = _MemorySource(payload=payload, content_length=declared_length)
    snapshot = SourceSnapshot(source)

    assert snapshot.content_length == declared_length
    with snapshot:
        assert snapshot.content_length == len(payload)
        with snapshot.open() as reader:
            assert reader.readable() is True
            assert reader.seekable() is True
            assert reader.seek(2) == 2
            assert reader.tell() == 2
            assert reader.seek(0) == 0
            assert reader.read() == payload
        processor = create_doc_file_processor(snapshot)
        assert processor is not None
        assert processor.list_sections()[0]["title"] == "Overview"

    assert source.open_count == 1


def test_source_snapshot_cleans_materialized_file_after_python_exception() -> None:
    """验证普通 Python exception 会清理 snapshot 拥有的物化文件。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 物化文件未按生命周期清理时抛出。
    """

    source = _MemorySource(payload=b"# Overview\n")
    materialized_path: Path | None = None

    with pytest.raises(RuntimeError, match="consumer failure"):
        with SourceSnapshot(source) as snapshot:
            materialized_path = snapshot.materialize(suffix=".md")
            assert materialized_path.name.startswith("dayu-doc-source-")
            assert materialized_path.exists()
            raise RuntimeError("consumer failure")

    assert materialized_path is not None
    assert not materialized_path.exists()


def test_source_snapshot_cleans_materialized_file_on_normal_exit() -> None:
    """验证正常退出 context 会清理并只复用一个物化文件。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 物化路径复用或清理行为不符合约定时抛出。
    """

    source = _MemorySource(payload=b"# Overview\n")
    with SourceSnapshot(source) as snapshot:
        materialized_path = snapshot.materialize(suffix=".md")
        assert snapshot.materialize(suffix=".txt") == materialized_path
        assert materialized_path.exists()

    assert not materialized_path.exists()


def test_source_snapshot_materialize_observes_cancellation_and_cleans_resources(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """验证物化复制持续观察同一取消检查并清理 partial 文件与 spool。

    Args:
        tmp_path: pytest 临时目录。
        monkeypatch: pytest monkeypatch fixture。

    Returns:
        无。

    Raises:
        AssertionError: 取消未原样透出或临时资源未清理时抛出。
    """

    payload = b"abcdefghijkl"
    cancellation_error = _SyntheticCancellation("cancel materialized source copy")
    cancellation_enabled = False
    checks_before_enable = 0
    materialize_checks = 0
    observed_partial_path: Path | None = None
    spool_recorder = _SpoolRecorder()

    def cancellation_check() -> None:
        """在第三次物化检查时记录真实 partial path 并取消。

        Args:
            无。

        Returns:
            无。

        Raises:
            _SyntheticCancellation: 第三次物化检查时原样抛出指定取消异常。
            AssertionError: 取消点未观察到唯一真实临时文件时抛出。
        """

        nonlocal checks_before_enable, materialize_checks, observed_partial_path
        if not cancellation_enabled:
            checks_before_enable += 1
            return
        materialize_checks += 1
        if materialize_checks < 3:
            return
        partial_paths = list(tmp_path.glob("dayu-doc-source-*.partial"))
        assert len(partial_paths) == 1
        observed_partial_path = partial_paths[0]
        assert observed_partial_path.exists()
        raise cancellation_error

    monkeypatch.setattr(
        "dayu.documents.processors.source_snapshot._COPY_CHUNK_BYTES",
        _MATERIALIZE_TEST_CHUNK_BYTES,
    )
    monkeypatch.setattr(
        "dayu.documents.processors.source_snapshot.tempfile.SpooledTemporaryFile",
        spool_recorder,
    )
    monkeypatch.setattr(
        "dayu.documents.processors.source_snapshot.tempfile.tempdir",
        str(tmp_path),
    )

    with pytest.raises(_SyntheticCancellation) as raised:
        with SourceSnapshot(
            _MemorySource(payload=payload),
            cancellation_check=cancellation_check,
        ) as snapshot:
            cancellation_enabled = True
            snapshot.materialize(suffix=".partial")

    assert raised.value is cancellation_error
    assert checks_before_enable > 0
    assert materialize_checks == 3
    assert observed_partial_path is not None
    assert not observed_partial_path.exists()
    assert spool_recorder.spool is not None
    assert spool_recorder.spool.closed is True


def test_source_snapshot_open_oserror_is_preserved_and_closes_spool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """验证 ``Source.open`` 的 ``OSError`` 原样透出且未发布 spool 被关闭。

    Args:
        monkeypatch: pytest monkeypatch fixture。

    Returns:
        无。

    Raises:
        AssertionError: 异常身份或 spool 清理不符合约定时抛出。
    """

    open_error = OSError("synthetic source open failure")
    spool_recorder = _SpoolRecorder()
    monkeypatch.setattr(
        "dayu.documents.processors.source_snapshot.tempfile.SpooledTemporaryFile",
        spool_recorder,
    )

    with pytest.raises(OSError) as raised:
        with SourceSnapshot(_FailingOpenSource(open_error)):
            pytest.fail("open failure must not publish a snapshot")

    assert raised.value is open_error
    assert spool_recorder.spool is not None
    assert spool_recorder.spool.closed is True


def test_source_snapshot_materialize_write_oserror_removes_partial_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """验证物化写入 ``OSError`` 原样透出并删除已写入的 partial 路径。

    Args:
        tmp_path: pytest 临时目录。
        monkeypatch: pytest monkeypatch fixture。

    Returns:
        无。

    Raises:
        AssertionError: 异常身份、partial 写入或路径清理不符合约定时抛出。
    """

    payload = b"materialized output payload"
    write_error = OSError("synthetic materialized output failure")
    partial_path = tmp_path / "failed-materialized.partial"
    output = _FailingMaterializedOutput(partial_path, write_error)
    monkeypatch.setattr(
        "dayu.documents.processors.source_snapshot.tempfile.NamedTemporaryFile",
        output,
    )

    with SourceSnapshot(_MemorySource(payload=payload)) as snapshot:
        with pytest.raises(OSError) as raised:
            snapshot.materialize(suffix=".partial")

    assert raised.value is write_error
    assert 0 < output.bytes_written < len(payload)
    assert not partial_path.exists()


@pytest.mark.parametrize(
    ("source", "cancellation_check", "expected_exception"),
    (
        (_FailingSource(), None, OSError),
        (_MemorySource(payload=b"payload"), _CancelAfterChecks(2), _SyntheticCancellation),
    ),
)
def test_source_snapshot_closes_spool_on_io_failure_or_cancellation(
    monkeypatch: pytest.MonkeyPatch,
    source: _MemorySource | _FailingSource,
    cancellation_check: Callable[[], None] | None,
    expected_exception: type[BaseException],
) -> None:
    """验证 Source I/O 失败与协作取消都会关闭未发布 spool。

    Args:
        monkeypatch: pytest monkeypatch fixture。
        source: 测试 Source。
        cancellation_check: 可选协作取消检查。
        expected_exception: 预期透出的异常类型。

    Returns:
        无。

    Raises:
        AssertionError: 异常未透出或 spool 未关闭时抛出。
    """

    spool_recorder = _SpoolRecorder()

    monkeypatch.setattr(
        "dayu.documents.processors.source_snapshot.tempfile.SpooledTemporaryFile",
        spool_recorder,
    )

    with pytest.raises(expected_exception):
        with SourceSnapshot(
            source,
            cancellation_check=cancellation_check,
        ):
            pytest.fail("failure path must not publish a snapshot")

    assert spool_recorder.spool is not None
    assert spool_recorder.spool.closed is True


def test_markdown_processor_sections_tables_and_search(tmp_path: Path) -> None:
    """Markdown 处理器应稳定产出章节、表格与搜索片段。"""

    markdown_path = tmp_path / "sample.md"
    markdown_path.write_text(
        "\n".join(
            [
                "# Overview",
                "Revenue grew quickly.",
                "",
                "| Metric | Value |",
                "| --- | ---: |",
                "| Revenue | 100 |",
                "",
                "## Details",
                "Margin improved.",
            ]
        ),
        encoding="utf-8",
    )

    processor = MarkdownProcessor(_source_for(markdown_path, "text/markdown"))

    sections = processor.list_sections()
    assert [section["ref"] for section in sections] == ["s_0001", "s_0002"]
    assert sections[0]["title"] == "Overview"
    assert sections[1]["parent_ref"] == "s_0001"

    tables = processor.list_tables()
    assert tables[0]["table_ref"] == "t_0001"
    assert tables[0]["headers"] == ["Metric", "Value"]

    section = processor.read_section("s_0001")
    assert "Revenue grew quickly." in section["content"]
    assert section["tables"] == ["t_0001"]

    table = processor.read_table("t_0001")
    assert table["columns"] == ["Metric", "Value"]
    assert table["data"] == [{"Metric": "Revenue", "Value": "100"}]

    hits = processor.search("Revenue")
    assert hits
    assert hits[0].get("section_ref") == "s_0001"
    assert "Revenue" in str(hits[0].get("snippet", ""))


def test_html_processor_sections_tables_and_search(tmp_path: Path) -> None:
    """HTML 处理器应稳定产出章节、表格 records 与搜索片段。"""

    html_path = tmp_path / "sample.html"
    html_path.write_text(
        (
            "<html><body>"
            "<h1>Overview</h1>"
            "<p>Revenue grew quickly.</p>"
            "<table>"
            "<tr><th>Metric</th><th>Value</th></tr>"
            "<tr><td>Revenue</td><td>100</td></tr>"
            "</table>"
            "</body></html>"
        ),
        encoding="utf-8",
    )

    processor = BSProcessor(_source_for(html_path, "text/html"))

    sections = processor.list_sections()
    assert sections[0]["ref"] == "s_0001"
    assert sections[0]["title"] == "Overview"

    section = processor.read_section("s_0001")
    assert section["tables"] == ["t_0001"]
    assert "[[t_0001]]" in section["content"]

    table = processor.read_table("t_0001")
    assert table["data_format"] == "records"
    assert table["columns"] == ["Metric", "Value"]
    assert table["data"] == [{"Metric": "Revenue", "Value": 100}]

    hits = processor.search("Revenue")
    assert hits
    assert hits[0].get("section_ref") == "s_0001"
    assert "Revenue" in str(hits[0].get("snippet", ""))


def test_docling_json_processor_sections_tables_and_search(tmp_path: Path) -> None:
    """Docling JSON 处理器应读取真实 JSON 并产出章节、表格与搜索片段。"""

    docling_path = tmp_path / "sample_docling.json"
    parent_ref = _ref_item("#/body")
    header = SectionHeaderItem(
        self_ref="#/texts/0",
        parent=parent_ref,
        orig="Overview",
        text="Overview",
        level=1,
    )
    paragraph = TextItem(
        self_ref="#/texts/1",
        parent=parent_ref,
        orig="Revenue grew quickly.",
        text="Revenue grew quickly.",
        label=DocItemLabel.TEXT,
    )
    table = TableItem(
        self_ref="#/tables/0",
        parent=parent_ref,
        data=TableData(
            num_rows=2,
            num_cols=2,
            table_cells=[
                TableCell(
                    start_row_offset_idx=0,
                    end_row_offset_idx=1,
                    start_col_offset_idx=0,
                    end_col_offset_idx=1,
                    text="Metric",
                    column_header=True,
                ),
                TableCell(
                    start_row_offset_idx=0,
                    end_row_offset_idx=1,
                    start_col_offset_idx=1,
                    end_col_offset_idx=2,
                    text="Value",
                    column_header=True,
                ),
                TableCell(
                    start_row_offset_idx=1,
                    end_row_offset_idx=2,
                    start_col_offset_idx=0,
                    end_col_offset_idx=1,
                    text="Revenue",
                ),
                TableCell(
                    start_row_offset_idx=1,
                    end_row_offset_idx=2,
                    start_col_offset_idx=1,
                    end_col_offset_idx=2,
                    text="100",
                ),
            ],
        ),
    )
    document = DoclingDocument(
        name="sample",
        texts=[header, paragraph],
        tables=[table],
    )
    document.body.children = [
        _ref_item("#/texts/0"),
        _ref_item("#/texts/1"),
        _ref_item("#/tables/0"),
    ]
    document.save_as_json(docling_path)

    processor = DoclingProcessor(_source_for(docling_path, "application/json"))

    sections = processor.list_sections()
    assert sections[0]["ref"] == "s_0001"
    assert sections[0]["title"] == "Overview"
    assert sections[0].get("internal_ref") == "#/texts/0"

    section = processor.read_section("s_0001")
    assert section["tables"] == ["t_0001"]
    assert "[[t_0001]]" in section["content"]

    table_content = processor.read_table("t_0001")
    assert table_content.get("internal_ref") == "#/tables/0"
    assert table_content["columns"] == ["Metric", "Value"]
    assert table_content["data"] == [{"Metric": "Revenue", "Value": "100"}]

    hits = processor.search("Revenue")
    assert hits
    assert hits[0].get("section_ref") == "s_0001"
    assert "Revenue" in str(hits[0].get("snippet", ""))


def test_docling_json_processor_projects_page_content_and_reuses_public_caches(
    tmp_path: Path,
) -> None:
    """真实 Docling 页级来源应统一投影 section、table、全文与缓存结果。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 任一公开页级或缓存契约漂移时抛出。
    """

    docling_path = tmp_path / "rich.json"
    parent_ref = _ref_item("#/body")
    provenance = [
        ProvenanceItem(
            page_no=1,
            bbox=BoundingBox(l=0.0, t=0.0, r=1.0, b=1.0),
            charspan=(0, 1),
        )
    ]
    header = SectionHeaderItem(
        self_ref="#/texts/0",
        parent=parent_ref,
        orig="Operating Review",
        text="Operating Review",
        level=1,
        prov=provenance,
    )
    paragraph = TextItem(
        self_ref="#/texts/1",
        parent=parent_ref,
        orig="Revenue expanded across regions.",
        text="Revenue expanded across regions.",
        label=DocItemLabel.TEXT,
        prov=provenance,
    )
    page_number = TextItem(
        self_ref="#/texts/2",
        parent=parent_ref,
        orig="1",
        text="1",
        label=DocItemLabel.PAGE_HEADER,
        prov=provenance,
    )
    table = TableItem(
        self_ref="#/tables/0",
        parent=parent_ref,
        prov=provenance,
        data=_caption_test_table_data(),
    )
    document = DoclingDocument(
        name="rich",
        texts=[header, paragraph, page_number],
        tables=[table],
    )
    document.body.children = [
        _ref_item("#/texts/0"),
        _ref_item("#/texts/1"),
        _ref_item("#/texts/2"),
        _ref_item("#/tables/0"),
    ]
    document.save_as_json(docling_path)
    source = _source_for(docling_path, "application/json")

    assert DoclingProcessor.supports(source, media_type="application/json") is True
    assert DoclingProcessor.get_parser_version() == "docling_processor_v1.1.0"
    processor = DoclingProcessor(source)
    section_ref = processor.list_sections()[0]["ref"]

    assert processor.get_section_title(section_ref) == "Operating Review"
    assert processor.get_section_title("s_missing") is None
    with pytest.raises(KeyError, match="Section not found"):
        processor.read_section("s_missing")
    with pytest.raises(KeyError, match="Table not found"):
        processor.read_table("t_missing")
    assert processor.read_section(section_ref) == processor.read_section(section_ref)
    assert processor.get_full_text() == processor.get_full_text()
    assert "Revenue expanded across regions." in processor.get_full_text()
    assert processor.search("") == []
    assert processor.search("Revenue", within_ref="s_missing") == []
    assert processor.get_full_text_with_table_markers() == ""

    page = processor.get_page_content(1)
    assert page["has_content"] is True
    assert page["sections"][0]["ref"] == section_ref
    assert page["tables"][0]["table_ref"] == "t_0001"
    assert "Revenue expanded across regions." in page["text_preview"]
    assert " 1 " not in f" {page['text_preview']} "
    assert processor.get_page_content(2)["has_content"] is False
    with pytest.raises(ValueError, match="positive integer"):
        processor.get_page_content(0)


def test_docling_json_processor_publishes_empty_document_as_full_text_section(
    tmp_path: Path,
) -> None:
    """空 Docling 文档应发布一个合法空全文 section，而不是缺失公共命名空间。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 空文档公共契约不完整时抛出。
    """

    docling_path = tmp_path / "empty.json"
    DoclingDocument(name="empty").save_as_json(docling_path)

    processor = DoclingProcessor(_source_for(docling_path, "application/json"))

    assert processor.list_sections() == [
        {
            "ref": "s_0001",
            "title": None,
            "level": 1,
            "parent_ref": None,
            "preview": "",
        }
    ]
    assert processor.read_section("s_0001")["contains_full_text"] is True
    assert processor.read_section("s_0001")["content"] == ""
    assert processor.list_tables() == []
    assert processor.get_page_content(1)["has_content"] is False

    headerless_path = tmp_path / "headerless.json"
    paragraph = TextItem(
        self_ref="#/texts/0",
        parent=_ref_item("#/body"),
        orig="Headerless filing narrative.",
        text="Headerless filing narrative.",
        label=DocItemLabel.TEXT,
    )
    headerless_document = DoclingDocument(name="headerless", texts=[paragraph])
    headerless_document.body.children = [_ref_item("#/texts/0")]
    headerless_document.save_as_json(headerless_path)

    headerless = DoclingProcessor(_source_for(headerless_path, "application/json"))
    assert headerless.list_sections()[0]["title"] is None
    assert headerless.read_section("s_0001")["contains_full_text"] is True
    assert headerless.read_section("s_0001")["content"] == "Headerless filing narrative."

    empty_table_path = tmp_path / "empty-table.json"
    empty_table = TableItem(
        self_ref="#/tables/0",
        parent=_ref_item("#/body"),
        data=TableData(num_rows=0, num_cols=0, table_cells=[]),
    )
    empty_table_document = DoclingDocument(name="empty-table", tables=[empty_table])
    empty_table_document.body.children = [_ref_item("#/tables/0")]
    empty_table_document.save_as_json(empty_table_path)

    empty_table_processor = DoclingProcessor(
        _source_for(empty_table_path, "application/json")
    )
    empty_table_content = empty_table_processor.read_table("t_0001")
    assert empty_table_content["data_format"] == "markdown"
    assert empty_table_content["data"]

    with pytest.raises(ValueError, match="Docling JSON 文件不存在"):
        DoclingProcessor(_source_for(tmp_path / "missing.json", "application/json"))


def test_docling_support_sniff_rejects_malformed_or_incomplete_json(tmp_path: Path) -> None:
    """Docling public support 探测不得把非法或缺少核心字段的 JSON 误判为文档。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 非 Docling JSON 被误判为支持时抛出。
    """

    payloads = [
        "not-json",
        "[]",
        '{"pages": {}, "texts": []}',
        '{"body": {}, "texts": []}',
    ]
    for index, payload in enumerate(payloads):
        path = tmp_path / f"invalid-{index}.json"
        path.write_text(payload, encoding="utf-8")
        assert DoclingProcessor.supports(_source_for(path, "application/json")) is False

    plain_path = tmp_path / "plain.txt"
    plain_path.write_text("plain text", encoding="utf-8")
    assert DoclingProcessor.supports(_source_for(plain_path, "text/plain")) is False
    assert DoclingProcessor.supports(_source_for(plain_path, "application/json")) is False

    conventional_path = tmp_path / "trusted_docling.json"
    conventional_path.write_text("not-json", encoding="utf-8")
    assert DoclingProcessor.supports(_source_for(conventional_path, "text/plain")) is True


def test_docling_json_processor_projects_referenced_table_caption(
    tmp_path: Path,
) -> None:
    """Docling 公共结果必须投影表格引用的业务标题。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 真实 Docling caption 引用未进入表格摘要时抛出。
    """

    docling_path = tmp_path / "caption_docling.json"
    parent_ref = _ref_item("#/body")
    header = SectionHeaderItem(
        self_ref="#/texts/0",
        parent=parent_ref,
        orig="Financial Review",
        text="Financial Review",
        level=1,
    )
    caption = TextItem(
        self_ref="#/texts/1",
        parent=parent_ref,
        orig="Consolidated statements of operations",
        text="Consolidated statements of operations",
        label=DocItemLabel.CAPTION,
    )
    table = TableItem(
        self_ref="#/tables/0",
        parent=parent_ref,
        captions=[_ref_item("#/texts/1")],
        data=TableData(
            num_rows=2,
            num_cols=2,
            table_cells=[
                TableCell(
                    start_row_offset_idx=0,
                    end_row_offset_idx=1,
                    start_col_offset_idx=0,
                    end_col_offset_idx=1,
                    text="Metric",
                    column_header=True,
                ),
                TableCell(
                    start_row_offset_idx=0,
                    end_row_offset_idx=1,
                    start_col_offset_idx=1,
                    end_col_offset_idx=2,
                    text="2025",
                    column_header=True,
                ),
                TableCell(
                    start_row_offset_idx=1,
                    end_row_offset_idx=2,
                    start_col_offset_idx=0,
                    end_col_offset_idx=1,
                    text="Revenue",
                ),
                TableCell(
                    start_row_offset_idx=1,
                    end_row_offset_idx=2,
                    start_col_offset_idx=1,
                    end_col_offset_idx=2,
                    text="100",
                ),
            ],
        ),
    )
    document = DoclingDocument(
        name="caption-sample",
        texts=[header, caption],
        tables=[table],
    )
    document.body.children = [
        _ref_item("#/texts/0"),
        _ref_item("#/texts/1"),
        _ref_item("#/tables/0"),
    ]
    document.save_as_json(docling_path)

    processor = DoclingProcessor(_source_for(docling_path, "application/json"))

    assert processor.list_tables()[0]["caption"] == (
        "Consolidated statements of operations"
    )
    assert processor.read_table("t_0001")["caption"] == (
        "Consolidated statements of operations"
    )


def test_docling_json_processor_preserves_normalized_unique_caption_order(
    tmp_path: Path,
) -> None:
    """多 caption 必须按引用顺序规范化、精确去重并确定性连接。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 顺序、空白规范化、大小写或去重语义不符合公共契约时抛出。
    """

    caption_items = [
        _caption_text_item(1, "  Consolidated\n Results  "),
        _caption_text_item(2, "Consolidated\t  Results"),
        _caption_text_item(3, "  Unaudited "),
        _caption_text_item(4, "unaudited"),
    ]
    ordered_path = _save_docling_caption_document(
        tmp_path,
        name="ordered-caption",
        caption_items=caption_items,
        caption_refs=[
            _ref_item("#/texts/1"),
            _ref_item("#/texts/2"),
            _ref_item("#/texts/3"),
            _ref_item("#/texts/4"),
        ],
    )
    reversed_path = _save_docling_caption_document(
        tmp_path,
        name="reversed-caption",
        caption_items=caption_items,
        caption_refs=[
            _ref_item("#/texts/4"),
            _ref_item("#/texts/3"),
            _ref_item("#/texts/2"),
            _ref_item("#/texts/1"),
        ],
    )

    assert _caption_from_public_views(ordered_path) == (
        "Consolidated Results Unaudited unaudited",
        "Consolidated Results Unaudited unaudited",
    )
    assert _caption_from_public_views(reversed_path) == (
        "unaudited Unaudited Consolidated Results",
        "unaudited Unaudited Consolidated Results",
    )


def test_docling_json_processor_returns_none_for_empty_or_blank_captions(
    tmp_path: Path,
) -> None:
    """空 caption 列表与全空白 caption 必须投影为 ``None``。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 空语义被投影为空字符串或上下文替代值时抛出。
    """

    empty_path = _save_docling_caption_document(
        tmp_path,
        name="empty-caption",
        caption_items=[],
        caption_refs=[],
    )
    blank_path = _save_docling_caption_document(
        tmp_path,
        name="blank-caption",
        caption_items=[_caption_text_item(1, " \n\t  ")],
        caption_refs=[_ref_item("#/texts/1")],
    )

    assert _caption_from_public_views(empty_path) == (None, None)
    assert _caption_from_public_views(blank_path) == (None, None)


def test_docling_json_processor_skips_dangling_caption_references(
    tmp_path: Path,
) -> None:
    """未知集合与越界 caption 引用只应被跳过并保留有效标题。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: dangling 引用污染或阻断公共 caption 投影时抛出。
    """

    caption_items = [_caption_text_item(1, "Valid caption")]
    mixed_path = _save_docling_caption_document(
        tmp_path,
        name="mixed-dangling-caption",
        caption_items=caption_items,
        caption_refs=[
            _ref_item("#/missing/0"),
            _ref_item("#/texts/1"),
            _ref_item("#/texts/999"),
        ],
    )
    dangling_only_path = _save_docling_caption_document(
        tmp_path,
        name="dangling-only-caption",
        caption_items=caption_items,
        caption_refs=[
            _ref_item("#/missing/0"),
            _ref_item("#/texts/999"),
        ],
    )

    assert _caption_from_public_views(mixed_path) == (
        "Valid caption",
        "Valid caption",
    )
    assert _caption_from_public_views(dangling_only_path) == (None, None)


def test_docling_json_processor_skips_document_root_caption_reference(
    tmp_path: Path,
) -> None:
    """Docling document-root 引用必须在解析前跳过且不影响有效标题。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: root 引用被解析或阻断其它有效 caption 时抛出。
    """

    caption_items = [_caption_text_item(1, "Root-safe caption")]
    mixed_path = _save_docling_caption_document(
        tmp_path,
        name="mixed-root-caption",
        caption_items=caption_items,
        caption_refs=[_ref_item("#"), _ref_item("#/texts/1")],
    )
    root_only_path = _save_docling_caption_document(
        tmp_path,
        name="root-only-caption",
        caption_items=caption_items,
        caption_refs=[_ref_item("#")],
    )

    assert _caption_from_public_views(mixed_path) == (
        "Root-safe caption",
        "Root-safe caption",
    )
    assert _caption_from_public_views(root_only_path) == (None, None)


def test_docling_json_processor_rejects_model_invalid_caption_reference(
    tmp_path: Path,
) -> None:
    """serialized ``$ref`` 非法时必须在真实 Docling loader 边界失败。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 非法引用进入 caption resolver 或未暴露加载失败时抛出。
        OSError: 读写临时 Docling JSON 失败时抛出。
    """

    docling_path = _save_docling_caption_document(
        tmp_path,
        name="model-invalid-caption",
        caption_items=[_caption_text_item(1, "Loader boundary")],
        caption_refs=[_ref_item("#/texts/1")],
    )
    serialized = docling_path.read_text(encoding="utf-8")
    valid_ref = '"$ref": "#/texts/1"'
    assert serialized.count(valid_ref) == 1
    docling_path.write_text(
        serialized.replace(valid_ref, '"$ref": "not-a-valid-cref"', 1),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="Docling JSON parsing failed") as raised:
        DoclingProcessor(_source_for(docling_path, "application/json"))

    assert raised.value.__cause__ is not None
    assert "string_pattern_mismatch" in str(raised.value.__cause__)


def test_docling_json_processor_skips_non_text_caption_references(
    tmp_path: Path,
) -> None:
    """解析到真实非文本对象的 caption 引用必须被忽略。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 非文本对象被误投影或阻断有效 caption 时抛出。
    """

    caption_items = [_caption_text_item(1, "Text caption")]
    mixed_path = _save_docling_caption_document(
        tmp_path,
        name="mixed-non-text-caption",
        caption_items=caption_items,
        caption_refs=[_ref_item("#/tables/0"), _ref_item("#/texts/1")],
    )
    non_text_only_path = _save_docling_caption_document(
        tmp_path,
        name="non-text-only-caption",
        caption_items=caption_items,
        caption_refs=[_ref_item("#/tables/0")],
    )

    assert _caption_from_public_views(mixed_path) == (
        "Text caption",
        "Text caption",
    )
    assert _caption_from_public_views(non_text_only_path) == (None, None)


def test_docling_json_processor_propagates_caption_to_public_table_views(
    tmp_path: Path,
) -> None:
    """同一 caption 必须传播到 list、read 与页级三个公开表格视图。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 三个公开消费者未共享同一 caption 投影时抛出。
    """

    expected_caption = "Consolidated statements"
    provenance = ProvenanceItem(
        page_no=1,
        bbox=BoundingBox(l=0.0, t=0.0, r=1.0, b=1.0),
        charspan=(0, 1),
    )
    docling_path = _save_docling_caption_document(
        tmp_path,
        name="public-caption-views",
        caption_items=[_caption_text_item(1, expected_caption)],
        caption_refs=[_ref_item("#/texts/1")],
        table_provenance=[provenance],
    )

    processor = DoclingProcessor(_source_for(docling_path, "application/json"))
    page_content = processor.get_page_content(1)

    assert processor.list_tables()[0]["caption"] == expected_caption
    assert processor.read_table("t_0001")["caption"] == expected_caption
    assert page_content["tables"][0]["caption"] == expected_caption
