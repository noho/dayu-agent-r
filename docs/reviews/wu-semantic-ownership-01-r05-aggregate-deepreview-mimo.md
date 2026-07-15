# WU-SEMANTIC-OWNERSHIP-01 R05 Aggregate DeepReview — AgentMiMo（第一路）

日期：2026-07-16

## 1. Scope 与 verdict

- umbrella：`WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation；不是新 WU。
- aggregate gate：R05 wait observation/state-machine ownership 全量 aggregate deepreview。
- accepted plan commit：`201eb7f5287fc8e73d05b442e84369e19928236a`。
- accepted S1 commit：`c5af5613b21673864fff072a132ac56a46cc9836`。
- accepted S2 commit：`ff7b0b1825491ee3690a45d56a059c5da00af7aa`。
- aggregate product transaction digest：`41bd8c057cb5ff3d389f909a367a19037a65ae59ffda377cd317b9d1db4eda9a`。
- R05 entry base：`5ba0d8b61f9d03f52c4529f5b83a6cd353d002b1`。
- 16-path transaction：`git diff --stat` 确认 65 files changed, +12219/-304。

**Verdict：PASS — 无 material current finding；两项 retained residual 有明确 owner/destination；deferred scope 未偷带。**

## 2. Reviewed evidence 列表

1. `AGENTS.md` — 完整读取。
2. `docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md` — Topic 5 完整读取。
3. `docs/engine/design.md` — waiting/handshake 章节完整读取（§10-§15）。
4. `docs/host/design.md` — §3 runtime、§7 Run lifecycle、§8 Attempt lifecycle、wait configuration ownership（`host_design.md:101`）、poller runtime policy 章节。
5. `docs/reviews/wu-semantic-ownership-01-r05-wait-observation-state-machine-plan.md` — accepted plan 完整读取。
6. `docs/reviews/wu-semantic-ownership-01-r05-plan-review-mimo.md`、`-ds.md`、`-controller-adjudication.md` — plan review chain。
7. `docs/reviews/wu-semantic-ownership-01-r05-plan-rereview-mimo.md`、`-ds.md`、`-controller-adjudication.md` — plan re-review chain。
8. `docs/reviews/wu-semantic-ownership-01-r05-plan-second-rereview-mimo.md`、`-ds.md`、`-controller-adjudication.md` — plan second re-review chain。
9. `docs/reviews/wu-semantic-ownership-01-r05-plan-fix-codex.md`、`-controller-validation.md` — plan fix chain。
10. `docs/reviews/wu-semantic-ownership-01-r05-plan-rereview-fix-codex.md`、`-controller-validation.md` — plan re-review fix chain。
11. `docs/reviews/wu-semantic-ownership-01-r05-s1-implementation-codex.md` — S1 implementation。
12. `docs/reviews/wu-semantic-ownership-01-r05-s1-validation-continuation-codex.md` — S1 validation continuation。
13. `docs/reviews/wu-semantic-ownership-01-r05-s1-validation-plan-correction-codex.md` 及完整 correction chain — S1 plan correction。
14. `docs/reviews/wu-semantic-ownership-01-r05-s1-code-review-mimo.md`、`-ds.md`、`-controller-adjudication.md` — S1 initial code review。
15. `docs/reviews/wu-semantic-ownership-01-r05-s1-code-review-fix-codex.md`、`-controller-validation.md` — S1 code review fix。
16. `docs/reviews/wu-semantic-ownership-01-r05-s1-code-rereview-mimo.md`、`-ds.md`、`-controller-adjudication.md` — S1 re-review。
17. `docs/reviews/wu-semantic-ownership-01-r05-s1-controller-validation.md` — S1 controller validation。
18. `docs/reviews/wu-semantic-ownership-01-r05-s2-implementation-codex.md` — S2 implementation。
19. `docs/reviews/wu-semantic-ownership-01-r05-s2-code-review-mimo.md`、`-ds.md`、`-controller-adjudication.md` — S2 initial code review。
20. `docs/reviews/wu-semantic-ownership-01-r05-s2-code-review-fix-codex.md`、`-controller-validation.md` — S2 code review fix。
21. `docs/reviews/wu-semantic-ownership-01-r05-s2-code-rereview-mimo.md`、`-ds.md`、`-controller-adjudication.md` — S2 re-review。
22. `docs/reviews/wu-semantic-ownership-01-r05-s2-controller-validation.md` — S2 controller validation。
23. `docs/reviews/wu-semantic-ownership-01-r05-aggregate-validation.md` — aggregate validation。
24. 16-path product/test/design/README diff 全文 — `git diff 5ba0d8b6..HEAD`。
25. `dayu/host/_wait_observation.py` — no-diff 验证 + token/fence 机制全文阅读。
26. `dayu/host/waiting.py` — no-diff 验证。
27. `dayu/host/durable/schema.py` — no-diff 验证。
28. `dayu/engine/agent.py` — no-diff 验证。
29. `dayu/host/dispatch.py` — no-diff 验证。
30. `dayu/host/engine_ingest.py` — no-diff 验证。
31. `tests/host/test_dispatch_scheduler.py` — R05 symbol 零命中验证。

## 3. Adversarial challenge 逐项验证

### 3.1 Topic 5 裁决组合闭环验证

**结论：全部闭环，无 gap。**

Topic 5 七项裁决子项逐一验证：

| 子项 | 设计真源 | 代码实现 | aggregate 验证 |
|---|---|---|---|
| provider mode/config owner | `tool_discovery.json` provider config 拥有 `poll`/`callback`/`manual` 恢复策略 | R04 config owner 保持，S1/S2 无修改 | PASS：`_binding_for_tool_name` 不再 hard-code `WaitResumePolicy.POLL`，provider config owner 完整 |
| runtime policy owner | `host_runtime.json` 拥有 12-field poller runtime policy | R04 config owner 保持，S1/S2 无修改 | PASS：`WaitPollerRuntimePolicy` 从 config 构造，不是无参默认 |
| Service composition | Service 不再 scene/name heuristic 构造默认 policy | R04 composition 保持，S1/S2 无修改 | PASS：无参 `WaitPollerRuntimePolicy()` 零命中（grep exit 1） |
| timeout release/backoff | S1 核心 transaction：`WaitPoller` 把 poll/abandon timeout 解释为 poll-local transient diagnostic + claim release/backoff | `wait_adapter.py:1072-1085`（poll timeout）、`wait_adapter.py:1320-1334`（abandon timeout）均改用 `_release_with_backoff` | PASS：timeout 不调用 `_resolve_claimed_wait`，不写 terminal `poll_abandoned_at` |
| late publication | `_wait_observation.py` token/generation/lock 是唯一 publication authority，no diff | S1 no-diff，S2 smoke 在第二轮 blocked boundary 证明首轮无发布权 | PASS：token fence + public durable facts 双路验证 |
| typed LOST | authoritative typed `WaitPollLost` 经 common resolver 终止 Wait/Run | S1 owner test `test_poll_adapter_lost_result_closes_run` 断言 | PASS：timeout code 不出现在 typed LOST branch |
| Engine handshake timer boundary | `agent.py` no diff；Engine 只在 executor 返回前使用 handshake timeout | S2 Engine regression test `test_engine_handshake_timer_does_not_own_accepted_awaiting_operation` | PASS：accepted `ToolAwaitingOutcome` 后无 timer ownership |

**Topic 5 等价组合验证**：R04 config handoff → Service composition → `open_host` → `WaitPoller` poll/abandon timeout release/backoff → token fence late publication guard → typed LOST resolver → Engine handshake boundary ——完整链路无断点。

### 3.2 S1/S2 semantic ownership drift 检查

**结论：无 drift、无第二真源、无下游 fallback、无过度耦合或 speculative abstraction。**

逐维度验证：

#### 3.2.1 Semantic ownership drift

S1 的唯一产品 transaction 精确落在 semantic owner boundary：
- `WaitPoller`（`wait_adapter.py`）是 poll/abandon observation timeout 结果解释与 claim release/backoff policy 的 owner。
- `release_wait_record_poll_claim`（`state.py`）是 atomic claim release、next-observe、attempt 与 diagnostic projection 的 owner。
- `mark_wait_record_poll_abandoned`（`state.py`）是 explicit applied/unsupported/noop lifecycle outcome 的 terminal `poll_abandoned_at` 写入 owner。
- `_wait_observation.py`（no diff）是 token identity、state、generation 与 publication fence 的 owner。
- `docs/host/design.md`（精确句子改写）是 wait contract 设计真源。

无任何下游消费者通过 fallback、特例、重复计算、loose parsing、`hasattr/getattr`、默认值或兼容分支补齐上游 contract。

#### 3.2.2 状态/diagnostic/trace 一致性

| 事实 | 状态真源 | diagnostic/trace 投影 | 一致性 |
|---|---|---|---|
| poll timeout → Wait 状态 | durable `WaitRecordStatus.WAITING` | `poll_last_outcome=ADAPTER_ERROR`, `poll_last_error_code=wait_observation_timeout` | 一致：状态不变 + diagnostic 写入 owner 边界 |
| poll timeout → Run 状态 | durable `RunStatus.WAITING` | 无 terminal event/outbox | 一致：timeout 不产生 terminal fact |
| authoritative typed LOST → Wait 状态 | `WaitRecordStatus.LOST` | `poll_last_outcome=LOST` + resolver idempotency key | 一致：resolver 写 terminal fact |
| late publication → dropped | `_wait_observation.py` token fence | `dropped_count`（S1 owner test 内部诊断）；S2 smoke 不依赖它 | 一致：fence 是 publication authority，dropped_count 是内部诊断 |
| abandon timeout → Wait 状态 | durable `WaitRecordStatus.CANCELLED`（不变） | `poll_last_outcome=ABANDON_ERROR`, `poll_last_error_code=wait_abandon_timeout` | 一致：cancelled 状态保持 + diagnostic 写入 |

无"返回成功但状态半提交""外部显示完成但系统仍可恢复或运行中"或"错误被默认成功值掩盖"的情况。

#### 3.2.3 第二真源

无。逐项确认：
- observation timeout 结果解释：唯一 owner 是 `WaitPoller._poll_once()` 的 timeout 分支。
- claim release/backoff：唯一 owner 是 `_release_with_backoff`。
- backoff delay 计算：唯一 owner 是 `_backoff_delay_seconds(next_attempt, policy)`。
- publication authority：唯一 owner 是 `_wait_observation.py` token/generation/lock。
- durable construction projection：唯一 owner 是 `project_host_durable_store_options`（S2 accepted finding）。

#### 3.2.4 下游 fallback

无。`mark_wait_record_poll_abandon_timeout` 已完全删除（production/tests 零定义、零调用）。`_MarkWaitRecordAbandonTimeoutOperation` 同样完全删除。无 `_durable_options_from_public_options`、`_durable_options_from_command_options`、`_WaitPollerDiagnosticsHost`、`cast`、`_wait_poller` 残留（grep 零命中）。

#### 3.2.5 过度耦合或 speculative abstraction

无。`HostDurableStoreOptionsSource` 是 structural Protocol，只声明九个 durable storage construction 所需字段；它是 Python 标准 dependency inversion 实践，不是 profile/god bag/上层语义泄漏。S1 的 `_release_with_backoff` 复用既有的 `_WaitRecordReleaseWithBackoffOperation`，不是新增 coupling。S2 的 smoke 保持 packaged `ConfigLoader → provider discovery → Service composition → open_host → durable poller → public terminal/outbox` 主链，无 speculative abstraction。

### 3.3 Original plan dropped-count smoke 与 Ruff=165 被 supersede 是否有完整证据

**结论：有完整证据，不是 plan conformance 漂移。**

| Original plan text | Accepted supersede | Evidence |
|---|---|---|
| 原 smoke handoff 写 runner `dropped_count` | S2 initial review 确认这要求穿透 `_HostHandle._wait_poller`；Controller accepted finding 后改成 blocked-second-observation 的 public/durable owner facts，内部 counter 仅留 S1 owner test | S2 re-review §4.2 完整 happens-before 验证；S1 owner test `test_timeout_invalidates_token_and_late_result_cannot_publish` 仍断言 `dropped_count == 1` |
| 原 Ruff residual 预期 `165` 只包含 S1 两条删除 | S2 accepted review fix 实际触及 command/admin test 并删除三条同文件旧 F401，aggregate registry 为 `162` = `167 - 5` | S2 re-review §3.1 Ruff 精确 diff 验证；Controller aggregate validation §4 full Ruff 机器可读 registry 比较确认 |

S2 original "Engine production no diff"仍成立；durable construction helper change 是 code-review accepted finding 的窄 Host owner fix，不修改 Engine wait semantics。

### 3.4 `HostDurableStoreOptionsSource` / shared projection 是否仍是最小正确 owner

**结论：是最小正确 owner，不是为 smoke 反向塑造 production contract。**

完整走读验证：

1. `HostDurableStoreOptionsSource`（`durable/options.py:25-122`）是 structural Protocol，声明九个 `@property`，全部是 durable storage construction 所需字段。
2. `project_host_durable_store_options`（`durable/options.py:286-319`）是唯一构造 `PayloadStoragePolicy` + `HostSQLiteStoragePolicy` + `HostDurableStoreOptions` 的位置。
3. 所有 construction path 共用该 helper：`command.py:373`、`open_host.py:525/591/632/1310`、`smoke:1407`、`test_public_host_admin.py:209`。
4. Protocol 不持久化、不查找默认值、不解释额外字段、不拥有上层 opener 语义。
5. `HostCommandHandleOptions` 和 `OpenHostOptions` 都是 frozen dataclass，它们的同名 typed 属性自动满足该 Protocol，无需继承。
6. 该 helper 是 S2 code review 中发现的 accepted finding（消除 command/open-host/smoke 重复 nested policy construction），不是为 smoke 反向塑造的 production contract。它走过了完整的 dual review → Controller adjudication → AgentCodex fix → fix Controller validation → dual re-review chain。

### 3.5 Public smoke、owner tests、coverage、Ruff、pyright、README 与 source scans 是否真实且足以覆盖组合失败模式

**结论：真实且足够。**

#### 3.5.1 Public smoke

Controller 独立验证（`docs/reviews/wu-semantic-ownership-01-r05-s2-controller-validation.md:19-44`）：

```text
typed provider modes: poll/manual/callback
packaged policy: 12 fields exact snapshot
test effective: handshake=0.05, observation=0.15, operation=0.30,
                backoff=0.60, quantum=0.005, margin=0.03
handshake elapsed=0.001269 < 0.05
first observation: Run=WAITING, Wait=WAITING, claim released,
                   ADAPTER_ERROR/wait_observation_timeout, terminal outbox=0
late Ready dropped_count=1, Run still WAITING, terminal outbox=0
second observation after real due -> public RunSnapshot SUCCEEDED
terminal event/outbox exact match
all 11 named phases complete
```

覆盖的组合失败模式：
- timeout 不产生 terminal fact（首轮 Run/Wait 保持 WAITING，terminal outbox=0）
- late publication 无 authority（durable state 证明首轮 result 无发布权）
- typed LOST 与 timeout 的 branch 隔离（authoritative lost 走 resolver，timeout 走 backoff）
- Engine handshake timer 不拥有 accepted external operation（`handshake < 0.05 < operation`）
- config owner 与 composition 的完整链路（12-field policy snapshot exact match）

#### 3.5.2 Owner tests

| 测试文件 | 覆盖 | 断言对象 |
|---|---|---|
| `test_wait_observation_runner.py` | token fence、late publication dropped_count、invalidated_count | publication authority owner |
| `test_wait_adapter_polling.py` | poll/abandon timeout release/backoff、typed LOST、Ready/NotReady、claim CAS | `WaitPoller` 结果解释 owner |
| `test_wait_record_state.py` | explicit lifecycle terminal marker、claim release、diagnostic projection | `state.py` durable mutation owner |
| `test_phase7_waiting_integration.py` | timeout 保持 Wait/Run WAITING、late Ready 不污染下一轮 | 集成 contract |
| `test_durable_options.py` | `project_host_durable_store_options` 全字段映射、validation 分支 | durable construction owner |
| `test_engine_phase3_tool_call.py` | Engine handshake timer 不拥有 accepted awaiting operation | Engine handshake boundary |
| `test_public_host_admin.py` | admin seed、durable projection | public admin boundary |

所有测试断言 owner 级 contract 行为，不是固化偶然行为。

#### 3.5.3 Coverage

| 文件 | 覆盖率 | 门禁 |
|---|---|---|
| `state.py` | 83% | `--fail-under=80` PASS |
| `wait_adapter.py` | 86% | `--fail-under=80` PASS |
| `command.py` | 88% | `--fail-under=80` PASS |
| `open_host.py` | 85% | `--fail-under=80` PASS |
| `durable/options.py` | 100% | `--fail-under=80` PASS |

所有 changed-production 文件均 ≥80%。Engine `agent.py` branch-aware 78% / statement 80.458% 是既有 debt，`agent.py` 在 R05 base / S1 / S2 均 no diff，不是新增 changed-production coverage debt。

#### 3.5.4 Ruff

| 阶段 | 注册数 | 精确 diff |
|---|---|---|
| R05 fixed base | 167 | baseline |
| accepted S1 | 165 | `state.py:40 F401 TERMINAL_RUN_STATUS_VALUES` + `test_phase7_waiting_integration.py:8 F401 UTC` |
| aggregate | 162 | 上述两条 + `command.py:37 F401 AttemptStatus` + `command.py:105 F401 read_run_by_id` + `test_public_host_admin.py F401 create_host_command_handle` |

精确等于 `167 - 5`。其它 162 条 path/rule/location/message/severity 与 base 同源，无新增、替换或扩散。无 `noqa`、ignore 或 config 变更。

#### 3.5.5 Pyright

full pyright `0 errors, 0 warnings, 0 informations`。

#### 3.5.6 README 与 source scans

- `docs/host/design.md`：只改写 accepted plan 指定的精确句子。
- `dayu/host/README.md`：补当前 Waiting 稳定 contract。
- `tests/README.md`：同步 owner tests 与 aggregate public smoke 边界。
- Engine README：`agent.py` no diff，保持 no diff。
- 根 README / `dayu/README.md`：无触发。
- deferred scope source scan：`git diff --unified=0 ... | rg authorization|permission|callback transport|process isolation|Issue 175` — exit 1，零命中。

### 3.6 Retained safety 是否完整；Issue 175/callback/unified authorization/R06+ 是否偷带

**结论：retained safety 完整，deferred scope 未偷带。**

| 安全机制 | 状态 | 验证方式 |
|---|---|---|
| late publication token/generation fence | 保留 | `_wait_observation.py` no diff + `test_timeout_invalidates_token_and_late_result_cannot_publish` 通过 |
| outstanding capacity / shared close deadline | 保留 | `test_supervisor_close_uses_one_shared_deadline_and_stays_closing` 通过 |
| claim token CAS / release backoff / next-due claimability | 保留 | `test_active_poll_claim_suppresses_second_poller_adapter_call` + `test_expired_poll_claim_allows_retry` 通过 |
| authoritative typed lost via common resolver | 保留 | `test_poll_adapter_lost_result_closes_run` 通过 + idempotency key 断言 |
| explicit applied/unsupported/noop terminal marker | 保留 | `test_cancelled_poll_wait_is_abandoned_once_without_resolve` + `test_poll_abandon_success_marks_row_and_clears_claim` 通过 |
| invalid timeout-only symbol 零残留 | 确认 | `rg mark_wait_record_poll_abandon_timeout\|_MarkWaitRecordAbandonTimeoutOperation dayu tests` — exit 1，零匹配 |
| R04 config ownership / 12-field snapshot | 保留 | R04 preservation tests 通过 |
| cancellation / close-drain / capacity | 保留 | focused matrix 通过 |
| filesystem / durable storage safety | 保留 | production added-lines 零安全删除 |
| path containment | 保留 | no diff |

Deferred scope 验证：
- Issue 175（process isolation）：production added-lines 零命中。
- callback transport：production added-lines 零命中。
- unified authorization/permission schema：production added-lines 零命中。
- R06+ semantic ownership remediation：production added-lines 零命中。

### 3.7 Scheduler close / terminal promotion coordination 与 cancelled long-retry residual

#### 3.7.1 Scheduler close / terminal promotion coordination

**判定：material current finding，但不是 R05 blocker；classification 为 RETAINED RESIDUAL。**

直接证据：
- 确定性 probe `workspace/tmp/test_r05_scheduler_close_probe.py` 仍 `1 passed`（以预期 `HostApiError` 为通过条件），证明 close gate → clean EOF terminal closeout → promotion wake rejection 缺口仍可确定性复现。
- `dispatch.py`、`engine_ingest.py`、`test_dispatch_scheduler.py` 相对 R05 base 均 no diff。
- R05 owner symbols 对 `test_dispatch_scheduler.py` 零命中。
- R05 不修、不掩盖、不 waive、不归 Issue 175。

Owner/destination 评估：
- **Owner**：Host scheduler / lifecycle coordination owner。这不是 wait observation timeout 的 semantic owner，而是独立的 Host 内部 scheduler close 与 terminal promotion coordination 缺口。
- **Destination**：需要独立 Host scheduler lifecycle WU 修复。不得归入 R05 timeout owner，不得归入 Issue 175（process isolation），不得从 timeout 猜 LOST。
- **当前风险**：close gate 后 clean EOF terminal closeout 发生，但 queued Run promotion wake 被拒绝，导致 Run 可能滞留在 QUEUED 状态。这是一个真实但范围有限的 Host scheduler 内部状态机缺口。

此 residual 在 S1 re-review（§3.2.14）、S2 re-review（§4.5）、aggregate validation（§6）中均被独立验证为未修、未掩盖。本 aggregate deepreview 再次确认。

#### 3.7.2 Cancelled long-retry residual

**判定：retained residual，不是 R05 blocker。**

直接证据：
- 当 provider 永不返回 explicit lifecycle terminal outcome 时，cancelled wait 按 capped backoff 长期重试。
- 当前 claim CAS、finite timeout、capacity cap、late-result fence 与 backoff cap 只限制资源，不创造 terminal evidence。
- R05 不能从 observation timeout 猜测 durable terminal evidence。

Owner/destination 评估：
- **Owner**：future Host durable evidence policy owner。
- **Destination**：需要设计显式 durable evidence 条件来终止 cancelled wait 的长期重试。当前 R05 保证资源安全但不保证终止。

### 3.8 是否有新的组合 finding 需要 AgentCodex 当前修复

**结论：无。**

经逐项 adversarial challenge 验证，未发现任何需要 AgentCodex 当前修复的新组合 finding。所有 material findings 的 owner/fix boundary/verification 点已在 S1/S2 accepted review chain 中完整覆盖。

## 4. Finding ledger

| 编号 | 分类 | 描述 | owner / destination | aggregate 状态 |
|---|---|---|---|---|
| AGG-RES-01 | retained residual | scheduler close / terminal promotion coordination | Host scheduler lifecycle owner；需独立 WU | 未修、未掩盖、未归 Issue 175 |
| AGG-RES-02 | retained residual | cancelled wait abandon observation 持续 timeout 长期重试 | future Host durable evidence policy owner | R05 只保证资源安全，不保证终止 |
| AGG-DEF-01 | deferred | Issue 175 process isolation | 独立 GitHub Issue | tracked，未实施 |
| AGG-DEF-02 | deferred | callback transport | later WU/issue | 零实现 |
| AGG-DEF-03 | deferred | unified authorization/permission | later WU/issue | 零实现 |
| AGG-DEF-04 | deferred | R06+ semantic ownership remediation | later remediation owner | 零实现 |

## 5. Aggregate semantic verification 总结

### 5.1 Timeout 与 durable state

- observation timeout 只拥有 transient `ADAPTER_ERROR/wait_observation_timeout` diagnostic、claim release 与既有 backoff；poll Wait/Run 保持 `WAITING`。
- cancelled abandon timeout 保持 `CANCELLED`、释放 claim/backoff，不写 `poll_abandoned_at`。
- `mark_wait_record_poll_abandon_timeout` 与 `_MarkWaitRecordAbandonTimeoutOperation` 在 production/tests 零定义、零调用；schema 无 diff。
- explicit provider lifecycle terminal marker 仍由 Fins/Host typed outcome route 写 `poll_abandoned_at`；authoritative `WaitPollLost` / `ResolveWaitLostOutcome` 保持。

### 5.2 Publication authority 与 public smoke

- `_wait_observation.py` token/generation/lock 仍是唯一 late-result publication authority，no diff。
- S1 owner tests 直接断言 timeout invalidation 后 late result 被 runner 丢弃，不污染下一轮。
- S2 public smoke 不把 runner diagnostics 提升为 Host public contract；它在首轮 late Ready 返回、第二轮 real claim active 且 adapter 尚未返回的 boundary，通过 public Run/outbox + durable Wait facts 证明首轮无发布权。
- Controller fresh smoke PASS 全部成立。

### 5.3 Engine 与 config ownership

- Engine production no diff；S2 新增 regression 在现有 production 上直接证明 executor handshake 返回后，accepted awaiting external operation 可越过 handshake timeout 且不被 Engine timer 取消。
- R04 provider poll/manual/callback typed modes 仍由 `tool_discovery.json` provider config owner。
- 12-field poller runtime policy 仍由 `host_runtime.json` owner。
- Service 不再 scene/name heuristic 构造默认 policy。

### 5.4 Durable construction owner

- `HostDurableStoreOptionsSource` 与 `project_host_durable_store_options(...)` 收敛 command/open-host/smoke 重复 nested policy construction。
- 该扩展已走完整 dual review/fix/re-review，不是未审 allowlist 漂移。
- durable 下层不 import 上层 opener type，所有 construction consumers 共用一个 typed owner。

## 6. Gate verification 矩阵

所有 Python 命令均在 `.venv` 激活后运行。

| Gate | Result |
|---|---|
| R05 ten-file functional aggregate | `360 passed, 3` 个第三方 edgar deprecation warnings |
| fresh public awaiting smoke | PASS，11 phases 完成 |
| durable projection owner + public admin focused | `11 passed` |
| R05 S1 changed-owner coverage session | `1839 passed, 2 skipped, 5 deselected`；`state.py 83%`、`wait_adapter.py 86%` |
| R05 S2 changed-production coverage session | `1840 passed, 1 skipped, 5 deselected`；`command.py 88%`、`open_host.py 85%`、`durable/options.py 100%` |
| full pyright | `0 errors, 0 warnings, 0 informations` |
| changed Python Ruff | `All checks passed!` |
| full Ruff registry | R05 fixed base `167` → accepted S1 `165` → aggregate `162`（精确 `167 - 5`） |
| `git diff --check` / working tree | PASS / clean |
| scheduler deterministic residual probe | `1 passed`，仍以预期 `HostApiError` 为直接证据 |
| deferred scope source scan | exit 1，零命中 |
| invalid timeout-only symbol guard | exit 1，零匹配 |
| no-diff audit（`_wait_observation.py`、`waiting.py`、`schema.py`、`agent.py`、`dispatch.py`、`engine_ingest.py`） | PASS |

## 7. Open Questions

无。所有 adversarial challenge 子项均已有直接 evidence 支撑的裁决。

## 8. Residual Risk

| Residual | 分类 | 风险 |
|---|---|---|
| scheduler close / terminal promotion coordination | retained residual | Host scheduler 内部状态机缺口，close gate 后 promotion wake 可能被拒绝；确定性 probe 可复现 |
| cancelled wait abandon 长期重试 | retained residual | provider 永不返回 explicit terminal outcome 时按 capped backoff 长期重试；R05 保证资源安全但不保证终止 |
| smoke timing margin（0.03s / 5×0.005s） | low | durable state 一旦成立不会瞬时消失；15s deadline 有大量 headroom |
| `backoff_max == initial` in smoke | low | smoke 只验证首轮 retry initial backoff，cap 不生效 |
| Engine branch-aware 78% / statement 80.458% | low | `agent.py` 在 R05 base / S1 / S2 均 no diff，不是新增 debt |
| Issue 175 process isolation | tracked | 未实施，物理进程终止不自动成为 Host durable terminal fact |
| callback transport / unified authorization / R06+ | deferred | 本 aggregate 确认未进入 |

## 9. 最终裁决

**PASS / 无 material current finding / 无 required fix gate。**

R05 两个 implementation slices 的组合行为正确：S1 的 timeout release/backoff transaction 与 S2 的 public smoke/durable construction owner 在 aggregate 架构中完全一致。所有 Topic 5 裁决子项组合闭环。S1/S2 未出现 semantic ownership drift、第二真源、下游 fallback、过度耦合或 speculative abstraction。Original plan 的 dropped-count smoke 与 Ruff=165 被后续 accepted review supersede 有完整证据链。`HostDurableStoreOptionsSource` / shared projection 是最小正确 owner。public smoke、owner tests、coverage、Ruff、pyright、README 与 source scans 真实且足以覆盖组合失败模式。retained safety 完整，deferred scope 未偷带。

两项 retained residual 有明确 owner/destination：
1. scheduler close / terminal promotion coordination → Host scheduler lifecycle owner（独立 WU，非 R05）。
2. cancelled abandon 长期重试 → future Host durable evidence policy owner。

四类 deferred scope 保持 zero implementation。

本 review verdict 不独立授权 commit；Controller 必须裁决全部 findings（本路为零 material finding + 两项 retained residual），并决定是否需要第二路 AgentDS aggregate deepreview 或可直接推进。

---

**Reviewer**：AgentMiMo
**Date**：2026-07-16
**Review type**：R05 aggregate deepreview（第一路）
**Reviewed digest**：`41bd8c057cb5ff3d389f909a367a19037a65ae59ffda377cd317b9d1db4eda9a`
