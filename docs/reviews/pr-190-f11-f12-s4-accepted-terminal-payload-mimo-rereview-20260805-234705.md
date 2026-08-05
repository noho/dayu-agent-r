# Code Review: PR 190 S4.2 accepted terminal payload — MiMo re-review after DS-F01 fix

## Scope

- Mode: current changes (uncommitted, workspace vs baseline)
- Branch: `codex/interactive-oracle`
- Base: `f7957b6343f4647ce0c6058a08e9ae84ab629f30`
- Output file: `docs/reviews/pr-190-f11-f12-s4-accepted-terminal-payload-mimo-rereview-20260805-234705.md`
- Review date: 2026-08-05
- Included scope:
  - 新增 `dayu/host/context_event_payload.py` — durable payload owner
  - 修改 `dayu/host/dispatch.py` — proactive writer 路径
  - 修改 `dayu/host/engine_ingest.py` — reactive writer 路径
  - 修改 `dayu/host/compact_material.py` — consumer 迁移到 resolver
  - 修改 `dayu/host/compaction_terminal.py` — consumer 迁移到 resolver
  - 修改 `dayu/host/projection.py` — `projection_event_view_from_row` 签名变更
  - 修改 `dayu/host/run_input.py` — 7 处 consumer 迁移到 resolver（含 DS-F01 修复）
  - 修改 `dayu/host/durable/tool_trace.py` — Tool Trace compactor response identity
  - 修改 `dayu/host/proactive_compaction.py` — `_project_state` 迁移
  - 新增测试 `test_dispatch_scheduler.py::test_oversized_accepted_compact_terminal_uses_descriptor_truth`
  - 新增测试 `test_engine_ingest_mapping.py::test_reactive_oversized_accepted_terminal_uses_descriptor_truth`
  - 新增测试 `test_run_input_builder.py::test_durable_compact_artifact_provider_resolves_descriptor_payload_and_fails_closed`
  - 测试签名变更（`projection_event_view_from_row` 新增 `transaction` 参数）
  - `dayu/host/README.md` / `tests/README.md` 更新
- Excluded scope: `dayu/host/context_events.py`（零 diff）、oracle/scenario/registry（零 diff）
- Parallel review coverage: 无

## Re-review Context

首轮 MiMo review 未发现实质问题。Controller adjudication 接受了 MiMo 结论，但补充接受了 DS-F01（`DurableCompactArtifactProvider` 遗漏 resolver），并拒绝了 DS-F02 至 DS-F08。AgentCodex 已实施 DS-F01 修复，本 re-review 独立验证：

1. DS-F01 fix 是否在正确 consumer boundary 完整关闭
2. descriptor-backed DurableCompactArtifactProvider refs/digest/evidence 与 corruption fail-closed owner test 是否真实
3. 完整 S4.2 diff 无新 regression、scope drift、兼容/下游补偿
4. controller 拒绝的 DS-F02–F08 裁决直接证据是否仍成立

## DS-F01 Fix Verification

### 1. Fix 位置正确 ✅

**文件**: `dayu/host/run_input.py:1970`
**变更**: `_payload_object(row)` → `resolve_context_compacted_payload(transaction, row)`

- `transaction` 参数已在 `_load_compact_artifact_tx` 签名中（line 1956）
- 与同文件其他 5 处已迁移 consumer 模式一致：
  - `_load_pre_start_compact_artifact` (line 4248)
  - `_memory_projection_payload` (line 5491-5492)
  - `_validate_loaded_compact_view_matches_event` (line 5571)
  - `_compaction_trigger_source_for_compacted_event` (line 5593-5596)
  - `_pre_start_protected_recent_raw_tail` 调用 `_validate_loaded_compact_view_matches_event` (line 4345)

### 2. Owner test 真实覆盖 ✅

**测试**: `test_durable_compact_artifact_provider_resolves_descriptor_payload_and_fails_closed`

- 使用 2048-byte inline threshold 构造 descriptor-backed CONTEXT_COMPACTED
- 通过 `_append_descriptor_backed_current_run_compacted_event` helper 写入真实 artifact-backed terminal
- 断言 `compacted.payload_json == "{}"`（descriptor-backed 时 EventLog 只保存空 object）
- 断言 `payload_ref is not None`（descriptor ref 存在）
- 断言 `PayloadKind.ARTIFACT_REF`（descriptor kind 正确）
- 断言 `descriptor.payload_size_bytes > inline_threshold_bytes`（确认超限外置）
- 断言 `view.compaction_event_ref == compacted.event_id`（event ref 同源）
- 断言 `view.compact_artifact_ref == "compact-artifact:test"`（artifact ref 正确）
- 断言 `view.compact_artifact_digest == _DIGEST_A`（artifact digest 正确）
- 断言 `view.represented_evidence_refs == ("evidence:memory-tool",)`（evidence refs 正确）
- 篡改 `payload_digest` 后断言 `HostDurableError("payload integrity validation failed")`（fail closed）

**测试结果**: `1 passed in 0.34s`

### 3. Test helper 真实性 ✅

`_append_descriptor_backed_current_run_compacted_event`：
- 使用 `store_context_compacted_payload`（与生产 writer 同一函数）
- 写入 `CONTEXT_COMPACTION_REQUESTED` + `CONTEXT_COMPACTED` 两个事件
- 使用 `_compact_payload` 构造真实 canonical payload（含 long summary_text 触发超限）
- 返回 `EventLogRow` 供测试断言

## Complete S4.2 Diff Review

### 4. Proactive/Reactive writer 外置超限完整 payload ✅

**Proactive (`dispatch.py:3285-3325`)**:
- 先构造完整 payload（`build_context_compacted_payload`）
- 调用 `store_context_compacted_payload(transaction, PayloadStore(), event_id=..., payload=...)`
- 将返回的 `payload_storage.event_payload` / `.payload_ref` / `.payload_digest` 原样写入 EventLog
- 不提高 limit，不删字段、截断

**Reactive (`engine_ingest.py:3087-3132`)**:
- 相同模式，使用 `self._payload_store`（与 reactive 路径既有注入一致）
- event_id 使用确定性 `_event_id(context.candidate, ...)` 派生

### 5. 所有消费者统一严格解析 ✅

| 消费者 | 文件 | 迁移状态 |
|--------|------|----------|
| `_validated_compacted_payload` | compact_material.py:2490 | ✅ `resolve_context_compacted_payload` |
| `_strict_terminal_payload` (COMPACTED) | compaction_terminal.py:260 | ✅ `resolve_context_compacted_payload` |
| `_strict_terminal_payload` (FAILED) | compaction_terminal.py:265 | ✅ `payload_object(row)` — inline-only，正确 |
| `_resolved_compactor_response_from_row` (ACCEPTED) | tool_trace.py:667 | ✅ `resolve_context_compacted_payload` |
| `_resolved_compactor_response_from_row` (REJECTED) | tool_trace.py:672 | ✅ `_json_object_from_text(row.payload_json)` — inline-only，正确 |
| `_project_state` (COMPACTED) | proactive_compaction.py:464-466 | ✅ `resolve_context_compacted_payload` |
| `_project_state` (其他) | proactive_compaction.py:467 | ✅ `payload_object(row)` — inline-only，正确 |
| `projection_event_view_from_row` (COMPACTED) | projection.py:715-716 | ✅ `resolve_context_compacted_payload` |
| `projection_event_view_from_row` (其他) | projection.py:718 | ✅ `payload_object(row)` — inline-only，正确 |
| `DurableCompactArtifactProvider._load_compact_artifact_tx` | run_input.py:1970 | ✅ `resolve_context_compacted_payload` (DS-F01 fix) |
| `_load_pre_start_compact_artifact` | run_input.py:4248 | ✅ `resolve_context_compacted_payload` |
| `_memory_projection_payload` (COMPACTED) | run_input.py:5491-5492 | ✅ `resolve_context_compacted_payload` |
| `_memory_projection_payload` (其他) | run_input.py:5493 | ✅ `_payload_object(row)` — inline-only，正确 |
| `_validate_loaded_compact_view_matches_event` | run_input.py:5571 | ✅ `resolve_context_compacted_payload` |
| `_compaction_trigger_source_for_compacted_event` | run_input.py:5593-5596 | ✅ `resolve_context_compacted_payload` |

**未迁移但正确的消费者**（controller 裁决依据仍成立）：
- `read_api._context_compaction_activity` — 只从 payload 读 `failure_reason`（CONTEXT_COMPACTED 无此字段），inline `{}` 与完整 payload 的可观察结果相同
- `context_anchor` — 只判断 `event_type` 是否停止扫描，不解析 payload
- `memory` — 通过上层传入的 `MemoryProjectionEvent.compacted_semantics` 获取数据

### 6. Ref/digest/descriptor/blob corruption fail closed ✅

`resolve_context_compacted_payload` 严格校验链：
1. `event.event_class is not EventClass.CANONICAL_FACT` → `HostDurableError`
2. `event.event_type != CONTEXT_COMPACTED` → `HostDurableError`
3. `(event.payload_ref is None) != (event.payload_digest is None)` → `HostDurableError`
4. `event_payload_object(transaction, event, ...)` → inline parse 或 descriptor/blob 读取
5. `validate_context_compacted_payload(payload)` → canonical contract 校验

任一环节失败都抛出 `HostDurableError`，无 fallback。

### 7. Artifact 与 terminal truth 同源 ✅

Proactive test 验证：
- `compact_artifact_json["accepted_candidate"] == compacted_payload["accepted_candidate"]`
- `view.compact_artifact_ref` / `view.compact_artifact_digest` 与 terminal payload 中的字段一致

### 8. 无第二真源、下游补偿、兼容 shim ✅

- 所有 CONTEXT_COMPACTED 消费者共用 `resolve_context_compacted_payload`
- 无 `hasattr`/`getattr`、loose parsing、fallback、默认值、兼容分支
- `context_event_payload.py` 职责清晰：只做 durable payload 映射，不产生 compact 业务语义
- 无格式 churn（已通过 patch 恢复）

### 9. Background promotion 无 fatal/hang ✅

Proactive test 断言：
- `_event_count(store.transaction_runner, CONTEXT_COMPACTED) == 1`
- `_run_status(store.transaction_runner, seeded.run_id) is RunStatus.RUNNING`
- `scheduler._promotion_drain_task.done() is False`
- `scheduler._health_gate.state is HostExecutionHealthState.READY`
- `not any("critical_task.fatal" in record.getMessage() for record in caplog.records)`

### 10. Controller rejected DS-F02–F08 裁决证据仍成立 ✅

| Finding | 裁决 | 证据验证 |
|---------|------|----------|
| DS-F02 event_id 非确定性 | rejected | `run_write` 使用全事务 rollback，terminal guard 防护；随机 event_id 是既有 proactive 选择 |
| DS-F03 descriptor/blob 非原子 | rejected | 既有 `PayloadStore.write_bounded_json_payload` 属性，非本 slice 新建路径 |
| DS-F04 activity timeline | rejected | `CONTEXT_COMPACTED` 无 `failure_reason`，inline `{}` 与完整 payload 可观察结果相同 |
| DS-F05 ATTEMPT_REJECTED | rejected | 无 descriptor-backed writer，inline-only 路径正确 |
| DS-F06 proactive 非 COMPACTED | rejected | 同 DS-F05 |
| DS-F07 PayloadStore 实例化 | rejected | `PayloadStore` 无实例状态 |
| DS-F08 build 时尺寸防护 | rejected | EventLog 写边界有最终 fail-closed guard |

## Tests and Risk

### 测试覆盖 ✅

| 测试 | 状态 |
|------|------|
| `test_durable_compact_artifact_provider_resolves_descriptor_payload_and_fails_closed` | ✅ 1 passed in 0.34s |
| `test_oversized_accepted_compact_terminal_uses_descriptor_truth` | ✅ passed |
| `test_reactive_oversized_accepted_terminal_uses_descriptor_truth` | ✅ passed |
| 受影响测试（7 个 test 文件） | ✅ 472 passed in 5.36s |
| compact/material/terminal/proactive/projection | ✅ 431 passed in 4.58s |
| pyright | ✅ 0 errors, 0 warnings, 0 informations |

### Residual Risk

1. **`read_api._context_compaction_activity`**: 使用 `_activity_payload_without_descriptor` 只做 inline parse。CONTEXT_COMPACTED 的 inline `{}` 对当前 activity 投影（只读 `failure_reason`）无功能影响。Severity: Low，不影响正确性。

2. **`proactive_compaction.py:964`**: `CONTEXT_COMPACTION_REQUESTED` 使用 `payload_object(row)` — 该 event type 无 descriptor-backed 存储，正确。

## Findings

### 未发现实质性问题

DS-F01 fix 在正确 consumer boundary 完整关闭，descriptor-backed DurableCompactArtifactProvider owner test 真实覆盖 refs/digest/evidence 与 corruption fail-closed。完整 S4.2 diff 无新 regression、scope drift、兼容/下游补偿。Controller 拒绝的 DS-F02–F08 裁决直接证据仍成立。

## Open Questions

无

## Verification Summary

| 验证项 | 结果 |
|--------|------|
| DS-F01 fix 位置正确（run_input.py:1970） | ✅ PASS |
| DS-F01 owner test 真实覆盖（refs/digest/evidence/fail-closed） | ✅ PASS |
| proactive writer 外置超限完整 payload | ✅ PASS |
| reactive writer 外置超限完整 payload | ✅ PASS |
| 所有 CONTEXT_COMPACTED 消费者统一严格解析 | ✅ PASS |
| ref/digest/descriptor/blob corruption fail closed | ✅ PASS |
| artifact 与 terminal truth 同源 | ✅ PASS |
| 无第二真源、下游补偿、兼容 shim | ✅ PASS |
| background promotion 无 fatal/hang | ✅ PASS |
| DS-F02–F08 controller 裁决证据仍成立 | ✅ PASS |
| 无新 regression | ✅ PASS |
| 无 scope drift | ✅ PASS |
| 受影响测试 472 passed | ✅ PASS |
| compact/material/terminal/proactive/projection 431 passed | ✅ PASS |
| pyright 0 errors | ✅ PASS |

## Conclusion

**PASS** — DS-F01 fix 在 `DurableCompactArtifactProvider._load_compact_artifact_tx` 正确复用 `resolve_context_compacted_payload(transaction, row)`，与同文件其他 5 处 consumer 迁移一致。新增 owner test 真实验证了 descriptor-backed terminal 的 refs/digest/evidence 同源性和 digest 漂移 fail-closed。完整 S4.2 diff 无新 regression、scope drift、兼容/下游补偿。Controller 拒绝的 DS-F02–F08 裁决直接证据仍成立。建议进入下一步 gate。
