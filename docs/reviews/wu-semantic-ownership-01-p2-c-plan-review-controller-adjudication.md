# WU-SEMANTIC-OWNERSHIP-01 P2-C plan review controller adjudication

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01`
- Sub WU: `P2-C`
- Gate: plan review controller adjudication
- Plan artifact: `docs/reviews/wu-semantic-ownership-01-p2-c-plan-codex.md`
- Controller validation: `docs/reviews/wu-semantic-ownership-01-p2-c-plan-controller-validation.md`
- Review artifacts:
  - `docs/reviews/wu-semantic-ownership-01-p2-c-plan-review-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-p2-c-plan-review-ds.md`

## Review results

AgentMiMo conclusion: `pass`.

- F01 LOW: `AgentPolicyDefaults` naming / docstring ambiguity.
- F02 LOW: `test_contract_fields_are_explicit` path not explicit.

AgentDS conclusion: `pass-with-risks`.

- F-1 MEDIUM: `AgentPolicyDefaults` / `code_default` rename must be a hard plan requirement, not implementation discretion.
- F-2 LOW: validation scan omits `utils/`.
- F-3 HIGH: `tests/host/public_smoke_support.py` omitted as a named migration target.
- F-4 INFO: config prompt text difference correctly scoped; no action.
- F-5 MEDIUM: `test_contract_fields_are_explicit` migration spec insufficiently concrete.
- F-6 LOW: focused validation command omits `tests/engine/test_agent_phase2.py`.

## Controller adjudication

Accepted for plan fix:

- `P2C-PLAN-F01`: `AgentPolicyDefaults` / `code_default` ambiguity. The plan must make runtime assembly naming/docstring cleanup mandatory and specify before/after naming. This is not merely readability: leaving `code_default` in a prompt-default ownership fix risks reintroducing a perceived code-owned prompt default.
- `P2C-PLAN-F02`: Explicitly list `tests/host/public_smoke_support.py` as a migration target and require fixture prompt values to be explicit and not exported as a shared default source.
- `P2C-PLAN-F03`: Make `test_contract_fields_are_explicit` migration concrete with file path and expected test split / rename: missing prompt `TypeError`, explicit prompt acceptance, and non-text default assertions remaining separate or explicit.

Accepted as implementation validation guardrails, no separate plan-fix blocker:

- `P2C-PLAN-G01`: Extend post-scan acceptance to include `utils/` AgentPolicy constructors.
- `P2C-PLAN-G02`: Add `tests/engine/test_agent_phase2.py` to focused validation.

Rejected / no action:

- DS F-4 is informational and correctly confirms config text remains the source of truth. No plan change needed.

## Required plan-fix scope

AgentCodex must update only the P2-C plan artifact. Do not edit production code, tests, README, or implementation files in the plan-fix gate.

The fixed plan must remain code-generation-ready and must preserve the key controller requirement: Engine prompt text defaults are removed rather than synchronized with config text.

## Next gate

P2-C plan fix by AgentCodex, then plan re-review by AgentMiMo and AgentDS.
