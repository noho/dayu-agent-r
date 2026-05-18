# Phase 10 Slice 2 Code Review — AgentMiMo

Reviewer: AgentMiMo
Date: 2026-05-18
Scope: Slice 2 compaction contracts, quality checker, compact artifact store, fake compactor, tests, README sync

## Verdict

**PASS**

## Summary

Slice 2 实现严格遵循计划要求：typed contracts 无 `Any`/`object`/untyped bag，pinned patch 三态语义清晰，quality checker 覆盖全部计划要求的拒绝场景，compact artifact store 只写 artifact + descriptor 不写 EventLog，fake compactor 明确限定为测试/本地注入，README 与测试同步且充分。发现 1 个 medium 和 3 个 low 级别问题，无 blocking/high 问题。

## Findings

### Medium

**M1. `CompactionRequest.__post_init__` 对 `current_message_summary` 的 isinstance 校验晚于属性访问**

- 文件: `dayu/host/compaction.py:202` vs `dayu/host/compaction.py:209`
- 第 202 行访问 `self.current_message_summary.current_user_input_ref` 做 `in` 检查，但 `isinstance(self.current_message_summary, CurrentMessageSummary)` 校验在第 209 行才执行。
- 若传入非 `CurrentMessageSummary` 且无 `current_user_input_ref` 属性的对象（如 `int`），会抛 `AttributeError` 而非计划预期的 `TypeError`。
- 影响范围有限：(1) 所有 dataclass 均有类型注解，pyright 会静态警告；(2) 此为 Host 内部 typed boundary，非公共 API；(3) frozen dataclass 不会在运行时强制字段类型。
- 建议：将第 209–212 行的 isinstance 校验移到第 202 行之前，保证错误类型符合 docstring 承诺的 `TypeError`。

### Low

**L1. `_require_string_tuple` 对空字符串元素抛 `ValueError` 但消息与 tuple 级 `TypeError` 一致**

- 文件: `dayu/host/compaction.py:900`
- `_require_non_empty` 抛 `ValueError`，但错误消息格式沿用上级 `field_name`，未区分是"元素为空"还是"tuple 本身类型非法"。
- 不影响正确性，但可能使调用方难以区分具体是哪个元素违规。优先级低，不影响 Slice 2 功能。

**L2. `CompactQualityCheckResult.to_json` 使用列表推导中间变量**

- 文件: `dayu/host/compaction.py:828–831`
- `[_enum_value for _enum_value in self._rejection_reason_values()]` 可简化为直接调用 `self._rejection_reason_values()`，因该方法已返回 `list[JsonValue]`。
- 不影响功能，纯代码风格。

**L3. `compact_artifact.py` 中 `_require_optional_non_empty` 与 `compaction.py` 中同名函数重复定义**

- 文件: `dayu/host/compact_artifact.py:321–331` vs `dayu/host/compaction.py:872–882`
- 两个模块各自定义了相同的 `_require_optional_non_empty` 私有辅助函数。
- 当前不违反编码约束（模块级私有辅助函数），但若后续扩展可能产生维护分歧。优先级低。

### Info

**I1. `FakeContextCompactor` 的 `budget_after_compact` 使用硬编码减半逻辑**

- 文件: `dayu/host/fake_compaction.py:92–94`
- `max(0, request.budget_before_compact.estimated_input_tokens // 2)` 是 deterministic fake 行为，不反映真实 compact 效果。
- 这是预期的：fake compactor 的职责是产生稳定可测 candidate，不模拟真实 token 节省。测试已验证 quality check 通过。

## Positive Observations

1. **Typed contracts严格**: 全部 dataclass 使用 `frozen=True, slots=True`，无 `Any`/`object`/无类型参数。`PinnedPatchOperation` StrEnum 的 `MISSING`/`CLEAR`/`REPLACE` 三态语义清晰，与计划 "未出现表示不修改，空值表示显式清空，非空值表示替换" 完全对应。
2. **Quality checker 覆盖完整**: 计划要求的 6 项拒绝场景全部实现且有对应测试：missing current input、missing tool fact refs、summary pretends verified fact、missing evidence、evidence anchor not retained、pinned patch tri-state invalid + evidence ref missing。
3. **Artifact store 边界清晰**: `write_compact_artifact` 只写 artifact bytes + payload descriptor，不写 EventLog。canonical JSON 包含计划要求的全部字段。expected digest 失败时 `HostDigestMismatchError` 在 descriptor 写入前抛出，测试确认 descriptor count 为 0。
4. **Fake compactor 隔离正确**: 模块 docstring 明确 "生产默认路径不得隐式使用"，不在任何 production 默认路径中被导入。
5. **README 同步准确**: `dayu/host/README.md` 新增 "Context Governance Boundary" 章节记录当前已实现边界；`tests/README.md` 补充了 Context Governance 测试覆盖事实与新增测试命令。
6. **测试充分**: 13 个测试覆盖 fake compactor 基本功能、6 种 quality rejection、artifact store descriptor/digest 写入、canonical fields 验证、corrupted digest 拒绝、unaccepted quality result 拒绝、descriptor 回读。

## Residual Risks

1. **Slice 3+ 接入 canonical events 时需保持 summary 不升格 verified fact**: 当前 quality checker 已实现此约束，后续 slice 的 memory projection 消费 `CONTEXT_COMPACTED` 时必须继续执行此规则。
2. **Real LLM compactor scene adapter 未实现**: 当前只有 `FakeContextCompactor`；production wiring 需在 Slice 6 显式提供 `ContextCompactor` 实现或 fail closed。
3. **`CompactionRequest.__post_init__` 校验顺序 (M1)**: 若后续有人绕过 pyright 传入错误类型，AttributeError 可能误导调试。建议在后续 commit 中调整顺序。
