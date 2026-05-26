# Controller Adjudication

## Scope

- Phase: P12.5 Conversation Memory Optimization
- Slice: Slice 7 Integration Smoke, README Sync, Aggregate Validation
- Design truth: `docs/host/design.md`
- Control doc: `docs/host/implementation-control.md`
- Review artifacts:
  - `docs/reviews/phase12-5-slice7-code-review-mimo-20260522.md`
  - `docs/reviews/phase12-5-slice7-code-review-ds-20260522.md`

## Decision

PASS.

Both review agents found no blocking defect in the Slice 7 workspace changes. The implementation proves the P12.5 smoke target at the Host memory / RunInputBuilder boundary:

- accepted tool result creates accepted evidence envelope availability, but not stable facts by itself;
- accepted `CONTEXT_COMPACTED.evidence_backed_fact_candidates` materializes stable `evidence_backed_facts`;
- RunInputBuilder renders post-compaction facts with `claim_text` and `evidence_refs`;
- minimum preserve continuity renders bounded ordered-reference context without retaining the full long input;
- old `verified_*` public contract names are absent from active production paths and remain only in fail-closed guards / tests.

## Validation

- `source .venv/bin/activate && pytest tests/host/test_compact_artifact_store.py tests/host/test_toolruntime_accept_barrier.py tests/host/test_compaction_contract.py tests/host/test_context_compact_events.py tests/host/test_compaction_operation.py tests/host/test_llm_compaction.py tests/host/test_memory_projection.py tests/host/test_run_input_builder.py tests/service/test_host_assembly.py tests/runtime/test_config_loader.py`
  - Result: PASS, 221 passed.
- `source .venv/bin/activate && pyright`
  - Result: PASS, 0 errors.
- Old-term scans:
  - `verified_facts|max_verified_facts|VerifiedFact|verified fact|verified_fact|TOOL_VERIFIED|PRETENDS_VERIFIED|proposed_verified|preserved_verified|stable:verified|max_verified`
  - `preserved_fact_refs|tool_fact_refs|verified_fact_refs|preserved_verified|proposed_verified`
  - Result: active production old verified/tool fact contract usage is absent; remaining hits are fail-closed guards, fail-closed tests, current `preserved_fact_refs` payload container naming, or historical docs/review artifacts.

## Residual Risks

- Public-path no-compaction continuity smoke is not added in this slice. Current coverage proves recent raw turn / older raw turn continuity and post-compaction fact reuse at the Host durable EventLog / memory projection / RunInputBuilder boundary. Owner: aggregate review may decide whether to add a public smoke before draft PR; otherwise move to follow-up public smoke hardening.
- `compaction_evidence.py` still uses a conservative session-filtered EventLog read from sequence 1 for compact evidence input collection. This is correctness-safe but not the final optimized query boundary. Owner: aggregate review or follow-up performance hardening.
- Candidate JSON helper duplication remains tolerable after Slice 7 because behavior is covered by contract tests and focused smoke. Owner: aggregate review may request refactor only if it finds a real maintenance or correctness risk.
