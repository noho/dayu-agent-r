# Code Review Re-review — WU-CM-01-F04

## Scope

- Mode: code review re-review（phaseflow gate）
- Branch: phaseflow/host-issues
- Original review artifact: docs/reviews/wu-cm-01-f04-code-review-ds.md
- Fix artifact: docs/reviews/wu-cm-01-f04-code-review-fix-codex.md
- Other review artifact: docs/reviews/wu-cm-01-f04-code-review-mimo.md
- Reviewed diff: working tree `tests/host/test_dispatch_scheduler.py`（相对 fix artifact 记录的已提交状态）
- Re-review scope: 验证 accepted finding 关闭状态；检查 fix 后 `prepared_requests` 是真源；确认无新 blocking issue
- Excluded scope: 不再重新扩大 review 范围到其他 compactor / test / 生产代码

## Finding 关闭验证

### Finding: `_RequestCapturingCompactor.requests` 与父类 `prepared_requests` 重复存储（原 severity 低）

- **原 finding 编号**: 1（两个 review artifact 中均有记录）
- **裁决**: accepted
- **fix 方式**: 删除 `_RequestCapturingCompactor` 的独立 `requests` 列表与覆盖方法，让 request 捕获只由 `_PreparedManifestProactiveCompactor.prepared_requests` 承担

**验证结果：已修复**

逐项证据：

1. `_RequestCapturingCompactor` 当前定义（行 625-626）为空类，仅继承 `_PreparedManifestProactiveCompactor`，无任何属性声明或方法覆盖。
2. `self.requests` 在整个 `tests/host/test_dispatch_scheduler.py` 中已不存在（grep 确认零匹配）。
3. `compactor.requests` 同样零匹配。
4. 两个 request capture test 均从 `compactor.prepared_requests` 读取：
   - `test_proactive_compaction_uses_selected_material_not_session_start_range`（行 3788-3789）：`assert len(compactor.prepared_requests) == 1`、`request = compactor.prepared_requests[0]`
   - `test_proactive_material_pack_not_larger_than_ordinary_material_for_same_view`（行 3832）：`request = compactor.prepared_requests[0]`
5. `prepared_requests` 仅在父类 `_PreparedManifestProactiveCompactor.prepare_compactor_proposal_run_input`（行 439）中 append——唯一写入点，真源唯一。

## New Blocking Findings

**0 个**。fix 为纯删除操作，无新增代码路径、无新增状态、无新增逻辑分支。不存在新引入的 blocking issue。

## Validation Reviewed

| 验证项 | 命令 | 结果 |
|---|---|---|
| 两个 request capture test 单独运行 | `pytest tests/host/test_dispatch_scheduler.py::test_proactive_compaction_uses_selected_material_not_session_start_range tests/host/test_dispatch_scheduler.py::test_proactive_material_pack_not_larger_than_ordinary_material_for_same_view` | 2 passed |
| proactive full suite | `pytest tests/host/test_dispatch_scheduler.py -k "proactive or soft_threshold or wake_queue_promotion_uses_tracked_async_promotion_task"` | 8 passed, 54 deselected |
| pyright | `pyright tests/host/test_dispatch_scheduler.py` | 0 errors, 0 warnings, 0 informations |

以上验证均在本 re-review gate 内重新运行并确认通过。

## Residual Risks

- 全量 test suite 未在本 gate 运行。变更仅涉及删除测试 seam 内部重复状态，影响面积极小，风险低。
- `_RequestCapturingCompactor` 命名保留但 capture 真源在父类 `prepared_requests`——语义清晰度略降，但不影响正确性，属 deferred cleanup 范畴。
- reactive test seam 后续对齐不在本 work unit 范围，不在此 re-review 中评估。

## Verdict

**pass** — accepted finding 已修复，`prepared_requests` 是 request capture 唯一真源，0 个 new blocking finding。所有 focused validation 通过。
