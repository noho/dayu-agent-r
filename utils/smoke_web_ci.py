#!/usr/bin/env python3
"""显式 opt-in 的 Web CI smoke 汇总脚本。

本模块只负责 smoke 级别的 opt-in、diagnostics artifact schema 校验、
pass/fail/skip/diagnostic-only 分类和 Codex 可读 summary 输出。网页访问、
``requests``、``fetch_web_page``、Playwright 与 Docling 事实均来自
``utils.diagnose_web_access`` 输出的 artifact；本脚本不重新诊断网页内容。
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Final, TypeAlias, cast

from dayu.contracts.json_value import JsonValue

JsonObject: TypeAlias = dict[str, JsonValue]
DiagnosticRunner: TypeAlias = Callable[[Sequence[str]], "DiagnosticChildResult"]

_ENV_OPT_IN: Final[str] = "DAYU_RUN_WEB_CI_SMOKE"
_ENV_OPT_IN_VALUE: Final[str] = "1"
_DEFAULT_OUTPUT_ROOT: Final[Path] = Path("workspace/output/web_smoke")
_DIAGNOSTIC_SCHEMA_VERSION: Final[str] = "web-diagnostics-v1"
_MIN_DIAGNOSTIC_SCHEMA_REVISION: Final[int] = 1
_STATUS_PASSED: Final[str] = "passed"
_STATUS_FAILED: Final[str] = "failed"
_STATUS_SKIPPED: Final[str] = "skipped"
_STATUS_DIAGNOSTIC_ONLY: Final[str] = "diagnostic_only"
_EXIT_OK: Final[int] = 0
_EXIT_LOCAL_FAILURE: Final[int] = 1
_EXIT_SCHEMA_OR_INFRA_FAILURE: Final[int] = 2
_CASE_LOCAL_HTML: Final[str] = "local_html"
_CASE_LOCAL_PDF: Final[str] = "local_pdf"
_CASE_EXTERNAL: Final[str] = "external"
_BUCKET_PASSED: Final[str] = "passed"
_BUCKET_NOT_OPTED_IN: Final[str] = "not_opted_in"
_BUCKET_LOCAL_FIXTURE_ATTACHED_BY_SLICE3: Final[str] = "local_fixture_attached_by_slice3"
_BUCKET_DIAGNOSTIC_SCHEMA_GAP: Final[str] = "diagnostic_schema_gap"
_BUCKET_CHILD_PROCESS_ERROR: Final[str] = "child_process_error"
_BUCKET_ARTIFACT_PARSE_FAILURE: Final[str] = "artifact_parse_failure"
_BUCKET_ARTIFACT_MISSING: Final[str] = "artifact_missing"
_BUCKET_LOCAL_REQUESTS_FAILURE: Final[str] = "local_requests_failure"
_BUCKET_LOCAL_FETCH_FAILURE: Final[str] = "local_fetch_failure"
_BUCKET_PDF_CONTENT_TYPE_FAILURE: Final[str] = "pdf_content_type_failure"
_BUCKET_PDF_CONTENT_LENGTH_FAILURE: Final[str] = "pdf_content_length_failure"
_BUCKET_PDF_DOCLING_INVOCATION_FAILURE: Final[str] = "pdf_docling_invocation_failure"
_BUCKET_DOCLING_INIT_SKIP: Final[str] = "docling_runtime_initialization_error"
_PDF_FETCH_MIN_CHARS: Final[int] = 20


@dataclass(frozen=True, slots=True)
class SmokeOptions:
    """Smoke CLI 选项的强类型投影。

    Args:
        run_live: CLI 是否显式要求执行 live smoke。
        output_dir: summary 与子 artifact 输出目录。
        request_timeout: 传给 diagnostics 的 requests timeout。
        tool_timeout_budget: 传给 diagnostics 的工具调用 timeout budget。
        include_playwright: 是否让 diagnostics 采样 Playwright。
        external_url_file: 外部 URL 样本文件；为空时不运行外部诊断。
        external_limit: 外部 URL 最多采样数量。
        diagnostic_only_external: 外部 URL 是否只作为 diagnostic-only。
        run_label: 本次 smoke 运行标签。

    Returns:
        无。

    Raises:
        无。
    """

    run_live: bool
    output_dir: Path
    request_timeout: float
    tool_timeout_budget: float
    include_playwright: bool
    external_url_file: Path | None
    external_limit: int
    diagnostic_only_external: bool
    run_label: str


@dataclass(frozen=True, slots=True)
class DiagnosticChildResult:
    """diagnostics 子进程执行结果。

    Args:
        returncode: 子进程退出码。
        stdout: 子进程标准输出。
        stderr: 子进程标准错误。

    Returns:
        无。

    Raises:
        无。
    """

    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True, slots=True)
class SmokeItem:
    """summary 中的一条失败、跳过或 diagnostic-only 记录。

    Args:
        bucket: smoke 分类 bucket。
        evidence_path: 证据 artifact 路径。
        url: 相关 URL。
        suggested_next_step: 建议下一步；failure/diagnostic-only 使用。
        reason: 跳过原因；skip 使用。

    Returns:
        无。

    Raises:
        无。
    """

    bucket: str
    evidence_path: str
    url: str
    suggested_next_step: str
    reason: str

    def to_json(self) -> JsonObject:
        """转换为 summary JSON 对象。

        Args:
            无。

        Returns:
            summary item JSON 对象。

        Raises:
            无。
        """

        return {
            "bucket": self.bucket,
            "evidence_path": self.evidence_path,
            "url": self.url,
            "suggested_next_step": self.suggested_next_step,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class SmokeCaseResult:
    """单个 smoke case 的分类结果。

    Args:
        case_name: case 名称。
        case_kind: case 类型。
        url: 相关 URL。
        status: ``passed``、``failed``、``skipped`` 或 ``diagnostic_only``。
        bucket: smoke 分类 bucket。
        evidence_path: 证据 artifact 路径。
        suggested_next_step: 建议下一步。
        reason: 跳过或 diagnostic-only 原因。
        exit_code: 该 case 对本地 gate 的退出码贡献。

    Returns:
        无。

    Raises:
        无。
    """

    case_name: str
    case_kind: str
    url: str
    status: str
    bucket: str
    evidence_path: str
    suggested_next_step: str
    reason: str
    exit_code: int

    def to_json(self) -> JsonObject:
        """转换为 summary JSON 对象。

        Args:
            无。

        Returns:
            case result JSON 对象。

        Raises:
            无。
        """

        return {
            "case_name": self.case_name,
            "case_kind": self.case_kind,
            "url": self.url,
            "status": self.status,
            "bucket": self.bucket,
            "evidence_path": self.evidence_path,
            "suggested_next_step": self.suggested_next_step,
            "reason": self.reason,
            "exit_code": self.exit_code,
        }

    def to_item(self) -> SmokeItem:
        """转换为 failure/skip/diagnostic-only 列表项。

        Args:
            无。

        Returns:
            summary item。

        Raises:
            无。
        """

        return SmokeItem(
            bucket=self.bucket,
            evidence_path=self.evidence_path,
            url=self.url,
            suggested_next_step=self.suggested_next_step,
            reason=self.reason,
        )


@dataclass(frozen=True, slots=True)
class SmokeSummary:
    """Web smoke summary 契约。

    Args:
        status: 总体状态。
        exit_code: 脚本退出码。
        run_label: 运行标签。
        output_dir: 输出目录。
        failures: local gate failure 或 schema gap。
        skips: 已跳过的 case。
        diagnostic_only: diagnostic-only 记录。
        local_cases: local case 结果。
        external_cases: external case 结果。

    Returns:
        无。

    Raises:
        无。
    """

    status: str
    exit_code: int
    run_label: str
    output_dir: str
    failures: tuple[SmokeItem, ...]
    skips: tuple[SmokeItem, ...]
    diagnostic_only: tuple[SmokeItem, ...]
    local_cases: tuple[SmokeCaseResult, ...]
    external_cases: tuple[SmokeCaseResult, ...]

    def to_json(self) -> JsonObject:
        """转换为 summary JSON 对象。

        Args:
            无。

        Returns:
            summary JSON 对象。

        Raises:
            无。
        """

        return {
            "status": self.status,
            "exit_code": self.exit_code,
            "run_label": self.run_label,
            "output_dir": self.output_dir,
            "failures": [item.to_json() for item in self.failures],
            "skips": [item.to_json() for item in self.skips],
            "diagnostic_only": [item.to_json() for item in self.diagnostic_only],
            "local_cases": [case.to_json() for case in self.local_cases],
            "external_cases": [case.to_json() for case in self.external_cases],
        }


def _utc_run_label() -> str:
    """生成默认运行标签。

    Args:
        无。

    Returns:
        UTC 时间戳运行标签。

    Raises:
        无。
    """

    return datetime.now(timezone.utc).strftime("web-smoke-%Y%m%dT%H%M%SZ")


def _default_output_dir(run_label: str) -> Path:
    """生成默认输出目录。

    Args:
        run_label: 运行标签。

    Returns:
        默认输出目录。

    Raises:
        无。
    """

    return (_DEFAULT_OUTPUT_ROOT / run_label).resolve()


def _json_object(value: JsonValue, *, field_name: str) -> JsonObject:
    """校验并复制 JSON 对象。

    Args:
        value: 待校验 JSON 值。
        field_name: 字段名，用于错误信息。

    Returns:
        JSON 对象副本。

    Raises:
        ValueError: 输入不是 JSON 对象时抛出。
    """

    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} 必须是 JSON 对象。")
    return {str(key): item for key, item in value.items()}


def _nested_object(payload: Mapping[str, JsonValue], key: str) -> JsonObject:
    """读取嵌套 JSON 对象。

    Args:
        payload: JSON 对象。
        key: 字段名。

    Returns:
        嵌套 JSON 对象副本；缺失或类型不符时返回空对象。

    Raises:
        无。
    """

    value = payload.get(key)
    if isinstance(value, Mapping):
        return {str(nested_key): nested_value for nested_key, nested_value in value.items()}
    return {}


def _bool_field(payload: Mapping[str, JsonValue], key: str) -> bool:
    """读取布尔字段。

    Args:
        payload: JSON 对象。
        key: 字段名。

    Returns:
        字段严格为 ``True`` 时返回 ``True``。

    Raises:
        无。
    """

    return payload.get(key) is True


def _int_field(payload: Mapping[str, JsonValue], key: str) -> int | None:
    """读取整数字段。

    Args:
        payload: JSON 对象。
        key: 字段名。

    Returns:
        整数字段；缺失或类型不符时返回 ``None``。

    Raises:
        无。
    """

    value = payload.get(key)
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def _string_field(payload: Mapping[str, JsonValue], key: str) -> str:
    """读取字符串字段。

    Args:
        payload: JSON 对象。
        key: 字段名。

    Returns:
        字符串值；缺失或非字符串时返回空字符串。

    Raises:
        无。
    """

    value = payload.get(key)
    return value if isinstance(value, str) else ""


def _load_json_artifact(path: Path) -> JsonObject:
    """读取 diagnostics JSON artifact。

    Args:
        path: artifact 路径。

    Returns:
        artifact JSON 对象。

    Raises:
        OSError: 文件读取失败时抛出。
        ValueError: 文件不是 JSON 对象时抛出。
        json.JSONDecodeError: JSON 解析失败时抛出。
    """

    payload = cast(JsonValue, json.loads(path.read_text(encoding="utf-8")))
    return _json_object(payload, field_name=str(path))


def _write_json(path: Path, payload: Mapping[str, JsonValue]) -> None:
    """写入 JSON 文件。

    Args:
        path: 输出路径。
        payload: JSON 对象。

    Returns:
        无。

    Raises:
        OSError: 文件写入失败时抛出。
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _diagnostic_schema_gap(payload: Mapping[str, JsonValue], *, case_kind: str) -> str:
    """返回 diagnostics artifact schema gap 描述。

    Args:
        payload: diagnostics artifact。
        case_kind: case 类型。

    Returns:
        空字符串表示 schema 满足当前 smoke；非空字符串为 gap 说明。

    Raises:
        无。
    """

    version = _string_field(payload, "diagnostic_schema_version") or _string_field(payload, "schema_version")
    revision = _int_field(payload, "diagnostic_schema_revision")
    if version != _DIAGNOSTIC_SCHEMA_VERSION:
        return "diagnostics artifact 缺少当前 smoke 需要的 diagnostic_schema_version。"
    if revision is None or revision < _MIN_DIAGNOSTIC_SCHEMA_REVISION:
        return "diagnostics artifact 的 diagnostic_schema_revision 低于当前 smoke 要求。"

    required_gap = _required_fetch_fact_gap(payload)
    if required_gap:
        return required_gap
    if case_kind == _CASE_LOCAL_PDF:
        return _required_pdf_fact_gap(payload)
    return ""


def _external_diagnostic_schema_gap(payload: Mapping[str, JsonValue]) -> str:
    """校验 external diagnostic-only artifact 的最低 schema 事实。

    外部 URL 在 Slice 2 只用于 diagnostic-only 汇总，只需要 HTML 级别的
    requests/fetch 事实；这里刻意不要求 PDF content-type、内容长度或 Docling
    invocation evidence，避免把外部样本误提升为 local PDF gate。

    Args:
        payload: diagnostics artifact。

    Returns:
        空字符串表示 schema 满足 external diagnostic-only 汇总；非空字符串为
        gap 说明。

    Raises:
        无。
    """

    return _diagnostic_schema_gap(payload, case_kind=_CASE_LOCAL_HTML)


def _required_fetch_fact_gap(payload: Mapping[str, JsonValue]) -> str:
    """校验 HTML/PDF local gate 共用的 requests/fetch 必需事实。

    Args:
        payload: diagnostics artifact。

    Returns:
        空字符串表示必需字段存在；非空字符串为 gap 说明。

    Raises:
        无。
    """

    requests_profile = _nested_object(payload, "requests_profile")
    requests_result = _nested_object(requests_profile, "result")
    fetch_profile = _nested_object(payload, "fetch_web_page_profile")
    if "sampled" not in requests_profile:
        return "diagnostics artifact 缺少 requests_profile.sampled。"
    if "ok" not in requests_result:
        return "diagnostics artifact 缺少 requests_profile.result.ok。"
    if "sampled" not in fetch_profile:
        return "diagnostics artifact 缺少 fetch_web_page_profile.sampled。"
    if "ok" not in fetch_profile:
        return "diagnostics artifact 缺少 fetch_web_page_profile.ok。"
    return ""


def _required_pdf_fact_gap(payload: Mapping[str, JsonValue]) -> str:
    """校验 PDF local gate 必需事实。

    Args:
        payload: diagnostics artifact。

    Returns:
        空字符串表示必需字段存在；非空字符串为 gap 说明。

    Raises:
        无。
    """

    if not _raw_content_type(payload):
        return "diagnostics artifact 缺少 local PDF raw response content-type。"
    if _raw_content_length(payload) is None:
        return "diagnostics artifact 缺少 local PDF raw response content length。"
    if _fetch_content_length(payload) is None:
        return "diagnostics artifact 缺少 fetch_web_page content length。"
    evidence = _docling_evidence(payload)
    if not evidence:
        return "diagnostics artifact 缺少 docling_conversion_invocation_evidence。"
    return ""


def _raw_content_type(payload: Mapping[str, JsonValue]) -> str:
    """读取 raw requests 响应 content-type。

    Args:
        payload: diagnostics artifact。

    Returns:
        content-type 字符串；缺失时返回空字符串。

    Raises:
        无。
    """

    requests_profile = _nested_object(payload, "requests_profile")
    requests_result = _nested_object(requests_profile, "result")
    headers = _nested_object(requests_result, "response_headers")
    for key, value in headers.items():
        if key.lower() == "content-type" and isinstance(value, str):
            return value
    return _string_field(requests_result, "content_type") or _string_field(requests_profile, "content_type")


def _raw_content_length(payload: Mapping[str, JsonValue]) -> int | None:
    """读取 raw requests 响应内容长度。

    Args:
        payload: diagnostics artifact。

    Returns:
        内容长度；缺失时返回 ``None``。

    Raises:
        无。
    """

    requests_profile = _nested_object(payload, "requests_profile")
    requests_result = _nested_object(requests_profile, "result")
    direct = _int_field(requests_result, "content_length")
    if direct is not None:
        return direct
    return _int_field(requests_result, "text_length")


def _fetch_content_length(payload: Mapping[str, JsonValue]) -> int | None:
    """读取 fetch_web_page 返回内容长度。

    Args:
        payload: diagnostics artifact。

    Returns:
        内容长度；缺失时返回 ``None``。

    Raises:
        无。
    """

    fetch_profile = _nested_object(payload, "fetch_web_page_profile")
    return _int_field(fetch_profile, "content_length")


def _docling_evidence(payload: Mapping[str, JsonValue]) -> JsonObject:
    """读取 Docling invocation evidence。

    Args:
        payload: diagnostics artifact。

    Returns:
        evidence JSON 对象；缺失时返回空对象。

    Raises:
        无。
    """

    evidence = _nested_object(payload, "docling_conversion_invocation_evidence")
    if evidence:
        return evidence
    fetch_profile = _nested_object(payload, "fetch_web_page_profile")
    return _nested_object(fetch_profile, "docling_conversion_invocation_evidence")


def _docling_init_skip(payload: Mapping[str, JsonValue]) -> bool:
    """判断 artifact 是否清楚表明 Docling 初始化或依赖缺失。

    Args:
        payload: diagnostics artifact。

    Returns:
        观察到 Docling 初始化或依赖错误时返回 ``True``。

    Raises:
        无。
    """

    evidence = _docling_evidence(payload)
    if _bool_field(evidence, "docling_runtime_initialization_error"):
        return True
    exception_type = _string_field(evidence, "original_exception_type")
    return exception_type in {"DoclingRuntimeInitializationError", "ModuleNotFoundError", "ImportError"}


def _requests_ok(payload: Mapping[str, JsonValue]) -> bool:
    """判断 raw requests 是否成功。

    Args:
        payload: diagnostics artifact。

    Returns:
        requests sampled 且 ok 时返回 ``True``。

    Raises:
        无。
    """

    requests_profile = _nested_object(payload, "requests_profile")
    requests_result = _nested_object(requests_profile, "result")
    return _bool_field(requests_profile, "sampled") and _bool_field(requests_result, "ok")


def _fetch_ok(payload: Mapping[str, JsonValue]) -> bool:
    """判断 current fetch_web_page 是否成功。

    Args:
        payload: diagnostics artifact。

    Returns:
        fetch sampled 且 ok 时返回 ``True``。

    Raises:
        无。
    """

    fetch_profile = _nested_object(payload, "fetch_web_page_profile")
    return _bool_field(fetch_profile, "sampled") and _bool_field(fetch_profile, "ok")


def _url_from_payload(payload: Mapping[str, JsonValue], fallback_url: str) -> str:
    """读取 artifact URL。

    Args:
        payload: diagnostics artifact。
        fallback_url: 缺失时使用的 URL。

    Returns:
        URL。

    Raises:
        无。
    """

    return _string_field(payload, "url") or fallback_url


def _observed_bucket(payload: Mapping[str, JsonValue], default_bucket: str) -> str:
    """读取 diagnostics observed bucket。

    Args:
        payload: diagnostics artifact。
        default_bucket: 缺失时使用的 bucket。

    Returns:
        bucket 字符串。

    Raises:
        无。
    """

    return (
        _string_field(payload, "observed_bucket")
        or _string_field(payload, "comparison_bucket")
        or default_bucket
    )


def _suggested_next_step(payload: Mapping[str, JsonValue], default_step: str) -> str:
    """读取 diagnostics action hint。

    Args:
        payload: diagnostics artifact。
        default_step: 缺失时使用的建议。

    Returns:
        建议下一步。

    Raises:
        无。
    """

    return _string_field(payload, "diagnostic_action_hint") or default_step


def _classify_loaded_artifact(
    *,
    case_name: str,
    case_kind: str,
    fallback_url: str,
    artifact_path: Path,
    payload: Mapping[str, JsonValue],
    child_returncode: int,
) -> SmokeCaseResult:
    """根据已加载 artifact 分类 smoke case。

    Args:
        case_name: case 名称。
        case_kind: case 类型。
        fallback_url: artifact 缺少 URL 时的后备 URL。
        artifact_path: artifact 路径。
        payload: diagnostics artifact。
        child_returncode: diagnostics 子进程退出码。

    Returns:
        smoke case 结果。

    Raises:
        无。
    """

    url = _url_from_payload(payload, fallback_url)
    evidence_path = str(artifact_path)
    if case_kind == _CASE_EXTERNAL:
        if child_returncode != _EXIT_OK:
            return _case_diagnostic_only(
                case_name=case_name,
                case_kind=case_kind,
                url=url,
                evidence_path=evidence_path,
                bucket=_BUCKET_CHILD_PROCESS_ERROR,
                reason="外部 URL diagnostics 子进程失败；外部站点行为不作为 local smoke gate。",
                suggested_next_step="查看 diagnostics stdout/stderr 和站点可达性；必要时缩小外部样本。",
            )
        schema_gap = _external_diagnostic_schema_gap(payload)
        if schema_gap:
            return _case_diagnostic_only(
                case_name=case_name,
                case_kind=case_kind,
                url=url,
                evidence_path=evidence_path,
                bucket=_BUCKET_DIAGNOSTIC_SCHEMA_GAP,
                reason=schema_gap,
                suggested_next_step="先升级或修复 diagnostics artifact schema，再使用该外部样本做人工判断。",
            )
        return _case_diagnostic_only(
            case_name=case_name,
            case_kind=case_kind,
            url=url,
            evidence_path=evidence_path,
            bucket=_observed_bucket(payload, _STATUS_DIAGNOSTIC_ONLY),
            reason="外部 URL 只作为 diagnostic-only，不影响 local smoke exit code。",
            suggested_next_step=_suggested_next_step(payload, "查看外部诊断证据；不要把站点不稳定直接判为生产 regression。"),
        )

    if child_returncode != _EXIT_OK and _docling_init_skip(payload) and case_kind == _CASE_LOCAL_PDF:
        return _case_skip(
            case_name=case_name,
            case_kind=case_kind,
            url=url,
            evidence_path=evidence_path,
            bucket=_BUCKET_DOCLING_INIT_SKIP,
            reason="diagnostics 观察到 Docling 初始化或依赖缺失，PDF local smoke 本轮跳过。",
        )
    if child_returncode != _EXIT_OK:
        return _case_failure(
            case_name=case_name,
            case_kind=case_kind,
            url=url,
            evidence_path=evidence_path,
            bucket=_BUCKET_CHILD_PROCESS_ERROR,
            exit_code=_EXIT_LOCAL_FAILURE,
            suggested_next_step="检查 diagnostics 子进程错误；local fixture 子进程失败是 smoke failure。",
        )

    schema_gap = _diagnostic_schema_gap(payload, case_kind=case_kind)
    if schema_gap:
        return _case_failure(
            case_name=case_name,
            case_kind=case_kind,
            url=url,
            evidence_path=evidence_path,
            bucket=_BUCKET_DIAGNOSTIC_SCHEMA_GAP,
            exit_code=_EXIT_SCHEMA_OR_INFRA_FAILURE,
            suggested_next_step=schema_gap,
        )
    if case_kind == _CASE_LOCAL_PDF and _docling_init_skip(payload):
        return _case_skip(
            case_name=case_name,
            case_kind=case_kind,
            url=url,
            evidence_path=evidence_path,
            bucket=_BUCKET_DOCLING_INIT_SKIP,
            reason="diagnostics 观察到 Docling 初始化或依赖缺失，PDF local smoke 本轮跳过。",
        )
    if not _requests_ok(payload):
        return _case_failure(
            case_name=case_name,
            case_kind=case_kind,
            url=url,
            evidence_path=evidence_path,
            bucket=_BUCKET_LOCAL_REQUESTS_FAILURE,
            exit_code=_EXIT_LOCAL_FAILURE,
            suggested_next_step="先检查 local fixture raw requests 路径；requests 失败不能由 fetch 成功掩盖。",
        )
    if not _fetch_ok(payload):
        return _case_failure(
            case_name=case_name,
            case_kind=case_kind,
            url=url,
            evidence_path=evidence_path,
            bucket=_BUCKET_LOCAL_FETCH_FAILURE,
            exit_code=_EXIT_LOCAL_FAILURE,
            suggested_next_step="检查 current fetch_web_page callable 路径；local fixture fetch 失败是 smoke failure。",
        )
    if case_kind == _CASE_LOCAL_PDF:
        pdf_failure = _classify_pdf_loaded_artifact(
            case_name=case_name,
            url=url,
            evidence_path=evidence_path,
            payload=payload,
        )
        if pdf_failure is not None:
            return pdf_failure
    return SmokeCaseResult(
        case_name=case_name,
        case_kind=case_kind,
        url=url,
        status=_STATUS_PASSED,
        bucket=_BUCKET_PASSED,
        evidence_path=evidence_path,
        suggested_next_step="",
        reason="",
        exit_code=_EXIT_OK,
    )


def _classify_pdf_loaded_artifact(
    *,
    case_name: str,
    url: str,
    evidence_path: str,
    payload: Mapping[str, JsonValue],
) -> SmokeCaseResult | None:
    """分类 PDF local gate 的额外必需事实。

    Args:
        case_name: case 名称。
        url: URL。
        evidence_path: 证据路径。
        payload: diagnostics artifact。

    Returns:
        PDF 失败结果；全部通过时返回 ``None``。

    Raises:
        无。
    """

    content_type = _raw_content_type(payload).lower()
    if "pdf" not in content_type:
        return _case_failure(
            case_name=case_name,
            case_kind=_CASE_LOCAL_PDF,
            url=url,
            evidence_path=evidence_path,
            bucket=_BUCKET_PDF_CONTENT_TYPE_FAILURE,
            exit_code=_EXIT_LOCAL_FAILURE,
            suggested_next_step="local PDF fixture 必须返回 application/pdf content-type。",
        )
    raw_length = _raw_content_length(payload)
    if raw_length is None or raw_length <= 0:
        return _case_failure(
            case_name=case_name,
            case_kind=_CASE_LOCAL_PDF,
            url=url,
            evidence_path=evidence_path,
            bucket=_BUCKET_PDF_CONTENT_LENGTH_FAILURE,
            exit_code=_EXIT_LOCAL_FAILURE,
            suggested_next_step="local PDF raw response 必须包含非空 PDF bytes。",
        )
    fetch_length = _fetch_content_length(payload)
    if fetch_length is None or fetch_length < _PDF_FETCH_MIN_CHARS:
        return _case_failure(
            case_name=case_name,
            case_kind=_CASE_LOCAL_PDF,
            url=url,
            evidence_path=evidence_path,
            bucket=_BUCKET_PDF_CONTENT_LENGTH_FAILURE,
            exit_code=_EXIT_LOCAL_FAILURE,
            suggested_next_step=f"fetch_web_page 返回内容长度必须至少 {_PDF_FETCH_MIN_CHARS} 个字符。",
        )
    evidence = _docling_evidence(payload)
    if not _bool_field(evidence, "invoked") or not _bool_field(evidence, "original_completed"):
        return _case_failure(
            case_name=case_name,
            case_kind=_CASE_LOCAL_PDF,
            url=url,
            evidence_path=evidence_path,
            bucket=_BUCKET_PDF_DOCLING_INVOCATION_FAILURE,
            exit_code=_EXIT_LOCAL_FAILURE,
            suggested_next_step="PDF local smoke 必须观察到 Docling conversion callable 实际调用并正常返回。",
        )
    return None


def _case_failure(
    *,
    case_name: str,
    case_kind: str,
    url: str,
    evidence_path: str,
    bucket: str,
    exit_code: int,
    suggested_next_step: str,
) -> SmokeCaseResult:
    """构造 failure case。

    Args:
        case_name: case 名称。
        case_kind: case 类型。
        url: URL。
        evidence_path: 证据路径。
        bucket: failure bucket。
        exit_code: 退出码贡献。
        suggested_next_step: 建议下一步。

    Returns:
        failure case result。

    Raises:
        无。
    """

    return SmokeCaseResult(
        case_name=case_name,
        case_kind=case_kind,
        url=url,
        status=_STATUS_FAILED,
        bucket=bucket,
        evidence_path=evidence_path,
        suggested_next_step=suggested_next_step,
        reason="",
        exit_code=exit_code,
    )


def _case_skip(
    *,
    case_name: str,
    case_kind: str,
    url: str,
    evidence_path: str,
    bucket: str,
    reason: str,
) -> SmokeCaseResult:
    """构造 skipped case。

    Args:
        case_name: case 名称。
        case_kind: case 类型。
        url: URL。
        evidence_path: 证据路径。
        bucket: skip bucket。
        reason: 跳过原因。

    Returns:
        skipped case result。

    Raises:
        无。
    """

    return SmokeCaseResult(
        case_name=case_name,
        case_kind=case_kind,
        url=url,
        status=_STATUS_SKIPPED,
        bucket=bucket,
        evidence_path=evidence_path,
        suggested_next_step="安装或修复 Docling runtime 后重跑 opt-in smoke。",
        reason=reason,
        exit_code=_EXIT_OK,
    )


def _case_diagnostic_only(
    *,
    case_name: str,
    case_kind: str,
    url: str,
    evidence_path: str,
    bucket: str,
    reason: str,
    suggested_next_step: str,
) -> SmokeCaseResult:
    """构造 diagnostic-only case。

    Args:
        case_name: case 名称。
        case_kind: case 类型。
        url: URL。
        evidence_path: 证据路径。
        bucket: diagnostic-only bucket。
        reason: diagnostic-only 原因。
        suggested_next_step: 建议下一步。

    Returns:
        diagnostic-only case result。

    Raises:
        无。
    """

    return SmokeCaseResult(
        case_name=case_name,
        case_kind=case_kind,
        url=url,
        status=_STATUS_DIAGNOSTIC_ONLY,
        bucket=bucket,
        evidence_path=evidence_path,
        suggested_next_step=suggested_next_step,
        reason=reason,
        exit_code=_EXIT_OK,
    )


def _classify_child_result(
    *,
    case_name: str,
    case_kind: str,
    fallback_url: str,
    artifact_path: Path,
    child_result: DiagnosticChildResult,
) -> SmokeCaseResult:
    """按子进程结果与 artifact 分类 smoke case。

    Args:
        case_name: case 名称。
        case_kind: case 类型。
        fallback_url: artifact 缺少 URL 时的后备 URL。
        artifact_path: artifact 路径。
        child_result: diagnostics 子进程结果。

    Returns:
        smoke case 结果。

    Raises:
        无。
    """

    if not artifact_path.is_file():
        if case_kind == _CASE_EXTERNAL:
            return _case_diagnostic_only(
                case_name=case_name,
                case_kind=case_kind,
                url=fallback_url,
                evidence_path=str(artifact_path),
                bucket=_BUCKET_ARTIFACT_MISSING,
                reason="外部 diagnostics 未生成 artifact；不影响 local smoke gate。",
                suggested_next_step="检查 external URL 文件、网络和 diagnostics 子进程 stderr。",
            )
        return _case_failure(
            case_name=case_name,
            case_kind=case_kind,
            url=fallback_url,
            evidence_path=str(artifact_path),
            bucket=_BUCKET_ARTIFACT_MISSING,
            exit_code=_EXIT_SCHEMA_OR_INFRA_FAILURE,
            suggested_next_step="local diagnostics artifact 缺失，无法进行 smoke 判定。",
        )
    try:
        payload = _load_json_artifact(artifact_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        if case_kind == _CASE_EXTERNAL:
            return _case_diagnostic_only(
                case_name=case_name,
                case_kind=case_kind,
                url=fallback_url,
                evidence_path=str(artifact_path),
                bucket=_BUCKET_ARTIFACT_PARSE_FAILURE,
                reason=f"外部 diagnostics artifact 无法解析：{exc}",
                suggested_next_step="检查外部 diagnostics artifact 是否完整写入。",
            )
        return _case_failure(
            case_name=case_name,
            case_kind=case_kind,
            url=fallback_url,
            evidence_path=str(artifact_path),
            bucket=_BUCKET_ARTIFACT_PARSE_FAILURE,
            exit_code=_EXIT_SCHEMA_OR_INFRA_FAILURE,
            suggested_next_step=f"local diagnostics artifact 无法解析：{exc}",
        )
    return _classify_loaded_artifact(
        case_name=case_name,
        case_kind=case_kind,
        fallback_url=fallback_url,
        artifact_path=artifact_path,
        payload=payload,
        child_returncode=child_result.returncode,
    )


def _summary_from_cases(
    *,
    run_label: str,
    output_dir: Path,
    local_cases: Sequence[SmokeCaseResult],
    external_cases: Sequence[SmokeCaseResult],
    extra_skips: Sequence[SmokeItem] = (),
) -> SmokeSummary:
    """按 case 结果构造 smoke summary。

    Args:
        run_label: 运行标签。
        output_dir: 输出目录。
        local_cases: local case 列表。
        external_cases: external case 列表。
        extra_skips: 不属于具体 case、但需要进入 summary 的 skip 信号。

    Returns:
        smoke summary。

    Raises:
        无。
    """

    failures = tuple(case.to_item() for case in local_cases if case.status == _STATUS_FAILED)
    skips = tuple(case.to_item() for case in local_cases if case.status == _STATUS_SKIPPED) + tuple(extra_skips)
    diagnostic_only = tuple(case.to_item() for case in external_cases if case.status == _STATUS_DIAGNOSTIC_ONLY)
    local_exit_code = _EXIT_OK
    if any(case.exit_code == _EXIT_SCHEMA_OR_INFRA_FAILURE for case in local_cases):
        local_exit_code = _EXIT_SCHEMA_OR_INFRA_FAILURE
    elif any(case.exit_code == _EXIT_LOCAL_FAILURE for case in local_cases):
        local_exit_code = _EXIT_LOCAL_FAILURE

    if local_exit_code != _EXIT_OK:
        status = _STATUS_FAILED
    elif any(case.status == _STATUS_PASSED for case in local_cases):
        status = _STATUS_PASSED
    elif diagnostic_only:
        status = _STATUS_DIAGNOSTIC_ONLY
    else:
        status = _STATUS_SKIPPED

    return SmokeSummary(
        status=status,
        exit_code=local_exit_code,
        run_label=run_label,
        output_dir=str(output_dir),
        failures=failures,
        skips=skips,
        diagnostic_only=diagnostic_only,
        local_cases=tuple(local_cases),
        external_cases=tuple(external_cases),
    )


def _skipped_summary(*, run_label: str, output_dir: Path) -> SmokeSummary:
    """构造未 opt-in summary。

    Args:
        run_label: 运行标签。
        output_dir: 输出目录。

    Returns:
        skipped summary。

    Raises:
        无。
    """

    skip_item = SmokeItem(
        bucket=_BUCKET_NOT_OPTED_IN,
        evidence_path="",
        url="",
        suggested_next_step="设置 DAYU_RUN_WEB_CI_SMOKE=1 或传入 --run-live 后才会执行 live smoke。",
        reason="未显式 opt-in；脚本未联网、未启动 server、未调用 diagnostics runner。",
    )
    return SmokeSummary(
        status=_STATUS_SKIPPED,
        exit_code=_EXIT_OK,
        run_label=run_label,
        output_dir=str(output_dir),
        failures=(),
        skips=(skip_item,),
        diagnostic_only=(),
        local_cases=(),
        external_cases=(),
    )


def _summary_markdown(summary: SmokeSummary) -> str:
    """构造 Codex 可读 Markdown summary。

    Args:
        summary: smoke summary。

    Returns:
        Markdown 文本。

    Raises:
        无。
    """

    lines = [
        f"# Web CI Smoke Summary - {summary.run_label}",
        "",
        f"- status: {summary.status}",
        f"- exit_code: {summary.exit_code}",
        f"- output_dir: {summary.output_dir}",
        f"- local_cases: {len(summary.local_cases)}",
        f"- external_cases: {len(summary.external_cases)}",
    ]
    lines.extend(_markdown_items("Failures", summary.failures))
    lines.extend(_markdown_items("Skips", summary.skips))
    lines.extend(_markdown_items("Diagnostic Only", summary.diagnostic_only))
    return "\n".join(lines) + "\n"


def _markdown_items(title: str, items: Sequence[SmokeItem]) -> list[str]:
    """构造 Markdown item 章节。

    Args:
        title: 章节标题。
        items: summary item 列表。

    Returns:
        Markdown 行列表。

    Raises:
        无。
    """

    lines = ["", f"## {title}", ""]
    if not items:
        lines.append("- 无")
        return lines
    for item in items:
        detail = item.reason or item.suggested_next_step
        lines.append(f"- bucket={item.bucket} url={item.url} evidence={item.evidence_path} detail={detail}")
    return lines


def _write_summary(summary: SmokeSummary) -> None:
    """写 summary.json 与 summary.md。

    Args:
        summary: smoke summary。

    Returns:
        无。

    Raises:
        OSError: 文件写入失败时抛出。
    """

    output_dir = Path(summary.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(output_dir / "summary.json", summary.to_json())
    (output_dir / "summary.md").write_text(_summary_markdown(summary), encoding="utf-8")


def _read_external_urls(path: Path, *, limit: int) -> list[str]:
    """读取外部 URL 样本并应用上限。

    Args:
        path: URL 文件路径，支持 JSONL 对象/字符串或纯文本。
        limit: 最多返回数量；``0`` 表示不返回样本。

    Returns:
        URL 字符串列表。

    Raises:
        ValueError: 输入文件不存在、JSONL 非法或 URL 为空时抛出。
        OSError: 文件读取失败时抛出。
    """

    if not path.is_file():
        raise ValueError(f"external URL 文件不存在: {path}")
    urls: list[str] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if limit >= 0 and len(urls) >= limit:
            break
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if path.suffix.lower() in {".jsonl", ".jsonlines"}:
            urls.append(_url_from_jsonl_line(line, line_number))
        else:
            urls.append(line)
    return urls


def _url_from_jsonl_line(line: str, line_number: int) -> str:
    """从 JSONL 行读取 URL。

    Args:
        line: JSONL 原始行。
        line_number: 行号。

    Returns:
        URL 字符串。

    Raises:
        ValueError: JSON 或 URL 字段非法时抛出。
    """

    try:
        value = cast(JsonValue, json.loads(line))
    except json.JSONDecodeError as exc:
        raise ValueError(f"external URL JSONL 第 {line_number} 行非法: {exc}") from exc
    if isinstance(value, str):
        url = value.strip()
    elif isinstance(value, Mapping):
        raw_url = value.get("url")
        url = raw_url.strip() if isinstance(raw_url, str) else ""
    else:
        url = ""
    if not url:
        raise ValueError(f"external URL JSONL 第 {line_number} 行缺少 url。")
    return url


def _run_diagnostic_command(command: Sequence[str]) -> DiagnosticChildResult:
    """执行 diagnostics 子进程。

    Args:
        command: 子进程命令。

    Returns:
        子进程结果。

    Raises:
        OSError: 进程启动失败时抛出。
    """

    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    return DiagnosticChildResult(
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def _diagnostic_command(
    *,
    url: str,
    artifact_path: Path,
    options: SmokeOptions,
) -> list[str]:
    """构造单 URL diagnostics 命令。

    Args:
        url: 待诊断 URL。
        artifact_path: diagnostics 输出 artifact。
        options: smoke 选项。

    Returns:
        子进程命令参数列表。

    Raises:
        无。
    """

    command = [
        sys.executable,
        "-m",
        "utils.diagnose_web_access",
        "--url",
        url,
        "--output",
        str(artifact_path),
        "--request-timeout",
        str(options.request_timeout),
        "--tool-timeout-budget",
        str(options.tool_timeout_budget),
    ]
    if not options.include_playwright:
        command.append("--skip-playwright")
    return command


def _run_external_cases(*, options: SmokeOptions, runner: DiagnosticRunner) -> list[SmokeCaseResult]:
    """运行 external diagnostic-only cases。

    Args:
        options: smoke 选项。
        runner: diagnostics 子进程 runner。

    Returns:
        external case 结果列表。

    Raises:
        ValueError: external URL 输入非法时抛出。
        OSError: 文件读写或子进程启动失败时抛出。
    """

    if options.external_url_file is None:
        return []
    urls = _read_external_urls(options.external_url_file, limit=options.external_limit)
    diagnostics_dir = options.output_dir / "diagnostics" / "external"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    results: list[SmokeCaseResult] = []
    for index, url in enumerate(urls, start=1):
        artifact_path = diagnostics_dir / f"external-{index:04d}.json"
        command = _diagnostic_command(url=url, artifact_path=artifact_path, options=options)
        child_result = runner(command)
        results.append(
            _classify_child_result(
                case_name=f"external-{index:04d}",
                case_kind=_CASE_EXTERNAL,
                fallback_url=url,
                artifact_path=artifact_path,
                child_result=child_result,
            )
        )
    return results


def _execute_smoke(*, options: SmokeOptions, runner: DiagnosticRunner) -> SmokeSummary:
    """执行当前 Slice 2 smoke 流程。

    Slice 2 只提供 opt-in CLI、summary contract、子进程 artifact 映射和外部
    diagnostic-only 执行框架；local HTTP fixture 由后续 Slice 3 接入。

    Args:
        options: smoke 选项。
        runner: diagnostics 子进程 runner。

    Returns:
        smoke summary。

    Raises:
        ValueError: operator 输入非法时抛出。
        OSError: 文件读写或子进程启动失败时抛出。
    """

    external_cases = _run_external_cases(options=options, runner=runner)
    return _summary_from_cases(
        run_label=options.run_label,
        output_dir=options.output_dir,
        local_cases=(),
        external_cases=external_cases,
        extra_skips=(_slice2_local_fixture_skip_item(),),
    )


def _slice2_local_fixture_skip_item() -> SmokeItem:
    """构造 Slice 2 opt-in 但尚无 local fixture case 的 summary 信号。

    Args:
        无。

    Returns:
        说明 local fixture smoke 由 Slice 3 接入的 skip item。

    Raises:
        无。
    """

    return SmokeItem(
        bucket=_BUCKET_LOCAL_FIXTURE_ATTACHED_BY_SLICE3,
        evidence_path="",
        url="",
        suggested_next_step="进入 WU-TOOLS-01-F03 Slice 3 后接入 local HTML/PDF fixture smoke。",
        reason="当前 Slice 2 只验证 opt-in CLI、summary contract 与 diagnostics artifact 映射；local fixture smoke 由 Slice 3 接入。",
    )


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    """解析 CLI 参数。

    Args:
        argv: 可选命令行参数；``None`` 表示读取进程参数。

    Returns:
        argparse namespace。

    Raises:
        SystemExit: argparse 在参数非法时抛出。
    """

    parser = argparse.ArgumentParser(description="显式 opt-in 的 Web CI smoke summary 生成器。")
    parser.add_argument("--run-live", action="store_true", help="显式执行 live smoke。")
    parser.add_argument("--output-dir", default="", help="summary 输出目录；缺省为 workspace/output/web_smoke/<run_label>。")
    parser.add_argument("--request-timeout", type=float, default=15.0, help="diagnostics requests timeout 秒数。")
    parser.add_argument("--tool-timeout-budget", type=float, default=30.0, help="diagnostics 工具调用 timeout budget 秒数。")
    parser.add_argument("--include-playwright", action="store_true", help="让 diagnostics 采样 Playwright；默认跳过。")
    parser.add_argument("--external-url-file", default="", help="外部 URL 文件；提供后只作为 diagnostic-only。")
    parser.add_argument("--external-limit", type=int, default=0, help="外部 URL 最多采样数量。")
    parser.add_argument(
        "--diagnostic-only-external",
        action="store_true",
        help="显式确认外部 URL 只作为 diagnostic-only；提供 external-url-file 时自动按此语义处理。",
    )
    parser.add_argument("--run-label", default="", help="可选运行标签，主要供 deterministic 测试或人工复现使用。")
    return parser.parse_args(argv)


def _options_from_namespace(namespace: argparse.Namespace) -> SmokeOptions:
    """从 argparse namespace 构造 SmokeOptions。

    Args:
        namespace: argparse namespace。

    Returns:
        smoke 选项。

    Raises:
        ValueError: 参数非法时抛出。
    """

    run_label_value = namespace.run_label
    run_label = run_label_value if isinstance(run_label_value, str) and run_label_value else _utc_run_label()
    output_dir_value = namespace.output_dir
    output_dir = Path(output_dir_value).expanduser().resolve() if isinstance(output_dir_value, str) and output_dir_value else _default_output_dir(run_label)
    request_timeout_value = namespace.request_timeout
    tool_timeout_budget_value = namespace.tool_timeout_budget
    external_limit_value = namespace.external_limit
    external_file_value = namespace.external_url_file
    if not isinstance(request_timeout_value, float) or request_timeout_value <= 0:
        raise ValueError("--request-timeout 必须大于 0。")
    if not isinstance(tool_timeout_budget_value, float) or tool_timeout_budget_value <= 0:
        raise ValueError("--tool-timeout-budget 必须大于 0。")
    if not isinstance(external_limit_value, int) or external_limit_value < 0:
        raise ValueError("--external-limit 必须大于等于 0。")
    external_url_file = (
        Path(external_file_value).expanduser().resolve()
        if isinstance(external_file_value, str) and external_file_value
        else None
    )
    return SmokeOptions(
        run_live=bool(namespace.run_live),
        output_dir=output_dir,
        request_timeout=request_timeout_value,
        tool_timeout_budget=tool_timeout_budget_value,
        include_playwright=bool(namespace.include_playwright),
        external_url_file=external_url_file,
        external_limit=external_limit_value,
        diagnostic_only_external=bool(namespace.diagnostic_only_external) or external_url_file is not None,
        run_label=run_label,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """脚本入口。

    Args:
        argv: 可选命令行参数；``None`` 表示读取进程参数。

    Returns:
        进程退出码。

    Raises:
        无。
    """

    try:
        namespace = _parse_args(argv)
        options = _options_from_namespace(namespace)
    except SystemExit as exc:
        return int(exc.code) if isinstance(exc.code, int) else _EXIT_SCHEMA_OR_INFRA_FAILURE
    except ValueError as exc:
        print(f"smoke 参数错误: {exc}", file=sys.stderr)
        return _EXIT_SCHEMA_OR_INFRA_FAILURE

    opted_in = options.run_live or os.environ.get(_ENV_OPT_IN) == _ENV_OPT_IN_VALUE
    try:
        if not opted_in:
            summary = _skipped_summary(run_label=options.run_label, output_dir=options.output_dir)
        else:
            summary = _execute_smoke(options=options, runner=_run_diagnostic_command)
        _write_summary(summary)
    except (OSError, ValueError) as exc:
        print(f"smoke 执行失败: {exc}", file=sys.stderr)
        return _EXIT_SCHEMA_OR_INFRA_FAILURE
    print(f"Web CI smoke summary 已写入: {options.output_dir}")
    return summary.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
