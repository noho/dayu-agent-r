"""Tool Trace Analyzer 的公开 source、policy 与 structured report 契约。

本模块冻结显式输入、诊断阈值、证据、finding、limitation、聚合摘要及
vendor debugging block 的 public shape，并在各语义 owner 边界校验不变量。
"""

from __future__ import annotations

import math
import os
import stat
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import TypeVar

from dayu.contracts.json_value import JsonValue
from dayu.engine.contracts.runner_identity import (
    ProviderRequestIdAvailability,
    RunnerRequestIdentity,
)
from dayu.host.durable.tool_trace import CompactorResponseDisposition

DEFAULT_TOOL_TRACE_LARGE_PAYLOAD_THRESHOLD_BYTES = 131_072
"""默认 large payload 诊断阈值。"""

DEFAULT_TOOL_TRACE_PAYLOAD_RANKING_LIMIT = 20
"""默认 payload 排名条目上限。"""

DEFAULT_TOOL_TRACE_LATENCY_MINIMUM_SAMPLE_COUNT = 5
"""默认 latency 异常判断最小样本数。"""

DEFAULT_TOOL_TRACE_LATENCY_OUTLIER_MULTIPLIER = 3.0
"""默认 latency 异常倍数。"""

DEFAULT_TOOL_TRACE_LATENCY_MINIMUM_DELTA_MS = 1_000
"""默认 latency 异常最小绝对差值。"""

_DAYU_DIRECTORY_NAME = ".dayu"
_HOST_DIRECTORY_NAME = "host"
_ARTIFACT_DIRECTORY_NAME = "artifacts"
_TOOL_TRACE_DIRECTORY_NAME = "tool-trace"
_TOOL_TRACE_COLD_FILE_NAME = "tool-trace-cold.jsonl"
_HOST_DATABASE_FILE_NAME = "dayu_host.sqlite3"
_ContractT = TypeVar("_ContractT")


class ToolTraceInputMode(StrEnum):
    """Tool Trace Analyzer 支持的显式输入模式。"""

    COLD_FILE = "cold_file"
    WORKSPACE_DIRECTORY = "workspace_directory"
    DAYU_DIRECTORY = "dayu_directory"
    TRACE_DIRECTORY = "trace_directory"


class ToolTraceAnalysisLayer(StrEnum):
    """Analyzer finding 的语义归因层。"""

    HOST = "host"
    ENGINE = "engine"
    TOOL = "tool"


class ToolTraceFindingSeverity(StrEnum):
    """Analyzer confirmed finding 的严重程度。"""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class ToolTraceFindingPriority(StrEnum):
    """Analyzer confirmed finding 的处置优先级。"""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ToolTraceSignalStatus(StrEnum):
    """Analyzer signal coverage 状态。"""

    AVAILABLE = "available"
    LIMITED_SIGNAL = "limited_signal"
    NOT_APPLICABLE = "not_applicable"


class ToolTraceEvidenceKind(StrEnum):
    """Analyzer finding/limitation 的直接证据类型。"""

    COLD_LINE = "cold_line"
    HOT_ROW = "hot_row"
    RESOLVED_PAYLOAD = "resolved_payload"
    INPUT_PATH = "input_path"


class ToolTracePayloadMeasurementSource(StrEnum):
    """payload byte measure 的唯一计量来源。"""

    COLD_JSONL_RECORD_BYTES = "cold_jsonl_record_bytes"
    RESOLVED_PAYLOAD_BYTES = "resolved_payload_bytes"


@dataclass(frozen=True, slots=True)
class ToolTraceAnalysisSource:
    """Tool Trace Analyzer 的完整显式输入来源。

    :param requested_path: Service 已归一化的绝对 operator 输入路径。
    :param mode: 输入布局模式。
    :param cold_jsonl_path: 当前模式唯一预期的 cold JSONL 路径。
    :param hot_db_path: directory 模式唯一预期的 Host DB 路径。
    :param artifact_root: directory 模式唯一预期的 artifact root。
    :raises TypeError: 字段类型错误时抛出。
    :raises ValueError: 路径、布局、存在性或文件类型违反契约时抛出。
    """

    requested_path: Path
    mode: ToolTraceInputMode
    cold_jsonl_path: Path
    hot_db_path: Path | None
    artifact_root: Path | None

    def __post_init__(self) -> None:
        """复核显式来源的路径与 mode 不变量。

        :returns: ``None``。
        :raises TypeError: 字段类型错误时抛出。
        :raises ValueError: 路径、布局、存在性或文件类型违反契约时抛出。
        """

        _validate_source(self)


@dataclass(frozen=True, slots=True)
class ToolTraceAnalysisPolicy:
    """Tool Trace Analyzer 的诊断阈值策略。

    :param large_payload_threshold_bytes: large payload 字节阈值。
    :param payload_ranking_limit: payload 排名条目上限。
    :param latency_minimum_sample_count: latency 判断最小样本数。
    :param latency_outlier_multiplier: latency 异常倍数。
    :param latency_minimum_delta_ms: latency 异常最小绝对差值。
    :raises TypeError: 数值类型错误时抛出。
    :raises ValueError: 数值边界错误时抛出。
    """

    large_payload_threshold_bytes: int = DEFAULT_TOOL_TRACE_LARGE_PAYLOAD_THRESHOLD_BYTES
    payload_ranking_limit: int = DEFAULT_TOOL_TRACE_PAYLOAD_RANKING_LIMIT
    latency_minimum_sample_count: int = DEFAULT_TOOL_TRACE_LATENCY_MINIMUM_SAMPLE_COUNT
    latency_outlier_multiplier: float = DEFAULT_TOOL_TRACE_LATENCY_OUTLIER_MULTIPLIER
    latency_minimum_delta_ms: int = DEFAULT_TOOL_TRACE_LATENCY_MINIMUM_DELTA_MS

    def __post_init__(self) -> None:
        """校验诊断阈值。

        :returns: ``None``。
        :raises TypeError: 数值类型错误时抛出。
        :raises ValueError: 数值边界错误时抛出。
        """

        _require_positive_int(
            self.large_payload_threshold_bytes,
            field_name="large_payload_threshold_bytes",
        )
        _require_positive_int(
            self.payload_ranking_limit,
            field_name="payload_ranking_limit",
        )
        _require_positive_int(
            self.latency_minimum_sample_count,
            field_name="latency_minimum_sample_count",
        )
        if isinstance(self.latency_outlier_multiplier, bool) or not isinstance(self.latency_outlier_multiplier, float):
            raise TypeError("latency_outlier_multiplier must be float")
        if not math.isfinite(self.latency_outlier_multiplier) or self.latency_outlier_multiplier <= 1.0:
            raise ValueError("latency_outlier_multiplier must be finite and greater than 1.0")
        _require_positive_int(
            self.latency_minimum_delta_ms,
            field_name="latency_minimum_delta_ms",
        )


@dataclass(frozen=True, slots=True)
class ToolTraceEvidence:
    """Analyzer 规则引用的直接证据。

    :param kind: 证据来源类型。
    :param source_path: 证据所在本地路径。
    :param line_number: 可选 1-based cold JSONL 行号。
    :param event_id: 可选 source EventLog id。
    :param event_sequence: 可选 source EventLog sequence。
    :param event_type: 可选 source EventLog type。
    :param trace_ref: 可选 Tool Trace 定位标签。
    :param payload_ref: 可选 payload 定位标签。
    :param observed: 规则白名单选择的直接观察值；不含 raw payload。
    """

    kind: ToolTraceEvidenceKind
    source_path: Path
    line_number: int | None
    event_id: str | None
    event_sequence: int | None
    event_type: str | None
    trace_ref: str | None
    payload_ref: str | None
    observed: Mapping[str, JsonValue]

    def __post_init__(self) -> None:
        """校验证据 identity 与白名单 observation。

        :returns: ``None``。
        :raises TypeError: 字段类型错误时抛出。
        :raises ValueError: identity 数值或文本边界错误时抛出。
        """

        if not isinstance(self.kind, ToolTraceEvidenceKind):
            raise TypeError("kind must be ToolTraceEvidenceKind")
        if not isinstance(self.source_path, Path):
            raise TypeError("source_path must be Path")
        _require_optional_positive_int(self.line_number, field_name="line_number")
        _require_optional_positive_int(
            self.event_sequence,
            field_name="event_sequence",
        )
        for field_name, value in (
            ("event_id", self.event_id),
            ("event_type", self.event_type),
            ("trace_ref", self.trace_ref),
            ("payload_ref", self.payload_ref),
        ):
            _require_optional_non_empty_text(value, field_name=field_name)
        if not isinstance(self.observed, Mapping):
            raise TypeError("observed must be Mapping")


@dataclass(frozen=True, slots=True)
class ToolTraceFinding:
    """由直接证据确认的 Analyzer finding。

    :param finding_id: 由稳定排序后分层递增生成的定位 id。
    :param rule_id: 稳定规则 id。
    :param layer: 唯一语义归因层。
    :param severity: confirmed finding 严重程度。
    :param priority: operator 处置优先级。
    :param title: operator-readable 中文标题。
    :param summary: operator-readable 中文摘要。
    :param recommendation: 指向正确 owner 的建议动作。
    :param evidence: 非空直接证据。
    """

    finding_id: str
    rule_id: str
    layer: ToolTraceAnalysisLayer
    severity: ToolTraceFindingSeverity
    priority: ToolTraceFindingPriority
    title: str
    summary: str
    recommendation: str
    evidence: tuple[ToolTraceEvidence, ...]

    def __post_init__(self) -> None:
        """校验 confirmed finding contract。

        :returns: ``None``。
        :raises TypeError: enum/evidence 类型错误时抛出。
        :raises ValueError: 文本为空或 evidence 为空时抛出。
        """

        for field_name, value in (
            ("finding_id", self.finding_id),
            ("rule_id", self.rule_id),
            ("title", self.title),
            ("summary", self.summary),
            ("recommendation", self.recommendation),
        ):
            _require_non_empty_text(value, field_name=field_name)
        if not isinstance(self.layer, ToolTraceAnalysisLayer):
            raise TypeError("layer must be ToolTraceAnalysisLayer")
        if not isinstance(self.severity, ToolTraceFindingSeverity):
            raise TypeError("severity must be ToolTraceFindingSeverity")
        if not isinstance(self.priority, ToolTraceFindingPriority):
            raise TypeError("priority must be ToolTraceFindingPriority")
        if not self.evidence or not all(
            isinstance(item, ToolTraceEvidence) for item in self.evidence
        ):
            raise ValueError("finding evidence must be non-empty ToolTraceEvidence")


@dataclass(frozen=True, slots=True)
class ToolTraceLimitation:
    """Analyzer 无法证明某项语义时的 structured limitation。

    :param reason_code: 稳定 limitation 原因码。
    :param signal_status: 固定为 ``limited_signal``。
    :param summary: operator-readable 中文说明。
    :param evidence: 可为空的直接相关证据。
    """

    reason_code: str
    signal_status: ToolTraceSignalStatus
    summary: str
    evidence: tuple[ToolTraceEvidence, ...]

    def __post_init__(self) -> None:
        """校验 limitation 与 confirmed finding 分离不变量。

        :returns: ``None``。
        :raises TypeError: evidence 类型错误时抛出。
        :raises ValueError: reason/summary 为空或 status 非 limited 时抛出。
        """

        _require_non_empty_text(self.reason_code, field_name="reason_code")
        _require_non_empty_text(self.summary, field_name="summary")
        if self.signal_status is not ToolTraceSignalStatus.LIMITED_SIGNAL:
            raise ValueError("limitation signal_status must be limited_signal")
        if not all(isinstance(item, ToolTraceEvidence) for item in self.evidence):
            raise TypeError("limitation evidence must contain ToolTraceEvidence")


@dataclass(frozen=True, slots=True)
class ToolTracePayloadMeasure:
    """不含 payload body 的 verified byte measure。

    :param category: 既有 owner 提供的 payload 类别。
    :param measurement_source: 精确字节计量来源。
    :param size_bytes: verified bytes。
    :param event_sequence: owner event sequence。
    :param payload_ref: payload 或 cold record 定位标签。
    :param evidence: 非空直接证据。
    """

    category: str
    measurement_source: ToolTracePayloadMeasurementSource
    size_bytes: int
    event_sequence: int
    payload_ref: str
    evidence: tuple[ToolTraceEvidence, ...]

    def __post_init__(self) -> None:
        """校验 verified byte measure。

        :returns: ``None``。
        :raises TypeError: measurement/evidence 类型错误时抛出。
        :raises ValueError: category/ref/size/sequence/evidence 边界错误时抛出。
        """

        _require_non_empty_text(self.category, field_name="category")
        if not isinstance(
            self.measurement_source,
            ToolTracePayloadMeasurementSource,
        ):
            raise TypeError(
                "measurement_source must be ToolTracePayloadMeasurementSource"
            )
        _require_non_negative_int(self.size_bytes, field_name="size_bytes")
        _require_positive_int(self.event_sequence, field_name="event_sequence")
        _require_non_empty_text(self.payload_ref, field_name="payload_ref")
        if not self.evidence or not all(
            isinstance(item, ToolTraceEvidence) for item in self.evidence
        ):
            raise ValueError(
                "payload measure evidence must be non-empty ToolTraceEvidence"
            )


@dataclass(frozen=True, slots=True)
class ToolTraceRunSummary:
    """按直接 identity 聚合的单个 Run 摘要。

    :param run_id: source Run id。
    :param session_ids: 直接出现的 Session ids。
    :param attempt_ids: 直接出现的 Attempt ids。
    :param execution_ids: 直接出现的 execution ids。
    :param tool_call_ids: 直接出现的 tool-call ids。
    :param tool_names: 直接出现的工具名。
    :param provider_request_ids: 直接出现的 provider request ids。
    :param client_correlation_ids: 直接出现的 client correlation ids。
    :param diagnostic_refs: 直接出现的 diagnostic refs。
    :param event_count: 当前可信 dataset 中的 event 数。
    :param tool_request_count: ``TOOL_CALL_REQUESTED`` 数。
    :param tool_result_count: ``TOOL_RESULT_ACCEPTED`` 数。
    :param tool_timing_sample_count: source-owned available timing 数。
    :param context_pressure_observation_count: direct context pressure signal 数。
    :param tool_awaiting_count: ``TOOL_AWAITING`` timeline 数。
    :param run_waiting_count: ``RUN_WAITING`` timeline 数。
    """

    run_id: str
    session_ids: tuple[str, ...]
    attempt_ids: tuple[str, ...]
    execution_ids: tuple[str, ...]
    tool_call_ids: tuple[str, ...]
    tool_names: tuple[str, ...]
    provider_request_ids: tuple[str, ...]
    client_correlation_ids: tuple[str, ...]
    diagnostic_refs: tuple[str, ...]
    event_count: int
    tool_request_count: int
    tool_result_count: int
    tool_timing_sample_count: int
    context_pressure_observation_count: int
    tool_awaiting_count: int
    run_waiting_count: int

    def __post_init__(self) -> None:
        """校验 Run summary identity 与非负计数。

        :returns: ``None``。
        :raises TypeError: identity collection 或 count 类型错误时抛出。
        :raises ValueError: identity 为空或 count 为负时抛出。
        """

        _require_non_empty_text(self.run_id, field_name="run_id")
        for field_name, values in (
            ("session_ids", self.session_ids),
            ("attempt_ids", self.attempt_ids),
            ("execution_ids", self.execution_ids),
            ("tool_call_ids", self.tool_call_ids),
            ("tool_names", self.tool_names),
            ("provider_request_ids", self.provider_request_ids),
            ("client_correlation_ids", self.client_correlation_ids),
            ("diagnostic_refs", self.diagnostic_refs),
        ):
            _require_text_tuple(values, field_name=field_name)
        for field_name, value in (
            ("event_count", self.event_count),
            ("tool_request_count", self.tool_request_count),
            ("tool_result_count", self.tool_result_count),
            ("tool_timing_sample_count", self.tool_timing_sample_count),
            (
                "context_pressure_observation_count",
                self.context_pressure_observation_count,
            ),
            ("tool_awaiting_count", self.tool_awaiting_count),
            ("run_waiting_count", self.run_waiting_count),
        ):
            _require_non_negative_int(value, field_name=field_name)


@dataclass(frozen=True, slots=True)
class ToolTraceCompactorResponseSummary:
    """Tool Trace analysis 的安全 compactor response 摘要。

    :param parent_host_run_id: compactor manifest 绑定的 parent Host Run id。
    :param disposition: accepted 或 attempt-rejected terminal。
    :param terminal_event_id: canonical terminal event id。
    :param terminal_event_sequence: canonical terminal sequence。
    :param compaction_operation_id: compaction operation id。
    :param compaction_attempt_number: proposal attempt 序号。
    :param proposal_manifest_ref: exact proposal manifest ref。
    :param proposal_manifest_digest: exact proposal manifest digest。
    :param effective_provider: 实际成功 response provider；no-success rejection
        时为 ``None``。
    :param effective_model: 实际成功 response model；no-success rejection 时为
        ``None``。
    :param runner_request_identity: 实际终结调用 request identity；no-success
        rejection 时为 ``None``。
    :param provider_request_id_availability: provider request id availability；
        no-success rejection 时为 ``None``。
    :param provider_request_id: provider-native request id；不可用或 no-success
        rejection 时为 ``None``。
    """

    parent_host_run_id: str
    disposition: CompactorResponseDisposition
    terminal_event_id: str
    terminal_event_sequence: int
    compaction_operation_id: str
    compaction_attempt_number: int
    proposal_manifest_ref: str
    proposal_manifest_digest: str
    effective_provider: str | None
    effective_model: str | None
    runner_request_identity: RunnerRequestIdentity | None
    provider_request_id_availability: ProviderRequestIdAvailability | None
    provider_request_id: str | None

    def __post_init__(self) -> None:
        """校验 response summary 的 binding 与 nullable identity cohesion。

        :returns: 无返回值。
        :raises TypeError: enum、identity 或字段类型非法时抛出。
        :raises ValueError: binding 为空、数值非正或 nullable identity 分裂时抛出。
        """

        for field_name, value in (
            ("parent_host_run_id", self.parent_host_run_id),
            ("terminal_event_id", self.terminal_event_id),
            ("compaction_operation_id", self.compaction_operation_id),
            ("proposal_manifest_ref", self.proposal_manifest_ref),
            ("proposal_manifest_digest", self.proposal_manifest_digest),
        ):
            _require_non_empty_text(value, field_name=field_name)
        if not isinstance(self.disposition, CompactorResponseDisposition):
            raise TypeError("disposition must be CompactorResponseDisposition")
        _require_positive_int(
            self.terminal_event_sequence,
            field_name="terminal_event_sequence",
        )
        _require_positive_int(
            self.compaction_attempt_number,
            field_name="compaction_attempt_number",
        )
        identity_values = (
            self.effective_provider,
            self.effective_model,
            self.runner_request_identity,
            self.provider_request_id_availability,
        )
        if self.runner_request_identity is None:
            if self.disposition is CompactorResponseDisposition.ACCEPTED:
                raise ValueError(
                    "accepted compactor response summary requires successful identity"
                )
            if any(value is not None for value in identity_values):
                raise ValueError(
                    "no-success compactor response identity fields must all be null"
                )
            if self.provider_request_id is not None:
                raise ValueError(
                    "no-success compactor provider_request_id must be null"
                )
            return
        if not isinstance(self.runner_request_identity, RunnerRequestIdentity):
            raise TypeError(
                "runner_request_identity must be RunnerRequestIdentity or None"
            )
        _require_optional_non_empty_text(
            self.effective_provider,
            field_name="effective_provider",
        )
        _require_optional_non_empty_text(
            self.effective_model,
            field_name="effective_model",
        )
        if self.effective_provider is None or self.effective_model is None:
            raise ValueError("successful compactor provider/model must be present")
        if not isinstance(
            self.provider_request_id_availability,
            ProviderRequestIdAvailability,
        ):
            raise TypeError(
                "provider_request_id_availability must be ProviderRequestIdAvailability"
            )
        if (
            self.provider_request_id_availability
            is ProviderRequestIdAvailability.PRESENT
        ):
            _require_optional_non_empty_text(
                self.provider_request_id,
                field_name="provider_request_id",
            )
            if self.provider_request_id is None:
                raise ValueError("present provider request id must have value")
        elif self.provider_request_id is not None:
            raise ValueError("unavailable provider request id must be null")


@dataclass(frozen=True, slots=True)
class ToolTraceVendorDebuggingBlock:
    """Provider/vendor 报障所需的最终冻结 block shape。

    :param status: block signal 完整性。
    :param provider_request_id: typed provider request id；不可由本地 id 代替。
    :param client_correlation_id: typed client correlation id。
    :param session_id: direct diagnostic source Session id。
    :param run_id: direct diagnostic source Run id。
    :param attempt_ids: 去重稳定排序的 Attempt ids。
    :param execution_ids: 去重稳定排序的 execution ids。
    :param iteration_ids: 去重稳定排序的 typed iteration ids。
    :param tool_trace_refs: 非空 direct Tool Trace evidence。
    :param diagnostic_refs: 去重稳定排序的 diagnostic refs。
    :param partial_tool_call_signal: partial tool-call signal coverage。
    :param limitations: block-local limitations。
    """

    status: ToolTraceSignalStatus
    provider_request_id: str | None
    client_correlation_id: str | None
    session_id: str
    run_id: str
    attempt_ids: tuple[str, ...]
    execution_ids: tuple[str, ...]
    iteration_ids: tuple[str, ...]
    tool_trace_refs: tuple[ToolTraceEvidence, ...]
    diagnostic_refs: tuple[str, ...]
    partial_tool_call_signal: ToolTraceSignalStatus
    limitations: tuple[ToolTraceLimitation, ...]

    def __post_init__(self) -> None:
        """校验冻结 vendor debugging block contract。

        :returns: ``None``。
        :raises TypeError: enum/tuple 元素类型错误时抛出。
        :raises ValueError: trigger block status、identity 或 evidence 不合法时抛出。
        """

        if self.status not in (
            ToolTraceSignalStatus.AVAILABLE,
            ToolTraceSignalStatus.LIMITED_SIGNAL,
        ):
            raise ValueError("vendor block status must be available or limited_signal")
        _require_optional_non_empty_text(
            self.provider_request_id,
            field_name="provider_request_id",
        )
        _require_optional_non_empty_text(
            self.client_correlation_id,
            field_name="client_correlation_id",
        )
        _require_non_empty_text(self.session_id, field_name="session_id")
        _require_non_empty_text(self.run_id, field_name="run_id")
        for field_name, values in (
            ("attempt_ids", self.attempt_ids),
            ("execution_ids", self.execution_ids),
            ("iteration_ids", self.iteration_ids),
            ("diagnostic_refs", self.diagnostic_refs),
        ):
            _require_text_tuple(values, field_name=field_name)
        if not self.tool_trace_refs or not all(
            isinstance(item, ToolTraceEvidence) for item in self.tool_trace_refs
        ):
            raise ValueError(
                "vendor tool_trace_refs must be non-empty ToolTraceEvidence"
            )
        if not isinstance(self.partial_tool_call_signal, ToolTraceSignalStatus):
            raise TypeError(
                "partial_tool_call_signal must be ToolTraceSignalStatus"
            )
        if not all(
            isinstance(item, ToolTraceLimitation) for item in self.limitations
        ):
            raise TypeError("vendor limitations must contain ToolTraceLimitation")


@dataclass(frozen=True, slots=True)
class ToolTraceAnalysisCapabilities:
    """本次实际可信输入能力。

    :param cold: 是否取得 cold prefix snapshot。
    :param hot: 是否取得 hot SQLite snapshot。
    :param payload_resolution: 是否具备 hot/artifact resolver 路径。
    """

    cold: bool
    hot: bool
    payload_resolution: bool

    def __post_init__(self) -> None:
        """校验 capability flags 是严格 bool。

        :returns: ``None``。
        :raises TypeError: 任一 flag 不是 bool 时抛出。
        """

        for field_name, value in (
            ("cold", self.cold),
            ("hot", self.hot),
            ("payload_resolution", self.payload_resolution),
        ):
            if not isinstance(value, bool):
                raise TypeError(f"{field_name} must be bool")


@dataclass(frozen=True, slots=True)
class ToolTraceAnalysisInputSummary:
    """structured report 的输入快照说明。

    :param requested_path: operator 请求路径。
    :param mode: 输入模式。
    :param cold_jsonl_path: expected cold JSONL 路径。
    :param cold_lock_path: Host owner 从 expected ``cold_jsonl_path`` 唯一派生的
        expected lock path；只有 ``capabilities.cold=true`` 才表示本次实际获取
        该路径的锁并读取 cold snapshot。
    :param hot_db_path: 可选 expected hot DB 路径。
    :param artifact_root: 可选 artifact root。
    :param capabilities: 本次实际读取能力。
    :param hot_event_sequence_watermark: hot snapshot watermark。
    """

    requested_path: Path
    mode: ToolTraceInputMode
    cold_jsonl_path: Path
    cold_lock_path: Path
    hot_db_path: Path | None
    artifact_root: Path | None
    capabilities: ToolTraceAnalysisCapabilities
    hot_event_sequence_watermark: int | None

    def __post_init__(self) -> None:
        """校验 report input snapshot 的 typed facts 与 capability 关系。

        :returns: ``None``。
        :raises TypeError: 路径、mode、capabilities 或 watermark 类型错误时抛出。
        :raises ValueError: hot/payload capability 与 watermark/path 关系不一致时抛出。
        """

        for field_name, value in (
            ("requested_path", self.requested_path),
            ("cold_jsonl_path", self.cold_jsonl_path),
            ("cold_lock_path", self.cold_lock_path),
        ):
            if not isinstance(value, Path):
                raise TypeError(f"{field_name} must be Path")
        for field_name, value in (
            ("hot_db_path", self.hot_db_path),
            ("artifact_root", self.artifact_root),
        ):
            if value is not None and not isinstance(value, Path):
                raise TypeError(f"{field_name} must be Path or None")
        if not isinstance(self.mode, ToolTraceInputMode):
            raise TypeError("mode must be ToolTraceInputMode")
        if not isinstance(self.capabilities, ToolTraceAnalysisCapabilities):
            raise TypeError(
                "capabilities must be ToolTraceAnalysisCapabilities"
            )
        watermark = self.hot_event_sequence_watermark
        if watermark is not None:
            _require_non_negative_int(
                watermark,
                field_name="hot_event_sequence_watermark",
            )
        if self.capabilities.hot:
            if self.hot_db_path is None:
                raise ValueError("hot capability requires hot_db_path")
            if watermark is None:
                raise ValueError("hot capability requires hot watermark")
        elif watermark is not None:
            raise ValueError("hot watermark requires hot capability")
        if self.capabilities.payload_resolution and (
            not self.capabilities.hot or self.artifact_root is None
        ):
            raise ValueError(
                "payload resolution requires hot capability and artifact_root"
            )


@dataclass(frozen=True, slots=True)
class ToolTraceSignalCoverage:
    """单类 Analyzer signal coverage。

    :param signal_name: 稳定 signal 名。
    :param status: available/limited/not-applicable。
    :param reason_codes: 去重稳定排序的 limitation reasons。
    """

    signal_name: str
    status: ToolTraceSignalStatus
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        """校验 signal coverage contract。

        :returns: ``None``。
        :raises TypeError: status 或 reason tuple 类型错误时抛出。
        :raises ValueError: signal name 为空时抛出。
        """

        _require_non_empty_text(self.signal_name, field_name="signal_name")
        if not isinstance(self.status, ToolTraceSignalStatus):
            raise TypeError("status must be ToolTraceSignalStatus")
        _require_text_tuple(self.reason_codes, field_name="reason_codes")


@dataclass(frozen=True, slots=True)
class ToolTraceAnalysisSummary:
    """structured report 顶层计数摘要。

    :param valid_record_count: strict parser 接受的唯一 cold records。
    :param invalid_record_count: 被 input integrity 排除的 cold records。
    :param run_count: direct run identity 数。
    :param tool_call_count: direct tool-call identity 数。
    :param finding_count: confirmed finding 数。
    :param limitation_count: limitation 数。
    """

    valid_record_count: int
    invalid_record_count: int
    run_count: int
    tool_call_count: int
    finding_count: int
    limitation_count: int

    def __post_init__(self) -> None:
        """校验 report summary 计数。

        :returns: ``None``。
        :raises TypeError: 计数类型错误时抛出。
        :raises ValueError: 计数为负时抛出。
        """

        for field_name, value in (
            ("valid_record_count", self.valid_record_count),
            ("invalid_record_count", self.invalid_record_count),
            ("run_count", self.run_count),
            ("tool_call_count", self.tool_call_count),
            ("finding_count", self.finding_count),
            ("limitation_count", self.limitation_count),
        ):
            _require_non_negative_int(value, field_name=field_name)


@dataclass(frozen=True, slots=True)
class ToolTraceAnalysisReport:
    """Tool Trace Analyzer fresh schema version 2 structured report。

    :param schema_version: Analyzer report schema；固定为 ``2``。
    :param input: 本次输入快照说明。
    :param policy: 本次实际诊断阈值。
    :param summary: 顶层计数摘要。
    :param signal_coverage: 各类 typed signal coverage。
    :param runs: direct identity 聚合摘要。
    :param compactor_responses: canonical terminal 同源的 compactor response 摘要。
    :param payload_rankings: verified byte measures top ranking。
    :param vendor_debugging: vendor debugging blocks；S2 合法值为空元组。
    :param findings: confirmed diagnostics。
    :param limitations: 无法证明的 signal coverage。
    """

    schema_version: int
    input: ToolTraceAnalysisInputSummary
    policy: ToolTraceAnalysisPolicy
    summary: ToolTraceAnalysisSummary
    signal_coverage: tuple[ToolTraceSignalCoverage, ...]
    runs: tuple[ToolTraceRunSummary, ...]
    compactor_responses: tuple[ToolTraceCompactorResponseSummary, ...]
    payload_rankings: tuple[ToolTracePayloadMeasure, ...]
    vendor_debugging: tuple[ToolTraceVendorDebuggingBlock, ...]
    findings: tuple[ToolTraceFinding, ...]
    limitations: tuple[ToolTraceLimitation, ...]

    def __post_init__(self) -> None:
        """校验最终 report schema 与嵌套 public contract 类型。

        :returns: ``None``。
        :raises TypeError: 嵌套 contract 类型错误时抛出。
        :raises ValueError: schema version 或 summary count 不一致时抛出。
        """

        if self.schema_version != 2:
            raise ValueError("analysis report schema_version must be 2")
        if not isinstance(self.input, ToolTraceAnalysisInputSummary):
            raise TypeError("input must be ToolTraceAnalysisInputSummary")
        if not isinstance(self.policy, ToolTraceAnalysisPolicy):
            raise TypeError("policy must be ToolTraceAnalysisPolicy")
        if not isinstance(self.summary, ToolTraceAnalysisSummary):
            raise TypeError("summary must be ToolTraceAnalysisSummary")
        _require_contract_tuple(
            self.signal_coverage,
            ToolTraceSignalCoverage,
            field_name="signal_coverage",
        )
        _require_contract_tuple(self.runs, ToolTraceRunSummary, field_name="runs")
        _require_contract_tuple(
            self.compactor_responses,
            ToolTraceCompactorResponseSummary,
            field_name="compactor_responses",
        )
        _require_contract_tuple(
            self.payload_rankings,
            ToolTracePayloadMeasure,
            field_name="payload_rankings",
        )
        _require_contract_tuple(
            self.vendor_debugging,
            ToolTraceVendorDebuggingBlock,
            field_name="vendor_debugging",
        )
        _require_contract_tuple(
            self.findings,
            ToolTraceFinding,
            field_name="findings",
        )
        _require_contract_tuple(
            self.limitations,
            ToolTraceLimitation,
            field_name="limitations",
        )
        if self.summary.run_count != len(self.runs):
            raise ValueError("summary run_count must match runs")
        if self.summary.finding_count != len(self.findings):
            raise ValueError("summary finding_count must match findings")
        if self.summary.limitation_count != len(self.limitations):
            raise ValueError("summary limitation_count must match limitations")
        response_keys = tuple(
            (
                item.parent_host_run_id,
                item.compaction_operation_id,
                item.compaction_attempt_number,
                item.terminal_event_sequence,
            )
            for item in self.compactor_responses
        )
        if response_keys != tuple(sorted(response_keys)):
            raise ValueError("compactor_responses must use stable owner ordering")
        if len(set(response_keys)) != len(response_keys):
            raise ValueError("compactor_responses must be unique")
        finding_ids = tuple(finding.finding_id for finding in self.findings)
        if any(finding_id == "" for finding_id in finding_ids):
            raise ValueError("report finding ids must be non-empty")
        if len(set(finding_ids)) != len(finding_ids):
            raise ValueError("report finding ids must be unique")


def _validate_source(source: ToolTraceAnalysisSource) -> None:
    """校验 Tool Trace 输入来源。

    :param source: 待校验来源。
    :returns: ``None``。
    :raises TypeError: 字段类型错误时抛出。
    :raises ValueError: 路径、布局、存在性或文件类型违反契约时抛出。
    """

    if not isinstance(source.mode, ToolTraceInputMode):
        raise TypeError("mode must be ToolTraceInputMode")
    _require_absolute_normalized_path(
        source.requested_path,
        field_name="requested_path",
    )
    _require_absolute_normalized_path(
        source.cold_jsonl_path,
        field_name="cold_jsonl_path",
    )
    if source.hot_db_path is not None:
        _require_absolute_normalized_path(
            source.hot_db_path,
            field_name="hot_db_path",
        )
    if source.artifact_root is not None:
        _require_absolute_normalized_path(
            source.artifact_root,
            field_name="artifact_root",
        )

    if source.mode is ToolTraceInputMode.COLD_FILE:
        _validate_cold_file_source(source)
    elif source.mode is ToolTraceInputMode.WORKSPACE_DIRECTORY:
        _validate_directory_source(
            source,
            dayu_root=source.requested_path / _DAYU_DIRECTORY_NAME,
        )
    elif source.mode is ToolTraceInputMode.DAYU_DIRECTORY:
        _validate_directory_source(source, dayu_root=source.requested_path)
    else:
        _validate_trace_directory_source(source)
    _reject_path_aliases(source)


def _validate_cold_file_source(source: ToolTraceAnalysisSource) -> None:
    """校验 cold-file 模式。

    :param source: 待校验来源。
    :returns: ``None``。
    :raises ValueError: 模式字段或文件类型不符合契约时抛出。
    """

    if source.cold_jsonl_path != source.requested_path:
        raise ValueError("cold_file cold_jsonl_path must equal requested_path")
    if source.hot_db_path is not None or source.artifact_root is not None:
        raise ValueError("cold_file must not carry hot_db_path or artifact_root")
    _require_regular_file(source.requested_path, field_name="requested_path")


def _validate_directory_source(
    source: ToolTraceAnalysisSource,
    *,
    dayu_root: Path,
) -> None:
    """校验 workspace/dayu directory 模式。

    :param source: 待校验来源。
    :param dayu_root: 当前模式预期的 ``.dayu`` 根或其内容根。
    :returns: ``None``。
    :raises ValueError: 布局、存在性或文件类型不符合契约时抛出。
    """

    _require_directory(source.requested_path, field_name="requested_path")
    expected_artifact_root = dayu_root / _ARTIFACT_DIRECTORY_NAME
    expected_cold_path = expected_artifact_root / _TOOL_TRACE_DIRECTORY_NAME / _TOOL_TRACE_COLD_FILE_NAME
    expected_hot_path = dayu_root / _HOST_DIRECTORY_NAME / _HOST_DATABASE_FILE_NAME
    if source.cold_jsonl_path != expected_cold_path:
        raise ValueError("cold_jsonl_path does not match input mode layout")
    if source.hot_db_path != expected_hot_path:
        raise ValueError("hot_db_path does not match input mode layout")
    if source.artifact_root != expected_artifact_root:
        raise ValueError("artifact_root does not match input mode layout")
    cold_exists = _path_exists(
        source.cold_jsonl_path,
        field_name="cold_jsonl_path",
    )
    hot_exists = _path_exists(expected_hot_path, field_name="hot_db_path")
    if not cold_exists and not hot_exists:
        raise ValueError("directory input requires hot DB or cold JSONL")
    if cold_exists:
        _require_regular_file(source.cold_jsonl_path, field_name="cold_jsonl_path")
    if hot_exists:
        _require_regular_file(expected_hot_path, field_name="hot_db_path")
    if _path_exists(expected_artifact_root, field_name="artifact_root"):
        _require_directory(expected_artifact_root, field_name="artifact_root")


def _validate_trace_directory_source(source: ToolTraceAnalysisSource) -> None:
    """校验 trace-directory 模式。

    :param source: 待校验来源。
    :returns: ``None``。
    :raises ValueError: 模式字段、布局或文件类型不符合契约时抛出。
    """

    _require_directory(source.requested_path, field_name="requested_path")
    expected_cold_path = source.requested_path / _TOOL_TRACE_COLD_FILE_NAME
    if source.cold_jsonl_path != expected_cold_path:
        raise ValueError("trace_directory cold_jsonl_path does not match layout")
    if source.hot_db_path is not None or source.artifact_root is not None:
        raise ValueError("trace_directory must not carry hot_db_path or artifact_root")
    _require_regular_file(source.cold_jsonl_path, field_name="cold_jsonl_path")


def _reject_path_aliases(source: ToolTraceAnalysisSource) -> None:
    """拒绝来源中承担不同语义的路径互相 alias。

    :param source: 已通过 mode 布局检查的来源。
    :returns: ``None``。
    :raises ValueError: 两个不同语义路径指向同一文件系统对象时抛出。
    """

    paths = tuple(
        path
        for path in (
            source.cold_jsonl_path,
            source.hot_db_path,
            source.artifact_root,
        )
        if path is not None
    )
    for index, left in enumerate(paths):
        for right in paths[index + 1 :]:
            if left == right:
                raise ValueError("analysis source paths must not alias")
            if (
                _path_exists(left, field_name="analysis source path")
                and _path_exists(right, field_name="analysis source path")
                and left.samefile(right)
            ):
                raise ValueError("analysis source paths must not alias")


def _require_absolute_normalized_path(value: Path, *, field_name: str) -> None:
    """校验绝对、词法归一化路径。

    :param value: 待校验路径。
    :param field_name: 错误消息字段名。
    :returns: ``None``。
    :raises TypeError: 值不是 ``Path`` 时抛出。
    :raises ValueError: 路径不是绝对归一化路径时抛出。
    """

    if not isinstance(value, Path):
        raise TypeError(f"{field_name} must be Path")
    if not value.is_absolute():
        raise ValueError(f"{field_name} must be absolute")
    if Path(os.path.normpath(os.fspath(value))) != value:
        raise ValueError(f"{field_name} must be normalized")


def _require_regular_file(value: Path, *, field_name: str) -> None:
    """校验现存 regular file。

    :param value: 待校验路径。
    :param field_name: 错误消息字段名。
    :returns: ``None``。
    :raises ValueError: 路径缺失或不是 regular file 时抛出。
    """

    try:
        mode = value.stat().st_mode
    except OSError as exc:
        raise ValueError(f"{field_name} must be an existing regular file") from exc
    if not stat.S_ISREG(mode):
        raise ValueError(f"{field_name} must be an existing regular file")


def _path_exists(value: Path, *, field_name: str) -> bool:
    """在不吞掉 permission/I/O error 的前提下判断路径是否缺失。

    :param value: 待检查路径。
    :param field_name: 错误消息字段名。
    :returns: 路径存在时返回 ``True``，确实缺失时返回 ``False``。
    :raises ValueError: 除缺失外的 metadata 读取失败时抛出。
    """

    try:
        value.stat()
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise ValueError(f"{field_name} metadata is unreadable") from exc
    return True


def _require_directory(value: Path, *, field_name: str) -> None:
    """校验现存 directory。

    :param value: 待校验路径。
    :param field_name: 错误消息字段名。
    :returns: ``None``。
    :raises ValueError: 路径缺失或不是 directory 时抛出。
    """

    try:
        mode = value.stat().st_mode
    except OSError as exc:
        raise ValueError(f"{field_name} must be an existing directory") from exc
    if not stat.S_ISDIR(mode):
        raise ValueError(f"{field_name} must be an existing directory")


def _require_positive_int(value: int, *, field_name: str) -> None:
    """校验正整数。

    :param value: 待校验值。
    :param field_name: 错误消息字段名。
    :returns: ``None``。
    :raises TypeError: 值不是整数或是布尔值时抛出。
    :raises ValueError: 值不是正数时抛出。
    """

    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be int")
    if value <= 0:
        raise ValueError(f"{field_name} must be positive")


def _require_non_negative_int(value: int, *, field_name: str) -> None:
    """校验非负整数并拒绝 bool。

    :param value: 待校验值。
    :param field_name: 错误消息字段名。
    :returns: ``None``。
    :raises TypeError: 值不是严格整数时抛出。
    :raises ValueError: 值为负时抛出。
    """

    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be int")
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative")


def _require_optional_positive_int(
    value: int | None,
    *,
    field_name: str,
) -> None:
    """校验可选正整数。

    :param value: 待校验可选值。
    :param field_name: 错误消息字段名。
    :returns: ``None``。
    :raises TypeError: 非空值不是严格整数时抛出。
    :raises ValueError: 非空值不是正数时抛出。
    """

    if value is not None:
        _require_positive_int(value, field_name=field_name)


def _require_non_empty_text(value: str, *, field_name: str) -> None:
    """校验非空文本。

    :param value: 待校验值。
    :param field_name: 错误消息字段名。
    :returns: ``None``。
    :raises TypeError: 值不是文本时抛出。
    :raises ValueError: 文本为空时抛出。
    """

    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str")
    if value == "":
        raise ValueError(f"{field_name} must not be empty")


def _require_optional_non_empty_text(
    value: str | None,
    *,
    field_name: str,
) -> None:
    """校验可选非空文本。

    :param value: 待校验可选值。
    :param field_name: 错误消息字段名。
    :returns: ``None``。
    :raises TypeError: 非空值不是文本时抛出。
    :raises ValueError: 非空文本为空时抛出。
    """

    if value is not None:
        _require_non_empty_text(value, field_name=field_name)


def _require_text_tuple(
    values: tuple[str, ...],
    *,
    field_name: str,
) -> None:
    """校验严格非空文本元组。

    :param values: 待校验元组。
    :param field_name: 错误消息字段名。
    :returns: ``None``。
    :raises TypeError: 值不是 tuple 或元素不是文本时抛出。
    :raises ValueError: 任一元素为空时抛出。
    """

    if not isinstance(values, tuple):
        raise TypeError(f"{field_name} must be tuple")
    for value in values:
        _require_non_empty_text(value, field_name=field_name)


def _require_contract_tuple(
    values: tuple[_ContractT, ...],
    expected_type: type[_ContractT],
    *,
    field_name: str,
) -> None:
    """校验 public contract 元组元素类型。

    :param values: 待校验元组。
    :param expected_type: 唯一允许的 public contract 类型。
    :param field_name: 错误消息字段名。
    :returns: ``None``。
    :raises TypeError: 值不是 tuple 或存在错误元素类型时抛出。
    """

    if not isinstance(values, tuple) or not all(
        isinstance(item, expected_type) for item in values
    ):
        raise TypeError(f"{field_name} must contain {expected_type.__name__}")


__all__ = [
    "DEFAULT_TOOL_TRACE_LARGE_PAYLOAD_THRESHOLD_BYTES",
    "DEFAULT_TOOL_TRACE_LATENCY_MINIMUM_DELTA_MS",
    "DEFAULT_TOOL_TRACE_LATENCY_MINIMUM_SAMPLE_COUNT",
    "DEFAULT_TOOL_TRACE_LATENCY_OUTLIER_MULTIPLIER",
    "DEFAULT_TOOL_TRACE_PAYLOAD_RANKING_LIMIT",
    "ToolTraceAnalysisCapabilities",
    "ToolTraceAnalysisInputSummary",
    "ToolTraceAnalysisLayer",
    "ToolTraceAnalysisPolicy",
    "ToolTraceAnalysisReport",
    "ToolTraceAnalysisSource",
    "ToolTraceAnalysisSummary",
    "ToolTraceCompactorResponseSummary",
    "ToolTraceEvidence",
    "ToolTraceEvidenceKind",
    "ToolTraceFinding",
    "ToolTraceFindingPriority",
    "ToolTraceFindingSeverity",
    "ToolTraceInputMode",
    "ToolTraceLimitation",
    "ToolTracePayloadMeasurementSource",
    "ToolTracePayloadMeasure",
    "ToolTraceRunSummary",
    "ToolTraceSignalCoverage",
    "ToolTraceSignalStatus",
    "ToolTraceVendorDebuggingBlock",
]
