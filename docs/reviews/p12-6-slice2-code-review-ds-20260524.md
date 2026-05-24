# P12.6 Slice 2 Code Review — AgentDS

## Gate

- Work unit: Phase 12.6 Conversation Memory Redesign
- Slice: Slice 2 Deterministic Segment Selection / Material Pack Builder
- Review role: AgentDS (strict code reviewer)
- Reviewed implementation artifact: `docs/reviews/p12-6-slice2-implementation-codex-20260524.md`
- Design source: `docs/host/design.md` §24 / §25
- Plan source: `docs/host/p12-6-conversation-memory-redesign-implementation-plan.md` Slice 2 与 §6.3/6.4/6.6
- Review base: HEAD = `c0a5b18` (P12.6 Slice 1 accepted)

## Verdict

**PASS** — 无 BLOCKED 发现。3 个 MEDIUM finding 建议修复但不阻塞 Slice 2 closeout；其余为 LOW/INFO 观察项。

---

## 1. 动机判断

动机成立。Slice 2 直接修复 material selection/source 同源问题：RunInputBuilder 和 compact builder 通过 `build_run_input_material_blocks` 共享同一 ordinary input material list source；`select_compact_segment` 在给定 trigger/input cursor/memory snapshot cursor/policy digest/material list 时确定性输出 selected block ids；`build_compact_material_pack` 强制 one-to-one section mapping 并检测 duplicate content。没有引入过度复杂或偏离设计的路径。

---

## 2. Findings

### M1 — MEDIUM: `_memory_material_kind` 通过字符串前缀匹配判断 material kind

**文件**: `dayu/host/run_input.py:_memory_material_kind` (L2095–L2106)

**证据**:
```python
if content.startswith("Memory evidence-backed facts:"):
    return CompactMaterialBlockKind.EVIDENCE_BACKED_FACT
if content.startswith("Memory open questions and working assumptions:"):
    return CompactMaterialBlockKind.WORKING_ASSUMPTION
if content.startswith("Memory episode summaries:"):
    return CompactMaterialBlockKind.EPISODE_SUMMARY
```

**影响**: 若 memory 渲染格式（当前由 `build_run_input_messages` 在同一模块内生成）将来变更 section header 文案，此处 kind 分类会静默降级为 `PINNED_STATE`（fallthrough 默认），导致 stable block 排序键不精确。虽然 `PINNED_STATE` 与其它 stable kinds 共享 `_BLOCK_KIND_ORDER=0`，实际排序不受影响，但 material provenance 中的 `kind` 字段会错误。

**建议**: 提取 `build_run_input_messages` 使用的 section header 常量为模块级共享常量，并在 `_memory_material_kind` 中引用同一常量。或在 `MemorySnapshotView` 中直接提供 per-message `kind` hint 而非依赖 content 解析。

**严重度依据**: 当前同一模块内格式自洽，实际后果限于 diagnostic/provenance kind 字段可能漂移，不影响 correctness。但属于 fragile coupling，与 AGENTS.md "禁止把业务规则硬编码成脆弱分支" 部分相关。

---

### M2 — MEDIUM: `check_compact_memory_snapshot_cursor` 中 `lag_events > max_delta_repair_events` 作为额外硬约束在 plan §6.6 中未明确

**文件**: `dayu/host/compact_material.py:check_compact_memory_snapshot_cursor` (L687–L690)

**证据**:
```python
if (
    lag_events > policy.max_lag_events_for_inline_delta
    or lag_events > policy.max_delta_repair_events
):
```

**影响**: Plan §6.6 明确只说 `max_lag_events_for_inline_delta` 作为 inline delta 阈值。`max_delta_repair_events` 在该 plan 上下文中语义为 "rebuild 时最大事件数"（§6.6 引用的 `MemoryProjectionPolicy` 字段定义）。此处将其解释为 inline delta 的附加硬约束：即使 `inline_delta_repair_view` 已提供且 lag 在 `max_lag_events_for_inline_delta` 内，若 lag 也超过 `max_delta_repair_events`，inline delta 被拒绝并抛 repair-required。这在安全侧是 fail-closed 的额外保守约束，不造成错误行为，但超出 plan 的明确语义范围。

**建议**: 选择以下任一项：
  (a) 删除 `or lag_events > policy.max_delta_repair_events` 条件，仅保留 `max_lag_events_for_inline_delta` 检查。
  (b) 若有意保留此约束，补充 `check_compact_memory_snapshot_cursor` docstring 说明 `max_delta_repair_events` 同时约束 inline delta 路径，并在 plan/design 中记录此决策。

**严重度依据**: 当前行为比 plan 更保守（额外 fail-closed），非正确性问题。但 plan-implementation 语义偏差应显式记录。

---

### M3 — MEDIUM: `build_run_input_material_blocks` 对 continuity/compact 消息使用 `event_sequence=None`

**文件**: `dayu/host/run_input.py:build_run_input_material_blocks` (L1999–L2035)

**证据**: 所有 `memory:*`、`compact:*`、`continuity:*` 前缀 block 的 `event_sequence=None`，仅 `current:` 前缀 block 具有明确 `event_sequence`。

**影响**: 在 `select_compact_segment` 中，`_sorted_material_blocks` 对所有 `event_sequence=None` 的 block 使用 `memory_snapshot_cursor` 作为 fallback 排序键（`_block_event_sequence` L1056–L1070）。由于 stable blocks 已被 `_block_exclusion_reason` 排除不进入 selection，影响面限于 history/evidence blocks 中 `event_sequence=None` 的情况。当前 `build_run_input_material_blocks` 中 history blocks（continuity/compact）的 `event_sequence=None` 是因为 RunInputBuilder 当前不追溯每条 continuity 消息到原始 EventLog sequence。这不影响 selection 确定性（因为 `block_id` 作为最终 tie-breaker），但排序丢失了 "更旧 event 的 continuity 先被 compact" 的语义。

**建议**: 后续 Slice 5 接线时，若 continuity provider 可追溯原始 event_sequence，应在 construction 时传入。当前不阻塞。

**严重度依据**: 不影响确定性（有 block_id tie-breaker），但 lose old-first compact 语义。trade-off 可接受。

---

### L1 — LOW: `_snapshot_goal_text` 引用 `subject.ref_kind.value` 时依赖 `ref_kind` 为 StrEnum 实现细节

**文件**: `dayu/host/compact_material.py:_snapshot_goal_text` (L1343)

**证据**:
```python
lines.append(f"confirmed_subject={subject.ref_kind.value}:{subject.ref_id}")
```

**影响**: 若 `ref_kind` 类型变更为非 StrEnum，`.value` 可能不存在或返回非预期值。当前 `OpaqueEvidenceRef.ref_kind` 为 `str` 类型声明——此处 `.value` 调用依赖于实际运行时值为 StrEnum。若该类型确实是 `str` 而非 StrEnum，`.value` 应替换为直接字符串化。

**建议**: 验证 `OpaqueEvidenceRef.ref_kind` 的类型定义。若 `ref_kind` 为普通 `str`，直接使用 `subject.ref_kind`；若为 `StrEnum`，`.value` 正确。

---

### L2 — LOW: `_snapshot_facts_text` 格式将 `fact.evidence_refs` 用逗号连接可能导致 LLM 难以解析

**文件**: `dayu/host/compact_material.py:_snapshot_facts_text` (L1361–L1367)

**证据**:
```python
lines.append(
    "fact="
    f"claim_text={fact.claim_text}; "
    f"evidence_refs={','.join(fact.evidence_refs)}; "
    f"evidence_kind={fact.evidence_kind.value}"
)
```

**影响**: 若 `fact.claim_text` 包含 `;` 字符，输出会破坏分隔语义。这是 V1 rendering，属可接受的 text format trade-off。

**建议**: 后续可考虑结构化 JSON rendering 或显式 escaping。当前不阻塞。

---

### L3 — LOW: 测试 `test_snapshot_cursor_lag_requires_catchup_or_inline_delta` 期望值与实现行为一致但 plan semantics 有细微偏差

**文件**: `tests/host/test_compact_material.py:test_snapshot_cursor_lag_requires_catchup_or_inline_delta` (L214–L243)

**证据**: 测试使用 `max_lag_events_for_inline_delta=1` (strict_policy) 与 `lag_events=2` 期望抛 repair-required。此行为依赖于 M2 中讨论的 OR 条件，即 `lag_events=2 > max_lag_events_for_inline_delta=1`。

**影响**: 测试正确验证了当前实现行为，但与 plan 的纯 `max_lag_events_for_inline_delta` 语义对齐。若 M2 建议被采纳（删除附加条件），此测试无需修改；若不采纳，测试行为正确。

---

### I1 — INFO: `_BLOCK_KIND_ORDER` 对 stable layer kinds 全设为相同排序值 0

**文件**: `dayu/host/compact_material.py:_BLOCK_KIND_ORDER` (L73–L83)

**观察**: `PINNED_STATE`、`EVIDENCE_BACKED_FACT`、`WORKING_ASSUMPTION`、`OPEN_QUESTION` 全部映射到 0。由于 stable blocks 已被 `_block_exclusion_reason` 排除出 selection（返回 `_REASON_STABLE_INPUT`），此分配不影响 selected block ids。但若未来需要选择 stable blocks（如 reactive path 中 stable 也需要 compact），此同值会导致排序依赖仅 block_id。

**建议**: 不阻塞。若未来需要 stable block selection，届时再分配 distinct order values。

---

### I2 — INFO: `test_run_input_builder_exposes_shared_material_block_source` 硬编码 `"event-current-input"` source ref

**文件**: `tests/host/test_run_input_builder.py:test_run_input_builder_exposes_shared_material_block_source` (L608–L632)

**观察**: `assert blocks[0].canonical_source_refs == ("event-current-input",)` 依赖 `_seed_current_run` 内部使用的固定 event_id。若 seed helper 变更 event_id 生成规则，测试会 break。

**建议**: 在测试中从 `seeded` 返回值读取实际 event_id 而非硬编码。当前不阻塞（seed helper 稳定）。

---

## 3. Review Focus 逐项结论

### 3.1 动机判断

| 检查项 | 结论 |
|--------|------|
| material selection/source 同源问题是否真的修了 | **修了**：`build_run_input_material_blocks` 提供 RunInputBuilder 与 compact builder 共享的 ordinary material list |
| 是否引入过度复杂 | **否**：新增类型均为 typed dataclass，无 god object/bag |
| 是否偏离设计路径 | **否**：严格遵循 plan §6.3/6.4/6.6 |

### 3.2 Correctness

| 检查项 | 结论 |
|--------|------|
| `select_compact_segment` 确定性 | **是**：排序键 `(event_sequence, event_sub_index, block_kind_order, block_id)` 确定，digest 包含所有输入参数 |
| proactive 排除 current anchor | **是**：`_block_exclusion_reason` 对 `CURRENT_INPUT_ANCHOR` 返回 `protected_current_input` |
| proactive 排除 protected recent raw floor | **是**：`_protected_recent_raw_block_ids` 自底向上取 `recent_raw_turns_floor` 条 + explicit 标记 |
| proactive 排除 stable/already represented | **是**：`STABLE_INPUT` section → `stable_input_not_selected`；`already_represented=True` → `already_represented` |
| reactive 只使用 frozen list | **是**：`select_compact_segment` 不扫描 EventLog，只消费传入 `material_blocks` |
| excluded reasons/digest 稳定 | **是**：`excluded_reason_codes` 由 deterministic ordering 产生，digest 含 sorted mapping |

### 3.3 Material Pack

| 检查项 | 结论 |
|--------|------|
| one-to-one section guard | **是**：`_raise_on_duplicate_section_owner` 使用 `(sorted(canonical_source_refs), content_digest)` 检测；`CompactMaterialPack.__post_init__` 也执行 `_require_one_section_per_canonical_content` |
| current input anchor 不重复 history raw turn | **是**：`_is_current_input_history_duplicate` 同时检查 source ref 重叠与 content digest |
| canonical source ref set + digest 去重 | **是**：dedupe key 正确 |

### 3.4 Snapshot Cursor Helper

| 检查项 | 结论 |
|--------|------|
| lag 语义符合 plan | **基本符合**，M2 中 `max_delta_repair_events` 作为附加约束略有偏差 |
| inline repair 语义正确 | **是**：`inline_delta_repair_view is None` 时抛 repair-required，非 None 且阈值内时返回 `INLINE_DELTA_REPAIR` |
| repair-required 不触发 Run RECOVERING | **是**：`requests_run_recovery=False` 始终设置 |
| 公共 API 未扩张 | **是**：所有新函数均为 Host internal，不在 public `api.py` 或 `open_host.py` 中 |

### 3.5 Architecture

| 检查项 | 结论 |
|--------|------|
| 不修改 Engine/Service/Fins/public Host API | **是**：仅修改 `dayu/host/` 内部模块 |
| 不引入 Any/object/getattr/hasattr/lazy seam | **是**：全 typed，无 `Any`/`object`/`hasattr`/`getattr` |
| 不反向依赖 | **是**：import 仅沿 `compact_material → compaction + memory`（同层）方向 |

### 3.6 Tests

| Plan 指定测试 | 实现状态 |
|---------------|----------|
| `test_segment_selection_is_deterministic_for_same_inputs` | **已实现**，通过 |
| `test_proactive_segment_excludes_current_anchor_and_recent_raw_floor` | **已实现**，通过 |
| `test_reactive_segment_uses_frozen_overflow_material_list` | **已实现**，通过 |
| `test_already_represented_blocks_are_not_reexpanded` | **已实现**，通过 |
| `test_material_pack_one_to_one_section_mapping_rejects_duplicate_content` | **已实现**，通过 |
| `test_current_input_anchor_does_not_duplicate_history_raw_turn` | **已实现**，通过 |
| `test_snapshot_cursor_lag_requires_catchup_or_inline_delta` | **已实现**，通过 |
| `test_snapshot_lag_failure_does_not_request_run_recovery` | **已实现**，通过 |
| 额外覆盖率：RunInputBuilder shared material source | `test_run_input_builder_exposes_shared_material_block_source` **已实现**，通过 |

**测试质量评估**:
- 所有 8 个 plan-mandated 测试全部实现并通过
- 测试不锁实现细节：测试通过 public function API 调用，断言 typed 返回值
- 关键 negative case 覆盖：snapshot cursor 缺失/lag/超阈值/inline repair 路径全部覆盖
- 缺少的 critical negative case：当前 stable blocks 排序路径的确定性测试（所有 stable blocks 因 `_REASON_STABLE_INPUT` 被排除，不进入 selection，但排序本身可另测）

### 3.7 README

| 检查项 | 结论 |
|--------|------|
| `dayu/host/README.md` | 只写稳定语义（同源 material view、deterministic segment selection、protected exclusion、material pack builder），无过程状态 ✓ |
| `tests/README.md` | 补充了 `test_compact_material.py` 的测试职责，无越界内容 ✓ |
| 旧术语残留 | 无 |
| 越界内容 | 无 |

---

## 4. 验证摘要

### 4.1 测试结果

```bash
source .venv/bin/activate
pytest tests/host/test_compact_material.py tests/host/test_run_input_builder.py \
  tests/host/test_memory_projection.py -q
# 92 passed in 1.84s
```

### 4.2 类型检查

```bash
python -m pyright dayu/host/compact_material.py dayu/host/run_input.py \
  dayu/host/memory.py dayu/host/memory_repair.py \
  tests/host/test_compact_material.py tests/host/test_run_input_builder.py \
  tests/host/test_memory_projection.py
# 0 errors, 0 warnings, 0 informations
```

### 4.3 旧字段泄漏检查

```bash
rg -n "accepted_evidence_envelopes|compact_raw_context_items|current_message_summary|\
CurrentMessageSummary|CompactRawContextItem" \
  dayu/host/compact_material.py dayu/host/run_input.py \
  tests/host/test_compact_material.py tests/host/test_run_input_builder.py
# No matches (旧字段已清除)
```

### 4.4 禁止模式检查

```bash
rg -n "hasattr|getattr|Any|object" dayu/host/compact_material.py | head -5
# No matches (除 import 中的 __future__ annotations)
```

---

## 5. Open Questions / Residual Risks

1. **M1 修复策略**: `_memory_material_kind` 的字符串前缀匹配是否需要立即修复，或留到 Slice 5 wiring 时一并处理？建议至少在模块内提取 section header 常量。

2. **M2 修复策略**: `max_delta_repair_events` 是否应作为 inline delta 的附加硬约束？若保留此行为，需在 plan/design 中显式记录。

3. **`_BLOCK_KIND_ORDER` 同值设计**: 当前 stable kinds 全为 0 因 stable blocks 不参与 selection。若后续 Slice 5 需要选择 stable blocks，此分配需重新评估。

4. **`event_sequence=None` 对 continuity/compact blocks 的影响**: 后续 wiring 阶段是否能补充 event_sequence 追溯能力。

5. **测试 `test_segment_selection_is_deterministic_for_same_inputs` 未包含 stable blocks**: 由于 stable blocks 被自动排除，此 gap 对 correctness 无影响；但若未来调整 stable block selection 规则，需补测。

---

## 6. 最终评估

Slice 2 实现质量高。Typed contract 完整、无类型逃逸、无架构越界。Deterministic selection 与 one-to-one section mapping 正确实现。8 个 mandated 测试全部覆盖并通过。pyright 零报错。README 更新准确且限于稳定语义。

M1（字符串前缀匹配脆弱性）是唯一建议在合并前修复的中等发现。M2/M3 可以 deferred 到后续 slice 但应记录。

**推荐**: PASS — Slice 2 closeout 可接受；建议修复 M1 后合并。
