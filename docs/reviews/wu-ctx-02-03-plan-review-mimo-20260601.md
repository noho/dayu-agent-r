# WU-CTX-02 + WU-CTX-03 Plan Review (MiMo)

## 1. Review 结论

**conclusion: pass**

plan handoff-ready / code-generation-ready，可进入 implementation gate。

findings 数量：0 个 blocking finding，3 个低风险 observation（不阻塞 handoff）。

residual risks 有 owner，blocking questions 为 none。

## 2. Review 依据

- design source 第 1 节：Host 是 context governance 治理真源，Engine 不拥有 Host 状态。
- design source 第 25 节：Context Governance 属于 Host；compact repair / retry bounded；budget 耗尽后只写一个最终 `CONTEXT_COMPACTION_FAILED`；deterministic recent-window fallback 不是 compact 成功；proactive failure 不进入 `RECOVERING`；reactive failure 不进入 `LOST`；`max_compaction_attempts_per_operation` 默认 packaged policy 为 5。
- control document WU-CTX-02 / WU-CTX-03 目标、非目标、验收信号。
- code inspection 直接证据：`context_policy.py` 默认 2、`execution_profiles.json` profiles 为 3、scene model 为 high-spec、`dispatch.py` / `engine_ingest.py` 无 fallback、`context_events.py` failed payload 字段不足、scheduler 无连续 overflow E2E。
- controller adjudication：DISC-01 到 DISC-05 accepted；provider tokenizer adapter、Engine overflow retry、memory projection redesign、旧兼容均不纳入。

## 3. 逐项审查

### 3.1 Motivation 是否基于直接证据

**通过。**

Plan 的 motivation 列出 5 个缺口，每个都有直接代码证据支撑：

| 缺口 | 直接证据 |
|---|---|
| 默认 attempt budget 未对齐 5 | `context_policy.py:22` 常量为 2；`execution_profiles.json` profiles 为 3 |
| scene/profile compactor model 不一致 | scene manifest `mimo-v2.5-pro-thinking-plan` vs profile `deepseek-v4-flash` |
| 无 deterministic recent-window fallback | `dispatch.py:1113-1128` 和 `engine_ingest.py:1530-1564` 直接 fail closed |
| failed payload 缺诊断字段 | `context_events.py:382-431` 只有 failure_reason / policy_decision / retryable / diagnostic_refs / budget_after_attempted_compact |
| 缺连续 overflow dispatch-loop E2E | scheduler 只有单次 recovery E2E |

不存在被高估的缺口。已覆盖项（bounded repair loop、reactive identity 校验、不进 LOST 等）均列在"已覆盖风险，不重复做"部分，有测试证据。

### 3.2 Scope 是否越界

**通过。**

Plan 的 non-goals 与 controller adjudication 完全对齐：

- 不引入 provider tokenizer adapter。
- 不把 overflow retry 放进 Engine。
- 不重写 memory projection / evidence-backed fact / compact candidate accept barrier。
- 不做旧 schema / 旧 profile / 旧 payload 兼容逻辑。
- 不重做 recovery / positive orphan proof。

Plan 未越界到 public contract：明确"不新增 Service-facing public API，不改变 `open_host(options)`、`SubmitFollowupRequest`"。fallback policy 第一版使用 Host 内部默认与现有 `MemoryProjectionPolicy.recent_raw_turns_floor` / material block 边界派生，不新增 public `ContextBudgetPolicy` 字段。

Stop conditions 设计合理：若 implementation agent 发现必须新增 public policy 字段，必须停止并交回 controller。

### 3.3 Fallback policy 是否绕过 design_doc

**通过。**

Plan 的 fallback 实现路径对齐 design doc 第 25 节：

- fallback 不是 compact 成功：不写 `CONTEXT_COMPACTED`、不写 memory projection、不生成 stable facts。
- fallback 必须写 `CONTEXT_COMPACTION_FAILED`，记录 fallback policy decision、fallback input window / digest、budget result。
- fallback 后重新估算预算；仍超 hard threshold 则 fail closed。
- proactive fallback 成功不进入 `RECOVERING`。
- reactive fallback 成功创建新 recovery Attempt，旧 Attempt 不 resume。
- reactive fallback 失败写 `RUN_FAILED`，不 `RUN_LOST`。

Plan 明确 fallback 不被误当 compact success：`fallback_input_window` 是结构化诊断，不是 raw prompt；不包含 API key、headers、完整 provider payload 或无界 raw text。

### 3.4 CONTEXT_COMPACTION_FAILED payload 设计

**通过。**

Plan 的目标字段完全覆盖 design doc 第 25 节要求：

| Design doc 要求 | Plan 字段 |
|---|---|
| operation id | `operation_id: str` |
| failure reason | `failure_reason: str` |
| policy decision | `policy_decision: str` |
| whether retryable | `retryable: bool` |
| attempt count | `attempt_count: int` |
| retry/repair budget exhausted | `retry_repair_budget_exhausted: bool` |
| diagnostic refs | `diagnostic_refs: list[str]` |
| fallback input window / digest | `fallback_input_window: object \| null`、`fallback_input_digest: str \| null` |
| fallback budget result | `fallback_budget_result: object \| null` |
| fallback action | `fallback_action: "dispatch" \| "fail_closed" \| "not_applicable"` |

额外字段 `budget_after_attempted_compact` 和 `fallback_policy_decision` 用于增强诊断，不违反 design doc。

`fallback_input_window` 建议包含 `selected_block_ids`、`dropped_block_ids`、`current_input_ref`、`source_refs`、`recent_raw_turns_floor`、`trigger_source`、`policy_ref`。这些字段足以解释 fallback 的输入选择，且不含敏感 raw payload。

Plan 明确了 attempt_count 计数规则：precondition / missing compactor failure 使用 `attempt_count=0`；operation failure 使用 rejected attempt count；stale result 不标记 exhausted 除非 operation result 已明确耗尽。

### 3.5 Proactive / Reactive 状态机

**通过。**

Plan 的状态机路径与 design doc 第 25.1 节完全对齐：

**Proactive fallback 成功：**
```
RUN_ACCEPTED|RUN_QUEUED
  -> CONTEXT_COMPACTION_REQUESTED
  -> CONTEXT_COMPACTION_FAILED(fallback_action=dispatch)
  -> RUN_STARTED(start_reason=initial|queue_promotion)
  -> ATTEMPT_STARTED
  -> dispatch
```
不进入 `RECOVERING`。符合 design doc："proactive compact failure 在 dispatch 前优先尝试 deterministic recent-window fallback；fallback 预算通过时允许创建 Attempt...不得进入 `RECOVERING`"。

**Proactive fallback 失败：**
```
... -> CONTEXT_COMPACTION_FAILED(fallback_action=fail_closed) -> RUN_FAILED
```
不创建 Attempt。符合 design doc。

**Reactive fallback 成功：**
```
RUNNING/Attempt RUNNING
  -> CONTEXT_COMPACTION_REQUESTED(trigger_source=reactive)
  -> ATTEMPT_FAILED
  -> RUN_RECOVERING
  -> CONTEXT_COMPACTION_FAILED(fallback_action=dispatch)
  -> RUN_STARTED(start_reason=recovery)
  -> ATTEMPT_STARTED
  -> dispatch
```
不写 `CONTEXT_COMPACTED`。符合 design doc："reactive compact failure 发生时当前 Attempt 已按 policy 关闭；Host 可按 policy 尝试 deterministic recent-window fallback，并创建新的 recovery Attempt"。

**Reactive fallback 失败：**
```
... -> CONTEXT_COMPACTION_FAILED(fallback_action=fail_closed) -> RUN_FAILED
```
不 `RUN_LOST`。符合 design doc："`LOST` 只属于 Phase 11 recovery / positive orphan proof owner"。

**连续 reactive overflow 达上限：**
写最终 `CONTEXT_COMPACTION_FAILED(failure_reason=reactive_compact_limit_reached)`，Run `FAILED`，不再创建新 Attempt。符合 design doc："超过上限后 append `CONTEXT_COMPACTION_FAILED`...不得进入 `LOST`，不得无限 compact retry"。

### 3.6 Slice 切分

**通过。**

5 个 slice 按依赖边界切分，每个 slice 有明确的 objective、allowed files、allowed changes、functions/classes/types、data flow、state transition、error handling、invariants、tests/validation、non-goals、completion signal 和 stop condition。

| Slice | 依赖 | 交付物 |
|---|---|---|
| A: 默认 policy/config/model 对齐 | 无 | 默认 5 一致、compactor model flash-tier |
| B: FAILED payload 诊断补足 | A | failed payload 字段完整 |
| C: Proactive fallback | B | proactive fallback dispatch + fail closed |
| D: Reactive fallback | B, C | reactive fallback dispatch + fail closed |
| E: Continuous overflow E2E + docs | C, D | dispatch-loop E2E、README sync |

File ownership 清楚：每个 slice 的 allowed files 明确列出，implementation agent 可直接执行。

Slice C 给 `RunInputBuilder` 增加可选内部 `ContextFallbackProvider`（默认 no-op），不改变 public interface，符合 architecture constraint。

### 3.7 Tests 覆盖

**通过。**

Plan 的测试覆盖与 WU-CTX-02 / WU-CTX-03 验收信号对齐：

| 验收信号 | 测试覆盖 |
|---|---|
| 默认 retry budget 为 5 | Slice A：断言 Host fallback、packaged profiles、Service assembly 默认一致为 5 |
| 默认 compact model flash-tier | Slice A：断言 `conversation_compaction.model.default_model_id == compactor_baseline.model_id` |
| failed payload 诊断完整 | Slice B：builder 单测覆盖无 fallback、fallback dispatch、fallback fail closed、非法负数/非法 action |
| proactive fallback dispatch | Slice C：compactor missing + fallback budget pass creates one Attempt and no compacted event |
| proactive fallback fail closed | Slice C：fallback budget fail keeps zero Attempt and Run failed |
| reactive fallback dispatch | Slice D：compactor missing + fallback budget pass creates second Attempt with new ids |
| reactive fallback fail closed | Slice D：fallback over-budget writes `RUN_FAILED` and `RUN_LOST` count 0 |
| fallback 不伪造 stable facts | Slice C/D：memory projection test or scheduler assertion 断言无 stable fact 物化 |
| 连续 overflow 不无限循环 | Slice E：`test_reactive_repeated_overflow_dispatch_loop_fails_closed_at_limit` |
| terminal diagnostic | Slice E：断言 compact request / compacted / failed / Attempt / terminal 数 |
| pyright | 最终验证 `python -m pyright dayu/ tests/ utils/` |
| README sync | Slice E：按触发规则检查 `dayu/host/README.md`、`dayu/config/README.md`、`tests/README.md` |

### 3.8 Residual risks / blocking questions

**通过。**

| Risk | Owner | 状态 |
|---|---|---|
| RR-CTX-PLAN-01 fallback policy public contract | WU-CTX-02 implementation owner | resolved-by-plan：第一版使用 Host 内部默认 |
| RR-CTX-PLAN-02 post-compact estimator failure | WU-CTX-02 Slice B/C/D | covered-by-slices：failed payload 增补预算结果 |
| RR-CTX-PLAN-03 连续 overflow E2E 稳定性 | WU-CTX-03 Slice E | covered-by-slice：使用确定性 fake worker |
| fallback message rendering 遗漏 | implementation + code review | current WU risk：通过测试约束 |
| EventLog failed payload 增补影响 | implementation + aggregate review | current WU risk：只增结构化字段 |
| README 漂移 | implementation owner | current WU risk：按触发规则检查 |

所有 residual risk 有 owner，无 blocking open questions。

## 4. Observations（不阻塞 handoff）

### OBS-01-[低]-fallback policy 具体参数未在 plan 中固定

- **Plan位置**: Slice C: "从 ordinary material blocks / frozen reactive material blocks 中确定性选择 fallback 输入窗口。选择必须保留 current input anchor、已有 stable / compact represented context、最近 raw turn floor"
- **问题类型**: 实现细节未明确
- **计划当前写法**: Plan 引用 `recent_raw_turns_floor` 和 material block 边界作为 fallback window 的选择依据，但未指定 N（最近 raw turns 数量）和 M（recent raw turns floor 下限）的具体值或派生规则
- **为什么有问题**: 5 个 slice 的 implementation agent 需要一致理解 fallback window 的选择逻辑；若各 slice 各自假设不同的 N/M 值，可能导致测试不一致
- **直接证据**: Design doc 第 25 节只说"最新 N 轮 raw turns、至少 M 轮 recent raw floor"，未给出具体值
- **影响**: 低。Host 内部默认可从现有 `MemoryProjectionPolicy.recent_raw_turns_floor` 派生，implementation agent 可在 Slice C 中确定具体值并作为内部常量
- **建议改法和验证点**: Slice C 实现时应在 `context_fallback.py` 中定义内部常量或从 policy 派生的计算逻辑，并在测试中明确断言 fallback window 的 block count 和 floor
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### OBS-02-[低]-Slice B 的 fallback 字段初始值与 Slice C/D 的衔接

- **Plan位置**: Slice B: "fallback fields 初始为 `null` / `not_applicable`"
- **问题类型**: Slice 间 contract 衔接
- **计划当前写法**: Slice B 先把 fallback 相关字段设为 null / not_applicable，Slice C/D 再填充实际值
- **为什么有问题**: 这是合理的增量实现策略，但 plan 未明确 Slice B -> C/D 的 contract：哪些字段在 B 中必须存在但可为 null，哪些在 C/D 中必须被填充
- **直接证据**: Plan Slice B 的 data flow 写明"fallback fields 初始为 `null` / `not_applicable`"；Slice C/D 的 functions 列出了填充这些字段的 helper
- **影响**: 低。字段定义已在 payload contract 中明确，null / not_applicable 是合法初始值
- **建议改法和验证点**: Slice C/D 实现时确保所有 fallback 路径都填充完整的 fallback 字段，validator 测试覆盖 fallback 路径的完整 payload
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### OBS-03-[低]-Slice D recovery transition 与 existing code 的接口边界

- **Plan位置**: Slice D: "`_StartReactiveRecoveryOperation` 可泛化为接受 compacted event ref 可空和 failed fallback ref 诊断"
- **问题类型**: 接口扩展边界
- **计划当前写法**: Plan 允许泛化 `_StartReactiveRecoveryOperation` 接受 compacted event ref 可空和 failed fallback ref，但未明确是否需要改变函数签名或新增参数
- **为什么有问题**: Slice D 的 stop condition 写明"若 recovery transition 必须把 `context_compacted_event_id` 伪造成 non-null 才能启动，停止"，说明 plan 已意识到这个风险
- **直接证据**: `dayu/host/engine_ingest.py` 中 `_complete_reactive_recovery_after_compact` 当前依赖 compacted event id；plan 允许新增 `_complete_reactive_recovery_after_fallback` 或泛化现有函数
- **影响**: 低。Plan 的 stop condition 已覆盖此风险；implementation agent 可选择新增函数或泛化现有函数
- **建议改法和验证点**: Slice D 实现时优先尝试新增独立函数 `_complete_reactive_recovery_after_fallback`，避免修改现有稳定路径的签名；若必须泛化，确保现有 reactive compact success 路径的测试不 regression
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## 5. Residual Risks

| ID | 状态 | Owner / Destination | 处理 |
|---|---|---|---|
| RR-CTX-PLAN-01 | resolved-by-plan | WU-CTX-02 implementation owner | 第一版使用 Host 内部默认和现有 memory policy 派生 |
| RR-CTX-PLAN-02 | covered-by-slices | WU-CTX-02 Slice B/C/D | failed payload 增补预算结果；fallback 后强制重估 |
| RR-CTX-PLAN-03 | covered-by-slice | WU-CTX-03 Slice E | 使用确定性 fake worker / scheduler helper |
| fallback message rendering | current WU risk | implementation + code review | 通过测试约束 |
| EventLog failed payload 增补 | current WU risk | implementation + aggregate review | 只增结构化字段 |
| README 漂移 | current WU risk | implementation owner | 按触发规则检查 |

## 6. Blocking Questions

none

## 7. 总结

Plan 基于直接证据，动机成立，scope 不越界，fallback policy 不绕过 design doc，payload 设计可验证且不过度暴露 raw payload，proactive / reactive 状态机符合 design doc，slice 足够小且 file ownership 清楚，tests 覆盖全部验收信号，residual risks 有 owner，blocking questions 为 none。

3 个低风险 observation 不阻塞 handoff，implementation agent 可在实现过程中自行处理。

本 plan 是 handoff-ready / code-generation-ready。
