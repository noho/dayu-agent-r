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
    DoclingConversionError,
    DoclingConversionFailureKind,
    DoclingConversionResult,
)
from dayu.fins.pipelines.upload_material_events import UploadMaterialEventType
from dayu.fins.processors.registry import build_fins_processor_registry


class _FakeDoclingConverter:
    """SEC material 测试用 typed converter。"""

    def __init__(self, calls: list[str] | None = None) -> None:
        """初始化可选转换调用记录器。

        Args:
            calls: 可选 basename 调用记录。

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


class _FailingMaterialDoclingConverter:
    """在指定 material 文件注入 typed conversion failure 的测试 converter。"""

    def __init__(self, *, failing_name: str, calls: list[str]) -> None:
        """初始化逐文件 failure converter。

        Args:
            failing_name: 应抛出异常的 basename。
            calls: 转换调用顺序记录。

        Returns:
            无。

        Raises:
            无。
        """

        self._failing_name = failing_name
        self._calls = calls

    async def convert_to_json_bytes(
        self,
        input_bytes: bytes,
        stream_name: str,
        *,
        config: DoclingConversionConfig,
        cancellation: CancellationToken | None,
    ) -> DoclingConversionResult:
        """记录调用并在目标文件抛出 closed typed conversion failure。

        Args:
            input_bytes: 输入字节。
            stream_name: 输入名称。
            config: 闭合转换配置。
            cancellation: canonical token。

        Returns:
            非目标文件的 typed conversion result。

        Raises:
            DoclingConversionError: 当前文件命中 failure fixture 时抛出。
        """

        del input_bytes, config, cancellation
        self._calls.append(stream_name)
        if stream_name == self._failing_name:
            raise DoclingConversionError(
                DoclingConversionFailureKind.CONVERTER_EXECUTION,
                "Docling conversion execution failed",
                23,
            )
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
    assert pipeline._company_repository.resolve_company_ticker("APC") == "AAPL"
    assert pipeline._company_repository.resolve_company_ticker("V.BA") == "AAPL"
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
async def test_upload_material_failure_uses_shared_typed_failure_owner(tmp_path: Path) -> None:
    """SEC material terminal catch 必须复用共享 typed failure owner。

    Args:
        tmp_path: 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: material 未使用 bounded typed failure projection 时抛出。
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
    assert result["message"] == "上传执行失败，请检查运行日志后重试"
    assert result["failure"] == {
        "kind": "runtime",
        "code": "unexpected_runtime",
        "message": "上传执行失败，请检查运行日志后重试",
        "retry_hint": None,
        "file_label": None,
    }
    assert events[-1].payload["error"] == "上传执行失败，请检查运行日志后重试"


@pytest.mark.asyncio
async def test_upload_material_nth_conversion_failure_is_content_terminal_without_source_publication(
    tmp_path: Path,
) -> None:
    """第 N 项 material 转换失败必须投影 content terminal 且不发布 source。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: failure 分类、文件归属或零 source 发布边界漂移时抛出。
    """

    calls: list[str] = []
    pipeline = SecPipeline(
        workspace_root=tmp_path,
        processor_registry=build_fins_processor_registry(),
        docling_converter=_FailingMaterialDoclingConverter(
            failing_name="corrupt.docx",
            calls=calls,
        ),
    )
    files = [tmp_path / "ok.pdf", tmp_path / "corrupt.docx"]
    for file_path in files:
        file_path.write_bytes(file_path.name.encode())

    events = [
        event
        async for event in pipeline.upload_material_stream(
            ticker="AAPL",
            action="create",
            form_type="MATERIAL_OTHER",
            material_name="Deck",
            files=files,
            company_name="Apple Inc.",
            overwrite=False,
        )
    ]

    assert [event.event_type for event in events] == [
        UploadMaterialEventType.UPLOAD_STARTED,
        UploadMaterialEventType.UPLOAD_FAILED,
    ]
    assert calls == ["ok.pdf", "corrupt.docx"]
    result = events[-1].payload["result"]
    assert isinstance(result, dict)
    assert result["status"] == "failed"
    assert result["stored_file_count"] == 0
    assert result["failure"] == {
        "kind": "content",
        "code": "docling_converter_execution",
        "message": "文件无法解析或已损坏，请检查文件后重试",
        "retry_hint": "请确认文件可正常打开并重新上传",
        "file_label": None,
    }
    document_id = str(result["document_id"])
    with pytest.raises(FileNotFoundError):
        pipeline._source_repository.get_source_meta(
            "AAPL",
            document_id,
            SourceKind.MATERIAL,
        )
    assert not tuple((tmp_path / "portfolio" / "AAPL" / "materials").glob("*"))


@pytest.mark.asyncio
async def test_upload_material_unsupported_suffix_fails_before_reads_or_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SEC material 格式 admission 必须在现有 catch 内先于任何外部副作用。

    Args:
        tmp_path: pytest 临时目录。
        monkeypatch: 外部读取与 mutation 禁用夹具。

    Returns:
        无。

    Raises:
        AssertionError: 格式错误逃逸、被重分类或产生副作用时抛出。
    """

    calls: list[str] = []
    pipeline = SecPipeline(
        workspace_root=tmp_path,
        processor_registry=build_fins_processor_registry(),
        docling_converter=_FakeDoclingConverter(calls),
    )
    unsupported_file = tmp_path / "deck.zip"
    unsupported_file.write_bytes(b"not read")

    def reject_state_read(ticker: str, document_id: str, source_kind: SourceKind) -> None:
        """拒绝 published-state 读取。

        Args:
            ticker: 意外 ticker。
            document_id: 意外文档 ID。
            source_kind: 意外 source kind。

        Returns:
            不返回。

        Raises:
            AssertionError: 始终抛出。
        """

        del ticker, document_id, source_kind
        raise AssertionError("格式 admission 前禁止读取 published state")

    def reject_batch(ticker: str) -> None:
        """拒绝任何 company/source batch。

        Args:
            ticker: 意外 batch ticker。

        Returns:
            不返回。

        Raises:
            AssertionError: 始终抛出。
        """

        del ticker
        raise AssertionError("格式 admission 失败禁止开启 batch")

    def reject_file_read(path: Path) -> bytes:
        """拒绝输入文件读取。

        Args:
            path: 意外读取路径。

        Returns:
            不返回。

        Raises:
            AssertionError: 始终抛出。
        """

        raise AssertionError(f"格式 admission 失败禁止读取文件: {path.name}")

    monkeypatch.setattr(pipeline, "_safe_get_document_meta", reject_state_read)
    monkeypatch.setattr(pipeline._batching_repository, "begin_batch", reject_batch)
    monkeypatch.setattr(Path, "read_bytes", reject_file_read)

    events = [
        event
        async for event in pipeline.upload_material_stream(
            ticker="AAPL",
            action="create",
            form_type="MATERIAL_OTHER",
            material_name="Deck",
            files=[unsupported_file],
            company_name="Apple Inc.",
        )
    ]
    result = events[-1].payload["result"]
    assert isinstance(result, dict)

    assert [event.event_type for event in events] == [UploadMaterialEventType.UPLOAD_FAILED]
    assert result["failure"] == {
        "kind": "usage",
        "code": "unsupported_upload_format",
        "message": "文件格式不受支持，请选择支持的文件后重试",
        "retry_hint": "请查看上传帮助中的支持格式后重试",
        "file_label": "deck.zip",
    }
    assert calls == []
    assert not (tmp_path / "portfolio" / "AAPL").exists()


@pytest.mark.asyncio
async def test_upload_material_alias_conflict_projects_exact_typed_terminal(tmp_path: Path) -> None:
    """SEC material alias conflict 必须从 storage typed error 投影 exact failure JSON。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: conflict 未原子拒绝或 terminal JSON 漂移时抛出。
    """

    pipeline = SecPipeline(
        workspace_root=tmp_path,
        processor_registry=build_fins_processor_registry(),
        docling_converter=_FakeDoclingConverter(),
    )
    existing = pipeline._batching_repository.begin_batch("MSFT")
    pipeline._batching_repository.commit_batch(existing)
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
            company_name="Apple Inc.",
            ticker_aliases=["MSFT"],
            overwrite=False,
        )
    ]

    result = events[-1].payload["result"]
    assert isinstance(result, dict)
    expected_failure = {
        "kind": "storage",
        "code": "ticker_alias_conflict",
        "message": "股票代码别名已属于当前工作区中的其他公司，请移除冲突别名后重试",
        "retry_hint": "请确认公司的主代码与别名声明后重新上传",
        "file_label": None,
    }
    assert events[-1].event_type is UploadMaterialEventType.UPLOAD_FAILED
    assert result["status"] == "failed"
    assert result["stored_file_count"] == 0
    assert result["failure"] == expected_failure
    assert events[-1].payload["error"] == expected_failure["message"]
    assert not (tmp_path / "portfolio" / "AAPL").exists()


@pytest.mark.parametrize(
    "corruption",
    (
        "malformed_meta",
        "meta_symlink",
        "meta_directory",
        "target_symlink",
        "target_regular_file",
    ),
)
@pytest.mark.asyncio
async def test_upload_material_identity_corruption_projects_storage_terminal(
    tmp_path: Path,
    corruption: str,
) -> None:
    """material 真实 meta/target corruption 必须走共享 typed terminal owner。

    Args:
        tmp_path: pytest 临时目录。
        corruption: 待注入的 durable corruption 形态。

    Returns:
        无。

    Raises:
        AssertionError: corruption 落成 unexpected_runtime、泄露 schema 原文或
            发布 material source 时抛出。
        OSError: 测试环境无法创建 symlink 时抛出。
    """

    pipeline = SecPipeline(
        workspace_root=tmp_path,
        processor_registry=build_fins_processor_registry(),
        docling_converter=_FakeDoclingConverter(),
    )
    ticker_dir = tmp_path / "portfolio" / "AAPL"
    if corruption.startswith("target_"):
        ticker_dir.parent.mkdir(parents=True, exist_ok=True)
        if corruption == "target_symlink":
            outside_dir = tmp_path / "outside-company"
            outside_dir.mkdir()
            ticker_dir.symlink_to(outside_dir, target_is_directory=True)
        else:
            ticker_dir.write_bytes(b"foreign locator")
    else:
        batch = pipeline._batching_repository.begin_batch("AAPL")
        pipeline._batching_repository.commit_batch(batch)
        meta_path = ticker_dir / "meta.json"
        if corruption == "malformed_meta":
            meta_path.write_text("{}", encoding="utf-8")
        elif corruption == "meta_symlink":
            outside_meta = tmp_path / "outside-meta.json"
            outside_meta.write_text("{}", encoding="utf-8")
            meta_path.symlink_to(outside_meta)
        else:
            meta_path.mkdir()
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
            company_name="Apple Inc.",
            overwrite=False,
        )
    ]

    result = events[-1].payload["result"]
    assert isinstance(result, dict)
    expected_failure = {
        "kind": "storage",
        "code": "storage_io",
        "message": "工作区公司代码身份数据损坏，无法安全提交",
        "retry_hint": "请修复工作区公司元数据后重试",
        "file_label": None,
    }
    assert events[-1].event_type is UploadMaterialEventType.UPLOAD_FAILED
    assert result["status"] == "failed"
    assert result["stored_file_count"] == 0
    assert result["failure"] == expected_failure
    assert events[-1].payload["error"] == expected_failure["message"]
    assert "CompanyMeta" not in str(events[-1].payload)
    assert "ticker_aliases 必须" not in str(events[-1].payload)
    if ticker_dir.is_dir() and not ticker_dir.is_symlink():
        assert not tuple((ticker_dir / "materials").glob("*"))
