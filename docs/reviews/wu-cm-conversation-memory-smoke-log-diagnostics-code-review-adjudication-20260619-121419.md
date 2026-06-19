# Code Review Adjudication and Fix

## Gate

- Gate: code review / fix
- Work unit: Conversation Memory smoke/log diagnostics and smoke coverage boundary
- Implementation artifact: `docs/reviews/wu-cm-conversation-memory-smoke-log-diagnostics-implementation-20260619-120929.md`
- Reviews:
  - AgentDS: `docs/reviews/code-review-20260619-121033.md`
  - AgentMiMo: `docs/reviews/code-review-20260619-121125.md`

## Finding Decisions

### Mimo-1: unused `TextIOWrapper` import

- Status: accepted
- Fix: removed unused import from `utils/smoke_host_public_conversation_memory_scenarios.py`.

### Mimo-2: `_compact_pressure_reserve_tokens` branches return identical value

- Status: rejected-with-reason
- Reason: this branch predates the current clean baseline and is unrelated to smoke/log diagnostics. Changing compact pressure sizing is outside this work unit.
- Residual risk: pre-existing maintainability issue, not introduced by this slice.

### Mimo-3: `CompactOperationAudit` docstring missing fields

- Status: rejected-with-reason
- Reason: the current implementation already documents `request_event_sequence`, `run_id`, `compacted_event_sequences` and `failed_events`.

### DS-1: `_print_round()` / `_print_session_observation()` / assembly diagnostics lack `flush=True`

- Status: accepted
- Fix: added `flush=True` to assembly diagnostics, compact pressure summary, round done, final preview and session observation prints.

### DS-2: `_compact_payload_int()` does not mention JSON floats

- Status: accepted
- Fix: docstring now explicitly states JSON floats are treated as type mismatch and return `None`.

### DS-3: per-operation failure / diagnostic histograms not printed

- Status: deferred-with-owner
- Owner: later smoke diagnostics enhancement if operation-local histogram proves necessary.
- Reason: current work unit requires per-operation timeline and global attempt reject histogram. Per-operation histograms are retained in `CompactOperationAudit` for future printing but not required for current acceptance.

### DS-4: `_compact_artifact_files()` recursive `rglob("*")`

- Status: rejected-with-reason
- Reason: pre-existing helper behavior and not introduced by this work unit. Changing artifact discovery semantics could alter existing smoke acceptance outside the requested scope.

### DS-5: `main()` does not print traceback

- Status: rejected-with-reason
- Reason: out of scope. Current work unit only requires failure line separation and hard-fail visibility; traceback policy is a broader CLI/logging behavior decision.

## Fix Validation Plan

Run:

```bash
source .venv/bin/activate && pytest tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py
source .venv/bin/activate && pyright utils/smoke_host_public_conversation_memory_scenarios.py tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py
```

## Residual Risks

- Production memory compact failure remains later work.
- Long25 real-LLM smoke has not been run in this gate.
- Pre-existing compact pressure reserve branch and artifact recursive scan remain intentionally unchanged.
