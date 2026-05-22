# Phase 12.3 Post-Push Pyright Fix Review - MiMo - 2026-05-22

## Gate

Phase 12.3 post-push pyright blocker fix review for PR 67.

## Verdict

**PASS**

## Scope

- Working tree diff after Codex fix.
- Files: `utils/smoke_host_public_multiturn.py`, `tests/runtime/test_smoke_host_public_multiturn_assembly.py`, `docs/reviews/phase12-3-post-push-pyright-fix-codex-20260522.md`.

## Findings

### [Correctness] pyright blocker fixed — no old schema reintroduction

**Severity**: none (verified clean)

The diff removes exactly one line from `utils/smoke_host_public_multiturn.py:703`:

```
-        f"agent_policy_profile:{diagnostics.agent_policy_profile_id},"
```

Verification:
- `grep agent_policy_profile_id dayu/` returns no hits — the old field is fully absent from production source.
- `tests/runtime/test_config_loader.py:594` still contains `test_old_agent_policy_profile_id_fails_fast`, which is a regression test asserting the old schema is rejected. This is correct and not stale.
- `python -m pyright utils/smoke_host_public_multiturn.py` → `0 errors, 0 warnings, 0 informations`.

No old field access, no old schema, no compatibility shim.

### [Test Adequacy] Focused regression test present

**Severity**: none (adequate)

New test `test_assembly_diagnostics_output_uses_current_agent_policy_sources` in `tests/runtime/test_smoke_host_public_multiturn_assembly.py:94`:
- Calls `_print_assembly_diagnostics` with a real assembly.
- Asserts `"agent_policy_profile" not in output` — catches any reintroduction of the stale label.
- Asserts `"SMOKE ASSEMBLY agent_policy_sources=" in output` — confirms the current diagnostics path is printed.

This test directly exercises the fixed code path and would fail if the stale attribute were reintroduced.

### [Boundary] No public contract change, no unrelated changes

**Severity**: none (clean)

- `ServiceOpenHostAssemblyDiagnostics` in `dayu/service/host_assembly.py` is untouched by this diff.
- The smoke script is in `utils/` (per project convention: no test/coverage requirement, but the new test is a net positive).
- No Host, Engine, or Service layer changes.
- `git diff --check` passes — no whitespace errors.

### [Docs/Artifact] Codex review artifact is accurate

**Severity**: none (verified)

`docs/reviews/phase12-3-post-push-pyright-fix-codex-20260522.md` correctly describes:
- Root cause: stale `diagnostics.agent_policy_profile_id` access after P12.3 Slice 1 schema removal.
- Changed files: smoke script (line removed) + test file (test added).
- Validation results match current run.
- Residual risk is honest: broader suite not re-run (acceptable for a focused blocker fix).

## Validation Summary

| Command | Result |
| --- | --- |
| `python -m pyright utils/smoke_host_public_multiturn.py` | 0 errors, 0 warnings, 0 informations |
| `pytest tests/runtime/test_smoke_host_public_multiturn_assembly.py -q` | 4 passed in 0.78s |
| `git diff --check` | clean |
| `grep agent_policy_profile_id dayu/` | no hits (old field absent from production source) |

## Residual Risk

None identified. The fix is minimal, targeted, and correctly removes the stale attribute access without masking the schema cleanup. The regression test adequately covers the fixed path.
