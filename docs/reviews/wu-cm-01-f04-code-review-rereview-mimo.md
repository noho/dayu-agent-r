# Code Review Re-Review

## Scope

- Mode: current changes (phaseflow gate re-review)
- Branch: phaseflow/host-issues
- Base: main
- Output file: docs/reviews/wu-cm-01-f04-code-review-rereview-mimo.md
- Included scope:
  - `tests/host/test_dispatch_scheduler.py` — fix diff 验证
  - `docs/reviews/wu-cm-01-f04-code-review-mimo.md` — original review
  - `docs/reviews/wu-cm-01-f04-code-review-ds.md` — other review
  - `docs/reviews/wu-cm-01-f04-code-review-fix-codex.md` — fix artifact
- Excluded scope: 不重新扩大 scope
- Parallel review coverage: 无

## Accepted Finding 验证

### 1-已修复-低-`_RequestCapturingCompactor.requests` 与父类 `prepared_requests` 双重存储

- **原始 finding 来源**: `docs/reviews/wu-cm-01-f04-code-review-mimo.md` Finding 1 与 `docs/reviews/wu-cm-01-f04-code-review-ds.md` Finding 1
- **裁决**: accepted
- **最终状态**: **已修复**

**修复验证**:

1. `_RequestCapturingCompactor` 类定义（当前行 625-626）：仅继承 `_PreparedManifestProactiveCompactor`，无 `__init__` 覆盖、无 `compact` 方法覆盖、无 `self.requests` 属性。类体为空，仅为语义化命名别名。
2. `self.requests` 已从整个文件中删除：`grep self\.requests` 返回 0 匹配。
3. `compactor.requests` 已从整个文件中删除：`grep compactor\.requests` 返回 0 匹配。
4. 两个 request capture 测试改读 `compactor.prepared_requests`：
   - `test_proactive_compaction_uses_selected_material_not_session_start_range`（行 3788-3789）：`assert len(compactor.prepared_requests) == 1`，`request = compactor.prepared_requests[0]`
   - `test_proactive_material_pack_not_larger_than_ordinary_material_for_same_view`（行 3832）：`request = compactor.prepared_requests[0]`
5. request capture 真源现在统一为 `_PreparedManifestProactiveCompactor.prepared_requests`（行 419），由 `prepare_compactor_proposal_run_input`（行 439）写入。

## 新引入 Blocking Issue 检查

**新引入 blocking findings: 0**

逐项检查：

- `_RequestCapturingCompactor` 降级为空子类后，`_PreparedManifestProactiveCompactor` 的所有方法（`prepare_compactor_proposal_run_input`、`run_prepared_compactor_proposal`、`_latest_prepared_request`）均可用，protocol 签名对齐不受影响。
- `_PreparedManifestProactiveCompactor.prepared_requests` 是 `list[CompactionRequest]`，与原 `_RequestCapturingCompactor.requests` 类型一致，测试断言语义不变。
- 未引入新的 import、新的类、新的生产代码依赖。

## Validation

实际运行验证：

```
pytest tests/host/test_dispatch_scheduler.py::test_proactive_compaction_uses_selected_material_not_session_start_range tests/host/test_dispatch_scheduler.py::test_proactive_material_pack_not_larger_than_ordinary_material_for_same_view
```

结果：**2 passed**。

```
pytest tests/host/test_dispatch_scheduler.py -k "proactive or soft_threshold or wake_queue_promotion_uses_tracked_async_promotion_task"
```

结果：**8 passed, 54 deselected**。

fix artifact 报告 pyright 0 errors；本轮未重新运行 pyright，因变更仅删除代码行不引入新类型。

## Findings

未发现实质性问题。

## Open Questions

无。

## Residual Risk

- 未运行项目全量测试套件；本 gate 按总控指定范围完成 focused validation。
- `_RequestCapturingCompactor` 现在是纯语义别名，无独立状态或行为；若未来不再需要该命名，可直接替换为 `_PreparedManifestProactiveCompactor`，但当前保留不影响 correctness。

## Verdict

**pass** — accepted finding 已关闭，无新引入 blocking issue，所有 focused validation 通过。
