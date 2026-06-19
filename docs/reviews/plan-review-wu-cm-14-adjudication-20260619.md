# WU-CM-14 Plan Review Adjudication

## Metadata

- Date: 2026-06-19
- Work unit: WU-CM-14 Recent Final Answer Preservation for Ordinal Follow-ups
- Plan artifact: `docs/host/host-issues/wu-cm-14-protected-recent-floor-plan.md`
- Plan reviews:
  - `docs/reviews/plan-review-wu-cm-14-mimo.md`
  - `docs/reviews/plan-review-wu-cm-14-ds.md`
- Plan re-reviews:
  - `docs/reviews/plan-rereview-wu-cm-14-mimo.md`
  - `docs/reviews/plan-rereview-wu-cm-14-ds.md`
- Verdict: PASS after fix and re-review

## Controller Adjudication

The original AgentCodex plan correctly established that WU-CM-14 is real and scoped to protected recent raw tail preservation across compact boundaries. AgentMiMo returned PASS with non-blocking findings. AgentDS returned conditional PASS with three HIGH findings that had to be fixed before implementation.

Controller accepted the DS HIGH findings and related MEDIUM findings, then sent AgentCodex through plan fix. AgentCodex updated the plan. Both AgentMiMo and AgentDS re-reviewed the fixed plan and returned PASS.

The plan is now code-generation-ready.

## Finding Adjudication

| Finding | Source | Severity | Controller verdict | Re-review status |
|---|---|---:|---|---|
| Provider / transaction access for ordinary RunInput raw tail rendering was underspecified | AgentDS H1 | HIGH | accepted | closed |
| Post-compaction activation condition was imprecise | AgentDS H2 / AgentMiMo F-04 | HIGH / LOW | accepted | closed |
| Reactive compact-success / fallback coverage did not meet control-doc acceptance signal | AgentDS H3 / AgentMiMo F-01 | HIGH / LOW | accepted | closed |
| `tests/host/test_compaction_operation.py` was listed without a required test | AgentDS M1 | MEDIUM | accepted | closed |
| Duplicate risk between memory selected recent window and EventLog raw tail was not handled | AgentDS M2 | MEDIUM | accepted | closed |
| Reactive frozen material repair stop condition was too vague | AgentDS M3 / AgentMiMo F-03 | MEDIUM | accepted | closed |
| `USER_VISIBLE_RUN_STATE` may not exist | AgentMiMo F-02 | LOW | accepted as implementation discovery item | no change required |

## Accepted Plan Constraints

- Reuse existing `MemoryProjectionPolicy.selected_recent_window_turn_floor` and protected recent floor.
- Do not add a WU-CM-14-specific floor, ordinal follow-up parser, prompt-pattern-specific retention, memory kind, public API, schema, or EventLog event type.
- Add module-private protected recent raw tail provider/view in `dayu/host/run_input.py`; `RunInputBuilder.build()` must not directly bypass provider boundaries to read durable storage.
- Activate ordinary raw-tail rendering only for current-run accepted compact artifact with `fallback is None`; fallback rendering remains owned by the fallback path.
- Add dedupe between memory selected recent window and EventLog-backed raw tail.
- Cover proactive compact-success, reactive compact-success, proactive fallback, reactive fallback, reactive frozen material assembly, duplicate prevention, current input anchor non-duplication, and negative LLM-facing internal-ref assertions.
- If implementation discovers reactive compact-success does not reach ordinary `RunInputBuilder.build()`, stop and raise a blocking question with direct state-machine evidence.

## Residual Risks

| ID | Risk | Owner | Controller verdict |
|---|---|---|---|
| WU-CM-14-RR-1 | Full reactive "freeze exact overflow ordinary material list" convergence remains broader than WU-CM-14. | WU-CM-13 | deferred-with-owner |
| WU-CM-14-RR-2 | `USER_VISIBLE_RUN_STATE` material kind may not exist. | WU-CM-14 implementation | accepted discovery item |
| WU-CM-14-RR-3 | EventLog double-read in protected recent raw tail provider may add dispatch-path overhead. | WU-CM-14 implementation / WU-CM-13 audit | accepted for WU-CM-14; revisit during WU-CM-13 if needed |

## Validation

- AgentCodex plan validation: `git diff --check -- docs/host/host-issues/wu-cm-14-protected-recent-floor-plan.md` passed.
- AgentMiMo review validation: `git diff --check -- docs/reviews/plan-review-wu-cm-14-mimo.md` passed.
- AgentDS review validation: `git diff --check -- docs/reviews/plan-review-wu-cm-14-ds.md` passed.
- AgentMiMo re-review validation: `git diff --check -- docs/reviews/plan-rereview-wu-cm-14-mimo.md` passed.
- AgentDS re-review validation: `git diff --check -- docs/reviews/plan-rereview-wu-cm-14-ds.md` passed.

## Final Verdict

PASS. WU-CM-14 may proceed to accepted plan commit and then implementation gate.
