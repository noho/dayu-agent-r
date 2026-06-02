# WU-TOOL-02 Plan Re-review — AgentDS

## 审查范围

- Plan artifact (fixed): `docs/host/wu-tool-02-accept-candidate-cleanup-plan.md`
- 原始 DS review: `docs/reviews/wu-tool-02-plan-review-ds-20260602.md`
- MiMo review: `docs/reviews/wu-tool-02-plan-review-mimo-20260602.md`
- Controller adjudication: `docs/reviews/wu-tool-02-plan-review-controller-adjudication-20260602.md`

## Finding 关闭确认

### DS-01: Slice 1/2 同文件修改顺序冲突 → CLOSED

Controller 裁决: 重排 slices — Slice 1 只新增子结构不改组合根，Slice 2 一次性原子迁移。

Plan fix 验证:
- Slice 1 标题改为"新增子结构与局部 validation helper"，non-goals 明确"不改变 `ToolFactAcceptCandidate` 当前顶层字段"、"不迁移 accept barrier consumer"、"不迁移 ToolRuntime executor producer"、"不迁移 tests"。
- Slice 1 步骤 3："保持现有 `ToolFactAcceptCandidate` 顶层字段、现有 producer、现有 accept barrier consumer 和现有 tests 不变，避免同文件中间态类型失败。"
- Slice 1 验证命令 `pyright dayu/host/tool_runtime.py` 在旧结构仍完整的情况下可通过（新子结构是独立 dataclass 定义，未被任何代码引用）。
- Slice 2 合并了原 Slice 1+2 的迁移动作：步骤 1 迁移组合根、步骤 3-4 迁移 producer、步骤 5 迁移 accept barrier consumer、步骤 7-9 迁移 tests。这些修改在同一 slice 内原子完成，结束时 pyright 通过。

中间态风险已消除。Slice 1 不产生 broken state；Slice 2 可独立验证闭环。

### DS-02: ToolAcceptDiagnostics 单一字段过度分解 → CLOSED

Controller 裁决: deferred-to-implementation-discretion。

Plan fix 验证:
- `ToolAcceptDiagnostics` 描述新增说明："该结构可保留以维持职责分组；implementation agent 也可在不破坏职责分组、类型边界和测试可读性的前提下，把单字段 diagnostics 保留为组合根的直接字段。"

Implementation agent 有明确裁量权，不再阻塞。

### DS-03: Slice 4 rg 命令覆盖盲区 → CLOSED

Controller 裁决: accepted, 补充 pyright 为主要证明。

Plan fix 验证:
- Slice 4 步骤 4 改写为："以 pyright 作为旧顶层字段迁移的主要证明；`rg` 只作为辅助检查，不能替代类型检查。"
- 辅助 rg 命令扩展为完整字段名列表。
- 明确说明"允许命中 EventLog payload 字符串、docstring、子结构字段和非 `ToolFactAcceptCandidate` 对象；需要人工判读。"

工具局限性已被承认，verification strategy 可信。

### DS-04: Validation 分解粒度未明确 → CLOSED

Controller 裁决: accepted, 补充分解原则。

Plan fix 验证:
- 新增"Validation 分解原则"章节（Proposed Typed Structure 与 Fact Kind 规则之间），三条规则：
  1. 子结构 `__post_init__` 只校验内部 invariant
  2. 跨子结构约束在 `ToolFactAcceptCandidate` 组合根校验
  3. 错误消息、命名和检查顺序可调整，语义不变
- Slice 1 步骤 2 明确只新增"内部 invariant 校验"
- Slice 2 步骤 2 明确"组合根 / fact-kind validator 校验"跨子结构约束

分解原则有具体落地位置，implementation agent 不会面临决策真空。

### DS-05: Fact Kind 校验规则过细节 → CLOSED

Controller 裁决: accepted, 补充非模板声明。

Plan fix 验证:
- Fact Kind 章节开头新增："本章节表达语义约束和验收边界，不是逐行实现模板。Implementation agent 可以在保持语义不变、测试覆盖完整和 pyright 通过的前提下调整 validator 组织、错误消息与检查顺序。"

Implementation agent 不会被逐行措辞绑死。

### MiMo-1: ToolFactKind.LOST 校验规则缺失 → CLOSED

Controller 裁决: accepted。

Plan fix 验证:
- 新增"### Unsupported: `LOST`" 子章节：
  - 声明 `LOST` 不在 `ToolFactAcceptCandidate` 支持范围
  - 要求现有 validation 继续 fail-fast
  - 未来如需 LOST candidate 必须另行设计
- Slice 1 步骤 4："明确 `ToolFactKind.LOST` 仍不接入新 helper 的 supported candidate 语义"
- Slice 2 步骤 2：fact-kind validator 包含 "unsupported `LOST`"
- Slice 2 预期断言："`ToolFactKind.LOST` candidate 仍 fail-fast，不产生新 payload 或 EventLog"

Implementation agent 不会误为 LOST 新增语义。

### MiMo-2: payload_ref/payload_digest 一致性约束措辞 → CLOSED

Controller 裁决: accepted, 调整措辞不引入新校验。

Plan fix 验证:
- `ToolAcceptResult` 约束改写为："本 work unit 不借结构拆分新增 payload digest 校验语义；`payload_ref` 存在时保持当前 descriptor 存在性校验与当前已有 candidate 校验，不扩大为新的等值规则或新持久化约束。"

措辞精确描述当前行为，不会诱导 implementation agent 引入新校验。

## 切片可验证性复查

| Slice | 修改范围 | 中间态风险 | 可独立验证 |
|-------|---------|-----------|-----------|
| Slice 1 | 仅新增子结构 dataclass + 未接入的 helper | 无 — 旧结构完整保留，新类型未被引用 | ✓ pyright + pytest(旧) |
| Slice 2 | 组合根 + producer + consumer + tests 原子迁移 | 无 — 同一 slice 内完成全部迁移 | ✓ pyright + pytest 覆盖 changed files |
| Slice 3 | duplicate/diagnostics tests 读取路径 | 依赖 Slice 2 完成组合根迁移 | ✓ |
| Slice 4 | payload consumer regression tests | 依赖 Slice 2 完成 EventLog payload 路径 | ✓ |
| Slice 5 | aggregate verification | 依赖 Slice 1-4 全部完成 | ✓ |

所有 slice 在 plan 约束下可独立验证。Slice 2-5 依赖 Slice 2 完成组合根迁移，此为正常的前后 slice handoff，不属于中间态 broken state。

## 新风险检查

无新增 blocking issue。Plan fix 未引入:
- 新的 public API 泄漏
- 新的兼容 facade 或 re-export
- 新的设计 doc 偏离
- 新的 slice 边界模糊
- 新的未覆盖 stop condition 场景

## 结论

**Plan re-review pass。**

DS Findings 01-05 全部关闭；MiMo Findings 1-2 全部关闭。Plan fix 正确回应了 controller adjudication 的全部 7 项裁决，未被接受的 change 被正确地 deferred-to-implementation-discretion 并给予明确裁量指引。

Plan 仍 handoff-ready 且 code-generation-ready。Implementation agent 可以按更新后的 slices 直接执行。
