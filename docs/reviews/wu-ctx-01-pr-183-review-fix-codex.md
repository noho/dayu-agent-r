# WU-CTX-01 PR #183 Review Fix — AgentCodex

## 1. Gate 与基线

- Work Unit：`WU-CTX-01`
- 类型：GitHub Issue #20 对应的 architecture-sensitive issue / public-contract change
- gate：PR review `fix`
- reviewed head：`ae524fe0`
- accepted finding：仅 `CTRL-PR-01`
- Controller 裁决：
  `docs/reviews/wu-ctx-01-pr-183-review-controller-adjudication.md`
- completion status：`已修复`
- blocking open questions：None

本 artifact 只记录 Controller 已接受 finding 的实现与验证，不重做 finding
裁决，不推进 re-review、commit、push、PR 或 final closeout gate。

## 2. First-principles 与 owner 证据

问题真实成立，但范围只是一处 public contract operator 漂移，不是 sizing
算法或 schema 缺陷：

1. canonical owner
   `dayu.host.context_budget.validate_context_threshold_ordering` 对
   `soft_threshold_tokens >= hard_threshold_tokens` fail closed，并明确要求
   soft 必须小于 hard；
2. `ContextSizingResult`、decision helper 与 durable canonical parser 均复用该
   invariant；
3. `HostContextUsageView` 与 `EntrypointContextUsage` 修改前只拒绝
   `soft_threshold_tokens > hard_threshold_tokens`，因此 direct constructor 可以
   表达 canonical fact 不可能产生的 equality 状态；
4. 正确修复边界是两个 typed public DTO 自身，不是 projection fallback、下游重算、
   默认值、loose parsing 或修改 `context_budget.py`。

## 3. `CTRL-PR-01` 修复明细

### 3.1 Host public boundary

- 文件：`dayu/host/api.py`
- owner：`HostContextUsageView.__post_init__`
- 修复：
  - threshold 顺序判断从 `soft > hard` 收紧为 `soft >= hard`；
  - 错误文本改为
    `HostContextUsageView.soft_threshold_tokens must be less than hard_threshold_tokens`，
    明确表达 strict ordering。

### 3.2 Service entrypoint boundary

- 文件：`dayu/service/entrypoint_runtime.py`
- owner：`EntrypointContextUsage.__post_init__`
- 修复：
  - threshold 顺序判断从 `soft > hard` 收紧为 `soft >= hard`；
  - 错误文本改为
    `EntrypointContextUsage.soft_threshold_tokens must be less than hard_threshold_tokens`，
    明确表达 strict ordering。

### 3.3 Owner-level direct tests

- `tests/host/test_context_budget_evaluated.py`
  - 新增
    `test_host_context_usage_view_requires_strict_threshold_ordering`；
  - direct constructor 证明合法 `800 < 900` 被接受；
  - `dataclasses.replace` direct constructor 证明 `900 == 900` 以精确错误文本
    fail closed。
- `tests/service/test_entrypoint_runtime.py`
  - 新增
    `test_entrypoint_context_usage_requires_strict_threshold_ordering`；
  - direct constructor 证明合法 `800 < 900` 被接受；
  - `dataclasses.replace` direct constructor 证明 `900 == 900` 以精确错误文本
    fail closed。

## 4. 明确未改

- 未改 context sizing 算法、threshold calculation 或
  `dayu/host/context_budget.py` canonical owner；
- 未改 `CONTEXT_BUDGET_EVALUATED` schema 或任何 canonical fact 字段；
- 未改 Host/Service public 七字段 shape：
  `predicted_input_tokens`、`context_window_size`、
  `utilization_basis_points`、`soft_threshold_tokens`、
  `hard_threshold_tokens`、`estimate_method`、`pressure_level`；
- 未改 `read_api` public projection 或
  `_entrypoint_context_usage_from_host` 逐字段 mapping；
- 未改 legacy recorder、`RunInputBuilder` 或其它 rejected path；
- 未改 README、Controller control/adjudication 或两路 PR review artifacts；
- 未 commit、push 或修改 PR。

## 5. 验证结果

所有命令均在 `source .venv/bin/activate` 后执行。

### 5.1 Focused owner nodes

```text
pytest -q \
  tests/host/test_context_budget_evaluated.py::test_soft_threshold_must_be_strictly_less_than_hard_across_boundaries \
  tests/host/test_context_budget_evaluated.py::test_host_context_usage_view_requires_strict_threshold_ordering \
  tests/service/test_entrypoint_runtime.py::test_entrypoint_context_usage_requires_strict_threshold_ordering \
  tests/service/test_entrypoint_runtime.py::test_submit_entrypoint_turn_maps_context_usage_without_recalculation
```

结果：`4 passed, 3 warnings`。

### 5.2 完整 owner test files

```text
pytest -q \
  tests/host/test_context_budget_evaluated.py \
  tests/service/test_entrypoint_runtime.py
```

结果：`76 passed, 3 warnings`。

### 5.3 Full Host + Service

```text
pytest -q tests/host tests/service
```

最终 clean 结果：`2501 passed, 2 skipped, 6 deselected, 3 warnings`。

首次运行命中 Controller 已记录的既有
`test_open_host_active_cancel_watchdog_public_watch_observes_cancelled`
时序抖动，结果为
`2500 passed, 1 failed, 2 skipped, 6 deselected`；失败是
`token_threads` 重复次数断言。该节点立即复跑为 `1 passed`，随后上述完整
Host + Service clean 复跑通过。

### 5.4 Changed production branch coverage

使用 Host + Service suite 开启 branch coverage；coverage instrumentation 与 macOS
spawn 不兼容，故 coverage-only run 排除
`tests/host/test_toolruntime_executor.py`，并排除两个 coverage 下出现并发次数抖动、
但无插桩完整 suite 已通过的 cancel nodes：

```text
pytest -q tests/host tests/service \
  --ignore=tests/host/test_toolruntime_executor.py \
  --deselect=tests/host/test_open_host_runtime.py::test_open_host_active_cancel_watchdog_public_watch_observes_cancelled \
  --deselect=tests/host/test_public_cancel_smoke.py::test_cancel_session_runs_scoped_to_session \
  --cov=dayu.host.api \
  --cov=dayu.service.entrypoint_runtime \
  --cov-branch \
  --cov-report=term-missing:skip-covered
```

clean 结果：

- tests：`2431 passed, 2 skipped, 8 deselected, 3 warnings`
- `dayu/host/api.py`：`90%`
- `dayu/service/entrypoint_runtime.py`：`83%`
- changed production union：`87%`

两个 changed production files 均满足 branch coverage `>=80%`。

### 5.5 Full pyright

```text
python -m pyright dayu/ tests/ utils/
```

结果：`0 errors, 0 warnings, 0 informations`。

### 5.6 Diff、allowlist、stale 与 README audit

- `git diff --check`：pass；
- relative base：`ae524fe0`，当前 HEAD 仍为 `ae524fe0`；
- AgentCodex tracked code/test diff 仅：
  - `dayu/host/api.py`
  - `dayu/service/entrypoint_runtime.py`
  - `tests/host/test_context_budget_evaluated.py`
  - `tests/service/test_entrypoint_runtime.py`
- 新增 AgentCodex artifact 仅：
  `docs/reviews/wu-ctx-01-pr-183-review-fix-codex.md`；
- 相对 `ae524fe0` 额外存在的
  `docs/host/issues-implementation-control.md` dirty change 与三份 untracked
  Controller/review artifacts 均为 preflight 已存在的受保护输入，不属于本次修改；
- 两个 production boundary 中 stale
  `soft_threshold_tokens > hard_threshold_tokens` 搜索结果：0；
- production zero-context diff 只包含两处 `>=` operator 与对应明确错误文本，
  因此算法、schema、七字段 shape、projection mapping、canonical owner 与 legacy
  recorder 均未变化；
- README diff：0。Host README 只记录稳定开发契约，tests README 只在测试层级或
  运行方式变化时更新；本修复不改变稳定字段 shape、架构、用户工作流、测试层级或
  推荐命令，因此不触发 README 更新。

## 6. 受保护文件完整性

preflight 与修复后 SHA-256 保持一致：

- `docs/host/issues-implementation-control.md`：
  `382efc2e982d0fbbf59d26b264f4fa701307ca35c0b8bac672b93b2c23e79089`
- `docs/reviews/wu-ctx-01-pr-183-deepreview-ds.md`：
  `37f070fe40aaa5312f8c4f325055fb4acd8048d8ad04cced6c7aa322f8077624`
- `docs/reviews/wu-ctx-01-pr-183-deepreview-mimo.md`：
  `53470af5e93264d59ac47bd1a65a1e01640ab353e33c635301f2619545e5e5de`
- `docs/reviews/wu-ctx-01-pr-183-review-controller-adjudication.md`：
  `bfe406457411e290a67dd6020925de8724915f78a7f18520a4b4e83e1c7db54d`

## 7. Residual risk 与下一入口

- `CTRL-PR-01`：`已修复`；
- 本 finding 无剩余 correctness、schema、mapping 或 coverage 缺口；
- 已知 cancel-watchdog 时序抖动仍属于 Controller 已记录的非 blocking residual，
  本次未修改其 owner；
- coverage instrumentation 下另观察到一次 session-cancel 回调次数抖动；无插桩
  full Host + Service clean 通过，当前没有证据将其归因于 context usage DTO。
  若未来在无 coverage 环境稳定复现，owner/destination 应为 Host cancellation
  独立 work unit，不进入 WU-CTX-01 PR review fix；
- 下一入口：由 Controller 派发 AgentMiMo / AgentDS 相对
  `ae524fe0` 执行 PR review-fix re-review。

## 8. Artifact path

`docs/reviews/wu-ctx-01-pr-183-review-fix-codex.md`
