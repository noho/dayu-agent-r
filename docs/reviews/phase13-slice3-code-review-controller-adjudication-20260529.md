# Phase 13 Slice 3 Code Review Controller Adjudication

## Gate

Phase 13 Slice 3 `OutboxSink Durable Projection` code review adjudication。

## Inputs

- Implementation artifact: `docs/reviews/phase13-slice3-implementation-codex-20260529.md`
- AgentMiMo review: `docs/reviews/phase13-slice3-code-review-mimo-20260529.md`
- AgentDS review: `docs/reviews/phase13-slice3-code-review-ds-20260529.md`
- Accepted plan: `docs/host/phase13-audit-tool-trace-outbox-plan.md`
- Schema clarification: `docs/reviews/phase13-schema-version-controller-clarification-20260529.md`

## Verdict

**PASS**。两路 code review 均为 PASS，无 blocking findings。Slice 3 可以进入 accepted local commit。

## Controller Decision

### MiMo Finding 1: `event_sequence` 外键约束冗余

裁决：non-blocking residual。

理由：`event_sequence` 外键在当前 EventLog append-only 和 unique sequence 语义下不会破坏 correctness。它确实带有冗余和未来 retention/vacuum 约束风险，但当前 Phase 13 Slice 3 的目标是建立 outbox projection/work queue，不定义 purge/retention。移除该外键属于 schema hardening，可在后续 retention/purge 设计中统一处理，避免本 slice 扩大 schema 语义讨论。

### MiMo Finding 2: 边界常量缺少显式拒绝测试

裁决：non-blocking hardening。

理由：`limit` 与 `seen_terminal_event_ids` 上限校验集中在 durable read helper，当前测试已覆盖正常 cursor、seen filtering、watermark、drain idempotency 与 conflict。缺少超限拒绝测试会增加未来重构风险，但不影响当前功能正确性。后续 public API slice 可在暴露入口时补充外部边界测试。

### DS Observation 1: `catch_up_outbox_terminal_projection` 循环实现冗余

裁决：observation only。

理由：该函数是 projection catch-up convenience helper，当前 while/run_once 语义正确，且不进入 public Host handle。若未来 `ProjectionRunner` 增加 run-to-completion helper，再统一收敛更合适。

### DS Observation 2: `scan_limit = limit + len(seen_ids)` 查询可能浪费

裁决：accepted residual。

理由：当前 `seen_terminal_event_ids` 有明确上限，最坏扫描规模受控。该实现优先保证 read after cursor、seen filtering、scanned watermark 与 `has_more` 语义清晰，不引入 SQLite-specific `NOT IN` 查询复杂度。若后续出现性能证据，再基于数据优化。

## Validation Required Before Commit

Controller 在创建 accepted commit 前需重新运行：

- `source .venv/bin/activate && pytest tests/host/test_outbox_projection.py tests/host/test_outbox_durable.py tests/host/test_durable_schema.py -q`
- `source .venv/bin/activate && python -m pyright dayu/host tests/host`
- `git diff --check`

## Outcome

无需 fix pass。通过验证后创建 accepted Slice 3 local commit，并进入 Phase 13 Slice 4 `Public Outbox Read / Drain API And Offline Smoke` implementation。
