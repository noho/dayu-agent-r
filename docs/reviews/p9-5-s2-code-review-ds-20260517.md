# P9.5 S2 Engine / OpenAI Runner / Parser Hardening — Code Review (AgentDS)

## Gate

- Role: AgentDS, review-only.
- Gate: P9.5 S2 Engine / OpenAI Runner / Parser Hardening code review.
- Approved plan: `docs/host/p9-5-pre-p10-hardening-plan.md` section S2.
- Implementation artifact: `docs/reviews/p9-5-s2-engine-openai-runner-parser-implementation-20260517.md`.
- Reviewed files: `dayu/engine/runners/openai/non_stream_parser.py`, `dayu/engine/runners/openai/sse_parser.py`, `dayu/engine/runners/openai/usage.py`, `tests/engine/runners/openai/test_non_stream_response.py`, `tests/engine/runners/openai/test_protocol_error.py`, `tests/engine/runners/openai/test_sse_tool_call_stream.py`, `tests/engine/runners/openai/test_stream_non_stream_terminal_parity.py`, `tests/engine/test_metadata_boundary.py`, `dayu/engine/runners/openai/_types.py` (read for impact).
- No code, tests, plan, or artifacts were modified. No commit, push, or PR.

## Scope Adherence Verification

### Confirmed: no prohibited semantics introduced

- **No provider public state/contract**: `coerce_usage()` returns `UsageTokenCounts | None`, a private type; no new public Runner/Engine contract.
- **No retry redesign**: usage, retry granularity, or partial tool-call-delta retry behavior unchanged.
- **No Host governance**: no Host state, memory, tool governance, wait truth, or durable cursor in parser or event metadata.
- **No P10 semantics**: no proactive context governance, compaction provider, or compaction logic.
- **No P11/12/13/14/15 semantics**: no recovery, no ToolsDiscovery, no audit/tool trace sinks, no remote proxy, no purge/retention.

### Confirmed: plan boundaries honored

- All changes are within `dayu/engine/runners/openai/*`, `tests/engine/runners/openai/*`, and `tests/engine/test_metadata_boundary.py`.
- `dayu/engine/contracts/*` was read but not modified.
- `dayu/engine/agent.py` was not modified (metadata boundary test exercises it as a black-box through `_AsyncAgent`).

## Findings

Findings ordered by severity. Blocking status requires a fix before this slice's commit is accepted.

---

### F1 [Medium] `_OpenAIUsage` TypedDict is now dead code

- **File/line**: `dayu/engine/runners/openai/_types.py:152-157` (definition), `_types.py:226` (`__all__` export)
- **Evidence**: After S2 extracted usage normalization to `usage.py` and removed the `_OpenAIUsage` import from `sse_parser.py`, the `_OpenAIUsage` TypedDict has zero production consumers. Grep confirms the only references are its definition, `__all__` export in `_types.py`, and a historical mention in `docs/engine/phase1-plan.md`.
- **Impact**: Dead code accumulation. `_OpenAIUsage` was the only non-stream/SSE-parser-facing typed description of the usage dict shape; now that role belongs to `UsageTokenCounts` + `coerce_usage()` in `usage.py`. Keeping the unused TypedDict and its `__all__` export risks future developers importing it instead of the new shared helper.
- **Required fix**: Remove `_OpenAIUsage` class definition (lines 152-157) and its entry from `__all__` (line 226) in `_types.py`.
- **Blocking**: No. `_types.py` is private (`_`-prefixed module), and the dead type causes no runtime or correctness issue. However, this is inconsistent with the project's "禁止兼容性代码" rule — leaving dead code that the refactoring should have cleaned up.

---

### F2 [Medium] `bool`-as-`int` pattern persists in `_coerce_tool_call_delta` index handling

- **File/line**: `dayu/engine/runners/openai/sse_parser.py:464`
- **Evidence**:
  ```python
  index = raw.get("index")
  if isinstance(index, int):
      delta["index"] = index
  ```
  `isinstance(True, int)` is `True` in Python. A provider returning `{"index": true, ...}` would result in `delta["index"] = True`, which is typed as `int` in `_OpenAIToolCallDelta` but is semantically a `bool`. This is the identical pattern that was fixed for usage token counts in `usage.py:_is_token_count`.
- **Impact**: If a malformed provider response includes boolean `index` values, tool call deltas would be routed to index 0 or 1 instead of being rejected/diagnosed. The impact is limited because:
  - A provider emitting `bool` as `index` is an extreme protocol violation
  - The aggregator and delta event would still function, albeit with incorrect routing
- **Required fix**: Change `isinstance(index, int)` to `isinstance(index, int) and not isinstance(index, bool)` at line 466, matching the `_is_token_count` pattern. Optionally add a `WARN` diagnostic.
- **Blocking**: No. This is a speculative hardening extension of the evidenced bool-in-int fix for usage. The plan states "Fix only directly evidenced parser defects." No direct evidence of bool index values from real providers exists. However, consistency with the usage fix (same file, same pattern) makes this a reasonable same-scope fix.

---

### F3 [Low] `bool`-as-`int` pattern in `ToolCallAggregator._resolve_index`

- **File/line**: `dayu/engine/runners/openai/tool_call_aggregator.py:158`
- **Evidence**:
  ```python
  delta_index = delta.get("index")
  if isinstance(delta_index, int):
      return delta_index
  ```
  Same `bool` acceptance issue. If `delta_index` is `True`/`False`, the aggregator routes the delta to internal index 0 or 1.
- **Impact**: Same limited impact as F2; index misrouting under extremely malformed provider protocol.
- **Required fix**: Same fix pattern — `isinstance(delta_index, int) and not isinstance(delta_index, bool)`.
- **Blocking**: No. Same reasoning as F2.

---

### F4 [Low] Non-stream parser `non_stream_missing_choices` error lacks `partial_tool_calls`

- **File/line**: `dayu/engine/runners/openai/non_stream_parser.py:215-228`
- **Evidence**: When `choices` is missing or empty in the non-stream path, the `RunnerProtocolErrorData` is emitted with default `partial_tool_calls=()`. The `ToolCallAggregator` is never instantiated in this error path, so there are genuinely no partial tool calls to report. However, the SSE path always includes `self._aggregator.partial_summaries()` in its protocol error events.
- **Impact**: No behavioral difference — non-stream errors at this stage cannot have partial tool calls. The absence is correct, not a gap.
- **Required fix**: None. Documented for reviewer awareness only.
- **Blocking**: No.

---

### F5 [Info] `_finalize_success` guard condition is logically unreachable

- **File/line**: `dayu/engine/runners/openai/sse_parser.py:570`
- **Evidence**:
  ```python
  if self._terminated and self._finish_reason is FinishReason.ERROR:
      return
  ```
  `_finish_reason` is set only from provider `finish_reason` strings via `_FINISH_REASON_MAP`, which maps `"stop"`, `"length"`, `"tool_calls"`, `"content_filter"` — never `ERROR`. Unknown finish reasons are logged and default to `STOP`. So `self._finish_reason is FinishReason.ERROR` is always `False`.
- **Impact**: The guard never triggers. In error paths where `_terminated=True`, the `parse()` loop already breaks before reaching `_finalize_success`, so the guard is harmless dead code.
- **Required fix**: None for S2 (pre-existing code). Flagged for controller awareness — could be cleaned up or should be replaced with a `_finalize_success` guard that checks `if self._terminated: return`.
- **Blocking**: No. Pre-existing, not introduced by S2.

---

### F6 [Info] `_is_token_count` TypeGuard and `coerce_usage` contract are correct

- **File/line**: `dayu/engine/runners/openai/usage.py:34-67`
- **Verification**:
  - `_is_token_count(None)` → `False` (missing field correctly rejected)
  - `_is_token_count(True)` → `False` (bool correctly rejected)
  - `_is_token_count(1.5)` → `False` (float correctly rejected)
  - `_is_token_count("10")` → `False` (string correctly rejected)
  - `_is_token_count(0)` → `True` (zero is valid token count)
  - `_is_token_count(-1)` → `True` (negative is accepted; non-negative check explicitly deferred — see plan acknowledgment)
  - `TypeGuard[int]` correctly narrows the type for pyright
  - `coerce_usage` accepts `Mapping[str, JsonValue]` while callers pass `dict` — correct covariance
- **Required fix**: None.
- **Blocking**: No.

---

### F7 [Info] Metadata boundary test correctly proves no log leakage

- **File/line**: `tests/engine/test_metadata_boundary.py:228-269`
- **Verification**:
  - Test creates a real `_AsyncAgent` with a fake `_MetadataBoundaryRunner`
  - Fake runner emits 2 scripted events: `RUNNER_CONTENT_COMPLETED` + `RUNNER_DONE`
  - Test captures DEBUG-level logs from `dayu.engine.agent` via caplog
  - After collecting all `EngineEvent`s, asserts:
    1. `event.metadata is None` for every event
    2. `not isinstance(event.metadata, logging.LogRecord)` (belt-and-suspenders)
    3. `not isinstance(event.data, logging.LogRecord)` (event data is typed correctly)
  - `assert caplog.records` ensures the test is non-vacuous (logs were actually produced)
- **Gap identified**: The test verifies metadata is `None`, confirming no log record leakage. However, it does NOT test the case where metadata might legitimately be populated with `Mapping[str, JsonValue]` in the future. This is by design — the current contract allows `metadata: Mapping[str, JsonValue] | None`, and the test proves the current Agent path sets it to `None`. Any future change that populates metadata should add corresponding tests.
- **Required fix**: None. Test coverage is adequate for current behavior.
- **Blocking**: No.

---

### F8 [Info] Non-stream `coerce_usage` diagnostic log correctly defers to shared helper

- **File/line**: `dayu/engine/runners/openai/non_stream_parser.py:300-323`
- **Verification**:
  - Non-stream path now calls `coerce_usage()` and branches on `None`
  - WARN log emitted with `type().name` of malformed fields — safe, no raw values logged
  - Correctly omits `RUNNER_USAGE_RECORDED` when malformed (matching SSE behavior)
  - Previously silently ignored malformed non-stream usage — now diagnosed
- **Required fix**: None.
- **Blocking**: No.

---

## Residual Risks and Test Gaps

### Explicitly acknowledged (from implementation artifact)

1. **No non-negative range checks on token counts** — `_is_token_count` accepts negative integers. Acknowledged as out of scope because current contracts don't define token-count range validation. Risk: provider returning negative token counts would pass validation and propagate to `RunnerUsageRecordedData`.

### Identified in review

2. **Dead `_OpenAIUsage` TypedDict** — F1 above. Low risk but incurs maintenance confusion.
3. **`bool`-as-`int` in index handling** — F2/F3 above. Low risk in practice; defense-in-depth gap.
4. **No unit test for `coerce_usage()` in isolation** — All coverage is through parser integration tests (`test_non_stream_response.py`, `test_protocol_error.py`). No standalone test for edge cases like all-three-bool, mixed-missing-and-wrong-type, extremal int values.
5. **Finish reason parity matrix excludes `tool_calls`** — `test_stream_and_non_stream_content_finish_reason_parity` parametrizes `("stop", "length", "content_filter")` but not `"tool_calls"`. The `tool_calls` finish reason is already covered by `test_stream_and_non_stream_thought_strip_terminal_parity` (which uses `"stop"`) and `test_non_stream_tool_calls_emitted` (which uses `"tool_calls"`), but a direct cross-path parity assertion for `tool_calls` finish reason is absent. The existing tool-call parity tests focus on `RunnerToolCallsCompletedData` payload correctness rather than `RunnerDoneData.finish_reason` parity.
6. **Non-stream parser doesn't thread `provider_request_id` through `_build_tool_calls` log messages** — The aggregator receives `provider_request_id` at construction, so downstream fatal/warning events carry it. The non-stream parser's own error paths (e.g., `non_stream_missing_choices`) correctly thread `provider_request_id`. No gap found on closer inspection.

## P9.5 Scope / Non-Goals Check

| Concern | Status |
|---|---|
| Provider public state/contract | Not introduced |
| Retry model redesign | Not introduced |
| Host governance in parser/runner | Not introduced |
| Memory/tool governance in metadata | Not introduced |
| Proactive context governance | Not introduced |
| P10+ semantics | Not introduced |
| `RECOVERING` / Phase 11 | Not introduced |
| God object/function/dataclass | Not introduced |
| Compatibility re-export/wrapper | Not introduced |
| `Any`/`object`/untyped signatures | Not introduced |
| Extra payload bag | Not introduced |

## Summary

- **Blocking findings**: 0
- **Non-blocking findings**: 4 (F1–F4), with F1 (dead code) and F2 (bool-in-index consistency) recommended for fix
- **Info observations**: 4 (F5–F8)
- **Residual risks**: 6 documented (1 from implementation artifact, 5 from review)

The implementation correctly addresses the three directly evidenced defects from the plan: bool-vs-int in usage parsing (via `_is_token_count`), non-stream malformed usage silent-ignore (via WARN diagnostic), and metadata/log boundary test (via behavioral `_AsyncAgent` test). The extraction of `coerce_usage()` into a shared `usage.py` module eliminates the duplicate `isinstance(int)` checks that existed in both parsers. Targeted tests for bool usage malformed behavior, parallel tool-call id fallback, and finish reason parity matrix are well-constructed with direct assertions on event type sequences, payload fields, and diagnostic log content.

The only recommended pre-commit fix is F1 (remove dead `_OpenAIUsage` TypedDict). F2/F3 are defense-in-depth improvements consistent with the evidenced pattern but lack direct provider-protocol evidence, so they sit at the "controller discretion" boundary described in the plan's stop conditions.
