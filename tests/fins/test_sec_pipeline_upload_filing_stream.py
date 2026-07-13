"""SecPipeline upload filing stream 测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from dayu.contracts.json_value import JsonValue
from dayu.fins.domain.document_models import CompanyMeta, CompanyMetaInventoryEntry, now_iso8601
from dayu.fins.domain.enums import SourceKind
from dayu.fins.pipelines.sec_pipeline import SecPipeline
from dayu.fins.pipelines.upload_filing_events import UploadFilingEventType
from dayu.fins.pipelines.upload_company_meta import (
    RESOLVER_VERSION,
    _normalize_ticker_aliases,
    upsert_company_meta_for_upload,
)
from dayu.fins.processors.registry import build_fins_processor_registry


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

    def upsert_company_meta(self, meta: CompanyMeta) -> None:
        """记录一次 company meta 写入。

        Args:
            meta: 待写入公司元数据。

        Returns:
            无。

        Raises:
            无。
        """

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


def _convert_docling_stub(raw_data: bytes, stream_name: str) -> dict[str, JsonValue]:
    """返回固定 Docling 转换结果。

    Args:
        raw_data: 输入原始字节。
        stream_name: 输入流名称。

    Returns:
        固定结构化结果。

    Raises:
        无。
    """

    del raw_data
    return {"name": stream_name, "format": "docling"}


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

    pipeline._company_repository.upsert_company_meta(
        CompanyMeta(
            company_id="AAPL_US",
            company_name=company_name,
            ticker="AAPL",
            market="US",
            resolver_version=resolver_version,
            updated_at=now_iso8601(),
            ticker_aliases=ticker_aliases,
        )
    )


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

    assert _normalize_ticker_aliases(
        canonical_ticker=canonical_ticker,
        ticker_aliases=raw_aliases,
    ) == expected


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

    pipeline = SecPipeline(
        workspace_root=tmp_path,
        processor_registry=build_fins_processor_registry(),
    )
    pipeline._upload_service._convert_with_docling = _convert_docling_stub
    filing_file = tmp_path / "filing.pdf"
    filing_file.write_text("demo filing", encoding="utf-8")

    events = [
        event
        async for event in pipeline.upload_filing_stream(
            ticker="AAPL",
            action="create",
            files=[filing_file],
            fiscal_year=2025,
            fiscal_period="Q1",
            amended=False,
            filing_date="2025-05-01",
            report_date="2025-03-31",
            company_name="Apple Inc.",
            ticker_aliases=["AAPL", "APC"],
            overwrite=False,
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
    )
    pipeline._upload_service._convert_with_docling = _convert_docling_stub
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
            ticker="AAPL",
            action="create",
            files=[filing_file],
            fiscal_year=2025,
            fiscal_period="Q1",
            company_name="Ignored Apple",
            ticker_aliases=["AAPL", "NEW"],
            overwrite=False,
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
    )
    pipeline._upload_service._convert_with_docling = _convert_docling_stub
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
            ticker="AAPL",
            action="create",
            files=[filing_file],
            fiscal_year=2025,
            fiscal_period="Q1",
            company_name="Apple Refreshed",
            ticker_aliases=["AAPL", "APC"],
            overwrite=False,
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
    )
    pipeline._upload_service._convert_with_docling = _convert_docling_stub
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
            ticker="AAPL",
            action="create",
            files=[filing_file],
            fiscal_year=2025,
            fiscal_period="Q1",
            company_name=None,
            overwrite=False,
        )
    ]

    assert [event.event_type for event in events] == [
        UploadFilingEventType.UPLOAD_STARTED,
        UploadFilingEventType.UPLOAD_FAILED,
    ]
    failed_result = events[-1].payload["result"]
    assert isinstance(failed_result, dict)
    assert failed_result["status"] == "failed"
    assert "--company-name" in str(failed_result["message"])
    company_meta = pipeline._company_repository.get_company_meta("AAPL")
    assert company_meta.company_name == "Stale Apple"
    assert company_meta.resolver_version == "market_resolver_v0.9.0"


@pytest.mark.asyncio
async def test_upload_filing_stream_auto_action_and_overwrite_reset(tmp_path: Path) -> None:
    """SEC filing upload stream 应自动解析动作并在 overwrite 时重置单文档。

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
    )
    pipeline._upload_service._convert_with_docling = _convert_docling_stub
    old_file = tmp_path / "q1_old.pdf"
    new_file = tmp_path / "q1_new.pdf"
    old_file.write_text("old filing", encoding="utf-8")
    new_file.write_text("new filing", encoding="utf-8")

    create_events = [
        event
        async for event in pipeline.upload_filing_stream(
            ticker="AAPL",
            action=None,
            files=[old_file],
            fiscal_year=2025,
            fiscal_period="Q1",
            company_name="Apple Inc.",
            overwrite=False,
        )
    ]
    create_result = create_events[-1].payload["result"]
    assert isinstance(create_result, dict)
    assert create_result["filing_action"] == "create"

    skip_events = [
        event
        async for event in pipeline.upload_filing_stream(
            ticker="AAPL",
            action=None,
            files=[old_file],
            fiscal_year=2025,
            fiscal_period="Q1",
            company_name="Apple Inc.",
            overwrite=False,
        )
    ]
    skip_result = skip_events[-1].payload["result"]
    assert isinstance(skip_result, dict)
    assert skip_result["status"] == "skipped"
    assert skip_result["filing_action"] == "update"

    overwrite_events = [
        event
        async for event in pipeline.upload_filing_stream(
            ticker="AAPL",
            action=None,
            files=[new_file],
            fiscal_year=2025,
            fiscal_period="Q1",
            company_name="Apple Inc.",
            overwrite=True,
        )
    ]
    overwrite_result = overwrite_events[-1].payload["result"]
    assert isinstance(overwrite_result, dict)
    assert overwrite_result["status"] == "ok"
    assert overwrite_result["filing_action"] == "update"
    assert overwrite_result["document_id"] == create_result["document_id"]

    handle = pipeline._source_repository.get_source_handle(
        "AAPL",
        str(overwrite_result["document_id"]),
        SourceKind.FILING,
    )
    file_names = sorted(meta.uri.split("/")[-1] for meta in pipeline._blob_repository.list_files(handle))
    assert file_names == ["q1_new.pdf", "q1_new_docling.json"]
