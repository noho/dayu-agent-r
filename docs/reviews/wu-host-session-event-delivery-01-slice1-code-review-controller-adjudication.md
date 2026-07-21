# WU-HOST-SESSION-EVENT-DELIVERY-01 Slice 1 Code Review Controller Adjudication

## Scope

- Gate: `code-review-slice-1`
- Base: accepted plan amendment commit `33af05fa`
- AgentMiMo artifact: `docs/reviews/code-review-20260721-203720.md`
- AgentDS artifact: `docs/reviews/code-review-20260721-203851.md`
- Controller role: 只裁决 finding、open question、residual risk 与 gate；不实施修复。

## Independent review result

- AgentMiMo: PASS，0 material finding，0 open question。
- AgentDS: 4 个 low finding、3 个 open question、5 个 residual observation。
- Controller 不按多数票放行；以下逐项以当前代码、accepted plan 和设计真源裁决。

## Findings adjudication

### DS-F01 `overflow_error()` 每次构造新异常实例

Decision: `rejected-with-reason`。

`dayu/host/transient_delta.py::overflow_error()` 每次产生字段完全相同的 typed、nonretryable `HostApiError`，已经满足 public contract。设计和 plan 中“同一个 typed error”约束的是同一错误 taxonomy、detail 与 retryability，不承诺 Python object identity；当前调用方也不存在 `is` 比较。缓存并重复抛出异常对象反而会复用可变的 traceback/context 状态，因此不得为了无主的 identity 假设扩大 subscription state。

### DS-F02 `pop_next_nowait()` 丢失 terminal fence 过滤

Decision: `accepted-current-fix-required`，严重度由 reviewer 的 low 提升为 correctness finding。

直接证据：

1. accepted base 的 `HostTransientDeltaSubscription.drain_nowait()` 会丢弃 `item.run_id in _terminal_run_ids` 的已排队项；当前 `pop_next_nowait()` 直接 `popleft()`，不再执行该 owner-level fence。
2. `_watch_session_events_after()` 在 mailbox 暂时为空后会 `await self._durable_actor.call(...)`。该 await 期间，同 Run transient 可以被 `_offer()` 接受并进入 mailbox。
3. durable batch 返回后，generator 可以先标记并交付该 Run terminal；下一次 `anext()` 再从 mailbox pop 时，当前实现会把 terminal 已交付后的 stale transient 交给 caller。
4. `_offer()` 仅能拒绝 `mark_run_terminal()` 之后的新 publish，不能清除标记之前已进入 mailbox 的项，因此 reviewer 所述“mark 前 mailbox 始终已排空”的 invariant 在 durable read await 交界处不成立。

语义 owner 是 `HostTransientDeltaSubscription` 的 watcher-local terminal fence。AgentCodex 必须在 single-pop owner boundary 恢复过滤，并补 deterministic owner-contract test，证明 mailbox 中预存同 Run stale item 在 `mark_run_terminal()` 后不会成为 in-flight/被交付，同时 retained/readiness accounting 正确。修复不得进入 Slice 2 causal fence 或改变已拒绝 findings。

### DS-F03 Host close 优先 EOF，不排空已缓存 durable batch

Decision: `rejected-with-reason`。

accepted plan 明确 Host close 使 iterator 正常 EOF 并释放全部 watcher resource，不保证 drain 已读取但尚未交付的 batch。durable rows仍在 EventLog，可由新 Host/subscription 从 durable cursor 重新读取；若强制先 drain，反而会让 close latency 依赖 batch/consumer。Slice 4 exact-five contract 已明确把正常 EOF 投影为 `ITERATOR_ENDED` 并由 durable recovery 处理，因此当前顺序不是数据丢失或 contract violation。

### DS-F04 20ms Host-internal poll interval 缺少选择依据注释

Decision: `rejected-with-reason`。

该常量在 accepted base 已存在，不是 Slice 1 引入的行为；当前实现仍符合 plan 的 Host-internal bounded constant 约束。正常路径由 level-triggered readiness 立即唤醒，timeout 是 durable reconciliation/close fallback。review 未提供 CPU regression、错误 latency 或跨平台失败的直接数据；增加推测性的数值依据注释不能修复代码缺陷，也可能把未经测量的假设写成承诺。

## Open questions adjudication

1. **大量 Session 的 20ms polling CPU**：`closed-no-current-action`。这是无测量数据的容量假设，且非 Slice 1 新行为；S2 的双 opener/periodic reconciliation 验证会按 plan 覆盖其真实调度路径，但不创建未证实的性能修复。
2. **`unwatched_runtime` 测试未显式 close**：`closed-no-current-action`。该单元测试对象只持有进程内 deque/set，无 task、线程、文件或外部句柄；测试函数结束即失去全部引用，不影响 owner contract。若 hub 未来拥有外部 resource，应由届时 contract test 随 owner 变化迁移。
3. **S1 期间 Service relay 256 与 Host mailbox 512**：`closed-by-accepted-slice-sequencing`。S1 plan 明确冻结 Service relay，S4 删除它；分支不会在 S1-S3 中间态创建 PR/closeout。现有 relay drain 可能等待 queue，但不反向阻塞 Agent/Engine publisher，Host overflow 仍由 subscription mailbox owner 决定。

## Residual observations adjudication

1. **S2 cross-opener/causal fence 尚未覆盖**：`assigned-slice-2`，是 accepted dependency graph，不是 S1 finding。
2. **Service relay 过渡态**：`assigned-slice-4`，分支只在完整 WU 后发布，不构成可交付 residual。
3. **三个 allocation/cancellation 场景合并在一个 test**：`rejected-with-reason`。每个场景有独立 setup/assertion，review 未证明共享状态掩盖失败或生产 contract 未覆盖；仅为风格建议。
4. **close 时清空 `_terminal_run_ids`**：`rejected-with-reason`。close 后 subscription 不再参与 fanout/交付，清空全部 watcher-local retained state 是正确 resource cleanup，不存在 close 后读取该私有集合的 caller。
5. **512/4 在 packaged config 与测试中重复出现**：`rejected-with-reason`。packaged default 与显式无 hidden fallback 的 construction fixtures 是不同 owner 的契约断言；共享常量会把独立验证耦合回生产默认值，削弱 drift detection。

## Gate decision

Decision: `fix-required`。

- Accepted finding: `DS-F02` only.
- Next gate: `code-review-fix-slice-1`。
- Next owner: AgentCodex。
- Required closure: AgentCodex 修复并验证后，AgentMiMo 与 AgentDS 作为原 reviewers 独立并行执行 `$deepreview --base 33af05fa` re-review；两路都必须确认 DS-F02 已关闭且无新增 material finding，Controller 才能 accepted-commit Slice 1。
- Blocking open questions: `None`。
