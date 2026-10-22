"""SEC 确认行分类真源及数量诊断的契约测试。"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from dayu.contracts.json_value import JsonValue
from dayu.fins.domain.document_models import DownloadRejectionEntry
from dayu.fins.download_contract import FinsDownloadDocumentDisposition
from dayu.fins.pipelines.sec_download_diagnostics import warn_insufficient_filings
from dayu.fins.pipelines.sec_download_disposition import project_sec_filing_disposition
from dayu.fins.pipelines.sec_pipeline import _project_sec_document_row
from dayu.fins.storage import FsSourceDocumentRepository


@pytest.mark.parametrize(
    ("row", "expected"),
    [
        ({"status": "downloaded"}, FinsDownloadDocumentDisposition.DOWNLOADED),
        ({"status": "failed", "reason_code": "file_download_failed"}, FinsDownloadDocumentDisposition.FAILED),
        ({"status": "rejected"}, FinsDownloadDocumentDisposition.REJECTED),
        ({"status": "skipped", "skip_reason": "6k_filtered"}, FinsDownloadDocumentDisposition.REJECTED),
        ({"status": "skipped", "reason_code": "6k_filtered"}, FinsDownloadDocumentDisposition.REJECTED),
        ({"status": " skipped ", "reason_code": " 6k_filtered "}, FinsDownloadDocumentDisposition.REJECTED),
        ({"status": "skipped", "skip_reason": "already_downloaded_complete"}, FinsDownloadDocumentDisposition.SKIPPED),
        ({"status": "skipped", "reason_code": "not_modified"}, FinsDownloadDocumentDisposition.SKIPPED),
        ({"status": "skipped", "skip_reason": "rejection_registry"}, FinsDownloadDocumentDisposition.SKIPPED),
        ({"status": "skipped", "reason_code": "already_downloaded_complete"}, FinsDownloadDocumentDisposition.SKIPPED),
        ({"status": "failed", "reason_code": "6k_filtered"}, FinsDownloadDocumentDisposition.FAILED),
    ],
)
def test_disposition_projects_existing_contract_without_mutating_row(
    row: dict[str, JsonValue], expected: FinsDownloadDocumentDisposition,
) -> None:
    """确认分类只由当前状态与参与判定的原因产生，不修改输入。

    参数：row 为确认行，expected 为既有契约分类。返回：无。
    异常：断言不满足时抛出 AssertionError。
    """

    original = dict(row)
    assert project_sec_filing_disposition(row) is expected
    assert row == original


@pytest.mark.parametrize("status", [None, "", " ", "unknown", 1, True, [], {}])
def test_disposition_rejects_invalid_status(status: JsonValue) -> None:
    """非法状态不能被默认分类或宽松转换。

    参数：status 为非法状态。返回：无。异常：未拒绝时抛出 AssertionError。
    """

    with pytest.raises(ValueError):
        project_sec_filing_disposition({"status": status})
    with pytest.raises(ValueError):
        project_sec_filing_disposition({})


@pytest.mark.parametrize("field", ["skip_reason", "reason_code"])
@pytest.mark.parametrize("value", ["", " ", 1, False, [], {}])
def test_disposition_rejects_invalid_participating_reason(field: str, value: JsonValue) -> None:
    """参与 skipped 分类的原因必须严格校验，即使另一原因已表示拒绝。

    参数：field 为原因字段，value 为非法内容。返回：无。
    异常：未拒绝时抛出 AssertionError。
    """

    row: dict[str, JsonValue] = {"status": "skipped", "skip_reason": "6k_filtered", "reason_code": "6k_filtered"}
    row[field] = value
    with pytest.raises(ValueError):
        project_sec_filing_disposition(row)
    with pytest.raises(ValueError):
        warn_insufficient_filings({"6-K": dt.date(2025, 1, 1)}, [row], {})


@pytest.mark.parametrize(
    "reasons",
    [
        {},
        {"skip_reason": None},
        {"reason_code": None},
        {"skip_reason": None, "reason_code": None},
        {"skip_reason": "6k_filtered", "reason_code": "already_downloaded_complete"},
        {"skip_reason": "already_downloaded_complete", "reason_code": "6k_filtered"},
        {"skip_reason": " 6k_filtered ", "reason_code": " already_downloaded_complete "},
    ],
)
def test_skipped_reason_contract_rejects_same_row_before_warning_and_public_projection(
    tmp_path: Path, reasons: dict[str, JsonValue],
) -> None:
    """缺因或冲突行在唯一 owner 拒绝，不能先计有效或生成矛盾的公开行。

    参数：tmp_path 为真实隔离仓储根，reasons 为非法原因对。返回：无。
    异常：三处未同源拒绝或改动输入时抛出 AssertionError。
    """

    row: dict[str, JsonValue] = {
        "document_id": "fil-invalid-skipped", "status": "skipped", "form_type": "6-K",
        "filing_date": "2025-01-01", "report_date": None, **reasons,
    }
    original = dict(row)
    with pytest.raises(ValueError) as owner_error:
        project_sec_filing_disposition(row)
    with pytest.raises(ValueError) as warning_error:
        warn_insufficient_filings({"6-K": dt.date(2025, 1, 1)}, [row], {})
    with pytest.raises(ValueError) as public_error:
        _project_sec_document_row(row, ticker="TCOM", source_repository=FsSourceDocumentRepository(tmp_path))
    assert str(warning_error.value) == str(public_error.value) == str(owner_error.value)
    assert row == original


@pytest.mark.parametrize(
    ("reasons", "expected", "category"),
    [
        ({"skip_reason": "6k_filtered"}, FinsDownloadDocumentDisposition.REJECTED, "6k_filtered"),
        ({"reason_code": "6k_filtered"}, FinsDownloadDocumentDisposition.REJECTED, "6k_filtered"),
        ({"skip_reason": "already_downloaded_complete"}, FinsDownloadDocumentDisposition.SKIPPED, "already_downloaded_complete"),
        ({"reason_code": "already_downloaded_complete"}, FinsDownloadDocumentDisposition.SKIPPED, "already_downloaded_complete"),
        ({"skip_reason": "6k_filtered", "reason_code": "6k_filtered"}, FinsDownloadDocumentDisposition.REJECTED, "6k_filtered"),
        ({"skip_reason": " already_downloaded_complete ", "reason_code": "already_downloaded_complete"}, FinsDownloadDocumentDisposition.SKIPPED, "already_downloaded_complete"),
        ({"skip_reason": None, "reason_code": "6k_filtered"}, FinsDownloadDocumentDisposition.REJECTED, "6k_filtered"),
        ({"skip_reason": "already_downloaded_complete", "reason_code": None}, FinsDownloadDocumentDisposition.SKIPPED, "already_downloaded_complete"),
    ],
)
def test_legal_skipped_reasons_keep_owner_warning_and_public_row_consistent(
    tmp_path: Path, reasons: dict[str, JsonValue], expected: FinsDownloadDocumentDisposition, category: str,
) -> None:
    """单原因、双同值及合法 null 不改变既有分类或公开原因。

    参数：tmp_path 为真实仓储根，reasons 为合法原因，expected/category 为原契约结果。
    返回：无。异常：三处分类或原因不一致时抛出 AssertionError。
    """

    row: dict[str, JsonValue] = {
        "document_id": "fil-valid-skipped", "status": "skipped", "form_type": "6-K",
        "filing_date": "2025-01-01", "report_date": None, **reasons,
    }
    original = dict(row)
    assert project_sec_filing_disposition(row) is expected
    public = _project_sec_document_row(row, ticker="TCOM", source_repository=FsSourceDocumentRepository(tmp_path))
    assert public.disposition is expected
    assert public.reason_category == category
    assert public.artifact_locator is None
    warnings = warn_insufficient_filings({"6-K": dt.date(2025, 1, 1)}, [row], {})
    effective_count = 0 if expected is FinsDownloadDocumentDisposition.REJECTED else 1
    assert len(warnings) == 1 and f"有效落盘数 {effective_count} 低于期望 3" in warnings[0]
    assert row == original


@pytest.mark.parametrize(
    ("forms", "minimum", "label"),
    [
        (("10-K", "20-F"), 5, "年报（10-K/20-F）"),
        (("10-Q",), 3, "季报（10-Q）"),
        (("6-K",), 3, "季报（6-K）"),
        (("DEF 14A",), 2, "DEF 14A"),
    ],
)
def test_quantity_warning_uses_only_effective_dispositions(
    forms: tuple[str, ...], minimum: int, label: str,
) -> None:
    """各组阈值仅统计成功和完整跳过，不让拒绝或失败补足数量。

    参数：forms 为请求组，minimum 为既有阈值，label 为业务说明。
    返回：无。异常：计数或阈值错误时抛出 AssertionError。
    """

    windows = {form: dt.date(2025, 1, 1) for form in forms}
    rows: list[dict[str, JsonValue]] = [
        {"status": "downloaded", "form_type": forms[index % len(forms)]}
        if index % 2 else
        {"status": "skipped", "form_type": forms[index % len(forms)],
         "skip_reason": "already_downloaded_complete", "reason_code": "already_downloaded_complete"}
        for index in range(minimum)
    ]
    rows.extend([
        {"status": "rejected", "form_type": forms[0]},
        {"status": "failed", "form_type": forms[0]},
        {"status": "downloaded", "form_type": "8-K"},
    ])
    assert warn_insufficient_filings(windows, rows, {}) == []
    rows.pop(0)
    warnings = warn_insufficient_filings(windows, rows, {})
    assert len(warnings) == 1
    assert f"有效落盘数 {minimum - 1} 低于期望 {minimum}" in warnings[0]
    assert label in warnings[0]
    assert warn_insufficient_filings({}, rows, {}) == []


def test_rejection_registry_only_supplements_warning_text() -> None:
    """注册表补充说明不增加本次有效数，也不改变原始拒绝行。

    参数：无。返回：无。异常：说明或计数错误时抛出 AssertionError。
    """

    entry = DownloadRejectionEntry(
        document_id="fil-rejected", reason="6k_filtered", category="NO_EX99_OR_XBRL",
        form_type="6-K", filing_date="2025-01-01", download_version="test-version",
    )
    rows: list[dict[str, JsonValue]] = [
        {"status": "skipped", "form_type": "6-K", "reason_code": "6k_filtered"},
    ]
    warnings = warn_insufficient_filings({"6-K": dt.date(2025, 1, 1)}, rows, {entry.document_id: entry})
    assert len(warnings) == 1
    assert "有效落盘数 0 低于期望 3" in warnings[0]
    assert "另有 1 份 6-K 被分类过滤" in warnings[0]
