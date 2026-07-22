# WU-CTX-04 Slice 3 review fix（AgentCodex）

## Gate metadata

- work unit：`WU-CTX-04`
- slice：`3/3`
- gate：code review fix
- baseline：accepted Slice 2 commit `4ca0810b27eded188e4f9aae54756a871eb371ed`
- adjudication：`docs/reviews/wu-ctx-04-slice-3-code-review-controller-adjudication.md`
- accepted findings：`CTRL-S3-001`、`CTRL-S3-002`、`CTRL-S3-003`
- completion status：三个 accepted findings 均已修复并有直接回归证据；等待双路 re-review 与
  Controller 最终裁决
- commit / push：未执行
- artifact path：`docs/reviews/wu-ctx-04-slice-3-review-fix-codex.md`

## First-principles 与 semantic owner 判断

三个 finding 的动机均成立，且严重性与 Controller 裁决一致。

- execution-owner physical cancel 是旧 scheduler 对自己 stable local worker 的 continuation
  责任；其进度不能由 attachment-authorized Session promotion 或事务外 compactor await 决定。
  正确 owner 是 `HostDispatchScheduler` 的独立 critical periodic task，不是恢复 global scan。
- `CANCEL_REQUESTED.reason` 已由 run-transition canonical fact owner 严格解析；dispatch 若生成
  `durable_cancel_requested` 会制造第二语义真源。正确边界是 run-transition typed projection，
  dispatch 只消费已验证值。
- exact identity VALUES 是 state SQL owner 的实现细节。合法完整输入不应因单 statement bind
  上限被拒绝；正确修复是在同一 caller transaction 内透明分批，而不是增加 public capacity
  contract 或固定超限错误。

本轮没有恢复 workspace-wide cancelling scan，没有增加 LRU/size guard、capacity public 限制、
兼容 wrapper/default、raw payload 解析或第二 terminal producer。

## Finding mapping

### CTRL-S3-001 — 已修复

**Production owner 修复**

- `dayu/host/dispatch.py` 新增独立
  `_active_worker_cancel_reconciliation_task` 与
  `_active_worker_cancel_reconciliation_loop()`。该 loop 只按
  `dispatch_poll_interval_seconds` 调用 exact owner one-shot，不进入
  `reconcile_owned_sessions_once()`、promotion 或 proactive compactor await 链。
- task 通过 `_start_critical_task(...)` 以稳定 component
  `active_cancel_owner_reconciliation` 接入 shared health supervisor。
- scheduler open 在启动 Session reconciliation 前启动 owner cancel task；后续 open step 失败时
  既有 `except BaseException -> scheduler.close()` 会取消并 await 已启动 task。
- scheduler close 的 mandatory background task 集合显式包含 owner cancel task，并与 Session
  reconciliation task 一起先 cancel、后逐个 await；lane close、Host instance `STOPPED` 与
  `_close_cleanup_done` 顺序未改变。
- `_owned_session_reconciliation_loop()` 现在只拥有 attachment-authorized new-work reconciliation。

**直接测试**

- `test_owner_cancel_periodic_task_progresses_while_session_reconcile_blocks` 用 barrier 确定性阻塞
  Session reconciliation；另一个 registry 接受 durable cancel 后，独立 periodic owner task 仍把
  canonical reason 传播到旧 local handle。随后 `scheduler.close()` 必须收口两个 task，阻塞 task
  可观察到 cancellation。
- `test_owner_cancel_task_is_joined_when_later_scheduler_open_step_fails` 在 owner task 启动后注入后续
  open step 失败，断言 failed-open 返回前 task 已 done。

**修正旧 artifact 表述**

原 implementation artifact 的“最多一个 interval”遗漏了 owner poll 与 Session compactor 共用 task
的阻塞窗口。修后 physical propagation 不再等待 Session reconciliation/proactive compactor 返回；
正常 cadence 是独立 owner task 的下一次 poll 加 exact durable transaction 执行时间。数据库持续失败
会由 critical supervisor 把 execution health 置为 unavailable，而不是静默跳过。

### CTRL-S3-002 — 已修复

**Production owner 修复**

- accepted plan 的 `OwnedAttemptCancelTarget(identity, cancel_request_event_id)` 字段保持不变。
- `dayu/host/durable/run_transition.py` 新增
  `OwnedAttemptCancelDelivery(target, reason)` 与
  `read_exact_owned_attempt_cancel_deliveries(...)`。同一个 strict linked-event validator 现在返回
  已验证的 exact six-field payload `reason`，typed delivery 是该 canonical 业务事实的唯一对外投影。
- `read_exact_owned_attempt_cancel_targets(...)` 继续提供 accepted target contract，并复用同一 strict
  validation/source of truth；没有暴露 EventLog raw row 或 payload。
- `dayu/host/dispatch.py` 只读取 typed deliveries，把 `delivery.reason` 交给
  `ActiveCancelMessage`；删除 `_ACTIVE_CANCEL_OWNER_RECONCILE_REASON` 与
  `durable_cancel_requested`。

**直接测试**

- `test_cross_opener_cancel_reaches_detached_execution_owner` 继续走真实 public 双 opener 路径，现同时
  断言 local cancellation token 与 worker `on_cancel(reason)` 均收到
  `cross_opener_cancel`，而不是 registry/open 时序相关的替代值。
- 独立 periodic task 回归同时断言 owner-level hook 收到 producer 的 canonical `user_stop`。

### CTRL-S3-003 — 已修复

**Production owner 修复**

- `dayu/host/durable/state.py` 在执行任何 batch 前对完整 tuple 先校验 owner id、每个 identity 的四个
  non-empty 字段以及全局 duplicate；empty tuple 继续返回空结果。
- SQLite 官方 limits 文档说明 3.32.0 之前默认
  `SQLITE_MAX_VARIABLE_NUMBER=999`。模块以该 legacy default 作为保守 statement 参数预算，按
  “每 identity 5 个 bind + 每 statement 1 个 owner bind”推导私有 batch size
  `(999 - 1) // 5 = 199`，没有形成 public capacity 限制：
  <https://www.sqlite.org/limits.html#max_variable_number>。
- 每个 batch 仍使用相同 `HostTransaction`，global `request_order` 从原 tuple 的绝对下标生成；batch
  内 `ORDER BY request_order` 后按连续 batch 追加，因此过滤 stale/wrong-owner 项后仍严格保持全局
  输入顺序。没有 Session/workspace scan。

**直接测试**

- `test_exact_owned_cancel_query_batches_preserve_global_order_and_filter_stale` 创建 205 个真实 typed
  cancel targets，以逆序输入跨越 199 条边界，并分别在不同 batch 注入 wrong dispatch owner 与 stale
  current Attempt。断言完整 typed output 精确等于过滤后的全局输入顺序。
- 既有 terminal truth、wrong owner、stale execution/current Attempt、duplicate 与 strict bad-link
  fail-closed cases 全部继续通过。

## Changed files

本 fix 新增或修改且只修改以下路径：

- `dayu/host/dispatch.py`
- `dayu/host/durable/state.py`
- `dayu/host/durable/run_transition.py`
- `tests/host/test_active_cancel_dispatch.py`
- `tests/host/test_run_attempt_transitions.py`
- `tests/host/test_public_session_attachment.py`
- `docs/reviews/wu-ctx-04-slice-3-review-fix-codex.md`

工作区中其它 production/test/README/control/review 变更均为本 fix 进入前已有的 Slice 3 状态，本轮没有
修改、回滚、格式化或 stage 它们。`tests/host/test_open_host_runtime.py` 不需要新增 delta。

## Validation

所有有效命令均在仓库根目录并先执行 `source .venv/bin/activate`。

- targeted Ruff：fix 允许的 production/tests Python paths，`All checks passed!`。
- targeted pyright：fix 允许的 production/tests Python paths，`0 errors, 0 warnings, 0 informations`。
- 新增/直接最小 cases：`7 passed`。
- 三个直接受影响测试文件：`109 passed`。
- scheduler/open/terminal producer 扩展回归：`246 passed`。
- Slice 3 focused matrix（含 Controller amendment tests）：`438 passed`，只有 3 个第三方 `edgar`
  deprecation warnings。
- terminal producer manifest：
  `tests/host/test_terminal_post_commit.py::test_static_terminal_producer_manifest_is_exact`，`1 passed`。
- 全量 pyright：`python -m pyright dayu/ tests/ utils/`，
  `0 errors, 0 warnings, 0 informations`。
- canonical 全量 pytest：
  `pytest tests/contracts tests/cli tests/documents tests/fins tests/tools tests/host tests/runtime tests/service tests/engine -q`，
  `5593 passed, 11 skipped, 6 deselected`，只有 3 个第三方 `edgar` deprecation warnings。
- coverage 测试面：`3542 passed, 9 skipped, 6 deselected`；相对 accepted plan baseline
  `974f9e1686f6e26f96830cd3478edc9d0d686c45` 的 21 个 modified production Python 文件逐文件
  `--fail-under=80` 全部通过。fix owner 文件：`dispatch.py` 90%、`run_transition.py` 93%、
  `state.py` 88%；全集合最低 `session_execution.py` 81%。
- `git diff --check`：通过。
- stale/invariant grep：以下 production/test stale shapes 全部零命中：
  - `StartupRecovery|read_non_terminal_runs\(|read_cancelling_runs\(`；
  - 已删除 proactive operation count 字段/常量/reason；
  - `dayu.runtime.native_mutex` 对 Engine/Host/Service/UI/Fins 的反向 import；
  - `durable_cancel_requested|_ACTIVE_CANCEL_OWNER_RECONCILE_REASON`。

补充环境证据：裸 `pytest -q` 会额外收集既存
`workspace/tmp/r06-base-9c07b88d/tests`，因其与正式 `tests.conftest` 同 module name 产生 pytest
`ImportPathMismatchError`。本轮没有删除或改写用户临时目录；随后按 accepted plan 的 canonical 全量目录
运行并取得上述 5593 passed。该收集冲突不是产品测试失败。

## README / docs decision

- README：`NO_UPDATE`。现有 `dayu/host/README.md` 已准确承诺 scheduler periodic reconcile 只按本
  opener active worker exact identities 查询、且不做 workspace-wide scan；它没有承诺 owner poll 与
  Session promotion 共用 task，也没有记录错误 reason。独立 task 与 typed reason 是内部 owner
  correctness 修复，不改变用户可见安装、CLI、分层或稳定 public contract。
- design/control/accepted plan/initial reviews/implementation artifact：按用户与 Controller 禁止项保持
  不变。
- 本文件是唯一新增 fix artifact。

## Residual risks / uncovered areas

- **existing accepted runtime boundary**：独立 task 消除了 compactor await 的无界阻塞，但 physical
  propagation 仍依赖 configured poll interval、SQLite transaction 可用性与 opener event loop 调度；
  durable failure由 health supervisor fail closed。分类：`covered by existing runtime health owner`。
- **external execution boundary**：本地 token/hook 传播不等价于远端 provider physical exactly-once
  停止；迟到结果继续由既有 identity/terminal fence 拒绝。分类：`assigned to existing provider boundary`。
- **custom SQLite build/runtime limit**：batch 以 SQLite 历史默认 999 为支持环境的保守依据；若未来
  明确支持把 connection variable limit 主动降到 999 以下的定制 runtime，应由独立 runtime-policy WU
  增加 connection-specific limit owner，不应在本 query 增加 public capacity 拒绝。分类：
  `assigned to later work unit if support scope expands`。
- **workspace tmp collection**：裸 pytest 的重复 conftest 冲突属于既存临时快照清理，不影响 canonical
  suite。分类：`uncovered environment hygiene outside this fix allowlist`。

没有 blocking open question，没有未分类 finding。下一 gate 仅为 AgentMiMo / AgentDS 基于 fix 后完整
workspace diff 的双路 re-review 与 Controller 裁决；本轮按要求停在 fix complete，不 commit / push。
