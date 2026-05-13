# Gateflow Plan Fix: Host Phase 1 Public Contract And Runtime

- **work gate name**: fix
- **work-unit name**: Host Phase 1 公共契约与 runtime 基础设施
- **current gate**: plan fix
- **approved plan path**: `docs/host/phase1-public-contract-runtime-plan.md`
- **controller adjudication path**: `docs/reviews/gateflow-plan-review-host-p1-public-contract-runtime-controller-adjudication-20260513.md`
- **artifact path**: `docs/reviews/gateflow-plan-fix-host-p1-public-contract-runtime-codex-20260513.md`

## Source Review Artifact Paths

- `docs/reviews/gateflow-plan-review-host-p1-public-contract-runtime-mimo-20260513.md`
- `docs/reviews/gateflow-plan-review-host-p1-public-contract-runtime-ds-20260513.md`

## Accepted Finding IDs

- M1
- M2
- M3
- M4
- D1
- D2
- D3
- D4

## Per-Finding Fix Status

| Finding | Status | Fix summary |
|---|---|---|
| M1 | fixed | `LaneClaimToken` public shape now uses `async def refresh(self) -> None` and `async def release(self) -> None`. |
| M2 | fixed | Coordinator / DB decisions and Slice 2 instructions require `PRAGMA journal_mode=WAL` during runtime lane DB initialization and state that it does not affect Host durable store policy. |
| M3 | fixed | Allowed files and Documentation Update Decision now require a minimal `dayu/runtime/__init__.py` docstring update and prohibit package-root lane / filelock re-export. |
| M4 | fixed | Slice 2 / Slice 3 tests now state that `tests/runtime/test_import_boundary.py` covers new `lane.py` / `filelock.py`, and that third-party `filelock` is allowed only in `dayu.runtime.filelock`. |
| D1 | fixed | Claim / release semantics and Slice 2 instructions now require stale cleanup, active count and insert to happen in the same SQLite transaction on successful acquire. |
| D2 | fixed | Slice 2 multi-process test instructions now require the parent process to create the DB path with `tmp_path` or `tempfile` and pass it to subprocesses by CLI argument or environment variable. |
| D3 | fixed | Coordinator / DB decisions and Slice 2 instructions now define `owner=None` defaults as `secrets.token_hex(8)`, `os.getpid()` and `process_start_token=None`, with explicit caller override allowed. |
| D4 | fixed | Public API and Slice 2 instructions now define `LaneAcquireOutcome` as a `typing.TypeAlias` for `LaneAcquired | LaneAcquireCancelled | LaneAcquireTimedOut`, with no new dataclass. |

## Changed Files

- `docs/host/phase1-public-contract-runtime-plan.md`
- `docs/reviews/gateflow-plan-review-host-p1-public-contract-runtime-mimo-20260513.md`
- `docs/reviews/gateflow-plan-review-host-p1-public-contract-runtime-ds-20260513.md`
- `docs/reviews/gateflow-plan-fix-host-p1-public-contract-runtime-codex-20260513.md`

## Validation Commands And Results

- `git diff --check`: PASS.
- Pyright was not run, per handoff instruction.
- Tests were not run because this fix only changes plan/review documentation and the handoff explicitly requested `git diff --check`.

## Finding Title Status Update Result

- `docs/reviews/gateflow-plan-review-host-p1-public-contract-runtime-mimo-20260513.md`: M1-M4 status lines changed from `未修复` to `已修复`; each `Controller decision status` changed to `accepted-fixed-by-codex-20260513`.
- `docs/reviews/gateflow-plan-review-host-p1-public-contract-runtime-ds-20260513.md`: D1-D4 status lines changed from `未修复` to `已修复`; each `Controller decision status` changed to `accepted-fixed-by-codex-20260513`.
- Finding headings were not edited because these two source review artifacts used `### Finding N: ...` headings without an embedded Gateflow status word. The status说明 lines were the artifact-local status mechanism, so updating those lines satisfies the requested state transition without rewriting heading semantics.

## New Risks Or Open Questions

- New risks introduced: none.
- New open questions introduced: none.
- Plan deviation: none; all edits are limited to controller-accepted findings M1-M4 and D1-D4.
- Blocking questions count: 0.

## Residual Risk Classification

- Residual risk classification: low.
- Rationale: this pass only clarifies plan handoff semantics and review artifact status. It does not change production code, schema, runtime behavior or implementation scope.
- Remaining residual risk: later implementation and re-review must verify that the eventual code follows the clarified WAL, transaction, owner and import-boundary requirements.
