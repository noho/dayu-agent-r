# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-B Aggregate DeepReview — AgentDS

## Scope

- **Review target**: R3-B complete diff (base `c1695df6` → HEAD `1a70fd20` + uncommitted aggregate validation fix)
- **Changed files**: 50 files, +6022/−804 lines (31 production/test, 19 plan/review artifacts)
- **Accepted plan**: `docs/host/wu-semantic-ownership-01-round3-r3-b-engine-provider-protocol-plan.md`
- **Design truth**: `docs/engine/design.md`, `docs/host/design.md`
- **Agent instructions**: `AGENTS.md`
- **Date**: 2026-07-12

---

## Aggregate Validation Summary

| Check | Result |
|-------|--------|
| Default pytest | `4137 passed, 3 skipped, 5 deselected` |
| Pyright | `0 errors, 0 warnings, 0 informations` |
| `git diff --check` | pass |

---

## Focus 1: S1 RunnerDone Commit Boundary — Cross-Path Consistency

### Path matrix verification

| Path | RunnerDone accepted? | Post-done cancel check | Cancel prevents terminal? | Evidence |
|------|---------------------|----------------------|--------------------------|----------|
| ordinary final (STOP) | Yes → yields `FINAL_ANSWER` | `agent.py:898`: `runner_done is None` guard | **Prevented** | Post-done cancel doesn't fire; FINAL_ANSWER is terminal |
| force-answer final | Yes → yields `FINAL_ANSWER` | `agent.py:2372`: same guard | **Prevented** | Same as ordinary final path |
| protocol error done | Yes → `_make_iteration_failure_terminal` → `runner_done is not None` → `_make_terminal_failed` | **No cancel check** | **Prevented** | `agent.py:2488`: directly returns FAILED |
| HTTP error done | Same mechanism | Same | **Prevented** | Same as protocol error |
| tool-call done | Yes → yields `TOOL_CALLS_BATCH_READY` + all `TOOL_CALL_REQUESTED` | `_execute_tool_batch:1963`: cancel check AFTER projecting | **Delayed** — tool facts projected, then cancel | `agent.py:1920-1965` |
| pre-done cancel | No | `agent.py:898`, `1305-1307`, `1316-1318` | **Allowed** | All pre-done cancel paths preserved |
| runner exception + cancel concurrent | No | Outer guard at `agent.py:898` catches it | **Allowed** (pre-done) | `runner_done is None` + `_is_cancelled()` → `RUN_CANCELLED` |
| runner exception after protocol candidate | N/A | First candidate preserved | N/A | `agent.py:1359-1378`: helper rejects overwrite |

### Key invariants

1. Post-done cancellation **never** produces `RUN_CANCELLED` — verified across all 5 paths ✅
2. Post-done failure (`_make_iteration_failure_terminal`) **never checks cancel** when `runner_done is not None` — verified at `agent.py:2488` ✅
3. Pre-done cancellation **always** produces `RUN_CANCELLED` — verified at 4 guard points ✅
4. `runner_done` is the **single typed commit fact** — `done_seen`/`finish_reason`/`provider_request_id` fields deleted, scan confirms zero residual ✅

**判定**: ✅ Pass — 全线一致。

---

## Focus 2: EngineEvent/Message/AgentRunRequest Runtime Validation — Owner Boundary

### Production owner verification

| Owner | Module | Mechanism | Consumed by | No downstream repair |
|-------|--------|-----------|-------------|---------------------|
| EngineEvent pairing | `engine_events.py` | `ENGINE_EVENT_TYPE_TO_DATA` + `__post_init__` | Agent producer, Host ingest | ✅ Host `_cancelled_eof_candidate` pairing verified correct |
| Message role | `messages.py` | `_validate_message_role` in 4 `__post_init__` | payload builder, trace | ✅ No role fallback in payload builder |
| AgentRunRequest union | `agent_run.py` | `isinstance(message, message_types)` | Agent, Host | ✅ No downstream repair |
| First failure candidate | `agent.py` | `_set_first_failure_candidate` sole writer | Iteration classification | ✅ No Host fallback |

### Test migration verification

- `tests/engine/test_engine_event_contract.py`: deleted local `EVENT_TYPE_TO_DATA`, imports production mapping ✅
- `tests/host/test_engine_ingest_mapping.py`: 3 negative fixtures migrated from Host `REJECTED` assertions to `EngineEvent(...)` constructor `pytest.raises` — owner boundary movement only ✅
- No `object.__new__` used ✅
- Host production code unchanged ✅

### Host scan

- `rg -n 'from dayu\.host\|import dayu\.host'` across all 10 changed production files → **无命中** ✅

**判定**: ✅ Pass — owner boundary 正确，Host/test 无下游 repair。

---

## Focus 3: S2 OpenAI — Identity Conflict, Terminal Shape, String-Only Arguments

### Identity conflict completeness

| Conflict type | Detected by | Fatal | No merge | No completed |
|--------------|-------------|-------|----------|--------------|
| Illegal native index (−1/−2/True/1.5/"0") | `_resolve_index` → `tool_call_invalid_index` | ✅ | ✅ (return None before write) | ✅ (no feed) |
| Synthetic → occupied native target | `_resolve_index` → `identity_conflict` | ✅ | ✅ | ✅ |
| Same id → two native indices | `_resolve_index` → `identity_conflict` | ✅ | ✅ | ✅ |
| Same native index → two ids | `_resolve_index` → `identity_conflict` | ✅ | ✅ | ✅ |
| Position-routed occupied target | `_resolve_index` + `_ambiguous_positions` | ✅ | ✅ | ✅ |
| Old merge (`source.name + target.name` etc.) | Scan: **zero hits** | N/A | ✅ (code deleted) | N/A |

### Terminal shape completeness

|Transport|Tool calls + STOP|Content + TOOL_CALLS|Missing/null|Completed before error?|
|---------|----------------|-------------------|------------|----------------------|
|SSE|`validate_sse_terminal_shape` → mismatch fatal|Same|missing_code fatal|**No** — terminal check at L658, before completed at L689/699|
|Non-stream|`validate_non_stream_terminal_shape` → mismatch fatal|Same|missing_code fatal|**No** — terminal check at L268, before completed at L312/320|

### String-only arguments completeness

| Argument type | Result | Code evidence |
|--------------|--------|---------------|
| JSON string `'{"a":1}'` | ✅ Accepted | `isinstance(arguments, str)` → feeds aggregator |
| dict `{"a":1}` | ❌ Fatal | `not isinstance(arguments, str)` → `tool_call_arguments_not_string` |
| list/number/bool/null/missing | ❌ Fatal | Same |
| Invalid JSON string | ❌ Fatal (existing) | Aggregator JSON parse → `tool_call_arguments_invalid_json` |
| JSON scalar string | ❌ Fatal (existing) | Aggregator object check → `tool_call_arguments_not_object` |

### Scan verification

| Scan pattern | Expected | Actual |
|-------------|----------|--------|
| `isinstance(arguments, Mapping)\|json\.dumps\(dict\(arguments\)\)` | 无 | **无命中** |
| `done_finish_reason = FinishReason\.TOOL_CALLS\|finish = FinishReason\.TOOL_CALLS` | 无 | **无命中** |
| `source\.name \+ target\.name\|source\.arguments_buffer \+ target\.arguments_buffer` | 无 | **无命中** |
| `FinishReason\.TOOL_CALLS` in sse/non_stream | 无 | **零命中** |
| `FinishReason\.TOOL_CALLS` in _choice_policy | wire mapping + comparison | **2 hits (expected)** |

**判定**: ✅ Pass — 无漏网兼容，无 completed-before-error。

---

## Focus 4: S3 Schema Bounds / Enum Equality — Owner-Closed

### Construction-time validation (tool_schema.py)

- `_COUNT_BOUND_KEYS`: `minLength`, `maxLength`, `minItems`, `maxItems` only ✅
- `_validate_count_bounds`: bool → TypeError, float/str → TypeError, negative → ValueError, `0` → valid ✅
- Array `items` recursion: one level, only when Mapping ✅
- No `oneOf`/`pattern`/`$ref`/`dependencies` — scan **zero hits** ✅

### Runtime defense (tool_call_projection.py)

- `_is_valid_count_bound`: same logic as construction-time ✅
- `_first_invalid_count_bound`: catches mutable tampering → `_schema_bound_failure` ✅
- Not reported as `_range_failure` (user parameter error) ✅

### Enum equality (_json_values_equal)

- 22 direct verification cases: all pass ✅
- `True != 1`, `False != 0.0`, `1 == 1.0` ✅
- Nested array/object recursion ✅
- NaN/inf → `math.isfinite` guard → never equal ✅
- Default and explicit argument: same `_project_field` recursive path ✅

### Consumer validation

- Doc/Web/Fins tool schemas: 225 passed (read-only) ✅
- No production schema modified ✅

### Scan verification

| Scan | Expected | Actual |
|------|----------|--------|
| `value not in enum_value\|value in enum_value` | 无 | **无命中** |
| `"(minLength\|maxLength\|minItems\|maxItems)"\s*:\s*-` in dayu | 无 | **无命中** |

**判定**: ✅ Pass — owner-closed。

---

## Focus 5: Documentation Sync

### `docs/engine/design.md`

9 substantive changes, all accurately reflecting implemented code:
1. AgentRunRequest message union validation → S1 `agent_run.py` ✅
2. AgentMessage role construction → S1 `messages.py` ✅
3. EngineEvent discriminator mapping → S1 `engine_events.py` ✅
4. Terminal shape requirement (tool-call presence ⟺ TOOL_CALLS) → S2 `_choice_policy.py` ✅
5. Tool-call identity aggregation rules → S2 `tool_call_aggregator.py` ✅
6. Non-stream string-only arguments → S2 `non_stream_parser.py` ✅
7. First-accepted failure candidate → S1 `agent.py` ✅
8. RunnerDone typed commit → S1 `agent.py` ✅
9. ToolParametersSchema bounds + enum equality → S3 `tool_schema.py` + `tool_call_projection.py` ✅
10. Removed duplicate final-answer commit bullet → Cleanup ✅

### `dayu/engine/README.md`

- Complies with `Agent更新约束【必须遵守】`: documents only implemented code facts ✅
- Covers: message/event construction, Runner normalization (identity conflict, terminal shape, string-only args), RunnerDone commit, first failure candidate, ToolSchema bounds/enum ✅
- No test lists or WU process status ✅

### `tests/README.md`

- Complies with "只记录当前 tests/ 下已经存在的测试" ✅
- Accurately describes S1/S2/S3 added coverage in existing sections ✅

### Unmodified docs

- `docs/host/design.md`, `dayu/host/README.md`, 根 `README.md`, `dayu/README.md`, Fins/Config README — all correctly skipped (no scope change in those layers) ✅

**判定**: ✅ Pass — 准确且不过度。

---

## Focus 6: Aggregate Validation Fix — Host Test Fixes

### Fix 1: `test_steer_replays_same_client_request_id_idempotently`

```python
+ await wait_for_diagnostic_event_type_count(
+     tmp_path / "host.sqlite3", "ATTEMPT_RUNNING", 1
+ )
```

- Reason: steer requires the current Attempt to be `ATTEMPT_RUNNING`. `_wait_for_run_status(RUNNING)` confirms the Run is RUNNING but not that its Attempt has reached `ATTEMPT_RUNNING`. The adjacent steer test already uses this pattern. ✅
- **Test-only**, zero production change ✅
- No workaround in Host admission logic ✅

### Fix 2: `test_succeeded_terminal_projection_fails_closed_for_descriptor_errors`

```python
- ("sha256:mismatch", "payload digest mismatch")
+ ("sha256:0000000000000000000000000000000000000000000000000000000000000000", "descriptor digest mismatch")
```

- Reason: `sha256:mismatch` is not a valid sha256 digest format; the durable payload owner correctly fails earlier with `expected_digest must be sha256 digest` instead of reaching the descriptor digest comparison. The fix uses a valid-format but wrong digest to test the actual descriptor mismatch path. ✅
- **Test-only**, zero production change ✅
- No workaround in Host durable logic ✅

**判定**: ✅ Pass — 合理、test-only、无 production workaround。

---

## Focus 7: Aggregate Source Scans — All Expected Results Confirmed

| # | Scan | Expected | Actual |
|---|------|----------|--------|
| 1 | `state\.(done_seen\|finish_reason\|provider_request_id)\|or FinishReason\.STOP` in agent.py | 无 | **无命中** |
| 2 | `state\.failure_candidate\s*=` in agent.py | helper only | **L564 only** ✅ |
| 3 | `isinstance\(arguments, Mapping\)\|json\.dumps\(dict\(arguments\)\)` | 无 | **无命中** |
| 4 | `done_finish_reason = FinishReason\.TOOL_CALLS\|finish = FinishReason\.TOOL_CALLS` | 无 | **无命中** |
| 5 | `FinishReason\.TOOL_CALLS` in sse/non_stream | 无 | **零命中** |
| 6 | `FinishReason\.TOOL_CALLS` in _choice_policy | mapping + comparison | **2 hits** ✅ |
| 7 | `source\.name \+ target\.name\|source\.arguments_buffer \+ target\.arguments_buffer` | 无 | **无命中** |
| 8 | `value not in enum_value\|value in enum_value` | 无 | **无命中** |
| 9 | `"(minLength\|maxLength\|minItems\|maxItems)"\s*:\s*-` in dayu | 无 | **无命中** |
| 10 | `hasattr\(\|getattr\(` in 10 production files | 无 | **无命中** |

### Additional cross-slice scans

| Scan | Result |
|------|--------|
| `from dayu\.host\|import dayu\.host` in 10 changed production files | **无命中** |
| `Any\|object` in new production signatures | 无新增 |
| `# type: ignore` | 无新增 |
| `compat\|OLD\|loose` in production code | **无命中** |
| `object\.__new__` in tests (bypass constructor) | **无使用** |
| Unauthorized scope (Host/Fins/Web/CLI/Service production) | **无修改** |

**判定**: ✅ Pass — 全部扫描符合预期。

---

## Propagation Audit (per plan §Propagation audit)

1. ✅ 所有生产 `EngineEvent(...)` 构造点均通过 owner pairing — Agent `_make_event` + Host `_cancelled_eof_candidate`
2. ✅ 所有生产 AgentMessage 构造点传本类固有 role — payload builder 无 fallback
3. ✅ Parser fatal tool call 不到达 `_execute_tool_batch` — identity conflict / mismatch → `RunnerDone(ERROR)`, no completed
4. ✅ `finish_reason` 从 `_choice_policy` → `RunnerDoneData` → `IterationCompletedData` → `FinalAnswerData` 同一 typed fact
5. ✅ First failure candidate 的 code/id 进入 `ProviderProtocolErrorData` / `RunFailedData` 后一致
6. ✅ `dayu.runtime` 只依赖标准库 + `dayu.contracts`
7. ✅ Rejected runner identity / error-marker findings 无被伪装成已修复

---

## Plan Review Findings — Final Verification

| Finding | Source | Resolution |
|---------|--------|------------|
| MiMo-F1 (post-done tests) | Plan review | ✅ S1: 5 post-done tests pass |
| MiMo-F2 (finish_reason semantic scan) | Plan review | ✅ S2: semantic scan + 人工审计, 0 parser hits |
| DS-F1 (position routing) | Plan review | ✅ S2: position routed conflict + ambiguous_positions |
| DS-F2 (exception first-candidate) | Plan review | ✅ S1: `_set_first_failure_candidate` sole writer |
| DS-F3 (finish_reason fallback) | Plan review | ✅ S1: `or STOP` deleted, `isinstance` guard |

---

## Residual Risks

All 4 plan residual risks unchanged:
- Non-standard provider dict arguments → fail-closed (no change)
- Synthetic index delta preview → accepted (no change)
- Context overflow marker → rejected finding (no change)
- Runner identity delimiter → rejected finding (no change)

No new residuals introduced by S1/S2/S3 implementation or aggregate validation fix.

---

## Findings

无。7 个 focus area 全部通过，未发现 material issue。

---

## Aggregate DeepReview Conclusion

**Pass** — 0 findings, 0 blocking questions.

**Artifact**: `docs/reviews/wu-semantic-ownership-01-round3-r3-b-aggregate-deepreview-ds.md`
