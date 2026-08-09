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
from typing import Final

from dayu.fins.domain.filing_semantics import (
    parse_fiscal_period_filter_value,
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

_YEAR_PATTERN: Final[re.Pattern[str]] = re.compile(r"^\d{4}$")
_YEAR_MONTH_PATTERN: Final[re.Pattern[str]] = re.compile(r"^\d{4}-\d{1,2}$")
_FULL_DATE_PATTERN: Final[re.Pattern[str]] = re.compile(r"^\d{4}-\d{1,2}-\d{1,2}$")


class FinsDownloadUsageError(ValueError):
    """下载调用可在静态输入阶段确定的用法错误。"""


class FinsDownloadSource(StrEnum):
    """由 canonical ticker 市场唯一确定的下载来源。"""

    SEC = "sec"
    CNINFO = "cninfo"
    HKEXNEWS = "hkexnews"


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
        if (
            self.start_bound is not None
            and self.end_bound is not None
            and self.start_bound > self.end_bound
        ):
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
        raise FinsDownloadUsageError(
            f"--ticker 过长，最多允许 {FINS_DOWNLOAD_MAX_TICKER_CHARS} 个字符"
        )
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
        raise FinsDownloadUsageError(
            f"--forms 最多允许 {FINS_DOWNLOAD_MAX_FORM_ITEMS} 项，请缩小筛选范围"
        )
    canonical_forms: list[str] = []
    seen: set[str] = set()
    for index, raw_form in enumerate(raw_forms, start=1):
        form = raw_form.strip()
        if not form:
            raise FinsDownloadUsageError(f"--forms 第 {index} 项不能为空")
        if len(form) > FINS_DOWNLOAD_MAX_FORM_CHARS:
            raise FinsDownloadUsageError(
                f"--forms 第 {index} 项过长，最多允许 {FINS_DOWNLOAD_MAX_FORM_CHARS} 个字符"
            )
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
        raise FinsDownloadUsageError(
            f"{field_name} 过长，请使用 YYYY、YYYY-MM 或 YYYY-MM-DD"
        )
    try:
        if _YEAR_PATTERN.fullmatch(value) is not None:
            year = int(value)
            return dt.date(year, 12, 31) if is_end else dt.date(year, 1, 1)
        if _YEAR_MONTH_PATTERN.fullmatch(value) is not None:
            year_text, month_text = value.split("-")
            year = int(year_text)
            month = int(month_text)
            day = calendar.monthrange(year, month)[1] if is_end else 1
            return dt.date(year, month, day)
        if _FULL_DATE_PATTERN.fullmatch(value) is not None:
            year_text, month_text, day_text = value.split("-")
            return dt.date(int(year_text), int(month_text), int(day_text))
    except (ValueError, OverflowError) as exc:
        raise FinsDownloadUsageError(
            f"{field_name} 不是有效日期，请使用 YYYY、YYYY-MM 或 YYYY-MM-DD"
        ) from exc
    raise FinsDownloadUsageError(
        f"{field_name} 格式错误，请使用 YYYY、YYYY-MM 或 YYYY-MM-DD"
    )


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


__all__: tuple[str, ...] = (
    "FINS_DOWNLOAD_MAX_DATE_CHARS",
    "FINS_DOWNLOAD_MAX_FORM_CHARS",
    "FINS_DOWNLOAD_MAX_FORM_ITEMS",
    "FINS_DOWNLOAD_MAX_TICKER_CHARS",
    "FinsDownloadDateRange",
    "FinsDownloadRequest",
    "FinsDownloadSource",
    "FinsDownloadUsageError",
    "build_fins_download_request",
)
