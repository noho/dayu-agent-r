# Aggregate Deep Review: WU-CLI-CONFORMANCE-F01-F07

## Scope

- **Mode**: Current Changes Mode (aggregate work unit)
- **Branch**: codex/interactive-oracle
- **Base**: cd6344c0
- **Head**: 584ee394
- **Output file**: docs/reviews/wu-cli-conformance-f01-f07-aggregate-deepreview-mimo.md
- **Included scope**: 15 commits, 174 files changed (102,270 insertions, 12,448 deletions)
- **S8 evidence bundle**: `/Users/leo/workspace/.dayu-cli-ci/pr190-wu-cli-conformance-f01-f07-s8-20260803T022326Z-9fec164715bc/bundle` (digest 7a80d9bcfb97bb7c8a80df8d2f10016d6f98577e01294f540a7ba2d9cea33b72)
- **Parallel review coverage**: CLI layer (subagent 1), Host layer (subagent 2), Tests/Design/Gateflow (subagent 3), 主 reviewer 直接审查跨层集成

## Review Verification

| 检查项 | 结果 |
|---|---|
| pyright | 0 errors, 0 warnings, 724 files checked |
| 全量测试 | 6602 passed, 10 skipped, 6 deselected, 1 flaky |
| S8 evidence verdict | PASS, READY-FOR-DUAL-S8-CODE-REVIEW |
| F01-F07 owner matrices | all PASS |

## Findings

### 001-未修复-低-flaky test: test_active_cancel_emits_public_cancel_event

- **入口/函数**: `tests/host/test_public_cancel_smoke.py::test_active_cancel_emits_public_cancel_event`
- **文件(行号)**: tests/host/test_public_cancel_smoke.py
- **输入场景**: 全量测试套件中按特定顺序运行时
- **实际分支**: 全量 suite 中 1 failed；单独运行或同文件运行时全部 pass
- **预期行为**: 全量 suite 中也应 pass
- **实际行为**: 全量 suite 中偶发失败，单独运行时 pass——典型的测试间状态泄漏
- **直接证据**: `6602 passed, 1 failed` (全量) vs `5 passed` (单独文件)
- **影响**: 不影响生产代码正确性；CI 中可能偶发红灯
- **建议改法和验证点**: 检查该测试是否存在 event loop / global state 泄漏；加 `isolation` fixture 或修复 teardown
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 002-未通过-架构良好-CLI cancel/terminal 协调重构

- **入口/函数**: `_ActiveTurnCloseout`, `_InteractiveSigintChordState`, `_InteractiveSessionAttachmentController`
- **文件(行号)**: dayu/cli/session_execution.py
- **评估**: 本次重构将原先分散在 `_PromptAcceptedRunState` / `_InteractiveAcceptedRunState` / `cancel_reason` / `acceptance_task` / `cancel_task` 的状态收敛为三个明确的 coordinator 类型：

  1. `_ActiveTurnCloseout`: 唯一持有 acceptance barrier、cancel intent 和 canonical terminal。`request_cancel` 保证至多一个 Host cancel path；`observe_terminal` 保证唯一 terminal truth；`wait_closeout` 协调 cancel 与 terminal 的 ordering。

  2. `_InteractiveSigintChordState`: 以 `input_revision` reconciliation 机制终结过期 chord，避免旧 SIGINT 语义泄漏到新 turn。`consume_active_signal` / `consume_idle_signal` / `finish_active_closeout` 构成完整的 chord 生命周期。

  3. `_InteractiveSessionAttachmentController`: READ_ONLY rejection 后 `require_refresh()` + `attachment_for_mutation()` 实现 close-before-open fresh attach，不原地升级 attachment mode。

  这三个类型消除了旧代码中 `cancel_reason is None` / `cancel_task is None` / `acceptance_task is None` 的散布式条件判断，每个状态转换都有明确的 typed invariant。

- **直接证据**: session_execution.py diff 中删除了 `_cancel_prompt_turn_after_local_request`、`_cancel_prompt_run_and_wait_for_terminal`、旧 `InteractiveCancelSource`，替换为 `_ActiveTurnCloseout` 的 `request_cancel` / `wait_accepted_then_cancel` / `observe_terminal` / `wait_closeout` 协议
- **影响**: 正面——消除了 cancel/terminal race 的多个潜在窗口
- **严重程度**: 架构良好，无需修复

### 003-未通过-架构良好-Host compaction v2 accept barrier

- **入口/函数**: `accept_compact_candidate_v2`, `build_compact_repair_feedback_v2`
- **文件(行号)**: dayu/host/context_governance.py
- **评估**: 旧 `check_conversation_compact_output_vnext` 只做 label 存在性检查，新 `accept_compact_candidate_v2` 执行完整的五阶段验收：

  1. `_collect_label_and_kind_issues`: source label 存在性、重复、source kind 合法性
  2. `_collect_coverage_issues`: represented/dropped 完整 partition、互斥、无遗漏
  3. `_collect_duplicate_and_contradiction_issues`: semantic item 去重与矛盾检测
  4. `_collect_information_issues`: empty/diagnostics-only/low-information 拒绝
  5. `_collect_policy_issues`: MemoryProjectionPolicy 的 section item cap 与 size cap

  验收成功后构造 `CompactAcceptedTruthV2`，绑定 immutable `source_boundary`、`represented_coverage` 和 `explicitly_dropped_coverage`。repair feedback 脱敏并受 32/240/8192 字符边界约束。

- **直接证据**: context_governance.py 从 170 行扩展到 807 行；`accept_compact_candidate_v2` 返回 `CompactAcceptedTruthV2 | CompactValidationReportV2` 二臂结果
- **影响**: 正面——消除了旧 quality checker 的语义所有权模糊（checker 同时做检查和返回结果，但不绑定 boundary）
- **严重程度**: 架构良好，无需修复

### 004-未通过-架构良好-Compaction root aggregation 与 multi-pass

- **入口/函数**: `_run_compaction_operation` (新增 root aggregation 路径)
- **文件(行号)**: dayu/host/compaction_operation.py
- **评估**: 新增 `_aggregate_pass_candidates` 把各 pass 的 accepted truth 机械合并为单一 candidate，然后用 root `accept_compact_candidate_v2` 重验。root 失败时 `_route_root_validation_report` 把 issue 路由到最后一个贡献 pass，该 pass 进入 repair。

  关键 invariant 正确：
  - pass_truths 全部 accepted 才进入 root validation（`_required_pass_truths` 抛出 RuntimeError）
  - root 验证失败不提交任何中间 truth
  - `_operation_pass_requests` 校验 pass boundaries 是 root 的 disjoint exact partition
  - `_failed_operation_result` 不泄漏 partial pass truth

- **直接证据**: compaction_operation.py 中 `accepted_pass_truths` list 在 pass 循环内累积，只有 root acceptance 成功后才写入 `CompactionOperationResult.accepted_truth`
- **影响**: 正面——支持 reactive multi-pass compaction 的正确语义
- **严重程度**: 架构良好，无需修复

### 005-未通过-架构良好-Interactive pending mutation identity

- **入口/函数**: `_InteractivePendingMutation.same_semantic_submission`
- **文件(行号)**: dayu/cli/session_execution.py
- **评估**: READ_ONLY rejection 后 `reject_submit_delivery()` 保留 exact editable draft；下次 Enter 时 `same_semantic_submission` 判断是否为同一语义，复用 `client_request_id` 避免重复创建 Run。

  `_is_read_only_mutation_rejection` 精确匹配 `HostSessionMutationErrorDetail` 的 `kind`/`reason`/`actual_mode`，不误判其它 `HostApiError`。

- **直接证据**: session_execution.py 中 `HostApiError` catch 块检查 `barrier.accepted_run_id is not None`（已 accepted 的 Run 不是 RO rejection）和 `_is_read_only_mutation_rejection(error)`（typed detail 精确匹配）
- **影响**: 正面——READ_ONLY rejection 后正确保留 REPL 并允许 fresh reattach
- **严重程度**: 架构良好，无需修复

### 006-未通过-架构良好-VT100 parser-based key monitor

- **入口/函数**: `TtyRunningKeyMonitor._read_loop`, `_feed_parser_resolution`, `_flush_parser_resolution`
- **文件(行号)**: dayu/cli/run_keys.py
- **评估**: 旧实现按单字节 `running_key_action_from_bytes` 映射，无法区分 ESC standalone 与 CSI/Alt/bracketed-paste 序列。新实现使用 `prompt_toolkit.input.vt100_parser.Vt100Parser` 做增量解析，配合 `ESCAPE_SEQUENCE_AMBIGUITY_SECONDS` (0.1s) 歧义窗口和 `time.monotonic()` deadline。

  关键改进：
  - `TCSANOW` 替代 `TCSAFLUSH` 保留 pre-accept 输入
  - `_READ_SIZE_BYTES` 从 1 增加到 1024 减少 syscall
  - `escape_deadline` 在收到 ESC 后设置，超时后 flush parser 产出 standalone Escape
  - `_classify_running_key_batch` 把 parser output 分类为 `CANCEL_RUN` / `TOGGLE_ACTIVITY` / `IGNORE`

- **直接证据**: run_keys.py 从 186 行扩展到完整 VT100 parser 集成；oracle `prompt.17-running-escape-sequence-disambiguation` 冻结 standalone ESC 取消、CSI/Alt/paste 不取消
- **影响**: 正面——解决了方向键、Home/Delete、Alt 序列误触发 cancel 的问题
- **严重程度**: 架构良好，无需修复

### 007-未通过-架构良好-Frozen oracle/scenario 一致性

- **入口/函数**: docs/cli_ci_oracles.json, docs/cli_ci_scenarios.json
- **评估**:
  - 新增 `prompt.17-running-escape-sequence-disambiguation` predicate，冻结 standalone ESC 取消、CSI/Alt/paste 不取消
  - 新增 `interactive.28-tool-registration-boundary`（不注册 start_fins_preprocess）
  - 新增 `interactive.29-compactor-output-accept-repair-fallback`（Host accept barrier 唯一 owner）
  - `runner_call_trigger_reason` 从 `context_compaction_completed` 改名为 `context_governance_resolved`
  - 6 个新 prompt scenarios（PS01-PS03, PX01-PX02）和 interactive coverage reconciliation
  - 用户裁决扩展到 #1-#47，日期 2026-08-02

  oracle 内部一致：predicate 的 expected/forbidden 与 scenario 的 `oracle_predicate_refs` 对齐；`applicable_from` 指向 `next-*-conformance-run-after-F01-F07`。

- **直接证据**: oracles.json 和 scenarios.json diff 中的 predicate/scenario 结构完整，无孤立引用
- **影响**: 正面——frozen oracle 正确反映 F01-F07 implementation findings
- **严重程度**: 通过

### 008-未通过-架构良好-Design doc owner 边界对齐

- **入口/函数**: docs/host/design.md §24.3
- **评估**: 设计文档从 vNext Compact I/O Contract 更新为 Compact v2 I/O Contract：
  - `ConversationCompactInputVNext` → `CompactInputV2`（schema + current_input + source_boundary）
  - `ConversationCompactOutputVNext` → `CompactCandidateV2`（schema + 7 个 typed section）
  - 明确 Context Governance 是唯一 accept owner
  - 明确 reactive multi-pass root revalidation 语义
  - 明确 Memory 只读已提交 canonical event 的 strict v2 projection

  代码实现与设计文档一致：`accept_compact_candidate_v2` 的五阶段验收、`CompactAcceptedTruthV2` 的 boundary binding、`build_compact_repair_feedback_v2` 的脱敏约束都与 design.md 描述对齐。

- **直接证据**: design.md diff 中 §24.3 的 schema 定义与 compaction.py / context_governance.py 的类型实现一一对应
- **影响**: 正面——设计文档正确反映实现
- **严重程度**: 通过

## Open Questions

无。

## Residual Risk

1. **Flaky test**: `test_active_cancel_emits_public_cancel_event` 在全量 suite 中偶发失败，需排查测试间状态泄漏。不影响生产代码。

2. **后续 conformance run**: oracle 和 scenario 的 `applicable_from` 指向 `next-*-conformance-run-after-F01-F07`，修复后需按正式 scenario 补跑并更新 evidence。

## Cross-Slice Integration Summary

| 集成面 | 评估 |
|---|---|
| CLI cancel ↔ Host terminal | `_ActiveTurnCloseout.wait_accepted_then_cancel` 正确处理 terminal-before-cancel 和 cancel-before-terminal 两种 ordering |
| CLI READ_ONLY ↔ Host attachment | `_InteractiveSessionAttachmentController` 实现 close-before-open fresh attach，`_is_read_only_mutation_rejection` 精确匹配 typed detail |
| CLI SIGINT chord ↔ composer revision | `_InteractiveSigintChordState.reconcile_input_revision` 在 signal 消费前按 composer revision 终结过期 chord |
| Host compaction accept ↔ Memory projection | `accept_compact_candidate_v2` 使用 `MemoryProjectionPolicy` 的同一 typed policy instance 做 section cap |
| Host compaction operation ↔ terminal | `_run_compaction_operation` 在 terminal 确定后不产生第二 terminal；`_failed_operation_result` 不泄漏 partial truth |
| Host dispatch ↔ compaction trigger | `context_compaction_completed` → `context_governance_resolved` 改名，dispatch 正确消费 |
| Frozen oracle ↔ implementation | predicate #17 (ESC disambiguation)、#28 (tool boundary)、#29 (accept repair) 与实现对齐 |

## Conclusion

未发现影响 correctness、stability 或 maintainability 的实质性 production code defects。1 个低严重度 flaky test 需要排查。CLI cancel/terminal 协调、Host compaction v2 accept barrier、VT100 parser key monitor、READ_ONLY rejection recovery 四个核心重构都经过充分的类型约束、状态机 invariant 和测试覆盖验证。

---

**READY-FOR-CONTROLLER-ADJUDICATION**
