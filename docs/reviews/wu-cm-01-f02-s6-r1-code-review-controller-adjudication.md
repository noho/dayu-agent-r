# Controller Adjudication — WU-CM-01-F02-S6-R1 Code Review

## Scope

- Work unit: `WU-CM-01-F02-S6-R1`
- Gate: code review / controller closure
- Implementation artifact: `docs/reviews/wu-cm-01-f02-s6-r1-implementation-codex.md`
- MiMo review artifact: `docs/reviews/wu-cm-01-f02-s6-r1-code-review-mimo.md`
- DS review artifact: `docs/reviews/wu-cm-01-f02-s6-r1-code-review-ds.md`

## Review Verdicts

- AgentMiMo: PASS. No substantive findings. All 9 required review points passed.
- AgentDS: PASS. No medium-or-higher finding. One low-severity observation about partial constant extraction in tests is explicitly non-defective and outside this rescope.

## Controller Decision

Accepted.

The implementation closes residual `WU-CM-01-F02-S6-R1` because the runtime LLM-facing compactor material now projects:

```json
{
  "instruction": {
    "output_schema_name": "conversation_compact_output_v1",
    "compact_goal": "roll_forward_session_memory"
  }
}
```

instead of exposing the internal Python type name `ConversationCompactOutputVNext`.

Direct closure basis:

- `CONVERSATION_COMPACT_OUTPUT_SCHEMA_NAME_VNEXT` now derives from `CONVERSATION_COMPACT_OUTPUT_SCHEMA_VERSION_VNEXT`, avoiding duplicate literals.
- `CompactInstructionVNext` still strictly validates `output_schema_name` and `compact_goal`.
- `to_json()` field names remain unchanged.
- Output parser, accept barrier, durable schema, public Host API, and compact output schema version remain unchanged.
- Contract, LLM compactor, and public fake compactor tests validate final runtime material JSON, not only prompt template text.
- Prompt and design text are aligned with LLM-facing semantics and no longer require the model to understand the old internal output type name.

## Accepted Findings

None.

## Closed Residual Risk

`WU-CM-01-F02-S6-R1` is closed by implementation plus two independent PASS reviews. The active residual table should remove this item and retain this artifact as closure evidence.

## Remaining Risks

- Optional real-provider compact smoke remains environment-dependent and is owned by WU-CM-01-F01 Slice 7 public smoke closeout.
- Internal Python names such as `ConversationCompactOutputVNext` remain valid in production code, tests, and developer documentation. This is not a defect because the closed risk only covered LLM-facing projection.
