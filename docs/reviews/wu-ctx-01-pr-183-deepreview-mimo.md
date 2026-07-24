# WU-CTX-01 PR #183 Whole-PR Deep Review — AgentMiMo

## Review Metadata

| Field | Value |
|---|---|
| PR | #183 (draft) |
| Branch | `feat/wu-ctx-01` → `main` |
| Head | `ae524fe0` ("gateflow: ready WU-CTX-01 draft PR") |
| Base | `main` |
| Files Changed | 139 (+36,398 / −4,316) |
| Review Timestamp | 2026-07-24T12:00 UTC |
| Controller-owned excluded | `docs/host/issues-implementation-control.md` (uncommitted working change) |

## Verdict

**PASS**

PR 实现完整、类型安全、语义所有权清晰，无 actionable findings。

---

## Verification Summary

### 1. Correctness — CONTEXT_BUDGET_EVALUATED canonical fact

- **Fact producer** (`context_events.py:build_context_budget_evaluated_payload`): 从 `ContextSizingResult` 单一真源构造 payload，不重新读取 policy、不重算 estimate。`__post_init__` 验证公式一致性（signed delta、predicted = U_anchor + delta、utilization = floor(P * 10000 / W)）。
- **Fact parser** (`context_events.py:parse_context_budget_evaluated_payload`): strict schema roundtrip 验证，`schema_version` 必须精确匹配 `context_budget_evaluated.v1`。
- **Deterministic identity**: `context_budget_evaluated_event_id` 由 `run_id + candidate_input_cursor + candidate_input_digest + sizing_stage + policy_snapshot_digest + estimator_id + estimator_version` 决定，同 decision 不产生第二条 fact。
- **Append idempotency**: `append_context_budget_evaluated_in_transaction` 在 event_id 冲突时抛 `HostEventIdentityConflictError`，不静默覆盖。

**Evidence**: 85 tests in `test_context_budget.py` + `test_context_budget_evaluated.py` + `test_context_anchor.py` all pass. `test_deterministic_append_reuses_same_truth_and_rejects_conflict`, `test_event_identity_uses_frozen_atoms_only`.

### 2. Adaptive Estimator Independence

- **Conservative estimator** (`context_budget.py`): 纯函数 `estimate_context_budget()` / `estimate_context_input()`，不依赖 EventLog、database 或 provider 状态。`CONTEXT_ESTIMATOR_CONTRACT` 是模块级 frozen constant。
- **Anchor resolver** (`context_anchor.py`): 只在调用方同一 `HostTransaction` snapshot 内扫描，不持有连接或缓存。resolver 结果 (`ContextAnchorResolution`) 只包含 `CompatibleContextAnchor | ContextSizingFallbackReason`，不包含 predicted 值。
- **Sizing result** (`context_budget.py:build_context_sizing_result_from_atoms`): 当 `anchor_resolution=None` 时强制 fallback，当 anchor 存在且 arithmetic 合法时才切换到 `USAGE_ANCHORED` method。两条路径收敛到同一个 `ContextSizingResult` typed boundary。

**Evidence**: `test_usage_anchored_sizing_uses_signed_delta_without_clamp` (positive & negative delta), `test_invalid_anchor_arithmetic_falls_back_to_exact_current_estimate` (non-positive prediction, overflow).

### 3. Provider 无 Usage 严格回退 — Run 不失败

- `context_anchor.py:resolve_context_anchor` 扫描到 compact boundary 后若无 compatible anchor，返回 `USAGE_MISSING` fallback reason，不抛异常。
- `engine_ingest.py` 中 `_usage_observation_diagnostic` 在 observation 构造失败时降级为 `USAGE_OBSERVATION_STATUS_ESTIMATE_UNAVAILABLE`，不中断 ingest。
- `engine_ingest.py:_usage_reported_*` 在 policy 不可用、manifest 缺失、usage tokens 非法时均保持 projection non-failing。
- 设计文档明确要求："usage 缺失、provider 不支持 usage 或 usage 字段格式异常都不得导致 Run 失败，后续预算判断必须确定性 fallback。"

**Evidence**: `test_usage_reported_without_policy_keeps_projection_non_failing`, `test_usage_reported_missing_input_event_keeps_projection_non_failing`, `test_usage_reported_invalid_tokens_keeps_projection_non_filling`, `test_actual_usage_presence_does_not_depend_on_supports_flag`, `test_supports_flag_does_not_invent_missing_usage`.

### 4. 五阶段 Producer/Recovery/Continuation 顺序

设计文档定义五阶段: `ORDINARY`, `POST_COMPACT`, `REACTIVE_POST_COMPACT`, `DISPATCH_FALLBACK`, `CONTINUATION`。

- **Pressure/Action matrix** (`context_budget.py:_pressure_and_decision`): 完整穷举 5×3=15 组合。POST_COMPACT / REACTIVE_POST_COMPACT / CONTINUATION 在 soft threshold 时 ALLOW_DISPATCH（因该 stage 的 compact 已完成）；DISPATCH_FALLBACK 和 ORDINARY 在 soft threshold 时分别 ALLOW 和 COMPACT。所有 stage 在 hard threshold 时为 BLOCK（除 REACTIVE_POST_COMPACT 和 CONTINUATION 允许 ALLOW）。
- **Canonical payload roundtrip** (`test_payload_roundtrip_preserves_five_stage_pressure_and_action`): 5 个 stage 全部通过 roundtrip 验证。
- **Manifest-before-start invariant** (`dispatch.py:2782`): "按 manifest-before-start 顺序提交一个 allow candidate"。
- **Continuation path** (`engine_ingest.py:4096`): `ContextSizingStage.CONTINUATION` 用于 Engine within-Attempt continuation，从 source manifest/budget fact 复用 accepted method/prediction/policy atoms。

**Evidence**: 15-parametrized test cases in `test_context_budget.py::test_context_sizing_stage_matrix_separates_pressure_from_action`, 5-parametrized in `test_context_budget_evaluated.py::test_payload_roundtrip_preserves_five_stage_pressure_and_action`.

### 5. Public Projection 没有跨层漂移

- **HostContextUsageView** (`api.py:3058-3118`): 精确 7 个字段 — `predicted_input_tokens`, `context_window_size`, `utilization_basis_points`, `soft_threshold_tokens`, `hard_threshold_tokens`, `estimate_method`, `pressure_level`。
- **Public activity projection** (`read_api.py:_context_usage_activity`): 从 `CONTEXT_BUDGET_EVALUATED` canonical fact 严格解析，只投影 7 字段到 `HostContextUsageView`，不暴露 raw usage、anchor diagnostic、policy ref、estimator digest 或 fallback reason。
- **utilization_basis_points**: `floor(predicted * 10000 / window)`, 不 clamp。验证: `test_payload_utilization_is_unclamped_and_public_subset_is_exact` 中 1250/1000 = 12500 basis points。
- **Service entrypoint** (`entrypoint_runtime.py:29-31`): import `HostContextUsageView`, `ContextEstimateMethod`, `ContextPressureLevel`，typed 投影。

**Evidence**: `test_payload_utilization_is_unclamped_and_public_subset_is_exact`, `test_strict_parser_and_public_projection_fail_closed_on_corruption`, `test_anchored_fact_roundtrip_keeps_diagnostic_host_private`.

### 6. Barrier 机制 — 不越过 Lineage Gap

- `context_anchor.py:_build_scan_items`: 对 manifest/link/usage/completion 解析失败统一生成 `_Barrier`。
- `context_anchor.py:resolve_context_anchor`: 倒序遍历 items，遇到 `_Barrier` 立即返回 fallback，不查找更旧 anchor。
- Barrier reasons 完整覆盖: `MANIFEST_INCOMPLETE`, `ITERATION_LINK_INVALID`, `ITERATION_INCOMPLETE`, `ITERATION_LINK_MISSING`, `ITERATION_LINK_INVALID`, `MANIFEST_MISMATCH`, `USAGE_INVALID`, `LINEAGE_GAP`, `ITERATION_FINISH_REASON_INELIGIBLE`, `ITERATION_COMPLETION_AMBIGUOUS`.

**Evidence**: 8-parametrized `test_newer_lineage_barrier_never_falls_through_to_old_anchor` covering all barrier types.

### 7. Runner-Call Manifest Sizing Snapshot

- `RunnerCallSizingSnapshot` (`_runner_call_manifest.py`): frozen dataclass with `status` (complete/unavailable/not_applicable), optional `reason`, and sizing atoms when complete.
- `sizing_snapshot` added to `_RUNNER_CALL_MANIFEST_REQUIRED_FIELDS`.
- Manifest v2 includes sizing snapshot in canonical JSON with strict parsing.

### 8. Anchor Compatibility Dimensions

Resolver explicitly checks 6 dimensions:
1. Provider match
2. Model match
3. Context window match
4. Estimator contract (id + version) match
5. Request semantics digest match
6. Accepted compact boundary

Each dimension has a dedicated test: `test_resolver_rejects_each_compatibility_dimension` (5 parametrized cases for provider/model/window/estimator/request_semantics).

### 9. Typing & Testing

- **pyright**: `dayu/host/` — 0 errors, 0 warnings, 0 informations.
- **Full test suite**: 2258 passed, 1 flaky (pre-existing `test_open_host_active_cancel_watchdog_public_watch_observes_cancelled` — thread id assertion, unrelated to context governance), 2 skipped, 6 deselected.
- **Context-specific**: 195 tests pass across `test_context_budget.py`, `test_context_budget_evaluated.py`, `test_context_anchor.py`, `test_context_compact_events.py`, `test_context_policy.py`, and context-related tests in `test_dispatch_scheduler.py`, `test_engine_ingest_mapping.py`, `test_run_input_builder.py`.
- **Coverage of Issue #20 acceptance criteria**:
  - ✅ Compatible anchors use signed-delta formula (positive & negative)
  - ✅ Missing/invalid usage → conservative full-input fallback
  - ✅ Soft threshold crossing → proactive compact before next dispatch
  - ✅ One canonical sizing/budget decision, all projections derive from it
  - ✅ Durable replay/recovery produces same anchor compatibility, predicted value, fallback reason, and decision
  - ✅ Tests cover mixed text/JSON/tool schema, source refs, usage-present and usage-absent providers, Host/Engine layering

### 10. Semantic Ownership Drift Check

| Semantic | Owner | Consumer | Drift? |
|---|---|---|---|
| Conservative estimator | `context_budget.py` | `run_input.py`, `dispatch.py`, `engine_ingest.py` | No — consumers call `estimate_context_budget()`/`estimate_context_input()`, don't reimplement |
| Anchor resolution | `context_anchor.py` | `run_input.py`, `dispatch.py` | No — consumers call `resolve_context_anchor()`, don't query EventLog directly |
| Context sizing result | `context_budget.py` | `context_events.py`, `dispatch.py`, `engine_ingest.py` | No — `ContextSizingResult` is single typed truth |
| Canonical fact | `context_events.py` | `read_api.py`, `dispatch.py` | No — build/parse in `context_events.py`, projection in `read_api.py` |
| Public usage view | `api.py` | `read_api.py`, `entrypoint_runtime.py` | No — `HostContextUsageView` defined in `api.py`, projected in `read_api.py` |
| Threshold ratio policy | `context_policy.py` | `context_budget.py` | No — `ContextBudgetPolicy` from `context_policy.py`, consumed by sizing |
| Provider usage presence | Engine (observation) | Host ingest (durable) | No — Host only consumes actual `USAGE_REPORTED`, never infers from provider name |

### 11. README Update Check

- `dayu/host/README.md`: Updated with context governance section changes (anchor resolver, five-stage matrix, manifest-before-start invariant, `CONTEXT_BUDGET_EVALUATED` projection). ✅
- `dayu/service/README.md`: Minor update (2 lines). ✅
- `tests/README.md`: Updated (6 lines). ✅

---

## Open Questions

None.

---

## Residual Risk

1. **Flaky test** (`test_open_host_active_cancel_watchdog_public_watch_observes_cancelled`): 线程 id 重复断言，与本次 PR 无关，pre-existing。建议后续单独修复。

2. **Large PR surface area** (139 files, 36k+ lines): 这是三个 Slice 加 aggregate review 产物的累积。虽然每个 Slice 都经过独立 review 和 controller adjudication，但 whole-PR diff 包含大量 review artifact 文件（docs/reviews/），增加 review 噪音。建议 merge 前确认 review artifacts 是否应保留在主分支。

3. **Controller docs excluded**: `docs/host/issues-implementation-control.md` 有未提交的 working change，按指令排除在本次 review 之外。

---

## Verification Artifacts

- `tests/host/test_context_budget.py` — 85 tests, conservative estimator & five-stage matrix
- `tests/host/test_context_budget_evaluated.py` — 12 tests, canonical fact roundtrip & projection
- `tests/host/test_context_anchor.py` — 22 tests, anchor resolver & barrier mechanism
- `tests/host/test_engine_ingest_mapping.py` — 5 usage-specific tests, non-failing projection
- `tests/host/test_dispatch_scheduler.py` — 14 budget-specific tests, manifest-before-start
- pyright `dayu/host/` — 0 errors
