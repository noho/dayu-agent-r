# WU-CM-01 Slice C Policy Contract Plan Fix Review - Mimo

## Gate Status 与结论

- Gate: WU-CM-01 Slice C policy contract plan fix review
- Branch: `phaseflow/wu-cm-01`
- Reviewer: Mimo (planreview skill)
- Verdict: **pass** (no blocking finding)
- Changed files under review:
  - `docs/host/wu-cm-01-conversation-memory-plan.md` (uncommitted diff)
  - `docs/reviews/wu-cm-01-slice-c-policy-contract-plan-fix-codex.md` (untracked)
- Production code / tests / README: not modified

## Findings (severity sorted)

### F-0 informational: plan 的 "不得引入" 列表与 Codex artifact 禁止字段列表措辞不完全对齐

- 位置: plan 第 437 行 `不得引入` 节 vs Codex artifact 第 67-81 行 `禁止字段` 节
- 证据: plan 第 437 行只写"旧库兼容读取、旧字段 fallback codec、旧 item kind alias、compatibility wrapper / facade / re-export"，未逐字列出 `selected_recent_window_floor_turns`、`max_memory_items_per_category`、`max_text_chars_per_memory_item`、`projection_max_repair_attempts`、`projection_max_rebuild_rows`、`projection_max_catchup_rows`、`max_evidence_backed_facts`、`max_working_assumptions`、`recent_raw_turns_floor`、`history_pool_*`、`stable_layer_*`。
- 影响: 无 blocking。上述字段在 plan 第 96 行（Slice C 前置说明）、第 392 行（dataclass / JSON / config view / assembly 硬约束）、第 393 行（config_loader 不接受旧字段）和第 394 行（旧 config 字段 fail fast）中已被显式禁止。第 437 行的"不得引入"列表是第 392-334 行之间所有约束的总结性收口，措辞偏泛但不产生漏洞。
- 建议: 后续 implementation prompt 可在 "不得引入" 节补充显式字段黑名单，减少实现 agent 的推断负担。非 blocker。

### F-1 informational: allowed test matrix 与 Codex artifact required validation 命令列表存在微小措辞差异

- 位置: plan 第 366-384 行 allowed test files vs Codex artifact 第 103-110 行 required validation commands
- 证据: plan 列出 17 个 allowed test files（含条件触发的 `test_public_contracts.py`、`test_public_compact_smoke.py`、`test_public_tool_wiring_smoke.py`）；Codex artifact 的 pytest 命令列出 15 个 test files（不含 `test_public_contracts.py` 和 `test_public_tool_wiring_smoke.py`）。差异来自 plan 包含"仅当"条件触发的 optional files，Codex 只列 mandatory batch。
- 影响: 无 blocking。plan 的 allowed matrix 是文件白名单（可修改范围），Codex 的 required validation 是必须通过的最小命令集。两者语义不同但互补，不冲突。
- 建议: 后续 implementation prompt 应明确"仅当"条件触发文件的判断标准，避免实现 agent 过度扩大或遗漏。非 blocker。

### F-2 informational: plan 无独立 "stop conditions" 小节，依赖 slice verification boundary 与实现边界约束

- 位置: plan 第 84-92 行 Slice Verification Boundary、第 386-412 行实现边界
- 证据: Codex artifact 有独立 "Stop Conditions 和 Required Validation" 小节（第 92-111 行），列出 4 条显式 stop condition 和 6 条 required validation 命令。plan 的 stop 语义分散在多处：第 90 行"如果某个 slice 发现 vNext contract 需要改变，停止当前 slice"、第 96 行"如果实现者认为设计真源字段应改变，必须停止 Slice C implementation，回到 design source gate"、第 392 行 dataclass / JSON / config view / assembly 硬约束、第 394 行旧 config 字段 fail fast、第 409 行 engine_ingest 同 slice 同步迁移。
- 影响: 无 blocking。plan 的 stop 语义覆盖面完整，只是没有像 Codex 那样集中为独立小节。实现 agent 在读 plan 时需要从多处提取 stop conditions，但每条 stop 语义都有直接、明确的措辞，不存在歧义。
- 建议: 后续 implementation prompt 可在 Slice C 实现边界末尾追加一个集中式 stop conditions 小节，汇总所有 stop 触发条件。非 blocker。

## 审查重点逐项判定

### 1. `selected_recent_window_floor_turns` 或 generic policy shape 是否仍被允许进入 production/config/test/README

**判定: 已阻断。**

- plan 第 96 行: 显式禁止 6 个 generic fields 进入 production dataclass、config JSON key、typed config view、Service assembly 参数、test fixture 或 README 术语。
- plan 第 362 行: `engine_ingest.py` 约束明确只能迁移到 `selected_recent_window_turn_floor`，不得改用 `selected_recent_window_floor_turns`。
- plan 第 392 行: 硬约束 dataclass / JSON / config view / assembly / test fixture 必须使用完全相同的字段集合，字段名必须是 `selected_recent_window_turn_floor`。
- plan 第 393 行: config_loader 不接受旧 `max_evidence_backed_facts`、`max_working_assumptions`、`recent_raw_turns_floor`、`history_pool_*`、`stable_layer_*`。
- plan 第 394 行: 旧 config 字段必须由 schema validation fail fast。
- plan 第 421 行: Runtime config consumer 只接受 design-source JSON key，旧 key 和 retry prompt generic key 均 fail fast。
- 没有发现任何允许 generic shape 通过 alias、wrapper、默认补齐或 extra payload 进入的路径。

### 2. design source 字段清单是否逐字完整

**判定: 完整。**

- design.md 第 95 行 `memory_projection_policy` 列出 20 个字段（`context_window_size` 至 `policy_ref`）。
- plan 第 391 行逐字列出完全相同的 20 个字段。
- Codex artifact 第 44-65 行逐字列出完全相同的 20 个字段。
- 三方一致，无遗漏、无拼写偏差。

### 3. `selected_recent_window_turn_floor` 与 per-section cap/floor 是否完整

**判定: 完整。**

design.md 第 95 行明确的 per-section cap/floor 字段:
- selected recent window: `selected_recent_window_item_cap`、`selected_recent_window_char_cap`、`selected_recent_window_turn_floor`
- fallback selected recent window: `fallback_selected_recent_window_item_cap`、`fallback_selected_recent_window_char_cap`
- evidence fact: `evidence_fact_item_cap`、`evidence_fact_char_cap`、`evidence_fact_floor`
- session summary: `session_summary_char_cap`
- answer anchor: `answer_anchor_item_cap`、`answer_anchor_char_cap`
- forward intent: `forward_intent_item_cap`、`forward_intent_char_cap`
- reference continuity: `reference_continuity_item_cap`、`reference_continuity_char_cap`、`reference_continuity_item_floor`
- inline delta repair: `max_lag_events_for_inline_delta`、`max_delta_repair_events`
- meta: `context_window_size`、`policy_ref`

plan 第 391 行和 Codex artifact 第 44-65 行均完整列出上述全部字段。

### 4. allowed file/test matrix 是否足以支撑 pyright-clean implementation

**判定: 足够，无明显缺失或过度扩大。**

allowed production files (plan 第 351-365 行):
- `dayu/host/memory.py`、`dayu/host/durable/memory.py`、`dayu/host/memory_repair.py`: policy / snapshot / durable / projection owner
- `dayu/host/compact_payload.py`、`dayu/host/context_events.py`: 条件触发，仅当 projection payload / event reader 需要 vNext typed helper
- `dayu/host/compact_material.py`: 仅限 previous compacted view、selected recent window、ordinary material 与 vNext snapshot 消费
- `dayu/host/run_input.py`: RunInputBuilder
- `dayu/host/context_fallback.py`: fallback view
- `dayu/host/dispatch.py`: 仅限 memory snapshot precondition、projection catch-up、fallback view 与 RunInputBuilder 参数迁移
- `dayu/host/engine_ingest.py`: 仅限 reactive compaction pending request 的 recent-window floor 字段迁移
- `dayu/service/host_assembly.py`: 仅限 config typed view 到 Host policy 映射
- `dayu/runtime/config_loader.py`: 仅限 execution_profiles.json.memory_projection_policy typed config schema / validation 迁移
- `dayu/config/execution_profiles.json`: 仅限 packaged memory_projection_policy 字段迁移

allowed test files (plan 第 366-384 行): 17 个 test files，含条件触发的 optional files。

所有 allowed files 都有"仅限"约束，不产生过度扩大。allowed matrix 与 Codex artifact 的 required validation 命令集互补。

### 5. stop conditions 是否足够阻止实现 agent 再次猜契约

**判定: 足够。**

plan 的 stop 语义分布在以下位置:
- 第 90 行: "如果某个 slice 发现 vNext contract 需要改变，停止当前 slice，回到 design source / plan 修正；禁止在实现中发明局部兼容分支。"
- 第 96 行: "如果实现者认为设计真源字段应改变，必须停止 Slice C implementation，回到 design source gate，而不是在代码中局部发明契约。"
- 第 392 行: dataclass / JSON / config view / assembly / test fixture 必须使用完全相同的字段集合。
- 第 394 行: 旧 config 字段必须由 schema validation fail fast。
- 第 409 行: engine_ingest 必须在同 slice 同步迁移，不得通过旧 policy alias 维持编译。
- 第 421 行: Runtime config consumer 旧 key 和 retry prompt generic key 均 fail fast。

Codex artifact 第 92-99 行的 4 条显式 stop conditions 与上述 plan 约束完全对齐。实现 agent 在读 plan + Codex artifact 时，所有 stop 触发条件都有直接、明确的措辞。

### 6. README 触发说明是否与 AGENTS.md 文档规则冲突

**判定: 无冲突。**

plan 第 651-657 行的 README / Doc Sync Triggers:
- 修改 `dayu/host/` → 检查 `dayu/host/README.md`
- 修改 `tests/` → 检查 `tests/README.md`
- 修改 `utils/smoke_host_public_*` → 条件更新根目录 `README.md`
- 不更新 `dayu/README.md`，除非分层关系或装配边界变化
- 不更新 `dayu/fins/README.md`

与 CLAUDE.md 的 README 触发规则一致，不产生冲突。

## 验证矩阵

| 验证项 | 结果 |
|---|---|
| design.md 字段清单 vs plan 字段清单 | 20/20 一致 |
| design.md 字段清单 vs Codex artifact 字段清单 | 20/20 一致 |
| plan 禁止字段 vs Codex artifact 禁止字段 | 完全覆盖（plan 措辞偏泛但语义等价） |
| plan allowed files vs Codex required validation | 互补，无冲突 |
| plan stop conditions vs Codex stop conditions | 对齐，plan 分散但完整 |
| plan README triggers vs CLAUDE.md README triggers | 一致 |
| `selected_recent_window_turn_floor` 拼写一致性 | plan 全文使用正确拼写，无 `selected_recent_window_floor_turns` 泄漏 |
| alias / wrapper / 默认补齐 / extra payload / 双字段真源 阻断 | 第 96、392、394、395、409、421 行已阻断 |

## 结论

plan fix 充分解决了上一轮 Slice C implementation retry 的 policy contract conflict。design source 字段清单逐字完整，generic policy shape 已被显式禁止进入 production/config/test/README，allowed file/test matrix 足够支撑 pyright-clean implementation，stop conditions 足够阻止实现 agent 再次猜契约，README 触发说明与 AGENTS.md 文档规则无冲突。无 blocking finding。

**verdict: pass**
