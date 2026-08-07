# PR 190 F15/F16 Plan Review — AgentMiMo (2026-08-07)

## Reviewed Target

`docs/gateflow/pr-190-f15-f16-plan-20260807.md`

## Scope

独立 adversarial plan review。不实施、不修改 plan/production、不测试、不 commit/push。完整核对
`AGENTS.md`、Goal Confirmation、直接 traceback/code、Host design owner 和 `docs/cli_ci.md`。

## Assumptions Tested

1. F15 root cause 是 packed block 归一化而 readable view 使用原始文本，导致 pair validator exact mismatch。
2. F15 覆盖全部 previous-view 文本 section，不只是 answer anchor。
3. F16 能从现有 EventLog API 取得 per-Run terminal/reason。
4. F16 helper 与 process outcome 正确分离。
5. F16 dependent-chain stop 不影响 independent mandatory work。
6. 不需要修改 schema/public contract。
7. README 触发条件不命中。

## Findings

### 01-未修复-中-reason_json 缺乏统一 typed contract，strict resolver 设计存在缺口

- **位置**: §5.1 tracked reusable helper 第 4 点
- **问题类型**: 契约缺失
- **当前写法**: plan 要求"从 canonical terminal event 的 `reason_json` 按 strict typed contract 读取 reason；missing、malformed 均 fail closed"
- **反例/失败场景**: `reason_json` 在生产代码中有至少三种不同形状：
  - `_fail_unstarted_in_transaction` (dispatch.py:2922): 裸字符串 `"runner_candidate_invalid"`
  - wait governance: 结构化 JSON `{"reason_code": "wait_cancelled"}`
  - tool policy: `_policy_reason_json` 产出的结构化 JSON
  - `FailUnstartedRunInput.reason` 是 `str`，但 `EventLogAppendRequest.reason` 是 `JsonValue | None`
  - plan 声称的 "strict typed contract" 在现有代码中不存在；helper 实现者无法确定应该期望哪种形状
- **为什么有问题**: 实现 agent 面对多态 `reason_json` 时，要么写一个能处理所有形状的 loose parser（违反 plan 约束），要么为每种 terminal type 写专门的 typed contract（plan 未定义这些 contract）
- **直接证据**:
  - dispatch.py:2922 `reason="runner_candidate_invalid"` (flat str)
  - event_log.py:99 `reason: JsonValue | None`
  - event_log.py:1029 `reason_json = _optional_canonical_json(request.reason)`
  - test_wait_cancel_late_result.py:230 `reason_json == '{"reason_code":"wait_cancelled"}'`
  - stress_support.py:1430 `SELECT json_extract(reason_json, ?)` — 说明生产代码自己也用 JSON path 访问
- **影响**: 实现 agent 可能 (a) 写 loose parsing 违反 plan 约束，或 (b) 对某些 terminal 的 reason 解析 fail closed 导致 valid terminal 被误判为 invalid
- **建议改法和验证点**: 在 plan 中明确列出每种 terminal type 的 reason_json 期望形状：
  - `RUN_SUCCEEDED`: `reason_json` 应为 `null`
  - `RUN_FAILED` (dispatch): flat string，如 `"runner_candidate_invalid"`
  - `RUN_FAILED` (wait): `{"reason_code": "..."}` 结构
  - `RUN_CANCELLED`: `reason` 字段
  - `RUN_LOST`: `null` 或结构化
  - helper 应按 terminal type 分别 typed parse，而不是假设统一形状
- **修复风险（低/中/高）**: 中 — 需要在 plan 中补充 contract 定义，不改变架构
- **严重程度（低/中/高/严重）**: 中

### 02-未修复-中-EventLog 连接方式未指定，影响 helper 可测试性与依赖隔离

- **位置**: §5.1 tracked reusable helper
- **问题类型**: 不可直接实施
- **当前写法**: plan 只说 helper "依赖生产 Host durable read API/EventLog reader 与 shared lifecycle constants/types"，未指定 helper 如何获得 EventLog 连接
- **反例/失败场景**: 现有 EventLog 读取通过 `EventLogStore` 类进行，需要 `HostTransaction`。helper 要么：
  - (a) 直接打开 SQLite 连接 — 违反 "依赖 Host API" 承诺，且与 `prompt_observe_calibration.py` 当前的 `_db_terminal_run_count` (直接 SQL) 模式相同
  - (b) 接收 `EventLogStore` 实例 — 但 `EventLogStore` 需要 `HostTransaction`，而 helper 定位为 "只读投影"
  - (c) 接收 SQLite 路径自行构建只读连接 — 绕过 Host API
- **为什么有问题**: plan 的 isolation 声称 ("helper 只依赖生产 Host durable read API") 与实际可用 API 之间有缺口，实现 agent 必须重新设计连接方式
- **直接证据**:
  - event_log.py:315 `EventLogStore` 类需要 transaction 参数
  - prompt_observe_calibration.py:749-776 `_db_terminal_run_count` 直接用 `sqlite3` 查询 host_runs 表
  - plan §5.1: "helper 只依赖生产 Host durable read API/EventLog reader"
- **影响**: 实现 agent 可能 (a) 直接用 sqlite3 绕过 Host API（与 plan 声称矛盾），或 (b) 花时间设计一个 plan 未定义的连接抽象
- **建议改法和验证点**: 明确 helper 的数据访问方式：
  - 选项 A: 接收 SQLite 只读路径，用 `EventLogStore` 的模块级函数（如 `read_run_events_by_types_page`）
  - 选项 B: 接收已打开的 `EventLogStore` 实例
  - 选项 C: 直接用 sqlite3 只读连接（最简单但绕过 Host API）
  - 建议选 A 或 C（因为 helper 在 `utils/`，不在 Host 进程内），并在 plan 中明确
- **修复风险（低/中/高）**: 低 — 只需补充一个设计决策
- **严重程度（低/中/高/严重）**: 中

### 03-未修复-低-observation window 边界与分页 exhaustion 语义未定义

- **位置**: §5.1 第 1 点 "以 EventLog cursor/sequence 分页读取指定 observation window，直到穷尽"
- **问题类型**: 契约缺失
- **当前写法**: "指定 observation window" — 但未定义 window 的起止边界
- **反例/失败场景**:
  - 如果 window 是整个 EventLog，helper 会扫描所有历史 Run（包括之前 CI run 的 Run）
  - 如果 window 是特定 session_id 范围，plan 未指定如何确定该范围
  - "直到穷尽" 的语义：当 `read_events_after` 返回空 tuple 时是否算穷尽？如果 EventLog 在读取过程中被追加新事件呢？
- **为什么有问题**: 现有 `f14_real_cli_observation.py` 通过 `ChainState.terminal_count` 和 `run-terminal-count:<N>` trigger 隐式定义了 window。新 helper 需要显式 window 边界。
- **直接证据**:
  - event_log.py:350 `read_events_after` 需要 cursor 和 limit
  - f14_real_cli_observation.py:39-50 `ChainState` 隐式定义 window
  - plan §5.1: "指定 observation window" — 未定义具体参数
- **影响**: 实现 agent 需要自行决定 window 边界，可能与 harness 期望不一致
- **建议改法和验证点**: 明确 helper 接收的 window 参数：
  - `session_id` 过滤（最精确）
  - 或 `min_event_sequence` / `max_event_sequence` 范围
  - 或从 `RUN_ACCEPTED` 事件推导 Run identity 集合
  - exhaustion 语义：page 返回空 tuple 且 `covered_event_sequence` 不前进时为穷尽
- **修复风险（低/中/高）**: 低 — 补充参数定义
- **严重程度（低/中/高/严重）**: 低

### 04-未修复-低-fresh evidence index 字段定义与 EventLog 数据模型映射不明确

- **位置**: §5.3 per-Run terminal/reason evidence 和 §5.5 fresh evidence index
- **问题类型**: 不可直接实施
- **当前写法**: index 包含 "accepted ordinal、session_id、run_id、RUN_ACCEPTED event id/sequence" 和 "terminal event type、event id/sequence、terminal class、strict canonical reason"
- **反例/失败场景**:
  - "accepted ordinal" — 这是 `event_sequence` 还是 Run 在 session 内的逻辑序号？现有代码没有 "accepted ordinal" 概念
  - "terminal class" 定义为 `succeeded | failed | cancelled | lost` — 这与 `HostTerminalStatus` 的枚举值一致，但 plan 未引用该类型
  - "strict canonical reason" — 如 finding 01 所述，reason 形状不统一
- **为什么有问题**: 实现 agent 需要从 EventLog 数据模型映射到 index 字段，但映射规则不明确
- **直接证据**:
  - plan §5.3: "accepted ordinal、session_id、run_id"
  - lifecycle_events.py: `HostRunEventType` 枚举值
  - api.py: `HostTerminalStatus(StrEnum)` 枚举值
- **影响**: 实现 agent 可能使用不同的字段名或映射方式，导致 index 与 EventLog 数据不一致
- **建议改法和验证点**: 明确每个 index 字段的 EventLog 数据源：
  - `accepted_ordinal`: 建议改为 `accepted_event_sequence` (直接来自 EventLog row)
  - `terminal_class`: 明确引用 `HostTerminalStatus` 的枚举值
  - `reason`: 参照 finding 01 的 typed contract
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 05-未修复-低-F15 新测试与既有测试的边界未明确

- **位置**: §6.1 Slice 1 deterministic tests 和 §7.1 F15 focused tests
- **问题类型**: 切片过粗
- **当前写法**: plan 列出 6 个新测试名称，但未说明它们与既有 `test_compact_material.py` 中 5648 行测试的关系
- **反例/失败场景**:
  - 既有测试 `test_compact_material_pack_rejects_previous_typed_pair_text_mismatch` (line 1077) 已经测试 pair validation 失败场景
  - 既有测试 `test_degrade_previous_compacted_view_keeps_highest_priority_section_exact` (line 948) 测试 recovery pair exact equality
  - 新测试可能与既有测试重叠，或者既有测试需要更新以适应新的 canonical projection 边界
- **为什么有问题**: 实现 agent 不确定是否需要更新既有测试、是否需要保持既有测试通过、以及新旧测试的覆盖边界
- **直接证据**:
  - test_compact_material.py:1077 `test_compact_material_pack_rejects_previous_typed_pair_text_mismatch`
  - test_compact_material.py:948 `test_degrade_previous_compacted_view_keeps_highest_priority_section_exact`
  - plan §7.1: 列出 6 个新测试名称，未提及既有测试
- **影响**: 实现 agent 可能 (a) 不更新既有测试导致测试失败，或 (b) 更新既有测试但破坏了原有覆盖
- **建议改法和验证点**: 明确：
  - 既有 `test_compact_material_pack_rejects_previous_typed_pair_text_mismatch` 是否需要更新（因为它测试的是旧的双路径行为）
  - 新测试是否替代或补充既有测试
  - 既有测试全部通过是否是 implementation gate 的前置条件
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Open Questions

1. **F16 helper 是否需要处理 `RUN_ACCEPTED` 之后但 terminal 之前的 Run？** Plan 说 "每个 Run 投影恰好一个 terminal"，但 Run 可能还在 RUNNING/WAITING 状态。helper 对 non-terminal Run 应该返回什么？plan 的 §5.1 第 5 点提到 "未 terminal 在等待期为 pending，deadline 后为 invalid/incomplete"，但 deadline 参数未定义。

2. **F15 的 `_CanonicalPreviousReplacementProjection` 是 frozen dataclass 还是普通 tuple？** Plan 说 "模块私有、严格 typed、不可变"，但未指定具体类型形式。这影响实现 agent 的设计选择。

3. **F16 helper 的 deterministic JSON 排序规则：** Plan 说 "排序只依据 canonical sequence/explicit ordinal"，但 canonical sequence 是 `event_sequence`（全局）还是 session 内的逻辑顺序？如果两个 Run 在不同 session 中，排序规则是什么？

## Residual Risks

1. **`reason_json` 多态性** — 即使 plan 补充了 typed contract，未来 Host 新增 terminal reason 类型时，helper 可能需要更新。建议 helper 对 unknown reason shape fail closed 而非 reject terminal。

2. **EventLog 读取性能** — 如果 observation window 很大（数百个 Run），逐 Run 分页读取可能较慢。现有 `f14_real_cli_observation.py` 通过直接 SQL 查询绕过了这个问题。

3. **temporary harness 与 tracked helper 的边界** — Plan 正确地将语义放在 tracked helper、将临时消费者放在 `workspace/tmp/`。但 `prompt_observe_calibration.py` 的 `_db_terminal_run_count` 直接查询 `host_runs` 表，而新 helper 将使用 EventLog API。两者的数据源可能不一致（`host_runs.status` 是 durable state index，`event_log` 是 canonical facts）。

## Goal Drift Check

无 goal drift。F15 和 F16 的所有设计决策均能映射到 Goal Confirmation 已确认的 goal：
- F15: 同源 canonical projection 修复 pair mismatch
- F16: per-Run terminal/reason 投影 + process outcome 分离 + dependent chain stop

Plan 的 §2.4 非目标、§10 schema/public-contract no-change stop condition 与 Goal Confirmation 的非目标一致。没有新增验收标准或架构强化超出 Goal Confirmation 范围。

## Architecture Boundary Check

- **分层**: F15 修改在 `dayu/host/compact_material.py`（Host 层内部），不违反 `UI -> Service -> Host -> Engine` 依赖方向。✓
- **反向依赖**: F16 helper 在 `utils/`，import `dayu.host` 的 `lifecycle_events` 和 `event_log`。`AGENTS.md` 说 "分析辅助代码仅放在 `utils/`"，且 `utils/` 可以 import 业务层。不违反。✓
- **Host design owner**: `dayu.host.compact_material` 是 previous compacted view pair 的 projection owner。F15 在 owner boundary 内修复。✓
- **F16 不创建第二套 Run status 真源**: helper 只做只读投影，不持久化新业务事实。✓

## README Trigger Check

- `dayu/host/compact_material.py` 修改 → 检查 `dayu/host/README.md` 更新约束：F15 是内部正确化，不新增 package public boundary。Plan 的判断正确，不需要修改。✓
- `tests/` 新增 → 检查 `tests/README.md`：新增测试属于现有 CLI test layer，不改变测试运行方式。Plan 的判断正确。✓
- `utils/cli_ci_run_observation.py` 新增 → `AGENTS.md` 没有 `utils/` 修改的 README 触发条件。✓
- `docs/cli_ci.md` 修改 → `AGENTS.md` 没有 `docs/` 修改的 README 触发条件。但这意味着 `docs/cli_ci.md` 的更新没有外部 review 约束。⚠️（低风险）

## Real Evidence / Secret Scan Check

- Plan §9 要求 fresh rerun 后扫描全部 evidence files，包括 credential、token、key、Authorization/Cookie/Bearer/API-key pattern、secret canary、external run root、repo absolute path、raw provider payload。✓
- Plan §9 要求 symlink、超限文件、不可读文件 fail closed。✓
- Plan §5.2 说 process outcome 不暴露 raw SQLite。✓
- Plan 的 evidence index 不含综合 `scenario_success` 字段。✓

## Plan Review Conclusion

**pass-with-risks**

Plan 的 root cause 分析准确，F15 canonical projection 设计方向正确，F16 terminal/process/dependency 分离设计合理。主要风险是 `reason_json` 缺乏统一 typed contract（finding 01）和 EventLog 连接方式未指定（finding 02），这两个问题会迫使实现 agent 在 plan 约束外重新设计。其余 findings 为低严重度的契约补充需求。

建议在 implementation gate 前：
1. 补充 `reason_json` 的 per-terminal-type typed contract
2. 明确 helper 的 EventLog 数据访问方式
3. 明确 observation window 参数定义
