# Controller Adjudication: Host Public Conversation Memory Scenario Smoke Plan

- Gate: plan review / plan fix / plan re-review
- Work unit: Host public conversation memory scenario smoke
- Branch: `feat/phase-12-5-conversation-memory-optimize`
- Date: 2026-05-26

## Reviewed Artifacts

- Plan: `docs/reviews/gateflow-plan-public-memory-scenario-smoke-20260526.md`
- MiMo plan review: `docs/reviews/gateflow-plan-review-public-memory-scenario-smoke-mimo-20260526.md`
- DS plan review: `docs/reviews/gateflow-plan-review-public-memory-scenario-smoke-ds-20260526.md`
- Plan fix: `docs/reviews/gateflow-plan-fix-public-memory-scenario-smoke-codex-20260526.md`
- MiMo plan re-review: `docs/reviews/gateflow-plan-rereview-public-memory-scenario-smoke-mimo-20260526.md`
- DS plan re-review: `docs/reviews/gateflow-plan-rereview-public-memory-scenario-smoke-ds-20260526.md`

## Controller Decision

Plan review verdicts were both PASS. Controller nevertheless accepted DS N1-N5 and MiMo F-01-F-05 as plan-hardening items before implementation, because N3 left too much long-suite prompt design to the implementation worker.

Plan fix updated the plan to specify:

- `--suite all` orchestration as one `open_host` lifecycle and one session.
- deterministic C2 long-input generation.
- fixed L01-L25 long-suite prompt specs.
- `calls_by_key` as observability summary.
- data-driven assertion helpers instead of label-based giant branching.
- MiMo clarifications for schema/naming rationale, E pressure source, `--long-rounds` boundary tests, and README renumbering.

MiMo and DS re-review both PASS. Final status mapping: DS N1-N5 resolved; MiMo F-01-F-05 resolved. No blocking open question remains.

## Residual Risks

- Public smoke cannot directly read or assert internal `pinned_state`, episode count, compact material, EventLog, or memory table contents. These remain covered by Host memory / compaction tests and are only behaviorally proxied by this smoke.
- LLM output format remains probabilistic. The plan mitigates this by hard/soft assertion split and by using deterministic markers for core final checks.
- Long suite has provider runtime cost and rate-limit risk. It is explicit opt-in via `--suite long` or `--suite all`; default suite remains `core`.

## Gate Status

Accepted plan gate is ready for local checkpoint commit. Implementation must follow the fixed plan and keep `utils/smoke_host_public_conversation_memory.py` semantically unchanged.
