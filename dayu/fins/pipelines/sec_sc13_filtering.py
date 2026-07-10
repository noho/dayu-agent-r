"""SEC SC13 过滤与补拉工作流真源。"""

from __future__ import annotations

from dayu.contracts.json_value import JsonValue

import datetime as dt
import inspect
from collections.abc import Mapping
from pathlib import Path
from typing import Awaitable, Callable, Optional, Protocol, Sequence, TypeVar

from dayu.fins.downloaders.sec_downloader import (
    BrowseEdgarFiling,
    RemoteFileDescriptor,
    Sc13PartyRoles,
    SecDownloadCancelledError,
    accession_to_no_dash,
    build_source_fingerprint,
)
from dayu.fins.domain.filing_semantics import normalize_sec_form_type_for_matching
from dayu.fins._log import Log

from .sec_download_state import (
    _SEC_CACHE_CATEGORY_BROWSE_EDGAR,
    _browse_edgar_filings_to_dicts,
    _dicts_to_browse_edgar_filings,
    _is_rejected as _is_rejected_impl,
    _read_sec_cache,
    _read_sec_cache_async,
    _record_rejection as _record_rejection_impl,
    _write_sec_cache,
    _write_sec_cache_async,
)

SC13_FORMS = frozenset({"SC 13D", "SC 13D/A", "SC 13G", "SC 13G/A"})
SC13_RETRY_MAX = 2
SC13_RETRY_EXPAND_YEARS = 1


def _browse_cache_rows(value: JsonValue | None) -> list[dict[str, str]]:
    """将 browse-edgar cache JSON 收窄为字符串字典列表。

    Args:
        value: cache 中读取的 JSON 值。

    Returns:
        字符串字典列表；非列表或非对象元素会被忽略。

    Raises:
        无。
    """

    if not isinstance(value, list):
        return []
    rows: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        rows.append({key: str(raw_value) for key, raw_value in item.items()})
    return rows

_AwaitableResult = TypeVar("_AwaitableResult")


class Sc13FilingRecordProtocol(Protocol):
    """SC13 工作流依赖的 filing 记录最小视图。"""

    @property
    def form_type(self) -> str:
        """返回 filing form 类型。"""

        ...

    @property
    def filing_date(self) -> str:
        """返回 filing 日期。"""

        ...

    @property
    def report_date(self) -> Optional[str]:
        """返回 report date。"""

        ...

    @property
    def accession_number(self) -> str:
        """返回 accession。"""

        ...

    @property
    def primary_document(self) -> str:
        """返回主文档名。"""

        ...

    @property
    def filer_key(self) -> Optional[str]:
        """返回 filer key。"""

        ...


class _Sc13WorkflowDownloader(Protocol):
    """SC13 工作流所需的最小下载器边界。"""

    def fetch_browse_edgar_filenum(
        self,
        filenum: str,
        count: int = 100,
        cancellation_checker: Optional[Callable[[], bool]] = None,
    ) -> Awaitable[list[BrowseEdgarFiling]] | list[BrowseEdgarFiling]:
        """按 filenum 拉取 browse-edgar 记录。"""

        ...

    def resolve_primary_document(
        self,
        *,
        cik: str,
        accession_no_dash: str,
        form_type: str,
        cancellation_checker: Optional[Callable[[], bool]] = None,
    ) -> Awaitable[str] | str:
        """解析 filing 的 primary document。"""

        ...

    def fetch_sc13_party_roles(
        self,
        *,
        archive_cik: str,
        accession_number: str,
        cancellation_checker: Optional[Callable[[], bool]] = None,
    ) -> Awaitable[Optional[Sc13PartyRoles]] | Optional[Sc13PartyRoles]:
        """解析 SC13 双方角色。"""

        ...

    def list_filing_files(
        self,
        *,
        cik: str,
        accession_no_dash: str,
        primary_document: str,
        form_type: str,
        include_xbrl: bool,
        include_exhibits: bool,
        include_http_metadata: bool,
        cancellation_checker: Optional[Callable[[], bool]] = None,
    ) -> Awaitable[list[RemoteFileDescriptor]] | list[RemoteFileDescriptor]:
        """列出 filing 远端文件。"""

        ...


class SecSc13WorkflowHost(Protocol):
    """SC13 工作流所需的最小宿主边界。"""

    @property
    def MODULE(self) -> str:
        """返回日志模块名。"""

        ...

    @property
    def _workspace_root(self) -> Path:
        """返回工作区根目录。"""

        ...

    @property
    def _downloader(self) -> _Sc13WorkflowDownloader:
        """返回下载器实例。"""

        ...

    def _filter_filings(
        self,
        ticker: str,
        submissions: dict[str, JsonValue],
        form_windows: dict[str, dt.date],
        end_date: dt.date,
        target_cik: str,
        sc13_direction_cache: Optional[dict[str, Optional[bool]]] = None,
        rejection_registry: Optional[dict[str, dict[str, str]]] = None,
        overwrite: bool = False,
        cancel_checker: Optional[Callable[[], bool]] = None,
    ) -> Awaitable[tuple[Sequence[Sc13FilingRecordProtocol], set[str]]]:
        """重新过滤 filings。"""

        ...

    def _extend_with_browse_edgar_sc13(
        self,
        ticker: str,
        filings: Sequence[Sc13FilingRecordProtocol],
        filenums: set[str],
        form_windows: dict[str, dt.date],
        end_date: dt.date,
        target_cik: str,
        sc13_direction_cache: Optional[dict[str, Optional[bool]]] = None,
        rejection_registry: Optional[dict[str, dict[str, str]]] = None,
        overwrite: bool = False,
        cancel_checker: Optional[Callable[[], bool]] = None,
    ) -> Awaitable[Sequence[Sc13FilingRecordProtocol]]:
        """补拉 browse-edgar SC13。"""

        ...

    def _should_keep_sc13_direction(
        self,
        ticker: str,
        filing: Sc13FilingRecordProtocol,
        archive_cik: str,
        target_cik: str,
        sc13_direction_cache: Optional[dict[str, Optional[bool]]] = None,
        rejection_registry: Optional[dict[str, dict[str, str]]] = None,
        overwrite: bool = False,
        cancel_checker: Optional[Callable[[], bool]] = None,
    ) -> Awaitable[bool]:
        """判断单条 SC13 是否应保留。"""

        ...

    def _persist_rejected_filing_artifact(
        self,
        ticker: str,
        cik: str,
        filing: Sc13FilingRecordProtocol,
        remote_files: list[RemoteFileDescriptor],
        overwrite: bool,
        rejection_reason: str,
        rejection_category: str,
        selected_primary_document: str,
        source_fingerprint: Optional[str],
        cancel_checker: Optional[Callable[[], bool]] = None,
    ) -> Awaitable[tuple[bool, Optional[str]]] | tuple[bool, Optional[str]]:
        """持久化 rejected artifact。"""

        ...


async def _maybe_await(value: Awaitable[_AwaitableResult] | _AwaitableResult) -> _AwaitableResult:
    """按需等待可等待对象。"""

    if inspect.isawaitable(value):
        return await value
    return value


def should_warn_missing_sc13(
    form_windows: dict[str, dt.date],
    filings: Sequence[Sc13FilingRecordProtocol],
) -> bool:
    """判断是否需要提示 SC13 缺失。"""

    if not SC13_FORMS.intersection(form_windows.keys()):
        return False
    return not any(item.form_type in SC13_FORMS for item in filings)


def keep_latest_sc13_per_filer(
    filings: Sequence[Sc13FilingRecordProtocol],
) -> list[Sc13FilingRecordProtocol]:
    """同一申报主体仅保留最新一份 SC13。"""

    if not filings:
        return []

    non_sc13_records: list[Sc13FilingRecordProtocol] = []
    latest_sc13_by_filer: dict[str, Sc13FilingRecordProtocol] = {}
    for filing in filings:
        if filing.form_type not in SC13_FORMS:
            non_sc13_records.append(filing)
            continue
        raw_filer_key = str(filing.filer_key or "").strip()
        filer_key = raw_filer_key or f"ACC:{filing.accession_number}"
        existing = latest_sc13_by_filer.get(filer_key)
        if existing is None:
            latest_sc13_by_filer[filer_key] = filing
            continue
        if (filing.filing_date, filing.accession_number) > (
            existing.filing_date,
            existing.accession_number,
        ):
            latest_sc13_by_filer[filer_key] = filing

    merged = non_sc13_records + list(latest_sc13_by_filer.values())
    return sorted(
        merged,
        key=lambda item: (item.filing_date, item.form_type, item.accession_number),
    )


def normalize_cik_for_compare(raw_cik: JsonValue) -> Optional[str]:
    """把 CIK 规范化成可比较的纯数字字符串。"""

    text = str(raw_cik).strip()
    if not text:
        return None
    digits = "".join(ch for ch in text if ch.isdigit())
    if not digits:
        return None
    return digits.lstrip("0") or "0"


def evaluate_sc13_direction(
    *,
    module: str,
    filing: Sc13FilingRecordProtocol,
    roles: Optional[Sc13PartyRoles],
    target_cik: str,
) -> bool:
    """计算 SC13 是否满足“别人持股我”的方向规则。"""

    target_cik_normalized = normalize_cik_for_compare(target_cik)
    if roles is None:
        Log.debug(
            (
                "SC13 方向不可判定，按策略跳过: "
                f"accession={filing.accession_number} form={filing.form_type}"
            ),
            module=module,
        )
        return False
    filed_by_cik_normalized = normalize_cik_for_compare(roles.filed_by_cik)
    subject_cik_normalized = normalize_cik_for_compare(roles.subject_cik)
    if (
        target_cik_normalized is None
        or filed_by_cik_normalized is None
        or subject_cik_normalized is None
    ):
        Log.warn(
            (
                "SC13 CIK 字段非法，按策略跳过: "
                f"accession={filing.accession_number} "
                f"filed_by={roles.filed_by_cik} subject={roles.subject_cik} target={target_cik}"
            ),
            module=module,
        )
        return False
    if subject_cik_normalized != target_cik_normalized:
        Log.debug(
            (
                "SC13 方向过滤（subject!=ticker）: "
                f"accession={filing.accession_number} subject={subject_cik_normalized} "
                f"target={target_cik_normalized}"
            ),
            module=module,
        )
        return False
    if filed_by_cik_normalized == target_cik_normalized:
        Log.debug(
            (
                "SC13 方向过滤（ticker 持股他人）: "
                f"accession={filing.accession_number} filed_by={filed_by_cik_normalized} "
                f"target={target_cik_normalized}"
            ),
            module=module,
        )
        return False
    return True


async def filter_sc13_by_direction(
    host: SecSc13WorkflowHost,
    *,
    ticker: str,
    filings: Sequence[Sc13FilingRecordProtocol],
    target_cik: str,
    archive_cik: str,
    sc13_direction_cache: Optional[dict[str, Optional[bool]]] = None,
    rejection_registry: Optional[dict[str, dict[str, str]]] = None,
    overwrite: bool = False,
    cancel_checker: Optional[Callable[[], bool]] = None,
) -> list[Sc13FilingRecordProtocol]:
    """按 SC13 方向规则过滤 filings。"""

    if not filings:
        return []
    filtered: list[Sc13FilingRecordProtocol] = []
    for filing in filings:
        if filing.form_type not in SC13_FORMS:
            filtered.append(filing)
            continue
        keep = await host._should_keep_sc13_direction(
            ticker=ticker,
            filing=filing,
            archive_cik=archive_cik,
            target_cik=target_cik,
            sc13_direction_cache=sc13_direction_cache,
            rejection_registry=rejection_registry,
            overwrite=overwrite,
            cancel_checker=cancel_checker,
        )
        if keep:
            filtered.append(filing)
    return filtered


async def should_keep_sc13_direction(
    host: SecSc13WorkflowHost,
    *,
    ticker: str,
    filing: Sc13FilingRecordProtocol,
    archive_cik: str,
    target_cik: str,
    download_version: str,
    sc13_direction_cache: Optional[dict[str, Optional[bool]]] = None,
    rejection_registry: Optional[dict[str, dict[str, str]]] = None,
    overwrite: bool = False,
    cancel_checker: Optional[Callable[[], bool]] = None,
) -> bool:
    """判断单条 SC13 是否应保留。"""

    if filing.form_type not in SC13_FORMS:
        return True
    document_id = f"fil_{filing.accession_number}"
    effective_registry = rejection_registry if rejection_registry is not None else {}
    if _is_rejected_impl(
        registry=effective_registry,
        document_id=document_id,
        overwrite=overwrite,
        download_version=download_version,
    ):
        Log.debug(
            f"SC13 拒绝注册表跳过: accession={filing.accession_number}",
            module=host.MODULE,
        )
        if sc13_direction_cache is not None:
            sc13_direction_cache[filing.accession_number] = False
        return False
    cache_key = filing.accession_number
    if sc13_direction_cache is not None and cache_key in sc13_direction_cache:
        cached_result = sc13_direction_cache[cache_key]
        return bool(cached_result)
    roles = await _maybe_await(
        host._downloader.fetch_sc13_party_roles(
            archive_cik=archive_cik,
            accession_number=filing.accession_number,
            cancellation_checker=cancel_checker,
        )
    )
    keep = evaluate_sc13_direction(
        module=host.MODULE,
        filing=filing,
        roles=roles,
        target_cik=target_cik,
    )
    if sc13_direction_cache is not None:
        sc13_direction_cache[cache_key] = keep
    if not keep and rejection_registry is not None:
        accession_no_dash = accession_to_no_dash(filing.accession_number)
        try:
            remote_files = await _maybe_await(
                host._downloader.list_filing_files(
                    cik=archive_cik,
                    accession_no_dash=accession_no_dash,
                    primary_document=filing.primary_document,
                    form_type=filing.form_type,
                    include_xbrl=True,
                    include_exhibits=True,
                    include_http_metadata=True,
                    cancellation_checker=cancel_checker,
                )
            )
        except SecDownloadCancelledError:
            raise
        except RuntimeError as exc:
            Log.warn(
                (
                    "SC13 reject artifact 预拉取失败，仅写 registry: "
                    f"ticker={ticker} accession={filing.accession_number} error={exc}"
                ),
                module=host.MODULE,
            )
        else:
            source_fingerprint = build_source_fingerprint(remote_files)
            artifact_saved, artifact_error = await _maybe_await(
                host._persist_rejected_filing_artifact(
                    ticker=ticker,
                    cik=archive_cik,
                    filing=filing,
                    remote_files=remote_files,
                    overwrite=overwrite,
                    rejection_reason="sc13_direction_rejected",
                    rejection_category="direction_mismatch",
                    selected_primary_document=filing.primary_document,
                    source_fingerprint=source_fingerprint,
                    cancel_checker=cancel_checker,
                )
            )
            if not artifact_saved:
                Log.warn(
                    (
                        "SC13 reject artifact 落盘失败，仅写 registry: "
                        f"ticker={ticker} accession={filing.accession_number} error={artifact_error}"
                    ),
                    module=host.MODULE,
                )
        _record_rejection_impl(
            registry=rejection_registry,
            document_id=document_id,
            reason="sc13_direction_rejected",
            category="direction_mismatch",
            form_type=filing.form_type,
            filing_date=filing.filing_date,
            download_version=download_version,
        )
    return keep


async def extend_with_browse_edgar_sc13(
    host: SecSc13WorkflowHost,
    *,
    ticker: str,
    filings: Sequence[Sc13FilingRecordProtocol],
    filenums: set[str],
    form_windows: dict[str, dt.date],
    end_date: dt.date,
    target_cik: str,
    parse_date: Callable[[str, bool], dt.date],
    create_filing_record: Callable[[str, str, Optional[str], str, str, Optional[str]], Sc13FilingRecordProtocol],
    sc13_direction_cache: Optional[dict[str, Optional[bool]]] = None,
    rejection_registry: Optional[dict[str, dict[str, str]]] = None,
    overwrite: bool = False,
    cancel_checker: Optional[Callable[[], bool]] = None,
) -> list[Sc13FilingRecordProtocol]:
    """通过 browse-edgar 补齐 SC13。"""

    if not SC13_FORMS.intersection(form_windows.keys()):
        return list(filings)
    candidate_filenums = [item for item in sorted(filenums) if item.startswith("005-")]
    if not candidate_filenums:
        return list(filings)
    records = {item.accession_number: item for item in filings}
    for filenum in candidate_filenums:
        cached_data = await _read_sec_cache_async(
            host._workspace_root,
            _SEC_CACHE_CATEGORY_BROWSE_EDGAR,
            filenum,
        )
        if cached_data is not None:
            entries = _dicts_to_browse_edgar_filings(_browse_cache_rows(cached_data))
        else:
            try:
                entries = await _maybe_await(
                    host._downloader.fetch_browse_edgar_filenum(
                        filenum,
                        cancellation_checker=cancel_checker,
                    )
                )
            except SecDownloadCancelledError:
                raise
            except RuntimeError as exc:
                Log.warn(f"browse-edgar 拉取失败: filenum={filenum} error={exc}", module=host.MODULE)
                continue
            await _write_sec_cache_async(
                host._workspace_root,
                _SEC_CACHE_CATEGORY_BROWSE_EDGAR,
                filenum,
                _browse_edgar_filings_to_dicts(entries),
            )
        for entry in entries:
            normalized_form = normalize_sec_form_type_for_matching(entry.form_type)
            if normalized_form is None:
                continue
            if normalized_form not in form_windows:
                continue
            try:
                filing_date_value = parse_date(entry.filing_date, False)
            except ValueError:
                continue
            if filing_date_value < form_windows[normalized_form] or filing_date_value > end_date:
                continue
            if entry.accession_number in records:
                continue
            if normalized_form in SC13_FORMS:
                pending_record = create_filing_record(
                    normalized_form,
                    filing_date_value.isoformat(),
                    None,
                    entry.accession_number,
                    "",
                    filenum,
                )
                keep_direction = await host._should_keep_sc13_direction(
                    ticker=ticker,
                    filing=pending_record,
                    archive_cik=entry.cik,
                    target_cik=target_cik,
                    sc13_direction_cache=sc13_direction_cache,
                    rejection_registry=rejection_registry,
                    overwrite=overwrite,
                    cancel_checker=cancel_checker,
                )
                if not keep_direction:
                    continue
            accession_no_dash = accession_to_no_dash(entry.accession_number)
            try:
                primary_document = await _maybe_await(
                    host._downloader.resolve_primary_document(
                        cik=entry.cik,
                        accession_no_dash=accession_no_dash,
                        form_type=normalized_form,
                        cancellation_checker=cancel_checker,
                    )
                )
            except SecDownloadCancelledError:
                raise
            except RuntimeError as exc:
                Log.warn(
                    (
                        "browse-edgar primary_document 解析失败: "
                        f"filenum={filenum} accession={entry.accession_number} error={exc}"
                    ),
                    module=host.MODULE,
                )
                continue
            records[entry.accession_number] = create_filing_record(
                normalized_form,
                filing_date_value.isoformat(),
                None,
                entry.accession_number,
                primary_document,
                filenum,
            )
    merged = sorted(
        records.values(),
        key=lambda item: (item.filing_date, item.form_type, item.accession_number),
    )
    return keep_latest_sc13_per_filer(merged)


async def retry_sc13_if_empty(
    host: SecSc13WorkflowHost,
    *,
    ticker: str,
    filings: Sequence[Sc13FilingRecordProtocol],
    filenums: set[str],
    submissions: dict[str, JsonValue],
    form_windows: dict[str, dt.date],
    end_date: dt.date,
    target_cik: str,
    sc13_direction_cache: Optional[dict[str, Optional[bool]]] = None,
    rejection_registry: Optional[dict[str, dict[str, str]]] = None,
    overwrite: bool = False,
    cancel_checker: Optional[Callable[[], bool]] = None,
) -> list[Sc13FilingRecordProtocol]:
    """在 SC13 初始为空时逐次扩大窗口重试。"""

    requested_sc13 = SC13_FORMS.intersection(form_windows.keys())
    if not requested_sc13:
        return list(filings)

    for retry in range(1, SC13_RETRY_MAX + 1):
        if any(item.form_type in SC13_FORMS for item in filings):
            return list(filings)

        expand = dt.timedelta(days=365 * SC13_RETRY_EXPAND_YEARS)
        for form in requested_sc13:
            form_windows[form] = form_windows[form] - expand
        Log.info(
            (
                f"SC 13 渐进式回溯: 第{retry}次重试，"
                f"SC 13 窗口扩大至 "
                f"{ {k: v.isoformat() for k, v in form_windows.items() if k in SC13_FORMS} }"
            ),
            module=host.MODULE,
        )

        filings, filenums = await host._filter_filings(
            ticker=ticker,
            submissions=submissions,
            form_windows=form_windows,
            end_date=end_date,
            target_cik=target_cik,
            sc13_direction_cache=sc13_direction_cache,
            rejection_registry=rejection_registry,
            overwrite=overwrite,
            cancel_checker=cancel_checker,
        )
        filings = await host._extend_with_browse_edgar_sc13(
            ticker=ticker,
            filings=filings,
            filenums=filenums,
            form_windows=form_windows,
            end_date=end_date,
            target_cik=target_cik,
            sc13_direction_cache=sc13_direction_cache,
            rejection_registry=rejection_registry,
            overwrite=overwrite,
            cancel_checker=cancel_checker,
        )

    return list(filings)


__all__ = [
    "SC13_FORMS",
    "SC13_RETRY_EXPAND_YEARS",
    "SC13_RETRY_MAX",
    "SecSc13WorkflowHost",
    "Sc13FilingRecordProtocol",
    "evaluate_sc13_direction",
    "extend_with_browse_edgar_sc13",
    "filter_sc13_by_direction",
    "keep_latest_sc13_per_filer",
    "normalize_cik_for_compare",
    "retry_sc13_if_empty",
    "should_keep_sc13_direction",
    "should_warn_missing_sc13",
]
