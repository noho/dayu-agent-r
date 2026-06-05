# WU-CM-01-F02-S6-R1 Compact Instruction Contract Rescope Plan Review

## Reviewed Target

- **Plan artifact**: `docs/host/wu-cm-01-f02-s6-r1-compact-instruction-rescope-plan.md`
- **Scope**: 生产 compact instruction contract rescope，将 LLM-facing material 中的 `instruction.output_schema_name` 从内部 Python 类型名改为业务可读 stable literal。
- **Reviewer**: mimo
- **Date**: 2026-06-05

## Assumptions Tested

1. Root cause 是 runtime material JSON 中的内部类型名，而非仅 prompt template 文本残留。
2. 替换 constant value 比移除字段更安全、更可维护。
3. `__post_init__` 严格校验在新 literal 下仍然正确。
4. 输出 parser / accept-barrier 行为不受 input literal 变更影响。
5. 设计真源 section 24.3 需要同步更新。
6. 测试覆盖最终 runtime material JSON，而非仅 prompt template 文本。

## Findings

### 001-unfixed-low-两常量值重复，应显式派生消除二源
- **位置**: Chosen Approach, Affected Files - Production `dayu/host/compaction.py`
- **问题类型**: 最佳实践偏离
- **当前写法**: plan 允许"Change `CONVERSATION_COMPACT_OUTPUT_SCHEMA_NAME_VNEXT` value from `ConversationCompactOutputVNext` to `conversation_compact_output_v1`，or derive it directly from `CONVERSATION_COMPACT_OUTPUT_SCHEMA_VERSION_VNEXT`"
- **反例/失败场景**: 实现 agent 选择直接硬编码新 literal 为字符串常量值，导致 `CONVERSATION_COMPACT_OUTPUT_SCHEMA_NAME_VNEXT = "conversation_compact_output_v1"` 和 `CONVERSATION_COMPACT_OUTPUT_SCHEMA_VERSION_VNEXT = "conversation_compact_output_v1"` 两个常量存储相同字符串。未来若 schema version 升级为 v2，实现者可能只更新 VERSION 常量而遗漏 NAME 常量，导致 `__post_init__` 校验拒绝合法 candidate。
- **为什么有问题**: 项目约束"禁止魔法字符串"和"数据处理、存储、工具调用职责必须分离，重复逻辑必须抽取"。两个常量承载相同值但名义不同，违反 single source of truth。
- **直接证据**: `dayu/host/compaction.py:31-35` — 两个常量紧邻定义，当前值不同，但 plan 目标使它们相同。
- **影响**: 实现 agent 可能选择不派生，引入 silent value duplication；后续 schema version 迭代时遗漏同步。
- **建议改法和验证点**: plan 应明确选择"derive from `CONVERSATION_COMPACT_OUTPUT_SCHEMA_VERSION_VNEXT`"为唯一路径，即 `CONVERSATION_COMPACT_OUTPUT_SCHEMA_NAME_VNEXT = CONVERSATION_COMPACT_OUTPUT_SCHEMA_VERSION_VNEXT`，并在验证点中 grep 确认无硬编码 `"conversation_compact_output_v1"` 字符串字面量出现在 compaction.py 中。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 002-unfixed-low-公共 smoke 未显式验证 runtime material JSON 中 instruction.output_schema_name
- **位置**: Affected Files - Tests `tests/host/test_public_compact_smoke.py`
- **问题类型**: 测试缺口
- **当前写法**: plan 在 test_public_compact_smoke.py 中要求"assert the final runtime material JSON has `instruction.output_schema_name == conversation_compact_output_v1`"和"assert `json.dumps(...)` does not contain `ConversationCompactOutputVNext`"。
- **反例/失败场景**: 当前 test_public_compact_smoke.py 已有 `_FORBIDDEN_COMPACTOR_PROMPT_TERMS` 检查 prompt template 文本，但 runtime material JSON 的 instruction 字段检查是新增的。如果实现 agent 仅在 `test_compaction_contract.py` 和 `test_llm_compaction.py` 中添加了 instruction literal 断言，但遗漏了 public smoke 中的 runtime material JSON instruction 断言，则 public smoke 路径仍可能未被验证。plan 将此列为 R1-S2 而非 R1-S1，说明它是可选的"proving"步骤。
- **为什么有问题**: success signal 要求"Public smoke tests assert the final runtime material JSON is clean, not only the packaged prompt template"。如果 public smoke 只检查 prompt template 不含 forbidden terms（已有检查），而不检查 runtime material JSON 中的 `instruction.output_schema_name`，则 success signal 的关键部分未被测试覆盖。
- **直接证据**: `tests/host/test_public_compact_smoke.py:95-101` — `_FORBIDDEN_COMPACTOR_PROMPT_TERMS` 只检查 prompt template 文本，不解析 runtime material JSON 的 instruction 字段。
- **影响**: 审查者无法通过 public smoke 测试确认 runtime material JSON 确实已清理。
- **建议改法和验证点**: plan 应将 runtime material JSON instruction literal 断言明确放入 R1-S2 的 exact allowed changes，而非仅作为 R1-S1 的附属。验证点应包含：运行 `pytest tests/host/test_public_compact_smoke.py -q` 后，至少一个 test 函数名包含"material"或"instruction"且 assert `instruction.output_schema_name == "conversation_compact_output_v1"`。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 003-unfixed-low-design.md section 24.3 使用无版本后缀类名
- **位置**: Design Alignment - Required design sync
- **问题类型**: 最佳实践偏离
- **当前写法**: plan 要求"Update `docs/host/design.md` section 24.3 so `CompactInstruction.output_schema_name` uses `conversation_compact_output_v1`"
- **反例/失败场景**: design.md section 24.3 当前写的是 `CompactInstruction`（无 VNext 后缀），而代码中类名是 `CompactInstructionVNext`。plan 更新 design 时，如果实现 agent 只修改 literal 值而不统一类名引用，design 和 code 的命名仍然不一致。
- **为什么有问题**: 项目约束"若概念已改名，必须全量清理旧名，禁止新旧术语并存"。虽然 VNext 后缀在此 plan scope 外，但 design.md 已使用无后缀名，而代码使用有后缀名——这是 pre-existing 不一致。plan 应至少明确此为 non-goal，避免实现 agent 误以为需要同时重命名。
- **直接证据**: `docs/host/design.md:2830-2832` — `CompactInstruction` 无后缀；`dayu/host/compaction.py:685` — `CompactInstructionVNext` 有后缀。
- **影响**: 实现 agent 可能在 design sync 时做超出 scope 的类名重命名，引入不必要的 diff。
- **建议改法和验证点**: plan 应在 Non-goals 中明确"Do not rename `CompactInstruction` to `CompactInstructionVNext` in design.md section 24.3; naming consistency between design doc and code is a pre-existing issue outside this work unit scope"。验证点：design.md diff 只涉及 `output_schema_name` literal 和相邻说明文字。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Open Questions

无 blocking open questions。

## Residual Risks

1. **Optional real-provider compact smoke remains environment-dependent**: Owner: WU-CM-01-F01 Slice 7 public smoke closeout。分类：已由后续 approved slice 覆盖。
2. **Internal class names remain in Python code**: `ConversationCompactOutputVNext` 作为 Python dataclass 名和 type 名仍在代码、类型系统和 developer docs 中。Owner: non-goal for this work unit。
3. **Historical review artifacts mention old literal**: 旧 blocker artifacts 和 review docs 中的 `ConversationCompactOutputVNext` 引用不会被清理。Owner: non-goal。

## Plan Review Conclusion

**pass-with-risks**

Plan 正确识别了 root cause（runtime material JSON 中的内部类型名），选择了最小可维护的修复路径（替换 constant value 而非移除字段），设计 sync scope 合理，slice 边界清晰，测试覆盖方向正确。三个 findings 均为低严重度，不构成 blocker，但建议在实现前明确以避免实现 agent 的歧义选择。

关键验证：实现后必须通过 `pytest tests/host/test_compaction_contract.py tests/host/test_llm_compaction.py tests/host/test_public_compact_smoke.py -q` 和 `pyright`，且 `grep -r "ConversationCompactOutputVNext" dayu/host/compaction.py` 应无匹配（确认 constant 值已替换）。
