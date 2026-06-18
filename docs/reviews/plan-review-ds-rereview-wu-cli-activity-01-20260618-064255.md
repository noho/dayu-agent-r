# Plan Re-Review: WU-CLI-ACTIVITY-01 follow-up — DS-01 到 DS-06 修复验证

## 元数据

- **Reviewer**: AgentDS
- **Re-review date**: 2026-06-18
- **Target revised plan**: `docs/host/host-issues/wu-cli-activity-01-followup-delta-eventlog-projection-catchup-plan.md`
- **Original review**: `docs/reviews/plan-review-20260618-063418-ds-wu-cli-activity-01-followup.md`
- **Fix artifact**: `docs/reviews/plan-review-fix-20260618-codex-wu-cli-activity-01-followup.md`
- **Re-review artifact**: `docs/reviews/plan-review-ds-rereview-wu-cli-activity-01-20260618-064255.md`
- **Scope**: 仅验证 DS-01 至 DS-06 是否在修订后的 plan 中修复；不扩大 scope 搜索新 finding。

## Re-Review Method

逐条对照原始 finding 的问题描述、修复建议，与修订后 plan 的对应章节，判断修复是否到位。若发现修复本身引入新 blocker，记录但不纳入本次 scope 的 finding 重新编号。

## 逐条验证

### DS-01 — 已修复

- **原始问题**: Plan 移除 design.md:3213 "不得让 dispatch hot path 无上限同步补账" 的约束保护，after-commit / after-compact catch-up 变为无上限同步追平，严重程度高。
- **修复验证**:
  - 修订后 Plan Design Alignment 段（第 62-63 行）明确保留 hot-path 硬约束："after-commit / after-compact 不能做无界同步补账，只能移除机会性同步动作，或执行 latency-only、显式页数上限的 maintenance。"
  - Implementation Decision 6（第 176-178 行）规定 required correctness catch-up 与 hot-path opportunity path 分治：required catch-up 无语义预算追到 target / idle / failure；after-commit / after-compact 只能 bounded latency-only maintenance 或删除 hook。
  - Slice 4 Exact changes（第 332-337 行）给出二选一实现方案，优先选择改动更小且证据支持的方案。
  - Risk 3（第 427-428 行）状态已标 "covered by Slice 4"，不再推迟给不存在的 future async projection worker。
  - Success Signals（第 42 行）明确 after-commit / after-compact hot-path hook 不执行无界 correctness catch-up。
- **裁决**: 修复完整。plan 现在区分 correctness catch-up（无界但不在 hot path）与 hot-path maintenance（有界或不执行），满足 design.md 硬约束。
- **状态**: **已修复**

### DS-02 — 已修复

- **原始问题**: Contract 段声明 "Public Host API 无计划变更" 与 Success Signals 中 "行为变更" 矛盾，严重程度中。
- **修复验证**:
  - 修订后 Plan Contract 段（第 121 行）改为："Public Host API：签名无计划变更；但 EventLog-backed stream / read 行为会变更，默认不再返回 content_delta、reasoning_delta、tool_call_delta per-delta rows。"
  - 签名不变与行为变更的边界明确，不再误导。
- **裁决**: 修复完整。
- **状态**: **已修复**

### DS-03 — 已修复

- **原始问题**: `FilteredEventLogPage` 边界语义（空 EventLog、`max_event_sequence` 无对应行、cursor 已在 latest row 之上）未定义，严重程度中。
- **修复验证**:
  - 修订后 Plan Implementation Decision 3（第 147-161 行）补充了完整的边界不变量：
    - 空 EventLog 或 cursor 已在 latest row 之上 → `covered_event_sequence=cursor`, `covered_event_id=None`
    - cursor 正好等于 latest row → 同样返回 `covered_event_sequence=cursor`, `covered_event_id=None`
    - 有匹配 row 且达到 page limit → covered cursor 是最后一条匹配 row
    - 未达到 page limit → covered cursor 是 cursor 之后可证明的最大真实 EventLog row
    - `max_event_sequence` 超过实际 latest → 只能覆盖到实际 latest row
    - `max_event_sequence` 无精确 row → 只能覆盖到 `<= max_event_sequence` 的最近真实 row
    - cursor 与读边界之间无真实 row → 返回 `covered_event_sequence=cursor`, `covered_event_id=None`，不得返回不存在 sequence
  - Slice 3 Tests/validation（第 296-297 行）已增加对应的空 EventLog 和 `max_event_sequence` 边界测试 entry。
- **裁决**: 修复完整。所有边界被显式冻结，implementation agent 不再需要自行决定。
- **状态**: **已修复**

### DS-04 — 已修复

- **原始问题**: Motivation 段将 inline repair 的 `_MEMORY_EVENT_TYPES` 与 consumer 的 `_EVENT_TYPE_FILTER` 当前语义等价描述为"看到不同 material"，高估严重性，可能误导 implementation agent 过度重构，严重程度中。
- **修复验证**:
  - 修订后 Plan Motivation 段（第 33 行）修正为："当前 _MEMORY_EVENT_TYPES / _is_memory_projection_row 与 Conversation Memory consumer 的 filter 语义等价，但它们是两份独立列表；未来 memory event type 调整时容易漂移。计划只做最小共源化：提供模块级 conversation_memory_projection_event_filter() 作为单一 filter 真源。"
  - Slice 5 Exact changes（第 375-377 行）固定方案为模块级 helper，不再保留 consumer 实例读取 filter 的备选方案。
  - 动机表述不再高估当前严重性，实施复杂度不再被放大。
- **裁决**: 修复完整。
- **状态**: **已修复**

### DS-05 — 已修复

- **原始问题**: Slice 3 filter-aware read 函数的 matching rows 查询与 covered row 查询的事务边界未显式规定，严重程度低。
- **修复验证**:
  - 修订后 Plan Implementation Decision 3（第 160 行）明确："匹配 rows 查询与 covered row 查询必须在调用方提供的同一个 transaction 内完成。"
  - Slice 3 Exact changes（第 282 行）重复强调："所有查询必须在调用方提供的同一个 transaction 内完成，包括 matching rows 查询和 covered row 查询。"
- **裁决**: 修复完整。
- **状态**: **已修复**

### DS-06 — 已修复

- **原始问题**: `memory_projection_catchup_batch_size` 语义变更但保留旧名字，没有计划更新 docstring/README 说明，可能误导后续维护者，严重程度低。
- **修复验证**:
  - 修订后 Plan Non-goals（第 55 行）明确："不移除或重命名 memory_projection_catchup_batch_size 配置字段；本 WU 必须更新 docstring / README / design 表述，明确它是内部 page size，不是单次 catch-up 的语义预算。"
  - Success Signals（第 41 行）明确该字段含义改为内部 page size。
  - Docs Decision（第 418 行）要求必须更新相关配置 docstring / README / design wording。
  - Risk 5（第 429-430 行）记录为 accepted tradeoff，字段重命名另立后续 WU。
- **裁决**: 修复完整。虽然名称未改，但 plan 明确要求通过文档消歧，且记录了已知 tradeoff。
- **状态**: **已修复**

## 新增 Blocker 检查

修订后 plan 整体自洽，未发现以下情况：
- 修复方案引入新的未定义边界行为。
- 修复方案与 plan 其他部分矛盾。
- 修复方案违反 `docs/host/design.md` 或 `docs/engine/design.md` 的已固定约束。
- 修复方案导致 slice 不可独立验证或 test entry 缺失。

无新增 blocker。

## 汇总

| Finding | 严重程度 | 状态 |
|---------|---------|------|
| DS-01   | 高      | 已修复 |
| DS-02   | 中      | 已修复 |
| DS-03   | 中      | 已修复 |
| DS-04   | 中      | 已修复 |
| DS-05   | 低      | 已修复 |
| DS-06   | 低      | 已修复 |

全部 6 个 accepted finding 已在修订后 plan 中修复，无证据失效，无新增 blocker。

## Final Re-Review Conclusion

**PASS**

修订后 plan 已将原始 review 中 DS-01 至 DS-06 全部六项 finding 修复到位。plan 当前状态满足 code-generation-ready 条件，建议进入 implementation gate。
