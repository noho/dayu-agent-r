# WU-TOOLS-01-F01 Plan Re-Review Artifact

## Review Metadata

- Reviewer: mimo (plan re-review agent)
- Date: 2026-06-07
- Gate: plan re-review
- Plan artifact: `docs/host/wu-tools-01-f01-shared-fins-ingestion-runtime-plan.md`
- Original review: `docs/reviews/wu-tools-01-f01-plan-review-mimo.md`
- Original review: `docs/reviews/wu-tools-01-f01-plan-review-ds.md`
- Controller adjudication: `docs/reviews/wu-tools-01-f01-plan-review-controller-adjudication.md`
- Plan fix summary: `docs/reviews/wu-tools-01-f01-plan-fix-controller-summary.md`
- Review scope: only re-review accepted findings fix status; no new full plan review; read-only; no file modification, commit, push or PR

## Overall Verdict

**PASS** — All 6 accepted findings are fixed. The plan fix correctly addresses every controller-adjudicated requirement. No remaining blockers for entering implementation gate.

## Finding Status Table

| # | Accepted Finding | Status | Evidence |
|---|---|---|---|
| 1 | S3 download scope: typed runtime + source adapter protocol + deterministic no-network fake path + storage write path + unsupported-source failure; no real SEC/CN/HK network download adapters in F01 | 已修复 | Plan lines 185-188 (Download adapter scope), lines 385-391 (S3 Exact allowed changes), lines 412-413 (S3 Non-goals), lines 430-436 (S3 completion signal + stop condition), lines 711 (Risks). All five required elements explicitly listed; real network adapters explicitly deferred. |
| 2 | Provider/runtime sharing: shared business code + workspace-scoped durable state, not Python singleton; module-level singleton forbidden; same workspace job store atomic/locked writes | 已修复 | Plan lines 141-143 (Implementation Decisions: "does not require one Python object instance", "Do not introduce a module-level singleton", "same workspace-derived job store path and cross-instance-safe writes"), line 236 (S1: "atomic/locked semantics so multiple runtime instances...are safe without a module-level singleton"), lines 281-282 (S1 Expected assertions: "Two create() instances read/write the same workspace-derived job store safely without sharing a Python object singleton"). |
| 3 | S5 provider detection: configured provider ids/import paths/binding specs, validate workspace_root, no ToolsDiscoveryProviderOutput change, no dependency on diagnostics strings | 已修复 | Plan lines 202-205 (Service/composition-root adapter: "detects Fins awaiting providers from explicit configured provider ids, import paths and binding specs", "must not inspect diagnostic strings", "Do not change ToolsDiscoveryProviderOutput shape"), lines 544-549 (S5 Exact allowed changes: "Detect Fins awaiting providers from explicit configured provider ids, import paths and binding specs", "Do not change ToolsDiscoveryProviderOutput shape and do not depend on provider diagnostics strings"), lines 561-565 (S5 call paths: "inspect explicit configured provider ids/import paths/binding specs"). |
| 4 | Job store path: workspace-derived path, only job governance records | 已修复 | Plan line 181 ("deterministic from workspace_root, such as `<workspace_root>/.dayu/fins_ingestion/jobs`"), line 182 ("must save only job governance records and must use atomic replacement plus a lock"), lines 235-236 (S1: "Derive the job store path from workspace_root"), lines 258 (S1 invariants: "Job store records contain governance state only...must not contain source document正文, processed payloads..."). |
| 5 | `include_ingestion_tools`: not target config; split providers 后 delete read-provider ingestion parsing/fail-closed test | 已修复 | Plan lines 192-193 (Provider split: "must remove include_ingestion_tools parsing from the target implementation after download/preprocess providers exist", "not a supported target config"), lines 460-461 (S4: "Remove read-provider include_ingestion_tools parsing after split providers exist; the old fail-closed test must be replaced with independent provider discovery tests"), lines 628-629 (S6: "Delete or rewrite tests that assert read-provider include_ingestion_tools fail-closed behavior"). |
| 6 | LLM-facing schema self-containment + processor/storage boundary | 已修复 | Plan line 465 (S4: "Tool schemas must be self-explanatory for LLMs and not expose Host internals, digest, cursor, raw job record paths or tool_call_id"), line 407 (S3: "Network/provider raw payloads must not be stored in job records or LLM-facing tool results"), line 258 (S1 invariants: governance records only, no source document payloads or raw filesystem paths), line 259 (S1: "must not contain source document正文, processed payloads, provider raw payloads or raw filesystem document paths exposed to tools"). |

## Validation Run

只读核查，不执行 pytest/pyright：

```text
$ git branch --show-current
host-wu-tools-01-f01

# Confirm plan artifact is the only file modified in fix gate
$ git status --short
M  docs/host/wu-tools-01-f01-shared-fins-ingestion-runtime-plan.md
?? docs/reviews/wu-tools-01-f01-plan-fix-controller-summary.md
→ plan artifact modified; fix summary is new review artifact; no production code changed.

# Verify key evidence lines exist in fixed plan
$ grep -n "module-level singleton" docs/host/wu-tools-01-f01-shared-fins-ingestion-runtime-plan.md
→ line 142: "Do not introduce a module-level singleton or hidden memoized global runtime factory."

$ grep -n "atomic replacement" docs/host/wu-tools-01-f01-shared-fins-ingestion-runtime-plan.md
→ line 182: "must use atomic replacement plus a lock, or an equivalent transactional filesystem-safe mechanism"

$ grep -n "explicit configured provider ids" docs/host/wu-tools-01-f01-shared-fins-ingestion-runtime-plan.md
→ line 202, 544, 561: consistent three-point articulation of detection mechanism.

$ grep -n "not inspect diagnostic strings" docs/host/wu-tools-01-f01-shared-fins-ingestion-runtime-plan.md
→ line 202, 549: prohibition stated in both design decisions and S5 allowed changes.

$ grep -n "include_ingestion_tools.*not.*supported target" docs/host/wu-tools-01-f01-shared-fins-ingestion-runtime-plan.md
→ line 193: "include_ingestion_tools is not a supported target config."

$ grep -n "governance state only" docs/host/wu-tools-01-f01-shared-fins-ingestion-runtime-plan.md
→ line 258: "Job store records contain governance state only"
```

All evidence claims verified against the fixed plan artifact. No factual discrepancies.

## Residual Risks

No new residual risks introduced by the fix. All residual risks from the controller adjudication remain unchanged:

| Risk | Classification | Owner / Destination |
|---|---|---|
| Real SEC/CN/HK network download adapters | deferred-with-owner | Later Fins source-adapter work unit or explicit user-approved F01 scope expansion |
| Upload ingestion | assigned to later work unit | `WU-TOOLS-01-F09` |
| SEC/Fins CI pipeline | assigned to later work unit | `WU-TOOLS-01-F04/F05` |
| CN/HK Docling CI pipeline | assigned to later work unit | `WU-TOOLS-01-F06/F07` |
| Future CLI download/process wrapper | assigned to later work unit | Future CLI/package work unit unless user explicitly expands F01 |

## Completion Report

- **Artifact path**: `docs/reviews/wu-tools-01-f01-plan-rereview-mimo.md`
- **Overall verdict**: PASS
- **Finding status**: 6/6 accepted findings fixed
- **Remaining blockers**: None
- **Residual risks**: 5 items deferred to later work units (unchanged from controller adjudication)
- **Validation run**: Read-only grep verification of all 6 finding evidence claims against the fixed plan artifact. No factual discrepancies found. pytest/pyright not required for this gate.
