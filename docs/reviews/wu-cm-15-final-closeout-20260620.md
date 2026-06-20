# WU-CM-15 Final Closeout

## Result

WU-CM-15 has passed the draft PR gate and final closeout.

Draft PR: https://github.com/noho/dayu-agent-r/pull/157

The work unit stayed within the user-confirmed scope: add public smoke coverage for reactive compact and deterministic compact-failure fallback. It did not modify Host / Engine / runtime / Service public contracts, schemas, or prompts. The only production code change is Host compact attempt rejection logging: attempt-level rejection diagnostics are WARNING, while terminal failure / fallback outcome severity remains owned by the surrounding dispatch and engine-ingest closeout path.

## Delivered

- Added explicit public smoke suites:
  - `memory-reactive-compact` for deterministic provider-overflow reactive compact and recovery dispatch.
  - `memory-compact-fallback` for deterministic compact failure and fallback dispatch.
- Preserved existing `memory-compact` semantics:
  - proactive compact request required;
  - accepted compact required;
  - compact artifacts required;
  - any compact failure remains a hard failure.
- Added deterministic smoke infrastructure for ordinary worker dispatch capture and compactor accept/reject behavior.
- Added bounded compact audit / fallback diagnostics without printing full pressure blobs, compactor prompts, provider payloads, or per-delta stream logs.
- Adjusted compact attempt rejection logging so deterministic fallback dispatch no longer emits attempt-level ERROR records before a successful degraded fallback outcome.
- Adjusted compact pressure observability so fallback reserve tokens are included in the printed effective / total pressure estimate.
- Added tests for suite parsing, reactive old-marker oracle, fallback selected / dropped / current window oracle, compact audit parsing, pressure bounds, and helper failure cases.
- Updated `tests/README.md` for the new runtime assembly coverage.
- Updated `docs/host/issues-implementation-control.md` with plan, implementation, review, aggregate review, fix, validation, residuals, and final state.

## Review History

- Accepted plan commit: `97518e93`.
- Accepted implementation slice commit: `572a88df`.
- Pre-PR closeout commit: `0fe4e910`.
- Draft PR: https://github.com/noho/dayu-agent-r/pull/157.
- PR review artifacts:
  - `docs/reviews/pr-157-review-20260620-134300.md` (AgentMiMo): PASS, no material findings.
  - `docs/reviews/pr-157-review-20260620-134346.md` (AgentDS): PASS, no material findings.
- Accepted PR review / final closeout commit: `5e04a841`.
- Plan review / fix / re-review passed.
- Code review / fix / focused re-review passed.
- Aggregate deepreview passed after small closeout fixes.
- Aggregate-fix focused re-review passed from AgentMiMo and AgentDS.
- PR review passed from AgentMiMo and AgentDS. No fix / re-review loop was required.

## Validation

- `source .venv/bin/activate && pytest tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py -q`
  - Passed: `20 passed`.
  - Warnings: existing third-party `edgar` deprecation warnings.
- `source .venv/bin/activate && DEEPSEEK_API_KEY=test-provider-key python utils/smoke_host_public_conversation_memory_scenarios.py --suite memory-reactive-compact --log-level CRITICAL`
  - Passed.
- `source .venv/bin/activate && DEEPSEEK_API_KEY=test-provider-key python utils/smoke_host_public_conversation_memory_scenarios.py --suite memory-compact-fallback --pressure-mode auto --log-level CRITICAL`
  - Passed.
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - Passed: `0 errors`.
- `git diff --check`
  - Passed.
- PR checks:
  - `gh pr checks 157`
    - No checks reported on the `phase/wu-cm-15` branch.
  - `gh pr view 157 --json statusCheckRollup`
    - Empty status check rollup.
- Closeout logging fix validation:
  - `source .venv/bin/activate && pytest tests/host/test_compaction_operation.py::test_run_compaction_operation_logs_terminal_reject_as_warning tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py::test_pressure_off_and_padding_helper_cover_runtime_pressure_bounds`
    - Passed: `2 passed`.
  - `source .venv/bin/activate && pytest tests/host/test_compaction_operation.py`
    - Passed: `31 passed`.
  - `source .venv/bin/activate && pytest tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py`
    - Passed: `20 passed`.
  - `source .venv/bin/activate && pyright`
    - Passed: `0 errors`.
  - `source .venv/bin/activate && python utils/smoke_host_public_conversation_memory_scenarios.py --suite memory-compact-fallback --pressure-mode auto --log-level DEBUG > workspace/tmp/cm-smoke-fallback-log-fix-20260620-131005.log 2>&1`
    - Passed. The fallback pressure line includes reserve / effective pressure, and there are no `[ERROR]` log lines.

## Fresh Smoke Evaluation

Fresh full-suite smoke logs were collected under `workspace/tmp/cm-smoke-fresh-20260620-125037` with `--log-level DEBUG`:

- `memory-core`: passed.
- `memory-compact`: passed after rerun; the first failed command was a local harness invocation error caused by passing `"--pressure-mode auto"` as one shell argument.
- `memory-reactive-compact`: passed.
- `memory-compact-fallback`: passed after rerun; the first failed command had the same local harness invocation error.

Evaluation result:

- Log level is appropriate for diagnostics. The remaining high-volume per-delta stream detail belongs to GitHub Issue #148 / WU-CLI-DEBUG-STREAM-01 and is not treated as WU-CM-15 noise.
- The smoke suite now covers the primary Conversation Memory public paths: ordinary continuity, proactive accepted compact, reactive compact recovery, and compact-failure fallback dispatch.
- No Conversation Memory production correctness bug was found by the full smoke run. The only production code polish accepted in closeout is attempt-level log severity for failed compact attempts.

## Residuals

- Real-provider `memory-compact` requires valid model / compactor provider keys. Owner: smoke runner environment. Destination: operational smoke precondition, not WU-CM-15 code residual.
- `_patched_compactor_runner(...)` remains smoke-local monkey-patching around `dayu.host.llm_compaction._run_agent_request`; it fails clearly if the hook changes and restores the original runner in `finally`. Owner: future smoke maintenance if Host internal compactor runner moves. Destination: no current follow-up issue because the failure mode is fail-closed and limited to `utils/`.
- Future smoke hardening may decide whether reactive acceptance should also reject nonzero `rejected_proactive`. Owner: future smoke hardening. Destination: deferred only if future config can emit proactive rejection without request / compacted / failed counts.
- Larger smoke maintainability refactors, such as splitting deterministic infrastructure or extracting shared public Host smoke flow, are intentionally deferred. Owner: future smoke maintenance; not required for WU-CM-15.
- Per-delta DEBUG log volume is owned by GitHub Issue #148 / WU-CLI-DEBUG-STREAM-01.
- Compaction artifact retention is tracked separately by GitHub Issue #156, now recorded as a child of #78. #78 remains purge-session-driven retention cleanup; no internal automatic scheduler is required for this WU.

## Next Entry

After the user manually merges draft PR 157, pull the latest `main` from GitHub and start the next phaseflow from `docs/host/issues-implementation-control.md` entry point `WU-CLI-DEBUG-STREAM-01`, backed by GitHub Issue #148.

No mark-ready, reviewer request, merge, branch deletion, or issue closure was performed by this closeout.
