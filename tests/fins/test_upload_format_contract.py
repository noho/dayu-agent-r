"""Fins 上传文件格式与角色 owner contract 测试。"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from dayu.fins.upload_format_contract import (
    FINS_UPLOAD_FORMAT_CAPABILITY,
    FINS_UPLOAD_FORMAT_TEXT,
    FinsUploadFileRole,
    FinsUploadFilingFiles,
    FinsUploadFormatCapability,
    FinsUploadFormatError,
    FinsUploadFormatFailureKind,
    FinsUploadMaterialFiles,
    project_fins_upload_format_text,
)

_PRIMARY_SUFFIXES: tuple[str, ...] = (
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
)
_REJECTED_STANDALONE_SUFFIXES: tuple[str, ...] = (
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
)


def test_capability_projects_exact_frozen_primary_and_companion_suffixes() -> None:
    """Fins overlay 必须精确复用 13 个 primary suffix，并只增加 XSD companion。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: primary 顺序、成员或 companion-only 集合漂移时抛出。
    """

    assert FINS_UPLOAD_FORMAT_CAPABILITY.primary_suffixes == _PRIMARY_SUFFIXES
    assert FINS_UPLOAD_FORMAT_CAPABILITY.companion_only_suffixes == frozenset({".xsd"})
    assert FINS_UPLOAD_FORMAT_CAPABILITY.companion_suffixes == (*_PRIMARY_SUFFIXES, ".xsd")
    assert all(FINS_UPLOAD_FORMAT_CAPABILITY.accepts_primary(suffix) for suffix in _PRIMARY_SUFFIXES)
    assert all(not FINS_UPLOAD_FORMAT_CAPABILITY.accepts_primary(suffix) for suffix in _REJECTED_STANDALONE_SUFFIXES)
    assert FINS_UPLOAD_FORMAT_CAPABILITY.accepts_companion("XSD")
    assert not FINS_UPLOAD_FORMAT_CAPABILITY.accepts_companion(".zip")


def test_filing_upsert_selection_preserves_primary_and_companion_order() -> None:
    """filing upsert 必须保存 authoritative primary，并保留 companion 相对顺序。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 角色、顺序或 require-primary contract 漂移时抛出。
    """

    primary = Path("report.html")
    companions = (Path("schema.xsd"), Path("tables.xlsx"), Path("notes.docx"))
    selection = FinsUploadFilingFiles.for_upsert(
        primary=primary,
        companions=companions,
    )

    assert selection.primary == primary
    assert selection.require_primary() == primary
    assert selection.companions == companions
    assert selection.ordered_files == (primary, *companions)
    assert selection.is_empty is False


def test_filing_delete_is_typed_empty_and_upsert_has_no_order_inference_entry() -> None:
    """filing delete 必须使用明确空状态，upsert 不能保留顺序推断入口。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: delete 空状态或 upsert 构造边界漂移时抛出。
    """

    assert "from_upsert_paths" not in FinsUploadFilingFiles.__dict__

    selection = FinsUploadFilingFiles.for_delete()
    assert selection.primary is None
    assert selection.companions == ()
    assert selection.ordered_files == ()
    assert selection.is_empty is True
    with pytest.raises(ValueError, match="没有 primary"):
        selection.require_primary()
    with pytest.raises(ValueError, match="不能包含 companion"):
        FinsUploadFilingFiles(primary=None, companions=(Path("schema.xsd"),))


@pytest.mark.parametrize("suffix", _REJECTED_STANDALONE_SUFFIXES)
def test_primary_rejects_legacy_unselected_and_companion_only_suffixes(suffix: str) -> None:
    """legacy、第三方未选择格式与 XSD 都不能成为 standalone primary。

    Args:
        suffix: 当前拒绝矩阵中的扩展名。

    Returns:
        无。

    Raises:
        AssertionError: primary 接受集扩面或 failure kind 漂移时抛出。
    """

    path = Path(f"report{suffix}")
    with pytest.raises(FinsUploadFormatError) as exc_info:
        FinsUploadFilingFiles.for_upsert(primary=path, companions=())

    assert exc_info.value.kind is FinsUploadFormatFailureKind.PRIMARY_SUFFIX_UNSUPPORTED
    assert exc_info.value.file_label == path.name
    assert str(exc_info.value) == f"财报主文件格式不受支持：{path.name}"


def test_xsd_is_accepted_only_as_filing_companion() -> None:
    """XSD 必须只以 explicit companion 角色通过，且失败保持角色明确。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: XSD 角色边界或 companion failure kind 漂移时抛出。
    """

    accepted = FinsUploadFilingFiles.for_upsert(
        primary=Path("report.html"),
        companions=(Path("schema.xsd"),),
    )
    assert accepted.ordered_files == (Path("report.html"), Path("schema.xsd"))

    with pytest.raises(FinsUploadFormatError) as primary_error:
        FINS_UPLOAD_FORMAT_CAPABILITY.require_filing_path(
            Path("schema.xsd"),
            role=FinsUploadFileRole.PRIMARY,
        )
    assert primary_error.value.kind is FinsUploadFormatFailureKind.PRIMARY_SUFFIX_UNSUPPORTED

    with pytest.raises(FinsUploadFormatError) as companion_error:
        FinsUploadFilingFiles.for_upsert(
            primary=Path("report.html"),
            companions=(Path("archive.zip"),),
        )
    assert companion_error.value.kind is FinsUploadFormatFailureKind.COMPANION_SUFFIX_UNSUPPORTED
    assert str(companion_error.value) == "财报随附文件格式不受支持：archive.zip"


def test_material_selection_requires_every_file_to_be_convertible() -> None:
    """material upsert 必须保序校验全部文件，且不产生 companion 例外。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: material 顺序、空状态或 failure kind 漂移时抛出。
    """

    paths = (Path("deck.pptx"), Path("tables.xlsx"), Path("notes.txt"))
    selection = FinsUploadMaterialFiles.from_upsert_paths(paths)
    assert selection.files == paths
    assert selection.is_empty is False

    with pytest.raises(FinsUploadFormatError) as exc_info:
        FinsUploadMaterialFiles.from_upsert_paths((Path("deck.pptx"), Path("schema.xsd"), Path("notes.txt")))
    assert exc_info.value.kind is FinsUploadFormatFailureKind.MATERIAL_SUFFIX_UNSUPPORTED
    assert exc_info.value.file_label == "schema.xsd"
    assert str(exc_info.value) == "补充材料文件格式不受支持：schema.xsd"

    with pytest.raises(ValueError, match="至少包含一个文件"):
        FinsUploadMaterialFiles.from_upsert_paths(())
    delete_selection = FinsUploadMaterialFiles.for_delete()
    assert delete_selection.files == ()
    assert delete_selection.is_empty is True


def test_format_error_is_bounded_and_never_exposes_parent_path(tmp_path: Path) -> None:
    """角色错误只能携带安全 basename，不能泄漏绝对父路径。

    Args:
        tmp_path: 用于构造带敏感父目录的绝对测试路径。

    Returns:
        无。

    Raises:
        AssertionError: error label/message 泄漏路径或超出边界时抛出。
    """

    path = tmp_path / "private" / "legacy.doc"
    with pytest.raises(FinsUploadFormatError) as exc_info:
        FinsUploadFilingFiles.for_upsert(primary=path, companions=())

    error = exc_info.value
    assert error.file_label == "legacy.doc"
    assert str(tmp_path) not in str(error)
    assert "/" not in str(error)
    assert "\\" not in str(error)
    assert 0 < len(str(error)) <= 240


def test_long_canonical_basename_keeps_label_and_bounds_primary_material_messages(
    tmp_path: Path,
) -> None:
    """长 canonical basename 必须保留为 label，同时让两类错误消息不超过 240 字符。

    Args:
        tmp_path: 用于构造带绝对父目录的长文件路径。

    Returns:
        无。

    Raises:
        AssertionError: label 被截断、消息超界或父路径泄漏时抛出。
    """

    basename = f"{'a' * 226}.doc"
    path = tmp_path / "private" / basename

    with pytest.raises(FinsUploadFormatError) as primary_exc:
        FinsUploadFilingFiles.for_upsert(primary=path, companions=())
    with pytest.raises(FinsUploadFormatError) as material_exc:
        FinsUploadMaterialFiles.from_upsert_paths((path,))

    assert len(basename) == 230
    assert primary_exc.value.file_label == basename
    assert material_exc.value.file_label == basename
    assert primary_exc.value.kind is FinsUploadFormatFailureKind.PRIMARY_SUFFIX_UNSUPPORTED
    assert material_exc.value.kind is FinsUploadFormatFailureKind.MATERIAL_SUFFIX_UNSUPPORTED
    assert str(primary_exc.value) == "财报主文件格式不受支持"
    assert str(material_exc.value) == "补充材料文件格式不受支持"
    for error in (primary_exc.value, material_exc.value):
        assert 0 < len(str(error)) <= 240
        assert str(tmp_path) not in str(error)


def test_text_projection_is_self_contained_and_uses_exact_suffix_order() -> None:
    """CLI/schema 投影必须自足说明角色、转换门槛与精确产品 suffix。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 用户或 LLM 文案缺少冻结语义时抛出。
    """

    suffix_text = ", ".join(_PRIMARY_SUFFIXES)
    filing_text = FINS_UPLOAD_FORMAT_TEXT.filing_files
    material_text = FINS_UPLOAD_FORMAT_TEXT.material_files
    tool_text = FINS_UPLOAD_FORMAT_TEXT.upload_tool_files

    expected_filing_text = (
        "auto/create/update 必须至少提供一个文件，并按给定顺序上传：首文件是主文件，必须实际转换成功；"
        "后续文件是仅原样保存、不转换的随附文件。"
        f"主文件支持后缀：{suffix_text}；随附文件支持这些后缀以及 .xsd，且 .xsd 只能作为后续随附文件。"
        ".xml 仅是 XBRL XML 候选，不代表任意 XML；主文件后缀通过只表示具备转换资格，不保证文件内容转换成功。"
        "随附文件只校验可随批保存的后缀，不执行转换。"
        ".json 仅是 Docling JSON 候选，不代表任意 JSON 内容可转换。delete 不得提供文件。"
    )
    expected_material_text = (
        "auto/create/update 必须至少提供一个文件；"
        f"每个文件都必须使用转换器支持的后缀：{suffix_text}，并逐个实际转换成功；"
        "后缀通过只表示具备转换资格，不保证文件内容转换成功。delete 不得提供文件。"
    )
    expected_tool_text = (
        f"upload_kind=filing 时，{expected_filing_text}"
        f"upload_kind=material 时，{expected_material_text}"
        "每个路径必须指向已存在、非空的普通文件。"
    )

    assert filing_text == expected_filing_text
    assert material_text == expected_material_text
    assert tool_text == expected_tool_text
    for required_text in (
        "auto/create/update 必须至少提供一个文件",
        "首文件是主文件",
        "必须实际转换成功",
        "后续文件",
        "仅原样保存、不转换",
        ".xsd 只能作为后续随附文件",
        ".xml 仅是 XBRL XML 候选",
        "不代表任意 XML",
        ".json 仅是 Docling JSON 候选",
        "不代表任意 JSON 内容可转换",
        "主文件后缀通过只表示具备转换资格",
        "不保证文件内容转换成功",
        "随附文件只校验可随批保存的后缀，不执行转换",
        "delete 不得提供文件",
    ):
        assert required_text in filing_text
        assert required_text in tool_text
    assert "upload_kind=material" in tool_text
    assert "upload_kind=material 时，auto/create/update 必须至少提供一个文件" in tool_text
    assert "每个文件" in tool_text
    assert "逐个实际转换成功" in tool_text


def test_text_projection_mechanically_consumes_companion_only_suffixes() -> None:
    """随附文件文案必须随 capability 输入变化，不能保留 XSD 字面量真源。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 文案没有机械投影 companion-only 集合时抛出。
    """

    capability = FinsUploadFormatCapability(
        converter_capability=FINS_UPLOAD_FORMAT_CAPABILITY.converter_capability,
        companion_only_suffixes=frozenset({".schema"}),
    )

    projection = project_fins_upload_format_text(capability)

    assert ".schema" in projection.filing_files
    assert ".xsd" not in projection.filing_files


def test_contract_and_cli_projection_import_without_loading_docling() -> None:
    """格式 contract 与 CLI help 模块导入阶段不得加载第三方 Docling。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 子进程导入失败或触发 Docling eager import 时抛出。
    """

    script = """
import builtins

original_import = builtins.__import__

def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
    if name == "docling" or name.startswith("docling."):
        raise AssertionError(f"eager Docling import: {name}")
    return original_import(name, globals, locals, fromlist, level)

builtins.__import__ = guarded_import
import dayu.fins.upload_format_contract
import dayu.cli.arg_parsing
import dayu.fins.tools.upload_tools
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
