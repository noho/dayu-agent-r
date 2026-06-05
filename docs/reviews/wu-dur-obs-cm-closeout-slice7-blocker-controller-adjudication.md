# WU-CM-01-F01 Slice 7 Blocker Controller Adjudication

## Gate

- gate: implementation blocker adjudication
- work unit: WU-CM-01-F01 Conversation Memory Smoke Correctness Closeout
- slice: Slice 7 Public Smoke Correctness Closeout
- branch: `phaseflow/wu-dur-obs-cm-closeout`
- status: blocker-accepted

## Inputs

- blocker artifact: `docs/reviews/wu-dur-obs-cm-closeout-slice7-blocker-codex.md`
- control residual: `WU-CM-01-F02-S6-R1`
- plan source: `docs/host/wu-dur-obs-cm-closeout-plan.md` Slice 7
- design source: `docs/host/design.md`

## Adjudication

Controller accepts the blocker.

The blocker motivation is valid and not overestimated. Slice 7 is supposed to validate the final public smoke / LLM-facing closeout path. The active residual `WU-CM-01-F02-S6-R1` proves that the final compactor request still includes:

```text
instruction.output_schema_name = "ConversationCompactOutputVNext"
```

That value is a Python / internal schema type name. It is projected into the runtime compactor material JSON through `CompactInstructionVNext.to_json()` and `ConversationCompactInputVNext.to_json()`, not merely left in an implementation comment or review document. Therefore it is inside the LLM-facing surface governed by AGENTS.md.

Slice 7 allowed files only cover tests, support helpers, and utility smoke scripts. Adding assertions there would only make the smoke fail; it would not remove the internal type name from the actual compactor request. Fixing the root cause requires a production compact instruction contract change, likely in `dayu/host/compaction.py` and focused tests that validate the final LLM-facing compactor request no longer contains the internal type name.

## Decision

Do not widen Slice 7 implementation directly.

Next gate must be a production compact instruction contract rescope / plan-fix before Slice 7 can be retried. The rescope must decide the external value for `instruction.output_schema_name` or remove the field from LLM-facing material JSON while preserving the compact output schema and parser behavior.

## Validation

AgentCodex ran:

- `source .venv/bin/activate && python utils/smoke_host_public_conversation_memory.py --help`
- `source .venv/bin/activate && python utils/smoke_host_public_diagnostics.py --help`
- `source .venv/bin/activate && python utils/smoke_host_public_conversation_memory_scenarios.py --help`
- `source .venv/bin/activate && python utils/smoke_host_public_multiturn.py --help`
- `source .venv/bin/activate && pyright`
- `git diff --check`

Controller reviewed the blocker artifact and accepts the result: blocker is real, scoped, and directly tied to production LLM-facing material.

