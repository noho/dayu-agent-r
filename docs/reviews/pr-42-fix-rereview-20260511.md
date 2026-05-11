# PR #42 Fix Re-review — P8.5 Host stabilization

- **review gate**: PR re-review
- **review target**: 当前 workspace diff after PR #42 fix pass
- **date**: 2026-05-11
- **role boundary**: Gateflow-governed re-review handoff；未启动 `$gateflow` / `/gateflow`；未修代码、未 commit、未 push、未更新 PR、未 closeout。
- **source review artifacts**:
  - `docs/reviews/pr-42-review-20260511-1547.md`
  - `docs/reviews/pr-42-review-20260511-1552.md`
  - `docs/reviews/pr-42-review-20260511-1554.md`
  - `docs/reviews/code-review-20260511-1607.md`
- **fix artifact**: `docs/reviews/pr-42-fix-report-20260511.md`

## Reviewer Conclusion

通过。

16 项 controller-accepted findings 均有代码或测试证据显示已修复，未发现新的 PR 阻塞项。controller-deferred scope 仍按既有 owner 记录，没有在 PR #42 fix pass 中被临时实现或漂移。

## Per-finding Status

| # | Status | Evidence |
| --- | --- | --- |
| 1. ToolTraceObserver 跨 batch request/result pairing | fixed | `ToolTraceObserver` 持有实例级 `_pending_tool_call_groups` 与 `_pending_lock`，`TOOL_CALL_REQUESTED` / `TOOL_RESULT_ACCEPTED` 经 `_collect_tool_call()` 跨 batch 暂存，只有 pair 齐全才 `_emit_tool_call()` 并清理 pending（`dayu/host/_tool_trace_projection.py:126`, `:206`, `:241`, `:251`）。测试 `test_tool_call_missing_accepted_waits_for_later_batch` 先处理 request、再处理 usage、最后处理 accepted，最终输出 `iteration_usage` + `tool_call`（`tests/host/test_phase7_tool_trace_projection.py:278`）。 |
| 2. trace/raw payload path construction 防 path traversal | fixed | `append_record_line()` 与 `write_raw_payload_blob()` 对 session/run/iteration/blob 逻辑 id 使用 `_safe_path_segment()`，并在目录和文件路径上调用 `_assert_under_root()`（`dayu/host/_tool_trace_jsonl_sink.py:149`, `:184`, `:234`, `:253`）。测试覆盖 `../s/..\\evil` 与 2048 字符长 id，断言最终路径仍在 root 内且 segment 长度受控（`tests/host/test_phase7_tool_trace_jsonl_sink.py:67`, `:89`）。 |
| 3. owner-lost after initial verify 不得消费/签发 cursor | fixed | framework `fetch_more` 传入 `owner_verifier`，manager 在读取 record 后、以及提交 next cursor / 删除旧 cursor 前二次 `verify_active_owner()`（`dayu/host/_tool_runtime.py:302`, `dayu/host/_runtime_truncate_manager.py:333`, `:396`）。业务工具成功后在 `apply_truncation()` 前二次校验 owner（`dayu/host/_tool_runtime.py:323`）。测试覆盖业务 truncation owner lost 后不签发 cursor、fetch_more owner lost 后旧 cursor 保留（`tests/host/test_phase8_tool_runtime_fencing.py:401`, `:427`）。 |
| 4. RunInput raw payload assistant tool-call arguments scrub 凭证 | fixed | `_message_to_dict()` 对 `AssistantMessage.tool_calls[].arguments` 复用 `scrub_tool_arguments()`（`dayu/host/_run_input_context_fact.py:324`, `:331`）。测试覆盖 `api_key`、`password`、`client_secret`、`Authorization`、`access_token` 被 scrub，同时 `cursor`、`scope_token`、普通 `token` 保留（`tests/host/test_phase7_run_input_context_fact.py:161`）。 |
| 5. `_decode_result_success` 缺 value fail-fast，允许 JSON null | fixed | `_decode_result_success()` 先检查 `"value" not in value` 并抛 `ValueError`，随后用 `value["value"]`，因此缺字段与显式 `null` 被区分（`dayu/host/_run_event_serializer.py:816`, `:832`）。测试覆盖缺 value 报 `missing value` 与 `value: null` 解码为 `None`（`tests/host/test_phase6_run_event_serializer.py:230`, `:260`）。 |
| 6. caller-provided `fetch_more` schema 即使 identical 也拒绝 | fixed | `engine_visible_tool_schemas()` 对任何 user schema 与 framework tool name 冲突均抛 `ValueError`，不再允许 identical schema 直通（`dayu/host/_tool_runtime.py:264`, `:269`）。测试直接把 runtime 的 framework schema 作为 user schema 传入并断言拒绝（`tests/host/test_phase2_tool_runtime_boundary.py:271`）。 |
| 7. Host truncation hint 不覆盖业务 `truncation` 字段 | fixed | `inject_truncation_hint()` 遇到原 value 是 object 且已有 `truncation` 字段时返回 `{"content": original, "truncation": host_hint}`，保留业务字段（`dayu/host/_tool_result_truncation.py:60`）。测试断言原业务 `truncation` 留在 `content` 中（`tests/host/test_phase8_5_tool_result_truncation.py:31`）。 |
| 8. credential scrub keyset 扩展 common credential names | fixed | keyset 与文本正则包含 `access_token` / `access-token`、`auth_token` / `auth-token`、`secret_key` / `secret-key`、`bearer_token` / `bearer-token`，同时仍不把普通 `token` 当凭证（`dayu/host/_credential_scrub.py:22`, `:49`）。相关测试在 trace、RunInput raw payload、provider secret scrub 中覆盖新增键与普通 token 保留。 |
| 9. `ProviderPartialToolCallDiagnostic` 加入 analyzer `__all__` 和测试 | fixed | dataclass 已定义并作为 `TraceAnalysisReport.provider_partial_tool_calls` 元素类型，`__all__` 包含该类（`utils/analyze_tool_trace_host.py:260`, `:314`, `:1276`）。测试断言类名及 `analyzer.__all__` 包含该符号（`tests/utils/test_analyze_tool_trace_host.py:844`）。 |
| 10. durable truncation path asserts no special RunEvent facts | fixed | durable fencing tests 对 business truncation、owner-lost、fetch_more、scope mismatch、expired fetch_more 等路径断言 `store.list_events(...) == ()`，证明不追加 truncation/cursor/fetch_more 专属 facts（`tests/host/test_phase8_tool_runtime_fencing.py:369`, `:397`, `:534`, `:567`, `:602`）。RunEventType 当前仅保留普通 `TOOL_CALL_REQUESTED` / `TOOL_RESULT_ACCEPTED` 映射，无 `TOOL_CURSOR_*` / `TOOL_FETCH_MORE_*` / `TOOL_RESULT_TRUNCATED`。 |
| 11. malformed `extract_truncation_hint` guard branches tested | fixed | `test_extract_truncation_hint_returns_none_for_malformed_payload` 参数化覆盖非 object、非 mapping truncation、非 bool `has_more`、has_more=True 但缺 cursor/scope token、cursor/scope token 类型错误等 guard（`tests/host/test_phase8_5_tool_result_truncation.py:52`）。 |
| 12. multi-tool concurrent truncation tested | fixed | `test_concurrent_apply_truncation_for_multiple_tools_registers_independent_cursors` 并发对两个 tool 调用 `apply_truncation()`，断言 cursor 不同且 registry 同时持有二者（`tests/host/test_phase2_tool_runtime_truncation.py:779`）。 |
| 13. `_replace_path` diagnostic improved and covered | fixed | `_replace_path()` 错误信息包含 `field_path`、`key` 与实际类型（`dayu/host/_runtime_truncate_manager.py:1068`）。测试匹配 `field_path=nested.long key=nested type=str`（`tests/host/test_phase2_tool_runtime_truncation.py:552`）。 |
| 14. `_fatal_terminated` and `_get_float` dead code removed | fixed | `rg -n "fatal_terminated|def _get_float|_get_float\\(" dayu/engine/runners/openai/sse_parser.py dayu/host/_run_event_serializer.py` 无命中。pyright 与 focused regression tests 通过，未见行为回归信号。 |
| 15. focused unit tests added/improved | fixed | 新增/补强 `tests/host/test_phase8_5_tool_result_truncation.py`、`tests/host/test_phase8_5_framework_tools.py`、`tests/host/test_phase8_5_run_input_raw_payload_store.py`；并在 runtime truncation/fencing 路径补充 owner reverify、multi-tool concurrent truncation、`_replace_path`、EventLog no special facts 等 tests。focused suite 本次重跑 `117 passed`。 |
| 16. JSONL append partial-line risk documented/tested or residualized | fixed | sink 模块 docstring 明确 JSONL append 不是崩溃原子，读侧必须跳过非法 JSON 行并按 `idempotency_key` 去重（`dayu/host/_tool_trace_jsonl_sink.py:13`）。analyzer 在 `json.JSONDecodeError` 时跳过该行继续读取（`utils/analyze_tool_trace_host.py:1102`）。测试 `test_analyzer_skips_malformed_jsonl_partial_line` 注入半行后仍统计两条完整记录（`tests/utils/test_analyze_tool_trace_host.py:856`）。残余风险仍保留为当前文件模型下的 crash-atomicity 限制。 |

## Deferred Scope Check

- `run_input_raw_payloads` retention / deletion / cleanup policy 未在 PR #42 中临时实现。`docs/host/migration-plan.md` 明确记录 side-store 当前不做 retention 清理，长期增长策略由 GitHub issue #43 跟踪，PR #42 不加入 ad-hoc `DELETE` / TTL（`docs/host/migration-plan.md:140`）。代码搜索未发现 `DELETE FROM run_input_raw_payloads` 或清理 API。
- P8.6 Recovery Model Re-challenge 仍记录为 next entry / deferred owner；`docs/host/migration-plan.md` 保留 P8.6 对 recovery scan、startup_reconcile、corrupt memory snapshot row 的重新挑战范围。
- P15 hard-gate/watchdog/required projection enforcement 与 P16 public/internal interface freeze 仍在 residual registry 中标记为 deferred-with-owner，fix pass 未越界实现。

## New Blockers

无。

## Validation

本次 re-review 实际执行：

```bash
source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
```

结果：`0 errors, 0 warnings, 0 informations`。

```bash
source .venv/bin/activate && pytest tests/host/test_phase7_tool_trace_projection.py tests/host/test_phase7_tool_trace_jsonl_sink.py tests/host/test_phase8_tool_runtime_fencing.py tests/host/test_phase7_run_input_context_fact.py tests/host/test_phase6_run_event_serializer.py tests/host/test_phase2_tool_runtime_boundary.py tests/host/test_phase2_tool_runtime_truncation.py tests/host/test_phase8_5_tool_result_truncation.py tests/host/test_phase8_5_framework_tools.py tests/host/test_phase8_5_run_input_raw_payload_store.py tests/utils/test_analyze_tool_trace_host.py -q
```

结果：`117 passed in 0.27s`。

```bash
source .venv/bin/activate && git diff --check
```

结果：通过，无输出。

Fix artifact 已报告但本次未重跑的更大集合：

- `python -m pyright dayu/ tests/ utils/`: `0 errors, 0 warnings, 0 informations`；本次已重跑并一致。
- `pytest tests/contracts tests/engine -q`: `327 passed`。
- `pytest tests/host -q`: `403 passed`。
- `pytest tests/utils/test_analyze_tool_trace_host.py -q`: `18 passed`。
- focused tests: `122 passed`。
- `git diff --check`: passed；本次已重跑并一致。

## Residual Risks And Owners

- `run_input_raw_payloads` side-store 长期 retention / cleanup：GitHub issue #43；PR #42 不做临时 TTL / delete。
- JSONL append crash atomicity：当前 owner 是 trace reader/analyzer invariant；reader 跳过 malformed line，完整重复行由 `idempotency_key` 去重。若未来要求文件级强原子行追加，需要后续 work unit 改写写入模型。
- Recovery model re-challenge：P8.6。
- observer hard-gate / required projection enforcement / watchdog：P15。
- Engine / Host public/internal interface freeze 与最终边界收口：P16。

## Stop Condition Status

- accepted findings 已逐项 re-reviewed。
- 未发现新增 blocker。
- 未修改生产代码、测试或 README；本 re-review 仅新增本 artifact。
- 未 commit、push、PR update、merge 或 closeout。

