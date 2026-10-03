"""上传资产规划 owner 的数量、身份与保序 handoff 测试。"""

from __future__ import annotations

import unicodedata
import hashlib
from pathlib import Path

import pytest
from unittest.mock import Mock

from dayu.fins.domain.enums import SourceKind
from dayu.fins.upload_asset_plan import (
    DOCLING_FILE_SUFFIX,
    UploadAssetPlan,
    UploadAssetPair,
    FinsUploadAssetPlanError,
    FinsUploadAssetPlanReason,
    docling_storage_name,
    filing_original_storage_name,
    has_duplicate_upload_asset_paths,
    normalize_upload_asset_path,
    plan_upload_assets,
    upload_asset_path_identity,
)
from dayu.fins.upload_format_contract import (
    FinsUploadFormatError,
    FinsUploadFilingFiles,
    FinsUploadMaterialFiles,
    MAX_MATERIAL_UPLOAD_FILES,
)
from dayu.fins.upload_usage_contract import (
    FinsUploadUsageCode,
    fins_upload_asset_plan_usage_failure,
)


def _material_plan(paths: tuple[Path, ...]) -> tuple[FinsUploadMaterialFiles, UploadAssetPlan]:
    """用显式 upsert 模式取得 material owner 计划。

    Args:
        paths: 保持输入顺序的原件路径。

    Returns:
        资产规划返回的选择和不可变计划。

    Raises:
        FinsUploadAssetPlanError: 资产输入不可唯一规划时抛出。
    """

    selection, plan = plan_upload_assets(material_primary_selectors=(paths[0],) if paths else (),
        source_kind=SourceKind.MATERIAL, operation="upsert", files=paths
    )
    if not isinstance(selection, FinsUploadMaterialFiles):
        raise AssertionError("material planner 返回错误 selection 类型")
    return selection, plan


def test_material_full_basename_mapping_and_order(tmp_path: Path) -> None:
    """同 stem 不同后缀按完整原件名派生且逆序稳定。

    Args:
        tmp_path: 隔离路径根。

    Returns:
        无。

    Raises:
        AssertionError: 名称或保序对应漂移时抛出。
    """

    first, second = tmp_path / "deck.txt", tmp_path / "deck.md"
    for paths in ((first, second), (second, first)):
        selection, plan = _material_plan(paths)
        assert isinstance(selection, FinsUploadMaterialFiles)
        assert selection.files == paths
        assert tuple(pair.path for pair in plan.ordered_pairs) == paths
        assert plan.converter_pairs == plan.ordered_pairs
        assert {pair.docling_name for pair in plan.ordered_pairs} == {
            "deck.txt_docling.json",
            "deck.md_docling.json",
        }
        assert tuple(pair.original_name for pair in plan.ordered_pairs) == tuple(
            path.name for path in paths
        )
        assert plan.primary_original_name == paths[0].name


def test_material_count_boundary_and_delete_mode(tmp_path: Path) -> None:
    """100 全部入计划，101 前置 typed 拒绝，delete 使用唯一空计划。

    Args:
        tmp_path: 隔离路径根。

    Returns:
        无。

    Raises:
        AssertionError: 数量边界或 delete 模式漂移时抛出。
    """

    paths = tuple(tmp_path / f"part-{index:03d}.pdf" for index in range(MAX_MATERIAL_UPLOAD_FILES + 1))
    selection, plan = _material_plan(paths[:-1])
    assert isinstance(selection, FinsUploadMaterialFiles)
    assert len(plan.ordered_pairs) == MAX_MATERIAL_UPLOAD_FILES
    assert len(plan.converter_pairs) == MAX_MATERIAL_UPLOAD_FILES
    assert tuple(pair.path for pair in plan.converter_pairs) == paths[:-1]
    with pytest.raises(FinsUploadAssetPlanError) as exc_info:
        _material_plan(paths)
    assert exc_info.value.reason is FinsUploadAssetPlanReason.TOO_MANY_FILES
    with pytest.raises(FinsUploadAssetPlanError) as empty_info:
        _material_plan(())
    assert empty_info.value.reason is FinsUploadAssetPlanReason.MISSING_FILES
    with pytest.raises(FinsUploadAssetPlanError) as delete_limit:
        plan_upload_assets(material_primary_selectors=(), source_kind=SourceKind.MATERIAL, operation="delete", files=paths)
    assert delete_limit.value.reason is FinsUploadAssetPlanReason.TOO_MANY_FILES
    empty_selection, empty_plan = plan_upload_assets(material_primary_selectors=(),
        source_kind=SourceKind.MATERIAL, operation="delete", files=paths[:-1]
    )
    assert isinstance(empty_selection, FinsUploadMaterialFiles)
    assert empty_selection.is_empty
    assert empty_plan.ordered_pairs == empty_plan.converter_pairs == ()


@pytest.mark.parametrize(
    ("raw_path", "expected_label"),
    (
        (Path("~dayu_assets_nonexistent_user_20260930/report.pdf"), "report.pdf"),
        (Path("bad\x00name.pdf"), "输入文件（文件名已隐藏）"),
        (Path("bad\ud800name.pdf"), "输入文件（文件名已隐藏）"),
    ),
)
def test_material_delete_classifies_raw_path_shape_without_selecting_files(
    raw_path: Path, expected_label: str
) -> None:
    """delete raw 路径形状由 planner 分类，且失败不改变空选择规则。

    Args:
        raw_path: 无法安全解析的用户路径。
        expected_label: 不泄漏路径的公开文件标签。

    Returns:
        无。

    Raises:
        AssertionError: 失败分类或安全标签漂移时抛出。
    """

    with pytest.raises(FinsUploadAssetPlanError) as raised:
        plan_upload_assets(material_primary_selectors=(),
            source_kind=SourceKind.MATERIAL, operation="delete", files=(raw_path,)
        )
    assert raised.value.reason is FinsUploadAssetPlanReason.INVALID_ASSET_NAME
    assert raised.value.file_label == expected_label
    assert str(raw_path) not in str(raised.value)


def test_material_delete_symlink_loop_keeps_pathless_operational_failure(
    tmp_path: Path,
) -> None:
    """delete raw 循环链接由 planner 保持无路径明文的操作失败。

    Args:
        tmp_path: 隔离自循环链接。

    Returns:
        无。

    Raises:
        AssertionError: 错误类型或路径脱敏漂移时抛出。
        OSError: 测试平台无法建立链接时抛出。
    """

    loop = tmp_path / "loop.pdf"
    loop.symlink_to(loop.name)
    with pytest.raises(OSError) as raised:
        plan_upload_assets(material_primary_selectors=(),
            source_kind=SourceKind.MATERIAL, operation="delete", files=(loop,)
        )
    assert raised.value.errno is not None
    assert str(loop) not in str(raised.value)


def test_plan_accepts_equal_distinct_converter_pairs(tmp_path: Path) -> None:
    """material 全转换与 filing 主文件匹配按保序值校验。

    Args:
        tmp_path: 隔离原件身份路径。

    Returns:
        无。

    Raises:
        AssertionError: 等值独立条目被拒绝或顺序不变量漂移时抛出。
    """

    first, second = tmp_path / "first.pdf", tmp_path / "second.pdf"
    _, material = _material_plan((first, second))
    material_converter = tuple(
        UploadAssetPair(pair.path, pair.original_name, pair.docling_name)
        for pair in material.ordered_pairs
    )
    assert material_converter is not material.ordered_pairs
    assert all(
        converted is not original
        for converted, original in zip(material_converter, material.ordered_pairs, strict=True)
    )
    assert UploadAssetPlan(material.ordered_pairs, material_converter, next(iter(material.ordered_pairs)).original_name, SourceKind.MATERIAL).converter_pairs == material.ordered_pairs

    primary = first.resolve(strict=False)
    selection = FinsUploadFilingFiles.for_upsert(primary=primary, companions=(second.resolve(strict=False),))
    _, filing = plan_upload_assets(material_primary_selectors=(),
        source_kind=SourceKind.FILING,
        operation="upsert",
        files=selection.ordered_files,
        filing_selection=selection,
    )
    original = filing.converter_pairs[0]
    copied = UploadAssetPair(original.path, original.original_name, original.docling_name)
    assert copied is not original
    assert UploadAssetPlan(
        filing.ordered_pairs, (copied,), filing.primary_original_name, SourceKind.FILING
    ).converter_pairs == filing.converter_pairs


def test_bare_plan_and_filing_identity_symlink_loop_use_safe_operational_failure(
    tmp_path: Path,
) -> None:
    """裸计划和 filing 仓储身份共用路径 owner 的无路径明文循环分类。

    Args:
        tmp_path: 构造自引用符号链接的隔离目录。

    Returns:
        无。

    Raises:
        AssertionError: 错误类型或公开文案泄漏路径时抛出。
        OSError: 测试平台无法创建符号链接时抛出。
    """

    loop = tmp_path / "loop.pdf"
    loop.symlink_to(loop.name)
    pair = UploadAssetPair(loop, loop.name, f"{loop.name}{DOCLING_FILE_SUFFIX}")
    with pytest.raises(OSError):
        normalize_upload_asset_path(loop)
    UploadAssetPlan((pair,), (pair,), pair.original_name, SourceKind.MATERIAL)
    filing_original_storage_name(loop)


@pytest.mark.parametrize(
    ("names", "reason"),
    (
        (("same.pdf", "same.pdf"), FinsUploadAssetPlanReason.DUPLICATE_ORIGINAL_BASENAME),
        (("Deck.txt", "deck.txt"), FinsUploadAssetPlanReason.ASSET_NAME_COLLISION),
        (("a.txt", "a.txt_docling.json"), FinsUploadAssetPlanReason.ASSET_NAME_COLLISION),
        (("a.txt", "a.txt_docling.json", "META.JSON"), FinsUploadAssetPlanReason.RESERVED_CONTROL_NAME),
        (("META.JSON", "a.txt_docling.json", "a.txt"), FinsUploadAssetPlanReason.RESERVED_CONTROL_NAME),
        (("a" * 243 + ".pdf", "META.JSON"), FinsUploadAssetPlanReason.RESERVED_CONTROL_NAME),
        (("META.JSON", "a" * 243 + ".pdf"), FinsUploadAssetPlanReason.RESERVED_CONTROL_NAME),
        (("meta.json",), FinsUploadAssetPlanReason.RESERVED_CONTROL_NAME),
        (("META.JSON",), FinsUploadAssetPlanReason.RESERVED_CONTROL_NAME),
        ((".identity.json",), FinsUploadAssetPlanReason.RESERVED_CONTROL_NAME),
        (("a" * 243 + ".pdf",), FinsUploadAssetPlanReason.INVALID_ASSET_NAME),
        (("a\\b.txt",), FinsUploadAssetPlanReason.INVALID_ASSET_NAME),
        (("a\\b.txt", "a\\b.txt"), FinsUploadAssetPlanReason.DUPLICATE_ORIGINAL_BASENAME),
        (("a" * 243 + ".pdf", "a\\b.txt"), FinsUploadAssetPlanReason.INVALID_ASSET_NAME),
        (("a\\b.txt", "a" * 243 + ".pdf"), FinsUploadAssetPlanReason.INVALID_ASSET_NAME),
        (("a\ud800b.txt",), FinsUploadAssetPlanReason.INVALID_ASSET_NAME),
        (("a\udc80b.txt",), FinsUploadAssetPlanReason.INVALID_ASSET_NAME),
        (("a\ud800b.txt", "META.JSON"), FinsUploadAssetPlanReason.RESERVED_CONTROL_NAME),
        (("META.JSON", "a\ud800b.txt"), FinsUploadAssetPlanReason.RESERVED_CONTROL_NAME),
        (("a\x00b.txt",), FinsUploadAssetPlanReason.INVALID_ASSET_NAME),
        (("a\x00b.txt", "META.JSON"), FinsUploadAssetPlanReason.RESERVED_CONTROL_NAME),
        (("META.JSON", "a\x00b.txt"), FinsUploadAssetPlanReason.RESERVED_CONTROL_NAME),
    ),
)
def test_material_rejects_name_conflicts_before_conversion(
    tmp_path: Path,
    names: tuple[str, ...],
    reason: FinsUploadAssetPlanReason,
) -> None:
    """控制名、跨资产碰撞与长度错误按封闭原因在转换和发布前拒绝。

    Args:
        tmp_path: 隔离路径根。
        names: 待规划的原件名。
        reason: 期待的规划失败原因。

    Returns:
        无。

    Raises:
        AssertionError: 错误分类或路径安全性漂移时抛出。
    """

    paths = tuple(tmp_path / str(index) / name for index, name in enumerate(names))
    with pytest.raises(FinsUploadAssetPlanError) as exc_info:
        _material_plan(paths)
    assert exc_info.value.reason is reason
    assert str(tmp_path) not in str(exc_info.value)
    assert not tuple(tmp_path.iterdir())
    if (
        any("\\" in name or "\ud800" in name or "\udc80" in name or "\x00" in name for name in names)
        and reason is not FinsUploadAssetPlanReason.RESERVED_CONTROL_NAME
    ):
        assert exc_info.value.file_label == "输入文件（文件名已隐藏）"
    if names == ("same.pdf", "same.pdf"):
        assert exc_info.value.file_label == "same.pdf"


@pytest.mark.parametrize("control_first", (False, True))
def test_control_name_precedes_duplicate_basename_with_stable_usage(
    tmp_path: Path, control_first: bool
) -> None:
    """控制名与重复原件同批出现时，两种顺序共享固定原因和安全文案。

    Args:
        tmp_path: 隔离路径根。
        control_first: 控制名是否位于重复原件之前。

    Returns:
        无。

    Raises:
        AssertionError: 错误优先级、标签或文案漂移时抛出。
    """

    duplicates = (tmp_path / "first" / "same.txt", tmp_path / "second" / "same.txt")
    control = tmp_path / "third" / "META.JSON"
    paths = (control, *duplicates) if control_first else (*duplicates, control)
    with pytest.raises(FinsUploadAssetPlanError) as raised:
        _material_plan(paths)
    error = raised.value
    usage = fins_upload_asset_plan_usage_failure(
        error, max_files=MAX_MATERIAL_UPLOAD_FILES
    )
    assert error.reason is FinsUploadAssetPlanReason.RESERVED_CONTROL_NAME
    assert error.file_label == "META.JSON"
    assert usage.code is FinsUploadUsageCode.RESERVED_CONTROL_NAME
    assert usage.message == "文件名与仓储控制文件冲突：META.JSON；请重命名后重试"
    assert usage.hint == "请避开仓储控制文件名后重试"
    assert str(tmp_path) not in usage.message


@pytest.mark.parametrize(
    ("names", "expected_reason", "expected_label", "expected_message"),
    (
        (("META.JSON", "deck.zip"), FinsUploadAssetPlanReason.RESERVED_CONTROL_NAME,
         "META.JSON", "文件名与仓储控制文件冲突：META.JSON；请重命名后重试"),
        (("deck.zip", "META.JSON"), FinsUploadAssetPlanReason.RESERVED_CONTROL_NAME,
         "META.JSON", "文件名与仓储控制文件冲突：META.JSON；请重命名后重试"),
        (("same.txt", "same.txt", "deck.zip"), FinsUploadAssetPlanReason.DUPLICATE_ORIGINAL_BASENAME,
         "same.txt", "原件文件名重复：same.txt；请重命名后重试"),
        (("deck.zip", "same.txt", "same.txt"), FinsUploadAssetPlanReason.DUPLICATE_ORIGINAL_BASENAME,
         "same.txt", "原件文件名重复：same.txt；请重命名后重试"),
    ),
)
def test_mixed_name_and_unsupported_format_share_plan_owner_priority(
    tmp_path: Path,
    names: tuple[str, ...],
    expected_reason: FinsUploadAssetPlanReason,
    expected_label: str,
    expected_message: str,
) -> None:
    """混合名称错误先于格式，planner 与裸计划共享原因和安全投影。

    Args:
        tmp_path: 隔离输入路径。
        names: 原件名的保序组合。
        expected_reason: 计划 owner 的封闭原因。
        expected_label: 安全文件标签。
        expected_message: 完整 usage 文案。

    Returns:
        无。

    Raises:
        AssertionError: 原因优先级或投影漂移时抛出。
    """

    paths = tuple(tmp_path / str(index) / name for index, name in enumerate(names))
    pairs = tuple(
        UploadAssetPair(path, path.name, docling_storage_name(SourceKind.MATERIAL, path.name))
        for path in paths
    )
    for produce in (
        lambda: _material_plan(paths),
        lambda: UploadAssetPlan(pairs, pairs, next(iter(pairs)).original_name, SourceKind.MATERIAL),
    ):
        with pytest.raises(FinsUploadAssetPlanError) as raised:
            produce()
        usage = fins_upload_asset_plan_usage_failure(
            raised.value, max_files=MAX_MATERIAL_UPLOAD_FILES
        )
        assert raised.value.reason is expected_reason
        assert raised.value.file_label == expected_label
        assert usage.code.value == expected_reason.value
        assert usage.message == expected_message
        assert str(tmp_path) not in usage.message


def test_bare_material_plan_rejects_101_distinct_names(tmp_path: Path) -> None:
    """裸 material 计划自身执行 100 文件上限，而非依赖 planner 入口。

    Args:
        tmp_path: 规范绝对路径根。

    Returns:
        无。

    Raises:
        AssertionError: 裸计划数量准入漂移时抛出。
    """

    pairs = tuple(
        UploadAssetPair(path, path.name, docling_storage_name(SourceKind.MATERIAL, path.name))
        for path in (tmp_path / f"asset-{index:03d}.pdf" for index in range(MAX_MATERIAL_UPLOAD_FILES + 1))
    )
    assert len({pair.original_name for pair in pairs}) == MAX_MATERIAL_UPLOAD_FILES + 1
    with pytest.raises(FinsUploadAssetPlanError) as raised:
        UploadAssetPlan(pairs, pairs, next(iter(pairs)).original_name, SourceKind.MATERIAL)
    assert raised.value.reason is FinsUploadAssetPlanReason.TOO_MANY_FILES


@pytest.mark.parametrize(
    ("names", "reason"),
    (
        (("Deck.txt", "deck.txt"), FinsUploadAssetPlanReason.ASSET_NAME_COLLISION),
        (("é.txt", "e\u0301.txt"), FinsUploadAssetPlanReason.ASSET_NAME_COLLISION),
        (("META.JSON",), FinsUploadAssetPlanReason.RESERVED_CONTROL_NAME),
        (("a" * 243 + ".pdf",), FinsUploadAssetPlanReason.INVALID_ASSET_NAME),
        (("deck.zip",), None),
    ),
)
def test_bare_material_plan_applies_planner_name_and_format_rules(
    tmp_path: Path,
    names: tuple[str, ...],
    reason: FinsUploadAssetPlanReason | None,
) -> None:
    """裸计划构造复用 planner 的控制名、碰撞、长度和格式规则。

    Args:
        tmp_path: 隔离的规范路径根。
        names: 待构造的原件名。
        reason: 预期资产原因；``None`` 表示格式错误。

    Returns:
        无。

    Raises:
        AssertionError: 裸计划越过 owner 校验时抛出。
    """

    pairs = tuple(
        UploadAssetPair(
            path=tmp_path / str(index) / name,
            original_name=name,
            docling_name=docling_storage_name(SourceKind.MATERIAL, name),
        )
        for index, name in enumerate(names)
    )
    if reason is None:
        with pytest.raises(FinsUploadFormatError):
            UploadAssetPlan(pairs, pairs, next(iter(pairs)).original_name, SourceKind.MATERIAL)
    else:
        with pytest.raises(FinsUploadAssetPlanError) as raised:
            UploadAssetPlan(pairs, pairs, next(iter(pairs)).original_name, SourceKind.MATERIAL)
        assert raised.value.reason is reason
    assert not tuple(tmp_path.iterdir())


@pytest.mark.parametrize("control_first", (False, True))
def test_material_unknown_home_is_typed_and_control_name_wins(
    tmp_path: Path, control_first: bool
) -> None:
    """未知用户目录解析失败时维持控制名优先和安全标签。

    Args:
        tmp_path: 隔离控制名路径。
        control_first: 控制名是否在用户路径之前。

    Returns:
        无。

    Raises:
        AssertionError: 封闭原因、标签或零文件副作用漂移时抛出。
    """

    unknown_home = Path("~dayu_assets_nonexistent_user_20260929/report.txt")
    control = tmp_path / "META.JSON"
    paths = (control, unknown_home) if control_first else (unknown_home, control)
    with pytest.raises(FinsUploadAssetPlanError) as raised:
        _material_plan(paths)
    assert raised.value.reason is FinsUploadAssetPlanReason.RESERVED_CONTROL_NAME
    with pytest.raises(FinsUploadAssetPlanError) as single:
        _material_plan((unknown_home,))
    assert single.value.reason is FinsUploadAssetPlanReason.INVALID_ASSET_NAME
    assert single.value.file_label == "report.txt"
    assert not tuple(tmp_path.iterdir())


@pytest.mark.parametrize("shape_first", (False, True))
def test_material_mixed_invalid_names_label_first_input(
    tmp_path: Path, shape_first: bool
) -> None:
    """形状与组件名同时非法时，安全标签跟随输入中的首个非法项。

    Args:
        tmp_path: 隔离原始路径根。
        shape_first: 反斜杠形状错误是否在未知用户目录之前。

    Returns:
        无。

    Raises:
        AssertionError: reason、保序标签或隐藏规则漂移时抛出。
    """

    shape = tmp_path / "a\\b.txt"
    unknown_home = Path("~dayu_assets_nonexistent_user_20260929/x.pdf")
    paths = (shape, unknown_home) if shape_first else (unknown_home, shape)
    with pytest.raises(FinsUploadAssetPlanError) as raised:
        _material_plan(paths)
    assert raised.value.reason is FinsUploadAssetPlanReason.INVALID_ASSET_NAME
    assert raised.value.file_label == (
        "输入文件（文件名已隐藏）" if shape_first else "x.pdf"
    )
    assert str(tmp_path) not in str(raised.value)
    assert not tuple(tmp_path.iterdir())


@pytest.mark.parametrize("long_first", (False, True))
def test_material_long_component_and_shape_keep_first_safe_label(
    tmp_path: Path, long_first: bool
) -> None:
    """超长组件与形状错误混合时维持首项和有界隐藏标签。

    Args:
        tmp_path: 隔离原始路径根。
        long_first: 超长组件是否在反斜杠形状错误之前。

    Returns:
        无。

    Raises:
        AssertionError: 首项选择或有界安全标签漂移时抛出。
    """

    long_name = "é" * 120 + ".pdf"
    long_component = tmp_path / long_name
    shape = tmp_path / "a\\b.txt"
    paths = (long_component, shape) if long_first else (shape, long_component)
    with pytest.raises(FinsUploadAssetPlanError) as raised:
        _material_plan(paths)
    assert raised.value.reason is FinsUploadAssetPlanReason.INVALID_ASSET_NAME
    label = raised.value.file_label
    assert isinstance(label, str)
    assert label == (
        long_name if long_first else "输入文件（文件名已隐藏）"
    )
    assert len(label) < 240
    assert str(tmp_path) not in str(raised.value)


def test_material_operational_path_failure_is_not_classified_as_invalid_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """底层操作性 OSError 保持透传，不伪装成用户文件名错误。

    Args:
        tmp_path: 隔离原始路径根。
        monkeypatch: 在共享路径解析入口注入操作性失败。

    Returns:
        无。

    Raises:
        AssertionError: 操作性失败被错误吞并时抛出。
    """

    denied = PermissionError("path operation denied")
    monkeypatch.setattr(
        "dayu.fins.upload_asset_plan.normalize_upload_asset_path", Mock(side_effect=denied)
    )
    with pytest.raises(PermissionError) as raised:
        _material_plan((tmp_path / "report.txt",))
    assert raised.value is denied


@pytest.mark.parametrize("control_first", (False, True))
def test_material_symlink_loop_is_operational_even_with_control_name(
    tmp_path: Path, control_first: bool
) -> None:
    """真实路径循环保持操作失败分类，不伪装成文件名用法错误。

    Args:
        tmp_path: 隔离符号链接和控制名路径。
        control_first: 控制名是否先于循环路径。

    Returns:
        无。

    Raises:
        AssertionError: 循环被吞并或产生发布文件时抛出。
    """

    loop = tmp_path / "loop.pdf"
    loop.symlink_to(loop.name)
    control = tmp_path / "META.JSON"
    paths = (control, loop) if control_first else (loop, control)
    with pytest.raises(OSError) as raised:
        _material_plan(paths)
    assert raised.value.errno is not None
    assert not (tmp_path / "META.JSON").exists()
    with pytest.raises(FinsUploadAssetPlanError) as invalid:
        _material_plan((Path("~dayu_assets_nonexistent_user_20260929/report.txt"),))
    assert invalid.value.reason is FinsUploadAssetPlanReason.INVALID_ASSET_NAME
    with pytest.raises(FinsUploadAssetPlanError) as nul:
        _material_plan((Path("bad\x00name.txt"),))
    assert nul.value.reason is FinsUploadAssetPlanReason.INVALID_ASSET_NAME


def test_bare_plan_rejects_cross_field_identity_drift(tmp_path: Path) -> None:
    """裸计划构造即校验 material 全转换和 filing 主文件子集。

    Args:
        tmp_path: 隔离规范路径。

    Returns:
        无。

    Raises:
        AssertionError: 错配身份越过计划 owner 时抛出。
    """

    first, second = tmp_path / "deck.txt", tmp_path / "notes.md"
    _, material = _material_plan((first, second))
    with pytest.raises(ValueError, match="保序一致"):
        UploadAssetPlan(material.ordered_pairs, material.ordered_pairs[:1], next(iter(material.ordered_pairs)).original_name, SourceKind.MATERIAL)
    wrong = UploadAssetPair(first, "notes.md", "notes.md_docling.json")
    with pytest.raises(ValueError, match="身份不一致"):
        UploadAssetPlan((wrong,), (wrong,), next(iter((wrong,))).original_name, SourceKind.MATERIAL)
    with pytest.raises(ValueError, match="身份不一致"):
        UploadAssetPlan((UploadAssetPair(first, first.name, "other.json"),), (), next(iter((UploadAssetPair(first, first.name, 'other.json'),))).original_name, SourceKind.MATERIAL)
    primary = first.resolve(strict=False)
    companion = second.resolve(strict=False)
    filing = FinsUploadFilingFiles.for_upsert(primary=primary, companions=(companion,))
    _, filing_plan = plan_upload_assets(material_primary_selectors=(),
        source_kind=SourceKind.FILING,
        operation="upsert",
        files=filing.ordered_files,
        filing_selection=filing,
    )
    assert len(filing_plan.converter_pairs) == 1
    with pytest.raises(ValueError, match="主文件"):
        UploadAssetPlan(filing_plan.ordered_pairs, filing_plan.ordered_pairs, filing_plan.primary_original_name, SourceKind.FILING)


def test_plan_source_kind_is_explicit_and_matches_primary_identity(tmp_path: Path) -> None:
    """计划来源类型显式决定主文件与命名规则，空计划也保留身份。

    Args:
        tmp_path: filing 和 material 的隔离路径根。

    Returns:
        无。

    Raises:
        AssertionError: 来源类型、主文件或命名规则不一致时抛出。
    """

    path = tmp_path / "report.pdf"
    material_pair = UploadAssetPair(path, path.name, docling_storage_name(SourceKind.MATERIAL, path.name))
    filing_name = filing_original_storage_name(path)
    filing_pair = UploadAssetPair(path, filing_name, docling_storage_name(SourceKind.FILING, filing_name))
    assert UploadAssetPlan((), (), None, SourceKind.MATERIAL).source_kind is SourceKind.MATERIAL
    assert UploadAssetPlan((), (), None, SourceKind.FILING).source_kind is SourceKind.FILING
    with pytest.raises(ValueError, match="身份不一致"):
        UploadAssetPlan((filing_pair,), (filing_pair,), filing_name, SourceKind.MATERIAL)
    with pytest.raises(ValueError, match="必须携带主文件"):
        UploadAssetPlan((filing_pair,), (filing_pair,), None, SourceKind.FILING)
    with pytest.raises(ValueError, match="身份不一致"):
        UploadAssetPlan((material_pair,), (material_pair,), filing_name, SourceKind.FILING)
    assert UploadAssetPlan((material_pair,), (material_pair,), next(iter((material_pair,))).original_name, SourceKind.MATERIAL).source_kind is SourceKind.MATERIAL


def test_path_identity_and_unicode_collision(tmp_path: Path) -> None:
    """规范路径去重与 Unicode 组合名碰撞使用共享 owner。

    Args:
        tmp_path: 隔离路径根。

    Returns:
        无。

    Raises:
        AssertionError: 路径或 Unicode 比较键漂移时抛出。
    """

    path = tmp_path / "part.pdf"
    normalized = normalize_upload_asset_path(path)
    assert upload_asset_path_identity(normalized) == str(normalized)
    assert has_duplicate_upload_asset_paths((normalized, normalized))
    with pytest.raises(FinsUploadAssetPlanError) as duplicate_info:
        _material_plan((path, path))
    assert duplicate_info.value.reason is FinsUploadAssetPlanReason.DUPLICATE_FILE_PATH
    composed = unicodedata.normalize("NFC", "é") + ".pdf"
    decomposed = unicodedata.normalize("NFD", "é") + ".pdf"
    with pytest.raises(FinsUploadAssetPlanError) as unicode_info:
        _material_plan((tmp_path / "a" / composed, tmp_path / "b" / decomposed))
    assert unicode_info.value.reason is FinsUploadAssetPlanReason.ASSET_NAME_COLLISION


def test_filing_identity_and_derived_mapping_keep_existing_bytes(tmp_path: Path) -> None:
    """filing 原件 digest、suffix 与 derived 名不受 material 规则改变。

    Args:
        tmp_path: 隔离路径根。

    Returns:
        无。

    Raises:
        AssertionError: filing 身份或主文件对应漂移时抛出。
    """

    primary = (tmp_path / "Report.PDF").resolve(strict=False)
    companion = (tmp_path / "appendix.xsd").resolve(strict=False)
    selection = FinsUploadFilingFiles.for_upsert(primary=primary, companions=(companion,))
    selected, plan = plan_upload_assets(material_primary_selectors=(),
        source_kind=SourceKind.FILING,
        operation="upsert",
        files=selection.ordered_files,
        filing_selection=selection,
    )
    assert selected == selection
    assert isinstance(selected, FinsUploadFilingFiles)
    assert selected.ordered_files == (primary, companion)
    assert selected.require_primary() == primary
    assert selected.companions == (companion,)
    expected_digest = hashlib.sha256(
        b"fins-upload-asset-v1\0" + primary.as_posix().encode("utf-8")
    ).hexdigest()
    assert plan.primary_original_name == f"original-{expected_digest}.pdf"
    assert plan.primary_original_name == filing_original_storage_name(primary)
    assert len(plan.converter_pairs) == 1
    assert plan.converter_pairs[0] == plan.ordered_pairs[0]
    assert plan.ordered_pairs[0].original_name.endswith(".pdf")
    assert plan.ordered_pairs[0].docling_name == docling_storage_name(
        SourceKind.FILING, plan.ordered_pairs[0].original_name
    )
    with pytest.raises(ValueError, match="保序一致"):
        plan_upload_assets(material_primary_selectors=(),
            source_kind=SourceKind.FILING,
            operation="upsert",
            files=(companion, primary),
            filing_selection=selection,
        )
    assert docling_storage_name(SourceKind.MATERIAL, "deck.txt") == f"deck.txt{DOCLING_FILE_SUFFIX}"
