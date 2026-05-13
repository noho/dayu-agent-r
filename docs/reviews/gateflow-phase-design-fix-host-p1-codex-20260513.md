# Host Phase 1 Phase Design Fix

## Work Gate

phase design fix

## Work Unit

Host Phase 1 公共契约与 runtime 基础设施。

## Source Review Artifacts

- `docs/reviews/gateflow-phase-design-review-host-p1-mimo-20260513.md`
- `docs/reviews/gateflow-phase-design-review-host-p1-ds-20260513.md`

## Accepted Finding IDs

- Finding 1: `FrameworkToolPolicyView` 缺少 typed shape。
- Finding 2: `docs/host/implementation-control.md` 当前状态段滞后。
- Finding 3: `ToolBundleSourceRef.source_kind` Python 类型表达未决。
- Finding 4: Phase 1 退出条件缺乏可验证验收标准。

## Per-Finding Fix Status

### Finding 1: 已修复

- 在 `docs/host/design.md` 的 `HostToolingOptions` 附近补充 minimum typed shape。
- `FrameworkToolPolicyView` 明确为 frozen dataclass 风格类型，最小字段为：
  - `reserved_framework_tool_names: frozenset[FrameworkToolName]`
  - `enabled_framework_tools: frozenset[FrameworkToolName]`
- 明确 reserved names 用于禁止业务 `ToolBundle` 占用 Host framework tool 名称；enabled framework tools 只表达 construction-time policy view。
- 明确 Phase 1 不实现 ToolRuntime policy resolution、framework tool 注入逻辑或完整工具治理策略。
- 明确 `FrameworkToolPolicyView` 是独立 construction-time framework-tool policy view，不是完整 `ToolGovernancePolicyView`；后续 ToolRuntime / Tool Governance phase 可以消费或并入更完整的 `ToolGovernancePolicyView`。

### Finding 2: 已修复

- 更新 `docs/host/implementation-control.md` 的 `当前状态` 段。
- 当前状态不再声明“当前阶段为 P0”或“当前 gate 为 PR”。
- 现状态明确：P0 implementation 与 review loop 已完成，后续进入 push / PR 路径；当前工作为 Phase 1 phase design review / fix gate；在 re-review 前不进入 phase plan、implementation、commit、PR 或 closeout。

### Finding 3: 已修复

- `ToolBundleSourceKind` 明确为 Python 3.11 `enum.StrEnum`，成员值为：
  - `explicit_provider`
  - `config_binding`
  - `package_entrypoint`
  - `service_composition`
- `FrameworkToolName` 明确为 Python 3.11 `enum.StrEnum`，当前成员至少包含：
  - `fetch_more`
- Controller 补充裁决已写入 `docs/host/design.md`：`ToolBundleSourceKind` 与 `FrameworkToolName` 不得实现为普通 `str` 常量或 `typing.Literal`。
- `docs/host/implementation-control.md` Phase 1 退出条件也写入同一 `enum.StrEnum` 要求。

### Finding 4: 已修复

- `docs/host/implementation-control.md` Phase 1 退出条件已改为可验证清单。
- 清单覆盖：
  - `dayu.host` 公共 API typed contracts。
  - `HostToolingOptions` / `ToolBundleSourceRef` / `ToolBundleSourceKind` / `FrameworkToolName` / `FrameworkToolPolicyView`。
  - `dayu.runtime.lane` 与 `dayu.runtime.filelock` import boundary。
  - unit tests、pyright、docs 同步要求。
  - Phase 1 non-goals：SQLite store、Host command path、Engine execution path、ToolRuntime policy resolution / framework tool injection、ToolsDiscovery / ScenePrepare adapter、manifest schema、业务工具扫描、财报场景 prompt。

## Changed Files

- `dayu/README.md`
- `docs/host/design.md`
- `docs/host/implementation-control.md`
- `docs/reviews/gateflow-phase-design-host-p1-codex-20260513.md`
- `docs/reviews/gateflow-phase-design-review-host-p1-mimo-20260513.md`
- `docs/reviews/gateflow-phase-design-review-host-p1-ds-20260513.md`
- `docs/reviews/gateflow-phase-design-fix-host-p1-codex-20260513.md`

## Validation Commands And Results

- `git diff --check`
  - Result: passed, no whitespace errors.

未运行 pyright；当前 gate 只允许文档级 phase design fix，且本轮未修改生产代码。

## New Risks / Open Questions

Blocking questions: 0.

新增 material risk: 无。

Non-blocking follow-up:

- Phase 1 implementation-ready plan 仍需决定 `dayu.host` 初始模块拆分、`__all__` 导出边界和测试文件布局。
- `dayu.runtime.lane` 的具体实现方式仍属于 Phase 1 implementation-ready plan 决策；当前 design 只固定层中立语义和可验证退出条件。

## Residual Risk Classification

- 后续 phase 覆盖：多 scene tool profile、profile registry、tool snapshot durability、source ref digest 算法。
- 后续 phase 覆盖：ToolsDiscovery / ScenePrepare 具体 adapter、manifest schema、provider 注册生命周期和业务装配代码。
- 当前 phase plan 覆盖：`dayu.host` 模块拆分、runtime helper 实现策略、测试矩阵。
- 当前 gate 已修复：`FrameworkToolPolicyView` typed shape、当前状态段、`ToolBundleSourceKind` / `FrameworkToolName` Python 类型表达、Phase 1 可验证退出条件。

## Finding Title Status Update Result

- `docs/reviews/gateflow-phase-design-review-host-p1-mimo-20260513.md`
  - Finding 1 title updated to `已修复`。
  - Finding 2 title updated to `已修复`。
  - Finding 3 title updated to `已修复`。
  - Finding 4 title updated to `已修复`。
  - `Controller decision status` updated to `accepted-fixed-by-codex-20260513` for all four findings.
- `docs/reviews/gateflow-phase-design-review-host-p1-ds-20260513.md`
  - Finding 1 title updated to `已修复`。
  - Finding 2 title updated to `已修复`。
  - Finding 3 title updated to `已修复`。
  - Finding 4 title updated to `已修复`。
  - `Controller decision status` updated to `accepted-fixed-by-codex-20260513` for all four findings.

## Ready For Re-Review

是。

## Artifact Path

`docs/reviews/gateflow-phase-design-fix-host-p1-codex-20260513.md`
