# P8.5 Slice 3 Re-review

## Review Metadata

- Review gate name: re-review
- Work unit: P8.5 — P8 Stabilization / ToolRuntime Event Model
- Assigned slice: Slice 3 — Tool Trace / Observer Projection Stability
- Source review artifact: `docs/host/phase8.5-s3-code-review.md`
- Fix artifact: `docs/host/phase8.5-s3-fix-report.md`
- Accepted finding ids: `S3-CR-001`
- Artifact path: `docs/host/phase8.5-s3-rereview.md`

## Reviewer Conclusion

pass

`S3-CR-001` 已修复。新增测试覆盖了原 finding 要求的同一条端到端链路：真实
`ProjectionCoordinator + ToolTraceObserver + ToolTraceJsonlSink` 在 sink 已成功写出
JSONL 后，由一次性失败的 `ProjectionStore.advance_success` 模拟 checkpoint 推进失败；
下一轮 `run_once` replay 同一 EventLog batch，产生两条相同 `idempotency_key` 的 JSONL
记录；随后调用 `analyze_trace_root` 验证 analyzer 按幂等键去重。

## Re-reviewed Finding

### S3-CR-001-fixed-[低]-缺少 ToolTraceObserver at-least-once replay 端到端去重测试

- **入口/函数**: `ProjectionCoordinator._process_non_transactional_batch` / `ToolTraceObserver.process_non_transactional` / `ToolTraceJsonlSink` / `analyze_trace_root`
- **文件(行号)**: `tests/host/test_phase6_projection_checkpoint.py:548`
- **输入场景**: non-required `ToolTraceObserver` JSONL sink 成功写入后，checkpoint 推进失败；下一轮 drain replay 同一 EventLog batch，产生重复 JSONL 行；analyzer 读取 trace root。
- **修复证据**: `test_tool_trace_replay_after_checkpoint_failure_is_analyzer_deduped` 使用真实 `ToolTraceObserver(jsonl_sink=ToolTraceJsonlSink(root_path=tmp_path))` 与 `ProjectionCoordinator`，并用 `_CheckpointFailOnceProjectionStore` 在第一次 `advance_success` 时抛出 `RuntimeError`，失败点位于 sink I/O 成功之后。
- **验证断言**: 第一次 `run_once` 后断言 checkpoint 为 `BLOCKED_FAILED`、`last_success_position is None`、`last_error_code == "non_required_checkpoint:RuntimeError"` 且 JSONL 只有 1 行；第二次 `run_once` 后断言 checkpoint `CAUGHT_UP` 且 position 为 2、JSONL 有 2 行、两行 `idempotency_key` 相同；随后 `analyze_trace_root` 断言 `total_lines_read == 2`、`deduped_record_count == 1`、`record_counts_by_type == {"tool_call": 1}`、`duplicate_idempotency_keys` 记录该重复 key。
- **结论**: fixed。
- **Controller decision status**: pending-controller-decision

## Validation

```bash
source .venv/bin/activate && python -m pyright dayu/host/ tests/host/ tests/utils/ utils/analyze_tool_trace_host.py
# 0 errors, 0 warnings, 0 informations

source .venv/bin/activate && pytest tests/host/test_phase6_projection_checkpoint.py tests/utils/test_analyze_tool_trace_host.py -q
# 25 passed in 0.16s

source .venv/bin/activate && pytest tests/host/test_phase7_tool_trace_projection.py tests/host/test_phase7_tool_trace_jsonl_sink.py -q
# 17 passed in 0.15s
```

## Open Questions And Residual Risk

- 未发现 `S3-CR-001` 修复引入新的 blocker。
- 本次 re-review 仅核验 `S3-CR-001`，未重新审查 Slice 3 全量 diff、未裁决最终 gate pass、未 commit、未 PR。
