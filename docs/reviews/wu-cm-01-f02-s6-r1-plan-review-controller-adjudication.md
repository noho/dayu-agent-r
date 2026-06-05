# WU-CM-01-F02-S6-R1 Plan Review Controller Adjudication

## Gate

- gate: plan review adjudication
- work unit: `WU-CM-01-F02-S6-R1`
- plan artifact: `docs/host/wu-cm-01-f02-s6-r1-compact-instruction-rescope-plan.md`
- branch: `phaseflow/wu-dur-obs-cm-closeout`
- status: accepted-after-plan-fix

## Inputs

- AgentMiMo plan review: `docs/reviews/wu-cm-01-f02-s6-r1-plan-review-mimo.md`
- AgentDS plan review: `docs/reviews/wu-cm-01-f02-s6-r1-plan-review-ds.md`
- Slice 7 blocker artifact: `docs/reviews/wu-dur-obs-cm-closeout-slice7-blocker-codex.md`
- Slice 7 blocker controller adjudication: `docs/reviews/wu-dur-obs-cm-closeout-slice7-blocker-controller-adjudication.md`

## Review Results

AgentMiMo verdict: pass-with-risks. Three low findings.

AgentDS verdict: pass. Three low findings.

No blocking open questions. Both reviews agree the plan correctly identifies the root cause as LLM-facing runtime compact material JSON, not prompt template text, and that replacing the projected internal type-name literal is the minimal maintainable fix.

## Findings Adjudication

- Accepted and fixed in plan: constant definition must be code-generation-ready. Controller chooses `CONVERSATION_COMPACT_OUTPUT_SCHEMA_NAME_VNEXT = CONVERSATION_COMPACT_OUTPUT_SCHEMA_VERSION_VNEXT` to avoid duplicate identical literals while preserving separate field semantics through docstrings.
- Accepted and fixed in plan: prompt clarification must specify exact wording for `instruction.output_schema_name` and `instruction.compact_goal`.
- Accepted and fixed in plan: implementation must inspect `__all__` and verify no external production use depends on the old literal.
- Accepted and fixed in plan: design/code naming mismatch for `CompactInstruction` / `CompactInstructionVNext` is explicitly non-goal; implementation must not rename the concept while fixing this residual.

No re-review is required because all accepted changes are low-risk clarifications to make the already-passing plan code-generation-ready; they do not alter the root approach, allowed module boundary, or validation matrix.

## Decision

Plan accepted. Next gate is implementation for `WU-CM-01-F02-S6-R1` compact instruction literal rescope.

Implementation must not change compact output schema fields, parser acceptance semantics, durable event/artifact schemas, or public Host APIs. It must close the active residual only after tests prove the final LLM-facing runtime compactor material no longer contains `ConversationCompactOutputVNext`.

