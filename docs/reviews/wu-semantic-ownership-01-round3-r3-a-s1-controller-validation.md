# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-A S1 Controller Validation

## Scope

- Gate: controller validation after AgentCodex S1 implementation
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-round3-r3-a-s1-implementation-codex.md`
- Plan artifact: `docs/host/wu-semantic-ownership-01-round3-r3-a-host-lifecycle-durable-plan.md`
- Status: ready for code review

## Scope Audit

Changed files are within the S1 allowed list:

- Host production: runner-call manifest owner, payload resolver, Tool Trace, compact material, effective execution projection, and three runner-call producers.
- Tests: allowed Host S1 tests plus the two new owner-level tests.
- Docs: `docs/host/design.md`, `dayu/host/README.md`, and `tests/README.md`.

No scheduler lifecycle, Host opener/admin actor, wait, Engine provider, context budget, CLI/config/R3-F, Fins, schema DDL, migration, or control-doc code path was modified.

## Validation

Focused S1 matrix:

```text
pytest tests/host/test_payload_store.py tests/host/test_effective_execution_config.py tests/host/test_run_input_builder.py tests/host/test_engine_ingest_mapping.py tests/host/test_compaction_operation.py tests/host/test_tool_trace_projection.py tests/host/test_tool_trace_queries.py tests/host/test_compact_material.py tests/host/test_terminal_payload.py tests/host/test_outbox_projection.py tests/host/test_runner_call_hot_payload_contract.py tests/host/test_durable_payload_integrity.py -q
406 passed in 3.05s
```

Type check:

```text
python -m pyright dayu/host/ tests/host/
0 errors, 0 warnings, 0 informations
```

Production stress:

```text
pytest -o addopts="" -m stress tests/host/test_host_production_stress.py::test_scheduler_liveness_long_run_mixed_flow_stress -q
1 passed in 1.32s

pytest -o addopts="" -m stress tests/host/test_host_production_stress.py -q
5 passed in 6.68s
```

During an earlier parallel controller validation run, full stress had one `active_cleanup` failure while focused tests and pyright were running concurrently. The same failing test passed when rerun alone, and the full stress file passed when rerun serially. This is recorded as validation-run interference, not an accepted S1 regression.

Source scans:

```text
rg -n "projector_metadata_summary" dayu/host/run_input.py dayu/host/engine_ingest.py dayu/host/compaction_operation.py dayu/host/tool_trace.py
zero matches

rg -n "tool_call_event_ref = row\\.event_id" dayu/host/compact_material.py
zero matches

rg -n "projector_metadata_id|projector_schema_version|source_contract_refs" dayu/host/_runner_call_manifest.py dayu/host/run_input.py dayu/host/engine_ingest.py dayu/host/compaction_operation.py dayu/host/tool_trace.py
expected owner/producer matches present
```

Whitespace:

```text
git diff --check
passed
```

## Decision

S1 implementation is ready for independent code review by AgentMiMo and AgentDS.
