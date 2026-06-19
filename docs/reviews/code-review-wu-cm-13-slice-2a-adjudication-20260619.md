# WU-CM-13 Slice 2a Code Review Adjudication

## Scope

- Work unit: `WU-CM-13`
- Gate: code review after Slice 2a implementation
- Reviewed implementation scope: proactive dispatch wiring to shared compact pipeline helpers
- Review artifacts:
  - `docs/reviews/deepreview-20260619-212804.md`
  - `docs/reviews/deepreview-wu-cm-13-slice-2a-20260619-212944.md`
- Validation:
  - `pytest tests/host/test_dispatch_scheduler.py tests/host/test_compact_pipeline.py -q` passed with 88 tests.
  - `python -m pyright dayu/ tests/ utils/` passed with 0 errors.
  - `git diff --check` passed.
  - Required search for tier 5, `fallback_tier`, old proactive fallback helpers, direct `select_compact_segment(...)`, and direct `build_compact_material_pack(...)` in `dayu/host/dispatch.py` returned no matches.

## Judgment

Both reviews are accepted as PASS. Slice 2a satisfies the accepted plan boundary:

- proactive normal request construction now uses `build_normal_compact_request_plan(...)`;
- proactive tier 1-3 recovery request construction now uses `build_tier_recovery_request_plans(...)`;
- proactive fallback failed payload / decision input now uses `build_fallback_decision_input(...)`;
- EventLog append, artifact write, fail-unstarted, pending dispatch / start, stale guards, cursor guards, and lifecycle transitions remain caller-owned in `dispatch.py`;
- no reactive `engine_ingest.py`, `run_input.py`, tier 5, `fallback_tier`, public API, durable schema, EventLog canonical semantic, Engine contract, or compact artifact contract change was introduced.

## Finding Decisions

| Finding | Decision | Reason |
|---|---|---|
| fallback selection failure log no longer carries `exc_info=True`. | rejected-with-reason | The exception is now intentionally captured inside `build_fallback_decision_input(...)` and converted into structured failed payload input. The durable EventLog payload carries the fallback selection failure reason and remains the audit truth. This is an observability preference, not a correctness or recovery issue, and should not block Slice 2a. |
| Slice 2b / 2c not implemented. | deferred-with-owner | This is planned follow-up scope, not a Slice 2a defect. Owner: WU-CM-13 Slice 2b / 2c. |

## Conclusion

Slice 2a may proceed to accepted slice commit. No fix gate is required before committing this slice. The next gate is WU-CM-13 Slice 2b reactive ingest wiring.
