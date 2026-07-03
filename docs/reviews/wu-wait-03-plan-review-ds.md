# WU-WAIT-03 Plan Review — AgentDS

- **Review agent**: AgentDS
- **Reviewed artifact**: `docs/host/wu-wait-03-external-job-lifecycle-plan.md`
- **Design sources**: `docs/host/design.md`, `docs/engine/design.md`
- **Control source**: `docs/host/issues-implementation-control.md`
- **Review date**: 2026-07-03 10:55 UTC+8
- **Gate**: plan review

---

## Review Scope

对 WU-WAIT-03 / GitHub issue-92 的 implementation plan 做严格 adversarial plan review，重点检查：

1. Plan 是否 code-generation-ready
2. 动机与 root cause 是否正确评估
3. Host/Engine 边界是否严格对齐
4. 是否存在过度设计
5. Slice 切分是否合理
6. Contract/schema/state-machine 变更是否自洽
7. 测试矩阵覆盖是否充分
8. README/docs 触发规则是否 correct

---

## Assumptions Tested

| # | Assumption | Verdict | Evidence |
|---|---|---|---|
| A1 | Host cancellation correctness 已由 durable state machine 保证，当前缺口只是 external lifecycle diagnostic | **成立** | `cancel_waiting_run_in_transaction` (run_transition.py:2280-2367) 在同一事务内 CAS 标记 active wait records cancelled 并 append `RUN_CANCELLED`，不调用 adapter；`_cancel_waiting` (admission.py:1850-1911) 只调用 durable transition |
| A2 | `WaitPollAdapter.abandon_wait(...) -> None` 结果表达过粗 | **成立** | wait_adapter.py:119-127 协议只返回 `None` 或抛异常；`_abandon_cancelled_wait` (wait_adapter.py:867-932) 只能区分 success（mark abandoned）和 exception（ABANDON_ERROR backoff） |
| A3 | Fins cancel_observation / abandon_observation 是 best-effort | **成立** | ingestion_runtime.py:2321-2349 cancel_observation docstring 明确 "取消是 best-effort，不承诺中断不可取消的 blocking call"；abandon_observation docstring 明确 "只清理本地 observation 记录" |
| A4 | resolve_wait 仍是 late result 唯一路径 | **成立** | host/design.md:2366 规定 poll adapter 完成时调用同一个 resolve_wait；cancelled wait 的迟到结果通过 WAIT_LATE_RESULT_REJECTED diagnostic 拒绝 |
| A5 | Host command cancel path 不做 provider I/O | **成立** | admission.py `_cancel_waiting` 和 `_cancel_waiting_target` 只调用 `cancel_waiting_run_in_transaction`，不引用任何 adapter |
| A6 | 不需要新的 durable table/columns | **成立** | 当前 `WaitRecordRow` (state.py:429-471) 已有 `status`, `poll_last_outcome`, `poll_abandoned_at`, claim/backoff 字段；缺失的只是 result classification |
| A7 | 不需要 provider capability registry | **成立** | Adapter 可以通过返回 `Unsupported` 表达；Host 不需要知道 provider-specific physical cancel API |
| A8 | 2 slices 足够覆盖本 WU | **部分成立** | 见 Finding F02 |

---

## Findings

### F01 — [HIGH] `WaitPollLastOutcome` enum 新增缺少明确的 schema/serialization/test 处理路径

- **位置**: Plan Contract/Schema 节 (line 99-102)、Slice 1 Exact changes (line 158)
- **问题类型**: 契约缺失 / 不可直接实施
- **当前写法**: Plan 写 "Add `WaitPollLastOutcome` values only if needed for durable diagnostic precision: `ABANDON_UNSUPPORTED`, `ABANDON_NOOP`"，Slice 1 写 "If adding ... update serialize / deserialize validation and row invariant checks"
- **反例/失败场景**: Implementation agent 读取 "only if needed" 后需要自行裁决是否添加。若添加，需要在至少 3 处做一致性变更：
  1. `WaitPollLastOutcome` enum 定义 (state.py:177-186)
  2. `mark_wait_record_poll_abandoned` 当前 **硬编码** `WaitPollLastOutcome.ABANDONED` (state.py:2249-2250)，unsupported/noop 路径不能复用同一个 mutation
  3. `_validate_wait_poll_fields` (state.py) 的行级不变量校验
- **为什么有问题**: "only if needed" 的模糊表述将设计决策推给 implementation agent。若不加新 enum 值，unsupported/noop 终端 diagnostic 必须复用现有 `ABANDONED`，这又回到 "结果表达过粗" 的 root cause。若加，plan 没有明确 `mark_wait_record_poll_abandoned` 是否需要参数化、`_validate_wait_poll_fields` 是否需要更新。
- **直接证据**:
  - state.py:2249-2250: `serialize_wait_poll_last_outcome(WaitPollLastOutcome.ABANDONED)` 硬编码在 `mark_wait_record_poll_abandoned` SQL UPDATE 中
  - state.py:177-186: `WaitPollLastOutcome` 当前只有 `ABANDONED`, `ABANDON_ERROR`，无 `ABANDON_UNSUPPORTED`, `ABANDON_NOOP`
  - plan line 99: "Add `WaitPollLastOutcome` values only if needed"
- **影响**: Implementation agent 自行设计 contract → review 发现不一致 → 返工；或 implementation agent 不加新值 → unsupported/noop 仍被归类为 ABANDONED → root cause 未修复
- **建议改法和验证点**:
  1. 明确裁决：是否添加 `ABANDON_UNSUPPORTED` 和 `ABANDON_NOOP`。基于 root cause "结果表达过粗"，建议**添加**
  2. 若添加，明确 `mark_wait_record_poll_abandoned` 需要参数化 `last_outcome: WaitPollLastOutcome` 参数，或为 unsupported/noop 创建独立的 release-with-terminal-outcome 路径（复用 `release_wait_record_poll_claim`）
  3. 明确 `_validate_wait_poll_fields` 是否需要更新
  4. 明确新 enum 值的 serialize/deserialize 不需要额外代码（`StrEnum` 自动支持），但需要在 `_validate_wait_poll_fields` 中确认新值可以通过 row decode
- **修复风险（低）**: 改动局限在 `state.py` 的 enum 定义和一个 mutation 函数签名
- **严重程度（高）**: 影响 code-generation-readiness；implementation agent 需要自行设计 contract

---

### F02 — [MEDIUM] Unsupported/noop 终端标记的 CAS 语义未明确定义

- **位置**: Plan State-machine changes (line 106-111)、Slice 1 State transitions (line 163-166)
- **问题类型**: 状态机漏洞
- **当前写法**: Plan 写 unsupported/noop 时 "mark no further lifecycle retry, using `poll_last_outcome=ABANDON_UNSUPPORTED` / `ABANDON_NOOP` if added"，但没有说明是否设置 `poll_abandoned_at`
- **反例/失败场景**: `claim_wait_record_for_poll` (state.py:2076) 的 WHERE 条件是 `status = ? AND poll_abandoned_at IS NULL`（cancelled 分支）。如果 unsupported/noop 只更新 `poll_last_outcome` 而不设置 `poll_abandoned_at`，下一次 poll round 该 cancelled wait record 会再次被 claim，导致无限重试 unsupported adapter。如果设置 `poll_abandoned_at`，需要决定是否修改 `mark_wait_record_poll_abandoned` 的 WHERE 条件（当前要求 `status = CANCELLED AND poll_abandoned_at IS NULL`）。
- **为什么有问题**: 这是 terminal marker 和 poll claim fencing 之间的语义耦合。plan 当前只说 "stop retrying"，但没有说明 CAS 层面如何实现 "stop retrying"——是通过 `poll_abandoned_at` 阻挡 re-claim，还是通过新 outcome 值在 claim 查询中过滤。
- **直接证据**:
  - state.py:2073-2077: claim 查询的 cancelled 分支依赖 `poll_abandoned_at IS NULL`
  - state.py:2229-2258: `mark_wait_record_poll_abandoned` 同时设置 `poll_abandoned_at` 和 `poll_last_outcome=ABANDONED`
  - plan line 109: "unsupported result -> mark no further lifecycle retry" 但不说如何实现
- **影响**: Implementation agent 可能漏掉 re-claim fencing → unsupported adapter 被反复调用 → 资源浪费或日志噪音
- **建议改法和验证点**:
  1. 明确 unsupported/noop 终端标记是否需要设置 `poll_abandoned_at`（建议设置，与 applied 路径一致，防 re-claim）
  2. 若设置，明确使用 `mark_wait_record_poll_abandoned` 参数化版本还是独立 mutation
  3. 若使用 `release_wait_record_poll_claim`（只更新 outcome 不设置 abandoned_at），必须说明为什么不需要防 re-claim，以及 claim 查询如何跳过已标记 unsupported/noop 的 record
  4. 在 Slice 1 测试中增加 "unsupported adapter 不会被第二次 claim" 的断言
- **修复风险（低）**: 建议使用参数化 `mark_wait_record_poll_abandoned`，改动局限在一个函数
- **严重程度（中）**: 不影响 plan 整体方向，但 implementation agent 需要明确指令

---

### F03 — [MEDIUM] Slice 1 边界允许修改 `dayu/host/durable/state.py` 但变更点未穷举

- **位置**: Plan Slice 1 Allowed files (line 141)、Exact changes (line 158)
- **问题类型**: 切片过粗 / 不可直接实施
- **当前写法**: Slice 1 allowed files 包含 `dayu/host/durable/state.py`，Exact changes 只说 "If adding ... update serialize / deserialize validation and row invariant checks"
- **反例/失败场景**: Implementation agent 发现 `mark_wait_record_poll_abandoned` 硬编码 `ABANDONED`，需要改为参数化版本，但 plan 没有说这个函数需要变更。Implementation agent 需要自行判断是改这个函数还是新写一个 mutation。如果改这个函数，所有现有调用者（`_abandon_cancelled_wait` in wait_adapter.py）需要同步更新。如果新写，需要在 `state.py` 新增函数和对应的 SQL。
- **为什么有问题**: `state.py` 是 durable mutation 真源，对其修改的影响面比 `wait_adapter.py` 大。plan 没有穷举 state.py 中需要修改的具体函数，implementation agent 需要自行探索。
- **直接证据**:
  - state.py:2229-2258: `mark_wait_record_poll_abandoned` 当前签名不接受 `last_outcome` 参数
  - wait_adapter.py:921-928: `_abandon_cancelled_wait` 调用 `_MarkWaitRecordAbandonedOperation`，后者调用 `mark_wait_record_poll_abandoned`
- **影响**: Implementation agent 可能只加 enum 值但漏改 mutation 函数 → 运行时 unsupported/noop 实际写入的 outcome 仍是 `ABANDONED` → 行为与 plan 不一致
- **建议改法和验证点**:
  1. Plan 显式列出 state.py 中需要修改的函数：`WaitPollLastOutcome` enum、`mark_wait_record_poll_abandoned`（参数化）、可能的 `_validate_wait_poll_fields`
  2. 明确 `mark_wait_record_poll_abandoned` 的新签名为 `mark_wait_record_poll_abandoned(transaction, *, wait_id, claim_id, abandoned_at, updated_at, last_outcome: WaitPollLastOutcome = WaitPollLastOutcome.ABANDONED)`
  3. 若 unsupported/noop 走不同 mutation 路径（release with terminal outcome），也需显式说明
- **修复风险（低）**: 只是 plan 文本补充，不涉及设计变更
- **严重程度（中）**: 影响 implementation agent 的变更边界认知

---

### F04 — [LOW] Fins adapter 的 corrupt/missing handle 场景与 `WaitExternalJobLifecycleResult` 映射关系未完全收敛

- **位置**: Plan Slice 2 Exact changes (line 217-220)
- **问题类型**: 契约缺失
- **当前写法**: Plan 写 corrupt handle → `WaitExternalJobLifecycleNoop(reason="invalid_observation_handle")`，missing observation → "call-safe and return no-op or applied abandon based on existing runtime behavior; test must document the chosen semantics"
- **反例/失败场景**: Missing observation（runtime 返回 LOST）场景，当前 `abandon_wait` 实现 (fins wait_adapter.py:140-157) 在 handle 为 None 时直接 `return`（即返回 None）。若 plan 将此映射为 `WaitExternalJobLifecycleNoop` 而非 `WaitExternalJobLifecycleApplied`，则与 "已经释放本地 observation record" 的实际情况一致。但 plan 写 "no-op **or** applied abandon"，留下二选一的歧义。
- **为什么有问题**: "test must document the chosen semantics" 把设计决策推给 implementation agent 在测试阶段裁决。这不符合 plan 应 code-generation-ready 的要求。
- **直接证据**:
  - fins wait_adapter.py:149-151: `handle is None` 时 `return`（当前返回 None）
  - fins wait_adapter.py:153-154: 正常 handle 时调用 `cancel_observation` + `abandon_observation`
  - plan line 219: "return no-op or applied abandon based on existing runtime behavior"
- **影响**: Implementation agent 需要在测试编写时回头补设计决策 → 可能选错 → review 返工
- **建议改法和验证点**:
  1. 明确裁决：missing observation handle → `WaitExternalJobLifecycleNoop`（因为没有 observation 可以 cancel/abandon）
  2. 理由：handle 不存在说明本地 observation 已释放或从未创建，不需要 further action
- **修复风险（低）**: 单行裁决
- **严重程度（低）**: 不影响整体架构，但增加 implementation agent 认知负担

---

### F05 — [LOW] 测试矩阵缺少 "unsupported/noop 后 CAS conflict" 和 "prepared cancel" 两项显式覆盖

- **位置**: Plan Slice 1 Tests/validation (line 184-189)、Slice 2 Tests/validation (line 243-248)
- **问题类型**: 测试缺口
- **当前写法**: Plan 列出了 applied/unsupported/noop/exception retry/missing adapter/shutdown 的场景覆盖，但没有显式覆盖：
  1. Adapter 返回 unsupported/noop 后 CAS conflict（与 abandon success 路径相同的 CAS race）
  2. Fins prepared observation cancelled before activation（即 `cancel_observation` 在 activation 前调用）
- **反例/失败场景**: 
  1. Adapter 返回 unsupported 后，poller 尝试 release claim with terminal outcome，但另一个 poller 或 supervisor 已修改该 record → CAS_LOST。当前 plan 的 error handling 只说 "CAS conflict after adapter returns does not rerun immediately"，但没有说 unsupported/noop 路径的 CAS conflict 处理方式是否与 applied/exception 路径相同。
  2. Fins prepared cancel 场景（issue-129 two-phase activation 相关）：prepared observation 被 cancel_observation 标记为 CANCELLED，随后 abandon_observation 释放。但 plan 的 Fins 测试没有显式覆盖这一路径。
- **为什么有问题**: 这两个场景都处于当前实现边界和 plan 覆盖之间的灰区。CAS conflict 在所有 abandon 路径上都可能发生，unsupported/noop 不应有不同行为，但 plan 未确认。Prepared cancel 是 Fins 两阶段激活的自然场景，应在 abandon 测试中覆盖。
- **直接证据**:
  - wait_adapter.py:930-932: 当前 `_abandon_cancelled_wait` 对 CAS_LOST 的处理是 `return 0, 0, 1, 0`（计为 claim_conflict）
  - ingestion_runtime.py:2341-2348: `cancel_observation` 对 prepared but not submitted observation 直接标记 CANCELLED
- **影响**: 边界行为未被验证，regression 保护不完整
- **建议改法和验证点**:
  1. 在 Slice 1 测试中确认 unsupported/noop 后的 CAS conflict 行为与 applied 路径一致：wait remains retryable
  2. 在 Slice 2 测试中显式覆盖 "prepared observation cancel + abandon" 场景
- **修复风险（低）**: 增加 2 个测试用例
- **严重程度（低）**: Non-blocking；现有测试基础已经覆盖 applied/exception/CAS conflict 路径，推理可以延伸到新路径

---

### F06 — [LOW] `WaitExternalJobLifecycleAction` enum 的 `CANCEL` vs `REVOKE` vs `ABANDON` 语义区分没有使用场景支撑

- **位置**: Plan Contract/Schema 节 (line 91-92)
- **问题类型**: 过度设计
- **当前写法**: Plan 定义 `WaitExternalJobLifecycleAction(StrEnum)`: `CANCEL`, `REVOKE`, `ABANDON`
- **反例/失败场景**: 当前 plan 只有一个调用路径：`_abandon_cancelled_wait` → adapter → lifecycle result。Fins adapter 当前执行 cancel + abandon 两个操作，但不区分 CANCEL/REVOKE/ABANDON。plan 没有定义三者的选择规则：哪个 adapter 应返回哪个 action？什么条件下用 REVOKE 而不是 CANCEL？
- **为什么有问题**: 定义了三个 action 值但只有一个 consumer（poller diagnostic），且 Fins 实现统一返回 ABANDON。REVOKE 在当前代码中没有对应语义。这是 future-proof 枚举膨胀。
- **直接证据**:
  - plan line 217: Fins adapter "preferred action is ABANDON"
  - plan line 91-92: 三个 action 值定义
  - 当前代码中无 REVOKE 语义
- **影响**: 类型系统多出未使用枚举值，增加维护者理解成本
- **建议改法和验证点**:
  1. 简化为 `ABANDON`（当前唯一使用场景）或 `ABANDON` + `CANCEL`（如果未来 provider 需要区分）
  2. 如果保留 REVOKE，必须在 plan 中给出具体使用场景和选择规则
- **修复风险（低）**: 仅删除枚举值
- **严重程度（低）**: Non-blocking；不影响正确性，只是接口膨胀

---

### F07 — [INFO] 2 Slice 结构合理，无机械按文件/owner 拆分或遗漏必要闭环

- **位置**: Plan Implementation Slices (line 132-257)
- **问题类型**: 切片合理性确认（非 defect）
- **当前写法**: Slice 1 聚焦 Host lifecycle contract + poller diagnostics；Slice 2 聚焦 Fins adapter mapping + provider tests
- **评价**: 两个 slice 沿稳定依赖边界切分（Host contract → provider adapter），各自形成可独立验证的行为闭环。Slice 1 产出 typed lifecycle contract + Host poller diagnostic 分类；Slice 2 产出 Fins adapter 映射 + provider-specific 测试。符合 control doc 的小型跨模块 cleanup 默认 1-3 slice 上限。Slice 1 触及 `wait_adapter.py` + `state.py` + 3 个测试文件是合理的语义闭环，不是机械按文件拆分。
- **直接证据**: 
  - Slice 1 闭环：contract → poller diagnostic → Host focused tests
  - Slice 2 闭环：Fins adapter mapping → provider runtime → Fins + Host focused tests
  - 两个 slice 都包含 allowed files、exact changes、state transitions、error handling、invariants、tests、completion signal、stop condition
- **严重程度**: 无（确认项）

---

## Architecture Boundary Review

逐项检查 plan 是否违反 Host/Engine 边界：

| 边界规则 | Plan 是否遵守 | 证据 |
|---|---|---|
| Engine 不拥有 wait/cancel/poll/external lifecycle | **遵守** | Plan Non-goals: "不修改 Engine awaiting public model"；plan line 19 |
| Host command cancel path 不做 provider I/O | **遵守** | Plan Implementation Decisions line 119: "Do not call provider adapter inside cancel_run" |
| resolve_wait 仍是 late result 唯一路径 | **遵守** | Plan Success signal line 14-15; plan State-machine changes line 112 |
| 不创建第二套 watchdog | **遵守** | Plan Non-goals line 23: "不创建 issue-87 之外的第二套 watchdog/runtime" |
| 不引入新的 public Host API | **遵守** | Plan line 85: "Host public API: no change" |
| 不引入新的 Engine contract | **遵守** | Plan line 83: "Public Engine contract: no change" |
| 不添加 durable schema columns | **遵守** | Plan line 87: "Durable DB schema: no table or column change" |
| Fins adapter 不写 Host EventLog | **遵守** | Plan Slice 2 invariants line 237-238 |

**结论**: Plan 在所有关键边界上严格对齐 Host/Engine 设计真源。

---

## Overengineering Review

检查 plan 是否引入了超出当前 issue 需要的设计元素：

| 可疑设计元素 | Plan 是否避免 | 裁决 |
|---|---|---|
| 新的 public Host API | 明确拒绝 | Plan line 85-86 |
| 新的 Engine contract | 明确拒绝 | Plan line 83 |
| 新的 durable table/columns | 明确拒绝 | Plan line 87 |
| provider capability registry | 明确拒绝 | Plan line 121 |
| 第二套 watchdog/runtime | 明确拒绝 | Plan line 23 |
| EventLog canonical facts for lifecycle | 明确拒绝 | Plan line 112 规定不创建 resume Attempt |
| 通用 scheduler/lease | 明确拒绝 | Plan line 118 复用 WaitPoller/WaitPollerSupervisor |
| `WaitExternalJobLifecycleAction.REVOKE` | 未充分论证 | 见 F06 |

**结论**: Plan 在结构层面有效避免了过度设计。F06 关于 `REVOKE` 枚举值是唯一的小规模接口膨胀。

---

## Open Questions

无 blocking open questions。以下为已收敛问题：

- Q1: `WaitPollLastOutcome.ABANDON_UNSUPPORTED` / `ABANDON_NOOP` 是否添加 → 建议添加（见 F01），等待 controller 裁决
- Q2: Unsupported/noop 是否设置 `poll_abandoned_at` → 建议设置（见 F02），等待 controller 裁决
- Q3: `WaitExternalJobLifecycleAction.REVOKE` 是否保留 → 建议移除（见 F06），等待 controller 裁决

---

## Residual Risks

| Risk | Severity | Owner/Destination |
|---|---|---|
| 某些真实 provider 不支持 physical cancel | 低 | Provider-specific Fins/source adapter owners under #92/#87；Host 通过 `Unsupported` 表达即可 |
| Poller disabled 部署不会执行 external lifecycle action | 低 | Service composition deployment + WU-WAIT-04 E2E smoke |
| Running Fins operation 只在 cooperative checkpoint 观察取消 | 低 | Fins provider/runtime owners；当前 WU 只做 best-effort request |
| Late result after unsupported/noop lifecycle mark | 极低 | 与 applied 路径相同：late result 仍走 resolve_wait → WAIT_LATE_RESULT_REJECTED |

---

## Verdict

**`pass-with-findings`**

- **Blocking findings**: 1 (F01)
- **Non-blocking findings**: 5 (F02, F03, F04, F05, F06)
- **Informational**: 1 (F07)

### Blocking Finding Summary

**F01 [HIGH]**: `WaitPollLastOutcome` enum 新增缺少明确的 schema/serialization/test 处理路径。Plan 的 "only if needed" 表述将 enum 设计与 `mark_wait_record_poll_abandoned` 参数化决策推给 implementation agent。必须明确裁决是否添加新 enum 值，并给出对应的 mutation 函数变更方案。

### Non-blocking Notes

- F02/F03: state.py 变更细节可在 controller 裁决 F01 时一并收敛
- F04: missing handle 映射可在 implementation 前一句话裁决
- F05: 测试覆盖增强，不阻塞 implementation
- F06: `REVOKE` 枚举值清理，不阻塞 implementation

### Key Strengths

1. 动机评估严格限定了 external lifecycle diagnostic 范围，未扩大为 Host cancel 状态机重写
2. Root cause 基于 5 处直接代码证据，形成完整证据链
3. 严格对齐 Host/Engine 边界，无一处违反
4. 有效避免了过度设计（无新 public API、Engine contract、durable table、capability registry、第二套 watchdog）
5. 2 Slice 结构合理，符合 control doc Slice 切分原则
6. Non-goals 清晰界定了不做的事项

---

##裁决建议

建议 controller 对以下 findings 做裁决：

| Finding | 建议裁决 | 理由 |
|---|---|---|
| F01 | **accepted** | Enum 新增是 root cause 修复的核心契约变更，不能留给 implementation agent 自行裁决 |
| F02 | **accepted** | Re-claim fencing 是正确性边界，需在 plan 中明确 |
| F03 | **accepted** | state.py 变更点应与 F01/F02 一并收敛 |
| F04 | **accepted** | 一句话裁决即可消除歧义 |
| F05 | **deferred-with-owner** | 可推迟到 Slice implementation 阶段由 test 补充，不影响 plan 整体结构 |
| F06 | **accepted** 或 **rejected-with-reason** | 若认为 REVOKE 有未来场景则拒绝并说明；否则接受并删除 |
