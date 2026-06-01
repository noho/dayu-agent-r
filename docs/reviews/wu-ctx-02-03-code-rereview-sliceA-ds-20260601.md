# WU-CTX-02 + WU-CTX-03 Slice A Focused Code Re-Review — DS

- Gate: WU-CTX-02 + WU-CTX-03 Slice A focused code re-review
- Source review: `docs/reviews/wu-ctx-02-03-code-review-sliceA-ds-20260601.md`
- Controller adjudication: `docs/reviews/wu-ctx-02-03-code-controller-adjudication-sliceA-20260601.md`
- Fix artifact: `docs/reviews/wu-ctx-02-03-fix-sliceA-codex-20260601.md`
- Re-review artifact: `docs/reviews/wu-ctx-02-03-code-rereview-sliceA-ds-20260601.md`
- Reviewer: AgentDS
- Review scope: 仅复核 DS-F1 是否已修复，确认未扩大 scope

## Focused Finding: DS-F1

**原始问题**: `tests/service/test_host_assembly.py` 中 `_write_execution_profile_overlay` helper 的 workspace overlay fixture 内 `max_compaction_attempts_per_operation: 3`，该值恰好等于旧 packaged profile 默认值，保留会造成未来读者误读。

**Controller 裁决**: accepted — 改为显著不同于 packaged default `5` 的值，例如 `7`。

**Fix artifact 声明**: 已将 `3` 改为 `7`。

## Re-Review Verification

### 1. 当前工作树实际值验证

`tests/service/test_host_assembly.py` 第 874 行（当前行号）：

```
"max_compaction_attempts_per_operation": 7,
```

- 值已从 `3` 改为 `7` ✅
- `7` 显著不同于 packaged default `5` ✅
- 使用该 fixture 的测试（`test_truncation_manager_enabled_is_derived_from_execution_profile`、`test_explicit_1m_profile_with_256k_model_fails_fast`）不对该字段做断言，不受影响 ✅

### 2. Scope Boundary 验证

| 检查项 | 状态 | 证据 |
|--------|------|------|
| 仅修改 `tests/service/test_host_assembly.py` | ✅ | `git diff HEAD --stat` 该文件 +10/-1 |
| 未新增 production code | ✅ | diff 中无 `dayu/host/`、`dayu/service/` 等 production 路径在此轮新增 |
| 未改变 schema | ✅ | 无 schema 文件变更 |
| 未改变 public API | ✅ | 无 API/RPC/shape 变更 |
| 未改变 Service request shape | ✅ | 无 Service 层变更 |

全量 diff 覆盖 7 文件，均为 Slice A 原有变更 + DS-F1 fix。除 fixture 值 `3→7` 外无任何超出 Slice A approved plan 的改动。

### 3. Validation

| 命令 | 结果 |
|------|------|
| `pytest tests/host/test_context_policy.py tests/runtime/test_config_loader.py tests/runtime/test_scene_assets_migration.py tests/service/test_host_assembly.py -q` | 74 passed in 0.35s |
| `python -m pyright dayu/ tests/ utils/` | 0 errors, 0 warnings, 0 informations |

## DS-F1 Final Status

**已修复**

- Fixture 值 `3→7`，与 packaged default `5` 的差距从 `|3-5|=2` 提升到 `|7-5|=2`（等距反方向，但语义从"碰巧等于旧默认"变为"显式非默认值"）
- 注释意图明确：workspace overlay 值独立于 package default，`7` 为故意选择的不同值
- 无 scope creep，无残留问题

## Residual Risks

无新增 residual risk。原 source review 中记录的 4 个 residual risks（非默认 profile compactor model 一致性、`context_budget_policy_from_threshold_tokens` 默认值路径测试、连续 overflow/compact failure E2E 覆盖）属于 Slice B-E 或后续 WU 范围，不受本次 fix 影响。

## Conclusion

DS-F1 已修复。Fix 精确、scope 未扩大。validation 全部通过。无 unresolved issue，无 blocking question。
