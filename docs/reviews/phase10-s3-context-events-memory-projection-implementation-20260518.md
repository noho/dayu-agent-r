# Phase 10 Slice 3 Context Events / Memory Projection Implementation

## 修改摘要

- 新增 `dayu.host.context_events`，集中提供 `CONTEXT_COMPACTION_REQUESTED`、`CONTEXT_COMPACTED`、`CONTEXT_COMPACTION_FAILED` 的 typed payload builder / validator；EventLog primitive 未加入 compact 业务语义。
- 将 Conversation Memory compact truth 从旧 `EPISODE_SUMMARY_ACCEPTED` 切换为 accepted `CONTEXT_COMPACTED`。
- `ConversationMemoryProjectionConsumer` 生产 filter 纳入 `CONTEXT_COMPACTED`，不纳入 `CONTEXT_COMPACTION_FAILED`。
- `project_conversation_memory_event` 解析 `CONTEXT_COMPACTED` 的 `episode_summary_candidate` 与 `pinned_state_patch_candidate`：episode summary 只生成 assumption continuity item；pinned state patch 按 missing / clear / replace 三态更新；verified facts 仍只来自 `TOOL_RESULT_ACCEPTED`。
- `confirmed_subjects` patch 只接受 Host-neutral opaque ref 结构或 `kind:ref_id` 形式，不接受自由业务字符串；summary 的 confirmed fact refs 只能引用已有 tool fact refs。
- RunInputBuilder 相关测试改为通过 projection catch-up 验证 memory messages 中包含 accepted compacted pinned state 与 episode summary。
- Controller 侧预审补强：
  - `CONTEXT_COMPACTED` validator 强制 `quality_check_result.accepted == true`、无 rejection reasons，且 accepted quality flags 必须为真。
  - pinned state patch validator 不再接受直写字符串 / 数组绕过字段级三态结构与 evidence 约束。
  - memory projection 支持 Host-neutral opaque ref object 的 optional `digest` 缺省，仍拒绝自由业务字符串。
  - code review 后补强 `proposed_verified_fact_refs` fail-closed 校验，并在 validator 层前置检查 replace patch value。

## 测试结果

- `source .venv/bin/activate && pytest tests/host/test_context_compact_events.py tests/host/test_memory_projection.py tests/host/test_run_input_builder.py -q`
  - 结果：`79 passed`
- `source .venv/bin/activate && pyright`
  - 结果：`0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - 结果：通过，无 whitespace error。

## README 决策

- 已更新 `dayu/host/README.md`：记录 `dayu.host.context_events` 的当前职责、`CONTEXT_COMPACTED` 作为 accepted compact memory input，以及 memory projection 不消费 `CONTEXT_COMPACTION_FAILED`。
- 已更新 `tests/README.md`：测试覆盖说明加入 context compact canonical payload validator 与 accepted `CONTEXT_COMPACTED` materialization。

## 风险 / 未覆盖项

- 本 slice 未实现 Slice 4+ proactive / reactive orchestration，未追加生产 compact events，也未实现 compact artifact provider rebuild。
- `CONTEXT_COMPACTED` 的 production append 调用点仍由后续 slice 接入；当前只提供 payload builder / validator 与 memory projection consumption。
- confirmed subject 文本 ref 第一版只支持 Host-neutral `kind:ref_id` 轻量格式；更复杂 ref schema 若由后续 compactor adapter 输出，应继续走 JSON object opaque ref 结构。
