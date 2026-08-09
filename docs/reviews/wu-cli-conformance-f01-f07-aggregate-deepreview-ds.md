# Aggregate Deepreview: WU-CLI-CONFORMANCE-F01-F07

## Scope

- **Mode**: aggregate deepreview (committed diff)
- **Branch**: `codex/interactive-oracle`
- **Range**: `cd6344c0` → `584ee394` (15 commits)
- **Base**: `cd6344c0`
- **Output file**: `docs/reviews/wu-cli-conformance-f01-f07-aggregate-deepreview-ds.md`
- **Review timestamp**: 2026-08-03T11:12:53+08:00
- **S8 immutable evidence bundle**:
  - Path: `/Users/leo/workspace/.dayu-cli-ci/pr190-wu-cli-conformance-f01-f07-s8-20260803T022326Z-9fec164715bc/bundle`
  - Digest: `7a80d9bcfb97bb7c8a80df8d2f10016d6f98577e01294f540a7ba2d9cea33b72` ✓ (verified)
- **Included scope**:
  - All 174 changed files, 102,270 insertions, 12,448 deletions
  - Production code: `dayu/cli/`, `dayu/host/`, `dayu/config/`, `dayu/service/`
  - Design docs: `docs/host/design.md`, `docs/engine/design.md`
  - Oracles: `docs/cli_ci_oracles.json`, `docs/cli_ci_scenarios.json`
  - Tests: `tests/cli/`, `tests/host/`, `tests/runtime/`, `tests/service/`, `tests/tools/`
  - Gateflow artifacts: `docs/workspace/PR190/wu-cli-conformance-f01-f07/`
  - Evidence bundle: full S8 integration evidence
- **Excluded scope**: none (complete diff coverage)
- **Parallel review coverage**:
  - CLI layer (composer, session_execution, run_keys, prompt, arg_parsing): primary reviewer direct read
  - Host compaction layer (context_governance, compaction, compaction_operation, compact_payload, compact_material, compact_pipeline, llm_compaction, context_events, run_input, memory): primary reviewer direct read
  - Tests/docs/contracts (design.md, oracles, test suites): primary reviewer direct read + subagent assist
- **S8 bundle evidence examined**: bundle-index.json, summary.md, summary.json, validation-results.json, run-manifest.json, F01-F07 owner matrices, F03/F07 scenario evidence, logs (full-pytest, full-pyright, affected-cli-coverage, frozen-hashes, target-diff-check)

## Commits in Scope

```
584ee394 docs(gateflow): accept F01-F07 full-real evidence
9fec1647 fix(cli): retain post-cancel chord ownership
63fca270 fix(cli): preserve interactive control intent
016d834a fix(cli): preserve pre-accept input ownership
eae09be9 test(integration): align conformance owner contracts
df99f858 fix(host): enforce compact acceptance truth
b8f87e3b refactor(host): rename context governance trigger
64c581f1 fix(config): remove preprocess from interactive tools
c556df2b fix(cli): retry read-only mutations on fresh attachments
25400fba fix(cli): preserve graceful input cancellation
fc1b4946 gateflow: correct S3 VT100 plan
16c6ddc8 fix(cli): update smoke runtime requests
e5b572d4 fix(cli): preserve explicit editor failures
a41526ec fix(cli): remove global config option
4a3dca64 gateflow: accept plan for WU-CLI-CONFORMANCE-F01-F07
```

## F01-F07 Cross-Slice Integration Summary

| Slice | Title | Scope | Evidence Status |
|-------|-------|-------|-----------------|
| F01 | 移除全局 --config 选项 | `dayu/cli/arg_parsing.py`, `dayu/service/entrypoint_runtime.py`, smoke scripts | PASS — S8 owner matrix confirms no residual --config references |
| F02 | 保留显式 editor 失败投影 | `dayu/cli/composer.py` (editor lifecycle, _EditorConfigurationError, _EditorActionError) | PASS — VISUAL/EDITOR validation, system editor fallback, failure matrix |
| F03 | 保留 pre-accept/active Escape 与 Ctrl+C 控制语义 | `dayu/cli/composer.py` (SUBMITTING phase, ESC ambiguity), `dayu/cli/run_keys.py` (Vt100Parser), `dayu/cli/session_execution.py` (_ActiveTurnCloseout, _InteractiveSigintChordState) | PASS — S8 scenario evidence covers CSI/Alt/paste/bracketed sequences |
| F04 | 保留 prompt/interactive 双向 label 连续性 | `dayu/cli/commands/prompt.py`, `dayu/cli/commands/session.py` | PASS — cross-entry label/session identity preserved |
| F05 | 保留 READ_ONLY 失败后的 fresh attach 重试 | `dayu/cli/session_execution.py` (_InteractiveSessionAttachmentController) | PASS — close-before-open refresh, stable client_request_id |
| F06 | 保留 post-compaction trigger 重命名 | `dayu/host/context_events.py`, `dayu/host/run_input.py`, `docs/host/design.md`, oracle | PASS — `context_compaction_completed` → `context_governance_resolved` consistent across all sites |
| F07 | 保留无效 compactor 响应拒绝与 repair/fallback | `dayu/host/context_governance.py` (accept_compact_candidate_v2), `dayu/host/compaction_operation.py` (reactive pass queue, root revalidation), `dayu/host/compact_payload.py` (v2 persistence) | PASS — accept barrier validates labels/coverage/duplicates/contradictions/caps/information; repair feedback bounded; root validation enforced |

## Evidence Bundle Verification

- **Digest match**: `7a80d9bcfb97bb7c8a80df8d2f10016d6f98577e01294f540a7ba2d9cea33b72` ✓
- **Verdict**: `PASS`
- **Full test suite**: 6603 passed, 10 skipped, 6 deselected ✓
- **Full pyright**: 0 errors, 0 warnings ✓
- **Owner matrices**: F01-F07 all verified ✓
- **3 historical failed bundles**: preserved and digest-verified ✓
- **F03 scenario evidence**: CSI Home/Delete, Alt sequences, bracketed paste, Ctrl+C chord, provider wait double Ctrl+C ✓
- **F07 scenario evidence**: success trigger followups (A2/A3), failure cap setup ✓

---

## Findings

### F-001 [中] CompactCandidateV2.intent_type 与 .reason 从闭集枚举退化为自由字符串，accept barrier 仅校验非空

- **入口/函数**: `accept_compact_candidate_v2` → `_collect_label_and_kind_issues`
- **文件(行号)**:
  - `dayu/host/compaction.py:1221` — `CompactForwardIntentV2.intent_type: str`（原为 `ForwardIntentTypeVNext` 枚举）
  - `dayu/host/compaction.py:1267` — `CompactReferenceContinuityV2.reason: str`（原为 `ReferenceContinuityReasonVNext` 枚举）
  - `dayu/host/compaction.py:1234` — 仅校验 `_require_non_empty(self.intent_type, ...)`
  - `dayu/host/compaction.py:1279` — 仅校验 `_require_non_empty(self.reason, ...)`
- **输入场景**: LLM compactor 返回 `intent_type: "invalid_category"` 或 `reason: "unknown_kind"`
- **实际分支**: 严格 JSON parser 接受任意非空字符串；accept barrier 的 label/source_kind 检查通过（intent_type/reason 不属于 label 校验路径）；覆盖分区、重复/矛盾、信息量、policy 上限检查均不关心这两个字段的语义值。
- **预期行为**: 按 original vNext 设计，`intent_type` 固定在 `{open_question, pending_clarification, pending_user_visible_task, next_step_note}`，`reason` 固定在 `{local_reference, ordinal_reference, ellipsis_recovery, recent_state}`；越界值被 JSON 层拒绝。
- **实际行为**: 任意非空字符串通过全部 accept barrier，进入 `CONTEXT_COMPACTED` → Memory projection → RunInput。下游 Memory 中的 `ForwardIntent.intent_type` 与 `ReferenceContinuityItem.reason` 同样是自由字符串，不做枚举校验。
- **直接证据**:
  - `ForwardIntentTypeVNext` 类在 `compaction.py` 中已删除（diff 行 `-ForwardIntentTypeVNext(StrEnum)`）
  - `ReferenceContinuityReasonVNext` 类同样已删除
  - `CompactForwardIntentV2.__post_init__` 行 1234：`_require_non_empty(self.intent_type, ...)` 仅校验非空
  - `CompactReferenceContinuityV2.__post_init__` 行 1279：`_require_non_empty(self.reason, ...)` 仅校验非空
  - `dayu/host/memory.py:592` — `ForwardIntent.intent_type: str`；行 608：`_require_non_empty(self.intent_type, "intent_type")`
  - `dayu/host/memory.py:403` — `ReferenceContinuityItem.reason: str`；行 421：`_require_non_empty(self.reason, "reason")`
- **影响**: LLM 可产出无意义的 intent_type/reason 值并通过全部 Host 验收与 Memory projection，污染 durable state。不影响 correctness（这些字段不驱动分支），但降低 Memory 语义质量，可能影响 compact 后模型的上下文理解。
- **建议改法和验证点**:
  - 选项 A（推荐）：在 `_collect_label_and_kind_issues` 或新增 `_collect_semantic_value_issues` 中，对 `intent_type` 与 `reason` 做允许值白名单校验；白名单与 design.md 24.3 的 LLM-facing schema 保持一致。
  - 选项 B：若设计上确认 v2 有意开放这两个字段，必须更新 design.md 24.3 明确说明 `intent_type` 和 `reason` 是自由文本，并记录决定理由；同时在 oracle `interactive.29` 的 expected 中明确"intent_type/reason 不做枚举约束"。
  - 验证点：构造 `intent_type="bogus"` 的 candidate，断言 accept barrier 拒绝或 design.md 明确允许。
- **修复风险（低）**: 若选 A，需同步更新 LLM-facing prompt 中的 `intent_type` / `reason` 字段说明，避免模型困惑。

### F-002 [低] `_aggregate_pass_candidates` 的 session_summary 机械拼接可能产生不连贯文本

- **入口/函数**: `_aggregate_pass_candidates` → `CompactSessionSummaryV2` 构造
- **文件(行号)**: `dayu/host/compaction_operation.py:1094–1102`
- **输入场景**: reactive pass queue 中 ≥2 个 pass 各自产出了非空 `session_summary`
- **实际分支**: 代码遍历所有 pass truth，收集非空 summary，以 `"\n".join(item.text for item in summaries)` 拼接为单个 summary text；source_labels 为各 pass summary labels 的并集。
- **预期行为**: 拼接后的 aggregate summary text 被传入 `accept_compact_candidate_v2` 做 root revalidation；char cap 校验在此处生效。
- **实际行为**: 拼接产生的新文本是两段独立 summary 的机械连接，可能读起来像"摘要A\n摘要B"而非一份连贯的 session summary。Char cap 可能通过（拼接后仍 ≤ cap），但语义质量下降。
- **直接证据**: `dayu/host/compaction_operation.py:1094–1102`：
  ```python
  summary = CompactSessionSummaryV2(
      text="\n".join(item.text for item in summaries),
      source_labels=tuple(label for label in root_input.source_labels if label in summary_labels),
  )
  ```
- **影响**: 仅发生在 reactive multi-pass 路径（当前仅用于测试/故障演练，生产路径为单 pass），不导致 correctness 失败。若未来 multi-pass 进入生产，可能污染 Memory 中的 session summary 可读性。
- **建议改法和验证点**:
  - 对 multi-pass summary 做最小语义处理：保留第一个 non-null summary 或要求 compactor 在 repair 阶段更新已有 summary 而非产出独立摘要。
  - 若当前设计确认接受机械拼接，在代码注释中记录此决定。
- **修复风险（低）**: 改动局限在 aggregate 函数内；root revalidation 的 char cap 校验不受影响。

### F-003 [低] VT100 parser 从主线程移至后台 reader 线程，增加线程内复杂度

- **入口/函数**: `TtyRunningKeyMonitor._read_loop`
- **文件(行号)**: `dayu/cli/run_keys.py:240–290`
- **输入场景**: 运行态 prompt/interactive 的 TTY 按键监控
- **实际分支**: 旧实现从 TTY 逐字节 `read(1)` 并用简单字节匹配判定 `RunningKeyAction`；新实现使用 `Vt100Parser` + `codecs.getincrementaldecoder("utf-8")` 在后台线程做完整 VT100 解析，含 0.1 秒 ESC 歧义期 deadline 逻辑。
- **预期行为**: 同旧实现——识别 standalone Escape 为 `CANCEL_RUN`，完整 ESC-prefixed sequence 不做取消。
- **实际行为**: 行为正确（S8 evidence 中 F03 场景全部 PASS），但 reader 线程现在承担 VT100 状态机、UTF-8 增量解码、ESC deadline 计时与 parser flush 等复杂逻辑。线程内 `select` + `os.read` + `parser.feed` + `parser.flush` 的组合增加了难以在单元测试中覆盖的交错时序。
- **直接证据**: `dayu/cli/run_keys.py:240–290` — `_read_loop` 中 `Vt100Parser`、`codecs.getincrementaldecoder`、`escape_deadline` 逻辑；行 500–540 — 测试 `test_reader_uses_conservative_deadline_and_readable_priority` 使用 `_ScriptedSelectClock` 做确定性注入，覆盖了核心时序。
- **影响**: 若 parser/decoder 在线程内抛出未捕获异常，reader 线程静默退出，后续 TTY 按键不再被监控（`RunningKeyAction` 队列停止投递）。外层 `wait_next()` 永久等待，需依赖外层 task 取消或 SIGINT 才能退出。测试中 `_ScriptedSelectClock` 覆盖了正常路径但未覆盖 parser 内部异常路径。
- **建议改法和验证点**:
  - 在 `_read_loop` 的 `while` 循环内增加 try/except，捕获 `Exception` 后记录日志并 break（或安全重启 reader）。
  - 增加测试：模拟 `Vt100Parser.feed()` 抛出异常，断言 monitor 不会永久阻塞外层 `wait_next()`。
- **修复风险（低）**: 仅增加防御性异常处理；不影响正常解析路径。

### F-004 [低] `_flush_submit_handoff_input` 的 application.is_done 检查与后续操作存在微小时间窗口

- **入口/函数**: `PromptToolkitInteractiveComposer._flush_submit_handoff_input`
- **文件(行号)**: `dayu/cli/composer.py:545–560`
- **输入场景**: submit handoff 后，前一 application 遗留的孤立 ESC 前缀需要被显式 flush
- **实际分支**: 在 `asyncio.sleep(ESCAPE_SEQUENCE_AMBIGUITY_SECONDS)` 后检查 `application.is_done`，若为 True 则 return；否则调用 `flush_keys()` + `feed_multiple()` + `process_keys()`。
- **预期行为**: 若 application 在 sleep 期间变为 done，安全跳过 flush。
- **实际行为**: sleep 返回后与 `is_done` 检查之间存在时间窗口：若 application 恰在 `is_done` 返回 False 后、`flush_keys()` 前变为 done，后续操作会作用于已完成的 application。prompt_toolkit 的 `flush_keys()` / `process_keys()` 在 done application 上应为 no-op，但该行为属于 prompt_toolkit 内部实现细节而非 Dayu 的公开契约。
- **直接证据**: `dayu/cli/composer.py:545–560`
- **影响**: 取决于 prompt_toolkit 版本；当前 3.0.52 的 `Application.is_done` 与 `flush_keys` / `process_keys` 交互安全（done application 的 key_processor 忽略输入）。升级 prompt_toolkit 后该假设可能被打破。
- **建议改法和验证点**:
  - 在 `flush_keys()` 前再次检查 `is_done`，或使用 try/except 包裹整个 flush 段。
  - 已有测试覆盖（`test_interactive_composer.py` 中的 handoff 场景），但未覆盖 application 恰好在 flush 前变为 done 的竞态。
- **修复风险（低）**: 增加一次 `is_done` 检查即可；不影响正常 handoff 路径。

---

## Oracle Integrity

### 已冻结 predicate 检查：全部 PASS

| Oracle | Predicates | 状态 | 变更 |
|--------|-----------|------|------|
| `cli.init.workspace-initialization` | 10 | 无变更 | — |
| `cli.prompt.core-execution` | 26 → 27 | 新增 `prompt.17`（Escape 序列歧义解析） | 仅追加 |
| `cli.interactive.core-execution` | 26 → 29 | 新增 `interactive.28`（工具注册边界）、`interactive.29`（compactor 输出验收） | 仅追加 |

关键检查：
- **无 predicate 弱化或删除**: 所有既有 predicate 的 `expected` / `forbidden` 未减少约束，`allowed_variants` 未放宽。
- **Frozen report 不变**: 三个 oracle 的 `observed_behavior.report_frozen` 均为 `true`，`supersedes` 均为 `null`。
- **trigger reason 重命名一致性**: `context_compaction_completed` → `context_governance_resolved` 同步出现在 `prompt` oracle（`scenario_refs` 中无直接引用）与 `interactive` oracle 的 `interactive.26` expected 文本中。
- **S8 supplemental evidence 链完整**: `prompt` 与 `interactive` oracle 均引用 `pr190-closure/` 下的 supplemental reports，digest 匹配。

### Scenario 注册

- `docs/cli_ci_scenarios.json`: 从 ~70,000 行增加到 70,126 行（+~560 行）。新增 `prompt` 与 `interactive` 的正式 scenario 条目。
- 604 formal scenarios + 96 parser/dynamic/shared-owner/static closure = 700 mandatory obligations。

---

## Design Doc vs Implementation

### `docs/host/design.md` Section 24.3: PASS

| Design Commit | Implementation | Status |
|--------------|----------------|--------|
| `CompactInputV2` 结构 (`schema`, `current_input`, `source_boundary`) | `dayu/host/compaction.py:1032–1084` | ✓ 精确匹配 |
| `CompactCandidateV2` 结构 (7 个顶层字段) | `dayu/host/compaction.py:1365–1402` | ✓ 精确匹配 |
| `CompactSourceBoundaryEntryV2` (label, kind, refs, text) | `dayu/host/compaction.py:619–658` | ✓ 精确匹配 |
| `CompactSessionSummaryV2` / `CompactEvidenceFactV2` / `CompactAnswerAnchorV2` / `CompactForwardIntentV2` / `CompactReferenceContinuityV2` / `CompactCandidateDiagnosticV2` / `CompactExplicitDropV2` | `dayu/host/compaction.py:1103–1350` | ✓ 精确匹配 |
| `exactly_dropped_sources` 闭集原因 `{superseded, redundant, out_of_scope, policy_limit}` | `CompactDropReasonV2` 枚举在 `dayu/host/compaction.py:162–169` | ✓ |
| Accept barrier: Coverage partition（represented ∪ dropped = boundary; disjoint） | `dayu/host/context_governance.py:398–432` (`_collect_coverage_issues`) | ✓ |
| Accept barrier: 重复/矛盾检测 | `dayu/host/context_governance.py:436–500` (`_collect_duplicate_and_contradiction_issues`) | ✓ |
| Accept barrier: 信息量检查（全空 / diagnostics-only / low-information） | `dayu/host/context_governance.py:504–530` (`_collect_information_issues`) | ✓ |
| Accept barrier: Policy caps（session summary char cap + 4 section item/size caps） | `dayu/host/context_governance.py:534–585` (`_collect_policy_issues`) | ✓ |
| Accept barrier: Source kind section 合法性 | `dayu/host/context_governance.py:312–370` (`_check_labels` with `allowed_kinds`) | ✓ |
| Reactive pass queue: 中��� pass 不提交，root revalidation | `dayu/host/compaction_operation.py:1060–1157` | ✓ |
| Repair feedback: bounded (32 issues, 240 char/issue, 8192 char total) | `dayu/host/compaction.py:1612–1661` (`CompactRepairFeedbackV2` + `MAX_*` constants) | ✓ |
| Memory projection: 同一 accepted truth 派生 | `dayu/host/memory.py:1236–1264` (CONTEXT_COMPACTED 路径) | ✓ |
| Memory policy: committed candidate 重验 | `dayu/host/memory.py:1648–1709` (`_validate_committed_candidate_policy`) | ✓ |
| Late/stale completion: terminal 已确定后不得产生第二 terminal | `dayu/host/compaction_operation.py` 中的 `_run_compaction_operation` + `dayu/host/engine_ingest.py` 中的 `begin_compaction_terminal_commit_in_transaction` | ✓ |

### `docs/host/design.md` Section 24 其他变更: PASS

| 变更 | 位置 | 一致性 |
|------|------|--------|
| trigger reason 重命名 `context_compaction_completed` → `context_governance_resolved` | design.md §24, `dayu/host/context_events.py`, `dayu/host/run_input.py` | ✓ 全部同源 |
| LLM-facing 禁止项 `ConversationCompactOutputVNext` → `CompactCandidateV2` | design.md §24, `dayu/host/run_input.py:311` | ✓ |
| answer anchor 扁平化：移除 `AnswerAnchorChild`，改为 `title + detail` | design.md §24.3, `dayu/host/compaction.py:1168–1215` | ✓ |

---

## Semantic Ownership Drift 检查

逐项扫描结果：

| 检查项 | 状态 | 证据 |
|--------|------|------|
| Memory 不再做 item-level budget truncation（原会丢弃超 cap 的单个 fact 并写 diagnostic） | PASS — 语义收束到 accept barrier | `dayu/host/memory.py:1236–1264` 移除 per-item cap 检查；`dayu/host/memory.py:1648–1709` 新增 committed policy 重验 |
| `ForwardIntentTypeVNext` / `ReferenceContinuityReasonVNext` 枚举移除 | OBSERVATION — 见 F-001 | 自由字符串扩大输入面 |
| `AnswerAnchorChild` 移除，anchor 扁平化为 `title + detail` | PASS | `dayu/host/compaction.py:1168–1215`；Memory projection 同步简化 |
| `evidence_kind` 不再由 LLM 输出，改为 Host 按 support labels 所属 material section 派生 | PASS — Host 拥有 evidence kind | design.md §24.3 明确说明；`dayu/host/compaction.py` 中 `evidence_facts` 不再携带 `evidence_kind` 字段 |
| `current_input_anchor` → `CompactCurrentInputV2` (source_ref + readable_text) | PASS — current input 不可引用 | `dayu/host/compaction.py:588–614`；`source_label` 不再暴露给 candidate |
| `CompactInstructionVNext` 移除 | PASS — instruction 合并到 repair feedback | 不再需要独立的 instruction bag |
| `source_boundary` 新增为 committed payload 字段 | PASS — 覆盖分区可追溯 | `dayu/host/compact_payload.py:202–249` (`_parse_source_boundary`) |
| `represented_coverage` / `explicitly_dropped_coverage` 新增为 committed payload 字段 | PASS — 覆盖分区持久化 | `dayu/host/compact_payload.py:251–310` |
| `context_governance_resolved` trigger reason 改名 | PASS — 精确 success/failure 仍由 CONTEXT_COMPACTED/CONTEXT_COMPACTION_FAILED 拥有 | `dayu/host/context_events.py`；`dayu/host/run_input.py:337` |

**无 semantic ownership drift 发现。** 所有 business fact 均有唯一清晰 owner；未出现下游 fallback、特例、loose parsing 或测试固化补偿上游 contract 缺陷的模式。

---

## Adversarial Failure/Recovery/Late-Result/Terminal Races 检查

| 场景 | 状态 | 证据 |
|------|------|------|
| **Compaction terminal double-write** | PASS | `begin_compaction_terminal_commit_in_transaction` 在写事务内先读后写；SQLite write lock 保证序列化；同一 transaction 内的 permit check 是唯一线性化点 |
| **Late/stale compactor completion after terminal** | PASS | `_run_compaction_operation` 行 851–870：cancellation token 检查后、attempt 执行前，`attempt_cancellation_token` 可被外部取消；`engine_ingest.py:2837–2849`：已存在 terminal 的 operation 被 `CompactionTerminalClosed` 拒绝 |
| **同一 operation 的第二个 CONTEXT_COMPACTION_FAILED** | PASS | 同 terminal double-write guard；permit 已消耗后再次进入 produce 不可写 |
| **Memory projection after CONTEXT_COMPACTED**: current input 误入 compacted coverage | PASS | `dayu/host/compact_payload.py:236–240`：`_validate_committed_coverage` 断言 `current_input_ref` 不在 `compacted_source_refs` 中 |
| **Reactive pass queue 中间 truth 泄漏** | PASS | `_run_compaction_operation` 行 1042–1050：中间 pass truth 只写入内存 `accepted_pass_truths` 列表；行 1052–1062：pass 失败返回 `accepted_truth=None`；root revalidation 失败同样走 `_failed_operation_result` 清零 |
| **interactive SIGINT chord 与 submit handoff 竞态** | PASS | `_InteractiveSigintChordState.reconcile_input_revision` 按 composer revision 清除过期 chord；`pending_submit_sigint_count` 在 current=None 时把 SIGINT 推迟到 active turn 创建后消费 |
| **interactive READ_ONLY 拒绝后 attachment refresh 竞态** | PASS | `_InteractiveSessionAttachmentController.attachment_for_mutation` 先 close 旧 attachment（`asyncio.shield` 保护）再 open 新 attachment；refresh_required 标记在 close/open 失败后保留 |
| **prompt Escape key 在 submit acceptance 前到达** | PASS | `RunningKeyMonitor` 在 `execute_prompt_on_session` 外层创建并传入；`tty.setcbreak(fd, when=termios.TCSANOW)` 不清空已到达的 pre-accept 输入 |
| **interactive composer SUBMITTING phase 与 SIGINT 的 Enter chord 绑定** | PASS | `composer.has_pending_submit_intent()` 在 Enter 按下时由 `_record_submit_intent` 同步设置；`pending_submit_sigint_count` 在 `current is None` 分支消费 |

**未发现 terminal race、late-result 污染 durable state 或 recovery 路径产生孤儿状态的证据。**

---

## Test Coverage

### S8 Evidence: PASS

- 6603 passed, 10 skipped, 6 deselected
- Affected CLI coverage rerun: PASS
- Owner matrix reruns (F01-F07): all PASS
- Full pyright: 0 errors, 0 warnings

### Coverage Gaps (非阻塞)

| 测试域 | 覆盖情况 | Gap |
|--------|---------|-----|
| `test_run_keys.py` (815 行, 16 tests) | VT100 parser resolution、ESC deadline、reader thread lifecycle、pre-start Escape/CSI/Alt/paste 保留 | 未覆盖：`Vt100Parser.feed()` 在 reader 线程内抛出异常后 monitor 阻塞行为 |
| `test_interactive_composer.py` (1459 行, ~25 tests) | Submit lifecycle、ESC ambiguity、Ctrl+C phase matrix、editor 配置失败矩阵、PTY 真实终端解析 | 未覆盖：`_flush_submit_handoff_input` 中 `is_done` 检查与 flush 之间的竞态窗口 |
| `test_compaction_contract.py` (815 行) | Accept barrier 的 label/coverage/duplicate/cap 检查 | 覆盖充分 |
| `test_compaction_operation.py` (1908 行) | Attempt loop、pass queue、root revalidation、repair feedback | 覆盖充分 |
| `test_memory_projection.py` (877 行) | CONTEXT_COMPACTED 后的 Memory replacement、committed policy 重验 | 覆盖充分 |
| `test_compact_material.py` (538 行) | Material builder v2 input construction | 覆盖充分 |
| `test_public_compact_smoke.py` (502 行) | Public compact smoke tests | 覆盖充分 |
| `tests/tools/test_combined_tools_acceptance.py` (45 行, 新文件) | 工具注册边界验证 | 覆盖充分（验证 `start_fins_preprocess` 不在 interactive tool set） |

---

## Architecture Boundaries

### PASS checks:

- **`dayu.runtime` 不 import `dayu.engine` / `dayu.host` / `dayu.service` / `dayu.ui` / `dayu.fins`**: 新增 `dayu.runtime.diagnostic_text` (redact/truncate helpers) 被 `dayu.host.context_governance` 使用，符合层中立公共基础设施定位。✓
- **Host → CLI 反向依赖**: 无。`dayu.host` 模块不 import `dayu.cli`。✓
- **Compaction contract 归属**: 类型定义在 `dayu.host.compaction`（Host-owned）；accept barrier 在 `dayu.host.context_governance`（Host-owned）；persistence 在 `dayu.host.compact_payload` 与 `dayu.host.context_events`（Host-owned）。Memory 只消费 canonical events。✓
- **Config → Host**: `dayu/config/prompts/manifests/interactive.json` 移除 `fins-preprocess` tool tag，由 Service assembly 消费；Host 不直接读 manifest。✓
- **Protocol/interface 依赖**: Compactor 通过 `CompactorProposalPreparedCompactor` Protocol 调用，不依赖具体 LLM runner 实现。✓

---

## Overcoupling 检查

| 检查项 | 状态 |
|--------|------|
| Compact v2 类型独立于 vNext 旧类型 | PASS — 所有 vNext 类型已删除（无 `*VNext` 类残留），v2 类型使用独立 field name（`evidence_facts` 而非 `evidence_backed_facts`，`text` 而非 `summary_text`） |
| 测试不依赖旧 schema 字段 | PASS — fake/mock/fixture 已更新到 v2 field names；旧字段名 `evidence_backed_facts`、`reference_continuity_items` 等已从全部测试中移除 |
| README 更新只反映实际变更 | PASS — `tests/README.md` 新增 5 行（test 数量更新）；`dayu/config/README.md` 更新 6 行（interactive manifest 工具列表）；`dayu/host/README.md` 更新 8 行（compaction contract 描述） |
| 兼容性 shim | PASS — 无 `*VNext` 兼容 re-export、wrapper 或 fallback |

---

## Open Questions

1. **intent_type/reason 开放字符串的设计意图** — `ForwardIntentTypeVNext` 与 `ReferenceContinuityReasonVNext` 枚举被移除，替换为自由字符串。这是 v2 有意放大 compactor 表达自由度，还是实施过程中遗漏的约束？若为前者，建议在 design.md 中记录决策理由；若为后者，见 F-001。

2. **`prompt.17` oracle predicate 编号不连续** — `prompt.17` 出现在 `prompt.22` 之后（oracle JSON 末尾）。这是否暗示还有其他待编号 predicate 尚未写入？

---

## Residual Risk

1. **VT100 parser 线程异常静默退出** — 后台 reader 线程内 `Vt100Parser` / decoder 抛异常会导致按键监控永久阻塞。当前测试用例使用 `_ScriptedSelectClock` 覆盖正常路径，未覆盖异常路径。风险：低（生产环境中 prompt_toolkit 的 parser 在合法 TTY 输入下不抛异常；只有终端输出畸形控制序列时可能触发）。

2. **Multi-pass reactive compaction 的 session summary 拼接** — 当前只在测试中使用 multi-pass；若未来进入生产，机械拼接的 summary 可能降低 Memory 质量。风险：低（当前生产路径为单 pass）。

3. **prompt_toolkit 版本升级风险** — `_flush_submit_handoff_input` 依赖 `Application.is_done` 后 `flush_keys` / `process_keys` 的安全行为。若 prompt_toolkit 未来版本改变此行为，需回归测试。风险：低（prompt_toolkit 是稳定依赖，且有 PTY 集成测试覆盖）。

4. **CLI coverage** — S8 evidence 确认 affected CLI coverage rerun 通过，但未提供具体行覆盖率百分比。本次 diff 涉及 `session_execution.py` 的 ~1000 行新增代码（`_ActiveTurnCloseout`、`_InteractiveSigintChordState`、`_InteractiveSessionAttachmentController`、`_InteractivePendingMutation`），均有测试覆盖，但 `_drive_interactive_tty_repl` 的复杂事件循环（~400 行）主要通过集成测试覆盖，单元测试集中在 `test_interactive_composer.py` 与 `test_interactive_command.py`。

---

## READY-FOR-CONTROLLER-ADJUDICATION

本 review 产出 actionable findings 4 项（中 1 项、低 3 项），无严重发现。S8 immutable evidence bundle digest 已验证一致。全部 F01-F07 cross-slice 集成通过。Design doc §24.3 与实现精确对齐。Oracle 仅追加，无 predicate 弱化或删除。所有 terminal/late-result/recovery race 检查通过。无 semantic ownership drift 发现。无过度耦合。

Controller 应逐项裁决 F-001 至 F-004（accept / reject-with-reason / defer-with-owner / needs-more-evidence），并决定是否需要 block merge。
