"""SecPipeline upload material stream 测试。"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from dayu.contracts.cancellation import CancellationToken
from dayu.fins.domain.enums import SourceKind
from dayu.fins.pipelines.sec_pipeline import SecPipeline
from dayu.fins.pipelines.docling_process_converter import (
    DoclingConversionConfig,
    DoclingConversionResult,
)
from dayu.fins.pipelines.upload_material_events import UploadMaterialEventType
from dayu.fins.processors.registry import build_fins_processor_registry


class _FakeDoclingConverter:
    """SEC material 测试用 typed converter。"""

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
        data = ('{"name": "' + stream_name + '", "format": "docling"}').encode()
        return DoclingConversionResult(data, len(data), hashlib.sha256(data).hexdigest())


@pytest.mark.asyncio
async def test_upload_material_stream_uploads_docling_files(tmp_path: Path) -> None:
    """SEC material upload stream 应完成上传并生成 Docling 主文件。

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
    material_file = tmp_path / "material.pdf"
    material_file.write_text("demo material", encoding="utf-8")

    events = [
        event
        async for event in pipeline.upload_material_stream(
            ticker="AAPL",
            action="create",
            form_type="MATERIAL_OTHER",
            material_name="Deck",
            files=[material_file],
            filing_date="2025-05-01",
            report_date="2025-03-31",
            company_name="Apple Inc.",
            ticker_aliases=["AAPL", "APC", "V.BA"],
            overwrite=False,
        )
    ]

    assert [event.event_type for event in events] == [
        UploadMaterialEventType.UPLOAD_STARTED,
        UploadMaterialEventType.CONVERSION_STARTED,
        UploadMaterialEventType.FILE_UPLOADED,
        UploadMaterialEventType.FILE_UPLOADED,
        UploadMaterialEventType.UPLOAD_COMPLETED,
    ]
    result_value = events[-1].payload["result"]
    assert isinstance(result_value, dict)
    assert result_value["action"] == "upload_material"
    assert result_value["ticker"] == "AAPL"
    assert result_value["status"] == "ok"
    assert result_value["stored_file_count"] == 1
    assert str(result_value["document_id"]).startswith("mat_")
    company_meta = pipeline._company_repository.get_company_meta("AAPL")
    assert company_meta.company_id == "AAPL_US"
    assert company_meta.company_name == "Apple Inc."
    assert company_meta.ticker_identity.accepted_aliases == ("APC", "V-BA")
    assert pipeline._company_repository.resolve_existing_ticker(["APC"]) == "AAPL"
    assert pipeline._company_repository.resolve_existing_ticker(["V.BA"]) == "AAPL"
    meta = pipeline._source_repository.get_source_meta(
        "AAPL",
        str(result_value["document_id"]),
        SourceKind.MATERIAL,
    )
    assert str(meta["primary_document"]).endswith("_docling.json")


@pytest.mark.asyncio
async def test_upload_material_stream_auto_action_and_overwrite_reset(tmp_path: Path) -> None:
    """SEC material upload stream 应自动解析动作并在 overwrite 时重置单文档。

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
    old_file = tmp_path / "deck_old.pdf"
    new_file = tmp_path / "deck_new.pdf"
    old_file.write_text("old material", encoding="utf-8")
    new_file.write_text("new material", encoding="utf-8")

    create_events = [
        event
        async for event in pipeline.upload_material_stream(
            ticker="AAPL",
            action=None,
            form_type="MATERIAL_OTHER",
            material_name="Deck",
            files=[old_file],
            company_name="Apple Inc.",
            ticker_aliases=["OLD"],
            overwrite=False,
        )
    ]
    create_result = create_events[-1].payload["result"]
    assert isinstance(create_result, dict)
    assert create_result["material_action"] == "create"

    overwrite_events = [
        event
        async for event in pipeline.upload_material_stream(
            ticker="AAPL",
            action=None,
            form_type="MATERIAL_OTHER",
            material_name="Deck",
            files=[new_file],
            company_name="Ignored Apple Name",
            ticker_aliases=["NEW"],
            overwrite=True,
        )
    ]
    overwrite_result = overwrite_events[-1].payload["result"]
    assert isinstance(overwrite_result, dict)
    assert overwrite_result["status"] == "ok"
    assert overwrite_result["stored_file_count"] == 1
    assert overwrite_result["material_action"] == "update"
    assert overwrite_result["document_id"] == create_result["document_id"]

    company_meta = pipeline._company_repository.get_company_meta("AAPL")
    assert company_meta.company_name == "Apple Inc."
    assert company_meta.ticker_identity.accepted_aliases == ("OLD", "NEW")

    handle = pipeline._source_repository.get_source_handle(
        "AAPL",
        str(overwrite_result["document_id"]),
        SourceKind.MATERIAL,
    )
    file_names = sorted(meta.uri.split("/")[-1] for meta in pipeline._blob_repository.list_files(handle))
    assert file_names == ["deck_new.pdf", "deck_new_docling.json"]


@pytest.mark.asyncio
async def test_upload_material_failure_preserves_existing_user_visible_semantics(tmp_path: Path) -> None:
    """Filing typed failure 收束不得改变 SEC material 的既有错误文案 contract。

    Args:
        tmp_path: 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: material 被改为 filing typed failure projection 时抛出。
    """

    pipeline = SecPipeline(
        workspace_root=tmp_path,
        processor_registry=build_fins_processor_registry(),
        docling_converter=_FakeDoclingConverter(),
    )
    material_file = tmp_path / "material.pdf"
    material_file.write_text("demo material", encoding="utf-8")

    events = [
        event
        async for event in pipeline.upload_material_stream(
            ticker="AAPL",
            action="create",
            form_type="MATERIAL_OTHER",
            material_name="Deck",
            files=[material_file],
            company_name=None,
            overwrite=False,
        )
    ]

    result = events[-1].payload["result"]
    assert isinstance(result, dict)
    assert result["status"] == "failed"
    assert result["stored_file_count"] == 0
    assert result["message"] == "create/update 时必须提供 --company-name"
    assert "failure" not in result
    assert events[-1].payload["error"] == "create/update 时必须提供 --company-name"
