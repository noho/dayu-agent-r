# WU-CM-01 Slice C Blocker Controller Adjudication

## Metadata

| 项目 | 值 |
|---|---|
| work unit | WU-CM-01 Conversation Memory overall optimization |
| gate | Slice C implementation blocker adjudication |
| design source | `docs/host/design.md` |
| control doc | `docs/host/issues-implementation-control.md` |
| blocker artifact | `docs/reviews/wu-cm-01-slice-c-implementation-codex.md` |
| adjudicator | AgentController |
| adjudication date | 2026-06-04 |

## Verdict

The Slice C blocker is **accepted**.

The motivation for Slice C remains valid: memory durable/projection must move to the vNext conversation memory model. The blocker is a plan slicing error. The current Slice C allowed files do not include all direct production consumers of the old `ConversationMemorySnapshot` and `MemoryProjectionPolicy` shapes, so the slice cannot be made pyright-clean without either modifying disallowed modules or retaining compatibility fields / bridge helpers.

## Accepted Evidence

AgentCodex identified direct consumer evidence:

- `dayu/host/run_input.py` reads old snapshot fields and belongs to Slice D in the current plan.
- `dayu/host/compact_material.py` reads old snapshot fields for compact material construction but is not allowed in Slice C.
- `dayu/host/dispatch.py` reads old memory snapshot fields in dispatch precondition paths but is not allowed in Slice C.
- `dayu/service/host_assembly.py` and `dayu/runtime/config_loader.py` construct old `MemoryProjectionPolicy` shapes and are not allowed in Slice C.
- Multiple tests outside Slice C allowed files still construct or assert old snapshot / policy shapes.

This means deleting the old shape within current Slice C would fail full pyright in disallowed consumers. Retaining compatibility aliases or bridge helpers would violate the plan and AGENTS constraints.

## Decision

Return to plan fix/reslice gate.

The next plan fix must choose one of these structurally coherent paths:

1. Expand Slice C into a larger pyright-clean vertical slice that includes direct snapshot / policy production consumers and their tests.
2. Split Slice C into smaller pyright-clean sub-slices that first introduce a directly-owned vNext memory contract without deleting old production snapshot consumers, then migrate consumers in a later accepted slice. If this path is chosen, the plan must explicitly avoid compatibility wrappers, re-exports, old-field aliases, or bridge helpers.

The current plan cannot continue as-is.

## Current Workspace State

No production code or tests were modified by the Slice C attempt. The only new file is the blocker artifact.

## Required Next Gate

Send AgentCodex to Slice C plan fix/reslice. It must update the plan and write a plan-fix artifact before implementation resumes.
