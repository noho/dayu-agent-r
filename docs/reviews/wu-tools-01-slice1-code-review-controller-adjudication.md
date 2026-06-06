# WU-TOOLS-01 Slice S1 Code Review Controller Adjudication

Gate: code review  
Work unit: WU-TOOLS-01  
Slice: S1 shared document foundations  
Controller: phaseflow  
Date: 2026-06-05  
Decision: needs fix

## Inputs

- Implementation artifact: `docs/reviews/wu-tools-01-slice1-implementation-codex.md`
- AgentMiMo review: `docs/reviews/wu-tools-01-slice1-code-review-mimo.md`
- AgentDS review: `docs/reviews/wu-tools-01-slice1-code-review-ds.md`
- Accepted plan: `docs/host/wu-tools-01-migration-plan.md`

## Review Summary

Both reviewers returned `pass-with-findings`.

Controller accepts one narrow fix and rejects or defers the remaining findings based on the accepted migration principle.

## Findings Adjudication

### M1 / D3: `build_engine_processor_registry` keeps OLD `engine` naming

Decision: split.

- `accepted`: `dayu/documents/processors/registry.py` module docstring still says the registry is for the "core layer". That wording is now wrong for the `dayu.documents` package and should be changed to documents package wording.
- `deferred-with-owner`: renaming `build_engine_processor_registry(...)` is deferred to post-migration cleanup or an explicit later design decision. The accepted S1 plan says copied OLD processor class/function signatures must stay unchanged except import/package references. Renaming this function in S1 would violate that migration principle.

Required fix:

- Update only the misleading module docstring wording in `dayu/documents/processors/registry.py`.
- Do not rename `build_engine_processor_registry(...)`.
- Do not change `_doc_processor_factory.py` function names in this fix gate.

### M2 / D1: processor tests are mostly happy-path and documents coverage is incomplete

Decision: deferred-with-owner.

Reason:

- The S1 accepted plan explicitly requires lightweight deterministic Markdown, HTML and Docling JSON fixture behavior, not full OLD parity or real PDF/OCR conversion.
- AgentCodex and Controller both ran the S1 required validation successfully.
- DS correctly identified uncovered areas, but several are intentionally consumed by later slices: Doc tools in S3, Fins in S4, Web HTML conversion in S5, combined acceptance in S6.

Owner / destination:

- Track as `WU-TOOLS-01-S1-R1` for later WU-TOOLS-01 slices and final residual reconciliation.

### D2: `PageAwareProcessor` missing from `__all__`

Decision: rejected-with-reason.

Reason:

- Direct code evidence shows `dayu/documents/processors/__init__.py` imports `PageAwareProcessor` on line 6 and includes `"PageAwareProcessor"` in `__all__`.
- No fix required.

### D4: `TypeVar` import position in `search_utils.py`

Decision: rejected-with-reason.

Reason:

- The reviewer itself classified it as an import audit note with no actual defect.
- No fix required.

## Residual Risks

- `WU-TOOLS-01-S1-R1`: documents test coverage / parity. Later slices must cover `_doc_processor_factory.py`, `ProcessorRegistry` fallback paths, HTML pipeline primitives, and Docling runtime integration when those paths become consumed.
- `WU-TOOLS-01-S1-R2`: OLD `build_engine_processor_registry(...)` naming. The function name remains intentionally unchanged in S1 to preserve migrated OLD function signatures. Revisit after WU-TOOLS-01 migration if public naming cleanup is still valuable.

## Next Gate

Dispatch AgentCodex for a narrow fix gate limited to the accepted docstring wording fix and a fix artifact.
