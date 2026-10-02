"""Fins 上传在转换前的唯一资产路径与仓储文件名规划 owner。"""

from __future__ import annotations

import hashlib
import errno
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Final, Literal

from dayu.fins.direct_events import canonicalize_fins_rejected_file_label
from dayu.fins.domain.enums import SourceKind
from dayu.fins.storage.asset_filename_contract import (
    is_document_source_control_name,
    source_asset_name_collision_key,
)
from dayu.fins.upload_format_contract import (
    FINS_UPLOAD_FORMAT_CAPABILITY,
    FinsUploadFilingFiles,
    FinsUploadMaterialFiles,
    MAX_MATERIAL_UPLOAD_FILES,
)

MAX_MATERIAL_ASSET_NAME_BYTES: Final[int] = 255
DOCLING_FILE_SUFFIX: Final[str] = "_docling.json"
_FILING_ASSET_IDENTITY_NAMESPACE: Final[str] = "fins-upload-asset-v1"
_FILING_ASSET_IDENTITY_SEPARATOR: Final[bytes] = b"\0"
_FILING_ORIGINAL_ASSET_PREFIX: Final[str] = "original-"


class FinsUploadAssetPlanReason(str, Enum):
    """资产规划失败的封闭业务原因。"""

    MISSING_FILES = "missing_files"
    TOO_MANY_FILES = "too_many_files"
    DUPLICATE_FILE_PATH = "duplicate_file_path"
    DUPLICATE_ORIGINAL_BASENAME = "duplicate_original_basename"
    ASSET_NAME_COLLISION = "asset_name_collision"
    RESERVED_CONTROL_NAME = "reserved_control_name"
    INVALID_ASSET_NAME = "invalid_asset_name"


class FinsUploadAssetPlanError(ValueError):
    """携带封闭原因与安全文件标签的资产规划错误。"""

    reason: FinsUploadAssetPlanReason
    file_label: str | None

    def __init__(self, reason: FinsUploadAssetPlanReason, path: Path | None = None) -> None:
        """创建不暴露本地绝对路径的规划错误。

        Args:
            reason: 封闭的资产规划失败原因。
            path: 可选关联原件路径；只投影安全 basename。

        Returns:
            无。

        Raises:
            TypeError: 原因或路径类型不符合契约时抛出。
        """

        if not isinstance(reason, FinsUploadAssetPlanReason):
            raise TypeError("资产规划原因必须属于封闭枚举")
        if path is not None and not isinstance(path, Path):
            raise TypeError("资产规划关联文件必须是 Path")
        self.reason = reason
        self.file_label = (
            canonicalize_fins_rejected_file_label(path.name) if path is not None else None
        )
        super().__init__(reason.value)


@dataclass(frozen=True, slots=True)
class UploadAssetPair:
    """同一原件路径对应的原件与 Docling 仓储身份。"""

    path: Path
    original_name: str
    docling_name: str


@dataclass(frozen=True, slots=True)
class UploadAssetPlan:
    """携带显式来源类型的保序原件、转换输入及 filing 主文件规划。"""

    ordered_pairs: tuple[UploadAssetPair, ...]
    converter_pairs: tuple[UploadAssetPair, ...]
    primary_original_name: str | None
    source_kind: SourceKind

    def __post_init__(self) -> None:
        """构造时执行同一纯资产计划不变量校验，不展开或解析路径。

        Args:
            无。

        Returns:
            无。

        Raises:
            TypeError: 来源类型、计划字段或资产项类型错误时抛出。
            ValueError: 来源类型、路径、名称、转换集合或主文件身份不一致时抛出。
        """

        self.validate()

    def validate(self) -> None:
        """纯校验原件、转换输入与主文件身份，不展开或解析路径，供构造和直接消费边界复用。

        Args:
            无。

        Returns:
            无。

        Raises:
            TypeError: 来源类型、计划字段或资产项类型错误时抛出。
            ValueError: 来源类型、路径、名称、转换集合或主文件身份不一致时抛出。
        """

        if not isinstance(self.ordered_pairs, tuple) or not isinstance(self.converter_pairs, tuple):
            raise TypeError("资产计划必须使用不可变的保序资产组")
        if not isinstance(self.source_kind, SourceKind):
            raise TypeError("资产计划 source kind 必须是 SourceKind")
        if self.primary_original_name is not None and not isinstance(
            self.primary_original_name, str
        ):
            raise TypeError("主文件身份必须是字符串或 None")
        if not self.ordered_pairs:
            if self.converter_pairs or self.primary_original_name is not None:
                raise ValueError("空资产计划不得携带转换输入或主文件")
            return
        if any(not isinstance(pair, UploadAssetPair) for pair in self.ordered_pairs + self.converter_pairs):
            raise TypeError("资产计划条目必须是 UploadAssetPair")
        filing = self.source_kind is SourceKind.FILING
        if self.primary_original_name is None:
            raise ValueError("上传资产计划必须携带主文件身份")
        if not filing and len(self.ordered_pairs) > MAX_MATERIAL_UPLOAD_FILES:
            raise FinsUploadAssetPlanError(FinsUploadAssetPlanReason.TOO_MANY_FILES)
        seen_paths: set[Path] = set()
        seen_names: set[str] = set()
        for pair in self.ordered_pairs:
            if not isinstance(pair.path, Path) or not pair.path.is_absolute() or ".." in pair.path.parts:
                raise ValueError("资产计划路径必须已规范化")
            expected_name = (
                filing_original_storage_name(pair.path) if filing else pair.path.name
            )
            expected_docling = docling_storage_name(self.source_kind, expected_name)
            if pair.original_name != expected_name or pair.docling_name != expected_docling:
                raise ValueError("资产计划原件与派生身份不一致")
            if pair.path in seen_paths or (filing and pair.original_name in seen_names):
                raise ValueError("资产计划原件身份重复")
            seen_paths.add(pair.path)
            seen_names.add(pair.original_name)
        if not filing:
            _validate_material_asset_names(tuple(enumerate(self.ordered_pairs)), None)
        primary = tuple(
            pair for pair in self.ordered_pairs
            if pair.original_name == self.primary_original_name
        )
        if len(primary) != 1:
            raise ValueError("主文件必须精确对应一个原件")
        if filing:
            if self.converter_pairs != primary:
                raise ValueError("filing 转换输入必须精确对应主文件")
        else:
            if self.converter_pairs != self.ordered_pairs:
                raise ValueError("material 转换输入必须与原件保序一致")



class UploadPrimarySelectionFailure(str, Enum):
    """唯一主文件纯选择算法的五个封闭失败原因。"""

    MISSING_FILES = "missing_files"
    DUPLICATE_FILE_PATH = "duplicate_file_path"
    MULTIPLE_PRIMARY_SELECTORS = "multiple_primary_selectors"
    MISSING_MULTI_FILE_PRIMARY = "missing_multi_file_primary"
    PRIMARY_NOT_IN_FILES = "primary_not_in_files"


class UploadPrimaryDeleteFailure(str, Enum):
    """删除请求不能声明主文件的独立原因。"""

    PRIMARY_NOT_ALLOWED_FOR_DELETE = "primary_not_allowed_for_delete"


class UploadPrimarySelectionError(ValueError):
    """携带纯选择或删除组合错误，交由用法 owner 分类。"""

    def __init__(self, reason: UploadPrimarySelectionFailure | UploadPrimaryDeleteFailure) -> None:
        """参数：封闭原因；返回：无；异常：TypeError 表示原因类型不合法。"""
        if not isinstance(reason, (UploadPrimarySelectionFailure, UploadPrimaryDeleteFailure)):
            raise TypeError("主文件选择原因类型错误")
        self.reason = reason
        super().__init__(reason.value)


class UploadPrimarySelectionPathError(ValueError):
    """保留无法规范化的 selector 输入，不吞资产规划异常。"""

    def __init__(self, input_path: Path) -> None:
        """参数：原始选择路径；返回：无；异常：TypeError 表示路径类型错误。"""
        if not isinstance(input_path, Path):
            raise TypeError("主文件选择路径必须是 Path")
        self.input_path = input_path
        super().__init__("主文件选择路径无法解析")


@dataclass(frozen=True, slots=True)
class UploadPrimarySelection:
    """从规范路径产生的 exact 主文件与保序随附文件。"""

    primary: Path
    companions: tuple[Path, ...]


def project_upload_primary_selection(
    *, files: tuple[Path, ...], primary_selectors: tuple[Path, ...],
) -> UploadPrimarySelection | UploadPrimarySelectionFailure:
    """参数：已规范文件与保留次数的选择路径；返回：唯一角色或封闭原因；异常：TypeError 表示形状错误。"""
    if not isinstance(files, tuple) or not isinstance(primary_selectors, tuple):
        raise TypeError("主文件选择要求 Path tuple")
    if any(not isinstance(path, Path) for path in (*files, *primary_selectors)):
        raise TypeError("主文件选择只接受 Path")
    if not files:
        return UploadPrimarySelectionFailure.MISSING_FILES
    if has_duplicate_upload_asset_paths(files):
        return UploadPrimarySelectionFailure.DUPLICATE_FILE_PATH
    if len(primary_selectors) > 1:
        return UploadPrimarySelectionFailure.MULTIPLE_PRIMARY_SELECTORS
    if len(files) > 1 and not primary_selectors:
        return UploadPrimarySelectionFailure.MISSING_MULTI_FILE_PRIMARY
    primary = next(iter(primary_selectors)) if primary_selectors else next(iter(files))
    if primary not in files:
        return UploadPrimarySelectionFailure.PRIMARY_NOT_IN_FILES
    return UploadPrimarySelection(primary, tuple(path for path in files if path != primary))

def normalize_upload_asset_path(path: Path) -> Path:
    """将上传路径规范成绝对路径。

    Args:
        path: 原始文件或 selector 路径。

    Returns:
        展开用户目录并解析后的路径。

    Raises:
        TypeError: 输入不是 Path 时抛出。
        ValueError: 用户目录写法无法展开时抛出。
        OSError: 路径解析出现循环时以无路径明文错误抛出，其他底层操作失败透传。
    """

    if not isinstance(path, Path):
        raise TypeError("上传路径必须是 Path")
    try:
        expanded = path.expanduser()
    except RuntimeError as exc:
        raise ValueError("上传路径的用户目录无法展开") from exc
    try:
        return expanded.resolve(strict=False)
    except RuntimeError as exc:
        # Python 3.11 把符号链接循环表示为 RuntimeError；归入现有操作失败契约。
        raise OSError(errno.ELOOP, "上传路径解析出现循环") from exc


def upload_asset_path_identity(path: Path) -> str:
    """返回规范绝对路径的 exact 字符串身份。

    Args:
        path: 已规范化的绝对路径。

    Returns:
        不做大小写折叠的路径字符串。

    Raises:
        TypeError: 输入不是 Path 时抛出。
    """

    if not isinstance(path, Path):
        raise TypeError("路径身份输入必须是 Path")
    return str(path)


def has_duplicate_upload_asset_paths(paths: tuple[Path, ...]) -> bool:
    """判断保序路径组是否有重复的 exact 规范路径身份。

    Args:
        paths: 已规范化的路径元组。

    Returns:
        出现重复身份时返回 ``True``。

    Raises:
        TypeError: 输入不是路径元组时抛出。
    """

    if not isinstance(paths, tuple) or any(not isinstance(path, Path) for path in paths):
        raise TypeError("路径组必须是 Path tuple")
    identities = tuple(upload_asset_path_identity(path) for path in paths)
    return len(identities) != len(set(identities))


def filing_original_storage_name(normalized_path: Path) -> str:
    """从已规范路径纯计算 filing 原件仓储身份，不再展开或解析路径。

    Args:
        normalized_path: 已解析的绝对文件路径。

    Returns:
        original 前缀、完整 SHA-256 与小写扩展名组成的身份。

    Raises:
        TypeError: 输入不是 Path 时抛出。
        ValueError: 路径不是已规范化绝对路径时抛出。
    """

    if not isinstance(normalized_path, Path):
        raise TypeError("filing asset identity 输入必须是 Path")
    if not normalized_path.is_absolute() or ".." in normalized_path.parts:
        raise ValueError("filing asset identity 输入必须是 absolute normalized path")
    digest_input = (
        _FILING_ASSET_IDENTITY_NAMESPACE.encode("utf-8")
        + _FILING_ASSET_IDENTITY_SEPARATOR
        + normalized_path.as_posix().encode("utf-8")
    )
    path_digest = hashlib.sha256(digest_input).hexdigest()
    return f"{_FILING_ORIGINAL_ASSET_PREFIX}{path_digest}{normalized_path.suffix.lower()}"


def docling_storage_name(source_kind: SourceKind, original_storage_name: str) -> str:
    """由原件仓储名唯一派生 Docling 仓储名。

    Args:
        source_kind: filing 或 material 来源类型。
        original_storage_name: 已规划的原件仓储名。

    Returns:
        完整原件名追加 Docling 后缀的仓储名。

    Raises:
        ValueError: 来源不受支持或 filing 原件不属于原 namespace 时抛出。
    """

    if source_kind is SourceKind.FILING:
        if not original_storage_name.startswith(_FILING_ORIGINAL_ASSET_PREFIX):
            raise ValueError("filing derived identity 必须来自 exact original identity")
    elif source_kind is not SourceKind.MATERIAL:
        raise ValueError("资产来源类型不受支持")
    return f"{original_storage_name}{DOCLING_FILE_SUFFIX}"


def _normalize_material_upload_paths(
    files: tuple[Path, ...],
) -> tuple[tuple[tuple[int, Path], ...], tuple[int, Path] | None]:
    """同源规范化 material raw 路径，保留原始索引和首个形状错误。

    Args:
        files: 保持用户输入顺序的原始路径。

    Returns:
        可解析路径的原始索引与规范路径，以及首个形状错误的索引和原始路径。

    Raises:
        TypeError: 原始路径不是 Path 时抛出。
        OSError: 循环链接或底层路径操作失败时透传。
    """

    normalized_entries: list[tuple[int, Path]] = []
    invalid_entry: tuple[int, Path] | None = None
    for index, path in enumerate(files):
        try:
            normalized_entries.append((index, normalize_upload_asset_path(path)))
        except (UnicodeEncodeError, ValueError):
            # 保留 upsert 后续的控制名优先分类；delete 仅需封闭形状错误。
            if invalid_entry is None:
                invalid_entry = (index, path)
    return tuple(normalized_entries), invalid_entry


def _validate_material_asset_names(
    indexed_pairs: tuple[tuple[int, UploadAssetPair], ...],
    invalid_entry: tuple[int, Path] | None,
) -> None:
    """按固定优先级校验整批 material 名称与格式，供规划及裸计划共用。

    Args:
        indexed_pairs: 原始输入索引与已规范路径的资产对。
        invalid_entry: 路径规范化失败时最早的原始输入项。

    Returns:
        全部名称可发布时返回 ``None``。

    Raises:
        FinsUploadAssetPlanError: 控制名、重复名、非法名或碰撞时抛出。
        FinsUploadFormatError: material 后缀不受支持时抛出。
    """

    keyed_names: list[tuple[Path, str, str]] = []
    for index, pair in indexed_pairs:
        try:
            original_key = source_asset_name_collision_key(pair.original_name)
            derived_key = source_asset_name_collision_key(pair.docling_name)
        except (ValueError, UnicodeEncodeError):
            if invalid_entry is None or index < invalid_entry[0]:
                invalid_entry = (index, pair.path)
            continue
        if is_document_source_control_name(pair.original_name) or is_document_source_control_name(pair.docling_name):
            raise FinsUploadAssetPlanError(
                FinsUploadAssetPlanReason.RESERVED_CONTROL_NAME, pair.path
            )
        try:
            derived_name_bytes = len(pair.docling_name.encode("utf-8"))
        except UnicodeEncodeError:
            if invalid_entry is None or index < invalid_entry[0]:
                invalid_entry = (index, pair.path)
            continue
        if derived_name_bytes > MAX_MATERIAL_ASSET_NAME_BYTES:
            if invalid_entry is None or index < invalid_entry[0]:
                invalid_entry = (index, pair.path)
            continue
        keyed_names.append((pair.path, original_key, derived_key))

    # 控制名先于所有业务冲突；重复 basename 仍先于非法名与碰撞。
    seen_originals: set[str] = set()
    for _, pair in indexed_pairs:
        if pair.original_name in seen_originals:
            raise FinsUploadAssetPlanError(
                FinsUploadAssetPlanReason.DUPLICATE_ORIGINAL_BASENAME, pair.path
            )
        seen_originals.add(pair.original_name)
    if invalid_entry is not None:
        raise FinsUploadAssetPlanError(FinsUploadAssetPlanReason.INVALID_ASSET_NAME, invalid_entry[1])
    seen_keys: set[str] = set()
    for path, original_key, derived_key in keyed_names:
        if original_key in seen_keys or derived_key in seen_keys or original_key == derived_key:
            raise FinsUploadAssetPlanError(FinsUploadAssetPlanReason.ASSET_NAME_COLLISION, path)
        seen_keys.update((original_key, derived_key))
    for _, pair in indexed_pairs:
        FINS_UPLOAD_FORMAT_CAPABILITY.require_material_path(pair.path)


def plan_upload_assets(
    *,
    source_kind: SourceKind,
    operation: Literal["upsert", "delete"],
    files: tuple[Path, ...],
    material_primary_selectors: tuple[Path, ...],
    filing_selection: FinsUploadFilingFiles | None = None,
) -> tuple[FinsUploadMaterialFiles | FinsUploadFilingFiles, UploadAssetPlan]:
    """一次规划 authoritative selection 和同一组原件/派生身份。

    Args:
        source_kind: filing 或 material。
        operation: 上游明确判定的资产操作模式。
        files: 保持输入顺序的原始 material 路径或 filing 路径。
        material_primary_selectors: 保留次数的材料主文件选择路径；filing 显式传空 tuple。
        filing_selection: filing 已判角色的 authoritative selection。

    Returns:
        文件选择和与之同源的不可变资产计划。

    Raises:
        FinsUploadAssetPlanError: material 数量、路径或仓储名不可规划时抛出。
        FinsUploadFormatError: material 名称有效但后缀不受支持时抛出。
        ValueError: 来源、操作或 filing selection 不符合契约时抛出。
        OSError: material 路径解析发生操作性失败时透传。
    """

    if operation not in ("upsert", "delete"):
        raise ValueError("资产操作模式不受支持")
    if source_kind is SourceKind.FILING:
        if material_primary_selectors:
            raise ValueError("filing 不接受 material selector 参数")
        if filing_selection is None:
            raise ValueError("filing 必须携带 authoritative selection")
        if files != filing_selection.ordered_files:
            raise ValueError("filing files 必须与 authoritative selection 保序一致")
        if operation == "delete":
            return filing_selection, UploadAssetPlan((), (), None, SourceKind.FILING)
        ordered = filing_selection.ordered_files
        filing_pairs_list: list[UploadAssetPair] = []
        for path in ordered:
            original_name = filing_original_storage_name(path)
            filing_pairs_list.append(
                UploadAssetPair(
                    path=path,
                    original_name=original_name,
                    docling_name=docling_storage_name(SourceKind.FILING, original_name),
                )
            )
        filing_pairs = tuple(filing_pairs_list)
        primary = filing_selection.require_primary()
        converter = tuple(pair for pair in filing_pairs if pair.path == primary)
        return filing_selection, UploadAssetPlan(
            filing_pairs, converter, filing_original_storage_name(primary), SourceKind.FILING
        )
    if source_kind is not SourceKind.MATERIAL:
        raise ValueError("资产来源类型不受支持")
    if len(files) > MAX_MATERIAL_UPLOAD_FILES:
        raise FinsUploadAssetPlanError(FinsUploadAssetPlanReason.TOO_MANY_FILES)
    if operation == "delete" and material_primary_selectors:
        raise UploadPrimarySelectionError(UploadPrimaryDeleteFailure.PRIMARY_NOT_ALLOWED_FOR_DELETE)
    normalized_entries, invalid_entry = _normalize_material_upload_paths(files)
    if operation == "delete":
        if invalid_entry is not None:
            raise FinsUploadAssetPlanError(FinsUploadAssetPlanReason.INVALID_ASSET_NAME, invalid_entry[1])
        return FinsUploadMaterialFiles.for_delete(), UploadAssetPlan((), (), None, SourceKind.MATERIAL)
    if not files:
        raise FinsUploadAssetPlanError(FinsUploadAssetPlanReason.MISSING_FILES)
    normalized = tuple(path for _, path in normalized_entries)
    if has_duplicate_upload_asset_paths(normalized):
        raise FinsUploadAssetPlanError(FinsUploadAssetPlanReason.DUPLICATE_FILE_PATH)
    indexed_pairs: list[tuple[int, UploadAssetPair]] = []
    for index, path in normalized_entries:
        original_name = path.name
        derived_name = docling_storage_name(SourceKind.MATERIAL, original_name)
        indexed_pairs.append((index, UploadAssetPair(path, original_name, derived_name)))
    _validate_material_asset_names(tuple(indexed_pairs), invalid_entry)
    normalized_selectors: list[Path] = []
    for selector in material_primary_selectors:
        try:
            normalized_selectors.append(normalize_upload_asset_path(selector))
        except (OSError, ValueError) as exc:
            raise UploadPrimarySelectionPathError(selector) from exc
    projection = project_upload_primary_selection(files=normalized, primary_selectors=tuple(normalized_selectors))
    if isinstance(projection, UploadPrimarySelectionFailure):
        raise UploadPrimarySelectionError(projection)
    ordered_pairs = tuple(pair for _, pair in indexed_pairs)
    plan = UploadAssetPlan(ordered_pairs, ordered_pairs, projection.primary.name, SourceKind.MATERIAL)
    selection = FinsUploadMaterialFiles.from_upsert_paths(normalized)
    return selection, plan
