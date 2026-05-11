# PR #42 Step 1 Fix Re-review 2 - 2026-05-11

## Findings

未发现实质性问题。

## Conclusion

- conclusion: pass
- 上一轮唯一 fail finding 已闭环：跨 batch 延迟配对完成后的 `tool_call` record 现在使用 accepted/result event 的 `source_event_position`，真实 `ToolTraceObserver -> ToolTraceJsonlSink -> analyze_trace_root()` 路径已覆盖 request(1)、usage(2)、accepted(3) 分批处理，并断言 analyzer 无 `source_event_position_gaps`。

## Scope

- Mode: PR #42 Step 1 第二轮 fix re-review。
- Branch or PR: `migration/host-p8-5-stabilization` / PR #42。
- Reviewed finding: ToolTrace 跨 batch 延迟配对导致 `tool_call(source_event_position=1)` 写在 `iteration_usage(source_event_position=2)` 后面，从而 analyzer 假报 `PositionGap`。
- Output file: `docs/reviews/pr-42-step1-fix-rereview2-20260511.md`。
- Explicitly excluded: Step 2 schema projection design、PR #42 全量复审、raw payload retention/#43、P8.6、P15/P16。

## Evidence

- `dayu/host/_tool_trace_projection.py:248-262`: `TOOL_CALL_REQUESTED` 仍先进入 pending；`TOOL_RESULT_ACCEPTED` 到达后补齐 group 并发射 `tool_call`，保持上一轮定位中的延迟写出模型。
- `dayu/host/_tool_trace_projection.py:329-350`: `_emit_tool_call()` 将 `source_event_position` 设为 `group.accepted.position.value`，并用同一个 position 计算 `idempotency_key` 与写入 `ToolCallRecord`。这直接消除了 `usage(2)` 后写出 `tool_call(1)` 的倒退来源。
- `dayu/host/_tool_trace_jsonl_sink.py:132-160`: `append_record_line()` 按调用顺序追加 JSONL，因此本轮复核仍沿真实写出顺序判断 analyzer 行为。
- `utils/analyze_tool_trace_host.py:704-725`: analyzer 仍按去重后的 JSONL entry 顺序检查同 run 的 `source_event_position` 严格降序；修复没有放宽 analyzer gap 规则。
- `utils/analyze_tool_trace_host.py:1081-1153`: `analyze_trace_root()` 从 `<trace_root>/sessions/**/tool_calls_*.jsonl` 读取、去重并调用 `_detect_position_gaps()`，测试覆盖的是真实分析入口。
- `tests/host/test_phase7_tool_trace_projection.py:338-391`: 新增端到端回归测试分三次调用 observer：request(position 1)、usage(position 2)、accepted(position 3)；断言 JSONL 写出顺序为 `iteration_usage`, `tool_call`，positions 为 `[2, 3]`，并断言 `analyze_trace_root(trace_root=tmp_path).source_event_position_gaps == ()`。

## Open Questions

无。

## Residual Risk

- 本轮只复核上一轮唯一 fail finding 是否闭环；未审 Step 2 schema projection design，也未重新审查 PR #42 的其它已知非目标议题。
- 未运行真实 provider smoke 或长时间/多进程 stress；本 finding 所需的核心路径已由聚焦单测覆盖。

## Validation

- `source .venv/bin/activate && pytest tests/host/test_phase7_tool_trace_projection.py tests/utils/test_analyze_tool_trace_host.py -q`
  - Result: `38 passed in 0.18s`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - Result: `0 errors, 0 warnings, 0 informations`
