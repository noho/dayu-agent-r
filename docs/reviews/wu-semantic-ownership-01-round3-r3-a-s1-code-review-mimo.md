# Code Review — WU-SEMANTIC-OWNERSHIP-01 Round3 R3-A S1

## Scope

- Mode: current changes
- Branch: `phaseflow/host-issues-control`
- Base: `main` (plan baseline commits `4a282850` and `41bd6ca9`)
- Output file: `docs/reviews/wu-semantic-ownership-01-round3-r3-a-s1-code-review-mimo.md`
- Included scope: S1 accepted findings DR-006 (runner-call hot payload unbounded), DR-010 (durable descriptor content/digest split), compact_material wrong tool_call_event_ref fallback
- Excluded scope: S2-S8 behavior changes, schema DDL changes
- Parallel review coverage: 无

## Review Focus Verification

### 1. Shared runner-call hot owner

**Verified.** `_runner_call_manifest.py` is the single owner of `RUNNER_CALL_INPUT_ASSEMBLED` hot payload shape. All three producers (`run_input._runner_call_manifest_hot_payload`, `engine_ingest._runner_call_manifest_hot_payload`, `compaction_operation._compactor_runner_call_hot_payload`) delegate to `runner_call_hot_payload(RunnerCallHotAtoms(...))`. The returned dict contains exactly 20 fixed scalar fields (confirmed by `test_runner_call_hot_payload_contract.py:test_runner_call_producers_share_fixed_hot_schema` asserting `frozenset(payload) == _EXPECTED_HOT_FIELDS` and `not isinstance(value, list)` for every value). No `projector_metadata_summary` array exists in the hot payload. Size is bounded: `max(sizes) - min(sizes) <= 8` across 0-300 messages.

Compactor six-field metadata: `_runner_call_projector_metadata_descriptor` in `_runner_call_manifest.py` validates and emits exactly 6 fields. No default/fallback version exists — compactor explicitly provides all fields via `_compactor_runner_call_hot_payload`.

### 2. Durable payload integrity owner

**Verified.** `dayu/host/durable/payload_resolution.py:resolve_json_payload` is the single owner. It verifies in order: (1) caller ref/digest, (2) descriptor ref/digest/size/kind identity, (3) SQLite row id/format/digest/size or artifact containment/digest/size, (4) actual canonical bytes digest/size, (5) canonical JSON object parse and re-canonicalization check. All consumers delegate here:
- `payload_resolution.sqlite_payload_object` → `resolve_json_payload`
- `tool_trace.read_tool_trace_json_payload` → `resolve_json_payload` (required `expected_digest: str`, no optional None path)
- `durable/tool_trace._read_hot_row_descriptor_payload` → `read_tool_trace_json_payload` → `resolve_json_payload`

No module outside `durable/payload_resolution.py` performs its own partial JSON payload integrity resolution. All `payload_digest` comparisons found elsewhere are write-time guards, not reader/resolvers.

### 3. Tool Trace projector metadata reconstruction

**Verified.** `durable/tool_trace._projector_metadata_summary_from_manifest` reads `manifest_ref` and `manifest_digest` from the hot row summary, loads the digest-verified manifest via `read_tool_trace_json_payload`, extracts `projector_metadata` from the manifest body, validates each item via `_validate_projector_metadata_contract` (exact 6-field `frozenset` check, sha256 digest, non-empty source_contract_refs), and returns `tuple[ProjectorMetadataSummary, ...]`. The old `_projector_metadata_summary_from_trace` (which read arrays from hot row) and `_runner_call_projector_metadata_summary` in `tool_trace.py` were deleted.

### 4. Effective execution snapshot verification

**Verified.** `_execution_config_projection.effective_execution_snapshot_from_json` verifies digest and ref BEFORE deserialization: (1) recomputes `actual_config_digest = sha256_digest_json(config)`, (2) compares against declared `policy_snapshot_digest`, (3) recomputes `expected_policy_snapshot_ref = "policy:" + actual_config_digest`, (4) compares against declared `policy_snapshot_ref`, (5) only then deserializes runner_spec/options/agent_policy. Both production callers (`dispatch.py:4605`, `admission.py:3641`) use this function; no caller constructs `EffectiveExecutionSnapshot` directly.

### 5. Compact material fail-closed

**Verified.** `compact_material._accepted_tool_evidence_delta_blocks` raises `HostDurableError` on missing `tool_call_requested_event_ref` (line 2559) and missing `request_arguments_json` (line 2564). No `result_event_id` fallback exists (zero occurrences in `compact_material.py`). The `tool_call_event_ref` comes from `project_accepted_tool_result` projection, not from `TOOL_RESULT_ACCEPTED.event_id`.

### 6. Stress and tests

**Verified.** `test_host_production_stress.py` asserts `len(factory.accepted_snapshots) == 12` (line 1957) — a hard equality check, not just happy path. The stress test covers crash/recovery, cancellation, worker failure, stream exception, stale owner detection, and consumer cancel isolation. Tamper fail-closed behavior is tested separately in `test_durable_payload_integrity.py` (7 SQLite + 3 artifact tamper kinds, caller digest split, noncanonical JSON, non-object JSON) and `test_effective_execution_config.py` (config content, policy digest, policy ref tamper). `test_compact_material.py` tests missing request atom, self-referencing result, cross-run identity mismatch, and payload damage fail-closed.

### 7. Scope/readme/design

**Verified.** All docs changes describe only S1 contracts. `design.md` adds sections for execution snapshot digest verification, durable payload resolver, tool trace manifest reconstruction, runner-call hot payload forbidding arrays, and compact material provenance fail-closed. `dayu/host/README.md` updates Admission, RunInputBuilder, and Outbox/audit sections with S1 contract descriptions. `tests/README.md` updates test coverage descriptions. No S2-S8 content. README changes follow AGENTS.md constraints.

### 8. Project constraints

**Verified.** New signatures use typed dataclasses (`RunnerCallHotAtoms`, `RunnerCallHotDiagnostic`, `RunnerCallProjectorMetadata`, `ResolvedJsonPayload`). No `Any` or `object` in new signatures. Chinese docstrings present on all new functions/classes. No compatibility shim. No downstream repair. No schema migration.

## Findings

未发现实质性问题。

## Open Questions

无。

## Residual Risk

- `durable/tool_trace._read_hot_row_descriptor_payload` 接受 `descriptor_digest: str | None`，当 `None` 时抛出 `HostDurableError`。当前所有调用方传入的 digest 来自 hot row projection summary，该 summary 由 `tool_trace._runner_call_trace_summary` 从 hot payload 的 `manifest_digest` scalar atom 读取。如果 hot payload 缺少 `manifest_digest`（由 `_runner_call_manifest._validate_hot_atoms` 已校验为必填），该路径会在 summary 构造阶段失败。风险低，因为 hot payload shape 由 shared owner 强校验。
- stress test 不覆盖 tamper/integrity failure path — 由独立 test 文件覆盖，不构成 gap。
