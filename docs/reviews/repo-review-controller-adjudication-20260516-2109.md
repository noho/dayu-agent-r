# Full Repository Deepreview Controller Adjudication - 2026-05-16 21:09

## Gate

当前 gate：Phase 8 ready-to-open-draft-PR 前追加 `/deepreview --all` 闭环。

Review artifacts：

- `docs/reviews/repo-review-20260516-2052.md`（AgentMiMo 过程 artifact）
- `docs/reviews/repo-review-20260516-2105.md`（AgentMiMo 补写 artifact，内容与 2052 同一轮）
- `docs/reviews/repo-review-20260516-2059.md`（AgentDS 独立全仓 artifact）

Truth docs：

- `docs/host/design.md`
- `docs/host/implementation-control.md`
- `dayu/README.md`
- `dayu/host/README.md`
- `dayu/runtime/` 层中立 runtime 约束

## Controller Verdict

本轮全仓 review 暂不进入 ready gate commit；需要先完成一个受控 fix 包，再做 MiMo / DS re-review。

Codex fix 只允许修 Host/runtime 中直接证据成立、风险可控、不会触碰 Engine 的 accepted findings。Engine 层 finding、
schema version hardening、后续 phase ownership 项不混入当前 Phase 8 readiness fix。

## Accepted Current Fix Findings

### DR-ALL-A1: `RuntimeFileLock` 同实例重叠获取会泄漏 context manager token

来源：DS finding 1 / 3。

裁决：accepted current fix。

理由：`RuntimeFileLock.__enter__` 只覆盖 `_active_token`，未拒绝同一 lock 实例嵌套 `with`；`acquire()` 也未感知已有
active token。同一第三方 `FileLock` 可能被重复获取，外层 token 被覆盖后无法由外层 `__exit__` 释放。该问题位于
`dayu.runtime`，不涉及 Host 治理语义，适合当前修复。

修复要求：

- 同一 `RuntimeFileLock` 实例存在未释放 active token 时，`acquire()` / `__enter__` 必须 fail fast。
- 手动 token release 后必须允许同一 lock 实例再次 acquire。
- 增加嵌套 `with`、context 内 manual acquire、manual acquire 后 context enter、manual release 后 reacquire 测试。

### DR-ALL-A2: `HostEventView` 未暴露 `event_class`

来源：DS finding 2。

裁决：accepted current fix。

理由：设计真源明确 `HostEventView` 是 EventLog row 的公共视图映射，应携带 event type / class；preview event 可以进入
Host event stream，但不得被调用方误解为 canonical fact。当前 public view 只有 `event_type`，无法区分
`canonical_fact` / `preview` / `diagnostic` / `projection_signal`，与 `docs/host/design.md` §16 不一致。

修复要求：

- 在 public API 增加稳定的 public event class 类型，并让 `HostEventView` 携带 `event_class`。
- `stream_run_events` 从 `EventLogRow.event_class` 映射该字段。
- 增加包含 preview / diagnostic 或至少非 canonical event row 的 stream regression，证明 caller 可区分 class。
- 更新 `dayu/host/README.md` 对 `HostEventView` 字段说明。

### DR-ALL-A3: `terminal_closeout_in_transaction` 未校验 Attempt / Run terminal status 配对

来源：DS finding 4。

裁决：accepted current fix。

理由：terminal closeout helper 是多个入口共享的 durable primitive。当前 `_validate_terminal_input` 只分别校验 attempt
status 和 run status 是否可转 terminal event type，但未拒绝 `ATTEMPT_SUCCEEDED` 搭配 `RUN_FAILED` 这类交叉不一致输入。
虽然现有调用方通常传正确配对，primitive 自身应阻止错误组合写入双事实。

修复要求：

- 在 `_validate_terminal_input` 增加 Attempt / Run terminal status compatibility check。
- 覆盖 succeeded / failed / cancelled / lost 的合法配对与至少一个非法配对。

### DR-ALL-A4: after-commit callback 链在第一处异常中断

来源：DS finding 5。

裁决：accepted current fix。

理由：`HostTransactionRunner.run_write(..., after_commit=(...))` 的语义是 durable commit 后 best-effort 执行回调。当前
`_run_after_commit` 在第一个 callback 失败时立即抛出，后续 callback 不会被尝试，可能导致多个 post-commit wakeup /
notification 只执行前缀集合。durable commit 已完成，后续 callback 应至少都被尝试。

修复要求：

- `_run_after_commit` 应尝试全部 callbacks。
- 若存在失败，保留第一个失败的 `callback_index` 并在循环后抛 `HostAfterCommitError`。
- 增加测试证明第一个 callback 失败时后续 callback 仍被调用，且异常 index 仍指向第一个失败 callback。

### DR-ALL-A5: `WaitPoller` adapter 异常捕获过窄

来源：DS finding 9。

裁决：accepted current fix。

理由：`WaitPoller` 是外部 poll adapter 边界；adapter 实现可能抛 `ValueError`、`TimeoutError` 或 provider client
exception。当前只捕获 `RuntimeError`，单个 adapter 异常会击穿整轮 poll，导致后续 wait record 不被观察。poller 对外部
adapter 应隔离单条失败。

修复要求：

- `WaitPoller.poll_once` 对 `poll_wait` / `abandon_wait` 捕获普通 `Exception`，但仍不得吞 `BaseException`。
- 增加测试：一个 adapter 抛非 `RuntimeError` 时，本轮继续处理后续 wait record，`adapter_errors` 增加。

## Rejected Findings

- MiMo finding 1 / DS finding 20：`record_idempotent_result` 并发 INSERT。当前所有调用处运行于 `HostTransactionRunner.run_write`
  的 `BEGIN IMMEDIATE` write transaction 内，同一 SQLite writer 被序列化；review 未证明同一事务边界内存在 read-then-write race。
- MiMo finding 3：`cancel_session_runs` 单事务原子取消。该行为与 session-scope cancel 的 all-or-none 语义一致；不是当前缺陷。
- MiMo finding 4：Host public API 依赖 Engine contracts。`dayu.host` 可在 `UI -> Service -> Host -> Engine` 方向依赖 Engine
  public contracts，这是当前架构约束允许的稳定边界。
- MiMo finding 6：StrEnum 使用 `is`。当前比较对象来自 typed enum row codec / EngineEvent type，不是 raw string；无直接失败路径。
- MiMo finding 12：`dayu.host` 缺少弱类型守卫测试。`tests/host/test_weak_typing_guard.py` 已覆盖 `dayu/host/`。
- DS finding 23 / 24：重复 schema validation、未使用常量。低价值 cleanup，不构成 correctness / stability blocker。

## Deferred With Owner

- MiMo finding 2：scheduler close cancellation 后 Run 仍 active。当前 scheduler close 设计只传播 cancel signal 并取消 active task；
  RECOVERING / worker-lost reconciliation 归 Phase 11 owner。
- MiMo finding 5：`LaneController._release_token` 二次 cancellation 下内存 token 清理。归 runtime cancellation hardening owner；当前
  Phase 8 不改 lane cancellation state machine。
- MiMo finding 7：`HostTransactionRunner.run_write` 同步 sleep 文档。归 durable docs hardening owner；当前调用方知道该 runner 为同步 API。
- MiMo finding 8 / 9：schema CHECK 约束 hardening。需要 schema version bump，归后续 schema hardening owner，不混入 Phase 8 readiness。
- MiMo finding 10：rollback 失败日志。归 durable diagnostics hardening owner。
- MiMo finding 11：`api.py` docstring 精确性。可随 A2 public event class 更新一并修正最小必要文本，否则不单独修。
- DS finding 6 / 7 / 13 / 15 / 16 / 18：Engine / OpenAI runner / parser / Agent findings。修改 Engine 代码需单独用户确认，
  归 Engine hardening gate owner。
- DS finding 8：awaiting accepted ack 重放时 wait record 当前状态重校验。涉及等待幂等语义，归 Phase 7 / Phase 11 wait lifecycle
  hardening owner。
- DS finding 10 / 14：poller LIMIT / CANCELLED abandon 退避。归 Phase 15 / production polling scale owner。
- DS finding 11 / 12 / 17 / 19 / 21 / 22：token immutability、sync accept barrier、marker restore logging、CAS return
  type、continuity index、minimal read model multi-consumer reset。均为后续 hardening / scale / API consistency owner。

## Codex Fix Scope

允许修改：

- `dayu/runtime/filelock.py`
- `tests/runtime/test_filelock.py`
- `dayu/host/api.py`
- `dayu/host/read_api.py`
- `dayu/host/__init__.py`
- `dayu/host/durable/run_transition.py`
- `dayu/host/durable/transaction.py`
- `dayu/host/wait_adapter.py`
- `tests/host/test_public_event_stream.py`
- `tests/host/test_package_exports.py`
- `tests/host/test_run_attempt_transitions.py`
- `tests/host/test_durable_transaction.py`
- `tests/host/test_wait_adapter_polling.py`
- `dayu/host/README.md`
- `docs/reviews/repo-review-fix-codex-20260516.md`

禁止修改：

- `dayu/engine/`
- `dayu/fins/`
- `dayu/service/`
- `dayu/ui/`
- command/admission/dispatch state machine，除非测试 import / public event view 必要。
- schema version / DDL。
- Git commit / push / PR。

## Required Validation

```bash
source .venv/bin/activate
pytest tests/runtime/test_filelock.py tests/host/test_public_event_stream.py tests/host/test_package_exports.py tests/host/test_run_attempt_transitions.py tests/host/test_durable_transaction.py tests/host/test_wait_adapter_polling.py -q
pytest tests/host tests/runtime -q
python -m pyright dayu/ tests/ utils/
git diff --check
```
