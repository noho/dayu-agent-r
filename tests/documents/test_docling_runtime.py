"""Docling 运行时各次尝试独立输入流的契约测试。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

import pytest
from docling.datamodel.accelerator_options import AcceleratorDevice
from docling.datamodel.base_models import DocumentStream
from docling.datamodel.pipeline_options import TableFormerMode

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
