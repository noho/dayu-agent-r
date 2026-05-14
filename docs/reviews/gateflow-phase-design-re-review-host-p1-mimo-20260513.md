# Host Phase 1 Phase Design Re-Review

## Review Gate

phase design re-review

## Reviewed Target

- Fix artifact: `docs/reviews/gateflow-phase-design-fix-host-p1-codex-20260513.md`
- Source review artifact: `docs/reviews/gateflow-phase-design-review-host-p1-mimo-20260513.md`
- Cross-source review artifact: `docs/reviews/gateflow-phase-design-review-host-p1-ds-20260513.md`
- Updated docs: `dayu/README.md`、`docs/host/design.md`、`docs/host/implementation-control.md`

## Reviewer

AgentMiMo

## Reviewer Conclusion

四个 controller-accepted findings 均已修复。fix 未引入新的 blocker、范围漂移、术语不一致或 implementation agent 仍需现场做的 material design choice。Phase 1 可进入 phase plan gate。

## Per-Finding Re-Review Result

### Finding 1. `FrameworkToolPolicyView` typed shape — Fixed

**Fix claim**: `FrameworkToolPolicyView` 明确为 frozen dataclass 风格类型，最小字段为 `reserved_framework_tool_names: frozenset[FrameworkToolName]` 与 `enabled_framework_tools: frozenset[FrameworkToolName]`。

**Evidence verification**:

- `docs/host/design.md:548-551` 定义了 typed shape：
  ```text
  @dataclass(frozen=True, slots=True)
  FrameworkToolPolicyView
    reserved_framework_tool_names: frozenset[FrameworkToolName]
    enabled_framework_tools: frozenset[FrameworkToolName]
  ```
- `docs/host/design.md:556-558` 明确 `FrameworkToolPolicyView` 是独立 construction-time framework-tool policy view，不是完整 `ToolGovernancePolicyView`；后续 ToolRuntime / Tool Governance phase 可以消费或并入更完整的 policy view。
- `docs/host/implementation-control.md:339` 写入同一 frozen dataclass shape 要求。
- `docs/host/design.md:532-533` 定义 `FrameworkToolName(StrEnum)`，当前成员至少包含 `FETCH_MORE = "fetch_more"`，reserved name 集合的 Python 类型已明确。
- `docs/host/design.md:523` 明确 Phase 1 scope：只定义 typed view dataclass，不实现 ToolRuntime policy resolution 或 framework tool 注入逻辑。

**评估**：fix 完整消除了原 finding 识别的四个 material implementation choices：(a) reserved name 集合类型为 `frozenset[FrameworkToolName]`；(b) enablement 语义为 `enabled_framework_tools` 白名单风格；(c) Phase 1 只定义 frozen dataclass，不实现 resolution 逻辑；(d) 与 `ToolGovernancePolicyView` 的关系为独立 construction-time view，后续可并入。implementation agent 无需做 material design choice。

**Result**: Fixed.

---

### Finding 2. `implementation-control.md` 当前状态段 — Fixed

**Fix claim**: 更新 "当前状态" 段，不再声明 "当前阶段为 P0" 或 "当前 gate 为 PR"。

**Evidence verification**:

- `docs/host/implementation-control.md:1249-1255` "当前状态" 段内容：
  - P0 已完成并进入 push / PR 路径（line 1251）。
  - 当前工作为 Phase 1（line 1253）。
  - Phase 1 design refinement 已完成并有 fix artifact（line 1253）。
  - 当前 gate 为 Phase 1 phase design review / fix gate（line 1253）。
  - 明确 re-review 前不进入后续 gate（line 1253）。
  - 列出进入 phase plan gate 的前置条件（line 1255）。

**评估**：段落准确反映当前工作流位置。不再包含 P0 PR gate 的过时信息。

**Result**: Fixed.

---

### Finding 3. `ToolBundleSourceRef.source_kind` Python 类型表达 — Fixed

**Fix claim**: `ToolBundleSourceKind` 明确为 Python 3.11 `enum.StrEnum`；`FrameworkToolName` 同样明确为 `enum.StrEnum`。Controller 补充裁决写入 design.md。

**Evidence verification**:

- `docs/host/design.md:526-531` 定义 `ToolBundleSourceKind(StrEnum)`，成员为 `EXPLICIT_PROVIDER`、`CONFIG_BINDING`、`PACKAGE_ENTRYPOINT`、`SERVICE_COMPOSITION`。
- `docs/host/design.md:532-533` 定义 `FrameworkToolName(StrEnum)`，成员至少包含 `FETCH_MORE`。
- `docs/host/implementation-control.md:338` 退出条件写入 "必须使用 Python 3.11 `enum.StrEnum`，不得使用普通 `str` 常量或 `typing.Literal`"。
- `docs/host/design.md:543` `ToolBundleSourceRef.source_kind` 类型为 `ToolBundleSourceKind`，不再是文字枚举。

**评估**：fix 完整。implementation agent 不需要做 `enum.Enum` / `typing.Literal` / `str` 常量的 material choice；裁决已明确，退出条件已约束。

**Result**: Fixed.

---

### Finding 4. Phase 1 退出条件 — Fixed

**Fix claim**: 退出条件改为可验证清单。

**Evidence verification**:

- `docs/host/implementation-control.md:337-344` 新退出条件为结构化清单：
  - Host public API typed contracts 列表（line 337）。
  - Host construction typed contracts 列表，含具体类型名（line 338）。
  - `ToolBundleSourceKind` 与 `FrameworkToolName` 的 `enum.StrEnum` 要求（line 338）。
  - `FrameworkToolPolicyView` 的 frozen dataclass shape 要求（line 339）。
  - `dayu.runtime.lane` / `dayu.runtime.filelock` 的层中立 import boundary 要求（line 340）。
  - unit tests 覆盖范围（line 341）。
  - pyright 要求（line 342）。
  - docs 同步要求（line 343）。
  - 明确 non-goals 列表（line 344）。

**评估**：退出条件从主观判断（"不需要自行发明"）改为客观可验证清单。每项均有明确的验收标准，Phase 2 implementation agent 和 Phase 1 review agent 不会产生边界分歧。

**Result**: Fixed.

---

## New Blockers

无。

## Open Questions / Residual Risk

无新增。原 review 的 non-blocking open questions（`dayu.host` 模块拆分、`dayu.runtime.lane` 实现方式、`FrameworkToolPolicyView` Phase 1 resolution 逻辑边界）均已在 fix 中明确或保持为 phase plan 决策项，不阻塞当前 gate。

## Artifact Path

`docs/reviews/gateflow-phase-design-re-review-host-p1-mimo-20260513.md`
