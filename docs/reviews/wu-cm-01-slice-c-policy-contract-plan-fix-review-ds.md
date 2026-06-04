# WU-CM-01 Slice C Policy Contract Plan Fix Review

## Gate

- Review gate: WU-CM-01 Slice C policy contract plan fix review
- Branch: `phaseflow/wu-cm-01`
- Artifacts under review:
  - `docs/host/wu-cm-01-conversation-memory-plan.md` current diff
  - `docs/reviews/wu-cm-01-slice-c-policy-contract-plan-fix-codex.md`
- Design source: `docs/host/design.md` 第 3 章 `memory_projection_policy` (line 95) 与第 24.6 章 (line 2850)
- Controller adjudication: `docs/reviews/wu-cm-01-slice-c-implementation-retry-blocker-controller-adjudication.md`
- Project rules: `AGENTS.md`

## Verdict: PASS

Plan fix 充分解决了上一轮 Slice C implementation retry 的 policy contract conflict。以下 findings 均为非阻塞观察项；无 blocking finding。

---

## Findings

### F1. [PASS] 字段清单逐字完整验证

**验证方法**: 将 `docs/host/design.md` line 95 的 `memory_projection_policy` 字段清单与 plan diff line 391 的字段清单逐字比对。

design source (line 95):
> `context_window_size`、`selected_recent_window_item_cap`、`selected_recent_window_char_cap`、`selected_recent_window_turn_floor`、`fallback_selected_recent_window_item_cap`、`fallback_selected_recent_window_char_cap`、`evidence_fact_item_cap`、`evidence_fact_char_cap`、`evidence_fact_floor`、`session_summary_char_cap`、`answer_anchor_item_cap`、`answer_anchor_char_cap`、`forward_intent_item_cap`、`forward_intent_char_cap`、`reference_continuity_item_cap`、`reference_continuity_char_cap`、`reference_continuity_item_floor`、`max_lag_events_for_inline_delta`、`max_delta_repair_events`、`policy_ref`

plan diff line 391: 逐字一致，20 字段完整。

Codex artifact lines 44-65: 逐字一致，20 字段完整。

额外验证 design source line 2850 确认 `selected_recent_window_turn_floor`（不是 `selected_recent_window_floor_turns`）为正确字段名。Plan diff line 392 显式断言了字段名差异。

**结论**: design source 字段清单已在 plan fix 中逐字完整落地，无遗漏、无增删、无拼写差异。

### F2. [PASS] 禁止字段与禁止机制全覆盖

**验证方法**: 检查 plan diff 是否对 controller adjudication 列出的全部 forbidden field 和 forbidden mechanism 有显式禁止。

forbidden fields（来自 controller adjudication lines 23-25 与 Codex artifact lines 69-81）:

| 禁止字段 | plan diff 禁止位置 | 证据 |
|---|---|---|
| `selected_recent_window_floor_turns` | line 96, line 362, line 392 | "不得改用 `selected_recent_window_floor_turns`" |
| `max_memory_items_per_category` | line 96, line 392 | "不得退化为 `max_memory_items_per_category`" |
| `max_text_chars_per_memory_item` | line 96, line 392 | "不得退化为 `max_text_chars_per_memory_item`" |
| `projection_max_repair_attempts` | line 96 | explicit ban |
| `projection_max_rebuild_rows` | line 96 | explicit ban |
| `projection_max_catchup_rows` | line 96 | explicit ban |
| `max_evidence_backed_facts` | line 393 | "不接受旧 ... 字段" |
| `max_working_assumptions` | line 393 | "不接受旧 ... 字段" |
| `recent_raw_turns_floor` | line 362, line 393 | "从旧 `recent_raw_turns_floor` 改为..." |
| `history_pool_*` | line 390, line 393 | "不含 `history_pool_*`" |
| `stable_layer_*` | line 390, line 393 | "不含 `stable_layer_*`" |

forbidden mechanisms（来自 controller adjudication lines 38-40）:

| 禁止机制 | plan diff 禁止位置 |
|---|---|
| alias | line 96, line 362, line 392, line 394, line 409, line 437, line 439 |
| compatibility wrapper | line 96, line 394, line 439 |
| 默认补齐 (default fill) | line 96, line 394 |
| extra payload | line 96, line 395, line 433, line 443 |
| 双字段读取 (dual-field truth) | line 96 |
| 旧库兼容读取 | line 396, line 428, line 439 |
| raw dict patch | line 395 |
| snapshot bridge | line 422, line 439 |
| lazy import seam | line 443 |
| `hasattr` / `getattr` | line 443 |

**结论**: 所有禁止字段和禁止机制均有显式覆盖，无遗漏。

### F3. [PASS] `engine_ingest.py` 歧义已消除

**证据**: plan diff line 362 将旧文本:
> 从旧 `recent_raw_turns_floor` 改为 vNext `selected_recent_window_turn_floor` 或本 slice 明确的新字段；不得恢复旧字段 alias

改为:
> 从旧 `recent_raw_turns_floor` 改为 vNext `selected_recent_window_turn_floor`；不得恢复旧字段 alias，不得改用 `selected_recent_window_floor_turns`

**分析**: 删除"或本 slice 明确的新字段"消除了实现 agent 自行发明字段名的歧义空间；新增"不得改用 `selected_recent_window_floor_turns`"直接堵住了上一轮 retry prompt 的错误字段名。

**结论**: 歧义已消除，字段名收敛到唯一正确值。

### F4. [PASS] direct consumer closure list 完整性

**验证方法**: 将 Slice C allowed files (plan lines 351-384) 与 direct consumer closure list (plan diff lines 414-423) 对照，检查是否有 production consumer 未被 closure list 覆盖。

closure list 覆盖:

| Consumer 角色 | 文件 | 与 allowed files 一致? |
|---|---|---|
| Host public policy owner | `dayu/host/memory.py` | ✓ (line 353) |
| Durable / projection owner | `dayu/host/durable/memory.py`, `dayu/host/memory_repair.py` | ✓ (lines 354-355) |
| Compact material consumer | `dayu/host/compact_material.py` | ✓ (line 358) |
| RunInputBuilder consumer | `dayu/host/run_input.py` | ✓ (line 359) |
| Dispatch / ingest consumer | `dayu/host/dispatch.py`, `dayu/host/engine_ingest.py` | ✓ (lines 361-362) |
| Runtime config consumer | `dayu/runtime/config_loader.py` | ✓ (line 364) |
| Service assembly consumer | `dayu/service/host_assembly.py` | ✓ (line 363) |
| Test consumer | 15 个测试文件 | ✓ (lines 366-381 全覆盖) |

allowed files 中的 `dayu/host/compact_payload.py`、`dayu/host/context_events.py`、`dayu/host/context_fallback.py` 不在 direct consumer closure list，但它们是 "仅当" 条件文件（仅在 projection payload reader / event reader / fallback view 需要 vNext type 时触碰），不是 `MemoryProjectionPolicy` 字段的直接 consumer。closure list 聚焦 policy 字段消费者是合理的。

**结论**: direct consumer closure list 完整覆盖所有 policy 字段的直接 production 和 test consumer。

### F5. [PASS] stop conditions 充分阻止实现 agent 再次猜契约

**证据**: Codex artifact lines 93-98 与 plan diff line 96:

1. "implementation prompt 或代码尝试使用 `selected_recent_window_floor_turns`、generic item/text cap、projection rebuild/catchup generic fields" → 停止
2. "发现 `docs/host/design.md` 的 `memory_projection_policy` 字段不足以实现需求" → 停止
3. "需要 alias、compatibility wrapper、旧 config key 兼容读取、旧 snapshot bridge、extra payload 或 raw dict patch 才能 pyright-clean" → 停止
4. "直接 consumer 无法在同一 Slice C 内 pyright-clean closure" → 停止

Plan diff line 96 补充: "如果实现者认为设计真源字段应改变，必须停止 Slice C implementation，回到 design source gate"

**分析**: 四个 stop condition 覆盖了上轮 retry 的所有失败模式：(1) 使用错误字段名；(2) design source 不足时自行扩展；(3) 用兼容机制绕过；(4) 无法闭环时推给后续 slice。第五个条件补充了 design source change 必须走 formal gate。

**结论**: stop conditions 充分，覆盖所有已知失败模式。

### F6. [PASS] allowed file/test matrix 范围合理

**验证方法**: 检查 Slice C allowed files 是否过度扩大或明显缺失。

allowed files 共 35 个条目 (lines 351-384)，覆盖:
- Host memory/durable/projection/repair: 5 个
- Host compact/event/payload/fallback: 4 个
- Host run_input: 1 个
- Host dispatch/ingest: 2 个
- Service assembly: 1 个
- Runtime config: 1 个
- Config JSON: 1 个
- Tests: 20 个（含条件文件）

required validation (Codex artifact lines 102-110) 覆盖所有 affected test batches + pyright，与 plan Slice C 测试命令 (lines 447-454) 一致。

**结论**: matrix 范围合理，既足以支撑 pyright-clean vertical closure，又不过度扩大到非 Slice C 文件。没有发现缺失或过度扩大。

### F7. [OBSERVATION] `dayu/config/README.md` 触发未显式列入

**证据**:
- AGENTS.md line 95: "`dayu/config/` 修改 -> 更新 `dayu/config/README.md`"
- Plan Slice C line 365: 修改 `dayu/config/execution_profiles.json`
- Plan README triggers (lines 651-657): 未提及 `dayu/config/README.md`
- Plan Slice D allowed files (lines 501-503): 列出 `dayu/host/README.md`、`tests/README.md`、`README.md`，未列出 `dayu/config/README.md`
- `dayu/config/README.md` 文件已存在

**分析**: Plan 修改 `dayu/config/execution_profiles.json` 的 `memory_projection_policy` 字段，触发了 AGENTS.md 的 `dayu/config/` → `dayu/config/README.md` 更新规则。Plan 的 README 触发说明未显式覆盖此触发条件，Slice D 的 allowed files 也未列入 `dayu/config/README.md`。

这不是冲突——plan 没有说"不更新 config README"，只是未显式列入。AGENTS.md 作为项目级规则对 implementation agent 仍有约束力，implementation agent 应同时遵循 plan 和 AGENTS.md。但 plan 作为 implementation agent 的直接指令，缺少此触发条件可能导致 implementation agent 遗漏。

**严重性**: 低。不影响 plan fix 的正确性。建议在 Slice D implementation 前确认 `dayu/config/README.md` 是否需要更新（如 `memory_projection_policy` 字段变更影响配置说明），或在本 plan 的 README 触发节补充此触发条件。

### F8. [OBSERVATION] Codex artifact 措辞小瑕

**证据**: Codex artifact line 18: "一性原理判断" 应为 "第一性原理判断"。

**分析**: 缺字不影响语义理解，且该行属于 review artifact 注释而非 plan 正文。plan 正文 line 14 正确使用 "第一性原理"。

**严重性**: 极低。不影响 plan fix 正确性。

---

## Cross-Check Matrix

| 审查维度 | 状态 | 关键证据 |
|---|---|---|
| design source 字段清单逐字完整 | PASS | F1 |
| `selected_recent_window_turn_floor` vs `floor_turns` 正确 | PASS | F1, F3 |
| per-section cap/floor 未被 generic shape 替代 | PASS | F2 |
| 所有禁止字段显式拒绝 | PASS | F2 |
| 所有禁止机制显式拒绝 | PASS | F2 |
| `engine_ingest.py` 歧义消除 | PASS | F3 |
| direct consumer closure list 完整 | PASS | F4 |
| stop conditions 充分 | PASS | F5 |
| allowed file/test matrix 范围合理 | PASS | F6 |
| README 触发与 AGENTS.md 无冲突 | PASS (含 observation) | F7 |

---

## Residual Risks

- **F7 config README 遗漏**: 低风险。AGENTS.md 规则对 implementation agent 仍有约束力，但 plan 未显式列入可能被遗漏。建议在 Slice D 或 implementation closeout 时主动确认。
- **Slice C 本身是较大 vertical closure**: 已在 controller adjudication 和原 plan 中 accept，不再重新评估。本 review 仅判断 plan fix 是否解决了 policy contract conflict。

---

## Review Conclusion

Plan fix 充分解决了上一轮 Slice C implementation retry 的 policy contract conflict:

1. `docs/host/design.md` 的 `memory_projection_policy` 字段清单已逐字完整落地为唯一真源。
2. 所有 retry prompt generic shape 字段 (`selected_recent_window_floor_turns`, `max_memory_items_per_category`, `max_text_chars_per_memory_item`, `projection_max_repair_attempts`, `projection_max_rebuild_rows`, `projection_max_catchup_rows`) 与所有旧 production 字段 (`max_evidence_backed_facts`, `max_working_assumptions`, `recent_raw_turns_floor`, `history_pool_*`, `stable_layer_*`) 均有显式禁止，且禁止进入 production dataclass、config JSON、typed config view、Service assembly、test fixture 与 README。
3. alias、compatibility wrapper、默认补齐、extra payload、双字段真源、旧库兼容读取、snapshot bridge 等所有绕过机制均有显式禁止。
4. `engine_ingest.py` 的字段迁移路径已收敛为唯一正确字段名，删除了"或本 slice 明确的新字段"歧义。
5. direct consumer closure list 完整覆盖所有 production 和 test consumer，并与 Slice C allowed files 一致。
6. stop conditions 充分覆盖所有已知失败模式。
7. allowed file/test matrix 范围合理，required validation 命令覆盖所有 affected test batches。
8. README 触发说明与 AGENTS.md 无冲突（有一个非阻塞的 config README 遗漏 observation）。

**Verdict: PASS** — 后续 Slice C implementation 可以基于此 plan fix 对 `docs/host/design.md` 的 `memory_projection_policy` 字段集合直接对齐实现。
