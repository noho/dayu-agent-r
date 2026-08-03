# PR Review: wu-cli-conformance-f01-f07

## Scope

- Mode: PR Review
- PR: [#190](https://github.com/noho/dayu-agent-r/pull/190)
- Title: `fix(cli): close interactive conformance gaps`
- Author: noho (Leo Liu)
- Base: `main`
- Head: `codex/interactive-oracle` (remote head `c69445c2`)
- Review date: 2026-08-03
- Output file: `docs/reviews/wu-cli-conformance-f01-f07-pr-review-mimo.md`
- Included scope: 45 production files (`dayu/`), all test files, all docs, all review artifacts
- Excluded scope: 70k+ lines of `docs/cli_ci_scenarios.json` (frozen scenario registry, reviewed structurally)
- Parallel review coverage: 6 subagents covering CLI session/composer, Host compaction, Host context/dispatch, Host memory/recovery, Engine contracts/config, PR metadata/prior reviews

## PR Facts

- 33 commits, 322 files changed, +133,484 / -15,476 lines
- State: OPEN/DRAFT, mergeable
- GitHub checks: 0 reported (no CI configured)
- Prior review history: S1–S6 dual review + fix + re-review; aggregate deepreview 4 fixed / 19 rejected; PR review 1 accepted / 3 rejected + fix + re-review PASS
- Final closeout verdict: `FINAL CLOSEOUT PASS`

## Findings

### 1-未修复-严重-_canonical_candidate 未对 explicitly_dropped_sources 排序导致持久化 artifact 不可恢复

- **入口/函数**: `_canonical_candidate` 和 `accept_compact_candidate_v2`
- **文件(行号)**: `dayu/host/context_governance.py` L669, `dayu/host/compact_payload.py` L375
- **输入场景**: LLM 返回的 compaction candidate 中 `explicitly_dropped_sources` 顺序与 `source_boundary` 不一致时
- **实际分支**: `_canonical_candidate` 对 `session_summary`、`evidence_facts`、`answer_anchors`、`forward_intents`、`reference_continuity`、`diagnostics` 的 `source_labels` 全部通过 `_ordered_labels` 按 boundary 顺序排序；唯独 `explicitly_dropped_sources` 原样传递
- **预期行为**: 所有 label tuple 都应按 boundary 顺序 canonicalize，确保持久化 artifact 的确定性
- **实际行为**: `accept_compact_candidate_v2` 构造 `CompactAcceptedTruthV2` 时，`explicitly_dropped_coverage.drops` 按 boundary 顺序排列；但 `candidate.explicitly_dropped_sources` 保持 LLM 原始顺序。re-parse 验证 `compact_payload.py` L375 比较两者：
  ```python
  if semantics.explicitly_dropped_coverage.drops != semantics.accepted_candidate.explicitly_dropped_sources:
      raise ValueError("dropped coverage must equal accepted candidate drops")
  ```
  当 LLM 返回的 drop 顺序与 boundary 不一致时，此比较永远失败，导致已持久化的 compact artifact 永久不可读取
- **直接证据**: `_canonical_candidate` L669 `explicitly_dropped_sources=candidate.explicitly_dropped_sources` 未排序；同函数中其它 6 个字段全部使用 `_ordered_labels(item.source_labels, boundary_order)` 排序
- **影响**: 已持久化的 compact artifact 在 re-parse 时永久损坏；Session 的 conversation memory 不可恢复
- **建议改法和验证点**:
  ```python
  # _canonical_candidate 中，与其它字段一致地排序 drops
  explicitly_dropped_sources=tuple(
      next(d for d in candidate.explicitly_dropped_sources if d.source_label == label)
      for label in sorted(
          (d.source_label for d in candidate.explicitly_dropped_sources),
          key=boundary_order.__getitem__,
      )
  )
  ```
  验证：构造 LLM 返回非 boundary 顺序 drops 的测试，确认 re-parse 不抛 ValueError。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 严重

### 2-未修复-高-_close_managed_attachment 缺少 try/finally 导致 attachment 资源泄漏

- **入口/函数**: `_PublicHostHandle._close_managed_attachment`
- **文件(行号)**: `dayu/host/open_host.py` L1367-1379
- **输入场景**: `_ManagedHostSessionAttachment.aclose()` 被调用时（interactive session 关闭、Host 关闭）
- **实际分支**: `_cancel_and_join_delayed_attachment_recovery` 先执行，成功后才执行 `attachment.aclose()`
- **预期行为**: 无论 delayed task 取消是否成功，attachment 的 `aclose()` 都必须被调用以释放 native SQLite mutex
- **实际行为**: 若 `_cancel_and_join_delayed_attachment_recovery` 抛出非 CancelledError 异常（例如 delayed task 的 `_report_delayed_attachment_recovery_fatal` 本身失败），`attachment.aclose()` 永远不会被调用，导致 RW attachment 持有的 native mutex 泄漏
- **直接证据**:
  ```python
  async def _close_managed_attachment(self, attachment):
      await self._cancel_and_join_delayed_attachment_recovery(attachment.session_id)
      await attachment.aclose()  # 若上面抛异常则永不执行
  ```
  `_cancel_and_join_delayed_attachment_recovery` 内部 `await asyncio.shield(task)` 会重新抛出 task 的异常。task 的 `except Exception` handler 调用 `_report_delayed_attachment_recovery_fatal`，若 `report_fatal` 本身失败则异常向上传播。
- **影响**: Session 的 native SQLite RW mutex 永久泄漏；后续对该 Session 的所有 attach 操作都会阻塞或失败
- **建议改法和验证点**:
  ```python
  async def _close_managed_attachment(self, attachment):
      try:
          await self._cancel_and_join_delayed_attachment_recovery(attachment.session_id)
      finally:
          await attachment.aclose()
  ```
  验证：构造 `_cancel_and_join_delayed_attachment_recovery` 失败的场景，确认 `aclose()` 仍被调用。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 高

### 3-未修复-低-CompactorProposalManifestReference 语义边界迁移

- **入口/函数**: `CompactorProposalManifestReference` 定义从 `dayu/host/compaction_operation.py` 迁移到 `dayu/host/context_events.py`
- **文件(行号)**: `dayu/host/context_events.py:812`, `dayu/host/compaction_operation.py` 原定义已删除
- **输入场景**: 所有 compaction operation 的 manifest reference 消费
- **实际分支**: 该类型同时被 `dispatch.py`、`engine_ingest.py`、`compaction_operation.py` 导入，全部从新位置 `context_events` 导入
- **预期行为**: 语义 owner 迁移应有明确的架构理由
- **实际行为**: `CompactorProposalManifestReference` 是 compaction operation 的 durable binding 引用，其语义更接近 compaction operation 而非 context events。当前迁移使得 `context_events.py` 承担了 compaction-specific 类型定义，扩大了该模块职责
- **直接证据**: `context_events.py` L812 定义了完整的 `CompactorProposalManifestReference`，包含 `compaction_operation_id`、`compaction_attempt_number`、`compactor_engine_run_id` 等 compaction-specific 字段
- **影响**: 维护性边界模糊；不影响正确性
- **建议改法和验证点**: 考虑将其移回 `compaction_operation.py` 或放入独立的 `compaction_contract.py`；或在 `context_events.py` docstring 中说明为何该类型属于 context events 边界
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 4-未修复-中-_report_delayed_attachment_recovery_fatal 双 shield 丢失原始异常

- **入口/函数**: `_run_delayed_attachment_recovery` 的 `except Exception` handler 和 `_report_delayed_attachment_recovery_fatal`
- **文件(行号)**: `dayu/host/open_host.py` L1326, L1339-1365
- **输入场景**: delayed attachment recovery task 的 actor submit/scan 失败
- **实际分支**: `except Exception as exc` 调用 `_report_delayed_attachment_recovery_fatal(exc)`；若 `report_fatal` 本身抛出非 CancelledError 异常，该异常替换原始 `exc`
- **预期行为**: 原始失败原因应始终可追溯
- **实际行为**: `_report_delayed_attachment_recovery_fatal` 内部的 `report_fatal` 若失败，其异常会替换原始异常向上传播。同时 `except asyncio.CancelledError` 中的 double `asyncio.shield(fatal_task)` 在理论上存在无限重试风险（虽然 `report_fatal` 预期快速完成）
- **直接证据**: `open_host.py` L1326 `await self._report_delayed_attachment_recovery_fatal(exc)` 无 try/except 保护；L1363-1364 的 double shield 无退出条件
- **影响**: 原始失败原因丢失，排障困难；不影响正确性（fatal 已上报 health gate）
- **建议改法和验证点**: 在 `except Exception` handler 中用独立 try/except 包裹 fatal report，确保原始异常始终被 re-raise
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### 5-未修复-低-intent_type/reason 枚举松弛为 str

- **入口/函数**: `ReadableForwardIntentVNext` 和 `ReadableReferenceContinuityItemVNext` 的 `intent_type` 和 `reason` 字段
- **文件(行号)**: `dayu/host/compaction.py` 中 `ReadableForwardIntentVNext.intent_type` 从 `ForwardIntentTypeVNext` 枚举改为 `str`；`ReadableReferenceContinuityItemVNext.reason` 从 `ReferenceContinuityReasonVNext` 枚举改为 `str`
- **输入场景**: LLM 返回的 compaction candidate 解析
- **实际分支**: v2 schema 设计选择松弛枚举约束
- **预期行为**: 类型系统应在构造时拦截非法值
- **实际行为**: `intent_type` 和 `reason` 现在是自由文本，非法值只能在 context governance validation 阶段被发现，而非在 parse 阶段
- **直接证据**: `compaction.py` L794 `intent_type: str`（原为 `ForwardIntentTypeVNext`），L838 `reason: str`（原为 `ReferenceContinuityReasonVNext`）
- **影响**: parse 阶段的类型安全降低；validation 阶段仍会拦截；符合 v2 设计意图（LLM 可能产生 schema 未预见的枚举值）
- **建议改法和验证点**: 当前设计是 v2 的显式选择，允许 LLM 使用非预定义值；若要恢复类型安全，可在 `_parse_forward_intent_v2` 和 `_parse_reference_continuity_v2` 中增加已知值校验但仍允许未知值通过
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 6-未修复-低-context_governance 模块职责扩大

- **入口/函数**: `context_governance.py` 从 ~170 行增长到 ~807 行
- **文件(行号)**: `dayu/host/context_governance.py`
- **输入场景**: compaction candidate acceptance
- **实际分支**: 模块现在同时承担 acceptance validation、repair feedback 构造、canonical normalization、coverage/duplicate/contradiction/information/policy 检查
- **预期行为**: 单一模块职责清晰
- **实际行为**: 虽然模块仍然只做 "验收" 不做 "写入"，但内部职责从简单 label 检查扩展为完整的 semantic validation pipeline
- **直接证据**: 新增函数 `accept_compact_candidate_v2`、`build_compact_repair_feedback_v2`、`_canonical_candidate`、`_represented_sections` 等 15+ 个内部函数
- **影响**: 模块内聚但仍较大；所有函数都服务于同一个 acceptance 语义
- **建议改法和验证点**: 当前实现是合理的——所有 validation 都服务于同一个 "accept or reject" 决策；若未来继续增长可考虑拆分 validation dimensions 为独立模块
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Architecture Assessment

### Semantic Ownership — PASS

逐项检查 F01-F13 对应的 semantic owner：

| 语义 | Owner | 验证 |
|---|---|---|
| prompt/interactive 参数 | `arg_parsing.py` | `--config` 和 interactive `--ticker` 已完全移除，无残留引用 |
| label → durable slot | `session_identity.py` | 统一 `cli.agent.<label>` namespace，旧 `cli.prompt.*`/`cli.interactive.*` 不读取 |
| TTY draft/key sequence | `composer.py` | 唯一 stdin owner，完整 ESC sequence 解析 |
| interactive Run/cancel/exit | `session_execution.py` | `_ActiveTurnCloseout` + `_InteractiveSigintChordState` |
| whole-stdin draft | CLI binary stdin reader | non-TTY 从首 byte 到 EOF 单一 draft |
| orphan recovery | `recovery_process.py` + `open_host.py` | delayed rescan 由 attachment-owned task 执行 |
| compaction terminal | `compaction_terminal.py` | trigger-aware transaction-local guard |
| pre-start single-flight | `dispatch.py` `_PreStartGovernanceFlight` | per-Session sole flight |
| response identity | `runner_identity.py` `SuccessfulRunnerResponseIdentity` | Engine → Host 同源绑定 |
| compaction v2 I/O | `compaction.py` + `context_governance.py` | strict parser + deterministic acceptance |

### State Machine Review — PASS

- **Compaction terminal**: `OPEN → COMPACTED/FAILED`，single absorbing terminal，`INVALID_MULTIPLE` fail closed
- **Interactive SIGINT chord**: `NONE → CANCEL_REQUESTED → EXIT_AFTER_CANCEL`，monotonic per `input_revision`
- **Interactive session attachment**: `current → refresh_required → close → fresh attach`，幂等 close
- **Pre-start governance**: `signal → coalesce → sole flight → rerun bit`，不跨 Session 泄漏

### Boundary Review — PASS

- CLI 不读取 Host internals（`session_execution.py` 只使用 Host public API）
- Engine 不理解 Host compaction（`SuccessfulRunnerResponseIdentity` 是纯 Engine contract）
- Host 不暴露 compaction policy 给 Engine（`CompactionRequest` 只传 material）
- `dayu.runtime` 不 import 任何业务层

### Test Coverage — PASS

- affected CLI/Service: 1181 passed, 7 skipped
- affected Host: 775 passed
- full Engine/Host: 2957 passed, 1 skipped, 6 deselected
- recovery: 116 passed + real POSIX SIGKILL smoke
- aggregate fix: 185 passed, production coverage 86%/95%/84%
- SQLite two-writer competition: 10 consecutive passes
- pyright: 0 errors, 0 warnings, 0 informations

## Open Questions

无。

## Residual Risk

1. **G01-G07 未裁决**: 本 PR 不裁决或关闭 G01-G07（完整 CLI calibration）。下一阶段必须在 merge 后补跑。
2. **GitHub zero checks**: 没有 CI 配置，无法声称 CI pass。本地 evidence 已完整但不替代外部 CI。
3. **Phase 5 六个 race**: 在 clean base 上已复现并分类为 non-regression。
4. **renderer target pin**: 行为项 29 的真实 compactor identity evidence 需要 merge 后的 renderer target 才能进入正式 scenario。

## Prior Review Adjudication Verification

逐项确认已接受的 prior findings 均已正确关闭：

| Finding | Status | Evidence |
|---|---|---|
| AGG-A01 non-TTY SIGINT lifecycle | ✅ fixed | `_wait_interactive_batch_terminal_handling_sigint` 完整 barrier 逻辑 |
| AGG-A02 Ctrl+T exit intent | ✅ fixed | `TOGGLE_ACTIVITY` 只 toggle display，不写 exit_intent |
| AGG-A03 SQLite terminal competition | ✅ fixed | `BEGIN IMMEDIATE` barrier + trace callback proof |
| AGG-A04 validator owner message | ✅ fixed | `_validate_non_empty_text` 接受 `owner_name` 参数 |
| PR-A01 duplicate required-field owners | ✅ fixed | `CompactionOperationResult.required_*()` 方法 + callers 迁移 |

19 项 rejected findings 无一因新 diff 变为真实问题。

## Overall Verdict

**1 项严重 finding（持久化 artifact 排序缺陷）、1 项高严重程度 finding（attachment 资源泄漏）、1 项中等严重程度 finding（异常丢失）、3 项低严重程度维护性观察。** 严重 finding 是 `_canonical_candidate` 未对 `explicitly_dropped_sources` 按 boundary 顺序排序，当 LLM 返回非 boundary 顺序的 drops 时，re-parse 验证永远失败，导致已持久化的 compact artifact 永久不可恢复。高严重程度 finding 是 `_close_managed_attachment` 缺少 try/finally，可能导致 Session 的 native SQLite RW mutex 永久泄漏。两项修复风险均低。F01-F13 的 implementation、test coverage、prior review closure 和 design alignment 均已验证通过。

READY-FOR-CONTROLLER-ADJUDICATION
