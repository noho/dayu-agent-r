# WU-SEMANTIC-OWNERSHIP-01 P3-C S1 Controller Validation

## Scope

- Accepted plan: `0dcef803`.
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-p3-c-s1-implementation-codex.md`.
- Production scope: compact semantic parser, canonical validation delegation, Conversation Memory typed projection, durable/inline-repair adapters, enum codecs/rendering.

## Controller Adjudication

The implementation motivation and owner boundary are confirmed against current code. The production writer persists `ConversationCompactOutputVNext.to_json()`, so strict reconstruction at `compact_payload` is the correct read owner. Keeping string compatibility in Memory would violate the design and AGENTS.md.

The test-only scope extension to `tests/host/memory_snapshot_factories.py` and `tests/host/test_compact_material.py` is accepted. It only migrates direct constructors/assertions to the strict enum contract; no S2 previous-view, pair, renderer, or budget behavior was implemented.

## Independent Validation

```text
focused affected matrix: 255 passed
full pyright: 0 errors, 0 warnings
import/weak typing guards: 25 passed
git diff --check: pass
```

AgentCodex reported per-file coverage gates:

- `compact_payload.py`: 80%
- `context_events.py`: 93%
- `memory.py`: 92%
- `durable/memory.py`: 86%
- `run_input.py`: 88%

## Propagation Audit

The current propagation path is single-source:

```text
ConversationCompactOutputVNext
  -> canonical CONTEXT_COMPACTED payload and digest
  -> compact_payload strict semantic parser
  -> durable memory / inline repair event adapter
  -> MemoryProjectionEvent typed semantics
  -> Conversation Memory sections and snapshot/table enum values
  -> strict snapshot restore and RunInput memory rendering
```

Invalid persisted candidate or enum values fail before snapshot/checkpoint advancement. Anchor children and ordinal remain typed throughout the tested round trip.

## Gate

- Implementation validation: pass.
- Blocking questions: 0.
- Next gate: parallel S1 code review by AgentMiMo and AgentDS.
