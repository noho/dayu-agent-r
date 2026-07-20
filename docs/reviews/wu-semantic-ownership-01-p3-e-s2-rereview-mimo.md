# WU-SEMANTIC-OWNERSHIP-01 P3-E S2 Fix Re-review

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 P3-E - Tool result, accepted status, wait callback, and Fins direct stream contracts`
- Slice: `S2 - Wait callback typed provider status ref and accepted status projection`
- Fix: `P3-E-S2-CR-F01` — 直接测试 `event_payload_unavailable -> LOST`
- Review target: `tests/host/test_accepted_result_projection.py` 新增 `test_projection_missing_event_payload_maps_lost_with_diagnostic`

## Closure Verdict

### P3-E-S2-CR-F01 — CLOSED

检查点逐项验证：

| 检查点 | 结果 |
|--------|------|
| `tests/host/test_accepted_result_projection.py` 新增 focused test | `test_projection_missing_event_payload_maps_lost_with_diagnostic` (line 700) |
| test 在 projection EventLog payload read boundary 触发错误 | 写入合法 payload descriptor 但 JSON 为 `["not-object"]`（list 非 object），使 `event_payload_object` -> `sqlite_payload_object` 读取时抛 `HostDurableError`，被 `_result_event_payload` 捕获 |
| 断言 `AcceptedToolResultStatus.LOST` | `assert projection.status is AcceptedToolResultStatus.LOST` (line 746) |
| 断言 `event_payload_unavailable` diagnostic | `assert "event_payload_unavailable" in projection.diagnostic_reasons` (line 747) |
| 保留 `result_payload_unavailable` coverage | line 697: `assert "result_payload_unavailable" in missing_projection.diagnostic_reasons` 未变动 |

**设计合理性**：test 通过 `PayloadStore().write_sqlite_payload` 写入合法 descriptor（有 digest、有 payload_id），但 payload JSON 为 list 而非 object。这确保错误发生在 projection owner 的 payload 读取边界（`_result_event_payload` 的 `HostDurableError` catch），而非 append-time foreign key 约束。符合 controller adjudication 要求的"错误发生在 projection EventLog payload read boundary"。

**传播路径**：`event_payload_object` 抛 `HostDurableError` → `_result_event_payload` 捕获并返回 `({}, (_DIAGNOSTIC_EVENT_PAYLOAD_UNAVAILABLE,))` → `_accepted_status` 检测 `_DIAGNOSTIC_EVENT_PAYLOAD_UNAVAILABLE in diagnostics` → 返回 `(AcceptedToolResultStatus.LOST, ())`。

## New Material Findings

0。无新 material finding。

## Blocking Questions

0。

## Residual Risk

- 既有 S2 residual risk 仍成立：`UNKNOWN` 的产品展示策略若需区别于 failed/error，应作为后续 projection/display policy work unit 处理，不能恢复 raw outcome status reconstruction。
- 本次 fix 未修改生产代码，无新增 residual risk。

## Final Conclusion

**PASS**

`P3-E-S2-CR-F01` 正确闭合。新增 test 在 projection payload read boundary 触发 `event_payload_unavailable`，断言 `LOST` status 和 diagnostic，保留既有 `result_payload_unavailable` coverage。17 tests passed，pyright 0 errors，`git diff --check` 通过。
