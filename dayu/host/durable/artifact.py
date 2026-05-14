"""Host durable 本地 artifact 写入 helper。

本模块只负责把 bytes 写入调用方显式注入的 artifact root，并在返回
``LocalArtifactRef`` 前完成 flush / fsync、digest 校验、atomic rename 与最终
路径 containment 校验。它不写 SQLite descriptor、不清理 orphan，也不读取环境
变量或当前工作目录作为隐式根目录。
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from dayu.host.durable.codec import is_sha256_digest, sha256_digest_bytes
from dayu.host.durable.errors import (
    HostArtifactWriteError,
    HostDigestMismatchError,
    HostDurableError,
)

_ARTIFACT_DIGEST_PREFIX = "sha256:"
_ARTIFACT_NAMESPACE = "sha256"
_ARTIFACT_TEMP_DIR_NAME = ".tmp"
_DIGEST_SHARD_LENGTH = 2
_NULL_BYTE = "\x00"


@dataclass(frozen=True, slots=True)
class LocalArtifactRef:
    """已发布本地 artifact 引用。

    :param artifact_relative_path: artifact root 下的最终相对路径。
    :param artifact_digest: artifact 内容 digest。
    :param artifact_size_bytes: artifact 字节长度。
    """

    artifact_relative_path: str
    artifact_digest: str
    artifact_size_bytes: int


class LocalArtifactStore:
    """本地 artifact 写入 helper。

    :param artifact_root: 调用方显式注入的 artifact 根目录。
    :param create_artifact_root: 根目录缺失时是否创建。
    """

    def __init__(self, artifact_root: Path, *, create_artifact_root: bool = True) -> None:
        """初始化本地 artifact store。

        :param artifact_root: 调用方显式注入的 artifact 根目录。
        :param create_artifact_root: 根目录缺失时是否创建。
        :returns: ``None``。
        :raises HostArtifactWriteError: 根目录不可用时抛出。
        """

        self._artifact_root = artifact_root
        self._create_artifact_root = create_artifact_root
        _prepare_artifact_root(
            self._artifact_root, create=self._create_artifact_root
        )

    @property
    def artifact_root(self) -> Path:
        """返回注入的 artifact 根目录。

        :returns: artifact 根目录。
        """

        return self._artifact_root

    def write_artifact_bytes(
        self, content: bytes, *, expected_digest: str | None = None
    ) -> LocalArtifactRef:
        """写入 bytes artifact 并返回最终引用。

        :param content: 待写入的 artifact bytes。
        :param expected_digest: 调用方预期 digest；无预期时为 ``None``。
        :returns: 已发布且校验过 digest 的本地 artifact 引用。
        :raises HostDigestMismatchError: 预期 digest 与实际 digest 不一致时抛出。
        :raises HostArtifactWriteError: 写入、fsync、路径 containment 或发布失败时抛出。
        """

        actual_digest = sha256_digest_bytes(content)
        _validate_expected_digest(actual_digest, expected_digest)
        relative_path = _artifact_relative_path_for_digest(actual_digest)
        final_path = _contained_final_path(self._artifact_root, relative_path)
        temp_path = _write_temp_file_under_root(self._artifact_root, content)
        try:
            temp_digest = _read_file_digest(temp_path)
            if temp_digest != actual_digest:
                raise HostDigestMismatchError("Artifact temp digest mismatch")
            final_path.parent.mkdir(parents=True, exist_ok=True)
            _ensure_contained(self._artifact_root, final_path.parent)
            os.replace(temp_path, final_path)
            _fsync_directory(final_path.parent)
            final_digest = _read_file_digest(final_path)
            if final_digest != actual_digest:
                raise HostDigestMismatchError("Artifact final digest mismatch")
            artifact_ref = LocalArtifactRef(
                artifact_relative_path=relative_path,
                artifact_digest=actual_digest,
                artifact_size_bytes=len(content),
            )
            validate_artifact_ref(artifact_ref)
            return artifact_ref
        except (HostDigestMismatchError, HostArtifactWriteError):
            _unlink_if_exists(temp_path)
            raise
        except OSError as exc:
            _unlink_if_exists(temp_path)
            raise HostArtifactWriteError("Artifact publish failed") from exc


def validate_artifact_ref(artifact_ref: LocalArtifactRef) -> None:
    """校验本地 artifact ref 只包含可接受的最终相对路径与 digest。

    :param artifact_ref: 待校验 artifact 引用。
    :returns: ``None``。
    :raises HostDurableError: 引用字段无效时抛出。
    """

    _validate_relative_path_text(artifact_ref.artifact_relative_path)
    if _is_temp_relative_path(artifact_ref.artifact_relative_path):
        raise HostDurableError("Artifact ref must not point to temp path")
    if not is_sha256_digest(artifact_ref.artifact_digest):
        raise HostDurableError("Artifact digest must be sha256 digest")
    if artifact_ref.artifact_size_bytes < 0:
        raise HostDurableError("Artifact size must be non-negative")


def _artifact_relative_path_for_digest(digest: str) -> str:
    """根据 digest 生成稳定 artifact 相对路径。

    :param digest: Host durable sha256 digest。
    :returns: artifact root 下的相对路径。
    :raises HostArtifactWriteError: digest 格式无效时抛出。
    """

    if not digest.startswith(_ARTIFACT_DIGEST_PREFIX):
        raise HostArtifactWriteError("Artifact digest has invalid prefix")
    digest_hex = digest.removeprefix(_ARTIFACT_DIGEST_PREFIX)
    shard = digest_hex[:_DIGEST_SHARD_LENGTH]
    return f"{_ARTIFACT_NAMESPACE}/{shard}/{digest_hex}"


def _validate_expected_digest(actual_digest: str, expected_digest: str | None) -> None:
    """校验调用方预期 digest。

    :param actual_digest: 实际 digest。
    :param expected_digest: 预期 digest；无预期时为 ``None``。
    :returns: ``None``。
    :raises HostDigestMismatchError: 预期 digest 与实际 digest 不一致时抛出。
    :raises HostArtifactWriteError: 预期 digest 格式无效时抛出。
    """

    if expected_digest is None:
        return
    if not is_sha256_digest(expected_digest):
        raise HostArtifactWriteError("Artifact expected_digest must be sha256 digest")
    if expected_digest != actual_digest:
        raise HostDigestMismatchError("Artifact digest does not match expected digest")


def _validate_relative_path_text(relative_path: str) -> None:
    """校验 artifact 相对路径文本。

    :param relative_path: 待校验的相对路径文本。
    :returns: ``None``。
    :raises HostDurableError: 路径为空、绝对、含空字节或目录穿越时抛出。
    """

    if relative_path == "" or relative_path.isspace():
        raise HostDurableError("Artifact relative path must be non-empty")
    if _NULL_BYTE in relative_path:
        raise HostDurableError("Artifact relative path must not contain null byte")
    path = PurePosixPath(relative_path)
    if path.is_absolute():
        raise HostDurableError("Artifact relative path must not be absolute")
    if any(part in ("", ".", "..") for part in path.parts):
        raise HostDurableError("Artifact relative path must not traverse")


def _is_temp_relative_path(relative_path: str) -> bool:
    """判断相对路径是否指向 artifact temp 区域。

    :param relative_path: artifact 相对路径。
    :returns: 指向 ``.tmp`` 时返回 ``True``。
    """

    path = PurePosixPath(relative_path)
    return len(path.parts) > 0 and path.parts[0] == _ARTIFACT_TEMP_DIR_NAME


def _read_file_digest(path: Path) -> str:
    """读取文件并计算 digest。

    :param path: 文件路径。
    :returns: Host durable sha256 digest。
    :raises HostArtifactWriteError: 文件读取失败时抛出。
    """

    try:
        return sha256_digest_bytes(path.read_bytes())
    except OSError as exc:
        raise HostArtifactWriteError("Artifact digest read failed") from exc


def _unlink_if_exists(path: Path) -> None:
    """尽力删除临时文件。

    :param path: 临时文件路径。
    :returns: ``None``。
    """

    try:
        path.unlink(missing_ok=True)
    except OSError:
        return


def _fsync_directory(path: Path) -> None:
    """对目录执行 fsync。

    :param path: 目录路径。
    :returns: ``None``。
    :raises HostArtifactWriteError: 目录 fsync 失败时抛出。
    """

    try:
        directory_fd = os.open(path, os.O_RDONLY)
    except OSError as exc:
        raise HostArtifactWriteError("Artifact directory open failed") from exc
    try:
        os.fsync(directory_fd)
    except OSError as exc:
        raise HostArtifactWriteError("Artifact directory fsync failed") from exc
    finally:
        os.close(directory_fd)


def _ensure_contained(root: Path, candidate: Path) -> None:
    """校验候选路径解析后仍位于 artifact root 内。

    :param root: artifact 根目录。
    :param candidate: 候选路径。
    :returns: ``None``。
    :raises HostArtifactWriteError: 候选路径逃逸根目录时抛出。
    """

    try:
        resolved_root = root.resolve(strict=True)
        resolved_candidate = candidate.resolve(strict=True)
        resolved_candidate.relative_to(resolved_root)
    except (OSError, ValueError) as exc:
        raise HostArtifactWriteError("Artifact path escapes artifact root") from exc


def _ensure_parent_dir_contained(root: Path, relative_path: str) -> None:
    """在创建目录前校验既有祖先目录不会通过 symlink 逃逸。

    :param root: artifact 根目录。
    :param relative_path: 最终 artifact 相对路径。
    :returns: ``None``。
    :raises HostArtifactWriteError: 已存在祖先路径逃逸根目录时抛出。
    """

    _validate_relative_path_text(relative_path)
    parts = PurePosixPath(relative_path).parts[:-1]
    current = root
    for part in parts:
        current = current / part
        if current.exists():
            _ensure_contained(root, current)


def _write_temp_file(content: bytes, temp_dir: Path) -> Path:
    """把内容写入 temp 文件并完成文件 fsync。

    :param content: artifact bytes。
    :param temp_dir: artifact root 下的 temp 目录。
    :returns: temp 文件路径。
    :raises HostArtifactWriteError: temp 文件创建、写入或 fsync 失败时抛出。
    """

    temp_path: Path | None = None
    try:
        temp_fd, temp_name = tempfile.mkstemp(
            prefix="artifact-", suffix=".tmp", dir=temp_dir
        )
        temp_path = Path(temp_name)
        with os.fdopen(temp_fd, "wb") as file:
            file.write(content)
            file.flush()
            os.fsync(file.fileno())
        return temp_path
    except OSError as exc:
        if temp_path is not None:
            _unlink_if_exists(temp_path)
        raise HostArtifactWriteError("Artifact temp write failed") from exc


def _prepare_directory(root: Path, path: Path, *, create: bool) -> None:
    """准备并校验 artifact 目录。

    :param root: artifact 根目录。
    :param path: 待准备目录。
    :param create: 缺失时是否创建。
    :returns: ``None``。
    :raises HostArtifactWriteError: 目录不可用或逃逸 root 时抛出。
    """

    if not path.exists():
        if not create:
            raise HostArtifactWriteError("Artifact directory does not exist")
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise HostArtifactWriteError("Artifact directory create failed") from exc
    if not path.is_dir():
        raise HostArtifactWriteError("Artifact path is not a directory")
    _ensure_contained(root, path)


def _write_temp_file_under_root(root: Path, content: bytes) -> Path:
    """在 artifact root 的 ``.tmp`` 目录下写入临时文件。

    :param root: artifact 根目录。
    :param content: artifact bytes。
    :returns: temp 文件路径。
    :raises HostArtifactWriteError: temp 目录或 temp 写入失败时抛出。
    """

    temp_dir = root / _ARTIFACT_TEMP_DIR_NAME
    if temp_dir.exists():
        _ensure_contained(root, temp_dir)
    _prepare_directory(root, temp_dir, create=True)
    return _write_temp_file(content, temp_dir)


def _path_from_posix_relative(root: Path, relative_path: str) -> Path:
    """把 POSIX 相对路径转换为当前平台路径。

    :param root: artifact 根目录。
    :param relative_path: POSIX 相对路径。
    :returns: root 下的平台路径。
    :raises HostDurableError: 相对路径无效时抛出。
    """

    _validate_relative_path_text(relative_path)
    path = PurePosixPath(relative_path)
    return root.joinpath(*path.parts)


def _contained_final_path(root: Path, relative_path: str) -> Path:
    """返回 containment 校验后的最终路径。

    :param root: artifact 根目录。
    :param relative_path: artifact 相对路径。
    :returns: root 下的最终路径。
    :raises HostArtifactWriteError: 既有路径通过 symlink 逃逸时抛出。
    """

    _ensure_parent_dir_contained(root, relative_path)
    return _path_from_posix_relative(root, relative_path)


def _prepare_artifact_root(root: Path, *, create: bool) -> None:
    """准备 artifact 根目录。

    :param root: artifact 根目录。
    :param create: 缺失时是否创建。
    :returns: ``None``。
    :raises HostArtifactWriteError: 根目录不可用时抛出。
    """

    if root.exists():
        if not root.is_dir():
            raise HostArtifactWriteError("Artifact root is not a directory")
        return
    if not create:
        raise HostArtifactWriteError("Artifact root does not exist")
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise HostArtifactWriteError("Artifact root create failed") from exc
