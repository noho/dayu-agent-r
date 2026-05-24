# P12.6 Slice 6 Implementation Artifact

## Gate

- Work unit: Phase 12.6 Conversation Memory Redesign
- Slice: Slice 6 Memory Projection Consolidation 与 RunInputBuilder Rendering
- Role: AgentCodex implementation specialist
- Base checkpoint: `851a2e7 gateflow: accept P12.6 slice 5`
- Non-goals: no commit, no push, no `docs/host/implementation-control.md` modification

## 动机判断

动机成立。`docs/host/design.md` §24 / §25 明确要求 Conversation Memory V1 consolidation 由 memory projection policy 与 RunInputBuilder / compactor bounded selection 负责，且 `CONTEXT_COMPACTED` 只能通过 committed EventLog 被 memory projection 消费。Slice 5 后的现状已具备 compact candidate 与 projection 接线，但 Slice 6 仍需补齐 evidence-backed facts 去重、bounded working set、episode summaries bounded rendering、minimum preserve 过期和 RunInputBuilder 渲染稳定性测试。

## 改动

- `dayu/host/memory.py`
  - accepted `CONTEXT_COMPACTED.evidence_backed_fact_candidates` 按 normalized `claim_text`、排序后的 canonical `evidence_refs`、`evidence_kind` 去重。
  - duplicate fact 保留较新的 extraction event sequence，并记录 `evidence_backed_fact_superseded` diagnostic。
  - evidence-backed fact snapshot selection 使用 Host-neutral bounded working set 排序：confirmed subject token overlap、current goal token overlap、recent user reference token overlap、newer extraction event sequence、stable item id。
  - episode summaries 只保留 policy-derived recent working set，旧 summary 被 budget diagnostic 解释，不继续 append-only 渲染全文。
  - episode summary materializes source refs，minimum preserve item 若被后续 stable fact 或 episode summary 覆盖，会从 visible continuity working set 移除并记录 diagnostic。
- `tests/host/test_memory_projection.py`
  - 增加并覆盖指定 Slice 6 projection tests：pinned current state、fact dedupe / bounded deterministic selection、episode summary bounded rendering、minimum preserve coverage expiry、final answer / user input / summary 不成为 stable fact。
- `tests/host/test_run_input_builder.py`
  - 增加 RunInputBuilder stable fact 渲染必须包含 `claim_text` / `evidence_refs` 的测试。
  - 增加 no-compaction recent raw turns continuity 测试。
- `dayu/host/README.md`
  - 同步 stable memory consolidation 的稳定语义：fact dedupe、bounded fact working set、minimum preserve coverage expiry、bounded recent episode summaries。
- `tests/README.md`
  - 同步 P12.6 memory semantic smoke 覆盖范围。

## 验证

- `source .venv/bin/activate && pytest tests/host/test_memory_projection.py tests/host/test_run_input_builder.py -q`
  - Result: `91 passed in 1.77s`
- `source .venv/bin/activate && python -m pyright dayu/host/memory.py dayu/host/run_input.py dayu/host/memory_repair.py tests/host/test_memory_projection.py tests/host/test_run_input_builder.py`
  - Result: `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - Result: pass

## README 决策

触发 `dayu/host/` 与 `tests/` README 规则。实际更新仅限职责范围内的稳定开发手册 / 测试手册说明；未写过程状态、未来计划或总控流水。

## 风险与未覆盖项

- 当前 fact working set relevance 排序保持 Host-neutral token overlap，不引入财务业务特定排序；若后续需要买方财务语义排序，应作为独立 Host policy / retrieval owner 设计，符合本 slice 停止条件。
- Durable historical all facts 仍受当前 snapshot table 物理模型约束；本 slice 保证 ordinary RunInputBuilder / compactor input 只消费 bounded snapshot working set，不新增 EventLog 写入或 Context Governance 直接写 snapshot。
- `docs/host/implementation-control.md` 在开始前已有未提交修改，本次只读未改。
