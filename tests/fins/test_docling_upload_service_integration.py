"""DoclingUploadService 真实 Docling 集成测试。"""

from __future__ import annotations

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
from dayu.fins.upload_format_contract import FinsUploadMaterialFiles

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
        selection=FinsUploadMaterialFiles.from_upsert_paths((sample_file,)),
        overwrite=False,
        previous_meta=None,
        meta={"material_name": "Docling Fixture", "ingest_method": "upload"},
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
    assert result.payload["primary_document"] == "minimal_docling.json"
