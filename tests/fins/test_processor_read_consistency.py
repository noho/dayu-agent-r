"""S2 processor/read 一致性与 typed failure 契约测试。"""

from __future__ import annotations

import gc
import hashlib
import json
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from functools import partial
from io import BytesIO
from pathlib import Path
from threading import Barrier, Event, Lock
from typing import Final

import pytest

from tests.fins.company_meta_test_support import stage_company_meta_fixture
import pandas as pd

import dayu.fins.storage._fs_source_snapshot as source_snapshot_module
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
from dayu.fins.ticker_normalization import build_company_ticker_identity
from dayu.fins.domain.document_models import (
    CompanyMeta,
    FinsSourceProvider,
    SourceHandle,
    SourceDocumentStateChangeRequest,
    SourceDocumentUpsertRequest,
    now_iso8601,
)
from dayu.fins.domain.enums import SourceKind
from dayu.fins.direct_events import FinsEventType, FinsResultStatus
from dayu.fins.ingestion_runtime import FinsUploadFilingRequest
from dayu.fins.processors.bs_ten_q_processor import BsTenQFormProcessor
from dayu.fins.processors.bs_ten_k_processor import BsTenKFormProcessor
from dayu.fins.processors.sec_form_section_common import (
    _VirtualSection,
    _VirtualSectionPublicationMode,
    _VirtualSectionProcessorMixin,
)
from dayu.fins.processors.sec_processor import SecProcessor, _load_text
from dayu.fins.processors.sec_report_form_common import (
    _EdgarSectionLike,
    _extract_source_text_preserving_lines,
    _find_table_of_contents_cutoff,
    _looks_like_inline_toc_snippet,
    _rebuild_virtual_sections_from_edgartools,
)
from dayu.fins.processors.sec_section_build import _build_sections
from dayu.fins.processors.sec_table_extraction import (
    _render_records_from_markdown_table,
    _render_records_table,
    _replace_table_with_placeholder,
)
from dayu.fins.processors.source_text import (
    FinsSourceDecodeError,
    decode_source_bytes,
    materialize_source_text,
    read_source_path_text,
    validate_source_utf8_text,
)
from dayu.fins.processors.ten_q_processor import TenQFormProcessor
from dayu.fins.processors.ten_k_processor import TenKFormProcessor
from dayu.fins.pipelines.docling_process_converter import (
    DoclingConversionConfig,
    DoclingConversionResult,
)
from dayu.fins.pipelines.sec_pipeline import SecPipeline
from dayu.fins.service_runtime import (
    DefaultFinsRuntime,
    prevalidate_fins_upload_filing_request_for_workspace,
)
from dayu.fins.storage import (
    FsBatchingRepository,
    FsCompanyMetaRepository,
    FsDocumentBlobRepository,
    FsProcessedDocumentRepository,
    FsSourceDocumentRepository,
    SourceIntegrityStatus,
)
from dayu.fins.storage._fs_repository_factory import _FsRepositorySet, build_fs_repository_set
from dayu.fins.storage.local_file_source import LocalFileSource
from dayu.fins.storage.repository_protocols import SourceSnapshotProtocol
from dayu.fins.tools.error_contract import ErrorCode
from dayu.fins.tools.cache import ProcessorCacheKey
from dayu.fins.tools.read_runtime import FinsReadRuntime
from dayu.fins.tools.read_runtime_helpers import (
    FinsReadArgumentError,
    FinsReadBusinessError,
    FinsReadCancelledError,
)
from dayu.service.fins_direct import FinsDirectCommandService

_LOCK_REGISTRY_CACHE_CAPACITY: Final[int] = 4


class _RepairPrimaryConverter:
    """为 workflow/downstream 测试生成逐次不同的 Docling primary。"""

    def __init__(self) -> None:
        """初始化空转换记录。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        self.calls: list[str] = []

    async def convert_to_json_bytes(
        self,
        input_bytes: bytes,
        stream_name: str,
        *,
        config: DoclingConversionConfig,
        cancellation: CancellationToken | None,
    ) -> DoclingConversionResult:
        """返回包含本次转换序号的确定性 Docling bytes。

        Args:
            input_bytes: authoritative primary bytes。
            stream_name: public input basename。
            config: 闭合转换配置。
            cancellation: canonical cancellation token。

        Returns:
            digest 与 size 同源的 typed conversion result。

        Raises:
            无。
        """

        del input_bytes, config, cancellation
        self.calls.append(stream_name)
        payload = json.dumps(
            {
                "name": stream_name,
                "format": "docling",
                "version": f"repair-primary-v{len(self.calls)}",
            },
            separators=(",", ":"),
        ).encode()
        return DoclingConversionResult(
            json_bytes=payload,
            size=len(payload),
            sha256=hashlib.sha256(payload).hexdigest(),
        )


def test_shared_converter_utf8_json_fixture_is_readable_by_source_decoder() -> None:
    """shared converter 的唯一 JSON bytes 必须可被 process/read 解码链消费。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: UTF-8、digest 或 JSON 读取契约漂移时抛出。
    """

    json_bytes = json.dumps(
        {"document": "年度财报", "tables": []},
        ensure_ascii=False,
    ).encode("utf-8")
    fixture = DoclingConversionResult(
        json_bytes=json_bytes,
        size=len(json_bytes),
        sha256=hashlib.sha256(json_bytes).hexdigest(),
    )

    decoded = decode_source_bytes(fixture.json_bytes)
    assert json.loads(decoded) == {"document": "年度财报", "tables": []}


def test_web_fetch_docling_import_graph_remains_documents_only() -> None:
    """web fetch 的 Docling 路径不得反向依赖 Fins shared converter。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: web import graph 被迁入 Fins owner 时抛出。
    """

    source = Path("dayu/tools/web/web_fetch_orchestrator.py").read_text(encoding="utf-8")
    assert "from dayu.documents.docling_runtime import" in source
    assert "dayu.fins.pipelines.docling_process_converter" not in source


_LOCK_REGISTRY_MISSING_KEY_COUNT: Final[int] = 64
_LOCK_REGISTRY_VALID_DOCUMENT_COUNT: Final[int] = 12


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


@dataclass(slots=True)
class _DataFrameTableFixture:
    """提供稳定 DataFrame 的 SEC 表格 owner fixture。"""

    dataframe: pd.DataFrame
    col_count: int

    def to_dataframe(self) -> pd.DataFrame:
        """返回独立 DataFrame；参数：无；返回：表格副本；异常：无。"""

        return self.dataframe.copy()

    def to_dict(self) -> dict[str, str]:
        """返回最小字典表示；参数：无；返回：fixture 标识；异常：无。"""

        return {"fixture": "dataframe"}


@dataclass(frozen=True, slots=True)
class _HtmlTableFixture:
    """只提供 HTML 结构的 SEC 表格 owner fixture。"""

    html: str
    col_count: int

    def to_dict(self) -> dict[str, str]:
        """返回最小字典表示；参数：无；返回：fixture 标识；异常：无。"""

        return {"fixture": "html"}


@dataclass(frozen=True, slots=True)
class _MarkdownTableFixture:
    """只允许 fallback Markdown 的 SEC 表格 owner fixture。"""

    col_count: int

    def to_dict(self) -> dict[str, str]:
        """返回最小字典表示；参数：无；返回：fixture 标识；异常：无。"""

        return {"fixture": "markdown"}


@dataclass(frozen=True, slots=True)
class _EdgarSectionFixture:
    """提供文本、标题与空表集合的 edgartools section fixture。"""

    content: str
    title: str | None
    name: str | None = None
    part: str | None = None
    item: str | None = None

    def text(self) -> str:
        """返回章节文本；参数：无；返回：固定内容；异常：无。"""

        return self.content

    def tables(self) -> tuple[_DataFrameTableFixture, ...]:
        """返回空表集合；参数：无；返回：空 tuple；异常：无。"""

        return ()


@dataclass(slots=True)
class _EdgarDocumentFixture:
    """提供 sections、全文和稳定 anchor sequence 的 edgartools 文档 fixture。"""

    sections: dict[str, _EdgarSectionLike]
    full_text: str

    def text(self) -> str:
        """返回文档全文；参数：无；返回：固定全文；异常：无。"""

        return self.full_text

    def get_sec_section_info(self, section_key: str) -> dict[str, str]:
        """返回章节 anchor；参数：章节键；返回：稳定 anchor id；异常：无。"""

        sequence = "2" if section_key == "first" else "1"
        return {"anchor_id": f"section_{sequence}"}


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
        self.before_read_section: Callable[[], None] | None = None

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
        if self.before_read_section is not None:
            self.before_read_section()
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


class _FinancialReadProcessor(_ReadProcessor):
    """为 borrowed-snapshot 一致性测试提供财务报表能力。"""

    def __init__(
        self,
        source: Source,
        *,
        form_type: str | None = None,
        media_type: str | None = None,
    ) -> None:
        """读取 source 标签并初始化财务调用暂停点。

        Args:
            source: processor 输入 source。
            form_type: 可选表单类型。
            media_type: 可选媒体类型。

        Returns:
            无。

        Raises:
            OSError: source 无法读取时抛出。
        """

        super().__init__(source, form_type=form_type, media_type=media_type)
        self.before_get_financial_statement: Callable[[], None] | None = None

    def get_financial_statement(self, statement_type: str) -> dict[str, JsonValue]:
        """返回携带当前 snapshot 标签的有效财务报表。

        Args:
            statement_type: 请求的报表类型。

        Returns:
            满足领域契约的财务报表载荷。

        Raises:
            AssertionError: 测试暂停点等待失败时抛出。
        """

        if self.before_get_financial_statement is not None:
            self.before_get_financial_statement()
        return {
            "statement_type": statement_type,
            "periods": [
                {
                    "period_end": "2024-09-28",
                    "fiscal_year": 2024,
                    "fiscal_period": "FY",
                }
            ],
            "rows": [{"source_label": self.label, "value": 100}],
            "currency": "USD",
            "units": "USD",
            "scale": "units",
            "data_quality": "extracted",
        }


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
        self.processor_type: type[_ReadProcessor] = _ReadProcessor
        self.before_return: Callable[[], None] | None = None
        self.fixed_processor: DocumentProcessor | None = None
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
        with source.open() as stream:
            label = stream.read().decode("utf-8")
        processor = self.processor_type(_MemorySource(label.encode("utf-8")))
        self.created.append(processor)
        return processor


class _RevisionProbeRepository(FsSourceDocumentRepository):
    """记录 read runtime snapshot 调用与 full snapshot 临时根的仓储探针。"""

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
        self.snapshot_read_calls = 0
        self.full_snapshot_roots: list[Path] = []
        self.on_full_snapshot: Callable[[int], None] | None = None
        self._snapshot_probe_lock = Lock()

    def read_source_snapshot(
        self,
        ticker: str,
        document_id: str,
        source_kind: SourceKind | None = None,
        *,
        materialize_files: bool,
    ) -> SourceSnapshotProtocol:
        """读取真实 storage snapshot，并记录调用与 full snapshot 临时根。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。
            source_kind: 可选 source kind。
            materialize_files: 是否物化业务文件。

        Returns:
            真实 storage snapshot。

        Raises:
            FileNotFoundError: source 不存在时抛出。
            ValueError: snapshot 非法时抛出。
            OSError: snapshot I/O 失败时抛出。
        """

        with self._snapshot_probe_lock:
            self.snapshot_read_calls += 1
        snapshot = super().read_source_snapshot(
            ticker,
            document_id,
            source_kind,
            materialize_files=materialize_files,
        )
        if materialize_files:
            root = snapshot.get_primary_source().materialize().parent
            with self._snapshot_probe_lock:
                self.full_snapshot_roots.append(root)
                full_snapshot_count = len(self.full_snapshot_roots)
            if self.on_full_snapshot is not None:
                self.on_full_snapshot(full_snapshot_count)
        return snapshot


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
    _base_sections: list[SectionSummary]
    _base_section_contents: dict[str, SectionContent]
    base_list_tables_call_count: int

    def list_sections(self) -> list[SectionSummary]:
        """返回空底层章节。

        Args:
            无。

        Returns:
            空列表。

        Raises:
            无。
        """

        return [section.copy() for section in self._base_sections]

    def read_section(self, ref: str) -> SectionContent:
        """拒绝底层章节读取。

        Args:
            ref: 章节 ref。

        Returns:
            不返回。

        Raises:
            KeyError: 始终抛出。
        """

        payload = self._base_section_contents.get(ref)
        if payload is None:
            raise KeyError(ref)
        return payload.copy()

    def list_tables(self) -> list[TableSummary]:
        """返回 harness 配置的底层表格。

        Args:
            无。

        Returns:
            底层表格列表。

        Raises:
            无。
        """

        self.base_list_tables_call_count += 1
        return [table.copy() for table in self._base_tables]

    def get_section_title(self, ref: str) -> str | None:
        """返回空标题。

        Args:
            ref: 章节 ref。

        Returns:
            始终返回 ``None``。

        Raises:
            无。
        """

        for section in self._base_sections:
            if section["ref"] == ref:
                return section["title"]
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

        normalized_query = query.casefold()
        hits: list[SearchHit] = []
        for section in self._base_sections:
            section_ref = section["ref"]
            if within_ref is not None and section_ref != within_ref:
                continue
            payload = self._base_section_contents[section_ref]
            content = str(payload["content"])
            if normalized_query not in content.casefold():
                continue
            hits.append(
                {
                    "section_ref": section_ref,
                    "section_title": section["title"],
                    "snippet": content,
                }
            )
        return hits


class _VirtualHarness(_VirtualSectionProcessorMixin, _VirtualBaseProcessor):
    """直接测试 virtual section refresh owner 的 harness。"""

    def __init__(
        self,
        *,
        include_table_marker: bool = True,
        base_table_refs: tuple[str, ...] = ("t_0001",),
        marked_text: str | None = None,
        marked_markers: list[tuple[int, str | None]] | None = None,
        virtual_sections: list[_VirtualSection] | None = None,
    ) -> None:
        """初始化两章节 harness。

        Args:
            include_table_marker: 默认 marked text 是否包含首张底层 table ref。
            base_table_refs: 底层公开 table refs，按公开顺序提供。
            marked_text: 可选的精确 marker material。
            marked_markers: 可选的精确章节 marker ranges 输入。
            virtual_sections: 可选的候选虚拟章节。

        Returns:
            无。

        Raises:
            无。
        """

        self._virtual_section_publication_mode = _VirtualSectionPublicationMode.BUILDING
        self._virtual_sections = virtual_sections or [
            _VirtualSection("s_alpha", "Alpha", "alpha body", "alpha", [], start=0, end=20),
            _VirtualSection("s_beta", "Beta", "beta body", "beta", [], start=20, end=40),
        ]
        self._virtual_section_by_ref = {}
        self._table_ref_to_virtual_ref = {}
        default_marker = f"[[{base_table_refs[0]}]]\n" if include_table_marker and base_table_refs else ""
        self._marked_text = marked_text if marked_text is not None else f"Alpha\n{default_marker}Beta\n"
        self._marked_markers = marked_markers
        self.marker_call_count = 0
        self.base_list_tables_call_count = 0
        self._base_sections = [
            {
                "ref": "base_alpha",
                "title": "Base Alpha",
                "level": 1,
                "parent_ref": None,
                "preview": "base alpha",
            },
            {
                "ref": "base_beta",
                "title": "Base Beta",
                "level": 1,
                "parent_ref": None,
                "preview": "base beta",
            },
        ]
        self._base_tables = [
            {
                "table_ref": table_ref,
                "caption": None,
                "context_before": "",
                "row_count": 1,
                "col_count": 1,
                "table_type": "data",
                "headers": None,
                "section_ref": "base_alpha" if index == 0 else "base_beta",
            }
            for index, table_ref in enumerate(base_table_refs)
        ]
        self._base_section_contents = {
            "base_alpha": {
                "ref": "base_alpha",
                "title": "Base Alpha",
                "content": "base alpha content",
                "tables": [base_table_refs[0]] if base_table_refs else [],
                "word_count": 3,
                "contains_full_text": False,
            },
            "base_beta": {
                "ref": "base_beta",
                "title": "Base Beta",
                "content": "base beta content",
                "tables": list(base_table_refs[1:]),
                "word_count": 3,
                "contains_full_text": False,
            },
        }

    def _build_markers(self, full_text: str) -> list[tuple[int, str | None]]:
        """按 Alpha/Beta 标题返回测试 marker。

        Args:
            full_text: 标记全文。

        Returns:
            两个稳定 marker。

        Raises:
            ValueError: 测试全文缺少 Beta 时抛出。
        """

        if self._marked_markers is not None:
            return list(self._marked_markers)
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

        self.marker_call_count += 1
        return self._marked_text


def _assert_virtual_harness_matches_base_contract(harness: _VirtualHarness) -> None:
    """逐值验证 harness 的五个 public consumers 委托同一 base contract。

    Args:
        harness: 已发布 whole-base fallback 的 owner harness。

    Returns:
        无。

    Raises:
        AssertionError: 任一 public consumer 未完整委托底层真源时抛出。
    """

    base_sections = _VirtualBaseProcessor.list_sections(harness)
    base_tables = _VirtualBaseProcessor.list_tables(harness)
    assert harness.list_sections() == base_sections
    assert harness.list_tables() == base_tables
    for section in base_sections:
        section_ref = section["ref"]
        assert harness.get_section_title(section_ref) == _VirtualBaseProcessor.get_section_title(
            harness,
            section_ref,
        )
        assert harness.read_section(section_ref) == _VirtualBaseProcessor.read_section(harness, section_ref)
        assert harness.search("alpha", within_ref=section_ref) == _VirtualBaseProcessor.search(
            harness,
            "alpha",
            within_ref=section_ref,
        )


def _build_runtime(
    tmp_path: Path,
    *,
    processor_cache_max_entries: int = 128,
) -> tuple[FinsReadRuntime, _RevisionProbeRepository, _CountingProcessorRegistry]:
    """构造真实 storage + 探针 processor 的 read runtime。

    Args:
        tmp_path: pytest 临时目录。
        processor_cache_max_entries: processor LRU cache 容量。

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
    stage_company_meta_fixture(
        company_repository,
        CompanyMeta(
            company_id="0000320193",
            company_name="Apple Inc.",
            ticker_identity=build_company_ticker_identity("AAPL", ()),
            resolver_version="test",
            updated_at=now_iso8601(),
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
                ),
                source_repository._blob_repository.store_file(
                    SourceHandle("AAPL", "doc-1", SourceKind.FILING.value),
                    "doc-1-related.txt",
                    BytesIO(b"related:version-one"),
                    batch=batch,
                    content_type="text/plain",
                ),
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
        processor_cache_max_entries=processor_cache_max_entries,
    )
    return runtime, source_repository, registry


def test_read_runtime_consumes_exact_opaque_primary_instead_of_original_or_companion(tmp_path: Path) -> None:
    """read runtime 必须只把 snapshot exact primary 交给 processor registry。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: read runtime 扫描 original/companion 或重选 primary 时抛出。
    """

    runtime, repository, registry = _build_runtime(tmp_path)
    original_name = f"original-{'a' * 64}.pdf"
    companion_name = f"original-{'b' * 64}.xsd"
    derived_name = f"{original_name}_docling.json"
    batch = repository._batching_repository.begin_batch("AAPL")
    try:
        repository.reset_source_document(
            ticker="AAPL",
            document_id="doc-1",
            source_kind=SourceKind.FILING,
            batch=batch,
        )
        handle = SourceHandle("AAPL", "doc-1", SourceKind.FILING.value)
        files = [
            repository._blob_repository.store_file(
                handle,
                original_name,
                BytesIO(b"original-must-not-be-selected"),
                batch=batch,
                content_type="application/pdf",
            ),
            repository._blob_repository.store_file(
                handle,
                companion_name,
                BytesIO(b"companion-must-not-be-selected"),
                batch=batch,
                content_type="application/xml",
            ),
            repository._blob_repository.store_file(
                handle,
                derived_name,
                BytesIO(b"exact-derived-primary"),
                batch=batch,
                content_type="application/json",
            ),
        ]
        repository.create_source_document(
            SourceDocumentUpsertRequest(
                ticker="AAPL",
                document_id="doc-1",
                internal_document_id="doc-1",
                form_type="10-K",
                primary_document=derived_name,
            file_entries=[
                {
                    "name": original_name,
                    "uri": files[0].uri,
                    "etag": files[0].etag,
                    "last_modified": files[0].last_modified,
                    "size": files[0].size,
                    "content_type": files[0].content_type,
                    "sha256": files[0].sha256,
                    "source": "original",
                    "original_filename": "primary.pdf",
                },
                {
                    "name": companion_name,
                    "uri": files[1].uri,
                    "etag": files[1].etag,
                    "last_modified": files[1].last_modified,
                    "size": files[1].size,
                    "content_type": files[1].content_type,
                    "sha256": files[1].sha256,
                    "source": "original",
                    "original_filename": "companion.xsd",
                },
                {
                    "name": derived_name,
                    "uri": files[2].uri,
                    "etag": files[2].etag,
                    "last_modified": files[2].last_modified,
                    "size": files[2].size,
                    "content_type": files[2].content_type,
                    "sha256": files[2].sha256,
                    "source": "docling",
                    "original_filename": "primary.pdf",
                    "derived_from": original_name,
                },
            ],
                meta={
                    "ingest_method": "upload",
                    "source_provider": FinsSourceProvider.USER_UPLOAD.to_storage_value(),
                    "ingest_complete": True,
                    "is_deleted": False,
                    "source_fingerprint": "opaque-primary",
                },
            ),
            SourceKind.FILING,
            batch=batch,
        )
    except BaseException:
        repository._batching_repository.rollback_batch(batch)
        raise
    repository._batching_repository.commit_batch(batch)

    result = runtime.get_document_sections(ticker="AAPL", document_id="doc-1")
    section = runtime.read_section(ticker="AAPL", document_id="doc-1", ref="s_0001")

    assert registry.create_count == 1
    assert [processor.label for processor in registry.created] == ["exact-derived-primary"]
    assert result["sections"][0]["title"] == "Overview"
    assert section["content"] == "exact-derived-primary"
    runtime.close()


@pytest.mark.asyncio
async def test_repaired_snapshot_and_process_entry_consume_only_new_primary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """repair 后 snapshot 与 process 入口必须只消费新发布的 exact primary。

    Args:
        tmp_path: 临时 workspace。
        monkeypatch: processor registry source spy 注入夹具。

    Returns:
        无。

    Raises:
        AssertionError: repair revision、snapshot primary 或 process 输入漂移时抛出。
        OSError: 真实 filesystem publication 读写失败时抛出。
        ValueError: persisted source contract 非法时抛出。
    """

    workspace_root = tmp_path / "repair-downstream"
    default_runtime = DefaultFinsRuntime.create(workspace_root=workspace_root)
    ingestion = default_runtime.get_ingestion_runtime()
    converter = _RepairPrimaryConverter()
    pipeline = SecPipeline(
        workspace_root=workspace_root,
        processor_registry=default_runtime.processor_registry,
        batching_repository=default_runtime.batching_repository,
        company_repository=default_runtime.company_repository,
        source_repository=default_runtime.source_repository,
        processed_repository=default_runtime.processed_repository,
        blob_repository=default_runtime.blob_repository,
        filing_maintenance_repository=default_runtime.filing_maintenance_repository,
        filing_upload_state_repository=default_runtime.filing_upload_state_repository,
        docling_converter=converter,
    )
    primary = tmp_path / "repair-process-primary.pdf"
    companion = tmp_path / "repair-process-companion.xlsx"
    primary.write_bytes(b"authoritative primary")
    companion.write_bytes(b"authoritative companion")
    raw_request = FinsUploadFilingRequest(
        ticker="AAPL",
        action="auto",
        files=(primary, companion),
        primary_selectors=(primary,),
        fiscal_year=2025,
        fiscal_period="Q1",
        company_name="Apple Inc.",
    )
    create_request = prevalidate_fins_upload_filing_request_for_workspace(
        raw_request,
        workspace_root=workspace_root,
    )
    create_events = [event async for event in pipeline.upload_filing_stream(create_request)]
    created = create_events[-1].payload["result"]
    assert isinstance(created, dict)
    assert created["status"] == "ok"
    document_id = create_request.document_id
    old_revision = default_runtime.source_repository.classify_source_integrity(
        "AAPL",
        document_id,
        SourceKind.FILING,
    ).revision
    source_meta = default_runtime.source_repository.get_source_meta(
        "AAPL",
        document_id,
        SourceKind.FILING,
    )
    old_primary = source_meta.get("primary_document")
    assert isinstance(old_primary, str)
    locator = default_runtime.source_repository.get_source_document_locator(
        "AAPL",
        document_id,
        SourceKind.FILING,
    )
    (workspace_root / locator / old_primary).unlink()
    with pytest.raises(ValueError, match="^source snapshot 只允许读取完整 source$"):
        default_runtime.source_repository.read_source_snapshot(
            "AAPL",
            document_id,
            SourceKind.FILING,
            materialize_files=False,
        )
    repair_request = prevalidate_fins_upload_filing_request_for_workspace(
        raw_request,
        workspace_root=workspace_root,
    )
    repair_events = [event async for event in pipeline.upload_filing_stream(repair_request)]
    repaired_result = repair_events[-1].payload["result"]
    assert isinstance(repaired_result, dict)
    assert repaired_result["status"] == "ok"
    repaired_integrity = default_runtime.source_repository.classify_source_integrity(
        "AAPL",
        document_id,
        SourceKind.FILING,
    )
    assert repaired_integrity.revision is not None
    assert repaired_integrity.revision != old_revision
    with default_runtime.source_repository.read_source_snapshot(
        "AAPL",
        document_id,
        SourceKind.FILING,
        materialize_files=True,
    ) as snapshot:
        with snapshot.get_primary_source().open() as stream:
            new_primary = stream.read()
        assert snapshot.revision == repaired_integrity.revision
        assert json.loads(new_primary.decode()) == {
            "name": primary.name,
            "format": "docling",
            "version": "repair-primary-v2",
        }

    processor_inputs: list[bytes] = []

    def observe_process_source(
        source: Source,
        *,
        form_type: str | None = None,
        media_type: str | None = None,
        on_fallback: Callable[[type[DocumentProcessor], Exception, int, int], None] | None = None,
    ) -> DocumentProcessor:
        """记录 process 入口收到的 snapshot exact primary 并委托真实 registry。

        Args:
            source: snapshot exact primary source。
            form_type: 可选 filing form type。
            media_type: 可选媒体类型。
            on_fallback: 可选 processor fallback callback。

        Returns:
            真实 registry 创建的 processor。

        Raises:
            OSError: source 读取失败时抛出。
            ValueError: registry 无候选时抛出。
            RuntimeError: processor 构建失败时抛出。
        """

        with source.open() as stream:
            processor_inputs.append(stream.read())
        return _ReadProcessor(
            source,
            form_type=form_type,
            media_type=media_type,
        )

    monkeypatch.setattr(
        ingestion.processor_registry,
        "create_with_fallback",
        observe_process_source,
    )
    service = FinsDirectCommandService(default_runtime)
    process_events = [
        event
        async for event in service.process_filing(
            ticker="AAPL",
            document_ids=(document_id,),
        )
    ]

    result_event = process_events[-1]
    assert result_event.event_type is FinsEventType.RESULT
    assert result_event.result is not None
    assert result_event.result.status is FinsResultStatus.SUCCESS
    assert result_event.result.exit_code == 0
    assert processor_inputs == [new_primary]
    post_process_integrity = default_runtime.source_repository.classify_source_integrity(
        "AAPL",
        document_id,
        SourceKind.FILING,
    )
    assert post_process_integrity.status is SourceIntegrityStatus.COMPLETE
    assert post_process_integrity.revision == repaired_integrity.revision
    assert converter.calls == [primary.name, primary.name]


def _update_source(
    repository: _RevisionProbeRepository,
    *,
    fingerprint: str,
    form_type: str = "10-K",
    document_id: str = "doc-1",
    payload: bytes | None = None,
    source_provider: FinsSourceProvider | None = None,
) -> None:
    """更新测试 source revision。

    Args:
        repository: source repository。
        fingerprint: 新 source fingerprint。
        form_type: 新表单类型。
        document_id: 待更新文档 ID。
        payload: 可选、随同一 publication 替换的主文件字节。
        source_provider: 可选、随同一 publication 更新的 provenance provider。

    Returns:
        无。

    Raises:
        OSError: source meta 更新失败时抛出。
    """

    batch = repository._batching_repository.begin_batch("AAPL")
    try:
        files = []
        primary_document = None
        if payload is not None:
            primary_document = f"{document_id}.txt"
            files = [
                repository._blob_repository.store_file(
                    SourceHandle("AAPL", document_id, SourceKind.FILING.value),
                    primary_document,
                    BytesIO(payload),
                    batch=batch,
                    content_type="text/plain",
                ),
                repository._blob_repository.store_file(
                    SourceHandle("AAPL", document_id, SourceKind.FILING.value),
                    f"{document_id}-related.txt",
                    BytesIO(b"related:" + payload),
                    batch=batch,
                    content_type="text/plain",
                ),
            ]
        meta: dict[str, JsonValue] = {"source_fingerprint": fingerprint}
        if source_provider is not None:
            meta["source_provider"] = source_provider.to_storage_value()
        repository.update_source_document(
            SourceDocumentUpsertRequest(
                ticker="AAPL",
                document_id=document_id,
                internal_document_id=document_id,
                form_type=form_type,
                primary_document=primary_document,
                files=files,
                meta=meta,
            ),
            SourceKind.FILING,
            batch=batch,
        )
    except Exception:
        repository._batching_repository.rollback_batch(batch)
        raise
    repository._batching_repository.commit_batch(batch)


def _create_test_source_documents(
    repository: _RevisionProbeRepository,
    document_ids: tuple[str, ...],
) -> None:
    """在一次真实 batch 中创建一组可读取的测试 source document。

    Args:
        repository: source repository 探针。
        document_ids: 待创建的 exact document ID 元组。

    Returns:
        无。

    Raises:
        OSError: source 文件写入或 batch publication 失败时抛出。
        ValueError: source contract 非法时抛出。
    """

    batch = repository._batching_repository.begin_batch("AAPL")
    try:
        for document_id in document_ids:
            filename = f"{document_id}.txt"
            payload = f"payload:{document_id}".encode("utf-8")
            file_meta = repository._blob_repository.store_file(
                SourceHandle("AAPL", document_id, SourceKind.FILING.value),
                filename,
                BytesIO(payload),
                batch=batch,
                content_type="text/plain",
            )
            repository.create_source_document(
                SourceDocumentUpsertRequest(
                    ticker="AAPL",
                    document_id=document_id,
                    internal_document_id=document_id,
                    form_type="10-K",
                    primary_document=filename,
                    files=[file_meta],
                    meta={
                        "ingest_method": "download",
                        "source_provider": FinsSourceProvider.SEC_EDGAR.to_storage_value(),
                        "ingest_complete": True,
                        "is_deleted": False,
                    },
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
        type[TenQFormProcessor] | type[BsTenQFormProcessor] | type[TenKFormProcessor] | type[BsTenKFormProcessor]
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
    if harness._virtual_section_publication_mode is _VirtualSectionPublicationMode.BUILDING:
        harness._refresh_virtual_section_state()
    processor._virtual_sections = harness._virtual_sections
    processor._virtual_section_by_ref = dict(harness._virtual_section_by_ref)
    processor._table_ref_to_virtual_ref = dict(harness._table_ref_to_virtual_ref)
    processor._virtual_section_publication_mode = harness._virtual_section_publication_mode
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

    del _index
    with runtime._borrow_processor(ticker="AAPL", document_id="doc-1") as borrow:
        return borrow.processor


def _read_runtime_processor_for_document(
    runtime: FinsReadRuntime,
    document_id: str,
) -> DocumentProcessor:
    """借用一次指定文档 processor 并返回其稳定实例身份。

    Args:
        runtime: 待读取的 read runtime。
        document_id: 文档 ID。

    Returns:
        当前 snapshot entry 的 processor。

    Raises:
        FinsReadBusinessError: storage snapshot 无法稳定读取时抛出。
        FileNotFoundError: source 不存在时抛出。
    """

    with runtime._borrow_processor(ticker="AAPL", document_id=document_id) as borrow:
        return borrow.processor


def _raise_processor_build_failure(failure: Exception) -> None:
    """在 processor registry 返回前抛出指定构建失败。

    Args:
        failure: 要保留身份并抛出的构建异常。

    Returns:
        不返回。

    Raises:
        Exception: 始终抛出传入 failure。
    """

    raise failure


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


def test_report_form_line_preserving_text_and_lazy_section_rebuild_share_owner(
    tmp_path: Path,
) -> None:
    """报告表单 fallback 应保留业务换行并从同源 edgartools sections 惰性重建。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: HTML 文本或惰性章节 owner 契约漂移时抛出。
    """

    html_path = tmp_path / "line-preserving.html"
    html_path.write_text(
        """<html><head><style>hidden style</style><script>hidden script</script></head>
<body><h1>Item 1. Business</h1><p>Revenue&nbsp;grew.</p>
<table><tr><th>Metric</th><th>2025</th></tr><tr><td>Revenue</td><td>100</td></tr></table>
<noscript>hidden fallback</noscript><h2>Item 1A. Risk Factors</h2><p>Market risk.</p></body></html>""",
        encoding="utf-8",
    )
    source = LocalFileSource(
        path=html_path,
        uri="local://line-preserving.html",
        media_type="text/html",
    )

    extracted = _extract_source_text_preserving_lines(source)

    assert extracted.splitlines() == [
        "Item 1. Business",
        "Revenue grew.",
        "Metric",
        "2025",
        "Revenue",
        "100",
        "Item 1A. Risk Factors",
        "Market risk.",
    ]
    assert "hidden" not in extracted

    document = _EdgarDocumentFixture(
        sections={
            "first": _EdgarSectionFixture(
                content="First section body with operating details. PART II",
                title="First Section",
            ),
            "empty": _EdgarSectionFixture(content="", title="Empty"),
            "second": _EdgarSectionFixture(
                content="Second section body with financial details.",
                title=None,
                part="I",
                item="2",
            ),
        },
        full_text="First section body. Second section body.",
    )

    rebuilt = _rebuild_virtual_sections_from_edgartools(document)
    assert [section.ref for section in rebuilt] == ["s_0001", "s_0003"]
    assert rebuilt[0].title == "First Section"
    assert rebuilt[0].content == "First section body with operating details."
    assert rebuilt[1].title == "Part I Item 2"

    fast_sections = _build_sections(document, fast_mode=True)
    assert [section.title for section in fast_sections] == ["Empty", "Part I Item 2", "First Section"]
    assert fast_sections[0].contains_full_text is False


def test_report_form_toc_detection_distinguishes_front_matter_and_late_notes() -> None:
    """报告表单 TOC owner 应跳过前置目录，但不误伤 notes 中的目录短语。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: TOC 截断或单行目录判断漂移时抛出。
    """

    front_matter = "Cover\nTable of Contents\n" + ("x" * 2000) + "\nItem 1. Business"
    late_notes = "Notes to the consolidated financial statements " + ("x" * 40) + " table of contents"

    assert _find_table_of_contents_cutoff("No directory marker") == 0
    assert _find_table_of_contents_cutoff(front_matter) > front_matter.index("Table of Contents")
    assert _find_table_of_contents_cutoff(late_notes) == 0
    assert _looks_like_inline_toc_snippet("Management Discussion 7 Item 7A Risk Factors", 0) is True
    assert _looks_like_inline_toc_snippet("Narrative without a page locator", 0) is False
    assert _looks_like_inline_toc_snippet("", 0) is False


def test_sec_table_records_owner_recovers_dataframe_index_multiheaders_and_ghost_columns() -> None:
    """SEC records owner 应恢复行标签、展平多级表头并合并 colspan 幽灵列。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: DataFrame 到 records 的业务投影丢失时抛出。
    """

    dataframe = pd.DataFrame(
        [
            ["Revenue", "$", "1,200[1]"],
            ["Costs", None, "(300)"],
        ],
        index=pd.Index(["North", "South"], name="Region"),
        columns=pd.MultiIndex.from_tuples(
            [
                ("Metric", ""),
                ("2025", "USD"),
                ("2025", "USD"),
            ]
        ),
    )
    fixture = _DataFrameTableFixture(dataframe=dataframe, col_count=4)

    payload = _render_records_table(
        fixture,
        allow_generated_columns=False,
        aggressive_fallback=False,
    )

    assert payload is not None
    assert payload["columns"] == ["Region", "Metric", "2025 | USD"]
    assert payload["data"] == [
        {"Region": "North", "Metric": "Revenue", "2025 | USD": "1200"},
        {"Region": "South", "Metric": "Costs", "2025 | USD": "-300"},
    ]


def test_sec_table_records_owner_uses_structured_html_and_markdown_fallbacks() -> None:
    """SEC records owner 应在 DataFrame 不可用时保留 HTML/Markdown 结构和数值语义。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 结构化 fallback 的列或记录漂移时抛出。
    """

    html_fixture = _HtmlTableFixture(
        html=(
            "<table><tr><th>Metric</th><th>Current Year</th></tr>"
            "<tr><td>Revenue</td><td>$1,200[1]</td></tr>"
            "<tr><td>Margin</td><td>12%</td></tr></table>"
        ),
        col_count=2,
    )
    html_payload = _render_records_table(
        html_fixture,
        allow_generated_columns=False,
        aggressive_fallback=True,
    )
    assert html_payload == {
        "columns": ["Metric", "Current Year"],
        "data": [
            {"Metric": "Revenue", "Current Year": "1200"},
            {"Metric": "Margin", "Current Year": "12%"},
        ],
    }

    markdown_payload = _render_records_table(
        _MarkdownTableFixture(col_count=2),
        fallback_text="| Metric | Prior Year |\n| --- | ---: |\n| Costs | (300) |",
        allow_generated_columns=False,
        aggressive_fallback=False,
    )
    assert markdown_payload == {
        "columns": ["Metric", "Prior Year"],
        "data": [{"Metric": "Costs", "Prior Year": "-300"}],
    }


def test_sec_table_fallback_owner_rejects_unstructured_markdown_and_short_placeholders() -> None:
    """SEC table fallback 不得把短文本或无结构 Markdown 伪造成可用表格。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 非结构化输入被误发布为表格时抛出。
    """

    content = "Narrative before a sufficiently long financial table payload and narrative after."
    table_text = "Revenue Current Year Prior Year 1200 1000"

    assert _replace_table_with_placeholder(content, "short table", "t_0001") == {
        "content": content,
        "replaced": False,
    }
    assert _replace_table_with_placeholder(content, table_text, "t_0001")["replaced"] is False
    embedded_content = f"Narrative {table_text} narrative"
    replaced = _replace_table_with_placeholder(embedded_content, table_text, "t_0001")
    assert replaced == {"content": "Narrative [[t_0001]] narrative", "replaced": True}

    assert _render_records_from_markdown_table(markdown_text="", allow_generated_columns=False) is None
    assert _render_records_from_markdown_table(markdown_text="plain text", allow_generated_columns=False) is None
    assert (
        _render_records_from_markdown_table(
            markdown_text="Metric | Value\nnot a separator | row\nRevenue | 100",
            allow_generated_columns=False,
        )
        is None
    )
    assert (
        _render_records_from_markdown_table(
            markdown_text="| Metric | Value |\n| --- | ---: |",
            allow_generated_columns=False,
        )
        is None
    )
    incomplete_header = "| | Value |\n| --- | ---: |\n| Revenue | 100 |"
    assert (
        _render_records_from_markdown_table(
            markdown_text=incomplete_header,
            allow_generated_columns=False,
        )
        is None
    )
    assert _render_records_from_markdown_table(
        markdown_text=incomplete_header,
        allow_generated_columns=True,
    ) == {
        "columns": ["col_1", "Value"],
        "data": [{"col_1": "Revenue", "Value": "100"}],
    }


def _assert_processor_matches_base_public_contract(
    processor: SecProcessor,
) -> None:
    """逐值验证 form processor 完整消费同源 base public contract。

    Args:
        processor: 已发布 base fallback 的 SEC form processor。

    Returns:
        无。

    Raises:
        AssertionError: 任一 section/table/title/read/search 事实不一致时抛出。
    """

    base_sections = SecProcessor.list_sections(processor)
    base_tables = SecProcessor.list_tables(processor)
    assert processor.list_sections() == base_sections
    assert processor.list_tables() == base_tables
    assert [table["table_ref"] for table in processor.list_tables()] == [table["table_ref"] for table in base_tables]
    assert [table["section_ref"] for table in processor.list_tables()] == [
        table["section_ref"] for table in base_tables
    ]
    for section in base_sections:
        section_ref = section["ref"]
        assert processor.get_section_title(section_ref) == SecProcessor.get_section_title(processor, section_ref)
        assert processor.read_section(section_ref) == SecProcessor.read_section(processor, section_ref)
        assert processor.search("Business", within_ref=section_ref) == SecProcessor.search(
            processor,
            "Business",
            section_ref,
        )


def test_ten_k_public_processor_assigns_tables_without_marker_capability(
    tmp_path: Path,
) -> None:
    """公开 10-K fallback 处理器必须为合法表格建立章节 ownership。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 合法 10-K 的公开 section/table 关系不完整时抛出。
    """

    filing_path = tmp_path / "minimal-10k.htm"
    filing_path.write_text(
        """<html><body>
<h1>UNITED STATES SECURITIES AND EXCHANGE COMMISSION</h1>
<h2>PART I</h2>
<h2>ITEM 1. BUSINESS</h2><p>Business operations and customers.</p>
<table><tr><th>Segment</th><th>Revenue</th></tr><tr><td>Cloud</td><td>100</td></tr></table>
<h2>ITEM 1A. RISK FACTORS</h2><p>Competition and market risk.</p>
<h2>ITEM 1B. UNRESOLVED STAFF COMMENTS</h2><p>None.</p>
<h2>ITEM 2. PROPERTIES</h2><p>Principal offices.</p>
<h2>PART II</h2>
<h2>ITEM 5. MARKET FOR REGISTRANT COMMON EQUITY</h2><p>Market information.</p>
<h2>ITEM 6. RESERVED</h2><p>Reserved.</p>
<h2>ITEM 7. MANAGEMENT'S DISCUSSION AND ANALYSIS</h2><p>Operating results.</p>
<h2>ITEM 8. FINANCIAL STATEMENTS AND SUPPLEMENTARY DATA</h2><p>Financial statements.</p>
<h2>SIGNATURES</h2><p>Signed.</p>
</body></html>""",
        encoding="utf-8",
    )
    source = LocalFileSource(
        path=filing_path,
        uri="local://minimal-10k.htm",
        media_type="text/html",
    )
    assert TenKFormProcessor.supports(
        source,
        form_type="10-K",
        media_type="text/html",
    )

    processor = TenKFormProcessor(
        source,
        form_type="10-K",
        media_type="text/html",
    )
    sections = processor.list_sections()
    tables = processor.list_tables()

    assert sections
    assert len(tables) == 1
    assert tables[0]["section_ref"] in {section["ref"] for section in sections}
    assert tables[0]["table_ref"] in {
        table_ref for section in sections for table_ref in processor.read_section(section["ref"])["tables"]
    }
    _assert_processor_matches_base_public_contract(processor)


def test_ten_q_public_processor_keeps_base_fallback_through_second_postprocess(
    tmp_path: Path,
) -> None:
    """公开 10-Q 二次 postprocess 必须保持首次 whole-base fallback。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 10-Q 二次 postprocess 重生 partial virtual state 时抛出。
    """

    filing_path = tmp_path / "minimal-10q.htm"
    filing_path.write_text(
        """<html><body>
<h1>UNITED STATES SECURITIES AND EXCHANGE COMMISSION</h1>
<h2>PART I</h2>
<h2>ITEM 1. FINANCIAL STATEMENTS</h2><p>Quarterly statements.</p>
<table><tr><th>Metric</th><th>Value</th></tr><tr><td>Revenue</td><td>25</td></tr></table>
<h2>ITEM 2. MANAGEMENT'S DISCUSSION AND ANALYSIS</h2><p>Business performance.</p>
<h2>ITEM 3. QUANTITATIVE AND QUALITATIVE DISCLOSURES</h2><p>Market risk.</p>
<h2>ITEM 4. CONTROLS AND PROCEDURES</h2><p>Controls.</p>
<h2>PART II</h2>
<h2>ITEM 1. LEGAL PROCEEDINGS</h2><p>None.</p>
<h2>ITEM 1A. RISK FACTORS</h2><p>Business risk.</p>
<h2>ITEM 2. UNREGISTERED SALES OF EQUITY SECURITIES</h2><p>None.</p>
<h2>ITEM 6. EXHIBITS</h2><p>Exhibits.</p>
<h2>SIGNATURES</h2><p>Signed.</p>
</body></html>""",
        encoding="utf-8",
    )
    source = LocalFileSource(
        path=filing_path,
        uri="local://minimal-10q.htm",
        media_type="text/html",
    )
    assert TenQFormProcessor.supports(source, form_type="10-Q", media_type="text/html")

    processor = TenQFormProcessor(source, form_type="10-Q", media_type="text/html")
    assert len(processor.list_tables()) == 1
    _assert_processor_matches_base_public_contract(processor)


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


def test_virtual_section_complete_mapping_publishes_deepest_bidirectional_candidate() -> None:
    """完整 marker proof 应从同一 candidate 下钻并原子发布双向映射。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 最深章节 remap 与最终双向发布不一致时抛出。
    """

    sections = [
        _VirtualSection(
            "s_alpha",
            "Alpha",
            "alpha child body",
            "alpha",
            [],
            child_refs=["s_alpha_child"],
        ),
        _VirtualSection(
            "s_alpha_child",
            "Child",
            "child body",
            "child",
            [],
            level=2,
            parent_ref="s_alpha",
        ),
        _VirtualSection("s_beta", "Beta", "beta body", "beta", []),
    ]
    harness = _VirtualHarness(
        base_table_refs=("t_0001", "t_0002"),
        marked_text="Alpha\nChild\n[[t_0001]]\nBeta\n[[t_0002]]\n",
        virtual_sections=sections,
    )

    harness._refresh_virtual_section_state()

    assert [section["ref"] for section in harness.list_sections()] == [
        "s_alpha",
        "s_alpha_child",
        "s_beta",
    ]
    assert [table["section_ref"] for table in harness.list_tables()] == ["s_alpha_child", "s_beta"]
    assert harness.read_section("s_alpha")["tables"] == []
    assert harness.read_section("s_alpha_child")["tables"] == ["t_0001"]
    assert harness.read_section("s_beta")["tables"] == ["t_0002"]
    first_result = (harness.list_sections(), harness.list_tables())
    harness._refresh_virtual_section_state()
    assert (harness.list_sections(), harness.list_tables()) == first_result


def test_virtual_section_incomplete_proof_publishes_whole_base_fallback() -> None:
    """无矛盾但缺失或标题范围不唯一的 proof 应整体回退 base contract。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: incomplete proof 发布 partial virtual state 时抛出。
    """

    partial = _VirtualHarness(
        base_table_refs=("t_0001", "t_0002"),
        marked_text="Alpha\n[[t_0001]]\nBeta\n",
    )
    partial._refresh_virtual_section_state()
    _assert_virtual_harness_matches_base_contract(partial)

    ambiguous = _VirtualHarness(
        base_table_refs=("t_0001",),
        marked_text="Gamma\n[[t_0001]]\n",
        marked_markers=[(0, "Gamma")],
    )
    ambiguous._refresh_virtual_section_state()
    _assert_virtual_harness_matches_base_contract(ambiguous)


def test_virtual_section_contradictions_fail_before_incomplete_fallback() -> None:
    """base/marker/tree 矛盾应在 atomic commit 前 fail closed。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 任一矛盾被 incomplete fallback 吞掉时抛出。
    """

    missing_base_ref = _VirtualHarness(base_table_refs=("",), include_table_marker=False)
    with pytest.raises(ValueError, match="缺失或为空"):
        missing_base_ref._refresh_virtual_section_state()

    duplicate_base_ref = _VirtualHarness(base_table_refs=("t_0001", "t_0001"))
    with pytest.raises(ValueError, match="底层 table_ref 重复"):
        duplicate_base_ref._refresh_virtual_section_state()

    incomplete_and_dangling = _VirtualHarness(
        base_table_refs=("t_0001", "t_0002"),
        marked_text="Alpha\n[[t_0001]]\n[[t_9999]]\nBeta\n",
    )
    with pytest.raises(ValueError, match="marker table_ref 悬挂"):
        incomplete_and_dangling._refresh_virtual_section_state()

    duplicate_marker = _VirtualHarness(
        marked_text="Alpha\n[[t_0001]]\n[[t_0001]]\nBeta\n",
    )
    with pytest.raises(ValueError, match="marker table_ref 重复"):
        duplicate_marker._refresh_virtual_section_state()

    contradictory_tree_sections = [
        _VirtualSection("s_alpha", "Alpha", "alpha", "alpha", [], child_refs=["s_child"]),
        _VirtualSection("s_child", "Child", "child", "child", [], level=2, parent_ref="s_beta"),
        _VirtualSection("s_beta", "Beta", "beta", "beta", []),
    ]
    contradictory_tree = _VirtualHarness(virtual_sections=contradictory_tree_sections)
    with pytest.raises(ValueError, match="反向关系不一致"):
        contradictory_tree._refresh_virtual_section_state()

    for harness in (
        missing_base_ref,
        duplicate_base_ref,
        incomplete_and_dangling,
        duplicate_marker,
        contradictory_tree,
    ):
        assert harness._virtual_section_publication_mode is _VirtualSectionPublicationMode.BUILDING
        assert harness.list_sections() == _VirtualBaseProcessor.list_sections(harness)


def test_virtual_section_zero_table_document_publishes_virtual_projection() -> None:
    """零表格文档应把空 mapping 视为完整 proof 并发布虚拟章节。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 零表格文档被无意义回退时抛出。
    """

    harness = _VirtualHarness(base_table_refs=(), include_table_marker=False)
    harness._refresh_virtual_section_state()

    assert [section["ref"] for section in harness.list_sections()] == ["s_alpha", "s_beta"]
    assert harness.list_tables() == []
    assert harness.read_section("s_alpha")["tables"] == []
    assert [hit.get("section_ref") for hit in harness.search("alpha")] == ["s_alpha"]


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

    dangling = _VirtualHarness(
        base_table_refs=("t_0001", "t_0002"),
        marked_text="Alpha\n[[t_0001]]\n[[t_9999]]\nBeta\n",
    )
    with pytest.raises(ValueError, match="marker table_ref 悬挂"):
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


@pytest.mark.parametrize(
    "processor_type",
    [TenKFormProcessor, BsTenKFormProcessor, TenQFormProcessor, BsTenQFormProcessor],
)
def test_report_form_second_postprocess_keeps_base_fallback_terminal(
    monkeypatch: pytest.MonkeyPatch,
    processor_type: (
        type[TenKFormProcessor] | type[BsTenKFormProcessor] | type[TenQFormProcessor] | type[BsTenQFormProcessor]
    ),
) -> None:
    """四条 report-form 路径二次 postprocess 都不得重入 fallback proof。

    Args:
        monkeypatch: pytest monkeypatch fixture。
        processor_type: 待验证的 10-K/10-Q processor 类型。

    Returns:
        无。

    Raises:
        AssertionError: 二次 postprocess 重读 marker 或重生 partial state 时抛出。
    """

    harness = _VirtualHarness(include_table_marker=False)
    processor = _build_virtual_postprocess_probe(processor_type, harness, monkeypatch)
    marker_calls_after_first_publication = harness.marker_call_count
    base_table_calls_after_first_publication = harness.base_list_tables_call_count

    processor._postprocess_virtual_sections(harness.get_full_text())
    processor._refresh_virtual_section_state()

    assert harness.marker_call_count == marker_calls_after_first_publication
    assert harness.base_list_tables_call_count == base_table_calls_after_first_publication
    assert processor.list_sections() == _VirtualBaseProcessor.list_sections(harness)
    assert processor.list_tables() == _VirtualBaseProcessor.list_tables(harness)
    for section in _VirtualBaseProcessor.list_sections(harness):
        section_ref = section["ref"]
        assert processor.get_section_title(section_ref) == _VirtualBaseProcessor.get_section_title(
            harness,
            section_ref,
        )
        assert processor.read_section(section_ref) == _VirtualBaseProcessor.read_section(harness, section_ref)
        assert processor.search("alpha", within_ref=section_ref) == _VirtualBaseProcessor.search(
            harness,
            "alpha",
            within_ref=section_ref,
        )


def test_processor_cache_reuses_equal_revision_and_rebuilds_after_source_change(tmp_path: Path) -> None:
    """processor cache 只复用 snapshot revision/source kind 相等的实例。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: cache reuse/rebuild 次数不正确时抛出。
    """

    runtime, repository, registry = _build_runtime(tmp_path)
    first = _read_runtime_processor_for_document(runtime, "doc-1")
    assert _read_runtime_processor_for_document(runtime, "doc-1") is first
    assert registry.create_count == 1

    _update_source(repository, fingerprint="revision-two", payload=b"version-two")
    second = _read_runtime_processor_for_document(runtime, "doc-1")
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
    _update_source(
        repository,
        fingerprint="invalid-utf8",
        payload=b"valid\xffinvalid",
    )

    with pytest.raises(FinsReadBusinessError) as error_info:
        _read_runtime_processor_for_document(runtime, "doc-1")

    assert error_info.value.code is ErrorCode.SOURCE_DECODE_FAILED
    assert isinstance(error_info.value.__cause__, FinsSourceDecodeError)
    assert registry.create_count == 0
    assert runtime._processor_cache.size() == 0
    assert len(repository.full_snapshot_roots) == 1
    assert all(not root.exists() for root in repository.full_snapshot_roots)


def test_processor_build_failure_closes_unpublished_full_snapshot(tmp_path: Path) -> None:
    """processor registry 构建失败时应保留主因并关闭未发布 snapshot。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 主异常、cache 状态或 snapshot cleanup 不正确时抛出。
    """

    runtime, repository, registry = _build_runtime(tmp_path)
    build_failure = RuntimeError("processor build failure")
    registry.before_return = partial(_raise_processor_build_failure, build_failure)

    with pytest.raises(RuntimeError) as error_info:
        _read_runtime_processor_for_document(runtime, "doc-1")

    assert error_info.value is build_failure
    assert registry.create_count == 1
    assert registry.created == []
    assert runtime._processor_cache.size() == 0
    assert len(repository.full_snapshot_roots) == 1
    assert all(not root.exists() for root in repository.full_snapshot_roots)


def test_processor_build_cancellation_closes_unpublished_full_snapshot(tmp_path: Path) -> None:
    """full snapshot 取得后、cache publish 前取消时应保留取消并清理资源。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 取消优先级、cache 状态或 snapshot cleanup 不正确时抛出。
    """

    runtime, repository, registry = _build_runtime(tmp_path)
    cancellation_token = _ManualCancellationToken()
    registry.before_return = cancellation_token.cancel

    with pytest.raises(FinsReadCancelledError):
        runtime.get_document_sections(
            ticker="AAPL",
            document_id="doc-1",
            cancellation_token=cancellation_token,
        )

    assert registry.create_count == 1
    assert runtime._processor_cache.size() == 0
    assert runtime._retired_entries == set()
    assert runtime._pending_snapshots == []
    assert len(repository.full_snapshot_roots) == 1
    assert all(not root.exists() for root in repository.full_snapshot_roots)


def test_single_snapshot_entry_replaces_meta_and_processor_together(tmp_path: Path) -> None:
    """同一个 cache entry 应一起替换 processor、meta 与 snapshot resource。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: meta/processor 不同版或旧 snapshot 未释放时抛出。
    """

    runtime, repository, _registry = _build_runtime(tmp_path)
    with runtime._borrow_processor(ticker="AAPL", document_id="doc-1") as first_borrow:
        first_processor = first_borrow.processor
        first_root = first_borrow.snapshot.get_primary_source().materialize().parent
        assert first_borrow.source_meta["form_type"] == "10-K"

    _update_source(
        repository,
        fingerprint="meta-revision-two",
        form_type="10-Q",
        payload=b"version-two",
    )
    with runtime._borrow_processor(ticker="AAPL", document_id="doc-1") as second_borrow:
        assert second_borrow.processor is not first_processor
        assert second_borrow.source_meta["form_type"] == "10-Q"
        assert second_borrow.snapshot.source_kind is SourceKind.FILING
    assert not first_root.exists()
    assert runtime._processor_cache.size() == 1


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
    _read_runtime_processor_for_document(runtime, "doc-2")
    _update_source(repository, fingerprint="doc-2-revision-two", document_id="doc-2")

    assert (
        runtime._diagnose_cross_document_locator(
            ticker="AAPL",
            current_document_id="doc-1",
            kind="ref",
            locator="s_0001",
        )
        is None
    )
    assert runtime._processor_cache.size() == 0


def test_transient_storage_change_recovers_without_consumer_retry_or_cache_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """真实 publication 在 copy 后变化时由 storage 内部恢复，consumer 只调用一次 full snapshot。

    Args:
        tmp_path: pytest 临时目录。
        monkeypatch: 用于挂接真实 fd-copy 后的确定性协调 seam。

    Returns:
        无。

    Raises:
        AssertionError: consumer 重试、结果混版或 cache 构建次数不正确时抛出。
    """

    runtime, repository, registry = _build_runtime(tmp_path)
    original_copy = source_snapshot_module._copy_snapshot_files
    first_copy_complete = Event()
    publication_complete = Event()
    first_attempt = True

    def _coordinated_copy(
        open_files: list[source_snapshot_module._OpenSnapshotFile],
        temp_root: Path,
    ) -> None:
        """第一次真实 fd-copy 后等待测试线程完成 B publication。"""

        nonlocal first_attempt
        original_copy(open_files, temp_root)
        if first_attempt:
            first_attempt = False
            first_copy_complete.set()
            assert publication_complete.wait(timeout=5.0)

    monkeypatch.setattr(source_snapshot_module, "_copy_snapshot_files", _coordinated_copy)
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_read_runtime_processor_for_document, runtime, "doc-1")
        assert first_copy_complete.wait(timeout=5.0)
        _update_source(
            repository,
            fingerprint="transient-b",
            payload=b"version-b",
            source_provider=FinsSourceProvider.USER_UPLOAD,
        )
        publication_complete.set()
        processor = future.result(timeout=5.0)

    assert isinstance(processor, _ReadProcessor)
    assert processor.label == "version-b"
    assert repository.snapshot_read_calls == 2
    assert registry.create_count == 1
    assert runtime._processor_cache.size() == 1


def test_sustained_storage_change_maps_once_to_source_changed_during_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """真实持续 publication 令 storage 耗尽预算，并由 runtime 单点映射。

    Args:
        tmp_path: pytest 临时目录。
        monkeypatch: 用于挂接真实 fd-copy 后的确定性协调 seam。

    Returns:
        无。

    Raises:
        AssertionError: storage 未真实耗尽、consumer 重试或 cache 状态不正确时抛出。
    """

    runtime, repository, _registry = _build_runtime(tmp_path)
    original_copy = source_snapshot_module._copy_snapshot_files
    publication_barrier = Barrier(2, timeout=5.0)
    copied_attempts = 0

    def _coordinate_every_copy(
        open_files: list[source_snapshot_module._OpenSnapshotFile],
        temp_root: Path,
    ) -> None:
        """每次真实 fd-copy 后等待测试线程发布下一版。"""

        nonlocal copied_attempts
        original_copy(open_files, temp_root)
        copied_attempts += 1
        publication_barrier.wait()
        publication_barrier.wait()

    monkeypatch.setattr(source_snapshot_module, "_copy_snapshot_files", _coordinate_every_copy)
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_read_runtime_processor_for_document, runtime, "doc-1")
        for attempt_index in range(source_snapshot_module._STABLE_READ_ATTEMPT_LIMIT):
            publication_barrier.wait()
            publish_b = attempt_index % 2 == 0
            _update_source(
                repository,
                fingerprint="sustained-b" if publish_b else "sustained-a",
                payload=b"version-b" if publish_b else b"version-a",
                source_provider=(FinsSourceProvider.USER_UPLOAD if publish_b else FinsSourceProvider.SEC_EDGAR),
            )
            publication_barrier.wait()
        with pytest.raises(FinsReadBusinessError) as error_info:
            future.result(timeout=5.0)

    assert error_info.value.code is ErrorCode.SOURCE_CHANGED_DURING_READ
    assert copied_attempts == source_snapshot_module._STABLE_READ_ATTEMPT_LIMIT
    assert repository.snapshot_read_calls == 2
    assert repository.full_snapshot_roots == []
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
    _read_runtime_processor_for_document(runtime, "doc-1")
    _update_source(repository, fingerprint="revision-concurrent", payload=b"version-concurrent")
    build_entered = Event()
    release_build = Event()

    def _block_first_build() -> None:
        """让第二个 reader 取得 losing full snapshot 后再释放唯一 build。"""

        build_entered.set()
        assert release_build.wait(timeout=5.0)

    registry.before_return = _block_first_build
    with ThreadPoolExecutor(max_workers=2) as executor:
        first_future = executor.submit(_read_runtime_processor, runtime, 0)
        assert build_entered.wait(timeout=5.0)
        second_future = executor.submit(_read_runtime_processor, runtime, 1)
        release_build.set()
        results = [first_future.result(timeout=5.0), second_future.result(timeout=5.0)]

    assert results[0] is results[1]
    assert registry.create_count == 2


def test_concurrent_initial_cache_miss_builds_one_processor_and_closes_losing_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """同文档初始 miss 共用一把 creation lock 且只发布一个 processor。

    Args:
        tmp_path: pytest 临时目录。
        monkeypatch: 用于记录两个重叠 caller 取得的 creation lock。

    Returns:
        无。

    Raises:
        AssertionError: 构建次数、processor 身份或 losing snapshot cleanup 不正确时抛出。
    """

    runtime, repository, registry = _build_runtime(tmp_path)
    build_entered = Event()
    release_build = Event()
    second_full_ready = Event()
    creation_lock_id_guard = Lock()
    creation_lock_ids: list[int] = []
    original_get_creation_lock = runtime._get_creation_lock

    def _record_creation_lock(cache_key: ProcessorCacheKey) -> Lock:
        """记录 caller 取得的强引用 document creation lock。

        Args:
            cache_key: processor cache key。

        Returns:
            runtime registry 返回的 document creation lock。

        Raises:
            RuntimeError: runtime lock registry 访问失败时抛出。
        """

        creation_lock = original_get_creation_lock(cache_key)
        with creation_lock_id_guard:
            creation_lock_ids.append(id(creation_lock))
        return creation_lock

    def _block_build() -> None:
        """阻塞唯一 processor build，直到第二个 full snapshot 已取得。"""

        build_entered.set()
        assert release_build.wait(timeout=5.0)

    def _observe_full_snapshot(count: int) -> None:
        """第二个 full snapshot 构造完成时通知测试主线程。"""

        if count >= 2:
            second_full_ready.set()

    registry.before_return = _block_build
    repository.on_full_snapshot = _observe_full_snapshot
    monkeypatch.setattr(runtime, "_get_creation_lock", _record_creation_lock)
    with ThreadPoolExecutor(max_workers=2) as executor:
        first_future = executor.submit(_read_runtime_processor, runtime, 0)
        assert build_entered.wait(timeout=5.0)
        second_future = executor.submit(_read_runtime_processor, runtime, 1)
        assert second_full_ready.wait(timeout=5.0)
        release_build.set()
        processors = [first_future.result(timeout=5.0), second_future.result(timeout=5.0)]

    assert processors[0] is processors[1]
    assert registry.create_count == 1
    assert len(creation_lock_ids) == 2
    assert len(set(creation_lock_ids)) == 1
    assert len(repository.full_snapshot_roots) == 2
    assert sum(root.exists() for root in repository.full_snapshot_roots) == 1


def test_runtime_close_before_cache_publication_rejects_build_and_cleans_snapshot(
    tmp_path: Path,
) -> None:
    """close 先线性化时，阻塞中的 build 必须失败且不得事后发布 entry。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: build 未以 close-state 失败或 cache/temp root 残留时抛出。
    """

    runtime, repository, registry = _build_runtime(tmp_path)
    build_entered = Event()
    release_build = Event()

    def _block_before_registry_return() -> None:
        """在 processor 已构建、cache 尚未发布的窗口阻塞 worker。

        Args:
            无。

        Returns:
            无。

        Raises:
            AssertionError: 主线程未释放 build 时抛出。
        """

        build_entered.set()
        assert release_build.wait(timeout=5.0)

    registry.before_return = _block_before_registry_return
    with ThreadPoolExecutor(max_workers=1) as executor:
        build_future = executor.submit(_read_runtime_processor_for_document, runtime, "doc-1")
        assert build_entered.wait(timeout=5.0)
        runtime.close()
        assert runtime._processor_cache.size() == 0
        release_build.set()
        with pytest.raises(RuntimeError, match="Fins read runtime 已关闭"):
            build_future.result(timeout=5.0)
        assert build_future.done()

    assert registry.create_count == 1
    assert runtime._processor_cache.size() == 0
    assert runtime._retired_entries == set()
    assert runtime._pending_snapshots == []
    assert len(repository.full_snapshot_roots) == 1
    assert all(not root.exists() for root in repository.full_snapshot_roots)


def test_creation_lock_registry_reclaims_missing_and_evicted_document_keys(
    tmp_path: Path,
) -> None:
    """missing 与超容量 valid key 调用结束后不得在线性 lock registry 中残留。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: creation lock registry 随历史 key 线性增长时抛出。
    """

    runtime, repository, registry = _build_runtime(
        tmp_path,
        processor_cache_max_entries=_LOCK_REGISTRY_CACHE_CAPACITY,
    )
    missing_document_ids = tuple(f"missing-{index}" for index in range(_LOCK_REGISTRY_MISSING_KEY_COUNT))
    for document_id in missing_document_ids:
        with pytest.raises(FileNotFoundError):
            _read_runtime_processor_for_document(runtime, document_id)
    gc.collect()

    assert runtime._processor_cache.size() == 0
    assert len(runtime._creation_locks) == 0

    added_document_ids = tuple(f"doc-{index}" for index in range(2, _LOCK_REGISTRY_VALID_DOCUMENT_COUNT + 1))
    _create_test_source_documents(repository, added_document_ids)
    valid_document_ids = ("doc-1", *added_document_ids)
    for document_id in valid_document_ids:
        _read_runtime_processor_for_document(runtime, document_id)
    gc.collect()

    assert registry.create_count == _LOCK_REGISTRY_VALID_DOCUMENT_COUNT
    assert runtime._processor_cache.size() == _LOCK_REGISTRY_CACHE_CAPACITY
    assert len(runtime._creation_locks) == 0
    assert sum(root.exists() for root in repository.full_snapshot_roots) == (_LOCK_REGISTRY_CACHE_CAPACITY)
    runtime.close()
    assert all(not root.exists() for root in repository.full_snapshot_roots)


def test_cache_eviction_defers_snapshot_close_until_active_borrow_releases(tmp_path: Path) -> None:
    """revision replacement retire 旧条目后，应等 active borrow 释放再删除旧临时树。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 旧 snapshot 过早关闭或最后 borrow 后仍泄漏时抛出。
    """

    runtime, repository, _registry = _build_runtime(tmp_path)
    old_borrow = runtime._borrow_processor(ticker="AAPL", document_id="doc-1")
    old_root = old_borrow.snapshot.get_primary_source().materialize().parent
    with ThreadPoolExecutor(max_workers=1) as executor:

        def _publish_and_read() -> DocumentProcessor:
            """发布 B 并借用新 processor。"""

            _update_source(repository, fingerprint="borrow-b", payload=b"version-b")
            return _read_runtime_processor_for_document(runtime, "doc-1")

        new_processor = executor.submit(_publish_and_read).result(timeout=5.0)

    assert isinstance(new_processor, _ReadProcessor)
    assert new_processor.label == "version-b"
    assert old_root.exists()
    with old_borrow.snapshot.get_primary_source().open() as stream:
        assert stream.read() == b"version-one"
    old_borrow.__exit__(None, None, None)
    assert not old_root.exists()


def test_cache_publication_before_runtime_close_preserves_active_borrow(
    tmp_path: Path,
) -> None:
    """entry 先发布且已被借用时，close 应 retire 并允许当前调用完成。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: close 提前删除 active snapshot 或最终未清理时抛出。
    """

    runtime, _repository, _registry = _build_runtime(tmp_path)
    with runtime._borrow_processor(ticker="AAPL", document_id="doc-1") as borrow:
        processor = borrow.processor
        snapshot_root = borrow.snapshot.get_primary_source().materialize().parent
    assert isinstance(processor, _ReadProcessor)
    borrow_entered = Event()
    release_borrow = Event()

    def _block_active_borrow() -> None:
        """让已发布 entry 的 active borrow 跨越 runtime.close。

        Args:
            无。

        Returns:
            无。

        Raises:
            AssertionError: 主线程未释放 active borrow 时抛出。
        """

        borrow_entered.set()
        assert release_borrow.wait(timeout=5.0)

    processor.before_list_sections = _block_active_borrow
    with ThreadPoolExecutor(max_workers=1) as executor:
        read_future = executor.submit(
            runtime.get_document_sections,
            ticker="AAPL",
            document_id="doc-1",
        )
        assert borrow_entered.wait(timeout=5.0)
        runtime.close()
        assert runtime._processor_cache.size() == 0
        assert snapshot_root.exists()
        release_borrow.set()
        result = read_future.result(timeout=5.0)

    assert result["sections"][0]["title"] == "Overview"
    assert not snapshot_root.exists()
    assert runtime._retired_entries == set()
    assert runtime._pending_snapshots == []
    runtime.close()


def test_cache_clear_and_runtime_close_release_all_snapshot_resources(tmp_path: Path) -> None:
    """runtime close 应清空 cache、释放 snapshot，并保持幂等与关闭后 fail-fast。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: cache/temp cleanup 或幂等关闭不正确时抛出。
    """

    runtime, _repository, _registry = _build_runtime(tmp_path)
    with runtime._borrow_processor(ticker="AAPL", document_id="doc-1") as borrow:
        snapshot_root = borrow.snapshot.get_primary_source().materialize().parent
    assert snapshot_root.exists()

    runtime.close()
    runtime.close()

    assert runtime._processor_cache.size() == 0
    assert not snapshot_root.exists()
    with pytest.raises(RuntimeError, match="已关闭"):
        runtime._borrow_processor(ticker="AAPL", document_id="doc-1")


def test_citation_and_result_use_the_same_borrowed_snapshot_during_publication(
    tmp_path: Path,
) -> None:
    """processor 返回 A 后发布 B，当前 result/citation 仍同为 A，下一次同为 B。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 内容与 provenance citation 混版时抛出。
    """

    runtime, repository, _registry = _build_runtime(tmp_path)
    processor = _read_runtime_processor_for_document(runtime, "doc-1")
    assert isinstance(processor, _ReadProcessor)
    result_ready = Event()
    allow_result = Event()

    def _pause_after_borrow() -> None:
        """在 processor 消费旧 snapshot 时等待 B publication 完成。"""

        result_ready.set()
        assert allow_result.wait(timeout=5.0)

    processor.before_read_section = _pause_after_borrow
    with ThreadPoolExecutor(max_workers=1) as executor:
        old_future = executor.submit(
            runtime.read_section,
            ticker="AAPL",
            document_id="doc-1",
            ref="s_0001",
        )
        assert result_ready.wait(timeout=5.0)
        _update_source(
            repository,
            fingerprint="citation-b",
            payload=b"version-b",
            source_provider=FinsSourceProvider.USER_UPLOAD,
        )
        allow_result.set()
        old_result = old_future.result(timeout=5.0)

    assert old_result["content"] == "version-one"
    assert old_result["citation"]["source_provider"] == "SEC_EDGAR"
    new_result = runtime.read_section(ticker="AAPL", document_id="doc-1", ref="s_0001")
    assert new_result["content"] == "version-b"
    assert new_result["citation"]["source_provider"] == "USER_UPLOAD"


def test_financial_projection_and_citation_share_borrowed_snapshot_during_publication(
    tmp_path: Path,
) -> None:
    """财务结果与公共 citation 必须在并发 publication 中保持同一 snapshot。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 财务结果、citation 或可选原因发生混版时抛出。
    """

    runtime, repository, registry = _build_runtime(tmp_path)
    registry.processor_type = _FinancialReadProcessor
    result_ready = Event()
    allow_result = Event()

    with runtime._borrow_processor(ticker="AAPL", document_id="doc-1") as borrow:
        processor = borrow.processor
    assert isinstance(processor, _FinancialReadProcessor)

    def _pause_financial_result() -> None:
        """在旧 snapshot 产生业务结果前等待新版本完成发布。

        Args:
            无。

        Returns:
            无。

        Raises:
            AssertionError: 等待 publication 超时时抛出。
        """

        result_ready.set()
        assert allow_result.wait(timeout=5.0)

    processor.before_get_financial_statement = _pause_financial_result
    with ThreadPoolExecutor(max_workers=1) as executor:
        old_future = executor.submit(
            runtime.get_financial_statement,
            ticker="AAPL",
            document_id="doc-1",
            statement_type="income",
        )
        assert result_ready.wait(timeout=5.0)
        _update_source(
            repository,
            fingerprint="financial-b",
            payload=b"version-b",
            source_provider=FinsSourceProvider.USER_UPLOAD,
        )
        allow_result.set()
        old_result = old_future.result(timeout=5.0)

    assert "rows" in old_result
    assert old_result["rows"][0]["source_label"] == "version-one"
    assert old_result["citation"]["source_provider"] == "SEC_EDGAR"
    assert "reason" not in old_result

    new_result = runtime.get_financial_statement(
        ticker="AAPL",
        document_id="doc-1",
        statement_type="income",
    )
    assert "rows" in new_result
    assert new_result["rows"][0]["source_label"] == "version-b"
    assert new_result["citation"]["source_provider"] == "USER_UPLOAD"
    assert "reason" not in new_result


def test_multi_query_search_keeps_result_and_citation_in_one_snapshot(tmp_path: Path) -> None:
    """批量 search 的聚合诊断、结果与 citation 应留在一个 snapshot borrow。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: multi-query 投影或 citation provenance 不正确时抛出。
    """

    runtime, _repository, _registry = _build_runtime(tmp_path)

    result = runtime.search_document(
        ticker="AAPL",
        document_id="doc-1",
        queries=["version one", "missing phrase"],
        mode="keyword",
    )

    assert result["query"] is None
    assert result.get("queries") == ["version one", "missing phrase"]
    diagnostics = result.get("diagnostics")
    assert isinstance(diagnostics, dict)
    assert diagnostics["query_count"] == 2
    per_query_stats = diagnostics["per_query_stats"]
    assert isinstance(per_query_stats, list)
    assert len(per_query_stats) == 2
    assert result.get("next_section_by_query") == {
        "version one": None,
        "missing phrase": None,
    }
    assert result["citation"]["source_provider"] == "SEC_EDGAR"
    runtime.close()


def test_optional_processor_entries_share_borrow_and_preserve_not_supported_contract(
    tmp_path: Path,
) -> None:
    """table error 与 page/financial/XBRL 不支持路径应安全释放同版 borrow。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 参数失败或 optional capability 投影漂移时抛出。
    """

    runtime, _repository, _registry = _build_runtime(tmp_path)

    with pytest.raises(FinsReadArgumentError) as table_error:
        runtime.get_table(
            ticker="AAPL",
            document_id="doc-1",
            table_ref="missing-table",
        )
    page_result = runtime.get_page_content(
        ticker="AAPL",
        document_id="doc-1",
        page_no=1,
    )
    financial_result = runtime.get_financial_statement(
        ticker="AAPL",
        document_id="doc-1",
        statement_type="income",
    )
    xbrl_result = runtime.query_xbrl_facts(
        ticker="AAPL",
        document_id="doc-1",
        concepts=["Revenue"],
    )

    assert table_error.value.arg_name == "table_ref"
    assert page_result["supported"] is False
    assert "error" in financial_result
    assert "error" in xbrl_result
    runtime.close()


def test_document_alias_across_source_kinds_is_rejected_as_ambiguous(tmp_path: Path) -> None:
    """跨 filing/material 命中同一 alias 时不得隐式选择任一 source kind。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: alias 歧义未在 read-runtime 参数边界被拒绝时抛出。
    """

    runtime, repository, _registry = _build_runtime(tmp_path)
    batch = repository._batching_repository.begin_batch("AAPL")
    material_document_id = "material-doc"
    shared_alias = "shared-alias"
    try:
        repository.update_source_document(
            SourceDocumentUpsertRequest(
                ticker="AAPL",
                document_id="doc-1",
                internal_document_id=shared_alias,
            ),
            SourceKind.FILING,
            batch=batch,
        )
        material_file = repository._blob_repository.store_file(
            SourceHandle("AAPL", material_document_id, SourceKind.MATERIAL.value),
            "material.txt",
            BytesIO(b"material-version"),
            batch=batch,
            content_type="text/plain",
        )
        repository.create_source_document(
            SourceDocumentUpsertRequest(
                ticker="AAPL",
                document_id=material_document_id,
                internal_document_id=shared_alias,
                form_type="EX-99",
                primary_document="material.txt",
                files=[material_file],
                meta={
                    "ingest_method": "upload",
                    "source_provider": FinsSourceProvider.USER_UPLOAD.to_storage_value(),
                    "ingest_complete": True,
                    "is_deleted": False,
                },
            ),
            SourceKind.MATERIAL,
            batch=batch,
        )
    except Exception:
        repository._batching_repository.rollback_batch(batch)
        raise
    repository._batching_repository.commit_batch(batch)

    with pytest.raises(FinsReadArgumentError, match="matches multiple documents"):
        runtime.read_section(
            ticker="AAPL",
            document_id=shared_alias,
            ref="s_0001",
        )
    assert runtime._processor_cache.size() == 0
    runtime.close()


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
    _read_runtime_processor_for_document(runtime, "doc-1")
    delete_batch = repository._batching_repository.begin_batch("AAPL")
    repository.delete_source_document(
        SourceDocumentStateChangeRequest("AAPL", "doc-1", SourceKind.FILING.value),
        batch=delete_batch,
    )
    repository._batching_repository.commit_batch(delete_batch)

    with pytest.raises(FileNotFoundError):
        _read_runtime_processor_for_document(runtime, "doc-1")
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
