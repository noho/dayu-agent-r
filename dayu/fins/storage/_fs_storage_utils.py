"""文件系统仓储通用工具函数。

提供 ticker/条目名/来源类型标准化、URI 解析、JSON 原子读写等纯函数工具。
"""

from __future__ import annotations

import json
import mimetypes
import os
import uuid
from pathlib import Path, PureWindowsPath
from typing import Any, BinaryIO, NoReturn, Optional

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


def _canonicalize_ticker_alias(ticker: str) -> str:
    """把公司检索 alias 规范化为公共 ticker alias。

    优先走 ``try_normalize_ticker`` 真源；识别失败时回退到
    ``strip().upper()``。canonical 与 fallback 最终都通过同一个单路径组件校验。

    Args:
        ticker: 原始公司检索 alias。

    Returns:
        标准化后的 ticker alias。

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

    normalized_aliases: list[str] = [canonical_ticker]
    for raw_alias in ticker_aliases or []:
        normalized_alias = _canonicalize_ticker_alias(raw_alias)
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
        raise ValueError("只支持 local URI")
    raw_key = raw.split("local://", 1)[1]
    if not raw_key:
        raise ValueError("local URI 缺少 key")
    key = _normalize_object_key(raw_key)
    try:
        normalized_root = portfolio_root.resolve()
        path = (normalized_root / Path(*key.split("/"))).resolve()
    except OSError as exc:
        _raise_path_free_error(
            _project_filesystem_error(exc, action="解析 local storage URI")
        )
    try:
        path.relative_to(normalized_root)
    except ValueError:
        _raise_path_free_error(
            ValueError("local URI key 越界，禁止访问 portfolio 根目录外路径")
        )
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

    if not primary_name:
        return None
    for item in file_payloads:
        name = str(item.get("name") or _infer_filename_from_uri(item.get("uri", ""))).strip()
        if name == primary_name:
            return str(item.get("uri"))
    return None


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


def _new_path_free_filesystem_error(error: OSError, *, message: str) -> OSError:
    """按原始异常类别与 errno 构造无物理 locator 的新异常。

    Args:
        error: 底层文件系统抛出的原始异常。
        message: 不包含物理路径的异常说明。

    Returns:
        保留有意义 subclass 与 ``errno``、但没有 raw args/notes/traceback 的异常。

    Raises:
        无。
    """

    error_type = type(error)
    if error.errno is None:
        return error_type(message)
    return error_type(error.errno, message)


def _project_filesystem_error(error: OSError, *, action: str) -> OSError:
    """将原始文件系统异常投影为完整 graph 均无 locator 的同类异常。

    Args:
        error: 底层文件系统抛出的原始异常。
        action: 不包含物理路径的 storage 操作说明。

    Returns:
        保留有意义 subclass、``errno`` 与 path-free cause 类别的异常。

    Raises:
        无。
    """

    projected_error = _new_path_free_filesystem_error(
        error,
        message=f"{action}失败",
    )
    projected_cause = _new_path_free_filesystem_error(
        error,
        message=f"{action}底层文件系统失败",
    )
    projected_error.__cause__ = projected_cause
    projected_error.__suppress_context__ = True
    return projected_error


def _raise_path_free_error(error: BaseException) -> NoReturn:
    """抛出已投影异常并显式移除当前 raw exception context。

    该 helper 只接受 owner 已重新构造、其 args/notes/cause 均不含 locator
    的异常。它不读取或清洗 raw message，也不承担下游补偿职责。

    Args:
        error: storage owner 已构造的 path-free 异常。

    Returns:
        永不返回。

    Raises:
        BaseException: 原样抛出传入异常；其 context 被清空，safe cause 保留。
    """

    try:
        raise error from error.__cause__
    except BaseException as projected_error:
        # 复杂逻辑说明：Python 会自动把当前 except 的 raw error 写入
        # __context__；必须在 re-raise 前清除，才能关闭完整 exception graph。
        projected_error.__context__ = None
        raise


def _append_secondary_error_note(
    primary_error: BaseException,
    secondary_error: BaseException,
    *,
    action: str,
) -> None:
    """把次级失败以无 locator 诊断附加到主异常。

    Args:
        primary_error: 必须保留的 authoritative 主异常。
        secondary_error: cleanup 或 lock release 阶段的次级异常。
        action: 不包含物理路径的次级操作说明。

    Returns:
        无。

    Raises:
        无。
    """

    diagnostic = f"{action}: error_type={secondary_error.__class__.__name__}"
    if isinstance(secondary_error, OSError) and secondary_error.errno is not None:
        diagnostic = f"{diagnostic} errno={secondary_error.errno}"
    primary_error.add_note(diagnostic)


def _list_directory(path: Path, *, action: str) -> list[Path]:
    """枚举目录并在 storage producer boundary 移除物理 locator。

    Args:
        path: 待枚举目录。
        action: 不包含物理路径的业务操作说明。

    Returns:
        当次枚举得到的直系条目快照。

    Raises:
        OSError: 目录枚举失败时抛出不含物理 locator 的同类异常。
    """

    try:
        return list(path.iterdir())
    except OSError as exc:
        _raise_path_free_error(_project_filesystem_error(exc, action=action))


def _read_file_bytes(path: Path, *, action: str) -> bytes:
    """读取文件字节并在 storage producer boundary 移除物理 locator。

    Args:
        path: 待读取文件。
        action: 不包含物理路径的业务操作说明。

    Returns:
        文件全部字节。

    Raises:
        OSError: 文件读取失败时抛出不含物理 locator 的同类异常。
    """

    try:
        return path.read_bytes()
    except OSError as exc:
        _raise_path_free_error(_project_filesystem_error(exc, action=action))


def _open_binary_file(path: Path, *, action: str) -> BinaryIO:
    """以二进制只读模式打开文件并移除物理 locator。

    Args:
        path: 待打开文件。
        action: 不包含物理路径的业务操作说明。

    Returns:
        已打开的二进制只读流。

    Raises:
        OSError: 文件打开失败时抛出不含物理 locator 的同类异常。
    """

    try:
        return path.open("rb")
    except OSError as exc:
        _raise_path_free_error(_project_filesystem_error(exc, action=action))


def _unlink_path(path: Path, *, missing_ok: bool, action: str) -> None:
    """删除文件型条目并在 storage producer boundary 移除物理 locator。

    Args:
        path: 待删除条目。
        missing_ok: 条目缺失时是否视为成功。
        action: 不包含物理路径的业务操作说明。

    Returns:
        无。

    Raises:
        OSError: 删除失败时抛出不含物理 locator 的同类异常。
    """

    try:
        path.unlink(missing_ok=missing_ok)
    except OSError as exc:
        _raise_path_free_error(_project_filesystem_error(exc, action=action))


def _read_json(path: Path) -> dict[str, Any] | list[Any]:
    """读取 JSON 文件。

    Args:
        path: JSON 文件路径。

    Returns:
        解析后的对象。

    Raises:
        FileNotFoundError: 文件不存在时抛出。
        ValueError: 路径是 symlink、非 regular file 或 JSON 无法解析时抛出。
    """

    try:
        if path.is_symlink():
            raise ValueError("JSON 文件禁止 symlink")
        if path.exists() and not path.is_file():
            raise ValueError("JSON 路径必须为 regular file")
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("JSON 解析失败") from exc
    except OSError as exc:
        _raise_path_free_error(
            _project_filesystem_error(exc, action="读取 storage JSON")
        )


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
        raise ValueError("JSON 根节点必须是 object")
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
        raise ValueError("JSON 根节点必须是 array")
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

    serialized = json.dumps(payload, ensure_ascii=False, indent=2)
    temp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    primary_error: BaseException | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with temp_path.open("w", encoding="utf-8") as stream:
            stream.write(serialized)
            stream.flush()
            os.fsync(stream.fileno())
        # 复杂逻辑说明：通过明确的 same-directory 原子替换确保意外退出时不会留下半写入 JSON。
        os.replace(temp_path, path)
        _fsync_directory(path.parent)
    except OSError as exc:
        projected_error = _project_filesystem_error(exc, action="写入 storage JSON")
        primary_error = projected_error
        _raise_path_free_error(projected_error)
    except BaseException as exc:
        primary_error = exc
        raise
    finally:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError as cleanup_error:
            projected_cleanup_error = _project_filesystem_error(
                cleanup_error,
                action="清理 storage JSON 临时文件",
            )
            if primary_error is None:
                _raise_path_free_error(projected_cleanup_error)
            _append_secondary_error_note(
                primary_error,
                projected_cleanup_error,
                action="storage JSON 临时文件清理失败",
            )


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
