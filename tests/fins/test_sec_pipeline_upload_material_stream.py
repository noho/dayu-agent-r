"""SecPipeline upload material stream 测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from dayu.contracts.json_value import JsonValue
from dayu.fins.domain.enums import SourceKind
from dayu.fins.pipelines.sec_pipeline import SecPipeline
from dayu.fins.pipelines.upload_material_events import UploadMaterialEventType
from dayu.fins.processors.registry import build_fins_processor_registry


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
    )
    pipeline._upload_service._convert_with_docling = _convert_docling_stub
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
            ticker_aliases=["AAPL", "APC"],
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
    assert str(result_value["document_id"]).startswith("mat_")
    company_meta = pipeline._company_repository.get_company_meta("AAPL")
    assert company_meta.company_id == "AAPL_US"
    assert company_meta.company_name == "Apple Inc."
    assert company_meta.ticker_aliases == ["AAPL", "APC"]
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
    )
    pipeline._upload_service._convert_with_docling = _convert_docling_stub
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
            company_name="Apple Inc.",
            overwrite=True,
        )
    ]
    overwrite_result = overwrite_events[-1].payload["result"]
    assert isinstance(overwrite_result, dict)
    assert overwrite_result["status"] == "ok"
    assert overwrite_result["material_action"] == "update"
    assert overwrite_result["document_id"] == create_result["document_id"]

    handle = pipeline._source_repository.get_source_handle(
        "AAPL",
        str(overwrite_result["document_id"]),
        SourceKind.MATERIAL,
    )
    file_names = sorted(meta.uri.split("/")[-1] for meta in pipeline._blob_repository.list_files(handle))
    assert file_names == ["deck_new.pdf", "deck_new_docling.json"]
