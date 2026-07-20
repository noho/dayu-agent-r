# WU-SEMANTIC-OWNERSHIP-01 R04 Plan Review — AgentMiMo

## 1. Review Identity

- **Reviewed target**: `docs/host/wu-semantic-ownership-01-r04-awaiting-provider-resolution-composition-plan.md`
- **Controller entry validation**: `docs/reviews/wu-semantic-ownership-01-r04-plan-entry-controller-validation.md`
- **Code baseline**: `f7006a80`
- **Review scope**: 完整 plan 204 行 + controller validation 45 行
- **Authority order**: AGENTS.md → `docs/host/issues-implementation-control.md` → `docs/phaseflow-umbrella-optimization-control.md` → `docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md` → `docs/host/design.md` → `docs/engine/design.md` → `docs/tool/design.md` → `docs/fins/design.md` → `docs/ui/design.md` → umbrella plan §7.3/§7.4/§7.5/§11

## 2. Assumptions Tested

| # | Assumption | Evidence | Verdict |
|---|---|---|---|
| A1 | `tool_discovery.json` 三个 Fins awaiting providers 无 `awaiting_resolution_mode` | `rg -n 'awaiting_resolution_mode' dayu` 零命中 | ✓ confirmed |
| A2 | `host_assembly.py::with_entrypoint_wait_poller_policy` 以 scene-selected tool 构造无参 `WaitPollerRuntimePolicy()` | `host_assembly.py:291` `return replace(overrides, wait_poller_policy=WaitPollerRuntimePolicy())` | ✓ confirmed |
| A3 | `entrypoint_runtime.py` 调用该 scene-derived helper | `entrypoint_runtime.py:537` `overrides=with_entrypoint_wait_poller_policy(` | ✓ confirmed |
| A4 | `host_runtime.json` 无 `wait_poller_policy` snapshot | 文件内容确认无该字段 | ✓ confirmed |
| A5 | `wait_adapter.py` 拥有 10 个部署数值 defaults 和无参 fallback | `wait_adapter.py:69-96` 10 个模块常量 + `:985,1654` 两个 `WaitPollerRuntimePolicy()` fallback | ✓ confirmed |
| A6 | `open_host` 已实现 disabled/no-policy 不启动和 enabled/no-registry fail-closed | `open_host.py:1634-1653` `_enabled_wait_poller_configuration` | ✓ confirmed |
| A7 | `OpenHostOptions.wait_poller_policy: ... | None` 是 composition 开关 | `api.py:1188` `wait_poller_policy: WaitPollerRuntimePolicy \| None = None` | ✓ confirmed |
| A8 | WU-WAIT-01 / Issue #89 存在作为 callback transport destination | `docs/host/wu-wait-01-callback-endpoint-auth-replay-plan.md` 存在，`#89` 在多处引用 | ✓ confirmed |

## 3. Findings

### 01-未修复-低-finding-`poll_interval_seconds` 字段 default 使用字面量而非模块常量

- **位置**: §2 policy snapshot 字段列表、§11.2 数值表、`dayu/host/wait_adapter.py:449`
- **问题类型**: 最佳实践偏离
- **当前写法**: plan 列出 12 个字段并要求删除模块常量；source scan 搜索 `_DEFAULT_CLAIM_BATCH_SIZE` 等 10 个常量名
- **反例/失败场景**: `poll_interval_seconds: float = 1.0` 使用字面量 `1.0` 而非模块常量 `_POLL_INTERVAL_SECONDS`（该常量不存在）。source scan 预期零命中，但该字面量 default 会在 S2 实施中被删除，因此 scan 不会遗漏。不会导致实现错误。
- **为什么有问题**: 不一致但不影响正确性。S2 要求删除所有 deployment defaults，字面量 `1.0` 同样会被删除。
- **直接证据**: `wait_adapter.py:449` `poll_interval_seconds: float = 1.0` vs 其余 11 个字段使用 `_POLL_*` 常量
- **影响**: 无实际影响；scan 命令不搜索字面量 `1.0`，但 S2 删除整个 dataclass default 层时会一并删除
- **建议改法和验证点**: 无需改 plan；实施时 S2 删除所有 field defaults 即可
- **修复风险**: 低
- **严重程度**: 低

**Status**: `no-fix` — 不影响实施正确性

---

### 02-未修复-中-`fins_wait_adapter.py::_operation_kind_from_tool_name` 结构映射是否属于"tool-name 推断"

- **位置**: §4.2 "删除 tool-name 推断"、`dayu/service/fins_wait_adapter.py:379-393`
- **问题类型**: 契约缺失
- **当前写法**: plan §4.2 说 "fins_wait_adapter 从 typed mode 精确映射 Host `WaitResumePolicy`；删除 tool-name 推断"
- **反例/失败场景**: `_operation_kind_from_tool_name` 将 `DOWNLOAD_TOOL_NAME` → `FinsOperationKind.DOWNLOAD`。这是 adapter 从 Host wait record 恢复 observation handle 时的结构性映射（tool name → Fins operation kind），不是 policy 推断。若实施 agent 把它当作"tool-name 推断"删除，adapter 无法恢复 observation handle。
- **为什么有问题**: plan 用语"删除 tool-name 推断"有歧义。`_binding_for_tool_name` 中的 `WaitResumePolicy.POLL` 硬编码是需要被 typed mode 替换的 policy 推断；`_operation_kind_from_tool_name` 是 adapter 内部的结构性映射，必须保留。
- **直接证据**: `fins_wait_adapter.py:379-393` `_operation_kind_from_tool_name` 用于 `_handle_from_snapshot`（line 369）和 `FinsIngestionWaitActivationAdapter.activate_accepted_wait`（line 225）
- **影响**: 实施 agent 可能误删结构性映射，导致 adapter 无法工作
- **建议改法和验证点**: plan §4.2 应明确区分：(1) `_binding_for_tool_name` 中的 `WaitResumePolicy.POLL` 硬编码 → 替换为 typed mode 映射；(2) `_operation_kind_from_tool_name` → 保留，它是 adapter 内部 observation handle 恢复的结构性映射
- **修复风险**: 低（plan 文本澄清即可）
- **严重程度**: 中

**Status**: `accepted-candidate` — plan 文本歧义可能导致实施 agent 误删

---

### 03-未修复-低-Host API `open_host` no-diff 声明需要更精确的停止条件

- **位置**: §5.2 "保持 `dayu/host/api.py`、`dayu/host/open_host.py` 无改动"
- **问题类型**: 契约缺失
- **当前写法**: plan 说 "如实施证据显示 public contract 必须变化，立即停止并回到 Controller，不扩 allowlist"
- **反例/失败场景**: `open_host.py:1634-1653` 已正确实现 `None → 不启动`、`disabled → 不启动`、`enabled + 缺 registry → fail-closed`。但 `WaitPollerSupervisor.__init__`（line 1639）有 `policy: WaitPollerRuntimePolicy | None = None` fallback。S2 删除该 fallback 后，`open_host.py` 构造 supervisor 时传入 `policy=configuration.policy`（line 1697），该值从 `_enabled_wait_poller_configuration` 返回，永不为 None。因此 `open_host.py` 本身确实不需要改。
- **为什么有问题**: plan 的停止条件表述正确但不够具体。实施 agent 需要知道：如果 `open_host.py` 的 `_enabled_wait_poller_configuration` 返回路径需要变化（例如新增 enabled + 缺 registry 的更细粒度错误），则必须停止。
- **直接证据**: `open_host.py:1634-1653` + `open_host.py:1685-1698`
- **影响**: 低；当前代码已满足 plan 需求
- **建议改法和验证点**: 无需改 plan；实施时验证 `_enabled_wait_poller_configuration` 的三个返回路径不变
- **修复风险**: 低
- **严重程度**: 低

**Status**: `no-fix` — 代码已验证 plan 声明正确

---

### 04-未修复-中-S2 `ServiceAssemblyOverrides.wait_poller_policy` 删除后的 composition 路径需要明确

- **位置**: §5.2 "删除 `ServiceAssemblyOverrides.wait_poller_policy`"、§6.2
- **问题类型**: 切片过粗
- **当前写法**: S2 删除 `ServiceAssemblyOverrides.wait_poller_policy`；S3 删除 `with_entrypoint_wait_poller_policy` 和 `_scene_selects_fins_awaiting_tools`
- **反例/失败场景**: `_compose_options`（`host_assembly.py:875`）读取 `request.overrides.wait_poller_policy`。S2 删除该字段后，`_compose_options` 必须改为从 ConfigLoader-derived policy 读取。但 `_compose_options` 在 `host_assembly.py` 中，属于 S3 的 allowed files（S3 允许 `dayu/service/host_assembly.py`）。S2 删除字段但不改 `_compose_options` 会导致编译错误。
- **为什么有问题**: S2 删除 `ServiceAssemblyOverrides.wait_poller_policy` 字段，但消费该字段的 `_compose_options` 在 S3 才允许修改。S2 结束后代码会处于 broken state。
- **直接证据**: `host_assembly.py:186` `wait_poller_policy: WaitPollerRuntimePolicy | None = None`、`host_assembly.py:875` `wait_poller_policy=request.overrides.wait_poller_policy`
- **影响**: S2 结束后 pyright 会报错，无法进入 S3
- **建议改法和验证点**: 方案一：把 `ServiceAssemblyOverrides.wait_poller_policy` 删除移到 S3（与 `_compose_options` 修改同步）。方案二：S2 只删除 Host policy dataclass defaults 和模块常量，保留 `ServiceAssemblyOverrides.wait_poller_policy` 字段直到 S3。推荐方案一，因为 S2 的核心目标是 config-owned policy 和 Host defaults 删除，`ServiceAssemblyOverrides` 字段删除属于 composition 收敛（S3 职责）。
- **修复风险**: 低（调整 S2/S3 边界即可）
- **严重程度**: 中

**Status**: `accepted-candidate` — S2/S3 边界需要调整以避免中间 broken state

---

### 05-未修复-低-Composition matrix 缺少 `callback + poll` 混合模式的具体行为描述

- **位置**: §6.3 composition negative matrix
- **问题类型**: 契约缺失
- **当前写法**: matrix 有 "任意 callback（单独或混合）| 无 authenticated transport | Service 在 `open_host` 前 composition error"
- **反例/失败场景**: 若一个 provider 声明 `callback`，另一个声明 `poll`，且无 transport，matrix 只说 "任意 callback → composition error"。这意味着整个 composition 失败，包括 poll provider。这是否是预期行为？
- **为什么有问题**: 用户可能期望 poll provider 正常工作，只有 callback provider 失败。但当前 matrix 表达的是"有 callback 就全部失败"。
- **直接证据**: §6.3 matrix row "任意 callback（单独或混合）| 无 authenticated transport | Service 在 `open_host` 前 composition error"
- **影响**: 低；当前产品只有 poll providers，callback 是未来能力
- **建议改法和验证点**: plan 已明确 "R04 不定义可绕过 marker"，callback 无 transport 是硬失败。这是合理的产品边界。无需改 plan，但实施 agent 应在测试中断言：有 callback mode 的 provider 存在时，即使有 poll provider，整个 composition 也失败。
- **修复风险**: 低
- **严重程度**: 低

**Status**: `no-fix` — plan 的产品边界选择合理

---

### 06-未修复-低-WU-WAIT-01 / Issue #89 的 callback transport 交付时间线

- **位置**: §3 "callback positive branch"、§6.3 matrix
- **问题类型**: open question 未收敛
- **当前写法**: plan 说 "正向 transport 装配留给既有 WU-WAIT-01 / #89"
- **反例/失败场景**: `docs/host/wu-wait-01-callback-endpoint-auth-replay-plan.md` 存在且有完整 plan，但尚未进入 implementation。如果 WU-WAIT-01 在 R04 之后很久才实施，callback mode 在实际产品中将永远触发 composition error。
- **为什么有问题**: 不是 R04 plan 的问题，但值得记录为 residual risk。R04 正确地把 callback 正向路径推迟到 WU-WAIT-01。
- **直接证据**: `docs/host/wu-wait-01-callback-endpoint-auth-replay-plan.md` 存在；`docs/host/wu-wait-04-production-awaiting-e2e-smoke-plan.md` 引用 `#89/#90/#92` 作为前置
- **影响**: 无；R04 的 callback fail-closed 是正确的产品边界
- **建议改法和验证点**: 无需改 plan；记录为 residual risk
- **修复风险**: 低
- **严重程度**: 低

**Status**: `no-fix` — residual risk 已在 umbrella plan 中追踪

---

### 07-未修复-低-S1 allowed files 包含 `fins_wait_adapter.py` 但 S1 不修改其 binding 逻辑

- **位置**: §4.1 allowed files 列表
- **问题类型**: 切片过粗
- **当前写法**: S1 allowed files 包含 `dayu/service/fins_wait_adapter.py`；S1 contract 说 "fins_wait_adapter 从 typed mode 精确映射 Host `WaitResumePolicy`"
- **反例/失败场景**: `_binding_for_tool_name`（line 342-356）在 `fins_wait_adapter.py` 中，硬编码 `WaitResumePolicy.POLL`。S1 引入 `AwaitingResolutionMode` enum 和 parser，但 `_binding_for_tool_name` 需要从 typed mode 映射 `WaitResumePolicy`。这应该在 S1 还是 S3 完成？
- **为什么有问题**: S1 的 contract 说 "fins_wait_adapter 从 typed mode 精确映射"，但 S3 的 contract 说 "删除 scene/tool-name 推断和 override 第二输入 owner"。`_binding_for_tool_name` 的 `POLL` 硬编码既是"tool-name 推断"（因为它不从 config 读 mode），也是 S1 应该修的（因为 S1 引入了 typed mode）。
- **直接证据**: `fins_wait_adapter.py:350-356` `_binding_for_tool_name` 返回 `WaitResumePolicy.POLL`；§4.1 allowed files 包含该文件
- **影响**: 低；S1 和 S3 都允许修改该文件，实施 agent 可以自行决定在哪一步改
- **建议改法和验证点**: 建议 plan 明确：S1 引入 enum/parser 并修改 `_binding_for_tool_name` 从 typed mode 映射 `WaitResumePolicy`（删除 `POLL` 硬编码）；S3 删除 scene-based composition 逻辑
- **修复风险**: 低
- **严重程度**: 低

**Status**: `accepted-candidate` — plan 边界应更明确以指导实施 agent

---

### 08-未修复-低-Source scan 预期"零命中"的表述需要区分"实施后"和"实施前"

- **位置**: §9 source scan
- **问题类型**: 最佳实践偏离
- **当前写法**: "前两项生产 source scan 预期零命中"
- **反例/失败场景**: 实施前运行 scan 会命中 `wait_adapter.py` 中的模块常量。plan 的"预期零命中"是指实施后。但 plan 没有明确说"实施后运行"。
- **为什么有问题**: 实施 agent 可能在实施前就运行 scan 并困惑于命中。
- **直接证据**: §9 "前两项生产 source scan 预期零命中"
- **影响**: 极低；实施 agent 应理解 scan 是验证步骤
- **建议改法和验证点**: 无需改 plan；上下文已足够清晰
- **修复风险**: 低
- **严重程度**: 低

**Status**: `no-fix` — 上下文足够清晰

---

### 09-未修复-低-测试验证矩阵基线 `325 passed, 3 warnings` 的可复现性

- **位置**: §7 "变更前直接基线：以下 R04 相关 collection 共 `325 passed, 3 warnings`"
- **问题类型**: open question 未收敛
- **当前写法**: plan 给出了精确的 pytest 命令和预期结果
- **反例/失败场景**: 如果环境依赖（Python 版本、包版本、NumPy）变化，基线可能不同
- **为什么有问题**: 不是 plan 的问题；基线是时间点快照
- **直接证据**: §7 pytest 命令和预期结果
- **影响**: 无
- **建议改法和验证点**: 实施时重新运行确认
- **修复风险**: 低
- **严重程度**: 低

**Status**: `no-fix` — 基线是时间点快照，实施时重新验证

---

### 10-未修复-中-ConfigLoader `WaitPollerRuntimePolicyConfig` 是否需要新增 `wait_poller_policy` 字段到 `HostRuntimeProfileConfig`

- **位置**: §5.2 "ConfigLoader 新增 frozen、全字段必填的 layer-neutral `WaitPollerRuntimePolicyConfig`，并作为 `HostRuntimeProfileConfig.wait_poller_policy` required 字段"
- **问题类型**: 架构边界
- **当前写法**: plan 要求 ConfigLoader 新增 `WaitPollerRuntimePolicyConfig` 并作为 `HostRuntimeProfileConfig` 的 required 字段
- **反例/失败场景**: `HostRuntimeProfileConfig` 当前没有 `wait_poller_policy` 字段。新增 required 字段意味着旧的 `host_runtime.json`（没有该字段）会无法加载。但 plan 明确说 "fresh schema 直接使用新布局，不兼容旧布局"，所以这是预期行为。
- **为什么有问题**: 不是问题；plan 正确要求 fresh schema。但实施 agent 需要同时更新 `host_runtime.json` 和 ConfigLoader，否则任何测试都无法运行。
- **直接证据**: `dayu/config/host_runtime.json` 当前无 `wait_poller_policy`；`dayu/runtime/config_loader.py` 的 `HostRuntimeProfileConfig` 当前无该字段
- **影响**: S2 必须同时更新 `host_runtime.json` 和 ConfigLoader，不能分步
- **建议改法和验证点**: plan 已覆盖；实施 agent 应在同一个 commit 中同时更新两者
- **修复风险**: 低
- **严重程度**: 中

**Status**: `no-fix` — plan 已覆盖，实施 agent 需理解 atomic 更新要求

---

### 11-未修复-低-Coverage 替换方案（单一 `--cov=dayu`）的边界

- **位置**: §3 "umbrella 多 dotted-module `--cov`"、§7
- **问题类型**: 最佳实践偏离
- **当前写法**: plan 用单一 `--cov=dayu --cov-report=json` 替代多 dotted-module `--cov`，从 JSON 逐文件读取覆盖率
- **反例/失败场景**: NumPy double-load 限制是已证实的工具限制。替换方案语义等价。
- **为什么有问题**: 不是问题；替换方案已验证可运行
- **直接证据**: §3 "该替换已直接运行通过"
- **影响**: 无
- **建议改法和验证点**: 无需改 plan
- **修复风险**: 低
- **严重程度**: 低

**Status**: `no-fix` — 已验证的等价替换

---

### 12-未修复-低-`_fins_awaiting_tool_name_from_provider_config` 在 S1 后是否需要修改

- **位置**: §4.2、`dayu/service/host_assembly.py:2048-2076`
- **问题类型**: 架构边界
- **当前写法**: S1 引入 `AwaitingResolutionMode` enum 和 parser；provider config 新增 `awaiting_resolution_mode` 字段
- **反例/失败场景**: `_fins_awaiting_tool_name_from_provider_config` 通过 provider ID/import_path/source_id 识别 Fins awaiting providers。S1 后，provider config 有了 `awaiting_resolution_mode` 字段，但该函数不读取它。函数仍然通过 ID 识别 provider，这是正确的——mode 字段是配置内容，provider 识别是装配逻辑。
- **为什么有问题**: 不是问题。函数的职责是"识别是否是 Fins awaiting provider"，不是"读取 mode"。mode 读取由 parser 完成。
- **直接证据**: `host_assembly.py:2048-2076`
- **影响**: 无
- **建议改法和验证点**: 无需改 plan
- **修复风险**: 低
- **严重程度**: 低

**Status**: `no-fix` — 职责分离正确

## 4. Open Questions

| # | Question | Evidence needed | Blocking? |
|---|---|---|---|
| Q1 | S2 删除 `ServiceAssemblyOverrides.wait_poller_policy` 是否应在 S3 完成？ | 见 Finding 04 | 是 — S2 结束后 pyright 会报错 |
| Q2 | `_operation_kind_from_tool_name` 是否被 plan 的"删除 tool-name 推断"覆盖？ | 见 Finding 02 | 否 — 但 plan 文本应澄清 |
| Q3 | `_binding_for_tool_name` 的 `POLL` 硬编码应在 S1 还是 S3 修改？ | 见 Finding 07 | 否 — 两步都允许修改该文件 |

## 5. Residual Risks

| Risk | Destination |
|---|---|
| callback 正向 transport 交付时间线 | WU-WAIT-01 / Issue #89 |
| `host_runtime.json` fresh schema 与旧 workspace 不兼容 | 预期行为；R04 不做兼容读取 |
| NumPy double-load 对 coverage 工具的限制 | 已用等价替换解决 |

## 6. Final Plan Review Conclusion

**Verdict**: `pass-with-risks`

**Summary**: R04 plan 在 owner 唯一性、三 slice 闭环、composition matrix、callback fail-closed、typed propagation、12-field policy、default/fallback 删除范围、manual/poll registry、scene independence、测试/coverage/pyright/README/scans/smoke、security/deferred boundary 等方面设计合理且基于直接代码证据。

**Blocking findings**: 1 个
- **Finding 04** (中): S2 删除 `ServiceAssemblyOverrides.wait_poller_policy` 字段会导致 S2 结束后 pyright 报错，因为消费该字段的 `_compose_options` 在 S3 才允许修改。建议把该字段删除移到 S3。

**Non-blocking accepted candidates**: 2 个
- **Finding 02** (中): plan "删除 tool-name 推断" 文本歧义，应区分结构性映射和 policy 推断
- **Finding 07** (低): `_binding_for_tool_name` 的 `POLL` 硬编码修改归属 S1/S3 边界应更明确

**No-fix observations**: 9 个（Findings 01, 03, 05, 06, 08, 09, 10, 11, 12）

**Blocking questions**: 1 个（Q1 — S2/S3 边界调整）

**Overall assessment**: plan 是 code-generation-ready 的，只需调整 S2/S3 边界（Finding 04）和澄清两处文本歧义（Findings 02, 07）即可安全交给 implementation agent。

---

**Output file**: `docs/reviews/wu-semantic-ownership-01-r04-plan-review-mimo.md`
**Generated**: 2026-07-15T17:27:01+08:00
