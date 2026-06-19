# WU-CM-12 Final Closeout - 2026-06-19

## Scope

WU-CM-12 reopened after draft PR #150 review for final conversation memory compact stability and diagnostic closure. This closeout covers the three-way `$deepreview --all` pass by AgentMiMo, AgentCodex, and AgentDS, the accepted fixes, focused re-review, and local validation.

## Review Artifacts

- AgentDS: `docs/reviews/repo-review-20260619-164637.md`
- AgentCodex: `docs/reviews/repo-review-20260619-164912.md`
- AgentMiMo: `docs/reviews/repo-review-20260619-165328.md`

## Accepted Fixes

- Proactive compact recovery now persists operation-level rejected attempts from initial and recovery tiers, with continuous attempt numbers and accurate failed `attempt_count`.
- Reactive recovery no longer gets stuck if post-commit memory catch-up fails; catch-up failure is logged and recovery dispatch still starts.
- Reactive fail-closed now propagates `_fail_recovering_run` rejection instead of always reporting accepted closeout.
- Compaction proposal cancellation after manifest recording now returns a cancellation rejected attempt with the manifest reference when the Host cancellation token is already cancelled.
- Memory projection no longer crashes when turn-floor candidate items lack `run_id`; those items are not protected by the turn floor.
- Memory snapshot JSON integer fields now reject JSON bool values instead of interpreting `true` / `false` as integers.
- Tests now cover normalized material text, multi-item previous compacted view splitting, attempt-rejected projection filtering, recovery-tier rejected attempt persistence, reactive recovery catch-up failure, recovering fail rejection propagation, and cancellation manifest preservation.

## Validation

- `pytest tests/host/test_dispatch_scheduler.py tests/host/test_engine_ingest_mapping.py tests/host/test_memory_projection.py tests/host/test_compact_material.py tests/host/test_compaction_operation.py -q` passed: `277 passed`.
- `pytest tests/host/test_dispatch_scheduler.py::test_proactive_compaction_recovery_all_tiers_fail_uses_dispatch_fallback tests/host/test_dispatch_scheduler.py::test_compaction_repair_attempt_rejection_is_recorded_in_eventlog -q` passed after final formatting fix: `2 passed`.
- `pyright dayu/ tests/ utils/` passed: `0 errors`.

## Re-review

Focused re-review result:

- AgentCodex: previous finding closed; no blocking finding.
- AgentDS: blocking findings closed; remaining observations are non-blocking policy / design follow-ups.
- AgentMiMo: high-priority coverage findings closed; remaining findings are non-blocking old debt or broader design / cleanup issues. One formatting issue in `dispatch.py` was accepted and fixed before closeout.

## Residuals

- `WU-CM-12-PR-R3` is closed by this final diagnostic fix: recovery-tier rejected attempts are now persisted and counted.
- Reactive compact recovery tier 1-3 remains deferred to `WU-CM-13` and is not part of this closeout.
- Broader old-debt observations from review, including Engine internal RuntimeError classification, Fins-to-Host wait adapter dependency, and compact previous-view text delimiter brittleness, are not WU-CM-12 blockers and require separate owner assignment before implementation.

## Constant Audit

No new LLM-facing memory material / compact material production constants were introduced in this final fix. Existing non-`memory_projection_policy` constants observed in the touched code are diagnostic schema ids, event id prefixes, parser labels, prompt-local label prefixes, cancellation/failure reason strings, or estimator constants; they do not truncate, preview, summarize, row-limit, chunk-limit, or field-cap EventLog-derived LLM-facing memory / compact material.
