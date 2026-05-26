"""Host public 财报对话记忆场景 smoke 的纯脚本基础。

本模块是 Gateflow S1a 的 standalone skeleton：只固定 CLI、场景规格、
mock 财报事实、长输入构造和纯断言 helper，不打开 Host、不提交 followup、
不读取 durable store、EventLog、memory 表或 compact payload 内容。
"""

from __future__ import annotations

import argparse
import asyncio
import pathlib
import re
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Final, TypeAlias

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
_CLIENT_REQUEST_PREFIX: Final[str] = "manual-smoke-conversation-memory-scenarios"
_DEFAULT_USER_ID: Final[str] = "manual-smoke-user"
_UNKNOWN_FACT_KEY: Final[str] = "_UNKNOWN_FACT_KEY"
_STDOUT_SKELETON_READY: Final[str] = "SMOKE SCENARIO SKELETON READY"
_STDOUT_PRESSURE_DISABLED: Final[str] = "SMOKE PRESSURE disabled"
_STDOUT_TOOL_CALLS_BY_KEY: Final[str] = "SMOKE TOOL_CALLS_BY_KEY"
_NO_TOOL_SELECTION: Final[frozenset[str]] = frozenset()
_MOCK_PRESSURE_UNIT: Final[str] = (
    "DAYU_MEM_SCENARIO_PRESSURE_PAD 财报场景记忆压力文本，"
    "仅用于 public Host conversation memory smoke。"
)
_MOCK_PRESSURE_REPEAT: Final[int] = 128
_ANSWER_PREVIEW_CHARS: Final[int] = 240
_NORMALIZED_SPACE_PATTERN: Final[re.Pattern[str]] = re.compile(r"\s+")
_ASSERTION_FAILURE_PREFIX: Final[str] = "answer assertion failed"

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


ToolArgumentsValue: TypeAlias = str | bool
ToolPayloadValue: TypeAlias = str | bool


@dataclass(frozen=True, slots=True)
class SmokeArgs:
    """命令行参数。

    :param workspace_root: workspace / 项目根目录。
    :param scene_id: 需要装配的 scene id。
    :param execution_profile_id: 可选 execution profile 显式覆盖。
    :param host_runtime_id: 可选 Host runtime 显式覆盖。
    :param model_id: 可选模型显式覆盖。
    :param runner_option_hint_id: 可选 runner option hint 显式覆盖。
    :param log_level: 日志级别字符串。
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
    log_level: str
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


@dataclass(frozen=True, slots=True)
class MockToolCallRequest:
    """S1a standalone mock tool 调用请求。

    :param arguments: 工具调用参数。
    """

    arguments: Mapping[str, ToolArgumentsValue]


@dataclass(frozen=True, slots=True)
class MockToolExecutionContext:
    """S1a standalone mock tool 执行上下文。

    :param session_id: 调用所属 session id。
    """

    session_id: str


@dataclass(frozen=True, slots=True)
class MockToolResponse:
    """S1a standalone mock tool 返回值。

    :param known: 是否命中固定测试事实。
    :param fact_key: 命中的事实 key；未知事实使用固定 unknown key。
    :param marker: 命中的 marker；未知事实为空字符串。
    :param payload: 稳定 payload 字段。
    """

    known: bool
    fact_key: str
    marker: str
    payload: Mapping[str, ToolPayloadValue]


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
    """返回固定财报记忆事实的 standalone mock tool 骨架。"""

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
        request: MockToolCallRequest,
        context: MockToolExecutionContext,
    ) -> MockToolResponse:
        """执行 mock 财报事实查询。

        :param request: 工具调用请求。
        :param context: 工具执行上下文。
        :returns: 稳定 mock tool 响应。
        :raises Exception: 不主动抛出异常；未知事实返回 ``known=false``。
        """

        record = _find_fact_record(request.arguments)
        fact_key = record.key if record is not None else _UNKNOWN_FACT_KEY
        if self._tracked_session_id == context.session_id:
            self._call_count += 1
            self._calls_by_key.update((fact_key,))
        if record is None:
            return MockToolResponse(
                known=False,
                fact_key=_UNKNOWN_FACT_KEY,
                marker="",
                payload={
                    "known": False,
                    "fact_key": _UNKNOWN_FACT_KEY,
                    "pressure_blob": "",
                },
            )
        include_pressure = _argument_bool(
            request.arguments,
            _FIELD_INCLUDE_PRESSURE,
            default=False,
        )
        pressure_blob = _mock_pressure_blob(include_pressure, self._pressure_mode)
        payload = _fact_payload(record, pressure_blob=pressure_blob)
        return MockToolResponse(
            known=True,
            fact_key=record.key,
            marker=record.marker,
            payload=payload,
        )


def parse_args(argv: Sequence[str]) -> SmokeArgs:
    """解析命令行参数。

    :param argv: 不包含程序名的命令行参数序列。
    :returns: 结构化 smoke 参数。
    :raises SystemExit: 参数非法时由 ``argparse`` fail closed。
    """

    parser = argparse.ArgumentParser(
        description="Host public 财报对话记忆场景 smoke skeleton。"
    )
    parser.add_argument("--workspace-root", type=pathlib.Path, default=pathlib.Path.cwd())
    parser.add_argument("--scene-id", default=_DEFAULT_SCENE_ID)
    parser.add_argument("--execution-profile-id", default=None)
    parser.add_argument("--host-runtime-id", default=None)
    parser.add_argument("--model-id", default=None)
    parser.add_argument("--runner-option-hint-id", default=None)
    parser.add_argument("--log-level", default=_DEFAULT_LOG_LEVEL)
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
    return SmokeArgs(
        workspace_root=namespace.workspace_root,
        scene_id=namespace.scene_id,
        execution_profile_id=namespace.execution_profile_id,
        host_runtime_id=namespace.host_runtime_id,
        model_id=namespace.model_id,
        runner_option_hint_id=namespace.runner_option_hint_id,
        log_level=namespace.log_level,
        reuse_session=namespace.reuse_session,
        keep_workspace=namespace.keep_workspace,
        suite=SuiteMode(namespace.suite),
        long_rounds=namespace.long_rounds,
        pressure_mode=PressureMode(namespace.pressure_mode),
    )


def select_round_specs(args: SmokeArgs) -> tuple[RoundSpec, ...]:
    """按 suite 参数选择场景轮次规格。

    :param args: smoke 参数。
    :returns: 需要执行的场景轮次规格。
    :raises ValueError: long 轮数超出 20 到 25 时抛出。
    """

    if args.suite is SuiteMode.CORE:
        return _core_round_specs(args.pressure_mode)
    if args.suite is SuiteMode.LONG:
        return _long_round_specs(args.pressure_mode, args.long_rounds)
    core_specs = _core_round_specs(args.pressure_mode)
    long_specs = _long_round_specs(args.pressure_mode, args.long_rounds)
    return (*core_specs, *long_specs)


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


def _core_round_specs(pressure_mode: PressureMode) -> tuple[RoundSpec, ...]:
    """构造 core suite 场景规格。

    :param pressure_mode: 压力模式；S1a 中只影响 prompt 中的 skeleton 压力文本。
    :returns: core suite 的固定轮次规格。
    :raises Exception: 不主动抛出异常。
    """

    pressure_text = _user_pressure_placeholder(pressure_mode)
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
            f"按“资产 / 负债 / 息差”三组重排，不要调用工具，并追加压力观察文本：{pressure_text}。"
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
    pressure_mode: PressureMode,
    round_count: int,
) -> tuple[RoundSpec, ...]:
    """构造 long suite 场景规格。

    :param pressure_mode: 压力模式；S1a 中只影响用户压力占位文本。
    :param round_count: long suite 轮数，范围为 20 到 25。
    :returns: long suite 的轮次规格。
    :raises ValueError: ``round_count`` 超出 20 到 25 时抛出。
    """

    templates = _select_long_templates(round_count)
    expected_calls = 0
    specs: list[RoundSpec] = []
    for template in templates:
        if template.tool_enabled:
            expected_calls += 1
        tool_names = frozenset((_TOOL_NAME,)) if template.tool_enabled else _NO_TOOL_SELECTION
        pressure_text = (
            _user_pressure_placeholder(pressure_mode) if template.include_user_pressure else ""
        )
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
    arguments: Mapping[str, ToolArgumentsValue],
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


def _argument_str(arguments: Mapping[str, ToolArgumentsValue], key: str) -> str:
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
    arguments: Mapping[str, ToolArgumentsValue],
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
) -> Mapping[str, ToolPayloadValue]:
    """构造稳定 mock fact payload。

    :param record: 命中的 mock fact。
    :param pressure_blob: 可选压力文本。
    :returns: mock tool payload。
    :raises Exception: 不主动抛出异常。
    """

    payload: dict[str, ToolPayloadValue] = {
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


def _preview_text(content: str) -> str:
    """生成单行短预览文本。

    :param content: 原始文本。
    :returns: 不超过固定长度的单行预览。
    :raises Exception: 不主动抛出异常。
    """

    compact = _NORMALIZED_SPACE_PATTERN.sub(" ", content).strip()
    return compact[:_ANSWER_PREVIEW_CHARS]


async def _skeleton_probe_tool(args: SmokeArgs) -> MockToolResponse:
    """在 standalone skeleton 中探测 mock tool 可调用性。

    :param args: smoke 参数。
    :returns: 一次确定性 mock tool 响应。
    :raises Exception: 不主动抛出异常。
    """

    tool = MockFinanceMemoryTool(pressure_mode=args.pressure_mode)
    session_id = "s1a-skeleton-session"
    tool.track_session(session_id)
    return await tool(
        MockToolCallRequest(
            arguments={
                _FIELD_COMPANY: _COMPANY_MAOTAI,
                _FIELD_TICKER: _TICKER_MAOTAI,
                _FIELD_PERIOD: _PERIOD_2024H1,
                _FIELD_TOPIC: _TOPIC_REVENUE_PRODUCT_GROWTH,
                _FIELD_METRIC: _METRIC_MAOTAI_REVENUE,
                _FIELD_INCLUDE_PRESSURE: False,
            }
        ),
        MockToolExecutionContext(session_id=session_id),
    )


def main(argv: Sequence[str] | None = None) -> int:
    """脚本入口。

    :param argv: 可选命令行参数；为 ``None`` 时使用进程参数。
    :returns: 进程退出码。
    :raises SystemExit: CLI 参数非法时由 ``argparse`` 抛出。
    """

    args = parse_args(sys.argv[1:] if argv is None else argv)
    specs = select_round_specs(args)
    if args.pressure_mode is PressureMode.OFF:
        print(_STDOUT_PRESSURE_DISABLED)
    response = asyncio.run(_skeleton_probe_tool(args))
    print(
        f"{_STDOUT_SKELETON_READY} suite={args.suite.value} "
        f"rounds={len(specs)} scene_id={args.scene_id} "
        f"provider_id={_PROVIDER_ID} provider_spec_id={_PROVIDER_SPEC_ID} "
        f"provider_import={_PROVIDER_IMPORT_DISPLAY_PATH} tool={_TOOL_NAME} "
        f"tag={_TOOL_TAG} default_user={_DEFAULT_USER_ID} "
        f"slot_prefix={_DEFAULT_SLOT_KEY_PREFIX} client_prefix={_CLIENT_REQUEST_PREFIX} "
        f"probe_known={response.known} probe_key={response.fact_key} "
        f"preview={_preview_text(response.marker)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
