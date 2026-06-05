# WU-CM-01-F01-S7-R1-S0 Design Contract Sync

## Metadata

- work unit: `WU-CM-01-F01-S7-R1`
- gate: S7-R1-S0 design contract sync
- plan: `docs/host/wu-cm-01-f01-s7-r1-one-system-message-rescope-plan.md`
- plan review adjudication: `docs/reviews/wu-cm-01-f01-s7-r1-plan-review-controller-adjudication.md`
- artifact: `docs/reviews/wu-cm-01-f01-s7-r1-s0-design-sync-codex.md`
- branch: `phaseflow/wu-dur-obs-cm-closeout`

## Changed Files

- `docs/host/design.md`
- `docs/host/issues-implementation-control.md`
- `docs/reviews/wu-cm-01-f01-s7-r1-s0-design-sync-codex.md`

This gate did not modify production code, tests, current red smoke assertions, `dayu/host/run_input.py`, `tests/README.md`, commit, push, or PR state.

## Design Changes

`docs/host/design.md` now defines ordinary public RunInput one-system-message as a hard contract:

- ordinary public RunInputBuilder output sent to Engine / Runner has at most one `system` role message;
- when present, the single system envelope is the first message;
- user / assistant selected recent window material preserves role and relative order;
- selected recent evidence that cannot legally use `tool` role moves into the system envelope;
- compactor proposal calls remain governed by compact I/O boundaries, not this ordinary RunInput contract.

The design now fixes concrete LLM-facing envelope section titles, order, and separators:

1. `Task Instructions`
2. `Execution Guidance`
3. `Conversation Summary`
4. `Verified Evidence and Facts`
5. `Prior Answer Anchors`
6. `Open Follow-up Context`
7. `Reference Continuity`
8. `Recent Evidence`
9. `Resume Guidance`

Section headers use `## <title>`, empty sections are omitted, and adjacent non-empty sections are separated by exactly `\n\n`.

The design also adds:

- an internal ref replacement table for ordinary RunInput LLM-facing material;
- manifest alignment rules requiring `RUNNER_CALL_INPUT_ASSEMBLED` to record normalized final messages;
- public-path vs focused durable manifest verification boundaries;
- boundedness and size sanity rules for system envelope merge;
- Conversation Memory Prompt Assembly rules mapping memory sections to the fixed envelope section titles.

## Review Finding Coverage

| Accepted finding | Coverage |
|---|---|
| 1. Concrete section titles / order / separator | Covered by the fixed nine-section order, exact titles, Markdown header format, and `\n\n` separator contract in `docs/host/design.md`. |
| 2. Selected recent evidence position trade-off | Covered by explicit role-preservation-over-interleaving rule and accepted trade-off statement; future historical `tool` role strategy is left to a later work unit. |
| 3. Internal ref replacement table | Covered for `policy_snapshot_ref`, `tool_call_id`, event ids, payload/artifact refs, digests, cursors, projection metadata, Attempt/execution ledger, scheduler state, and Python/internal type names. |
| 4. Manifest verification boundary | Covered by separating public smoke request / runner message assertions from focused durable manifest tests via manifest recorder or payload resolution helper. |
| 5. Boundedness enforcement / sanity | Covered by merge-only rule, section cap preservation, header/separator overhead sanity, and focused test requirement that merge adds no new business text. |

## Validation

- Ran `git diff --check`: passed.
- Did not run pyright because this gate only changes docs and the user explicitly disallowed production/test changes.
- Did not run tests because this gate changes design/control/review docs only and must not modify current red tests.

## README Decision

No README update was made.

Reason: this gate only changes `docs/host/design.md`, `docs/host/issues-implementation-control.md`, and a review artifact. It does not change CLI usage, configuration entry points, runtime composition, `dayu/host/` production behavior, tests, or project/user workflow. The README trigger rules do not require updating root `README.md`, `dayu/README.md`, `dayu/host/README.md`, or `tests/README.md` for a design-only sync.

## Next Gate

Proceed to S7-R1-S0 review gate before any production `dayu/host/run_input.py` changes.
