# P12.6 Design Refinement Controller Artifact

## Scope

Work unit: Phase 12.6 Conversation Memory Redesign From First-Principles Discussion.

Reviewed truth sources:

- `docs/host/implementation-control.md` Phase 12.6.
- `docs/host/design.md` §24 Conversation Memory and §25 Context Governance.
- `docs/host/conversation-memory-compact-io-first-principles-discussion.md`.

## Motivation Judgment

The motivation is valid. The current failure mode is not a local threshold or truncation problem. It comes from an incorrect
compaction I/O boundary: compactor input can render Host ledger data, current long user input and raw evidence repeatedly, so the
actual compactor prompt can be much larger than the ordinary run input that triggered compaction.

## Design Refinement Summary

`docs/host/design.md` now records these stable P12.6 decisions:

- Conversation Memory no longer has an independent `evidence anchors / tool facts / provenance` memory layer.
- Host provenance remains internal mapping from prompt-local evidence labels to canonical `TOOL_RESULT_ACCEPTED`,
  `TOOL_CALL_REQUESTED`, payload, artifact and locator refs.
- LLM-facing memory receives readable claims, continuity and short evidence refs, not Host ledger keys as semantic input.
- Long-session retention / consolidation is part of memory semantics: pinned state is materialized current state, assumptions and
  open questions merge / resolve / expire, episode summaries roll up, evidence-backed facts use bounded working sets, and minimum
  preserve items are short-lived continuity.
- Compaction request input is a compact material pack, not a Session-start EventLog replay.
- The material pack consists of `stable_input`, `history_input`, `evidence_input` and `current_input_anchor`.
- Prompt-local evidence blocks contain readable query / raw result / source locator plus short labels such as `E1`; Host separately
  maps those labels back to canonical provenance.
- Proactive compact must estimate the real compactor messages and must not produce material substantially larger than the ordinary
  input material that triggered compaction.
- Reactive compact freezes the overflowed ordinary input material list, compresses older prefix first, preserves recent raw turns and
  current input anchor, supports block-based multi-pass compaction, and fails closed after policy limits.
- `CONTEXT_COMPACTED` records evidence-backed fact candidates, minimum preserve candidates and accepted evidence label mapping refs
  rather than the old vague `evidence anchors retained` wording.

## Review Request

Reviewers should judge whether the design refinement:

- satisfies the Phase 12.6 goals and success signals;
- aligns with Host design goals: Host governance truth, EventLog canonical facts, memory as projection / read model, Context
  Governance as orchestrator, and `LLM in the loop` under Host constraints;
- removes the root cause instead of adding local truncation stopgaps;
- avoids overdesign, reverse dependencies, public API drift, Engine changes, Fins/tool-provider leakage and extra payload escape
  hatches;
- is specific enough to support a handoff implementation-ready plan without forcing the planning agent to redesign architecture.

## Controller Stop Condition

This design refinement should not enter plan gate until at least two independent design reviewers pass it or all accepted findings
have been fixed and re-reviewed.
