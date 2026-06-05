# Slice 6 Fix

## Scope

- Work unit: WU-CM-01-F02
- Slice: Slice 6 code review fix
- Gate: code review fix
- Branch: `phaseflow/wu-dur-obs-cm-closeout`
- Accepted finding fixed: DS Finding 2
- Artifact path: `docs/reviews/wu-dur-obs-cm-closeout-slice6-fix-codex.md`

## First-principles judgment

DS Finding 2 成立。`conversation_compaction_user.md` 是直接进入默认 compactor prompt 的 LLM-facing 文本；证据保留规则若使用 `应为`，会把必须保留 evidence-backed facts 的约束弱化为建议语气。对无状态、上下文有限的 compactor LLM 来说，强制规则必须在当前 prompt 中自足、明确，不能依赖字段级描述补救。

本轮修复边界成立且应保持窄范围：只恢复 evidence label 保留规则的强制语气，并用真实默认 compactor prompt 装配 smoke 守住该文本。

## Changed files

- `dayu/config/prompts/scenes/conversation_compaction_user.md`
- `tests/host/test_public_compact_smoke.py`
- `docs/reviews/wu-dur-obs-cm-closeout-slice6-fix-codex.md`

## Fix

### DS Finding 2

状态：已修复。

修复内容：

- 将保留规则从弱语气 `应为每个确实需要保留的 evidence label...` 改为强约束：`必须为每个确实需要保留的 evidence label 产出至少一个 evidence_backed_facts 条目；不得合成无证据事实。`
- 在 `test_default_compactor_prompt_is_llm_facing_and_self_contained` 中增加断言，确认真实默认 compactor prompt 装配出的 user prompt template 包含强约束文本。
- 同一测试增加反向断言，确认弱语气 `应为每个确实需要保留的 evidence label` 不再出现在默认 user prompt template 中。

## Deferred / not fixed

### DS Finding 1

状态：未在本轮修复，按用户指令作为 deferred / rescope residual 记录。

原因：Finding 1 涉及运行时 material JSON 中 `instruction.output_schema_name = ConversationCompactOutputVNext`，修复需要修改 Host 生产 compact instruction 字面量与相关 contract 校验，不属于本轮窄范围 prompt fix，也超出 Slice 6 允许文件边界。本轮不把它作为 prompt-text fix 处理。

### DS Finding 3

状态：未修改。

原因：Finding 3 是 generic forbidden-term 维护风险，用户明确要求本轮不做代码变更。

## Validation

- `source .venv/bin/activate && pytest tests/host/test_public_compact_smoke.py`
  - Result: passed, `6 passed, 1 skipped`
- `source .venv/bin/activate && pyright`
  - Result: passed, `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - Result: passed

## Docs decision

未更新 README。本轮仅调整 compactor prompt 的一句约束语气和对应 smoke 断言，不改变配置入口、prompts 目录职责、测试分层或运行方式；已有 README 职责范围内没有需要同步的新稳定说明。

## Residual risks

- DS Finding 1：assigned to later work unit / production contract rescope。需要后续由控制器记录并在允许修改 Host compact instruction contract 时处理。
- DS Finding 3：deferred with no current code change。仅影响未来 forbidden-term 维护，不影响当前 prompt 语义正确性。
- 真实模型在复杂 evidence material 上的保留质量仍未由本轮新增 eval 覆盖；本轮只守住默认 prompt 装配文本约束。

## Completion status

本轮 accepted fix 已完成，验证通过，无 blocking open question。
