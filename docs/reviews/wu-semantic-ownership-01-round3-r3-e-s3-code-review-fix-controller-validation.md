# R3-E Slice S3 Code Review Fix Controller Validation

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01`
- Slice: `R3-E S3`
- Gate: controller validation after accepted code-review fix
- Fix artifact: `docs/reviews/wu-semantic-ownership-01-round3-r3-e-s3-code-review-fix-codex.md`
- Controller adjudication: `docs/reviews/wu-semantic-ownership-01-round3-r3-e-s3-code-review-controller-adjudication.md`

## Result

Controller validation passes. `R3-E-S3-CR-F01` through `R3-E-S3-CR-F09` have direct implementation and test evidence. S3 remains ready for code re-review.

No S4 Documents, Host/Engine/Fins, `dayu/tools/web/web_egress_policy.py`, egress-policy expansion, or tool-security implementation was added in this fix.

## Validation Commands

| Command | Result |
| --- | --- |
| `source .venv/bin/activate && pytest tests/tools/web/test_web_tools_provider.py -q -k "diagnostic or fetch or final_url or failure"` | PASS: `32 passed, 92 deselected` |
| `source .venv/bin/activate && pytest tests/tools/web/test_diagnose_web_access.py -q` | PASS: `35 passed` |
| `source .venv/bin/activate && pytest tests/tools/web/test_smoke_web_ci.py -q` | PASS: `40 passed, 3 warnings` |
| `source .venv/bin/activate && pytest tests/tools/web -q` | PASS: `197 passed, 2 skipped, 3 warnings` |
| `source .venv/bin/activate && pyright` | PASS: `0 errors, 0 warnings, 0 informations` |
| `git diff --check` | PASS |

The three warnings are existing `edgar` deprecation warnings from installed dependencies.

## Finding Closure Check

| Finding | Controller validation |
| --- | --- |
| `R3-E-S3-CR-F01` | PASS. Requests and Playwright LLM-facing success payloads safe-project `final_url`; tests cover userinfo/query-token/fragment removal. |
| `R3-E-S3-CR-F02` | PASS. `_raise_fetch_failure` no longer accepts caller-owned arbitrary `internal_diagnostics`; failure diagnostics come from `failed_projection().to_json()`. |
| `R3-E-S3-CR-F03` | PASS. `published=True` is set immediately after `os.replace`; post-replace chmod failure test proves `cleanup_failure()` removes final. |
| `R3-E-S3-CR-F04` | PASS. Private storage directory contract has tests for create, valid existing, invalid mode, and non-directory path. |
| `R3-E-S3-CR-F05` | PASS. HEAD negative control is exercised and `NEGATIVE_METHOD` is required by ledger gap validation. |
| `R3-E-S3-CR-F06` | PASS. Intermediate parents use normal mkdir semantics; only the leaf storage directory is forced to `0700`, with nested path test coverage. |
| `R3-E-S3-CR-F07` | PASS. Challenge-control cases with missing, `none`, or `suspected` decision fail as `challenge_control_failed`. |
| `R3-E-S3-CR-F08` | PASS. Covered by the post-replace failure cleanup test. |
| `R3-E-S3-CR-F09` | PASS. HEAD probe no longer computes unused body diagnostics. |

## Scope And Tool-Security Scan

`git diff --name-only` is limited to S3 implementation files, S3 tests, `tests/README.md`, and S3 artifacts:

- `dayu/tools/web/web_fetch_orchestrator.py`
- `dayu/tools/web/web_playwright_backend.py`
- `dayu/tools/web/web_tools.py`
- `dayu/tools/web/web_diagnostics.py`
- `utils/diagnose_web_access.py`
- `utils/smoke_web_ci.py`
- `tests/tools/web/test_web_tools_provider.py`
- `tests/tools/web/test_diagnose_web_access.py`
- `tests/tools/web/test_smoke_web_ci.py`
- `tests/README.md`
- S3 review / validation artifacts under `docs/reviews/`

The scan for `tool-security`, upload allowlist, SSRF, TLS policy, symlink-safe upload, file authority, and security schema terms found only:

- Existing control-doc historical rows.
- S3 artifacts explicitly saying those items were not implemented or were excluded.
- Existing unrelated test text outside the S3 diff.

There is no new tool-security code in the current S3 diff.

## Next Gate

Dispatch R3-E S3 code re-review to AgentMiMo and AgentDS. If both pass with no accepted findings, controller can accept and commit S3. If either reports evidence-backed findings, return to fix gate.

