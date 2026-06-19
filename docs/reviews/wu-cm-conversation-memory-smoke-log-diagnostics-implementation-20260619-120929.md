# Implementation Report

## Gate

- Gate: implementation
- Work unit: Conversation Memory smoke/log diagnostics and smoke coverage boundary
- Accepted plan commit: `60d895ee`
- Scope: smoke/log diagnostics, utils smoke tests, README boundary notes, follow-up implementation status.

## Changed Files

- `utils/smoke_host_public_conversation_memory_scenarios.py`
- `tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py`
- `README.md`
- `tests/README.md`
- `docs/host/conversation-memory-smoke-compact-followup.md`

## Implementation Summary

- Added compact audit report construction from compact EventLog rows.
- Added per-operation compact timeline output with request sequence, run id, trigger source, accepted / failed sequences, failure reason, policy decision, fallback policy decision, fallback action and attempt count.
- Added rejected attempt histograms by failure category, normalized diagnostic suffix and proposal manifest ref present / missing.
- Added debug rejected attempt detail output with `failure_stage=prepare_or_material_projection` and `log_insufficient=offending_material_block_unavailable` when `proposal_manifest_ref` is missing.
- Kept `CONTEXT_COMPACTION_FAILED` as `memory-compact` hard fail.
- Added flush on key smoke summary / pass / fail output paths to avoid `SMOKE TOOL_CALLS_BY_KEY` and `SMOKE FAIL` line adhesion.
- Updated README boundaries:
  - `memory-core` is the lightweight daily smoke.
  - `memory-compact --pressure-mode auto` is the pressure / diagnostic smoke.
  - current smoke does not cover full conversation memory correctness validation.
- Updated tests README to describe compact report / histogram / manifest missing stage coverage.
- Updated follow-up notes with implementation status and explicit non-fix of production memory compact failure.

## Validation

```bash
source .venv/bin/activate && pytest tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py
```

Result: 16 passed, 3 third-party deprecation warnings.

```bash
source .venv/bin/activate && pyright utils/smoke_host_public_conversation_memory_scenarios.py tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py
```

Result: 0 errors, 0 warnings, 0 informations.

```bash
rg -n "issue 80|完整 issue|已实现 eval|memory correctness 全量验证" README.md tests/README.md docs/host/conversation-memory-smoke-compact-followup.md
```

Result: no root README / tests README internal issue reference; matches only follow-up note historical context.

## Residual Risks

- Production memory compact failure remains assigned to later work unit; this implementation only improves smoke diagnostics.
- Real LLM long25 was not run in this implementation pass; no-real-LLM assembly tests cover report construction and stdout formatting helpers.
- Offending compact material block remains unavailable when `proposal_manifest_ref` is missing; smoke now makes that log insufficiency explicit instead of pretending it has the block.

## Completion Status

Ready for code review gate.
