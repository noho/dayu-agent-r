# WU-TOOLS-CANCEL-01 Residual Risk Reopen Controller Decision

## Scope

- Work unit: WU-TOOLS-CANCEL-01
- Gate: residual risk reconciliation / reopened planning entry
- Branch: `phase/wu-tools-cancel-01`
- Draft PR: https://github.com/noho/dayu-agent-r/pull/170
- Design sources: `docs/host/design.md`, `docs/engine/design.md`
- Control source: `docs/host/issues-implementation-control.md`

## User Decision

On 2026-07-05, the user reclassified the WU-TOOLS-CANCEL-01 final closeout residual risks:

| Risk | Decision |
|---|---|
| Process envelope hint structure | Must be fixed in WU-TOOLS-CANCEL-01 |
| Web process cold-start | Deferred; performance-only if it does not weaken cancellation robustness |
| Playwright cleanup smoke | Must be fixed in WU-TOOLS-CANCEL-01 |
| Fins XBRL fixture breadth | Must be fixed in WU-TOOLS-CANCEL-01; use an already downloaded AAPL filing as fixture if suitable |
| Process envelope constants single-source | Must be fixed in WU-TOOLS-CANCEL-01; Host may define the process-backed envelope contract, but must not assume concrete tools exist |
| Process capsule grace tuning | Must be fixed in WU-TOOLS-CANCEL-01; avoid raw hard-coded constants, use typed runtime policy/config with defaults and validation |

## First-principles Judgment

The motivation is valid. The previous final closeout correctly proved the user-perceived interrupt path, but these five non-performance risks affect the durability of that guarantee:

- Process envelope hint structure and single-source constants are public contract hygiene for process-backed tools.
- Playwright cleanup needs evidence for nested browser subprocess behavior, not only parent process cancellation.
- Fins XBRL fixture breadth is a real representative business path for process-backed Fins read.
- Process capsule grace tuning should be a typed Host runtime policy, not an untracked magic constant.

Web process cold-start remains a performance tradeoff. It does not weaken cancellation robustness because the process-backed boundary still gives Host an interruptible execution boundary and late-result isolation.

## Gate Decision

The previous `final-closeout-pass` state is superseded. WU-TOOLS-CANCEL-01 is reopened at the plan gate for residual hardening. PR #170 remains draft/open and must not be marked ready or merged until the reopened gate chain reaches final closeout again.

## Next Gate

Dispatch AgentCodex to produce a code-generation-ready residual hardening plan.

The plan must cover:

- process envelope contract ownership and typed helper location;
- structured hint propagation without exposing Host-governed statuses from child processes;
- Playwright nested process cleanup test strategy and any required runtime process tree changes;
- AAPL XBRL fixture selection and Fins spawned-child coverage;
- single-source envelope constants without Host importing tool packages or tools importing Host internals;
- typed process capsule interrupt grace policy/config, keeping `tool_execution_timeout_seconds` as the only tool-call business deadline;
- slice boundaries, validation commands, docs/README update decisions, and stop conditions.

## Non-goals

- Do not optimize Web process cold-start in this WU.
- Do not introduce a tool registry in Host.
- Do not let Host import Doc, Fins, or Web tool modules.
- Do not put execution policy into LLM-facing tool schema.
- Do not change `tool_execution_timeout_seconds` semantics.

