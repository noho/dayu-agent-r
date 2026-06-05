# Code Review — Re-review

## Scope

- Mode: current changes re-review
- Branch: phaseflow/wu-dur-obs-cm-closeout
- Base: main
- Original review: docs/reviews/wu-dur-obs-cm-closeout-slice6-code-review-ds.md
- Fix artifact: docs/reviews/wu-dur-obs-cm-closeout-slice6-fix-codex.md
- Output file: docs/reviews/wu-dur-obs-cm-closeout-slice6-rereview-ds.md
- Re-review scope:
  - DS Finding 2 fix verification：`conversation_compaction_user.md` 保留规则 + `test_public_compact_smoke.py` 守卫断言
  - DS Finding 1 / Finding 3 确认未回归
- Excluded scope:
  - Host 生产代码（Finding 1 指向的 `dayu/host/compaction.py`），已确认为 deferred/rescope，本轮不检查

## Findings

### Fix DS Finding 2 — 已修复

- **入口/函数**: `test_default_compactor_prompt_is_llm_facing_and_self_contained` → `_compactor_baseline_inputs()` → ConfigLoader + ScenePrepare 真实装配
- **文件(行号)**:
  - `dayu/config/prompts/scenes/conversation_compaction_user.md:105`
  - `tests/host/test_public_compact_smoke.py:139-144`
- **验证**:
  1. Prompt 保留规则第 105 行文字：`必须为每个确实需要保留的 evidence label 产出至少一个 evidence_backed_facts 条目；不得合成无证据事实。` — 与 accepted fix spec 一致 ✓
  2. 测试正向断言（第 139-143 行）通过真实 `ConfigLoader` + `ScenePrepare` + 文件读取装配出的 `user_prompt_template` 检查该强约束文本存在 ✓
  3. 测试反向断言（第 144 行）确认弱语气 `应为每个确实需要保留的 evidence label` 不在装配出的 `user_prompt_template` 中 ✓
  4. `pytest tests/host/test_public_compact_smoke.py` — 6 passed, 1 skipped ✓
  5. `pyright` — 0 errors, 0 warnings ✓
- **严重程度**: 已修复，不适用

### DS Finding 1 — deferred/rescope，未引入回归

- **文件(行号)**: 无变更
- **确认**: `conversation_compaction_user.md` 与 `test_public_compact_smoke.py` 的 diff 不涉及 `instruction.output_schema_name`、`CONVERSATION_COMPACT_OUTPUT_SCHEMA_NAME_VNEXT` 或 `dayu/host/compaction.py` ✓
- **严重程度**: 已确认，本轮不修复

### DS Finding 3 — non-blocking maintenance risk，未引入回归

- **文件(行号)**: 无变更
- **确认**: `_FORBIDDEN_COMPACTOR_PROMPT_TERMS` 内容未变化，`digest`/`cursor`/`policy` 通用词仍在列表中，但 fix 未扩大或缩小其范围 ✓
- **严重程度**: 已确认，本轮不修复

## Open Questions

无。

## Residual Risk

- DS Finding 1（`instruction.output_schema_name = "ConversationCompactOutputVNext"` 运行时泄露）：deferred to later work unit / Host production contract rescope，需由 controller 在 control doc 中记录 owner 与后续处理 slice。
- DS Finding 3（`_FORBIDDEN_COMPACTOR_PROMPT_TERMS` 通用词误报风险）：deferred with no code change，仅影响未来维护者。

## Verdict

DS Finding 2 已修复，验证通过。DS Finding 1 按用户指令作为 deferred/rescope residual，不在本轮 prompt-text fix 中处理。DS Finding 3 保持 non-blocking。无新增 blockage 或回归。

Fix 范围严格遵守 accepted finding 边界：仅改 `conversation_compaction_user.md` 一句强制语气和 `test_public_compact_smoke.py` 两条守卫断言。未扩散到系统 prompt、README、control doc 或其他文件。
