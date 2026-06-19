# WU-CM-12-FIX-R1 Slice 2 Code Review Adjudication

## Scope

- Work unit: `WU-CM-12-FIX-R1`
- Slice: 2, accepted tool evidence provider limit removal
- Implementation artifact: `docs/reviews/wu-cm-12-fix-r1-s2-implementation-codex-20260618.md`
- Code review artifacts:
  - `docs/reviews/code-review-20260618-191048.md` (AgentDS)
  - `docs/reviews/code-review-20260618-191823.md` (AgentMiMo)

## Controller Decision

Slice 2 code review gate is accepted. The implementation removes the private accepted evidence row-count truth and delegates accepted evidence material semantics to the EventLog-backed compact material builder, without adding public API, durable schema, EventLog canonical semantic, Engine contract, or WU-CM-13 reactive recovery changes.

## Finding Adjudication

| Finding | Source | Decision | Rationale |
| --- | --- | --- | --- |
| Provider compact-present scenario lacks a provider-level test | AgentDS finding 1 | rejected-with-reason | The finding is a valid observation but not a current-slice blocker. `DurableAcceptedToolEvidenceMaterialProvider` is now a thin adapter over `build_pre_dispatch_compact_material_view(...)`, and compact-present delta boundary behavior belongs to that EventLog material builder. The builder's compact-present behavior is already covered in `tests/host/test_compact_material.py`; adding a second provider fixture with synthetic `CONTEXT_COMPACTED` would duplicate lower-layer contract tests and increase coupling. Slice 2 tests cover the new provider responsibilities: no private row cap, accepted evidence block filtering, represented refs exclusion, and raw outcome/readable query material. |

## Accepted Evidence

- AgentMiMo review: no substantive findings.
- AgentDS review: core implementation verified; one low test-gap observation was rejected with reason above.
- Validation from implementation: `pytest tests/host/test_run_input_builder.py tests/host/test_compact_material.py -q` PASS (`118 passed`); `pyright dayu/host/run_input.py tests/host/test_run_input_builder.py tests/host/test_compact_material.py` PASS (`0 errors`); `git diff --check` PASS; old private symbols absent from `dayu` and `tests`.

## Residual Risks

- Long-session material view construction cost remains a non-blocking deferred residual for a future Host material source performance hardening WU if real production evidence shows latency pressure. It is not owned by WU-CM-13 and does not justify reintroducing a private row limit or page correctness cap.
