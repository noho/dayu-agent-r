# WU-LIFE-03 Aggregate Deepreview Controller Adjudication

## Scope

- Work unit: `WU-LIFE-03`
- Gate: aggregate deepreview
- Base: `main`
- Branch: `phase/host-engine-next`
- Review artifacts:
  - `docs/reviews/wu-life-03-aggregate-deepreview-mimo.md`
  - `docs/reviews/wu-life-03-aggregate-deepreview-ds.md`

## Controller Decision

Aggregate deepreview passes. No current fix is required before draft PR gate.

Both review lanes conclude that WU-LIFE-03 satisfies the plan:

- Host durable truth for accepted active cancel no longer depends on worker, provider, or tool cooperation.
- Timeout path closes `CANCELLING` active Runs as `CANCELLED` through Host-owned durable terminal facts.
- First-committer-wins, late terminal rejection, awaiting/suspend rejection, replay, queue promotion, projection, startup watchdog tick, and recovery defer are consistent across Slice 1 and Slice 2.
- No Host / Engine layering, `dayu.runtime`, EventLog schema, Service public API, or LLM-facing text violation was found.
- README/design/control docs describe implemented behavior and do not claim future provider/tool hard-kill capability.

## Non-blocking Observations

### AGG-OBS-01 watchdog scan uses non-terminal full scan

- Source: DS observation 01.
- Status: deferred-with-owner.
- Owner / destination: GitHub Issue #87 umbrella follow-up for Host lifecycle watchdog runtime tuning after #91 / WU-LIFE-03.
- Reasoning: `read_non_terminal_runs(...)` plus Python filtering is correct for the current semantics. It may need query-level optimization under high non-terminal Run volume, but this is performance tuning, not correctness.

### AGG-OBS-02 timeout closeout does not clean active worker handles

- Source: DS observation 02.
- Status: deferred-with-owner.
- Owner / destination: `WU-TOOLS-CANCEL-01`.
- Reasoning: WU-LIFE-03 intentionally fixes Host durable terminal truth and does not implement physical provider/tool interruption or execution capsule cleanup. The residual risk is already assigned to WU-TOOLS-CANCEL-01.

### AGG-OBS-03 `_cancel_request_event_id_from_cancelling` theoretical `payload_json=None` boundary

- Source: DS observation 03.
- Status: accepted-risk.
- Reasoning: current durable schema and EventLog append contract protect `payload_json` as present material. The observed `json.loads(None)` path is a theoretical boundary, not a reachable current defect. No current fix is required.

## Validation

Controller validation already run after Slice 2 fix:

```bash
source .venv/bin/activate && pytest tests/host/test_active_cancel_dispatch.py tests/host/test_public_cancel_session_runs.py tests/host/test_public_cancel_smoke.py tests/host/test_dispatch_scheduler.py tests/host/test_open_host_runtime.py tests/host/test_recovery_scan.py -q
```

Result: `142 passed`.

```bash
source .venv/bin/activate && pytest tests/host/test_run_attempt_transitions.py tests/host/test_engine_ingest_mapping.py -q
```

Result: `123 passed`.

```bash
source .venv/bin/activate && pyright
```

Result: `0 errors, 0 warnings, 0 informations`.

```bash
source .venv/bin/activate && git diff --check
```

Result: passed.

## Next Gate

Proceed to ready-to-open-draft-PR gate after committing the aggregate deepreview artifacts and control-doc update.
