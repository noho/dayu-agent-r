# Controller Adjudication — S7/F07 Code Review

## Scope

- Work unit: `WU-CLI-CONFORMANCE-F01-F07`
- Gate: S7/F07 implementation code review
- Entry HEAD: `b8f87e3b`
- Reviewer artifacts:
  - `docs/reviews/wu-cli-conformance-f01-f07-s7-code-review-mimo.md`
  - `docs/reviews/wu-cli-conformance-f01-f07-s7-code-review-ds.md`
- Frozen oracle/scenario registry is outside this fix loop and remains byte-identical.

## Finding-by-finding adjudication

| ID | Source | Disposition | Direct evidence and required action |
|---|---|---|---|
| M-001 | MiMo | `rejected-with-reason` | `CompactMaterialSection` has no `VNext` suffix and is not the deleted `ConversationCompactLabelSectionVNext` input/output label contract. No active compatibility alias exists. Renaming an unrelated internal material enum would expand scope. |
| M-002 | MiMo | `rejected-with-reason` | The artifact itself confirms duplicate source labels are rejected by Context Governance. There is no silent deduplication path to fix. |
| M-003 | MiMo | `rejected-with-reason` | Direct runtime construction shows dataclass exception arguments are populated: `_CompactorProposalExecutionError(...).args` contains all four typed fields and `_CompactorProposalCancelledError(None).args == (None,)`. Callers consume typed fields. This is not an observed correctness defect. |
| M-004 | MiMo | `rejected-with-reason` | `LlmContextCompactor.compact()` is the documented single-attempt convenience boundary. Operation retries use `run_compaction_operation` and pass the operation/attempt identities explicitly. Adding a second attempt owner to the convenience API would duplicate lifecycle semantics. |
| M-005 | MiMo | `rejected-with-reason` | String-prefixed `ValueError` classification is local to one strict parser module and currently closed by owner tests. A typed exception refactor is maintainability work without evidence of a current conformance failure; it is outside this atomic repair. |
| M-006 | MiMo | `rejected-with-reason` | The final utils diff is a fresh-v2 consumer migration, not unexplained formatting. The implementation ledger records the correction and both active smoke consumers require the semantic rewrite. |
| M-R1 | MiMo residual test-density risk | `accepted-in-part` | The reduced operation test file no longer proves several plan §9.8 defensive paths at the operation owner. Add fresh-v2 tests for redacted feedback, cancellation between attempts, accepted-result manifest/response-identity guards, and a later-pass failure. Do not restore v1 fakes or compatibility fixtures. Diagnostics-only validity remains an accept-barrier test independent of payload size; no redundant large-diagnostic operation fake is required. |
| DS-1 | DeepSeek | `accepted-in-part` | Same direct test inventory as M-R1. Restore only behavior required by accepted plan §9.8 using the fresh v2 contract: secret-safe repair feedback, mid-retry cancellation, manifest/response identity fail-closed, and multi-pass later-pass failure. Existing root duplicate/repair tests already cover content-divergent multi-pass aggregation. |
| DS-2 | DeepSeek | `rejected-with-reason` | Reviewer explicitly states no runtime impact and recommends no modification. `git diff -w` isolates the two required serializer changes (`intent_type` and `reason` are now strings); full ruff/pyright/round-trip tests passed. This is not a conformance finding. |
| DS-3 | DeepSeek | `rejected-with-reason` | Accepted plan §9.3 and design §24.3 explicitly freeze `CompactForwardIntentV2.intent_type: str` and `CompactReferenceContinuityV2.reason: str`; only forward-intent status and explicit-drop reason are closed enums. Reintroducing old enums would violate the accepted fresh contract. |
| DS-4 | DeepSeek | `rejected-with-reason` | Accepted plan §9.3 and design §24.3 explicitly freeze `CompactAnswerAnchorV2` as `title + detail + source_labels`. Restoring v1 `anchor_items` would be an unauthorized oracle/design change. |
| DS-O1 | DeepSeek open question | `closed-by-design` | Free-text `intent_type`/`reason` is explicit in accepted plan §9.3 and `docs/host/design.md`; downstream Memory types use the same string contract. |
| DS-O2 | DeepSeek open question | `closed-by-design` | The flattened answer anchor shape is explicit in accepted plan §9.3 and design §24.3. No implementation agent may re-decide it. |
| DS-O3 | DeepSeek open question | `closed-by-evidence` | Final `-w` numstat differs from ordinary numstat by four lines; the remaining large delta is the required removal of old schema readers and construction of strict-v2 candidates, recorded with hashes in the implementation artifact. |
| C-001 | Controller | `accepted-medium` | A duplicate JSON key is copied raw into `json_path` by `_strict_object_pairs`/`_parser_validation_report`; `_bounded_issue_message` redacts only `message`. A key such as `api_key=sk-secret-123` therefore reaches LLM-facing repair feedback unredacted, violating plan §9.5. Fix at the strict LLM-output/feedback owner and add a secret-bearing duplicate-key regression test; do not expose raw keys through paths or add a loose fallback. |
| C-002 | Controller | `accepted-low` | `docs/host/design.md` says Context Governance enforces item-char and total-char caps, and the implementation artifact claims count/item/section/total coverage for diagnostics. Actual `MemoryProjectionPolicy` owns summary char cap plus per-section item-count and aggregate-size caps; diagnostics have no Memory cap. Correct both artifacts to the exact existing policy. Do not expand product policy. |

## Required fix boundary

The fix loop may change only the current S7 allowlist plus these review artifacts. It must:

1. make every repair-feedback field secret-safe at the strict parser/feedback owner, with a deterministic malicious duplicate-key test;
2. add fresh-v2 owner tests for the accepted portion of the operation coverage finding;
3. correct cap wording in `docs/host/design.md` and the S7 implementation artifact;
4. rerun focused tests, the full S7 matrix, full-repository pyright, ruff, modified-production coverage, frozen registry digests, and `git diff --check`;
5. produce `docs/reviews/wu-cli-conformance-f01-f07-s7-code-review-fix-codex.md` and stop at independent re-review without staging, committing, pushing, or changing PR state.

No frozen oracle, scenario, old evidence, README, Engine production, CLI/Service production, branch, or PR operation is authorized in this fix loop.
