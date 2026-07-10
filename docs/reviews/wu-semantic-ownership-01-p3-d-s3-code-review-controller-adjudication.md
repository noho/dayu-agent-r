# WU-SEMANTIC-OWNERSHIP-01 / P3-D / S3 Code Review Controller Adjudication

## Inputs

- MiMo review: `docs/reviews/wu-semantic-ownership-01-p3-d-s3-code-review-mimo.md`
- DS review: `docs/reviews/wu-semantic-ownership-01-p3-d-s3-code-review-ds.md`
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-p3-d-s3-implementation-codex.md`
- Controller validation: `docs/reviews/wu-semantic-ownership-01-p3-d-s3-controller-validation.md`

## Findings

### P3-D-S3-CR-F01 - accepted - tests compare typed error codes directly with string literals

- Source: MiMo finding 001.
- Decision: accepted.
- Correct owner boundary: Engine contract tests and Agent behavior tests own regression proof for typed error-code contracts. Since both `EngineRunErrorCode` (`StrEnum`) and `RunnerSpecificErrorCode` (`str` subclass) can compare equal to raw strings, direct string equality does not prove the field stayed typed.
- Fix direction:
  - Update affected Agent tests to assert the concrete typed code first.
  - For `EngineRunErrorCode`, use enum identity or `isinstance` plus `serialize_engine_error_code(...)`.
  - For `RunnerSpecificErrorCode`, assert `isinstance(..., RunnerSpecificErrorCode)`, source where relevant, and serialized value.
  - Extend weak-typing guard only if it can target these high-value assertions without brittle broad scans.
- Validation required: focused Agent tests, weak-typing guard, S3 required Engine matrix, pyright, `git diff --check`.

## Rejected / Deferred

- None.

## Residual Risk

- S3 intentional string-only constructor break remains accepted.
- Provider-specific wrapper source remains internal and serialized to durable text at Host boundary.
