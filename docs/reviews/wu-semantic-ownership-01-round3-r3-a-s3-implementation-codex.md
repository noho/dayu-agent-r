# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-A S3 Implementation（AgentCodex）

## 状态

`ready-for-code-review`

本 gate 只实施 S3。未修改 S2 actor（`dayu/host/_durable_actor.py`）、Service、CLI、总控文档，也未实施 S4 recovery batching 或 S5 watchdog/cancel classification。

Controller 复验后窄扩展测试范围，仅授权修改 `tests/host/test_public_contracts.py`，把该文件的 public enum 精确集合与本 slice 新增的 `HostApiErrorCode.UNAVAILABLE` 对齐。该扩展未修改生产代码、未添加兼容 shim，也未扩张其它测试或 lifecycle 语义。

## 第一性原理与 owner 判定

DR-009 的动机成立，直接证据不是间接 timing 迹象：旧 `HostDispatchScheduler._drain_loop()` 在一次 `HostTransactionRetryExhaustedError` 后清空/terminalize pending queue、写 `_closed=True`、取消 active workers；与此同时 public handle 的 close truth 不变，且 promotion wake 对 closed scheduler 静默返回。结果是 durable admission 仍可接受新 work，但 scheduler 已自行退出，形成 accepted-without-execution/wake 的分裂 lifecycle truth。

S3 的唯一 owner 判定如下：

- execution lifecycle health 与 new-work admission 排序：新 `HostExecutionHealthGate`；public handle 与 scheduler 不再各自用无关 bool 推断健康。
- actor transaction/commit/wake 的完成事实：S2 `DurableActor` future；lease 绑定底层 future，而不是 caller awaiter，因此 caller cancellation 不伪造 operation 已结束。
- durable retry exhaustion：scheduler reconciliation loop；它是 transient storage contention，不是 fatal lifecycle 事实。
- admission replay wake：`HostAdmissionService` transaction 返回的最新 Run/current Attempt/dispatch snapshot；`idempotent_replay` bool 不是 wake 真源。
- scheduler critical task fatal：统一 supervisor 到同一 `report_fatal(component, reason_code)`；原始异常只留内部日志，不进入 public typed detail。

没有理由修改 actor callable/connection owner；S2 boundary 足以承载 admission lease 与 loop bridge，因此未触发 blocking stop condition。

## 实际变更与文件范围

### Production

- `dayu/host/_execution_health.py`（新增）
  - 定义 `STARTING / READY / UNAVAILABLE / CLOSING / CLOSED` 单向 lifecycle state。
  - admission lease 串行化 READY check、actor submission/future 与 fatal transition。
  - `release_when_done()` 让 caller cancellation 后底层 commit/rollback、after-commit wake 完成才释放 lease。
  - closed/unavailable scheduler wake 生成 retryable typed unavailable；CLOSING 只允许 close gate 前已提交 actor command 完成 matching wake，scheduler 私有 close 后强制拒绝。
- `dayu/host/api.py`
  - 新增 `HostApiErrorCode.UNAVAILABLE`。
  - 新增 frozen/slots `HostUnavailableDetail(component, reason_code)`，加入受限 `HostApiErrorDetail` union。
- `dayu/host/open_host.py`
  - opener 在 scheduler/actor/recovery/poller assembly 前创建 STARTING gate，全部 startup 成功后才 `mark_ready()`。
  - `submit_followup`、`retry_run`、`replay_run` 经 admission lease 提交 actor；read/cancel/close 不被 UNAVAILABLE admission gate 阻断。
  - close 以 shared gate 提交 CLOSING，等待 active admission future/wake 后保持 S2 的 scheduler -> projection -> actor handle -> executor -> scheduler store 顺序，最终提交 CLOSED。
- `dayu/host/dispatch.py`
  - scheduler 接收同一个 health gate；heartbeat/drain/promotion/watchdog task 由统一 critical supervisor 包裹。
  - 非 retry critical exit 报告稳定 typed fatal；原始异常文本不进入 public detail。
  - drain retry exhaustion 改为按 `dispatch_poll_interval_seconds` 退避并继续 reconcile；不 self-close、不 terminalize pending queue、不取消 worker、不报告 fatal。
  - dispatch/promotion/watchdog wake 在 closed/unavailable 时抛 typed unavailable，不再静默 return。
  - 删除仅服务旧 retry-self-close 的 pending queue terminal closeout helper。
- `dayu/host/admission.py`
  - idempotent run replay 在同一 transaction snapshot 中派生 `RUNNING + STARTING + PENDING` matching dispatch wake。
  - `ACCEPTED` replay 继续由现有同源 helper 派生 pre-start governance wake；queued、terminal、已取消、lane/worker 已接手的 snapshot 不误 wake。
- `dayu/host/__init__.py`
  - 导出 public `HostUnavailableDetail`。

`dayu/host/command.py` 在 allowed list 中但无需修改：start/submit/retry/replay 已统一消费 `RunAdmissionResult.pending_dispatch` 并调用 admission service 的 after-commit wake；修复应落在 snapshot/wake owner，而不是 command facade 增加 replay 特例。

### Tests

- 新增 `tests/host/test_scheduler_health.py`：状态 gate、首个 fatal detail、admission-first、fatal-first、caller cancellation lease。
- `tests/host/test_open_host_runtime.py`：真实 opener + S2 actor/thread barrier 的 public admission-first 与 cancellation race，断言 matching wake 先于 fatal；fatal 后 submit typed reject，read/cancel 仍进入业务路径。
- `tests/host/test_dispatch_scheduler.py`：critical component typed mapping、retry exhaustion Event 驱动 reconcile、pending durable truth 保留、closed/unavailable wake。
- `tests/host/test_admission_multiprocess.py`：真实 SQLite snapshot 下 ACCEPTED governance replay wake、PENDING complete identity dispatch wake、cancelled replay no-wake。
- `tests/host/test_package_exports.py`：新增 public detail export contract。
- `tests/host/test_public_contracts.py`（controller 窄范围 extension）：在 `HostApiErrorCode` 精确枚举 contract 中加入 `UNAVAILABLE = "unavailable"`。

所有 race oracle 使用 `asyncio.Event`、`threading.Event`、actor FIFO/barrier 或 task completion；没有用 sleep/stress 命中概率作为 correctness oracle。生产 poll interval sleep 只属于被验证的 backoff 行为。

### Docs

- `docs/host/design.md`：补充 shared health/admission contract、retry classification、replay wake 与 public unavailable error/detail。
- `dayu/host/README.md`：同步当前已实现的 opener、admission、scheduler 与 close stable boundary。
- `tests/README.md`：同步 health/race/replay owner-level 覆盖。

## 必须反例如何满足

1. **STARTING / READY / UNAVAILABLE gate**：gate 默认 STARTING，new-work 返回 retryable unavailable；opener 全部 critical assembly 成功后才 READY；首个 fatal 提交 UNAVAILABLE 并保持首个 typed detail。
2. **critical task fatal typed mapping**：统一 supervisor 对 heartbeat/dispatch/promotion component 写固定 `critical_task_unexpected_exit`；测试注入含敏感私有文本的异常，public detail 只保留 component/reason_code。
3. **admission-first commit+wake before fatal**：真实 public `submit_followup` 在 actor barrier 后已持 lease并排队；fatal 确定等待同一 lease；释放 barrier 后真实 SQLite commit、loop bridge governance wake完成，fatal 才提交 UNAVAILABLE。顺序断言为 `wake -> fatal`。
4. **fatal-first submit 不进 actor**：owner-level fatal 完成后 acquire admission 立即 typed reject；public race 中 fatal 后新 client request 不产生 matching wake/accepted path。`get_session` 与 missing-run `cancel_run` 分别返回正常 read 与业务 NOT_FOUND，证明未被 health admission gate误拦。
5. **caller cancellation 不破坏 commit+wake/no-commit**：public caller 在 actor submission 后取消只得到 `CancelledError`；底层 future 继续，matching wake出现后 lease才释放，fatal随后提交。fatal-first 变体在 actor submission 前拒绝，对应 no-commit 分支。
6. **retry exhaustion 不自闭**：第一次 `HostTransactionRetryExhaustedError` 通过 Event 记录，下一轮 reconcile Event 确认已发生；scheduler仍打开、active cancellation token未取消、pending Run/Attempt/dispatch仍为 RUNNING/STARTING/PENDING，close前无 terminal rewrite。
7. **closed/unavailable wake typed internal unavailable**：dispatch、promotion、watchdog 三个 wake 都返回 `HostApiErrorCode.UNAVAILABLE`、`retryable=True`；不再静默返回或裸 `RuntimeError`。
8. **idempotent replay matching wake**：真实 durable snapshot 验证 ACCEPTED replay恰好一次 promotion wake，PENDING replay恰好一次且 run/attempt/dispatch identity完整匹配，CANCELLED replay零 dispatch/promotion/watchdog wake。

## 验证结果

### Required focused pytest

命令：

```bash
source .venv/bin/activate
pytest tests/host/test_scheduler_health.py tests/host/test_open_host_runtime.py tests/host/test_public_session_api.py tests/host/test_public_run_api.py tests/host/test_submit_followup_public_contract.py tests/host/test_public_retry_replay.py tests/host/test_command_handle.py tests/host/test_dispatch_scheduler.py tests/host/test_admission_multiprocess.py tests/host/test_package_exports.py tests/host/test_import_boundary.py -q
```

结果：`212 passed in 7.95s`。

### Controller direct affected contract

命令：

```bash
source .venv/bin/activate
pytest tests/host/test_public_contracts.py -q
```

结果：`45 passed in 0.33s`。原 `1 failed, 44 passed` 的 stale public enum assertion 已按 controller 授权迁移，没有生产兼容分支。

### Required pyright

命令：

```bash
source .venv/bin/activate
python -m pyright dayu/host/ tests/host/
```

结果：`0 errors, 0 warnings, 0 informations`。

### Required source scans

```bash
rg -n "HostExecutionHealthGate|STARTING|READY|UNAVAILABLE|CLOSING|CLOSED|report_fatal" dayu/host/_execution_health.py dayu/host/open_host.py dayu/host/dispatch.py
```

分类：状态定义/transition 只在 `_execution_health.py`；`open_host.py` 只创建、READY/close消费；`dispatch.py` 只消费 gate 并调用唯一 `report_fatal`。

```bash
rg -n "idempotent_replay|wake_dispatch|wake_queue_promotion|HostTransactionRetryExhaustedError" dayu/host/admission.py dayu/host/command.py dayu/host/dispatch.py
```

分类：S3 admission replay wake 来自 `_idempotent_replay_pending_dispatch()` 与既有 `_wake_start_governance_if_needed()`；drain retry exhausted 只进入 warning + poll interval backoff。`command.py:802/886` 的 `not idempotent_replay` 属于 `resolve_wait` / callback wait resume，不是 S3 start/submit/retry/replay admission，未跨入 S6 修改。

```bash
rg -n "if .*_closed.*return|Queue\(maxsize=1\)" dayu/host/dispatch.py dayu/host/open_host.py
```

结果仅命中 `dayu/host/dispatch.py` 的 active-cancel watchdog `Queue(maxsize=1)`；这是计划明确留给 S5 的 level-triggered wake owner。本 scan 未命中 closed scheduler wake 静默 return；admin handle 的独立 `_closed` 不在 execution health owner范围。

```bash
git diff --check
```

结果：通过，无输出。

## README / design 触发判断

- `dayu/host/` lifecycle、public error 与 scheduler/admission stable boundary 发生变化，命中 `dayu/host/README.md` 更新触发，已更新。
- 新增 Host owner-level test 层级与 race oracle，命中 `tests/README.md` 更新触发，已更新。
- S3 是 accepted Host design contract 的落地，`docs/host/design.md` 已同步当前实现。
- 分层方向、Service assembly、CLI 参数/输出、最终用户工作流均未变化，且 `dayu/README.md`、Service、CLI 不在 S3 allowed list，因此不更新根 README 或 `dayu/README.md`。

## Residual risk / scope note

- S5-owned active-cancel watchdog 仍使用 `asyncio.Queue(maxsize=1)`；本 slice 只让其 closed/unavailable wake typed fail，不提前实施 level-triggered Event。
- `resolve_wait` / callback wait resume 仍有自己的 idempotent replay wake suppression；它们不是本 slice 冻结的 new-work admission 集合，按计划留在 wait owner slice审查。
- required matrix、controller 直接受影响 contract 与 full `dayu/host/ tests/host/` pyright 已通过；未运行全仓 pytest。此前 `tests/host/test_public_contracts.py` 的 stale enum residual 已由本次 controller scope extension 关闭，不再是 residual。

以上 residual 均不构成 S3 stop condition。admin 未启动 execution side effect、connection 未跨线程、race oracle 可确定推进、scheduler close 未越过 admitted actor wake，状态为 `ready-for-code-review`。
