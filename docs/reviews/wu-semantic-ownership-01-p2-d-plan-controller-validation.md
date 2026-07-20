# WU-SEMANTIC-OWNERSHIP-01 P2-D plan controller validation

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01`
- Sub WU: `P2-D`
- Gate: plan
- Plan artifact: `docs/reviews/wu-semantic-ownership-01-p2-d-plan-codex.md`

## Motivation Check

The motivation is valid. The targeted public compact smoke fails before dispatch
because compact material construction passes `projection.source.text` as
`RunInputMaterialBlock.readable_source_text`, while the shared accepted-result
projection currently returns `None` when no business source refs are available.
Evidence material requires non-empty readable source text, so the current
projection contract and compact material contract are inconsistent.

This is not a test-only issue. ToolRuntime currently writes accepted evidence
envelopes with empty `source_refs` and `locator_refs` for ordinary accepted tool
results, so production compact material can hit the same path.

## Owner Boundary

- Durable truth owner: `TOOL_RESULT_ACCEPTED` payload, accepted evidence envelope,
  and digest-checked raw tool outcome.
- Shared projection owner: `dayu/host/accepted_result_projection.py`.
- Consumers: compact material, Conversation Memory, RunInputBuilder, Tool Trace
  and Read API.

The plan correctly rejects test fixture changes and compact-material local
fallbacks. The source-unavailable LLM-facing wording must be owned by the shared
accepted-result projection so all consumers derive the same semantics.

## Controller Notes For Review

Reviewers should specifically challenge:

1. Whether changing `AcceptedToolResultSourceProjection.text` from `str | None`
   to `str` is the cleanest owner-boundary fix, or whether it creates an
   avoidable public contract churn.
2. Whether the proposed unavailable wording is business-readable and does not
   imply the tool result is invalid.
3. Whether the validation set covers all direct consumers that currently consume
   `projection.source.text`.
4. Whether tests should prove no internal refs (`event_id`, payload ref, digest,
   cursor, policy, ToolRuntime / Host governance text) enter compact material,
   memory or RunInput.
5. Whether `dayu/host/README.md` needs a minimal contract note after the
   projection contract is tightened.

## Controller Decision

Proceed to plan review. No implementation should start until AgentMiMo /
AgentDS review findings are adjudicated and any accepted plan findings are
fixed and re-reviewed.
