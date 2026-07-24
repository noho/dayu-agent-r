# WU-CTX-01 PR #183 Review-Fix Re-Review — AgentDS

## 1. Review metadata

- **角色**：AgentDS（独立 reviewer），只 review，不实现、不改 production/tests/control、不 commit/push/改 PR
- **目标**：CTRL-PR-01 修复的 re-review（Codex 实施后）
- **PR head**：`ae524fe0`
- **Review range**：`ae524fe0..working-tree`
- **Controller 裁决**：`docs/reviews/wu-ctx-01-pr-183-review-controller-adjudication.md`
- **Codex fix 记录**：`docs/reviews/wu-ctx-01-pr-183-review-fix-codex.md`
- **原两路 PR review**：`wu-ctx-01-pr-183-deepreview-ds.md`、`wu-ctx-01-pr-183-deepreview-mimo.md`
- **F-DS-02（legacy recorder）**：Controller 已驳回，无新的 direct failure evidence，不重开

## 2. Scope

仅审查 CTRL-PR-01 修复及其与完整 PR 契约的交互。Controller 允许的文件修改范围：

- `dayu/host/api.py`
- `dayu/service/entrypoint_runtime.py`
- 两个 owner boundary 对应的既有 Host/Service tests
- 本 re-review artifact

不得改：Controller adjudication、两路 PR review、control doc、算法/schema、rejected path、commit。

## 3. Verified claim set

| # | Claim | Method | Result |
|---|-------|--------|--------|
| C1 | `HostContextUsageView` 拒绝 `soft >= hard` | 读代码 `api.py:3107` | `>=` operator，错误文本 `must be less than` |
| C2 | `EntrypointContextUsage` 拒绝 `soft >= hard` | 读代码 `entrypoint_runtime.py:232` | `>=` operator，错误文本 `must be less than` |
| C3 | 合法 `soft < hard` 保持 | 读代码 + 测试 | 现有 canonical fact roundtrip tests pass |
| C4 | Host owner test 直接覆盖 equality | 读测试 `test_context_budget_evaluated.py:104` | `replace(usage, soft=hard)` → `pytest.raises(ValueError, match=...)` |
| C5 | Service owner test 直接覆盖 equality | 读测试 `test_entrypoint_runtime.py:1355` | 同上 pattern |
| C6 | 算法未漂移 | `grep` context_budget.py/context_anchor.py/context_events.py diff | 空 diff |
| C7 | Canonical fact schema 未漂移 | 同上 | 空 diff |
| C8 | 七字段 shape 未漂移 | 读 `api.py:3071-3077`、`entrypoint_runtime.py:196-202` | 字段名/类型/顺序未变 |
| C9 | Projection mapping 未漂移 | `grep` read_api.py diff | 空 diff |
| C10 | `context_budget.py` canonical owner 未漂移 | `grep` diff | 空 diff |
| C11 | Legacy recorder 未漂移 | `grep` `_runner_call_manifest.py`/`run_input.py` diff | 空 diff |
| C12 | 无 fallback/兼容 shim | 全文审计 production diff | 仅 operator 和错误文本变更，无新增代码路径 |
| C13 | 无 stale `soft > hard` | `grep -rn 'soft.*>.*hard' dayu/` | 0 hits（5 处全为 `>=`） |
| C14 | Production diff 在 allowlist 内 | `git diff --stat` | 仅 4 个 tracked production+test 文件 |
| C15 | 受保护文件完整 | SHA-256 vs Codex artifact | 4/4 匹配 |
| C16 | pyright clean | `python -m pyright dayu/ tests/ utils/` | 0 errors, 0 warnings, 0 informations |
| C17 | Diff whitespace clean | `git diff --check` | pass |
| C18 | README 未误触发 | `git diff --stat -- *README*` | 空 diff |

## 4. Test evidence

### 4.1 Focused owner nodes

```
pytest -q \
  tests/host/test_context_budget_evaluated.py::test_host_context_usage_view_requires_strict_threshold_ordering \
  tests/service/test_entrypoint_runtime.py::test_entrypoint_context_usage_requires_strict_threshold_ordering \
  tests/host/test_context_budget_evaluated.py::test_soft_threshold_must_be_strictly_less_than_hard_across_boundaries \
  tests/service/test_entrypoint_runtime.py::test_submit_entrypoint_turn_maps_context_usage_without_recalculation
```

结果：**4 passed**.

### 4.2 Full Host + Service

```
pytest -q tests/host tests/service
```

结果：**2501 passed, 2 skipped, 6 deselected**. 本 run 未命中 cancel-watchdog 时序抖动。

### 4.3 Branch coverage

```
--cov=dayu.host.api --cov=dayu.service.entrypoint_runtime --cov-branch
```

结果：
- `dayu/host/api.py`：**90%**
- `dayu/service/entrypoint_runtime.py`：**83%**
- Changed production union：**87%**

两个 changed production files 均 ≥80%。

## 5. Finding closure

### CTRL-PR-01 — `已闭合`

Controller 要求的 4 项修复全部验证通过：

1. ✅ 两个 public DTO boundary 均拒绝 `soft >= hard`，错误文本明确 `must be less than`
2. ✅ Host owner test：`test_host_context_usage_view_requires_strict_threshold_ordering` — direct constructor equality fail-closed + 合法 strict ordering 接受
3. ✅ Service owner test：`test_entrypoint_context_usage_requires_strict_threshold_ordering` — 同上 pattern
4. ✅ 未改七字段 shape、canonical fact schema、projection mapping、threshold calculation、`context_budget.py` owner

### F-DS-02 — `已驳回（不重开）`

Controller 已驳回为 non-defect（conservative contract for legacy boundary）。无新的 direct failure evidence，不重开。

## 6. New actionable findings

**无。**

两条 production boundary、两条 owner test 的修改精确限定在 Controller 接受的 CTRL-PR-01 范围内。没有观察到新的 correctness、stability、maintainability、semantic ownership drift 或类型安全缺陷。

## 7. Cancel-watchdog 时序抖动

本 re-review 的 full Host + Service run（2501 passed）未命中该抖动。Codex fix 记录中首次 run 命中一次（2500 passed, 1 failed），立即复跑通过。Controller 已记录为非 blocking test residual。本次未观察到新证据将其归因于 context usage DTO 或本次 fix。维持 Controller 裁决：不接受 production fix。

## 8. Residual risk

| 风险 | 等级 | 说明 |
|------|------|------|
| Cancel-watchdog 时序抖动 | Low | Controller 已记录，与本次 fix 无关 |
| Coverage instrumentation 下 session-cancel 回调次数抖动 | Low | Codex 记录，无插桩 clean run 通过，归因于 Host cancellation 独立 work unit |

CTRL-PR-01 修复本身无剩余 correctness、schema、mapping 或 coverage 缺口。

## 9. Verdict

### `PASS`

CTRL-PR-01 修复正确、完整、最小。两处 public DTO boundary 的 `soft >= hard` rejection 与 canonical owner `validate_context_threshold_ordering` 一致；owner tests 直接证明 equality fail-closed；算法、schema、七字段 shape、projection mapping、context_budget owner、legacy recorder 均未漂移；无 fallback、兼容 shim 或超出 allowlist 的修改。测试证据（2501 passed, pyright 0 errors, branch coverage 87%）充分。无新 actionable findings。

## 10. Artifact path

`docs/reviews/wu-ctx-01-pr-183-review-fix-rereview-ds.md`
