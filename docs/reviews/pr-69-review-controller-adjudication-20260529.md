# PR 69 Review Controller Adjudication

## Gate

PR 69 draft PR review gate adjudication。

## Inputs

- AgentMiMo PR review: `docs/reviews/pr-69-review-mimo-20260529.md`
- AgentDS PR review: `docs/reviews/pr-69-review-ds-20260529.md`
- PR: `https://github.com/noho/dayu-agent-r/pull/69`
- Design truth: `docs/host/design.md`
- Accepted plan: `docs/host/phase13-audit-tool-trace-outbox-plan.md`

## Verdict

**NEEDS FIX**。PR 69 进入 draft PR fix gate。

## Accepted Blocking Findings

### PR-F1: Tool Trace cold JSONL 复制完整 raw payload

裁决：accepted blocking。

理由：Phase 13 plan 要求 Tool Trace 从 typed EventLog payload 中抽取 provider/tool refs、长参数/结果摘要、截断、duplicate、wait/cancel/timeout 与 raw diagnostic refs；不得用无结构全量 diagnostic payload 兜底。当前 `dayu/host/tool_trace.py` 的 `_build_cold_line()` 写入 `_FIELD_PAYLOAD: event.payload`，把完整 EventLog raw payload 复制进 cold JSONL。即使不影响 Host truth，也违背 ref-first / typed whitelist 边界，并可能把大工具结果或无结构 payload 放进 append-only 文件。

Required fix：

- 移除 cold JSONL 中的完整 `_FIELD_PAYLOAD` / `event.payload` 写入。
- 保留已有 typed fields、source payload ref/digest、extracted payload ref/digest、trace summary、operation context refs/digest。
- 更新测试，明确 cold JSONL 不包含 raw payload 字段，并仍包含 refs / digests。

### PR-F2: PR 全量 `git diff --check main...HEAD` 失败

裁决：accepted blocking。

理由：DS PR review 复现 `git diff --check main...HEAD` 在已提交 review artifact 中发现 trailing whitespace。虽然当前工作区 `git diff --check` clean，但 PR diff 本身不 clean，draft PR gate 不应通过。

Required fix：

- 清理 `docs/reviews/phase13-aggregate-deepreview-ds-20260529.md` 中的 trailing whitespace。
- 复跑 `git diff --check main...HEAD`，必须通过。

## Non-blocking Findings

- MiMo F002: audit/tool_trace 私有 helper 重复。裁决为 follow-up cleanup；不扩大本 PR fix 范围。
- MiMo F003: `OutboxProjectionStatus.FAILED` public 路径缺少测试。裁决为 test-hardening；当前已有 lag/catch-up 和 projection failure row aggregate review evidence，不阻塞 PR。
- MiMo F004: `read_api.__all__` 不完整。裁决为 low priority cleanup；该模块 public surface 由 package root 管理，不阻塞 PR。

## Validation Required

Fix 后必须运行：

- `source .venv/bin/activate && pytest tests/host/test_tool_trace_projection.py tests/host/test_tool_trace_queries.py -q`
- `source .venv/bin/activate && pytest tests/host/test_audit_sink.py tests/host/test_tool_trace_projection.py tests/host/test_tool_trace_queries.py tests/host/test_outbox_projection.py tests/host/test_outbox_durable.py tests/host/test_public_outbox_api.py tests/host/test_public_offline_outbox_smoke.py tests/host/test_projection_runner.py tests/host/test_projection_checkpoint.py tests/host/test_public_event_stream.py tests/host/test_watch_session_events.py tests/host/test_open_host_runtime.py tests/host/test_package_exports.py tests/host/test_durable_schema.py tests/host/test_import_boundary.py -q`
- `source .venv/bin/activate && python -m pyright dayu/host tests/host`
- `git diff --check`
- `git diff --check main...HEAD`

## Outcome

进入 PR 69 draft PR fix gate。修复、验证、re-review、accepted PR review commit 并 push 后，才能进入 `draft-PR-pass`。
