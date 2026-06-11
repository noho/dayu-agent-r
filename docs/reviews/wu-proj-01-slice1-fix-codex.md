# WU-PROJ-01 Slice 1 Fix Report - AgentCodex

## 元数据

- Work unit: `WU-PROJ-01`
- Gate: Slice 1 fix
- 日期: 2026-06-11
- Scope: controller accepted code-review findings only

## Fixed Findings

1. **MiMo F1**: 为 `CompactMaterialSourceBoundary.__post_init__` 补 direct negative tests，覆盖 inverted delta boundary 与 delta end / current input sequence mismatch。
2. **MiMo F2**: 为 `PreDispatchCompactMaterialView.__post_init__` 补 direct negative tests，覆盖四个便捷诊断字段与 `source_boundary` 不一致时抛 `ValueError`。
3. **MiMo F3**: 澄清 `_accepted_tool_evidence_delta_blocks` 中 fallback `tool_call_event_ref` 的语义：缺少 durable request atom 时退化为 producer event ref，只用于 prompt-local provenance，不表示 request event 存在。
4. **DS-F1 / DS-R3**: 删除 `_snapshot_with_goal` 冗余 helper，并将调用点改为直接使用 `_empty_snapshot`；`_snapshot_with_fact` 只接收实际使用的参数。
5. **DS-F2**: 修正 memory fact fixture provenance，不再使用不存在的硬编码 `event-memory-compact`；调用点显式传入当前测试 EventLog 中实际存在且语义合理的来源事件 id，并按语义设置 `tool_result_ref`。

## Changed Files

- `dayu/host/compact_material.py`
- `tests/host/test_compact_material.py`
- `docs/reviews/wu-proj-01-slice1-fix-codex.md`

## Validation

- `source .venv/bin/activate && python -m pytest tests/host/test_compact_material.py`
  - Result: `31 passed`
- `source .venv/bin/activate && pyright`
  - Result: `0 errors, 0 warnings, 0 informations`

## Blocking Open Questions

无。

## Residual Risks

- 本轮严格限定为 controller accepted findings，未处理 deferred findings。
- `pyright` 输出提示存在新版本 `1.1.410`，当前验证仍使用项目环境中的 `1.1.409`，不影响本轮结果。
