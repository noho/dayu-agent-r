"""SEC filing 收集与解析工具集。

包含 FilingRecord 数据类、submissions 表解析，
以及 6-K 远端候选分类协调。
"""

from __future__ import annotations

from dayu.contracts.json_value import JsonValue

import datetime as dt
import inspect
from dataclasses import dataclass
from collections.abc import Callable
from typing import Awaitable, Optional, TypeVar

from dayu.fins.downloaders.sec_downloader import RemoteFileDescriptor, SecDownloader
from dayu.fins.pipelines.sec_6k_rules import (
    _SixKCandidateDiagnosis,
    _classify_6k_text,
    _collect_6k_candidate_entries,
    _extract_head_text,
    _score_6k_filename,
)
from dayu.fins.pipelines.sec_form_utils import normalize_form, parse_date
from dayu.fins._log import Log


# ---------- 数据类 ----------


@dataclass(frozen=True)
class FilingRecord:
    """SEC filing 记录。"""

    form_type: str
    filing_date: str
    report_date: Optional[str]
    accession_number: str
    primary_document: str
    filer_key: Optional[str] = None


# ---------- 辅助 ----------


_AwaitableResult = TypeVar("_AwaitableResult")


async def _maybe_await(value: Awaitable[_AwaitableResult] | _AwaitableResult) -> _AwaitableResult:
    """按需等待可等待对象。"""

    if inspect.isawaitable(value):
        return await value
    return value


def _json_list(value: JsonValue | None) -> list[JsonValue]:
    """将 submissions 字段收窄成 JSON 数组。

    Args:
        value: 原始字段值。

    Returns:
        JSON 数组；非数组返回空列表。

    Raises:
        无。
    """

    if isinstance(value, list):
        return value
    return []


# ---------- 函数 ----------


def collect_filings_from_table(
    records: dict[str, FilingRecord],
    table: dict[str, JsonValue],
    form_windows: dict[str, dt.date],
    end_date: dt.date,
) -> None:
    """从 submissions 表结构中收集 filings。

    Args:
        records: 输出收集字典（按 accession 去重）。
        table: ``filings.recent`` 或历史文件内容。
        form_windows: form 到起始日期映射。
        end_date: 结束日期。

    Returns:
        无。

    Raises:
        ValueError: 日期字段解析失败时抛出。
    """

    forms = _json_list(table.get("form"))
    filing_dates = _json_list(table.get("filingDate"))
    report_dates = _json_list(table.get("reportDate"))
    accessions = _json_list(table.get("accessionNumber"))
    primary_documents = _json_list(table.get("primaryDocument"))
    file_numbers = _json_list(table.get("fileNumber"))
    row_count = min(len(forms), len(filing_dates), len(accessions), len(primary_documents))
    for index in range(row_count):
        normalized_form = normalize_form(str(forms[index]))
        if normalized_form not in form_windows:
            continue
        filing_date_value = parse_date(str(filing_dates[index]), is_end=False)
        if filing_date_value < form_windows[normalized_form] or filing_date_value > end_date:
            continue
        accession_number = str(accessions[index]).strip()
        if not accession_number:
            continue
        report_date = str(report_dates[index]).strip() if index < len(report_dates) else ""
        filer_key = str(file_numbers[index]).strip() if index < len(file_numbers) else ""
        records[accession_number] = FilingRecord(
            form_type=normalized_form,
            filing_date=filing_date_value.isoformat(),
            report_date=report_date or None,
            accession_number=accession_number,
            primary_document=str(primary_documents[index]).strip(),
            filer_key=filer_key or None,
        )


def collect_filenums_from_table(filenums: set[str], table: dict[str, JsonValue]) -> None:
    """从 submissions 表收集 filenum。

    Args:
        filenums: filenum 集合。
        table: submissions 表结构。

    Returns:
        无。

    Raises:
        无。
    """

    values = _json_list(table.get("fileNumber"))
    for item in values:
        filenum = str(item).strip()
        if filenum:
            filenums.add(filenum)


async def classify_6k_remote_candidates(
    remote_files: list[RemoteFileDescriptor],
    primary_document: str,
    downloader: SecDownloader,
    *,
    max_lines: int,
    cancellation_checker: Callable[[], bool] | None = None,
) -> list[_SixKCandidateDiagnosis]:
    """对 6-K 远端候选文件逐个下载头部并重跑真源分类。

    Args:
        remote_files: 远端文件描述列表。
        primary_document: 当前主文件名。
        downloader: SEC 下载器。
        max_lines: 头部文本最大行数。
        cancellation_checker: 可选协作式取消检查器。

    Returns:
        成功完成分类的候选结果列表。

    Raises:
        RuntimeError: 下载候选文件失败时抛出。
        SecDownloadCancelledError: 取消检查点观察到取消请求时抛出。
    """

    descriptor_by_name = {
        item.name.lower(): item for item in remote_files if str(item.name).strip()
    }
    candidate_entries = _collect_6k_candidate_entries(
        [
            {
                "name": item.name,
                "sec_document_type": item.sec_document_type,
            }
            for item in remote_files
        ],
        primary_document,
    )
    normalized_primary = str(primary_document).strip().lower()
    diagnoses: list[_SixKCandidateDiagnosis] = []
    for candidate_name, candidate_type in candidate_entries:
        descriptor = descriptor_by_name.get(candidate_name.lower())
        if descriptor is None:
            continue
        payload = await _maybe_await(
            downloader.fetch_file_bytes(
                descriptor.source_url,
                cancellation_checker=cancellation_checker,
            )
        )
        head_text = _extract_head_text(payload, max_lines=max_lines)
        diagnoses.append(
            _SixKCandidateDiagnosis(
                filename=candidate_name,
                filename_priority=_score_6k_filename(
                    filename=candidate_name,
                    primary_document=primary_document,
                    sec_document_type=candidate_type,
                )[0],
                classification=_classify_6k_text(head_text),
                is_primary_document=bool(normalized_primary)
                and candidate_name.lower() == normalized_primary,
            )
        )
    return diagnoses
