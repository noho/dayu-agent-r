# Phase 12.3 Post-Push Pyright Fix Controller Adjudication - 2026-05-22

## Gate

Phase 12.3 post-push pyright blocker fix before Pull Request 67 post-push review.

## Input

- Fix artifact: `docs/reviews/phase12-3-post-push-pyright-fix-codex-20260522.md`
- MiMo review artifact: `docs/reviews/phase12-3-post-push-pyright-fix-mimo-20260522.md`
- DS review artifact: `docs/reviews/phase12-3-post-push-pyright-fix-review-ds-20260522.md`

## Finding

User-reported pyright failure:

```text
utils/smoke_host_public_multiturn.py:704:45 - error: Cannot access attribute "agent_policy_profile_id" for class "ServiceOpenHostAssemblyDiagnostics"
```

Root cause: Phase 12.3 intentionally removed the old `agent_policy_profile_id` schema and the matching `ServiceOpenHostAssemblyDiagnostics.agent_policy_profile_id` field, but the smoke diagnostics output still referenced the deleted field.

## Decision

Accepted fix.

The fix removes the stale smoke diagnostic reference without reintroducing the old schema, compatibility field, or Host public contract change. Agent policy diagnostics continue to be reported through the current `agent_policy_sources` output.

## Review Results

- MiMo verdict: PASS, blocking finding count = 0.
- DS verdict: PASS, blocking finding count = 0.

## Controller Validation

Controller reran:

```text
source .venv/bin/activate && python -m pyright utils/smoke_host_public_multiturn.py
source .venv/bin/activate && pytest tests/runtime/test_smoke_host_public_multiturn_assembly.py -q
git diff --check
```

Results:

- pyright: 0 errors, 0 warnings, 0 informations.
- focused smoke assembly tests: 4 passed.
- diff check: clean.

## Residual Risk

No residual blocker. Broader Phase 12.3 aggregate validation already passed before this narrow post-push fix; this gate only addressed the newly reported stale smoke diagnostics pyright blocker.
