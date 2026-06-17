# WU-CLI-ACTIVITY-01 Plan Review Adjudication

## Scope

- Work unit: `WU-CLI-ACTIVITY-01`
- Gate: plan review adjudication
- Plan artifact: `docs/host/host-issues/wu-cli-activity-01-activity-composer-plan.md`
- Review artifacts:
  - `docs/reviews/plan-review-20260617-124817.md` (AgentMiMo)
  - `docs/reviews/plan-review-20260617-124923.md` (AgentDS)

## Decision

Plan review does not block the work unit direction. The plan must receive one fix pass before re-review because several findings identify code-generation-readiness gaps, especially around Host-owned tool display metadata lookup and cancel race semantics.

## Finding Adjudication

| Finding | Decision | Rationale |
|---|---|---|
| MiMo F001: `HostEventClass` enum undefined | rejected-with-reason | Code fact: `dayu/host/api.py` already defines public `HostEventClass` with `CANONICAL_FACT`, `PREVIEW`, `DIAGNOSTIC`, and `PROJECTION_SIGNAL`. The plan should clarify that it reuses this existing enum, but the finding's premise is false. |
| MiMo F002: `event_type` semantics unclear | accepted | Plan should explicitly state `HostEvent.event_type` is copied from EventLog row `event_type` and is a public event identity label, not UI copy or business fact. |
| MiMo F003 / DS Finding 1: Host-owned tool metadata lookup unspecified | accepted | Code fact: current `effective_tool_set` freezes tool names/digests/source refs but no display mapping; `ToolSchemaSnapshot` also has no display metadata. Plan must specify the minimum Host-owned snapshot path before implementation. |
| MiMo F004: terminal events need `event_class` / `event_type` tests | accepted | Plan requires terminal `HostEvent` identity but Slice A tests should explicitly verify succeeded/failed/cancelled/lost terminal events carry identity. |
| MiMo F005: Service DTO field source unclear | accepted | Plan should clarify `run_id`, `event_sequence`, and `dedupe_key` come from public `HostEvent`, while UI semantics come from `HostEvent.activity`; Service must not parse private payload. |
| MiMo F006: external editor edge cases | accepted | Plan should define blank return, launch failure, and cancel behavior for Ctrl+X Ctrl+E. |
| MiMo F007: `REASONING_DELTA` / `CONTENT_DELTA` projection not deterministic | accepted | Plan must choose a deterministic rule: both keep public identity and `activity=None`; raw deltas are never projected to activity. |
| MiMo F008: prompt_toolkit async compatibility validation | accepted | Plan should require an early Slice D validation or minimal test around prompt_toolkit async/key binding assumptions before broad REPL wiring. |
| MiMo F009: Service README check | deferred-with-owner | AGENTS.md does not require `dayu/service/README.md`; implementation should still check if the file exists and note the decision. This is a docs check, not a plan blocker. |
| DS Finding 2: `event_class` / `event_type` exposure may be misused | accepted-with-modification | Keep fields because user explicitly requested `watch_session_events(session_id)` accurately express event identity and existing `HostEventView` already exposes these public identities. Plan must constrain Service/CLI usage: no UI branching from `event_class`; UI uses `activity.kind/status/title/summary`; `event_class/event_type` are identity/diagnostic labels. |
| DS Finding 3: cancel terminal race undefined | accepted | Plan must define CANCELLING + terminal arrival transition and tests for terminal-before-cancel and cancel-before-terminal orderings. |
| DS Finding 4: `HostActivityCounts` too loose | accepted | Plan should define the exact first-version fields: `total`, `completed`, `failed`, `cancelled`, all non-negative ints. |
| DS Finding 5: non-TTY Ctrl key behavior unclear | accepted | Plan should separate TTY key bindings from non-TTY SIGINT behavior. |
| DS Finding 6: cross-slice state machine tests | accepted | Plan should require shared state transition helper or explicit cross-slice integration tests, without over-abstracting. |

## Required Plan Fixes

AgentCodex must update the plan artifact to:

1. Clarify reuse of existing `HostEventClass` values.
2. Clarify `event_type` copies EventLog row `event_type`.
3. Specify Host-owned tool display snapshot path: extend `USER_INPUT_ACCEPTED.effective_tool_set` with a selected-tool display mapping built in Host admission from `ToolBundle.definitions`; `read_api` looks it up by run/input payload and falls back to stable `tool_name`.
4. Clarify Service/CLI must not use `event_class` for UI branching.
5. Define `HostActivityCounts` first-version fields.
6. Define deterministic `REASONING_DELTA` / `CONTENT_DELTA` behavior as `activity=None`.
7. Add terminal identity tests.
8. Add cancel race state transition and tests.
9. Add external editor edge behavior.
10. Add prompt_toolkit early compatibility validation.
11. Add non-TTY key/SIGINT distinction.
12. Add cross-slice state-machine integration validation.

## Next Gate

Proceed to plan fix by AgentCodex, then re-review by AgentMiMo / AgentDS.
