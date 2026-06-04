# WU-CM-01 Slice B Plan Fix Re-review Controller Adjudication

## Metadata

| 项目 | 值 |
|---|---|
| work unit | WU-CM-01 Conversation Memory overall optimization |
| gate | Slice B plan fix re-review adjudication |
| design source | `docs/host/design.md` |
| control doc | `docs/host/issues-implementation-control.md` |
| plan fix artifact | `docs/reviews/wu-cm-01-slice-b-plan-fix-codex.md` |
| re-review artifacts | `docs/reviews/wu-cm-01-slice-b-plan-fix-rereview-mimo.md`; `docs/reviews/wu-cm-01-slice-b-plan-fix-rereview-ds.md` |
| adjudicator | AgentController |
| adjudication date | 2026-06-04 |

## Verdict

The Slice B plan fix direction is correct, but the re-review findings require a small additional plan fix before implementation restarts.

The blocker root cause remains accepted: `engine_ingest.py` is the missing reactive accepted closeout owner. However, the next implementation prompt would still be ambiguous unless the plan also covers the direct `engine_ingest.py` test boundary and the vNext artifact writer strategy.

## Accepted Findings

### A1: `engine_ingest.py` non-closeout old type boundary

- Source: AgentMiMo Finding 01.
- Decision: accepted as plan clarification.
- Required plan change: state that non-closeout old imports / annotations may remain if still used outside the reactive closeout path, and that cleanup is limited to imports / annotations made unused by the reactive closeout migration.

### A2: proactive subsequent run input test ownership

- Source: AgentMiMo Finding 02 and AgentDS residual note.
- Decision: accepted as plan clarification.
- Required plan change: explicitly state that Slice B may adjust `test_multi_turn_proactive_compact_feeds_subsequent_run_input` to assert proactive operation/event closeout only, while moving subsequent RunInputBuilder consumption assertions to Slice D.

### A3: vNext artifact writer strategy

- Source: AgentDS Finding 1 and Finding 3.
- Decision: accepted.
- Required plan change: state that reactive `engine_ingest.py` must not use old `CompactArtifactWriteRequest`; shared vNext artifact JSON / descriptor helpers should live in an allowed shared module, preferably `dayu/host/compact_payload.py`, and be reused by both `dispatch.py` and `engine_ingest.py`.

### A4: direct `engine_ingest.py` tests

- Source: AgentDS Finding 2.
- Decision: accepted.
- Required plan change: add `tests/host/test_engine_ingest_mapping.py` to Slice B allowed tests, limited to reactive compaction closeout / fake compactor vNext migration. This follows the implementation boundary because `engine_ingest.py` is now part of Slice B.

## Deferred Findings

None from this re-review should be deferred as ordinary residual before implementation. All accepted findings are small plan-boundary clarifications.

## Required Next Gate

Send AgentCodex to a narrow plan-fix gate. It must update only `docs/host/wu-cm-01-conversation-memory-plan.md`, `docs/host/issues-implementation-control.md` if artifact indexing needs it, and a new plan-fix artifact. It must not modify production code or tests in this gate.
