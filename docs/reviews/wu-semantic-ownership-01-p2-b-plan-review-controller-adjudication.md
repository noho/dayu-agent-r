# WU-SEMANTIC-OWNERSHIP-01 P2-B Plan Review Controller Adjudication

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01`
- Sub WU: `P2-B`
- Gate: plan review adjudication/fix
- Plan artifact: `docs/host/wu-semantic-ownership-01-p2-b-plan.md`
- Controller validation: `docs/reviews/wu-semantic-ownership-01-p2-b-plan-controller-validation.md`
- Review artifacts:
  - `docs/reviews/wu-semantic-ownership-01-p2-b-plan-review-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-p2-b-plan-review-ds.md`

## Review Verdicts

- AgentMiMo: `pass-with-findings`
- AgentDS: `pass-with-findings`

Controller accepts the actionable plan underspecification findings and has patched the P2-B plan before re-review.

## Accepted Findings And Fixes

| Finding | Source | Controller decision | Plan fix |
|---|---|---|---|
| typed field落点不明确，可能混淆 read model field 与 durable schema | MiMo F1 / DS F1 | Accepted | Plan now says typed field, if used, should land in projection-internal view or RunInputBuilder internal event view; it explicitly excludes `ConversationMemorySnapshotVNext` / `SelectedRecentWindowItem` schema changes and preserves `TOOL_RESULT_ACCEPTED` owner boundary. |
| relative import resolution algorithm underspecified | MiMo F2 / DS F2 | Accepted | Plan now defines deterministic package-relative resolution from scanned file path and package root, including `node.module is None`, parent traversal, and unresolvable failure behavior. |
| source scan does not cover `test_memory_projection.py` | MiMo F3 | Accepted | Plan now includes `tests/host/test_memory_projection.py` in sentinel source scan and S2 negative scan. |
| cross-path equivalence assertion underspecified | MiMo F4 / DS F6 | Accepted | Plan now requires a real durable store case with terminal artifact descriptor and exact string equality plus explicit no-ref/no-digest assertions. |
| one-slice strategy can let MiMo 08 stop condition block MiMo 09/12 | DS F4 | Accepted | Plan now uses two implementation slices: S1 import-boundary + snapshot fixture hardening; S2 terminal answer continuity projection contract. |
| allowed files missing `dayu/host/terminal_payload.py` | DS F5 | Accepted | Plan now allows `dayu/host/terminal_payload.py` only if resolver/helper typed material contract requires it. |
| business test body vs digest invariant boundary unclear | DS F3 | Accepted | Plan now defines factory/internal sentinel boundary and source-scan expectations for `ConversationMemorySnapshotVNext(` and `snapshot_digest="pending"`. |

## Non-blocking Notes

- The plan still preserves P2-B non-goals: no Conversation Memory redesign, no compact schema redesign, no Engine contract change, no forced full final answer copy into hot EventLog payload.
- Design truth sync remains required before S2 production code changes.
- S1 can proceed independently if S2 hits a design stop condition.

## Validation

- `git diff --check`
  - Result: passed

No production tests or pyright are required for this plan-fix-only gate.

## Next Gate

Dispatch AgentMiMo and AgentDS plan re-review. Re-review must confirm all accepted plan-review findings are closed and no new blocking plan issue remains.
