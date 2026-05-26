# Plan Review: Host Public Conversation Memory Smoke

- **Reviewer**: mimo
- **Plan artifact**: `docs/reviews/gateflow-plan-conversation-memory-smoke-20260526.md`
- **Source intent**: `/Users/leo/workspace/dayu-agent/docs/conversation_memory_test.md`
- **Reference**: `utils/smoke_host_public_multiturn.py`
- **Date**: 2026-05-26

---

## Summary

Plan is implementation-ready with 2 minor observations. No blocking findings. The plan correctly scopes to public-API-only boundaries, selects an appropriate scenario subset from the source intent doc, and produces a small, testable slice. The mock tool design is deterministic, the assertion strategy is well-stratified (hard vs soft), and the non-goals are honest about what the smoke does NOT prove.

---

## Findings

### F1: Round 4 hard assertion could false-pass on value co-occurrence [observation]

- **Status**: observation
- **Section**: §6 Round 4 hard assertions
- **Detail**: Round 4 asserts that normalized final answer contains `1.88%` and `-0.14pct`. The plan also requires the marker `DAYU_FINANCE_MEMORY_CMB_NIM_2024H1_V1` to be present. However, the assertion does not require the `DAYU_FINANCE_MEMORY_ASSERT` prefix line itself — only the marker and two values. If the model happens to restate the values in running text (e.g., "净息差为 1.88%，同比下降 0.14 个百分点") without the assertion line, the hard assertion still passes. This is acceptable because the marker co-occurrence with both values is strong enough evidence of memory continuity, and the plan explicitly prints the full assertion line status for human inspection.
- **Risk**: None. The three-field conjunction (marker + `1.88%` + `-0.14pct`) is sufficiently discriminating for a smoke test.

### F2: Mock tool schema fields vs. tool callable parameter handling [observation]

- **Status**: observation
- **Section**: §5 Mock Tool Design
- **Detail**: The plan specifies `company`, `period`, `topic`, `metric`, `include_pressure` as required schema fields with `additionalProperties=false`. The existing `SmokeFactTool` in `utils/smoke_host_public_multiturn.py` has a single `marker` field and ignores all call parameters (the `del call, context` pattern). The plan's `get_mock_finance_facts` tool will similarly ignore its schema parameters and return a fixed response — this is correct for determinism. However, the plan does not explicitly state that the tool callable should ignore all parameters. The implementation worker should ensure the callable ignores `company`/`period`/etc. and returns the fixed JSON, matching the existing smoke pattern.
- **Risk**: None. The plan's emphasis on "deterministic return values" makes intent clear.

---

## Checklist

| Criterion | Status | Notes |
|---|---|---|
| Motivation valid, not overclaiming | PASS | §1 honestly scopes to "mock tool accepted facts in multi-turn" only |
| Public API boundary enforced | PASS | §4 explicit allow/deny list matches `Host` protocol in `dayu/host/api.py` |
| Scenario selection appropriate | PASS | Test group D core + test group B subset; correctly excludes A/C/E |
| Mock tool deterministic | PASS | Fixed JSON return, constant marker, pressure blob |
| Hard assertions distinguishable | PASS | Round 4 three-field conjunction; Round 2 soft fallback is correct |
| Compaction pressure realistic | PASS | Reuses `_compact_pressure_padding` logic from existing smoke |
| Implementation slice small | PASS | One new script, one manifest, one scene prompt, README update |
| Chinese docstrings required | PASS | §8 explicitly requires |
| Strict typing, no Any/object | PASS | §8 explicitly requires |
| No magic strings/numbers | PASS | §8 requires constants centralization |
| README scope correct | PASS | §10 correctly identifies only root README needs update |
| Verification commands complete | PASS | §9 covers focused tests, pyright, manual smoke |

---

## Conclusion

No blocking findings. Plan is handoff-ready and code-generation-ready.
