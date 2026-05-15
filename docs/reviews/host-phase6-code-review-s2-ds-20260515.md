# Code Review

## Scope

- Mode: current changes
- Branch: feat/host-phase-6-toolruntime
- Base: main (commit 0746bd8 is the branch tip; uncommitted workspace diff is the review target)
- Output file: docs/reviews/host-phase6-code-review-s2-ds-20260515.md
- Included scope:
  - `dayu/host/tool_runtime.py` — P6-S2 新增 accept barrier typed contract 与 `DefaultHostToolFactAcceptPort`
  - `tests/host/test_toolruntime_accept_barrier.py` (new) — accept barrier 测试
  - `tests/host/test_engine_ingest_mapping.py` — Engine 工具事件 preview 边界测试强化
  - `dayu/host/README.md` — ToolRuntime 当前能力同步
  - `tests/README.md` — 测试范围与命令同步
- Excluded scope:
  - P6-S1 已有代码（`EffectiveToolBundle`、`ToolRuntimeHandle` 等）仅在 P6-S2 diff 中作为上下文被新代码引用，不做深度重审。
  - `dayu/host/durable/event_log.py`、`dayu/host/durable/run_transition.py`、`dayu/host/_event_payload.py`、`dayu/host/engine_ingest.py`、`dayu/host/durable/schema.py` 均在 P6-S2 允许文件列表中但未修改；经确认 engine_ingest.py 已正确将工具事件映射为 PREVIEW，无需变更。
- Parallel review coverage: 无
- Design source of truth: `docs/host/design.md` §17 (accept idempotency)、§18 (ToolRuntime boundary / accept barrier)、§16.4 (EngineEvent 工具事件 preview 边界)
- Implementation control: `docs/host/implementation-control.md` Phase 6
- Approved plan: `docs/host/phase6-toolruntime-truncation-fetch-more-plan.md` P6-S2

## Verification

- `pytest tests/host/test_toolruntime_accept_barrier.py tests/host/test_event_log_store.py tests/host/test_engine_ingest_mapping.py -q`: **34 passed**
- `python -m pyright dayu/host tests/host`: **0 errors, 0 warnings, 0 informations**
- `git diff --check`: **clean**

## Findings

### 1-未修复-中-`_invalid_accept_context_reason` 将不同语义的 precondition 失败统一归为 `INVALID_ATTEMPT`

- **入口/函数**: `_invalid_accept_context_reason`
- **文件(行号)**: `dayu/host/tool_runtime.py:647-681`
- **输入场景**: Run 已进入终态（CANCELLED / FAILED / COMPLETED）或 Attempt 已非 RUNNING 时，调用方尝试 accept 工具事实。
- **实际分支**: 行 675-680 的复合条件中，`context.run.status is not RunStatus.RUNNING`、`context.attempt.status is not AttemptStatus.RUNNING`、`context.dispatch_record.status is not DispatchRecordStatus.DISPATCHING` 三条任一为 True，均返回 `ToolAcceptRejectReason.INVALID_ATTEMPT`。
- **预期行为**: Run/Attempt 存在但状态已非 RUNNING 时，实际语义是 "accept rejected because execution context is no longer active"，这与 "Attempt 不存在" 或 "Run 不存在" 的 `INVALID_ATTEMPT` 是不同的失败模式。区分终端状态与不存在可以帮助调用方（P6-S3 ToolExecutor wrapper）做出更精确的 retry / abort 决策。
- **实际行为**: 所有非 active 状态统一返回 `INVALID_ATTEMPT`，调用方无法区分 "ID 本身非法" 与 "ID 合法但状态已终结"。
- **直接证据**: 行 675-680，整个 if 块使用同一个 `ToolAcceptRejectReason.INVALID_ATTEMPT`。
- **影响**: 仅影响诊断精度。当前 P6-S2 只实现 accept port，ToolExecutor wrapper 在 P6-S3。`ToolFactRejectedAck.message` 已携带 `"tool fact accept precondition failed"` 辅助诊断，实际运行时行为一致（都是 reject）。严重程度评估为**中**。
- **建议改法和验证点**:
  1. 保持 `INVALID_ATTEMPT` 仅用于 Run/Attempt/dispatch_record 不存在的情况。
  2. Run/Attempt status 非 RUNNING 时，改为返回独立的拒绝原因，例如已在 `ToolAcceptRejectReason` 枚举中预留一个新值，或在 message 中明确区分。
  3. 若不改枚举，至少在 `message` 中明确写出具体是哪个字段不符合预期（如 `"Run status is CANCELLED, expected RUNNING"`），让调用方可以解析。
- **修复风险（低）**: 只改 reject reason 枚举值或 message 文案，不影响事务行为或 EventLog 写入。
- **严重程度（中）**:

### 2-未修复-中-`ToolFactKind.FAILED` / `CANCELLED` / `GOVERNED_ERROR` 的 accept path 无直接测试覆盖

- **入口/函数**: `DefaultHostToolFactAcceptPort.accept_tool_fact` → `_accept_in_transaction`
- **文件(行号)**: `dayu/host/tool_runtime.py:596-701` 与 `tests/host/test_toolruntime_accept_barrier.py` 全文
- **输入场景**: 调用方提交 `tool_fact_kind=FAILED`（带 outcome_digest）、`tool_fact_kind=CANCELLED` 或 `tool_fact_kind=GOVERNED_ERROR` 的 candidate。
- **实际分支**: `__post_init__` 行 303-313 对 FAILED/CANCELLED/GOVERNED_ERROR 仅校验 `outcome_digest` 存在且不携带 prior reuse refs，accept path 其余逻辑与 COMPLETED 共享同一通道（都写 TOOL_CALL_REQUESTED + TOOL_RESULT_ACCEPTED）。
- **预期行为**: FAILED/CANCELLED/GOVERNED_ERROR 候选应通过 accept 写入对应的 canonical facts，且 `TOOL_RESULT_ACCEPTED` payload 中的 `tool_fact_kind` 应反映实际类别。
- **实际行为**: 根据代码走读，COMPLETED 路径的测试已验证主干（TOOL_CALL_REQUESTED + TOOL_RESULT_ACCEPTED 写入 + 幂等），但 FAILED/CANCELLED/GOVERNED_ERROR 分支缺少独立测试。主干路径相同，但缺少以下断言：
  - GOVERNED_ERROR 候选写入的 `policy_decision.kind` 在 payload 中正确存为 `governed_error`
  - FAILED/CANCELLED 候选的 `outcome_digest` 在 `TOOL_RESULT_ACCEPTED` payload 中正确反映
  - reuse_prior_event_refs 校验（`must not carry prior reuse refs`）未被任何测试触发
- **直接证据**: 测试文件 `test_toolruntime_accept_barrier.py` 中 `_completed_candidate` 和 `_reuse_candidate` 覆盖了 COMPLETED 与 REUSE 两种 fact kind，FAILED / CANCELLED / GOVERNED_ERROR 无对应 helper 或测试函数。
- **影响**: FAILED/CANCELLED/GOVERNED_ERROR 的 accept 行为与 COMPLETED 共享同一代码路径（`_append_tool_result_if_needed` 对所有非 REUSE 的 kind 行为一致），当前缺少回归防护。plan 行 187 要求 `governed_error` 的 `unsupported_awaiting` 只能作为 policy reason，该约束当前无测试覆盖。
- **建议改法和验证点**: 新增测试函数覆盖：
  1. `tool_fact_kind=FAILED` + ALLOW policy → accepted ack，TOOL_RESULT_ACCEPTED payload 中 `tool_fact_kind=failed`
  2. `tool_fact_kind=GOVERNED_ERROR` + GOVERNED_ERROR policy → accepted ack，`policy_decision.kind=governed_error`
  3. FAILED/CANCELLED/GOVERNED_ERROR 的 reuse_prior_event_refs 非空时 `__post_init__` 抛 ValueError
- **修复风险（低）**: 仅新增测试，不改生产代码。
- **严重程度（中）**:

### 3-未修复-低-`ToolAcceptRetryPolicy` 与 `ToolFactAcceptTimedOut` 未在测试中验证构造校验

- **入口/函数**: `ToolAcceptRetryPolicy.__post_init__` / `ToolFactAcceptTimedOut.__post_init__`
- **文件(行号)**: `dayu/host/tool_runtime.py:399-411` 与 `372-387`
- **输入场景**: 非法参数（如 `max_attempts=0`、`backoff_seconds=-1`、`attempt_count=0`）构造 retry policy 或 timed-out ack。
- **实际分支**: `__post_init__` 中的 guard 条件会抛出 ValueError。
- **预期行为**: 非法参数应被拒绝。
- **实际行为**: 逻辑正确，但无独立测试覆盖这些 guard。plan 要求 `max_attempts` 与 `backoff_seconds` 为 named policy fields 且禁止魔法数字，当前实现已满足。
- **直接证据**: 测试文件中无对应 `ToolAcceptRetryPolicy` 或 `ToolFactAcceptTimedOut` 的构造测试。
- **影响**: 低。这些类型当前 P6-S2 未被调用（P6-S3 才会使用），且 `__post_init__` 逻辑简单。
- **建议改法和验证点**: P6-S3 接入 retry loop 时补充。
- **修复风险（低）**:
- **严重程度（低）**:

### 4-未修复-低-`_tool_accept_event_plan` 中 `digest.removeprefix("sha256:")` 对 digest 格式有隐式依赖

- **入口/函数**: `_tool_accept_event_plan`
- **文件(行号)**: `dayu/host/tool_runtime.py:1072`
- **输入场景**: `sha256_digest_json` 返回的 digest 格式变化（例如未来不带 `sha256:` 前缀或改用其他前缀）。
- **实际分支**: `removeprefix("sha256:")` 静默处理两种情况：有前缀则去掉，无前缀则原样返回。
- **预期行为**: 应使用 Host 内部稳定的 digest 剥离方法（`dayu.host.durable.codec` 中可能已有等价工具），避免在多处重复格式假设。
- **实际行为**: 当前 `sha256_digest_json` 始终返回 `sha256:` 前缀格式，`removeprefix` 在该上下文正确。但模块中已有 `is_sha256_digest` 校验函数，没有对等的 "strip prefix" 函数在 codec 中暴露，所以此处只能直接操作字符串。
- **直接证据**: `dayu/host/tool_runtime.py:1072`。
- **影响**: 低。`sha256_digest_json` 是 Host 内部稳定函数，格式变更概率低。
- **建议改法和验证点**: 若后续有多处需要去掉 sha256 前缀，抽取为 `dayu.host.durable.codec` 中的公共函数。
- **修复风险（低）**:
- **严重程度（低）**:

## Adversarial Failure Pass

按以下维度逐项检查：

### Accept Idempotency
- **同 key + 同 digest 重放**: `_accept_in_transaction` 先读幂等记录 → 命中 → digest 匹配 → 返回既有 ack（`_accepted_ack_from_existing`）。事件不重复写入。测试 `test_same_accept_key_and_digest_returns_existing_ack_without_duplicate_facts` 覆盖。**通过**。
- **同 key + 不同 digest**: digest 不匹配 → 返回 `IDEMPOTENCY_CONFLICT` rejected ack，retryable=False。不写入事件。测试 `test_same_accept_key_with_different_digest_returns_idempotency_conflict` 覆盖。**通过**。
- **并发 accept race**: SQLite `BEGIN IMMEDIATE` 序列化写事务，T1 提交后 T2 读取到既有幂等记录。若 T2 的 record_idempotent_result 因 UNIQUE 约束失败，`HostIdempotencyConflictError` 被外层捕获，事务回滚（`run_write` 行 257-259 对 `HostDurableError` 子类执行 rollback + re-raise），不残留事件。**通过**。
- **幂等记录存在但 EventLog 事件缺失**: `_read_required_event` 抛 `HostDurableError`，该异常不在 `accept_tool_fact` 的 except 子句中 → 向上传播。符合预期——这是数据库损坏场景，不应静默。**通过**。

### Invalid / Stale Execution Reject
- **Attempt 不存在**: `_read_accept_context` → `_AcceptContext(attempt=None)` → `_invalid_accept_context_reason` 返回 `INVALID_ATTEMPT`。测试 `test_invalid_attempt_and_stale_execution_reject_without_tool_facts` 覆盖。**通过**。
- **execution_id 不匹配**: attempt.execution_id != candidate.execution_id 或 dispatch_record.execution_id != candidate.execution_id → `STALE_EXECUTION`。测试覆盖。**通过**。
- **Run 不存在**: 同 INVALID_ATTEMPT 路径，测试中 `invalid_attempt` 场景覆盖（attempt_id 不匹配 → context.attempt 为 None 或 run_id 不匹配）。**通过**。
- **dispatch_record 不存在**: `context.dispatch_record is None` → `INVALID_ATTEMPT`。未单独测试，但与 attempt 不存在的校验在同一分支，覆盖等价。**通过**。

### Canonical Facts 写入完整性
- **事务原子性**: 所有 EventLog 写入与幂等记录在同一 `run_write` 事务中。COMMIT 前任何异常触发 rollback，不残留部分写入。**通过**。
- **REUSE 不写入 TOOL_RESULT_ACCEPTED**: `_append_tool_result_if_needed` 行 1196 `if candidate.tool_fact_kind is ToolFactKind.REUSE: return None`。测试 `test_event_sequence_monotonic_and_reuse_has_canonical_governance_only` 验证 TOOL_RESULT_ACCEPTED 为 None 且只有 canonical TOOL_CALL_REQUESTED + TOOL_CALL_GOVERNED。**通过**。
- **event_sequence 单调性**: 测试验证 `sorted(row.event_sequence for row in tool_events)` 等于原始 sequence。**通过**。
- **EventClass 正确**: 所有工具事实写入 `EventClass.CANONICAL_FACT`（`_tool_event_request` 行 912）。测试断言 `all(row.event_class is EventClass.CANONICAL_FACT for row in after)`。**通过**。

### EngineEvent 工具事件不写 Canonical Facts
- **engine_ingest.py mapping**: `TOOL_CALL_REQUESTED`、`TOOL_RESULT_ACCEPTED`、`TOOL_CALL_DELTA`、`TOOL_CALLS_BATCH_READY`、`TOOL_CALLS_BATCH_DONE` 均在 `_is_preview_event_type`（行 1683-1700）中返回 True，通过 `_append_preview_event`（行 850-851）写入 `EventClass.PREVIEW`。
- **测试验证**: `test_tool_call_requested_and_result_accepted_are_preview` 断言 `EventClass.PREVIEW` + `_canonical_tool_event_count == 0`。`test_tool_batch_and_delta_events_stay_preview_not_canonical` 覆盖 batch/delta。**通过**。

### 类型纪律
- pyright: 0 errors in `dayu/host` + `tests/host`。**通过**。
- 无 `Any`、`object`、无类型参数引入新 contract。所有 dataclass 字段、函数签名均有完整类型标注。**通过**。

### 分层边界
- `tool_runtime.py` 新增 import 均来自 `dayu.host.durable.*`、`dayu.host.api`、`dayu.host.tooling` 与 `dayu.contracts.*`。无 `dayu.fins`、`dayu.service`、`dayu.ui` 导入。**通过**。
- 无新增 durable table。**通过**。
- 无 Engine public contract 修改。**通过**。
- 无 Remote wire protocol 修改。**通过**。

### Scope 合规
- 所有变更文件均在 plan P6-S2 允许列表中。`engine_ingest.py`、`event_log.py`、`run_transition.py`、`_event_payload.py`、`schema.py` 未修改，但确认现有实现已满足 P6-S2 要求（Engine tool events 已为 PREVIEW；EventLog 无需 schema 变更）。**通过**。

### README 同步
- `dayu/host/README.md`: 移除 "Host accept barrier 未实现"、同步当前能力、未实现项更新为剩余 slice。**通过**。
- `tests/README.md`: 新增 `test_toolruntime_accept_barrier.py` 测试命令、更新覆盖描述。**通过**。
- 未修改 `dayu/README.md`、`dayu/engine/README.md`、`dayu/fins/README.md`——合理，P6-S2 不涉及这些层。**通过**。

## Open Questions

1. `_invalid_accept_context_reason` 中 `context.dispatch_record.worker_accept_event_id is None`（行 678）与 `context.dispatch_record.status is not DispatchRecordStatus.DISPATCHING`（行 677）在同一 if 块中。若 dispatch_record 状态为 DISPATCHING 但 `worker_accept_event_id` 为 None（可能是 dispatch 状态机的中间态），当前实现同时拒绝并归为 `INVALID_ATTEMPT`。是否存在 DISPATCHING 但 worker 尚未 accepted 的合法中间态？若是，`INVALID_ATTEMPT` 可能对从此状态提交工具事实的场景过于严厉。

2. `HostToolFactAcceptPort.accept_tool_fact` 的返回值类型为 `ToolFactAcceptResult`（`ToolFactAcceptedAck | ToolFactRejectedAck | ToolFactAcceptTimedOut`）。当前 `DefaultHostToolFactAcceptPort.accept_tool_fact` 实现不会产生 `ToolFactAcceptTimedOut`，仅 P6-S3 ToolExecutor wrapper 会使用该分支。类型签名中包含 timed-out 是否暗示 `DefaultHostToolFactAcceptPort` 也应支持重试？或 timed-out 完全是调用方（ToolExecutor wrapper）的责任？

## Residual Risk

- **FAILED / CANCELLED / GOVERNED_ERROR accept path 无独立测试**: 见 Finding 2。P6-S3 接入 ToolExecutor wrapper 后，这些路径将被间接覆盖，但单元级覆盖缺失。
- **`SCHEMA_MISMATCH` / `CAS_CONFLICT` / `EXPLICIT_POLICY_REJECT` 拒绝分支**: plan 指出这些 reason code 已定义类型但 P6-S2 尚无触发路径。后续 slice 接入 policy provider / tool schema snapshot 后需补测试。
- **`ToolAcceptTimedOut` / `ToolAcceptRetryPolicy` 无调用方**: P6-S3 ToolExecutor wrapper 是第一调用方，届时需验证 timed-out → governed error 转换逻辑。
- **`_accepted_ack_from_existing` 在读 EventLog 时不重新校验 Run/Attempt 当前状态**: 设计上正确（幂等重放只返回既有 ack），但若系统允许 accepted 事实的 Run 被某些 bypass 路径清理（如手动删库），会抛 `HostDurableError`。这在正常运维场景下不应发生。
- **dispatched but not-yet-worker-accepted 状态下的 accept 行为**: 见 Open Question 1。

## Verdict

**P6-S2 未发现 blocking finding。** 实现正确满足 plan 中 accept idempotency、EventLog canonical facts、invalid/stale execution reject 与 EngineEvent 工具事件 preview 边界要求。类型纪律、分层边界、事务安全性与 README 同步均通过验证。

两个中等级 findings（INVALID_ATTEMPT 语义粒度过粗、FAILED/CANCELLED/GOVERNED_ERROR 测试缺失）建议在 P6-S3 或后续 slice 中随 ToolExecutor wrapper 接入时一并修复，无需阻塞 P6-S2 推进。
