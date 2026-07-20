# WU-SEMANTIC-OWNERSHIP-01 R05 Aggregate Deepreview Fix — AgentCodex Zero-Change Record

日期：2026-07-16

## 1. Gate identity、第一性原理判断与结论

| 项目 | 值 |
|---|---|
| umbrella | `WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation；不是新 WU、feature 或 issue |
| internal remediation sub-WU | R05 wait observation/state-machine ownership |
| gate | R05 aggregate zero-change fix record |
| R05 entry base | `5ba0d8b61f9d03f52c4529f5b83a6cd353d002b1` |
| accepted plan commit | `201eb7f5287fc8e73d05b442e84369e19928236a` |
| accepted S1 commit | `c5af5613b21673864fff072a132ac56a46cc9836` |
| accepted S2 commit | `ff7b0b1825491ee3690a45d56a059c5da00af7aa` |
| Controller verdict | `PASS / ZERO_ACCEPTED_CURRENT_FINDING / ZERO-CHANGE FIX RECORD REQUIRED` |
| accepted / no-fix observation groups / retained residual / blocker | `0 / 3 / 2 / 0` |
| 唯一 write allowlist | `docs/reviews/wu-semantic-ownership-01-r05-aggregate-deepreview-fix-codex.md` |
| completion status | `WAITING_FOR_CONTROLLER_VALIDATION` |

本 gate 的流程动机成立，但不存在可修的 R05 产品 defect。两路 aggregate deepreview 均已完整验证 Topic 5、S1/S2 组合行为、plan supersession、durable construction owner、安全保留项与 deferred boundary；Controller 裁决 accepted current finding 为零。此时修改 product、test、design、README、control 或既有 artifact，都会把 no-fix observation 或 later-owner residual 擅自升级为 R05 产品语义，反而破坏已确认的 owner boundary。

因此正确 fix 是零产品改动：只新增本 durable gate record，冻结并复算 16-path aggregate transaction，记录 finding ledger、只读扫描、创建前后 worktree 证据与下一 gate。本轮没有 stage、commit、push，也没有进入 re-review、R05 acceptance/completion、scheduler fix、Issue 175、callback、统一 authorization 或 R06+。

## 2. 完整读取、scope 与 owner boundary

本记录完整读取并交叉核对：

1. `AGENTS.md`；
2. `docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md` Topic 5；
3. `docs/host/wu-semantic-ownership-01-r05-wait-observation-state-machine-plan.md`；
4. `docs/reviews/wu-semantic-ownership-01-r05-aggregate-validation.md`；
5. `docs/reviews/wu-semantic-ownership-01-r05-aggregate-deepreview-mimo.md`；
6. `docs/reviews/wu-semantic-ownership-01-r05-aggregate-deepreview-ds.md`；
7. `docs/reviews/wu-semantic-ownership-01-r05-aggregate-deepreview-controller-adjudication.md`；
8. `docs/host/issues-implementation-control.md` 当前 gate、next entry point 与 R05 状态行。

直接证据继续支持既有 owner 裁决：

- provider resolution mode 由 provider config 拥有，Host poller runtime policy 由 Host runtime config 拥有；Service 只装配，不从 scene/name 推导默认 policy；
- `WaitPoller` 拥有 observation timeout 的 policy 解释，既有 durable release operation 拥有 claim/backoff/diagnostic 原子投影；timeout 不产生 LOST 或 terminal abandon；
- `_wait_observation.py` 的 token/generation/lock 仍是唯一 late-publication authority；
- authoritative typed LOST 与 explicit lifecycle terminal outcome 保留各自 owner；
- Engine handshake timer 不拥有已经接受的 awaiting 外部长事务；
- shared durable options projection 由 `dayu.host.durable.options` 唯一拥有。

本 gate 的非目标是任何产品或测试修复、scheduler residual 修复、cancelled retry policy 设计、Issue 175、callback transport、统一 authorization、R06+、README/control 同步或外部状态变更。

## 3. Finding ledger 与 zero-change disposition

### 3.1 Accepted current findings

数量为 `0`。Controller 已确认当前 16-path transaction 满足 Topic 5，不存在本 gate 可修的 correctness、stability、ownership 或 public-contract finding。

### 3.2 No-fix observations

| observation | disposition | 本 gate动作 |
|---|---|---|
| `dayu/host/durable/options.py` 未声明 `__all__` | `NO_CURRENT_DEFECT / NO_FIX`；当前只有精确模块 import，无 package re-export 或稳定顶层 API 承诺 | 不修改 |
| scheduler close + poll timeout + late result 的跨 owner 压力测试尚缺 | `OUTSIDE_R05_OWNER / NO_R05_FIX`；正确 oracle 依赖 scheduler lifecycle residual 的后续修复 | 不以测试 shim 偷带 scheduler owner；登记为该 residual 后续 mandatory verification |
| smoke timing margin、单次 backoff cap 与 Engine 既有 branch coverage | `LOW / NO_FIX`；durable/event happens-before、overall deadline 与 Engine no-diff 证据充分 | 不修改 |

### 3.3 Final ledger

| 分类 | 数量 | 状态 |
|---|---:|---|
| accepted current finding | 0 | `CLOSED / NO PRODUCT FIX` |
| no-fix observation | 3 组 | `CLOSED WITH REASON` |
| retained residual | 2 | `OPEN AT EXPLICIT LATER OWNER`；R05 中未修、未 waive |
| blocker | 0 | `NONE` |

## 4. Frozen 16-path aggregate transaction

### 4.1 精确路径集合

受保护 product/test/design/README transaction 精确为：

1. `dayu/host/durable/state.py`
2. `dayu/host/wait_adapter.py`
3. `docs/host/design.md`
4. `tests/host/test_phase7_waiting_integration.py`
5. `tests/host/test_wait_adapter_polling.py`
6. `tests/host/test_wait_observation_runner.py`
7. `tests/host/test_wait_record_state.py`
8. `tests/engine/test_agent_phase3_tool_call.py`
9. `utils/smoke_host_public_awaiting_entrypoint.py`
10. `dayu/host/durable/options.py`
11. `dayu/host/command.py`
12. `dayu/host/open_host.py`
13. `tests/host/test_durable_options.py`
14. `tests/host/test_public_host_admin.py`
15. `dayu/host/README.md`
16. `tests/README.md`

相对 R05 entry base 复算命令：

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

创建本 artifact 前的 path/content digest 为：

```text
41bd8c057cb5ff3d389f909a367a19037a65ae59ffda377cd317b9d1db4eda9a
```

与 Controller aggregate validation、两路 deepreview 和 Controller adjudication 的 frozen value 精确一致。相同 16-path `git diff --name-only` 有序 path-set digest 为：

```text
ff3b00d67510c45396305a723a939b8006e9e740e61c8ff23ea6fb86e8389f4f
```

创建后复算结果记录于 §6；本 artifact 不属于该 transaction。

### 4.2 创建前 worktree evidence

创建前 `git status --porcelain=v1 --untracked-files=all` 精确为 `4` 条：

```text
 M docs/host/issues-implementation-control.md
?? docs/reviews/wu-semantic-ownership-01-r05-aggregate-deepreview-controller-adjudication.md
?? docs/reviews/wu-semantic-ownership-01-r05-aggregate-deepreview-ds.md
?? docs/reviews/wu-semantic-ownership-01-r05-aggregate-deepreview-mimo.md
```

该 canonical status 的 SHA-256 为：

```text
2976dd50b45e1e5fe56243dbf576fe37b6e33bcb21181fc9b5f836d0b6cb2e62
```

四个既有 dirty path 的逐文件 SHA-256 为：

```text
461b0f0798c20e42e8e6976751435abc3d11c941e7f04be7e58339a23130f4a6  docs/host/issues-implementation-control.md
f1402b98d474506f242e38ff52d18c918f1315bed41d7c04b8c6f43e2a80d099  docs/reviews/wu-semantic-ownership-01-r05-aggregate-deepreview-controller-adjudication.md
26aa2e8f86e1d518a251a885cc263f1ef6a367564e23391c2f7a1cf292aca1ed  docs/reviews/wu-semantic-ownership-01-r05-aggregate-deepreview-ds.md
8ca04c7ac955b225e6e2f08d920a24064e9a5debc73a7119de3716d6ad1297b5  docs/reviews/wu-semantic-ownership-01-r05-aggregate-deepreview-mimo.md
```

上述有序 manifest 自身 digest 为 `aaa13ec90e290326b0dd98eb04cb98f0708b6fa141d15a810d1f56852254df39`。创建前 staged path count 为 `0`。

## 5. Diff、source、security 与 no-diff scans

以下检查只读执行；负向 `rg` 的 exit `1` 表示零匹配，是预期 PASS。

| 检查 | 结果 |
|---|---|
| `git diff --check` | exit `0`，无输出 / PASS |
| R05 no-diff owners | 相对 entry base，`dayu/engine/agent.py`、`dayu/engine/README.md`、`dayu/host/_wait_observation.py`、`dayu/host/waiting.py`、`dayu/host/durable/schema.py`、`dayu/host/dispatch.py`、`dayu/host/engine_ingest.py`、`tests/host/test_dispatch_scheduler.py` empty diff / PASS |
| timeout-only terminal symbols | `mark_wait_record_poll_abandon_timeout`、`_MarkWaitRecordAbandonTimeoutOperation` 对 `dayu tests` 零匹配，`rg` exit `1` / PASS |
| timeout branch audit | poll timeout 仍调用 `_release_with_backoff(... ADAPTER_ERROR, wait_observation_timeout)`；cancelled abandon timeout 仍调用 `_release_with_backoff(... ABANDON_ERROR, wait_abandon_timeout)`；timeout branch 不调用 resolve |
| claim/backoff 真源 | timeout branches 复用唯一 `_release_with_backoff`；该 helper 调用 `_backoff_delay_seconds` 并经 `release_wait_record_poll_claim` durable projection / PASS |
| authoritative terminal preservation | `ResolveWaitLostOutcome` typed branch、explicit lifecycle terminal path 与相应 owner tests anchors 均保留 / PASS |
| private smoke diagnostics | `_WaitPollerDiagnosticsHost`、`runner_dropped_count`、`observation_diagnostics_snapshot`、`._wait_poller`、`cast(...)` 在 current public smoke 零匹配，`rg` exit `1` / PASS |
| duplicate durable projection | `_durable_options_from_public_options`、`_durable_options_from_command_options` 对 `dayu tests utils` 零匹配；current smoke 的 `def _durable_options(...)` 零匹配 / PASS |
| shared durable projection owner | `HostDurableStoreOptionsSource` 与 `project_host_durable_store_options` 唯一定义于 `dayu/host/durable/options.py`；command/open-host/admin test/current smoke consumers 共用该 projection / PASS |
| R04 composition/config owner | 三个 Fins provider mode 仍由 `tool_discovery.json` 显式配置，完整 Host policy 仍由 `host_runtime.json` 提供；旧 scene/name helper与无参 `WaitPollerRuntimePolicy()` 零匹配 / PASS |
| deferred/security added-lines | production added lines 对 `authorization`、`permission`、`callback transport`、`process isolation`、`process_backed`、`subprocess`、`Issue 175` 零匹配，pipeline exit `1` / PASS |
| staged paths | 创建前 `0`；创建后见 §6 |

Retained safety anchors 仍存在：late-publication token invalidation、shared close deadline、active/expired claim、typed LOST、explicit abandon terminal 的 owner tests 均未被删除；filesystem/durable storage containment、capacity、CAS 与 close-drain 没有本 gate diff。

## 6. 创建后 worktree 与唯一写入证明

创建后复核结果如下：

| evidence | 创建前 | 创建后 | verdict |
|---|---|---|---|
| 16-path binary diff digest | `41bd8c057cb5ff3d389f909a367a19037a65ae59ffda377cd317b9d1db4eda9a` | `41bd8c057cb5ff3d389f909a367a19037a65ae59ffda377cd317b9d1db4eda9a` | identical / PASS |
| 16-path path-set digest | `ff3b00d67510c45396305a723a939b8006e9e740e61c8ff23ea6fb86e8389f4f` | `ff3b00d67510c45396305a723a939b8006e9e740e61c8ff23ea6fb86e8389f4f` | identical / PASS |
| 排除本 artifact 的 status digest | `2976dd50b45e1e5fe56243dbf576fe37b6e33bcb21181fc9b5f836d0b6cb2e62` | `2976dd50b45e1e5fe56243dbf576fe37b6e33bcb21181fc9b5f836d0b6cb2e62` | identical / PASS |
| 既有 dirty-path manifest digest | `aaa13ec90e290326b0dd98eb04cb98f0708b6fa141d15a810d1f56852254df39` | `aaa13ec90e290326b0dd98eb04cb98f0708b6fa141d15a810d1f56852254df39` | identical / PASS |
| staged path count | `0` | `0` | identical / PASS |

创建后 `git status --porcelain=v1 --untracked-files=all` 精确为 `5` 条：

```text
 M docs/host/issues-implementation-control.md
?? docs/reviews/wu-semantic-ownership-01-r05-aggregate-deepreview-controller-adjudication.md
?? docs/reviews/wu-semantic-ownership-01-r05-aggregate-deepreview-ds.md
?? docs/reviews/wu-semantic-ownership-01-r05-aggregate-deepreview-fix-codex.md
?? docs/reviews/wu-semantic-ownership-01-r05-aggregate-deepreview-mimo.md
```

创建后 full canonical status digest 为：

```text
6a6bec9f7844d256be936b46bccf1ab10e15ff93463aae0d3547f90fffc7cc28
```

相对创建前唯一新增状态行是：

```text
?? docs/reviews/wu-semantic-ownership-01-r05-aggregate-deepreview-fix-codex.md
```

排除该行后，status count 恢复为 `4`，digest 精确恢复为创建前的 `2976dd50...cb2e62`。四个既有 dirty path 的逐文件 hash 与有序 manifest digest 逐项不变；product、test、design、README、control、两路 review 与 Controller adjudication 均未被本 gate修改。

创建后普通 `git diff --check` exit `0`、无输出。由于该命令不检查 untracked file，另执行：

```bash
git diff --no-index --check /dev/null \
  docs/reviews/wu-semantic-ownership-01-r05-aggregate-deepreview-fix-codex.md
```

命令 exit `1` 只表示新文件相对 `/dev/null` 存在内容差异，且没有 whitespace diagnostic；本 artifact whitespace check PASS。

结论：创建前后受保护 transaction、path set、既有 dirty contents 与 staged state 均未变化；唯一写入是本 zero-change artifact。

## 7. 既有 Controller validation evidence（仅引用，未重跑）

本 gate没有重跑 product tests、coverage、pyright、Ruff 或 public smoke，也不声称这些验证是本 gate 新取得的结果。以下只引用 `docs/reviews/wu-semantic-ownership-01-r05-aggregate-validation.md` 的 Controller evidence：

| Gate | Controller aggregate validation 已通过结果 |
|---|---|
| R05 ten-file functional aggregate | `360 passed`，另有 3 个第三方 edgar deprecation warnings |
| fresh public awaiting smoke | PASS，11 phases 完成 |
| durable projection owner + public admin focused | `11 passed` |
| R05 S1 changed-owner coverage | `1839 passed, 2 skipped, 5 deselected`；`state.py 83%`、`wait_adapter.py 86%`；逐文件 `--fail-under=80` PASS |
| R05 S2 changed-production coverage | `1840 passed, 1 skipped, 5 deselected`；`command.py 88%`、`open_host.py 85%`、`durable/options.py 100%`；逐文件 `--fail-under=80` PASS |
| full pyright | `0 errors, 0 warnings, 0 informations` |
| changed Python Ruff | `All checks passed!` |
| full Ruff registry | fixed base `167` → accepted S1 `165` → aggregate `162`，精确只删除五条 touched-file F401 |
| scheduler deterministic residual probe | `1 passed`，仍以预期 `HostApiError` 作为 residual 直接证据 |

README decision：本 gate不更新 README。唯一变更是 review artifact，不改变产品、测试 contract、用户入口、工作流、分层或装配；任务 closed allowlist 也禁止 README 修改。

## 8. Residual risks、owner 与 mandatory follow-up

| residual | owner / destination | 当前 disposition |
|---|---|---|
| scheduler close / terminal promotion coordination | Host scheduler/lifecycle coordination owner；需要后续独立显式 work item，umbrella final closeout 必须保留明确入口 | `RETAINED / UNFIXED / UNWAIVED`；不属于 R05 blocker，不归 Issue 175；`dispatch.py`、`engine_ingest.py` 与 scheduler owner tests 本 gate no diff |
| cancelled abandon 在 provider 永不提供 terminal evidence 时长期 capped retry | future Host durable evidence policy owner；后续显式 contract/design work | `RETAINED / UNFIXED / UNWAIVED`；缺少 authoritative durable evidence 时不得以 retry count、timestamp fallback 或 timeout 猜 LOST |

Scheduler residual 的后续修复必须加入 **scheduler close + terminal promotion + poll timeout/late result** 的组合验证；该 mandatory verification 归 scheduler lifecycle owner，不得在本 R05 zero-change gate 用测试 shim 预先固化错误 oracle。

其它 deferred boundary 保持不变：Issue 175 process isolation 继续由既有 issue 拥有；callback transport、统一 authorization/permission 与 R06+ 继续由 later work owner 拥有。没有 unclassified residual risk 或 blocking open question。

## 9. 下一 gate 与 stop status

本 zero-change record 完成后，下一步只能是 **Controller validation**。Controller 必须复核 16-path digest、创建前后 status/content proof、finding ledger、source/security/no-diff scans、retained safety 与两个 residual 的未修/未 waive 状态。

只有 Controller validation PASS 后，才进入 AgentMiMo / AgentDS 双路 **full aggregate re-review**。本 gate明确不进入 re-review；reviewer verdict 也不独立授权 R05 aggregate accepted local commit、R05 completion、R06、push 或 PR。

当前停止于 `WAITING_FOR_CONTROLLER_VALIDATION`。

Artifact path：`docs/reviews/wu-semantic-ownership-01-r05-aggregate-deepreview-fix-codex.md`
