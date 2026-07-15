# WU-SEMANTIC-OWNERSHIP-01 / R04-S1 Code Review — AgentDS

## Scope

- **Mode**: Current changes (adversarial correctness, semantic ownership, full implementation review)
- **Branch**: `phaseflow/host-issues-control`
- **Base/HEAD**: `a4ffd7641c8f114e987972d77572c2c2b4a8202f`
- **Reviewer**: AgentDS（第二路独立完整 code review，不依赖 MiMo 结论）
- **Output file**: `docs/reviews/wu-semantic-ownership-01-r04-s1-code-review-ds.md`
- **Review date**: 2026-07-15T19:35:10+08:00
- **Included scope**:
  - 全部 11 个 production/config changed files（`dayu/config/`, `dayu/fins/tools/`, `dayu/host/wait_adapter.py`, `dayu/runtime/config_loader.py`, `dayu/service/`)
  - 全部 11 个 test/smoke changed files
  - 5 个 README changed files
  - F01 fix 授权的 4 个 consumer files
  - 完整 git diff（staged + unstaged）
- **Excluded scope**: 无（所有 changed files 均已逐文件审查）
- **Documents read**: `AGENTS.md`, controller discussion, `docs/host/design.md`, `docs/engine/design.md`, `docs/tool/design.md`, `docs/fins/design.md`, `docs/ui/design.md`, accepted plan, implementation artifact, Controller validation, fix artifact, Controller re-validation

## Independent Verification

```text
419 passed, 3 warnings in 19.10s  (DS reviewer subset)
pyright: 0 errors, 0 warnings, 0 informations

Controller re-validation 另已独立运行 accepted plan §7 完整 509-test matrix 并通过
（`docs/reviews/wu-semantic-ownership-01-r04-s1-controller-revalidation.md` §3.2）。
```

Coverage（逐文件，全部 >=80%）：

| file | coverage |
|---|---:|
| `dayu/fins/tools/_ingestion_tool_helpers.py` | 85.5% |
| `dayu/fins/tools/download_provider.py` | 100% |
| `dayu/fins/tools/preprocess_provider.py` | 100% |
| `dayu/fins/tools/upload_provider.py` | 100% |
| `dayu/host/wait_adapter.py` | 90.4% |
| `dayu/runtime/config_loader.py` | 96.3% |
| `dayu/service/entrypoint_runtime.py` | 88.3% |
| `dayu/service/fins_wait_adapter.py` | 94.6% |
| `dayu/service/host_assembly.py` | 94.8% |

## Findings

### DS-F01 — 未修复 — 中 — `WaitPoller.poll_once` 对 observation timeout 仍按 lost terminalize wait

- **入口/函数**: `WaitPoller.poll_once` → `_resolve_claimed_wait`
- **文件(行号)**: `dayu/host/wait_adapter.py:1102-1128`
- **输入场景**: 单次同步 adapter observation 在 `adapter_call_timeout_seconds` 内未返回，`WaitObservationRunner` 产生 `WaitObservationTimedOut`
- **实际分支**: `isinstance(observation, WaitObservationTimedOut)` → 构造 `WaitPollLost(ResolveWaitLostOutcome(reason_code="wait_observation_timeout", ...))` → 调用 `_resolve_claimed_wait(record, timeout_result)` → `resolver.resolve_wait(record.wait_id, request)` → 将 wait record 与 Run 推进到 `LOST` 终态
- **预期行为**: Controller discussion Topic 5 最终裁决明确：“Wait observation timeout revokes late publication, records a transient diagnostic, releases the claim, and enters policy backoff. It must not call resolve_wait or terminalize the wait / Run.”
- **实际行为**: observation timeout 仍通过 `_resolve_claimed_wait` terminalize wait
- **直接证据**:
  - Controller 裁决: `docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md` §Topic 5 最终裁决第 4 条
  - 代码路径: `wait_adapter.py:1102` `isinstance(observation, WaitObservationTimedOut)` → `1107-1113` 构造 `WaitPollLost(ResolveWaitLostOutcome(...))` → `1114` `self._resolve_claimed_wait(record, timeout_result)` → `1454-1501` 调用 `self._resolver.resolve_wait(record.wait_id, request)` 真实 terminalize
- **影响**: 一个 transport/status-check 级别的超时将 wait 和 Run 永久标记为 `LOST`，而不是退避重试。在 adapter 因临时网络抖动超时但外部 job 正常运行的情况下，会导致误报 lost terminal
- **建议改法和验证点**: 将 `WaitObservationTimedOut` 分支改为 release-with-backoff（与 `WaitObservationFailed` 相同处理），不调用 `_resolve_claimed_wait`。需同步删除 `_POLL_ERROR_CODE_OBSERVATION_TIMEOUT` 作为 lost reason_code 的使用
- **Deferred scope 说明**: accepted plan §1 明确将 "R05 observation-timeout / retry-backoff / LOST 状态机" 列为非目标。本 finding 记录的是 R04-S1 范围内仍存在的已知行为，属于 R05 deferred scope；当前不要求 R04-S1 修复，但必须明确该行为与 Controller 裁决之间的差距，防止被当作已接受终态
- **修复风险（低）**: 仅为 observation timeout 分支改用 backoff 语义，不影响 adapter 主动返回 `WaitPollLost` 的路径，不影响 expiry boundary 处理
- **严重程度（中）**: deferred scope，当前不阻塞 R04-S1 通过；但若 R05 实施前该路径被当作正确终态引用，会扩散错误语义

---

### DS-F02 — 未修复 — 低 — `_is_recognized_non_awaiting_provider_config` OR 匹配可能误伤未来 provider

- **入口/函数**: `_fins_awaiting_provider_metadata_from_configs` → `_is_recognized_non_awaiting_provider_config`
- **文件(行号)**: `dayu/service/host_assembly.py:2157-2177`
- **输入场景**: 未来新增一个 provider，其 `import_path` 或 `source_id` 恰好与现有 Fins read 或 Web provider 的常量集合中某个值匹配，但该 provider 并非 Fins read / Web
- **实际分支**: `_is_recognized_non_awaiting_provider_config` 返回 `True` → 若该 provider 的 config 中存在 `awaiting_resolution_mode` 字段 → 抛出 `ValueError("non-awaiting provider ... must not declare config.awaiting_resolution_mode")`
- **预期行为**: 未知 provider 应被忽略（opaque），不为其发明 R04 语义
- **实际行为**: 因三个维度的 OR 匹配过于宽松，未知 provider 可能被误识别为 "recognized non-awaiting"，从而在携带 `awaiting_resolution_mode` 字段时被误拒绝
- **直接证据**: `2157-2177` 使用 provider_id / import_path / source_id 三个维度的 OR 匹配，且 `import_path` 和 `source_id` 检查的是字符串集合成员关系（而非精确 provider identity 三元组）
- **影响**: 低——当前 packaged config 中已知 provider 的 identity tuple 不会产生误匹配。该风险只在未来新增 provider 且其 identity fragment 与现有常量恰好重叠时触发。Service 装配期的 fail-fast 语义会将误匹配暴露为配置错误而非静默错误行为
- **建议改法和验证点**: 将识别逻辑改为精确三元组匹配（provider_id + import_path + source_id 的 tuple），而非 OR 松散匹配；或至少将 `_is_recognized_non_awaiting_provider_config` 的匹配条件与 `_fins_awaiting_tool_name_from_provider_config` 保持一致的精确定义
- **修复风险（低）**: 只收紧 Service 内部识别边界，不影响 ConfigLoader、Fins parser 或 Host
- **严重程度（低）**: 当前 packaged config 不受影响，属于未来扩展的预防性改进

## R04-S1-CV-F01 Closure Verification

**F01 已关闭。** 独立验证如下：

1. `ServiceDiscoveredTools.fins_awaiting_runtime` 与 `_fins_awaiting_providers` 均无默认值（`host_assembly.py:272-273`）——漏传由 pyright 在开发期拒绝
2. 全仓 Python source scan 确认只有 `host_assembly.py:510-525` 一处直接 `ServiceDiscoveredTools(...)` 构造（discovery owner）
3. 四个 authorized derived consumers 均使用 `dataclasses.replace(...)`：
   - `tests/tools/test_combined_tools_acceptance.py`
   - `utils/smoke_host_public_conversation_memory.py`
   - `utils/smoke_host_public_conversation_memory_scenarios.py`
   - `utils/smoke_host_public_multiturn.py`
4. 四个派生点均无对私有 metadata field、`effective_provider_configs` reparsing、raw `awaiting_resolution_mode` 解析或直接 `ServiceDiscoveredTools(...)` 重构的 added-line 命中
5. `test_replacing_discovered_bundle_preserves_host_wait_composition` 通过 public Host registry resolution 验证，不读取私有字段
6. Full pyright: `0 errors, 0 warnings, 0 informations`

## Adversarial Correctness Pass

以下攻击面已逐项审查，未发现 R04-S1 scope 内的缺陷：

### ConfigLoader bool/数值/NaN/Infinity/exact-shape 边界

- **bool 拒绝**: `_require_int_field`（`:2751`）通过 `isinstance(value, bool)` 正确拒绝 Python bool 冒充整数；`_require_float_field`（`:2644`）同样拒绝。`WaitPollerRuntimePolicy.__post_init__`（`wait_adapter.py:444,476`）对 `claim_batch_size` 和 `max_outstanding_adapter_calls` 通过 `isinstance(x, bool)` 守卫正确拒绝 bool
- **NaN/Infinity 拒绝**: JSON 加载层 `parse_float=_parse_finite_json_float`（`:1007-1018`）拒绝解析后为非有限的浮点数；`parse_constant=_reject_non_finite_json_constant`（`:1021-1029`）拒绝 `NaN`/`Infinity`/`-Infinity` 字面量。`_require_float_field`（`:2646`）二次校验 `is_finite_number(value)`
- **零值拒绝**: `_require_positive_int_field`（`:2717`）`value <= 0` 拒绝零；`_require_positive_float_field`（`:2664`）通过 `is_positive_finite_number` 拒绝零
- **exact-shape**: `_require_exact_fields`（`:2429-2447`）和 `_require_required_and_optional_fields`（`:2283-2306`）确保无多余字段、无缺失必填字段；12 字段 policy block 通过 `_parse_wait_poller_runtime_policy`（`:1972-2040`）严格校验

### Provider mode 传播

- Fins `AwaitingResolutionMode(StrEnum)` + `parse_awaiting_resolution_mode` 是唯一 parser（`_ingestion_tool_helpers.py:27-65`）
- 三个 direct provider（download/preprocess/upload）在构造 runtime/tool definition 前调用同一 parser
- Service 在 `_fins_awaiting_provider_metadata_from_configs`（`host_assembly.py:1189-1231`）中 active filtering 前遍历全部 configs 完成 parse；disabled+illegal fail-fast（`:1217-1218` 先 parse 再判断 enabled）
- Service 只通过 `_FinsAwaitingProviderMetadata.mode` 消费 typed mode，不再读取 raw config
- `_binding_for_tool_name`（`fins_wait_adapter.py:360-377`）精确映射 `AwaitingResolutionMode` → `WaitResumePolicy`；`_operation_kind_from_tool_name`（`:419-433`）保留为 observation handle 恢复所需的稳定结构映射

### Host policy 无默认/无 fallback

- `WaitPollerRuntimePolicy`（`wait_adapter.py:397-481`）所有字段必填，无默认值，`__post_init__` 校验全部 12 个字段为正数
- `WaitPoller`（`:927-978`）接收显式 `policy: WaitPollerRuntimePolicy` keyword argument
- `WaitPollerSupervisor`（`:1607-1642`）接收显式 `policy: WaitPollerRuntimePolicy` keyword argument
- 旧部署常量扫描（10 个 `_DEFAULT_*` / `_POLL_*` 等）零命中——已全部删除
- 旧 `WaitPollerRuntimePolicy()` 无参构造扫描零命中

### Service scene independence

- `_compose_options`（`host_assembly.py:754-879`）只从 `request.discovered_tools._fins_awaiting_providers` 读取 typed metadata，不读取 scene
- `_wait_poller_policy_for_composition`（`:882-917`）只基于 active typed modes 决定 poller policy
- prompt 与 interactive 入口共用同一 composition path（`entrypoint_runtime.py:494-545`）
- 测试 `test_scene_all_select_none_produces_same_opener_decision` 验证 scene 选择不改变 opener policy

### Callback pre-open fail-closed

- `_compose_options`（`:785-792`）在构造 `OpenHostOptions` 前检查任意 active callback → `raise ValueError`
- 无 marker/protocol/facade 可绕过；不存在 authenticated transport owner

### Typed metadata 构造/派生传播

- `_FinsAwaitingProviderMetadata`（`host_assembly.py:388-407`）frozen/slots，携带 provider_id、tool_name、mode 等完整 owner facts
- `_tool_discovery_bindings`（`:1270-1324`）按 metadata_by_spec_id 路由，对 enabled Fins awaiting provider 使用共享 runtime 的 `_FinsAwaitingProviderCallable`
- activation registry（`:2065-2092`）、poll adapter registry（`:2095-2122`）均从同一 typed metadata 构造

### 已确认 deferred scope（未偷带）

| deferred item | owner | R04-S1 状态 |
|---|---|---|
| R05 observation-timeout/retry-backoff/LOST 状态机 | Controller discussion Topic 5 | 未实现；当前 observation-timeout→LOST 行为保留（见 DS-F01） |
| Issue 175 Fins Docling process isolation | GitHub Issue #175 | 未触碰 |
| Callback transport 本体 | WU-WAIT-01 / #89 | 未实现；pre-open fail-closed 是正确行为 |
| Host public API/open_host 改动 | Host design | `dayu/host/api.py` 与 `dayu/host/open_host.py` 未修改 |
| 统一 tool authorization | Controller discussion Topic 9 | 未实现 |
| Issue 142/151/177/178 | 各自 issue | 未触碰 |
| Topic 8 Engine 240 chars | Controller discussion Topic 8 | no-code |
| Topic 9 Tool security wording | Controller discussion Topic 9 | no-code |

### 安全机制完整性

现有 `allowed_paths`、Web egress/DNS/peer/resource defense、path containment、symlink rejection、atomic write、process fencing 均未删除或弱化。

## Deferred-Scope Added-Line Scan

```text
authorization|permission|process_backed|subprocess|observation_timeout|ResolveWaitLostOutcome
```
R04-S1 diff 中上述 pattern 的 added-line 命中仅位于 `wait_adapter.py` 既有 observation-timeout→LOST 路径（该路径在 base `a4ffd764` 已存在，非本次新增）。无新增 deferred scope 实现。

## README Consistency Review

| README | 修改内容 | 一致性判断 |
|---|---|---|
| `dayu/config/README.md` | 新增 12 字段 policy block 与 provider mode 配置契约 | 与实现一致 |
| `dayu/host/README.md` | 新增 config-owned 显式 policy 与 Host 无 deployment defaults | 与实现一致 |
| `dayu/service/README.md` | 删除 scene-selected auto policy，改为 typed composition | 与实现一致 |
| `dayu/fins/README.md` | 新增 provider-owned mode、parser 与 registry 行为 | 与实现一致 |
| `tests/README.md` | 新增 ConfigLoader/Fins/Service/Host 矩阵与 derived discovery invariant | 与实现一致 |
| 根 `README.md` | 未修改 | 正确——入口、命令、工作流未变 |
| `dayu/README.md` | 未修改 | 正确——分层关系未变 |

## Test Effectiveness Assessment

### Owner contract tests（充分覆盖）

- `test_config_loader.py`: 202 行新增，覆盖 12 字段 policy 的 exact-shape、bool/int 边界、NaN/Infinity、零/负数、缺失/多余字段
- `test_fins_ingestion_tools.py`: 148 行新增，覆盖三模式、缺失/null/错类型/空串/大小写变体/未知值
- `test_host_assembly.py`: 848 行新增/修改，覆盖完整 composition matrix（§6.3 全部 14 行）、scene independence、derived discovery preservation
- `test_fins_wait_adapter.py`: 覆盖 typed mode→WaitResumePolicy 精确映射
- `test_wait_adapter_polling.py`: 覆盖 Host policy 构造、默认删除

### Propagation tests

- Scene all/select/none comparison tests 验证 opener policy 不因 scene 选择变化
- Prompt/interactive 同路径验证通过 entrypoint tests

### Regression tests

- `test_replacing_discovered_bundle_preserves_host_wait_composition` 验证 derived discovery 后 Host wait binding/registry/policy composition 不变

### 未覆盖区域

- `_ingestion_tool_helpers.py` 85.5%：`_awaiting_outcome_from_observation_handle`、`_failed_outcome` 等既有 helper 的覆盖不足，但不在 R04-S1 新增范围内
- Observation-timeout→LOST 路径（deferred R05）的正确性变更尚未测试

## Open Questions

- 无。所有设计决策已在 Controller discussion 中裁决，所有实现 contract 已在 accepted plan 中定义。

## Residual Risk

| risk | owner | severity |
|---|---|---|
| Observation-timeout→LOST terminalize（DS-F01） | R05 deferred scope | 中 |
| `_is_recognized_non_awaiting_provider_config` OR 匹配过于宽松（DS-F02） | 未来 provider 扩展时触发 | 低 |
| Callback 正向 transport 未实现 | WU-WAIT-01 / #89 | 信息（pre-open fail-closed 是正确的当前行为） |
| 外部 LLM/网络 smoke 未执行 | 本任务显式约束 | 信息（本地 packaged smoke 已覆盖 assembly→public Host 完整路径） |

## Verdict

R04-S1 唯一原子实现已达到 accepted plan 的 contract 要求。Provider mode 归 Fins owner parser、runtime policy 归 ConfigLoader/host_runtime.json、Host 执行显式 policy、Service typed composition、scene independence、callback fail-closed 均正确落地。R04-S1-CV-F01 已通过 required constructor + `dataclasses.replace(...)` + owner regression + full pyright 闭合。ConfigLoader bool/int/NaN/Infinity/exact-shape 边界严格。Deferred scope（R05、Issue 175、callback transport 等）未偷带。所有逐文件覆盖率 >=80%，pyright clean，419 reviewer-subset tests pass（Controller re-validation 独立验证完整 509-test matrix）。两个 findings 均为 deferred/低风险项，不阻塞 R04-S1 进入下一 gate。
