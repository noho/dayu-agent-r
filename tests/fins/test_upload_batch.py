"""Fins 批量上传计划生成测试。"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from dayu.fins.upload_batch import (
    UploadBatchPlanEmptyError,
    UploadBatchPlanRequest,
    UploadBatchPlanUsageError,
    generate_upload_batch_plan,
)


def test_non_recursive_scan_only_uses_top_level_files(tmp_path: Path) -> None:
    """非递归扫描只识别源目录第一层普通文件。"""

    source_dir = tmp_path / "source"
    nested_dir = source_dir / "nested"
    nested_dir.mkdir(parents=True)
    filing = source_dir / "AAPL 10-K 2024.pdf"
    nested_filing = nested_dir / "AAPL 10-Q 2024.pdf"
    filing.write_text("filing", encoding="utf-8")
    nested_filing.write_text("nested", encoding="utf-8")

    result = generate_upload_batch_plan(
        UploadBatchPlanRequest(
            ticker="AAPL",
            source_dir=source_dir,
            action="create",
        )
    )

    assert [entry.command_name for entry in result.entries] == ["upload_filing"]
    assert result.entries[0].files == (filing.resolve(),)


def test_recursive_scan_includes_nested_files(tmp_path: Path) -> None:
    """递归扫描必须识别子目录中的 filing 文件。"""

    source_dir = tmp_path / "source"
    nested_dir = source_dir / "nested"
    nested_dir.mkdir(parents=True)
    root_filing = source_dir / "AAPL 10-K 2024.pdf"
    nested_filing = nested_dir / "AAPL 10-Q 2024.pdf"
    root_filing.write_text("root", encoding="utf-8")
    nested_filing.write_text("nested", encoding="utf-8")

    result = generate_upload_batch_plan(
        UploadBatchPlanRequest(
            ticker="AAPL",
            source_dir=source_dir,
            action="update",
            recursive=True,
        )
    )

    assert [entry.files[0].name for entry in result.entries] == [
        "AAPL 10-K 2024.pdf",
        "AAPL 10-Q 2024.pdf",
    ]
    assert {entry.action for entry in result.entries} == {"update"}


def test_material_forms_generate_material_entries(tmp_path: Path) -> None:
    """material form token 命中时必须生成 upload_material 计划条目。"""

    source_dir = tmp_path / "source"
    source_dir.mkdir()
    material = source_dir / "AAPL EX-99.1 investor day.pdf"
    material.write_text("material", encoding="utf-8")

    result = generate_upload_batch_plan(
        UploadBatchPlanRequest(
            ticker="AAPL",
            source_dir=source_dir,
            action="create",
            material_forms=("EX-99.1",),
            fiscal_year=2024,
            company_name="Apple Inc.",
        )
    )

    assert len(result.entries) == 1
    entry = result.entries[0]
    assert entry.command_name == "upload_material"
    assert entry.form_type == "EX-99.1"
    assert entry.material_name == "AAPL EX-99.1 investor day"
    assert entry.fiscal_year == 2024
    assert entry.company_name == "Apple Inc."
    assert entry.files == (material.resolve(),)


def test_no_recognizable_files_raises_empty_error(tmp_path: Path) -> None:
    """源目录中没有 filing / material 语义文件时必须失败。"""

    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "notes.pdf").write_text("notes", encoding="utf-8")

    with pytest.raises(UploadBatchPlanEmptyError, match="no recognizable"):
        generate_upload_batch_plan(
            UploadBatchPlanRequest(
                ticker="AAPL",
                source_dir=source_dir,
                action="create",
            )
        )


def test_missing_source_dir_raises_usage_error(tmp_path: Path) -> None:
    """source dir 不存在属于用户输入错误。"""

    with pytest.raises(UploadBatchPlanUsageError, match="source dir does not exist"):
        generate_upload_batch_plan(
            UploadBatchPlanRequest(
                ticker="AAPL",
                source_dir=tmp_path / "missing",
                action="create",
            )
        )


def test_source_dir_is_file_raises_usage_error(tmp_path: Path) -> None:
    """source dir 指向普通文件时属于用户输入错误。"""

    source_file = tmp_path / "source.pdf"
    source_file.write_text("not a directory", encoding="utf-8")

    with pytest.raises(UploadBatchPlanUsageError, match="source path is not a directory"):
        generate_upload_batch_plan(
            UploadBatchPlanRequest(
                ticker="AAPL",
                source_dir=source_file,
                action="create",
            )
        )


def test_empty_material_form_raises_usage_error(tmp_path: Path) -> None:
    """material_forms 不允许包含空字符串。"""

    source_dir = tmp_path / "source"
    source_dir.mkdir()

    with pytest.raises(UploadBatchPlanUsageError, match="material_forms"):
        generate_upload_batch_plan(
            UploadBatchPlanRequest(
                ticker="AAPL",
                source_dir=source_dir,
                action="create",
                material_forms=("",),
            )
        )


def test_upload_batch_module_has_no_host_engine_or_storage_imports() -> None:
    """批量计划 helper 不得导入 Host、Engine、Service 或 Fins storage。"""

    module_path = Path("dayu/fins/upload_batch.py")
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    forbidden_prefixes = (
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

    violations = [
        name
        for name in imports
        if any(
            name == prefix or name.startswith(prefix + ".")
            for prefix in forbidden_prefixes
        )
    ]
    assert violations == []
