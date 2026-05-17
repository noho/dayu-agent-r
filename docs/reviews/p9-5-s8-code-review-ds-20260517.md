# P9.5 S8 Engine Wait Confirmation Matching-Ref Hardening — Code Review (AgentDS)

## Gate

- Role: AgentDS, review-only.
- Gate: P9.5 S8 Engine Wait Confirmation Matching-Ref Hardening code review.
- Approved plan: `docs/host/p9-5-pre-p10-hardening-plan.md` section S8.
- Implementation artifact: `docs/reviews/p9-5-s8-engine-wait-confirmation-matching-ref-implementation-20260517.md`.
- Reviewed files: `dayu/host/engine_ingest.py`, `tests/host/test_engine_ingest_mapping.py`, `dayu/host/README.md`, `tests/README.md`.
- No code, tests, or artifacts were modified.

## Scope Adherence Verification

### Confirmed: plan boundaries honored

- All changes within S8 allowed files: `dayu/host/engine_ingest.py`, `tests/host/test_engine_ingest_mapping.py`, `dayu/host/README.md`, `tests/README.md`.
- `dayu/host/waiting.py` 与 `dayu/host/tool_runtime.py` 未修改——仅通过现有 `DefaultHostToolAwaitingAcceptPort` / `DefaultHostResolveWaitService` 构造测试中的 accepted refs 前提。
- 无 Engine contract 修改：所有新 import 来自已有 `dayu.engine.contracts`、`dayu.contracts.tool_await` 与 Host 内部 `dayu.host.durable` 模块。

### Confirmed: no prohibited semantics introduced

| 语义 | 状态 |
|---|---|
| RemoteProxy / wire protocol | 未引入 |
| Exactly-once event delivery | 未引入 |
| Callback endpoint | 未引入 |
| Poller loop / physical external cancel | 未引入 |
| Recovery / P11 orphan recovery | 未引入 |
| New public facade / error code | 未引入 |
| Host/Engine contract 修改 | 未引入——Engine `TOOL_AWAITING`/`RUN_SUSPENDED` 契约不变 |
| 新状态机状态 | 未引入 |

## Findings

未发现实质性问题。

## Review Point Checklist

### 1. TOOL_AWAITING / RUN_SUSPENDED 是否只能在 Host durable 全量匹配时记为 confirmation

**通过。**

`_validate_waiting_confirmation()` (engine_ingest.py:1252-1307) 执行五层逐级校验，全部通过才返回 `accepted=True`：

| 层级 | 校验内容 | 代码位置 |
|---|---|---|
| L1 状态 | Run `WAITING` + Attempt `SUSPENDED` | 1276-1281 |
| L2 wait record | 存在唯一 active wait record，match attempt_id + execution_id | 1282-1292 |
| L3 wait status | wait record status 必须是 `WAITING`（非 resolved/cancelled） | 1293-1296 |
| L4 canonical refs | `TOOL_AWAITING` + `RUN_WAITING` + `ATTEMPT_SUSPENDED` 三个 canonical fact 全部存在、EventLog row identity 匹配 envelope、wait record 的 created/updated event refs 指向正确 row | 1297-1309; `_accepted_waiting_refs_or_none` 1356-1419 |
| L5 Engine record | Engine `ToolAwaitingData.record` / `RunSuspendedData.awaiting_records[0]` 的 tool_call_id、tool_name、await_kind、resume_token、deadline、snapshot 全部匹配 wait record 与 `TOOL_AWAITING` payload | `_engine_awaiting_record_mismatch` 1624-1677 |

任一不匹配返回 `_WaitingConfirmationCheck(accepted=False, mismatch_reason=...)`。

### 2. missing/mismatch/wrong attempt/wrong execution/old Attempt late confirmation 是否只 diagnostic/rejection，不创建 wait record、不推进 WAITING、不追加 canonical tool fact

**通过。**

所有失败路径均只写 diagnostic event，不执行状态推进路径分析：

| 失败场景 | 拦截点 | 写入内容 | 测试 |
|---|---|---|---|
| wrong attempt_id (envelope 与 durable 不匹配) | `_validate_durable_context` → `stale_execution_id` | diagnostic `ENGINE_EVENT_REJECTED` | `test_waiting_confirmation_wrong_attempt_identity_is_rejected` |
| wrong execution_id (envelope 与 durable 不匹配) | `_validate_durable_context` → `stale_execution_id` | diagnostic `ENGINE_EVENT_REJECTED` | `test_waiting_confirmation_wrong_execution_identity_is_rejected` |
| wait 已 resolved 后的 old Attempt late confirmation | `_late_rejection_reason` → `terminal_already_closed` | diagnostic `ENGINE_EVENT_REJECTED` | `test_old_attempt_late_waiting_confirmation_is_rejected_after_resolve` |
| Engine awaiting record 与 wait record 不匹配 | `_validate_waiting_confirmation` → reason=`awaiting_spec_mismatch` | diagnostic `ENGINE_EVENT_DIAGNOSTIC`，`waiting_confirmation_accepted: false` | `test_tool_awaiting_rejects_mismatched_engine_record_without_state_change` |

`_confirm_waiting_engine_event()` (line 766-825) 在所有路径下只调用 `_append_diagnostic_event()`——写入 EventClass `DIAGNOSTIC`，不创建 canonical fact、不调用 `create_wait_record`、不调用任何 state transition helper。docstring 明确："写 Engine 等待事件确认 diagnostic，不改变 Host wait 状态。"

测试中关键断言验证不变量：
- `_canonical_tool_event_count(store.transaction_runner) == 1`——只有 accept path 创建的 canonical fact，Engine event 不新增
- `run_status == RunStatus.WAITING` + `attempt_status == AttemptStatus.SUSPENDED`——状态由 accept path 设定，不被 Engine event 改变

### 3. 是否违反 Host/Engine 边界、引入 Engine contract 修改、RemoteProxy/exactly-once/recovery/callback/poller 语义

**通过。**

- Engine contract 不变：所有 Engine 侧 import 来自已有公共契约 (`dayu.engine.contracts.engine_events` 的 `ToolAwaitingData`、`RunSuspendedData`、`RUN_SUSPENDED_REASON_TOOL_AWAITING`)，无新增 Engine 类型或接口
- Host 侧 import 来自 `dayu.host.durable.state`（`read_active_wait_records_for_run`、`WaitRecordRow` 等）和 `dayu.host._event_payload`（`_payload_object`、`_required_payload_text`）——均为主机内部模块
- `dayu.contracts.tool_await` 的 `ToolAwaitSnapshot` 是层中立 shared contract，不属于 Engine 专属
- 全文搜索 S8 diff：无 "RemoteProxy"、"exactly-once"、"recovery"、"callback"、"poller"、"orphan"、"wire protocol"
- S8 通过 envelope identity（session_id/run_id/attempt_id/execution_id）做校验，不依赖 in-process object identity——符合 plan "Keep LocalProxy semantics compatible with future RemoteProxy"

### 4. 是否符合 AGENTS：无 Any/object/无类型签名、中文 docstring、README 只同步当前行为

**通过。**

- 所有新增函数、dataclass 字段均有完整类型注解，无 `Any`/`object`/无类型参数/无类型返回值：
  - `_WaitingConfirmationCheck` — `accepted: bool`, `wait_record: WaitRecordRow | None`, `mismatch_reason: str | None`
  - `_AcceptedWaitingRefs` — `tool_awaiting_payload: Mapping[str, JsonValue]`
  - `_validate_waiting_confirmation()` — 全类型参数，返回 `_WaitingConfirmationCheck`
  - 所有 `_*_matches_wait` 函数均全类型签名，使用 `Mapping[str, JsonValue]`（代码库现有 pattern）
- 新增 10 个顶层函数、1 个 dataclass，全部有中文 docstring，包含 `:param`/`:returns`/`:raises`
- `dayu/host/README.md` 变更：只写当前行为——"只在 envelope identity、当前 WAITING/SUSPENDED 状态、active wait record、最新 canonical refs 与 Engine awaiting record 相互匹配时记为已确认；缺失或不匹配只写未确认 diagnostic/rejection"
- `tests/README.md` 变更：补充 "Engine awaiting confirmation diagnostic 与 accepted wait refs 匹配"

### 5. 测试是否覆盖 S8 要求

**通过。** S8 plan 要求覆盖 6 类场景，实际覆盖如下：

| Plan 要求 | 测试 | 覆盖确认 |
|---|---|---|
| accepted refs replay | `test_tool_awaiting_confirms_only_matching_host_accepted_wait_refs` | ✓ 真实 `DefaultHostToolAwaitingAcceptPort` 路径 + Engine ingest，断言 `waiting_event_confirmation` |
| accepted refs replay (RUN_SUSPENDED) | `test_run_suspended_confirms_only_matching_host_accepted_wait_refs` | ✓ 同上，断言 `ATTEMPT_SUSPENDED` 计数 =1 |
| mismatched Engine awaiting record | `test_tool_awaiting_rejects_mismatched_engine_record_without_state_change` | ✓ `await_spec` 不匹配 → `waiting_event_without_host_accepted_refs`，无状态变更 |
| wrong attempt | `test_waiting_confirmation_wrong_attempt_identity_is_rejected` | ✓ `stale_execution_id` rejection |
| wrong execution_id | `test_waiting_confirmation_wrong_execution_identity_is_rejected` | ✓ `stale_execution_id` rejection |
| old Attempt late confirmation | `test_old_attempt_late_waiting_confirmation_is_rejected_after_resolve` | ✓ 真实 `resolve_wait` 后 late TOOL_AWAITING → `terminal_already_closed` |

所有测试通过真实 `EngineEventIngestor.ingest()` 入口执行，不走内部 shortcut。测试使用 `DefaultHostToolAwaitingAcceptPort` 与 `DefaultHostResolveWaitService` 构造真实 durable 前提，再以 `EngineEventCandidate` 触发 ingest，验证完整链路。

## Open Questions

无。

## Residual Risk

- `_validate_waiting_confirmation` 对 active wait records 的筛选依赖 `attempt_id` 精确匹配（line 1287: `wait_record.attempt_id == context.attempt.attempt_id`）。若未来支持同一 Run 下多 active wait（当前不变量为单 active wait），筛选与 `len(active_waits) != 1` 拒绝逻辑需重新设计。
- `_accepted_waiting_refs_or_none` 使用 `read_latest_run_event_by_type` 读取 canonical facts——只取最新一条，不校验事件插入顺序（TOOL_AWAITING 应先于 RUN_WAITING 先于 ATTEMPT_SUSPENDED）。当前 ToolRuntime accept path 在同一事务内按序写入，事件序号保证单调性，但未交叉校验 `event_sequence` 顺序。如果未来允许乱序写入或不同事务分批写入 canonical facts，需补充事件顺序校验。
- S8 未新增 `ToolAwaitingData` / `RunSuspendedData` 的 Engine contract 字段。Engine 事件仍不携带 Host wait refs——确认仍依赖 Host 事务内回读 durable accepted refs，保持了 Engine 契约独立性但增加了 Host 事务内读负载。
- `_engine_awaiting_record_mismatch` 对 `RunSuspendedData` 只取第一条 `awaiting_records`（line 1653: `record = data.awaiting_records[0]`）。当前 Engine 的 RUN_SUSPENDED 在 reason=`tool_awaiting` 时仅承载单个 awaiting record，但若未来 Engine 变更多记录承载，该假设可能断裂。

## Summary

- **Blocking findings**: 0
- **Non-blocking findings**: 0
- **五项审查点**: 全部通过
- **测试**: 38 passed, 0 failed (`pytest tests/host/test_engine_ingest_mapping.py tests/host/test_wait_awaiting_accept.py tests/host/test_phase7_waiting_integration.py tests/host/test_wait_cancel_late_result.py`)
- **类型检查**: pyright 0 errors, 0 warnings, 0 informations
- **diff check**: 通过
