# WU-SEMANTIC-OWNERSHIP-01 R05-S2 Code Review Fix（AgentCodex）

日期：2026-07-16
Gate：R05-S2 accepted code-review findings fix
Controller adjudication：`docs/reviews/wu-semantic-ownership-01-r05-s2-code-review-controller-adjudication.md`
工作区 HEAD：`e077c70878bc47a2f1724d30f3ef22b8eb88e56f`

## 1. 结论

Controller 接受的三项 current findings 均已修复，当前状态为
`FIX_COMPLETE_WAITING_CONTROLLER_VALIDATION_AND_DUAL_COMPLETE_RE_REVIEW`。

本 gate 没有修改 Engine production behavior、R05-S1 状态机 owner、scheduler
owner、durable schema、Host public diagnostics API、Controller-owned control/review
artifacts，也没有 stage、commit 或 push。

Artifact path：
`docs/reviews/wu-semantic-ownership-01-r05-s2-code-review-fix-codex.md`。

## 2. 第一性原理与 owner 判定

三项 finding 的动机均成立：

1. `OpenHostOptions` / `HostCommandHandleOptions` 到
   `HostDurableStoreOptions` 的映射决定 Host durable connection 使用的 DB、artifact、
   payload inline threshold 与 SQLite retry policy。该 construction 事实只能由
   `dayu.host.durable.options` 拥有；smoke 或 `command.py` 各自构造嵌套 policy 都会形成
   第二真源。
2. observation runner 的 `dropped_count` 是 S1 owner-level 内部诊断，不是 Host public
   business fact。S2 public smoke 只需证明迟到 Ready 不能改变 public Run/outbox 与
   durable Wait truth；为此暴露或穿透 `_HostHandle._wait_poller` 会把内部字段错误升级为
   public contract。
3. fake adapter 的阻塞只用于制造确定性 observation 顺序。若 gate 永不发布，fake
   自己必须有限失败并说明缺失 phase；Host close/drain 不能替 fake 拥有该失败边界。

没有采用以下路径：没有把下划线 private helper 公开，没有兼容 wrapper/facade，没有让
`dayu.runtime` 反向依赖 Host，没有新增 Host diagnostics API，没有修改 runner token/fence，
也没有为单次 smoke 创建新的 scheduler/backoff policy。

## 3. Finding ledger

| Finding | 最终状态 | 修复证据 |
|---|---|---|
| MiMo-001 / DS-02：durable construction projection 重复真源 | 已修复 | `dayu.host.durable.options.project_host_durable_store_options(...)` 成为唯一 typed projection；command、open-host factories、admin seed 与当前 smoke 共用；旧 private helper和 smoke `_durable_options()` 删除。 |
| MiMo-002 / DS-01：smoke 穿透 `_wait_poller` / runner diagnostics | 已修复 | 删除局部 Protocol、`cast`、`_wait_poller` 与 `dropped_count`；第二轮 observation 进入后阻塞，在其尚未返回时读取 public Run/outbox 与 durable Wait active claim，证明首轮迟到 Ready 没有发布权。 |
| DS-05：首轮 fake `operation_finished.wait()` 无界 | 已修复 | `_wait_for_poll_adapter_gate(...)` 对 operation finish、late-result release 与 second-observation release 全部使用具名 `_TEST_OVERALL_DEADLINE_SECONDS` 有限预算；超时错误包含 gate 名与 timeout 秒数；`abort()` 继续释放全部 gate。 |

Controller 明确 no-fix 的单文件拆分、backoff cap relation、Engine fake thread 化与理论慢
CI margin 均未实施。

## 4. 实现范围

### 4.1 Production construction owner

- `dayu/host/durable/options.py`
  - 新增最小只读 typed source protocol
    `HostDurableStoreOptionsSource`，只表达 durable projection 所需九个字段；使用 Protocol
    的理由是 command/open/admin options 均为 frozen typed dataclass，durable 下层不能反向
    import 或依赖任一更宽 opener 具体类型。
  - 新增 `project_host_durable_store_options(...)`，唯一构造
    `PayloadStoragePolicy`、`HostSQLiteStoragePolicy` 与
    `HostDurableStoreOptions`。
- `dayu/host/command.py`
  - `create_host_command_handle(...)` 改用 owner helper。
  - 删除 `_durable_options_from_public_options(...)`，不保留兼容 wrapper。
- `dayu/host/open_host.py`
  - 删除对 `command.py` private helper 的跨模块 import。
  - wait poller、execution actor、admin actor 与 scheduler store 四个 construction path 直接
    共用 durable owner helper。

这只是 construction projection ownership 迁移；实际字段值、validation、store 数量、
connection ownership 与 open/close 顺序均未改变。

### 4.2 Direct owner tests

- 新增 `tests/host/test_durable_options.py`：逐字段断言唯一 projection 的 DB、artifact、
  create policy、payload threshold 与五个 SQLite policy 字段；同时覆盖所有 durable
  option validation failure branches。
- `tests/host/test_public_host_admin.py`：admin durable seed 改用同一 helper。
- 两个新触及文件内三条既有未使用 import 同步删除，使 changed-file Ruff 为零；不改变
  业务行为。

### 4.3 Public smoke evidence

- `utils/smoke_host_public_awaiting_entrypoint.py`
  - durable read 使用 production owner helper，删除重复 `_durable_options()`。
  - `_SmokeStateSnapshot` 只保留 public Run、durable Wait 与 terminal outbox；删除
    `_WaitPollerDiagnosticsHost`、`cast`、private `_wait_poller` 与
    `runner_dropped_count`。
  - 新增 `second_observation_release` gate。首轮迟到 Ready 返回后，真实 backoff 到期的
    第二轮 observation 先提交 active claim、发布 entered event，然后在返回 Ready 前阻塞。
    主流程此时断言：public Run=`WAITING`、durable Wait=`WAITING`、第二轮 claim 四字段均
    active、上一轮 diagnostic 仍为 `ADAPTER_ERROR/wait_observation_timeout`、backoff attempt
    仍为 1、terminal outbox 为空。因为首轮已经返回而第二轮尚未返回，该边界直接证明首轮
    result 没有 durable publication authority。
  - 断言完成后才释放第二轮 Ready，最终仍经 public terminal/outbox 收为 `SUCCEEDED`。
  - 三个 adapter gate 均有限等待；失败路径与 `finally -> abort()` cleanup 保留。

## 5. 验证

所有 Python 命令均在 `source .venv/bin/activate` 后运行。

### 5.1 Fresh public smoke（连续两次）

```text
python utils/smoke_host_public_awaiting_entrypoint.py \
  --workspace-root workspace/tmp/r05-s2-fix-smoke-3
PASS

python utils/smoke_host_public_awaiting_entrypoint.py \
  --workspace-root workspace/tmp/r05-s2-fix-smoke-4
PASS
```

上述两次在同一 shell 中以两个 fresh workspace 连续执行；此前
`r05-s2-fix-smoke-1` 与 `r05-s2-fix-smoke-2` 也分别通过。四次均打印并断言：

- typed provider modes=`poll/manual/callback`；
- packaged 12-field policy 精确快照；
- handshake elapsed 小于 `0.05s`，operation 约 `0.301s`；
- 首轮 timeout 后 Run/Wait=`WAITING`、claim release、
  `ADAPTER_ERROR/wait_observation_timeout`、outbox=0；
- `LATE_READY_REJECTED second_observation_blocked=true
  second_claim_active=true run=WAITING wait=WAITING terminal_outbox=0`；
- 释放第二轮后 final=`SUCCEEDED`、terminal event/outbox exact match、worker accept=2、
  poll observation=2，11 个 phase 全部完成。

### 5.2 Functional matrices

| Matrix | Result |
|---|---|
| durable owner + public admin focused | `11 passed` |
| Engine full `tests/engine/test_agent_phase3_tool_call.py` | `48 passed` |
| R04 config/Fins/Service exact owner matrix | `35 passed, 3 third-party deprecation warnings` |
| R05 ten-file aggregate functional matrix | `360 passed, 3 third-party deprecation warnings` |
| scheduler retained deterministic probe | `1 passed`（仍以预期 owner failure 为可复现证据，未修复） |

warnings 仍来自 `.venv` 的 edgar deprecation，不在当前 source/propagation path。

### 5.3 Coverage

新 production helper 直接 owner coverage：

```text
python -m pytest -q tests/host/test_durable_options.py \
  --cov=dayu.host.durable.options --cov-branch ...
9 passed
dayu/host/durable/options.py: 100%（73 statements, 8 branches）
```

Host S1 owner coverage contract 完整重跑，仍只保留 accepted 两个 ignore：

```text
1839 passed, 2 skipped, 5 deselected
dayu/host/durable/state.py: 83%
dayu/host/wait_adapter.py: 86%
两个逐文件 --fail-under=80：PASS
```

### 5.4 Type、lint 与 diff

- full pyright：`0 errors, 0 warnings, 0 informations`。
- 所有当前 changed Python paths 的 Ruff：`All checks passed!`。
- full Ruff machine-readable registry：pre-fix
  `workspace/tmp/r05-s2-ruff-current.json` 为 165，fix 后为 162；`jq` 精确比较结果
  `true`，即 fix 后 registry 等于 pre-fix registry 精确删除以下三条 touched-file F401：
  - `dayu/host/command.py` unused `AttemptStatus`；
  - `dayu/host/command.py` unused `read_run_by_id`；
  - `tests/host/test_public_host_admin.py` unused `create_host_command_handle`。
- `git diff --check`：PASS。

### 5.5 Source、propagation、no-diff、security 与 deferred scans

- `_durable_options_from_public_options`、`_durable_options_from_command_options` 在
  `dayu/tests/utils` 零命中；当前 smoke `def _durable_options(...)` 零命中。
- current smoke 的 `_WaitPollerDiagnosticsHost`、`cast(...)`、`._wait_poller`、
  `runner_dropped_count`、`observation_diagnostics_snapshot` 零命中。
- current smoke 的裸 `operation_finished.wait()` / `late_result_release.wait()` /
  `second_observation_release.wait()` 零命中；唯一等待点为带
  `_TEST_OVERALL_DEADLINE_SECONDS` 的 helper。
- current smoke 的 `hasattr/getattr`、`.resolve_wait(...)` shortcut 与
  `poll_next_observe_at` mutation 零命中。
- `dayu/engine/agent.py` 与 `dayu/engine/README.md` 相对 accepted S1 no diff。
- R05-S1 state/wait adapter/runner/waiting/schema/design 与四个 owner test paths 相对
  accepted S1 no diff；timeout-only terminal primitive 仍零定义、零调用。
- scheduler `dispatch.py` / `engine_ingest.py` / owner test no diff，deterministic residual
  仍可复现。
- fix production added lines 对 authorization、permission、callback transport、process
  isolation、process-backed/subprocess、Issue 175 零命中。
- R04 三个 provider mode 仍显式为 `poll`，Host runtime policy 仍由 config 拥有完整
  12 fields；旧 scene/name heuristic 与无参 policy construction 零命中。

## 6. README decision

- `tests/README.md`：需要更新且已更新。记录 durable construction projection owner test，
  并把 public smoke 的 late-result 证据改为第二轮 observation 阻塞边界上的 public
  Run/outbox + durable Wait/claim facts。
- `dayu/host/README.md`：已完整读取更新约束；S2 原有 Waiting contract 文本继续准确，
  当前 helper 只是内部 construction ownership relocation，不新增稳定 public contract，
  因此本 fix 不再机械扩写。
- `dayu/engine/README.md`：Engine production no diff，既有 handshake timeout 边界已完整，
  no diff。
- 根 `README.md`、`dayu/README.md`：无用户入口、工作流、分层或装配 contract 变化，
  no diff。

## 7. Residual risks 与 uncovered areas

| Residual / uncovered area | 分类与 owner |
|---|---|
| scheduler close / terminal promotion coordination | `requiring new issue or explicit user decision`；沿用 Controller 保留项，本 gate 未改 scheduler、未创建 issue、未称为已修复或 Issue 175 子项。 |
| cancelled wait abandon observation 持续 timeout 时按 capped backoff 长期重试 | `assigned to later work unit`；future Host durable evidence policy 拥有终止 evidence/schema/contract。 |
| Issue 175 process isolation / process-backed containment | `tracked by existing issue`；未实施，物理终止也不自动成为 Host durable terminal fact。 |
| callback transport、统一 authorization/permission、R06+ | `assigned to later work unit`；本 gate source/security scan 确认未进入。 |

没有 unclassified residual risk、blocking open question 或 deferred current finding。

## 8. Gate handoff

本 fix 只完成 AgentCodex accepted-findings fix gate。下一入口是 Controller 独立验证，
随后 AgentMiMo / AgentDS 双路完整 re-review。R05-S2 accepted local commit、R05 aggregate、
scheduler fix、Issue 175、callback、统一 authorization、R06-R12、push 与 PR 均未授权。
