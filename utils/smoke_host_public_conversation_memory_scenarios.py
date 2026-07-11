"""Host public 财报对话记忆场景 smoke 的 runtime flow。

本模块是 Gateflow S1b 的 Host public smoke runtime flow：通过
``ConfigLoader``、``resolve_runtime_locations``、``prepare_scene``、
``discover_service_tools``、``compose_open_host_options`` 与
``compose_submit_followup_request`` 完成 Service-like 装配，然后只使用
``open_host`` 返回的 public Host handle 执行多轮财报对话记忆场景。

脚本不读取 durable store、EventLog、memory 表、compact payload 内容或
private Host implementation；所有财报事实均来自 deterministic mock tool。
``compact`` suite 额外观察本次 session 的 compact public event 与 compact
artifact 文件数作为验收信号。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import pathlib
import re
import sys
from collections import Counter
from collections.abc import AsyncIterator, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from math import floor
from typing import Final, Protocol, cast
from uuid import uuid4

_PROJECT_ROOT: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from dayu.contracts import (
    AsyncDirectToolExecutionCapability,
    JsonValue,
    ToolBundle,
    ToolBundleSourceKind,
    ToolBundleSourceRef,
)
from dayu.contracts.tool_call import (
    BatchToolExecutionContext,
    ToolCallRequest,
)
from dayu.contracts.tool_declaration import ToolDefinition
from dayu.contracts.tool_outcome import (
    ToolCompletedOutcome,
    ToolExecutionOutcome,
)
from dayu.contracts.tool_result import ToolResultSuccess
from dayu.contracts.tool_schema import (
    ToolFunctionSchema,
    ToolParametersSchema,
    ToolSchema,
)
from dayu.engine.contracts.agent_run import (
    AgentRunRequest,
    AgentRunResult,
    EngineRunOutcomeFinalAnswer,
)
from dayu.engine.contracts.engine_events import (
    ContextCompactionRequestedData,
    EngineEvent,
    EngineEventType,
    FinalAnswerData,
)
from dayu.engine.contracts.finish_reason import FinishReason
from dayu.engine.contracts.messages import AgentMessage, AgentMessageRole, UserMessage
import dayu.host.llm_compaction as llm_compaction
from dayu.host import (
    AttemptDispatchSnapshot,
    AuthorizationClaim,
    EnsureSessionRequest,
    FollowupBehavior,
    Host,
    HostCallContext,
    HostEvent,
    HostEventKind,
    LocalEngineWorker,
    LocalEngineWorkerFactory,
    LocalWorkerHandle,
    OpenHostOptions,
    OperationContext,
    SessionSnapshot,
    SessionStatus,
    open_host,
)
from dayu.host.compaction import (
    CONVERSATION_COMPACT_OUTPUT_SCHEMA_VERSION_VNEXT,
    ForwardIntentStatusVNext,
    ForwardIntentTypeVNext,
    ReferenceContinuityReasonVNext,
)
from dayu.host.context_budget import DEFAULT_ESTIMATOR_CHARS_PER_TOKEN
from dayu.host.context_events import (
    CONTEXT_COMPACTED,
    CONTEXT_COMPACTION_ATTEMPT_REJECTED,
    CONTEXT_COMPACTION_FAILED,
    CONTEXT_COMPACTION_REQUESTED,
)
from dayu.host.durable.connection import open_host_durable_store
from dayu.host.durable.event_log import (
    EventClass,
    EventLogReadClassFilter,
    EventLogReadFilter,
    EventLogRow,
    EventLogStore,
)
from dayu.host.durable.options import (
    HostDurableStoreOptions,
    HostSQLiteStoragePolicy,
    PayloadStoragePolicy,
)
from dayu.host.durable.transaction import HostTransaction
from dayu.host.memory import MemoryProjectionPolicy
from dayu.runtime.config_loader import ConfigLoader, RuntimeConfig
from dayu.runtime.location import resolve_runtime_locations
from dayu.runtime.log import LogLevel, configure
from dayu.runtime.scene_prepare import (
    PreparedSceneInputs,
    ScenePrepareRequest,
    SceneToolCatalog,
    prepare_scene,
)
from dayu.runtime.tools_discovery import (
    PythonImportPathProvider,
    ToolsDiscovery,
    ToolsDiscoveryProviderBinding,
    ToolsDiscoveryProviderOutput,
    ToolsDiscoveryProviderSpec,
    ToolsDiscoveryResult,
)
from dayu.service.host_assembly import (
    ServiceAssemblyOverrides,
    ServiceDiscoveredTools,
    ServiceOpenHostAssemblyDiagnostics,
    ServiceOpenHostAssemblyRequest,
    assemble_effective_tool_provider_configs,
    compose_open_host_options,
    compose_submit_followup_request,
    discover_service_tools,
)
from dayu.service.scene_context import CURRENT_TIME_SLOT, current_time
from utils.smoke_host_public_diagnostics import (
    print_duplicate_governance_diagnostics,
)

_PACKAGE_CONFIG_ROOT: Final[pathlib.Path] = _PROJECT_ROOT / "dayu" / "config"
_DEFAULT_WORKSPACE_PARENT: Final[pathlib.Path] = _PROJECT_ROOT / "workspace" / "tmp"
_DEFAULT_WORKSPACE_PREFIX: Final[str] = "host-public-conversation-memory-scenarios-smoke"
_DEFAULT_SCENE_ID: Final[str] = "smoke_host_public_conversation_memory_scenarios"
_DEFAULT_SLOT_KEY_PREFIX: Final[str] = "manual-smoke-conversation-memory-scenarios"
_DEFAULT_LOG_LEVEL: Final[str] = "INFO"
_DEFAULT_LONG_ROUNDS: Final[int] = 25
_MIN_LONG_ROUNDS: Final[int] = 20
_MAX_LONG_ROUNDS: Final[int] = 25
_TOOL_NAME: Final[str] = "get_mock_finance_memory_fact"
_TOOL_TAG: Final[str] = "manual-smoke"
_PROVIDER_ID: Final[str] = "host-public-conversation-memory-scenarios-smoke"
_PROVIDER_SPEC_ID: Final[str] = "host-public-conversation-memory-scenarios-smoke"
_PROVIDER_IMPORT_DISPLAY_PATH: Final[str] = "__main__:discover_smoke_tools"
_PROVIDER_VERSION: Final[str] = "v1"
_CLIENT_REQUEST_PREFIX: Final[str] = "manual-smoke-conversation-memory-scenarios"
_DEFAULT_USER_ID: Final[str] = "manual-smoke-user"
_UNKNOWN_FACT_KEY: Final[str] = "_UNKNOWN_FACT_KEY"
_STDOUT_PRESSURE_DISABLED: Final[str] = "SMOKE PRESSURE disabled"
_STDOUT_TOOL_CALLS_BY_KEY: Final[str] = "SMOKE TOOL_CALLS_BY_KEY"
_STDOUT_PREFIX_ROUND_START: Final[str] = "SMOKE ROUND_START"
_STDOUT_PREFIX_ROUND_DONE: Final[str] = "SMOKE ROUND_DONE"
_STDOUT_PREFIX_FINAL_PREVIEW: Final[str] = "SMOKE FINAL_PREVIEW"
_STDOUT_PREFIX_SOFT_OBSERVE: Final[str] = "SMOKE SOFT_OBSERVE"
_STDOUT_PREFIX_SESSION_OBSERVE: Final[str] = "SMOKE SESSION_OBSERVE"
_STDOUT_PREFIX_TOOL_DELTA: Final[str] = "SMOKE TOOL_DELTA"
_STDOUT_PREFIX_TOOL_CALL: Final[str] = "SMOKE TOOL_CALL"
_STDOUT_PREFIX_TOOL_EXTRA: Final[str] = "SMOKE TOOL_EXTRA"
_STDOUT_PREFIX_COMPACT_AUDIT: Final[str] = "SMOKE COMPACT_AUDIT"
_STDOUT_PREFIX_COMPACT_OPERATION: Final[str] = "SMOKE COMPACT_OPERATION"
_STDOUT_PREFIX_COMPACT_REJECT_HISTOGRAM: Final[str] = "SMOKE COMPACT_REJECT_HISTOGRAM"
_STDOUT_PREFIX_COMPACT_REJECT_DETAIL: Final[str] = "SMOKE COMPACT_REJECT_DETAIL"
_STDOUT_PREFIX_COMPACT_ACCEPTANCE: Final[str] = "SMOKE COMPACT_ACCEPTANCE"
_STDOUT_PREFIX_COMPACT_ARTIFACT_ROOT: Final[str] = "SMOKE COMPACT_ARTIFACT_ROOT"
_STDOUT_PREFIX_COMPACT_ARTIFACT_FILE_COUNT: Final[str] = "SMOKE COMPACT_ARTIFACT_FILE_COUNT"
_STDOUT_PREFIX_DETERMINISTIC_DISPATCH: Final[str] = "SMOKE DETERMINISTIC_DISPATCH"
_NO_TOOL_SELECTION: Final[frozenset[str]] = frozenset()
_MOCK_PRESSURE_UNIT: Final[str] = (
    "DAYU_MEM_SCENARIO_PRESSURE_PAD 财报场景记忆压力文本，" "仅用于 public Host conversation memory smoke。"
)
_MOCK_PRESSURE_REPEAT: Final[int] = 128
_FINAL_PREVIEW_CHARS: Final[int] = 600
_TERMINAL_TIMEOUT_SECONDS: Final[float] = 600.0
_COMPACT_PRESSURE_TARGET_EXTRA_TOKENS: Final[int] = 16_384
_COMPACT_PRESSURE_HARD_MARGIN_TOKENS: Final[int] = 24_576
# 575K 预留既有历史、固定 system/tool 消息与真实模型输出涨幅；启动期 bounds 断言负责防止该预留把 auto pressure 压到 soft threshold 以下。
_COMPACT_PRESSURE_RESERVE_TOKENS: Final[int] = 575_000
_COMPACT_FALLBACK_PRESSURE_RESERVE_TOKENS: Final[int] = 160_000
_COMPACT_PRESSURE_MIN_PROMPT_TOKENS: Final[int] = 1_024
_PRESSURE_LINE_CHARS: Final[int] = 120
_COMPACT_ARTIFACT_PRINT_LIMIT: Final[int] = 10
_COMPACT_EVENT_AUDIT_PAGE_SIZE: Final[int] = 512
_NORMALIZED_SPACE_PATTERN: Final[re.Pattern[str]] = re.compile(r"\s+")
_ASSERTION_FAILURE_PREFIX: Final[str] = "answer assertion failed"
_SOURCE_NAME: Final[str] = "utils.smoke_host_public_conversation_memory_scenarios"
_OPERATION_NAME: Final[str] = "host_public_conversation_memory_scenarios_smoke"
_OPERATION_KIND: Final[str] = "manual_smoke"
_BUSINESS_DOMAIN: Final[str] = "host"
_SCENARIO: Final[str] = "phase12_5_conversation_memory_scenarios_smoke"
_COMPACT_TRIGGER_PROACTIVE: Final[str] = "proactive"
_COMPACT_TRIGGER_REACTIVE: Final[str] = "reactive"
_COMPACT_EVENT_TYPES: Final[tuple[str, ...]] = (
    CONTEXT_COMPACTION_REQUESTED,
    CONTEXT_COMPACTED,
    CONTEXT_COMPACTION_FAILED,
    CONTEXT_COMPACTION_ATTEMPT_REJECTED,
)
_PAYLOAD_FIELD_TRIGGER_SOURCE: Final[str] = "trigger_source"
_PAYLOAD_FIELD_OPERATION_ID: Final[str] = "operation_id"
_PAYLOAD_FIELD_ATTEMPT_NUMBER: Final[str] = "attempt_number"
_PAYLOAD_FIELD_FAILURE_CATEGORY: Final[str] = "failure_category"
_PAYLOAD_FIELD_REPAIRABLE: Final[str] = "repairable"
_PAYLOAD_FIELD_FAILURE_REASON: Final[str] = "failure_reason"
_PAYLOAD_FIELD_POLICY_DECISION: Final[str] = "policy_decision"
_PAYLOAD_FIELD_FALLBACK_POLICY_DECISION: Final[str] = "fallback_policy_decision"
_PAYLOAD_FIELD_FALLBACK_ACTION: Final[str] = "fallback_action"
_PAYLOAD_FIELD_FALLBACK_TIER: Final[str] = "fallback_tier"
_PAYLOAD_FIELD_ATTEMPT_COUNT: Final[str] = "attempt_count"
_PAYLOAD_FIELD_RETRY_REPAIR_BUDGET_EXHAUSTED: Final[str] = "retry_repair_budget_exhausted"
_PAYLOAD_FIELD_RUNNER_ATTEMPT_SUMMARY_REFS: Final[str] = "runner_attempt_summary_refs"
_PAYLOAD_FIELD_DIAGNOSTIC_REFS: Final[str] = "diagnostic_refs"
_PAYLOAD_FIELD_NEXT_POLICY_DECISION: Final[str] = "next_policy_decision"
_PAYLOAD_FIELD_BUDGET_AFTER_ATTEMPTED_COMPACT: Final[str] = "budget_after_attempted_compact"
_PAYLOAD_FIELD_FALLBACK_INPUT_WINDOW: Final[str] = "fallback_input_window"
_PAYLOAD_FIELD_SELECTED_BLOCK_IDS: Final[str] = "selected_block_ids"
_PAYLOAD_FIELD_DROPPED_BLOCK_IDS: Final[str] = "dropped_block_ids"
_PAYLOAD_FIELD_CURRENT_INPUT_REF: Final[str] = "current_input_ref"
_PAYLOAD_FIELD_PROPOSAL_MANIFEST_REF: Final[str] = "proposal_manifest_ref"
_PAYLOAD_FIELD_PROPOSAL_MANIFEST_DIGEST: Final[str] = "proposal_manifest_digest"
_COMPACT_OPERATION_UNKNOWN_TRIGGER: Final[str] = "<unknown>"
_COMPACT_OPERATION_MISSING_ID: Final[str] = "<missing-operation-id>"
_COMPACT_HISTOGRAM_EMPTY: Final[str] = "<none>"
_COMPACT_NONE_VALUE: Final[str] = "<none>"
_COMPACT_NOT_APPLICABLE: Final[str] = "not_applicable"
_COMPACT_FAILURE_STAGE_PROPOSAL_OR_QUALITY: Final[str] = "proposal_or_quality"
_COMPACT_FAILURE_STAGE_PREPARE_OR_MATERIAL: Final[str] = "prepare_or_material_projection"
_COMPACT_LOG_INSUFFICIENT_NONE: Final[str] = "none"
_COMPACT_LOG_INSUFFICIENT_OFFENDING_BLOCK: Final[str] = "offending_material_block_unavailable"
_COMPACT_MANIFEST_PRESENT: Final[str] = "present"
_COMPACT_MANIFEST_MISSING: Final[str] = "missing"
_DIAGNOSTIC_REF_SEPARATOR: Final[str] = ":"
_DIAGNOSTIC_REF_SUFFIX_OFFSET: Final[int] = 4
_COMPACT_HISTOGRAM_PRINT_LIMIT: Final[int] = 8
_COMPACT_FALLBACK_FORBIDDEN_SECTIONS: Final[tuple[str, ...]] = (
    "## Conversation Summary",
    "## Verified Evidence and Facts",
    "## Prior Answer Anchors",
    "## Open Follow-up Context",
    "## Reference Continuity",
)
_COMPACTOR_MATERIAL_BEGIN: Final[str] = "UNTRUSTED_COMPACTION_MATERIAL_JSON_BEGIN"
_COMPACTOR_MATERIAL_END: Final[str] = "UNTRUSTED_COMPACTION_MATERIAL_JSON_END"
_COMPACTOR_FIELD_TRACE_MATERIAL: Final[str] = "trace_material"
_COMPACTOR_FIELD_EVIDENCE_MATERIAL: Final[str] = "evidence_material"
_COMPACTOR_FIELD_ANSWER_MATERIAL: Final[str] = "answer_material"
_COMPACTOR_FIELD_PREVIOUS_COMPACTED_VIEW: Final[str] = "previous_compacted_view"
_COMPACTOR_FIELD_LABEL: Final[str] = "label"
_COMPACTOR_FIELD_SOURCE_LABEL: Final[str] = "source_label"
_COMPACTOR_FIELD_SOURCE_LABELS: Final[str] = "source_labels"
_COMPACTOR_FIELD_RESPONSE_TEXT: Final[str] = "response_text"
_COMPACTOR_FIELD_RESULT_TEXT: Final[str] = "result_text"
_COMPACTOR_FIELD_ANSWER_TEXT: Final[str] = "answer_text"
_SMOKE_COMPACTOR_SUMMARY_TEXT: Final[str] = "Deterministic smoke compact summary."
_SMOKE_COMPACTOR_FACT_PREFIX: Final[str] = "Deterministic smoke evidence material: "
_SMOKE_COMPACTOR_ANSWER_TITLE: Final[str] = "Previous answer"
_SMOKE_COMPACTOR_FORWARD_TEXT: Final[str] = "Continue current user-visible analysis."
_SMOKE_COMPACTOR_REFERENCE_TEXT: Final[str] = "Keep nearest prior context for local references."
_SMOKE_INVALID_CURRENT_ANCHOR_LABEL: Final[str] = "C1"
_SMOKE_REACTIVE_PROVIDER_REQUEST_ID: Final[str] = "smoke-reactive-provider-request"
_SMOKE_REACTIVE_ITERATION_ID: Final[str] = "smoke-reactive-iteration"
_SMOKE_REACTIVE_REASON: Final[str] = "provider_overflow"
_SMOKE_REACTIVE_WORKER_ID: Final[str] = "smoke-reactive-worker"
_SMOKE_FINAL_WORKER_ID: Final[str] = "smoke-final-worker"
_SMOKE_FINAL_ANSWER_PREFIX: Final[str] = "deterministic smoke final answer"
_SMOKE_REACTIVE_OLD_MARKER: Final[str] = "DAYU_SMOKE_REACTIVE_OLD_SEED_V1"
_SMOKE_REACTIVE_RECENT_MARKER: Final[str] = "DAYU_SMOKE_REACTIVE_PROTECTED_RECENT_V1"
_SMOKE_REACTIVE_CURRENT_MARKER: Final[str] = "DAYU_SMOKE_REACTIVE_CURRENT_INPUT_V1"
_SMOKE_FALLBACK_OLD_MARKER: Final[str] = "DAYU_SMOKE_FALLBACK_DROPPED_OLD_V1"
_SMOKE_FALLBACK_RECENT_MARKER: Final[str] = "DAYU_SMOKE_FALLBACK_SELECTED_RECENT_V1"
_SMOKE_FALLBACK_CURRENT_MARKER: Final[str] = "DAYU_SMOKE_FALLBACK_CURRENT_INPUT_V1"
_SMOKE_REACTIVE_TARGET_ACCEPT_INDEX: Final[int] = 6
_SMOKE_REACTIVE_HISTORY_GAP_ROUNDS: Final[int] = 3
_SMOKE_REACTIVE_SELECTED_RECENT_ITEMS_PER_TURN: Final[int] = 2
_SMOKE_COMPACTOR_MARKER_REPLACEMENT: Final[str] = "[deterministic smoke marker elided]"
_SMOKE_COMPACTOR_MARKERS: Final[tuple[str, ...]] = (
    _SMOKE_REACTIVE_OLD_MARKER,
    _SMOKE_REACTIVE_RECENT_MARKER,
    _SMOKE_REACTIVE_CURRENT_MARKER,
    _SMOKE_FALLBACK_OLD_MARKER,
    _SMOKE_FALLBACK_RECENT_MARKER,
    _SMOKE_FALLBACK_CURRENT_MARKER,
)
_SMOKE_DETERMINISTIC_EVENT_TIME: Final[datetime] = datetime(2026, 6, 20, 0, 0, 0, tzinfo=UTC)

_FIELD_COMPANY: Final[str] = "company"
_FIELD_TICKER: Final[str] = "ticker"
_FIELD_PERIOD: Final[str] = "period"
_FIELD_TOPIC: Final[str] = "topic"
_FIELD_METRIC: Final[str] = "metric"
_FIELD_INCLUDE_PRESSURE: Final[str] = "include_pressure"

_COMPANY_MAOTAI: Final[str] = "贵州茅台"
_TICKER_MAOTAI: Final[str] = "600519.SH"
_COMPANY_WULIANGYE: Final[str] = "五粮液"
_TICKER_WULIANGYE: Final[str] = "000858.SZ"
_COMPANY_CATL: Final[str] = "宁德时代"
_TICKER_CATL: Final[str] = "300750.SZ"
_COMPANY_BYD: Final[str] = "比亚迪"
_TICKER_BYD: Final[str] = "002594.SZ"
_COMPANY_CMB: Final[str] = "招商银行"
_TICKER_CMB: Final[str] = "600036.SH"
_COMPANY_MIDEA: Final[str] = "美的集团"
_TICKER_MIDEA: Final[str] = "000333.SZ"
_PERIOD_2024H1: Final[str] = "2024H1"
_PERIOD_2024A: Final[str] = "2024A"
_UNIT_MILLION_CNY: Final[str] = "百万元"
_UNIT_RMB_MILLION: Final[str] = "人民币百万元"
_CONSTRAINT_NO_MULTIPLE_EXTRAPOLATION: Final[str] = "no_multiple_extrapolation"
_CONSTRAINT_DOMESTIC_EXPORT_SPLIT: Final[str] = "内销与外销"

_TOPIC_REVENUE_PRODUCT_GROWTH: Final[str] = "revenue_product_growth"
_TOPIC_CASHFLOW: Final[str] = "cashflow"
_TOPIC_GROSS_MARGIN_LONG_INPUT: Final[str] = "gross_margin_long_input"
_TOPIC_NET_INTEREST_MARGIN: Final[str] = "net_interest_margin"
_TOPIC_LONG_SESSION_PROFILE: Final[str] = "long_session_profile"

_METRIC_MAOTAI_REVENUE: Final[str] = "maotai_revenue"
_METRIC_WULIANGYE_REVENUE: Final[str] = "wuliangye_revenue"
_METRIC_CATL_CASHFLOW: Final[str] = "catl_cashflow"
_METRIC_BYD_MARGIN_LONG_INPUT: Final[str] = "byd_margin_long_input"
_METRIC_CMB_NIM: Final[str] = "cmb_nim"
_METRIC_MIDEA_REVENUE: Final[str] = "midea_revenue_profile"
_METRIC_MIDEA_MARGIN: Final[str] = "midea_margin_profile"
_METRIC_MIDEA_EXPENSE: Final[str] = "midea_expense_profile"
_METRIC_MIDEA_ASSET: Final[str] = "midea_asset_profile"
_METRIC_MIDEA_CASHFLOW: Final[str] = "midea_cashflow_profile"
_METRIC_MIDEA_PEER: Final[str] = "midea_peer_profile"

_MARKER_MAOTAI_REVENUE: Final[str] = "DAYU_MEM_MAOTAI_REV_2024H1_V1"
_MARKER_WULIANGYE_REVENUE: Final[str] = "DAYU_MEM_WULIANGYE_REV_2024H1_V1"
_MARKER_CATL_CASHFLOW: Final[str] = "DAYU_MEM_CATL_CFO_2024A_V1"
_MARKER_BYD_LONG_FACTOR2: Final[str] = "DAYU_MEM_BYD_LONG_FACTOR2_V1"
_MARKER_CMB_NIM: Final[str] = "DAYU_MEM_CMB_NIM_2024H1_V2"
_MARKER_MIDEA_LONG: Final[str] = "DAYU_MEM_MIDEA_LONG_2024H1_V1"
_BYD_FACTOR2_MARKER: Final[str] = "BATTERY_PRICE_PRESSURE_FACTOR_2"

_VALUE_MAOTAI_WINE_YOY: Final[str] = "17.56%"
_VALUE_MAOTAI_SERIES_YOY: Final[str] = "30.51%"
_VALUE_WULIANGYE_CORE_YOY: Final[str] = "11.67%"
_VALUE_WULIANGYE_SERIES_YOY: Final[str] = "17.77%"
_VALUE_CATL_OPERATING_CF: Final[str] = "928.0亿元"
_VALUE_CATL_NET_PROFIT: Final[str] = "507.5亿元"
_VALUE_CATL_LARGEST_GAP: Final[str] = "经营性应付款增加"
_VALUE_CMB_NIM: Final[str] = "1.88%"
_VALUE_CMB_NIM_YOY: Final[str] = "-0.14pct"
_VALUE_CMB_ASSET_YIELD: Final[str] = "3.45%"
_VALUE_CMB_LIABILITY_COST: Final[str] = "1.74%"
_VALUE_CMB_RETAIL_LOAN_SHARE: Final[str] = "52.6%"
_VALUE_CMB_TIME_DEPOSIT_SHARE: Final[str] = "37.2%"
_VALUE_CMB_NPL_RATIO: Final[str] = "0.94%"

_FACT_KEY_MAOTAI_REVENUE: Final[str] = "maotai_revenue"
_FACT_KEY_WULIANGYE_REVENUE: Final[str] = "wuliangye_revenue"
_FACT_KEY_CATL_CASHFLOW: Final[str] = "catl_cashflow"
_FACT_KEY_BYD_MARGIN_LONG_INPUT: Final[str] = "byd_margin_long_input"
_FACT_KEY_CMB_NIM: Final[str] = "cmb_nim"
_FACT_KEY_MIDEA_LONG_SESSION: Final[str] = "midea_long_session"

_ASSERT_A: Final[str] = (
    "DAYU_MEM_ASSERT_A company=贵州茅台 ticker=600519.SH period=2024H1 "
    "unit=百万元 marker=DAYU_MEM_MAOTAI_REV_2024H1_V1 "
    "maotai_wine_yoy=17.56% series_wine_yoy=30.51%"
)
_ASSERT_A_SWITCH: Final[str] = (
    "DAYU_MEM_ASSERT_A_SWITCH company=五粮液 ticker=000858.SZ period=2024H1 "
    "unit=百万元 marker=DAYU_MEM_WULIANGYE_REV_2024H1_V1 "
    "wuliangye_core_yoy=11.67% series_yoy=17.77%"
)
_ASSERT_A_RETURN: Final[str] = (
    "DAYU_MEM_ASSERT_A_RETURN company=贵州茅台 ticker=600519.SH period=2024H1 "
    "unit=百万元 marker=DAYU_MEM_MAOTAI_REV_2024H1_V1 "
    "maotai_wine_yoy=17.56% series_wine_yoy=30.51%"
)
_ASSERT_B_CFO: Final[str] = (
    "DAYU_MEM_ASSERT_B_CFO marker=DAYU_MEM_CATL_CFO_2024A_V1 "
    "operating_cf=928.0亿元 net_profit=507.5亿元 largest_gap=经营性应付款增加"
)
_ASSERT_B_FOLLOW: Final[str] = (
    "DAYU_MEM_ASSERT_B_FOLLOW marker=DAYU_MEM_CATL_CFO_2024A_V1 " "referent=operating_cf largest_gap=经营性应付款增加"
)
_ASSERT_C_LONG: Final[str] = (
    "DAYU_MEM_ASSERT_C_LONG marker=DAYU_MEM_BYD_LONG_FACTOR2_V1 " "factor2=BATTERY_PRICE_PRESSURE_FACTOR_2"
)
_ASSERT_C_FOLLOW: Final[str] = (
    "DAYU_MEM_ASSERT_C_FOLLOW marker=DAYU_MEM_BYD_LONG_FACTOR2_V1 " "factor2=BATTERY_PRICE_PRESSURE_FACTOR_2"
)
_ASSERT_D_NIM: Final[str] = (
    "DAYU_MEM_ASSERT_D_NIM marker=DAYU_MEM_CMB_NIM_2024H1_V2 "
    "nim=1.88% yoy=-0.14pct asset_yield=3.45% liability_cost=1.74%"
)
_ASSERT_D_RETURN: Final[str] = (
    "DAYU_MEM_ASSERT_D_RETURN marker=DAYU_MEM_CMB_NIM_2024H1_V2 " "nim=1.88% yoy=-0.14pct consistent=yes"
)
_ASSERT_E_CONSTRAINTS: Final[str] = (
    "DAYU_MEM_ASSERT_E_CONSTRAINTS marker=DAYU_MEM_MIDEA_LONG_2024H1_V1 "
    "unit=人民币百万元 valuation=no_multiple_extrapolation split=内销与外销"
)

_LABEL_CORE_A1: Final[str] = "core-a1-maotai-tool"
_LABEL_CORE_A2: Final[str] = "core-a2-maotai-followup-no-tool"
_LABEL_CORE_A3: Final[str] = "core-a3-switch-wuliangye-tool"
_LABEL_CORE_A4: Final[str] = "core-a4-return-maotai-no-tool"
_LABEL_CORE_B1: Final[str] = "core-b1-catl-cashflow-tool"
_LABEL_CORE_B2: Final[str] = "core-b2-this-number-no-tool"
_LABEL_CORE_B3: Final[str] = "core-b3-investment-spend-soft"
_LABEL_CORE_C1: Final[str] = "core-c1-byd-intro"
_LABEL_CORE_C2: Final[str] = "core-c2-byd-long-input"
_LABEL_CORE_C3: Final[str] = "core-c3-byd-factor-followup"
_LABEL_CORE_D1: Final[str] = "core-d1-cmb-tool-pressure"
_LABEL_CORE_D2: Final[str] = "core-d2-group-pressure-no-tool"
_LABEL_CORE_D3: Final[str] = "core-d3-topic-shift-no-tool"
_LABEL_CORE_D4: Final[str] = "core-d4-return-nim-no-tool"

_LONG_LABEL_01: Final[str] = "long-l01-revenue-tool"
_LONG_LABEL_02: Final[str] = "long-l02-revenue-followup"
_LONG_LABEL_03: Final[str] = "long-l03-revenue-constraint-check"
_LONG_LABEL_04: Final[str] = "long-l04-revenue-risk"
_LONG_LABEL_05: Final[str] = "long-l05-margin-tool"
_LONG_LABEL_06: Final[str] = "long-l06-margin-followup"
_LONG_LABEL_07: Final[str] = "long-l07-margin-anti-drift"
_LONG_LABEL_08: Final[str] = "long-l08-margin-pressure"
_LONG_LABEL_09: Final[str] = "long-l09-expense-tool"
_LONG_LABEL_10: Final[str] = "long-l10-expense-followup"
_LONG_LABEL_11: Final[str] = "long-l11-profit-bridge"
_LONG_LABEL_12: Final[str] = "long-l12-profit-constraint-check"
_LONG_LABEL_13: Final[str] = "long-l13-asset-tool"
_LONG_LABEL_14: Final[str] = "long-l14-asset-followup"
_LONG_LABEL_15: Final[str] = "long-l15-liability-setup"
_LONG_LABEL_16: Final[str] = "long-l16-liability-pressure"
_LONG_LABEL_17: Final[str] = "long-l17-cashflow-tool"
_LONG_LABEL_18: Final[str] = "long-l18-cashflow-followup"
_LONG_LABEL_19: Final[str] = "long-l19-valuation-constraint"
_LONG_LABEL_20: Final[str] = "long-l20-valuation-application"
_LONG_LABEL_21: Final[str] = "long-l21-peer-tool"
_LONG_LABEL_22: Final[str] = "long-l22-peer-followup"
_LONG_LABEL_23: Final[str] = "long-l23-session-recap"
_LONG_LABEL_24: Final[str] = "long-l24-final-pressure-recap"
_LONG_LABEL_25: Final[str] = "long-l25-constraint-assert"

_LONG_PROMPT_01_REVENUE_TOOL: Final[str] = (
    "请调用 get_mock_finance_memory_fact 查询美的集团 000333.SZ 2024H1 长会话画像，"
    "参数 company=美的集团、ticker=000333.SZ、period=2024H1、"
    "topic=long_session_profile、metric=midea_revenue_profile、include_pressure=true。"
    "回答只概括收入结构，并记住本会话口径：人民币百万元、区分内销与外销、"
    "不使用估值倍数外推。"
)
_LONG_PROMPT_02_REVENUE_FOLLOWUP: Final[str] = (
    "继续上一轮，不要调用工具。把收入结构按内销和外销拆成两段，并说明后续都沿用人民币百万元口径。"
)
_LONG_PROMPT_03_REVENUE_CONSTRAINT_CHECK: Final[str] = (
    "不调用工具。确认我们当前研究主体、期间、证券代码和计量口径分别是什么；不要新增事实。"
)
_LONG_PROMPT_04_REVENUE_RISK: Final[str] = (
    "不调用工具。仅基于会话中已确认的信息，列出收入分析还缺哪些事实；不能编造缺失数据。"
)
_LONG_PROMPT_05_MARGIN_TOOL: Final[str] = (
    "请调用 get_mock_finance_memory_fact 查询美的集团 000333.SZ 2024H1 毛利主题，"
    "参数 company=美的集团、ticker=000333.SZ、period=2024H1、"
    "topic=long_session_profile、metric=midea_margin_profile、include_pressure=true。"
    "回答时继续保留人民币百万元、内销/外销拆分和不使用估值倍数外推三条约束。"
)
_LONG_PROMPT_06_MARGIN_FOLLOWUP: Final[str] = (
    "不调用工具。把刚才毛利主题和收入结构连起来，说明哪些结论已经确认、哪些只是待验证。"
)
_LONG_PROMPT_07_MARGIN_ANTI_DRIFT: Final[str] = (
    "不调用工具。请确认当前主体仍是美的集团 000333.SZ 2024H1，"
    "而不是前面 core suite 的任何公司；回答中不要引用茅台、五粮液、宁德时代、比亚迪或招商银行的数值。"
)
_LONG_PROMPT_08_MARGIN_PRESSURE: Final[str] = (
    "不调用工具。用三句话总结收入和毛利之间的关系，末尾保留三条口径约束。"
    "下面是长会话稳定性压力文本：{auto_user_pressure}"
)
_LONG_PROMPT_09_EXPENSE_TOOL: Final[str] = (
    "请调用 get_mock_finance_memory_fact 查询美的集团 000333.SZ 2024H1 费用主题，"
    "参数 company=美的集团、ticker=000333.SZ、period=2024H1、"
    "topic=long_session_profile、metric=midea_expense_profile、include_pressure=true。"
    "回答只基于工具结果和本会话既有约束。"
)
_LONG_PROMPT_10_EXPENSE_FOLLOWUP: Final[str] = (
    "不调用工具。把费用主题和毛利主题做一个承接说明，指出费用分析仍然沿用人民币百万元口径。"
)
_LONG_PROMPT_11_PROFIT_BRIDGE: Final[str] = (
    "不调用工具。基于已确认的收入、毛利、费用讨论，给出利润分析的桥接框架；没有确认过的利润数值不要编。"
)
_LONG_PROMPT_12_PROFIT_CONSTRAINT_CHECK: Final[str] = (
    "不调用工具。复述本会话到目前为止的三条口径约束，并说明这些约束如何影响利润分析。"
)
_LONG_PROMPT_13_ASSET_TOOL: Final[str] = (
    "请调用 get_mock_finance_memory_fact 查询美的集团 000333.SZ 2024H1 资产主题，"
    "参数 company=美的集团、ticker=000333.SZ、period=2024H1、"
    "topic=long_session_profile、metric=midea_asset_profile、include_pressure=true。"
    "回答中保持当前主体和三条口径约束。"
)
_LONG_PROMPT_14_ASSET_FOLLOWUP: Final[str] = (
    "不调用工具。把资产主题和利润桥接框架连接起来，明确哪些资产相关信息已经确认。"
)
_LONG_PROMPT_15_LIABILITY_SETUP: Final[str] = (
    "不调用工具。准备进入负债主题前，先列出我们需要关注的负债问题；不要假设还没确认的数据。"
)
_LONG_PROMPT_16_LIABILITY_PRESSURE: Final[str] = (
    "不调用工具。继续负债主题，只说明当前会话中已确认和未确认的边界，并再次保留三条口径约束。"
    "下面是长会话稳定性压力文本：{auto_user_pressure}"
)
_LONG_PROMPT_17_CASHFLOW_TOOL: Final[str] = (
    "请调用 get_mock_finance_memory_fact 查询美的集团 000333.SZ 2024H1 现金流主题，"
    "参数 company=美的集团、ticker=000333.SZ、period=2024H1、"
    "topic=long_session_profile、metric=midea_cashflow_profile、include_pressure=true。"
    "回答要把现金流主题接到收入、利润和资产讨论上。"
)
_LONG_PROMPT_18_CASHFLOW_FOLLOWUP: Final[str] = (
    "不调用工具。解释现金流主题对前面收入、费用和资产分析的校验作用；缺失的具体数值要标明未确认。"
)
_LONG_PROMPT_19_VALUATION_CONSTRAINT: Final[str] = (
    "不调用工具。进入估值口径前，确认本会话不使用估值倍数外推；说明这条约束如何限制后续表达。"
)
_LONG_PROMPT_20_VALUATION_APPLICATION: Final[str] = (
    "不调用工具。在不使用估值倍数外推的约束下，给出可以讨论和不可以讨论的估值相关内容边界。"
)
_LONG_PROMPT_21_PEER_TOOL: Final[str] = (
    "请调用 get_mock_finance_memory_fact 查询美的集团 000333.SZ 2024H1 同行对比主题，"
    "参数 company=美的集团、ticker=000333.SZ、period=2024H1、"
    "topic=long_session_profile、metric=midea_peer_profile、include_pressure=true。"
    "回答只说明对比维度，不引入未确认的同行数值。"
)
_LONG_PROMPT_22_PEER_FOLLOWUP: Final[str] = (
    "不调用工具。把同行对比维度与内销/外销拆分约束连接起来，说明哪些比较是可做的。"
)
_LONG_PROMPT_23_SESSION_RECAP: Final[str] = (
    "不调用工具。按收入、毛利、费用、利润、资产、负债、现金流、估值口径、同行对比九个主题，"
    "概括本会话已经形成的分析框架。"
)
_LONG_PROMPT_24_FINAL_PRESSURE_RECAP: Final[str] = (
    "不调用工具。在长会话结束前，再次确认当前主体、期间、证券代码和三条口径约束；"
    "不要引用 core suite 的公司。下面是长会话稳定性压力文本：{auto_user_pressure}"
)
_LONG_PROMPT_25_CONSTRAINT_ASSERT: Final[str] = (
    "我们这次对话定下了哪些口径约束？不要调用工具。最后输出 "
    "DAYU_MEM_ASSERT_E_CONSTRAINTS marker=DAYU_MEM_MIDEA_LONG_2024H1_V1 "
    "unit=人民币百万元 valuation=no_multiple_extrapolation split=内销与外销"
)

_CORE_FORBIDDEN_MARKERS_FOR_LONG: Final[tuple[str, ...]] = (
    _MARKER_MAOTAI_REVENUE,
    _MARKER_WULIANGYE_REVENUE,
    _MARKER_CATL_CASHFLOW,
    _MARKER_BYD_LONG_FACTOR2,
    _MARKER_CMB_NIM,
)

_BYD_LONG_INPUT_TARGET_CHARS: Final[int] = 12_000
_BYD_LONG_INPUT_MIN_CHARS: Final[int] = 8_000
_BYD_LONG_INPUT_MAX_CHARS: Final[int] = 15_000
_BYD_LONG_INPUT_HEAD_ANCHOR: Final[str] = "DAYU_LONG_INPUT_FACTOR_1_EXPORT_MIX"
_BYD_LONG_INPUT_MIDDLE_ANCHOR: Final[str] = _BYD_FACTOR2_MARKER
_BYD_LONG_INPUT_TAIL_ANCHOR: Final[str] = "DAYU_LONG_INPUT_FACTOR_3_SCALE_EFFECT"
_BYD_LONG_INPUT_FILLER: Final[str] = "。"
_BYD_LONG_INPUT_TEMPLATE_PARAGRAPHS: Final[tuple[str, ...]] = (
    "出口车型结构段：公司海外车型组合变化会影响单车收入、渠道费用和毛利率弹性，"
    "需要区分出口销量增长与出口车型升级两个层次。",
    "动力电池价格压力段：电池材料价格、 pack 定价和外供订单节奏会共同影响毛利率，"
    "若价格下降快于成本下降，短期可能形成毛利压力。",
    "规模效应段：产量爬坡、平台化零部件复用和制造费用摊薄会改善单位成本，"
    "但产能利用率不足时规模效应会被固定成本吸收。",
    "原材料与产能利用率段：铝、钢、锂相关材料波动需要和库存周期一起观察，" "单一价格变化不能直接推出毛利率结论。",
)


class SuiteMode(StrEnum):
    """场景套件模式。

    :param MEMORY_CORE: 公开多轮记忆基础 smoke，不要求 compact。
    :param MEMORY_COMPACT: compact 专项 smoke，必须断言 proactive compact
        accepted，且 compact failed 会硬失败。
    :param MEMORY_REACTIVE_COMPACT: reactive compact 专项 smoke，使用
        deterministic worker 触发 Engine overflow 并断言 Host recovery。
    :param MEMORY_COMPACT_FALLBACK: compact failure fallback 专项 smoke，使用
        deterministic compactor rejection 断言 fallback dispatch。
    """

    MEMORY_CORE = "memory-core"
    MEMORY_COMPACT = "memory-compact"
    MEMORY_REACTIVE_COMPACT = "memory-reactive-compact"
    MEMORY_COMPACT_FALLBACK = "memory-compact-fallback"


class PressureMode(StrEnum):
    """压力注入模式。

    :param AUTO: 按 context budget 自适应注入 compact 压力。
    :param OFF: 不注入人工压力文本。
    """

    AUTO = "auto"
    OFF = "off"


@dataclass(frozen=True, slots=True)
class SmokeArgs:
    """命令行参数。

    :param workspace_root: workspace 根目录。
    :param scene_id: 需要装配的 scene id。
    :param execution_profile_id: 可选 execution profile 显式覆盖。
    :param host_runtime_id: 可选 Host runtime 显式覆盖。
    :param model_id: 可选模型显式覆盖。
    :param runner_option_hint_id: 可选 runner option hint 显式覆盖。
    :param log_level: Dayu 日志级别。
    :param reuse_session: 是否复用稳定 slot。
    :param keep_workspace: 是否保留 workspace。
    :param suite: 场景套件。
    :param long_rounds: long suite 轮数，范围为 20 到 25。
    :param pressure_mode: 压力注入模式。
    :param debug_smoke_output: 是否打印 smoke 自身的工具调用诊断。
    """

    workspace_root: pathlib.Path
    scene_id: str
    execution_profile_id: str | None
    host_runtime_id: str | None
    model_id: str | None
    runner_option_hint_id: str | None
    log_level: LogLevel
    reuse_session: bool
    keep_workspace: bool
    suite: SuiteMode
    long_rounds: int
    pressure_mode: PressureMode
    debug_smoke_output: bool


@dataclass(frozen=True, slots=True)
class RoundSpec:
    """单轮场景规格。

    :param label: 轮次标签。
    :param prompt: 用户输入文本。
    :param tool_names: 本轮允许使用的工具名集合。
    :param expected_tool_fact_key: 本轮必须命中的 fact key；为 ``None`` 时仅
        执行工具调用泄漏检查和诊断。
    :param hard_answer_contains: 最终回答必须包含的文本片段。
    :param hard_answer_forbidden: 最终回答禁止包含的文本片段。
    :param soft_answer_contains: 最终回答建议包含的观察片段。
    :param print_calls_by_key: 是否在本轮后打印 calls_by_key 摘要。
    """

    label: str
    prompt: str
    tool_names: frozenset[str]
    expected_tool_fact_key: str | None
    hard_answer_contains: tuple[str, ...]
    hard_answer_forbidden: tuple[str, ...]
    soft_answer_contains: tuple[str, ...]
    print_calls_by_key: bool


@dataclass(frozen=True, slots=True)
class RoundResult:
    """单轮 public Host 运行摘要。

    :param label: 人工可读轮次标签。
    :param run_id: Host Run id。
    :param event: terminal HostEvent。
    """

    label: str
    run_id: str
    event: HostEvent


@dataclass(frozen=True, slots=True)
class CompactAuditSummary:
    """本次 session 的 compact EventLog 摘要。

    :param requested_proactive: proactive compact request 数。
    :param requested_reactive: reactive compact request 数。
    :param compacted_proactive: proactive accepted compact 数。
    :param compacted_reactive: reactive accepted compact 数。
    :param failed_proactive: proactive compact failed 数。
    :param failed_reactive: reactive compact failed 数。
    :param rejected_proactive: proactive compact attempt rejected 数。
    :param rejected_reactive: reactive compact attempt rejected 数。
    """

    requested_proactive: int
    requested_reactive: int
    compacted_proactive: int
    compacted_reactive: int
    failed_proactive: int
    failed_reactive: int
    rejected_proactive: int
    rejected_reactive: int


@dataclass(frozen=True, slots=True)
class CompactRejectedAttemptAudit:
    """单次 compact rejected attempt 的诊断摘要。

    :param event_id: rejected attempt EventLog id。
    :param event_sequence: rejected attempt EventLog sequence。
    :param operation_id: compact operation id；payload 缺失时为 ``None``。
    :param trigger_source: request 归因后的 trigger source；无法归因时为 ``None``。
    :param attempt_number: operation 内 attempt 序号；payload 缺失时为 ``None``。
    :param failure_category: compact failure category；payload 缺失时为 ``None``。
    :param repairable: 是否可 repair；payload 缺失时为 ``None``。
    :param next_policy_decision: 下一步 policy decision；payload 缺失时为 ``None``。
    :param budget_after_attempted_compact: attempt 后预算；payload 缺失或未知时为
        ``None``。
    :param runner_attempt_summary_refs: runner attempt 摘要 refs。
    :param diagnostic_refs: Host diagnostic refs。
    :param proposal_manifest_ref: proposal manifest ref；prepare 阶段失败时为
        ``None``。
    :param proposal_manifest_digest: proposal manifest digest；prepare 阶段失败时
        为 ``None``。
    """

    event_id: str
    event_sequence: int
    operation_id: str | None
    trigger_source: str | None
    attempt_number: int | None
    failure_category: str | None
    repairable: bool | None
    next_policy_decision: str | None
    budget_after_attempted_compact: int | None
    runner_attempt_summary_refs: tuple[str, ...]
    diagnostic_refs: tuple[str, ...]
    proposal_manifest_ref: str | None
    proposal_manifest_digest: str | None


@dataclass(frozen=True, slots=True)
class CompactFailedOperationAudit:
    """单个 ``CONTEXT_COMPACTION_FAILED`` 的诊断摘要。

    :param event_id: failed EventLog id。
    :param event_sequence: failed EventLog sequence。
    :param operation_id: compact operation id；payload 缺失时为 ``None``。
    :param trigger_source: request 归因后的 trigger source；无法归因时为 ``None``。
    :param failure_reason: Host failure reason；payload 缺失时为 ``None``。
    :param policy_decision: Host policy decision；payload 缺失时为 ``None``。
    :param fallback_policy_decision: fallback policy decision；payload 缺失时为
        ``None``。
    :param fallback_action: fallback 后动作；payload 缺失时为 ``None``。
    :param fallback_tier: fallback tier；payload 缺失时为 ``None``。
    :param attempt_count: compact attempt count；payload 缺失时为 ``None``。
    :param retry_repair_budget_exhausted: retry / repair budget 是否耗尽。
    :param budget_after_attempted_compact: attempt 后预算；payload 缺失或未知时为
        ``None``。
    :param selected_block_ids: fallback input window 选择的 bounded block ids。
    :param dropped_block_ids: fallback input window 丢弃的 bounded block ids。
    :param current_input_ref: fallback input window 绑定的当前输入 ref。
    """

    event_id: str
    event_sequence: int
    operation_id: str | None
    trigger_source: str | None
    failure_reason: str | None
    policy_decision: str | None
    fallback_policy_decision: str | None
    fallback_action: str | None
    fallback_tier: str | None
    attempt_count: int | None
    retry_repair_budget_exhausted: bool | None
    budget_after_attempted_compact: int | None
    selected_block_ids: tuple[str, ...]
    dropped_block_ids: tuple[str, ...]
    current_input_ref: str | None


@dataclass(frozen=True, slots=True)
class CompactOperationAudit:
    """单个 compact operation 的结构化审计摘要。

    :param operation_id: compact operation id；无法归因时使用占位符。
    :param trigger_source: trigger source；无法归因时使用占位符。
    :param request_event_id: request EventLog id；缺失时为 ``None``。
    :param request_event_sequence: request EventLog sequence；缺失时为
        ``None``。
    :param run_id: request row 对应的 run id；缺失时为 ``None``。
    :param requested: request event 数。
    :param compacted: accepted compact event 数。
    :param compacted_event_sequences: accepted compact event sequences。
    :param failed: failed compact event 数。
    :param rejected: rejected attempt event 数。
    :param rejected_attempts: rejected attempt 明细。
    :param failed_events: failed event 明细。
    :param failure_categories: rejected failure category histogram。
    :param diagnostic_histogram: rejected diagnostic suffix histogram。
    """

    operation_id: str
    trigger_source: str
    request_event_id: str | None
    request_event_sequence: int | None
    run_id: str | None
    requested: int
    compacted: int
    compacted_event_sequences: tuple[int, ...]
    failed: int
    rejected: int
    rejected_attempts: tuple[CompactRejectedAttemptAudit, ...]
    failed_events: tuple[CompactFailedOperationAudit, ...]
    failure_categories: tuple[tuple[str, int], ...]
    diagnostic_histogram: tuple[tuple[str, int], ...]


@dataclass(frozen=True, slots=True)
class CompactAuditReport:
    """本次 session 的 compact EventLog 审计报告。

    :param summary: compact event 计数摘要。
    :param operations: per-operation 审计摘要。
    :param rejected_failure_histogram: 全局 rejected failure category histogram。
    :param rejected_diagnostic_histogram: 全局 rejected diagnostic suffix histogram。
    :param rejected_manifest_presence_histogram: 全局 proposal manifest ref
        present / missing histogram。
    """

    summary: CompactAuditSummary
    operations: tuple[CompactOperationAudit, ...]
    rejected_failure_histogram: tuple[tuple[str, int], ...]
    rejected_diagnostic_histogram: tuple[tuple[str, int], ...]
    rejected_manifest_presence_histogram: tuple[tuple[str, int], ...]


@dataclass(frozen=True, slots=True)
class DeterministicDispatchCapture:
    """deterministic worker 捕获的一次普通 dispatch 摘要。

    :param run_id: Host Run id。
    :param attempt_id: Host Attempt id。
    :param execution_id: Attempt execution id。
    :param joined_messages: 本次 ``AgentRunRequest.messages`` 的合并文本。
    :param system_message_count: system message 数量。
    :param system_message_at_start: 唯一 system message 是否位于首位；无
        system message 时为 ``True``。
    """

    run_id: str
    attempt_id: str
    execution_id: str
    joined_messages: str
    system_message_count: int
    system_message_at_start: bool


@dataclass(frozen=True, slots=True)
class DeterministicSmokeObservation:
    """deterministic public Host smoke 的 bounded 观测。

    :param dispatches: ordinary worker 捕获的 dispatch 摘要。
    :param target_run_id: 目标 Run id。
    :param current_input_marker: 当前输入稳定 marker。
    :param protected_recent_marker: 必须保留的近期 marker。
    :param dropped_old_marker: 应被策略窗口丢弃的旧 marker；不适用时为
        ``None``。
    :param pressure_tokens: fallback suite 的有效压力估算 token；不适用时为
        ``None``。
    :param soft_threshold_tokens: fallback suite 使用的 soft threshold；不适用
        时为 ``None``。
    :param hard_threshold_tokens: fallback suite 使用的 hard threshold；不适用
        时为 ``None``。
    """

    dispatches: tuple[DeterministicDispatchCapture, ...]
    target_run_id: str
    current_input_marker: str
    protected_recent_marker: str
    dropped_old_marker: str | None
    pressure_tokens: int | None
    soft_threshold_tokens: int | None
    hard_threshold_tokens: int | None


@dataclass(frozen=True, slots=True)
class FallbackPressureObservation:
    """fallback suite 的压力阈值观测。

    :param pressure_tokens: 有效压力估算 token；非 fallback suite 为 ``None``。
    :param soft_threshold_tokens: soft threshold token；非 fallback suite 为
        ``None``。
    :param hard_threshold_tokens: hard threshold token；非 fallback suite 为
        ``None``。
    """

    pressure_tokens: int | None
    soft_threshold_tokens: int | None
    hard_threshold_tokens: int | None


class SmokeCompactorRunner(Protocol):
    """smoke-local compactor runner patch 协议。"""

    async def __call__(self, request: AgentRunRequest, *, timeout_seconds: float) -> AgentRunResult:
        """执行一次 compactor Engine request。

        :param request: Host compactor 构造的 Engine request。
        :param timeout_seconds: compactor 单次超时秒数。
        :returns: Engine run result。
        :raises Exception: fake runner 断言失败时向上抛出。
        """

        ...


@dataclass(frozen=True, slots=True)
class RuntimeAssemblyResult:
    """Host runtime assembly 结果。

    :param options: 可传给 ``open_host`` 的 Host 构造期输入。
    :param scene_inputs: ScenePrepare 输出。
    :param diagnostics: 调用 Host 前的装配诊断。
    :param effective_tool_bundle: Host 打开前已应用截断默认值的工具 bundle。
    :param smoke_tool: 从 effective ToolBundle 恢复出的 mock 财报记忆工具实例。
    """

    options: OpenHostOptions
    scene_inputs: PreparedSceneInputs
    diagnostics: ServiceOpenHostAssemblyDiagnostics
    effective_tool_bundle: ToolBundle
    smoke_tool: "MockFinanceMemoryTool"


@dataclass(frozen=True, slots=True)
class LongRoundTemplate:
    """long suite 的固定轮次模板。

    :param label: long 轮次标签。
    :param prompt_template: 用户输入模板，允许包含自动压力占位符。
    :param tool_enabled: 本轮是否允许工具。
    :param metric: 本轮工具 metric；禁用工具轮次为空字符串。
    :param include_tool_pressure: 工具参数是否要求压力。
    :param include_user_pressure: 用户输入是否追加压力文本。
    :param hard_contains: 最终回答必须包含的文本片段。
    :param hard_forbidden: 最终回答禁止包含的文本片段。
    """

    label: str
    prompt_template: str
    tool_enabled: bool
    metric: str
    include_tool_pressure: bool
    include_user_pressure: bool
    hard_contains: tuple[str, ...]
    hard_forbidden: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ToolCallSnapshot:
    """mock 工具调用计数快照。

    :param total_count: tracked session 内累计工具调用次数。
    :param calls_by_key: 按 fact key 聚合的累计调用次数。
    """

    total_count: int
    calls_by_key: Mapping[str, int]


@dataclass(frozen=True, slots=True)
class ToolCallObservation:
    """mock 工具单次调用诊断。

    :param sequence: tracked session 内递增调用序号。
    :param tool_call_id: Engine 传入的工具调用 id。
    :param known: 是否命中已知 mock fact。
    :param fact_key: 命中的 fact key；未知时为 ``_UNKNOWN_FACT_KEY``。
    :param company: 工具参数 company。
    :param ticker: 工具参数 ticker。
    :param period: 工具参数 period。
    :param topic: 工具参数 topic。
    :param metric: 工具参数 metric。
    :param include_pressure: 工具参数 include_pressure。
    """

    sequence: int
    tool_call_id: str
    known: bool
    fact_key: str
    company: str
    ticker: str
    period: str
    topic: str
    metric: str
    include_pressure: bool


@dataclass(frozen=True, slots=True)
class MockFactRecord:
    """mock 财报事实记录。

    :param key: calls_by_key 使用的事实 key。
    :param company: 公司名称。
    :param ticker: 证券代码。
    :param period: 财报期间。
    :param topic: 查询主题。
    :param metrics: 可匹配的 metric 名称。
    :param marker: 稳定事实 marker。
    :param values: 稳定事实字段和值。
    """

    key: str
    company: str
    ticker: str
    period: str
    topic: str
    metrics: tuple[str, ...]
    marker: str
    values: tuple[tuple[str, str], ...]


_MOCK_FACTS: Final[tuple[MockFactRecord, ...]] = (
    MockFactRecord(
        key=_FACT_KEY_MAOTAI_REVENUE,
        company=_COMPANY_MAOTAI,
        ticker=_TICKER_MAOTAI,
        period=_PERIOD_2024H1,
        topic=_TOPIC_REVENUE_PRODUCT_GROWTH,
        metrics=(_METRIC_MAOTAI_REVENUE,),
        marker=_MARKER_MAOTAI_REVENUE,
        values=(
            ("unit", _UNIT_MILLION_CNY),
            ("maotai_wine_yoy", _VALUE_MAOTAI_WINE_YOY),
            ("series_wine_yoy", _VALUE_MAOTAI_SERIES_YOY),
        ),
    ),
    MockFactRecord(
        key=_FACT_KEY_WULIANGYE_REVENUE,
        company=_COMPANY_WULIANGYE,
        ticker=_TICKER_WULIANGYE,
        period=_PERIOD_2024H1,
        topic=_TOPIC_REVENUE_PRODUCT_GROWTH,
        metrics=(_METRIC_WULIANGYE_REVENUE,),
        marker=_MARKER_WULIANGYE_REVENUE,
        values=(
            ("unit", _UNIT_MILLION_CNY),
            ("wuliangye_core_yoy", _VALUE_WULIANGYE_CORE_YOY),
            ("series_yoy", _VALUE_WULIANGYE_SERIES_YOY),
        ),
    ),
    MockFactRecord(
        key=_FACT_KEY_CATL_CASHFLOW,
        company=_COMPANY_CATL,
        ticker=_TICKER_CATL,
        period=_PERIOD_2024A,
        topic=_TOPIC_CASHFLOW,
        metrics=(_METRIC_CATL_CASHFLOW,),
        marker=_MARKER_CATL_CASHFLOW,
        values=(
            ("operating_cf", _VALUE_CATL_OPERATING_CF),
            ("net_profit", _VALUE_CATL_NET_PROFIT),
            ("largest_gap", _VALUE_CATL_LARGEST_GAP),
        ),
    ),
    MockFactRecord(
        key=_FACT_KEY_BYD_MARGIN_LONG_INPUT,
        company=_COMPANY_BYD,
        ticker=_TICKER_BYD,
        period=_PERIOD_2024H1,
        topic=_TOPIC_GROSS_MARGIN_LONG_INPUT,
        metrics=(_METRIC_BYD_MARGIN_LONG_INPUT,),
        marker=_MARKER_BYD_LONG_FACTOR2,
        values=(
            ("factor1", _BYD_LONG_INPUT_HEAD_ANCHOR),
            ("factor2", _BYD_FACTOR2_MARKER),
            ("factor3", _BYD_LONG_INPUT_TAIL_ANCHOR),
        ),
    ),
    MockFactRecord(
        key=_FACT_KEY_CMB_NIM,
        company=_COMPANY_CMB,
        ticker=_TICKER_CMB,
        period=_PERIOD_2024H1,
        topic=_TOPIC_NET_INTEREST_MARGIN,
        metrics=(_METRIC_CMB_NIM,),
        marker=_MARKER_CMB_NIM,
        values=(
            ("nim", _VALUE_CMB_NIM),
            ("yoy", _VALUE_CMB_NIM_YOY),
            ("asset_yield", _VALUE_CMB_ASSET_YIELD),
            ("liability_cost", _VALUE_CMB_LIABILITY_COST),
            ("retail_loan_share", _VALUE_CMB_RETAIL_LOAN_SHARE),
            ("time_deposit_share", _VALUE_CMB_TIME_DEPOSIT_SHARE),
            ("npl_ratio", _VALUE_CMB_NPL_RATIO),
        ),
    ),
    MockFactRecord(
        key=_FACT_KEY_MIDEA_LONG_SESSION,
        company=_COMPANY_MIDEA,
        ticker=_TICKER_MIDEA,
        period=_PERIOD_2024H1,
        topic=_TOPIC_LONG_SESSION_PROFILE,
        metrics=(
            _METRIC_MIDEA_REVENUE,
            _METRIC_MIDEA_MARGIN,
            _METRIC_MIDEA_EXPENSE,
            _METRIC_MIDEA_ASSET,
            _METRIC_MIDEA_CASHFLOW,
            _METRIC_MIDEA_PEER,
        ),
        marker=_MARKER_MIDEA_LONG,
        values=(
            ("unit", _UNIT_RMB_MILLION),
            ("valuation", _CONSTRAINT_NO_MULTIPLE_EXTRAPOLATION),
            ("split", _CONSTRAINT_DOMESTIC_EXPORT_SPLIT),
        ),
    ),
)

_LONG_ROUND_TEMPLATES: Final[tuple[LongRoundTemplate, ...]] = (
    LongRoundTemplate(
        _LONG_LABEL_01,
        _LONG_PROMPT_01_REVENUE_TOOL,
        True,
        _METRIC_MIDEA_REVENUE,
        True,
        False,
        (),
        (),
    ),
    LongRoundTemplate(
        _LONG_LABEL_02,
        _LONG_PROMPT_02_REVENUE_FOLLOWUP,
        False,
        "",
        False,
        False,
        (),
        _CORE_FORBIDDEN_MARKERS_FOR_LONG,
    ),
    LongRoundTemplate(
        _LONG_LABEL_03,
        _LONG_PROMPT_03_REVENUE_CONSTRAINT_CHECK,
        False,
        "",
        False,
        False,
        (),
        _CORE_FORBIDDEN_MARKERS_FOR_LONG,
    ),
    LongRoundTemplate(
        _LONG_LABEL_04,
        _LONG_PROMPT_04_REVENUE_RISK,
        False,
        "",
        False,
        False,
        (),
        _CORE_FORBIDDEN_MARKERS_FOR_LONG,
    ),
    LongRoundTemplate(
        _LONG_LABEL_05,
        _LONG_PROMPT_05_MARGIN_TOOL,
        True,
        _METRIC_MIDEA_MARGIN,
        True,
        False,
        (),
        (),
    ),
    LongRoundTemplate(
        _LONG_LABEL_06,
        _LONG_PROMPT_06_MARGIN_FOLLOWUP,
        False,
        "",
        False,
        False,
        (),
        _CORE_FORBIDDEN_MARKERS_FOR_LONG,
    ),
    LongRoundTemplate(
        _LONG_LABEL_07,
        _LONG_PROMPT_07_MARGIN_ANTI_DRIFT,
        False,
        "",
        False,
        False,
        (),
        _CORE_FORBIDDEN_MARKERS_FOR_LONG,
    ),
    LongRoundTemplate(
        _LONG_LABEL_08,
        _LONG_PROMPT_08_MARGIN_PRESSURE,
        False,
        "",
        False,
        True,
        (),
        _CORE_FORBIDDEN_MARKERS_FOR_LONG,
    ),
    LongRoundTemplate(
        _LONG_LABEL_09,
        _LONG_PROMPT_09_EXPENSE_TOOL,
        True,
        _METRIC_MIDEA_EXPENSE,
        True,
        False,
        (),
        (),
    ),
    LongRoundTemplate(
        _LONG_LABEL_10,
        _LONG_PROMPT_10_EXPENSE_FOLLOWUP,
        False,
        "",
        False,
        False,
        (),
        _CORE_FORBIDDEN_MARKERS_FOR_LONG,
    ),
    LongRoundTemplate(
        _LONG_LABEL_11,
        _LONG_PROMPT_11_PROFIT_BRIDGE,
        False,
        "",
        False,
        False,
        (),
        _CORE_FORBIDDEN_MARKERS_FOR_LONG,
    ),
    LongRoundTemplate(
        _LONG_LABEL_12,
        _LONG_PROMPT_12_PROFIT_CONSTRAINT_CHECK,
        False,
        "",
        False,
        False,
        (),
        _CORE_FORBIDDEN_MARKERS_FOR_LONG,
    ),
    LongRoundTemplate(
        _LONG_LABEL_13,
        _LONG_PROMPT_13_ASSET_TOOL,
        True,
        _METRIC_MIDEA_ASSET,
        True,
        False,
        (),
        (),
    ),
    LongRoundTemplate(
        _LONG_LABEL_14,
        _LONG_PROMPT_14_ASSET_FOLLOWUP,
        False,
        "",
        False,
        False,
        (),
        _CORE_FORBIDDEN_MARKERS_FOR_LONG,
    ),
    LongRoundTemplate(
        _LONG_LABEL_15,
        _LONG_PROMPT_15_LIABILITY_SETUP,
        False,
        "",
        False,
        False,
        (),
        _CORE_FORBIDDEN_MARKERS_FOR_LONG,
    ),
    LongRoundTemplate(
        _LONG_LABEL_16,
        _LONG_PROMPT_16_LIABILITY_PRESSURE,
        False,
        "",
        False,
        True,
        (),
        _CORE_FORBIDDEN_MARKERS_FOR_LONG,
    ),
    LongRoundTemplate(
        _LONG_LABEL_17,
        _LONG_PROMPT_17_CASHFLOW_TOOL,
        True,
        _METRIC_MIDEA_CASHFLOW,
        True,
        False,
        (),
        (),
    ),
    LongRoundTemplate(
        _LONG_LABEL_18,
        _LONG_PROMPT_18_CASHFLOW_FOLLOWUP,
        False,
        "",
        False,
        False,
        (),
        _CORE_FORBIDDEN_MARKERS_FOR_LONG,
    ),
    LongRoundTemplate(
        _LONG_LABEL_19,
        _LONG_PROMPT_19_VALUATION_CONSTRAINT,
        False,
        "",
        False,
        False,
        (),
        _CORE_FORBIDDEN_MARKERS_FOR_LONG,
    ),
    LongRoundTemplate(
        _LONG_LABEL_20,
        _LONG_PROMPT_20_VALUATION_APPLICATION,
        False,
        "",
        False,
        False,
        (),
        _CORE_FORBIDDEN_MARKERS_FOR_LONG,
    ),
    LongRoundTemplate(
        _LONG_LABEL_21,
        _LONG_PROMPT_21_PEER_TOOL,
        True,
        _METRIC_MIDEA_PEER,
        True,
        False,
        (),
        (),
    ),
    LongRoundTemplate(
        _LONG_LABEL_22,
        _LONG_PROMPT_22_PEER_FOLLOWUP,
        False,
        "",
        False,
        False,
        (),
        _CORE_FORBIDDEN_MARKERS_FOR_LONG,
    ),
    LongRoundTemplate(
        _LONG_LABEL_23,
        _LONG_PROMPT_23_SESSION_RECAP,
        False,
        "",
        False,
        False,
        (),
        _CORE_FORBIDDEN_MARKERS_FOR_LONG,
    ),
    LongRoundTemplate(
        _LONG_LABEL_24,
        _LONG_PROMPT_24_FINAL_PRESSURE_RECAP,
        False,
        "",
        False,
        True,
        (),
        _CORE_FORBIDDEN_MARKERS_FOR_LONG,
    ),
    LongRoundTemplate(
        _LONG_LABEL_25,
        _LONG_PROMPT_25_CONSTRAINT_ASSERT,
        False,
        "",
        False,
        False,
        (
            _MARKER_MIDEA_LONG,
            _UNIT_RMB_MILLION,
            _CONSTRAINT_NO_MULTIPLE_EXTRAPOLATION,
            _CONSTRAINT_DOMESTIC_EXPORT_SPLIT,
        ),
        _CORE_FORBIDDEN_MARKERS_FOR_LONG,
    ),
)


class MockFinanceMemoryTool:
    """返回固定财报记忆事实的 runtime mock tool。"""

    def __init__(self, *, pressure_mode: PressureMode) -> None:
        """初始化工具调用观测状态。

        :param pressure_mode: 压力注入模式。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self._pressure_mode = pressure_mode
        self._tracked_session_id: str | None = None
        self._call_count = 0
        self._calls_by_key: Counter[str] = Counter()
        self._observations: list[ToolCallObservation] = []
        self._debug_output = False

    def set_pressure_mode(self, pressure_mode: PressureMode) -> None:
        """设置本次 smoke 的压力注入模式。

        provider callable 本身不接收 CLI 参数，因此 runtime assembly 后由
        ``run_smoke`` 把命令行 pressure mode 注入真实 callable 实例。

        :param pressure_mode: 压力注入模式。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self._pressure_mode = pressure_mode

    def set_debug_output(self, enabled: bool) -> None:
        """设置是否打印 smoke 工具调用诊断。

        :param enabled: ``True`` 时每次 tracked session 工具调用都会打印
            ``SMOKE TOOL_CALL``。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self._debug_output = enabled

    @property
    def call_count(self) -> int:
        """返回 tracked session 内工具调用次数。

        :returns: 已计入 tracked session 的工具调用次数。
        :raises Exception: 不主动抛出异常。
        """

        return self._call_count

    @property
    def calls_by_key(self) -> Mapping[str, int]:
        """返回按事实 key 聚合的调用次数。

        :returns: fact key 到调用次数的只读视图。
        :raises Exception: 不主动抛出异常。
        """

        return self._calls_by_key

    def snapshot(self) -> ToolCallSnapshot:
        """返回当前 tracked session 工具调用快照。

        :returns: 工具调用累计计数与 fact key 计数副本。
        :raises Exception: 不主动抛出异常。
        """

        return ToolCallSnapshot(
            total_count=self._call_count,
            calls_by_key=dict(self._calls_by_key),
        )

    def observations_since(self, snapshot: ToolCallSnapshot) -> tuple[ToolCallObservation, ...]:
        """返回指定快照之后新增的工具调用诊断。

        :param snapshot: 本轮运行前的工具调用快照。
        :returns: 新增调用诊断，按调用顺序排列。
        :raises Exception: 不主动抛出异常。
        """

        return tuple(observation for observation in self._observations if observation.sequence > snapshot.total_count)

    def track_session(self, session_id: str) -> None:
        """限定本次 smoke 计数观察的 session。

        :param session_id: 本次 smoke 需要计数的 session id。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self._tracked_session_id = session_id

    async def __call__(
        self,
        call: ToolCallRequest,
        context: BatchToolExecutionContext,
    ) -> ToolExecutionOutcome:
        """执行 mock 财报事实查询。

        :param call: 工具调用请求。
        :param context: 工具执行上下文。
        :returns: Host 工具执行结果。
        :raises Exception: 不主动抛出异常；未知事实返回 ``known=false``。
        """

        record = _find_fact_record(call.arguments)
        fact_key = record.key if record is not None else _UNKNOWN_FACT_KEY
        if self._tracked_session_id == context.session_id:
            self._call_count += 1
            self._calls_by_key.update((fact_key,))
            observation = _tool_call_observation(
                sequence=self._call_count,
                call=call,
                fact_key=fact_key,
                known=record is not None,
            )
            self._observations.append(observation)
            if self._debug_output:
                print_tool_call_observation(observation)
        if record is None:
            return ToolCompletedOutcome(
                result=ToolResultSuccess(
                    ok=True,
                    value={
                        "known": False,
                        "fact_key": _UNKNOWN_FACT_KEY,
                        "pressure_blob": "",
                    },
                    meta=None,
                )
            )
        include_pressure = _argument_bool(
            call.arguments,
            _FIELD_INCLUDE_PRESSURE,
            default=False,
        )
        pressure_blob = _mock_pressure_blob(include_pressure, self._pressure_mode)
        payload = _fact_payload(record, pressure_blob=pressure_blob)
        return ToolCompletedOutcome(
            result=ToolResultSuccess(
                ok=True,
                value=payload,
                meta=None,
            )
        )


def discover_smoke_tools(
    spec: ToolsDiscoveryProviderSpec,
) -> ToolsDiscoveryProviderOutput:
    """ToolsDiscovery provider callable，用于提供 smoke mock 财报记忆工具。

    :param spec: 工具发现 provider spec。
    :returns: smoke provider 输出。
    :raises ValueError: 工具定义字段非法时由底层抛出。
    """

    smoke_tool = MockFinanceMemoryTool(pressure_mode=PressureMode.OFF)
    return ToolsDiscoveryProviderOutput(
        provider_id=_PROVIDER_ID,
        version_ref=_PROVIDER_VERSION,
        source_refs=(
            ToolBundleSourceRef(
                source_kind=ToolBundleSourceKind.CONFIG_BINDING,
                source_id=spec.spec_id,
            ),
        ),
        definitions=(_smoke_tool_definition(smoke_tool),),
    )


class _SingleEventWorkerHandle:
    """deterministic smoke 使用的单事件 worker handle。

    :param worker_id: 本地 worker id。
    :param event: 要产出的 Engine event。
    """

    def __init__(self, *, worker_id: str, event: EngineEvent) -> None:
        """初始化单事件 handle。

        :param worker_id: 本地 worker id。
        :param event: 要产出的 Engine event。
        :returns: ``None``。
        :raises ValueError: worker id 为空时抛出。
        """

        if worker_id.strip() == "":
            raise ValueError("worker_id must be non-empty")
        self._worker_id = worker_id
        self._event = event

    @property
    def local_worker_id(self) -> str:
        """返回 worker id。

        :returns: worker id。
        :raises Exception: 不主动抛出异常。
        """

        return self._worker_id

    async def events(self) -> AsyncIterator[EngineEvent]:
        """产出单个 Engine event。

        :returns: EngineEvent 异步迭代器。
        :raises Exception: 不主动抛出异常。
        """

        yield self._event

    async def close(self) -> None:
        """关闭 handle。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        return None

    def on_cancel(self, reason: str) -> None:
        """接收取消通知。

        :param reason: 取消原因。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        del reason


class _DeterministicCompactWorker:
    """deterministic compact smoke 的普通 worker。

    :param factory: 所属 factory。
    """

    def __init__(self, factory: "_DeterministicCompactWorkerFactory") -> None:
        """初始化 worker。

        :param factory: 所属 factory。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self._factory = factory

    async def accept(
        self,
        snapshot: AttemptDispatchSnapshot,
        request: AgentRunRequest,
    ) -> LocalWorkerHandle:
        """记录 dispatch 输入并返回 deterministic handle。

        :param snapshot: dispatch snapshot。
        :param request: Engine request。
        :returns: 单事件 worker handle。
        :raises Exception: 不主动抛出异常。
        """

        self._factory.requests.append(request)
        self._factory.snapshots.append(snapshot)
        if self._factory.should_emit_reactive_request():
            return _SingleEventWorkerHandle(
                worker_id=_SMOKE_REACTIVE_WORKER_ID,
                event=_reactive_compaction_requested_event(snapshot),
            )
        return _SingleEventWorkerHandle(
            worker_id=_SMOKE_FINAL_WORKER_ID,
            event=_final_answer_event(
                snapshot,
                f"{_SMOKE_FINAL_ANSWER_PREFIX}: {len(self._factory.requests)}",
            ),
        )


class _DeterministicCompactWorkerFactory:
    """deterministic compact smoke 共用 worker factory。

    :param reactive_overflow_accept_index: 第几次 ordinary accept 产出 reactive
        compact request；为 ``None`` 时所有 accept 都产出 final answer。
    """

    def __init__(self, *, reactive_overflow_accept_index: int | None) -> None:
        """初始化 factory。

        :param reactive_overflow_accept_index: reactive overflow accept 序号。
        :returns: ``None``。
        :raises ValueError: 序号非正时抛出。
        """

        if reactive_overflow_accept_index is not None and reactive_overflow_accept_index < 1:
            raise ValueError("reactive_overflow_accept_index must be positive")
        self._reactive_overflow_accept_index = reactive_overflow_accept_index
        self.requests: list[AgentRunRequest] = []
        self.snapshots: list[AttemptDispatchSnapshot] = []

    def create_worker(self, snapshot: AttemptDispatchSnapshot) -> LocalEngineWorker:
        """创建 deterministic worker。

        :param snapshot: dispatch snapshot。
        :returns: deterministic worker。
        :raises Exception: 不主动抛出异常。
        """

        del snapshot
        return _DeterministicCompactWorker(self)

    def should_emit_reactive_request(self) -> bool:
        """判断当前 accept 是否应产出 reactive compact request。

        :returns: 当前累计 accept 数命中 reactive 序号时返回 ``True``。
        :raises Exception: 不主动抛出异常。
        """

        return self._reactive_overflow_accept_index == len(self.requests)


@dataclass(slots=True)
class _AcceptingSmokeCompactorRunner:
    """返回 deterministic accepted compact proposal 的 smoke compactor runner。

    :param prompt_lengths: 每次 compactor user prompt 字符数。
    :param material_jsons: 每次 compactor material JSON。
    """

    prompt_lengths: list[int]
    material_jsons: list[Mapping[str, JsonValue]]

    def __init__(self) -> None:
        """初始化记录容器。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.prompt_lengths = []
        self.material_jsons = []

    async def __call__(self, request: AgentRunRequest, *, timeout_seconds: float) -> AgentRunResult:
        """返回 strict JSON final answer outcome。

        :param request: compactor Engine request。
        :param timeout_seconds: compactor 超时；fake 不使用。
        :returns: final answer outcome。
        :raises AssertionError: compactor request 不是预期单 user prompt 时抛出。
        """

        del timeout_seconds
        _assert_at_most_one_system_message(request.messages, label="accepting compactor request")
        user_prompt = _compactor_user_prompt(request)
        material_json = _material_json_from_compactor_prompt(user_prompt)
        self.prompt_lengths.append(len(user_prompt))
        self.material_jsons.append(material_json)
        return EngineRunOutcomeFinalAnswer(
            session_id=request.session_id,
            run_id=request.run_id,
            content=_fake_compaction_proposal_from_material_json(material_json),
            filtered=False,
            degraded=False,
            finish_reason=FinishReason.STOP,
        )


@dataclass(slots=True)
class _RejectingSmokeCompactorRunner:
    """返回必然被 semantic barrier 拒绝的 smoke compactor runner。

    :param prompt_lengths: 每次 compactor user prompt 字符数。
    :param material_jsons: 每次 compactor material JSON。
    """

    prompt_lengths: list[int]
    material_jsons: list[Mapping[str, JsonValue]]

    def __init__(self) -> None:
        """初始化记录容器。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.prompt_lengths = []
        self.material_jsons = []

    async def __call__(self, request: AgentRunRequest, *, timeout_seconds: float) -> AgentRunResult:
        """返回引用 current input anchor 的非法 proposal。

        :param request: compactor Engine request。
        :param timeout_seconds: compactor 超时；fake 不使用。
        :returns: final answer outcome。
        :raises AssertionError: compactor request 不是预期单 user prompt 时抛出。
        """

        del timeout_seconds
        _assert_at_most_one_system_message(request.messages, label="rejecting compactor request")
        user_prompt = _compactor_user_prompt(request)
        material_json = _material_json_from_compactor_prompt(user_prompt)
        self.prompt_lengths.append(len(user_prompt))
        self.material_jsons.append(material_json)
        return EngineRunOutcomeFinalAnswer(
            session_id=request.session_id,
            run_id=request.run_id,
            content=_invalid_current_anchor_citation_proposal(),
            filtered=False,
            degraded=False,
            finish_reason=FinishReason.STOP,
        )


def _reactive_compaction_requested_event(snapshot: AttemptDispatchSnapshot) -> EngineEvent:
    """构造 reactive compact requested Engine event。

    :param snapshot: 当前 dispatch snapshot。
    :returns: EngineEvent。
    :raises Exception: 不主动抛出异常。
    """

    return EngineEvent(
        occurred_at=_SMOKE_DETERMINISTIC_EVENT_TIME,
        session_id=snapshot.session_id,
        run_id=snapshot.run_id,
        type=EngineEventType.CONTEXT_COMPACTION_REQUESTED,
        data=ContextCompactionRequestedData(
            iteration_id=_SMOKE_REACTIVE_ITERATION_ID,
            budget_state=None,
            reason=_SMOKE_REACTIVE_REASON,
            provider_request_id=_SMOKE_REACTIVE_PROVIDER_REQUEST_ID,
        ),
        metadata=None,
    )


def _final_answer_event(snapshot: AttemptDispatchSnapshot, content: str) -> EngineEvent:
    """构造 final answer Engine event。

    :param snapshot: 当前 dispatch snapshot。
    :param content: final answer 文本。
    :returns: EngineEvent。
    :raises ValueError: content 为空时抛出。
    """

    if content.strip() == "":
        raise ValueError("content must be non-empty")
    return EngineEvent(
        occurred_at=_SMOKE_DETERMINISTIC_EVENT_TIME,
        session_id=snapshot.session_id,
        run_id=snapshot.run_id,
        type=EngineEventType.FINAL_ANSWER,
        data=FinalAnswerData(
            content=content,
            filtered=False,
            degraded=False,
            finish_reason=FinishReason.STOP,
        ),
        metadata=None,
    )


@contextmanager
def _patched_compactor_runner(runner: SmokeCompactorRunner) -> Iterator[None]:
    """临时替换 Host LLM compactor 的 Engine runner 边界。

    :param runner: smoke-local deterministic compactor runner。
    :returns: context manager iterator。
    :raises RuntimeError: patch 未生效时抛出。
    :raises Exception: context 内异常原样向上抛出。
    """

    try:
        original_runner = llm_compaction._run_agent_request
    except AttributeError as exc:
        raise RuntimeError(
            "Host compactor runner hook changed: "
            "dayu.host.llm_compaction._run_agent_request is missing"
        ) from exc
    try:
        llm_compaction._run_agent_request = runner
        if llm_compaction._run_agent_request is not runner:
            raise RuntimeError("failed to patch dayu.host.llm_compaction._run_agent_request")
        yield
    finally:
        llm_compaction._run_agent_request = original_runner


def _compactor_user_prompt(request: AgentRunRequest) -> str:
    """读取 compactor request 的唯一 user prompt。

    :param request: compactor Engine request。
    :returns: user prompt 文本。
    :raises AssertionError: user prompt 数量不是 1 时抛出。
    """

    user_messages = tuple(message for message in request.messages if isinstance(message, UserMessage))
    if len(user_messages) != 1:
        raise AssertionError(f"compactor request expected one user message, got {len(user_messages)}")
    return user_messages[0].content


def _material_json_from_compactor_prompt(prompt: str) -> Mapping[str, JsonValue]:
    """从 compactor prompt 中提取 bounded material JSON。

    :param prompt: compactor user prompt。
    :returns: material JSON object。
    :raises AssertionError: prompt 缺少 material delimiter 或 JSON 不是 object 时抛出。
    """

    begin_index = prompt.find(_COMPACTOR_MATERIAL_BEGIN)
    end_index = prompt.find(_COMPACTOR_MATERIAL_END)
    if begin_index < 0 or end_index <= begin_index:
        raise AssertionError("compactor prompt missing material JSON delimiters")
    json_start = begin_index + len(_COMPACTOR_MATERIAL_BEGIN)
    parsed = cast(JsonValue, json.loads(prompt[json_start:end_index].strip()))
    if not isinstance(parsed, Mapping):
        raise AssertionError("compactor material JSON must be object")
    return cast(Mapping[str, JsonValue], parsed)


def _fake_compaction_proposal_from_material_json(material_json: Mapping[str, JsonValue]) -> str:
    """从 LLM-facing material JSON 生成 deterministic strict proposal。

    :param material_json: Host 投影给 compactor 的 material JSON。
    :returns: strict JSON proposal 文本。
    :raises TypeError: material JSON 字段类型非法时抛出。
    """

    evidence_items = _proposal_labeled_items(material_json, _COMPACTOR_FIELD_EVIDENCE_MATERIAL)
    answer_items = _proposal_labeled_items(material_json, _COMPACTOR_FIELD_ANSWER_MATERIAL)
    trace_labels = _proposal_source_labels(material_json, _COMPACTOR_FIELD_TRACE_MATERIAL)
    previous_labels = _proposal_previous_labels(material_json)
    evidence_labels = tuple(item[0] for item in evidence_items)
    answer_labels = tuple(item[0] for item in answer_items)
    summary_labels = (*trace_labels, *evidence_labels, *answer_labels)
    continuity_labels = (*previous_labels, *trace_labels, *answer_labels)
    proposal: dict[str, JsonValue] = {
        "schema_version": CONVERSATION_COMPACT_OUTPUT_SCHEMA_VERSION_VNEXT,
        "session_summary": (
            {
                "summary_text": _SMOKE_COMPACTOR_SUMMARY_TEXT,
                "source_labels": list(summary_labels),
            }
            if summary_labels
            else None
        ),
        "evidence_backed_facts": [
            {
                "claim_text": f"{_SMOKE_COMPACTOR_FACT_PREFIX}{_sanitize_compactor_material_text(text)}",
                "evidence_labels": [label],
                "source_labels": [label],
            }
            for label, text in evidence_items
        ],
        "answer_anchors": [
            {
                "anchor_title": _SMOKE_COMPACTOR_ANSWER_TITLE,
                "anchor_items": [{"display_text": _sanitize_compactor_material_text(text), "ordinal": None}],
                "answer_source_labels": [label],
            }
            for label, text in answer_items
        ],
        "forward_intents": (
            [
                {
                    "intent_type": ForwardIntentTypeVNext.NEXT_STEP_NOTE.value,
                    "text": _SMOKE_COMPACTOR_FORWARD_TEXT,
                    "status": ForwardIntentStatusVNext.OPEN.value,
                    "source_labels": [continuity_labels[0]],
                }
            ]
            if continuity_labels
            else []
        ),
        "reference_continuity_items": (
            [
                {
                    "text": _SMOKE_COMPACTOR_REFERENCE_TEXT,
                    "reason": ReferenceContinuityReasonVNext.LOCAL_REFERENCE.value,
                    "source_labels": [continuity_labels[0]],
                }
            ]
            if continuity_labels
            else []
        ),
        "diagnostics": [],
    }
    return json.dumps(proposal, ensure_ascii=False, sort_keys=True)


def _sanitize_compactor_material_text(text: str) -> str:
    """移除 deterministic smoke marker，避免 fake compact view 回写测试探针。

    :param text: compactor material 文本。
    :returns: 已移除 smoke marker 的文本。
    :raises Exception: 不主动抛出异常。
    """

    sanitized = text
    for marker in _SMOKE_COMPACTOR_MARKERS:
        sanitized = sanitized.replace(marker, _SMOKE_COMPACTOR_MARKER_REPLACEMENT)
    return sanitized


def _invalid_current_anchor_citation_proposal() -> str:
    """构造引用 current input anchor 的非法 compact proposal。

    :returns: strict JSON proposal 文本。
    :raises TypeError: JSON 编码失败时由标准库抛出。
    """

    proposal: Mapping[str, JsonValue] = {
        "schema_version": CONVERSATION_COMPACT_OUTPUT_SCHEMA_VERSION_VNEXT,
        "session_summary": {
            "summary_text": "invalid current-anchor citation",
            "source_labels": [_SMOKE_INVALID_CURRENT_ANCHOR_LABEL],
        },
        "evidence_backed_facts": [],
        "answer_anchors": [],
        "forward_intents": [],
        "reference_continuity_items": [],
        "diagnostics": [],
    }
    return json.dumps(proposal, ensure_ascii=False, sort_keys=True)


def _proposal_labeled_items(
    material_json: Mapping[str, JsonValue],
    field_name: str,
) -> tuple[tuple[str, str], ...]:
    """读取 material section 中的 label 与文本。

    :param material_json: material JSON。
    :param field_name: section 字段名。
    :returns: ``(label, text)`` 元组。
    :raises TypeError: section item 不是 object 时抛出。
    """

    values = _json_list_or_empty(material_json, field_name)
    items: list[tuple[str, str]] = []
    for index, value in enumerate(values):
        item = _json_object(value, field_name=f"{field_name}[{index}]")
        label = _json_label(item)
        text = _json_string_alias(item, _COMPACTOR_FIELD_RESPONSE_TEXT, _COMPACTOR_FIELD_RESULT_TEXT)
        if text == "":
            text = _json_string_alias(item, _COMPACTOR_FIELD_ANSWER_TEXT, _COMPACTOR_FIELD_RESULT_TEXT)
        items.append((label, text))
    return tuple(items)


def _proposal_source_labels(material_json: Mapping[str, JsonValue], field_name: str) -> tuple[str, ...]:
    """读取 material section 中的 source labels。

    :param material_json: material JSON。
    :param field_name: section 字段名。
    :returns: label 元组。
    :raises TypeError: section item 不是 object 时抛出。
    """

    labels: list[str] = []
    values = _json_list_or_empty(material_json, field_name)
    for index, value in enumerate(values):
        item = _json_object(value, field_name=f"{field_name}[{index}]")
        labels.append(_json_label(item))
    return tuple(labels)


def _proposal_previous_labels(material_json: Mapping[str, JsonValue]) -> tuple[str, ...]:
    """读取 previous compacted view 中可用于 continuity 的 labels。

    :param material_json: material JSON。
    :returns: previous labels。
    :raises TypeError: previous compacted view 字段类型非法时抛出。
    """

    previous = material_json.get(_COMPACTOR_FIELD_PREVIOUS_COMPACTED_VIEW)
    if previous is None:
        return ()
    if not isinstance(previous, Mapping):
        raise TypeError("previous_compacted_view must be object or null")
    labels: list[str] = []
    previous_mapping = cast(Mapping[str, JsonValue], previous)
    for key in (
        "evidence_backed_facts",
        "answer_anchors",
        "forward_intents",
        "reference_continuity_items",
    ):
        for index, value in enumerate(_json_list_or_empty(previous_mapping, key)):
            item = _json_object(value, field_name=f"{key}[{index}]")
            labels.extend(_json_source_label_values(item))
    return tuple(labels)


def _json_list_or_empty(data: Mapping[str, JsonValue], field_name: str) -> tuple[JsonValue, ...]:
    """读取 JSON list 字段。

    :param data: JSON object。
    :param field_name: 字段名。
    :returns: list 内容元组；字段缺失或为 ``None`` 时返回空元组。
    :raises TypeError: 字段存在但不是 list 时抛出。
    """

    value = data.get(field_name)
    if value is None:
        return ()
    if not isinstance(value, Sequence) or isinstance(value, str):
        raise TypeError(f"{field_name} must be list")
    return tuple(cast(Sequence[JsonValue], value))


def _json_object(value: JsonValue, *, field_name: str) -> Mapping[str, JsonValue]:
    """校验并返回 JSON object。

    :param value: JSON value。
    :param field_name: 诊断字段名。
    :returns: JSON object。
    :raises TypeError: value 不是 object 时抛出。
    """

    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be object")
    return cast(Mapping[str, JsonValue], value)


def _json_label(data: Mapping[str, JsonValue]) -> str:
    """读取 material item 的 label。

    :param data: material item。
    :returns: 非空 label。
    :raises TypeError: label 缺失或为空时抛出。
    """

    value = data.get(_COMPACTOR_FIELD_LABEL, data.get(_COMPACTOR_FIELD_SOURCE_LABEL))
    if not isinstance(value, str) or value.strip() == "":
        raise TypeError("material item label must be non-empty string")
    return value


def _json_string_alias(data: Mapping[str, JsonValue], primary: str, fallback: str) -> str:
    """读取字符串字段别名。

    :param data: JSON object。
    :param primary: 优先字段名。
    :param fallback: 备选字段名。
    :returns: 字符串值；缺失或类型不匹配时返回空字符串。
    :raises Exception: 不主动抛出异常。
    """

    primary_value = data.get(primary)
    if isinstance(primary_value, str):
        return primary_value
    fallback_value = data.get(fallback)
    if isinstance(fallback_value, str):
        return fallback_value
    return ""


def _json_source_label_values(data: Mapping[str, JsonValue]) -> tuple[str, ...]:
    """读取 previous view item 中的 source label 序列。

    :param data: previous view item。
    :returns: source labels。
    :raises Exception: 不主动抛出异常。
    """

    labels = _compact_payload_str_tuple(data, _COMPACTOR_FIELD_SOURCE_LABELS)
    if labels:
        return labels
    label = _compact_payload_str(data, _COMPACTOR_FIELD_SOURCE_LABEL)
    if label is None:
        return ()
    return (label,)


def parse_args(argv: Sequence[str]) -> SmokeArgs:
    """解析命令行参数。

    :param argv: 不包含程序名的命令行参数序列。
    :returns: 结构化 smoke 参数。
    :raises SystemExit: 参数非法时由 ``argparse`` fail closed。
    """

    parser = argparse.ArgumentParser(description="Host public 财报对话记忆场景 smoke。")
    parser.add_argument(
        "--workspace-root",
        default=None,
        help=(
            "workspace / project root；默认使用 workspace/tmp 下的 fresh smoke "
            "workspace，避免历史 durable DB schema 污染。"
        ),
    )
    parser.add_argument("--scene-id", default=_DEFAULT_SCENE_ID)
    parser.add_argument("--execution-profile-id", default=None)
    parser.add_argument("--host-runtime-id", default=None)
    parser.add_argument("--model-id", default=None)
    parser.add_argument("--runner-option-hint-id", default=None)
    parser.add_argument(
        "--log-level",
        choices=tuple(level.name for level in LogLevel),
        default=_DEFAULT_LOG_LEVEL,
    )
    parser.add_argument("--reuse-session", action="store_true")
    parser.add_argument("--keep-workspace", action="store_true")
    parser.add_argument(
        "--suite",
        choices=tuple(item.value for item in SuiteMode),
        default=SuiteMode.MEMORY_CORE.value,
    )
    parser.add_argument(
        "--long-rounds",
        type=_parse_long_rounds,
        default=_DEFAULT_LONG_ROUNDS,
    )
    parser.add_argument(
        "--pressure-mode",
        choices=tuple(item.value for item in PressureMode),
        default=PressureMode.OFF.value,
    )
    namespace = parser.parse_args(tuple(argv))
    workspace_root_text: str | None = namespace.workspace_root
    scene_id: str = namespace.scene_id
    execution_profile_id: str | None = namespace.execution_profile_id
    host_runtime_id: str | None = namespace.host_runtime_id
    model_id: str | None = namespace.model_id
    runner_option_hint_id: str | None = namespace.runner_option_hint_id
    log_level_text: str = namespace.log_level
    reuse_session: bool = namespace.reuse_session
    keep_workspace: bool = namespace.keep_workspace
    suite_text: str = namespace.suite
    long_rounds: int = namespace.long_rounds
    pressure_mode_text: str = namespace.pressure_mode
    pressure_suite = SuiteMode(suite_text)
    pressure_mode = PressureMode(pressure_mode_text)
    if pressure_suite in (
        SuiteMode.MEMORY_COMPACT,
        SuiteMode.MEMORY_COMPACT_FALLBACK,
    ) and pressure_mode is PressureMode.OFF:
        parser.error(f"--suite {pressure_suite.value} requires --pressure-mode auto")
    log_level = LogLevel[log_level_text]
    return SmokeArgs(
        workspace_root=_resolve_workspace_root(workspace_root_text),
        scene_id=scene_id,
        execution_profile_id=execution_profile_id,
        host_runtime_id=host_runtime_id,
        model_id=model_id,
        runner_option_hint_id=runner_option_hint_id,
        log_level=log_level,
        reuse_session=reuse_session,
        keep_workspace=keep_workspace,
        suite=pressure_suite,
        long_rounds=long_rounds,
        pressure_mode=pressure_mode,
        debug_smoke_output=log_level is LogLevel.DEBUG,
    )


def _resolve_workspace_root(workspace_root_text: str | None) -> pathlib.Path:
    """解析 smoke workspace root。

    :param workspace_root_text: CLI 显式传入的 workspace root；为 ``None`` 时
        生成 fresh smoke workspace root。
    :returns: 归一化后的 workspace root。
    :raises Exception: 不主动抛出异常。
    """

    if workspace_root_text is not None:
        return pathlib.Path(workspace_root_text).resolve()
    return (_DEFAULT_WORKSPACE_PARENT / f"{_DEFAULT_WORKSPACE_PREFIX}-{uuid4().hex[:12]}").resolve()


def select_round_specs(args: SmokeArgs) -> tuple[RoundSpec, ...]:
    """按 suite 参数选择场景轮次规格。

    :param args: smoke 参数。
    :returns: 需要执行的场景轮次规格。
    :raises ValueError: long 轮数超出 20 到 25 时抛出。
    """

    return _round_specs_for_suite(
        suite=args.suite,
        long_rounds=args.long_rounds,
        user_pressure_text=_user_pressure_placeholder(args.pressure_mode),
    )


def _round_specs_for_suite(
    *,
    suite: SuiteMode,
    long_rounds: int,
    user_pressure_text: str,
) -> tuple[RoundSpec, ...]:
    """按 suite 生成工具调用期望连续的轮次规格。

    :param suite: 需要运行的场景套件。
    :param long_rounds: long suite 轮数，范围为 20 到 25。
    :param user_pressure_text: 已按当前模式生成的用户侧压力文本。
    :returns: 需要执行的场景轮次规格。
    :raises ValueError: long 轮数超出 20 到 25 时抛出。
    """

    if suite is SuiteMode.MEMORY_CORE:
        return _core_round_specs(user_pressure_text)
    if suite is SuiteMode.MEMORY_COMPACT:
        return (*_core_round_specs(user_pressure_text), *_long_round_specs(user_pressure_text, long_rounds))
    if suite is SuiteMode.MEMORY_REACTIVE_COMPACT:
        return _reactive_compact_round_specs()
    if suite is SuiteMode.MEMORY_COMPACT_FALLBACK:
        return _fallback_compact_round_specs(user_pressure_text)
    raise ValueError(f"unsupported suite: {suite.value}")


def calls_by_key_summary(calls_by_key: Mapping[str, int]) -> str:
    """格式化工具调用 key 计数摘要。

    :param calls_by_key: fact key 到调用次数的映射。
    :returns: stdout 可打印的稳定摘要。
    :raises Exception: 不主动抛出异常。
    """

    if not calls_by_key:
        return f"{_STDOUT_TOOL_CALLS_BY_KEY} none"
    parts = tuple(f"{key}={calls_by_key[key]}" for key in sorted(calls_by_key))
    return f"{_STDOUT_TOOL_CALLS_BY_KEY} {' '.join(parts)}"


def normalize_answer(content: str) -> str:
    """归一化回答文本以做严格包含断言。

    该函数只做空白压缩、全角百分号转半角和大小写统一，不做语义猜测。

    :param content: 原始回答文本。
    :returns: 归一化后的回答文本。
    :raises Exception: 不主动抛出异常。
    """

    normalized = content.replace("％", "%").casefold()
    return _NORMALIZED_SPACE_PATTERN.sub("", normalized)


def assert_answer_contains(
    content: str,
    *,
    label: str,
    required: tuple[str, ...],
    forbidden: tuple[str, ...] = (),
) -> None:
    """断言回答包含必需片段且不包含禁止片段。

    :param content: 原始回答文本。
    :param label: 当前轮次标签。
    :param required: 必须包含的文本片段。
    :param forbidden: 禁止包含的文本片段。
    :returns: ``None``。
    :raises AssertionError: 回答缺失必需片段或包含禁止片段时抛出。
    """

    normalized = normalize_answer(content)
    for item in required:
        expected = normalize_answer(item)
        if expected not in normalized:
            raise AssertionError(f"{_ASSERTION_FAILURE_PREFIX}: label={label} missing={item}")
    for item in forbidden:
        blocked = normalize_answer(item)
        if blocked in normalized:
            raise AssertionError(f"{_ASSERTION_FAILURE_PREFIX}: label={label} forbidden={item}")


def observe_soft_answer_contains(
    content: str,
    *,
    label: str,
    markers: tuple[str, ...],
) -> tuple[str, ...]:
    """返回回答缺失的 soft observation marker。

    :param content: 原始回答文本。
    :param label: 当前轮次标签；保留给调用方打印诊断。
    :param markers: 建议包含但不作为硬失败的片段。
    :returns: 缺失的 soft marker。
    :raises Exception: 不主动抛出异常。
    """

    del label
    normalized = normalize_answer(content)
    return tuple(marker for marker in markers if normalize_answer(marker) not in normalized)


def _parse_long_rounds(raw_value: str) -> int:
    """解析 long suite 轮数并执行边界检查。

    :param raw_value: 命令行传入的原始字符串。
    :returns: 合法 long suite 轮数。
    :raises argparse.ArgumentTypeError: 值不是整数或超出 20 到 25 时抛出。
    """

    try:
        value = int(raw_value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("--long-rounds must be an integer") from exc
    if value < _MIN_LONG_ROUNDS or value > _MAX_LONG_ROUNDS:
        raise argparse.ArgumentTypeError("--long-rounds must be in range 20..25")
    return value


def _core_round_specs(user_pressure_text: str) -> tuple[RoundSpec, ...]:
    """构造 core suite 场景规格。

    :param user_pressure_text: 已按当前模式生成的用户侧压力文本。
    :returns: core suite 的固定轮次规格。
    :raises Exception: 不主动抛出异常。
    """

    tool = frozenset((_TOOL_NAME,))
    return (
        RoundSpec(
            _LABEL_CORE_A1,
            (
                "请调用 get_mock_finance_memory_fact 查询贵州茅台 600519.SH 2024H1 "
                "产品系列收入增长，参数 company=贵州茅台、ticker=600519.SH、period=2024H1、"
                "topic=revenue_product_growth、metric=maotai_revenue、include_pressure=false。"
                f"回答末尾输出 {_ASSERT_A}。"
            ),
            tool,
            _FACT_KEY_MAOTAI_REVENUE,
            (_MARKER_MAOTAI_REVENUE, _VALUE_MAOTAI_WINE_YOY, _VALUE_MAOTAI_SERIES_YOY),
            (),
            (),
            True,
        ),
        RoundSpec(
            _LABEL_CORE_A2,
            "把刚才提到的产品系列对应的销量也一起列出来；如果会话里没有销量事实，请明确说没有，不要编数字。"
            "回答仍需保留当前主体、期间和百万元口径。",
            _NO_TOOL_SELECTION,
            None,
            (),
            (_MARKER_WULIANGYE_REVENUE,),
            ("没有",),
            False,
        ),
        RoundSpec(
            _LABEL_CORE_A3,
            (
                "请调用 get_mock_finance_memory_fact 切换到五粮液 000858.SZ 2024H1 "
                "同口径产品系列拆分，参数 company=五粮液、ticker=000858.SZ、period=2024H1、"
                "topic=revenue_product_growth、metric=wuliangye_revenue、include_pressure=false。"
                f"回答末尾输出 {_ASSERT_A_SWITCH}。"
            ),
            tool,
            _FACT_KEY_WULIANGYE_REVENUE,
            (
                _MARKER_WULIANGYE_REVENUE,
                _VALUE_WULIANGYE_CORE_YOY,
                _VALUE_WULIANGYE_SERIES_YOY,
            ),
            (),
            (),
            True,
        ),
        RoundSpec(
            _LABEL_CORE_A4,
            f"回到茅台，刚才茅台酒和系列酒同比增速再确认一遍；不要调用工具，最后输出 {_ASSERT_A_RETURN}。",
            _NO_TOOL_SELECTION,
            None,
            (_MARKER_MAOTAI_REVENUE, _VALUE_MAOTAI_WINE_YOY, _VALUE_MAOTAI_SERIES_YOY),
            (
                _MARKER_WULIANGYE_REVENUE,
                _VALUE_WULIANGYE_CORE_YOY,
                _VALUE_WULIANGYE_SERIES_YOY,
            ),
            (),
            False,
        ),
        RoundSpec(
            _LABEL_CORE_B1,
            (
                "请调用 get_mock_finance_memory_fact 查询宁德时代 300750.SZ 2024A "
                "现金流关键数据，参数 company=宁德时代、ticker=300750.SZ、period=2024A、"
                "topic=cashflow、metric=catl_cashflow、include_pressure=false。"
                "回答末尾输出断言行：DAYU_MEM_ASSERT_B_CFO "
                "marker=<工具返回marker> operating_cf=<工具返回经营现金流> "
                "net_profit=<工具返回净利润> largest_gap=<工具返回最大差异项目>。"
            ),
            tool,
            _FACT_KEY_CATL_CASHFLOW,
            (_MARKER_CATL_CASHFLOW, _VALUE_CATL_OPERATING_CF, _VALUE_CATL_LARGEST_GAP),
            (),
            (),
            True,
        ),
        RoundSpec(
            _LABEL_CORE_B2,
            f"这个数和净利润比，差异在哪个项目最大？不要调用工具。最后输出 {_ASSERT_B_FOLLOW}。",
            _NO_TOOL_SELECTION,
            None,
            (_MARKER_CATL_CASHFLOW, _VALUE_CATL_LARGEST_GAP),
            (),
            (),
            False,
        ),
        RoundSpec(
            _LABEL_CORE_B3,
            "投资活动的支出主要花在什么上？如果当前会话没有确认过，不要编造。",
            _NO_TOOL_SELECTION,
            None,
            (),
            (),
            ("没有确认",),
            False,
        ),
        RoundSpec(
            _LABEL_CORE_C1,
            "我准备分析比亚迪 2024H1 毛利率结构变化。后续只根据我贴的原文回答。",
            _NO_TOOL_SELECTION,
            None,
            (),
            (),
            (),
            False,
        ),
        RoundSpec(
            _LABEL_CORE_C2,
            (
                f"{_build_byd_long_input()}\n\n"
                "基于以上原文，提炼影响毛利率的三个最重要因素，按重要性排序。"
                f"回答最后输出 {_ASSERT_C_LONG}。"
            ),
            _NO_TOOL_SELECTION,
            None,
            (),
            (),
            (_MARKER_BYD_LONG_FACTOR2, _BYD_FACTOR2_MARKER),
            False,
        ),
        RoundSpec(
            _LABEL_CORE_C3,
            f"第二个因素能再展开讲讲吗？不要调用工具。最后单独输出 {_ASSERT_C_FOLLOW}。",
            _NO_TOOL_SELECTION,
            None,
            (_MARKER_BYD_LONG_FACTOR2, _BYD_FACTOR2_MARKER),
            (),
            (),
            False,
        ),
        RoundSpec(
            _LABEL_CORE_D1,
            (
                "请调用 get_mock_finance_memory_fact 查询招商银行 600036.SH 2024H1 息差数据，"
                "参数 company=招商银行、ticker=600036.SH、period=2024H1、topic=net_interest_margin、"
                f"metric=cmb_nim、include_pressure=true。回答末尾输出 {_ASSERT_D_NIM}。"
            ),
            tool,
            _FACT_KEY_CMB_NIM,
            (_MARKER_CMB_NIM, _VALUE_CMB_NIM, _VALUE_CMB_NIM_YOY),
            (),
            (),
            True,
        ),
        RoundSpec(
            _LABEL_CORE_D2,
            f"按“资产 / 负债 / 息差”三组重排，不要调用工具，并追加压力观察文本：{user_pressure_text}。"
            f"回答末尾尽量输出同一 {_ASSERT_D_NIM}。",
            _NO_TOOL_SELECTION,
            None,
            (),
            (),
            (_MARKER_CMB_NIM, _VALUE_CMB_NIM, _VALUE_CMB_NIM_YOY),
            False,
        ),
        RoundSpec(
            _LABEL_CORE_D3,
            "不调用工具。招商银行刚才讨论中不良率是多少？如果会话里没有确认，明确说明未确认。",
            _NO_TOOL_SELECTION,
            None,
            (),
            (),
            (_VALUE_CMB_NPL_RATIO,),
            False,
        ),
        RoundSpec(
            _LABEL_CORE_D4,
            f"回到刚才息差讨论，净息差具体数值和同比变化再确认，最后输出 {_ASSERT_D_RETURN}。",
            _NO_TOOL_SELECTION,
            None,
            (_MARKER_CMB_NIM, _VALUE_CMB_NIM, _VALUE_CMB_NIM_YOY),
            (),
            (),
            False,
        ),
    )


def _long_round_specs(
    user_pressure_text: str,
    round_count: int,
) -> tuple[RoundSpec, ...]:
    """构造 long suite 场景规格。

    :param user_pressure_text: 已按当前模式生成的用户侧压力文本。
    :param round_count: long suite 轮数，范围为 20 到 25。
    :returns: long suite 的轮次规格。
    :raises ValueError: ``round_count`` 超出 20 到 25 时抛出。
    """

    templates = _select_long_templates(round_count)
    specs: list[RoundSpec] = []
    for template in templates:
        tool_names = frozenset((_TOOL_NAME,)) if template.tool_enabled else _NO_TOOL_SELECTION
        pressure_text = user_pressure_text if template.include_user_pressure else ""
        specs.append(
            RoundSpec(
                label=template.label,
                prompt=template.prompt_template.format(auto_user_pressure=pressure_text),
                tool_names=tool_names,
                expected_tool_fact_key=_long_required_tool_fact_key(template),
                hard_answer_contains=template.hard_contains,
                hard_answer_forbidden=template.hard_forbidden,
                soft_answer_contains=(),
                print_calls_by_key=template.tool_enabled,
            )
        )
    return tuple(specs)


def _reactive_compact_round_specs() -> tuple[RoundSpec, ...]:
    """构造 reactive compact deterministic suite 轮次。

    :returns: 六轮 public Host followup：旧种子、历史填充、近期保护种子和
        reactive 目标轮。
    :raises Exception: 不主动抛出异常。
    """

    return (
        RoundSpec(
            label="reactive-r1-old-seed",
            prompt=f"记录旧上下文种子 {_SMOKE_REACTIVE_OLD_MARKER}，后续只作为 compact 可丢弃历史。",
            tool_names=_NO_TOOL_SELECTION,
            expected_tool_fact_key=None,
            hard_answer_contains=(),
            hard_answer_forbidden=(),
            soft_answer_contains=(),
            print_calls_by_key=False,
        ),
        RoundSpec(
            label="reactive-r2-history-gap",
            prompt="记录 reactive 历史间隔 1，用于把旧种子推出 recent floor。",
            tool_names=_NO_TOOL_SELECTION,
            expected_tool_fact_key=None,
            hard_answer_contains=(),
            hard_answer_forbidden=(),
            soft_answer_contains=(),
            print_calls_by_key=False,
        ),
        RoundSpec(
            label="reactive-r3-history-gap",
            prompt="记录 reactive 历史间隔 2，用于把旧种子推出 recent floor。",
            tool_names=_NO_TOOL_SELECTION,
            expected_tool_fact_key=None,
            hard_answer_contains=(),
            hard_answer_forbidden=(),
            soft_answer_contains=(),
            print_calls_by_key=False,
        ),
        RoundSpec(
            label="reactive-r4-history-gap",
            prompt="记录 reactive 历史间隔 3，用于把旧种子推出 recent floor。",
            tool_names=_NO_TOOL_SELECTION,
            expected_tool_fact_key=None,
            hard_answer_contains=(),
            hard_answer_forbidden=(),
            soft_answer_contains=(),
            print_calls_by_key=False,
        ),
        RoundSpec(
            label="reactive-r5-protected-recent",
            prompt=f"记录近期保护种子 {_SMOKE_REACTIVE_RECENT_MARKER}，用于验证 protected recent floor。",
            tool_names=_NO_TOOL_SELECTION,
            expected_tool_fact_key=None,
            hard_answer_contains=(),
            hard_answer_forbidden=(),
            soft_answer_contains=(),
            print_calls_by_key=False,
        ),
        RoundSpec(
            label="reactive-r6-overflow-target",
            prompt=f"目标轮当前输入 marker {_SMOKE_REACTIVE_CURRENT_MARKER}，worker 将报告 reactive overflow。",
            tool_names=_NO_TOOL_SELECTION,
            expected_tool_fact_key=None,
            hard_answer_contains=(),
            hard_answer_forbidden=(),
            soft_answer_contains=(),
            print_calls_by_key=False,
        ),
    )


def _fallback_compact_round_specs(user_pressure_text: str) -> tuple[RoundSpec, ...]:
    """构造 compact failure fallback deterministic suite 轮次。

    :param user_pressure_text: 足以触发 proactive compact 的 bounded 压力文本。
    :returns: 三轮 public Host followup：旧种子、近期种子和 fallback 目标轮。
    :raises Exception: 不主动抛出异常。
    """

    old_specs = tuple(
        RoundSpec(
            label=f"fallback-f{index}-old-dropped",
            prompt=(
                "记录 fallback 旧上下文 "
                f"{_fallback_old_marker_for_index(index)} old_index={index}，"
                "后续最老材料应被 fallback window 丢弃。"
            ),
            tool_names=_NO_TOOL_SELECTION,
            expected_tool_fact_key=None,
            hard_answer_contains=(),
            hard_answer_forbidden=(),
            soft_answer_contains=(),
            print_calls_by_key=False,
        )
        for index in range(1, 6)
    )
    return (
        *old_specs,
        RoundSpec(
            label="fallback-f6-selected-recent",
            prompt=f"记录 fallback 近期上下文 {_SMOKE_FALLBACK_RECENT_MARKER}，后续必须保留。",
            tool_names=_NO_TOOL_SELECTION,
            expected_tool_fact_key=None,
            hard_answer_contains=(),
            hard_answer_forbidden=(),
            soft_answer_contains=(),
            print_calls_by_key=False,
        ),
        RoundSpec(
            label="fallback-f7-pressure-target",
            prompt=(
                f"{user_pressure_text}\n"
                f"目标 fallback 当前输入 marker {_SMOKE_FALLBACK_CURRENT_MARKER}，"
                "compactor 将 deterministic reject 到 fallback dispatch。"
            ),
            tool_names=_NO_TOOL_SELECTION,
            expected_tool_fact_key=None,
            hard_answer_contains=(),
            hard_answer_forbidden=(),
            soft_answer_contains=(),
            print_calls_by_key=False,
        ),
    )


def _fallback_old_marker_for_index(index: int) -> str:
    """返回 fallback 旧种子 marker。

    :param index: 旧种子序号，1 表示最老材料。
    :returns: 最老轮使用 dropped marker，其它旧轮使用填充 marker。
    :raises ValueError: index 非正时抛出。
    """

    if index < 1:
        raise ValueError("fallback old marker index must be positive")
    if index == 1:
        return _SMOKE_FALLBACK_OLD_MARKER
    return f"DAYU_SMOKE_FALLBACK_OLD_FILLER_{index}_V1"


def _long_required_tool_fact_key(template: LongRoundTemplate) -> str | None:
    """返回 long suite 本轮必须命中的工具 fact key。

    long suite 只有 L01 负责建立美的长会话主体事实；后续 tool-enabled 轮次
    允许模型调用工具以刷新语境，但不把是否再次调用工具作为 conversation
    memory 的硬失败条件。

    :param template: long suite 轮次模板。
    :returns: 必须命中的 fact key；无硬要求时返回 ``None``。
    :raises Exception: 不主动抛出异常。
    """

    if template.label == _LONG_LABEL_01:
        return _FACT_KEY_MIDEA_LONG_SESSION
    return None


def _select_long_templates(round_count: int) -> tuple[LongRoundTemplate, ...]:
    """按 ``L01..L(N-1)+L25`` 选择 long suite 模板。

    :param round_count: long suite 轮数，范围为 20 到 25。
    :returns: 选中的 long suite 模板。
    :raises ValueError: ``round_count`` 超出 20 到 25 时抛出。
    """

    if round_count < _MIN_LONG_ROUNDS or round_count > _MAX_LONG_ROUNDS:
        raise ValueError("long round count must be in range 20..25")
    if round_count == _MAX_LONG_ROUNDS:
        return _LONG_ROUND_TEMPLATES
    prefix_count = round_count - 1
    return (*_LONG_ROUND_TEMPLATES[:prefix_count], _LONG_ROUND_TEMPLATES[-1])


def _build_byd_long_input() -> str:
    """构造确定性 C2 单轮长输入。

    :returns: 长度在 8,000 到 15,000 字符之间且三个 anchor 各出现一次的文本。
    :raises AssertionError: 生成结果不满足长度或 anchor 约束时抛出。
    """

    head = f"{_BYD_LONG_INPUT_HEAD_ANCHOR}：出口车型结构是本段原文固定 anchor，" "后续回答只能依据该原文。"
    middle = (
        f"{_BYD_LONG_INPUT_MIDDLE_ANCHOR}：动力电池价格压力是第二因素固定 anchor，" "用于验证长输入 minimum-preserve。"
    )
    tail = f"{_BYD_LONG_INPUT_TAIL_ANCHOR}：规模效应是第三因素固定 anchor，" "用于验证结尾信息可被引用。"
    paragraphs: list[str] = [head]
    while _joined_length(paragraphs) < (_BYD_LONG_INPUT_TARGET_CHARS // 2):
        paragraphs.extend(_BYD_LONG_INPUT_TEMPLATE_PARAGRAPHS)
    paragraphs.append(middle)
    while _joined_length(paragraphs) < (_BYD_LONG_INPUT_TARGET_CHARS - len(tail) - 1):
        paragraphs.extend(_BYD_LONG_INPUT_TEMPLATE_PARAGRAPHS)
    paragraphs.append(tail)
    text = "\n".join(paragraphs)
    if len(text) < _BYD_LONG_INPUT_TARGET_CHARS:
        text = text + (_BYD_LONG_INPUT_FILLER * (_BYD_LONG_INPUT_TARGET_CHARS - len(text)))
    if len(text) > _BYD_LONG_INPUT_MAX_CHARS:
        raise AssertionError("BYD long input exceeded maximum length")
    _assert_byd_long_input(text)
    return text


def _joined_length(parts: Sequence[str]) -> int:
    """计算按换行拼接后的文本长度。

    :param parts: 文本片段。
    :returns: 拼接后的字符长度。
    :raises Exception: 不主动抛出异常。
    """

    if not parts:
        return 0
    return sum(len(part) for part in parts) + len(parts) - 1


def _assert_byd_long_input(text: str) -> None:
    """校验 C2 长输入的确定性约束。

    :param text: 已生成的长输入。
    :returns: ``None``。
    :raises AssertionError: 长度、anchor 次数或中部位置不满足约束时抛出。
    """

    if len(text) < _BYD_LONG_INPUT_MIN_CHARS or len(text) > _BYD_LONG_INPUT_MAX_CHARS:
        raise AssertionError("BYD long input length must be in range 8000..15000")
    for anchor in (
        _BYD_LONG_INPUT_HEAD_ANCHOR,
        _BYD_LONG_INPUT_MIDDLE_ANCHOR,
        _BYD_LONG_INPUT_TAIL_ANCHOR,
    ):
        if text.count(anchor) != 1:
            raise AssertionError(f"BYD long input anchor count mismatch: {anchor}")
    middle_index = text.index(_BYD_LONG_INPUT_MIDDLE_ANCHOR)
    lower_bound = len(text) // 3
    upper_bound = (len(text) * 2) // 3
    if middle_index < lower_bound or middle_index > upper_bound:
        raise AssertionError("BYD factor2 anchor must be in the middle third")


def _find_fact_record(
    arguments: Mapping[str, JsonValue],
) -> MockFactRecord | None:
    """按固定参数查找 mock fact。

    :param arguments: 工具调用参数。
    :returns: 命中的 fact；未知事实返回 ``None``。
    :raises Exception: 不主动抛出异常。
    """

    company = _argument_str(arguments, _FIELD_COMPANY)
    ticker = _argument_str(arguments, _FIELD_TICKER)
    period = _argument_str(arguments, _FIELD_PERIOD)
    topic = _argument_str(arguments, _FIELD_TOPIC)
    metric = _argument_str(arguments, _FIELD_METRIC)
    for record in _MOCK_FACTS:
        if (
            record.company == company
            and record.ticker == ticker
            and record.period == period
            and record.topic == topic
            and metric in record.metrics
        ):
            return record
    return None


def _argument_str(arguments: Mapping[str, JsonValue], key: str) -> str:
    """读取字符串工具参数。

    :param arguments: 工具调用参数。
    :param key: 参数名。
    :returns: 字符串值；类型不匹配时返回空字符串。
    :raises Exception: 不主动抛出异常。
    """

    value = arguments.get(key)
    if isinstance(value, str):
        return value
    return ""


def _argument_bool(
    arguments: Mapping[str, JsonValue],
    key: str,
    *,
    default: bool,
) -> bool:
    """读取布尔工具参数。

    :param arguments: 工具调用参数。
    :param key: 参数名。
    :param default: 参数不存在或类型不匹配时使用的默认值。
    :returns: 布尔值。
    :raises Exception: 不主动抛出异常。
    """

    value = arguments.get(key)
    if isinstance(value, bool):
        return value
    return default


def _fact_payload(
    record: MockFactRecord,
    *,
    pressure_blob: str,
) -> Mapping[str, JsonValue]:
    """构造稳定 mock fact payload。

    :param record: 命中的 mock fact。
    :param pressure_blob: 可选压力文本。
    :returns: mock tool payload。
    :raises Exception: 不主动抛出异常。
    """

    payload: dict[str, JsonValue] = {
        "known": True,
        "fact_key": record.key,
        "company": record.company,
        "ticker": record.ticker,
        "period": record.period,
        "topic": record.topic,
        "marker": record.marker,
        "pressure_blob": pressure_blob,
    }
    for key, value in record.values:
        payload[key] = value
    return payload


def _mock_pressure_blob(include_pressure: bool, pressure_mode: PressureMode) -> str:
    """构造 S1a mock tool 压力文本。

    :param include_pressure: 工具参数是否要求压力。
    :param pressure_mode: 压力模式。
    :returns: 压力文本；关闭或未要求压力时返回空字符串。
    :raises Exception: 不主动抛出异常。
    """

    if not include_pressure or pressure_mode is PressureMode.OFF:
        return ""
    return _MOCK_PRESSURE_UNIT * _MOCK_PRESSURE_REPEAT


def _user_pressure_placeholder(pressure_mode: PressureMode) -> str:
    """构造 S1a 用户 prompt 压力占位文本。

    :param pressure_mode: 压力模式。
    :returns: 压力占位文本；关闭时为空字符串。
    :raises Exception: 不主动抛出异常。
    """

    if pressure_mode is PressureMode.OFF:
        return ""
    return _MOCK_PRESSURE_UNIT


async def run_smoke(args: SmokeArgs, env: Mapping[str, str]) -> int:
    """运行 Host public 财报对话记忆场景 smoke。

    :param args: smoke 参数。
    :param env: 环境变量映射。
    :returns: 进程退出码。
    :raises Exception: Host public path、provider 调用或硬断言失败时向上抛出。
    """

    if args.suite in (
        SuiteMode.MEMORY_REACTIVE_COMPACT,
        SuiteMode.MEMORY_COMPACT_FALLBACK,
    ):
        return await _run_deterministic_compact_smoke(args, env)

    assembly = _prepare_runtime_assembly(args, env=env)
    assembly.smoke_tool.set_pressure_mode(args.pressure_mode)
    assembly.smoke_tool.set_debug_output(args.debug_smoke_output)
    _assert_memory_compact_pressure_bounds(assembly.options, args.pressure_mode, args.suite)
    specs = _runtime_round_specs(args, assembly.options)
    _print_assembly_diagnostics(assembly.diagnostics, assembly.options)
    smoke_run_id = _new_smoke_run_id()

    if args.pressure_mode is PressureMode.OFF:
        print(_STDOUT_PRESSURE_DISABLED)
    _print_compact_pressure_plan(assembly.options, args.pressure_mode, suite=args.suite)
    print("SMOKE START Host public conversation memory scenario smoke")
    print(f"SMOKE WORKSPACE_ROOT {args.workspace_root}")
    print(f"SMOKE RUN_ID {smoke_run_id}")
    print(f"SMOKE SCENE_ID {args.scene_id}")
    print(f"SMOKE SUITE {args.suite.value} rounds={len(specs)}")
    print("SMOKE CONTRACT open_host -> ensure_session -> submit_followup -> watch -> get_session")
    print(f"SMOKE LOG_LEVEL {args.log_level.name}")

    async with open_host(assembly.options) as host:
        session = await host.ensure_session(_ensure_request(args, smoke_run_id))
        session_id = session.session_id
        assembly.smoke_tool.track_session(session.session_id)
        watcher = host.watch_session_events(session.session_id)
        print(f"SMOKE SESSION session_id={session.session_id}")
        _assert_session_open(session, label="ensure-session")
        _print_session_observation(session, label="ensure-session")

        for index, spec in enumerate(specs, start=1):
            tool_snapshot = assembly.smoke_tool.snapshot()
            result = await _run_round(
                host=host,
                watcher=watcher,
                session_id=session.session_id,
                spec=spec,
                client_request_id=_round_client_request_id(smoke_run_id, index),
                scene_inputs=assembly.scene_inputs,
            )
            _print_round(result)
            _assert_round_result(
                result,
                assembly.smoke_tool,
                spec,
                before_tools=tool_snapshot,
                debug_smoke_output=args.debug_smoke_output,
            )
            snapshot = await host.get_session(session.session_id)
            _assert_session_open(snapshot, label=spec.label)
            _print_session_observation(snapshot, label=spec.label)
            if spec.print_calls_by_key:
                print(calls_by_key_summary(assembly.smoke_tool.calls_by_key), flush=True)

        final_session = await host.get_session(session.session_id)
        _assert_session_open(final_session, label="final")
        print(f"SMOKE SESSION_STATUS {final_session.status.value}")

    print(calls_by_key_summary(assembly.smoke_tool.calls_by_key), flush=True)
    _print_compact_summary(assembly.options)
    compact_audit = _compact_audit_report(assembly.options, session_id=session_id)
    _print_compact_audit_summary(compact_audit.summary)
    _print_compact_audit_report(compact_audit, debug_smoke_output=args.debug_smoke_output)
    _assert_compact_acceptance(
        suite=args.suite,
        audit=compact_audit.summary,
        options=assembly.options,
    )
    print("SMOKE PASS public Host conversation memory scenario smoke", flush=True)
    if args.keep_workspace:
        print("SMOKE WORKSPACE_KEPT true", flush=True)
    else:
        print("SMOKE WORKSPACE_KEPT true  # smoke never deletes Host/runtime artifacts", flush=True)
    return 0


async def _run_deterministic_compact_smoke(args: SmokeArgs, env: Mapping[str, str]) -> int:
    """运行 reactive / fallback deterministic compact smoke。

    :param args: smoke 参数。
    :param env: 环境变量映射。
    :returns: 进程退出码。
    :raises Exception: public Host 流程、compact 验收或确定性断言失败时向上抛出。
    """

    assembly = _prepare_runtime_assembly(args, env=env)
    worker_factory = _DeterministicCompactWorkerFactory(
        reactive_overflow_accept_index=(
            _SMOKE_REACTIVE_TARGET_ACCEPT_INDEX
            if args.suite is SuiteMode.MEMORY_REACTIVE_COMPACT
            else None
        )
    )
    deterministic_options = replace(assembly.options, worker_factory=worker_factory)
    assembly = replace(assembly, options=deterministic_options)
    assembly.smoke_tool.set_pressure_mode(args.pressure_mode)
    assembly.smoke_tool.set_debug_output(args.debug_smoke_output)
    specs = _runtime_round_specs(args, assembly.options)
    _print_assembly_diagnostics(assembly.diagnostics, assembly.options)
    smoke_run_id = _new_smoke_run_id()
    pressure_observation = _fallback_pressure_observation(args, assembly.options)
    compactor_runner: SmokeCompactorRunner
    if args.suite is SuiteMode.MEMORY_REACTIVE_COMPACT:
        compactor_runner = _AcceptingSmokeCompactorRunner()
    else:
        compactor_runner = _RejectingSmokeCompactorRunner()

    if args.pressure_mode is PressureMode.OFF:
        print(_STDOUT_PRESSURE_DISABLED)
    _print_compact_pressure_plan(assembly.options, args.pressure_mode, suite=args.suite)
    print("SMOKE START Host public conversation memory scenario smoke")
    print(f"SMOKE WORKSPACE_ROOT {args.workspace_root}")
    print(f"SMOKE RUN_ID {smoke_run_id}")
    print(f"SMOKE SCENE_ID {args.scene_id}")
    print(f"SMOKE SUITE {args.suite.value} rounds={len(specs)}")
    print("SMOKE CONTRACT open_host -> ensure_session -> submit_followup -> watch -> get_session")
    print(f"SMOKE LOG_LEVEL {args.log_level.name}")

    results: list[RoundResult] = []
    with _patched_compactor_runner(compactor_runner):
        async with open_host(assembly.options) as host:
            session = await host.ensure_session(_ensure_request(args, smoke_run_id))
            session_id = session.session_id
            assembly.smoke_tool.track_session(session.session_id)
            watcher = host.watch_session_events(session.session_id)
            print(f"SMOKE SESSION session_id={session.session_id}")
            _assert_session_open(session, label="ensure-session")
            _print_session_observation(session, label="ensure-session")

            for index, spec in enumerate(specs, start=1):
                tool_snapshot = assembly.smoke_tool.snapshot()
                result = await _run_round(
                    host=host,
                    watcher=watcher,
                    session_id=session.session_id,
                    spec=spec,
                    client_request_id=_round_client_request_id(smoke_run_id, index),
                    scene_inputs=assembly.scene_inputs,
                )
                results.append(result)
                _print_round(result)
                _assert_round_result(
                    result,
                    assembly.smoke_tool,
                    spec,
                    before_tools=tool_snapshot,
                    debug_smoke_output=args.debug_smoke_output,
                )
                snapshot = await host.get_session(session.session_id)
                _assert_session_open(snapshot, label=spec.label)
                _print_session_observation(snapshot, label=spec.label)

            final_session = await host.get_session(session.session_id)
            _assert_session_open(final_session, label="final")
            print(f"SMOKE SESSION_STATUS {final_session.status.value}")

    if not results:
        raise RuntimeError("deterministic compact smoke produced no runs")
    print(calls_by_key_summary(assembly.smoke_tool.calls_by_key), flush=True)
    _print_deterministic_dispatches(worker_factory)
    _print_compact_summary(assembly.options)
    compact_audit = _compact_audit_report(assembly.options, session_id=session_id)
    _print_compact_audit_summary(compact_audit.summary)
    _print_compact_audit_report(compact_audit, debug_smoke_output=args.debug_smoke_output)
    observation = DeterministicSmokeObservation(
        dispatches=_deterministic_dispatch_captures(worker_factory),
        target_run_id=results[-1].run_id,
        current_input_marker=_deterministic_current_marker(args.suite),
        protected_recent_marker=_deterministic_protected_recent_marker(args.suite),
        dropped_old_marker=_deterministic_dropped_old_marker(args.suite),
        pressure_tokens=pressure_observation.pressure_tokens,
        soft_threshold_tokens=pressure_observation.soft_threshold_tokens,
        hard_threshold_tokens=pressure_observation.hard_threshold_tokens,
    )
    if args.suite is SuiteMode.MEMORY_REACTIVE_COMPACT:
        _assert_reactive_compact_acceptance(compact_audit, observation)
    else:
        _assert_fallback_dispatch_acceptance(compact_audit, observation)
    print("SMOKE PASS public Host conversation memory scenario smoke", flush=True)
    if args.keep_workspace:
        print("SMOKE WORKSPACE_KEPT true", flush=True)
    else:
        print("SMOKE WORKSPACE_KEPT true  # smoke never deletes Host/runtime artifacts", flush=True)
    return 0


def _prepare_runtime_assembly(args: SmokeArgs, *, env: Mapping[str, str]) -> RuntimeAssemblyResult:
    """执行 Host 调用前的 runtime/config/tools/scene typed assembly。

    :param args: smoke 参数。
    :param env: 环境变量映射。
    :returns: 完整 runtime assembly 结果。
    :raises ValueError: 配置、工具发现、scene 或 override 无法映射时抛出。
    """

    locations = resolve_runtime_locations(
        workspace_root=args.workspace_root,
        package_config_root=_PACKAGE_CONFIG_ROOT,
    )
    config = ConfigLoader(package_config_dir=_PACKAGE_CONFIG_ROOT).load(
        workspace_config_dir=locations.config_overlay_dir
    )
    discovered_tools = _discover_smoke_service_tools(
        config,
        workspace_root=args.workspace_root,
    )
    scene_inputs = prepare_scene(
        ScenePrepareRequest(
            scene_id=args.scene_id,
            scene_manifest_root=locations.scene_manifest_root,
            prompt_asset_root=locations.prompt_asset_root,
            context_slot_values={CURRENT_TIME_SLOT: current_time()},
            available_tools=SceneToolCatalog.from_tool_bundle(discovered_tools.tool_bundle),
        )
    )
    assembly = compose_open_host_options(
        ServiceOpenHostAssemblyRequest(
            workspace_root=args.workspace_root,
            config=config,
            locations=locations,
            scene_inputs=scene_inputs,
            discovered_tools=discovered_tools,
            overrides=ServiceAssemblyOverrides(
                host_runtime_id=args.host_runtime_id,
                execution_profile_id=args.execution_profile_id,
                model_id=args.model_id,
                runner_option_hint_id=args.runner_option_hint_id,
            ),
            env=env,
        )
    )
    smoke_tool = _find_mock_finance_memory_tool(assembly.effective_tool_bundle)
    if smoke_tool is None:
        raise ValueError("effective ToolBundle does not contain MockFinanceMemoryTool")
    options = _smoke_options_for_suite(assembly.options, args.suite)
    return RuntimeAssemblyResult(
        options=options,
        scene_inputs=scene_inputs,
        diagnostics=assembly.diagnostics,
        effective_tool_bundle=assembly.effective_tool_bundle,
        smoke_tool=smoke_tool,
    )


def _smoke_options_for_suite(options: OpenHostOptions, suite: SuiteMode) -> OpenHostOptions:
    """按 smoke suite 返回本地 Host options。

    :param options: Service-like 装配得到的原始 Host options。
    :param suite: 当前 smoke suite。
    :returns: suite-local Host options。
    :raises ValueError: reactive suite 的 recent floor 超出当前轮次布局能力时抛出。
    """

    if suite is not SuiteMode.MEMORY_REACTIVE_COMPACT:
        return options
    return replace(
        options,
        memory_projection_policy=_reactive_compact_smoke_memory_policy(
            options.memory_projection_policy
        ),
    )


def _reactive_compact_smoke_memory_policy(
    policy: MemoryProjectionPolicy,
) -> MemoryProjectionPolicy:
    """返回 reactive compact smoke 使用的本地 memory policy。

    该 suite 需要让 r1 old seed 真实进入 Host 历史，同时在 recovery dispatch
    中被排除。收紧 selected recent item cap 可让 r2-r5 作为 protected recent
    保留，并让 r1 只通过 compacted semantic view 表示。

    :param policy: Service-like 装配得到的 memory policy。
    :returns: reactive suite 的本地 memory policy。
    :raises ValueError: selected recent floor 无法由当前三轮 gap 加一轮 recent
        布局承载时抛出。
    """

    max_supported_turn_floor = _SMOKE_REACTIVE_HISTORY_GAP_ROUNDS + 1
    if policy.selected_recent_window_turn_floor > max_supported_turn_floor:
        raise ValueError(
            "memory-reactive-compact selected recent floor exceeds deterministic "
            "history gap layout"
        )
    selected_recent_item_cap = max(
        1,
        policy.selected_recent_window_turn_floor
        * _SMOKE_REACTIVE_SELECTED_RECENT_ITEMS_PER_TURN,
    )
    fallback_selected_recent_item_cap = min(
        policy.fallback_selected_recent_window_item_cap,
        selected_recent_item_cap,
    )
    return replace(
        policy,
        selected_recent_window_item_cap=selected_recent_item_cap,
        fallback_selected_recent_window_item_cap=fallback_selected_recent_item_cap,
    )


def _discover_smoke_service_tools(
    config: RuntimeConfig,
    *,
    workspace_root: pathlib.Path,
) -> ServiceDiscoveredTools:
    """发现 Service 工具并确保 smoke mock 财报记忆工具可用。

    :param config: ``ConfigLoader`` 输出的 runtime typed config。
    :param workspace_root: 当前 smoke 的 workspace root。
    :returns: 包含 smoke mock 工具的 Service 工具发现结果。
    :raises ValueError: 已发现同名非 smoke 工具时抛出。
    :raises Exception: 工具发现 provider 失败时向上抛出。
    """

    effective_provider_configs = assemble_effective_tool_provider_configs(
        tuple(config.tool_discovery.providers.values()),
        workspace_root=workspace_root,
    )
    discovered = discover_service_tools(effective_provider_configs)
    existing_smoke_tool = _find_mock_finance_memory_tool(discovered.tool_bundle)
    if existing_smoke_tool is not None:
        return discovered
    if _has_tool_name(discovered.tool_bundle, _TOOL_NAME):
        raise ValueError(f"discovered tool bundle already contains non-smoke tool: {_TOOL_NAME}")

    smoke_result = _discover_builtin_smoke_tools()
    return ServiceDiscoveredTools(
        tool_bundle=ToolBundle(
            definitions=(
                *discovered.tool_bundle.definitions,
                *smoke_result.tool_bundle.definitions,
            )
        ),
        source_refs=(
            *discovered.source_refs,
            *smoke_result.source_refs,
        ),
        provider_reports=(
            *discovered.provider_reports,
            *(
                _format_provider_report(
                    report.provider_id,
                    report.spec_id,
                    report.version_ref,
                    report.tool_names,
                )
                for report in smoke_result.provider_reports
            ),
        ),
        effective_provider_configs=discovered.effective_provider_configs,
        fins_awaiting_runtime=discovered.fins_awaiting_runtime,
    )


def _discover_builtin_smoke_tools() -> ToolsDiscoveryResult:
    """通过 ToolsDiscovery 调用内置 smoke provider。

    :returns: 内置 smoke provider 的工具发现结果。
    :raises Exception: provider 解析或工具定义校验失败时向上抛出。
    """

    return ToolsDiscovery().discover_from_bindings(
        (
            ToolsDiscoveryProviderBinding(
                spec=ToolsDiscoveryProviderSpec(
                    spec_id=_PROVIDER_SPEC_ID,
                    location=PythonImportPathProvider(import_path=_PROVIDER_IMPORT_DISPLAY_PATH),
                ),
                provider=discover_smoke_tools,
            ),
        )
    )


def _has_tool_name(tool_bundle: ToolBundle, tool_name: str) -> bool:
    """检查工具 bundle 是否包含指定工具名。

    :param tool_bundle: 待检查的工具 bundle。
    :param tool_name: 工具名。
    :returns: 存在同名工具时返回 ``True``。
    :raises Exception: 不主动抛出异常。
    """

    return any(definition.name == tool_name for definition in tool_bundle.definitions)


def _find_mock_finance_memory_tool(
    tool_bundle: ToolBundle,
) -> MockFinanceMemoryTool | None:
    """从 effective ToolBundle 中找出 mock 财报记忆工具实例。

    :param tool_bundle: 已发现或已生效的工具 bundle。
    :returns: mock 财报记忆工具实例；未发现时返回 ``None``。
    :raises Exception: 不主动抛出异常。
    """

    for definition in tool_bundle.definitions:
        if isinstance(definition.callable, MockFinanceMemoryTool):
            return definition.callable
    return None


def _smoke_tool_definition(smoke_tool: MockFinanceMemoryTool) -> ToolDefinition:
    """构造 mock 财报记忆工具定义。

    :param smoke_tool: 返回固定财报记忆事实的工具实例。
    :returns: ToolDefinition。
    :raises ValueError: schema 字段非法时由底层抛出。
    """

    properties: dict[str, JsonValue] = {
        "company": {"type": "string", "description": "Company name."},
        "ticker": {"type": "string", "description": "Security ticker."},
        "period": {"type": "string", "description": "Reporting period."},
        "topic": {"type": "string", "description": "Finance topic."},
        "metric": {"type": "string", "description": "Metric name."},
        "include_pressure": {
            "type": "boolean",
            "description": "Whether to include deterministic pressure text.",
        },
    }
    return ToolDefinition(
        name=_TOOL_NAME,
        schema=ToolSchema(
            type="function",
            function=ToolFunctionSchema(
                name=_TOOL_NAME,
                description=(
                    "Return deterministic mock finance memory facts for Host "
                    "public conversation memory scenario smoke."
                ),
                parameters=ToolParametersSchema(
                    type="object",
                    properties=properties,
                    required=(
                        "company",
                        "ticker",
                        "period",
                        "topic",
                        "metric",
                        "include_pressure",
                    ),
                    additional_properties=False,
                ),
            ),
        ),
        callable=smoke_tool,
        execution=AsyncDirectToolExecutionCapability(),
        truncate=None,
        display=None,
        tags=(_TOOL_TAG,),
    )


def _runtime_round_specs(
    args: SmokeArgs,
    options: OpenHostOptions,
) -> tuple[RoundSpec, ...]:
    """按 runtime options 构造场景轮次规格。

    :param args: smoke 参数。
    :param options: 本次 Host opener options。
    :returns: 需要执行的场景轮次规格。
    :raises RuntimeError: compact pressure 需要 context budget policy 但缺失时抛出。
    """

    if args.suite is SuiteMode.MEMORY_COMPACT_FALLBACK and args.pressure_mode is PressureMode.AUTO:
        user_pressure_text = _fallback_compact_pressure_padding(options)
    else:
        user_pressure_text = _runtime_user_pressure_text(args.pressure_mode, options)
    return _round_specs_for_suite(
        suite=args.suite,
        long_rounds=args.long_rounds,
        user_pressure_text=user_pressure_text,
    )


def _runtime_user_pressure_text(
    pressure_mode: PressureMode,
    options: OpenHostOptions,
) -> str:
    """按 pressure mode 生成用户侧压力文本。

    :param pressure_mode: 压力注入模式。
    :param options: 本次 Host opener options。
    :returns: 用户 prompt 中使用的压力文本。
    :raises RuntimeError: auto pressure 需要 context budget policy 但缺失时抛出。
    """

    if pressure_mode is PressureMode.OFF:
        return ""
    return _compact_pressure_padding(options)


def _fallback_compact_pressure_padding(options: OpenHostOptions) -> str:
    """构造 fallback suite 专用 proactive compact 压力文本。

    fallback deterministic suite 只有一个目标压力轮，必须稳定跨过 soft
    threshold；旧 ``memory-compact`` 长会话则使用更保守的全局 padding，避免
    真实模型长输出把 pre-dispatch 估算推过 hard threshold。

    :param options: Host opener options。
    :returns: fallback 目标轮 pressure padding。
    :raises RuntimeError: smoke 未启用 context budget policy 时抛出。
    """

    return _compact_pressure_padding_with_reserve(
        options,
        reserve_tokens=_COMPACT_FALLBACK_PRESSURE_RESERVE_TOKENS,
    )


def _compact_pressure_reserve_tokens(suite: SuiteMode) -> int:
    """返回 suite 专用 compact pressure reserve token 数。

    :param suite: 当前 smoke suite。
    :returns: pressure 估算需要追加的 reserve token 数。
    :raises Exception: 不主动抛出异常。
    """

    if suite is SuiteMode.MEMORY_COMPACT_FALLBACK:
        return _COMPACT_FALLBACK_PRESSURE_RESERVE_TOKENS
    return _COMPACT_PRESSURE_RESERVE_TOKENS


def _fallback_pressure_observation(
    args: SmokeArgs,
    options: OpenHostOptions,
) -> FallbackPressureObservation:
    """计算 fallback suite 的压力阈值观测。

    :param args: smoke 参数。
    :param options: Host opener options。
    :returns: fallback 压力观测；非 fallback suite 返回全 ``None``。
    :raises RuntimeError: fallback suite 缺少 context budget policy 时抛出。
    """

    if args.suite is not SuiteMode.MEMORY_COMPACT_FALLBACK:
        return FallbackPressureObservation(
            pressure_tokens=None,
            soft_threshold_tokens=None,
            hard_threshold_tokens=None,
        )
    policy = options.context_budget_policy
    if policy is None:
        raise RuntimeError("memory-compact-fallback requires context budget policy")
    prompt_tokens = _estimate_chars_as_tokens(
        len(_fallback_compact_pressure_padding(options))
    )
    pressure_tokens = (
        prompt_tokens
        + _tool_pressure_estimated_tokens()
        + _compact_pressure_reserve_tokens(args.suite)
    )
    return FallbackPressureObservation(
        pressure_tokens=pressure_tokens,
        soft_threshold_tokens=_threshold_tokens(
            policy.context_window_size,
            policy.soft_threshold_context_ratio,
        ),
        hard_threshold_tokens=_threshold_tokens(
            policy.context_window_size,
            policy.hard_threshold_context_ratio,
        ),
    )


def _deterministic_dispatch_captures(
    worker_factory: _DeterministicCompactWorkerFactory,
) -> tuple[DeterministicDispatchCapture, ...]:
    """把 worker 捕获的 public request 转为 bounded 断言摘要。

    :param worker_factory: deterministic worker factory。
    :returns: dispatch capture 元组。
    :raises RuntimeError: request 与 snapshot 数量不一致时抛出。
    """

    if len(worker_factory.requests) != len(worker_factory.snapshots):
        raise RuntimeError("deterministic worker request/snapshot capture length mismatch")
    captures: list[DeterministicDispatchCapture] = []
    for request, snapshot in zip(worker_factory.requests, worker_factory.snapshots, strict=True):
        captures.append(
            DeterministicDispatchCapture(
                run_id=request.run_id,
                attempt_id=snapshot.attempt_id,
                execution_id=snapshot.execution_id,
                joined_messages=_joined_message_content(request.messages),
                system_message_count=_system_message_count(request.messages),
                system_message_at_start=_system_message_at_start(request.messages),
            )
        )
    return tuple(captures)


def _print_deterministic_dispatches(worker_factory: _DeterministicCompactWorkerFactory) -> None:
    """打印 bounded deterministic dispatch 摘要。

    :param worker_factory: deterministic worker factory。
    :returns: ``None``。
    :raises RuntimeError: request 与 snapshot 数量不一致时抛出。
    """

    for index, capture in enumerate(_deterministic_dispatch_captures(worker_factory), start=1):
        print(
            f"{_STDOUT_PREFIX_DETERMINISTIC_DISPATCH} "
            f"index={index} run_id={capture.run_id} "
            f"attempt_id={capture.attempt_id} execution_id={capture.execution_id} "
            f"system_messages={capture.system_message_count}",
            flush=True,
        )


def _assert_reactive_compact_acceptance(
    report: CompactAuditReport,
    observation: DeterministicSmokeObservation,
) -> None:
    """断言 reactive compact deterministic suite 验收信号。

    :param report: compact EventLog 审计报告。
    :param observation: deterministic dispatch 观测。
    :returns: ``None``。
    :raises RuntimeError: reactive compact 或 recovery dispatch 信号缺失时抛出。
    """

    summary = report.summary
    if (
        summary.requested_proactive > 0
        or summary.compacted_proactive > 0
        or summary.failed_proactive > 0
    ):
        raise RuntimeError(
            "memory-reactive-compact observed unexpected proactive compact activity: "
            f"requested_proactive={summary.requested_proactive} "
            f"compacted_proactive={summary.compacted_proactive} "
            f"failed_proactive={summary.failed_proactive}"
        )
    if summary.requested_reactive < 1:
        raise RuntimeError("memory-reactive-compact did not observe reactive CONTEXT_COMPACTION_REQUESTED")
    if summary.compacted_reactive < 1:
        raise RuntimeError("memory-reactive-compact did not observe reactive CONTEXT_COMPACTED")
    if summary.failed_reactive > 0:
        raise RuntimeError("memory-reactive-compact observed reactive CONTEXT_COMPACTION_FAILED")
    target_dispatches = _dispatches_for_run(observation, observation.target_run_id)
    if len(target_dispatches) != 2:
        raise RuntimeError(
            "memory-reactive-compact expected original and recovery dispatch for target run, "
            f"got {len(target_dispatches)}"
        )
    original = target_dispatches[0]
    recovery = target_dispatches[1]
    if original.attempt_id == recovery.attempt_id:
        raise RuntimeError("memory-reactive-compact recovery attempt_id did not change")
    if original.execution_id == recovery.execution_id:
        raise RuntimeError("memory-reactive-compact recovery execution_id did not change")
    _assert_one_system_message_contract(observation.dispatches, suite=SuiteMode.MEMORY_REACTIVE_COMPACT)
    _assert_marker_present(
        recovery.joined_messages,
        marker=observation.current_input_marker,
        label="reactive recovery current input",
    )
    _assert_marker_present(
        recovery.joined_messages,
        marker=observation.protected_recent_marker,
        label="reactive recovery protected recent",
    )
    if observation.dropped_old_marker is None:
        raise RuntimeError("memory-reactive-compact missing dropped old marker expectation")
    _assert_marker_absent(
        recovery.joined_messages,
        marker=observation.dropped_old_marker,
        label="reactive recovery dropped old",
    )
    print(
        f"{_STDOUT_PREFIX_COMPACT_ACCEPTANCE} status=pass "
        f"requested_reactive={summary.requested_reactive} "
        f"compacted_reactive={summary.compacted_reactive} "
        f"failed_reactive={summary.failed_reactive} "
        f"recovery_attempt_id={recovery.attempt_id}",
        flush=True,
    )


def _assert_fallback_dispatch_acceptance(
    report: CompactAuditReport,
    observation: DeterministicSmokeObservation,
) -> None:
    """断言 compact failure fallback deterministic suite 验收信号。

    :param report: compact EventLog 审计报告。
    :param observation: deterministic dispatch 观测。
    :returns: ``None``。
    :raises RuntimeError: fallback dispatch 或 bounded fallback window 信号缺失时抛出。
    """

    _assert_fallback_pressure_bounds(observation)
    summary = report.summary
    if summary.requested_proactive < 1:
        raise RuntimeError("memory-compact-fallback did not observe proactive CONTEXT_COMPACTION_REQUESTED")
    failed_operation = _fallback_failed_operation(report)
    if failed_operation.compacted > 0:
        raise RuntimeError("memory-compact-fallback observed CONTEXT_COMPACTED for failed fallback operation")
    if not failed_operation.failed_events:
        raise RuntimeError("memory-compact-fallback expected at least one failed compact event")
    failed_event = failed_operation.failed_events[-1]
    if failed_event.fallback_action != "dispatch":
        raise RuntimeError("memory-compact-fallback did not observe fallback_action=dispatch")
    if not failed_event.selected_block_ids:
        raise RuntimeError("memory-compact-fallback missing fallback selected_block_ids")
    if observation.dropped_old_marker is not None and not failed_event.dropped_block_ids:
        raise RuntimeError("memory-compact-fallback expected dropped_block_ids for old seed material")
    if failed_event.current_input_ref is None or failed_event.current_input_ref.strip() == "":
        raise RuntimeError("memory-compact-fallback missing current_input_ref")
    target_dispatches = _dispatches_for_run(observation, observation.target_run_id)
    if len(target_dispatches) != 1:
        raise RuntimeError(
            "memory-compact-fallback expected one final fallback dispatch for target run, "
            f"got {len(target_dispatches)}"
        )
    final_dispatch = target_dispatches[0]
    _assert_one_system_message_contract(observation.dispatches, suite=SuiteMode.MEMORY_COMPACT_FALLBACK)
    _assert_marker_present(
        final_dispatch.joined_messages,
        marker=observation.current_input_marker,
        label="fallback current input",
    )
    _assert_marker_present(
        final_dispatch.joined_messages,
        marker=observation.protected_recent_marker,
        label="fallback selected recent",
    )
    if observation.dropped_old_marker is not None:
        _assert_marker_absent(
            final_dispatch.joined_messages,
            marker=observation.dropped_old_marker,
            label="fallback dropped old",
        )
    for section in _COMPACT_FALLBACK_FORBIDDEN_SECTIONS:
        if section in final_dispatch.joined_messages:
            raise RuntimeError(f"memory-compact-fallback rendered fake semantic memory section: {section}")
    print(
        f"{_STDOUT_PREFIX_COMPACT_ACCEPTANCE} status=pass "
        f"requested_proactive={summary.requested_proactive} "
        f"failed_operation={failed_operation.operation_id} "
        f"fallback_action={failed_event.fallback_action} "
        f"selected_block_ids={len(failed_event.selected_block_ids)} "
        f"dropped_block_ids={len(failed_event.dropped_block_ids)}",
        flush=True,
    )


def _assert_fallback_pressure_bounds(observation: DeterministicSmokeObservation) -> None:
    """断言 fallback pressure 落在 soft 与 hard threshold 之间。

    :param observation: deterministic smoke 观测。
    :returns: ``None``。
    :raises RuntimeError: 压力或阈值缺失 / 越界时抛出。
    """

    if (
        observation.pressure_tokens is None
        or observation.soft_threshold_tokens is None
        or observation.hard_threshold_tokens is None
    ):
        raise RuntimeError("memory-compact-fallback missing pressure threshold observation")
    if observation.pressure_tokens < observation.soft_threshold_tokens:
        raise RuntimeError(
            "memory-compact-fallback pressure below soft threshold: "
            f"pressure={observation.pressure_tokens} soft={observation.soft_threshold_tokens}"
        )
    if observation.pressure_tokens >= observation.hard_threshold_tokens:
        raise RuntimeError(
            "memory-compact-fallback pressure reached hard threshold: "
            f"pressure={observation.pressure_tokens} hard={observation.hard_threshold_tokens}"
        )


def _assert_memory_compact_pressure_bounds(
    options: OpenHostOptions,
    pressure_mode: PressureMode,
    suite: SuiteMode,
) -> None:
    """启动期断言 real-provider memory-compact auto pressure 落在预算区间内。

    :param options: 本次 Host opener options。
    :param pressure_mode: 压力注入模式。
    :param suite: 当前 smoke suite。
    :returns: ``None``。
    :raises RuntimeError: context budget policy 缺失或估算压力未落入
        soft / hard threshold 区间时抛出。
    """

    if suite is not SuiteMode.MEMORY_COMPACT or pressure_mode is not PressureMode.AUTO:
        return
    policy = options.context_budget_policy
    if policy is None:
        raise RuntimeError("memory-compact auto pressure requires context budget policy")
    reserve_tokens = _compact_pressure_reserve_tokens(suite)
    prompt_tokens = _estimate_chars_as_tokens(len(_compact_pressure_padding(options)))
    tool_pressure_tokens = _tool_pressure_estimated_tokens()
    pressure_tokens = prompt_tokens + tool_pressure_tokens + reserve_tokens
    soft_threshold_tokens = _threshold_tokens(
        policy.context_window_size,
        policy.soft_threshold_context_ratio,
    )
    hard_threshold_tokens = _threshold_tokens(
        policy.context_window_size,
        policy.hard_threshold_context_ratio,
    )
    if pressure_tokens < soft_threshold_tokens:
        raise RuntimeError(
            "memory-compact auto pressure below soft threshold: "
            f"reserve={reserve_tokens} prompt_pressure={prompt_tokens} "
            f"tool_pressure={tool_pressure_tokens} pressure={pressure_tokens} "
            f"soft={soft_threshold_tokens} hard={hard_threshold_tokens}"
        )
    if pressure_tokens >= hard_threshold_tokens:
        raise RuntimeError(
            "memory-compact auto pressure reached hard threshold: "
            f"reserve={reserve_tokens} prompt_pressure={prompt_tokens} "
            f"tool_pressure={tool_pressure_tokens} pressure={pressure_tokens} "
            f"soft={soft_threshold_tokens} hard={hard_threshold_tokens}"
        )


def _fallback_failed_operation(report: CompactAuditReport) -> CompactOperationAudit:
    """返回唯一 fallback dispatch failed operation。

    :param report: compact EventLog 审计报告。
    :returns: fallback dispatch operation。
    :raises RuntimeError: 未找到或找到多个 fallback dispatch failed operation 时抛出。
    """

    operations = tuple(
        operation
        for operation in report.operations
        if any(event.fallback_action == "dispatch" for event in operation.failed_events)
    )
    if len(operations) != 1:
        raise RuntimeError(f"memory-compact-fallback expected exactly one dispatch fallback operation, got {len(operations)}")
    return operations[0]


def _dispatches_for_run(
    observation: DeterministicSmokeObservation,
    run_id: str,
) -> tuple[DeterministicDispatchCapture, ...]:
    """筛选指定 Run 的 dispatch captures。

    :param observation: deterministic smoke 观测。
    :param run_id: Host Run id。
    :returns: dispatch captures。
    :raises Exception: 不主动抛出异常。
    """

    return tuple(dispatch for dispatch in observation.dispatches if dispatch.run_id == run_id)


def _assert_one_system_message_contract(
    dispatches: tuple[DeterministicDispatchCapture, ...],
    *,
    suite: SuiteMode,
) -> None:
    """断言所有 ordinary dispatch 至多一个 system message 且位于首位。

    :param dispatches: dispatch captures。
    :param suite: suite 名称，用于错误诊断。
    :returns: ``None``。
    :raises RuntimeError: system message contract 被破坏时抛出。
    """

    for index, dispatch in enumerate(dispatches, start=1):
        if dispatch.system_message_count > 1:
            raise RuntimeError(f"{suite.value} dispatch {index} has multiple system messages")
        if not dispatch.system_message_at_start:
            raise RuntimeError(f"{suite.value} dispatch {index} system message is not first")


def _assert_marker_present(text: str, *, marker: str, label: str) -> None:
    """断言文本包含 marker。

    :param text: 待检查文本。
    :param marker: 稳定 marker。
    :param label: 诊断标签。
    :returns: ``None``。
    :raises RuntimeError: marker 缺失时抛出。
    """

    if marker not in text:
        raise RuntimeError(f"{label} missing marker {marker}")


def _assert_marker_absent(text: str, *, marker: str, label: str) -> None:
    """断言文本不包含 marker。

    :param text: 待检查文本。
    :param marker: 稳定 marker。
    :param label: 诊断标签。
    :returns: ``None``。
    :raises RuntimeError: marker 出现时抛出。
    """

    if marker in text:
        raise RuntimeError(f"{label} unexpectedly contains marker {marker}")


def _deterministic_current_marker(suite: SuiteMode) -> str:
    """返回 deterministic suite 的当前输入 marker。

    :param suite: suite 模式。
    :returns: 当前输入 marker。
    :raises ValueError: suite 不支持时抛出。
    """

    if suite is SuiteMode.MEMORY_REACTIVE_COMPACT:
        return _SMOKE_REACTIVE_CURRENT_MARKER
    if suite is SuiteMode.MEMORY_COMPACT_FALLBACK:
        return _SMOKE_FALLBACK_CURRENT_MARKER
    raise ValueError(f"unsupported deterministic suite: {suite.value}")


def _deterministic_protected_recent_marker(suite: SuiteMode) -> str:
    """返回 deterministic suite 的 protected recent marker。

    :param suite: suite 模式。
    :returns: protected recent marker。
    :raises ValueError: suite 不支持时抛出。
    """

    if suite is SuiteMode.MEMORY_REACTIVE_COMPACT:
        return _SMOKE_REACTIVE_RECENT_MARKER
    if suite is SuiteMode.MEMORY_COMPACT_FALLBACK:
        return _SMOKE_FALLBACK_RECENT_MARKER
    raise ValueError(f"unsupported deterministic suite: {suite.value}")


def _deterministic_dropped_old_marker(suite: SuiteMode) -> str | None:
    """返回 deterministic suite 的 dropped old marker。

    :param suite: suite 模式。
    :returns: dropped old marker；不适用时为 ``None``。
    :raises ValueError: suite 不支持时抛出。
    """

    if suite is SuiteMode.MEMORY_REACTIVE_COMPACT:
        return _SMOKE_REACTIVE_OLD_MARKER
    if suite is SuiteMode.MEMORY_COMPACT_FALLBACK:
        return _SMOKE_FALLBACK_OLD_MARKER
    raise ValueError(f"unsupported deterministic suite: {suite.value}")


def _joined_message_content(messages: Sequence[AgentMessage]) -> str:
    """合并 Agent messages 中的文本内容。

    :param messages: Agent messages。
    :returns: 换行拼接后的文本。
    :raises Exception: 不主动抛出异常。
    """

    parts: list[str] = []
    for message in messages:
        content = message.content
        if content is not None:
            parts.append(content)
    return "\n".join(parts)


def _system_message_count(messages: Sequence[AgentMessage]) -> int:
    """统计 system message 数量。

    :param messages: Agent messages。
    :returns: system message 数量。
    :raises Exception: 不主动抛出异常。
    """

    return sum(1 for message in messages if message.role is AgentMessageRole.SYSTEM)


def _system_message_at_start(messages: Sequence[AgentMessage]) -> bool:
    """判断唯一 system message 是否位于首位。

    :param messages: Agent messages。
    :returns: 无 system message 或 system message 位于首位时返回 ``True``。
    :raises Exception: 不主动抛出异常。
    """

    if _system_message_count(messages) == 0:
        return True
    return bool(messages) and messages[0].role is AgentMessageRole.SYSTEM


def _assert_at_most_one_system_message(messages: Sequence[AgentMessage], *, label: str) -> None:
    """断言 messages 至多一个 system message 且位于首位。

    :param messages: Agent messages。
    :param label: 诊断标签。
    :returns: ``None``。
    :raises AssertionError: system message contract 被破坏时抛出。
    """

    system_count = _system_message_count(messages)
    if system_count > 1:
        raise AssertionError(f"{label} expected at most one system message, got {system_count}")
    if system_count == 1 and not _system_message_at_start(messages):
        raise AssertionError(f"{label} expected system message at index 0")


def _ensure_request(args: SmokeArgs, smoke_run_id: str) -> EnsureSessionRequest:
    """构造 ensure session 请求。

    :param args: smoke 参数。
    :param smoke_run_id: 本次 smoke 批次 id。
    :returns: EnsureSessionRequest。
    :raises ValueError: 字段非法时由底层抛出。
    """

    slot_key = _DEFAULT_SLOT_KEY_PREFIX if args.reuse_session else f"{_DEFAULT_SLOT_KEY_PREFIX}-{smoke_run_id}"
    return EnsureSessionRequest(
        scope="workspace",
        slot_key=slot_key,
        metadata=(),
    )


def _host_context(request_id: str) -> HostCallContext:
    """构造 HostCallContext。

    :param request_id: request id。
    :returns: HostCallContext。
    :raises ValueError: 字段非法时由底层抛出。
    """

    return HostCallContext(
        actor=_DEFAULT_USER_ID,
        source=_SOURCE_NAME,
        request_id=request_id,
        authorization_claims=(AuthorizationClaim(name="role", value="manual-smoke"),),
        operation_context=OperationContext(
            operation_name=_OPERATION_NAME,
            operation_kind=_OPERATION_KIND,
            business_domain=_BUSINESS_DOMAIN,
            business_object_type=None,
            business_object_id=None,
            scenario=_SCENARIO,
            correlation_id=None,
        ),
    )


async def _run_round(
    *,
    host: Host,
    watcher: AsyncIterator[HostEvent],
    session_id: str,
    spec: RoundSpec,
    client_request_id: str,
    scene_inputs: PreparedSceneInputs,
) -> RoundResult:
    """提交一轮 prompt 并等待 terminal HostEvent。

    :param host: public Host handle。
    :param watcher: session-level HostEvent iterator。
    :param session_id: Session id。
    :param spec: 本轮场景规格。
    :param client_request_id: 幂等请求 id。
    :param scene_inputs: ScenePrepare 输出。
    :returns: RoundResult。
    :raises RuntimeError: terminal 不是 succeeded 或缺少 final answer 时抛出。
    """

    print(f"{_STDOUT_PREFIX_ROUND_START} label={spec.label}")
    accepted = await host.submit_followup(
        session_id,
        compose_submit_followup_request(
            context=_host_context(client_request_id),
            session_id=session_id,
            client_request_id=client_request_id,
            scene_inputs=scene_inputs,
            user_prompt=spec.prompt,
            tool_names=spec.tool_names,
            behavior=FollowupBehavior.QUEUE,
            target_run_id=None,
        ),
    )
    event = await _next_terminal_for_run(watcher, accepted.accepted_run_id)
    if event.kind is not HostEventKind.SUCCEEDED:
        print(
            "SMOKE ROUND_FAILED "
            + await _terminal_failure_summary(
                host=host,
                event=event,
                run_id=accepted.accepted_run_id,
                label=spec.label,
            )
        )
        raise RuntimeError(
            f"round {spec.label} terminal kind is {event.kind.value}; " f"run_id={accepted.accepted_run_id}"
        )
    if event.final_answer is None or event.final_answer.content.strip() == "":
        raise RuntimeError(f"round {spec.label} returned empty final answer")
    return RoundResult(
        label=spec.label,
        run_id=accepted.accepted_run_id,
        event=event,
    )


async def _terminal_failure_summary(
    *,
    host: Host,
    event: HostEvent,
    run_id: str,
    label: str,
) -> str:
    """构造 terminal failed 的脱敏短摘要。

    :param host: public Host handle。
    :param event: terminal HostEvent。
    :param run_id: 目标 Run id。
    :param label: smoke 轮次标签。
    :returns: 可直接打印的一行短摘要。
    :raises Exception: public ``get_run`` 失败时向上抛出。
    """

    snapshot = await host.get_run(run_id)
    terminal_summary = snapshot.terminal_result_summary
    summary_ref = terminal_summary.summary_ref if terminal_summary is not None else None
    summary_digest = terminal_summary.summary_digest if terminal_summary is not None else None
    message = _safe_summary_text(event.error_message)
    terminal_status = event.terminal_status.value if event.terminal_status is not None else "unknown"
    return (
        f"label={label} run_id={run_id} kind={event.kind.value} "
        f"terminal_status={terminal_status} "
        f"event_id={event.event_id} event_sequence={event.event_sequence} "
        f"message={message!r} terminal_summary_ref={summary_ref!r} "
        f"terminal_summary_digest={summary_digest!r}"
    )


def _safe_summary_text(text: str | None) -> str:
    """脱敏并截断 smoke 失败摘要文本。

    :param text: Host public error message。
    :returns: 安全短文本。
    :raises Exception: 不主动抛出异常。
    """

    if text is None or text.strip() == "":
        return "none"
    secret_markers = ("api_key", "apikey", "authorization", "bearer ", "token", "secret")
    lowered = text.lower()
    if any(marker in lowered for marker in secret_markers):
        return "<redacted>"
    max_length = 240
    if len(text) <= max_length:
        return text
    return text[:max_length] + "..."


async def _next_terminal_for_run(iterator: AsyncIterator[HostEvent], run_id: str) -> HostEvent:
    """读取指定 Run 的 terminal HostEvent。

    :param iterator: HostEvent iterator。
    :param run_id: Run id。
    :returns: terminal HostEvent。
    :raises TimeoutError: 超时未收到 terminal event 时抛出。
    :raises RuntimeError: iterator 结束前没有 terminal event 时抛出。
    """

    while True:
        event = await asyncio.wait_for(
            anext(iterator),
            timeout=_TERMINAL_TIMEOUT_SECONDS,
        )
        if event.run_id == run_id and event.terminal_status is not None:
            return event


def _assert_round_result(
    result: RoundResult,
    smoke_tool: MockFinanceMemoryTool,
    spec: RoundSpec,
    *,
    before_tools: ToolCallSnapshot,
    debug_smoke_output: bool,
) -> None:
    """按 RoundSpec 执行本轮硬断言与软观察。

    :param result: 单轮运行摘要。
    :param smoke_tool: tracked session 的 mock tool 实例。
    :param spec: 本轮场景规格。
    :param before_tools: 本轮运行前的工具调用计数快照。
    :param debug_smoke_output: 是否打印本轮工具调用 delta 诊断。
    :returns: ``None``。
    :raises RuntimeError: 工具禁用轮次出现工具调用，或工具启用轮次未命中
        目标 fact key 时抛出。
    :raises AssertionError: 回答硬断言失败时抛出。
    """

    _assert_tool_usage(
        spec,
        smoke_tool=smoke_tool,
        before=before_tools,
        debug_smoke_output=debug_smoke_output,
    )
    content = _final_answer_content(result)
    assert_answer_contains(
        content,
        label=spec.label,
        required=spec.hard_answer_contains,
        forbidden=spec.hard_answer_forbidden,
    )
    missing_soft = observe_soft_answer_contains(
        content,
        label=spec.label,
        markers=spec.soft_answer_contains,
    )
    if missing_soft:
        print(
            f"{_STDOUT_PREFIX_SOFT_OBSERVE} label={spec.label} " f"status=soft-missing markers={','.join(missing_soft)}"
        )


def _assert_tool_usage(
    spec: RoundSpec,
    *,
    smoke_tool: MockFinanceMemoryTool,
    before: ToolCallSnapshot,
    debug_smoke_output: bool,
) -> None:
    """断言本轮工具使用符合 conversation memory smoke 语义。

    工具禁用轮次的硬契约是没有新增工具调用；工具启用轮次的硬契约是
    至少命中目标 fact key 一次。额外工具调用属于模型行为诊断，不作为
    conversation memory 失败条件。

    :param spec: 本轮场景规格。
    :param smoke_tool: tracked session 的 mock 工具实例。
    :param before: 本轮运行前的工具调用快照。
    :param debug_smoke_output: 是否打印本轮 delta 诊断。
    :returns: ``None``。
    :raises RuntimeError: 工具禁用轮次出现调用，或工具启用轮次未命中目标
        fact key 时抛出。
    """

    after = smoke_tool.snapshot()
    observations = smoke_tool.observations_since(before)
    total_delta = after.total_count - before.total_count
    expected_key = spec.expected_tool_fact_key
    key_delta = (
        _tool_call_count(after.calls_by_key, expected_key) - _tool_call_count(before.calls_by_key, expected_key)
        if expected_key is not None
        else 0
    )
    if debug_smoke_output:
        print_tool_delta(
            label=spec.label,
            spec=spec,
            total_delta=total_delta,
            key_delta=key_delta,
        )

    if not spec.tool_names:
        if total_delta != 0:
            raise RuntimeError(
                f"{spec.label} no-tool round produced {total_delta} tool calls: "
                f"{_format_tool_observations(observations)}"
            )
        return
    if expected_key is None:
        return
    if key_delta < 1:
        raise RuntimeError(
            f"{spec.label} expected tool fact {expected_key}, got delta "
            f"{key_delta}; calls={_format_tool_observations(observations)}"
        )
    extra_observations = tuple(observation for observation in observations if observation.fact_key != expected_key)
    if debug_smoke_output and extra_observations:
        print_tool_extra(label=spec.label, observations=extra_observations)


def _tool_call_count(calls_by_key: Mapping[str, int], key: str | None) -> int:
    """读取 fact key 对应的工具调用计数。

    :param calls_by_key: fact key 到调用次数的映射。
    :param key: 需要读取的 fact key；为 ``None`` 时返回 0。
    :returns: 对应调用次数。
    :raises Exception: 不主动抛出异常。
    """

    if key is None:
        return 0
    return calls_by_key.get(key, 0)


def _tool_call_observation(
    *,
    sequence: int,
    call: ToolCallRequest,
    fact_key: str,
    known: bool,
) -> ToolCallObservation:
    """从工具调用请求构造 smoke 诊断记录。

    :param sequence: tracked session 内递增调用序号。
    :param call: 工具调用请求。
    :param fact_key: 命中的 fact key；未知时为 ``_UNKNOWN_FACT_KEY``。
    :param known: 是否命中已知 mock fact。
    :returns: 单次工具调用诊断。
    :raises Exception: 不主动抛出异常。
    """

    return ToolCallObservation(
        sequence=sequence,
        tool_call_id=call.tool_call_id,
        known=known,
        fact_key=fact_key,
        company=_argument_str(call.arguments, _FIELD_COMPANY),
        ticker=_argument_str(call.arguments, _FIELD_TICKER),
        period=_argument_str(call.arguments, _FIELD_PERIOD),
        topic=_argument_str(call.arguments, _FIELD_TOPIC),
        metric=_argument_str(call.arguments, _FIELD_METRIC),
        include_pressure=_argument_bool(
            call.arguments,
            _FIELD_INCLUDE_PRESSURE,
            default=False,
        ),
    )


def print_tool_delta(
    *,
    label: str,
    spec: RoundSpec,
    total_delta: int,
    key_delta: int,
) -> None:
    """打印本轮工具调用 delta 诊断。

    :param label: 当前轮次标签。
    :param spec: 当前轮次规格。
    :param total_delta: 本轮新增工具调用次数。
    :param key_delta: 目标 fact key 本轮新增命中次数。
    :returns: ``None``。
    :raises Exception: 不主动抛出异常。
    """

    tools = "<none>" if not spec.tool_names else ",".join(sorted(spec.tool_names))
    expected_key = spec.expected_tool_fact_key or "<none>"
    print(
        f"{_STDOUT_PREFIX_TOOL_DELTA} label={label} tools={tools} "
        f"expected_fact_key={expected_key} total_delta={total_delta} "
        f"expected_key_delta={key_delta}"
    )


def print_tool_call_observation(observation: ToolCallObservation) -> None:
    """打印单次 mock 工具调用诊断。

    :param observation: 工具调用诊断。
    :returns: ``None``。
    :raises Exception: 不主动抛出异常。
    """

    print(f"{_STDOUT_PREFIX_TOOL_CALL} {_format_tool_observation(observation)}")


def print_tool_extra(*, label: str, observations: tuple[ToolCallObservation, ...]) -> None:
    """打印工具启用轮次中的非目标工具调用诊断。

    :param label: 当前轮次标签。
    :param observations: 非目标 fact key 调用诊断。
    :returns: ``None``。
    :raises Exception: 不主动抛出异常。
    """

    print(
        f"{_STDOUT_PREFIX_TOOL_EXTRA} label={label} count={len(observations)} "
        f"calls={_format_tool_observations(observations)}"
    )


def _format_tool_observations(
    observations: tuple[ToolCallObservation, ...],
) -> str:
    """格式化多条工具调用诊断。

    :param observations: 工具调用诊断序列。
    :returns: 单行诊断字符串。
    :raises Exception: 不主动抛出异常。
    """

    if not observations:
        return "<none>"
    return " | ".join(_format_tool_observation(item) for item in observations)


def _format_tool_observation(observation: ToolCallObservation) -> str:
    """格式化单条工具调用诊断。

    :param observation: 工具调用诊断。
    :returns: 单行诊断字符串。
    :raises Exception: 不主动抛出异常。
    """

    include_pressure = "true" if observation.include_pressure else "false"
    known = "true" if observation.known else "false"
    return (
        f"seq={observation.sequence} tool_call_id={observation.tool_call_id} "
        f"known={known} fact_key={observation.fact_key} "
        f"company={observation.company} ticker={observation.ticker} "
        f"period={observation.period} topic={observation.topic} "
        f"metric={observation.metric} include_pressure={include_pressure}"
    )


def _final_answer_content(result: RoundResult) -> str:
    """读取单轮 final answer 内容。

    :param result: 单轮运行摘要。
    :returns: 已去首尾空白的 final answer。
    :raises RuntimeError: 缺少 final answer 时抛出。
    """

    final_answer = result.event.final_answer
    if final_answer is None:
        raise RuntimeError(f"{result.label} missing final answer")
    return final_answer.content.strip()


def _assert_session_open(snapshot: SessionSnapshot, *, label: str) -> None:
    """断言 public session 快照仍为 open。

    :param snapshot: public SessionSnapshot。
    :param label: 当前观测标签。
    :returns: ``None``。
    :raises RuntimeError: Session 已关闭时抛出。
    """

    if snapshot.status is SessionStatus.CLOSED:
        raise RuntimeError(f"{label} session is closed: {snapshot.session_id}")


def _compact_pressure_padding(options: OpenHostOptions) -> str:
    """构造预算压力 padding，使估算值落在 soft / hard threshold 之间。

    :param options: 本次 smoke 使用的 Host opener options。
    :returns: 用于用户 prompt 的 padding。
    :raises RuntimeError: smoke 未启用 context budget policy 时抛出。
    """

    return _compact_pressure_padding_with_reserve(
        options,
        reserve_tokens=_COMPACT_PRESSURE_RESERVE_TOKENS,
    )


def _compact_pressure_padding_with_reserve(
    options: OpenHostOptions,
    *,
    reserve_tokens: int,
) -> str:
    """按指定历史 reserve 构造预算压力 padding。

    :param options: 本次 smoke 使用的 Host opener options。
    :param reserve_tokens: 为既有历史与固定消息预留的估算 token。
    :returns: 用于用户 prompt 的 padding。
    :raises RuntimeError: smoke 未启用 context budget policy 时抛出。
    :raises ValueError: reserve token 为负数时抛出。
    """

    if reserve_tokens < 0:
        raise ValueError("reserve_tokens must be non-negative")
    policy = options.context_budget_policy
    if policy is None:
        raise RuntimeError("smoke compact pressure requires context budget policy")
    soft_threshold_tokens = _threshold_tokens(
        policy.context_window_size,
        policy.soft_threshold_context_ratio,
    )
    hard_threshold_tokens = _threshold_tokens(
        policy.context_window_size,
        policy.hard_threshold_context_ratio,
    )
    target_tokens = min(
        soft_threshold_tokens + _COMPACT_PRESSURE_TARGET_EXTRA_TOKENS,
        hard_threshold_tokens - _COMPACT_PRESSURE_HARD_MARGIN_TOKENS,
    )
    tool_pressure_tokens = _tool_pressure_estimated_tokens()
    prompt_tokens = max(
        _COMPACT_PRESSURE_MIN_PROMPT_TOKENS,
        target_tokens - reserve_tokens - tool_pressure_tokens,
    )
    return _repeat_to_chars(
        token=_MOCK_PRESSURE_UNIT,
        target_chars=prompt_tokens * DEFAULT_ESTIMATOR_CHARS_PER_TOKEN,
    )


def _threshold_tokens(context_window_size: int, ratio: float) -> int:
    """按 Host context budget ratio 计算阈值 token 数。

    :param context_window_size: 当前模型上下文窗口 token 数。
    :param ratio: 阈值比例。
    :returns: 阈值 token 数。
    :raises Exception: 不主动抛出异常。
    """

    return floor(context_window_size * ratio)


def _tool_pressure_estimated_tokens() -> int:
    """估算 smoke tool 压力片段贡献的 token 数。

    :returns: 估算 token 数。
    :raises Exception: 不主动抛出异常。
    """

    return _estimate_chars_as_tokens(len(_mock_pressure_blob(True, PressureMode.AUTO)))


def _estimate_chars_as_tokens(char_count: int) -> int:
    """按 Host conservative estimator 估算字符量对应的 token 数。

    :param char_count: 字符数量。
    :returns: 估算 token 数。
    :raises Exception: 不主动抛出异常。
    """

    return (char_count + DEFAULT_ESTIMATOR_CHARS_PER_TOKEN - 1) // DEFAULT_ESTIMATOR_CHARS_PER_TOKEN


def _repeat_to_chars(*, token: str, target_chars: int) -> str:
    """把稳定 token 重复到目标字符量。

    :param token: 重复使用的短文本。
    :param target_chars: 目标字符数。
    :returns: 至少达到目标字符数的文本。
    :raises Exception: 不主动抛出异常。
    """

    line = f"{token} " * max(1, _PRESSURE_LINE_CHARS // len(token))
    repeat_count = max(1, target_chars // len(line) + 1)
    return (line * repeat_count)[:target_chars]


def _new_smoke_run_id() -> str:
    """生成本次手工 smoke 的调用方请求批次 id。

    :returns: 用于 stdout 和 client request id 的唯一短 id。
    :raises Exception: 不主动抛出异常。
    """

    return uuid4().hex[:12]


def _round_client_request_id(smoke_run_id: str, round_index: int) -> str:
    """构造每轮 Host command 的幂等请求 id。

    :param smoke_run_id: 本次手工 smoke 批次 id。
    :param round_index: 轮次序号。
    :returns: 本轮 ``client_request_id``。
    :raises Exception: 不主动抛出异常。
    """

    return f"{_CLIENT_REQUEST_PREFIX}-{smoke_run_id}-round-{round_index}"


def _print_assembly_diagnostics(
    diagnostics: ServiceOpenHostAssemblyDiagnostics,
    options: OpenHostOptions,
) -> None:
    """打印 Host 调用前 assembly diagnostics。

    :param diagnostics: assembly diagnostics。
    :param options: Host opener options，用于打印 effective tooling policy。
    :returns: ``None``。
    :raises Exception: 不主动抛出异常。
    """

    print("SMOKE ASSEMBLY_MODE runtime", flush=True)
    print(f"SMOKE ASSEMBLY config_overlay={diagnostics.config_overlay_dir}", flush=True)
    print(f"SMOKE ASSEMBLY prompt_asset_root={diagnostics.prompt_asset_root}", flush=True)
    print(f"SMOKE ASSEMBLY scene_manifest_root={diagnostics.scene_manifest_root}", flush=True)
    print(f"SMOKE ASSEMBLY host_runtime_id={diagnostics.host_runtime_id}", flush=True)
    print(f"SMOKE ASSEMBLY execution_profile_id={diagnostics.execution_profile_id}", flush=True)
    print(f"SMOKE ASSEMBLY model_id={diagnostics.model_id} source={diagnostics.model_source}", flush=True)
    print(
        "SMOKE ASSEMBLY runner_option_hint_id="
        f"{diagnostics.runner_option_hint_id} "
        f"source={diagnostics.runner_option_hint_source}",
        flush=True,
    )
    print(f"SMOKE ASSEMBLY compactor_model_id={diagnostics.compactor_model_id}", flush=True)
    print(
        "SMOKE ASSEMBLY compactor_runner_option_hint_id=" f"{diagnostics.compactor_runner_option_hint_id}",
        flush=True,
    )
    print(f"SMOKE ASSEMBLY lane_name={diagnostics.lane_name}", flush=True)
    if diagnostics.tool_provider_reports:
        for report in diagnostics.tool_provider_reports:
            print(f"SMOKE ASSEMBLY tool_provider_report={report}", flush=True)
    else:
        print("SMOKE ASSEMBLY tool_provider_report=<none>", flush=True)
    print(f"SMOKE ASSEMBLY tool_selection={diagnostics.tool_selection}", flush=True)
    print(
        "SMOKE ASSEMBLY policy_refs="
        f"context_budget:{diagnostics.context_budget_policy_ref},"
        f"tool_truncation:{diagnostics.tool_truncation_policy}",
        flush=True,
    )
    print_duplicate_governance_diagnostics(options)
    print("SMOKE ASSEMBLY agent_policy_sources=" f"{','.join(diagnostics.agent_policy_sources)}", flush=True)
    print(
        "SMOKE ASSEMBLY provider_extension_status="
        f"ordinary:{diagnostics.ordinary_provider_extension_status},"
        f"compactor:{diagnostics.compactor_provider_extension_status}",
        flush=True,
    )


def _print_compact_pressure_plan(
    options: OpenHostOptions,
    pressure_mode: PressureMode,
    *,
    suite: SuiteMode,
) -> None:
    """打印 compact pressure 摘要，不输出完整 pressure prompt。

    :param options: 本次 smoke 使用的 Host opener options。
    :param pressure_mode: 压力注入模式。
    :param suite: 当前 suite，用于选择 suite-specific pressure padding。
    :returns: ``None``。
    :raises Exception: 不主动抛出异常。
    """

    if pressure_mode is PressureMode.OFF:
        print("SMOKE COMPACT_PRESSURE skipped pressure_mode=off", flush=True)
        return
    policy = options.context_budget_policy
    if policy is None:
        print("SMOKE COMPACT_PRESSURE disabled", flush=True)
        return
    soft_threshold_tokens = _threshold_tokens(
        policy.context_window_size,
        policy.soft_threshold_context_ratio,
    )
    hard_threshold_tokens = _threshold_tokens(
        policy.context_window_size,
        policy.hard_threshold_context_ratio,
    )
    prompt = (
        _fallback_compact_pressure_padding(options)
        if suite is SuiteMode.MEMORY_COMPACT_FALLBACK
        else _compact_pressure_padding(options)
    )
    prompt_chars = len(prompt)
    estimated_prompt_tokens = _estimate_chars_as_tokens(prompt_chars)
    reserve_tokens = _compact_pressure_reserve_tokens(suite)
    tool_pressure_tokens = _tool_pressure_estimated_tokens()
    estimated_without_reserve_tokens = estimated_prompt_tokens + tool_pressure_tokens
    estimated_effective_pressure_tokens = estimated_without_reserve_tokens + reserve_tokens
    print(
        "SMOKE COMPACT_PRESSURE "
        f"context_window_tokens={policy.context_window_size} "
        f"soft_threshold_tokens={soft_threshold_tokens} "
        f"hard_threshold_tokens={hard_threshold_tokens} "
        f"tool_pressure_tokens={tool_pressure_tokens} "
        f"reserve_tokens={reserve_tokens} "
        f"prompt_pressure_chars={prompt_chars} "
        f"estimated_prompt_tokens={estimated_prompt_tokens} "
        f"estimated_without_reserve_tokens={estimated_without_reserve_tokens} "
        f"estimated_effective_pressure_tokens={estimated_effective_pressure_tokens} "
        f"estimated_total_pressure_tokens={estimated_effective_pressure_tokens}",
        flush=True,
    )


def _print_round(result: RoundResult) -> None:
    """打印一轮运行摘要。

    :param result: 轮次结果。
    :returns: ``None``。
    :raises Exception: 不主动抛出异常。
    """

    content = _final_answer_content(result)
    preview = content[:_FINAL_PREVIEW_CHARS]
    terminal = result.event.terminal_status.value if result.event.terminal_status is not None else "none"
    print(
        f"{_STDOUT_PREFIX_ROUND_DONE} "
        f"label={result.label} run_id={result.run_id} "
        f"event_id={result.event.event_id} "
        f"event_sequence={result.event.event_sequence} "
        f"terminal={terminal}",
        flush=True,
    )
    print(f"{_STDOUT_PREFIX_FINAL_PREVIEW} label={result.label} content={preview!r}", flush=True)


def _print_session_observation(snapshot: SessionSnapshot, *, label: str) -> None:
    """打印 active / queued 软观测。

    :param snapshot: public SessionSnapshot。
    :param label: 当前观测标签。
    :returns: ``None``。
    :raises Exception: 不主动抛出异常。
    """

    queued_count = len(snapshot.queued_run_ids)
    active_run_id = snapshot.active_run_id if snapshot.active_run_id is not None else "<none>"
    print(
        f"{_STDOUT_PREFIX_SESSION_OBSERVE} label={label} "
        f"status={snapshot.status.value} active_run_id={active_run_id} "
        f"queued_run_count={queued_count}",
        flush=True,
    )


def _print_compact_audit_summary(summary: CompactAuditSummary) -> None:
    """打印 compact EventLog audit 摘要。

    :param summary: 本次 session 的 compact EventLog 摘要。
    :returns: ``None``。
    :raises Exception: 不主动抛出异常。
    """

    print(
        f"{_STDOUT_PREFIX_COMPACT_AUDIT} "
        f"requested_proactive={summary.requested_proactive} "
        f"requested_reactive={summary.requested_reactive} "
        f"compacted_proactive={summary.compacted_proactive} "
        f"compacted_reactive={summary.compacted_reactive} "
        f"failed_proactive={summary.failed_proactive} "
        f"failed_reactive={summary.failed_reactive} "
        f"rejected_proactive={summary.rejected_proactive} "
        f"rejected_reactive={summary.rejected_reactive}",
        flush=True,
    )


def _print_compact_audit_report(report: CompactAuditReport, *, debug_smoke_output: bool) -> None:
    """打印 compact EventLog 结构化审计报告。

    :param report: compact EventLog 结构化审计报告。
    :param debug_smoke_output: 是否打印 rejected attempt 明细。
    :returns: ``None``。
    :raises Exception: 不主动抛出异常。
    """

    for operation in report.operations:
        _print_compact_operation(operation)
    _print_compact_histogram(
        kind="failure_category",
        histogram=report.rejected_failure_histogram,
    )
    _print_compact_histogram(
        kind="diagnostic_suffix",
        histogram=report.rejected_diagnostic_histogram,
    )
    _print_compact_histogram(
        kind="proposal_manifest_ref",
        histogram=report.rejected_manifest_presence_histogram,
    )
    if debug_smoke_output:
        for operation in report.operations:
            for attempt in operation.rejected_attempts:
                _print_compact_reject_detail(operation, attempt)


def _print_compact_operation(operation: CompactOperationAudit) -> None:
    """打印单个 compact operation timeline。

    :param operation: compact operation 审计摘要。
    :returns: ``None``。
    :raises Exception: 不主动抛出异常。
    """

    accepted_seq = _compact_sequence_text(operation.compacted_event_sequences)
    failed_seq = _compact_sequence_text(tuple(event.event_sequence for event in operation.failed_events))
    last_failed = operation.failed_events[-1] if operation.failed_events else None
    print(
        f"{_STDOUT_PREFIX_COMPACT_OPERATION} "
        f"operation_id={operation.operation_id} "
        f"request_seq={_compact_optional_text(operation.request_event_sequence)} "
        f"request_event_id={_compact_optional_text(operation.request_event_id)} "
        f"run_id={_compact_optional_text(operation.run_id)} "
        f"trigger_source={operation.trigger_source} "
        f"requested={operation.requested} "
        f"rejected={operation.rejected} "
        f"compacted={operation.compacted} "
        f"accepted_seq={accepted_seq} "
        f"failed={operation.failed} "
        f"failed_seq={failed_seq} "
        f"failure_reason={_compact_optional_text(last_failed.failure_reason if last_failed is not None else None)} "
        f"policy_decision={_compact_optional_text(last_failed.policy_decision if last_failed is not None else None)} "
        "fallback_policy_decision="
        f"{_compact_optional_text(last_failed.fallback_policy_decision if last_failed is not None else None)} "
        f"fallback_action={_compact_optional_text(last_failed.fallback_action if last_failed is not None else None)} "
        f"fallback_tier={_compact_optional_text(last_failed.fallback_tier if last_failed is not None else None)} "
        f"attempt_count={_compact_optional_text(last_failed.attempt_count if last_failed is not None else None)} "
        "fallback_selected_block_ids="
        f"{len(last_failed.selected_block_ids) if last_failed is not None else 0} "
        "fallback_dropped_block_ids="
        f"{len(last_failed.dropped_block_ids) if last_failed is not None else 0} "
        "fallback_current_input_ref="
        f"{_compact_optional_text(last_failed.current_input_ref if last_failed is not None else None)}",
        flush=True,
    )


def _print_compact_histogram(*, kind: str, histogram: tuple[tuple[str, int], ...]) -> None:
    """打印 compact rejected attempt histogram。

    :param kind: histogram 类型。
    :param histogram: histogram items。
    :returns: ``None``。
    :raises Exception: 不主动抛出异常。
    """

    if not histogram:
        print(
            f"{_STDOUT_PREFIX_COMPACT_REJECT_HISTOGRAM} "
            f"kind={kind} value={_COMPACT_HISTOGRAM_EMPTY} count=0",
            flush=True,
        )
        return
    for value, count in histogram[:_COMPACT_HISTOGRAM_PRINT_LIMIT]:
        print(
            f"{_STDOUT_PREFIX_COMPACT_REJECT_HISTOGRAM} "
            f"kind={kind} value={value!r} count={count}",
            flush=True,
        )


def _print_compact_reject_detail(
    operation: CompactOperationAudit,
    attempt: CompactRejectedAttemptAudit,
) -> None:
    """打印单个 compact rejected attempt 明细。

    :param operation: compact operation 审计摘要。
    :param attempt: rejected attempt 审计摘要。
    :returns: ``None``。
    :raises Exception: 不主动抛出异常。
    """

    diagnostic_suffixes = tuple(_compact_normalized_diagnostic_suffix(ref) for ref in attempt.diagnostic_refs)
    print(
        f"{_STDOUT_PREFIX_COMPACT_REJECT_DETAIL} "
        f"operation_id={operation.operation_id} "
        f"event_seq={attempt.event_sequence} "
        f"attempt_number={_compact_optional_text(attempt.attempt_number)} "
        f"trigger_source={_compact_optional_text(attempt.trigger_source)} "
        f"failure_category={_compact_optional_text(attempt.failure_category)} "
        f"repairable={_compact_optional_text(attempt.repairable)} "
        f"next_policy_decision={_compact_optional_text(attempt.next_policy_decision)} "
        f"proposal_manifest_ref={_compact_manifest_presence(attempt.proposal_manifest_ref)} "
        f"failure_stage={_compact_failure_stage(attempt.proposal_manifest_ref)} "
        f"log_insufficient={_compact_log_insufficient(attempt.proposal_manifest_ref)} "
        f"diagnostic_suffixes={_compact_sequence_text(diagnostic_suffixes)} "
        "budget_after_attempted_compact="
        f"{_compact_optional_text(attempt.budget_after_attempted_compact)}",
        flush=True,
    )


def _compact_sequence_text(values: tuple[int, ...] | tuple[str, ...]) -> str:
    """格式化 compact 诊断序列。

    :param values: 整数或字符串元组。
    :returns: 逗号分隔文本；空序列返回占位符。
    :raises Exception: 不主动抛出异常。
    """

    if not values:
        return _COMPACT_NONE_VALUE
    return ",".join(str(value) for value in values)


def _assert_compact_acceptance(
    *,
    suite: SuiteMode,
    audit: CompactAuditSummary,
    options: OpenHostOptions,
) -> None:
    """按 suite 断言 compact 验收信号。

    ``memory-core`` 不要求 compact；``memory-compact`` 必须看到 proactive
    compact request 与 accepted compact，且任何 compact failed 都是硬失败。

    :param suite: 本次 smoke suite。
    :param audit: 本次 session 的 compact EventLog 摘要。
    :param options: 本次 Host opener options，用于检查 compact artifact 文件数。
    :returns: ``None``。
    :raises RuntimeError: compact suite 未观察到 accepted compact 或观察到
        failed compact 时抛出。
    """

    if suite is not SuiteMode.MEMORY_COMPACT:
        return
    artifact_count = len(_compact_artifact_files(options))
    failed_total = audit.failed_proactive + audit.failed_reactive
    if audit.requested_proactive < 1:
        raise RuntimeError("memory-compact did not observe proactive CONTEXT_COMPACTION_REQUESTED")
    if audit.compacted_proactive < 1:
        raise RuntimeError("memory-compact did not observe proactive CONTEXT_COMPACTED")
    if failed_total > 0:
        raise RuntimeError("memory-compact observed CONTEXT_COMPACTION_FAILED")
    if artifact_count < 1:
        raise RuntimeError("memory-compact did not observe compact artifact files")
    print(
        f"{_STDOUT_PREFIX_COMPACT_ACCEPTANCE} status=pass "
        f"requested_proactive={audit.requested_proactive} "
        f"compacted_proactive={audit.compacted_proactive} "
        f"failed_total={failed_total} "
        f"artifact_files={artifact_count}",
        flush=True,
    )


def _compact_audit_summary(options: OpenHostOptions, *, session_id: str) -> CompactAuditSummary:
    """读取本次 session 的 compact EventLog 摘要。

    :param options: 本次 Host opener options。
    :param session_id: 本次 smoke session id。
    :returns: compact event 计数摘要。
    :raises Exception: durable store 打开、EventLog 读取或 payload 解析失败时向上抛出。
    """

    return _compact_audit_report(options, session_id=session_id).summary


def _compact_audit_report(options: OpenHostOptions, *, session_id: str) -> CompactAuditReport:
    """读取本次 session 的 compact EventLog 审计报告。

    :param options: 本次 Host opener options。
    :param session_id: 本次 smoke session id。
    :returns: compact EventLog 结构化审计报告。
    :raises Exception: durable store 打开、EventLog 读取或 payload 解析失败时向上抛出。
    """

    durable_options = _durable_options_from_open_host_options(options)
    rows: tuple[EventLogRow, ...] = ()
    with open_host_durable_store(durable_options) as store:
        rows = store.transaction_runner.run_read(
            lambda transaction: _read_compact_event_rows(
                transaction,
                event_log_store=EventLogStore(),
                session_id=session_id,
            )
        )
    return _compact_audit_report_from_rows(rows)


def _compact_audit_report_from_rows(rows: tuple[EventLogRow, ...]) -> CompactAuditReport:
    """从 compact EventLog rows 构造结构化审计报告。

    :param rows: compact EventLog rows。
    :returns: compact EventLog 结构化审计报告。
    :raises ValueError: payload JSON 不是 object 时抛出。
    """

    summary = _compact_audit_summary_from_rows(rows)
    request_trigger_sources = _compact_request_trigger_sources(rows)
    request_rows: dict[str, list[EventLogRow]] = {}
    compacted_rows: dict[str, list[EventLogRow]] = {}
    rejected_attempts: dict[str, list[CompactRejectedAttemptAudit]] = {}
    failed_events: dict[str, list[CompactFailedOperationAudit]] = {}
    operation_ids: set[str] = set()
    for row in rows:
        operation_id = _compact_operation_key(row)
        operation_ids.add(operation_id)
        if row.event_type == CONTEXT_COMPACTION_REQUESTED:
            request_rows.setdefault(operation_id, []).append(row)
        elif row.event_type == CONTEXT_COMPACTED:
            compacted_rows.setdefault(operation_id, []).append(row)
        elif row.event_type == CONTEXT_COMPACTION_ATTEMPT_REJECTED:
            rejected_attempts.setdefault(operation_id, []).append(
                _compact_rejected_attempt_audit(row, request_trigger_sources=request_trigger_sources)
            )
        elif row.event_type == CONTEXT_COMPACTION_FAILED:
            failed_events.setdefault(operation_id, []).append(
                _compact_failed_operation_audit(row, request_trigger_sources=request_trigger_sources)
            )
    operations = tuple(
        _compact_operation_audit(
            operation_id,
            request_rows=tuple(request_rows.get(operation_id, ())),
            compacted_rows=tuple(compacted_rows.get(operation_id, ())),
            rejected_attempts=tuple(rejected_attempts.get(operation_id, ())),
            failed_events=tuple(failed_events.get(operation_id, ())),
            request_trigger_sources=request_trigger_sources,
        )
        for operation_id in sorted(
            operation_ids,
            key=lambda item: _compact_operation_sort_key(
                item,
                request_rows=request_rows,
                compacted_rows=compacted_rows,
                rejected_attempts=rejected_attempts,
                failed_events=failed_events,
            ),
        )
    )
    return CompactAuditReport(
        summary=summary,
        operations=operations,
        rejected_failure_histogram=_compact_rejected_failure_histogram(operations),
        rejected_diagnostic_histogram=_compact_rejected_diagnostic_histogram(operations),
        rejected_manifest_presence_histogram=_compact_rejected_manifest_presence_histogram(operations),
    )


def _durable_options_from_open_host_options(options: OpenHostOptions) -> HostDurableStoreOptions:
    """从 Host opener options 构造 durable store options。

    :param options: 本次 Host opener options。
    :returns: durable store 打开选项。
    :raises Exception: 字段非法时由 durable options 校验抛出。
    """

    return HostDurableStoreOptions(
        db_path=options.db_path,
        payload_policy=PayloadStoragePolicy(
            artifact_root=options.artifact_root,
            payload_inline_threshold_bytes=options.payload_inline_threshold_bytes,
            create_artifact_root=options.create_parent_dirs,
        ),
        create_parent_dirs=options.create_parent_dirs,
        sqlite_policy=HostSQLiteStoragePolicy(
            busy_timeout_seconds=options.sqlite_busy_timeout_seconds,
            write_busy_retry_count=options.sqlite_write_busy_retry_count,
            write_retry_initial_delay_seconds=options.sqlite_write_retry_initial_delay_seconds,
            write_retry_backoff_multiplier=options.sqlite_write_retry_backoff_multiplier,
            write_retry_max_delay_seconds=options.sqlite_write_retry_max_delay_seconds,
        ),
    )


def _read_compact_event_rows(
    transaction: HostTransaction,
    *,
    event_log_store: EventLogStore,
    session_id: str,
) -> tuple[EventLogRow, ...]:
    """读取指定 session 的 compact canonical EventLog rows。

    :param transaction: Host durable read transaction。
    :param event_log_store: EventLog typed store。
    :param session_id: 目标 session id。
    :returns: compact EventLog rows，按 event_sequence 升序排列。
    :raises Exception: EventLog 读取失败时向上抛出。
    """

    event_filter = EventLogReadFilter(
        class_filters=(
            EventLogReadClassFilter(
                event_class=EventClass.CANONICAL_FACT,
                event_types=_COMPACT_EVENT_TYPES,
            ),
        )
    )
    cursor = 0
    rows: list[EventLogRow] = []
    while True:
        page = event_log_store.read_events_after_matching(
            transaction,
            cursor,
            event_filter=event_filter,
            limit=_COMPACT_EVENT_AUDIT_PAGE_SIZE,
            session_id=session_id,
        )
        rows.extend(page.rows)
        if page.covered_event_sequence == cursor:
            return tuple(rows)
        cursor = page.covered_event_sequence


def _compact_operation_key(row: EventLogRow) -> str:
    """返回 compact row 的 operation 分组键。

    :param row: compact EventLog row。
    :returns: operation 分组键；缺失时返回固定占位符。
    :raises ValueError: payload JSON 不是 object 时抛出。
    """

    if row.event_type == CONTEXT_COMPACTION_REQUESTED:
        return row.event_id
    operation_id = _compact_row_operation_id(row)
    if operation_id is None:
        return _COMPACT_OPERATION_MISSING_ID
    return operation_id


def _compact_operation_sort_key(
    operation_id: str,
    *,
    request_rows: Mapping[str, list[EventLogRow]],
    compacted_rows: Mapping[str, list[EventLogRow]],
    rejected_attempts: Mapping[str, list[CompactRejectedAttemptAudit]],
    failed_events: Mapping[str, list[CompactFailedOperationAudit]],
) -> tuple[int, str]:
    """返回 compact operation 的稳定排序键。

    :param operation_id: compact operation id。
    :param request_rows: operation 到 request rows 的映射。
    :param compacted_rows: operation 到 accepted rows 的映射。
    :param rejected_attempts: operation 到 rejected attempt 审计的映射。
    :param failed_events: operation 到 failed event 审计的映射。
    :returns: 以最早 EventLog sequence 和 operation id 组成的排序键。
    :raises Exception: 不主动抛出异常。
    """

    sequences: list[int] = []
    sequences.extend(row.event_sequence for row in request_rows.get(operation_id, ()))
    sequences.extend(row.event_sequence for row in compacted_rows.get(operation_id, ()))
    sequences.extend(attempt.event_sequence for attempt in rejected_attempts.get(operation_id, ()))
    sequences.extend(event.event_sequence for event in failed_events.get(operation_id, ()))
    if not sequences:
        return (0, operation_id)
    return (min(sequences), operation_id)


def _compact_operation_audit(
    operation_id: str,
    *,
    request_rows: tuple[EventLogRow, ...],
    compacted_rows: tuple[EventLogRow, ...],
    rejected_attempts: tuple[CompactRejectedAttemptAudit, ...],
    failed_events: tuple[CompactFailedOperationAudit, ...],
    request_trigger_sources: Mapping[str, str],
) -> CompactOperationAudit:
    """构造单个 compact operation 的审计摘要。

    :param operation_id: compact operation id。
    :param request_rows: 归属该 operation 的 request rows。
    :param compacted_rows: 归属该 operation 的 accepted compact rows。
    :param rejected_attempts: 归属该 operation 的 rejected attempt 审计。
    :param failed_events: 归属该 operation 的 failed event 审计。
    :param request_trigger_sources: request event id 到 trigger source 的映射。
    :returns: 单个 compact operation 审计摘要。
    :raises ValueError: payload JSON 不是 object 时抛出。
    """

    first_request = request_rows[0] if request_rows else None
    trigger_source = _compact_operation_trigger_source(
        operation_id,
        request_rows=request_rows,
        rejected_attempts=rejected_attempts,
        failed_events=failed_events,
        request_trigger_sources=request_trigger_sources,
    )
    return CompactOperationAudit(
        operation_id=operation_id,
        trigger_source=trigger_source,
        request_event_id=first_request.event_id if first_request is not None else None,
        request_event_sequence=first_request.event_sequence if first_request is not None else None,
        run_id=first_request.run_id if first_request is not None else None,
        requested=len(request_rows),
        compacted=len(compacted_rows),
        compacted_event_sequences=tuple(row.event_sequence for row in compacted_rows),
        failed=len(failed_events),
        rejected=len(rejected_attempts),
        rejected_attempts=rejected_attempts,
        failed_events=failed_events,
        failure_categories=_compact_operation_failure_categories(rejected_attempts),
        diagnostic_histogram=_compact_operation_diagnostic_histogram(rejected_attempts),
    )


def _compact_operation_trigger_source(
    operation_id: str,
    *,
    request_rows: tuple[EventLogRow, ...],
    rejected_attempts: tuple[CompactRejectedAttemptAudit, ...],
    failed_events: tuple[CompactFailedOperationAudit, ...],
    request_trigger_sources: Mapping[str, str],
) -> str:
    """返回 compact operation 的 trigger source。

    :param operation_id: compact operation id。
    :param request_rows: 归属该 operation 的 request rows。
    :param rejected_attempts: 归属该 operation 的 rejected attempt 审计。
    :param failed_events: 归属该 operation 的 failed event 审计。
    :param request_trigger_sources: request event id 到 trigger source 的映射。
    :returns: trigger source；无法确定时返回占位符。
    :raises ValueError: payload JSON 不是 object 时抛出。
    """

    if request_rows:
        trigger_source = _compact_row_trigger_source(request_rows[0])
        if trigger_source is not None:
            return trigger_source
    trigger_source = request_trigger_sources.get(operation_id)
    if trigger_source is not None:
        return trigger_source
    for attempt in rejected_attempts:
        if attempt.trigger_source is not None:
            return attempt.trigger_source
    for event in failed_events:
        if event.trigger_source is not None:
            return event.trigger_source
    return _COMPACT_OPERATION_UNKNOWN_TRIGGER


def _compact_rejected_attempt_audit(
    row: EventLogRow,
    *,
    request_trigger_sources: Mapping[str, str],
) -> CompactRejectedAttemptAudit:
    """构造单个 compact rejected attempt 审计摘要。

    :param row: rejected attempt EventLog row。
    :param request_trigger_sources: request event id 到 trigger source 的映射。
    :returns: rejected attempt 审计摘要。
    :raises ValueError: payload JSON 不是 object 时抛出。
    """

    payload = _compact_row_payload(row)
    return CompactRejectedAttemptAudit(
        event_id=row.event_id,
        event_sequence=row.event_sequence,
        operation_id=_compact_payload_str(payload, _PAYLOAD_FIELD_OPERATION_ID),
        trigger_source=_compact_row_effective_trigger_source(row, request_trigger_sources),
        attempt_number=_compact_payload_int(payload, _PAYLOAD_FIELD_ATTEMPT_NUMBER),
        failure_category=_compact_payload_str(payload, _PAYLOAD_FIELD_FAILURE_CATEGORY),
        repairable=_compact_payload_bool(payload, _PAYLOAD_FIELD_REPAIRABLE),
        next_policy_decision=_compact_payload_str(payload, _PAYLOAD_FIELD_NEXT_POLICY_DECISION),
        budget_after_attempted_compact=_compact_payload_int(
            payload,
            _PAYLOAD_FIELD_BUDGET_AFTER_ATTEMPTED_COMPACT,
        ),
        runner_attempt_summary_refs=_compact_payload_str_tuple(
            payload,
            _PAYLOAD_FIELD_RUNNER_ATTEMPT_SUMMARY_REFS,
        ),
        diagnostic_refs=_compact_payload_str_tuple(payload, _PAYLOAD_FIELD_DIAGNOSTIC_REFS),
        proposal_manifest_ref=_compact_payload_str(payload, _PAYLOAD_FIELD_PROPOSAL_MANIFEST_REF),
        proposal_manifest_digest=_compact_payload_str(payload, _PAYLOAD_FIELD_PROPOSAL_MANIFEST_DIGEST),
    )


def _compact_failed_operation_audit(
    row: EventLogRow,
    *,
    request_trigger_sources: Mapping[str, str],
) -> CompactFailedOperationAudit:
    """构造单个 compact failed event 审计摘要。

    :param row: failed compact EventLog row。
    :param request_trigger_sources: request event id 到 trigger source 的映射。
    :returns: failed compact event 审计摘要。
    :raises ValueError: payload JSON 不是 object 时抛出。
    """

    payload = _compact_row_payload(row)
    fallback_window = _compact_payload_mapping(payload, _PAYLOAD_FIELD_FALLBACK_INPUT_WINDOW)
    return CompactFailedOperationAudit(
        event_id=row.event_id,
        event_sequence=row.event_sequence,
        operation_id=_compact_payload_str(payload, _PAYLOAD_FIELD_OPERATION_ID),
        trigger_source=_compact_row_effective_trigger_source(row, request_trigger_sources),
        failure_reason=_compact_payload_str(payload, _PAYLOAD_FIELD_FAILURE_REASON),
        policy_decision=_compact_payload_str(payload, _PAYLOAD_FIELD_POLICY_DECISION),
        fallback_policy_decision=_compact_payload_str(payload, _PAYLOAD_FIELD_FALLBACK_POLICY_DECISION),
        fallback_action=_compact_payload_str(payload, _PAYLOAD_FIELD_FALLBACK_ACTION),
        fallback_tier=_compact_payload_str(payload, _PAYLOAD_FIELD_FALLBACK_TIER),
        attempt_count=_compact_payload_int(payload, _PAYLOAD_FIELD_ATTEMPT_COUNT),
        retry_repair_budget_exhausted=_compact_payload_bool(
            payload,
            _PAYLOAD_FIELD_RETRY_REPAIR_BUDGET_EXHAUSTED,
        ),
        budget_after_attempted_compact=_compact_payload_int(
            payload,
            _PAYLOAD_FIELD_BUDGET_AFTER_ATTEMPTED_COMPACT,
        ),
        selected_block_ids=_compact_payload_str_tuple(
            fallback_window,
            _PAYLOAD_FIELD_SELECTED_BLOCK_IDS,
        ),
        dropped_block_ids=_compact_payload_str_tuple(
            fallback_window,
            _PAYLOAD_FIELD_DROPPED_BLOCK_IDS,
        ),
        current_input_ref=_compact_payload_str(
            fallback_window,
            _PAYLOAD_FIELD_CURRENT_INPUT_REF,
        ),
    )


def _compact_operation_failure_categories(
    attempts: tuple[CompactRejectedAttemptAudit, ...],
) -> tuple[tuple[str, int], ...]:
    """统计单个 operation 的 rejected failure category。

    :param attempts: rejected attempt 审计摘要。
    :returns: 按名称排序的 histogram。
    :raises Exception: 不主动抛出异常。
    """

    counter: Counter[str] = Counter(
        attempt.failure_category if attempt.failure_category is not None else _COMPACT_NONE_VALUE
        for attempt in attempts
    )
    return _compact_counter_items(counter)


def _compact_operation_diagnostic_histogram(
    attempts: tuple[CompactRejectedAttemptAudit, ...],
) -> tuple[tuple[str, int], ...]:
    """统计单个 operation 的 rejected diagnostic suffix。

    :param attempts: rejected attempt 审计摘要。
    :returns: 按名称排序的 histogram。
    :raises Exception: 不主动抛出异常。
    """

    counter: Counter[str] = Counter()
    for attempt in attempts:
        counter.update(_compact_normalized_diagnostic_suffix(ref) for ref in attempt.diagnostic_refs)
    return _compact_counter_items(counter)


def _compact_rejected_failure_histogram(
    operations: tuple[CompactOperationAudit, ...],
) -> tuple[tuple[str, int], ...]:
    """统计全部 operation 的 rejected failure category。

    :param operations: compact operation 审计摘要。
    :returns: 按名称排序的 histogram。
    :raises Exception: 不主动抛出异常。
    """

    counter: Counter[str] = Counter()
    for operation in operations:
        for name, count in operation.failure_categories:
            counter.update({name: count})
    return _compact_counter_items(counter)


def _compact_rejected_diagnostic_histogram(
    operations: tuple[CompactOperationAudit, ...],
) -> tuple[tuple[str, int], ...]:
    """统计全部 operation 的 rejected diagnostic suffix。

    :param operations: compact operation 审计摘要。
    :returns: 按名称排序的 histogram。
    :raises Exception: 不主动抛出异常。
    """

    counter: Counter[str] = Counter()
    for operation in operations:
        for name, count in operation.diagnostic_histogram:
            counter.update({name: count})
    return _compact_counter_items(counter)


def _compact_rejected_manifest_presence_histogram(
    operations: tuple[CompactOperationAudit, ...],
) -> tuple[tuple[str, int], ...]:
    """统计全部 rejected attempt 的 proposal manifest ref 有无。

    :param operations: compact operation 审计摘要。
    :returns: present / missing histogram。
    :raises Exception: 不主动抛出异常。
    """

    counter: Counter[str] = Counter()
    for operation in operations:
        counter.update(_compact_manifest_presence(attempt.proposal_manifest_ref) for attempt in operation.rejected_attempts)
    return _compact_counter_items(counter)


def _compact_counter_items(counter: Counter[str]) -> tuple[tuple[str, int], ...]:
    """返回稳定排序后的 counter items。

    :param counter: 字符串 counter。
    :returns: 按 key 排序的 ``(key, count)`` 元组。
    :raises Exception: 不主动抛出异常。
    """

    return tuple((key, counter[key]) for key in sorted(counter))


def _compact_audit_summary_from_rows(rows: tuple[EventLogRow, ...]) -> CompactAuditSummary:
    """从 compact EventLog rows 计算摘要。

    :param rows: compact EventLog rows。
    :returns: compact event 计数摘要。
    :raises Exception: payload JSON 非 object 时向上抛出。
    """

    request_trigger_sources = _compact_request_trigger_sources(rows)
    return CompactAuditSummary(
        requested_proactive=_compact_row_count(
            rows,
            event_type=CONTEXT_COMPACTION_REQUESTED,
            trigger_source=_COMPACT_TRIGGER_PROACTIVE,
            request_trigger_sources=request_trigger_sources,
        ),
        requested_reactive=_compact_row_count(
            rows,
            event_type=CONTEXT_COMPACTION_REQUESTED,
            trigger_source=_COMPACT_TRIGGER_REACTIVE,
            request_trigger_sources=request_trigger_sources,
        ),
        compacted_proactive=_compact_row_count(
            rows,
            event_type=CONTEXT_COMPACTED,
            trigger_source=_COMPACT_TRIGGER_PROACTIVE,
            request_trigger_sources=request_trigger_sources,
        ),
        compacted_reactive=_compact_row_count(
            rows,
            event_type=CONTEXT_COMPACTED,
            trigger_source=_COMPACT_TRIGGER_REACTIVE,
            request_trigger_sources=request_trigger_sources,
        ),
        failed_proactive=_compact_row_count(
            rows,
            event_type=CONTEXT_COMPACTION_FAILED,
            trigger_source=_COMPACT_TRIGGER_PROACTIVE,
            request_trigger_sources=request_trigger_sources,
        ),
        failed_reactive=_compact_row_count(
            rows,
            event_type=CONTEXT_COMPACTION_FAILED,
            trigger_source=_COMPACT_TRIGGER_REACTIVE,
            request_trigger_sources=request_trigger_sources,
        ),
        rejected_proactive=_compact_row_count(
            rows,
            event_type=CONTEXT_COMPACTION_ATTEMPT_REJECTED,
            trigger_source=_COMPACT_TRIGGER_PROACTIVE,
            request_trigger_sources=request_trigger_sources,
        ),
        rejected_reactive=_compact_row_count(
            rows,
            event_type=CONTEXT_COMPACTION_ATTEMPT_REJECTED,
            trigger_source=_COMPACT_TRIGGER_REACTIVE,
            request_trigger_sources=request_trigger_sources,
        ),
    )


def _compact_request_trigger_sources(rows: tuple[EventLogRow, ...]) -> Mapping[str, str]:
    """返回 compact request event id 到 trigger source 的映射。

    :param rows: compact EventLog rows。
    :returns: request event id 到 trigger source 的映射。
    :raises Exception: payload JSON 非 object 时向上抛出。
    """

    trigger_sources: dict[str, str] = {}
    for row in rows:
        if row.event_type != CONTEXT_COMPACTION_REQUESTED:
            continue
        trigger_source = _compact_row_trigger_source(row)
        if trigger_source is not None:
            trigger_sources[row.event_id] = trigger_source
    return trigger_sources


def _compact_row_count(
    rows: tuple[EventLogRow, ...],
    *,
    event_type: str,
    trigger_source: str,
    request_trigger_sources: Mapping[str, str],
) -> int:
    """统计指定 event type 与 trigger source 的 compact row 数。

    :param rows: compact EventLog rows。
    :param event_type: 目标 EventLog event type。
    :param trigger_source: 目标 trigger source。
    :param request_trigger_sources: request event id 到 trigger source 的映射。
    :returns: 命中 row 数。
    :raises Exception: payload JSON 非 object 时向上抛出。
    """

    return sum(
        1
        for row in rows
        if row.event_type == event_type
        and _compact_row_effective_trigger_source(row, request_trigger_sources) == trigger_source
    )


def _compact_row_effective_trigger_source(
    row: EventLogRow,
    request_trigger_sources: Mapping[str, str],
) -> str | None:
    """读取 compact row 的有效 trigger source。

    accepted / rejected / failed payload 可能不直接携带 ``trigger_source``，
    而是通过 ``operation_id`` 回指 request event id。

    :param row: compact EventLog row。
    :param request_trigger_sources: request event id 到 trigger source 的映射。
    :returns: trigger source；缺失或无法归因时返回 ``None``。
    :raises ValueError: payload JSON 不是 object 时抛出。
    """

    trigger_source = _compact_row_trigger_source(row)
    if trigger_source is not None:
        return trigger_source
    request_event_id = _compact_row_operation_id(row)
    if request_event_id is None:
        return None
    return request_trigger_sources.get(request_event_id)


def _compact_row_trigger_source(row: EventLogRow) -> str | None:
    """读取 compact EventLog row 的 trigger source。

    :param row: compact EventLog row。
    :returns: trigger source；缺失或非字符串时返回 ``None``。
    :raises ValueError: payload JSON 不是 object 时抛出。
    """

    return _compact_payload_str(_compact_row_payload(row), _PAYLOAD_FIELD_TRIGGER_SOURCE)


def _compact_row_operation_id(row: EventLogRow) -> str | None:
    """读取 compact EventLog row 的 operation id。

    :param row: compact EventLog row。
    :returns: operation id；缺失或非字符串时返回 ``None``。
    :raises ValueError: payload JSON 不是 object 时抛出。
    """

    return _compact_payload_str(_compact_row_payload(row), _PAYLOAD_FIELD_OPERATION_ID)


def _compact_row_payload(row: EventLogRow) -> Mapping[str, JsonValue]:
    """读取 compact EventLog row 的 JSON object payload。

    :param row: compact EventLog row。
    :returns: JSON object payload。
    :raises ValueError: payload JSON 不是 object 时抛出。
    """

    payload_json = cast(JsonValue, json.loads(row.payload_json))
    if not isinstance(payload_json, Mapping):
        raise ValueError(f"compact event payload must be object: event_id={row.event_id}")
    return cast(Mapping[str, JsonValue], payload_json)


def _compact_payload_str(payload: Mapping[str, JsonValue], field_name: str) -> str | None:
    """读取 compact payload 中的字符串字段。

    :param payload: compact event payload。
    :param field_name: 字段名。
    :returns: 字符串字段；字段缺失或类型不匹配时返回 ``None``。
    :raises Exception: 不主动抛出异常。
    """

    value = payload.get(field_name)
    if isinstance(value, str):
        return value
    return None


def _compact_payload_int(payload: Mapping[str, JsonValue], field_name: str) -> int | None:
    """读取 compact payload 中的整数字段。

    :param payload: compact event payload。
    :param field_name: 字段名。
    :returns: 整数字段；字段缺失、JSON 浮点数或其它类型不匹配时返回
        ``None``。
    :raises Exception: 不主动抛出异常。
    """

    value = payload.get(field_name)
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def _compact_payload_bool(payload: Mapping[str, JsonValue], field_name: str) -> bool | None:
    """读取 compact payload 中的布尔字段。

    :param payload: compact event payload。
    :param field_name: 字段名。
    :returns: 布尔字段；字段缺失或类型不匹配时返回 ``None``。
    :raises Exception: 不主动抛出异常。
    """

    value = payload.get(field_name)
    if isinstance(value, bool):
        return value
    return None


def _compact_payload_mapping(payload: Mapping[str, JsonValue], field_name: str) -> Mapping[str, JsonValue]:
    """读取 compact payload 中的 JSON object 字段。

    :param payload: compact event payload。
    :param field_name: 字段名。
    :returns: JSON object；字段缺失或类型不匹配时返回空 object。
    :raises Exception: 不主动抛出异常。
    """

    value = payload.get(field_name)
    if not isinstance(value, Mapping):
        return {}
    return cast(Mapping[str, JsonValue], value)


def _compact_payload_str_tuple(payload: Mapping[str, JsonValue], field_name: str) -> tuple[str, ...]:
    """读取 compact payload 中的字符串序列字段。

    :param payload: compact event payload。
    :param field_name: 字段名。
    :returns: 字符串元组；字段缺失或类型不匹配时返回空元组。
    :raises Exception: 不主动抛出异常。
    """

    value = payload.get(field_name)
    if not isinstance(value, Sequence) or isinstance(value, str):
        return ()
    values = cast(Sequence[JsonValue], value)
    return tuple(item for item in values if isinstance(item, str))


def _compact_normalized_diagnostic_suffix(diagnostic_ref: str) -> str:
    """返回 compact diagnostic ref 的归一化后缀。

    :param diagnostic_ref: Host diagnostic ref。
    :returns: 可用于 histogram 的诊断后缀；分段不足时返回原文。
    :raises Exception: 不主动抛出异常。
    """

    parts = diagnostic_ref.split(_DIAGNOSTIC_REF_SEPARATOR)
    if len(parts) > _DIAGNOSTIC_REF_SUFFIX_OFFSET:
        return _DIAGNOSTIC_REF_SEPARATOR.join(parts[_DIAGNOSTIC_REF_SUFFIX_OFFSET:])
    return diagnostic_ref


def _compact_manifest_presence(proposal_manifest_ref: str | None) -> str:
    """返回 proposal manifest ref 的存在性分类。

    :param proposal_manifest_ref: proposal manifest ref。
    :returns: ``present`` 或 ``missing``。
    :raises Exception: 不主动抛出异常。
    """

    if proposal_manifest_ref:
        return _COMPACT_MANIFEST_PRESENT
    return _COMPACT_MANIFEST_MISSING


def _compact_failure_stage(proposal_manifest_ref: str | None) -> str:
    """返回 rejected attempt 的失败阶段分类。

    :param proposal_manifest_ref: proposal manifest ref。
    :returns: 失败阶段分类。
    :raises Exception: 不主动抛出异常。
    """

    if proposal_manifest_ref:
        return _COMPACT_FAILURE_STAGE_PROPOSAL_OR_QUALITY
    return _COMPACT_FAILURE_STAGE_PREPARE_OR_MATERIAL


def _compact_log_insufficient(proposal_manifest_ref: str | None) -> str:
    """返回 rejected attempt 的日志不足分类。

    :param proposal_manifest_ref: proposal manifest ref。
    :returns: 日志不足分类；日志足够时返回 ``none``。
    :raises Exception: 不主动抛出异常。
    """

    if proposal_manifest_ref:
        return _COMPACT_LOG_INSUFFICIENT_NONE
    return _COMPACT_LOG_INSUFFICIENT_OFFENDING_BLOCK


def _compact_optional_text(value: str | int | bool | None) -> str:
    """格式化可选 compact 诊断值。

    :param value: 可选字符串、整数或布尔值。
    :returns: stdout 诊断文本。
    :raises Exception: 不主动抛出异常。
    """

    if value is None:
        return _COMPACT_NONE_VALUE
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)


def _print_compact_summary(options: OpenHostOptions) -> None:
    """打印 compact 观测摘要，不读取 artifact 内容。

    :param options: 本次 smoke 使用的 Host opener options。
    :returns: ``None``。
    :raises Exception: 不主动抛出异常。
    """

    compact_root = _compact_artifact_root(options)
    if compact_root is None:
        print(f"{_STDOUT_PREFIX_COMPACT_ARTIFACT_ROOT} <none>", flush=True)
        print(f"{_STDOUT_PREFIX_COMPACT_ARTIFACT_FILE_COUNT} 0", flush=True)
        return
    artifacts = _compact_artifact_files(options)
    print(f"{_STDOUT_PREFIX_COMPACT_ARTIFACT_ROOT} {compact_root}", flush=True)
    print(f"{_STDOUT_PREFIX_COMPACT_ARTIFACT_FILE_COUNT} {len(artifacts)}", flush=True)
    for path in artifacts[:_COMPACT_ARTIFACT_PRINT_LIMIT]:
        print(f"SMOKE COMPACT_ARTIFACT {path}", flush=True)


def _compact_artifact_root(options: OpenHostOptions) -> pathlib.Path | None:
    """读取 compact artifact root 配置。

    :param options: 本次 Host opener options。
    :returns: compact artifact root；未配置时返回 ``None``。
    :raises Exception: 不主动抛出异常。
    """

    if options.compactor_runner_baseline is None:
        return None
    return options.compactor_runner_baseline.compact_artifact_root


def _compact_artifact_files(options: OpenHostOptions) -> tuple[pathlib.Path, ...]:
    """列出 compact artifact 文件，不读取文件内容。

    :param options: 本次 Host opener options。
    :returns: compact artifact 文件路径元组。
    :raises Exception: 不主动抛出异常。
    """

    compact_root = _compact_artifact_root(options)
    if compact_root is None or not compact_root.exists():
        return ()
    return tuple(path for path in compact_root.rglob("*") if path.is_file())


def _format_provider_report(
    provider_id: str,
    spec_id: str,
    version_ref: str | None,
    tool_names: tuple[str, ...],
) -> str:
    """格式化 ToolsDiscovery provider report。

    :param provider_id: provider 自声明身份。
    :param spec_id: provider spec id。
    :param version_ref: provider 版本引用。
    :param tool_names: provider 产出的工具名。
    :returns: stdout 友好报告行。
    :raises Exception: 不主动抛出异常。
    """

    version = "<none>" if version_ref is None else version_ref
    names = "<none>" if not tool_names else ",".join(sorted(tool_names))
    return f"provider={provider_id},spec={spec_id},version={version},tools={names}"


def main(argv: Sequence[str] | None = None) -> int:
    """脚本入口。

    :param argv: 可选命令行参数；为 ``None`` 时使用进程参数。
    :returns: 进程退出码。
    :raises Exception: 不主动抛出；异常会被转换为退出码 1。
    """

    args = parse_args(sys.argv[1:] if argv is None else argv)
    configure(level=args.log_level)
    try:
        return asyncio.run(run_smoke(args, os.environ))
    except Exception as exc:
        print(f"SMOKE FAIL {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
