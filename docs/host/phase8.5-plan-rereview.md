# P8.5 Plan Re-Review Artifact

- **re-review gate name**: plan re-review
- **reviewed target**: `docs/host/phase8.5-plan.md` (post-fix)
- **source review artifact**: `docs/host/phase8.5-plan-review.md`
- **source fix artifact**: `docs/host/phase8.5-plan-fix-report.md`
- **re-reviewer**: plan re-review agent (Claude)
- **re-review date**: 2026-05-11
- **re-reviewer conclusion**: **pass**
- **artifact path**: `docs/host/phase8.5-plan-rereview.md`

## Per-Finding Verification

### F01 — test file paths

- **原始问题**: plan 引用不存在的 `tests/host/test_run_event_serializer.py`，projection 测试路径模糊。
- **修复承诺**: 改为 `tests/host/test_phase6_run_event_serializer.py`，补充 `tests/host/test_phase7_contract_serializer.py`，明确 projection 测试为 `test_phase3_conversation_memory_projection.py`、`test_phase7_tool_trace_projection.py`、`test_phase7_tool_trace_eventlog_source.py`、`test_phase7_tool_trace_jsonl_sink.py` 等。
- **验证**: plan §5 Affected Files 已更新为 `tests/host/test_phase6_run_event_serializer.py` 和 `tests/host/test_phase7_contract_serializer.py`。Slice 2/3/6 validation commands 使用具体文件路径。与 `Glob("tests/host/test_*serializer*.py")` 和 `Glob("tests/host/test_phase7_*.py")` 返回结果一致。
- **判定**: **fixed**

### F02 — RunInput raw payload side store ownership

- **原始问题**: side store writer / reader / transaction ownership 未定义。
- **修复承诺**: 明确 writer 是 `LocalRunHarness._append_run_input_context_snapshot_fact` 所在 Host durable append 边界；`RunInputContextFactBuilder` 只构造 material / summary；side store write 与 EventLog append 共用同一个 `HostStorage.transaction()`；reader 是 `ToolTraceObserver` / trace projection。
- **验证**: plan §2.4 point 3 和 §7 已更新。明确 `RunInputContextFactBuilder` 产出 material，side store write 在 `LocalRunHarness._run_to_store` attempt 生命周期事务内完成，与 EventLog fact 共用 `HostStorage.transaction()`。stop condition：无法同事务时停下回报。
- **判定**: **fixed**

### F03 — SSE partial tool-call diagnostic layer boundary

- **原始问题**: diagnostic fact 是 Engine-owned 还是 Host-owned 未裁决。
- **修复承诺**: 明确为 Engine-owned diagnostic data、Host-owned persistence；通过扩展现有 provider/protocol failure data 的 bounded `partial_tool_calls` summary，由 Host `_event_translation.py` 透传为现有 `PROVIDER_PROTOCOL_ERROR` RunEvent data；禁止新增具体工具名或 provider-specific RunEventType。
- **验证**: plan Slice 6 已重写。diagnostic 定义为 Engine `RunnerHTTPErrorData` 或 `RunnerProtocolFailureData` 扩展 bounded `partial_tool_calls` summary 字段，Host `_event_translation.py` 翻译为 `PROVIDER_PROTOCOL_ERROR` RunEvent。不新增 RunEventType。Engine public contract 扩展范围受限。
- **判定**: **fixed**

### F04 — durable memory repair fetch helper

- **原始问题**: `_fetch_canonical_events_for_session()` 仍是全库扫描 + client-side 过滤，plan 未指定 helper SQL shape。
- **修复承诺**: 新增 `DurableRunEventStore.fetch_events_by_session(...)` 或等价强类型 helper；SQL shape 固定为 `WHERE session_id = ? AND kind = ? AND event_position > ? ORDER BY event_position ASC LIMIT ?`；索引 `(session_id, kind, event_position)`。
- **验证**: plan Slice 3 已明确 helper 方法签名、SQL shape 和索引定义。与 `_conversation_memory_durable.py:369-402` 当前全库扫描实现形成直接对照。
- **判定**: **fixed**

### F05 — Slice 7 粒度和 BUSY reason

- **原始问题**: Slice 7 过粗（6 个子任务），BUSY reason 缺少具体枚举值，是 open design choice。
- **修复承诺**: 拆为 Slice 7a（attempt lease contract hardening）和 Slice 7b（attempt adversarial coverage）；新增 `AttemptLeaseBusyReason.ATTEMPT_INDEX_CONFLICT = "attempt_index_conflict"`，在 `AttemptLeaseResult.busy_reason` 独立字段表达，禁止复用 fencing reason。
- **验证**: plan §8 已拆为 Slice 7a 和 Slice 7b。7a 覆盖 `AttemptFencingReason.RUN_ID_MISMATCH`、`AttemptLeaseBusyReason.ATTEMPT_INDEX_CONFLICT`、`lease_context` 参数校验。7b 覆盖 adversarial tests。枚举值名和字段位置明确。
- **判定**: **fixed**

### F06 — append_many stop condition

- **原始问题**: "不先做 append_many" stop condition 缺少可验证基线，无法注入 cursor fact 失败场景。
- **修复承诺**: 删除模糊 stop condition，改为明确测试要求：注入 mechanism fact append failure，断言 `HostToolRuntime.execute_tool_call()` 不返回 successful `ToolCompletedOutcome`；当前预期不需要 `append_many`，若测试反证则 stop and report。
- **验证**: plan Slice 2 implementation prompt point 7 已重写。明确注入方法：在 `_append_fetch_completed` 或等价路径的 cursor fact append 阶段注入 `sqlite3.DatabaseError`，断言 `_fetch_more` 抛出异常。与 `_tool_runtime.py:840` 代码事实一致（cursor append 在返回前执行）。
- **判定**: **fixed**

### F07 — corrupt snapshot diagnostic

- **原始问题**: corrupt snapshot 处理未收敛：抛异常 vs log vs fail fast 未定义，可能中断 startup_reconcile。
- **修复承诺**: 收敛为 typed diagnostic `MemoryRepairDiagnostic(kind=CORRUPT_SNAPSHOT, session_id=..., reason=...)`；WARNING 日志、不自动 delete / overwrite、不阻断其它 missing-row repair；report / diagnostics 对调用方可见。
- **验证**: plan Slice 3 已更新。定义 `MemoryRepairDiagnostic(kind=CORRUPT_SNAPSHOT, ...)` typed diagnostic，要求 WARNING 日志、不自动 delete/overwrite、不阻断其它 session repair。与 `_conversation_memory_durable.py:517-537` 当前抛异常行为形成对照。
- **判定**: **fixed**

### F08 — 旧 TOOL_FETCH_MORE_* 数据迁移

- **原始问题**: "全新 schema 起库" 但未显式声明旧数据丢弃和不写兼容 reader。
- **修复承诺**: 显式声明 P8.5 按全新起库处理，旧 `TOOL_FETCH_MORE_*` EventLog 行、旧 inline raw payload 行和 P8 测试库数据丢弃；不写兼容 reader、decoder 或 migration。
- **验证**: plan §1 Goal / Success Signal 和 §6 Contract impact 已显式声明。与 `contracts.py:73-75`、`_run_event_serializer.py:1476-1478` 中待删除的条目对应。
- **判定**: **fixed**

## Fix-Introduced Risk Assessment

fix agent 声明未引入新风险或新 open question。逐项验证：

- **新 blocker**: 无。所有 fix 都是对 plan artifact 的澄清和细化，未改变核心架构裁决方向。
- **新 open question**: 无。原有 3 个 open questions（SSE partial diagnostic 边界、BUSY reason 枚举、append_many stop condition）已在 fix 中收敛为明确实现选择。
- **fix 引入的副作用**: 无。fix 仅修改 plan 文档，未修改生产代码或测试代码。

## Residual Risk

| Risk | Owner | Status |
| --- | --- | --- |
| observer claim lease / outbox / hard-gate | P15 / issue #28 | Explicitly not P8.5 |
| `InMemoryRunEventStore` 生产语义收口 | P16 interface freeze | Deferred |
| schema bootstrap 半失败治理 | P15 | Deferred |
| `LocalRunHarness` God Object 膨胀 | P9 / P16 | Deferred |
| `DurableHarnessBundle` public/internal 边界 | P16 | Deferred |
| P15 required projection enforcement | P15 | Deferred |
| `HostStorage.close()` 后台 task 生命周期 | P9 lifecycle | Deferred |

## Conclusion

全部 8 个 accepted findings（F01–F08）均已按 fix report 承诺修复，plan artifact 中对应内容与 fix 描述一致。fix 未引入新 blocker、新 open question 或新风险。原有 3 个 open questions 已在 fix 中收敛为明确实现选择，不再 blocking implementation handoff。

**re-review 结论：pass**。plan 可进入 implementation handoff。
