# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-C Plan Review Controller Adjudication

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 / Round3 R3-C`
- Gate: plan review
- Plan artifact: `docs/host/wu-semantic-ownership-01-round3-r3-c-fins-storage-atomicity-plan.md`
- Goal confirmation artifact: `docs/reviews/wu-semantic-ownership-01-round3-r3-c-goal-confirmation.md`
- Review artifacts:
  - `docs/reviews/wu-semantic-ownership-01-round3-r3-c-plan-review-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-round3-r3-c-plan-review-ds.md`

## Review Summary

Both reviewers returned `pass-with-risks` and confirmed the plan correctly excludes tool-security implementation from R3-C.

| Reviewer | Conclusion | Findings | Blocking questions |
| --- | --- | ---: | ---: |
| AgentMiMo | `pass-with-risks` | 5 | 0 |
| AgentDS | `pass-with-risks` | 6 | 0 |

The plan is directionally accepted but must receive a plan-fix pass before implementation. The accepted findings are specification-completeness issues; no code implementation is authorized until they are fixed and re-reviewed.

## Tool-Security Scope Decision

Accepted: R3-C must not implement tool-security work.

The following remain explicitly assigned to a later dedicated tool-security / remote-egress WU:

- upload user-file allowlist / explicit file authority / symlink-safe upload source policy;
- URL / TLS / redirect / SSRF provenance policy;
- remote download byte-budget policy;
- LLM-facing upload/download security schema or prompt changes.

Both reviewers verified the current plan keeps these out of implementation. The plan fix must preserve this exclusion.

## Accepted Plan Findings

### R3-C-PF-01 — S2 caller-batch contract for `commit_cn_filing_source_document`

- Source: AgentDS finding 1.
- Decision: accepted.
- Reason: Direct code evidence shows `commit_cn_filing_source_document()` writes source meta and processed reprocess marker through repository methods. If called without an outer active shared batch, those methods can auto-batch independently, defeating S2's single-document atomicity.
- Required plan fix: state that S2 must execute `commit_cn_filing_source_document()` only inside the caller-owned document batch, or split it into a clearly named final-meta staging helper. It must not create a second commit owner. Verification must prove reset -> ack -> blob -> final meta -> processed marker all occur under the same active batch.

### R3-C-PF-02 — S2 token lifecycle and commit-failure rollback rule

- Source: AgentMiMo finding 001.
- Decision: accepted.
- Reason: Plan says commit failure relies on storage all-or-nothing but does not explicitly forbid caller-side rollback after `commit_batch()` has consumed the token.
- Required plan fix: specify that callers rollback only operation exceptions before commit. After `commit_batch()` is called, success or failure is owned by storage; caller must propagate the storage exception and must not attempt invalid-token rollback.

### R3-C-PF-03 — S2 active-batch exception/cancellation pattern

- Source: AgentMiMo finding 002.
- Decision: accepted.
- Reason: The invariant "no yield/await inside batch" is correct but not enough as implementation guidance; accidental cancellation inside a batch must still be safe.
- Required plan fix: specify the batch scope pattern: `token` remains owned by the caller until commit begins; `try/finally` rolls back any uncommitted active token on operation exception/cancellation; no `yield`/`await` while token is active; tests must inject an exception/cancellation inside the batch section and assert rollback.

### R3-C-PF-04 — S1 `SWAPPED_TARGET` recovery semantic reversal

- Source: AgentMiMo finding 003.
- Decision: accepted.
- Reason: Current recovery treats `SWAPPED_TARGET` as committed when backup and target coexist. The plan reverses that meaning but does not explicitly say this is a required behavior change.
- Required plan fix: explicitly state that recovery for `SWAPPED_TARGET` before `COMMITTED` must delete the new target and restore backup, contrary to current behavior. Add a required test for crash between swap and `COMMITTED`.

### R3-C-PF-05 — S1 dual commit/rollback error reporting

- Source: AgentDS finding 2.
- Decision: accepted.
- Reason: "Report both errors" is under-specified for Python exception propagation and test assertions.
- Required plan fix: specify the propagation shape for commit failure plus rollback failure, including which error is primary, where the rollback error is preserved, and that journal/backup evidence remains for recovery. Tests must assert both errors are inspectable.

### R3-C-PF-06 — S2 `DownloadedReportAsset` impact scan

- Source: AgentDS finding 3.
- Decision: accepted.
- Reason: `pdf_path -> pdf_bytes` affects a shared dataclass and all its consumers, not only the workflow files initially listed.
- Required plan fix: identify the type owner (`dayu/fins/pipelines/cn_download_models.py`) and require full attribute/reference scans for `.pdf_path`, constructor usages, fixtures, and type annotations across `dayu/fins` and `tests`.

### R3-C-PF-07 — S1 per-phase failure injection strategy

- Source: AgentDS finding 4.
- Decision: accepted.
- Reason: The plan requires phase failure tests but does not tell the implementation agent how to avoid brittle call-count mocks.
- Required plan fix: specify preferred injection seams. Use owner-level controlled helpers or journal/rename monkeypatches with explicit filesystem state assertions; avoid tests that pass only because a call-count mock happened to fire.

### R3-C-PF-08 — S3 snapshot field/error contract

- Source: AgentMiMo finding 004 and AgentDS open question 3.
- Decision: accepted.
- Reason: `WaitAdapterSnapshot.created_at` and invalid resume-token/timestamp handling must be Host-owned and typed, or Service may reintroduce durable parsing fallback.
- Required plan fix: specify `created_at` is a timezone-aware `datetime` produced by Host from existing durable timestamp parsing; invalid durable timestamp or resume token must fail closed at Host snapshot projection with a concrete existing or new Host-owned error path.

### R3-C-PF-09 — S3 sequencing and documentation sync

- Source: AgentMiMo finding 005 and AgentDS finding 6.
- Decision: accepted.
- Reason: S3 shares README/doc sync and `tests/fins/test_fins_storage_provider.py` import-boundary cleanup with earlier slices. "Recommended after S2" is too weak for the final documentation sync.
- Required plan fix: state S1 -> S2 -> S3 is mandatory for implementation. README/doc sync must occur only after all three production slices have landed, and S1/S2 must not leave permanent TODO-style compatibility behavior for S3.

### R3-C-PF-10 — S1 journal directory sync and `DoclingUploadService` batch context clarity

- Source: AgentDS open questions 1 and 2.
- Decision: accepted as low-risk plan clarification.
- Reason: Both are implementation-affecting details with direct owner impact.
- Required plan fix: specify journal writes use the existing atomic JSON + directory sync pattern, including `COMMITTED` writes. Clarify how `_acknowledge_source_before_blob_write()` behaves when called inside an explicit batch during create/update.

## Rejected Or No-Plan-Fix Findings

### DS finding 5 — old-format journal migration

- Decision: rejected as a required plan fix.
- Reason: Reviewer classifies it as low-probability and self-resolving; the new recovery tests for `SWAPPED_TARGET` and commit/rollback phases cover the current implementation direction. Implementation artifact may note deployment assumes no active in-process batch, but plan need not add migration work.

## Controller Decision

Plan review is not fully closed. AgentCodex must perform a plan fix before implementation.

Next gate: plan fix by AgentCodex, then MiMo/DS plan re-review.
