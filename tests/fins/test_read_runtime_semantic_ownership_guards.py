"""Fins read runtime 语义所有权守护测试。"""

from __future__ import annotations

import ast
from collections.abc import Callable
from io import BytesIO
from pathlib import Path
from typing import TypeGuard

import pytest

from tests.fins.company_meta_test_support import stage_company_meta_fixture

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
    BatchToken,
    CompanyMeta,
    DocumentMeta,
    FinsSourceProvider,
    SourceHandle,
    SourceDocumentUpsertRequest,
    now_iso8601,
)
from dayu.fins.domain.enums import SourceKind
from dayu.fins.domain.financial_result_contract import (
    FinancialStatementResult as ProducerFinancialStatementResult,
    validate_financial_statement_result_payload,
)
from dayu.fins.domain.xbrl_result_contract import (
    XbrlQueryExecutionError,
    XbrlQueryParams,
)
from dayu.fins.storage import (
    FsBatchingRepository,
    FsCompanyMetaRepository,
    FsDocumentBlobRepository,
    FsProcessedDocumentRepository,
    FsSourceDocumentRepository,
)
from dayu.fins.storage._fs_repository_factory import _FsRepositorySet, build_fs_repository_set
from dayu.fins.storage.repository_protocols import SourceSnapshotProtocol
from dayu.fins.tools.read_runtime import FinsReadRuntime, _parse_source_document_meta
from dayu.fins.tools.read_runtime_helpers import (
    FinsReadArgumentError,
    FinsReadBusinessError,
    _resolve_processor_taxonomy,
    build_search_next_section_fields,
    resolve_document_type_for_source,
)
from dayu.fins.tools.result_types import (
    NotSupportedResult,
    PublicFinancialStatementResult,
    PublicXbrlQueryResult,
    project_financial_statement_result,
    project_xbrl_query_result,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_FINS_WAIT_ADAPTER_PATH = (_REPO_ROOT / "dayu" / "fins" / "ingestion" / "wait_adapter.py").resolve(strict=False)
_FINS_FORBIDDEN_IMPORT_ROOTS = ("dayu.engine", "dayu.host", "dayu.service", "dayu.ui")
_FINS_WAIT_ADAPTER_FORBIDDEN_IMPORT_ROOTS = ("dayu.engine", "dayu.service", "dayu.ui")


class _TaxonomyCapableProcessor:
    """测试用 taxonomy processor。"""

    def get_xbrl_taxonomy(self) -> str:
        """返回 taxonomy。

        Args:
            无。

        Returns:
            taxonomy 名称。

        Raises:
            无。
        """

        return "US-GAAP"


class _LegacyTaxonomyAttributeOnlyProcessor:
    """仅提供旧属性名的测试 processor。"""

    xbrl_taxonomy = "us-gaap"


class _FailingTaxonomyProcessor:
    """测试用 taxonomy 读取失败 processor。"""

    def get_xbrl_taxonomy(self) -> str:
        """抛出 taxonomy 读取错误。

        Args:
            无。

        Returns:
            不返回。

        Raises:
            RuntimeError: 始终抛出，模拟 processor owner 读取失败。
        """

        raise RuntimeError("taxonomy source unavailable")


class _FakeSource:
    """测试用空 Source。"""

    @property
    def uri(self) -> str:
        """返回资源 URI。

        Args:
            无。

        Returns:
            资源 URI。

        Raises:
            无。
        """

        return "memory://financial-statement-test"

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

        return "text/plain"

    @property
    def content_length(self) -> int:
        """返回内容长度。

        Args:
            无。

        Returns:
            内容长度。

        Raises:
            无。
        """

        return 0

    @property
    def etag(self) -> str:
        """返回资源 etag。

        Args:
            无。

        Returns:
            etag。

        Raises:
            无。
        """

        return "empty"

    def open(self) -> BytesIO:
        """打开空二进制流。

        Args:
            无。

        Returns:
            空二进制流。

        Raises:
            无。
        """

        return BytesIO()

    def materialize(self, suffix: str | None = None) -> Path:
        """返回可读路径占位。

        Args:
            suffix: 可选后缀，本测试不消费。

        Returns:
            仓库根目录路径。

        Raises:
            无。
        """

        del suffix
        return _REPO_ROOT


class _FinancialStatementPayloadProcessor:
    """测试用财务报表 processor。"""

    def __init__(
        self,
        source: Source,
        *,
        form_type: str | None = None,
        media_type: str | None = None,
    ) -> None:
        """初始化 processor。

        Args:
            source: 文档来源。
            form_type: 表单类型。
            media_type: 媒体类型。

        Returns:
            无。

        Raises:
            无。
        """

        del source, form_type, media_type
        self._payload: dict[str, JsonValue] = {}

    def set_financial_statement_payload(self, payload: dict[str, JsonValue]) -> None:
        """设置财务报表返回载荷。

        Args:
            payload: `get_financial_statement` 返回载荷。

        Returns:
            无。

        Raises:
            无。
        """

        self._payload = payload

    @classmethod
    def get_parser_version(cls) -> str:
        """返回 parser version。

        Args:
            无。

        Returns:
            parser version。

        Raises:
            无。
        """

        return "test"

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
            source: 文档来源。
            form_type: 表单类型。
            media_type: 媒体类型。

        Returns:
            始终返回 ``True``。

        Raises:
            无。
        """

        del source, form_type, media_type
        return True

    def list_sections(self) -> list[SectionSummary]:
        """返回空章节列表。

        Args:
            无。

        Returns:
            空章节列表。

        Raises:
            无。
        """

        return []

    def list_tables(self) -> list[TableSummary]:
        """返回空表格列表。

        Args:
            无。

        Returns:
            空表格列表。

        Raises:
            无。
        """

        return []

    def read_section(self, ref: str) -> SectionContent:
        """读取章节内容。

        Args:
            ref: 章节 ref。

        Returns:
            不返回。

        Raises:
            KeyError: 始终抛出，测试不消费章节内容。
        """

        raise KeyError(ref)

    def read_table(self, table_ref: str) -> TableContent:
        """读取表格内容。

        Args:
            table_ref: 表格 ref。

        Returns:
            不返回。

        Raises:
            KeyError: 始终抛出，测试不消费表格内容。
        """

        raise KeyError(table_ref)

    def get_section_title(self, ref: str) -> str | None:
        """返回章节标题。

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
            query: 搜索词。
            within_ref: 可选章节范围。

        Returns:
            空搜索结果。

        Raises:
            无。
        """

        del query, within_ref
        return []

    def get_full_text(self) -> str:
        """返回空全文。

        Args:
            无。

        Returns:
            空字符串。

        Raises:
            无。
        """

        return ""

    def get_full_text_with_table_markers(self) -> str:
        """返回空标记全文。

        Args:
            无。

        Returns:
            空字符串。

        Raises:
            无。
        """

        return ""

    def get_financial_statement(self, statement_type: str) -> dict[str, JsonValue]:
        """返回预设财务报表载荷。

        Args:
            statement_type: 报表类型。

        Returns:
            预设载荷。

        Raises:
            无。
        """

        del statement_type
        return self._payload


class _SectionPayloadProcessor(_FinancialStatementPayloadProcessor):
    """为 read_section 公共投影提供 typed 章节输入的测试 processor。"""

    def __init__(
        self,
        source: Source,
        *,
        form_type: str | None = None,
        media_type: str | None = None,
    ) -> None:
        """初始化固定章节载荷。

        Args:
            source: 文档来源。
            form_type: 表单类型。
            media_type: 媒体类型。

        Returns:
            无。

        Raises:
            无。
        """

        super().__init__(source, form_type=form_type, media_type=media_type)
        self._sections: dict[str, SectionContent] = {
            "section-1": SectionContent(
                ref="section-1",
                title="Item 1. Business",
                content="Revenue grew while operating costs remained controlled.",
                tables=[],
                word_count=7,
                contains_full_text=True,
                children=[
                    SectionSummary(
                        ref=" child-valid ",
                        title=" Valid Child ",
                        level=2,
                        parent_ref="section-1",
                        preview="有效子章节",
                    ),
                    SectionSummary(
                        ref="   ",
                        title="Invalid Child",
                        level=2,
                        parent_ref="section-1",
                        preview="空 ref 必须被丢弃",
                    ),
                    SectionSummary(
                        ref="child-without-title",
                        title=None,
                        level=2,
                        parent_ref="section-1",
                        preview="标题允许为空",
                    ),
                ],
                page_range=[3, 5],
            )
        }

    def read_section(self, ref: str) -> SectionContent:
        """读取固定章节，并为未知 ref 产生 processor 协议的 KeyError 输入。

        Args:
            ref: 章节 ref。

        Returns:
            ref 对应的 typed 章节载荷。

        Raises:
            KeyError: ref 不存在时抛出，交由 public runtime 转换。
        """

        return self._sections[ref]


class _TablePayloadProcessor(_FinancialStatementPayloadProcessor):
    """为 get_table 公共投影提供三类 typed 表格输入的测试 processor。"""

    def __init__(
        self,
        source: Source,
        *,
        form_type: str | None = None,
        media_type: str | None = None,
    ) -> None:
        """初始化 records、Markdown 与普通文本表格载荷。

        Args:
            source: 文档来源。
            form_type: 表单类型。
            media_type: 媒体类型。

        Returns:
            无。

        Raises:
            无。
        """

        super().__init__(source, form_type=form_type, media_type=media_type)
        self._tables: dict[str, TableContent] = {
            "records-table": TableContent(
                table_ref="records-table",
                caption="Revenue by quarter",
                data_format="records",
                data=[{" Quarter ": "Q1", "Revenue": 100}],
                columns=[" Quarter ", "Revenue", "Revenue", "   "],
                row_count=1,
                col_count=2,
                section_ref=None,
                table_type=" FINANCIAL ",
                page_no=7,
                is_financial=True,
            ),
            "markdown-table": TableContent(
                table_ref="markdown-table",
                caption=None,
                data_format="markdown",
                data="| Metric | Value |\n| --- | ---: |\n| Revenue | 100 |",
                columns=None,
                row_count=1,
                col_count=2,
                section_ref=None,
                table_type="data",
            ),
            "text-table": TableContent(
                table_ref="text-table",
                caption=None,
                data_format="markdown",
                data="Revenue was 100 in the reported period.",
                columns=None,
                row_count=0,
                col_count=0,
                section_ref=None,
                table_type="unsupported-table-type",
            ),
        }

    def read_table(self, table_ref: str) -> TableContent:
        """读取固定表格，并为未知 table_ref 产生 processor 协议的 KeyError 输入。

        Args:
            table_ref: 表格 ref。

        Returns:
            table_ref 对应的 typed 表格载荷。

        Raises:
            KeyError: table_ref 不存在时抛出，交由 public runtime 转换。
        """

        return self._tables[table_ref]


class _DefaultConceptsXbrlProcessor(_FinancialStatementPayloadProcessor):
    """为 query_xbrl_facts 默认 concept 选择提供 typed 输入的测试 processor。"""

    def __init__(
        self,
        source: Source,
        *,
        taxonomy: str = "US-GAAP",
        fail_query: bool = False,
        form_type: str | None = None,
        media_type: str | None = None,
    ) -> None:
        """初始化 taxonomy 与可选 typed query failure。

        Args:
            source: 文档来源。
            taxonomy: processor 识别出的 taxonomy 名称。
            fail_query: 是否把实际收到的 concepts 投影为 typed 执行失败。
            form_type: 表单类型。
            media_type: 媒体类型。

        Returns:
            无。

        Raises:
            无。
        """

        super().__init__(source, form_type=form_type, media_type=media_type)
        self._taxonomy = taxonomy
        self._fail_query = fail_query

    def get_xbrl_taxonomy(self) -> str:
        """返回 processor 的 typed taxonomy 业务事实。

        Args:
            无。

        Returns:
            初始化时提供的 taxonomy 名称。

        Raises:
            无。
        """

        return self._taxonomy

    def query_xbrl_facts(
        self,
        *,
        concepts: list[str],
        statement_type: str | None = None,
        period_end: str | None = None,
        fiscal_year: int | None = None,
        fiscal_period: str | None = None,
        min_value: float | None = None,
        max_value: float | None = None,
    ) -> dict[str, JsonValue]:
        """把实际收到的 concepts 原样写入 producer contract 或 typed failure。

        Args:
            concepts: runtime owner 选择的 concept 列表。
            statement_type: 可选报表类型。
            period_end: 可选期间结束日。
            fiscal_year: 可选财年。
            fiscal_period: 可选财期。
            min_value: 可选最小值。
            max_value: 可选最大值。

        Returns:
            query_params 与输入 concepts 同源的合法 XBRL producer 载荷。

        Raises:
            XbrlQueryExecutionError: 启用 typed failure 时，携带实际收到的 concepts 抛出。
        """

        del statement_type, period_end, fiscal_year, fiscal_period, min_value, max_value
        if self._fail_query:
            raise XbrlQueryExecutionError(tuple(concepts))
        return {
            "query_params": {"concepts": list(concepts)},
            "facts": [
                {
                    "concept": concepts[0],
                    "numeric_value": 100.0,
                    "decimals": "0",
                }
            ],
            "data_quality": "xbrl",
        }


class _AllFailedXbrlProcessor(_FinancialStatementPayloadProcessor):
    """始终报告所有 XBRL concept 执行失败的测试 processor。"""

    def query_xbrl_facts(
        self,
        *,
        concepts: list[str],
        statement_type: str | None = None,
        period_end: str | None = None,
        fiscal_year: int | None = None,
        fiscal_period: str | None = None,
        min_value: float | None = None,
        max_value: float | None = None,
    ) -> dict[str, JsonValue]:
        """抛出 typed XBRL all-failed 异常。

        Args:
            concepts: concept 列表。
            statement_type: 可选报表类型。
            period_end: 可选期末日期。
            fiscal_year: 可选财年。
            fiscal_period: 可选财期。
            min_value: 可选最小值。
            max_value: 可选最大值。

        Returns:
            本函数不会返回。

        Raises:
            XbrlQueryExecutionError: 始终抛出。
        """

        del statement_type, period_end, fiscal_year, fiscal_period, min_value, max_value
        raise XbrlQueryExecutionError(tuple(concepts)) from RuntimeError("sentinel")


class _FixedProcessorRegistry(ProcessorRegistry):
    """返回固定 processor 的测试 registry。"""

    def __init__(self, processor: DocumentProcessor) -> None:
        """初始化 registry。

        Args:
            processor: 固定返回的 processor。

        Returns:
            无。

        Raises:
            无。
        """

        super().__init__()
        self._processor = processor

    def create_with_fallback(
        self,
        source: Source,
        *,
        form_type: str | None = None,
        media_type: str | None = None,
        on_fallback: Callable[[type[DocumentProcessor], Exception, int, int], None] | None = None,
    ) -> DocumentProcessor:
        """返回固定 processor。

        Args:
            source: 文档来源。
            form_type: 表单类型。
            media_type: 媒体类型。
            on_fallback: fallback 回调。

        Returns:
            固定 processor。

        Raises:
            无。
        """

        del source, form_type, media_type, on_fallback
        return self._processor


class _CountingSourceRepository(FsSourceDocumentRepository):
    """统计 typed list、meta 与 snapshot 读取的测试仓储。"""

    def __init__(self, workspace_root: Path, *, repository_set: _FsRepositorySet) -> None:
        """初始化计数仓储。

        Args:
            workspace_root: Fins workspace 根目录。
            repository_set: 文件系统仓储 core 集合。

        Returns:
            无。

        Raises:
            OSError: 底层仓储初始化失败时抛出。
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
        self.get_source_meta_calls = 0
        self.get_source_meta_calls_by_kind: dict[SourceKind, int] = {}
        self.list_source_document_ids_calls: list[SourceKind] = []
        self.snapshot_read_calls = 0
        self.full_snapshot_roots: list[Path] = []

    def list_source_document_ids(
        self,
        ticker: str,
        source_kind: SourceKind,
    ) -> list[str]:
        """统计并执行 typed source document list。

        Args:
            ticker: 股票代码。
            source_kind: 来源类型。

        Returns:
            storage 返回的文档 ID 列表。

        Raises:
            OSError: 底层目录读取失败时抛出。
        """

        self.list_source_document_ids_calls.append(source_kind)
        return super().list_source_document_ids(ticker, source_kind)

    def read_source_snapshot(
        self,
        ticker: str,
        document_id: str,
        source_kind: SourceKind | None = None,
        *,
        materialize_files: bool,
    ) -> SourceSnapshotProtocol:
        """统计并执行真实 storage snapshot 读取。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。
            source_kind: 可选来源类型。
            materialize_files: 是否物化业务文件。

        Returns:
            storage-owned snapshot。

        Raises:
            FileNotFoundError: source 不存在时抛出。
            ValueError: source kind 歧义或 descriptor 非法时抛出。
            OSError: snapshot I/O 失败时抛出。
        """

        self.snapshot_read_calls += 1
        snapshot = super().read_source_snapshot(
            ticker,
            document_id,
            source_kind,
            materialize_files=materialize_files,
        )
        if materialize_files:
            self.full_snapshot_roots.append(snapshot.get_primary_source().materialize().parent)
        return snapshot

    def get_source_meta(
        self,
        ticker: str,
        document_id: str,
        source_kind: SourceKind,
    ) -> DocumentMeta:
        """统计并读取源文档 meta。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。
            source_kind: 来源类型。

        Returns:
            源文档 meta。

        Raises:
            FileNotFoundError: source meta 不存在时抛出。
            ValueError: source meta 非法时抛出。
        """

        self.get_source_meta_calls += 1
        self.get_source_meta_calls_by_kind[source_kind] = self.get_source_meta_calls_by_kind.get(source_kind, 0) + 1
        return super().get_source_meta(ticker, document_id, source_kind)

    def get_primary_source(self, ticker: str, document_id: str, source_kind: SourceKind) -> Source:
        """返回测试用 source，避免测试依赖真实文档文件。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。
            source_kind: 来源类型。

        Returns:
            测试用空 source。

        Raises:
            无。
        """

        del ticker, document_id, source_kind
        return _FakeSource()


def test_processor_taxonomy_uses_typed_protocol_not_attribute_fallback() -> None:
    """taxonomy 能力只通过显式 Protocol 方法识别。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    assert _resolve_processor_taxonomy(_TaxonomyCapableProcessor()) == "us-gaap"
    assert _resolve_processor_taxonomy(_LegacyTaxonomyAttributeOnlyProcessor()) is None


def test_processor_taxonomy_failure_propagates_without_default_fallback() -> None:
    """taxonomy 读取失败不得伪装成无 taxonomy。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    with pytest.raises(RuntimeError, match="taxonomy source unavailable"):
        _resolve_processor_taxonomy(_FailingTaxonomyProcessor())


def test_parse_source_document_meta_preserves_bool_and_defaults() -> None:
    """source meta bool 字段保留显式 bool，缺省字段使用 storage 默认。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    meta = _parse_source_document_meta({"amended": True, "is_deleted": False})

    assert meta["amended"] is True
    assert meta["is_deleted"] is False
    assert meta["ingest_complete"] is True


@pytest.mark.parametrize("value", [1000, 2025, 9999])
def test_parse_source_document_meta_preserves_valid_four_digit_fiscal_year(value: int) -> None:
    """read runtime 应保留 owner 已验证的合法四位财年。

    Args:
        value: 合法四位 fiscal year。

    Returns:
        无。

    Raises:
        AssertionError: read runtime 未原样保留合法年份时抛出。
    """

    meta = _parse_source_document_meta({"fiscal_year": value})

    assert meta["fiscal_year"] == value


@pytest.mark.parametrize("value", [999, 10000, True, False, "2025"])
def test_parse_source_document_meta_fails_closed_for_invalid_historical_fiscal_year(
    value: JsonValue,
) -> None:
    """read runtime 对历史非法财年必须按 domain owner 失败关闭。

    Args:
        value: 仓储中非法的历史 fiscal year 值。

    Returns:
        无。

    Raises:
        AssertionError: 非法历史值被忽略、默认化或未触发 ``ValueError`` 时抛出。
    """

    with pytest.raises(ValueError, match=r"fiscal_year 必须是 1000\.\.9999 的整数"):
        _parse_source_document_meta({"fiscal_year": value})


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("amended", 1),
        ("is_deleted", "false"),
        ("ingest_complete", None),
    ],
)
def test_parse_source_document_meta_rejects_non_bool_fields(field_name: str, value: JsonValue | None) -> None:
    """source meta bool 字段存在但非 bool 时必须失败。

    Args:
        field_name: 待测试 bool 字段名。
        value: 非 bool 字段值。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    raw_meta: dict[str, JsonValue] = {
        "amended": False,
        "is_deleted": False,
        "ingest_complete": True,
    }
    raw_meta[field_name] = value

    with pytest.raises(ValueError, match=f"source meta 字段 {field_name} 必须为 bool"):
        _parse_source_document_meta(raw_meta)


def test_read_runtime_snapshot_processor_cache_is_bounded_and_releases_evicted_resources(
    tmp_path: Path,
) -> None:
    """snapshot processor cache 受容量约束且淘汰时释放资源。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    processor = _FinancialStatementPayloadProcessor(_FakeSource())
    runtime, source_repository = _build_runtime_with_source_documents(
        tmp_path,
        processor_cache_max_entries=2,
        processor_registry=_FixedProcessorRegistry(processor),
    )
    roots: list[Path] = []
    for document_id in ("doc-1", "doc-2", "doc-3"):
        with runtime._borrow_processor(ticker="AAPL", document_id=document_id) as borrow:
            roots.append(borrow.snapshot.get_primary_source().materialize().parent)

    assert runtime._processor_cache.size() == 2
    assert len(source_repository.full_snapshot_roots) == 3
    assert not roots[0].exists()
    assert roots[1].exists()
    assert roots[2].exists()

    runtime.close()
    assert all(not root.exists() for root in roots)


def test_storage_snapshot_resolves_explicit_kind_and_rejects_ambiguity(tmp_path: Path) -> None:
    """source kind 的 0/1/2 解析只由 storage snapshot owner 完成。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    _runtime, source_repository = _build_runtime_with_source_documents(
        tmp_path,
        processor_cache_max_entries=4,
    )
    batch = source_repository._batching_repository.begin_batch("AAPL")
    _create_source_document(
        source_repository=source_repository,
        blob_repository=source_repository._blob_repository,
        batch=batch,
        document_id="doc-1",
        source_kind=SourceKind.MATERIAL,
        form_type="EX-99",
    )
    source_repository._batching_repository.commit_batch(batch)

    with pytest.raises(ValueError, match="不明确"):
        source_repository.read_source_snapshot(
            "AAPL",
            "doc-1",
            None,
            materialize_files=False,
        )
    with source_repository.read_source_snapshot(
        "AAPL",
        "doc-1",
        SourceKind.FILING,
        materialize_files=False,
    ) as filing_snapshot:
        assert filing_snapshot.source_meta["form_type"] == "10-K"
    with source_repository.read_source_snapshot(
        "AAPL",
        "doc-1",
        SourceKind.MATERIAL,
        materialize_files=False,
    ) as material_snapshot:
        assert material_snapshot.source_meta["form_type"] == "EX-99"


@pytest.mark.parametrize(
    ("payload", "expected_message"),
    [
        (
            {
                "statement_type": "income_statement",
                "periods": [],
                "currency": None,
                "units": None,
                "scale": None,
                "data_quality": "partial",
                "reason": "statement_not_found",
            },
            "缺少必填字段: rows",
        ),
        (
            {
                "statement_type": "income_statement",
                "periods": [],
                "rows": {"unexpected": "dict"},
                "currency": None,
                "units": None,
                "scale": None,
                "data_quality": "partial",
                "reason": "statement_not_found",
            },
            "rows 必须为数组",
        ),
    ],
)
def test_financial_statement_owner_rejects_missing_or_non_list_rows(
    payload: dict[str, JsonValue],
    expected_message: str,
) -> None:
    """财务领域 owner 必须直接拒绝 rows 缺失或非数组载荷。

    Args:
        payload: 测试用 producer 载荷。
        expected_message: owner validator 的预期失败信息。

    Returns:
        无。

    Raises:
        AssertionError: owner contract 未在边界处拒绝非法 rows 时抛出。
    """

    with pytest.raises(ValueError, match=expected_message):
        validate_financial_statement_result_payload(payload)


def test_get_financial_statement_accepts_list_rows(tmp_path: Path) -> None:
    """processor 财报 rows 为 list 时保持正常结果构造。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    processor = _FinancialStatementPayloadProcessor(_FakeSource())
    processor.set_financial_statement_payload(
        {
            "statement_type": "income_statement",
            "periods": [
                {
                    "period_end": "2025-12-31",
                    "fiscal_year": 2025,
                    "fiscal_period": "FY",
                }
            ],
            "currency": "USD",
            "units": "USD",
            "scale": "millions",
            "rows": [{"concept": "Revenue", "label": "Revenue", "values": [100]}],
            "data_quality": "xbrl",
        }
    )
    runtime, _source_repository = _build_runtime_with_source_documents(
        tmp_path,
        processor_cache_max_entries=4,
        processor_registry=_FixedProcessorRegistry(processor),
    )

    result = runtime.get_financial_statement(ticker="AAPL", document_id="doc-1", statement_type="income_statement")

    assert _is_financial_statement_result(result)
    assert result["periods"][0]["fiscal_year"] == 2025
    assert result["rows"] == [{"concept": "Revenue", "label": "Revenue", "values": [100]}]
    assert result["units"] == "USD"
    assert result["scale"] == "millions"
    assert result["data_quality"] == "xbrl"
    assert "reason" not in result
    assert set(result) == {
        "ticker",
        "document_id",
        "citation",
        "statement_type",
        "periods",
        "rows",
        "currency",
        "units",
        "scale",
        "data_quality",
    }


def test_public_result_builders_copy_inputs_and_preserve_optional_reason() -> None:
    """两个公共 builder 必须复制引用容器并只机械投影存在的业务原因。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 公共字段、容器独立性或可选原因发生漂移时抛出。
    """

    citation: dict[str, JsonValue] = {
        "source_type": "SEC_EDGAR",
        "document_id": "doc-1",
        "ticker": "AAPL",
        "source_provider": "SEC_EDGAR",
    }
    producer_result = ProducerFinancialStatementResult(
        statement_type="income",
        periods=[],
        rows=[],
        currency=None,
        units=None,
        scale=None,
        data_quality="partial",
        reason="statement_not_found",
    )

    financial_result: PublicFinancialStatementResult = project_financial_statement_result(
        ticker="AAPL",
        document_id="doc-1",
        citation=citation,
        producer_result=producer_result,
    )

    assert financial_result["citation"] == citation
    assert financial_result["citation"] is not citation
    assert "reason" in financial_result
    assert financial_result["reason"] == "statement_not_found"
    assert set(financial_result) == {
        "ticker",
        "document_id",
        "citation",
        "statement_type",
        "periods",
        "rows",
        "currency",
        "units",
        "scale",
        "data_quality",
        "reason",
    }

    query_params = XbrlQueryParams(concepts=["Revenue"], min_value=1)
    returned_facts: list[dict[str, JsonValue]] = [{"concept": "Revenue", "numeric_value": 100.0}]
    xbrl_result: PublicXbrlQueryResult = project_xbrl_query_result(
        ticker="AAPL",
        document_id="doc-1",
        citation=citation,
        query_params=query_params,
        returned_facts=returned_facts,
        data_quality="partial",
        optional_reason="query_partially_failed",
    )

    assert xbrl_result["citation"] == citation
    assert xbrl_result["citation"] is not citation
    assert xbrl_result["query_params"] == query_params
    assert xbrl_result["query_params"] is not query_params
    assert xbrl_result["facts"] == returned_facts
    assert xbrl_result["facts"] is not returned_facts
    assert xbrl_result["facts"][0] is not returned_facts[0]
    assert xbrl_result["fact_count"] == len(xbrl_result["facts"])
    assert "reason" in xbrl_result
    assert xbrl_result["reason"] == "query_partially_failed"


def test_public_projection_ast_has_new_types_and_single_count_assignment() -> None:
    """公共投影 AST 必须只暴露新类型并保持唯一计数赋值 owner。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 旧类型、弱签名或第二个计数赋值 owner 出现时抛出。
    """

    result_types_path = Path("dayu/fins/tools/result_types.py")
    result_types_tree = _parse_module(result_types_path)
    class_names = {node.name for node in result_types_tree.body if isinstance(node, ast.ClassDef)}
    assert "PublicFinancialStatementResult" in class_names
    assert "PublicXbrlQueryResult" in class_names
    assert "FinancialStatementResult" not in class_names
    assert "XbrlQueryResult" not in class_names

    builder_names = {
        "project_financial_statement_result",
        "project_xbrl_query_result",
    }
    builders = [
        node for node in result_types_tree.body if isinstance(node, ast.FunctionDef) and node.name in builder_names
    ]
    assert {builder.name for builder in builders} == builder_names
    for builder in builders:
        annotations = [_annotation_text(argument.annotation) for argument in builder.args.kwonlyargs]
        assert all("Any" not in annotation for annotation in annotations)

    count_owners = [
        node
        for builder in builders
        for node in ast.walk(builder)
        if isinstance(node, ast.keyword) and node.arg == "fact_count"
    ]
    assert len(count_owners) == 1
    assert isinstance(count_owners[0].value, ast.Call)
    assert ast.unparse(count_owners[0].value.func) == "len"

    for path in (
        Path("dayu/fins/tools/read_runtime_helpers.py"),
        Path("dayu/fins/tools/read_runtime.py"),
        Path("dayu/fins/tools/fins_tools.py"),
    ):
        tree = _parse_module(path)
        assert not any(isinstance(node, ast.keyword) and node.arg == "fact_count" for node in ast.walk(tree))


def test_query_xbrl_facts_maps_all_failed_to_typed_business_failure(tmp_path: Path) -> None:
    """read runtime 必须把 all-failed 映射为 xbrl_query_failed 而非空成功。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: typed failure code、cause 或文本语义不正确时抛出。
    """

    processor = _AllFailedXbrlProcessor(_FakeSource())
    runtime, _source_repository = _build_runtime_with_source_documents(
        tmp_path,
        processor_cache_max_entries=4,
        processor_registry=_FixedProcessorRegistry(processor),
    )

    with pytest.raises(FinsReadBusinessError) as error_info:
        runtime.query_xbrl_facts(
            ticker="AAPL",
            document_id="doc-1",
            concepts=["Revenue"],
        )

    assert error_info.value.code == "xbrl_query_failed"
    assert "零命中" in error_info.value.message
    assert isinstance(error_info.value.__cause__, XbrlQueryExecutionError)


def test_fins_read_runtime_weak_typing_guards_lock_owner_boundaries() -> None:
    """锁住本轮 read runtime weak typing 修复边界。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    read_runtime_path = Path("dayu/fins/tools/read_runtime.py")
    read_helpers_path = Path("dayu/fins/tools/read_runtime_helpers.py")
    read_runtime_tree = _parse_module(read_runtime_path)
    read_helpers_tree = _parse_module(read_helpers_path)

    assert _getattr_processor_call_lines(read_runtime_tree) == []
    assert _getattr_processor_call_lines(read_helpers_tree) == []
    assert not _function_returns_list_dict_any(read_runtime_tree, "_collect_source_documents")
    assert not _function_returns_list_dict_any(read_runtime_tree, "_collect_source_documents_by_kind")

    forbidden_argument_annotations = (
        ("dayu/fins/storage/_fs_storage_utils.py", "_coerce_optional_int", "value"),
        ("dayu/fins/processors/sec_section_build.py", "_normalize_table_objects", "table_objects"),
        (
            "dayu/fins/processors/sec_report_form_common.py",
            "_rebuild_virtual_sections_from_edgartools",
            "document",
        ),
        ("dayu/fins/processors/sec_form_section_common.py", "_build_structured_split_anchor", "section_ref"),
        ("dayu/documents/processors/docling_processor.py", "_normalize_label", "raw_label"),
    )
    for path_text, function_name, argument_name in forbidden_argument_annotations:
        tree = _parse_module(Path(path_text))
        assert not _function_argument_has_weak_annotation(tree, function_name, argument_name), (
            f"{path_text}:{function_name}({argument_name}) still uses object/Any"
        )


def test_read_runtime_has_no_revision_hash_double_read_or_source_kind_probe() -> None:
    """read runtime 不得重建 revision、double-read 或自行探测 source kind。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: consumer 旧一致性算法或 source kind probing 回归时抛出。
    """

    path = Path("dayu/fins/tools/read_runtime.py")
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    forbidden_names = {
        "_build_source_" + "revision",
        "_resolve_source_kind",
        "_get_document_meta_cached",
        "_get_source_meta_cached_by_kind",
        "revision_" + "before",
        "revision_" + "after",
    }
    assert forbidden_names.isdisjoint(node.id for node in ast.walk(tree) if isinstance(node, ast.Name))
    forbidden_repository_calls = (
        "get_source_" + "revision",
        "get_document_provenance",
        "get_source_handle",
        "get_primary_source",
        "get_source",
    )
    repository_calls = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and ast.unparse(node.func.value).endswith("_source_repository")
    }
    assert repository_calls.isdisjoint(forbidden_repository_calls)
    assert "hashlib" not in source
    assert ".digest" not in source


def test_list_documents_uses_two_typed_storage_lists_without_per_document_snapshot(
    tmp_path: Path,
) -> None:
    """list_documents 只组合 filing/material typed list，不构造 per-document snapshot。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: list 路径触发 kind probing 或 snapshot N+1 时抛出。
    """

    runtime, source_repository = _build_runtime_with_source_documents(
        tmp_path,
        processor_cache_max_entries=4,
    )

    result = runtime.list_documents(ticker="AAPL")

    assert result["total"] == 3
    assert source_repository.list_source_document_ids_calls == [
        SourceKind.FILING,
        SourceKind.MATERIAL,
    ]
    assert source_repository.get_source_meta_calls == 3
    assert source_repository.snapshot_read_calls == 0


def test_list_documents_projects_stable_document_type_and_filter_contract(
    tmp_path: Path,
) -> None:
    """list_documents 公共投影统一拥有文档类型、过滤与无匹配建议语义。

    Args:
        tmp_path: pytest 临时目录，用于创建真实 filesystem repositories。

    Returns:
        无。

    Raises:
        AssertionError: canonical 类型、normalized filters、过滤结果、建议或 typed failure 漂移时抛出。
        OSError: 真实 filesystem repository 写入失败时抛出。
    """

    runtime, source_repository = _build_runtime_with_source_documents(
        tmp_path,
        processor_cache_max_entries=4,
    )
    batch = source_repository._batching_repository.begin_batch("AAPL")
    _create_source_document(
        source_repository=source_repository,
        blob_repository=source_repository._blob_repository,
        batch=batch,
        document_id="material-earnings-call",
        source_kind=SourceKind.MATERIAL,
        form_type="EARNINGS_CALLS",
    )
    source_repository._batching_repository.commit_batch(batch)

    unfiltered_result = runtime.list_documents(ticker="AAPL")
    document_types_by_id = {
        document["document_id"]: document["document_type"] for document in unfiltered_result["documents"]
    }
    assert document_types_by_id == {
        "doc-1": "annual_report",
        "doc-2": "annual_report",
        "doc-3": "annual_report",
        "material-earnings-call": "earnings_call",
    }

    filtered_result = runtime.list_documents(
        ticker="AAPL",
        document_types=[
            " earnings_call ",
            "earnings_call",
            "unknown_document_type",
        ],
        fiscal_periods=["FY"],
    )
    assert filtered_result["filters"] == {
        "document_types": ["earnings_call"],
        "fiscal_years": None,
        "fiscal_periods": ["FY"],
    }
    assert {document["document_id"]: document["document_type"] for document in filtered_result["documents"]} == {
        "material-earnings-call": "earnings_call"
    }
    assert filtered_result["matched"] == 1
    assert filtered_result["match_status"] == "ok"
    assert "suggestion" not in filtered_result

    no_match_result = runtime.list_documents(
        ticker="AAPL",
        document_types=["proxy"],
        fiscal_periods=["FY"],
    )
    assert no_match_result["documents"] == []
    assert no_match_result["matched"] == 0
    assert no_match_result["match_status"] == "no_match"
    assert "suggestion" in no_match_result
    assert no_match_result["suggestion"] == {
        "action": "broaden_filter",
        "available_document_types": ["annual_report", "earnings_call"],
        "reason": "no_documents_matched_document_types",
    }

    with pytest.raises(FinsReadArgumentError) as error_info:
        runtime.list_documents(ticker="   ")
    assert error_info.value.tool_name == "list_documents"
    assert error_info.value.arg_name == "ticker"


def test_read_section_projects_minimal_navigation_payload_and_rejects_unknown_ref(
    tmp_path: Path,
) -> None:
    """read_section 公共 owner 投影最小导航载荷并转换未知 ref failure。

    Args:
        tmp_path: pytest 临时目录，用于创建真实 filesystem repositories。

    Returns:
        无。

    Raises:
        AssertionError: children、page range、identity、citation 或 public typed failure 漂移时抛出。
        OSError: 真实 filesystem repository 读取或写入失败时抛出。
    """

    processor = _SectionPayloadProcessor(_FakeSource())
    runtime, _source_repository = _build_runtime_with_source_documents(
        tmp_path,
        processor_cache_max_entries=4,
        processor_registry=_FixedProcessorRegistry(processor),
    )

    result = runtime.read_section(
        ticker="AAPL",
        document_id="doc-1",
        ref="section-1",
    )

    assert set(result) == {
        "ticker",
        "document_id",
        "ref",
        "title",
        "item",
        "topic",
        "content",
        "children",
        "page_range",
        "content_word_count",
        "citation",
    }
    assert result["ticker"] == "AAPL"
    assert result["document_id"] == "doc-1"
    assert result["ref"] == "section-1"
    assert result["title"] == "Item 1. Business"
    assert result["content"] == "Revenue grew while operating costs remained controlled."
    assert result["children"] == [
        {"ref": "child-valid", "title": "Valid Child"},
        {"ref": "child-without-title", "title": None},
    ]
    assert result["page_range"] == [3, 5]
    assert result["content_word_count"] == 7
    assert result["citation"]["ticker"] == "AAPL"
    assert result["citation"]["document_id"] == "doc-1"
    assert result["citation"]["source_type"] == "SEC_EDGAR"
    assert result["citation"]["source_provider"] == "SEC_EDGAR"

    with pytest.raises(FinsReadArgumentError) as error_info:
        runtime.read_section(
            ticker="AAPL",
            document_id="doc-1",
            ref="missing-section",
        )
    assert error_info.value.tool_name == "read_section"
    assert error_info.value.arg_name == "ref"
    assert error_info.value.arg_value == "missing-section"


def test_get_table_projects_self_describing_data_shapes_and_rejects_unknown_ref(
    tmp_path: Path,
) -> None:
    """get_table 公共 owner 投影三类自描述数据并转换未知 table_ref failure。

    Args:
        tmp_path: pytest 临时目录，用于创建真实 filesystem repositories。

    Returns:
        无。

    Raises:
        AssertionError: data shape、table identity、citation 或 public typed failure 漂移时抛出。
        OSError: 真实 filesystem repository 读取或写入失败时抛出。
    """

    processor = _TablePayloadProcessor(_FakeSource())
    runtime, _source_repository = _build_runtime_with_source_documents(
        tmp_path,
        processor_cache_max_entries=4,
        processor_registry=_FixedProcessorRegistry(processor),
    )

    records_result = runtime.get_table(
        ticker="AAPL",
        document_id="doc-1",
        table_ref="records-table",
    )
    markdown_result = runtime.get_table(
        ticker="AAPL",
        document_id="doc-1",
        table_ref="markdown-table",
    )
    text_result = runtime.get_table(
        ticker="AAPL",
        document_id="doc-1",
        table_ref="text-table",
    )

    assert records_result["data"] == {
        "kind": "records",
        "description": "Structured table data; rows are row-level objects, columns define column order.",
        "columns": ["Quarter", "Revenue"],
        "rows": [{"Quarter": "Q1", "Revenue": 100}],
    }
    assert records_result["row_count"] == 1
    assert records_result["col_count"] == 2
    assert records_result["is_financial"] is True
    assert records_result["table_type"] == "financial"
    assert "caption" in records_result
    assert records_result["caption"] == "Revenue by quarter"
    assert "page_no" in records_result
    assert records_result["page_no"] == 7

    assert markdown_result["data"] == {
        "kind": "markdown",
        "description": "Markdown table text, ready to render.",
        "markdown": "| Metric | Value |\n| --- | ---: |\n| Revenue | 100 |",
    }
    assert markdown_result["table_type"] == "data"

    assert text_result["data"] == {
        "kind": "raw_text",
        "description": "Raw text content; does not meet standard Markdown table structure.",
        "text": "Revenue was 100 in the reported period.",
    }
    assert text_result["table_type"] is None

    results_by_ref = {result["table_ref"]: result for result in (records_result, markdown_result, text_result)}
    assert set(results_by_ref) == {
        "records-table",
        "markdown-table",
        "text-table",
    }
    for table_ref, result in results_by_ref.items():
        assert result["ticker"] == "AAPL"
        assert result["document_id"] == "doc-1"
        assert result["table_ref"] == table_ref
        assert result["citation"]["ticker"] == "AAPL"
        assert result["citation"]["document_id"] == "doc-1"
        assert result["citation"]["source_type"] == "SEC_EDGAR"
        assert result["citation"]["source_provider"] == "SEC_EDGAR"

    with pytest.raises(FinsReadArgumentError) as error_info:
        runtime.get_table(
            ticker="AAPL",
            document_id="doc-1",
            table_ref="missing-table",
        )
    assert error_info.value.tool_name == "get_table"
    assert error_info.value.arg_name == "table_ref"
    assert error_info.value.arg_value == "missing-table"


def test_query_xbrl_facts_selects_default_concepts_from_typed_taxonomy(
    tmp_path: Path,
) -> None:
    """query_xbrl_facts 公共 owner 按 form/taxonomy 选择默认 concepts 并保留 typed failure。

    Args:
        tmp_path: pytest 临时目录，用于创建相互独立的真实 filesystem repositories。

    Returns:
        无。

    Raises:
        AssertionError: 默认 concept 选择、public query_params 或 typed business failure 漂移时抛出。
        OSError: 真实 filesystem repository 读取或写入失败时抛出。
    """

    us_gaap_processor = _DefaultConceptsXbrlProcessor(
        _FakeSource(),
        taxonomy="US-GAAP 2024",
    )
    us_gaap_runtime, _us_gaap_source_repository = _build_runtime_with_source_documents(
        tmp_path / "us-gaap",
        processor_cache_max_entries=4,
        processor_registry=_FixedProcessorRegistry(us_gaap_processor),
    )

    us_gaap_result = us_gaap_runtime.query_xbrl_facts(
        ticker="AAPL",
        document_id="doc-1",
    )
    assert _is_xbrl_query_result(us_gaap_result)
    expected_annual_us_gaap_concepts = [
        "Revenues",
        "NetIncomeLoss",
        "Assets",
        "Liabilities",
        "StockholdersEquity",
        "NetCashProvidedByUsedInOperatingActivities",
    ]
    assert us_gaap_result["query_params"] == {
        "concepts": expected_annual_us_gaap_concepts,
    }
    assert us_gaap_result["facts"][0]["concept"] == expected_annual_us_gaap_concepts[0]
    assert us_gaap_result["fact_count"] == 1

    unknown_taxonomy_processor = _DefaultConceptsXbrlProcessor(
        _FakeSource(),
        taxonomy="custom-financial-taxonomy",
    )
    unknown_taxonomy_runtime, _unknown_source_repository = _build_runtime_with_source_documents(
        tmp_path / "unknown-taxonomy",
        processor_cache_max_entries=4,
        processor_registry=_FixedProcessorRegistry(unknown_taxonomy_processor),
    )

    unknown_taxonomy_result = unknown_taxonomy_runtime.query_xbrl_facts(
        ticker="AAPL",
        document_id="doc-1",
    )
    assert _is_xbrl_query_result(unknown_taxonomy_result)
    expected_global_concepts = ["Revenues", "NetIncomeLoss", "Assets"]
    assert unknown_taxonomy_result["query_params"] == {
        "concepts": expected_global_concepts,
    }
    assert unknown_taxonomy_result["facts"][0]["concept"] == expected_global_concepts[0]
    assert unknown_taxonomy_result["fact_count"] == 1

    failing_processor = _DefaultConceptsXbrlProcessor(
        _FakeSource(),
        taxonomy="custom-financial-taxonomy",
        fail_query=True,
    )
    failing_runtime, _failing_source_repository = _build_runtime_with_source_documents(
        tmp_path / "failing-taxonomy-query",
        processor_cache_max_entries=4,
        processor_registry=_FixedProcessorRegistry(failing_processor),
    )

    with pytest.raises(FinsReadBusinessError) as error_info:
        failing_runtime.query_xbrl_facts(
            ticker="AAPL",
            document_id="doc-1",
        )
    assert error_info.value.code == "xbrl_query_failed"
    assert isinstance(error_info.value.__cause__, XbrlQueryExecutionError)
    assert error_info.value.__cause__.failed_concepts == tuple(expected_global_concepts)


def test_search_next_section_projection_ranks_business_evidence_per_query() -> None:
    """search next-step owner 只按稳定业务 evidence 投影单/多查询下一章节。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 排名、按查询映射、业务字段清洗或 malformed input 处理漂移时抛出。
    """

    matches = [
        {
            "section": {
                "ref": " risk-section ",
                "title": " Risk Factors ",
                "item": " Item 1A ",
                "topic": " risk_factors ",
            },
            "matched_query": "risk",
            "is_exact_phrase": True,
        },
        {
            "section": {
                "ref": "risk-section",
                "title": "Risk Factors",
                "item": "Item 1A",
                "topic": "risk_factors",
            },
            "matched_query": "risk",
            "is_exact_phrase": False,
        },
        {
            "section": {
                "ref": "liquidity-section",
                "title": "Liquidity",
                "item": "Item 7",
                "topic": "liquidity",
            },
            "matched_query": "risk",
            "is_exact_phrase": False,
        },
        {
            "section": {
                "ref": "business-section",
                "title": "Business",
                "item": "Item 1",
                "topic": "business",
            },
            "matched_query": "revenue",
            "is_exact_phrase": False,
        },
        {
            "section": {
                "ref": "business-section",
                "title": "Business",
                "item": "Item 1",
                "topic": "business",
            },
            "matched_query": "revenue",
            "is_exact_phrase": True,
        },
        {
            "section": {
                "ref": "risk-section",
                "title": "Risk Factors",
                "item": "Item 1A",
                "topic": "risk_factors",
            },
            "matched_query": "revenue",
            "is_exact_phrase": False,
        },
        {
            "section": {"ref": "   ", "title": "Invalid blank ref"},
            "matched_query": "risk",
            "is_exact_phrase": True,
        },
        {
            "section": {"title": "Missing ref"},
            "matched_query": "revenue",
            "is_exact_phrase": True,
        },
        {
            "matched_query": "risk",
            "is_exact_phrase": True,
        },
    ]

    next_section, next_section_by_query = build_search_next_section_fields(
        matches=matches,
    )
    assert next_section == {
        "section": {
            "ref": "risk-section",
            "title": "Risk Factors",
            "item": "Item 1A",
            "topic": "risk_factors",
        },
        "evidence_hit_count": 3,
    }
    assert next_section_by_query is None

    reversed_next_section, reversed_by_query = build_search_next_section_fields(
        matches=list(reversed(matches)),
    )
    assert reversed_next_section == next_section
    assert reversed_by_query is None

    multi_next_section, multi_by_query = build_search_next_section_fields(
        matches=matches,
        queries=["risk", "revenue", "no evidence", "   "],
    )
    assert multi_next_section is None
    assert multi_by_query == {
        "risk": {
            "section": {
                "ref": "risk-section",
                "title": "Risk Factors",
                "item": "Item 1A",
                "topic": "risk_factors",
            },
            "evidence_hit_count": 2,
        },
        "revenue": {
            "section": {
                "ref": "business-section",
                "title": "Business",
                "item": "Item 1",
                "topic": "business",
            },
            "evidence_hit_count": 2,
        },
        "no evidence": None,
    }


def test_document_type_resolver_projects_material_other_and_cn_categories() -> None:
    """文档类型 public owner 投影材料、其它 filing 与中国财期分类。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 任一文档类型业务分类漂移时抛出。
    """

    assert (
        resolve_document_type_for_source(
            form_type="UNLISTED_MATERIAL",
            source_kind=SourceKind.MATERIAL.value,
        )
        == "material"
    )
    assert (
        resolve_document_type_for_source(
            form_type=None,
            source_kind=SourceKind.FILING.value,
        )
        == "other"
    )
    assert (
        resolve_document_type_for_source(
            form_type="FY",
            source_kind=SourceKind.FILING.value,
        )
        == "annual_report"
    )


def test_fins_import_boundary_keeps_host_exception_narrow() -> None:
    """Fins import boundary 只允许 wait adapter 依赖 Host wait contract。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    offenders: list[str] = []
    for path in Path("dayu/fins").rglob("*.py"):
        forbidden_roots = _forbidden_import_roots(path)
        imported_modules = _module_imports(path)
        if any(_is_forbidden_import(name, forbidden_roots) for name in imported_modules):
            offenders.append(str(path))

    assert offenders == []


def _build_runtime_with_source_documents(
    tmp_path: Path,
    *,
    processor_cache_max_entries: int,
    processor_registry: ProcessorRegistry | None = None,
) -> tuple[FinsReadRuntime, _CountingSourceRepository]:
    """构造带多个 source document 的 read runtime 与计数仓储。

    Args:
        tmp_path: pytest 临时目录。
        processor_cache_max_entries: snapshot processor 缓存容量。
        processor_registry: 可选 processor registry。

    Returns:
        已装配真实仓储的 read runtime 与 source 仓储。

    Raises:
        OSError: 仓储写入失败时抛出。
    """

    workspace_root = tmp_path / "read-runtime-cache"
    repository_set = build_fs_repository_set(workspace_root=workspace_root)
    company_repository = FsCompanyMetaRepository(workspace_root, repository_set=repository_set)
    source_repository = _CountingSourceRepository(workspace_root, repository_set=repository_set)
    blob_repository = FsDocumentBlobRepository(workspace_root, repository_set=repository_set)
    processed_repository = FsProcessedDocumentRepository(workspace_root, repository_set=repository_set)
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
    for index in range(1, 4):
        _create_source_document(
            source_repository=source_repository,
            blob_repository=blob_repository,
            batch=batch,
            document_id=f"doc-{index}",
            source_kind=SourceKind.FILING,
            form_type="10-K",
        )
    batching_repository.commit_batch(batch)
    runtime = FinsReadRuntime(
        company_repository=company_repository,
        source_repository=source_repository,
        processed_repository=processed_repository,
        processor_registry=processor_registry or ProcessorRegistry(),
        processor_cache_max_entries=processor_cache_max_entries,
    )
    return runtime, source_repository


def _create_source_document(
    *,
    source_repository: FsSourceDocumentRepository,
    blob_repository: FsDocumentBlobRepository,
    batch: BatchToken,
    document_id: str,
    source_kind: SourceKind,
    form_type: str,
) -> None:
    """创建测试 source document。

    Args:
        source_repository: source 仓储。
        blob_repository: blob 仓储。
        batch: 显式 transaction capability。
        document_id: 文档 ID。
        source_kind: 来源类型。
        form_type: 表单类型。

    Returns:
        无。

    Raises:
        OSError: 仓储写入失败时抛出。
    """

    meta: dict[str, JsonValue] = {
        "ingest_method": "download",
        "source_provider": FinsSourceProvider.SEC_EDGAR.to_storage_value(),
        "ingest_complete": True,
        "fiscal_year": 2024,
        "fiscal_period": "FY",
        "filing_date": "2024-11-01",
        "report_date": "2024-09-28",
        "amended": False,
    }
    filename = f"{document_id}.txt"
    file_meta = blob_repository.store_file(
        SourceHandle("AAPL", document_id, source_kind.value),
        filename,
        BytesIO(document_id.encode("utf-8")),
        batch=batch,
        content_type="text/plain",
    )
    source_repository.create_source_document(
        SourceDocumentUpsertRequest(
            ticker="AAPL",
            document_id=document_id,
            internal_document_id=document_id,
            form_type=form_type,
            primary_document=filename,
            files=[file_meta],
            meta=meta,
        ),
        source_kind,
        batch=batch,
    )


def _is_financial_statement_result(
    result: PublicFinancialStatementResult | NotSupportedResult,
) -> TypeGuard[PublicFinancialStatementResult]:
    """判断结果是否为财务报表成功载荷。

    Args:
        result: read runtime 返回结果。

    Returns:
        包含 rows 字段时返回 ``True``。

    Raises:
        无。
    """

    return "rows" in result


def _is_xbrl_query_result(
    result: PublicXbrlQueryResult | NotSupportedResult,
) -> TypeGuard[PublicXbrlQueryResult]:
    """判断结果是否为 XBRL 查询成功载荷。

    Args:
        result: read runtime 返回结果。

    Returns:
        包含 facts 业务字段时返回 ``True``。

    Raises:
        无。
    """

    return "facts" in result


def _parse_module(path: Path) -> ast.Module:
    """解析 Python 模块 AST。

    Args:
        path: Python 文件路径。

    Returns:
        Python 模块 AST。

    Raises:
        SyntaxError: 源码无法解析时抛出。
    """

    return ast.parse(path.read_text(encoding="utf-8"))


def _getattr_processor_call_lines(tree: ast.Module) -> list[int]:
    """返回 `getattr(processor, ...)` 调用所在行号。

    Args:
        tree: Python 模块 AST。

    Returns:
        命中调用的行号列表。

    Raises:
        无。
    """

    lines: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Name) or node.func.id != "getattr":
            continue
        if not node.args:
            continue
        first_arg = node.args[0]
        if isinstance(first_arg, ast.Name) and first_arg.id == "processor":
            lines.append(node.lineno)
    return lines


def _function_returns_list_dict_any(tree: ast.Module, function_name: str) -> bool:
    """判断函数返回注解是否为 `list[dict[str, Any]]`。

    Args:
        tree: Python 模块 AST。
        function_name: 函数名。

    Returns:
        命中时返回 ``True``。

    Raises:
        无。
    """

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == function_name:
            return _annotation_text(node.returns) == "list[dict[str, Any]]"
    return False


def _function_argument_has_weak_annotation(tree: ast.Module, function_name: str, argument_name: str) -> bool:
    """判断指定函数参数是否使用 `object` 或 `Any` 注解。

    Args:
        tree: Python 模块 AST。
        function_name: 函数名。
        argument_name: 参数名。

    Returns:
        命中弱类型注解时返回 ``True``。

    Raises:
        无。
    """

    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or node.name != function_name:
            continue
        for arg in [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]:
            if arg.arg != argument_name:
                continue
            return _annotation_text(arg.annotation) in {"object", "Any", "typing.Any"}
    return False


def _annotation_text(annotation: ast.expr | None) -> str:
    """返回注解 AST 的稳定文本。

    Args:
        annotation: 注解 AST；无注解时为 ``None``。

    Returns:
        注解文本；无注解时返回空字符串。

    Raises:
        无。
    """

    if annotation is None:
        return ""
    return ast.unparse(annotation)


def _module_imports(path: Path) -> set[str]:
    """解析 Python 文件的 import 目标。

    Args:
        path: Python 文件路径。

    Returns:
        import 模块集合。

    Raises:
        SyntaxError: 源码无法解析时抛出。
    """

    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.add(node.module)
            for alias in node.names:
                if alias.name != "*":
                    modules.add(f"{node.module}.{alias.name}")
    return modules


def _is_forbidden_import(module_name: str, forbidden_roots: tuple[str, ...]) -> bool:
    """判断 import 目标是否命中禁用根模块。

    Args:
        module_name: AST 解析出的模块名。
        forbidden_roots: 禁用根模块集合。

    Returns:
        命中时返回 ``True``。

    Raises:
        无。
    """

    return any(module_name == root or module_name.startswith(f"{root}.") for root in forbidden_roots)


def _forbidden_import_roots(path: Path) -> tuple[str, ...]:
    """返回 Fins 文件适用的禁用 import 根模块。

    Args:
        path: Fins Python 文件路径。

    Returns:
        禁用 import 根模块集合。

    Raises:
        无。
    """

    if path.resolve(strict=False) == _FINS_WAIT_ADAPTER_PATH:
        return _FINS_WAIT_ADAPTER_FORBIDDEN_IMPORT_ROOTS
    return _FINS_FORBIDDEN_IMPORT_ROOTS
