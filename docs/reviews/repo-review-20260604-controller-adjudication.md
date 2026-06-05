# Full Repository Review Controller Adjudication

## Gate

- Review mode: full repository code review after WU-CM-01 final closeout.
- Design source of truth:
  - `docs/engine/design.md`
  - `docs/host/design.md`
- Review artifacts:
  - `docs/reviews/repo-review-20260604-220925.md` (AgentMiMo)
  - `docs/reviews/repo-review-20260604-220415.md` (AgentDS)
- Controller objective: adjudicate findings against design source of truth, route accepted non-God fixes to AgentCodex, and keep God-module remediation in the maintainability control document.

## Design-Source Decisions

### Engine package-root exports are not expanded

`docs/engine/design.md` defines package-root function entries as `run_agent_messages` and `run_agent_and_wait`, and says package root also exports Engine contracts required by callers. It does not name `RunnerRequestIdentity`, `build_runner_request_identity`, or `ClientCorrelationPolicy` as `dayu.engine` root API. These symbols are already available from `dayu.engine.contracts`, which is the narrower contract namespace.

Decision: do not add `dayu.engine` root exports for these symbols in this fix batch. Adding them would expand public surface without design authorization.

### Runner request identity is a real Runner protocol input

The current code and Engine README contain `request_identity`, while `docs/engine/design.md` section 7 still shows the older `AsyncRunner.call(messages, options, tools)` signature. Because request identity is an Engine/Runner protocol input and is already used by implementation, the fix must synchronize the design text and protocol-surface tests together. The test must not be changed in isolation.

Decision: current fix required.

### Host durable schema stays fresh-schema only

`docs/host/design.md` section "SQLite schema convention" explicitly says the first version uses fresh schema creation only, has `PRAGMA user_version` validation, and does not provide old-schema compatibility or migration fallback in normal open path.

Decision: no migration framework fix in this batch.

## Accepted For Current Fix

### A1 Sync `AsyncRunner.call()` design and protocol-surface test

- Source: AgentDS finding 4.
- Decision: accepted.
- Required fix:
  - Update `docs/engine/design.md` section 7 so `AsyncRunner.call()` includes keyword-only `request_identity`.
  - Update `tests/engine/runners/openai/test_protocol_surface.py` so the signature assertion covers `request_identity` and its keyword-only boundary.

### A2 Support HTTP-date `Retry-After`

- Source: AgentDS finding 5.
- Decision: accepted.
- Design basis: `docs/host/design.md` assigns low-level provider transport retry to Engine Runner and explicitly includes `Retry-After`.
- Required fix: parse both delay-seconds and HTTP-date forms with standard-library parsing, preserve positive-only wait semantics, and add focused tests.

### A3 Remove unreachable `ServerTimeoutError` branch

- Source: AgentDS finding 6.
- Decision: accepted.
- Required fix: remove the dead branch or refactor timeout classification so each branch is reachable, preserving existing timeout classification behavior.

### A4 Add missing durable query indexes

- Source: AgentDS finding 7.
- Decision: accepted.
- Design basis: `docs/host/design.md` requires current-version schema validation to include required indexes and names session-scoped EventLog projection and host-instance recovery as durable responsibilities.
- Required fix: add focused indexes for stale host-instance scanning and session-scoped EventLog reads, update schema validation/tests, and increment fresh schema version if current project convention requires it.

### A5 Runtime package docstring includes `diagnostic_text`

- Source: AgentDS finding 10.
- Decision: accepted.
- Required fix: update `dayu/runtime/__init__.py` documentation so the layer-neutral `diagnostic_text` helper is explicitly part of the allowed runtime surface.

### A6 Fix `cancel_session_runs()` handling for `WAITING` / `RECOVERING`

- Source: AgentMiMo finding 8.
- Decision: accepted.
- Design basis: Host owns lifecycle, cancellation, and governance for Session/Run states. A session-level cancel operation must not silently leave active lifecycle states untreated or unexplained.
- Required fix: either cancel supported `WAITING` / `RECOVERING` states, or return a typed explicit unsupported/blocked result that callers cannot mistake for full session cancellation. Add focused tests for both states.

### A7 Ensure scheduler close cleanup is marked after failed cleanup

- Source: AgentMiMo finding 10.
- Decision: accepted.
- Required fix: make `HostDispatchScheduler.close()` set its cleanup completion marker on exception paths without hiding the original exception. Add a focused test if existing scheduler tests can cover it locally.

### A8 Validate `ToolDisplayInfo.name`

- Source: AgentMiMo finding 13.
- Decision: accepted.
- Required fix: reject empty or whitespace-only display names with the same style of contract validation used by adjacent dataclasses. Add tests.

### A9 Stop exposing private `_ToolDecorator` as `tool()` return type

- Source: AgentMiMo finding 14.
- Decision: accepted.
- Required fix: express the public return type through a public callable/protocol shape instead of the private implementation class, while preserving decorator behavior and pyright compatibility.

### A10 Reuse runtime text digest helper in ScenePrepare

- Source: AgentMiMo finding 15.
- Decision: accepted.
- Required fix: add a layer-neutral text digest helper under `dayu.runtime`, reuse it from `scene_prepare.py`, preserve exact digest output, and add focused tests.

### A11 Consolidate repeated non-empty text validation where safe

- Source: AgentMiMo finding 5.
- Decision: accepted, scoped.
- Required fix: introduce a typed layer-neutral helper for modules that can safely share identical "non-empty text" semantics. Do not force modules with intentionally different error wording, return type, or domain-specific validation into the helper. Report any intentionally retained local validator with reason.

### A12 Remove or justify unprotected dispatch `sleep(0)`

- Source: AgentDS finding 9.
- Decision: accepted.
- Design basis: `docs/host/design.md` says dispatch must recheck durable state and then dispatch; it does not require an unconditional scheduler yield between successful CAS and worker start.
- Required fix: remove the yield if tests confirm no behavior dependency, or add a precise comment plus focused test evidence if the yield is required.

## Maintainability Control Only

### M1 God module / God object remediation

- Sources:
  - AgentMiMo findings 1, 2, 3, 4, 6
  - AgentDS finding 1
- Decision: tracked in `docs/host/maintainability-implementation-control.md`, not fixed in this review-fix batch.
- Reason: these require architecture slices, module-boundary design, and broad test migration.

## Rejected With Reason

### R1 Schema migration framework

- Source: AgentDS finding 2.
- Decision: rejected for current design.
- Reason: `docs/host/design.md` requires fresh schema creation and structured schema mismatch failure, not online migration or compatibility fallback. A migration framework would need a new design gate.

### R2 Engine package-root exports for request identity and correlation policy

- Sources: AgentDS findings 3 and 12.
- Decision: rejected.
- Reason: `docs/engine/design.md` does not authorize these symbols as `dayu.engine` root API. They are already exported from `dayu.engine.contracts`.

### R3 Engine package-root `__all__` ordering style

- Source: AgentDS finding 11.
- Decision: rejected.
- Reason: no design or behavioral issue. Do not churn package-root exports for style in this fix batch.

### R4 Host importing Engine contracts

- Source: AgentMiMo finding 7.
- Decision: rejected.
- Reason: the current layer order is `UI -> Service -> Host -> Engine`; Host is an Engine caller and may depend on Engine contracts. Engine must not depend upward on Host.

### R5 `_PublicHostHandle.close()` lock

- Source: AgentMiMo finding 9.
- Decision: rejected.
- Reason: `_closed` is set before the first `await`, so concurrent async callers in the current model observe the closed state. No bug path was shown.

### R6 Durable cancellation token read caching

- Source: AgentMiMo finding 11.
- Decision: rejected.
- Reason: adding TTL caching changes cancellation freshness semantics and the review did not provide a correctness failure or a measured performance issue.

### R7 Watch-session poll interval configurability

- Source: AgentMiMo finding 12.
- Decision: rejected.
- Reason: no design source requires `watch_session_events` poll interval to be a public construction option, and adding one would expand Host public configuration surface.

### R8 Missing-owner orphan classification

- Source: AgentDS finding 8.
- Decision: rejected until direct invariant evidence exists.
- Reason: ownerless records can represent non-dispatched or not-yet-owned lifecycle points. Marking them lost without a design-backed stale threshold risks converting valid queued/pre-dispatch work into terminal failure.

### R9 Lane cancellation helper extraction

- Source: AgentMiMo finding 16.
- Decision: rejected for current batch.
- Reason: this is a broad internal refactor of cancellation cleanup machinery, not a proven correctness bug. It can be considered later as part of runtime maintainability work if supported by a dedicated design slice.

## Required Fix Validation

AgentCodex must run focused tests for every touched area, plus:

```bash
source .venv/bin/activate
python -m pyright dayu/ tests/ utils/
git diff --check
```

If a listed review fix cannot be safely implemented without expanding a public contract beyond `docs/engine/design.md` or `docs/host/design.md`, AgentCodex must stop and report the blocker instead of inventing compatibility behavior.
