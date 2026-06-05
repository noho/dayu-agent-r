# WU-CM-01-F02-S6-R1 Compact Instruction Contract Rescope Plan

## Gate

- gate: plan
- work unit: `WU-CM-01-F02-S6-R1`
- branch: `phaseflow/wu-dur-obs-cm-closeout`
- design source: `docs/host/design.md`
- control source: `docs/host/issues-implementation-control.md`
- accepted Slice 6 commit: `f6474b0c`
- Slice 7 blocker commit: `d5233aa2`
- artifact path: `docs/host/wu-cm-01-f02-s6-r1-compact-instruction-rescope-plan.md`

## Goal Confirmation

### First-principles judgment

The work unit is valid and not overestimated.

The compactor request is LLM-facing material. Its job is to give a stateless model the business-readable context, citation labels, task goal, and strict output contract needed for one compaction action. Exposing a Python dataclass name in that material does not help the model perform the task; it increases cognitive load, violates the project rule that LLM-facing text must not rely on internal implementation names, and blocks the final public smoke closeout because the final runtime request still contains the internal type name.

The correct fix is production contract rescope, not a smoke-only assertion. Tests can expose the failure, but they cannot remove the value from the actual request.

### Direct evidence

- `dayu/host/compaction.py` defines `CONVERSATION_COMPACT_OUTPUT_SCHEMA_NAME_VNEXT = "ConversationCompactOutputVNext"`.
- `CompactInstructionVNext.output_schema_name` defaults to that constant.
- `CompactInstructionVNext.__post_init__()` requires that exact value.
- `CompactInstructionVNext.to_json()` projects `{"output_schema_name": self.output_schema_name, "compact_goal": self.compact_goal}`.
- `ConversationCompactInputVNext.to_json()` includes `"instruction": self.instruction.to_json()`.
- `dayu/host/llm_compaction.py` renders `request.to_json()` inside `UNTRUSTED_COMPACTION_MATERIAL_JSON_BEGIN/END`, so this value reaches the compactor user prompt.
- `tests/host/test_public_compact_smoke.py` already extracts runtime material JSON from the fake compactor request, proving this is observable on the public opener path.
- `docs/reviews/wu-dur-obs-cm-closeout-slice7-blocker-codex.md` and `docs/reviews/wu-dur-obs-cm-closeout-slice7-blocker-controller-adjudication.md` accepted the blocker as production-scope.
- `docs/host/design.md` section 24.3 still lists `CompactInstruction.output_schema_name: "ConversationCompactOutputVNext"`, so the design truth must be narrowly synchronized before implementation can claim a clean contract.

## Goal

Remove the internal Python type name from LLM-facing compact instruction material by replacing runtime `instruction.output_schema_name` with a business-readable stable literal:

```text
conversation_compact_output_v1
```

The implementation must preserve compact output JSON field names and must not weaken parser or accept-barrier behavior.

## Success Signal

- Runtime compactor material JSON no longer contains `ConversationCompactOutputVNext`.
- Runtime compactor material JSON has:

```json
{
  "instruction": {
    "output_schema_name": "conversation_compact_output_v1",
    "compact_goal": "roll_forward_session_memory"
  }
}
```

- The compactor output schema remains the same strict JSON object with top-level fields `schema_version`, `session_summary`, `evidence_backed_facts`, `answer_anchors`, `forward_intents`, `reference_continuity_items`, and `diagnostics`.
- `parse_conversation_compact_output_vnext()` and `check_conversation_compact_output_vnext()` still reject old schema, unknown labels, stale labels, cross-section labels, missing source labels, and `current_input_anchor` citations.
- Public smoke tests assert the final runtime material JSON is clean, not only the packaged prompt template.
- Active residual `WU-CM-01-F02-S6-R1` is marked closed in the control doc with implementation and validation evidence.

## Non-goals

- Do not rename compact output candidate fields.
- Do not rename `ConversationCompactOutputVNext` as an internal Python dataclass.
- Do not remove or relax `schema_version = "conversation_compact_output_v1"` from output parsing.
- Do not accept legacy compact output schemas.
- Do not loosen source-label validation, current-input-anchor rejection, section boundary checks, item caps, enum checks, or text non-empty checks.
- Do not redesign the whole compactor material contract.
- Do not add compatibility aliases, wrappers, re-exports, or old-value fallback.
- Do not change compact artifact schema, EventLog payload schema, memory projection schema, runner-call manifest schema, or public Host API.
- Do not retry WU-CM-01-F01 Slice 7 in this implementation slice until this residual is closed.
- Do not rename `CompactInstruction` / `CompactInstructionVNext` concepts in design or code as part of this residual. The design/code naming mismatch is pre-existing and outside this narrow LLM-facing literal cleanup; design sync should only update the literal and adjacent meaning.

## Design Alignment

Host design says Context Governance owns compaction orchestration, while RunInputBuilder / material assembly provide LLM-readable material and Host validates the candidate before writing durable compact events. This plan preserves that boundary:

- The production change stays in Host compaction material contract code.
- The output parser remains in `dayu/host/llm_compaction.py`.
- The accept barrier remains in `dayu/host/context_governance.py` and `dayu/host/compaction.py`.
- No Service, UI, Engine, durable storage, or Fins dependency is introduced.

Required design sync:

- Update `docs/host/design.md` section 24.3 so `CompactInstruction.output_schema_name` uses `"conversation_compact_output_v1"` instead of `"ConversationCompactOutputVNext"`.
- Clarify that `output_schema_name` is a business-readable output contract identifier for the current compaction task, not a Python type name and not a business fact.

## Chosen Approach

Use replacement, not removal.

### Decision

Set the production `instruction.output_schema_name` value to `conversation_compact_output_v1`.

### Justification

- It is the minimal root-cause fix: one LLM-facing literal changes from an internal type name to the already-stable output schema identifier.
- It preserves the existing input shape, so prompt templates, fake compactor helpers, and material consumers do not need to infer a missing instruction field.
- It aligns with the current prompt, which already tells the compactor the output `schema_version` must be `conversation_compact_output_v1`.
- It avoids broad contract churn. Removing the field would require deciding whether `instruction` still has enough information, updating prompt wording more broadly, and proving no downstream material consumers depend on the field.
- It does not weaken parser behavior because output validation is still driven by the candidate `schema_version` and typed candidate fields, not by trusting `instruction.output_schema_name`.

Why this is not overdesigned:

- The plan changes only the literal and the tests that prove its final LLM-facing projection.
- It does not introduce schema registries, alias maps, migrations, adapter layers, or compatibility readers.
- It keeps existing class names and internal type boundaries intact because the defect is only the value projected to the LLM.

## Affected Files

### Production

- `dayu/host/compaction.py`
  - Define `CONVERSATION_COMPACT_OUTPUT_SCHEMA_NAME_VNEXT = CONVERSATION_COMPACT_OUTPUT_SCHEMA_VERSION_VNEXT`; do not hard-code the same `"conversation_compact_output_v1"` literal twice.
  - Keep the separate name constant because `output_schema_name` is the instruction field value, while `schema_version` is the candidate output field value. The value is shared because both identify the same output contract.
  - Update the constant docstring and `CompactInstructionVNext` docstring so they describe an LLM-facing output contract identifier, not an internal schema/type name.
  - Keep `CompactInstructionVNext.__post_init__()` strict: only the new literal is accepted.
  - Keep `CompactInstructionVNext.to_json()` field names unchanged.
  - Inspect `__all__`: keep `CONVERSATION_COMPACT_OUTPUT_SCHEMA_NAME_VNEXT` exported, but update its docstring / semantics. Verify it has no external production use that depends on the old value.

- `dayu/config/prompts/scenes/conversation_compaction_user.md`
  - Narrowly clarify `instruction.output_schema_name` and `instruction.compact_goal` allowed values by replacing the current broad `instruction` description with explicit bullets:
    - `` `instruction.output_schema_name`：JSON string，唯一允许值为 `conversation_compact_output_v1`；它只是本次请求的输出格式标识，不是业务事实。``
    - `` `instruction.compact_goal`：JSON string，唯一允许值为 `roll_forward_session_memory`；它只是本次整理目标，不是财报事实或用户结论。``
  - Do not introduce internal Python names, Host module names, or migration terms.

### Design and Control Docs

- `docs/host/design.md`
  - Update section 24.3 `CompactInstruction.output_schema_name` to `"conversation_compact_output_v1"`.
  - Update adjacent prose to forbid Python type names in `CompactInstruction`.

- `docs/host/issues-implementation-control.md`
  - After implementation and validation, mark `WU-CM-01-F02-S6-R1` as `closed`.
  - Update current status / inspection note so WU-CM-01-F01 Slice 7 is unblocked and the next entry point is retrying Slice 7 public smoke closeout.

### Tests

- `tests/host/test_compaction_contract.py`
  - Add or update a focused test that constructs `conversation_compact_input_vnext_from_material_pack(...).to_json()`.
  - Assert `instruction.output_schema_name == "conversation_compact_output_v1"`.
  - Assert the serialized LLM material JSON does not contain `ConversationCompactOutputVNext`.
  - Assert invalid old `CompactInstructionVNext(output_schema_name="ConversationCompactOutputVNext")` raises `ValueError`.
  - Keep existing output parser / quality checker tests unchanged except for imports or expected constants if needed.

- `tests/host/test_llm_compaction.py`
  - In `test_llm_context_compactor_compact_uses_vnext_material`, inspect the rendered user prompt / extracted material JSON and assert:
    - `ConversationCompactOutputVNext` is absent.
    - `ConversationCompactInputVNext` is absent.
    - `"output_schema_name": "conversation_compact_output_v1"` is present in the rendered material.
  - Do not alter `parse_conversation_compact_output_vnext()` expected output shape.

- `tests/host/test_public_compact_smoke.py`
  - In the fake public compactor path, assert the final runtime material JSON has `instruction.output_schema_name == "conversation_compact_output_v1"`.
  - Assert `json.dumps(material_json, ensure_ascii=False, sort_keys=True)` does not contain `ConversationCompactOutputVNext`.
  - Prefer a focused helper such as `_assert_compactor_material_instruction_contract(material_json)` if multiple public compact tests should share the assertion.
  - Keep the optional real provider smoke optional; do not make provider availability part of this residual closure.

Optional only if an existing focused owner is more natural:

- `tests/host/test_compact_material.py`
  - Add the instruction literal assertion here only if this file already owns material JSON assembly coverage at the implementation point. Do not duplicate the same assertion across too many tests.

## Contract and Schema Impact

- LLM-facing input contract changes only one literal value:
  - old: `instruction.output_schema_name = "ConversationCompactOutputVNext"`
  - new: `instruction.output_schema_name = "conversation_compact_output_v1"`
- Output candidate schema field names do not change.
- Output `schema_version` value does not change.
- Parser accept/reject behavior does not change.
- Accept-barrier behavior does not change.
- Durable compact artifact/event schemas do not change.
- No legacy database migration is needed because this is request material generation, not durable schema compatibility.

## Implementation Slices

### Slice R1-S1: Compact Instruction Literal Rescope

Objective: Replace the internal type-name literal in production request material and update direct contract tests.

Allowed files:

- `dayu/host/compaction.py`
- `tests/host/test_compaction_contract.py`
- `tests/host/test_llm_compaction.py`

Exact allowed changes:

- Change the instruction schema-name constant value to `conversation_compact_output_v1` by assigning `CONVERSATION_COMPACT_OUTPUT_SCHEMA_NAME_VNEXT = CONVERSATION_COMPACT_OUTPUT_SCHEMA_VERSION_VNEXT`.
- Keep strict validation on `CompactInstructionVNext.output_schema_name`.
- Add tests proving the old literal is rejected and absent from LLM material JSON.
- Add tests proving parser / accept barrier still use the same output fields and validation rules.
- Verify `git grep "CONVERSATION_COMPACT_OUTPUT_SCHEMA_NAME_VNEXT" -- ":!dayu/host/compaction.py" ":!docs/"` has no external production use that depends on the old literal.

Stop condition:

- If changing the literal causes output parser behavior, artifact schema, EventLog payloads, or memory projection fields to require changes, stop and report scope expansion. Do not add compatibility handling.

### Slice R1-S2: Prompt, Public Smoke, and Control Closeout

Objective: Prove the final public opener compactor request is clean and update durable planning/control docs.

Allowed files:

- `dayu/config/prompts/scenes/conversation_compaction_user.md`
- `tests/host/test_public_compact_smoke.py`
- `docs/host/design.md`
- `docs/host/issues-implementation-control.md`
- `dayu/config/README.md` only if inspection finds prompt directory responsibilities or documented examples changed.
- `dayu/host/README.md` only if inspection finds Host README currently documents the old instruction literal or needs stable contract sync.

Exact allowed changes:

- Clarify prompt input schema wording for `instruction.output_schema_name`.
- Update design truth to the new literal.
- Add public smoke assertion on extracted runtime material JSON.
- Mark `WU-CM-01-F02-S6-R1` closed only after tests and pyright pass.
- Set next entry point to retry WU-CM-01-F01 Slice 7 public smoke closeout.

Stop condition:

- If prompt wording needs broader compactor schema rewrite beyond allowed-values clarification, stop and route to a prompt-specific plan review.
- If README inspection finds no stable documentation mismatch, do not mechanically edit README.

## Validation Commands

Run from repository root:

```bash
source .venv/bin/activate && pytest tests/host/test_compaction_contract.py tests/host/test_llm_compaction.py tests/host/test_public_compact_smoke.py -q
source .venv/bin/activate && pyright
git diff --check
```

Expected assertions:

- `tests/host/test_compaction_contract.py` passes with the new `instruction.output_schema_name` literal and old literal rejected.
- `tests/host/test_llm_compaction.py` passes and the rendered compactor request no longer contains `ConversationCompactOutputVNext`.
- `tests/host/test_public_compact_smoke.py` passes and public runtime material JSON no longer contains `ConversationCompactOutputVNext`.
- `pyright` reports no new or expanded errors.
- `git diff --check` reports no whitespace errors.

Optional provider smoke remains manual / environment gated:

```bash
source .venv/bin/activate && DAYU_RUN_REAL_COMPACTOR_SMOKE=1 pytest tests/host/test_public_compact_smoke.py::test_real_compactor_public_opener_compacts_and_preserves_continuity -q
```

Do not require this optional smoke to close `WU-CM-01-F02-S6-R1`, because provider availability is external to the literal contract.

## README and Doc Sync Decision

Implementation must inspect doc triggers after code changes:

- `dayu/host/compaction.py` changes trigger `dayu/host/README.md` inspection. Update only if the README documents the old instruction literal or gives a now-wrong compaction contract statement.
- `dayu/config/prompts/scenes/conversation_compaction_user.md` changes trigger `dayu/config/README.md` inspection. Update only if prompt directory responsibilities, examples, or current config behavior become inconsistent.
- `docs/host/design.md` must be updated because it currently contains the old LLM-facing literal and is the design truth.
- `docs/host/issues-implementation-control.md` must be updated after validation to close the residual and unblock Slice 7.

No root README update is expected because no CLI, user workflow, trace/render entry, installation, or configuration entry point changes.

## Risks and Open Questions

No blocking open questions.

Classified residual risks:

- Optional real-provider compact smoke remains environment-dependent. Owner: WU-CM-01-F01 Slice 7 public smoke closeout. Classification: covered by later approved slice.
- Internal class names such as `ConversationCompactOutputVNext` remain in Python code, type names, tests, and developer docs. Owner: none for this work unit because the defect is LLM-facing projection only. Classification: non-goal.
- Historical review artifacts may still mention the old literal. Owner: none for this work unit because artifacts are historical records, not runtime LLM material. Classification: non-goal.

## Completion Report Format

Implementation completion must report:

- Production changes:
  - exact instruction literal change;
  - whether prompt wording was updated;
  - whether design truth and control doc were updated.
- Tests:
  - exact pytest command and result;
  - pyright result;
  - `git diff --check` result.
- Residual status:
  - `WU-CM-01-F02-S6-R1` closed or not closed, with reason.
- Next entry point:
  - retry WU-CM-01-F01 Slice 7 public smoke closeout if closed;
  - blocker details if not closed.

## Closeout and Slice 7 Retry Path

After implementation validation passes:

1. Update `docs/host/issues-implementation-control.md`:
   - set `WU-CM-01-F02-S6-R1` status to `closed`;
   - record that runtime LLM-facing material now uses `conversation_compact_output_v1`;
   - set `WU-CM-01-F01` from blocked to ready for Slice 7 retry;
   - set next entry point to WU-CM-01-F01 Slice 7 public smoke closeout retry.
2. Create the accepted local commit for this residual closure under the gateflow commit convention.
3. Restart WU-CM-01-F01 Slice 7 from implementation gate using the original Slice 7 scope, now adding assertions that were previously blocked:
   - public smoke material JSON contains no internal compact type names;
   - runner-call messages / manifest counts / role digest closeout assertions are completed;
   - utility smoke help and applicable full-run validations follow the Slice 7 plan.
4. Do not mark WU-CM-01-F01 Slice 7 accepted until public smoke tests and required pyright validation pass.
