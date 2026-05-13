# Host Phase 1 Phase Design Review

## Review Gate

phase design review

## Reviewed Target

- `docs/reviews/gateflow-phase-design-host-p1-codex-20260513.md`（AgentCodex Phase 1 design refinement artifact）
- Working tree diff of `dayu/README.md`、`docs/host/design.md`、`docs/host/implementation-control.md`
- Design truth source: `docs/host/design.md`
- Implementation control: `docs/host/implementation-control.md`
- Cross-reference: `dayu/contracts/tool_declaration.py`、`dayu/contracts/__init__.py`、`dayu/runtime/__init__.py`、`tests/engine/test_import_boundary.py`

## Reviewer

AgentDS

## Reviewer Conclusion

**Fix status update（2026-05-13）**：Controller accepted Finding 1-4 均需在当前 phase design fix gate 修复；AgentCodex 已按 controller 裁决完成修复，等待 re-review。

Phase 1 的核心判断——Host API public typing 放 `dayu.host`、`ToolBundle` 留在 `dayu.contracts`、ToolsDiscovery/ScenePrepare 后置——均经 direct evidence 验证成立，且与分层架构、已有 Engine import boundary 测试、`dayu.contracts` 实际导入关系一致。`dayu.host` 尚未存在，Phase 1 创建它是合理的 foundation work，不会引入反向依赖风险——Engine 已有 `tests/engine/test_import_boundary.py` 的 AST 扫描防线（`ENGINE_CORE_FORBIDDEN_PREFIXES` 包含 `dayu.host`）。

三个文档的术语、Phase 1 范围已在 refinement 后高度收敛。原 review 识别出的 tracking section 滞后、`FrameworkToolPolicyView` typed shape、`ToolBundleSourceRef.source_kind` 类型表达与 Phase 1 退出条件问题，已按 controller 裁决在当前 fix gate 修复。

## Findings

### Finding 1. 已修复：`FrameworkToolPolicyView` 缺少 typed shape 定义

**严重性**：high —— 阻塞 implementation-ready plan 生成。若无此定义，implementation agent 必须自行做 material implementation choice，违反 "phase discussion/plan 阶段消除 material open question" 的工作流约束。

**证据**：

- `docs/host/design.md:526-536` 在 `HostToolingOptions` text shape 中使用了 `framework_tool_policy: FrameworkToolPolicyView`，但未定义该类型的任何字段、枚举或约束。
- `docs/reviews/gateflow-phase-design-host-p1-codex-20260513.md:66` 声明 "`FrameworkToolPolicyView` 在 Phase 1 只需要覆盖 framework tool reserved-name / enablement 的 typed policy view"，但同样没有给出 typed shape。
- `docs/host/design.md:540-568` 的 `HostPolicyProviderSet` 列出了 `ToolGovernancePolicyView` 作为 policy view 之一，但 `FrameworkToolPolicyView` 与 `ToolGovernancePolicyView` 的关系未定义——是独立 view、子集还是别名。
- `docs/host/implementation-control.md` Slice 3 只列了 "framework tool reserved-name policy view" 作为交付物名称，没有 shape 约束。
- 全仓库 `FrameworkToolPolicyView` 仅在 `design.md:529`、`codex-20260513.md:66` 和 `mimo-20260513.md:32,95` 中出现，没有任何 `.py` 实现、typed fields 定义或 enum 约束。

**问题**：implementation agent 在 Phase 1 Slice 3 需要自行决定：(a) reserved name 集合用什么 Python 类型表达（`frozenset[str]` / `tuple[str, ...]` / `enum.StrEnum`）；(b) enablement 语义是白名单、黑名单还是默认启用+显式禁用；(c) Phase 1 是否实现 policy resolution 逻辑，还是只定义 dataclass skeleton；(d) 与 `ToolGovernancePolicyView` 的关系。这四个问题都是 material implementation choices。

**要求**：在 `docs/host/design.md` §10.1 或 §18.1 中补充 `FrameworkToolPolicyView` 的 minimum typed shape。最小可接受定义至少包含：
- reserved framework tool name 集合类型与默认值（当前已知 reserved name 为 `fetch_more`）。
- enablement 语义（例如 `enabled: frozenset[str]` 或 `disabled: frozenset[str]`）及默认行为。
- Phase 1 scope：只定义 typed dataclass/frozen class，还是需要实现 resolution 逻辑。
- 与 `ToolGovernancePolicyView` 的关系（独立 view / 子集 / 后续合并目标）。

**Controller decision status**: accepted-fixed-by-codex-20260513

---

### Finding 2. 已修复：implementation-control.md "当前状态" 段滞后

**严重性**：low —— 不阻塞设计，但影响后续 agent 对工作流位置的判断。

**证据**：

- `docs/host/implementation-control.md:1242-1269` "当前状态" 段仍描述 P0 PR gate 状态，包括 P0 plan re-review 通过、P0-S1/S2 implementation slices 完成、push/PR 阶段。
- 当前实际 gate 为 Phase 1 phase design review（由 `$planreview` 启动）。P0 已完成。
- Phase 1 design refinement（Codex artifact）已完成，但 "当前状态" 段未提及。
- 文档自身声明 "当前阶段为 P0"（line 1244），与实际不一致。

**问题**：后续 agent 或人类读者读取此段时会误判当前工作流阶段为 P0 PR gate。

**要求**：在 phase design review 通过后更新 "当前状态" 段，反映：(a) P0 已完成并进入 PR；(b) Phase 1 design refinement 已完成；(c) 当前 gate 为 Phase 1 phase design review；(d) Phase 1 ready for phase plan gate 的前置条件状态。

**Controller decision status**: accepted-fixed-by-codex-20260513

---

### Finding 3. 已修复：`ToolBundleSourceRef.source_kind` Python 类型表达未决

**严重性**：low —— 不阻塞 design gate，但应在 phase plan 中明确。

**证据**：

- `docs/host/design.md:531-533` 定义 `source_kind: explicit_provider | config_binding | package_entrypoint | service_composition`，使用 text spec 风格的枚举值。
- 未说明 Python 实现中使用 `enum.Enum`、`typing.Literal` 还是 `str` 常量。
- `source_kind` 预期用于 Attempt snapshot、audit 和 diagnostic 解释（design.md:538），这意味着它需要稳定序列化和比较语义，这些语义因 Python 类型选择而异。

**问题**：implementation agent 需要做 material implementation choice。`enum.StrEnum` 提供 exhaustiveness check 和稳定序列化，推荐但需 design doc 明确。

**要求**：在 phase plan 中明确 `source_kind` 的 Python 类型表达。推荐 `enum.StrEnum` 以获得 exhaustiveness check、稳定 `str()` 序列化和类型安全比较，但最终选择由 controller 裁决。

**Controller decision status**: accepted-fixed-by-codex-20260513

---

### Finding 4. 已修复：Phase 1 退出条件缺乏可验证的验收标准

**严重性**：low —— 不阻塞当前 gate，但可能导致后续 plan review 与 phase closeout 产生分歧。

**证据**：

- `docs/host/implementation-control.md:337` 退出条件为 "后续 Host phase 可以只依赖 typed contract，不需要自行发明 request、snapshot、status、runtime helper 或 `ToolBundle` construction input"。
- "不需要自行发明" 是主观判断。例如，Phase 2（Durable Store）是否"自行发明"了 EventLog row 类型？如果 Phase 1 只提供公共 API 类型而不提供 durable row 类型，Phase 2 是否需要"自行发明"？边界模糊。
- 对比 Phase 0 的退出条件（"Engine overflow event 明确表达 reactive fallback 与 unknown budget，provider overflow path 使用 `budget_state=None`"），该条件是精确可验证的。

**问题**：Phase 2 implementation agent 和 Phase 1 review agent 可能对 "不需要自行发明" 的边界有不同解读。

**要求**：在 phase plan 中将退出条件细化为可验证的验收标准列表，明确：(a) Phase 1 必须产出的 typed contract 清单（哪些模块/类型必须存在）；(b) 明确的 non-goals（哪些类型留给后续 phase 自行定义是合法的）；(c) 通过的测试和 pyright 检查。建议格式："以下 typed contract 存在且通过 pyright 与对应测试：`dayu.host` 下的 request/snapshot/status/error 类型、`dayu.runtime.lane`、`dayu.runtime.filelock`、`HostToolingOptions`/`ToolBundleSourceRef`/`FrameworkToolPolicyView`"。此 finding 不阻塞当前 gate，可在 phase plan 中处理。

**Controller decision status**: accepted-fixed-by-codex-20260513

---

## Additional Observations (Non-Findings)

以下观察不构成独立 finding，但值得 controller 在后续 gate 中关注：

1. **`FrameworkToolPolicyView` 与 `HostPolicyProviderSet` 的关系**：`design.md:553-558` 列出 `ToolGovernancePolicyView` 作为 `HostPolicyProviderSet` 解析出的 typed policy view，但 `FrameworkToolPolicyView` 不在该列表中。两者可能是同一类型的不同名称，也可能是独立类型。如果 `FrameworkToolPolicyView` 是 `ToolGovernancePolicyView` 的 Phase 1 subset，应在 design doc 中显式声明关系。此点已由 Finding 1 的修复覆盖。

2. **Phase 1 deferred items 的追踪区归属**：`implementation-control.md:218` 要求每个 phase 的 deferred risk 回写到追踪区。Phase 1 的 "后续依赖" 字段已包含 ToolsDiscovery/ScenePrepare 后置和 FrameworkToolPolicyView 细化的追踪信息，但追踪区独节没有 Phase 1 相关条目。当前 Phase 1 条目自身足够追踪，但建议在 Phase 1 closeout 时确认是否需要独立追踪区条目——特别是如果 ToolsDiscovery/ScenePrepare 后置涉及跨 phase 依赖链。

3. **`dayu.runtime` 包初始化 import 边界**：当前 `dayu/runtime/__init__.py` 的 docstring 已声明不得 import `dayu.host` 等上层包（line 9-11）。当 Phase 1 创建 `dayu.host` 后，应在 `tests/runtime/test_import_boundary.py` 中添加 `dayu.host` 的禁止导入检查，与 Engine 的 import boundary 测试保持同等防御强度。此点属于 Phase 1 implementation detail，不阻塞 design gate。

## Open Questions and Residual Risks

### Blocking Open Questions

无。Finding 1 的 `FrameworkToolPolicyView` typed shape material design gap 已由当前 fix gate 关闭。

### Non-Blocking Open Questions

1. **`dayu.host` 包的初始模块拆分**：Phase 1 需要创建 `dayu/host/` 包。具体模块拆分（`requests.py`/`snapshots.py`/`status.py`/`errors.py` vs `public_types.py`）和 `__all__` 导出边界属于 phase plan 决策，不影响当前 design gate。与 AgentMiMo review 结论一致。

2. **`dayu.runtime.lane` 的具体实现方式**：`design.md:66` 定义了 lane 的语义边界（named semaphore，可取消），但未指定实现（`asyncio.Semaphore`、第三方库、或自行实现）。Phase 1 plan 需要确认选择，但设计层面层中立边界已明确。与 AgentMiMo review 结论一致。

3. **`FrameworkToolPolicyView` Phase 1 resolution 逻辑边界**：已由 Finding 1 fix 决策。Phase 1 定义 frozen dataclass 风格的 construction-time framework-tool policy view，不实现 ToolRuntime policy resolution 或 framework tool 注入逻辑。

### Residual Risks

1. **`HostToolingOptions` typed shape 只覆盖 construction-time 最小集**：后续多 scene tool profile、profile registry、tool snapshot durability 与 source ref digest 算法仍需在 ToolRuntime / command path 相关 phase 细化。已在 Codex refinement 和 design doc 中一致记录，风险可控。

2. **Host public API 类型模块拆分未定**：具体模块拆分、`__all__` 导出边界和测试矩阵仍需在 implementation-ready plan 中列为可审查 slice。已在 Codex refinement 中记录，风险可控。

3. **ToolsDiscovery / ScenePrepare 后置的边界约束可验证性**：当前 design doc 规定 "这些能力若需要代码实现，必须作为独立后续 phase 进入 design refinement"，但未定义 Phase 1 退出时如何验证这些边界约束（例如是否需要 import boundary 测试）。建议在 Phase 1 plan 中加入最小验证：确认 `dayu.host` 不 import 具体业务工具模块、不持有 scene manifest parser。低风险。

---

## Artifact Path

`docs/reviews/gateflow-phase-design-review-host-p1-ds-20260513.md`
