# Re-Review: Full-Repo Review Fix Loop (Batch 1 + Batch 2)

## Scope

- Mode: Re-review after batch1+batch2 fixes
- Branch: `refactor/host-layer-followup-wu-layer-01-02`
- Original artifact: `docs/reviews/repo-review-20260602-210230.md`
- Batch 1 report: `docs/reviews/repo-review-batch1-implementation-report-codex-20260602.md`
- Batch 2 report: `docs/reviews/repo-review-batch2-implementation-report-codex-20260602.md`
- Output file: `docs/reviews/repo-review-rereview-mimo-20260602.md`
- Review date: 2026-06-02
- Controller verification: `pytest -q` 2024 passed / 1 skipped / 5 deselected; `pyright` 0 errors; `git diff --check` passed

## Verification Method

逐条对照原始 review 的 26 个 findings，检查当前 workspace 代码是否已修复、有 controller 裁决、或仍为 pre-existing。对 batch1/batch2 新增/修改的代码走读关键路径，检查是否引入新 defect。

## Original High Findings Disposition

### 1-高-host-core-002: llm_compaction 直接调用 Engine run_agent_and_wait

- **Status**: ACCEPTED (Controller Ruling)
- **证据**: Controller 裁决 Host -> Engine 是允许方向（`UI -> Service -> Host -> Engine`），不是反向依赖。当前 Host 使用 Engine 公共契约和公共入口，未依赖 Engine 内部实现。
- **当前代码**: `dayu/host/llm_compaction.py` L26 仍 `from dayu.engine import run_agent_and_wait`，符合 controller 裁决。
- **结论**: 不需要修复。架构方向正确。

### 2-高-api-test-016: HostEventKind 缺少 LOST

- **Status**: FIXED (Batch 1)
- **验证**:
  - `dayu/host/api.py` L288: `LOST = "lost"` 已添加到 `HostEventKind`
  - `dayu/host/api.py` L305: `LOST = "lost"` 已添加到 `HostTerminalStatus`
  - `dayu/host/api.py` L2505: `LOST = "lost"` 已添加到 `HostTerminalStatus` (enum)
  - `dayu/host/read_api.py`: `_host_event_from_row` 对 `RUN_LOST` 生成 lost terminal host event
  - `tests/host/test_public_host_event.py` L103-138: 覆盖 LOST event 创建和 final answer payload 拒绝
  - `tests/host/test_public_contracts.py` L370, L380: enum stability 测试覆盖 LOST
- **结论**: 已修复，测试覆盖充分。

### 3-高-api-test-011: _execution_config_projection 使用 RuntimeError

- **Status**: FIXED (Batch 1)
- **验证**:
  - `dayu/host/_execution_config_projection.py` L32: `from dayu.host.durable.errors import HostDurableError`
  - L99: docstring 标注 `:raises HostDurableError:`
  - L120-123: `except HostDurableError: raise HostDurableError(...)` 统一包装
  - L305: `raise HostDurableError(f"unknown provider_request kind: {kind}")`
  - 所有 JSON shape 错误路径均使用 `HostDurableError`，无残留 `RuntimeError`
  - `tests/host/test_effective_execution_config.py`: 覆盖 corrupted JSON 和 unknown provider request kind
- **结论**: 已修复，异常类型统一。

## Original Medium Findings Disposition

### 4-中-durable-001: transaction._rollback 吞错

- **Status**: NOT FIXED (pre-existing, deferred)
- **证据**: `dayu/host/durable/transaction.py` `_rollback` 仍为 `except sqlite3.Error: pass`
- **评估**: pre-existing 代码模式，rollback 失败是极端 edge case（disk full），不在 batch1/batch2 scope 内。可 deferred。

### 5-中-durable-006: purge 无限循环保护

- **Status**: NOT FIXED (pre-existing, deferred)
- **证据**: `dayu/host/durable/purge.py` `_delete_runs_child_before_parent` 仍无 max iteration guard
- **评估**: schema CHECK 约束 + purge 前置条件保护，实际风险极低。可 deferred。

### 6-中-durable-010: connect() 无事务保护

- **Status**: NOT FIXED (pre-existing, accepted)
- **评估**: 仅用于 maintenance/test，文档已说明职责边界。可 accepted。

### 7-中-durable-015: read_model 全表 DELETE

- **Status**: NOT FIXED (pre-existing, accepted)
- **评估**: 仅被 projection repair 路径调用，同一事务内配合 checkpoint 重置。语义正确。可 accepted。

### 8-中-durable-002: run_read 复用 write 重试策略

- **Status**: NOT FIXED (pre-existing, deferred)
- **评估**: 功能正确，语义耦合。可 deferred。

### 9-中-contract-001: contracts 包根导出遗漏

- **Status**: FIXED (Batch 2)
- **验证**: `dayu/contracts/__init__.py` L82 已包含 `truncate_limit_key_for_strategy`，L126 已加入 `__all__`
- **结论**: 已修复。

### 10-中-runtime-001: tool_runtime_schema_projection 缺少 __all__

- **Status**: NOT FIXED (pre-existing, deferred)
- **评估**: host 内部模块，低风险。可 deferred。

### 11-中-api-test-001: HostClosedError 覆盖不完整

- **Status**: NOT FIXED (pre-existing, deferred)
- **评估**: 测试覆盖缺口，非 correctness 问题。可 deferred。

### 12-中-api-test-002: watch error propagation 未测试

- **Status**: NOT FIXED (pre-existing, deferred)
- **评估**: 测试覆盖缺口。可 deferred。

### 13-中-api-test-003: read_api session watch 缺少隔离测试

- **Status**: NOT FIXED (pre-existing, deferred)
- **评估**: 测试覆盖缺口。可 deferred。

### 14-中-api-test-006: outbox catch-up failure 未测试

- **Status**: NOT FIXED (pre-existing, deferred)
- **评估**: 测试覆盖缺口。可 deferred。

### 15-中-api-test-009: watch/close 竞态未测试

- **Status**: NOT FIXED (pre-existing, deferred)
- **评估**: 测试覆盖缺口。可 deferred。

### 16-中-api-test-013: audit JSONL O(n) 扫描

- **Status**: NOT FIXED (pre-existing, deferred)
- **评估**: 性能问题，非 correctness。purge 操作低频。可 deferred。

### 17-中-host-core-003: ActiveWorkerRegistry threading.RLock

- **Status**: NOT FIXED (pre-existing, deferred)
- **评估**: 当前 `on_cancel` 为非阻塞 hook，实际风险低。可 deferred。

## Batch 1 + Batch 2 New Code Review

### Terminal Closeout Replay Idempotency (Batch 2, Item E)

- **文件**: `dayu/host/durable/run_transition.py` L4697-4728
- **逻辑**: `_terminal_closeout_replay_result` 检查 4 个条件：`current_attempt_id` 匹配、`run_id` 匹配、`run.status` 匹配、`attempt.status` 匹配。全部满足时返回 `UPDATED`（幂等吸收），否则返回 `None`（允许新 event 写入）。
- **验证**: 异种终态（如 succeeded → failed）不满足 `run.status is request.run_terminal_status`，返回 None，正确允许新 event。同终态不同 ref 不满足 `current_attempt_id` 匹配，同样返回 None。
- **测试**: `test_terminal_closeout_replay_absorbs_same_terminal_status_without_new_events`、`test_terminal_run_row_absorbs_only_same_terminal_ref_replay`、`test_terminal_run_row_rejects_same_terminal_status_with_different_ref`
- **结论**: 逻辑正确，防护充分。

### Terminal Run Row CAS Defense (Batch 1, Item D)

- **文件**: `dayu/host/durable/state.py` L3593-3606
- **逻辑**: `terminal_run_row` 的 UPDATE WHERE 包含 `_TERMINAL_REFS_UNSET_WHERE_SQL`，与同文件其它 terminal mutation 一致。
- **验证**: 如果 terminal refs 已存在（如 terminal_event_id 已设置），WHERE 不匹配，UPDATE 影响 0 行，返回 CAS lost。
- **测试**: `test_terminal_run_row_reports_cas_lost_when_terminal_refs_already_set`
- **结论**: CAS 防御正确。

### SSE Buffer Bounds (Batch 2, Item F1)

- **文件**: `dayu/engine/runners/openai/sse_parser.py` L81-82, L194, L207, L229, L329
- **逻辑**: 单行缓冲上限 1 MiB（`_MAX_SSE_LINE_CHARS`），单 event data 行数上限 256（`_MAX_SSE_DATA_LINES`）。超限产出 `provider_protocol_error` + `runner_done(ERROR)`。
- **验证**: 检查点覆盖累积阶段（L194）、行提取后（L207, L229）和 data 行追加前（L329）。三处均 yield `_handle_buffer_limit_exceeded`。
- **测试**: `test_sse_line_buffer_limit_emits_protocol_error`、`test_sse_data_line_count_limit_emits_protocol_error`
- **结论**: 防御正确，覆盖恶意/异常 provider 场景。

### Stream=True Missing Content-Type (Batch 2, Item F2)

- **文件**: `dayu/engine/runners/openai/runner.py` L126-141, L588-590
- **逻辑**: `_is_sse_response` 在 `stream=True` 且 `content_type=""` 时返回 `True`（按 SSE 尝试）。L588-590 记录 warning 诊断。
- **验证**: 逻辑链：`stream=False` → not SSE；`stream=True` + empty → SSE；`stream=True` + `text/event-stream` → SSE；`stream=True` + `application/json` → not SSE；`stream=True` + unknown → SSE。
- **测试**: `test_stream_true_missing_content_type_falls_back_to_sse`
- **结论**: 行为正确，符合 SSE 规范降级策略。

### CJK Token Estimator (Batch 1, Item E)

- **文件**: `dayu/host/context_budget.py` L37, L44, L471-488, L543-554
- **逻辑**: `estimate_budget_text_tokens` 对 East Asian Width 为 W/F 的字符按 1 char/token 估算，其它字符按 chars/3。`llm_compaction.py` 复用同一 helper。
- **验证**: `is_cjk_char` 使用 `unicodedata.east_asian_width` 判断，`_CJK_EAST_ASIAN_WIDTH_VALUES = frozenset(("W", "F"))`。
- **测试**: `test_text_token_estimator_keeps_english_chars_per_token_semantics`、`test_text_token_estimator_counts_cjk_more_conservatively`
- **结论**: 保守化正确，避免 CJK 文本低估 token。

### Dispatch Drain Loop Retry Exhausted (Batch 2, Item B)

- **文件**: `dayu/host/dispatch.py` L2154-2171
- **逻辑**: `_drain_loop` catch `HostTransactionRetryExhaustedError` 后，先 `_best_effort_closeout_pending_queue_for_shutdown` drain 残留 queue，再 `_closed = True` + `cancel_all` + `mark_host_instance_stopped`。
- **测试**: `test_drain_loop_retry_exhausted_closes_pending_queue_records`
- **结论**: 队列残留被正确收口为 failed/cancelled dispatch。

### Worker Lost Closeout Failure (Batch 2, Item A)

- **文件**: `dayu/host/dispatch.py` L3063-3094, L249
- **逻辑**: `_safe_close_worker_lost` 包装 `close_worker_lost`，失败时记录 run_id/attempt_id/execution_id/dispatch_record_id/worker signal/异常类型，返回 `False`，不替换原始异常路径。
- **测试**: `test_close_worker_lost_failure_logs_context_without_raising`
- **结论**: 诊断信息充分，best-effort cleanup 不干扰主路径。

### Duplicate Cleanup Best-Effort (Batch 1, Item C)

- **文件**: `dayu/host/tool_runtime.py` L2363-2403
- **逻辑**: `_record_duplicate_durable_missing_best_effort` 包装 cleanup，失败时记录 warning 并通过 `_emit_duplicate_cleanup_diagnostic_best_effort` 发出诊断。diagnostic emitter 自身失败也不替换原始控制流。
- **测试**: `test_duplicate_cleanup_failure_does_not_replace_tool_timeout_return`、`test_duplicate_cleanup_failure_does_not_replace_original_exception`
- **结论**: best-effort cleanup 正确，不干扰工具执行主路径。

### Compaction Untrusted Delimiter (Batch 1, Item F1)

- **文件**: `dayu/host/llm_compaction.py` L82-83, L392-394
- **逻辑**: `_UNTRUSTED_COMPACTION_MATERIAL_BEGIN/END` 包裹 material JSON，标记非信任边界。
- **测试**: `test_prompt_renders_material_pack_without_ledger_dump`
- **结论**: 小修复，降低 prompt injection 风险。

### scene_prepare Helper Rename (Batch 2, Item C)

- **文件**: `dayu/runtime/scene_prepare.py` L1228
- **逻辑**: `_require_exact_fields` → `_require_no_unknown_fields`，语义更精确。config_loader 的 exact fields 语义不变。
- **测试**: `test_manifest_model_missing_required_field_fails_fast`
- **结论**: 命名修正，字段级校验保留。

## New Defect Check

对 batch1/batch2 新增代码走读关键路径后，**未发现新 correctness、分层、类型或测试问题**。具体验证：

- terminal closeout replay 逻辑：4 条件 AND 门控，异种终态/不同 ref 正确穿透
- SSE buffer bounds：三处检查点覆盖完整生命周期
- CJK estimator：`unicodedata.east_asian_width` 标准库函数，W/F 判断正确
- drain loop retry exhausted：queue drain 在 `_closed = True` 前执行，顺序正确
- `_execution_config_projection.py`：全部错误路径统一 `HostDurableError`，无残留 `RuntimeError`
- `HostEventKind.LOST`：枚举值、映射、测试、enum stability 均覆盖

## Conclusion

**PASS with residual notes.**

所有 3 个原始 high finding 已解决（1 个 controller 裁决 accepted，2 个代码修复）。batch1/batch2 新增代码逻辑正确，未引入新 defect。剩余 13 个 medium finding 和 10 个 low finding 均为 pre-existing 代码质量或测试覆盖问题，不在本轮修复 scope 内，可 deferred。

### Residual Notes (可 deferred，不阻塞 ship)

| ID | 严重程度 | 描述 | 理由 |
|---|---|---|---|
| 4 | 中 | transaction._rollback 吞错 | pre-existing，rollback 失败极端 edge case |
| 5 | 中 | purge 无限循环保护 | pre-existing，schema CHECK + 前置条件保护 |
| 8 | 中 | run_read 复用 write 重试策略 | pre-existing，功能正确，语义耦合 |
| 10 | 中 | tool_runtime_schema_projection 缺 __all__ | pre-existing，host 内部模块 |
| 11 | 中 | HostClosedError 覆盖不完整 | pre-existing 测试缺口 |
| 12 | 中 | watch error propagation 未测试 | pre-existing 测试缺口 |
| 13 | 中 | read_api session watch 缺隔离测试 | pre-existing 测试缺口 |
| 14 | 中 | outbox catch-up failure 未测试 | pre-existing 测试缺口 |
| 15 | 中 | watch/close 竞态未测试 | pre-existing 测试缺口 |
| 16 | 中 | audit JSONL O(n) 扫描 | pre-existing 性能问题 |
| 17 | 中 | ActiveWorkerRegistry threading.RLock | pre-existing，当前风险低 |
| 18-26 | 低 | 代码质量/测试覆盖/死代码 | pre-existing，不阻塞 |
