# Code Review (Re-review)

## Scope

- Mode: current changes (fix verification)
- Branch: `phaseflow/wu-dur-obs-cm-closeout`
- Base: `main`
- Output file: `docs/reviews/wu-dur-obs-cm-closeout-slice6-rereview-mimo.md`
- Included scope:
  - `dayu/config/prompts/scenes/conversation_compaction_user.md` (fix target)
  - `tests/host/test_public_compact_smoke.py` (fix guard)
  - `docs/reviews/wu-dur-obs-cm-closeout-slice6-fix-codex.md` (fix artifact)
- Excluded scope: DS Finding 1 (runtime `instruction.output_schema_name`) — deferred by user instruction; DS Finding 3 (generic forbidden terms) — non-blocking maintenance risk
- Parallel review coverage: 无

## Findings

未发现实质性问题。

### DS Finding 2 — FIXED

**验证结果**: PASS。

修复内容正确：

1. **Prompt 文本**（`conversation_compaction_user.md:105`）：保留规则已恢复为强约束语气：
   - 旧（弱）：`应为每个确实需要保留的 evidence label 产出至少一个 evidence_backed_facts 条目；不要合成无证据事实。`
   - 新（强）：`必须为每个确实需要保留的 evidence label 产出至少一个 evidence_backed_facts 条目；不得合成无证据事实。`
   - 与 DS review 建议的改法一致。

2. **正向断言**（`test_public_compact_smoke.py:139-143`）：通过 `_compactor_baseline_inputs()` 真实装配默认 compactor prompt，断言 user prompt template 包含强约束文本：
   ```python
   assert (
       "必须为每个确实需要保留的 evidence label 产出至少一个 "
       "evidence_backed_facts 条目；不得合成无证据事实。"
       in user_prompt_template
   )
   ```

3. **反向断言**（`test_public_compact_smoke.py:144`）：断言弱语气不再出现：
   ```python
   assert "应为每个确实需要保留的 evidence label" not in user_prompt_template
   ```

4. **装配路径**：两个断言均通过 `_compactor_baseline_inputs()` 使用真实 `ConfigLoader` → `ScenePrepare` → prompt asset 读取，不使用 test-only bridge。

直接证据：`conversation_compaction_user.md:105`；`test_public_compact_smoke.py:139-144`。

### DS Finding 1 — DEFERRED (intentional, not regression)

**验证结果**: 确认为 deferred / rescope residual。

fix artifact 正确记录 Finding 1 为 deferred：`instruction.output_schema_name = "ConversationCompactOutputVNext"` 是 Host 生产代码常量注入，超出 Slice 6 prompt-only 允许文件边界。这不是 prompt-text 回退，而是运行时 material JSON 的跨层残留。用户指令明确要求将其作为 deferred/rescope residual 处理。

### DS Finding 3 — NON-BLOCKING (unchanged)

**验证结果**: 确认为 non-blocking maintenance risk。

`_FORBIDDEN_COMPACTOR_PROMPT_TERMS` 中的 `digest`、`cursor`、`policy` 通用词风险未修改，符合用户指令。当前 prompt 不使用这些词，测试通过。

## Verdict

DS Finding 2 fix verified。prompt 文本已恢复强约束 `必须` 语气，测试通过正向+反向断言守住该文本。无 blocking findings。DS Finding 1 为 intentional deferral，DS Finding 3 为 non-blocking maintenance risk。
