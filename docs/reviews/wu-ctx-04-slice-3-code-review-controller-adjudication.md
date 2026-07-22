# WU-CTX-04 Slice 3 Code Review Controller Adjudication

## Gate metadata

- work unit：`WU-CTX-04`
- slice：`3/3`
- baseline：accepted Slice 2 commit
  `4ca0810b27eded188e4f9aae54756a871eb371ed`
- implementation artifact：
  `docs/reviews/wu-ctx-04-slice-3-implementation-codex.md`
- reviewer artifacts：
  - `docs/reviews/wu-ctx-04-slice-3-code-review-mimo.md`
  - `docs/reviews/wu-ctx-04-slice-3-code-review-ds.md`
- Controller decision：`needs-fix`
- blocking open questions：None
- accepted findings：3
- rejected observations：3

## Outcome first

两路 reviewer 均建议 pass，但该结论不成立。Controller 基于直接调用链确认一个 High
correctness finding：execution-owner cancel reconcile 与可进入事务外 proactive compactor 的
Session reconciliation 共用同一个周期 task，后者可长期 await，从而阻断后续 physical cancel
poll，违反设计真源“在有界时间内 reconcile 并作用于 local worker”的要求。

Controller 另确认一个 Medium semantic-owner finding：run-transition owner 已严格解析 canonical
`CANCEL_REQUESTED.reason`，但随后丢弃该值；dispatch owner 改用
`durable_cancel_requested` 常量通知 token/hook，使同一 public cancel 在同 opener 与跨 opener
场景产生不同 cancel reason。该下游重写违反本仓库的语义唯一 owner 约束。

DS 的 SQLite bind 参数可移植性观察成立，但建议的固定超限拒绝不是最佳修复；应在同一 caller
transaction 内对有界 identity 输入做安全分批，并保持全局输入顺序。DS 的 workspace-wide
periodic safety scan、LRU/size guard 和测试 helper 观察均不采纳。

## Accepted findings

### CTRL-S3-001 — High — execution-owner cancel poll 被不相关的 proactive compactor 阻塞

**直接证据**

- `dayu/host/dispatch.py:3657-3678` 的
  `_owned_session_reconciliation_loop()` 每轮先调用
  `reconcile_active_worker_cancels_once(...)`，随后在同一个 task 中 `await
  reconcile_owned_sessions_once(...)`。
- `dayu/host/dispatch.py:3165-3183` 对每个 active RW Session 顺序 `await
  _run_queue_promotion_with_lease(...)`。
- 该路径进入 `dayu/host/dispatch.py:1987-1996` 的 `await
  run_compaction_attempt(...)`；`dayu/host/compaction_operation.py:800-808` 最终 await
  外部 compactor proposal。该 provider seam 没有由 execution-owner cancel poll 拥有的完成
  deadline；仅靠 cooperative cancellation token 不能证明它及时返回。
- design truth `docs/host/design.md:782` 要求旧 execution scheduler 在有界时间内 reconcile
  durable cancel 并作用于自己的 local worker；accepted plan Section 5.8 则要求 scheduler 每个
  `dispatch_poll_interval_seconds` 执行 exact owner reconcile。

**反例与影响**

同一旧 opener 可在 Session A 持有一个 stable active worker，同时在 Session B 持有 RW
attachment 并进入慢/不返回的 proactive compactor。Session A detach 后由 fresh opener 接受
cancel；旧 opener 的共享 loop 正阻塞在 Session B compactor，后续 exact owner poll 不再执行，
Session A 的 token/hook 可无限延迟。caller watchdog 可以写 durable `CANCELLED`，但不能代替旧
execution owner 执行 physical propagation。

**Required fix**

- execution-owner cancel reconcile 必须拥有独立、受 health supervisor 管理的 periodic task；
  不得与 Session promotion/governance 的任何事务外 await 共用进度。
- scheduler open/failed-open/close lifecycle 必须启动、监督、取消并 await 该 task；不得泄漏 task
  或改变 Host close 的 mandatory barrier。
- 原 Session reconciliation loop 只拥有 attachment-authorized new-work reconciliation。
- 增加确定性测试：阻塞 Session reconciliation/proactive work 时，独立 owner poll 仍按 exact
  identity 传播 cancel；close 仍能完整收口两个 task。
- implementation artifact 中“最多一个 interval”的表述必须在 fix artifact 中按最终真实调度
  边界更正，不得用不相关 compactor 的返回时间充当 cancel poll 上界。

### CTRL-S3-002 — Medium — 跨 opener token/hook 丢失 canonical cancel reason

**直接证据**

- `dayu/host/durable/run_transition.py:2522-2539` 从 linked `CANCEL_REQUESTED` payload 读取并
  验证 `reason` 非空，但 validator 返回 `None`，`OwnedAttemptCancelTarget` 只保留 identity 与
  event id。
- `dayu/host/dispatch.py:248` 新建 `_ACTIVE_CANCEL_OWNER_RECONCILE_REASON =
  "durable_cancel_requested"`；`dayu/host/dispatch.py:3122-3129` 将该常量写入
  `ActiveCancelMessage.reason`，没有从已验证 event 投影 canonical reason。
- 同 opener fast path 由 `dayu/host/command.py` 直接传递 admission target 的用户 cancel reason；
  因此相同 public command 的 reason 取决于 registry 是否恰好属于 caller opener。
- `ActiveWorkerRegistry.cancel()` 把该字段写入 Host cancellation token 并传给
  `LocalWorkerHandle.on_cancel(reason)`；token reason 还可被
  `dayu/host/dispatch.py:4965-4979` 投影成 synthesized `RunCancelledData.reason`。

**反例与影响**

用户以 reason `cross_opener_cancel` 取消旧 opener worker。caller registry miss 后，旧 owner
收到的 token/hook reason 变成 `durable_cancel_requested`；同一业务事实出现两套值，custom worker
或诊断消费者无法区分用户原因，且当前 public cross-opener 测试只断言 `cancel_count`，没有断言
reason。

**Required fix**

- canonical cancel reason 继续由 run-transition cancel fact owner 解析、校验并做 typed 投影；
  dispatch 不得解析 raw payload，也不得生成替代业务 reason。
- accepted plan 要求的 `OwnedAttemptCancelTarget(identity, cancel_request_event_id)` 精确输出保持
  不变；可由 cancel owner 提供 companion typed delivery/reason projection，避免扩大 raw row
  暴露面。
- owner reconcile 构造的 `ActiveCancelMessage.reason` 必须等于 linked canonical reason；删除
  generic reconcile reason 常量。
- cross-opener public/owner-level 测试必须同时断言 token reason 与 handle hook reason。

### DS-M-01 / CTRL-S3-003 — Medium — dynamic VALUES 依赖 SQLite bind 上限

**直接证据**

`dayu/host/durable/state.py:2246-2258` 为每个 identity 生成五个 bind 参数，再追加一个 owner
参数；`OpenHostOptions.lane_capacity` / `HostLocalExecutionOptions.lane_capacity` 只要求正整数，
没有与 SQLite build 的 `MAX_VARIABLE_NUMBER` 建立 contract。当前环境 SQLite 3.51.3 的编译值是
250000，但受支持 Python 3.11 环境不能把该本机构建值当成 portable contract。

**Controller correction**

DS 建议固定拒绝大于约 200 的合法 identity tuple，会把 SQLite 实现限制升级成新的 public/runtime
容量限制，并引入未经设计确认的 magic cap，因此不采纳该修法。根因仍成立：有效 lane 配置不应在
cancel correctness path 偶然触发 `too many SQL variables`。

**Required fix**

- 在同一个调用方 read transaction 内按模块级、带依据的安全 batch size 查询全部 identities；
  duplicate/non-empty 校验仍覆盖完整输入 tuple。
- 合并结果必须严格保持全局输入顺序；不得按 Run/Session 重排，不得拆成 workspace scan。
- 增加超过单 batch 的直接测试，证明多 batch 仍保持顺序、owner/stale semantics 与 typed output。

## Rejected observations

### DS-L-01 — rejected — 恢复 workspace-wide periodic safety scan

accepted plan 明确删除 workspace-wide periodic cancelling scan。caller/fresh attach 只做 target
Session tick；execution owner 的 periodic correctness path 是 exact local identity reconcile。
用“可能存在边缘 bug”恢复全局 scan 既无直接失败证据，也会重新引入已禁止的权限与扫描边界。

### DS-L-02 — rejected — 对 target Session set 使用 LRU/size guard

观察没有证明当前内存风险；set 只保存本轮尚未消费的唯一 target Session。LRU 或拒绝会丢失已提交
cancel 的 target wake，直接削弱 correctness。若未来需要 admission/backpressure，必须由明确的
队列容量 contract 拥有，不能在本 Slice 添加静默丢弃。

### DS-L-03 — evidence-invalid — monkeypatch helper 未恢复

DS 自己的直接证据已经确认测试用 `try/finally` 调用 `monkeypatch.undo()`，pytest fixture 也会在
case teardown 恢复；该条没有失败条件，不是 finding。

## Reviewer conclusion adjudication

- AgentMiMo：`pass`、0 actionable findings。其 strict query、digest、stale identity、唯一
  terminal producer、target wake 与 scope 审查证据保留；但它把同一 fixed timestamp 等同于
  cancel poll 独立进度，未沿 `reconcile_owned_sessions_once -> proactive compactor` await 链构造
  反例，也未核对 canonical reason 被 validator 丢弃，故最终 pass 结论被 Controller 覆盖。
- AgentDS：`pass`、1 Medium + 3 Low。接受 M-01 的 portability root cause但更正修法；其余三条
  驳回。DS 同样漏掉 CTRL-S3-001/002，且“最多一个 poll interval”的 residual risk 复述不成立。

## Fix gate exit criteria

- CTRL-S3-001、CTRL-S3-002、CTRL-S3-003 全部有 production-owner 修复和直接回归测试。
- 不修改 design、accepted plan 或 Controller-owned control artifact；不增加 compatibility
  wrapper/default/global scan。
- targeted ruff、受影响 focused tests、terminal producer manifest、全量 pyright、全量 pytest、
  per-file coverage 与 stale grep重新通过。
- AgentMiMo 与 AgentDS 基于 fix 后完整 workspace diff做双路 re-review；Controller 最终裁决后才可
  创建 accepted Slice 3 commit。
