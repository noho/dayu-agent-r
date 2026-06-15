"""Fins 批量上传计划生成。

本模块只负责从用户提供的本地目录生成结构化上传计划，不启动 ingestion
job，不读取 Fins storage，也不输出 shell 文本。调用方可以把计划渲染成 CLI
脚本、GUI preview 或其它用户可见格式。
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

BatchUploadCommandName = Literal["upload_filing", "upload_material"]
BatchUploadAction = Literal["create", "update"]

FINS_UPLOAD_FILE_SUFFIXES: Final[frozenset[str]] = frozenset(
    {
        ".csv",
        ".docx",
        ".htm",
        ".html",
        ".json",
        ".md",
        ".pdf",
        ".txt",
        ".xbrl",
        ".xhtml",
        ".xls",
        ".xlsx",
        ".xml",
        ".zip",
    }
)
_DEFAULT_FILING_FORMS: Final[tuple[str, ...]] = (
    "10-K",
    "10-Q",
    "8-K",
    "20-F",
    "6-K",
    "DEF 14A",
    "SC 13D",
    "SC 13G",
)
_FORM_TOKEN_SEPARATOR_PATTERN: Final[re.Pattern[str]] = re.compile(r"[^A-Z0-9]+")


class UploadBatchPlanUsageError(ValueError):
    """批量上传计划请求的用户输入错误。"""


class UploadBatchPlanEmptyError(ValueError):
    """源目录中没有可识别上传文件。"""


@dataclass(frozen=True, slots=True)
class UploadBatchPlanRequest:
    """批量上传计划请求。

    Attributes:
        ticker: 上传命令使用的 canonical ticker 文本。
        source_dir: 待扫描的本地源目录。
        action: 生成上传命令使用的动作。
        recursive: 是否递归扫描子目录。
        fiscal_year: 可选财政年度。
        fiscal_period: 可选财政期间。
        amended: 是否标记为修订文件。
        filing_date: 可选 filing 日期。
        report_date: 可选报告日期。
        company_name: 可选公司名称。
        material_forms: 用于识别 material 文件并写入 material 命令的表单类型。
    """

    ticker: str
    source_dir: Path
    action: BatchUploadAction
    recursive: bool = False
    fiscal_year: int | None = None
    fiscal_period: str | None = None
    amended: bool = False
    filing_date: str | None = None
    report_date: str | None = None
    company_name: str | None = None
    material_forms: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class UploadBatchPlanEntry:
    """单条结构化上传命令计划。

    Attributes:
        command_name: 目标 CLI 命令名。
        ticker: 上传命令使用的 ticker。
        action: 上传动作。
        files: 当前命令携带的本地文件路径。
        fiscal_year: 可选财政年度。
        fiscal_period: 可选财政期间。
        amended: 是否标记为修订文件。
        filing_date: 可选 filing 日期。
        report_date: 可选报告日期。
        company_name: 可选公司名称。
        form_type: material 命令的关联表单类型；filing 命令为空。
        material_name: material 命令的材料名称；filing 命令为空。
    """

    command_name: BatchUploadCommandName
    ticker: str
    action: BatchUploadAction
    files: tuple[Path, ...]
    fiscal_year: int | None = None
    fiscal_period: str | None = None
    amended: bool = False
    filing_date: str | None = None
    report_date: str | None = None
    company_name: str | None = None
    form_type: str | None = None
    material_name: str | None = None


@dataclass(frozen=True, slots=True)
class UploadBatchPlanResult:
    """批量上传计划生成结果。

    Attributes:
        source_dir: 实际扫描的绝对源目录。
        recursive: 是否递归扫描。
        entries: 结构化上传命令条目。
        skipped_files: 扩展名可接受但无法识别业务类型的文件。
    """

    source_dir: Path
    recursive: bool
    entries: tuple[UploadBatchPlanEntry, ...]
    skipped_files: tuple[Path, ...]


def generate_upload_batch_plan(
    request: UploadBatchPlanRequest,
) -> UploadBatchPlanResult:
    """扫描本地目录并生成结构化批量上传计划。

    :param request: 批量上传计划请求。
    :returns: 批量上传计划结果。
    :raises UploadBatchPlanUsageError: ticker、source dir 或 material forms 非法时抛出。
    :raises UploadBatchPlanEmptyError: 没有可识别上传文件时抛出。
    :raises KeyboardInterrupt: 扫描阶段收到用户中断时透传。
    """

    ticker = request.ticker.strip()
    if ticker == "":
        raise UploadBatchPlanUsageError("ticker must not be empty")
    source_dir = request.source_dir.expanduser().resolve(strict=False)
    if not source_dir.exists():
        raise UploadBatchPlanUsageError(f"source dir does not exist: {source_dir}")
    if not source_dir.is_dir():
        raise UploadBatchPlanUsageError(f"source path is not a directory: {source_dir}")
    material_forms = _normalized_forms(request.material_forms, field_name="material_forms")
    filing_patterns = _form_patterns(_DEFAULT_FILING_FORMS)
    material_patterns = _form_patterns(material_forms)

    entries: list[UploadBatchPlanEntry] = []
    skipped_files: list[Path] = []
    for file_path in _iter_source_files(source_dir, recursive=request.recursive):
        if file_path.suffix.lower() not in FINS_UPLOAD_FILE_SUFFIXES:
            continue
        material_form = _matched_form(file_path, material_patterns)
        if material_form is not None:
            entries.append(
                _material_entry(
                    request=request,
                    source_file=file_path,
                    ticker=ticker,
                    form_type=material_form,
                )
            )
            continue
        filing_form = _matched_form(file_path, filing_patterns)
        if filing_form is not None:
            entries.append(
                _filing_entry(request=request, source_file=file_path, ticker=ticker)
            )
            continue
        skipped_files.append(file_path)

    if not entries:
        raise UploadBatchPlanEmptyError(
            f"no recognizable filing or material files under {source_dir}"
        )
    return UploadBatchPlanResult(
        source_dir=source_dir,
        recursive=request.recursive,
        entries=tuple(entries),
        skipped_files=tuple(skipped_files),
    )


def _iter_source_files(source_dir: Path, *, recursive: bool) -> Iterable[Path]:
    """按稳定顺序枚举源目录普通文件。

    :param source_dir: 已验证存在的源目录。
    :param recursive: 是否递归枚举。
    :returns: 源目录中的普通文件迭代器。
    :raises KeyboardInterrupt: 目录遍历期间收到用户中断时透传。
    """

    candidates = source_dir.rglob("*") if recursive else source_dir.iterdir()
    for path in sorted(candidates):
        if path.is_file():
            yield path.resolve(strict=False)


def _filing_entry(
    *,
    request: UploadBatchPlanRequest,
    source_file: Path,
    ticker: str,
) -> UploadBatchPlanEntry:
    """构造 filing 上传计划条目。

    :param request: 批量上传计划请求。
    :param source_file: 当前识别出的源文件。
    :param ticker: 已规范化的 ticker。
    :returns: filing 上传计划条目。
    :raises Exception: 不主动抛出异常。
    """

    return UploadBatchPlanEntry(
        command_name="upload_filing",
        ticker=ticker,
        action=request.action,
        files=(source_file,),
        fiscal_year=request.fiscal_year,
        fiscal_period=_optional_stripped_text(request.fiscal_period),
        amended=request.amended,
        filing_date=_optional_stripped_text(request.filing_date),
        report_date=_optional_stripped_text(request.report_date),
        company_name=_optional_stripped_text(request.company_name),
    )


def _material_entry(
    *,
    request: UploadBatchPlanRequest,
    source_file: Path,
    ticker: str,
    form_type: str,
) -> UploadBatchPlanEntry:
    """构造 material 上传计划条目。

    :param request: 批量上传计划请求。
    :param source_file: 当前识别出的源文件。
    :param ticker: 已规范化的 ticker。
    :param form_type: 匹配到的 material form。
    :returns: material 上传计划条目。
    :raises Exception: 不主动抛出异常。
    """

    return UploadBatchPlanEntry(
        command_name="upload_material",
        ticker=ticker,
        action=request.action,
        files=(source_file,),
        fiscal_year=request.fiscal_year,
        fiscal_period=_optional_stripped_text(request.fiscal_period),
        amended=request.amended,
        filing_date=_optional_stripped_text(request.filing_date),
        report_date=_optional_stripped_text(request.report_date),
        company_name=_optional_stripped_text(request.company_name),
        form_type=form_type,
        material_name=_material_name_from_path(source_file),
    )


def _normalized_forms(values: tuple[str, ...], *, field_name: str) -> tuple[str, ...]:
    """规范化表单类型列表。

    :param values: 原始表单类型。
    :param field_name: 错误消息使用的字段名。
    :returns: 去重后的表单类型，保持首次出现顺序。
    :raises UploadBatchPlanUsageError: 任一表单为空时抛出。
    """

    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        stripped = value.strip()
        if stripped == "":
            raise UploadBatchPlanUsageError(f"{field_name} must not contain empty item")
        key = _normalized_form_token(stripped)
        if key not in seen:
            normalized.append(stripped)
            seen.add(key)
    return tuple(normalized)


def _form_patterns(forms: tuple[str, ...]) -> tuple[tuple[str, str], ...]:
    """把表单类型转换为可匹配文件名的 token pattern。

    :param forms: 已规范化表单类型。
    :returns: ``(原始表单, 规范 token)`` 元组。
    :raises Exception: 不主动抛出异常。
    """

    return tuple((form, _normalized_form_token(form)) for form in forms)


def _matched_form(
    file_path: Path,
    patterns: tuple[tuple[str, str], ...],
) -> str | None:
    """识别文件名中包含的表单类型。

    :param file_path: 待识别文件路径。
    :param patterns: 可匹配表单 token。
    :returns: 匹配到的原始表单类型；未匹配时返回 ``None``。
    :raises Exception: 不主动抛出异常。
    """

    filename_token = _normalized_form_token(file_path.stem)
    for form, pattern in patterns:
        if pattern in filename_token:
            return form
    return None


def _normalized_form_token(value: str) -> str:
    """把表单或文件名规范为只含大写字母数字的 token。

    :param value: 原始文本。
    :returns: 规范化 token。
    :raises Exception: 不主动抛出异常。
    """

    return _FORM_TOKEN_SEPARATOR_PATTERN.sub("", value.upper())


def _material_name_from_path(path: Path) -> str:
    """从文件名生成 material name。

    :param path: material 文件路径。
    :returns: 去除扩展名后的文件名。
    :raises Exception: 不主动抛出异常。
    """

    return path.stem


def _optional_stripped_text(value: str | None) -> str | None:
    """规范化可选文本。

    :param value: 原始文本。
    :returns: 去除首尾空白后的文本；空白或 ``None`` 返回 ``None``。
    :raises Exception: 不主动抛出异常。
    """

    if value is None:
        return None
    stripped = value.strip()
    if stripped == "":
        return None
    return stripped


__all__: tuple[str, ...] = (
    "BatchUploadAction",
    "BatchUploadCommandName",
    "FINS_UPLOAD_FILE_SUFFIXES",
    "UploadBatchPlanEmptyError",
    "UploadBatchPlanEntry",
    "UploadBatchPlanRequest",
    "UploadBatchPlanResult",
    "UploadBatchPlanUsageError",
    "generate_upload_batch_plan",
)
