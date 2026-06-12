# WU-RET-00 Plan Review Adjudication

- work unit: WU-RET-00 Host Storage Lifecycle Retention Policy
- gate: plan review adjudication / plan fix
- date: 2026-06-12
- plan artifact: `docs/host/wu-ret-00-storage-lifecycle-retention-plan.md`
- review artifacts:
  - `docs/reviews/wu-ret-00-plan-review-mimo.md`
  - `docs/reviews/wu-ret-00-plan-review-ds.md`

## Controller Verdict

Plan review result is **PASS after plan fix**.

Both reviewers found no blocking finding. The controller accepted the findings that affect safety or code-generation readiness and updated the plan artifact before re-review. The most important accepted fix is the `sha256/` namespace restriction: artifact maintenance must never scan or reclaim arbitrary files under `artifact_root`, because audit and tool trace JSONL files can also live under that root.

## Accepted Findings

| Finding | Source | Verdict | Plan fix status |
| --- | --- | --- | --- |
| Restrict artifact file scanning to `sha256/` namespace | AgentDS F6 | accepted | fixed in plan Slice 1 / Slice 3 / risk R6 |
| New public maintenance API requires design source sync | AgentDS F2 | accepted | fixed in docs decision and affected files |
| Clarify descriptor logical bytes vs physical bytes | AgentDS F1 / AgentMiMo F7 | accepted | fixed by renaming to `artifact_descriptor_logical_bytes` and docstring requirement |
| Document recheck/unlink TOCTOU residual | AgentDS F3 | accepted | fixed in implementation decisions / R1 |
| Ensure one truth for artifact path reference check | AgentDS F4 | accepted | fixed in implementation decisions |
| `_open_durable_connection()` close contract must be explicit | AgentDS F5 | accepted | fixed in affected files / implementation decisions |
| Avoid storage path god bag | AgentMiMo F1 | accepted | fixed by preferring `_db_path()` and `_artifact_root_options()` |
| Complete or justify usage report table coverage | AgentMiMo F2 | accepted | fixed in Slice 2 implementation note |
| Use final path containment guard for delete | AgentMiMo F3 | accepted | fixed in Slice 1 exact changes |
| Fix grace default | AgentMiMo F4 | accepted | fixed as `DEFAULT_ORPHAN_ARTIFACT_GRACE_SECONDS = 3600.0` |
| Avoid leaking transaction outside transaction boundary | AgentMiMo F5 | accepted-with-correction | fixed by replacing transaction factory with explicit recheck callable; the suggested `lambda: host._run_read(lambda txn: txn)` is rejected as unsafe because it would return a transaction outside its valid boundary |
| Clarify single-file deletion failure behavior | AgentMiMo F6 | accepted | fixed by adding `HostStorageMaintenanceFileError` / `file_errors` |

## Rejected Or Deferred Findings

| Finding | Source | Verdict | Reason |
| --- | --- | --- | --- |
| Do not update `docs/host/design.md` | AgentMiMo design-source conclusion | rejected-with-reason | The plan adds operator-facing Host public API / maintenance entrypoint. Per project constraints, public contract changes must update design truth. The design update is narrow and does not add scheduler, VACUUM, schema, or JSONL governance scope. |
| Implement DB VACUUM in current WU | User issue comparison / Issue 76 | deferred-with-owner | GitHub Issue 76 owns SQLite vacuum / space reclamation strategy. WU-RET-00 only exposes DB/WAL size and checkpoint diagnostics. |

## Residual Risks

| ID | Status | Owner / Destination | Note |
| --- | --- | --- | --- |
| R1 | accepted-current-WU | Slice 3 / Slice 4 | publish-before-commit and recheck/unlink TOCTOU are mitigated by dry-run default, 3600s grace, recheck, and containment. |
| R2 | deferred-with-owner | later cleanup WU | purge `cleanup_refs` remains a dead field; maintenance scanning closes correctness without touching central purge path. |
| R3 | deferred-with-owner | later storage lifecycle follow-up | orphan SQLite payload rows are reported, not deleted. |
| R4 | covered-by-design | WU-RET-00 | artifact root scan is maintenance-only and not command path. |
| R5 | deferred-with-owner | GitHub Issue 76 | SQLite VACUUM / space reclamation remains out of current WU. |
| R6 | fixed-in-plan | WU-RET-00 implementation | only `sha256/` namespace is eligible for artifact orphan scanning / reclaim. |

## Re-review Request

Re-review should check only the plan fix delta:

- `sha256/` namespace restriction is explicit enough for implementation.
- design-source update requirement is correctly captured.
- transaction-boundary correction avoids returning `HostTransaction`.
- Issue 76 is correctly deferred as DB VACUUM owner.
- plan remains minimal and code-generation-ready.

