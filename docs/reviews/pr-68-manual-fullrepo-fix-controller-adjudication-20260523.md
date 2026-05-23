# PR 68 manual full-repo review repair controller adjudication

## Scope

- Review inputs:
  - `docs/reviews/repo-review-20260523-193249.md`
  - `docs/reviews/repo-review-20260523-193334.md`
- Fix artifact:
  - `docs/reviews/pr-68-manual-fullrepo-fix-codex-20260523.md`
- Re-review artifacts:
  - `docs/reviews/pr-68-manual-fullrepo-fix-rereview-mimo-20260523.md`
  - `docs/reviews/pr-68-manual-fullrepo-fix-rereview-ds-20260523.md`

## Controller Decision

Verdict: PASS.

The manual full-repo review repair closes the accepted PR 68 post-draft findings without introducing a blocking regression. Both independent re-review agents returned PASS.

## Accepted Findings

- Runtime digest malformed test setup: accepted because the existing test failed before reaching the intended digest normalization branch.
- Engine ingest stale Attempt events: accepted because Host durable context validation must reject EngineEvents that no longer belong to the Run current Attempt.
- OpenAI tool-call synthetic index collision: accepted because provider-native index and synthetic fallback index must not share a collision-prone keyspace.
- Service weak typing guard: accepted because Service is part of the typed composition boundary and must have the same weak-type regression guard as other layers.
- Service import boundary `dayu.config`: accepted because Service should consume runtime config loader outputs, not import the config package directly.
- Engine `"api key"` redaction marker: accepted because provider exception diagnostics must not leak secret-bearing API key messages.
- LLM compaction `token` / `secret` redaction: accepted because compactor failure summaries are diagnostic text and must use the same sensitive assignment coverage as surrounding compaction code.
- SSE all non-dict choices protocol error: accepted because a provider protocol anomaly must not be silently converted into an empty successful response.
- Service project path relative escape guard: accepted because workspace-relative deployment paths must not escape the workspace root through `..`.

## Deferred Findings

- durable / memory and durable / API import boundary cleanup: deferred to a Host durable layering cleanup work unit because it is a structural migration across row primitives, public type ownership and import tests.
- idempotency / EventLog TOCTOU and direct durable unit test expansion: deferred to durable hardening unless reproduced as an immediate PR 68 regression.
- helper consolidation, WAL checkpoint, watch polling, orphan recovery and PID liveness hardening: deferred to production hardening owners already tracked in `docs/host/implementation-control.md`.
- AgentPolicy merge layer simplification: deferred because it is a runtime assembly cleanup, not part of the P12.5 memory / compaction success signal.
- reactive compaction hard-threshold rejection: rejected for this repair gate because the current design intentionally relies on actual recovery dispatch plus `max_reactive_compactions_per_run` instead of an inaccurate token estimate guard.
- waiting digest fallback: deferred because changing fallback behavior would affect waiting state-machine semantics and requires a dedicated wait adapter / durable contract gate.

## Validation

Controller reran:

```bash
source .venv/bin/activate && pytest tests/runtime/test_tools_discovery_digest.py tests/host/test_engine_ingest_mapping.py tests/engine/runners/openai/test_sse_tool_call_index_fallback_to_id.py tests/engine/runners/openai/test_sse_tool_call_stream.py tests/engine/runners/openai/test_old_protocol_parity_regressions.py tests/engine/runners/openai/test_protocol_error.py tests/service/test_weak_typing_guard.py tests/service/test_import_boundary.py tests/service/test_host_assembly.py tests/engine/test_agent_phase2.py tests/host/test_llm_compaction.py
```

Result: 146 passed.

```bash
source .venv/bin/activate && pyright dayu tests
```

Result: 0 errors, 0 warnings, 0 informations.

```bash
git diff --check
```

Result: passed.

## Residual Risk

- `RunnerToolCallDeltaData.tool_call_index` can now be negative for synthetic fallback deltas. This is an internal correlation key; final `ToolCallRequest.index_in_iteration` remains non-negative and sequential.
- Old Attempt late events can now reject earlier as `stale_execution_id` instead of reaching later terminal-state rejection. This is the intended Host identity barrier behavior.
- Deferred durable layering and production hardening findings remain tracked under existing owners in `docs/host/implementation-control.md`.
