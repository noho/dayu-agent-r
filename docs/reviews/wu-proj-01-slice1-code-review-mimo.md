# WU-PROJ-01 Slice 1 Code Review — AgentMiMo

## 元数据

- Work unit: `WU-PROJ-01`
- Gate: code review
- Slice: Slice 1, EventLog-backed pre-dispatch compact material source
- Reviewer: AgentMiMo
- 日期: 2026-06-11
- Review scope: `dayu/host/compact_material.py`, `tests/host/test_compact_material.py`, `dayu/host/README.md`, `tests/README.md`, `docs/reviews/wu-proj-01-slice1-implementation-codex.md`, `docs/host/issues-implementation-control.md` (gate bookkeeping only)

## Verdict

**pass-with-findings**

Implementation 正确实现了 plan Slice 1 的全部核心要求。`build_pre_dispatch_compact_material_view` 只读 EventLog / payload / artifact truth，不读 Conversation Memory snapshot；`previous_compacted_view` 从 latest accepted compact event 的 accepted candidate 解析并校验 digest；`post_compact_delta_material` boundary 严格为 latest compact 后、current input 前；`build_compact_material_pack` 的 `previous_compacted_view` keyword-only 参数类型安全，`None` 与 explicit tuple 两条路径均有测试覆盖。无 blocking finding。

## Verification

- `source .venv/bin/activate && python -m pytest tests/host/test_compact_material.py` — 28 passed, 0.28s
- `source .venv/bin/activate && pyright dayu/host/compact_material.py tests/host/test_compact_material.py` — 0 errors, 0 warnings, 0 informations

## Findings

### F1 [low-maintainability] CompactMaterialSourceBoundary validation 缺少直接测试

**Severity**: low

**Location**: `dayu/host/compact_material.py:386-389` (`CompactMaterialSourceBoundary.__post_init__`)

**Description**: `CompactMaterialSourceBoundary.__post_init__` 包含两条边界校验：`post_compact_delta_start_sequence > post_compact_delta_end_sequence`（inverted boundary）和 `post_compact_delta_end_sequence != current_input_event_sequence`（delta end mismatch）。这两条路径没有直接单元测试。当前间接覆盖依赖 `build_pre_dispatch_compact_material_view` 的 happy path，但 `__post_init__` 作为独立 contract 应有直接 negative case。

**Recommendation**: 在 `test_compact_material.py` 中补充两条直接测试：构造 inverted boundary 和 mismatched delta end 时 `CompactMaterialSourceBoundary` 抛出 `ValueError`。

**Blocking**: 否。数据构造路径（builder 内部）已经保证这些 invariant 成立，直接构造边界对象的场景较少。

### F2 [low-maintainability] PreDispatchCompactMaterialView boundary mismatch check 缺少直接测试

**Severity**: low

**Location**: `dayu/host/compact_material.py:435-451` (`PreDispatchCompactMaterialView.__post_init__`)

**Description**: `PreDispatchCompactMaterialView.__post_init__` 校验便捷诊断字段与 `source_boundary` 一致性（`latest_compacted_event_id`、`latest_compacted_event_sequence`、`post_compact_delta_start_sequence`、`post_compact_delta_end_sequence`）。这些 mismatch 分支没有直接测试。当前 builder 始终从同一 boundary 对象赋值，所以运行时不会触发；但作为独立 dataclass contract 应有 negative coverage。

**Recommendation**: 补充直接测试覆盖 boundary mismatch 时 `ValueError` 路径。

**Blocking**: 否。builder 路径保证一致性，直接构造场景为内部 contract 防御。

### F3 [low-correctness] `_accepted_tool_evidence_delta_blocks` fallback `tool_call_event_ref` 语义模糊

**Severity**: low

**Location**: `dayu/host/compact_material.py:2109-2110`

**Description**: 当 `envelope.tool_query.tool_call_requested_event_ref` 为 `None` 时，代码 fallback 到 `row.event_id`（即 `TOOL_RESULT_ACCEPTED` event id）。这会导致 `tool_call_event_ref` 指向 result event 而非 request event，与字段名语义不完全一致。当前测试 fixture 中 `tool_call_requested_event_ref` 为 `None`（见 `_accepted_evidence_envelope_for_event`），因此该 fallback 路径确实被测试覆盖，但产出的 `tool_call_event_ref` 值语义上是 result event id。

**Recommendation**: 当前行为不影响 correctness（`_readable_query_text_from_envelope` 在 `requested_event_ref is None` 时返回 limited signal），但可在 docstring 中明确说明 fallback 语义：当 durable request atom 缺失时，`tool_call_event_ref` 退化为 producer event ref，仅用于 prompt-local provenance 追溯，不表示 request event 存在。

**Blocking**: 否。已有 limited signal 路径保护。

### F4 [low-maintainability] `_post_compact_delta_rows` SQL event type 白名单为硬编码

**Severity**: low

**Location**: `dayu/host/compact_material.py:1934-1939`

**Description**: delta rows 查询只包含 `USER_INPUT_ACCEPTED`、`RUN_SUCCEEDED`、`TOOL_RESULT_ACCEPTED` 三种 event type。这是当前 plan 要求的正确集合，但若未来新增 canonical fact type 需要进入 delta material，此处必须同步修改。当前已有模块常量 `_EVENT_TYPE_*`，白名单引用这些常量，可维护性可接受。

**Recommendation**: 无需修改。当前 event type 集合与 plan 定义一致；未来扩展时由对应 work unit 负责同步。

**Blocking**: 否。

### F5 [info] `tests/README.md` 更新符合触发范围

**Location**: `tests/README.md`

**Description**: README 补充了 `test_compact_material.py` 覆盖 EventLog-backed pre-dispatch compact material source 和 explicit previous compacted view pack path 的说明。更新内容只描述当前已实现的测试覆盖范围，未写未来计划，符合 README 更新约束。

**Verdict**: 合格。

### F6 [info] `dayu/host/README.md` 更新符合触发范围

**Location**: `dayu/host/README.md`

**Description**: 更新将 "RunInputBuilder 和 Context Governance 可以读取 memory snapshot 作为输入材料" 改为 "ordinary RunInput 可以读取 memory snapshot 作为已物化 read model；pre-dispatch compact material 则由 EventLog / payload / artifact truth 构造"。这是对当前已实现的 stable developer mechanism 的准确描述，未写未来计划，符合 README Agent 更新约束。

**Verdict**: 合格。

### F7 [info] `docs/host/issues-implementation-control.md` gate bookkeeping 合理

**Location**: `docs/host/issues-implementation-control.md`

**Description**: 控制文档更新了当前状态表（gate: code review, implementation status: Slice 1 completed, next entry point: code review gate）并新增了 Slice 1 implementation gate 条目，记录了 implementation artifact、changed files、validation results 和 controller decision。符合总控文档推进规则。

**Verdict**: 合格。

## 核心设计点验证

### 1. `build_pre_dispatch_compact_material_view` 只读 EventLog / payload / artifact truth

**结论**: ✅ 通过。

Builder 函数签名只接收 `transaction`、`event_log_store`、`run`、`current_display_text` 和 caps。内部调用链：
- `_validated_current_input_event` — 读 EventLog row + payload
- `_latest_compacted_event_before_current_input` — SQL 查询 `CONTEXT_COMPACTED` canonical fact
- `_accepted_evidence_mapping_refs_from_compacted_event` — 读 compact payload
- `_previous_compacted_view_from_compacted_event` — 读 compact payload accepted candidate + digest 校验
- `_post_compact_delta_rows` — SQL 查询 delta canonical facts
- `_pre_dispatch_delta_material_blocks` — 读 EventLog payload / evidence envelope

全程不读 `ConversationMemorySnapshotVNext`，不调用 memory projection 相关函数。

### 2. `previous_compacted_view` 从 accepted candidate 解析

**结论**: ✅ 通过。

`_previous_compacted_view_from_compacted_event` 读取 `CONTEXT_COMPACTED` payload 的 `accepted_candidate` 字段，校验 `accepted_candidate_digest`（`sha256_digest_json(candidate) != expected_digest` 时抛 `HostDurableError`），然后按 candidate 内容映射为 session summary / facts / answer anchors / forward intents / reference continuity 五类 `CompactMaterialBlock`。

### 3. `post_compact_delta_material` boundary 正确

**结论**: ✅ 通过。

`_post_compact_delta_start_sequence` 返回 `latest_compacted_event.event_sequence + 1`（有 latest compact 时）或 session 内第一条 relevant canonical fact（无 latest compact 时），或 `current_input_sequence`（无 relevant fact 时）。`_post_compact_delta_rows` 查询 `event_sequence >= start_sequence AND event_sequence < end_sequence`，end_sequence 为 current input sequence。测试 `test_pre_dispatch_second_compact_rolls_from_latest_accepted_candidate` 验证 delta 不包含 compact 前旧 raw history。

### 4. 首次 compact 起点 cursor 语义

**结论**: ✅ 通过。

`_post_compact_delta_start_sequence` 在无 latest compact 时查询 session 内第一条 `USER_INPUT_ACCEPTED` / `RUN_SUCCEEDED` / `TOOL_RESULT_ACCEPTED` canonical fact。测试 `test_pre_dispatch_first_compact_empty_delta_starts_at_current_input` 验证无 relevant fact 时 delta 为空且 start == end == current input sequence。

### 5. `build_compact_material_pack` `previous_compacted_view` 参数类型安全

**结论**: ✅ 通过。

参数类型为 `tuple[CompactMaterialBlock, ...] | None = None`。当 `previous_compacted_view is not None` 时调用 `_require_compact_material_block_tuple` 校验（包括空 tuple 路径），然后直接使用；当 `None` 时走 `_previous_blocks_from_snapshot` 旧路径。测试 `test_build_compact_material_pack_uses_explicit_previous_view_without_snapshot` 覆盖两条路径。

### 6. 无 God function / 过度重复解析 / fragile JSON / 裸内部 ref 投影

**结论**: ✅ 通过。

- 函数分解合理：builder 拆为 `_validated_current_input_event`、`_latest_compacted_event_before_current_input`、`_accepted_evidence_mapping_refs_from_compacted_event`、`_previous_compacted_view_from_compacted_event`、`_post_compact_delta_start_sequence`、`_post_compact_delta_rows`、`_pre_dispatch_delta_material_blocks`、`_pre_dispatch_budget_fragments` 等独立 helper。
- JSON 解析使用 typed helper（`_required_json_text`、`_required_json_mapping`、`_required_json_text_tuple`），异常统一转 `HostDurableError`。
- LLM-facing 文本不包含 event_id、payload_ref、digest、cursor；`_readable_query_text_from_envelope` 使用 semantic query 或 bounded arguments JSON；`_limited_signal_query_text` 使用中文状态描述。
- evidence source text 使用 `ref_kind:ref_id` 格式，属于 diagnostic-style 参考，不作为业务事实引用。

### 7. 中文 docstring / 严格类型 / 无 Any/object

**结论**: ✅ 通过。

所有新增 / 修改函数均有完整中文 docstring（参数、返回值、异常）。类型签名使用严格类型（`tuple[CompactMaterialBlock, ...]`、`str | None`、`int` 等），无 `Any`、`object` 或无类型参数。

### 8. 测试覆盖 plan 要求

**结论**: ✅ 通过。

| Plan 测试要求 | 测试函数 | 覆盖 |
|---|---|---|
| 首次 compact：无 previous compact，delta 包含 user/assistant/evidence，current input 只在 anchor | `test_pre_dispatch_first_compact_uses_eventlog_delta_before_current_input` | ✅ |
| 首次 compact 空 delta | `test_pre_dispatch_first_compact_empty_delta_starts_at_current_input` | ✅ |
| 第二次 compact：previous view 来自 accepted candidate，delta 只含 compact 后新 facts | `test_pre_dispatch_second_compact_rolls_from_latest_accepted_candidate` | ✅ |
| memory snapshot lag / missing 不影响 builder | `test_pre_dispatch_builder_ignores_memory_snapshot_lag_or_missing` | ✅ |
| represented evidence refs 只来自 latest compact | `test_pre_dispatch_represented_evidence_refs_only_from_latest_compact` | ✅ |
| payload 损坏 fail closed | `test_pre_dispatch_payload_damage_fails_closed_without_recovery_request` | ✅ |
| explicit previous view path 与 snapshot path | `test_build_compact_material_pack_uses_explicit_previous_view_without_snapshot` | ✅ |

## Residual Risks

- **R1 [deferred-with-owner]**: Slice 1 只落地 builder 与 pack 显式 previous-view path，尚未改 dispatch proactive call path。后续 Slice 2 需要把 proactive budget estimate、segment selection 与 compaction request 切到该 material view。Owner: WU-PROJ-01 Slice 2。
- **R2 [deferred-with-owner]**: `CompactMaterialSourceBoundary` 和 `PreDispatchCompactMaterialView` 的 negative validation 测试缺失（F1 / F2）。Owner: 可在 Slice 2 或后续 cleanup 中补充。
