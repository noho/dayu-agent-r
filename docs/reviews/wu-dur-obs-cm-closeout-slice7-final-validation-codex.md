# WU-DUR-OBS-CM Closeout Slice 7 Final Validation Codex

## Gate

- gate: final public-path validation
- work units: `WU-DUR-P01` / `WU-OBS-P00` / `WU-CM-01-F02` / `WU-CM-01-F01`
- validating work unit: `WU-CM-01-F01`
- branch: `phaseflow/wu-dur-obs-cm-closeout`
- accepted S7-R1-S1 commit: `2195a2ff`
- bookkeeping commit before this artifact: `6eb4a9db`
- artifact path: `docs/reviews/wu-dur-obs-cm-closeout-slice7-final-validation-codex.md`

## Validation Commands

- `source .venv/bin/activate && pytest tests/engine/test_engine_event_contract.py tests/engine/test_agent_phase3_tool_call.py -q`
  - result: `56 passed in 0.21s`
- `source .venv/bin/activate && pytest tests/host/test_engine_ingest_mapping.py tests/host/test_toolruntime_accept_barrier.py tests/host/test_tool_trace_projection.py tests/host/test_tool_trace_queries.py -q`
  - result: `93 passed in 1.01s`
- `source .venv/bin/activate && pytest tests/host/test_compaction_operation.py tests/host/test_run_input_builder.py -q`
  - result: `88 passed in 0.78s`
- `source .venv/bin/activate && pytest tests/host/test_public_tool_wiring_smoke.py tests/host/test_public_open_host_multiturn_smoke.py tests/host/test_public_compact_smoke.py -q`
  - result: `13 passed, 1 skipped in 6.82s`
- `source .venv/bin/activate && pyright`
  - result: `0 errors, 0 warnings, 0 informations`
  - note: pyright only reported an available version update warning.
- `git diff --check`
  - result: passed, no whitespace errors.

## Utility Smoke Audit

- `source .venv/bin/activate && python utils/smoke_host_public_conversation_memory.py --help`
  - result: exit `0`; CLI help emitted.
  - applicability: standalone public conversation memory smoke. It defaults to a fresh workspace under `workspace/tmp`, so it does not depend on old durable schema state.
- `source .venv/bin/activate && python utils/smoke_host_public_conversation_memory_scenarios.py --help`
  - result: exit `0`; CLI help emitted.
  - applicability: standalone public conversation memory scenario smoke. It defaults to a fresh workspace under `workspace/tmp`, so it does not depend on old durable schema state.
- `source .venv/bin/activate && python utils/smoke_host_public_multiturn.py --help`
  - result: exit `0`; CLI help emitted.
  - applicability: standalone public multiturn smoke. It defaults to a fresh workspace under `workspace/tmp`, so it does not depend on old durable schema state.
- `source .venv/bin/activate && python utils/smoke_host_public_diagnostics.py --help`
  - result: exit `0`; no help text emitted.
  - applicability: this file is a shared diagnostics printing helper, not a standalone public runner-call smoke entry point. It does not trigger runner calls or compaction; one-system-message and compact prompt assertions are not applicable to this helper itself.

## Closure Evidence

- Public runner-call messages are asserted through `tests/host/public_smoke_support.py::assert_at_most_one_system_message()`.
- Public tool wiring, multiturn, and compact smoke tests now validate that ordinary public path runner-call messages contain at most one leading system message.
- Compact public smoke keeps compactor prompt and material internal-term checks active, and verifies manifest message entries / role digest against the normalized final message role sequence.
- Focused RunInputBuilder tests cover no-compact, post-compact, memory facts, selected recent window role preservation, manifest boundedness, internal-field ban, and same-section system envelope boundedness.
- Tool Trace / manifest / Engine ingest focused tests passed, providing the WU-DUR-P01 and WU-OBS-P00 durable truth / observability validation needed before WU-CM-01-F01 closeout.

## Residual Risk

- Real provider matrix remains environment-gated and was not required for this deterministic closeout.
- Optional real compactor smoke was not run because `DAYU_RUN_REAL_COMPACTOR_SMOKE=1` is explicitly environment-gated and not required for this gate.
- `utils/smoke_host_public_diagnostics.py` being a helper rather than a standalone CLI remains a documentation/control-doc naming mismatch. It is not a blocker for this code gate because no runner-call or compaction behavior can be validated through that helper alone.

## Status

Final Slice 7 public-path validation passed. WU-CM-01-F01 can close the S7-R1 residual and complete the WU-DUR-P01 / WU-OBS-P00 / WU-CM-01-F02 / WU-CM-01-F01 closeout chain.
