# WU-TOOL-02 Plan Re-Review (AgentMiMo)

## 复核范围

- Plan artifact: `docs/host/wu-tool-02-accept-candidate-cleanup-plan.md`（plan fix 后版本）
- Source review: `docs/reviews/wu-tool-02-plan-review-mimo-20260602.md`
- DS review: `docs/reviews/wu-tool-02-plan-review-ds-20260602.md`
- Controller adjudication: `docs/reviews/wu-tool-02-plan-review-controller-adjudication-20260602.md`
- Gate: plan re-review

## 复核结论

**Plan re-review pass。** 全部 accepted findings 已关闭，plan 仍 handoff-ready，不引入新 blocking issue。

## Finding 逐一复核

### DS Finding 01 — Slice 1 与 Slice 2 的 tool_runtime.py 同文件修改存在顺序冲突

**Controller 裁决**: accepted。要求重排或合并 slices。

**Plan fix 验证**:

- Slice 1 已重写为"新增子结构与局部 validation helper"（line 229），Non-goals 第一条明确"不改变 `ToolFactAcceptCandidate` 当前顶层字段"（line 237），第三条明确"不迁移 ToolRuntime executor producer"（line 239）。
- Slice 1 步骤 3 明确"保持现有 `ToolFactAcceptCandidate` 顶层字段、现有 producer、现有 accept barrier consumer 和现有 tests 不变，避免同文件中间态类型失败"（line 248）。
- Slice 2 已重写为"组合根、producer、accept barrier consumer 与核心 tests 一次性迁移"（line 264），一次性完成组合根变更、producer 迁移、accept barrier consumer 迁移和核心 tests 迁移。
- Slice 2 预期断言包含"pyright 通过"的隐含要求（验证命令包含 pyright）。

**关闭状态**: 已关闭。Slice 1 只新增子结构定义和局部 helper，不改变现有类型；Slice 2 一次性完成组合根 + producer + consumer + tests 迁移。Implementation agent 不会遇到"Slice 1 pyright 失败但 non-goals 说不该改 producer"的困境。

---

### MiMo Finding 1 — `ToolFactKind.LOST` 校验规则未显式声明

**Controller 裁决**: accepted。要求在 fact kind 规则或 stop condition 中补充 LOST 不在支持范围。

**Plan fix 验证**:

- Plan "Fact Kind 字段归属与校验规则" 章节新增 "Unsupported: `LOST`" 小节（line 140-144），明确三点：LOST 当前不在 `ToolFactAcceptCandidate` 支持范围内；validation 必须继续 fail-fast；未来若需要必须另行设计。
- Slice 1 步骤 4 补充"明确 `ToolFactKind.LOST` 仍不接入新 helper 的 supported candidate 语义，未来另行设计"（line 249）。
- Slice 2 步骤 2 补充"组合根 / fact-kind validator 校验 ordinary result、reuse、plain governed error、duplicate governed error 和 unsupported `LOST`"（line 282）。
- Slice 2 预期断言补充"`ToolFactKind.LOST` candidate 仍 fail-fast，不产生新 payload 或 EventLog"（line 303）。

**关闭状态**: 已关闭。LOST 的 fail-fast 语义在 fact kind 规则、Slice 1 和 Slice 2 中均有显式声明。

---

### MiMo Finding 2 — `ToolAcceptResult` payload_ref/payload_digest 一致性约束措辞与当前代码不完全对齐

**Controller 裁决**: accepted。要求调整措辞，不新增等值校验。

**Plan fix 验证**:

- `ToolAcceptResult` 约束已重写（line 53）："本 work unit 不借结构拆分新增 payload digest 校验语义；`payload_ref` 存在时保持当前 descriptor 存在性校验与当前已有 candidate 校验，不扩大为新的等值规则或新持久化约束。"
- 原措辞"有 `payload_ref` 时 `payload_digest` 必须与 `payload_ref.payload_digest` 一致"已删除。

**关闭状态**: 已关闭。措辞准确描述当前行为，明确不引入新校验语义。

---

### DS Finding 02 — `ToolAcceptDiagnostics` 单字段子结构可能过度分解

**Controller 裁决**: deferred-to-implementation-discretion。要求在 plan 中保留职责边界要求，补充 implementation agent 可把单字段 diagnostics 保留为组合根直接字段。

**Plan fix 验证**:

- `ToolAcceptDiagnostics` 说明已补充（line 72）："该结构可保留以维持职责分组；implementation agent 也可在不破坏职责分组、类型边界和测试可读性的前提下，把单字段 diagnostics 保留为组合根的直接字段。"

**关闭状态**: 已关闭。Implementation discretion 已清楚。

---

### DS Finding 03 — Slice 4 旧字段残留检测 rg 命令存在覆盖盲区

**Controller 裁决**: accepted。要求补充 pyright 是主要证明，rg 只是辅助。

**Plan fix 验证**:

- Slice 4 步骤 4 已重写（line 376）："以 pyright 作为旧顶层字段迁移的主要证明；`rg` 只作为辅助检查，不能替代类型检查。"
- 补充说明："允许命中 EventLog payload 字符串、docstring、子结构字段和非 `ToolFactAcceptCandidate` 对象；需要人工判读。"

**关闭状态**: 已关闭。pyright 为主要证明、rg 为辅助的定位已明确。

---

### DS Finding 04 — Validation 分解粒度未明确

**Controller 裁决**: accepted。要求补充分解原则。

**Plan fix 验证**:

- Plan "Proposed Typed Structure" 章节新增 "Validation 分解原则"（line 89-93），明确三条：
  1. 子结构 `__post_init__` 只校验本结构内部 invariant。
  2. 跨子结构约束和 fact-kind 约束必须由组合根或专门 fact-kind validator 校验。
  3. 错误消息、helper 命名和检查顺序可按实现局部代码质量调整，但不得改变现有语义。

**关闭状态**: 已关闭。分解原则足够具体，不绑定实现细节。

---

### DS Finding 05 — Fact Kind 校验规则章节过细节

**Controller 裁决**: accepted。要求补充该章节表达语义约束，不是逐行实现模板。

**Plan fix 验证**:

- "Fact Kind 字段归属与校验规则" 章节开头新增声明（line 97）："本章节表达语义约束和验收边界，不是逐行实现模板。Implementation agent 可以在保持语义不变、测试覆盖完整和 pyright 通过的前提下调整 validator 组织、错误消息与检查顺序。"

**关闭状态**: 已关闭。

---

## Plan Fix 引入新 Issue 检查

| 检查项 | 结果 |
|---|---|
| Slice 重排是否引入新的中间态类型失败风险 | 否。Slice 1 不改变现有类型，Slice 2 一次性迁移。 |
| Validation 分解原则是否过度约束实现 | 否。原则只约束 invariant 归属，不绑定具体 helper 命名或错误消息。 |
| LOST 章节是否过度扩展 scope | 否。只声明 fail-fast，不引入新语义。 |
| `ToolAcceptDiagnostics` implementation discretion 是否引入歧义 | 否。明确"不破坏职责分组、类型边界和测试可读性"的前提条件。 |
| Slice 2 合并范围是否过大 | 否。组合根 + producer + consumer + 核心 tests 属于同一可验证闭环，pyright 是最终证明。 |

## Handoff Readiness 复核

Plan fix 后仍 handoff-ready。Implementation agent 可按更新后的 slices 直接执行，不需要重新设计结构边界、字段归属、file ownership 或测试矩阵。
