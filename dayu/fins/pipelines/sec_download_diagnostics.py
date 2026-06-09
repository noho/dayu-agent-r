"""SEC 下载诊断与 filing 数量警告检测。

在 download 完成后检查年报/季报/DEF 14A 数量是否低于预期，
以及强制 XBRL 表单是否缺少 XBRL instance 文件。
"""

from __future__ import annotations

from dayu.contracts.json_value import JsonValue

import datetime as dt


from dayu.fins.pipelines.sec_filing_collection import FilingRecord

# ---------- 数量诊断常量 ----------

# 年报/季报 document_type 分组及最低期望数量。
# 10-K 与 20-F 同属年报（境内注册公司用 10-K，外国公司用 20-F，两者互斥），合并计数。
# 10-Q 与 6-K 同属季报（境内注册公司用 10-Q，外国公司用 6-K，两者互斥），合并计数。
# 8-K、SC 13D/G 不在此表中：8-K 合理可变；SC 13D/G 已有专项 warning。
_ANNUAL_FORMS: frozenset[str] = frozenset({"10-K", "20-F"})
_QUARTERLY_FORMS: frozenset[str] = frozenset({"10-Q", "6-K"})
_MIN_ANNUAL_COUNT: int = 5
_MIN_QUARTERLY_COUNT: int = 3
_MIN_DEF14A_COUNT: int = 2

# ---------- XBRL 诊断常量 ----------

# 始终强制要求 XBRL 的 form_type
_XBRL_ALWAYS_REQUIRED_FORMS: frozenset[str] = frozenset({"10-K", "10-K/A", "10-Q", "10-Q/A"})
# 满足截止日期条件后才强制要求 XBRL 的 form_type
_XBRL_CONDITIONAL_FORMS: frozenset[str] = frozenset({"20-F", "20-F/A"})
# 20-F 强制 XBRL 的生效日期（SEC 规则，2012 年 6-15-F 之后的提交）
_XBRL_20F_CUTOFF_DATE: str = "2012-01-01"


# ---------- 函数 ----------


def warn_insufficient_filings(
    form_windows: dict[str, dt.date],
    filing_results: list[dict[str, JsonValue]],
    rejection_registry: dict[str, dict[str, str]],
) -> list[str]:
    """检查年报/季报组及 DEF 14A 的落盘数量，不足最低期望时返回 warning 文本列表。

    分组规则：
    - 年报组：10-K 与 20-F 合并计数（外国公司用 20-F，境内注册公司用 10-K，两者互斥）。
    - 季报组：10-Q 与 6-K 合并计数（外国公司用 6-K，境内注册公司用 10-Q，两者互斥）。
    - DEF 14A：单独检查，最低期望 2。
    - 若该组中没有任何 form 出现在本次 form_windows 中，跳过该组检查。

    有效下载规则：
    - 统计 status 为 downloaded 或 skipped（已存在）的 filing 数量，两者都算"有效下载"。
    - 6-K 额外区分：若 rejection_registry 中存在 6-K 记录（有 submission 但全被过滤），
      warning 中会注明，方便排查分类规则是否漏判。

    Args:
        form_windows: 本次下载请求的 form 到起始日期映射。
        filing_results: 所有 filing 的下载结果列表，每项含 status / form_type 字段。
        rejection_registry: 拒绝注册表，用于判断 6-K 是否存在被过滤记录。

    Returns:
        warning 文本列表（无问题时为空列表）。

    Raises:
        无。
    """

    warnings: list[str] = []
    requested_forms = set(form_windows)

    # 年报组：10-K + 20-F 合并检查
    requested_annual = _ANNUAL_FORMS & requested_forms
    if requested_annual:
        actual = sum(
            1
            for item in filing_results
            if item.get("form_type") in _ANNUAL_FORMS
            and item.get("status") in {"downloaded", "skipped"}
        )
        if actual < _MIN_ANNUAL_COUNT:
            label = "/".join(sorted(requested_annual))
            warnings.append(
                f"年报（{label}）有效落盘数 {actual} 低于期望 {_MIN_ANNUAL_COUNT}；"
                "请检查 SEC submissions 数据或适当扩大回溯窗口。"
            )

    # 季报组：10-Q + 6-K 合并检查
    requested_quarterly = _QUARTERLY_FORMS & requested_forms
    if requested_quarterly:
        actual = sum(
            1
            for item in filing_results
            if item.get("form_type") in _QUARTERLY_FORMS
            and item.get("status") in {"downloaded", "skipped"}
        )
        if actual < _MIN_QUARTERLY_COUNT:
            label = "/".join(sorted(requested_quarterly))
            # 6-K 额外补充：是否有 rejection 记录（有 submission 但被过滤）
            if "6-K" in requested_quarterly:
                rejected_count = sum(
                    1
                    for entry in rejection_registry.values()
                    if entry.get("form_type") == "6-K"
                )
                if rejected_count > 0:
                    warnings.append(
                        f"季报（{label}）有效落盘数 {actual} 低于期望 {_MIN_QUARTERLY_COUNT}；"
                        f"另有 {rejected_count} 份 6-K 被分类过滤（rejection_registry）。"
                        "请检查 _classify_6k_text 是否漏判季报。"
                    )
                else:
                    warnings.append(
                        f"季报（{label}）有效落盘数 {actual} 低于期望 {_MIN_QUARTERLY_COUNT}；"
                        "该公司在回溯窗口内可能未提交季报型 6-K。"
                    )
            else:
                warnings.append(
                    f"季报（{label}）有效落盘数 {actual} 低于期望 {_MIN_QUARTERLY_COUNT}；"
                    "请检查 SEC submissions 数据或适当扩大回溯窗口。"
                )

    # DEF 14A 单独检查
    if "DEF 14A" in requested_forms:
        actual = sum(
            1
            for item in filing_results
            if item.get("form_type") == "DEF 14A"
            and item.get("status") in {"downloaded", "skipped"}
        )
        if actual < _MIN_DEF14A_COUNT:
            warnings.append(
                f"DEF 14A 有效落盘数 {actual} 低于期望 {_MIN_DEF14A_COUNT}；"
                "请检查 SEC submissions 数据或适当扩大回溯窗口。"
            )

    return warnings


def warn_xbrl_missing_filings(
    filing_results: list[dict[str, JsonValue]],
) -> list[str]:
    """检查本次下载中强制 XBRL 表单是否缺少 XBRL instance。

    检查规则：
    - has_xbrl=True → 正常，跳过
    - has_xbrl=False → 缺失，发 warning
    - has_xbrl=None → 无法判断（旧数据 / fast-skip），跳过
    - 10-K / 10-K/A / 10-Q / 10-Q/A：始终强制
    - 20-F / 20-F/A：filing_date >= ``_XBRL_20F_CUTOFF_DATE`` 时强制

    Args:
        filing_results: 所有 filing 的下载结果列表。

    Returns:
        warning 文本列表（无问题时为空列表）。

    Raises:
        无。
    """

    warnings: list[str] = []
    for item in filing_results:
        if item.get("status") not in {"downloaded", "skipped"}:
            continue
        has_xbrl = item.get("has_xbrl")
        if has_xbrl is not False:
            # None 表示无法判断（跳过），True 表示正常
            continue
        form = str(item.get("form_type", ""))
        filing_date = str(item.get("filing_date") or "")
        doc_id = str(item.get("document_id", ""))

        if form in _XBRL_ALWAYS_REQUIRED_FORMS:
            xbrl_required = True
        elif form in _XBRL_CONDITIONAL_FORMS:
            xbrl_required = bool(filing_date) and filing_date >= _XBRL_20F_CUTOFF_DATE
        else:
            xbrl_required = False

        if xbrl_required:
            warnings.append(
                f"XBRL 缺失（{form} {filing_date}，{doc_id}）：该 filing 目录内未发现 XBRL instance 文件，"
                "财务数据提取将回退到 HTML/文本解析，精确性下降。请检查 SEC EDGAR 源文件。"
            )
    return warnings
