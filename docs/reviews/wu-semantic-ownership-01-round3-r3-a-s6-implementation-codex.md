# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-A S6 Implementation

## Gate

- Work unit：`WU-SEMANTIC-OWNERSHIP-01 Round3 R3-A`
- Slice：`S6 - Wait Expiry、Bounded Observation 与 Host Shutdown`
- Agent：`AgentCodex`
- Gate：implementation / fix
- 基线：S5 accepted commit `b655fae9`，control-doc commit `1b589ee6`
- 状态：`ready-for-code-review`
- Artifact：`docs/reviews/wu-semantic-ownership-01-round3-r3-a-s6-implementation-codex.md`

本 gate 未 commit、push、创建 PR、进入 S7/S8，也未修改总控文档。

## 第一性原理与 owner 判定

### 动机是否成立

成立，且严重性没有被高估。

1. durable deadline 是 Host 已经确认的治理事实。deadline 到期后仍只释放 poll claim / backoff，会让 Wait 与 Run 无限停在 `WAITING`；这不是 provider 观察问题，而是 Host wait state machine 未提交其拥有的 terminal fact。
2. provider `poll_wait()` / `abandon_wait()` 是否返回只是外部观察能力。无界等待不能提高事实可信度，只会让 Host close 失去上界；观察超时表示状态不可确认，应是 `LOST` 或 abandon diagnostic，而不能伪装成 deadline expiry。
3. deadline expiry 与 observation timeout 必须由两个 owner 分别产生，再在 poller orchestration 处组合。把两者都放在 adapter、callback 或 open-host cleanup 中会造成状态分类、幂等 identity 和关闭语义漂移。

### 唯一语义 owner

| 语义 | 唯一 owner | 消费者 / handoff | 禁止的补救方式 |
| --- | --- | --- | --- |
| durable deadline terminal | `dayu.host.waiting._expire_wait_in_transaction()` | direct、callback、poller；现有 failed transition、projection、promotion | poller release/backoff；callback fallback；把 expiry 写成 LOST |
| expiry identity / payload | `ExpireWaitInput`、固定 reason/message、durable boundary digest | `ResolveWaitFailedOutcome`、EventLog、idempotency | 从 poll/callback source 或迟到 outcome 派生 identity |
| sync adapter invocation budget / publish authority | `dayu.host._wait_observation.WaitObservationRunner` | `WaitPoller`、`WaitPollerSupervisor` | 散落线程、迟到 resolver 调用、用 sleep count 猜线程状态 |
| observation timeout classification | `WaitPoller` | common `resolve_wait` LOST path 或 abandon timeout marker | 把 provider 卡住解释为 deadline expired；接受迟到 READY |
| shared close deadline / CLOSING→STOPPED | `WaitPollerSupervisor` | `open_host` S2 close order | 每个 thread 各等一份预算；timeout 后无界 join；虚假 STOPPED |

实现没有修改 S3 health state machine、S4 recovery cursor、S5 cancel governance、Engine、Service、CLI 或 Fins。`dayu.host.durable.run_transition` 的既有 `fail_run_from_waiting_in_transaction()` 已能表达所需 terminal matrix，因此复用而未复制 transition。

## 实际变更

### Production

- `dayu/host/_wait_observation.py`（新增）
  - 新增 Host-owned bounded observation runner。
  - token gate 为 `ACTIVE / INVALIDATED / FINISHED`；publish、timeout invalidation 与 close generation 在同一 lock 下线性化。
  - 每个 invocation 使用 daemon thread 与 `Queue(maxsize=1)`；registry 施加 `max_outstanding_adapter_calls`。
  - timeout/close 后迟到 value/exception 只增加 dropped diagnostic，不调用 resolver，也不持 durable authority。
  - `drain_until(deadline_monotonic)` 对所有线程只消费一个绝对 shared deadline。
- `dayu/host/api.py`
  - 扩展 public opener 所消费的 wait policy runtime Protocol：finite adapter call budget、required finite close budget、positive outstanding cap。
  - structural policy validation 同样拒绝 non-finite 新预算。
- `dayu/host/waiting.py`
  - 新增 `ExpireWaitInput`、`ExpireWaitResult` 与 exact two-argument `_expire_wait_in_transaction(transaction, input)`。
  - expiry 固定构造 `ResolveWaitFailedOutcome(ToolResultFailure(error="wait_deadline_expired", hint/meta=None), payload_ref=None)`，复用 payload planner、event-id planner 与 `fail_run_from_waiting_in_transaction()`。
  - expiry identity 只由 wait id、durable boundary field/value 与固定 reason 派生；source/actor 不参与 identity。
  - direct/callback late result 在同一 transaction 先完成 expiry，再写 `WAIT_LATE_RESULT_REJECTED`；commit 后 projection 与 queue-promotion wake 完成后才向 caller 抛 `INVALID_STATE`。
  - failed/lost wait closeout 也统一返回 queue-promotion owner handoff；resume/cancelled tool outcome 语义未改变。
- `dayu/host/command.py`
  - direct/callback resolve service 注入既有 admission wake port。
  - 新增 Host-internal `expire_wait()` command handoff，供 poll round 私有 command handle 使用。
- `dayu/host/wait_adapter.py`
  - `WaitPollerRuntimePolicy` 新增 `adapter_call_timeout_seconds` 与 `max_outstanding_adapter_calls`，并把 `close_drain_timeout_seconds` 收窄为 required finite-positive float。
  - poll deadline-first 路径调用 common expiry helper，不再调用旧 expired release/backoff helper。
  - `poll_wait()` / `abandon_wait()` 统一进入 bounded observation runner；timeout、capacity、closed、ordinary exception 都是 typed branch。
  - stuck poll 通过既有 resolve pipeline 收为 `LOST(wait_observation_timeout)`；stuck abandon 写 `poll_abandoned_at + wait_abandon_timeout`，保留 `ABANDON_ERROR` schema enum，不声明 external cancel success，也不重复 spawn。
  - supervisor close 先关闭 generation / INVALIDATE tokens，再以一个 monotonic deadline join poller 与 registry snapshot；预算耗尽保持 `CLOSING`，最后一个 tracked thread finally 后才 `STOPPED`。
- `dayu/host/durable/state.py`
  - 新增 owner-level `mark_wait_record_poll_abandon_timeout()`，在既有 fresh schema 内原子写 timeout diagnostic / close marker并清 claim；未修改 schema 或状态枚举约束。
- `dayu/host/open_host.py`
  - production poller factory 接收 supervisor-owned observation runner。
  - poller resolver 增加 internal expiry handoff；S2 actor、scheduler、store close order保持不变。

### Tests

- 新增 `tests/host/test_wait_expiry_closeout.py`：helper owner、固定 failure envelope、stable replay、commit→projection→promotion，以及 spawn 多进程 result/cancel/expiry first-committer race。
- 新增 `tests/host/test_wait_observation_runner.py`：stuck poll、late publish=false、cap=1、stuck abandon、shared close deadline 与 CLOSING/STOPPED refs。
- 更新 `tests/host/test_resolve_wait_command.py`、`test_wait_callback.py`、`test_wait_adapter_polling.py`：旧“expired 仍 WAITING”断言迁移为 common FAILED owner contract；poll test resolver 增加 internal expiry port。
- 更新 `tests/host/test_wait_poller_runtime.py`：factory 接收 shared runner；`None` / non-finite / non-positive policy 反例；bounded close 不再等待无界 in-flight call。
- 更新 `tests/host/test_wait_cancel_late_result.py`：late diagnostic commit 后 projection catch-up 的现行 owner contract。
- 更新 `tests/host/test_public_open_host_options.py`：structural public wait policy shape 与新增字段一致。

### Docs

- `docs/host/design.md`：冻结 expiry=FAILED、observation timeout=LOST、token gate、cap 与 shared close deadline。
- `dayu/host/README.md`：只记录当前已实现的 wait terminal / bounded observation / execution close contract。
- `tests/README.md`：登记两个新增 owner-level测试层级与确定性 oracle。

未修改 `dayu/host/__init__.py`：新增 expiry/observation 类型是 Host-internal owner，不应扩大 package public surface。未修改 `dayu/host/durable/run_transition.py`：既有 transition 已满足契约。未修改 `dayu/fins/`、Service、CLI、Engine、根 README 或 `dayu/README.md`。

## 11 个 required counterexamples

1. **expiry helper owner contract**：`test_expiry_helper_owns_failed_terminal_and_stable_replay` 直接把真实 `HostTransaction` 交给 exact helper；一次 outer write 生成固定 FAILED outcome 与两个 terminal facts。第二次改 actor/source 重放，event 集合不变，证明 identity 不依赖 source。
2. **poller deadline-first / provider call=0**：更新后的 `test_expired_poll_wait_is_released_before_provider_observation` 对 READY、NOT_READY、exception adapter 均断言 provider call=0，Wait/Run=FAILED；新增 expiry closeout test 断言 commit 后 projection/promotion 顺序。
3. **direct/callback late result after deadline**：`test_resolve_wait_rejects_expired_wait_from_common_owner` 与 `test_expired_callback_is_rejected_by_resolve_owner` 断言 caller 收 `INVALID_STATE`，但 durable Wait/Run 已 FAILED且 late diagnostic 已提交。
4. **result/cancel/expiry first-commit race**：`test_result_cancel_expiry_multiprocess_first_committer_wins` 使用 spawn context 的四方 Barrier 同时释放三个独立 SQLite process；最终恰好一个 `RUN_FAILED` / `RUN_CANCELLED` terminal ref，Run/Wait 状态一致。
5. **deadline-before 与 INVALID semantics**：既有 completed/failed/lost/cancelled tests继续通过；invalid durable deadline 仍 fail closed且不转 LOST；`ResolveWaitCancelledOutcome` 仍走 resume。
6. **stuck poll→LOST**：`test_stuck_poll_times_out_to_lost_and_late_result_is_dropped` 以 Event barrier 卡住 provider，Host 在 test policy budget 后收为 LOST，poller round 有界返回。
7. **late adapter result publish=false**：释放第 6 项 barrier 后，registry 从 INVALIDATED 到 FINISHED/removed，`dropped_count=1`，Wait 保持 LOST，无 accepted result/resume wake。
8. **outstanding cap**：`test_outstanding_cap_does_not_spawn_second_thread` 在 cap=1 且首线程 INVALIDATED/live 时返回 typed capacity，第二 operation 的 entered Event 未 set；释放首线程后 registry 清零并允许下一次观察。
9. **stuck abandon bounded closeout**：`test_stuck_abandon_writes_timeout_marker_without_external_success` 断言 `poll_abandoned_at`、`wait_abandon_timeout`、无 repeated observation、`abandoned=0`；迟到 applied 只 dropped。
10. **supervisor shared close deadline**：`test_supervisor_close_uses_one_shared_deadline_and_stays_closing` 用不同 Event barrier 阻塞 poller loop 与两个 provider。close 只消费一次 budget并返回 CLOSING；依次释放时 refs 从 2→1→0，最后一个 finally 后才 STOPPED，重复 close 幂等。
11. **invalid policy rejection**：`test_runtime_policy_rejects_none_close_drain_timeout`、non-finite 参数化测试、non-positive field/cap 测试覆盖 `None`、NaN、正负 infinity、零与负数。

新增并发测试的业务 oracle 均来自 Event/Barrier、durable terminal facts、token state/registry refs 与 callback order；短轮询 helper只等待已由 barrier 触发的 thread finally/status 收敛，不以 sleep 次数证明竞态正确性。

## Validation

### Required focused pytest

命令：

```bash
source .venv/bin/activate
pytest tests/host/test_wait_expiry_closeout.py tests/host/test_wait_observation_runner.py tests/host/test_resolve_wait_command.py tests/host/test_wait_callback.py tests/host/test_wait_adapter_polling.py tests/host/test_wait_poller_runtime.py tests/host/test_wait_cancel_late_result.py tests/host/test_phase7_waiting_integration.py tests/host/test_public_open_host_options.py tests/host/test_open_host_runtime.py tests/host/test_package_exports.py -q
```

结果：`137 passed in 2.47s`。

### Required pyright

命令：

```bash
source .venv/bin/activate
python -m pyright dayu/host/ tests/host/
```

结果：`0 errors, 0 warnings, 0 informations`。仅输出 pyright `1.1.409 -> 1.1.411` 可升级提示，不是检查失败。

### Source scans

1. `rg -n "thread\.join\(\)|close_drain_timeout_seconds: float \| None|join_thread\(\)" ...`
   - 零命中：无无参 `thread.join()`、无 optional close timeout、无 queue feeder `join_thread()`。
2. `rg -n "_release_expired_or_invalid_boundary|WAIT_EXPIRED" ...`
   - 旧 `_release_expired_or_invalid_boundary` 零命中。
   - `WAIT_EXPIRED` 只命中 `WaitLateRejectionReason` 与两处 late diagnostic classification；它不再拥有 terminal transition或 poll release。
3. `rg -n "ExpireWaitInput|_expire_wait_in_transaction|ResolveWaitFailedOutcome|fail_run_from_waiting_in_transaction" ...`
   - 命中 typed expiry input、direct/service/poller handoff、固定 failed outcome、现有 failed transition；common owner 链闭合。
4. `rg -n "max_outstanding_adapter_calls|ACTIVE|INVALIDATED|FINISHED|publish" ...`
   - 命中唯一 runner registry/cap/token/publish gate owner与 policy wiring；无第二套 cap 或 downstream publish fallback。
5. `git diff --name-only -- dayu/fins/`
   - 零输出；Fins production diff 为空。
6. `git diff --check`
   - 通过，零输出。

## README / design 触发判断

- `dayu/host/` production contract发生变化，命中 `dayu/host/README.md` 触发；已先读取其 Agent 更新约束，只写已实现的稳定 boundary。
- 新增 Host owner-level测试，命中 `tests/README.md` 触发；已更新测试层级与 oracle，不写 implementation 流水账。
- approved plan 明确要求 `docs/host/design.md` 同步 expiry FAILED / bounded close contract；已更新。
- 用户安装、CLI 参数、输出、工作区位置与最终用户 workflow 未变化，根 `README.md` 不更新。
- UI/Service/Host/Engine 分层关系与 Service assembly 未变化，且 `dayu/README.md` 不在 S6 allowed list，不更新。
- Fins/Engine package 未修改，对应 README 不更新。

## Residual risk

1. **deferred-with-owner（R3-D）**：不合作的同步 provider daemon thread 在 timeout 后仍可能运行到进程退出。本 slice 已用 outstanding cap、INVALIDATED token、dropped publish 与无 durable authority把 Host 风险有界化；provider cooperative cancellation与 Fins adapter reverse-dependency 搬迁仍由 controller 已指定的 R3-D owner处理。
2. **无未分类 S6 residual**：deadline terminal、first-commit、late publish、cap、stuck poll/abandon、shared close deadline与 open-host shutdown handoff均已有直接测试。没有把 required failure留作 residual。

## Completion decision

S6 stop condition 全部满足：没有 Wait 因已确认 deadline 无限停在 WAITING；late observation thread不能 publish或接触 Host durable authority；tracked invocation 有上限；close 预算不按线程数倍增且不存在无界 join；`dayu/fins/` diff为空。

**最终状态：`ready-for-code-review`。**
