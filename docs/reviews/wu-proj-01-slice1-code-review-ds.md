# WU-PROJ-01 Slice 1 Code Review — AgentDS

## 元数据

- Work unit: `WU-PROJ-01`
- Gate: code review
- Slice: Slice 1 — EventLog-backed pre-dispatch compact material source
- Reviewer: AgentDS
- 日期: 2026-06-11
- 设计真源: `docs/host/design.md`; `docs/engine/design.md`
- 总控真源: `docs/host/issues-implementation-control.md`
- Accepted plan: `docs/host/wu-proj-01-compact-material-truth-and-bounded-memory-catchup-plan.md`
- Implementation report: `docs/reviews/wu-proj-01-slice1-implementation-codex.md`
- Review scope: `dayu/host/compact_material.py`, `tests/host/test_compact_material.py`, `dayu/host/README.md`, `tests/README.md`, `docs/reviews/wu-proj-01-slice1-implementation-codex.md`, `docs/host/issues-implementation-control.md` (bookkeeping only)

## Verdict

**PASS** — 无 blocking findings。

## 验证复验

| 检查项 | 结果 |
|---|---|
| `pytest tests/host/test_compact_material.py` | 28 passed |
| `pyright dayu/host/compact_material.py tests/host/test_compact_material.py` | 0 errors, 0 warnings |

AgentCodex 报告的验证结果与本地复验一致。

## Findings by Severity

### 无 Critical / High / Medium 严重度 finding

---

### DS-F1: `_snapshot_with_goal` 未使用 `current_goal` 参数

- **严重度**: Low
- **类别**: Maintainability
- **位置**: `tests/host/test_compact_material.py:1675-1691`

`_snapshot_with_goal` 接受 `current_goal: str` 参数，但在函数体第一行即 `del current_goal`，随后直接返回 `base`（`_empty_snapshot`）。该函数在测试中有 3 处调用，都传入了有意义的 `current_goal` 字符串，但该值对 snapshot 状态无任何影响。

这不是 correctness 问题——调用处的结果仍然正确，因为 snapshot 不依赖 `current_goal`。但它对未来的测试维护者构成困惑：阅读调用代码时会预期 `current_goal` 被写入 snapshot 的某处，而实际 snapshot 没有该字段。

**建议**: 要么删除该参数并重命名为 `_empty_snapshot_with_fact`（但该函数需要同时接受 `claim_text`），要么在 docstring 中显式说明该参数仅为 API 对齐保留且不影响输出。最干净的做法是将该 helper 改为只接受实际使用的参数。

---

### DS-F2: `_snapshot_with_goal_and_fact` 构造的 snapshot 中 `evidence_fact_memory` 的 `provenance` 使用外部 snapshot id 作为 `event_id`

- **严重度**: Low
- **类别**: Maintainability
- **位置**: `tests/host/test_compact_material.py:1694-1752`

`_snapshot_with_goal_and_fact` 构造的 `EvidenceBackedFactView.provenance.event_id` 使用 `"event-memory-compact"`（硬编码字符串），但该 event_id 不在测试 EventLog 中存在。在测试 `test_pre_dispatch_builder_ignores_memory_snapshot_lag_or_missing` 中，该 snapshot 仅用于断言 `lagged_snapshot.evidence_fact_memory.evidence_backed_facts[0].claim_text` 不等于 builder 输出——snapshot 本身不被 builder 消费，所以该不存在的 event_id 不会导致 failure。但若未来测试复用该 fixture 并尝试通过 EventLog 回查 provenance，会出现不可预期的失败。

**建议**: 将 `event_id` 改为 `None` 或使用 `_SESSION_ID` 中确实存在的 event id，明确表达该 snapshot 的 provenance 不映射到测试 EventLog 中。

---

### DS-F3: `PreDispatchCompactMaterialView` 存在 source_boundary 字段与其扁平副本的冗余

- **严重度**: Informational
- **类别**: Maintainability
- **位置**: `dayu/host/compact_material.py:392-453`

`PreDispatchCompactMaterialView` 同时包含 `source_boundary: CompactMaterialSourceBoundary` 和四个扁平便捷字段（`latest_compacted_event_id`, `latest_compacted_event_sequence`, `post_compact_delta_start_sequence`, `post_compact_delta_end_sequence`）。`__post_init__` 中逐一校验扁平字段与 `source_boundary` 对应字段一致。

这是 accepted plan 允许的设计——plan 明确将扁平字段标记为"便捷诊断字段"。`__post_init__` 的交叉校验确保不会出现不一致。但 5 个字段存储同一份数据增加了维护面：未来若对 source_boundary 某字段语义做调整，必须同步修改扁平字段、构造调用和 `__post_init__` 校验。

**当前不构成问题**，标记为 informational 供后续 slice 参考。

---

### DS-F4: `_accepted_tool_evidence_delta_blocks` 对 `TOOL_RESULT_ACCEPTED` 缺少 `requested_event_ref` 的分支覆盖

- **严重度**: Informational
- **类别**: Test Coverage
- **位置**: `dayu/host/compact_material.py:2054-2128`; `tests/host/test_compact_material.py`

`_accepted_tool_evidence_delta_blocks` 在 `envelope.tool_query.tool_call_requested_event_ref` 为 `None` 时 fallback 到 `row.event_id`，这意味着 `tool_call_event_ref` 不会为 None。但 `_readable_query_text_from_envelope` 中，当 `requested_event_ref` 为 `None` 时走 limited-signal 路径。当前所有测试用例的 `_accepted_evidence_envelope_for_event` 都设置 `tool_call_requested_event_ref=None`，因此 `_readable_query_text_from_envelope` 总是走 limited-signal 路径。

这意味着有两个路径未被测试覆盖：
1. `requested_event_ref` 非 None 且对应 EventLog row 存在时的完整 query text 路径。
2. `requested_event_ref` 非 None 但对应 row 不存在/类型不匹配/参数不一致时的各种 limited-signal 退化路径。

根据 Codex report，"带 `TOOL_CALL_REQUESTED` 的完整 query atom 已由既有 compaction evidence / ToolRuntime 测试覆盖"，这些路径属于已有测试的间接覆盖范围。但 `_readable_query_text_from_envelope` 是本 Slice 新增的函数，其内部所有分支应该有本模块的直接覆盖或显式说明依赖外部覆盖。

**不阻塞**，但建议在 Slice 2 或后续清理中补一个 focused test。

---

### DS-F5: `_accepted_tool_evidence_delta_blocks` 对 `result_preview` 的防御性检查与既有路径行为一致

- **严重度**: Informational
- **类别**: Correctness (verified)
- **位置**: `dayu/host/compact_material.py:2094-2095`

```python
if _PAYLOAD_FIELD_RESULT_PREVIEW in result_payload:
    raise HostDurableError("TOOL_RESULT_ACCEPTED result_preview is not allowed")
```

这是正确的 fail-closed 检查：`result_preview` 是面向 UI 流式展示的 preview 字段，不应出现在 canonical `TOOL_RESULT_ACCEPTED` payload 中。该检查与现有 `build_accepted_tool_evidence_material_blocks` 的行为一致。标记为 informational，确认这不是新增的过度防御。

## Mandatory Check Results

### 1. build_pre_dispatch_compact_material_view 只读 EventLog/payload/artifact truth

**PASS**。Builder 调用链为：
- `_validated_current_input_event` → EventLogStore + payload
- `_latest_compacted_event_before_current_input` → SQL query + EventLogStore
- `_accepted_evidence_mapping_refs_from_compacted_event` → compact payload
- `_previous_compacted_view_from_compacted_event` → compact payload + artifact digest
- `_post_compact_delta_start_sequence` → SQL query
- `_post_compact_delta_rows` → SQL query
- `_pre_dispatch_delta_material_blocks` → EventLogStore + payload resolution

全程无 ConversationMemorySnapshotVNext 导入或读取。测试 `test_pre_dispatch_builder_ignores_memory_snapshot_lag_or_missing` 显式证明即使 snapshot 滞后或包含额外事实，builder 输出也不受影响。

### 2. latest accepted CONTEXT_COMPACTED → previous_compacted_view 解析、digest/source 校验、evidence mapping 去重

**PASS**。

- **Digest 校验**: `_previous_compacted_view_from_compacted_event` 在 L1749 执行 `sha256_digest_json(candidate) != expected_digest` → HostDurableError
- **Payload 结构校验**: `_validated_compacted_payload` 调用 `validate_context_compacted_payload(payload)` 进行 schema-level 校验
- **Evidence 去重来源**: `_accepted_evidence_mapping_refs_from_compacted_event` 从 compact payload 的 `accepted_evidence_mapping_refs` 字段读取，不从 memory snapshot 读取
- **去重执行**: `_accepted_tool_evidence_delta_blocks` 在 L2085 通过 `envelope.evidence_id in represented_evidence_refs` 去重
- **测试**: `test_pre_dispatch_represented_evidence_refs_only_from_latest_compact` 证明即使 memory 中有额外 evidence fact，去重也不受其影响

### 3. post_compact_delta_material boundary 严格为 latest compact 后、当前 input 前

**PASS**。

- **Delta 起点计算**: `_post_compact_delta_start_sequence`:
  - 有 latest compact: `latest_compacted_event.event_sequence + 1`
  - 无 latest compact: 查询 session 内第一条 relevant canonical fact
  - 无 relevant fact: 等于 `current_input_sequence`
- **Delta 终点**: 排他式 `current_event.event_sequence`（SQL 使用 `<`）
- **Current input anchor 不进入 delta**: `_pre_dispatch_delta_material_blocks` 中 `USER_INPUT_ACCEPTED` 只处理历史事件；当前 input 的 event_sequence 等于 end_sequence，被 SQL `<` 排除在外
- **测试**: `test_pre_dispatch_first_compact_uses_eventlog_delta_before_current_input` 断言 current input text 不在 material_blocks 文本中
- **Boundary 约束**: `CompactMaterialSourceBoundary.__post_init__` L388 强制 `post_compact_delta_end_sequence == current_input_event_sequence`

### 4. 首次 compact 起点 cursor 语义

**PASS**。

- 有历史 relevant fact 时: `_post_compact_delta_start_sequence` 返回第一条 relevant canonical fact 的 sequence
- 无历史 relevant fact 时: 返回 current_input_sequence，delta 为空 tuple
- 测试: `test_pre_dispatch_first_compact_empty_delta_starts_at_current_input` 证明 delta_start == delta_end == current_input_sequence 且 material_blocks 为空

### 5. build_compact_material_pack previous_compacted_view=None 与 explicit tuple 两条路径类型安全

**PASS**。

- **Signature**: `previous_compacted_view: tuple[CompactMaterialBlock, ...] | None = None` — 类型安全，不可将非 CompactMaterialBlock 传入
- **None 路径**: 走既有 `_previous_blocks_from_snapshot(snapshot)`，反向兼容
- **Non-None 路径**: L992-996 先通过 `_require_compact_material_block_tuple` 校验元素类型，再直接赋值
- **空 tuple 语义**: `()` 表示"明确无 previous view"，不等于 `None`（走 snapshot 路径）。测试 `test_build_compact_material_pack_uses_explicit_previous_view_without_snapshot` 同时覆盖非空 explicit previous 和空 tuple first_pack 两条子路径
- **既有调用兼容**: 所有既有 `build_compact_material_pack(...)` 调用点未传 `previous_compacted_view`，走默认 `None` → snapshot path

### 6. 无 God function / 过度重复解析 / fragile JSON parsing / 裸内部 ref 投影到 LLM-facing text

**PASS**。

- **God function**: `build_pre_dispatch_compact_material_view` ~100 行，由 6 个 private helper 组成，每个 helper 单一职责
- **JSON parsing**: 通过 `_required_json_text` / `_required_json_mapping` / `_required_json_mapping_tuple` / `_json_mapping` 等 typed helper 统一处理，均 fail closed → HostDurableError
- **LLM-facing text**: previous view 文本通过 `_candidate_session_summary_text` / `_candidate_facts_text` 等 helper 生成，使用业务可读前缀（`fact=claim_text=...`），不暴露 event_id / payload_ref / digest
- **Limited signal**: evidence query 的 degraded path 使用中文业务语义（"已验收工具请求参数材料缺失"），不以 `tool_call_id=xxx` 裸串投影
- **Budget fragments**: 使用 `previous:P1` / `current_input_anchor` 等业务可读 refs，不使用 event_sequence、cursor 或 digest

### 7. 新增/修改函数中文 docstring、严格类型

**PASS**。

- 所有新增 public 函数（`build_pre_dispatch_compact_material_view`）和新增 dataclass（`CompactMaterialSourceBoundary`、`PreDispatchCompactMaterialView`）均有完整中文 docstring 含 `:param` / `:returns` / `:raises`
- 所有新增 private helper 均有中文 docstring
- 类型签名严格：无 `Any`、无 `object`、无裸容器
- 返回类型显式：`tuple[CompactMaterialBlock, ...]`、`EventLogRow | None`、`str | None` 等
- `__post_init__` 校验覆盖所有 invariant

### 8. Tests 覆盖 plan 要求

**PASS**。Plan Slice 1 要求的 6 类测试均已覆盖：

| Plan 要求 | 对应测试 |
|---|---|
| 首次 compact：无 previous compact，delta 包含 current input 前 canonical blocks，current input 只在 anchor | `test_pre_dispatch_first_compact_uses_eventlog_delta_before_current_input` |
| 首次 compact delta 为空时起点等于 current input sequence | `test_pre_dispatch_first_compact_empty_delta_starts_at_current_input` |
| 第二次 compact：previous view 来自 accepted compact candidate，delta 只包含 compact 后新 facts | `test_pre_dispatch_second_compact_rolls_from_latest_accepted_candidate` |
| memory snapshot lag / missing 不影响 builder 输出 | `test_pre_dispatch_builder_ignores_memory_snapshot_lag_or_missing` |
| represented evidence refs 只来自 latest compact accepted mapping | `test_pre_dispatch_represented_evidence_refs_only_from_latest_compact` |
| payload 损坏 fail closed | `test_pre_dispatch_payload_damage_fails_closed_without_recovery_request` |
| build_compact_material_pack explicit previous view 与 snapshot 路径 | `test_build_compact_material_pack_uses_explicit_previous_view_without_snapshot` |

测试 fixture 设计良好：增量 seed → run_write → run_read(build) 模式，EventLogStore 直连，不绕过 durable store。7 个新增 focused test 构成完整行为闭环。

### 9. README 更新

**PASS**。

- `dayu/host/README.md`: 在 Conversation Memory projection 章节末尾将"RunInputBuilder 和 Context Governance 可以读取 memory snapshot 作为输入材料"改为明确区分 ordinary RunInput（读 snapshot）和 pre-dispatch compact material（EventLog truth），只新增一句，不写未来计划
- `tests/README.md`: 在 P12.6 memory semantic smoke 条目中追加"EventLog-backed pre-dispatch compact material source"和"explicit previous compacted view pack path"两个覆盖描述，属于对已有测试分类的事实更新
- 两个 README 的更新均符合各自的 `Agent更新约束【必须遵守】`

### 10. Control doc bookkeeping

**PASS**。

- gate 更新为 `code review`
- implementation status 更新为 `WU-PROJ-01 Slice 1 implementation completed; awaiting two-lane code review by AgentMiMo and AgentDS`
- next entry point 更新为 `WU-PROJ-01 Slice 1 code review gate via AgentMiMo and AgentDS`
- 新增 Slice 1 implementation gate 条目，记录实现者、变更文件、验证结果、controller 决策和期望 review artifacts
- 所有 bookkeeping 字段仅记录已完成事实，无 forward-looking statement

## Blocking Open Questions

无。

## Residual Risks

### DS-R1: `_readable_query_text_from_envelope` 的非 limited-signal 路径缺少模块内直接测试覆盖

- **来源**: DS-F4
- **Owner**: Slice 2 (proactive Context Governance) 或后续 focused test cleanup
- **说明**: `_readable_query_text_from_envelope` 的完整 query atom 路径（`requested_event_ref` 非 None、对应 row 存在且校验通过）在本模块内无直接测试。AgentCodex report 称该路径由既有 compaction evidence / ToolRuntime 测试覆盖。本 reviewer 未独立验证该声称——不在本 gate scope。
- **影响**: 若既有测试未实际覆盖该分支且该分支存在 bug，proactive compact evidence query 会在进入 Slice 2 dispatch 集成后出现不可预期的 limited-signal 退化。
- **建议**: Slice 2 implementation 前，确认既有测试确实覆盖了 `_readable_query_text_from_envelope` 的完整 query atom 路径；若未覆盖，补 focused test。

### DS-R2: `_valided_current_input_event` 的失败分支无独立单元测试

- **来源**: DS-F3 comment
- **Owner**: Slice 2 或后续 test hardening
- **说明**: `_validated_current_input_event` 的 5 个 HostDurableError 抛出路径（missing event、session mismatch、type mismatch、sequence mismatch、display text mismatch）均无独立测试。当前通过 end-to-end builder 测试的正确路径间接覆盖输入校验的存在性，但错误路径的精确错误类型和错误信息无断言。
- **影响**: Low。这些错误路径在 production 中被 `build_pre_dispatch_compact_material_view` 的 fail-closed 语义兜底（均抛 HostDurableError），不会静默通过。缺少独立测试意味着未来重构该校验逻辑时没有安全网。
- **建议**: 非阻塞。可在 Slice 2 或后续统一补 Host durable error 的 focused error-path 测试。

### DS-R3: `_snapshot_with_goal` 冗余参数

- **来源**: DS-F1
- **Owner**: 后续 test cleanup
- **说明**: 辅助函数接受但不使用的参数构成维护债务。该 helper 在 3 处被调用且每次传入有意义的字符串，读者会误以为该值被写入 snapshot。
- **影响**: 纯测试维护面，不影响 production correctness。
- **建议**: 后续清理轮次中移除 `current_goal` 参数。

## 总结

Slice 1 实现质量高，架构对齐 accepted plan，所有 mandatory checks 通过。7 个新增 focused test 覆盖了首次 compact、滚动 compact、memory 隔离、evidence 去重来源、fail-closed 和 explicit previous view 的关键路径。28 tests passed，pyright 0 errors。无 blocking findings，可进入下一 gate。

3 条 low/informational findings 和 3 条 residual risks 均不阻塞 Slice 2 推进。
