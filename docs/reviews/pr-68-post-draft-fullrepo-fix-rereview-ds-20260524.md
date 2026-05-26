# PR 68 Post-Draft Full-Repo Fix Re-Review DS 20260524

## Gate

- Gate: P12.6 post-draft full-repo fix re-review for PR 68
- Branch: `feat/phase-12-5-conversation-memory-optimize`
- Reviewed artifact: `docs/reviews/pr-68-post-draft-fullrepo-fix-codex-20260524.md`
- Controller adjudication: `docs/reviews/pr-68-post-draft-fullrepo-review-controller-adjudication-20260524.md`
- Scope: A1-A9 only

## Validation Results

| Check | Result |
|---|---|
| Focused tests (A1-A9) | **95 passed in 1.26s** |
| Full test suite | **1653 passed, 1 skipped in 80.90s** |
| pyright | **0 errors, 0 warnings, 0 informations** |
| git diff --check | **CLEAN** |
| Host-prefixed ToolBundleSource import grep | **CLEAN** (zero matches) |

## Per-Finding Verification

### A1 — memory_repair.py direct tests — **FIXED**

- File: `tests/host/test_memory_repair.py` (新增, 349 行)
- Coverage:
  - `test_rebuild_resets_projection_and_finishes_empty_batch` — rebuild 先 reset、空 batch 正常终止
  - `test_catch_up_accumulates_batches_until_short_batch` — catch-up 多批聚合、短 batch 终止
  - `test_catch_up_stops_on_failure_and_counts_failure` — failure 立即终止并汇总
  - `test_catchup_port_delegates_to_catch_up_function` — ConversationMemoryProjectionCatchupPort 委托
- 验证: 4/4 测试通过

### A2 — ToolBundleSourceKind/ToolBundleSourceRef re-export removal — **FIXED**

- `dayu/host/__init__.py`: 移除 import 与 `__all__` 中的两个符号
- `dayu/host/tooling.py`: 移除 `__all__` 中两个符号；保留 `ToolBundleSourceRef` import 仅供 Host 内部使用
- `dayu/host/tool_runtime.py`: 改为从 `dayu.contracts.tool_source` 导入
- 受影响的 Host 测试文件全部更新 import: `public_smoke_support.py`, `test_package_exports.py`, `test_tooling_options.py`, `test_dispatch_scheduler.py`, `test_per_run_tool_selection.py`, `test_phase6_toolruntime_integration.py`, `test_phase7_waiting_integration.py`, `test_public_compact_smoke.py`, `test_run_input_builder.py`, `test_toolruntime_diagnostics.py`, `test_toolruntime_duplicate_governance.py`, `test_toolruntime_effective_bundle.py`, `test_toolruntime_executor.py`, `test_toolruntime_truncation_fetch_more.py`
- `grep "from dayu\.host.*import.*ToolBundleSource" --include="*.py"` 返回零匹配
- README 同步更新: `dayu/host/README.md` 移除两个符号、`tests/README.md` 更新 tooling options 测试职责描述

### A3 — default compaction attempts raised to 2 — **FIXED**

- `dayu/host/context_policy.py:22`: `DEFAULT_MAX_COMPACTION_ATTEMPTS_PER_OPERATION = 1` → `2`
- 含义: 默认允许首次 proposal + 一次 semantic repair attempt

### A4 — open-question quality check 区分原始状态 — **FIXED**

- `dayu/host/context_governance.py`:
  - `_open_questions_retained` 增加 `request` 参数
  - 新增 `_original_open_questions_present(request)` 检查 material pack 中是否有 open question / working assumption block
  - 原始无 open questions → 直接返回 `True`（不要求候补发明问题）
  - 原始有 open questions → summary 保留、CLEAR、或非空 REPLACE 均接受；MISSING 仍拒绝
- 新增测试:
  - `test_quality_accepts_clear_when_request_has_no_original_open_questions` — 无原始 open question 时 CLEAR 被接受
  - `test_quality_rejects_original_open_questions_without_retention_or_clear` — 有原始 open question 时 MISSING 被拒绝
  - `test_quality_accepts_evidence_supported_clear_for_original_open_questions` — 有原始 open question 时证据化 CLEAR 被接受

### A5 — multi-pass merge preserved refs 改为 candidate 并集 — **FIXED**

- `dayu/host/compaction_operation.py:_merge_pass_candidates`:
  - `preserved_canonical_evidence_refs` 改为 `_dedupe_strings(tuple(candidate.preserved_canonical_evidence_refs for candidate in candidates))`
  - `preserved_evidence_backed_fact_refs` 改为 `_dedupe_strings(tuple(candidate.preserved_evidence_backed_fact_refs for candidate in candidates))`
- 新增测试:
  - `test_reactive_multi_pass_merges_only_candidate_preserved_refs` — 使用 `_NoPreservedFactPassCompactor` 验证当 pass candidate 不声明 fact refs 时合并结果也不包含

### A6 — preserved-ref subset rejection test — **FIXED**

- `tests/host/test_compaction_contract.py`:
  - 新增 `test_quality_rejects_preserved_fact_ref_outside_request_subset` — 构造 `preserved_evidence_backed_fact_refs` 包含请求外 ref 的候选，断言 `accepted=False` 且 `SUMMARY_PRETENDS_EVIDENCE_BACKED_FACT` 在拒绝原因中

### A7 — tool_runtime_schema_projection functional tests — **FIXED**

- File: `tests/host/test_tool_runtime_schema_projection.py` (新增, 134 行)
- Coverage:
  - `test_valid_projection_indexes_definitions_and_digests_schema` — 有效定义投影为 name index 与 schema digest
  - `test_definitions_by_name_rejects_duplicate_names` — 拒绝重复工具名
  - `test_reserved_name_conflict_rejects_framework_tool_name` — 业务工具不得占用 framework reserved name
- 验证: 3/3 测试通过

### A8 — runtime/tool_truncation boundary tests — **FIXED**

- File: `tests/runtime/test_tool_truncation.py` (新增, 162 行)
- Coverage:
  - `test_no_truncation_disabled_spec_returns_original` — disabled spec 原样返回
  - `test_exact_declared_threshold_is_preserved` — 声明阈值不被覆盖
  - `test_truncation_missing_limit_uses_policy_default` — 缺失 limit 由 policy default 补齐
  - `test_empty_policy_defaults_reject_enabled_truncation` — 启用但无 default 时必须拒绝
  - `test_multibyte_target_path_is_preserved_as_typed_spec` — 多字节字段名保留
  - `test_default_values_must_be_strict_ints` — 非严格整数默认值被拒绝
- 验证: 6/6 测试通过

### A9 — after-commit secondary error logging — **FIXED**

- `dayu/host/durable/transaction.py`:
  - 新增 `import logging` 与 `_LOGGER = logging.getLogger(__name__)`
  - `_run_after_commit` 中: 首个错误记录后，后续 callback 错误通过 `_LOGGER.exception` 记录（含 `callback_index` 与 `first_callback_index`），不再静默丢弃
- `tests/host/test_durable_transaction.py`:
  - `test_after_commit_failure_still_attempts_later_callbacks` 增加 `caplog` 断言: 验证 `"after-commit callback secondary failure"` 与 `"callback_index=1"` 出现在 ERROR 日志中

## README Sync

- `dayu/host/README.md`: 移除 `ToolBundleSourceKind`/`ToolBundleSourceRef` 从 public exports 列表，注明由 `dayu.contracts.tool_source` 提供
- `tests/README.md`: tooling options 测试职责更新为 contracts source refs 验证

## Regression Check

- Full test suite 1653 passed, 1 skipped — 与修复前基线 (1637) 加上新增测试 (16) 减去移除测试 (2) 一致: 1637 + 4 + 4 + 1 + 3 + 6 - 2 = 1653 ✓
- pyright 全量零错误
- 无 whitespace 损坏

## Verdict

**PASS**

A1-A9 全部已修复。每项修复均经直接文件/行号证据验证、聚焦测试通过、pyright 零错误、全量测试无回归、README 同步更新。

此分支已准备好 accepted post-draft full-repo review commit。
