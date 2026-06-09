# WU-TOOLS-01-F01-03 Goal Confirmation Controller

## Metadata

- Work unit: `WU-TOOLS-01-F01-03`
- Gate: goal confirmation
- Controller branch: `phase/wu-tools-01-f01-03`
- Date: 2026-06-09
- Design sources: `docs/host/design.md`; `docs/engine/design.md`
- Control source: `docs/host/issues-implementation-control.md`

## Decision

Goal confirmed. `WU-TOOLS-01-F01-03` should proceed to the plan gate.

This work unit is an OLD-to-NEW migration and NEW-contract adaptation. It is not a rewrite of the proven OLD business logic. OLD SEC/CN/HK downloader implementations and SEC/CN pipeline download/upload workflow implementations must be migrated rather than reimplemented. Public and internal interfaces may be changed only where needed to fit NEW layering, typed contracts, storage protocols, ToolRuntime, awaiting, cancellation, tests, and documentation.

Upload is classified as a long transaction for this work unit. The plan must model upload through the same durable ingestion / awaiting external-job family as download and preprocess unless direct code evidence proves a narrower long-transaction shape is required. If a `start_upload` awaiting tool is introduced, GitHub Issue 129 must be updated before closeout to track future prepare / activate coverage for `start_upload` alongside `start_download` and `start_preprocess`. Controller authorization is still required before modifying external GitHub issues.

## First-Principles Judgment

The motivation is valid. F01 established shared Fins runtime foundations, but real production ingestion still depends on source-specific download adapters and upload runtime/tool entrypoints.

Direct NEW code evidence:

- `DefaultFinsRuntime.get_ingestion_runtime()` currently creates `FinsIngestionRuntime` without real SEC/CN/HK download adapters.
- `FinsIngestionRuntime._select_download_adapter()` fails when `(source, market)` has no adapter.
- `dayu/config/tool_discovery.json` exposes Fins read, download, and preprocess providers, but no upload provider.
- NEW code has download/preprocess awaiting tools, but no `start_upload`, upload tool callable, or upload provider.

Direct OLD code evidence:

- OLD contains `SecDownloader`, `CninfoDiscoveryClient`, and `HkexnewsDiscoveryClient`.
- OLD contains SEC and CN pipeline download/upload workflow code.
- OLD contains focused tests for SEC/CN/HK downloader, download workflow, upload workflow, storage behavior, and pipeline boundaries.

Therefore the correct path is migration plus contract adaptation, not NEW-side business logic invention.

## Goal

- Migrate SEC download, CN download, and HK download capability from OLD into NEW source adapters/runtime entrypoints.
- Migrate SEC/CN/HK upload workflow capability from OLD into NEW shared Fins runtime and upload tool entrypoint.
- Preserve shared `dayu.fins.storage` as the only financial document storage boundary.
- Preserve `dayu.fins.ticker_normalization` as the only ticker / market normalization truth.
- Ensure future CLI and CI can call the same shared Fins runtime APIs without copying download/upload business rules.
- Expose upload through ToolDiscovery and ToolRuntime with Host-governed awaiting semantics for the long transaction path.

## Non-Goals

- Do not implement Host two-phase activation in this work unit.
- Do not rewrite OLD downloader or pipeline business logic.
- Do not migrate OLD UI, FastAPI, Streamlit, OLD ToolRegistry, OLD truncation manager, OLD `fetch_more`, or OLD path safety framework.
- Do not create separate CLI, CI, and tool business implementations.
- Do not change Host / Engine public contracts unless the plan identifies a blocking design mismatch and returns to controller discussion first.

## Success Signals

- Code-generation-ready plan identifies small implementation slices with explicit file ownership and validation commands.
- Plan traces OLD source modules/tests to NEW destination modules/tests.
- Plan defines upload as long transaction and states how `start_upload` fits current awaiting / wait-resume governance.
- Plan states when Issue 129 must be updated and what authorization is required before doing so.
- Plan includes README and test README update decisions.

## Blocking Open Questions

None for entering the plan gate.

## Next Entry Point

Dispatch `AgentCodex` to produce the code-generation-ready plan at `docs/host/wu-tools-01-f01-03-production-fins-ingestion-plan.md`.
