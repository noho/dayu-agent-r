"""CN/HK 下载链路的 form / 窗口纯函数工具集。

本模块仅提供无副作用纯函数：

- :func:`split_cn_form_input`：把 CLI / service 透传过来的 form 输入
  （``None`` / CSV 字符串 / 已切分 tuple）规范化为 ``tuple[str, ...]``，
  同时支持英文逗号 ``,``、中文全角逗号 ``，`` 与空白分隔。
- :func:`resolve_download_period_policy`：按市场把 form 输入解析成 effective、
  discovery 与 missing eligibility 三个 typed 财期集合。
- :func:`resolve_window`：解析 ``start_date`` / ``end_date``，生成远端查询用的
  最大窗口。
- :func:`resolve_period_windows`：生成按财期区分的业务窗口；年报默认 5 年，
  半年报/季报默认 2 年。
- CN bare default 为 ``(FY, H1, Q1, Q3)``；HK bare effective/missing baseline
  为 ``(FY, H1)``，discovery 覆盖全部六期。

设计要点：

- 不依赖仓储 / downloader / docling，可被 workflow 与 pipeline 共享。
- 解析失败抛 ``ValueError``，调用方决定是否升级为 ``failed`` 事件。
- ``Q2`` / ``Q4`` 与 ``H1`` / ``FY`` 不做互相归一。主源缺少独立季度报告
  时由 workflow 标记 skipped。
"""

from __future__ import annotations

import datetime as dt
import hashlib
import re
from dataclasses import dataclass
from typing import Final

from dayu.fins.domain.filing_semantics import parse_fiscal_period_filter_value
from dayu.fins.pipelines.cn_download_models import (
    CN_FISCAL_PERIOD_ORDER,
    CnFiscalPeriod,
    CnMarketKind,
)

CN_BARE_DEFAULT_PERIODS: Final[tuple[CnFiscalPeriod, ...]] = ("FY", "H1", "Q1", "Q3")
"""A 股 bare 请求的 effective、discovery 与 missing eligibility 集合。"""

HK_BARE_EFFECTIVE_PERIODS: Final[tuple[CnFiscalPeriod, ...]] = ("FY", "H1")
"""港股 bare 请求向用户承诺并允许报告 missing 的基线财期。"""

HK_BARE_DISCOVERY_PERIODS: Final[tuple[CnFiscalPeriod, ...]] = CN_FISCAL_PERIOD_ORDER
"""港股 bare 请求为发现 optional 季度材料而覆盖的全部六期。"""

# 窗口默认值与 SEC 链路的业务意图对齐：年报 5 年，季报/半年报 2 年。
_ANNUAL_LOOKBACK_YEARS: Final[int] = 5
_INTERIM_LOOKBACK_YEARS: Final[int] = 2
_LOOKBACK_GRACE_DAYS: Final[int] = 60

# form 输入分隔符：英文逗号 / 中文全角逗号 / 任意空白。
_FORM_INPUT_SEPARATOR_PATTERN: Final[re.Pattern[str]] = re.compile(r"[,，\s]+")

_DATE_FULL_PATTERN: Final[re.Pattern[str]] = re.compile(r"^\d{4}-\d{1,2}-\d{1,2}$")
_DATE_YEAR_MONTH_PATTERN: Final[re.Pattern[str]] = re.compile(r"^\d{4}-\d{1,2}$")
_DATE_YEAR_PATTERN: Final[re.Pattern[str]] = re.compile(r"^\d{4}$")


@dataclass(frozen=True, slots=True)
class CnDownloadPeriodPolicy:
    """CN/HK 下载期间策略的唯一强类型 owner。

    Attributes:
        effective_periods: 向用户承诺并投影到 effective filters 的财期。
        discovery_periods: provider 与本地 rebuild 必须搜索的财期。
        missing_eligible_periods: 无候选时允许报告 missing 的财期。
    """

    effective_periods: tuple[CnFiscalPeriod, ...]
    discovery_periods: tuple[CnFiscalPeriod, ...]
    missing_eligible_periods: tuple[CnFiscalPeriod, ...]

    def __post_init__(self) -> None:
        """校验三个期间集合的 canonical 与包含关系。

        Args:
            无。

        Returns:
            无。

        Raises:
            ValueError: 任一集合为空、重复、顺序非 canonical，或不满足
                ``missing ⊆ effective ⊆ discovery`` 时抛出。
        """

        _validate_policy_periods("effective_periods", self.effective_periods)
        _validate_policy_periods("discovery_periods", self.discovery_periods)
        _validate_policy_periods("missing_eligible_periods", self.missing_eligible_periods)
        if not set(self.missing_eligible_periods).issubset(self.effective_periods):
            raise ValueError("missing_eligible_periods 必须是 effective_periods 的子集")
        if not set(self.effective_periods).issubset(self.discovery_periods):
            raise ValueError("effective_periods 必须是 discovery_periods 的子集")


@dataclass(frozen=True)
class DownloadWindow:
    """``resolve_window`` 的强类型返回。

    Attributes:
        start_date: 已规范为 ``YYYY-MM-DD`` 的窗口起点（含）。
        end_date: 已规范为 ``YYYY-MM-DD`` 的窗口终点（含）。
    """

    start_date: str
    end_date: str


@dataclass(frozen=True)
class PeriodDownloadWindow:
    """单个财期的下载窗口。

    Attributes:
        fiscal_period: 财期字面量。
        start_date: 已规范为 ``YYYY-MM-DD`` 的窗口起点（含）。
        end_date: 已规范为 ``YYYY-MM-DD`` 的窗口终点（含）。
    """

    fiscal_period: CnFiscalPeriod
    start_date: str
    end_date: str


def split_cn_form_input(form_type: str | tuple[str, ...] | None) -> tuple[str, ...]:
    """把 CLI / service 透传的 form 输入规范化为 ``tuple[str, ...]``。

    支持三种形态，均不在此处做合法性校验，仅做切分与去空白：

    - ``None`` -> 空 tuple；调用方据此走默认 forms 分支。
    - ``str``：按英文逗号 ``,``、中文全角逗号 ``，`` 与任意空白拆分；
      连续分隔符与首尾分隔符产生的空 token 被过滤。
    - ``tuple[str, ...]``：原样返回，保留 token 顺序与重复。

    Args:
        form_type: 原始 form 输入。``service_runtime`` 经
            ``_coerce_forms_input`` 转成 CSV 字符串后调用 download_stream，
            CSV 串与 CLI 直接拼接的 ``"FY,H1"`` / ``"FY H1"`` 都能解析。

    Returns:
        归一化后的 token tuple；调用方再交给 :func:`resolve_download_period_policy`
        做语义校验。
    """

    if form_type is None:
        return ()
    if isinstance(form_type, tuple):
        return form_type
    tokens = tuple(token for token in _FORM_INPUT_SEPARATOR_PATTERN.split(form_type) if token)
    return tokens


def build_cn_filing_ids(
    *,
    ticker: str,
    form_type: str,
    fiscal_year: int,
    fiscal_period: str,
    amended: bool,
) -> tuple[str, str]:
    """生成港 A 股 filing 文档 ID 对。

    契约：``ticker`` 必须是已经过 ``ticker_normalization.normalize_ticker``
    的 canonical 形态；本函数只负责按稳定规则生成 ID，不再在内部重复归一化，
    以保证归一化职责在调用方层唯一。

    Args:
        ticker: 已归一化的 canonical ticker。
        form_type: form type。
        fiscal_year: 财年。
        fiscal_period: 财期。
        amended: 是否修订版。

    Returns:
        ``(document_id, internal_document_id)``。

    Raises:
        ValueError: ``ticker`` 或 ``form_type`` 为空时抛出。
    """

    normalized_ticker = ticker.strip()
    if not normalized_ticker:
        raise ValueError("ticker 不能为空")
    normalized_form = form_type.strip().upper()
    normalized_period = fiscal_period.strip().upper()
    if not normalized_form:
        raise ValueError("form_type 不能为空")
    seed = f"{normalized_ticker}|{normalized_form}|{fiscal_year}|{normalized_period}|{int(amended)}"
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()
    internal_document_id = f"cn_{digest}"
    document_id = f"fil_{internal_document_id}"
    return document_id, internal_document_id


def resolve_download_period_policy(
    raw_forms: str | tuple[str, ...] | None,
    market: CnMarketKind,
) -> CnDownloadPeriodPolicy:
    """把 form 输入解析成市场专属的三集合期间策略。

    解析规则：

    - CN bare 输入令三集合均为 ``FY,H1,Q1,Q3``。
    - HK bare 输入令 effective/missing 为 ``FY,H1``，discovery 为全部六期。
    - 字符串输入按 :func:`split_cn_form_input` 规则切分；tuple 输入直接消费。
    - 输入 token 经 domain 财期 parser 归一，``Q2``/``Q4`` 保留为独立季度期间，
      不折叠到 ``H1``/``FY``。
    - 输出按字面量稳定顺序去重：``FY`` / ``H1`` / ``Q1`` / ``Q2`` /
      ``Q3`` / ``Q4``。

    Args:
        raw_forms: 原始 form 输入；接受 ``None`` / CSV 字符串 / 已切分 tuple。
        market: 市场标识，决定空输入时使用哪个默认集合。

    Returns:
        :class:`CnDownloadPeriodPolicy`。

    Raises:
        ValueError: 出现无法识别的 token、或全部 token 解析后为空时抛出，
            调用方据此升级为 ``PIPELINE_COMPLETED.status="failed"``。
    """

    tokens = split_cn_form_input(raw_forms)
    if not tokens:
        if market == "CN":
            return CnDownloadPeriodPolicy(
                effective_periods=CN_BARE_DEFAULT_PERIODS,
                discovery_periods=CN_BARE_DEFAULT_PERIODS,
                missing_eligible_periods=CN_BARE_DEFAULT_PERIODS,
            )
        return CnDownloadPeriodPolicy(
            effective_periods=HK_BARE_EFFECTIVE_PERIODS,
            discovery_periods=HK_BARE_DISCOVERY_PERIODS,
            missing_eligible_periods=HK_BARE_EFFECTIVE_PERIODS,
        )

    seen: set[CnFiscalPeriod] = set()
    for raw in tokens:
        period = parse_fiscal_period_filter_value(raw, field_name="form 输入")
        seen.add(period)
    if not seen:
        raise ValueError("form 输入解析后为空")

    explicit_periods: tuple[CnFiscalPeriod, ...] = tuple(period for period in CN_FISCAL_PERIOD_ORDER if period in seen)
    return CnDownloadPeriodPolicy(
        effective_periods=explicit_periods,
        discovery_periods=explicit_periods,
        missing_eligible_periods=explicit_periods,
    )


def resolve_window(
    start_date: str | None,
    end_date: str | None,
    today: dt.date | None = None,
) -> DownloadWindow:
    """解析远端查询用的最大 ``start_date`` / ``end_date``。

    解析规则：

    - ``end_date`` 缺省 -> ``today``。
    - ``start_date`` 缺省 -> ``end_date`` 回退 5 年再减 60 天宽限；这是远端
      查询最大窗口，workflow 会再按财期应用 :func:`resolve_period_windows`。
    - ``YYYY`` -> ``YYYY-01-01`` / ``YYYY-12-31``（``end`` 语义补尾）。
    - ``YYYY-MM`` -> 月初 / 月末。
    - ``YYYY-MM-DD`` -> 直接采用。

    Args:
        start_date: 原始起点字符串；``None`` 表示缺省。
        end_date: 原始终点字符串；``None`` 表示缺省。
        today: 用于注入测试。生产调用传 ``None`` 即取当天 UTC 日期。

    Returns:
        :class:`DownloadWindow`，字段已规范为 ``YYYY-MM-DD``。

    Raises:
        ValueError: 输入格式非法、或 ``start_date > end_date``。
    """

    anchor_today = today if today is not None else dt.date.today()
    end = _parse_date(end_date, is_end=True) if end_date else anchor_today
    if start_date:
        start = _parse_date(start_date, is_end=False)
    else:
        start = _subtract_years(end, _ANNUAL_LOOKBACK_YEARS) - dt.timedelta(days=_LOOKBACK_GRACE_DAYS)
    if start > end:
        raise ValueError(f"start_date 不能晚于 end_date: {start.isoformat()} > {end.isoformat()}")
    return DownloadWindow(start_date=start.isoformat(), end_date=end.isoformat())


def resolve_period_windows(
    *,
    discovery_periods: tuple[CnFiscalPeriod, ...],
    start_date: str | None,
    end_date: str | None,
    today: dt.date | None = None,
) -> tuple[PeriodDownloadWindow, ...]:
    """解析各财期的业务下载窗口。

    Args:
        discovery_periods: 已归一化的 provider / rebuild discovery 财期。
        start_date: 用户显式起点；提供时所有财期共用该起点。
        end_date: 用户显式终点；缺省时使用 ``today``。
        today: 测试注入日期；生产传 ``None``。

    Returns:
        按 ``discovery_periods`` 顺序返回的窗口 tuple。默认窗口为年报 5 年、
        半年报/季报 2 年，均加 60 天披露宽限。

    Raises:
        ValueError: 日期非法或起点晚于终点时抛出。
    """

    anchor_today = today if today is not None else dt.date.today()
    end = _parse_date(end_date, is_end=True) if end_date else anchor_today
    explicit_start = _parse_date(start_date, is_end=False) if start_date else None
    windows: list[PeriodDownloadWindow] = []
    for period in discovery_periods:
        lookback_years = _ANNUAL_LOOKBACK_YEARS if period == "FY" else _INTERIM_LOOKBACK_YEARS
        start = explicit_start or (_subtract_years(end, lookback_years) - dt.timedelta(days=_LOOKBACK_GRACE_DAYS))
        if start > end:
            raise ValueError(f"start_date 不能晚于 end_date: {start.isoformat()} > {end.isoformat()}")
        windows.append(
            PeriodDownloadWindow(
                fiscal_period=period,
                start_date=start.isoformat(),
                end_date=end.isoformat(),
            )
        )
    return tuple(windows)


# ---------- 模块级私有辅助 ----------


def _validate_policy_periods(
    field_name: str,
    periods: tuple[CnFiscalPeriod, ...],
) -> None:
    """校验单个 policy 财期 tuple 非空、无重复且顺序 canonical。

    Args:
        field_name: 用于错误消息的字段名。
        periods: 待校验财期 tuple。

    Returns:
        无。

    Raises:
        ValueError: tuple 为空、包含重复/未知值或顺序非 canonical 时抛出。
    """

    if not periods:
        raise ValueError(f"{field_name} 不能为空")
    if len(periods) != len(set(periods)):
        raise ValueError(f"{field_name} 不能包含重复财期")
    canonical = tuple(period for period in CN_FISCAL_PERIOD_ORDER if period in periods)
    if periods != canonical:
        raise ValueError(f"{field_name} 必须使用 canonical 财期顺序")


def _parse_date(value: str, *, is_end: bool) -> dt.date:
    """解析 ``YYYY`` / ``YYYY-MM`` / ``YYYY-MM-DD`` 字符串。"""

    raw = value.strip()
    try:
        if _DATE_YEAR_PATTERN.fullmatch(raw):
            year = int(raw)
            return dt.date(year, 12, 31) if is_end else dt.date(year, 1, 1)
        if _DATE_YEAR_MONTH_PATTERN.fullmatch(raw):
            year_str, month_str = raw.split("-")
            year = int(year_str)
            month = int(month_str)
            if is_end:
                next_month = dt.date(year + 1, 1, 1) if month == 12 else dt.date(year, month + 1, 1)
                return next_month - dt.timedelta(days=1)
            return dt.date(year, month, 1)
        if _DATE_FULL_PATTERN.fullmatch(raw):
            return dt.datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError(f"日期格式非法: {value!r}") from exc
    raise ValueError(f"日期格式非法: {value!r}")


def _subtract_years(anchor_date: dt.date, years: int) -> dt.date:
    """从 ``anchor_date`` 回退 ``years`` 年；闰日 2 月 29 取 28。"""

    target_year = anchor_date.year - years
    try:
        return anchor_date.replace(year=target_year)
    except ValueError:
        return anchor_date.replace(year=target_year, day=28)


__all__ = [
    "CN_BARE_DEFAULT_PERIODS",
    "CnDownloadPeriodPolicy",
    "DownloadWindow",
    "HK_BARE_DISCOVERY_PERIODS",
    "HK_BARE_EFFECTIVE_PERIODS",
    "PeriodDownloadWindow",
    "build_cn_filing_ids",
    "resolve_download_period_policy",
    "resolve_period_windows",
    "resolve_window",
    "split_cn_form_input",
]
