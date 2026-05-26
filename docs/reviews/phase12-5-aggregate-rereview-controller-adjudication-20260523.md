# Controller Adjudication

## Scope

- Phase: P12.5 Conversation Memory Optimization
- Gate: Aggregate deepreview / re-review
- Accepted implementation head before repair: `0dbcc5a`
- Design truth: `docs/host/design.md`
- Control doc: `docs/host/implementation-control.md`
- Review artifacts:
  - `docs/reviews/phase12-5-aggregate-deepreview-mimo-20260523.md`
  - `docs/reviews/phase12-5-aggregate-deepreview-ds-20260522.md`
  - `docs/reviews/phase12-5-aggregate-rereview-mimo-20260523.md`
  - `docs/reviews/phase12-5-aggregate-rereview-ds-20260523.md`

## Decision

PASS. P12.5 is ready to open a draft PR after this aggregate repair is committed.

DS aggregate deepreview initially found two severe and three high issues. The severe issues were valid: the LLM compactor only saw opaque evidence ids, and memory projection lag could close a Run as failed. The repair changes address those root causes rather than papering over tests:

- accepted evidence envelopes now carry bounded `result_preview` derived from accepted tool outcomes;
- LLM compaction prompt renders accepted evidence envelope fields and preview before asking for evidence-backed fact candidates;
- `FakeContextCompactor` now consumes `accepted_evidence_envelopes` and derives deterministic claims from preview content;
- dispatch catches projection catch-up failures and lag-over-threshold repair through rebuild / retry, and no longer maps lag repair to Run / Attempt terminal closeout;
- `EvidenceBackedFactView` now enforces the same `claim_text` length cap as the candidate contract.

## Validation

- `source .venv/bin/activate && pytest tests/host/test_toolruntime_accept_barrier.py tests/host/test_llm_compaction.py tests/host/test_compaction_contract.py tests/host/test_compaction_operation.py tests/host/test_memory_projection.py tests/host/test_run_input_builder.py tests/host/test_dispatch_scheduler.py tests/host/test_compact_artifact_store.py tests/host/test_toolruntime_executor.py tests/service/test_host_assembly.py tests/runtime/test_config_loader.py`
  - Result: PASS, 260 passed.
- `source .venv/bin/activate && pyright`
  - Result: PASS, 0 errors.
- `git diff --check`
  - Result: PASS.

## Residual Risks

- `_NeverCancelledToken` still prevents in-flight compaction LLM calls from being cancelled immediately on session close. This is bounded by the compactor runner timeout and stale output checks, but should be handled by a follow-up Host runtime cancellation hardening work unit.
- `result_preview` is a Host-neutral canonical JSON preview. It gives the extractor real evidence content, but highly nested tool results may still need future tool-provider-owned summaries for better extraction quality.
- Rebuild after projection lag has no dedicated timeout / backoff policy. The current path is correctness-safe and avoids Run failure; future performance hardening should add observability and retry budgeting for large sessions.

## Ready-To-Open-Draft-PR

The phase exit condition requiring aggregate deepreview from at least two review agents is satisfied after re-review:

- MiMo re-review: PASS.
- DS re-review: PASS and explicitly marked ready-to-open-draft-PR.
