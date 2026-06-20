# WU-CM-15 Code Review Fix

## Gate

- Gate: code-review fix.
- Agent: AgentCodex.
- Scope: only accepted findings from `docs/reviews/wu-cm-15-code-review-adjudication-20260620.md`.
- No review, commit, push, PR, control-doc edit, or README edit was performed.

## 已修 Findings

1. Reactive compact acceptance now treats `_SMOKE_REACTIVE_OLD_MARKER` as the dropped old marker and asserts it is absent from the recovery dispatch.
   - `_deterministic_dropped_old_marker(SuiteMode.MEMORY_REACTIVE_COMPACT)` returns `_SMOKE_REACTIVE_OLD_MARKER`.
   - `_assert_reactive_compact_acceptance` fails closed when `dropped_old_marker` is missing.
   - `_assert_reactive_compact_acceptance` calls `_assert_marker_absent` on the recovery dispatch.
   - Focused tests cover both missing dropped marker and leaked old marker failure cases.

2. Removed unused `_compact_pressure_reserve_tokens`.
   - Tests now use `_COMPACT_PRESSURE_RESERVE_TOKENS` directly for the existing pressure-bound calculation.
   - Removed the now-unused large-window reserve constant.

3. Added `_patched_compactor_runner` sanity check.
   - After assignment, the context manager checks `llm_compaction._run_agent_request is runner`.
   - It raises a clear `RuntimeError` if patching does not take effect.
   - The original runner is still restored in `finally`.

Additional smoke-local adjustment:

- The deterministic accepting compactor sanitizes deterministic smoke markers before writing material text into fake compact proposals, preventing marker probes from being reintroduced through compacted semantic text.
- The reactive deterministic suite now has enough rounds to separate old history, intermediate history, protected recent material, and the overflow target.

## Controller Correction

- Controller local verification found that `reactive-r1-old-seed` no longer wrote `_SMOKE_REACTIVE_OLD_MARKER` into the old public Host history, so the recovery absent assertion could pass without a real old-marker premise.
- Correction: `reactive-r1-old-seed` now includes `_SMOKE_REACTIVE_OLD_MARKER` in its prompt, while `_assert_reactive_compact_acceptance` still requires the recovery dispatch to exclude that marker.
- Assembly coverage now explicitly asserts the first reactive spec prompt contains `_SMOKE_REACTIVE_OLD_MARKER`, preventing the dropped-old oracle from becoming vacuous again.
- Re-running the reactive smoke showed the old marker was then still rendered through selected recent memory, not through fake compact proposal text. The correction keeps this smoke-local: `memory-reactive-compact` now uses a bounded local memory projection policy so r2-r5 remain the protected recent window while r1 is old history represented only through accepted compact output.
- No Host production policy, fallback pressure decision, review, commit, push, PR, control doc, or README change was made.

## 修改文件

- `utils/smoke_host_public_conversation_memory_scenarios.py`
- `tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py`
- `docs/reviews/wu-cm-15-code-review-fix-codex-20260620.md`

## 验证结果

- `source .venv/bin/activate && pytest tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py -q`
  - Passed: `20 passed`.
  - Warnings: existing `edgar` deprecation warnings.
- `source .venv/bin/activate && DEEPSEEK_API_KEY=test-provider-key python utils/smoke_host_public_conversation_memory_scenarios.py --suite memory-reactive-compact --log-level CRITICAL`
  - Passed: observed reactive requested/compacted counts and `SMOKE PASS`.
- `source .venv/bin/activate && DEEPSEEK_API_KEY=test-provider-key python utils/smoke_host_public_conversation_memory_scenarios.py --suite memory-compact-fallback --pressure-mode auto --log-level CRITICAL`
  - Passed: observed proactive failure fallback dispatch and `SMOKE PASS`.
- `source .venv/bin/activate && python -m pyright utils/smoke_host_public_conversation_memory_scenarios.py tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py`
  - Passed: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`
  - Passed.

## 残余风险

- Existing real-provider `memory-compact` smoke remains outside this fix gate and still depends on a valid compactor provider key.
- Runtime monkey-patching of `dayu.host.llm_compaction._run_agent_request` remains a smoke-local maintenance tradeoff; this fix only adds a fail-fast identity check.
- Reactive public smoke verifies the recovery dispatch oracle and helper failure cases, but it does not change production Host raw-tail selection behavior.
