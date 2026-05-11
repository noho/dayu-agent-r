# PR #42 Fix Report — P8.5 Host stabilization

- **work gate**: PR review fix
- **branch**: `migration/host-p8-5-stabilization`
- **date**: 2026-05-11
- **role boundary**: fix handoff only；未启动 `$gateflow` / `/gateflow`，未 commit、push、merge、closeout。

## Source Review Artifacts

- `docs/reviews/pr-42-review-20260511-1547.md`
- `docs/reviews/pr-42-review-20260511-1552.md`
- `docs/reviews/pr-42-review-20260511-1554.md`
- `docs/reviews/code-review-20260511-1607.md`

## Controller Decisions

- Accepted findings 1-16 均在本 pass 处理。
- `run_input_raw_payloads` retention / deletion / TTL 不在 PR #42 临时实现，跟踪到 GitHub issue #43。
- P8.6 Recovery Model Re-challenge、P15 hard-gate/watchdog、P16 interface freeze 仍为后续 owner。
- 未恢复 `ToolTruncationInfo`、`ToolResultSuccess.truncation`、`TOOL_CURSOR_*`、`TOOL_RESULT_TRUNCATED`、`TOOL_FETCH_MORE_*`。
- Engine 仍只看到普通 tool schema / request / outcome；Host 私有 truncation/cursor/fetch_more 状态不回流 Engine。

## Fix Status

| Finding | Status | Notes |
| --- | --- | --- |
| 1. ToolTraceObserver 跨 batch 配对 | fixed | observer 维护实例级 pending group，request/result 可跨 checkpoint batch 配对；新增 split batch regression。 |
| 2. trace/raw payload path traversal | fixed | session/run/iteration/blob 逻辑 id 编码为安全 path segment，写入前做 trace root containment；覆盖 `/`、`\`、`..`、空 id、超长 id。 |
| 3. owner-lost 后 cursor mutation | fixed | business truncation 和 framework fetch_more 在 cursor registry mutation 前二次 owner verify；owner lost 时旧 cursor 保留、不提交 next cursor。 |
| 4. RunInput raw payload assistant tool-call credential scrub | fixed | assistant tool call arguments 写 side-store 前复用显式凭证 scrub；保留 cursor/scope_token/普通 token。 |
| 5. `_decode_result_success` 缺 value | fixed | 缺失 `value` fail-fast；显式 JSON null 仍允许。 |
| 6. caller-provided fetch_more schema | fixed | 任意调用方传入同名 `fetch_more` schema 均拒绝；Host harness 内部只做一次 schema projection，避免双重投影。 |
| 7. truncation 字段覆盖 | fixed | 原业务 object 已有 `truncation` 时包装为 `{"content": original, "truncation": host_hint}`。 |
| 8. credential scrub key coverage | fixed | 增加 `access_token`、`auth_token`、`secret_key`、`bearer_token` 及连字符形式；普通 `token` 不 scrub。 |
| 9. analyzer public surface | fixed | `ProviderPartialToolCallDiagnostic` 加入 `utils.analyze_tool_trace_host.__all__` 并测试。 |
| 10. durable truncation no special facts | fixed | durable scope 截断测试断言 EventLog 不追加 truncation/cursor/fetch_more 专属事实。 |
| 11. malformed truncation hint guards | fixed | 新增 malformed payload 参数化测试。 |
| 12. multi-tool concurrent truncation | fixed | 新增并发 apply_truncation 测试，断言独立 cursor。 |
| 13. `_replace_path` diagnostic | fixed | 错误信息包含 `field_path`、`key`、实际 `type`；新增测试。 |
| 14. dead code cleanup | fixed | 删除 `_fatal_terminated` 与 `_get_float`；未扩大清理。 |
| 15. focused unit tests | fixed | 新增 `_tool_result_truncation.py`、`_framework_tools.py`、`_run_input_raw_payload_store.py` 测试，补 text/binary/raw read error 等重点路径。 |
| 16. JSONL partial-line risk | fixed | 文档化 JSONL append 崩溃半行不变量；analyzer 跳过非法 JSON 行并继续按 `idempotency_key` 去重。 |

## Changed Files

- Host / Engine / utils:
  - `dayu/host/_tool_trace_projection.py`
  - `dayu/host/_tool_trace_jsonl_sink.py`
  - `dayu/host/_tool_runtime.py`
  - `dayu/host/_runtime_truncate_manager.py`
  - `dayu/host/_tool_result_truncation.py`
  - `dayu/host/_credential_scrub.py`
  - `dayu/host/_run_input_context_fact.py`
  - `dayu/host/_run_event_serializer.py`
  - `dayu/host/_durable_harness.py`
  - `dayu/engine/runners/openai/sse_parser.py`
  - `utils/analyze_tool_trace_host.py`
  - `utils/smoke_host_multiturn_no_governance.py`
- Tests:
  - `tests/host/test_phase2_tool_runtime_boundary.py`
  - `tests/host/test_phase2_tool_runtime_truncation.py`
  - `tests/host/test_phase6_projection_checkpoint.py`
  - `tests/host/test_phase6_run_event_serializer.py`
  - `tests/host/test_phase7_run_input_context_fact.py`
  - `tests/host/test_phase7_tool_trace_eventlog_source.py`
  - `tests/host/test_phase7_tool_trace_jsonl_sink.py`
  - `tests/host/test_phase7_tool_trace_projection.py`
  - `tests/host/test_phase8_5_credential_scrub.py`
  - `tests/host/test_phase8_tool_runtime_fencing.py`
  - `tests/host/test_phase8_5_framework_tools.py`
  - `tests/host/test_phase8_5_run_input_raw_payload_store.py`
  - `tests/host/test_phase8_5_tool_result_truncation.py`
  - `tests/utils/test_analyze_tool_trace_host.py`
- Docs:
  - `dayu/host/README.md`
  - `docs/host/migration-plan.md`
  - `tests/README.md`
  - `docs/reviews/pr-42-fix-report-20260511.md`

## Validation

- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - Result: `0 errors, 0 warnings, 0 informations`
- `source .venv/bin/activate && pytest tests/contracts tests/engine -q`
  - Result: `327 passed`
- `source .venv/bin/activate && pytest tests/host -q`
  - Result: `403 passed`
- `source .venv/bin/activate && pytest tests/utils/test_analyze_tool_trace_host.py -q`
  - Result: `18 passed`
- Focused tests added/changed:
  - Result: `122 passed`
- `git diff --check`
  - Result: passed, no output.

## Residual Risks And Owners

- `run_input_raw_payloads` retention / deletion / TTL: GitHub issue #43。
- Recovery model re-challenge: P8.6。
- observer hard-gate / required projection enforcement / watchdog: P15。
- Engine / Host public/internal interface freeze and final boundary cleanup: P16。
- JSONL append cannot be made per-line crash-atomic with the current append file model；current invariant is documented, reader skips malformed lines, and complete duplicate lines are deduped by `idempotency_key`.

## Stop Condition Status

- 未遇到需要新 policy decision 的 finding。
- trace cross-batch pairing 采用 non-required observer 的实例级 pending 行为，未引入 schema migration 或 durable pending-state。
- owner re-verify 未移动 ownership semantics 到 Engine 或 public contracts。
- 未 commit、push、merge 或更新 PR 状态。
