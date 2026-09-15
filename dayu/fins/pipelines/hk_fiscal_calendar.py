"""港股标题中的报告截止日与有来源依据的财年日历；不读取披露日期。"""

from __future__ import annotations

import calendar
import re
from datetime import date

_DIGITS = dict(zip("零〇一二三四五六七八九", "00123456789", strict=True))
_MONTHS = (
    "JANUARY",
    "FEBRUARY",
    "MARCH",
    "APRIL",
    "MAY",
    "JUNE",
    "JULY",
    "AUGUST",
    "SEPTEMBER",
    "OCTOBER",
    "NOVEMBER",
    "DECEMBER",
)
_ANNUAL = re.compile(
    r"全年|年度[業业][績绩]|末期[業业][績绩]|ANNUAL RESULTS|FINAL RESULTS|FULL[- ]YEAR"
    r"|十二[個个]月|TWELVE MONTHS|12 MONTHS"
)
_NON_ANNUAL = re.compile(
    r"中期|半年|(?:六|九|十八|十五)[個个]月|(?:SIX|NINE|EIGHTEEN|FIFTEEN|6|9|18|15) MONTHS|INTERIM|HALF[- ]YEAR"
)
_END = re.compile(r"截至|截止|ENDED|ENDING")
_CN_DATE = re.compile(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日")
_ISO_DATE = re.compile(r"\b(\d{4})[-/](\d{1,2})[-/](\d{1,2})\b")
_EN_DATE = re.compile(r"\b(\d{1,2})\s+(" + "|".join(_MONTHS) + r")\s+(\d{4})\b")
_EN_US_DATE = re.compile(r"\b(" + "|".join(_MONTHS) + r")\s+(\d{1,2}),?\s+(\d{4})\b")
_CHINESE_NUMBER = re.compile(r"[零〇一二三四五六七八九十]+")


def _number(match: re.Match[str]) -> str:
    """转换标题数字。参数为中文数字匹配；返回阿拉伯数字；不抛出业务异常。"""
    value = match.group()
    if "十" in value:
        left, right = value.split("十", 1)
        if len(left) > 1 or len(right) > 1 or "十" in right:
            return value
        return str(int(_DIGITS.get(left, "1")) * 10 + int(_DIGITS.get(right, "0")))
    return "".join(_DIGITS[char] for char in value)


def report_end_date(title: str) -> date | None:
    """读取唯一明确截止日。

    参数：title 为原始公告标题。返回：有效且唯一的报告截止日，否则 None。
    异常：无；无效日期与多个日期均保留不确定性。
    """
    if not _END.search(title.upper()):
        return None
    text = _CHINESE_NUMBER.sub(_number, title.upper())
    parts = [tuple(map(int, match.groups())) for pattern in (_CN_DATE, _ISO_DATE) for match in pattern.finditer(text)]
    parts.extend((int(m[3]), _MONTHS.index(m[2]) + 1, int(m[1])) for m in _EN_DATE.finditer(text))
    parts.extend((int(m[3]), _MONTHS.index(m[1]) + 1, int(m[2])) for m in _EN_US_DATE.finditer(text))
    try:
        dates = {date(*part) for part in parts}
    except ValueError:
        return None
    return next(iter(dates)) if len(dates) == 1 else None


def has_unresolved_end_date(title: str) -> bool:
    """检测截止日表达中的歧义。参数为标题；返回是否有年份却无法解析截止日；异常无。"""
    text = _CHINESE_NUMBER.sub(_number, title.upper())
    has_date = bool(
        re.search(r"(?:19|20)\d{2}\s*年|(?:19|20)\d{2}[-/]\d", text)
        or _EN_DATE.search(text)
        or _EN_US_DATE.search(text)
    )
    return bool(_END.search(text) and has_date and report_end_date(title) is None)


def annual_end_dates(titles: tuple[str, ...]) -> tuple[date, ...]:
    """提取同公司年度业绩截止日证据。

    参数：titles 为同公司原始标题。返回：去重排序的年度截止日。
    异常：无；不从年报名称、披露日期或已有季度标签反推日历。
    """
    return tuple(
        sorted(
            {
                end
                for title in titles
                if _ANNUAL.search(title.upper()) and not _NON_ANNUAL.search(title.upper())
                if (end := report_end_date(title)) is not None
            }
        )
    )


def fiscal_quarter_at(end: date, annual_ends: tuple[date, ...]) -> tuple[int, int] | None:
    """用邻近年度截止日识别财年（结束年份）和季度序号。

    参数：end 为报告截止日，annual_ends 为同公司年度截止日证据。
    返回：财年及季度；没有依据、变更年结日、非月末或不在季度边界返回 None。
    异常：无。仅支持有邻近依据的规则月末财年，不猜测过渡期或 52/53 周财年。
    """
    nearby = tuple(d for d in annual_ends if abs((d - end).days) <= 366)
    if not nearby or len({d.month for d in nearby}) != 1:
        return None
    if any(d.day != calendar.monthrange(d.year, d.month)[1] for d in (*nearby, end)):
        return None
    month = nearby[0].month
    offset = (end.month - month) % 12
    if offset % 3:
        return None
    return end.year + int(end.month > month), (offset // 3 if offset else 4)
