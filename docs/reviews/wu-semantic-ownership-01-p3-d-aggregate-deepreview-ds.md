# P3-D Aggregate Deepreview

## Scope

- Mode: aggregate deepreview (post-accepted slices S1/S2/S3)
- Branch: phaseflow/host-issues-control
- Base: c52519f0 (accepted P3-D plan)
- Output file: docs/reviews/wu-semantic-ownership-01-p3-d-aggregate-deepreview-ds.md
- Included scope:
  - Production code: `dayu/engine/contracts/error_codes.py`, `dayu/engine/contracts/runner_events.py`, `dayu/engine/contracts/engine_events.py`, `dayu/engine/contracts/agent_run.py`, `dayu/engine/contracts/__init__.py`, `dayu/engine/__init__.py`, `dayu/engine/agent.py`, `dayu/engine/runners/openai/_choice_policy.py`, `dayu/engine/runners/openai/sse_parser.py`, `dayu/engine/runners/openai/non_stream_parser.py`, `dayu/engine/runners/openai/runner.py`, `dayu/engine/runners/openai/tool_call_aggregator.py`, `dayu/engine/runners/openai/error_classifier.py`, `dayu/host/engine_ingest.py`, `dayu/host/read_api.py`, `dayu/host/tool_trace.py`, `dayu/host/api.py`, `dayu/service/entrypoint_runtime.py`
  - Tests: all P3-D test files listed in plan testing matrices
  - Docs: `dayu/engine/README.md`, `dayu/host/README.md`, `tests/README.md`, `docs/engine/design.md`, `docs/host/design.md`
  - Review/control artifacts: all S1/S2/S3 review, fix, re-review, and controller adjudication artifacts
- Excluded scope: unrelated untracked files (`docs/cli_ci.md`, `docs/cli_ci_oracles.json`, `docs/cli_ci_scenarios.json`, `docs/reviews/code-review-20260710-*.md`)
- Parallel review coverage:
  - Subagent A: S1 review artifacts (all 10 files)
  - Subagent B: S2 review artifacts (all 10 files)
  - Subagent C: S3 review artifacts (all 10 files)
  - Subagent D: Core production files (all 11 files)
  - Main reviewer: cross-slice consistency, propagation audit, Host boundary checks, test/pyright/coverage validation

## Findings

未发现实质性问题。

## Cross-Slice Consistency Audit

### 1. S1 finish_reason/choice fail-closed → S2 provider diagnostic → S3 typed error-code

**S1 — Adapter choice and finish-reason policy:**
- `_choice_policy.py`: All `ChoicePolicyError` results are fatal. SSE validates before state merge; non-stream validates before `choices[0]` selection. Unknown/illegal `finish_reason` → fatal (not `STOP` fallback).
- **Confirmed intact after S2/S3**: No S2 or S3 change reintroduced `STOP` fallback. Source scan (`rg "unknown_finish_reason|finish_reason or FinishReason\.STOP"`) returns zero hits outside tests and the `_FINISH_REASON_MAP` in `_choice_policy.py` (which is the single source of truth).

**S2 — Provider diagnostic non-fatal path:**
- `RunnerProviderDiagnosticData` / `ProviderDiagnosticData`: Non-fatal warnings (unknown tool-call namespace/key, malformed usage, missing Content-Type, context-overflow marker fallback) go through `PROVIDER_DIAGNOSTIC` → `EventClass.DIAGNOSTIC` without setting Agent `failure_candidate`.
- `RunnerProtocolErrorData` / `ProviderProtocolErrorData`: Remain fatal, set `failure_candidate`.
- **Confirmed against S1**: No S2 change reclassified S1 fatal choices/finish_reason failures as non-fatal diagnostics. The `ChoicePolicyError` path still wraps via `runner_protocol_error_code()` into `RunnerProtocolErrorData`, which sets `failure_candidate`.
- **Confirmed against S3**: S3 typed the `error_code` field in `RunnerProtocolErrorData` (to `RunnerSpecificErrorCode`) and `ProviderProtocolErrorData` (to `EngineErrorCode` union). The S2 split between fatal `PROVIDER_PROTOCOL_ERROR` and non-fatal `PROVIDER_DIAGNOSTIC` remained intact; no S3 change collapsed them.

**S3 — Typed error-code contract:**
- `EngineRunErrorCode` (18-member StrEnum) for Engine-owned failures; `RunnerSpecificErrorCode` (str subclass with `source` discriminator) for provider/adapter-specific codes.
- `RunFailedData.error_code: EngineErrorCode`, `ProviderProtocolErrorData.error_code: EngineErrorCode`, `RunnerProtocolErrorData.error_code: RunnerSpecificErrorCode`, `EngineRunOutcomeFailed.error_code: EngineErrorCode`.
- `__post_init__` validation guards in all four dataclasses (via `validate_engine_error_code` / `validate_runner_specific_error_code`).
- **Confirmed against S1/S2**: Agent's `_ERROR_*` string constants are now all `EngineRunErrorCode` enum members. `adapter_error_code()` wraps previously bare-string HTTP error codes. No old `error_code: str` remains in Engine contract dataclasses (verified: `rg "error_code: str" dayu/engine/contracts/` returns zero hits).

### 2. Provider wire facts normalized at Runner adapter boundary

**Propagation chain verified:**

```text
provider wire response
  → OpenAI adapter (_choice_policy.py, sse_parser.py, non_stream_parser.py)
  → RunnerEvent (typed: RunnerProtocolErrorData, RunnerProviderDiagnosticData, etc.)
  → Agent._consume_runner_event() → EngineEvent (typed: ProviderProtocolErrorData, ProviderDiagnosticData, RunFailedData)
  → Host EngineEvent ingest → EventLog (durable: serialized error_code, diagnostic_code)
  → read_api.py / tool_trace.py / outbox.py (consume durable strings only)
```

**Confirmed**: No Agent or Host code infers provider semantics from raw strings. All `finish_reason` resolution happens in `_choice_policy.py._resolve_finish_reason()`. All error code construction happens via typed constructors (`runner_protocol_error_code()`, `http_provider_error_code()`, `adapter_error_code()`, `EngineRunErrorCode` enum members).

### 3. Fatal/non-fatal distinction through all layers

| Layer | Fatal protocol error | Non-fatal diagnostic |
|---|---|---|
| Runner adapter | `RunnerProtocolErrorData` + `RunnerDoneData(ERROR)` | `RunnerProviderDiagnosticData` (stream continues) |
| Agent | Sets `failure_candidate` → later `RunFailedData` | `_provider_diagnostic_event()` → `ProviderDiagnosticData`; no `failure_candidate` |
| Host EventLog | `PROVIDER_PROTOCOL_ERROR` + `failure_metadata` (with `provider_error_code`) | `PROVIDER_DIAGNOSTIC` (no `failure_metadata`) |
| Read API | `HostActivityKind.PROVIDER_PROTOCOL_ERROR` / `HostActivityStatus.FAILED` | `HostActivityKind.PROVIDER_DIAGNOSTIC` / `HostActivityStatus.INFO` |
| Tool Trace | `provider_error_ref` set; `failure_kind = "provider_protocol_error"` | `provider_error_ref = None` |
| Outbox | Not emitted (EventClass.DIAGNOSTIC is filtered) | Not emitted (EventClass.DIAGNOSTIC is filtered) |
| Memory/evidence/compact/LLM | Not consumed | Not consumed (LLM-facing leakage scan clean) |

### 4. Engine typed error-code union leakage check

**`serialize_engine_error_code` call sites (all correct):**
- `engine_ingest.py:1030` — `RUN_FAILED` terminal closeout: `serialize_engine_error_code(event.data.error_code)` ✓
- `engine_ingest.py:3280` — `PROVIDER_PROTOCOL_ERROR` payload: `serialize_engine_error_code(data.error_code)` ✓
- `engine_ingest.py:3309` — `PROVIDER_PROTOCOL_ERROR` reason: `serialize_engine_error_code(data.error_code)` ✓
- `engine_ingest.py:5015` — `_run_failed_plan`: `serialize_engine_error_code(data.error_code)` ✓
- `engine_ingest.py:6935` — `_provider_protocol_failure_metadata`: `serialize_engine_error_code(data.error_code)` ✓
- `agent.py:378` — `_fallback_error_message`: `serialize_engine_error_code(error_code)` ✓

**No wrapper leakage**: Host consumers (`read_api.py`, `tool_trace.py`, `outbox.py`) only access serialized strings from durable payloads. No Host module imports `EngineRunErrorCode`, `RunnerSpecificErrorCode`, or `RunnerSpecificErrorSource` (only `engine_ingest.py` imports `serialize_engine_error_code` at the ingest boundary, as designed).

**One Host-owned bare string noted**: `engine_ingest.py:2025` passes `error_code="context_compaction_failed"` to `_fail_recovering_run()`. This is a Host-owned recovery failure code for Host's own compaction failure path, not an Engine error code. The `_fail_recovering_run` function signature takes `error_code: str` because it writes directly to Host durable storage. This is semantically correct — Host owns compaction policy and its failure codes.

### 5. Weak-typing guard

**`tests/engine/test_weak_typing_guard.py`** (8 tests, all passing):
- `test_error_code_str_not_in_engine_contracts` — scans `dayu/engine/contracts/` for `error_code: str` → zero hits ✓
- `test_run_failed_data_no_literal_string_error_code` — scans `dayu/engine/agent.py` for `RunFailedData(error_code="..."` → zero hits ✓
- `test_engine_run_outcome_failed_no_literal_string_error_code` — scans `dayu/engine/agent.py` for `EngineRunOutcomeFailed(error_code="..."` → zero hits ✓
- `test_provider_protocol_error_data_no_literal_string_error_code` — scans `dayu/engine/agent.py` for `ProviderProtocolErrorData(error_code="..."` → zero hits ✓
- `test_host_consumers_use_serialize — engine_ingest.py` always calls `serialize_engine_error_code` before writing error_code to durable ✓
- `test_runner_protocol_error_data_no_literal_string_error_code` — scans runner adapter files ✓
- `test_agent_tests_do_not_compare_typed_error_codes_to_literal_strings` — AST-level scan of `tests/engine/test_agent_phase2.py` ✓
- Additional guard for `RunnerProtocolErrorData` construction sites ✓

**Guard scope limitation**: The direct-comparison guard (`test_agent_tests_do_not_compare_typed_error_codes_to_literal_strings`) only scans `tests/engine/test_agent_phase2.py`. Other Engine test files currently have no such pattern (verified), but if future tests introduce them, the guard won't catch them.

### 6. Public exports, docs, tests, pyright, coverage, LLM-facing leakage

**Public exports** (`dayu/engine/__init__.py`):
- `EngineRunErrorCode`, `RunnerSpecificErrorCode`, `RunnerSpecificErrorSource`, `EngineErrorCode`, `serialize_engine_error_code`, `adapter_error_code`, `http_provider_error_code`, `runner_protocol_error_code`, `ProviderDiagnosticData`, `RunnerProviderDiagnosticData`, `RunnerDiagnosticSeverity`, `RunnerDiagnosticSource`, `ContextOverflowDetection`, `ContextOverflowDetectionKind` — all exported ✓

**Docs/README**:
- `dayu/engine/README.md`: Updated for typed error codes, finish-reason fail-closed, provider diagnostics, context-overflow provenance ✓
- `docs/engine/design.md`: Updated RunnerEvent/EngineEvent tables, Provider error section, context overflow section ✓
- `docs/host/design.md`: Updated EngineEvent ingest diagnostic matrix ✓

**Tests**: 428 Engine tests passing (contracts + agent_phase2 + runner/openai + weak_typing_guard + package_exports). 155 Host projection tests passing (engine_ingest_mapping + tool_trace_projection + host_activity_event_projection + outbox_projection).

**Pyright**: 0 errors, 0 warnings, 0 informations ✓

**Coverage**: Per-slice controller validations confirmed all touched production files at ≥80% single-file coverage (S1: `_choice_policy.py` 95%, `sse_parser.py` 86%, `non_stream_parser.py` 89%; S2: `agent.py` 89%, `runner.py` 82%; S3: `error_codes.py` 100%, all other touched files ≥80%).

**LLM-facing leakage**: Source scan (`rg "PROVIDER_DIAGNOSTIC|message_marker_fallback|provider diagnostic|provider_diagnostic" dayu/config dayu/host dayu/engine`) returned zero hits in config/prompts or LLM-facing content. Provider diagnostic text, raw_payload, and diagnostic payload refs do not enter memory, final answer, evidence, compact, or prompt assembly paths.

## Open Questions

1. **`engine_ingest.py` at 7146 lines**: The Host ingest module handles event routing, terminal closeout, reactive compaction, runner call manifest management, wait confirmation, and rejected diagnostics in a single file. This violates single-responsibility principle but is pre-existing and not introduced by P3-D. Future refactoring should consider splitting into focused modules.

2. **`_FAILURE_METADATA_ALLOWED_KINDS` in `tool_trace.py`**: The tool trace validates `failure_kind` against a closed set. If a new failure kind is added (e.g., in a future Host recovery path), `tool_trace.py` must be updated in sync with `engine_ingest.py`. This three-file coupling (`engine_ingest.py`, `tool_trace.py`, `read_api.py`) for field names and failure kinds is a maintenance risk but is outside P3-D scope.

3. **`USAGE_REPORTED` classification**: `USAGE_REPORTED` uses `EventClass.PROJECTION_SIGNAL` while `PROVIDER_DIAGNOSTIC` uses `EventClass.DIAGNOSTIC`. The distinction is by design (usage is a projection signal for observability; provider diagnostics are diagnostic events), but the classification boundary between these two `EventClass` values may need to be revisited if new event types are added in future phases.

## Residual Risk

1. **`RunnerSpecificErrorCode` inherits `str`**: This enables `str.__eq__` to succeed when comparing a typed wrapper to a bare string, meaning type degradation in production code would not be caught by equality checks. The S3 fix addressed this in tests (AST-based guard + typed assertion helpers), and `__post_init__` validation guards in all four dataclasses provide runtime protection. Risk: Low.

2. **Weak-typing guard scope limited to `test_agent_phase2.py`**: If future Engine tests in other files introduce `.error_code == "..."` patterns, the AST guard won't catch them. Current scan confirms no such patterns exist in other test files. Risk: Low — expand guard scope when new test files are added.

3. **`adapter_error_code()` collapses HTTP error type distinction**: `RunnerHTTPErrorCode` types (TIMEOUT, NETWORK_ERROR, RATE_LIMIT_EXCEEDED, etc.) are all converted to `RunnerSpecificErrorCode(source=ADAPTER)` at `agent.py:1500`. The original HTTP error type is preserved in the `RunnerHTTPErrorData` event that was previously emitted, but the `RunFailedData.error_code` carries only the serialized string value. If Host consumers need to distinguish between HTTP error types for recovery policy, they must read the `runner_http_error` diagnostic event, not just the terminal `error_code`. This is by design per the plan but limits what Host can infer from the terminal error code alone. Risk: Low.

4. **Host-owned `context_compaction_failed` is bare string**: `engine_ingest.py:2025` uses `error_code="context_compaction_failed"` for Host recovery failures. This is semantically correct (Host owns its compaction policy failures), but the error code is not unified with the Engine error code system. If Host-owned error codes proliferate, consider a Host-owned error code enum with the same serialization contract. Risk: Low.

5. **No round-trip serialization test**: There is no test that constructs a typed `EngineErrorCode`, serializes it via `serialize_engine_error_code()`, writes it to durable storage, reads it back as a plain string, and verifies the value is preserved. The durable store is string-based by design, so a round-trip test would only verify that `serialize_engine_error_code` produces the expected string — which is already covered by existing tests. The loss of `RunnerSpecificErrorSource` on deserialization is by design. Risk: Low.

6. **`engine_ingest.py` extreme file length (7146 lines)**: Pre-existing architectural risk. P3-D added provider diagnostic and typed error code serialization paths without increasing structural complexity. Not introduced or worsened by P3-D. Risk: Medium (pre-existing, not P3-D scope).

---

P3-D aggregate deepreview complete.
