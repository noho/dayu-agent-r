# WU-SEMANTIC-OWNERSHIP-01 R04 Plan Re-Review — AgentMiMo

## 1. Review Identity

- **Reviewed target**: `docs/host/wu-semantic-ownership-01-r04-awaiting-provider-resolution-composition-plan.md`（最终 212 行）
- **Review chain**: 初 review（MiMo + DS）→ Controller adjudication（4 accepted findings）→ AgentCodex plan fix → Controller validation → CV-F05 finding → AgentCodex atomic-slice merge → Controller re-validation（PASS / READY_FOR_DUAL_COMPLETE_PLAN_RE_REVIEW）
- **Code baseline**: `f7006a80`
- **Authority order**: AGENTS.md → `docs/host/issues-implementation-control.md` → `docs/host/wu-semantic-ownership-01-overdesign-remediation-plan.md` §7.3/§7.4/§7.5/§11 → `docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md` Topic 5 → `docs/host/design.md` §10.1/§11.1/§20 → 当前代码
- **Review scope**: 完整 plan 212 行 + 全部 review/fix/adjudication/validation 链 + 当前代码直接证据
- **Generated**: 2026-07-15T18:02:27+08:00

## 2. Review Posture

本 review 是第一路完整 plan re-review。目标不是证明 plan 可行，而是尽力找出最强的、基于证据的理由说明 plan 还不应交给 implementation agent。重新完整读取 plan、全部 review artifacts、Controller 裁决链、设计真源和当前代码，逐项验证 F01-F04 和 CV-F05 closure，特别挑战唯一原子 S1 的完整性和 code-generation-ready 程度。

## 3. Assumptions Tested

| # | Assumption | Evidence | Verdict |
|---|-----------|----------|---------|
| A1 | 唯一原子 S1 完整消费 umbrella 原 S1/S2/S3 mandatory baseline | §3 逐项映射表覆盖 provider mode（原 S1）、runtime policy（原 S2）、composition（原 S3）；§4-§6 合并为同一 slice | ✓ confirmed |
| A2 | `dayu/host/api.py` 和 `open_host.py` 不需改动 | `open_host.py:1634-1653` 已实现 `None→不启动`、`disabled→不启动`、`enabled+缺 registry→fail-closed`；plan §5.2 明确 no-diff | ✓ confirmed |
| A3 | `WaitPollerRuntimePolicy` 12 字段全部 required 时可无 default 构造 | `wait_adapter.py:427-508` 当前有 defaults；plan S1 删除全部 defaults 和无参构造，改为显式 keyword-only | ✓ confirmed |
| A4 | 三个 packaged Fins awaiting providers 均为 `poll` mode | `tool_discovery.json` 当前无 `awaiting_resolution_mode` 字段；plan §2 规定 packaged 三 provider mode 均为 `poll` | ✓ confirmed |
| A5 | source scan 零命中可在实施后满足 | 当前 `_DEFAULT_CLAIM_BATCH_SIZE` 等 10 个常量和 `WaitPollerRuntimePolicy()` 无参构造在 S1 删除后自然消除；`with_entrypoint_wait_poller_policy` 和 `_scene_selects_fins_awaiting_tools` 函数在 S1 删除后消除 | ✓ confirmed |
| A6 | callback 无 transport 时 fail-closed 不发明 abstraction | plan §2/§6.3 明确 "不新增 marker/protocol/facade"；composition error 沿用现有异常惯例 | ✓ confirmed |
| A7 | `host_runtime.json` fresh schema 与 ConfigLoader 必须同时更新 | plan §5.2 要求 JSON 与 ConfigLoader 同一 S1 完成；AGENTS.md 禁止旧 schema 兼容 | ✓ confirmed |
| A8 | ConfigLoader layer-neutral 新增 `WaitPollerRuntimePolicyConfig` 不违反 `dayu.runtime` 边界 | ConfigLoader 当前已承载 `HostRuntimeProfileConfig` 等层中立 typed config；新增 frozen dataclass 不引入业务层 import | ✓ confirmed |
| A9 | F01-F04 和 CV-F05 全部已 closure | fix artifact 逐项记录 before/after/evidence；Controller re-validation 确认所有 5 个 findings 关闭 | ✓ confirmed |

## 4. Finding Closure Verification

### R04-PLAN-F01 — 区分 resolution policy 映射与结构性 tool-name 映射

**Status**: ✓ 已修复

plan §4.2 明确：
- `_binding_for_tool_name` 由 typed `AwaitingResolutionMode` 映射 `WaitResumePolicy.POLL/CALLBACK/MANUAL`，替换硬编码 `POLL`（第 87 行）
- `_operation_kind_from_tool_name` 保留为 "observation handle 恢复所需的稳定结构映射，不是 resolution policy 推断"（第 87 行）
- owner tests 必须 "断言 `_operation_kind_from_tool_name` 的 download/preprocess/upload 结构映射保持有效"（第 89 行）

代码直接证据：`fins_wait_adapter.py:379-393` 的 `_operation_kind_from_tool_name` 确实被 `_handle_from_snapshot`（line 369）和 `activate_accepted_wait`（line 225）调用，是结构映射而非 policy 推断。

**Closure 证据充分，无残余歧义。**

---

### R04-PLAN-F02 — 修正 S2/S3 共享节点，禁止中间 broken state

**Status**: ✓ 已修复

原始问题：S2 删除 `ServiceAssemblyOverrides.wait_poller_policy` 字段后，`_compose_options`（`host_assembly.py:875`）引用该字段会报错，但 S3 才允许修改 `_compose_options`。

plan 修复方案：原 S1/S2/S3 合并为唯一原子 S1。§4.2（第 81 行）明确 "provider mode、runtime policy、Host defaults/fallback 删除、override/scene helper 删除、typed composition、tests、README、scans 与 smoke 必须在一次 implementation pass 内共同完成"。

代码直接证据：
- `ServiceAssemblyOverrides.wait_poller_policy`（`host_assembly.py:186`）
- `_compose_options` 中 `wait_poller_policy=request.overrides.wait_poller_policy`（`host_assembly.py:875`）
- 两者在同一文件，S1 同时删除字段和重建 composition 路径，不存在中间 broken state。

**Closure 证据充分，原子性保证消除 broken state 风险。**

---

### R04-PLAN-F03 — 固定 non-awaiting/disabled provider 配置校验 owner

**Status**: ✓ 已修复

plan §4.2（第 84-85 行）明确：
- Service 在 active filtering 前遍历全部 effective provider configs
- 用现有 `_fins_awaiting_tool_name_from_provider_config` 识别当前三个 Fins awaiting providers
- "识别后立即把 opaque config 交给 Fins parser，因此 disabled Fins provider 的缺失或非法 mode 同样 fail fast"
- "对 Service 已有 identity 明确认识的 non-awaiting providers，若 opaque config 存在 `awaiting_resolution_mode`，Service 只做字段存在性 misuse check 并失败"

Controller 裁决确认：Fins parser 天然只处理 Fins provider；ConfigLoader 不应理解 Fins 业务语义；Service composition 用现有 provider identity 路由。

**Closure 证据充分，owner 边界清晰。**

---

### R04-PLAN-F04 — 明确旧 override/scene 测试的 owner-level 迁移

**Status**: ✓ 已修复

plan §7（第 166-174 行）列出五类迁移：
1. 直接构造 `ServiceAssemblyOverrides.wait_poller_policy` → 重写为完整 12 字段构造链
2. `with_entrypoint_wait_poller_policy` / scene-selected → 重写为 scene-independence negative/propagation tests
3. Host `None/disabled/enabled+missing registry` → 保留 fail-closed，改为显式完整 policy 构造
4. provider mode → 重写为三模式、非法输入、disabled、non-awaiting misuse
5. §6.3 matrix → 每行至少一个 owner-level assertion

**Closure 证据充分，迁移分类覆盖所有旧测试类别。**

---

### R04-PLAN-CV-F05 — S1 暴露三模式 contract，但 scene-derived poller authority 延迟到 S2

**Status**: ✓ 已修复

原始问题：两-slice 计划在 S1 暴露 manual/callback typed mode，但 `with_entrypoint_wait_poller_policy → _scene_selects_fins_awaiting_tools` 仍依据 scene selection 且无 typed mode 输入，形成过渡语义。

plan 修复方案：S1/S2 合并为唯一原子 S1。§4.2（第 81 行）明确禁止 "中间 commit/checkpoint"、"旧 scene bridge"、"临时 fallback"。§6.1（第 115 行）要求 `_compose_options` 一次性写入最终 registry 与 policy。

代码直接证据：
- `with_entrypoint_wait_poller_policy`（`host_assembly.py:268-291`）：只看 scene selection，不看 typed mode
- `_scene_selects_fins_awaiting_tools`（`host_assembly.py:2017-2045`）：只按 tool name 和 scene intersection 判断
- 两者在 S1 中被删除，scene 不再拥有后台 runtime authority

**Closure 证据充分，原子性保证消除过渡语义。**

## 5. 唯一原子 S1 完整性挑战

### 5.1 umbrella 原 S1/S2/S3 消费完整性

| umbrella baseline | plan 处置 | 证据 |
|---|---|---|
| provider mode 为 `poll/callback/manual` 且 provider-owned | §3 第一行：保留；Fins 单一 typed enum/parser | §4.2: "在 Fins 共享 helper 定义 closed `AwaitingResolutionMode(StrEnum)` 与唯一严格 parser" |
| `host_runtime.json` 持有完整 required snapshot | §3 第二行：保留；ConfigLoader layer-neutral typed projection | §5.2: 12 字段全部 required，JSON block 缺失/字段缺失/多余/类型错误都失败 |
| poll/manual/callback/no-provider/disabled composition | §3 第三行：保留；§6.3 完整矩阵 | §6.3 矩阵覆盖 12 行，比 umbrella §11.2 的 6 行更细化 |
| umbrella 原 R04-S1 provider mode | §3 第四行：完整保留并纳入唯一原子 S1 | §4.2 覆盖三模式、非法输入、disabled、non-awaiting misuse |
| umbrella 原 R04-S2 runtime policy | §3 第五行：完整保留并纳入同一原子 S1 | §5.2 覆盖完整 required snapshot、Host defaults/fallback 删除 |
| umbrella 原 R04-S3 composition | §3 第六行：完整保留并纳入同一原子 S1 | §6 覆盖 typed composition、override/scene authority 删除 |
| source/propagation/security scans、README、smoke | §3 第七行：保留 | §7-§10 命令和交付门槛完整 |

**结论：唯一原子 S1 完整消费 umbrella 原 S1/S2/S3 mandatory baseline，无静默遗漏。**

### 5.2 transitional state / seam 消除验证

S1 内部所有改动必须同时完成。以下关键 seam 已逐一验证：

| 潜在 seam | 消除方式 | 证据 |
|---|---|---|
| typed mode 暴露但 scene authority 未删除 | S1 同时删除 `with_entrypoint_wait_poller_policy` 和 `_scene_selects_fins_awaiting_tools` | §4.2 第 81 行 "必须在一次 implementation pass 内共同完成" |
| Host defaults 删除但 override 未删除 | S1 同时删除 `ServiceAssemblyOverrides.wait_poller_policy` 和 Host policy dataclass defaults | §5.2 第 103-104 行 |
| typed composition 建立但旧 `_compose_options` 仍读 override | S1 同时修改 `_compose_options` 为 typed composition | §6.1 第 115 行 "一次性写入最终 registry 与 policy" |
| ConfigLoader 新增 `wait_poller_policy` 但 JSON 未更新 | S1 同时更新 `host_runtime.json` 和 ConfigLoader | §5.2 第 100 行 "必须与 §4 provider mode 在同一 S1 完成" |

**结论：唯一原子 S1 内无 transitional state 或 seam。**

### 5.3 allowlist 自洽验证

**生产 allowlist**（§4.1 第 63-73 行）vs umbrella §7.4：

umbrella §7.4 R04 行：`tool_discovery.json`、`host_runtime.json`、`config_loader.py`、三个 Fins provider、`_ingestion_tool_helpers.py`、`host_assembly.py`、`entrypoint_runtime.py`、`fins_wait_adapter.py`

plan §4.1 生产 allowlist 增加 `dayu/host/wait_adapter.py`。§3 第八行解释："该文件当前拥有 10 个部署数值常量、policy dataclass defaults，以及 `WaitPoller`/`WaitPollerSupervisor` 的无参 fallback；§11.3 和 §7.5 R04-S2 又明确要求移除这些默认。若不改该 owner 文件会留下第二真源"

umbrella §7.3 规则："若重新核对发现语义 owner、依赖、production allowlist 或 controller accepted contract 发生实质变化，sub-WU plan 必须停止并回到 controller 裁决"。Controller entry validation 已裁决接受 `wait_adapter.py` 作为 R04-S2 的窄化 owner 文件。

**测试 allowlist**（§4.1 第 75 行）覆盖：runtime config tests、Fins ingestion tests、Service host assembly tests、Service entrypoint runtime tests（base + interactive + prompt）、Host open host tests、Host wait adapter/poller/observation tests、smoke tests。

**README allowlist**（§4.1 第 77 行）覆盖：config、host、service、fins、tests。

**结论：allowlist 与 umbrella §7.4 一致（基于直接证据窄化），测试和 README 覆盖完整。**

### 5.4 manual/callback/poll/disabled/no-provider/scene-independence code-generation-ready 验证

§6.3 矩阵 12 行逐行检查：

| 行 | 场景 | code-generation-ready? | 证据 |
|---|---|---|---|
| 1 | 无 active awaiting provider | ✓ | plan 明确 "不向 Host 传 poller policy，不启动" |
| 2 | 仅 manual | ✓ | plan 明确 "binding=`MANUAL`，不向 Host 传 policy，不启动" |
| 3 | 仅 poll，policy enabled | ✓ | plan 明确 "一对一传 policy，Host 启动 poller" |
| 4 | poll + manual，policy enabled | ✓ | plan 明确 "只 claim/observe `POLL` wait，manual 不被后台轮询" |
| 5 | active poll，policy disabled | ✓ | plan 明确 "一对一传 disabled policy；Host 不启动，不得用代码默认重启" |
| 6 | active poll，policy enabled，poll registry 缺失/空 | ✓ | plan 明确 "Service 在 `open_host` 前 composition error" |
| 7 | 任意 callback（单独或混合），无 transport | ✓ | plan 明确 "Service 在 `open_host` 前 composition error；不得降级为 poll/manual" |
| 8 | callback + 伪 marker | ✓ | plan 明确 "R04 不定义可绕过 marker" |
| 9 | mode 缺失/null/非字符串/空串/未知/大小写变体 | ✓ | plan 明确 "provider config parse error，不进入 composition" |
| 10 | 非 Fins provider 声明该字段 | ✓ | plan 明确 "owner misuse error，不 loose parse" |
| 11 | disabled provider（任意合法 mode） | ✓ | plan 明确 "不创建 binding，不影响 poller 决策" |
| 12 | scene 未选择 active poll tool | ✓ | plan 明确 "Host 装配决策与 scene 选择前一致" |

**结论：§6.3 矩阵每行都有明确的预期行为，implementation agent 可直接据此编写代码和测试。**

### 5.5 non-awaiting/disabled validation owner 无 loose parse 验证

- plan §2 owner table（第 29 行）：Service "只用现有 provider identity 路由到 Fins parser，并检查 recognized non-awaiting provider 的字段误用；不解析 raw mode、不拥有第二 enum/parser"
- plan §4.2（第 85 行）："若 opaque config 存在 `awaiting_resolution_mode`，Service 只做字段存在性 misuse check 并失败；不得读取、规范化或解析该字段的 raw value"
- Fins parser 是唯一 mode parser，Service 不解析 raw string

**结论：无 loose parse，owner 边界清晰。**

### 5.6 Host API/open_host no-diff 和安全/deferred 边界验证

- plan §5.2（第 105-106 行）："保持 `dayu/host/api.py`、`dayu/host/open_host.py` 无改动；如实施证据显示 public contract 必须变化，立即停止并回到 Controller，不扩 allowlist"
- plan §1（第 22 行）非目标明确排除：R05 observation-timeout / retry-backoff / `LOST` 状态机；Engine handshake 改动；Issue 175 process isolation；callback transport 本体；scene / execution_profiles 配置；统一 tool authorization；permission DSL
- plan §10（第 210 行）停止条件："现有安全机制需放宽" 时立即停止
- diff 二次扫描（§9 第 202 行）：对 diff 扫描 `authorization|permission|process_backed|subprocess|observation_timeout|ResolveWaitLostOutcome`，任何新增均失败并回退

**结论：Host API/open_host no-diff 保持，安全/deferred 边界未漂移。**

## 6. Architecture Boundary Review

### 6.1 分层架构合规

- ConfigLoader（`dayu.runtime`）：只做层中立 typed parse，不 import Host/Fins/Service/Engine → ✓
- Fins parser（`dayu.fins`）：定义 `AwaitingResolutionMode` enum 和严格 parser → ✓
- Service composition（`dayu.service`）：组合 typed mode、typed policy、registry → ✓
- Host（`dayu.host`）：执行 Service 传入的显式 policy → ✓

### 6.2 语义所有权合规

| 语义 | owner | 消费方 | 是否单一真源 |
|---|---|---|---|
| provider 恢复方式 | Fins provider config + Fins parser | Service | ✓ |
| poller 部署参数 | `host_runtime.json` + ConfigLoader | Service → Host | ✓ |
| 是否装配 poller | Service composition（typed inputs only） | Host | ✓ |
| poller 生命周期 | Host | — | ✓ |

### 6.3 过度耦合检查

plan 把 provider mode、runtime policy、Host defaults、override/scene deletion、typed composition 放在同一原子 S1 中。这是 CV-F05 的直接修复——原 S1/S2 切分会导致 scene-derived poller authority 与 typed mode 共存的过渡语义。合并是必要的，不是过度耦合。

所有 11 个生产文件之间依赖关系清晰：
- `tool_discovery.json` → Fins providers（parser 定义）→ `fins_wait_adapter.py`（binding）→ `host_assembly.py`（composition）→ `entrypoint_runtime.py`（调用）
- `host_runtime.json` → `config_loader.py`（typed config）→ `host_assembly.py`（composition）
- `wait_adapter.py`（Host policy dataclass）被 `host_assembly.py` 和 `config_loader.py` 消费

没有双向依赖，没有跨层穿透。

## 7. Best-Practice / Overengineering / Overcoupling Review

### 7.1 Best-Practice Review

- frozen dataclass + required fields + `__post_init__` 校验 → 符合最佳实践
- closed StrEnum + strict parser → 符合最佳实践
- ConfigLoader 层中立 typed projection → 符合最佳实践
- Service composition 显式 typed inputs → 符合最佳实践

### 7.2 Overengineering Review

- plan 没有引入不必要的 abstraction、layer、builder 或 protocol
- `AwaitingResolutionMode` enum 是最小 closed enum，不是过度设计
- `WaitPollerRuntimePolicyConfig` 是 ConfigLoader 已有模式的自然扩展
- callback fail-closed 不发明 marker/protocol/facade

### 7.3 Overcoupling Review

- 唯一原子 S1 是 CV-F05 的必要修复，不是过度耦合
- `wait_adapter.py` 加入 allowlist 是基于直接代码证据的窄化，不是扩域
- plan 没有把可独立演进的概念绑定在一起

## 8. Open Questions

无 blocking questions。

以下为已解决或不阻塞的观察：

| # | Question | Resolution |
|---|---|---|
| Q1 | non-Fins provider `awaiting_resolution_mode` 静默接受 | Controller 裁决：不为非 Fins provider 发明新语义；plan §4.2 已明确 "未知第三方 provider 不由 R04 发明新语义" |
| Q2 | 12 个 packaged 数值的产品依据 | Controller discussion Topic 5 和 umbrella §11.2 已完成产品裁决；plan §2 列出完整字段和值 |
| Q3 | `dayu/host/api.py` Protocol 是否需更新 | Controller re-validation 确认：required-field 改造只删除 dataclass defaults，Protocol 的 12 字段形状不变，no-diff |

## 9. Residual Risks

| Risk | Severity | Owner/Destination |
|------|----------|-------------------|
| authenticated callback transport 尚不存在 | Low | WU-WAIT-01 / Issue #89；R04 继续 fail-closed |
| fresh `host_runtime.json` schema 不兼容旧 workspace | Low | 预期 fresh-schema 行为；AGENTS.md 禁止旧 schema 兼容 |
| NumPy multi-module coverage double-load | Low | 已由既有等价验证处置：单一 `--cov=dayu` session 后逐文件读取 JSON |
| disabled Fins provider validation 时机（ConfigLoader vs Service） | Low | plan 已通过 "遍历全部 effective provider configs" 明确 Service-level 早于 active filtering |

## 10. Final Plan Review Conclusion

**Verdict: `pass`**

R04 plan 在以下方面设计合理且基于直接代码证据：

1. **语义所有权**：provider config 拥有 `poll/callback/manual` mode；`host_runtime.json` 拥有完整 required policy snapshot；Service 只组合 typed inputs；scene 不拥有后台 runtime authority；Host 只执行显式 policy。

2. **唯一原子 S1 完整性**：完整消费 umbrella 原 S1/S2/S3 mandatory baseline；无 transitional state 或 seam；provider mode/parser/binding/metadata、runtime policy、Host defaults/fallback 删除、override/scene helper 删除、typed composition、tests/README/scans/smoke 一次完成。

3. **F01-F04 和 CV-F05 closure**：5 个 finding 全部关闭，fix 证据充分，无残余歧义。

4. **code-generation-ready 程度**：§6.3 矩阵 12 行每行有明确预期行为；§7 测试迁移分类覆盖所有旧测试类别；§4.1 allowlist 自洽封闭；§9 source scan 可满足；§10 停止条件和 handoff 格式完整。

5. **边界保持**：Host API/open_host no-diff；callback fail-closed 不发明 abstraction；安全/deferred 边界未漂移；`dayu.runtime` 不引入业务层 import。

6. **无过度耦合**：唯一原子 S1 是 CV-F05 的必要修复；allowlist 窄化基于直接代码证据；无双向依赖或跨层穿透。

**0 个 accepted findings，0 个 blocking questions。Plan 可以交给 implementation agent。**

---

**Output file**: `docs/reviews/wu-semantic-ownership-01-r04-plan-rereview-mimo.md`
**Generated**: 2026-07-15T18:02:27+08:00
