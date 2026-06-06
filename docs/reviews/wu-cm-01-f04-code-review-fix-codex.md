# WU-CM-01-F04 Code Review Fix Artifact

## Gate

- Work unit: WU-CM-01-F04 Proactive Compaction Manifest-producing Test Seam Closeout
- Gate: fix for code review
- Status: ready for re-review
- Implementer: AgentCodex

## Accepted Finding

### 1-已修复-低-`_RequestCapturingCompactor.requests` 与 `prepared_requests` 重复存储

- 来源：`docs/reviews/wu-cm-01-f04-code-review-mimo.md` 与 `docs/reviews/wu-cm-01-f04-code-review-ds.md`
- 裁决：accepted
- 直接根因：`_RequestCapturingCompactor.prepare_compactor_proposal_run_input(...)` 先写入 `self.requests`，随后调用父类方法，父类又把同一个 `CompactionRequest` 写入 `self.prepared_requests`，形成两个平行 list。
- 修复方式：删除 `_RequestCapturingCompactor` 的独立 `requests` 列表与覆盖方法，让 request 捕获只由 `_PreparedManifestProactiveCompactor.prepared_requests` 承担；两个 request capture 测试改读 `compactor.prepared_requests`。
- 状态：已修复。

## Changed Files

- `tests/host/test_dispatch_scheduler.py`
- `docs/reviews/wu-cm-01-f04-code-review-fix-codex.md`

## Validation

通过：

```bash
source .venv/bin/activate && pytest tests/host/test_dispatch_scheduler.py::test_proactive_compaction_uses_selected_material_not_session_start_range tests/host/test_dispatch_scheduler.py::test_proactive_material_pack_not_larger_than_ordinary_material_for_same_view
```

结果：2 passed。

通过：

```bash
source .venv/bin/activate && pytest tests/host/test_dispatch_scheduler.py -k "proactive or soft_threshold or wake_queue_promotion_uses_tracked_async_promotion_task"
```

结果：8 passed, 54 deselected。

通过：

```bash
source .venv/bin/activate && pyright
```

结果：0 errors, 0 warnings, 0 informations。

## README Decision

本 gate 受总控限制只允许修改测试文件与 fix artifact，且修复仅消除测试 seam 内部重复状态，不改变测试分层、运行方式、维护规则或用户可见接口；未更新 README。

## Residual Risks

- 未运行整个项目测试套件；本 gate 按总控指定范围完成 focused validation 与 pyright。
- `_RequestCapturingCompactor` 现在只是语义化测试类名，捕获真源在父类 `prepared_requests`；该命名保留是为了减少测试阅读迁移成本，不影响状态真源。

## Blocking Open Questions

无。
