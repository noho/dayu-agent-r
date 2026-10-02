"""材料 manifest 严格主源投影与真实 Fs 发布/内容失败链回归。"""
from __future__ import annotations

from dayu.fins.storage import FsBatchingRepository, FsCompanyMetaRepository, FsSourceDocumentRepository, FsDocumentBlobRepository, FsFilingMaintenanceRepository, FsFilingUploadStateRepository, FsProcessedDocumentRepository
from dayu.fins.storage._fs_repository_factory import build_fs_repository_set

from dayu.fins.storage import FsMaterialUploadStateRepository

from docling_core.types.doc.document import DoclingDocument
from docling_core.types.doc.labels import DocItemLabel

import json

import hashlib
from dataclasses import replace
from pathlib import Path

import pytest

from dayu.contracts.cancellation import CancellationToken
from dayu.contracts.json_value import JsonValue
from dayu.fins.domain.enums import SourceKind
from dayu.fins.ingestion_runtime import FinsUploadMaterialRequest
from dayu.fins.pipelines.docling_process_converter import DoclingConversionConfig, DoclingConversionResult, DoclingConversionError, DoclingConversionFailureKind
from dayu.fins.pipelines.sec_pipeline import SecPipeline
from dayu.fins.pipelines.docling_upload_service import build_material_ids
from dayu.fins.processors.registry import build_fins_processor_registry
from dayu.fins.storage import FsSourceDocumentRepository, FsBatchingRepository, FsCompanyMetaRepository
from dayu.fins.storage._fs_repository_factory import build_fs_repository_set
from dayu.fins.storage.source_manifest_contract import project_filing_manifest_item, project_material_manifest_item
from dayu.fins.storage.source_meta_contract import require_material_source_meta_primary_document
from dayu.fins.storage._fs_source_integrity import validate_material_source_primary
from dayu.fins.upload_failure import FinsUploadFailureError, fins_upload_failure_from_exception, fins_upload_empty_input_failure
from dayu.fins.direct_events import canonicalize_fins_public_file_label


class _Converter:
    """只控制转换 outcome；发布、仓储、manifest 与 snapshot 使用生产实现。"""

    def __init__(self, failing_name: str | None = None) -> None:
        """参数：可选失败文件名；返回：无；异常：无。"""
        self.calls: list[str] = []
        self.failing_name = failing_name

    async def convert_to_json_bytes(self, input_bytes: bytes, stream_name: str, *, config: DoclingConversionConfig, cancellation: CancellationToken | None) -> DoclingConversionResult:
        """参数：真实原字节/文件名/配置/取消；返回：受控结果；异常：指定文件抛 typed 失败。"""
        self.calls.append(stream_name)
        if stream_name == self.failing_name:
            raise DoclingConversionError(DoclingConversionFailureKind.CONVERTER_EXECUTION, "Docling conversion execution failed", 1)
        document = DoclingDocument(name=stream_name)
        document.add_text(label=DocItemLabel.TEXT, text=input_bytes.decode("utf-8"))
        data = document.model_dump_json().encode("utf-8")
        return DoclingConversionResult(data, len(data), hashlib.sha256(data).hexdigest())


@pytest.mark.parametrize("value", (None, 0, True, "", "  "))
def test_strict_primary(value: JsonValue) -> None:
    """参数：非法主源值；返回：无；异常：断言失败；strict reader 无默认或宽松转换。"""
    with pytest.raises(ValueError):
        require_material_source_meta_primary_document({"primary_document": value})
    with pytest.raises(KeyError):
        require_material_source_meta_primary_document({})


def test_typed_failure_preserves_object_and_label() -> None:
    """参数：无；返回：无；异常：断言失败；resolver 不覆盖已拥有的当前安全标签。"""
    for name in ("empty.txt", "x" * 230 + ".txt", "control\n.txt"):
        reason = fins_upload_empty_input_failure(canonicalize_fins_public_file_label(name))
        error = FinsUploadFailureError(reason)
        assert fins_upload_failure_from_exception(error, file_label=None) is reason


@pytest.mark.asyncio
async def test_role_publish_a_b_b_and_snapshot(tmp_path: Path) -> None:
    """参数：真实隔离仓储根；返回：无；异常：断言失败；稳定身份 v1/v2/v2、全部转换与新旧 snapshot 主源一致。"""
    converter = _Converter()
    pipeline = SecPipeline(workspace_root=tmp_path, processor_registry=build_fins_processor_registry(), docling_converter=converter,  material_upload_state_repository=FsMaterialUploadStateRepository(tmp_path, repository_set=(_material_test_repository_set := build_fs_repository_set(workspace_root=tmp_path, create_directories=False))), batching_repository=FsBatchingRepository(tmp_path, repository_set=_material_test_repository_set), company_repository=FsCompanyMetaRepository(tmp_path, repository_set=_material_test_repository_set), source_repository=FsSourceDocumentRepository(tmp_path, repository_set=_material_test_repository_set), blob_repository=FsDocumentBlobRepository(tmp_path, repository_set=_material_test_repository_set), filing_maintenance_repository=FsFilingMaintenanceRepository(tmp_path, repository_set=_material_test_repository_set), filing_upload_state_repository=FsFilingUploadStateRepository(tmp_path, repository_set=_material_test_repository_set), processed_repository=FsProcessedDocumentRepository(tmp_path, repository_set=_material_test_repository_set),)
    repository = FsSourceDocumentRepository(tmp_path)
    a, b = tmp_path / "a.txt", tmp_path / "b.md"
    a.write_bytes(b"original a"); b.write_bytes(b"original b")
    raw = FinsUploadMaterialRequest(ticker="AAPL", files=(a, b), primary_selectors=(a,), form_type=" other ", material_name=" Deck ", company_name="Apple Inc.")
    identity = build_material_ids(form_type=raw.form_type, material_name=raw.material_name, fiscal_year=None, fiscal_period=None, document_id=None)
    await _upload(pipeline, raw)
    old = repository.read_source_snapshot("AAPL", identity.document_id, SourceKind.MATERIAL, materialize_files=True)
    try:
        assert old.primary_filename == "a.txt_docling.json"
        for request, primary, version, expected_calls in ((replace(raw, primary_selectors=(b,)), "b.md_docling.json", "v2", 4), (replace(raw, files=(b, a), primary_selectors=(b,)), "b.md_docling.json", "v2", 4)):
            await _upload(pipeline, request)
            meta = repository.get_source_meta("AAPL", identity.document_id, SourceKind.MATERIAL)
            assert meta["document_version"] == version
            assert meta["document_id"] == identity.document_id
            assert meta["internal_document_id"] == identity.internal_document_id
            assert meta["primary_document"] == primary
            assert project_material_manifest_item(meta).primary_document == primary
            primary_file = repository.get_primary_file("AAPL", identity.document_id, SourceKind.MATERIAL)
            declared = meta["files"]
            assert isinstance(declared, list)
            assert primary_file.sha256 == next(item["sha256"] for item in declared if isinstance(item, dict) and item["name"] == primary)
            with repository.read_source_snapshot("AAPL", identity.document_id, SourceKind.MATERIAL, materialize_files=True) as snapshot:
                assert snapshot.primary_filename == primary
                with snapshot.get_primary_source().open() as stream:
                    assert b"b.md" in stream.read()
                processor = build_fins_processor_registry().create_with_fallback(
                    source=snapshot.get_primary_source(), form_type="OTHER",
                    media_type=snapshot.get_primary_source().media_type)
                assert "original b" in processor.get_full_text()
                assert "original a" not in processor.get_full_text()
            assert len(converter.calls) == expected_calls
        assert old.primary_filename == "a.txt_docling.json"
        with old.get_primary_source().open() as stream:
            assert b"a.txt" in stream.read()
    finally:
        old.close()


async def _upload(pipeline: SecPipeline, request: FinsUploadMaterialRequest) -> None:
    """参数：生产 pipeline 与请求；返回：无；异常：断言失败；真实流必须成功才作为发布证据。"""
    events = [event async for event in pipeline.upload_material_stream(request)]
    result = events[-1].payload["result"]
    assert isinstance(result, dict)
    assert result["status"] in ("ok", "skipped")


@pytest.mark.asyncio
@pytest.mark.parametrize("empty_position", (0, 1, 2))
async def test_empty_original_before_any_conversion(tmp_path: Path, empty_position: int) -> None:
    """参数：真实根与单空/空前/空后位置；返回：无；异常：断言失败；零转换/零材料发布，合法公司保持。"""
    converter = _Converter()
    pipeline = SecPipeline(workspace_root=tmp_path, processor_registry=build_fins_processor_registry(), docling_converter=converter,  material_upload_state_repository=FsMaterialUploadStateRepository(tmp_path, repository_set=(_material_test_repository_set := build_fs_repository_set(workspace_root=tmp_path, create_directories=False))), batching_repository=FsBatchingRepository(tmp_path, repository_set=_material_test_repository_set), company_repository=FsCompanyMetaRepository(tmp_path, repository_set=_material_test_repository_set), source_repository=FsSourceDocumentRepository(tmp_path, repository_set=_material_test_repository_set), blob_repository=FsDocumentBlobRepository(tmp_path, repository_set=_material_test_repository_set), filing_maintenance_repository=FsFilingMaintenanceRepository(tmp_path, repository_set=_material_test_repository_set), filing_upload_state_repository=FsFilingUploadStateRepository(tmp_path, repository_set=_material_test_repository_set), processed_repository=FsProcessedDocumentRepository(tmp_path, repository_set=_material_test_repository_set),)
    empty, valid = tmp_path / "empty.txt", tmp_path / "valid.txt"
    empty.write_bytes(b""); valid.write_bytes(b"valid")
    paths = (empty,) if empty_position == 0 else (empty, valid) if empty_position == 1 else (valid, empty)
    raw = FinsUploadMaterialRequest(ticker="AAPL", files=paths, primary_selectors=(empty,), form_type="OTHER", material_name="Deck", company_name="Apple Inc.")
    events = [event async for event in pipeline.upload_material_stream(raw)]
    result = events[-1].payload["result"]
    assert isinstance(result, dict)
    assert result["status"] == "failed" and result["stored_file_count"] == 0
    assert result["failure"] == fins_upload_empty_input_failure("empty.txt").to_json()
    assert converter.calls == []
    assert FsCompanyMetaRepository(tmp_path).get_company_meta("AAPL").company_name == "Apple Inc."
    assert FsSourceDocumentRepository(tmp_path).list_source_document_ids("AAPL", SourceKind.MATERIAL) == []


@pytest.mark.parametrize("role", (None, "original", "docling"))
def test_exact_declared_docling_member(tmp_path: Path, role: str | None) -> None:
    """参数：真实声明目录及角色；返回：无；异常：断言失败；不能仅字符串 primary 相等就接受原件。"""
    meta: dict[str, JsonValue] = {"amended": False, "primary_document": "a.json", "files": [{"name": "a.json", "uri": "local://a.json", "source": role}]}
    if role == "docling":
        validate_material_source_primary(source_meta=meta, source_directory=tmp_path)
    else:
        with pytest.raises(ValueError):
            validate_material_source_primary(source_meta=meta, source_directory=tmp_path)


@pytest.mark.asyncio
async def test_material_replace_and_public_primary_are_strict(tmp_path: Path) -> None:
    """参数：真实新库；返回：无；异常：断言失败；strict 主源拒绝原件/缺字段/类型，replace 零发布，public primary 不 strip 或猜文件。"""
    repository_set = build_fs_repository_set(workspace_root=tmp_path, create_directories=False)
    pipeline = SecPipeline(workspace_root=tmp_path, processor_registry=build_fins_processor_registry(), docling_converter=_Converter(),  material_upload_state_repository=FsMaterialUploadStateRepository(tmp_path, repository_set=repository_set), batching_repository=FsBatchingRepository(tmp_path, repository_set=repository_set), company_repository=FsCompanyMetaRepository(tmp_path, repository_set=repository_set), source_repository=FsSourceDocumentRepository(tmp_path, repository_set=repository_set), blob_repository=FsDocumentBlobRepository(tmp_path, repository_set=repository_set), filing_maintenance_repository=FsFilingMaintenanceRepository(tmp_path, repository_set=repository_set), filing_upload_state_repository=FsFilingUploadStateRepository(tmp_path, repository_set=repository_set), processed_repository=FsProcessedDocumentRepository(tmp_path, repository_set=repository_set),)
    path = tmp_path / "source.txt"
    path.write_bytes(b"source")
    raw = FinsUploadMaterialRequest(ticker="AAPL", files=(path,), form_type="OTHER", material_name="Strict", company_name="Apple Inc.")
    await _upload(pipeline, raw)
    identity = build_material_ids(form_type="OTHER", material_name="Strict", fiscal_year=None, fiscal_period=None, document_id=None)
    repository_set = build_fs_repository_set(workspace_root=tmp_path)
    repository = FsSourceDocumentRepository(tmp_path, repository_set=repository_set)
    batching = FsBatchingRepository(tmp_path, repository_set=repository_set)
    good = repository.get_source_meta("AAPL", identity.document_id, SourceKind.MATERIAL)
    for primary in (None, True, "", "source.txt", " source.txt_docling.json ", "absent.json"):
        bad = dict(good)
        bad["primary_document"] = primary
        batch = batching.begin_batch("AAPL")
        try:
            with pytest.raises(ValueError):
                repository.replace_source_meta("AAPL", identity.document_id, SourceKind.MATERIAL, bad, batch=batch)
        finally:
            batching.rollback_batch(batch)
        assert repository.get_source_meta("AAPL", identity.document_id, SourceKind.MATERIAL) == good
    locator = repository.get_source_document_locator("AAPL", identity.document_id, SourceKind.MATERIAL)
    meta_path = tmp_path / locator / "meta.json"
    handle = repository.get_source_handle("AAPL", identity.document_id, SourceKind.MATERIAL)
    assert repository.get_primary_file("AAPL", identity.document_id, SourceKind.MATERIAL).sha256 is not None
    try:
        for primary in (None, True, "source.txt", " source.txt_docling.json "):
            bad = dict(good)
            bad["primary_document"] = primary
            meta_path.write_text(json.dumps(bad), encoding="utf-8")
            with pytest.raises(ValueError):
                repository.get_primary_file("AAPL", identity.document_id, SourceKind.MATERIAL)
        bad = dict(good)
        del bad["primary_document"]
        meta_path.write_text(json.dumps(bad), encoding="utf-8")
        with pytest.raises(KeyError):
            repository.get_primary_file("AAPL", identity.document_id, SourceKind.MATERIAL)
    finally:
        meta_path.write_text(json.dumps(good), encoding="utf-8")


@pytest.mark.asyncio
@pytest.mark.parametrize("failed_first", (True, False))
async def test_material_corrupt_original_in_each_position_has_no_partial_publication(tmp_path: Path, failed_first: bool) -> None:
    """参数：真实根与损坏位置；返回：无；异常：断言失败；真实多原件当前标签/五字段同源，先前内存转换不形成发布。"""
    good, corrupt = tmp_path / "good.pdf", tmp_path / "corrupt.docx"
    good.write_bytes(b"controlled valid contents")
    corrupt.write_bytes(b"corrupt document")
    converter = _Converter(failing_name=corrupt.name)
    pipeline = SecPipeline(workspace_root=tmp_path, processor_registry=build_fins_processor_registry(), docling_converter=converter,  material_upload_state_repository=FsMaterialUploadStateRepository(tmp_path, repository_set=(_material_test_repository_set := build_fs_repository_set(workspace_root=tmp_path, create_directories=False))), batching_repository=FsBatchingRepository(tmp_path, repository_set=_material_test_repository_set), company_repository=FsCompanyMetaRepository(tmp_path, repository_set=_material_test_repository_set), source_repository=FsSourceDocumentRepository(tmp_path, repository_set=_material_test_repository_set), blob_repository=FsDocumentBlobRepository(tmp_path, repository_set=_material_test_repository_set), filing_maintenance_repository=FsFilingMaintenanceRepository(tmp_path, repository_set=_material_test_repository_set), filing_upload_state_repository=FsFilingUploadStateRepository(tmp_path, repository_set=_material_test_repository_set), processed_repository=FsProcessedDocumentRepository(tmp_path, repository_set=_material_test_repository_set),)
    files = (corrupt, good) if failed_first else (good, corrupt)
    request = FinsUploadMaterialRequest(ticker="AAPL", files=files, primary_selectors=(good,),
        form_type="OTHER", material_name="Failure Position", company_name="Apple Inc.")
    events = [event async for event in pipeline.upload_material_stream(request)]
    result = events[-1].payload["result"]
    assert isinstance(result, dict)
    assert result["status"] == "failed" and result["stored_file_count"] == 0
    error = DoclingConversionError(DoclingConversionFailureKind.CONVERTER_EXECUTION, "Docling conversion execution failed", 1)
    expected = fins_upload_failure_from_exception(error, file_label=canonicalize_fins_public_file_label(corrupt.name))
    assert result["failure"] == expected.to_json()
    assert converter.calls == ([corrupt.name] if failed_first else [good.name, corrupt.name])
    assert FsSourceDocumentRepository(tmp_path).list_source_document_ids("AAPL", SourceKind.MATERIAL) == []
    assert FsCompanyMetaRepository(tmp_path).get_company_meta("AAPL").company_name == "Apple Inc."


@pytest.mark.parametrize("source_kind", (SourceKind.FILING, SourceKind.MATERIAL))
@pytest.mark.parametrize("deleted", (False, True))
def test_manifest_deletion_uses_strict_storage_fact(source_kind: SourceKind, deleted: bool) -> None:
    """参数：来源类别与删除事实；返回：无；异常：断言失败；两类manifest不自行默认删除状态。"""
    meta: dict[str, JsonValue] = {"amended": False,
        "document_id": "doc", "internal_document_id": "doc", "ingest_method": "upload",
        "source_provider": "user_upload", "ingest_complete": True,
        "primary_document": "a.txt_docling.json", "is_deleted": deleted,
    }
    project = project_filing_manifest_item if source_kind is SourceKind.FILING else project_material_manifest_item
    assert project(meta).is_deleted is deleted
    del meta["is_deleted"]
    with pytest.raises(KeyError):
        project(meta)
    for wrong in (None, 0, "false"):
        meta["is_deleted"] = wrong
        with pytest.raises(ValueError):
            project(meta)
