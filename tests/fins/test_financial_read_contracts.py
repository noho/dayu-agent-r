"""财务结果、XBRL 执行与读取投影契约测试。"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Literal, TypeAlias, cast

import pytest
import pandas as pd
from edgar.xbrl.facts import FactQuery, FactsView
from edgar.xbrl import XBRL

from dayu.contracts.json_value import JsonValue
from dayu.fins.domain.financial_result_contract import (
    FinancialPeriod,
    FinancialScale,
    FinancialStatementResult,
    determine_financial_statement_quality,
    infer_financial_scale_from_decimals,
    validate_financial_statement_result_payload,
)
from dayu.fins.domain.filing_semantics import FISCAL_PERIODS, FiscalPeriod
from dayu.fins.domain.xbrl_result_contract import (
    XbrlQueryExecutionError,
    validate_xbrl_facts_result_payload,
)
from dayu.fins.processors.sec_xbrl_query import _query_facts_rows
from dayu.fins.processors.sec_processor import SecProcessor
from dayu.fins.processors.bs_report_form_common import _BaseBsReportFormProcessor
from dayu.fins.processors.bs_six_k_processor import BsSixKFormProcessor
from dayu.fins.processors.bs_ten_k_processor import BsTenKFormProcessor
from dayu.fins.processors.bs_ten_q_processor import BsTenQFormProcessor
from dayu.fins.processors.bs_twenty_f_processor import BsTwentyFFormProcessor
from dayu.fins.processors.html_financial_statement_common import (
    _extract_currency_for_column,
    _extract_first_date,
    _extract_fiscal_period_from_direct_text,
    _extract_fiscal_period_year,
    _infer_scale_from_caption,
    _normalize_period_end,
    _parse_optional_numeric,
    build_html_statement_result_from_tables,
)
from dayu.fins.processors.report_form_financial_statement_common import (
    classify_report_statement_type_for_table,
    select_report_statement_tables,
    should_apply_report_statement_html_fallback,
)
from dayu.fins.processors.six_k_form_common import (
    _classify_statement_type_for_table,
    extract_statement_result_from_ocr_pages,
)
from dayu.fins.storage.local_file_source import LocalFileSource


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


class _MissingStatements:
    """不提供任何报表 method 的测试替身。"""


class _FakeXbrl:
    """为 concept execution matrix 提供 fake query 的 XBRL 测试替身。"""

    def __init__(
        self,
        results: dict[str, _FakeExecutionResult],
        *,
        statement_dataframe: pd.DataFrame | None = None,
        statement_method_available: bool = True,
    ) -> None:
        """初始化 concept 结果。

        Args:
            results: concept 到 execute 结果/异常的映射。
            statement_dataframe: 可选 statement DataFrame。
            statement_method_available: 是否提供 income statement method。

        Returns:
            无。

        Raises:
            无。
        """

        self._results = results
        self.statements: _FakeStatements | _MissingStatements
        if statement_method_available:
            self.statements = _FakeStatements(statement_dataframe)
        else:
            self.statements = _MissingStatements()

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
        self._tables = []

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
        self._tables = []

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

    def _get_statement_result_from_ocr_pages(
        self,
        statement_type: str,
    ) -> FinancialStatementResult | None:
        """声明测试场景无 OCR 回退结果。

        Args:
            statement_type: 目标报表类型。

        Returns:
            ``None``。

        Raises:
            无。
        """

        del statement_type
        return None


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


class _ReportTableFixture(_HtmlTableFixture):
    """报告类 HTML 选择规则使用的真实 DataFrame 表格。"""

    def __init__(
        self,
        *,
        caption: str,
        headers: list[str],
        is_financial: bool,
        table_type: str = "data",
        dataframe: pd.DataFrame | None = None,
    ) -> None:
        """初始化分类、layout 与行信号输入。

        Args:
            caption: 表格标题。
            headers: 表头文本。
            is_financial: 是否由上游标记为财务表。
            table_type: 表格结构类型。
            dataframe: 可选自定义 DataFrame。

        Returns:
            无。

        Raises:
            无。
        """

        super().__init__(caption=caption)
        self.headers = headers
        self.is_financial = is_financial
        self.table_type = table_type
        if dataframe is not None:
            self.dataframe = dataframe


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
    }


def _assert_financial_result_contract(result: FinancialStatementResult) -> None:
    """断言 actual producer 结果满足财务 owner exact contract。

    Args:
        result: actual producer 返回的财务报表结果。

    Returns:
        无。

    Raises:
        AssertionError: 键集、可选 reason 或 terminal validator 语义不一致时抛出。
    """

    required_keys = {
        "statement_type",
        "periods",
        "rows",
        "currency",
        "units",
        "scale",
        "data_quality",
    }
    expected_keys = required_keys | ({"reason"} if result["data_quality"] == "partial" else set())

    assert set(result) == expected_keys
    assert validate_financial_statement_result_payload(result) == result


_StatementObservation = Literal["method_absent", "method_none", "empty_table", "empty_rows"]


def _statement_xbrl_for_observation(observation: _StatementObservation) -> XBRL:
    """构造一类报表不可用的直接 XBRL 观测。

    Args:
        observation: method 缺失、返回空、空表或空 rows 之一。

    Returns:
        只包含该观测的 fake XBRL。

    Raises:
        AssertionError: 传入未声明的观测时抛出。
    """

    if observation == "method_absent":
        return cast(XBRL, _FakeXbrl({}, statement_method_available=False))
    if observation == "method_none":
        return cast(XBRL, _FakeXbrl({}, statement_dataframe=None))
    if observation == "empty_table":
        return cast(
            XBRL,
            _FakeXbrl(
                {},
                statement_dataframe=pd.DataFrame(
                    columns=["concept", "label", "2025-12-31"]
                ),
            ),
        )
    if observation == "empty_rows":
        return cast(
            XBRL,
            _FakeXbrl(
                {},
                statement_dataframe=pd.DataFrame(
                    [{"concept": "", "label": "", "2025-12-31": 100}]
                ),
            ),
        )
    raise AssertionError(f"未声明的报表观测: {observation}")


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
    ["statement_type", "periods", "rows", "currency", "units", "scale", "data_quality"],
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
        ({"data_quality": "partial"}, "partial 必须提供 reason"),
        ({"data_quality": "xbrl", "reason": "scale_unavailable"}, "必须省略 reason"),
        ({"reason": None}, "不得使用 null"),
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


@pytest.mark.parametrize(
    "reason",
    [
        "unsupported_statement_type",
        "xbrl_not_available",
        "statement_not_found",
        "low_confidence_extraction",
        "scale_unavailable",
        "period_semantics_unavailable",
        "scale_and_period_semantics_unavailable",
    ],
)
def test_financial_validator_accepts_exact_actionable_reason_set(reason: str) -> None:
    """财务 producer 只能在 partial 结果中输出七个可行动原因。

    Args:
        reason: 待验证的业务原因。

    Returns:
        无。

    Raises:
        AssertionError: 合法原因被拒绝或可选字段丢失时抛出。
    """

    payload = _complete_financial_payload()
    payload.update(
        {
            "rows": [],
            "periods": [],
            "scale": None,
            "data_quality": "partial",
            "reason": reason,
        }
    )

    validated = validate_financial_statement_result_payload(payload)

    assert "reason" in validated
    assert validated["reason"] == reason


def test_financial_validator_rejects_unknown_fields_and_reason() -> None:
    """财务 producer 契约必须对未知字段与未知原因 fail closed。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 任一未知语义被接受时抛出。
    """

    unknown_field_payload = _complete_financial_payload()
    unknown_field_payload["internal_detail"] = "hidden"
    with pytest.raises(ValueError, match="包含未知字段: internal_detail"):
        validate_financial_statement_result_payload(unknown_field_payload)

    unknown_reason_payload = _complete_financial_payload()
    unknown_reason_payload.update(
        {"rows": [], "data_quality": "partial", "reason": "unknown_reason"}
    )
    with pytest.raises(ValueError, match="reason 非法"):
        validate_financial_statement_result_payload(unknown_reason_payload)


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

    validated = validate_financial_statement_result_payload(payload)

    assert validated == payload
    assert set(validated) == {
        "statement_type",
        "periods",
        "rows",
        "currency",
        "units",
        "scale",
        "data_quality",
    }


@pytest.mark.parametrize("observation", ["method_absent", "method_none", "empty_table", "empty_rows"])
@pytest.mark.parametrize("processor_type", [_SecQueryHarness, _BsQueryHarness])
def test_sec_and_bs_statement_terminals_normalize_not_found_observations(
    observation: _StatementObservation,
    processor_type: type[_SecQueryHarness] | type[_BsQueryHarness],
) -> None:
    """SEC generic 与 BS report terminal 必须统一四类报表缺失观测。

    Args:
        observation: 报表不可用的直接观测。
        processor_type: 待验证的 actual processor terminal。

    Returns:
        无。

    Raises:
        AssertionError: 观测未归一或结果越出 owner contract 时抛出。
    """

    processor = processor_type(_statement_xbrl_for_observation(observation))

    result = processor.get_financial_statement("income")

    assert "reason" in result
    assert result["reason"] == "statement_not_found"
    _assert_financial_result_contract(result)


@pytest.mark.parametrize("observation", ["method_absent", "method_none", "empty_table", "empty_rows"])
def test_bs_six_k_terminal_normalizes_not_found_observations(
    observation: _StatementObservation,
) -> None:
    """BS 6-K terminal 必须在 XBRL/HTML/OCR 均无结果时统一四类观测。

    Args:
        observation: 报表不可用的直接观测。

    Returns:
        无。

    Raises:
        AssertionError: 观测未归一或结果越出 owner contract 时抛出。
    """

    processor = _BsSixKStatementHarness(_statement_xbrl_for_observation(observation))

    result = processor.get_financial_statement("income")

    assert "reason" in result
    assert result["reason"] == "statement_not_found"
    _assert_financial_result_contract(result)


def test_bs_report_concrete_processors_share_the_validated_terminal_owner() -> None:
    """BS 10-K/10-Q/20-F concrete processors 必须共享同一报表 terminal。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 任一 concrete processor 脱离 common owner 时抛出。
    """

    assert issubclass(BsTenKFormProcessor, _BaseBsReportFormProcessor)
    assert issubclass(BsTenQFormProcessor, _BaseBsReportFormProcessor)
    assert issubclass(BsTwentyFFormProcessor, _BaseBsReportFormProcessor)


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


def test_xbrl_validator_allows_countless_zero_hit_and_preserves_raw_payload() -> None:
    """producer XBRL 契约允许无 count 的正常零命中且不改写输入。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: valid empty 被拒绝或原始载荷被修改时抛出。
    """

    payload: dict[str, JsonValue] = {
        "query_params": {"concepts": ["Revenue"]},
        "facts": [],
        "data_quality": "xbrl",
    }
    before = deepcopy(payload)

    validated = validate_xbrl_facts_result_payload(payload)

    assert payload == before
    assert validated.query_params == {"concepts": ["Revenue"]}
    assert validated.facts == []
    assert validated.data_quality == "xbrl"
    assert validated.reason is None


def test_xbrl_validator_rejects_unknown_result_and_query_param_fields() -> None:
    """XBRL result 与 query params 键集必须同时 fail closed。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 任一未知字段被接受时抛出。
    """

    result_field_payload: dict[str, JsonValue] = {
        "query_params": {"concepts": ["Revenue"]},
        "facts": [],
        "data_quality": "xbrl",
        "unexpected": 0,
    }
    with pytest.raises(ValueError, match="包含未知字段: unexpected"):
        validate_xbrl_facts_result_payload(result_field_payload)

    query_field_payload: dict[str, JsonValue] = {
        "query_params": {"concepts": ["Revenue"], "nested_filters": {}},
        "facts": [],
        "data_quality": "xbrl",
    }
    with pytest.raises(ValueError, match="包含未知字段: nested_filters"):
        validate_xbrl_facts_result_payload(query_field_payload)


@pytest.mark.parametrize("fiscal_period", sorted(FISCAL_PERIODS))
def test_xbrl_validator_consumes_shared_fiscal_period_values(
    fiscal_period: FiscalPeriod,
) -> None:
    """XBRL 查询财期必须消费共享 ``FISCAL_PERIODS`` 真源。

    Args:
        fiscal_period: 共享闭集中的财期。

    Returns:
        无。

    Raises:
        AssertionError: 任一共享财期被拒绝时抛出。
    """

    payload: dict[str, JsonValue] = {
        "query_params": {"concepts": ["Revenue"], "fiscal_period": fiscal_period},
        "facts": [],
        "data_quality": "xbrl",
    }

    validated = validate_xbrl_facts_result_payload(payload)

    assert "fiscal_period" in validated.query_params
    assert validated.query_params["fiscal_period"] == fiscal_period


@pytest.mark.parametrize(
    ("field_name", "value", "expected_message"),
    [
        ("min_value", True, "min_value 不得为 bool"),
        ("max_value", False, "max_value 不得为 bool"),
        ("fiscal_period", "fy", "fiscal_period 非法"),
    ],
)
def test_xbrl_validator_rejects_non_contract_filter_values(
    field_name: str,
    value: JsonValue,
    expected_message: str,
) -> None:
    """XBRL 查询参数必须拒绝 bool number 与非精确财期。

    Args:
        field_name: 待验证字段。
        value: 非法值。
        expected_message: 期望错误片段。

    Returns:
        无。

    Raises:
        AssertionError: 非法值未被拒绝时抛出。
    """

    query_params: dict[str, JsonValue] = {"concepts": ["Revenue"], field_name: value}
    payload: dict[str, JsonValue] = {
        "query_params": query_params,
        "facts": [],
        "data_quality": "xbrl",
    }

    with pytest.raises(ValueError, match=expected_message):
        validate_xbrl_facts_result_payload(payload)


def test_xbrl_validator_accepts_flat_numbers_and_omits_absent_filters() -> None:
    """XBRL 查询参数接受 int/float 并保持未提供字段缺席。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: number 被拒绝或缺席字段被补写时抛出。
    """

    payload: dict[str, JsonValue] = {
        "query_params": {"concepts": ["Revenue"], "min_value": 1, "max_value": 2.5},
        "facts": [],
        "data_quality": "xbrl",
    }

    validated = validate_xbrl_facts_result_payload(payload)

    assert validated.query_params == {
        "concepts": ["Revenue"],
        "min_value": 1,
        "max_value": 2.5,
    }
    assert "fiscal_period" not in validated.query_params


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

    assert set(result) == {"query_params", "facts", "data_quality", "reason"}
    assert result["facts"] == []
    assert result["data_quality"] == "partial"
    assert "reason" in result
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

    assert set(result) == {"query_params", "facts", "data_quality"}
    assert result["facts"] == []
    assert result["data_quality"] == "xbrl"
    assert "reason" not in result


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

    assert set(result) == {"query_params", "facts", "data_quality", "reason"}
    assert result["facts"] == []
    assert result["data_quality"] == "partial"
    assert "reason" in result
    assert result["reason"] == "xbrl_not_available"


@pytest.mark.parametrize("processor_type", [_SecQueryHarness, _BsQueryHarness])
def test_xbrl_callers_emit_flat_typed_query_params(
    processor_type: type[_SecQueryHarness] | type[_BsQueryHarness],
) -> None:
    """Sec 与 BS actual caller 必须仅输出实际提供的扁平查询参数。

    Args:
        processor_type: 待验证的 actual caller harness。

    Returns:
        无。

    Raises:
        AssertionError: 参数被嵌套、补空或丢失时抛出。
    """

    processor = processor_type(None)

    result = processor.query_xbrl_facts(
        ["Revenue"],
        statement_type="income",
        period_end="2025-12-31",
        fiscal_year=2025,
        fiscal_period="FY",
        min_value=1,
        max_value=2.5,
    )

    assert result["query_params"] == {
        "concepts": ["Revenue"],
        "statement_type": "IncomeStatement",
        "period_end": "2025-12-31",
        "fiscal_year": 2025,
        "fiscal_period": "FY",
        "min_value": 1,
        "max_value": 2.5,
    }
    assert validate_xbrl_facts_result_payload(result).query_params == result["query_params"]


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
    if include_decimals:
        assert "reason" not in result
    else:
        assert "reason" in result
        assert result["reason"] == "scale_unavailable"
    _assert_financial_result_contract(result)


@pytest.mark.parametrize("processor_type", [_SecQueryHarness, _BsQueryHarness])
def test_sec_and_bs_actual_producers_emit_exact_complete_contract(
    processor_type: type[_SecQueryHarness] | type[_BsQueryHarness],
) -> None:
    """SEC generic 与 BS report actual producer 的完整结果必须省略 reason。

    Args:
        processor_type: 待验证的 actual processor harness。

    Returns:
        无。

    Raises:
        AssertionError: producer 输出非 exact contract 或显式空 reason 时抛出。
    """

    processor = processor_type(_statement_xbrl(include_decimals=True))

    result = processor.get_financial_statement("income")

    assert result["data_quality"] == "xbrl"
    assert "reason" not in result
    _assert_financial_result_contract(result)


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
    if include_decimals:
        assert "reason" not in result
    else:
        assert "reason" in result
        assert result["reason"] == "scale_unavailable"
    _assert_financial_result_contract(result)


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
    assert "reason" in result
    assert result["reason"] == "scale_and_period_semantics_unavailable"
    _assert_financial_result_contract(result)


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
    if expected_reason is None:
        assert "reason" not in result
    else:
        assert "reason" in result
        assert result["reason"] == expected_reason
    _assert_financial_result_contract(result)


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
    assert "reason" in result
    assert result["reason"] == expected_reason
    _assert_financial_result_contract(result)


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
    assert "reason" in result
    assert result["reason"] == "period_semantics_unavailable"
    _assert_financial_result_contract(result)


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
    assert "reason" not in result
    _assert_financial_result_contract(result)


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
    assert "reason" in result
    assert result["reason"] == expected_reason
    _assert_financial_result_contract(result)


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
    assert "reason" not in result
    _assert_financial_result_contract(result)


@pytest.mark.parametrize(
    ("caption", "headers", "context", "expected"),
    [
        ("Consolidated Statements of Operations", ["Revenue"], "", "income"),
        ("Consolidated Balance Sheets", ["Total assets"], "", "balance_sheet"),
        ("Statements of Cash Flows", ["Operating activities"], "", "cash_flow"),
        ("Statements of Shareholders' Equity", ["Common stock"], "", "equity"),
        ("Statements of Comprehensive Income", ["Net income"], "", "comprehensive_income"),
        ("Table of Contents", ["Statements of Operations"], "", None),
        (None, None, "discussion of operations", None),
    ],
)
def test_report_form_table_classification_uses_business_signals(
    caption: str | None,
    headers: list[str] | None,
    context: str,
    expected: str | None,
) -> None:
    """报告类表格分类必须组合标题、表头、上下文并排除噪声。

    Args:
        caption: 表格标题。
        headers: 表头。
        context: 表格前文。
        expected: 预期报表类型。

    Returns:
        无。

    Raises:
        AssertionError: 分类结果偏离业务信号时抛出。
    """

    assert classify_report_statement_type_for_table(
        caption=caption,
        headers=headers,
        context_before=context,
    ) == expected


def test_report_form_selection_prefers_classification_then_row_signals() -> None:
    """报告类候选选择必须过滤 layout 并按分类、严格行信号顺序返回。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: fallback reason 或候选顺序漂移时抛出。
    """

    classified = _ReportTableFixture(
        caption="Consolidated Statements of Operations",
        headers=["Revenue", "FY2025"],
        is_financial=True,
    )
    layout = _ReportTableFixture(
        caption="Consolidated Statements of Operations",
        headers=["Revenue"],
        is_financial=True,
        table_type="layout",
    )
    row_signal = _ReportTableFixture(
        caption="Quarterly data",
        headers=["FY2025"],
            is_financial=False,
            dataframe=pd.DataFrame(
                [
                    ["Metric", "FY2025"],
                    ["Revenue", 100],
                    ["Gross profit", 50],
                    ["Operating income", 20],
                    ["Net income", 10],
                    ["Earnings per share", 1],
                    ["Cost of revenue", 50],
                    ["Total revenue", 100],
            ]
        ),
    )

    assert select_report_statement_tables(
        statement_type="income",
        tables=[layout, row_signal, classified],
        parse_table_dataframe=_parse_html_fixture_table,
    ) == [classified]
    assert select_report_statement_tables(
        statement_type="income",
        tables=[layout, row_signal],
        parse_table_dataframe=_parse_html_fixture_table,
    ) == [row_signal]
    assert select_report_statement_tables(
        statement_type="unsupported",
        tables=[classified],
        parse_table_dataframe=_parse_html_fixture_table,
    ) == []
    assert select_report_statement_tables(
        statement_type="income",
        tables=[layout],
        parse_table_dataframe=_parse_html_fixture_table,
    ) == []
    assert should_apply_report_statement_html_fallback("xbrl_not_available")
    assert should_apply_report_statement_html_fallback("statement_not_found")
    assert not should_apply_report_statement_html_fallback("scale_unavailable")
    assert not should_apply_report_statement_html_fallback(None)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2025-09-28", "2025-09-28"),
        ("28-Sep-2025", "2025-09-28"),
        ("2025 Sep 28", "2025-09-28"),
        ("09/28/2025", "2025-09-28"),
        ("28/09/25", "2025-09-28"),
        ("September 28, 2025", "2025-09-28"),
        ("September 2025", "2025-09-30"),
        ("not a date", None),
    ],
)
def test_html_period_date_parser_accepts_supported_direct_formats(
    text: str,
    expected: str | None,
) -> None:
    """HTML 期间 owner 必须稳定解析已支持的直接日期格式。

    Args:
        text: 日期文本。
        expected: 预期 ISO 日期。

    Returns:
        无。

    Raises:
        AssertionError: 日期解析语义漂移时抛出。
    """

    parsed = _extract_first_date(text)
    assert (parsed.isoformat() if parsed is not None else None) == expected


def test_html_period_currency_scale_and_numeric_rule_owners_preserve_semantics() -> None:
    """HTML owner 必须保持财期、币种、倍率与数值的稳定业务规则。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 任一基础业务语义解析错误时抛出。
    """

    assert _extract_fiscal_period_year("Q1'25") == ("Q1", 2025)
    assert _extract_fiscal_period_year("2025 H1") == ("H1", 2025)
    assert _extract_fiscal_period_year("9M 2025") == ("Q3", 2025)
    assert _extract_fiscal_period_year("FY 2025") == ("FY", 2025)
    assert _extract_fiscal_period_year("third quarter 2025") == ("Q3", 2025)
    assert _extract_fiscal_period_year("plain year 2025") is None
    assert _extract_fiscal_period_from_direct_text(scope_text="year ended 2025") == "FY"
    assert _extract_fiscal_period_from_direct_text(scope_text="as of 2025") is None
    assert _normalize_period_end(scope_text="year ended", date_text="2025") == "2025-12-31"

    assert _extract_currency_for_column(scope_text="US$ in millions", column_header_text="2025") == "US$"
    assert _extract_currency_for_column(scope_text="RMB", column_header_text="") == "RMB"
    assert _extract_currency_for_column(scope_text="EUR", column_header_text="") == "EUR"
    assert _extract_currency_for_column(scope_text="", column_header_text="") is None
    assert _infer_scale_from_caption("USD in billions") == "billions"
    assert _infer_scale_from_caption("USD in thousands") == "thousands"
    assert _infer_scale_from_caption("USD in units") == "units"
    assert _infer_scale_from_caption(None) is None

    assert _parse_optional_numeric("(1,234.5)") == -1234.5
    assert _parse_optional_numeric("US$ 1.234,5") == 1234.5
    assert _parse_optional_numeric("—") is None
    assert _parse_optional_numeric("n/a") is None


def test_real_sec_processor_reads_and_projects_aapl_fixture() -> None:
    """真实 AAPL filing 必须贯穿 SEC parse、read、search、table 与 XBRL owner。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 任一真实 processor public capability 失败时抛出。
    """

    fixture_path = (
        Path(__file__).resolve().parent
        / "fixtures"
        / "aapl_xbrl"
        / "fil_0000320193-24-000123"
        / "aapl-20240928.htm"
    )
    source = LocalFileSource(
        path=fixture_path,
        uri="local://aapl-20240928.htm",
        media_type="text/html",
    )
    assert SecProcessor.supports(source, form_type="10-K", media_type="text/html")
    assert not SecProcessor.supports(source, form_type="6-K", media_type="text/html")
    assert not SecProcessor.supports(source, form_type=None, media_type="text/html")

    processor = SecProcessor(source, form_type="10-K", media_type="text/html")
    sections = processor.list_sections()
    tables = processor.list_tables()
    assert sections
    assert tables
    first_section = processor.read_section(sections[0]["ref"])
    assert first_section["content"]
    assert processor.get_section_title(sections[0]["ref"]) == sections[0]["title"]
    assert processor.get_section_title("missing") is None
    assert processor.search("Apple")
    assert processor.search("", within_ref=None) == []
    assert processor.search("Apple", within_ref="missing") == []
    assert processor.read_table(tables[0]["table_ref"])["table_ref"] == tables[0]["table_ref"]
    assert processor.get_full_text()
    assert processor.get_full_text_with_table_markers() == ""
    with pytest.raises(KeyError):
        processor.read_section("missing")
    with pytest.raises(KeyError):
        processor.read_table("missing")

    financial_result = processor.get_financial_statement("income")
    _assert_financial_result_contract(financial_result)
    xbrl_result = processor.query_xbrl_facts(["NetIncomeLoss"])
    assert validate_xbrl_facts_result_payload(xbrl_result).query_params == {
        "concepts": ["NetIncomeLoss"]
    }
    assert processor.get_xbrl_taxonomy() == "us-gaap"


def test_real_bs_six_k_processor_uses_html_and_ocr_fallbacks(tmp_path: Path) -> None:
    """真实 BS 6-K HTML 必须覆盖结构化表格、分页与 OCR fallback owner。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 6-K 表格、分页或财务 terminal 行为错误时抛出。
    """

    page_text = " ".join(["Business results and outlook"] * 30)
    html = f"""<html><body>
<h1>Financial Results and Business Updates</h1><p>Business highlights and operating review.</p>
<h2>FINANCIAL STATEMENTS</h2>
<table><caption>Consolidated Statements of Operations (USD in millions)</caption>
<tr><td>Metric</td><td>FY2025</td><td>FY2024</td></tr>
<tr><td>Revenue</td><td>100</td><td>90</td></tr>
<tr><td>Gross profit</td><td>50</td><td>45</td></tr>
<tr><td>Operating income</td><td>20</td><td>18</td></tr>
<tr><td>Net income</td><td>10</td><td>8</td></tr></table>
<div id="Page1">{page_text}</div>
<p style="page-break-before: always">{page_text}</p>
<h2>About Example Holdings Limited</h2><p>Company profile and contacts.</p>
</body></html>"""
    fixture_path = tmp_path / "six-k-owner.html"
    fixture_path.write_text(html, encoding="utf-8")
    source = LocalFileSource(
        path=fixture_path,
        uri="local://six-k-owner.html",
        media_type="text/html",
    )

    assert BsSixKFormProcessor.supports(source, form_type="6-K", media_type="text/html")
    processor = BsSixKFormProcessor(source, form_type="6-K", media_type="text/html")
    sections = processor.list_sections()
    tables = processor.list_tables()
    assert sections
    assert tables
    assert processor.read_section(sections[0]["ref"])["content"]
    assert processor.read_table(tables[0]["table_ref"])["table_ref"] == tables[0]["table_ref"]
    assert processor.search("Business outlook")

    result = processor.get_financial_statement("income")
    _assert_financial_result_contract(result)
    assert result["periods"] == [
        {"period_end": "2025-12-31", "fiscal_year": 2025, "fiscal_period": "FY"},
        {"period_end": "2024-12-31", "fiscal_year": 2024, "fiscal_period": "FY"},
    ]
    assert [row["label"] for row in result["rows"]] == [
        "Revenue",
        "Gross profit",
        "Operating income",
        "Net income",
    ]
    assert result["scale"] == "millions"
    assert result["data_quality"] == "extracted"

    low_confidence_path = tmp_path / "six-k-low-confidence-owner.html"
    low_confidence_path.write_text(
        f"""<html><body>
<h1>Financial Results and Business Updates</h1>
<table><caption>Consolidated Statements of Operations (USD in millions)</caption>
<tr><th>Metric</th><th>FY2025</th><th>FY2024</th></tr>
<tr><td>Revenue</td><td>100</td><td>90</td></tr>
<tr><td>Gross profit</td><td>50</td><td>45</td></tr>
<tr><td>Operating income</td><td>20</td><td>18</td></tr>
<tr><td>Net income</td><td>10</td><td>8</td></tr></table>
<div id="Page1">{page_text}</div>
<p style="page-break-before: always">{page_text}</p>
<h2>About Example Holdings Limited</h2><p>Company profile.</p>
</body></html>""",
        encoding="utf-8",
    )
    low_confidence_processor = BsSixKFormProcessor(
        LocalFileSource(
            path=low_confidence_path,
            uri="local://six-k-low-confidence-owner.html",
            media_type="text/html",
        ),
        form_type="6-K",
        media_type="text/html",
    )
    low_confidence = low_confidence_processor.get_financial_statement("income")
    _assert_financial_result_contract(low_confidence)
    assert low_confidence["rows"] == []
    assert low_confidence["periods"] == []
    assert "reason" in low_confidence
    assert low_confidence["reason"] == "low_confidence_extraction"

    unsupported = processor.get_financial_statement("unknown")
    assert "reason" in unsupported
    assert unsupported["reason"] == "unsupported_statement_type"
    missing = processor.get_financial_statement("equity")
    assert "reason" in missing
    assert missing["reason"] == "statement_not_found"

    hidden_ocr = """CONSOLIDATED STATEMENTS OF OPERATIONS
(USD in millions)
Year ended December 31, 2025 2024
Revenue 100 90
Operating income 20 15
Net income 10 8"""
    ocr_path = tmp_path / "six-k-ocr-owner.html"
    ocr_path.write_text(
        "<html><body><h1>FINANCIAL RESULTS</h1>"
        f'<div style="font-size:1pt;color:white">{hidden_ocr}</div>'
        "<h2>ABOUT COMPANY</h2><p>Issuer profile.</p></body></html>",
        encoding="utf-8",
    )
    ocr_processor = BsSixKFormProcessor(
        LocalFileSource(
            path=ocr_path,
            uri="local://six-k-ocr-owner.html",
            media_type="text/html",
        ),
        form_type="6-K",
        media_type="text/html",
    )
    ocr_result = ocr_processor.get_financial_statement("income")
    _assert_financial_result_contract(ocr_result)
    assert ocr_result["periods"] == [
        {"period_end": "2025-12-31", "fiscal_year": 2025, "fiscal_period": "FY"},
        {"period_end": "2024-12-31", "fiscal_year": 2024, "fiscal_period": "FY"},
    ]
    assert [row["values"] for row in ocr_result["rows"]] == [
        [100.0, 90.0],
        [20.0, 15.0],
        [10.0, 8.0],
    ]
    assert ocr_result["scale"] == "millions"

    report_path = tmp_path / "six-k-report-owner.html"
    report_path.write_text(
        "<html><body><h1>Table of Contents</h1>"
        f"<p>{'directory entry ' * 140}</p>"
        "<h2>About this report</h2><p>Reporting basis and scope.</p>"
        "<h2>Overview</h2><p>Issuer overview.</p>"
        "<h2>Governance</h2><p>Governance approach.</p>"
        "<h2>Strategy</h2><p>Business strategy.</p>"
        "<h2>Environment</h2><p>Environmental performance.</p>"
        "</body></html>",
        encoding="utf-8",
    )
    report_processor = BsSixKFormProcessor(
        LocalFileSource(
            path=report_path,
            uri="local://six-k-report-owner.html",
            media_type="text/html",
        ),
        form_type="6-K",
        media_type="text/html",
    )
    report_sections = report_processor.list_sections()
    report_titles = [section["title"] for section in report_sections]
    assert report_titles == [
        "Table of Contents",
        "About this report",
        "Overview",
        "Governance",
        "Strategy",
        "Environment",
    ]
    assert report_processor.read_section(report_sections[2]["ref"])["content"] == "Issuer overview."


def test_six_k_statement_classification_owner_rejects_navigation_noise() -> None:
    """6-K 报表分类 owner 必须识别报表并排除导航噪声。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: marker、类型、期间、数值或单位解析漂移时抛出。
    """

    assert _classify_statement_type_for_table(
        caption="Consolidated Statements of Operations",
        headers=["Revenue", "Net income"],
        context_before="",
    ) == "income"
    assert _classify_statement_type_for_table(
        caption="Table of Contents",
        headers=[],
        context_before="",
    ) is None


def test_ocr_quarter_token_owner_projects_periods_values_currency_and_scale() -> None:
    """OCR 公开提取必须从季度 token 产生可观察期间、金额、货币与倍率。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 季度 token 或业务数值投影漂移时抛出。
    """

    result = extract_statement_result_from_ocr_pages(
        statement_type="income",
        page_texts=[
            """CONSOLIDATED STATEMENTS OF OPERATIONS
Revenue Gross profit Net income
Q1 2025 Q1 2024 USD in billions
100 90 50 45 10 (8)"""
        ],
    )

    assert result is not None
    assert result["periods"] == [
        {"period_end": "2025-03-31", "fiscal_year": 2025, "fiscal_period": "Q1"},
        {"period_end": "2024-03-31", "fiscal_year": 2024, "fiscal_period": "Q1"},
    ]
    assert [row["values"] for row in result["rows"]] == [
        [100.0, 90.0],
        [50.0, 45.0],
        [10.0, -8.0],
    ]
    assert result["currency"] == "USD"
    assert result["units"] == "USD"
    assert result["scale"] == "billions"
    assert result["data_quality"] == "extracted"
