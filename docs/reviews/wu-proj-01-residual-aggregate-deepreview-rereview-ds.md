# WU-PROJ-01 Residual Aggregate Deepreview Re-Review DS

## 元数据

- Work unit: `WU-PROJ-01`
- Gate: aggregate deepreview re-review
- Date: 2026-06-11
- Reviewer: AgentDS
- Artifact: `docs/reviews/wu-proj-01-residual-aggregate-deepreview-rereview-ds.md`

## Scope

- Mode: current uncommitted changes (aggregate deepreview fix re-review)
- Branch: `wu-proj-01`
- Base: committed state (after CAP-R1 `448b70ba`, S3/S4 `3baeef53`, residual risk user decision)
- Changed files:
  - `dayu/host/memory_repair.py` (2 lines deleted)
  - `tests/host/test_memory_repair.py` (10 lines: 5 purpose value replacements)
  - `docs/host/issues-implementation-control.md` (1 line: WU-PROJ-01 row status update)
- Unchanged files verified: `dayu/host/dispatch.py`, `dayu/host/compact_material.py`
- Source of truth: `docs/host/design.md`; `docs/host/issues-implementation-control.md`
- Required artifacts reviewed:
  - `docs/reviews/wu-proj-01-residual-aggregate-deepreview-controller-adjudication.md`
  - `docs/reviews/wu-proj-01-residual-aggregate-deepreview-fix-codex.md`

## 方法

沿当前未提交 diff 中每条变更走读直接证据链。对每项 controller accepted finding 做闭合验证。对每项 controller rejected finding 做非侵入检查（确认 fix 未违反裁决）。

## 逐项审查

### AGG-F1: 删除不再使用的 REQUIRED_BEFORE_DISPATCH / REBUILD_BEFORE_DISPATCH enum 值

**闭合验证**：

- 直接证据 1 — 枚举定义：`dayu/host/memory_repair.py:33-36`，`MemoryProjectionRepairPurpose` 现仅保留 `BEST_EFFORT_AFTER_COMMIT = "best_effort_after_commit"`。旧值 `REQUIRED_BEFORE_DISPATCH` 和 `REBUILD_BEFORE_DISPATCH` 已删除。
- 直接证据 2 — 无兼容 alias/wrapper：`rg "alias\|wrapper\|compat\|re_export\|re-export" dayu/host/memory_repair.py` 无命中。
- 直接证据 3 — 全仓无残留引用：`rg "REQUIRED_BEFORE_DISPATCH\|REBUILD_BEFORE_DISPATCH" dayu/ tests/ docs/host/issues-implementation-control.md` 无命中。旧名称仅出现在 controller adjudication artifact 中作为历史裁决描述，未改写为当前事实。
- 直接证据 4 — `budget=None` correctness 路径未被此变更影响：`memory_repair.py:136` 的 `catch_up_conversation_memory_projection(budget=None)` 与 `memory_repair.py:238` 的 `rebuild_conversation_memory_projection(budget=None)` 不依赖 `MemoryProjectionRepairPurpose` 枚举。两条 `budget=None` 路径的测试 `test_required_catch_up_without_budget_crosses_old_batch_cap_to_target`（line 390）和 `test_rebuild_without_budget_crosses_old_batch_cap_to_target`（line 482）均未修改，断言保持不变。
- 直接证据 5 — `_budget_purpose_value` 仍正确处理 `budget=None` 返回 `None`，`budget is not None` 返回 `budget.purpose.value`（`memory_repair.py:529-538`）。

**结论**：AGG-F1 已闭合，无残留。

### AGG-F2: 修正控制文档 focused count 为 174

**闭合验证**：

- 直接证据 — `issues-implementation-control.md:227`，WU-PROJ-01 行已更新为 "corrected CAP/S3/S4 focused set to 174 passed"。全文 `rg "173"` 无命中。
- fix/re-review gate 正确记录在行末："Next gate: aggregate deepreview re-review." 与当前 gate 一致。

**结论**：AGG-F2 已闭合，无残留。

### 非侵入检查: 未修改 dispatch/projection correctness / opportunistic batch / source builder caps

**验证**：

- `dayu/host/dispatch.py` 不在 diff 中。`rg "opportunistic" dayu/host/dispatch.py` 确认 `_OPPORTUNISTIC_MEMORY_PROJECTION_CATCHUP_BATCHES = 1`（line 245）未变。
- `dayu/host/compact_material.py` 不在 diff 中。
- `rg "catch_up_conversation_memory_projection\|rebuild_conversation_memory_projection" dayu/host/dispatch.py` 无命中——dispatch 路径中 memory repair 调用不在本 diff 影响范围内。
- production dispatch / projection correctness 路径中 `budget=None` 的 required-before-dispatch 和 rebuild-before-dispatch 语义由既有代码表达，未被本 diff 的 enum 删除误改。

**结论**：无侵入。

### 测试意图检查

**逐一检查 5 处测试 purpose 值替换**：

1. `test_rebuild_resets_projection_and_finishes_empty_batch`（line 228）：purpose 从 `REBUILD_BEFORE_DISPATCH` → `BEST_EFFORT_AFTER_COMMIT`。测试断言 `result.reset_checkpoint is True`、`result.stop_reason is TARGET_REACHED`、`result.target_reached is True`。这些断言仅依赖 `max_batches=1`、`max_scanned_events=10` 和 fake runner 输出的 `finished_cursor=0`；purpose 只作为日志元数据传入，不参与分支选择。意图不变。

2. `test_catch_up_budget_exhausted_stops_before_idle`（line 329）：purpose 从 `REQUIRED_BEFORE_DISPATCH` → `BEST_EFFORT_AFTER_COMMIT`。断言 `result.budget_exhausted is True`、`result.stop_reason is BUDGET_EXHAUSTED`、`result.finished_cursor == 2`。预算耗尽逻辑仅由 `max_batches=1`、`max_scanned_events=2` 驱动；purpose 不参与停止判断。意图不变。

3. `test_catch_up_stops_when_target_reached_before_idle`（line 378）：purpose 从 `REQUIRED_BEFORE_DISPATCH` → `BEST_EFFORT_AFTER_COMMIT`。断言 `result.target_reached is True`、`result.stop_reason is TARGET_REACHED`。target reached 逻辑由 `max_event_sequence=2` 和 fake runner 输出 `finished_cursor=2` 驱动。意图不变。

4. `test_rebuild_budget_exhausted_reports_target_not_reached`（line 466）：purpose 从 `REBUILD_BEFORE_DISPATCH` → `BEST_EFFORT_AFTER_COMMIT`。断言 `result.budget_exhausted is True`、`result.target_reached is False`、`result.stop_reason is BUDGET_EXHAUSTED`。预算耗尽由 `max_batches=1`、`max_scanned_events=2` 和 `max_event_sequence=4` 驱动。意图不变。

5. `test_catch_up_budget_exhausted_advances_only_processed_checkpoint`（line 726-728）：purpose 从 `REQUIRED_BEFORE_DISPATCH` → `BEST_EFFORT_AFTER_COMMIT`。断言 checkpoint 仅推进到已处理的事件、snapshot 只包含已投影的文本。意图不变。

**直接证据**：`MemoryProjectionRepairPurpose` 值在 `memory_repair.py` 中仅在以下位置消费：
- `MemoryProjectionCatchupBudget.__post_init__`（line 74）：仅校验 `isinstance(self.purpose, MemoryProjectionRepairPurpose)`，不按具体值分支。
- `_budget_purpose_value`（line 538）：仅返回 `budget.purpose.value` 字符串用于日志。
- `catch_up_conversation_memory_projection`（line 203, 208-210）和 `rebuild_conversation_memory_projection`（line 264, 270）：仅通过 `_budget_purpose_value` / `_budget_max_batches` / `_budget_max_scanned_events` 辅助函数提取日志字段。

**结论**：purpose 从未驱动生产行为分支，测试意图未被削弱。

### README 判断复核

- `dayu/host/README.md` 的 `Agent更新约束【必须遵守】` 规定只写"当前代码已实现的 `dayu.host` package 的开发接口、公共契约、架构、稳定边界"。本轮删除的是已无 production consumer 的内部 enum 值，不改变 public interface、架构边界、状态机或关键执行路径。不更新 README 的判断正确。
- `tests/README.md`：本轮仅更新既有测试中 enum 引用，不新增测试层级、目录职责或常用命令。不更新 README 的判断正确。

### 类型检查

- `pyright`：0 errors, 0 warnings, 0 informations。无新增或扩散类型错误。

### 残留风险复核

- 既有 aggregate deepreview 中被 controller rejected 的 AGG-F3（opportunistic one-batch）和 AGG-F4（source builder cap）未在本 diff 中修改，保持原裁决。
- 既有 deferred residual risks `WU-PROJ-01-S3-R1` 和 `WU-PROJ-01-S4-R1` 不受本 diff 影响。

## Findings

未发现实质性问题。

## Open Questions

无。

## Residual Risk

- `MemoryProjectionRepairPurpose` 现仅含单一枚举值 `BEST_EFFORT_AFTER_COMMIT`。按当前用户裁决（after-commit best-effort 是唯一 bounded 路径，required/rebuild 走 `budget=None`），这是设计一致的结果。若未来需要区分不同 bounded 路径的 purpose 用于日志/诊断，可在当时新增枚举值——当前不构成缺陷。
- 本轮只验证了 controller 指定的 3 个 focused test files（91 passed）+ pyright + git diff --check。未重跑 PR 级完整 affected Host test set（185 tests）。controller adjudication 已接受该验证范围，不构成本 review 的新风险。

## 结论

**PASS**

两项 accepted findings（AGG-F1, AGG-F2）均已闭合，无残留。diff 未侵入 dispatch/projection correctness、opportunistic batch count 或 source builder caps。测试意图完整保留。类型检查通过。无 blocking findings，无非阻塞 findings。
