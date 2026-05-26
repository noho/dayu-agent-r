# Code Review: Host Public Conversation Memory Smoke S1

- **Reviewer**: mimo
- **Review gate**: implementation code review (S1)
- **Reviewed artifact**: `docs/reviews/gateflow-implementation-conversation-memory-smoke-s1-20260526.md`
- **Approved plan commit**: `dbb9862`
- **Date**: 2026-05-26

---

## Verdict: PASS

No blocking findings. Implementation faithfully follows the approved plan and all controller/user corrections.

---

## Blocking Findings

None.

---

## Non-blocking Findings

### NB-1 — Dead branch in `_compact_pressure_reserve_tokens`

**File**: `utils/smoke_host_public_conversation_memory.py:1089-1099`

```python
def _compact_pressure_reserve_tokens(*, context_window_size: int) -> int:
    if context_window_size >= _COMPACT_PRESSURE_LARGE_WINDOW_TOKENS:
        return _COMPACT_PRESSURE_RESERVE_TOKENS
    return _COMPACT_PRESSURE_RESERVE_TOKENS
```

Both branches return `_COMPACT_PRESSURE_RESERVE_TOKENS` unconditionally. The parameter `context_window_size` is unused in effect. The reference implementation (`smoke_host_public_multiturn.py`) has the same pattern — it was likely copied verbatim. Either remove the dead branch or differentiate the values if large-window behavior should differ.

**Consequence**: None for correctness. Minor readability/maintainability concern.

---

### NB-2 — `_normalize_answer` allows partial numeric match

**File**: `utils/smoke_host_public_conversation_memory.py:1277-1286`

`_normalize_answer` strips all whitespace. The assertion `_normalize_answer(_FACT_NIM) not in normalized` checks substring containment. Since `_FACT_NIM = "1.88%"`, a model answer like "1.88%..." or "约1.88%" would match. This is intentional for smoke-level tolerance, but means the assertion cannot distinguish "1.88%" from "1.880%" or other suffixes. Not a risk for this smoke's design intent.

---

### NB-3 — `_mock_finance_fact_payload` return type is `Mapping[str, JsonValue]`

**File**: `utils/smoke_host_public_conversation_memory.py:723`

The return annotation `Mapping[str, JsonValue]` is technically correct (`JsonValue` includes `Mapping[str, JsonValue]`). A narrower `TypedDict` or concrete dict type would give stronger guarantees, but the current annotation matches the reference implementation style and is acceptable for a smoke utility.

---

## Review Priorities Checklist

### 1. Public API Boundary — PASS

All Host calls use only public handle methods:
- `open_host` (L405)
- `host.ensure_session` (L406)
- `host.submit_followup` (L827)
- `host.watch_session_events` (L408)
- `host.get_session` (L432, L449, L465, L482)
- `host.get_run` (L877, terminal failure summary only)

No imports of durable store, scheduler, command handle, EventLog reader, memory projection reader, or compact material builder. Assembly helpers (`ConfigLoader`, `resolve_runtime_locations`, `discover_service_tools`, `prepare_scene`, `compose_open_host_options`, `compose_submit_followup_request`) are correctly classified as pre-Host typed composition.

### 2. Anti-cheat — PASS

- **No context slot injection**: `context_slot_values={}` (L521). Manifest has `"context_slots": []` (manifest L49). Confirmed no `fins_default_subject` or `base_user` in new smoke script (grep returned zero matches).
- **No hidden scene context leak**: Scene prompt (`smoke_host_public_conversation_memory.md`) contains only execution contract rules ("优先回答用户当前财务问题", "不披露 smoke 运行过程"). No answer content, no company facts, no assertion line text.
- **Target company only in user prompts and assertions**: `_TARGET_COMPANY` appears in `_round1_prompt`, `_round2_prompt`, `_round3_prompt`, `_round4_prompt`, `_mock_finance_fact_payload`, and assertion helpers. Never in scene prompt or hidden context.
- **No `base_user`/`fins_default_subject` args**: `SmokeArgs` dataclass has no `fins_default_subject` or `base_user` fields, unlike the reference multiturn smoke.

### 3. Mock Tool and Assertions — PASS

- **Mock tool design**: `MockFinanceFactTool` follows `SmokeFactTool` callable pattern with `call_count`, `last_marker`, and typed `__call__`. Returns deterministic JSON with fixed facts.
- **Session-scoped counting**: `track_session(session_id)` (L241-250) ensures `call_count` only increments for the current smoke session, not recovery of stale runs. Correctly applied at L407 after `ensure_session`.
- **Tool recovery from effective bundle**: `_find_mock_finance_fact_tool(assembly.effective_tool_bundle)` (L543) uses `isinstance(definition.callable, MockFinanceFactTool)` — same pattern as reference `_find_smoke_tool`.
- **Round 1 hard assertions**: terminal SUCCEEDED, final answer non-empty, `call_count == 1`, `last_marker == _SMOKE_MARKER`. Optional assertion line check with `SMOKE OBSERVE` fallback.
- **Round 2 soft observation**: `_observe_round2_assertion` prints `soft-missing` if assertion line absent; does not fail. Hard assertion: `call_count` still 1.
- **Round 3 zero pass/fail weight**: Only asserts terminal SUCCEEDED, answer non-empty, `call_count` still 1. No content assertions on `npl_ratio` or other facts.
- **Round 4 hard assertions**: marker + `_FACT_NIM` + `_FACT_NIM_YOY` must all be present after normalization. `call_count` still 1.

### 4. Context Pressure and Compaction — PASS

- **Additive pressure**: Tool pressure (`_SMOKE_TOOL_PRESSURE_CHARS = 120_000`) + Round 2 prompt pressure are calibrated together against `context_budget_policy` soft/hard thresholds. `_compact_pressure_padding` (L1040-1074) correctly computes prompt padding as `target - reserve - tool_pressure`.
- **`include_pressure` behavior**: When `true`, `_tool_pressure_blob()` returns 120K chars; when `false`, returns `""`. Shape is always stable (field always present).
- **Pressure diagnostics**: `_print_compact_pressure_plan` prints context window, soft/hard thresholds, tool pressure chars, prompt pressure chars, estimated tokens. No full prompt or pressure payload is printed.
- **Failure messages**: `_terminal_failure_summary` prints desensitized error info (redacts API keys, truncates to 240 chars). `_assert_round4_answer` raises with specific missing-field message.

### 5. Manifest / Scene / README Consistency — PASS

- **Manifest** (`smoke_host_public_conversation_memory.json`): Correct `tool_selection` with `manual-smoke` tag, `allow_empty=false`. Empty `context_slots: []`. Model hint `mimo-v2.5-pro-plan` + `interactive`.
- **Scene prompt** (`smoke_host_public_conversation_memory.md`): Correct execution contract. No answer leak.
- **README** (`README.md` §5.2): Accurately describes four-round flow, mock tool, hard assertions, stdout markers. Command `python utils/smoke_host_public_conversation_memory.py --log-level VERBOSE` matches actual script entry point.

### 6. Project Rules — PASS

- **Chinese docstrings**: All functions, classes, and modules have Chinese docstrings with `:param:`, `:returns:`, `:raises:` annotations. Verified across all 30+ functions.
- **Strict typing**: No `Any`, `object`, untyped parameters, or untyped return values in new code. `JsonValue` is a defined union type, not `Any`. All `Final` constants are type-annotated.
- **No magic strings**: All smoke constants are module-level `Final` variables. Schema field name literals (`"company"`, `"period"`, etc.) are correctly exempt per plan §5.
- **No `hasattr`/`getattr`**: Zero occurrences in new code.
- **No lazy imports**: All imports are top-level.
- **No `fins_default_subject`/`base_user`**: Confirmed absent from new smoke.
- **Constants inventory**: All 20+ constants from plan §5 are present with correct naming and values.

---

## Tests/Validation Reviewed

- **Focused tests**: `pytest tests/runtime/test_scene_prepare.py tests/runtime/test_smoke_host_public_multiturn_assembly.py tests/service/test_host_assembly.py -q` → `58 passed in 0.79s`
- **Pyright**: `python -m pyright dayu/ tests/ utils/` → `0 errors, 0 warnings, 0 informations`
- **Manual smoke**: `python utils/smoke_host_public_conversation_memory.py --log-level VERBOSE` → PASS with expected stdout markers

---

## Residual Risks

1. **LLM format compliance**: Model may omit the `DAYU_FINANCE_MEMORY_ASSERT` line in Round 4. Mitigated by only asserting marker + two numeric values (not the full line format).
2. **Provider availability**: Smoke requires a working model API key and endpoint. Environment failures are distinct from code failures.
3. **Compaction timing**: Proactive/background compaction timing is not controlled by the script. Compaction artifact count is log-only, not a pass/fail signal.
4. **Dead branch in `_compact_pressure_reserve_tokens`**: Both branches return same value. Non-blocking — see NB-1.
