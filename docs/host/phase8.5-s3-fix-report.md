# P8.5 Slice 3 Fix Report

## Fix Metadata

- Work gate name: fix
- Work unit: P8.5 — P8 Stabilization / ToolRuntime Event Model
- Assigned slice: Slice 3 — Tool Trace / Observer Projection Stability
- Source review artifact: `docs/host/phase8.5-s3-code-review.md`
- Implementation artifact: `docs/host/phase8.5-s3-implementation-report.md`
- Accepted finding ids: `S3-CR-001`
- Artifact path: `docs/host/phase8.5-s3-fix-report.md`

## Motivation Check

`S3-CR-001` 成立。它不是已证实的生产行为 bug，而是 approved plan expected assertions
对应的端到端回归覆盖缺口：原测试分别覆盖了 checkpoint failure replay、`ToolTraceObserver`
幂等键稳定性、analyzer 去重，但没有在同一条真实
`ProjectionCoordinator + ToolTraceObserver + ToolTraceJsonlSink` 路径里证明 checkpoint
失败后 replay 会产生重复 JSONL 行，并由 analyzer 按 `idempotency_key` 去重。

## Fix Status

- `S3-CR-001`: fixed

## Changed Files

- `tests/host/test_phase6_projection_checkpoint.py`
  - 增加真实 `ToolTraceObserver` + `ToolTraceJsonlSink` + `ProjectionCoordinator` 聚合测试。
  - 复用 `_CheckpointFailOnceProjectionStore`，在 sink 成功后模拟一次 checkpoint 推进失败。
  - 断言第一次 `run_once` 写出 1 条 JSONL 且 checkpoint 未推进；第二次 `run_once`
    replay 同一 batch 写出 2 条 JSONL，二者 `idempotency_key` 相同。
  - 调用 `analyze_trace_root` 断言 `total_lines_read == 2`、
    `deduped_record_count == 1`、`duplicate_idempotency_keys` 记录重复 key。
- `docs/host/phase8.5-s3-fix-report.md`
  - 记录本 fix gate 的 finding 状态、验证结果与剩余风险。

## Validation

```bash
source .venv/bin/activate && python -m pyright dayu/host/ tests/host/ tests/utils/ utils/analyze_tool_trace_host.py
# 0 errors, 0 warnings, 0 informations

source .venv/bin/activate && pytest tests/host/test_phase6_projection_checkpoint.py tests/utils/test_analyze_tool_trace_host.py -q
# 25 passed in 0.17s

source .venv/bin/activate && pytest tests/host/test_phase7_tool_trace_projection.py tests/host/test_phase7_tool_trace_jsonl_sink.py -q
# 17 passed in 0.15s
```

## Documentation Decision

不更新 README。此次只补齐既有行为的测试覆盖与 fix artifact，不改变用户命令、包边界、
测试运行方式、Host 接口或文档职责范围内的说明。

## New Risks Or Open Questions

- 未引入生产代码变更，因此没有新的运行时行为风险。
- 新测试依赖真实 JSONL 文件写入到 pytest `tmp_path`，属于已有 trace sink 测试模式。

## Residual Risks And Uncovered Areas

- durable outbox、watchdog、hard-gate、observer claim lease 明确不在本 accepted finding 范围内；
  未处理，也未新增相关风险。
- checkpoint failure 后如果 failure record 自身写入失败，仍属于既有 storage failure 边界；
  本 finding 未要求覆盖。
