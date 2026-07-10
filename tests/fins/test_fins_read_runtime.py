"""Fins read runtime focused tests。"""

from __future__ import annotations

import pytest

from dayu.contracts.json_value import JsonValue
from dayu.fins.pipelines.sec_fiscal_fields import _extract_fiscal_from_xbrl_query
from dayu.fins.tools.read_runtime_helpers import _normalize_form_type_for_matching, _normalize_xbrl_query_payload


class _FiscalXbrlProcessor:
    """测试用 fiscal XBRL 查询处理器。"""

    def __init__(self, payload: dict[str, JsonValue]) -> None:
        """初始化查询结果。

        Args:
            payload: `query_xbrl_facts` 返回的 payload。

        Returns:
            无。

        Raises:
            无。
        """

        self._payload = payload

    def query_xbrl_facts(self, *, concepts: list[str]) -> dict[str, JsonValue]:
        """返回预设 XBRL facts payload。

        Args:
            concepts: 待查询 concept 列表。

        Returns:
            预设 XBRL facts payload。

        Raises:
            无。
        """

        del concepts
        return self._payload


def test_read_runtime_form_matching_consumes_domain_sec_aliases() -> None:
    """验证 read runtime form 匹配消费 domain SEC form 归一结果。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    assert _normalize_form_type_for_matching("10K") == "10-K"
    assert _normalize_form_type_for_matching("SCHEDULE 13D/A") == "SC 13D/A"
    assert _normalize_form_type_for_matching("def 14a") == "DEF 14A"


def test_xbrl_query_payload_missing_total_fails_closed() -> None:
    """processor 缺少 XBRL total 时 read runtime 不得重算掩盖。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    payload: dict[str, JsonValue] = {
        "query_params": {"concepts": ["Revenue"]},
        "facts": [{"concept": "Revenue", "value": 100}],
    }

    with pytest.raises(ValueError, match="total 必须为整数"):
        _normalize_xbrl_query_payload(payload=payload, default_concepts=["Revenue"])


def test_xbrl_query_payload_non_int_total_fails_closed() -> None:
    """processor 返回非整数 XBRL total 时 read runtime 不得重算掩盖。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    payload: dict[str, JsonValue] = {
        "query_params": {"concepts": ["Revenue"]},
        "facts": [{"concept": "Revenue", "value": 100}],
        "total": "1",
    }

    with pytest.raises(ValueError, match="total 必须为整数"):
        _normalize_xbrl_query_payload(payload=payload, default_concepts=["Revenue"])


def test_xbrl_query_payload_mismatched_raw_total_fails_closed_before_dedup() -> None:
    """processor raw total 与 raw facts 数量不一致时必须先失败。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    payload: dict[str, JsonValue] = {
        "query_params": {"concepts": ["Revenue"]},
        "facts": [
            {"concept": "Revenue", "value": 100},
            {"concept": "Revenue", "value": 100},
        ],
        "total": 1,
    }

    with pytest.raises(ValueError, match="total 必须等于 raw facts 数量"):
        _normalize_xbrl_query_payload(payload=payload, default_concepts=["Revenue"])


def test_xbrl_query_payload_preserves_processor_total_after_dedup() -> None:
    """read runtime 去重后必须保留 processor raw total 并单独投影去重数量。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    payload: dict[str, JsonValue] = {
        "query_params": {"concepts": ["Revenue"]},
        "facts": [
            {
                "concept": "Revenue",
                "value": 100,
                "unit": "USD",
                "period_end": "2025-12-31",
            },
            {
                "concept": "Revenue",
                "value": 100,
                "unit": "USD",
                "period_end": "2025-12-31",
            },
        ],
        "total": 2,
        "data_quality": "xbrl",
    }

    normalized = _normalize_xbrl_query_payload(payload=payload, default_concepts=["Revenue"])

    assert normalized["total"] == 2
    assert normalized["deduped_fact_count"] == 1
    assert len(normalized["facts"]) == 1


def test_sec_fiscal_inference_rejects_invalid_xbrl_total() -> None:
    """SEC fiscal inference 直接消费 processor 时也必须拒绝坏 total。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    processor = _FiscalXbrlProcessor(
        {
            "query_params": {"concepts": ["Revenue"]},
            "facts": [{"concept": "Revenue", "fiscal_year": 2025, "fiscal_period": "FY"}],
            "total": 0,
        }
    )

    assert _extract_fiscal_from_xbrl_query(processor) == (None, None)
