"""共享文档处理器的轻量确定性 fixture 测试。"""

from __future__ import annotations

import io
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
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
from dayu.documents.processors.bounded_source import (
    BoundedSourceSnapshot,
    SourceBudgetExceeded,
)
from dayu.documents.processors.bs_processor import BSProcessor
from dayu.documents.processors.docling_processor import DoclingProcessor
from dayu.documents.processors.local_file_source import LocalFileSource
from dayu.documents.processors.markdown_processor import MarkdownProcessor


@dataclass(frozen=True, slots=True)
class _MemorySource:
    """测试用内存 Source。"""

    payload: bytes
    uri: str = "memory.md"
    media_type: str | None = "text/markdown"
    content_length: int | None = None
    etag: str | None = None

    def open(self) -> BinaryIO:
        """打开 payload 的独立二进制流。

        Returns:
            内存二进制流。

        Raises:
            无。
        """

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
        raise AssertionError("bounded snapshot must only depend on Source.open()")


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
            raise _SyntheticCancellation("cancel bounded source copy")


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


def test_bounded_source_snapshot_enforces_actual_stream_limit_plus_one() -> None:
    """声明长度偏小时仍必须对同一 open stream 实读 ``limit+1``。"""

    source = _MemorySource(payload=b"123456789", content_length=1)

    with pytest.raises(SourceBudgetExceeded) as raised:
        with BoundedSourceSnapshot(source, max_bytes=8):
            pytest.fail("oversized source must not publish a snapshot")

    assert raised.value.limit_bytes == 8
    assert raised.value.observed_bytes == 9


def test_bounded_source_snapshot_accepts_exact_limit_and_feeds_processor() -> None:
    """精确命中预算应成功，processor 只消费 snapshot 而不重开原来源。"""

    payload = b"# Overview\nRevenue grew.\n"
    source = _MemorySource(payload=payload, content_length=len(payload))

    with BoundedSourceSnapshot(source, max_bytes=len(payload)) as snapshot:
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

    with pytest.raises(ValueError, match="not active"):
        snapshot.open()
    with pytest.raises(RuntimeError, match="cannot be reused"):
        snapshot.__enter__()


@pytest.mark.parametrize("max_bytes", (0, -1, True))
def test_bounded_source_snapshot_rejects_invalid_byte_limit(max_bytes: int) -> None:
    """有界 Source 预算只接受非 bool 正整数。"""

    with pytest.raises(ValueError, match="positive integer"):
        BoundedSourceSnapshot(_MemorySource(payload=b"data"), max_bytes=max_bytes)


def test_bounded_source_snapshot_declared_oversize_is_only_an_early_rejection() -> None:
    """声明长度超限可早拒绝，但不会发布或物化 snapshot。"""

    source = _MemorySource(payload=b"tiny", content_length=100)

    with pytest.raises(SourceBudgetExceeded) as raised:
        with BoundedSourceSnapshot(source, max_bytes=8):
            pytest.fail("declared oversize must be rejected before publication")

    assert raised.value.source_uri == "memory.md"
    assert raised.value.observed_bytes == 100


def test_bounded_source_snapshot_cleans_materialized_file_after_python_exception() -> None:
    """普通 Python exception 必须清理 snapshot 拥有的物化文件。"""

    source = _MemorySource(payload=b"# Overview\n")
    materialized_path: Path | None = None

    with pytest.raises(RuntimeError, match="consumer failure"):
        with BoundedSourceSnapshot(source, max_bytes=64) as snapshot:
            materialized_path = snapshot.materialize(suffix=".md")
            assert materialized_path.exists()
            raise RuntimeError("consumer failure")

    assert materialized_path is not None
    assert not materialized_path.exists()


def test_bounded_source_snapshot_cleans_materialized_file_on_normal_exit() -> None:
    """正常退出 context 时也必须清理 snapshot 拥有的物化文件。"""

    source = _MemorySource(payload=b"# Overview\n")
    with BoundedSourceSnapshot(source, max_bytes=64) as snapshot:
        materialized_path = snapshot.materialize(suffix=".md")
        assert snapshot.materialize(suffix=".txt") == materialized_path
        assert materialized_path.exists()

    assert not materialized_path.exists()


@pytest.mark.parametrize(
    ("source", "cancellation_check", "expected_exception"),
    (
        (_FailingSource(), None, OSError),
        (_MemorySource(payload=b"payload"), _CancelAfterChecks(2), _SyntheticCancellation),
    ),
)
def test_bounded_source_snapshot_closes_spool_on_resource_failure_or_cancellation(
    monkeypatch: pytest.MonkeyPatch,
    source: _MemorySource | _FailingSource,
    cancellation_check: Callable[[], None] | None,
    expected_exception: type[BaseException],
) -> None:
    """资源失败与协作取消都必须关闭未发布 spool。"""

    spools: list[io.BytesIO] = []

    def fake_spooled_temporary_file(*, max_size: int, mode: str) -> io.BytesIO:
        """记录 snapshot 创建的 spool。

        Args:
            max_size: 内存阈值。
            mode: 文件模式。

        Returns:
            可观察关闭状态的内存流。

        Raises:
            无。
        """

        del max_size, mode
        spool = io.BytesIO()
        spools.append(spool)
        return spool

    monkeypatch.setattr(
        "dayu.documents.processors.bounded_source.tempfile.SpooledTemporaryFile",
        fake_spooled_temporary_file,
    )

    with pytest.raises(expected_exception):
        with BoundedSourceSnapshot(
            source,
            max_bytes=64,
            cancellation_check=cancellation_check,
        ):
            pytest.fail("failure path must not publish a snapshot")

    assert len(spools) == 1
    assert spools[0].closed is True


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
