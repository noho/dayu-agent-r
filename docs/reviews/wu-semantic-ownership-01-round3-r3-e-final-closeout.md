# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-E Final Closeout

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 Round3 R3-E - Web/Documents egress, resource, diagnostics, and oracle ownership`
- Gate: local final closeout
- Design truth: `docs/host/design.md`, `docs/engine/design.md`
- Control truth: `docs/host/issues-implementation-control.md`, `docs/phaseflow-umbrella-optimization-control.md`
- Plan: `docs/host/wu-semantic-ownership-01-round3-r3-e-web-doc-egress-resource-plan.md`

## Accepted Commits

- Goal confirmation: `18d62f40`
- Plan: `cd5e8595`
- Plan acceptance record: `e0634fbe`
- S1 implementation and review/fix acceptance: `a20efac7`
- S1 acceptance record: `fc31619b`
- S2 implementation and review/fix acceptance: `728e73af`
- S2 acceptance record: `c2009966`
- S3 implementation and review/fix acceptance: `94a12c9e`
- S3 acceptance record: `2e47ee63`
- S4 implementation and review acceptance: `7e4749e5`
- S4 acceptance record: `c1024a43`
- Aggregate deepreview acceptance: `989ca0eb`
- Aggregate acceptance record: `cccc3ce4`

## What Changed

R3-E fixed the Web/Documents semantic ownership findings accepted from Round3 review:

- Web egress ownership is centralized in `WebEgressPolicy`, `AuthorizedHttpTarget`, and target-bound HTTP connection adapters with connect-time peer proof.
- Web response ownership now uses an `AuthorizedResponseLease`, so redirect, rejection, success-transfer, and cancellation paths close response handles exactly once.
- Web resource budgets are owned by typed `WebResourceBudget` values and enforced before unsafe materialization across requests, warmup, decoded body, and Playwright DOM probes.
- Bot-challenge outcomes are owned by a closed `BotChallengeDecision` contract rather than status-code/string-matching callers.
- DuckDuckGo shape drift now reports typed provider response errors instead of silently returning empty success.
- Web diagnostics now project schema v2 safe URL/content diagnostics through `WebDiagnosticProjection`; reversible response prefixes and sensitive URL parts are not persisted or LLM-facing.
- Storage-state diagnostics use explicit opt-in, positive TTL, atomic publish, owner-named reconciliation, and post-replace cleanup.
- Web smoke PASS is owned by parent-observed fixture ledger evidence, frozen before classification, with negative controls and schema v2 rejection of old prefix fields.
- Document tools now read from `BoundedSourceSnapshot` and `DocResourceBudget` before processor construction, text decoding, directory listing, and search result accumulation.

## Review And Fix Status

All accepted R3-E findings are closed.

- S1 code review found one current-scope issue; AgentCodex fixed it; MiMo/DS re-review passed.
- S2 code review found three accepted current-scope issues; AgentCodex fixed them; MiMo/DS re-review passed. Two findings were rejected with reason, and one was deferred to S3 then closed there.
- S3 code review found nine accepted current-scope issues; AgentCodex fixed them; MiMo/DS re-review passed.
- S4 code review by AgentMiMo and AgentDS found zero material findings; no fix gate was required.
- Aggregate deepreview by AgentMiMo and AgentDS found zero material findings; no aggregate fix gate was required.

## Validation

Controller aggregate validation:

- `source .venv/bin/activate && pytest tests/tools/web tests/documents tests/tools/test_doc_tools_provider.py -q`: `280 passed, 2 skipped, 3 warnings`
- `source .venv/bin/activate && pyright`: `0 errors, 0 warnings, 0 informations`
- `git diff --check`: pass
- Legacy diagnostic field scan: only expected `utils/smoke_web_ci.py` denylist entries for rejecting old schema fields.
- Tool-security / file-authority / SSRF / TLS / symlink-safe / generic capability scan: no current-scope implementation; hits were artifacts, historical control text, import-boundary forbidden lists, or unrelated existing forbidden-term tests.

The three warnings are existing upstream `edgar` deprecation warnings and are not R3-E regressions.

## README / Documentation

- `dayu/config/README.md` was updated during S2 because Web resource-budget configuration changed.
- `tests/README.md` was updated during S3/S4 because Web diagnostics/smoke and Documents bounded-source test ownership changed.
- No root, `dayu/README.md`, Host, Engine, Fins, or new tools/documents README update was required because R3-E did not change those reader-facing contracts.
- Control doc was updated with the R3-E slice artifacts, aggregate artifacts, accepted commits, validation, residual destinations, and final closeout state.

## Tool-Security Statement

No unrelated tool-security code was implemented in R3-E.

R3-E implemented Web egress/resource/diagnostic and Documents source-budget owner contracts only. It did not implement repository-wide tool security, Fins upload/download security policy, file-authority/symlink-race policy, SSRF/TLS provenance policy, browser sandbox/proxy policy, generic capability governance, or LLM-facing upload/download security schema/prompt changes. Those remain deferred to later dedicated owners.

## Residual Risk Reconciliation

| Residual | Status | Owner / destination |
| --- | --- | --- |
| `pytest-cov` dotted source / NumPy double-load validation issue | accepted validation tooling residual | Coverage toolchain; equivalent coverage path passed |
| Web diagnostic digest is not a confidentiality guarantee for low-entropy content | accepted contract limitation | `dayu.tools.web.web_diagnostics` |
| Playwright lacks response-body streaming iterator | accepted API limitation | `utils/diagnose_web_access.py`; Content-Length early reject plus post body budget |
| SIGKILL or host crash can leave storage-state or bounded-source temp files | accepted lifecycle limitation | Storage-state lifecycle and bounded-source cleanup owners |
| Doc processor object graph can exceed raw input bytes | deferred-with-owner | Future processor-complexity budget WU |
| Doc file-authority / symlink-race policy remains unimplemented | deferred-with-owner | Future Doc tool file-authority WU |
| Public Playwright direct egress defaults fail closed when peer proof is unavailable | deferred-with-owner | Future browser egress proxy/deployment WU |
| External live URL/search provider behavior remains diagnostic-only | accepted external boundary | `utils/smoke_web_ci.py` external/search classifier |
| Existing edgar deprecation warnings | deferred-with-owner | Dependency upgrade tracking |

No accepted current-scope R3-E finding remains open.

## Final Decision

R3-E reached local final-closeout-pass.

R3-F, R3-A, R3-B, R3-C, R3-D, and R3-E have now all reached local final-closeout-pass for the accepted Round3 sub WUs. The controller may proceed to umbrella WU final reconciliation and closeout if the control document has no remaining required sub WU gate.
