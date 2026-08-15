"""Docling 产品转换能力与运行时回退装配的 owner 契约测试。"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest
from docling.backend.docling_parse_backend import DoclingParseDocumentBackend
from docling.datamodel.accelerator_options import AcceleratorDevice
from docling.datamodel.base_models import DocumentStream, FormatToExtensions, InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions, TableFormerMode
from docling.document_converter import PdfFormatOption

from dayu.documents import docling_runtime

if TYPE_CHECKING:
    from docling.datamodel.document import ConversionResult
    from docling.document_converter import DocumentConverter


_DOCLING_PARSE_BACKEND = "docling-parse"
_PYPDFIUM2_BACKEND = "pypdfium2"
_AUTO_DEVICE = "auto"
_CPU_DEVICE = "cpu"
_CUDA_DEVICE = "cuda"
_BLANK_DEVICE = "   "
_MIXED_CASE_CUDA_DEVICE = " CuDa "
_INVALID_DEVICE = "quantum"
_ACCURATE_TABLE_MODE = "accurate"
_FAST_TABLE_MODE = "fast"
_INVALID_TABLE_MODE = "approximate"
_NON_WINDOWS_PLATFORM = "darwin"
_WINDOWS_PLATFORM = "win32"
_STREAM_NAME = "annual-report.pdf"
_PDF_BYTES = b"%PDF-1.7\nowner-stream-contract\n%%EOF"
_EXPECTED_PRODUCT_FORMATS = (
    ("PDF", (".pdf",)),
    ("DOCX", (".docx",)),
    ("PPTX", (".pptx",)),
    ("HTML", (".htm", ".html", ".xhtml")),
    ("MD", (".md", ".txt")),
    ("CSV", (".csv",)),
    ("XLSX", (".xlsx",)),
    ("XML_XBRL", (".xbrl", ".xml")),
    ("JSON_DOCLING", (".json",)),
)
_EXPECTED_PRODUCT_SUFFIXES = (
    ".pdf",
    ".docx",
    ".pptx",
    ".htm",
    ".html",
    ".xhtml",
    ".md",
    ".txt",
    ".csv",
    ".xlsx",
    ".xbrl",
    ".xml",
    ".json",
)
_KNOWN_UNSELECTED_THIRD_PARTY_SUFFIXES = frozenset({".text", ".rmd", ".qmd", ".xlsm", ".potx"})
_FUTURE_PDF_EXTENSION = "future-pdf"


class _ConversionResultMarker:
    """标记测试中的成功转换结果。"""


@dataclass(frozen=True)
class _StreamObservation:
    """记录一次 converter 收到的输入流事实。"""

    wrapper_identity: int
    stream_identity: int
    initially_closed: bool
    name: str
    payload: bytes


class _RecordingConverter:
    """读取并关闭输入流，再返回或抛出预设结果的转换器替身。"""

    def __init__(
        self,
        observations: list[_StreamObservation],
        *,
        result: ConversionResult | None = None,
        failure: RuntimeError | None = None,
    ) -> None:
        """初始化转换器替身。

        Args:
            observations: 追加输入流事实的共享列表。
            result: 成功时返回的预设结果。
            failure: 失败时抛出的预设异常。

        Returns:
            无。

        Raises:
            ValueError: 成功结果和失败异常未恰好提供一个时抛出。
        """

        if (result is None) == (failure is None):
            raise ValueError("成功结果与失败异常必须且只能提供一个")
        self._observations = observations
        self._result = result
        self._failure = failure

    def convert(self, source: DocumentStream) -> ConversionResult:
        """读取并关闭本次输入流，再执行预设结果。

        Args:
            source: 本次转换收到的 Docling 文档流。

        Returns:
            预设的成功转换结果。

        Raises:
            RuntimeError: 本次转换配置为失败时抛出预设异常。
        """

        stream = source.stream
        self._observations.append(
            _StreamObservation(
                wrapper_identity=id(source),
                stream_identity=id(stream),
                initially_closed=stream.closed,
                name=source.name,
                payload=stream.read(),
            )
        )
        stream.close()
        if self._failure is not None:
            raise self._failure
        assert self._result is not None
        return self._result


class _RecordingConverterFactory:
    """按尝试顺序返回转换器，并记录后端与设备装配事实。"""

    def __init__(self, converters: list[_RecordingConverter]) -> None:
        """初始化转换器工厂。

        Args:
            converters: 按预期尝试顺序返回的转换器列表。

        Returns:
            无。

        Raises:
            无。
        """

        self._converters = converters
        self._next_index = 0
        self.attempts: list[tuple[str, str]] = []

    def __call__(
        self,
        *,
        do_ocr: bool,
        do_table_structure: bool,
        table_mode: str,
        do_cell_matching: bool,
        device_name: str | None,
        backend_name: str,
    ) -> DocumentConverter:
        """返回当前尝试对应的转换器。

        Args:
            do_ocr: 是否开启 OCR。
            do_table_structure: 是否开启表格结构识别。
            table_mode: 表格结构模式。
            do_cell_matching: 是否开启单元格匹配。
            device_name: 当前尝试的设备名。
            backend_name: 当前尝试的后端名。

        Returns:
            当前尝试使用的转换器。

        Raises:
            AssertionError: 尝试次数超过预设转换器数量，或设备名为空时抛出。
        """

        del do_ocr, do_table_structure, table_mode, do_cell_matching
        assert device_name is not None
        assert self._next_index < len(self._converters)
        self.attempts.append((backend_name, device_name))
        converter = self._converters[self._next_index]
        self._next_index += 1
        return cast("DocumentConverter", converter)


def _is_not_windows() -> bool:
    """为测试固定返回非 Windows 平台。

    Args:
        无。

    Returns:
        固定返回 False。

    Raises:
        无。
    """

    return False


def _cuda_is_available() -> bool:
    """为测试固定返回 CUDA 可用。

    Args:
        无。

    Returns:
        固定返回 True。

    Raises:
        无。
    """

    return True


def _cuda_is_unavailable() -> bool:
    """为测试固定返回 CUDA 不可用。

    Args:
        无。

    Returns:
        固定返回 False。

    Raises:
        无。
    """

    return False


def _prepare_auto_attempts(
    monkeypatch: pytest.MonkeyPatch,
    factory: _RecordingConverterFactory,
) -> None:
    """固定非 Windows 的 auto 尝试链并安装转换器工厂。

    Args:
        monkeypatch: pytest 属性与环境变量替换工具。
        factory: 本测试使用的记录型转换器工厂。

    Returns:
        无。

    Raises:
        无。
    """

    monkeypatch.delenv(docling_runtime.DOCLING_DEVICE_ENV, raising=False)
    monkeypatch.setattr(docling_runtime, "_is_windows_platform", _is_not_windows)
    monkeypatch.setattr(docling_runtime, "build_docling_pdf_converter", factory)


def test_product_capability_freezes_exact_formats_suffixes_and_metadata_subset() -> None:
    """验证 9 个格式与 13 个有序扩展名精确冻结且受安装元数据支持。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    capability = docling_runtime.DOCLING_CONVERTER_CAPABILITY
    product_formats = tuple((format_item.format_id, format_item.suffixes) for format_item in capability.formats)
    resolved_formats = docling_runtime._resolve_docling_allowed_formats(capability)

    assert product_formats == _EXPECTED_PRODUCT_FORMATS
    assert capability.format_ids == tuple(format_id for format_id, _suffixes in _EXPECTED_PRODUCT_FORMATS)
    assert capability.product_suffixes == _EXPECTED_PRODUCT_SUFFIXES
    assert capability.accepts_product_suffix(" .PDF ") is True
    assert capability.accepts_product_suffix("zip") is False
    assert tuple(input_format.name for input_format in resolved_formats) == capability.format_ids
    for format_item, input_format in zip(capability.formats, resolved_formats, strict=True):
        installed_suffixes = frozenset(
            docling_runtime._normalize_docling_product_suffix(extension)
            for extension in FormatToExtensions[input_format]
        )
        assert frozenset(format_item.suffixes).issubset(installed_suffixes)
    assert _KNOWN_UNSELECTED_THIRD_PARTY_SUFFIXES.isdisjoint(capability.product_suffixes)


@pytest.mark.parametrize(
    "candidate",
    ("", "   ", ".", " \t.\n", Path("README").suffix, Path(".DS_Store").suffix),
    ids=("empty", "blank", "dot", "padded-dot", "no-suffix", "dotfile"),
)
def test_product_suffix_predicate_returns_false_for_inputs_without_effective_suffix(
    candidate: str,
) -> None:
    """验证 admission predicate 对无有效扩展名的任意字符串安全返回 False。

    Args:
        candidate: 空串、空白、点或由无扩展名路径投影出的候选值。

    Returns:
        无。

    Raises:
        无。
    """

    assert docling_runtime.DOCLING_CONVERTER_CAPABILITY.accepts_product_suffix(candidate) is False


def test_product_capability_rejects_minimal_invalid_declarations() -> None:
    """验证 capability owner 拒绝裁决指定的四类最小非法声明。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    with pytest.raises(ValueError, match="扩展名不能为空"):
        docling_runtime.DoclingConverterFormat(format_id="PDF", suffixes=("",))

    with pytest.raises(ValueError, match="至少声明一个格式"):
        docling_runtime.DoclingConverterCapability(formats=())

    with pytest.raises(ValueError, match="重复格式标识"):
        docling_runtime.DoclingConverterCapability(
            formats=(
                docling_runtime.DoclingConverterFormat(format_id="PDF", suffixes=(".pdf",)),
                docling_runtime.DoclingConverterFormat(format_id="PDF", suffixes=(".pdf2",)),
            )
        )

    with pytest.raises(ValueError, match="跨格式声明重复扩展名"):
        docling_runtime.DoclingConverterCapability(
            formats=(
                docling_runtime.DoclingConverterFormat(format_id="PDF", suffixes=(".shared",)),
                docling_runtime.DoclingConverterFormat(format_id="DOCX", suffixes=(".shared",)),
            )
        )


def test_static_capability_projection_does_not_import_docling() -> None:
    """验证模块导入与 help 所需静态投影不会加载 Docling。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    probe = (
        "import sys\n"
        "sys.modules['docling'] = None\n"
        "from dayu.documents.docling_runtime import DOCLING_CONVERTER_CAPABILITY\n"
        "print('|'.join(DOCLING_CONVERTER_CAPABILITY.product_suffixes))\n"
    )

    completed = subprocess.run(
        [sys.executable, "-c", probe],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "|".join(_EXPECTED_PRODUCT_SUFFIXES)


def test_converter_allowed_formats_share_product_capability_and_ignore_added_suffix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """验证第三方新增扩展名不扩面，构造器 allowed_formats 仍与产品声明同源。

    Args:
        monkeypatch: pytest 映射替换工具。

    Returns:
        无。

    Raises:
        无。
    """

    installed_pdf_extensions = FormatToExtensions[InputFormat.PDF]
    monkeypatch.setitem(
        FormatToExtensions,
        InputFormat.PDF,
        [*installed_pdf_extensions, _FUTURE_PDF_EXTENSION],
    )

    converter = docling_runtime.build_docling_pdf_converter(
        do_ocr=False,
        do_table_structure=False,
        device_name=_CPU_DEVICE,
    )

    assert tuple(input_format.name for input_format in converter.allowed_formats) == (
        docling_runtime.DOCLING_CONVERTER_CAPABILITY.format_ids
    )
    assert tuple(converter.format_to_options) == tuple(converter.allowed_formats)
    pdf_option = converter.format_to_options[InputFormat.PDF]
    assert isinstance(pdf_option, PdfFormatOption)
    pdf_pipeline_options = pdf_option.pipeline_options
    assert isinstance(pdf_pipeline_options, PdfPipelineOptions)
    assert pdf_option.backend is DoclingParseDocumentBackend
    assert pdf_pipeline_options.do_ocr is False
    assert pdf_pipeline_options.do_table_structure is False
    assert pdf_pipeline_options.accelerator_options is not None
    assert pdf_pipeline_options.accelerator_options.device is AcceleratorDevice.CPU
    assert docling_runtime.DOCLING_CONVERTER_CAPABILITY.product_suffixes == _EXPECTED_PRODUCT_SUFFIXES
    assert f".{_FUTURE_PDF_EXTENSION}" not in (docling_runtime.DOCLING_CONVERTER_CAPABILITY.product_suffixes)


def test_converter_construction_fails_typed_when_format_extension_mapping_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """验证第三方扩展名 mapping 整项缺失时 constructor path typed fail。

    Args:
        monkeypatch: pytest 映射替换工具。

    Returns:
        无。

    Raises:
        无。
    """

    monkeypatch.delitem(FormatToExtensions, InputFormat.PDF)

    with pytest.raises(
        docling_runtime.DoclingRuntimeInitializationError,
        match="缺少产品格式 'PDF' 的扩展名映射",
    ):
        docling_runtime.build_docling_pdf_converter(
            do_ocr=False,
            do_table_structure=False,
            device_name=_CPU_DEVICE,
        )


@pytest.mark.parametrize(
    ("capability", "expected_message"),
    [
        (
            docling_runtime.DoclingConverterCapability(
                formats=(
                    docling_runtime.DoclingConverterFormat(
                        format_id="REMOVED_FORMAT",
                        suffixes=(".removed",),
                    ),
                )
            ),
            "缺少产品声明的格式",
        ),
        (
            docling_runtime.DoclingConverterCapability(
                formats=(
                    docling_runtime.DoclingConverterFormat(
                        format_id="PDF",
                        suffixes=(".removed",),
                    ),
                )
            ),
            "缺少产品扩展名",
        ),
    ],
    ids=("format-id-missing", "product-suffix-missing"),
)
def test_converter_construction_fails_typed_when_product_metadata_is_missing(
    monkeypatch: pytest.MonkeyPatch,
    capability: docling_runtime.DoclingConverterCapability,
    expected_message: str,
) -> None:
    """验证格式或扩展名缺失时 constructor path typed fail 且不回退默认能力。

    Args:
        monkeypatch: pytest 属性替换工具。
        capability: 本例注入的缺失元数据 capability。
        expected_message: 预期稳定错误片段。

    Returns:
        无。

    Raises:
        无。
    """

    monkeypatch.setattr(docling_runtime, "DOCLING_CONVERTER_CAPABILITY", capability)

    with pytest.raises(
        docling_runtime.DoclingRuntimeInitializationError,
        match=expected_message,
    ):
        docling_runtime.build_docling_pdf_converter(
            do_ocr=False,
            do_table_structure=False,
            device_name=_CPU_DEVICE,
        )


@pytest.mark.parametrize(
    ("platform_name", "device_name", "cuda_available", "expected_attempts"),
    [
        (
            _NON_WINDOWS_PLATFORM,
            _AUTO_DEVICE,
            False,
            (
                (_DOCLING_PARSE_BACKEND, _AUTO_DEVICE),
                (_PYPDFIUM2_BACKEND, _AUTO_DEVICE),
                (_DOCLING_PARSE_BACKEND, _CPU_DEVICE),
            ),
        ),
        (
            _NON_WINDOWS_PLATFORM,
            _CPU_DEVICE,
            False,
            (
                (_DOCLING_PARSE_BACKEND, _CPU_DEVICE),
                (_PYPDFIUM2_BACKEND, _CPU_DEVICE),
            ),
        ),
        (
            _WINDOWS_PLATFORM,
            _AUTO_DEVICE,
            True,
            (
                (_DOCLING_PARSE_BACKEND, _AUTO_DEVICE),
                (_PYPDFIUM2_BACKEND, _AUTO_DEVICE),
                (_DOCLING_PARSE_BACKEND, _CPU_DEVICE),
            ),
        ),
        (
            _WINDOWS_PLATFORM,
            _AUTO_DEVICE,
            False,
            (
                (_PYPDFIUM2_BACKEND, _AUTO_DEVICE),
                (_DOCLING_PARSE_BACKEND, _AUTO_DEVICE),
                (_DOCLING_PARSE_BACKEND, _CPU_DEVICE),
            ),
        ),
        (
            _WINDOWS_PLATFORM,
            _CUDA_DEVICE,
            False,
            (
                (_DOCLING_PARSE_BACKEND, _CUDA_DEVICE),
                (_PYPDFIUM2_BACKEND, _CUDA_DEVICE),
            ),
        ),
    ],
)
def test_plan_conversion_attempts_preserves_platform_and_device_order(
    monkeypatch: pytest.MonkeyPatch,
    platform_name: str,
    device_name: str,
    cuda_available: bool,
    expected_attempts: tuple[tuple[str, str], ...],
) -> None:
    """验证平台与设备矩阵映射到既有后端与设备尝试顺序。

    Args:
        monkeypatch: pytest 属性替换工具。
        platform_name: 本例固定的平台名。
        device_name: 本例使用的 Docling 设备名。
        cuda_available: Windows auto 分支中的 CUDA 可用状态。
        expected_attempts: 预期的 backend/device 尝试顺序。

    Returns:
        无。

    Raises:
        无。
    """

    cuda_probe = _cuda_is_available if cuda_available else _cuda_is_unavailable
    monkeypatch.setattr(docling_runtime.sys, "platform", platform_name)
    monkeypatch.setattr(docling_runtime, "_is_windows_cuda_available", cuda_probe)

    attempts = docling_runtime._plan_conversion_attempts(device_name)

    assert tuple((attempt.backend_name, attempt.device_name) for attempt in attempts) == expected_attempts


@pytest.mark.parametrize(
    (
        "do_ocr",
        "do_table_structure",
        "table_mode",
        "do_cell_matching",
        "device_name",
        "expected_table_mode",
        "expected_device",
    ),
    [
        (
            True,
            True,
            _ACCURATE_TABLE_MODE,
            True,
            _CPU_DEVICE,
            TableFormerMode.ACCURATE,
            AcceleratorDevice.CPU,
        ),
        (
            False,
            True,
            _FAST_TABLE_MODE,
            False,
            _CUDA_DEVICE,
            TableFormerMode.FAST,
            AcceleratorDevice.CUDA,
        ),
        (
            False,
            False,
            _ACCURATE_TABLE_MODE,
            True,
            _AUTO_DEVICE,
            None,
            AcceleratorDevice.AUTO,
        ),
    ],
)
def test_build_docling_pdf_pipeline_options_projects_supported_settings(
    do_ocr: bool,
    do_table_structure: bool,
    table_mode: str,
    do_cell_matching: bool,
    device_name: str,
    expected_table_mode: TableFormerMode | None,
    expected_device: AcceleratorDevice,
) -> None:
    """验证正式 Docling 选项中的 OCR、表格、单元格与设备投影。

    Args:
        do_ocr: 本例是否开启 OCR。
        do_table_structure: 本例是否开启表格结构识别。
        table_mode: 本例使用的表格结构模式。
        do_cell_matching: 本例是否开启表格单元格匹配。
        device_name: 本例使用的 Docling 设备名。
        expected_table_mode: 开启表格结构时预期的 Docling 模式。
        expected_device: 预期的 Docling 加速器设备枚举。

    Returns:
        无。

    Raises:
        无。
    """

    options = docling_runtime.build_docling_pdf_pipeline_options(
        do_ocr=do_ocr,
        do_table_structure=do_table_structure,
        table_mode=table_mode,
        do_cell_matching=do_cell_matching,
        device_name=device_name,
    )

    assert options.do_ocr is do_ocr
    assert options.do_table_structure is do_table_structure
    assert options.accelerator_options is not None
    assert options.accelerator_options.device is expected_device
    if expected_table_mode is not None:
        assert options.table_structure_options.mode is expected_table_mode
        assert options.table_structure_options.do_cell_matching is do_cell_matching


def test_build_docling_pdf_pipeline_options_rejects_invalid_table_mode() -> None:
    """验证非法表格模式在 Docling 依赖装配前被 owner 拒绝。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    with pytest.raises(ValueError):
        docling_runtime.build_docling_pdf_pipeline_options(
            table_mode=_INVALID_TABLE_MODE,
        )


@pytest.mark.parametrize(
    ("configured_device", "expected_device"),
    [
        (None, _AUTO_DEVICE),
        (_BLANK_DEVICE, _AUTO_DEVICE),
        (_MIXED_CASE_CUDA_DEVICE, _CUDA_DEVICE),
    ],
)
def test_resolve_docling_device_name_uses_default_and_canonicalizes_environment(
    monkeypatch: pytest.MonkeyPatch,
    configured_device: str | None,
    expected_device: str,
) -> None:
    """验证设备环境变量缺失、空白与支持值的规范化语义。

    Args:
        monkeypatch: pytest 环境变量替换工具。
        configured_device: 本例注入的设备配置；None 表示删除环境变量。
        expected_device: 预期的 canonical 设备名。

    Returns:
        无。

    Raises:
        无。
    """

    if configured_device is None:
        monkeypatch.delenv(docling_runtime.DOCLING_DEVICE_ENV, raising=False)
    else:
        monkeypatch.setenv(docling_runtime.DOCLING_DEVICE_ENV, configured_device)

    assert docling_runtime.resolve_docling_device_name() == expected_device


def test_resolve_docling_device_name_rejects_unsupported_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """验证不支持的设备环境变量由运行时真源明确拒绝。

    Args:
        monkeypatch: pytest 环境变量替换工具。

    Returns:
        无。

    Raises:
        无。
    """

    monkeypatch.setenv(docling_runtime.DOCLING_DEVICE_ENV, _INVALID_DEVICE)

    with pytest.raises(docling_runtime.DoclingRuntimeInitializationError):
        docling_runtime.resolve_docling_device_name()


def test_convert_pdf_bytes_rebuilds_stream_after_closed_first_attempt_and_second_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """验证首档关闭输入失败后，第二档仍收到全新可读流并成功。

    Args:
        monkeypatch: pytest 属性与环境变量替换工具。

    Returns:
        无。

    Raises:
        无。
    """

    observations: list[_StreamObservation] = []
    first_failure = RuntimeError("first attempt failed")
    success = cast("ConversionResult", _ConversionResultMarker())
    factory = _RecordingConverterFactory(
        [
            _RecordingConverter(observations, failure=first_failure),
            _RecordingConverter(observations, result=success),
        ]
    )
    _prepare_auto_attempts(monkeypatch, factory)

    result = docling_runtime.convert_pdf_bytes_with_docling(
        _PDF_BYTES,
        stream_name=_STREAM_NAME,
    )

    assert result is success
    assert factory.attempts == [
        (_DOCLING_PARSE_BACKEND, _AUTO_DEVICE),
        (_PYPDFIUM2_BACKEND, _AUTO_DEVICE),
    ]
    assert len(observations) == 2
    first_observation, second_observation = observations
    assert first_observation.initially_closed is False
    assert second_observation.initially_closed is False
    assert first_observation.name == second_observation.name == _STREAM_NAME
    assert first_observation.payload == second_observation.payload == _PDF_BYTES
    assert first_observation.wrapper_identity != second_observation.wrapper_identity
    assert first_observation.stream_identity != second_observation.stream_identity


def test_convert_pdf_bytes_auto_three_attempts_use_distinct_streams_and_preserve_failure_chain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """验证 auto 三档流均独立，且全失败时保留末因与首因 identity。

    Args:
        monkeypatch: pytest 属性与环境变量替换工具。

    Returns:
        无。

    Raises:
        无。
    """

    observations: list[_StreamObservation] = []
    first_failure = RuntimeError("first attempt failed")
    middle_failure = RuntimeError("middle attempt failed")
    last_failure = RuntimeError("last attempt failed")
    factory = _RecordingConverterFactory(
        [
            _RecordingConverter(observations, failure=first_failure),
            _RecordingConverter(observations, failure=middle_failure),
            _RecordingConverter(observations, failure=last_failure),
        ]
    )
    _prepare_auto_attempts(monkeypatch, factory)

    with pytest.raises(RuntimeError) as exception_info:
        docling_runtime.convert_pdf_bytes_with_docling(
            _PDF_BYTES,
            stream_name=_STREAM_NAME,
        )

    caught = exception_info.value
    assert caught is last_failure
    assert caught.__cause__ is first_failure
    assert caught.__cause__ is not middle_failure
    assert factory.attempts == [
        (_DOCLING_PARSE_BACKEND, _AUTO_DEVICE),
        (_PYPDFIUM2_BACKEND, _AUTO_DEVICE),
        (_DOCLING_PARSE_BACKEND, _CPU_DEVICE),
    ]
    assert len(observations) == 3
    assert len({item.wrapper_identity for item in observations}) == 3
    assert len({item.stream_identity for item in observations}) == 3
    assert all(item.initially_closed is False for item in observations)
    assert all(item.name == _STREAM_NAME for item in observations)
    assert all(item.payload == _PDF_BYTES for item in observations)
