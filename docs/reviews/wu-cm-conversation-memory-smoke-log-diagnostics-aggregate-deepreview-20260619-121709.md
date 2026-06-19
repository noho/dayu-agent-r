# Aggregate Deepreview

## Scope

- Gate: aggregate deepreview
- Work unit: Conversation Memory smoke/log diagnostics and smoke coverage boundary
- Branch: `wu-cm-12-conversation-memory-drift`
- Base for this work unit: `f5f047453148c193dbf5639ec43554c628a333f5`
- Reviewed range: `f5f047453148c193dbf5639ec43554c628a333f5..HEAD`
- Included files:
  - `utils/smoke_host_public_conversation_memory_scenarios.py`
  - `tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py`
  - `README.md`
  - `tests/README.md`
  - `docs/host/conversation-memory-smoke-compact-followup.md`
  - gateflow plan / review / implementation artifacts under `docs/reviews/`
- Excluded files:
  - production Host / Engine compact behavior files, because this work unit explicitly forbids production memory behavior changes.

## Findings

未发现实质性问题。

## Evidence Checked

- `run_smoke()` still uses public Host handle for execution and only reads compact EventLog rows after the Host context closes.
- `_compact_audit_report()` is a durable-row read wrapper and delegates report construction to `_compact_audit_report_from_rows()`.
- `_compact_audit_report_from_rows()` builds summary, operation timeline and histograms from the same `EventLogRow` tuple.
- `CONTEXT_COMPACTION_FAILED` remains a hard fail in `_assert_compact_acceptance()` regardless of `fallback_action=dispatch`.
- Rejected attempt manifest missing emits `failure_stage=prepare_or_material_projection` and `log_insufficient=offending_material_block_unavailable` in debug detail output.
- README text describes current smoke behavior only and does not claim full conversation memory correctness validation.
- Tests cover normal report construction, manifest present / missing histogram, malformed payload, missing operation id, empty rows, and hard-fail behavior.

## Validation

```bash
source .venv/bin/activate && pytest tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py
```

Result: 16 passed, 3 third-party deprecation warnings.

```bash
source .venv/bin/activate && pyright utils/smoke_host_public_conversation_memory_scenarios.py tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py
```

Result: 0 errors, 0 warnings, 0 informations.

## Open Questions

无。

## Residual Risk

- Production memory compact failure from long25 remains assigned to the later production memory compact failure work unit.
- Real LLM long25 smoke was not run in this work unit; diagnostics were validated through no-real-LLM assembly / helper tests.
- Per-operation histograms are retained in `CompactOperationAudit` but only global histograms are printed; operation-local histogram printing is a deferred smoke diagnostics enhancement if needed.
- Offending material block text remains unavailable when `proposal_manifest_ref` is missing; this is intentionally exposed as log insufficiency.

## Conclusion

Aggregate deepreview status: pass.
