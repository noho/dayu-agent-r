# WU-SEMANTIC-OWNERSHIP-01 R05 Aggregate Re-Review — AgentMiMo（第一路）

日期：2026-07-16

## 1. Scope 与 verdict

- umbrella：`WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation；不是新 WU。
- aggregate gate：R05 wait observation/state-machine ownership 全量 aggregate re-review。
- R05 entry base：`5ba0d8b61f9d03f52c4529f5b83a6cd353d002b1`。
- accepted S1 commit：`c5af5613b21673864fff072a132ac56a46cc9836`。
- accepted S2 commit：`ff7b0b1825491ee3690a45d56a059c5da00af7aa`。
- aggregate product transaction digest：`41bd8c057cb5ff3d389f909a367a19037a65ae59ffda377cd317b9d1db4eda9a`。
- AgentMiMo initial deepreview：`docs/reviews/wu-semantic-ownership-01-r05-aggregate-deepreview-mimo.md`。
- AgentDS initial deepreview：`docs/reviews/wu-semantic-ownership-01-r05-aggregate-deepreview-ds.md`。
- Controller adjudication：`docs/reviews/wu-semantic-ownership-01-r05-aggregate-deepreview-controller-adjudication.md`。
- AgentCodex zero-change fix：`docs/reviews/wu-semantic-ownership-01-r05-aggregate-deepreview-fix-codex.md`。
- Controller fix validation：`docs/reviews/wu-semantic-ownership-01-r05-aggregate-deepreview-fix-controller-validation.md`。

**Verdict：PASS — 无 material current finding；zero-change 唯一写入且 product digest 保持不变；`0/3/2/0` ledger 正确；no-fix observations 未被误关；两项 retained residual 仍真实、未修、未 waive 且 owner/destination 充分；retained safety/deferred/no-code boundary 未漂移；未出现新 material finding。**

## 2. Reviewed evidence 列表

本 re-review 完整读取并交叉核对以下 evidence：

1. `AGENTS.md` — 完整读取。
2. `docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md` — Topic 5 完整读取（lines 335-433）。
3. `docs/host/design.md` — wait configuration ownership、poller runtime policy、`host_runtime.json` 章节。
4. `docs/engine/design.md` — §10-§15 waiting/handshake 章节。
5. `docs/host/wu-semantic-ownership-01-r05-wait-observation-state-machine-plan.md` — accepted plan 完整读取。
6. `docs/reviews/wu-semantic-ownership-01-r05-aggregate-validation.md` — aggregate validation 完整读取。
7. `docs/reviews/wu-semantic-ownership-01-r05-aggregate-deepreview-mimo.md` — initial MiMo deepreview 完整读取。
8. `docs/reviews/wu-semantic-ownership-01-r05-aggregate-deepreview-ds.md` — initial DS deepreview 完整读取。
9. `docs/reviews/wu-semantic-ownership-01-r05-aggregate-deepreview-controller-adjudication.md` — Controller adjudication 完整读取。
10. `docs/reviews/wu-semantic-ownership-01-r05-aggregate-deepreview-fix-codex.md` — Codex zero-change fix 完整读取。
11. `docs/reviews/wu-semantic-ownership-01-r05-aggregate-deepreview-fix-controller-validation.md` — Controller fix validation 完整读取。
12. 16-path product/test/design/README diff — `git diff 5ba0d8b6..HEAD` 对 16 paths。
13. `dayu/host/wait_adapter.py` — poll timeout（line 1072-1085）与 abandon timeout（line 1320-1334）分支直接走读。
14. `dayu/host/durable/options.py` — `HostDurableStoreOptionsSource` Protocol 与 `project_host_durable_store_options` 直接走读。
15. `dayu/host/_wait_observation.py` — no-diff 验证 + token/fence 机制确认。
16. `dayu/engine/agent.py` — no-diff 验证。
17. `dayu/host/dispatch.py` — no-diff 验证 + scheduler residual 确认。
18. `dayu/host/engine_ingest.py` — no-diff 验证。
19. `workspace/tmp/test_r05_scheduler_close_probe.py` — scheduler deterministic probe 走读。

## 3. Adversarial challenge 逐项验证

### 3.1 Topic 5 组合闭环验证

**结论：全部闭环，无 gap。**

本 re-review 独立验证 Topic 5 七项裁决子项，结论与 initial deepreview 一致：

| 子项 | 设计真源 | 代码验证 | re-review verdict |
|---|---|---|---|
| provider mode/config owner | `tool_discovery.json` provider config 拥有 `poll`/`callback`/`manual` | `_binding_for_tool_name` 接收 typed `AwaitingResolutionMode`，不再 hard-code `POLL` | PASS |
| runtime policy owner | `host_runtime.json` 拥有 12-field poller runtime policy | `WaitPollerRuntimePolicy` 从 config 构造；无参 `WaitPollerRuntimePolicy()` 零匹配（rg exit 1） | PASS |
| Service composition | Service 不从 scene/name heuristic 构造默认 policy | scene/name heuristic helper 零匹配（rg exit 1） | PASS |
| timeout release/backoff | poll/abandon timeout → transient diagnostic + claim release/backoff | `wait_adapter.py:1078`（poll）与 `wait_adapter.py:1326`（abandon）均调用 `_release_with_backoff`，不调用 `_resolve_claimed_wait` | PASS |
| late publication | `_wait_observation.py` token/generation/lock 是唯一 publication authority | no-diff 确认；S1 owner tests 断言 timeout invalidation 后 late result 被丢弃 | PASS |
| typed LOST | 只有 adapter 显式返回 `WaitPollLost` 时走 `_resolve_claimed_wait` | `wait_adapter.py:1124` `WaitPollLost` 分支保留；timeout 分支不构造 `WaitPollLost` | PASS |
| Engine handshake timer | `agent.py` no diff；Engine 只在 executor 返回前使用 handshake timeout | `git diff` 0 行确认；S2 regression test 通过 | PASS |

**组合链路**：R04 config handoff → Service composition → `open_host` → `WaitPoller` poll/abandon timeout release/backoff → token fence late publication guard → typed LOST resolver → Engine handshake boundary —— 完整链路无断点。

### 3.2 Zero-change 唯一写入与 product digest 保持

**结论：确认。**

独立复算结果：

| 证据 | 值 |
|---|---|
| 16-path binary diff digest | `41bd8c057cb5ff3d389f909a367a19037a65ae59ffda377cd317b9d1db4eda9a` |
| 16-path path-set digest | `ff3b00d67510c45396305a723a939b8006e9e740e61c8ff23ea6fb86e8389f4f` |

两者与 aggregate validation、两路 initial deepreview、Controller adjudication、AgentCodex fix record 和 Controller fix validation 的 frozen value 精确一致。

当前 worktree 状态（排除本 artifact）精确为：

```text
 M docs/host/issues-implementation-control.md
?? docs/reviews/wu-semantic-ownership-01-r05-aggregate-deepreview-controller-adjudication.md
?? docs/reviews/wu-semantic-ownership-01-r05-aggregate-deepreview-ds.md
?? docs/reviews/wu-semantic-ownership-01-r05-aggregate-deepreview-fix-codex.md
?? docs/reviews/wu-semantic-ownership-01-r05-aggregate-deepreview-fix-controller-validation.md
?? docs/reviews/wu-semantic-ownership-01-r05-aggregate-deepreview-mimo.md
```

AgentCodex zero-change fix artifact（`fix-codex.md`）与 Controller fix validation（`fix-controller-validation.md`）是 initial deepreview 后唯一新增的 untracked 文件。product/test/design/README/control/既有 review artifacts 均未变化。staged paths 为 `0`。

### 3.3 `0/3/2/0` ledger 验证

**结论：正确。**

| 分类 | 数量 | 状态 | 验证 |
|---|---|---|---|
| accepted current finding | 0 | CLOSED / NO PRODUCT FIX | 两路 deepreview 均 PASS，Controller adjudication 确认 |
| no-fix observation | 3 | CLOSED WITH REASON | 见 §3.4 |
| retained residual | 2 | OPEN AT EXPLICIT LATER OWNER | 见 §3.5 |
| blocker | 0 | NONE | 两路 deepreview 均无 blocker |

### 3.4 No-fix observations 未被误关

**结论：未被误关；每条 disposition 有直接理由。**

| observation | Controller disposition | re-review 验证 |
|---|---|---|
| `options.py` 缺少 `__all__` | `NO_CURRENT_DEFECT / NO_FIX` | 确认：当前符号均由精确模块 import 使用，无 package re-export 或稳定顶层 API 承诺。机械增加 `__all__` 不修复 correctness/ownership/public contract。 |
| scheduler close + poll timeout + late result 跨 owner 压力测试尚缺 | `OUTSIDE_R05_OWNER / NO_R05_FIX` | 确认：该组合的正确 terminal coordination oracle 依赖 scheduler lifecycle residual 的后续修复。当前先添加组合测试既不能提供正确 oracle，也可能把独立 scheduler owner 偷带进 R05。 |
| smoke timing margin、单次 backoff cap、Engine 既有 branch coverage | `LOW / NO_FIX` | 确认：durable/event happens-before 提供直接同步保证；smoke 总 deadline 有大量 headroom；Engine `agent.py` 在 R05 base/S1/S2 均 no diff。 |

三条 observation 的 disposition 均基于直接证据，不是"因为没有 finding 所以关闭"的机械操作。

### 3.5 Retained residuals 仍真实、未修、未 waive

#### 3.5.1 Scheduler close / terminal promotion coordination

**判定：仍为确定性真实 material bug；RETAINED / UNFIXED / UNWAIVED。**

直接证据：
- `workspace/tmp/test_r05_scheduler_close_probe.py` 以预期 `HostApiError`（`UNAVAILABLE` code）为通过条件，证明 close gate → clean EOF terminal closeout → promotion wake rejection 缺口仍可确定性复现。
- `dayu/host/dispatch.py` 与 `dayu/host/engine_ingest.py` 相对 R05 base 均 no diff（`git diff --stat` 零输出）。
- R05 product transaction 不包含 scheduler 修改。
- 该 residual 在 S1 re-review、S2 re-review、aggregate validation、initial MiMo deepreview、initial DS deepreview、Controller adjudication、Codex fix record 和 Controller fix validation 八个文档中均被显式记录。

Owner/destination：Host scheduler/lifecycle coordination owner；需要独立显式 work item；不得归 Issue 175；umbrella final closeout 必须保留明确入口。

#### 3.5.2 Cancelled abandon 长期 retry

**判定：仍为真实终止性 residual；RETAINED / UNFIXED / UNWAIVED。**

直接证据：
- 当 provider 永不返回 explicit lifecycle terminal outcome 时，cancelled wait 按 capped backoff 长期重试。
- `_release_with_backoff`（line 1455）释放 claim 并写 backoff，但不产生 durable terminal evidence。
- R05 正确地不从 timeout 猜 LOST。

Owner/destination：future Host durable evidence policy owner；后续显式 contract/design work；不得从 timeout/retry count/timestamp 猜 LOST。

### 3.6 S1/S2 semantic ownership drift 检查

**结论：无 drift、无第二真源、无下游 fallback、无过度耦合。**

逐维度验证：

#### 3.6.1 Semantic ownership drift

S1 的唯一产品 transaction 精确落在 semantic owner boundary：
- `WaitPoller`（`wait_adapter.py`）是 poll/abandon observation timeout 结果解释与 claim release/backoff policy 的 owner。
- `release_wait_record_poll_claim`（`state.py`）是 atomic claim release、next-observe、attempt 与 diagnostic projection 的 owner。
- `mark_wait_record_poll_abandoned`（`state.py`）是 explicit applied/unsupported/noop lifecycle outcome 的 terminal `poll_abandoned_at` 写入 owner。
- `_wait_observation.py`（no diff）是 token identity、state、generation 与 publication fence 的 owner。
- `docs/host/design.md`（精确句子改写）是 wait contract 设计真源。

无任何下游消费者通过 fallback、特例、重复计算、loose parsing、`hasattr/getattr`、默认值或兼容分支补齐上游 contract。

#### 3.6.2 第二真源

无。逐项确认：
- observation timeout 结果解释：唯一 owner 是 `WaitPoller._poll_once()` 的 timeout 分支。
- claim release/backoff：唯一 owner 是 `_release_with_backoff`。
- publication authority：唯一 owner 是 `_wait_observation.py` token/generation/lock。
- durable construction projection：唯一 owner 是 `project_host_durable_store_options`。

#### 3.6.3 下游 fallback

无。`mark_wait_record_poll_abandon_timeout` 与 `_MarkWaitRecordAbandonTimeoutOperation` 在 production/tests 零定义、零调用（rg exit 1）。`_durable_options_from_public_options`、`_durable_options_from_command_options` 零匹配（rg exit 1）。changed production files 中 `hasattr`/`getattr` 零命中。

#### 3.6.4 过度耦合或 speculative abstraction

无。`HostDurableStoreOptionsSource` 是 structural Protocol，只声明九个 durable storage construction 所需字段；它是 Python 标准 dependency inversion 实践，不是 profile/god bag/上层语义泄漏。`project_host_durable_store_options` 是纯函数，不持有状态、不 side-effect。

### 3.7 `HostDurableStoreOptionsSource` / shared projection 是否仍是最小正确 owner

**结论：是最小正确 owner。**

独立走读验证：
1. `HostDurableStoreOptionsSource`（`durable/options.py:25`）是 structural Protocol，声明九个 `@property`，全部是 durable storage construction 所需字段。
2. `project_host_durable_store_options`（`durable/options.py:286`）是唯一构造 `PayloadStoragePolicy` + `HostSQLiteStoragePolicy` + `HostDurableStoreOptions` 的位置。
3. 所有 construction path 共用该 helper：`command.py`、`open_host.py`、smoke、`test_public_host_admin.py`。
4. Protocol 不持久化、不查找默认值、不解释额外字段、不拥有上层 opener 语义。
5. 该 helper 是 S2 code review 中发现的 accepted finding（消除 command/open-host/smoke 重复 nested policy construction），不是为 smoke 反向塑造的 production contract。

### 3.8 Retained safety 是否完整

**结论：完整。**

| 安全机制 | 状态 | 验证方式 |
|---|---|---|
| late publication token/generation fence | 保留 | `_wait_observation.py` no diff |
| outstanding capacity / shared close deadline | 保留 | existing tests 通过 |
| claim token CAS / release backoff / next-due claimability | 保留 | existing tests 通过 |
| authoritative typed lost via common resolver | 保留 | `WaitPollLost` branch at line 1124 保持 |
| explicit applied/unsupported/noop terminal marker | 保留 | `mark_wait_record_poll_abandoned` 函数保持 |
| invalid timeout-only symbol 零残留 | 确认 | rg exit 1，零匹配 |
| R04 config ownership / 12-field snapshot | 保留 | R04 preservation tests 通过 |
| cancellation / close-drain / capacity | 保留 | focused matrix 通过 |
| filesystem / durable storage safety | 保留 | production added-lines 零安全删除 |

### 3.9 Issue 175/callback/unified authorization/R06+ 是否偷带

**结论：未偷带。**

Deferred scope 验证：
- Issue 175（process isolation）：production added-lines 零命中（rg exit 1）。
- callback transport：production added-lines 零命中（rg exit 1）。
- unified authorization/permission schema：production added-lines 零命中（rg exit 1）。
- R06+ semantic ownership remediation：production added-lines 零命中。

### 3.10 是否有新的组合 finding 需要 AgentCodex 当前修复

**结论：无。**

经逐项 adversarial challenge 验证，未发现任何需要 AgentCodex 当前修复的新组合 finding。

## 4. Finding ledger

| 编号 | 分类 | 描述 | owner / destination | re-review 状态 |
|---|---|---|---|---|
| AGG-RES-01 | retained residual | scheduler close / terminal promotion coordination | Host scheduler lifecycle owner；需独立 WU | 未修、未掩盖、未归 Issue 175、未 waive |
| AGG-RES-02 | retained residual | cancelled wait abandon observation 持续 timeout 长期重试 | future Host durable evidence policy owner | R05 只保证资源安全，不保证终止 |
| AGG-DEF-01 | deferred | Issue 175 process isolation | 独立 GitHub Issue | tracked，未实施 |
| AGG-DEF-02 | deferred | callback transport | later WU/issue | 零实现 |
| AGG-DEF-03 | deferred | unified authorization/permission | later WU/issue | 零实现 |
| AGG-DEF-04 | deferred | R06+ semantic ownership remediation | later remediation owner | 零实现 |

No-fix observations（3 组）均 CLOSED WITH REASON，未被误关为 accepted finding 或被隐含 waive。

## 5. Gate verification 矩阵

本 re-review 独立执行的 source/security/diff scans：

| 检查 | 结果 |
|---|---|
| 16-path binary diff digest | `41bd8c057cb5ff3d389f909a367a19037a65ae59ffda377cd317b9d1db4eda9a` — 与 frozen value 精确一致 |
| 16-path path-set digest | `ff3b00d67510c45396305a723a939b8006e9e740e61c8ff23ea6fb86e8389f4f` — 与 frozen value 精确一致 |
| no-diff owners | `agent.py`、Engine README、`_wait_observation.py`、`waiting.py`、durable schema、`dispatch.py`、`engine_ingest.py`、scheduler test 相对 R05 base empty diff |
| timeout-only terminal symbols | `mark_wait_record_poll_abandon_timeout`、`_MarkWaitRecordAbandonTimeoutOperation` 对 `dayu tests` 零匹配（rg exit 1） |
| private smoke diagnostics | `_WaitPollerDiagnosticsHost`、`runner_dropped_count`、`observation_diagnostics_snapshot`、`._wait_poller`、`cast(` 零匹配（rg exit 1） |
| duplicate durable projection | `_durable_options_from_public_options`、`_durable_options_from_command_options` 零匹配（rg exit 1） |
| unique durable projection | `HostDurableStoreOptionsSource` 与 `project_host_durable_store_options` 唯一定义于 `dayu/host/durable/options.py` |
| old composition fallback | scene/name helper 与无参 `WaitPollerRuntimePolicy()` 零匹配（rg exit 1） |
| deferred/security added lines | `authorization`、`permission`、callback transport、process isolation、`process_backed`、`subprocess`、`Issue 175` 零新增匹配（rg exit 1） |
| `git diff --check` | PASS |

既有 Controller validation evidence（仅引用，未重跑）：aggregate functional `360 passed`、fresh public smoke PASS（11 phases）、S1 coverage `83%/86%`、S2 coverage `88%/85%/100%`、full pyright zero、changed Ruff green、full Ruff `167→165→162`、scheduler probe `1 passed`。

## 6. Open Questions

无。所有 adversarial challenge 子项均已有直接 evidence 支撑的裁决。

## 7. Residual Risk

| Residual | 分类 | 风险 |
|---|---|---|
| scheduler close / terminal promotion coordination | retained residual | Host scheduler 内部状态机缺口，close gate 后 promotion wake 可能被拒绝；确定性 probe 可复现 |
| cancelled wait abandon 长期重试 | retained residual | provider 永不返回 explicit terminal outcome 时按 capped backoff 长期重试；R05 保证资源安全但不保证终止 |
| smoke timing margin（0.03s / 5×0.005s） | low | durable state 一旦成立不会瞬时消失；15s deadline 有大量 headroom |
| `backoff_max == initial` in smoke | low | smoke 只验证首轮 retry initial backoff，cap 不生效 |
| Engine branch-aware 78% / statement 80.458% | low | `agent.py` 在 R05 base / S1 / S2 均 no diff，不是新增 debt |
| Issue 175 process isolation | tracked | 未实施，物理进程终止不自动成为 Host durable terminal fact |
| callback transport / unified authorization / R06+ | deferred | 本 re-review 确认未进入 |

## 8. 最终裁决

**PASS / 无 material current finding / 无 required fix gate。**

本 re-review 独立验证了以下全部 challenge：

1. **Topic 5 组合闭环**：七项裁决子项全部闭环，config → Service → Host → timeout → fence → typed LOST → Engine boundary 完整链路无断点。
2. **Zero-change 唯一写入**：product digest `41bd8c05...` 保持不变；AgentCodex 唯一写入为 fix artifact；product/test/design/README/control/既有 review artifacts 均未变化。
3. **`0/3/2/0` ledger 正确**：accepted current finding 为零；三条 no-fix observation 各有直接理由且未被误关；两项 retained residual 有明确 owner/destination。
4. **No-fix observations 未被误关**：`__all__` 缺失不构成 defect；跨 owner 组合测试归 scheduler residual 修复后 mandatory verification；timing/coverage 有直接 evidence。
5. **Retained residuals 仍真实、未修、未 waive**：scheduler close 确定性 probe 可复现；cancelled abandon 长期重试无 durable terminal evidence。
6. **Retained safety 完整**：token fence、claim CAS、capacity、typed LOST、explicit terminal marker、config owner、filesystem containment 均保留。
7. **Deferred boundary 未漂移**：Issue 175、callback、统一 authorization、R06+ 均零实现、零偷带。
8. **无新 material finding**。

本 review verdict 不独立授权 commit；Controller 必须裁决全部 findings（本路为零 material finding + 两项 retained residual），并决定是否需要第二路 AgentDS aggregate re-review 或可直接推进。

---

**Reviewer**：AgentMiMo
**Date**：2026-07-16
**Review type**：R05 aggregate re-review（第一路）
**Reviewed digest**：`41bd8c057cb5ff3d389f909a367a19037a65ae59ffda377cd317b9d1db4eda9a`
