# WU-PROJ-01 PR Review Re-review — AgentDS

## 元数据

- Work unit: `WU-PROJ-01`
- Gate: PR review re-review gate (post-fix)
- 审查人: AgentDS
- 日期: 2026-06-11
- PR: [#136](https://github.com/noho/dayu-agent-r/pull/136)
- Fix artifact: `docs/reviews/wu-proj-01-pr-review-fix-codex.md`
- Controller adjudication: `docs/reviews/wu-proj-01-pr-review-controller-adjudication.md`
- 审查范围: Codex fix gate 工作区产物（2 个 dirty files）

## Preflight

| 检查项 | 结果 |
|---|---|
| 当前分支 | `wu-proj-01` ✅ |
| 工作树变更文件 | `docs/host/issues-implementation-control.md`, `tests/host/test_dispatch_scheduler.py` ✅ |
| 生产代码变更 | 0 文件 ✅ |
| 工作树有未跟踪文件 | `docs/reviews/wu-proj-01-pr-review-fix-codex.md` (fix artifact) ✅ |

## 审查结论

**PASS**

5 个检查点全部通过，无 blocking findings，无 non-blocking findings。

---

## 检查点 1: 3 个旧测试按 fail-closed 新设计正确迁移

**结论: PASS**

### 1a. `test_dispatch_lag_repair_rebuild_not_reached_fails_closed` (原 `test_dispatch_lag_repair_rebuild_retry_does_not_fail_run`)

| 断言项 | 旧值 | 新值 | 是否正确 |
|---|---|---|---|
| `result.dispatched` | `== 1` | `== 0` | ✅ 不 dispatch worker |
| `result.timed_out` | 未断言 | `== 1` | ✅ timed_out 语义 |
| `builder.calls` | `== 2` | `== 1` | ✅ 不进入旧 retry dispatch |
| `factory.created` | `== 1` | `== 0` | ✅ 不创建 worker |
| Run 状态 | `== RUNNING` | `== FAILED` | ✅ fail-closed |
| Attempt 状态 | 未直接断言 | `== FAILED` | ✅ |
| Dispatch record 状态 | 未直接断言 | `== CANCELLED` | ✅ |
| `RUN_FAILED` event | `== 0` | `== 1` | ✅ |
| `RUN_RECOVERING` event | 未断言 | `== 0` | ✅ 不进入 RECOVERING |
| `repair_not_reached` diagnostic | 未断言 | `in caplog.text` | ✅ 结构化 diagnostic |

- 测试名已从表达旧语义的 `_retry_does_not_fail_run` 改为表达新语义的 `_not_reached_fails_closed` ✅
- 新增 `caplog` fixture 捕获 `dayu.host.dispatch` WARNING 级 diagnostic ✅

### 1b. `test_memory_lag_pre_dispatch_failure_does_not_enter_recovering`

| 断言项 | 旧值 | 新值 | 是否正确 |
|---|---|---|---|
| `RUN_RECOVERING` event | `== 0` | `== 0` (保持) | ✅ |
| Run 状态 | `== RUNNING` | `== FAILED` | ✅ fail-closed |
| Attempt count | 未直接断言 | `== 1` | ✅ 不创建 recovery Attempt |
| `RUN_FAILED` event | 未断言 | `== 1` | ✅ |

- 原测试名已准确（`does_not_enter_recovering`），保留 ✅
- 新增 `_attempt_count_for_run` 断言确保不创建 recovery Attempt ✅

### 1c. `test_persistent_memory_lag_repair_failure_closes_starting_run`

| 断言项 | 旧值 | 新值 | 是否正确 |
|---|---|---|---|
| `builder.calls` | `== 2` | `== 1` | ✅ 不进入旧 retry |
| `RUN_RECOVERING` event | 未断言 | `== 0` | ✅ 不进入 RECOVERING |
| 其余断言 | 已正确 | 保持 | ✅ `timed_out==1`, `factory.created==0`, run=FAILED, attempt=FAILED, dispatch=CANCELLED, `cancelled_event_id is not None` |

---

## 检查点 2: PR-F1 已关闭，无生产实现回退或设计放宽

**结论: PASS**

- 工作树变更仅 2 文件: `docs/host/issues-implementation-control.md` 与 `tests/host/test_dispatch_scheduler.py` ✅
- `git diff --name-only` 确认 dayu/host/ 下无任何生产代码变更 ✅
- 测试断言变更方向一致：3 个测试全部收紧为 fail-closed 语义，无放宽 ✅
- 生产代码中 `_raise_if_memory_projection_target_not_reached`、`_MemoryProjectionDispatchDiagnosticError`、`_safe_closeout_worker_startup_timeout` 等 fail-closed 机制未被触及 ✅

---

## 检查点 3: PR body 准确报告完整受影响测试文件集合

**结论: PASS**

`gh pr view 136 --json body` 返回内容验证：

- ✅ 完整受影响测试文件命令与结果明确列出: `185 passed`
- ✅ pyright 结果: `0 errors, 0 warnings, 0 informations`
- ✅ git diff 检查: `passed`
- ✅ 历史 -k 过滤结果已标注为 "Historical focused review context, not a substitute for the full affected-file run above"
- ✅ 历史结果的过滤条件明确: "143 passed by AgentDS"、"68 passed, 1 skipped, 123 deselected"、"25 passed, 103 deselected"
- ✅ 不会误导 reviewer 把选择性子集当成完整通过

---

## 检查点 4: 控制文档仅记录 fix completed / validation passed

**结论: PASS**

`docs/host/issues-implementation-control.md` 变更验证：

### 当前状态表 (line ~144-147)

```
| implementation status | WU-PROJ-01 PR review fix completed by AgentCodex; validation passed; awaiting controller next step |
| next entry point | WU-PROJ-01 post-fix controller adjudication |
```

- ✅ 记录 fix completed / validation passed
- ✅ next entry point 指向 controller adjudication，未擅自推进到 re-review pass 或 draft-PR-pass
- ✅ gate 仍为 `review`，未推进

### WU-PROJ-01 行 (line ~229)

```
| WU-PROJ-01 | implementation | ... | PR review accepted fix completed；旧 dispatch scheduler 测试断言已按 fail-closed 新设计更新，完整受影响测试文件集合 185 passed，pyright 0 errors；等待 controller 下一步裁决 |
```

- ✅ 记录 fix completed / 185 passed / pyright 0 errors
- ✅ 以"等待 controller 下一步裁决"结尾，未自行推进

---

## 检查点 5: Controller 复验结果

**结论: PASS**

| 验证项 | 命令 | 结果 | 状态 |
|---|---|---|---|
| 完整受影响 Host 测试文件 | `pytest tests/host/test_compact_material.py tests/host/test_dispatch_scheduler.py tests/host/test_memory_repair.py tests/host/test_memory_projection.py tests/host/test_run_input_builder.py tests/host/test_logging.py tests/host/test_open_host_runtime.py` | 185 passed in 2.07s | ✅ |
| 目标 3 个回归测试 | `pytest tests/host/test_dispatch_scheduler.py::test_dispatch_lag_repair_rebuild_not_reached_fails_closed tests/host/test_dispatch_scheduler.py::test_memory_lag_pre_dispatch_failure_does_not_enter_recovering tests/host/test_dispatch_scheduler.py::test_persistent_memory_lag_repair_failure_closes_starting_run` | 3 passed in 0.29s | ✅ |
| pyright | `pyright` | 0 errors, 0 warnings, 0 informations | ✅ |
| git diff --check | `git diff --check` | 无输出（通过） | ✅ |

---

## 验证命令记录

```bash
# 完整受影响 Host 测试文件
source .venv/bin/activate && python -m pytest \
  tests/host/test_compact_material.py \
  tests/host/test_dispatch_scheduler.py \
  tests/host/test_memory_repair.py \
  tests/host/test_memory_projection.py \
  tests/host/test_run_input_builder.py \
  tests/host/test_logging.py \
  tests/host/test_open_host_runtime.py \
  -q
# → 185 passed in 2.07s

# 目标回归测试
source .venv/bin/activate && python -m pytest \
  tests/host/test_dispatch_scheduler.py::test_dispatch_lag_repair_rebuild_not_reached_fails_closed \
  tests/host/test_dispatch_scheduler.py::test_memory_lag_pre_dispatch_failure_does_not_enter_recovering \
  tests/host/test_dispatch_scheduler.py::test_persistent_memory_lag_repair_failure_closes_starting_run \
  --tb=short -q
# → 3 passed in 0.29s

# pyright
source .venv/bin/activate && pyright
# → 0 errors, 0 warnings, 0 informations

# git diff --check
git diff --check
# → (无输出，通过)

# PR body
gh pr view 136 --json body
# → 完整受影响测试文件集合 185 passed，pyright 0 errors，
#   历史 -k 结果已标注为 Historical focused review context

# 工作树变更
git diff --name-only
# → docs/host/issues-implementation-control.md
# → tests/host/test_dispatch_scheduler.py
```

## 剩余风险

本 re-review 不改变以下已 deferred risk 的 owner：

- `WU-PROJ-01-S3-R1`: dispatch before-worker catch-up happy path 独立集成测试 — deferred to Host dispatch test hardening
- `WU-PROJ-01-S4-R1`: `test_reactive_compact_failure_fallback_dispatch_uses_failed_view` lane timeout flaky — deferred to Host dispatch scheduler test hardening

---

## 下一步建议

1. Controller 确认 re-review PASS 后，更新控制文档 gate 状态。
2. PR-F1 / PR-F2 均已关闭，可以进入下一 gate。
