# WU-TOOL-02 Slice 4 Implementation Handoff

## Assignment

你是 implementation agent。当前 gate: implementation。当前 slice: Slice 4 `EventLog payload consumers regression 与 README/doc sync`。

Approved plan: `docs/host/wu-tool-02-accept-candidate-cleanup-plan.md`

## Allowed Files

- `tests/host/test_tool_trace_projection.py`
- `tests/host/test_tool_trace_queries.py`
- `tests/host/test_memory_projection.py`
- `tests/host/test_compaction_operation.py`
- `tests/host/test_llm_compaction.py`
- `tests/README.md`，仅当测试约定稳定说明需要同步。
- `dayu/host/README.md`，仅当实际存在且 Host 开发手册需要同步内部 accept candidate 边界说明。
- completion artifact: `docs/reviews/wu-tool-02-slice4-implementation-report-20260602.md`

Read-only unless direct evidence proves necessary:

- `dayu/host/tool_trace.py`
- `dayu/host/compaction_evidence.py`
- `dayu/host/compact_material.py`
- `dayu/host/memory.py`

不得修改其它 production files、tests、配置、schema、plan 或总控文档。不得 commit、push、PR、进入 review gate。

## Objective

运行并修正 payload consumer regression tests，证明 committed EventLog payload、tool trace projection、memory projection、compaction evidence material 在 candidate 组合结构迁移后保持不变。

## Required Work

- 运行 slice 指定 payload consumer tests。
- 若失败仅因测试 helper 或旧 flat candidate inspection 路径，迁移 tests 到组合结构。
- 不改变 tool trace hot/cold projection schema。
- 不改变 memory projection 对 `TOOL_RESULT_ACCEPTED` 的事实生成门槛。
- 不改变 compaction material 对 accepted evidence envelope / raw outcome 的 fail-closed 行为。
- 执行旧 flat field 辅助 `rg` 检查并人工判读；pyright 是主要证明。
- README 仅在职责范围内同步稳定说明；如无需更新，report 中说明原因。

## Validation

必须运行：

```bash
source .venv/bin/activate && pytest tests/host/test_tool_trace_projection.py tests/host/test_tool_trace_queries.py tests/host/test_memory_projection.py tests/host/test_compaction_operation.py tests/host/test_llm_compaction.py
source .venv/bin/activate && pyright dayu/host/tool_runtime.py dayu/host/tool_trace.py dayu/host/compaction_evidence.py dayu/host/compact_material.py dayu/host/memory.py
```

还要运行辅助检查并在 report 中记录人工判读结果：

```bash
rg -n "candidate\\.(session_id|run_id|attempt_id|execution_id|iteration_id|tool_call_id|tool_name|tool_schema_digest|tool_identity_digest|normalized_arguments_digest|outcome_digest|payload_digest|payload_ref|truncation|raw_tool_outcome|duplicate_key|duplicate_decision|duplicate_scope|duplicate_decision_message|reuse_prior_event_refs|policy_decision|tool_idempotency_key|diagnostic_refs|accept_idempotency_key|semantic_input_digest)" dayu tests
```

## Completion Report

写入 `docs/reviews/wu-tool-02-slice4-implementation-report-20260602.md`，包含：

- changed files
- implemented plan items
- validation commands and results
- auxiliary rg result and interpretation
- README/doc sync decision
- residual risks / uncovered areas
- explicit confirmation that tool trace / memory / compaction production semantics were not changed
- stop status
