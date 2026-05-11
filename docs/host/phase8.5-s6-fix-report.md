# P8.5 Slice 6 Fix Report

## Gate

- work gate name: `fix`
- work-unit name: P8.5 — P8 Stabilization / ToolRuntime Event Model
- assigned slice id: Slice 6 — Documentation / Migration Registry Closeout
- source review artifact: `docs/host/phase8.5-s6-code-review.md`
- accepted finding ids: `S6-CR-01`, `S6-CR-02`
- artifact path: `docs/host/phase8.5-s6-fix-report.md`

## Finding Status

| Finding | Status | Fix |
| --- | --- | --- |
| `S6-CR-01` | fixed | Updated Engine explicit field/export tests to accept the current Slice 4 contract: `ProviderProtocolErrorData` and `RunnerProtocolErrorData` include `partial_tool_calls`, and `dayu.engine.__all__` exports `PartialToolCallSummary`. Added a boundary assertion that `PartialToolCallSummary` does not expose raw `arguments`. |
| `S6-CR-02` | fixed | Split the migration registry residual into a completed provider protocol error row and a separately owned transport-layer read failure row. The remaining transport-layer provider adapter coverage is `deferred-with-owner` to `P16 interface freeze`, the closest existing phase for Engine / Host contract freeze and provider adapter coverage recheck. |

## Changed Files

- `tests/engine/test_metadata_boundary.py`
- `tests/engine/test_package_exports.py`
- `docs/host/migration-plan.md`
- `tests/README.md`
- `docs/host/phase8.5-s6-fix-report.md`

## Validation

```bash
source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
```

Result: passed, `0 errors, 0 warnings, 0 informations`.

```bash
source .venv/bin/activate && pytest tests/contracts tests/engine -q
```

Result: passed, `327 passed in 1.10s`.

```bash
source .venv/bin/activate && pytest tests/host -q
```

Result: passed, `376 passed in 2.71s`.

```bash
rg "TOOL_FETCH_MORE|TOOL_CURSOR_|TOOL_RESULT_TRUNCATED|ToolFetchMore|ToolCursor.*Data|ToolResultTruncatedData" dayu tests dayu/host/README.md tests/README.md
```

Result: expected guard-only matches in Host public API / boundary negative tests; no production code or current README surface match.

```bash
rg "TOOL_FETCH_MORE|TOOL_CURSOR_|TOOL_RESULT_TRUNCATED|ToolFetchMore|ToolCursor.*Data|ToolResultTruncatedData" docs/host/migration-plan.md docs/host/phase8.5-plan.md
```

Result: expected matches in P8.5 plan guard / historical evidence and migration registry historical rows.

```bash
git diff --check
```

Result: passed.

## Risk And Open Questions

- new risk introduced: no.
- new open question introduced: no.
- plan deviation: no.
- residual risk classification: low; the only remaining uncovered transport-layer provider adapter behavior is explicitly assigned to `P16 interface freeze`.
