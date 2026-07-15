# WU-SEMANTIC-OWNERSHIP-01 R04 Plan Review — AgentDS

## Review Identity

- **Reviewer**: AgentDS（第二路独立 adversarial plan review）
- **Reviewed target**: `docs/host/wu-semantic-ownership-01-r04-awaiting-provider-resolution-composition-plan.md`
- **Controller entry validation**: `docs/reviews/wu-semantic-ownership-01-r04-plan-entry-controller-validation.md`（以 discussion 为准）
- **Code baseline**: `f7006a80`（`dc565d8c` 仅为 R03→R04 transition）
- **Authority order**: AGENTS.md → issues-implementation-control.md → phaseflow-umbrella-optimization-control.md → controller-discussion.md → host/engine/tool/fins/ui design.md → umbrella plan §7.3/§7.4/§7.5/§11
- **Timestamp**: 20260715-172854

## Scope

本 review 是完整的 adversarial plan review，目标是找出最强理由说明此 plan 还不应交给 implementation agent。审查范围包括：

- plan 宣称的 goal、non-goals、三 slice 依赖与独立可验证闭环
- closed allowlist、typed propagation、完整 required Host policy
- 所有 default/fallback removal
- callback/manual/poll composition
- scene independence
- 测试/coverage/pyright/README/scans/smoke
- security/deferred boundary
- 重点反例区域（见下文）

## Assumptions Tested

| # | Assumption | Verdict |
|---|-----------|--------|
| A1 | Host API/open_host 无需改动即可满足新 composition | **成立** — `open_host.py` 已有完整 fail-closed 逻辑（`_validate_wait_poller_configuration` → `policy is None` 不启动，`not policy.enabled` 不启动，enabled+missing registry → `HostApiError`），与 plan §2/§5.2 一致 |
| A2 | 三 slice 依赖顺序（S1→S2→S3）可独立验证闭合 | **成立** — S1 只产出 typed mode + provider metadata；S2 只产出 typed policy + 删除 defaults；S3 只消费 S1/S2 的 public typed contract。每 slice 有独立测试集且允许文件无重叠 |
| A3 | `WaitPollerRuntimePolicy` 所有 12 字段可在无 default 时构造 | **成立** — 构造期全部 required keyword，`__post_init__` 做正数/finite/bool 拒绝。plan §2 已列出完整字段列表 |
| A4 | 真实 smoke 可在不访问外部 LLM/网络的情况下按 allowlist 实现 | **成立** — 两个既有 smoke (`smoke_host_public_r03_semantic_ownership.py`、`smoke_host_public_awaiting_entrypoint.py`) 均已走 `ConfigLoader → Service assembly → public Host`，不调真实 LLM，plan §9 明确了更新后的覆盖矩阵 |
| A5 | plan source scans 可满足零命中预期 | **基本成立** — 见 Finding 5 |
| A6 | callback transport 不存在时 fail fast 不发明未来 abstraction | **成立** — plan §6.3 明确 "Service 在 open_host 前 composition error；不得降级为 poll/manual" 且 §2 明确 "不新增 marker/protocol/facade" |

## Findings

### F-01 — Non-Fins provider mode misconfig owner 边界不清 [Medium]

- **位置**: plan §4.2 "非 Fins provider 若携带 `awaiting_resolution_mode`，在 discovery/composition 边界失败，禁止 Service 把 generic raw config 解释为 Fins 语义"
- **问题类型**: 契约缺失
- **当前写法**: plan 声明了规则，但未指定具体 validation boundary。S1 allowed files 仅包含 Fins provider (`download_provider.py` / `preprocess_provider.py` / `upload_provider.py`) 和 Fins shared helper (`_ingestion_tool_helpers.py`)。S3 allowed files 包含 `host_assembly.py` / `fins_wait_adapter.py`。
- **反例/失败场景**: 假设 Web provider (`tool_discovery.json` 的 `web-tools` entry) 的 `config` 中误写 `"awaiting_resolution_mode": "callback"`。当前 `ToolDiscoveryProviderConfig.config` 是 `Mapping[str, JsonValue]`（untyped catch-all）。该字段不会被 ConfigLoader 的 typed parser 拒绝，也不会被 Fins shared parser 看到（因为 non-Fins provider 不调用 Fins parser）。Service composition 的 `_fins_awaiting_tool_name_from_provider_config` 只按 `provider_id`/`import_path`/`source_id` 白名单识别 Fins provider，不会触发 non-Fins provider 的 mode 检查。
- **为什么有问题**: 该规则写入 plan 但没有分配具体 owner。Fins shared parser 天然只处理 Fins provider；ConfigLoader 不应该 import Fins；Service composition 只组合 typed inputs。三者之间无明确负责方。
- **直接证据**:
  - `ToolDiscoveryProviderConfig`（`dayu/runtime/config_loader.py`）的 `config` 字段接受任意 `Mapping[str, JsonValue]`
  - `_fins_awaiting_tool_name_from_provider_config`（`dayu/service/host_assembly.py:2056`）仅按 provider_id/import_path/source_id 白名单匹配
  - plan S1 allowed files 不含任何 cross-provider validation 入口
- **影响**: implementation agent 可能把该规则实现为 defensive check 在错误的层（如 Service composition 做 loose string check），或干脆遗漏该检查
- **建议改法和验证点**:
  1. 明确 owner：建议在 S1 的 `_ingestion_tool_helpers.py` 中定义 `AwaitingResolutionMode` parser 后，在 S3 的 `host_assembly.py` composition 阶段对所有 enabled provider 的 config 做结构化校验（非 Fins provider 携带该 mode 时 fail closed with typed error）
  2. 或在 plan 中承认该场景仅可能在手工编辑 JSON 时发生，由 ConfigLoader 的 JSON schema validation 在顶层字段检查中覆盖（即把 `awaiting_resolution_mode` 提升为 `ToolDiscoveryProviderConfig` 的可选 typed field，ConfigLoader 对全体 provider 校验其合法性）
  3. 无论哪种方案，S1 allowlist 需增加对应文件，或在 plan §4.2 写明 owner
- **修复风险**: 低 — 只需澄清边界，不需要改变核心架构
- **severity**: Medium
- **status**: accepted-candidate

### F-02 — Disabled provider 的 parse 边界未落地 [Low]

- **位置**: plan §4.2 "disabled provider 仍须配置 schema 合法，但不进入 active metadata/registry"
- **问题类型**: 契约缺失
- **当前写法**: plan 声明了 disabled provider 仍需 parse 规则，但 S1 的实现 contract 未指定 disabled provider 在何处被校验。当前代码 `_fins_awaiting_registry_inputs_from_provider_configs`（`host_assembly.py:1995`）在 `if not provider_config.enabled: continue` 处直接跳过 disabled provider，不会调用 `_fins_awaiting_tool_name_from_provider_config`。
- **反例/失败场景**: Fins download provider 被 `enabled: false`，但其 `config.awaiting_resolution_mode` 设为 `"invalid_value"`。当前代码和 plan S1 flow 均跳过该 provider，非法 mode 不会被发现。未来若 operator 重新启用该 provider，会在运行时失败而非 config-load 时失败。
- **为什么有问题**: "disabled 仍需 parse" 规则与 "disabled 不进入 active metadata" 规则同时存在，但 plan 未明确 parse 发生在哪个 gate。若 parse 在 discovery 阶段（ConfigLoader 或 provider discover_tools），disabled provider 会被跳过；若 parse 在 Service composition 阶段，当前 flow 也跳过 disabled provider。
- **直接证据**:
  - `_fins_awaiting_registry_inputs_from_provider_configs:1995` — `if not provider_config.enabled: continue`
  - plan §4.2 两句话紧邻但未区分 gate
- **影响**: 配置错误在 disabled→enabled 切换时才暴露，推迟了 fail-fast。严重性低因为生产 packaged config 中三 provider 均为 `enabled: true`
- **建议改法和验证点**:
  1. 明确 disabled provider parse gate：建议在 ConfigLoader 层或 provider discover_tools 入口对所有 provider（含 disabled）校验 `awaiting_resolution_mode` 的合法值（若存在）
  2. 或在 plan 中降级此规则为 "best-effort，只在 enabled provider 上强制 parse"，与现有代码行为一致
  3. 若选择保留该规则，S1 测试必须包含 disabled+illegal mode 的反例
- **修复风险**: 低
- **severity**: Low
- **status**: accepted-candidate

### F-03 — `ServiceAssemblyOverrides.wait_poller_policy` 删除后缺少显式替代通道 [Medium]

- **位置**: plan §5.2 "删除 `ServiceAssemblyOverrides.wait_poller_policy`，避免测试/调用方形成第二配置入口"；§6.2 "Service 基于 active typed modes 构造 activation registry、可选 poll registry和可选显式 Host policy"
- **问题类型**: 切片过粗
- **当前写法**: plan S2 删除 `ServiceAssemblyOverrides.wait_poller_policy`，S3 说 Service 自己构造 policy。但 plan 未描述替换的数据流：`compose_open_host_options` 当前从 `request.overrides.wait_poller_policy` 读取 policy 并直接传给 `OpenHostOptions(wait_poller_policy=...)`。删除该字段后，`compose_open_host_options` 需要新的 policy 真源。
- **反例/失败场景**: implementation agent 实现 S2 时删除了 `ServiceAssemblyOverrides.wait_poller_policy`，导致 `compose_open_host_options` 的 `wait_poller_policy=request.overrides.wait_poller_policy` 引用失败。agent 可能：
  - 在 S2 中临时创建一个新的内部传递路径（violating slice boundary）
  - 在 `compose_open_host_options` 内部直接读取 ConfigLoader 的 config（可能跨 S2/S3 边界）
  - 引入一个新的 intermediate type 作为替代通道
- **为什么有问题**: plan 把删除 override field（S2）和建立新 composition path（S3）分到两个 slice，但两个 slice 共享同一个数据流关键节点（`compose_open_host_options` 的 `OpenHostOptions` 构造）。S2 删除了输入端，S3 负责重建输出逻辑，中间存在一个 slice 边界上的空窗。
- **直接证据**:
  - `host_assembly.py:875` — `wait_poller_policy=request.overrides.wait_poller_policy`
  - plan §5.1 S2 allowed files 包含 `dayu/service/host_assembly.py`
  - plan §6.1 S3 allowed files 同样包含 `dayu/service/host_assembly.py`
  - 两者共享同一文件，意味着 S2 和 S3 不能完全独立验证 — S2 的改动会在 `compose_open_host_options` 中留下 broken reference，需要 S3 来修复
- **影响**: implementation agent 可能跨 slice 边界做临时兼容（如保留 field 但改类型、添加 deprecated marker），或把 S3 的 composition 逻辑提前到 S2
- **建议改法和验证点**:
  1. 承认 S2/S3 在 `host_assembly.py` 上有共享节点，将 `ServiceAssemblyOverrides.wait_poller_policy` 的删除和 `compose_open_host_options` 的 policy 构造合并到同一个 slice（S3），S2 只改 ConfigLoader 和 Host policy dataclass
  2. 或明确 S2 中 `compose_open_host_options` 的 `wait_poller_policy` 参数临时设为 `None`（disabled），S3 再激活完整 composition logic。但这要求 S2 测试接受 "poller 不启动" 的中间状态
  3. 最少改动：在 plan §5.2 和 §6.2 之间增加显式 handoff note，说明 S2 的 `host_assembly.py` 改动仅限于删除 `ServiceAssemblyOverrides` 字段声明及 `with_entrypoint_wait_poller_policy` 函数体，`compose_open_host_options` 的 `wait_poller_policy` 参数在 S2 仍然硬编码 `None`，S3 替换为 typed composition
- **修复风险**: 低 — 仅需 plan 文本澄清，不影响设计
- **severity**: Medium
- **status**: accepted-candidate

### F-04 — Plan §9 source scan 对内部算法常量的零命中预期可能过度 [Low]

- **位置**: plan §9 第二个 `rg` scan：`_DEFAULT_CLAIM_BATCH_SIZE|_POLL_CLAIM_TTL_SECONDS|...`
- **问题类型**: 测试缺口
- **当前写法**: plan §9 要求对 10 个模块常量名的 `rg` 扫描预期零命中。plan §11.3 在 umbrella 中又说 "与部署 policy 无关的内部算法常量可以保留，但任何数值命中必须逐条证明其语义不属于 wait_poller_policy"。
- **反例/失败场景**: 当前 `wait_adapter.py` 中有 `_POLL_ERROR_CODE_*` 系列常量（如 `_POLL_ERROR_CODE_ADAPTER_EXCEPTION = "adapter_exception"`）。这些是 error code 字符串常量，不是部署数值默认，不匹配 scan pattern，不会误命中。但若 implementation agent 删除了 `_DEFAULT_CLAIM_BATCH_SIZE` 等数值常量后，发现某些内部算法（如 claim batch size 的 minimum bound check）引用了它们，可能被迫保留。此时 scan 命中不是产品失败，而是需要 documented exception。
- **为什么有问题**: scan 的零命中预期是绝对化的，但 umbrella §11.3 的 "可以保留" 子句提供了例外。两条规则之间有细微张力：agent 可能为了满足零命中 scan 而删除仍有合理内部用途的常量，或者保留常量但无法通过 scan gate。
- **直接证据**:
  - umbrella plan §11.3: "与部署 policy 无关的内部算法常量可以保留，但任何数值命中必须逐条证明其语义不属于 wait_poller_policy"
  - plan §9 scan 预期 "零命中"
  - 当前代码中 10 个被扫描常量确实全部是部署默认值（由 `WaitPollerRuntimePolicy` 字段 defaults 引用），应全部删除
- **影响**: 低 — 当前代码中这 10 个常量确实是纯部署默认值，应该全部删除。仅当 implementation agent 发现未预见的内部依赖时可能产生 friction
- **建议改法和验证点**: 在 plan §9 添加 note：若 scan 命中但可逐条证明属于内部算法常量（非部署默认），不作为 plan failure，改为在 completion report 中记录 owner 和保留理由
- **修复风险**: 低
- **severity**: Low
- **status**: observation（风险很低，仅 plan 文本微调）

### F-05 — 测试迁移范围在 `ServiceAssemblyOverrides` 删除后缺少分类指导 [Low]

- **位置**: plan §7 测试与验证矩阵
- **问题类型**: 不可直接实施
- **当前写法**: plan §7 列出了完整测试文件列表和统一运行命令，但未说明 `ServiceAssemblyOverrides.wait_poller_policy` 删除后，现有测试如何分类迁移。
- **反例/失败场景**: 当前有大量测试构造 `ServiceAssemblyOverrides(wait_poller_policy=...)`：
  - `tests/service/test_host_assembly.py:326` — 显式传入 policy 并断言传递
  - `tests/service/test_host_assembly.py:335-431` — 两个测试验证 `with_entrypoint_wait_poller_policy` 的 scene-derived 行为
  - `tests/service/test_host_assembly.py:278-332` — 验证显式 override 传递

  这些测试在 S2/S3 实现后需要完全不同的断言逻辑（不再通过 override 传递 policy，而是验证 composition 直接读取 config）。plan 只说 "测试不得靠旧默认构造 policy"，但未分类指导：哪些测试删除、哪些重写、哪些迁移到新的 composition 验证。
- **为什么有问题**: implementation agent 可能机械删除旧测试而不补充新的 owner-level contract 测试，导致 coverage gap；或保留旧测试的 spirit 但用错误的 new API 重写，导致测试验证了错误的行为
- **直接证据**:
  - `tests/service/test_host_assembly.py:278-431` — 三个与 wait_poller_policy override 直接相关的测试
  - plan §7 只说 "新增/修改行为必须分别有 owner contract、传播、negative 和 composition 断言"
- **影响**: 测试迁移质量依赖 implementation agent 的判断，可能产生 coverage gap 或错误断言
- **建议改法和验证点**:
  1. 在 plan §7 或 §10 handoff 中增加测试迁移分类表：列出每个受影响的现有测试及其处置方式（删除/重写/保留但改断言）
  2. 明确新的 composition 测试应覆盖：config→policy→OpenHostOptions 完整链路、typed mode→registry decision、所有 §6.3 negative matrix 行
- **修复风险**: 低
- **severity**: Low
- **status**: observation（implementation agent 可从 plan §6.3 matrix 自行推导测试迁移，但 plan 可以更精确）

### F-06 — `_scene_selects_fins_awaiting_tools` 中 `selected_tool_names is None` 默认为全选 [已由 plan 覆盖]

- **位置**: plan §6.2 "scene all/select/none 不影响 Host opener"
- **问题类型**: 已覆盖
- **当前写法**: 当前代码 `_scene_selects_fins_awaiting_tools` 在 `selected_tool_names is None` 时返回 `True`（表示 scene 选择全部工具）。这意味着 scene 不显式限制工具时，自动启用 poller。plan 正确识别并计划删除此逻辑。
- **反例/失败场景**: 无 — plan 已明确删除此函数
- **直接证据**: `host_assembly.py:2046-2047` — `if selected_tool_names is None: return True`
- **severity**: No-fix（plan 已正确处置）

## Open Questions

1. **Q1**: plan §4.2 的非 Fins provider misconfig 规则，具体 owner 是 ConfigLoader（top-level provider entry typed validation）还是 Service composition（cross-provider config inspection）？Controller 已在 validation 中确认 allowlist 不扩展到非 Fins provider，但此规则的 enforcement boundary 仍需澄清。

2. **Q2**: plan §2 的 "packaged snapshot 固定为 `true, 1, 60, 100, 30, 2, 300, 1, 5, 30, 5, 8`" — 这些数值在当前代码的模块常量中（如 `_POLL_CLAIM_TTL_SECONDS = 60.0`），与 packaged config 一致。但 plan 未解释 `poll_interval_seconds=1`（当前 `WaitPollerRuntimePolicy.poll_interval_seconds` 默认也是 `1.0`）的来源和产品依据。是否所有 12 个 packaged 值都有产品依据？还是部分值沿用了当前代码默认？

3. **Q3**: plan §2 提到 "已审计 public boundary：`dayu.host.api` 的 runtime-checkable structural policy Protocol" — 这个 Protocol 是什么？当前代码中 `dayu/host/api.py` 是否有 `WaitPollerRuntimePolicy` 的 Protocol 定义？需确认此 Protocol 是否需要随 `WaitPollerRuntimePolicy` 的 required-field 改造而更新。

## Residual Risks

| Risk | Severity | Owner/Destination |
|------|----------|-------------------|
| F-01 non-Fins misconfig boundary 若未在 implementation 前澄清，可能导致该检查被遗漏或实现位置错误 | Medium | Controller adjudication 或 plan 修订 |
| F-03 S2/S3 共享 `host_assembly.py` 节点若未明确 handoff，可能导致跨 slice 临时兼容代码 | Medium | Controller 在 implementation handoff 时确认 |
| `WaitPollerRuntimePolicy` 12-field required 改造后，所有测试构造（含非 Host 测试的 fixture）需逐字段传入，遗漏会导致测试失败 | Low | Implementation agent 在 S2 逐文件核对 |
| callback transport 的 composition error 类型未在 plan 中指定（`ValueError` vs 自定义 exception） | Low | Implementation agent 可在 S3 选择合适类型，遵循现有 `host_assembly.py` 的异常惯例 |
| plan §9 source scan 若误命中内部算法常量（非部署默认），agent 可能过度删除 | Low | Implementation completion report 逐条归属 |

## Plan Source Scans 可满足性判断

逐一审查 plan §9 的 6 个 `rg` 命令：

1. `rg -n 'with_entrypoint_wait_poller_policy|_scene_selects_fins_awaiting_tools|WaitPollerRuntimePolicy\(\)'` — **可满足**。目标函数/构造全部在 allowlist 内删除；`WaitPollerRuntimePolicy()` 无参构造在 S2 删除 dataclass defaults 后自然消除。

2. `rg -n '_DEFAULT_CLAIM_BATCH_SIZE|...'` (10 个模块常量) — **可满足**。当前代码中这 10 个常量仅被 `WaitPollerRuntimePolicy` 字段 defaults 引用，删除 defaults 后不再被引用，可安全删除。

3. `rg -n 'awaiting_resolution_mode' dayu/config/tool_discovery.json dayu/fins/tools dayu/service tests` — **可满足**。命中应在 allowlist 内：`tool_discovery.json`（配置）、Fins tools（parser）、Service（typed consumption）、tests（验证）。

4. `rg -n 'wait_poller_policy|awaiting_resolution_mode' dayu/config/prompts dayu/config/execution_profiles.json` — **可满足**。这些概念不应该进入 prompt 或 execution profile，预期零命中。

5. `rg -n 'from dayu\.(engine|host|service|ui|fins)|import dayu\.(engine|host|service|ui|fins)' dayu/runtime` — **可满足**。当前 `dayu/runtime` 无反向 import，S2 仅在 ConfigLoader 新增 layer-neutral typed config，不引入业务层依赖。

6. `git diff --name-only f7006a80 --` + 二次扫描 `authorization|permission|...` — **可满足**。三 slices allowlist 完整且不触及 R05/R06 等后续范围。

## Final Plan Review Conclusion

**Verdict: `pass-with-risks`**

Plan 的语义 owner 分配、三 slice 结构、composition matrix、typed propagation、default/fallback removal、scene independence 和验证门禁均基于充分的直接代码证据，可以交给 implementation agent。

3 个 accepted-candidate findings（F-01、F-02、F-03）涉及边界澄清和 slice 间 handoff 精确性，建议 Controller 在授权 implementation 前裁决，但不构成结构性阻断。

2 个 observation 级发现（F-04、F-05）属于 plan 文本微调建议，不影响实施可行性。

F-06 和 3 个 open questions 为已覆盖项或澄清请求，不构成 finding。

### Finding Summary

| Finding | Severity | Status |
|---------|----------|--------|
| F-01 Non-Fins provider mode misconfig owner 边界不清 | Medium | accepted-candidate |
| F-02 Disabled provider parse 边界未落地 | Low | accepted-candidate |
| F-03 ServiceAssemblyOverrides 删除后 S2/S3 共享节点 | Medium | accepted-candidate |
| F-04 Source scan 零命中预期过度 | Low | observation |
| F-05 测试迁移范围缺少分类指导 | Low | observation |
| F-06 Scene None=全选逻辑已由 plan 覆盖 | — | no-fix |

**Total**: 3 accepted-candidate, 2 observation, 1 no-fix, 3 open questions

### Blocking Questions for Controller

1. Q1: non-Fins provider mode misconfig 的 enforcement boundary 确认为何？
2. Q3: `dayu/host/api.py` 的 runtime-checkable policy Protocol 需要随 required-field 改造更新吗？
