# WU-SEMANTIC-OWNERSHIP-01 P3-E S2 Fix Re-Review — AgentDS

## Scope

- Mode: current changes (uncommitted workspace diff vs HEAD)
- Branch: `phaseflow/host-issues-control`
- Base: `HEAD` (uncommitted staged changes)
- Output file: `docs/reviews/wu-semantic-ownership-01-p3-e-s2-rereview-ds.md`
- Reviewed fix artifact: `docs/reviews/wu-semantic-ownership-01-p3-e-s2-fix-codex.md`
- Controller adjudication: `docs/reviews/wu-semantic-ownership-01-p3-e-s2-code-review-controller-adjudication.md`
- Controller validation: `docs/reviews/wu-semantic-ownership-01-p3-e-s2-fix-controller-validation.md`
- Re-reviewed fix: `P3-E-S2-CR-F01` (accepted from AgentMiMo residual risk; controller plan-conformance audit)
- File in scope: `tests/host/test_accepted_result_projection.py` (only the newly added test)
- Production code: 未修改（本 fix gate 仅补测试）

## Closure Verdict

### P3-E-S2-CR-F01 — CLOSED ✅

**要求**: 新增 focused test，直接证明 `event_payload_unavailable → LOST`。

**逐项验证**:

#### 1. 是否新增 focused test

`tests/host/test_accepted_result_projection.py:700-747`: `test_projection_missing_event_payload_maps_lost_with_diagnostic` ✅

#### 2. 错误是否发生在 projection EventLog payload read boundary

测试构造路径（`tests/host/test_accepted_result_projection.py:708-738`）：

- 先通过 `PayloadStore().write_sqlite_payload(...)` 写入合法 SQLite payload descriptor（行 718-728），其 `payload_json` 为 `["not-object"]`（list，非 object/dict）
- `TOOL_RESULT_ACCEPTED` EventLog row 的 `payload={}`，但 `payload_ref` 和 `payload_digest` 指向该 list payload（行 730-738）
- `project_accepted_tool_result(transaction, row)` 调用进入 `_result_event_payload(...)`（`dayu/host/accepted_result_projection.py:255-281`）
- `resolved_payload is None` → 走 `event_payload_object(transaction, result_row, ...)` 读取路径
- `event_payload_object` 通过 descriptor 读取 payload JSON，得到 `["not-object"]`（list）
- list 不是 `Mapping` → 校验失败 → 抛出 `HostDurableError`
- 在 `_result_event_payload` 行 280-281 被捕获 → 返回 `({}, (_DIAGNOSTIC_EVENT_PAYLOAD_UNAVAILABLE,))`

错误链完全位于 projection EventLog payload 读取与校验边界（`_result_event_payload` → `event_payload_object`），不是 append-time FK 级别。Fix artifact 明确记录了首次尝试被 FK 拦截后改为合法 descriptor + 非 object payload 的迭代过程。✅

#### 3. 是否断言 `AcceptedToolResultStatus.LOST`

`tests/host/test_accepted_result_projection.py:746`: `assert projection.status is AcceptedToolResultStatus.LOST` ✅

#### 4. 是否断言 `event_payload_unavailable` diagnostic

`tests/host/test_accepted_result_projection.py:747`: `assert "event_payload_unavailable" in projection.diagnostic_reasons` ✅

#### 5. 是否保留 `result_payload_unavailable` coverage

`tests/host/test_accepted_result_projection.py:697`: `assert "result_payload_unavailable" in missing_projection.diagnostic_reasons` — 位于 `test_projection_handles_missing_result_descriptor_and_missing_payload` 测试中，未被修改 ✅

#### 6. 是否有新 material finding

无。本次仅新增一个测试函数；无生产代码修改；既有测试断言未退化；production code 中 `_result_event_payload` 的 `HostDurableError` 捕获 → `event_payload_unavailable` 路径和 `_accepted_status` 的 diagnostic → `LOST` 映射未改变。✅

## New Material Findings

无。

## Blocking Questions

无。

## Residual Risk

无新增 residual risk。既有 S2 residual risk 列表不变：

- `UNKNOWN` 在 Read API 中映射为 `FAILED/ERROR` severity 是 pre-existing consumer 策略，非本次引入。
- External callback 兼容性（旧 bare-string `provider_status_ref` 收到 `malformed_payload`）是 S2 fail-closed 设计意图。

## Conclusion

**PASS**

`P3-E-S2-CR-F01` 修复完整：

- 新增 focused test `test_projection_missing_event_payload_maps_lost_with_diagnostic` 覆盖 `event_payload_unavailable → LOST` 路径；
- 错误发生在 projection `_result_event_payload` payload read boundary（合法 descriptor + 非 object JSON），而非 append-time FK；
- 断言 `projection.status is AcceptedToolResultStatus.LOST` + `"event_payload_unavailable" in diagnostic_reasons`；
- 既有 `result_payload_unavailable` coverage 完整保留；
- 无生产代码修改，无新增 material finding。
