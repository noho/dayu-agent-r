# R3-E Slice S3 Code Review Controller Adjudication

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01`
- Slice: `R3-E S3`
- Reviewed implementation artifact: `docs/reviews/wu-semantic-ownership-01-round3-r3-e-s3-implementation-codex.md`
- Controller validation artifact: `docs/reviews/wu-semantic-ownership-01-round3-r3-e-s3-controller-validation.md`
- Agent review artifacts:
  - `docs/reviews/wu-semantic-ownership-01-round3-r3-e-s3-code-review-mimo-20260713-162345.md`
  - `docs/reviews/wu-semantic-ownership-01-round3-r3-e-s3-code-review-ds.md`

## Controller Decision

S3 code review is not accepted yet. Controller accepts all evidence-backed findings below as one fix batch.

The accepted findings stay inside the S3 owner boundary: Web diagnostic projection, Web fetch result projection, diagnostic storage-state lifecycle, parent-owned smoke fixture ledger, and S3 tests. No S4 Documents, Host/Engine/Fins, egress-policy expansion, or tool-security implementation is authorized.

## Accepted Findings

### R3-E-S3-CR-F01: LLM-facing `final_url` bypasses safe URL projection

- Source: AgentMiMo finding 001.
- Severity: high.
- Owner: `dayu.tools.web.web_diagnostics` safe URL projection, consumed by `dayu.tools.web.web_tools` before returning LLM-facing tool payloads.
- Evidence:
  - `dayu/tools/web/web_tools.py:2380` returns `fetch_result.get("final_url", url)` directly.
  - `dayu/tools/web/web_fetch_orchestrator.py:1617,1689` returns raw `response.url`.
  - `dayu/tools/web/web_playwright_backend.py:1505,1520` returns raw `page.url`.
- Required fix:
  - Tool success payloads must expose only `project_safe_url_or_empty(raw_final_url)`.
  - Add tests proving userinfo, query tokens, and fragments are absent from returned `final_url`.

### R3-E-S3-CR-F02: `_raise_fetch_failure` accepts diagnostics it silently drops

- Source: AgentMiMo finding 002.
- Severity: medium.
- Owner: `dayu.tools.web.web_tools._raise_fetch_failure` failure diagnostic projection contract.
- Evidence:
  - `dayu/tools/web/web_tools.py:1179` accepts `internal_diagnostics`.
  - `dayu/tools/web/web_tools.py:1221` always passes `projection.to_json()` to `ToolBusinessError`.
  - Multiple call sites build `internal_diagnostics` that cannot affect the result.
- Required fix:
  - Remove the misleading parameter and call-site dictionaries, or replace it with an explicit owner-projected input if actually needed.
  - Do not merge arbitrary downstream dicts into diagnostics.

### R3-E-S3-CR-F03: storage-state publish can leave final after post-replace failure

- Source: AgentMiMo finding 003.
- Severity: medium.
- Owner: `utils.diagnose_web_access._StorageStateLifecycle`.
- Evidence:
  - `utils/diagnose_web_access.py:312-315` sets `published=True` only after `os.chmod(final_path, ...)`.
  - `cleanup_failure()` removes final only when `published` is true.
- Required fix:
  - Mark the final path as published immediately after `os.replace` succeeds.
  - Add a post-replace failure test that proves `cleanup_failure()` removes final.

### R3-E-S3-CR-F04: storage-state directory privacy helper lacks owner-contract tests

- Source: AgentMiMo finding 004.
- Severity: low.
- Owner: `utils.diagnose_web_access._ensure_private_storage_directory`.
- Evidence:
  - No tests reference `_ensure_private_storage_directory`.
- Required fix:
  - Add tests for newly created directory, valid existing private directory, invalid permissions, and non-directory path.

### R3-E-S3-CR-F05: `NEGATIVE_METHOD` is not part of smoke ledger gap contract

- Source: AgentMiMo finding 005.
- Severity: low.
- Owner: `utils.smoke_web_ci` parent-owned fixture ledger and negative-control contract.
- Evidence:
  - `utils/smoke_web_ci.py:1468-1487` sends only GET negative controls before child.
  - `utils/smoke_web_ci.py:2337-2342` omits `FixtureResponseKind.NEGATIVE_METHOD`.
- Required fix:
  - Exercise a HEAD negative control and require `NEGATIVE_METHOD` in `_fixture_ledger_gap`.
  - Add/adjust tests to prove the method negative control is required.

### R3-E-S3-CR-F06: private directory creation applies `0700` to intermediate parents

- Source: AgentMiMo finding 006.
- Severity: low.
- Owner: `utils.diagnose_web_access._ensure_private_storage_directory`.
- Evidence:
  - `utils/diagnose_web_access.py:2019` uses `path.mkdir(parents=True, mode=0o700)`.
- Required fix:
  - Create intermediate parents with ordinary default permissions, then create/chmod only the final storage-state directory to `0700`.
  - Add a nested path test proving intermediate parents are not forcibly set to `0700`.

### R3-E-S3-CR-F07: challenge-control reverse decision case lacks test coverage

- Source: AgentMiMo finding 007.
- Severity: low.
- Owner: `utils.smoke_web_ci._classify_loaded_artifact`.
- Evidence:
  - Current tests cover non-challenge marked confirmed, but do not cover challenge case with non-confirmed decision.
- Required fix:
  - Add a test proving a challenge-control case fails when `challenge_decision` is missing or not `confirmed`.

### R3-E-S3-CR-F08: post-replace cleanup path lacks direct test

- Source: AgentMiMo finding 008.
- Severity: low.
- Owner: `utils.diagnose_web_access._StorageStateLifecycle`.
- Evidence:
  - Current replace-failure test covers failure before final publication only.
- Required fix:
  - Covered together with F03 by the post-replace failure test.

### R3-E-S3-CR-F09: HEAD probe computes unused body diagnostic

- Source: AgentDS finding 1.
- Severity: low.
- Owner: `dayu.tools.web.web_fetch_orchestrator._probe_content_type`.
- Evidence:
  - `dayu/tools/web/web_fetch_orchestrator.py:1372` computes `response_content`.
  - Returned probe dict does not include the computed value, and no consumer reads it.
- Required fix:
  - Delete the unused computation. Do not add new probe response fields unless a consumer contract requires them.

## Rejected Findings

None. Low-severity accepted findings are included because they are evidence-backed, cheap to fix inside S3, and the current WU instruction is to fix all known findings before reporting.

## Required Verification

- Focused tests for modified S3 files:
  - `pytest tests/tools/web/test_web_tools_provider.py -q -k "diagnostic or fetch or final_url or failure"`
  - `pytest tests/tools/web/test_diagnose_web_access.py -q`
  - `pytest tests/tools/web/test_smoke_web_ci.py -q`
- Full Web tools test subset:
  - `pytest tests/tools/web -q`
- Type and hygiene:
  - `pyright`
  - `git diff --check`
- Scope scan:
  - Confirm no S4 Documents, Host/Engine/Fins, egress-policy expansion, or tool-security implementation changes were introduced.

