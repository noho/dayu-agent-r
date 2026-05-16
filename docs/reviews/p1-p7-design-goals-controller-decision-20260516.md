# P1-P7 Design Goals Controller Decision

日期：2026-05-16

设计目标真源：`docs/host/design.md`

背景：用户明确决定 `fetch_more` cursor 只存在内存，作为当前最终设计口径。

## Verdict

本轮不再以 `1245aeefeeb182a2da833c8577d701a6a71b7065` 的字面事件 / cursor 细节作为唯一裁决依据，而是以当前 `docs/host/design.md` 的设计目标与最佳实践裁决。

## Decisions

### D1 — `fetch_more` cursor 内存态能力

- 裁决：接受当前设计，不作为偏离。
- 理由：用户明确决定 `fetch_more` cursor 只存在内存；当前 `docs/host/design.md` 已在 Phase 6 细化为 Run-scoped、short-lived、ToolRuntime-local capability，不承诺跨 Host restart、Attempt `LOST`、recovery 或 replay 续读。
- 动作：无需修代码；无需为该项保持 High finding。

### D2 — active worker registry 注入

- 裁决：代码偏离，必须修代码。
- 设计目标：Host composition root 必须显式持有影响执行和外部通信的运行参数；不得只能通过模块级全局变量或隐式单例取得。
- 当前问题：`command.py` cancel propagation 通过 `cancel_active_worker()` 访问 `dispatch.py` 模块级 `DEFAULT_ACTIVE_WORKER_REGISTRY`；这与 scheduler 可注入的 `active_registry` 不同源。
- 最佳实践：把 cancel propagation 做成 Host command handle / composition root 持有的 typed port 或 injected `ActiveWorkerRegistry`，让 command path 与 scheduler 使用同源依赖。
- 动作：修代码与测试。

### D3 — `resolve_wait` 幂等 digest

- 裁决：代码偏离，必须修代码。
- 设计目标：`resolve_wait` 幂等范围是 `(wait_id, idempotency_key)`；同一 key + 同一 outcome 重试必须重放既有结果，只有不同 outcome 才 conflict。
- 当前问题：`_wait_resolution_digest()` 把 `observed_at` 纳入 semantic digest，使同 outcome 但不同观测时间的真实 retry 可能变成 `idempotency_conflict`。
- 最佳实践：`observed_at` 保留在首次提交的 EventLog / audit / diagnostic payload 中，但不参与“同 outcome”幂等冲突判断。
- 动作：修代码与测试。

### D4 — `TOOL_TERMINAL_RESULT`

- 裁决：修改 design，不修代码。
- 设计目标：EventLog 作为 canonical fact ledger，应该避免同一工具结果同时产生两套等价 canonical fact；RunInputBuilder、memory、audit 和 tool trace 应能从一个稳定工具结果事实解释等待完成后的工具结果。
- 当前代码：等待完成结果通过 `TOOL_RESULT_ACCEPTED` 写入，payload 包含 `wait_id`、`resolution_source`、`resolution_kind`、`resolution_idempotency_key`、`observed_at`、wait refs、adapter refs、resume Attempt / dispatch refs 等 wait-specific 字段。
- 最佳实践：`TOOL_RESULT_ACCEPTED` 作为唯一 accepted tool result canonical event，覆盖普通工具结果与 waiting terminal tool result；通过 payload 中的 wait-specific 字段区分来源，不新增重复 `TOOL_TERMINAL_RESULT` event。
- 动作：更新 `docs/host/design.md`，删除 / 澄清 `TOOL_TERMINAL_RESULT` 独立 event 口径。

### D5 — `FOLLOWUP_QUEUED`

- 裁决：修改 design，不修代码。
- 设计目标：follow-up queue 必须可审计、可重放、可由 EventLog 解释，同时避免重复 canonical fact。
- 当前代码：`submit_followup(queue)` 通过 `USER_INPUT_ACCEPTED` 记录输入，后续 `RUN_ACCEPTED` / `RUN_QUEUED` / `RUN_STARTED` 记录 Run 接受、排队或直接启动；snapshot 通过 `accepted_run_id` / `accepted_run_status` 表达结果。
- 最佳实践：不增加单独 `FOLLOWUP_QUEUED` canonical event；follow-up queue 的 canonical 表达是 `USER_INPUT_ACCEPTED` + Run admission facts。必要时在 `USER_INPUT_ACCEPTED` payload 中保留 `operation_kind` / call context digest 来解释来源。
- 动作：更新 `docs/host/design.md`，删除 / 澄清 `FOLLOWUP_QUEUED` 独立 event 口径。

### D6 — WAITING cancel docstring

- 裁决：代码文档注释 stale，低风险修复。
- 当前代码行为：`admission.py` 已实现 `RunStatus.WAITING` 分支的 `_cancel_waiting()`。
- 当前问题：`command.py` 的 `cancel_run` / `cancel_session_runs` docstring 仍称 `WAITING` cancel 由 Phase 7 负责。
- 动作：更新 docstring，不改变行为。

## Fix Gate

派发 AgentCodex 执行 D2、D3、D4、D5、D6。完成后由 AgentMiMo 与 AgentDS 做同口径 fix review。
