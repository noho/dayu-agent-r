# WU-CLI-INTERACTIVE-RESUME-01 Plan Review Adjudication

- Work unit: `WU-CLI-INTERACTIVE-RESUME-01`
- Plan artifact: `docs/reviews/wu-cli-interactive-resume-01-plan-codex-20260617.md`
- Review artifacts:
  - `docs/reviews/plan-review-20260617-183641.md`
  - `docs/reviews/plan-review-20260617-183910.md`
- Adjudication date: 2026-06-17
- Verdict: **PLAN ACCEPTED WITH REQUIRED AMENDMENTS**

## Controller Decision

原 plan 的动机成立：`prompt` 与 `interactive` 的 session 启动语义必须分开处理。`prompt` 只提交并展示本次输入对应的 terminal/final answer；`interactive` 对已有 Session 的入口必须执行 attach/reconnect startup，在进入输入态之前处理该 Session 已存在的离线 terminal 与未完成 Run。

原 plan 不能直接进入 implementation，因为两路 review 都指出了会导致 terminal 漏投或状态静默忽略的边界问题。AgentCodex 必须先修订 plan，再按修订后的 plan 实施。

## Required Amendments

### 1. Outbox backfill 必须是 session-scoped

接受 AgentMiMo Finding 1。startup backfill 读取的是选中 Session 下所有离线 terminal/final answer 通知，不是某个目标 Run 的 fallback。因此不得复用现有 run-scoped `_read_outbox_terminal(...)` 语义。

修订后的 plan 必须明确：

- 新增 session-scoped private helper。
- 不按 `run_id` 过滤。
- `CAUGHT_UP` 且没有新 item 是正常结束，不是异常。
- 可复用 terminal item 到 display/result DTO 的转换逻辑，但不得复用 run-scoped fallback 的匹配与异常语义。

### 2. 必须关闭 live watcher 与 Outbox backfill 之间的漏投窗口

接受两路 review 的 TOCTOU finding。startup attach/reconnect 必须提供无漏投证明，不能先 drain Outbox 再打开 watcher 后直接相信两者之间没有 terminal。

修订后的 plan 必须采用以下顺序：

1. 读取 CLI 保存的 terminal cursor。
2. 打开 `watch_session_events(session_id)`，开始缓存 live events。
3. 读取 session-scoped Outbox terminal 增量。
4. 用 `terminal_event_id` / `event_sequence` / `run_id` 对 Outbox 与 live watcher overlap 去重。
5. 再读取 Session snapshot 并处理 active / queued nonterminal Run。

如实现中采用等价 tail-read 方案，必须在 artifact 中证明窗口闭合；默认采用 watcher-first。

### 3. queued-only Session 不得 silent ignore

接受 queued-only finding，但裁决为：interactive existing-session startup 是 pre-input recovery barrier。进入 REPL 前，启动时已经存在的 `active_run_id` 与 `queued_run_ids` 都必须被处理到可解释状态。

修订后的 plan 必须明确：

- 如果有 `active_run_id`，观察该 Run 到 terminal，再重新读取 Session snapshot。
- 如果没有 active 但存在 `queued_run_ids`，不得直接进入 REPL。
- queued-only 应按 bounded promotion wait 处理：等待 Host 将 queued Run promotion 为 active；promotion 后按 active Run 观察；如果 bounded wait 后仍然 queued-only，CLI 以结构化启动失败退出并说明 Session 仍有未开始的 queued Run，不得让用户在未知队列前提下继续输入。
- 当 snapshot 同时没有 active 与 queued，才进入 REPL。

该行为不新增 Host / Engine public API；只使用 `get_session`、`watch_session_events` 与 Outbox read。

### 4. prompt 不做 startup，但可以标记已展示 terminal

部分接受 prompt cursor finding。`prompt` 不得读取 startup cursor，不得补读离线 terminal，不得等待或重放历史未完成 Run。它只提交当前输入并展示当前 terminal/final answer。

但 CLI terminal cursor 的语义是“本 CLI 已展示过的 terminal watermark”，不是“interactive startup 专用状态”。因此 `prompt` 在成功展示本次 terminal/final answer 后，可以更新 cursor，以避免随后 `interactive --label` 或 `session resume --mode interactive` 重复展示同一 terminal。该写入不属于 startup backfill 或 unfinished-run resume/replay。

修订后的 plan 必须把这个边界写清楚，并补测试证明：

- `prompt --label` 不读取旧 cursor、不补读旧 terminal。
- `prompt --label` 展示当前 answer 后更新 cursor。
- 后续 interactive resume 不重复展示 prompt 已展示的 terminal。

### 5. async cursor store 不得阻塞 event loop

接受 AgentDS Finding 2。cursor store 可以复用同步 `dayu.runtime.filelock`，但 async CLI 路径必须通过 `asyncio.to_thread()` 或等价 executor 包裹同步文件读写与锁持有过程。

修订后的 plan 必须包含：

- 命名常量，禁止裸魔法数字。
- 腐坏 JSON / 非法字段结构化失败，不静默 reset。
- 写入必须在成功渲染后发生；渲染后写入前崩溃允许重复展示，优先不漏投。

### 6. poll policy 必须参数化

接受 bounded poll finding。Service helper 可理解 Host projection status，但 poll policy 由调用方参数传入，沿用现有 `poll_interval_seconds` 风格。

修订后的 plan 必须明确：

- LAGGED poll 最大尝试次数、间隔来自参数或命名默认常量。
- projection `FAILED` 是启动失败，不降级为静默进入 REPL。
- bounded promotion wait 的总时长或尝试次数由 CLI/Service 调用参数表达，不在底层硬编码。

## Rejected Or Deferred Items

- 不采纳“prompt cursor advancement 必须移出本 WU”。本裁决将 cursor 定义为 CLI 已展示 terminal watermark；prompt 展示当前 terminal 后更新 watermark 是防重复展示所需，不改变 prompt startup 语义。
- 多 CLI 客户端共享 workspace cursor 的 per-client isolation 暂不进入本 WU。当前按 workspace-local CLI client state 处理，作为 residual risk 记录。

## Implementation Gate Requirement

AgentCodex 必须先产出修订后的 implementation plan artifact，体现上述 required amendments。修订 plan 通过总控检查后，才允许进入代码 implementation。
