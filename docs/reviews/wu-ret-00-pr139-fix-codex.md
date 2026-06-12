# WU-RET-00 PR 139 Review Fix - Codex

## Scope

- Gate: PR review fix
- Input review artifacts:
  - `docs/reviews/wu-ret-00-pr139-review-mimo.md`
  - `docs/reviews/wu-ret-00-pr139-review-ds.md`
- Scope boundary: only accepted test coverage and control document status findings were fixed. Production behavior was not changed.

## Changed Files

- `tests/host/test_storage_maintenance.py`
- `tests/host/test_storage_orphan_proof.py`
- `docs/host/issues-implementation-control.md`
- `docs/reviews/wu-ret-00-pr139-fix-codex.md`

`tests/README.md` was read before modifying tests. Its Host testing section already describes storage usage, orphan proof, storage maintenance, recheck, file error, async handle, closed handle, and json coverage responsibilities; this fix only extends existing Host storage tests and does not add a new test layer, command, or maintenance rule, so no README change was needed.

## Accepted Findings Fixed

### MiMo Finding 1

Added public-facade recheck integration coverage in `test_storage_maintenance_reclaim_recheck_hit_skips_delete`.

The test now enters through `run_storage_maintenance()` with `reclaim_orphan_artifacts=True`. A controlled monkeypatch writes a new descriptor after `scan_orphan_artifact_files()` returns candidates and before per-file reclaim recheck runs. The assertion verifies that the candidate remains reported, the file is not deleted, no file error is produced, and the descriptor is visible through the public maintenance recheck path.

### MiMo Finding 2

Added `test_storage_maintenance_recheck_durable_error_fails_safe`.

The test triggers a durable-layer failure from the recheck operation used by the public facade. It verifies the public API fail-safe behavior: the operation raises `HostApiError(INTERNAL_ERROR)` with a `HostDurableError` cause and the candidate file remains on disk. This proves the failure is not swallowed as a per-file deletion diagnostic.

### MiMo Finding 3

Added boundary rejection tests in `tests/host/test_storage_orphan_proof.py`:

- `test_scan_orphan_artifact_files_rejects_negative_grace_seconds`
- `test_scan_orphan_artifact_files_rejects_naive_datetime`

These cover the explicit `ValueError` guards for negative `grace_seconds` and naive `datetime` inputs.

### MiMo Finding 4

Updated `docs/host/issues-implementation-control.md` Work Units table:

- `WU-RET-00`: `planning` -> `ready-to-open-draft-PR`

This now matches the current-state table and WU-RET-00 readiness notes in the same control document.

### MiMo Finding 8

Added `test_storage_maintenance_result_json_value_is_stable_self_explaining_and_non_negative`.

The test locks the `HostStorageMaintenanceResult.json_value()` top-level keys, verifies nested `usage` structure, checks non-negative physical artifact bytes, and confirms candidate/reclaimed/file-error/checkpoint fields use stable JSON shapes.

## Validation

```bash
source .venv/bin/activate && pytest tests/host/test_storage_maintenance.py tests/host/test_storage_orphan_proof.py -q
```

Result:

```text
18 passed in 0.38s
```

```bash
source .venv/bin/activate && pyright tests/host/test_storage_maintenance.py tests/host/test_storage_orphan_proof.py
```

Result:

```text
0 errors, 0 warnings, 0 informations
```

## Not Covered / Deferred

- DS async event-loop synchronous I/O finding remains deferred by current WU instruction.
- `DEFAULT_ORPHAN_ARTIFACT_GRACE_SECONDS` package-root export was not added by current WU instruction.
- Plan field naming, facade aggregation re-export, and duplicate private validators were not changed by current WU instruction.
- No production behavior, schema, public API, or README content was changed.
