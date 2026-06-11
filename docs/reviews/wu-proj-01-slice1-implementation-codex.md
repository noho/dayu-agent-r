# WU-PROJ-01 Slice 1 Implementation Report

## 元数据

- Work unit: `WU-PROJ-01`
- Gate: implementation
- Slice: Slice 1, EventLog-backed pre-dispatch compact material source
- Agent: AgentCodex
- 日期: 2026-06-11

## 实现内容

- 在 `dayu/host/compact_material.py` 新增 `CompactMaterialSourceBoundary` 与 `PreDispatchCompactMaterialView`。
- 新增 `build_pre_dispatch_compact_material_view(...)`，从当前 transaction 内读取 EventLog / payload truth，构造：
  - latest accepted `CONTEXT_COMPACTED` 对应的 `previous_compacted_view`。
  - latest compact 后、当前 input 前的 canonical delta material。
  - 当前 `USER_INPUT_ACCEPTED` display text anchor。
  - latest compact accepted evidence mapping 派生的 `represented_evidence_refs`。
  - 与 material view 同源的 `budget_fragments`。
- 修改 `build_compact_material_pack(...)`，新增 keyword-only `previous_compacted_view` 参数；传入 `None` 时保留既有 snapshot path，传入 tuple 时使用显式 previous view 并跳过 snapshot path。
- Builder 不读取 Conversation Memory snapshot，不伪造 `ConversationMemorySnapshotVNext`，payload / accepted candidate digest 损坏时 fail closed 为 `HostDurableError`。

## 测试覆盖

- 首次 compact：无 previous compact，delta 包含 current input 前 user / assistant / evidence material，current input 只在 anchor。
- 首次 compact 空 delta：current input 前没有 relevant canonical fact 时，delta 起点与终点均为 current input sequence。
- 第二次 compact：previous view 来自 latest accepted compact candidate，delta 只包含 compact 后新 facts。
- memory snapshot lag / missing 不影响 EventLog-backed builder 输出。
- represented evidence refs 只来自 latest compact accepted mapping，不从 memory snapshot 排除。
- compact payload digest 损坏 fail closed，不进入 memory repair / Run recovery 语义。
- `build_compact_material_pack(...)` explicit previous view path 与旧 snapshot path 均有覆盖。

## README 决策

- 已更新 `dayu/host/README.md`：澄清 ordinary RunInput snapshot path 与 pre-dispatch compact EventLog-backed truth path 的边界。
- 已更新 `tests/README.md`：补充 `test_compact_material.py` 的 EventLog-backed pre-dispatch compact material source 覆盖范围。

## 验证

- `source .venv/bin/activate && python -m pytest tests/host/test_compact_material.py`
- `source .venv/bin/activate && pyright`

## Blocking Open Questions

- 无。

## Residual Risks

- Slice 1 只落地 builder 与 pack 显式 previous-view path，尚未改 dispatch proactive call path；后续 slice 需要把 proactive budget estimate、segment selection 与 compaction request 切到该 material view。
- Evidence query text 复用 durable request atoms；测试覆盖了无 request atom 的 limited-signal 路径，带 `TOOL_CALL_REQUESTED` 的完整 query atom 已由既有 compaction evidence / ToolRuntime 测试覆盖。
