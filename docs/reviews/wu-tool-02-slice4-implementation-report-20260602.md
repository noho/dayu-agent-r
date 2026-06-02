# WU-TOOL-02 Slice 4 Implementation Report

## Changed Files

- `docs/reviews/wu-tool-02-slice4-implementation-report-20260602.md`

未修改 payload consumer tests、production files 或 README。指定回归测试已直接通过，未发现需要把旧 flat candidate inspection 迁移到组合结构的测试失败。

## Implemented Plan Items

- 已运行 Slice 4 指定 payload consumer regression tests，验证 committed EventLog payload consumers 在 candidate 组合结构迁移后保持可用。
- 已运行指定 Host production consumer pyright 检查，确认 `tool_runtime`、`tool_trace`、`compaction_evidence`、`compact_material`、`memory` 类型检查通过。
- 已运行旧 flat field `candidate.*` 辅助 `rg` 检查，并完成命中人工判读。
- 已检查 `dayu/host/README.md` 与 `tests/README.md` 的触发条件；本 slice 未产生稳定文档事实变化，因此不更新 README。

## Validation Commands And Results

```bash
source .venv/bin/activate && pytest tests/host/test_tool_trace_projection.py tests/host/test_tool_trace_queries.py tests/host/test_memory_projection.py tests/host/test_compaction_operation.py tests/host/test_llm_compaction.py
```

结果：`121 passed in 0.49s`。

```bash
source .venv/bin/activate && pyright dayu/host/tool_runtime.py dayu/host/tool_trace.py dayu/host/compaction_evidence.py dayu/host/compact_material.py dayu/host/memory.py
```

结果：`0 errors, 0 warnings, 0 informations`。

## Auxiliary rg Result And Interpretation

执行命令：

```bash
rg -n "candidate\.(session_id|run_id|attempt_id|execution_id|iteration_id|tool_call_id|tool_name|tool_schema_digest|tool_identity_digest|normalized_arguments_digest|outcome_digest|payload_digest|payload_ref|truncation|raw_tool_outcome|duplicate_key|duplicate_decision|duplicate_scope|duplicate_decision_message|reuse_prior_event_refs|policy_decision|tool_idempotency_key|diagnostic_refs|accept_idempotency_key|semantic_input_digest)" dayu tests
```

命中集中在：

- `dayu/host/waiting.py`：读取 `ToolAwaitingAcceptCandidate` 的 flat 字段。该 candidate 属于 wait / external job accept barrier，不是本 work unit 拆分的 `ToolFactAcceptCandidate`，approved plan 明确 awaiting 路径不在本次结构拆分 scope 内。
- `tests/host/test_wait_awaiting_accept.py`：同样读取 awaiting candidate 字段，用于等待接受路径测试，不是普通 tool fact candidate。
- `tests/host/test_toolruntime_executor.py`：命中行位于 fake awaiting accept port，读取 awaiting candidate 的 `tool_call_id` 与 `semantic_input_digest` 来构造等待三事实和 ack，仍属于 awaiting 路径。

未发现 `dayu/host/tool_trace.py`、`dayu/host/compaction_evidence.py`、`dayu/host/compact_material.py`、`dayu/host/memory.py` 或本 slice payload consumer tests 中存在旧 `ToolFactAcceptCandidate` flat field 读取。`rg` 命中不构成生产 tool fact candidate 迁移遗漏；主要证明仍以 pyright 与回归测试通过为准。

## README / Doc Sync Decision

- `dayu/host/README.md` 已存在，但当前内容描述的是 ToolRuntime accept barrier、EventLog payload、Memory 与 Context Compaction 的稳定语义，没有描述内部 `ToolFactAcceptCandidate` 字段结构；本 slice 未改变这些稳定语义，因此不更新。
- `tests/README.md` 只记录测试分层、运行方式与维护约定；本 slice 未新增测试层级、运行命令或稳定 helper 约定，因此不更新。
- 根目录 README、`dayu/README.md`、设计文档和总控文档不属于本 slice allowed scope，且没有触发更新条件。

## Production Semantics Confirmation

- 未修改 `dayu/host/tool_trace.py`，tool trace hot / cold projection schema 未改变。
- 未修改 `dayu/host/memory.py`，memory projection 对 `TOOL_RESULT_ACCEPTED` 的事实生成门槛未改变；assistant final answer / raw accepted tool evidence 仍不会自动成为 evidence-backed fact。
- 未修改 `dayu/host/compaction_evidence.py` 或 `dayu/host/compact_material.py`，accepted evidence envelope / raw outcome 的 fail-closed 行为未改变。
- 未修改 `dayu/host/tool_runtime.py`，本 slice 没有改变 EventLog payload key、accepted evidence envelope、duplicate governance、reuse、wait、retry、replay 或 resume 语义。

## Residual Risks / Uncovered Areas

- 本 slice 只覆盖 handoff 指定的 payload consumer tests 与 production consumer pyright 范围；未运行全仓 pytest 或全量 pyright，这属于后续 aggregate gate 范围。
- `rg` 是字符串辅助检查，不能证明所有语义路径；本报告以指定 pyright、payload consumer regression tests 和人工判读共同作为 Slice 4 证据。

## Stop Status

Slice 4 implementation complete。未触发 stop condition；未修改 production files、配置、schema、plan、总控文档，未 commit、push、PR 或进入 review gate。
