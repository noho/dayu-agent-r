# WU-TOOLS-01-F03 Plan Review Controller Adjudication

## Scope

- Work unit: `WU-TOOLS-01-F03 Web CI Smoke Generation`
- Gate: plan review adjudication
- Plan artifact: `docs/host/wu-tools-01-f03-web-ci-smoke-plan.md`
- Review artifacts:
  - `docs/reviews/wu-tools-01-f03-plan-review-mimo.md`
  - `docs/reviews/wu-tools-01-f03-plan-review-ds.md`
- Date: 2026-06-10

## Decision Summary

Plan review result: `pass-with-fixes`.

The plan is directionally accepted, but it must be amended before implementation. The core issue is the Docling PDF route evidence: F03 must prove that current `fetch_web_page` actually invokes the Docling conversion path for a local PDF fixture. Code-route inference alone is not enough for the user's stated requirement.

The accepted fix direction is diagnostics-side instrumentation, not production tool schema expansion. `utils/diagnose_web_access.py` may wrap the current Web module's Docling conversion function during a diagnostic run, call the original implementation, and record diagnostic-only invocation evidence in the diagnostic artifact. This keeps F02 diagnostics as the evidence source, avoids duplicating route logic in the smoke wrapper, and does not expose `extraction_source` or implementation labels in the production `fetch_web_page` result consumed by an LLM.

## Finding Adjudication

| Finding | Source | Decision | Required plan amendment |
|---|---|---|---|
| PDF Docling route evidence has no runtime data source | MiMo F-1 / DS F-1 | accepted | Add diagnostics-side instrumentation around the current Docling conversion callable. PDF pass requires recorded invocation evidence, not only content-type plus success. Do not add implementation-only fields to production LLM-facing tool output unless a later user-approved production contract change explicitly allows it. |
| Playwright skipped plus requests and fetch success falls into `partial_sample` | MiMo F-2 | accepted | Plan must define either a new diagnostics bucket such as requests-and-fetch success with Playwright skipped, or define local HTML pass directly from diagnostics facts. This must be explicit before implementation. |
| Minimal PDF may produce empty output | MiMo F-3 / DS F-2 / DS F-4 | accepted | Plan must require a PDF fixture with stable extractable text and a minimum fetched content assertion. Empty or too-short PDF content after a successful fetch is a fail, except for clearly classified Docling runtime dependency/init skip. |
| Diagnostics field ownership mixes facts and smoke classification | DS F-3 | accepted | Plan must separate diagnostics facts from smoke classification, or rename fields so diagnostics describes observed facts while `utils/smoke_web_ci.py` owns smoke-specific pass/fail/skip classification. |
| Diagnostics/smoke schema mismatch handling | MiMo F-4 | accepted | Plan must require schema/version validation and a clear `diagnostic_schema_gap` failure path. |
| Subprocess output to smoke decision mapping is underspecified | DS F-5 | accepted | Plan must include a mapping table for diagnostic subprocess results, JSON parsing failure, Docling init skip, local HTML/PDF fail, and external diagnostic-only outcomes. |
| Shell wrapper optionality | DS F-7 | accepted-with-note | If a wrapper is created, validate with `bash -n`; otherwise omit wrapper validation from the actual implementation report. |
| External/browser/provider residual ownership | MiMo residuals / DS F-8 | accepted | Closeout must either close `WU-TOOLS-01-S5-R2` or transfer remaining external/browser/provider instability to a concrete owner or issue. |
| Line references and status naming polish | MiMo F-5 / F-6 | accepted-low | Amend where cheap, but these do not block implementation if the substantive fixes above are handled. |

## Controller Rationale

The user's added PDF requirement is not satisfied by static inference alone. A smoke gate that says "the URL looked like a PDF and fetch succeeded, therefore Docling must have been used" would be brittle and would fail the root-cause evidence standard. At the same time, adding `extraction_source` to the production `fetch_web_page` success result would change LLM-facing tool output and expose implementation vocabulary without a separate production contract decision.

The best current-phase fix is to strengthen the diagnostics pipeline: during `diagnose_web_access.py` runs, install a narrow wrapper around the current Docling conversion callable, delegate to the original function, and emit diagnostic-only evidence such as invoked flag, stream name, content type, fixture URL, and whether the original conversion completed or raised a Docling initialization error. The smoke wrapper then consumes that diagnostic artifact.

This preserves the intended layering:

- production Web tool behavior remains unchanged;
- diagnostics owns route evidence;
- smoke owns pass/fail/skip classification;
- external URL instability remains diagnostic-only.

## Required Next Gate

Dispatch AgentCodex for plan fix only.

Expected result:

- update `docs/host/wu-tools-01-f03-web-ci-smoke-plan.md`;
- do not implement code;
- do not commit, push, or create PR;
- report the amended sections and remaining open questions.

