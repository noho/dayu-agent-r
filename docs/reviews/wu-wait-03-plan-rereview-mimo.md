# WU-WAIT-03 Plan Re-review — AgentMiMo

**Reviewer**: AgentMiMo
**Timestamp**: 20260703-111044
**Plan artifact**: `docs/host/wu-wait-03-external-job-lifecycle-plan.md`
**Review gate**: plan re-review
**Design sources**: `docs/host/design.md`, `docs/engine/design.md`
**Control doc**: `docs/host/issues-implementation-control.md`

---

## 1. Reviewed Target and Scope

Plan artifact `docs/host/wu-wait-03-external-job-lifecycle-plan.md` 的 plan-fix 是否关闭了 controller accepted findings。本 re-review 只审查 plan-fix 是否已修复所有 accepted findings，不扩大 scope。

**输入 artifacts**：
- Original plan review: `docs/reviews/wu-wait-03-plan-review-mimo.md`
- Other review: `docs/reviews/wu-wait-03-plan-review-ds.md`
- Controller adjudication: `docs/reviews/wu-wait-03-plan-review-controller-adjudication.md`
- Plan-fix: `docs/reviews/wu-wait-03-plan-fix-codex.md`

---

## 2. Accepted Findings Verification

### Finding 01: `WaitPollLastOutcome` enum conditional language

**Controller adjudication**: accepted — Plan 必须明确添加 `ABANDON_UNSUPPORTED` 与 `ABANDON_NOOP`，并说明 StrEnum serialize/deserialize、row validation 与 tests 的处理。不得保留 "if needed / only if needed" 表述。

**Plan artifact 验证** (line 99-103):
```
- Add these `WaitPollLastOutcome` values for durable diagnostic precision:
  - `ABANDON_UNSUPPORTED`
  - `ABANDON_NOOP`
  Existing `ABANDONED` remains the success/applied terminal lifecycle marker.
- `WaitPollLastOutcome` remains a `StrEnum`; serialization continues to store `enum.value`, deserialization continues to validate through the enum member set, and row validation must accept rows decoded with the new enum members. Tests must cover serialize/deserialize roundtrip and wait row validation for `ABANDON_UNSUPPORTED` and `ABANDON_NOOP`.
```

**状态**: ✅ 已修复

- 条件性语言已移除（无 "if needed" / "only if needed" / "If adding"）
- 明确添加了 `ABANDON_UNSUPPORTED` 和 `ABANDON_NOOP`
- 明确了 StrEnum value-based serialization、enum-set deserialization、row validation
- 明确了 tests 必须覆盖 serialize/deserialize roundtrip 和 wait row validation

---

### Finding 02: unsupported/noop durable write path

**Controller adjudication**: accepted — Plan 必须明确参数化 `mark_wait_record_poll_abandoned(...)` 或新增等价 mutation。Controller 裁决优先方案：参数化 existing mutation，新增 `last_outcome: WaitPollLastOutcome = WaitPollLastOutcome.ABANDONED`，unsupported/noop 同样设置 `poll_abandoned_at` 以阻止 re-claim。

**Plan artifact 验证** (line 113):
```
- Parameterize existing durable mutation `mark_wait_record_poll_abandoned(...)` instead of adding a second terminal marker mutation. New signature must add keyword-only `last_outcome: WaitPollLastOutcome = WaitPollLastOutcome.ABANDONED` and keep the current CAS predicate and return semantics. Unsupported and noop terminal results call the same mutation with `ABANDON_UNSUPPORTED` or `ABANDON_NOOP`; setting `poll_abandoned_at` is required to prevent re-claim.
```

**状态**: ✅ 已修复

- 明确采用 controller 优先方案：参数化 existing mutation
- 明确了新签名：keyword-only `last_outcome: WaitPollLastOutcome = WaitPollLastOutcome.ABANDONED`
- 明确了 unsupported/noop 都通过该 mutation 写入 terminal marker
- 明确了 unsupported/noop 也设置 `poll_abandoned_at` 以阻止 re-claim
- 保持了 CAS predicate 和 return semantics

---

### Finding 03: Fins non-transient error / corrupt / missing handle mapping

**Controller adjudication**: accepted — Plan 必须明确：corrupt token、missing observation 或非 transient observation error 均映射为 `WaitExternalJobLifecycleNoop`，并写清 reason 语义；`TRANSIENT_UNAVAILABLE` 继续 re-raise 进入 retry/backoff。

**Plan artifact 验证** (line 223-226):
```
- Current Fins behavior should map as:
  - Valid observation handle: call `cancel_observation(handle)` then `abandon_observation(handle)`, return `WaitExternalJobLifecycleApplied(action=ABANDON, message=...)`. Do not return `CANCEL` for current Fins because the adapter also releases the local observation handle after requesting cooperative cancellation.
  - Corrupt / unparsable token: return `WaitExternalJobLifecycleNoop(reason="invalid_observation_handle")`; do not call runtime.
  - Observation missing / runtime returns LOST: return `WaitExternalJobLifecycleNoop(reason="observation_missing")`, because there is no live local observation handle left to cancel or abandon.
  - Non-transient observation error during cancel or abandon: return `WaitExternalJobLifecycleNoop(reason="observation_error:<error_kind>")`, where `<error_kind>` is the stable enum value. This records that Fins cleanup cannot do more for the current handle without making Host cancellation depend on provider cleanup.
  - `TRANSIENT_UNAVAILABLE`: re-raise so Host poller writes `ABANDON_ERROR` and retries.
```

**状态**: ✅ 已修复

- 明确了 corrupt / unparsable token → `WaitExternalJobLifecycleNoop(reason="invalid_observation_handle")`
- 明确了 missing observation / LOST → `WaitExternalJobLifecycleNoop(reason="observation_missing")`
- 明确了 non-transient observation error → `WaitExternalJobLifecycleNoop(reason="observation_error:<error_kind>")`
- 明确了 `TRANSIENT_UNAVAILABLE` → re-raise，Host poller 写 `ABANDON_ERROR` 并重试
- 所有 reason 语义清晰

---

### Finding 04: `WaitPollOnceResult.abandoned` counter semantics

**Controller adjudication**: accepted — Plan 必须明确 applied / unsupported / noop 这三类 terminal lifecycle result 均计入 `abandoned`，因为它们都会完成 cancelled wait 的 lifecycle terminal marker。不得新增当前 WU 不需要的新 counter。

**Plan artifact 验证** (line 114):
```
- `WaitPollOnceResult.abandoned` counts cancelled wait records whose terminal lifecycle marker was durably written. Applied, unsupported, and noop results all increment `abandoned` after the CAS write succeeds. Do not add a new counter in this work unit.
```

**状态**: ✅ 已修复

- 明确了 `abandoned` 计数语义：cancelled wait terminal lifecycle marker 已成功 durable write
- 明确了 applied / unsupported / noop 三类 terminal lifecycle result 均在 CAS 成功后计入 `abandoned`
- 明确了当前 WU 不新增 counter

---

### Finding 05: unsupported/noop CAS conflict and prepared cancel tests

**Controller adjudication**: accepted — Plan 必须把 unsupported/noop terminal marker CAS conflict 和 prepared observation cancel + abandon 明确列入 Slice 1 / Slice 2 测试矩阵。

**Plan artifact 验证**:

Slice 1 (line 192-193):
```
- Add CAS conflict tests for unsupported and noop terminal marker writes: after adapter returns, a lost CAS reports claim conflict, does not count as `abandoned`, and leaves the wait retryable for a later poll.
```

Slice 2 (line 254-255):
```
- Add or update runtime test proving prepared observation cancel + abandon before activation still prevents submit and releases the local observation handle.
```

**状态**: ✅ 已修复

- Slice 1 测试矩阵明确包含了 unsupported/noop terminal marker CAS conflict
- 明确了 lost CAS 计为 claim conflict、不计入 `abandoned`、wait 保持可后续 retry
- Slice 2 测试矩阵明确包含了 prepared observation cancel + abandon before activation
- 明确了阻止 submit 并释放 local observation handle

---

### Finding 06: `WaitExternalJobLifecycleAction.REVOKE` action selection rule

**Controller adjudication**: accepted-for-clarification — 不要求删除 `REVOKE`。Issue #92 明确包含 revoke / invalidate future delivery 语义，保留该 internal enum 可以接受；但 plan 必须说明 action selection rule：adapter 返回实际采取的最强 lifecycle action；`REVOKE` 只用于 provider 能 invalidate future delivery/result 但不 necessarily physical stop 的场景。当前 Fins adapter 返回 `ABANDON`。

**Plan artifact 验证** (line 98):
```
- Method semantics: adapter receives the Host wait record snapshot, chooses the strongest provider-supported best-effort action it actually took, and returns a typed diagnostic result. `CANCEL` means the provider requested physical or cooperative stop. `REVOKE` means the provider can invalidate future delivery/result without necessarily stopping already-running physical work. `ABANDON` means the provider/adapter released local or remote lifecycle tracking and will not deliver the job through this wait path. Current Fins adapter returns `ABANDON` because it requests cooperative cancel and then releases the local observation handle after requesting cooperative cancellation.
```

**状态**: ✅ 已修复

- 保留了 `REVOKE` enum 值
- 明确了 action selection rule：adapter 返回实际采取的最强 provider-supported lifecycle action
- 明确了 `REVOKE` 语义：provider 能 invalidate future delivery/result 但不 necessarily physical stop
- 明确了当前 Fins adapter 返回 `ABANDON`

---

## 3. Plan Boundary Compliance Verification

**Controller adjudication**: Plan 仍保持 Host/Engine 边界、无新 public API、无 Engine contract、无 durable table/columns、无第二套 watchdog、无 implementation 越界。

**Plan artifact 验证**:

| 边界规则 | Plan 是否遵守 | 证据 |
|---|---|---|
| Host public API: no change | ✅ | Line 85: "Host public API: no change to `cancel_run(...)`, `cancel_session_runs(...)`, `resolve_wait(...)`, `OpenHostOptions`, or `HostToolingOptions`" |
| Public Engine contract: no change | ✅ | Line 83: "Public Engine contract: no change" |
| Durable DB schema: no table or column change | ✅ | Line 87: "Durable DB schema: no table or column change" |
| 不创建第二套 watchdog | ✅ | Line 121: "Use existing `WaitPoller` / `WaitPollerSupervisor` as the lifecycle trigger" |
| Host command cancel path 不做 provider I/O | ✅ | Line 122: "Do not call provider adapter inside `cancel_run(...)` or `cancel_session_runs(...)`" |
| 不添加 provider capability registry | ✅ | Line 124: "Do not add provider capability registry" |
| 不把 `external_job_id` 变成 durable primary key | ✅ | Line 125: "Do not make `external_job_id` a lookup key" |
| `resolve_wait(...)` 仍是 late result 唯一路径 | ✅ | Line 115: "`resolve_wait(...)` late-result rejection remains unchanged and remains the only path" |

**状态**: ✅ Plan 保持了所有边界约束

---

## 4. Finding Status Summary

| # | Finding | Source | Status | Evidence |
|---|---|---|---|---|
| F01 | `WaitPollLastOutcome` enum conditional language | MiMo F01 / DS F01 | ✅ 已修复 | Plan line 99-103: 明确添加 enum，移除条件性语言，明确 serialization/deserialization/row validation/tests |
| F02 | unsupported/noop durable write path | MiMo F02 / DS F02 / DS F03 | ✅ 已修复 | Plan line 113: 参数化 `mark_wait_record_poll_abandoned(...)`，unsupported/noop 设置 `poll_abandoned_at` |
| F03 | Fins non-transient error / corrupt / missing handle mapping | MiMo F03 / DS F04 | ✅ 已修复 | Plan line 223-226: 明确所有错误情况映射为 Noop，TRANSIENT_UNAVAILABLE re-raise |
| F04 | `WaitPollOnceResult.abandoned` counter semantics | MiMo F04 | ✅ 已修复 | Plan line 114: 明确 applied/unsupported/noop 均计入 `abandoned` |
| F05 | unsupported/noop CAS conflict and prepared cancel tests | DS F05 | ✅ 已修复 | Plan line 192-193, 254-255: 明确列入测试矩阵 |
| F06 | `WaitExternalJobLifecycleAction.REVOKE` action selection rule | DS F06 | ✅ 已修复 | Plan line 98: 保留 REVOKE，明确 action selection rule |

---

## 5. Verdict

**Verdict: pass**

**Blocking findings**: 0

**Non-blocking findings**: 0

**Summary**: Plan-fix 已完全关闭所有 controller accepted findings。每个 accepted finding 都有明确的 plan 文本证据，条件性语言已移除，设计决策已明确，测试矩阵已补充，边界约束已保持。Plan 达到 code-generation-ready 状态，可以进入 accepted plan commit gate。

---

## 6. Artifact Output

- **Output file**: `docs/reviews/wu-wait-03-plan-rereview-mimo.md`
- **Files modified**: Only this re-review artifact. No changes to plan, production code, tests, control doc, or other review artifacts.
