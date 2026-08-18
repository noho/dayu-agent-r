"""Company ticker identity owner contract 测试。"""

from __future__ import annotations

import pytest

from dayu.contracts.json_value import JsonValue
from dayu.fins.domain.document_models import CompanyMeta
from dayu.fins.ticker_normalization import (
    build_company_ticker_identity,
    normalize_ticker,
)


@pytest.mark.parametrize(
    ("raw_ticker", "expected_canonical"),
    [
        ("AAPL", "AAPL"),
        ("AAPL.US", "AAPL"),
        ("BRK.B", "BRK-B"),
        ("V.BA", "V-BA"),
        ("AAPL.SW", "AAPL-SW"),
        ("600519.SH", "600519"),
        ("SZ.000333", "000333"),
        ("700.HK", "0700"),
    ],
)
def test_normalize_ticker_supports_identity_grammar(
    raw_ticker: str,
    expected_canonical: str,
) -> None:
    """唯一 grammar 应覆盖 US/CN/HK 与多字符单分节 ticker。

    Args:
        raw_ticker: 原始 ticker。
        expected_canonical: 期望 canonical ticker。

    Returns:
        无。

    Raises:
        AssertionError: grammar 或 canonicalization 漂移时抛出。
    """

    assert normalize_ticker(raw_ticker).canonical == expected_canonical


@pytest.mark.parametrize("valid_ticker", ["ABCDEFGH", "ABC-DEFG"])
def test_us_ticker_eight_character_boundary_is_valid(valid_ticker: str) -> None:
    """US ticker 完整 canonical 字面长度八字符应有效。

    Args:
        valid_ticker: 八字符 ticker。

    Returns:
        无。

    Raises:
        AssertionError: 合法长度被拒绝时抛出。
    """

    assert normalize_ticker(valid_ticker).canonical == valid_ticker


@pytest.mark.parametrize("invalid_ticker", ["ABCDEFGHI", "ABCD-DEFG", "A.B.C", "A."])
def test_us_ticker_invalid_shape_or_nine_character_boundary_fails(
    invalid_ticker: str,
) -> None:
    """九字符、多个分节或空分节 ticker 应失败关闭。

    Args:
        invalid_ticker: 非法 ticker。

    Returns:
        无。

    Raises:
        AssertionError: 非法 ticker 未抛 ``ValueError`` 时抛出。
    """

    with pytest.raises(ValueError):
        normalize_ticker(invalid_ticker)


def test_build_company_ticker_identity_stably_deduplicates_equivalent_aliases() -> None:
    """builder 应排除 canonical-equivalent alias 并稳定保留不同声明。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: identity 字段或 stable dedupe 漂移时抛出。
    """

    identity = build_company_ticker_identity(
        "AAPL",
        ("AAPL", "US.AAPL", "MSFT", "msft.us", "V.BA", "0700.HK"),
    )

    assert identity.canonical_ticker == "AAPL"
    assert identity.market == "US"
    assert identity.exchange is None
    assert identity.accepted_aliases == ("MSFT", "V-BA", "0700")
    assert identity.lookup_tickers() == ("AAPL", "MSFT", "V-BA", "0700")


def test_build_company_ticker_identity_trusts_distinct_declared_alias() -> None:
    """builder 不应联网核验或纠正语法合法的显式公司关系声明。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: ``DELTA,MSFT`` 被过滤或重写时抛出。
    """

    identity = build_company_ticker_identity("DELTA", ("MSFT",))

    assert identity.accepted_aliases == ("MSFT",)


@pytest.mark.parametrize("invalid_alias", ["", "A.B.C", "Apple Inc."])
def test_build_company_ticker_identity_rejects_invalid_alias(invalid_alias: str) -> None:
    """任一空或非法声明 alias 应使整个 identity 构造失败。

    Args:
        invalid_alias: 非法 alias。

    Returns:
        无。

    Raises:
        AssertionError: builder 未失败关闭时抛出。
    """

    with pytest.raises(ValueError):
        build_company_ticker_identity("AAPL", (invalid_alias,))


def test_company_meta_flat_json_round_trip_uses_identity_projection() -> None:
    """CompanyMeta flat JSON 应只从 ticker identity 投影 canonical 与 aliases。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: durable JSON shape 或 round-trip identity 漂移时抛出。
    """

    company_meta = CompanyMeta(
        company_id="AAPL_US",
        company_name="Apple Inc.",
        ticker_identity=build_company_ticker_identity(
            "AAPL",
            ("AAPL.US", "MSFT", "V.BA"),
        ),
        resolver_version="test",
        updated_at="2026-08-14T00:00:00+00:00",
    )

    payload = company_meta.to_dict()
    assert payload == {
        "company_id": "AAPL_US",
        "company_name": "Apple Inc.",
        "ticker": "AAPL",
        "market": "US",
        "resolver_version": "test",
        "updated_at": "2026-08-14T00:00:00+00:00",
        "ticker_aliases": ["MSFT", "V-BA"],
    }
    assert CompanyMeta.from_dict(payload) == company_meta


@pytest.mark.parametrize(
    "invalid_payload",
    [
        {
            "company_id": "AAPL_US",
            "company_name": "Apple Inc.",
            "ticker": "AAPL",
            "market": "US",
            "resolver_version": "test",
            "updated_at": "2026-08-14T00:00:00+00:00",
        },
        {
            "company_id": "AAPL_US",
            "company_name": "Apple Inc.",
            "ticker": "AAPL",
            "market": "US",
            "resolver_version": "test",
            "updated_at": "2026-08-14T00:00:00+00:00",
            "ticker_aliases": "MSFT",
        },
        {
            "company_id": "AAPL_US",
            "company_name": "Apple Inc.",
            "ticker": "AAPL",
            "market": "CN",
            "resolver_version": "test",
            "updated_at": "2026-08-14T00:00:00+00:00",
            "ticker_aliases": ["MSFT"],
        },
        {
            "company_id": "AAPL_US",
            "company_name": "Apple Inc.",
            "ticker": "AAPL",
            "market": "US",
            "resolver_version": "test",
            "updated_at": "2026-08-14T00:00:00+00:00",
            "ticker_aliases": [""],
        },
    ],
)
def test_company_meta_from_dict_rejects_non_strict_identity_json(
    invalid_payload: dict[str, JsonValue],
) -> None:
    """CompanyMeta 应拒绝缺失、wrong type、market mismatch 与非法 alias。

    Args:
        invalid_payload: 不符合 strict flat JSON contract 的 payload。

    Returns:
        无。

    Raises:
        AssertionError: 非法 payload 未失败关闭时抛出。
    """

    with pytest.raises((KeyError, ValueError)):
        CompanyMeta.from_dict(invalid_payload)
