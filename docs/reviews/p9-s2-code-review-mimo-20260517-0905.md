# Code Review

## Scope

- Mode: current changes
- Branch: feat/host-p9-conversation-memory
- Base: main
- Output file: docs/reviews/p9-s2-code-review-mimo-20260517-0905.md
- Included scope:
  - `dayu/host/memory.py`
  - `dayu/host/durable/memory.py`
  - `tests/host/test_memory_projection.py`
- Excluded scope: schema.py, run_input.py, README, docs (per slice boundary)
- Parallel review coverage: 无

## Findings

### 1-未修复-中-ASSISTANT_CONCLUSION items bypass history pool budget

- **入口/函数**: `_limit_continuity_items`
- **文件(行号)**: `dayu/host/memory.py:1316-1321`
- **输入场景**: 多轮 `RUN_SUCCEEDED` 事件产生多个 `ASSISTANT_CONCLUSION` continuity items
- **实际分支**: `ASSISTANT_CONCLUSION` 既非 `_is_raw_turn` 也非 `_is_episode`，因此落入 `always_items`，绕过 `history_pool_size_units` 预算
- **预期行为**: 设计要求 history pool 有 size budget 约束；`always_items` 当前语义是"不参与 history pool 竞争"，但 `ASSISTANT_CONCLUSION` 本质是 continuity item 而非 stable layer item
- **实际行为**: `budget_used` 从 `_size_units_sum(always_items)` 起算，`always_items` 自身永不被降级。若未来新增 continuity item kind 也进入 `always_items`，会静默突破 pool 预算
- **直接证据**: `memory.py:1316-1318` — `always_items = tuple(item for item in items if not _is_raw_turn(item) and not _is_episode(item))`；`ASSISTANT_CONCLUSION` 不匹配 `_is_raw_turn`（只检查 `RAW_USER_TURN` / `RAW_ASSISTANT_TURN`）也不匹配 `_is_episode`
- **影响**: 当前安全——`ASSISTANT_CONCLUSION` 单条受 `max_raw_turn_size_units` 限制，且每 Run 只产生一个。但结构上 `always_items` 是一个不受 budget 约束的隐式通道，后续扩展容易引入预算泄漏
- **建议改法和验证点**: 在 `_limit_continuity_items` 注释中显式标注 `always_items` 的设计意图（"这些 item 由 stable layer budget 而非 history pool budget 约束"），或为 `ASSISTANT_CONCLUSION` 增加独立的 count/size cap。当前可不改代码，但应在 review 中记录此设计决策
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### 2-未修复-低-_explicit_source_refs 传播无效 ref_kind ValueError

- **入口/函数**: `_explicit_source_refs`
- **文件(行号)**: `dayu/host/memory.py:1535`
- **输入场景**: `TOOL_RESULT_ACCEPTED` payload 的 `source_refs` 中携带非 `HostNeutralRefKind` 枚举值的 `ref_kind_text`
- **实际分支**: `HostNeutralRefKind(ref_kind_text)` 直接构造枚举，无效值抛 `ValueError`
- **预期行为**: 对 malformed payload 中的单条 ref 应容错跳过，不破坏整个 projection event
- **实际行为**: `ValueError` 向上传播，导致 `_tool_source_refs` → `_verified_fact_from_projection_event` → `project_conversation_memory_event` 整个投影失败
- **直接证据**: `memory.py:1535` — `refs.append(OpaqueMemoryRef(ref_kind=HostNeutralRefKind(ref_kind_text), ...))` 无 try/except
- **影响**: 单条 malformed source_ref 导致整个 TOOL_RESULT_ACCEPTED 事件投影失败。projection runner 会将此记录为 projection failure，该工具事实丢失
- **建议改法和验证点**: 在 `HostNeutralRefKind(ref_kind_text)` 外层加 try/except ValueError，无效值时 `continue` 跳过该 ref 并记录 diagnostic。验证：构造 payload 含无效 ref_kind，确认 fact 仍生成且 diagnostic 记录 malformed ref
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 3-未修复-低-缺少 _limit_verified_facts / _limit_working_assumptions / _limit_pinned_state 预算路径测试

- **入口/函数**: `_limit_verified_facts`, `_limit_working_assumptions`, `_limit_pinned_state`
- **文件(行号)**: `dayu/host/memory.py:1242-1293`, `tests/host/test_memory_projection.py`
- **输入场景**: 超过 `max_verified_facts` / `max_working_assumptions` / `max_pinned_items` 的 events 序列
- **实际分支**: 未被测试覆盖
- **预期行为**: 超过 limit 时保留最新 N 条，丢弃最旧条目，并生成 `BUDGET_LIMIT_REACHED` diagnostic
- **实际行为**: 函数逻辑正确（保留 `[-max:]` 切片 + diagnostic），但无测试证明
- **直接证据**: `test_memory_projection.py` 中 `_low_history_policy` 只覆盖 history pool budget；无 `_low_verified_facts_policy` 或等价 fixture
- **影响**: 预算降级路径无回归保护；后续修改可能引入 off-by-one 或 diagnostic 缺失而不被发现
- **建议改法和验证点**: 增加 3 个测试：(1) 超过 `max_verified_facts` 时保留最新条目 + diagnostic；(2) 超过 `max_working_assumptions` 时保留最新条目 + diagnostic；(3) 超过 `max_pinned_items` 时 user_constraints 截断
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Open Questions

无。

## Verification

### 测试

```
$ source .venv/bin/activate && pytest tests/host/test_memory_projection.py tests/host/test_durable_schema.py -v
30 passed in 0.25s
```

### 弱类型守卫

```
$ source .venv/bin/activate && pytest tests/host/test_weak_typing_guard.py -v
1 passed in 0.3s
```

### Pyright

```
$ source .venv/bin/activate && pyright dayu/host/memory.py dayu/host/durable/memory.py tests/host/test_memory_projection.py
0 errors, 0 warnings, 0 informations
```

### Git whitespace

```
$ git diff --check HEAD -- dayu/host/memory.py dayu/host/durable/memory.py tests/host/test_memory_projection.py
(clean)
```

### Review lens 逐项验证

| Lens | 结论 |
|------|------|
| P9 是财报分析工作台状态投影，不是聊天记录压缩器 | 通过。snapshot 结构包含 pinned_state / verified_facts / working_assumptions / continuity，无聊天压缩语义 |
| verified_facts 只来自 TOOL_RESULT_ACCEPTED | 通过。`_verified_fact_from_projection_event` 只在 `_EVENT_TYPE_TOOL_RESULT_ACCEPTED` 分支调用；VerifiedFactView.__post_init__ 强制 `claim_status == TOOL_VERIFIED` 且 `provenance.producer_kind == TOOL` |
| final_answer / RUN_SUCCEEDED 只进入 continuity 作为 ASSUMPTION | 通过。`_assistant_conclusion_from_projection_event` 产生 `ConversationContinuityKind.ASSISTANT_CONCLUSION`，`claim_status=ASSUMPTION`，`producer_kind=ASSISTANT` |
| USER_INPUT_ACCEPTED 不进入 verified_facts | 通过。USER_INPUT 分支只更新 pinned_state 和 continuity |
| 缺失工具 fact summary 使用中立 fallback + diagnostic | 通过。`_neutral_tool_fact_fallback` 生成 `tool_name=...; outcome_digest=...; payload_ref=...` 格式；`MISSING_FACT_SUMMARY_FALLBACK` diagnostic 被记录 |
| 无 Host 业务语义 / dayu.fins import | 通过。`test_memory_contracts_do_not_expose_business_specific_fields` 断言 contracts 不含 business 专有字段 |
| Reserved CANDIDATE / CONFLICTED / STALE / SUPERSEDED 不被合成 | 通过。`test_p9_contracts_do_not_synthesize_conflict_stale_or_superseded` 和 `test_projection_ignores_reserved_claim_status_from_payload` 覆盖 |
| Episode summary 只做导航，不替代 evidence anchor | 通过。`test_episode_summary_does_not_replace_evidence_anchor` 覆盖 |
| History pool: recent floor 保留，summaries 先于 older raw 丢弃 | 通过。`test_history_pool_preserves_recent_floor_and_drops_summaries_first` 覆盖 |
| Projection failure 不改 Run state / EventLog | 通过。`ConversationMemoryProjectionConsumer.apply_event` 只写 memory-owned tables |
| Slice 边界：无 RunInputBuilder provider / repair wiring / schema / docs | 通过。diff 只涉及 memory.py / durable/memory.py / test |
| 严格类型 / 中文 docstring / 无 Any / 无 object | 通过。pyright 0 errors；所有函数有中文 docstring |
| 无兼容性 wrapper | 通过 |

### Diff 摘要

- `dayu/host/memory.py` (+1083 lines): 新增 `MemoryProjectionEvent` dataclass、`project_conversation_memory_event` 投影函数、stable layer builder（verified fact / working assumption / continuity item extraction）、history pool budget 限制、deterministic snapshot digest、policy digest、JSON 序列化/反序列化
- `dayu/host/durable/memory.py` (+138 lines): 新增 `ConversationMemoryProjectionConsumer` 实现 `ProjectionConsumer`、`_memory_projection_event_from_view` adapter
- `tests/host/test_memory_projection.py` (+326 lines): 新增 11 个测试覆盖 anti-hallucination matrix、history pool budget、snapshot rebuild determinism、ProjectionRunner integration

## Verdict

**通过，0 blocking findings。**

3 个 findings 均为非阻塞性：
- Finding 1（中）: `always_items` 绕过 history pool budget 是当前设计决策，结构上有维护风险但当前安全。建议记录设计意图。
- Finding 2（低）: malformed `source_refs` 的 `ref_kind` 导致投影失败。建议增加容错。
- Finding 3（低）: stable layer 预算降级路径缺少测试覆盖。建议补充。

剩余 blocking count: **0**

Implementation 满足 Slice 2 stop condition：ProjectionRunner 可从 committed EventLog 构建 session snapshot；projection failure 只写 projection-local failure row；未接 RunInputBuilder provider。
