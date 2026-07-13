# R3-E Aggregate Validation

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01`
- Round: `Round3 R3-E`
- Gate: aggregate validation after S1-S4 accepted slice commits
- Accepted commits:
  - S1: `a20efac7`
  - S2: `728e73af`
  - S3: `94a12c9e`
  - S4: `7e4749e5`

## Result

Aggregate validation passes. R3-E is ready for aggregate deepreview.

## Validation Commands

| Command | Result |
| --- | --- |
| `source .venv/bin/activate && pytest tests/tools/web tests/documents tests/tools/test_doc_tools_provider.py -q` | PASS: `280 passed, 2 skipped, 3 warnings` |
| `source .venv/bin/activate && pyright` | PASS: `0 errors, 0 warnings, 0 informations` |
| `git diff --check` | PASS |

The three warnings are existing upstream `edgar` deprecation warnings.

## Source Scans

- Legacy diagnostic field scan over Web/Doc current-scope sources found only expected `utils/smoke_web_ci.py` denylist entries for rejecting old schema fields:
  - `content_prefix`
  - `html_prefix`
  - `stderr_prefix`
  - `stdout_prefix`
- Tool-security / file-authority / SSRF / TLS / symlink-safe / generic capability scan found only:
  - R3-E plan/review artifacts stating exclusions or residual destinations.
  - Existing control-doc history.
  - `tests/documents/test_import_boundary.py` forbidden import list.
  - Existing unrelated Fins test forbidden-term tuple.

No current-scope production/test implementation of unrelated tool-security, Fins upload policy, file-authority, symlink-race policy, Host/Engine/Fins change, or aggregate code was detected.

## Accepted Residuals

| Residual | Owner / destination |
| --- | --- |
| Web `pytest-cov` dotted source / NumPy double-load tooling issue. | Validation tooling residual; equivalent coverage paths were used in S3/S4. |
| Web diagnostic digest is not a confidentiality guarantee for low-entropy content. | `dayu.tools.web.web_diagnostics`; accepted minimal-disclosure contract. |
| Playwright body streaming iterator is unavailable in current API. | `utils/diagnose_web_access.py`; bounded by current Content-Length early reject and post body budget checks. |
| Storage-state and bounded-source cleanup do not promise SIGKILL cleanup. | Respective lifecycle owners; future durable temp cleanup WU if required. |
| Doc processor object expansion beyond raw bytes remains possible. | Future processor-complexity budget WU. |
| Doc file-authority / symlink-race policy remains out of R3-E scope. | Future Doc tool file-authority WU; S4 caps bytes on the actually opened handle. |
| External live URL/search provider behavior remains diagnostic-only. | `utils/smoke_web_ci.py` external/search classifier. |

## Next Gate

Dispatch aggregate deepreview to AgentMiMo and AgentDS over the committed R3-E slice set and artifacts. If accepted findings are reported, return to aggregate fix gate; otherwise proceed to R3-E final closeout.

