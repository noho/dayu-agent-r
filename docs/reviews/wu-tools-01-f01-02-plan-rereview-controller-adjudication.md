# WU-TOOLS-01-F01-02 Plan Re-Review Controller Adjudication

## Metadata

| 项目 | 值 |
|---|---|
| work unit | WU-TOOLS-01-F01-02 |
| gate | plan re-review controller adjudication |
| plan artifact | `docs/host/wu-tools-01-f01-02-cancellation-plan.md` |
| fix artifact | `docs/reviews/wu-tools-01-f01-02-plan-fix-codex.md` |
| re-review artifacts | `docs/reviews/wu-tools-01-f01-02-plan-rereview-mimo.md`; `docs/reviews/wu-tools-01-f01-02-plan-rereview-ds.md` |
| date | 2026-06-08 |

## Controller Decision

Plan re-review passed. The plan is code-generation-ready and may proceed to accepted plan commit, then implementation gate.

Both reviewers verified the four required plan fixes:

- direct Fins awaiting callable `ToolExecutionOutcome` legally includes `ToolCancelledOutcome`;
- durable job create / cancellation checkpoint / background submit timing is explicitly constrained;
- Fins read checkpoint density is split between bounded instant reads and high-risk looping / processor / XBRL paths;
- `search_public_web` provider fallback checks cancellation before each provider attempt and stops subsequent fallback attempts after cancellation.

## Final Finding Status

| Finding | Final status | Evidence |
|---|---|---|
| F-DS-1 / F-MIMO-04 callable cancelled outcome type clarity | 已修复 | Re-reviewed by AgentMiMo and AgentDS. |
| F-DS-2 / F-MIMO-05 create/checkpoint/submit timing invariant | 已修复 | Re-reviewed by AgentMiMo and AgentDS. |
| F-DS-4 checkpoint density standard | 已修复 | Re-reviewed by AgentMiMo and AgentDS. |
| F-DS-5 provider fallback checkpoint location | 已修复 | Re-reviewed by AgentMiMo and AgentDS. |

Non-blocking implementation constraints remain owned by the implementation gate:

- grep and decide whether `read_section` can remove or must retain `**_kwargs`;
- audit `search_public_web` callers before changing the signature;
- reuse the existing Web `tool_cancelled` business error pattern for Doc / Fins read unless direct evidence shows a better adapter-compatible type;
- record which tools have behavior-level tests and which are covered by declaration-level audit matrix;
- record two-stage startup residual risk R1 and synchronous-call limitation R2 in implementation report.

## Residual Risks

| ID | 状态 | Owner / Destination | 下一步 |
|---|---|---|---|
| R1 | deferred-with-owner | WU-WAIT-03 or independent Host awaiting activation design WU | Do not implement two-stage startup in this WU; design Host awaiting accepted activation contract first. |
| R2 | accepted limitation | WU-TOOLS-01-F01-02 implementation report | Synchronous requests / filesystem / processor calls can only be checkpointed, not physically preempted. |
| R3 | deferred-with-owner | future tool adapter cancellation contract WU | Legacy adapter cancelled-as-failed outcome remains a known contract limitation. |

## Gate Result

Proceed to accepted plan commit.
