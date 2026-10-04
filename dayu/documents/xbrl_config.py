"""管理员 XBRL 部署配置、可信清单及请求独占快照的唯一校验边界。

此处只验证部署文件及 ZIP 成员完整性，不解释 XBRL 引用或财务事实。
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import stat
import zlib
from dataclasses import dataclass
from datetime import datetime, timedelta
from lzma import LZMAError
from pathlib import Path, PurePosixPath
from typing import cast
from urllib.parse import urlsplit
from zipfile import BadZipFile, ZipFile

from dayu.contracts.json_value import JsonValue

_SHA_LENGTH = 64
_PRIVATE_WRITE_BITS = stat.S_IWGRP | stat.S_IWOTH
_RESERVED_INSTANCE_NAME = "instance.xml"
_CONFIG_KEYS = frozenset({"taxonomy_root", "manifest_path", "manifest_sha256"})
_MANIFEST_KEYS = frozenset({"source_urls", "acquired_at", "license_urls", "files"})
_FILE_KEYS = frozenset({"relative_path", "size_bytes", "sha256", "archive_entries"})
_ENTRY_KEYS = frozenset({"relative_path", "size_bytes", "sha256"})


def _unique_json_fields(pairs: list[tuple[str, JsonValue]]) -> dict[str, JsonValue]:
    """参数：JSON 原字段序列；返回：唯一字段字典；异常：重复字段抛配置错误。"""
    result: dict[str, JsonValue] = {}
    for key, value in pairs:
        if key in result:
            raise XbrlConfigurationError("XBRL JSON 包含重复字段")
        result[key] = value
    return result


class XbrlConfigurationError(ValueError):
    """配置、清单或可信复制无法闭合验证。"""


@dataclass(frozen=True, slots=True)
class TaxonomyArchiveEntry:
    """ZIP 成员声明，目录成员用末尾斜线及零字节声明。"""

    relative_path: PurePosixPath
    size_bytes: int
    sha256: str


@dataclass(frozen=True, slots=True)
class TaxonomyFile:
    """清单文件声明；仅非 ZIP 文件的 archive_entries 可为空。"""

    relative_path: PurePosixPath
    size_bytes: int
    sha256: str
    archive_entries: tuple[TaxonomyArchiveEntry, ...] | None


@dataclass(frozen=True, slots=True)
class TaxonomyManifest:
    """部署来源、UTC 获取时间、许可及完整文件声明。"""

    source_urls: tuple[str, ...]
    acquired_at: datetime
    license_urls: tuple[str, ...]
    files: tuple[TaxonomyFile, ...]


@dataclass(frozen=True, slots=True)
class XbrlConversionConfig:
    """显式管理员根、清单路径及管理员绑定的摘要。"""

    taxonomy_root: Path
    manifest_path: Path
    manifest_sha256: str


@dataclass(frozen=True, slots=True)
class PreparedXbrlInput:
    """已完整复验的本请求只读 taxonomy 副本和独占可写目录。"""

    taxonomy_snapshot_root: Path
    manifest: TaxonomyManifest
    writable_root: Path


def _shape(value: JsonValue, keys: frozenset[str]) -> dict[str, JsonValue]:
    """参数：JSON 与精确字段集；返回：字典；异常：形状不符抛配置错误。"""
    if not isinstance(value, dict) or value.keys() != keys:
        raise XbrlConfigurationError("XBRL JSON 字段不符合声明")
    return value


def _text(value: JsonValue) -> str:
    """参数：候选值；返回：非空原文本；异常：类型或空白不符抛配置错误。"""
    if not isinstance(value, str) or not value or value != value.strip():
        raise XbrlConfigurationError("XBRL 声明必须是非空规范文本")
    return value


def _digest(value: JsonValue) -> str:
    """参数：摘要；返回：规范 SHA256；异常：非法值抛配置错误。"""
    text = _text(value)
    if len(text) != _SHA_LENGTH or any(c not in "0123456789abcdef" for c in text):
        raise XbrlConfigurationError("XBRL SHA256 声明非法")
    return text


def _size(value: JsonValue) -> int:
    """参数：字节数；返回：非负整数；异常：非法值抛配置错误。"""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise XbrlConfigurationError("XBRL 字节数声明非法")
    return value


def _relative(value: JsonValue) -> PurePosixPath:
    """参数：清单相对路径；返回：规范路径；异常：越界或非规范抛配置错误。"""
    text = _text(value)
    path = PurePosixPath(text)
    if path.is_absolute() or ".." in path.parts or "\\" in text or str(path) != text.rstrip("/"):
        raise XbrlConfigurationError("XBRL 清单路径非法")
    if str(path) == ".":
        raise XbrlConfigurationError("XBRL 清单路径不能为空")
    return path


def _urls(value: JsonValue) -> tuple[str, ...]:
    """参数：URL 列表；返回：声明元组；异常：非公开 HTTPS 声明抛配置错误。"""
    if not isinstance(value, list) or not value:
        raise XbrlConfigurationError("XBRL 来源及许可声明不能为空")
    urls = tuple(_text(item) for item in value)
    for url in urls:
        parts = urlsplit(url)
        if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
            raise XbrlConfigurationError("XBRL 来源及许可必须显式声明 HTTPS URL")
    if len(set(urls)) != len(urls):
        raise XbrlConfigurationError("XBRL URL 声明重复")
    return urls


def _parse_manifest(raw: bytes) -> TaxonomyManifest:
    """参数：清单字节；返回：严格清单；异常：非法 JSON/声明抛配置错误。"""
    value = _shape(cast(JsonValue, json.loads(raw, object_pairs_hook=_unique_json_fields)), _MANIFEST_KEYS)
    acquired = datetime.fromisoformat(_text(value["acquired_at"]))
    if acquired.utcoffset() != timedelta(0):
        raise XbrlConfigurationError("XBRL 获取时间必须显式 UTC")
    rows = value["files"]
    if not isinstance(rows, list) or not rows:
        raise XbrlConfigurationError("XBRL 文件清单不能为空")
    files: list[TaxonomyFile] = []
    for row in rows:
        fields = _shape(row, _FILE_KEYS)
        path = _relative(fields["relative_path"])
        entries_value = fields["archive_entries"]
        entries: tuple[TaxonomyArchiveEntry, ...] | None = None
        if path.suffix.lower() == ".zip":
            if not isinstance(entries_value, list) or not entries_value:
                raise XbrlConfigurationError("XBRL ZIP 必须声明全部成员")
            parsed: list[TaxonomyArchiveEntry] = []
            for entry in entries_value:
                item = _shape(entry, _ENTRY_KEYS)
                parsed.append(TaxonomyArchiveEntry(_relative(item["relative_path"]), _size(item["size_bytes"]), _digest(item["sha256"])))
            if len({e.relative_path for e in parsed}) != len(parsed):
                raise XbrlConfigurationError("XBRL ZIP 成员声明重复")
            entries = tuple(parsed)
        elif entries_value is not None:
            raise XbrlConfigurationError("非 ZIP 不能声明 ZIP 成员")
        files.append(TaxonomyFile(path, _size(fields["size_bytes"]), _digest(fields["sha256"]), entries))
    if len({f.relative_path for f in files}) != len(files):
        raise XbrlConfigurationError("XBRL 文件声明重复")
    return TaxonomyManifest(_urls(value["source_urls"]), acquired, _urls(value["license_urls"]), tuple(files))


def _read_regular(path: Path, *, size: int | None, digest: str | None) -> bytes:
    """参数：路径及可选完整性声明；返回：同 fd 字节；异常：链接/变动/摘要错误抛配置错误。"""
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_mode & _PRIVATE_WRITE_BITS:
            raise XbrlConfigurationError("XBRL 输入必须为不可共享写入的单链接普通文件")
        if size is not None and before.st_size != size:
            raise XbrlConfigurationError("XBRL 文件大小与清单不符")
        raw = stream.read(before.st_size + 1)
        after = os.fstat(stream.fileno())
        if (before.st_dev, before.st_ino, before.st_mode, before.st_nlink, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_dev, after.st_ino, after.st_mode, after.st_nlink, after.st_size, after.st_mtime_ns, after.st_ctime_ns) or len(raw) != before.st_size:
            raise XbrlConfigurationError("XBRL 文件读取期间变动")
        if digest is not None and hashlib.sha256(raw).hexdigest() != digest:
            raise XbrlConfigurationError("XBRL 文件摘要与清单不符")
        return raw


def _trusted_path(value: JsonValue, forbidden_root: Path) -> Path:
    """参数：管理员路径与工作区；返回：规范绝对路径；异常：重叠/链接/权限错误抛配置错误。"""
    path = Path(_text(value))
    if not path.is_absolute() or ".." in path.parts or path.resolve(strict=True) != path:
        raise XbrlConfigurationError("XBRL 管理员路径必须为无链接规范绝对路径")
    forbidden = forbidden_root.resolve()
    if path.is_relative_to(forbidden) or forbidden.is_relative_to(path):
        raise XbrlConfigurationError("XBRL 管理员输入不能与工作区重叠")
    if path.stat().st_mode & _PRIVATE_WRITE_BITS or path.parent.stat().st_mode & _PRIVATE_WRITE_BITS:
        raise XbrlConfigurationError("XBRL 管理员输入及专用父目录不能允许组或公共写入")
    return path


def _verify_archive(raw: bytes, entries: tuple[TaxonomyArchiveEntry, ...]) -> None:
    """参数：ZIP 字节与全部声明；返回：无；异常：非法/未声明/摘要不符抛配置错误。"""
    expected = {entry.relative_path: entry for entry in entries}
    try:
        archive = ZipFile(io.BytesIO(raw))
    except (BadZipFile, NotImplementedError, UnicodeError) as exc:
        raise XbrlConfigurationError("XBRL ZIP 容器非法或格式不受支持") from exc
    with archive:
        seen: set[PurePosixPath] = set()
        for info in archive.infolist():
            path = _relative(info.filename)
            mode = info.external_attr >> 16
            if path in seen or info.flag_bits & 1 or stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR):
                raise XbrlConfigurationError("XBRL ZIP 包含重复、加密或非普通成员")
            seen.add(path)
            if path not in expected:
                raise XbrlConfigurationError("XBRL ZIP 包含未声明成员")
            entry = expected[path]
            if info.file_size != entry.size_bytes or (info.is_dir() and entry.size_bytes != 0):
                raise XbrlConfigurationError("XBRL ZIP 成员大小不符")
            # 只归一 ZIP 库读取输入时的格式、解压和截断错误，不吞校验逻辑错误。
            try:
                with archive.open(info) as stream:
                    content = stream.read(entry.size_bytes + 1)
            except (BadZipFile, NotImplementedError, UnicodeError, EOFError, OSError, OverflowError, zlib.error, LZMAError) as exc:
                raise XbrlConfigurationError("XBRL ZIP 成员无法完整读取或校验") from exc
            if len(content) != entry.size_bytes or hashlib.sha256(content).hexdigest() != entry.sha256:
                raise XbrlConfigurationError("XBRL ZIP 成员摘要不符")
        if seen != expected.keys():
            raise XbrlConfigurationError("XBRL ZIP 缺少声明成员")



def _inventory(root: Path) -> set[PurePosixPath]:
    """参数：可信目录；返回：精确文件集；异常：链接或非普通条目抛配置错误。"""
    found: set[PurePosixPath] = set()
    directories: set[PurePosixPath] = set()
    mode = root.lstat().st_mode
    if not stat.S_ISDIR(mode) or mode & _PRIVATE_WRITE_BITS or root.resolve(strict=True) != root:
        raise XbrlConfigurationError("XBRL 根必须是规范、独占写入的真实目录")
    for directory, dirs, files in os.walk(root, followlinks=False):
        for name in (*dirs, *files):
            path = Path(directory) / name
            mode = path.lstat().st_mode
            if stat.S_ISLNK(mode) or not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)) or mode & _PRIVATE_WRITE_BITS:
                raise XbrlConfigurationError("XBRL 目录含链接、特殊或共享可写条目")
        found.update(PurePosixPath((Path(directory) / name).relative_to(root).as_posix()) for name in files)
        directories.update(PurePosixPath((Path(directory) / name).relative_to(root).as_posix()) for name in dirs)
    expected_directories = {parent for path in found for parent in path.parents if str(parent) != "."}
    if directories != expected_directories:
        raise XbrlConfigurationError("XBRL 根含未声明目录条目")
    return found


def _verify_files(root: Path, manifest: TaxonomyManifest) -> None:
    """参数：根与清单；返回：无；异常：文件/ZIP 集合或字节不符抛配置错误。"""
    if _inventory(root) != {file.relative_path for file in manifest.files}:
        raise XbrlConfigurationError("XBRL 目录与完整清单不一致")
    for file in manifest.files:
        raw = _read_regular(root / file.relative_path, size=file.size_bytes, digest=file.sha256)
        if file.archive_entries is not None:
            _verify_archive(raw, file.archive_entries)


def load_xbrl_conversion_config(config_path: Path | None, forbidden_root: Path) -> XbrlConversionConfig | None:
    """参数：显式配置或未配置、工作区根；返回：校验配置或 None；异常：配置不可信抛配置错误。"""
    if config_path is None:
        return None
    try:
        path = _trusted_path(str(config_path), forbidden_root)
        fields = _shape(cast(JsonValue, json.loads(_read_regular(path, size=None, digest=None), object_pairs_hook=_unique_json_fields)), _CONFIG_KEYS)
        root = _trusted_path(fields["taxonomy_root"], forbidden_root)
        manifest_path = _trusted_path(fields["manifest_path"], forbidden_root)
        digest = _digest(fields["manifest_sha256"])
        if not root.is_dir() or manifest_path.is_relative_to(root) or path.is_relative_to(root):
            raise XbrlConfigurationError("XBRL taxonomy 必须是独立目录")
        manifest = _parse_manifest(_read_regular(manifest_path, size=None, digest=digest))
        _verify_files(root, manifest)
        return XbrlConversionConfig(root, manifest_path, digest)
    except XbrlConfigurationError:
        raise
    except (OSError, ValueError, KeyError) as exc:
        raise XbrlConfigurationError("XBRL 配置读取或完整性校验失败") from exc


def prepare_xbrl_input(config: XbrlConversionConfig, *, snapshot_root: Path, writable_root: Path, stream_name: str) -> PreparedXbrlInput:
    """参数：已校验配置、新快照/工作目录、原件名；返回：复验副本；异常：复制不闭合抛配置错误。"""
    try:
        roots = (config.taxonomy_root, snapshot_root, writable_root)
        if any(not p.is_absolute() or p.resolve() != p for p in roots):
            raise XbrlConfigurationError("XBRL 请求目录必须规范绝对")
        if any(a.is_relative_to(b) for a in roots for b in roots if a != b) or len(set(roots)) != len(roots):
            raise XbrlConfigurationError("XBRL 请求区域必须互不重叠")
        manifest = _parse_manifest(_read_regular(config.manifest_path, size=None, digest=config.manifest_sha256))
        if any(f.relative_path.name in {_RESERVED_INSTANCE_NAME, stream_name} for f in manifest.files):
            raise XbrlConfigurationError("XBRL taxonomy 文件与原件名冲突")
        _verify_files(config.taxonomy_root, manifest)
        snapshot_root.mkdir(mode=0o700)
        writable_root.mkdir(mode=0o700)
        for file in manifest.files:
            raw = _read_regular(config.taxonomy_root / file.relative_path, size=file.size_bytes, digest=file.sha256)
            target = snapshot_root / file.relative_path
            target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            with target.open("xb") as stream:
                stream.write(raw)
            target.chmod(0o400)
        prepared = PreparedXbrlInput(snapshot_root, manifest, writable_root)
        verify_prepared_xbrl_input(prepared)
        return prepared
    except XbrlConfigurationError:
        raise
    except (OSError, ValueError, KeyError) as exc:
        raise XbrlConfigurationError("XBRL 请求快照准备失败") from exc


def verify_prepared_xbrl_input(prepared: PreparedXbrlInput) -> None:
    """参数：受控快照；返回：无；异常：启动后字节/清单不符抛配置错误。"""
    try:
        _verify_files(prepared.taxonomy_snapshot_root, prepared.manifest)
    except XbrlConfigurationError:
        raise
    except (OSError, ValueError, KeyError) as exc:
        raise XbrlConfigurationError("XBRL worker 快照复验失败") from exc
