# WU-CM-15 Aggregate Fix

## Fixed Findings

- Finding 1: `_assert_reactive_compact_acceptance` now fails closed when a reactive suite audit observes any proactive compact activity. The guard rejects nonzero `requested_proactive`, `compacted_proactive`, or `failed_proactive` before accepting reactive recovery signals.
- Finding 2: `docs/host/issues-implementation-control.md` now uses `aggregate-review` in `blocking open questions`, matching the current gate.
- Finding 3: `_COMPACT_PRESSURE_RESERVE_TOKENS` now has a short intent comment. The real-provider `memory-compact --pressure-mode auto` startup path now asserts `prompt pressure + tool pressure + reserve` is at or above soft threshold and below hard threshold, with reserve, pressure, and threshold values in failure messages.
- Finding 4: `_assert_fallback_dispatch_acceptance` now checks `failed_events` before reading `failed_events[-1]` and raises a semantic `RuntimeError`.
- Finding 5: `_patched_compactor_runner` now converts a missing `dayu.host.llm_compaction._run_agent_request` hook into a semantic `RuntimeError` while keeping the existing `finally` restore behavior.
- Finding 8: WU-CM-15 `Implementation / Review 状态` now records the plan review chain: two initial plan reviews, plan adjudication, plan fix, and two focused plan re-reviews.

## Files Changed

- `utils/smoke_host_public_conversation_memory_scenarios.py`
- `tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py`
- `docs/host/issues-implementation-control.md`
- `docs/reviews/wu-cm-15-aggregate-fix-codex-20260620.md`

## Validation

- `source .venv/bin/activate && pytest tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py -q` passed: `20 passed`, with existing edgar deprecation warnings.
- `source .venv/bin/activate && DEEPSEEK_API_KEY=test-provider-key python utils/smoke_host_public_conversation_memory_scenarios.py --suite memory-reactive-compact --log-level CRITICAL` passed.
- `source .venv/bin/activate && DEEPSEEK_API_KEY=test-provider-key python utils/smoke_host_public_conversation_memory_scenarios.py --suite memory-compact-fallback --pressure-mode auto --log-level CRITICAL` passed.
- `source .venv/bin/activate && python -m pyright utils/smoke_host_public_conversation_memory_scenarios.py tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py` passed: `0 errors, 0 warnings, 0 informations`.
- `git diff --check` passed.

## Deferred Residuals

- Did not extract shared `run_smoke` / `_run_deterministic_compact_smoke` flow.
- Did not split the smoke script module.
- Did not modify Host, Engine, `dayu/` production code, public contracts, schemas, or compact semantics.
- Real-provider `memory-compact` still requires a valid compactor provider key; this remains an environment validation residual, not part of this deterministic fix gate.
