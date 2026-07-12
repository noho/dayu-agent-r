# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-A S5 Implementation（AgentCodex）

## 状态

`ready-for-code-review`

本 gate 只实施 S5 Active-cancel Watchdog 与 Transaction-local Classification。未修改 S3 health state machine、S4 recovery cursor、wait adapter、public API、Service、CLI、Fins 或 Engine，也未扩张 cancel 支持状态、terminal taxonomy 或 physical provider cancellation。

## 第一性原理与 owner 判定

两个 S5 finding 均成立，且有直接代码证据：

- watchdog 原先持有 `asyncio.Queue(maxsize=1)`，`wake_active_cancel_watchdog()` 对 `QueueFull` 静默 `pass`；watchdog loop 又在 tick 内捕获普通异常并 `continue`，外层再次吞异常，导致 S3 critical-task supervisor无法提交 typed fatal。
- public `command.cancel_run()` 在 admission write transaction 抛 `INVALID_STATE` 后调用 `_is_deferred_cancel_state()`，另开 read transaction重读 Run/Attempt/dispatch。并发 writer可在两个 snapshot 之间改变状态，使返回错误码属于第二个 snapshot，而不是发起 cancel 的获锁 snapshot。

唯一 owner 判定：

- accepted-cancel low-latency signal、tick clear/set 和 critical loop异常传播属于 `HostDispatchScheduler`。
- supported/deferred/terminal/conflict 判定属于 admission `_CancelRunOperation` 持有的 SQLite write snapshot；command facade 只消费 owner结果并执行 commit 后 bridge，不重读 durable state。
- active worker token/hook 与 watchdog wake 的线程切换继续由 S2 opener-loop bridge 持有；S5 只验证并消费，不修改 actor/bridge。
- cancel释放 active slot 后的 promotion资格继续由 `CancelRunResult.released_active_slot` 与 `_promote_after_release()` 持有；classification不复制 promotion规则。

`dayu/host/admission.py` 的 allowed 注释强调 promotion handoff，但 accepted S5 plan同时明确要求 `_CancelRunOperation` 在同一 transaction 返回分类。该 operation 当前真实位于 admission owner，因而本次修改是关闭 finding 所必需的最窄 owner变更；没有把 operation搬到 command 层或添加兼容 wrapper。

## 实际变更与文件范围

### Production

- `dayu/host/dispatch.py`
  - 用 opener-loop owned `asyncio.Event` 替换 bounded watchdog queue。
  - wake 只执行 `event.set()`；多个 wake自然合并为 level signal，不再有 `QueueFull` 吞 wake分支。
  - loop 在每轮 tick 前 `clear()`；tick 内到达的新 wake保持 set并立即驱动下一轮，periodic timeout只保留 restart/fallback reconcile职责。
  - 删除 tick普通异常的两层吞异常逻辑；非取消异常上浮到既有 S3 `_supervise_critical_task()`，提交稳定 `active_cancel_watchdog / critical_task_unexpected_exit`。scheduler正常 close产生的 `CancelledError` 仍透传给 supervisor且不报告 fatal。
- `dayu/host/admission.py`
  - 新增内部闭集 `_CancelRunClassification`：`SUPPORTED / DEFERRED / TERMINAL / CONFLICT`，以及 immutable `_CancelRunOperationResult`。
  - `_CancelRunOperation` 在唯一 write transaction snapshot内返回闭集分类；active transition 的 `INVALID_STATE` + 同 snapshot RUNNING/CANCELLING映射为 deferred，其它未提交 mutation 的 loser映射 conflict。
  - terminal与幂等 terminal replay从同一 durable snapshot标记 terminal；supported路径携带既有 `CancelRunResult`。
  - `HostAdmissionService.cancel_run()` 在 transaction返回后只映射分类到既有 public错误 taxonomy：deferred为 `UNSUPPORTED_OPERATION`，conflict为 `INVALID_STATE`。没有新增 public错误码或 detail。
  - 只有携带成功 result 且 `released_active_slot=True` 的首次提交路径执行既有 promotion wake；deferred/conflict/terminal/idempotent replay不重复 wake。
- `dayu/host/command.py`
  - 删除 `INVALID_STATE` 后的 `_is_deferred_cancel_state()`、`_IsDeferredCancelStateOperation` 以及相关 Attempt/dispatch二次读取 helpers。
  - 保留现有 commit 后顺序：先 watchdog wake，再 active registry cancel；两者通过 S2 bridge回到 opener loop。

没有修改 `dayu/host/admission.py` 的 cancel状态集合、durable transitions或 session-scope cancel算法。

### Tests

- `tests/host/test_dispatch_scheduler.py`
  - deterministic probe在第一轮 tick 内再次 wake，断言两轮 tick前 event均已 clear，nested wake后 event为 set，且第二轮无需 periodic timeout。
  - 三次同步并发 wake合并为一次 tick，Event状态而非 sleep次数作为 oracle。
  - watchdog普通异常完成 critical supervisor task后 health进入 UNAVAILABLE，public detail只含稳定 component/reason code；正常 close cancel保持 READY，不误报 fatal。
- `tests/host/test_active_cancel_dispatch.py`
  - active cancel bridge改用真实 S2 durable actor worker thread，而不是普通 `to_thread`。
  - transaction spy对 deferred与injected conflict路径均断言一次 write、零 read、零新 EventLog fact。
  - watchdog closeout重复 tick不重复 terminal/promotion dispatch。
- `tests/host/test_open_host_runtime.py`
  - 真实 public `host.cancel_run()` 经 actor后，记录 watchdog Event.set、`_HostCancellationToken.request_cancel()`、`LocalWorkerHandle.on_cancel()` 与测试 `asyncio.Event.set()` 全部发生在 opener loop thread。
- `tests/host/test_admission_multiprocess.py`
  - duplex pipe + SQLite write lock barrier验证 Attempt在 cancel write snapshot前先进入 RUNNING时得到 supported/CANCELLING；classification完成且尚未 commit时另一个进程尝试改为 RUNNING，当前调用稳定返回旧 snapshot的 `UNSUPPORTED_OPERATION`，后续 mutation才提交。
  - 首次 direct cancel释放 slot恰好一次 promotion wake；同 key replay与terminal loser均零重复 wake。

所有 race oracle使用 `asyncio.Event`、真实 actor future、multiprocessing pipe barrier、SQLite write lock与durable row/event identity；没有用 sleep次数或概率竞争判定 correctness。

### Docs

- `docs/host/design.md`：冻结 level Event、clear-before-tick、critical fatal、single-write cancel分类和promotion wake规则。
- `dayu/host/README.md`：同步当前已实现的 cancel/watchdog稳定机制。
- `tests/README.md`：同步 S5 owner-level deterministic覆盖。

## 必须反例如何满足

1. **tick barrier 内第二次 wake**：第一轮 tick entry断言 event已 clear；tick body调用真实 `wake_active_cancel_watchdog()` 后 event立即 set，loop下一轮无需timeout即执行，第二轮 entry再次观察 clear状态。
2. **多个 wake level合并且不丢 tick期间事实**：三次并发 wake只产生一次初始 tick；nested wake产生且仅产生必要的第二轮。断言使用 Event `is_set()`、tick entry events与task completion，不用 sleep。
3. **watchdog fatal / normal close**：injected RuntimeError不再被 loop吞，S3 supervisor提交 `UNAVAILABLE` 与 `HostUnavailableDetail(component="active_cancel_watchdog", reason_code="critical_task_unexpected_exit")`，私有异常文本不泄漏。正常 scheduler close取消 watchdog task后 health保持 READY。
4. **actor到opener-loop bridge**：真实 durable actor worker thread发起 public active cancel；watchdog Event.set、token写入、worker hook和hook内 asyncio primitive访问的记录线程均等于 opener loop thread，actor worker id不同。
5. **同一 write transaction分类**：`_CancelRunOperationResult`覆盖 supported/deferred/terminal/conflict；deferred与conflict transaction spy均为 `write_calls=1 / read_calls=0`，command中 post-write reader及其依赖helpers已删除。
6. **多进程 snapshot race**：mutation先于 cancel write lock时 Attempt RUNNING并得到 CANCELLING；cancel operation持锁完成deferred分类后，另一进程只能等待，当前调用返回 UNSUPPORTED，随后 mutation提交为 RUNNING。错误码未被post-write状态改写。
7. **promotion与durable classification一致**：首次 pre-worker cancel返回 `released_active_slot=True` 并投递一次 session promotion；idempotent replay与terminal loser均 `released_active_slot=False`、无重复 wake。watchdog首次closeout促进 queued Run，第二次 tick `closed=0` 且worker创建数不增加。

## 验证结果

### Required focused pytest

命令：

```bash
source .venv/bin/activate
pytest tests/host/test_active_cancel_dispatch.py tests/host/test_dispatch_scheduler.py tests/host/test_public_cancel_session_runs.py tests/host/test_public_run_api.py tests/host/test_admission_multiprocess.py tests/host/test_open_host_runtime.py -q
```

结果：`165 passed in 6.77s`。

### Required pyright

命令：

```bash
source .venv/bin/activate
python -m pyright dayu/host/command.py dayu/host/dispatch.py dayu/host/admission.py tests/host/
```

结果：`0 errors, 0 warnings, 0 informations`。工具另提示 pyright `1.1.409 -> 1.1.411` 有新版本，不影响检查结论。

### Required source scans

命令：

```bash
rg -n "_is_deferred_cancel_state|Queue\(maxsize=1\)|except asyncio\.QueueFull" dayu/host/command.py dayu/host/dispatch.py
```

结果：零命中，`rg` exit code 1，符合删除型 scan预期。command已无 deferred post-write reader；dispatch已无 bounded watchdog queue与 QueueFull吞 wake。

命令：

```bash
rg -n "asyncio\.Event|wake_active_cancel_watchdog|_CancelRunOperation" dayu/host/command.py dayu/host/dispatch.py
```

结果分类：

- `dayu/host/dispatch.py:1002` 命中唯一 watchdog `asyncio.Event` owner。
- `dayu/host/dispatch.py:1133` 命中 scheduler wake；`dayu/host/command.py:161/1619/1624/1634` 命中 typed wake port与commit后调用链。
- `_CancelRunOperation` 不在这两个文件命中，因为 baseline及正确 owner一直是 `dayu/host/admission.py`；没有为满足 scan伪造 command compatibility symbol。

补充 owner scan：

```bash
rg -n "_CancelRunOperation|_CancelRunClassification|_CancelRunOperationResult" dayu/host/admission.py
```

结果：明确命中 classification定义、service映射、operation返回类型及 supported/deferred/terminal/conflict各分支。

命令：

```bash
git diff --check
```

结果：通过，无输出。

## README / design 触发判断

- 修改 Host cancel并发信号、transaction classification与critical-task行为，命中 `dayu/host/README.md` 更新触发；已按其 Agent约束同步当前稳定机制。
- 修改 Host deterministic tests，命中 `tests/README.md` 更新触发；已同步 owner-level coverage。
- accepted S5 design contract已落地，`docs/host/design.md` 同步 level Event与single-snapshot规则。
- public API、用户输出、Service/CLI assembly、分层关系、Fins/Engine均未改变，因此不更新根 README、`dayu/README.md` 或其它 README。

## Residual risk / scope note

- periodic watchdog scan仍保留为 restart/fallback reconcile；正确性不再依赖它补偿 bounded queue丢 wake。该行为属于当前 scheduler owner且已分类为预期机制，不是未关闭风险。
- watchdog fatal后已提交的 CANCELLING truth由下一 healthy opener的 S4 recovery/watchdog顺序收口；这是 S3/S4 accepted lifecycle contract，当前 slice不修改 health或recovery owner。
- provider、tool thread/process、HTTP request与external job的physical stop仍是明确 non-goal，继续由既有 ToolRuntime/wait-adapter后续 owner负责；S5只承诺 Host durable cancel治理。
- multiprocess deferred fixture故意删除 child dispatch row以覆盖现有 defensive deferred capability；它不作为有效业务事实，也未推动生产 fallback/兼容分支。
- required matrix与全 `tests/host/` scoped pyright已通过；未运行全仓 pytest。该验证范围按 S5 accepted plan分类，不是未归属 correctness finding。

以上 residual均已有 owner/destination，不构成 S5 stop condition。没有 QueueFull吞 wake、post-write read、错误码来自新 snapshot或watchdog异常绕过 S3 supervisor，状态为 `ready-for-code-review`。
