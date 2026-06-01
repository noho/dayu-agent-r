# WU-LIFE-01 + WU-LIFE-02 Discussion / Code Inspection

日期：2026-06-01
执行角色：phaseflow / gateflow specialist
当前 gate：WU-LIFE-01 + WU-LIFE-02 discussion / code inspection
约束：只读代码核对；除本 artifact 外不修改代码、测试、README、control doc，不 commit，不 push，不进入 plan / implementation gate。

## 1. Scope 与 design/control doc 对齐摘要

### 设计真源

- `docs/host/design.md` 把 Host 定位为“宿主强约束下的 LLM in the loop”，Host 是 Session / Run / Attempt / EventLog / admission / cancel / resume / retry / recovery / governance 的 durable truth。
- Recovery owner 明确：Host startup scan 只基于 durable truth 与 positive orphan proof；旧 Attempt 不 takeover；恢复必须创建新 Attempt。
- Host opener close 明确：close 是 handle lifecycle，不是用户 cancel；close 后 API fail-fast；close 不写 `CANCEL_REQUESTED` / `RUN_CANCELLED` / `RUN_FAILED` / `RUN_LOST` 等伪装用户意图或确认失败的 canonical fact。
- projection checkpoint、memory snapshot、read model、audit、outbox、tool trace 都不是 recovery truth；需要 fresh durable truth 的 recovery / scheduler / governance decision 必须使用新的短事务。

### Control doc

- `docs/host/host-core-followup-implementation-control.md` 明确当前 active work unit 是 WU-LIFE-01 + WU-LIFE-02，当前入口是 discussion / code inspection gate。
- WU-LIFE-01 的目标不是预设重写 recovery，而是整理 recovery lifecycle matrix，对照已有测试只补缺口。只有 reason 不可区分、diagnostic payload 不足或状态转换不稳定时才改生产代码。
- WU-LIFE-02 的目标不是把 close 做成无限 drain，而是整理 scheduler close / cancel_all lifecycle matrix，证明 close / cancel_all 极端窗口稳定，且 close 本身不伪造 terminal facts。

### 第一性原理判断

这两个 work unit 的动机成立，但风险等级被 control doc 正确压低为“证明与缺口补强”，不是“大规模生产逻辑缺失”。直接代码证据显示 recovery、positive orphan proof、open_host startup scan、scheduler close、active cancel、lane close、close 后 fail-fast 已经存在；真实风险集中在矩阵覆盖不完整、部分边界只被低层 classifier 或压力测试覆盖、以及 close / cancel_all 的快照窗口尚未被单元级稳定证明。

设计真源当前足以支持后续 code-generation-ready plan。除非后续 plan 要改变 `WAITING` 语义、close 写入 terminal fact、recovery proof 来源或 scheduler close drain 策略，否则不需要先改 `docs/host/design.md`。

## 2. WU-LIFE-01 Recovery lifecycle proof

### 生产代码直接证据

- `dayu/host/open_host.py`：`_OpenHostContextManager.__aenter__` 打开 `HostDispatchScheduler` 后立即构造 `StartupRecoveryScanner(..., dispatch_wakeup_port=scheduler, recovery_owner_host_instance_id=scheduler.host_instance_id).scan()`，说明 public opener ready 前执行 startup recovery scan。
- `dayu/host/recovery.py`：`StartupRecoveryScanner.scan()` 在单个 write transaction 内读取 `read_non_terminal_runs()`，分类后才在 commit 后 wake dispatch / queue promotion。
- `dayu/host/recovery.py`：`ACCEPTED` 与 `QUEUED` 只产生 promotion wake；`WAITING` 返回 `WAITING_DIAGNOSTIC_ONLY`，reason 为 `waiting_adapter_observation_unavailable`；不创建 Attempt、不推进 `RECOVERING`。
- `dayu/host/recovery.py`：`RUNNING` / `CANCELLING` 读取 current Attempt 与 dispatch record，缺失时返回 `ORPHAN_INCONCLUSIVE`；owner classification 只接受 `PositiveOrphanProof` 后才调用 `close_startup_orphan_attempt_in_transaction()`。
- `dayu/host/recovery_process.py`：`classify_orphan_candidate()` 对 missing owner、missing liveness、recent heartbeat、probe error、live pid without identity proof 都返回 still-live 或 inconclusive；只有 stopped owner、stale + pid missing、pid reused start token / boot id mismatch 等 positive proof 才允许 recovery closeout。
- `dayu/host/recovery.py`：positive orphan 且 recoverable 时写 `ATTEMPT_LOST` + `RUN_RECOVERING`，随后在 wakeup port 和 new owner id 存在时创建 recovery Attempt / execution / dispatch record；`CANCELLING` orphan 使用 `cancel_in_flight_attempt_lost` 收口为 `RUN_LOST`，不继续用户目标。
- `dayu/host/recovery.py`：`RECOVERING` Run 通过 EventLog 统计 recovery dispatch 次数，超过 `recovery_dispatch_limit` 后用 `startup_recovery_dispatch_limit_exceeded` 收口为 `RUN_LOST`。
- `dayu/host/engine_ingest.py` 与 `tests/host/test_recovery_dispatch.py` 共同证明新 Attempt 创建后旧 execution 的 late terminal event 被 reject，不进入 canonical facts。

### 已有测试覆盖

- `tests/host/test_recovery_orphan_classifier.py` 覆盖 missing owner、missing liveness、recent heartbeat、STOPPED owner、STOPPING + recent heartbeat、STOPPING + pid missing、stale heartbeat alone、pid missing、pid live without identity、identity matched、pid reused start token mismatch、boot id mismatch、probe error。
- `tests/host/test_recovery_scan.py` 覆盖 RUNNING positive orphan 进入 `RECOVERING` 且不依赖 projection lag、WAITING diagnostic-only、CANCELLING orphan 写 `ATTEMPT_LOST` / `RUN_LOST`、ACCEPTED / QUEUED 不写 recovery fact 只 wake promotion、RECOVERING 超过 dispatch limit 后 LOST、Session row 缺失时不凭残留 Run row 写 recovery facts。
- `tests/host/test_recovery_dispatch.py` 覆盖 positive orphan startup scan 创建新 Attempt / execution / dispatch 并 wake，旧 execution late final answer 被 reject，orphan closeout 后 recovery dispatch invalid-state 时留下 `RECOVERING_READY`。
- `tests/host/test_open_host_runtime.py` 覆盖 public `open_host` startup recovery：interrupted Run 和 graceful close 后 Run 均在 reopen 时创建新 Attempt 并通过 watch 观察最终 answer。
- `tests/host/test_recovery_multiprocess.py` 覆盖 live owner 不误杀、owner crash 后 public Host event stream 能观察恢复 final answer、projection lag 下仍以 durable EventLog / Run / Attempt / dispatch rows 恢复。
- `tests/host/test_host_production_stress.py` 的 stress suite 覆盖 repeated crash / recovery / live owner probe / terminal 去重，但默认 pytest 不运行。

### 新增缺口

- 缺少 scanner 层的 owner still-live / inconclusive 集成测试。classifier 已覆盖 `owner_heartbeat_recent`、`owner_pid_live_without_identity_proof`、`process_probe_error` 等，但 `StartupRecoveryScanner._classify_active_or_cancelling()` 对这些结果不写 `ATTEMPT_LOST` / `RUN_RECOVERING` 的路径没有专门测试。
- 缺少 recovery lifecycle matrix artifact 或测试参数矩阵，把 Run 状态、owner proof、dispatch record 状态、期望 decision、durable mutation、diagnostic reason 逐项标注为“已有覆盖 / 新增覆盖 / 非目标”。
- `WAITING` startup recovery 的 diagnostic-only 用户可见语义已有低层测试，但缺少 public-path 或 read/watch 语义说明型测试，证明 reopen 后仍保持 WAITING 且不会创建新 Attempt。
- startup timeout / dispatch failure / stream failure reason 已在 scheduler 测试中覆盖，但尚未被纳入 recovery lifecycle matrix，后续 plan 需要把这些现有测试映射到 WU-LIFE-01 验收信号，而不是重复实现。

### 非目标

- 不改变 `WAITING` durable 状态语义。
- 不把 projection checkpoint、memory snapshot、read model、audit、outbox 或 stress summary 提升为 recovery truth。
- 不实现旧 Attempt / Engine / Agent / Runner takeover。
- 不为了矩阵证明引入 lease / fencing / remote ownership 新抽象。

### 是否需要设计真源变更

不需要。`docs/host/design.md` 第 27 节已经足够定义 startup scan、positive orphan proof、RECOVERING 退出、dispatch limit、close 后 recovery 语义和 projection 非 truth 边界。后续 plan 应以当前设计为约束补矩阵和少量 focused tests。

## 3. WU-LIFE-02 Scheduler close / cancel_all lifecycle hardening

### 生产代码直接证据

- `dayu/host/open_host.py`：public handle 的每个 API 入口先调用 `_raise_if_closed()`；`close()` 先置 `_closed = True`，再 `await self._scheduler.close()`，最后 projection catch-up 与 command handle close。重复 close 直接 return。
- `dayu/host/dispatch.py`：`HostDispatchScheduler.wake_dispatch()`、`wake_queue_promotion()`、`run_queue_promotion()`、`drain_once()` 在 `_closed` 为真时抛 `RuntimeError("HostDispatchScheduler is closed")`，满足 close 后 wake fail closed。
- `dayu/host/dispatch.py`：`HostDispatchScheduler.close()` 先置 `_closed = True`，best-effort mark host instance stopping，取消 heartbeat task、dispatch drain task、promotion drain task，调用 `ActiveWorkerRegistry.cancel_all("scheduler_close")`，取消 active tasks，关闭 lane controller，清理 duplicate governance registry，best-effort mark stopped。
- `dayu/host/dispatch.py`：`ActiveWorkerRegistry.cancel_all()` 在锁内复制当前 entries tuple 后释放锁逐个传播取消，语义是快照取消；它没有声称关闭 registry 或阻止后续 register。
- `dayu/host/dispatch.py`：worker event consumer 在 `finally` 中 unregister active worker、close handle、release lane token；close 取消 active task 后依赖该 finally 收口资源。
- `dayu/host/dispatch.py`：worker event clean EOF 在 `cancellation_token.is_cancelled() and not self._closed` 时才把 EOF 映射为 cancelled closeout；scheduler close 期间 `_closed=True`，因此 close 自身不会把 active worker EOF 伪装为 user cancel。
- `dayu/host/dispatch.py`：lane acquire 被 close 取消且 `self._closed` 为真时返回 skipped，不写 worker startup timeout terminal fact。
- `dayu/host/open_host.py`：scheduler close 抛错时仍在 finally 中追平 projection 并关闭 command handle；`tests/host/test_open_host_runtime.py` 有对应验证。

### 已有测试覆盖

- `tests/host/test_public_lifecycle_smoke.py` 覆盖 host close 幂等、close 后 public API 抛 `HostClosedError`、host close 不关闭 open Session、不写 terminal facts，reopen 后 Run 仍为 RUNNING。
- `tests/host/test_open_host_runtime.py` 覆盖 scheduler close 抛错时 command handle 仍 close、projection 仍 flush；startup failure 也会先 flush projection 再 close。
- `tests/host/test_dispatch_scheduler.py` 覆盖 close 不被 active handle cancel / close 异常打断；close 只发 cancel，handle close 由 active task finally 执行一次；close during active events 会取消 token、调用 handle cancel、close handle、unregister registry、release lane；默认 active registry 为 scheduler-local；promotion task 被 close 取消；wake methods after close fail；close 幂等。
- `tests/host/test_dispatch_scheduler.py` 覆盖 durable retry exhausted requeue 不写 terminal closeout、worker startup timeout reason、clean EOF / stream error closeout、terminal 后关闭 stream 不读 late event。
- `tests/host/test_public_cancel_session_runs.py` 覆盖 `cancel_session_runs` 的 QUEUED / pre-dispatch / active worker / WAITING / RECOVERING 子集、幂等重放、空集不写 EventLog；这证明 public cancel 是用户意图，与 scheduler close 的 lifecycle cancel 分离。

### 新增缺口

- close 非无限 drain 的语义缺少显式测试：当前 close 会取消 drain / promotion tasks，但没有专门构造 dispatch queue / promotion queue 非空并断言 close 不处理剩余内存队列、不写 terminal fact、durable pending 留给 next open recovery / promotion。
- `cancel_all` 快照语义缺少独立单元测试：可以直接构造 registry，在 `cancel_all()` 复制快照后注册新 entry，证明本次 cancel_all 不取消后注册 entry；后续语义由 scheduler close gate / active task cancellation / next-open recovery 兜底。
- worker 已启动但尚未 durable accept / active registry register 的 close 极端窗口缺少 focused 测试。生产背景 drain task 被 close 取消后理论上应释放 lane、不写 terminal；但这个窗口目前主要由代码结构和间接测试支撑。
- close 中途被外层取消的行为没有单独证明。当前 `HostDispatchScheduler.close()` 没有 shield/finally 包裹完整 cleanup；若调用方 task 在 close 执行中被取消，可能停在 mark stopping、active cancel、lane close 或 mark stopped 中间。control doc 明确要求“close 中途取消”稳定行为，因此这是 WU-LIFE-02 最实质的待核对风险。
- close 不写 `RUN_CANCELLED` / `RUN_FAILED` / `RUN_LOST` 已有 public smoke，但缺少 scheduler-level 精确断言覆盖 active lane wait、pending dispatch、promotion queue 非空等 close windows。

### 非目标

- 不把 close 设计成 drain-until-empty。
- 不让 close 隐式创建用户 cancel 或 failed / lost terminal facts。
- 不把 scheduler close 的进程内 lifecycle cancel 改成 durable user cancel。
- 不为 `ActiveWorkerRegistry` 引入全局 closed 状态，除非后续测试证明现有 close gate 无法覆盖新注册窗口。

### 是否需要设计真源变更

不需要。`docs/host/design.md` 对 Host close lifecycle、close 后 API fail-fast、close 不写 terminal fact、shutdown order、active worker lifecycle cancel 与 next-open recovery 兜底已经足够具体。后续 plan 可以直接按现有设计补测试；只有发现 close 中途取消需要改变 public lifecycle guarantee 时，才需要回设计真源。

## 4. Residual risks RR-DUR-01 / RR-DUR-04 核对

### RR-DUR-01 projection checkpoint 真实多进程 CAS race 证明

直接证据：

- `dayu/host/recovery.py` 的 recovery scanner 只读 Run / Attempt / dispatch / liveness durable truth，不读 projection checkpoint。
- `tests/host/test_recovery_scan.py::test_scan_running_positive_orphan_moves_to_recovering_without_projection` 明确插入 projection lag marker 后仍按 durable truth 进入 `RECOVERING`。
- `tests/host/test_recovery_scan.py::test_scan_recovering_loses_when_eventlog_recovery_limit_reached_despite_projection_lag` 明确 recovery dispatch limit 只看 canonical EventLog，projection lag 不影响 LOST 决策。
- `tests/host/test_durable_concurrency_matrix.py` 已有 deterministic projection checkpoint lost CAS 与 memory snapshot + checkpoint rollback 证明。

判断：不纳入 WU-LIFE-01/02 implementation scope。Recovery lifecycle proof 不需要真实多进程 projection checkpoint CAS race 才能成立，因为 recovery 不依赖 projection checkpoint。建议后续 controller 更新 tracking 时将 RR-DUR-01 按“当前 WU-LIFE inspection 证明不属于 recovery lifecycle correctness 前置条件”关闭；若未来需要真实多进程 projection CAS 压力，应转入 projection / durable hardening owner，而不是 WU-LIFE。

### RR-DUR-04 production long read transaction governance scan

直接证据：

- `dayu/host/recovery.py::StartupRecoveryScanner.scan()` 使用 `transaction_runner.run_write(operation)` 执行一次短事务；scan 完成后才 wake dispatch / promotion，没有持有 read transaction 跨外部调用。
- `dayu/host/open_host.py` startup recovery、admission service 创建与 public handle ready 是顺序执行；recovery scan 不依赖 long-lived read snapshot。
- `dayu/host/dispatch.py` 的 queue promotion、dispatch recheck、worker accept closeout、heartbeat 都通过短 `run_read` / `run_write` operation 完成；worker event stream 和 compactor调用不应持有 Host write transaction。
- `tests/host/test_dispatch_scheduler.py::test_proactive_compaction_calls_llm_outside_write_transaction` 已验证 proactive compactor 外部调用时不持有 Host write transaction。
- `tests/README.md` 与 `dayu/host/README.md` 均记录 read transaction 使用 SQLite snapshot 语义，新的短读事务读取最新 committed truth；WAL checkpoint primitive 不作为 EventLog / state correctness 前置条件。

判断：纳入 WU-LIFE-01 plan 的 proof matrix / code inspection scope，但不预设生产代码修改。后续 planning agent 应把 recovery、queue promotion、dispatch recheck、active cancel、close、compaction 外部调用这些 governance decision 路径逐项列入矩阵；只有发现某路径把长 read transaction / projection lag 用作治理 truth，才进入 implementation slice。

## 5. 建议的 plan scope boundary、non-goals、stop conditions

### 建议 plan scope boundary

- 一个联合 plan 可以覆盖 WU-LIFE-01 + WU-LIFE-02，但应拆成两个 implementation slices：
  - Slice A：Recovery lifecycle proof matrix + focused recovery tests。优先补 scanner still-live / inconclusive 集成测试、WAITING startup recovery public/read 语义测试，以及 existing scheduler startup failure reason 到矩阵的映射。
  - Slice B：Scheduler close / cancel_all lifecycle matrix + focused close-window tests。优先补 close queue 非空不 drain、cancel_all snapshot after-register、close 中途取消 cleanup、lane wait / pending dispatch close 不写 terminal fact。
- plan artifact 应位于 `docs/host/`；discussion / review artifact 位于 `docs/reviews/`。
- README 触发判断：若只新增测试与 review / plan artifact，不改 Host public contract 或测试运行入口，通常不需要更新 `dayu/host/README.md` 或 `tests/README.md`；若新增稳定测试入口、marker 或改变 close / recovery public semantics，才同步对应 README。

### Non-goals

- 不改变 recovery public contract、durable schema、EventLog event type、Run / Attempt 状态机。
- 不实现 remote worker takeover、lease、fencing 或 recovery ownership 新机制。
- 不让 close 写 cancel / failed / lost terminal facts。
- 不扩大为 stress / fuzz / soak；stress suite 仍是独立显式入口。
- 不把 RR-DUR-01 的真实多进程 projection checkpoint CAS race 放进本 work unit。

### Stop conditions

- 发现 current design 不足以决定某个 state transition、EventLog fact、close cancellation guarantee 或 public user-visible behavior。
- 任何新增测试证明 close 中途取消会稳定泄漏 active task / lane token / registry entry，且不能在不改变 lifecycle contract 的前提下修复。
- 任何新增测试证明 recovery scanner 会基于 projection/read model/heartbeat stale alone 写 `ATTEMPT_LOST` / `RUN_RECOVERING` / `RUN_LOST`。
- 任何实现修改需要 durable schema、public request / response dataclass、Host event type 或 README 中稳定 public API 变更。
- pyright 或 affected tests 暴露既有错误并触及本 work unit 修改范围。

## 6. Blocking open questions

none

## 7. 后续 planning agent 可直接使用的 affected files/modules 与测试入口候选

### Affected files/modules

- `dayu/host/recovery.py`
- `dayu/host/recovery_process.py`
- `dayu/host/dispatch.py`
- `dayu/host/open_host.py`
- `dayu/host/engine_ingest.py`
- `dayu/host/durable/run_transition.py`
- `dayu/host/durable/state.py`
- `dayu/host/durable/liveness.py`
- `dayu/host/durable/projection.py`
- `tests/host/test_recovery_scan.py`
- `tests/host/test_recovery_dispatch.py`
- `tests/host/test_recovery_orphan_classifier.py`
- `tests/host/test_recovery_multiprocess.py`
- `tests/host/test_dispatch_scheduler.py`
- `tests/host/test_open_host_runtime.py`
- `tests/host/test_public_lifecycle_smoke.py`
- `tests/host/test_public_cancel_session_runs.py`
- `tests/host/test_host_production_stress.py`

### 测试入口候选

```bash
source .venv/bin/activate
pytest tests/host/test_recovery_scan.py tests/host/test_recovery_dispatch.py tests/host/test_recovery_orphan_classifier.py tests/host/test_recovery_multiprocess.py -q
pytest tests/host/test_dispatch_scheduler.py tests/host/test_open_host_runtime.py tests/host/test_public_lifecycle_smoke.py tests/host/test_public_cancel_session_runs.py -q
pytest tests/host/test_durable_concurrency_matrix.py tests/host/test_projection_checkpoint.py tests/host/test_memory_projection.py -q
python -m pyright dayu/ tests/ utils/
```

Stress suite 只作为可选显式验证入口，不应进入默认 plan validation：

```bash
source .venv/bin/activate
pytest -o addopts="" -m stress tests/host/test_host_production_stress.py -q
```

## 8. 结论

- WU-LIFE-01 风险真实存在，但主要是 lifecycle proof / matrix / focused regression 缺口，不是 recovery 生产逻辑缺失。设计真源足够，不建议先改设计。
- WU-LIFE-02 风险真实存在，且 close 中途取消、非空内存队列不 drain、cancel_all 快照后注册窗口是比普通 close 幂等更值得补的真实缺口。设计真源足够，不建议先改设计。
- RR-DUR-01 不应纳入本 work unit implementation scope；recovery 不依赖 projection checkpoint，现有 deterministic CAS 与 recovery projection-lag 测试足以支撑当前判断。
- RR-DUR-04 应纳入 WU-LIFE-01 planning 的 proof matrix / code inspection scope，但不预设代码改动。
- 建议进入 plan gate：是。plan 应是 code-generation-ready 的测试与证明补强计划，默认不修改生产逻辑；只有新增测试暴露稳定性或 diagnostic 缺陷时才允许最小生产修复。
