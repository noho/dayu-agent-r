"""文件系统仓储通用工具函数。

提供 ticker/条目名/来源类型标准化、URI 解析、JSON 原子读写等纯函数工具。
"""

from __future__ import annotations

import json
import mimetypes
import os
import uuid
from pathlib import Path, PureWindowsPath
from typing import Any, Optional

from dayu.contracts.json_value import JsonValue
from dayu.fins.domain.document_models import FileObjectMeta, now_iso8601
from dayu.fins.domain.enums import SourceKind
from dayu.fins.ticker_normalization import try_normalize_ticker

# -- 文件名常量 --
_SOURCE_META_FILENAME = "meta.json"
_PROCESSED_META_FILENAME = "tool_snapshot_meta.json"
_DOWNLOAD_REJECTIONS_FILENAME = "_download_rejections.json"
_REJECTED_FILINGS_DIRNAME = ".rejections"


# ---------- 标准化 ----------


def _normalize_path_component(value: str, *, field_name: str) -> str:
    """标准化并校验单个文件系统路径组件。

    Args:
        value: 原始路径组件。
        field_name: 错误信息使用的字段名。

    Returns:
        去除首尾空白后的单路径组件。

    Raises:
        ValueError: 组件为空、为当前/父目录、包含分隔符或表达绝对路径/盘符时抛出。
    """

    normalized = str(value).strip()
    if not normalized:
        raise ValueError(f"{field_name} 不能为空")
    if normalized in {".", ".."}:
        raise ValueError(f"{field_name} 非法")
    if "/" in normalized or "\\" in normalized:
        raise ValueError(f"{field_name} 不能包含路径分隔符")
    if Path(normalized).is_absolute() or PureWindowsPath(normalized).drive:
        raise ValueError(f"{field_name} 不能是绝对路径或盘符表达")
    return normalized


def _normalize_ticker(ticker: str) -> str:
    """标准化 ticker。

    优先走 ``try_normalize_ticker`` 真源；识别失败时回退到
    ``strip().upper()``。canonical 与 fallback 最终都通过同一个单路径组件校验。

    Args:
        ticker: 原始 ticker。

    Returns:
        标准化后的 ticker。

    Raises:
        ValueError: ticker 为空、包含路径分隔符或表达绝对路径/盘符时抛出。
    """

    normalized_source = try_normalize_ticker(ticker)
    candidate = normalized_source.canonical if normalized_source is not None else ticker.strip().upper()
    return _normalize_path_component(candidate, field_name="ticker")


def _normalize_company_ticker_aliases(
    *,
    canonical_ticker: str,
    ticker_aliases: Optional[list[str]],
) -> list[str]:
    """标准化公司级 ticker alias 列表。

    Args:
        canonical_ticker: 规范 ticker。
        ticker_aliases: 原始 alias 列表。

    Returns:
        去重后的 alias 列表，且首项始终为规范 ticker。

    Raises:
        ValueError: alias 中存在空白 ticker 时抛出。
    """

    normalized_aliases: list[str] = []
    for raw_alias in [canonical_ticker, *(ticker_aliases or [])]:
        normalized_alias = _normalize_ticker(raw_alias)
        if normalized_alias in normalized_aliases:
            continue
        normalized_aliases.append(normalized_alias)
    return normalized_aliases


def _normalize_entry_name(name: str) -> str:
    """标准化文档目录直系条目名。

    Args:
        name: 条目名称。

    Returns:
        规范化后的条目名称。

    Raises:
        ValueError: 名称为空、包含路径分隔或为 `.` / `..` 时抛出。
    """

    return _normalize_path_component(name, field_name="条目名称")


def _normalize_document_id(document_id: str) -> str:
    """标准化并校验仓储文档 ID。

    Args:
        document_id: 原始文档 ID。

    Returns:
        可作为单个路径组件使用的文档 ID。

    Raises:
        ValueError: 文档 ID 为空、包含路径分隔或为 ``.`` / ``..`` 时抛出。
    """

    return _normalize_path_component(document_id, field_name="document_id")


def _normalize_filename(filename: str) -> str:
    """标准化仓储文件名。

    Args:
        filename: 原始文件名。

    Returns:
        可作为单个路径组件使用的文件名。

    Raises:
        ValueError: 文件名为空、为当前/父目录、包含分隔符或表达绝对路径/盘符时抛出。
    """

    return _normalize_path_component(filename, field_name="filename")


def _normalize_object_key(key: str) -> str:
    """标准化本地对象存储的多组件 key。

    Args:
        key: 使用正斜杠分隔的原始对象 key。

    Returns:
        每个组件均已校验的 canonical 对象 key。

    Raises:
        ValueError: key 为空、为绝对路径、包含反斜杠、空组件或非法组件时抛出。
    """

    normalized = str(key).strip()
    if not normalized:
        raise ValueError("key 不能为空")
    if normalized.startswith("/"):
        raise ValueError("key 不能以路径分隔符开头")
    if "\\" in normalized:
        raise ValueError("key 不能包含反斜杠")
    raw_segments = normalized.split("/")
    if any(segment == "" for segment in raw_segments):
        raise ValueError("key 不能包含空路径组件")
    segments = [
        _normalize_path_component(segment, field_name="key 路径组件")
        for segment in raw_segments
    ]
    return "/".join(segments)


def _normalize_source_kind(source_kind: str | SourceKind) -> SourceKind:
    """标准化来源类型。

    Args:
        source_kind: 来源类型。

    Returns:
        标准化后的 `SourceKind`。

    Raises:
        ValueError: 来源类型非法时抛出。
    """

    if isinstance(source_kind, SourceKind):
        return source_kind
    try:
        return SourceKind(str(source_kind))
    except ValueError as exc:
        raise ValueError(f"source_kind 非法: {source_kind}") from exc


def _source_dir_name(source_kind: SourceKind) -> str:
    """返回来源目录名。

    Args:
        source_kind: 来源类型。

    Returns:
        目录名（filings/materials）。

    Raises:
        ValueError: 来源类型非法时抛出。
    """

    if source_kind == SourceKind.FILING:
        return "filings"
    if source_kind == SourceKind.MATERIAL:
        return "materials"
    raise ValueError(f"source_kind 非法: {source_kind}")


# ---------- URI / 文件名 ----------


def _infer_filename_from_uri(uri: str) -> str:
    """从 URI 推断文件名。

    Args:
        uri: 文件 URI。

    Returns:
        文件名；无法解析时返回空字符串。

    Raises:
        无。
    """

    raw = str(uri or "").strip()
    if not raw:
        return ""
    if "://" in raw:
        raw = raw.split("://", 1)[1]
    raw = raw.rstrip("/")
    if not raw:
        return ""
    return Path(raw).name or raw.split("/")[-1]


def _local_path_from_uri(portfolio_root: Path, uri: str) -> Path:
    """从 local URI 解析本地路径。

    Args:
        portfolio_root: portfolio 根目录。
        uri: local URI。

    Returns:
        本地路径。

    Raises:
        ValueError: URI 非法或 scheme 不支持时抛出。
    """

    raw = str(uri or "").strip()
    if not raw:
        raise ValueError("uri 不能为空")
    if not raw.startswith("local://"):
        raise ValueError(f"不支持的 URI scheme: {raw}")
    raw_key = raw.split("local://", 1)[1]
    if not raw_key:
        raise ValueError("local URI 缺少 key")
    key = _normalize_object_key(raw_key)
    normalized_root = portfolio_root.resolve()
    path = (normalized_root / Path(*key.split("/"))).resolve()
    try:
        path.relative_to(normalized_root)
    except ValueError as exc:
        raise ValueError("local URI key 越界，禁止访问 portfolio 根目录外路径") from exc
    return path


def _guess_media_type(path: Path) -> Optional[str]:
    """根据路径推断 media_type。

    Args:
        path: 文件路径。

    Returns:
        media_type 或 None。

    Raises:
        无。
    """

    return mimetypes.guess_type(str(path))[0]


# ---------- 文件条目操作 ----------


def _extract_file_payloads(meta: dict[str, Any]) -> list[dict[str, Any]]:
    """从 meta 中提取 files 列表。

    Args:
        meta: 文档元数据字典。

    Returns:
        文件条目列表。

    Raises:
        无。
    """

    files = meta.get("files", [])
    if not isinstance(files, list):
        return []
    return [item for item in files if isinstance(item, dict)]


def _normalize_file_entries(file_entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """标准化外部传入的文件条目。

    Args:
        file_entries: 外部文件条目列表。

    Returns:
        规范化后的文件条目列表。

    Raises:
        无。
    """

    normalized: list[dict[str, Any]] = []
    for item in file_entries:
        if not isinstance(item, dict):
            continue
        payload = dict(item)
        if not payload.get("name"):
            payload["name"] = _infer_filename_from_uri(payload.get("uri", ""))
        normalized.append(payload)
    return normalized


def _build_file_payloads(files: list[FileObjectMeta]) -> list[dict[str, Any]]:
    """构建 meta.json 的 files 列表。

    Args:
        files: 文件对象元数据列表。

    Returns:
        可序列化的文件条目列表。

    Raises:
        无。
    """

    payloads: list[dict[str, Any]] = []
    for item in files:
        name = _infer_filename_from_uri(item.uri)
        payloads.append(
            {
                "name": name,
                "uri": item.uri,
                "etag": item.etag,
                "last_modified": item.last_modified,
                "size": item.size,
                "content_type": item.content_type,
                "sha256": item.sha256,
                "ingested_at": now_iso8601(),
            }
        )
    return payloads


def _extract_file_names(file_payloads: list[dict[str, Any]]) -> list[str]:
    """提取文件名列表。

    Args:
        file_payloads: 文件条目列表。

    Returns:
        文件名列表。

    Raises:
        无。
    """

    names: list[str] = []
    for item in file_payloads:
        name = str(item.get("name") or _infer_filename_from_uri(item.get("uri", ""))).strip()
        if name:
            names.append(name)
    return names


def _resolve_primary_uri(file_payloads: list[dict[str, Any]], primary_name: Optional[str]) -> Optional[str]:
    """从文件条目列表中解析主文件 URI。

    Args:
        file_payloads: 文件条目列表。
        primary_name: 主文件名。

    Returns:
        主文件 URI；若未找到返回 `None`。

    Raises:
        无。
    """

    if not file_payloads:
        return None
    if primary_name:
        for item in file_payloads:
            name = str(item.get("name") or _infer_filename_from_uri(item.get("uri", ""))).strip()
            if name == primary_name:
                return str(item.get("uri"))
    return str(file_payloads[0].get("uri"))


def _file_object_meta_from_dict(payload: dict[str, Any]) -> FileObjectMeta:
    """从字典构建 `FileObjectMeta`。

    Args:
        payload: 文件条目字典。

    Returns:
        `FileObjectMeta` 实例。

    Raises:
        KeyError: 缺少 uri 时抛出。
    """

    return FileObjectMeta(
        uri=str(payload["uri"]),
        etag=str(payload.get("etag")) if payload.get("etag") is not None else None,
        last_modified=str(payload.get("last_modified")) if payload.get("last_modified") is not None else None,
        size=_coerce_optional_int(payload.get("size")),
        content_type=str(payload.get("content_type")) if payload.get("content_type") is not None else None,
        sha256=str(payload.get("sha256")) if payload.get("sha256") is not None else None,
    )


def _coerce_optional_int(value: JsonValue) -> int | None:
    """把未知值收窄为可选整数。

    Args:
        value: 原始值。

    Returns:
        合法整数；否则返回 ``None``。

    Raises:
        无。
    """

    if value is None or isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


# ---------- JSON 读写 ----------


def _read_json(path: Path) -> dict[str, Any] | list[Any]:
    """读取 JSON 文件。

    Args:
        path: JSON 文件路径。

    Returns:
        解析后的对象。

    Raises:
        FileNotFoundError: 文件不存在时抛出。
        ValueError: JSON 无法解析时抛出。
    """

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON 解析失败: {path}") from exc


def _read_json_object(path: Path) -> dict[str, Any]:
    """读取 JSON object 文件。

    Args:
        path: JSON 文件路径。

    Returns:
        解析后的 JSON object。

    Raises:
        FileNotFoundError: 文件不存在时抛出。
        ValueError: JSON 无法解析或根节点不是 object 时抛出。
    """

    payload = _read_json(path)
    if not isinstance(payload, dict):
        raise ValueError(f"JSON 根节点必须是 object: {path}")
    return payload


def _read_json_array(path: Path) -> list[Any]:
    """读取 JSON array 文件。

    Args:
        path: JSON 文件路径。

    Returns:
        解析后的 JSON array。

    Raises:
        FileNotFoundError: 文件不存在时抛出。
        ValueError: JSON 无法解析或根节点不是 array 时抛出。
    """

    payload = _read_json(path)
    if not isinstance(payload, list):
        raise ValueError(f"JSON 根节点必须是 array: {path}")
    return payload


def _write_json(path: Path, payload: Any) -> None:
    """写入 JSON 文件。

    Args:
        path: 目标路径。
        payload: 可序列化对象。

    Returns:
        无。

    Raises:
        OSError: 写入失败时抛出。
        TypeError: 对象不可序列化时抛出。
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(payload, ensure_ascii=False, indent=2)
    temp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temp_path.open("w", encoding="utf-8") as stream:
            stream.write(serialized)
            stream.flush()
            os.fsync(stream.fileno())
        # 复杂逻辑说明：通过明确的 same-directory 原子替换确保意外退出时不会留下半写入 JSON。
        os.replace(temp_path, path)
        _fsync_directory(path.parent)
    finally:
        temp_path.unlink(missing_ok=True)


def _fsync_directory(path: Path) -> None:
    """将目录元数据刷新到磁盘（尽力而为）。

    Args:
        path: 目录路径。

    Returns:
        无。

    Raises:
        无。
    """

    try:
        directory_fd = os.open(str(path), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(directory_fd)
    except OSError:
        return
    finally:
        os.close(directory_fd)


def _list_directory_names(root: Path) -> list[str]:
    """列出目录下的一级子目录名。

    Args:
        root: 根目录。

    Returns:
        已排序目录名列表。

    Raises:
        OSError: 读取目录失败时抛出。
    """

    if not root.exists():
        return []
    # 隐藏目录（例如 `.rejections/`）属于仓储内部治理数据，不应暴露为 active 文档 ID。
    names = [path.name for path in root.iterdir() if path.is_dir() and not path.name.startswith(".")]
    names.sort()
    return names
