# WU-CM-15 Public Smoke Reactive Compact And Fallback Plan

## Gate / Scope

- Gate: plan only.
- Work unit: WU-CM-15 Conversation memory public smoke reactive compact and fallback coverage.
- Allowed implementation scope after this plan is accepted: public smoke coverage hardening only.
- This plan does not authorize implementation, fix, review, commit, push, PR, merge, control-doc update, README edit, or any other gate.

## Goal / Motivation / Success Signal

Goal:

- Add explicit public Host conversation memory smoke coverage for the reactive compact path.
- Add explicit public Host conversation memory smoke coverage for deterministic compact-failure dispatch fallback.
- Preserve the existing `memory-compact` suite as the proactive compact accepted smoke: proactive request, accepted compact, compact artifacts, and zero compact failures remain required.

Motivation:

- The current public conversation memory smoke already validates the long-session memory and proactive compact accepted path, but it does not make reactive compact or deterministic dispatch fallback first-class smoke targets.
- Focused production-path tests already cover reactive compact and fallback semantics, so the risk is not a missing Host/Engine state machine. The gap is public smoke visibility and acceptance coverage.
- Fallback cannot be folded into existing `memory-compact` acceptance because that suite correctly treats every `CONTEXT_COMPACTION_FAILED` as a hard failure.

Success signal:

- Existing `memory-compact` still requires `requested_proactive >= 1`, `compacted_proactive >= 1`, compact artifact files, and `failed_total == 0`.
- A new reactive suite or equivalent public smoke entry asserts `requested_reactive >= 1`, `compacted_reactive >= 1`, `failed_reactive == 0`, recovery attempt creation, terminal success, one-system-message contract, current input anchor preservation, and protected recent floor behavior.
- A new fallback suite or equivalent public smoke entry asserts `CONTEXT_COMPACTION_FAILED`, `fallback_action=dispatch`, diagnostic fallback input window, no accepted `CONTEXT_COMPACTED` for that operation, fallback terminal success, fallback RunInput includes only the selected recent window plus current input, and no fake Session Semantic Memory is generated.
- Smoke stdout prints compact audit, operation, and fallback key signals without full pressure blob output or per-delta stream noise.

## Non-Goals / Scope Boundary

- Do not change Host or Engine compact contract.
- Do not change durable schema.
- Do not change EventLog canonical semantics.
- Do not change Context Governance state machine.
- Do not change provider contract.
- Do not rely on real provider random overflow.
- Do not merge the full GitHub Issue #80 Conversation Memory benchmark into this work unit.
- Do not add production-only hooks.
- Do not bypass the public Host path: smoke execution must still go through `open_host -> ensure_session -> submit_followup -> watch -> get_session`.
- Do not relax `memory-compact` proactive acceptance or reinterpret fallback success as proactive compact acceptance.
- Do not modify README or control doc unless a later accepted implementation changes documented user-facing behavior. This plan expects no README update.

Stop condition:

- If implementation requires a Host/Engine public API change, durable schema change, EventLog semantic change, provider contract change, production state-machine change, or non-smoke production hook, stop and report a blocker instead of implementing.

## Design Alignment

Host design alignment:

- `docs/host/design.md` makes Host the owner of Context Governance, compact orchestration, recovery, fallback, EventLog canonical facts, and RunInputBuilder assembly.
- The design states reactive compact is triggered by Engine overflow, closes the current Attempt by policy, moves the Run through recovery, performs bounded compaction, and creates a new recovery Attempt when accepted.
- The design states tier 4/5 dispatch fallback must not submit `CONTEXT_COMPACTED`, must not materialize Session Semantic Memory, and must leave `CONTEXT_COMPACTION_FAILED` or equivalent diagnostic evidence.
- The design states RunInputBuilder rebuilds complete messages from durable facts, memory snapshot, compact artifacts, and fallback input view; it must not reuse failed provider request payloads.
- This WU only adds public smoke observations for those already-designed behaviors.

Engine design alignment:

- `docs/engine/design.md` says Engine only reports provider context overflow as `context_compaction_requested` and then fails the run with recoverable `context_compaction_required`.
- Engine does not own Host context budget governance, compact, retry, recovery, fallback, Session lifecycle, or durable state.
- The deterministic reactive smoke should therefore use an ordinary worker that emits an Engine `context_compaction_requested` event, then let Host perform recovery and dispatch a new Attempt through the public Host flow.

Control-doc alignment:

- `docs/host/issues-implementation-control.md` records WU-CM-15 as `planning`, with no GitHub Issue, and states goal confirmation is complete.
- It explicitly requires adding public smoke coverage for reactive compact and deterministic fallback without weakening existing `memory-compact` proactive acceptance.

## First-Principles Judgment And Direct Evidence

Judgment:

- The problem is real but bounded. Production semantics already have focused coverage; the missing piece is public smoke coverage and stdout/audit acceptance for two important recovery paths.
- The severity should not be inflated into an architecture or contract task. The right fix is a narrow smoke/test hardening task.
- The user-provided path is mostly correct, but fallback must remain separate from `memory-compact`; otherwise the smoke would either fail by design or weaken a valid proactive acceptance invariant.

Direct evidence:

- `utils/smoke_host_public_conversation_memory_scenarios.py` already defines `SuiteMode.MEMORY_CORE` and `SuiteMode.MEMORY_COMPACT`, but no reactive or fallback suite.
- The same smoke script already counts `requested_reactive`, `compacted_reactive`, `failed_reactive`, rejected attempts, and fallback payload fields including `fallback_policy_decision`, `fallback_action`, and `fallback_tier`.
- `_assert_compact_acceptance(...)` currently only applies to `memory-compact`; it requires proactive request, proactive accepted compact, zero failed compact events, and compact artifact files.
- `tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py` already tests the current compact acceptance behavior and confirms `CONTEXT_COMPACTION_FAILED` remains a `memory-compact` hard failure.
- `tests/host/test_public_compact_smoke.py` already contains deterministic public Host tests for reactive compact recovery and compact-failure fallback dispatch.
- `tests/host/test_dispatch_scheduler.py` covers production reactive recovery, protected recent floor selection, reactive fallback dispatch, failed payload fallback fields, and no accepted compact on fallback.
- `tests/host/test_run_input_builder.py` covers fallback RunInput rendering: only selected recent window and current input are rendered, stale/damaged fallback payloads fail closed, and protected recent floor consistency is enforced.

## Affected Files / Modules

Planned implementation files:

- `utils/smoke_host_public_conversation_memory_scenarios.py`
- `tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py`

Referenced regression tests, not expected to need edits unless implementation reveals drift:

- `tests/host/test_public_compact_smoke.py`
- `tests/host/test_dispatch_scheduler.py`
- `tests/host/test_run_input_builder.py`
- `tests/host/fake_compaction.py`

No production `dayu/host`, `dayu/engine`, `dayu/runtime`, `dayu/service`, prompt, schema, or config file is planned for modification.

## Contract / Schema / State-Machine / Public Interface Changes

Expected changes: none.

- Host public API: no change.
- Engine public API: no change.
- Durable schema: no change.
- EventLog canonical semantics: no change.
- Context Governance state machine: no change.
- Provider contract: no change.
- Service assembly contract: no change.

Smoke CLI surface:

- Adding new smoke `--suite` enum values is a utility entrypoint extension, not a Host/Engine public contract change.
- Proposed suite names:
  - `memory-reactive-compact`
  - `memory-compact-fallback`

If deterministic smoke cannot be implemented using smoke-local helpers plus existing public Host opener fields and test-proven compactor runner stubbing, stop. Do not add Host production seams just for smoke.

## Implementation Decisions

1. Keep `memory-compact` unchanged.

   `_assert_compact_acceptance(...)` remains strict for `SuiteMode.MEMORY_COMPACT`: proactive request, proactive accepted compact, artifact files, and `failed_total == 0`.

2. Add suite-specific acceptance helpers instead of weakening the existing helper.

   Add helpers conceptually equivalent to:

   - `_assert_reactive_compact_acceptance(audit, report, observation)`
   - `_assert_fallback_dispatch_acceptance(audit, report, observation)`

   These helpers should be called only for their suite. They must use EventLog audit rows and captured public Host requests, not final-answer text alone.

3. Use deterministic smoke-local ordinary workers for the new suites.

   Deterministic worker injection must happen after normal Service assembly:

   - call `compose_open_host_options(...)` exactly as the current smoke script does;
   - use `dataclasses.replace(assembled_options, worker_factory=...)` to replace only the assembled `OpenHostOptions.worker_factory`;
   - the replacement factory must be a smoke-local `LocalEngineWorkerFactory`;
   - do not modify Host public API, Service assembly API, `compose_open_host_options(...)`, or production worker factory wiring.

   The deterministic worker must record every `AgentRunRequest` and `AttemptDispatchSnapshot` inside `LocalEngineWorker.accept(snapshot, request)` before returning a handle. These captured requests/snapshots are the assertion source for one-system-message checks, current input preservation, selected-window rendering, and recovery Attempt identity.

   Reactive suite:

   - Seed one or two successful public runs with stable markers.
   - On target run first Attempt, worker emits `EngineEventType.CONTEXT_COMPACTION_REQUESTED`.
   - Host performs reactive compact and starts a recovery Attempt.
   - Recovery Attempt worker emits final answer.

   Fallback suite:

   - Seed older and recent public runs with stable markers.
   - Target run crosses the proactive compact threshold using bounded deterministic pressure.
   - Pressure must use either existing smoke pressure helpers such as `_compact_pressure_padding(...)` / `_estimate_chars_as_tokens(...)`, or an explicit long `RoundSpec.prompt` pattern equivalent to the focused `_soft_threshold_prompt()` approach.
   - Before executing fallback assertions, compute or assert the effective prompt pressure lands between the active soft and hard context thresholds: high enough to require proactive compact and below the hard fail-closed threshold.
   - Fallback coverage requires `requested_proactive >= 1`; if no proactive compact was requested, the fallback suite must fail rather than report a pass.
   - Compactor proposal is deterministically rejected until bounded attempts are exhausted.
   - Host writes `CONTEXT_COMPACTION_FAILED` with `fallback_action=dispatch`.
   - Fallback dispatch worker emits final answer.

4. Stub only the external LLM compactor call in smoke/test code.

   Existing focused public tests already monkeypatch `dayu.host.llm_compaction._run_agent_request` to make compactor output deterministic while still exercising `open_host`, `submit_followup`, Host Context Governance, EventLog, RunInputBuilder, dispatch, and watcher terminal events.

   Implementation must keep the minimal deterministic compactor stubs smoke-local in `utils/smoke_host_public_conversation_memory_scenarios.py`, behind a small context manager used only inside deterministic suite execution. Runtime `utils/` code must not import test modules, including `tests/host/test_public_compact_smoke.py`, and this WU must not extract a production seam just to share compactor stubs.

   The smoke-local stubs may reuse the same semantic shape as `tests/host/fake_compaction.py`, but they should stay minimal: one accepted deterministic proposal path for reactive compact, and one rejecting deterministic proposal path for fallback. This is not a production hook and must not touch Host/Engine code.

   If review determines that runtime patching the compactor runner boundary is unacceptable for a standalone smoke script, the implementation must stop and report blocker, because adding a public compactor callable seam would violate this WU scope.

5. Keep stdout diagnostic bounded.

   Reuse the existing compact audit summary and operation printer. Extend operation output only with bounded fallback signals if needed:

   - `fallback_policy_decision`
   - `fallback_action`
   - `fallback_tier`
   - `attempt_count`
   - optional fallback input window status/count/digest fields, not full material text

   Do not print full pressure blob, full compactor prompt, full provider payload, or per-delta stream logs.

6. Make acceptance assertions inspect the actual public dispatch request shape.

   Reactive suite must assert:

   - both ordinary dispatch attempts have at most one system message;
   - recovery attempt has a different `attempt_id` and `execution_id`;
   - recovery request uses the same `run_id`;
   - current input marker is present as current input;
   - protected recent seed marker is preserved in the recovery input;
   - old seed marker is dropped or excluded when fallback/compact policy caps require it.

   Fallback suite must assert:

   - exactly one failed compact operation for the target run;
   - `fallback_action == "dispatch"`;
   - `fallback_input_window` exists and has selected/dropped/current refs;
   - no `CONTEXT_COMPACTED` belongs to that operation;
   - final worker request contains selected recent marker and current input marker;
   - final worker request does not contain dropped old marker;
   - final worker request does not contain accepted compact semantic sections such as `Conversation Summary`, `Verified Evidence and Facts`, `Prior Answer Anchors`, `Open Follow-up Context`, or `Reference Continuity`.

   To support the fallback assertions, implementation is pre-authorized to extend `CompactFailedOperationAudit` or an equivalent smoke-local audit object with bounded fields extracted from `fallback_input_window`:

   - `selected_block_ids`: non-empty list of selected recent material refs or ids;
   - `dropped_block_ids`: list of dropped material refs or ids, possibly empty only when the scenario genuinely has nothing old enough to drop;
   - `current_input_ref`: non-empty current input ref.

   The smoke audit must keep these as diagnostic refs/countable bounded fields only. It must not print full fallback material, compactor input, provider payload, or hidden Host internals.

## Small Slices

### Slice S1 - Suite Routing And Acceptance Helpers

Objective:

- Add new suite enum values, parser support, suite-specific round specs, and acceptance helpers.

Allowed files:

- `utils/smoke_host_public_conversation_memory_scenarios.py`
- `tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py`

Exact changes:

- Extend `SuiteMode` with `MEMORY_REACTIVE_COMPACT` and `MEMORY_COMPACT_FALLBACK`.
- Keep existing `memory-compact` pressure requirement unchanged.
- Require or auto-use deterministic bounded pressure only for `memory-compact-fallback` if needed to cross proactive threshold.
- Add small deterministic `RoundSpec` sets for reactive and fallback suites.
- Add pure tests for parser choices, suite selection, and unchanged `memory-compact` acceptance failure on `CONTEXT_COMPACTION_FAILED`.
- Add pure tests for reactive and fallback acceptance helpers using explicit synthetic data:
  - reactive helper tests construct `CompactAuditSummary` with `requested_reactive >= 1`, `compacted_reactive >= 1`, and `failed_reactive == 0`;
  - fallback helper tests construct `CompactAuditReport` or an equivalent failed-operation audit with one `CompactFailedOperationAudit`, `fallback_action="dispatch"`, bounded `fallback_input_window` fields (`selected_block_ids`, `dropped_block_ids`, `current_input_ref`), and no accepted `CONTEXT_COMPACTED` for the same operation.
- Add a fallback helper failure case proving the suite does not pass unless `requested_proactive >= 1`.

Completion signal:

- Pure helper tests prove old compact acceptance remains strict and new suite acceptance has separate failure messages.

Stop condition:

- If helper assertions require reading Host internals beyond existing compact EventLog audit rows and captured public `AgentRunRequest`s, stop and rescope.

### Slice S2 - Deterministic Reactive Public Smoke Path

Objective:

- Add a deterministic public smoke path that exercises Engine-reported reactive overflow, Host reactive compact, recovery Attempt creation, and terminal success.

Allowed files:

- `utils/smoke_host_public_conversation_memory_scenarios.py`
- `tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py`

Exact changes:

- Add shared smoke-local deterministic worker infrastructure modeled on `tests/host/test_public_compact_smoke.py`.
- Build this shared infrastructure in S2 for reuse by S3: deterministic worker factory, deterministic worker handles, request/snapshot capture, and compactor stub context manager. S3 must extend or parameterize this infrastructure, not duplicate a second worker implementation.
- Add a fake compactor runner response using `tests/host/fake_compaction.py` semantics or equivalent minimal smoke-local JSON proposal generation.
- Keep compactor stubs in `utils/smoke_host_public_conversation_memory_scenarios.py`; do not import tests from runtime `utils/`.
- After `compose_open_host_options(...)`, inject the deterministic factory with `dataclasses.replace(assembled_options, worker_factory=smoke_factory)`. Do not add parameters to Host or Service assembly APIs.
- Capture ordinary `AgentRunRequest`s and dispatch snapshots in a smoke observation object by recording both arguments at the start of `LocalEngineWorker.accept(snapshot, request)` before returning the handle.
- Assert the reactive acceptance signals listed above after the smoke run.
- Add unit tests that exercise the reactive helper with synthetic audit/report data and verify stdout line prefixes remain `SMOKE ...`.

Completion signal:

- `python utils/smoke_host_public_conversation_memory_scenarios.py --suite memory-reactive-compact ...` can run without real provider overflow and reports reactive accepted compact.
- The deterministic worker factory, request/snapshot capture, and compactor stub context manager are reusable by S3 without introducing a second worker implementation.

Stop condition:

- If recovery Attempt cannot be produced without changing Host/Engine code, stop and report that the smoke uncovered a production regression rather than adding a smoke workaround.

### Slice S3 - Deterministic Fallback Public Smoke Path

Objective:

- Add a deterministic compact-failure fallback smoke path that proves fallback dispatch succeeds without accepted compact or fake semantic memory.

Allowed files:

- `utils/smoke_host_public_conversation_memory_scenarios.py`
- `tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py`

Exact changes:

- Add a rejecting compactor response that cites the current input anchor or otherwise deterministically fails the semantic barrier, matching existing focused tests.
- Implement the rejecting compactor response with the smoke-local compactor stub context manager created in S2; do not import test-only stubs and do not add production seams.
- Trigger proactive compact in the target run using bounded deterministic pressure, not real provider overflow.
- Use existing smoke pressure helpers (`_compact_pressure_padding(...)`, `_estimate_chars_as_tokens(...)`, and threshold helpers) or an explicit long prompt pattern equivalent to `_soft_threshold_prompt()`.
- Assert before or during fallback acceptance that the effective pressure is at or above the soft threshold and below the hard threshold for the active context policy. Failure should report the effective pressure and thresholds, not silently skip fallback coverage.
- Require `requested_proactive >= 1` in fallback acceptance so the suite proves compact was requested before fallback dispatch.
- Capture fallback final dispatch request through the shared S2 `LocalEngineWorker.accept(snapshot, request)` recorder.
- Assert `CONTEXT_COMPACTION_FAILED`, `fallback_action=dispatch`, `fallback_input_window`, no accepted compact for the same operation, terminal success, selected-window-only rendering, current input preservation, and no compact semantic memory sections.
- Extend `CompactFailedOperationAudit` or an equivalent smoke-local audit object to carry bounded `fallback_input_window.selected_block_ids`, `fallback_input_window.dropped_block_ids`, and `fallback_input_window.current_input_ref`.
- Extend compact operation stdout if needed to include bounded fallback tier/window signals.

Completion signal:

- `python utils/smoke_host_public_conversation_memory_scenarios.py --suite memory-compact-fallback --pressure-mode auto ...` reports fallback dispatch success while `memory-compact` still rejects any failed compact event.
- Fallback acceptance proves `requested_proactive >= 1`, the effective pressure sits between soft and hard thresholds, and dispatch fallback uses only the selected recent window plus current input.

Stop condition:

- If fallback success requires relaxing `memory-compact` or submitting `CONTEXT_COMPACTED`, stop.

### Slice S4 - Validation And Documentation Decision

Objective:

- Run focused tests, deterministic smoke commands, pyright, and whitespace checks. Confirm README decision.

Allowed files:

- No additional files.

Exact changes:

- No code changes expected in this slice unless validation exposes a mistake in S1-S3.

Completion signal:

- All required commands pass or failures are classified with direct evidence.

Stop condition:

- Any pyright error in touched files, smoke acceptance failure, or README trigger uncertainty blocks closeout.

## Tests And Validation Commands

Run all commands after `source .venv/bin/activate`.

Focused helper tests:

```bash
pytest tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py -q
```

Expected assertions:

- New suite parser choices are accepted.
- `memory-compact` still requires proactive accepted compact and still fails on any compact failure.
- Reactive acceptance helper fails without requested/accepted reactive compact and passes with `requested_reactive >= 1`, `compacted_reactive >= 1`, `failed_reactive == 0`.
- Fallback acceptance helper passes only when failed payload has `fallback_action=dispatch`, fallback window diagnostics, terminal success, and no accepted compact for the operation.
- Compact stdout lines remain bounded and start with `SMOKE `.

Focused Host public compact tests:

```bash
pytest \
  tests/host/test_public_compact_smoke.py::test_public_reactive_compact_recovers_with_followup_attempt \
  tests/host/test_public_compact_smoke.py::test_public_compact_failure_dispatches_deterministic_recent_window \
  -q
```

Expected assertions:

- Existing deterministic public Host reactive and fallback tests still pass.
- One-system-message checks continue to pass.

Production semantic regression subset:

```bash
pytest \
  tests/host/test_dispatch_scheduler.py::test_reactive_overflow_recovers_and_dispatches_new_attempt \
  tests/host/test_dispatch_scheduler.py::test_reactive_root_compact_selection_passes_protected_recent_floor \
  tests/host/test_dispatch_scheduler.py::test_reactive_compact_failure_fallback_dispatch_uses_failed_view \
  tests/host/test_dispatch_scheduler.py::test_reactive_fallback_pipeline_uses_memory_policy_caps \
  tests/host/test_dispatch_scheduler.py::test_pre_start_governance_compact_failure_is_attempt_free \
  tests/host/test_run_input_builder.py::test_fallback_provider_renders_only_selected_window_and_current_input \
  tests/host/test_run_input_builder.py::test_fallback_context_messages_render_all_and_only_selected_blocks \
  tests/host/test_run_input_builder.py::test_fallback_context_messages_fail_closed_on_protected_group_mismatch \
  -q
```

Expected assertions:

- Reactive recovery creates a new Attempt.
- Protected recent floor remains enforced.
- Fallback dispatch uses failed view, does not depend on accepted compact artifact, and uses memory policy fallback caps.
- RunInputBuilder fallback renders only selected recent window plus current input and fail-closes on protected floor drift.

Deterministic smoke commands:

```bash
DEEPSEEK_API_KEY=test-provider-key \
python utils/smoke_host_public_conversation_memory_scenarios.py \
  --suite memory-reactive-compact \
  --log-level CRITICAL
```

Expected stdout:

- `SMOKE COMPACT_AUDIT ... requested_reactive=... compacted_reactive=... failed_reactive=0 ...`
- `SMOKE COMPACT_OPERATION ... trigger_source=reactive ... compacted=1 ... failed=0 ...`
- `SMOKE PASS public Host conversation memory scenario smoke`

```bash
DEEPSEEK_API_KEY=test-provider-key \
python utils/smoke_host_public_conversation_memory_scenarios.py \
  --suite memory-compact-fallback \
  --pressure-mode auto \
  --log-level CRITICAL
```

Expected stdout:

- `SMOKE COMPACT_AUDIT ... failed_proactive=...` or the trigger source used by the suite, with at least one failed compact.
- `SMOKE COMPACT_OPERATION ... fallback_action=dispatch ...`
- no full pressure blob;
- no per-delta stream noise;
- `SMOKE PASS public Host conversation memory scenario smoke`.

Existing proactive compact smoke must still pass:

```bash
DEEPSEEK_API_KEY=test-provider-key \
python utils/smoke_host_public_conversation_memory_scenarios.py \
  --suite memory-compact \
  --pressure-mode auto \
  --log-level CRITICAL
```

Expected stdout:

- `SMOKE COMPACT_ACCEPTANCE status=pass requested_proactive=... compacted_proactive=... failed_total=0 artifact_files=...`

Type check:

```bash
python -m pyright utils/smoke_host_public_conversation_memory_scenarios.py tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py
python -m pyright dayu/ tests/ utils/
```

Whitespace:

```bash
git diff --check
```

If only the plan artifact is created during plan gate, validate it with:

```bash
git diff --no-index --check /dev/null docs/host/host-issues/wu-cm-15-public-smoke-reactive-fallback-plan.md
```

For implementation gate, use `git diff --check` after code changes.

## Docs / README Decision

Plan gate:

- No README update.
- No control-doc update.
- The only write is this plan artifact.

Expected implementation gate:

- `utils/` changes do not require README coverage by project rule.
- `tests/` changes require checking `tests/README.md` only if the change alters test organization, test-running contract, or reader-facing test guidance. This WU is expected to add focused tests without changing test organization, so README update is expected to be unnecessary.
- No `dayu/host`, `dayu/engine`, `dayu/config`, or user-facing CLI workflow change is planned. New smoke suite choices are diagnostic utility modes, not end-user workflow.

## Risks / Open Questions

Risks:

- Standalone deterministic compactor stubbing in `utils/` may be considered too close to a private Host runner boundary. Mitigation: keep it smoke-local, bounded to the deterministic suites, and do not modify production Host code. If unacceptable, stop rather than add a production seam.
- The fallback smoke may be sensitive to configured memory policy caps. Mitigation: assert the effective policy and use deterministic prompt/pressure bounds, with failure messages that identify cap/threshold mismatch.
- The smoke command may still require a placeholder provider API key for runtime assembly even though no real provider call should occur. Mitigation: validation commands use `DEEPSEEK_API_KEY=test-provider-key` and assertions must prove deterministic workers handled the dispatches.
- If existing runtime config changes model/profile defaults, deterministic suites should still avoid external provider calls and should fail with assembly diagnostics rather than silently skipping coverage.

Open questions:

- None blocking for plan gate.

## Why This Is Not Over-Designed

- The plan adds two explicit smoke targets for two already-designed and already-tested Host paths; it does not create a new compact framework, benchmark harness, state machine, schema, or public API.
- It reuses existing compact audit helpers, existing public Host smoke structure, and existing deterministic focused-test patterns.
- It keeps fallback out of `memory-compact`, preserving a useful strict acceptance invariant instead of adding flags or mixed semantics.
- It limits code changes to the smoke utility and its tests, leaving Host, Engine, durable storage, provider adapters, and production assembly untouched.

## Completion Report Format

Implementation closeout should report:

- Artifact path: `docs/host/host-issues/wu-cm-15-public-smoke-reactive-fallback-plan.md`
- Key plan decisions implemented.
- Validation run and result, including focused tests, deterministic smoke commands, pyright, and `git diff --check`.
- Blocking questions, if any.
- Residual risks, if any, classified with owner or destination.
