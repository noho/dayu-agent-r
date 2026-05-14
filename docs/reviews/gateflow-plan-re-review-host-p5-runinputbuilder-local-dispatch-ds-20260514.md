# Phase 5 Plan Fix Re-Review

## Scope

Gate: Phase 5 plan fix re-review.

Reviewed artifacts:
- `docs/host/phase5-runinputbuilder-local-dispatch-plan.md` (fixed)
- `docs/reviews/gateflow-plan-review-host-p5-runinputbuilder-local-dispatch-controller-adjudication-20260514.md`
- `docs/reviews/gateflow-plan-fix-host-p5-runinputbuilder-local-dispatch-codex-20260514.md`
- `docs/reviews/gateflow-plan-review-host-p5-runinputbuilder-local-dispatch-ds-20260514.md`
- `docs/reviews/gateflow-plan-review-host-p5-runinputbuilder-local-dispatch-mimo-20260514.md`

## Verdict

All 8 accepted findings are fixed. No new blockers introduced. Plan is accepted for implementation gate.

## Per-finding verification

### MiMo F001: `observed_at` timezone not explicit — FIXED

**Claim in fix:** Added UTC-aware `datetime` requirement and Phase 2 durable timestamp convention.

**Verified in plan:** §3.1 line 128: `observed_at` 必须是 `timezone.utc` aware `datetime`。写入 EventLog 时必须沿用 Phase 2 durable timestamp convention：UTC ISO-8601 TEXT、微秒精度、`Z` 后缀；naive `datetime` 属于构造错误。

**Verdict:** Fixed. Timezone contract is now unambiguous.

---

### MiMo F002: Canonical event id derivation formula absent — FIXED

**Claim in fix:** Added deterministic derivation formula.

**Verified in plan:** §3.1 lines 130-142 provide complete formula:

```text
event_id = "event-engine-" + sha256_digest_json({
  "execution_id": execution_id,
  "worker_event_index": worker_event_index,
  "event_class": event_class,
  "event_type": event_type,
  "sub_index": sub_index
}).removeprefix("sha256:")
```

`sub_index` semantics (starts from 0, handles multi-event mapping) are defined. Input determinism guarantee stated.

**Verdict:** Fixed. Derivation is deterministic and code-generation-ready.

---

### MiMo F003: `PROVIDER_PROTOCOL_ERROR` raw payload / partial call mapping unclear — FIXED

**Claim in fix:** Defined `partial_tool_call_count = len(engine_event.data.partial_tool_calls)` and payload descriptor mapping.

**Verified in plan:** §3.5 lines 386: `partial_tool_call_count` 必须由 `len(engine_event.data.partial_tool_calls)` 派生。`raw_payload_ref` / `raw_payload_digest` 通过 Phase 2 payload descriptor 机制保存 `engine_event.data.raw_payload`；当 `raw_payload is None` 时二者均为 `None`。

**Verdict:** Fixed. Mapping from Engine data to Host payload is explicit.

---

### MiMo F004: `EngineEvent` evidence omits `occurred_at` — FIXED

**Claim in fix:** Corrected evidence statement.

**Verified in plan:** §1.2 line 30: `EngineEvent` 包含 `occurred_at`、`session_id`、`run_id`、`type`、`data`、`metadata`。

**Verdict:** Fixed. Evidence now matches the actual Engine contract.

---

### MiMo F005: `AttemptDispatchSnapshot` vs provider field ownership unclear — FIXED

**Claim in fix:** Clarified snapshot carries identity/refs, providers inject Engine request fields.

**Verified in plan:** P5-S2 exact changes section adds: `AttemptDispatchSnapshot` 只携带 durable identity refs、dispatch refs、policy snapshot refs 和 cancellation token；`runner_spec`、`runner_options`、`agent_policy`、`tool_schemas`、`tool_executor` 由对应 providers 在 `build()` 时注入，不在 snapshot 中重复保存。

**Verdict:** Fixed. Ownership boundary between snapshot and providers is explicit.

---

### MiMo F006: `cancel_session_runs` replay best-effort test missing — FIXED

**Claim in fix:** Added replay re-propagation test expectation.

**Verified in plan:** P5-S5 tests now include: `cancel_session_runs` replay 不追加 facts；若仍存在同 execution_id 的 active `CANCELLING` worker，best-effort re-propagation 不影响返回值与幂等记录。

**Verdict:** Fixed. Test expectation covers the best-effort re-propagation path while confirming idempotency constraint.

---

### DS F-N1: `worker_accept_event_id` / `worker_accept_event_sequence` underspecified — FIXED

**Claim in fix:** Bound refs to `ATTEMPT_RUNNING` EventLog event id and global event_sequence.

**Verified in plan:** §3.2 lines 177: `worker_accept_event_id` 是 Host append 的 `ATTEMPT_RUNNING` EventLog `event_id`；`worker_accept_event_sequence` 是同一 `ATTEMPT_RUNNING` EventLog row 的全局 `event_sequence`。它们不是 worker-local sequence，也不是 Engine event id。

**Verdict:** Fixed. Semantics are unambiguous — both refs point to the Host-owned `ATTEMPT_RUNNING` EventLog row.

---

### DS F-N2: Engine contract type module binding unclear — FIXED

**Claim in fix:** Bound `AgentRunRequest`, `RunnerSpec`, `RunnerCallOptions`, `AgentPolicy` to existing `dayu.engine.contracts` modules.

**Verified in plan:** §3.4 lines 240-247 explicitly bind:
- `dayu.engine.contracts.agent_run.AgentRunRequest`
- `dayu.engine.contracts.runner_spec.RunnerSpec`
- `dayu.engine.contracts.runner_spec.RunnerCallOptions`
- `dayu.engine.contracts.agent_policy.AgentPolicy`

And adds: "Host RunInputBuilder 只构造这些既有 Engine request / policy objects，不在 Host 内重新定义同名 dataclass，不扩展 Engine contract，也不要求 Engine import Host 类型。"

**Verdict:** Fixed. Type provenance is explicit and Engine contract integrity is preserved.

---

## New blocker audit

Checked for regressions or new ambiguities introduced by the fix:

1. **Event id derivation uses `sha256_digest_json`**: This is a project-internal hash helper pattern. If not available, implementation agent can substitute with standard `hashlib` — the contract is stable input → stable output. Not a blocker.

2. **`.removeprefix("sha256:")`**: Implies the hash helper returns a prefixed string. This is an existing project convention — the implementation agent inherits it.

3. **Engine type existence**: The plan references `dayu.engine.contracts.agent_policy.AgentPolicy` etc. If these don't exist yet, the implementation agent hits P5-S2 stop condition (can't modify Engine contracts) and stops. This is correct behavior, not a plan defect.

4. **No changes to stop conditions, slice boundaries, module ownership, or import constraints.** The fix is a pure documentation/clarification pass.

**Conclusion: zero new blockers.**

---

## Final gate recommendation

| Category | Result |
| --- | --- |
| MiMo F001-F006 fix status | All 6 fixed |
| DS F-N1, F-N2 fix status | Both fixed |
| New blockers introduced | 0 |
| New implementation ambiguity | 0 |
| Plan acceptance for implementation | **Accepted** |
