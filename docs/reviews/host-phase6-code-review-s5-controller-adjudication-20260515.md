# Host Phase 6 P6-S5 Controller Adjudication

## Scope

- Work unit: P6-S5 `Duplicate Governance And Diagnostic Emitter`
- Design source: `docs/host/design.md` §18.2 / §18.3
- Plan source: `docs/host/phase6-toolruntime-truncation-fetch-more-plan.md` P6-S5
- Implementation artifact: `docs/reviews/host-phase6-implementation-s5-duplicate-governance-20260515.md`
- Fix artifact: `docs/reviews/host-phase6-fix-s5-duplicate-governance-20260515.md`
- Reviews:
  - `docs/reviews/host-phase6-code-review-s5-mimo-20260515.md`
  - `docs/reviews/host-phase6-code-review-s5-ds-20260515.md`
  - `docs/reviews/host-phase6-code-re-review-s5-ds-20260515.md`

## Verdict

**Accepted.** P6-S5 is complete after accepted finding fixes. The implementation satisfies the Phase 6 design boundary: duplicate governance is Host / ToolRuntime-owned, run-local, ToolRuntime instance-local, and does not introduce Engine semantics, durable duplicate ledger, Memory retrieval, audit / trace projection, Remote transport, wait record, or scheduler composition wiring.

## Review Findings Adjudication

### MiMo-F1 — REUSE rejection lacks reject-specific diagnostic ref

- Decision: accepted as low-risk deferred observation.
- Reason: REUSE rejection still carries duplicate diagnostic refs and `ToolFactRejectedAck.reason_code`; no raw business result leaks and no canonical EventLog pollution occurs.
- Owner: P13 durable tool trace / diagnostic enrichment, or later ToolRuntime diagnostics hardening.

### MiMo-F2 / MiMo-F3

- Decision: accepted as non-issues.
- Reason: `_event_payload.py` / `event_log.py` did not need changes because existing accept barrier payload shape already supports governed / reuse refs. `_tool_fact_kind` broadening to `policy_decision.kind is not ALLOW` is required for `hint` / `require_justification` / `hard_stop`.

### DS-F1 — `require_justification` valid / downgrade branches untested

- Decision: accepted and fixed.
- Fix: added tests for valid justification allowing execution and missing justification argument binding downgrading to `HINT`.
- Re-review: AgentDS confirmed fixed.

### DS-F2 — duplicate index could record governed-error accepted entry

- Decision: accepted and fixed.
- Fix: `_record_duplicate_accepted` now writes the duplicate index only when `policy_decision.kind is ALLOW` and `duplicate_decision.kind is ALLOW`.
- Evidence: added test proving governed duplicate accepted does not overwrite prior successful reuse source.
- Re-review: AgentDS confirmed fixed.

### DS-F3 — deterministic diagnostic emitter validation inconsistency

- Decision: accepted and fixed.
- Fix: `DeterministicToolTraceDiagnosticEmitter.emit` now validates `reason_code` and `message` consistently with no-op and in-memory emitters.
- Re-review: AgentDS confirmed fixed.

### DS-F4 — ordinary policy rejection carried unrelated prior refs

- Decision: accepted and fixed.
- Fix: `_tool_fact_accept_candidate` now receives `duplicate_governed`; prior refs are carried on governed errors only when duplicate governance actually triggered the governed outcome.
- Re-review: AgentDS confirmed fixed.

### DS-F5 — semantic duplicate key lacks dedicated test

- Decision: deferred low-risk tracking.
- Reason: `semantic_duplicate_key_argument_name` is Host-internal, default disabled, and not required by the P6-S5 completion signal. If a later policy provider enables it, that owner must add dedicated tests and clarify its relation to normalized arguments digest.
- Owner: later policy provider / ToolRuntime hardening.

### DS-F6 — `GOVERNED_ERROR` defensive validation can be stricter

- Decision: deferred low-risk tracking.
- Reason: current production paths always set `duplicate_decision`; stricter public dataclass validation is defensive hardening, not a correctness blocker.
- Owner: later ToolRuntime hardening.

## Validation

- `source .venv/bin/activate && pytest tests/host/test_toolruntime_duplicate_governance.py tests/host/test_toolruntime_diagnostics.py tests/host/test_toolruntime_accept_barrier.py -q`
  - 24 passed
- `source .venv/bin/activate && pytest tests/host/test_toolruntime_executor.py tests/host/test_toolruntime_truncation_fetch_more.py tests/host/test_toolruntime_effective_bundle.py tests/host/test_phase6_toolruntime_integration.py tests/host/test_toolruntime_accept_barrier.py tests/host/test_toolruntime_duplicate_governance.py tests/host/test_toolruntime_diagnostics.py -q`
  - 46 passed
- `source .venv/bin/activate && python -m pyright dayu/host tests/host`
  - 0 errors, 0 warnings, 0 informations
- `git diff --check`
  - clean

## Residual Risks

- Default duplicate policy remains `allow`; production policy provider resolution is not part of P6-S5.
- `ToolTraceDiagnosticEmitter` emits typed refs only; durable trace projection remains Phase 13.
- `semantic_duplicate_key_argument_name` remains default-disabled and untested until a later policy provider enables it.
- Real `HostDispatchScheduler` tool-enabled composition wiring remains a Phase 6 exit blocker owned by P6-S6 integration.
