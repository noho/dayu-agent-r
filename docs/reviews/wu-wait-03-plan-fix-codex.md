# WU-WAIT-03 Plan Fix - Codex

## Work Unit / Gate / Scope

- Work unit: WU-WAIT-03 / GitHub issue-92
- Gate: plan-fix
- Scope: 根据 controller adjudication 修复 plan artifact，使其达到 code-generation-ready。
- Boundary: 本 gate 只修复 plan 文档，不进入 implementation，不修改生产代码、测试、control doc、review artifacts，不执行 commit / push / PR / merge。

## Input Artifacts

- Plan artifact: `docs/host/wu-wait-03-external-job-lifecycle-plan.md`
- Plan review artifact: `docs/reviews/wu-wait-03-plan-review-mimo.md`
- Plan review artifact: `docs/reviews/wu-wait-03-plan-review-ds.md`
- Controller adjudication: `docs/reviews/wu-wait-03-plan-review-controller-adjudication.md`

## Fix Summary

- Accepted finding: `WaitPollLastOutcome` enum conditional language.
  - Plan fix: 明确要求新增 `WaitPollLastOutcome.ABANDON_UNSUPPORTED` 与 `WaitPollLastOutcome.ABANDON_NOOP`，删除条件性表述；补充 `StrEnum` value-based serialization、enum-set deserialization、row validation 和 roundtrip/validation tests 的处理要求。

- Accepted finding: unsupported/noop durable terminal marker.
  - Plan fix: 明确采用 controller 优先方案，参数化 existing `mark_wait_record_poll_abandoned(...)`，新增 keyword-only `last_outcome: WaitPollLastOutcome = WaitPollLastOutcome.ABANDONED`；applied / unsupported / noop 都通过该 mutation 写入 terminal marker，unsupported/noop 也设置 `poll_abandoned_at` 以阻止 re-claim。

- Accepted finding: Fins non-transient error / corrupt / missing handle mapping.
  - Plan fix: 明确 corrupt / unparsable token 返回 `WaitExternalJobLifecycleNoop(reason="invalid_observation_handle")`；missing observation / LOST 返回 `WaitExternalJobLifecycleNoop(reason="observation_missing")`；非 transient observation error 返回 `WaitExternalJobLifecycleNoop(reason="observation_error:<error_kind>")`；`TRANSIENT_UNAVAILABLE` 继续 re-raise，让 Host poller 进入 `ABANDON_ERROR` retry/backoff。

- Accepted finding: `WaitPollOnceResult.abandoned` counter semantics.
  - Plan fix: 明确 `abandoned` 计数语义为 cancelled wait terminal lifecycle marker 已成功 durable write；applied / unsupported / noop 三类 terminal lifecycle result 均在 CAS 成功后计入 `abandoned`，当前 WU 不新增 counter。

- Accepted finding: unsupported/noop CAS conflict and prepared cancel tests.
  - Plan fix: Slice 1 测试矩阵新增 unsupported/noop terminal marker CAS conflict，要求 lost CAS 计为 claim conflict、不计入 `abandoned`、wait 保持可后续 retry；Slice 2 测试矩阵新增 prepared observation cancel + abandon before activation，要求阻止 submit 并释放 local observation handle。

- Accepted-for-clarification finding: `WaitExternalJobLifecycleAction.REVOKE`.
  - Plan fix: 保留 `REVOKE`，并补充 action selection rule：adapter 返回实际采取的最强 provider-supported lifecycle action；`REVOKE` 只用于 provider 能 invalidate future delivery/result 但不 necessarily physical stop 的场景；当前 Fins adapter 明确返回 `ABANDON`。

## Modified Files

- `docs/host/wu-wait-03-external-job-lifecycle-plan.md`

## Validation

- Tests: not run.
- Pyright: not run.
- Reason: 本 gate 是 documentation-only plan-fix，禁止进入 implementation；未修改生产代码或测试。
- Text validation performed:
  - 核对 plan 中已移除 `if needed` / `only if needed` / `If adding` / `no-op or applied` / `Pick one` 等会把设计决策推给 implementation 的表述。
  - 核对 plan 明确包含新增 enum、durable mutation 参数化、unsupported/noop `poll_abandoned_at` terminal marker、Fins noop reason mapping、`TRANSIENT_UNAVAILABLE` re-raise、`abandoned` counter 语义、CAS conflict tests、prepared cancel + abandon tests、`REVOKE` action selection rule。
  - 核对本次 follow-up 只新增本 fix artifact，不再修改 plan、代码、测试、control doc 或既有 review artifacts。

## Residual Risks / Owners

- Provider 不支持 physical cancel。
  - Owner / destination: provider-specific Fins/source adapter owners under GitHub issue #92 / #87。

- Poller disabled deployment 不执行 external lifecycle。
  - Owner / destination: Service composition / WU-WAIT-04 production-grade E2E smoke。

- Fins running operation 只做 cooperative checkpoint。
  - Owner / destination: Fins provider/runtime owners。

- 更丰富 tool trace lifecycle diagnostic。
  - Owner / destination: future tool trace / diagnostic projection work。

Blocking open questions: none.

## Completion Status

plan-fix completed; ready for re-review.
