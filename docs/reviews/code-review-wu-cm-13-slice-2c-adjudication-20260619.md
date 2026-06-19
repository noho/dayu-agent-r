# WU-CM-13 Slice 2c Code Review Adjudication

## Scope

- Work unit: `WU-CM-13`
- Gate: code review after Slice 2c implementation
- Reviewed implementation scope: RunInput ordinary protected raw-tail wiring to the shared compact pipeline helper
- Review artifacts:
  - `docs/reviews/deepreview-20260619-220450.md`
  - `docs/reviews/deepreview-wu-cm-13-slice-2c-20260619-220501.md`
- Validation:
  - `pytest tests/host/test_run_input_builder.py tests/host/test_compact_pipeline.py -q` passed with 107 tests.
  - `python -m pyright dayu/ tests/ utils/` passed with 0 errors.
  - `git diff --check` passed.
  - Required search confirmed no remaining `run_input.py` owner for `_protected_recent_raw_tail_blocks`; `compact_pipeline.py` owns `select_ordinary_protected_raw_tail(...)`; the remaining `protected_recent_turn_group_ids_for_material_blocks` use in `run_input.py` is the explicit fallback branch non-goal.

## Judgment

Both reviews are accepted as PASS. Slice 2c satisfies the accepted plan boundary:

- RunInput ordinary post-compaction raw-tail selection now delegates to `select_ordinary_protected_raw_tail(...)`.
- `_DurableProtectedRecentRawTailProvider` remains the EventLog second-read adapter, but no longer owns protected group eligibility or memory dedup semantics.
- The second-read adapter validates the accepted compact event, reconstructs the compact material source snapshot, and obtains the original trigger source from the paired `CONTEXT_COMPACTION_REQUESTED` event.
- Fallback RunInput assembly remains on `_fallback_context_messages(...)` and is not migrated in this slice.
- LLM-facing accepted tool evidence source rendering filters internal event, payload, artifact, and digest provenance while keeping business-readable source text.
- No `dispatch.py`, `engine_ingest.py`, tier 5, `fallback_tier`, public API, durable schema, EventLog canonical semantic, Engine contract, or compact artifact contract change was introduced.

## Finding Decisions

| Finding | Decision | Reason |
|---|---|---|
| Extra EventLog read is required to recover `trigger_source` from the paired request event. | accepted-as-nonblocking | This preserves the no-schema-change boundary of WU-CM-13. Moving `trigger_source` into `CONTEXT_COMPACTED` would be a contract/schema discussion outside the accepted slice scope. |
| `WU-CM-14-RR-1` reactive material convergence residual. | closed | Slice 2a and Slice 2b moved proactive/reactive compact request, recovery, and fallback decision construction to shared helpers; Slice 2c moved ordinary post-compaction raw-tail eligibility into `compact_pipeline.py`. Review artifacts confirm the WU-CM-14 preservation path is no longer proactive-only, reactive-only, or RunInput-only selection logic. |
| `WU-CM-14-RR-3` EventLog second-read residual. | closed | The second-read remains intentionally caller-owned for durable freshness, but the selection semantics are now pipeline-owned and audited through `select_ordinary_protected_raw_tail(...)`. Replacing the read with a frozen handoff would require a broader lifecycle/contract change and is not needed to satisfy WU-CM-13. |
| `WU-CM-13-S1-R1` compact quality/provenance edge. | deferred-with-owner | Slice 2c adds focused LLM-facing provenance filtering for ordinary raw-tail evidence rendering, but final closure should be decided during aggregate deepreview / final smoke because the original residual targeted accepted compact quality gate coverage across the whole WU. |

## Conclusion

Slice 2c may proceed to accepted slice commit. No fix gate is required before committing this slice. After the accepted slice commit, the next gate is WU-CM-13 aggregate deepreview.
