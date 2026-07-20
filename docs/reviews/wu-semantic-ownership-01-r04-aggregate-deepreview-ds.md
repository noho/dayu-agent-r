# WU-SEMANTIC-OWNERSHIP-01 / R04 Aggregate Deepreview — AgentDS

## Scope

- **Review type**: Aggregate adversarial deepreview（第二路独立，不依赖 MiMo 结论）
- **Work unit**: Existing umbrella `WU-SEMANTIC-OWNERSHIP-01` R04 continuation
- **Product range**: `f7006a80` (R03 accepted base) → `9e349ac4` (R04 accepted product commit)
- **Control-only HEAD**: `c2a40929` (aggregate validation transition)
- **Branch**: `phaseflow/host-issues-control`
- **Reviewer**: AgentDS
- **Output file**: `docs/reviews/wu-semantic-ownership-01-r04-aggregate-deepreview-ds.md`
- **Review date**: 2026-07-15T19:46:49+08:00
- **Documents read**: `AGENTS.md`, controller discussion, `docs/host/design.md`, `docs/engine/design.md`, `docs/tool/design.md`, `docs/fins/design.md`, `docs/ui/design.md`, R04 accepted plan, R04-S1 implementation/Controller validation/F01 fix/re-validation/dual code review/Controller adjudication, `docs/reviews/wu-semantic-ownership-01-r04-aggregate-validation.md`
- **Included scope**:
  - 全部 11 个 R04 production/config changed files (`dayu/config/tool_discovery.json`, `dayu/config/host_runtime.json`, `dayu/fins/tools/`, `dayu/host/wait_adapter.py`, `dayu/runtime/config_loader.py`, `dayu/service/`)
  - 全部 11 个 test/smoke changed files
  - 5 个 README changed files
  - F01 fix 授权的 4 个 derived consumer files
  - Aggregate composite chain: config → Fins owner parser → runtime typed config → Service discovery/typed metadata/derived consumers → Host policy/poller → prompt/interactive/public Host
  - Current uncommitted aggregate validation/control state (`docs/host/issues-implementation-control.md`, `docs/reviews/wu-semantic-ownership-01-r04-aggregate-validation.md`)
- **Excluded scope**: Engine, Host public API/open_host, callback transport, R05 state machine, Issue 175, Issue 142/151/177/178, permission schema, design/control documents（除非作为 evidence chain 阅读）
- **Explicit non-R04 boundaries**: Topic 8/9 no-code; R05 observation-timeout/LOST fix; Issue 175 process isolation; callback transport; Host public API/open_host; unified authorization; permission schema; Issue 142/151/177/178. 现有 `allowed_paths`、Web defense、containment/symlink、DNS/peer、resource budgets、atomic write、cancel/durable wait/process fencing 不得被削弱。

## Verification

```text
验证方法: 只读代码走读 + adversarial failure pass + source scan
验证范围: 完整 composite chain config→Fins→runtime→Service→Host→prompt/interactive/public
```

Controller aggregate validation 已独立运行 accepted-plan complete 509-test matrix 并通过（`docs/reviews/wu-semantic-ownership-01-r04-aggregate-validation.md` §3）；本 review 不再单独运行测试。

## Prior Finding Final Status Re-verification

### R04-S1-CV-F01 — closed at aggregate boundary

**Re-verification result: CLOSED / NO DRIFT.**

独立逐项核查（与 R04-S1 code review DS 的 F01 closure verification 一致，并在 aggregate composite chain 上做了额外验证）：

1. `ServiceDiscoveredTools.fins_awaiting_runtime`（`host_assembly.py:272`）与 `_fins_awaiting_providers`（`:273`）均无默认值——漏传由 pyright `reportCallIssue` 在开发期拒绝。
2. 全仓 Python source scan 确认只有 `host_assembly.py:510`（`discover_service_tools`）一处 `ServiceDiscoveredTools(...)` 直接构造——即 discovery owner。
3. 四个 authorized derived consumers 均使用 `dataclasses.replace(...)`：
   - `tests/tools/test_combined_tools_acceptance.py`
   - `utils/smoke_host_public_conversation_memory.py`
   - `utils/smoke_host_public_conversation_memory_scenarios.py`
   - `utils/smoke_host_public_multiturn.py`
4. 四个派生点均无对私有 metadata field 的重解析、raw `awaiting_resolution_mode` 解析或直接 `ServiceDiscoveredTools(...)` 重构。
5. Aggregate validation smoke（Controller §5）通过 public Host registry resolution 验证 `not_ready=1 → ready=1 → SUCCEEDED → outbox_terminal_match=true`，不读取私有字段。
6. Full pyright: `0 errors, 0 warnings, 0 informations`。

### DS-F01 — observation timeout currently terminalizes as LOST

**Re-verification result: STILL DEFERRED TO R05 / NO REGRESSION.**

代码证据不变：`wait_adapter.py:1102-1114` 仍对 `WaitObservationTimedOut` 调用 `_resolve_claimed_wait(record, timeout_result)` 将 wait/Run terminalize 为 `LOST`。Controller discussion Topic 5 最终裁决（line 426）与 `docs/host/design.md` line 2425-2427 均要求本次 observation timeout 应 release-with-backoff 而非 call `resolve_wait`。

- **R04 scope**: 不修改此路径。accepted plan §1 明确排除 "R05 observation-timeout / retry-backoff / LOST 状态机"。
- **R04 status**: deferred-to-R05 / no current fix。R04 范围内的 deferred-scope added-line scan（`observation_timeout|ResolveWaitLostOutcome`）零新增命中，确认未偷带 R05 实现。
- **Risk**: 若 R05 实施前该路径被当作正确终态引用，会扩散错误语义。当前代码注释和 design.md 均已明确记录正确行为，该风险可控。
- **Residual owner**: R05（mandatory before umbrella final closeout）。

### DS-F02 — future provider identity OR matching

**Re-verification result: STILL REJECTED-WITH-REASON / NO CHANGE.**

Controller adjudication 的裁决理由在 aggregate composite chain 上重新验证：

- `_fins_awaiting_tool_name_from_provider_config`（`host_assembly.py:2126-2154`）与 `_is_recognized_non_awaiting_provider_config`（`:2157-2177`）使用同一 OR identity 规则（`provider_id in SET or import_path in SET or source_id in SET`），该规则是既有 Service identity ownership 的延续，不是 R04 引入的新 pattern。
- 三个维度的常量集合（`_FINS_DOWNLOAD_PROVIDER_IDS`、`_FINS_DOWNLOAD_IMPORT_PATHS`、`_FINS_DOWNLOAD_SOURCE_IDS` 等）是具体的字符串字面量（如 `"financial-download-tools"`、`"dayu.fins.tools.download_provider"`），不是通配或前缀模式。未来 provider 同时命中三个维度中任一的概率极低。
- 即使发生误匹配，Service 装配期的 fail-fast 语义（`ValueError`）会将误匹配暴露为配置错误而非静默错误行为。
- 测试 `test_unknown_third_party_provider_mode_field_remains_opaque` 已证明未知 provider 保持 opaque。
- 改为精确三元组 conjunctive matching 会改变既有 identity contract（当前 `or` 语义允许单维度匹配就识别 built-in provider），可能破坏既有 identity alias 路径，且没有当前产品需求支撑。

**不变。**

## Findings

以下 findings 按 severity 排序。每个 finding 必须包含直接代码/数据证据、severity、owner、failure path 和最小正确修复。

---

### DS-AGG-F01 — 未修复 — 低 — `_fins_awaiting_metadata_by_spec_id` 在一次调用中被用于 pure-validation-only，返回值被丢弃；同一 dict 在 `_tool_discovery_bindings` 中重复构造

- **入口/函数**: `_fins_awaiting_provider_metadata_from_configs` → `_fins_awaiting_metadata_by_spec_id`
- **文件(行号)**: `dayu/service/host_assembly.py:1230`, `dayu/service/host_assembly.py:1289`
- **输入场景**: 正常 provider discovery flow
- **实际分支**: `_fins_awaiting_provider_metadata_from_configs`（`:1230`）调用 `_fins_awaiting_metadata_by_spec_id(result)` 但丢弃返回值——仅用于抛出 `ValueError("duplicate Fins awaiting provider id")`。随后 `_tool_discovery_bindings`（`:1289`）再次调用同一函数构造实际使用的 index。
- **预期行为**: 如果重复 spec id 确实是需要 fail-fast 的 invariant，validation call 是合理的设计。但两次调用构造了相同 dict 两次——这不是 correctness 问题，但表明 validation concern 与 indexing concern 在同一函数内被分别调用而非复用。
- **实际行为**: 同一 pure function 在同一次 assembly 中被调用两次，第一次结果被丢弃。功能正确，无数据漂移风险（两次调用的输入 tuple 相同）。
- **直接证据**: `host_assembly.py:1230`（返回值赋给 `_fins_awaiting_metadata_by_spec_id(result)` 后无使用）与 `:1289`（`metadata_by_spec_id = _fins_awaiting_metadata_by_spec_id(fins_awaiting_providers)` 实际使用）
- **影响**: 低——仅轻微性能冗余（O(n) dict 构造一次多余），不影响 correctness。typed metadata tuple 是唯一真源，两次调用之间不会发生突变。
- **建议改法和验证点**: 将 validation call 改为直接检查 `len({item.spec_id for item in result}) == len(result)`，或让 `_fins_awaiting_metadata_by_spec_id` 的调用方复用第一次调用的结果。不需要修改 public contract。
- **修复风险（低）**: 局部重构，不改变外部行为
- **严重程度（低）**: 纯内部冗余，不构成 correctness/security/ownership 风险

---

## Aggregate Chain Adversarial Failure Pass

以下按 composite chain 顺序做 adversarial pass，逐段记录结论。未发现 material finding 的段标注"无 finding"。

### 1. Config → Fins Owner Parser (provider mode)

**链路**: `tool_discovery.json` `awaiting_resolution_mode: "poll"` → `ToolDiscoveryProviderConfig.config` (raw dict) → `parse_awaiting_resolution_mode(config)` → `AwaitingResolutionMode(StrEnum)` → typed mode 进入 `_FinsAwaitingProviderMetadata.mode`

**Verification**:
- `AwaitingResolutionMode`（`_ingestion_tool_helpers.py:27-32`）为 `poll/callback/manual` 三成员 `StrEnum` 闭集——不可通过非 member 构造
- `parse_awaiting_resolution_mode`（`:35-65`）依次检查：字段存在于 config → `isinstance(value, str)`（拒绝 None/bool/int/list/dict） → `AwaitingResolutionMode(value)`（拒绝空串/大小写变体/未知值）。无 default、无 fallback
- 三个 Fins direct provider（`download_provider.py`、`preprocess_provider.py`、`upload_provider.py`）在构造 runtime 前调用同一 parser——直接 provider discovery 路径也校验 owner contract
- packaged config 三 provider 均为 `"poll"`

**Adversarial checks**:
- bool 冒充字符串：`isinstance(True, str)` 为 `False` → 正确拒绝
- null/None → 字段存在但 `not isinstance(value, str)` 拒绝
- 空字符串 `""` → `StrEnum("")` 失败
- 大小写变体 `"POLL"` / `"Poll"` → `StrEnum("POLL")` 失败
- 数字 `1` / `0` → `not isinstance(value, str)` 拒绝
- `config` 为 empty dict → `AWAITING_RESOLUTION_MODE_CONFIG_FIELD not in config` 失败

**无 finding**。

### 2. Runtime ConfigLoader Strict Typed Parse

**链路**: `host_runtime.json` `wait_poller_policy: {...}` → `_parse_wait_poller_runtime_policy` → `WaitPollerRuntimePolicyConfig` (frozen, all-fields-required dataclass) → `HostRuntimeProfileConfig.wait_poller_policy`

**Verification**:
- `_parse_wait_poller_runtime_policy`（`config_loader.py:1972-2040`）使用 `_require_exact_fields` 校验 12 字段 exact-shape，拒绝缺失和多余字段
- `_require_bool_field` 用于 `enabled`：`isinstance(value, bool)` 拒绝 int 1/0
- `_require_positive_int_field` 用于 `claim_batch_size`、`max_outstanding_adapter_calls`：先 `isinstance(value, bool)` 拒绝 bool → `isinstance(value, int)` → `value <= 0` 拒绝零和负数
- `_require_positive_float_field` 用于其余 9 个数值字段：`isinstance(value, bool)` 拒绝 → `isinstance(value, (int, float))` 接受 → `is_finite_number(value)` 拒绝 NaN/Infinity → `is_positive_finite_number(value)` 拒绝零和负数
- `WaitPollerRuntimePolicyConfig` 是 frozen/slots dataclass，13 字段全部 required，无默认
- `HostRuntimeProfileConfig.wait_poller_policy` 类型为 `WaitPollerRuntimePolicyConfig`（非 Optional）——JSON block 缺失时 `_parse_host_runtime_profile` 会因 `KeyError` fail

**Adversarial checks**:
- JSON `NaN`/`Infinity`/`-Infinity` 字面量 → `json.loads` 的 `parse_constant=_reject_non_finite_json_constant` 拒绝
- 解析后的非有限浮点数 → `_require_float_field` → `is_finite_number` 拒绝
- `enabled: 1` → `_require_bool_field` 拒绝（`isinstance(1, bool)` 为 `False`，但 `isinstance(1, int)` 为 `True`，因此正确报 `"must be bool"`）
- `claim_batch_size: true` → `_require_positive_int_field` → `isinstance(True, bool)` 拒绝
- `poll_interval_seconds: 0` → `_require_positive_float_field` → `is_positive_finite_number` 拒绝
- JSON block 完全缺失 → `KeyError`（ConfigLoader parent parser 在 `wait_poller_policy` key 缺失时 fail）
- 多余字段 → `_require_exact_fields` 拒绝

**无 finding**。

### 3. Host Policy Value Object (no defaults)

**链路**: `WaitPollerRuntimePolicyConfig` → `_wait_poller_runtime_policy_from_config` → `WaitPollerRuntimePolicy` (Host value object)

**Verification**:
- `WaitPollerRuntimePolicy`（`wait_adapter.py:397-481`）12 字段全部 required，无默认值。`__post_init__` 校验全部字段：
  - `enabled` 必须是 `bool`
  - `claim_batch_size` 与 `max_outstanding_adapter_calls` 必须是非 bool 正整数
  - 其余 9 个必须是正浮点数
- `WaitPoller.__init__`（`:927-978`）`policy` 参数为 required keyword `WaitPollerRuntimePolicy`，无 `| None`
- `WaitPollerSupervisor.__init__`（`:1607-1642`）`policy` 参数为 required keyword `WaitPollerRuntimePolicy`
- 十个旧部署默认常量扫描：零命中
- 旧 `WaitPollerRuntimePolicy()` 无参构造扫描：零命中

**无 finding**。

### 4. Service Typed Discovery → Metadata → Derived Consumers

**链路**: `discover_service_tools` → `_fins_awaiting_provider_metadata_from_configs` → `_FinsAwaitingProviderMetadata` (frozen, all-required) → `ServiceDiscoveredTools._fins_awaiting_providers` (required, no default) → derived consumers via `dataclasses.replace(...)`

**Verification**:
- `_fins_awaiting_provider_metadata_from_configs`（`host_assembly.py:1189-1231`）按 plan 完整执行：遍历全部 configs → provider identity routing → disabled+illegal fail-fast → mode parse → enabled filter → metadata construct → dedup check
- `_FinsAwaitingProviderMetadata`（`:388-407`）frozen/slots，7 字段全部 required
- `ServiceDiscoveredTools._fins_awaiting_providers` 无默认值——漏传由 pyright 拒绝
- 三个 registry builder（`_fins_wait_adapter_registry_from_provider_metadata`、`_fins_wait_activation_registry_from_provider_metadata`、`_fins_wait_poll_adapter_registry_from_provider_metadata`）均从 typed metadata 构造，不重读 raw config
- `_tool_discovery_bindings`（`:1270-1324`）使用 typed `_FinsAwaitingProviderCallable` 包装 metadata+runtime，不重读 raw config
- `_tooling_options_from_discovery`（`:1968-2023`）接收 typed metadata tuple 而非 raw `provider_configs`
- 旧 `_fins_awaiting_registry_inputs_from_provider_configs` 已删除

**Adversarial propagation checks**:
- F01 关闭验证：唯一 constructor 在 discovery owner，全部派生消费者用 `dataclasses.replace(...)`
- `_fins_awaiting_metadata_by_spec_id` 在 `_fins_awaiting_provider_metadata_from_configs:1230` 被调用用于 dedup validation，返回值丢弃；在 `_tool_discovery_bindings:1289` 再次调用构造实际 index——两次调用之间输入 tuple 相同，无数据漂移风险（见 DS-AGG-F01）
- `_active_fins_awaiting_provider_metadata` 在 `_tool_discovery_bindings` 之前二次过滤（只保留 `tool_name in available_tool_names` 的 metadata），registry builder 接收的是二次过滤后的结果
- Scene selection（all/select/none）不参与 `_compose_options` 的 poller policy 决策——`_compose_options` 只从 `request.discovered_tools._fins_awaiting_providers` 取 typed metadata

**无 material finding**（DS-AGG-F01 为低严重度内部冗余）。

### 5. Service Composition → Host Policy

**链路**: `_compose_options` → `_wait_poller_policy_for_composition` → `_wait_poller_runtime_policy_from_config` → `WaitPollerRuntimePolicy` → `OpenHostOptions.wait_poller_policy`

**Verification**:
- `_compose_options`（`host_assembly.py:754-879`）的完整分支逻辑：
  1. `worker_backend != "local"` → `ValueError`
  2. `any(mode is CALLBACK)` → `ValueError("authenticated callback transport")`（pre-open fail-closed）
  3. `_tooling_options_from_discovery(...)` → 构造 `HostToolingOptions`（含三个 registry）
  4. `_wait_poller_policy_for_composition(...)` → 决定 `wait_poller_policy`
  5. 若 active poll → policy enabled → 但 poll registry 缺失/空 → `ValueError`（fail before open_host）

- `_wait_poller_policy_for_composition`（`:882-917`）：
  - 无 active POLL mode → 返回 `None`（不传 policy）
  - 有 active POLL mode → 一对一构造 policy → 若 enabled 则 check registry → 若 registry 缺失则 fail
  - policy disabled 时仍传递给 Host，由 Host 既有分支不启动

- `_wait_poller_runtime_policy_from_config`（`:920-945`）：逐字段一对一投影，不加默认，不修改值

- `ServiceAssemblyOverrides.wait_poller_policy` 已删除
- `with_entrypoint_wait_poller_policy` 与 `_scene_selects_fins_awaiting_tools` 已删除

**Adversarial matrix checks**（与 plan §6.3 对照）:
| active modes / runtime | registry / transport | 代码路径 | 预期 |
|---|---|---|---|
| 无 active awaiting provider | 无 poll registry | `_wait_poller_policy_for_composition:897-901` 返回 `None` | 不传 policy |
| 仅 manual | poll registry 无 | `:897-901` 返回 `None`；`_fins_wait_poll_adapter_registry_from_provider_metadata:2111-2115` 过滤 poll-only，manual 不进入 | 不传 policy |
| 仅 poll, enabled | poll registry 非空 | `:902-917` 构造 policy → check registry → 传入 | 启动 poller |
| poll+manual, enabled | poll registry 仅 poll | `_fins_wait_poll_adapter_registry_from_provider_metadata` 只取 mode=poll；`_wait_poller_policy_for_composition` 看到 active poll → 启动 | 只 claim POLL |
| active poll, disabled | poll registry 可构造 | `:902-917` 构造 disabled policy → 传入 Host | Host 不启动 |
| active poll, enabled, registry 缺失/空 | 缺失/空 | `:909-916` `registry is None or resolve_adapter is None` → `ValueError` | fail before open_host |
| 任意 callback | 无 transport | `:785-792` `any(mode is CALLBACK)` → `ValueError` | fail before open_host |
| disabled provider (legal mode) | 不 active | `_fins_awaiting_provider_metadata_from_configs:1218-1219` `not enabled → continue` | 不创建 binding |
| scene 选 all/select/none | active provider/policy/registry 不变 | `_compose_options` 只取 `_fins_awaiting_providers`，不读 scene | 决策一致 |

**无 finding**。

### 6. Prompt/Interactive Entrypoint Path

**链路**: `prepare_entrypoint_runtime` → `discover_service_tools` → `compose_open_host_options` → 同一 composition path

**Verification**:
- `prepare_entrypoint_runtime`（`entrypoint_runtime.py:494-545`）对 prompt 与 interactive 调用同一 `discover_service_tools` 与 `compose_open_host_options`
- 不再调用已删除的 `with_entrypoint_wait_poller_policy`
- Aggregate validation smoke（Controller §5）验证 `prompt_interactive_same=true`
- `entrypoint_runtime.py` 不拥有 poller policy 决策——只把 assembly 结果传给调用方

**无 finding**。

### 7. Public Host Poller Execution

**链路**: `open_host(options)` → `OpenHostOptions.wait_poller_policy` → poller lifecycle

**Verification**:
- Host public API（`dayu/host/api.py`、`dayu/host/open_host.py`）未修改
- `OpenHostOptions.wait_poller_policy: WaitPollerRuntimePolicy | None` 保持不变
- `None` 表示不启动 poller；disabled policy 传入后 Host 既有分支不启动

**无 finding**（R04 不修改 Host public API）。

### 8. LLM-Facing Leakage

**审查目标**: tool schema、prompt assets、Host/Service projection 是否泄漏内部治理标识

**Verification**:
- `awaiting_resolution_mode` 不出现于 `dayu/config/prompts/` 或 `dayu/config/execution_profiles.json`（source scan 零命中）
- `wait_poller_policy` 不出现于 prompt assets 或 execution profiles（source scan 零命中）
- `_FinsAwaitingProviderMetadata` 中的 `provider_id`、`version_ref`、`source_id`、`spec_id` 用于 Host 内部 binding/registry，不进入 LLM-facing material
- tool schema 的 name/description/参数说明未修改
- `_operation_kind_from_tool_name` 的 download/preprocess/upload 结构映射保持不变——该映射用于 observation handle 恢复，不是 LLM-facing 语义

**无 finding**。

### 9. Layering / Reverse Dependency

**审查目标**: `dayu.runtime` 是否反向依赖上层，Service → Host → Fins 方向是否正确

**Verification**:
- `dayu.runtime.config_loader` 新增 `WaitPollerRuntimePolicyConfig`，只 import `dayu.runtime.numeric`（标准库 helper），不 import Host/Fins/Service/Engine
- `dayu.fins.tools._ingestion_tool_helpers` 新增 `AwaitingResolutionMode` 与 `parse_awaiting_resolution_mode`，只 import `dayu.contracts.json_value`（公共契约）
- `dayu.service.host_assembly` import `dayu.fins.tools._ingestion_tool_helpers` 与 `dayu.runtime.config_loader`，符合 `Service → Fins/Runtime` 方向
- `dayu.service.fins_wait_adapter` import `dayu.fins.tools._ingestion_tool_helpers.AwaitingResolutionMode`，符合 `Service → Fins` 方向
- `dayu.host.wait_adapter` 无新增 import
- Runtime reverse-import scan（`from dayu.(engine|host|service|ui|fins)`）：零命中

**无 finding**。

### 10. Security Retention

**审查目标**: 现有安全机制是否被删除、弱化或绕过

**Verification**:
- Deferred-scope added-line scan：`authorization|permission|process_backed|subprocess|observation_timeout|ResolveWaitLostOutcome` —— 零新增命中（R04 diff 中仅 `wait_adapter.py` 既有 observation-timeout→LOST 路径存在，非本次新增）
- 十个 Host deployment default 常量扫描：零命中（已全部删除）
- 旧 entrypoint/scene helper 扫描（`with_entrypoint_wait_poller_policy`、`_scene_selects_fins_awaiting_tools`）：零命中（已全部删除）
- prompt/execution profile 污染扫描：零命中
- `dayu/host/api.py`、`dayu/host/open_host.py`：未修改
- 现有 `allowed_paths`、Web egress/DNS/peer/resource defense、path containment、symlink rejection、atomic write、process fencing、cancel/durable wait 机制均未删除或弱化

**无 finding**。

### 11. README Consistency

**审查目标**: 5 个 README 更新是否与实现一致、是否在各自职责范围内

**Verification**:
| README | 修改内容 | 一致性 |
|---|---|---|
| `dayu/config/README.md` | 新增 12 字段 policy block 与 provider mode 配置契约 | 与实现一致 |
| `dayu/host/README.md` | 新增 config-owned 显式 policy 与 Host 无 deployment defaults | 与实现一致 |
| `dayu/service/README.md` | 删除 scene-selected auto policy，改为 typed composition | 与实现一致 |
| `dayu/fins/README.md` | 新增 provider-owned mode、parser 与 registry 行为 | 与实现一致 |
| `tests/README.md` | 新增 ConfigLoader/Fins/Service/Host 矩阵与 derived discovery invariant | 与实现一致 |
| 根 `README.md` | 未修改 | 正确——入口、命令、工作流未变 |
| `dayu/README.md` | 未修改 | 正确——分层关系未变 |

**无 finding**。

### 12. Deferred Issue/Scope Boundary

**审查目标**: R05、Issue 175、callback transport、Issue 142/151/177/178、permission schema、unified authorization 是否被偷带

**Verification**:
| deferred item | R04 状态 | 证据 |
|---|---|---|
| R05 observation-timeout/retry-backoff/LOST | 未实现 | added-line scan 零命中；既有路径在 base commit 已存在 |
| Issue 175 Fins Docling process isolation | 未触碰 | diff 中零命中 |
| Callback transport 本体 (WU-WAIT-01 / #89) | 未实现 | pre-open fail-closed 是正确行为；无新增 transport |
| Host public API/open_host | 未修改 | `dayu/host/api.py`、`dayu/host/open_host.py` 未在 diff 中 |
| Unified tool authorization / permission schema | 未实现 | added-line scan 零命中 |
| Issue 142/151/177/178 | 未触碰 | diff 中零命中 |
| Topic 8 Engine 240 chars (no-code) | 不适用 | no-code item |
| Topic 9 Tool security wording (no-code) | 不适用 | no-code item |
| Browser storage-state lifecycle (Issue #178) | 未触碰 | diff 中零命中 |

**无 finding**。

### 13. Test Self-Proving

**审查目标**: tests 是否真正证明关键行为，测试断言是否适配实现而非反之

**Verification**（基于 Controller aggregate validation 的 per-file coverage 与 MiMo/DS R04-S1 测试有效性审查）:

- `test_fins_ingestion_tools.py`: 覆盖三模式 parser、8 种非法输入、三个 provider 直接 discovery、disabled+illegal fail-fast、recognized non-awaiting 字段误用、unknown third-party opaque
- `test_config_loader.py`: 覆盖 12 字段 exact-shape、bool/int 边界、NaN/Infinity、零/负数、缺失/多余字段
- `test_host_assembly.py`: 覆盖完整 composition matrix（plan §6.3 全部 14 行）、scene independence、derived discovery preservation
- `test_fins_wait_adapter.py`: 覆盖 typed mode→WaitResumePolicy 精确映射、`_operation_kind_from_tool_name` 结构映射稳定性
- `test_wait_adapter_polling.py`: 覆盖 Host policy 构造、旧默认删除
- Smoke: 覆盖 prompt/interactive equality、packaged composition → public Host → poller → terminal SUCCEEDED → outbox match
- 每文件 coverage >=80%（Controller §3）

**无 finding**。

## Open Questions

- 无。所有设计决策已在 Controller discussion 中裁决，所有实现 contract 已在 accepted plan 中定义，所有 deferred scope 已有明确 owner。

## Residual Risk

| risk | owner | severity |
|---|---|---|
| Observation-timeout→LOST terminalize（DS-F01） | R05 deferred scope | 中 — code 与 design 矛盾，R05 mandatory before umbrella closeout |
| `_fins_awaiting_metadata_by_spec_id` double-construct（DS-AGG-F01） | R04 internal | 低 — 纯内部冗余，不影响 correctness/security/ownership |
| `_is_recognized_non_awaiting_provider_config` OR matching（DS-F02） | 未来 provider 扩展 | 低 — speculative，Controller rejected |
| Callback 正向 transport 未实现 | WU-WAIT-01 / #89 | 信息 — pre-open fail-closed 是正确当前行为 |
| 外部 LLM/网络 smoke 未执行 | 本任务显式约束 | 信息 — packaged local smoke 已覆盖 assembly→public Host 完整路径 |
| Controller discussion Topic 5 要求 "observation timeout → release-with-backoff, not resolve_wait" 与当前代码矛盾 | R05 mandatory | 信息 — 为 R05 入口提供精确修复目标 |

## Verdict

**PASS / READY_FOR_DUAL_AGGREGATE_DEEPREVIEW_CONCURRENCE.**

R04 的 aggregate composite chain（config → Fins owner parser → runtime typed config → Service discovery/typed metadata/derived consumers → Host policy/poller → prompt/interactive/public Host）经 adversarial failure pass 逐段审查：

1. **Provider mode ownership**：Fins `AwaitingResolutionMode(StrEnum)` + `parse_awaiting_resolution_mode` 是唯一 parser，无默认、无 fallback。三个 direct provider 在构造 runtime 前调用同一 parser。Service 对 disabled provider 同样 fail-fast。

2. **Runtime policy ownership**：`host_runtime.json` `wait_poller_policy` 为 12 字段完整 required snapshot。ConfigLoader 做层中立 exact-shape strict typed parse，bool/NaN/Infinity/零/负/多余字段均 fail closed。Host policy value object 无默认构造、无 `None` fallback，十个旧部署常量已全部删除。

3. **Service typed composition**：`_FinsAwaitingProviderMetadata`（frozen, all-required）是 discovery owner 的唯一 typed metadata 真源。全部 registry builder、binding constructor 与 `_tooling_options_from_discovery` 均从 typed metadata 消费，不重读 raw config。三个 registry 正确按 mode 分区（activation=all, poll adapter=poll-only）。Callback fail-closed before open_host。Policy enabled + registry 缺失 fail before open_host。Scene selection 不参与 poller policy 决策。`ServiceAssemblyOverrides.wait_poller_policy` 与 `with_entrypoint_wait_poller_policy` 已删除。

4. **R04-S1-CV-F01**：在 aggregate boundary 确认已关闭——`ServiceDiscoveredTools` 的 required construction invariant + unique discovery owner constructor + `dataclasses.replace(...)` 派生传播 + public-composition regression test + full pyright。

5. **DS-F01**：code 与 design 矛盾不变，deferred to R05 mandatory owner。R04 未偷带 R05 修复。

6. **DS-F02**：Controller rejected-with-reason 的裁决在 aggregate chain 上重新验证，维持不变。

7. **No regression**：所有 deferred scope（R05、Issue 175、callback transport、permission schema、Issue 142/151/177/178）均无偷带。现有安全机制完整保留。LLM-facing 文本无泄漏。分层依赖无反向。README 一致。

8. **DS-AGG-F01**：一个新发现的低严重度内部冗余 finding——`_fins_awaiting_metadata_by_spec_id` 在一次调用中被用于 pure-validation-only，同一 dict 在下游重复构造。不影响 correctness，不阻塞 R04 完成。
