# WU-SEMANTIC-OWNERSHIP-01 R05 Aggregate Deepreview — AgentDS

日期：2026-07-16
Gate：R05 aggregate deepreview（第二路，独立 AgentDS）
Controller aggregate validation：`docs/reviews/wu-semantic-ownership-01-r05-aggregate-validation.md`
Frozen aggregate product digest：`41bd8c057cb5ff3d389f909a367a19037a65ae59ffda377cd317b9d1db4eda9a`

## 1. Scope 与 evidence baseline

本 deepreview 针对 R05 aggregate（S1 + S2）的完整 16-path product/test/design/README
transaction 做独立 adversarial review，覆盖：

- R05 accepted plan 及全部 plan review/fix/re-review/controller artifacts
- S1 全部 implementation/validation/code review/fix/re-review/controller chain
- S2 全部 implementation/validation/code review/fix/re-review/controller chain
- `docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md` Topic 5
- `docs/host/design.md` 与 `docs/engine/design.md` 相关 waiting/handshake 章节
- `docs/reviews/wu-semantic-ownership-01-r05-aggregate-validation.md`
- `AGENTS.md`
- 相对 R05 base `5ba0d8b61f9d03f52c4529f5b83a6cd353d002b1` 的完整 16-path diff

## 2. Topic 5 八项裁决组合闭环验证

### 2.1 Provider mode / config owner

**裁决要求**：`tool_discovery.json` provider config 拥有 `awaiting_resolution_mode`（poll/callback/manual）。

**直接证据**：

- `dayu/config/tool_discovery.json` 三个 Fins awaiting provider 各自显式声明 `"awaiting_resolution_mode": "poll"`。
- `dayu/fins/tools/_ingestion_tool_helpers.py:27-65`：`AwaitingResolutionMode` 闭集枚举 + `parse_awaiting_resolution_mode()` 从 provider config 解析，不接收松散字符串或不存在的字段。
- `dayu/service/fins_wait_adapter.py:360-396`：`_binding_for_tool_name` 接收 typed `mode: AwaitingResolutionMode` 参数，经 `_wait_resume_policy_from_mode` 映射为 Host `WaitResumePolicy`。**不再硬编码 `POLL`**。
- `dayu/service/host_assembly.py:785-792`：任一 active provider 选择 `CALLBACK` 时在 `open_host` 前 fail fast；没有 authenticated callback transport 时不会宣传该 mode。

**Verdict**：✅ 闭环。Provider mode 的配置 owner、类型解析、Service 装配与 fail-fast 均就位。

### 2.2 Runtime policy owner

**裁决要求**：12-field `WaitPollerRuntimePolicy` 在 `host_runtime.json`，不放进 scene 或 execution profile。

**直接证据**：

- `dayu/config/host_runtime.json` 的 `wait_poller_policy` 精确包含 12 个字段：`enabled`、`poll_interval_seconds`、`claim_ttl_seconds`、`claim_batch_size`、`backoff_initial_delay_seconds`、`backoff_multiplier`、`backoff_max_delay_seconds`、`not_ready_observe_interval_seconds`、`idle_poll_interval_seconds`、`adapter_call_timeout_seconds`、`close_drain_timeout_seconds`、`max_outstanding_adapter_calls`。
- `dayu/service/host_assembly.py:889-910`：`_wait_poller_policy_for_composition` 从 host_runtime config 读取，仅当 `enabled=true`、存在 POLL provider 且 registry 存在时才启动。
- 旧 `WaitPollerRuntimePolicy()` 无参构造在 production/service/tests/smoke 中零命中。

**Verdict**：✅ 闭环。

### 2.3 Service composition

**裁决要求**：Service 不再根据 scene/name heuristic 构造默认 policy。

**直接证据**：

- 存在 `_wait_poller_policy_for_composition` 严格校验 enabled/poll-provider/registry 三条件；不存在一条 path 可绕过该装配逻辑。
- 无参 `WaitPollerRuntimePolicy()`、scene 名称匹配、工具名前缀推断等旧 heuristic 在 production 零命中。
- `wait_poller_policy=None` 仅表示"不启用 poller"，不会触发默认 policy 构造。

**Verdict**：✅ 闭环。

### 2.4 Timeout release/backoff

**裁决要求**：poll observation timeout 只写 transient diagnostic + release/backoff，不调 `resolve_wait`；cancelled abandon timeout 同理，不写 `poll_abandoned_at`。

**直接证据**：

- `dayu/host/wait_adapter.py:1077-1084`（poll 路径）：timeout → `adapter_errors += 1` + `_release_with_backoff(..., outcome=ADAPTER_ERROR, error_code=wait_observation_timeout)`。**不再调用 `_resolve_claimed_wait` / `resolve_wait`**。
- `dayu/host/wait_adapter.py:1323-1333`（abandon 路径）：timeout → 直接 `_release_with_backoff(..., outcome=ABANDON_ERROR, error_code=wait_abandon_timeout)` + return `(0, 1, ...)`。**不再写 `poll_abandoned_at` 或调用 `_MarkWaitRecordAbandonTimeoutOperation`**。
- `dayu/host/durable/state.py`：`mark_wait_record_poll_abandon_timeout` 函数（73 行）已完整删除，零残留 import。
- `dayu/host/wait_adapter.py`：`_MarkWaitRecordAbandonTimeoutOperation` dataclass 已完整删除。
- `mark_wait_record_poll_abandon_timeout` 与 `_MarkWaitRecordAbandonTimeoutOperation` 在 production/tests 零定义、零调用、零 import。

**Verdict**：✅ 闭环。这是 R05 最核心的行为变更，adversarial 逐行验证通过。

### 2.5 Late publication

**裁决要求**：late Ready 结果被 token/generation fence 丢弃，不污染下一轮。

**直接证据**：

- `dayu/host/_wait_observation.py`（相对 R05 base no diff）：token/generation/lock 仍是唯一 late-result publication authority。
- S1 owner tests (`test_wait_observation_runner.py:164` 行新增) 直接断言 timeout invalidation 后 late result 被 runner 丢弃。
- S2 public smoke 第二轮 observation 阻塞边界：首轮 Ready 已返回 → 第二轮真实 durable claim 已提交 → 第二轮 adapter 被 release gate 阻塞在 Ready 返回前 → 此时 public Run=`WAITING`、durable Wait=`WAITING`、`poll_claim_id/owner_id/claimed_at/expires_at` 四字段均 active → 首轮 timeout `ADAPTER_ERROR/wait_observation_timeout` 保持 → backoff attempt=1 → terminal outbox 为空。若首轮获得发布权，此组合不可能成立。

**Verdict**：✅ 闭环。happens-before 证据链完整且可反证。

### 2.6 Typed LOST

**裁决要求**：只有 adapter 显式返回 authoritative typed lost outcome 时走 common resolve 收为 LOST。

**直接证据**：

- `dayu/host/wait_adapter.py`：`WaitPollLost`、`ResolveWaitLostOutcome`、`_resolve_claimed_wait` 完整保留。`WaitPollLost` 分支（line 1124-1130）仍存在，调用 `_resolve_claimed_wait(record, lost_result)` → `StateMutationStatus.UPDATED` / `CAS_LOST`。
- poll timeout 路径不再产生 `WaitPollLost` 实例或调用 resolve。
- `_resolve_claimed_wait` 内部 `WaitRecordStatus.LOST` transition（line 1450）仍存在。

**Verdict**：✅ 闭环。typed LOST 路径保留，timeout 不再伪装 LOST。

### 2.7 Engine handshake timer boundary

**裁决要求**：Engine `tool_execution_timeout_seconds` 只拥有 executor handshake，不拥有已接受的 awaiting 外部 operation。

**直接证据**：

- `dayu/engine/agent.py`：**相对 R05 base 零 diff**（`git diff` 0 行）。
- `docs/engine/design.md` §11：handshake timeout 规则已写回，明确"该 timeout 只表示 Engine 不再等待 `execute()` 的 handshake outcome"。
- `tests/engine/test_agent_phase3_tool_call.py`：新增 `test_accepted_awaiting_external_operation_outlives_handshake_timeout`（79 行），直接证明：
  - 握手在 `0.1s` budget 内返回（`handshake_returned_at - handshake_started_at < 0.1s`）；
  - 外部 operation 持续 `0.25s > 0.1s` handshake budget 且 `operation_cancelled=False`；
  - Agent 产出 `TOOL_AWAITING` → `RUN_SUSPENDED` terminal；
  - 无 `RUN_FAILED` 事件。

**Verdict**：✅ 闭环。Engine production owner 未被修改，regression 首次即绿。

### 2.8 组合 verdict

八项 Topic 5 裁决全部实现闭环，不存在部分实现、遗漏或漂移。本路 AgentDS 与 aggregate validation 的结论一致。

## 3. S1/S2 semantic ownership drift 检查

### 3.1 状态/diagnostic/trace 一致性

- `state.py` 删除 `mark_wait_record_poll_abandon_timeout`：该函数写的 `poll_abandoned_at` 是 timeout-only terminal marker，在 R05 plan 中被判定为来自 timeout 的第二真源（timeout 不应产生 durable terminal）。删除动作是修复 ownership drift，而不是产生 drift。
- `wait_adapter.py` poll/abandon timeout 路径：均产出 `ADAPTER_ERROR` / `ABANDON_ERROR` diagnostic + `_release_with_backoff`。diagnostic 在 `WaitRecordRow` 中持久化，public Run/outbox 中可见 Run=`WAITING` / `CANCELLED` status。durable state、public projection 与 smoke evidence 三者一致。
- `options.py` 的 `project_host_durable_store_options`：command/open/admin/smoke 四个 consumer 共用同一 typed projection，无各自反推字段。

### 3.2 第二真源检查

- 旧 `_durable_options_from_public_options`（command.py private helper）已删除。
- 旧 `_durable_options_from_command_options` 零命中。
- Smoke 旧 `_durable_options()` 已删除。
- `HostDurableStoreOptionsSource` Protocol 仅定义 9 个 storage 字段，不引入额外 policy 计算。它不是第二真源——它是唯一 typed projection 的输入契约。

### 3.3 下游 fallback 检查

- R05 changed production files（state.py、wait_adapter.py、options.py、command.py、open_host.py）中 `hasattr`/`getattr` 零命中。
- 无 `noqa`、`# type: ignore`、`# pyright: ignore`。
- 无 loose parsing、默认值 fallback 或兼容分支。

### 3.4 过度耦合检查

- `HostDurableStoreOptionsSource`：使用 Protocol（structural typing）而非具体 dataclass 或 ABC。这避免了 `durable/options.py` import `command.py` / `open_host.py` 的上层类型。Protocol 不查 profile/default、不持久化、不解释上层字段，无 callback/factory/query 行为。这是最小 dependency inversion，不是 speculative abstraction。
- `project_host_durable_store_options` 是纯函数，不持有状态、不 side-effect。以朴素直接传参（非 callback/factory/profile/query）暴露，符合架构硬约束。

### 3.5 组合 drift verdict

未发现 S1+S2 组合引入的 semantic ownership drift、双真源、下游 fallback 或过度耦合。所有修改位于正确 owner boundary。

## 4. Plan conformance 演变验证

### 4.1 Original plan `dropped_count` smoke

**原 plan**：smoke handoff 写 runner `dropped_count`。

**演变**：S2 initial review 确认这要求穿透 `_HostHandle._wait_poller`。Controller accepted finding 后改为 blocked-second-observation 的 public/durable owner facts。内部 counter 仅留在 S1 owner tests。

**直接证据**：
- 当前 smoke 中 `runner_dropped_count`、`_WaitPollerDiagnosticsHost`、`cast`、`._wait_poller` 零命中。
- `_is_late_ready_rejected_at_second_observation_boundary` 使用 public Run status、durable Wait poll_claim 四字段、backoff attempt、poll_last_outcome/error_code 与 terminal outbox——全部是 public/durable owner facts。
- S1 `test_wait_observation_runner.py` 仍保留 `dropped_count` 作为 runner 内部诊断断言（正确的 owner）。

**Verdict**：✅ supersede 有完整证据链。plan → initial review（发现 penetration）→ Controller accepted → fix → re-review → accepted commit。不是 plan conformance 漂移，是 plan 被后续 review 在正确 gate 中改进。

### 4.2 Ruff 165 → 162

**原 plan**：S1 预期删两条 F401 → 165。

**演变**：S2 accepted review fix 实际触及 command.py 两条旧 F401（`AttemptStatus`、`read_run_by_id`）与 admin test 一条旧 F401（`create_host_command_handle`），共删除三条。

**直接证据**：
- fixed base：`167`
- S1 accepted：`165`（删除 `state.py` `TERMINAL_RUN_STATUS_VALUES` 与 `test_phase7_waiting_integration.py` `UTC`）
- S2 accepted：`162`（额外删除 `command.py` `AttemptStatus` 与 `read_run_by_id`、`test_public_host_admin.py` `create_host_command_handle`）
- `167 - 5 = 162`，精确匹配。

**Verdict**：✅ Ruff 演变可追溯。S2 accepted fix 在 touched files 中发现了既有 F401 并同步清理，属于 correct owner 行为，不是 scope creep。

### 4.3 S2 "Engine production no diff" 保持

**原 plan**：S2 Engine production no diff。

**演变**：S2 durable construction helper change（`options.py` + `command.py` + `open_host.py`）是 code-review accepted finding 的窄 Host owner fix。

**直接证据**：
- `dayu/engine/agent.py` 相对 R05 base **零 diff**（`git diff` 0 行）。
- `dayu/engine/README.md` 零 diff。
- Engine 测试新增 regression 在现有 production 上证明 boundary，不修改 Engine 行为。

**Verdict**：✅ "Engine production no diff" 承诺完整保持。

## 5. HostDurableStoreOptionsSource 设计评估

### 5.1 是否是最小正确 owner

**论证**：

- `dayu/host/durable/options.py` 的 module docstring 声明了"本模块同时拥有 Host construction options 到 durable store options 的唯一 typed 投影"。
- `HostDurableStoreOptionsSource` Protocol 精确声明了 9 个存储字段：`db_path`、`artifact_root`、`create_parent_dirs`、`sqlite_busy_timeout_seconds`、`sqlite_write_busy_retry_count`、`sqlite_write_retry_initial_delay_seconds`、`sqlite_write_retry_backoff_multiplier`、`sqlite_write_retry_max_delay_seconds`、`payload_inline_threshold_bytes`。
- 这 9 个字段是 `HostDurableStoreOptions` nested construction（`PayloadStoragePolicy` + `HostSQLiteStoragePolicy`）所需的闭集。
- 使用 Protocol 的理由成立：command options / execution options / admin options 是三个不同的 typed dataclass，各自有超过 9 个字段的更多 construction 语义。durable/options 是下层模块，不应 import 任一更宽 opener 具体类型。
- 当前四个 consumer（`command.py`、`open_host.py` 三条 construction path、smoke diagnostic read）共用同一个 `project_host_durable_store_options`。
- 不存在为满足 smoke 需求而扩张 production contract 的迹象——smoke 只是 diagnotic 读取 durable state，不启动 poller、不写 wait record。

**Verdict**：✅ 这是最小正确 owner。Protocol 不是为了 smoke 反向塑造 production contract——多 typed opener input 使该 dependency inversion 有独立充分理由。

### 5.2 潜在 concern

- `options.py` 缺少 `__all__`。当前 helper 仅由精确模块 import 使用，无 package re-export 或 stable top-level API 承诺，机械新增 `__all__` 反而扩张修复范围。记录为 **minor observation**，非 material finding。

## 6. Evidence chain 完整性

### 6.1 Coverage

| Owner | Coverage | Pass threshold |
|---|---|---|
| `dayu/host/durable/state.py` | 83% | 80% ✅ |
| `dayu/host/wait_adapter.py` | 86% | 80% ✅ |
| `dayu/host/command.py` | 88% | 80% ✅ |
| `dayu/host/open_host.py` | 85% | 80% ✅ |
| `dayu/host/durable/options.py` | 100%（73 statements, 8 branches）| 80% ✅ |

- Engine `agent.py` branch-aware 78%（statement 80.458%）：如 Controller 所指出，`agent.py` 在 fixed base / S1 / S2 均 no diff，不是 R05 新增 changed-production coverage debt。78 与 80 的差值是既有事实，aggregate review 不把它解释为新增缺陷。

### 6.2 Pyright

- Aggregated：`0 errors, 0 warnings, 0 informations`。
- Controller 与两路 reviewer 均独立验证通过。

### 6.3 Ruff

- Fixed base：167
- S1 accepted：165（删除 2 条 touched-file F401）
- S2 accepted：162（删除 5 条 touched-file F401）
- `167 - 5 = 162` 精确
- 其它 162 条 path/rule/location/message/severity 与 base 同源
- 无新增 rule/location/message、无 `noqa`、ignore 或 config 变更
- 无"为了通过 lint 而在语义上让步"的迹象

### 6.4 Public smoke

Controller 在 fresh workspace 独立运行通过：

- 11 named phases 全部完成
- typed provider modes：`poll/manual/callback`
- packaged 12-field policy 精确快照
- handshake `0.001269s < 0.05s`
- 首轮 timeout → Run/Wait=`WAITING`、claim release、`ADAPTER_ERROR/wait_observation_timeout`、terminal outbox=0
- `LATE_READY_REJECTED second_observation_blocked=true second_claim_active=true`
- 最终 `SUCCEEDED` 、terminal event/outbox exact match
- worker accept=2, poll observation=2

### 6.5 Aggregate functional

360 passed, 3 third-party edgar deprecation warnings（不在 R05 source/propagation path）。

### 6.6 Source scans

- Deleted symbols `mark_wait_record_poll_abandon_timeout` / `_MarkWaitRecordAbandonTimeoutOperation` 在 production/tests 零定义、零调用。
- `_wait_observation.py`、`waiting.py`、`agent.py`、durable schema、scheduler `dispatch.py`、`engine_ingest.py` 相对 R05 base no diff。
- 无 `hasattr`/`getattr`、`noqa`、type ignore 或 pyright ignore 在 changed production files。

## 7. Retained safety

### 7.1 未实现 / deferred 项的完整性

| Deferred item | R05 aggregate status |
|---|---|
| Issue 175 process isolation | 零新增语义。production added lines 零命中 `process_backed`、`subprocess`、`child process`。 |
| callback transport（authenticated HTTP） | 零新增语义。`AwaitingResolutionMode.CALLBACK` 选择时 fail fast，不宣传不可操作模式。 |
| unified authorization/permission framework | 零新增语义。production added lines 零命中 `authorization`、`permission`。 |
| R06+ | 零实现。 |

### 7.2 未删除/放宽的现有安全

- token invalidation / generation fence（`_wait_observation.py`）no diff
- claim CAS（`claim_wait_record_for_poll`）no diff
- capacity / outstanding invocation 上限 no diff
- shared close deadline no diff
- filesystem/durable storage/path/SQLite safety no diff
- 现有 `allowed_paths` / Web policy config 未删除或弱化

## 8. Scheduler close / terminal promotion coordination

### 8.1 问题真实性

**是确定性真实 bug**。证据：

- `tests/host/test_dispatch_scheduler.py` 中的 deterministic probe 以预期 `HostApiError`（`UNAVAILABLE` code）为通过条件，证明 scheduler close 与 dispatch queue 中存在 pending work 时，close 不 drain 也不写 terminal fact。该行为可能留下 orphan Attempt 在 `STARTING`/`RUNNING`。
- 这不是 theoretical concern——probe 是可复现的。

### 8.2 在本 aggregate 中的分类

**分类：RETAINED RESIDUAL（不是 blocker，不是 material current finding）**。

理由：

1. R05 plan 明确限定 scope 为 wait observation/state-machine ownership。scheduler close/terminal promotion 属于独立的 Host scheduler/lifecycle owner。
2. R05 product transaction（state.py、wait_adapter.py、options.py、command.py、open_host.py、design.md）不包含 scheduler `dispatch.py` 或 `engine_ingest.py` 修改。
3. S1/S2 controller validation 与两路 reviewer 均确认 scheduler owner 保持 no diff。scheduler deterministic probe 仍以预期 `HostApiError` 复现，未被修复、掩盖或 waive。
4. 当前 residual 有明确 owner（Host scheduler/lifecycle owner）和 destination（需要显式后续裁决/issue），不归入 Issue 175 或 callback/auth/R06+ deferred bucket。

**Verdict**：本 aggregate 没有因为"超出 R05 allowlist"机械忽略此问题。它在 aggregate validation、S1 controller validation、S2 controller validation、S1 re-review adjudication 与 S2 re-review adjudication 五个文档中被显式记录为 retained residual，owner/destination 明确。Aggregate deepreview 必须重申这一判定：**R05 不修 scheduler，不等同于 scheduler bug 不存在或不重要**。

### 8.3 Cancelled abandon long retry

同类 residual：cancelled wait 在 provider 永不返回 explicit terminal outcome 时，abandon observation timeout 按 capped backoff 长期重试。future Host durable evidence policy 才拥有终止 evidence/schema/contract。

**Verdict**：正确分类为 retained residual。R05 不从 timeout 猜 LOST，不等同于 evidence gap 不存在。

## 9. 新组合 finding

本路 adversarial review 对以下方向做了专门扫描：

### 9.1 `HostDurableStoreOptionsSource` 与 smoke 对 production 的反向塑造

**扫描结论**：未发现。Protocol 的 9 个字段全部是 durable construction 的固有需求。Smoke 的 durable read（`open_host_durable_store(project_host_durable_store_options(options))`）使用与 production 完全相同的 projection，没有新增字段、放宽校验或添加 smoke-only code path。

### 9.2 第二轮 observation 阻塞边界的并发正确性

**扫描结论**：未发现缺陷。第二轮 observation 在 `second_observation_entered` event 之后、`second_observation_release` 之前阻塞。主线程在此同步点读取 public Run（通过 `host.get_run`）、durable Wait（独立 read transaction）、terminal outbox。read 的时序保证来自 durable store 的事务隔离——第二轮 claim 已提交后才设置 `entered` event，主线程在该 event 之后才能读取到 active claim。happens-before 链正确。

### 9.3 Engine coverage 78% 与 80% 陈述

**扫描结论**：陈述忠实。aggregate validation 已说明 `agent.py` branch-aware 78% / statement 80.458%，且 `agent.py` 在 R05 no diff。不需要修改。

### 9.4 `options.py` 缺少 `__all__`

**扫描结论**：minor observation。当前模块只通过精确 import 使用，无 package re-export。不建议在 aggregate deepreview 阶段为此创建 fix gate。

### 9.5 Double durable open

Smoke 的 `_read_wait_record` 打开独立的 read transaction。这在 smoke 上下文中是可接受的 diagnostic pattern（只读、短事务、不修改 durable state）。当前没有多个 diagnostic reader 竞争，不是 production issue。

### 9.6 组合 coverage gap

S1 changed-owner coverage（state 83%、wait_adapter 86%）与 S2 new production（options 100%）已满足 >=80%。但是 R05 aggregate 没有跨切片组合 failure 测试（例如 poll timeout 同时发生 + scheduler 被 close + late 结果到达的组合压力）。这不是 R05 的 coverage defect——这些是 scheduler lifecycle 与 wait poller 的交互，属于 scheduler residual 修复后的验证范围。

**Verdict**：记录为 uncovered combination area，不提升为 finding。

## 10. Finding ledger

### 10.1 Material current findings

**0 条**。本路 adversarial review 未发现需要 current fix 的新 material finding。

### 10.2 Observations（非阻断）

| # | Observation | Classification |
|---|---|---|
| DS-AGG-OBS-01 | `options.py` 缺少 `__all__` | Minor cosmetic inconsistency；不构成 defect。当前 helper 只由精确 import 使用，无 package re-export。记录留存，未来若模块变宽再补。 |
| DS-AGG-OBS-02 | R05 aggregate 缺少跨切片组合 failure 压力测试（scheduler close + poll timeout + late result） | Uncovered combination area；属于 scheduler residual 修复后的验证范围，不是当前 defect。 |

### 10.3 Retained residuals

| # | Residual | Owner | Destination |
|---|---|---|---|
| DS-AGG-RES-01 | scheduler close / terminal promotion coordination | Host scheduler/lifecycle owner | 需要显式后续裁决（独立 issue/WU/phase）；不得归入 Issue 175 |
| DS-AGG-RES-02 | cancelled abandon 持续 timeout 时按 capped backoff 长期重试，无 durable terminal evidence | future Host durable evidence policy | 后续 WU/phase；不得从 timeout 猜 LOST |
| DS-AGG-RES-03 | Issue 175 process isolation / process-backed containment | existing Issue 175 | 已跟踪 |
| DS-AGG-RES-04 | callback transport / unified authorization / R06+ | later remediation/issue owner | 已 deferred |

### 10.4 Blockers

**0 条**。没有 aggregate blocker。

## 11. Verdict

**PASS / NO_NEW_MATERIAL_FINDING / READY_FOR_AGGREGATE_CONTROLLER_ADJUDICATION**

R05 aggregate 的：
- Topic 5 八项裁决组合闭环 ✅
- S1/S2 semantic ownership drift 检查 ✅（零 drift）
- Plan conformance 演变 ✅（有完整 supersede 证据链）
- `HostDurableStoreOptionsSource` 设计 ✅（最小正确 owner，非 speculative）
- Evidence chain（coverage、Ruff、pyright、smoke、tests、source scans）✅
- Retained safety 完整性 ✅
- Scheduler close residual 分类正确（retained，owner/destination 明确）✅

均通过本路独立 adversarial verification。

## 12. 下一 gate 建议

本 aggregate deepreview（AgentDS 路）完成。建议：

1. AgentMiMo 路 aggregate deepreview 完成后，Controller 裁决两路 findings。
2. 若两路均无 material finding：R05 aggregate gate 通过，进入 accepted local commit / draft PR。
3. 若任一路有 accepted material finding：AgentCodex 修复 → 双路 full re-review → Controller 最终裁决。
4. Scheduler close / terminal promotion coordination residual 必须在 umbrella 最终 closeout 前获得显式 owner/destination 裁决（新 issue 或显式后续 phase），不得被"aggregate 无 finding"隐含 waive。

R05-S2 accepted local commit、R05 aggregate completion、scheduler fix、Issue 175、callback、统一 authorization、R06-R12、push 与 PR 均未授权。本 artifact 不修改任何 product/test/README/control/已有 artifacts。
