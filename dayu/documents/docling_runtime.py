"""Docling 转换能力与运行时装配真源。

本模块是 Dayu 所有 Docling 转换入口的能力与装配真源，统一负责：

1. 以不加载 Docling 的不可变声明冻结产品允许的输入格式与扩展名；
2. 在构造转换器时延迟校验产品声明仍是已安装 Docling 能力的子集；
3. 解析稳定的设备策略并构造带统一参数的 `DocumentConverter`；
4. 维护一条二维（backend × device）的有序回退尝试链，自动绕开
   docling-parse 后端在某些上市公司年报 PDF 上把合法文档判定为
   ``not valid`` 的情况，并兼容 GPU/MPS 推理崩溃后的 CPU 兜底。

当前策略：

- 若显式设置环境变量 ``DAYU_DOCLING_DEVICE``，则以该值为准。
- 若未显式设置，则默认使用 ``auto``。
- 转换尝试链按平台展开：
  - 非 Windows（macOS / Linux）：
    1. ``backend=docling-parse, device=resolved``：保留现状，覆盖正常路径。
    2. ``backend=pypdfium2, device=resolved``：救 docling-parse 解析失败。
    3. ``backend=docling-parse, device=cpu``：仅当 ``resolved == auto`` 追加，
       救加速器栈在 ``auto`` 阶段崩溃的故障。
  - Windows + 显式加速器设备（``cuda/mps/xpu``）或 ``auto`` 且 CUDA 可用：
    1. ``backend=docling-parse, device=resolved``：GPU 路径实测稳定，
       优先保留解析质量。
    2. ``backend=pypdfium2, device=resolved``：救 docling-parse 解析失败。
  - Windows + ``cpu``，或 ``auto`` 但 CUDA 不可用：
    1. ``backend=pypdfium2, device=resolved``：优先，规避 docling-parse 在
       Windows 上的 ``std::bad_alloc`` 与 mbcs 路径编码两类已知崩溃。
    2. ``backend=docling-parse, device=resolved``：兜底，给特殊文档保留机会。
    3. ``backend=docling-parse, device=cpu``：仅当 ``resolved == auto`` 追加。
- 任意一档成功即返回；全部失败时抛出最后一次异常，并以**首次**失败
  作为 ``__cause__``，便于排查首因。
"""

from __future__ import annotations

import os
import logging
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, TypeVar, cast

if TYPE_CHECKING:
    from docling.backend.abstract_backend import AbstractDocumentBackend
    from docling.datamodel.accelerator_options import AcceleratorOptions
    from docling.datamodel.base_models import DocumentStream, InputFormat
    from docling.datamodel.document import ConversionResult
    from docling.datamodel.pipeline_options import PipelineOptions, TableFormerMode
    from docling.document_converter import DocumentConverter

DOCLING_DEVICE_ENV = "DAYU_DOCLING_DEVICE"
_SUPPORTED_DOCLING_DEVICES = frozenset({"auto", "cpu", "cuda", "mps", "xpu"})
_AUTO_DEVICE_NAME = "auto"
_CPU_DEVICE_NAME = "cpu"
_CUDA_DEVICE_NAME = "cuda"
_MPS_DEVICE_NAME = "mps"
_XPU_DEVICE_NAME = "xpu"
_ACCELERATOR_DEVICE_NAMES = frozenset({_CUDA_DEVICE_NAME, _MPS_DEVICE_NAME, _XPU_DEVICE_NAME})
_DOCLING_PARSE_BACKEND_NAME = "docling-parse"
_PYPDFIUM2_BACKEND_NAME = "pypdfium2"
_SUPPORTED_DOCLING_BACKENDS = frozenset({_DOCLING_PARSE_BACKEND_NAME, _PYPDFIUM2_BACKEND_NAME})
_TABLE_MODE_ACCURATE = "accurate"
_TABLE_MODE_FAST = "fast"
_LOGGER = logging.getLogger(__name__)
_WINDOWS_PLATFORM_NAME = "win32"
_TResult = TypeVar("_TResult")
# Protocol 返回值需要协变，才能让更具体的转换结果回调安全替换更宽的调用点。
_TResultCovariant = TypeVar("_TResultCovariant", covariant=True)


def _normalize_docling_product_suffix(suffix: str) -> str:
    """把候选扩展名规范化为产品 capability 使用的形式。

    Args:
        suffix: 候选扩展名，可包含首尾空白、大小写差异或省略前导点。

    Returns:
        带前导点的小写扩展名。

    Raises:
        ValueError: 扩展名为空或只包含前导点时抛出。
    """

    normalized_suffix = suffix.strip().lower()
    if not normalized_suffix:
        raise ValueError("Docling 产品扩展名不能为空")
    if not normalized_suffix.startswith("."):
        normalized_suffix = f".{normalized_suffix}"
    if normalized_suffix == ".":
        raise ValueError("Docling 产品扩展名不能只有前导点")
    return normalized_suffix


@dataclass(frozen=True, slots=True)
class DoclingConverterFormat:
    """一个不可变的产品 Docling 格式声明。

    Args:
        format_id: 可在构造期解析为 Docling ``InputFormat`` 的稳定标识。
        suffixes: 当前产品明确承诺给该格式的有序扩展名 tuple。

    Raises:
        ValueError: 格式标识为空，或扩展名为空、未规范化、重复时抛出。
    """

    format_id: str
    suffixes: tuple[str, ...]

    def __post_init__(self) -> None:
        """校验单个产品格式声明的静态不变量。

        Args:
            无。

        Returns:
            无。

        Raises:
            ValueError: 格式标识为空，或扩展名为空、未规范化、重复时抛出。
        """

        if not self.format_id.strip():
            raise ValueError("Docling 产品格式标识不能为空")
        if not self.suffixes:
            raise ValueError(f"Docling 产品格式 {self.format_id!r} 必须声明扩展名")
        normalized_suffixes = tuple(_normalize_docling_product_suffix(suffix) for suffix in self.suffixes)
        if normalized_suffixes != self.suffixes:
            raise ValueError(f"Docling 产品格式 {self.format_id!r} 的扩展名必须是规范化小写形式")
        if len(frozenset(self.suffixes)) != len(self.suffixes):
            raise ValueError(f"Docling 产品格式 {self.format_id!r} 不能声明重复扩展名")


@dataclass(frozen=True, slots=True)
class DoclingConverterCapability:
    """不可变的产品 Docling 转换能力契约。

    Args:
        formats: 按产品投影顺序排列的非空格式声明 tuple。

    Raises:
        ValueError: 格式 tuple 为空，或格式标识、扩展名跨项重复时抛出。
    """

    formats: tuple[DoclingConverterFormat, ...]

    def __post_init__(self) -> None:
        """校验 capability 的唯一性与非空不变量。

        Args:
            无。

        Returns:
            无。

        Raises:
            ValueError: 格式 tuple 为空，或格式标识、扩展名跨项重复时抛出。
        """

        if not self.formats:
            raise ValueError("Docling 产品 capability 必须至少声明一个格式")
        format_ids = self.format_ids
        if len(frozenset(format_ids)) != len(format_ids):
            raise ValueError("Docling 产品 capability 不能声明重复格式标识")
        product_suffixes = self.product_suffixes
        if len(frozenset(product_suffixes)) != len(product_suffixes):
            raise ValueError("Docling 产品 capability 不能跨格式声明重复扩展名")

    @property
    def format_ids(self) -> tuple[str, ...]:
        """投影稳定有序的产品格式标识。

        Args:
            无。

        Returns:
            与 ``formats`` 顺序一致的格式标识 tuple。

        Raises:
            无。
        """

        return tuple(format_item.format_id for format_item in self.formats)

    @property
    def product_suffixes(self) -> tuple[str, ...]:
        """投影稳定有序且去重的产品转换扩展名。

        Args:
            无。

        Returns:
            按格式声明顺序展平的扩展名 tuple。

        Raises:
            无。
        """

        return tuple(suffix for format_item in self.formats for suffix in format_item.suffixes)

    def accepts_product_suffix(self, suffix: str) -> bool:
        """判断候选扩展名是否属于产品转换能力。

        Args:
            suffix: 待判断的扩展名。

        Returns:
            候选扩展名规范化后属于 capability 时返回 ``True``；空串、空白、仅有前导点
            或不属于 capability 时返回 ``False``。

        Raises:
            无。
        """

        normalized_candidate = suffix.strip().lower()
        if not normalized_candidate or normalized_candidate == ".":
            return False
        return _normalize_docling_product_suffix(normalized_candidate) in self.product_suffixes


DOCLING_CONVERTER_CAPABILITY = DoclingConverterCapability(
    formats=(
        DoclingConverterFormat(format_id="PDF", suffixes=(".pdf",)),
        DoclingConverterFormat(format_id="DOCX", suffixes=(".docx",)),
        DoclingConverterFormat(format_id="PPTX", suffixes=(".pptx",)),
        DoclingConverterFormat(format_id="HTML", suffixes=(".htm", ".html", ".xhtml")),
        DoclingConverterFormat(format_id="MD", suffixes=(".md", ".txt")),
        DoclingConverterFormat(format_id="CSV", suffixes=(".csv",)),
        DoclingConverterFormat(format_id="XLSX", suffixes=(".xlsx",)),
        DoclingConverterFormat(format_id="XML_XBRL", suffixes=(".xbrl", ".xml")),
        DoclingConverterFormat(format_id="JSON_DOCLING", suffixes=(".json",)),
    )
)


class DoclingRuntimeInitializationError(RuntimeError):
    """Docling 运行时初始化错误。"""


class _DoclingTableStructureOptionsProtocol(Protocol):
    """Docling 表格结构选项最小协议。"""

    mode: "TableFormerMode"
    do_cell_matching: bool


class _DoclingPdfPipelineOptionsProtocol(Protocol):
    """Docling PDF pipeline 选项最小协议。"""

    do_ocr: bool
    do_table_structure: bool
    accelerator_options: "AcceleratorOptions | None"
    table_structure_options: _DoclingTableStructureOptionsProtocol


class _DoclingPdfConvertOperation(Protocol[_TResultCovariant]):
    """Docling PDF 转换执行回调协议。"""

    def __call__(self, converter: "DocumentConverter") -> _TResultCovariant:
        """使用已构造的转换器执行一次转换。"""

        ...


@dataclass(frozen=True)
class _DoclingConversionAttempt:
    """一次 Docling PDF 转换尝试的描述。

    每个尝试由 (backend_name, device_name) 二元组唯一标识：

    - ``backend_name``：决定 PDF 解析后端，可选 ``docling-parse`` 或 ``pypdfium2``。
    - ``device_name``：决定加速器设备，与 ``DAYU_DOCLING_DEVICE`` 同空间。
    """

    backend_name: str
    device_name: str


def _normalize_docling_device_name(device_name: str) -> str:
    """规范化并校验 Docling 设备名。

    Args:
        device_name: 候选设备名。

    Returns:
        规范化后的设备名。

    Raises:
        DoclingRuntimeInitializationError: 设备名不在允许列表时抛出。
    """

    normalized_device_name = device_name.strip().lower()
    if normalized_device_name not in _SUPPORTED_DOCLING_DEVICES:
        supported = ", ".join(sorted(_SUPPORTED_DOCLING_DEVICES))
        raise DoclingRuntimeInitializationError(
            f"{DOCLING_DEVICE_ENV} 不支持 {normalized_device_name!r}；允许值: {supported}"
        )
    return normalized_device_name


def _normalize_docling_backend_name(backend_name: str) -> str:
    """规范化并校验 Docling backend 名。

    Args:
        backend_name: 候选 backend 名。

    Returns:
        规范化后的 backend 名。

    Raises:
        DoclingRuntimeInitializationError: backend 名不在允许列表时抛出。
    """

    normalized_backend_name = backend_name.strip().lower()
    if normalized_backend_name not in _SUPPORTED_DOCLING_BACKENDS:
        supported = ", ".join(sorted(_SUPPORTED_DOCLING_BACKENDS))
        raise DoclingRuntimeInitializationError(
            f"不支持的 Docling backend {normalized_backend_name!r}；允许值: {supported}"
        )
    return normalized_backend_name


def _resolve_backend_class(backend_name: str) -> type["AbstractDocumentBackend"]:
    """把 backend 名映射到 Docling 后端实现类。

    集中此处的 lazy import 是为了将 Docling 第三方依赖收口到真源单点，
    便于错误信息统一与依赖缺失的兜底。

    Args:
        backend_name: 已规范化的 backend 名。

    Returns:
        Docling 后端实现类。

    Raises:
        DoclingRuntimeInitializationError: Docling 依赖缺失或 backend 名非法时抛出。
    """

    normalized_backend_name = _normalize_docling_backend_name(backend_name)
    try:
        if normalized_backend_name == _DOCLING_PARSE_BACKEND_NAME:
            from docling.backend.docling_parse_backend import DoclingParseDocumentBackend

            return DoclingParseDocumentBackend
        from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend

        return PyPdfiumDocumentBackend
    except ImportError as exc:  # pragma: no cover - 依赖缺失保护
        raise DoclingRuntimeInitializationError(
            f"Docling 未安装，无法解析 backend {normalized_backend_name!r}"
        ) from exc


def _resolve_docling_allowed_formats(
    capability: DoclingConverterCapability,
) -> list["InputFormat"]:
    """延迟解析并校验产品 capability 对应的 Docling 格式。

    校验是单向的：每个产品声明的扩展名都必须受已安装 Docling 对应格式支持；
    第三方新增的扩展名不会进入产品投影，也不会导致构造失败。

    Args:
        capability: 待解析的不可变产品转换能力。

    Returns:
        与 capability 格式顺序一致、供 ``DocumentConverter`` 使用的格式列表。

    Raises:
        DoclingRuntimeInitializationError: Docling 依赖缺失、格式标识缺失、格式映射缺失，
            或产品扩展名不再受对应格式支持时抛出。
    """

    try:
        from docling.datamodel.base_models import FormatToExtensions, InputFormat
    except ImportError as exc:  # pragma: no cover - 依赖缺失保护
        raise DoclingRuntimeInitializationError("Docling 未安装，无法校验产品转换能力") from exc

    allowed_formats: list[InputFormat] = []
    for format_item in capability.formats:
        try:
            input_format = InputFormat[format_item.format_id]
        except KeyError as exc:
            raise DoclingRuntimeInitializationError(f"Docling 缺少产品声明的格式 {format_item.format_id!r}") from exc
        try:
            installed_extensions = FormatToExtensions[input_format]
        except KeyError as exc:
            raise DoclingRuntimeInitializationError(
                f"Docling 缺少产品格式 {format_item.format_id!r} 的扩展名映射"
            ) from exc
        installed_suffixes = frozenset(
            _normalize_docling_product_suffix(extension) for extension in installed_extensions
        )
        missing_suffixes = tuple(suffix for suffix in format_item.suffixes if suffix not in installed_suffixes)
        if missing_suffixes:
            missing_projection = ", ".join(missing_suffixes)
            raise DoclingRuntimeInitializationError(
                f"Docling 格式 {format_item.format_id!r} 缺少产品扩展名: {missing_projection}"
            )
        allowed_formats.append(input_format)
    return allowed_formats


def resolve_docling_device_name() -> str:
    """解析当前 Docling PDF 转换应使用的设备名。

    Args:
        无。

    Returns:
        Docling 设备名，取值为 ``auto/cpu/cuda/mps/xpu`` 之一。

    Raises:
        DoclingRuntimeInitializationError: 当 ``DAYU_DOCLING_DEVICE`` 配置了不支持的值时抛出。
    """

    configured_device = str(os.environ.get(DOCLING_DEVICE_ENV, "") or "").strip()
    if configured_device:
        return _normalize_docling_device_name(configured_device)

    return _AUTO_DEVICE_NAME


def _is_windows_platform() -> bool:
    """判断当前进程是否运行在 Windows 平台。

    Args:
        无。

    Returns:
        True 表示当前为 Windows，False 表示 macOS / Linux 等其它平台。

    Raises:
        无。
    """

    return sys.platform == _WINDOWS_PLATFORM_NAME


def _is_explicit_accelerator_device(device_name: str) -> bool:
    """判断设备名是否指向显式加速器设备。

    Args:
        device_name: 已规范化的 Docling 设备名。

    Returns:
        True 表示设备名是显式加速器，False 表示 ``auto`` 或 ``cpu``。

    Raises:
        无。
    """

    return device_name in _ACCELERATOR_DEVICE_NAMES


def _is_windows_cuda_available() -> bool:
    """探测当前 Windows 运行环境是否可用 CUDA。

    此处 lazy import `torch` 是为了把硬件探测成本限制在 Windows auto 设备
    的策略分支内；Docling 运行时本身已经依赖 torch，探测失败时保守视为
    CUDA 不可用。

    Args:
        无。

    Returns:
        True 表示 CUDA 当前可用，False 表示不可用或探测失败。

    Raises:
        无。
    """

    try:
        import torch

        return bool(torch.cuda.is_available())
    except Exception:
        return False


def _should_prefer_docling_parse_first_on_windows(resolved_device_name: str) -> bool:
    """判断 Windows 平台是否应优先使用 docling-parse。

    Args:
        resolved_device_name: 已规范化的 Docling 设备名。

    Returns:
        True 表示优先使用 ``docling-parse``，False 表示优先使用 ``pypdfium2``。

    Raises:
        无。
    """

    if _is_explicit_accelerator_device(resolved_device_name):
        return True
    return resolved_device_name == _AUTO_DEVICE_NAME and _is_windows_cuda_available()


def _plan_conversion_attempts(resolved_device_name: str) -> list[_DoclingConversionAttempt]:
    """按二维回退策略生成 Docling 转换尝试链。

    Windows 上 docling-parse 后端在某些 PDF 上会在 C++ 层抛 ``std::bad_alloc``，
    且对 mbcs 路径编码也存在已知 bug；为减少 CPU/auto 路径的首次失败概率
    与日志刷屏，Windows 在未显式选择加速器设备且 CUDA 不可用时把
    ``pypdfium2`` 提到首位。Windows 显式加速器设备、Windows auto 且 CUDA
    可用、以及其它平台保持 ``docling-parse`` 优先，以维持既有解析质量。

    Args:
        resolved_device_name: 已规范化的 Docling 设备名。

    Returns:
        有序的尝试链，至少包含一项。

    Raises:
        无。
    """

    prefers_pypdfium2_first = _is_windows_platform() and not (
        _should_prefer_docling_parse_first_on_windows(resolved_device_name)
    )
    if prefers_pypdfium2_first:
        attempts: list[_DoclingConversionAttempt] = [
            _DoclingConversionAttempt(
                backend_name=_PYPDFIUM2_BACKEND_NAME,
                device_name=resolved_device_name,
            ),
            _DoclingConversionAttempt(
                backend_name=_DOCLING_PARSE_BACKEND_NAME,
                device_name=resolved_device_name,
            ),
        ]
    else:
        attempts = [
            _DoclingConversionAttempt(
                backend_name=_DOCLING_PARSE_BACKEND_NAME,
                device_name=resolved_device_name,
            ),
            _DoclingConversionAttempt(
                backend_name=_PYPDFIUM2_BACKEND_NAME,
                device_name=resolved_device_name,
            ),
        ]
    if resolved_device_name == _AUTO_DEVICE_NAME:
        attempts.append(
            _DoclingConversionAttempt(
                backend_name=_DOCLING_PARSE_BACKEND_NAME,
                device_name=_CPU_DEVICE_NAME,
            )
        )
    return attempts


def build_docling_pdf_converter(
    *,
    do_ocr: bool = True,
    do_table_structure: bool = True,
    table_mode: str = _TABLE_MODE_ACCURATE,
    do_cell_matching: bool = True,
    device_name: str | None = None,
    backend_name: str = _DOCLING_PARSE_BACKEND_NAME,
) -> "DocumentConverter":
    """构造带稳定设备与 backend 策略的 Docling 转换器。

    Dayu 只为 PDF 注入受控的 pipeline 与 backend 配置。其余允许格式不在本函数中
    重建第三方默认配置，而由 Docling ``DocumentConverter`` constructor 按
    ``allowed_formats`` 生成当前版本的默认 format options。

    Args:
        do_ocr: 是否开启 OCR。
        do_table_structure: 是否开启表格结构识别。
        table_mode: 表格结构模式，仅支持 ``accurate`` 或 ``fast``。
        do_cell_matching: 是否开启表格单元格匹配。
        device_name: 显式设备名；为空时按 `resolve_docling_device_name()` 解析。
        backend_name: 显式 PDF backend 名；默认 ``docling-parse``。

    Returns:
        配置完成的 Docling `DocumentConverter`。

    Raises:
        DoclingRuntimeInitializationError: Docling 依赖未安装、设备或 backend 配置非法时抛出。
        ValueError: `table_mode` 非法时抛出。
    """

    pipeline_options = build_docling_pdf_pipeline_options(
        do_ocr=do_ocr,
        do_table_structure=do_table_structure,
        table_mode=table_mode,
        do_cell_matching=do_cell_matching,
        device_name=device_name,
    )

    backend_class = _resolve_backend_class(backend_name)
    allowed_formats = _resolve_docling_allowed_formats(DOCLING_CONVERTER_CAPABILITY)

    try:
        from docling.datamodel.base_models import InputFormat
        from docling.document_converter import DocumentConverter, PdfFormatOption
    except ImportError as exc:  # pragma: no cover - 依赖缺失保护
        raise DoclingRuntimeInitializationError("Docling 未安装，无法构造 PDF 转换器") from exc

    # 非 PDF 格式故意不传 option：默认值由 Docling constructor 拥有，Dayu 不复制第三方默认表。
    return DocumentConverter(
        allowed_formats=allowed_formats,
        format_options={
            InputFormat.PDF: PdfFormatOption(
                pipeline_options=cast("PipelineOptions", pipeline_options),
                backend=backend_class,
            ),
        },
    )


def build_docling_pdf_pipeline_options(
    *,
    do_ocr: bool = True,
    do_table_structure: bool = True,
    table_mode: str = _TABLE_MODE_ACCURATE,
    do_cell_matching: bool = True,
    device_name: str | None = None,
) -> _DoclingPdfPipelineOptionsProtocol:
    """构造带稳定设备策略的 Docling PDF pipeline 选项。

    Args:
        do_ocr: 是否开启 OCR。
        do_table_structure: 是否开启表格结构识别。
        table_mode: 表格结构模式，仅支持 ``accurate`` 或 ``fast``。
        do_cell_matching: 是否开启表格单元格匹配。
        device_name: 显式设备名；为空时按 `resolve_docling_device_name()` 解析。

    Returns:
        配置完成的 Docling PDF pipeline 选项对象。

    Raises:
        DoclingRuntimeInitializationError: Docling 依赖未安装或设备环境变量非法时抛出。
        ValueError: `table_mode` 非法时抛出。
    """

    normalized_table_mode = table_mode.strip().lower()
    if normalized_table_mode not in {_TABLE_MODE_ACCURATE, _TABLE_MODE_FAST}:
        raise ValueError(f"不支持的 Docling table_mode: {table_mode}")

    try:
        from docling.datamodel.accelerator_options import (
            AcceleratorOptions,
            AcceleratorDevice,
        )
        from docling.datamodel.pipeline_options import (
            PdfPipelineOptions,
            TableFormerMode,
        )
    except ImportError as exc:  # pragma: no cover - 依赖缺失保护
        raise DoclingRuntimeInitializationError("Docling 未安装，无法构造 PDF pipeline 选项") from exc

    normalized_device_name = (
        resolve_docling_device_name() if device_name is None else _normalize_docling_device_name(device_name)
    )

    pipeline_options = cast(_DoclingPdfPipelineOptionsProtocol, PdfPipelineOptions())
    pipeline_options.do_ocr = do_ocr
    pipeline_options.do_table_structure = do_table_structure
    pipeline_options.accelerator_options = AcceleratorOptions(device=AcceleratorDevice(normalized_device_name))

    if do_table_structure:
        table_structure_options = cast(
            _DoclingTableStructureOptionsProtocol,
            pipeline_options.table_structure_options,
        )
        table_structure_options.mode = (
            TableFormerMode.ACCURATE if normalized_table_mode == _TABLE_MODE_ACCURATE else TableFormerMode.FAST
        )
        table_structure_options.do_cell_matching = do_cell_matching

    return pipeline_options


def _build_attempt_converter(
    attempt: _DoclingConversionAttempt,
    *,
    do_ocr: bool,
    do_table_structure: bool,
    table_mode: str,
    do_cell_matching: bool,
    attempt_index: int,
    total_attempts: int,
) -> "DocumentConverter":
    """为指定尝试构造 Docling 转换器，并把初始化异常包装成统一类型。

    Args:
        attempt: 当前尝试描述。
        do_ocr: 是否开启 OCR。
        do_table_structure: 是否开启表格结构识别。
        table_mode: 表格结构模式。
        do_cell_matching: 是否开启表格单元格匹配。
        attempt_index: 当前尝试在尝试链中的 0 基序号。
        total_attempts: 尝试链总长度。

    Returns:
        Docling 转换器实例。

    Raises:
        DoclingRuntimeInitializationError: 初始化失败时抛出。
    """

    try:
        return build_docling_pdf_converter(
            do_ocr=do_ocr,
            do_table_structure=do_table_structure,
            table_mode=table_mode,
            do_cell_matching=do_cell_matching,
            device_name=attempt.device_name,
            backend_name=attempt.backend_name,
        )
    except DoclingRuntimeInitializationError:
        raise
    except Exception as exc:
        raise DoclingRuntimeInitializationError(
            f"Docling 转换器初始化失败 (attempt {attempt_index + 1}/{total_attempts}: "
            f"backend={attempt.backend_name}, device={attempt.device_name}): {exc}"
        ) from exc


def run_docling_pdf_conversion(
    convert_operation: _DoclingPdfConvertOperation[_TResult],
    *,
    do_ocr: bool = True,
    do_table_structure: bool = True,
    table_mode: str = _TABLE_MODE_ACCURATE,
    do_cell_matching: bool = True,
) -> _TResult:
    """执行带二维（backend × device）回退的 Docling PDF 转换。

    尝试链由 `_plan_conversion_attempts` 给出，命中即返回；全链失败时抛出
    最后一次异常，并以首次失败作为 ``__cause__`` 保留首因。

    Args:
        convert_operation: 接收 `DocumentConverter` 并执行具体转换的回调。
        do_ocr: 是否开启 OCR。
        do_table_structure: 是否开启表格结构识别。
        table_mode: 表格结构模式，仅支持 ``accurate`` 或 ``fast``。
        do_cell_matching: 是否开启表格单元格匹配。

    Returns:
        由 `convert_operation` 返回的转换结果。

    Raises:
        DoclingRuntimeInitializationError: Docling 依赖缺失或设备配置非法时抛出。
        ValueError: `table_mode` 非法时抛出。
    """

    resolved_device_name = resolve_docling_device_name()
    attempts = _plan_conversion_attempts(resolved_device_name)
    total_attempts = len(attempts)
    _LOGGER.debug(
        (
            "Docling 转换尝试链装配完成: "
            f"platform={'windows' if _is_windows_platform() else 'unix'} "
            f"resolved_device={resolved_device_name} "
            f"total_attempts={total_attempts} "
            f"chain={[(a.backend_name, a.device_name) for a in attempts]}"
        ),
    )
    first_failure: Exception | None = None
    last_failure: Exception | None = None
    for attempt_index, attempt in enumerate(attempts):
        _LOGGER.debug(
            (
                "Docling 转换尝试启动: "
                f"attempt={attempt_index + 1}/{total_attempts} "
                f"backend={attempt.backend_name} device={attempt.device_name}"
            ),
        )
        converter = _build_attempt_converter(
            attempt,
            do_ocr=do_ocr,
            do_table_structure=do_table_structure,
            table_mode=table_mode,
            do_cell_matching=do_cell_matching,
            attempt_index=attempt_index,
            total_attempts=total_attempts,
        )
        try:
            result = convert_operation(converter)
        except Exception as exc:
            last_failure = exc
            if first_failure is None:
                first_failure = exc
            if attempt_index + 1 < total_attempts:
                next_attempt = attempts[attempt_index + 1]
                _LOGGER.warning(
                    (
                        "Docling 转换失败，准备按尝试链回退: "
                        f"attempt={attempt_index + 1}/{total_attempts} "
                        f"failed_backend={attempt.backend_name} "
                        f"failed_device={attempt.device_name} "
                        f"next_backend={next_attempt.backend_name} "
                        f"next_device={next_attempt.device_name} "
                        f"error_type={type(exc).__name__} error={exc}"
                    ),
                )
                continue
        else:
            _LOGGER.debug(
                (
                    "Docling 转换尝试成功: "
                    f"attempt={attempt_index + 1}/{total_attempts} "
                    f"backend={attempt.backend_name} device={attempt.device_name}"
                ),
            )
            return result
    # 全链失败：保留首次失败为 __cause__，便于排查首因。
    assert last_failure is not None
    if first_failure is not None and first_failure is not last_failure:
        raise last_failure from first_failure
    raise last_failure


def _build_docling_document_stream(raw_bytes: bytes, *, stream_name: str) -> "DocumentStream":
    """构造 Docling ``DocumentStream``。

    Args:
        raw_bytes: 原始字节内容。
        stream_name: 流名称，决定 Docling 解析模式（按扩展名判别）。

    Returns:
        构造完成的 Docling ``DocumentStream`` 对象。

    Raises:
        DoclingRuntimeInitializationError: Docling 依赖缺失时抛出。
    """

    from io import BytesIO

    try:
        from docling.datamodel.base_models import DocumentStream
    except ImportError as exc:  # pragma: no cover - 依赖缺失保护
        raise DoclingRuntimeInitializationError("Docling 未安装，无法构造 DocumentStream") from exc

    return DocumentStream(name=stream_name, stream=BytesIO(raw_bytes))


def convert_pdf_bytes_with_docling(
    raw_bytes: bytes,
    *,
    stream_name: str,
    do_ocr: bool = True,
    do_table_structure: bool = True,
    table_mode: str = _TABLE_MODE_ACCURATE,
    do_cell_matching: bool = True,
) -> "ConversionResult":
    """以字节流形式调用 Docling，规避 Windows 非 ASCII 路径编码问题。

    Docling 在 Windows 上把 ``Path`` 输入按 mbcs（cp936）编码后传给
    docling-parse C++ 后端，导致合法文档被判 ``not valid``。本函数把字节流
    封装成 ``DocumentStream`` 直接喂给 Docling，绕开文件系统路径编码层。
    每次回退尝试都从同一份不可变原始字节构造独立流，避免前一档转换器
    关闭输入后破坏后续尝试。

    Args:
        raw_bytes: PDF 原始字节内容。
        stream_name: 流名称，建议直接传文件名以保留扩展名。
        do_ocr: 是否开启 OCR。
        do_table_structure: 是否开启表格结构识别。
        table_mode: 表格结构模式，仅支持 ``accurate`` 或 ``fast``。
        do_cell_matching: 是否开启表格单元格匹配。

    Returns:
        Docling 转换结果对象。

    Raises:
        DoclingRuntimeInitializationError: Docling 依赖缺失或装配失败时抛出。
        ValueError: ``table_mode`` 非法时抛出。
    """

    return run_docling_pdf_conversion(
        lambda converter: converter.convert(_build_docling_document_stream(raw_bytes, stream_name=stream_name)),
        do_ocr=do_ocr,
        do_table_structure=do_table_structure,
        table_mode=table_mode,
        do_cell_matching=do_cell_matching,
    )
