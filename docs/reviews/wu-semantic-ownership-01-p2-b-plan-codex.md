# WU-SEMANTIC-OWNERSHIP-01 P2-B Plan Delivery - AgentCodex

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 P2-B Host memory/test contract hardening`
- Gate: planning only
- Plan artifact: `docs/host/wu-semantic-ownership-01-p2-b-plan.md`
- Control doc: `docs/host/issues-implementation-control.md`
- Design sources: `docs/host/design.md`, `docs/engine/design.md`
- Source adjudication: `docs/reviews/fullrepo-semantic-ownership-controller-adjudication.md`
- Non-goals preserved:
  - No production code changes.
  - No tests changed.
  - No README changed.
  - No commit.
  - Did not enter implementation, plan review, code review, or PR gates.

## Preflight

- Branch: `phaseflow/host-issues-control`
- Existing dirty file before this task: `docs/host/issues-implementation-control.md`
- I read the dirty control doc as current controller truth and did not modify it.

## Direct Evidence Checked

| Area | Evidence |
|---|---|
| Controller scope | `docs/host/issues-implementation-control.md:174` records P2-B as current plan entry and lists final-answer artifact hydration, import-boundary relative import gaps, and memory snapshot fixture/sentinel patterns. |
| Source adjudication | `docs/reviews/fullrepo-semantic-ownership-controller-adjudication.md:148-162` accepts MiMo 08 / 09 / 12 and describes expected fix shape. |
| Host owner boundary | `docs/host/design.md:43`, `:51-56`, `:2778-2784`, `:3069-3071`, `:3078`, `:3082`, `:3140` define EventLog truth, memory read model, RunInputBuilder, and LLM-facing projection boundaries. |
| Engine boundary | `docs/engine/design.md:3-7`, `:483` confirm Engine emits events but does not own Host durable truth. |
| MiMo 08 | `dayu/host/durable/memory.py:373-419` mutates a payload view with `_PAYLOAD_FIELD_FINAL_ANSWER`; `dayu/host/run_input.py:3199-3229` has the same pattern; `tests/host/test_memory_projection.py:1063-1175` captures durable adapter hydrate vs direct consumer descriptor-blind behavior; `dayu/host/_terminal_answer.py:1-16` currently documents transient hydration as allowed. |
| MiMo 09 | `tests/host/test_import_boundary.py:180-197` only records `ImportFrom` when `node.level == 0`, so relative imports are out of scope. |
| MiMo 12 | `tests/host/test_compact_material.py:2990-3045` and `tests/host/test_run_input_builder.py:4010` / `:4177` / `:4245` hand-build snapshots; `snapshot_digest="pending"` remains in compact/run-input tests. `tests/host/test_memory_projection.py` uses public builders in some paths and does not currently show the same sentinel concentration. |

## Finding Disposition

| Finding | Current judgment | Reason |
|---|---|---|
| MiMo 08 memory projection hydrates final-answer fallback from artifacts | accepted / design-truth-dependent | The production path still merges resolver output into a transient payload dict. Because `_terminal_answer.py` currently documents this as allowed, implementation must first sync design/module truth. The plan does not require durable schema migration unless implementation proves shared typed resolver material is insufficient. |
| MiMo 09 import-boundary tests miss relative imports | accepted | The AST helper explicitly filters `ImportFrom` to `node.level == 0`; this is a test helper owner bug, not a production import bug. |
| MiMo 12 scattered memory snapshot construction and `"pending"` sentinel | accepted with narrowed evidence | The sentinel remains in compact/run-input tests, while current evidence does not support claiming it is still concentrated in `test_memory_projection.py`. The plan scopes this to shared tests fixture factory plus cross-path equivalence tests. |

## Owner Boundary

- Durable terminal facts: Host EngineEvent Ingest / terminal closeout owns `RUN_SUCCEEDED`, terminal payload descriptor refs, and digest-checked terminal answer continuity source.
- Memory projection read model: Conversation Memory consumes committed EventLog facts and resolver-provided typed material; it must not make mutated payload views look like canonical EventLog truth.
- RunInputBuilder: consumes the same durable facts / memory snapshot / resolver material to build LLM-facing messages; it must not expose refs/digests/governance text.
- Import-boundary tests: `tests/host/test_import_boundary.py` owns the AST scan helper and must cover absolute and relative imports with one source of truth.
- Memory snapshot fixtures: tests-only factory owns snapshot/cursor/digest construction for compact material and RunInputBuilder tests.

## Proposed Slice And Validation Matrix

The plan proposes one implementation slice, `S1. Host Memory/Test Contract Hardening`.

Why one slice:

- All three findings are P2 contract/test hardening.
- The production change is narrowly bounded to terminal answer continuity projection, not a memory redesign.
- Import scanner and fixture cleanup share the same affected Host test matrix.
- More slices would add gate overhead without isolating an independent schema or rollback risk.

Required validation recorded in the plan:

```bash
source .venv/bin/activate && pytest tests/host/test_import_boundary.py
source .venv/bin/activate && pytest tests/host/test_memory_projection.py tests/host/test_run_input_builder.py tests/host/test_compact_material.py
source .venv/bin/activate && pyright
git diff --check
```

Optional broader reviewer validation:

```bash
source .venv/bin/activate && pytest tests/host
```

## Risks / Stop Conditions

- Stop if removing payload mutation requires adding or migrating durable EventLog schema fields.
- Stop if `docs/host/design.md` and `_terminal_answer.py` cannot be aligned without changing Host public terminal contract.
- Stop if relative import resolution cannot be deterministic from file path and package root.
- Stop if shared memory snapshot factory requires production-only test hooks or bypasses digest invariants.
- Stop if cross-path equivalence exposes a real RunInputBuilder vs memory projection semantic conflict outside P2-B.

## README Decision

No README update was made in this planning-only gate.

The plan records future triggers:

- `dayu/host/README.md` must be checked before implementation changes under `dayu/host/`.
- `tests/README.md` must be checked before test helper/test responsibility changes.
- Root `README.md` and `dayu/README.md` are not expected to change unless implementation discovers user-visible workflow or layering/public-contract changes.

## Validation

No production tests or pyright were run because this gate only creates planning artifacts and does not modify code or tests.

Artifact whitespace validation was run after writing:

```bash
git diff --check
git diff --no-index --check /dev/null docs/host/wu-semantic-ownership-01-p2-b-plan.md
git diff --no-index --check /dev/null docs/reviews/wu-semantic-ownership-01-p2-b-plan-codex.md
```

Result: `git diff --check` passed with no output. The two `--no-index --check` commands exited `1` because `/dev/null` differs from each new artifact, but produced no whitespace diagnostics.
