# WU-CM-01 Slice C Implementation Retry Blocker - Controller Adjudication

## 裁决

- Gate: WU-CM-01 Slice C implementation retry
- Verdict: blocker accepted
- Next gate: WU-CM-01 Slice C policy contract plan fix
- Accepted implementation commit: none

本轮 Slice C implementation retry 不成立为可验收实现。AgentCodex 留下的 `dayu/host/memory.py` 是未完成的 vNext 草稿，未形成 pyright-clean vertical closure，且字段形状按本轮 gate prompt 选择了与设计真源不一致的 policy contract。该草稿已作为 stash 保存，不进入裁决提交。

## 一性原理判断

Slice C 的真实目标不是“尽快替换 `memory.py` 字段名”，而是关闭 Conversation Memory vNext 在 memory projection、durable row、compact material、run input、dispatch、runtime config、service assembly 与测试文档之间的同源契约。若 policy 字段名和预算形状不先统一，任何实现都只能在以下两种坏路径之间选择：

- 按 gate prompt 实现 `selected_recent_window_floor_turns` 与 generic item/text caps，偏离 `docs/host/design.md`。
- 按设计真源实现 `selected_recent_window_turn_floor` 与 per-section caps，但与本轮 implementation prompt 冲突。

在本项目约束下，不能用 alias、兼容 wrapper、默认补齐或 extra payload 同时接受两套字段。因此 blocker 成立，严重性没有被高估。

## 直接证据

- `docs/host/design.md` 的 `memory_projection_policy` 明确要求 `selected_recent_window_turn_floor`，以及 `selected_recent_window_item_cap`、`selected_recent_window_char_cap`、`fallback_selected_recent_window_item_cap`、`fallback_selected_recent_window_char_cap`、`evidence_fact_item_cap`、`evidence_fact_char_cap`、`evidence_fact_floor`、`session_summary_char_cap`、`answer_anchor_item_cap`、`answer_anchor_char_cap`、`forward_intent_item_cap`、`forward_intent_char_cap`、`reference_continuity_item_cap`、`reference_continuity_char_cap`、`reference_continuity_item_floor` 等 per-section 字段。
- `docs/host/wu-cm-01-conversation-memory-plan.md` 的 Slice C 实现边界重复上述字段清单，并明确 JSON 字段清单必须直接对齐 design source。
- AgentCodex blocker artifact 记录本轮 gate prompt 要求 `selected_recent_window_floor_turns`、`projection_max_repair_attempts`、`projection_max_rebuild_rows`、`projection_max_catchup_rows`、`max_memory_items_per_category`、`max_text_chars_per_memory_item`，与设计真源字段集合不一致。
- AgentCodex blocker artifact 同时列出仍引用旧 snapshot / policy 字段的 direct consumers，说明仅替换 `dayu/host/memory.py` 不能构成闭环。

## 接受与拒绝

Accepted:

- 接受 blocker：Slice C implementation retry 必须停止。
- 接受 root cause：implementation prompt 与设计真源/已接受 plan 的 policy contract 不一致。
- 接受后续动作：先进入 policy contract plan fix gate，明确 implementation prompt、allowed files、字段清单与验证矩阵，再重新进入 Slice C implementation。

Rejected:

- 不接受 `dayu/host/memory.py` partial draft 为 implementation artifact。
- 不接受通过 alias、旧字段兼容读取、默认补齐、wrapper/facade 或 extra payload 同时容纳两套 policy 字段。
- 不接受只更新 tests 或 README 来掩盖未闭合的 production consumer graph。

## 后续入口

下一 gate 应由 AgentCodex 产出 plan fix artifact，仅修改 plan / 总控相关说明，不做生产代码实现。plan fix 必须以 `docs/host/design.md` 为真源，除非先获得明确设计真源变更；并把 Slice C implementation prompt 改为直接对齐 `selected_recent_window_turn_floor` 与 per-section cap/floor 字段集合。

后续 implementation 重新开始前，至少需要明确：

- `MemoryProjectionPolicy` production dataclass 字段清单与 `execution_profiles.json.memory_projection_policy` JSON 字段清单。
- 所有旧 policy 字段和旧 snapshot key 的 fail-fast/fail-closed 边界。
- direct consumers 的迁移闭环：durable memory、compact material、run input、dispatch、engine ingest、runtime config loader、service assembly、tests、README。
- 验证命令：受影响 pytest 批次、`python -m pyright dayu/ tests/ utils/`，以及 README 触发范围。

## 工作区处理

- 未完成的 `dayu/host/memory.py` 草稿保存为 stash：`partial WU-CM-01 Slice C memory retry draft`。
- 既有旧 stash `partial WU-CM-01 Slice C typed contract attempt` 保留，不应用、不删除。
