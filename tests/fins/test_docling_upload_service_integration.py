"""DoclingUploadService 真实 Docling 集成测试。"""

from __future__ import annotations

from dayu.fins.upload_asset_plan import plan_upload_assets

from dataclasses import replace
from dayu.fins.ingestion_runtime import FinsUploadMaterialRequest
from dayu.fins.pipelines.sec_pipeline import SecPipeline
from dayu.fins.pipelines.docling_upload_service import build_material_ids
from dayu.fins.processors.registry import build_fins_processor_registry

import os
from pathlib import Path

import pytest

from dayu.fins.domain.enums import SourceKind
from dayu.fins.pipelines.docling_upload_service import (
    DoclingUploadService,
    UploadOperationResult,
    commit_prepared_upload_batch,
)
from dayu.fins.pipelines.docling_process_converter import ProcessDoclingConverter
from dayu.fins.storage import FsBatchingRepository, FsDocumentBlobRepository, FsSourceDocumentRepository
from dayu.fins.storage._fs_repository_factory import build_fs_repository_set
from dayu.fins.upload_repair_contract import NoExistingSourceRepair

_RUN_DOCLING_UPLOAD_INTEGRATION = "DAYU_RUN_DOCLING_UPLOAD_INTEGRATION"
_MINIMAL_PDF = (
    b"%PDF-1.4\n"
    b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Count 1/Kids[3 0 R]>>endobj\n"
    b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]>>endobj\n"
    b"trailer<</Root 1 0 R>>\n%%EOF\n"
)


@pytest.mark.asyncio
async def test_real_docling_upload_service_conversion_when_enabled(tmp_path: Path) -> None:
    """显式启用时用真实 Docling conversion 跑完整上传。

    Args:
        tmp_path: 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    if os.environ.get(_RUN_DOCLING_UPLOAD_INTEGRATION) != "1":
        pytest.skip(f"设置 {_RUN_DOCLING_UPLOAD_INTEGRATION}=1 后运行真实 Docling upload 集成测试")
    pytest.importorskip("docling")

    repository_set = build_fs_repository_set(workspace_root=tmp_path)
    batching_repository = FsBatchingRepository(tmp_path, repository_set=repository_set)
    source_repository = FsSourceDocumentRepository(tmp_path, repository_set=repository_set)
    blob_repository = FsDocumentBlobRepository(tmp_path, repository_set=repository_set)
    service = DoclingUploadService(
        source_repository=source_repository,
        blob_repository=blob_repository,
        docling_converter=ProcessDoclingConverter(),
    )
    sample_file = tmp_path / "minimal.pdf"
    sample_file.write_bytes(_MINIMAL_PDF)

    prepared = await service.prepare_upload(
        ticker="AAPL",
        source_kind=SourceKind.MATERIAL,
        action="create",
        document_id="mat_docling_integration",
        internal_document_id="mat_docling_integration",
        form_type="MATERIAL_OTHER",
        selection=plan_upload_assets(material_primary_selectors=(), source_kind=SourceKind.MATERIAL, operation="upsert", files=(sample_file,))[1],
        overwrite=False,
        previous_meta=None,
        meta={"material_name": "Docling Fixture", "ingest_method": "upload"},
        repair_disposition=NoExistingSourceRepair(),
        cancellation=None,
    )
    assert not isinstance(prepared, UploadOperationResult)
    result = commit_prepared_upload_batch(
        service=service,
        batching_repository=batching_repository,
        batch=batching_repository.begin_batch("AAPL"),
        prepared=prepared,
        cancellation=None,
    )

    assert result.status == "uploaded"
    assert result.payload["primary_document"] == "minimal.pdf_docling.json"


@pytest.mark.asyncio
async def test_real_text_conversion_role_versions_and_default_processor(tmp_path: Path) -> None:
    """参数：真实隔离根；返回：无；异常：转换或断言失败；离线文本经真实子进程转换、仓储及 processor factory 验证 A→B→B。"""
    registry = build_fins_processor_registry()
    pipeline = SecPipeline(workspace_root=tmp_path, processor_registry=registry, docling_converter=ProcessDoclingConverter())
    a, b = tmp_path / "a.txt", tmp_path / "b.txt"
    a.write_text("Alpha source contents", encoding="utf-8")
    b.write_text("Bravo source contents", encoding="utf-8")
    raw = FinsUploadMaterialRequest(ticker="AAPL", form_type="MATERIAL_OTHER", material_name="Real Text",
                                    files=(a, b), primary_selectors=(a,), company_name="Apple Inc.")
    identity = build_material_ids(form_type=raw.form_type, material_name=raw.material_name, fiscal_year=None, fiscal_period=None, document_id=None)
    source = FsSourceDocumentRepository(tmp_path)
    for request, expected_status, primary, version in (
        (raw, "ok", "a.txt_docling.json", "v1"),
        (replace(raw, primary_selectors=(b,)), "ok", "b.txt_docling.json", "v2"),
        (replace(raw, files=(b, a), primary_selectors=(b,)), "skipped", "b.txt_docling.json", "v2"),
    ):
        events = [event async for event in pipeline.upload_material_stream(request)]
        result = events[-1].payload["result"]
        assert isinstance(result, dict)
        assert result["status"] == expected_status, result
        assert result["document_id"] == identity.document_id
        assert result["internal_document_id"] == identity.internal_document_id
        meta = source.get_source_meta("AAPL", identity.document_id, SourceKind.MATERIAL)
        assert meta["document_version"] == version
        assert meta["primary_document"] == primary
        with source.read_source_snapshot("AAPL", identity.document_id, SourceKind.MATERIAL, materialize_files=True) as snapshot:
            assert snapshot.primary_filename == primary
            processor = registry.create_with_fallback(source=snapshot.get_primary_source(), form_type="MATERIAL_OTHER", media_type="application/json")
            text = processor.get_full_text()
            assert ("Alpha source contents" if primary.startswith("a.") else "Bravo source contents") in text
