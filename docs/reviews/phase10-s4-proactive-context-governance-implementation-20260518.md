# Phase 10 Slice 4 Proactive Context Governance Implementation

## 修改摘要

- 新增 `RunStatus.ACCEPTED` 与 durable schema v9 约束，accepted Run 不允许 queued/start/current Attempt refs，并作为 Session active/start-blocking 状态参与读取与唯一性约束。
- Admission `start_run` / `submit_followup(queue)` 在无 active/start-blocking Run 时创建 `ACCEPTED` Run，只写 `USER_INPUT_ACCEPTED` 与 `RUN_ACCEPTED`；accepted Run 上 `REJECT` 与 `ATTACH_ACTIVE` 都返回 conflict，cancel accepted 走 attempt-free `RUN_CANCELLED`。
- Durable transition 增加 accepted Run 创建、accepted/queued governance start、accepted/queued attempt-free failure 三类 helper。
- Dispatch scheduler 的 queue wakeup 改为 pre-start governance gate：选择 accepted Run 或无 active 时最早 queued Run，预算通过后才写 `RUN_STARTED`、`ATTEMPT_STARTED` 与 dispatch record。
- Proactive soft threshold 会写 `CONTEXT_COMPACTION_REQUESTED`、调用显式注入 compactor、通过 quality check 后写 compact artifact 与 `CONTEXT_COMPACTED`，再 catch up conversation memory projection 后启动 Attempt。
- Proactive compact failure、hard threshold、compact 后仍超过 hard threshold、committed compact-count facts 损坏均写 `CONTEXT_COMPACTION_FAILED` 与 attempt-free `RUN_FAILED`。
- RunInputBuilder 增加 `DurableCompactArtifactProvider`，按当前 Attempt cursor 读取 accepted `CONTEXT_COMPACTED`，向 Engine 只暴露 artifact ref/digest、compacted event refs、preserved tool fact refs 与 bounded episode summary。
- Controller 预审补强：`ACCEPTED` 已纳入 durable active unique index 与 queued/accepted start CAS 的 active 冲突集合，避免同 Session 同时存在 accepted 与 running/waiting/cancelling/recovering Run。

## 状态流

- Admission: `USER_INPUT_ACCEPTED` -> `RUN_ACCEPTED` -> durable Run `accepted`，无 Attempt / dispatch。
- No compact start: `accepted|queued` -> `RUN_STARTED` -> `ATTEMPT_STARTED` -> Run `running` + Attempt `starting` + dispatch `pending`。
- Compact accepted start: `CONTEXT_COMPACTION_REQUESTED` -> compact artifact descriptor -> `CONTEXT_COMPACTED` -> memory projection catch-up -> `RUN_STARTED` -> `ATTEMPT_STARTED`。
- Compact failed / hard block: `CONTEXT_COMPACTION_FAILED` -> `RUN_FAILED`，Run `failed`，无 Attempt / dispatch。
- Cancel accepted: `CANCEL_REQUESTED` -> `RUN_CANCELLED`，Run `cancelled`，无 Attempt / dispatch。

## 测试结果

- `source .venv/bin/activate && pytest tests/host/test_run_attempt_transitions.py tests/host/test_admission_queue.py tests/host/test_dispatch_scheduler.py tests/host/test_phase5_local_execution_integration.py tests/host/test_run_input_builder.py -q`：通过，124 passed。
- `source .venv/bin/activate && pyright`：通过，0 errors。
- `git diff --check`：通过。
- `source .venv/bin/activate && pytest tests/host/test_admission_queue.py -q`：通过，23 passed。
- `source .venv/bin/activate && pytest tests/host/test_dispatch_scheduler.py -q`：通过，29 passed。
- `source .venv/bin/activate && pytest tests/host/test_phase5_local_execution_integration.py -q`：通过，9 passed。
- `source .venv/bin/activate && pytest tests/host/test_run_input_builder.py -q`：通过，30 passed。

## README 决策

- 已更新 `dayu/host/README.md`：记录 accepted pre-start gate、proactive compact orchestration、attempt-free failure、durable compact artifact provider 与 admission 当前语义。
- 已更新 `tests/README.md`：同步 public run / local execution 集成测试职责中的 accepted pre-start 与 governance wakeup 表述。

## 未覆盖风险

- proactive compactor 调用与 compact artifact 写入当前发生在 Host SQLite write transaction 内。当前 Slice 4 单进程同步调度可接受，但真实 LLM compactor 可能形成长事务并阻塞其它 writer；后续应以 durable in-progress / fencing 语义把 LLM 调用和 artifact 文件写入移到 transaction 外，仅把 descriptor、canonical event 与状态 CAS 保留在 transaction 内。
- proactive compact provider 只暴露 compact event payload 中的 bounded summary 与 artifact refs，尚未读取 artifact JSON 正文；这符合当前 Slice 4 最小要求，但后续若需要 artifact 内容级 rebuild，需要补充 artifact read path。
- proactive budget estimate 当前只覆盖当前用户输入文本片段，未纳入完整 RunInputBuilder message / tool schema 估算；provider-specific tokenizer、长期 retrieval、reactive overflow 均留给后续 slice。
- `promote_next_queued_run` 仍保留为 admission 内部/测试可调用 helper；生产启动真源已迁移为 scheduler `wake_queue_promotion` governance gate，后续若不再需要该 helper 可单独收敛接口面。
