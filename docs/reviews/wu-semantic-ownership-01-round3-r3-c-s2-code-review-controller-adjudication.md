# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-C S2 Code Review Controller Adjudication

## Scope

- Slice: S2 Single-Document Ingestion Atomicity And Temp-Less CN/HK Assets
- Inputs:
  - `docs/reviews/wu-semantic-ownership-01-round3-r3-c-s2-code-review-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-round3-r3-c-s2-code-review-ds.md`
- Controller: AgentCodex
- Status: fix-required

## Review Merge

| Reviewer | Status | Findings | Controller decision |
|---|---:|---:|---|
| AgentMiMo | pass-with-risks | 1 | Accept F01 |
| AgentDS | pass | 0 | Accept pass |

## Accepted Findings

### S2-F01 CN commit failure test should assert storage absence

- Severity: low
- Semantic fact: commit failure belongs to storage-owned `commit_batch` recovery; caller must not perform a second rollback and must not expose a completed filing.
- Correct owner: S2 caller-side commit-failure test matrix.
- Drift location: `tests/fins/test_cn_download_workflow.py::test_cn_commit_failure_does_not_trigger_caller_rollback_or_success`
- Direct evidence: upload and generic download commit-failure tests already assert `FileNotFoundError`; CN commit-failure test asserted no caller rollback and no success event but did not assert source absence.
- Decision: accept as a test-contract completeness finding. It is not a production defect because S1 storage tests and S2 controller validation already cover storage rollback behavior, but the S2 matrix should be symmetric across all three callers.
- Required fix: add `pytest.raises(FileNotFoundError)` around `source_repository.get_source_meta("600519", "fil2024", SourceKind.FILING)`.
- Verification: rerun the focused CN workflow test, affected fins tests, full `tests/fins`, pyright, and diff checks.

## Rejected Findings

None.

## Tool-Security Boundary

No tool-security finding is accepted or implemented in S2. The S2 code keeps URL, TLS, redirect, SSRF, allowlist, remote byte-budget, prompt, and tool-schema policies unchanged and deferred.

