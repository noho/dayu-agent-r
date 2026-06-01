# WU-CTX-02 + WU-CTX-03 Slice B Code Review Controller Adjudication

## 1. 裁决结论

Slice B code review 需要一次 fix，然后 focused re-review。

`AgentMiMo` 结论为 PASS，无 blocker；`AgentDS` 结论为 PASS，但提出 1 个 medium、1 个 low、2 个 info。基于 `docs/host/design.md` 第 25 节对 compact failure diagnostic 可验证性的要求，以及项目重复逻辑约束，接受 F1 与 F2。

## 2. Finding 裁决

| ID | 来源 | Finding | 裁决 | 理由 |
|---|---|---|---|---|
| DS-F1 | docs/reviews/wu-ctx-02-03-code-review-sliceB-ds-20260601.md | `_assert_failed_payload_no_fallback` 在两个测试模块中逐字重复 | accepted | 两个测试模块重复 32 行相同 helper，后续 Slice C/D 还会继续扩展 failed payload 断言；当前抽取可减少同步维护风险，符合项目重复逻辑必须抽取的约束。 |
| DS-F2 | docs/reviews/wu-ctx-02-03-code-review-sliceB-ds-20260601.md | `_validate_failed_fallback_fields` 拒绝路径缺少显式单元测试 | accepted | Slice B 的目标是补足 failed payload validator 的可观察诊断；合法路径和非法 action 已覆盖，但 fallback 字段组合拒绝路径缺回归保护，容易在后续 fallback 接线时被削弱。 |
| DS-F3 | docs/reviews/wu-ctx-02-03-code-review-sliceB-ds-20260601.md | `context_budget_policy_missing` 与 `input_event_missing` 前置条件路径无集成测试 | deferred-with-owner | 这两条是边缘 precondition path，当前统一 helper 和 payload builder 已覆盖核心字段；若 Slice D 触及 reactive precondition / fallback failure，可继续评估是否补集成测试。Owner: WU-CTX Slice D / aggregate review。 |
| DS-F9 | docs/reviews/wu-ctx-02-03-code-review-sliceB-ds-20260601.md | 冗余括号 | rejected-with-reason | 纯格式问题，不影响可读性或行为；不为它单独扩大 fix scope。 |

## 3. Required Fix

Fix 必须覆盖：

- 抽取 `_assert_failed_payload_no_fallback` 到 Host 测试共享 helper，例如 `tests/host/_context_compaction_assertions.py`，并让 `tests/host/test_dispatch_scheduler.py` 与 `tests/host/test_engine_ingest_mapping.py` 复用同一 helper。新 helper 必须有中文 docstring、严格类型签名，不使用 `Any` / `object`。
- 在 `tests/host/test_context_compact_events.py` 增加 validator 拒绝路径测试：
  - `fallback_action="not_applicable"` 且任一 fallback 诊断字段非 `None` 必须拒绝。
  - `fallback_action="dispatch"` 且必需 fallback 诊断字段缺失 / 为 `None` 必须拒绝。
  - `fallback_action="fail_closed"` 且必需 fallback 诊断字段缺失 / 为 `None` 必须拒绝。
- 不改 production behavior，除非测试抽取暴露类型问题；不得实现 fallback，不得改状态机 / schema / public API。

Allowed write files:

- `tests/host/test_context_compact_events.py`
- `tests/host/test_dispatch_scheduler.py`
- `tests/host/test_engine_ingest_mapping.py`
- `tests/host/_context_compaction_assertions.py`
- `docs/reviews/wu-ctx-02-03-fix-sliceB-codex-20260601.md`

Required validation:

- `pytest tests/host/test_context_compact_events.py tests/host/test_dispatch_scheduler.py tests/host/test_engine_ingest_mapping.py -q`
- `python -m pyright dayu/ tests/ utils/`

## 4. Re-review Scope

Focused re-review 只需复核 DS-F1、DS-F2 是否已修复，DS-F3 是否保持 deferred-with-owner，DS-F9 是否未被扩大为必修。

## 5. Blocking Open Questions

none

