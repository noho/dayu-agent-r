"""Fins read runtime 语义所有权守护测试。"""

from __future__ import annotations

import ast
from collections.abc import Callable
from io import BytesIO
from pathlib import Path
from typing import TypeGuard

import pytest

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
    validate_financial_statement_result_payload,
)
from dayu.fins.domain.xbrl_result_contract import XbrlQueryExecutionError
from dayu.fins.storage import (
    FsBatchingRepository,
    FsCompanyMetaRepository,
    FsDocumentBlobRepository,
    FsProcessedDocumentRepository,
    FsSourceDocumentRepository,
)
from dayu.fins.storage._fs_repository_factory import _FsRepositorySet, build_fs_repository_set
from dayu.fins.tools.read_runtime import FinsReadRuntime, _parse_source_document_meta
from dayu.fins.tools.read_runtime_helpers import FinsReadBusinessError, _resolve_processor_taxonomy
from dayu.fins.tools.result_types import FinancialStatementResult, NotSupportedResult

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
    """统计 source meta 读取次数的测试仓储。"""

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


def test_read_runtime_source_meta_cache_is_bounded(tmp_path: Path) -> None:
    """source meta cache 不得超过配置上限。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    runtime, source_repository = _build_runtime_with_source_documents(tmp_path, source_meta_cache_max_entries=2)

    assert runtime._get_document_meta_cached("AAPL", "doc-1") is not None
    assert runtime._get_document_meta_cached("AAPL", "doc-2") is not None
    assert runtime._get_document_meta_cached("AAPL", "doc-3") is not None
    assert source_repository.get_source_meta_calls == 3

    assert runtime._get_document_meta_cached("AAPL", "doc-1") is not None
    assert source_repository.get_source_meta_calls == 4


def test_read_runtime_source_meta_cache_is_partitioned_by_source_kind(tmp_path: Path) -> None:
    """source meta by-kind 缓存不得混用不同来源类型。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    runtime, source_repository = _build_runtime_with_source_documents(tmp_path, source_meta_cache_max_entries=4)
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

    filing_meta = runtime._get_source_meta_cached_by_kind("AAPL", "doc-1", SourceKind.FILING)
    material_meta = runtime._get_source_meta_cached_by_kind("AAPL", "doc-1", SourceKind.MATERIAL)
    cached_filing_meta = runtime._get_source_meta_cached_by_kind("AAPL", "doc-1", SourceKind.FILING)
    cached_material_meta = runtime._get_source_meta_cached_by_kind("AAPL", "doc-1", SourceKind.MATERIAL)

    assert filing_meta["form_type"] == "10-K"
    assert material_meta["form_type"] == "EX-99"
    assert cached_filing_meta["form_type"] == "10-K"
    assert cached_material_meta["form_type"] == "EX-99"
    assert source_repository.get_source_meta_calls_by_kind == {
        SourceKind.FILING: 1,
        SourceKind.MATERIAL: 1,
    }


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
                "reason": "statement_empty",
                "statement_locator": {
                    "statement_type": "income_statement",
                    "statement_title": "Income Statement",
                    "period_labels": [],
                    "row_labels": [],
                },
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
                "reason": "statement_empty",
                "statement_locator": {
                    "statement_type": "income_statement",
                    "statement_title": "Income Statement",
                    "period_labels": [],
                    "row_labels": [],
                },
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
                "reason": None,
                "statement_locator": {
                    "statement_type": "income_statement",
                    "statement_title": "Income Statement",
                    "period_labels": ["FY2025"],
                    "row_labels": ["Revenue"],
                },
        }
    )
    runtime, _source_repository = _build_runtime_with_source_documents(
        tmp_path,
        source_meta_cache_max_entries=4,
        processor_registry=_FixedProcessorRegistry(processor),
    )

    result = runtime.get_financial_statement(ticker="AAPL", document_id="doc-1", statement_type="income_statement")

    assert _is_financial_statement_result(result)
    assert result["periods"][0]["fiscal_year"] == 2025
    assert result["rows"] == [{"concept": "Revenue", "label": "Revenue", "values": [100]}]
    assert result["units"] == "USD"
    assert result["scale"] == "millions"
    assert result["data_quality"] == "xbrl"
    assert result["reason"] is None
    assert result["statement_locator"] == {
        "statement_type": "income_statement",
        "statement_title": "Income Statement",
        "period_labels": ["FY2025"],
        "row_labels": ["Revenue"],
    }


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
        source_meta_cache_max_entries=4,
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
    source_meta_cache_max_entries: int,
    processor_registry: ProcessorRegistry | None = None,
) -> tuple[FinsReadRuntime, _CountingSourceRepository]:
    """构造带多个 source document 的 read runtime 与计数仓储。

    Args:
        tmp_path: pytest 临时目录。
        source_meta_cache_max_entries: source meta 缓存容量。
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
        source_meta_cache_max_entries=source_meta_cache_max_entries,
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
    result: FinancialStatementResult | NotSupportedResult,
) -> TypeGuard[FinancialStatementResult]:
    """判断结果是否为财务报表成功载荷。

    Args:
        result: read runtime 返回结果。

    Returns:
        包含 rows 字段时返回 ``True``。

    Raises:
        无。
    """

    return "rows" in result


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
