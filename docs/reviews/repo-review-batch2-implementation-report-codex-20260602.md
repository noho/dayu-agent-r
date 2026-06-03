# Batch 2 implementation report - AgentCodex

## 范围

本轮处理 full-repo review fix loop batch 2 中指定的 DS high / medium 与 quick win。基于 batch 1 未提交 workspace 继续修改；未执行 commit、push 或 PR 操作。

## 处理结果

### A. DS finding 5 `_consume_worker_events` lost closeout 二次失败

- 裁决：fixed。
- 修改：
  - `HostDispatchScheduler._safe_close_worker_lost` 包装 `EngineEventIngestor.close_worker_lost`。
  - closeout 自身失败时记录 `run_id` / `attempt_id` / `execution_id` / `dispatch_record_id` / worker signal / 原始异常类型 / closeout 异常类型。
  - closeout 失败返回 `False`，不替换原始 stream / ingest 异常路径。
- 测试：
  - `test_close_worker_lost_failure_logs_context_without_raising` 覆盖 closeout 二次失败只记录诊断。

### B. DS finding 6 `_drain_loop` retry exhausted 丢弃队列残留

- 裁决：fixed。
- 修改：
  - drain loop 收到 `HostTransactionRetryExhaustedError` 后，在关闭 scheduler 前 best-effort drain 本地 dispatch queue。
  - 对每个残留 `PendingDispatchRecord` 复用 startup failure terminal closeout；单条 closeout 失败仍按 best-effort 诊断，不阻塞 scheduler fail-close。
- 测试：
  - `test_drain_loop_retry_exhausted_closes_pending_queue_records` 覆盖残留 queue record 被收口为 failed/cancelled dispatch 并清空队列。

### C. DS finding 7 runtime 同名 `_require_exact_fields` 语义不一致

- 裁决：fixed by rename。
- 证据：
  - `scene_prepare` 对 manifest / model / defaults / fragment / context slot 的缺字段已有字段级 `_require_*_field` 独立校验。
  - 问题核心是 helper 名称误导，不是缺字段未校验。
- 修改：
  - `dayu.runtime.scene_prepare._require_exact_fields` 改名为 `_require_no_unknown_fields`。
  - 保留 config_loader 的 exact fields 语义不变。
- 测试：
  - `test_manifest_model_missing_required_field_fails_fast` 覆盖缺少 `model.default_model_id` 仍 fail-fast。

### D. DS finding 8 `_AsyncAgent.run_messages()` acquire 失败 runner cleanup

- 裁决：rejected-with-controller-reason。
- 纠偏：
  - Controller 裁决原建议错误：`_AsyncAgent` 是单次 run 私有状态机，同一实例非法重入时第二个 generator 关闭 runner 会破坏第一个 active generator。
  - 已回滚本轮最初对 `dayu/engine/agent.py` 的 D 项实现改动。
- 当前行为：
  - 非法重入 fail-fast，且不关闭 active runner。
  - 没有新 runner 泄漏，因为 runner 属于同一个 private agent，不是第二次调用新建资源。
- 测试：
  - `test_private_agent_concurrent_run_fail_fast` 增加断言：重入失败后 active runner `close_count == 0`。

### E. DS finding 10 terminal closeout replay 幂等吸收

- 裁决：fixed with guard。
- 修改：
  - `terminal_closeout_in_transaction` 在 append terminal event 前识别同 Run / Attempt / 同种 terminal status replay，直接返回 `UPDATED`，不追加新 EventLog terminal event。
  - `_run_mutation_result_for_active` 仅在同 terminal status 且同 terminal event id 时吸收低层 replay；不同终态、同终态不同 ref 均不吸收。
  - 避免 succeeded 吸收 failed、failed 吸收 lost 等异种终态。
- 测试：
  - `test_terminal_closeout_replay_absorbs_same_terminal_status_without_new_events`
  - `test_terminal_run_row_absorbs_only_same_terminal_ref_replay`
  - `test_terminal_run_row_rejects_same_terminal_status_with_different_ref`

### F1. DS finding 11 SSE parser buffer bounds

- 裁决：fixed。
- 修改：
  - SSE 单行缓冲上限：1 MiB。
  - 单个 SSE event 的 `data:` 行数上限：256。
  - 超限产出 `provider_protocol_error` 并以 `runner_done(error)` 收口。
- 测试：
  - `test_sse_line_buffer_limit_emits_protocol_error`
  - `test_sse_data_line_count_limit_emits_protocol_error`

### F2. DS finding 12 empty Content-Type streaming handling

- 裁决：fixed。
- 修改：
  - `stream=True` 且 HTTP 200 `Content-Type` 缺失 / 空白时按 SSE 尝试解析，同时保留 warning 诊断。
  - `Content-Type` 含 JSON 时仍按非流式 JSON 解析。
- 测试：
  - `test_stream_true_missing_content_type_falls_back_to_sse`
  - 全量 `tests/engine/runners/openai/` 覆盖 JSON / SSE / unknown content-type 分流。

### F3. MiMo contract-001 / DS low 26 contracts 包根导出

- 裁决：fixed。
- 修改：
  - `dayu.contracts.__all__` 导出 `truncate_limit_key_for_strategy`。
- 测试：
  - `tests/contracts/test_package_exports.py::test_contracts_all_matches_expected_set`

## 文档同步

- `dayu/engine/README.md`：同步空 Content-Type SSE 分流与 SSE buffer bounds。
- `dayu/host/README.md`：同步 worker lost closeout 失败诊断与 drain retry exhausted queue closeout。
- `tests/README.md`：同步 SSE buffer bounds 测试覆盖。

## 验证命令

```bash
source .venv/bin/activate && pytest tests/engine/test_agent_phase2.py::test_private_agent_concurrent_run_fail_fast tests/host/test_dispatch_scheduler.py::test_drain_loop_retry_exhausted_closes_pending_queue_records tests/host/test_dispatch_scheduler.py::test_close_worker_lost_failure_logs_context_without_raising tests/runtime/test_scene_prepare.py::test_manifest_model_missing_required_field_fails_fast tests/engine/runners/openai/test_protocol_error.py::test_sse_line_buffer_limit_emits_protocol_error tests/engine/runners/openai/test_protocol_error.py::test_sse_data_line_count_limit_emits_protocol_error tests/engine/runners/openai/test_streaming_capability_and_content_type.py::test_stream_true_missing_content_type_falls_back_to_sse tests/host/test_run_attempt_transitions.py::test_terminal_closeout_replay_absorbs_same_terminal_status_without_new_events tests/host/test_run_attempt_transitions.py::test_terminal_run_row_absorbs_only_same_terminal_ref_replay tests/host/test_run_attempt_transitions.py::test_terminal_run_row_rejects_same_terminal_status_with_different_ref tests/contracts/test_package_exports.py::test_contracts_all_matches_expected_set
```

结果：`14 passed in 0.64s`

```bash
source .venv/bin/activate && pytest tests/host/test_dispatch_scheduler.py tests/host/test_run_attempt_transitions.py tests/runtime/test_scene_prepare.py tests/engine/runners/openai/test_protocol_error.py tests/engine/runners/openai/test_streaming_capability_and_content_type.py tests/engine/test_agent_phase2.py tests/contracts/test_package_exports.py
```

结果：`228 passed in 1.74s`

```bash
source .venv/bin/activate && pytest tests/engine/runners/openai
```

结果：`238 passed in 0.94s`

```bash
source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
```

结果：`0 errors, 0 warnings, 0 informations`

## 剩余风险

- 未运行完整全仓测试；本轮运行了受影响 Host / Runtime / Engine / Contracts 测试与 OpenAI runner 全目录测试。
- D 项按 controller 裁决拒绝原建议；当前只补测试锁住非法重入不关闭 active runner。
