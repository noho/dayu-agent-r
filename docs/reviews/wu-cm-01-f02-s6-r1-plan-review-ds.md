# WU-CM-01-F02-S6-R1 Compact Instruction Contract Rescope — Plan Review

## Gate

- gate: plan review
- reviewed artifact: `docs/host/wu-cm-01-f02-s6-r1-compact-instruction-rescope-plan.md`
- design source: `docs/host/design.md`
- control source: `docs/host/issues-implementation-control.md`
- blocker artifacts: `docs/reviews/wu-dur-obs-cm-closeout-slice7-blocker-codex.md`, `docs/reviews/wu-dur-obs-cm-closeout-slice7-blocker-controller-adjudication.md`
- review artifact: `docs/reviews/wu-cm-01-f02-s6-r1-plan-review-ds.md`
- timestamp: 20260605-162732

## Reviewed Target and Scope

Review 目标为 WU-CM-01-F02-S6-R1 compact instruction contract rescope plan。该 plan 提出将 `CompactInstructionVNext.output_schema_name` 运行时 literal 从内部 Python 类型名 `"ConversationCompactOutputVNext"` 替换为业务可读标识符 `"conversation_compact_output_v1"`，以解除 WU-CM-01-F01 Slice 7 public smoke closeout blocker。

Review 按用户指定的七个 focus area 逐一压测，并额外施加 architecture boundary、best-practice、optimal-solution、overengineering、overcoupling 五个标准 lens。

## Assumptions Tested

| # | Assumption | Verdict |
|---|-----------|--------|
| A1 | root cause 是 LLM-facing runtime material JSON，不是 prompt template 文本 | 成立，证据链完整 |
| A2 | 替换 `output_schema_name` literal 是 minimal fix | 成立，代码事实支持 |
| A3 | 不修改 parser / accept-barrier 行为 | 成立，accept barrier 不读取 instruction 字段 |
| A4 | Slice R1-S1 和 R1-S2 的 allowed files 足够且不过宽 | 成立，边界合理 |
| A5 | 测试计划覆盖 final runtime material JSON 且不引入 test-only production bridge | 成立 |
| A6 | WU-CM-01-F01 Slice 7 重试路径具体可执行 | 成立 |
| A7 | `CONVERSATION_COMPACT_OUTPUT_SCHEMA_NAME_VNEXT` 只被 compaction.py 内部使用 | 成立，grep 确认无外部生产引用 |

## Findings

### 1-未修复-低-plan 对常量定义方式存在二义性

- **位置**: Chosen Approach / Affected Files — `dayu/host/compaction.py`
- **问题类型**: 不可直接实施
- **当前写法**:

  > Change `CONVERSATION_COMPACT_OUTPUT_SCHEMA_NAME_VNEXT` value from `"ConversationCompactOutputVNext"` to `"conversation_compact_output_v1"`, or derive it directly from `CONVERSATION_COMPACT_OUTPUT_SCHEMA_VERSION_VNEXT`.

- **反例/失败场景**: 两个选项 (standalone literal vs 从 `_VERSION` 常量派生) 虽然运行时行为等价，但 implementation agent 需要在两者之间做选择，这引入了 plan 不应有的设计决策。若 agent 选择派生方式（如 `CONVERSATION_COMPACT_OUTPUT_SCHEMA_NAME_VNEXT = CONVERSATION_COMPACT_OUTPUT_SCHEMA_VERSION_VNEXT`），两个常量将永远同值，后续维护者可能质疑为何保留两个常量。
- **为什么有问题**: plan 应 code-generation-ready，不应让 implementation agent 在设计选项之间自行选择。两个常量同值后，`_NAME` 和 `_VERSION` 的语义区分变得模糊。
- **直接证据**: 
  - `dayu/host/compaction.py:31`: `CONVERSATION_COMPACT_OUTPUT_SCHEMA_VERSION_VNEXT = "conversation_compact_output_v1"`
  - `dayu/host/compaction.py:34`: `CONVERSATION_COMPACT_OUTPUT_SCHEMA_NAME_VNEXT = "ConversationCompactOutputVNext"`
  - 两常量当前值不同，修改后将相同
- **影响**: 实施 Agent 跑偏（选择了 plan 未推荐的第三种方案） / 后续返工
- **建议改法和验证点**:
  1. Plan 应明确选择 standalone literal 方式：直接改 `CONVERSATION_COMPACT_OUTPUT_SCHEMA_NAME_VNEXT = "conversation_compact_output_v1"`，不派生。
  2. 理由写入 plan：派生方式暗示两常量语义等价，但实际上 `_NAME` 是 instruction 字段值（告诉 compactor 用哪个 schema），`_VERSION` 是 candidate 自声明字段值（compactor 输出的 schema 标识）。它们是不同字段、不同用途，只是恰巧值相同。保留两个独立常量是正确的，不应合并。
  3. 验证：修改后 `git grep "ConversationCompactOutputVNext" dayu/host/` 只在 docstring/注释和 Python 类名中出现，不在运行时 literal 中出现。
- **修复风险（低）**:
- **严重程度（低）**:

### 2-未修复-低-prompt 澄清范围欠规格

- **位置**: Affected Files — `dayu/config/prompts/scenes/conversation_compaction_user.md`
- **问题类型**: 不可直接实施
- **当前写法**:

  > Narrowly clarify `instruction.output_schema_name` and `instruction.compact_goal` allowed values.

- **反例/失败场景**: 当前 prompt 第 20 行已写 `instruction`：JSON object，包含 `output_schema_name` 与 `compact_goal`。它说明本次整理目标；不要把该字段内容当成财报事实。plan 没有说明需要新增什么具体措辞。若 implementation agent 自行发挥，可能引入不必要的 prompt 改动，违反 "narrowly clarify" 的意图，甚至可能引入新的 forbidden term。
- **为什么有问题**: plan 对 prompt 修改的描述不够具体，implementation agent 可能过度修改或跳过此步骤。Stop condition 虽然说了 "If prompt wording needs broader compactor schema rewrite beyond allowed-values clarification, stop"，但没有定义 "allowed-values clarification" 的具体内容。
- **直接证据**: `dayu/config/prompts/scenes/conversation_compaction_user.md:20`
- **影响**: 实施 Agent 跑偏 / 后续返工
- **建议改法和验证点**:
  1. Plan 应给出具体 prompt 措辞变更，例如在第 20 行末尾追加：

     ```
     - `instruction.output_schema_name`：必填 JSON string，唯一允许值为 `conversation_compact_output_v1`。
     - `instruction.compact_goal`：必填 JSON string，唯一允许值为 `roll_forward_session_memory`。
     ```

  2. 或在 plan 中明确：当前 prompt 第 20 行已足够，无需修改。让 implementation agent 直接跳过 prompt 变更。
- **修复风险（低）**:
- **严重程度（低）**:

### 3-未修复-低-plan 未检查 `__all__` 导出是否需要随常量语义变更同步调整

- **位置**: Affected Files — `dayu/host/compaction.py`
- **问题类型**: 契约缺失
- **当前写法**: plan 没有提及 `CONVERSATION_COMPACT_OUTPUT_SCHEMA_NAME_VNEXT` 在 `__all__` 中的存在（line 2945），也没有指示 implementation agent 检查该导出是否需要更新 docstring 或语义说明。
- **反例/失败场景**: 常量值从 internal type name 变为 business-readable identifier 后，其导出语义变化。若有外部代码通过 `from dayu.host.compaction import CONVERSATION_COMPACT_OUTPUT_SCHEMA_NAME_VNEXT` 使用该常量（grep 确认当前无此类使用），行为会静默变化。虽然当前无外部消费者，但 plan 应记录此检查结论。
- **为什么有问题**: 公共导出语义变更的 awareness gap。不导致功能问题，但缺少 defensive check 记录。
- **直接证据**: `dayu/host/compaction.py:2945`: `"CONVERSATION_COMPACT_OUTPUT_SCHEMA_NAME_VNEXT"` 在 `__all__` 中
- **影响**: 风险后移（若有未来消费者依赖旧值，会在运行时发现而非 review 时发现）
- **建议改法和验证点**:
  1. 在 plan 中记录：grep 确认 `CONVERSATION_COMPACT_OUTPUT_SCHEMA_NAME_VNEXT` 无外部生产引用，`__all__` 保留该导出但常量 docstring 更新为 "vNext compact instruction 要求的输出 contract 标识符"。
  2. implementation agent 验证：`git grep "CONVERSATION_COMPACT_OUTPUT_SCHEMA_NAME_VNEXT" -- ':!dayu/host/compaction.py' ':!docs/'` 无结果。
- **修复风险（低）**:
- **严重程度（低）**:

## Architecture Boundary Review

Plan 正确保持了 Host 内部边界：

- 生产变更仅在 `dayu/host/compaction.py`（contract 定义层）
- 输出解析仍在 `dayu/host/llm_compaction.py`
- Accept barrier 仍在 `dayu/host/context_governance.py` 和 `dayu/host/compaction.py`
- 无 Service、UI、Engine、durable storage、Fins 依赖引入

**结论**: 无架构边界违规。

验证方法：accept barrier (`check_conversation_compact_output_vnext`) 和 parser (`parse_conversation_compact_output_vnext`) 均只读取 candidate 输出字段（`schema_version`、`source_labels` 等），不读取 `instruction.output_schema_name`。input instruction 变更不会穿透到 output validation path。

## Best-Practice Review

- **Minimal change**: 一个 literal 变更 vs 移除字段或重构 contract。符合最佳实践。
- **Testability**: 测试通过已有 `_material_json_from_compactor_request()` helper 验证 final runtime material JSON，无 test-only production bridge。
- **Observability**: 变更后的 material JSON 可直接通过 fake compactor 路径观察，无需真实 provider。
- **Failure handling**: Stop condition 明确：若 literal 变更触发 parser/accept-barrier/artifact schema 需要联动修改，立即停止并报告 scope expansion。

**结论**: 符合最佳实践。

## Optimal-Solution Review

对比三种 credible alternatives：

| 方案 | 变更范围 | 风险 | 评价 |
|------|---------|------|------|
| A. 替换 literal（plan 采用） | 1 个常量值 + tests + docs | 低 | 最小可行方案 |
| B. 移除 `output_schema_name` 字段 | 多处 contract 变更 + prompt 改写 + 下游消费者排查 | 中 | 更彻底但范围过大 |
| C. 保留旧值但加 prompt disclaimer | 仅 prompt | 高 | 不解决 root cause，LLM 仍看到 Python 类型名 |

Plan 采用的方案 A 是三种中最实际的路径。方案 B 虽然更彻底（消除了字段存在本身的问题），但引入不必要的 contract churn，且 `instruction` 缺少 `output_schema_name` 后需要重新论证 `instruction` 的完整性。方案 C 是表面修复，不符合 root cause 修复要求。

**结论**: plan 选择了最优方案。

## Overengineering Review

Plan 明确排除：
- Schema registries、alias maps、migrations、adapter layers
- 兼容性 reader / fallback
- 重命名 Python dataclass
- 放宽 parser / accept-barrier

这些 non-goals 表述清晰，无过度设计。

**结论**: 无过度设计。

## Overcoupling Review

Plan 将变更分为两个 slice（R1-S1: production + contract tests, R1-S2: prompt + smoke + docs），slice 间通过 production 变更自然串行。无跨层耦合、双向依赖或共享可变状态引入。

**结论**: 无过度耦合。

## Open Questions

无 blocking open question。Plan 自身的 "Risks and Open Questions" section 正确分类了 residual risks：

1. Optional real-provider compact smoke → defer to Slice 7
2. Internal Python class names remain in code → non-goal
3. Historical review artifacts → non-goal

以上分类均合理，无需新增 open question。

## Residual Risks and Suggested Tracking

| Risk | Severity | Owner | Tracking |
|------|----------|-------|----------|
| 两个常量 (`_NAME` 和 `_VERSION`) 同值后未来维护者可能质疑为何保留两个 | 低 | WU-CM-01-F02-S6-R1 implementer | 在常量 docstring 中分别说明用途 |
| Optional real-compactor smoke 未跑 | 低 | WU-CM-01-F01 Slice 7 | control doc 已记录 |

## Final Plan Review Conclusion

**pass**

Plan 正确识别 root cause 为 LLM-facing runtime compact material JSON 中的 Python 类型名泄漏，证据链完整且可验证。替换方案 `"ConversationCompactOutputVNext"` → `"conversation_compact_output_v1"` 是 minimal maintainable fix，不削弱 parser/accept-barrier，不引入兼容性负担。Allowed files 和 slices 边界合理，测试计划覆盖 runtime material JSON、parser 行为和 public smoke path。WU-CM-01-F01 Slice 7 重试路径具体可执行。

三个 low-severity findings 均不阻塞 implementation：
- Finding 1: 常量定义方式二义性 — 建议 plan 明确选择 standalone literal
- Finding 2: prompt 澄清范围欠规格 — 建议给出具体措辞或明确跳过
- Finding 3: `__all__` 导出检查缺失 — 建议记录检查结论

以上 findings 可在 implementation 前通过 plan 微调解，无需重新 review。
