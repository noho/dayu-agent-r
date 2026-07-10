"""DoclingUploadService 行为测试。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from dayu.contracts.json_value import JsonValue
from dayu.fins.domain.enums import SourceKind
from dayu.fins.pipelines.docling_upload_service import (
    DoclingUploadService,
    _PendingFileAsset,
    _build_upload_source_fingerprint,
    _increment_document_version,
    _resolve_document_version,
    _resolve_upsert_mode,
    build_cn_filing_ids,
    build_material_ids,
    build_sec_filing_ids,
    derive_report_kind,
    normalize_cn_fiscal_period,
    validate_material_upload_ids,
)
from dayu.fins.storage import (
    FsDocumentBlobRepository,
    FsSourceDocumentRepository,
)
from dayu.fins.storage._fs_repository_factory import build_fs_repository_set


@dataclass(frozen=True)
class _UploadServiceContext:
    """上传服务测试上下文。"""

    source_repository: FsSourceDocumentRepository
    blob_repository: FsDocumentBlobRepository
    service: DoclingUploadService


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
    return {"name": stream_name, "source": "docling"}


def _build_service_context(tmp_path: Path) -> _UploadServiceContext:
    """构建上传服务测试上下文。

    Args:
        tmp_path: 临时工作区目录。

    Returns:
        上传服务测试上下文。

    Raises:
        OSError: 底层仓储初始化失败时抛出。
    """

    repository_set = build_fs_repository_set(workspace_root=tmp_path)
    source_repository = FsSourceDocumentRepository(tmp_path, repository_set=repository_set)
    blob_repository = FsDocumentBlobRepository(tmp_path, repository_set=repository_set)
    service = DoclingUploadService(
        source_repository=source_repository,
        blob_repository=blob_repository,
        convert_with_docling=_convert_docling_stub,
    )
    return _UploadServiceContext(
        source_repository=source_repository,
        blob_repository=blob_repository,
        service=service,
    )


def test_execute_upload_create_material_success(tmp_path: Path) -> None:
    """create 上传应写入原文件与 Docling 主文件。

    Args:
        tmp_path: 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    context = _build_service_context(tmp_path)
    sample_file = tmp_path / "deck.pdf"
    sample_file.write_text("hello", encoding="utf-8")

    result = context.service.execute_upload(
        ticker="AAPL",
        source_kind=SourceKind.MATERIAL,
        action="create",
        document_id="mat_demo",
        internal_document_id="mat_demo",
        form_type="MATERIAL_OTHER",
        files=[sample_file],
        overwrite=False,
        meta={"material_name": "Deck", "ingest_method": "upload"},
    )

    assert result.status == "uploaded"
    assert result.document_id == "mat_demo"
    assert len(result.file_events) == 3
    assert result.file_events[0].event_type == "conversion_started"
    meta = context.source_repository.get_source_meta("AAPL", "mat_demo", SourceKind.MATERIAL)
    assert str(meta["primary_document"]).endswith("_docling.json")
    assert meta["source_provider"] == "user_upload"
    assert len(meta["files"]) == 2


def test_execute_upload_skips_when_source_fingerprint_matches(tmp_path: Path) -> None:
    """相同源文件重复上传时应在转换前跳过。

    Args:
        tmp_path: 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    calls: list[str] = []

    def counting_converter(raw_data: bytes, stream_name: str) -> dict[str, JsonValue]:
        """记录转换调用并返回固定结果。

        Args:
            raw_data: 输入原始字节。
            stream_name: 输入流名称。

        Returns:
            固定结构化结果。

        Raises:
            无。
        """

        del raw_data
        calls.append(stream_name)
        return {"name": stream_name, "source": "docling"}

    repository_set = build_fs_repository_set(workspace_root=tmp_path)
    source_repository = FsSourceDocumentRepository(tmp_path, repository_set=repository_set)
    blob_repository = FsDocumentBlobRepository(tmp_path, repository_set=repository_set)
    service = DoclingUploadService(
        source_repository=source_repository,
        blob_repository=blob_repository,
        convert_with_docling=counting_converter,
    )
    sample_file = tmp_path / "deck.pdf"
    sample_file.write_text("hello", encoding="utf-8")

    first = service.execute_upload(
        ticker="AAPL",
        source_kind=SourceKind.MATERIAL,
        action="create",
        document_id="mat_demo",
        internal_document_id="mat_demo",
        form_type="MATERIAL_OTHER",
        files=[sample_file],
        overwrite=False,
        meta={"material_name": "Deck", "ingest_method": "upload"},
    )
    second = service.execute_upload(
        ticker="AAPL",
        source_kind=SourceKind.MATERIAL,
        action="create",
        document_id="mat_demo",
        internal_document_id="mat_demo",
        form_type="MATERIAL_OTHER",
        files=[sample_file],
        overwrite=False,
        meta={"material_name": "Deck", "ingest_method": "upload"},
    )

    assert first.status == "uploaded"
    assert second.status == "skipped"
    assert calls == ["deck.pdf"]
    assert all(event.event_type == "file_skipped" for event in second.file_events)


def test_execute_upload_delete_material(tmp_path: Path) -> None:
    """delete 动作应执行逻辑删除且不要求文件。

    Args:
        tmp_path: 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    context = _build_service_context(tmp_path)
    sample_file = tmp_path / "deck.pdf"
    sample_file.write_text("hello", encoding="utf-8")
    context.service.execute_upload(
        ticker="AAPL",
        source_kind=SourceKind.MATERIAL,
        action="create",
        document_id="mat_demo",
        internal_document_id="mat_demo",
        form_type="MATERIAL_OTHER",
        files=[sample_file],
        overwrite=False,
        meta={"material_name": "Deck", "ingest_method": "upload"},
    )

    result = context.service.execute_upload(
        ticker="AAPL",
        source_kind=SourceKind.MATERIAL,
        action="delete",
        document_id="mat_demo",
        internal_document_id="mat_demo",
        form_type="MATERIAL_OTHER",
        files=[],
        overwrite=False,
        meta={},
    )

    meta = context.source_repository.get_source_meta("AAPL", "mat_demo", SourceKind.MATERIAL)
    assert result.status == "deleted"
    assert meta["is_deleted"] is True


def test_upload_helper_id_and_version_rules() -> None:
    """上传 helper 应保留 OLD ID、版本与财期规则。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    cn_document_id, cn_internal_id = build_cn_filing_ids(
        ticker="600519",
        form_type="FY",
        fiscal_year=2024,
        fiscal_period="FY",
        amended=False,
    )
    sec_document_id, sec_internal_id = build_sec_filing_ids(
        ticker="AAPL",
        fiscal_year=2024,
        fiscal_period="FY",
        amended=True,
    )
    material_id, material_internal_id = build_material_ids(
        form_type="MATERIAL_OTHER",
        material_name="Deck",
        fiscal_year=2024,
        fiscal_period="FY",
    )

    assert cn_document_id.startswith("fil_cn_")
    assert cn_internal_id.startswith("cn_")
    assert sec_document_id.startswith("fil_sec_")
    assert sec_internal_id.startswith("sec_")
    assert material_id == material_internal_id
    assert material_id.startswith("mat_")
    assert normalize_cn_fiscal_period("h1") == "H1"
    assert derive_report_kind("FY") == "annual"
    assert _increment_document_version("v2") == "v3"
    assert _resolve_document_version(None, "fp") == "v1"
    assert _resolve_document_version({"document_version": "v1", "source_fingerprint": "old"}, "new") == "v2"
    assert _resolve_upsert_mode("update", None, True) == "create"
    assert validate_material_upload_ids(
        stable_document_id="mat_a",
        stable_internal_document_id="mat_a",
        document_id=None,
        internal_document_id=None,
    ) == ("mat_a", "mat_a")
    with pytest.raises(ValueError, match="document_id"):
        validate_material_upload_ids(
            stable_document_id="mat_a",
            stable_internal_document_id="mat_a",
            document_id="mat_b",
            internal_document_id=None,
        )


def test_upload_source_fingerprint_is_stable() -> None:
    """上传源指纹应按文件名排序保持稳定。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    first = [
        _PendingFileAsset("b.pdf", b"b", "application/pdf", "sha-b", 1, "original"),
        _PendingFileAsset("a.pdf", b"a", "application/pdf", "sha-a", 1, "original"),
    ]
    second = [
        _PendingFileAsset("a.pdf", b"a", "application/pdf", "sha-a", 1, "original"),
        _PendingFileAsset("b.pdf", b"b", "application/pdf", "sha-b", 1, "original"),
    ]

    assert _build_upload_source_fingerprint(first) == _build_upload_source_fingerprint(second)
