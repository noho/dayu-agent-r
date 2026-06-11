# WU-PROJ-01 Slice 1 Code Review Controller Adjudication

## 元数据

- Work unit: `WU-PROJ-01`
- Gate: Slice 1 code review controller adjudication
- 日期: 2026-06-11
- Implementation artifact: `docs/reviews/wu-proj-01-slice1-implementation-codex.md`
- AgentMiMo review artifact: `docs/reviews/wu-proj-01-slice1-code-review-mimo.md`
- AgentDS review artifact: `docs/reviews/wu-proj-01-slice1-code-review-ds.md`
- Controller verdict: fix required for accepted low findings

## Review Verdicts

| Lane | Verdict | Controller decision |
|---|---|---|
| AgentMiMo | pass-with-findings | accepted; low findings triaged |
| AgentDS | PASS | accepted; low findings triaged |

两路 review 均确认 Slice 1 implementation 的核心语义正确：builder 只读 EventLog / payload / artifact truth，previous view 来自 accepted compact event，delta boundary 与 current input anchor 语义正确，explicit `previous_compacted_view` pack path 类型安全，focused tests 与 pyright 通过。无 blocking finding。

## Accepted Fix Findings

| Finding | 裁决 | 当前 fix 要求 |
|---|---|---|
| MiMo F1: `CompactMaterialSourceBoundary.__post_init__` inverted boundary / end mismatch 缺少直接测试 | accepted | 在 `tests/host/test_compact_material.py` 补 direct negative tests。 |
| MiMo F2: `PreDispatchCompactMaterialView.__post_init__` boundary mismatch 缺少直接测试 | accepted | 补 direct negative tests 覆盖便捷字段与 `source_boundary` 不一致时抛 `ValueError`。 |
| MiMo F3: `_accepted_tool_evidence_delta_blocks` fallback `tool_call_event_ref` 语义模糊 | accepted | 在相关 helper docstring / 注释中明确：无 request atom 时该 ref 退化为 producer event ref，仅用于 prompt-local provenance，不表示 request event 存在。 |
| DS-F1: `_snapshot_with_goal` 未使用 `current_goal` 参数 | accepted | 移除冗余参数或改造 helper，使调用点只传实际使用的参数。 |
| DS-F2: `_snapshot_with_goal_and_fact` fixture provenance 使用不存在的 event id | accepted | 将 fixture provenance 调整为不误导维护者的值；若类型不允许 `None`，使用当前测试 EventLog 中实际存在且语义合理的 event id。 |

## Rejected / Deferred Findings

| Finding | 裁决 | 理由 / Owner |
|---|---|---|
| MiMo F4: `_post_compact_delta_rows` SQL event type 白名单为硬编码 | rejected-with-reason | 当前白名单正是 accepted plan 的 relevant canonical facts 集合，且使用模块常量。未来新增 canonical fact type 时由对应 WU 修改。 |
| MiMo F5 / F6 / F7 informational findings | rejected-with-reason | 这些条目确认 README 和 bookkeeping 合格，无需 fix。 |
| DS-F3: `PreDispatchCompactMaterialView` source_boundary 与扁平字段冗余 | deferred-with-owner | accepted plan 明确允许便捷诊断字段，并已有一致性校验。若后续维护成本升高，由 WU-PROJ-01 later cleanup 或 Slice 2 集成 review 再裁决。 |
| DS-F4 / DS-R1: `_readable_query_text_from_envelope` 完整 query atom 路径缺模块内直接覆盖 | deferred-with-owner | 当前 limited-signal 路径已覆盖，完整 request atom 与 proactive dispatch 物化更适合 Slice 2 集成时确认；Owner 为 WU-PROJ-01 Slice 2。 |
| DS-R2: `_validated_current_input_event` failure branches 缺少独立单元测试 | deferred-with-owner | 当前 all failure branches 都 fail closed 为 `HostDurableError`，非 blocker。Owner 为后续 test hardening。 |
| DS-R3: `_snapshot_with_goal` 冗余参数 | accepted | 与 DS-F1 合并处理。 |

## Fix Gate

- Responsible agent: AgentCodex
- Expected fix artifact: `docs/reviews/wu-proj-01-slice1-fix-codex.md`
- Allowed files:
  - `dayu/host/compact_material.py`
  - `tests/host/test_compact_material.py`
  - `docs/reviews/wu-proj-01-slice1-fix-codex.md`
- Required validation:
  - `source .venv/bin/activate && python -m pytest tests/host/test_compact_material.py`
  - `source .venv/bin/activate && pyright`

Fix gate 不得修改 design docs、control doc、README、GitHub issue、commit、push、PR，除非修复过程中发现 accepted finding 无法在 allowed files 内完成；这种情况必须停止并回报。
