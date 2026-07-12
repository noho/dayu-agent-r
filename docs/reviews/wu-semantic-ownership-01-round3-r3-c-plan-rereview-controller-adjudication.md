# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-C Plan Re-Review Controller Adjudication

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 / Round3 R3-C`
- Gate: plan re-review
- Plan artifact: `docs/host/wu-semantic-ownership-01-round3-r3-c-fins-storage-atomicity-plan.md`
- Plan fix artifact: `docs/reviews/wu-semantic-ownership-01-round3-r3-c-plan-fix-codex.md`
- Plan re-review artifacts:
  - `docs/reviews/wu-semantic-ownership-01-round3-r3-c-plan-rereview-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-round3-r3-c-plan-rereview-ds.md`

## Re-Review Summary

Both reviewers passed the fixed plan.

| Reviewer | Conclusion | Fixed findings | Remaining findings | New findings | Blocking questions |
| --- | --- | ---: | ---: | ---: | ---: |
| AgentMiMo | `pass` | 10 | 0 | 0 | 0 |
| AgentDS | `pass` | 10 | 0 | 0 | 0 |

Controller independently accepts the re-review result. The fixed plan closes all ten accepted plan-review findings:

- `R3-C-PF-01`: S2 caller-owned batch contract for `commit_cn_filing_source_document()`.
- `R3-C-PF-02`: S2 token lifecycle handoff at `commit_batch()`.
- `R3-C-PF-03`: S2 active-batch `try/finally`, cancellation, and no-yield pattern.
- `R3-C-PF-04`: S1 `SWAPPED_TARGET` recovery semantic reversal before `COMMITTED`.
- `R3-C-PF-05`: S1 dual commit/rollback exception propagation.
- `R3-C-PF-06`: S2 `DownloadedReportAsset` owner and impact scan.
- `R3-C-PF-07`: S1 per-phase failure injection strategy.
- `R3-C-PF-08`: S3 Host-owned `WaitAdapterSnapshot` field and error contract.
- `R3-C-PF-09`: Mandatory `S1 -> S2 -> S3` implementation order and deferred docs sync.
- `R3-C-PF-10`: S1 journal directory sync and upload acknowledgement explicit-batch behavior.

## Tool-Security Scope Decision

No tool-security work is authorized in R3-C implementation.

The goal confirmation and fixed plan now explicitly defer these four security-oriented items to a later dedicated owner:

- upload allowlist / file authority / symlink-safe upload policy;
- URL / TLS / redirect / SSRF provenance policy;
- remote download byte-budget policy;
- LLM-facing upload/download security schema or prompt changes.

Both re-reviewers verified that these items remain excluded from S1, S2, and S3. Controller accepts that classification. Any implementation path that requires one of these policies must stop and record a deferred tool-security WU item instead of adding local validation, fallback, prompt/schema changes, or compatibility behavior.

## Controller Decision

Status: `accepted-plan`.

R3-C is code-generation-ready with three mandatory sequential implementation slices:

1. S1 Storage Identity, Commit Point, And Local Durability.
2. S2 Single-Document Ingestion Atomicity And Temp-Less CN/HK Assets.
3. S3 Host Adapter Snapshot And Service-Owned Fins Wait Glue.

Implementation must proceed in that order. S2 must not start until S1 production code, tests, validation, and per-slice review are accepted. S3 must not start until S2 production code, tests, validation, and per-slice review are accepted. README and design/current-fact documentation sync happens only after S1, S2, and S3 production/test changes have landed and passed slice review.

Next gate: R3-C S1 implementation by AgentCodex.
