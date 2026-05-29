# PR 69 Fix Re-Review — AgentMiMo

## Gate

PR 69 draft PR fix re-review gate。

## Source Artifacts

- Controller adjudication: `docs/reviews/pr-69-review-controller-adjudication-20260529.md`
- Codex fix report: `docs/reviews/pr-69-fix-codex-20260529.md`
- MiMo PR review: `docs/reviews/pr-69-review-mimo-20260529.md`
- DS PR review: `docs/reviews/pr-69-review-ds-20260529.md`

## Accepted Findings Verification

### PR-F1: Tool Trace cold JSONL 复制完整 raw payload — FIXED ✅

**验证方式**：逐行审查 `git diff` + 代码搜索 + 测试运行。

**证据**：

1. `_FIELD_PAYLOAD` 常量已从 `dayu/host/tool_trace.py` 删除（原 line 104）。`grep "_FIELD_PAYLOAD" tool_trace.py` 仅匹配 `_FIELD_PAYLOAD_REF` 和 `_FIELD_PAYLOAD_DIGEST`，无 raw payload 常量残留。
2. `_build_cold_line()` dict 构造（line 670-693）不再包含 `_FIELD_PAYLOAD: event.payload`。`fields_without_digest` 只含 typed fields、extracted refs/digests、source refs/digests、operation_context refs/digest、trace_summary。
3. `event.payload` 在 tool_trace.py 中仍有 5 处引用（line 433, 504, 553, 658, 738），均为从 typed EventLog payload 中抽取字段的读操作，不写入 cold JSONL。符合 typed whitelist 设计。
4. 测试 `test_tool_call_chain_projects_hot_rows_and_cold_lines` 已更新：
   - 构造事件包含 `raw_result: {"unbounded_text": "raw payload must stay in EventLog only"}` 与 `payload_ref="artifact://event-log-payload"`。
   - 断言 `"payload" not in result_line`（cold JSONL 不含顶层 raw payload 字段）。
   - 断言 `"raw_result" not in json.dumps(result_line, sort_keys=True)`（raw payload 内容不泄露）。
   - 断言 cold JSONL 仍包含：`payload_ref`, `payload_digest`, `source_payload_ref`, `source_payload_digest`, `diagnostic_refs`, `operation_context_refs`, `operation_context_digest`, `trace_summary`, `cold_trace_ref`, `cold_trace_digest`。

**结论**：PR-F1 完全修复。raw payload 不再写入 cold JSONL；typed fields、refs、digests 全部保留。

### PR-F2: PR diff trailing whitespace — FIXED ✅（工作区已清理，待提交）

**验证方式**：`git diff --check` 命令审查。

**证据**：

1. `git diff --check`（工作区全量）：**通过**，无输出。
2. `git diff --check main`（工作区 vs main）：**通过**，无输出。
3. `git diff main...HEAD --check`（已提交 PR diff）：**失败**，报告 `docs/reviews/phase13-aggregate-deepreview-ds-20260529.md` 第 131 行和第 173 行 trailing whitespace。
4. `git diff -- docs/reviews/phase13-aggregate-deepreview-ds-20260529.md` 确认工作区已有清理改动（unstaged），但未提交。

**结论**：PR-F2 修复已在工作区就绪。工作区 `git diff --check` 与 `git diff --check main` 均 clean。已提交 PR diff（`main...HEAD`）仍含 2 处 trailing whitespace，需提交 fix 后消除。这与 Codex fix report 的说明一致。

## 负面验证：未新增禁止项

| 检查项 | 结果 |
|--------|------|
| payload reader / `read_payload()` API | 未新增 ✅ |
| timeline replay / cursor-based `watch_session_events` | 未新增 ✅ |
| public API 扩张（`Host` Protocol 新方法） | 未新增 ✅ |
| Tool Trace event whitelist 扩张 | 未新增 ✅ |
| `__all__` 变更 | 未变更 ✅ |

## 复跑验证

| 验证项 | 结果 |
|--------|------|
| `pytest tests/host/test_tool_trace_projection.py tests/host/test_tool_trace_queries.py -q` | **6 passed** ✅ |
| aggregate host suite（16 个 test 模块） | **108 passed** ✅ |
| `pyright dayu/host tests/host` | **0 errors, 0 warnings, 0 informations** ✅ |
| `git diff --check`（工作区） | **clean** ✅ |
| `git diff --check main`（工作区 vs main） | **clean** ✅ |
| `git diff main...HEAD --check`（已提交 PR diff） | **2 trailing whitespace** ⚠️ 待提交 fix |

## Open Questions

无。

## Residual Risk

- PR-F2 trailing whitespace fix 已在工作区就绪，提交后 `git diff main...HEAD --check` 将 clean。
- 无新增 residual risk。Phase 13 原有 residual risks（跨介质 exactly-once、Outbox drain ≠ channel delivery success、purge/retention）不因本次 fix 变化。

## Verdict

**PASS**。

PR-F1 完全修复：raw payload 不再写入 cold JSONL，typed fields/refs/digests 保留，测试覆盖 raw payload 不泄露与 refs/digests 存在。PR-F2 修复已在工作区就绪，工作区 diff clean，待提交后已提交 PR diff 亦将 clean。未新增 payload reader、timeline replay、public API 或 tool trace whitelist 扩张。全部 108 个 aggregate host tests 通过，pyright 0 errors。无新 blocking findings。
