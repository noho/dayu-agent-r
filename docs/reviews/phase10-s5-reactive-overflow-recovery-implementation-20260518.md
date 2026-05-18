# Phase 10 Slice 5 Reactive Overflow Recovery Implementation

## 修改摘要

- `EngineEventIngestor` 接入 `EngineEventType.CONTEXT_COMPACTION_REQUESTED` reactive path：继续以 envelope `attempt_id` / `execution_id` / dispatch refs 做 durable identity guard，接受后写 `CONTEXT_COMPACTION_REQUESTED(trigger_source=reactive)`，再关闭当前 Attempt 为 `FAILED` 并写 `RUN_RECOVERING`。
- reactive compact 复用 Phase 10 Host policy、conservative estimator、typed compactor、quality check、compact artifact store 与 `CONTEXT_COMPACTED` / `CONTEXT_COMPACTION_FAILED` payload builders；Engine `budget_state=None` 不成为预算真源。
- compact accepted 后追平 Conversation Memory projection 到 `CONTEXT_COMPACTED` sequence，再写 `RUN_STARTED(start_reason=recovery)` / `ATTEMPT_STARTED`，创建新的 Attempt、execution 与 pending dispatch record，并唤醒 scheduler dispatch。
- compact failure、reactive count 上限、compact-count fact 损坏、compactor / artifact root 缺失、quality rejection、compact 后仍越过 hard threshold 均让 Run 从 `RECOVERING` 收口为 `FAILED`，不写 `RUN_LOST`。
- durable transition 增加 context recovery close、recovery start、recovering failure helper；state helper 增加 running -> recovering、recovering -> running、recovering -> failed 的 CAS 更新。
- scheduler worker event ingest wiring 注入 local execution 的 context policy、compactor、artifact root 与 memory projection policy。
- controller 复核修正：recovery accepted 的 ingest result 不再标记为 Run terminal closeout；新增 `stop_worker_stream` 只用于停止旧 Attempt worker stream。因此 scheduler 会关闭旧 handle / 释放 lane，但不会清理同 Run duplicate governance registry，也不会触发 queued promotion wakeup。

## 关键状态流

- accepted reactive overflow:
  `RUNNING / Attempt RUNNING -> CONTEXT_COMPACTION_REQUESTED(reactive) -> ATTEMPT_FAILED -> RUN_RECOVERING -> CONTEXT_COMPACTED -> memory catch-up -> RUN_STARTED(start_reason=recovery) -> ATTEMPT_STARTED -> RUNNING / new Attempt STARTING / dispatch PENDING`
- failed reactive overflow:
  `RUNNING / Attempt RUNNING -> ATTEMPT_FAILED -> RUN_RECOVERING -> CONTEXT_COMPACTION_FAILED -> RUN_FAILED`
- stale old Attempt:
  recovery start 后旧 Attempt 的后续 `run_failed(context_compaction_required)` 走 stale diagnostic / rejected path，不创建第二个 recovery Attempt，也不失败新 Attempt。
- worker stream handling:
  recovery accepted 返回 `terminal_closeout=False, stop_worker_stream=True`；真正 Run terminal 才返回 `terminal_closeout=True` 并触发 queue promotion / duplicate registry clear。

## 新增/修改测试

- `tests/host/test_engine_ingest_mapping.py`
  - `budget_state=None` 使用 Host estimator 并完成 reactive recovery。
  - recovery accepted 不触发 terminal promotion wakeup，并用 `stop_worker_stream` 表达停止旧 worker stream。
  - mismatched execution identity 被拒绝且不 compact。
  - compact failure 后 Run `FAILED`，不写 `RUN_LOST`。
  - old Attempt 后续 recoverable `run_failed` 为 stale diagnostic，不创建第二个 Attempt。
  - reactive count 上限与 corrupt count facts fail closed，且不创建 recovery Attempt。
  - `usage_reported` 既有 projection signal 测试保持不改变 Run / Attempt 状态。
- `tests/host/test_dispatch_scheduler.py`
  - worker 先发 reactive overflow，Host compact 后创建新 Attempt 并再次 dispatch，第二个 worker final answer 后 Run 成功。
  - reactive recovery accepted 后同 Run duplicate governance registry 保持 active，不因旧 Attempt worker stream 停止而被清理。

## 实际验证结果

- `source .venv/bin/activate && pytest tests/host/test_engine_ingest_mapping.py tests/host/test_run_attempt_transitions.py tests/host/test_dispatch_scheduler.py tests/host/test_phase5_local_execution_integration.py -q`：通过，104 passed。
- `source .venv/bin/activate && pyright`：通过，0 errors。
- `git diff --check`：通过。

## README 同步决策

- 已最小更新 `dayu/host/README.md`：补充 reactive overflow recovery 当前事实、failure policy、new Attempt dispatch 与旧 Attempt stale 处理。
- 已最小更新 `tests/README.md`：测试覆盖说明从 unsupported recovery mapping 更新为 reactive context compaction recovery。

## 未覆盖风险 / 后续 Owner

- 沿用 Slice 4 residual：compactor 与 artifact write 仍在 Host write transaction 内执行。后续若接入慢速生产 compactor，需要由 Context Governance / durable orchestration owner 增加 in-progress / fencing 设计后再移出 transaction。
- 当前 reactive estimator 只使用 durable current user input 片段生成 Host budget refs；provider-specific tokenizer、长期 retrieval 和更完整 prompt-level budget 归后续 tokenizer / retrieval owner。
- 不实现 Phase 11 startup recovery、positive orphan proof、RECOVERING cancel 或通用 recovery scan；本 slice 只覆盖 Engine overflow reactive recovery。
