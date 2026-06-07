# WU-CM-01 Umbrella Final Closeout

## Scope

- Work unit: `WU-CM-01`
- Gate: final closeout
- GitHub issue: `https://github.com/noho/dayu-agent-r/issues/81`
- Current PR containing final closeout records: `https://github.com/noho/dayu-agent-r/pull/125`

## Closeout Verdict

Passed. `WU-CM-01` is complete and Issue 81 has been closed.

This closeout is performed before PR 125 is merged, following the current Phaseflow definition that final closeout is the last bookkeeping gate before user merge.

## Completed Follow-ups

| Work unit | Status | Evidence |
|---|---|---|
| `WU-CM-01-F01` | completed | Public-path smoke correctness closeout accepted; S7-R1 S1 one-system-message production assembly accepted. |
| `WU-CM-01-F02` | completed | Compact evidence query readability and prompt semantic rewrite accepted. |
| `WU-CM-01-F03` | completed | Final closeout artifact `docs/reviews/wu-cm-01-f03-final-closeout-controller.md`; PR 125 includes implementation and review chain. |
| `WU-CM-01-F04` | completed | Final closeout artifact `docs/reviews/wu-cm-01-f04-final-closeout-controller.md`; PR 124 merged with commit `38bf01b05a26a8f7a6a8f8959abd15f6c8d26d13`. |

## Issue Closure

Closed issues during this closeout:

- Issue 81: `https://github.com/noho/dayu-agent-r/issues/81`
- Issue 117: `https://github.com/noho/dayu-agent-r/issues/117`

Already closed before this closeout:

- Issue 10: `https://github.com/noho/dayu-agent-r/issues/10`
- Issue 63: `https://github.com/noho/dayu-agent-r/issues/63`

Issues intentionally left open because they retain pending follow-up scope:

- Issue 64: native Anthropic / Claude Code gateway adapter-specific request identity scope remains open.
- Issue 70: Tool Trace analyzer umbrella remains open, with issue 119 as a child owner.
- Issue 82 / 97 / 98: WU-TOOLS follow-up umbrella issues remain open because pending WU-TOOLS-01-F01 through F09 work units still own follow-up scope.
- Issue 119 / 120 / 121 / 122: active follow-up owners remain in the control doc.

## Residual Risk Reconciliation

No active residual risk remains owned by `WU-CM-01` or Issue 81.

The active residual risk table still contains only unrelated or deliberately deferred work with explicit owners:

- `WU-ENG-02-S3-R1` -> WU-OBS-00B / Issue 119 under Issue 70.
- `WU-TOOLS-01-S4-R1` -> WU-TOOLS-01-F01.
- `WU-TOOLS-01-S5-R2` -> WU-TOOLS-01-F02 then WU-TOOLS-01-F03 / Issue 120.
- `WU-TOOLS-01-S1-R1` -> WU-TOOLS-01-F04/F05 and WU-TOOLS-01-F06/F07 / Issues 121 and 122.
- `WU-TOOLS-01-S1-R2` -> WU-TOOLS-01-F08.

These are not WU-CM-01 residual risks and are intentionally retained.

## Validation Baseline

The latest WU-CM-01-F03 final validation before PR 125:

```bash
source .venv/bin/activate && pytest tests/host/test_terminal_summary_payload.py tests/host/test_memory_projection.py tests/host/test_run_input_builder.py tests/host/test_compaction_operation.py tests/host/test_compact_material.py tests/host/test_engine_ingest_mapping.py
```

Result: `197 passed`.

```bash
source .venv/bin/activate && pyright
```

Result: `0 errors, 0 warnings, 0 informations`.

This umbrella closeout changes only documentation and GitHub issue state, so no additional code validation is required.

## Next Entry Point

After user merge of PR 125, continue with `WU-TOOLS-01-F01` unless the user selects a different pending work unit.
