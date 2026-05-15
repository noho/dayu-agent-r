# Code Review

## Scope

- Mode: current changes
- Branch: feat/host-phase-6-toolruntime
- Base: main（workspace diff，未提交）
- Output file: `docs/reviews/host-phase6-code-review-s2-mimo-20260515.md`
- Included scope:
  - `dayu/host/tool_runtime.py` — accept barrier typed contract + durable accept port
  - `tests/host/test_toolruntime_accept_barrier.py` — new file
  - `tests/host/test_engine_ingest_mapping.py` — Engine 工具事件 preview 边界强化
  - `dayu/host/README.md` — ToolRuntime 能力同步
  - `tests/README.md` — 测试范围同步
- Excluded scope: Engine public contract、Remote wire protocol、durable 新表、ToolExecutor wrapper、truncation / fetch_more、duplicate governance 算法
- Parallel review coverage: 无

## Findings

未发现实质性问题。

以下是对 review 重点的逐项 evidence-based 审查结论：

### Accept Idempotency

`DefaultHostToolFactAcceptPort._accept_in_transaction`（`tool_runtime.py:636-701`）首先通过 `IdempotencyStore.read_idempotency_record` 检查 `scope_kind=tool_fact_accept`、`scope_id={attempt_id}:{tool_call_id}`、`idempotency_key=accept_idempotency_key`。若已有记录且 `semantic_input_digest` 相同，走 `_accepted_ack_from_existing` 重建 ack，不追加新 EventLog 事件。若已有记录但 digest 不同，返回 `IDEMPOTENCY_CONFLICT` rejected ack。首次写入通过 `IdempotencyStore.record_idempotent_result` 持久化幂等记录。整个流程在单一 write transaction 内完成。

测试 `test_same_accept_key_and_digest_returns_existing_ack_without_duplicate_facts` 验证重放不追加新事件；`test_same_accept_key_with_different_digest_returns_idempotency_conflict` 验证冲突拒绝。两者均断言 `_tool_events` 不变。

### EventLog Canonical Facts

`_tool_event_request`（`tool_runtime.py:1280`）所有工具 accept path 事件均使用 `event_class=EventClass.CANONICAL_FACT`。EngineEvent ingest 中的 `TOOL_CALL_REQUESTED`、`TOOL_RESULT_ACCEPTED`、`TOOL_CALL_DELTA`、`TOOL_CALLS_BATCH_READY`、`TOOL_CALLS_BATCH_DONE` 走 `_append_preview_event`（`engine_ingest.py:850-851`），event_class 为 `EventClass.PREVIEW`。两条路径互不穿透。

测试 `test_tool_batch_and_delta_events_stay_preview_not_canonical` 新增覆盖 batch/delta 事件的 PREVIEW 边界，断言 `_canonical_tool_event_count == 0`。

### Invalid / Stale Execution Reject

`_invalid_accept_context_reason`（`tool_runtime.py:1017-1051`）分层校验：
1. Run / Attempt 不存在 → `INVALID_ATTEMPT`
2. Dispatch record 不存在 → `INVALID_ATTEMPT`
3. session_id / run_id / current_attempt_id / attempt.run_id 身份不匹配 → `INVALID_ATTEMPT`
4. execution_id 在 attempt 或 dispatch record 中不匹配 → `STALE_EXECUTION`
5. Run 非 RUNNING / Attempt 非 RUNNING / Dispatch 非 DISPATCHING / 无 worker_accept_event_id → `INVALID_ATTEMPT`

测试 `test_invalid_attempt_and_stale_execution_reject_without_tool_facts` 覆盖 invalid_attempt（不存在的 attempt_id）和 stale_execution（不存在的 execution_id），断言返回正确 reason_code 且不写任何 EventLog 事件。

### EngineEvent 工具事件不得写 Canonical Facts

已在 EngineEvent Canonical Facts 项确认。EngineEvent ingest 中所有工具类型事件均走 PREVIEW 路径，不经过 `DefaultHostToolFactAcceptPort`。`_canonical_tool_event_count` 辅助函数在 `test_engine_ingest_mapping.py` 中被两处测试使用，均断言为 0。

### 文件范围 / Scope

P6-S2 只修改 `dayu/host/tool_runtime.py`（typed contract + durable accept port）、对应测试和 README。未触及 Engine public contract、Remote wire protocol、durable 新表、`dayu/host/api.py`、`dayu/host/durable/` 新模块或 `dayu/contracts/`。scope 与 plan P6-S2 定义一致。

### 类型纪律

所有新增 dataclass 均为 `frozen=True, slots=True`。签名无 `Any`、`object` 或无类型参数。`ToolFactAcceptResult` 为显式 union type alias。`ToolFactKind`、`ToolAcceptRejectReason`、`ToolPolicyDecisionKind`、`DuplicateDecisionKind` 均为 `StrEnum`。`__post_init__` 校验覆盖所有 fact kind 的必填字段组合。pyright 通过，0 errors。

### 测试质量

`test_toolruntime_accept_barrier.py` 覆盖 4 个核心场景：
1. 同 key + 同 digest 幂等重放
2. 同 key + 不同 digest 冲突拒绝
3. invalid attempt + stale execution 拒绝
4. EventLog 序号单调递增 + reuse 不伪造新 result fact

`test_engine_ingest_mapping.py` 新增 `test_tool_batch_and_delta_events_stay_preview_not_canonical`，覆盖 delta / batch_ready / batch_done 三种 Engine 工具事件的 PREVIEW 边界。

### README 是否只写当前事实

`dayu/host/README.md` 更新内容准确描述 P6-S2 已实现的 accept barrier typed contract / durable port / idempotency / canonical facts / EngineEvent preview 边界，以及仍未实现的真实工具 dispatch / truncation / fetch_more / duplicate governance 算法。未写未来设计。

`tests/README.md` 新增 `test_toolruntime_accept_barrier.py` 命令与 accept barrier 测试覆盖范围描述，与实际测试一致。

## Open Questions

无。

## Residual Risk

- `DefaultHostToolFactAcceptPort` 当前未被真实 `ToolExecutor` wrapper 调用，该连接属于 P6-S3。
- `ToolAcceptTimedOut` 与 `ToolAcceptRetryPolicy` 仅完成 typed contract，未实现 retry loop。
- `schema_mismatch`、`cas_conflict`、`explicit_policy_reject` 作为 rejected ack reason 已定义枚举值，但当前 P6-S2 没有触发路径可测试这些分支；后续 slice 接入 policy / snapshot 后应补测试。
- `accept_tool_fact` 仅 catch `HostIdempotencyConflictError` 和 `HostPayloadReferenceError`，其它 `HostDurableError` 子类会直接传播为未处理异常。这是正确行为（基础设施错误应上浮），但未被测试覆盖。
