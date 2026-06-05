# WU-CM-01 Compact Contract Closure Plan Re-Review

## Metadata

| 项目 | 值 |
|---|---|
| work unit | WU-CM-01 Conversation Memory overall optimization |
| gate | compact contract closure plan re-review gate |
| design source | `docs/host/design.md` 第 24 / 25 章 |
| control doc | `docs/host/issues-implementation-control.md` |
| plan doc | `docs/host/wu-cm-01-conversation-memory-plan.md` |
| plan artifact | `docs/reviews/wu-cm-01-compact-contract-closure-plan-codex.md` |
| review artifacts | `docs/reviews/wu-cm-01-compact-contract-closure-plan-review-mimo.md`; `docs/reviews/wu-cm-01-compact-contract-closure-plan-review-ds.md` |
| controller adjudication | `docs/reviews/wu-cm-01-compact-contract-closure-plan-review-controller-adjudication.md` |
| fix artifact | `docs/reviews/wu-cm-01-compact-contract-closure-plan-fix-codex.md` |
| reviewer | AgentDS |
| date | 2026-06-04 |
| re-review scope | 只判断 AgentCodex 的 plan fix 是否完整处理 Controller accepted findings，并判断 Pre-Slice C 是否足以进入 implementation。不修改 production code、tests、README 或 plan。 |
| conclusion | **pass** |

## Re-Review Scope

本 re-review 只对准 Controller adjudication 中 `accepted` 的全部 findings，逐项验证 plan fix 是否已在 `docs/host/wu-cm-01-conversation-memory-plan.md` 中落地。不对 Controller 的判定做二次裁决，也不扩大审查范围到 Controller 未 accepted 的 findings。

## Controller Accepted Findings — 逐项验证

### DS B1: `tests/host/test_compact_artifact_store.py` orphaned

**Controller 修复要求**：加入 Pre-Slice C allowed tests 和测试命令，限定为 artifact store 的 vNext candidate / quality check / material JSON 迁移。

**Fix 验证**：**已完整处理。**

Plan 文档中共 6 处落地点：

| 位置 | 内容 | 行号 |
|---|---|---|
| allowed files | `tests/host/test_compact_artifact_store.py`，仅限 artifact store 的 vNext candidate / quality check / material JSON 迁移 | 250 |
| 实现边界 | `tests/host/test_compact_artifact_store.py` 必须从旧 candidate / quality check / material JSON 断言迁移到 vNext contract | 267 |
| 测试命令 | 显式包含在 pytest 命令中 | 282 |
| 退出信号 | 显式列在必须通过的 tests 列表中 | 301 |
| Test Matrix | 核心 contract/projection 中单独列出 | 551 |
| 最终验证命令 | 包含在最终 ptest 命令中 | 589 |

Scope 限定与 Controller 要求一致：只做 artifact store 的 vNext candidate / quality check / material JSON 迁移，不扩大到其他 domain。

---

### DS B2: `dayu/host/compaction_evidence.py` 无 slice owner

**Controller 修复要求**：加入 Pre-Slice C allowed files，限定为 compact evidence material section label / vNext material contract 迁移。

**Fix 验证**：**已完整处理。**

Plan 文档中共 4 处落地点：

| 位置 | 内容 | 行号 |
|---|---|---|
| allowed files | `dayu/host/compaction_evidence.py`，仅限 compact evidence material section label / vNext material contract 迁移 | 240 |
| 实现边界 | 明确要求同步使用 vNext material section label，不得继续依赖旧 `CompactMaterialBlockKind` 或旧 material JSON field | 262 |
| 退出信号 | production closeout files 列表中显式包含 `compaction_evidence.py` | 296 |
| Allowed Files Summary | 总体列表中包含 | 520 |

补充验证：`tests/host/test_compaction_evidence*` 不存在（Glob 确认），因此无 orphan test 风险。Scope 限定与 Controller 要求一致。

---

### DS B3: 退出信号 grep 与 class definition 删除张力

**Controller 修复要求**：重写 exit signal — 旧 candidate/type/helper 在 production closeout files 中不得有 class definition、public export 或 production reference；历史 docs / implementation report 可命中。若保留任何旧 symbol，必须是私有、不可导出、非 production path，并 report 给出直接证据。

**Fix 验证**：**已完整处理。**

Plan 第 296 行退出信号完全重写，不再使用盲 grep 作为唯一标准。新 exit signal 建立了三层条件：

1. **必须清零**：旧 candidate / type / helper 在 8 个 production closeout files 中不得再有 class definition、public export 或 production reference。
2. **允许命中但不出错**：历史 docs、review artifact、implementation report 可命中旧 symbol（明确豁免非 production 文本）。
3. **保留的严格条件**：若保留旧 symbol，必须同时满足：(a) 私有 (b) 不可导出 (c) 非 production path，并在 implementation report 中给出直接代码证据和 owner。

8 个 production closeout files 列表完整：`compaction.py`、`llm_compaction.py`、`context_governance.py`、`compaction_operation.py`、`context_events.py`、`compact_payload.py`、`compact_material.py`、`compaction_evidence.py`。

该 exit signal 比原 grep 方案精确，避免了盲 grep 误伤历史 artifact，同时封死了旧 symbol 继续作为 production API 的风险。

---

### MiMo 1: exit signals 未显式列出关键测试文件

**Controller 修复要求**：显式列出 `test_compaction_contract.py`、`test_llm_compaction.py`、`test_compaction_operation.py`、`test_compact_material.py`、`test_compact_artifact_store.py`。

**Fix 验证**：**已完整处理。**

Plan 第 301 行退出信号完整列出 5 个测试文件，并写明了 fake/public smoke 的触发条件。第 282 行测试命令也同步更新。清单与 Controller 要求完全一致。

---

### MiMo 2: exit signals 缺少 vNext positive adoption 验证

**Controller 修复要求**：增加 positive signals — `context_governance.py` production accept barrier 使用 vNext checker；operation closeout / repair / fallback 使用 vNext candidate。

**Fix 验证**：**已完整处理。**

Plan 第 299-300 行增加两个 positive signals：

1. `context_governance.py` 的 production accept barrier 使用 vNext checker；operation accepted / rejected / repair exhausted / fallback closeout、whole-candidate repair 和 failed fallback 均使用 vNext candidate、vNext quality issue 与 vNext payload / artifact helper。
2. `context_events.py` 中旧 compact payload constants、旧 field allowlist 与旧 payload reader / writer helper 不再作为 production event contract 暴露。

此外，第 298 行对 `LLMContextCompactor.compact()` 只返回 vNext 的要求也是 positive signal。这比原 exit signals 的 negative-only 验证显著改善。

---

### DS N1: `compact()` / `compact_request_vnext()` 双 method 收敛策略

**Controller 修复要求**：明确收敛策略。

**Fix 验证**：**已完整处理。**

Plan 第 256 行明确：

- `ContextCompactor` 的生产 protocol、`LLMContextCompactor.compact()` 与 operation 调用路径必须收敛到 `ConversationCompactOutputVNext`。
- `compact_request_vnext()` 若实现阶段临时保留，只能作为未导出的内部拆分 helper，必须由 public production `compact()` 调用。
- Slice closeout 时不得形成 `compact()` 旧 contract 与 `compact_request_vnext()` vNext contract 并存的双 public method。

三个约束（临时保留条件 → 调用关系 → closeout 禁止双 public method）覆盖了实现全生命周期，不会留下分叉风险。

---

### DS N2: `run_compaction_operation()` compactor 参数类型

**Controller 修复要求**：compactor 参数类型必须是返回 vNext output 的 protocol。

**Fix 验证**：**已完整处理。**

Plan 第 257 行明确：`run_compaction_operation()` 的 `compactor` 参数类型必须是返回 vNext output 的 `ContextCompactor` protocol；不得继续以旧 `CompactionCandidate` compactor annotation、overload 或 adapter 维持编译。禁止项明确封死三种绕路方式（旧 annotation / overload / adapter）。

---

### DS N4: `context_events.py` / `compact_payload.py` 旧 payload constants 清理

**Controller 修复要求**：明确清理范围和退出信号。

**Fix 验证**：**已完整处理。**

两处落地：

1. 实现边界（第 265 行）：`context_events.py` / `compact_payload.py` 如被触碰，只能收敛到 vNext candidate JSON 及相关 refs，旧 compact payload constants、旧 field allowlist、旧 payload reader / writer helper 必须同步清理，不得保留旧 payload fields 给后续 memory projection 兼容读取。
2. 退出信号（第 300 行）：`context_events.py` 中旧 compact payload constants、旧 field allowlist 与旧 payload reader / writer helper 不再作为 production event contract 暴露。

---

### DS residual: 外部 `ContextCompactor` implementor risk

**Controller 修复要求**：标注 residual risk。

**Fix 验证**：**已完整处理。**

Plan 第 307 行在 Pre-Slice C residual risks 中明确标注：外部 `ContextCompactor` implementor 若存在，可能因 protocol 从旧 candidate 收敛到 vNext output 而需要同步迁移；当前 slice owner 必须通过 package exports / tests / pyright 识别仓库内 implementor，仓库外 implementor 风险作为 public contract breakage 在 implementation report 中列明。

---

## 额外检查

### Owner 缺口复核

| 文件 | Pre-Slice C owner | 说明 |
|---|---|---|
| `dayu/host/compaction.py` | 是 | 核心 production owner |
| `dayu/host/llm_compaction.py` | 是 | LLM parser |
| `dayu/host/context_governance.py` | 是 | quality checker |
| `dayu/host/compact_material.py` | 是 | material pack |
| `dayu/host/compaction_operation.py` | 是 | operation closeout |
| `dayu/host/compaction_evidence.py` | 是 | DS B2 fix 后已补 |
| `dayu/host/context_events.py` | 条件 | payload reader/writer 受触及时 |
| `dayu/host/compact_payload.py` | 条件 | payload reader/writer 受触及时 |
| `dayu/host/dispatch.py` | 条件 | proactive closeout 受影响时 |
| `dayu/host/engine_ingest.py` | 条件 | reactive closeout 受影响时 |

**无 owner 缺口。** 所有 compact production owner 均有明确归属。

### 跨层越界检查

Pre-Slice C 的 allowed files 全部在 `dayu/host/` 和 `tests/host/` 范围内。Service、Engine、Runtime、UI、Fins 均未混入。禁止项（第 275 行）明确禁止混入 Slice C 内容（`memory.py`、`durable/memory.py`、`run_input.py`、`host_assembly.py`、`config_loader.py`、`execution_profiles.json`）。

**无跨层越界。**

### Compat wrapper / alias 风险检查

Pre-Slice C 禁止项（第 269-276 行）覆盖 6 类违规模式：旧 candidate type wrapper、旧 material field alias、旧 block kind alias、旧 snapshot bridge、Slice C 混入、类型逃逸。所有模式有明确禁止表述。退出信号（第 296 行）进一步封死旧 symbol 的 production class definition、public export、production reference。

此外，plan 第 256 行对 `compact_request_vnext()` 的收敛约束（不能成为与 `compact()` 并存的双 public method）防止了 method-level alias。

**无 compat wrapper / alias 风险残留。**

### Implementation scope 检查

Pre-Slice C 的 scope 严格限定在 compact contract domain：material pack → LLM parser → quality checker → operation closeout → event payload → artifact write。Tests 限定在 5 个核心文件 + 条件追加的 fake/smoke。不涉及 memory durable、projection、RunInputBuilder、config assembly。

**Scope 合理，未过大。**

### Design.md 一致性检查

Plan 的 vNext contract 定义直接引用 `docs/host/design.md` 第 24.3 章：`ConversationCompactInputVNext`（`previous_compacted_view`、`trace_material`、`evidence_material`、`answer_material`、`current_input_anchor`、`instruction`）与 `ConversationCompactOutputVNext`（`schema_version`、`session_summary`、`evidence_backed_facts`、`answer_anchors`、`forward_intents`、`reference_continuity_items`、`diagnostics`）。design.md 第 2880-2925 行确认 compact request 输入边界固定为 `ConversationCompactInputVNext`，compactor 输出 schema 以 vNext compact I/O contract 为准。

**Plan 与 design.md 一致，无冲突。**

### 非阻塞观察：compaction_evidence.py 无对应测试文件

`tests/host/test_compaction_evidence*` 不存在。Pre-Slice C 修改 `compaction_evidence.py` 时，其正确性主要依赖 pyright 类型检查和间接通过 material/operation tests 覆盖。由于修改 scope 限定为 "compact evidence material section label / vNext material contract 迁移"，影响面窄，风险可控。实现 agent 应将此作为 implementation 校验点——若修改范围超出单纯 label 替换，应考虑在已有 material 或 operation tests 中添加相关断言。

**此观察为 non-blocking，不阻塞进入 implementation。**

## 总结

Controller 的 9 个 accepted findings 全部在 plan 文档中找到直接、可验证的落地点。额外检查也确认无 owner 缺口、跨层越界、compat 风险、过大 scope 或 design.md 冲突。

| finding 来源 | 数量 | 状态 |
|---|---|---|
| DS B1/B2/B3 | 3 | 全部已修复 |
| MiMo 1/2 | 2 | 全部已修复 |
| DS N1/N2/N4/residual | 4 | 全部已修复 |
| 额外检查 | 5 项 | 全部通过 |

## 结论

**pass。**

Pre-Slice C - Compact Contract Closure 的 plan 已足够进入 implementation gate。Implementation agent 应严格按 plan 的 allowed files、实现边界、禁止项、测试命令和退出信号执行，特别注意 `compaction_evidence.py` 的修改不超出 section label / material contract 迁移范围。
