# P8.5 Plan Fix Report

- **work gate name**: plan fix
- **plan target**: `docs/host/phase8.5-plan.md`
- **source review artifact**: `docs/host/phase8.5-plan-review.md`
- **fix agent**: Dayu Host P8.5 plan-fix agent
- **artifact path**: `docs/host/phase8.5-plan-fix-report.md`

## Accepted Finding IDs

- F01 accepted
- F02 accepted
- F03 accepted
- F04 accepted
- F05 accepted
- F06 accepted
- F07 accepted
- F08 accepted

## Per-Finding Fix Status

| Finding | Status | Fix summary |
| --- | --- | --- |
| F01 | fixed | 将不存在的 `tests/host/test_run_event_serializer.py` 改为 `tests/host/test_phase6_run_event_serializer.py`，补充 `tests/host/test_phase7_contract_serializer.py`；将模糊 projection 测试路径改为 `tests/host/test_phase3_conversation_memory_projection.py`、`tests/host/test_phase7_tool_trace_projection.py`、`tests/host/test_phase7_tool_trace_eventlog_source.py`、`tests/host/test_phase7_tool_trace_jsonl_sink.py` 等具体文件；同步修正 validation commands 中不存在的 `test_phase5_tool_runtime.py`。 |
| F02 | fixed | 明确 RunInput raw payload side store ownership：writer 是 `LocalRunHarness._append_run_input_context_snapshot_fact` 所在 Host durable append 边界；`RunInputContextFactBuilder` 只构造 material / summary；side store write 与 EventLog append 必须共用同一个 `HostStorage.transaction()`；reader 是 `ToolTraceObserver` / trace projection。 |
| F03 | fixed | 明确 SSE partial diagnostic 为 Engine-owned diagnostic data、Host-owned persistence；通过扩展现有 provider/protocol failure data 的 bounded `partial_tool_calls` summary，并由 Host `_event_translation.py` 透传为现有 `PROVIDER_PROTOCOL_ERROR` RunEvent data；禁止新增具体工具名或 provider-specific RunEventType。 |
| F04 | fixed | 明确新增 `DurableRunEventStore.fetch_events_by_session(...)` 或等价强类型 helper；固定 SQL shape 为 `WHERE session_id = ? AND kind = ? AND event_position > ? ORDER BY event_position ASC LIMIT ?`，并要求 `(session_id, kind, event_position)` index。 |
| F05 | fixed | 将原 Slice 7 拆为 Slice 7a（attempt lease contract hardening）和 Slice 7b（attempt adversarial coverage）；明确新增 `AttemptLeaseBusyReason.ATTEMPT_INDEX_CONFLICT = "attempt_index_conflict"`，并在 `AttemptLeaseResult.busy_reason` 等独立字段表达，禁止复用 fencing reason。 |
| F06 | fixed | 删除模糊 `append_many` stop condition，改为明确测试要求：注入 mechanism fact append failure，断言 `HostToolRuntime.execute_tool_call()` 不返回 successful `ToolCompletedOutcome`；当前预期是不需要 `append_many`，若测试反证则 stop and report。 |
| F07 | fixed | 将 corrupt snapshot 诊断收敛为 typed diagnostic，例如 `MemoryRepairDiagnostic(kind=CORRUPT_SNAPSHOT, session_id=..., reason=...)`；要求 WARNING 日志、不自动 delete / overwrite、不阻断其它 missing-row repair，并要求 report / diagnostics 对调用方可见。 |
| F08 | fixed | 显式声明 P8.5 按全新起库处理，旧 `TOOL_FETCH_MORE_*` EventLog 行、旧 inline raw payload 行和 P8 测试库数据丢弃；不写兼容 reader、decoder 或 migration。 |

## Changed Files

- `docs/host/phase8.5-plan.md`
- `docs/host/phase8.5-plan-fix-report.md`

## New Risk / Open Question

- New risk introduced: none.
- New open question introduced: none.
- Blocking open question remaining: none.

## Residual Risk Classification

| Residual risk | Classification |
| --- | --- |
| observer claim lease / outbox / hard-gate | assigned to P15 / issue #28, explicitly not P8.5 |
| P9 Session / Run lifecycle admission | assigned to P9, explicitly not P8.5 |
| P16 public/internal bundle interface freeze | assigned to P16, explicitly not P8.5 |
| old `TOOL_FETCH_MORE_*` EventLog rows | accepted as discarded under fresh P8.5 schema; no compatibility reader / decoder / migration |

## Validation

No production code or tests were modified in this plan-fix pass. No pytest or pyright run was required for the documentation-only fix.

## Completion Signal

All eight controller-accepted findings from `docs/host/phase8.5-plan-review.md` were fixed in the plan artifact. The plan now contains no new open blocking question and is ready for re-review.
