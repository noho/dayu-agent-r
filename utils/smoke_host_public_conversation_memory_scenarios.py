"""Host public 财报对话记忆场景 smoke 的 runtime flow。

本模块是 Gateflow S1b 的 Host public smoke runtime flow：通过
``ConfigLoader``、``resolve_runtime_locations``、``prepare_scene``、
``discover_service_tools``、``compose_open_host_options`` 与
``compose_submit_followup_request`` 完成 Service-like 装配，然后只使用
``open_host`` 返回的 public Host handle 执行多轮财报对话记忆场景。

脚本不读取 durable store、EventLog、memory 表、compact payload 内容或
private Host implementation；所有财报事实均来自 deterministic mock tool。
"""

from __future__ import annotations

import argparse
import asyncio
import os
import pathlib
import re
import sys
from collections import Counter
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from math import floor
from typing import Final
from uuid import uuid4

_PROJECT_ROOT: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from dayu.contracts import (
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
from dayu.host import (
    AuthorizationClaim,
    EnsureSessionRequest,
    FollowupBehavior,
    Host,
    HostCallContext,
    HostEvent,
    HostEventKind,
    OpenHostOptions,
    OperationContext,
    SessionSnapshot,
    SessionStatus,
    open_host,
)
from dayu.host.context_budget import DEFAULT_ESTIMATOR_CHARS_PER_TOKEN
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
    compose_open_host_options,
    compose_submit_followup_request,
    discover_service_tools,
)
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
_INITIAL_TOOL_CALL_COUNT: Final[int] = 0
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
_STDOUT_PREFIX_COMPACT_ARTIFACT_ROOT: Final[str] = "SMOKE COMPACT_ARTIFACT_ROOT"
_STDOUT_PREFIX_COMPACT_ARTIFACT_FILE_COUNT: Final[str] = (
    "SMOKE COMPACT_ARTIFACT_FILE_COUNT"
)
_NO_TOOL_SELECTION: Final[frozenset[str]] = frozenset()
_MOCK_PRESSURE_UNIT: Final[str] = (
    "DAYU_MEM_SCENARIO_PRESSURE_PAD 财报场景记忆压力文本，"
    "仅用于 public Host conversation memory smoke。"
)
_MOCK_PRESSURE_REPEAT: Final[int] = 128
_FINAL_PREVIEW_CHARS: Final[int] = 600
_TERMINAL_TIMEOUT_SECONDS: Final[float] = 600.0
_COMPACT_PRESSURE_TARGET_EXTRA_TOKENS: Final[int] = 16_384
_COMPACT_PRESSURE_HARD_MARGIN_TOKENS: Final[int] = 24_576
_COMPACT_PRESSURE_RESERVE_TOKENS: Final[int] = 160_000
_COMPACT_PRESSURE_MIN_PROMPT_TOKENS: Final[int] = 1_024
_COMPACT_PRESSURE_LARGE_WINDOW_TOKENS: Final[int] = 1_000_000
_PRESSURE_LINE_CHARS: Final[int] = 120
_COMPACT_ARTIFACT_PRINT_LIMIT: Final[int] = 10
_NORMALIZED_SPACE_PATTERN: Final[re.Pattern[str]] = re.compile(r"\s+")
_ASSERTION_FAILURE_PREFIX: Final[str] = "answer assertion failed"
_SOURCE_NAME: Final[str] = "utils.smoke_host_public_conversation_memory_scenarios"
_OPERATION_NAME: Final[str] = "host_public_conversation_memory_scenarios_smoke"
_OPERATION_KIND: Final[str] = "manual_smoke"
_BUSINESS_DOMAIN: Final[str] = "host"
_SCENARIO: Final[str] = "phase12_5_conversation_memory_scenarios_smoke"

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
    "DAYU_MEM_ASSERT_B_FOLLOW marker=DAYU_MEM_CATL_CFO_2024A_V1 "
    "referent=operating_cf largest_gap=经营性应付款增加"
)
_ASSERT_C_LONG: Final[str] = (
    "DAYU_MEM_ASSERT_C_LONG marker=DAYU_MEM_BYD_LONG_FACTOR2_V1 "
    "factor2=BATTERY_PRICE_PRESSURE_FACTOR_2"
)
_ASSERT_C_FOLLOW: Final[str] = (
    "DAYU_MEM_ASSERT_C_FOLLOW marker=DAYU_MEM_BYD_LONG_FACTOR2_V1 "
    "factor2=BATTERY_PRICE_PRESSURE_FACTOR_2"
)
_ASSERT_D_NIM: Final[str] = (
    "DAYU_MEM_ASSERT_D_NIM marker=DAYU_MEM_CMB_NIM_2024H1_V2 "
    "nim=1.88% yoy=-0.14pct asset_yield=3.45% liability_cost=1.74%"
)
_ASSERT_D_RETURN: Final[str] = (
    "DAYU_MEM_ASSERT_D_RETURN marker=DAYU_MEM_CMB_NIM_2024H1_V2 "
    "nim=1.88% yoy=-0.14pct consistent=yes"
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
    "请调用 get_mock_finance_memory_fact 查询美的集团 2024H1 毛利主题，"
    "metric=midea_margin_profile、include_pressure=true。回答时继续保留人民币百万元、"
    "内销/外销拆分和不使用估值倍数外推三条约束。"
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
    "请调用 get_mock_finance_memory_fact 查询美的集团 2024H1 费用主题，"
    "metric=midea_expense_profile、include_pressure=true。回答只基于工具结果和本会话既有约束。"
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
    "请调用 get_mock_finance_memory_fact 查询美的集团 2024H1 资产主题，"
    "metric=midea_asset_profile、include_pressure=true。回答中保持当前主体和三条口径约束。"
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
    "请调用 get_mock_finance_memory_fact 查询美的集团 2024H1 现金流主题，"
    "metric=midea_cashflow_profile、include_pressure=true。回答要把现金流主题接到收入、利润和资产讨论上。"
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
    "请调用 get_mock_finance_memory_fact 查询美的集团 2024H1 同行对比主题，"
    "metric=midea_peer_profile、include_pressure=true。回答只说明对比维度，不引入未确认的同行数值。"
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
    "原材料与产能利用率段：铝、钢、锂相关材料波动需要和库存周期一起观察，"
    "单一价格变化不能直接推出毛利率结论。",
)


class SuiteMode(StrEnum):
    """场景套件模式。

    :param CORE: 只生成 core 场景规格。
    :param LONG: 只生成 long 场景规格。
    :param ALL: 在同一逻辑序列中先生成 core 再生成 long 场景规格。
    """

    CORE = "core"
    LONG = "long"
    ALL = "all"


class PressureMode(StrEnum):
    """压力注入模式。

    :param AUTO: 后续 Host 实现按预算自适应注入压力。
    :param OFF: 不注入人工压力文本。
    """

    AUTO = "auto"
    OFF = "off"


@dataclass(frozen=True, slots=True)
class SmokeArgs:
    """命令行参数。

    :param workspace_root: workspace / 项目根目录。
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


@dataclass(frozen=True, slots=True)
class RoundSpec:
    """单轮场景规格。

    :param label: 轮次标签。
    :param prompt: 用户输入文本。
    :param tool_names: 本轮允许使用的工具名集合。
    :param expected_tool_calls_after_round: 本轮结束后的期望工具调用总数。
    :param hard_answer_contains: 最终回答必须包含的文本片段。
    :param hard_answer_forbidden: 最终回答禁止包含的文本片段。
    :param soft_answer_contains: 最终回答建议包含的观察片段。
    :param print_calls_by_key: 是否在本轮后打印 calls_by_key 摘要。
    """

    label: str
    prompt: str
    tool_names: frozenset[str]
    expected_tool_calls_after_round: int
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

    def set_pressure_mode(self, pressure_mode: PressureMode) -> None:
        """设置本次 smoke 的压力注入模式。

        provider callable 本身不接收 CLI 参数，因此 runtime assembly 后由
        ``run_smoke`` 把命令行 pressure mode 注入真实 callable 实例。

        :param pressure_mode: 压力注入模式。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self._pressure_mode = pressure_mode

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

    smoke_tool = MockFinanceMemoryTool(pressure_mode=PressureMode.AUTO)
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


def parse_args(argv: Sequence[str]) -> SmokeArgs:
    """解析命令行参数。

    :param argv: 不包含程序名的命令行参数序列。
    :returns: 结构化 smoke 参数。
    :raises SystemExit: 参数非法时由 ``argparse`` fail closed。
    """

    parser = argparse.ArgumentParser(
        description="Host public 财报对话记忆场景 smoke。"
    )
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
        default=SuiteMode.CORE.value,
    )
    parser.add_argument(
        "--long-rounds",
        type=_parse_long_rounds,
        default=_DEFAULT_LONG_ROUNDS,
    )
    parser.add_argument(
        "--pressure-mode",
        choices=tuple(item.value for item in PressureMode),
        default=PressureMode.AUTO.value,
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
    return SmokeArgs(
        workspace_root=_resolve_workspace_root(workspace_root_text),
        scene_id=scene_id,
        execution_profile_id=execution_profile_id,
        host_runtime_id=host_runtime_id,
        model_id=model_id,
        runner_option_hint_id=runner_option_hint_id,
        log_level=LogLevel[log_level_text],
        reuse_session=reuse_session,
        keep_workspace=keep_workspace,
        suite=SuiteMode(suite_text),
        long_rounds=long_rounds,
        pressure_mode=PressureMode(pressure_mode_text),
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
    return (
        _DEFAULT_WORKSPACE_PARENT
        / f"{_DEFAULT_WORKSPACE_PREFIX}-{uuid4().hex[:12]}"
    ).resolve()


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

    if suite is SuiteMode.CORE:
        return _core_round_specs(user_pressure_text)
    if suite is SuiteMode.LONG:
        return _long_round_specs(user_pressure_text, long_rounds)
    core_specs = _core_round_specs(user_pressure_text)
    long_specs = _long_round_specs(
        user_pressure_text,
        long_rounds,
        base_expected_calls=_final_expected_tool_calls(core_specs),
    )
    return (*core_specs, *long_specs)


def _final_expected_tool_calls(specs: Sequence[RoundSpec]) -> int:
    """读取一组轮次规格结束后的累计工具调用数。

    :param specs: 已生成的轮次规格序列。
    :returns: 最后一轮结束后的期望工具调用总数；空序列返回初始计数。
    :raises Exception: 不主动抛出异常。
    """

    if not specs:
        return _INITIAL_TOOL_CALL_COUNT
    return specs[-1].expected_tool_calls_after_round


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
            raise AssertionError(
                f"{_ASSERTION_FAILURE_PREFIX}: label={label} missing={item}"
            )
    for item in forbidden:
        blocked = normalize_answer(item)
        if blocked in normalized:
            raise AssertionError(
                f"{_ASSERTION_FAILURE_PREFIX}: label={label} forbidden={item}"
            )


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
            1,
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
            1,
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
            2,
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
            2,
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
                f"回答末尾输出 {_ASSERT_B_CFO}。"
            ),
            tool,
            3,
            (_MARKER_CATL_CASHFLOW, _VALUE_CATL_OPERATING_CF, _VALUE_CATL_LARGEST_GAP),
            (),
            (),
            True,
        ),
        RoundSpec(
            _LABEL_CORE_B2,
            f"这个数和净利润比，差异在哪个项目最大？不要调用工具。最后输出 {_ASSERT_B_FOLLOW}。",
            _NO_TOOL_SELECTION,
            3,
            (_MARKER_CATL_CASHFLOW, _VALUE_CATL_LARGEST_GAP),
            (),
            (),
            False,
        ),
        RoundSpec(
            _LABEL_CORE_B3,
            "投资活动的支出主要花在什么上？如果当前会话没有确认过，不要编造。",
            _NO_TOOL_SELECTION,
            3,
            (),
            (),
            ("没有确认",),
            False,
        ),
        RoundSpec(
            _LABEL_CORE_C1,
            "我准备分析比亚迪 2024H1 毛利率结构变化。后续只根据我贴的原文回答。",
            _NO_TOOL_SELECTION,
            3,
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
            3,
            (),
            (),
            (_MARKER_BYD_LONG_FACTOR2, _BYD_FACTOR2_MARKER),
            False,
        ),
        RoundSpec(
            _LABEL_CORE_C3,
            f"第二个因素能再展开讲讲吗？不要调用工具。最后单独输出 {_ASSERT_C_FOLLOW}。",
            _NO_TOOL_SELECTION,
            3,
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
            4,
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
            4,
            (),
            (),
            (_MARKER_CMB_NIM, _VALUE_CMB_NIM, _VALUE_CMB_NIM_YOY),
            False,
        ),
        RoundSpec(
            _LABEL_CORE_D3,
            "不调用工具。招商银行刚才讨论中不良率是多少？如果会话里没有确认，明确说明未确认。",
            _NO_TOOL_SELECTION,
            4,
            (),
            (),
            (_VALUE_CMB_NPL_RATIO,),
            False,
        ),
        RoundSpec(
            _LABEL_CORE_D4,
            f"回到刚才息差讨论，净息差具体数值和同比变化再确认，最后输出 {_ASSERT_D_RETURN}。",
            _NO_TOOL_SELECTION,
            4,
            (_MARKER_CMB_NIM, _VALUE_CMB_NIM, _VALUE_CMB_NIM_YOY),
            (),
            (),
            False,
        ),
    )


def _long_round_specs(
    user_pressure_text: str,
    round_count: int,
    *,
    base_expected_calls: int = _INITIAL_TOOL_CALL_COUNT,
) -> tuple[RoundSpec, ...]:
    """构造 long suite 场景规格。

    :param user_pressure_text: 已按当前模式生成的用户侧压力文本。
    :param round_count: long suite 轮数，范围为 20 到 25。
    :param base_expected_calls: long suite 首轮之前已经累计的工具调用次数。
    :returns: long suite 的轮次规格。
    :raises ValueError: ``round_count`` 超出 20 到 25 时抛出。
    """

    templates = _select_long_templates(round_count)
    expected_calls = base_expected_calls
    specs: list[RoundSpec] = []
    for template in templates:
        if template.tool_enabled:
            expected_calls += 1
        tool_names = frozenset((_TOOL_NAME,)) if template.tool_enabled else _NO_TOOL_SELECTION
        pressure_text = user_pressure_text if template.include_user_pressure else ""
        specs.append(
            RoundSpec(
                label=template.label,
                prompt=template.prompt_template.format(auto_user_pressure=pressure_text),
                tool_names=tool_names,
                expected_tool_calls_after_round=expected_calls,
                hard_answer_contains=template.hard_contains,
                hard_answer_forbidden=template.hard_forbidden,
                soft_answer_contains=(),
                print_calls_by_key=template.tool_enabled,
            )
        )
    return tuple(specs)


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

    head = (
        f"{_BYD_LONG_INPUT_HEAD_ANCHOR}：出口车型结构是本段原文固定 anchor，"
        "后续回答只能依据该原文。"
    )
    middle = (
        f"{_BYD_LONG_INPUT_MIDDLE_ANCHOR}：动力电池价格压力是第二因素固定 anchor，"
        "用于验证长输入 minimum-preserve。"
    )
    tail = (
        f"{_BYD_LONG_INPUT_TAIL_ANCHOR}：规模效应是第三因素固定 anchor，"
        "用于验证结尾信息可被引用。"
    )
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

    assembly = _prepare_runtime_assembly(args, env=env)
    assembly.smoke_tool.set_pressure_mode(args.pressure_mode)
    specs = _runtime_round_specs(args, assembly.options)
    _print_assembly_diagnostics(assembly.diagnostics, assembly.options)
    smoke_run_id = _new_smoke_run_id()

    if args.pressure_mode is PressureMode.OFF:
        print(_STDOUT_PRESSURE_DISABLED)
    _print_compact_pressure_plan(assembly.options, args.pressure_mode)
    print("SMOKE START Host public conversation memory scenario smoke")
    print(f"SMOKE WORKSPACE_ROOT {args.workspace_root}")
    print(f"SMOKE RUN_ID {smoke_run_id}")
    print(f"SMOKE SCENE_ID {args.scene_id}")
    print(f"SMOKE SUITE {args.suite.value} rounds={len(specs)}")
    print("SMOKE CONTRACT open_host -> ensure_session -> submit_followup -> watch -> get_session")
    print(f"SMOKE LOG_LEVEL {args.log_level.name}")

    async with open_host(assembly.options) as host:
        session = await host.ensure_session(_ensure_request(args, smoke_run_id))
        assembly.smoke_tool.track_session(session.session_id)
        watcher = host.watch_session_events(session.session_id)
        print(f"SMOKE SESSION session_id={session.session_id}")
        _assert_session_open(session, label="ensure-session")
        _print_session_observation(session, label="ensure-session")

        for index, spec in enumerate(specs, start=1):
            result = await _run_round(
                host=host,
                watcher=watcher,
                session_id=session.session_id,
                spec=spec,
                client_request_id=_round_client_request_id(smoke_run_id, index),
                scene_inputs=assembly.scene_inputs,
            )
            _print_round(result)
            _assert_round_result(result, assembly.smoke_tool, spec)
            snapshot = await host.get_session(session.session_id)
            _assert_session_open(snapshot, label=spec.label)
            _print_session_observation(snapshot, label=spec.label)
            if spec.print_calls_by_key:
                print(calls_by_key_summary(assembly.smoke_tool.calls_by_key))

        final_session = await host.get_session(session.session_id)
        _assert_session_open(final_session, label="final")
        print(f"SMOKE SESSION_STATUS {final_session.status.value}")

    print(calls_by_key_summary(assembly.smoke_tool.calls_by_key))
    _print_compact_summary(assembly.options)
    print("SMOKE PASS public Host conversation memory scenario smoke")
    if args.keep_workspace:
        print("SMOKE WORKSPACE_KEPT true")
    else:
        print("SMOKE WORKSPACE_KEPT true  # smoke never deletes Host/runtime artifacts")
    return 0


def _prepare_runtime_assembly(
    args: SmokeArgs, *, env: Mapping[str, str]
) -> RuntimeAssemblyResult:
    """执行 Host 调用前的 runtime/config/tools/scene typed assembly。

    :param args: smoke 参数。
    :param env: 环境变量映射。
    :returns: 完整 runtime assembly 结果。
    :raises ValueError: 配置、工具发现、scene 或 override 无法映射时抛出。
    """

    locations = resolve_runtime_locations(
        project_root=args.workspace_root,
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
            context_slot_values={},
            available_tools=SceneToolCatalog.from_tool_bundle(
                discovered_tools.tool_bundle
            ),
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
    return RuntimeAssemblyResult(
        options=assembly.options,
        scene_inputs=scene_inputs,
        diagnostics=assembly.diagnostics,
        effective_tool_bundle=assembly.effective_tool_bundle,
        smoke_tool=smoke_tool,
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

    discovered = discover_service_tools(config, workspace_root=workspace_root)
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
                    location=PythonImportPathProvider(
                        import_path=_PROVIDER_IMPORT_DISPLAY_PATH
                    ),
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
    :raises RuntimeError: pressure auto 需要 context budget policy 但缺失时抛出。
    """

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
    :raises RuntimeError: auto 模式需要 context budget policy 但缺失时抛出。
    """

    if pressure_mode is PressureMode.OFF:
        return ""
    return _compact_pressure_padding(options)


def _ensure_request(args: SmokeArgs, smoke_run_id: str) -> EnsureSessionRequest:
    """构造 ensure session 请求。

    :param args: smoke 参数。
    :param smoke_run_id: 本次 smoke 批次 id。
    :returns: EnsureSessionRequest。
    :raises ValueError: 字段非法时由底层抛出。
    """

    slot_key = (
        _DEFAULT_SLOT_KEY_PREFIX
        if args.reuse_session
        else f"{_DEFAULT_SLOT_KEY_PREFIX}-{smoke_run_id}"
    )
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
        authorization_claims=(
            AuthorizationClaim(name="role", value="manual-smoke"),
        ),
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
            f"round {spec.label} terminal kind is {event.kind.value}; "
            f"run_id={accepted.accepted_run_id}"
        )
    if event.final_answer is None or event.final_answer.content.strip() == "":
        raise RuntimeError(f"round {spec.label} returned empty final answer")
    return RoundResult(label=spec.label, run_id=accepted.accepted_run_id, event=event)


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
    summary_digest = (
        terminal_summary.summary_digest if terminal_summary is not None else None
    )
    message = _safe_summary_text(event.error_message)
    terminal_status = (
        event.terminal_status.value
        if event.terminal_status is not None
        else "unknown"
    )
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


async def _next_terminal_for_run(
    iterator: AsyncIterator[HostEvent], run_id: str
) -> HostEvent:
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
) -> None:
    """按 RoundSpec 执行本轮硬断言与软观察。

    :param result: 单轮运行摘要。
    :param smoke_tool: tracked session 的 mock tool 实例。
    :param spec: 本轮场景规格。
    :returns: ``None``。
    :raises RuntimeError: 工具调用次数不符合预期时抛出。
    :raises AssertionError: 回答硬断言失败时抛出。
    """

    _assert_tool_call_count(
        smoke_tool,
        expected=spec.expected_tool_calls_after_round,
        label=spec.label,
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
            f"{_STDOUT_PREFIX_SOFT_OBSERVE} label={spec.label} "
            f"status=soft-missing markers={','.join(missing_soft)}"
        )


def _assert_tool_call_count(
    smoke_tool: MockFinanceMemoryTool, *, expected: int, label: str
) -> None:
    """断言 tracked session 内工具调用次数。

    :param smoke_tool: effective ToolBundle 中恢复出的 mock 工具实例。
    :param expected: 期望调用次数。
    :param label: 当前轮次标签。
    :returns: ``None``。
    :raises RuntimeError: 工具调用次数不符合预期时抛出。
    """

    if smoke_tool.call_count != expected:
        raise RuntimeError(
            f"{label} tool call count expected {expected}, "
            f"got {smoke_tool.call_count}"
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
    pressure_reserve_tokens = _compact_pressure_reserve_tokens(
        context_window_size=policy.context_window_size
    )
    tool_pressure_tokens = _tool_pressure_estimated_tokens()
    prompt_tokens = max(
        _COMPACT_PRESSURE_MIN_PROMPT_TOKENS,
        target_tokens - pressure_reserve_tokens - tool_pressure_tokens,
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


def _compact_pressure_reserve_tokens(*, context_window_size: int) -> int:
    """计算 pressure prompt 与工具压力之外预留的估算 token。

    :param context_window_size: 当前模型上下文窗口 token 数。
    :returns: prompt 与工具压力之外预留 token 数。
    :raises Exception: 不主动抛出异常。
    """

    if context_window_size >= _COMPACT_PRESSURE_LARGE_WINDOW_TOKENS:
        return _COMPACT_PRESSURE_RESERVE_TOKENS
    return _COMPACT_PRESSURE_RESERVE_TOKENS


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

    return (
        char_count + DEFAULT_ESTIMATOR_CHARS_PER_TOKEN - 1
    ) // DEFAULT_ESTIMATOR_CHARS_PER_TOKEN


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

    print("SMOKE ASSEMBLY_MODE runtime")
    print(f"SMOKE ASSEMBLY config_overlay={diagnostics.config_overlay_dir}")
    print(f"SMOKE ASSEMBLY prompt_asset_root={diagnostics.prompt_asset_root}")
    print(f"SMOKE ASSEMBLY scene_manifest_root={diagnostics.scene_manifest_root}")
    print(f"SMOKE ASSEMBLY host_runtime_id={diagnostics.host_runtime_id}")
    print(f"SMOKE ASSEMBLY execution_profile_id={diagnostics.execution_profile_id}")
    print(f"SMOKE ASSEMBLY model_id={diagnostics.model_id} source={diagnostics.model_source}")
    print(
        "SMOKE ASSEMBLY runner_option_hint_id="
        f"{diagnostics.runner_option_hint_id} "
        f"source={diagnostics.runner_option_hint_source}"
    )
    print(f"SMOKE ASSEMBLY compactor_model_id={diagnostics.compactor_model_id}")
    print(
        "SMOKE ASSEMBLY compactor_runner_option_hint_id="
        f"{diagnostics.compactor_runner_option_hint_id}"
    )
    print(f"SMOKE ASSEMBLY lane_name={diagnostics.lane_name}")
    if diagnostics.tool_provider_reports:
        for report in diagnostics.tool_provider_reports:
            print(f"SMOKE ASSEMBLY tool_provider_report={report}")
    else:
        print("SMOKE ASSEMBLY tool_provider_report=<none>")
    print(f"SMOKE ASSEMBLY tool_selection={diagnostics.tool_selection}")
    print(
        "SMOKE ASSEMBLY policy_refs="
        f"context_budget:{diagnostics.context_budget_policy_ref},"
        f"tool_truncation:{diagnostics.tool_truncation_policy}"
    )
    print_duplicate_governance_diagnostics(options)
    print(
        "SMOKE ASSEMBLY agent_policy_sources="
        f"{','.join(diagnostics.agent_policy_sources)}"
    )
    print(
        "SMOKE ASSEMBLY provider_extension_status="
        f"ordinary:{diagnostics.ordinary_provider_extension_status},"
        f"compactor:{diagnostics.compactor_provider_extension_status}"
    )


def _print_compact_pressure_plan(
    options: OpenHostOptions,
    pressure_mode: PressureMode,
) -> None:
    """打印 compact pressure 摘要，不输出完整 pressure prompt。

    :param options: 本次 smoke 使用的 Host opener options。
    :param pressure_mode: 压力注入模式。
    :returns: ``None``。
    :raises Exception: 不主动抛出异常。
    """

    if pressure_mode is PressureMode.OFF:
        print("SMOKE COMPACT_PRESSURE skipped pressure_mode=off")
        return
    policy = options.context_budget_policy
    if policy is None:
        print("SMOKE COMPACT_PRESSURE disabled")
        return
    soft_threshold_tokens = _threshold_tokens(
        policy.context_window_size,
        policy.soft_threshold_context_ratio,
    )
    hard_threshold_tokens = _threshold_tokens(
        policy.context_window_size,
        policy.hard_threshold_context_ratio,
    )
    prompt_chars = len(_compact_pressure_padding(options))
    estimated_prompt_tokens = _estimate_chars_as_tokens(prompt_chars)
    estimated_total_pressure_tokens = (
        estimated_prompt_tokens + _tool_pressure_estimated_tokens()
    )
    print(
        "SMOKE COMPACT_PRESSURE "
        f"context_window_tokens={policy.context_window_size} "
        f"soft_threshold_tokens={soft_threshold_tokens} "
        f"hard_threshold_tokens={hard_threshold_tokens} "
        f"tool_pressure_tokens={_tool_pressure_estimated_tokens()} "
        f"prompt_pressure_chars={prompt_chars} "
        f"estimated_prompt_tokens={estimated_prompt_tokens} "
        f"estimated_total_pressure_tokens={estimated_total_pressure_tokens}"
    )


def _print_round(result: RoundResult) -> None:
    """打印一轮运行摘要。

    :param result: 轮次结果。
    :returns: ``None``。
    :raises Exception: 不主动抛出异常。
    """

    content = _final_answer_content(result)
    preview = content[:_FINAL_PREVIEW_CHARS]
    terminal = (
        result.event.terminal_status.value
        if result.event.terminal_status is not None
        else "none"
    )
    print(
        f"{_STDOUT_PREFIX_ROUND_DONE} "
        f"label={result.label} run_id={result.run_id} "
        f"event_id={result.event.event_id} "
        f"event_sequence={result.event.event_sequence} "
        f"terminal={terminal}"
    )
    print(f"{_STDOUT_PREFIX_FINAL_PREVIEW} label={result.label} content={preview!r}")


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
        f"queued_run_count={queued_count}"
    )


def _print_compact_summary(options: OpenHostOptions) -> None:
    """打印 compact 观测摘要，不读取 artifact 内容。

    :param options: 本次 smoke 使用的 Host opener options。
    :returns: ``None``。
    :raises Exception: 不主动抛出异常。
    """

    compact_root = (
        options.compactor_runner_baseline.compact_artifact_root
        if options.compactor_runner_baseline is not None
        else None
    )
    if compact_root is None:
        print(f"{_STDOUT_PREFIX_COMPACT_ARTIFACT_ROOT} <none>")
        print(f"{_STDOUT_PREFIX_COMPACT_ARTIFACT_FILE_COUNT} 0")
        return
    artifacts = (
        tuple(path for path in compact_root.rglob("*") if path.is_file())
        if compact_root.exists()
        else ()
    )
    print(f"{_STDOUT_PREFIX_COMPACT_ARTIFACT_ROOT} {compact_root}")
    print(f"{_STDOUT_PREFIX_COMPACT_ARTIFACT_FILE_COUNT} {len(artifacts)}")
    for path in artifacts[:_COMPACT_ARTIFACT_PRINT_LIMIT]:
        print(f"SMOKE COMPACT_ARTIFACT {path}")


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
        print(f"SMOKE FAIL {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
