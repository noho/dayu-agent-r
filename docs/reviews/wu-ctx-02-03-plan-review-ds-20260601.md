# WU-CTX-02 + WU-CTX-03 Plan Review

## 审查依据

- 设计真源：`docs/host/design.md` 第 1 节（设计目标）、第 25 节（Context Governance）
- 实施总控：`docs/host/host-core-followup-implementation-control.md`
- 代码核对证据：`docs/reviews/wu-ctx-02-03-discussion-code-inspection-20260601.md`
- 裁决记录：`docs/reviews/wu-ctx-02-03-discussion-controller-adjudication-20260601.md`
- Review target：`docs/host/wu-ctx-02-03-compact-failure-overflow-plan.md`

## 1. Motivation 审查

### 动机成立性

Plan 的动机成立。每个断言的缺口均有直接代码证据支撑：

- 默认 `max_compaction_attempts_per_operation`：代码常量 2（`context_policy.py:22`），packaged profiles 3（`execution_profiles.json`），设计要求 5。证据充分。
- Scene/profile compactor model 不一致：`conversation_compaction.json` scene default 为 `mimo-v2.5-pro-thinking-plan`（high-spec），`execution_profiles.json` compactor baseline 为 `deepseek-v4-flash`（flash-tier），设计第 3 节要求 packaged default 不互相矛盾。证据充分。
- Deterministic recent-window fallback 未实现：`dispatch.py` proactive failure 和 `engine_ingest.py` reactive failure 直接 fail closed，无 fallback 分支。证据充分。
- `CONTEXT_COMPACTION_FAILED` payload 诊断不足：builder 缺少 operation_id、attempt_count、retry_repair_budget_exhausted、fallback 诊断字段。证据充分。
- 连续 reactive overflow dispatch-loop E2E 缺失：scheduler 层只有单次 overflow recovery 成功测试。证据充分。

### 被正确识别为不应纳入的部分

Plan 正确排除了：
- provider tokenizer adapter（设计第 25 节明确第一版不实现）
- Engine overflow retry（控制文档 WU-CTX-03 明确非目标）
- memory projection redesign（已覆盖且与当前缺口无关）
- 旧 schema/profile/接口兼容逻辑

### 结论：动机成立，scope 收窄合理。

## 2. Scope Boundary 审查

### 2.1 分层边界

Plan scope 严格约束在 Host 层：
- `dayu/host/context_policy.py`：默认值调整 ✓
- `dayu/host/context_events.py`：payload 补足 ✓
- `dayu/host/context_fallback.py`（新增）：fallback 内部逻辑 ✓
- `dayu/host/run_input.py`：内部 fallback provider 注入 ✓
- `dayu/host/dispatch.py`：proactive fallback 分支 ✓
- `dayu/host/engine_ingest.py`：reactive fallback 分支 ✓
- `dayu/host/durable/run_transition.py`：仅最小修改 ✓

未越界到 Engine、Service public API 或 dayu.runtime。符合设计第 1 节分层约束。

### 2.2 Non-goals 充分性

Non-goals 覆盖了所有已知的过度设计风险：
- provider tokenizer adapter ✓
- Engine overflow retry ✓
- memory projection redesign ✓
- fallback 不生成 episode summary / stable facts / pinned state ✓
- 旧 schema/profile 兼容 ✓
- recovery/positive orphan proof 重构 ✓
- ingest 层单点计数重复 ✓

### 2.3 Stop Conditions 质量

Stop conditions 与设计真源对齐良好：
- Public contract 变更 -> 停 ✓
- Fallback 写 CONTEXT_COMPACTED / memory -> 停 ✓
- Reactive 进 LOST / proactive 进 RECOVERING -> 停 ✓
- E2E 依赖 sleep/race -> 停 ✓
- 旧配置兼容路径 -> 停 ✓

## 3. Fallback Policy 审查

### 3.1 是否绕过设计真源

Plan 的 fallback policy 正确对齐设计第 25 节：

| 设计要求 | Plan 对齐状态 |
|---|---|
| fallback 不是 compact 成功 | Section 5 success signal 和 Section 6 invariants 明确：不写 CONTEXT_COMPACTED、不写 memory projection、不生成 stable facts |
| fallback 只构造本次 dispatch bounded input view | Section 6 Slice C："只替换 memory / compact / continuity messages 为 fallback bounded messages" |
| fallback 必须写 CONTEXT_COMPACTION_FAILED 或等价 diagnostic | Section 5：fallback_action 字段区分 dispatch/fail_closed/not_applicable |
| fallback 记录 fallback decision、input window/digest、budget result | Section 5：fallback_policy_decision、fallback_input_window、fallback_input_digest、fallback_budget_result 均已列出 |
| fallback 后重新估算预算 | Section 6 Slice C："调用现有 conservative estimator" |
| 预算通过才 dispatch，仍超则 fail closed | Section 6 invariants 明确 |

### 3.2 Fallback 参数是否误入 public contract

Plan Section 5 明确："fallback policy 第一版使用 Host 内部默认与现有 `MemoryProjectionPolicy.recent_raw_turns_floor` / material block 边界派生，不新增 public `ContextBudgetPolicy` 字段"。Stop condition 覆盖了"若实现发现必须新增 public policy field，停止并交回 controller"。设计合理。

## 4. CONTEXT_COMPACTION_FAILED Payload 审查

### 4.1 字段完备性

| 设计要求（design.md:2869） | Plan 覆盖 |
|---|---|
| operation_id | ✓ |
| failure_reason | ✓（已有保留） |
| policy_decision | ✓（已有保留） |
| retryable | ✓（已有保留） |
| attempt_count | ✓（新增） |
| retry/repair budget exhausted | ✓（新增 retry_repair_budget_exhausted） |
| diagnostic_refs | ✓（已有保留） |
| fallback input window / digest | ✓（新增 fallback_input_window、fallback_input_digest） |
| fallback budget result | ✓（新增 fallback_budget_result） |
| fallback dispatch or fail closed | ✓（新增 fallback_action） |

### 4.2 不过度暴露 raw payload

Plan Section 5 明确 `fallback_input_window` 必须是结构化诊断："建议包含 `selected_block_ids`、`dropped_block_ids`、`current_input_ref`、`source_refs`、`recent_raw_turns_floor`、`trigger_source`、`policy_ref`。不得包含 API key、headers、完整 provider payload 或无界 raw text。" 符合设计"不包含 API key、headers、完整 raw prompt 或完整 provider payload"的要求。

## 5. State Machine 审查

### 5.1 Proactive 路径

Plan 状态路径：
```
RUN_ACCEPTED|RUN_QUEUED -> CONTEXT_COMPACTION_REQUESTED -> CONTEXT_COMPACTION_FAILED(fallback_action=dispatch) -> RUN_STARTED -> ATTEMPT_STARTED -> dispatch
```

设计真源（line 2834-2841）：
```
proactive trigger -> CONTEXT_COMPACTION_REQUESTED -> CONTEXT_COMPACTED or CONTEXT_COMPACTION_FAILED -> if failed + fallback: build view + re-estimate -> RUN_STARTED / ATTEMPT_STARTED -> dispatch
```

一致。Proactive fallback 不进 RECOVERING。Plan 额外精确化了 fallback_action=dispatch 与 fail_closed 分支，属于对设计真源的合理细化。

### 5.2 Reactive 路径

Plan 状态路径：
```
RUNNING -> CONTEXT_COMPACTION_REQUESTED(reactive) -> ATTEMPT_FAILED -> RUN_RECOVERING -> CONTEXT_COMPACTION_FAILED(fallback_action=dispatch) -> RUN_STARTED(start_reason=recovery) -> ATTEMPT_STARTED -> dispatch
```

设计真源（line 2843-2854）：
```
reactive trigger -> validate -> CONTEXT_COMPACTION_REQUESTED(reactive) -> close Attempt -> RUN_RECOVERING -> compact/failed + fallback -> RUN_STARTED(recovery) -> new Attempt -> dispatch
```

一致。Reactive fallback 失败不进 LOST（design line 2865 明确 "LOST 只属于 Phase 11 recovery / positive orphan proof owner"）。

### 5.3 连续 overflow 上限

Plan 明确：
- 连续 reactive overflow 达上限 -> 写最终 CONTEXT_COMPACTION_FAILED(failure_reason=reactive_compact_limit_reached, fallback_action=fail_closed) -> RUN_FAILED
- 不创建新 Attempt
- 不进 RUN_LOST

符合设计"超过 max_reactive_compactions_per_run 后 fail closed"（design line 2878）。

## 6. Slice 质量审查

### Slice A：默认 policy/config/model 对齐
- 文件 ownership 清楚：`context_policy.py`、`execution_profiles.json`、`conversation_compaction.json`、四组测试
- 变更范围控制良好：只改默认常量、packaged profile 字段、compaction scene model
- 验证闭环：Host fallback 默认、execution profile 默认、assembled Host policy 默认三者均为 5
- Stop condition：若需要新增 config schema 字段表达 compactor default precedence，停止 ✓

### Slice B：CONTEXT_COMPACTION_FAILED payload 诊断补足
- 变更集中在 `context_events.py` builder/validator
- 不改变状态机
- 测试覆盖无 fallback、fallback dispatch、fallback fail closed、非法值
- Stop condition：若需要读取旧 failed payload 兼容，停止 ✓

### Slice C：Proactive deterministic recent-window fallback
- 新增 `context_fallback.py` 为全新内部模块，职责单一
- `RunInputBuilder` 变更仅限内部 provider 注入，默认 no-op
- 状态路径清晰
- Stop condition：若 RunInputBuilder 需要 public request 参数，停止 ✓

### Slice D：Reactive fallback recovery path
- 复用 Slice C 的 `context_fallback.py`
- `durable/run_transition.py` 变更限定为最小修改
- Stop condition：若需要伪造 context_compacted_event_id 为非 null，停止 ✓

### Slice E：Continuous reactive overflow dispatch-loop E2E
- 新增确定性 fake worker factory
- 通过 scheduler drain/explicit wait helper 收敛，禁止 sleep
- 断言 Attempt 数、compact events、terminal 状态
- Stop condition：若只能通过竞态时间等待，停止 ✓

### Slice 依赖关系

A -> B -> C -> D -> E 是合理的递增构建顺序。A 建立默认值基线；B 建立 payload 诊断能力（C/D 的 diagnostic 产出依赖 B）；C 实现 proactive fallback；D 在 C 基础上实现 reactive fallback；E 验证整体闭环。

## 7. Test Coverage 审查

| 验收项 | Plan 覆盖位置 |
|---|---|
| 默认 5（Host fallback + profiles + assembly） | Slice A：`test_context_policy.py`、`test_config_loader.py`、`test_scene_assets_migration.py`、`test_host_assembly.py` |
| Scene/profile model 一致性 | Slice A：`conversation_compaction.model.default_model_id == compactor_baseline.model_id` |
| Fallback dispatch / fail closed | Slice C/D：proactive compactor missing + fallback budget pass/fail；reactive compactor missing + fallback budget pass/fail |
| 连续 overflow E2E | Slice E：`test_reactive_repeated_overflow_dispatch_loop_fails_closed_at_limit` |
| pyright | Section 8 验证命令覆盖 |
| README sync | Section 9 触发规则和职责说明 |

## 8. Residual Risk 与 Blocking Question 审查

### Residual Risk Owner

| Risk | Owner | 状态 |
|---|---|---|
| RR-CTX-PLAN-01 fallback contract 边界 | WU-CTX-02 implementation owner | resolved-by-plan |
| RR-CTX-PLAN-02 estimator failure | WU-CTX-02 Slice B/C/D | covered-by-slices |
| RR-CTX-PLAN-03 overflow E2E 稳定性 | WU-CTX-03 Slice E | covered-by-slice |
| fallback message rendering 遗漏上下文 | WU-CTX-02 implementation + code review | current WU risk |
| EventLog payload 增补影响 read model | WU-CTX-02 implementation + aggregate review | current WU risk |
| README 漂移 | implementation owner | current WU risk |

所有 residual risk 有明确 owner 和处理方式。

### Blocking Questions

Plan Section 5 和 Section 13 均声明 "Blocking Questions For Controller: none"。经审查确认：
- 不需新增 public contract 字段
- 不需改设计真源
- 状态机路径与设计一致
- Stop conditions 覆盖了所有已知阻断场景

Blocking questions 确实为 none。

---

## Findings

### 1-未修复-中-Slice C fallback "最新 N 轮" 选择参数不完全由现有 policy 派生

- **Plan位置**: Section 6 Slice C / Section 5
- **问题类型**: 实现不确定性
- **计划当前写法**: "fallback policy 第一版使用 Host 内部默认与现有 `MemoryProjectionPolicy.recent_raw_turns_floor` / material block 边界派生"
- **为什么有问题**: 设计真源（line 2722）要求 fallback input view 包含"最新 N 轮 raw turns、至少 M 轮 recent raw floor"。`recent_raw_turns_floor` 只能提供 floor M，无法提供"最新 N 轮"的 ceiling N。Plan 未说明 N 如何从现有 policy 或 internal default 派生，也未给出 N 的默认值或派生规则。Implementation agent 可能在缺乏指引的情况下引入任意 N 值或触发 stop condition。
- **直接证据**:
  - design.md:2722："最新 N 轮 raw turns、至少 M 轮 recent raw floor"
  - design.md:95：`MemoryProjectionPolicy` 包含 `recent_raw_turns_floor`，但不包含 "max_recent_raw_turns_for_fallback" 或等价字段
  - Plan Section 5："不新增 public `ContextBudgetPolicy` 字段"
- **影响**: Implementation agent 需要在 fallback 选择算法中决定 N，可能选择任意值、触发 stop condition 回到 controller，或在无充分约束的情况下引入不一致行为。
- **建议改法和验证点**:
  1. 在 plan 中为 N 增加 explicit internal default（例如 N = `recent_raw_turns_floor` * 2 或 N = policy 中已有的 raw turn cap），保持 Host 内部派生，不新增 public field；
  2. 或在 Slice C 的 allowed changes 中明确"若需要确定 N 的上界且无现有 policy 字段可派生，使用 internal constant `DEFAULT_FALLBACK_MAX_RECENT_RAW_TURNS`，不从 public policy 读取"；
  3. 验证点：fallback selection 测试应断言选中的 raw turns 数 ≤ N 且 ≥ M。
- **修复风险**: 低 — 只需在 plan 中明确派生规则，不改变 scope 或 public contract
- **严重程度**: 中 — 不修复不会导致实现错误，但可能导致 implementation agent 在 fallback 核心选择算法上做出无约束决策

### 2-未修复-低-Slice A 未验证 scene manifest 变更对其他 scene 的继承影响

- **Plan位置**: Section 7 Slice A
- **问题类型**: 测试覆盖缺口
- **计划当前写法**: Slice A Non-goals："不改普通 scene 默认模型；不新增 high-spec allow-list"
- **为什么有问题**: `conversation_compaction` scene 的 `model.default_model_id` 从 `mimo-v2.5-pro-thinking-plan` 改为 `deepseek-v4-flash`。当前所有 scene 的 `extends` 均为空数组，因此实际无继承影响（已直接验证）。但 plan 的配置一致性测试未包含"无 scene 继承 conversation_compaction 并依赖其旧 model_id"的断言。若未来新增 scene 继承了 conversation_compaction，可能意外获得 flash-tier 模型。
- **直接证据**:
  - `dayu/config/prompts/manifests/*.json`：所有 scene extends 均为空数组
  - Plan Section 7 Slice A tests："scene asset 测试断言 `conversation_compaction.model.default_model_id == compactor_baseline.model_id`"
- **影响**: 当前实际场景中无影响（不存在继承链），但测试不防御未来配置漂移。
- **建议改法和验证点**:
  1. Slice A 测试增加断言：所有 scene manifest 的 extends 不包含 `conversation_compaction`，或等价于验证 conversation_compaction 不作为其他 scene 的 base；
  2. 或标记为 non-goal（当前 extends 均为空，属于配置事实，非设计约束），并在 plan 的 risk 中记录"若未来引入继承，需回归验证"；
  3. 验证点：运行 scene assets 测试时检查该断言。
- **修复风险**: 低 — 当前无继承链，增加防御性断言不产生副作用
- **严重程度**: 低 — 当前实际场景中无影响

### 3-未修复-低-Slice D durable/run_transition.py 修改边界依赖停止条件

- **Plan位置**: Section 4 Allowed files / Section 7 Slice D
- **问题类型**: 实现风险（已有 stop condition 兜底）
- **计划当前写法**: "仅在 reactive fallback recovery start 需要把 failed diagnostic ref 写入 `RUN_STARTED` payload 时允许最小修改；若需要改变 public request contract，停止"
- **为什么有问题**: `RUN_STARTED` payload 是 durable schema 的一部分。将 fallback diagnostic ref 写入 `RUN_STARTED` payload 本质上改变了该 payload 的语义——从"启动原因"扩展到"携带前次 fallback 诊断"。若实现需要修改 `RUN_STARTED` 的 typed payload dataclass、durable row codec 或 EventLog schema validator，则触发了"改变 public contract"的 stop condition。Plan 已识别这一风险并设置了 stop condition，但 implementation agent 需要精确理解"最小修改"的边界：只能在现有 payload 可选字段中附加 diagnostic ref，不能新增 required field、不能改 row schema。
- **直接证据**:
  - Plan Section 7 Slice D Stop condition："若 recovery transition 必须把 `context_compacted_event_id` 伪造成 non-null 才能启动，停止"
  - Plan Section 7 Slice D Functions："如需扩展 `StartRecoveryRunInput` payload 仅限内部 typed diagnostic 字段"
  - design.md:2851："append RUN_STARTED(start_reason=recovery)"
- **影响**: 若实现 agent 误解"最小修改"边界，可能引入 durable schema 变更。Stop condition 已覆盖，但 plan 对"最小修改"的具体约束可以更精确。
- **建议改法和验证点**:
  1. 在 Slice D Exact allowed changes 中明确：只能在 `StartRecoveryRunInput` 的现有 optional diagnostic 字段中附加 fallback ref，不得新增 required field、不得修改 durable table schema、不得改变 `RUN_STARTED` payload validator 的 required field 集合；
  2. 补充 stop condition：若修改涉及 SQLite schema、EventLog required field 或 public typed payload class 的 required 字段，停止；
  3. 验证点：pyright + 现有 `RUN_STARTED` payload 测试必须通过。
- **修复风险**: 低 — 增加精确约束不改变 scope，只降低实现走偏的概率
- **严重程度**: 低 — stop condition 已兜底

### 4-未修复-低-Fallback budget re-estimate 使用 conservative estimator 的兼容性未验证

- **Plan位置**: Section 6 Slice C
- **问题类型**: 实现假设
- **计划当前写法**: "fallback selection 生成后必须调用现有 conservative estimator，使用 selected material block text 与 current input anchor 作为 `BudgetEstimateInput.message_fragments`"
- **为什么有问题**: 现有 conservative estimator 是为 ordinary RunInputBuilder 的完整 material blocks 设计的。Fallback 选择的 bounded input view 是 material blocks 的子集，形状可能与 ordinary input 不同（例如去掉了部分 older raw turns、去掉了 compacted summary block）。Plan 假设 estimator 可以直接接收 fallback-selected block text，但未确认 estimator 的输入接口是否支持这种部分选择输入、是否会对缺失的 block category 产生异常。
- **直接证据**:
  - Plan Section 6 Slice C Data flow："proactive material blocks -> fallback selection -> budget estimate"
  - Plan Section 11 RR-CTX-PLAN-02："post-compact estimator failure 独立路径" 标记为 "covered-by-slices"
  - RR-CTX-PLAN-02 原讨论要求"进一步核对 estimator / candidate budget 数据流和测试入口"
- **影响**: 若 estimator 对 fallback-selected block shape 不兼容，实现时可能需要对 estimator 做适配（潜在扩大 scope）或引入新的估算路径。
- **建议改法和验证点**:
  1. 在 Slice C 实现前优先验证：现有 conservative estimator 是否接受任意 `message_fragments` 列表输入（不要求特定 block category 完整性）；
  2. 若不兼容，在 Slice C 的 allowed changes 中允许对 estimator 做最小适配（不改变估算算法，只放宽输入约束）；
  3. 验证点：fallback 后预算估算测试覆盖 normal、edge（空 stable_input）、over-budget 三种场景。
- **修复风险**: 低 — 优先验证 + 最小适配
- **严重程度**: 低 — RR-CTX-PLAN-02 已在讨论阶段标记 needs-more-evidence，plan 将其标记为 covered-by-slices 但未提供独立验证路径

---

## Conclusion

**结论：PASS** — Plan 为 handoff-ready / code-generation-ready。

Plan 严格对齐设计真源第 1 节和第 25 节，动机基于直接代码核对证据，scope 不越界到 provider tokenizer、Engine retry、memory projection redesign 或 public contract。Fallback policy 正确区分 compact success 与 deterministic recent-window fallback，状态机 proactive 不进 RECOVERING、reactive 不进 LOST。Slices 沿稳定模块边界切分，A 到 E 有清晰的依赖关系和可独立验证的行为闭环。Stop conditions 覆盖全部已知越界风险。

**4 findings**：1 中（fallback N 参数）、3 低（scene 继承防御、run_transition 边界、estimator 兼容性）。中 severity finding 建议在 handoff 前明确 N 的派生规则；3 个低 severity finding 不阻塞实现。

### Residual risks 需实现/code review 持续关注

1. Fallback 最新 N 轮 ceiling 参数派生（Finding 1）：implementation agent 需在有约束条件下做出选择
2. Estimator 对 fallback block shape 的兼容性（Finding 4）：实现前先验证
3. Durable/run_transition.py 修改边界（Finding 3）：避免引入 durable schema 变更
4. Plan Section 11 中的 3 个 current WU risks 需要 code review 和 aggregate deepreview 验证

### Test gaps（优先通知 implementation agent）

1. Scene manifest `extends` 影响防御（Finding 2）：建议增加防御性断言
2. Fallback budget re-estimate edge case：empty stable_input 时估计器行为
3. Fallback selection determinism：相同 input cursor / material list 产生相同 selected block ids

### Blocking questions：none（确认）

---

- **Artifact path**: `docs/reviews/wu-ctx-02-03-plan-review-ds-20260601.md`
- **Conclusion**: PASS
- **Findings count**: 4（1 中、3 低）
- **Blocking questions**: 0
