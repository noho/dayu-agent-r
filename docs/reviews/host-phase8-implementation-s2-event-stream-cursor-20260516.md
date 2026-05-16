# Host Phase 8 P8-S2 Implementation Artifact

- **gate**: P8-S2 implementation
- **work-unit**: Host Phase 8 Projection Core Event Stream
- **slice**: P8-S2 Host Event Stream Cursor Truth / Fanout Boundary
- **approved plan**: `docs/host/phase8-projection-core-event-stream-plan.md`
- **baseline**: P8-S1 accepted slice commit `80c12a2`
- **branch**: `feat/host-phase8-projection-core-event-stream`
- **artifact path**: `docs/reviews/host-phase8-implementation-s2-event-stream-cursor-20260516.md`

## Scope And Non-Goals

Allowed files were limited to `dayu/host/read_api.py`,
`tests/host/test_public_event_stream.py`, `tests/host/test_import_boundary.py`,
`tests/host/test_weak_typing_guard.py`, optional `dayu/host/README.md`, and this
artifact. Implementation stayed within test and artifact files.

No fanout, wakeup, notification shell, repair helper, public `HostEventStream`
shape change, Engine/runtime/service/UI/Fins change, command path change,
projection runner change, schema change, plan/control-doc change, commit, push,
PR, or review was performed.

## Motivation Check

The production implementation in `dayu/host/read_api.py` already uses
`read_events_after(transaction, cursor.event_sequence, limit=...)` and builds
`HostStreamCursor` from the last scanned EventLog row. It does not import
projection, durable projection, fanout, notification, or repair modules.

Therefore the S2 problem was not a production logic bug in the current branch.
The real gap was regression coverage: future work could accidentally make
`stream_run_events` depend on projection checkpoint, projection failure state,
fanout offsets, or repair side effects. This slice strengthens tests around
that boundary.

## Changed Files

- `tests/host/test_public_event_stream.py`
  - Added projection table interference helpers that write checkpoint/failure
    rows directly through SQLite using schema table constants.
  - Added coverage proving a lagged projection checkpoint does not affect
    returned stream events or `next_cursor`.
  - Added coverage proving an existing projection failure row does not affect
    returned stream events or scan-window cursor advancement.
  - Added coverage proving `stream_run_events` does not advance checkpoint,
    clear/repair failure rows, or otherwise write projection tables.
- `tests/host/test_import_boundary.py`
  - Added read API boundary coverage forbidding `read_api.py` from importing
    projection/fanout/notification/read-model truth modules or referencing
    projection/fanout/repair truth tokens.

## Implemented Plan Items

- Preserved `stream_run_events(host, run_id, cursor, limit)` public shape and
  existing EventLog-backed semantics.
- Proved projection checkpoint lag is not stream truth.
- Proved projection failure rows are not stream truth.
- Proved stream correctness does not depend on projection/fanout/repair
  side effects.
- Proved stream reads do not write projection checkpoint/failure tables.

## Validation

```text
source .venv/bin/activate && pytest tests/host/test_public_event_stream.py tests/host/test_import_boundary.py tests/host/test_weak_typing_guard.py -q
```

Result: passed, `18 passed in 0.62s`.

```text
source .venv/bin/activate && python -m pyright dayu/host tests/host
```

Result: passed, `0 errors, 0 warnings, 0 informations`.

```text
git diff --check
```

Result: passed.

## Docs Decision

No README update was made. `dayu/host/README.md` already states that
`stream_run_events` scans global EventLog `event_sequence` and does not read
projection checkpoint, memory state, outbox state, in-memory subscription
position, session-local cursor, or client sequence. The current S2 changes only
add regression tests for that existing boundary.

## Plan Gaps

No blocking plan gap was found for S2. The plan's stop conditions did not
trigger: no projection cursor replacement, Service/UI delivery state, or fanout
shell was needed.

## Residual Risk Classification

- Future approved fanout/wakeup work could still accidentally couple stream
  correctness to notification state. Owner: later fanout/wakeup slice; current
  S2 adds import/token boundary tests to catch that at read API level.
- P8-S3 repair implementation is not present in this slice by design. Owner:
  P8-S3 Minimal RunResult / Session Timeline Read Model / Repair.

## Completion Status

Implementation complete for P8-S2. Stopped after implementation artifact and
summary as requested. No review, commit, push, PR, or further gate transition
was started.
