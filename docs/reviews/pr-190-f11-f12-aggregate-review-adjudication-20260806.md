# PR 190 F11/F12 Aggregate Review Adjudication

## Gate

- Aggregate base: `3087b1b983a97ce5012d54e818795f4755434a98`
- Reviewed head: `2cf1b4ac`
- MiMo artifact: `docs/reviews/pr-190-f11-f12-aggregate-mimo-review-20260806.md`
- DeepSeek artifact: `docs/reviews/pr-190-f11-f12-aggregate-ds-review-20260806.md`
- Controller decision date: 2026-08-06

MiMo reported PASS with no finding. DeepSeek reported PASS with three low findings and three open questions. The controller adjudicates each
item independently below.

## Findings

### DS-01 — `CompactSemanticSectionV3` and the public structure projection can drift

**Decision: accepted as a low-severity owner-test gap.**

The runtime types have different legitimate owners: `CompactSemanticSectionV3` owns Host semantic coverage categories, while
`compact_structure.py` owns the LLM output shape. They should not be collapsed into a cyclic import or a generated enum. However, the five
semantic section names are a required cross-contract invariant and the existing structure-owner test already centralizes the public
template/schema/rules/parser equality assertion. A single additional assertion there is the minimal, non-invasive closure:

```python
tuple(item.value for item in CompactSemanticSectionV3) == tuple(compact_output_template_v3())[1:]
```

This catches field rename/add/delete drift without exporting `_ROOT`, adding a second owner, or changing runtime behavior.

### DS-02 — Prompt business descriptions are handwritten rather than generated from `_ROOT`

**Decision: rejected as a finding.**

Structure and business meaning are intentionally separate semantic owners. The structure descriptor mechanically owns field names, types,
requiredness, allowed values, template, schema, parser, and concise structural rules. The prompt asset owns the business-readable meaning,
source-kind restrictions, meaningful-or-null rule, and LLM-facing prohibitions required by AGENTS.md. Generating that prose from the shape
would either duplicate business semantics into a structure descriptor or reduce the prompt to non-self-contained schema text. Current owner
tests and prompt hash tests already fail if the prompt contract changes. No code or prompt change is authorized.

### DS-03 — Broad `except Exception` in fallback selection loses traceback

**Decision: rejected for this work unit; record as pre-existing observability debt.**

Direct history proves the broad catch existed unchanged at prior completed work-unit base `3087b1b9`. It implements the accepted safety
principle that any unexpected fallback selection/estimation failure returns a deterministic fail-closed decision rather than escaping the
Host lifecycle. Changing exception taxonomy or logging ownership is unrelated to F11/F12 and would expand scope. The durable failure reason
and caller error log remain available, but stack-level diagnostics are a future Host observability owner concern.

## Open questions

### OQ-01 — Dedicated `test_compact_structure.py` / coverage gap

**Decision: not a gap.**

Test ownership follows the public contract rather than mirroring production filenames. `test_compaction_contract.py` and
`test_llm_compaction.py` exercise strict duplicate/unknown/missing/type/enum/empty/round-trip behavior. Final coverage must still prove the
changed file is at least 80%; a dedicated filename is not required.

### OQ-02 — Oracle adjudication before or after merge

**Decision: already frozen by the user; not open.**

The explicit next entry point is Oracle-controller adjudication on the final PR head after implementation Gateflow closeout. PR 190 remains
draft and will not be merged or marked ready in this work unit, so no post-merge sequencing assumption is being made.

### OQ-03 — `session_summary=null` consumer semantics

**Decision: already directly covered; no further fix.**

`tests/host/test_memory_projection.py::test_accepted_compact_without_summary_clears_prior_session_summary` proves full-replacement clear
semantics at the Memory owner. Current Memory/RunInput tests and real reconnect observation cover downstream continuity. The aggregate review
executed those suites successfully.

## Required fix and re-review

Only DS-01 is accepted:

- add the structure/semantic-section equality assertion to the existing owner-level test;
- run the focused structure/LLM compaction tests, changed-file coverage for `compact_structure.py`, pyright, Ruff, and `git diff --check`;
- write a dedicated aggregate-fix artifact;
- obtain independent MiMo and DeepSeek aggregate re-reviews.

No production, prompt, schema, registry, README, design, evidence, or PR-body behavior may change in this fix.

