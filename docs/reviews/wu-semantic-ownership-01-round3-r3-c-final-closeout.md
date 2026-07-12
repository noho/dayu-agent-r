# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-C Final Closeout

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 / Round3 / R3-C`
- Theme: Fins storage / upload / download provenance and atomicity
- Branch: `phaseflow/host-issues-control`
- Accepted plan commit: `7b24b070`
- Accepted slice commits: S1 `6e9ad77e`, S2 `272575e4`, S3 `9ef24a68`
- Accepted aggregate commit: `01597147`

## What Changed

- S1 moved Fins storage identity, object-key validation, local URI containment, commit point, rollback, orphan recovery, and local blob durability behind storage owner contracts.
- S2 made upload, generic download, and CN/HK filing ingestion use single-document caller-owned batches with storage-owned commit points, and replaced CN/HK temp PDF path handoff with `pdf_bytes`.
- S3 moved Fins wait adapter assembly to Service, deleted the Fins-to-Host reverse dependency, and made Host project only the public `WaitAdapterSnapshot` into external adapters.
- README updates were applied where triggered: `dayu/README.md`, `dayu/fins/README.md`, `dayu/host/README.md`, `dayu/service/README.md`, and `tests/README.md`.

## Finding Status

- Plan review findings: all accepted R3-C plan findings were fixed before implementation.
- S1 code review findings: fixed and re-reviewed; no remaining material finding.
- S2 code review findings: fixed and re-reviewed; no remaining material finding.
- S3 code review findings: no fix gate required.
- Aggregate deepreview: AgentMiMo and AgentDS both returned PASS; controller accepted aggregate deepreview with no fix / re-review gate.

## Verification

- Aggregate affected matrix: `774 passed, 1 skipped, 3 warnings`.
- Pyright: `0 errors`.
- `git diff --check`: pass.
- Fins to Host import scan: no matches.
- Temp/PDF path scans: no matches.
- Tool-security implementation diff scan over production/tests: no current-scope implementation matches.

## Residual Risk Reconciliation

| Residual | Status | Owner / destination |
| --- | --- | --- |
| S1 orphan recovery branch coverage enhancements | Non-blocking test enhancement | `dayu.fins.storage` recovery tests |
| Rollback rename failure can leave physical recovery evidence | Deferred with owner | Fins storage orphan recovery / filesystem backend portability |
| Directory fsync unsupported-platform behavior is best-effort | Deferred with owner | Future filesystem backend portability work |
| Multi-document transaction rollback | Accepted non-goal | New WU only if business requirement appears |
| CN/HK Docling synchronous conversion cannot be physically interrupted mid-call | Deferred with owner | Future process/subprocess isolation WU |
| Tool-security four items | Deferred with owner | Later dedicated tool-security WU |
| `_execute_with_auto_batch` rollback error chaining | Deferred with owner | Future non-document-mutation storage cleanup |
| `docling_upload_service.py` local `_normalize_ticker` | Deferred with owner | Future consumer-normalizer cleanup; storage remains final identity gate |

## Tool-Security Statement

R3-C did not implement tool security. The following remain unplanned for this WU and deferred to a later dedicated owner:

- Upload allowlist / file authority / symlink-safe upload source policy.
- URL, TLS, redirect, SSRF, and remote provenance policy.
- Remote download byte-budget policy.
- LLM-facing upload/download security schema or prompt changes.

The symlink containment behavior implemented in R3-C is storage identity / object-key containment, not tool-security policy.

## Closeout Decision

R3-C reached local final-closeout-pass. All accepted R3-C findings are closed. No current-scope material finding remains unfixed.

Next entry point: Round3 R3-D Fins financial/read semantics goal confirmation / plan. The umbrella WU remains open until the accepted Round3 sub WUs through R3-E are implemented, reviewed, fixed where needed, validated, committed, and final closeout passes.
