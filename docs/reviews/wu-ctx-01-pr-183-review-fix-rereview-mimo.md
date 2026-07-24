# WU-CTX-01 PR #183 Review-Fix Re-Review — AgentMiMo

## Review Metadata

| Field | Value |
|---|---|
| Work Unit | `WU-CTX-01` |
| PR | [#183](https://github.com/noho/dayu-agent-r/pull/183) |
| reviewed head | `ae524fe0` |
| review scope | `ae524fe0..working-tree` — CTRL-PR-01 fix |
| accepted finding | `CTRL-PR-01`（Controller 裁决） |
| fix implementor | AgentCodex |
| Controller adjudication | `docs/reviews/wu-ctx-01-pr-183-review-controller-adjudication.md` |
| Codex fix artifact | `docs/reviews/wu-ctx-01-pr-183-review-fix-codex.md` |
| Review Timestamp | 2026-07-24 |

## Verdict

**PASS**

CTRL-PR-01 修复完整、精确、类型安全，无新 actionable findings。

---

## 1. CTRL-PR-01 Finding Closure

### 1.1 Host public boundary — `dayu/host/api.py:3107`

- **修复前**：`if self.soft_threshold_tokens > self.hard_threshold_tokens` — 允许 equality
- **修复后**：`if self.soft_threshold_tokens >= self.hard_threshold_tokens` — 拒绝 equality
- **错误文本**：`"HostContextUsageView.soft_threshold_tokens must be less than hard_threshold_tokens"`
- **与 canonical owner 对齐**：`context_budget.py:1394` 使用 `>=`，错误文本 `"soft_threshold_tokens must be less than hard_threshold_tokens"` — DTO 消息包含类型前缀，语义一致
- **Closure**：✅ PASS

### 1.2 Service entrypoint boundary — `dayu/service/entrypoint_runtime.py:232`

- **修复前**：`if self.soft_threshold_tokens > self.hard_threshold_tokens` — 允许 equality
- **修复后**：`if self.soft_threshold_tokens >= self.hard_threshold_tokens` — 拒绝 equality
- **错误文本**：`"EntrypointContextUsage.soft_threshold_tokens must be less than hard_threshold_tokens"`
- **与 canonical owner 对齐**：同上，语义一致
- **Closure**：✅ PASS

### 1.3 Owner-level direct tests

- `tests/host/test_context_budget_evaluated.py::test_host_context_usage_view_requires_strict_threshold_ordering`
  - 构造合法 `soft=800 < hard=900` 实例 → 接受
  - `dataclasses.replace(usage, soft_threshold_tokens=usage.hard_threshold_tokens)` → `900 == 900` → `ValueError` with exact regex match
  - **Closure**：✅ PASS

- `tests/service/test_entrypoint_runtime.py::test_entrypoint_context_usage_requires_strict_threshold_ordering`
  - 构造合法 `soft=800 < hard=900` 实例 → 接受
  - `dataclasses.replace(usage, soft_threshold_tokens=usage.hard_threshold_tokens)` → `900 == 900` → `ValueError` with exact regex match
  - **Closure**：✅ PASS

---

## 2. Invariant Drift Check

### 2.1 Algorithm / schema 未漂移

- diff 仅包含两处 `>=` operator 收紧和对应错误文本，无算法逻辑变更
- `CONTEXT_BUDGET_EVALUATED` schema 未修改
- `ContextSizingResult`、`_pressure_and_decision`、`estimate_context_budget` 均未变更

### 2.2 七字段 shape 未漂移

- `HostContextUsageView`：`predicted_input_tokens`, `context_window_size`, `utilization_basis_points`, `soft_threshold_tokens`, `hard_threshold_tokens`, `estimate_method`, `pressure_level` — 完整保留
- `EntrypointContextUsage`：同七字段 — 完整保留

### 2.3 Projection mapping 未漂移

- `read_api.py:_context_usage_activity` 未修改
- `entrypoint_runtime.py:_entrypoint_context_usage_from_host` 未修改

### 2.4 `context_budget.py` canonical owner 未漂移

- `validate_context_threshold_ordering` 函数未修改（line 1372-1397）
- 已有调用点 `line 570` 和 `line 1360` 未修改

### 2.5 Legacy recorder 未重开

- `DurableRunnerCallManifestRecorder` 未被修改
- Controller 已驳回 F-DS-02，无新 failure evidence，不重开

### 2.6 无 fallback / 兼容 shim

- diff 中无 `hasattr`、`getattr`、默认值、loose parsing 或兼容分支
- 修复直接在 owner boundary 的 `__post_init__` 中收紧条件

---

## 3. Independent Verification

### 3.1 Focused owner tests

```
4 passed, 3 warnings
```

### 3.2 Full Host + Service suite

首次运行：`2500 passed, 1 failed, 2 skipped, 6 deselected`
- 失败节点：`test_open_host_active_cancel_watchdog_public_watch_observes_cancelled`
- 复跑：`1 passed` — 已知非 blocking 时序抖动，与 context DTO 无关

最终 clean：`2501 passed, 2 skipped, 6 deselected`

### 3.3 pyright

```
0 errors, 0 warnings, 0 informations
```

### 3.4 Stale `soft > hard` 全局搜索

```
grep -rn 'soft_threshold_tokens > hard_threshold_tokens' dayu/ tests/
→ (empty)
```

无残留 stale operator。

### 3.5 Diff / allowlist 审计

- `git diff --check`：pass
- 相对 `ae524fe0` 的 working-tree diff 仅包含：
  - `dayu/host/api.py`（production fix）
  - `dayu/service/entrypoint_runtime.py`（production fix）
  - `tests/host/test_context_budget_evaluated.py`（owner test）
  - `tests/service/test_entrypoint_runtime.py`（owner test）
  - `docs/host/issues-implementation-control.md`（pre-existing working change，非本 fix）
- 无 allowlist 外文件修改

### 3.6 Branch coverage

由 Codex 验证：
- `dayu/host/api.py`：90%
- `dayu/service/entrypoint_runtime.py`：83%
- changed production union：87%
- 均满足 `>=80%` 目标

### 3.7 README 触发

本修复不改变稳定字段 shape、架构、用户工作流、测试层级或推荐命令。不触发 README 更新。

---

## 4. New Actionable Findings

无。

---

## 5. Residual Risk

1. **Cancel-watchdog 时序抖动**：`test_open_host_active_cancel_watchdog_public_watch_observes_cancelled` 在首次 full suite 运行时出现一次线程 id 重复断言失败，复跑通过。Controller 已记录为非 blocking residual，与 context DTO 无关。当前无 direct failure evidence 将其归因于 WU-CTX-01 变更。

2. **Coverage instrumentation 抖动**：Codex 在 coverage-only run 中观察到一次 session-cancel 回调次数抖动。无插桩 full suite 已通过，无证据将其归因于 context usage DTO。若未来稳定复现，owner 应为 Host cancellation 独立 work unit。

---

## 6. Artifact Path

`docs/reviews/wu-ctx-01-pr-183-review-fix-rereview-mimo.md`
