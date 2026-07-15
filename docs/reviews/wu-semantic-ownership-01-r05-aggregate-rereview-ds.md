# WU-SEMANTIC-OWNERSHIP-01 R05 Aggregate Re-Review — AgentDS（第二路）

日期：2026-07-16
Gate：R05 aggregate full re-review（AgentDS 第二路，独立于 AgentMiMo）
Controller adjudication：`docs/reviews/wu-semantic-ownership-01-r05-aggregate-deepreview-controller-adjudication.md`
Zero-change fix record：`docs/reviews/wu-semantic-ownership-01-r05-aggregate-deepreview-fix-codex.md`
Fix Controller validation：`docs/reviews/wu-semantic-ownership-01-r05-aggregate-deepreview-fix-controller-validation.md`
Frozen aggregate product digest：`41bd8c057cb5ff3d389f909a367a19037a65ae59ffda377cd317b9d1db4eda9a`

## 1. Scope 与 evidence baseline

本 re-review 以 AgentDS 身份，对 R05 aggregate（S1 + S2）做与 AgentMiMo 独立的第二路 full aggregate re-review。完整读取并交叉核对以下 evidence：

1. `AGENTS.md` — 项目指令与语义所有权约束全文
2. `docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md` Topic 5
3. `docs/host/design.md` §3 runtime、§7 Run lifecycle、§8 Attempt lifecycle、wait configuration ownership
4. `docs/engine/design.md` §10-§15 waiting/handshake 章节
5. R05 accepted plan（`docs/reviews/wu-semantic-ownership-01-r05-wait-observation-state-machine-plan.md`）及完整 plan review/fix/re-review/controller chain
6. S1 全量 implementation/validation/code review/fix/re-review/controller chain
7. S2 全量 implementation/validation/code review/fix/re-review/controller chain
8. `docs/reviews/wu-semantic-ownership-01-r05-aggregate-validation.md`
9. AgentMiMo initial aggregate deepreview：`docs/reviews/wu-semantic-ownership-01-r05-aggregate-deepreview-mimo.md`
10. AgentDS initial aggregate deepreview：`docs/reviews/wu-semantic-ownership-01-r05-aggregate-deepreview-ds.md`
11. Controller adjudication：`docs/reviews/wu-semantic-ownership-01-r05-aggregate-deepreview-controller-adjudication.md`
12. AgentCodex zero-change fix record：`docs/reviews/wu-semantic-ownership-01-r05-aggregate-deepreview-fix-codex.md`
13. Fix Controller validation：`docs/reviews/wu-semantic-ownership-01-r05-aggregate-deepreview-fix-controller-validation.md`
14. 相对 R05 entry base `5ba0d8b61f9d03f52c4529f5b83a6cd353d002b1` 的完整 16-path product/test/design/README transaction diff

本 re-review 不依赖 initial AgentDS review 的结论；所有 findings 均经过对当前 product/test/design/README 代码的独立直接阅读得出。

## 2. Zero-change 与 product digest 验证

### 2.1 16-path transaction digest

```bash
git diff --binary 5ba0d8b61f9d03f52c4529f5b83a6cd353d002b1 -- \
  dayu/host/durable/state.py \
  dayu/host/wait_adapter.py \
  docs/host/design.md \
  tests/host/test_phase7_waiting_integration.py \
  tests/host/test_wait_adapter_polling.py \
  tests/host/test_wait_observation_runner.py \
  tests/host/test_wait_record_state.py \
  tests/engine/test_agent_phase3_tool_call.py \
  utils/smoke_host_public_awaiting_entrypoint.py \
  dayu/host/durable/options.py \
  dayu/host/command.py \
  dayu/host/open_host.py \
  tests/host/test_durable_options.py \
  tests/host/test_public_host_admin.py \
  dayu/host/README.md \
  tests/README.md \
  | shasum -a 256
```

结果：`41bd8c057cb5ff3d389f909a367a19037a65ae59ffda377cd317b9d1db4eda9a`

与 aggregate validation、两路 initial deepreview、Controller adjudication、AgentCodex fix record、fix Controller validation 的 frozen value **精确一致**。

### 2.2 Zero-change 写入证据

AgentDS re-review 写入前 worktree status（`git status --porcelain=v1 --untracked-files=all`）：

```text
 M docs/host/issues-implementation-control.md
?? docs/reviews/wu-semantic-ownership-01-r05-aggregate-deepreview-controller-adjudication.md
?? docs/reviews/wu-semantic-ownership-01-r05-aggregate-deepreview-ds.md
?? docs/reviews/wu-semantic-ownership-01-r05-aggregate-deepreview-fix-codex.md
?? docs/reviews/wu-semantic-ownership-01-r05-aggregate-deepreview-fix-controller-validation.md
?? docs/reviews/wu-semantic-ownership-01-r05-aggregate-deepreview-mimo.md
```

本 artifact 创建后，worktree 将新增唯一一行：

```text
?? docs/reviews/wu-semantic-ownership-01-r05-aggregate-rereview-ds.md
```

product/test/design/README、control doc、两路 initial review、Controller adjudication、AgentCodex fix record、fix Controller validation 均未被本 re-review 修改。

**Verdict**：✅ Zero-change 成立。AgentCodex fix record 是 aggregate deepreview 之后唯一的 product-write gate，且其写入为零产品改动。本 re-review 的 16-path digest 与全链 frozen value 精确一致。

## 3. Topic 5 八项裁决组合闭环 — 独立验证

本路以与 initial AgentDS review 和 AgentMiMo review 不同的阅读顺序和代码切入点，对 Topic 5 八项裁决做独立验证。

### 3.1 Provider mode / config owner

**独立证据**：

- `dayu/config/tool_discovery.json`：`financial-download-tools`、`financial-preprocess-tools`、`financial-upload-tools` 三个 Fins awaiting provider 各自声明 `"awaiting_resolution_mode": "poll"`（第 31、41、51 行）。
- `dayu/fins/tools/_ingestion_tool_helpers.py`：`AWAITING_RESOLUTION_MODE_CONFIG_FIELD = "awaiting_resolution_mode"` + `parse_awaiting_resolution_mode()` 从 provider config 解析，返回闭集枚举，拒绝缺失/非法值。
- `dayu/service/host_assembly.py`：从 provider config 读取 mode，经 `_wait_resume_policy_from_mode` 映射为 Host `WaitResumePolicy`。
- `dayu/service/host_assembly.py`：任一 active provider 选择 `CALLBACK` 时在 `open_host` 前 fail fast。

**Verdict**：✅ 闭环。Provider mode 拥有者为 provider config（`tool_discovery.json`），不是 scene、execution profile 或 Service heuristic。

### 3.2 Runtime policy owner

**独立证据**：

- `dayu/config/host_runtime.json` 的 `wait_poller_policy` 精确包含 12 个字段：`enabled`、`poll_interval_seconds`、`claim_ttl_seconds`、`claim_batch_size`、`backoff_initial_delay_seconds`、`backoff_multiplier`、`backoff_max_delay_seconds`、`not_ready_observe_interval_seconds`、`idle_poll_interval_seconds`、`adapter_call_timeout_seconds`、`close_drain_timeout_seconds`、`max_outstanding_adapter_calls`。
- `dayu/host/wait_adapter.py:396-428`：`WaitPollerRuntimePolicy` dataclass 精确声明上述 12 个字段，与 JSON config 一一对应。
- `dayu/host/api.py:1159-1188`：`OpenHostOptions.wait_poller_policy: WaitPollerRuntimePolicy | None`，`None` 表示"不启用 poller"。
- 无参 `WaitPollerRuntimePolicy()` 在 production/service/tests/smoke 中零命中（grep exit 1）。

**Verdict**：✅ 闭环。

### 3.3 Service composition

**独立证据**：

- `dayu/service/host_assembly.py` 中的 `_wait_poller_policy_for_composition` 严格校验 enabled/poll-provider/registry 三条件。
- 不存在绕过该装配逻辑的 code path。
- 旧 scene/name heuristic 在 production 中零命中（grep exit 1）。

**Verdict**：✅ 闭环。

### 3.4 Timeout release/backoff — 核心行为变更

这是 R05 S1 最核心的行为变更。本路做独立逐行验证：

**Poll observation timeout**（`wait_adapter.py:1072-1085`）：

```python
if isinstance(observation, WaitObservationTimedOut):
    if self._lifecycle_gate.is_closed():
        shutdown_skipped += 1
        claim_conflicts += self._release_shutdown_skipped(record, claim_id)
        continue
    adapter_errors += 1
    claim_conflicts += self._release_with_backoff(
        record, claim_id,
        outcome=WaitPollLastOutcome.ADAPTER_ERROR,
        error_code=_POLL_ERROR_CODE_OBSERVATION_TIMEOUT,
        error_message="wait adapter observation exceeded Host time budget",
    )
    continue
```

- 只写入 `ADAPTER_ERROR` diagnostic + claim release + backoff。
- **不调用 `_resolve_claimed_wait`**。代码在 `continue` 后不会 fall through 到 resolve 分支（line 1113）。
- close gate 检查在 timeout 处理和 resolve 前各执行一次，保证单次迭代内 gate 状态一致。

**Abandon observation timeout**（`wait_adapter.py:1320-1334`）：

```python
if isinstance(observation, WaitObservationTimedOut):
    if self._lifecycle_gate.is_closed():
        return 0, 0, self._release_shutdown_skipped(record, claim_id), 1
    return (
        0, 1,
        self._release_with_backoff(
            record, claim_id,
            outcome=WaitPollLastOutcome.ABANDON_ERROR,
            error_code=_POLL_ERROR_CODE_ABANDON_TIMEOUT,
            error_message="wait adapter abandon exceeded Host time budget",
        ),
        0,
    )
```

- 写入 `ABANDON_ERROR` diagnostic + claim release + backoff。
- **不写 `poll_abandoned_at`**。`_MarkWaitRecordAbandonedOperation` 仅在 explicit lifecycle result（`WaitObservationPublished` → `_MarkWaitRecordAbandonedOperation`，line 1340-1344）时被调用。
- **不调用 `_resolve_claimed_wait`**。

**`_release_with_backoff` 实现**（`wait_adapter.py:1455-1495`）：

```python
status = self._transaction_runner.run_write(
    _ReleaseWaitRecordClaimOperation(
        wait_id=record.wait_id,
        claim_id=claim_id,
        next_observe_at=format_utc_timestamp(
            now + timedelta(seconds=_backoff_delay_seconds(next_attempt, self._policy))
        ),
        backoff_attempt=next_attempt,
        last_outcome=outcome,
        last_error_code=error_code,
        last_error_message=error_message,
        updated_at=format_utc_timestamp(now),
    )
)
```

- 原子的 claim release + backoff increment + diagnostic projection。
- `_backoff_delay_seconds` 是唯一 backoff 计算 owner；不存在第二真源。
- 返回 CAS 冲突计数（`0` = success, `1` = conflict）。

**Deleted symbols guard**：

- `mark_wait_record_poll_abandon_timeout`（`state.py` 73 行函数）：完全删除。
- `_MarkWaitRecordAbandonTimeoutOperation`（`wait_adapter.py` dataclass）：完全删除。
- 两符号在 `dayu/` 和 `tests/` 中零定义、零调用、零 import（grep exit 1）。

**Verdict**：✅ 闭环。timeout 只写 transient diagnostic + claim release/backoff；不产生 durable terminal fact；不伪装 LOST。代码路径间不存在 fall-through 风险。

### 3.5 Late publication

**独立证据**：

- `dayu/host/_wait_observation.py`（相对 R05 base **零 diff**）：`_ObservationToken` 拥有 `token_id`、`generation`、`state`（`ACTIVE`/`INVALIDATED`/`FINISHED`）。`invalidate()` 将 state 设为 `INVALIDATED` 并推送 `WaitObservationClosed` signal。
- S1 owner test（`test_wait_observation_runner.py`）直接断言 timeout invalidation 后 late result 被 runner 丢弃（`dropped_count == 1`）。
- S2 public smoke 的 `_is_late_ready_rejected_at_second_observation_boundary`：使用 public Run status、durable Wait `poll_claim_id/owner_id/claimed_at/expires_at` 四字段、backoff attempt、`poll_last_outcome/error_code` 与 terminal outbox——全部是 public/durable owner facts；不穿透 `_HostHandle._wait_poller`。

**Verdict**：✅ 闭环。token/generation fence 是唯一 publication authority；smoke 不依赖私有 runner diagnostics。

### 3.6 Typed LOST

**独立证据**：

- `dayu/host/wait_adapter.py`：`WaitPollLost`（line 189-195）、`ResolveWaitLostOutcome`（line 25）、`_resolve_claimed_wait`（line 1406-1453）完整保留。
- `WaitPollLost` 分支（line 1124）：`_resolve_claimed_wait(record, lost_result)` → `StateMutationStatus.UPDATED` / `CAS_LOST`。
- poll timeout 路径不对 `WaitPollLost` 实例化或调用 resolve。
- `_resolve_claimed_wait` 内部 `WaitRecordStatus.LOST` transition 保留。

**Verdict**：✅ 闭环。typed LOST 路径保留；timeout 不伪装 LOST。

### 3.7 Engine handshake timer boundary

**独立证据**：

- `dayu/engine/agent.py`：相对 R05 base **零 diff**（`git diff` 0 行）。
- S2 Engine regression test（`tests/engine/test_agent_phase3_tool_call.py`）新增 `_AwaitingExternalOperationExecutor` fake executor 类和对应测试函数：
  - 握手在 `0.1s` budget 内返回（`handshake_returned_at - handshake_started_at < 0.1s`）
  - 外部 operation 持续 `0.25s > 0.1s` handshake budget
  - `operation_cancelled = False`
  - Agent 产出 `TOOL_AWAITING` → `RUN_SUSPENDED` terminal
  - 无 `RUN_FAILED` 事件
  - Engine production 未被修改，regression 在现有 production 上证明 boundary。

**Verdict**：✅ 闭环。

### 3.8 组合闭环 verdict

八项 Topic 5 裁决全部实现。本路以独立的阅读顺序、不同的代码切入点和不同的 adversarial challenge 角度验证，与两路 initial review 和 Controller 结论一致。

## 4. Finding ledger 独立验证：`0/3/2/0`

### 4.1 Accepted current findings：0

本路对 16-path transaction 做完整 adversarial review，未发现需要 current fix 的新 material finding。与两路 initial review 的 PASS 结论一致。

**专门扫描的方向**：

- 并发正确性：timeout 处理和 close gate 检查在单次 `_poll_once` 迭代内、单线程执行，无 race。
- backoff 计数一致性：`_release_with_backoff` 是唯一 `poll_backoff_attempt` 递增路径；`_release_not_ready` 重置为 `0`；关闭门控触发 `_release_shutdown_skipped` 时也使用 backoff 递增——这是正确的"保留重试能力"语义。
- claim CAS 一致性：`_release_with_backoff`、`_release_not_ready`、`_release_shutdown_skipped` 都通过 `_ReleaseWaitRecordClaimOperation` 做 CAS 检查；`claim_id` 不匹配时返回冲突计数。
- durable state ↔ public projection ↔ smoke evidence 一致性：timeout diagnostic（`ADAPTER_ERROR/wait_observation_timeout`）在 durable `WaitRecordRow` 中持久化；public `RunSnapshot` 保持 `WAITING`；smoke evidence 的 `terminal outbox=0` 与此一致。
- abort 路径完整性：abandon observation timeout 保持 `CANCELLED` 状态不变（不产生 terminal fact）；explicit lifecycle result（abandon 成功/失败/不支持）才通过 `_MarkWaitRecordAbandonedOperation` 写 `poll_abandoned_at`。

### 4.2 No-fix observations：3 组 — 独立验证未被误关

| observation | 本路独立验证 | 裁决 |
|---|---|---|
| DS-AGG-OBS-01：`options.py` 缺少 `__all__` | 直接确认：当前模块符号仅由精确 import 使用（`from dayu.host.durable.options import project_host_durable_store_options`），无 package re-export。机械增加 `__all__` 不修复任何 correctness 或 ownership defect。 | `NO_CURRENT_DEFECT / NO_FIX` — 正确分类 |
| DS-AGG-OBS-02：缺少 scheduler close + poll timeout + late result 跨 owner 压力测试 | 直接确认：该组合的未覆盖边界依赖 scheduler lifecycle residual（见 §5.1）。当前添加组合测试既不能提供正确 terminal coordination oracle，也可能把独立 scheduler owner 偷带进 R05 wait observation scope。 | `OUTSIDE_R05_OWNER / NO_R05_FIX` — 正确分类；登记为该 residual 后续 mandatory verification |
| smoke timing margin、单次 backoff cap、Engine 既有 branch coverage | 直接确认：durable/event 同步提供直接 happens-before；smoke 只验证首轮 backoff（`backoff_max == initial` 时 cap 不生效）；Engine `agent.py` branch-aware 78% 是既有 debt，在 R05 no diff。 | `LOW / NO_FIX` — 正确分类 |

**Verdict**：3 组 no-fix observations 均未被误关。每项都有直接证据支撑其分类理由，不存在"为关闭而关闭"的迹象。

### 4.3 Retained residuals：2 — 独立验证仍真实、未修、未 waive

见 §5。

### 4.4 Blockers：0

本路独立确认无 aggregate blocker。

## 5. Retained residuals 独立深度验证

### 5.1 Scheduler close / terminal promotion coordination

**问题真实性**：本路独立确认该 residual 是确定性真实 bug。

**直接证据**：

- `workspace/tmp/test_r05_scheduler_close_probe.py`：确定性 probe 以预期 `HostApiError`（`"Host execution is unavailable"`）为通过条件。
- 探针逻辑：close gate 先提交 → active worker clean EOF → promotion wake 被拒绝 → Run 可能滞留 `QUEUED`。
- `dayu/host/dispatch.py`、`dayu/host/engine_ingest.py`、`tests/host/test_dispatch_scheduler.py`：相对 R05 base 均 **零 diff**。
- R05 wait observation symbols 对 scheduler owner files 零命中。

**Owner/destination 充分性**：

- **Owner**：Host scheduler/lifecycle coordination owner。这是独立的 Host 内部调度缺口，不属于 wait observation timeout owner。
- **Destination**：需要独立显式 work item（scheduler lifecycle WU/issue），不得归入 R05 或 Issue 175。
- **后续 mandatory verification**：修复时必须覆盖 scheduler close + terminal promotion + poll timeout/late result 组合验证。

**R05 aggregate 状态**：未修、未掩盖、未 waive、未归 Issue 175。`dispatch.py`、`engine_ingest.py` 与 scheduler tests 在 zero-change gate 保持 no diff。

**Verdict**：✅ `RETAINED / UNFIXED / UNWAIVED` — 分类正确，owner/destination 充分。

### 5.2 Cancelled abandon 长期 capped retry

**问题真实性**：本路独立确认该 residual 是真实终止性缺口。

**直接证据**：

- `wait_adapter.py:1280-1334`：abandon observation timeout → `_release_with_backoff(ABANDON_ERROR, wait_abandon_timeout)` → backoff 递增 → 下次 observe。capped backoff 限制资源但不产生 terminal evidence。
- 当 provider 永不返回 explicit lifecycle outcome 时，cancelled wait 按 capped backoff 长期重试。
- R05 正确地从 timeout 只写 diagnostic + release/backoff，不从 timeout 猜 LOST。

**Owner/destination 充分性**：

- **Owner**：future Host durable evidence policy owner。需要设计显式 durable evidence 条件来终止 cancelled wait 的长期重试。
- **Destination**：后续显式 contract/design work。

**R05 aggregate 状态**：未修、未 waive。R05 保证资源安全（capped backoff、finite timeout、claim CAS），但不保证终止。

**Verdict**：✅ `RETAINED / UNFIXED / UNWAIVED` — 分类正确，owner/destination 充分。

## 6. Retained safety、deferred 与 no-code boundary 漂移检查

### 6.1 Retained safety anchors

本路独立确认以下 safety anchors 未被本 gate 删除或放宽：

| 安全机制 | 本路直接证据 |
|---|---|
| late-publication token invalidation | `_wait_observation.py` no diff；`_ObservationToken.invalidate()` 保留 |
| shared close deadline | 既有 supervisor close test 通过 |
| claim CAS | `_ReleaseWaitRecordClaimOperation` + `claim_id` match — no diff |
| typed LOST | `WaitPollLost` class + `_resolve_claimed_wait` branch — 保留 |
| explicit abandon terminal marker | `_MarkWaitRecordAbandonedOperation` — 仅在 explicit lifecycle result 路径调用 |
| timeout-only symbol 零残留 | `mark_wait_record_poll_abandon_timeout` / `_MarkWaitRecordAbandonTimeoutOperation` — grep exit 1 |
| filesystem/durable storage containment | 无路径或权限删除 |
| capacity / close-drain | 无 policy 字段或上限删除 |

### 6.2 Deferred scope 漂移检查

本路独立确认 production added lines 对以下 deferred 项零命中（grep exit 1 或仅命中既有代码）：

- `authorization`（统一权限框架）：command.py/open_host.py 中的 `authorization_claims` 是既有代码，R05 diff 零命中（`git diff 5ba0d8b6.. -- dayu/host/command.py dayu/host/open_host.py | rg authorization` exit 1）。
- `permission`：零命中。
- `callback transport`：零命中。
- `process isolation` / `process_backed` / `subprocess`：零命中。
- `Issue 175`：零命中。

### 6.3 No-code boundary 漂移检查

- Issue 175 process isolation：零实现，保持既有 owner。
- callback transport：零实现；CALLBACK mode 选择时 fail fast。
- unified authorization/permission：零实现。
- R06+：零实现。
- 现有 token fence、claim CAS、capacity/close deadline、filesystem containment、allowed paths、Web 防御、DNS/peer proof、resource budgets、atomic write 与 process fencing 均未被删除或放宽。

**Verdict**：✅ retained safety、deferred scope 与 no-code boundaries 均未漂移。

## 7. Plan supersession 与 Ruff 演变 — 独立验证

### 7.1 Original plan `dropped_count` smoke

**原 plan**：smoke handoff 写 runner `dropped_count`。

**演变**：S2 initial review 确认这要求穿透 `_HostHandle._wait_poller`。Controller accepted finding 后改为 blocked-second-observation 的 public/durable owner facts。

**本路独立证据**：

- 当前 smoke 中 `_WaitPollerDiagnosticsHost`、`runner_dropped_count`、`observation_diagnostics_snapshot`、`._wait_poller` 零匹配（grep exit 1）。
- `_is_late_ready_rejected_at_second_observation_boundary` 使用 public Run status、durable Wait claim 四字段、backoff attempt、terminal outbox——全部是 public/durable owner facts。
- S1 owner test 仍保留 `dropped_count` 作为 runner 内部诊断断言（正确的 owner）。

**Verdict**：✅ plan → review finding → Controller accepted → fix → re-review → accepted commit 的完整证据链成立。

### 7.2 Ruff 167 → 165 → 162

**本路独立复算**：

- R05 fixed base：`167`
- S1 accepted：`165`（删除 `state.py` `TERMINAL_RUN_STATUS_VALUES` + `test_phase7_waiting_integration.py` `UTC`）
- S2 accepted：`162`（额外删除 `command.py` `AttemptStatus` + `read_run_by_id` + `test_public_host_admin.py` `create_host_command_handle`）
- `167 - 5 = 162`，精确匹配。

S2 accepted fix 在 touched files 中发现既有 F401 并同步清理——属于 correct owner 行为，不是 scope creep。

**Verdict**：✅ 演变可追溯。

### 7.3 S2 "Engine production no diff" 保持

**本路独立确认**：`dayu/engine/agent.py` 相对 R05 base 零 diff。S2 durable construction helper change 是 code-review accepted finding 的窄 Host owner fix，不修改 Engine wait semantics。

**Verdict**：✅ 承诺完整保持。

## 8. HostDurableStoreOptionsSource 设计 — 独立评估

### 8.1 是否是最小正确 owner

**本路独立论证**：

- `dayu/host/durable/options.py:25-122`：`HostDurableStoreOptionsSource` Protocol 声明 9 个 `@property`：`db_path`、`artifact_root`、`create_parent_dirs`、`sqlite_busy_timeout_seconds`、`sqlite_write_busy_retry_count`、`sqlite_write_retry_initial_delay_seconds`、`sqlite_write_retry_backoff_multiplier`、`sqlite_write_retry_max_delay_seconds`、`payload_inline_threshold_bytes`。
- `project_host_durable_store_options`（line 286-319）是唯一构造 `PayloadStoragePolicy` + `HostSQLiteStoragePolicy` + `HostDurableStoreOptions` 的位置。
- 四个 consumer 共用该 helper：`command.py:373`、`open_host.py:525/591/632/1310`、`smoke:1407`、`test_public_host_admin.py:209`。
- Protocol（structural typing）允许 `HostCommandHandleOptions` 和 `OpenHostOptions`（两个不同 frozen dataclass）各自同名属性自动满足，无需继承或 import 上层类型。
- Protocol 不持久化、不查找默认值、不解释额外字段、不拥有上层 opener 语义。

**使用 Protocol 的理由**：durable/options 是下层模块，不应 import 任一更宽 opener 具体类型。Protocol 是 Python 标准 dependency inversion 实践，不是 speculative abstraction。

**Verdict**：✅ 最小正确 owner。不是为 smoke 反向塑造 production contract。

### 8.2 `options.py` 缺少 `__all__`

本路确认：当前模块符号仅由精确 import 使用，无 package re-export。正确分类为 minor observation，非 material finding。

## 9. 新组合 finding 独立扫描

本路对以下方向做了专门的 adversarial 扫描，这些方向在两路 initial review 中未被完全覆盖或值得独立验证：

### 9.1 Lifecycle gate TOCTOU：`_poll_once` 中多次 `is_closed()` 检查的并发安全性

**问题描述**：`_poll_once` 内对 `_lifecycle_gate.is_closed()` 做了多次检查（entry 处 line 987、poll timeout 前 line 1073、resolve 前 line 1109、abandon timeout 前 line 1321 等）。`WaitPollerSupervisor.close()` 在另一个线程中调用 `_close_event.set()`（line 1658），可在任意两次 `is_closed()` 检查之间改变 gate 状态。这是一个真实的 TOCTOU 窗口。

**本路直接走读以下并发相关 owner、装配顺序与 drain 语义**：

**一、resolve 的真实 owner：poll-round 私有 command handle，非 execution DurableActor**

`_OpenHostWaitPollerFactory.create_wait_poller`（`open_host.py:511-551`）每轮 poll 创建**独立的** `HostCommandHandle`（line 532-537），打在自己的 `durable_store` 上（line 524-525）。`_CommandHandleWaitResolver`（`open_host.py:433-453`）接收该私有 handle，在 poller thread 内直接调用 `_resolve_wait(self._command_handle, wait_id, request)`（line 453）。`_ClosingWaitPoller.poll_once`（`open_host.py:480-489`）在 `_poll_once` 返回后才关闭该 handle（line 489）。

关键结论：poller 的 resolve 路径不经 execution `DurableActor`（`_durable_actor.py:88-125`，其 `call/submit` 队列服务于 execution command path）。`_close_owned_resources` 中 `poller drain → actor stop` 的装配 teardown 顺序**不能**证明 resolve 可提交——poller 用的是自己每轮私有 handle，不依赖 execution actor 的存活。

**二、resolve 路径的并发保护（drain deadline 内）**

`_resolve_claimed_wait`（`wait_adapter.py:1406-1447`）构造 `ResolveWaitRequest`，经 `_CommandHandleWaitResolver` → `_resolve_wait(command_handle, ...)` 进入 common `resolve_wait` 管道（`waiting.py:750`）。管道内由 durable state-machine + `(wait_id, idempotency_key)` 幂等保护（`waiting.py:864` scope、`waiting.py:873-885` idempotent replay）。**resolve 不经过 claim_id CAS**。

在 drain deadline 内：poll thread 仍在运行，`_ClosingWaitPoller` 的 `command_handle.close()` 尚未执行（`poll_once` 未返回），私有 handle 仍存活——resolve 可正常进入 common pipeline。

**三、release 路径的并发保护（drain deadline 内）**

timeout/error/not_ready/shutdown_skipped 均通过 `_release_with_backoff` → `_ReleaseWaitRecordClaimOperation` → SQL `WHERE poll_claim_id = ?`（`state.py:2641`）做 claim_id CAS。claim 不匹配时返回冲突计数。

**四、late observation 的并发保护**

close 已调用 `begin_close()` 使 token 失效后，迟到 result 被 `_wait_observation.py` token fence 丢弃——`WaitObservationClosed` → `_release_shutdown_skipped`（R05 base no diff）。

**五、finite drain timeout 的 residual 风险**

`supervisor.close()`（`wait_adapter.py:1631-1692`）的 drain deadline 为 `close_drain_timeout_seconds`（line 1661）。若 deadline 到期时 poll thread 仍未退出（line 1665 `thread_alive=True`），`close()` 记录 warning 后**仍然返回**（line 1666-1677）。此后 `_close_owned_resources`（`open_host.py:981`）继续执行 `durable_actor.stop_and_drain()`（line 1007）与 `scheduler.close()`（line 1020）。

此时 poll thread 可能仍在一轮 `_poll_once` 中——gate check 已通过（line 1109），resolve 即将进入私有 handle 的 `_resolve_wait`。resolve 的 durable write 本身可成功（私有 handle 在 `_poll_once` 返回前仍存活），但其 after-commit wakeup（queue promotion）与正在 teardown 的 scheduler 之间存在竞态。

此风险**不是新的 R05 current finding**——它落入已记录的 retained residual：**scheduler close / terminal promotion coordination**。该 residual 的 future owner 必须覆盖 `close + promotion + poll timeout/late result` 的组合验证。本 gate 不修、不 waive、不归 Issue 175；在 drain deadline 内，三条写路径（release/resolve/observation）的 per-path 机制分析成立，但超出 deadline 的组合风险由 scheduler coordination owner 承担后续修复。

**Verdict**：**不是 material finding**。TOCTOU 窗口真实存在。在 drain deadline 内：release 由 `claim_id` CAS 保护、resolve 由 common `resolve_wait` state-machine + `(wait_id, idempotency_key)` 幂等保护（**不依赖 claim_id CAS，也不依赖 execution DurableActor**）、late observation 由 token fence 保护。超出 drain deadline 时，late resolve + scheduler teardown 的组合风险落入 retained residual「scheduler close / terminal promotion coordination」，其 future owner 承担后续修复，不是本 R05 gate 的 blocker。gate 单调转换（只 open→closed）保证没有振荡风险。不在 `_poll_once` 内对 `is_closed()` 加锁是正确的——deadline 内的 per-path 保护已充分，deadline 外的 residual 由 scheduler coordination owner 独立承担。

### 9.2 Abandon timeout 的 claim release 与 backoff 原子性

**扫描**：abandon timeout 路径调用 `_release_with_backoff`，内部执行 `_ReleaseWaitRecordClaimOperation` 写事务。如果 CAS 冲突（`claim_id` 不匹配，例如被另一个 poller 实例重新 claim），返回冲突计数但不抛异常——wait 在下一次 observe 时会被重新评估。

**Verdict**：无缺陷。CAS 冲突被优雅降级为冲突计数，不导致 orphan claim。

### 9.3 `_release_shutdown_skipped` 使用 backoff 递增的语义正确性

**扫描**：当 close gate 触发时，`_release_shutdown_skipped` 调用 `_release_with_backoff(SHUTDOWN_SKIPPED)`，这会递增 `backoff_attempt` 并设置 `next_observe_at`。这使 wait 在系统重启后可被重新 claim。如果系统立即重启，backoff delay 提供合理的重试间隔。

**Verdict**：语义正确。shutdown 时保留重试能力是期望行为。

### 9.4 16-path 外文件的一致性

**扫描**：R05 aggregate validation 声明的 no-diff files（`agent.py`、Engine README、`_wait_observation.py`、`waiting.py`、durable schema、`dispatch.py`、`engine_ingest.py`）本路独立确认均 empty diff。未发现 16-path 外文件的意外修改。

**Verdict**：无意外修改。

### 9.5 Smoke diagnostics 读取双重 durable open

**扫描**：Smoke 的 `_read_wait_record` 打开独立 read transaction。这在 smoke 上下文中是 acceptable diagnostic pattern（只读、短事务、不修改 durable state）。

**Verdict**：非 production issue。smoke 是诊断脚本，双重 read open 不引入正确性风险。

## 10. Final ledger

| 分类 | 数量 | 状态 |
|---|---:|---|
| accepted current finding | 0 | `CLOSED / NO PRODUCT FIX` |
| no-fix observation | 3 组 | `CLOSED WITH DIRECT REASON` |
| retained residual | 2 | `OPEN AT EXPLICIT LATER OWNER`；R05 中未修、未 waive |
| blocker | 0 | `NONE` |

### Retained residuals 详情

| residual | owner / destination | 状态 |
|---|---|---|
| scheduler close / terminal promotion coordination | Host scheduler/lifecycle coordination owner；需要独立显式 work item；umbrella final closeout 必须保留入口 | `RETAINED / UNFIXED / UNWAIVED`；不归 Issue 175；后续修复必须覆盖 close + promotion + poll timeout/late result 组合验证 |
| cancelled abandon 长期 capped retry | future Host durable evidence policy owner；需要显式 contract/design | `RETAINED / UNFIXED / UNWAIVED`；不得从 timeout/retry count/timestamp 猜 LOST |

## 11. Verdict

**PASS / NO_NEW_MATERIAL_FINDING / READY_FOR_CONTROLLER_ADJUDICATION**

R05 aggregate 的：

- Zero-change 与 product digest（`41bd8c...`）✅ — 精确一致，唯一写入为本 re-review artifact
- Topic 5 八项裁决组合闭环 ✅ — 独立逐行验证
- `0/3/2/0` ledger ✅ — 独立确认正确
- No-fix observations 未被误关 ✅ — 每项有直接证据支撑分类
- Scheduler close 与 cancelled retry 两项 residual ✅ — 仍真实、未修、未 waive；owner/destination 充分
- Retained safety/deferred/no-code boundary ✅ — 未漂移
- §9.1 lifecycle gate TOCTOU ✅ — 经 Controller 四轮指正后完整重写：resolve owner 修正为 poll-round 私有 `HostCommandHandle`（`_OpenHostWaitPollerFactory` 每轮独立创建，**不经 execution DurableActor**）；drain deadline 内 release 由 `claim_id` CAS 保护、resolve 由 common `resolve_wait` state-machine/`(wait_id, idempotency_key)` 幂等保护、late observation 由 token fence 保护；drain deadline 外的 late resolve + scheduler teardown 组合风险落入 **retained residual「scheduler close / terminal promotion coordination」**——不是新 R05 finding、不 waive、future owner 必须覆盖 close + promotion + poll timeout/late result 组合验证
- 新 material finding ✅ — 零（经 5 项专项 adversarial 扫描 + Controller 四轮指正后 TOCTOU 深度复查）

两路 initial deepreview（AgentMiMo + AgentDS initial）、Controller adjudication、AgentCodex zero-change fix record 与 fix Controller validation 的结论与本 re-review 一致。§9.1 的并发论证经 Controller 四轮指正后已修正——第一轮删除"单线程保证 gate 不变"错误论断，第二轮删除"所有写经 claim_id CAS"的错误泛化并替换为 per-path 机制分析，第三轮删除"已提交 durable actor"的时序错误并替换为装配 teardown 顺序，第四轮修正 resolve owner（poll-round 私有 handle 非 execution DurableActor）与 drain timeout 后的 residual 风险归属。

## 12. 下一 gate

本 re-review 完成后，下一 gate 为 **Controller 最终裁决**。Controller 必须：

1. 复核 16-path digest 未变（`41bd8c...`）
2. 确认 zero-change 唯一写入
3. 确认 `0/3/2/0` ledger 正确
4. 确认两项 retained residual 的 owner/destination 未漂移
5. 决定 R05 aggregate accepted local commit 是否可执行

R05 aggregate accepted local commit、R05 completion、R06-R12、scheduler 产品修复、Issue 175、callback、统一 authorization、push 与 PR 均未授权。本 artifact 不修改任何 product/test/README/control/已有 artifacts。

---

**Reviewer**：AgentDS（第二路 independent re-review）
**Date**：2026-07-16
**Review type**：R05 aggregate full re-review
**Reviewed digest**：`41bd8c057cb5ff3d389f909a367a19037a65ae59ffda377cd317b9d1db4eda9a`
**First-pass DS review**：`docs/reviews/wu-semantic-ownership-01-r05-aggregate-deepreview-ds.md`
**Stops at**：Controller adjudication
