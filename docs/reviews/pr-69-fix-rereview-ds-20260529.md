# PR 69 Fix Re-review — AgentDS

## Gate

PR 69 draft PR fix gate re-review。

## Inputs

- Fix diff（当前工作区未提交）: `git diff`
- Fix report: `docs/reviews/pr-69-fix-codex-20260529.md`
- Original PR reviews:
  - `docs/reviews/pr-69-review-mimo-20260529.md`
  - `docs/reviews/pr-69-review-ds-20260529.md`
- Controller adjudication: `docs/reviews/pr-69-review-controller-adjudication-20260529.md`
- Design truth: `docs/host/design.md`
- Accepted plan: `docs/host/phase13-audit-tool-trace-outbox-plan.md`

## Blocking Finding Verification

### PR-F1: Tool Trace cold JSONL 复制完整 raw payload → FIXED

**Production change** (`dayu/host/tool_trace.py`):

- 删除 `_FIELD_PAYLOAD = "payload"` 常量。
- `_build_cold_line()` 移除 `_FIELD_PAYLOAD: event.payload` 写入。

cold JSONL line 当前写入字段（保留字段）:
- `event_id`, `event_class`, `event_type`, `occurred_at`, `run_id`, `attempt_id`, `execution_id`
- `source_payload_ref`, `source_payload_digest` — EventLog payload 间接引用
- `payload_ref`, `payload_digest` — 从 typed payload 中抽取的 payload 引用
- `operation_context_refs`, `operation_context_digest` — 操作上下文引用和摘要
- `trace_summary` — trace 摘要
- `cold_trace_ref`, `cold_trace_digest`, `line_digest`, `policy_decision`
- `diagnostic_refs` — 诊断引用

确认不再写入 `event.payload` 顶层 raw payload。

**Test change** (`tests/host/test_tool_trace_projection.py`):

- 新增 `_append_tool_event_in_transaction` helper，支持通过 `SQLitePayloadWriteRequest` 构造带 payload descriptor 的事件。
- `test_tool_call_chain_projects_hot_rows_and_cold_lines` 测试扩展：
  - 构造包含 `raw_result`（未白名单字段）、`operation_context`、extracted `payload_ref`/`payload_digest` 的事件。
  - 断言 cold JSONL 不含 `payload` 顶层字段：`assert "payload" not in result_line`
  - 断言 `raw_result` 不泄露进 cold JSONL：`assert "raw_result" not in json.dumps(result_line, sort_keys=True)`
  - 断言所有必要 refs/digests 仍存在：`payload_ref`、`payload_digest`、`source_payload_ref`、`source_payload_digest`、`diagnostic_refs`、`operation_context_refs`、`operation_context_digest`、`trace_summary`、`cold_trace_ref`、`cold_trace_digest`。

**验证结果**: 6 passed。

### PR-F2: PR 全量 `git diff --check main...HEAD` 失败 → FIXED（工作区）

**变更** (`docs/reviews/phase13-aggregate-deepreview-ds-20260529.md`):
- 行 131: trailing whitespace 清理
- 行 173: trailing whitespace 清理

**验证结果**:
- `git diff --check` → clean（工作区 diff 无 trailing whitespace）
- `git diff --check main...HEAD` → 仍报同两处 trailing whitespace。原因是 fix 未提交，该命令只检查 `HEAD` 相对 `main` 的已提交 diff。提交 fix 后该检查将纳入已清理内容。与 Codex fix report 中的分析一致，属于预期行为。

## Non-blocking Finding 确认

根据 Controller Adjudication，以下 findings 标记为 non-blocking，不在本次 fix 范围内：

- MiMo F002: audit/tool_trace 私有 helper 重复 — follow-up cleanup，未扩大 fix 范围。
- MiMo F003: `OutboxProjectionStatus.FAILED` 路径无测试 — test-hardening，不阻塞 PR。
- MiMo F004: `read_api.__all__` 不完整 — low priority cleanup，不阻塞 PR。

工作区 diff 确认未修改以上任何一项，符合 adjudication 裁决。

## 边界检查

### 未新增 payload reader

`git diff` 中不包含 `read_payload`、`get_payload`、`fetch_payload` 等符号。确认无 payload reader 新增。

### 未新增 timeline replay

`git diff` 中不包含 `replay`、`timeline`、`cursor` 等符号。`watch_session_events` 签名未改变。

### 未新增 public API

工作区 diff 仅修改 `tool_trace.py`（内部实现）和测试文件。`api.py`、`read_api.py`、`__init__.py` 均未修改。确认无 public API 扩张。

### 未扩大 tool trace whitelist

`_build_cold_line` 的变更仅删除 `_FIELD_PAYLOAD` 写入，未向 cold JSONL 添加新字段。`_FIELD_*` 常量列表中仅移除 `_FIELD_PAYLOAD`，无新增常量。

## 验证汇总

| 验证项 | 结果 |
|--------|------|
| `pytest tests/host/test_tool_trace_projection.py tests/host/test_tool_trace_queries.py` | 6 passed |
| `pytest tests/host/test_audit_sink.py ...(full aggregate suite)` | 108 passed |
| `python -m pyright dayu/host tests/host` | 0 errors, 0 warnings, 0 informations |
| `git diff --check` | clean |
| `git diff --check main...HEAD` | 仍报 2 trailing whitespace（已提交部分未清理，工作区已修复，提交后通过） |
| 未新增 payload reader | 确认 |
| 未新增 timeline replay | 确认 |
| 未新增 public API | 确认 |
| 未扩大 tool trace whitelist | 确认 |

## Residual Risk

- `git diff --check main...HEAD` 在 fix 提交前会持续报已提交 review artifact 中的 trailing whitespace。提交本 fix 后该检查将纳入已清理的文档内容，届时通过。不构成 blocking risk。
- 本次 fix 范围外已知 risk（跨介质 exactly-once、Outbox drain ≠ channel delivery success 等）仍在 `implementation-control.md` Phase 15 追踪区中，owner 未变。

## Verdict: PASS

PR-F1 和 PR-F2 均已修复。工具 trace cold JSONL 不再写入完整 raw event.payload，测试覆盖 raw payload 不泄露且 refs/digests 保留。trailing whitespace 已清理。未新增 payload reader、timeline replay、public API 或 tool trace whitelist 扩张。全部自动化验证通过（108 tests, pyright clean）。无新增 blocking findings。
