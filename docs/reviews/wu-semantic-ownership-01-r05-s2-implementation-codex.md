# WU-SEMANTIC-OWNERSHIP-01 R05-S2 Implementation Evidence（AgentCodex）

日期：2026-07-15
Slice：R05-S2 implementation gate
S1 accepted commit：`c5af5613b21673864fff072a132ac56a46cc9836`
Transition HEAD：`e077c708`

## 1. 结论

R05-S2 implementation 已完成，当前应停回 Controller validation / code review；未 stage、未 commit、未 push，也未修改 control doc。

本 slice 没有创建第二个 production transaction。`dayu/engine/agent.py` 在 fixed plan base、S1 accepted commit 与 transition HEAD 上均保持 no diff。新增 Engine regression 在现有 production 上直接通过；真实本地 smoke 通过 packaged `ConfigLoader -> provider discovery -> Service composition -> open_host -> durable poller -> public terminal/outbox` 主链，证明 accepted awaiting 后的独立 operation 可以越过 Engine 握手预算，同时 Host observation timeout 仍只产生 retry diagnostic，迟到 Ready 无 durable authority，真实 backoff due 后第二轮 Ready 才恢复 Run。

计划 §13 stop condition 均未触发。

## 2. 动机与 semantic owner 判断

问题动机成立，但它是跨层 contract evidence 缺口，不是第二个 production root cause：

- Engine 只拥有 `ToolExecutor.execute` 返回前的握手预算。当前 `agent.py` 只在构造 `BatchToolExecutionContext` 和 `_execute_batch` 的 `await_or_cancel_or_timeout(...)` 中读取 `tool_execution_timeout_seconds`；收到 accepted `ToolAwaitingOutcome` 后只投影 `TOOL_AWAITING` / `RUN_SUSPENDED`，没有再次读取该预算。
- 独立外部 operation、durable wait、observation、claim/backoff、late-publication fencing 与 resume 属于 Host / ToolRuntime owner。R05-S1 已在 `dayu/host/wait_adapter.py` 与 `dayu/host/durable/state.py` 修复并接受；S2 没有重写或补偿 S1。
- 因此正确路径是新增 Engine no-diff regression，并用 public smoke 证明跨层组合语义；修改 `agent.py`、新增 timer、在 adapter 下游补 fallback 或私有 direct-resolve 都会落错 owner。

直接 source evidence：

- `agent.py:1974` 把预算投影进 batch context；
- `agent.py:2180-2184` 只用该预算包裹 executor handshake；
- `agent.py:2017` 接受 `ToolAwaitingOutcome`，随后 suspended path 不再读取 timeout；
- fixed base 与 accepted S1 上的 `git diff --exit-code ... -- dayu/engine/agent.py` 均为 exit 0。

## 3. 修改路径

本 slice 只修改 closed allowlist 内五条路径：

1. `tests/engine/test_agent_phase3_tool_call.py`
   - 新增 accepted-awaiting 独立 operation fake executor；
   - 新增 `test_accepted_awaiting_external_operation_outlives_handshake_timeout`；
   - 断言握手在预算内返回、operation 实测越过预算且未被取消、终态为 `RUN_SUSPENDED`、事件为 `TOOL_AWAITING -> RUN_SUSPENDED`、没有 `RUN_FAILED`。
2. `utils/smoke_host_public_awaiting_entrypoint.py`
   - 保留 packaged composition 主链与 typed provider mode matrix；
   - 精确断言 packaged policy 十二字段；
   - 从 packaged policy 只用 `dataclasses.replace(...)` 派生 test-effective timing；
   - 增加独立 operation、首轮 timeout/迟到 Ready、第二轮 Ready provider driver；
   - 增加 public Run/outbox、durable Wait 和只读 observation diagnostics 的 condition-driven phase ledger；
   - 增加单一 monotonic overall deadline 与完整失败诊断；
   - 不调用私有 resolve，不篡改 `poll_next_observe_at`，不使用 fixed business sleep 推断状态。
3. `dayu/host/README.md`
   - 按现有 Waiting 章节职责补充当前实现：同步 observation timeout 是 poll-local diagnostic；poll wait 保持 `WAITING`，cancelled abandon 保持 `CANCELLED` 且不写 `poll_abandoned_at`；迟到结果没有发布权；只有 authoritative typed outcome 才可写对应 durable 语义。
4. `tests/README.md`
   - 纠正旧的 stuck-poll→LOST / abandon-timeout-marker 测试描述；
   - 登记 Engine accepted-awaiting regression 与 public awaiting entrypoint smoke 的当前覆盖边界。
5. `docs/reviews/wu-semantic-ownership-01-r05-s2-implementation-codex.md`
   - 本 implementation evidence。

只读且 no-diff：`dayu/engine/agent.py`、`dayu/engine/README.md`、S1 七条 protected product/test/design 路径、`docs/host/issues-implementation-control.md`、scheduler owner、根 README 与 `dayu/README.md`。

## 4. Test-first 与 no-production-diff evidence

先只修改 Engine test，再运行新节点：

```text
python -m pytest -q \
  tests/engine/test_agent_phase3_tool_call.py::test_accepted_awaiting_external_operation_outlives_handshake_timeout

1 passed in 0.47s
```

该节点在当前 production 上首次即绿，符合 S2 的 no-production-diff 设计：若失败才说明 `agent.py` 仍错误拥有 accepted operation 的 timeout，按计划必须立即停回 Controller，而不是修改 production。测试运行前后 `dayu/engine/agent.py` 均无 diff。

测试使用 `0.1s` Engine 握手预算和 `0.25s` 独立 operation；断言 executor context 收到同一命名预算、握手返回小于预算、operation 实测大于预算、operation 未被 timer 取消，并精确投影 suspended 事件。

## 5. Public smoke contract 与 evidence

### 5.1 Timing constants

```text
handshake_budget              = 0.05s
adapter_observation_timeout   = 0.15s
external_operation_target    = 0.30s
initial_backoff              = 0.60s
state_poll_quantum           = 0.005s
relative_margin              = 0.03s
overall_deadline             = 15.0s
CI_duration_cap              = 20.0s
poller_interval              = 0.01s
close_drain                  = 1.0s
```

脚本在打开 Host 前断言，并在运行中用实测 operation 时长复核四条关系：

```text
handshake_budget + margin < observation_timeout
observation_timeout + margin < measured_operation_duration
measured_operation_duration + margin < observation_timeout + initial_backoff
margin >= 5 * state_poll_quantum
```

### 5.2 Packaged 与 test-effective policy

packaged 十二字段精确快照：

```text
enabled=True
poll=1.0
claim_ttl=60.0
claim_batch=100
backoff_initial=30.0
backoff_multiplier=2.0
backoff_max=300.0
not_ready=1.0
idle=5.0
adapter_timeout=30.0
close_drain=5.0
max_outstanding=8
```

test-effective policy 只从上述 packaged typed policy 通过 `replace(...)` 改写测试 timing；没有无参 `WaitPollerRuntimePolicy()`、产品 config 改动或第二套 backoff 算法。

### 5.3 Condition-driven phases

唯一 phase ledger 按下列顺序全部完成：

```text
run_accepted
operation_started
handshake_accepted
durable_waiting
first_observation_entered
first_observation_timeout_released
operation_finished
late_result_released
late_publication_dropped
second_observation_entered
public_terminal_outbox
```

phase 由 `asyncio.Event`、`threading.Event`、public/durable state predicate 或 public terminal task 驱动。唯一 `asyncio.sleep(0.30)` 是被测外部 operation 自身行为；state loop 的 `0.005s` 只让出调度，每次都重新读取 owner state，不以 sleep 推断业务事实。所有 phase wait 共用一个 monotonic deadline 的 remaining budget。

deadline 失败 helper 会输出 completed/pending phase、monotonic elapsed、Run/Wait status、四个 claim fields、`poll_next_observe_at`、backoff attempt、last outcome/error、`poll_abandoned_at`、runner dropped count 与 terminal outbox。

### 5.4 实际 smoke 输出摘要

执行过计划指定命令：

```text
python utils/smoke_host_public_awaiting_entrypoint.py \
  --workspace-root workspace/tmp/r05-host-public-awaiting-entrypoint
```

最终代码另在 fresh `workspace/tmp/r05-host-public-awaiting-entrypoint-rerun` 复跑，结果为 exit 0，关键证据：

```text
SMOKE TYPED_PROVIDER_MODES poll=poll manual=manual callback=callback
SMOKE HANDSHAKE_ACCEPTED elapsed=0.001224 budget=0.05
SMOKE OBSERVED_WAITING true
SMOKE FIRST_OBSERVATION_TIMEOUT run=WAITING wait=WAITING
  claim_released=true diagnostic=ADAPTER_ERROR/wait_observation_timeout
  terminal_outbox=0
SMOKE OPERATION_DURATION measured=0.301236 handshake_budget=0.05
SMOKE TIMING_INEQUALITIES ...=true（四项全部 true）
SMOKE LATE_READY_DROPPED runner_dropped_count=1
  run=WAITING terminal_outbox=0
SMOKE WORKER_ACCEPT_COUNT 2
SMOKE POLL_OBSERVATION_COUNT 2
SMOKE TERMINAL_STATUS SUCCEEDED
SMOKE OUTBOX_TERMINAL_MATCH true
SMOKE PASS Host public awaiting entrypoint
```

脚本还断言最终 public `RunSnapshot.status` 为 `SUCCEEDED`、terminal event id 与同 Run 唯一 terminal outbox item 精确一致。两个 smoke workspace 均保留 Host artifacts，脚本未输出 secret。

## 6. 完整验证

所有 Python 命令均在 `source .venv/bin/activate` 后执行。

### 6.1 R05-S2 Engine exact nodes 与整文件

计划 §7.2 七个 exact nodes：

```text
7 passed in 0.42s
```

Engine 整文件：

```text
python -m pytest -q tests/engine/test_agent_phase3_tool_call.py
48 passed in 0.46s
```

### 6.2 R04 ownership preservation 与 aggregate

计划 §7.3 的 11 个 exact config/Fins/Service nodes因参数化实际展开为：

```text
35 passed, 3 third-party deprecation warnings in 1.16s
```

十文件 aggregate：

```text
360 passed, 3 third-party deprecation warnings in 3.55s
```

warnings 来自 `.venv` 中 edgar deprecated import，不在本 slice source/propagation path。

### 6.3 Coverage

R05-S2 Engine coverage 精确命令通过，生成 `workspace/tmp/r05-s2-coverage.json`：

```text
48 passed in 0.58s
agent.py statements: 597 / 742 = 80.458221%
agent.py branches:   201 / 286 = 70.279720%
combined branch-aware coverage: 77.626459%（终端显示 78%）
```

计划所述 `agent.py=80%` 对应 statement coverage；branch-aware combined display 是 78%。两项在此如实保留，没有把 78% 隐藏成 80%。`agent.py` 不是 actual changed production file，且 fixed base / accepted S1 / transition HEAD 三重 no-diff，因此不存在新增 Engine production coverage debt。

按计划 §8 重新运行 S1 changed-owner coverage measurement，没有只沿用历史结果，也没有新增第三个 ignore：

```text
python -m pytest -q tests/host \
  --ignore=tests/host/test_toolruntime_executor.py \
  --ignore=tests/host/test_dispatch_scheduler.py \
  --cov=dayu.host.durable.state \
  --cov=dayu.host.wait_adapter \
  --cov-branch ...

1831 passed, 1 skipped, 5 deselected in 54.39s
dayu/host/durable/state.py = 83%
dayu/host/wait_adapter.py  = 86%
```

随后两个逐文件命令均为 exit 0：

```text
python -m coverage report --include='dayu/host/durable/state.py' --fail-under=80
python -m coverage report --include='dayu/host/wait_adapter.py' --fail-under=80
```

从 fixed plan base 计算的 actual changed production Python files仍精确为上述两个 S1 Host owners；S2 没有新增 production Python diff。

### 6.4 Pyright 与 Ruff

最终全量 pyright：

```text
python -m pyright dayu/ tests/ utils/
0 errors, 0 warnings, 0 informations
```

计划列出的八个 changed Python / protected S1 paths 单独 Ruff：

```text
All checks passed!
```

全量 Ruff exact command仍按 accepted baseline 非零：

```text
python -m ruff check dayu tests utils
Found 165 errors.
```

machine-readable registry：

```text
fixed base registry          = 167
accepted S1 residual         = 165
current S2 residual          = 165
current == accepted S1       = true
new vs fixed base            = 0
removed vs fixed base        = 2
```

两条 removal 精确为 S1 计划登记的 changed-file F401：

- `dayu/host/durable/state.py:40:5` unused `TERMINAL_RUN_STATUS_VALUES`；
- `tests/host/test_phase7_waiting_integration.py:8:22` unused `datetime.UTC`。

没有 `noqa`、ignore、Ruff config 改动、新 rule/location/fingerprint 或数量替换。

### 6.5 Diff、source、propagation 与 security

```text
git diff --check                                      PASS
S1 protected seven paths vs accepted S1              NO DIFF
dayu/engine/agent.py                                  NO DIFF
dayu/engine/README.md                                 NO DIFF
docs/host/issues-implementation-control.md            NO DIFF
dayu/host/_wait_observation.py                        NO DIFF
dayu/host/waiting.py                                  NO DIFF
dayu/host/durable/schema.py                           NO DIFF
dayu/host/dispatch.py                                 NO DIFF
dayu/host/engine_ingest.py                            NO DIFF
README.md / dayu/README.md                            NO DIFF
```

source/propagation scan 结论：

- `mark_wait_record_poll_abandon_timeout` 与 `_MarkWaitRecordAbandonTimeoutOperation` 在 `dayu tests` 零定义、零调用；
- poll / abandon timeout branches只调用既有 `_release_with_backoff(...)`，backoff 只由既有 `_backoff_delay_seconds(...)` 与 durable `release_wait_record_poll_claim(...)` owner 产生；
- `_start_observation / _invalidate_token / _publish` 仍在 `_wait_observation.py` 内以同一 token/generation/lock决定发布权；adapter/store/smoke 未创建第二套 publication fence；
- `ResolveWaitLostOutcome` 只保留在 public typed contract、authoritative `WaitPollLost`、waiting owner 与对应 tests；timeout branch不构造 lost outcome；
- R04 provider raw config仍显式拥有 `awaiting_resolution_mode`，Host runtime config仍拥有完整 `wait_poller_policy`；prompt/execution profile未取得 ownership；
- `with_entrypoint_wait_poller_policy`、`_scene_selects_fins_awaiting_tools` 与无参 `WaitPollerRuntimePolicy()` 零命中；
- 本 WU production added lines 对 `authorization|permission|callback transport|process isolation|process_backed|subprocess|Issue 175` 零命中；
- changed test/smoke 中无 `hasattr/getattr`、monkeypatch 或 `.resolve_wait(...)` shortcut。

## 7. README decision

- `dayu/host/README.md`：命中 Host README 触发，且 timeout/retry/late-publication 是 Waiting 稳定 contract，已在现有章节按当前 production 同步。
- `tests/README.md`：命中 tests 触发，已纠正旧测试语义并登记新增 regression/smoke 覆盖边界。
- `dayu/engine/README.md`：当前已明确 handshake timeout 只限制 ToolExecutor handshake，`agent.py` no diff，因此不机械修改。
- 根 `README.md`：无用户安装、CLI/Web/WeChat、输出、workspace 或排障流程变化，no diff。
- `dayu/README.md`：分层/装配边界未变化，no diff。

## 8. Security、deferred scope 与 residual risk

### 8.1 Security / safety 保留

- 没有放宽 cancellation、claim CAS、capacity、close-drain、token fencing 或 authoritative Lost tests；
- smoke 无网络、无外部 credential、无 secret output；
- callback mode仍在 authenticated transport 缺失时 pre-open fail closed；
- 没有新增 private command/direct-resolve、raw durable mutation、schema/migration、兼容 shim 或 fallback；
- durable/outbox/Run 的同一业务事实分别从 owner/public projection读取并交叉断言，没有以日志或偶然时间顺序重算 terminal 语义。

### 8.2 Scheduler residual：未修、未隐藏

既有 Host scheduler close / terminal promotion coordination root cause保持原 owner：scheduler `close()` 先提交私有 close gate，在等待 promotion task cancellation 时让出 event loop；active worker clean EOF terminal closeout同步 wake queue promotion，随后被 force health gate拒绝，异常从 active task传播回 close。

本 slice：

- 未修改 `dayu/host/dispatch.py`、`dayu/host/engine_ingest.py` 或 `tests/host/test_dispatch_scheduler.py`；
- 没有把它称为 flake、inherited pass、已修复或 Issue 175 子项；
- R05 changed-owner coverage只保留 accepted plan 的两个 ignore，没有第三个 ignore/deselect/xfail/retry/failure exemption；
- 确定性 `workspace/tmp/test_r05_scheduler_close_probe.py` 最终复核为 `1 passed in 0.30s`，说明 residual 仍可复现，没有被本 WU 隐藏。

### 8.3 Deferred owners

- cancelled wait 的 abandon observation若持续 timeout且 provider从不返回 explicit lifecycle terminal outcome，仍可能按 capped backoff长期重试；R05 只保证 claim CAS、bounded capacity、finite observation timeout、late-publication fencing 与 backoff，不发明 terminal evidence；
- 若产品需要停止上述重试，future Host durable evidence policy必须另定义 owner、evidence、终止条件、schema/contract与 owner tests；
- Issue 175 process isolation / process-backed containment不属于 R05；物理进程终止也不能自动投影成 durable terminal fact；
- authenticated callback transport、unified authorization/permission schema 与 R06+ semantic ownership remediation继续延期。

## 9. Stop status 与 handoff

逐项审计 plan §13：没有 Engine regression failure、accepted-awaiting timeout reuse、Host/Engine owner扩域、private shortcut、fixed-state sleep、timeout terminalization、R04 ownership drift、security/fence放宽、coverage gate失败、pyright新增错误、changed-file Ruff错误、full Ruff registry漂移、allowlist外 diff或 scheduler waiver。

当前状态：`IMPLEMENTATION_COMPLETE_WAITING_CONTROLLER_VALIDATION_AND_CODE_REVIEW`。
