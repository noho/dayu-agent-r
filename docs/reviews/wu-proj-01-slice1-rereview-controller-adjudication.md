# WU-PROJ-01 Slice 1 Re-Review Controller Adjudication

## 元数据

- Work unit: `WU-PROJ-01`
- Gate: Slice 1 re-review controller adjudication
- 日期: 2026-06-11
- Fix artifact: `docs/reviews/wu-proj-01-slice1-fix-codex.md`
- AgentMiMo re-review artifact: `docs/reviews/wu-proj-01-slice1-rereview-mimo.md`
- AgentDS re-review artifact: `docs/reviews/wu-proj-01-slice1-rereview-ds.md`
- Controller verdict: accepted; proceed to accepted slice commit

## Re-Review Verdicts

| Lane | Verdict | Controller decision |
|---|---|---|
| AgentMiMo | PASS | accepted |
| AgentDS | PASS | accepted |

两路 re-review 均确认 5 条 controller accepted findings 已全部修复，fix 未引入新的 correctness、type、test 或 architecture 问题。Controller 接受该结论。

## Fixed Findings

| Finding | Re-review status | Controller decision |
|---|---|---|
| `CompactMaterialSourceBoundary.__post_init__` direct negative tests | fixed | accepted |
| `PreDispatchCompactMaterialView.__post_init__` boundary mismatch tests | fixed | accepted |
| fallback `tool_call_event_ref` producer-event provenance 语义说明 | fixed | accepted |
| `_snapshot_with_goal` 冗余 helper / 参数清理 | fixed | accepted |
| memory fact fixture provenance 不再引用不存在 EventLog event id | fixed | accepted |

## Validation

- AgentCodex fix report: `tests/host/test_compact_material.py` passed, 31 tests; `pyright` passed, 0 errors.
- AgentMiMo re-review independently verified: `tests/host/test_compact_material.py` passed, 31 tests; targeted pyright passed, 0 errors.
- AgentDS re-review independently verified: `tests/host/test_compact_material.py` passed, 31 tests; `pyright` passed, 0 errors.

## Deferred Residual Risks

| ID | 状态 | Owner / Destination | 处理方式 |
|---|---|---|---|
| WU-PROJ-01-S1-R1 | deferred-with-owner | WU-PROJ-01 Slice 2 | `_readable_query_text_from_envelope` 完整 query atom 路径缺模块内直接测试覆盖；Slice 2 集成 proactive Context Governance 时确认并按需补 focused test。 |
| WU-PROJ-01-S1-R2 | deferred-with-owner | 后续 test hardening | `_validated_current_input_event` failure branches 缺少独立单元测试；当前均 fail closed 为 `HostDurableError`，不阻塞 Slice 1 accepted commit。 |
| WU-PROJ-01-S1-R3 | deferred-with-owner | WU-PROJ-01 later cleanup / Slice 2 review | `PreDispatchCompactMaterialView` 便捷诊断字段与 `source_boundary` 存在冗余；accepted plan 允许，当前已有一致性校验，若维护成本升高再收敛。 |

## 下一步

- 进入 accepted slice commit gate。
- Commit scope 包含 Slice 1 implementation、fix、tests、README、controller/review artifacts 和总控状态更新。
- Commit 后将 accepted slice commit hash 写回总控，并将 next entry point 指向 WU-PROJ-01 Slice 2 implementation gate via AgentCodex。
