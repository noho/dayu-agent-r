# WU-SEMANTIC-OWNERSHIP-01 P1-A Plan Re-review Controller Adjudication

## Metadata

- Work unit: `WU-SEMANTIC-OWNERSHIP-01`
- Sub WU: `P1-A`
- Gate: plan re-review
- P0-A accepted commit: `6731b451`
- P0-B accepted commit: `750af328`
- Plan artifact: `docs/host/wu-semantic-ownership-01-p1-a-plan.md`
- Plan fix artifact: `docs/reviews/wu-semantic-ownership-01-p1-a-plan-fix-codex.md`
- Plan review controller adjudication: `docs/reviews/wu-semantic-ownership-01-p1-a-plan-review-controller-adjudication.md`
- Re-review artifacts:
  - `docs/reviews/plan-review-20260709-p1-a-rereview-mimo.md`
  - `docs/reviews/plan-review-20260709-p1-a-rereview-ds.md`
- Decision date: 2026-07-09

## Decision

`accepted-plan`

Both re-reviewers concluded `pass`. Controller accepts that P1A-PLAN-F01 through P1A-PLAN-F07 are closed. P1-A plan is code-generation-ready and may proceed to accepted plan commit, then implementation.

## Closure Summary

| Finding | Controller requirement | Re-review result | Controller decision |
|---|---|---|---|
| P1A-PLAN-F01 | Specify Tool Trace request summary strategy without re-owning query/status/source. | Both reviewers verified the narrow projection-truth plus display-only Tool Trace rendering boundary. | Closed. |
| P1A-PLAN-F02 | Specify Read API PREVIEW vs CANONICAL_FACT boundary and status mapping. | Both reviewers verified canonical `TOOL_RESULT_ACCEPTED` projection dispatch and `AcceptedToolResultStatus` to `HostActivityStatus` mapping. | Closed. |
| P1A-PLAN-F03 | Cover `_readable_source_text_from_refs()` source producer and validation scans. | Both reviewers verified accepted-result source production is replaced by projection helper and grep expectations include source producer paths. | Closed. |
| P1A-PLAN-F04 | Assign unavailable-query fallback ownership to projection helper. | Both reviewers verified `ACCEPTED_EVIDENCE_QUERY_UNAVAILABLE_TEXT` owner and Conversation Memory consumption boundary. | Closed. |
| P1A-PLAN-F05 | Define status mapping and `_tool_result_status()` fate. | Both reviewers verified mapping table, precedence and Tool Trace adapter/deletion boundary. | Closed. |
| P1A-PLAN-F06 | Classify `InitialEvidenceMaterial` / `_evidence_blocks()`. | Both reviewers verified the non-accepted-result boundary and fixture constraint. | Closed. |
| P1A-PLAN-F07 | Expand validation scans. | Both reviewers verified `_readable_source_text_from_refs`, `source_note` and `tool_call_request_atoms` scans and allowed/forbidden match rules. | Closed. |

## Residual Risks

- `governed_error` durable signal naming must be confirmed during S1 implementation from current payload contract. If no existing signal exists, implementation must stop for controller adjudication rather than inventing one.
- Source refs are often empty today; P1-A closes projection ownership and no-leak semantics, not source enrichment.
- Tool Trace result details and argument summaries may retain display-level bounded rendering, but they cannot own accepted query/status/source truth.

All residual risks have implementation-stage owner and do not block accepted plan commit.

## Next Gate

Proceed to P1-A accepted plan commit. After the commit, enter P1-A implementation through AgentCodex, preserving the approved plan slices S1 through S3 and the re-review constraints above.
