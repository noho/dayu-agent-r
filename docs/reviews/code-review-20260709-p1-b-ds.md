# WU-SEMANTIC-OWNERSHIP-01 P1-B Code Review — AgentDS

## 审查范围

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 P1-B`
- 审查对象：当前 branch 未提交 diff（基于 accepted plan commit `81621bae`）
- 审查维度：correctness / stability / maintainability / semantic ownership drift / over-coupling / missing tests
- Plan 真源: `docs/host/wu-semantic-ownership-01-p1-b-plan.md`
- Design 真源: `docs/host/design.md`

## 动机确认

P1-B 的动机仍然成立：Host terminal event type、terminal status 与 public outbox terminal item set 应该由单一 source-of-truth 定义；`cancel_request_event_id` 不应该从 `RUN_CANCELLING` payload JSON 中 loose parsing 作为 active cancel critical linkage。当前实现正确地解决了这两个语义漂移问题。

## Baseline Validation

```
pytest tests/host/test_durable_schema.py tests/host/test_state_schema.py \
  tests/host/test_run_attempt_transitions.py tests/host/test_engine_ingest_mapping.py \
  tests/host/test_recovery_scan.py tests/host/test_outbox_durable.py -x -q
-> 218 passed

pyright -> 0 errors, 0 warnings, 0 informations

rg -n "_cancel_request_event_id_from_cancelling|
  payload\.get\(\"cancel_request_event_id\"\)|
  event_payload_object\(.*RUN_CANCELLING" dayu/host tests/host
-> 仅 lifecycle_events.py（source-of-truth）、outbox.py（helper-derived）、
   stress_support.py（deferred test support）命中。无生产 critical path 残留。
```

## Ownership Boundary 审计

| 层次 | Owner | 实现状态 |
|---|---|---|
| Producer: terminal facts | `durable/run_transition.py` | 正确 — 所有 cancel 路径写入 typed link |
| Producer: CANCEL_REQUESTED | `admission.py`（已提交，无改动） | 正确 — 已通过 event id 传递给 transition |
| Validator: row/schema | `durable/state.py`, `durable/schema.py` | 正确 — CHECK 约束、row codec、`_validate_terminal_cancel_request_link` |
| Durable truth: EventLog | `durable/run_transition.py` | 正确 — `RUN_CANCELLING` payload 仍含 `cancel_request_event_id` 作为审计可读字段 |
| Durable truth: Run row | `durable/state.py` | 正确 — `cancel_request_event_id` 列/TEXT NULL/FK |
| Projection: Outbox | `outbox.py`, `durable/outbox.py` | 正确 — filter 含 `RUN_LOST`（观察），但 item 创建 skip；latest public terminal sequence 使用 `PUBLIC_OUTBOX_TERMINAL_EVENT_TYPES`（排除 `RUN_LOST`） |
| Projection: Read Model | `read_model.py` | 正确 — terminal status 从 `run_status_for_terminal_event` 派生；`RUN_LOST` → `lost` |
| Projection: Tool Trace | `tool_trace.py` | 正确 — 使用 `HOST_RUN_LIFECYCLE_EVENT_TYPES` |
| Closeout: Engine ingest | `engine_ingest.py` | 正确 — typed link 读取；`active_cancel_closeout_in_transaction` 校验 link |
| Closeout: Watchdog | `run_transition.py` | 正确 — 从 typed link 读，不从 payload 解析 |
| Closeout: Dispatch | `dispatch.py` | 正确 — `_read_linked_cancel_requested_event` 使用 `read_cancel_requested_event_from_run_link` |
| Closeout: Recovery | `recovery.py` | 正确 — `_has_accepted_cancel_fact` 使用 typed link |
| User/LLM visible: Read API | `read_api.py` | 正确 — `HostEvent` terminal 映射使用 `parse_host_run_event_type` |

## Findings

### P1B-CODE-DS-F01 — Stale docstrings in watchdog helper functions

- **文件/行号**: `dayu/host/durable/run_transition.py:4373,4424,4474`
- **严重性**: LOW
- **Root cause**: 三个 watchdog helper 函数（`_active_watchdog_attempt_cancelled_event_request`、`_active_watchdog_run_cancelled_event_request`、`_active_watchdog_cancelled_payload`）的 `cancel_request_event_id` 参数 docstring 仍写"从 `RUN_CANCELLING` payload 读取的 cancel request id"。实际调用方（line 2351, 2363）传入的是 `cancel_requested.event_id`，来自 `read_cancel_requested_event_from_run_link`（typed Run row link），而非 payload JSON 解析。
- **Owner boundary**: 这三个 helper 函数是 durable transition 层的 EventLog append request 构造器，负责写入审计可读 payload。
- **建议修复位置**: 三处 docstring 应改为"由 typed `RunRow.cancel_request_event_id` 回查得到的 `CANCEL_REQUESTED` event id"或等价表述。
- **是否 blocking**: NO — 仅为文档与实现不一致，不影响 correctness 或 stability。建议在任一后续 fix gate 修复。
- **验证方法**: 人工审查 docstring 文本。

### P1B-CODE-DS-F02 — CHECK 约束缺少显式 integrity error 测试

- **文件/行号**: `dayu/host/durable/schema.py:533-540` + `tests/host/test_durable_schema.py`
- **严重性**: LOW
- **Root cause**: `host_runs` 新增 CHECK 约束 `status NOT IN ('cancelling', 'cancelled') OR cancel_request_event_id IS NOT NULL` 是 SQLite 层的防御。`_insert_run_tx` 在 `test_state_schema.py` 为 CANCELLING/CANCELLED 状态写入了 `cancel_request_event_id`（happy path），但没有显式测试 INSERT CANCELLING run without cancel link 会触发 SQLite integrity error。CHECK 是 SQLite 层强制执行，不会被绕过，但缺少防御深度。
- **Owner boundary**: Schema DDL / CHECK 约束属于 durable schema layer；测试应由 `test_durable_schema.py` 或 `test_state_schema.py` 验证。
- **建议修复位置**: 在 `test_durable_schema.py` 或 `test_state_schema.py` 添加测试：事务内 INSERT host_runs with status='cancelling' and cancel_request_event_id=NULL，验证 `sqlite3.IntegrityError`。
- **是否 blocking**: NO — CHECK 由 SQLite 强制，不会被代码绕过。列为 residual risk。
- **验证方法**: 新增测试后 `pytest tests/host/test_durable_schema.py tests/host/test_state_schema.py`。

### P1B-CODE-DS-F03 — read_api.py 中 HostRunEventType 与私有常量混用

- **文件/行号**: `dayu/host/read_api.py:1144-1153` vs `dayu/host/read_api.py:1135-1137`
- **严重性**: LOW
- **Root cause**: `_run_lifecycle_activity` 函数中，terminal events（line 1144+）使用 `HostRunEventType.RUN_SUCCEEDED.value` 做字符串比较，但非 terminal lifecycle events（line 1135）仍使用模块级私有常量 `_EVENT_TYPE_RUN_ACCEPTED`、`_EVENT_TYPE_RUN_QUEUED`。同一函数内两种引用模式存在不一致。Plan section 5.1 residual risk 已声明"Non-terminal Run lifecycle constants are only migrated in P1-B where a touched consumer needs the shared lifecycle helper"，此不一致不违反 plan 约束。
- **Owner boundary**: `read_api.py` 是 HostEvent 投影的 read-side 消费者，负责把 EventLog event type 映射为 UI 可读 activity。
- **建议修复位置**: 可统一使用 `HostRunEventType.RUN_ACCEPTED.value` 替换 `_EVENT_TYPE_RUN_ACCEPTED` 等。非 P1-B scope，可推迟到后续 work unit。
- **是否 blocking**: NO — 仅为 code style consistency，不影响 correctness。列为 deferred cleanup。
- **验证方法**: 人工审查。

### P1B-CODE-DS-F04 — Tool trace canonical event filter expansion 未文档化

- **文件/行号**: `dayu/host/tool_trace.py:215-224`
- **严重性**: INFO
- **Root cause**: 旧 `_CANONICAL_EVENT_TYPES` 只包含 `RUN_WAITING` + 四个 terminal events；新版本使用 `*event_type_values(HOST_RUN_LIFECYCLE_EVENT_TYPES)`，增加了 `RUN_ACCEPTED`、`RUN_QUEUED`、`RUN_STARTED`、`RUN_CANCELLING`、`RUN_RECOVERING`。这是正确的语义收敛（tool trace 应观察完整 Run lifecycle），但实现 artifact 和 controller validation 中未记录此 expansion。
- **Owner boundary**: Tool trace projection consumer owns canonical event filter 的组合。
- **建议修复位置**: 在 implementation artifact 中记录此 behavioral expansion。非生产代码修改。
- **是否 blocking**: NO — behavior 符合 plan section 5.1 "Tool Trace 使用 Host lifecycle helper 组合 canonical event filter"。列为 awareness note。

### P1B-CODE-DS-F05 — `cancel_cancelling_run_row` 不显式保留 cancel link

- **文件/行号**: `dayu/host/durable/state.py:3471-3511`
- **严重性**: INFO
- **Root cause**: `cancel_cancelling_run_row` 把 Run 从 CANCELLING 推到 CANCELLED 时，UPDATE SET 子句不包含 `cancel_request_event_id`。该字段在 `mark_run_cancelling_row` 时已写入，且 WHERE 子句要求 `status = 'cancelling'`，CHECK 约束保证 cancelling Run 的 `cancel_request_event_id` 非空，因此当前语义正确。但缺少显式保留语义，未来若有人修改 CHECK 约束或 WHERE 子句可能引入不一致。
- **Owner boundary**: `cancel_cancelling_run_row` 是 Run terminal mutator，属于 durable state layer。
- **建议修复位置**: 可在 docstring 注明"`cancel_request_event_id` 已由 CANCELLING 状态进入时固定，本 mutator 不重写"。或在 UPDATE 中显式 `cancel_request_event_id = cancel_request_event_id`（无行为变化）。
- **是否 blocking**: NO — 当前语义正确。列为 design clarity note。

## Propagation Audit 确认

### Terminal event/status 传播

| 步骤 | 实现 | 验证 |
|---|---|---|
| 1. Producer → EventLog | `durable/run_transition.py` append 四个 terminal event types | 已有测试覆盖 |
| 2. EventLog → Run row | `durable/state.py` terminal_status、terminal_event_id/sequence | 已有测试覆盖 |
| 3. Run row → Read Model | `read_model.py` 使用 `run_status_for_terminal_event`，`RUN_LOST` → `lost` | 已有测试覆盖 |
| 4. Run row → Read API/HostEvent | `read_api.py` 使用 `parse_host_run_event_type` 做 terminal mapping | 已有测试覆盖 |
| 5. Run row → Tool Trace | `tool_trace.py` 使用 `HOST_RUN_LIFECYCLE_EVENT_TYPES` | 已有测试覆盖 |
| 6. EventLog → Outbox | `outbox.py` filter 观察 `HOST_RUN_TERMINAL_EVENT_TYPES`（含 `RUN_LOST`），item 创建 skip `RUN_LOST` | 新测试 `test_projection_state_ignores_run_lost_eventlog_tail` 覆盖 |
| 7. EventLog → Durable Outbox latest terminal | `durable/outbox.py` 使用 `PUBLIC_OUTBOX_TERMINAL_EVENT_TYPES`（排除 `RUN_LOST`） | 已有测试覆盖 |

### Cancel linkage 传播

| 步骤 | 实现 | 验证 |
|---|---|---|
| 1. Admission → CANCEL_REQUESTED | `admission.py` append event（已提交） | 已有测试覆盖 |
| 2. Transition → Run row link | `mark_run_cancelling_row` / all direct cancel mutators 写入 `cancel_request_event_id` | 已有测试覆盖 |
| 3. Run row → Engine ingest | `_close_active_cancel` 使用 `read_cancel_requested_event_from_run_link` | `test_run_cancelled_with_malformed_active_cancel_payload_uses_typed_link` 覆盖 |
| 4. Run row → Watchdog | `active_cancel_watchdog_closeout_in_transaction` 使用 typed link | `test_active_cancel_watchdog_closeout_uses_typed_link_with_malformed_payload` 覆盖 |
| 5. Run row → Dispatch | `_read_linked_cancel_requested_event` 使用 typed link | 已有测试覆盖 |
| 6. Run row → Recovery | `_has_accepted_cancel_fact` 使用 typed link | `test_scan_malformed_cancelling_payload_uses_typed_cancel_link` 覆盖 |
| 7. Closeout → CANCELLED EventLog | payload 仍含 `cancel_request_event_id`（审计可读） | 已有测试覆盖 |

## LLM-facing 文本约束检查

`lifecycle_events.py` 的 `event_type` 字符串值（"RUN_ACCEPTED"、"RUN_CANCELLED" 等）是 EventLog durable 事实，也是 durable state `status` 列的值，不是 LLM-facing 文本。`run_status_for_terminal_event` 和 `host_terminal_status_for_terminal_event` 返回的是 `RunStatus` / `HostTerminalStatus` enum，这些是 Host 内部治理标识，当前不进入 LLM prompt 或 tool schema。无需改写。

## Residual scan 分类确认

```
dayu/host/lifecycle_events.py:       source-of-truth（正确）
dayu/host/outbox.py:80:              helper-derived from source-of-truth（正确）
dayu/host/durable/outbox.py:72:      helper-derived from source-of-truth（正确）
tests/host/stress_support.py:106-111: deferred test support（正确，不在 P1-B scope）
```

- `tests/host/stress_support.py` 保留的 terminal tuples 是 stress test 内联常量，用于 diagnostic 查询和验证。这些测试模块不属于 Host projection consumer，将其迁移到 `lifecycle_events` 不会消除任何语义漂移。分类为 deferred test support 合理。
- `dayu/host/durable/run_transition.py` 保留的 `_EVENT_TYPE_RUN_CANCELLING`：仅用于写 EventLog（line 3997）和读最新 RUN_CANCELLING 行做审计上下文（line 2328），不做 critical linkage 解析。符合 plan 要求。

## README / Design 更新检查

- **`docs/host/design.md`**: 在 Run 状态迁移矩阵后新增三段自足结构（Host terminal set、public outbox terminal item set、non-public terminal skip/diagnostic behavior）。插入位置合理，语义完整。✅
- **`dayu/host/README.md`**: 更新了三处：cancel paragraph 添加 typed `cancel_request_event_id` 说明；HostEvent 段落添加 `RUN_LOST` outbox 区分说明；cancel lifecycle 段落添加 typed link 说明。符合 README `Agent更新约束` 的读者职责。✅
- **`tests/README.md`**: 无变化。P1-B 未新增 test layer 或运行约定。✅
- **根 `README.md`、`dayu/README.md`**: 未触发（无用户可见入口变化、无分层边界变化）。✅

## 结论: **PASS-WITH-RISKS**

P1-B implementation 正确解决了两个语义所有权问题：

1. **Terminal event/status contract**: `lifecycle_events.py` 成为单一 source-of-truth，所有 consumer 删除私有 terminal set 拷贝。`RUN_LOST` 正确区分：Host terminal/lifecycle truth（含 lost），public outbox terminal item（不含 lost），outbox watermark 不会被 `RUN_LOST` 产生假 lag。

2. **Cancel durable linkage**: `host_runs.cancel_request_event_id` 成为 typed durable link，所有 critical closeout path（engine ingest、watchdog、dispatch、recovery）从 typed link 读取，不再从 `RUN_CANCELLING` payload JSON 解析。`_cancel_request_event_id_from_cancelling` 已删除。malformed payload 不再阻塞 cancel closeout。

### Residual risks

| Risk | Severity | Mitigation |
|---|---|---|
| F01: 3 watchdog helper docstrings stale | LOW | Fix in follow-up gate. No correctness impact. |
| F02: CHECK constraint missing explicit integrity error test | LOW | CHECK enforced by SQLite. Defense depth only. |
| F03: `read_api.py` mixed HostRunEventType / private constants | LOW | Consistency cleanup, deferrable to later WU. |
| F04: Tool trace canonical event expansion undocumented | INFO | Add note to implementation artifact. |
| F05: `cancel_cancelling_run_row` cancel link preservation implicit | INFO | Add docstring clarity. Current semantics correct. |

### Test gaps (non-blocking)

- CHECK constraint integrity error test（F02）
- `tool_trace.py` canonical event filter 变更未触发现有任何测试失败，说明该 expansion 不影响 projection 行为正确性，但缺少显式的"tool trace 应观察完整 lifecycle events"断言

### Uncovered by current tests (reviewer note, not a finding)

- `active_cancel_closeout_in_transaction` 中 `cancel_requested.event_id != request.cancel_request_event_id` mismatch 路径（line 2198-2206）未有显式单元测试——即 engine ingest 传入的 `cancel_request_event_id` 与 Run row typed link 不一致的场景。当前 engine ingest 从同一个 Run row 读取 typed link 后立即传入，在单事务内不可能出现 mismatch。但如果未来 engine ingest 从其他来源构造 `ActiveCancelCloseoutInput`，此路径需要测试覆盖。

---

*AgentDS review completed 2026-07-09. No blocking finding. Proceed to aggregate review and controller adjudication.*
