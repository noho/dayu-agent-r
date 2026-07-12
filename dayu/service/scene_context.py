"""Service 入口 scene context slot 文本生成。

本模块是 CLI、未来 UI 或其它 Service 入口生成 LLM-facing context slot
文本的单一来源。它消费显式业务输入和显式 FMP API key；Fins resolver 不
读取环境变量，FMP 失败也不会被投影成业务事实。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Final
from zoneinfo import ZoneInfo

from dayu.contracts import JsonValue
from dayu.fins.resolver import FmpCompanyInfoResolutionError, FmpCompanyInfoResolver
from dayu.fins.ticker_normalization import normalize_ticker
from dayu.runtime.numeric import is_positive_finite_number

FMP_API_KEY_ENV: Final[str] = "FMP_API_KEY"
"""FMP API key 的环境变量名称。"""

DEFAULT_ENTRYPOINT_FMP_TIMEOUT_SECONDS: Final[float] = 5.0
"""entrypoint slot path 的默认 FMP 请求超时秒数。"""

FINS_DEFAULT_SUBJECT_SLOT: Final[str] = "fins_default_subject"
"""默认财报分析对象 context slot 名称。"""

CURRENT_TIME_SLOT: Final[str] = "current_time"
"""当前时间 context slot 名称。"""

_SHANGHAI_TIMEZONE_NAME: Final[str] = "Asia/Shanghai"
_SHANGHAI_TIMEZONE: Final[ZoneInfo] = ZoneInfo(_SHANGHAI_TIMEZONE_NAME)
_WEEKDAYS: Final[tuple[str, ...]] = (
    "星期一",
    "星期二",
    "星期三",
    "星期四",
    "星期五",
    "星期六",
    "星期日",
)


@dataclass(frozen=True, slots=True)
class EntrypointContextSlotRequest:
    """entrypoint context slot 生成请求。

    :param ticker: 用户入口传入的业务 ticker；未传时为 ``None``。
    :param now: 调用方指定的当前时间；``None`` 时使用当前上海时间。
    :param fmp_api_key: 调用方显式传入的 FMP API key；缺失时不调用 FMP。
    :param fmp_timeout_seconds: FMP resolver 单次请求超时秒数，默认不超过 5 秒。
    """

    ticker: str | None
    now: datetime | None = None
    fmp_api_key: str | None = None
    fmp_timeout_seconds: float = DEFAULT_ENTRYPOINT_FMP_TIMEOUT_SECONDS


def fins_default_subject(ticker: str | None, company_name: str | None = None) -> str:
    """生成默认财报分析对象的 LLM-facing Markdown 文本。

    :param ticker: 当前分析 ticker；``None`` 或空白时返回空字符串。
    :param company_name: 可选公司名称；空白时只展示 ticker。
    :returns: LLM-facing Markdown 文本。
    :raises ValueError: ticker 形态无法被项目 ticker 归一化规则识别时抛出。
    """

    normalized_ticker = _normalize_optional_ticker(ticker)
    if normalized_ticker is None:
        return ""
    normalized_company_name = _optional_stripped_text(company_name)
    if normalized_company_name is None:
        return f"# 当前分析对象\n你正在分析的是 {normalized_ticker}。"
    return f"# 当前分析对象\n你正在分析的是 {normalized_ticker}（{normalized_company_name}）。"


def current_time(now: datetime | None = None) -> str:
    """生成当前时间的 LLM-facing 中文文本。

    :param now: 指定时间；``None`` 时读取当前上海时间。naive datetime 按
        上海时间解释，aware datetime 会转换到上海时间。
    :returns: 固定格式中文时间文本，并说明该时间不会自动更新。
    :raises Exception: 不主动抛出异常。
    """

    effective_now = _to_shanghai_time(now)
    weekday = _WEEKDAYS[effective_now.weekday()]
    return (
        "# 当前时间\n"
        f"现在是 {effective_now.year}年{effective_now.month}月{effective_now.day}日 "
        f"{effective_now.hour:02d}:{effective_now.minute:02d}"
        f"（{_SHANGHAI_TIMEZONE_NAME}，{weekday}）。\n"
        "这是对话开始时的当前时间；回答“现在/今天/当前时间”默认使用它；该时间不会自动更新。"
    )


def build_entrypoint_context_slot_values(
    request: EntrypointContextSlotRequest,
) -> dict[str, JsonValue]:
    """构造 entrypoint scene context slot 值。

    :param request: context slot 生成请求。
    :returns: ScenePrepare 可消费的 JSON slot 映射。
    :raises ValueError: ticker 或 timeout 输入非法时抛出。
    """

    company_name = _resolve_company_name_for_subject(request)
    return {
        FINS_DEFAULT_SUBJECT_SLOT: fins_default_subject(
            ticker=request.ticker,
            company_name=company_name,
        ),
        CURRENT_TIME_SLOT: current_time(request.now),
    }


def _resolve_company_name_for_subject(request: EntrypointContextSlotRequest) -> str | None:
    """解析 subject slot 可使用的公司名称。

    :param request: context slot 生成请求。
    :returns: 成功解析时返回公司名称；缺 key、缺 ticker 或 FMP 失败时返回 ``None``。
    :raises ValueError: ticker 或 timeout 输入非法时抛出。
    """

    normalized_ticker = _normalize_optional_ticker(request.ticker)
    if normalized_ticker is None:
        return None
    api_key = _optional_stripped_text(request.fmp_api_key)
    if api_key is None:
        return None
    if not is_positive_finite_number(request.fmp_timeout_seconds):
        raise ValueError("fmp_timeout_seconds must be positive finite seconds")
    try:
        return FmpCompanyInfoResolver(
            api_key=api_key,
            timeout_seconds=request.fmp_timeout_seconds,
        ).resolve_company_info(normalized_ticker).company_name
    except FmpCompanyInfoResolutionError:
        return None


def _normalize_optional_ticker(ticker: str | None) -> str | None:
    """归一化可选 ticker。

    :param ticker: 用户入口 ticker。
    :returns: canonical ticker；缺失或空白时返回 ``None``。
    :raises ValueError: 非空 ticker 无法识别时由 ``normalize_ticker`` 抛出。
    """

    stripped_ticker = _optional_stripped_text(ticker)
    if stripped_ticker is None:
        return None
    return normalize_ticker(stripped_ticker).canonical


def _optional_stripped_text(value: str | None) -> str | None:
    """读取可选非空白文本。

    :param value: 原始文本。
    :returns: 去空白后的文本；缺失或空白时为 ``None``。
    :raises Exception: 不主动抛出异常。
    """

    if value is None:
        return None
    stripped = value.strip()
    if stripped == "":
        return None
    return stripped


def _to_shanghai_time(now: datetime | None) -> datetime:
    """把输入时间转换为上海时间。

    :param now: 输入时间；``None`` 表示当前上海时间。
    :returns: 上海时区下的 datetime。
    :raises Exception: 不主动抛出异常。
    """

    if now is None:
        return datetime.now(tz=_SHANGHAI_TIMEZONE)
    if now.tzinfo is None:
        return now.replace(tzinfo=_SHANGHAI_TIMEZONE)
    return now.astimezone(_SHANGHAI_TIMEZONE)


__all__: tuple[str, ...] = (
    "CURRENT_TIME_SLOT",
    "DEFAULT_ENTRYPOINT_FMP_TIMEOUT_SECONDS",
    "FINS_DEFAULT_SUBJECT_SLOT",
    "FMP_API_KEY_ENV",
    "EntrypointContextSlotRequest",
    "build_entrypoint_context_slot_values",
    "current_time",
    "fins_default_subject",
)
