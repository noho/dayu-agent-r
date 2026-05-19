# Host-owned compactor plan fix artifact - Codex

## Gate

- Gate: plan fix after parallel plan review.
- Work unit: Host-owned LLM context compactor public opener contract.
- Source plan: `docs/host/host-owned-compactor-plan.md`.
- Source review artifacts:
  - `docs/reviews/host-owned-compactor-plan-review-ds-gateflow.md`
  - `docs/reviews/host-owned-compactor-plan-review-mimo-gateflow.md`

## Accepted Findings Addressed

- DS R1: fixed. The plan now makes the HostEvent exposure decision explicit and evidence-based: no new `HostEventKind`; compact EventLog facts map through the existing `HostEventKind.PROGRESS` fallback, while Run terminal status remains owned by `RUN_SUCCEEDED` / `RUN_FAILED` / `RUN_CANCELLED`. `CONTEXT_COMPACTION_ATTEMPT_REJECTED` is a committed EventLog canonical fact with diagnostic payload semantics, not a diagnostic-only log and not a new terminal HostEvent kind.
- DS R3: fixed. Slice 4 now explicitly owns `CONTEXT_COMPACTION_ATTEMPT_REJECTED` payload builder and validator work in `dayu/host/context_events.py`, plus focused tests in `tests/host/test_context_compact_events.py`.
- DS R6: fixed. Slice 2 now requires no-network tests to monkeypatch `dayu.host.llm_compaction.run_agent_and_wait` without expanding the `LLMContextCompactor` constructor seam, and requires assertions for `RunnerSpec.max_retries`, `RunnerCallOptions`, disabled tools, and runner failure propagation.
- DS R5 / controller decision: fixed. The plan now states that Slice 1-4 may be local Gateflow checkpoints but are one work unit / one PR readiness boundary, and Slice 1-3 must not be presented as a separately shippable public contract state while transaction splitting is outstanding.
- MiMo residual: fixed. Slice 4 step 1 now says the compactor source seam remains internal, but dispatch / ingest compact control flow must still be restructured into request write, transaction-external LLM call, and result recheck/write.

## Exact Plan Sections Changed

- `docs/host/host-owned-compactor-plan.md` §3.6:
  - Added explicit HostEvent mapping using the current `HostEventKind` contract and `dayu.host.read_api._host_event_from_row(...)` behavior.
  - Clarified `CONTEXT_COMPACTION_ATTEMPT_REJECTED` as an EventLog canonical fact with diagnostic payload semantics.
  - Stated that runner-internal HTTP retry does not write compact EventLog facts or emit HostEvent.
- `docs/host/host-owned-compactor-plan.md` Slice 2 test requirements:
  - Added the concrete monkeypatch target `dayu.host.llm_compaction.run_agent_and_wait`.
  - Required assertions around `AgentRunRequest.runner_spec`, `RunnerSpec.max_retries`, `runner_options`, disabled tools, and runner failure propagation.
  - Prohibited adding public constructor seams solely for tests.
- `docs/host/host-owned-compactor-plan.md` Slice 3 step 7:
  - Replaced the Slice 1-3 boundary with a Slice 1-4 PR readiness boundary.
- `docs/host/host-owned-compactor-plan.md` Slice 4:
  - Added `dayu/host/context_events.py` and `tests/host/test_context_compact_events.py` to the required scope.
  - Clarified step 1 as compactor source seam only, not control-flow preservation.
  - Added `build_context_compaction_attempt_rejected_payload(...)` and `validate_context_compaction_attempt_rejected_payload(...)` requirements.
  - Added attempt rejected payload validation and HostEvent progress mapping tests.
- `docs/host/host-owned-compactor-plan.md` §5.1, §6.2, §7:
  - Added the Slice 1-4 non-shippable intermediate-state risk.
  - Added focused validation commands and expected test names for attempt rejected payload and HostEvent mapping.
  - Updated the implementation handoff summary to include the no-network monkeypatch seam and context event builder/validator scope.

## Validation

- Ran: `git diff --check`
- Result: passed.

## Residual Risks For Implementation Review

- Reactive compaction still needs a concrete pending-operation handoff shape in `EngineEventIngestor`; the plan intentionally leaves that implementation detail to Slice 4 while requiring transaction-external LLM-call tests.
- `CONTEXT_COMPACTION_ATTEMPT_REJECTED` payload field names are now fixed at plan level, but implementation review must verify the chosen EventLog `event_class` is `CANONICAL_FACT` and that no sensitive prompt/provider payload is recorded.
- HostEvent progress mapping depends on preserving current `read_api` projection behavior. Implementation review should reject any attempt-specific `HostEventKind` addition unless a later public contract change explicitly approves it.

## Stop Status

- Code implementation: not started.
- Design document: not edited.
- Commit / push / PR: not performed.
- Stop reason: plan-fix artifact written and required validation completed.
