# Code Review

## Scope

- Mode: current changes
- Branch: phaseflow/host-issues
- Base: main (uncommitted working tree diff)
- Output file: docs/reviews/wu-cm-01-f04-code-review-mimo.md
- Included scope:
  - `tests/host/test_dispatch_scheduler.py` implementation diff
  - `docs/reviews/wu-cm-01-f04-implementation-codex.md` validation/report consistency
- Excluded scope:
  - `docs/host/issues-implementation-control.md` gate bookkeeping（仅在与 scope 矛盾时检查）
- Parallel review coverage: 无

## Findings

### 1-未修复-低-_RequestCapturingCompactor.requests 与父类 prepared_requests 双重存储

- **入口/函数**: `_RequestCapturingCompactor.prepare_compactor_proposal_run_input`
- **文件(行号)**: `tests/host/test_dispatch_scheduler.py` diff 行 631-660（新增 `_RequestCapturingCompactor.prepare_compactor_proposal_run_input`）
- **输入场景**: 任何 proactive compaction test 使用 `_RequestCapturingCompactor` 时
- **实际分支**: `self.requests.append(request)` 后 `super().prepare_compactor_proposal_run_input(...)` 再次将同一 request 存入 `self.prepared_requests`
- **预期行为**: request 捕获语义应单一真源，不产生平行重复列表
- **实际行为**: `compactor.requests` 和 `compactor.prepared_requests` 各存一份相同 request；当前 tests 只读 `compactor.requests` 的内容字段，不受影响
- **直接证据**: diff 中 `_RequestCapturingCompactor.prepare_compactor_proposal_run_input` 调用 `self.requests.append(request)` 后调用 `super().prepare_compactor_proposal_run_input(...)`，父类 `_PreparedManifestProactiveCompactor.prepare_compactor_proposal_run_input` 也执行 `self.prepared_requests.append(request)`
- **影响**: 无 correctness 影响；未来若测试改为断言 `len(compactor.requests)` 会意外得到 2× 期望值
- **建议改法和验证点**: 去掉 `_RequestCapturingCompactor.requests` 列表，改为暴露 `prepared_requests` 的 property alias；或在 `prepare_compactor_proposal_run_input` 中去掉 `self.requests.append(request)` 并让下游改读 `prepared_requests`。验证：`test_proactive_compaction_uses_selected_material_not_session_start_range` 和 `test_proactive_material_pack_not_larger_than_ordinary_material_for_same_view` 仍通过
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Open Questions

无。

## Residual Risk

- implementation artifact 报告只运行了 focused validation（8 passed, 54 deselected）和 pyright，未运行 `tests/host/test_dispatch_scheduler.py` 全量或项目全量测试套件。focused 范围已覆盖所有 proactive compact 语义，reactive seam 由既有 prepared manifest tests 独立覆盖，风险低。
- `_StaleMutatingCompactor` 保持 legacy `FakeContextCompactor` 路径未迁移，符合 plan 设计（stale check 在 accepted guard 前写 `CONTEXT_COMPACTION_FAILED`，不触发 manifest guard）。若未来 production contract 变更要求 stale attempt 也记录 manifest，需单独 work unit。
- `RUNNER_CALL_INPUT_ASSEMBLED` 计数断言未加入，符合 plan 的 conditional assertion 策略；核心验收为 compacted/rejected payload manifest ref/digest。

## Validation Reviewed

- 实际运行 `pytest tests/host/test_dispatch_scheduler.py -k "proactive or soft_threshold or wake_queue_promotion_uses_tracked_async_promotion_task"`：**8 passed, 54 deselected**。与 implementation artifact 报告一致。
- 实际运行 `pyright tests/host/test_dispatch_scheduler.py`：**0 errors, 0 warnings, 0 informations**。与 implementation artifact 报告一致。
- Protocol 签名核对：`_PreparedManifestProactiveCompactor.prepare_compactor_proposal_run_input` 和 `run_prepared_compactor_proposal` 的参数名、参数类型、返回类型与 `CompactorProposalPreparedCompactor` Protocol（`compaction_operation.py:134-167`）完全匹配。`@runtime_checkable` 的 `isinstance` 检查可正确命中。
- Manifest 录制时序核对：`compaction_operation.py:756-776` 先调用 `_record_compactor_proposal_manifest` 再调用 `run_prepared_compactor_proposal`；`_RaisingCompactor(fail_run=True)` 的 failure 发生在 manifest 已记录之后，rejected payload 可正确携带 manifest ref/digest。
- `_StaleMutatingCompactor` 确认未迁移：仍继承 `FakeContextCompactor`，不实现 `CompactorProposalPreparedCompactor`，走 legacy `compact()` 路径。
- implementation artifact 的 proactive compactor 注入清单与实际 diff 一致：8 个迁移、3 个 excluded（stale、count limit、corrupted count）、reactive 不纳入。

## Verdict

**pass**
