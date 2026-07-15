# WU-SEMANTIC-OWNERSHIP-01 R04 Final Plan Re-Review — AgentDS

## 1. Review Identity

- **Reviewer**: AgentDS（第二路独立完整 plan re-review，非 diff-only，非新 WU）
- **Reviewed target**: `docs/host/wu-semantic-ownership-01-r04-awaiting-provider-resolution-composition-plan.md`（最终 212 行 immutable plan）
- **Reviewed chain**:
  - 初 review 两路: `docs/reviews/wu-semantic-ownership-01-r04-plan-review-ds.md`, `docs/reviews/wu-semantic-ownership-01-r04-plan-review-mimo.md`
  - Controller adjudication: `docs/reviews/wu-semantic-ownership-01-r04-plan-review-controller-adjudication.md`
  - Codex fix: `docs/reviews/wu-semantic-ownership-01-r04-plan-fix-codex.md`
  - Controller validation (含 re-validation): `docs/reviews/wu-semantic-ownership-01-r04-plan-fix-controller-validation.md`
  - Controller entry validation: `docs/reviews/wu-semantic-ownership-01-r04-plan-entry-controller-validation.md`
- **Authority order**: AGENTS.md → issues-implementation-control.md → controller-discussion.md → host/engine/tool/fins/ui design.md → umbrella §7.3/§7.4/§7.5/§11
- **Code baseline**: `f7006a80`（`dc565d8c` 仅为 R03→R04 transition 文档）
- **Timestamp**: 20260715-181200

## 2. Scope

本 re-review 是完整的从零出发的 adversarial plan review。它不假设初 review 正确，而是独立地：

1. 重新完整读取所有相关 artifacts 和当前代码直接证据
2. 逐项验证 R04-PLAN-F01..F04 与 R04-PLAN-CV-F05 的 closure
3. 从反例出发挑战唯一原子 S1 的以下维度：
   - 上下文可承载性（单 slice 跨 11 production / 14+ test / 5 README / scans / smoke）
   - 闭环完整性（typed mode → metadata → binding → registry → composition → Host policy）
   - 所有 consumers/callers/tests 是否全部覆盖
   - allowlist 是否完整且不遗漏
   - runtime config / Host concrete policy / Service composition 原子性
   - manual/callback/poll mixed matrix 是否完整
   - disabled/non-awaiting/unknown provider boundary
   - scene independence 是否可证明
   - Host no-diff 声明是否可证实
   - 安全与 deferred scope 边界是否保持
4. 检查是否因合并遗漏原 umbrella 测试/coverage/README/smoke/source scan
5. 检查是否仍有隐藏第二 owner/transition seam
6. 检查是否需要改出 allowlist

初 review rejected/no-fix 项只有新直接证据才能重开。每个新 finding 给出 severity、直接证据、root owner、plan fix、状态。

## 3. Previous Finding Closure Verification

### 3.1 R04-PLAN-F01 — Resolution policy 映射与结构性 mapping 分离

**Plan text**: §4.2 明确 "S1 修改 `_binding_for_tool_name`，以 typed `AwaitingResolutionMode` 精确映射 `WaitResumePolicy.POLL/CALLBACK/MANUAL`"；同时明确 "`_operation_kind_from_tool_name` 必须保留：它是 observation handle 恢复所需的稳定 `tool name -> FinsOperationKind` 结构映射，不是 resolution policy 推断"

**Direct evidence**:
- 当前 `_binding_for_tool_name`（`fins_wait_adapter.py:350-356`）硬编码 `WaitResumePolicy.POLL`
- 当前 `_operation_kind_from_tool_name`（`fins_wait_adapter.py:379-393`）被 `_handle_from_snapshot`（line 369）和 `activate_accepted_wait`（line 225）调用

**Verdict**: **CLOSED**. Plan 文本明确区分了 policy 推断替换和结构性映射保留。

### 3.2 R04-PLAN-F02 — S2/S3 共享节点 broken state

**Plan text**: 原 S1/S2/S3 已合并为唯一原子 S1。§4.1 统一封闭所有 allowed files。§10 明确 "不存在 slice 间顺序" 且 "只有全部 contract 与验证同时通过后才能进入 code review"。

**Direct evidence**:
- `ServiceAssemblyOverrides.wait_poller_policy` 声明（`host_assembly.py:186`）和 `_compose_options` 消费者（`host_assembly.py:875`）在同一文件
- 唯一原子 S1 保证删除旧 override 和建立新 typed composition 同时完成

**Verdict**: **CLOSED**. 单 slice 消除了跨 slice broken state。

### 3.3 R04-PLAN-F03 — Non-awaiting/disabled provider 校验 owner

**Plan text**: §4.2 明确三层规则：
1. Service 在 active filtering 前用现有 identity 路由 Fins awaiting providers 到 Fins parser
2. Recognized non-awaiting provider 携带该字段时只做字段存在性 misuse check
3. Disabled Fins provider 的缺失/非法 mode 同样 fail fast
4. §7 测试迁移表包含 disabled+illegal、non-awaiting misconfig 断言

**Direct evidence**:
- `_fins_awaiting_tool_name_from_provider_config`（`host_assembly.py:2048-2076`）通过三组白名单识别 Fins awaiting providers
- `ToolDiscoveryProviderConfig.config` 是 `Mapping[str, JsonValue]`（opaque）
- Plan 不扩展 ConfigLoader generic provider schema（符合 `dayu.runtime` 不得理解 Fins 业务语义的硬约束）

**Verdict**: **CLOSED**. Owner boundary 明确，validation gate 位于 Service assembly。

### 3.4 R04-PLAN-F04 — 旧 override/scene 测试迁移分类

**Plan text**: §7 测试迁移表明确四类处置：
1. 直接传 override → 重写为 ConfigLoader → composition → OpenHostOptions
2. scene-derived helper → 重写为 scene all/select/none negative/propagation
3. Host None/disabled/enabled+missing registry → 保留并改为显式 12-field 构造
4. Provider mode → 新增三模式、非法输入、disabled、non-awaiting misuse
5. §6.3 matrix 每行至少一个 owner-level assertion

**Verdict**: **CLOSED**. 迁移分类明确且可执行。

### 3.5 R04-PLAN-CV-F05 — S1 暴露三模式 contract 但 scene authority 延迟删除

**Plan text**: 原 S1/S2 已合并为唯一原子 S1。§4.2 明确 "只有本唯一 slice 全部改动完成后才允许形成可 review 状态"。§10 明确禁止 "建立临时 fallback、兼容字段/wrapper、hard-coded bridge 或其他 seam"。

**Direct evidence**:
- `with_entrypoint_wait_poller_policy`（`host_assembly.py:268-291`）和 `_scene_selects_fins_awaiting_tools`（`host_assembly.py:2017-2045`）都在 allowlist 内
- 唯一原子 S1 保证 typed mode contract、Host defaults 删除、override/scene helper 删除同时完成

**Verdict**: **CLOSED**. 没有中间状态允许旧 scene authority 与 typed mode contract 共存。

### 3.6 Controller rejected/no-fix dispositions 重开检查

逐项检查初 review 被 Controller rejected 或标记 no-fix 的项目，仅当有**新直接证据**时才重开：

| 来源 | 原 disposition | 新直接证据? | 重开? |
|---|---|---|---|
| DS F-04 | rejected — scan 零命中预期严格 | 无新证据；scan 常量列表仍是对应 10 个部署默认值 | **否** |
| DS F-06 | no-fix — scene None=all 已覆盖 | 无新证据 | **否** |
| DS Q2 | no-fix — 12 个 packaged 值已有产品裁决 | 验证了 12 个值与当前常量完全一致（见 §4.2） | **否** |
| DS Q3 | no-fix — Protocol 12 字段形状不变 | 直接验证了 `api.py:59-73` Protocol 与 `wait_adapter.py:448-459` dataclass 字段一致（见 §5.2） | **否** |
| MiMo F-01 | no-fix — `poll_interval_seconds=1.0` 字面量 | 无新证据 | **否** |
| MiMo F-03 | no-fix — stop condition 可更具体 | 直接验证了 `open_host.py:1623-1653` 三个分支 | **否** |
| MiMo F-05 | no-fix — callback+poll 混合整体失败 | 无新证据 | **否** |
| MiMo F-06 | no-fix — callback transport 时间线 | 无新证据 | **否** |
| MiMo F-08 | no-fix — scan 实施前/后措辞 | 无新证据 | **否** |
| MiMo F-09 | no-fix — `325` 基线可复现性 | 无新证据 | **否** |
| MiMo F-10 | no-fix — fresh schema 原子更新 | 无新证据 | **否** |
| MiMo F-11 | no-fix — coverage 等价替换 | 无新证据 | **否** |
| MiMo F-12 | no-fix — provider identity 与 mode 分离 | 无新证据 | **否** |

**结论**: 无任何 rejected/no-fix 项需要基于新直接证据重开。

## 4. Cross-Cutting Adversarial Challenge

### 4.1 唯一原子 S1 上下文可承载性

**挑战**: 单 S1 跨越 11 production files、16 test files、5 READMEs、两类 smoke、6 个 source scan、全量 pyright、逐文件 ≥80% coverage。是否过于庞大的上下文？

**分析**:
- 原子性要求来自 Controller CV-F05 裁决：不允许 provider mode contract 与旧 scene authority 在任何中间状态共存。这是正确性约束，不是偏好选择。
- Plan §10 禁止的是 **git commit/checkpoint**，不是同 session 内迭代编辑。Implementation agent 可在同一工作会话中逐步编辑、逐步验证，只是不能在中间状态创建 commit。
- 所有文件的改动方向是单向的：typed mode 引入 → defaults/fallback 删除 → override/helper 删除 → composition 替换。没有双向依赖或循环。
- 风险在于 agent 可能在某一步犯错后需要回退大量改动。这是真实风险，但单 slice 结构是当前已知的最安全路径（替代方案是两 slice，但已由 CV-F05 证明会产生过渡语义错误）。

**Verdict**: 挑战已知但可管理。单 slice 是 CV-F05 裁决的直接结果，不是计划设计缺陷。不构成 material finding。

### 4.2 Allowlist 完整性

**挑战**: §4.1 allowlist 是否包含所有必要文件？是否遗漏任何必须改动的位置？

**验证**:
- Production: 11 files。逐项验证每个文件的改动动机：
  1. `tool_discovery.json` — 添加 `awaiting_resolution_mode` 到三个 provider config ✓
  2. `_ingestion_tool_helpers.py` — 新增 enum + parser ✓
  3. `download_provider.py` — 调用 parser ✓
  4. `preprocess_provider.py` — 调用 parser ✓
  5. `upload_provider.py` — 调用 parser ✓
  6. `host_runtime.json` — 新增完整 policy block ✓
  7. `config_loader.py` — 新增 `WaitPollerRuntimePolicyConfig` + 修改 `HostRuntimeProfileConfig` ✓
  8. `wait_adapter.py` — 删除 10 个常量 + 删除 dataclass defaults + 删除两个 `None` fallback ✓
  9. `fins_wait_adapter.py` — 修改 `_binding_for_tool_name` ✓
  10. `host_assembly.py` — 删除 `ServiceAssemblyOverrides.wait_poller_policy` + 删除 `with_entrypoint_wait_poller_policy` + 删除 `_scene_selects_fins_awaiting_tools` + 重写 `_compose_options` + 重写 `_fins_awaiting_registry_inputs_from_provider_configs` + 新增 non-awaiting misuse check + 新增 callback error ✓
  11. `entrypoint_runtime.py` — 删除 `with_entrypoint_wait_poller_policy` 调用 ✓

- Host API (`api.py`) 和 `open_host.py` 不在 allowlist 内。验证 no-diff 声明（见 §5.2）。

- Tests: 16 files 全部存在（已验证），覆盖 config/parser/provider/composition/Host/scene 边界。

- `tests/runtime/test_import_boundary.py` 在 §7 测试命令中但不在 §4.1 allowlist 中。**这不是遗漏** — 该测试不被修改，只是作为验证门禁运行（验证 runtime 无反向 import）。

**Verdict**: Allowlist 完整，无遗漏的必须改动位置。

### 4.3 Hidden Consumers 扫描

**挑战**: 是否存在不被 allowlist 覆盖的 consumer，会在改动后静默失败？

**`with_entrypoint_wait_poller_policy` consumers**:
- `entrypoint_runtime.py:537` — 在 allowlist 内 ✓
- `tests/service/test_host_assembly.py:373,422` — 在 allowlist 内（测试迁移） ✓

**`_scene_selects_fins_awaiting_tools` consumers**:
- `host_assembly.py:286`（`with_entrypoint_wait_poller_policy` 内部） — 随函数删除 ✓
- 无其他 callers ✓

**`ServiceAssemblyOverrides.wait_poller_policy` consumers**:
- `host_assembly.py:284`（`with_entrypoint_wait_poller_policy` 读取） — 随函数删除 ✓
- `host_assembly.py:875`（`_compose_options` 读取） — 重写 ✓
- 无其他 callers ✓

**`WaitPollerRuntimePolicy()` no-arg construction**:
- `host_assembly.py:291` — 随函数删除 ✓
- `wait_adapter.py:985`（`WaitPoller.__init__` fallback） — 删除 ✓
- `wait_adapter.py:1654`（`WaitPollerSupervisor.__init__` fallback） — 删除 ✓

**10 个模块常量 consumers**:
- `wait_adapter.py:450-458`（dataclass field defaults） — 与 defaults 一起删除 ✓
- 无其他 consumers（每个常量只被其对应 field default 引用） ✓

**Verdict**: 所有 consumers 均在 allowlist 内覆盖，无隐藏 consumer。

### 4.4 Scene Independence Proof

**挑战**: 删除 `_scene_selects_fins_awaiting_tools` 后，scene `all/select/none` 是否真的不影响 poller behavior？

**分析**:
- 当前 scene 影响 poller 的唯一路径：`scene_inputs.tool_selection.tool_names` → `_scene_selects_fins_awaiting_tools` → `with_entrypoint_wait_poller_policy` → `WaitPollerRuntimePolicy()` default
- 删除后：Host opener policy 仅由 typed modes + runtime snapshot 决定
- Scene 仍控制 LLM 可用的 tools（通过 `tool_selection`），但不控制后台 poller 的启动/策略
- Plan §6.2 要求测试比较 "owner inputs 相同而仅 scene selection 不同时的结果" 一致

**Verdict**: Scene independence 可证明。✓

### 4.5 Host No-Diff Verification

**挑战**: `api.py` 和 `open_host.py` 是否真的不需要任何改动？

**`api.py` no-diff 验证**:
1. `WaitPollerRuntimePolicy` Protocol（lines 59-73）：12 字段声明。dataclass 删除 defaults 后仍满足此 Protocol。`@runtime_checkable` 基于结构匹配，不检查是否有 default。✓
2. `_validate_wait_poller_policy`（lines 300-375）：逐字段校验。所有 caller 传入完整 12-field policy。不变。✓
3. `OpenHostOptions.wait_poller_policy` type annotation（line 1159 文档）：`WaitPollerRuntimePolicy | None`。不变。✓

**`open_host.py` no-diff 验证**:
1. `_enabled_wait_poller_configuration`（lines 1623-1653）：
   - `policy = options.wait_poller_policy`（line 1634）— 来自 Service composition，完整 typed policy ✓
   - `if policy is None: return None`（line 1635-1636）— 不变 ✓
   - `if not policy.enabled: return None`（line 1637-1638）— 不变 ✓
   - enabled + no registry → `HostApiError`（line 1640-1648）— 不变 ✓
2. `_wait_poller_supervisor_from_open_host_options`（lines 1685-1702）：
   - `WaitPollerSupervisor(policy=configuration.policy, ...)` at line 1700 — 显式传递 policy ✓
   - `_OpenHostWaitPollerFactory(policy=configuration.policy, ...)` at line 1697 — 显式传递 ✓
3. `_OpenHostWaitPollerFactory.create_wait_poller`（lines 540-549）：
   - `WaitPoller(policy=self.policy, ...)` at line 545 — 显式传递，`self.policy` 来自 factory 字段（line 510, required） ✓

**WaitPoller/WaitPollerSupervisor fallback 删除后对 open_host.py 的影响**:
- `WaitPollerSupervisor.__init__`（`wait_adapter.py:1654`）删除 fallback 后，`policy` 变为 required。open_host.py line 1700 显式传递 `policy=configuration.policy`。✓
- `WaitPoller.__init__`（`wait_adapter.py:985`）删除 fallback 后，`policy` 变为 required。open_host.py line 545（factory）显式传递 `policy=self.policy`。✓
- `open_host.py` 无需改动。✓

**Verdict**: Host no-diff 声明成立。API 和 open_host 均无需修改。

### 4.6 Callback Transport Boundary

**挑战**: Plan §6.3 要求 callback 无 transport 时 fail-closed。但 callback mode 的 provider 如何进入 composition？是否有遗漏的 callback 入口？

**分析**:
- 当前三个 Fins awaiting providers 的 mode 均为 packaged `poll`
- Callback mode 只能通过手工编辑 `tool_discovery.json` 引入
- Plan §6.3 matrix row: "任意 callback（单独或混合）| 无 authenticated transport | Service 在 `open_host` 前 composition error"
- Plan §2: "callback 必须在打开 Host 前 composition error，不新增 marker/protocol/facade"
- Host design（`docs/host/design.md:101`）: "当前 product runtime 尚未装配真实 authenticated callback transport 时，选择 `callback` 必须在 Host 打开前 fail fast"

**Verdict**: Callback boundary 明确。Fail-closed 是正确的产品边界。✓

### 4.7 Manual Mode Non-Regression

**挑战**: Manual mode provider 是否会被错误地创建 poll registry entry 或启动 poller？

**分析**:
- Plan §6.1 step 2: "poll registry 只使用 mode=`poll` 的 metadata；manual/callback 不得进入 poll registry"
- Plan §6.1 step 4: "无 active poll（无 provider 或仅 manual）时，`OpenHostOptions.wait_poller_policy=None`"
- Plan §6.3 matrix: "仅 manual | activation 有、poll registry 无 | binding=`MANUAL`，不向 Host 传 policy，不启动"

**Verdict**: Manual mode 正确排除在 poller 之外。✓

## 5. New Findings

### R04-PLAN-RR-F01 — Typed metadata 中间数据结构未达到 code-generation-ready 精度 [Medium]

- **位置**: Plan §4.2 "进入后续装配的私有 typed metadata 携带...`AwaitingResolutionMode`"、§6.1 data flow
- **问题类型**: 不可直接实施
- **当前写法**: Plan 描述了 typed metadata 应携带的内容（provider id、tool name、workspace root、source/version facts、`AwaitingResolutionMode`），并描述了各消费者如何使用 mode（`_binding_for_tool_name` 映射、poll registry 过滤、composition matrix 决策）。但未指定：
  1. 新 typed metadata 的具体数据结构（修改现有 `_FinsAwaitingRegistryInputs` 还是新增 dataclass？）
  2. `_binding_for_tool_name` 的精确签名变化（当前 `(tool_name: str) -> WaitAdapterBinding`，新签名需接受 mode 参数）
  3. Mode 从 pre-validation loop 到 poll registry construction 到 binding construction 的完整数据流
- **反例/失败场景**: Implementation agent 在单 atomic pass 中需要同时修改 10+ 处来建立这个数据流。若 agent 选择了不一致的中间表示（如 `_binding_for_tool_name` 接收 raw string mode 而非 typed enum，或 poll registry 从不同来源读取 mode），会导致：
  - Parser 输出 typed enum 但某消费者接收 string
  - `_binding_for_tool_name` 和 poll registry filter 使用不同的 mode 来源
  - Composition matrix 决策与 binding 不一致
- **为什么有问题**: 这是整个单 slice 中数据流最复杂的部分。Plan 对 end state 的描述是正确的，但对 intermediate data structure 的 specification 不足以让 implementation agent 直接生成代码而无需自行设计。
- **直接证据**:
  - `_FinsAwaitingRegistryInputs`（`host_assembly.py:423-431`）当前仅含 `tool_names: tuple[str, ...]` + `workspace_root: pathlib.Path`，不含 mode
  - `_binding_for_tool_name`（`fins_wait_adapter.py:342-356`）当前 `tool_name: str` 单一参数
  - `_fins_awaiting_registry_inputs_from_provider_configs`（`host_assembly.py:1981-2014`）当前返回 `_FinsAwaitingRegistryInputs | None`
- **影响**: Implementation agent 需自行设计中间数据结构，可能导致不一致或需要 Controller 干预
- **建议改法和验证点**:
  1. 在 plan §4.2 或 §6.1 中明确 typed metadata 的新数据结构（dataclass），字段包括 `tool_name`、`workspace_root`、`mode: AwaitingResolutionMode`、及既有 source/version facts
  2. 明确 `_binding_for_tool_name` 新签名为 `(tool_name: str, mode: AwaitingResolutionMode) -> WaitAdapterBinding`
  3. 明确 `_fins_awaiting_registry_inputs_from_provider_configs` 的新返回类型包含 per-tool mode
  4. 或至少增加 note：implementation agent 必须先设计此中间结构并得到 Controller 确认后再继续
- **修复风险**: 低 — 仅需 plan 文本补充，不改变架构
- **严重程度**: Medium
- **状态**: `accepted-candidate`

### R04-PLAN-RR-F02 — Python `bool` 子类 `int` 的 ConfigLoader 类型校验陷阱 [Low]

- **位置**: Plan §5.2 "bool 冒充数值"、ConfigLoader `WaitPollerRuntimePolicyConfig` int 字段
- **问题类型**: 不可直接实施
- **当前写法**: Plan §5.2 要求 "bool 冒充数值" 被拒绝。但未提及 Python 特有的 `bool` 是 `int` 子类问题（`isinstance(True, int)` 返回 `True`）。
- **反例/失败场景**: JSON 中 `"claim_batch_size": true` 经过 `json.load` 变为 Python `True`。若 ConfigLoader 校验仅写 `isinstance(value, int)` 而不先检查 `isinstance(value, bool)`，则 `True` 会被接受为 `1`，`False` 被接受为 `0`。这违反了 plan 的 "整数位拒绝 bool" 约束。
- **为什么有问题**: 这是 Python 类型系统的已知 footgun。`claim_batch_size` 和 `max_outstanding_adapter_calls` 两个 int 字段受影响。严重性低因为：plan 明确要求拒绝 bool；有经验的 Python 开发者会处理此问题；pyright 类型检查器和测试会捕获。
- **直接证据**:
  - `WaitPollerRuntimePolicy.__post_init__`（`wait_adapter.py:468-479`）当前不检查 bool — 因为它信任 dataclass field type annotation
  - ConfigLoader 的 validation 是新增代码，可能遗漏此检查
- **影响**: 若遗漏，JSON `true`/`false` 会被静默转为 `1`/`0`。测试（负向输入）会捕获，但 agent 可能只测试非法字符串/负数而遗漏 bool
- **建议改法和验证点**:
  1. Plan 可选补充：ConfigLoader int 字段校验必须先 `isinstance(value, bool)` → reject，再 `isinstance(value, int)` → accept
  2. 或在 int field validation helper 的 docstring 中注明此要求
  3. Implementation agent 应在 plan 接受后自行注意此 Python 特性
- **修复风险**: 极低 — 一行代码
- **严重程度**: Low
- **状态**: `accepted-candidate`

### R04-PLAN-RR-F03 — `_fins_awaiting_registry_inputs_from_provider_configs` 重构范围未细化 [Low]

- **位置**: Plan §4.2、当前代码 `host_assembly.py:1981-2014`
- **问题类型**: 不可直接实施
- **当前写法**: Plan 要求：(1) 遍历全部 provider configs（含 disabled），(2) 识别 Fins awaiting providers 并调用 parser，(3) 对 recognized non-awaiting 做 misuse check，(4) 然后做 enabled + available-tool filtering，(5) 构造含 mode 的 typed metadata。但未指定该重构是：
  - 修改 `_fins_awaiting_registry_inputs_from_provider_configs` 自身
  - 新增独立 pre-validation 函数 + 保留原函数做 filtering
  - 拆分 parse+validate 和 filter+collect 两阶段
- **反例/失败场景**: 当前函数已做了 disabled filtering（line 1998）和 available-tool filtering（line 2003）。若 agent 直接在原函数体内加入 pre-validation（在 disabled continue 之前），会改变函数的单一职责。若 agent 新增函数但命名/边界不一致，会导致 Service composition 流程中出现两个相似但职责不同的函数，增加维护负担。
- **为什么有问题**: 函数职责从 "收集 enabled+available Fins awaiting tools" 变为 "验证所有 Fins provider modes + 检查 non-awaiting misuse + 收集 enabled+available"。职责显著扩大，plan 应给出重构方向。
- **直接证据**:
  - `_fins_awaiting_registry_inputs_from_provider_configs`（`host_assembly.py:1981-2014`）当前 34 行，单一职责
  - Plan §4.2 新增的 pre-validation、disabled validation、non-awaiting misuse check 在当前函数中无处安放
- **影响**: Implementation agent 可能做出次优的重构选择（如 God function），或需停下来向 Controller 确认结构
- **建议改法和验证点**:
  1. Plan 补充建议：新增独立 `_validate_fins_awaiting_provider_modes(provider_configs)` 做 mode 校验 + non-awaiting misuse check；然后 `_fins_awaiting_registry_inputs_from_provider_configs` 调用之并在 filtering 后构造 typed metadata
  2. 或在 plan 中明确接受 agent 自行设计此重构结构（当前 plan 未明确授权）
- **修复风险**: 低 — 仅需 plan 文本补充
- **严重程度**: Low
- **状态**: `accepted-candidate`

### R04-PLAN-RR-F04 — `tests/runtime/test_import_boundary.py` 在 §7 测试命令中但不在 §4.1 allowlist 中 [Observation]

- **位置**: Plan §7（包含 `tests/runtime/test_import_boundary.py`）vs §4.1 allowlist（不含）
- **问题类型**: 测试缺口（轻微）
- **当前写法**: §7 测试命令包含 `tests/runtime/test_import_boundary.py`，但 §4.1 allowlist 不含此文件。
- **反例/失败场景**: §4.1 的 "测试/烟测仅允许" list 是 modification allowlist（声明哪些测试文件**可被修改**），而 §7 的命令是 verification command（声明哪些测试**必须运行并通过**）。`test_import_boundary.py` 验证 runtime 无反向 import（对应 §9 scan #5），不应被修改，但必须通过。因此它出现在 §7 但不在 §4.1 是**语义正确的**。
- **为什么有问题**: 不是 plan 错误，而是 plan 未明确区分 "modification allowlist" 和 "verification command"。Implementation agent 可能误解为需要在 §4.1 补充此文件。
- **直接证据**: Plan §4.1 标题 "Allowed files"（修改允许列表），§7 标题 "测试与验证矩阵"（运行验证列表）
- **影响**: 极低 — agent 应理解此区分
- **建议改法和验证点**: 无需改 plan；此为 observation
- **严重程度**: Observation（非 finding）
- **状态**: `observation`

## 6. Umbrella Baseline 保留验证

Plan §3 "Mandatory baseline 逐项处置" 表逐项对照 umbrella 原 R04-S1/S2/S3 mandatory baseline：

| Umbrella mandatory baseline | R04 处置 | 保留状态 |
|---|---|---|
| Provider mode 为 `poll/callback/manual` 且 provider-owned | Fins typed enum/parser 落地 | ✓ 保留 |
| `host_runtime.json` 持有完整 required snapshot | ConfigLoader layer-neutral typed projection | ✓ 保留 |
| Poll/manual/callback/no-provider/disabled composition | §6.3 完整矩阵验证 | ✓ 保留 |
| Umbrella 原 R04-S1 provider mode | 纳入 S1，含 disabled/non-Fins/available-tool negative | ✓ 保留 |
| Umbrella 原 R04-S2 runtime policy | 纳入 S1，完整 required snapshot，Host defaults 删除不延后 | ✓ 保留 |
| Umbrella 原 R04-S3 composition | 纳入 S1，typed composition，override/scene authority 删除同时生效 | ✓ 保留 |
| Source/propagation/security scans、README、smoke、handoff | §7-§10 明确命令和交付门槛 | ✓ 保留 |
| §7.4 closed production list 未列 `wait_adapter.py` | 基于直接证据细化加入 | ✓ 保留（Controller 已裁决） |

**Verdict**: 所有 umbrella mandatory baseline 均保留。合并为单 slice 未弱化任何 baseline。✓

## 7. Security 与 Deferred Scope 边界验证

| 边界 | Plan 处置 | 验证 |
|---|---|---|
| R05 observation-timeout / retry-backoff / LOST 状态机 | §1 明确非目标 | ✓ |
| Engine handshake | §1 明确非目标 | ✓ |
| Issue 175 process isolation | §1 明确非目标 | ✓ |
| Callback transport 本体 | §1/§2 明确非目标，fail-closed only | ✓ |
| Scene / `execution_profiles` 配置 | §1 明确非目标 | ✓ |
| 统一 tool authorization | §1 明确非目标 | ✓ |
| Permission DSL | §1 明确非目标 | ✓ |
| Issue 142/151/177/178 | §1 明确非目标 | ✓ |
| R05-R12 后续能力 | §1 明确非目标 | ✓ |
| 现有安全机制（身份、权限、callback 映射、文件边界、egress、cancel、durable wait、ToolRuntime） | §1 明确保留 | ✓ |

**Verdict**: 所有 deferred/no-code 边界均未被侵入。✓

## 8. Open Questions

1. **Q1**: Plan §4.2 "Service 在 active filtering 前遍历全部 effective provider configs" — 该遍历是否应在 `compose_open_host_options` 中、在 `_fins_awaiting_registry_inputs_from_provider_configs` 被调用之前完成？当前 `compose_open_host_options` 的调用链为 `_tooling_options_from_discovery → _fins_awaiting_registry_inputs_from_provider_configs`（在 Service 内部）。新的 pre-validation 应在此链的哪个精确位置介入？

2. **Q2**: Plan §2 "packaged snapshot 固定为 `true, 1, 60, 100, 30, 2, 300, 1, 5, 30, 5, 8`" — 这 12 个值完全匹配当前 10 个模块常量 + `enabled=True` + `poll_interval_seconds=1.0`。Controller 已裁决为 no-fix（DS Q2）。但如果有未来产品需求改变这些值，修改流程是什么？是编辑 `host_runtime.json` 即可，还是有额外的 review gate？此问题不阻塞 R04，但值得在 implementation handoff 中记录。

## 9. Residual Risks

| Risk | Severity | Owner / Destination |
|---|---|---|
| 单 slice 跨 11 production + 16 test files 的实现复杂度 | Medium | Implementation agent 能力依赖；plan 的 no-checkpoint 约束增加了单次 pass 的压力 |
| R04-PLAN-RR-F01 中间数据结构设计未被 implementation agent 正确执行 | Medium | 若 agent 选择了不一致的 mode 传播方式，composition matrix 可能产生错误行为 |
| Python bool-int subclass footgun（R04-PLAN-RR-F02） | Low | 有经验的 agent 会处理；ConfigLoader validation tests 应覆盖 |
| Callback transport 交付时间线 | Low | WU-WAIT-01 / Issue #89；R04 仅 fail-closed |
| Fresh `host_runtime.json` schema 不兼容旧 workspace | Low | 预期 fresh-schema 行为；R04 禁止兼容读取 |
| NumPy multi-module coverage double-load | Low | 已由等价验证处置：单一 `--cov=dayu` session |

## 10. Final Plan Re-Review Conclusion

**Verdict: `pass-with-risks`**

### Summary

R04 final plan（212 行，唯一原子 S1）在以下维度通过了基于直接证据的 adversarial re-review：

- **语义 owner 唯一性**: Provider config owns mode（Fins parser）；`host_runtime.json` owns policy（ConfigLoader）；Service owns composition；Host owns execution。无第二 owner 或隐藏 transition seam。
- **Previous finding closure**: R04-PLAN-F01..F04 和 R04-PLAN-CV-F05 全部关闭。Verified through plan text + direct code evidence。
- **Rejected/no-fix dispositions**: 全部保持。无新直接证据触发重开。
- **Allowlist 完整性**: 11 production + 16 test + 2 smoke + 5 README 全部覆盖，无遗漏。
- **Hidden consumers**: 全部三个待删除函数、两个 `None` fallback、10 个模块常量、`ServiceAssemblyOverrides.wait_poller_policy` 的所有 consumers 均在 allowlist 内。
- **Host no-diff**: `api.py` 和 `open_host.py` 经逐行验证无需修改。Protocol 结构不变，`_enabled_wait_poller_configuration` 三个分支不变，factory/supervisor 显式传递 policy。
- **Scene independence**: 可证明。唯一影响路径（`_scene_selects_fins_awaiting_tools → with_entrypoint_wait_poller_policy → default policy`）被完整删除。
- **Manual/callback/poll mixed matrix**: §6.3 14 行 negative matrix 覆盖所有组合。
- **Security 与 deferred scope**: 全部边界保持。R05/Issue 175/callback transport/authorization/permission DSL/Issue 142-178 均未侵入。
- **Umbrella baseline**: 原 R04-S1/S2/S3 mandatory baseline 逐项保留，未因合并弱化。

### Accepted Findings

| Finding | Severity | Status |
|---|---|---|
| R04-PLAN-RR-F01 Typed metadata 中间数据结构未达 code-generation-ready 精度 | Medium | `accepted-candidate` |
| R04-PLAN-RR-F02 Python bool-int subclass ConfigLoader 校验陷阱 | Low | `accepted-candidate` |
| R04-PLAN-RR-F03 `_fins_awaiting_registry_inputs_from_provider_configs` 重构范围未细化 | Low | `accepted-candidate` |
| R04-PLAN-RR-F04 `test_import_boundary.py` allowlist 语义区分 | — | `observation` |

**Total**: 3 accepted-candidate findings, 1 observation, 0 blocking

### Blocking Questions

无。所有 open questions 为非阻塞澄清。

### Overall Assessment

Plan 是 code-generation-ready 的，但 R04-PLAN-RR-F01（typed metadata 中间数据结构）应在 implementation 前补充至 plan 或由 Controller 在 implementation handoff 时明确授权 agent 自行设计。R04-PLAN-RR-F02 和 R04-PLAN-RR-F03 是轻度精度问题，不阻止 implementation。

---

**Output file**: `docs/reviews/wu-semantic-ownership-01-r04-plan-rereview-ds.md`
**Generated**: 2026-07-15T18:12:00+08:00
