"""Fins typed 批量上传计划 owner contract 测试。"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import cast

import pytest

import dayu.fins.upload_batch as upload_batch
from dayu.fins.upload_batch import (
    BatchUploadAction,
    UploadBatchPlanEmptyError,
    UploadBatchPlanRequest,
    UploadBatchPlanUsageError,
    generate_upload_batch_plan,
)


def test_real_filesystem_builds_typed_old_aligned_plan(tmp_path: Path) -> None:
    """真实文件系统扫描必须产生 filing/material/skipped 三分 typed plan。"""

    source_dir = tmp_path / "source"
    nested_dir = source_dir / "2024Q1"
    nested_dir.mkdir(parents=True)
    annual = source_dir / "2024FY_AAPL_Annual_Report.htm"
    duplicate = source_dir / "2024FY_AAPL_Announcement.htm"
    call = source_dir / "2024FY_AAPL_Earnings_Call_Transcript.htm"
    quarterly = nested_dir / "季度正式报告.htm"
    unsupported = source_dir / "notes.exe"
    for path in (annual, duplicate, call, quarterly, unsupported):
        path.write_text("fixture", encoding="utf-8")

    plan = generate_upload_batch_plan(
        UploadBatchPlanRequest(ticker="AAPL", source_dir=source_dir)
    )

    assert plan.recursive is True
    assert [(entry.fiscal_year, entry.fiscal_period) for entry in plan.recognized_entries] == [
        (2024, "FY"),
        (2024, "Q1"),
    ]
    assert plan.recognized_entries[0].file == annual.resolve()
    assert [entry.form_type for entry in plan.material_entries] == ["EARNINGS_CALL"]
    assert plan.material_entries[0].file == call.resolve()
    assert {entry.reason_code for entry in plan.skipped_entries} == {
        "duplicate_period",
        "unsupported_suffix",
    }


@pytest.mark.parametrize(
    ("filename", "expected_period"),
    (
        ("2024Q4季报.pdf", "Q4"),
        ("2024Q4季度报告.pdf", "FY"),
        ("2024Q4年报.pdf", "FY"),
    ),
)
def test_q4_filename_oracles(
    tmp_path: Path,
    filename: str,
    expected_period: str,
) -> None:
    """Q4 必须只按 child 完整 filename 与 literal ``季报`` 判定。"""

    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / filename).write_text("filing", encoding="utf-8")

    plan = generate_upload_batch_plan(
        UploadBatchPlanRequest(ticker="AAPL", source_dir=source_dir)
    )

    assert plan.recognized_entries[0].fiscal_period == expected_period


@pytest.mark.parametrize(
    ("filename", "expected_period"),
    (("季报.pdf", "Q4"), ("季度报告.pdf", "FY")),
)
def test_q4_direct_parent_oracles(
    tmp_path: Path,
    filename: str,
    expected_period: str,
) -> None:
    """direct ``20YYQ4`` parent fallback 仍只检查 child literal ``季报``。"""

    source_dir = tmp_path / "source"
    parent = source_dir / "2021Q4"
    parent.mkdir(parents=True)
    (parent / filename).write_text("filing", encoding="utf-8")

    plan = generate_upload_batch_plan(
        UploadBatchPlanRequest(ticker="AAPL", source_dir=source_dir)
    )

    entry = plan.recognized_entries[0]
    assert entry.fiscal_year == 2021
    assert entry.fiscal_period == expected_period


def test_explicit_fiscal_fields_override_inference_independently(tmp_path: Path) -> None:
    """显式 year/period 必须逐字段覆盖推断，而不是全有或全无覆盖。"""

    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "2022Q2报告.pdf").write_text("filing", encoding="utf-8")

    plan = generate_upload_batch_plan(
        UploadBatchPlanRequest(
            ticker="AAPL",
            aliases=("MSFT",),
            source_dir=source_dir,
            fiscal_year=2024,
            amended=True,
            filing_date=" 2025-01-30 ",
            report_date="2024-12-31",
            company_name=" Apple Inc. ",
            overwrite=True,
        )
    )

    entry = plan.recognized_entries[0]
    assert (entry.fiscal_year, entry.fiscal_period) == (2024, "Q2")
    assert entry.aliases == ("MSFT",)
    assert entry.amended is True
    assert entry.filing_date == "2025-01-30"
    assert entry.report_date == "2024-12-31"
    assert entry.company_name == "Apple Inc."
    assert entry.overwrite is True


def test_missing_fiscal_field_is_typed_skip(tmp_path: Path) -> None:
    """普通 filing 缺 year 或 period 时必须进入 typed skip evidence。"""

    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "2024报告.pdf").write_text("filing", encoding="utf-8")

    with pytest.raises(UploadBatchPlanEmptyError) as raised:
        generate_upload_batch_plan(
            UploadBatchPlanRequest(ticker="AAPL", source_dir=source_dir)
        )

    assert raised.value.skipped_entries[0].reason_code == "missing_fiscal_metadata"


def test_material_routing_precedence_override_and_name(tmp_path: Path) -> None:
    """material 必须首项路由、只对已路由项覆盖 form，并按 OLD 派生名称。"""

    source_dir = tmp_path / "source"
    parent = source_dir / "2024Q2"
    parent.mkdir(parents=True)
    material = parent / "HKEX财务报表 Earnings Call Presentation.pdf"
    filing = source_dir / "2024FY正式报告.pdf"
    material.write_text("material", encoding="utf-8")
    filing.write_text("filing", encoding="utf-8")

    plan = generate_upload_batch_plan(
        UploadBatchPlanRequest(
            ticker="AAPL",
            source_dir=source_dir,
            material_form="EARNINGS_PRESENTATION",
        )
    )

    entry = plan.material_entries[0]
    assert entry.form_type == "EARNINGS_PRESENTATION"
    assert entry.material_name == "2024Q2 财务报表 Earnings Call Presentation"
    assert entry.fiscal_year == 2024
    assert entry.fiscal_period == "Q2"
    assert plan.recognized_entries[0].file == filing.resolve()


def test_invalid_material_form_is_rejected_by_fins_owner(tmp_path: Path) -> None:
    """非法 material form 候选必须只在 Fins request boundary 被拒绝。"""

    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "2024 Earnings Call Transcript.pdf").write_text(
        "material",
        encoding="utf-8",
    )

    with pytest.raises(
        UploadBatchPlanUsageError,
        match="unsupported material form: ESG_REPORT",
    ):
        generate_upload_batch_plan(
            UploadBatchPlanRequest(
                ticker="AAPL",
                source_dir=source_dir,
                material_form="ESG_REPORT",
            )
        )


def test_same_period_priority_and_stable_path_tie(tmp_path: Path) -> None:
    """同期去重必须先按正式报告优先级，再按 stable relative path 决胜。"""

    source_dir = tmp_path / "source"
    source_dir.mkdir()
    names = (
        "2024FY Z公告.pdf",
        "2024FY B年度报告.pdf",
        "2024FY A年度报告.pdf",
    )
    for name in names:
        (source_dir / name).write_text("filing", encoding="utf-8")

    plan = generate_upload_batch_plan(
        UploadBatchPlanRequest(ticker="AAPL", source_dir=source_dir)
    )

    assert plan.recognized_entries[0].file.name == "2024FY A年度报告.pdf"
    assert [entry.reason_code for entry in plan.skipped_entries] == [
        "duplicate_period",
        "duplicate_period",
    ]


def test_annual_cap_is_five_newest_years(tmp_path: Path) -> None:
    """annual 必须按年份降序最多保留五份。"""

    source_dir = tmp_path / "source"
    source_dir.mkdir()
    for year in range(2018, 2025):
        (source_dir / f"{year}FY年度报告.pdf").write_text("filing", encoding="utf-8")

    plan = generate_upload_batch_plan(
        UploadBatchPlanRequest(ticker="AAPL", source_dir=source_dir)
    )

    assert [entry.fiscal_year for entry in plan.recognized_entries] == [
        2024,
        2023,
        2022,
        2021,
        2020,
    ]
    assert [entry.reason_code for entry in plan.skipped_entries] == [
        "annual_cap",
        "annual_cap",
    ]


def test_periodic_keeps_only_latest_year_in_business_order(tmp_path: Path) -> None:
    """periodic 必须只保留最新年度并按 Q1/H1/Q2/Q3/Q4 顺序排列。"""

    source_dir = tmp_path / "source"
    source_dir.mkdir()
    for name in (
        "2023Q1季报.pdf",
        "2024Q3季报.pdf",
        "2024H1中报.pdf",
        "2024Q1季报.pdf",
        "2024Q2季报.pdf",
        "2024Q4季报.pdf",
    ):
        (source_dir / name).write_text("filing", encoding="utf-8")

    plan = generate_upload_batch_plan(
        UploadBatchPlanRequest(ticker="AAPL", source_dir=source_dir)
    )

    assert [entry.fiscal_period for entry in plan.recognized_entries] == [
        "Q1",
        "H1",
        "Q2",
        "Q3",
        "Q4",
    ]
    assert len(plan.recognized_entries) <= 6
    assert plan.skipped_entries[0].reason_code == "periodic_older_year"


def test_material_caps_use_filtered_filing_count_and_no_financial_cap(
    tmp_path: Path,
) -> None:
    """presentation=6、call=filtered filing count，财务报表必须无 cap。"""

    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "2024FY年度报告.pdf").write_text("filing", encoding="utf-8")
    for year in range(2017, 2024):
        (source_dir / f"{year} Investor Day Presentation.pdf").write_text(
            "presentation", encoding="utf-8"
        )
    for index in range(3):
        (source_dir / f"2024 Earnings Call Transcript {index}.pdf").write_text(
            "call", encoding="utf-8"
        )
    for index in range(8):
        (source_dir / f"2024 财务报表 {index}.pdf").write_text(
            "statements", encoding="utf-8"
        )

    plan = generate_upload_batch_plan(
        UploadBatchPlanRequest(ticker="AAPL", source_dir=source_dir)
    )

    forms = [entry.form_type for entry in plan.material_entries]
    assert forms.count("EARNINGS_PRESENTATION") == 6
    assert forms.count("EARNINGS_CALL") == 1
    assert forms.count("FINANCIAL_STATEMENTS") == 8
    assert [entry.reason_code for entry in plan.skipped_entries].count("material_cap") == 3


def test_zero_recognized_filings_skips_all_calls_but_keeps_financials(
    tmp_path: Path,
) -> None:
    """filtered filing 为零时 call cap 必须为零，不能擅自保留一份。"""

    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "2024 Earnings Call Transcript.pdf").write_text("call", encoding="utf-8")
    financial = source_dir / "2024 财务报表.pdf"
    financial.write_text("financial", encoding="utf-8")

    plan = generate_upload_batch_plan(
        UploadBatchPlanRequest(ticker="AAPL", source_dir=source_dir)
    )

    assert [entry.form_type for entry in plan.material_entries] == [
        "FINANCIAL_STATEMENTS"
    ]
    assert plan.skipped_entries[0].reason_code == "material_cap"


@pytest.mark.parametrize("action", ("auto", "create", "update"))
def test_batch_actions_propagate(action: str, tmp_path: Path) -> None:
    """auto/create/update 必须原样传播到 typed entries。"""

    source_dir = tmp_path / action
    source_dir.mkdir()
    (source_dir / "2024FY年报.pdf").write_text("filing", encoding="utf-8")

    plan = generate_upload_batch_plan(
        UploadBatchPlanRequest(
            ticker="AAPL",
            source_dir=source_dir,
            action=cast(BatchUploadAction, action),
        )
    )

    assert plan.recognized_entries[0].action == action


def test_unsupported_suffix_is_readable_skip_evidence(tmp_path: Path) -> None:
    """unsupported suffix 必须由 Fins owner 产生 typed、可读 skip。"""

    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "2024FY年报.exe").write_text("unsupported", encoding="utf-8")

    with pytest.raises(UploadBatchPlanEmptyError) as raised:
        generate_upload_batch_plan(
            UploadBatchPlanRequest(ticker="AAPL", source_dir=source_dir)
        )

    skipped = raised.value.skipped_entries[0]
    assert skipped.reason_code == "unsupported_suffix"
    assert ".exe" in skipped.reason


@pytest.mark.parametrize(
    "suffix",
    (
        ".pdf",
        ".docx",
        ".pptx",
        ".htm",
        ".html",
        ".xhtml",
        ".md",
        ".txt",
        ".csv",
        ".xlsx",
        ".xbrl",
        ".xml",
        ".json",
    ),
)
def test_batch_enters_every_frozen_primary_suffix(tmp_path: Path, suffix: str) -> None:
    """batch 必须让每个冻结 primary suffix 进入 standalone filing 计划。

    Args:
        tmp_path: 用于创建单格式 source 的临时目录。
        suffix: 当前冻结 primary 扩展名。

    Returns:
        无。

    Raises:
        AssertionError: batch primary admission 与 capability 真源漂移时抛出。
    """

    source_dir = tmp_path / "source"
    source_dir.mkdir()
    filing = source_dir / f"2024FY正式年报{suffix}"
    filing.write_text("filing", encoding="utf-8")

    plan = generate_upload_batch_plan(UploadBatchPlanRequest(ticker="AAPL", source_dir=source_dir))

    assert [entry.file for entry in plan.recognized_entries] == [filing.resolve()]
    assert plan.material_entries == ()
    assert plan.skipped_entries == ()


@pytest.mark.parametrize(
    "suffix",
    (
        ".doc",
        ".ppt",
        ".xls",
        ".zip",
        ".xsd",
        ".text",
        ".rmd",
        ".qmd",
        ".xlsm",
        ".potx",
    ),
)
def test_batch_skips_legacy_companion_only_and_unselected_suffixes(
    tmp_path: Path,
    suffix: str,
) -> None:
    """batch 必须稳定 skip 非产品 primary，且不得自动关联 XSD companion。

    Args:
        tmp_path: 用于创建单格式 source 的临时目录。
        suffix: 当前冻结 skip 扩展名。

    Returns:
        无。

    Raises:
        AssertionError: skip code、standalone admission 或 association 边界漂移时抛出。
    """

    source_dir = tmp_path / "source"
    source_dir.mkdir()
    candidate = source_dir / f"2024FY正式年报{suffix}"
    candidate.write_text("filing", encoding="utf-8")

    with pytest.raises(UploadBatchPlanEmptyError) as exc_info:
        generate_upload_batch_plan(UploadBatchPlanRequest(ticker="AAPL", source_dir=source_dir))

    assert exc_info.value.skipped_entries[0].path == candidate.resolve()
    assert exc_info.value.skipped_entries[0].reason_code == "unsupported_suffix"


def test_batch_consumes_format_owner_without_legacy_allowlist() -> None:
    """batch 源码必须消费 Fins capability，不再声明或导出旧 allow-list。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: batch 重新建立 suffix owner 或遗留旧常量时抛出。
    """

    # Governance audit：锁定唯一 owner 边界，避免行为测试无法察觉的重复 allow-list 回流。
    source = Path(upload_batch.__file__).read_text(encoding="utf-8")
    legacy_allowlist_name = "FINS_UPLOAD_FILE_" + "SUFFIXES"
    assert legacy_allowlist_name not in source
    assert "FINS_UPLOAD_FORMAT_CAPABILITY.accepts_primary" in source


def test_explicit_recursive_and_non_recursive_policy(tmp_path: Path) -> None:
    """普通目录默认直属扫描，显式 recursive 才扫描非 structured 子目录。"""

    source_dir = tmp_path / "source"
    nested = source_dir / "nested"
    nested.mkdir(parents=True)
    root_filing = source_dir / "2024FY年报.pdf"
    nested_filing = nested / "2024Q1季报.pdf"
    root_filing.write_text("root", encoding="utf-8")
    nested_filing.write_text("nested", encoding="utf-8")

    shallow = generate_upload_batch_plan(
        UploadBatchPlanRequest(ticker="AAPL", source_dir=source_dir)
    )
    recursive = generate_upload_batch_plan(
        UploadBatchPlanRequest(ticker="AAPL", source_dir=source_dir, recursive=True)
    )

    assert [entry.file for entry in shallow.recognized_entries] == [root_filing.resolve()]
    assert {entry.file for entry in recursive.recognized_entries} == {
        root_filing.resolve(),
        nested_filing.resolve(),
    }


def test_external_ancestor_symlink_is_allowed(tmp_path: Path) -> None:
    """source root 外部祖先 symlink 不得被误判为内部逃逸。"""

    real_parent = tmp_path / "real"
    source_dir = real_parent / "source"
    source_dir.mkdir(parents=True)
    (source_dir / "2024FY年报.pdf").write_text("filing", encoding="utf-8")
    alias = tmp_path / "alias"
    alias.symlink_to(real_parent, target_is_directory=True)

    plan = generate_upload_batch_plan(
        UploadBatchPlanRequest(ticker="AAPL", source_dir=alias / "source")
    )

    assert len(plan.recognized_entries) == 1


def test_source_root_self_symlink_is_rejected(tmp_path: Path) -> None:
    """lexical source root 自身为 symlink 时必须作为 usage failure 拒绝。"""

    real_source = tmp_path / "real"
    real_source.mkdir()
    source_link = tmp_path / "source-link"
    source_link.symlink_to(real_source, target_is_directory=True)

    with pytest.raises(UploadBatchPlanUsageError, match="source root must not be a symlink"):
        generate_upload_batch_plan(
            UploadBatchPlanRequest(ticker="AAPL", source_dir=source_link)
        )


def test_internal_file_and_directory_symlinks_are_typed_skips(tmp_path: Path) -> None:
    """root 内 component/candidate symlink 必须跳过且不能读取目标。"""

    source_dir = tmp_path / "source"
    source_dir.mkdir()
    regular = source_dir / "2024FY年报.pdf"
    regular.write_text("filing", encoding="utf-8")
    external = tmp_path / "2023FY年报.pdf"
    external.write_text("external", encoding="utf-8")
    (source_dir / "2023FY年报.pdf").symlink_to(external)
    external_dir = tmp_path / "external-dir"
    external_dir.mkdir()
    (external_dir / "2022FY年报.pdf").write_text("external", encoding="utf-8")
    (source_dir / "linked-dir").symlink_to(external_dir, target_is_directory=True)

    plan = generate_upload_batch_plan(
        UploadBatchPlanRequest(ticker="AAPL", source_dir=source_dir, recursive=True)
    )

    assert [entry.file for entry in plan.recognized_entries] == [regular.resolve()]
    assert all(entry.reason_code == "unsafe_symlink" for entry in plan.skipped_entries)


def test_missing_source_and_file_source_are_usage_errors(tmp_path: Path) -> None:
    """不存在或非目录 source root 必须在 owner input boundary 失败。"""

    with pytest.raises(UploadBatchPlanUsageError, match="does not exist"):
        generate_upload_batch_plan(
            UploadBatchPlanRequest(ticker="AAPL", source_dir=tmp_path / "missing")
        )
    source_file = tmp_path / "source.pdf"
    source_file.write_text("file", encoding="utf-8")
    with pytest.raises(UploadBatchPlanUsageError, match="not a directory"):
        generate_upload_batch_plan(
            UploadBatchPlanRequest(ticker="AAPL", source_dir=source_file)
        )


def test_upload_batch_module_has_no_reverse_layer_imports() -> None:
    """Fins owner 不得反向 import CLI、Service、Host、Engine、UI 或 storage。"""

    module_path = Path("dayu/fins/upload_batch.py")
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    forbidden_prefixes = (
        "dayu.cli",
        "dayu.engine",
        "dayu.host",
        "dayu.service",
        "dayu.ui",
        "dayu.fins.storage",
    )
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imports.append(node.module)

    assert [
        name
        for name in imports
        if any(name == prefix or name.startswith(prefix + ".") for prefix in forbidden_prefixes)
    ] == []
