"""SEC fiscal 字段解析真源模块。"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional, Protocol, runtime_checkable

from dayu.contracts.json_value import JsonValue
from dayu.fins.domain.document_models import SourceHandle
from dayu.fins.domain.enums import SourceKind
from dayu.fins.domain.filing_semantics import (
    DocumentQuality,
    normalize_fiscal_period,
    normalize_sec_form_type_for_matching,
    sanitize_fiscal_period_by_sec_form,
)
from dayu.fins.domain.xbrl_result_contract import (
    XbrlFactsPayload,
    validate_xbrl_facts_result_payload,
)
from dayu.fins.storage import SourceDocumentRepositoryProtocol
from dayu.fins.storage.repository_protocols import SourceSnapshotProtocol

from .sec_6k_rules import _infer_filename_from_uri


FINANCIAL_STATEMENT_TYPES = (
    "income",
    "balance_sheet",
    "cash_flow",
    "equity",
    "comprehensive_income",
)
FINANCIAL_EXTRACTION_SKIP_FORMS = frozenset({"8-K", "8-K/A", "DEF 14A"})
_XBRL_LINKBASE_FILE_SUFFIXES = ("_pre.xml", "_cal.xml", "_def.xml", "_lab.xml")
_DOWNLOAD_DEI_FISCAL_YEAR_KEYS = (
    "document_fiscal_year_focus",
    "documentfiscalyearfocus",
    "dei:documentfiscalyearfocus",
)
_DOWNLOAD_DEI_FISCAL_PERIOD_KEYS = (
    "document_fiscal_period_focus",
    "documentfiscalperiodfocus",
    "dei:documentfiscalperiodfocus",
)


@runtime_checkable
class _XbrlQueryProcessor(Protocol):
    """可查询 XBRL facts 的处理器边界。"""

    def query_xbrl_facts(self, *, concepts: list[str]) -> XbrlFactsPayload:
        """查询 XBRL facts。

        Args:
            concepts: 待查询 concept 列表。

        Returns:
            XBRL 查询结果。

        Raises:
            处理器内部异常原样抛出。
        """

        ...

def _resolve_processed_quality(
    has_xbrl: bool,
    financial_capable: bool,
    form_type: Optional[str] = None,
) -> DocumentQuality:
    """根据处理结果计算 processed 文档质量等级。

    Args:
        has_xbrl: 当前处理结果是否包含 XBRL 能力。
        financial_capable: 当前处理结果是否至少具备财务表格能力。
        form_type: 原始或 canonical SEC form。

    Returns:
        domain 认可的文档质量值。

    Raises:
        无。
    """

    normalized_form_type = normalize_sec_form_type_for_matching(form_type)
    if normalized_form_type == "DEF 14A":
        return "partial"
    if has_xbrl:
        return "full"
    if financial_capable:
        return "partial"
    return "fallback"


def _resolve_processed_fiscal_fields(
    source_meta: dict[str, JsonValue],
    financials_payload: Optional[dict[str, JsonValue]],
    processor: _XbrlQueryProcessor | None,
    allow_xbrl_query: bool = True,
) -> tuple[Optional[int], Optional[str]]:
    """解析 processed 元数据中的 fiscal_year/fiscal_period。"""

    source_fiscal_year = _coerce_optional_int(source_meta.get("fiscal_year"))
    source_fiscal_period = _normalize_optional_period(source_meta.get("fiscal_period"))
    normalized_form_type = normalize_sec_form_type_for_matching(_normalize_optional_string(source_meta.get("form_type")))
    if source_fiscal_period is not None:
        source_fiscal_period = _sanitize_fiscal_period_by_form(
            form_type=normalized_form_type,
            fiscal_period=source_fiscal_period,
        )
    if source_fiscal_year is not None and source_fiscal_period is not None:
        return source_fiscal_year, source_fiscal_period

    if allow_xbrl_query:
        query_fiscal_year, query_fiscal_period = _extract_fiscal_from_xbrl_query(processor)
    else:
        query_fiscal_year, query_fiscal_period = None, None
    if query_fiscal_period is not None:
        query_fiscal_period = _sanitize_fiscal_period_by_form(
            form_type=normalized_form_type,
            fiscal_period=query_fiscal_period,
        )

    payload_fiscal_year, payload_fiscal_period = _extract_fiscal_from_financials(financials_payload)
    if payload_fiscal_period is not None:
        payload_fiscal_period = _sanitize_fiscal_period_by_form(
            form_type=normalized_form_type,
            fiscal_period=payload_fiscal_period,
        )
    resolved_year_candidate = query_fiscal_year if query_fiscal_year is not None else payload_fiscal_year
    resolved_period_candidate = query_fiscal_period if query_fiscal_period is not None else payload_fiscal_period
    fiscal_year = source_fiscal_year if source_fiscal_year is not None else resolved_year_candidate
    fiscal_period = source_fiscal_period if source_fiscal_period is not None else resolved_period_candidate

    fiscal_year_from_report_date = False
    if fiscal_year is None:
        fiscal_year = _coerce_year_from_date(source_meta.get("report_date"))
        fiscal_year_from_report_date = fiscal_year is not None
    if fiscal_period is None:
        fiscal_period = _resolve_fiscal_period_fallback(
            form_type=normalized_form_type,
            fiscal_year=fiscal_year,
            fiscal_year_from_report_date=fiscal_year_from_report_date,
        )
    return fiscal_year, fiscal_period


def _resolve_download_fiscal_fields(
    *,
    source_handle: SourceHandle,
    source_repository: SourceDocumentRepositoryProtocol,
    file_entries: list[dict[str, JsonValue]],
    form_type: Optional[str],
    report_date: Optional[str],
) -> tuple[Optional[int], Optional[str]]:
    """解析 download 阶段应写入 source meta 的 fiscal 字段。"""

    dei_year, dei_period = _extract_download_fiscal_from_xbrl(
        source_handle=source_handle,
        source_repository=source_repository,
        file_entries=file_entries,
        form_type=form_type,
    )
    fallback_year, fallback_period = _infer_download_fiscal_fields(form_type=form_type, report_date=report_date)
    if dei_year is None and dei_period is None:
        return fallback_year, fallback_period

    resolved_year = dei_year if dei_year is not None else fallback_year
    normalized_form_type = normalize_sec_form_type_for_matching(form_type)
    if dei_period is not None:
        return resolved_year, dei_period
    if dei_year is None:
        return resolved_year, fallback_period
    if normalized_form_type in {"10-K", "20-F"}:
        return resolved_year, fallback_period
    return resolved_year, None


def _extract_download_fiscal_from_xbrl(
    *,
    source_handle: SourceHandle,
    source_repository: SourceDocumentRepositoryProtocol,
    file_entries: list[dict[str, JsonValue]],
    form_type: Optional[str],
) -> tuple[Optional[int], Optional[str]]:
    """从一份已发布 source snapshot 抽取 fiscal_year/fiscal_period。

    Args:
        source_handle: 指向已发布 source 的精确业务身份。
        source_repository: 提供原子 snapshot 的 source 仓储协议。
        file_entries: 当前下载描述符顺序下的完整业务文件条目。
        form_type: 当前 SEC form type。

    Returns:
        可选 fiscal year 与 fiscal period；snapshot 或 XBRL 不可用时返回空值。

    Raises:
        无；沿用 download fiscal 的 best-effort 语义吸收读取与解析失败。
    """

    try:
        snapshot = source_repository.read_source_snapshot(
            source_handle.ticker,
            source_handle.document_id,
            SourceKind(source_handle.source_kind),
            materialize_files=True,
        )
    except Exception:
        return None, None
    with snapshot:
        return _extract_download_fiscal_from_snapshot(
            snapshot=snapshot,
            file_entries=file_entries,
            form_type=form_type,
        )


def _extract_download_fiscal_from_snapshot(
    *,
    snapshot: SourceSnapshotProtocol,
    file_entries: list[dict[str, JsonValue]],
    form_type: Optional[str],
) -> tuple[Optional[int], Optional[str]]:
    """从一份 full snapshot 的同版 XBRL 文件组提取 fiscal 字段。

    Args:
        snapshot: storage owner 返回的 full source snapshot。
        file_entries: 当前下载描述符顺序下的业务文件条目。
        form_type: 当前 SEC form type。

    Returns:
        可选 fiscal year 与 fiscal period。

    Raises:
        RuntimeError: snapshot 已关闭或未物化文件时抛出。
    """

    local_file_map = _build_download_local_file_map(
        snapshot=snapshot,
        file_entries=file_entries,
    )
    if not local_file_map:
        return None, None

    instance_file = _pick_download_xbrl_file(local_file_map, candidates=("_htm.xml", "_ins.xml"), xml_fallback=True)
    schema_file = _pick_download_xbrl_file(local_file_map, candidates=(".xsd",))
    if instance_file is None or schema_file is None:
        return None, None

    presentation_file = _pick_download_xbrl_file(local_file_map, candidates=("_pre.xml",))
    calculation_file = _pick_download_xbrl_file(local_file_map, candidates=("_cal.xml",))
    definition_file = _pick_download_xbrl_file(local_file_map, candidates=("_def.xml",))
    label_file = _pick_download_xbrl_file(local_file_map, candidates=("_lab.xml",))

    try:
        from edgar.xbrl import XBRL
    except Exception:
        return None, None

    try:
        xbrl = XBRL.from_files(
            instance_file=instance_file,
            schema_file=schema_file,
            presentation_file=presentation_file,
            calculation_file=calculation_file,
            definition_file=definition_file,
            label_file=label_file,
        )
    except Exception:
        return None, None

    entity_info = getattr(xbrl, "entity_info", None)
    raw_year = _pick_first_non_empty(
        (
            getattr(xbrl, "fiscal_year", None),
            _mapping_get_case_insensitive(entity_info, _DOWNLOAD_DEI_FISCAL_YEAR_KEYS),
        )
    )
    raw_period = _pick_first_non_empty(
        (
            getattr(xbrl, "fiscal_period", None),
            _mapping_get_case_insensitive(entity_info, _DOWNLOAD_DEI_FISCAL_PERIOD_KEYS),
        )
    )
    fiscal_year = _coerce_optional_int(raw_year)
    fiscal_period = _normalize_optional_period(raw_period)
    if fiscal_period is not None:
        fiscal_period = _sanitize_fiscal_period_by_form(
            form_type=normalize_sec_form_type_for_matching(form_type),
            fiscal_period=fiscal_period,
        )
    return fiscal_year, fiscal_period


def _build_download_local_file_map(
    *,
    snapshot: SourceSnapshotProtocol,
    file_entries: list[dict[str, JsonValue]],
) -> dict[str, Path]:
    """将业务文件条目映射到同一 full snapshot 的临时路径。

    Args:
        snapshot: storage owner 返回的 full source snapshot。
        file_entries: 当前下载描述符顺序下的业务文件条目。

    Returns:
        以 lowercase exact 业务文件名为键的 snapshot 临时路径映射。

    Raises:
        无；单文件不可用时沿用既有 best-effort 语义跳过该条目。
    """

    result: dict[str, Path] = {}
    for item in file_entries:
        if not isinstance(item, dict):
            continue
        uri = _normalize_optional_string(item.get("uri"))
        if uri is None:
            continue
        name = _normalize_optional_string(item.get("name")) or _normalize_optional_string(_infer_filename_from_uri(uri))
        if name is None:
            continue
        try:
            source = snapshot.get_source(name)
            local_path = source.materialize()
        except Exception:
            continue
        if not local_path.exists() or not local_path.is_file():
            continue
        result[name.lower()] = local_path
    return result


def _pick_download_xbrl_file(
    file_map: dict[str, Path],
    *,
    candidates: tuple[str, ...],
    xml_fallback: bool = False,
) -> Optional[Path]:
    """按后缀优先级从下载文件映射中选择 XBRL 文件。"""

    ordered_names = sorted(file_map.keys())
    for suffix in candidates:
        for name in ordered_names:
            if name.endswith(suffix):
                return file_map[name]
    if not xml_fallback:
        return None
    for name in ordered_names:
        if not name.endswith(".xml"):
            continue
        if name.endswith(_XBRL_LINKBASE_FILE_SUFFIXES):
            continue
        if name.endswith("filingsummary.xml"):
            continue
        return file_map[name]
    return None


def _mapping_get_case_insensitive(mapping: JsonValue, keys: tuple[str, ...]) -> JsonValue:
    """从映射中按大小写不敏感方式读取首个可用键值。"""

    if not isinstance(mapping, dict):
        return None
    normalized: dict[str, JsonValue] = {}
    for key, value in mapping.items():
        lowered = _normalize_optional_string(key)
        if lowered is None:
            continue
        normalized[lowered.lower()] = value
    for key in keys:
        value = normalized.get(key.lower())
        if value not in (None, ""):
            return value
    return None


def _pick_first_non_empty(candidates: tuple[JsonValue, ...]) -> JsonValue:
    """返回候选值中首个非空元素。"""

    for item in candidates:
        if item is None:
            continue
        if isinstance(item, str) and not item.strip():
            continue
        return item
    return None


def _infer_download_fiscal_fields(form_type: Optional[str], report_date: Optional[str]) -> tuple[Optional[int], Optional[str]]:
    """在 download 阶段为 source meta 推断 fiscal 字段。"""

    normalized_form_type = normalize_sec_form_type_for_matching(form_type)
    fiscal_year = _coerce_year_from_date(report_date)
    if _is_6k_family_form(normalized_form_type):
        fiscal_year = None
    fiscal_period = _resolve_fiscal_period_fallback(
        form_type=normalized_form_type,
        fiscal_year=fiscal_year,
        fiscal_year_from_report_date=fiscal_year is not None,
    )
    return fiscal_year, fiscal_period


def _resolve_fiscal_period_fallback(
    *,
    form_type: Optional[str],
    fiscal_year: Optional[int],
    fiscal_year_from_report_date: bool,
) -> Optional[str]:
    """按 form 解析 fiscal_period 的保守回退值。"""

    if fiscal_year is None:
        return None
    if form_type in {"10-K", "20-F"}:
        return "FY"
    return None


def _extract_fiscal_from_financials(
    financials_payload: Optional[dict[str, JsonValue]],
) -> tuple[Optional[int], Optional[str]]:
    """从 financials 载荷中提取 fiscal_year/fiscal_period。"""

    if not isinstance(financials_payload, dict):
        return None, None
    statements = financials_payload.get("statements")
    if not isinstance(statements, dict):
        return None, None
    for statement_type in FINANCIAL_STATEMENT_TYPES:
        statement = statements.get(statement_type)
        if not isinstance(statement, dict):
            continue
        periods = statement.get("periods")
        if not isinstance(periods, list):
            continue
        for period in periods:
            if not isinstance(period, dict):
                continue
            fiscal_year = _coerce_optional_int(period.get("fiscal_year"))
            fiscal_period = _normalize_optional_period(period.get("fiscal_period"))
            if fiscal_year is None:
                fiscal_year = _coerce_year_from_date(period.get("period_end"))
            if fiscal_year is not None or fiscal_period is not None:
                return fiscal_year, fiscal_period
    return None, None


def _extract_fiscal_from_xbrl_query(
    processor: _XbrlQueryProcessor | None,
) -> tuple[Optional[int], Optional[str]]:
    """通过 query_xbrl_facts 提取 fiscal_year/fiscal_period。"""

    if not isinstance(processor, _XbrlQueryProcessor):
        return None, None
    try:
        query_result = processor.query_xbrl_facts(
            concepts=[
                "us-gaap:Assets",
                "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
                "us-gaap:Revenues",
                "us-gaap:NetIncomeLoss",
                "ifrs-full:Assets",
                "ifrs-full:Revenue",
                "ifrs-full:ProfitLoss",
            ]
        )
    except Exception:
        return None, None
    if not isinstance(query_result, dict):
        return None, None
    try:
        validated_query_result = validate_xbrl_facts_result_payload(query_result)
    except ValueError:
        return None, None
    facts = validated_query_result.facts

    first_year_only: Optional[int] = None
    for fact in facts:
        if not isinstance(fact, dict):
            continue
        fiscal_year = _coerce_optional_int(fact.get("fiscal_year"))
        fiscal_period = _normalize_optional_period(fact.get("fiscal_period"))
        if fiscal_year is None:
            fiscal_year = _coerce_year_from_date(fact.get("period_end"))
        if fiscal_year is not None and first_year_only is None:
            first_year_only = fiscal_year
        if fiscal_year is not None and fiscal_period is not None:
            return fiscal_year, fiscal_period
    return first_year_only, None


def _coerce_optional_int(value: JsonValue) -> Optional[int]:
    """将输入值安全转换为可选整数。"""

    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    text = str(value).strip()
    if not text:
        return None
    if not re.fullmatch(r"-?\d+", text):
        return None
    try:
        return int(text)
    except ValueError:
        return None


def _normalize_optional_string(value: JsonValue) -> Optional[str]:
    """标准化可选字符串。"""

    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text


def _normalize_optional_period(value: JsonValue) -> Optional[str]:
    """标准化可选 fiscal_period 字段。

    Args:
        value: 原始 JSON 字段值。

    Returns:
        canonical 财期；字段为空或无法解析时返回 `None`。

    Raises:
        无。
    """

    normalized = _normalize_optional_string(value)
    if normalized is None:
        return None
    try:
        return normalize_fiscal_period(normalized)
    except ValueError:
        return None


def _coerce_year_from_date(value: JsonValue) -> Optional[int]:
    """从 `YYYY-MM-DD` 字符串中提取年份。"""

    text = _normalize_optional_string(value)
    if text is None:
        return None
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return int(text[:4])
    return None


def _is_6k_family_form(form_type: Optional[str]) -> bool:
    """判断表单是否属于 6-K 家族。

    Args:
        form_type: 已归一化或原始 form_type。

    Returns:
        若属于 `6-K` 或 `6-K/A` 家族则返回 `True`。

    Raises:
        无。
    """

    return form_type in {"6-K", "6-K/A"}


def _should_skip_financial_extraction(form_type: Optional[str]) -> bool:
    """判断是否应跳过 financial statements 提取。"""

    normalized = _normalize_optional_string(form_type)
    if normalized is None:
        return False
    normalized_form = normalize_sec_form_type_for_matching(normalized)
    if normalized_form in FINANCIAL_EXTRACTION_SKIP_FORMS:
        return True
    normalized_no_space = normalized.upper().replace(" ", "")
    return normalized_no_space.startswith("SC13")


def _sanitize_fiscal_period_by_form(form_type: Optional[str], fiscal_period: str) -> Optional[str]:
    """按 SEC form 约束 fiscal_period 合法值。

    Args:
        form_type: 原始或 canonical SEC form。
        fiscal_period: 原始或 canonical 财期。

    Returns:
        通过 form 约束的 canonical 财期；为空或不匹配时返回 `None`。

    Raises:
        ValueError: 非空财期不是 Fins 支持的财期枚举时抛出。
    """

    return sanitize_fiscal_period_by_sec_form(form_type, fiscal_period)
