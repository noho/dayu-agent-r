"""Fins 下载调用的强类型契约与静态输入校验真源。

本模块在任何 workspace、runtime 或来源适配器构造前，把用户输入收敛为唯一的
下载请求。下游只消费 canonical ticker、来源、表单与日期边界，不再反解析原始
字符串或猜测边界是否由用户显式提供。
"""

from __future__ import annotations

import calendar
import datetime as dt
import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Final

from dayu.contracts.json_value import JsonValue
from dayu.fins.domain.filing_semantics import (
    FISCAL_PERIODS,
    parse_calendar_year,
    parse_fiscal_period_filter_value,
    parse_iso_calendar_date,
    parse_sec_form_filter_value,
)
from dayu.fins.ticker_normalization import NormalizedTicker, normalize_ticker

FINS_DOWNLOAD_MAX_TICKER_CHARS: Final[int] = 32
"""下载入口接受的单个 ticker 原始文本长度上限。"""

FINS_DOWNLOAD_MAX_FORM_ITEMS: Final[int] = 100
"""下载入口接受的显式 form 数量上限。"""

FINS_DOWNLOAD_MAX_FORM_CHARS: Final[int] = 64
"""单个下载 form 文本长度上限。"""

FINS_DOWNLOAD_MAX_DATE_CHARS: Final[int] = 10
"""下载日期输入长度上限，覆盖年、年月与完整日期。"""

FINS_DOWNLOAD_PUBLIC_MAX_DOCUMENT_ROWS: Final[int] = 10
"""单次 public terminal 最多投影的下载文档行数。"""

FINS_DOWNLOAD_PUBLIC_MAX_TEXT_CHARS: Final[int] = 240
"""下载 public contract 中单个用户可读文本字段的字符上限。"""

_YEAR_PATTERN: Final[re.Pattern[str]] = re.compile(r"^\d{4}$")
_YEAR_MONTH_PATTERN: Final[re.Pattern[str]] = re.compile(r"^\d{4}-\d{1,2}$")
_FULL_DATE_PATTERN: Final[re.Pattern[str]] = re.compile(r"^\d{4}-\d{1,2}-\d{1,2}$")


class FinsDownloadUsageError(ValueError):
    """下载调用可在静态输入阶段确定的用法错误。"""


_DOWNLOAD_MUTATION_MODE_CONFLICT_MESSAGE: Final[str] = "--overwrite 与 --rebuild 不能同时使用；请只选择一种下载变更模式"
"""下载变更模式冲突的唯一用户可读诊断。"""


def _validate_download_mutation_mode(
    *,
    overwrite_existing: bool,
    rebuild_local_artifacts: bool,
) -> None:
    """校验下载请求只能选择一种变更模式。

    Args:
        overwrite_existing: 是否允许远端下载覆盖完整本地 source。
        rebuild_local_artifacts: 是否只基于本地 source 重建下载元数据。

    Returns:
        无。

    Raises:
        TypeError: 任一模式字段不是布尔值时抛出。
        FinsDownloadUsageError: overwrite 与 rebuild 同时启用时抛出。
    """

    if not isinstance(overwrite_existing, bool):
        raise TypeError("overwrite_existing must be bool")
    if not isinstance(rebuild_local_artifacts, bool):
        raise TypeError("rebuild_local_artifacts must be bool")
    if overwrite_existing and rebuild_local_artifacts:
        raise FinsDownloadUsageError(_DOWNLOAD_MUTATION_MODE_CONFLICT_MESSAGE)


class FinsDownloadSource(StrEnum):
    """由 canonical ticker 市场唯一确定的下载来源。"""

    SEC = "sec"
    CNINFO = "cninfo"
    HKEXNEWS = "hkexnews"


class FinsDownloadDocumentDisposition(StrEnum):
    """单个 provider candidate 的互斥下载结果分类。"""

    DOWNLOADED = "downloaded"
    SKIPPED = "skipped"
    REJECTED = "rejected"
    FAILED = "failed"


class FinsDownloadTerminalDisposition(StrEnum):
    """一次下载摘要由文档结果机械派生的终态分类。"""

    SUCCEEDED = "succeeded"
    PARTIAL_FAILURE = "partial_failure"
    FAILED = "failed"
    CANCELLED = "cancelled"


class FinsDownloadTransportCategory(StrEnum):
    """下载来源 transport 的封闭失败分类。"""

    UNCONFIGURED = "unconfigured"
    TIMEOUT = "timeout"
    CONNECTION = "connection"
    HTTP_STATUS = "http_status"
    PROTOCOL = "protocol"
    UNKNOWN = "unknown"


class FinsDownloadProviderError(RuntimeError):
    """来源 transport owner 产生的脱敏下载失败。

    Attributes:
        source: 失败来源。
        transport_category: 封闭 transport 分类。
        retryable: 相同请求稍后重试是否可能恢复。
        safe_message: 不含 URL、联系值、raw payload 或绝对路径的安全说明。
    """

    def __init__(
        self,
        *,
        source: FinsDownloadSource,
        transport_category: FinsDownloadTransportCategory,
        retryable: bool,
        safe_message: str,
    ) -> None:
        """初始化 typed provider failure。

        Args:
            source: 失败来源。
            transport_category: transport 分类。
            retryable: 是否建议重试。
            safe_message: 已脱敏的用户可读说明。

        Returns:
            无。

        Raises:
            TypeError: source、transport_category 或 retryable 类型非法时抛出。
            ValueError: safe_message 为空、过长或包含禁止内容时抛出。
        """

        if not isinstance(source, FinsDownloadSource):
            raise TypeError("source must be FinsDownloadSource")
        if not isinstance(transport_category, FinsDownloadTransportCategory):
            raise TypeError("transport_category must be FinsDownloadTransportCategory")
        if not isinstance(retryable, bool):
            raise TypeError("retryable must be bool")
        _validate_public_text(safe_message, field_name="safe_message", allow_none=False)
        self.source = source
        self.transport_category = transport_category
        self.retryable = retryable
        self.safe_message = safe_message.strip()
        super().__init__(self.safe_message)


class SecUserAgentConfigurationError(FinsDownloadProviderError):
    """SEC 首次 HTTP 前发现合规 User-Agent 未配置。"""

    def __init__(self) -> None:
        """构造不包含联系值的 SEC 配置失败。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        super().__init__(
            source=FinsDownloadSource.SEC,
            transport_category=FinsDownloadTransportCategory.UNCONFIGURED,
            retryable=False,
            safe_message="SEC 下载需要先配置合规 User-Agent 身份",
        )


@dataclass(frozen=True, slots=True)
class FinsDownloadEffectiveFilters:
    """来源 workflow 已实际采用的下载筛选条件。

    Attributes:
        form_types: canonical form 或财期过滤。
        start_date: effective inclusive 起始日期。
        end_date: effective inclusive 结束日期。
        overwrite_existing: 是否覆盖完整本地 source。
        rebuild_local_artifacts: 是否为 local-only rebuild。
    """

    form_types: tuple[str, ...]
    start_date: str | None
    end_date: str | None
    overwrite_existing: bool
    rebuild_local_artifacts: bool

    def __post_init__(self) -> None:
        """校验 effective filters。

        Args:
            无。

        Returns:
            无。

        Raises:
            TypeError: form 或布尔字段类型非法时抛出。
            ValueError: form/date 为空、重复或日期范围非法时抛出。
            FinsDownloadUsageError: overwrite 与 rebuild 同时启用时抛出。
        """

        _validate_download_mutation_mode(
            overwrite_existing=self.overwrite_existing,
            rebuild_local_artifacts=self.rebuild_local_artifacts,
        )
        if len(set(self.form_types)) != len(self.form_types):
            raise ValueError("form_types must not contain duplicates")
        for form_type in self.form_types:
            _validate_public_text(form_type, field_name="form_type", allow_none=False)
        start = _parse_optional_iso_date(self.start_date, field_name="start_date")
        end = _parse_optional_iso_date(self.end_date, field_name="end_date")
        if start is not None and end is not None and start > end:
            raise ValueError("effective start_date must not exceed end_date")


@dataclass(frozen=True, slots=True)
class FinsDownloadDocumentResult:
    """source adapter 产生的单个下载候选 typed 结果。

    Attributes:
        document_id: provider candidate 的业务文档 ID。
        form_or_period: canonical form 或财期；来源无法提供时为 ``None``。
        filing_date: 可选披露日期。
        report_date: 可选报告期日期。
        covered_fiscal_periods: 来源明确声明的覆盖财期；不适用时为空 tuple。
        disposition: 互斥结果分类。
        reason_category: 可选稳定原因分类。
        reason_message: 可选脱敏、可行动原因说明。
        artifact_locator: 已发布 source 文档目录的 workspace-relative locator。
    """

    document_id: str
    form_or_period: str | None
    filing_date: str | None
    report_date: str | None
    covered_fiscal_periods: tuple[str, ...]
    disposition: FinsDownloadDocumentDisposition
    reason_category: str | None
    reason_message: str | None
    artifact_locator: PurePosixPath | None

    def __post_init__(self) -> None:
        """校验单文档结果与 disposition 组合。

        Args:
            无。

        Returns:
            无。

        Raises:
            TypeError: disposition 或 locator 类型非法时抛出。
            ValueError: 文本、日期、reason 或 locator 不满足契约时抛出。
        """

        _validate_public_text(self.document_id, field_name="document_id", allow_none=False)
        _validate_public_text(self.form_or_period, field_name="form_or_period", allow_none=True)
        _parse_optional_iso_date(self.filing_date, field_name="filing_date")
        _parse_optional_iso_date(self.report_date, field_name="report_date")
        if not isinstance(self.covered_fiscal_periods, tuple):
            raise TypeError("covered_fiscal_periods must be tuple")
        if any(not isinstance(period, str) or period not in FISCAL_PERIODS for period in self.covered_fiscal_periods):
            raise ValueError("covered_fiscal_periods must contain canonical fiscal periods")
        if len(set(self.covered_fiscal_periods)) != len(self.covered_fiscal_periods):
            raise ValueError("covered_fiscal_periods must not contain duplicates")
        if not isinstance(self.disposition, FinsDownloadDocumentDisposition):
            raise TypeError("disposition must be FinsDownloadDocumentDisposition")
        _validate_public_text(self.reason_category, field_name="reason_category", allow_none=True)
        _validate_public_text(self.reason_message, field_name="reason_message", allow_none=True)
        if (self.reason_category is None) is not (self.reason_message is None):
            raise ValueError("reason_category and reason_message must be provided together")
        if (
            self.disposition
            in {
                FinsDownloadDocumentDisposition.SKIPPED,
                FinsDownloadDocumentDisposition.REJECTED,
                FinsDownloadDocumentDisposition.FAILED,
            }
            and self.reason_category is None
        ):
            raise ValueError("non-downloaded document result must contain a reason")
        if self.artifact_locator is not None:
            if not isinstance(self.artifact_locator, PurePosixPath):
                raise TypeError("artifact_locator must be PurePosixPath")
            if self.artifact_locator.is_absolute() or ".." in self.artifact_locator.parts:
                raise ValueError("artifact_locator must be workspace-relative")
            if self.disposition is not FinsDownloadDocumentDisposition.DOWNLOADED:
                raise ValueError("only downloaded rows may contain artifact_locator")
        if self.disposition is FinsDownloadDocumentDisposition.DOWNLOADED and self.artifact_locator is None:
            raise ValueError("downloaded document result requires artifact_locator")


@dataclass(frozen=True, slots=True)
class FinsDownloadResultSummary:
    """一次 source adapter operation 的完整 typed 下载结果。

    本 owner 保留全部 operation-local 文档行；public row 上限只在 runtime
    terminal projection 时应用，避免 source adapter 静默丢失结果。
    """

    source: FinsDownloadSource
    canonical_ticker: str
    effective_filters: FinsDownloadEffectiveFilters
    discovered_count: int
    downloaded_count: int
    skipped_count: int
    rejected_count: int
    failed_count: int
    document_rows: tuple[FinsDownloadDocumentResult, ...]
    terminal_disposition: FinsDownloadTerminalDisposition
    missing_periods: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """校验计数、文档行与 missing period 不变量。

        Args:
            无。

        Returns:
            无。

        Raises:
            TypeError: source、filters 或 row 类型非法时抛出。
            ValueError: 计数不守恒、row 分类不一致或 missing period 非法时抛出。
        """

        if not isinstance(self.source, FinsDownloadSource):
            raise TypeError("source must be FinsDownloadSource")
        if not isinstance(self.effective_filters, FinsDownloadEffectiveFilters):
            raise TypeError("effective_filters must be FinsDownloadEffectiveFilters")
        if not isinstance(self.terminal_disposition, FinsDownloadTerminalDisposition):
            raise TypeError("terminal_disposition must be FinsDownloadTerminalDisposition")
        _validate_public_text(
            self.canonical_ticker,
            field_name="canonical_ticker",
            allow_none=False,
        )
        counts = (
            self.discovered_count,
            self.downloaded_count,
            self.skipped_count,
            self.rejected_count,
            self.failed_count,
        )
        if any(count < 0 for count in counts):
            raise ValueError("download counts must be non-negative")
        if self.discovered_count != sum(counts[1:]):
            raise ValueError("discovered_count must equal disposition counts")
        for row in self.document_rows:
            if not isinstance(row, FinsDownloadDocumentResult):
                raise TypeError("document_rows must contain FinsDownloadDocumentResult")
        if len(self.document_rows) != self.discovered_count:
            raise ValueError("document_rows must contain every discovered document")
        disposition_counts = {
            disposition: sum(1 for row in self.document_rows if row.disposition is disposition)
            for disposition in FinsDownloadDocumentDisposition
        }
        if disposition_counts[FinsDownloadDocumentDisposition.DOWNLOADED] != self.downloaded_count:
            raise ValueError("downloaded_count does not match document_rows")
        if disposition_counts[FinsDownloadDocumentDisposition.SKIPPED] != self.skipped_count:
            raise ValueError("skipped_count does not match document_rows")
        if disposition_counts[FinsDownloadDocumentDisposition.REJECTED] != self.rejected_count:
            raise ValueError("rejected_count does not match document_rows")
        if disposition_counts[FinsDownloadDocumentDisposition.FAILED] != self.failed_count:
            raise ValueError("failed_count does not match document_rows")
        expected_terminal = _terminal_disposition_from_counts(
            discovered_count=self.discovered_count,
            downloaded_count=self.downloaded_count,
            rejected_count=self.rejected_count,
            failed_count=self.failed_count,
        )
        # 零候选通常表示正常完成且没有命中；只有 adapter 启动前失败或取消可覆盖终态。
        empty_terminal_override = self.discovered_count == 0 and self.terminal_disposition in {
            FinsDownloadTerminalDisposition.FAILED,
            FinsDownloadTerminalDisposition.CANCELLED,
        }
        if self.terminal_disposition is not expected_terminal and not empty_terminal_override:
            raise ValueError("terminal_disposition does not match download outcome")
        if len(set(self.missing_periods)) != len(self.missing_periods):
            raise ValueError("missing_periods must not contain duplicates")
        for period in self.missing_periods:
            _validate_public_text(period, field_name="missing_period", allow_none=False)

    @classmethod
    def from_document_rows(
        cls,
        *,
        source: FinsDownloadSource,
        canonical_ticker: str,
        effective_filters: FinsDownloadEffectiveFilters,
        document_rows: tuple[FinsDownloadDocumentResult, ...],
        missing_periods: tuple[str, ...] = (),
    ) -> "FinsDownloadResultSummary":
        """从完整 typed rows 唯一派生 counts 与正常终态。

        Args:
            source: resolved 下载来源。
            canonical_ticker: canonical ticker。
            effective_filters: workflow 实际采用的筛选条件。
            document_rows: 完整 operation-local document rows。
            missing_periods: 不计入 discovered 的缺失财期。

        Returns:
            计数、rows 与 terminal disposition 同源的 owner summary。

        Raises:
            TypeError: typed 字段非法时由构造校验抛出。
            ValueError: rows、文本或日期违反 contract 时抛出。
        """

        downloaded_count = sum(row.disposition is FinsDownloadDocumentDisposition.DOWNLOADED for row in document_rows)
        skipped_count = sum(row.disposition is FinsDownloadDocumentDisposition.SKIPPED for row in document_rows)
        rejected_count = sum(row.disposition is FinsDownloadDocumentDisposition.REJECTED for row in document_rows)
        failed_count = sum(row.disposition is FinsDownloadDocumentDisposition.FAILED for row in document_rows)
        discovered_count = len(document_rows)
        return cls(
            source=source,
            canonical_ticker=canonical_ticker,
            effective_filters=effective_filters,
            discovered_count=discovered_count,
            downloaded_count=downloaded_count,
            skipped_count=skipped_count,
            rejected_count=rejected_count,
            failed_count=failed_count,
            document_rows=document_rows,
            terminal_disposition=_terminal_disposition_from_counts(
                discovered_count=discovered_count,
                downloaded_count=downloaded_count,
                rejected_count=rejected_count,
                failed_count=failed_count,
            ),
            missing_periods=missing_periods,
        )

    @property
    def written_document_ids(self) -> tuple[str, ...]:
        """返回 downloaded rows 的 document ID。

        Returns:
            与 ``downloaded_count`` 同源的文档 ID tuple。

        Raises:
            无。
        """

        return tuple(
            row.document_id
            for row in self.document_rows
            if row.disposition is FinsDownloadDocumentDisposition.DOWNLOADED
        )

    @property
    def omitted_count(self) -> int:
        """返回 owner-level 省略数量。

        Returns:
            始终为 ``0``；省略只允许发生在 public projection。

        Raises:
            无。
        """

        return 0

    def to_json_summary(self) -> dict[str, JsonValue]:
        """投影 legacy job record 使用的同源有界摘要。

        Returns:
            计数、downloaded IDs、missing periods 与 effective filters。

        Raises:
            无。
        """

        written_document_ids = self.written_document_ids[:FINS_DOWNLOAD_PUBLIC_MAX_DOCUMENT_ROWS]
        return {
            "source": self.source.value,
            "ticker": self.canonical_ticker,
            "filters": {
                "forms": list(self.effective_filters.form_types),
                "start_date": self.effective_filters.start_date,
                "end_date": self.effective_filters.end_date,
                "overwrite": self.effective_filters.overwrite_existing,
                "rebuild": self.effective_filters.rebuild_local_artifacts,
            },
            "discovered_count": self.discovered_count,
            "downloaded_count": self.downloaded_count,
            "skipped_count": self.skipped_count,
            "rejected_count": self.rejected_count,
            "failed_count": self.failed_count,
            "written_document_ids": list(written_document_ids),
            "omitted_written_document_count": self.downloaded_count - len(written_document_ids),
            "missing_periods": list(self.missing_periods),
            "terminal_disposition": self.terminal_disposition.value,
        }


def _terminal_disposition_from_counts(
    *,
    discovered_count: int,
    downloaded_count: int,
    rejected_count: int,
    failed_count: int,
) -> FinsDownloadTerminalDisposition:
    """从 owner counts 派生正常完成后的终态分类。

    Args:
        discovered_count: provider candidate 总数。
        downloaded_count: 下载成功数。
        rejected_count: 业务拒绝数。
        failed_count: 下载失败数。

    Returns:
        succeeded、partial failure 或 failed。

    Raises:
        AssertionError: 调用方绕过计数守恒并传入不可达组合时抛出。
    """

    if failed_count == 0:
        return FinsDownloadTerminalDisposition.SUCCEEDED
    if downloaded_count == 0 and rejected_count == 0:
        return FinsDownloadTerminalDisposition.FAILED
    if discovered_count > 0:
        return FinsDownloadTerminalDisposition.PARTIAL_FAILURE
    raise AssertionError("mixed download failure requires discovered_count > 0")


@dataclass(frozen=True, slots=True)
class FinsDownloadDateRange:
    """下载使用的 inclusive 日期边界及其显式性。

    Attributes:
        start_bound: inclusive 起始日期；未指定时为 ``None``。
        end_bound: inclusive 结束日期；未指定时为 ``None``。
        start_is_explicit: 起始日期是否来自调用方显式输入。
        end_is_explicit: 结束日期是否来自调用方显式输入。
    """

    start_bound: dt.date | None
    end_bound: dt.date | None
    start_is_explicit: bool
    end_is_explicit: bool

    def __post_init__(self) -> None:
        """校验日期边界与显式性组合的不变量。

        Args:
            无。

        Returns:
            无。

        Raises:
            FinsDownloadUsageError: 显式标记缺少对应边界，或起点晚于终点时抛出。
        """

        if self.start_is_explicit and self.start_bound is None:
            raise FinsDownloadUsageError("显式起始日期必须提供 start_bound")
        if self.end_is_explicit and self.end_bound is None:
            raise FinsDownloadUsageError("显式结束日期必须提供 end_bound")
        if self.start_bound is not None and self.end_bound is not None and self.start_bound > self.end_bound:
            raise FinsDownloadUsageError("--start 不能晚于 --end，请检查下载日期范围")

    @property
    def start_text(self) -> str | None:
        """返回下游 adapter 使用的 canonical 起始日期文本。

        Returns:
            ``YYYY-MM-DD`` 文本；未指定时返回 ``None``。

        Raises:
            无。
        """

        return None if self.start_bound is None else self.start_bound.isoformat()

    @property
    def end_text(self) -> str | None:
        """返回下游 adapter 使用的 canonical 结束日期文本。

        Returns:
            ``YYYY-MM-DD`` 文本；未指定时返回 ``None``。

        Raises:
            无。
        """

        return None if self.end_bound is None else self.end_bound.isoformat()


@dataclass(frozen=True, slots=True)
class FinsDownloadRequest:
    """已完成静态校验的 Fins 下载请求。

    Attributes:
        normalized_ticker: 公共 ticker owner 产生的 canonical ticker。
        source: 由 ticker 市场唯一解析的来源。
        form_types: 来源业务 owner 产生的 canonical 显式表单过滤。
        date_range: 已展开为 inclusive date 的窗口与显式性。
        overwrite_existing: 是否覆盖已有 source document。
        rebuild_local_artifacts: 是否只基于本地 source 重建下载产物。
    """

    normalized_ticker: NormalizedTicker
    source: FinsDownloadSource
    form_types: tuple[str, ...]
    date_range: FinsDownloadDateRange
    overwrite_existing: bool = False
    rebuild_local_artifacts: bool = False

    def __post_init__(self) -> None:
        """校验下载请求的变更模式不变量。

        Args:
            无。

        Returns:
            无。

        Raises:
            TypeError: overwrite 或 rebuild 字段不是布尔值时抛出。
            FinsDownloadUsageError: overwrite 与 rebuild 同时启用时抛出。
        """

        _validate_download_mutation_mode(
            overwrite_existing=self.overwrite_existing,
            rebuild_local_artifacts=self.rebuild_local_artifacts,
        )


def build_fins_download_request(
    *,
    ticker: str,
    form_types: tuple[str, ...] = (),
    start: str | None = None,
    end: str | None = None,
    overwrite_existing: bool = False,
    rebuild_local_artifacts: bool = False,
) -> FinsDownloadRequest:
    """校验原始下载参数并构造唯一 typed request。

    Args:
        ticker: 单个公司 ticker；不接受 CSV 或多 ticker。
        form_types: 用户显式提供的 form 项。
        start: 可选起始日期，接受 ``YYYY``、``YYYY-MM`` 或 ``YYYY-MM-DD``。
        end: 可选结束日期，接受相同格式并展开为对应周期末日。
        overwrite_existing: 是否覆盖已有 source document。
        rebuild_local_artifacts: 是否只基于本地 source 重建下载产物。

    Returns:
        完成 canonicalization 的下载请求。

    Raises:
        TypeError: overwrite 或 rebuild 参数不是布尔值时抛出。
        FinsDownloadUsageError: ticker、form、日期或日期范围非法时抛出。
    """

    normalized_ticker = _parse_single_ticker(ticker)
    canonical_forms = _parse_form_types(form_types, normalized_ticker=normalized_ticker)
    start_bound = _parse_date_bound(start, field_name="--start", is_end=False)
    end_bound = _parse_date_bound(end, field_name="--end", is_end=True)
    return FinsDownloadRequest(
        normalized_ticker=normalized_ticker,
        source=_source_for_ticker(normalized_ticker),
        form_types=canonical_forms,
        date_range=FinsDownloadDateRange(
            start_bound=start_bound,
            end_bound=end_bound,
            start_is_explicit=start is not None,
            end_is_explicit=end is not None,
        ),
        overwrite_existing=overwrite_existing,
        rebuild_local_artifacts=rebuild_local_artifacts,
    )


def _parse_single_ticker(raw_ticker: str) -> NormalizedTicker:
    """校验并规范化下载专用的单 ticker 输入。

    Args:
        raw_ticker: 用户提供的 ticker 文本。

    Returns:
        canonical ticker。

    Raises:
        FinsDownloadUsageError: 输入为空、过长、包含 CSV 分隔符或无法识别时抛出。
    """

    ticker = raw_ticker.strip()
    if not ticker:
        raise FinsDownloadUsageError("--ticker 不能为空，请提供一个公司代码")
    if len(ticker) > FINS_DOWNLOAD_MAX_TICKER_CHARS:
        raise FinsDownloadUsageError(f"--ticker 过长，最多允许 {FINS_DOWNLOAD_MAX_TICKER_CHARS} 个字符")
    if "," in ticker or "，" in ticker:
        raise FinsDownloadUsageError("--ticker 只接受一个公司代码，不能使用逗号分隔多个 ticker")
    try:
        return normalize_ticker(ticker)
    except ValueError as exc:
        raise FinsDownloadUsageError(f"--ticker 无法识别：{ticker}") from exc


def _parse_form_types(
    raw_forms: tuple[str, ...],
    *,
    normalized_ticker: NormalizedTicker,
) -> tuple[str, ...]:
    """按 ticker 市场校验并规范化显式 form 列表。

    Args:
        raw_forms: 原始 form 项。
        normalized_ticker: 已规范化 ticker，用于选择来源业务 parser。

    Returns:
        去重且保持首次出现顺序的 canonical form tuple。

    Raises:
        FinsDownloadUsageError: 数量、长度、空项或业务取值非法时抛出。
    """

    if len(raw_forms) > FINS_DOWNLOAD_MAX_FORM_ITEMS:
        raise FinsDownloadUsageError(f"--forms 最多允许 {FINS_DOWNLOAD_MAX_FORM_ITEMS} 项，请缩小筛选范围")
    canonical_forms: list[str] = []
    seen: set[str] = set()
    for index, raw_form in enumerate(raw_forms, start=1):
        form = raw_form.strip()
        if not form:
            raise FinsDownloadUsageError(f"--forms 第 {index} 项不能为空")
        if len(form) > FINS_DOWNLOAD_MAX_FORM_CHARS:
            raise FinsDownloadUsageError(f"--forms 第 {index} 项过长，最多允许 {FINS_DOWNLOAD_MAX_FORM_CHARS} 个字符")
        try:
            if normalized_ticker.market == "US":
                canonical = parse_sec_form_filter_value(form, field_name="--forms")
            else:
                canonical = parse_fiscal_period_filter_value(form, field_name="--forms")
        except ValueError as exc:
            raise FinsDownloadUsageError(str(exc)) from exc
        if canonical not in seen:
            seen.add(canonical)
            canonical_forms.append(canonical)
    return tuple(canonical_forms)


def _parse_date_bound(
    raw_value: str | None,
    *,
    field_name: str,
    is_end: bool,
) -> dt.date | None:
    """解析并展开单个 inclusive 日期边界。

    Args:
        raw_value: 原始日期文本；``None`` 表示未显式提供。
        field_name: 中文错误中使用的 CLI 参数名。
        is_end: 是否按周期末日展开。

    Returns:
        展开后的日期；未提供时返回 ``None``。

    Raises:
        FinsDownloadUsageError: 日期为空、过长、格式非法或日历日期不存在时抛出。
    """

    if raw_value is None:
        return None
    value = raw_value.strip()
    if not value:
        raise FinsDownloadUsageError(f"{field_name} 不能为空，请使用 YYYY、YYYY-MM 或 YYYY-MM-DD")
    if len(value) > FINS_DOWNLOAD_MAX_DATE_CHARS:
        raise FinsDownloadUsageError(f"{field_name} 过长，请使用 YYYY、YYYY-MM 或 YYYY-MM-DD")
    try:
        if _YEAR_PATTERN.fullmatch(value) is not None:
            year = parse_calendar_year(int(value), field_name=field_name)
            return dt.date(year, 12, 31) if is_end else dt.date(year, 1, 1)
        if _YEAR_MONTH_PATTERN.fullmatch(value) is not None:
            year_text, month_text = value.split("-")
            year = parse_calendar_year(int(year_text), field_name=field_name)
            month = int(month_text)
            day = calendar.monthrange(year, month)[1] if is_end else 1
            return dt.date(year, month, day)
        if _FULL_DATE_PATTERN.fullmatch(value) is not None:
            year_text, month_text, day_text = value.split("-")
            canonical_value = (
                f"{int(year_text):04d}-{int(month_text):02d}-{int(day_text):02d}"
            )
            return parse_iso_calendar_date(canonical_value, field_name=field_name)
    except (ValueError, OverflowError) as exc:
        raise FinsDownloadUsageError(f"{field_name} 不是有效日期，请使用 YYYY、YYYY-MM 或 YYYY-MM-DD") from exc
    raise FinsDownloadUsageError(f"{field_name} 格式错误，请使用 YYYY、YYYY-MM 或 YYYY-MM-DD")


def _source_for_ticker(normalized_ticker: NormalizedTicker) -> FinsDownloadSource:
    """由 ticker 市场解析唯一下载来源。

    Args:
        normalized_ticker: 已规范化 ticker。

    Returns:
        对应市场的下载来源枚举。

    Raises:
        AssertionError: ticker owner 返回未封闭市场时抛出。
    """

    if normalized_ticker.market == "US":
        return FinsDownloadSource.SEC
    if normalized_ticker.market == "CN":
        return FinsDownloadSource.CNINFO
    if normalized_ticker.market == "HK":
        return FinsDownloadSource.HKEXNEWS
    raise AssertionError(f"未支持的 ticker 市场: {normalized_ticker.market}")


def _parse_optional_iso_date(value: str | None, *, field_name: str) -> dt.date | None:
    """校验可选 ISO 日期。

    Args:
        value: 可选 ``YYYY-MM-DD`` 日期文本。
        field_name: 错误说明使用的字段名。

    Returns:
        解析后的日期；输入为 ``None`` 时返回 ``None``。

    Raises:
        ValueError: 日期不是严格 ISO 日期时抛出。
    """

    if value is None:
        return None
    _validate_public_text(value, field_name=field_name, allow_none=False)
    try:
        return parse_iso_calendar_date(value, field_name=field_name)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO date") from exc


def _validate_public_text(
    value: str | None,
    *,
    field_name: str,
    allow_none: bool,
) -> None:
    """校验下载 public contract 文本不会携带高风险 transport/material 内容。

    Args:
        value: 待校验文本。
        field_name: 错误说明使用的字段名。
        allow_none: 是否接受 ``None``。

    Returns:
        无。

    Raises:
        TypeError: 文本字段类型非法时抛出。
        ValueError: 文本为空、过长或包含 URL、绝对路径、raw payload 标记时抛出。
    """

    if value is None:
        if allow_none:
            return
        raise ValueError(f"{field_name} must not be None")
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str")
    stripped = value.strip()
    if not stripped:
        raise ValueError(f"{field_name} must not be empty")
    if len(stripped) > FINS_DOWNLOAD_PUBLIC_MAX_TEXT_CHARS:
        raise ValueError(f"{field_name} exceeds {FINS_DOWNLOAD_PUBLIC_MAX_TEXT_CHARS} characters")
    lowered = stripped.lower()
    if "://" in lowered or "raw payload" in lowered or "provider payload" in lowered:
        raise ValueError(f"{field_name} contains disallowed transport content")
    if stripped.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:\\", stripped):
        raise ValueError(f"{field_name} contains an absolute path")


__all__: tuple[str, ...] = (
    "FINS_DOWNLOAD_MAX_DATE_CHARS",
    "FINS_DOWNLOAD_MAX_FORM_CHARS",
    "FINS_DOWNLOAD_MAX_FORM_ITEMS",
    "FINS_DOWNLOAD_MAX_TICKER_CHARS",
    "FINS_DOWNLOAD_PUBLIC_MAX_DOCUMENT_ROWS",
    "FINS_DOWNLOAD_PUBLIC_MAX_TEXT_CHARS",
    "FinsDownloadDateRange",
    "FinsDownloadDocumentDisposition",
    "FinsDownloadDocumentResult",
    "FinsDownloadEffectiveFilters",
    "FinsDownloadProviderError",
    "FinsDownloadRequest",
    "FinsDownloadResultSummary",
    "FinsDownloadSource",
    "FinsDownloadTerminalDisposition",
    "FinsDownloadTransportCategory",
    "FinsDownloadUsageError",
    "SecUserAgentConfigurationError",
    "build_fins_download_request",
)
