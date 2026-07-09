# WU-SEMANTIC-OWNERSHIP-01 P2-B S2 implementation controller validation

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01`
- Sub WU / slice: `P2-B S2`
- Gate: implementation controller validation before code review
- Design truth:
  - `docs/host/design.md`
  - `docs/engine/design.md`
- Control truth:
  - `docs/host/issues-implementation-control.md`
- Agent implementation artifact:
  - `docs/reviews/wu-semantic-ownership-01-p2-b-s2-implementation-codex.md`

## Motivation and root cause

The accepted finding is real: descriptor-backed successful Run terminal answers were resolved for memory continuity by mutating the payload mapping seen by the memory consumer. That made a descriptor/artifact-derived answer look as if it came from the EventLog hot payload field `final_answer`.

This is a semantic ownership bug. The canonical terminal fact, payload descriptor, and terminal artifact own the durable answer material. Memory projection and RunInputBuilder may resolve that material for LLM-facing continuity, but they must not rewrite the EventLog payload view and must not leak descriptor refs, digests, event ids, cursors, or Host governance labels into LLM-facing messages.

## Owner boundary

- Fact producer: successful Run terminal fact plus optional terminal payload descriptor / artifact.
- Validation: terminal answer resolver validates inline text or digest-checked artifact content.
- Durable projection: Conversation Memory projection consumes projection-internal typed answer material.
- RunInput projection: RunInputBuilder consumes the same resolver output as typed answer material for inline repair / continuity.
- Direct consumer boundary: direct `build_conversation_memory_snapshot_from_events(...)` remains descriptor-blind unless typed material is explicitly supplied.
- LLM-facing output: selected recent window / RunInput assistant messages contain only answer text.

## Controller adjustments

After AgentCodex implementation, controller made narrow cleanup fixes:

- Restored unrelated formatting churn from `dayu/host/memory.py`, `dayu/host/durable/memory.py`, `dayu/host/run_input.py`, `tests/host/test_memory_projection.py`, and `tests/host/test_run_input_builder.py`.
- Kept `MemoryProjectionEvent.assistant_final_answer_text` after the existing evidence fields, preserving positional test call behavior for existing evidence material.
- Added the missing test helpers for descriptor-backed terminal answer seeding and terminal answer internal-ref assertions.
- Confirmed `dayu/host/compact_material.py` and `tests/host/test_compact_material.py` are not modified by this slice.

## Validation

Passed:

```text
source .venv/bin/activate && pytest tests/host/test_memory_projection.py tests/host/test_run_input_builder.py tests/host/test_compact_material.py
205 passed
```

```text
source .venv/bin/activate && pyright
0 errors, 0 warnings, 0 informations
```

```text
git diff --check
pass
```

```text
rg -n "merged\[_PAYLOAD_FIELD_FINAL_ANSWER\]|transient ``final_answer``|_PAYLOAD_FIELD_FINAL_ANSWER|assistant_final_answer_text_from_run_payload" dayu/host/durable/memory.py dayu/host/run_input.py docs/host/design.md
no matches
```

Additional non-S2 smoke:

```text
source .venv/bin/activate && pytest tests/host/test_terminal_payload.py tests/host/test_public_compact_smoke.py
1 failed, 26 passed, 1 skipped
```

Failure:

- `tests/host/test_public_compact_smoke.py::test_post_compaction_fact_reuse_uses_raw_accepted_tool_evidence`
- Error path: accepted tool evidence delta block construction raises `TypeError: RunInputMaterialBlock.readable_source_text must be str`.
- Controller classification: accepted as an independent umbrella residual. The failure is in accepted tool evidence compact material source projection, not in terminal answer continuity projection. It should be handled as a follow-up sub WU before umbrella closeout, not hidden inside P2-B S2.

## Propagation audit

- Producer: EventLog `RUN_SUCCEEDED` payload and optional terminal summary descriptor remain unchanged.
- Resolver: `assistant_final_answer_continuity_text(...)` resolves inline final answer or digest-checked terminal artifact content.
- Durable memory projection: passes resolver output through `MemoryProjectionEvent.assistant_final_answer_text`; it no longer merges a synthetic `final_answer` into the payload view.
- RunInputBuilder inline repair: computes the same typed answer material and passes it to `MemoryProjectionEvent`; it no longer mutates payload with a synthetic `final_answer`.
- Direct memory consumer: descriptor-blind behavior is preserved without typed material.
- LLM-facing selected recent window and RunInput assistant messages contain the answer text only and are covered by no-internal-ref assertions.

## Docs / README

Updated:

- `docs/host/design.md`: terminal answer continuity truth and projection constraints.
- `dayu/host/README.md`: Host developer-facing terminal answer continuity contract.
- `tests/README.md`: coverage boundary for typed terminal answer material and cross-path equivalence.

No `docs/engine/design.md` update was needed because this slice changes Host projection semantics, not Engine contracts.

## Controller decision

Ready for P2-B S2 implementation code review by AgentMiMo and AgentDS.

Residual carried outside this slice:

- Accepted tool evidence compact material may produce non-string `readable_source_text`; owner boundary appears to be accepted evidence material projection / compact material source, not terminal answer continuity.
