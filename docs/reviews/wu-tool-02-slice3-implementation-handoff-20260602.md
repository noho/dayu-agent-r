# WU-TOOL-02 Slice 3 Implementation Handoff

## Assignment

你是 implementation agent。当前 gate: implementation。当前 slice: Slice 3 `Duplicate / diagnostics candidate inspection 迁移`。

Approved plan: `docs/host/wu-tool-02-accept-candidate-cleanup-plan.md`

## Allowed Files

- `dayu/host/tool_runtime.py`
- `tests/host/test_toolruntime_duplicate_governance.py`
- `tests/host/test_toolruntime_diagnostics.py`
- completion artifact: `docs/reviews/wu-tool-02-slice3-implementation-report-20260602.md`

不得修改其它 production files、tests、README、配置、schema、plan 或总控文档。不得 commit、push、PR、进入 review gate。

## Objective

迁移 duplicate governance 与 diagnostics tests 对 `ToolFactAcceptCandidate` 的读取路径，使其使用新的组合结构；如必须触及 `dayu/host/tool_runtime.py`，只能做为保持当前 duplicate / diagnostics 语义不变所需的局部修正。

## Required Work

- 确认 `ToolAcceptDuplicateGovernance` 覆盖 reuse、hint、require justification、hard stop、durable missing 所需字段。
- 更新 `tests/host/test_toolruntime_duplicate_governance.py` 对 `duplicate_scope`、`duplicate_decision`、`reuse_prior_event_refs`、`diagnostic_refs` 的读取路径。
- 更新 `tests/host/test_toolruntime_diagnostics.py` 对 candidate / ack diagnostic refs 的读取路径。
- 保留或补充断言：
  - duplicate governed candidate scope 为 `attempt` 且 attempt id 正确。
  - reuse candidate prior refs 不丢失。
  - ack diagnostic refs 等于 candidate diagnostics refs。
  - require justification / hard stop / hint / durable missing 的 reason/message 校验仍生效。

## Non-goals

- 不改变 attempt-scoped duplicate governance key、scope、owner/waiter、durable missing 或 reuse semantics。
- 不改变 diagnostic emitter、diagnostic ref hint 格式或 tool trace payload。
- 不修改 EventLog payload、memory、compaction、awaiting、truncation、fetch_more 或 accept retry 行为。
- 不保留旧 flat field facade / compatibility branch。

## Validation

必须运行：

```bash
source .venv/bin/activate && pytest tests/host/test_toolruntime_duplicate_governance.py tests/host/test_toolruntime_diagnostics.py
source .venv/bin/activate && pyright dayu/host/tool_runtime.py tests/host/test_toolruntime_duplicate_governance.py tests/host/test_toolruntime_diagnostics.py
```

## Completion Report

写入 `docs/reviews/wu-tool-02-slice3-implementation-report-20260602.md`，包含：

- changed files
- implemented plan items
- validation commands and results
- docs decision
- residual risks / uncovered areas
- explicit confirmation that duplicate governance and diagnostics production semantics were not changed
- stop status
