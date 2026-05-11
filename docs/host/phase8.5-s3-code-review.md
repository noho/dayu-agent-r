# P8.5 Slice 3 Code Review

## Review Metadata

- Review gate name: code review
- Work unit: P8.5 — P8 Stabilization / ToolRuntime Event Model
- Assigned slice: Slice 3 — Tool Trace / Observer Projection Stability
- Approved plan: `docs/host/phase8.5-plan.md`
- Implementation artifact: `docs/host/phase8.5-s3-implementation-report.md`
- Baseline: Slice 2 commit `77f4e53`
- Reviewed diff scope:
  - `dayu/host/_event_observer.py`
  - `dayu/host/_tool_trace_projection.py`
  - `utils/analyze_tool_trace_host.py`
  - `tests/host/test_phase6_projection_checkpoint.py`
  - `tests/utils/test_analyze_tool_trace_host.py`
  - `dayu/host/README.md`
  - `tests/README.md`
  - `docs/host/phase8.5-s3-implementation-report.md`
- Artifact path: `docs/host/phase8.5-s3-code-review.md`

## Reviewer Conclusion

pass-with-risks

核心实现满足 Slice 3 的事务边界：required observer 仍走事务内 `process(tx, batch)`；非 required 且实现
`NonTransactionalObserverSink` 的 observer 先在 SQLite checkpoint transaction 外执行 sink I/O，sink 成功后才用短事务推进 checkpoint。
sink I/O 失败不会推进 checkpoint，也不会阻塞其它 required observer；sink 成功后 checkpoint 推进失败会记录 failure，保持
`last_success_position` 不变，允许后续 replay。未发现 P15 hard-gate、watchdog、observer claim lease 或 durable outbox 范围漂移。

保留的风险是测试覆盖没有把计划中的 at-least-once trace replay 场景端到端串起来：当前测试分别证明了 non-required checkpoint failure 会重放 batch、
`ToolTraceObserver` 重复处理同一 envelope 会产生相同 `idempotency_key`、analyzer 会按 `idempotency_key` 去重，但没有同一个测试通过
`ProjectionCoordinator + ToolTraceObserver + checkpoint failure` 真实产生重复 JSONL/blob record 后再运行 analyzer 验证去重。

## Validation

```bash
source .venv/bin/activate && python -m pyright dayu/host/ tests/host/
# 0 errors, 0 warnings, 0 informations

source .venv/bin/activate && pytest tests/host/test_phase7_tool_trace_projection.py tests/host/test_phase7_tool_trace_jsonl_sink.py -q
# 17 passed in 0.16s

source .venv/bin/activate && pytest tests/host/test_phase6_projection_checkpoint.py tests/host/test_phase8_multiprocess_stress.py -q
# 12 passed in 1.72s

source .venv/bin/activate && pytest tests/utils/test_analyze_tool_trace_host.py -q
# 16 passed in 0.05s
```

## Findings

### S3-CR-001-未修复-[低]-缺少 ToolTraceObserver at-least-once replay 端到端去重测试

- **入口/函数**: `ProjectionCoordinator._process_non_transactional_batch` / `ToolTraceObserver.process_non_transactional` / `analyze_trace_root`
- **文件(行号)**: `tests/host/test_phase6_projection_checkpoint.py:416`、`tests/host/test_phase7_tool_trace_projection.py:489`、`tests/utils/test_analyze_tool_trace_host.py:180`
- **输入场景**: non-required `ToolTraceObserver` JSONL/blob sink 已成功写入，随后 checkpoint 推进失败；下一轮 drain replay 同一 EventLog batch，产生重复 JSONL/blob record，随后 analyzer 读取 trace root。
- **实际分支**: 当前测试把该链路拆开验证：`test_non_required_checkpoint_failure_replays_after_sink_success` 使用测试 observer 证明 batch 重放；`test_idempotency_key_stable_across_redrain` 直接调用 `ToolTraceObserver.process` 证明重复处理同一 envelope 的 key 稳定；`test_analyzer_dedupes_orphan_lines_by_idempotency_key` 使用手写 JSONL 证明 analyzer 去重。
- **预期行为**: Approved plan 的 Slice 3 validation 明确要求 I/O success + checkpoint failure 后 replay 产生相同 `idempotency_key` 的重复 row，并由 analyzer / reader 去重后只保留一条逻辑记录。
- **实际行为**: 没有一条测试通过真实 `ProjectionCoordinator + ToolTraceObserver + checkpoint failure` 路径写出重复 JSONL/blob row，再调用 analyzer 验证 `deduped_record_count` 与 `duplicate_idempotency_keys`。
- **直接证据**: `docs/host/phase8.5-plan.md:587-593` 将该场景列为 expected assertion；当前相关覆盖分别位于 `tests/host/test_phase6_projection_checkpoint.py:416-446`、`tests/host/test_phase7_tool_trace_projection.py:489-508`、`tests/utils/test_analyze_tool_trace_host.py:180-194`，没有共同覆盖真实 trace observer replay 到 analyzer 的完整路径。
- **影响**: 主要是回归保护不足。当前实现从代码路径看符合语义，但未来若 `ToolTraceObserver` 的 idempotency source、coordinator 非事务选择逻辑或 analyzer 去重规则之一漂移，局部测试可能仍然通过。
- **建议改法和验证点**: 增加一个聚合测试：用真实 `ToolTraceObserver` 和 `ToolTraceJsonlSink` 装配 `ProjectionCoordinator`，用一次性失败的 `ProjectionStore.advance_success` 模拟 checkpoint failure；第一次 `run_once` 后断言 checkpoint 为 non-required checkpoint failure 且 JSONL 有一行，第二次 `run_once` 后断言 JSONL 有两行且 `idempotency_key` 相同，再调用 `analyze_trace_root` 断言读取两行、去重后一条、duplicate key 被记录。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低
- **Controller decision status**: pending-controller-decision

## Non-Finding Notes

- `dayu/host/_event_observer.py:295-308` 对非 required `NonTransactionalObserverSink` 与 required / transactional `ObserverSink` 分支做了明确分离，required observer 仍保留原事务语义。
- `dayu/host/_event_observer.py:391-430` 先执行 `process_non_transactional`，再推进 checkpoint；I/O 失败与 checkpoint 失败都会走 `record_failure`，不前进 `last_success_position`。
- `dayu/host/_tool_trace_projection.py:154-172` 通过 `asyncio.to_thread` 把同步 JSONL/blob 写入放到 checkpoint transaction 外。
- `utils/analyze_tool_trace_host.py:433-648` 的 truncation / `fetch_more` 诊断只基于 ordinary tool_call record 与 `arguments_json`，不再依赖 legacy `fetch_more_consumed_cursor` / `fetch_more_next_cursor`。
- `utils/analyze_tool_trace_host.py:1007-1058` 继续按 `idempotency_key` 去重，适配 non-required trace at-least-once replay。

## Open Questions And Residual Risk

- Persistent status 仍复用 `BLOCKED_FAILED` / `RETRYABLE_FAILED`，通过 `non_required_io:*` 和 `non_required_checkpoint:*` 区分非 required failure 类型。该语义对当前 Slice 3 足够，但如果后续需要运维 UI 或 hard-gate，需要另行设计更细的状态模型；P15 明确不在本 slice。
- checkpoint failure 之后若连 failure row 都无法写入，异常仍会从 coordinator 冒出。这是既有 storage failure 边界；durable outbox / watchdog 明确不在本 slice。

## Scope Check

- 未发现修改超出指定 diff scope。
- 未发现 P15 hard-gate / watchdog / observer claim lease / durable outbox / required projection enforcement 的实现漂移。
- 未修改生产代码、测试代码或 README；本次仅新增本 review artifact。
