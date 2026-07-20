# WU-SEMANTIC-OWNERSHIP-01 P2-C implementation controller validation

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01`
- Sub WU: `P2-C`
- Gate: implementation controller validation before code review
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-p2-c-implementation-codex.md`
- Accepted plan commit: `256cda50`

## Motivation and owner boundary

The fix addresses the accepted MiMo 05 finding: Engine `AgentPolicy` and runtime execution profile config both defined LLM-facing fallback / continuation prompt defaults.

Owner boundary after implementation:

- Ordinary prompt defaults are produced by execution profile `agent_policy`.
- Compactor prompt defaults are produced by compactor scene required `agent_policy`.
- Runtime assembly merges already resolved baseline / override fields; its baseline naming no longer claims Engine or code prompt ownership.
- Host freezes and projects complete typed `AgentPolicy`.
- Engine validates complete typed values and appends already supplied prompt text; it no longer owns LLM-facing prompt defaults.

## Controller verification

Controller reran focused validation:

```text
source .venv/bin/activate && pytest tests/engine/test_agent_phase3_tool_call.py tests/engine/test_agent_phase2.py tests/engine/contracts/test_agent_run.py
110 passed
```

```text
source .venv/bin/activate && pytest tests/runtime/test_assembly_helpers.py tests/runtime/test_config_loader.py tests/service/test_host_assembly.py
124 passed, 3 existing edgar deprecation warnings
```

```text
source .venv/bin/activate && pyright
0 errors, 0 warnings, 0 informations
```

```text
git diff --check
pass
```

Controller scans:

```text
rg -n "_DEFAULT_FALLBACK_PROMPT|_DEFAULT_CONTINUATION_PROMPT" dayu/engine dayu/runtime tests
```

Result: no Engine contract prompt default remains. Remaining matches are in `dayu/runtime/config_loader.py`, which is the config-layer source of truth.

AST scan across `dayu/`, `tests/`, and `utils/` found no non-deliberate `AgentPolicy(...)` call missing `fallback_prompt` or `continuation_prompt`. The deliberate omissions are the new `pytest.raises(TypeError)` cases in `tests/engine/test_agent_phase3_tool_call.py`.

## Broad test classification

AgentCodex ran the requested broad suite:

```text
source .venv/bin/activate && pytest tests/engine tests/runtime tests/service/test_host_assembly.py tests/host
8 failed, 2584 passed, 1 skipped, 5 deselected
```

Controller reproduced the failed items in focused form. Classification:

- `tests/engine/test_package_exports.py::test_engine_all_matches_expected_set`: unrelated to P2-C diff; failure reports pre-existing extra exports `RunnerInputMessageProjection` and `RunnerInputToolCallProjection`.
- `tests/host/test_package_exports.py::test_host_all_matches_current_public_contracts`: unrelated to P2-C diff; failure reports pre-existing extra export `HostThinkingView`.
- `tests/host/test_package_exports.py::test_api_all_stays_request_snapshot_boundary`: unrelated to P2-C diff; failure reports pre-existing extra export `HostThinkingView`.
- `tests/engine/runners/openai/test_stream_idle.py::test_idle_heartbeat_emits_debug_log_and_does_not_drop_bytes`: unrelated to P2-C diff; no touched production file in this path.
- `tests/engine/test_engine_event_contract.py::test_iteration_started_runner_input_signal_fields_are_locked`: unrelated to P2-C diff; reports pre-existing `IterationStartedData.input_projection`.
- `tests/host/test_phase7_waiting_integration.py::test_local_awaiting_tool_manual_resolve_resumes_run`: test file only received explicit fixture prompt fields; the failing assertion concerns wait-resume guidance text, not AgentPolicy prompt defaults.
- `tests/host/test_purge_session.py::test_purge_session_durable_rejects_non_terminal_runs[cancelling]`: file is not touched by P2-C; failure is a durable CHECK constraint fixture issue.
- `tests/host/test_public_compact_smoke.py::test_post_compaction_fact_reuse_uses_raw_accepted_tool_evidence`: already recorded umbrella residual; owner boundary is accepted evidence compact material source projection, not P2-C.

Controller decision: the broad failures are not P2-C implementation blockers, but they remain umbrella residuals / current-branch validation risks and must not be forgotten before final umbrella closeout.

## README decision

- `dayu/engine/README.md` updated because Engine contract behavior changed.
- `dayu/config/README.md` checked by AgentCodex; no update needed because it already states execution profile `agent_policy` ownership.
- `tests/README.md` checked by AgentCodex; no update needed because no shared test fixture responsibility changed.

## Propagation audit

- Config source: `execution_profiles.json` / compactor scene provide prompt text.
- Runtime assembly: `AgentPolicyBaseline` / `base_policy` naming represents runtime merge baseline only, not Engine prompt default.
- Service assembly: continues to construct complete `AgentPolicy` with prompt fields.
- Host durable projection: `agent_policy_from_json(...)` already requires prompt fields.
- Engine: `AgentPolicy` requires explicit prompt fields and validates non-empty values.
- LLM-facing output: fallback / continuation user messages use the resolved prompt text from the typed policy.

## Controller decision

Ready for P2-C implementation code review.

Reviewers must specifically verify the broad failure classification above and confirm no P2-C-related failed test is being incorrectly deferred.
