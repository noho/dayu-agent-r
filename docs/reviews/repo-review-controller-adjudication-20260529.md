# Full Repository Review Controller Adjudication 20260529

## Gate

PR 69 已达到 `draft-PR-pass` 后的用户追加全仓 review gate。总控职责是整合 AgentMiMo 与 AgentDS 的全仓
`/deepreview --all` 结果，裁决哪些 finding 阻断当前 gate，哪些应作为后续治理风险追踪。

## Inputs

- AgentDS: `docs/reviews/repo-review-20260529-132719.md`
- AgentMiMo: `docs/reviews/repo-review-20260529-133403.md`
- 设计真源: `docs/host/design.md`
- 总控文档: `docs/host/implementation-control.md`

## Accepted Blocking Findings

### FR-F1 Audit / Tool Trace JSONL 写入不是 projection 幂等操作

裁决：accepted blocking。

直接证据：

- `dayu/host/audit.py:231-239` 先追加 audit JSONL，再写 audit sink marker。
- `dayu/host/tool_trace.py:317-324` 在同一 projection transaction 中写 hot row 后追加 cold JSONL。
- JSONL 文件写入不参与 SQLite rollback；进程或 transaction 在 DB commit 前失败时，重放同一 event 会再次追加同一 JSONL line。

第一性原理裁决：Phase 13 的 Audit / Tool Trace 目标是“committed EventLog 的可追溯 projection sink”，至少必须保证
同一 EventLog row 重放不产生重复外部行。当前实现把文件 append 当作不可回滚副作用，但没有文件侧幂等检查，违反
Host durable facts 可恢复与审计链可追溯目标。

修复要求：

- 不引入 payload reader、timeline replay 或 public API 扩张。
- 保持 Audit / Tool Trace 仍只消费 committed EventLog，不反向写 governance truth。
- 优先实现 JSONL append 的文件侧幂等：在相同 file lock 保护下，如果目标 JSONL 中已存在同一 `line_digest`
  或同一稳定 source key（Audit `event_id`，Tool Trace `event_id` / `cold_trace_ref`），不得重复 append。
- 增加可复现测试：模拟“JSONL 已有 line 但 DB marker/hot row 缺失”的 replay 场景，确认 catch-up 后 JSONL
  仍只有一行，且 DB marker/hot row 被补齐。

### FR-F2 Outbox projection read state 用全局 EventLog watermark 判定 LAGGED

裁决：accepted blocking。

直接证据：

- `dayu/host/durable/outbox.py:403` 将 checkpoint 与 `_latest_event_sequence(transaction)` 比较。
- `_latest_event_sequence` 在 `dayu/host/durable/outbox.py:722-738` 查询全表 `MAX(event_sequence)`，不限定
  Outbox terminal canonical fact。

第一性原理裁决：Outbox public read state 应表达 Outbox terminal projection 是否追上自身关心的 committed facts。
把无关 EventLog row 算作 lag 会误导调用方，属于 Phase 13 public Outbox API correctness 问题。

修复要求：

- 改为比较 checkpoint 与最新 Outbox terminal canonical fact sequence，而不是全局 EventLog watermark。
- 增加测试：checkpoint 已追上 terminal fact 后，再追加非 terminal EventLog row，projection state 仍为 `CAUGHT_UP`。

### FR-F3 Outbox drain 缺 per-item pending CAS

裁决：accepted blocking。

直接证据：

- `dayu/host/durable/outbox.py:418-491` drain 首次调用选出 item 后逐条 `UPDATE`。
- UPDATE 条件只按 `item_id`，缺少 `AND item_state = 'pending'`。

第一性原理裁决：Outbox drain 是 Phase 13 对外投递确认 API。即使当前部署默认单 drainer，durable helper 不应允许
不同 drain request 静默覆盖同一 item 的 drained metadata。

修复要求：

- UPDATE 增加 pending-state CAS。
- 对 CAS miss 给出结构化、可测试行为；不得静默覆盖已 drained row。
- 增加并发/顺序模拟测试：第二个不同 `drain_request_id` 不得覆盖第一轮 drained metadata。

### FR-F4 SSE parser 对非空 choices 全不可解析但 usage 合法的 chunk 不应静默成功

裁决：accepted blocking。

直接证据：

- `dayu/engine/runners/openai/sse_parser.py:400-437` 对非 dict choice 只 warning；当 `has_valid_usage=True`
  时不会发 `RunnerProtocolErrorData`。

第一性原理裁决：usage-only chunk 可以合法，但“非空 choices 全不可解析”不是 usage-only chunk。Engine 必须把 provider
协议异常显式暴露给 Host，而不是只上报 usage 后继续。

修复要求：

- 当 `choices` 非空且没有任何 dict choice 时，无论 usage 是否合法，都发 protocol error 并终止。
- 保留真正 usage-only chunk 的合法路径。
- 增加 SSE parser focused test。

### FR-F5 startup orphan recoverable closeout 对 CANCELING expected status 的前置条件不一致

裁决：accepted blocking。

直接证据：

- `StartupOrphanCloseInput` 路径允许 `expected_run_status=CANCELLING` 进入 recoverable closeout。
- `dayu/host/durable/state.py:3165` 的 `mark_running_run_recovering_row` 固定要求 run status 为 `RUNNING`。

第一性原理裁决：该组合不会腐败数据，但会让 recovery path 在已通过前置检查后进入必然失败的 transaction。Host
recovery 是设计真源里的核心治理边界，应避免内部 contract 自相矛盾。

修复要求：

- 在 `close_startup_orphan_attempt_in_transaction` 或 request validation 层拒绝
  `recoverable=True + expected_run_status=CANCELLING`，并用测试覆盖。

## Deferred Findings

以下 findings 不阻断当前 gate，但必须保留在 control doc 风险追踪或后续 phase：

- `StdlibPidLivenessProbe` 无 PID start token：accepted risk，需后续 recovery hardening；当前直接改成 positive proof
  会引入误杀 live owner 风险。
- `ProjectionRunner` failure 后 checkpoint 停滞：deferred design decision；跳过损坏 event 可能破坏 projection 顺序语义。
- pinned state `current_goal` first-write-wins 与 constraints 去重：deferred memory design refinement；当前测试明确冻结了现有行为。
- ToolRuntime / EngineIngest / memory 模块过长：deferred refactor，不作为 correctness gate。
- monkeypatch / sleep / e2e 测试质量问题：accepted test debt，需后续测试治理 phase。
- Outbox idempotency key 全局唯一、fallback_mode 常量重复、read transaction retry 配置复用等中低风险项：deferred。

## Next Action

派发 AgentCodex 修复 FR-F1 至 FR-F5，补充测试与必要 README 同步；修复后由 AgentMiMo 与 AgentDS 做 full-repo fix
re-review。两路 re-review PASS 后，总控更新本 gate 为 PASS。
