"""文件系统仓储 identity 到物理 locator 的唯一映射。

ticker 使用业务 owner 已产生的 canonical 值作为可读 locator；document identity
使用 filesystem-safe private locator。两类 locator 共用 descriptor 原子持久化与
双向校验，document private locator 的格式不属于公共契约。
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Final, Literal, TypeAlias

from dayu.fins.ticker_normalization import normalize_ticker

from ._fs_storage_utils import (
    _list_directory,
    _project_filesystem_error,
    _raise_path_free_error,
    _read_json_object,
    _write_json,
)


_IdentityNamespace: TypeAlias = Literal[
    "ticker",
    "filing_document",
    "material_document",
    "processed_document",
    "rejected_filing_document",
]

_TICKER_IDENTITY_NAMESPACE: Final[_IdentityNamespace] = "ticker"
_FILING_IDENTITY_NAMESPACE: Final[_IdentityNamespace] = "filing_document"
_MATERIAL_IDENTITY_NAMESPACE: Final[_IdentityNamespace] = "material_document"
_PROCESSED_IDENTITY_NAMESPACE: Final[_IdentityNamespace] = "processed_document"
_REJECTED_FILING_IDENTITY_NAMESPACE: Final[_IdentityNamespace] = (
    "rejected_filing_document"
)
_IDENTITY_DESCRIPTOR_FILENAME: Final[str] = ".identity.json"
_IDENTITY_DESCRIPTOR_FIELDS: Final[frozenset[str]] = frozenset(
    {"namespace", "external_identity"}
)
_PRIVATE_KEY_PREFIX: Final[str] = "id-"


def _require_external_identity(value: str, *, field_name: str) -> str:
    """校验并原样返回 external identity。

    Args:
        value: caller/domain 产生的业务 identity。
        field_name: 错误信息使用的字段名。

    Returns:
        未做 strip、大小写或 Unicode 归一化的原始 identity。

    Raises:
        ValueError: identity 为空或不能编码为 UTF-8 时抛出。
    """

    if value == "":
        raise ValueError(f"{field_name} 不能为空")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError(f"{field_name} 必须可编码为 UTF-8") from exc
    return value


def _require_canonical_ticker_identity(value: str, *, field_name: str) -> str:
    """校验并返回 canonical ticker identity。

    ticker 的业务归一化由 ``dayu.fins.ticker_normalization`` 唯一拥有；storage
    只验证调用方已经传入 canonical 值，不在 mutation/read 边界静默改写 identity。

    Args:
        value: 调用方传入的 ticker identity。
        field_name: 错误信息使用的字段名。

    Returns:
        与 ticker normalization 真源完全一致的 canonical ticker。

    Raises:
        ValueError: ticker 为空、无法识别或不是 canonical 形态时抛出。
    """

    identity = _require_external_identity(value, field_name=field_name)
    try:
        normalized = normalize_ticker(identity)
    except ValueError as exc:
        raise ValueError(f"{field_name} 必须是可识别的 canonical ticker") from exc
    if normalized.canonical != identity:
        raise ValueError(f"{field_name} 必须使用 canonical ticker")
    return identity


def _derive_storage_key(namespace: _IdentityNamespace, external_identity: str) -> str:
    """为指定 namespace 派生 storage locator key。

    Args:
        namespace: storage 私有 identity namespace。
        external_identity: 已由 identity owner 校验的原始业务 identity。

    Returns:
        ticker namespace 返回 canonical ticker；document namespace 返回只供 storage
        locator 使用的确定性 private key。

    Raises:
        ValueError: external identity 非法时抛出。
    """

    if namespace == _TICKER_IDENTITY_NAMESPACE:
        return _require_canonical_ticker_identity(
            external_identity,
            field_name="ticker identity",
        )
    identity = _require_external_identity(external_identity, field_name="external identity")
    digest = hashlib.sha256()
    digest.update(namespace.encode("utf-8"))
    digest.update(b"\0")
    digest.update(identity.encode("utf-8"))
    return f"{_PRIVATE_KEY_PREFIX}{digest.hexdigest()}"


def _identity_directory_path(
    root: Path,
    namespace: _IdentityNamespace,
    external_identity: str,
) -> Path:
    """返回 external identity 对应的 directory locator。

    Args:
        root: 当前 namespace 的固定 storage root。
        namespace: storage 私有 identity namespace。
        external_identity: 原始业务 identity。

    Returns:
        root 下的 directory path。

    Raises:
        ValueError: external identity 非法时抛出。
    """

    return root / _derive_storage_key(namespace, external_identity)


def _identity_descriptor_path(directory: Path) -> Path:
    """返回 identity directory 的 descriptor 路径。

    Args:
        directory: private identity directory。

    Returns:
        descriptor 文件路径。

    Raises:
        无。
    """

    return directory / _IDENTITY_DESCRIPTOR_FILENAME


def _ensure_identity_directory(
    root: Path,
    namespace: _IdentityNamespace,
    external_identity: str,
) -> Path:
    """创建或幂等验证 identity directory 及 descriptor。

    descriptor 必须先于该目录内的业务 payload 写入。已存在目录只允许与当前
    namespace/external identity 精确一致，不允许以缺失 descriptor 作为旧布局回退。

    Args:
        root: 当前 namespace 的固定 storage root。
        namespace: storage 私有 identity namespace。
        external_identity: 原始业务 identity。

    Returns:
        已创建并校验的 identity directory。

    Raises:
        ValueError: locator、descriptor 或双向映射不一致时抛出。
        OSError: 目录或 descriptor 创建失败时抛出。
    """

    identity = _require_external_identity(
        external_identity,
        field_name="external identity",
    )
    try:
        if root.is_symlink():
            raise ValueError("identity namespace root 禁止 symlink")
        root.mkdir(parents=True, exist_ok=True)
        directory = _identity_directory_path(root, namespace, identity)
        if directory.exists() or directory.is_symlink():
            _read_identity_descriptor(
                directory,
                namespace,
                expected_external_identity=identity,
            )
            return directory
        directory.mkdir(parents=True)
    except OSError as exc:
        _raise_path_free_error(
            _project_filesystem_error(exc, action="准备 identity directory")
        )
    try:
        _write_json(
            _identity_descriptor_path(directory),
            {
                "namespace": namespace,
                "external_identity": identity,
            },
        )
    except Exception:
        # descriptor 是目录可见性的先决条件；失败时只清理由本调用创建的空目录。
        try:
            directory.rmdir()
        except OSError:
            pass
        raise
    _read_identity_descriptor(
        directory,
        namespace,
        expected_external_identity=identity,
    )
    return directory


def _read_identity_descriptor(
    directory: Path,
    namespace: _IdentityNamespace,
    *,
    expected_external_identity: str | None = None,
    expected_storage_key: str | None = None,
) -> str:
    """读取并双向校验 identity directory 的 identity descriptor。

    Args:
        directory: identity directory。
        namespace: 预期 storage namespace。
        expected_external_identity: lookup 已知的 external identity；枚举时为 ``None``。
        expected_storage_key: directory 名含 transaction 后缀时由 locator owner 传入的
            原始 locator key；普通 identity directory 为 ``None``。

    Returns:
        descriptor 中经校验的 exact external identity。

    Raises:
        FileNotFoundError: directory 或 descriptor 不存在时抛出。
        ValueError: directory、descriptor、namespace、identity 或派生 key 不一致时抛出。
        OSError: 文件系统读取失败时抛出。
    """

    try:
        if not directory.exists():
            raise FileNotFoundError("identity directory 不存在")
        if directory.is_symlink() or not directory.is_dir():
            raise ValueError("identity directory 必须为 non-symlink directory")
        descriptor_path = _identity_descriptor_path(directory)
        if descriptor_path.is_symlink() or not descriptor_path.is_file():
            raise ValueError("identity descriptor 必须为 non-symlink regular file")
    except OSError as exc:
        _raise_path_free_error(
            _project_filesystem_error(exc, action="校验 identity descriptor locator")
        )
    payload = _read_json_object(descriptor_path)
    if frozenset(payload) != _IDENTITY_DESCRIPTOR_FIELDS:
        raise ValueError("identity descriptor 字段不合法")
    raw_namespace = payload["namespace"]
    raw_external_identity = payload["external_identity"]
    if raw_namespace != namespace or not isinstance(raw_external_identity, str):
        raise ValueError("identity descriptor namespace 或 external identity 不合法")
    identity = _require_external_identity(
        raw_external_identity,
        field_name="descriptor external identity",
    )
    if expected_external_identity is not None and identity != expected_external_identity:
        raise ValueError("identity descriptor 与请求 external identity 不一致")
    storage_key = directory.name if expected_storage_key is None else expected_storage_key
    if storage_key != _derive_storage_key(namespace, identity):
        raise ValueError("identity descriptor 与 private locator 不一致")
    return identity


def _identity_directory_for_read(
    root: Path,
    namespace: _IdentityNamespace,
    external_identity: str,
) -> Path:
    """返回 lookup locator，并在目录存在时强制 descriptor 校验。

    Args:
        root: 当前 namespace 的固定 storage root。
        namespace: storage 私有 identity namespace。
        external_identity: 原始业务 identity。

    Returns:
        对应 identity directory；目录不存在时仍返回确定性 locator。

    Raises:
        ValueError: external identity、目录或 descriptor 不合法时抛出。
        OSError: descriptor 读取失败时抛出。
    """

    identity = _require_external_identity(
        external_identity,
        field_name="external identity",
    )
    try:
        if root.is_symlink():
            raise ValueError("identity namespace root 禁止 symlink")
        if root.exists() and not root.is_dir():
            raise ValueError("identity namespace root 必须为 directory")
        directory = _identity_directory_path(root, namespace, identity)
        if directory.exists() or directory.is_symlink():
            _read_identity_descriptor(
                directory,
                namespace,
                expected_external_identity=identity,
            )
    except OSError as exc:
        _raise_path_free_error(
            _project_filesystem_error(exc, action="查找 identity directory")
        )
    return directory


def _identity_directory_if_present_for_read(
    root: Path,
    namespace: _IdentityNamespace,
    external_identity: str,
) -> Path | None:
    """返回已存在且通过 descriptor 校验的 identity directory。

    Args:
        root: 当前 namespace 的固定 storage root。
        namespace: storage 私有 identity namespace。
        external_identity: 原始业务 identity。

    Returns:
        identity directory 存在且合法时返回 canonical locator；namespace 或
        identity directory 不存在时返回 ``None``。

    Raises:
        ValueError: external identity、目录或 descriptor 不合法时抛出。
        OSError: locator 或 descriptor 读取失败时抛出。
    """

    directory = _identity_directory_for_read(root, namespace, external_identity)
    try:
        if directory.exists() or directory.is_symlink():
            return directory
    except OSError as exc:
        _raise_path_free_error(
            _project_filesystem_error(exc, action="检查 identity directory 是否存在")
        )
    return None


def _list_external_identities(
    root: Path,
    namespace: _IdentityNamespace,
) -> list[str]:
    """从 descriptor 枚举 namespace 下的 external identities。

    非目录业务文件会被忽略；非隐藏 symlink、损坏 descriptor、碰撞或重复
    external identity 一律 fail closed，不从目录名反推业务值。

    Args:
        root: 当前 namespace 的固定 storage root。
        namespace: storage 私有 identity namespace。

    Returns:
        按 exact external identity 排序的列表。

    Raises:
        ValueError: directory/descriptor 不合法或 external identity 重复时抛出。
        OSError: 目录或 descriptor 读取失败时抛出。
    """

    try:
        if not root.exists():
            return []
        if root.is_symlink() or not root.is_dir():
            raise ValueError("identity namespace root 必须为 non-symlink directory")
        identities: list[str] = []
        for child in _list_directory(root, action="枚举 identity namespace"):
            if child.name.startswith("."):
                continue
            if child.is_symlink():
                raise ValueError("identity namespace 禁止 symlink directory entry")
            if not child.is_dir():
                continue
            identity = _read_identity_descriptor(child, namespace)
            if identity in identities:
                raise ValueError("identity namespace 存在重复 external identity")
            identities.append(identity)
    except OSError as exc:
        _raise_path_free_error(
            _project_filesystem_error(exc, action="枚举 identity namespace")
        )
    return sorted(identities)
