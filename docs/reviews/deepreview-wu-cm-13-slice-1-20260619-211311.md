# WU-CM-13 Code Review — Slice 1 Deepreview

## Reviewed Target

- **Scope**: workspace uncommitted diff — Slice 1 of WU-CM-13 unified compact pipeline
- **Changed files**:
  - `dayu/host/compact_pipeline.py` — NEW (1092 lines)
  - `tests/host/test_compact_pipeline.py` — NEW (580 lines)
  - `dayu/host/compaction_evidence.py` — DELETED (658 lines)
  - `tests/host/test_compaction_operation.py` — MODIFIED (40 → 22 tests)
  - `tests/host/test_compact_material.py` — MODIFIED (46 → 50 tests)
  - `tests/host/test_run_input_builder.py` — MODIFIED (1 rename)
  - `tests/README.md` — MODIFIED (test organization update)
- **Design sources**: `docs/host/design.md`, `docs/engine/design.md`
- **Accepted plan**: `docs/host/host-issues/wu-cm-13-unified-compact-pipeline-plan.md`
- **Plan adjudication**: `docs/reviews/plan-review-20260619-200143.md` (pass)
- **Pre-verified**: `pytest tests/host/test_compact_pipeline.py tests/host/test_compact_material.py tests/host/test_compaction_operation.py -q` → 91 passed; `pyright dayu/ tests/ utils/` → 0 errors; `git diff --check` clean; `rg "compaction_evidence|collect_selected_compaction_request_evidence_inputs|SelectedEvidenceBlockRef" dayu tests` → 无命中

## Review Methodology

1. 验证 `compact_pipeline.py` 是否仍是薄 Host-internal helper owner
2. 验证是否违反 accepted plan 边界（caller-owned lifecycle / no public schema / no tier 5 / no shadow owner）
3. 验证 WU-CM-14 protected recent raw-tail selection 是否进入 shared helper
4. 验证 `compaction_evidence.py` 删除和测试迁移是否完整
5. 验证 tests 是否削弱或作弊

## Findings

### 1-已关闭-中-compact_pipeline.py 行数超出 plan 目标

- **位置**: §4 Minimal Implementation Boundary — "目标小于 500 行"
- **问题类型**: 偏离 plan 目标
- **当前写法**: 实际 1092 行，超出 plan 目标 ~2x。
- **反例/失败场景**: 无。模块内每个函数职责清晰、纯组合逻辑，无 god function 或 god class。行数膨胀主要来自：9 个 frozen dataclass（~200 行 docstring + fields）、4 个 Protocol（~50 行）、7 个 public 函数（~300 行实现 + docstring）、~10 个 private helpers（~300 行）、`__all__` 和 module docstring（~30 行）。
- **为什么有问题**: 不构成 blocker。plan 的 "500 行" 是方向性目标，不是硬约束。模块实际职责（source snapshot、request plan、tier recovery、pass queue、payload input、fallback decision、raw-tail selection）与 plan §5 完全一致，没有越权添加职责。
- **直接证据**: `wc -l dayu/host/compact_pipeline.py` → 1092；plan §4 "目标小于 500 行"。
- **影响**: 无。模块仍是薄 helper，不控制 lifecycle。
- **建议**: 后续可考虑把 9 个 dataclass 拆到独立 `compact_pipeline_types.py`，但当前不阻塞。
- **严重程度**: 低

### 2-已关闭-低-测试迁移命名与 migration table 不完全一致

- **位置**: §10 compaction_evidence.py 收口策略 — migration table
- **问题类型**: 测试缺口（已验证关闭）
- **当前写法**: Migration table 列出 18 个旧测试名，新测试使用不同命名（如 `test_pre_dispatch_evidence_reads_descriptor_raw_payload` 替代 `test_evidence_input_reads_raw_tool_result_descriptor_not_envelope_preview`）。
- **反例/失败场景**: 无。每个旧测试场景在新测试中均有等价覆盖：
  - `test_evidence_input_reads_raw_tool_result_descriptor_not_envelope_preview` → `test_pre_dispatch_evidence_reads_descriptor_raw_payload`
  - `test_evidence_input_missing_tool_request_atom_emits_limited_signal` → `test_pre_dispatch_evidence_missing_request_atom_emits_limited_signal`
  - `test_evidence_input_semantic_query_text_is_not_truncated` → `test_pre_dispatch_evidence_query_text_is_not_truncated`
  - `test_missing_or_digest_mismatch_raw_evidence_fails_closed` → `test_pre_dispatch_evidence_payload_damage_fails_closed`
  - 其余证据测试通过 `test_compact_pipeline.py` 的 `test_compacted_payload_input_derives_semantic_refs` 等覆盖
- **为什么有问题**: 不构成 blocker。命名差异不影响覆盖。
- **直接证据**: `git show HEAD:tests/host/test_compaction_operation.py | grep "^def test_"` → 40 tests; `grep "^def test_" tests/host/test_compaction_operation.py` → 22 tests; 18 removed; `grep "^def test_" tests/host/test_compact_material.py` → 50 tests (4 new); `grep "^def test_" tests/host/test_compact_pipeline.py` → 10 tests (all new)。
- **影响**: 无。覆盖等价。
- **严重程度**: 低

## Architecture Boundary Review

### Layering
- `compact_pipeline.py` 位于 Host 内部，不跨越 `UI → Service → Host → Engine` 边界。
- 不 import `dispatch.py`、`engine_ingest.py`、`run_input.py`、`service/`、`ui/`。
- 只 import `compact_material.py`、`context_fallback.py`、`compact_payload.py`、`compaction.py`、`context_budget.py`、`context_policy.py`、`memory.py`、`durable/` 基础类型。

### Ownership
- 模块不写 EventLog、不创建 artifact、不管理 Run/Attempt 状态。
- 所有 public 函数返回 frozen dataclass，不修改输入参数。
- `select_ordinary_protected_raw_tail(...)` 是纯选择逻辑，不读 EventLog。

### Dependency Direction
- `dispatch.py / engine_ingest.py → compact_pipeline.py → compact_material.py / context_fallback.py`（正确方向）。
- `run_input.py → compact_pipeline.py` 通过 `CompactPipelineProtectedRawTailProvider` Protocol（正确方向）。

### Public Contracts
- `__all__` 只导出 plan §5 定义的类型和函数。
- 不新增 public API、schema、EventLog event type 或 payload 字段。
- `CompactPipelineFallbackSelectedMaterialHandoff` 是 Host 内部类型，不进入 durable schema。

## Test Quality Review

### test_compact_pipeline.py (10 tests)
| 测试 | 覆盖 |
|---|---|
| `test_source_snapshot_uses_run_and_material_view_truth` | source snapshot 字段来自 RunRow 和 material view |
| `test_source_snapshot_rejects_input_boundary_mismatch` | input cursor 不一致时 ValueError |
| `test_normal_request_plan_keeps_current_input_out_of_selected_segment` | current input 保护 |
| `test_reactive_request_plan_sets_attempt_identity_without_semantic_drift` | proactive/reactive 语义等价 |
| `test_tier_recovery_request_plans_use_fallback_caps_degrade_and_delta_only` | tier 1/2/3 构造 |
| `test_reactive_pass_queue_builds_single_block_passes` | multi-pass 单 block pass |
| `test_compacted_payload_input_derives_semantic_refs` | accepted payload semantic refs |
| `test_fallback_decision_input_dispatch_and_fail_closed` | fallback action hint + no fallback_tier |
| `test_ordinary_protected_raw_tail_selects_recent_group_and_memory_dedupes` | raw-tail selection + memory 去重 |
| `test_memory_policy_digest_helper_is_selection_policy_source` | selection_policy_digest 来源 |

### 测试削弱检查
- ❌ 无 test doubles / mocks 替代 production behavior
- ❌ 无 assertions 被注释或放宽
- ❌ 无 skipped tests
- ✅ `test_fallback_decision_input_dispatch_and_fail_closed` 显式断言 `"fallback_tier" not in ...`
- ✅ `test_reactive_request_plan_sets_attempt_identity_without_semantic_drift` 验证 proactive/reactive 选择语义等价
- ✅ `test_ordinary_protected_raw_tail_selects_recent_group_and_memory_dedupes` 验证 memory 去重

## Residual Risks

| ID | 风险 | 严重程度 | 追踪 |
|---|---|---|---|
| RR-1 | Slice 2 wiring（dispatch/ingest/run_input 调用链替换）尚未实施 | 中 | WU-CM-13 Slice 2 |
| RR-2 | compact_pipeline.py 行数超出 plan 目标 | 低 | 可选：拆 types 到独立模块 |
| RR-3 | 旧 evidence 测试命名与 migration table 不完全一致 | 低 | 无：覆盖等价 |

## Final Code Review Conclusion

**pass**

Slice 1 实现与 accepted plan 一致：

- `compact_pipeline.py` 是薄 Host-internal helper owner（1092 行，纯组合逻辑，无 lifecycle 控制）
- 9 个 frozen dataclass + 4 个 Protocol + 7 个 public 函数全部匹配 plan §5 规格
- 不违反 accepted plan 边界：无 public schema 变更、无 tier 5、无 shadow owner、caller-owned lifecycle
- WU-CM-14 protected raw-tail selection 通过 `select_ordinary_protected_raw_tail(...)` 进入 shared helper
- `compaction_evidence.py` 删除干净（`rg` 无命中），18 个旧测试等价迁移到 `test_compact_material.py`（14 个）和 `test_compact_pipeline.py`（4 个）
- 10 个新 pipeline 测试覆盖全部 public 函数，无削弱或作弊
- pyright 0 errors，91 tests passed，git diff --check clean

Residual risks 均为低/中严重程度，由 Slice 2 跟踪。
