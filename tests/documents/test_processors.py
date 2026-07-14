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
    RefItem,
    SectionHeaderItem,
    TableCell,
    TableData,
    TableItem,
    TextItem,
)
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
