# P12.6 Slice 7 Review Cleanup - Codex - 2026-05-24

## Gate

- Work unit: P12.6 Slice 7 review cleanup
- Role: fix agent / AgentCodex
- Scope: controller-accepted cleanup items only
- Explicit non-goals: no commit, no push, no change to `docs/host/implementation-control.md`

## Fixed Items

### MiMo F1/F2 - fixed - dispatch/run_input duplicated compact payload parsing

- Added Host-internal `dayu.host.compact_payload`.
- Moved reusable text-list parsing into `optional_text_list_field`.
- Moved compact preserved refs parsing into `preserved_canonical_evidence_refs`.
- Moved compact preserved refs rendering into `preserved_fact_refs_summary`.
- Updated `dayu.host.dispatch` and `dayu.host.run_input` to depend on the shared Host helper instead of keeping duplicate local parsers.
- Updated `tests/host/test_run_input_builder.py` to assert the same payload semantics through the new Host helper, avoiding a production compatibility re-export of the removed private `run_input` helper.

### DS Finding 1 / MiMo F4 - fixed - local EventLogStore construction

- Changed `_latest_session_compacted_event_before_input` to accept the caller-owned `EventLogStore`.
- Changed `_proactive_represented_evidence_refs` to receive and pass through that same store.
- The proactive dispatch path now uses `HostDispatchScheduler._event_log_store` for the latest compacted event lookup.

## Non-Fixed Items

- MiMo F3: accepted-as-non-blocking by controller. `tests/host/fake_compaction.py` continues to reuse the production parser for test helper behavior.
- DS Finding 2 / 3 / 4: recorded as non-fix items per controller instruction; not changed in this cleanup pass.
- Residual risks from prior review: recorded only; no scope expansion in this pass.

## Documentation Decision

- `dayu/host/README.md`: no update required. The existing Host README already describes RunInputBuilder / proactive material sharing and accepted evidence material behavior; this pass only deduplicates implementation helpers and store injection.
- `tests/README.md`: no update required. The test taxonomy and command guidance do not change.

## Validation

- `source .venv/bin/activate && pytest tests/host/test_public_compact_smoke.py -q`
  - Result: passed, `5 passed, 1 skipped`
- `source .venv/bin/activate && pytest tests/host/test_compaction_contract.py tests/host/test_llm_compaction.py tests/host/test_compaction_operation.py tests/host/test_context_compact_events.py tests/host/test_compact_artifact_store.py tests/host/test_memory_projection.py tests/host/test_run_input_builder.py tests/host/test_dispatch_scheduler.py tests/host/test_engine_ingest_mapping.py tests/host/test_public_compact_smoke.py -q`
  - Result: passed, `292 passed, 1 skipped`
- `source .venv/bin/activate && python -m pyright dayu/ tests/`
  - Result: passed, `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - Result: passed

## Risks

- `tests/host/test_run_input_builder.py` was minimally updated because it imported a removed private production helper. Keeping that old import path in production would have required a compatibility re-export, which conflicts with the cleanup goal and project constraints.
- Existing unrelated dirty files remain outside this cleanup pass, including `docs/host/implementation-control.md`; this pass did not modify that control document.
