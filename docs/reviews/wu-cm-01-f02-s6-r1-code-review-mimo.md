# Code Review

## Scope

- Mode: current changes
- Branch: `phaseflow/wu-dur-obs-cm-closeout`
- Base: `main`
- Output file: `docs/reviews/wu-cm-01-f02-s6-r1-code-review-mimo.md`
- Included scope:
  - Production: `dayu/host/compaction.py`
  - Prompt/design: `dayu/config/prompts/scenes/conversation_compaction_user.md`, `docs/host/design.md`
  - Tests: `tests/host/test_compaction_contract.py`, `tests/host/test_llm_compaction.py`, `tests/host/test_public_compact_smoke.py`
  - Control doc: `docs/host/issues-implementation-control.md`
- Excluded scope: 无
- Parallel review coverage: 无

## Findings

未发现实质性问题。

### Required Review Points — Pass/Fail Verdict

1. **Runtime LLM-facing compactor material JSON 不再通过 `instruction.output_schema_name` 暴露 `ConversationCompactOutputVNext`** — PASS
   - 直接证据: `dayu/host/compaction.py:34` — `CONVERSATION_COMPACT_OUTPUT_SCHEMA_NAME_VNEXT = CONVERSATION_COMPACT_OUTPUT_SCHEMA_VERSION_VNEXT`，运行时值为 `"conversation_compact_output_v1"`。
   - 测试覆盖: `test_compact_instruction_uses_llm_facing_output_contract_identifier` (contract.py:78) 断言 `instruction["output_schema_name"] == "conversation_compact_output_v1"` 且 material_text 不含旧名；`test_llm_context_compactor_compact_uses_vnext_material` (llm_compaction.py:246) 从实际渲染 prompt 提取 material JSON 并验证；`test_post_compaction_fact_reuse_uses_raw_accepted_tool_evidence` (public_smoke.py:211) 通过 `FakeCompactorRunAgent.__call__` 对每次 compactor request 调用 `_assert_compactor_material_instruction_contract`。

2. **`CONVERSATION_COMPACT_OUTPUT_SCHEMA_NAME_VNEXT` 从 `CONVERSATION_COMPACT_OUTPUT_SCHEMA_VERSION_VNEXT` 派生，不重复字面量** — PASS
   - 直接证据: `compaction.py:34` — `= CONVERSATION_COMPACT_OUTPUT_SCHEMA_VERSION_VNEXT`，非 `= "conversation_compact_output_v1"`。

3. **`CompactInstructionVNext` 严格校验和 `to_json` 字段名不变** — PASS
   - 直接证据: `compaction.py:702` — `__post_init__` 仍用 `!= CONVERSATION_COMPACT_OUTPUT_SCHEMA_NAME_VNEXT` 做 identity 比较；`compaction.py:713-715` — `to_json()` 字段名仍为 `"output_schema_name"` 和 `"compact_goal"`。

4. **compact output schema 字段、output schema_version、parser 行为、accept barrier、durable schema、public Host API 不变** — PASS
   - pytest 39 passed, 1 skipped in 0.77s；pyright 0 errors。
   - 测试覆盖 `test_parse_conversation_compact_output_vnext_accepts_design_schema`、`test_vnext_quality_checker_*`、`test_compaction_public_exports_do_not_include_old_compact_contract` 等全链路断言。

5. **测试验证最终 runtime material JSON，不仅是 prompt 模板文本，包括 public fake compactor 路径** — PASS
   - 直接证据:
     - `test_llm_context_compactor_compact_uses_vnext_material` (llm_compaction.py:296-301) — 从渲染后 prompt 中 `_material_json_from_compactor_prompt` 提取 material JSON 并验证 instruction。
     - `FakeCompactorRunAgent.__call__` (public_smoke.py:630) — 对每次 compactor Engine request 提取 material JSON 并调用 `_assert_compactor_material_instruction_contract`。
     - `test_compact_instruction_uses_llm_facing_output_contract_identifier` (contract.py:85-101) — 直接构造 `ConversationCompactInputVNext.to_json()` 验证 material。

6. **旧内部类型名被 `CompactInstructionVNext` 拒绝** — PASS
   - 直接证据: `test_compact_instruction_rejects_internal_python_type_name` (contract.py:104-112) — `CompactInstructionVNext(output_schema_name="ConversationCompactOutputVNext")` 抛出 `ValueError`。
   - 生产代码: `compaction.py:702-703` — `__post_init__` 比较 `!= CONVERSATION_COMPACT_OUTPUT_SCHEMA_NAME_VNEXT`（当前值 `"conversation_compact_output_v1"`），旧值 `"ConversationCompactOutputVNext"` 必然不匹配。

7. **Prompt/design 措辞保持 LLM-facing，不引入内部名称或迁移术语** — PASS
   - 直接证据:
     - `conversation_compaction_user.md:20-22` — `instruction.output_schema_name` 和 `instruction.compact_goal` 说明为业务可读字段，唯一允许值为业务标识，不涉及 Python 类型名。
     - `design.md:2831` — `output_schema_name: "conversation_compact_output_v1"` 已从旧值更新。
     - `design.md:2837` — 散文明确 "`output_schema_name` 是业务可读输出 contract 标识，不是 Python 类型名"。
     - `test_default_compactor_prompt_is_llm_facing_and_self_contained` (public_smoke.py:122) 断言 `_FORBIDDEN_COMPACTOR_PROMPT_TERMS`（含 `ConversationCompactOutputVNext`、`vNext`、`migration` 等）均不出现在 prompt 中。

8. **无兼容 alias / wrapper / fallback** — PASS
   - 直接证据: diff 只有字面量替换和 docstring 更新，无兼容层引入。`__all__` 仍导出 `CONVERSATION_COMPACT_OUTPUT_SCHEMA_NAME_VNEXT`，语义更新但无 re-export 或 wrapper。

9. **README sync 决策可辩护** — PASS
   - 直接证据: implementation codex 记录了 `dayu/host/README.md`、`dayu/config/README.md`、`tests/README.md` 的 trigger 检查结论：README 文档内部类行为，不文档 LLM-facing instruction literal，无稳定文档不一致。

## Open Questions

无。

## Residual Risk

- `WU-CM-01-F02-S6-R1` residual risk item 在 control doc 中仍为 `open` 状态。这是预期行为：implementation codex 和 plan 均明确裁决留给 code review / controller bookkeeping gate 关闭。
- Optional real-provider compact smoke 仍受环境限制（`DAYU_RUN_REAL_COMPACTOR_SMOKE=1`）。Owner: WU-CM-01-F01 Slice 7 public smoke closeout。
- 内部 Python 类型名 `ConversationCompactOutputVNext` 仍在代码、类型名、测试和开发者文档中存在。Owner: none（non-goal，defect 仅限 LLM-facing projection）。
