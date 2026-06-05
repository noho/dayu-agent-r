# Code Review

## Scope

- Mode: current changes
- Branch: phaseflow/wu-dur-obs-cm-closeout
- Base: main
- Output file: docs/reviews/wu-dur-obs-cm-closeout-slice6-code-review-ds.md
- Included scope:
  - `dayu/config/prompts/scenes/conversation_compaction.md`
  - `dayu/config/prompts/scenes/conversation_compaction_user.md`
  - `tests/host/test_public_compact_smoke.py`
  - `dayu/config/README.md`
  - `tests/README.md`
  - `docs/host/issues-implementation-control.md`
- Excluded scope:
  - Host 生产代码（`dayu/host/compaction.py`、`dayu/host/compaction_evidence.py` 等），仅验证 prompt 字段与生产 material JSON 字段对齐
  - design.md 和其他不在 diff 范围内的文档
- Parallel review coverage: 无

## Findings

### 1-未修复-中-`instruction.output_schema_name` 运行时注入 Python 类型名 `ConversationCompactOutputVNext` 到 LLM-facing material JSON

- **入口/函数**: `CompactInstructionVNext.to_json()` → compactor material JSON → `<<compaction_request>>` 占位符替换
- **文件(行号)**: `dayu/host/compaction.py:34` (常量定义), `dayu/host/compaction.py:692` (默认值), `dayu/host/compaction.py:714` (to_json)
- **输入场景**: 任意一次 compaction 触发时，Host 构造 material JSON 并将 `instruction.output_schema_name` 注入
- **实际分支**: `CONVERSATION_COMPACT_OUTPUT_SCHEMA_NAME_VNEXT = "ConversationCompactOutputVNext"` 字面量进入 LLM 上下文
- **预期行为**: 按 plan 目标"删除或改写 ConversationCompactOutputVNext"，LLM 不应看到任何 Python 类型名
- **实际行为**: prompt 模板自身已清理干净，但运行时 material JSON 的 `instruction.output_schema_name` 字段仍携带字符串 `"ConversationCompactOutputVNext"`。prompt 虽然声明 "不要把该字段内容当成财报事实"，但 Python 类型名仍占据 LLM 上下文，增加认知负担
- **直接证据**:
  - `dayu/host/compaction.py:34`: `CONVERSATION_COMPACT_OUTPUT_SCHEMA_NAME_VNEXT = "ConversationCompactOutputVNext"`
  - `dayu/host/compaction.py:714`: `to_json()` 输出 `{"output_schema_name": self.output_schema_name, ...}`
  - `dayu/host/compaction.py:1225`: material JSON 中 `"instruction": self.instruction.to_json()`
  - 测试 `test_default_compactor_prompt_is_llm_facing_and_self_contained` 仅检查 prompt 模板文本（`system_prompt + user_prompt_template`），不检查运行时替换后的完整 material JSON，因此未发现此泄露
- **影响**: Slice 6 的 prompt 清理目标未完全达成——prompt 模板干净，但 LLM 最终消费的完整文本仍含 Python 类名。严重性受限因为：(a) 在 `instruction` metadata 块内，模型被明确告知非业务事实；(b) 输出 schema 已在 prompt 中完整自足说明，模型不依赖此字段决定输出格式
- **建议改法和验证点**:
  - 将 `CONVERSATION_COMPACT_OUTPUT_SCHEMA_NAME_VNEXT` 的值改为 `"conversation_compact_output_v1"`（与输出 `schema_version` 允许值一致），或改为纯功能描述如 `"session_memory_compaction"`
  - 同步更新 `CompactInstructionVNext.__post_init__` 中的校验逻辑
  - 同步更新 `dayu/host/compaction.py:2945` 的 `__all__` 白名单
  - 验证：在测试中构造完整 material JSON 后检查不包含 `ConversationCompactOutputVNext`
- **修复风险**: 中。需跨 slice 修改 Host 生产代码常量与 parser 校验逻辑，超出 Slice 6 prompt asset 范围。建议作为 Slice 6 或后续 closeout slice 的 residual risk 跟踪
- **严重程度**: 中

### 2-未修复-低-evidence-backed fact 保留规则 `应为` 语气弱于旧 `必须`

- **入口/函数**: conversation_compaction_user.md "保留规则"
- **文件(行号)**: `dayu/config/prompts/scenes/conversation_compaction_user.md:105`
- **输入场景**: LLM 在整理 evidence material 时，参考"保留规则"决定是否产出 `evidence_backed_facts`
- **实际分支**: 新规则 "应为每个确实需要保留的 evidence label 产出至少一个 evidence_backed_facts 条目"；旧规则 "必须为每个被保留的 evidence label 产出至少一个 evidence_backed_facts 条目"
- **预期行为**: 按 plan 要求"Prompt does not let result/content source rules weaken evidence-backed fact requirements"，强制约束不应减弱
- **实际行为**: 旧 `必须` → 新 `应为` 将强制约束变为建议语气；增加了 `确实需要保留的` 限定语，给模型 skipping 的借口空间
- **直接证据**:
  - 旧 prompt（`git show HEAD:dayu/config/prompts/scenes/conversation_compaction_user.md`）第 59 行：`必须为每个被保留的 evidence label 产出至少一个 evidence_backed_facts 条目；不得合成 fallback fact。`
  - 新 prompt 第 105 行：`应为每个确实需要保留的 evidence label 产出至少一个 evidence_backed_facts 条目；不要合成无证据事实。`
- **影响**: LLM 可能选择性跳过部分 evidence label 的事实提取。但实际影响有限：(a) 输出字段级描述仍保留 `必填`、`必须非空` 等强制约束；(b) LLM 对 应/必须 的区分不如人类读者严格
- **建议改法和验证点**:
  - 恢复 `必须` 语气，但可以保留 `确实需要保留的` 限定语：`必须为每个确实需要保留的 evidence label 产出至少一个 evidence_backed_facts 条目；不得合成无证据事实。`
  - 验证：确认 `evidence_backed_facts` 字段描述中已保留 `必填 JSON array`、`必须非空` 约束
- **修复风险**: 低。仅改 prompt 文本
- **严重程度**: 低

### 3-未修复-低-`_FORBIDDEN_COMPACTOR_PROMPT_TERMS` 中通用英语词 `digest`、`cursor`、`policy` 存在未来误报风险

- **入口/函数**: `test_default_compactor_prompt_is_llm_facing_and_self_contained`
- **文件(行号)**: `tests/host/test_public_compact_smoke.py:113-115`
- **输入场景**: 未来 prompt 更新中合法使用 `digest`、`cursor`、`policy` 等英语常见词描述业务场景时
- **实际分支**: `assert forbidden_term not in prompt_text` 会因通用英语词误杀合法 prompt
- **预期行为**: 仅阻止内部治理术语（`EventLog`、`payload ref`、`digest` 作为 `sha256:hex` digest 标识、`cursor` 作为 page/snapshot cursor、`policy` 作为 `ContextBudgetPolicy` 引用）进入 LLM 语境
- **实际行为**: 当前 prompt 不使用这些词，测试全部通过。但 `digest`（摘要）、`cursor`（光标/游标）、`policy`（策略/政策）是高频通用英语词，未来 prompt 若写"会计政策"(accounting policy) 或"摘要内容"(content digest) 会触发误报
- **直接证据**: `tests/host/test_public_compact_smoke.py:95-116` 的 `_FORBIDDEN_COMPACTOR_PROMPT_TERMS` 包含 `"digest"`、`"cursor"`、`"policy"` 三条通用词
- **影响**: 未来合法 prompt 更新可能被测试误拦，需人工判断并排除。不影响当前正确性
- **建议改法和验证点**:
  - 可考虑替换为更精确的子串匹配：`"payload_refs"` 已是精确匹配，但 `"digest"` 可能需要具体化为 `"sha256:"` 或 `"content_digest"`
  - 或在 `_FORBIDDEN_COMPACTOR_PROMPT_TERMS` 上方添加注释说明这些词在 compactor prompt 语境中对应内部治理语义
  - 仅建议，非必须修复
- **修复风险**: 低。仅改测试常量
- **严重程度**: 低

## Open Questions

1. 运行时 material JSON 中的 `instruction.output_schema_name = "ConversationCompactOutputVNext"` 是否应在 Slice 6 或后续 slice 修复？当前 prompt template 已清理，但因 Host 常量注入，LLM 最终仍看到 Python 类型名。是否因 `instruction` 被标注为 metadata 而接受此泄露？

## Residual Risk

- `instruction.output_schema_name` 的 Python 类型名泄露（Finding 1）未在 Slice 6 内修复，because it requires a Host production constant change beyond the prompt-only allowed files. 若裁决为 accepted deferral，需在后续 slice 或 WU-CM-01-F01 smoke closeout 中处理。
- evidence-backed fact 保留规则的语气弱化（Finding 2）属于 prompt 微调建议；若模型在复杂 material 上出现 evidence fact 遗漏，可第一时间检查此规则是否贡献。
- `_FORBIDDEN_COMPACTOR_PROMPT_TERMS` 通用词误报风险（Finding 3）仅影响未来维护者，不影响当前正确性。
- Slice 6 不覆盖 `utils/smoke_host_public_*.py` 四个 smoke 脚本审计（属于 Slice 7），也不覆盖真实模型 compaction 质量 eval（属于后续 WU）。
- 其余 plan review point 均通过：prompt 自足说明输入/输出、label 解释为请求内引用、schema 字段名不变、不暴露 EventLog/digest/cursor/policy、不弱化 current input anchor 不可引用规则、README 更新在职责边界内、control doc bookkeeping 正确。

## Verdict

No blocking findings. Slice 6 implementation passes core review points — prompt template is clean of internal implementation and migration terminology, self-contained for stateless LLM, preserves output schema field names, and does not expose Host governance internals. The `instruction.output_schema_name` runtime data injection (Finding 1) is a cross-boundary residual risk from Host production code, outside the prompt-only scope of this slice. Tests pass (6 passed, 1 skipped), pyright 0 errors.
