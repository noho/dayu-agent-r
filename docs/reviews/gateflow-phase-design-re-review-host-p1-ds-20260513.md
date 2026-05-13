# Host Phase 1 Phase Design Re-Review

## Review Gate

phase design re-review

## Reviewed Target

- Fix artifact: `docs/reviews/gateflow-phase-design-fix-host-p1-codex-20260513.md`
- Source review artifact: `docs/reviews/gateflow-phase-design-review-host-p1-ds-20260513.md`
- Cross-source review artifact: `docs/reviews/gateflow-phase-design-review-host-p1-mimo-20260513.md`
- Updated docs: `dayu/README.md`, `docs/host/design.md`, `docs/host/implementation-control.md`

## Reviewer

AgentDS（re-review）

## Re-Review Scope

仅复查 controller-accepted findings 1-4 及其 fixes。不重做全量 design review；仅在 fix 引入明显新 blocker 时报告。

## Per-Finding Re-Review Result

### Finding 1: Fixed — `FrameworkToolPolicyView` typed shape

**Original concern**：implementation agent 需要自行决定 (a) reserved name 集合的 Python 类型；(b) enablement 语义；(c) Phase 1 是否实现 policy resolution；(d) 与 `ToolGovernancePolicyView` 的关系。

**Fix evidence**：

- `docs/host/design.md:548-552` 明确定义 `FrameworkToolPolicyView` 为 `@dataclass(frozen=True, slots=True)`，字段 `reserved_framework_tool_names: frozenset[FrameworkToolName]` 与 `enabled_framework_tools: frozenset[FrameworkToolName]`。
- `docs/host/design.md:556-558` 明确：(c) Phase 1 只定义 frozen dataclass，不实现 ToolRuntime 注入或完整工具治理策略；(d) `FrameworkToolPolicyView` 是独立 construction-time framework-tool policy view，不是完整 `ToolGovernancePolicyView`，后续 phase 可消费或并入。
- `docs/host/implementation-control.md:339` 退出条件中写入同一 typed shape 要求。

All four original material design choices are resolved.

**Verdict**: **Fixed**。无新 blocker。

---

### Finding 2: Fixed — implementation-control.md "当前状态" 段滞后

**Original concern**："当前状态" 段仍描述 P0 PR gate，未反映当前实际 Phase 1 gate。

**Fix evidence**：

- `docs/host/implementation-control.md:1251` 明确 P0 已完成，进入 push/PR 路径，不再是当前 gate。
- `docs/host/implementation-control.md:1253` 明确当前工作为 Phase 1，当前 gate 为 phase design review/fix gate；声明在 re-review 前不进入后续 gate。
- `docs/host/implementation-control.md:1255` 明确 Phase 1 进入 phase plan 的前置条件。
- 旧 "当前阶段为 P0" 表述已清除。

**Verdict**: **Fixed**。无新 blocker。

---

### Finding 3: Fixed — `ToolBundleSourceRef.source_kind` 与 `FrameworkToolName` Python 类型表达

**Original concern**：`source_kind` 枚举值用 text spec 表达，未说明 Python 实现类型。`FrameworkToolName` 无类型决策。

**Fix evidence**：

- `docs/host/design.md:526-533` 以 text spec 定义 `ToolBundleSourceKind(StrEnum)` 四成员与 `FrameworkToolName(StrEnum)`，当前成员 `FETCH_MORE`。
- `docs/host/design.md:556` 明确两者必须使用 Python 3.11 `enum.StrEnum`，不得实现为 `str` 常量或 `typing.Literal`。
- `docs/host/implementation-control.md:338` 退出条件写入同一 `enum.StrEnum` 硬约束。

**Verdict**: **Fixed**。无新 blocker。

---

### Finding 4: Fixed — Phase 1 退出条件可验证性

**Original concern**："不需要自行发明" 是主观判断，缺乏可验证的验收标准。

**Fix evidence**：

- `docs/host/implementation-control.md:337-344` 退出条件已细化为 8 条可验证标准：
  1. 具体 typed contracts 清单，含类型名与导入命名空间。
  2. Host construction typed contracts 清单，含 `enum.StrEnum` 硬约束。
  3. `FrameworkToolPolicyView` 最小字段与 Phase 1 scope 边界。
  4. `dayu.runtime.lane` / `dayu.runtime.filelock` 与 import boundary。
  5. unit tests 覆盖面（contract validation、ToolBundle input、reserved name 冲突、lane acquire/release、filelock wrapper）。
  6. pyright 通过。
  7. docs 同步。
  8. non-goals 明确且测试不期待这些能力。

每条均可由任意 reviewer（人或 agent）客观验证：类型是否存在、是否可导入、是否通过 pyright、测试是否覆盖指定行为。

**Verdict**: **Fixed**。无新 blocker。

---

## New Blockers

**0 个**。本轮 fixes 未引入新的 blocker、范围漂移、术语不一致或 implementation agent 仍需现场做的 material design choice。

## Cross-Verification

- 四 finding 的 typed shape / 退出条件 / 类型表达在 `docs/host/design.md` 与 `docs/host/implementation-control.md` 之间一致，无交叉矛盾。
- `dayu/README.md` 术语约定中 `lane`、`filelock`、`ToolBundle`、`ToolsDiscovery`、`ScenePrepare` 等术语与 design.md / implementation-control.md 一致。
- `FrameworkToolPolicyView` 与 `HostPolicyProviderSet` 的关系已明确：前者是 construction-time input（`HostToolingOptions` 的一部分），后者是 composition root 的 policy resolution；`ToolGovernancePolicyView` 是 `HostPolicyProviderSet` 解析出的 typed policy view，而 `FrameworkToolPolicyView` 是独立 view，后续 phase 可消费或并入。两者关系已显式声明，不构成 ambiguity。

## Open Questions / Residual Risk

### Non-Blocking

1. **`dayu.host` 模块拆分与 `__all__` 导出边界**：仍属于 Phase 1 implementation-ready plan 决策。现有 exit conditions 已提供足够的 "what must exist" 清单，plan 只需决定 "where"。
2. **`dayu.runtime.lane` 的具体实现方式**：设计层中立项已固定，implementation-ready plan 需选择方案（`asyncio.Semaphore` / 第三方 / 自实现）。此问题在原始 review 中已标记为 non-blocking，fix 后的 design doc 未引入新约束。
3. **ToolsDiscovery / ScenePrepare 后置边界的验证方式**：Phase 1 exit conditions 通过 import boundary 约束间接覆盖（`dayu.host` 不 import 具体业务工具模块），但未要求显式 import boundary 测试。此风险在原始 review 中已标记为 low，fix 后无恶化。

## Artifact Path

`docs/reviews/gateflow-phase-design-re-review-host-p1-ds-20260513.md`
