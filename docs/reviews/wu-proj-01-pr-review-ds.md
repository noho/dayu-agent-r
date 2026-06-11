# WU-PROJ-01 PR Review — AgentDS

## 元数据

- Work unit: `WU-PROJ-01`
- Gate: PR review (draft PR gate)
- 审查人: AgentDS
- 日期: 2026-06-11
- PR: [#136](https://github.com/noho/dayu-agent-r/pull/136) (draft, wu-proj-01 → main)
- 本地 HEAD: `228c5e44`
- 审查范围: PR #136 相对 `main` 的完整 diff (12 commits, `fb3cc9ec` → `228c5e44`)

## Preflight

| 检查项 | 结果 |
|---|---|
| 当前分支 | `wu-proj-01` ✅ |
| 工作树状态 | clean ✅ |
| PR head/base | `wu-proj-01` → `main` ✅ |
| PR 状态 | Draft, OPEN ✅ |
| 本地 HEAD = PR head | `228c5e44` ✅ |
| 本地 commit 数 = PR commit 数 | 12 = 12 ✅ |
| PR diff 与本地 branch 一致 | ✅ |

## 审查结论

**FAIL**

3 个既有测试在 PR 变更后回归，PR body 声称的测试通过率不完整。

---

## Blocking Findings

### F1: 3 个既有 dispatch scheduler 测试回归 (BLOCKING)

**严重程度**: BLOCKING

**现象**:
```
FAILED tests/host/test_dispatch_scheduler.py::test_dispatch_lag_repair_rebuild_retry_does_not_fail_run
FAILED tests/host/test_dispatch_scheduler.py::test_memory_lag_pre_dispatch_failure_does_not_enter_recovering
FAILED tests/host/test_dispatch_scheduler.py::test_persistent_memory_lag_repair_failure_closes_starting_run
```

**完整测试结果**:
- 受影响测试文件全集: `185 selected, 3 failed, 182 passed`
- 3 个失败均在同一文件 `tests/host/test_dispatch_scheduler.py`
- 其余 182 个测试全部通过

**根因**:

Slice 3 (commit `a658ee1f`, `feat(host): bound memory projection repair`) 修改了 `_start_worker` 的 memory lag repair 行为。旧代码在 rebuild 未完全追平 required cursor 时仍允许 retry `build_run_input()` 并继续 dispatch；新代码在 `_build_run_input_with_lag_repair` 中通过 `_raise_if_memory_projection_target_not_reached` 严格校验 rebuild 结果，若未追平则抛 `_MemoryProjectionDispatchDiagnosticError`，被 `_start_worker` 的外层 catch 捕获后调用 `_safe_closeout_worker_startup_timeout` 并返回 `"timed_out"`。

3 个失败的测试均在 `main` 上存在且通过，但在本分支上因行为改变而失败。这些测试未被任何 slice review 或 aggregate deepreview 的选择性测试过滤 (`-k`) 覆盖：

- Slice 4 controller 验证: `-k "compact_failure_is_attempt_free or compact or governance"` → 25 passed, 103 deselected（排除了 lag repair 测试）
- AgentMiMo aggregate: `68 passed, 1 skipped, 123 deselected`（排除了大多数 dispatch 测试）
- AgentDS aggregate: `143 tests passed`（同样使用选择性过滤）

**证据**:

```
# 日志输出显示 rebuild 完成但未追平 required cursor:
WARNING dispatch.memory_projection.lag_rebuild_retry
  required_event_sequence=20
WARNING dispatch.memory_projection.repair_not_reached
  operation=rebuild_before_dispatch
  required_event_sequence=20 started_cursor=0 finished_cursor=5
  stop_reason=idle budget_exhausted=False
  max_batches=32 max_scanned_events=4096
```

**修复方向**:

两种可能路径，需由 controller 裁决：

A. **更新测试以匹配新行为**（推荐）: 新行为（rebuild 未追平 → fail-closed → timed_out）是 WU-PROJ-01 的 intentional design decision——"成功追到 required cursor 时继续 dispatch；超预算或失败时产生结构化 diagnostic，且不得触发 Run recovery"。若走此路径，需更新 3 个测试的断言：
   - `test_dispatch_lag_repair_rebuild_retry_does_not_fail_run`: 预期 `result.timed_out == 1` 且 Run 不进入 RECOVERING
   - `test_memory_lag_pre_dispatch_failure_does_not_enter_recovering`: 预期 Run 状态为 FAILED（非 RUNNING 也非 RECOVERING）
   - `test_persistent_memory_lag_repair_failure_closes_starting_run`: 预期 `builder.calls == 1`（不再有第二次重试）

B. **调整实现以兼容旧测试**: 若 controller 认为旧行为（rebuild 未完全追平仍允许 dispatch）是正确的，则需修改 `_raise_if_memory_projection_target_not_reached` 的调用逻辑或 `_build_run_input_with_lag_repair` 的异常处理。

### F2: PR body 测试声明不完整 (BLOCKING)

**严重程度**: BLOCKING

PR body 声明：
> - Aggregate focused tests: 143 passed by AgentDS
> - Aggregate MiMo validation: 68 passed, 1 skipped, 123 deselected
> - Slice 4 controller validation: 25 passed, 103 deselected

这些数字是通过选择性测试过滤 (`-k`) 得到的子集结果，不是受影响测试文件的完整运行结果。完整运行 `tests/host/test_compact_material.py tests/host/test_dispatch_scheduler.py tests/host/test_memory_repair.py tests/host/test_memory_projection.py tests/host/test_run_input_builder.py tests/host/test_logging.py tests/host/test_open_host_runtime.py` 的结果是 **185 selected, 3 failed, 182 passed**。

PR body 必须如实报告完整测试结果，或明确标注使用了选择性过滤及过滤条件。当前表述会误导 reviewer 认为所有受影响测试均通过。

---

## Non-Blocking Findings

### NF1: Aggregate deepreview 验证覆盖缺口

**严重程度**: LOW

Aggregate deepreview 的 controller 验证（`docs/reviews/wu-proj-01-aggregate-deepreview-controller-adjudication.md`）使用了选择性测试过滤：
- Slice 4 controller: `-k "compact_failure_is_attempt_free or compact or governance"`
- AgentMiMo: `68 passed, 1 skipped, 123 deselected`
- AgentDS: `143 tests passed`

这些过滤条件排除了 memory lag repair 相关测试（命名不含 `compact`/`governance` 关键词）。3 个失败的测试均属于 memory lag repair 行为验证，不在选择范围内。

这不是 PR body 本身的问题，但解释了为什么这些回归在 aggregate deepreview 阶段未被发现。

### NF2: 控制文档 state 微小不同步

**严重程度**: LOW

`docs/host/issues-implementation-control.md` 的当前状态表显示:
```
| gate | review |
```

与 WU-PROJ-01 条目显示的一致。但 Residual Risk 表中 `WU-PROJ-01-S3-R1` 和 `WU-PROJ-01-S4-R1` 的描述未提及 3 个既有测试在 behavior change 后需要更新。若修复路径选择"更新测试"，建议在 residual risk 或 WU-PROJ-01 条目中记录这一发现。

---

## 已验证通过的检查项

| 检查项 | 结果 |
|---|---|
| pyright (0 errors, 0 warnings, 0 informations) | ✅ |
| 受影响文件均在 plan allowed files 范围内 | ✅ |
| 无 `dayu.engine` / `dayu.service` / `dayu.ui` / `dayu.fins` 代码变更 | ✅ |
| 无 durable schema / EventLog event type 变更 | ✅ |
| 架构分层 (UI → Service → Host → Engine) 未被破坏 | ✅ |
| `dayu.runtime` 无反向依赖 | ✅ |
| 设计真源 (`docs/host/design.md`) 已同步更新 | ✅ |
| 控制文档 (`docs/host/issues-implementation-control.md`) 记录 PR #136 | ✅ |
| Aggregate deepreview artifacts 完整 | ✅ |
| Residual risks WU-PROJ-01-S3-R1, WU-PROJ-01-S4-R1 已记录 owner | ✅ |
| `dayu/host/README.md` 已按需更新 | ✅ |
| `tests/README.md` 已按需更新 | ✅ |
| 无无关文件泄漏 | ✅ |
| Plan implementation fidelity（Slice 1-4 按 plan 实施） | ✅ |
| Rolling compact 语义实现（second compact 不重展旧 raw history） | ✅ |
| EventLog-backed compact material source 不依赖 memory snapshot | ✅ |
| Bounded memory catch-up 有总预算 (max_batches + max_scanned_events) | ✅ |
| Material source failure fail-closed（不进入 RECOVERING） | ✅ |
| Reactive path 最小适配（仅复用 shared previous-view helper） | ✅ |
| Accepted compact → Conversation Memory projection → ordinary RunInput 数据流正确 | ✅ |

---

## 建议的下一步

1. **Controller 裁决 F1**: 确定修复路径（更新测试 vs 调整实现），然后将 3 个测试修复。
2. **修复 F2**: 更新 PR body，如实报告完整测试结果（包括选择性过滤条件）。
3. **修复后重新验证**: `python -m pytest tests/host/test_compact_material.py tests/host/test_dispatch_scheduler.py tests/host/test_memory_repair.py tests/host/test_memory_projection.py tests/host/test_run_input_builder.py tests/host/test_logging.py tests/host/test_open_host_runtime.py` 必须全部通过。
4. **pyright 重新验证**: `0 errors, 0 warnings, 0 informations`。
5. 完成后更新 `docs/host/issues-implementation-control.md` 的 WU-PROJ-01 条目和本 review artifact。

---

## 验证命令记录

```bash
# Preflight
git branch --show-current          # wu-proj-01
git status --short                 # clean
gh pr view 136 --json number,title,isDraft,state,url,headRefName,baseRefName

# pyright
source .venv/bin/activate && pyright --outputjson
# → errors=0, warnings=0, informations=0

# 完整受影响测试文件
source .venv/bin/activate && python -m pytest \
  tests/host/test_compact_material.py \
  tests/host/test_dispatch_scheduler.py \
  tests/host/test_memory_repair.py \
  tests/host/test_memory_projection.py \
  tests/host/test_run_input_builder.py \
  tests/host/test_logging.py \
  tests/host/test_open_host_runtime.py \
  --tb=short -q
# → 3 failed, 182 passed

# 排除 3 个失败测试后
source .venv/bin/activate && python -m pytest \
  tests/host/test_compact_material.py \
  tests/host/test_dispatch_scheduler.py \
  tests/host/test_memory_repair.py \
  tests/host/test_memory_projection.py \
  tests/host/test_run_input_builder.py \
  tests/host/test_logging.py \
  tests/host/test_open_host_runtime.py \
  --deselect tests/host/test_dispatch_scheduler.py::test_dispatch_lag_repair_rebuild_retry_does_not_fail_run \
  --deselect tests/host/test_dispatch_scheduler.py::test_memory_lag_pre_dispatch_failure_does_not_enter_recovering \
  --deselect tests/host/test_dispatch_scheduler.py::test_persistent_memory_lag_repair_failure_closes_starting_run \
  --tb=short -q
# → 182 passed
```
