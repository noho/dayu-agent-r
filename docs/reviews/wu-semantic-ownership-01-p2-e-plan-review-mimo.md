# WU-SEMANTIC-OWNERSHIP-01 / P2-E Plan Review — AgentMiMo

## Review Context

- Reviewer: AgentMiMo
- Artifact under review: `docs/reviews/wu-semantic-ownership-01-p2-e-plan-codex.md`
- Controller validation: `docs/reviews/wu-semantic-ownership-01-p2-e-plan-controller-validation.md`
- Design ground truth: `docs/host/design.md`, `docs/engine/design.md`
- Control doc: `docs/host/issues-implementation-control.md`
- Gate: plan review

## Review Checklist

### 1. 7 failures — all stale test/fixture, or any must-fix production first?

**Verdict: All 7 are stale test/fixture alignment. None require production code changes.**

Direct evidence from code inspection:

| # | Failure | Root cause confirmed by code | Stale test? | Production regression? |
|---|---|---|---|---|
| 1 | stream idle heartbeat | Production logs at `STREAM_DEBUG_LOG_LEVEL=9` (`dayu/runtime/log_levels.py:16`); test caplog at `logging.DEBUG=10` (`test_stream_idle.py:207`). Companion `test_runner_diagnostics.py:383` correctly uses `STREAM_DEBUG_LOG_LEVEL`. | Yes | No |
| 2 | IterationStartedData fields | Production `IterationStartedData` has 6 fields including `input_projection` (`engine_events.py:94-112`); test expects 5 (`test_engine_event_contract.py:207-213`). | Yes | No |
| 3 | Engine `__all__` | Production exports `RunnerInputMessageProjection`, `RunnerInputToolCallProjection` (`dayu/engine/__init__.py:80-81,169-170`); test `EXPECTED_EXPORTS` missing both. | Yes | No |
| 4 | Host `__all__` | Production exports `HostThinkingView` (`dayu/host/__init__.py:200`); test `EXPECTED_HOST_EXPORTS` missing it. | Yes | No |
| 5 | Host.api `__all__` | Production exports `HostThinkingView` (`dayu/host/api.py:3565`); test `EXPECTED_API_EXPORTS` missing it. | Yes | No |
| 6 | wait-resume guidance | Production uses structured `UserMessage → AssistantMessage(tool_call) → ToolMessage` with Chinese fallback (`dayu/host/run_input.py:3846-3888`); test asserts old English `"A previous interrupted step..."` which no longer exists in codebase. | Yes | No |
| 7 | purge cancelling fixture | Production schema CHECK requires `cancel_request_event_id IS NOT NULL` for `cancelling`/`cancelled` (`dayu/host/durable/schema.py:536-540`); test `_insert_run_row` omits this column, causing `IntegrityError` before purge logic runs. | Yes | No |

**No finding.** Plan's classification is correct.

### 2. Slice E1/E2 grouping — too wide or needs more sub WUs?

**Verdict: Two slices is appropriate. Not too wide.**

Reasoning:

- The slice-principle doc (control doc §Slice 切分原则) states: "小型同一语义 cleanup 的默认切分上限是 3 个 implementation slices" and "对代码量较小、语义上属于同一个 contract cleanup / config cleanup / schema cleanup 的 work unit...应优先合并为少量可验证闭环 slices"。
- E1 (3 test files, all Engine-side) and E2 (3 test files, all Host-side) are natural module-boundary splits.
- Each slice forms an independently verifiable closure: E1 aligns Engine test expectations with accepted Engine contracts; E2 aligns Host test expectations with accepted Host contracts.
- Gate cost of 7 individual WUs (plan + dual review + controller + implementation + code review + re-review each) would far exceed implementation risk of ~6 test file edits.
- The plan's stop conditions (E1: "if `input_projection` lacks design/artifact support, stop"; E2: "if resume messages are not protocol closure, stop") correctly gate each slice against production regression.

**No finding.**

### 3. stream heartbeat `STREAM_DEBUG_LEVEL` — direct evidence?

**Verdict: Direct evidence exists.**

- `dayu/runtime/log_levels.py:16`: `STREAM_DEBUG_LOG_LEVEL: Final[int] = DEBUG_LOG_LEVEL - 1` = 9.
- `dayu/engine/runners/openai/runner.py:967-968`: heartbeat logged at `STREAM_DEBUG_LOG_LEVEL`.
- `tests/engine/runners/openai/test_stream_idle.py:207`: `caplog.at_level(logging.DEBUG, logger="dayu")` captures level ≥ 10 only.
- `tests/engine/runners/openai/test_runner_diagnostics.py:383`: correctly uses `log_level=STREAM_DEBUG_LOG_LEVEL` for the same heartbeat pattern.
- Engine design doc §1.1 defines stream terminology; `STREAM_DEBUG_LOG_LEVEL` is the designated gate for stream-only diagnostics below ordinary DEBUG.

Plan correctly identifies this as intentional diagnostic-level gating, not a production bug. The test must capture at `STREAM_DEBUG_LOG_LEVEL` to observe heartbeat, and should also assert that ordinary `DEBUG` does *not* capture it (to preserve `--debug` / `--debug-stream` semantics).

**Finding F-1 (LOW):** Plan's "Proposed fix location" says "更新该测试的 caplog level/import；不改 `runner.py`" but does not explicitly require the test to retain a negative assertion that ordinary `DEBUG` does *not* capture heartbeat. This negative assertion is important for preserving the `--debug` vs `--debug-stream` semantic gate. The plan's "Required direct evidence" section does mention "保留或补充普通 `DEBUG` 不捕获 stream heartbeat 的 gating 断言" — this should be elevated to a required test change, not just "still needed" evidence.

- Severity: LOW
- Owner boundary: test owner `tests/engine/runners/openai/test_stream_idle.py`
- Minimum fix: Update test to capture at `STREAM_DEBUG_LOG_LEVEL` AND add/retain assertion that `caplog.at_level(logging.DEBUG)` does NOT capture heartbeat.

### 4. Engine `input_projection` / projection exports — design ground truth support?

**Verdict: Fully supported by design ground truth.**

- `docs/engine/design.md` §14 (EngineEvent Stream table): "`iteration_started` 携带 Engine 对本次真实 Runner 输入的直接观察：`message_count`、按实际 message role 顺序计算的 `role_sequence_digest`、`runner_input_serializer_schema_version`，以及 `input_projection`。"
- `docs/engine/design.md` §2 (公共入口): "当前包根也导出 Runner 请求身份与输入观测相关公共契约，包括 `ClientCorrelationPolicy`、`RunnerRequestIdentity`、`build_runner_request_identity`、`RUNNER_INPUT_SERIALIZER_SCHEMA_VERSION`、`RunnerInputMessageProjection`、`RunnerInputToolCallProjection` 与 `runner_role_sequence_digest`。"
- `docs/engine/design.md` §14: "`input_projection` 是按实际 Runner 输入顺序排列的中性 LLM-facing message projection...不包含 Host-owned runner call index、manifest ref、source refs、memory / compact refs、tool schema refs、provider headers、Authorization/API key 或 provider raw request/response。"

All three items (`input_projection` field, `RunnerInputMessageProjection` export, `RunnerInputToolCallProjection` export) are explicitly documented in the Engine design ground truth as accepted public contract.

**No finding.**

### 5. `HostThinkingView` export — design/API support?

**Verdict: Fully supported by design ground truth.**

- `docs/host/design.md` §2 (EngineEvent Ingest): references Host event types including reasoning/thinking projection.
- `dayu/host/api.py:3061`: `HostEvent.thinking: HostThinkingView | None = None` with `__post_init__` validation.
- `dayu/host/read_api.py`: projects `EngineEventType.REASONING_DELTA` into `HostThinkingView`.
- `dayu/host/__init__.py:200` and `dayu/host/api.py:3565`: both export `HostThinkingView` in `__all__`.
- The `HostThinkingView` is a typed public view of `HostEvent.thinking`, consistent with the design principle that HostEvent data fields use typed views.

**No finding.**

### 6. wait-resume integration — assertion protocol closure; possible production regression masking?

**Verdict: Plan's stop condition correctly guards against masking production regression.**

Direct evidence:
- `dayu/host/run_input.py:3846-3866`: normal path emits `UserMessage → AssistantMessage(tool_call) → ToolMessage` structured sequence.
- `dayu/host/run_input.py:3881-3888`: fallback path uses Chinese self-explaining guidance (`恢复上下文：上一轮被等待中断的外部工具步骤已经完成...`).
- Test `test_phase7_waiting_integration.py:343-351` asserts old English string `"A previous interrupted step has an accepted wait result."` which does not exist anywhere in current production code.

The plan's Slice E2 stop condition states: "若 `resume_request.messages` 实际不是协议闭环，而是 fallback guidance 或缺 request atom，则停止；这将是 production wait-resume regression，owner 转为 `dayu/host/run_input.py` / awaiting accept path，而不是改测试。"

This is the correct approach: implementation must first inspect actual `resume_request.messages` content. If structured protocol messages are present (user prompt + assistant tool_call + tool result), update assertions. If only fallback guidance is present or messages are missing, this indicates a production regression and the slice must stop.

**Finding F-2 (MEDIUM):** Plan's proposed fix for failure 6 lists 4 bullet points for the new assertion but does not explicitly require verifying that the `AssistantMessage` tool call contains the correct `tool_call_id` matching the original awaiting request. The `tool_call_id` closure is the critical semantic invariant that proves the resume correctly reconstructs the tool call identity. Without this assertion, a partial fix could pass with a generic replay that doesn't match the original tool call.

- Severity: MEDIUM
- Owner boundary: integration assertion owner `tests/host/test_phase7_waiting_integration.py`
- Minimum fix: New assertion must verify `tool_call_id` in the `AssistantMessage` tool call matches the original awaiting tool call id, and `ToolMessage.tool_call_id` matches the same id. This closes the protocol identity loop.

### 7. purge cancelling fixture — proposed fix semantically effective?

**Verdict: Plan's proposed fix is semantically correct.**

Direct evidence:
- `dayu/host/durable/schema.py:536-540`: `CHECK (status NOT IN ('cancelling', 'cancelled') OR cancel_request_event_id IS NOT NULL)`.
- Test `_insert_run_row` helper omits `cancel_request_event_id`, causing `IntegrityError` on INSERT for `cancelling` status.
- The plan correctly identifies that the fixture must create a semantically valid cancel request EventLog row and reference its id in the Run row.

The plan's risk note about "pointing `cancel_request_event_id` at an arbitrary terminal event" is well-identified, and the mitigation ("prefer adding an explicit cancel request EventLog row in the fixture") is correct. A `CANCEL_REQUESTED` event row is the semantically correct referent for `cancel_request_event_id`.

**Finding F-3 (LOW):** Plan does not explicitly specify whether the fixture should also handle `cancelled` status (currently in `_NON_TERMINAL_RUN_STATUSES` or a separate parametrize). If `cancelled` is also parametrized, the same `cancel_request_event_id` fix applies. If `cancelled` is already tested separately or is a terminal status not in the purge rejection test, this is fine. Implementation should check.

- Severity: LOW
- Owner boundary: test fixture owner `tests/host/test_purge_session.py`
- Minimum fix: Verify whether `cancelled` status is also in the parametrize list; if so, apply the same `cancel_request_event_id` fixture fix.

### 8. validation/README/propagation audit — complete?

**Verdict: Mostly complete, with one gap.**

Validation plan:
- ✅ Targeted tests cover all 7 failing test files.
- ✅ Regression suite covers related modules (`test_resolve_wait_command.py`, `test_run_input_builder.py`, `test_wait_awaiting_accept.py`, `test_log_levels.py`, `test_runner_diagnostics.py`).
- ✅ Broad suite (`pytest tests/engine tests/runtime tests/service/test_host_assembly.py tests/host`).
- ✅ pyright and `git diff --check`.
- ✅ README trigger analysis correctly concludes no README update needed for test-only changes.
- ✅ Propagation audit for wait-resume LLM-facing semantics is thorough (6-step audit).

**Finding F-4 (LOW):** Validation plan does not include `pytest tests/engine/test_engine_event_contract.py` in the regression section — it only appears in targeted. While this is fine since it's directly fixed, the broader `pytest tests/engine` in the regression section does cover it. However, the regression section lists `tests/engine` as a whole which is quite broad; the plan could benefit from noting that the Engine event contract test is the specific regression guard for `input_projection` stability.

- Severity: LOW
- Owner boundary: validation plan
- Minimum fix: Optional — no action required, current coverage is adequate.

## Findings Summary

| ID | Severity | Description | Owner boundary | Minimum fix |
|---|---|---|---|---|
| F-1 | LOW | stream heartbeat test should retain negative assertion that ordinary DEBUG does not capture heartbeat | `tests/engine/runners/openai/test_stream_idle.py` | Add/retain negative assertion alongside positive fix |
| F-2 | MEDIUM | wait-resume assertion must verify `tool_call_id` identity closure in structured replay messages | `tests/host/test_phase7_waiting_integration.py` | Assert `tool_call_id` matches original awaiting request in both AssistantMessage and ToolMessage |
| F-3 | LOW | purge fixture fix should verify whether `cancelled` status also needs `cancel_request_event_id` | `tests/host/test_purge_session.py` | Check parametrize list; apply same fixture fix if `cancelled` is included |
| F-4 | LOW | Validation plan adequacy note — Engine event contract regression is implicitly covered by broad suite | validation plan | Optional — no action required |

## Conclusion

**Pass-with-findings.**

The plan is sound. All 7 failures are correctly classified as stale test/fixture alignment against accepted production contracts. No production code changes are required. The two-slice grouping is appropriate for the scope. Design ground truth supports all claimed public contracts (`input_projection`, projection exports, `HostThinkingView`). The wait-resume stop condition correctly guards against masking production regression.

Four findings are identified:
- **F-2 (MEDIUM)** is the only one that could allow a semantic gap if not addressed: the wait-resume test must verify `tool_call_id` identity closure, not just content presence. Without this, a test could pass with a partial or incorrect replay.
- **F-1, F-3, F-4 (LOW)** are completeness improvements that do not block implementation.

None of the findings require production code changes or design ground truth updates. All are test-side refinements.
