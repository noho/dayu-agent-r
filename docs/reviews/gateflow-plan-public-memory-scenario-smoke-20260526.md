# Host Public Conversation Memory Scenario Smoke 计划

## 0. Gate 与角色

- 当前 gate：plan。
- 角色：planning worker only，不是 controller。
- Work unit：新增 public Host conversation memory 场景 smoke。
- Repository：`/Users/leo/workspace/dayu-agent-r`。
- Branch：`feat/phase-12-5-conversation-memory-optimize`。
- 本 artifact 只给后续 implementation / review worker 使用；本 gate 不实施、不提交、不推送、不开 PR。

## 1. 动机判断

动机成立，但用户给定的旧项目路径不能照搬。

旧参考文档 `/Users/leo/workspace/dayu-agent/docs/conversation_memory_test.md` 的 A-E 组覆盖的是交互式 CLI、真实财报语料、日志、tool trace 和 SQLite 表内查。当前 work unit 的硬边界是 Host public API smoke，因此不能直接读取 `pinned_state`、`confirmed_facts`、memory 表、EventLog 或 compact payload 内容。可维护方案是新增一个独立“场景 smoke”，用 deterministic mock finance tools 和用户可见回答断言，模拟旧文档的常见记忆场景；内部 memory 结构只作为被 public 行为间接验证的实现细节。

现有 `utils/smoke_host_public_conversation_memory.py` 已经是最小四轮 continuity smoke，应继续保留为快速入口。新脚本负责更广的场景矩阵，避免把最小 smoke 变慢、变脆或改变既有语义。

## 2. Non-goals

- 不修改 Host public API、Host durable schema、memory projection、compaction state machine 或 Fins 仓储。
- 不读取 `.dayu/host/dayu_host.db`、EventLog、memory table、conversation transcript、compact material 或 compact artifact 内容。
- 不调用真实 Fins 工具；所有财务事实都来自 deterministic mock tool。
- 不把旧项目测试文档中的实现假设、字段名、日志文案当作 dayu-agent-r 的契约。
- 不让现有最小 smoke 承担 A-E 全场景验证；它只保持当前四轮最小 continuity 语义。
- 不把 LLM 自然语言判断变成脆弱语义 parser；硬断言只检查可归一化的 marker、数值、工具调用次数、terminal 状态和 public snapshot。

## 3. 直接证据

- `utils/smoke_host_public_conversation_memory.py` 当前脚本模块 docstring 明确只通过 `open_host`、`ensure_session`、`submit_followup`、`watch_session_events`、`get_session` 与必要时 `get_run` 观察，不读取 durable store、EventLog、memory 表或 compact payload 内容。
- `utils/smoke_host_public_conversation_memory.py` 当前固定四轮：Round 1 工具确认招商银行 2024H1 息差事实，Round 2 禁用工具并施加 pressure，Round 3 topic shift，Round 4 禁用工具核对 marker、`1.88%`、`-0.14pct`。它已覆盖旧文档 D 组的一小段核心 intent，但不覆盖 A/B/C/E。
- `utils/smoke_host_public_multiturn.py` 展示了 public boundary style：Service-like assembly 后只使用 Host handle 的 public 方法；mock tool 通过 `ToolsDiscovery` / `manual-smoke` tag 注入；pressure padding 按 `OpenHostOptions.context_budget_policy` 自适应估算。
- `dayu/host/api.py` 的 `Host` protocol 暴露 public 方法：`ensure_session`、`create_session`、`get_session`、`get_run`、`submit_followup`、`retry_run`、`replay_run`、`resolve_wait`、`cancel_run`、`cancel_session_runs`、`close_session`、`watch_session_events`、`close`。其中本 smoke 只需要 `ensure_session`、`submit_followup`、`watch_session_events`、`get_session`，失败摘要可用 `get_run`。
- `dayu/host/api.py` 的 `SessionSnapshot` 只暴露 `session_id`、`status`、`slot`、`active_run_id`、`queued_run_ids`、`timeline_cursor`，没有 public `pinned_state` 或 memory snapshot 字段。因此 pinned_state 演进只能通过后续回答是否保持主体、期间、口径和值做代理验证。
- `dayu/config/prompts/manifests/smoke_host_public_conversation_memory.json` 和 scene prompt 已存在最小 smoke 配置；新增场景 smoke 应使用独立 scene id，避免改变现有入口行为。
- `tests/runtime/test_scene_assets_migration.py` 对所有 manifest 做装配检查，并在 `_OLD_SCENE_MAX_ITERATIONS` 中列出当前普通 scene 的 `max_iterations`。新增 manifest 后需要同步该测试或明确保持无 `agent_policy`。
- `README.md` 第 5 节已有手工 smoke 说明，当前 5.2 是最小 conversation memory smoke；新增入口属于根 README 用户手册职责。

## 4. 文件范围

新增文件：

- `utils/smoke_host_public_conversation_memory_scenarios.py`
  - 新场景 smoke 脚本。
  - 默认 scene id：`smoke_host_public_conversation_memory_scenarios`。
  - 默认 suite：`core`。
- `dayu/config/prompts/manifests/smoke_host_public_conversation_memory_scenarios.json`
  - 新 scene manifest。
- `dayu/config/prompts/scenes/smoke_host_public_conversation_memory_scenarios.md`
  - 新 scene prompt。
- `tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py`
  - 轻量 assembly / 参数 / pressure / mock tool 单测，不跑真实 LLM。

允许修改的既有文件：

- `README.md`
  - 在手工 smoke 章节新增“Host public 财报对话记忆场景 smoke”说明；现有最小 smoke 小节保留。
- `tests/README.md`
  - 如新增 assembly 测试，补充 runtime smoke assembly 测试说明。
- `tests/runtime/test_scene_assets_migration.py`
  - 将新 scene 加入 `_OLD_SCENE_MAX_ITERATIONS`，建议值 `32`；或若 manifest 不声明 `agent_policy`，则无需加入。推荐声明 `max_iterations=32`，因为 long suite 会复用同一 scene，多轮与工具调用需要明确上限。

禁止修改：

- `utils/smoke_host_public_conversation_memory.py`
  - 本 work unit 不做 shared helper extraction；保持现有最小 smoke 可用且语义不变。
  - 如果 implementation worker 认为无法避免抽取，必须停止并交回 controller 裁决，不得自行改写最小 smoke。
- `dayu/host/**`、`dayu/fins/**`、`dayu/engine/**`、`dayu/runtime/**`
  - 本 work unit 不改生产路径。

## 5. Public API 调用流

新脚本运行期 Host 调用必须保持与现有 public smoke 同一边界：

1. 解析 CLI 参数为 `SmokeArgs`。
2. 用 `resolve_runtime_locations`、`ConfigLoader`、`discover_service_tools`、内置 smoke provider、`prepare_scene`、`compose_open_host_options` 完成 Host 打开前 typed assembly。
3. `async with open_host(assembly.options) as host:`。
4. `session = await host.ensure_session(...)`；默认 fresh slot，`--reuse-session` 才复用稳定 slot。
5. `watcher = host.watch_session_events(session.session_id)`。
6. 每轮用 `compose_submit_followup_request(...)` 构造 request，再调用 `await host.submit_followup(session_id, request)`。
7. 从 `watcher` 等待目标 `run_id` 的 terminal `HostEvent`。
8. 每轮后调用 `await host.get_session(session_id)` 断言 session 未关闭，并打印 public snapshot 摘要。
9. 只有 terminal failure 摘要需要时允许 `await host.get_run(run_id)`，用于打印脱敏 `terminal_result_summary` ref / digest。

Suite 编排必须统一在一个 Host lifecycle 中完成：

- `--suite core`：单次 `open_host`、单次 `ensure_session`，执行 `_core_round_specs(...)`。
- `--suite long`：单次 `open_host`、单次 `ensure_session`，执行 `_long_round_specs(...)`。
- `--suite all`：单次 `open_host`、单次 `ensure_session`，先构造 core specs，再构造 long specs，并用 `(*core_specs, *long_specs)` 拼接后顺序执行。不得拆成两次 `open_host`，也不得依赖 `--reuse-session` 在两个 Host block 之间恢复 continuity。这样 core 和 long 自然共享同一个 watcher、session、tool instance 计数与 public memory history。

禁止的运行期读取：

- SQLite / durable store / EventLog / memory projection reader。
- compact material / compact payload 内容。
- compact artifact 文件内容。只能打印 artifact root 和文件数量，作为人工观察线索。
- private Host implementation object、scheduler、command handle、memory repair helper。

## 6. CLI 设计

保留现有 smoke 常用参数：

- `--workspace-root`
- `--scene-id`
- `--execution-profile-id`
- `--host-runtime-id`
- `--model-id`
- `--runner-option-hint-id`
- `--log-level`
- `--reuse-session`
- `--keep-workspace`

新增参数：

- `--suite {core,long,all}`，默认 `core`。
  - `core`：跑 A/B/C/D 的 compact 版本，目标 12-16 轮，适合日常手工验证。
  - `long`：只跑 E 长会话稳定性，默认 25 轮。
  - `all`：在同一个 `open_host` block、同一个 session 内先跑 `core` 再跑 `long`，以最大化 public memory continuity 压力。
- `--long-rounds <int>`，默认 `25`，允许范围 `20..25`；低于 20、高于 25、0、负数或非整数时 argparse fail closed。设置小于 25 时执行 `L01..L(N-1)`，并把固定最终 recap 轮 `L25` 作为第 N 个实际执行轮，确保所有 long suite 都有 constraints recap hard assertion；默认和推荐值仍为 25。
- `--pressure-mode {auto,off}`，默认 `auto`。
  - `auto`：按 `OpenHostOptions.context_budget_policy` 计算 pressure，使估算落在 soft threshold 以上、hard threshold 以下。
  - `off`：不注入人工长 padding，用于快速验证 prompt / tool flow；此模式必须打印 `SMOKE PRESSURE disabled`，并把 compaction 相关观察标为 soft skipped。

不增加读取 DB、指定 memory id、dump prompt、dump payload 等调试开关。

## 7. Mock Tool Schema 与数据设计

Provider 常量：

- provider id：`host-public-conversation-memory-scenarios-smoke`
- provider spec id：`host-public-conversation-memory-scenarios-smoke`
- display import path：`__main__:discover_smoke_tools`
- tag：`manual-smoke`

工具名：`get_mock_finance_memory_fact`

命名与 schema rationale：

- 新工具名和类名使用 `Memory` 而不是沿用最小 smoke 的 `MockFinanceFactTool`，是为了表达该脚本覆盖多数据集、多场景的 public memory 行为；现有最小 smoke 仍保留 `get_mock_finance_facts` / `MockFinanceFactTool` 命名，不做 shared helper extraction。
- 新 schema 比最小 smoke 多 required `ticker` 字段是 intentional design：A/E 等场景需要同时验证公司名和证券代码不漂移，ticker 是 public prompt/tool-call contract 的一部分；两个 smoke 使用不同 scene id、provider id 和 tool name，不会构成 scene tool selection 冲突。

schema：

```json
{
  "type": "object",
  "properties": {
    "company": {"type": "string"},
    "ticker": {"type": "string"},
    "period": {"type": "string"},
    "topic": {"type": "string"},
    "metric": {"type": "string"},
    "include_pressure": {"type": "boolean"}
  },
  "required": ["company", "ticker", "period", "topic", "metric", "include_pressure"],
  "additionalProperties": false
}
```

Callable 行为：

- 使用 typed `ToolCallRequest.arguments` 读取字段，只接受固定测试数据集；未知 `company/ticker/topic/metric` 返回成功 JSON 中的 `known=false` 与空事实，不抛异常，以免把 LLM 参数轻微偏差变成 tool runtime 失败。
- `include_pressure=true` 时返回 `pressure_blob`，内容为确定性重复文本；`false` 时返回空字符串。返回 shape 必须稳定。
- 只在 `BatchToolExecutionContext.session_id` 等于本次 tracked session 时累计 `call_count` 与 `calls_by_key`，避免 Host startup recovery 旧 run 污染本次断言。
- `calls_by_key` 不参与 hard pass/fail；它是 observability 计数，key 使用固定 fact key（如 `maotai_revenue`、`cmb_nim`、`midea_long_session`）。每轮后可打印短摘要 `SMOKE TOOL_CALLS_BY_KEY maotai_revenue=1 cmb_nim=1 ...`，最终 summary 必须打印完整 per-key 调用分布，帮助人工确认 long suite 的工具调用覆盖。未知 key 使用 `_UNKNOWN_FACT_KEY` 常量计数。
- 不用模块级全局计数器；必须从 `assembly.effective_tool_bundle` 中找回真实 callable 实例。

固定 facts：

| key | company | ticker | period | topic/metric | marker | values |
|---|---|---|---|---|---|---|
| maotai_revenue | 贵州茅台 | 600519.SH | 2024H1 | revenue_product_growth | `DAYU_MEM_MAOTAI_REV_2024H1_V1` | 茅台酒同比 `17.56%`，系列酒同比 `30.51%`，口径 `百万元` |
| wuliangye_revenue | 五粮液 | 000858.SZ | 2024H1 | revenue_product_growth | `DAYU_MEM_WULIANGYE_REV_2024H1_V1` | 五粮液产品同比 `11.67%`，系列酒同比 `17.77%`，口径 `百万元` |
| catl_cashflow | 宁德时代 | 300750.SZ | 2024A | cashflow | `DAYU_MEM_CATL_CFO_2024A_V1` | 经营性现金流净额 `928.0亿元`，净利润 `507.5亿元`，最大差异项 `经营性应付款增加` |
| byd_margin_long_input | 比亚迪 | 002594.SZ | 2024H1 | gross_margin_long_input | `DAYU_MEM_BYD_LONG_FACTOR2_V1` | 第二因素 marker `BATTERY_PRICE_PRESSURE_FACTOR_2`，三个因素：出口结构、动力电池价格压力、规模效应 |
| cmb_nim | 招商银行 | 600036.SH | 2024H1 | net_interest_margin | `DAYU_MEM_CMB_NIM_2024H1_V2` | 净息差 `1.88%`，同比 `-0.14pct`，生息资产收益率 `3.45%`，计息负债成本率 `1.74%`，零售贷款占比 `52.6%`，定期存款占比 `37.2%`，不良率 `0.94%` |
| midea_long_session | 美的集团 | 000333.SZ | 2024H1 | long_session_profile；允许 metric：`midea_revenue_profile`、`midea_margin_profile`、`midea_expense_profile`、`midea_asset_profile`、`midea_cashflow_profile`、`midea_peer_profile` | `DAYU_MEM_MIDEA_LONG_2024H1_V1` | 约束 `人民币百万元`、`不使用估值倍数外推`、`区分内销与外销`，关键 markers 分散在收入、毛利、费用、现金流主题 |

所有 marker、数值、assertion line、round label、stdout prefix 都必须定义为模块级 `Final` 常量；schema 字段字符串是允许的字面量例外。

## 8. 场景矩阵

### A. pinned_state 演进与抗漂移代理验证

目标：模拟旧文档 A 组的“主体 / 期间 / 口径不漂移”。由于 public API 不暴露 `pinned_state`，用用户可见回答断言代理验证。

轮次：

1. `core-a1-maotai-tool`
   - tools：允许 `get_mock_finance_memory_fact`。
   - prompt：查询贵州茅台 `600519.SH` `2024H1` 产品系列收入增长，要求 `company=贵州茅台`、`period=2024H1`、`topic=revenue_product_growth`、`metric=maotai_revenue`、`include_pressure=false`；回答末尾输出 `DAYU_MEM_ASSERT_A company=贵州茅台 ticker=600519.SH period=2024H1 unit=百万元 marker=DAYU_MEM_MAOTAI_REV_2024H1_V1 maotai_wine_yoy=17.56% series_wine_yoy=30.51%`。
   - hard：terminal succeeded、final answer 非空、tool count +1、assertion values 匹配。
2. `core-a2-maotai-followup-no-tool`
   - tools：`frozenset()`。
   - prompt：`把刚才提到的产品系列对应的销量也一起列出来；如果会话里没有销量事实，请明确说没有，不要编数字。回答仍需保留当前主体、期间和百万元口径。`
   - hard：terminal succeeded、工具调用次数不变、final answer 不得包含五粮液 marker。
   - soft：是否明确承认销量缺失。
3. `core-a3-switch-wuliangye-tool`
   - tools：允许 mock tool。
   - prompt：切换到五粮液 `000858.SZ` `2024H1` 同口径产品系列拆分，要求输出 `DAYU_MEM_ASSERT_A_SWITCH company=五粮液 ticker=000858.SZ period=2024H1 unit=百万元 marker=DAYU_MEM_WULIANGYE_REV_2024H1_V1 wuliangye_core_yoy=11.67% series_yoy=17.77%`。
   - hard：tool count +1，五粮液 assertion 匹配。
4. `core-a4-return-maotai-no-tool`
   - tools：`frozenset()`。
   - prompt：`回到茅台，刚才茅台酒和系列酒同比增速再确认一遍；不要调用工具，最后输出 DAYU_MEM_ASSERT_A_RETURN ...`。
   - expected assertion：`DAYU_MEM_ASSERT_A_RETURN company=贵州茅台 ticker=600519.SH period=2024H1 unit=百万元 marker=DAYU_MEM_MAOTAI_REV_2024H1_V1 maotai_wine_yoy=17.56% series_wine_yoy=30.51%`
   - hard：工具调用次数不变；必须包含茅台 marker 与两个茅台值；assertion line 中不得包含五粮液 marker 或五粮液值。

覆盖说明：覆盖 pinned_state 演进 / 抗漂移的 public 代理行为；不直接证明内部 `pinned_state` JSON 单调 patch。

### B. 追问连续性

目标：模拟旧文档 B 组“这个数 / 这部分支出”指代最近轮。

轮次：

1. `core-b1-catl-cashflow-tool`
   - tools：允许 mock tool。
   - prompt：查询宁德时代 `300750.SZ` `2024A` 现金流关键数据，要求输出 `DAYU_MEM_ASSERT_B_CFO marker=DAYU_MEM_CATL_CFO_2024A_V1 operating_cf=928.0亿元 net_profit=507.5亿元 largest_gap=经营性应付款增加`。
   - hard：tool count +1，assertion 匹配。
2. `core-b2-this-number-no-tool`
   - tools：`frozenset()`。
   - prompt：`这个数和净利润比，差异在哪个项目最大？不要调用工具。最后输出 DAYU_MEM_ASSERT_B_FOLLOW marker=DAYU_MEM_CATL_CFO_2024A_V1 referent=operating_cf largest_gap=经营性应付款增加`。
   - hard：工具调用次数不变，assertion 匹配。
3. `core-b3-investment-spend-soft`
   - tools：`frozenset()`。
   - prompt：`投资活动的支出主要花在什么上？如果当前会话没有确认过，不要编造。`
   - hard：terminal succeeded、工具调用次数不变。
   - soft：打印 preview，人工观察是否承认未确认。

覆盖说明：覆盖最近轮 follow-up continuity；不覆盖旧文档中的 IFRS 口径新增，因为那属于更复杂的 pinned_state 约束写入，已由 A 组口径 / 主体切换和 E 组 constraints recap 覆盖。

### C. 单轮极长输入 minimum-preserve 代理验证

目标：模拟旧文档 C 组“单轮 user_text 远超预算时，后续追问仍能引用第 2 轮内容”。这不依赖工具，使用用户输入中的 deterministic marker。

轮次：

1. `core-c1-byd-intro`
   - tools：`frozenset()`。
   - prompt：`我准备分析比亚迪 2024H1 毛利率结构变化。后续只根据我贴的原文回答。`
   - hard：terminal succeeded。
2. `core-c2-byd-long-input`
   - tools：`frozenset()`。
   - prompt：包含 8,000-15,000 字确定性长文本，由脚本生成，不读取外部文件。文本必须在开头、中部、结尾分别放置稳定 anchors：
     - `DAYU_LONG_INPUT_FACTOR_1_EXPORT_MIX`
     - `BATTERY_PRICE_PRESSURE_FACTOR_2`
     - `DAYU_LONG_INPUT_FACTOR_3_SCALE_EFFECT`
   - 用户问题：`基于以上原文，提炼影响毛利率的三个最重要因素，按重要性排序。回答最后输出 DAYU_MEM_ASSERT_C_LONG marker=DAYU_MEM_BYD_LONG_FACTOR2_V1 factor2=BATTERY_PRICE_PRESSURE_FACTOR_2`。
   - hard：terminal succeeded、final answer 非空。
   - soft：如果 assertion 存在则检查 marker；缺失只打印 `soft-missing`，因为长输入下格式遵循风险高。
   - deterministic generation：
     - 定义模块级常量 `_BYD_LONG_INPUT_TARGET_CHARS: Final[int] = 12_000`、`_BYD_LONG_INPUT_HEAD_ANCHOR`、`_BYD_LONG_INPUT_MIDDLE_ANCHOR`、`_BYD_LONG_INPUT_TAIL_ANCHOR`。
     - 定义 `_BYD_LONG_INPUT_TEMPLATE_PARAGRAPHS: Final[tuple[str, ...]]`，包含 4 段固定中文披露风格文本，分别围绕出口车型结构、动力电池价格压力、规模效应、原材料与产能利用率。模板可包含 anchor 所代表的自然语言含义，但不得随机生成、不得读取外部文件、不得依赖当前日期。
     - `_build_byd_long_input()` 先拼接 head anchor 段，再重复模板段落直到接近目标长度，在文本中点后插入 middle anchor 段，最后追加 tail anchor 段，然后截断/补齐到 `8_000 <= len(text) <= 15_000`。最终文本必须满足三个 anchor 各出现一次，且 `BATTERY_PRICE_PRESSURE_FACTOR_2` 位于文本中部三分之一附近。
     - assembly test 需断言文本长度范围、三个 anchor 出现次数均为 1、连续两次调用完全相同。
3. `core-c3-byd-factor-followup`
   - tools：`frozenset()`。
   - prompt：`第二个因素能再展开讲讲吗？不要调用工具。最后单独输出 DAYU_MEM_ASSERT_C_FOLLOW marker=DAYU_MEM_BYD_LONG_FACTOR2_V1 factor2=BATTERY_PRICE_PRESSURE_FACTOR_2`。
   - hard：工具调用次数不变；answer 必须包含 `BATTERY_PRICE_PRESSURE_FACTOR_2` 与 `DAYU_MEM_BYD_LONG_FACTOR2_V1`。

覆盖说明：覆盖 minimum-preserve 的 public 可见效果；不直接证明 `_build_minimum_preserved_turn_view` 被调用或 assistant 降级路径命中。

### D. confirmed facts 跨轮一致性与 compaction pressure

目标：复用并扩展现有最小 smoke 的招商银行息差一致性，但用新 marker，避免和最小 smoke 输出混淆。

轮次：

1. `core-d1-cmb-tool-pressure`
   - tools：允许 mock tool。
   - prompt：查询招商银行 `600036.SH` `2024H1` 息差数据，`include_pressure=true`，要求输出 `DAYU_MEM_ASSERT_D_NIM marker=DAYU_MEM_CMB_NIM_2024H1_V2 nim=1.88% yoy=-0.14pct asset_yield=3.45% liability_cost=1.74%`。
   - hard：tool count +1，assertion 匹配。
2. `core-d2-group-pressure-no-tool`
   - tools：`frozenset()`。
   - prompt：按“资产 / 负债 / 息差”三组重排，并追加 auto pressure padding；要求输出同一 `DAYU_MEM_ASSERT_D_NIM`。
   - hard：terminal succeeded、工具调用次数不变。
   - soft：assertion line 缺失不立即失败，但如出现则必须匹配。
3. `core-d3-topic-shift-no-tool`
   - tools：`frozenset()`。
   - prompt：问不良率，不调用工具。
   - hard：terminal succeeded、工具调用次数不变。
   - soft：观察是否输出 `0.94%`。
4. `core-d4-return-nim-no-tool`
   - tools：`frozenset()`。
   - prompt：回到刚才息差讨论，净息差具体数值和同比变化再确认，最后输出 `DAYU_MEM_ASSERT_D_RETURN marker=DAYU_MEM_CMB_NIM_2024H1_V2 nim=1.88% yoy=-0.14pct consistent=yes`。
   - hard：工具调用次数不变；必须包含 marker、`1.88%`、`-0.14pct`。

覆盖说明：覆盖 cross-turn facts consistency 和 compaction 后 public answer continuity。compaction 是否实际发生只作为日志 / artifact count 观察，不作为硬 pass 条件，因为 public API 没有 compact terminal 事件契约。

### E. 长会话稳定性

目标：模拟旧文档 E 组 20+ 轮预算稳定性。默认不跑，必须 `--suite long` 或 `--suite all`。

轮次生成：

- 默认 `25` 轮，允许 `20..25`。
- 公司固定为美的集团 `000333.SZ` `2024H1`。
- 长会话 prompt 不允许 implementation worker 临场发明；必须由 `_LONG_ROUND_TEMPLATES: Final[tuple[LongRoundTemplate, ...]]` 或等价 `Final` 常量组生成。`LongRoundTemplate` 至少包含 `label`、`prompt`、`tool_enabled`、`metric`、`include_tool_pressure`、`include_user_pressure`、`hard_contains`、`hard_forbidden`。
- `_long_round_specs(round_count=25)` 返回 L01-L25。`round_count < 25` 时返回 L01 到 `L(N-1)` 加 L25，保证最终 recap 仍执行。
- E 场景 pressure 来源必须显式：
  - tool-enabled pressure：L01、L05、L09、L13、L17、L21 的 tool 参数 `include_pressure=true`，由 mock tool 返回 `pressure_blob`。
  - user prompt pressure：L08、L16、L24 在 prompt 末尾追加 `_compact_pressure_padding(options, label=<label>)`。
  - 其它轮次不注入 pressure。
  - 两类 pressure 都必须按同一个 `OpenHostOptions.context_budget_policy` 自适应估算，不能突破 hard threshold；`--pressure-mode off` 时 tool 参数仍按 spec 传递，但工具返回空 `pressure_blob`，user padding 为空，并打印 skipped marker。

固定 25 轮 prompt specs：

| 轮次 | label / 常量名 | tools / pressure | prompt 固定文本或 intent |
|---|---|---|---|
| L01 | `_LONG_PROMPT_01_REVENUE_TOOL` | tool, tool pressure | `请调用 get_mock_finance_memory_fact 查询美的集团 000333.SZ 2024H1 长会话画像，参数 company=美的集团、ticker=000333.SZ、period=2024H1、topic=long_session_profile、metric=midea_revenue_profile、include_pressure=true。回答只概括收入结构，并记住本会话口径：人民币百万元、区分内销与外销、不使用估值倍数外推。` |
| L02 | `_LONG_PROMPT_02_REVENUE_FOLLOWUP` | no tool | `继续上一轮，不要调用工具。把收入结构按内销和外销拆成两段，并说明后续都沿用人民币百万元口径。` |
| L03 | `_LONG_PROMPT_03_REVENUE_CONSTRAINT_CHECK` | no tool | `不调用工具。确认我们当前研究主体、期间、证券代码和计量口径分别是什么；不要新增事实。` |
| L04 | `_LONG_PROMPT_04_REVENUE_RISK` | no tool | `不调用工具。仅基于会话中已确认的信息，列出收入分析还缺哪些事实；不能编造缺失数据。` |
| L05 | `_LONG_PROMPT_05_MARGIN_TOOL` | tool, tool pressure | `请调用 get_mock_finance_memory_fact 查询美的集团 2024H1 毛利主题，metric=midea_margin_profile、include_pressure=true。回答时继续保留人民币百万元、内销/外销拆分和不使用估值倍数外推三条约束。` |
| L06 | `_LONG_PROMPT_06_MARGIN_FOLLOWUP` | no tool | `不调用工具。把刚才毛利主题和收入结构连起来，说明哪些结论已经确认、哪些只是待验证。` |
| L07 | `_LONG_PROMPT_07_MARGIN_ANTI_DRIFT` | no tool | `不调用工具。请确认当前主体仍是美的集团 000333.SZ 2024H1，而不是前面 core suite 的任何公司；回答中不要引用茅台、五粮液、宁德时代、比亚迪或招商银行的数值。` |
| L08 | `_LONG_PROMPT_08_MARGIN_PRESSURE` | no tool, user pressure | `不调用工具。用三句话总结收入和毛利之间的关系，末尾保留三条口径约束。下面是长会话稳定性压力文本：<auto_user_pressure>` |
| L09 | `_LONG_PROMPT_09_EXPENSE_TOOL` | tool, tool pressure | `请调用 get_mock_finance_memory_fact 查询美的集团 2024H1 费用主题，metric=midea_expense_profile、include_pressure=true。回答只基于工具结果和本会话既有约束。` |
| L10 | `_LONG_PROMPT_10_EXPENSE_FOLLOWUP` | no tool | `不调用工具。把费用主题和毛利主题做一个承接说明，指出费用分析仍然沿用人民币百万元口径。` |
| L11 | `_LONG_PROMPT_11_PROFIT_BRIDGE` | no tool | `不调用工具。基于已确认的收入、毛利、费用讨论，给出利润分析的桥接框架；没有确认过的利润数值不要编。` |
| L12 | `_LONG_PROMPT_12_PROFIT_CONSTRAINT_CHECK` | no tool | `不调用工具。复述本会话到目前为止的三条口径约束，并说明这些约束如何影响利润分析。` |
| L13 | `_LONG_PROMPT_13_ASSET_TOOL` | tool, tool pressure | `请调用 get_mock_finance_memory_fact 查询美的集团 2024H1 资产主题，metric=midea_asset_profile、include_pressure=true。回答中保持当前主体和三条口径约束。` |
| L14 | `_LONG_PROMPT_14_ASSET_FOLLOWUP` | no tool | `不调用工具。把资产主题和利润桥接框架连接起来，明确哪些资产相关信息已经确认。` |
| L15 | `_LONG_PROMPT_15_LIABILITY_SETUP` | no tool | `不调用工具。准备进入负债主题前，先列出我们需要关注的负债问题；不要假设还没确认的数据。` |
| L16 | `_LONG_PROMPT_16_LIABILITY_PRESSURE` | no tool, user pressure | `不调用工具。继续负债主题，只说明当前会话中已确认和未确认的边界，并再次保留三条口径约束。下面是长会话稳定性压力文本：<auto_user_pressure>` |
| L17 | `_LONG_PROMPT_17_CASHFLOW_TOOL` | tool, tool pressure | `请调用 get_mock_finance_memory_fact 查询美的集团 2024H1 现金流主题，metric=midea_cashflow_profile、include_pressure=true。回答要把现金流主题接到收入、利润和资产讨论上。` |
| L18 | `_LONG_PROMPT_18_CASHFLOW_FOLLOWUP` | no tool | `不调用工具。解释现金流主题对前面收入、费用和资产分析的校验作用；缺失的具体数值要标明未确认。` |
| L19 | `_LONG_PROMPT_19_VALUATION_CONSTRAINT` | no tool | `不调用工具。进入估值口径前，确认本会话不使用估值倍数外推；说明这条约束如何限制后续表达。` |
| L20 | `_LONG_PROMPT_20_VALUATION_APPLICATION` | no tool | `不调用工具。在不使用估值倍数外推的约束下，给出可以讨论和不可以讨论的估值相关内容边界。` |
| L21 | `_LONG_PROMPT_21_PEER_TOOL` | tool, tool pressure | `请调用 get_mock_finance_memory_fact 查询美的集团 2024H1 同行对比主题，metric=midea_peer_profile、include_pressure=true。回答只说明对比维度，不引入未确认的同行数值。` |
| L22 | `_LONG_PROMPT_22_PEER_FOLLOWUP` | no tool | `不调用工具。把同行对比维度与内销/外销拆分约束连接起来，说明哪些比较是可做的。` |
| L23 | `_LONG_PROMPT_23_SESSION_RECAP` | no tool | `不调用工具。按收入、毛利、费用、利润、资产、负债、现金流、估值口径、同行对比九个主题，概括本会话已经形成的分析框架。` |
| L24 | `_LONG_PROMPT_24_FINAL_PRESSURE_RECAP` | no tool, user pressure | `不调用工具。在长会话结束前，再次确认当前主体、期间、证券代码和三条口径约束；不要引用 core suite 的公司。下面是长会话稳定性压力文本：<auto_user_pressure>` |
| L25 | `_LONG_PROMPT_25_CONSTRAINT_ASSERT` | no tool | `我们这次对话定下了哪些口径约束？不要调用工具。最后输出 DAYU_MEM_ASSERT_E_CONSTRAINTS marker=DAYU_MEM_MIDEA_LONG_2024H1_V1 unit=人民币百万元 valuation=no_multiple_extrapolation split=内销与外销` |
 
Long suite forbidden markers：

- 所有 no-tool 轮次的 `hard_forbidden` 至少包含 core suite 的关键 markers：`DAYU_MEM_MAOTAI_REV_2024H1_V1`、`DAYU_MEM_WULIANGYE_REV_2024H1_V1`、`DAYU_MEM_CATL_CFO_2024A_V1`、`DAYU_MEM_BYD_LONG_FACTOR2_V1`、`DAYU_MEM_CMB_NIM_2024H1_V2`，防止跨 suite 公司 / fact 漂移。
- L25 `hard_contains` 必须包含 `DAYU_MEM_MIDEA_LONG_2024H1_V1`、`人民币百万元`、`no_multiple_extrapolation`、`内销与外销`。

hard：

- 所有轮次 terminal succeeded。
- final answer 非空。
- session 始终 open。
- tracked tool call count 等于计划中 tool-enabled 轮数，禁用工具轮次不增加。
- 最终 answer 包含 `DAYU_MEM_MIDEA_LONG_2024H1_V1` 与三个 constraint 值。

soft：

- 每轮打印 active/queued public snapshot 摘要。
- 每 5 轮打印 `SMOKE LONG_PROGRESS completed_rounds=<n> tool_calls=<n> compact_artifact_files=<n>`。
- compact artifact file count 增长只作为观察，不作为硬断言。

覆盖说明：覆盖 long-session stability 的 public 行为与工具禁用边界；不证明 episode 数量、pinned_state 去重或 budget 裁剪内部算法。那些内部语义已有 `tests/host/test_memory_projection.py`、`tests/host/test_run_input_builder.py`、`tests/host/test_compact_material.py` 等单元 / 集成测试承担。

## 9. Hard / Soft 断言总表

Hard assertions：

- 每轮 terminal `HostEvent.kind is HostEventKind.SUCCEEDED`。
- 每轮 final answer 非空。
- 每轮后 `host.get_session(session_id).status` 不是 `CLOSED`。
- fresh slot 默认包含本次 smoke run id；`--reuse-session` 才使用稳定 slot。
- mock tool 从 `assembly.effective_tool_bundle` 找回；同名非 smoke tool 冲突时 fail closed。
- 工具启用轮次 call count 按计划递增；`tool_names=frozenset()` 轮次 call count 不变。
- A4 回到茅台时包含茅台 marker / values，且不包含五粮液 marker / values。
- B2 指代 follow-up 包含 `DAYU_MEM_CATL_CFO_2024A_V1` 与 `经营性应付款增加`。
- C3 长输入追问包含 `DAYU_MEM_BYD_LONG_FACTOR2_V1` 与 `BATTERY_PRICE_PRESSURE_FACTOR_2`。
- D4 息差回看包含 `DAYU_MEM_CMB_NIM_2024H1_V2`、`1.88%`、`-0.14pct`。
- E 最终 constraints recap 包含 long marker 与三个约束值。
- 归一化仅做去空白、全角百分号转半角、大小写统一；禁止语义猜测。

Soft observations / log markers：

- LLM 未按要求输出可选 assertion line 时打印 `status=soft-missing`。
- 不良率、销量缺失、投资支出缺失等非核心问题只打印 preview。
- `calls_by_key` per-key 工具调用分布只打印为 observability summary，不参与 hard assertion。
- compaction pressure plan、artifact root、artifact file count 只用于人工观察。
- compact 日志不作为 pass/fail，因为脚本不解析内部日志。

## 10. Scene Manifest 与 Prompt

Manifest：

- `scene`: `smoke_host_public_conversation_memory_scenarios`
- `capability_tags`: `["smoke_host_public_conversation_memory_scenarios"]`
- `model.default_model_id`: 保持与最小 conversation memory smoke 一致，建议 `mimo-v2.5-pro-plan`。
- `model.runner_option_hint_id`: `interactive`
- `agent_policy.max_iterations`: `32`
- `agent_policy.allow_tool_calls`: `true`
- `tool_selection.mode`: `select`
- `tool_selection.tool_tags_any`: `["manual-smoke"]`
- `tool_selection.allow_empty`: `false`
- `context_slots`: `[]`
- fragments：`base/agents.md`、`base/fact_rules.md`、`scenes/smoke_host_public_conversation_memory_scenarios.md`

Scene prompt 必须短小，不包含任何测试答案、公司数值或 marker：

```markdown
# Host public 财报对话记忆场景 smoke 执行契约

- 你当前处于 Host public 财报对话记忆场景 smoke。
- 优先回答用户当前财务问题；需要使用工具时，只调用当前轮次允许的工具。
- 不披露 smoke 运行过程、装配细节、上下文压力文本或运行时诊断。
- 当用户要求输出 `DAYU_MEM_ASSERT` 或同类核对行时，按用户给定字段原样输出。
- 如果会话里没有确认过某个事实，明确说明没有确认，不要编造数值。
- 输出 Markdown 格式。
```

## 11. 实现结构

建议类型：

- `SmokeArgs`
- `RoundSpec`
- `RoundResult`
- `ScenarioResult`
- `RuntimeAssemblyResult`
- `MockFinanceMemoryTool`
- `MockFinanceFactRecord`
- `ScenarioSuite` 使用 `StrEnum`，值为 `core`、`long`、`all`。
- `PressureMode` 使用 `StrEnum`，值为 `auto`、`off`。

`RoundSpec` 设计必须避免把所有场景写进一个脆弱的 label-based `if/elif` 巨函数。推荐字段：

- `label: str`
- `prompt: str`
- `tool_names: frozenset[str]`
- `expected_tool_calls_after_round: int`
- `hard_answer_contains: tuple[str, ...]`
- `hard_answer_forbidden: tuple[str, ...]`
- `soft_answer_contains: tuple[str, ...]`
- `print_calls_by_key: bool`

断言策略：

- `_assert_terminal_ok(result)` 只检查 terminal succeeded 与 final answer 非空。
- `_assert_tool_count(tool, expected, label)` 只检查 tracked session 的 total call count。
- `_assert_answer_contains(content, label, required, forbidden)` 只做归一化字符串包含 / 禁止包含。
- `_observe_soft_answer_contains(content, label, markers)` 只打印 soft observation，不抛错。
- `_assert_round_result(...)` 只能组合以上 helper，按 `RoundSpec` 数据驱动执行，不允许按 label 写长分支。确需少量特殊行为时，优先增加 `RoundSpec` 字段，不在 helper 内新增业务分支。

关键函数：

- `parse_args(argv: Sequence[str]) -> SmokeArgs`
- `run_smoke(args: SmokeArgs, env: Mapping[str, str]) -> int`
- `discover_smoke_tools(spec: ToolsDiscoveryProviderSpec) -> ToolsDiscoveryProviderOutput`
- `_prepare_runtime_assembly(args: SmokeArgs, *, env: Mapping[str, str]) -> RuntimeAssemblyResult`
- `_run_round(host: Host, watcher: AsyncIterator[HostEvent], session_id: str, spec: RoundSpec, scene_inputs: PreparedSceneInputs) -> RoundResult`
- `_core_round_specs(options: OpenHostOptions, pressure_mode: PressureMode) -> tuple[RoundSpec, ...]`
- `_long_round_specs(options: OpenHostOptions, pressure_mode: PressureMode, round_count: int) -> tuple[RoundSpec, ...]`
- `_select_long_templates(round_count: int) -> tuple[LongRoundTemplate, ...]`，按 `L01..L(N-1)+L25` 选择模板。
- `_assert_round_result(result: RoundResult, tool: MockFinanceMemoryTool, spec: RoundSpec) -> None`
- `_assert_answer_contains(content: str, *, label: str, required: tuple[str, ...], forbidden: tuple[str, ...] = ()) -> None`
- `_compact_pressure_padding(options: OpenHostOptions, *, label: str) -> str`
- `_print_*` helper 只打印脱敏短摘要，不输出 API key、headers、完整 prompt、完整 pressure payload。

编码约束：

- 所有模块、类、函数必须有中文 docstring，包含参数、返回值、异常。
- 不使用 `Any`、`object`、无类型参数、无类型返回值。
- 不使用 `hasattr` / `getattr` 逃避边界；确有必要必须在 plan fix 中重新裁决。
- 不使用 lazy import。
- 不把显式参数塞进 extra payload。
- 不使用嵌套函数 / 嵌套类，除非 review 后确认必要。
- constants 集中在模块顶部，schema 内字段字面量除外。
- stdout 不打印完整 prompt、pressure blob、provider headers、API key 或完整 final answer；只打印 preview。

## 12. 测试计划

新增 `tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py`，覆盖：

- 默认 args：suite=`core`、pressure_mode=`auto`、fresh slot。
- `--suite long --long-rounds 20` 和 `--long-rounds 25` 解析成功；`--long-rounds 19`、`--long-rounds 26`、`--long-rounds 0`、`--long-rounds -1` fail closed。
- `_select_long_templates(20)` 返回 20 个模板，最后一个模板是 L25；`_select_long_templates(25)` 返回 L01-L25 全量模板。
- suite all 编排函数返回 `(*core_specs, *long_specs)`，且测试应确认它不创建第二个 ensure/open lifecycle abstraction；可通过纯函数 spec 拼接单测覆盖。
- `_prepare_runtime_assembly` 在无 workspace overlay 时通过内置 provider 注入 `get_mock_finance_memory_fact`。
- workspace overlay 同名非 smoke tool 冲突时 fail closed。
- scene tool selection 只选中 `manual-smoke` mock tool。
- fresh / reuse session slot key 规则。
- pressure padding 估算落在 soft threshold 以上、hard threshold 以下；`pressure-mode=off` 返回空 padding 并打印 disabled marker。
- mock tool 对已知 key 返回固定 marker/value；未知 key 返回 `known=false` 的稳定 shape。
- mock tool `calls_by_key` 在 tracked session 内按 fact key 累计，并能格式化为 `SMOKE TOOL_CALLS_BY_KEY ...` 摘要。
- 禁用工具轮次的 `RoundSpec.tool_names == frozenset()`。
- C2 `_build_byd_long_input()` 长度在 8,000-15,000 字，三个 anchor 各出现一次，连续调用输出完全一致。
- answer normalization 对空白、全角百分号、大小写稳定。

更新 `tests/runtime/test_scene_assets_migration.py`：

- 新 scene 加入 `_OLD_SCENE_MAX_ITERATIONS`，期望 `32`。
- 现有所有 scene prepare 测试应继续通过。

不新增真实 LLM 自动测试；这是手工 smoke，真实 provider 运行由 operator 执行。

## 13. 验证命令

实现后必须在虚拟环境中运行：

```bash
source .venv/bin/activate
pytest tests/runtime/test_smoke_host_public_multiturn_assembly.py tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py tests/runtime/test_scene_assets_migration.py -q
pyright
```

手工 core smoke：

```bash
source .venv/bin/activate
python utils/smoke_host_public_conversation_memory_scenarios.py --suite core --log-level VERBOSE
```

手工 long smoke：

```bash
source .venv/bin/activate
python utils/smoke_host_public_conversation_memory_scenarios.py --suite long --long-rounds 25 --log-level VERBOSE
```

手工 all smoke：

```bash
source .venv/bin/activate
python utils/smoke_host_public_conversation_memory_scenarios.py --suite all --long-rounds 25 --log-level VERBOSE
```

快速无 pressure flow：

```bash
source .venv/bin/activate
python utils/smoke_host_public_conversation_memory_scenarios.py --suite core --pressure-mode off --log-level DEBUG
```

预期 pass markers：

- `SMOKE PASS public Host conversation memory scenario suite=core`
- `SMOKE PASS public Host conversation memory scenario suite=long`
- `SMOKE PASS public Host conversation memory scenario suite=all`

## 14. README / Docs 决策

需要更新：

- `README.md`
  - 触发原因：新增 `utils/` 手工 smoke 入口，属于用户手册的手工验证入口。
  - 内容：保留 5.2 最小 conversation memory smoke；新增 5.3 场景 smoke，说明 `--suite core|long|all`、默认不跑 long、只用 mock finance tool、不读取 durable DB。现有 5.3 Engine provider smoke 需要同步顺延为 5.4，后续同级小节编号一并机械更新，避免 README 目录/引用出现重复编号。
- `tests/README.md`
  - 触发原因：新增 runtime assembly 测试。
  - 内容：在 runtime assembly / smoke assembly 说明中加入新测试文件职责。

不更新：

- `dayu/host/README.md`：不改 Host public API、状态机、事件流或机制。
- `dayu/config/README.md`：新增 smoke scene asset，不改变配置覆盖关系、默认配置或 prompts 目录职责。
- `dayu/README.md`：不改变分层关系、装配方式或 UI / Service / Host / Engine 边界。
- `dayu/fins/README.md`：不接真实 Fins。

## 15. Residual Risks 与 Owner

- `pinned_state` 内部 JSON 单调演进不可由 public smoke 直接读取。
  - Owner：Host memory 单元 / 集成测试继续覆盖；本 smoke 只验证 public anti-drift 行为。
- compaction 是否真实触发不可作为 public hard assertion。
  - Owner：Host compact tests 覆盖内部触发；本 smoke 打印 pressure plan 与 artifact count 供人工观察。
- LLM 可能不按要求输出 assertion line。
  - Owner：implementation worker 用 hard / soft 分层降低误伤；核心最终轮使用 marker/value hard assertion。
- long suite 成本高、耗时长、受 provider rate limit 影响。
  - Owner：operator / controller 决定何时运行；默认 `core` 不自动跑 long。
- 新脚本与最小 smoke 存在部分 assembly pattern 重复。
  - Owner：controller。当前裁决是不抽取 shared helper，因为保护已通过的最小 smoke 语义比减少 utils-only 重复更重要；若后续 review 强制要求抽取，应作为单独 slice 并加入最小 smoke parity 检查。

## 16. Implementation Slices

### S1：新增场景 smoke 脚本

- Allowed files：
  - `utils/smoke_host_public_conversation_memory_scenarios.py`
- Objective：
  - 实现 CLI、mock tool、public Host call flow、core / long round specs、hard / soft assertions、stdout markers。
- Non-goals：
  - 不新增 manifest / scene 文件之外的配置依赖。
  - 不修改现有最小 smoke。
- Completion signal：
  - `python -m py_compile utils/smoke_host_public_conversation_memory_scenarios.py` 通过。
  - 新脚本不导入 Host private modules。

### S2：新增 scene asset

- Allowed files：
  - `dayu/config/prompts/manifests/smoke_host_public_conversation_memory_scenarios.json`
  - `dayu/config/prompts/scenes/smoke_host_public_conversation_memory_scenarios.md`
  - `tests/runtime/test_scene_assets_migration.py`
- Objective：
  - 新 scene 可被 `prepare_scene` 装配，tool selection 选中 `manual-smoke`。
- Completion signal：
  - `pytest tests/runtime/test_scene_assets_migration.py -q` 通过。

### S3：新增 assembly tests

- Allowed files：
  - `tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py`
- Objective：
  - 覆盖 CLI、assembly、mock tool、pressure、slot key、normalization。
- Completion signal：
  - `pytest tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py -q` 通过。

### S4：README 同步与验证

- Allowed files：
  - `README.md`
  - `tests/README.md`
- Objective：
  - 文档只描述当前真实入口，不写未来计划，不要求用户查 DB。
- Completion signal：
  - 受影响 tests 与 `pyright` 通过。
  - README 中现有最小 smoke 说明仍在，新增场景 smoke 说明清楚区分 core / long。

## 17. Completion Report 格式

Implementation worker 最终报告必须包含：

- 改了什么：列出新增脚本、scene asset、tests、README。
- 验证了什么：列出 pytest、pyright、手工 smoke 是否运行；若未运行真实 provider smoke，说明原因。
- 未覆盖 / 风险：按第 15 节分类，不得遗漏 long suite 是否运行。
- 明确说明：`utils/smoke_host_public_conversation_memory.py` 未修改，或如经 controller 授权发生 helper extraction，说明等价性验证。

## Blocking Questions For Controller

无。
