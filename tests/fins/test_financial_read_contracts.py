"""财务结果、XBRL 执行与读取投影契约测试。"""

from __future__ import annotations

from typing import TypeAlias, cast

import pytest
import pandas as pd
from edgar.xbrl.facts import FactQuery, FactsView
from edgar.xbrl import XBRL

from dayu.contracts.json_value import JsonValue
from dayu.fins.domain.financial_result_contract import (
    FinancialPeriod,
    FinancialScale,
    determine_financial_statement_quality,
    infer_financial_scale_from_decimals,
    validate_financial_statement_result_payload,
)
from dayu.fins.domain.filing_semantics import FiscalPeriod
from dayu.fins.domain.xbrl_result_contract import (
    XbrlQueryExecutionError,
    validate_xbrl_facts_result_payload,
)
from dayu.fins.processors.sec_xbrl_query import _query_facts_rows
from dayu.fins.processors.sec_processor import SecProcessor
from dayu.fins.processors.bs_report_form_common import _BaseBsReportFormProcessor
from dayu.fins.processors.bs_six_k_processor import BsSixKFormProcessor
from dayu.fins.processors.html_financial_statement_common import (
    build_html_statement_result_from_tables,
)
from dayu.fins.processors.six_k_form_common import extract_statement_result_from_ocr_pages


class _SentinelEdgarExecutionError(RuntimeError):
    """标记 edgartools 查询执行失败的测试异常。"""


class _EmptyFactsView(FactsView):
    """返回合法空 facts 集合的 edgartools 测试视图。"""

    def __init__(self) -> None:
        """初始化无外部 XBRL 依赖的测试视图。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

    def get_facts(self) -> list[dict[str, JsonValue]]:
        """返回合法空 facts 集合。

        Args:
            无。

        Returns:
            空 facts 列表。

        Raises:
            无。
        """

        return []


class _FailingFactsView(FactsView):
    """抛出 sentinel 异常的 edgartools 测试视图。"""

    def __init__(self) -> None:
        """初始化无外部 XBRL 依赖的测试视图。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

    def get_facts(self) -> list[dict[str, JsonValue]]:
        """模拟 edgartools facts 读取失败。

        Args:
            无。

        Returns:
            本函数不会返回。

        Raises:
            _SentinelEdgarExecutionError: 始终抛出，用于锁定异常传播边界。
        """

        raise _SentinelEdgarExecutionError("sentinel edgartools execution failure")


_FakeExecutionResult: TypeAlias = (
    list[dict[str, JsonValue]] | list[str] | str | Exception
)


class _FakeFactQuery:
    """模拟 edgartools concept query 的最窄执行边界。"""

    def __init__(self, results: dict[str, _FakeExecutionResult]) -> None:
        """初始化查询结果表。

        Args:
            results: concept 到 execute 结果/异常的映射。

        Returns:
            无。

        Raises:
            无。
        """

        self._results = results
        self._concept = ""

    def by_concept(self, concept: str) -> _FakeFactQuery:
        """记录当前查询 concept。

        Args:
            concept: concept 名称。

        Returns:
            当前查询对象。

        Raises:
            无。
        """

        self._concept = concept
        return self

    def execute(self) -> list[dict[str, JsonValue]] | list[str] | str:
        """返回预设结果或抛出预设异常。

        Args:
            无。

        Returns:
            预设的合法或 malformed 返回值。

        Raises:
            Exception: 预设值为异常时原样抛出。
        """

        result = self._results.get(self._concept, [])
        if isinstance(result, Exception):
            raise result
        return result


class _FakeXbrl:
    """为 concept execution matrix 提供 fake query 的 XBRL 测试替身。"""

    def __init__(
        self,
        results: dict[str, _FakeExecutionResult],
        *,
        statement_dataframe: pd.DataFrame | None = None,
    ) -> None:
        """初始化 concept 结果。

        Args:
            results: concept 到 execute 结果/异常的映射。
            statement_dataframe: 可选 statement DataFrame。

        Returns:
            无。

        Raises:
            无。
        """

        self._results = results
        self.statements = _FakeStatements(statement_dataframe)

    def query(self) -> _FakeFactQuery:
        """创建一次 fake query。

        Args:
            无。

        Returns:
            fake query。

        Raises:
            无。
        """

        return _FakeFactQuery(self._results)


class _FakeStatement:
    """返回固定 DataFrame 的 edgartools statement 测试替身。"""

    def __init__(self, dataframe: pd.DataFrame) -> None:
        """保存 DataFrame。

        Args:
            dataframe: statement DataFrame。

        Returns:
            无。

        Raises:
            无。
        """

        self._dataframe = dataframe

    def to_dataframe(self) -> pd.DataFrame:
        """返回 statement DataFrame。

        Args:
            无。

        Returns:
            statement DataFrame。

        Raises:
            无。
        """

        return self._dataframe


class _FakeStatements:
    """提供 income statement method 的测试替身。"""

    def __init__(self, dataframe: pd.DataFrame | None) -> None:
        """保存可选 DataFrame。

        Args:
            dataframe: 可选 statement DataFrame。

        Returns:
            无。

        Raises:
            无。
        """

        self._dataframe = dataframe

    def income_statement(self) -> _FakeStatement | None:
        """返回 income statement 或 ``None``。

        Args:
            无。

        Returns:
            固定 statement。

        Raises:
            无。
        """

        if self._dataframe is None:
            return None
        return _FakeStatement(self._dataframe)


class _SecQueryHarness(SecProcessor):
    """只暴露 SecProcessor XBRL caller mapping 的测试处理器。"""

    def __init__(self, xbrl: XBRL | None) -> None:
        """保存测试 XBRL 对象而不解析文档。

        Args:
            xbrl: 测试 XBRL 对象。

        Returns:
            无。

        Raises:
            无。
        """

        self._test_xbrl = xbrl

    def _get_xbrl(self) -> XBRL | None:
        """返回预设 XBRL 对象。

        Args:
            无。

        Returns:
            预设 XBRL 对象。

        Raises:
            无。
        """

        return self._test_xbrl


class _BsQueryHarness(_BaseBsReportFormProcessor):
    """只暴露 BS report XBRL caller mapping 的测试处理器。"""

    FORM_TYPE = "10-K"

    def __init__(self, xbrl: XBRL | None) -> None:
        """保存测试 XBRL 对象而不解析文档。

        Args:
            xbrl: 测试 XBRL 对象。

        Returns:
            无。

        Raises:
            无。
        """

        self._test_xbrl = xbrl

    def _get_xbrl(self) -> XBRL | None:
        """返回预设 XBRL 对象。

        Args:
            无。

        Returns:
            预设 XBRL 对象。

        Raises:
            无。
        """

        return self._test_xbrl


class _BsSixKStatementHarness(BsSixKFormProcessor):
    """只暴露 BS 6-K XBRL statement caller 的测试处理器。"""

    def __init__(self, xbrl: XBRL | None) -> None:
        """保存测试 XBRL 对象而不解析文档。

        Args:
            xbrl: 测试 XBRL 对象。

        Returns:
            无。

        Raises:
            无。
        """

        self._test_xbrl = xbrl

    def _get_xbrl(self) -> XBRL | None:
        """返回预设 XBRL 对象。

        Args:
            无。

        Returns:
            预设 XBRL 对象。

        Raises:
            无。
        """

        return self._test_xbrl


class _HtmlTableFixture:
    """HTML 财务表解析测试使用的表格对象。"""

    def __init__(self, *, caption: str, fiscal_semantics: bool = True) -> None:
        """构造带 caption、上下文和 DataFrame 的表格。

        Args:
            caption: 表格 caption。
            fiscal_semantics: 是否在列头提供明示 fiscal period/year。

        Returns:
            无。

        Raises:
            无。
        """

        self.caption = caption
        self.context_before = "US$ Year ended December 31" if fiscal_semantics else "US$"
        period_headers = ["FY2025", "FY2024"] if fiscal_semantics else [
            "2025-12-31",
            "2024-12-31",
        ]
        self.dataframe = pd.DataFrame(
            [
                ["Income Statement", *period_headers],
                ["Revenue", "100", "90"],
                ["Gross profit", "50", "45"],
                ["Operating income", "20", "18"],
                ["Net income", "10", "8"],
            ]
        )


def _parse_html_fixture_table(table: _HtmlTableFixture) -> pd.DataFrame:
    """返回 HTML 测试表格的 DataFrame。

    Args:
        table: HTML 测试表格。

    Returns:
        表格 DataFrame。

    Raises:
        无。
    """

    return table.dataframe


def _complete_financial_payload() -> dict[str, JsonValue]:
    """构造满足完整财务领域契约的测试载荷。

    Args:
        无。

    Returns:
        完整财务报表 JSON 载荷。

    Raises:
        无。
    """

    return {
        "statement_type": "income",
        "periods": [
            {
                "period_end": "2025-12-31",
                "fiscal_year": 2025,
                "fiscal_period": "FY",
            }
        ],
        "rows": [{"concept": "Revenue", "label": "Revenue", "values": [100]}],
        "currency": "USD",
        "units": "USD",
        "scale": "millions",
        "data_quality": "xbrl",
        "reason": None,
        "statement_locator": {
            "statement_type": "income",
            "statement_title": "Income Statement",
            "period_labels": ["FY2025"],
            "row_labels": ["Revenue"],
        },
    }


def test_edgartools_execute_treats_empty_list_as_successful_zero_rows() -> None:
    """edgartools execute 的合法空列表必须保持成功零命中。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: edgartools 不再返回合法空列表时抛出。
    """

    assert FactQuery(_EmptyFactsView()).execute() == []


def test_edgartools_execute_propagates_facts_view_exception() -> None:
    """edgartools execute 的底层异常必须可与合法空列表区分。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: edgartools 吞掉 sentinel 异常时抛出。
    """

    with pytest.raises(_SentinelEdgarExecutionError):
        FactQuery(_FailingFactsView()).execute()


@pytest.mark.parametrize(
    ("scale", "fiscal_year", "fiscal_period", "expected_reason"),
    [
        (None, 2025, "FY", "scale_unavailable"),
        ("millions", None, None, "period_semantics_unavailable"),
        (None, None, None, "scale_and_period_semantics_unavailable"),
    ],
)
def test_financial_quality_reason_matrix_uses_direct_evidence(
    scale: str | None,
    fiscal_year: int | None,
    fiscal_period: str | None,
    expected_reason: str,
) -> None:
    """缺失倍率/财期证据时必须产生唯一 partial reason。

    Args:
        scale: 直接倍率证据。
        fiscal_year: 直接财年证据。
        fiscal_period: 直接财期证据。
        expected_reason: 期望降级原因。

    Returns:
        无。

    Raises:
        AssertionError: 质量矩阵不唯一时抛出。
    """

    period = FinancialPeriod(
        period_end="2025-12-31",
        fiscal_year=fiscal_year,
        fiscal_period=cast(FiscalPeriod | None, fiscal_period),
    )
    outcome = determine_financial_statement_quality(
        rows=[{"concept": "Revenue", "values": [100]}],
        periods=[period],
        scale=cast(FinancialScale | None, scale),
        complete_quality="xbrl",
    )

    assert outcome.data_quality == "partial"
    assert outcome.reason == expected_reason


@pytest.mark.parametrize(
    "missing_field",
    ["periods", "scale", "data_quality", "reason", "statement_locator"],
)
def test_financial_validator_rejects_missing_required_fields(missing_field: str) -> None:
    """财务领域校验器必须拒绝任一 required 字段缺失。

    Args:
        missing_field: 要删除的必填字段。

    Returns:
        无。

    Raises:
        AssertionError: 缺失字段未被拒绝时抛出。
    """

    payload = _complete_financial_payload()
    payload.pop(missing_field)

    with pytest.raises(ValueError, match=missing_field):
        validate_financial_statement_result_payload(payload)


@pytest.mark.parametrize(
    ("updates", "expected_message"),
    [
        ({"scale": "mega"}, "scale 非法"),
        ({"data_quality": "partial", "reason": None}, "partial 必须提供 reason"),
        ({"data_quality": "xbrl", "reason": "scale_unavailable"}, "reason 必须为 None"),
        ({"rows": []}, "空 rows"),
        ({"units": "USD in millions"}, "units 不得承载 scale"),
    ],
)
def test_financial_validator_rejects_invalid_quality_and_scale_contracts(
    updates: dict[str, JsonValue],
    expected_message: str,
) -> None:
    """财务领域校验器必须拒绝质量、原因、倍率与 units 冲突。

    Args:
        updates: 覆盖到合法载荷的非法字段。
        expected_message: 预期错误片段。

    Returns:
        无。

    Raises:
        AssertionError: 非法载荷未被拒绝时抛出。
    """

    payload = _complete_financial_payload()
    payload.update(updates)

    with pytest.raises(ValueError, match=expected_message):
        validate_financial_statement_result_payload(payload)


def test_financial_validator_preserves_complete_owner_fields() -> None:
    """合法财务载荷必须逐字段通过并保留 owner 语义。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 任一 owner 字段丢失时抛出。
    """

    payload = _complete_financial_payload()

    assert validate_financial_statement_result_payload(payload) == payload


@pytest.mark.parametrize(
    ("decimals", "expected_scale"),
    [(-9, "billions"), (-6, "millions"), (-3, "thousands"), (0, "units"), (2, "units"), ("INF", "units"), (-4, None)],
)
def test_financial_scale_truth_is_shared_and_exact(
    decimals: JsonValue,
    expected_scale: str | None,
) -> None:
    """XBRL decimals 只能按领域 owner 的精确规则产生倍率。

    Args:
        decimals: XBRL decimals 直接值。
        expected_scale: 期望倍率。

    Returns:
        无。

    Raises:
        AssertionError: 倍率规则漂移时抛出。
    """

    assert infer_financial_scale_from_decimals(decimals) == expected_scale


def test_xbrl_execution_summary_distinguishes_empty_success_and_failure() -> None:
    """合法空集与 concept 异常必须分别计入 successful/failed。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 执行会计丢失时抛出。
    """

    xbrl = cast(
        XBRL,
        _FakeXbrl(
            {
                "Revenue": [],
                "Assets": _SentinelEdgarExecutionError("sentinel"),
            }
        ),
    )

    summary = _query_facts_rows(
        xbrl,
        ["Revenue", "Assets"],
        None,
        None,
        None,
        None,
        None,
        None,
    )

    assert summary.rows == []
    assert summary.attempted_concepts == ("Revenue", "Assets")
    assert summary.successful_concepts == ("Revenue",)
    assert summary.failed_concepts == ("Assets",)


@pytest.mark.parametrize("malformed_result", [["malformed"], "malformed"])
def test_xbrl_execution_summary_treats_malformed_return_as_failure(
    malformed_result: list[str] | str,
) -> None:
    """非 list 或含非 mapping row 的返回必须计为 concept failure。

    Args:
        malformed_result: 非 list 或含非 mapping row 的返回值。

    Returns:
        无。

    Raises:
        AssertionError: malformed 返回被当成成功时抛出。
    """

    xbrl = cast(XBRL, _FakeXbrl({"Revenue": [], "Assets": malformed_result}))

    summary = _query_facts_rows(
        xbrl,
        ["Revenue", "Assets"],
        None,
        None,
        None,
        None,
        None,
        None,
    )

    assert summary.successful_concepts == ("Revenue",)
    assert summary.failed_concepts == ("Assets",)


def test_xbrl_execution_summary_all_failed_raises_with_cause() -> None:
    """全部 concept 失败必须抛 typed error 并保留最后 cause。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: all-failed 被投影为空成功或 cause 丢失时抛出。
    """

    sentinel = _SentinelEdgarExecutionError("sentinel")
    xbrl = cast(XBRL, _FakeXbrl({"Revenue": sentinel}))

    with pytest.raises(XbrlQueryExecutionError) as error_info:
        _query_facts_rows(xbrl, ["Revenue"], None, None, None, None, None, None)

    assert error_info.value.failed_concepts == ("Revenue",)
    assert error_info.value.__cause__ is sentinel


def test_xbrl_execution_summary_local_filter_zero_is_successful() -> None:
    """合法 rows 被本地 period filter 清空仍必须是 successful zero rows。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 本地零命中被误判执行失败时抛出。
    """

    xbrl = cast(
        XBRL,
        _FakeXbrl(
            {
                "Revenue": [
                    {
                        "concept": "us-gaap:Revenue",
                        "value": 100,
                        "period_end": "2024-12-31",
                    }
                ]
            }
        ),
    )

    summary = _query_facts_rows(
        xbrl,
        ["Revenue"],
        None,
        "2025-12-31",
        None,
        None,
        None,
        None,
    )

    assert summary.rows == []
    assert summary.successful_concepts == ("Revenue",)
    assert summary.failed_concepts == ()


def test_xbrl_validator_allows_valid_zero_and_rejects_read_dedup_field() -> None:
    """producer XBRL 契约允许正常零命中但拒绝 read-side dedup 字段。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: valid empty 被拒绝或 dedup owner 漂移时抛出。
    """

    payload: dict[str, JsonValue] = {
        "query_params": {"concepts": ["Revenue"]},
        "facts": [],
        "total": 0,
        "data_quality": "xbrl",
        "reason": None,
    }

    validated = validate_xbrl_facts_result_payload(payload)
    assert validated.total == 0
    assert validated.data_quality == "xbrl"

    payload["deduped_fact_count"] = 0
    with pytest.raises(ValueError, match="不得包含.*deduped_fact_count"):
        validate_xbrl_facts_result_payload(payload)


@pytest.mark.parametrize("processor_type", [_SecQueryHarness, _BsQueryHarness])
def test_xbrl_callers_preserve_partial_execution_accounting(
    processor_type: type[_SecQueryHarness] | type[_BsQueryHarness],
) -> None:
    """Sec 与 BS caller 必须用同一 summary 映射 partial reason。

    Args:
        processor_type: 要验证的 caller harness 类型。

    Returns:
        无。

    Raises:
        AssertionError: caller 丢失 failed accounting 时抛出。
    """

    xbrl = cast(
        XBRL,
        _FakeXbrl(
            {
                "Revenue": [],
                "Assets": _SentinelEdgarExecutionError("sentinel"),
            }
        ),
    )
    processor = processor_type(xbrl)

    result = processor.query_xbrl_facts(["Revenue", "Assets"])

    assert result["facts"] == []
    assert result["total"] == 0
    assert result["data_quality"] == "partial"
    assert result["reason"] == "query_partially_failed"


@pytest.mark.parametrize("processor_type", [_SecQueryHarness, _BsQueryHarness])
def test_xbrl_callers_preserve_successful_zero_rows(
    processor_type: type[_SecQueryHarness] | type[_BsQueryHarness],
) -> None:
    """Sec 与 BS caller 必须把合法空 list 投影为 xbrl 零命中。

    Args:
        processor_type: 要验证的 caller harness 类型。

    Returns:
        无。

    Raises:
        AssertionError: 合法空集被降级或失败时抛出。
    """

    processor = processor_type(cast(XBRL, _FakeXbrl({"Revenue": []})))

    result = processor.query_xbrl_facts(["Revenue"])

    assert result["facts"] == []
    assert result["total"] == 0
    assert result["data_quality"] == "xbrl"
    assert result["reason"] is None


@pytest.mark.parametrize("processor_type", [_SecQueryHarness, _BsQueryHarness])
def test_xbrl_callers_preserve_unavailable_degradation(
    processor_type: type[_SecQueryHarness] | type[_BsQueryHarness],
) -> None:
    """Sec 与 BS caller 必须把 XBRL unavailable 投影为完整 partial value。

    Args:
        processor_type: 要验证的 caller harness 类型。

    Returns:
        无。

    Raises:
        AssertionError: unavailable reason 或 required 字段丢失时抛出。
    """

    processor = processor_type(None)

    result = processor.query_xbrl_facts(["Revenue"])

    assert result["facts"] == []
    assert result["total"] == 0
    assert result["data_quality"] == "partial"
    assert result["reason"] == "xbrl_not_available"


@pytest.mark.parametrize("processor_type", [_SecQueryHarness, _BsQueryHarness])
def test_xbrl_callers_do_not_build_payload_when_all_concepts_fail(
    processor_type: type[_SecQueryHarness] | type[_BsQueryHarness],
) -> None:
    """Sec 与 BS caller 的 all-failed 路径必须直接抛 typed error。

    Args:
        processor_type: 要验证的 caller harness 类型。

    Returns:
        无。

    Raises:
        AssertionError: caller 把 all-failed 改写为空结果时抛出。
    """

    xbrl = cast(
        XBRL,
        _FakeXbrl({"Revenue": _SentinelEdgarExecutionError("sentinel")}),
    )
    processor = processor_type(xbrl)

    with pytest.raises(XbrlQueryExecutionError):
        processor.query_xbrl_facts(["Revenue"])


@pytest.mark.parametrize("include_decimals", [True, False])
def test_bs_common_statement_consumes_shared_scale_and_quality_owner(
    include_decimals: bool,
) -> None:
    """BS report statement caller 必须消费共享 XBRL scale outcome。

    Args:
        include_decimals: 是否提供 ``-6`` 倍率证据。

    Returns:
        无。

    Raises:
        AssertionError: BS common 丢失倍率或质量降级时抛出。
    """

    xbrl = _statement_xbrl(include_decimals=include_decimals)
    processor = _BsQueryHarness(xbrl)

    result, reason = processor._get_statement_from_xbrl(
        statement_type="income",
        normalized_statement_type="income",
    )

    assert reason is None
    assert result is not None
    assert result["scale"] == ("millions" if include_decimals else None)
    assert result["data_quality"] == ("xbrl" if include_decimals else "partial")
    assert result["reason"] == (None if include_decimals else "scale_unavailable")


@pytest.mark.parametrize("include_decimals", [True, False])
def test_bs_six_k_statement_consumes_shared_scale_and_quality_owner(
    include_decimals: bool,
) -> None:
    """BS 6-K statement caller 必须消费共享 XBRL scale outcome。

    Args:
        include_decimals: 是否提供 ``-6`` 倍率证据。

    Returns:
        无。

    Raises:
        AssertionError: BS 6-K 丢失倍率或质量降级时抛出。
    """

    processor = _BsSixKStatementHarness(_statement_xbrl(include_decimals=include_decimals))

    result = processor._get_financial_statement_from_xbrl(
        statement_type="income",
        normalized_statement_type="income",
    )

    assert result is not None
    assert result["scale"] == ("millions" if include_decimals else None)
    assert result["data_quality"] == ("xbrl" if include_decimals else "partial")
    assert result["reason"] == (None if include_decimals else "scale_unavailable")


def _statement_xbrl(*, include_decimals: bool) -> XBRL:
    """构造带 statement、fiscal 与可选倍率证据的 fake XBRL。

    Args:
        include_decimals: 是否在 Revenue fact 中提供 ``-6``。

    Returns:
        fake XBRL 对象。

    Raises:
        无。
    """

    fact: dict[str, JsonValue] = {
        "concept": "us-gaap:Revenue",
        "value": 100,
        "period_end": "2025-12-31",
        "fiscal_year": 2025,
        "fiscal_period": "FY",
        "unit": "USD",
    }
    if include_decimals:
        fact["decimals"] = -6
    dataframe = pd.DataFrame(
        [{"concept": "Revenue", "label": "Revenue", "2025-12-31": 100}]
    )
    return cast(
        XBRL,
        _FakeXbrl(
            {"Revenue": [fact]},
            statement_dataframe=dataframe,
        ),
    )


def test_bs_scale_probe_failure_keeps_rows_and_degrades_quality() -> None:
    """XBRL scale probe 失败不得吞 statement rows，必须显式降级。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: probe failure 被吞或 rows 丢失时抛出。
    """

    dataframe = pd.DataFrame(
        [{"concept": "Revenue", "label": "Revenue", "2025-12-31": 100}]
    )
    failures: dict[str, _FakeExecutionResult] = {
        concept: _SentinelEdgarExecutionError("scale probe failed")
        for concept in ("Revenues", "Revenue", "SalesRevenueNet", "SalesRevenueGoodsNet")
    }
    xbrl = cast(XBRL, _FakeXbrl(failures, statement_dataframe=dataframe))

    result, reason = _BsQueryHarness(xbrl)._get_statement_from_xbrl(
        statement_type="income",
        normalized_statement_type="income",
    )

    assert reason is None
    assert result is not None
    assert result["rows"]
    assert result["scale"] is None
    assert result["data_quality"] == "partial"
    assert result["reason"] == "scale_and_period_semantics_unavailable"


@pytest.mark.parametrize(
    ("caption", "expected_scale", "expected_quality", "expected_reason"),
    [
        ("Income Statement (US$ in millions)", "millions", "extracted", None),
        ("Income Statement (US$)", None, "partial", "scale_unavailable"),
    ],
)
def test_html_caption_owns_scale_and_units_remain_measurement_only(
    caption: str,
    expected_scale: str | None,
    expected_quality: str,
    expected_reason: str | None,
) -> None:
    """HTML caption 倍率证据必须进入统一质量矩阵且不拼入 units。

    Args:
        caption: 测试表格 caption。
        expected_scale: 期望倍率。
        expected_quality: 期望质量。
        expected_reason: 期望原因。

    Returns:
        无。

    Raises:
        AssertionError: HTML producer 倍率或质量语义错误时抛出。
    """

    result = build_html_statement_result_from_tables(
        statement_type="income",
        tables=[_HtmlTableFixture(caption=caption)],
        parse_table_dataframe=_parse_html_fixture_table,
    )

    assert result is not None
    assert result["scale"] == expected_scale
    assert result["units"] == "USD"
    assert result["data_quality"] == expected_quality
    assert result["reason"] == expected_reason


@pytest.mark.parametrize(
    ("caption", "expected_reason"),
    [
        ("Income Statement (US$ in millions)", "period_semantics_unavailable"),
        ("Income Statement (US$)", "scale_and_period_semantics_unavailable"),
    ],
)
def test_html_missing_fiscal_evidence_uses_quality_owner(
    caption: str,
    expected_reason: str,
) -> None:
    """HTML 无明示 fiscal 证据时不得从期末月份猜测 issuer 财期。

    Args:
        caption: 表格 caption。
        expected_reason: 期望降级原因。

    Returns:
        无。

    Raises:
        AssertionError: HTML producer 猜测财期或原因矩阵错误时抛出。
    """

    result = build_html_statement_result_from_tables(
        statement_type="income",
        tables=[_HtmlTableFixture(caption=caption, fiscal_semantics=False)],
        parse_table_dataframe=_parse_html_fixture_table,
    )

    assert result is not None
    assert all(period["fiscal_year"] is None for period in result["periods"])
    assert all(period["fiscal_period"] is None for period in result["periods"])
    assert result["data_quality"] == "partial"
    assert result["reason"] == expected_reason


def test_html_year_token_without_accepted_fiscal_period_clears_fiscal_year() -> None:
    """HTML 普通年份 token 不得脱离认可的 fiscal period 产生财年。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: producer 保留孤立财年或未按 owner 矩阵降级时抛出。
    """

    table = _HtmlTableFixture(
        caption="Income Statement (US$ in millions)",
        fiscal_semantics=False,
    )
    table.context_before = "US$ Reporting year 2025"

    result = build_html_statement_result_from_tables(
        statement_type="income",
        tables=[table],
        parse_table_dataframe=_parse_html_fixture_table,
    )

    assert result is not None
    assert all(period["fiscal_year"] is None for period in result["periods"])
    assert all(period["fiscal_period"] is None for period in result["periods"])
    assert result["data_quality"] == "partial"
    assert result["reason"] == "period_semantics_unavailable"


def test_ocr_heading_owns_scale_and_units_remain_measurement_only() -> None:
    """OCR heading 的倍率证据必须与 units 分离并产生完整结果。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: OCR producer 倍率或 units 语义错误时抛出。
    """

    page_text = """CONSOLIDATED STATEMENTS OF OPERATIONS
(USD in millions)
Year ended December 31, 2025 2024
Revenue 100 90
Operating income 20 15
Net income 10 8"""

    result = extract_statement_result_from_ocr_pages(
        statement_type="income",
        page_texts=[page_text],
    )

    assert result is not None
    assert result["scale"] == "millions"
    assert result["units"] == "USD"
    assert result["data_quality"] == "extracted"
    assert result["reason"] is None


@pytest.mark.parametrize(
    ("heading", "expected_reason"),
    [
        ("(USD in millions)", "period_semantics_unavailable"),
        ("(USD)", "scale_and_period_semantics_unavailable"),
    ],
)
def test_ocr_missing_fiscal_evidence_uses_quality_owner(
    heading: str,
    expected_reason: str,
) -> None:
    """OCR 无明示 fiscal period 时不得根据十二月日期补写 FY。

    Args:
        heading: 货币/倍率 heading。
        expected_reason: 期望降级原因。

    Returns:
        无。

    Raises:
        AssertionError: OCR producer 猜测财期或原因矩阵错误时抛出。
    """

    page_text = f"""CONSOLIDATED STATEMENTS OF OPERATIONS
{heading}
December 31, 2025 2024
Revenue 100 90
Operating income 20 15
Net income 10 8"""

    result = extract_statement_result_from_ocr_pages(
        statement_type="income",
        page_texts=[page_text],
    )

    assert result is not None
    assert all(period["fiscal_period"] is None for period in result["periods"])
    assert result["data_quality"] == "partial"
    assert result["reason"] == expected_reason


def test_ocr_income_summary_fallback_consumes_heading_scale_owner() -> None:
    """OCR Profit & Loss 单期间 fallback 必须复用 heading scale owner。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: fallback 丢失倍率或拼接 units 时抛出。
    """

    page_text = """1Q25 Earnings
Profit & Loss
USD in millions
Revenue 1,000
Gross profit 500
Operating income 200
Net income 100"""

    result = extract_statement_result_from_ocr_pages(
        statement_type="income",
        page_texts=[page_text],
    )

    assert result is not None
    assert result["periods"] == [
        {"period_end": "2025-03-31", "fiscal_year": 2025, "fiscal_period": "Q1"}
    ]
    assert result["scale"] == "millions"
    assert result["units"] == "USD"
    assert result["data_quality"] == "extracted"
    assert result["reason"] is None
