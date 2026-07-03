# WU-WAIT-03 Plan Re-Review — AgentDS

- **Review agent**: AgentDS
- **Reviewed artifacts**:
  - Plan: `docs/host/wu-wait-03-external-job-lifecycle-plan.md`
  - Plan-fix: `docs/reviews/wu-wait-03-plan-fix-codex.md`
  - Controller adjudication: `docs/reviews/wu-wait-03-plan-review-controller-adjudication.md`
- **Re-review date**: 2026-07-03 11:10 UTC+8
- **Gate**: plan re-review
- **Scope**: 仅审查 plan-fix 是否关闭 controller accepted findings，不扩大 scope

---

## Re-Review Method

逐项对照 controller adjudication 的 6 个 accepted findings，验证 plan 修改后的文本是否消除了原歧义、给出了具体可执行方案。不重新 review plan 的整体结构、architecture boundary、slice 切分——这些已在原始 review 中确认成立。

---

## Accepted Finding 逐项验证

### Finding 1: WaitPollLastOutcome enum conditional language

- **Controller 要求**: 明确添加 `ABANDON_UNSUPPORTED` 与 `ABANDON_NOOP`，移除 "if needed / only if needed" 表述，说明 StrEnum serialize/deserialize、row validation 与 tests。
- **Plan 当前写法** (line 99-103):
  - "Add these `WaitPollLastOutcome` values for durable diagnostic precision: `ABANDON_UNSUPPORTED`, `ABANDON_NOOP`" — 明确要求添加，无条件性语言。
  - "`WaitPollLastOutcome` remains a `StrEnum`; serialization continues to store `enum.value`, deserialization continues to validate through the enum member set, and row validation must accept rows decoded with the new enum members. Tests must cover serialize/deserialize roundtrip and wait row validation for `ABANDON_UNSUPPORTED` and `ABANDON_NOOP`." — 覆盖了 serialize/deserialize/row validation/tests 全部四个维度。
- **验证**: plan 全文搜索无 `if needed`、`only if needed`、`If adding`、`no-op or applied`、`Pick one` 等条件性表述残留。
- **状态**: ✅ 已修复

### Finding 2: unsupported/noop durable write path (含 DS F02 / DS F03)

- **Controller 要求**: 参数化 `mark_wait_record_poll_abandoned(...)`，新增 `last_outcome: WaitPollLastOutcome = WaitPollLastOutcome.ABANDONED`，unsupported/noop 同样设置 `poll_abandoned_at` 以阻止 re-claim。
- **Plan 当前写法** (line 113):
  - "Parameterize existing durable mutation `mark_wait_record_poll_abandoned(...)` instead of adding a second terminal marker mutation. New signature must add keyword-only `last_outcome: WaitPollLastOutcome = WaitPollLastOutcome.ABANDONED` and keep the current CAS predicate and return semantics."
  - "Unsupported and noop terminal results call the same mutation with `ABANDON_UNSUPPORTED` or `ABANDON_NOOP`; setting `poll_abandoned_at` is required to prevent re-claim."
- **验证**:
  - 参数化方案与 controller 优先方案一致：keyword-only `last_outcome`，默认值 `ABANDONED` 保持现有调用者兼容。
  - unsupported/noop 明确设置 `poll_abandoned_at` → 与 `claim_wait_record_for_poll` 的 `poll_abandoned_at IS NULL` WHERE 条件形成 re-claim fencing。
  - Slice 1 Exact changes (line 156-162) 进一步细化了 `_abandon_cancelled_wait` 中对三种 `WaitExternalJobLifecycleResult` 的处理，各自调用参数化的 `mark_wait_record_poll_abandoned` 并传入对应的 `last_outcome`。
- **状态**: ✅ 已修复

### Finding 3: Fins corrupt/missing/non-transient error mapping

- **Controller 要求**: corrupt token、missing observation、非 transient observation error → `WaitExternalJobLifecycleNoop`；`TRANSIENT_UNAVAILABLE` → re-raise。
- **Plan 当前写法** (line 222-226):
  - "Corrupt / unparsable token: return `WaitExternalJobLifecycleNoop(reason="invalid_observation_handle")`; do not call runtime."
  - "Observation missing / runtime returns LOST: return `WaitExternalJobLifecycleNoop(reason="observation_missing")`, because there is no live local observation handle left to cancel or abandon."
  - "Non-transient observation error during cancel or abandon: return `WaitExternalJobLifecycleNoop(reason="observation_error:<error_kind>")`, where `<error_kind>` is the stable enum value."
  - "`TRANSIENT_UNAVAILABLE`: re-raise so Host poller writes `ABANDON_ERROR` and retries."
- **验证**: 四种场景均有一对一显式映射，无 "no-op or applied abandon" 等二选一歧义，reason 语义自解释。
- **状态**: ✅ 已修复

### Finding 4: WaitPollOnceResult.abandoned 计数语义

- **Controller 要求**: applied / unsupported / noop 三类 terminal lifecycle result 均计入 `abandoned`，不新增 counter。
- **Plan 当前写法** (line 114):
  - "`WaitPollOnceResult.abandoned` counts cancelled wait records whose terminal lifecycle marker was durably written. Applied, unsupported, and noop results all increment `abandoned` after the CAS write succeeds. Do not add a new counter in this work unit."
- **验证**: 语义明确：三类结果均计入 `abandoned`，前提是 CAS write 成功。明确禁止新增 counter。
- **状态**: ✅ 已修复

### Finding 5: unsupported/noop CAS conflict 与 prepared cancel 测试

- **Controller 要求**: unsupported/noop terminal marker CAS conflict 和 prepared observation cancel + abandon 明确列入 Slice 1 / Slice 2 测试矩阵。
- **Plan 当前写法**:
  - Slice 1 (line 192): "Add CAS conflict tests for unsupported and noop terminal marker writes: after adapter returns, a lost CAS reports claim conflict, does not count as `abandoned`, and leaves the wait retryable for a later poll."
  - Slice 2 (line 254-255): "Add or update runtime test proving prepared observation cancel + abandon before activation still prevents submit and releases the local observation handle."
- **验证**: 两项测试均已显式列入对应 slice 的 Tests/validation 节，包含预期断言。
- **状态**: ✅ 已修复

### Finding 6: REVOKE action selection rule

- **Controller 要求**: 保留 `REVOKE`，补充 action selection rule；当前 Fins adapter 返回 `ABANDON`。
- **Plan 当前写法** (line 98):
  - "Method semantics: adapter receives the Host wait record snapshot, chooses the strongest provider-supported best-effort action it actually took, and returns a typed diagnostic result."
  - "`CANCEL` means the provider requested physical or cooperative stop."
  - "`REVOKE` means the provider can invalidate future delivery/result without necessarily stopping already-running physical work."
  - "`ABANDON` means the provider/adapter released local or remote lifecycle tracking and will not deliver the job through this wait path."
  - "Current Fins adapter returns `ABANDON` because it requests cooperative cancel and then releases the local observation handle."
- **验证**: 三个 action 值各有清晰语义定义，adapter 选择规则明确（返回实际采取的最强 action），Fins adapter 当前行为明确指定为 `ABANDON`。未引入新 public API 或 provider registry，不属于过度设计。
- **状态**: ✅ 已修复

---

## Architecture Boundary 再验证

逐项确认 plan-fix 未引入结构性越界：

| 边界规则 | 状态 | Plan 证据 |
|---|---|---|
| 无新 public Host API | ✅ | line 85-86 |
| 无新 Engine contract | ✅ | line 83 |
| 无 durable table/columns | ✅ | line 87 |
| 无第二套 watchdog | ✅ | line 23 |
| Host command cancel path 不做 provider I/O | ✅ | line 25, line 122 |
| resolve_wait 仍是 late result 唯一路径 | ✅ | line 115 |
| Fins adapter 不写 Host EventLog | ✅ | line 244-245 |
| 2-slice 结构不变 | ✅ | Slice 1/2 边界、allowed files、stop conditions 均保持 |

---

## Verdict

**`pass`**

- **Blocking findings**: 0
- **Controller accepted findings 状态**: 6/6 已修复
- **是否可进入 accepted plan commit gate**: 是

所有 controller accepted findings 均已在 plan artifact 中完整关闭。Plan 当前文本无遗留的条件性语言、无歧义映射、无推给 implementation agent 的设计决策。Plan 仍严格保持 Host/Engine 边界，无新 public API、无 Engine contract、无 durable table/columns、无第二套 watchdog、无 implementation 越界。

---

## Residual Risks（不变）

以下风险在原始 review 中已识别并归属，plan-fix 未引入新风险：

| Risk | Owner/Destination |
|---|---|
| Provider 不支持 physical cancel | Provider-specific adapter owners under #92/#87 |
| Poller disabled 部署不执行 external lifecycle | Service composition / WU-WAIT-04 |
| Fins running operation 只做 cooperative checkpoint | Fins provider/runtime owners |
| 更丰富 tool trace lifecycle diagnostic | 后续 tool trace / diagnostic projection work |

---

## 未修复 Findings

无。

---

## 修改文件

仅写入本 re-review artifact: `docs/reviews/wu-wait-03-plan-rereview-ds.md`。未修改 plan、代码、测试、control doc 或其它 review artifact。
