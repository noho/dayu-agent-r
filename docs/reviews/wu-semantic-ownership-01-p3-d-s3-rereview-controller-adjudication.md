# WU-SEMANTIC-OWNERSHIP-01 / P3-D / S3 Re-Review Controller Adjudication

## Inputs

- MiMo re-review: `docs/reviews/wu-semantic-ownership-01-p3-d-s3-rereview-mimo.md`
- DS re-review: `docs/reviews/wu-semantic-ownership-01-p3-d-s3-rereview-ds.md`
- Fix artifact: `docs/reviews/wu-semantic-ownership-01-p3-d-s3-fix-codex.md`
- Controller fix validation: `docs/reviews/wu-semantic-ownership-01-p3-d-s3-fix-controller-validation.md`

## Decision

- `P3-D-S3-CR-F01`: fixed.
- New material findings: none.
- Gate decision: S3 re-review pass; ready for accepted slice commit.

## Evidence

- Agent tests no longer directly compare `.error_code` to string literals.
- Engine-owned code assertions use enum identity and `serialize_engine_error_code(...)`.
- Runner-specific code assertions check `RunnerSpecificErrorCode`, source enum identity, and serialized value.
- Weak-typing guard uses AST against `tests/engine/test_agent_phase2.py` to reject direct `.error_code == "..."` and `.error_code != "..."` regressions without scanning Host durable text paths.
- Fix changed only tests and the fix artifact; no production behavior, README/doc, LLM-facing path, or Host projection was changed.

## Residual Risk

- S3 intentional string-only constructor break remains accepted.
- Provider-specific wrapper source remains internal to Engine and is serialized to durable/public text at Host boundary.
- The direct-comparison guard currently targets `tests/engine/test_agent_phase2.py`, the file containing the accepted finding. If future Engine tests introduce typed error-code direct string comparisons elsewhere, the guard scope should be expanded with the same AST precision.
