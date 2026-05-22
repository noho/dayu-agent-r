# Phase 12.3 Post-Push Pyright Fix - Codex - 2026-05-22

## Scope

- Gate: Phase 12.3 post-push pyright blocker before PR post-push review.
- Role: implementation/fix worker.
- Branch: `docs/phase12-design-discussion`.
- Fix scope: remove the stale smoke diagnostics reference to deleted `ServiceOpenHostAssemblyDiagnostics.agent_policy_profile_id`.
- Non-goals: no public contract change, no old `agent_policy_profile_id` schema reintroduction, no commit, no push, no PR, no next gate.

## Root Cause

P12.3 Slice 1 intentionally removed the old `agent_policy_profile_id` schema and the matching `ServiceOpenHostAssemblyDiagnostics.agent_policy_profile_id` field. `utils/smoke_host_public_multiturn.py` still printed `diagnostics.agent_policy_profile_id` in the assembly diagnostics `policy_refs` line, so pyright correctly rejected the stale attribute access.

## Changed Files

- `utils/smoke_host_public_multiturn.py`
  - Removed `agent_policy_profile:{diagnostics.agent_policy_profile_id}` from the `SMOKE ASSEMBLY policy_refs=` output.
  - Kept current `SMOKE ASSEMBLY agent_policy_sources=` output as the source of Agent policy diagnostics.
- `tests/runtime/test_smoke_host_public_multiturn_assembly.py`
  - Added focused coverage for `_print_assembly_diagnostics` to assert the output no longer mentions `agent_policy_profile` and still prints `agent_policy_sources`.

## Validation

| Command | Result |
| --- | --- |
| `source .venv/bin/activate && python -m pyright utils/smoke_host_public_multiturn.py` | `0 errors, 0 warnings, 0 informations` |
| `source .venv/bin/activate && pytest tests/runtime/test_smoke_host_public_multiturn_assembly.py -q` | `4 passed in 0.80s` |
| `git diff --check` | passed, no output |

## README Decision

No README update. The existing root README describes the smoke script as printing generic `policy refs`; after this fix the smoke still prints policy refs plus the already-existing `agent_policy_sources` diagnostics. No command, argument, entrypoint, or stable user workflow changed.

## Residual Risk

- Not run: broader Phase 12.3 post-push review or full repository pyright/test suite. This fix was intentionally limited to the reported blocker and the focused smoke assembly coverage.
- No known residual risk in the touched smoke diagnostics path.
