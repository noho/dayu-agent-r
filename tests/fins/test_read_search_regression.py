"""取消 owner 迁移后的公开搜索语义回归，使用真实 Markdown processor。"""

from pathlib import Path

import pytest

from dayu.fins.service_runtime import DefaultFinsRuntime
import tests.tools.test_combined_tools_acceptance as combined_fixture

_REPORT = """# Business
Competition in the cloud market increased. Competitors compete on price and services.
Annual recurring revenue and subscriptions grew. Revenue growth reflects new customer contracts.
Capital expenditures expanded data centers. Research and development expenses increased.

# Risk Factors
Competition risks affect operating margins. Cybersecurity threats affect our supply chain.
Foreign exchange risk and interest rate risk remain significant.

# Management Discussion and Analysis
Revenue and operating cash flow increased. Cash flows from operations funded capital expenditure.
Net income and operating income grew. Gross margins and diluted earnings per share improved.

# Governance and Executive Compensation
Executive compensation includes performance awards. Non-competition agreements apply to directors.
Board of directors and audit committee review internal controls.

# Employees
We have full time employees in engineering and sales. Human capital management supports recruitment.

# Legal Proceedings
Litigation and legal proceedings include non-competition agreements and patent claims.
"""


@pytest.mark.parametrize("mode", ("auto", "exact", "keyword", "semantic"))
def test_public_search_keeps_navigation_and_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    """参数：真实 workspace、fixture 内容替换、公开搜索模式。返回：无。异常：失去公开证据、导航或查询隔离。"""
    monkeypatch.setattr(combined_fixture, "_fins_fixture_markdown", lambda: _REPORT)
    root = combined_fixture._build_fins_workspace(tmp_path)
    runtime = DefaultFinsRuntime.create(workspace_root=root)
    try:
        reader = runtime.get_read_runtime()
        for query in (
            "competition",
            "revenue",
            "executive compensation",
            "cash flow",
            "risk",
            "employees",
            '"annual recurring revenue"',
            "capital-expenditures",
            "net/income",
            "gross margins",
            "cybersecurity",
            "董事会",
        ):
            result = reader.search_document(ticker="AAPL", document_id="aapl-2024-10k", query=query, mode=mode)
            assert result["document_id"] == "aapl-2024-10k"
            assert result["query"] == query
            for match in result["matches"]:
                ref = match["section"]["ref"]
                assert isinstance(ref, str)
                section = reader.read_section(ticker="AAPL", document_id="aapl-2024-10k", ref=ref)
                assert section["content"]
            if mode in {"auto", "exact"} and query in {"competition", "revenue", "employees"}:
                assert result["total_matches"] > 0
        missing = reader.search_document(
            ticker="AAPL", document_id="aapl-2024-10k", query="missing-unique-837", mode="exact"
        )
        assert missing["total_matches"] == 0
    finally:
        runtime.close()


def test_many_exact_matches_remain_grounded_when_display_budget_is_small(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """参数：真实根和内容 fixture。返回：无。异常：展示预算静默丢弃 exact 证据或导航断裂。"""
    report = "\n".join(f"# Business Segment {i}\n\nRecurring revenue grew in region {i}.\n" for i in range(20))
    monkeypatch.setattr(combined_fixture, "_fins_fixture_markdown", lambda: report)
    root = combined_fixture._build_fins_workspace(tmp_path)
    runtime = DefaultFinsRuntime.create(workspace_root=root)
    try:
        result = runtime.get_read_runtime().search_document(
            ticker="AAPL", document_id="aapl-2024-10k", query="revenue", mode="exact", display_budget=4
        )
        assert result["total_matches"] >= 20
        assert all(match["is_exact_phrase"] for match in result["matches"])
        assert all(match["section"]["ref"] for match in result["matches"])
    finally:
        runtime.close()
