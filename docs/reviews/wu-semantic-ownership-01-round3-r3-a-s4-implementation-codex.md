# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-A S4 Implementation（AgentCodex）

## 状态

`ready-for-code-review`

本 gate 只实施 S4 Startup Recovery Keyset Batching。未修改 S3 health state machine、admission lease、watchdog、cancel command、public API、S2 actor 实现、Service、CLI、Fins、Engine 或总控文档，也未实施 S5-S8。

## 第一性原理与 owner 判定

S4 动机成立。直接证据是原 `StartupRecoveryScanner.scan()` 在一次 `HostTransactionRunner.run_write(...)` 中调用全量 `read_non_terminal_runs(...)`，并在同一 write transaction 内分类、迁移全部 non-terminal Run；数据量增长会线性延长单次 SQLite writer 占用。production opener 还在 durable actor 创建前使用 scheduler store connection 同步执行该 scan，因此 recovery 没有落在 S2 actor 的 connection/thread owner 上，也没有显式的 bounded commit/wake/READY handoff。

语义 owner 判定如下：

- non-terminal recovery 顺序、fixed upper boundary 与 page query：`dayu.host.durable.state` 的 durable Run governance reader；唯一全序是 `(accepted_event_sequence, run_id)`，projection/read model 不参与。
- scan 级 fixed `policy.now`、batch 大小、cursor 推进、每批 transaction 与 commit 后 wake：`StartupRecoveryScanner`；业务分类继续由既有 `_classify_run(...)` owner 持有。
- SQLite connection/thread：S2 durable actor；recovery operation 只通过 actor-owned `HostCommandHandle` 取得 transaction runner。
- STARTING 到 READY 的 orchestration：execution opener；全部 batch 与 matching wake 成功前不调用 S3 `mark_ready()`。
- 失败重跑：durable CAS/idempotency 与 pending records，不保存或恢复进程内 offset。

该 owner 划分足以完成 S4，不需要修改 health、watchdog、cancel、Service/CLI/Fins/Engine，因此未触发 blocking stop condition。

## 实际变更与文件范围

### Production

- `dayu/host/durable/state.py`
  - 新增 immutable typed `NonTerminalRunKeysetCursor(accepted_event_sequence, run_id)`。
  - 新增 `read_non_terminal_run_upper_watermark(...)`，从 durable non-terminal Run index 读取固定最大 keyset，SQL 使用 `ORDER BY ... DESC LIMIT 1`。
  - 新增 `read_non_terminal_runs_keyset_page(...)`，使用严格 lower cursor、inclusive upper watermark、稳定升序与 `LIMIT ?`；不使用 OFFSET，`fetchall()` 只消费单个 bounded page。
  - reader 在查询前严格校验 watermark、cursor 与正整数 batch size。
- `dayu/host/recovery.py`
  - 增加唯一 typed 默认 batch size `DEFAULT_STARTUP_RECOVERY_BATCH_SIZE = 64`。
  - scan 开始时只创建一次 policy，冻结 `policy_now`，读取一次 upper watermark。
  - 每个 page 通过独立 `_StartupRecoveryBatchOperation` 执行 write transaction；operation 内 accumulator 为 retry-local，不让失败/retry 泄漏 actions 或 wakes。
  - transaction 成功返回后才投递该批 dispatch / queue-promotion wake；rollback batch 不投递 wake。
  - cursor 只从已提交 page 最后一行派生并校验严格推进；完整 scan aggregate 只包含 committed batches。
  - 保留原 `_classify_run(...)` 及 orphan/recovery/cancel 分类实现，没有改状态集合、positive orphan proof、recovery dispatch limit 或 accepted-cancel 语义。
- `dayu/host/open_host.py`
  - 新增 typed `_StartupRecoveryActorOperation`，在 S2 actor worker thread/connection 上执行全部 recovery batches。
  - wake 继续使用既有 actor-thread 到 opener-loop bridge。
  - recovery 完成后才创建后续 runtime handle并执行既有 `health_gate.mark_ready()`；异常进入既有 startup cleanup，绝不 READY。

### Tests

- `tests/host/test_recovery_scan.py`
  - batch size=2、5 个 Run 的 page 上限、严格 cursor、无 duplicate/missing action。
  - defensive 同 sequence/different run id SQL tie-break；由于 production EventLog sequence 唯一，fixture 只为 reader-level total-order 反例临时关闭 FK，不把该状态当作业务事实。
  - watermark read 后插入更高 sequence Run，验证本轮排除、下一轮纳入。
  - advancing clock 替身验证 default policy 只创建一次、所有 batch 使用同一 `policy.now`。
  - 第 2 批在实际 mutation 后失败，验证整批 rollback、零该批 wake、第 1 批 facts/wakes 保持；完整重跑验证五个 durable dispatch 与五个 wake identity 一一匹配且无内存 offset 依赖。
  - batch size=2 下验证 ACCEPTED、QUEUED、WAITING、accepted-cancel CANCELLING 的既有分类不漂移。
- `tests/host/test_open_host_runtime.py`
  - `threading.Event` barrier 确认 recovery 在 actor worker thread，barrier 释放前 READY 未发生，完成后 READY 只在 opener loop thread发生。
  - startup recovery 异常路径额外断言 `mark_ready()` 调用次数为零。

`tests/host/test_recovery_dispatch.py`、`tests/host/test_recovery_multiprocess.py` 与 `tests/host/test_admission_multiprocess.py` 无需修改；它们作为 required regression matrix 验证原 recovery dispatch identity、positive orphan proof、多进程 recovery 与 admission durable invariants未被分页改变。

### Docs

- `docs/host/design.md`：记录 fixed policy/watermark、keyset 全序、默认 64 行 batch、每批 commit 后 wake、失败重跑与 STARTING/READY handoff。
- `dayu/host/README.md`：同步当前已实现的 startup recovery stable boundary。
- `tests/README.md`：同步 S4 deterministic owner-level coverage。

## 必须反例如何满足

1. **bounded batch 与稳定 cursor**：5 个同 sequence Run、batch size=2 实际读取 page size 为 `(2, 2, 1)`；cursor 为 `None -> (100, run-b) -> (100, run-d)`，upper watermark 始终 `(100, run-e)`，actions 按 run id 全序且无重复/遗漏。每个 page reader 在对应 write operation 内执行，单 transaction 最多分类 2 行。
2. **fixed upper watermark 与 concurrent insert**：watermark read transaction 返回后确定性插入更高 EventLog sequence 的新 Run；首次 scan actions 不含该 Run，第二次 scan 包含。独立 defensive fixture 验证同 sequence 由 run id 稳定排序。
3. **fixed policy time**：monkeypatched `StartupRecoveryPolicy.default()` 每次调用会推进一分钟；完整五行/三批 scan 只调用一次 default，所有分类观察到同一 `_NOW`，结果均保持 `OWNER_STILL_LIVE`。
4. **commit 后 wake / rollback 无 wake**：第 2 批第 1 行完成真实 transition 后抛错；该批 transaction rollback，第三个 Run 仍指向旧 Attempt，该批无 wake；第 1 批两个 `ATTEMPT_LOST` facts 与两个 wake 保持。
5. **完整重跑与 idempotent durable convergence**：失败后从 cursor=None 完整重跑；已提交前两行由 durable current owner 分类为 `OWNER_STILL_LIVE`，未提交三行各创建一次 recovery dispatch。最终五个 distinct wake 的 run/attempt/execution/dispatch identity 与 durable current dispatch 一一匹配，canonical transition 计数与既有 single-batch recovery baseline 相同，不读取失败 scan 的内存 cursor。
6. **分类不漂移**：同一 paginated scan 精确得到 `ACCEPTED_WAKE`、`QUEUE_PROMOTION_CHECK`、`WAITING_DIAGNOSTIC_ONLY`、`DEFERRED_TO_ACTIVE_CANCEL_WATCHDOG`；WAITING/CANCELLING durable status 不变，未提前实施 S5 watchdog。
7. **失败不得 READY**：actor barrier 在 scan 未完成时断言 READY 记录为空；scan 异常测试断言 `mark_ready()` 零调用。已提交 batch 只留下 durable facts/pending records，scanner 完整重跑及 required multiprocess healthy opener matrix证明后续 opener 不依赖内存 offset。

全部 race/ordering oracle 使用 `threading.Event`、actor future、transaction rollback 与 durable row/event identity；没有用 sleep 次数或概率竞争作为 correctness oracle。

## 验证结果

### Required focused pytest

命令：

```bash
source .venv/bin/activate
pytest tests/host/test_recovery_scan.py tests/host/test_recovery_dispatch.py tests/host/test_recovery_multiprocess.py tests/host/test_open_host_runtime.py tests/host/test_admission_multiprocess.py -q
```

结果：`60 passed in 6.57s`。

### Required pyright

命令：

```bash
source .venv/bin/activate
python -m pyright dayu/host/recovery.py dayu/host/open_host.py dayu/host/durable/state.py tests/host/
```

结果：`0 errors, 0 warnings, 0 informations`。工具另提示 pyright `1.1.409 -> 1.1.411` 有新版本，该提示不影响检查结果。

### Required source scans

命令：

```bash
rg -n "read_non_terminal_runs\(|OFFSET|fetchall\(" dayu/host/recovery.py dayu/host/durable/state.py
```

分类：

- `dayu/host/recovery.py` 无命中：recovery 不再调用全量 reader，不含 OFFSET，也不直接 `fetchall()`。
- `dayu/host/durable/state.py:1927` 是保留给非 recovery 消费者的既有全量 reader定义；S4 recovery 没有引用它。
- `dayu/host/durable/state.py:2032/2075` 是 S4 bounded page reader 的说明与唯一 `fetchall()`；同一 SQL 在 `dayu/host/durable/state.py:2109` 明确使用 `LIMIT ?`，参数为唯一 typed `batch_size`。
- 其余 `fetchall()` 命中属于既有 Session、Session-scoped Run、cancelling Run、wait、queued Run readers，均不在 S4 recovery call graph，也不是本 slice 新增。

命令：

```bash
rg -n "accepted_event_sequence|upper_watermark|cursor|batch_size|policy_now" dayu/host/recovery.py dayu/host/durable/state.py
```

分类：`NonTerminalRunKeysetCursor` 是 keyset/watermark 唯一 typed owner；state reader拥有 SQL lower/upper boundary 与 LIMIT；scanner 拥有 default batch size、fixed `policy_now`、batch orchestration和 committed cursor推进。其它 `accepted_event_sequence` 命中是既有 Run row codec/readers，不构成第二 recovery cursor owner。

命令：

```bash
git diff --check
```

结果：通过，无输出。

## README / design 触发判断

- 修改 `dayu/host/` 且改变 startup recovery stable mechanism，命中 `dayu/host/README.md` 触发条件；已按其 Agent 更新约束同步当前实现，不写 gate 流水账。
- 修改 Host tests，命中 `tests/README.md` 触发条件；已同步 deterministic coverage。
- 本实现落地 accepted S4 design，`docs/host/design.md` 已同步 fixed watermark/keyset/batch/READY contract。
- 未改变用户可见安装、CLI 参数/输出、Service assembly、分层关系或跨层依赖，因此不更新根 README、`dayu/README.md` 或其它 README。

## Residual risk / scope note

- fixed watermark 依赖 EventLog `event_sequence` 单调唯一这一 durable schema invariant；reader仍以 `run_id` 提供 defensive tie-break，测试使用专用 invalid-FK fixture 覆盖该全序分支。
- 一个 batch commit 后若多个 loop wake 中的后续 wake bridge 失败，先前 callback可能已执行；opener仍 fail closed、不进入 READY，durable pending truth 允许下一 healthy opener幂等重放。wake callback 本身不是跨 callback 的原子事务，这不是 rollback wake 泄漏。
- legacy `read_non_terminal_runs(...)` 仍供非 recovery 代码/测试使用；S4 只要求并已保证 recovery call graph 不再使用全量 reader。删除该通用 reader超出本 slice。
- required matrix 与 scoped pyright 已通过；未运行全仓 pytest。

以上 residual 不构成 S4 stop condition。没有全量 recovery write transaction、OFFSET、duplicate/missing action、rollback batch wake 或失败后 READY，状态为 `ready-for-code-review`。
