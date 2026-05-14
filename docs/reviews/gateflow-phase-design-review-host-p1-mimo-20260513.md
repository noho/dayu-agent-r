# Host Phase 1 Phase Design Review

## Review Gate

phase design review

## Reviewed Target

- `docs/reviews/gateflow-phase-design-host-p1-codex-20260513.md`（Phase 1 design refinement artifact）
- Working tree diff of `dayu/README.md`、`docs/host/design.md`、`docs/host/implementation-control.md`
- Design truth source: `docs/host/design.md`
- Implementation control: `docs/host/implementation-control.md`

## Reviewer

AgentMiMo

## Reviewer Conclusion

**Fix status update（2026-05-13）**：Controller accepted Finding 1-4 均需在当前 phase design fix gate 修复；AgentCodex 已按 controller 裁决完成修复，等待 re-review。

Phase 1 的动机成立且未被高估或低估。把 Host API public typing 放到 `dayu.host` 而非 `dayu.contracts` 符合 `UI -> Service -> Host -> Engine` 分层——Engine 不应 import Host 治理语义类型，而 `dayu.contracts` 会被 Engine 导入。ToolsDiscovery / ScenePrepare 后置合理，不会破坏 Phase 1 退出条件。原 review 识别出的 `FrameworkToolPolicyView` typed shape、总控文档当前状态、`ToolBundleSourceRef.source_kind` 类型表达与 Phase 1 退出条件问题，已按 controller 裁决在当前 fix gate 修复。

## Findings

### Finding 1. 已修复：`FrameworkToolPolicyView` 缺少 typed shape 定义

**严重性**：medium —— 阻塞 implementation-ready plan 生成。

**证据**：

- `docs/host/design.md:523-536` 定义了 `HostToolingOptions` 的 text shape，其中包含 `framework_tool_policy: FrameworkToolPolicyView`。
- `docs/reviews/gateflow-phase-design-host-p1-codex-20260513.md:66` 声明 "`FrameworkToolPolicyView` 在 Phase 1 只需要覆盖 framework tool reserved-name / enablement 的 typed policy view"。
- 但 `design.md` 中没有任何位置给出 `FrameworkToolPolicyView` 的具体字段、枚举或约束。
- `implementation-control.md` Slice 3 只列了 "framework tool reserved-name policy view"，没有定义 shape。

**问题**：implementation agent 在生成 Slice 3 时需要自行决定 `FrameworkToolPolicyView` 的字段、reserved name 列表的表达方式（enum / frozenset / Mapping）、enablement 的默认策略等 material implementation choices。这违反了 phase design review 前应消除 material open question 的工作流约束。

**要求**：在 `docs/host/design.md` §10.1 或 §18.1 中补充 `FrameworkToolPolicyView` 的最小 typed shape，至少明确：

- reserved name 集合的表达形式（`frozenset[str]` / `tuple[str, ...]` / typed enum）。
- enablement 的语义（白名单 / 黑名单 / 默认启用+显式禁用）。
- Phase 1 是否需要实现 policy resolution 逻辑，还是只定义 typed view dataclass。

**Controller decision status**: accepted-fixed-by-codex-20260513

---

### Finding 2. 已修复：implementation-control.md "当前状态" 段滞后

**严重性**：low —— 不阻塞设计，但影响后续 agent 对工作流状态的判断。

**证据**：

- `docs/host/implementation-control.md:1244-1269`（working tree）"当前状态" 段仍描述 P0 的 PR gate、plan re-review、implementation slices、code review artifacts 和 commits。
- 当前实际 gate 是 Phase 1 phase design review（由 `$planreview` 启动），P0 已完成并进入 PR。
- 该段未提及 Phase 1 design refinement 已完成、当前应进入 phase design review。

**问题**：后续 agent 读取此段时会误判当前工作流阶段为 P0 PR gate，而非 Phase 1 phase design review。

**要求**：在 phase design review 通过后、进入 user confirmation 前更新"当前状态"段，反映 Phase 1 design refinement 已完成、当前 gate 为 Phase 1 phase design review。

**Controller decision status**: accepted-fixed-by-codex-20260513

---

### Finding 3. 已修复：`ToolBundleSourceRef.source_kind` 使用文字枚举而非 typed enum

**严重性**：low —— 不阻塞设计，但 implementation-ready plan 中需要明确是 Python enum 还是 Literal type。

**证据**：

- `docs/host/design.md:530` 定义 `source_kind: explicit_provider | config_binding | package_entrypoint | service_composition`。
- 这是 text spec 中的枚举值，但未说明在 Python 实现中使用 `enum.Enum`、`typing.Literal` 或 `str` 常量。

**问题**：implementation agent 需要做 material implementation choice。

**要求**：在 design.md 或 phase plan 中明确 `source_kind` 的 Python 类型表达方式。推荐 `enum.Enum` 以获得 exhaustiveness check，但应由设计文档决策而非 implementation agent 现场决定。

**Controller decision status**: accepted-fixed-by-codex-20260513

---

### Finding 4. 已修复：Phase 1 退出条件过于宽泛

**严重性**：low —— 不阻塞当前 gate，但可能导致后续 plan review 产生分歧。

**证据**：

- `docs/host/implementation-control.md:337`（working tree）退出条件为 "后续 Host phase 可以只依赖 typed contract，不需要自行发明 request、snapshot、status、runtime helper 或 `ToolBundle` construction input"。
- 此条件没有量化或可验证的验收标准。"不需要自行发明" 是主观判断，没有具体列出哪些 typed contract 必须存在。

**问题**：Phase 2（Durable Store）和 Phase 4（Public API Command Path）依赖 Phase 1 的 typed contract，但退出条件没有明确 Phase 1 必须产出哪些具体类型模块。

**建议**：在 phase plan 中把退出条件细化为 "以下 typed contract 存在且通过 pyright / 测试：`dayu.host` 下的 request / snapshot / status / error 类型、`dayu.runtime.lane`、`dayu.runtime.filelock`、`HostToolingOptions` / `ToolBundleSourceRef` / `FrameworkToolPolicyView`"。此 finding 不阻塞当前 gate，可在 phase plan 中处理。

**Controller decision status**: accepted-fixed-by-codex-20260513

---

## Open Questions and Residual Risks

### Non-blocking Open Questions

1. **`dayu.host` 包的初始结构**：Phase 1 需要创建 `dayu/host/` 包。具体模块拆分（如 `requests.py` / `snapshots.py` / `status.py` / `errors.py` vs 单模块 `public_types.py`）和 `__all__` 导出边界属于 implementation plan 阶段决策，不阻塞设计 review。

2. **`FrameworkToolPolicyView` 与 `HostPolicyProviderSet` 的关系**：已由 Finding 1 fix 解决；`FrameworkToolPolicyView` 是独立 construction-time framework-tool policy view，不是完整 `ToolGovernancePolicyView`，后续 ToolRuntime / Tool Governance phase 可以消费或并入更完整的 policy view。

3. **`dayu.runtime.lane` 第三方依赖选择**：`design.md:66` 定义了 lane 的语义边界但未指定实现方式（`asyncio.Semaphore` / `aiosqlite` based / 第三方 named semaphore 库）。Phase 1 plan 需要确认选择，但设计层面的层中立边界已足够明确。

### Residual Risks

1. **`HostToolingOptions` typed shape 只覆盖 construction-time 最小集**：后续多 scene tool profile、profile registry、tool snapshot durability 与 source ref digest 算法仍需在 ToolRuntime / command path 相关 phase 细化。此风险已在 refinement artifact 中记录，设计文档一致。

2. **Host public API 类型模块拆分未定**：具体模块拆分、`__all__` 导出边界和测试矩阵仍需在 implementation-ready plan 中列为可审查 slice。此风险已在 refinement artifact 中记录。

3. **ToolsDiscovery / ScenePrepare 后置的边界约束强度**：当前设计文档只说"这些能力若需要代码实现，必须作为独立后续 phase 进入 design refinement"，但没有定义 Phase 1 退出时这些边界约束的验证方式（例如是否需要 import boundary 测试或 lint rule）。低风险，可在 phase plan 中决定。

---

## Artifact Path

`docs/reviews/gateflow-phase-design-review-host-p1-mimo-20260513.md`
