# WU-SEMANTIC-OWNERSHIP-01 P3-J Aggregate Fix Re-review - AgentMiMo

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01`
- Sub work unit: `P3-J - Host durable schema and weak-contract hardening backlog`
- Gate: aggregate fix re-review
- Accepted finding: `P3-J-AGG-F01`
- Fix artifact: `docs/reviews/wu-semantic-ownership-01-p3-j-aggregate-fix-codex.md`
- Controller validation: `docs/reviews/wu-semantic-ownership-01-p3-j-aggregate-fix-controller-validation.md`
- Base ref: `0bc75a5b`
- Review date: 2026-07-11

## Verification Method

沿 producer → durable row → SQLite write → SQLite read → tests 完整链路逐行走读，验证 P3-J-AGG-F01 的每个 required fix 是否完整实现且无 regression。

## Chain Verification

### 1. Producer owner

- `dayu.host.queue_policy.RunQueuePolicy` 是 queue policy 的合法集合与解析/序列化 owner。
- `parse_run_queue_policy(value: str) -> RunQueuePolicy` 解析文本为 typed enum。
- `serialize_run_queue_policy(policy: RunQueuePolicy) -> str` 序列化为稳定文本。
- 状态：owner 未变更，修复不涉及 owner 本身。

### 2. Durable row typed surface

- `state.py:287`: `RunRow.queue_policy: RunQueuePolicy` ← 修复前为 `str`。
- 状态：✓ 已修复。

### 3. Decode (SQLite read → typed row)

- `state.py:1187-1208`: `_decode_run_queue_policy(row, *, row_name) -> RunQueuePolicy`
  - 从 HostRow 读取原始文本，调用 `parse_run_queue_policy(raw_policy)` 返回 `RunQueuePolicy`。
  - 修复前为 `serialize_run_queue_policy(parse_run_queue_policy(raw_policy))` 即 parse→serialize round-trip 返回 `str`。
  - 修复后直接返回 `RunQueuePolicy`，消除冗余 round-trip。
- 状态：✓ 已修复。

### 4. Insert (typed row → SQLite write)

- `state.py:2702`: `run.queue_policy.value` 直接取 enum value 写入 SQLite。
  - 修复前为 `serialize_run_queue_policy(parse_run_queue_policy(run.queue_policy))` 即对已 typed 的值做 parse→serialize round-trip。
  - 修复后在 SQLite 写入边界精确序列化一次。
- 状态：✓ 已修复。

### 5. Validation (insert 前校验)

- `state.py:5263-5264`: `if not isinstance(run.queue_policy, RunQueuePolicy): raise HostDurableError(...)`
  - 修复前为 `parse_run_queue_policy(run.queue_policy)` + ValueError catch，语义上是对已 typed 的值重复 parse。
  - 修复后用 isinstance 做类型守卫，语义清晰。
- 状态：✓ 已修复。

### 6. Upstream creation inputs (direct upstream boundary)

- `run_transition.py:150`: `CreateQueuedRunInput.queue_policy: RunQueuePolicy`
- `run_transition.py:186`: `CreateAcceptedRunInput.queue_policy: RunQueuePolicy`
- `run_transition.py:233`: `CreateRunningRunInput.queue_policy: RunQueuePolicy`
- 修复前均为 `str`。修复后与 `RunRow.queue_policy` 保持 typed 一致。
- 状态：✓ 已修复。

### 7. Common creation validation

- `run_transition.py:5969-5970`: `if not isinstance(queue_policy, RunQueuePolicy): raise HostDurableError(...)`
  - 修复前为 `parse_run_queue_policy(queue_policy)` + ValueError catch。
  - 修复后用 isinstance 类型守卫。
- 状态：✓ 已修复。

### 8. EventLog payload serialization

- `run_transition.py:3002`: `"queue_policy": serialize_run_queue_policy(request.queue_policy)`
  - 修复前为 `serialize_run_queue_policy(parse_run_queue_policy(request.queue_policy))`，即对 typed 值做冗余 parse→serialize。
  - 修复后直接 serialize typed policy 一次。EventLog payload 是文本边界，序列化在此处是正确的。
- 状态：✓ 已修复。

### 9. RunResultRow terminal_status validation helper

- `read_model.py:484-495`: 新增 `_validate_run_result_terminal_status(status: RunStatus) -> None`
  - 显式校验 `isinstance(status, RunStatus)` 和 `is_terminal_run_status(status)`。
  - 修复前由 `serialize_run_result_terminal_status()` 通过丢弃返回值完成校验，语义不清晰。
- `read_model.py:323`: `_validate_run_result()` 调用 `_validate_run_result_terminal_status(row.terminal_status)`。
- `read_model.py:480`: `serialize_run_result_terminal_status()` 调用 `_validate_run_result_terminal_status(status)` 后返回 `status.value`。
- 状态：✓ 已修复。校验职责与序列化职责分离。

### 10. Public request text boundary

- `api.py:1800`: `StartRunRequest.queue_policy: str` — 公共请求仍为文本。
- `api.py:1819`: `parse_run_queue_policy(self.queue_policy)` — 在 `__post_init__` 中通过 owner 校验。
- `admission.py:531`: `policy = parse_run_queue_policy(request.queue_policy)` — admission 层将文本解析为 typed policy 后传递给 `Create*RunInput`。
- `admission.py:4655-4656`: `serialize_run_queue_policy(parse_run_queue_policy(request.queue_policy))` — 语义 digest 计算边界，对公共请求文本做 normalize，属于合法文本边界处理。
- 状态：✓ 公共请求保持文本输入，通过 owner 解析后进入 durable 层，无 regression。

## Tests Verification

### 新增测试

- `test_state_schema.py::test_run_row_queue_policy_decodes_to_owner_type`:
  - 写入 Run → 读取 `RunRow.queue_policy` → 断言 `is RunQueuePolicy.QUEUE`。
  - 覆盖 SQLite 文本 → decode → typed surface 的完整 round-trip。
  - 状态：✓ 通过。

### Fixture 更新

- 所有直接构造 `RunRow` 或 `Create*RunInput` 的 test fixture 从 `queue_policy="queue"` 改为 `queue_policy=RunQueuePolicy.QUEUE`。
- 涉及文件：test_state_schema.py, test_run_attempt_transitions.py, test_admission_queue.py, test_public_run_api.py, test_dispatch_scheduler.py, test_recovery_scan.py, test_resolve_wait_command.py, test_run_input_builder.py, test_accepted_result_projection.py, test_compact_material.py, test_compact_pipeline.py, test_engine_ingest_mapping.py, test_phase5_local_execution_integration.py, test_phase6_toolruntime_integration.py, test_recovery_dispatch.py, test_toolruntime_accept_barrier.py, test_wait_awaiting_accept.py, test_wait_record_state.py。
- 状态：✓ 所有 fixture 已更新为 typed policy。

### 保持文本的测试

- 使用 `StartRunRequest` (公共请求) 的 test fixture 保持 `queue_policy="queue"`。
- 涉及文件：test_active_cancel_dispatch.py, test_logging.py, test_public_event_stream.py, test_command_handle.py, test_public_cancel_session_runs.py, test_storage_maintenance.py, test_storage_usage_report.py, test_phase7_waiting_integration.py, test_admission_multiprocess.py, test_projection_read_model.py, test_public_run_api.py (部分)。
- 状态：✓ 公共请求 fixture 正确保留文本。

### 测试结果

- 焦点测试 (`test_run_row_queue_policy_decodes_to_owner_type`, `test_host_runs_queue_policy_check_uses_owner_values`, `test_read_model_python_validation_rejects_unknown_terminal_status`): 3 passed。
- 广泛测试 (19 个变更测试文件): 572 passed。
- pyright: 0 errors, 0 warnings, 0 informations。
- `git diff --check`: passed。

### 基线已知失败

- `test_dispatch_scheduler.py::test_proactive_compaction_recovery_tier2_degrades_previous_view`: pre-existing failure，assertion 在 `previous_compacted_view` text 上失败，与 `queue_policy` / `RunResultRow.terminal_status` 数据路径无关。
- `test_dispatch_scheduler.py::test_reactive_compact_request_uses_latest_previous_view`: pre-existing failure，dispatch 结果为 `dispatched=0`，与本次修复数据路径无关。
- controller validation 已在 pre-fix baseline `0bc75a5b` 验证两个测试同样失败。
- 状态：✓ 确认为基线问题，非本次修复引入。

## Propagation Audit

完整数据流验证：

```text
public StartRunRequest.queue_policy: str
  → api.py __post_init__: parse_run_queue_policy(text) → RunQueuePolicy (owner 校验)
  → admission.py: parse_run_queue_policy(request.queue_policy) → policy: RunQueuePolicy
  → Create*RunInput.queue_policy: RunQueuePolicy (typed upstream boundary)
  → RunRow.queue_policy: RunQueuePolicy (typed durable row)
  → insert_run(): run.queue_policy.value (SQLite write boundary, 单次序列化)
  → SQLite TEXT column
  → _decode_run_queue_policy(): parse_run_queue_policy(raw_text) → RunQueuePolicy (typed decode)
  → RunRow.queue_policy: RunQueuePolicy (typed read surface)
```

每个边界精确一次序列化/反序列化，无冗余 round-trip，无弱 contract 泄漏。

## AgentCodex Masking Check

- test fixture 变更是机械替换 `str → RunQueuePolicy`，不涉及 assertion 削弱或行为隐藏。
- 新增测试 `test_run_row_queue_policy_decodes_to_owner_type` 断言 `is RunQueuePolicy.QUEUE`（identity check），覆盖了 decode → typed surface 的关键路径。
- `_validate_run_result_terminal_status` 的新增不改变校验逻辑，仅将 `serialize_run_result_terminal_status` 中的校验抽取为独立 helper，原 serializer 行为不变。
- 未发现 AgentCodex masking 行为。

## Findings

未发现实质性问题。

## Open Questions

- 无。

## Residual Risk

- `test_dispatch_scheduler.py` 的两个 pre-existing compaction/previous-view 验证失败未在本次修复范围内，记录为验证残余风险。
- 无阻塞性残余风险。

## Completion Report

**PASS**。P3-J-AGG-F01 的所有 required fix 沿 producer → durable row → SQLite write → SQLite read → tests 完整链路验证通过。公共请求文本边界无 regression。AgentCodex 未在测试或下游消费者中掩盖问题。pyright 0 errors。572 个变更范围测试全部通过。
