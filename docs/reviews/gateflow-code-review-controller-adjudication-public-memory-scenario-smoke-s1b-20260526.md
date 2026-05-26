# Controller Adjudication: Host Public Conversation Memory Scenario Smoke S1b

- Gate: S1b code review / fix / re-review
- Work unit: Host public conversation memory scenario smoke
- Slice: S1b Host public flow integration
- Branch: `feat/phase-12-5-conversation-memory-optimize`
- Date: 2026-05-26

## Reviewed Artifacts

- Implementation artifact: `docs/reviews/gateflow-implementation-public-memory-scenario-smoke-s1b-codex-20260526.md`
- DS code review: `docs/reviews/gateflow-code-review-public-memory-scenario-smoke-s1b-ds-20260526.md`
- Fix artifact: `docs/reviews/gateflow-fix-public-memory-scenario-smoke-s1b-codex-20260526.md`
- DS re-review: `docs/reviews/gateflow-code-rereview-public-memory-scenario-smoke-s1b-ds-20260526.md`

## Controller Decisions

DS Finding 1 was accepted as blocking: `--suite all` generated long-suite `expected_tool_calls_after_round` values from a zero base even though core had already accumulated tool calls in the same session.

DS Finding 2 was accepted as a same-root fix item: `select_round_specs` contained independent ALL-mode selection semantics and would have preserved the same bug / confusion if left unchanged.

DS Finding 3 and Finding 4 are deferred:

- Finding 3 (`_compact_pressure_reserve_tokens` same return both branches): deferred to later cleanup or S3 tests if it becomes test-visible; current behavior is non-blocking and unchanged.
- Finding 4 (tiny context-window target edge): deferred to later pressure hardening; current production profiles have large context windows and downstream minimum prompt tokens already fail soft for this slice.

## Fix Status

Fix introduced `_round_specs_for_suite`, `_final_expected_tool_calls`, and `base_expected_calls` in `_long_round_specs`.

Final status after DS re-review:

- Finding 1: resolved.
- Finding 2: resolved.
- Finding 3: deferred, not worsened.
- Finding 4: deferred, not worsened.

## Validation

Controller re-ran:

```text
source .venv/bin/activate && python -m py_compile utils/smoke_host_public_conversation_memory_scenarios.py
source .venv/bin/activate && pyright utils/smoke_host_public_conversation_memory_scenarios.py
source .venv/bin/activate && python - <<'PY' ... pure spec assertions ... PY
rg private-read / weak-typing boundary checks
```

Results:

- `py_compile`: passed.
- `pyright`: 0 errors, 0 warnings, 0 informations.
- spec check: `SPEC_CHECK PASS core_final=4 long_first=1 all20_first_long=5 all25_first_long=5 long20_len=20 long25_len=25 long20_last=long-l25-constraint-assert`.
- boundary grep: only matched module docstring line documenting forbidden durable reads before fix; fix did not add private imports, sqlite/EventLog/memory reads, `Any`/`object` signatures, `getattr`, or `hasattr`.

## Gate Status

S1b accepted. No blocking finding remains. Ready for accepted slice commit.
