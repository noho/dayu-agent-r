# P9.5 S2 Code Re-Review — AgentDS

## Gate

- Role: AgentDS, re-review only. No code, test, artifact modification. No commit, push, or PR.
- Gate: S2 fix re-review post controller adjudication.
- Source review: `docs/reviews/p9-5-s2-code-review-ds-20260517.md`.
- Controller adjudication: `docs/reviews/p9-5-s2-code-review-controller-adjudication-20260517.md`.
- Fix artifact: `docs/reviews/p9-5-s2-fix-20260517.md`.
- Approved plan: `docs/host/p9-5-pre-p10-hardening-plan.md` section S2.

## Scope

Verify controller-accepted findings F1, F2, F3 from `docs/reviews/p9-5-s2-code-review-ds-20260517.md` are fixed per `docs/reviews/p9-5-s2-code-review-controller-adjudication-20260517.md`, and no new blocking issue was introduced.

## Fix Verification

### F1: Remove dead `_OpenAIUsage` TypedDict

- **Adjudication**: Accepted as required fix.
- **Fix claim**: Removed `_OpenAIUsage` class definition and its `__all__` entry from `dayu/engine/runners/openai/_types.py`.
- **Direct evidence**:
  - `_types.py` diff: lines 152-157 (`class _OpenAIUsage(TypedDict, total=False): ...`) removed.
  - `_types.py` diff: line 226 (`"_OpenAIUsage"` from `__all__`) removed.
  - `_types.py` diff: imports restructured — `_OpenAIUsage` line removed from `sse_parser.py` import block.
  - Grep for `_OpenAIUsage` in `dayu/engine/`: zero matches.
- **Status**: **FIXED**.

### F2: Reject bool index in `SSEParser._coerce_tool_call_delta`

- **Adjudication**: Accepted as required fix.
- **Fix claim**: Reused parser-internal `_is_tool_call_index()` check; bool-valued `index` no longer enters `_OpenAIToolCallDelta` as semantic integer.
- **Direct evidence**:
  - `sse_parser.py:469`: `isinstance(index, int)` → `_is_tool_call_index(index)`.
  - `_is_tool_call_index` is imported from `tool_call_aggregator` at line 55.
  - `_is_tool_call_index(value)` implementation at `tool_call_aggregator.py:48-57`:
    ```python
    return isinstance(value, int) and not isinstance(value, bool)
    ```
    This correctly rejects `True`/`False` (bool is subclass of int in Python) while accepting real `int`.
  - Test `test_bool_index_tool_calls_stay_separate_by_id` added in `test_sse_tool_call_stream.py:128`: full SSE-path test with `{"index":true,"id":"call-a",...}` / `{"index":false,"id":"call-b",...}`. Proves bool indexes are rejected by parser, id fallback routes correctly, and completed tool calls have correct `index_in_iteration` ordering.
- **Status**: **FIXED**.

### F3: Reject bool index in `ToolCallAggregator._resolve_index`

- **Adjudication**: Accepted as required fix.
- **Fix claim**: Added `_is_tool_call_index()` with `TypeGuard[int]` and applied in `_resolve_index()`.
- **Direct evidence**:
  - `tool_call_aggregator.py:48-57`: `_is_tool_call_index()` defined with `TypeGuard[int]`, same `isinstance(value, int) and not isinstance(value, bool)` pattern.
  - `tool_call_aggregator.py:170`: `isinstance(delta_index, int)` → `_is_tool_call_index(delta_index)`.
  - `_is_tool_call_index(None)` → `False` (missing index correctly rejected).
  - `_is_tool_call_index(True)` → `False` (bool correctly rejected).
  - `_is_tool_call_index(0)` → `True` (real int index accepted).
  - Test `test_aggregator_rejects_bool_index_and_falls_back_to_id` added in `test_sse_tool_call_stream.py:169`: direct aggregator-level test feeding `delta = {"index": True, "id": "call-bool", ...}`. Proves resolved index is `0` (synthetic), `result.fatal_errors == ()`, and completed tool call preserves correct `tool_call_id`.
- **Status**: **FIXED**.

## No New Blocker Introduced

### Scope boundary verification

- All fix changes are within controller-approved fix scope: `_types.py`, `sse_parser.py`, `tool_call_aggregator.py`, `test_sse_tool_call_stream.py`, fix artifact.
- No provider public state, public contract, retry behavior, Host governance, memory/tool governance, proactive context governance, or P10+ semantics introduced or altered.
- `_is_tool_call_index` is a private parser-internal helper; it exposes no new public contract.
- No `RunnerEvent` / `EngineEvent` contract change.

### Type consistency

- `_is_tool_call_index` uses `TypeGuard[int]`, matching `_is_token_count` pattern in `usage.py`. Both correctly narrow `JsonValue | None` to `int` after rejecting `bool`.
- Pyright: 0 errors, 0 warnings, 0 informations across all changed files.

### Test correctness

- `test_bool_index_tool_calls_stay_separate_by_id` covers SSE-path bool index rejection with id fallback for parallel tool calls.
- `test_aggregator_rejects_bool_index_and_falls_back_to_id` covers direct aggregator-level bool index rejection.
- 5 tests in `test_sse_tool_call_stream.py` pass (2 new + 3 existing).

## Non-Blocking Observations

### O1 [Info] `_is_tool_call_index` is not in `tool_call_aggregator.__all__`

- **File/line**: `tool_call_aggregator.py:48` (definition), `tool_call_aggregator.py:440-445` (`__all__`)
- **Evidence**: `_is_tool_call_index` is `_`-prefixed, defined in `tool_call_aggregator.py`, and NOT listed in that module's `__all__`. Yet `sse_parser.py:55` imports it by name. The function is private-by-convention but consumed cross-module within the same `dayu/engine/runners/openai/` package.
- **Impact**: No runtime issue. The `_` prefix signals "internal to the runner package", and both modules are co-located in the same private runner package. No circular import. The existing pattern in this package already uses `_`-prefixed imports across peer modules (e.g., `_OpenAIToolCallDelta` from `_types.py`).
- **Suggestion**: Either add `_is_tool_call_index` to `tool_call_aggregator.__all__` or move it to `_types.py` (which already serves as the shared internal types module). Low priority; does not block S2 acceptance.
- **Blocking**: No.

### O2 [Info] No WARN diagnostic on bool index rejection

- **Evidence**: The parser now silently treats bool index as invalid and falls through to id/position fallback without logging. This matches the existing behavior for other type-mismatched fields in `_coerce_tool_call_delta` (e.g., non-string `id` is silently ignored).
- **Impact**: A provider emitting bool index values would not produce observable diagnostics. However, this is consistent with the overall parser philosophy of silently ignoring non-conforming optional fields rather than emitting diagnostics for every type mismatch.
- **Blocking**: No. Acknowledged in fix artifact as intentional.

## Residual Risks

1. **`_is_tool_call_index` cross-module import without `__all__` entry** (O1 above) — maintenance clarity only; no correctness risk.
2. **Bool index rejection is silent** (O2 above) — consistent with existing parser behavior for type-mismatched optional fields; no operational risk.
3. **Original S2 residual risks remain unchanged** — non-negative range checks on token counts, no isolated `coerce_usage()` unit tests, finish reason parity matrix excludes `tool_calls`.

## Validation

| Command | Result |
|---|---|
| `pytest tests/engine/runners/openai/test_sse_tool_call_stream.py` | 5 passed |
| `python -m pyright dayu/engine/runners/openai/{_types,sse_parser,tool_call_aggregator,usage}.py` | 0 errors, 0 warnings |
| Grep `_OpenAIUsage` in `dayu/engine/` | 0 matches |
| Grep `isinstance.*int.*index\|isinstance.*index.*int` in changed files | 0 remaining bare-bool-accepting checks |

## Summary

| Finding | Status |
|---|---|
| F1 — dead `_OpenAIUsage` | **FIXED** |
| F2 — bool-as-int in `_coerce_tool_call_delta` | **FIXED** |
| F3 — bool-as-int in `_resolve_index` | **FIXED** |

- **Blocking findings**: 0
- **New blockers**: 0
- **Non-blocking observations**: 2 (O1/O2)
- **S2 accepted findings**: 3/3 fixed
