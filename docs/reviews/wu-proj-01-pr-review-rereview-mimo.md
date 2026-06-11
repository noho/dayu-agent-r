# WU-PROJ-01 PR Review Re-Review Gate — AgentMiMo

## 元数据

- Work unit: `WU-PROJ-01`
- Gate: PR review re-review gate
- 日期: 2026-06-11
- PR: `https://github.com/noho/dayu-agent-r/pull/136`
- Reviewer: AgentMiMo
- 前置 gate: PR review fix gate (AgentCodex)

## 输入

- PR review controller adjudication: `docs/reviews/wu-proj-01-pr-review-controller-adjudication.md`
- PR review fix artifact: `docs/reviews/wu-proj-01-pr-review-fix-codex.md`
- PR review DS: `docs/reviews/wu-proj-01-pr-review-ds.md`
- PR review MiMo (初审): `docs/reviews/wu-proj-01-pr-review-mimo.md`
- Fix diff: `tests/host/test_dispatch_scheduler.py` (dirty working tree)
- Control doc diff: `docs/host/issues-implementation-control.md` (dirty working tree)

## 审查结论

**PASS**

---

## 检查项逐项裁决

### 1. 3 个旧测试是否按 fail-closed 新设计正确迁移

**结论: PASS**

3 个测试均按 controller adjudication 要求的 fail-closed 语义更新：

| 测试 | 旧断言 | 新断言 | 裁决 |
|---|---|---|---|
| `test_dispatch_lag_repair_rebuild_retry_does_not_fail_run` → 重命名为 `test_dispatch_lag_repair_rebuild_not_reached_fails_closed` | `dispatched==1, builder.calls==2, factory.created==1, run.RUNNING, RUN_FAILED==0` | `dispatched==0, timed_out==1, builder.calls==1, factory.created==0, run.FAILED, attempt.FAILED, dispatch_record.CANCELLED, RUN_FAILED==1, RUN_RECOVERING==0, diagnostic log` | ✅ 正确迁移 |
| `test_memory_lag_pre_dispatch_failure_does_not_enter_recovering` | `RUN_RECOVERING==0, run.RUNNING` | `RUN_RECOVERING==0, attempt_count==1, run.FAILED, RUN_FAILED==1` | ✅ 正确迁移 |
| `test_persistent_memory_lag_repair_failure_closes_starting_run` | `timed_out==1, builder.calls==2, factory.created==0, run.FAILED, attempt.FAILED, dispatch_record.CANCELLED` | `timed_out==1, builder.calls==1, factory.created==0, run.FAILED, attempt.FAILED, dispatch_record.CANCELLED, RUN_RECOVERING==0` | ✅ 正确迁移 |

关键行为覆盖：
- rebuild / catch-up 未达 required cursor → `timed_out` ✅
- 不进入 `RECOVERING`，不创建 recovery Attempt ✅
- 不继续旧 retry dispatch（`builder.calls` 从 2 降为 1） ✅
- Run / Attempt fail-closed 为 `FAILED`，dispatch record 被取消 ✅
- 直接断言 `dispatch.memory_projection.repair_not_reached` diagnostic 日志 ✅

### 2. PR-F1 是否关闭，且没有回退生产实现或放宽设计

**结论: PASS**

- PR-F1 关闭条件：更新 3 个测试断言使其匹配 WU-PROJ-01 fail-closed 新设计 → 已完成。
- 未修改任何生产代码（`git diff tests/host/test_dispatch_scheduler.py` 只含测试文件变更）。
- 未放宽设计：新断言比旧断言更严格（fail-closed > fail-open）。
- 旧测试名 `test_dispatch_lag_repair_rebuild_retry_does_not_fail_run` 已不存在于文件中。

### 3. PR body 是否准确报告完整受影响测试文件集合

**结论: PASS**

PR body validation 段落：
```
- Full affected Host test files: ... -> 185 passed.
- pyright: ... -> 0 errors, 0 warnings, 0 informations.
- git diff check: ... -> passed.
```

历史选择性过滤结果已标注为：
```
Historical focused review context, not a substitute for the full affected-file run above:
- Aggregate focused tests: 143 passed by AgentDS.
- Aggregate MiMo validation: 68 passed, 1 skipped, 123 deselected.
- Slice 4 controller validation: 25 passed, 103 deselected.
```

准确、完整、无误导。

### 4. 控制文档是否只记录 fix completed / validation passed

**结论: PASS**

`docs/host/issues-implementation-control.md` diff 中：
- `implementation status`: `WU-PROJ-01 PR review fix completed by AgentCodex; validation passed; awaiting controller next step`
- `next entry point`: `WU-PROJ-01 post-fix controller adjudication`

未擅自推进到 pass，未擅自推进到 merge。符合 gate 流程纪律。

### 5. Controller 复验结果

**结论: PASS**

| 检查项 | 命令 | 结果 |
|---|---|---|
| 完整受影响 Host 测试文件集合 | `python -m pytest tests/host/test_compact_material.py tests/host/test_dispatch_scheduler.py tests/host/test_memory_repair.py tests/host/test_memory_projection.py tests/host/test_run_input_builder.py tests/host/test_logging.py tests/host/test_open_host_runtime.py` | **185 passed in 2.05s** ✅ |
| 目标回归测试 | `python -m pytest ...::test_dispatch_lag_repair_rebuild_not_reached_fails_closed ...::test_memory_lag_pre_dispatch_failure_does_not_enter_recovering ...::test_persistent_memory_lag_repair_failure_closes_starting_run` | **3 passed in 0.31s** ✅ |
| pyright | `pyright` | **0 errors, 0 warnings, 0 informations** ✅ |
| git diff whitespace | `git diff --check` | **pass, 无输出** ✅ |

---

## Findings

无 finding。

---

## 结论

**PASS**

WU-PROJ-01 PR review re-review gate 通过。AgentCodex 的 fix 正确关闭了 PR-F1（3 个旧测试按 fail-closed 新设计迁移）和 PR-F2（PR body 准确报告完整测试结果）。未回退生产实现、未放宽设计、未违反 gate 流程纪律。完整受影响 Host 测试文件集合 185 passed，pyright 0 errors，git diff --check pass。
