"""SEC 下载状态与重建快照真源模块。"""

from __future__ import annotations

from dayu.contracts.json_value import JsonValue

import asyncio
import json
import time
from pathlib import Path
from typing import Final, Optional

from dayu.fins.domain.document_models import now_iso8601
from dayu.fins.downloaders.sec_downloader import (
    BrowseEdgarFiling,
    RemoteFileDescriptor,
    build_source_fingerprint,
)
from dayu.fins.storage import FilingMaintenanceRepositoryProtocol

from .sec_6k_rules import _infer_filename_from_uri


_SEC_CACHE_RELATIVE_DIR: Final[Path] = Path(".dayu") / "sec_cache"
_SEC_CACHE_DIR: Final[str] = _SEC_CACHE_RELATIVE_DIR.as_posix()
_SEC_CACHE_TTL_HOURS: Final[int] = 24
_SEC_CACHE_CATEGORY_SUBMISSIONS: Final[str] = "submissions"
_SEC_CACHE_CATEGORY_BROWSE_EDGAR: Final[str] = "browse_edgar"


def _build_sec_cache_dir(workspace_root: Path) -> Path:
    """构造 SEC HTTP 缓存目录。

    Args:
        workspace_root: Fins 运行时工作区根目录。

    Returns:
        工作区内 SEC cache 目录。

    Raises:
        无。
    """

    return workspace_root.resolve() / _SEC_CACHE_RELATIVE_DIR


def _load_rejection_registry(
    repository: FilingMaintenanceRepositoryProtocol,
    ticker: str,
) -> dict[str, dict[str, str]]:
    """加载拒绝注册表。

    Args:
        repository: filing 维护治理仓储。
        ticker: 股票代码。

    Returns:
        document_id 到拒绝记录的映射；文件不存在或解析失败时返回空字典。

    Raises:
        无。
    """

    return repository.load_download_rejection_registry(ticker)


def _save_rejection_registry(
    repository: FilingMaintenanceRepositoryProtocol,
    ticker: str,
    registry: dict[str, dict[str, str]],
) -> None:
    """持久化拒绝注册表。

    Args:
        repository: filing 维护治理仓储。
        ticker: 股票代码。
        registry: document_id 到拒绝记录的映射。

    Returns:
        无。

    Raises:
        无。
    """

    repository.save_download_rejection_registry(ticker, registry)


def _is_rejected(
    registry: dict[str, dict[str, str]],
    document_id: str,
    overwrite: bool,
    download_version: str,
) -> bool:
    """判断 document_id 是否命中拒绝注册表。

    条件：overwrite=False 且注册表中存在该 document_id 且 download_version 匹配。

    Args:
        registry: 拒绝注册表。
        document_id: 文档 ID。
        overwrite: 是否覆盖模式。
        download_version: 当前下载链路版本号。

    Returns:
        命中返回 True；否则返回 False。

    Raises:
        无。
    """

    if overwrite:
        return False
    entry = registry.get(document_id)
    if entry is None:
        return False
    return str(entry.get("download_version", "")) == download_version


def _record_rejection(
    registry: dict[str, dict[str, str]],
    document_id: str,
    reason: str,
    category: str,
    form_type: str,
    filing_date: str,
    download_version: str,
) -> None:
    """向拒绝注册表写入一条拒绝记录。

    Args:
        registry: 拒绝注册表（就地修改）。
        document_id: 文档 ID。
        reason: 拒绝原因标识。
        category: 筛选分类标签。
        form_type: 表单类型。
        filing_date: 申报日期。
        download_version: 当前下载链路版本号。

    Returns:
        无。

    Raises:
        无。
    """

    registry[document_id] = {
        "reason": reason,
        "category": category,
        "form_type": form_type,
        "filing_date": filing_date,
        "download_version": download_version,
    }


def _sec_cache_path(workspace_root: Path, category: str, key: str) -> Path:
    """构造缓存文件路径。

    Args:
        workspace_root: 工作区根目录。
        category: 缓存类别。
        key: 缓存键。

    Returns:
        缓存文件绝对路径。

    Raises:
        无。
    """

    safe_key = key.replace("/", "_").replace("\\", "_")
    return _build_sec_cache_dir(workspace_root) / category / f"{safe_key}.json"


def _read_sec_cache(
    workspace_root: Path,
    category: str,
    key: str,
    ttl_hours: int = _SEC_CACHE_TTL_HOURS,
) -> dict[str, JsonValue] | list[JsonValue] | None:
    """读取缓存，过期或不存在返回 None。

    Args:
        workspace_root: 工作区根目录。
        category: 缓存类别。
        key: 缓存键。
        ttl_hours: 有效期（小时）。

    Returns:
        反序列化后的缓存对象；无效或过期时返回 None。

    Raises:
        无。
    """

    path = _sec_cache_path(workspace_root, category, key)
    if not path.exists():
        return None
    try:
        age_seconds = time.time() - path.stat().st_mtime
        if age_seconds > ttl_hours * 3600:
            return None
        with open(path, "r", encoding="utf-8") as file_handle:
            return json.load(file_handle)
    except (json.JSONDecodeError, OSError):
        return None


def _write_sec_cache(
    workspace_root: Path,
    category: str,
    key: str,
    data: dict[str, JsonValue] | list[JsonValue],
) -> None:
    """写入缓存。

    Args:
        workspace_root: 工作区根目录。
        category: 缓存类别。
        key: 缓存键。
        data: 待缓存数据。

    Returns:
        无。

    Raises:
        无。
    """

    path = _sec_cache_path(workspace_root, category, key)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as file_handle:
            json.dump(data, file_handle, ensure_ascii=False)
    except OSError:
        pass


async def _read_sec_cache_async(
    workspace_root: Path,
    category: str,
    key: str,
    ttl_hours: int = _SEC_CACHE_TTL_HOURS,
) -> JsonValue:
    """异步读取缓存，过期或不存在返回 None。

    通过 asyncio.to_thread 将同步文件 I/O 卸载到线程池，避免阻塞事件循环。

    Args:
        workspace_root: 工作区根目录。
        category: 缓存类别。
        key: 缓存键。
        ttl_hours: 有效期（小时）。

    Returns:
        反序列化后的缓存对象；无效或过期时返回 None。
    """
    return await asyncio.to_thread(
        _read_sec_cache, workspace_root, category, key, ttl_hours,
    )


async def _write_sec_cache_async(
    workspace_root: Path,
    category: str,
    key: str,
    data: dict[str, JsonValue] | list[JsonValue],
) -> None:
    """异步写入缓存。

    通过 asyncio.to_thread 将同步文件 I/O 卸载到线程池，避免阻塞事件循环。

    Args:
        workspace_root: 工作区根目录。
        category: 缓存类别。
        key: 缓存键。
        data: 待缓存数据。
    """
    await asyncio.to_thread(
        _write_sec_cache, workspace_root, category, key, data,
    )


def _browse_edgar_filings_to_dicts(entries: list[BrowseEdgarFiling]) -> list[JsonValue]:
    """将 BrowseEdgarFiling 列表序列化为可 JSON 存储的字典列表。

    Args:
        entries: BrowseEdgarFiling 对象列表。

    Returns:
        可 JSON 序列化的字典列表。

    Raises:
        无。
    """

    return [
        {
            "form_type": entry.form_type,
            "filing_date": entry.filing_date,
            "accession_number": entry.accession_number,
            "cik": entry.cik,
            "index_url": getattr(entry, "index_url", ""),
        }
        for entry in entries
    ]


def _dicts_to_browse_edgar_filings(data: list[dict[str, str]]) -> list[BrowseEdgarFiling]:
    """将字典列表反序列化为 BrowseEdgarFiling 对象列表。

    Args:
        data: 字典列表。

    Returns:
        BrowseEdgarFiling 列表。

    Raises:
        无。
    """

    return [
        BrowseEdgarFiling(
            form_type=item["form_type"],
            filing_date=item["filing_date"],
            accession_number=item["accession_number"],
            cik=item["cik"],
            index_url=item["index_url"],
        )
        for item in data
    ]


def _index_file_entries(meta: Optional[dict[str, JsonValue]]) -> dict[str, dict[str, JsonValue]]:
    """按文件名索引已有文件条目。

    Args:
        meta: 文档 meta。

    Returns:
        文件名到条目的映射。

    Raises:
        无。
    """

    if not meta:
        return {}
    files = meta.get("files", [])
    if not isinstance(files, list):
        return {}
    mapping: dict[str, dict[str, JsonValue]] = {}
    for item in files:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or _infer_filename_from_uri(str(item.get("uri") or ""))).strip()
        if name:
            mapping[name] = item
    return mapping


def _normalize_rebuild_file_entries(previous_meta: dict[str, JsonValue]) -> list[dict[str, JsonValue]]:
    """标准化重建模式下的 meta.files 条目。

    Args:
        previous_meta: 旧 meta 字典。

    Returns:
        规范化后的文件条目列表。

    Raises:
        无。
    """

    indexed_entries = _index_file_entries(previous_meta)
    normalized: list[dict[str, JsonValue]] = []
    for name in sorted(indexed_entries.keys()):
        item = indexed_entries[name]
        normalized.append(
            {
                "name": name,
                "uri": item.get("uri"),
                "etag": item.get("etag"),
                "last_modified": item.get("last_modified"),
                "size": item.get("size"),
                "content_type": item.get("content_type"),
                "sha256": item.get("sha256"),
                "source_url": item.get("source_url"),
                "http_etag": item.get("http_etag"),
                "http_last_modified": item.get("http_last_modified"),
                "ingested_at": item.get("ingested_at") or now_iso8601(),
            }
        )
    return normalized


def _resolve_rebuild_source_fingerprint(
    *,
    previous_meta: dict[str, JsonValue],
    file_entries: list[dict[str, JsonValue]],
) -> str:
    """计算重建模式下的 source_fingerprint。

    Args:
        previous_meta: 旧 meta 字典。
        file_entries: 规范化后的文件条目列表。

    Returns:
        指纹字符串；无法构建时返回空字符串。

    Raises:
        无。
    """

    previous_fingerprint = str(previous_meta.get("source_fingerprint", "")).strip()
    if previous_fingerprint:
        return previous_fingerprint

    descriptors: list[RemoteFileDescriptor] = []
    for item in file_entries:
        name = str(item.get("name", "")).strip()
        if not name:
            continue
        raw_size = item.get("size")
        normalized_size = raw_size if isinstance(raw_size, int) and raw_size >= 0 else None
        descriptors.append(
            RemoteFileDescriptor(
                name=name,
                source_url=str(item.get("source_url", "")).strip(),
                http_etag=str(item.get("http_etag") or item.get("etag") or "").strip() or None,
                http_last_modified=str(
                    item.get("http_last_modified") or item.get("last_modified") or ""
                ).strip()
                or None,
                remote_size=normalized_size,
                http_status=None,
            )
        )
    if not descriptors:
        return ""
    return build_source_fingerprint(descriptors)


def _has_same_file_name_set(
    *,
    remote_files: list[RemoteFileDescriptor],
    existing_files: dict[str, dict[str, JsonValue]],
) -> bool:
    """判断远端与本地已记录文件集合是否一致。

    Args:
        remote_files: 远端文件列表。
        existing_files: 本地已有文件条目映射。

    Returns:
        文件名集合一致时返回 True。

    Raises:
        无。
    """

    if not remote_files or not existing_files:
        return False
    remote_names = {item.name for item in remote_files if item.name}
    existing_names = set(existing_files.keys())
    return bool(remote_names) and remote_names == existing_names


def _remote_files_equivalent_to_previous_meta(
    *,
    previous_meta: Optional[dict[str, JsonValue]],
    remote_files: Optional[list[RemoteFileDescriptor]],
) -> bool:
    """基于文件级 HTTP 元数据判断远端是否等价于已落盘版本。

    Args:
        previous_meta: 历史文档 meta。
        remote_files: 本次远端文件描述列表。

    Returns:
        远端与历史文件等价时返回 True；否则返回 False。

    Raises:
        无。
    """

    if previous_meta is None or not remote_files:
        return False
    previous_files = _index_file_entries(previous_meta)
    if not _has_same_file_name_set(remote_files=remote_files, existing_files=previous_files):
        return False

    for descriptor in remote_files:
        previous = previous_files.get(descriptor.name, {})
        remote_etag = _normalize_compare_etag(descriptor.http_etag)
        previous_etag = _normalize_compare_etag(previous.get("http_etag") or previous.get("etag"))
        if remote_etag and previous_etag:
            if remote_etag != previous_etag:
                return False
            continue

        remote_last_modified = str(descriptor.http_last_modified or "").strip()
        previous_last_modified = str(
            previous.get("http_last_modified") or previous.get("last_modified") or ""
        ).strip()
        if remote_last_modified and previous_last_modified:
            if remote_last_modified != previous_last_modified:
                return False
            continue

        remote_size = descriptor.remote_size
        previous_size = previous.get("size")
        if isinstance(remote_size, int) and remote_size >= 0 and isinstance(previous_size, int) and previous_size >= 0:
            if remote_size != previous_size:
                return False

    return True


def _normalize_compare_etag(raw_etag: JsonValue) -> str:
    """标准化 ETag 用于稳定比较。

    Args:
        raw_etag: 原始 ETag。

    Returns:
        标准化后的 ETag；无有效值时返回空字符串。

    Raises:
        无。
    """

    normalized = str(raw_etag or "").strip()
    if not normalized:
        return ""
    if normalized.upper().startswith("W/"):
        normalized = normalized[2:].strip()
    if normalized.startswith('"') and normalized.endswith('"') and len(normalized) >= 2:
        normalized = normalized[1:-1]
    lowered = normalized.lower()
    if lowered.endswith("-gzip"):
        lowered = lowered[: -len("-gzip")]
    return lowered.strip()
