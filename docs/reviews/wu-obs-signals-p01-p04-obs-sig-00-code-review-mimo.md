# Code Review

## Scope

- Mode: current changes
- Branch: `phaseflow/wu-obs-signals-p01-p04`
- Base: `main`
- Output file: `docs/reviews/wu-obs-signals-p01-p04-obs-sig-00-code-review-mimo.md`
- Included scope:
  - `dayu/host/tool_trace.py` — signal carrier wiring
  - `tests/host/test_tool_trace_projection.py` — signal projection tests
  - `docs/reviews/wu-obs-signals-p01-p04-obs-sig-00-implementation-codex.md` — implementation artifact
  - `docs/host/issues-implementation-control.md` — status bookkeeping only
- Excluded scope: none
- Parallel review coverage: 无

## Findings

未发现实质性问题。

## Open Questions

无。

## Residual Risk

- **Runner-call trace 路径不含 signal 字段**：`_extract_runner_call_trace` / `_runner_call_trace_summary` 不走 `_trace_summary`，因此 `RUNNER_CALL_INPUT_ASSEMBLED` 事件的 `trace_summary` 不会有四类 signal key。这是当前切片的设计意图（计划明确 runner-call 专用 summary 路径不是 P01-P04 的批准 signal source），但 analyzer 消费端必须知道：runner-call 行的 signal 缺失不代表"无 signal"，而是"该路径尚未接入"。此风险已由计划记录为 `OBS-SIG-00` non-goal，后续切片或 work unit 决定是否扩展。
- **实际 signal payload 仍为空**：当前没有任何 producer（Engine ingest、ToolRuntime、context events）往 payload 写入这四类 signal object，因此生产环境中 `trace_summary` 不会出现 signal key。此风险由后续 `OBS-SIG-01/P01` 到 `OBS-SIG-04/P04` 切片覆盖。
- **`_trace_summary` 参数数量**：函数已有 16 个参数（含 `signals`），虽然 signals 使用 grouped carrier 避免了进一步膨胀，但函数参数总量已偏高。当前切片不改此结构，后续可考虑将 `_trace_summary` 的非 signal 参数也收束为 grouped carrier。

## Validation

- pytest: `pytest tests/host/test_tool_trace_projection.py tests/host/test_tool_trace_queries.py` — 21 passed in 0.43s
- pyright: 0 errors, 0 warnings, 0 informations
- 验证已在本机实际运行

## Completion Report

- Artifact path: `docs/reviews/wu-obs-signals-p01-p04-obs-sig-00-code-review-mimo.md`
- Verdict: **pass**
- Finding count: 0
- Blocking open questions: 无
- Validation: 已运行（pytest 21 passed, pyright 0 errors）
