# WU-CM-01-F02-S6-R1 Implementation Codex

## Gate

- gate: implementation
- work unit: `WU-CM-01-F02-S6-R1`
- branch: `phaseflow/wu-dur-obs-cm-closeout`
- accepted plan: `docs/host/wu-cm-01-f02-s6-r1-compact-instruction-rescope-plan.md`
- accepted plan review: `docs/reviews/wu-cm-01-f02-s6-r1-plan-review-controller-adjudication.md`
- artifact path: `docs/reviews/wu-cm-01-f02-s6-r1-implementation-codex.md`

## Scope

本轮只处理 LLM-facing compactor material JSON 中的 `instruction.output_schema_name` 字面量。动机成立：该字段会被 `CompactInstructionVNext.to_json()` 投影到 `ConversationCompactInputVNext.to_json()`，再由 `LLMContextCompactor` 渲染进 `UNTRUSTED_COMPACTION_MATERIAL_JSON_BEGIN/END` 数据块；旧值 `ConversationCompactOutputVNext` 是内部 Python 类型名，不是模型完成当前整理任务所需的业务可读 contract 标识。

非目标保持不变：不重命名内部 `ConversationCompactOutputVNext` 类型，不修改 compact output 字段名，不放松 parser / accept barrier，不改 durable schema，不改 public Host API，不添加兼容 alias / wrapper / fallback。

## Changed Files

- `dayu/host/compaction.py`
  - exact literal change: `CONVERSATION_COMPACT_OUTPUT_SCHEMA_NAME_VNEXT` 由旧的 `"ConversationCompactOutputVNext"` 改为 `CONVERSATION_COMPACT_OUTPUT_SCHEMA_VERSION_VNEXT`，实际 runtime 值为 `"conversation_compact_output_v1"`。
  - 更新常量与 `CompactInstructionVNext.output_schema_name` docstring，语义改为投影给 LLM 的输出 contract 标识，不是内部类型名。
  - 保留 `CompactInstructionVNext.__post_init__()` 严格校验和 `to_json()` 字段名。
- `dayu/config/prompts/scenes/conversation_compaction_user.md`
  - 将 broad `instruction` 说明改为明确允许值：
    - `instruction.output_schema_name` 唯一允许值 `conversation_compact_output_v1`。
    - `instruction.compact_goal` 唯一允许值 `roll_forward_session_memory`。
- `docs/host/design.md`
  - section 24.3 的 `CompactInstruction.output_schema_name` 改为 `conversation_compact_output_v1`。
  - 邻近文字明确 `output_schema_name` 是业务可读输出 contract 标识，不是 Python 类型名。
- `tests/host/test_compaction_contract.py`
  - 增加 material JSON instruction contract 断言：包含 `conversation_compact_output_v1`，不包含 `ConversationCompactOutputVNext`。
  - 增加 `CompactInstructionVNext(output_schema_name="ConversationCompactOutputVNext")` 被拒绝的断言。
- `tests/host/test_llm_compaction.py`
  - 从实际渲染的 compactor user prompt 提取 material JSON，断言 runtime material 包含 `output_schema_name = "conversation_compact_output_v1"`，且不包含 `ConversationCompactOutputVNext` / `ConversationCompactInputVNext`。
- `tests/host/test_public_compact_smoke.py`
  - 在 fake public compactor 捕获点校验每次最终 runtime material JSON 的 instruction contract，断言旧内部类型名不存在。
- `docs/host/issues-implementation-control.md`
  - 只更新 implementation artifact / gate bookkeeping；残余项保留到 code review / controller closure 裁决。

## Contract Status

- Compact output schema fields: unchanged.
- Output candidate `schema_version`: unchanged, still `conversation_compact_output_v1`.
- Parser behavior: unchanged.
- Accept-barrier behavior: unchanged.
- Durable artifact / EventLog / memory projection schemas: unchanged.
- Public Host APIs: unchanged.
- `__all__`: inspected; `CONVERSATION_COMPACT_OUTPUT_SCHEMA_NAME_VNEXT` remains exported with updated semantics.
- External production usage check: `git grep -n "CONVERSATION_COMPACT_OUTPUT_SCHEMA_NAME_VNEXT" -- ':!dayu/host/compaction.py' ':!docs/'` returned no matches.

## Validation

- `source .venv/bin/activate && pytest tests/host/test_compaction_contract.py tests/host/test_llm_compaction.py tests/host/test_public_compact_smoke.py -q`
  - result: `39 passed, 1 skipped in 0.80s`
- `source .venv/bin/activate && pyright`
  - result: `0 errors, 0 warnings, 0 informations`
  - note: pyright reported only an available version update warning.
- `git diff --check`
  - result: passed, no whitespace errors.
- Production external grep:
  - command: `git grep -n "CONVERSATION_COMPACT_OUTPUT_SCHEMA_NAME_VNEXT" -- ':!dayu/host/compaction.py' ':!docs/'`
  - result: no matches.

## README Sync Decision

- `dayu/host/README.md`: inspected. It documents internal `ConversationCompactOutputVNext` structured candidate behavior, not the LLM-facing `instruction.output_schema_name` literal; no stable doc mismatch from this change.
- `dayu/config/README.md`: inspected by trigger search; it does not document this prompt field literal or conflicting prompt directory responsibility; no update.
- `tests/README.md`: inspected by trigger search; it does not document these specific compaction contract assertions; no update.

## Residual Risks

- fixed in current slice: runtime LLM-facing material JSON no longer contains `ConversationCompactOutputVNext` as `instruction.output_schema_name`; public fake compactor path now asserts the final material contract.
- fixed in current slice: old internal Python type name is rejected by `CompactInstructionVNext` strict validation.
- covered by existing validation: parser and accept barrier unchanged; targeted tests still cover old candidate schema rejection, label validation, current-input-anchor rejection, cross-section label rejection, and public compact smoke behavior.
- assigned to next gate: controller final closure of `WU-CM-01-F02-S6-R1` after code review / re-review, then retry `WU-CM-01-F01` Slice 7 public smoke closeout.

## Status

Implementation complete and ready for code review. `WU-CM-01-F02-S6-R1` is functionally fixed by this slice, but the control doc leaves final residual closure to the review / controller bookkeeping gate per current instruction.
