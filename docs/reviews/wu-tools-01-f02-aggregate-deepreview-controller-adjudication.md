# WU-TOOLS-01-F02 Aggregate Deepreview Controller Adjudication

## Gate

- Work unit: `WU-TOOLS-01-F02`
- Current gate: aggregate deepreview adjudication
- MiMo aggregate artifact: `docs/reviews/wu-tools-01-f02-aggregate-deepreview-mimo.md`
- DS aggregate artifact: `docs/reviews/wu-tools-01-f02-aggregate-deepreview-ds.md`
- Decision date: 2026-06-09

## Overall Decision

Aggregate deepreview enters fix gate.

Both reviewers found no blocking issue and confirmed the final WU combination satisfies the F02 success signals and non-goals. Controller accepts one plan-alignment fix and one deterministic coverage hardening item. Remaining findings are rejected or deferred with owners.

## Finding Decisions

| Finding | Decision | Reason | Required action |
|---|---|---|---|
| DS F1: `--url` and `--url-file` can both be supplied, and `--url` is silently ignored. | accepted | The accepted plan explicitly requires clear failure when `--url` and `--url-file` are both present or both absent. Current `main()` only branches on `options.url_file`, so this is a direct plan-alignment defect. | Add an explicit mutual-exclusion validation with a business-readable error, and add a deterministic test. |
| MiMo F2: direct tests are missing for `_is_private_or_local_host`, `_redact_headers`, `_validate_url_safety`, and `_normalize_url_for_http`. | accepted | The implementation is correct, but these helpers protect the security/privacy boundary of an opt-in live diagnostics script. Adding focused deterministic tests improves CI value without changing production behavior or default live CI. | Add focused tests for URL normalization/safety and header redaction, including local/private hosts and IPv4-mapped IPv6 evidence. Do not add live network tests. |
| MiMo F1: requests+fetch success with Playwright un-sampled returns `partial_sample`. | rejected-with-reason | This is the correct conservative classification: an un-sampled Playwright path is not a failed path. The same reasoning was already applied to `requests_only_success`. | No code change. |
| MiMo F3: importing `detect_bot_challenge` from current Web challenge detection. | rejected-with-reason | This is a current `dayu.tools.web` diagnostic helper, not an OLD registry/truncation/UI dependency. It improves raw requests / Playwright challenge evidence and stays inside the utility boundary. | No code change. |
| MiMo F4/F5/F6: wrapper headed/manual-wait defaults, `all_success` before challenge, batch subprocess environment inheritance. | rejected-with-reason | All three are intentional behaviors already covered by the accepted plan or current utility semantics. | No code change. |
| DS F2: batch mode has no concurrency control. | deferred-with-owner | Serial execution is acceptable for a manual opt-in diagnostics utility and avoids adding scheduling complexity in F02. If F03 needs faster live diagnostics, it can define `--max-workers` or a separate runner policy. | Owner: WU-TOOLS-01-F03 or later maintenance. |
| DS F3 / residual IPv4-mapped IPv6 note. | accepted-for-test-only | `ipaddress.ip_address("::ffff:10.0.0.1")` already marks the address private, so no production fix is indicated. A deterministic test should lock that evidence. | Add test coverage only; do not change classifier or URL safety logic unless the test proves a real bug. |

## Required Validation

- `source .venv/bin/activate && pytest tests/tools/web/test_diagnose_web_access.py tests/tools/web/test_web_tools_provider.py -q`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
- `bash -n utils/diag_web.sh utils/diag_web_batch.sh`
- `git diff --check`
- precise forbidden import / wide-type scan for `utils/diagnose_web_access.py` and `tests/tools/web/test_diagnose_web_access.py`

## Residual Risk Routing

- F02 live network / real Playwright / storage-state environment behavior remains outside default CI and is routed to WU-TOOLS-01-F03 when it defines opt-in Web smoke evidence consumption.
- Diagnostic JSON schema consumption beyond the F02 minimum stable subset is routed to WU-TOOLS-01-F03 plan.
- Batch concurrency optimization is deferred to WU-TOOLS-01-F03 or later maintenance only if live diagnostics runtime becomes a practical bottleneck.
