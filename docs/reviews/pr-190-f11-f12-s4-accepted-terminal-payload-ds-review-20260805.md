# Code Review — PR 190 S4.2 accepted terminal payload fix (AgentDS 独立 adversarial)

## Scope

- **Mode**: current changes (uncommitted, workspace vs baseline)
- **Branch**: `codex/interactive-oracle`
- **Base**: `f7957b6343f4647ce0c6058a08e9ae84ab629f30`
- **Output file**: `docs/reviews/pr-190-f11-f12-s4-accepted-terminal-payload-ds-review-20260805.md`
- **Review date**: 2026-08-05
- **Included scope**:
  - 新增 `dayu/host/context_event_payload.py` — durable payload owner
  - 修改 `dayu/host/dispatch.py` — proactive writer 路径
  - 修改 `dayu/host/engine_ingest.py` — reactive writer 路径
  - 修改 `dayu/host/compact_material.py` — consumer 迁移到 resolver
  - 修改 `dayu/host/compaction_terminal.py` — consumer 迁移到 resolver
  - 修改 `dayu/host/projection.py` — `projection_event_view_from_row` 签名变更
  - 修改 `dayu/host/run_input.py` — 6 处 consumer 迁移到 resolver
  - 修改 `dayu/host/durable/tool_trace.py` — Tool Trace compactor response identity
  - 修改 `dayu/host/proactive_compaction.py` — `_project_state` 迁移
  - 新增测试 `test_dispatch_scheduler.py::test_oversized_accepted_compact_terminal_uses_descriptor_truth`
  - 新增测试 `test_engine_ingest_mapping.py::test_reactive_oversized_accepted_terminal_uses_descriptor_truth`
  - 测试签名变更（`projection_event_view_from_row` 新增 `transaction` 参数）
  - `dayu/host/README.md` / `tests/README.md` 更新
- **Excluded scope**: `dayu/host/context_events.py`（零 diff）、oracle/scenario/registry（零 diff）
- **Parallel review coverage**:
  - Agent 1: writer transaction/file artifact failure semantics
  - Agent 2: resolver fail-closed semantics and consumer completeness
  - Agent 3: idempotency, event-id determinism, terminal exactly-once
  - Agent 4: residual raw `payload_json` consumer sweep
  - 主 reviewer 整合、去重、裁定 severity、复核证据链

## Findings

### F01-未修复-严重-run_input.py DurableCompactArtifactProvider 对大 payload 静默 crash

- **入口/函数**: `DurableCompactArtifactProvider._load_compact_artifact_tx`
- **文件(行号)**: `dayu/host/run_input.py:1973`
- **输入场景**: CONTEXT_COMPACTED terminal 因超限走 descriptor-backed 存储（`payload_json`=`"{}"`，`payload_ref`/`payload_digest` 非空），随后调用 `DurableCompactArtifactProvider` 读取 compact artifact view。
- **实际分支**: 第 1973 行 `payload = _payload_object(row)` 调用 `dayu.host._event_payload.payload_object()`，该函数只做 `json.loads(row.payload_json)`，不 follow `payload_ref`/`payload_digest` descriptor。`json.loads("{}")` 返回 `{}`。第 1975 行 `parse_context_compacted_semantic_payload(payload)` 因 `{}` 缺少 `accepted_candidate` 字段抛出 `ValueError`，被第 1976-1977 行包装为 `HostDurableError("compact semantic payload is invalid")`。
- **预期行为**: 应使用 `resolve_context_compacted_payload(transaction, row)` 获取完整 payload。
- **实际行为**: 永远 crash；超大 accepted compact terminal 场景下 `DurableCompactArtifactProvider` 不可用。
- **直接证据**:
  - run_input.py:70 — `from dayu.host._event_payload import payload_object as _payload_object`
  - run_input.py:1973 — `payload = _payload_object(row)`（raw inline-only parse）
  - compact_payload.py:159 — `_required_mapping({}, _FIELD_ACCEPTED_CANDIDATE)` 会因 key 缺失抛出 `ValueError`
  - 已确认此函数与其他已迁移函数（line 5491-5492 `_memory_projection_payload`、line 5593-5596 `_compaction_trigger_source_for_compacted_event`）不一致
- **影响**: `DurableCompactArtifactProvider` 是 `CompactArtifactProvider` protocol 的公开实现（`__all__` 中导出），在超大 CONTEXT_COMPACTED 事件下必然崩溃。当前 production wiring 使用 `NoopCompactArtifactProvider` 故未触发，但该 public API class 已对外暴露且被多个测试直接实例化。
- **建议改法和验证点**: 第 1973 行改为 `payload = resolve_context_compacted_payload(transaction, row)`；需 import `resolve_context_compacted_payload`；补测 oversized terminal 经 `DurableCompactArtifactProvider` 可正常读取。
- **修复风险（低）**: 与同文件其他 3 处已迁移调用一致。
- **严重程度（严重）**: 该 public API 在 oversized terminal 场景下必然崩溃，是 root cause 级遗漏。

### F02-未修复-严重-proactive 路径 event_id 非确定性导致幂等缺口

- **入口/函数**: `HostDispatchScheduler._append_compacted_event` 内的 `_operation` 闭包
- **文件(行号)**: `dayu/host/dispatch.py:3288`
- **输入场景**: proactive compaction 的 `run_write` transaction 闭包被 retry（savepoint rollback 或跨事务重试）。
- **实际分支**: 第 3288 行 `event_id = _new_event_id(_EVENT_ID_CONTEXT_COMPACTED_PREFIX)` 生成 `f"event-context-compacted-{uuid4().hex}"`。每次重试产生不同的随机 event_id。若第一次 write 部分提交（savepoint 场景）或外层 caller 重试整个 `_execute_proactive_compaction`，可能产生两个不同 event_id 的 CONTEXT_COMPACTED 行。
- **预期行为**: event_id 应从确定性 identity material 派生（如 `operation_id` + terminal kind），与 reactive 路径一致。
- **实际行为**: 每次调用产生新的随机 event_id；`begin_compaction_terminal_commit_in_transaction` 的 terminal guard 提供第一层防护，但不能防护 savepoint 级别的部分提交。
- **直接证据**:
  - dispatch.py:3288 — `event_id = _new_event_id(...)` 使用 `uuid4().hex`
  - dispatch.py:5955-5962 — `_new_event_id` 实现确认随机 UUID
  - engine_ingest.py:3090-3095 — reactive 路径使用 `_event_id(context.candidate, ...)` 产生确定性 digest-derived event_id
  - engine_ingest.py:5123-5147 — `_event_id` 实现确认 SHA256-derived
  - event_log.py:510-516 — idempotency 检查依赖 event_id 匹配 + event_body_digest 匹配；不同 event_id 导致 idempotency 完全不生效
- **影响**: 在 `run_write` 使用 savepoint 级别 retry 的极端场景下可能产生重复 CONTEXT_COMPACTED。当前 `transaction.py` 的 `run_write` 使用全事务 rollback 故实际触发概率低，但 proactive/reactive 路径的确定性不对称是结构性脆弱。
- **建议改法和验证点**: 将 proactive event_id 改为基于 `operation_id` 的确定性派生（如 `sha256_digest_json({"operation_id": pending.operation_id, "terminal_kind": "compacted"})` 加前缀）；补测 transaction retry 后只产出一个 terminal。
- **修复风险（低）**: `_new_event_id` 仅此一处使用，改动局部。
- **严重程度（严重）**: proactive/reactive 路径 event_id 确定性不对称，存在结构性幂等缺口。

### F03-未修复-高-oversized payload descriptor/blob 写入与 SQLite 事务非原子

- **入口/函数**: `store_context_compacted_payload` → `PayloadStore.write_bounded_json_payload`
- **文件(行号)**: `dayu/host/context_event_payload.py:85-99`, `dayu/host/durable/payload.py:410-426`
- **输入场景**: CONTEXT_COMPACTED payload 超过 `transaction.payload_inline_threshold_bytes`；后续 SQLite `payload_descriptors` INSERT 失败（如 UNIQUE constraint、serialization error）。
- **实际分支**: `write_bounded_json_payload` 的超限分支（payload.py:413-418）先通过 `LocalArtifactStore.write_artifact_bytes()` 写入文件系统 artifact（`os.replace` 原子 rename + fsync），再通过 `write_payload_descriptor_for_artifact`（payload.py:420-426）在该 SQLite transaction 内 INSERT descriptor row。若 descriptor INSERT 失败（第 421-426 行），`run_write` 会 rollback SQLite transaction，但 **已落盘的文件系统 artifact 不会被清理**。
- **预期行为**: 要么 artifact 写入 + descriptor INSERT 都成功，要么都回滚。文件系统 artifact 应在 descriptor 写入失败时被清理。
- **实际行为**: 文件系统 artifact 孤儿残留；无 SQLite descriptor 引用，无法被 normal path 读取，也无法被 GC 回收（代码中没有 descriptor-less artifact GC）。
- **直接证据**:
  - payload.py:413-418 — `write_artifact_bytes` 在 SQLite INSERT 之前执行
  - payload.py:420-426 — descriptor INSERT 在同一 `HostTransaction` 内
  - artifact.py:76-116 — `write_artifact_bytes` 是文件系统操作，不使用 SQLite 连接
  - transaction.py:347-352 — `run_write` 的 rollback 只撤销 SQLite，不回调文件系统
  - 该调用路径没有 register `after_commit` 或 `on_rollback` callback
- **影响**: 磁盘空间泄漏；在高 compaction 频率 + 高 SQLite contention 下累积明显。
- **建议改法和验证点**: 在 descriptor INSERT 失败时同步 unlink artifact 文件（在 `write_bounded_json_payload` 函数内 catch exception → unlink → re-raise），或使用 `run_write` 的 rollback callback 机制注册清理；补测 descriptor INSERT 失败后 artifact 文件不存在。
- **修复风险（中）**: 对 `write_bounded_json_payload` 添加文件系统清理逻辑需注意并发场景（同 digest 的 artifact 可能被其他请求共享）。
- **严重程度（高）**: 非原子写入导致确定性的磁盘泄漏路径；proactive 路径每次重试产生新 payload_ref 会加剧。

### F04-未修复-中-read_api.py activity timeline 对大 payload 静默降级

- **入口/函数**: `_context_compaction_activity`
- **文件(行号)**: `dayu/host/read_api.py:1363`
- **输入场景**: oversized CONTEXT_COMPACTED terminal（`payload_json`=`"{}"`）经过 activity timeline projection。
- **实际分支**: 第 1363 行 `_activity_payload_without_descriptor(row)` 内部调用 `_payload_object(row)`（只 parse `row.payload_json`），第 1537 行的 `except HostDurableError` 不触发（因为 `json.loads("{}")` 成功返回 `{}`）。第 1382 行 `_payload_text({}, _PAYLOAD_FIELD_FAILURE_REASON)` 从 `{}` 中读不到 `failure_reason`，返回 `None`，`_bounded_summary(None)` 返回 `None`。
- **预期行为**: activity view 应正确解析完整 payload。当前 CONTEXT_COMPACTED 的 activity 投影只取 `failure_reason`（该字段在 COMPACTED 事件中本身就不存在），所以功能上 `summary=None` 与正常行为一致。但 `payload` 被解析为 `{}` 意味着所有其他字段（`operation_id`、`accepted_attempt_number` 等）在 activity 计算中均不可用。
- **实际行为**: activity view 的 `summary` 为 `None` 是 CONTEXT_COMPACTED 的正常行为；但若未来 activity 投影增加更多字段（如显示 accepted attempt number），会静默得到空值。
- **直接证据**:
  - read_api.py:1527-1538 — `_activity_payload_without_descriptor` 只做 inline parse + 错误时 fallback `{}`
  - read_api.py:1363 — 无 descriptor-aware 分支
  - 对比 run_input.py:5491-5492 `_memory_projection_payload` 正确分支 `if row.event_type == CONTEXT_COMPACTED`
- **影响**: 当前无功能影响（CONTEXT_COMPACTED 无 `failure_reason`），但结构性缺口意味着未来修改 activity 投影时会引入 bug。
- **建议改法和验证点**: 将 `_context_compaction_activity` 的 CONTEXT_COMPACTED 分支改用 `resolve_context_compacted_payload`；或引入 `_activity_payload_with_descriptor` 替代函数。
- **修复风险（低）**: 与其他 consumer 迁移一致。
- **严重程度（中）**: 不影响当前功能正确性，但结构性缺口是确定的。

### F05-未修复-中-tool_trace.py ATTEMPT_REJECTED 分支绕过 descriptor 解析

- **入口/函数**: `_resolved_compactor_response_from_row`
- **文件(行号)**: `dayu/host/durable/tool_trace.py:664-675`
- **输入场景**: CONTEXT_COMPACTION_ATTEMPT_REJECTED 事件走 oversized descriptor-backed 存储。
- **实际分支**: ACCEPTED 分支（line 667-670）使用 `resolve_context_compacted_payload(transaction, row)` 正确解析；ATTEMPT_REJECTED 分支（line 672-675）使用 `_json_object_from_text(row.payload_json)` 只 parse inline payload_json。若 ATTEMPT_REJECTED 未来也走 descriptor-backed 存储，会读到 `{}`。
- **预期行为**: 两个分支应统一使用 descriptor-aware 解析。
- **实际行为**: 当前 ATTEMPT_REJECTED payload 均走 inline 存储（无 `store_*` 函数），所以无立即影响。但不对称性是 fragility。
- **直接证据**:
  - tool_trace.py:667-668 — ACCEPTED 正确使用 `resolve_context_compacted_payload`
  - tool_trace.py:672 — ATTEMPT_REJECTED 使用 `_json_object_from_text(row.payload_json)`（只 parse inline）
  - context_events.py:1471-1576 — `build_context_compaction_attempt_rejected_payload` 构造 inline-only payload
- **影响**: 当前无影响，未来 ATTEMPT_REJECTED 若支持 descriptor-backed 会 crash。
- **建议改法和验证点**: ATTEMPT_REJECTED 分支改用 `event_payload_object(transaction, row, payload_label=CONTEXT_COMPACTION_ATTEMPT_REJECTED)`。
- **修复风险（低）**: 与 ACCEPTED 分支模式对齐。
- **严重程度（中）**: 当前无功能影响，但代码不对称性代表确定的结构性缺口。

### F06-未修复-中-proactive_compaction.py _project_state 对非 COMPACTED 事件缺少 descriptor 解析

- **入口/函数**: `_project_state`
- **文件(行号)**: `dayu/host/proactive_compaction.py:461-468`
- **输入场景**: CONTEXT_COMPACTION_ATTEMPT_REJECTED 或 CONTEXT_COMPACTION_FAILED 走 oversized descriptor-backed 存储。
- **实际分支**: 第 464-468 行 COMPACTED 正确使用 `resolve_context_compacted_payload`；ATTEMPT_REJECTED、FAILED、RUNNER_CALL_INPUT_ASSEMBLED 走 `payload_object(row)`（无 transaction，不解析 descriptor）。
- **预期行为**: 其他 compaction event type 若走 descriptor-backed 存储应能正确解析。
- **实际行为**: 当前这些 event type 均无 descriptor-backed 存储，无立即影响。但 ATTEMPT_REJECTED 携带 `runner_attempt_summary_refs`、`diagnostic_refs` 等可能增长为超限 payload。
- **直接证据**:
  - proactive_compaction.py:467 — `else payload_object(row)`
  - `payload_object` 来自 `dayu.host._event_payload`，只做 `json.loads()`，不支持 descriptor
- **影响**: 当前无影响，未来扩展触及。
- **建议改法和验证点**: 为 ATTEMPT_REJECTED 和 FAILED 分支添加 `event_payload_object` 或等效 descriptor 解析。
- **修复风险（低）**: 需引入 `transaction` 参数（该函数已有 `transaction` 参数）。
- **严重程度（中）**: 结构性缺口，当前无功能影响。

### F07-未修复-低-dispatch.py proactive 路径 PayloadStore 行内实例化

- **入口/函数**: `HostDispatchScheduler._append_compacted_event` 内 `_operation` 闭包
- **文件(行号)**: `dayu/host/dispatch.py:3307`
- **输入场景**: proactive compaction 的 write 事务。
- **实际分支**: 第 3307 行 `PayloadStore()` 行内实例化，对照 reactive 路径（engine_ingest.py:3114）使用 `self._payload_store`。
- **预期行为**: 两条路径应使用一致的方式获取 `PayloadStore`。
- **实际行为**: `PayloadStore` 当前是无状态类（无 `__init__`、无 `__slots__`、无类级可变状态），所以行为一致。但如果 `PayloadStore` 未来添加 `__init__` 级别的状态（如 connection reference、动态阈值），proactive 路径的 `PayloadStore()` 会创建未初始化实例。
- **直接证据**:
  - dispatch.py:3307 — `PayloadStore()`
  - engine_ingest.py:3114 — `self._payload_store`
  - payload.py:155 — `class PayloadStore:` 无 `__init__`
- **影响**: 当前无功能影响；是 fragility，不是 bug。
- **建议改法和验证点**: proactive 路径应从 `HostDispatchScheduler` 取得 `PayloadStore` 实例或通过构造注入。
- **修复风险（低）**: 纯重构。
- **严重程度（低）**: 当前无功能影响，纯代码一致性。

### F08-未修复-低-build_context_compacted_payload 缺少构建时尺寸防护

- **入口/函数**: `build_context_compacted_payload`
- **文件(行号)**: `dayu/host/context_events.py:1268`, `dayu/host/context_event_payload.py:79`, `dayu/host/durable/event_log.py:1285-1307`
- **输入场景**: 使用 `build_context_compacted_payload` 构造 payload 但绕过 `store_context_compacted_payload` 直接写入 EventLog。
- **实际分支**: `build_context_compacted_payload` 不检查尺寸；`store_context_compacted_payload` 在 line 79 检查尺寸；`_validate_canonical_inline_payload_size` 在 EventLog write 边界对所有 `CANONICAL_FACT` 做最终 guard。
- **预期行为**: 三层防护的最终 guard（EventLog 写边界）存在且正确触发 `HostPayloadReferenceError`，但错误发生在 write 时而非 build 时，错误消息指向 `payload_json` 超限而非缺少 `payload_ref`/`payload_digest`。
- **实际行为**: guard 存在（event_log.py:1299-1306），但 build 时不报错，write 时才发现。如果被写入的 event class 不是 `CANONICAL_FACT`（例如未来新增其他 event class 使用 `build_context_compacted_payload`），guard 不会触发，大 payload 会直接写入 inline。
- **直接证据**:
  - context_events.py:1195-1269 — `build_context_compacted_payload` 无尺寸检查
  - event_log.py:1299 — `if request.event_class is not EventClass.CANONICAL_FACT: return`（非 canonical fact 不检查）
- **影响**: 当前无影响（所有 writter 均通过 `store_context_compacted_payload`），但设计依赖调用方遵守约定。
- **建议改法和验证点**: 可选在 `build_context_compacted_payload` 返回值上添加尺寸断言（仅开发/测试模式），或在文档中明确 `store_context_compacted_payload` 是唯一 write path。
- **修复风险（低）**: 纯文档/assert 级别。
- **严重程度（低）**: 多层防护存在，当前路径正确。

## Open Questions

- 无。

## Residual Risk

1. **orphan artifact 风险**: `PayloadStore.write_bounded_json_payload` 的 artifact 文件写入在 descriptor INSERT 之前，descriptor INSERT 失败后 artifact 文件残留。当前环境因 `run_write` 使用全事务 rollback 且 proactive/reactive retry 都会走相同 digest-addressed 路径（文件内容相同所以覆盖），所以 orphaning 概率低；但严格语义上是非原子的。建议为 `write_bounded_json_payload` 添加 descriptor INSERT 失败后的 artifact 清理。

2. **savepoint retry 语义未测试**: 所有测试使用全事务级别的 `run_write`（`BEGIN IMMEDIATE ... COMMIT`），未覆盖 savepoint 或部分回滚场景。若 `HostTransactionRunner` 在未来引入 savepoint 级别的 retry，F02（event_id 非确定性）和 F06（descriptor orphaning）会从 latent 变为 active bug。

3. **DurableCompactArtifactProvider 未更新**: 已有 4 个测试直接实例化 `DurableCompactArtifactProvider`，但均使用小 payload（inline），未覆盖 oversized terminal 场景。F01 的 crash 路径在现有测试中无法触发。建议在修复 F01 后添加 oversized terminal 经 `DurableCompactArtifactProvider` 的测试。

4. **activity timeline 未覆盖 oversized**: read_api 测试未包含 oversized CONTEXT_COMPACTED 经过 activity timeline projection 的 case。F04 当前无功能影响但缺乏回归防护。

5. **测试全部通过 (2425 passed)**: 新加入的 2 个 oversized terminal owner tests 正确验证了 proactive 和 reactive 路径。test fixture 使用真实 durable store 和 background queue promotion，不依赖 mock 或共享可变状态。但测试未覆盖 savepoint retry、descriptor INSERT 失败、以及全部 6 种 consumer（activity timeline 和 DurableCompactArtifactProvider 未覆盖）。

6. **全仓 pyright clean**: `0 errors, 0 warnings, 0 informations`。

7. **未修改 context_events.py**: 确认 baseline 后零 diff；contract 所有者未被本 change 修改。

8. **无 scope/format churn**: 确认 diff 只包含必要 import、writer/resolver 签名变更、consumer 迁移、owner tests 和 README 更新。
