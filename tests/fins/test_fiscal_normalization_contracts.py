"""Fiscal 与 dataframe 可选字符串 owner contract 测试。"""

from __future__ import annotations

import pandas as pd
import pytest

from dayu.contracts.json_value import JsonValue
from dayu.fins.domain.filing_semantics import fiscal_period_recency_rank, normalize_fiscal_year
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


@pytest.mark.parametrize("value", [True, False, 0, -1, 2024.0, "2024"])
def test_normalize_fiscal_year_rejects_non_positive_or_non_integer_values(value: JsonValue) -> None:
    """fiscal year 对 bool、非正数与非整数必须失败关闭。

    Args:
        value: 非法 fiscal year 值。

    Returns:
        无。

    Raises:
        AssertionError: 非法值未触发 ``ValueError`` 时抛出。
    """

    with pytest.raises(ValueError, match="fiscal_year 必须为正整数"):
        normalize_fiscal_year(value)


def test_normalize_fiscal_year_accepts_missing_and_positive_integer() -> None:
    """fiscal year 只接受缺失或正整数直接事实。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 合法值解析不一致时抛出。
    """

    assert normalize_fiscal_year(None) is None
    assert normalize_fiscal_year(2025) == 2025


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
