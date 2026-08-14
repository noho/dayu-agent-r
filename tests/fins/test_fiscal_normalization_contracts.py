"""Fins calendar、Fiscal 与 dataframe 字段 owner contract 测试。"""

from __future__ import annotations

import datetime
from typing import cast

import pandas as pd
import pytest

from dayu.contracts.json_value import JsonValue
from dayu.fins.domain import filing_semantics as filing_semantics_module
from dayu.fins.domain.filing_semantics import (
    fiscal_period_recency_rank,
    normalize_fiscal_year,
    parse_calendar_year,
    parse_iso_calendar_date,
)
from dayu.fins.processors.value_normalization import (
    StringConvertible,
    normalize_optional_dataframe_string,
)
from dayu.fins.tools import read_runtime as read_runtime_module
from dayu.fins.tools.read_runtime import (
    _SourceDocumentSummary,
    _parse_source_document_meta,
    _source_document_recency_sort_key,
)


def test_fiscal_period_recency_rank_uses_fixed_business_order() -> None:
    """财期排序 helper 应固定同一财年内的业务顺序。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 排序权重漂移时抛出。
    """

    periods = [None, "unknown", "Q1", "Q2", "H1", "Q3", "Q4", "FY"]
    assert [fiscal_period_recency_rank(period) for period in periods] == [0, 0, 1, 2, 3, 4, 5, 6]


def test_read_runtime_recency_sort_consumes_domain_rank_helper(monkeypatch: pytest.MonkeyPatch) -> None:
    """read runtime 排序必须消费 domain rank helper，不保留第二份映射。

    Args:
        monkeypatch: pytest monkeypatch fixture。

    Returns:
        无。

    Raises:
        AssertionError: runtime 未调用 domain helper 时抛出。
    """

    observed_periods: list[str | None] = []

    def _record_rank(period: str | None) -> int:
        """记录 runtime 传入的财期并返回可识别权重。

        Args:
            period: runtime 已解析的财期。

        Returns:
            测试用固定权重。

        Raises:
            无。
        """

        observed_periods.append(period)
        return 37

    monkeypatch.setattr(read_runtime_module, "fiscal_period_recency_rank", _record_rank)
    summary = _SourceDocumentSummary(
        document_id="doc-1",
        source_kind="filing",
        form_type="10-Q",
        material_name=None,
        fiscal_year=2025,
        fiscal_period="Q2",
        report_date=None,
        filing_date=None,
        amended=False,
        has_financial_data=None,
    )

    sort_key = _source_document_recency_sort_key(summary)

    assert observed_periods == ["Q2"]
    assert sort_key[4] == 37


def test_source_meta_missing_fiscal_fields_stay_missing_without_date_or_form_inference() -> None:
    """缺失 fiscal 字段时不得从 annual form 或日期补偿。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: read runtime 生成了 producer 未提供的 fiscal 事实时抛出。
    """

    meta = _parse_source_document_meta(
        {
            "form_type": "10-K",
            "report_date": "2024-12-31",
            "filing_date": "2025-02-01",
        }
    )

    assert meta["fiscal_year"] is None
    assert meta["fiscal_period"] is None


def test_source_meta_canonicalizes_explicit_fiscal_period() -> None:
    """producer 显式 fiscal 值应由 domain parser canonical 化。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 显式 fiscal 值未被保真解析时抛出。
    """

    meta = _parse_source_document_meta({"form_type": "10-K", "fiscal_year": 2024, "fiscal_period": " fy "})

    assert meta["fiscal_year"] == 2024
    assert meta["fiscal_period"] == "FY"


@pytest.mark.parametrize("value", [1000, 2025, 9999])
def test_parse_calendar_year_accepts_closed_four_digit_range(value: int) -> None:
    """calendar year owner 应接受闭区间内的整数年份。

    Args:
        value: 合法四位整数年份。

    Returns:
        无。

    Raises:
        AssertionError: 合法年份未原样返回时抛出。
    """

    assert parse_calendar_year(value) == value


@pytest.mark.parametrize(
    "value",
    [True, False, 0, -1, 999, 10000, 2024.0, "2024", None],
)
def test_parse_calendar_year_rejects_invalid_runtime_values(value: JsonValue) -> None:
    """calendar year owner 应拒绝 bool、越界年份和非整数输入。

    Args:
        value: 非法年份运行时值。

    Returns:
        无。

    Raises:
        AssertionError: 非法值未触发 ``ValueError`` 时抛出。
    """

    with pytest.raises(ValueError, match=r"year 必须是 1000\.\.9999 的整数"):
        parse_calendar_year(cast(int, value))


def test_calendar_year_entry_points_share_exact_range_message() -> None:
    """required 与 optional year 入口应共享完全相同的范围文案。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 两个入口的错误文案不同或对外文本变化时抛出。
    """

    expected_message = "reporting_year 必须是 1000..9999 的整数"
    with pytest.raises(ValueError) as required_error:
        parse_calendar_year(999, field_name="reporting_year")
    with pytest.raises(ValueError) as optional_error:
        normalize_fiscal_year("2024", field_name="reporting_year")

    assert str(required_error.value) == expected_message
    assert str(optional_error.value) == expected_message


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("0001-01-01", datetime.date(1, 1, 1)),
        ("0999-12-31", datetime.date(999, 12, 31)),
        ("2000-02-29", datetime.date(2000, 2, 29)),
        ("2024-02-29", datetime.date(2024, 2, 29)),
        ("9999-12-31", datetime.date(9999, 12, 31)),
    ],
)
def test_parse_iso_calendar_date_accepts_real_gregorian_dates(
    value: str,
    expected: datetime.date,
) -> None:
    """ISO date owner 应接受完整公历域内的真实 canonical 日期。

    Args:
        value: 精确 ISO 日期文本。
        expected: 期望公历日期。

    Returns:
        无。

    Raises:
        AssertionError: 合法日期未解析为期望值时抛出。
    """

    assert parse_iso_calendar_date(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "",
        "   ",
        " 2024-02-29",
        "2024-02-29 ",
        "2024-2-9",
        "2024-02-9",
        "2024-2-09",
        "2024/02/29",
        "0000-12-31",
        "10000-01-01",
        "1900-02-29",
        "2023-02-29",
        "2024-00-01",
        "2024-13-01",
        "2024-04-31",
        "2024-01-00",
        "２０２４-０２-２９",
    ],
)
def test_parse_iso_calendar_date_rejects_noncanonical_or_nonexistent_dates(value: str) -> None:
    """ISO date owner 应拒绝空白、非补零、非 ASCII 与不存在日期。

    Args:
        value: 非法日期文本。

    Returns:
        无。

    Raises:
        AssertionError: 非法日期未触发 ``ValueError`` 时抛出。
    """

    with pytest.raises(ValueError, match="date 必须是实际存在的 YYYY-MM-DD 日期"):
        parse_iso_calendar_date(value)


@pytest.mark.parametrize("value", [None, 2024])
def test_parse_iso_calendar_date_rejects_non_string_runtime_values(value: JsonValue) -> None:
    """ISO date owner 应在运行时拒绝绕过窄签名的非字符串输入。

    Args:
        value: 绕过静态类型检查传入的非字符串 JSON 值。

    Returns:
        无。

    Raises:
        AssertionError: 非字符串未触发统一 ``ValueError`` 时抛出。
    """

    with pytest.raises(ValueError, match="date 必须是实际存在的 YYYY-MM-DD 日期"):
        parse_iso_calendar_date(cast(str, value))


def test_parse_iso_calendar_date_does_not_delegate_to_calendar_year_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """完整日期不得继承 partial calendar year 的业务下界。

    Args:
        monkeypatch: pytest monkeypatch fixture。

    Returns:
        无。

    Raises:
        AssertionError: 日期 parser 调用 year owner 或结果错误时抛出。
    """

    def _unexpected_year_parser(value: int, *, field_name: str = "year") -> int:
        """标记完整日期错误调用了 calendar year owner。

        Args:
            value: 意外传入的年份。
            field_name: 意外传入的字段名。

        Returns:
            不返回。

        Raises:
            AssertionError: 始终抛出，证明不允许该调用。
        """

        raise AssertionError(f"unexpected calendar year parse: {field_name}={value}")

    monkeypatch.setattr(filing_semantics_module, "parse_calendar_year", _unexpected_year_parser)

    assert parse_iso_calendar_date("0999-12-31") == datetime.date(999, 12, 31)


@pytest.mark.parametrize("value", [True, False, 0, -1, 999, 10000, 2024.0, "2024"])
def test_normalize_fiscal_year_rejects_non_four_digit_or_non_integer_values(value: JsonValue) -> None:
    """fiscal year 对 bool、越界年份与非整数必须失败关闭。

    Args:
        value: 非法 fiscal year 值。

    Returns:
        无。

    Raises:
        AssertionError: 非法值未触发 ``ValueError`` 时抛出。
    """

    with pytest.raises(ValueError, match=r"fiscal_year 必须是 1000\.\.9999 的整数"):
        normalize_fiscal_year(value)


@pytest.mark.parametrize("value", [1000, 2025, 9999])
def test_normalize_fiscal_year_accepts_missing_and_four_digit_integer(value: int) -> None:
    """fiscal year 只接受缺失或四位整数直接事实。

    Args:
        value: 合法四位 fiscal year。

    Returns:
        无。

    Raises:
        AssertionError: 合法值解析不一致时抛出。
    """

    assert normalize_fiscal_year(None) is None
    assert normalize_fiscal_year(value) == value


def test_normalize_fiscal_year_narrows_json_before_delegating_year_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """optional normalizer 应先收窄 raw JSON，再委托 required year owner。

    Args:
        monkeypatch: pytest monkeypatch fixture。

    Returns:
        无。

    Raises:
        AssertionError: 非整数进入 owner 或合法整数未委托时抛出。
    """

    observed: list[tuple[int, str]] = []

    def _record_year_parser(value: int, *, field_name: str = "year") -> int:
        """记录 optional normalizer 委托的窄年份。

        Args:
            value: 已收窄的整数年份。
            field_name: 透传的字段名。

        Returns:
            原样返回年份。

        Raises:
            无。
        """

        observed.append((value, field_name))
        return value

    monkeypatch.setattr(filing_semantics_module, "parse_calendar_year", _record_year_parser)

    with pytest.raises(ValueError, match=r"reporting_year 必须是 1000\.\.9999 的整数"):
        normalize_fiscal_year("2025", field_name="reporting_year")
    assert observed == []

    assert normalize_fiscal_year(2025, field_name="reporting_year") == 2025
    assert observed == [(2025, "reporting_year")]


@pytest.mark.parametrize("value", ["not-a-period", 1, False])
def test_source_meta_rejects_invalid_fiscal_period(value: JsonValue) -> None:
    """source meta 非空非法 fiscal period 必须失败关闭。

    Args:
        value: 非法 fiscal period 值。

    Returns:
        无。

    Raises:
        AssertionError: 非法值未触发 ``ValueError`` 时抛出。
    """

    with pytest.raises(ValueError, match="fiscal_period"):
        _parse_source_document_meta({"fiscal_period": value})


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        ("", None),
        ("   ", None),
        (float("nan"), None),
        (pd.NA, None),
        (pd.NaT, None),
        (0, "0"),
        (False, "False"),
        ("  ordinary text  ", "ordinary text"),
    ],
)
def test_normalize_optional_dataframe_string_matrix(
    value: StringConvertible | None,
    expected: str | None,
) -> None:
    """dataframe 可选字符串 helper 应保留有效 falsy 标量并统一缺失值。

    Args:
        value: dataframe 标量输入。
        expected: 期望可选文本。

    Returns:
        无。

    Raises:
        AssertionError: 缺失或 falsy 值语义漂移时抛出。
    """

    assert normalize_optional_dataframe_string(value) == expected
