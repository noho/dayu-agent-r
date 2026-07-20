# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-E S3 controller validation

## Scope

- Gate: R3-E Slice S3 implementation controller validation.
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-round3-r3-e-s3-implementation-codex.md`.
- Slice objective: Web diagnostic projection, storage-state lifecycle, and independent smoke oracle.
- This validation does not close S4 Documents work, aggregate deepreview, PR gates, or final closeout.

## Changed files reviewed

- `dayu/tools/web/web_diagnostics.py`
- `dayu/tools/web/web_fetch_orchestrator.py`
- `dayu/tools/web/web_playwright_backend.py`
- `dayu/tools/web/web_tools.py`
- `utils/diagnose_web_access.py`
- `utils/smoke_web_ci.py`
- `tests/tools/web/test_web_tools_provider.py`
- `tests/tools/web/test_diagnose_web_access.py`
- `tests/tools/web/test_smoke_web_ci.py`
- `tests/README.md`
- `docs/reviews/wu-semantic-ownership-01-round3-r3-e-s3-implementation-codex.md`

No `dayu/tools/web/web_egress_policy.py`, S4 Documents, Host, Engine, Fins, or tool-security implementation file is in the current diff.

## Controller judgment

S3 implementation is ready for independent code review.

Direct inspection confirms the intended owner boundaries:

- `dayu.tools.web.web_diagnostics` owns schema v2 path projection, safe URL projection, content length/digest, response header presence projection, redacted error projection, and network-event projection.
- `utils/diagnose_web_access.py` owns diagnostic artifact assembly and storage-state lifecycle; it now requires schema v2/revision 2 and implements explicit opt-in storage-state output with owner-named atomic publish, permissions, TTL, failure cleanup, and startup reconciliation.
- `utils/smoke_web_ci.py` owns parent-side fixture registration, one-time sentinels, in-memory typed ledger, freeze-before-classify ordering, exact expected bytes, negative controls, and PASS classification. Artifact `ok` is no longer sufficient to pass a local case.
- `tests/README.md` was updated within its testing-maintainer scope only.

## Validation rerun

- `source .venv/bin/activate && pytest tests/tools/web/test_web_tools_provider.py -q -k "diagnostic or log or redaction"`
  - Result: `8 passed, 114 deselected`.
- `source .venv/bin/activate && pytest tests/tools/web/test_diagnose_web_access.py -q`
  - Result: `29 passed`.
- `source .venv/bin/activate && pytest tests/tools/web/test_smoke_web_ci.py -q`
  - Result: `37 passed, 3 warnings`.
- `source .venv/bin/activate && pytest tests/tools/web -q`
  - Result: `186 passed, 2 skipped, 3 warnings`.
- `source .venv/bin/activate && coverage erase && coverage run -m pytest tests/tools/web -q`
  - Result: `186 passed, 2 skipped, 3 warnings`.
- `source .venv/bin/activate && coverage report -m dayu/tools/web/web_diagnostics.py`
  - Result: `90%` coverage for `web_diagnostics.py`.
- `source .venv/bin/activate && pyright`
  - Result: `0 errors, 0 warnings, 0 informations`.
- `source .venv/bin/activate && git diff --check`
  - Result: pass.
- `source .venv/bin/activate && python utils/smoke_web_ci.py --output-dir workspace/tmp/r3e-s3-controller-smoke --include-playwright --external-limit 0 --run-label r3e-s3-controller`
  - Result: exit `0`; `SMOKE STATUS passed`; `SMOKE LOCAL_CASES 7`; `SMOKE FAILURES 0`; `SMOKE SKIPS 0`; `SMOKE DIAGNOSTIC_ONLY 4`.

## Coverage command note

The exact command required by the plan,

`source .venv/bin/activate && pytest tests/tools/web -q --cov=dayu.tools.web.web_diagnostics --cov-report=term-missing`,

fails during collection before running tests. Controller reproduced the same failure: pytest-cov imports the dotted source before collection, which triggers eager package imports and the local pandas/NumPy import chain then fails with `ImportError: cannot load module more than once per process`.

The same test set passes without dotted pre-import, and `coverage report -m dayu/tools/web/web_diagnostics.py` reports `90%`. This is recorded as validation tooling residual, not as a product/test failure, and no production import or package initializer was changed to work around it.

## Source scans

- `rg -n "response_excerpt|content_prefix|html_prefix|body_prefix|stdout_prefix|stderr_prefix|web-diagnostics-v1|schema_version.*v1|storage_state\\(path=" dayu/tools/web utils/diagnose_web_access.py utils/smoke_web_ci.py`
  - Only expected hit: `utils/smoke_web_ci.py` old-prefix denylist in `_legacy_diagnostic_field`, used to reject old schema fields.
- `rg -n "tool[-_ ]security|upload allowlist|SSRF|symlink-safe|security schema|file authority" ...`
  - Only expected hit: implementation artifact explicitly states tool-security was not implemented.
- Current diff scope confirms no S4 Documents, Host, Engine, Fins, or egress-policy expansion.

## Residual classification

- SIGKILL or host crash can leave owner temp files or unexpired final storage-state files until next opt-in startup reconciliation / TTL. Owner: `utils/diagnose_web_access.py`; accepted contract limitation.
- Content digest can be dictionary-guessed for low-entropy content and is used only for deterministic fixture/oracle correlation, not as a confidentiality guarantee. Owner: `web_diagnostics.py`; accepted limitation.
- Playwright diagnostic response body still depends on Playwright API body availability; implementation enforces budget before successful artifact/PASS. Owner: `utils/diagnose_web_access.py`; future streaming improvement only if upstream API allows.
- Dotted pytest-cov source import failure is a validation tooling residual, not a S3 owner behavior failure.
- External live URL/search provider cases remain diagnostic-only and do not participate in local hard PASS oracle.

## Decision

Controller validation: PASS for S3 code review entry.

Proceed to AgentMiMo and AgentDS S3 code review.
