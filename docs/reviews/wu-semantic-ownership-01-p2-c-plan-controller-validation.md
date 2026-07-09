# WU-SEMANTIC-OWNERSHIP-01 P2-C plan controller validation

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01`
- Sub WU: `P2-C`
- Gate: plan controller validation
- Plan artifact: `docs/reviews/wu-semantic-ownership-01-p2-c-plan-codex.md`
- Design truth:
  - `docs/host/design.md`
  - `docs/engine/design.md`
- Control truth: `docs/host/issues-implementation-control.md`

## First-principles judgment

The motivation is valid and not overstated.

`fallback_prompt` and `continuation_prompt` are LLM-facing policy text. The current code has two sources for the same ordinary Run default prompt semantics:

- Engine `AgentPolicy` defines prompt defaults in `dayu/engine/contracts/agent_policy.py`.
- Config `execution_profiles.json` defines ordinary `agent_policy.fallback_prompt` and `agent_policy.continuation_prompt`.

The fallback prompt strings differ. This creates a real semantic ownership problem: direct Engine callers or tests can omit prompt fields and get Engine-owned text, bypassing the execution profile config source of truth.

## Owner boundary

- Default producer:
  - ordinary Run defaults: execution profile `agent_policy`
  - compactor policy: compactor scene manifest required `agent_policy`
- Validation:
  - ConfigLoader / scene preparation / Service assembly validate the config or scene shape.
  - Engine `AgentPolicy` validates complete typed values only.
- Freeze / persistence:
  - Host opener baseline, per-run effective config, and execution config projection carry complete `AgentPolicy`.
- LLM-facing projection:
  - Engine appends the already supplied policy prompt as a user message during fallback / continuation; it does not generate default prompt text.

## Plan quality

Accepted.

The plan chooses the correct root fix: remove Engine prompt text defaults instead of copying config text into Engine defaults. It keeps non-text defaults (`fallback_mode`, `max_consecutive_failed_tool_batches`) out of scope because the accepted finding is about LLM-facing prompt text ownership.

The plan correctly rejects splitting into multiple slices: making `AgentPolicy.fallback_prompt` / `continuation_prompt` required must be coordinated with production call sites, test fixtures, and docs in one implementation pass to keep pyright and tests meaningful.

## Required implementation guardrails

- Do not replace Engine defaults with the config default strings.
- Do not add compatibility wrappers, aliases, or production default helpers.
- Every production `AgentPolicy(...)` constructor must pass `fallback_prompt=` and `continuation_prompt=`.
- Test helpers may provide explicit fixture prompt text, but must remain test-local and must not be presented as Engine defaults.
- Negative tests for missing prompts should expect constructor `TypeError`; blank prompt tests should still expect `ValueError`.
- README checks must follow AGENTS.md triggers for `dayu/engine/`, `dayu/config/`, and `tests/`.

## Validation

Plan gate only changed artifact text. AgentCodex reported:

```text
git diff --check
pass
```

Controller independently checked the plan content and direct code evidence. No implementation tests were required for this plan gate.

## Controller decision

Plan is ready for dual plan review.

Next gate:

- P2-C plan review by AgentMiMo and AgentDS.
