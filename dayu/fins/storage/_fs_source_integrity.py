"""文件系统 source publication 完整性检查的唯一私有语义 owner。

本模块定义 published 与 staged source 共用的 typed inspection payload。调用方必须
已经持有对应 ticker 的 publication guard，或已经验证真实 open batch capability；
本模块不获取锁、不解析 batch capability，也不拥有 staging URI 规则。
"""

from __future__ import annotations

import hashlib
import os
import stat
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Final, cast

from dayu.contracts.json_value import JsonValue
from dayu.fins.domain.document_models import (
    FilingManifestItem,
    FinsIngestMethod,
    FinsSourceProvider,
    MaterialManifestItem,
    SourceDocumentProvenance,
    SourceDocumentRevision,
)
from dayu.fins.domain.enums import SourceKind

from ._fs_identity import (
    _FILING_IDENTITY_NAMESPACE,
    _IDENTITY_DESCRIPTOR_FILENAME,
    _MATERIAL_IDENTITY_NAMESPACE,
    _TICKER_IDENTITY_NAMESPACE,
    _identity_directory_path,
    _read_identity_descriptor,
    _require_external_identity,
)
from ._fs_storage_utils import (
    _DOWNLOAD_REJECTIONS_FILENAME,
    _REJECTED_FILINGS_DIRNAME,
    _SOURCE_META_FILENAME,
    _list_directory,
    _normalize_filename,
    _open_binary_file,
    _project_filesystem_error,
    _raise_path_free_error,
    _read_json_object,
)
from .repository_protocols import SourceSnapshotFileDescriptor
from .source_integrity import (
    SourceIntegrityClassification,
    SourceIntegrityPreflightError,
    SourceIntegrityPreflightReason,
    SourceIntegrityReason,
    SourceIntegrityRepairBlockedReason,
    SourceIntegrityStatus,
)


_SOURCE_REVISION_META_FIELD: Final[str] = "_published_source_revision"
_FILING_MANIFEST_FILENAME: Final[str] = "filing_manifest.json"
_MATERIAL_MANIFEST_FILENAME: Final[str] = "material_manifest.json"
_FILE_SOURCE_ORIGINAL: Final[str] = "original"
_FILE_SOURCE_DOCLING: Final[str] = "docling"
_HASH_CHUNK_SIZE: Final[int] = 64 * 1024


@dataclass(frozen=True, slots=True)
class _InspectedSourceFile:
    """同一次 inspection 已验证的业务文件事实。

    Attributes:
        descriptor: 不暴露 filesystem locator 的 snapshot 文件描述符。
        physical_path: caller 当前稳定视图中的物理文件路径。
    """

    descriptor: SourceSnapshotFileDescriptor
    physical_path: Path


@dataclass(frozen=True, slots=True)
class _SourcePublicationInspection:
    """单个 source publication 的完整 typed inspection payload。

    Attributes:
        classification: 含 target-local 与 shared manifest 原因的公共分类。
        content_classification: 不含 shared manifest 原因的 source-local 分类。
        persisted_meta: 可信且仍含 storage 私有 revision 的元数据。
        business_meta: 可信且已移除 storage 私有 revision 的业务元数据。
        provenance: 从可信 meta 解析出的来源事实。
        revision: 与 classification 同版的可信 opaque revision。
        files: 同一次扫描验证的业务文件事实。
        primary_document: 同一次扫描验证的主文件名。
        canonical_manifest_item: 由 manifest item owner 从可信 meta 产生的投影。
    """

    classification: SourceIntegrityClassification
    content_classification: SourceIntegrityClassification
    persisted_meta: Mapping[str, JsonValue] | None
    business_meta: Mapping[str, JsonValue] | None
    provenance: SourceDocumentProvenance | None
    revision: SourceDocumentRevision | None
    files: tuple[_InspectedSourceFile, ...]
    primary_document: str | None
    canonical_manifest_item: Mapping[str, JsonValue] | None


@dataclass(frozen=True, slots=True)
class _SourceKindPublicationInspection:
    """同一次 source-kind 扫描产生的聚合 inspection payload。

    Attributes:
        target: exact-target mode 的精确目标；whole-kind mode 固定为 ``None``。
        inventory: 按 document ID 稳定排序的完整 source-kind inventory。
        shared_manifest_reasons: 同一次扫描识别出的 source-kind shared 原因。
        canonical_manifest_items: 由全部 complete source 产生的 canonical manifest 项目。
        repair_blocked_reason: 其它 source 或 canonical aggregate 对 repair 的阻断原因。
    """

    target: _SourcePublicationInspection | None
    inventory: tuple[_SourcePublicationInspection, ...]
    shared_manifest_reasons: tuple[SourceIntegrityReason, ...]
    canonical_manifest_items: tuple[Mapping[str, JsonValue], ...]
    repair_blocked_reason: SourceIntegrityRepairBlockedReason | None


@dataclass(frozen=True, slots=True)
class _DeclaredSourceFile:
    """已通过结构校验的单个 source file 声明。

    Attributes:
        inspected: snapshot descriptor 与 physical locator。
        source: 可选 original/docling 来源角色。
        original_filename: 可选用户输入 basename。
        derived_from: 可选派生来源 identity。
    """

    inspected: _InspectedSourceFile
    source: str | None
    original_filename: str | None
    derived_from: str | None


@dataclass(frozen=True, slots=True)
class _ManifestInspection:
    """一次 source-kind manifest 读取的封闭结构事实。

    Attributes:
        exists: manifest locator 是否存在。
        trusted: manifest shape、ticker 与 document identities 是否可信。
        items: 以 canonical document ID 为键的原始 manifest item。
    """

    exists: bool
    trusted: bool
    items: Mapping[str, Mapping[str, JsonValue]]


def _inspect_source_kind_unguarded(
    *,
    ticker: str,
    source_kind: SourceKind,
    ticker_dir: Path,
    source_root: Path,
    requested_document_id: str | None,
) -> _SourceKindPublicationInspection:
    """在 caller 提供的稳定视图中检查一个完整 source kind。

    ``requested_document_id`` 非空时为 exact-target mode，返回非空 ``target``；
    为 ``None`` 时为 whole-kind mode，返回的 ``target`` 必须为 ``None``。两种模式
    都必须在一次扫描中产生完整 inventory、shared manifest reasons 与 canonical
    manifest facts，不得在本函数内获取 publication guard 或解析 batch capability。

    Args:
        ticker: 已由 caller 校验的 exact canonical ticker。
        source_kind: 已规范化的 filing 或 material source kind。
        ticker_dir: published ticker 或真实 staging ticker 的稳定根目录。
        source_root: ``ticker_dir`` 下当前 source kind 的稳定根目录。
        requested_document_id: exact-target mode 的 canonical document ID；whole-kind
            mode 为 ``None``。

    Returns:
        同一次 filesystem scan 产生的 typed source-kind inspection payload。

    Raises:
        SourceIntegrityPreflightError: whole-kind mode 遇到无法归属单一 target 的
            root 或 manifest structural corruption 时抛出。
        ValueError: caller 传入的 ticker、source kind、locator 或 document ID 不满足
            frozen capability precondition 时抛出。
        OSError: 文件系统 operational I/O 失败时抛出 path-free 异常。
    """

    external_ticker = _require_external_identity(ticker, field_name="ticker")
    if not isinstance(source_kind, SourceKind):
        raise ValueError("source_kind 必须是 SourceKind")
    external_document_id = (
        None
        if requested_document_id is None
        else _require_external_identity(
            requested_document_id,
            field_name="requested_document_id",
        )
    )
    if source_root.parent != ticker_dir:
        raise ValueError("source_root 必须是 ticker_dir 的直属 source-kind 根")

    ticker_state = _lstat_optional(ticker_dir, action="检查 source integrity ticker root")
    if ticker_state is None:
        return _empty_source_kind_inspection(
            ticker=external_ticker,
            source_kind=source_kind,
            requested_document_id=external_document_id,
        )
    ticker_trusted = _is_non_symlink_directory(ticker_state)
    if ticker_trusted:
        try:
            _read_identity_descriptor(
                ticker_dir,
                _TICKER_IDENTITY_NAMESPACE,
                expected_external_identity=external_ticker,
            )
        except (FileNotFoundError, KeyError, TypeError, ValueError):
            ticker_trusted = False
    if not ticker_trusted:
        return _close_unassignable_root(
            ticker=external_ticker,
            source_kind=source_kind,
            requested_document_id=external_document_id,
            reason=SourceIntegrityReason.IDENTITY_UNTRUSTED,
        )

    root_state = _lstat_optional(source_root, action="检查 source integrity source root")
    if root_state is None:
        return _empty_source_kind_inspection(
            ticker=external_ticker,
            source_kind=source_kind,
            requested_document_id=external_document_id,
        )
    if not _is_non_symlink_directory(root_state):
        return _close_unassignable_root(
            ticker=external_ticker,
            source_kind=source_kind,
            requested_document_id=external_document_id,
            reason=SourceIntegrityReason.UNSAFE_FILESYSTEM_ENTRY,
        )

    identity_namespace = (
        _FILING_IDENTITY_NAMESPACE
        if source_kind is SourceKind.FILING
        else _MATERIAL_IDENTITY_NAMESPACE
    )
    manifest_name = _manifest_filename(source_kind)
    requested_directory = (
        None
        if external_document_id is None
        else _identity_directory_path(
            source_root,
            identity_namespace,
            external_document_id,
        )
    )
    inspections_by_id: dict[str, _SourcePublicationInspection] = {}
    unassignable_root_fact = False
    for child in _list_directory(source_root, action="枚举 source integrity source root"):
        if child.name == manifest_name or _is_allowed_filing_control(child.name, source_kind):
            continue
        child_state = _lstat_optional(child, action="检查 source integrity root entry")
        if child_state is None:
            unassignable_root_fact = True
            continue
        if not _is_non_symlink_directory(child_state):
            unassignable_root_fact = True
            continue
        try:
            document_id = _read_identity_descriptor(child, identity_namespace)
        except (FileNotFoundError, KeyError, TypeError, ValueError):
            if requested_directory is not None and child == requested_directory:
                if external_document_id is None:
                    raise ValueError("exact target directory 缺少 requested document ID")
                inspections_by_id[external_document_id] = _unsafe_source_inspection(
                    ticker=external_ticker,
                    source_kind=source_kind,
                    document_id=external_document_id,
                    reason=SourceIntegrityReason.IDENTITY_UNTRUSTED,
                )
            else:
                unassignable_root_fact = True
            continue
        if document_id in inspections_by_id:
            unassignable_root_fact = True
            continue
        inspections_by_id[document_id] = _inspect_source_directory(
            ticker=external_ticker,
            source_kind=source_kind,
            document_id=document_id,
            source_directory=child,
        )

    if unassignable_root_fact and external_document_id is None:
        raise SourceIntegrityPreflightError(
            SourceIntegrityPreflightReason.UNSAFE_PUBLICATION
        )

    ordered_inventory = tuple(
        inspections_by_id[document_id]
        for document_id in sorted(inspections_by_id)
    )
    manifest = _inspect_source_manifest(
        ticker=external_ticker,
        source_kind=source_kind,
        manifest_path=source_root / manifest_name,
    )
    inventory, shared_manifest_reasons = _apply_manifest_facts(
        ticker=external_ticker,
        source_kind=source_kind,
        inventory=ordered_inventory,
        manifest=manifest,
    )
    canonical_manifest_items = _canonical_manifest_items(inventory)
    target = _select_exact_target(
        ticker=external_ticker,
        source_kind=source_kind,
        requested_document_id=external_document_id,
        inventory=inventory,
        manifest=manifest,
    )
    if unassignable_root_fact and target is not None and target.classification.status is not SourceIntegrityStatus.MISSING:
        target = _with_unsafe_classification(
            target,
            SourceIntegrityReason.CROSS_SOURCE_INCONSISTENCY,
        )
        inventory = tuple(
            target
            if item.classification.document_id == target.classification.document_id
            else item
            for item in inventory
        )
    repair_blocked_reason = _derive_repair_blocked_reason(
        target=target,
        inventory=inventory,
        canonical_manifest_items=canonical_manifest_items,
        unassignable_root_fact=unassignable_root_fact,
    )
    return _SourceKindPublicationInspection(
        target=target,
        inventory=inventory,
        shared_manifest_reasons=shared_manifest_reasons,
        canonical_manifest_items=canonical_manifest_items,
        repair_blocked_reason=repair_blocked_reason,
    )


def _empty_source_kind_inspection(
    *,
    ticker: str,
    source_kind: SourceKind,
    requested_document_id: str | None,
) -> _SourceKindPublicationInspection:
    """构造 source-kind root 不存在时的封闭 inspection。

    Args:
        ticker: exact canonical ticker。
        source_kind: filing 或 material。
        requested_document_id: exact target；whole-kind mode 为 ``None``。

    Returns:
        空 inventory；exact mode 额外携带 ``MISSING`` target。

    Raises:
        无。
    """

    target = (
        None
        if requested_document_id is None
        else _missing_source_inspection(
            ticker=ticker,
            source_kind=source_kind,
            document_id=requested_document_id,
        )
    )
    return _SourceKindPublicationInspection(
        target=target,
        inventory=(),
        shared_manifest_reasons=(),
        canonical_manifest_items=(),
        repair_blocked_reason=None,
    )


def _close_unassignable_root(
    *,
    ticker: str,
    source_kind: SourceKind,
    requested_document_id: str | None,
    reason: SourceIntegrityReason,
) -> _SourceKindPublicationInspection:
    """把 source-kind root 级结构损坏闭合到 exact target 或 whole preflight。

    Args:
        ticker: exact canonical ticker。
        source_kind: filing 或 material。
        requested_document_id: exact target；whole-kind mode 为 ``None``。
        reason: exact target 使用的 unsafe reason。

    Returns:
        exact mode 的 ``UNSAFE`` target payload。

    Raises:
        SourceIntegrityPreflightError: whole-kind mode 无法把 root 损坏归属到 target 时抛出。
    """

    if requested_document_id is None:
        raise SourceIntegrityPreflightError(
            SourceIntegrityPreflightReason.UNSAFE_PUBLICATION
        )
    target = _unsafe_source_inspection(
        ticker=ticker,
        source_kind=source_kind,
        document_id=requested_document_id,
        reason=reason,
    )
    return _SourceKindPublicationInspection(
        target=target,
        inventory=(),
        shared_manifest_reasons=(),
        canonical_manifest_items=(),
        repair_blocked_reason=(
            SourceIntegrityRepairBlockedReason.CROSS_SOURCE_PUBLICATION_UNSAFE
        ),
    )


def _inspect_source_directory(
    *,
    ticker: str,
    source_kind: SourceKind,
    document_id: str,
    source_directory: Path,
) -> _SourcePublicationInspection:
    """检查一个 identity 已可信的 source directory。

    Args:
        ticker: exact canonical ticker。
        source_kind: filing 或 material。
        document_id: descriptor 已验证的 canonical document ID。
        source_directory: 当前稳定视图中的 source directory。

    Returns:
        source-local content inspection；尚不叠加 shared manifest facts。

    Raises:
        OSError: meta、目录或业务文件 operational I/O 失败时抛出 path-free 异常。
    """

    meta_path = source_directory / _SOURCE_META_FILENAME
    meta_state = _lstat_optional(meta_path, action="检查 source integrity meta")
    if meta_state is None or not _is_non_symlink_regular_file(meta_state):
        return _unsafe_source_inspection(
            ticker=ticker,
            source_kind=source_kind,
            document_id=document_id,
            reason=SourceIntegrityReason.META_UNTRUSTED,
        )
    try:
        persisted_meta = cast(
            Mapping[str, JsonValue],
            _read_json_object(meta_path),
        )
    except (FileNotFoundError, KeyError, TypeError, ValueError):
        return _unsafe_source_inspection(
            ticker=ticker,
            source_kind=source_kind,
            document_id=document_id,
            reason=SourceIntegrityReason.META_UNTRUSTED,
        )
    if (
        persisted_meta.get("ticker") != ticker
        or persisted_meta.get("document_id") != document_id
        or persisted_meta.get("source_kind") != source_kind.value
    ):
        return _unsafe_source_inspection(
            ticker=ticker,
            source_kind=source_kind,
            document_id=document_id,
            reason=SourceIntegrityReason.IDENTITY_UNTRUSTED,
        )
    try:
        provenance = SourceDocumentProvenance.from_meta(
            persisted_meta,
            source_kind,
        )
    except (KeyError, TypeError, ValueError):
        return _unsafe_source_inspection(
            ticker=ticker,
            source_kind=source_kind,
            document_id=document_id,
            reason=SourceIntegrityReason.PROVENANCE_UNTRUSTED,
        )
    if not provenance.ingest_complete:
        return _unsafe_source_inspection(
            ticker=ticker,
            source_kind=source_kind,
            document_id=document_id,
            reason=SourceIntegrityReason.PROVENANCE_UNTRUSTED,
        )
    try:
        revision = _source_revision_from_meta(persisted_meta)
    except (KeyError, TypeError, ValueError):
        return _unsafe_source_inspection(
            ticker=ticker,
            source_kind=source_kind,
            document_id=document_id,
            reason=SourceIntegrityReason.REVISION_UNTRUSTED,
        )
    declared_files = _parse_declared_source_files(
        persisted_meta=persisted_meta,
        source_directory=source_directory,
    )
    if declared_files is None:
        return _unsafe_source_inspection(
            ticker=ticker,
            source_kind=source_kind,
            document_id=document_id,
            reason=SourceIntegrityReason.FILE_DECLARATION_UNTRUSTED,
        )
    physical_structure_reason = _validate_physical_structure(
        source_directory=source_directory,
        declared_files=declared_files,
    )
    if physical_structure_reason is not None:
        return _unsafe_source_inspection(
            ticker=ticker,
            source_kind=source_kind,
            document_id=document_id,
            reason=physical_structure_reason,
        )
    role_reasons = _classify_role_projection(
        source_kind=source_kind,
        provenance=provenance,
        persisted_meta=persisted_meta,
        declared_files=declared_files,
    )
    if role_reasons is None:
        return _unsafe_source_inspection(
            ticker=ticker,
            source_kind=source_kind,
            document_id=document_id,
            reason=SourceIntegrityReason.FILE_DECLARATION_UNTRUSTED,
        )
    try:
        canonical_manifest_item = _canonical_manifest_item(
            source_kind=source_kind,
            persisted_meta=persisted_meta,
        )
    except (KeyError, TypeError, ValueError):
        return _unsafe_source_inspection(
            ticker=ticker,
            source_kind=source_kind,
            document_id=document_id,
            reason=SourceIntegrityReason.META_UNTRUSTED,
        )
    physical_reasons = _classify_physical_file_facts(declared_files)
    reasons = _ordered_reasons((*role_reasons, *physical_reasons))
    status = (
        SourceIntegrityStatus.REPAIR_REQUIRED
        if reasons
        else SourceIntegrityStatus.COMPLETE
    )
    classification = SourceIntegrityClassification(
        ticker=ticker,
        source_kind=source_kind,
        document_id=document_id,
        revision=revision,
        status=status,
        reasons=reasons,
    )
    business_meta = _source_meta_without_revision(persisted_meta)
    return _SourcePublicationInspection(
        classification=classification,
        content_classification=classification,
        persisted_meta=persisted_meta,
        business_meta=business_meta,
        provenance=provenance,
        revision=revision,
        files=tuple(item.inspected for item in declared_files),
        primary_document=_trusted_primary_document(
            persisted_meta=persisted_meta,
            declared_files=declared_files,
        ),
        canonical_manifest_item=(
            canonical_manifest_item
            if status is SourceIntegrityStatus.COMPLETE
            else None
        ),
    )


def _parse_declared_source_files(
    *,
    persisted_meta: Mapping[str, JsonValue],
    source_directory: Path,
) -> tuple[_DeclaredSourceFile, ...] | None:
    """解析并严格校验 source meta 的 files 声明。

    Args:
        persisted_meta: 已通过 identity、provenance 与 revision 校验的 meta。
        source_directory: 当前 source directory。

    Returns:
        保持 meta 顺序的 typed 声明；结构不可信时返回 ``None``。

    Raises:
        无。
    """

    raw_files = persisted_meta.get("files")
    if not isinstance(raw_files, list) or not raw_files:
        return None
    result: list[_DeclaredSourceFile] = []
    names: set[str] = set()
    for raw_file in raw_files:
        if not isinstance(raw_file, Mapping):
            return None
        raw_name = raw_file.get("name")
        if not isinstance(raw_name, str):
            return None
        try:
            name = _normalize_filename(raw_name)
        except ValueError:
            return None
        if (
            name != raw_name
            or name in {_SOURCE_META_FILENAME, _IDENTITY_DESCRIPTOR_FILENAME}
            or name in names
        ):
            return None
        raw_uri = raw_file.get("uri")
        if not isinstance(raw_uri, str) or not raw_uri:
            return None
        size = _optional_non_negative_int(raw_file.get("size"))
        if raw_file.get("size") is not None and size is None:
            return None
        sha256 = _optional_canonical_sha256(raw_file.get("sha256"))
        if raw_file.get("sha256") is not None and sha256 is None:
            return None
        etag = _optional_text(raw_file.get("etag"))
        last_modified = _optional_text(raw_file.get("last_modified"))
        content_type = _optional_text(raw_file.get("content_type"))
        if (
            raw_file.get("etag") is not None and etag is None
            or raw_file.get("last_modified") is not None and last_modified is None
            or raw_file.get("content_type") is not None and content_type is None
        ):
            return None
        source_valid, source = _optional_role_text(raw_file, "source")
        original_filename_valid, original_filename = _optional_non_empty_text(
            raw_file,
            "original_filename",
        )
        derived_from_valid, derived_from = _optional_non_empty_text(
            raw_file,
            "derived_from",
        )
        if not source_valid or not original_filename_valid or not derived_from_valid:
            return None
        names.add(name)
        result.append(
            _DeclaredSourceFile(
                inspected=_InspectedSourceFile(
                    descriptor=SourceSnapshotFileDescriptor(
                        name=name,
                        etag=etag,
                        last_modified=last_modified,
                        size=size,
                        content_type=content_type,
                        sha256=sha256,
                    ),
                    physical_path=source_directory / name,
                ),
                source=source,
                original_filename=original_filename,
                derived_from=derived_from,
            )
        )
    return tuple(result)


def _optional_non_negative_int(value: JsonValue | None) -> int | None:
    """收窄可选非负整数。

    Args:
        value: JSON 字段值。

    Returns:
        合法整数；缺失或非法时返回 ``None``。

    Raises:
        无。
    """

    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _optional_canonical_sha256(value: JsonValue | None) -> str | None:
    """收窄可选 canonical SHA-256。

    Args:
        value: JSON 字段值。

    Returns:
        合法摘要；缺失或非法时返回 ``None``。

    Raises:
        无。
    """

    if not isinstance(value, str) or len(value) != 64 or value != value.lower():
        return None
    try:
        int(value, 16)
    except ValueError:
        return None
    return value


def _optional_text(value: JsonValue | None) -> str | None:
    """收窄允许空字符串的可选文本字段。

    Args:
        value: JSON 字段值。

    Returns:
        字符串值；缺失或非法时返回 ``None``。

    Raises:
        无。
    """

    return value if isinstance(value, str) else None


def _optional_role_text(
    payload: Mapping[str, JsonValue],
    field_name: str,
) -> tuple[bool, str | None]:
    """收窄可选 source role 字段。

    Args:
        payload: 单个 file 声明。
        field_name: 待读取字段名。

    Returns:
        二元组第一项表示字段是否合法，第二项为可选 role。

    Raises:
        无。
    """

    if field_name not in payload:
        return True, None
    value = payload[field_name]
    if isinstance(value, str) and value in {
        _FILE_SOURCE_ORIGINAL,
        _FILE_SOURCE_DOCLING,
    }:
        return True, value
    return False, None


def _optional_non_empty_text(
    payload: Mapping[str, JsonValue],
    field_name: str,
) -> tuple[bool, str | None]:
    """收窄可选非空字符串字段。

    Args:
        payload: 单个 file 声明。
        field_name: 待读取字段名。

    Returns:
        二元组第一项表示字段是否合法，第二项为可选文本。

    Raises:
        无。
    """

    if field_name not in payload:
        return True, None
    value = payload[field_name]
    if isinstance(value, str) and value:
        return True, value
    return False, None


def _validate_physical_structure(
    *,
    source_directory: Path,
    declared_files: tuple[_DeclaredSourceFile, ...],
) -> SourceIntegrityReason | None:
    """在计算 missing/digest 前验证 actual tree 无歧义。

    Args:
        source_directory: 当前 source directory。
        declared_files: 已通过结构校验的文件声明。

    Returns:
        unsafe reason；结构可信时返回 ``None``。

    Raises:
        OSError: 目录枚举或 containment operational I/O 失败时抛出 path-free 异常。
    """

    declared_names = {item.inspected.descriptor.name for item in declared_files}
    for child in _list_directory(
        source_directory,
        action="枚举 source integrity document directory",
    ):
        if child.name in {_SOURCE_META_FILENAME, _IDENTITY_DESCRIPTOR_FILENAME}:
            continue
        child_state = _lstat_optional(child, action="检查 source integrity business entry")
        if child_state is None:
            continue
        if not _is_non_symlink_regular_file(child_state):
            return SourceIntegrityReason.UNSAFE_FILESYSTEM_ENTRY
        if child.name not in declared_names:
            return SourceIntegrityReason.UNDECLARED_BUSINESS_FILE
        _require_contained_path(child, source_directory)
    return None


def _classify_role_projection(
    *,
    source_kind: SourceKind,
    provenance: SourceDocumentProvenance,
    persisted_meta: Mapping[str, JsonValue],
    declared_files: tuple[_DeclaredSourceFile, ...],
) -> tuple[SourceIntegrityReason, ...] | None:
    """验证 generic primary 与 user-upload filing 的 original/Docling 关系。

    Args:
        source_kind: filing 或 material。
        provenance: 已验证的 source provenance。
        persisted_meta: 当前 source meta。
        declared_files: 已验证结构的 files 声明。

    Returns:
        repairable projection reasons；关系存在歧义时返回 ``None``。

    Raises:
        无。
    """

    primary = _trusted_primary_document(
        persisted_meta=persisted_meta,
        declared_files=declared_files,
    )
    reasons: list[SourceIntegrityReason] = []
    if primary is None:
        reasons.append(SourceIntegrityReason.PRIMARY_PROJECTION_MISMATCH)
    is_user_upload_filing = (
        source_kind is SourceKind.FILING
        and provenance.ingest_method is FinsIngestMethod.UPLOAD
        and provenance.source_provider is FinsSourceProvider.USER_UPLOAD
    )
    if not is_user_upload_filing:
        return _ordered_reasons(reasons)

    originals = tuple(
        item for item in declared_files if item.source == _FILE_SOURCE_ORIGINAL
    )
    docling_files = tuple(
        item for item in declared_files if item.source == _FILE_SOURCE_DOCLING
    )
    if len(originals) < 1 or len(docling_files) != 1:
        return None
    if len(originals) + len(docling_files) != len(declared_files):
        return None
    if any(
        item.original_filename is None or item.derived_from is not None
        for item in originals
    ):
        return None
    original_names = [item.inspected.descriptor.name for item in originals]
    docling_file = docling_files[0]
    if docling_file.derived_from is None or docling_file.original_filename is None:
        return None
    derived_matches = [
        item
        for item in originals
        if item.inspected.descriptor.name == docling_file.derived_from
    ]
    if len(derived_matches) == 1:
        # storage name 是 authoritative asset identity；basename 只校验该 exact
        # identity 的用户可读投影，不能用来要求不同 authoritative assets 全局唯一。
        if derived_matches[0].original_filename != docling_file.original_filename:
            reasons.append(SourceIntegrityReason.DERIVED_PROJECTION_MISMATCH)
    else:
        filename_matches = [
            item
            for item in originals
            if item.original_filename == docling_file.original_filename
        ]
        # exact derived identity 损坏时，只允许唯一 basename 提供 repairable
        # projection；同 basename 命中多个 assets 仍是无法安全归属的结构歧义。
        if len(filename_matches) != 1:
            return None
        reasons.append(SourceIntegrityReason.DERIVED_PROJECTION_MISMATCH)
    docling_name = docling_file.inspected.descriptor.name
    if primary != docling_name:
        reasons.append(SourceIntegrityReason.PRIMARY_PROJECTION_MISMATCH)
    if docling_file.derived_from not in original_names:
        reasons.append(SourceIntegrityReason.DERIVED_PROJECTION_MISMATCH)
    return _ordered_reasons(reasons)


def _trusted_primary_document(
    *,
    persisted_meta: Mapping[str, JsonValue],
    declared_files: tuple[_DeclaredSourceFile, ...],
) -> str | None:
    """从已验证声明中投影 exact primary document。

    Args:
        persisted_meta: 当前 source meta。
        declared_files: 已验证结构的 files 声明。

    Returns:
        exact 命中的 primary filename；投影不匹配时返回 ``None``。

    Raises:
        无。
    """

    raw_primary = persisted_meta.get("primary_document")
    if not isinstance(raw_primary, str) or not raw_primary:
        return None
    try:
        primary = _normalize_filename(raw_primary)
    except ValueError:
        return None
    names = {item.inspected.descriptor.name for item in declared_files}
    if primary != raw_primary or primary not in names:
        return None
    return primary


def _classify_physical_file_facts(
    declared_files: tuple[_DeclaredSourceFile, ...],
) -> tuple[SourceIntegrityReason, ...]:
    """在结构与 role 无歧义后分类 physical missing/size/digest。

    Args:
        declared_files: 已验证结构与 role 的 files 声明。

    Returns:
        按 enum 顺序去重的 repairable physical reasons。

    Raises:
        OSError: 文件 stat 或摘要读取失败时抛出 path-free 异常。
    """

    reasons: list[SourceIntegrityReason] = []
    for item in declared_files:
        path_state = _lstat_optional(
            item.inspected.physical_path,
            action="检查 source integrity declared file",
        )
        if path_state is None:
            if item.source == _FILE_SOURCE_ORIGINAL:
                reasons.append(SourceIntegrityReason.ORIGINAL_FILE_MISSING)
            elif item.source == _FILE_SOURCE_DOCLING:
                reasons.append(SourceIntegrityReason.PRIMARY_DOCLING_FILE_MISSING)
            else:
                reasons.append(SourceIntegrityReason.DECLARED_FILE_MISSING)
            continue
        descriptor = item.inspected.descriptor
        if descriptor.size is not None and path_state.st_size != descriptor.size:
            reasons.append(SourceIntegrityReason.SIZE_MISMATCH)
        if (
            descriptor.sha256 is not None
            and _hash_regular_file_sha256(item.inspected.physical_path)
            != descriptor.sha256
        ):
            reasons.append(SourceIntegrityReason.DIGEST_MISMATCH)
    return _ordered_reasons(reasons)


def _canonical_manifest_item(
    *,
    source_kind: SourceKind,
    persisted_meta: Mapping[str, JsonValue],
) -> Mapping[str, JsonValue]:
    """只通过 manifest item owner 生成 canonical projection。

    Args:
        source_kind: filing 或 material。
        persisted_meta: 已验证的完整 source meta。

    Returns:
        source-kind owner 生成的 canonical manifest item。

    Raises:
        KeyError: meta 缺少 manifest owner 必需字段时抛出。
        ValueError: manifest owner 拒绝字段值时抛出。
    """

    item = (
        FilingManifestItem.from_source_meta(persisted_meta).to_dict()
        if source_kind is SourceKind.FILING
        else MaterialManifestItem.from_source_meta(persisted_meta).to_dict()
    )
    return cast(Mapping[str, JsonValue], item)


def _inspect_source_manifest(
    *,
    ticker: str,
    source_kind: SourceKind,
    manifest_path: Path,
) -> _ManifestInspection:
    """读取并关闭 source-kind manifest 的结构事实。

    Args:
        ticker: exact canonical ticker。
        source_kind: filing 或 material。
        manifest_path: 当前稳定视图中的 manifest locator。

    Returns:
        missing、trusted 或 untrusted manifest inspection。

    Raises:
        OSError: manifest operational I/O 失败时抛出 path-free 异常。
    """

    manifest_state = _lstat_optional(
        manifest_path,
        action="检查 source integrity manifest",
    )
    if manifest_state is None:
        return _ManifestInspection(exists=False, trusted=True, items={})
    if not _is_non_symlink_regular_file(manifest_state):
        return _ManifestInspection(exists=True, trusted=False, items={})
    try:
        payload = cast(Mapping[str, JsonValue], _read_json_object(manifest_path))
    except (FileNotFoundError, KeyError, TypeError, ValueError):
        return _ManifestInspection(exists=True, trusted=False, items={})
    if payload.get("ticker") != ticker:
        return _ManifestInspection(exists=True, trusted=False, items={})
    raw_documents = payload.get("documents")
    if not isinstance(raw_documents, list):
        return _ManifestInspection(exists=True, trusted=False, items={})
    items: dict[str, Mapping[str, JsonValue]] = {}
    for raw_item in raw_documents:
        if not isinstance(raw_item, Mapping):
            return _ManifestInspection(exists=True, trusted=False, items={})
        raw_document_id = raw_item.get("document_id")
        if not isinstance(raw_document_id, str):
            return _ManifestInspection(exists=True, trusted=False, items={})
        try:
            document_id = _require_external_identity(
                raw_document_id,
                field_name=f"{source_kind.value} manifest document_id",
            )
        except ValueError:
            return _ManifestInspection(exists=True, trusted=False, items={})
        if document_id in items:
            return _ManifestInspection(exists=True, trusted=False, items={})
        items[document_id] = cast(Mapping[str, JsonValue], dict(raw_item))
    return _ManifestInspection(exists=True, trusted=True, items=items)


def _apply_manifest_facts(
    *,
    ticker: str,
    source_kind: SourceKind,
    inventory: tuple[_SourcePublicationInspection, ...],
    manifest: _ManifestInspection,
) -> tuple[tuple[_SourcePublicationInspection, ...], tuple[SourceIntegrityReason, ...]]:
    """把同一次 manifest inspection 机械叠加到 content inventory。

    Args:
        ticker: exact canonical ticker。
        source_kind: filing 或 material。
        inventory: 同一次扫描产生的 source-local inventory。
        manifest: 同一次扫描产生的 manifest fact。

    Returns:
        public classification inventory 与 shared manifest reasons。

    Raises:
        无。
    """

    del ticker, source_kind
    if not manifest.exists:
        if not inventory:
            return inventory, ()
        if _all_content_complete(inventory):
            reason = SourceIntegrityReason.SOURCE_MANIFEST_MISSING
            return (
                tuple(_with_repairable_classification(item, reason) for item in inventory),
                (reason,),
            )
        reason = SourceIntegrityReason.CROSS_SOURCE_INCONSISTENCY
        return (
            tuple(_with_unsafe_classification(item, reason) for item in inventory),
            (SourceIntegrityReason.SOURCE_MANIFEST_MISSING,),
        )
    if not manifest.trusted:
        reason = SourceIntegrityReason.SOURCE_MANIFEST_UNTRUSTED
        return (
            tuple(_with_unsafe_classification(item, reason) for item in inventory),
            (reason,),
        )

    source_ids = {item.classification.document_id for item in inventory}
    manifest_ids = set(manifest.items)
    if manifest_ids - source_ids:
        reason = SourceIntegrityReason.SOURCE_MANIFEST_UNTRUSTED
        return (
            tuple(_with_unsafe_classification(item, reason) for item in inventory),
            (reason,),
        )
    mismatched_ids: set[str] = set(source_ids - manifest_ids)
    for item in inventory:
        document_id = item.classification.document_id
        actual = manifest.items.get(document_id)
        expected = _manifest_projection_for_comparison(item)
        if actual is None:
            continue
        if expected is not None and dict(actual) != dict(expected):
            mismatched_ids.add(document_id)
    if not mismatched_ids:
        return inventory, ()
    if len(mismatched_ids) == 1 and _all_content_complete(inventory):
        mismatch_id = next(iter(mismatched_ids))
        reason = SourceIntegrityReason.SOURCE_MANIFEST_PROJECTION_MISMATCH
        return (
            tuple(
                _with_repairable_classification(item, reason)
                if item.classification.document_id == mismatch_id
                else item
                for item in inventory
            ),
            (),
        )
    reason = SourceIntegrityReason.CROSS_SOURCE_INCONSISTENCY
    return (
        tuple(_with_unsafe_classification(item, reason) for item in inventory),
        (SourceIntegrityReason.SOURCE_MANIFEST_UNTRUSTED,),
    )


def _select_exact_target(
    *,
    ticker: str,
    source_kind: SourceKind,
    requested_document_id: str | None,
    inventory: tuple[_SourcePublicationInspection, ...],
    manifest: _ManifestInspection,
) -> _SourcePublicationInspection | None:
    """从同一次 inventory 中选择 exact target 或构造 missing/unsafe target。

    Args:
        ticker: exact canonical ticker。
        source_kind: filing 或 material。
        requested_document_id: exact target；whole-kind mode 为 ``None``。
        inventory: 已叠加 manifest facts 的 inventory。
        manifest: 同一次 manifest fact。

    Returns:
        exact mode 的非空 target；whole-kind mode 返回 ``None``。

    Raises:
        无。
    """

    if requested_document_id is None:
        return None
    for item in inventory:
        if item.classification.document_id == requested_document_id:
            return item
    if manifest.trusted and requested_document_id not in manifest.items:
        return _missing_source_inspection(
            ticker=ticker,
            source_kind=source_kind,
            document_id=requested_document_id,
        )
    return _unsafe_source_inspection(
        ticker=ticker,
        source_kind=source_kind,
        document_id=requested_document_id,
        reason=SourceIntegrityReason.SOURCE_MANIFEST_UNTRUSTED,
    )


def _canonical_manifest_items(
    inventory: tuple[_SourcePublicationInspection, ...],
) -> tuple[Mapping[str, JsonValue], ...]:
    """聚合同一次 scan 中全部 complete content 的 canonical manifest items。

    Args:
        inventory: source-local/public inspection inventory。

    Returns:
        全部 content complete 时按 document ID 排序的 canonical items；否则为空。

    Raises:
        无。
    """

    if not _all_content_complete(inventory):
        return ()
    items: list[Mapping[str, JsonValue]] = []
    for inspection in inventory:
        item = inspection.canonical_manifest_item
        if item is None:
            return ()
        items.append(item)
    return tuple(items)


def _manifest_projection_for_comparison(
    inspection: _SourcePublicationInspection,
) -> Mapping[str, JsonValue] | None:
    """为现有 manifest equality 生成 source-local canonical projection。

    该临时比较值仍只由 ManifestItem owner 产生，但不会写入
    ``canonical_manifest_item``；后者按冻结契约仅在 content complete 时可用。

    Args:
        inspection: 同一次 scan 的 source-local inspection。

    Returns:
        trusted persisted meta 可投影时返回 canonical item，否则返回 ``None``。

    Raises:
        无。
    """

    if inspection.persisted_meta is None:
        return None
    try:
        return _canonical_manifest_item(
            source_kind=inspection.classification.source_kind,
            persisted_meta=inspection.persisted_meta,
        )
    except (KeyError, TypeError, ValueError):
        return None


def _derive_repair_blocked_reason(
    *,
    target: _SourcePublicationInspection | None,
    inventory: tuple[_SourcePublicationInspection, ...],
    canonical_manifest_items: tuple[Mapping[str, JsonValue], ...],
    unassignable_root_fact: bool,
) -> SourceIntegrityRepairBlockedReason | None:
    """从同一 inspection payload 派生 staged repair 阻断原因。

    Args:
        target: exact target；whole-kind mode 为 ``None``。
        inventory: 同一次 scan 的完整 inventory。
        canonical_manifest_items: 同一次 scan 的 canonical aggregate。
        unassignable_root_fact: 是否存在无法归属的 root structural fact。

    Returns:
        封闭 repair blocked reason；没有阻断时返回 ``None``。

    Raises:
        无。
    """

    if unassignable_root_fact or any(
        item.classification.status is SourceIntegrityStatus.UNSAFE
        for item in inventory
    ):
        return SourceIntegrityRepairBlockedReason.CROSS_SOURCE_PUBLICATION_UNSAFE
    if target is None:
        if inventory and not canonical_manifest_items:
            return SourceIntegrityRepairBlockedReason.CANONICAL_MANIFEST_UNAVAILABLE
        return None
    target_id = None if target is None else target.classification.document_id
    if any(
        item.classification.document_id != target_id
        and item.content_classification.status is not SourceIntegrityStatus.COMPLETE
        for item in inventory
    ):
        return SourceIntegrityRepairBlockedReason.NON_TARGET_SOURCE_INCOMPLETE
    if (
        target is not None
        and target.content_classification.status
        is SourceIntegrityStatus.REPAIR_REQUIRED
    ):
        return None
    if inventory and not canonical_manifest_items:
        return SourceIntegrityRepairBlockedReason.CANONICAL_MANIFEST_UNAVAILABLE
    return None


def _with_repairable_classification(
    inspection: _SourcePublicationInspection,
    reason: SourceIntegrityReason,
) -> _SourcePublicationInspection:
    """为 trusted source 叠加一个 repairable public reason。

    Args:
        inspection: 当前 source inspection。
        reason: 待叠加的 repairable reason。

    Returns:
        保留 source-local facts 的新 inspection。

    Raises:
        ValueError: source-local classification 不是 complete/repairable 时抛出。
    """

    if inspection.revision is None or inspection.classification.status is SourceIntegrityStatus.UNSAFE:
        raise ValueError("unsafe source 不得叠加 repairable classification")
    reasons = _ordered_reasons((*inspection.classification.reasons, reason))
    classification = SourceIntegrityClassification(
        ticker=inspection.classification.ticker,
        source_kind=inspection.classification.source_kind,
        document_id=inspection.classification.document_id,
        revision=inspection.revision,
        status=SourceIntegrityStatus.REPAIR_REQUIRED,
        reasons=reasons,
    )
    return replace(inspection, classification=classification)


def _with_unsafe_classification(
    inspection: _SourcePublicationInspection,
    reason: SourceIntegrityReason,
) -> _SourcePublicationInspection:
    """把 source public classification 收敛为 unsafe。

    Args:
        inspection: 当前 source inspection。
        reason: 待叠加的 unsafe reason。

    Returns:
        保留可信私有 content facts但不再公开 revision 的新 inspection。

    Raises:
        无。
    """

    existing_unsafe_reasons = (
        inspection.classification.reasons
        if inspection.classification.status is SourceIntegrityStatus.UNSAFE
        else ()
    )
    reasons = _ordered_reasons((*existing_unsafe_reasons, reason))
    classification = SourceIntegrityClassification(
        ticker=inspection.classification.ticker,
        source_kind=inspection.classification.source_kind,
        document_id=inspection.classification.document_id,
        revision=None,
        status=SourceIntegrityStatus.UNSAFE,
        reasons=reasons,
    )
    return replace(inspection, classification=classification)


def _missing_source_inspection(
    *,
    ticker: str,
    source_kind: SourceKind,
    document_id: str,
) -> _SourcePublicationInspection:
    """构造 exact target 完全不存在的 inspection。

    Args:
        ticker: exact canonical ticker。
        source_kind: filing 或 material。
        document_id: exact canonical document ID。

    Returns:
        ``MISSING`` source inspection。

    Raises:
        无。
    """

    classification = SourceIntegrityClassification(
        ticker=ticker,
        source_kind=source_kind,
        document_id=document_id,
        revision=None,
        status=SourceIntegrityStatus.MISSING,
        reasons=(),
    )
    return _SourcePublicationInspection(
        classification=classification,
        content_classification=classification,
        persisted_meta=None,
        business_meta=None,
        provenance=None,
        revision=None,
        files=(),
        primary_document=None,
        canonical_manifest_item=None,
    )


def _unsafe_source_inspection(
    *,
    ticker: str,
    source_kind: SourceKind,
    document_id: str,
    reason: SourceIntegrityReason,
) -> _SourcePublicationInspection:
    """构造无法承诺任何 trusted source facts 的 unsafe inspection。

    Args:
        ticker: exact canonical ticker。
        source_kind: filing 或 material。
        document_id: exact canonical document ID。
        reason: source-local unsafe reason。

    Returns:
        ``UNSAFE/revision=None`` source inspection。

    Raises:
        无。
    """

    classification = SourceIntegrityClassification(
        ticker=ticker,
        source_kind=source_kind,
        document_id=document_id,
        revision=None,
        status=SourceIntegrityStatus.UNSAFE,
        reasons=(reason,),
    )
    return _SourcePublicationInspection(
        classification=classification,
        content_classification=classification,
        persisted_meta=None,
        business_meta=None,
        provenance=None,
        revision=None,
        files=(),
        primary_document=None,
        canonical_manifest_item=None,
    )


def _all_content_complete(
    inventory: tuple[_SourcePublicationInspection, ...],
) -> bool:
    """判断 inventory 的每个 source-local content 是否 complete。

    Args:
        inventory: 同一次 scan 的 source inventory。

    Returns:
        全部 content complete 时返回 ``True``。

    Raises:
        无。
    """

    return all(
        item.content_classification.status is SourceIntegrityStatus.COMPLETE
        for item in inventory
    )


def _ordered_reasons(
    reasons: tuple[SourceIntegrityReason, ...] | list[SourceIntegrityReason],
) -> tuple[SourceIntegrityReason, ...]:
    """按 public enum 顺序稳定去重 reasons。

    Args:
        reasons: 待规范化的 reasons。

    Returns:
        按 enum 顺序去重的 reasons tuple。

    Raises:
        无。
    """

    selected = set(reasons)
    return tuple(reason for reason in SourceIntegrityReason if reason in selected)


def _source_revision_from_meta(
    meta: Mapping[str, JsonValue],
) -> SourceDocumentRevision:
    """从 persisted meta 机械读取 opaque source revision。

    Args:
        meta: storage owner 已读取的 persisted source meta。

    Returns:
        只承诺 equality 的 typed revision。

    Raises:
        KeyError: revision 字段缺失时抛出。
        ValueError: revision 不是非空字符串时抛出。
    """

    raw_revision = meta[_SOURCE_REVISION_META_FIELD]
    if not isinstance(raw_revision, str) or not raw_revision:
        raise ValueError("persisted source revision 必须为非空字符串")
    return SourceDocumentRevision(token=raw_revision)


def _source_meta_without_revision(
    meta: Mapping[str, JsonValue],
) -> dict[str, JsonValue]:
    """投影不含 storage 私有 revision 的业务 meta。

    Args:
        meta: persisted source meta。

    Returns:
        独立的 business meta mapping。

    Raises:
        无。
    """

    return {
        field_name: field_value
        for field_name, field_value in meta.items()
        if field_name != _SOURCE_REVISION_META_FIELD
    }


def _manifest_filename(source_kind: SourceKind) -> str:
    """返回 source-kind manifest 文件名。

    Args:
        source_kind: filing 或 material。

    Returns:
        对应的固定 manifest 文件名。

    Raises:
        ValueError: source kind 非法时抛出。
    """

    if source_kind is SourceKind.FILING:
        return _FILING_MANIFEST_FILENAME
    if source_kind is SourceKind.MATERIAL:
        return _MATERIAL_MANIFEST_FILENAME
    raise ValueError("source_kind 必须是 filing 或 material")


def _is_allowed_filing_control(name: str, source_kind: SourceKind) -> bool:
    """判断 source root 条目是否为 filing 专属治理文件。

    Args:
        name: source root 直属条目名。
        source_kind: filing 或 material。

    Returns:
        filing download rejection 治理条目返回 ``True``。

    Raises:
        无。
    """

    return source_kind is SourceKind.FILING and name in {
        _DOWNLOAD_REJECTIONS_FILENAME,
        _REJECTED_FILINGS_DIRNAME,
    }


def _lstat_optional(path: Path, *, action: str) -> os.stat_result | None:
    """读取 locator 自身状态并投影 operational filesystem error。

    Args:
        path: 待检查 locator。
        action: 不含路径的业务动作说明。

    Returns:
        locator 状态；不存在时返回 ``None``。

    Raises:
        OSError: 非 missing operational I/O 失败时抛出 path-free 异常。
    """

    try:
        return path.lstat()
    except FileNotFoundError:
        return None
    except OSError as exc:
        _raise_path_free_error(_project_filesystem_error(exc, action=action))


def _is_non_symlink_directory(path_state: os.stat_result) -> bool:
    """判断 lstat 结果是否为 physical directory。

    Args:
        path_state: locator 的 lstat 结果。

    Returns:
        非 symlink directory 返回 ``True``。

    Raises:
        无。
    """

    return stat.S_ISDIR(path_state.st_mode)


def _is_non_symlink_regular_file(path_state: os.stat_result) -> bool:
    """判断 lstat 结果是否为 physical regular file。

    Args:
        path_state: locator 的 lstat 结果。

    Returns:
        非 symlink regular file 返回 ``True``。

    Raises:
        无。
    """

    return stat.S_ISREG(path_state.st_mode)


def _require_contained_path(path: Path, root: Path) -> None:
    """要求 physical business path 仍位于 source directory 内。

    Args:
        path: 待验证 physical path。
        root: 已验证的 source directory。

    Returns:
        无。

    Raises:
        ValueError: path containment escape 时抛出 path-free 异常。
        OSError: path resolve operational I/O 失败时抛出 path-free 异常。
    """

    try:
        resolved_root = root.resolve(strict=False)
        resolved_path = path.resolve(strict=False)
        resolved_path.relative_to(resolved_root)
    except ValueError:
        _raise_path_free_error(ValueError("source business file 越出 source directory"))
    except OSError as exc:
        _raise_path_free_error(
            _project_filesystem_error(exc, action="校验 source integrity containment")
        )


def _hash_regular_file_sha256(path: Path) -> str:
    """流式计算已验证 regular file 的 SHA-256。

    Args:
        path: 已通过 physical structure 校验的文件。

    Returns:
        64 位小写 SHA-256。

    Raises:
        OSError: 文件打开或读取失败时抛出 path-free 异常。
    """

    digest = hashlib.sha256()
    try:
        with _open_binary_file(path, action="打开 source integrity business file") as stream:
            while chunk := stream.read(_HASH_CHUNK_SIZE):
                digest.update(chunk)
    except OSError as exc:
        _raise_path_free_error(
            _project_filesystem_error(exc, action="读取 source integrity business file")
        )
    return digest.hexdigest()


def _require_complete_source_for_snapshot_unguarded(
    inspection: _SourcePublicationInspection,
) -> _SourcePublicationInspection:
    """要求同一次 inspection 中的 exact source 可被 snapshot 消费。

    Args:
        inspection: exact-target mode 返回的单 source inspection。

    Returns:
        原样返回已证明为 ``COMPLETE`` 的 inspection payload。

    Raises:
        FileNotFoundError: exact source 为 ``MISSING`` 时抛出。
        ValueError: exact source 为 ``REPAIR_REQUIRED`` 或 ``UNSAFE``，或 complete
            payload 缺少 snapshot 必需可信事实时抛出。
    """

    classification = inspection.classification
    if classification.status is SourceIntegrityStatus.MISSING:
        raise FileNotFoundError("source snapshot 目标不存在")
    if classification.status is not SourceIntegrityStatus.COMPLETE:
        raise ValueError("source snapshot 只允许读取 COMPLETE source")
    if (
        inspection.content_classification.status is not SourceIntegrityStatus.COMPLETE
        or inspection.persisted_meta is None
        or inspection.business_meta is None
        or inspection.provenance is None
        or inspection.revision is None
        or not inspection.files
        or inspection.primary_document is None
        or inspection.canonical_manifest_item is None
    ):
        raise ValueError("COMPLETE source inspection 缺少 snapshot 必需事实")
    return inspection


__all__ = [
    "_InspectedSourceFile",
    "_SourceKindPublicationInspection",
    "_SourcePublicationInspection",
    "_inspect_source_kind_unguarded",
    "_require_complete_source_for_snapshot_unguarded",
]
