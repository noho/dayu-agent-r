# Host Phase 6 P6-S2 Implementation Artifact - Accept Barrier

- **gate**: Phase 6 P6-S2 implementation
- **work unit**: Host Accept Barrier And Tool Canonical Facts
- **approved plan**: `docs/host/phase6-toolruntime-truncation-fetch-more-plan.md`
- **scope**: Host accept path、accepted / rejected / timeout result types、accept idempotency mapping、EventLog tool canonical facts、EngineEvent 工具事件 preview 边界
- **non-goals honored**: 未实现 ToolExecutor 真实 callable execution、truncation / `fetch_more` / cursor、wait record / `WAITING` / `resolve_wait`、duplicate governance 算法、Remote wire protocol、Engine public contract、durable 新表
- **artifact path**: `docs/reviews/host-phase6-implementation-s2-accept-barrier-20260515.md`

## Motivation Judgment

动机成立，严重性没有被高估。P6-S1 只固定 effective `ToolBundle` 同源边界，工具结果如果仍能通过 EngineEvent ingest 或未确认路径进入模型，会破坏 Host 作为 tool governance truth 的设计目标。P6-S2 只实现 Host accept barrier 与 canonical facts，不接入执行器，切片边界合理。

## Changed Files

- `dayu/host/tool_runtime.py`
  - 新增 `ToolFactKind`、`ToolAcceptRejectReason`、`HostEventRef`、`HostPayloadRef`、`ToolTruncationFact`、`ToolFactAcceptCandidate`、`ToolFactAcceptedAck`、`ToolFactRejectedAck`、`ToolFactAcceptTimedOut`、`ToolAcceptRetryPolicy` 与 `ToolFactAcceptResult`。
  - 将 `HostToolFactAcceptPort` 改为 typed candidate -> structured result。
  - 新增 `DefaultHostToolFactAcceptPort`，复用现有 `HostTransactionRunner`、`EventLogStore` 与 `IdempotencyStore`，在一个 write transaction 内校验 Run / Attempt / execution / dispatch precondition，写入 `TOOL_CALL_REQUESTED`、必要的 `TOOL_CALL_GOVERNED` 与非 reuse 的 `TOOL_RESULT_ACCEPTED`。
  - 同一 `scope_kind=tool_fact_accept`、`scope_id={attempt_id}:{tool_call_id}`、`accept_idempotency_key` 与同 semantic digest 返回既有 ack；同 key 不同 digest 返回 `idempotency_conflict` rejected ack。
- `tests/host/test_toolruntime_accept_barrier.py`
  - 新增 direct accept port 测试，覆盖 accepted ack、幂等重放、幂等冲突、invalid Attempt、stale execution、EventLog canonical facts、monotonic `event_sequence`、reuse 不伪造第二个 `TOOL_RESULT_ACCEPTED`、failed / cancelled / governed_error result fact、非 reuse 携带 prior refs 拒绝，以及 retry / timeout guard。
- `tests/host/test_engine_ingest_mapping.py`
  - 强化 Engine 工具事件测试，证明 `TOOL_CALL_REQUESTED`、`TOOL_RESULT_ACCEPTED`、`TOOL_CALL_DELTA`、`TOOL_CALLS_BATCH_READY`、`TOOL_CALLS_BATCH_DONE` 只写 preview，不产生 canonical `TOOL_*` facts。
- `dayu/host/README.md`
  - 同步 Host ToolRuntime 当前能力，移除 “Host accept barrier 未实现” 的过期描述。
- `tests/README.md`
  - 同步新增 ToolRuntime accept barrier 测试范围与常用命令。

## Validation

- `source .venv/bin/activate && pytest tests/host/test_toolruntime_accept_barrier.py tests/host/test_event_log_store.py tests/host/test_engine_ingest_mapping.py -q`
  - Result: PASS, `37 passed`.
- `source .venv/bin/activate && python -m pyright dayu/host tests/host`
  - Result: PASS, `0 errors, 0 warnings, 0 informations`.
- `git diff --check`
  - Result: PASS.

## Docs Decision

本 slice 修改 `dayu/host/` 与 `tests/host/`，按 README 触发规则检查并更新：

- `dayu/host/README.md`：属于 Host 开发手册职责，已更新 ToolRuntime accept barrier 当前能力与未实现项。
- `tests/README.md`：属于测试手册职责，已更新新增测试命令与 Host 测试覆盖范围。

## Residual Risks

- `DefaultHostToolFactAcceptPort` 当前只提供直接 Host durable accept path，尚未由真实 `ToolExecutor` wrapper 调用；该连接属于 P6-S3。
- `TOOL_CALL_GOVERNED` 目前按 candidate 中的 policy / duplicate 字段决定是否写入，不实现 duplicate governance 算法；该算法属于后续 P6 slice。
- `ToolAcceptTimedOut` 与 `ToolAcceptRetryPolicy` 仅完成 typed contract 与构造校验，未实现 retry loop；有限 retry 属于 P6-S3 ToolExecutor wrapper。
- `schema_mismatch`、`cas_conflict`、`explicit_policy_reject` 作为 rejected ack reason 已固定类型，但当前 P6-S2 没有 durable tool schema snapshot 或 policy reject caller 可触发这些分支；后续 slice 接入 policy / snapshot 后应补相应路径测试。

## Completion Status

P6-S2 implementation complete. 未发现需要新增 durable table 的情况；未修改 Engine public contracts、Remote wire protocol、wait record 或业务工具导入边界。
