"""SecPipeline upload filing stream 测试。"""

from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path

import pytest

import dayu.fins.pipelines.sec_upload_workflow as sec_upload_workflow
from dayu.contracts.cancellation import CancellationToken
from dayu.fins.domain.document_models import BatchToken, CompanyMeta, CompanyMetaInventoryEntry, now_iso8601
from dayu.fins.domain.enums import SourceKind
from dayu.fins.ingestion_runtime import (
    FinsUploadFilingRequest,
    FinsUploadUsageCode,
    FinsUploadUsageError,
    ValidatedFinsUploadFilingRequest,
)
from dayu.fins.pipelines.sec_pipeline import SecPipeline
from dayu.fins.pipelines.docling_process_converter import (
    DoclingConversionConfig,
    DoclingConversionCancelledError,
    DoclingConversionError,
    DoclingConversionFailureKind,
    DoclingConversionResult,
)
from dayu.fins.pipelines.upload_filing_events import UploadFilingEventType
from dayu.fins.pipelines.upload_company_meta import (
    RESOLVER_VERSION,
    _normalize_ticker_aliases,
    upsert_company_meta_for_upload,
)
from dayu.fins.processors.registry import build_fins_processor_registry
from dayu.fins.service_runtime import prevalidate_fins_upload_filing_request_for_workspace
from dayu.fins.storage import (
    FilingUploadPublishedState,
    FsDocumentBlobRepository,
    FsFilingUploadStateRepository,
)
from dayu.fins.storage._fs_repository_factory import build_fs_repository_set

from .upload_filing_test_support import (
    TrackingBatchingRepository,
    TrackingCompanyMetaRepository,
    TrackingSourceDocumentRepository,
    published_tree_sha256,
)


class _SpyCompanyMetaRepository:
    """记录 company meta 写入次数的测试仓储。"""

    def __init__(self) -> None:
        """初始化空仓储。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        self.writes: list[CompanyMeta] = []

    def scan_company_meta_inventory(self) -> list[CompanyMetaInventoryEntry]:
        """返回空盘点结果。

        Args:
            无。

        Returns:
            空列表。

        Raises:
            无。
        """

        return []

    def get_company_meta(self, ticker: str) -> CompanyMeta:
        """模拟 company meta 不存在。

        Args:
            ticker: 查询 ticker。

        Returns:
            不返回。

        Raises:
            FileNotFoundError: 始终抛出以模拟空仓储。
        """

        raise FileNotFoundError(ticker)

    def upsert_company_meta(self, meta: CompanyMeta, *, batch: BatchToken) -> None:
        """记录一次 company meta 写入。

        Args:
            meta: 待写入公司元数据。

        Returns:
            无。

        Raises:
            无。
        """

        del batch
        self.writes.append(meta)

    def resolve_existing_ticker(self, ticker_candidates: list[str]) -> str | None:
        """模拟无候选 ticker 已存在。

        Args:
            ticker_candidates: ticker 候选列表。

        Returns:
            始终返回 ``None``。

        Raises:
            无。
        """

        del ticker_candidates
        return None


class _FakeDoclingConverter:
    """SEC filing 测试用 typed converter。"""

    def __init__(self, calls: list[str] | None = None) -> None:
        """初始化 converter。

        Args:
            calls: 可选转换调用记录。

        Returns:
            无。

        Raises:
            无。
        """

        self._calls = calls

    async def convert_to_json_bytes(
        self,
        input_bytes: bytes,
        stream_name: str,
        *,
        config: DoclingConversionConfig,
        cancellation: CancellationToken | None,
    ) -> DoclingConversionResult:
        """返回固定 typed JSON bytes。

        Args:
            input_bytes: 输入字节。
            stream_name: 输入名称。
            config: 闭合转换配置。
            cancellation: canonical token。

        Returns:
            typed conversion result。

        Raises:
            无。
        """

        del input_bytes, config, cancellation
        if self._calls is not None:
            self._calls.append(stream_name)
        data = ('{"name": "' + stream_name + '", "format": "docling"}').encode()
        return DoclingConversionResult(data, len(data), hashlib.sha256(data).hexdigest())


class _FailingDoclingConverter:
    """抛出指定 typed/runtime exception 的 converter 测试替身。"""

    def __init__(self, error: Exception) -> None:
        """初始化 failure converter。

        Args:
            error: conversion 调用应抛出的异常。

        Returns:
            无。

        Raises:
            无。
        """

        self.error = error

    async def convert_to_json_bytes(
        self,
        input_bytes: bytes,
        stream_name: str,
        *,
        config: DoclingConversionConfig,
        cancellation: CancellationToken | None,
    ) -> DoclingConversionResult:
        """抛出预设异常以验证 workflow typed catch 顺序。

        Args:
            input_bytes: 输入字节。
            stream_name: 输入名称。
            config: 闭合转换配置。
            cancellation: canonical cancellation token。

        Returns:
            不返回。

        Raises:
            Exception: 始终抛出构造时传入的异常。
        """

        del input_bytes, stream_name, config, cancellation
        raise self.error


def _validated_sec_filing_request(
    *,
    pipeline: SecPipeline,
    filing_file: Path,
    action: str | None,
    company_name: str | None,
    overwrite: bool = False,
    ticker_aliases: tuple[str, ...] = (),
    fiscal_year: int = 2025,
    fiscal_period: str = "Q1",
    filing_date: str | None = None,
    report_date: str | None = None,
) -> ValidatedFinsUploadFilingRequest:
    """使用 production validator 构造 SEC filing 测试请求。

    Args:
        pipeline: 持有当前 published state 的 SEC pipeline。
        filing_file: 上传文件。
        action: 请求动作；``None`` 表示 auto。
        company_name: 可选公司名称。
        overwrite: 是否覆盖既有 filing。
        ticker_aliases: 可选 ticker aliases。
        fiscal_year: 财年。
        fiscal_period: 财期。
        filing_date: 可选披露日期。
        report_date: 可选报告日期。

    Returns:
        由 production storage/validator owner 产生的 validated request。

    Raises:
        FinsUploadUsageError: 请求不满足 filing usage contract 时抛出。
        OSError: published state 读取失败时抛出。
        ValueError: published state 损坏时抛出。
    """

    return prevalidate_fins_upload_filing_request_for_workspace(
        FinsUploadFilingRequest(
            ticker="AAPL",
            action=action or "auto",
            files=(filing_file,),
            fiscal_year=fiscal_year,
            fiscal_period=fiscal_period,
            filing_date=filing_date,
            report_date=report_date,
            company_name=company_name,
            ticker_aliases=ticker_aliases,
            overwrite=overwrite,
        ),
        workspace_root=pipeline._workspace_root,
    )


def _tracking_sec_pipeline(
    workspace_root: Path,
    *,
    converter_calls: list[str] | None = None,
) -> tuple[
    SecPipeline,
    TrackingBatchingRepository,
    TrackingCompanyMetaRepository,
    TrackingSourceDocumentRepository,
]:
    """构造共享同一 FS core 的 SEC upload tracking composition。

    Args:
        workspace_root: 测试工作区根目录。
        converter_calls: 可选转换调用记录。

    Returns:
        pipeline、batch、company 与 source tracking repositories。

    Raises:
        OSError: storage composition 初始化失败时抛出。
    """

    repository_set = build_fs_repository_set(
        workspace_root=workspace_root,
        create_directories=False,
    )
    batching = TrackingBatchingRepository(workspace_root, repository_set=repository_set)
    company = TrackingCompanyMetaRepository(workspace_root, repository_set=repository_set)
    source = TrackingSourceDocumentRepository(workspace_root, repository_set=repository_set)
    pipeline = SecPipeline(
        workspace_root=workspace_root,
        processor_registry=build_fins_processor_registry(),
        batching_repository=batching,
        company_repository=company,
        source_repository=source,
        blob_repository=FsDocumentBlobRepository(workspace_root, repository_set=repository_set),
        filing_upload_state_repository=FsFilingUploadStateRepository(
            workspace_root,
            repository_set=repository_set,
        ),
        docling_converter=_FakeDoclingConverter(converter_calls),
    )
    return pipeline, batching, company, source


def _seed_sec_upload_company_meta(
    *,
    pipeline: SecPipeline,
    company_name: str,
    resolver_version: str,
    ticker_aliases: list[str],
) -> None:
    """写入 SEC upload 测试用公司元数据。

    Args:
        pipeline: SEC pipeline 实例。
        company_name: 公司名称。
        resolver_version: 元数据 resolver 版本。
        ticker_aliases: ticker alias 列表。

    Returns:
        无。

    Raises:
        OSError: 仓储写入失败时抛出。
    """

    batch = pipeline._batching_repository.begin_batch("AAPL")
    pipeline._company_repository.upsert_company_meta(
        CompanyMeta(
            company_id="AAPL_US",
            company_name=company_name,
            ticker="AAPL",
            market="US",
            resolver_version=resolver_version,
            updated_at=now_iso8601(),
            ticker_aliases=ticker_aliases,
        ),
        batch=batch,
    )
    pipeline._batching_repository.commit_batch(batch)


@pytest.mark.parametrize(
    ("canonical_ticker", "raw_aliases", "expected"),
    [
        ("0700", ["700.HK", "HK.0700", "0700.hk"], ["0700"]),
        ("BRK-B", ["BRK.B", "brk-b.us"], ["BRK-B"]),
        ("AAPL", ["aapl", "AAPL.US", "us.aapl"], ["AAPL"]),
    ],
)
def test_upload_company_meta_ticker_aliases_use_canonical_owner(
    canonical_ticker: str,
    raw_aliases: list[str],
    expected: list[str],
) -> None:
    """upload ticker aliases 应 canonical 化、稳定去重并保持主 ticker 首项。

    Args:
        canonical_ticker: 主 ticker。
        raw_aliases: 含大小写、市场后缀或类股分隔符变体的 aliases。
        expected: 期望 canonical alias 列表。

    Returns:
        无。

    Raises:
        AssertionError: alias owner 未被消费或去重顺序漂移时抛出。
    """

    assert (
        _normalize_ticker_aliases(
            canonical_ticker=canonical_ticker,
            ticker_aliases=raw_aliases,
        )
        == expected
    )


def test_upload_company_meta_invalid_ticker_alias_fails_before_repository_write() -> None:
    """非 ticker alias 必须在 company meta 仓储写入前失败关闭。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 非法 alias 被写入或未抛 ``ValueError`` 时抛出。
    """

    repository = _SpyCompanyMetaRepository()

    with pytest.raises(ValueError, match="无法识别 ticker alias"):
        upsert_company_meta_for_upload(
            repository=repository,
            ticker="AAPL",
            action="create",
            company_id=None,
            company_name="Apple Inc.",
            ticker_aliases=["AAPL", "Apple Inc."],
            batch=BatchToken(transaction_id="invalid-alias", ticker="AAPL"),
        )

    assert repository.writes == []


@pytest.mark.asyncio
async def test_upload_filing_stream_uploads_docling_files(tmp_path: Path) -> None:
    """SEC filing upload stream 应完成上传并生成 Docling 主文件。

    Args:
        tmp_path: 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    pipeline, batching, company, source = _tracking_sec_pipeline(tmp_path)
    filing_file = tmp_path / "filing.pdf"
    filing_file.write_text("demo filing", encoding="utf-8")
    before_tree = published_tree_sha256(tmp_path, "AAPL")

    events = [
        event
        async for event in pipeline.upload_filing_stream(
            _validated_sec_filing_request(
                pipeline=pipeline,
                filing_file=filing_file,
                action="create",
                company_name="Apple Inc.",
                ticker_aliases=("AAPL", "APC"),
                filing_date="2025-05-01",
                report_date="2025-03-31",
            )
        )
    ]

    assert [event.event_type for event in events] == [
        UploadFilingEventType.UPLOAD_STARTED,
        UploadFilingEventType.CONVERSION_STARTED,
        UploadFilingEventType.FILE_UPLOADED,
        UploadFilingEventType.FILE_UPLOADED,
        UploadFilingEventType.UPLOAD_COMPLETED,
    ]
    result_value = events[-1].payload["result"]
    assert isinstance(result_value, dict)
    assert result_value["action"] == "upload_filing"
    assert result_value["ticker"] == "AAPL"
    assert result_value["status"] == "ok"
    assert result_value["stored_file_count"] == 1
    assert str(result_value["document_id"]).startswith("fil_sec_")
    assert result_value["filing_action"] == "create"
    company_meta = pipeline._company_repository.get_company_meta("AAPL")
    assert company_meta.ticker_aliases == ["AAPL", "APC"]
    meta = pipeline._source_repository.get_source_meta(
        "AAPL",
        str(result_value["document_id"]),
        SourceKind.FILING,
    )
    assert str(meta["primary_document"]).endswith("_docling.json")
    assert str(meta["form_type"]) == "Q1"
    after_tree = published_tree_sha256(tmp_path, "AAPL")
    assert before_tree == {}
    assert after_tree
    assert len(batching.begin_tokens) == 1
    assert batching.commit_tokens == batching.begin_tokens
    assert batching.rollback_tokens == []
    assert company.stage_tokens == batching.begin_tokens
    assert source.stage_tokens == batching.begin_tokens


@pytest.mark.asyncio
async def test_upload_filing_stream_preserves_same_version_company_meta(tmp_path: Path) -> None:
    """SEC filing upload 遇到同版本公司元数据时应保留既有值。

    Args:
        tmp_path: 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    pipeline = SecPipeline(
        workspace_root=tmp_path,
        processor_registry=build_fins_processor_registry(),
        docling_converter=_FakeDoclingConverter(),
    )
    _seed_sec_upload_company_meta(
        pipeline=pipeline,
        company_name="Existing Apple",
        resolver_version=RESOLVER_VERSION,
        ticker_aliases=["AAPL", "OLD"],
    )
    filing_file = tmp_path / "filing.pdf"
    filing_file.write_text("demo filing", encoding="utf-8")

    events = [
        event
        async for event in pipeline.upload_filing_stream(
            _validated_sec_filing_request(
                pipeline=pipeline,
                filing_file=filing_file,
                action="create",
                company_name="Ignored Apple",
                ticker_aliases=("AAPL", "NEW"),
            )
        )
    ]

    assert events[-1].event_type == UploadFilingEventType.UPLOAD_COMPLETED
    company_meta = pipeline._company_repository.get_company_meta("AAPL")
    assert company_meta.company_name == "Existing Apple"
    assert company_meta.resolver_version == RESOLVER_VERSION
    assert company_meta.ticker_aliases == ["AAPL", "OLD"]


@pytest.mark.asyncio
async def test_upload_filing_stream_refreshes_stale_company_meta(tmp_path: Path) -> None:
    """SEC filing upload 遇到旧 resolver 版本公司元数据时应刷新。

    Args:
        tmp_path: 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    pipeline = SecPipeline(
        workspace_root=tmp_path,
        processor_registry=build_fins_processor_registry(),
        docling_converter=_FakeDoclingConverter(),
    )
    _seed_sec_upload_company_meta(
        pipeline=pipeline,
        company_name="Stale Apple",
        resolver_version="market_resolver_v0.9.0",
        ticker_aliases=["AAPL", "STALE"],
    )
    filing_file = tmp_path / "filing.pdf"
    filing_file.write_text("demo filing", encoding="utf-8")

    events = [
        event
        async for event in pipeline.upload_filing_stream(
            _validated_sec_filing_request(
                pipeline=pipeline,
                filing_file=filing_file,
                action="create",
                company_name="Apple Refreshed",
                ticker_aliases=("AAPL", "APC"),
            )
        )
    ]

    assert events[-1].event_type == UploadFilingEventType.UPLOAD_COMPLETED
    company_meta = pipeline._company_repository.get_company_meta("AAPL")
    assert company_meta.company_id == "AAPL_US"
    assert company_meta.company_name == "Apple Refreshed"
    assert company_meta.resolver_version == RESOLVER_VERSION
    assert company_meta.ticker_aliases == ["AAPL", "APC"]


@pytest.mark.asyncio
async def test_upload_filing_stream_stale_company_meta_requires_company_name(tmp_path: Path) -> None:
    """SEC filing upload 遇到旧 resolver 版本且缺少公司名时应失败关闭。

    Args:
        tmp_path: 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    pipeline = SecPipeline(
        workspace_root=tmp_path,
        processor_registry=build_fins_processor_registry(),
        docling_converter=_FakeDoclingConverter(),
    )
    _seed_sec_upload_company_meta(
        pipeline=pipeline,
        company_name="Stale Apple",
        resolver_version="market_resolver_v0.9.0",
        ticker_aliases=["AAPL", "STALE"],
    )
    filing_file = tmp_path / "filing.pdf"
    filing_file.write_text("demo filing", encoding="utf-8")

    with pytest.raises(FinsUploadUsageError) as exc_info:
        _validated_sec_filing_request(
            pipeline=pipeline,
            filing_file=filing_file,
            action="create",
            company_name=None,
        )

    assert exc_info.value.failure.code is FinsUploadUsageCode.COMPANY_NAME_REQUIRED
    assert exc_info.value.failure.message == ("当前公司缺少有效元数据；create/update 必须提供 --company-name")
    company_meta = pipeline._company_repository.get_company_meta("AAPL")
    assert company_meta.company_name == "Stale Apple"
    assert company_meta.resolver_version == "market_resolver_v0.9.0"


@pytest.mark.asyncio
async def test_upload_filing_stream_renamed_update_without_overwrite_replaces_complete_set(
    tmp_path: Path,
) -> None:
    """SEC renamed update 不依赖 overwrite，并只发布新完整文件集合。

    Args:
        tmp_path: 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    pipeline = SecPipeline(
        workspace_root=tmp_path,
        processor_registry=build_fins_processor_registry(),
        docling_converter=_FakeDoclingConverter(),
    )
    old_file = tmp_path / "q1_old.pdf"
    new_file = tmp_path / "q1_renamed.pdf"
    sibling_file = tmp_path / "q2_sibling.pdf"
    old_file.write_text("old filing", encoding="utf-8")
    new_file.write_text("new filing", encoding="utf-8")
    sibling_file.write_text("sibling filing", encoding="utf-8")

    create_events = [
        event
        async for event in pipeline.upload_filing_stream(
            _validated_sec_filing_request(
                pipeline=pipeline,
                filing_file=old_file,
                action=None,
                company_name="Apple Inc.",
            )
        )
    ]
    create_result = create_events[-1].payload["result"]
    assert isinstance(create_result, dict)
    assert create_result["filing_action"] == "create"

    skip_events = [
        event
        async for event in pipeline.upload_filing_stream(
            _validated_sec_filing_request(
                pipeline=pipeline,
                filing_file=old_file,
                action=None,
                company_name="Apple Inc.",
            )
        )
    ]
    skip_result = skip_events[-1].payload["result"]
    assert isinstance(skip_result, dict)
    assert skip_result["status"] == "skipped"
    assert skip_result["stored_file_count"] == 0
    assert skip_result["filing_action"] == "update"
    sibling_events = [
        event
        async for event in pipeline.upload_filing_stream(
            _validated_sec_filing_request(
                pipeline=pipeline,
                filing_file=sibling_file,
                action=None,
                company_name="Apple Inc.",
                fiscal_period="Q2",
            )
        )
    ]
    sibling_result = sibling_events[-1].payload["result"]
    assert isinstance(sibling_result, dict)
    sibling_document_id = str(sibling_result["document_id"])
    sibling_meta = pipeline._source_repository.get_source_meta(
        "AAPL",
        sibling_document_id,
        SourceKind.FILING,
    )
    sibling_handle = pipeline._source_repository.get_source_handle(
        "AAPL",
        sibling_document_id,
        SourceKind.FILING,
    )
    sibling_files = pipeline._blob_repository.list_files(sibling_handle)
    company_meta = pipeline._company_repository.get_company_meta("AAPL")

    update_events = [
        event
        async for event in pipeline.upload_filing_stream(
            _validated_sec_filing_request(
                pipeline=pipeline,
                filing_file=new_file,
                action=None,
                company_name="Apple Inc.",
            )
        )
    ]
    update_result = update_events[-1].payload["result"]
    assert isinstance(update_result, dict)
    assert update_result["status"] == "ok"
    assert update_result["filing_action"] == "update"
    assert update_result["document_id"] == create_result["document_id"]

    handle = pipeline._source_repository.get_source_handle(
        "AAPL",
        str(update_result["document_id"]),
        SourceKind.FILING,
    )
    file_names = sorted(meta.uri.split("/")[-1] for meta in pipeline._blob_repository.list_files(handle))
    assert file_names == ["q1_renamed.pdf", "q1_renamed_docling.json"]
    assert pipeline._company_repository.get_company_meta("AAPL") == company_meta
    assert (
        pipeline._source_repository.get_source_meta(
            "AAPL",
            sibling_document_id,
            SourceKind.FILING,
        )
        == sibling_meta
    )
    assert pipeline._blob_repository.list_files(sibling_handle) == sibling_files


@pytest.mark.asyncio
async def test_upload_filing_fresh_create_existing_fails_before_conversion_and_batch(
    tmp_path: Path,
) -> None:
    """SEC fresh recheck 必须让 stale create-existing 在 conversion 前 typed fail。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: stale action 被消费、converter/batch 被调用或 tree 漂移时抛出。
    """

    calls: list[str] = []
    pipeline, batching, company, source = _tracking_sec_pipeline(
        tmp_path,
        converter_calls=calls,
    )
    filing_file = tmp_path / "filing.pdf"
    filing_file.write_text("published filing", encoding="utf-8")
    stale_create = _validated_sec_filing_request(
        pipeline=pipeline,
        filing_file=filing_file,
        action="create",
        company_name="Apple Inc.",
    )
    published_events = [
        event
        async for event in pipeline.upload_filing_stream(
            _validated_sec_filing_request(
                pipeline=pipeline,
                filing_file=filing_file,
                action=None,
                company_name="Apple Inc.",
            )
        )
    ]
    assert published_events[-1].event_type is UploadFilingEventType.UPLOAD_COMPLETED
    calls.clear()
    batching.begin_tokens.clear()
    batching.commit_tokens.clear()
    batching.rollback_tokens.clear()
    company.stage_tokens.clear()
    source.stage_tokens.clear()
    published_tree = published_tree_sha256(tmp_path, "AAPL")

    with pytest.raises(FinsUploadUsageError) as exc_info:
        _ = [event async for event in pipeline.upload_filing_stream(stale_create)]

    assert exc_info.value.failure.code is FinsUploadUsageCode.CREATE_TARGET_EXISTS
    assert calls == []
    assert batching.begin_tokens == []
    assert company.stage_tokens == []
    assert source.stage_tokens == []
    assert published_tree_sha256(tmp_path, "AAPL") == published_tree


@pytest.mark.parametrize("changed_input", (False, True))
@pytest.mark.asyncio
async def test_upload_filing_auto_after_delete_republishes_active_source(
    tmp_path: Path,
    changed_input: bool,
) -> None:
    """SEC delete 后 equal/changed 完整输入 auto 必须发布 uploaded/update active source。

    Args:
        tmp_path: pytest 临时目录。
        changed_input: logical delete 后是否改变完整输入内容。

    Returns:
        无。

    Raises:
        AssertionError: restore 被 skip 或 source 仍处于 logical deleted 时抛出。
    """

    pipeline = SecPipeline(
        workspace_root=tmp_path,
        processor_registry=build_fins_processor_registry(),
        docling_converter=_FakeDoclingConverter(),
    )
    filing_file = tmp_path / "restore.pdf"
    filing_file.write_text("same filing", encoding="utf-8")
    create_request = _validated_sec_filing_request(
        pipeline=pipeline,
        filing_file=filing_file,
        action=None,
        company_name="Apple Inc.",
    )
    create_events = [event async for event in pipeline.upload_filing_stream(create_request)]
    create_result = create_events[-1].payload["result"]
    assert isinstance(create_result, dict)
    document_id = str(create_result["document_id"])
    delete_events = [
        event
        async for event in pipeline.upload_filing_stream(
            _validated_sec_filing_request(
                pipeline=pipeline,
                filing_file=filing_file,
                action="delete",
                company_name="Apple Inc.",
            )
        )
    ]
    assert delete_events[-1].event_type is UploadFilingEventType.UPLOAD_COMPLETED
    if changed_input:
        filing_file.write_text("changed filing", encoding="utf-8")

    restore_events = [
        event
        async for event in pipeline.upload_filing_stream(
            _validated_sec_filing_request(
                pipeline=pipeline,
                filing_file=filing_file,
                action=None,
                company_name="Apple Inc.",
            )
        )
    ]
    restore_result = restore_events[-1].payload["result"]
    state = pipeline._filing_upload_state_repository.read_filing_upload_state("AAPL", document_id)

    assert isinstance(restore_result, dict)
    assert restore_result["status"] == "ok"
    assert restore_result["filing_action"] == "update"
    assert state.source_meta is not None
    assert state.source_meta["is_deleted"] is False
    assert state.source_meta["deleted_at"] is None


@pytest.mark.parametrize("failure_point", ("company", "source"))
@pytest.mark.asyncio
async def test_upload_filing_stage_failure_rolls_back_one_batch_and_preserves_published_tree(
    tmp_path: Path,
    failure_point: str,
) -> None:
    """SEC company/source stage failure 必须回滚同一 batch 且 published SHA 不变。

    Args:
        tmp_path: 临时目录。
        failure_point: 注入 company 或 source stage failure。

    Returns:
        无。

    Raises:
        AssertionError: batch 计数、token identity 或 published tree 漂移时抛出。
    """

    pipeline, batching, company, source = _tracking_sec_pipeline(tmp_path)
    filing_file = tmp_path / "filing.pdf"
    filing_file.write_text("demo filing", encoding="utf-8")
    request = _validated_sec_filing_request(
        pipeline=pipeline,
        filing_file=filing_file,
        action="create",
        company_name="Apple Inc.",
    )
    company.fail_after_stage = failure_point == "company"
    source.fail_after_stage = failure_point == "source"
    before_tree = published_tree_sha256(tmp_path, "AAPL")

    events = [event async for event in pipeline.upload_filing_stream(request)]

    assert events[-1].event_type is UploadFilingEventType.UPLOAD_FAILED
    assert published_tree_sha256(tmp_path, "AAPL") == before_tree == {}
    assert len(batching.begin_tokens) == 1
    assert batching.commit_tokens == []
    assert batching.rollback_tokens == batching.begin_tokens
    assert company.stage_tokens == batching.begin_tokens
    if failure_point == "source":
        assert source.stage_tokens == batching.begin_tokens
    else:
        assert source.stage_tokens == []


@pytest.mark.asyncio
async def test_upload_filing_fresh_recheck_discards_stale_action_and_company_decision(
    tmp_path: Path,
) -> None:
    """SEC workflow 必须丢弃 preflight 后失效的 action/company decision。

    Args:
        tmp_path: 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: fresh recheck 未成为唯一 prepare/stage authority 时抛出。
    """

    pipeline, batching, company, source = _tracking_sec_pipeline(tmp_path)
    filing_file = tmp_path / "filing.pdf"
    filing_file.write_text("demo filing", encoding="utf-8")
    stale_preflight = _validated_sec_filing_request(
        pipeline=pipeline,
        filing_file=filing_file,
        action=None,
        company_name="Stale Decision Name",
    )
    assert stale_preflight.resolved_action == "create"
    assert stale_preflight.company_meta_decision.disposition == "stage"
    published_request = _validated_sec_filing_request(
        pipeline=pipeline,
        filing_file=filing_file,
        action=None,
        company_name="Published Company Name",
    )
    published_events = [event async for event in pipeline.upload_filing_stream(published_request)]
    assert published_events[-1].event_type is UploadFilingEventType.UPLOAD_COMPLETED
    batching.begin_tokens.clear()
    batching.commit_tokens.clear()
    batching.rollback_tokens.clear()
    company.stage_tokens.clear()
    source.stage_tokens.clear()
    published_tree = published_tree_sha256(tmp_path, "AAPL")

    stale_events = [event async for event in pipeline.upload_filing_stream(stale_preflight)]

    stale_result = stale_events[-1].payload["result"]
    assert isinstance(stale_result, dict)
    assert stale_result["filing_action"] == "update"
    assert stale_result["status"] == "skipped"
    assert stale_result["stored_file_count"] == 0
    assert pipeline._company_repository.get_company_meta("AAPL").company_name == ("Published Company Name")
    assert batching.begin_tokens == []
    assert company.stage_tokens == []
    assert source.stage_tokens == []
    assert published_tree_sha256(tmp_path, "AAPL") == published_tree


@pytest.mark.asyncio
async def test_upload_filing_rollback_failure_logs_primary_and_recovery_evidence(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """SEC rollback failure 必须保留 stage 主因与 recovery evidence 给 operator。

    Args:
        tmp_path: 临时目录。
        caplog: operator log 捕获夹具。

    Returns:
        无。

    Raises:
        AssertionError: 主因被 rollback failure 覆盖或 public reason 泄漏时抛出。
    """

    pipeline, batching, company, _source = _tracking_sec_pipeline(tmp_path)
    filing_file = tmp_path / "filing.pdf"
    filing_file.write_text("demo filing", encoding="utf-8")
    request = _validated_sec_filing_request(
        pipeline=pipeline,
        filing_file=filing_file,
        action="create",
        company_name="Apple Inc.",
    )
    company.fail_after_stage = True
    batching.fail_rollback = True

    with caplog.at_level("ERROR"):
        events = [event async for event in pipeline.upload_filing_stream(request)]

    failed_result = events[-1].payload["result"]
    assert isinstance(failed_result, dict)
    assert failed_result["stored_file_count"] == 0
    assert failed_result["message"] == "上传执行失败，请检查运行日志后重试"
    assert "injected company stage primary failure" not in str(failed_result)
    assert "injected rollback evidence failure" not in str(failed_result)
    assert "injected company stage primary failure" in caplog.text
    assert "injected rollback evidence failure" in caplog.text
    assert batching.commit_tokens == []
    assert batching.rollback_tokens == batching.begin_tokens
    assert published_tree_sha256(tmp_path, "AAPL") == {}


@pytest.mark.parametrize(
    ("error", "expected_status", "expected_code", "operator_marker"),
    (
        (DoclingConversionCancelledError(), "cancelled", None, None),
        (
            DoclingConversionError(
                DoclingConversionFailureKind.CONVERTER_EXECUTION,
                "Docling conversion execution failed",
                7,
            ),
            "failed",
            "docling_converter_execution",
            "Docling conversion failed",
        ),
        (OSError("private storage cause"), "failed", "storage_io", "storage operation failed"),
        (
            RuntimeError("private runtime cause"),
            "failed",
            "unexpected_runtime",
            "runtime operation failed",
        ),
    ),
)
@pytest.mark.asyncio
async def test_upload_filing_observably_classifies_cancelled_docling_storage_and_generic(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    error: Exception,
    expected_status: str,
    expected_code: str | None,
    operator_marker: str | None,
) -> None:
    """SEC filing failure path 必须按 frozen typed priority 分类并保留 operator cause。

    Args:
        tmp_path: 临时目录。
        caplog: operator log 捕获夹具。
        error: converter 注入异常。
        expected_status: pipeline 预期终态。
        expected_code: failed 终态的 closed code；取消时为空。
        operator_marker: 对应 typed catch 的 operator marker；取消时为空。

    Returns:
        无。

    Raises:
        AssertionError: typed failure 落入错误分类或 public/internal cause 边界漂移时抛出。
    """

    pipeline = SecPipeline(
        workspace_root=tmp_path,
        processor_registry=build_fins_processor_registry(),
        docling_converter=_FailingDoclingConverter(error),
    )
    filing_file = tmp_path / "filing.pdf"
    filing_file.write_text("demo filing", encoding="utf-8")
    request = _validated_sec_filing_request(
        pipeline=pipeline,
        filing_file=filing_file,
        action="create",
        company_name="Apple Inc.",
    )

    with caplog.at_level("ERROR"):
        events = [event async for event in pipeline.upload_filing_stream(request)]

    result = events[-1].payload["result"]
    assert isinstance(result, dict)
    assert result["status"] == expected_status
    assert result["stored_file_count"] == 0
    if expected_code is None:
        assert events[-1].event_type is UploadFilingEventType.UPLOAD_COMPLETED
        assert "failure" not in result
        assert operator_marker is None
        assert caplog.text == ""
    else:
        assert events[-1].event_type is UploadFilingEventType.UPLOAD_FAILED
        failure = result["failure"]
        assert isinstance(failure, dict)
        assert failure["code"] == expected_code
        assert operator_marker is not None
        assert operator_marker in caplog.text
        assert str(error) in caplog.text
        assert str(error) not in str(result)


@pytest.mark.parametrize(
    ("commit_error", "expected_kind", "expected_code"),
    (
        (OSError("commit storage failure"), "storage", "storage_io"),
        (RuntimeError("commit runtime failure"), "runtime", "unexpected_runtime"),
    ),
)
@pytest.mark.asyncio
async def test_upload_filing_commit_failure_never_publishes_staged_count(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    commit_error: Exception,
    expected_kind: str,
    expected_code: str,
) -> None:
    """commit 失败时 staged original count 不得成为 terminal stored fact。

    Args:
        tmp_path: pytest 临时目录。
        monkeypatch: commit failure 注入夹具。
        commit_error: ``commit_batch`` 应抛出的异常。
        expected_kind: 既有 failure kind。
        expected_code: 既有 failure code。

    Returns:
        无。

    Raises:
        AssertionError: terminal count、分类或 published tree 漂移时抛出。
    """

    pipeline, batching, _company, _source = _tracking_sec_pipeline(tmp_path)
    filing_file = tmp_path / "filing.pdf"
    filing_file.write_text("demo filing", encoding="utf-8")
    request = _validated_sec_filing_request(
        pipeline=pipeline,
        filing_file=filing_file,
        action="create",
        company_name="Apple Inc.",
    )
    before_tree = published_tree_sha256(tmp_path, "AAPL")

    def fail_commit(batch: BatchToken) -> None:
        """在 storage commit owner 入口注入指定异常。

        Args:
            batch: 当前 publication batch。

        Returns:
            不返回。

        Raises:
            Exception: 始终抛出测试参数提供的 commit 异常。
        """

        del batch
        raise commit_error

    monkeypatch.setattr(batching, "commit_batch", fail_commit)
    events = [event async for event in pipeline.upload_filing_stream(request)]

    result = events[-1].payload["result"]
    assert isinstance(result, dict)
    failure = result["failure"]
    assert isinstance(failure, dict)
    assert events[-1].event_type is UploadFilingEventType.UPLOAD_FAILED
    assert result["stored_file_count"] == 0
    assert failure["kind"] == expected_kind
    assert failure["code"] == expected_code
    assert published_tree_sha256(tmp_path, "AAPL") == before_tree == {}
    assert batching.rollback_tokens == []


@pytest.mark.asyncio
async def test_upload_filing_authoritative_identity_mismatch_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SEC fresh validator identity 漂移必须在 prepare/mutation 前失败关闭。

    Args:
        tmp_path: 临时目录。
        monkeypatch: authoritative validator 输出注入夹具。

    Returns:
        无。

    Raises:
        AssertionError: identity mismatch 未失败关闭或产生 published mutation 时抛出。
    """

    pipeline, batching, _company, _source = _tracking_sec_pipeline(tmp_path)
    filing_file = tmp_path / "filing.pdf"
    filing_file.write_text("demo filing", encoding="utf-8")
    request = _validated_sec_filing_request(
        pipeline=pipeline,
        filing_file=filing_file,
        action="create",
        company_name="Apple Inc.",
    )
    owner_validator = sec_upload_workflow.validate_fins_upload_filing_request

    def mismatched_validator(
        raw_request: FinsUploadFilingRequest,
        *,
        published_state: FilingUploadPublishedState,
    ) -> ValidatedFinsUploadFilingRequest:
        """返回仅 document identity 漂移的 validator 结果。

        Args:
            raw_request: immutable raw filing request。
            published_state: workflow fresh snapshot。

        Returns:
            document ID 被注入漂移的 validated request。

        Raises:
            FinsUploadUsageError: owner validator 拒绝请求时抛出。
        """

        validated = owner_validator(raw_request, published_state=published_state)
        return replace(validated, document_id=f"{validated.document_id}-mismatch")

    monkeypatch.setattr(
        sec_upload_workflow,
        "validate_fins_upload_filing_request",
        mismatched_validator,
    )

    with pytest.raises(RuntimeError, match="filing authoritative identity mismatch"):
        _ = [event async for event in pipeline.upload_filing_stream(request)]

    assert batching.begin_tokens == []
    assert published_tree_sha256(tmp_path, "AAPL") == {}
