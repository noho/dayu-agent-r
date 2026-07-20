"""Fins 批量上传领域计划生成。

本模块是本地批量上传的业务语义 owner：负责安全扫描源目录、识别财期与
material、执行同期去重和数量限制，并输出不可变 typed facts。它不依赖 CLI，
不构造 argv，不渲染 shell，也不启动上传任务。
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal, cast

from dayu.fins.domain.filing_semantics import (
    FiscalPeriod,
    normalize_fiscal_period,
)

BatchUploadAction = Literal["auto", "create", "update"]
MaterialFormType = Literal[
    "FINANCIAL_STATEMENTS",
    "EARNINGS_CALL",
    "EARNINGS_PRESENTATION",
]
UploadBatchSkipReasonCode = Literal[
    "unsupported_suffix",
    "unsafe_symlink",
    "resolved_escape",
    "not_regular_file",
    "missing_fiscal_metadata",
    "duplicate_period",
    "annual_cap",
    "periodic_older_year",
    "periodic_cap",
    "material_cap",
]

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

_FISCAL_YEAR_PATTERN: Final[re.Pattern[str]] = re.compile(r"(?P<year>20\d{2})")
_Q1_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"(?:Q1|(?<!\d)1Q|第一季度|一季度)", re.IGNORECASE
)
_Q2_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"(?:Q2|(?<!\d)2Q|第二季度|二季度)", re.IGNORECASE
)
_Q3_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"(?:Q3|(?<!\d)3Q|第三季度|三季度)", re.IGNORECASE
)
_Q4_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"(?:Q4|(?<!\d)4Q|第四季度|四季度)", re.IGNORECASE
)
_H1_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"(?:H1|HALF[-_ ]?YEAR|半年度|半年报|中报|中期报告)", re.IGNORECASE
)
_FY_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"(?:FY|ANNUAL|年度报告|年报)", re.IGNORECASE
)
_Q4_QUARTERLY_MARKER: Final[str] = "季报"
_STRUCTURED_DIRECTORY_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^(?P<year>20\d{2})(?P<period>Q[1-4]|H1)?$", re.IGNORECASE
)
_MATERIAL_PREFIX_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^(20\d{2}(?:Q[1-4]|H1|FY)?)\s*", re.IGNORECASE
)

_FINANCIAL_STATEMENTS_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"财务报表", re.IGNORECASE
)
_EARNINGS_CALL_PATTERN: Final[re.Pattern[str]] = re.compile(
    (
        r"电话会议|"
        r"(?:财报|业绩|业绩会|业绩说明会|业绩发布会).{0,8}会议纪要|"
        r"Earnings.{0,5}Call|Transcript|Conference.{0,5}Call"
    ),
    re.IGNORECASE,
)
_EARNINGS_PRESENTATION_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"演示|Slide|Presentation|Investor.{0,10}Day|Deck", re.IGNORECASE
)
_MATERIAL_ROUTING_TABLE: Final[
    tuple[tuple[re.Pattern[str], MaterialFormType], ...]
] = (
    (_FINANCIAL_STATEMENTS_PATTERN, "FINANCIAL_STATEMENTS"),
    (_EARNINGS_CALL_PATTERN, "EARNINGS_CALL"),
    (_EARNINGS_PRESENTATION_PATTERN, "EARNINGS_PRESENTATION"),
)
_MATERIAL_FORM_TYPES: Final[frozenset[str]] = frozenset(
    form_type for _, form_type in _MATERIAL_ROUTING_TABLE
)

_PRIORITY_LONG_SCOPE_REPORT: Final[re.Pattern[str]] = re.compile(
    r"年度报告|中期报告|Annual.{0,5}Report|Interim.{0,5}Report|半年.{0,3}报告|年报|中报",
    re.IGNORECASE,
)
_PRIORITY_QUARTERLY_REPORT: Final[re.Pattern[str]] = re.compile(
    r"季报|季度.{0,5}报告|Quarterly.{0,5}Report", re.IGNORECASE
)
_PRIORITY_GENERIC_REPORT: Final[re.Pattern[str]] = re.compile(r"报告", re.IGNORECASE)
_PRIORITY_ANNOUNCEMENT: Final[re.Pattern[str]] = re.compile(
    r"公告|通告|Announcement", re.IGNORECASE
)
_PRIORITY_SUPPLEMENTARY: Final[re.Pattern[str]] = re.compile(
    r"演示|Slide|Presentation|Deck|新闻|News|简报|摘要|Summary",
    re.IGNORECASE,
)

_ANNUAL_CAP: Final[int] = 5
_PERIODIC_CAP: Final[int] = 6
_PRESENTATION_CAP: Final[int] = 6
_PERIOD_ORDER: Final[dict[FiscalPeriod, int]] = {
    "Q1": 1,
    "H1": 2,
    "Q2": 3,
    "Q3": 4,
    "Q4": 5,
    "FY": 6,
}


class UploadBatchPlanUsageError(ValueError):
    """批量上传计划请求的用户输入错误。"""


@dataclass(frozen=True, slots=True)
class UploadBatchSkippedEntry:
    """Fins owner 判定不能进入上传计划的文件事实。

    Attributes:
        path: 被跳过的 lexical 绝对路径。
        reason_code: 稳定的 typed 跳过原因。
        reason: 面向用户的业务可读原因。
    """

    path: Path
    reason_code: UploadBatchSkipReasonCode
    reason: str


class UploadBatchPlanEmptyError(ValueError):
    """源目录没有可上传条目，同时保留 owner 产生的 skipped evidence。"""

    skipped_entries: tuple[UploadBatchSkippedEntry, ...]

    def __init__(
        self,
        *,
        source_dir: Path,
        skipped_entries: tuple[UploadBatchSkippedEntry, ...],
    ) -> None:
        """初始化空计划错误。

        :param source_dir: 已验证的源目录。
        :param skipped_entries: Fins owner 产生的跳过事实。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        super().__init__(f"no recognizable filing or material files under {source_dir}")
        self.skipped_entries = skipped_entries


@dataclass(frozen=True, slots=True)
class UploadBatchPlanRequest:
    """批量上传计划请求。

    Attributes:
        ticker: canonical ticker。
        aliases: 已规范化且不含 canonical 的 ticker aliases。
        source_dir: 待扫描目录。
        action: 每条生成命令的上传动作。
        recursive: 是否显式递归扫描。
        fiscal_year: 可选显式财政年度，逐字段覆盖推断值。
        fiscal_period: 可选显式财政期间，逐字段覆盖推断值。
        amended: 是否为修订文档。
        filing_date: 可选 filing 日期。
        report_date: 可选报告日期。
        company_name: 可选公司名称。
        overwrite: 是否允许 direct upload 覆盖已有存储文档。
        material_form: 可选单一 material form 候选，由 Fins owner 验证后仅作用于已路由 material。
    """

    ticker: str
    source_dir: Path
    action: BatchUploadAction = "auto"
    aliases: tuple[str, ...] = ()
    recursive: bool = False
    fiscal_year: int | None = None
    fiscal_period: FiscalPeriod | None = None
    amended: bool = False
    filing_date: str | None = None
    report_date: str | None = None
    company_name: str | None = None
    overwrite: bool = False
    material_form: str | None = None


@dataclass(frozen=True, slots=True)
class UploadBatchFilingEntry:
    """可直接机械投影为 ``upload_filing`` 的 typed fact。"""

    file: Path
    ticker: str
    aliases: tuple[str, ...]
    action: BatchUploadAction
    fiscal_year: int
    fiscal_period: FiscalPeriod
    amended: bool
    filing_date: str | None
    report_date: str | None
    company_name: str | None
    overwrite: bool


@dataclass(frozen=True, slots=True)
class UploadBatchMaterialEntry:
    """可直接机械投影为 ``upload_material`` 的 typed fact。"""

    file: Path
    ticker: str
    aliases: tuple[str, ...]
    action: BatchUploadAction
    form_type: MaterialFormType
    material_name: str
    fiscal_year: int | None
    fiscal_period: FiscalPeriod | None
    amended: bool
    filing_date: str | None
    report_date: str | None
    company_name: str | None
    overwrite: bool


@dataclass(frozen=True, slots=True)
class UploadBatchPlan:
    """Fins owner 生成的完整不可变批量上传计划。"""

    source_dir: Path
    recursive: bool
    recognized_entries: tuple[UploadBatchFilingEntry, ...]
    material_entries: tuple[UploadBatchMaterialEntry, ...]
    skipped_entries: tuple[UploadBatchSkippedEntry, ...]


@dataclass(frozen=True, slots=True)
class _DiscoveredFile:
    """安全扫描后可供领域识别的内部文件事实。"""

    path: Path
    relative_path: str


def generate_upload_batch_plan(request: UploadBatchPlanRequest) -> UploadBatchPlan:
    """扫描目录并生成 OLD-aligned typed 上传计划。

    :param request: 批量上传计划请求。
    :returns: recognized/material/skipped 三分计划。
    :raises UploadBatchPlanUsageError: 请求字段或 source root 非法时抛出。
    :raises UploadBatchPlanEmptyError: recognized/material 均为空时抛出。
    :raises OSError: 文件系统扫描失败时透传。
    :raises KeyboardInterrupt: 扫描被用户中断时透传。
    """

    ticker = request.ticker.strip()
    if ticker == "":
        raise UploadBatchPlanUsageError("ticker must not be empty")
    action = _validated_action(request.action)
    explicit_period = _validated_explicit_period(request.fiscal_period)
    material_form = _validated_material_form(request.material_form)
    source_dir = _lexical_absolute(request.source_dir)
    if source_dir.is_symlink():
        raise UploadBatchPlanUsageError(f"source root must not be a symlink: {source_dir}")
    if not source_dir.exists():
        raise UploadBatchPlanUsageError(f"source dir does not exist: {source_dir}")
    if not source_dir.is_dir():
        raise UploadBatchPlanUsageError(f"source path is not a directory: {source_dir}")
    resolved_source_dir = source_dir.resolve(strict=True)
    effective_recursive = request.recursive or _has_structured_top_level_directory(
        source_dir
    )
    discovered, skipped = _discover_source_files(
        source_dir=source_dir,
        resolved_source_dir=resolved_source_dir,
        recursive=effective_recursive,
    )

    filing_candidates: list[tuple[UploadBatchFilingEntry, str]] = []
    material_candidates: list[tuple[UploadBatchMaterialEntry, str]] = []
    for discovered_file in discovered:
        inferred_year, inferred_period = _infer_fiscal_fields(discovered_file.path)
        final_year = request.fiscal_year if request.fiscal_year is not None else inferred_year
        final_period = explicit_period if explicit_period is not None else inferred_period
        routed_material_form = _match_material_form(discovered_file.path.name)
        if routed_material_form is not None:
            material_candidates.append(
                (
                    _build_material_entry(
                        request=request,
                        source_file=discovered_file.path,
                        ticker=ticker,
                        action=action,
                        form_type=(
                            material_form
                            if material_form is not None
                            else routed_material_form
                        ),
                        fiscal_year=final_year,
                        fiscal_period=final_period,
                    ),
                    discovered_file.relative_path,
                )
            )
            continue
        if final_year is None or final_period is None:
            skipped.append(
                _skipped(
                    discovered_file.path,
                    "missing_fiscal_metadata",
                    "无法从完整文件名或直接 structured parent 识别完整 fiscal year/period",
                )
            )
            continue
        filing_candidates.append(
            (
                _build_filing_entry(
                    request=request,
                    source_file=discovered_file.path,
                    ticker=ticker,
                    action=action,
                    fiscal_year=final_year,
                    fiscal_period=final_period,
                ),
                discovered_file.relative_path,
            )
        )

    deduplicated_filings, duplicate_skips = _deduplicate_filings(filing_candidates)
    skipped.extend(duplicate_skips)
    recognized_entries, filing_cap_skips = _apply_filing_caps(deduplicated_filings)
    skipped.extend(filing_cap_skips)
    material_entries, material_cap_skips = _apply_material_caps(
        material_candidates,
        recognized_filing_count=len(recognized_entries),
    )
    skipped.extend(material_cap_skips)
    skipped_entries = tuple(skipped)
    if not recognized_entries and not material_entries:
        raise UploadBatchPlanEmptyError(
            source_dir=resolved_source_dir,
            skipped_entries=skipped_entries,
        )
    return UploadBatchPlan(
        source_dir=resolved_source_dir,
        recursive=effective_recursive,
        recognized_entries=recognized_entries,
        material_entries=material_entries,
        skipped_entries=skipped_entries,
    )


def _discover_source_files(
    *,
    source_dir: Path,
    resolved_source_dir: Path,
    recursive: bool,
) -> tuple[tuple[_DiscoveredFile, ...], list[UploadBatchSkippedEntry]]:
    """安全、稳定地发现可识别候选文件。

    :param source_dir: lexical 绝对 source root。
    :param resolved_source_dir: resolved source root。
    :param recursive: effective recursive policy。
    :returns: 安全普通文件与 owner 跳过事实。
    :raises OSError: 目录读取或路径解析失败时透传。
    :raises KeyboardInterrupt: 扫描被用户中断时透传。
    """

    raw_candidates = source_dir.rglob("*") if recursive else source_dir.iterdir()
    candidates = sorted(
        raw_candidates,
        key=lambda path: path.relative_to(source_dir).as_posix(),
    )
    discovered: list[_DiscoveredFile] = []
    skipped: list[UploadBatchSkippedEntry] = []
    for candidate in candidates:
        relative_path = candidate.relative_to(source_dir).as_posix()
        if candidate.is_dir() and not candidate.is_symlink():
            continue
        lexical_candidate = _lexical_absolute(candidate)
        if _has_internal_symlink(source_dir, lexical_candidate):
            skipped.append(
                _skipped(
                    lexical_candidate,
                    "unsafe_symlink",
                    "源目录内部路径组件或候选文件是 symlink",
                )
            )
            continue
        resolved_candidate = lexical_candidate.resolve(strict=False)
        if not _is_within(resolved_candidate, resolved_source_dir):
            skipped.append(
                _skipped(
                    lexical_candidate,
                    "resolved_escape",
                    "候选文件 resolved path 逃逸 source root",
                )
            )
            continue
        if not lexical_candidate.is_file():
            skipped.append(
                _skipped(
                    lexical_candidate,
                    "not_regular_file",
                    "候选路径不是普通文件",
                )
            )
            continue
        if lexical_candidate.suffix.lower() not in FINS_UPLOAD_FILE_SUFFIXES:
            skipped.append(
                _skipped(
                    lexical_candidate,
                    "unsupported_suffix",
                    f"不支持的上传文件后缀: {lexical_candidate.suffix or '<none>'}",
                )
            )
            continue
        discovered.append(
            _DiscoveredFile(path=resolved_candidate, relative_path=relative_path)
        )
    return tuple(discovered), skipped


def _has_structured_top_level_directory(source_dir: Path) -> bool:
    """判断顶层是否存在 OLD structured directory。

    :param source_dir: 已验证的 lexical source root。
    :returns: 存在真实 ``20YY[/Qn/H1]`` 目录时返回 ``True``。
    :raises OSError: 目录读取失败时透传。
    """

    return any(
        path.is_dir()
        and not path.is_symlink()
        and _STRUCTURED_DIRECTORY_PATTERN.fullmatch(path.name) is not None
        for path in source_dir.iterdir()
    )


def _infer_fiscal_fields(path: Path) -> tuple[int | None, FiscalPeriod | None]:
    """从 child 完整文件名与直接 structured parent 推断财期字段。

    :param path: 已通过安全扫描的文件。
    :returns: 可独立缺失的 fiscal year 与 fiscal period。
    :raises Exception: 不主动抛出异常。
    """

    filename = path.name
    year_match = _FISCAL_YEAR_PATTERN.search(filename)
    fiscal_year = int(year_match.group("year")) if year_match is not None else None
    fiscal_period = _infer_period_from_filename(filename)
    parent_match = _STRUCTURED_DIRECTORY_PATTERN.fullmatch(path.parent.name)
    if parent_match is None or parent_match.group("period") is None:
        return fiscal_year, fiscal_period
    if fiscal_year is None:
        fiscal_year = int(parent_match.group("year"))
    if fiscal_period is None:
        parent_period = parent_match.group("period").upper()
        if parent_period == "Q4":
            fiscal_period = (
                "Q4" if _Q4_QUARTERLY_MARKER in filename else "FY"
            )
        else:
            fiscal_period = cast(FiscalPeriod, parent_period)
    return fiscal_year, fiscal_period


def _infer_period_from_filename(filename: str) -> FiscalPeriod | None:
    """按 OLD exact filename-only precedence 推断财期。

    :param filename: child 完整文件名。
    :returns: canonical fiscal period；无法识别时返回 ``None``。
    :raises Exception: 不主动抛出异常。
    """

    if _H1_PATTERN.search(filename):
        return "H1"
    if _FY_PATTERN.search(filename):
        return "FY"
    if _Q1_PATTERN.search(filename):
        return "Q1"
    if _Q2_PATTERN.search(filename):
        return "Q2"
    if _Q3_PATTERN.search(filename):
        return "Q3"
    if _Q4_PATTERN.search(filename):
        return "Q4" if _Q4_QUARTERLY_MARKER in filename else "FY"
    return None


def _match_material_form(filename: str) -> MaterialFormType | None:
    """按 OLD routing table 首个命中识别 material form。

    :param filename: child 完整文件名。
    :returns: material form；未命中返回 ``None``。
    :raises Exception: 不主动抛出异常。
    """

    for pattern, form_type in _MATERIAL_ROUTING_TABLE:
        if pattern.search(filename):
            return form_type
    return None


def _build_filing_entry(
    *,
    request: UploadBatchPlanRequest,
    source_file: Path,
    ticker: str,
    action: BatchUploadAction,
    fiscal_year: int,
    fiscal_period: FiscalPeriod,
) -> UploadBatchFilingEntry:
    """构造完整 filing typed fact。

    :param request: 批量请求。
    :param source_file: 单一安全文件。
    :param ticker: canonical ticker。
    :param action: 已验证 action。
    :param fiscal_year: 最终财政年度。
    :param fiscal_period: 最终财政期间。
    :returns: filing entry。
    :raises Exception: 不主动抛出异常。
    """

    return UploadBatchFilingEntry(
        file=source_file,
        ticker=ticker,
        aliases=request.aliases,
        action=action,
        fiscal_year=fiscal_year,
        fiscal_period=fiscal_period,
        amended=request.amended,
        filing_date=_optional_text(request.filing_date),
        report_date=_optional_text(request.report_date),
        company_name=_optional_text(request.company_name),
        overwrite=request.overwrite,
    )


def _build_material_entry(
    *,
    request: UploadBatchPlanRequest,
    source_file: Path,
    ticker: str,
    action: BatchUploadAction,
    form_type: MaterialFormType,
    fiscal_year: int | None,
    fiscal_period: FiscalPeriod | None,
) -> UploadBatchMaterialEntry:
    """构造完整 material typed fact。

    :param request: 批量请求。
    :param source_file: 单一安全文件。
    :param ticker: canonical ticker。
    :param action: 已验证 action。
    :param form_type: 最终 material form。
    :param fiscal_year: 可选最终财政年度。
    :param fiscal_period: 可选最终财政期间。
    :returns: material entry。
    :raises Exception: 不主动抛出异常。
    """

    return UploadBatchMaterialEntry(
        file=source_file,
        ticker=ticker,
        aliases=request.aliases,
        action=action,
        form_type=form_type,
        material_name=_derive_material_name(source_file),
        fiscal_year=fiscal_year,
        fiscal_period=fiscal_period,
        amended=request.amended,
        filing_date=_optional_text(request.filing_date),
        report_date=_optional_text(request.report_date),
        company_name=_optional_text(request.company_name),
        overwrite=request.overwrite,
    )


def _derive_material_name(path: Path) -> str:
    """从文件名生成保留 structured prefix 的 material name。

    :param path: material 文件路径。
    :returns: 去扩展名、去紧邻 ``HKEX`` 标识后的 material name。
    :raises Exception: 不主动抛出异常。
    """

    stem = path.stem
    prefix_match = _MATERIAL_PREFIX_PATTERN.match(stem)
    prefix = prefix_match.group(1).upper() if prefix_match is not None else ""
    rest = stem[prefix_match.end() :].strip() if prefix_match is not None else stem
    rest = re.sub(r"^HKEX\s*", "", rest, flags=re.IGNORECASE).strip()
    if prefix == "":
        parent_match = _STRUCTURED_DIRECTORY_PATTERN.fullmatch(path.parent.name)
        if parent_match is not None:
            prefix = path.parent.name.upper()
    if prefix != "" and rest != "":
        return f"{prefix} {rest}"
    return rest if rest != "" else stem


def _deduplicate_filings(
    candidates: list[tuple[UploadBatchFilingEntry, str]],
) -> tuple[
    list[tuple[UploadBatchFilingEntry, str]],
    list[UploadBatchSkippedEntry],
]:
    """按财期选择唯一最高优先级 filing。

    :param candidates: 按 stable relative path 排列的 filing candidates。
    :returns: 保留 candidates 与 typed duplicate skips。
    :raises Exception: 不主动抛出异常。
    """

    groups: dict[
        tuple[int, FiscalPeriod], list[tuple[UploadBatchFilingEntry, str]]
    ] = {}
    for candidate in candidates:
        entry = candidate[0]
        groups.setdefault((entry.fiscal_year, entry.fiscal_period), []).append(candidate)
    kept: list[tuple[UploadBatchFilingEntry, str]] = []
    skipped: list[UploadBatchSkippedEntry] = []
    for group in groups.values():
        ordered = sorted(
            group,
            key=lambda item: (_filing_priority(item[0].file.name), item[1]),
        )
        kept.append(ordered[0])
        skipped.extend(
            _skipped(
                item[0].file,
                "duplicate_period",
                "同一 fiscal year/period 已保留更高优先级或 stable-path 更早的正式报告",
            )
            for item in ordered[1:]
        )
    return kept, skipped


def _filing_priority(filename: str) -> int:
    """计算 OLD 主报告优先级，数值越小越优先。

    :param filename: child 完整文件名。
    :returns: ``0`` 至 ``5`` 的优先级。
    :raises Exception: 不主动抛出异常。
    """

    if _PRIORITY_LONG_SCOPE_REPORT.search(filename):
        return 0
    if _PRIORITY_QUARTERLY_REPORT.search(filename):
        return 1
    if _PRIORITY_GENERIC_REPORT.search(filename):
        return 2
    if _PRIORITY_ANNOUNCEMENT.search(filename):
        return 3
    if _PRIORITY_SUPPLEMENTARY.search(filename):
        return 5
    return 4


def _apply_filing_caps(
    candidates: list[tuple[UploadBatchFilingEntry, str]],
) -> tuple[tuple[UploadBatchFilingEntry, ...], list[UploadBatchSkippedEntry]]:
    """应用 annual=5 与 periodic latest-year/max6 规则。

    :param candidates: 已完成同期去重的 filing candidates。
    :returns: 最终 filing entries 与 typed cap skips。
    :raises Exception: 不主动抛出异常。
    """

    annual = sorted(
        (item for item in candidates if item[0].fiscal_period == "FY"),
        key=lambda item: (-item[0].fiscal_year, item[1]),
    )
    periodic = [item for item in candidates if item[0].fiscal_period != "FY"]
    kept_annual = annual[:_ANNUAL_CAP]
    skipped: list[UploadBatchSkippedEntry] = [
        _skipped(item[0].file, "annual_cap", "超过 annual 最新 5 份上限")
        for item in annual[_ANNUAL_CAP:]
    ]
    kept_periodic: list[tuple[UploadBatchFilingEntry, str]] = []
    if periodic:
        latest_year = max(item[0].fiscal_year for item in periodic)
        latest = sorted(
            (item for item in periodic if item[0].fiscal_year == latest_year),
            key=lambda item: (_PERIOD_ORDER[item[0].fiscal_period], item[1]),
        )
        older = [item for item in periodic if item[0].fiscal_year != latest_year]
        skipped.extend(
            _skipped(
                item[0].file,
                "periodic_older_year",
                f"periodic 只保留最新 fiscal year {latest_year}",
            )
            for item in older
        )
        kept_periodic = latest[:_PERIODIC_CAP]
        skipped.extend(
            _skipped(item[0].file, "periodic_cap", "超过 periodic 最新年度最多 6 份上限")
            for item in latest[_PERIODIC_CAP:]
        )
    return tuple(item[0] for item in (*kept_annual, *kept_periodic)), skipped


def _apply_material_caps(
    candidates: list[tuple[UploadBatchMaterialEntry, str]],
    *,
    recognized_filing_count: int,
) -> tuple[tuple[UploadBatchMaterialEntry, ...], list[UploadBatchSkippedEntry]]:
    """按 material form 应用稳定排序与数量规则。

    :param candidates: material candidates。
    :param recognized_filing_count: 已过滤后的 filing 数量，作为 call cap。
    :returns: 最终 material entries 与 typed cap skips。
    :raises Exception: 不主动抛出异常。
    """

    kept: list[UploadBatchMaterialEntry] = []
    skipped: list[UploadBatchSkippedEntry] = []
    for form_type in (
        "FINANCIAL_STATEMENTS",
        "EARNINGS_CALL",
        "EARNINGS_PRESENTATION",
    ):
        group = sorted(
            (item for item in candidates if item[0].form_type == form_type),
            key=lambda item: (-_filename_year(item[0].file.name), item[1]),
        )
        cap: int | None
        if form_type == "EARNINGS_PRESENTATION":
            cap = _PRESENTATION_CAP
        elif form_type == "EARNINGS_CALL":
            cap = recognized_filing_count
        else:
            cap = None
        kept_items = group if cap is None else group[:cap]
        dropped_items = () if cap is None else group[cap:]
        kept.extend(item[0] for item in kept_items)
        skipped.extend(
            _skipped(
                item[0].file,
                "material_cap",
                f"超过 {form_type} material 收集上限 {cap}",
            )
            for item in dropped_items
        )
    return tuple(kept), skipped


def _filename_year(filename: str) -> int:
    """读取 material 文件名中的首个年份排序键。

    :param filename: child 完整文件名。
    :returns: 四位年份；无法识别时返回 ``0``。
    :raises Exception: 不主动抛出异常。
    """

    match = _FISCAL_YEAR_PATTERN.search(filename)
    return int(match.group("year")) if match is not None else 0


def _validated_action(action: BatchUploadAction) -> BatchUploadAction:
    """在运行时验证 batch action 封闭值。

    :param action: 请求 action。
    :returns: 已验证 action。
    :raises UploadBatchPlanUsageError: action 不在封闭集合时抛出。
    """

    if action not in ("auto", "create", "update"):
        raise UploadBatchPlanUsageError(f"unsupported batch upload action: {action}")
    return action


def _validated_explicit_period(value: FiscalPeriod | None) -> FiscalPeriod | None:
    """验证显式 fiscal period。

    :param value: 请求中的显式 period。
    :returns: canonical period 或 ``None``。
    :raises UploadBatchPlanUsageError: period 非法时抛出。
    """

    try:
        return normalize_fiscal_period(value, field_name="fiscal_period")
    except ValueError as exc:
        raise UploadBatchPlanUsageError(str(exc)) from exc


def _validated_material_form(
    value: str | None,
) -> MaterialFormType | None:
    """验证可选单一 material form override。

    :param value: 请求中的 override。
    :returns: 已验证 form 或 ``None``。
    :raises UploadBatchPlanUsageError: form 不在 routing owner 封闭集合时抛出。
    """

    if value is None:
        return None
    normalized = value.strip().upper()
    if normalized not in _MATERIAL_FORM_TYPES:
        raise UploadBatchPlanUsageError(f"unsupported material form: {value}")
    return cast(MaterialFormType, normalized)


def _skipped(
    path: Path,
    reason_code: UploadBatchSkipReasonCode,
    reason: str,
) -> UploadBatchSkippedEntry:
    """构造 typed skip fact。

    :param path: 被跳过路径。
    :param reason_code: 稳定原因码。
    :param reason: 业务可读原因。
    :returns: skip entry。
    :raises Exception: 不主动抛出异常。
    """

    return UploadBatchSkippedEntry(path=path, reason_code=reason_code, reason=reason)


def _optional_text(value: str | None) -> str | None:
    """规范化可选文本字段。

    :param value: 原始文本。
    :returns: 去首尾空白的非空文本，或 ``None``。
    :raises Exception: 不主动抛出异常。
    """

    if value is None:
        return None
    stripped = value.strip()
    return stripped if stripped != "" else None


def _lexical_absolute(path: Path) -> Path:
    """形成不解析 symlink 的 lexical 绝对路径。

    :param path: 用户或扫描器提供的路径。
    :returns: 已展开用户目录并规范 ``.``/``..`` 的绝对路径。
    :raises OSError: 获取绝对路径失败时透传。
    """

    return Path(os.path.abspath(path.expanduser()))


def _has_internal_symlink(root: Path, candidate: Path) -> bool:
    """检查 root 内部到 candidate 的任一组件是否为 symlink。

    :param root: lexical 绝对 root。
    :param candidate: lexical 绝对 candidate。
    :returns: 内部组件或 candidate 是 symlink 时返回 ``True``。
    :raises ValueError: candidate 不在 lexical root 时抛出。
    """

    relative = candidate.relative_to(root)
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            return True
    return False


def _is_within(path: Path, root: Path) -> bool:
    """判断 resolved path 是否位于 resolved root 内。

    :param path: resolved candidate。
    :param root: resolved root。
    :returns: path 等于或位于 root 内时返回 ``True``。
    :raises Exception: 不主动抛出异常。
    """

    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


__all__: tuple[str, ...] = (
    "BatchUploadAction",
    "FINS_UPLOAD_FILE_SUFFIXES",
    "MaterialFormType",
    "UploadBatchFilingEntry",
    "UploadBatchMaterialEntry",
    "UploadBatchPlan",
    "UploadBatchPlanEmptyError",
    "UploadBatchPlanRequest",
    "UploadBatchPlanUsageError",
    "UploadBatchSkipReasonCode",
    "UploadBatchSkippedEntry",
    "generate_upload_batch_plan",
)
