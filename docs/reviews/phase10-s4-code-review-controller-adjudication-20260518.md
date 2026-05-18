# Phase 10 Slice 4 Code Review Controller Adjudication

Date: 2026-05-18
Controller: Codex
Scope: Phase 10 Slice 4 proactive context governance

## Inputs

- `docs/reviews/phase10-s4-code-review-mimo-20260518.md`
- `docs/reviews/phase10-s4-code-review-ds-20260518.md`
- `docs/reviews/phase10-s4-proactive-context-governance-implementation-20260518.md`

## Verdict

ACCEPTED_WITH_RESIDUAL。

MiMo 给出 PASS，无 blocking / high / medium finding。DS 给出 ACCEPTED_WITH_RESIDUAL，确认 9 个 adversarial 向量被阻断，并记录 3 个 residual：compactor / artifact write 位于 SQLite write transaction 内、budget estimate 只覆盖当前 prompt、`promote_next_queued_run` 旧 API 表面仍存在。

## Adjudication

R1 事务内 compactor 是真实结构风险，但不在 Slice 4 里临时改造。把 LLM compactor 移出 transaction 需要新增 durable in-progress / fencing 或等价状态，否则 `CONTEXT_COMPACTION_REQUESTED` 提前提交后会和重复 wakeup、cancel、compact limit 产生新竞态。当前实现保持 compact count 查询与 request append 在同一 transaction 内，满足本 slice 的“attempt-free proactive failure”主目标；风险已补入 implementation artifact，后续 reactive / production compactor slice 必须显式处理。

R2 budget estimate 覆盖不足接受为已知 residual。第一版 conservative estimator 和 Host policy threshold 已落地，provider-specific tokenizer 与完整 RunInputBuilder message sizing 属于后续能力；当前风险是漏报 soft threshold 或过晚 compact，不破坏 EventLog / Attempt 状态机正确性。

R3 legacy helper 表面接受为 residual。生产路径已迁移到 scheduler `wake_queue_promotion` governance gate；测试已覆盖 accepted active 阻止 direct queued promotion。后续若不再需要 public helper，应收敛接口面或让 helper 进入 governance gate。

## Required Follow-up

- 后续 slice 若引入真实异步 LLM compactor，必须先设计 durable in-progress / fencing，再把 compactor 调用和 artifact 文件写入移出 DB write transaction。
- 后续 tokenizer / sizing owner 必须让 budget estimate 输入覆盖 RunInputBuilder messages、tool schemas、memory snapshot 和 compact artifact refs。
- Phase 10 结束前应复查 `promote_next_queued_run` 是否仍需要暴露。

## Validation Baseline

- `pytest tests/host/test_run_attempt_transitions.py tests/host/test_admission_queue.py tests/host/test_dispatch_scheduler.py tests/host/test_phase5_local_execution_integration.py tests/host/test_run_input_builder.py -q`：124 passed。
- `pyright`：0 errors。
- `git diff --check`：passed。
