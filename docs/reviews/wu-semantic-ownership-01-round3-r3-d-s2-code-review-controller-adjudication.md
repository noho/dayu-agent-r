# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-D S2 Code Review Controller Adjudication

## Metadata

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 / Round3 / R3-D`
- Slice: `S2 - Virtual Section Consistency, Source Freshness, And Read Failure Contracts`
- Gate: code review adjudication
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-round3-r3-d-s2-implementation-codex.md`
- Controller validation: `docs/reviews/wu-semantic-ownership-01-round3-r3-d-s2-controller-validation.md`
- MiMo review: `docs/reviews/wu-semantic-ownership-01-round3-r3-d-s2-code-review-mimo.md`
- DS review: `docs/reviews/wu-semantic-ownership-01-round3-r3-d-s2-code-review-ds.md`
- Decision: one accepted low-severity fix; proceed to fix gate

## Findings

| ID | Source | Decision | Severity | Required fix |
| --- | --- | --- | --- | --- |
| `R3-D-S2-CR-F01` | MiMo finding 1; DS residual note | accepted | low | Remove the unreachable `except FinsSourceDecodeError` branch in `FinsReadRuntime._get_or_create_processor()`. `_create_processor()` already converts decode failures to `FinsReadBusinessError(ErrorCode.SOURCE_DECODE_FAILED, ...)`, so the outer branch is dead code. Keep behavior unchanged and verify invalid UTF-8 mapping still passes. |

## Rejected / Deferred / Needs-More-Evidence

- None.

## Residual Risk Classification

- Downloader-side `errors="ignore"` matches remain outside S2 read owner path and outside S2 allowed files; no current fix.
- Non-UTF-8 business charset support remains assigned to a later encoding-policy work unit if product requirements demand it.
- Cache revision read overhead remains assigned to later profiling/performance optimization if measured.
- Full `pytest tests/fins -q` remains covered by approved S3 aggregate validation.

## Fix Validation Required

Minimum fix validation:

```bash
source .venv/bin/activate
pytest tests/fins/test_processor_read_consistency.py::test_read_runtime_maps_invalid_utf8_to_source_decode_failure -q
pytest tests/fins/test_processor_read_consistency.py tests/fins/test_read_runtime_semantic_ownership_guards.py -q
python -m pyright dayu/ tests/ utils/
git diff --check
```

The fix must not modify S3, R3-E, Host, Engine, upload/download security, or tool-security files.
