# P10.5 Slice 1 Implementation Artifact

## Gate

- Work unit: Phase 10.5 Ordinary Local Multi-turn Public Contract Freeze
- Gate: P10.5 implementation Slice 1
- Slice: Public Opener Types, Export Boundary And Options
- Agent: Codex implementation specialist
- Date: 2026-05-18

## Changed Files

- `dayu/host/api.py`
- `dayu/host/open_host.py`
- `dayu/host/__init__.py`
- `tests/host/test_public_open_host_options.py`
- `tests/host/test_package_exports.py`
- `dayu/host/README.md`

## Implemented Plan Items

- Added frozen slots dataclasses:
  - `OrdinaryRunExecutionBaseline`
  - `CompactorExecutionBaseline`
  - `OpenHostOptions`
- Reused existing `HostToolingOptions` as the typed tooling policy shape. No `extra payload`, service locator, profile lookup, `object`, `Any`, or unstructured dict was introduced.
- Added standalone public lifecycle exception `HostClosedError`.
- Added public async handle protocol:
  - `Host`
  - `HostHandle` type alias
- Added public terminal event surface:
  - `HostEventKind`
  - `HostTerminalStatus`
  - `HostFinalAnswerView`
  - `HostEvent`
- Added `dayu.host.open_host.open_host(options)` skeleton as an async context manager. Slice 1 validates the options type and raises `NotImplementedError` on context entry because production composition is owned by later P10.5 slices.
- Adjusted `dayu.host.__all__` Service-facing export boundary:
  - Added `open_host`, opener options, async handle protocol, terminal HostEvent types, and `HostClosedError`.
  - Removed `HostCommandHandle`, `create_host_command_handle`, `HostLocalExecutionOptions`, `HostEventView`, `HostEventStream`, `start_run`, and `stream_run_events` from Service-facing `__all__`.
  - Kept low-level symbols available through internal module paths; existing package module attributes were not deleted to avoid unrelated low-level test churn in this slice.
- Kept `_start_run` internal; no compatibility re-export was added.

## Tests And Pyright

- `source .venv/bin/activate && pytest tests/host/test_public_open_host_options.py tests/host/test_package_exports.py -q`
  - Result: passed, `13 passed in 0.18s`
- `source .venv/bin/activate && python -m pyright dayu/host tests/host`
  - Result: passed, `0 errors, 0 warnings, 0 informations`

## Docs Decision

- Updated `dayu/host/README.md` because Slice 1 changed the package-root Service-facing export boundary and the previous README directly described removed low-level entries as package-root public entries.
- The README update is intentionally narrow: it records the current Slice 1 public opener/type boundary and demotes the existing sync command handle/run-level stream wording to low-level module paths. It does not document Slice 2 runtime wiring, live fanout, scheduler composition, compactor behavior, or smoke matrix behavior.

## Residual Risks And Open Questions

- `open_host(options)` is only a contract skeleton in this slice and intentionally raises `NotImplementedError` on context entry. Runtime composition remains Slice 2 scope.
- `Host` / `HostHandle` is a Protocol only. No production concrete handle exists in Slice 1.
- Closed-handle method behavior is not implemented because no concrete skeletal closed handle was introduced in this slice. `HostClosedError` is available for Slice 2 lifecycle handling.
- Existing low-level command functions and diagnostic stream types remain importable from their internal modules. They are removed from `dayu.host.__all__` but not physically deleted from implementation modules.
- Package module attributes for some legacy low-level names remain present because broad test import migration is outside this slice's allowed test file set. Service-facing star import / `__all__` no longer exposes them.

## Stop Status

Slice 1 implementation is complete. No Slice 2 runtime wiring, scheduler composition, command wakeup, live fanout, Session wrappers, compactor wiring, ToolRuntime behavior, Engine contract change, schema change, commit, push, or PR action was performed.
