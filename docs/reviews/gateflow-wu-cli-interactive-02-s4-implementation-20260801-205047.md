# wu-cli-interactive-02 S4 implementation（F11/F12）

- Work unit：`wu-cli-interactive-02-conformance-fixes`
- Gate：S4 implementation，仅 F11/F12
- Branch：`codex/interactive-oracle`
- Base HEAD：`eadee40932cff2113e944620dcbac1bf187ab799`
- 完成时间：2026-08-01 20:50:47 CST
- Finding status：`implementation未review`
- Next gate：`S4 code review`

## 1. 直接证据与 owner 判定

F11 的冲突事实来自多个 request-backed terminal writer 在各自 write transaction
内独立判断并追加 `CONTEXT_COMPACTED` / `CONTEXT_COMPACTION_FAILED`。唯一正确
owner 必须位于 terminal 写 transaction 内，且同时理解 request、trigger 与 operation
现存 terminal truth；下游 projection、日志或 artifact 都不能替代这个线性化点。

F12 的重复执行来自 wake queue、periodic reconciliation 与直接 promotion 各自进入
pre-start governance。该语义属于 scheduler-local、按 Session 隔离的 signal/flight
owner；`SessionWorkLease` 只负责 attachment lifecycle，不是互斥锁。

## 2. Exact dataflow

### 2.1 F11 terminal transaction owner

1. caller 进入计划写 terminal 的既有 Host write transaction。
2. `begin_compaction_terminal_commit_in_transaction` 以 `operation_id == request
   event_id` 读取唯一 request，严格校验 canonical event class、event type、run
   identity、request payload 与 proactive/reactive trigger。
3. owner 按 run 分页读取两类 terminal。对每一行先校验
   `event_class is CANONICAL_FACT`，再 strict validate 对应 type payload，最后才按
   `operation_id` 过滤；同 type 的 non-canonical row 因此不能成为 winner，也不能
   绕过 event-class invariant。
4. fresh transaction read 没有 terminal 时返回 transaction-local typed permit；一个
   terminal 时返回 `COMPACTED` 或 `FAILED` closed result；多个 terminal 时返回
   `INVALID_MULTIPLE`。
5. permit 不离开 transaction、不跨 `await`。只有 `OPEN` caller 可继续写
   rejected/artifact descriptor/terminal/fallback/fail-close/recovery start。
6. 单 terminal late loser 只写 bounded warning 并 no-op；`INVALID_MULTIPLE` 在所有
   proactive/reactive caller 中显式抛出稳定
   `HostDurableError("compaction operation has multiple canonical terminals")`，保留已有
   truth，不追加第三 terminal，不 fallback，不 start。

### 2.2 F11 writer inventory

`tests/host/test_compaction_terminal.py` 的 AST inventory 固定验证以下 request-backed
写路径只调用同一个 shared owner：

| 模块 | request-backed terminal commit 点 | shared owner 调用数 |
| --- | --- | ---: |
| `dayu/host/dispatch.py` | invalid/exhausted close、proactive outcome commit、resume snapshot invalid、missing compactor | 4 |
| `dayu/host/engine_ingest.py` | reactive outcome commit | 1 |
| `dayu/host/proactive_compaction.py` | durable projection 复用同一 owner 判定 terminal disposition | 1（只读判定） |

hard-threshold-before-dispatch、material-source precondition 与 reactive precondition
diagnostic 没有 `CONTEXT_COMPACTION_REQUESTED`，不是 operation terminal writer；它们
保持现有 fail-close 语义，不新造第二 guard。实现没有引入通用 event framework、表、
index、migration 或 S5 identity bag。

### 2.3 F12 scheduler-local sole flight

1. `_PreStartGovernanceFlight` 仅包含 `task: Task[bool]` 与
   `rerun_requested: bool`；scheduler 只新增 `_pre_start_flights` dict 与
   `_promotion_pending_session_ids` set，没有 lock。
2. `wake_queue_promotion`、promotion drain、direct `run_queue_promotion` 与 periodic
   `reconcile_owned_sessions_once` 都只向 `_signal_pre_start_governance` 提交 signal。
3. 同 Session 已有 flight 时只把 level bit 置为 `True` 并 shield-await 同一 task；
   没有 flight 时才建立一个 critical/close-tracked task。不同 Session 使用不同 task，
   可并行。
4. flight 每个 pass 前清 bit，每个 pass 取得并释放 fresh `SessionWorkLease`；pass
   完成后从 durable truth fresh reread。bit 为真时再执行一个 pass，否则在无
   `await` 的 identity-check/delete 边界删除 flight，避免 exit-race signal 丢失。
5. RO、closing 或无 active RW attachment 的 Session 不能创建 flight。live compactor
   await 时的重复 signal 只置 bit；只有 fresh owner 重启后读取 durable incomplete
   operation，才按同 operation/snapshot/budget/next-attempt 恢复。

## 3. 修改文件

Production：

- 新增 `dayu/host/compaction_terminal.py`
- 修改 `dayu/host/proactive_compaction.py`
- 修改 `dayu/host/dispatch.py`
- 修改 `dayu/host/engine_ingest.py`（仅 reactive terminal outcome commit 收敛）

Tests：

- 新增 `tests/host/test_compaction_terminal.py`
- 修改 `tests/host/test_dispatch_scheduler.py`
- 修改 `tests/host/test_engine_ingest_mapping.py`

`dayu/host/session_attachment.py` 无需修改：现有 lease lifecycle 已足够，未把 lease
改造成 mutex。按 accepted plan，F12 design/README/docs 同步留给 S6，本 gate 未机械
修改 README 或 design。

### 3.1 总控 pre-review correction

总控 diff 审计发现
`test_pending_waiting_dispatching_worker_accept_marks_running` 的无关 fixture 曾从
HEAD 的 `_FakeWorkerFactory(accepted_handle=_CloseCountingHandle())` 意外变为
`_FakeWorkerFactory()`。直接对比 HEAD 确认长存 handle 是该旧测试维持
`RUNNING` 判定的 barrier，与 F11/F12 新契约无关。本 implementation gate
仅恢复该 fixture 一行到 HEAD 原值，没有修改测试断言、production 或其它
范围。

## 4. Owner-level 证据

- shared owner direct tests 覆盖 OPEN permit、trigger mismatch、单 terminal 精确投影、
  multiple terminal、伪 request、non-canonical terminal 在 operation filter 前失败，
  以及 writer inventory。
- proactive I0543 late accepted result：compactor await 期间先提交 FAILED，晚到 accepted
  outcome 零 artifact/descriptor/event/fallback/start，first truth 不变。
- proactive 同 operation 两 outcome contenders：accepted-first/failed-late 与
  failed-first/accepted-late 两种顺序都只有一个 terminal，loser 后无 durable 写入。
- reactive 同 pending race：两个顺序都只有一个 terminal；loser 零 rejected、artifact、
  descriptor、fallback、recovery start/fail-close。
- proactive/reactive `INVALID_MULTIPLE` 均证明不追加第三 terminal、不 fallback、不
  start，并抛稳定 `HostDurableError`。
- 真实 F12 async barrier 使用 `_BlockingAfterManifestCompactor` 冻结 manifest 后的
  provider await：periodic one-shot 在任何 wake 前只置现有 flight bit，随后多次 wake
  仍保持同 Session sole flight；barrier 内 request/provider/prepared attempt 都精确为
  1。释放后只产生一个 terminal，coalesced fresh pass 不重复 provider、request 或
  attempt，Run 在可判定 worker barrier 下保持 `RUNNING`。
- 其余 F12 tests 覆盖 seam-level 多 wake/periodic/direct coalesce、fresh no-op pass、
  exit boundary、新/不同 Session、caller cancel、scheduler close 与 fresh owner crash
  recovery。
- transient retry 测试显式取消其 periodic background source 后保留
  `attempts == 2`；compact-failure 测试使用长期存活 handle，等待
  `ATTEMPT_RUNNING` 后继续断言 `RunStatus.RUNNING`，未因并发时序弱化旧 contract。

## 5. Validation

执行环境均先运行 `source .venv/bin/activate`。

- 批准的 8 个 owner/integration 文件：`412 passed in 5.59s`。
- 全仓 `pyright`：`0 errors, 0 warnings, 0 informations`。
- pytest-cov：`410 passed, 2 deselected in 7.70s`。两个 deselected 用例是插桩下受
  既有 10ms local-lane timeout 影响的 `default_local_proxy` 测试；它们已包含在上述
  未插桩 412-test 批次并通过，没有更改或放宽断言。
- 总控 pre-review correction 后，原 owner 测试
  `test_pending_waiting_dispatching_worker_accept_marks_running`：`1 passed in 0.59s`。
- 总控 pre-review correction 后，F11/F12 关键选测（shared owner、proactive /
  reactive terminal race、`INVALID_MULTIPLE`、sole flight、真实 compactor barrier、
  exit/parallel/fresh-owner recovery、transient retry 与 compact-failure 旧契约）：
  `27 passed in 0.88s`。
- 总控 pre-review correction 后再次运行全仓 `pyright`：
  `0 errors, 0 warnings, 0 informations`。

| Production 文件 | Coverage |
| --- | ---: |
| `dayu/host/compaction_terminal.py` | 85% |
| `dayu/host/dispatch.py` | 87% |
| `dayu/host/engine_ingest.py` | 89% |
| `dayu/host/proactive_compaction.py` | 85% |
| 合计 | 87% |

静态与 diff 审计：

- `git diff --check` 通过；两个 untracked 新文件分别执行
  `git diff --no-index --check /dev/null <file>`，无 whitespace error 输出（exit 1
  仅表示文件内容有差异）。
- 比较普通 diff 与 `--ignore-all-space` diff：tracked 文件集合相同，无隐藏的越界
  文件或纯 formatter 扩 scope；统计行数差异来自大测试文件的 diff matcher 对齐。
- added production 扫描没有 `Any` / `object` 类型用法、`getattr`、`hasattr`、
  compat shim 或 extra payload。对所有新增/修改函数的 AST docstring 审计确认
  中文文档完整包含参数、返回值与异常。
- secret/credential/`Authorization`/Bearer/API key 及 provider-payload 组合扫描无
  命中；没有把 provider payload 或诊断写入新 public contract。
- 工作树文件边界审计仅包含本节列出的 production/tests 与本 artifact；未创建或
  切换分支，未 commit、push、建 PR 或执行 review。

## 6. Residual risks

- 本实现尚未经过 S4 code review，finding status 保持 `implementation未review`。
- terminal owner 使用 bounded page size 分页读取当前 Run 的 terminal facts；这是现有
  EventLog primitive 上的正确性实现，但超长 Run 的读取成本仍需在后续性能观测中
  关注，不在本 work unit 内新增 index/schema。
- F12 flight 是单进程 scheduler-local coalescing；进程级 crash 的恢复仍刻意依赖
  durable request/manifest projection 与 fresh owner reconciliation，而非跨进程锁。
- S6 仍需按 accepted plan 完成 design/README/docs 更新；本 gate 不提前同步。

结论：F11/F12 implementation 已完成并通过实现侧验证，下一 gate 为
`S4 code review`。
