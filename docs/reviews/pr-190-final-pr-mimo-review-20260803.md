# PR 190 Final Independent PR Review — AgentMiMo

**日期**: 2026-08-03
**审查范围**: `main..0f7dc591` (43 commits, 364 files, +141152/-15597)
**本次 follow-up commits**: `7cf1027c..0f7dc591` (6 commits: plan + S1–S4 + aggregate)
**PR**: fix(cli): close interactive conformance gaps (draft, codex/interactive-oracle)
**Remote HEAD**: `0f7dc59168aca6e5f5b5bb30c059711465347bf2`
**Base**: `main` (`113ea34d`)
**工作树**: 干净（`git status --porcelain` 无输出）
**PR 状态**: OPEN, isDraft=true, mergeable=MERGEABLE

---

## 审查结论

**PASS — 无 blocking finding。**

本次 Compactor LLM-facing follow-up（`7cf1027c..0f7dc591`）实现了 v2 compaction schema、LLM-facing prompt 重写、coverage partition 验证、repair feedback 机制。代码结构清晰，语义所有权边界正确，LLM-facing 文本自足且业务可读。deterministic 测试矩阵全部通过。

**真实 provider 行为 not_observed**：本次 follow-up 的真实 smoke 运行中，Mimo 与 DeepSeek 均被分类为 `network_unavailable`，未收到任何非空 candidate。strict parse、governance acceptance、caps compliance、injection resistance 的真实模型行为观察为空；deterministic matrix 只证明 owner contract，不替代真实行为。

---

## 审查范围说明

本审查覆盖 PR 全量 diff `main..0f7dc591`，但将 follow-up commits（`7cf1027c..0f7dc591`，即 Compactor LLM-facing plan/S1-S4/aggregate）与前序 F01-F07 closeout commits（`main..7cf1027c`）的证据严格分离：

- **F01-F07 closeout**（前序）：interactive conformance 修正、frozen oracle/scenario registry 更新、ESC sequence predicate 新增、P25→P27R baseline 重命名、full-real bundle 采集。
- **Compactor LLM-facing follow-up**（本次）：v2 schema 迁移、prompt 重写、governance acceptance、repair feedback、coverage partition。

---

## 审查维度与结果

### 1. Correctness

| # | 严重度 | Finding | Evidence |
|---|--------|---------|----------|
| C1 | — | **PASS**: `CompactCandidateV2` 与 `CompactInputV2` 的 `to_json()` / parser 严格对齐。parser 使用 `_strict_object_pairs` 检测重复 key、`_require_exact_keys` 检测未知 key。 | `dayu/host/llm_compaction.py:_parse_vnext_proposal` (L756-808) |
| C2 | — | **PASS**: `_validate_committed_coverage` 验证 represented ∪ dropped = boundary、represented ∩ dropped = ∅、顺序保持、candidate 派生 section 一致。 | `dayu/host/compact_payload.py:_validate_committed_coverage` |
| C3 | — | **PASS**: `CompactionTerminalCommitPermit` 通过 `_CompactAcceptancePermit` 私有构造函数强制 `CompactAcceptedTruthV2` 只能由 governance owner 产出。 | `dayu/host/compaction.py:_COMPACT_ACCEPTANCE_PERMIT` |
| C4 | — | **PASS**: ESC sequence 歧义解析属于 F01-F07 closeout 范围，非本次 follow-up。`run_keys.py` 的 `Vt100Parser` + 100ms ambiguity window 实现在前序 commits 中已完成。 | `dayu/cli/run_keys.py:_classify_running_key_batch` (前序 `7cf1027c`) |
| C5 | — | **PASS**: SIGINT handler fallback 属于 F01-F07 closeout 范围，非本次 follow-up。 | `dayu/cli/agent_entrypoint.py:CliSigintMonitor.install` (前序 `7cf1027c`) |

### 2. Semantic Ownership Drift

| # | 严重度 | Finding | Evidence |
|---|--------|---------|----------|
| S1 | — | **PASS**: v2 schema 的每个字段有唯一 owner。`CompactCandidateV2` 由 LLM 产出、Host governance 验收；`CompactAcceptedTruthV2` 由 governance owner 独占构造；`ContextCompactedSemanticPayload` 从 truth/boundary/coverage 派生 `compacted_source_refs` 属性。 | `dayu/host/compaction.py`, `dayu/host/context_governance.py`, `dayu/host/compact_payload.py` |
| S2 | — | **PASS**: `CompactorProposalManifestReference` 从 `compaction_operation.py` 迁移到 `context_events.py`（canonical event owner），消除了跨层引用。 | `dayu/host/context_events.py:L807-845` |
| S3 | — | **PASS**: `SuccessfulRunnerResponseIdentity` 新增于 `dayu/engine/contracts/runner_identity.py`（Engine contracts owner），被 Host `CompactorProposal` 和 `CompactPipelineAcceptedPayloadInput` 正确引用。 | `dayu/engine/contracts/runner_identity.py:L93-170` |

### 3. LLM-facing North-star

| # | 严重度 | Finding | Evidence |
|---|--------|---------|----------|
| L1 | — | **PASS**: 系统 prompt (`conversation_compaction.md`) 自足说明：不可信数据边界 (`UNTRUSTED_COMPACTION_MATERIAL_JSON_BEGIN/END`)、source label 只是引用标签、覆盖规则、修复反馈机制。不含内部类型名或模块名。 | `dayu/config/prompts/scenes/conversation_compaction.md` |
| L2 | — | **PASS**: 用户 prompt (`conversation_compaction_user.md`) 完整说明输入 schema、输出 schema、source-kind 引用规则、覆盖规则、修复反馈 JSON schema。提供完整同源示例输入/输出。 | `dayu/config/prompts/scenes/conversation_compaction_user.md` |
| L3 | — | **PASS**: `CompactSourceBoundaryEntryV2.to_json()` 正确省略 `source_refs`（Host-internal canonical refs），只暴露 `source_label`、`source_kind`、`readable_text` 给 LLM。 | `dayu/host/compaction.py:CompactSourceBoundaryEntryV2.to_json` |
| L4 | — | **PASS**: `intent_type` 和 `reason` 是 frozen v2 str contract。controller 已 REJECT-WITH-REASON 拒绝恢复 enum/pattern acceptance 的提议；当前 `_require_non_empty` 验证是 frozen contract 的正确实现，本 gate 不得扩张 accept pattern。 | `dayu/host/memory.py:L592-610`, `dayu/host/compaction.py:L1221-1234` |
| L5 | — | **PASS**: 修复反馈 prompt 完整说明 `REPAIR_FEEDBACK_JSON_BEGIN/END` 边界、`required_action` + `issues` schema、每个 issue 的四个必填字段。提供最小示例。 | `dayu/config/prompts/scenes/conversation_compaction_user.md:L137-155` |

### 4. Overcoupling

| # | 严重度 | Finding | Evidence |
|---|--------|---------|----------|
| O1 | — | **PASS**: CLI 不依赖 Host/Engine 内部类型。`composer.py` 只暴露 `InteractiveComposerEvent`（CLI-owned）；`session_execution.py` 通过 `InteractiveComposer` 协议交互。 | `dayu/cli/composer.py`, `dayu/cli/session_execution.py` |
| O2 | — | **PASS**: `run_keys.py` 明确限定为 "prompt one-shot"，interactive 由 composer 独占 stdin。模块 docstring 清晰声明职责边界。 | `dayu/cli/run_keys.py:L1-8` |

### 5. Frozen CLI Oracle / Scenario 未因 follow-up 改写

| # | 严重度 | Finding | Evidence |
|---|--------|---------|----------|
| F1 | — | **PASS**: `git diff 7cf1027c..0f7dc591 -- docs/cli_ci_oracles.json docs/cli_ci_scenarios.json` 输出为空（0 行）。follow-up commits（plan/S1-S4/aggregate）未触碰 frozen oracle 或 scenario 文件。 | `git diff 7cf1027c..0f7dc591 -- docs/cli_ci_oracles.json docs/cli_ci_scenarios.json` = 0 lines |
| F2 | — | **PASS**: 既有 frozen oracle/scenario 的 hash 在 follow-up commits 中保持不变。oracle/scenario 的变更（ESC predicate 新增、P25→P27R baseline 重命名等）均属于前序 F01-F07 closeout commits（`main..7cf1027c`），已由前序 review 冻结。 | `git diff 7cf1027c..0f7dc591` = 0 |

### 6. Stability

| # | 严重度 | Finding | Evidence |
|---|--------|---------|----------|
| T1 | — | **PASS**: `CompactionTerminalCommitPermit` 在同一 write transaction 内取得，不可跨 transaction 或 `await` 保存。`begin_compaction_terminal_commit_in_transaction` 检查 operation 无既有 terminal。 | `dayu/host/compaction_terminal.py` |
| T2 | — | **PASS**: `build_compact_repair_feedback_v2` 严格 bound: `MAX_COMPACT_REPAIR_ISSUES=32`、`MAX_COMPACT_REPAIR_ISSUE_MESSAGE_CHARS=240`、`MAX_COMPACT_REPAIR_FEEDBACK_CHARS=8192`。超出时逐项裁剪 issue，最终裁剪 source_labels。 | `dayu/host/context_governance.py:L120-170` |

### 7. Test / Documentation / Manifest / Evidence

| # | 严重度 | Finding | Evidence |
|---|--------|---------|----------|
| E1 | — | **PASS**: PR body 记录 6605 passed / 10 skipped / 6 deselected、pyright 0 errors、Ruff/compileall/JSON validation/frozen hashes 全部通过。 | PR body "Exact-head validation" |
| E2 | Observation | `docs/reviews/` 新增 230 个 review artifact 文件（37,575 行），包含 F01-F07 closeout、Compactor LLM-facing plan/S1-S4/aggregate 的双人 review、fix、re-review 记录。 | `git diff main..0f7dc591 --stat -- docs/reviews/` |
| E3 | — | **PASS（F01-F07 closeout 专属）**: 真实 provider (`mimo-v2.5-pro`) 下 full-real evidence 已采集并密封于 bundle（commit `58aeb7b3`，bundle digest `ab3f6ae5...`，checksum 743/743）。**该 bundle 属于前序 F01-F07 closeout，不能证明本次 Compactor prompt follow-up 的 strict parse/governance/caps/injection behavior。** | PR body "Immutable evidence"（前序 closeout） |
| E4 | **not_observed** | **真实 provider 行为未观察**: 本次 follow-up 的真实 smoke 运行中，Mimo 与 DeepSeek 均被分类为 `network_unavailable`，未收到任何非空 candidate。以下行为必须标记为 `not_observed`，不得当作 pass：strict v2 JSON parse、governance acceptance、repair feedback caps compliance、untrusted boundary injection resistance、whole-candidate replacement repair。deterministic matrix 只证明 owner contract 与 typed boundary，不替代真实模型行为。 | `tests/host/test_public_compact_smoke.py` — Mimo/DeepSeek 均 `network_unavailable` |

### 8. Schema v2 迁移完整性

| # | 严重度 | Finding | Evidence |
|---|--------|---------|----------|
| V1 | — | **PASS**: vNext → v2 重命名一致。`ConversationCompactOutputVNext` → `CompactCandidateV2`，`ConversationCompactInputVNext` → `CompactInputV2`，`CompactQualityCheckResultVNext` → `CompactAcceptedTruthV2 | CompactValidationReportV2`。所有 import 路径已更新。 | 全量 `git diff` |
| V2 | — | **PASS**: 新增 `CompactExplicitDropV2` + `CompactDropReasonV2` 闭集，支持 source 显式丢弃。`CompactSemanticSectionV2` 定义 represented coverage 的业务区枚举。 | `dayu/host/compaction.py` |
| V3 | — | **PASS**: `CompactCandidateV2` 新增 `explicitly_dropped_sources` 字段，与 `CompactValidationReportV2` 的 `UNCOVERED_SOURCE` / `REPRESENTED_AND_DROPPED` issue code 配合，确保每个 boundary source 恰好走一条路径。 | `dayu/host/compaction.py`, `dayu/host/context_governance.py` |

### 9. REPL State Machine Edge Cases（Observation，非 finding）

以下为 `_drive_interactive_tty_repl` 的状态管理边界观察，不构成 blocking finding，不影响 core compaction contract 或 LLM-facing 行为。

| # | 严重度 | Observation | Evidence |
|---|--------|-------------|----------|
| R1 | Observation | **READ_ONLY rejection 不取消 `queued.submit_task`**: READ_ONLY handler 清理 `current`/`current_acceptance_task`/`composer_task`，但 `queued` 和 `queued_acceptance_task` 不变。随后 `queued` 被 promote 为 `current`，submit_task 按引用共享。若 promote 前 submit_task 已完成且 barrier 未 set（submit 异常），`queued_acceptance_task` 挂起至 finally 取消。正常路径下 promote 后 barrier 由 submit 设置，无影响。 | `session_execution.py:L2067-2087`（handler）+ `L2096-2103`（promote） |
| R2 | Observation | **正常 EOF 退出时 `queued.submit_task` 未取消**: EOF handler 设置 `normal_completion = True` 后返回，finally 块中 `queued.submit_task` 的取消被 `if not normal_completion:` 守卫。`queued_acceptance_task` 在行 2132-2133 无条件取消。若 `queued.submit_task` 仍在运行，它作为 fire-and-forget 任务泄漏。 | `session_execution.py:L1928-1930`（EOF）+ `L2132-2135`（finally） |
| R3 | Observation | **空提交不消费 `pending_submit_sigint_count`**: 空 prompt 被拒绝时 `current` 仍为 `None`，消费逻辑要求 `current is not None`，延迟 SIGINT 泄漏到下一个非空 submit turn。 | `session_execution.py:L1849-1851` + `L1933` |

---

## Residual Risks

1. **真实模型行为 `not_observed`（阻塞项）**: 本次 follow-up 的真实 smoke 中 Mimo/DeepSeek 均 `network_unavailable`，未产出非空 candidate。strict parse、governance acceptance、caps compliance、injection resistance 的真实模型行为观察为空。deterministic matrix 只证明 owner contract，不替代真实行为。待网络可用时需补充 `DAYU_RUN_REAL_COMPACTOR_SMOKE=1` 运行。

2. **`previous_session_summary` 注入位置未单独参数化**: adversarial material 测试覆盖了 `current_input`、`trace_material`、`evidence_material`、`answer_material` 四个位置，但 `previous_session_summary`、`previous_evidence_fact` 等 previous-* kind 未单独作为注入参数。这些 kind 的 `readable_text` 同样受不可信边界保护，风险等价，但如需穷举可追加。

3. **Review artifact 体积**: 230 个 review 文件是 gateflow 流程的预期产出，不影响运行时，但增加了仓库体积。

---

## Merge Readiness（仅 code review）

**Code review 层面: READY。**

- 实现正确，语义所有权清晰，LLM-facing 文本自足
- deterministic 测试矩阵全部通过（6605 passed，pyright 0 errors）
- Frozen oracle/scenario 在 follow-up commits 中零变更（`git diff 7cf1027c..0f7dc591` = 0）
- 工作树干净，PR metadata/head 一致

**注意**:
- 本审查仅覆盖 code review 维度。PR 的 draft 状态和正式 conformance pass 决策由 user/Oracle controller 拥有，不在本审查范围内。
- 真实 provider 行为 `not_observed` 是唯一的阻塞 residual；deterministic matrix 不替代真实行为观察。

---

*Generated by AgentMiMo final PR review on 2026-08-03.*
