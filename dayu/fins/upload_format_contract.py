"""Fins 上传文件格式、角色与业务文案真源。

本模块在 Documents 转换能力之上定义 Fins 上传语义：filing 具有一个显式主文件，
其余文件是不会转换的原始随附文件；material 的每个文件都必须转换。
本模块只校验路径扩展名与已确定角色，不读取文件，也不承担内容、存储、重复或主文件选择语义。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Final

from dayu.documents.docling_runtime import (
    DOCLING_CONVERTER_CAPABILITY,
    DoclingConverterCapability,
)
from dayu.fins.direct_events import (
    canonicalize_fins_public_file_label,
    validate_fins_public_file_label,
)

_XSD_COMPANION_SUFFIX: Final[str] = ".xsd"
_FORMAT_ERROR_MESSAGE_MAX_CHARS: Final[int] = 240
_PRIMARY_UNSUPPORTED_TEMPLATE: Final[str] = "财报主文件格式不受支持：{file_label}"
_COMPANION_UNSUPPORTED_TEMPLATE: Final[str] = "财报随附文件格式不受支持：{file_label}"
_MATERIAL_UNSUPPORTED_TEMPLATE: Final[str] = "补充材料文件格式不受支持：{file_label}"
_PRIMARY_UNSUPPORTED_BOUNDED_MESSAGE: Final[str] = "财报主文件格式不受支持"
_COMPANION_UNSUPPORTED_BOUNDED_MESSAGE: Final[str] = "财报随附文件格式不受支持"
_MATERIAL_UNSUPPORTED_BOUNDED_MESSAGE: Final[str] = "补充材料文件格式不受支持"


class FinsUploadFileRole(str, Enum):
    """filing 上传文件的业务角色。"""

    PRIMARY = "primary"
    COMPANION = "companion"


class FinsUploadFormatFailureKind(str, Enum):
    """上传文件格式不符合角色要求的 closed failure kind。"""

    PRIMARY_SUFFIX_UNSUPPORTED = "primary_suffix_unsupported"
    COMPANION_SUFFIX_UNSUPPORTED = "companion_suffix_unsupported"
    MATERIAL_SUFFIX_UNSUPPORTED = "material_suffix_unsupported"


_FORMAT_FAILURE_MESSAGES: Final[dict[FinsUploadFormatFailureKind, str]] = {
    FinsUploadFormatFailureKind.PRIMARY_SUFFIX_UNSUPPORTED: _PRIMARY_UNSUPPORTED_TEMPLATE,
    FinsUploadFormatFailureKind.COMPANION_SUFFIX_UNSUPPORTED: _COMPANION_UNSUPPORTED_TEMPLATE,
    FinsUploadFormatFailureKind.MATERIAL_SUFFIX_UNSUPPORTED: _MATERIAL_UNSUPPORTED_TEMPLATE,
}
_BOUNDED_FORMAT_FAILURE_MESSAGES: Final[dict[FinsUploadFormatFailureKind, str]] = {
    FinsUploadFormatFailureKind.PRIMARY_SUFFIX_UNSUPPORTED: _PRIMARY_UNSUPPORTED_BOUNDED_MESSAGE,
    FinsUploadFormatFailureKind.COMPANION_SUFFIX_UNSUPPORTED: _COMPANION_UNSUPPORTED_BOUNDED_MESSAGE,
    FinsUploadFormatFailureKind.MATERIAL_SUFFIX_UNSUPPORTED: _MATERIAL_UNSUPPORTED_BOUNDED_MESSAGE,
}


def _bounded_format_failure_message(
    kind: FinsUploadFormatFailureKind,
    *,
    file_label: str,
) -> str:
    """构造不截断 canonical label 的有界格式错误文案。

    Args:
        kind: 角色明确的格式失败类别。
        file_label: 已规范化的安全文件标签。

    Returns:
        完整标签可容纳时包含标签，否则使用同角色的固定有界文案。

    Raises:
        无。
    """

    message = _FORMAT_FAILURE_MESSAGES[kind].format(file_label=file_label)
    if len(message) <= _FORMAT_ERROR_MESSAGE_MAX_CHARS:
        return message
    return _BOUNDED_FORMAT_FAILURE_MESSAGES[kind]


class FinsUploadFormatError(ValueError):
    """上传文件扩展名不符合 Fins 角色契约。"""

    kind: FinsUploadFormatFailureKind
    file_label: str

    def __init__(self, kind: FinsUploadFormatFailureKind, file_label: str) -> None:
        """初始化有界、去路径化的格式错误。

        Args:
            kind: 角色明确的格式失败类别。
            file_label: 已规范化的安全文件标签。

        Returns:
            无。

        Raises:
            TypeError: ``kind`` 不是声明的 failure kind 时抛出。
            ValueError: ``file_label`` 不是安全公开标签时抛出。
        """

        if not isinstance(kind, FinsUploadFormatFailureKind):
            raise TypeError("kind 必须是 FinsUploadFormatFailureKind")
        validate_fins_public_file_label(file_label)
        self.kind = kind
        self.file_label = file_label
        super().__init__(_bounded_format_failure_message(kind, file_label=file_label))


def _normalize_fins_upload_suffix(suffix: str) -> str | None:
    """规范化 Fins companion 扩展名候选。

    Args:
        suffix: 可含大小写差异、空白或省略前导点的扩展名。

    Returns:
        带前导点的小写扩展名；空串、空白或只有前导点时返回 ``None``。

    Raises:
        无。
    """

    normalized = suffix.strip().lower()
    if not normalized:
        return None
    if not normalized.startswith("."):
        normalized = f".{normalized}"
    if normalized == ".":
        return None
    return normalized


def _safe_file_label(path: Path) -> str:
    """从路径产生唯一安全公开文件标签。

    Args:
        path: 发生格式错误的上传路径。

    Returns:
        可安全投影给 CLI、事件或 LLM 的文件标签。

    Raises:
        ValueError: 路径没有合法 basename 时由公共标签 owner 抛出。
    """

    return canonicalize_fins_public_file_label(path.name)


@dataclass(frozen=True, slots=True)
class FinsUploadFormatCapability:
    """Fins 上传格式与文件角色能力。

    Args:
        converter_capability: Documents 层提供的角色中立转换能力。
        companion_only_suffixes: 只能作为 filing 随附文件的扩展名集合。

    Raises:
        ValueError: companion-only 扩展名未规范化或与主文件能力重叠时抛出。
    """

    converter_capability: DoclingConverterCapability
    companion_only_suffixes: frozenset[str]

    def __post_init__(self) -> None:
        """校验 Fins overlay 的静态不变量。

        Args:
            无。

        Returns:
            无。

        Raises:
            ValueError: companion-only 集合为空、未规范化或与主文件能力重叠时抛出。
        """

        if not self.companion_only_suffixes:
            raise ValueError("Fins companion-only 扩展名集合不能为空")
        normalized_suffixes = frozenset(
            _normalize_fins_upload_suffix(suffix) for suffix in self.companion_only_suffixes
        )
        if None in normalized_suffixes or normalized_suffixes != self.companion_only_suffixes:
            raise ValueError("Fins companion-only 扩展名必须是规范化小写形式")
        if any(self.converter_capability.accepts_product_suffix(suffix) for suffix in self.companion_only_suffixes):
            raise ValueError("Fins companion-only 扩展名不能与主文件能力重叠")

    @property
    def primary_suffixes(self) -> tuple[str, ...]:
        """投影稳定有序的 filing primary 与 material 转换扩展名。

        Args:
            无。

        Returns:
            Documents converter capability 的产品扩展名 tuple。

        Raises:
            无。
        """

        return self.converter_capability.product_suffixes

    @property
    def companion_suffixes(self) -> tuple[str, ...]:
        """投影稳定有序的 filing companion 扩展名。

        Args:
            无。

        Returns:
            primary 扩展名之后追加 companion-only 扩展名的 tuple。

        Raises:
            无。
        """

        return (*self.primary_suffixes, *tuple(sorted(self.companion_only_suffixes)))

    def accepts_primary(self, suffix: str) -> bool:
        """判断扩展名能否作为 filing primary。

        Args:
            suffix: 待判断的扩展名。

        Returns:
            扩展名属于产品转换能力时返回 ``True``。

        Raises:
            无。
        """

        return self.converter_capability.accepts_product_suffix(suffix)

    def accepts_companion(self, suffix: str) -> bool:
        """判断扩展名能否作为 filing companion。

        Args:
            suffix: 待判断的扩展名。

        Returns:
            扩展名属于 primary 能力或 companion-only overlay 时返回 ``True``。

        Raises:
            无。
        """

        normalized = _normalize_fins_upload_suffix(suffix)
        if normalized is None:
            return False
        return self.accepts_primary(normalized) or normalized in self.companion_only_suffixes

    def require_filing_path(self, path: Path, *, role: FinsUploadFileRole) -> None:
        """按 filing 角色校验单个路径的扩展名。

        Args:
            path: 待校验的文件路径。
            role: 文件在 filing 请求中的业务角色。

        Returns:
            无。

        Raises:
            TypeError: ``path`` 或 ``role`` 类型错误时抛出。
            FinsUploadFormatError: 扩展名不符合对应角色时抛出。
        """

        if not isinstance(path, Path):
            raise TypeError("path 必须是 Path")
        if not isinstance(role, FinsUploadFileRole):
            raise TypeError("role 必须是 FinsUploadFileRole")
        if role is FinsUploadFileRole.PRIMARY:
            accepted = self.accepts_primary(path.suffix)
            failure_kind = FinsUploadFormatFailureKind.PRIMARY_SUFFIX_UNSUPPORTED
        else:
            accepted = self.accepts_companion(path.suffix)
            failure_kind = FinsUploadFormatFailureKind.COMPANION_SUFFIX_UNSUPPORTED
        if not accepted:
            raise FinsUploadFormatError(failure_kind, _safe_file_label(path))

    def require_material_path(self, path: Path) -> None:
        """校验 material 文件具备 converter-required 扩展名。

        Args:
            path: 待校验的 material 文件路径。

        Returns:
            无。

        Raises:
            TypeError: ``path`` 不是 ``Path`` 时抛出。
            FinsUploadFormatError: 扩展名不属于产品转换能力时抛出。
        """

        if not isinstance(path, Path):
            raise TypeError("path 必须是 Path")
        if not self.accepts_primary(path.suffix):
            raise FinsUploadFormatError(
                FinsUploadFormatFailureKind.MATERIAL_SUFFIX_UNSUPPORTED,
                _safe_file_label(path),
            )


FINS_UPLOAD_FORMAT_CAPABILITY: Final[FinsUploadFormatCapability] = FinsUploadFormatCapability(
    converter_capability=DOCLING_CONVERTER_CAPABILITY,
    companion_only_suffixes=frozenset({_XSD_COMPANION_SUFFIX}),
)


@dataclass(frozen=True, slots=True)
class FinsUploadFilingFiles:
    """带明确 primary/companion 角色的 filing 文件 selection。

    Args:
        primary: 已验证、必须转换的 filing 主文件；delete selection 为 ``None``。
        companions: 按原请求相对顺序保存、仅原样上传的随附文件。

    Raises:
        TypeError: companions 不是 tuple 或任一文件不是 ``Path`` 时抛出。
        ValueError: 空 primary 携带 companion 时抛出。
        FinsUploadFormatError: 任一文件扩展名不符合其角色时抛出。
    """

    primary: Path | None
    companions: tuple[Path, ...]

    def __post_init__(self) -> None:
        """校验 selection 的角色与格式不变量。

        Args:
            无。

        Returns:
            无。

        Raises:
            TypeError: companions 不是 tuple 或任一文件不是 ``Path`` 时抛出。
            ValueError: 空 primary 携带 companion 时抛出。
            FinsUploadFormatError: 任一文件扩展名不符合其角色时抛出。
        """

        if not isinstance(self.companions, tuple):
            raise TypeError("companions 必须是 Path tuple")
        if self.primary is None:
            if self.companions:
                raise ValueError("delete filing selection 不能包含 companion")
            return
        FINS_UPLOAD_FORMAT_CAPABILITY.require_filing_path(
            self.primary,
            role=FinsUploadFileRole.PRIMARY,
        )
        for companion in self.companions:
            FINS_UPLOAD_FORMAT_CAPABILITY.require_filing_path(
                companion,
                role=FinsUploadFileRole.COMPANION,
            )

    @classmethod
    def for_upsert(
        cls,
        *,
        primary: Path,
        companions: tuple[Path, ...],
    ) -> FinsUploadFilingFiles:
        """从已确定角色的路径构造 filing upsert selection。

        Args:
            primary: 上游 admission 已确定的唯一主文件。
            companions: 上游 admission 已确定且保持相对顺序的随附文件。

        Returns:
            保留 authoritative primary/companions 的不可变 selection。

        Raises:
            TypeError: ``primary`` 不是 ``Path``、companions 不是 tuple 或任一随附文件不是 ``Path`` 时抛出。
            FinsUploadFormatError: 任一文件扩展名不符合其角色时抛出。
        """

        if not isinstance(primary, Path):
            raise TypeError("primary 必须是 Path")
        return cls(primary=primary, companions=companions)

    @classmethod
    def for_delete(cls) -> FinsUploadFilingFiles:
        """构造 filing delete 的唯一合法空 selection。

        Args:
            无。

        Returns:
            不含 primary 与 companions 的不可变 selection。

        Raises:
            无。
        """

        return cls(primary=None, companions=())

    @property
    def ordered_files(self) -> tuple[Path, ...]:
        """按角色顺序投影全部 filing 文件。

        Args:
            无。

        Returns:
            upsert 时先返回 authoritative primary，再返回保持原相对顺序的 companions；delete 时为空 tuple。

        Raises:
            无。
        """

        if self.primary is None:
            return ()
        return (self.primary, *self.companions)

    @property
    def is_empty(self) -> bool:
        """判断 selection 是否为 delete 空状态。

        Args:
            无。

        Returns:
            不含文件时返回 ``True``。

        Raises:
            无。
        """

        return self.primary is None

    def require_primary(self) -> Path:
        """返回 upsert selection 的 primary。

        Args:
            无。

        Returns:
            filing primary 路径。

        Raises:
            ValueError: 当前是 delete 空 selection 时抛出。
        """

        if self.primary is None:
            raise ValueError("delete filing selection 没有 primary")
        return self.primary


@dataclass(frozen=True, slots=True)
class FinsUploadMaterialFiles:
    """所有文件都必须转换的 material 文件 selection。

    Args:
        files: 保留用户输入顺序的 material 路径 tuple；delete selection 为空。

    Raises:
        TypeError: 任一文件不是 ``Path`` 时抛出。
        FinsUploadFormatError: 任一文件扩展名不属于产品转换能力时抛出。
    """

    files: tuple[Path, ...]

    def __post_init__(self) -> None:
        """校验每个 material 文件都具备 converter-required 格式。

        Args:
            无。

        Returns:
            无。

        Raises:
            TypeError: 任一文件不是 ``Path`` 时抛出。
            FinsUploadFormatError: 任一文件扩展名不属于产品转换能力时抛出。
        """

        for path in self.files:
            FINS_UPLOAD_FORMAT_CAPABILITY.require_material_path(path)

    @classmethod
    def from_upsert_paths(cls, paths: tuple[Path, ...]) -> FinsUploadMaterialFiles:
        """从非空有序路径构造 material upsert selection。

        Args:
            paths: 用户给定顺序的非空 material 路径 tuple。

        Returns:
            每项均 converter-required 的不可变 selection。

        Raises:
            ValueError: ``paths`` 为空时抛出。
            TypeError: 任一文件不是 ``Path`` 时抛出。
            FinsUploadFormatError: 任一文件扩展名不受支持时抛出。
        """

        if not paths:
            raise ValueError("material upsert selection 必须至少包含一个文件")
        return cls(files=paths)

    @classmethod
    def for_delete(cls) -> FinsUploadMaterialFiles:
        """构造 material delete 的唯一合法空 selection。

        Args:
            无。

        Returns:
            不含文件的不可变 selection。

        Raises:
            无。
        """

        return cls(files=())

    @property
    def is_empty(self) -> bool:
        """判断 selection 是否为 delete 空状态。

        Args:
            无。

        Returns:
            不含文件时返回 ``True``。

        Raises:
            无。
        """

        return not self.files


@dataclass(frozen=True, slots=True)
class FinsUploadFormatTextProjection:
    """CLI help 与 LLM schema 共用的业务可读格式投影。

    Args:
        filing_files: filing ``--files`` 的自足说明。
        filing_primary: filing ``--primary`` 的自足说明。
        material_files: material ``--files`` 的自足说明。
        upload_tool_files: 同时覆盖 filing 与 material 的工具字段说明。
        upload_tool_primary: 工具 ``primary`` 字段的自足说明。
        upload_tool_material_primary_failure: material 携带 ``primary`` 时的工具失败说明。

    Raises:
        无。
    """

    filing_files: str
    filing_primary: str
    material_files: str
    upload_tool_files: str
    upload_tool_primary: str
    upload_tool_material_primary_failure: str


def _project_filing_primary_rules(
    *,
    files_label: str,
    primary_label: str,
) -> str:
    """按入口字段名投影同一组 filing 主文件选择规则。

    Args:
        files_label: 当前入口的文件集合字段名。
        primary_label: 当前入口的主文件 selector 字段名。

    Returns:
        包含单文件、多文件、membership、顺序与 delete 规则的自足文本。

    Raises:
        无。
    """

    return (
        f"单文件 filing 可省略 {primary_label}，省略时唯一文件就是主文件；"
        f"多文件 filing 必须恰好指定一个 {primary_label}；"
        f"{primary_label} 必须精确匹配 {files_label} 中的一个路径；"
        f"{files_label} 的顺序不决定主文件角色；"
        f"delete 必须省略 {files_label} 和 {primary_label}。"
    )


def project_fins_upload_format_text(
    capability: FinsUploadFormatCapability,
) -> FinsUploadFormatTextProjection:
    """从 Fins 格式 capability 产生稳定、自足的用户与 LLM 文案。

    Args:
        capability: 负责上传格式与文件角色语义的 Fins capability。

    Returns:
        CLI filing/material help 与 upload tool schema 共用的不可变文本投影。

    Raises:
        无。
    """

    suffixes = ", ".join(capability.primary_suffixes)
    companion_only_suffixes = ", ".join(sorted(capability.companion_only_suffixes))
    filing_primary = _project_filing_primary_rules(
        files_label="--files",
        primary_label="--primary",
    )
    upload_tool_primary_rules = _project_filing_primary_rules(
        files_label="files",
        primary_label="primary",
    )
    upload_tool_material_primary_failure = (
        "upload_kind=material 不得提供 primary；请省略 primary 字段"
    )
    filing_files = (
        "auto/create/update 必须至少提供一个文件。已选主文件必须实际转换成功；"
        "其余文件是仅原样保存、不转换的随附文件。"
        f"主文件支持后缀：{suffixes}；随附文件支持这些后缀以及 {companion_only_suffixes}，"
        f"且 {companion_only_suffixes} 只能作为随附文件。"
        ".xml 仅是 XBRL XML 候选，不代表任意 XML；主文件后缀通过只表示具备转换资格，不保证文件内容转换成功。"
        "随附文件只校验可随批保存的后缀，不执行转换。"
        ".json 仅是 Docling JSON 候选，不代表任意 JSON 内容可转换。delete 不得提供文件。"
    )
    material_files = (
        "auto/create/update 必须至少提供一个文件；"
        f"每个文件都必须使用转换器支持的后缀：{suffixes}，并逐个实际转换成功；"
        "后缀通过只表示具备转换资格，不保证文件内容转换成功。delete 不得提供文件。"
    )
    return FinsUploadFormatTextProjection(
        filing_files=filing_files,
        filing_primary=filing_primary,
        material_files=material_files,
        upload_tool_files=(
            f"upload_kind=filing 时，{filing_files}"
            f"upload_kind=material 时，{material_files}"
            "每个路径必须指向已存在、非空的普通文件。"
        ),
        upload_tool_primary=(
            f"仅用于 upload_kind=filing：{upload_tool_primary_rules}"
            f"{upload_tool_material_primary_failure}。"
            "primary 是用户选择的业务角色，不能根据质量、重要性或转换是否成功推断。"
        ),
        upload_tool_material_primary_failure=upload_tool_material_primary_failure,
    )


FINS_UPLOAD_FORMAT_TEXT: Final[FinsUploadFormatTextProjection] = project_fins_upload_format_text(
    FINS_UPLOAD_FORMAT_CAPABILITY
)


__all__: tuple[str, ...] = (
    "FINS_UPLOAD_FORMAT_CAPABILITY",
    "FINS_UPLOAD_FORMAT_TEXT",
    "FinsUploadFileRole",
    "FinsUploadFilingFiles",
    "FinsUploadFormatCapability",
    "FinsUploadFormatError",
    "FinsUploadFormatFailureKind",
    "FinsUploadFormatTextProjection",
    "FinsUploadMaterialFiles",
    "project_fins_upload_format_text",
)
