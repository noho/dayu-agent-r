# WU-CLI-FINS-OBS-01 Plan Review Adjudication

## Scope

- Work unit: `WU-CLI-FINS-OBS-01`
- Gate: plan review adjudication
- Plan: `docs/host/wu-cli-fins-obs-01-fins-direct-live-events-plan.md`
- Reviews:
  - `docs/reviews/plan-review-20260615-154655.md` (AgentDS)
  - `docs/reviews/plan-review-20260615-180157.md` (AgentMiMo)

## Decision Summary

Plan review does not fail the work unit direction. Both reviewers agree the motivation, Host / Engine / Fins stream boundary, CLI-as-UI-consumer boundary, and prompt / interactive non-goal decision are sound.

The plan is not ready for implementation until accepted findings below are fixed in the plan artifact.

## Finding Adjudication

| Finding | Decision | Reason | Required Plan Fix |
|---|---|---|---|
| DS-001 / MiMo-001: S2 async/sync boundary not resolved | accepted | Current plan asks synchronous ingestion adapters to consume async pipeline streams without choosing a threading/event-loop strategy. This would force the implementation agent to redesign runtime execution. | Change S2 to the lower-risk path: do not change adapter protocols in this work unit. Emit coarse progress from `FinsIngestionRuntime` around existing synchronous adapter/runner calls and in existing preprocess loops. Fine-grained async pipeline event consumption is deferred unless explicitly re-scoped. |
| DS-002 / MiMo-002: adapter protocol breaking-change blast radius | accepted | Adding mandatory `event_sink` to adapter protocols is unnecessary if S2 uses runtime-owned coarse progress; otherwise it would require complete implementation/test substitute inventory. | Remove mandatory adapter protocol changes from this plan. If any protocol change remains, list every concrete implementer and test double. |
| DS-003 / MiMo-003: progress event failure should not fail job | accepted | Progress events are observability/UI signals, not business terminal truth. Letting progress write failure mark the job failed would corrupt user-visible business state. | State that non-terminal progress event append failure logs bounded WARN diagnostics and continues. Terminal job record remains truth. Terminal event append failure also warns and terminal fallback remains available. |
| MiMo-004: sidecar file locking underspecified | accepted | Event sidecar sequence allocation and terminal/event race behavior need one clear store locking rule. | Specify that event sidecar append/read sequence allocation uses the same `FsFinsIngestionJobStore` runtime file lock as job record operations, unless implementation evidence proves a narrower lock is safe and tested. |
| DS-004 / MiMo-005: Service event poll interval unspecified | accepted | Poll interval affects CPU and user-visible progress latency. It must not be left to implementation guesswork. | State that `stream_job_events_until_terminal` reuses `FinsDirectCommandService.poll_interval_seconds` and sleeps after empty reads; tests must prove no tight loop. |
| DS-005 / MiMo-006: log assembly should reuse helper | accepted | `dayu.runtime.log.set_level_from_flags` already owns CLI log-level precedence. Reimplementing mapping in `main.py` creates drift risk. | Update S5 to call the existing runtime helper rather than manually mapping strings. |
| DS-006 / MiMo-007: synthesized terminal event should warn | accepted | Terminal fallback is needed to avoid UI hangs, but silent fallback hides event-production bugs. | Require a bounded WARN log when Service synthesizes terminal event from terminal job record without seeing a terminal event sidecar entry. |
| MiMo-008: event type enum mixes status and observation events | accepted | The risk is maintainability rather than correctness. The implementation should not blur status transitions with observation-only events. | Clarify event type semantics in the plan. A single enum is acceptable if docstrings/helpers distinguish status events from observation/progress events; splitting enums is optional, not required. |

## Deferred Risks

| Risk | Decision | Owner / Destination |
|---|---|---|
| Long-term `.events.jsonl` retention / compaction | deferred-with-owner | Future Fins job storage retention work unit; not required for current live UI restoration. |
| Prompt / interactive token/content streaming expectation | deferred-with-owner | Future Agent command streaming/UI work unit; current work unit only protects terminal output and CLI log assembly. |
| Fine-grained pipeline stream consumption | deferred-with-owner | Future Fins pipeline live-event refinement if coarse runtime progress is insufficient after implementation validation. |

## Open Questions

None blocking after accepted plan fixes. The async adapter question is resolved for this work unit by requiring runtime-owned coarse progress and deferring adapter async conversion.

## Conclusion

Plan review gate proceeds to `fix`. AgentCodex must update only the plan artifact to incorporate accepted findings. No production code, tests, README, commit, push, or PR is allowed in the plan fix gate.
