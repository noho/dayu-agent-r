"""S2 processor/read 一致性与 typed failure 契约测试。"""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from functools import partial
from io import BytesIO
from pathlib import Path
from threading import Lock
import time

import pytest

from dayu.contracts.cancellation import CancellationToken
from dayu.contracts.json_value import JsonValue
from dayu.documents.processors.base import (
    DocumentProcessor,
    SearchHit,
    SectionContent,
    SectionSummary,
    TableContent,
    TableSummary,
)
from dayu.documents.processors.processor_registry import ProcessorRegistry
from dayu.documents.processors.source import Source
from dayu.fins.domain.document_models import (
    CompanyMeta,
    DocumentMeta,
    FinsSourceProvider,
    SourceHandle,
    SourceDocumentStateChangeRequest,
    SourceDocumentUpsertRequest,
    now_iso8601,
)
from dayu.fins.domain.enums import SourceKind
from dayu.fins.processors.bs_ten_q_processor import BsTenQFormProcessor
from dayu.fins.processors.bs_ten_k_processor import BsTenKFormProcessor
from dayu.fins.processors.sec_form_section_common import (
    _VirtualSection,
    _VirtualSectionProcessorMixin,
)
from dayu.fins.processors.sec_processor import _load_text
from dayu.fins.processors.sec_report_form_common import _extract_source_text_preserving_lines
from dayu.fins.processors.source_text import (
    FinsSourceDecodeError,
    decode_source_bytes,
    materialize_source_text,
    read_source_path_text,
    validate_source_utf8_text,
)
from dayu.fins.processors.ten_q_processor import TenQFormProcessor
from dayu.fins.processors.ten_k_processor import TenKFormProcessor
from dayu.fins.storage import (
    FsBatchingRepository,
    FsCompanyMetaRepository,
    FsDocumentBlobRepository,
    FsProcessedDocumentRepository,
    FsSourceDocumentRepository,
)
from dayu.fins.storage._fs_repository_factory import _FsRepositorySet, build_fs_repository_set
from dayu.fins.storage.local_file_source import LocalFileSource
from dayu.fins.tools.error_contract import ErrorCode
from dayu.fins.tools.read_runtime import FinsReadRuntime
from dayu.fins.tools.read_runtime_helpers import FinsReadBusinessError, FinsReadCancelledError


class _MemorySource:
    """测试用内存文本 Source。"""

    def __init__(self, payload: bytes, *, media_type: str = "text/html") -> None:
        """初始化内存 source。

        Args:
            payload: source 字节。
            media_type: source 媒体类型。

        Returns:
            无。

        Raises:
            无。
        """

        self._payload = payload
        self._media_type = media_type

    @property
    def uri(self) -> str:
        """返回内存 URI。

        Args:
            无。

        Returns:
            内存 URI。

        Raises:
            无。
        """

        return "memory://source.html"

    @property
    def media_type(self) -> str:
        """返回媒体类型。

        Args:
            无。

        Returns:
            媒体类型。

        Raises:
            无。
        """

        return self._media_type

    @property
    def content_length(self) -> int:
        """返回字节长度。

        Args:
            无。

        Returns:
            source 字节长度。

        Raises:
            无。
        """

        return len(self._payload)

    @property
    def etag(self) -> str:
        """返回测试 etag。

        Args:
            无。

        Returns:
            固定 etag。

        Raises:
            无。
        """

        return "test-etag"

    def open(self) -> BytesIO:
        """打开内存二进制流。

        Args:
            无。

        Returns:
            可读取的二进制流。

        Raises:
            无。
        """

        return BytesIO(self._payload)

    def materialize(self, suffix: str | None = None) -> Path:
        """拒绝未配置的物化请求。

        Args:
            suffix: 可选后缀。

        Returns:
            不返回。

        Raises:
            OSError: 始终抛出，测试物化失败契约。
        """

        del suffix
        raise OSError("materialize sentinel path")


class _ReadProcessor:
    """测试用最小 DocumentProcessor。"""

    def __init__(
        self,
        source: Source,
        *,
        form_type: str | None = None,
        media_type: str | None = None,
    ) -> None:
        """初始化 processor。

        Args:
            source: processor 输入 source。
            form_type: 可选表单类型。
            media_type: 可选媒体类型。

        Returns:
            无。

        Raises:
            无。
        """

        del form_type, media_type
        with source.open() as stream:
            self.label = stream.read().decode("utf-8")
        self.list_sections_error: Exception | None = None
        self.before_list_sections: Callable[[], None] | None = None

    @classmethod
    def get_parser_version(cls) -> str:
        """返回测试 parser version。

        Args:
            无。

        Returns:
            固定版本。

        Raises:
            无。
        """

        return "test-v1"

    @classmethod
    def supports(
        cls,
        source: Source,
        *,
        form_type: str | None = None,
        media_type: str | None = None,
    ) -> bool:
        """声明支持测试 source。

        Args:
            source: 文档 source。
            form_type: 可选表单类型。
            media_type: 可选媒体类型。

        Returns:
            始终返回 ``True``。

        Raises:
            无。
        """

        del source, form_type, media_type
        return True

    def list_sections(self) -> list[SectionSummary]:
        """返回单章节或注入失败。

        Args:
            无。

        Returns:
            单章节摘要。

        Raises:
            Exception: 测试注入的 list failure。
        """

        if self.before_list_sections is not None:
            self.before_list_sections()
        if self.list_sections_error is not None:
            raise self.list_sections_error
        return [
            {
                "ref": "s_0001",
                "title": "Overview",
                "level": 1,
                "parent_ref": None,
                "preview": self.label,
            }
        ]

    def read_section(self, ref: str) -> SectionContent:
        """读取固定章节。

        Args:
            ref: 章节 ref。

        Returns:
            固定章节内容。

        Raises:
            KeyError: ref 非固定章节时抛出。
        """

        if ref != "s_0001":
            raise KeyError(ref)
        return {
            "ref": ref,
            "title": "Overview",
            "content": self.label,
            "tables": [],
            "word_count": 1,
            "contains_full_text": True,
        }

    def list_tables(self) -> list[TableSummary]:
        """返回空表格列表。

        Args:
            无。

        Returns:
            空列表。

        Raises:
            无。
        """

        return []

    def read_table(self, table_ref: str) -> TableContent:
        """拒绝未知表格。

        Args:
            table_ref: 表格 ref。

        Returns:
            不返回。

        Raises:
            KeyError: 始终抛出。
        """

        raise KeyError(table_ref)

    def get_section_title(self, ref: str) -> str | None:
        """返回章节标题。

        Args:
            ref: 章节 ref。

        Returns:
            固定章节标题或 ``None``。

        Raises:
            无。
        """

        return "Overview" if ref == "s_0001" else None

    def search(self, query: str, within_ref: str | None = None) -> list[SearchHit]:
        """返回空搜索命中。

        Args:
            query: 查询词。
            within_ref: 可选章节范围。

        Returns:
            空列表。

        Raises:
            无。
        """

        del query, within_ref
        return []

    def get_full_text(self) -> str:
        """返回完整测试文本。

        Args:
            无。

        Returns:
            processor 标签。

        Raises:
            无。
        """

        return self.label

    def get_full_text_with_table_markers(self) -> str:
        """返回带 marker 的完整测试文本。

        Args:
            无。

        Returns:
            processor 标签。

        Raises:
            无。
        """

        return self.label


class _CountingProcessorRegistry(ProcessorRegistry):
    """记录 processor 构建次数的测试 registry。"""

    def __init__(self) -> None:
        """初始化 registry 探针。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        super().__init__()
        self.create_count = 0
        self.created: list[_ReadProcessor] = []
        self.before_return: Callable[[], None] | None = None
        self.fixed_processor: DocumentProcessor | None = None
        self.delay_seconds = 0.0
        self._guard = Lock()

    def create_with_fallback(
        self,
        source: Source,
        *,
        form_type: str | None = None,
        media_type: str | None = None,
        on_fallback: Callable[[type[DocumentProcessor], Exception, int, int], None] | None = None,
    ) -> DocumentProcessor:
        """创建并记录测试 processor。

        Args:
            source: 文档 source。
            form_type: 可选表单类型。
            media_type: 可选媒体类型。
            on_fallback: 可选 fallback 回调。

        Returns:
            新建测试 processor。

        Raises:
            OSError: source 读取失败时抛出。
        """

        del form_type, media_type, on_fallback
        with self._guard:
            self.create_count += 1
        if self.fixed_processor is not None:
            return self.fixed_processor
        if self.before_return is not None:
            self.before_return()
        if self.delay_seconds > 0:
            time.sleep(self.delay_seconds)
        with source.open() as stream:
            label = stream.read().decode("utf-8")
        processor = _ReadProcessor(_MemorySource(label.encode("utf-8")))
        self.created.append(processor)
        return processor


class _RevisionProbeRepository(FsSourceDocumentRepository):
    """返回可变内存 source 并统计 meta 读取的仓储探针。"""

    def __init__(self, workspace_root: Path, *, repository_set: _FsRepositorySet) -> None:
        """初始化仓储探针。

        Args:
            workspace_root: Fins workspace 根目录。
            repository_set: 共享文件系统仓储集合。

        Returns:
            无。

        Raises:
            OSError: 仓储初始化失败时抛出。
        """

        super().__init__(workspace_root, repository_set=repository_set)
        self._batching_repository = FsBatchingRepository(
            workspace_root,
            repository_set=repository_set,
        )
        self._blob_repository = FsDocumentBlobRepository(
            workspace_root,
            repository_set=repository_set,
        )
        self.payload = b"version-one"
        self.get_source_meta_calls = 0
        self.mutate_on_next_meta_read = False

    def get_primary_source(self, ticker: str, document_id: str, source_kind: SourceKind) -> Source:
        """返回当前内存 source。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。
            source_kind: source kind。

        Returns:
            当前内存 source。

        Raises:
            无。
        """

        del ticker, document_id, source_kind
        return _MemorySource(self.payload)

    def get_source_meta(
        self,
        ticker: str,
        document_id: str,
        source_kind: SourceKind,
    ) -> DocumentMeta:
        """读取 meta，并可在返回后注入一次 revision 变化。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。
            source_kind: source kind。

        Returns:
            读取时刻的 source meta。

        Raises:
            FileNotFoundError: source meta 不存在时抛出。
            ValueError: source meta 非法时抛出。
        """

        self.get_source_meta_calls += 1
        meta = super().get_source_meta(ticker, document_id, source_kind)
        if self.mutate_on_next_meta_read:
            self.mutate_on_next_meta_read = False
            _update_source(self, fingerprint="revision-during-meta", form_type="10-Q")
        return meta


class _ManualCancellationToken:
    """测试用可控取消 token。"""

    def __init__(self) -> None:
        """初始化未取消 token。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        self.cancelled = False

    def cancel(self) -> None:
        """触发取消。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        self.cancelled = True

    def is_cancelled(self) -> bool:
        """返回取消状态。

        Args:
            无。

        Returns:
            是否已取消。

        Raises:
            无。
        """

        return self.cancelled

    def cancel_reason(self) -> str | None:
        """返回取消原因。

        Args:
            无。

        Returns:
            已取消时返回测试原因。

        Raises:
            无。
        """

        return "test cancellation" if self.cancelled else None

    def requested_at(self) -> datetime | None:
        """返回取消时间。

        Args:
            无。

        Returns:
            本探针不记录时间，始终返回 ``None``。

        Raises:
            无。
        """

        return None


class _VirtualBaseProcessor:
    """虚拟章节 mixin 的测试下一跳。"""

    _base_tables: list[TableSummary]

    def list_sections(self) -> list[SectionSummary]:
        """返回空底层章节。

        Args:
            无。

        Returns:
            空列表。

        Raises:
            无。
        """

        return []

    def read_section(self, ref: str) -> SectionContent:
        """拒绝底层章节读取。

        Args:
            ref: 章节 ref。

        Returns:
            不返回。

        Raises:
            KeyError: 始终抛出。
        """

        raise KeyError(ref)

    def list_tables(self) -> list[TableSummary]:
        """返回 harness 配置的底层表格。

        Args:
            无。

        Returns:
            底层表格列表。

        Raises:
            无。
        """

        return list(self._base_tables)

    def get_section_title(self, ref: str) -> str | None:
        """返回空标题。

        Args:
            ref: 章节 ref。

        Returns:
            始终返回 ``None``。

        Raises:
            无。
        """

        del ref
        return None

    def search(self, query: str, within_ref: str | None = None) -> list[SearchHit]:
        """返回空搜索结果。

        Args:
            query: 查询词。
            within_ref: 可选章节范围。

        Returns:
            空列表。

        Raises:
            无。
        """

        del query, within_ref
        return []


class _VirtualHarness(_VirtualSectionProcessorMixin, _VirtualBaseProcessor):
    """直接测试 virtual section refresh owner 的 harness。"""

    def __init__(self, *, include_table_marker: bool = True) -> None:
        """初始化两章节 harness。

        Args:
            include_table_marker: marked text 是否包含底层 table ref。

        Returns:
            无。

        Raises:
            无。
        """

        self._virtual_sections = [
            _VirtualSection("s_alpha", "Alpha", "alpha", "alpha", [], start=0, end=20),
            _VirtualSection("s_beta", "Beta", "beta", "beta", [], start=20, end=40),
        ]
        self._virtual_section_by_ref = {}
        self._table_ref_to_virtual_ref = {}
        marker = "[[t_0001]]\n" if include_table_marker else ""
        self._marked_text = f"Alpha\n{marker}Beta\n"
        self._base_tables: list[TableSummary] = [
            {
                "table_ref": "t_0001",
                "caption": None,
                "context_before": "",
                "row_count": 1,
                "col_count": 1,
                "table_type": "data",
                "headers": None,
                "section_ref": None,
            }
        ]

    def _build_markers(self, full_text: str) -> list[tuple[int, str | None]]:
        """按 Alpha/Beta 标题返回测试 marker。

        Args:
            full_text: 标记全文。

        Returns:
            两个稳定 marker。

        Raises:
            ValueError: 测试全文缺少 Beta 时抛出。
        """

        return [(0, "Alpha"), (full_text.index("Beta"), "Beta")]

    def get_full_text(self) -> str:
        """返回测试全文。

        Args:
            无。

        Returns:
            测试全文。

        Raises:
            无。
        """

        return self._marked_text

    def get_full_text_with_table_markers(self) -> str:
        """返回带 table marker 的测试全文。

        Args:
            无。

        Returns:
            测试全文。

        Raises:
            无。
        """

        return self._marked_text


def _build_runtime(tmp_path: Path) -> tuple[FinsReadRuntime, _RevisionProbeRepository, _CountingProcessorRegistry]:
    """构造真实 storage + 探针 processor 的 read runtime。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        runtime、source repository 与 registry。

    Raises:
        OSError: fixture storage 初始化或写入失败时抛出。
    """

    workspace_root = tmp_path / "s2-read-consistency"
    repository_set = build_fs_repository_set(workspace_root=workspace_root)
    company_repository = FsCompanyMetaRepository(workspace_root, repository_set=repository_set)
    source_repository = _RevisionProbeRepository(workspace_root, repository_set=repository_set)
    processed_repository = FsProcessedDocumentRepository(workspace_root, repository_set=repository_set)
    registry = _CountingProcessorRegistry()
    batching_repository = FsBatchingRepository(workspace_root, repository_set=repository_set)
    batch = batching_repository.begin_batch("AAPL")
    company_repository.upsert_company_meta(
        CompanyMeta(
            company_id="0000320193",
            company_name="Apple Inc.",
            ticker="AAPL",
            market="US",
            resolver_version="test",
            updated_at=now_iso8601(),
            ticker_aliases=[],
        ),
        batch=batch,
    )
    source_repository.create_source_document(
        SourceDocumentUpsertRequest(
            ticker="AAPL",
            document_id="doc-1",
            internal_document_id="doc-1",
            form_type="10-K",
            primary_document="doc-1.txt",
            files=[
                source_repository._blob_repository.store_file(
                    SourceHandle("AAPL", "doc-1", SourceKind.FILING.value),
                    "doc-1.txt",
                    BytesIO(b"version-one"),
                    batch=batch,
                    content_type="text/plain",
                )
            ],
            meta={
                "ingest_method": "download",
                "source_provider": FinsSourceProvider.SEC_EDGAR.to_storage_value(),
                "ingest_complete": True,
                "is_deleted": False,
                "source_fingerprint": "revision-one",
                "filing_date": "2025-01-01",
                "amended": False,
            },
        ),
        SourceKind.FILING,
        batch=batch,
    )
    batching_repository.commit_batch(batch)
    runtime = FinsReadRuntime(
        company_repository=company_repository,
        source_repository=source_repository,
        processed_repository=processed_repository,
        processor_registry=registry,
    )
    return runtime, source_repository, registry


def _update_source(
    repository: _RevisionProbeRepository,
    *,
    fingerprint: str,
    form_type: str = "10-K",
    document_id: str = "doc-1",
) -> None:
    """更新测试 source revision。

    Args:
        repository: source repository。
        fingerprint: 新 source fingerprint。
        form_type: 新表单类型。
        document_id: 待更新文档 ID。

    Returns:
        无。

    Raises:
        OSError: source meta 更新失败时抛出。
    """

    batch = repository._batching_repository.begin_batch("AAPL")
    try:
        repository.update_source_document(
            SourceDocumentUpsertRequest(
                ticker="AAPL",
                document_id=document_id,
                internal_document_id=document_id,
                form_type=form_type,
                meta={"source_fingerprint": fingerprint},
            ),
            SourceKind.FILING,
            batch=batch,
        )
    except Exception:
        repository._batching_repository.rollback_batch(batch)
        raise
    repository._batching_repository.commit_batch(batch)


def _mutate_existing_ten_q_sections(
    *,
    full_text: str,
    virtual_sections: list[_VirtualSection],
) -> None:
    """模拟 10-Q expansion 只修改既有 boundary/order。

    Args:
        full_text: 测试全文。
        virtual_sections: 待修改的既有章节。

    Returns:
        无。

    Raises:
        ValueError: 章节不足两个时抛出。
    """

    del full_text
    if len(virtual_sections) < 2:
        raise ValueError("测试需要两个章节")
    virtual_sections[0].start = 30
    virtual_sections[1].start = 0
    virtual_sections.reverse()


def _append_virtual_section(
    *,
    full_text: str,
    virtual_sections: list[_VirtualSection],
) -> None:
    """向测试列表追加非法 section。

    Args:
        full_text: 测试全文。
        virtual_sections: 待修改章节。

    Returns:
        无。

    Raises:
        无。
    """

    del full_text
    virtual_sections.append(_VirtualSection("s_new", "New", "new", "new", []))


def _build_virtual_postprocess_probe(
    processor_type: (
        type[TenQFormProcessor]
        | type[BsTenQFormProcessor]
        | type[TenKFormProcessor]
        | type[BsTenKFormProcessor]
    ),
    harness: _VirtualHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> TenQFormProcessor | BsTenQFormProcessor | TenKFormProcessor | BsTenKFormProcessor:
    """构造不运行重型 parser 的真实 10-Q postprocess probe。

    Args:
        processor_type: edgartools/BS 的 10-Q 或 10-K processor 类型。
        harness: 提供稳定 section/table fixture 的 harness。
        monkeypatch: pytest monkeypatch fixture。

    Returns:
        已装配真实 postprocess/refresh 方法的 processor probe。

    Raises:
        ValueError: processor 类型不属于四条 report-form 路径时抛出。
    """

    if processor_type is TenQFormProcessor:
        processor: TenQFormProcessor | BsTenQFormProcessor | TenKFormProcessor | BsTenKFormProcessor
        processor = TenQFormProcessor.__new__(TenQFormProcessor)
    elif processor_type is BsTenQFormProcessor:
        processor = BsTenQFormProcessor.__new__(BsTenQFormProcessor)
    elif processor_type is TenKFormProcessor:
        processor = TenKFormProcessor.__new__(TenKFormProcessor)
    elif processor_type is BsTenKFormProcessor:
        processor = BsTenKFormProcessor.__new__(BsTenKFormProcessor)
    else:
        raise ValueError("未知 report-form processor 类型")
    processor._virtual_sections = harness._virtual_sections
    processor._virtual_section_by_ref = {}
    processor._table_ref_to_virtual_ref = {}
    monkeypatch.setattr(processor, "_get_base_processor", harness._get_base_processor)
    monkeypatch.setattr(processor, "_collect_marked_text", harness._collect_marked_text)
    monkeypatch.setattr(processor, "_build_markers", harness._build_markers)
    return processor


def _preserve_virtual_sections(
    *,
    full_text: str,
    virtual_sections: list[_VirtualSection],
) -> None:
    """模拟不改变 section 骨架的 10-K expansion。

    Args:
        full_text: 测试全文。
        virtual_sections: 既有虚拟章节。

    Returns:
        无。

    Raises:
        无。
    """

    del full_text, virtual_sections


def _read_runtime_processor(runtime: FinsReadRuntime, _index: int) -> DocumentProcessor:
    """并发读取同一 runtime 文档 processor。

    Args:
        runtime: 待读取的 read runtime。
        _index: executor map 占位序号。

    Returns:
        runtime 返回的 processor。

    Raises:
        FinsReadBusinessError: processor 读取失败时抛出。
    """

    return runtime._get_or_create_processor(ticker="AAPL", document_id="doc-1")


def _raise_search_enrichment_failure(
    failure: Exception,
    sections: list[SectionSummary],
    form_type: str | None,
    *,
    cancellation_token: CancellationToken | None = None,
) -> list[dict[str, JsonValue]]:
    """注入 search enrichment 失败。

    Args:
        failure: 要抛出的异常。
        sections: 原始章节。
        form_type: 表单类型。
        cancellation_token: 取消 token。

    Returns:
        不返回。

    Raises:
        Exception: 始终抛出传入 failure。
    """

    del sections, form_type, cancellation_token
    raise failure


def _raise_search_stage_failure(
    failure: Exception,
    sections: list[dict[str, JsonValue]],
) -> None:
    """注入 BM25F/profile stage 失败。

    Args:
        failure: 要抛出的异常。
        sections: enrichment 后章节。

    Returns:
        不返回。

    Raises:
        Exception: 始终抛出传入 failure。
    """

    del sections
    raise failure


def test_strict_source_decoder_accepts_utf8_bom_and_rejects_invalid_bytes(tmp_path: Path) -> None:
    """严格 decoder 应规范 BOM，并让非法 bytes typed fail。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: decode contract 不满足时抛出。
    """

    assert decode_source_bytes(b"\xef\xbb\xbfhello") == "hello"
    valid_path = tmp_path / "valid.html"
    valid_path.write_bytes("财报".encode("utf-8"))
    assert read_source_path_text(valid_path) == "财报"
    assert _load_text(valid_path) == "财报"

    invalid_path = tmp_path / "invalid.html"
    invalid_path.write_bytes(b"valid\xffinvalid")
    with pytest.raises(FinsSourceDecodeError) as error_info:
        read_source_path_text(invalid_path)
    assert isinstance(error_info.value.__cause__, UnicodeDecodeError)
    assert "invalid.html" not in str(error_info.value)
    assert "\\xff" not in str(error_info.value)


def test_strict_source_decoder_wraps_materialize_and_path_read_failures(tmp_path: Path) -> None:
    """materialize/read 失败不得返回空文本。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: typed failure 或 cause 不正确时抛出。
    """

    with pytest.raises(FinsSourceDecodeError) as materialize_error:
        materialize_source_text(_MemorySource(b"payload"), suffix=".html")
    assert isinstance(materialize_error.value.__cause__, OSError)

    with pytest.raises(FinsSourceDecodeError) as read_error:
        read_source_path_text(tmp_path / "missing.html")
    assert isinstance(read_error.value.__cause__, OSError)


def test_report_fallback_and_source_validation_share_strict_decoder(tmp_path: Path) -> None:
    """report fallback 与 registry 前校验应共享严格 decoder。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 非法 UTF-8 未 typed fail 时抛出。
    """

    invalid_path = tmp_path / "report.html"
    invalid_path.write_bytes(b"<html>\xff</html>")
    source = LocalFileSource(path=invalid_path, uri="local://report.html", media_type="text/html")
    with pytest.raises(FinsSourceDecodeError):
        _extract_source_text_preserving_lines(source)
    with pytest.raises(FinsSourceDecodeError):
        validate_source_utf8_text(source)

    binary_path = tmp_path / "report.pdf"
    binary_path.write_bytes(b"\xff")
    binary_source = LocalFileSource(path=binary_path, uri="local://report.pdf", media_type="application/pdf")
    validate_source_utf8_text(binary_source)


def test_virtual_section_refresh_rebuilds_final_indexes_and_bidirectional_tables() -> None:
    """refresh 应让 section object/index/table 双向状态同源。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: refresh 后状态不一致时抛出。
    """

    harness = _VirtualHarness()
    expected = harness._virtual_section_identity_multiset()
    harness._virtual_sections.reverse()
    harness._refresh_virtual_section_state(expected_identity_multiset=expected)

    alpha = next(section for section in harness._virtual_sections if section.ref == "s_alpha")
    assert harness._virtual_section_by_ref["s_alpha"] is alpha
    assert alpha.table_refs == ["t_0001"]
    assert harness._table_ref_to_virtual_ref == {"t_0001": "s_alpha"}


def test_virtual_section_refresh_fails_closed_for_duplicate_or_dangling_refs() -> None:
    """duplicate section 与无法分配 table 都应 fail closed。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 非法状态未被拒绝时抛出。
    """

    duplicate = _VirtualHarness()
    duplicate._virtual_sections[1].ref = "s_alpha"
    with pytest.raises(ValueError, match="ref 重复"):
        duplicate._refresh_virtual_section_state()

    dangling = _VirtualHarness(include_table_marker=False)
    with pytest.raises(ValueError, match="无法分配"):
        dangling._refresh_virtual_section_state()


@pytest.mark.parametrize(
    ("processor_type", "module_path"),
    [
        (TenQFormProcessor, "dayu.fins.processors.ten_q_processor.expand_ten_q_virtual_sections_content"),
        (BsTenQFormProcessor, "dayu.fins.processors.bs_ten_q_processor.expand_ten_q_virtual_sections_content"),
    ],
)
def test_both_ten_q_paths_preserve_object_ref_multiset_and_refresh(
    monkeypatch: pytest.MonkeyPatch,
    processor_type: type[TenQFormProcessor] | type[BsTenQFormProcessor],
    module_path: str,
) -> None:
    """edgartools/BS 10-Q postprocess 都应保持 object/ref 并刷新最终状态。

    Args:
        monkeypatch: pytest monkeypatch fixture。
        processor_type: 待调用的 10-Q processor 类型。
        module_path: expansion 符号路径。

    Returns:
        无。

    Raises:
        AssertionError: 任一路径未保持/刷新状态时抛出。
    """

    harness = _VirtualHarness()
    before = harness._virtual_section_identity_multiset()
    monkeypatch.setattr(module_path, _mutate_existing_ten_q_sections)
    processor = _build_virtual_postprocess_probe(processor_type, harness, monkeypatch)
    processor._postprocess_virtual_sections(harness.get_full_text())

    assert processor._virtual_section_identity_multiset() == before
    assert processor._virtual_section_by_ref["s_alpha"] is next(
        section for section in processor._virtual_sections if section.ref == "s_alpha"
    )
    assert processor._table_ref_to_virtual_ref == {"t_0001": "s_alpha"}


def test_ten_q_path_rejects_expansion_that_creates_section(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """10-Q expansion 创建新 ref 时必须在 refresh owner fail closed。

    Args:
        monkeypatch: pytest monkeypatch fixture。

    Returns:
        无。

    Raises:
        AssertionError: 新 section 未被拒绝时抛出。
    """

    harness = _VirtualHarness()
    processor = _build_virtual_postprocess_probe(TenQFormProcessor, harness, monkeypatch)
    monkeypatch.setattr(
        "dayu.fins.processors.ten_q_processor.expand_ten_q_virtual_sections_content",
        _append_virtual_section,
    )
    with pytest.raises(ValueError, match="不得创建"):
        processor._postprocess_virtual_sections(harness.get_full_text())


@pytest.mark.parametrize(
    ("processor_type", "module_path"),
    [
        (TenKFormProcessor, "dayu.fins.processors.ten_k_processor.expand_ten_k_virtual_sections_content"),
        (BsTenKFormProcessor, "dayu.fins.processors.bs_ten_k_processor.expand_ten_k_virtual_sections_content"),
    ],
)
def test_both_ten_k_paths_migrate_to_shared_refresh_without_behavior_drift(
    monkeypatch: pytest.MonkeyPatch,
    processor_type: type[TenKFormProcessor] | type[BsTenKFormProcessor],
    module_path: str,
) -> None:
    """edgartools/BS 10-K postprocess 应复用 refresh 并保持既有 section/table。

    Args:
        monkeypatch: pytest monkeypatch fixture。
        processor_type: 待调用的 10-K processor 类型。
        module_path: expansion 符号路径。

    Returns:
        无。

    Raises:
        AssertionError: 10-K 迁移后状态发生漂移时抛出。
    """

    harness = _VirtualHarness()
    before = harness._virtual_section_identity_multiset()
    monkeypatch.setattr(module_path, _preserve_virtual_sections)
    processor = _build_virtual_postprocess_probe(processor_type, harness, monkeypatch)
    processor._postprocess_virtual_sections(harness.get_full_text())

    assert processor._virtual_section_identity_multiset() == before
    assert processor._table_ref_to_virtual_ref == {"t_0001": "s_alpha"}


def test_processor_cache_reuses_equal_revision_and_rebuilds_after_source_change(tmp_path: Path) -> None:
    """processor cache 只应复用 revision 相等的实例。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: cache reuse/rebuild 次数不正确时抛出。
    """

    runtime, repository, registry = _build_runtime(tmp_path)
    first = runtime._get_or_create_processor(ticker="AAPL", document_id="doc-1")
    assert runtime._get_or_create_processor(ticker="AAPL", document_id="doc-1") is first
    assert registry.create_count == 1

    repository.payload = b"version-two"
    _update_source(repository, fingerprint="revision-two")
    second = runtime._get_or_create_processor(ticker="AAPL", document_id="doc-1")
    assert second is not first
    assert isinstance(second, _ReadProcessor)
    assert second.label == "version-two"
    assert registry.create_count == 2


def test_read_runtime_maps_invalid_utf8_to_source_decode_failure(tmp_path: Path) -> None:
    """read runtime 应在 registry 前把非法 UTF-8 映射为 typed failure。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: failure code、cause 或 cache 状态不正确时抛出。
    """

    runtime, repository, registry = _build_runtime(tmp_path)
    repository.payload = b"valid\xffinvalid"

    with pytest.raises(FinsReadBusinessError) as error_info:
        runtime._get_or_create_processor(ticker="AAPL", document_id="doc-1")

    assert error_info.value.code is ErrorCode.SOURCE_DECODE_FAILED
    assert isinstance(error_info.value.__cause__, FinsSourceDecodeError)
    assert registry.create_count == 0
    assert runtime._processor_cache.size() == 0


def test_independent_meta_cache_compares_revision_and_evicts_old_processor(tmp_path: Path) -> None:
    """独立 meta 路径应刷新 meta 并驱逐同 revision owner 的旧 processor。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: meta/processor cache 未同步失效时抛出。
    """

    runtime, repository, _registry = _build_runtime(tmp_path)
    runtime._get_or_create_processor(ticker="AAPL", document_id="doc-1")
    assert runtime._get_source_meta_cached_by_kind("AAPL", "doc-1", SourceKind.FILING)["form_type"] == "10-K"

    _update_source(repository, fingerprint="meta-revision-two", form_type="10-Q")
    refreshed = runtime._get_source_meta_cached_by_kind("AAPL", "doc-1", SourceKind.FILING)
    assert refreshed["form_type"] == "10-Q"
    assert runtime._processor_cache.size() == 0


def test_cross_document_diagnosis_does_not_reuse_stale_cached_processor(tmp_path: Path) -> None:
    """cross-document 诊断也只能消费 revision 匹配的 processor cache。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: stale processor 被用于 locator 诊断时抛出。
    """

    runtime, repository, _registry = _build_runtime(tmp_path)
    create_batch = repository._batching_repository.begin_batch("AAPL")
    file_meta = repository._blob_repository.store_file(
        SourceHandle("AAPL", "doc-2", SourceKind.FILING.value),
        "doc-2.txt",
        BytesIO(b"version-one"),
        batch=create_batch,
        content_type="text/plain",
    )
    repository.create_source_document(
        SourceDocumentUpsertRequest(
            ticker="AAPL",
            document_id="doc-2",
            internal_document_id="doc-2",
            form_type="10-K",
            primary_document="doc-2.txt",
            files=[file_meta],
            meta={
                "ingest_method": "download",
                "source_provider": FinsSourceProvider.SEC_EDGAR.to_storage_value(),
                "ingest_complete": True,
                "is_deleted": False,
                "source_fingerprint": "doc-2-revision-one",
            },
        ),
        SourceKind.FILING,
        batch=create_batch,
    )
    repository._batching_repository.commit_batch(create_batch)
    runtime._get_or_create_processor(ticker="AAPL", document_id="doc-2")
    _update_source(repository, fingerprint="doc-2-revision-two", document_id="doc-2")

    assert runtime._diagnose_cross_document_locator(
        ticker="AAPL",
        current_document_id="doc-1",
        kind="ref",
        locator="s_0001",
    ) is None
    assert runtime._processor_cache.size() == 0


def test_processor_build_revision_race_has_zero_retry_and_no_cache_artifact(tmp_path: Path) -> None:
    """processor build 期间 revision 变化应立即 typed fail，固定零 retry。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: failure code、构建次数或 cache 状态不正确时抛出。
    """

    runtime, repository, registry = _build_runtime(tmp_path)
    registry.before_return = lambda: _update_source(repository, fingerprint="revision-during-build")

    with pytest.raises(FinsReadBusinessError) as error_info:
        runtime._get_or_create_processor(ticker="AAPL", document_id="doc-1")

    assert error_info.value.code is ErrorCode.SOURCE_CHANGED_DURING_READ
    assert registry.create_count == 1
    assert runtime._processor_cache.size() == 0
    assert runtime._meta_cache.size() == 0


def test_independent_meta_revision_race_has_zero_retry_and_no_cache_artifact(tmp_path: Path) -> None:
    """meta read 期间 revision 变化应立即 typed fail，固定零 retry。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: failure code、读取次数或 cache 状态不正确时抛出。
    """

    runtime, repository, _registry = _build_runtime(tmp_path)
    repository.get_source_meta_calls = 0
    repository.mutate_on_next_meta_read = True

    with pytest.raises(FinsReadBusinessError) as error_info:
        runtime._get_source_meta_cached_by_kind("AAPL", "doc-1", SourceKind.FILING)

    assert error_info.value.code is ErrorCode.SOURCE_CHANGED_DURING_READ
    assert repository.get_source_meta_calls == 1
    assert runtime._meta_cache.size() == 0
    assert runtime._processor_cache.size() == 0


def test_concurrent_reads_after_revision_change_build_one_processor(tmp_path: Path) -> None:
    """一次 revision 变化后的并发读取应只构建一个新 processor。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 并发构建次数或实例身份不正确时抛出。
    """

    runtime, repository, registry = _build_runtime(tmp_path)
    runtime._get_or_create_processor(ticker="AAPL", document_id="doc-1")
    repository.payload = b"version-concurrent"
    _update_source(repository, fingerprint="revision-concurrent")
    registry.delay_seconds = 0.05

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(partial(_read_runtime_processor, runtime), range(2)))

    assert results[0] is results[1]
    assert registry.create_count == 2


def test_cached_processor_is_not_returned_after_source_deleted(tmp_path: Path) -> None:
    """source 删除后不得返回旧 processor。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 删除后仍返回 cache 或 cache 未清理时抛出。
    """

    runtime, repository, _registry = _build_runtime(tmp_path)
    runtime._get_or_create_processor(ticker="AAPL", document_id="doc-1")
    delete_batch = repository._batching_repository.begin_batch("AAPL")
    repository.delete_source_document(
        SourceDocumentStateChangeRequest("AAPL", "doc-1", SourceKind.FILING.value),
        batch=delete_batch,
    )
    repository._batching_repository.commit_batch(delete_batch)

    with pytest.raises(FileNotFoundError):
        runtime._get_or_create_processor(ticker="AAPL", document_id="doc-1")
    assert runtime._processor_cache.size() == 0


@pytest.mark.parametrize("stage", ["list", "enrichment", "bm25f", "profile"])
def test_search_index_stages_map_to_typed_failure_with_cause(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stage: str,
) -> None:
    """section/list/enrichment/BM25F/profile 异常都应映射 typed failure。

    Args:
        tmp_path: pytest 临时目录。
        monkeypatch: pytest monkeypatch fixture。
        stage: 注入失败的 index stage。

    Returns:
        无。

    Raises:
        AssertionError: failure code 或 cause 不正确时抛出。
    """

    runtime, _repository, registry = _build_runtime(tmp_path)
    processor = _ReadProcessor(_MemorySource(b"search"))
    sentinel = RuntimeError(f"{stage} sentinel")
    registry.before_return = None

    registry.fixed_processor = processor
    if stage == "list":
        processor.list_sections_error = sentinel
    elif stage == "enrichment":
        monkeypatch.setattr(
            runtime,
            "_enrich_sections_with_semantic",
            partial(_raise_search_enrichment_failure, sentinel),
        )
    elif stage == "bm25f":
        monkeypatch.setattr(
            "dayu.fins.tools.read_runtime.build_section_bm25f_index",
            partial(_raise_search_stage_failure, sentinel),
        )
    else:
        monkeypatch.setattr(
            "dayu.fins.tools.read_runtime._build_section_semantic_profiles",
            partial(_raise_search_stage_failure, sentinel),
        )

    with pytest.raises(FinsReadBusinessError) as error_info:
        runtime.search_document(ticker="AAPL", document_id="doc-1", query="revenue")

    assert error_info.value.code is ErrorCode.SEARCH_INDEX_FAILED
    assert error_info.value.__cause__ is sentinel


def test_search_index_failure_preserves_cancellation_priority(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """index 异常与取消同时发生时应优先投影取消。

    Args:
        tmp_path: pytest 临时目录。
        monkeypatch: pytest monkeypatch fixture。

    Returns:
        无。

    Raises:
        AssertionError: 异常被错误映射为 search failure 时抛出。
    """

    runtime, _repository, registry = _build_runtime(tmp_path)
    processor = _ReadProcessor(_MemorySource(b"search"))
    token = _ManualCancellationToken()
    processor.before_list_sections = token.cancel
    processor.list_sections_error = RuntimeError("search and cancel")
    registry.fixed_processor = processor

    with pytest.raises(FinsReadCancelledError):
        runtime.search_document(
            ticker="AAPL",
            document_id="doc-1",
            query="revenue",
            cancellation_token=token,
        )
