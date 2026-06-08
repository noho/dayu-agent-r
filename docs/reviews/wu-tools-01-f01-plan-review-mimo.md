# WU-TOOLS-01-F01 Plan Review Artifact

## Review Metadata

- Reviewer: mimo (plan review agent)
- Date: 2026-06-07
- Gate: plan review
- Plan artifact: `docs/host/wu-tools-01-f01-shared-fins-ingestion-runtime-plan.md`
- Control doc: `docs/host/issues-implementation-control.md`
- Design sources: `docs/host/design.md`, `docs/engine/design.md`
- Review scope: read-only plan review, no code/plan modification

## Overall Verdict

**Accepted with conditions.** The plan is correct in its first-principles judgment, properly aligned with Host/Engine design, and sufficiently code-generation-ready for S1/S2/S4/S5/S6. S3 has a well-scoped stop condition that correctly protects against scope creep. Two findings require controller adjudication; neither is a hard blocker if the conditions are met.

## Validation Run

```bash
# Verify plan's direct code evidence claims (read-only)
# 1. service_runtime.py docstring confirms read-only scope
# 2. provider.py confirms include_ingestion_tools fail-closed
# 3. wait_adapter.py confirms WaitAdapterRegistry/WaitPollAdapter/WaitPoller exist
# 4. host_assembly.py confirms wait_adapter_registry=None
# 5. tool_runtime.py confirms awaiting_accept_port + wait_adapter_registry guard
# 6. tool_await.py confirms ToolAwaitKind.EXTERNAL_JOB
# 7. tool_outcome.py confirms ToolAwaitingOutcome
# 8. ticker_normalization.py confirms normalize_ticker/try_normalize_ticker/ticker_to_company_id
# 9. No dayu/cli directory exists
# 10. No ingestion_runtime.py or download/preprocess provider files exist yet
# 11. Host design Section 20 confirms wait record, resolve_wait, poll/callback/manual paths
```

All plan evidence claims verified against actual codebase. No factual discrepancies found.

## Findings

### F01 — S3 Download Runtime Scope: Source-Specific Downloader Evidence

- **Severity:** medium
- **Category:** scope / evidence
- **Evidence:** Plan S3 (lines 347-413) says "implement download as a Fins runtime business operation" and "route request to source-specific download adapter." Plan's Risks section (line 688) acknowledges "current repo evidence shows that source-specific NEW implementation is absent." S3 stop condition (line 412-413) says "stop and request user decision if completing download is interpreted as rebuilding full SEC/CN/HK downloader breadth."
- **Why not blocking:** The stop condition is correctly written and will protect against scope creep. The plan does not claim to rebuild full downloader breadth. The minimal "download adapter" can be a thin interface stub with deterministic test fake for S1-S5 verification. Real SEC/CN/HK adapter breadth is correctly classified as requiring user decision.
- **Adjudication:** accepted — stop condition is sufficient. Implementation must respect it literally: if the slice attempts real network downloaders, stop and escalate.
- **Suggested correction:** None required. The stop condition is the correct mechanism.

### F02 — S5 Wiring Location Specificity

- **Severity:** low
- **Category:** code-generation readiness
- **Evidence:** Plan S5 (lines 496-572) describes updating `dayu/service/host_assembly.py` to pass `wait_adapter_registry` into `HostToolingOptions`. The current code at `host_assembly.py:1024-1050` shows `_tooling_options_from_discovery(...)` with `wait_adapter_registry=None`. The plan says "detect enabled Fins download/preprocess provider config -> build registry -> HostToolingOptions(wait_adapter_registry=registry)" but does not specify whether the detection happens inside `_tooling_options_from_discovery` or in a new helper called before it.
- **Why not blocking:** The plan's allowed files list and call path are sufficient for implementation. The exact wiring location is an implementation detail within the allowed file set. The invariant "Service assembly fails before open_host if Fins awaiting provider config cannot construct a wait adapter registry" (line 547) gives the implementer a clear verification target.
- **Adjudication:** accepted — plan is sufficiently specific for a skilled implementer.
- **Suggested correction:** None required. Implementer should choose the most natural location within `host_assembly.py` and verify the invariant in tests.

### F03 — Fins Job Store Persistence Mechanism

- **Severity:** low
- **Category:** code-generation readiness
- **Evidence:** Plan S1 (lines 219-220) says "Add Fins job store interface and filesystem implementation for job records only." Plan line 177 says "The Fins job store may use runtime-owned files because job governance state is not financial document content." But no specific file format, directory convention, or locking strategy is specified.
- **Why not blocking:** The plan correctly distinguishes Fins job governance state from financial document content. The "filesystem implementation" is a well-understood pattern in this codebase (see `dayu.fins.storage._fs_*` modules). The implementer has sufficient context to choose JSON files, SQLite, or other filesystem approaches within the `dayu.fins` boundary.
- **Adjudication:** accepted — the plan gives enough direction without over-specifying.
- **Suggested correction:** None required.

### F04 — S2 Preprocess Uses Existing Processors: Boundary Verification

- **Severity:** low
- **Category:** scope / evidence
- **Evidence:** Plan S2 (line 292) says "Use existing `dayu.fins.processors` / `dayu.documents.processors` processor registry to produce processed outputs." Current code shows `DefaultFinsRuntime.create(...)` already builds `build_fins_processor_registry()` and passes it to `FinsToolService`. The plan reuses this same registry for preprocess.
- **Why not blocking:** The processor registry is already assembled in `DefaultFinsRuntime` (line 87 of `service_runtime.py`). S2 only needs to call it from the ingestion executor path. This is a well-scoped extension, not a new boundary.
- **Adjudication:** accepted.
- **Suggested correction:** None required.

### F05 — Provider Split: `include_ingestion_tools` Removal Scope

- **Severity:** low
- **Category:** design alignment
- **Evidence:** Plan S4 (line 438) says "Remove target reliance on `include_ingestion_tools`; after implementation, the old fail-closed test must be replaced with independent provider discovery tests." Plan S6 (line 594) says "Replace default mixed Fins provider config with separate disabled provider entries." Current `provider.py` lines 67-76 show the fail-closed `ValueError`.
- **Why not blocking:** The split is correctly sequenced: S4 creates independent providers, S6 updates config and tests. The fail-closed behavior in current code is a transitional guard, not a permanent contract. Removing it after independent providers exist is correct.
- **Adjudication:** accepted.
- **Suggested correction:** None required.

### F06 — LLM-Facing Schema Self-Containment

- **Severity:** low
- **Category:** design alignment
- **Evidence:** Plan S4 (line 442) says "Tool schemas must be self-explanatory for LLMs and not expose Host internals, digest, cursor, raw job record paths or tool_call_id." This aligns with CLAUDE.md Agent semantic constraints: "只写模型完成当前任务所需的动作、输入、输出、判断规则和禁止事项；不用代码类型名、内部模块名、历史迁移名或 Host 实现术语要求模型自行理解。"
- **Why not blocking:** The constraint is correctly stated and testable (inspect tool schema JSON in tests).
- **Adjudication:** accepted.
- **Suggested correction:** None required.

## Architecture Alignment Summary

| Design Source | Constraint | Plan Compliance |
|---|---|---|
| Host design §2 | `UI -> Service -> Host -> Engine` | Compliant. Fins runtime stays in `dayu.fins`, wait adapter wiring in Service. |
| Host design §3 | `dayu.runtime` must not import `dayu.fins` | Compliant. Plan explicitly keeps Fins runtime under `dayu.fins`. |
| Host design §3 | `ToolsDiscovery` layer-neutral | Compliant. No Fins imports added to `dayu.runtime`. |
| Host design §18 | `ToolRuntime` owns tool execution governance | Compliant. Awaiting acceptance remains Host-owned. |
| Host design §20 | `ToolAwaitingOutcome` path, wait record semantics | Compliant. S4 returns `ToolAwaitingOutcome`, S5 wires poll adapter. |
| Host design §10.1 | `HostToolingOptions.wait_adapter_registry` | Compliant. S5 updates Service assembly to populate it. |
| Engine design §1.1 | Financial doc storage outside Engine | Compliant. Storage access through `dayu.fins.storage`. |
| Engine design §12 | `ToolAwaitingOutcome` only suspension path | Compliant. Download/preprocess return it, not `ToolResult.meta`. |
| Engine design §12 | Engine handshake timeout bounded | Compliant. Long work returns `ToolAwaitingOutcome` quickly after durable job creation. |
| Engine design §12 | Resume is not recovery of old instance | Compliant. Fins job state maps to Host `resolve_wait` outcomes. |
| Control doc §S4-R1 | F01 owns shared Fins ingestion runtime | Compliant. S1-S6 cover runtime, providers, wait adapter, docs. |
| CLAUDE.md | Agent semantic constraints | Compliant. S4 specifies self-explanatory LLM-facing schemas. |
| CLAUDE.md | Storage boundary | Compliant. All financial doc access through `dayu.fins.storage`. |

## Slice Readiness Assessment

| Slice | Allowed Files | Types/Functions | Call Path | State Machine | Error Handling | Tests | Stop Condition | Verdict |
|---|---|---|---|---|---|---|---|---|
| S1 | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Ready |
| S2 | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Ready |
| S3 | Yes | Yes | Yes | Yes | Yes | Yes | Yes (user decision) | Ready with stop |
| S4 | Yes | Yes | Yes | N/A (provider) | Yes | Yes | Yes | Ready |
| S5 | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Ready |
| S6 | Yes | N/A | N/A | N/A | N/A | Yes | Yes | Ready |

## Residual Risk Classification

| Risk | Classification | Owner / Destination |
|---|---|---|
| `WU-TOOLS-01-S4-R1` | Fixed in current slice (S1-S6) | WU-TOOLS-01-F01 |
| `include_ingestion_tools` fail-closed | Fixed in current slice (S4/S6) | WU-TOOLS-01-F01 |
| Host awaiting adapter missing for Fins | Fixed in current slice (S5) | WU-TOOLS-01-F01 |
| SEC/CN/HK source-specific downloader breadth | Requiring user decision | S3 stop condition escalates |
| Upload migration | Assigned to later work unit | WU-TOOLS-01-F09 |
| SEC/Fins CI pipeline migration | Assigned to later work unit | WU-TOOLS-01-F04/F05 |
| CN/HK Docling CI pipeline migration | Assigned to later work unit | WU-TOOLS-01-F06/F07 |
| Future CLI download/process adapter | Assigned to later work unit | Future CLI/package WU |
| README/config sync | Covered by later approved slice (S6) | WU-TOOLS-01-F01 |
| `WU-TOOLS-01-S1-R1` CI coverage | Tracked by existing issue | WU-TOOLS-01-F04-F07 |
| `WU-TOOLS-01-S1-R2` processor naming | Tracked by existing issue | WU-TOOLS-01-F08 |

## Completion Report

- **Artifact path:** `docs/reviews/wu-tools-01-f01-plan-review-mimo.md`
- **Overall verdict:** Accepted with conditions (2 findings requiring adjudication, neither blocking)
- **Findings summary:** 6 findings total — 0 critical, 1 medium (S3 source-specific downloader scope, protected by stop condition), 5 low (wiring specificity, job store mechanism, processor boundary, provider split scope, schema self-containment)
- **Residual risks:** 3 fixed in current slice, 1 requiring user decision (S3 stop condition), 3 assigned to later work units, 2 tracked by existing issues, 1 covered by later slice
- **Validation run:** Read-only verification of all plan evidence claims against actual codebase. No factual discrepancies found. All design alignment constraints verified.
