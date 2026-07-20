"""Fins read runtime focused tests。"""

from __future__ import annotations

from copy import deepcopy

import pytest

from dayu.contracts.json_value import JsonValue
from dayu.fins.pipelines.sec_fiscal_fields import _extract_fiscal_from_xbrl_query
from dayu.fins.tools.cache import ProcessorCacheKey, ProcessorLRUCache
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


def test_generic_lru_returns_replaced_evicted_and_cleared_values() -> None:
    """generic LRU 应把所有 displaced values 返回给资源 owner。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: replacement、capacity eviction、evict 或 clear 丢失旧值时抛出。
    """

    cache = ProcessorLRUCache[str](max_entries=2)
    first_key = ProcessorCacheKey(ticker="AAPL", document_id="doc-1")
    second_key = ProcessorCacheKey(ticker="AAPL", document_id="doc-2")
    third_key = ProcessorCacheKey(ticker="AAPL", document_id="doc-3")

    assert cache.put(first_key, "first") == ()
    assert cache.put(first_key, "replacement") == ("first",)
    assert cache.put(second_key, "second") == ()
    assert cache.put(third_key, "third") == ("replacement",)
    assert cache.evict_if(second_key, "wrong-instance") is None
    assert cache.evict_if(second_key, "second") == "second"
    assert cache.put(second_key, "second-new") == ()
    assert cache.evict(second_key) == "second-new"
    assert cache.evict(second_key) is None
    assert cache.clear() == ("third",)


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


def test_xbrl_query_payload_missing_facts_fails_closed() -> None:
    """XBRL producer 缺少必填 facts 时必须在规范化前失败。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    payload: dict[str, JsonValue] = {
        "query_params": {"concepts": ["Revenue"]},
        "data_quality": "xbrl",
    }

    with pytest.raises(ValueError, match="缺少必填字段: facts"):
        _normalize_xbrl_query_payload(
            ticker="AAPL",
            document_id="doc-1",
            citation={"source_type": "SEC_EDGAR"},
            payload=payload,
        )


def test_xbrl_query_payload_rejects_non_flat_query_params() -> None:
    """XBRL query params 必须保持扁平且 concepts 为字符串数组。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    payload: dict[str, JsonValue] = {
        "query_params": {"concepts": {"nested": ["Revenue"]}},
        "facts": [{"concept": "Revenue", "value": 100}],
        "data_quality": "xbrl",
    }

    with pytest.raises(ValueError, match="concepts 必须为非空字符串数组"):
        _normalize_xbrl_query_payload(
            ticker="AAPL",
            document_id="doc-1",
            citation={"source_type": "SEC_EDGAR"},
            payload=payload,
        )


def test_xbrl_query_payload_preserves_raw_input_during_normalization() -> None:
    """规范化与稳定去重不得修改 producer payload、列表或 fact 深层值。

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
                "dimensions": {"Region": ["Global"]},
            },
            {
                "concept": "Revenue",
                "value": 100,
                "unit": "USD",
                "period_end": "2025-12-31",
                "dimensions": {"Region": ["Global"]},
            },
        ],
        "data_quality": "xbrl",
    }
    original = deepcopy(payload)

    _normalize_xbrl_query_payload(
        ticker="AAPL",
        document_id="doc-1",
        citation={"source_type": "SEC_EDGAR"},
        payload=payload,
    )

    assert payload == original


def test_xbrl_query_payload_stable_dedup_projects_unique_fact_count() -> None:
    """相同稳定键的 facts 只返回首个最佳项且唯一计数等于结果长度。

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
        "data_quality": "xbrl",
    }

    normalized = _normalize_xbrl_query_payload(
        ticker="AAPL",
        document_id="doc-1",
        citation={"source_type": "SEC_EDGAR"},
        payload=payload,
    )

    assert set(normalized) == {
        "ticker",
        "document_id",
        "citation",
        "query_params",
        "facts",
        "fact_count",
        "data_quality",
    }
    assert normalized["fact_count"] == 1
    assert len(normalized["facts"]) == 1
    assert normalized["query_params"] == payload["query_params"]
    assert normalized["query_params"] is not payload["query_params"]


def test_xbrl_query_payload_preserves_owner_quality_and_optional_reason() -> None:
    """公共投影必须机械保留 producer quality 与存在的可选 reason。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 唯一计数缺失或 quality/reason 被重算时抛出。
    """

    payload: dict[str, JsonValue] = {
        "query_params": {"concepts": ["Revenue"]},
        "facts": [{"concept": "Revenue", "value": 100}],
        "data_quality": "partial",
        "reason": "query_partially_failed",
    }

    normalized = _normalize_xbrl_query_payload(
        ticker="AAPL",
        document_id="doc-1",
        citation={"source_type": "SEC_EDGAR"},
        payload=payload,
    )

    assert normalized["fact_count"] == len(normalized["facts"]) == 1
    assert normalized["data_quality"] == "partial"
    assert "reason" in normalized
    assert normalized["reason"] == "query_partially_failed"


def test_xbrl_query_payload_zero_hit_has_single_count_and_no_reason() -> None:
    """合法零命中只投影零值 fact_count，完整质量不补 reason。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 零命中公共字段或可选原因存在性错误时抛出。
    """

    payload: dict[str, JsonValue] = {
        "query_params": {"concepts": ["Revenue"]},
        "facts": [],
        "data_quality": "xbrl",
    }

    normalized = _normalize_xbrl_query_payload(
        ticker="AAPL",
        document_id="doc-1",
        citation={"source_type": "SEC_EDGAR"},
        payload=payload,
    )

    assert normalized["facts"] == []
    assert normalized["fact_count"] == 0
    assert "reason" not in normalized


def test_sec_fiscal_inference_consumes_countless_xbrl_contract() -> None:
    """SEC fiscal inference 必须直接消费无 count 的 XBRL producer contract。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: fiscal consumer 仍要求 count 或丢失财期时抛出。
    """

    processor = _FiscalXbrlProcessor(
        {
            "query_params": {"concepts": ["Revenue"]},
            "facts": [{"concept": "Revenue", "fiscal_year": 2025, "fiscal_period": "FY"}],
            "data_quality": "xbrl",
        }
    )

    assert _extract_fiscal_from_xbrl_query(processor) == (2025, "FY")
