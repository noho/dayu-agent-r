# WU-SEMANTIC-OWNERSHIP-01 / R04 aggregate deepreview — AgentMiMo

## 1. Gate identity

- Active work unit: existing umbrella `WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation.
- Internal remediation sub-WU: R04 `awaiting provider resolution composition`.
- Accepted plan commit: `983070dd`.
- Accepted R04-S1 implementation commit: `9e349ac4`.
- Control-only transition HEAD: `c2a40929`.
- Review base: R03 accepted base `f7006a80` to R04 accepted `9e349ac4`, plus uncommitted control state.
- Review date: 2026-07-15T19:46:54+08:00.

本 artifact 是 aggregate deepreview 的 MiMo 路输出。Reviewer 不做最终 Controller 裁决。

## 2. Review scope and method

从配置→Fins owner parser/direct provider→runtime typed config→Service discovery/typed metadata/derived consumers→Host policy/poller→prompt/interactive/public Host 的完整组合链做 adversarial failure pass。逐文件走读以下生产文件：

| 文件 | 行数 | 覆盖状态 |
|---|---:|---|
| `dayu/runtime/config_loader.py` | 2754 | 完整覆盖 |
| `dayu/service/host_assembly.py` | 2350 | 完整覆盖 |
| `dayu/fins/tools/_ingestion_tool_helpers.py` | 297 | 完整覆盖 |
| `dayu/host/wait_adapter.py` | 2308 | 完整覆盖 |
| `dayu/service/fins_wait_adapter.py` | 639 | 完整覆盖 |
| `dayu/config/host_runtime.json` | 37 | 完整覆盖 |
| `dayu/config/tool_discovery.json` | diff | 完整覆盖 |
| `dayu/fins/tools/download_provider.py` | diff | 完整覆盖 |
| `dayu/fins/tools/preprocess_provider.py` | diff | 完整覆盖 |
| `dayu/fins/tools/upload_provider.py` | diff | 完整覆盖 |

同时读取了完整的 R04 证据链（plan review/review/re-review/adjudication、S1 implementation/validation/fix/re-validation/code review/controller adjudication、aggregate validation）和 controller discussion。

## 3. Findings

未发现实质性问题。

## 4. Adversarial failure pass 逐项验证

### 4.1 配置层：ConfigLoader typed projection

**验证结论：通过。**

- `dayu/config/host_runtime.json` 包含完整 12 字段 `wait_poller_policy`，无缺省值。
- `dayu/config/tool_discovery.json` 中三个 Fins awaiting provider 均显式声明 `awaiting_resolution_mode: "poll"`。
- `ConfigLoader._parse_wait_poller_runtime_policy`（config_loader.py:1972-2040）使用 `_require_exact_fields` 强制 12 个字段全部存在，每个数值字段经 `_require_positive_float_field` 或 `_require_positive_int_field` 校验。
- `_require_int_field`（config_loader.py:2750-2753）和 `_require_float_field`（config_loader.py:2643-2648）均先检查 `isinstance(value, bool)` 再检查 `isinstance(value, int/float)`，正确拒绝 `bool` 冒充数值。
- JSON 解析使用自定义 `parse_float=_parse_finite_json_float` 和 `parse_constant=_reject_non_finite_json_constant`，拒绝 NaN/Infinity。
- ConfigLoader 不 import Host/Engine/Service/Fins，层中立约束成立。

### 4.2 Fins owner parser / direct providers

**验证结论：通过。**

- `AwaitingResolutionMode`（_ingestion_tool_helpers.py:27-33）是 closed-set StrEnum，只有 `poll/callback/manual`。
- `parse_awaiting_resolution_mode`（_ingestion_tool_helpers.py:35-65）是唯一 raw mode parser，严格校验字段存在、类型和闭集值。
- 三个 direct providers（download/preprocess/upload_provider.py）各自在 `discover_tools` 入口调用 `parse_awaiting_resolution_mode(spec.config)`，fail-fast。
- `AWAITING_RESOLUTION_MODE_CONFIG_FIELD` 是唯一的字段名常量，无魔法字符串扩散。

### 4.3 Service discovery / typed metadata

**验证结论：通过。**

- `ServiceDiscoveredTools`（host_assembly.py:252-273）的 `fins_awaiting_runtime` 和 `_fins_awaiting_providers` 字段无默认值，调用方必须显式传入。
- 仓库范围内只有一处直接构造 `ServiceDiscoveredTools(...)`（host_assembly.py:510），位于 discovery owner `discover_service_tools`。
- `_fins_awaiting_provider_metadata_from_configs`（host_assembly.py:1189-1231）是单次遍历完成 owner 路由、mode 校验和 active 过滤的唯一入口。disabled provider 的 mode 同样被校验（plan F03 要求）。recognized non-awaiting provider 携带 `awaiting_resolution_mode` 字段时 fail-fast。
- `_active_fins_awaiting_provider_metadata`（host_assembly.py:1252-1267）在 discovery output 后按实际可用工具名收敛 active collection，不重读 raw mode。

### 4.4 Derived consumers 和 dataclasses.replace()

**验证结论：通过。**

- 测试中 4 处使用 `dataclasses.replace()` 操作 `ServiceDiscoveredTools`（test_host_assembly.py:364）或 `ServiceOpenHostAssemblyRequest`，不访问私有 metadata 字段、不重解析 `effective_provider_configs`、不读取 raw mode。
- `_tooling_options_from_discovery`（host_assembly.py:1968-2023）接收 typed metadata tuple，构造 binding/activation/poll registries。
- `_fins_wait_adapter_registry_from_provider_metadata`（host_assembly.py:2044-2062）从 typed metadata 构造 binding，不重读 raw mode。
- `_fins_wait_activation_registry_from_provider_metadata`（host_assembly.py:2065-2092）和 `_fins_wait_poll_adapter_registry_from_provider_metadata`（host_assembly.py:2095-2123）同样从 typed metadata 构造。

### 4.5 Host policy composition

**验证结论：通过。**

- `WaitPollerRuntimePolicy`（wait_adapter.py:397-429）的 12 个字段全部无默认值。R04 diff 确认删除了 10 个旧部署常量和所有 dataclass field defaults。
- `_wait_poller_policy_for_composition`（host_assembly.py:882-917）按 active typed modes 决定是否返回 policy；无 active poll provider 时返回 `None`。enabled policy 要求非空 poll adapter registry，否则 fail-fast。
- `_wait_poller_runtime_policy_from_config`（host_assembly.py:920-945）是一对一字段投影，无默认值注入或值变换。

### 4.6 Callback fail-closed

**验证结论：通过。**

- `_compose_options`（host_assembly.py:785-792）在任何 active callback provider 存在时立即 `raise ValueError`，因为 authenticated callback transport 不存在。
- 这是正确的 fail-closed 行为，符合 controller discussion Topic 5 和 WU-WAIT-01/Issue 89 owner。

### 4.7 Public Host smoke path

**验证结论：通过。**

- Controller aggregate validation 独立运行 smoke，确认 `not_ready=1 -> ready=1 -> SUCCEEDED` 和 `outbox_terminal_match=true`。
- smoke 使用本地确定性执行/观察边界，未访问外部 LLM、网络、secrets 或 raw credential-bearing config。

### 4.8 R04-S1-CV-F01 最终状态

**验证结论：已关闭。**

直接证据：
1. `ServiceDiscoveredTools` 两个 Fins 字段无默认值（host_assembly.py:272-273）。
2. 仓库范围内唯一直接构造在 host_assembly.py:510。
3. 4 处测试 derived consumers 使用 `dataclasses.replace()`。
4. 公共 composition regression test 覆盖 policy + binding/activation/poll registries。
5. pyright 全量通过（0 errors），遗漏字段在开发期即失败。

### 4.9 DS-F01：observation-timeout/LOST

**验证结论：代码证据真实；正确 defer 到 R05。**

- `dayu/host/wait_adapter.py:1107-1128`：`WaitObservationTimedOut` 分支构造 `WaitPollLost` 并调用 `_resolve_claimed_wait`，将 wait 终端化为 LOST。
- R04 diff 确认该分支未被修改——R04 只删除了 `WaitPollerRuntimePolicy` 的旧部署默认值常量和 dataclass defaults。
- controller discussion Topic 5 要求 R05 实现：撤销延迟发布、记录 transient diagnostic、释放 claim、退避而不终端化。
- R04 plan §1/§4 明确排除 "R05 observation-timeout / retry-backoff / LOST state machine"。
- 这是 R05 mandatory owner，不是 R04 accepted finding，也不是 umbrella-final acceptable behavior。

### 4.10 DS-F02：provider identity collision

**验证结论：无当前证据；正确 rejected-with-reason。**

- `_fins_awaiting_tool_name_from_provider_config`（host_assembly.py:2126-2154）使用 OR 逻辑跨 `provider_id`、`import_path`、`source_id` 识别 Fins awaiting provider。
- 同一 OR identity 规则已拥有 Fins awaiting routing、Fins workspace injection 和 Web workspace configuration。
- 当前无 packaged config、overlay、provider contract 或 test fixture 存在此类 identity collision。
- `test_unknown_third_party_provider_mode_field_remains_opaque` 证明未知三方 provider 保持 opaque。

### 4.11 Semantic ownership drift 检查

**验证结论：无 drift。**

- `awaiting_resolution_mode` 的唯一 parser 是 `parse_awaiting_resolution_mode`（Fins owner）。
- Service `_fins_awaiting_provider_metadata_from_configs` 调用该 parser 一次，产出 typed `AwaitingResolutionMode` enum。
- 下游 `_binding_for_tool_name`（fins_wait_adapter.py:360-377）接收 typed mode，通过 `_wait_resume_policy_from_mode` 映射为 Host `WaitResumePolicy`。
- `_wait_poller_policy_for_composition` 检查 `AwaitingResolutionMode.POLL` 决定是否启用 poller。
- 无下游 fallback、raw mode reparse、第二 LLM-safe normalization、兼容 shim 或 scene/execution-profile bridge。

### 4.12 分层反向依赖检查

**验证结论：无反向依赖。**

- `dayu.runtime.config_loader` 不 import `dayu.engine` / `dayu.host` / `dayu.service` / `dayu.ui` / `dayu.fins`。
- `dayu.service.host_assembly` import `dayu.host`、`dayu.engine`、`dayu.fins`、`dayu.runtime`——符合 `UI -> Service -> Host -> Engine` 分层。
- 锚定 runtime 反向 import scan：零匹配。

### 4.13 LLM-facing 泄漏检查

**验证结论：无泄漏。**

- Prompt assets 和 `execution_profiles.json` 不包含 wait poller policy 或 awaiting resolution mode。
- `_ingestion_tool_helpers.py` 中的面向模型错误消息（如 "awaiting_resolution_mode must be one of: poll, callback, manual"）只在工具参数非法时暴露，是工具 schema 例外允许的业务可读语义。
- 内部治理标识如 `spec_id`、`adapter_key` 未暴露给 LLM。

### 4.14 Security retention 检查

**验证结论：未削弱。**

- R04 added-line scan 对 authorization、permission、process isolation、observation timeout、lost-outcome implementation：零匹配。
- 现有 allowed_paths、Web defenses、containment/symlink、DNS/peer、resource budgets、atomic write、cancellation、durable wait、process fencing 完整保留。

### 4.15 Deferred issue 偷带检查

**验证结论：无偷带。**

- R04 未实施 R05、Issue 175、callback transport、Host public API/open_host、统一 authorization、permission schema、Issue 142/151/177/178。
- DS-F01 是 deferred-to-R05，不是 accepted R04 finding。

### 4.16 测试自证检查

**验证结论：测试覆盖真实行为。**

- 509 passed, 3 warnings（三个 edgar dependency deprecation warnings）。
- 所有 9 个修改的生产 Python 文件覆盖率 85.54%-100%，均 >=80% 门限。
- 测试覆盖三模式（poll/callback/manual）、缺失/错类型/未知、disabled、non-awaiting misuse、bool 冒充数值、NaN/Infinity、公共 composition regression。
- `test_replacing_discovered_bundle_preserves_host_wait_composition` 是 owner-level regression，断言 public Host policy + 三个 Fins bindings + activation adapter + poll adapter 通过 registry resolution。

### 4.17 README 检查

**验证结论：通过。**

- 5 个 responsibility-owned README 已更新：`dayu/config/README.md`、`dayu/fins/README.md`、`dayu/host/README.md`、`dayu/service/README.md`、`tests/README.md`。
- 根目录 `README.md` 和 `dayu/README.md` 正确未变。

## 5. Open Questions

无。

## 6. Residual Risk

- **R05 observation-timeout/LOST（mandatory owner）**：`dayu/host/wait_adapter.py:1107-1128` 的 `WaitObservationTimedOut` 分支当前将 wait 终端化为 LOST。R05 必须实现：撤销延迟发布、记录 transient diagnostic、释放 claim、退避。这不是 R04 residual，是 R05 mandatory entry condition。
- **callback transport（WU-WAIT-01 / Issue 89 owner）**：当前 fail-closed 行为正确，但 callback 的正向路径（authenticated transport）仍未实现。

## 7. Finding ledger

| category | count | items |
|---|---:|---|
| accepted current R04 aggregate findings | 0 | none |
| deferred to existing mandatory owner | 1 | observation-timeout/LOST -> R05 |
| rejected-with-reason | 1 | DS-F02 provider identity collision |
| observation / no-fix | 0 | none |
| blocking questions | 0 | none |

## 8. Verdict

**PASS / ZERO ACCEPTED CURRENT FINDINGS。**

R04 实现从配置→Fins owner parser→runtime typed config→Service discovery/typed metadata→Host policy/poller→public Host 的完整组合链通过 adversarial failure pass。semantic ownership drift、过度耦合、分层反向依赖、fallback/compat seam、LLM-facing 泄漏、测试自证、README、security retention 和 deferred issue 偷带均未发现问题。R04-S1-CV-F01 保持关闭。DS-F01 正确 defer 到 R05 mandatory owner。DS-F02 正确 rejected-with-reason。

## 9. Artifact path

`docs/reviews/wu-semantic-ownership-01-r04-aggregate-deepreview-mimo.md`
