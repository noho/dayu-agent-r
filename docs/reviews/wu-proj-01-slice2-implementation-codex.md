# WU-PROJ-01 Slice 2 Implementation - AgentCodex

## Implemented Slice

Slice 2：Proactive Context Governance 使用 Slice 1 的同源 `PreDispatchCompactMaterialView`。

本次实现让 pre-start proactive governance 在读取当前 input event 后立即构造 EventLog-backed material view，并让 budget estimate、segment selection、compact material pack、compaction request refs 与 compactor-failure fallback 共用这份冻结 view。

## Changed Files

- `dayu/host/dispatch.py`
  - proactive budget estimate 改为使用 `material_view.budget_fragments`，不再只估当前 prompt。
  - `_prepare_compact_before_dispatch(...)` 改为接收冻结 material view；`select_compact_segment(...)` 与 `build_compact_material_pack(...)` 使用同一 `material_view.material_blocks`。
  - proactive `build_compact_material_pack(...)` 显式传入 `previous_compacted_view=material_view.previous_compacted_view`。
  - `CompactionRequest.evidence_backed_fact_refs`、`recent_raw_turn_refs`、`older_raw_turn_refs` 从 selected material / current anchor 派生。
  - 删除 dispatch 内旧 proactive material 拼接和 memory snapshot evidence 去重职责。
  - material source failure 在 Run 启动前写 `CONTEXT_COMPACTION_FAILED` 并 fail closed，不进入 recent-window fallback。
  - deterministic recent-window fallback 只在已有可信 material view 的 compactor/config failure 路径使用，并从该 view 构造 fallback window。
  - hard-threshold precondition 不再进入 fallback。
- `dayu/host/engine_ingest.py`
  - reactive compact pending 增加 latest accepted compact 对应的 explicit previous view。
  - reactive root request 和 pass request 调用 `build_compact_material_pack(...)` 时传入 explicit `previous_compacted_view`。
  - 仅做 previous-view source helper 最小适配；未改 reactive multi-pass、overflow material freeze 或 evidence 分段。
- `tests/host/test_dispatch_scheduler.py`
  - 覆盖 proactive budget 使用同源 material view。
  - 覆盖第二次 proactive compact 使用 previous view 且不重展旧 raw material。
  - 覆盖 material source failure fail closed、不创建 Attempt、不 fallback。
  - 覆盖 reactive compact request 使用 latest previous view。
  - 更新 hard-threshold precondition 测试为 no-fallback 语义。
- `tests/host/test_compact_material.py`
  - 补齐 `_readable_query_text_from_envelope` 完整 `TOOL_CALL_REQUESTED` query atom 路径测试。

## Validation

- `source .venv/bin/activate && python -m pytest tests/host/test_compact_material.py`：32 passed。
- `source .venv/bin/activate && python -m pytest tests/host/test_dispatch_scheduler.py -k "governance or compact or proactive"`：18 passed，48 deselected。
- `source .venv/bin/activate && python -m pytest tests/host/test_public_compact_smoke.py`：6 passed，1 skipped。
- `source .venv/bin/activate && pyright`：0 errors。

## README Decision

- 已按触发规则读取 `dayu/host/README.md` 的 Agent 更新约束。当前改动没有改变 Host public API、公共契约、状态机名称或开发者稳定入口；已有 README 已说明 Context Governance 属于 Host、Conversation Memory 是 projection/read model，因此不更新。
- 已按触发规则读取 `tests/README.md` 的更新边界。当前只是在既有 `tests/host/test_dispatch_scheduler.py` 与 `tests/host/test_compact_material.py` 内补覆盖，没有新增测试层级或稳定运行入口，因此不更新。

## Blocking Open Questions

- 无。

## Residual Risks

- reactive path 本次只完成 latest previous view 显式传递；reactive multi-pass、overflow ordinary material freeze 和 evidence-block 分段仍按 accepted plan 留给后续 owner。
- fallback 仍是 deterministic recent-window fallback，不提交 `CONTEXT_COMPACTED`，只在已有可信 material view 的 compactor/config failure 路径使用。
