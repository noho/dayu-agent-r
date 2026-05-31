# WU-AUDIT-01 Purge Audit Reconciliation Plan Review

- **Reviewed target**: `docs/host/wu-audit-01-purge-audit-reconciliation-plan.md`
- **Design source of truth**: `docs/host/design.md`
- **Control document**: `docs/host/host-core-followup-implementation-control.md`
- **Review date**: 2026-05-31
- **Review posture**: adversarial plan review, pre-implementation

## Review Scope

Review the WU-AUDIT-01 plan against these specific concerns raised by the user:

1. 是否仍有过度设计 (whether there is still over-engineering)
2. 是否真正只做必要 audit (whether it truly does only necessary audit)
3. 是否满足 `purge_started` 不表示完成 (started ≠ completed)
4. `purge_completed` 仅在 tombstone commit 后写入并引用 tombstone (completed only after tombstone commit, referencing tombstone)
5. SQLite 失败无 completed (no completed on SQLite failure)
6. 是否足够 code-generation-ready (whether it is sufficiently code-generation-ready)

## Assumptions Tested

1. **Plan correctly identifies root cause**: The current `_insert_tombstone_and_idempotency` calls `audit_recorder.record_purge_tombstone_audit()` BEFORE inserting the tombstone. If SQLite insert fails after the JSONL write, the audit falsely claims purge completed. Verified via code: `dayu/host/durable/purge.py:1486-1501`.

2. **Plan respects design constraints**: Audit is projection/sink, not Host truth (design.md line 1634). SQLite tombstone is the durable truth source. Verified: plan Section 2.4 explicitly states "真正完成真源仍是 SQLite tombstone；JSONL 不参与 recovery / resume / memory / durable truth".

3. **Plan respects the "command path doesn't write audit" constraint**: Design.md line 1646 says "Host command path 不直接写 audit log file". The plan's approach of having the command path write started/completed/failed directly to JSONL extends an existing pattern (`_PurgeAuditJsonlRecorder` in command.py). This tension is inherent to purge being the only destructive operation — the EventLog rows are being deleted, so the projection-based audit path cannot capture purge audit. The plan does not explicitly acknowledge this tension.

4. **Plan respects non-goals**: No general audit query/analysis API, no complex diagnostic framework, no durable schema changes. Verified against all listed non-goals.

5. **Slice independence**: Three slices can be implemented and verified independently. Slice 1 (durable layer) doesn't depend on Slice 2 (audit contracts). Slice 3 (orchestration) depends on both. This sequencing is correct.

## Findings

### 01-未修复-中-retry 后 completed append 的检测机制未具体化

- **位置**: Section 4 事务与失败顺序，步骤 4；Section 6 Slice 3
- **问题类型**: 不可直接实施
- **当前写法**: "completed append 失败：tombstone 已提交，purge 已完成；返回 retryable `HostApiError(INTERNAL_ERROR, ...)`，同 `client_request_id` retry 应 replay tombstone 并重试 completed append。" Slice 3 验收信号："completed append 失败后同 key retry 可补写 completed。"
- **反例/失败场景**: 同 `client_request_id` retry 时，`purge_session_durable` 检测到已有 tombstone，走 replay 路径返回 `idempotent_replay=True`。此时 orchestration 层（`_PurgeSessionOperation` 或 `purge_session` 函数）需要判断：是 replay 且 completed 未写 → 补写 completed；还是 replay 且 completed 已写 → 直接返回成功。plan 没有指定这个判断机制的具体实现方式。
- **为什么有问题**: implementation agent 需要自行决定：(a) 在 retry 时扫描 JSONL 检查 completed 是否已存在；(b) 无条件尝试写 completed，依赖 JSONL 幂等机制去重；(c) 在 durable 层返回额外信号告知调用方是否需要补写。这三种实现方式的行为和复杂度不同，plan 没有收敛到其中一种。
- **直接证据**: 当前 `PurgeSessionDeleteResult` 只有 `idempotent_replay: bool` 字段，无法区分 "replay 但 completed 可能未写" 与 "fresh purge 刚完成需要写 completed"。command.py 的 `_PurgeSessionOperation.__call__` 返回后由 `purge_session` 构造 `PurgeSessionResult`，其间没有 completed append 的逻辑空间。
- **影响**: 实施 Agent 可能选择一个实现方式但在 edge case 下（completed 写入中途崩溃）行为不正确；或引入不必要的 JSONL 扫描逻辑。
- **建议改法和验证点**: 在 plan Section 4 中明确 retry 时补写 completed 的具体机制。推荐方案：在 `purge_session` 函数中，当 `result.idempotent_replay is True` 时，尝试通过 JSONL 幂等机制写 completed（利用 `(line_kind=purge_completed, purge_attempt_ref)` 作为 source key）；如果 completed 已存在（同 digest），幂等跳过；如果 completed 不存在，补写。这样不需要额外的状态检测逻辑，利用 JSONL 自身幂等性。验证点：测试模拟 completed append 失败后 retry，断言 retry 成功后 JSONL 有且仅有一条 completed line。
- **修复风险（低）**: 只需要在 plan 文档中补充具体机制描述，不涉及设计变更。
- **严重程度（中）**: 不修复会导致 implementation agent 自行决策，可能在 edge case 下行为不一致。

### 02-未修复-低-command path 直接写 audit 与设计真源的 tension 未显式声明

- **位置**: Section 5.2 对 `dayu/host/audit.py` 的改动；整体方案
- **问题类型**: 架构边界
- **当前写法**: plan 在 command path（`dayu/host/command.py`）通过新增的 `append_purge_started/completed/failed_audit_record` 函数直接写 audit JSONL，但不讨论这与设计真源 line 1646 "Host command path 不直接写 audit log file" 的 tension。
- **反例/失败场景**: 如果将来有其他 destructive 操作（如 `clear_session`），可能按此先例继续在 command path 直接写 audit，逐渐侵蚀设计真源的架构约束。plan 不声明此 tension 和 scope boundary，可能导致后续 work unit 误用此模式。
- **为什么有问题**: 不声明特殊性会让 implementation agent 和 reviewer 无法判断这是否是设计真源的例外，以及例外的边界在哪。实际上当前代码已有 `_PurgeAuditJsonlRecorder` 做同样的事，plan 是在已有例外上扩展。显式声明可以防止模式扩散。
- **直接证据**: 设计真源 line 1646；当前 command.py line 832-853 `_PurgeAuditJsonlRecorder`；plan Section 5.3 允许改动 `_PurgeAuditJsonlRecorder`。
- **影响**: 低 — 当前实现不会出错，但架构文档的一致性受损，后续开发者可能误读。
- **建议改法和验证点**: 在 plan 或设计真源中增加一条说明：purge 是唯一 destructive 操作，其 audit 必须在 command path 直接写，因为 EventLog 在 purge 事务中被删除，projection-based audit 无法捕获 purge completion。这不是通用模式。实现阶段可在代码 docstring 中注明 "purge 专用"。
- **修复风险（低）**: 补充文档声明即可，不涉及代码变更。
- **严重程度（低）**: 不影响实施正确性，但影响长期架构一致性。

### 03-未修复-低-`purge_failed` line 与 started line 在重试时的幂等交互未完全覆盖

- **位置**: Section 2.5 `purge_failed` 语义；Section 4 步骤 3
- **问题类型**: 状态机漏洞
- **当前写法**: "SQLite 失败后 best-effort append failed"。Section 7.3 测试 "允许有 `purge_failed`，但不强制依赖复杂诊断"。
- **反例/失败场景**: 假设 purge 流程：started append 成功 → SQLite transaction 失败（例如 precondition check failed）→ best-effort write failed 成功 → 调用方 retry（同 key）。retry 时：(a) SQLite 层没有 tombstone 也没有 idempotency record（因为上次事务回滚），所以 `record_or_read_purge_idempotency` 返回 `PROCEED_TO_PURGE`；(b) started append 尝试写同 `(purge_started, purge_attempt_ref)` — 如果 started line 的 digest 在两次尝试间相同（所有字段确定），JSONL 幂等跳过，这是正确的。但如果 started line 因某些字段变化（例如 `request_context` 在两次调用间略有不同）产生不同 digest，会触发 source key conflict。plan 没有分析这个场景。
- **为什么有问题**: 虽然在实际使用中 request_context 通常不变（同 client_request_id），但 plan 的 contract 没有保证 started line 的所有字段在 retry 时完全 deterministic。实现时可能引入非确定性字段（如内部 timestamp 或状态快照），导致幂等冲突。
- **直接证据**: plan Section 2.2 共同字段不包含时间戳，但 Section 2.3 started 的必要字段也不包含。当前计划下 started line digest 应该确定，但没有显式约束说明"started line 所有字段在重试时必须确定"。
- **影响**: 低 — 当前字段设计下不太可能发生，但如果 implementation agent 自行在 started line 中添加非确定字段，会在 retry 时产生 source key conflict。
- **建议改法和验证点**: 在 plan Section 2.3 增加一条约束："`purge_started` 的所有字段在同 `client_request_id` 重试时必须完全确定性（不含 timestamp、随机值等），以保证 digest 不变、JSONL 幂等跳过生效。" 测试 7.3 可以追加一个场景：同 key retry 后 started line 不重复（只存在一条 started）。
- **修复风险（低）**: 只是补充约束声明，不改变设计。
- **严重程度（低）**: 实施阶段大概率不会引入非确定字段，但显式约束可以防止。

### 04-未修复-低-`PurgeTombstoneRow.audit_record_ref/digest` docstring 更新范围不够明确

- **位置**: Section 3 Durable Schema Decision；Section 5.1
- **问题类型**: 不可直接实施
- **当前写法**: "实现阶段必须更新 docstring，说明该字段是 destructive attempt audit ref，不再表示 completed line。"
- **反例/失败场景**: `PurgeTombstoneRow` 的 docstring 在 `dayu/host/durable/purge.py:250-251` 当前写 "audit_record_ref: purge audit record 引用" / "audit_record_digest: purge audit record digest"。除此之外，可能还有 tombstone DDL 注释、schema 模块中的字段说明、以及引用这些字段的测试断言需要更新。plan 只说"更新相关中文 docstring"，不够具体。
- **为什么有问题**: implementation agent 可能只更新了 `PurgeTombstoneRow` docstring 而遗漏其他位置。review 时也没有明确的检查清单。
- **直接证据**: `dayu/host/durable/purge.py` line 269-270 `PurgeTombstoneRow` docstring；`dayu/host/durable/schema.py` 中 DDL 注释可能也需要更新。
- **影响**: 低 — 遗漏的 docstring 不改变行为，但会造成文档与代码不一致。
- **建议改法和验证点**: plan Section 5.1 中增加显式的 docstring 更新清单：`PurgeTombstoneRow.audit_record_ref/digest`、`_insert_tombstone_and_idempotency` docstring、tombstone DDL comment（如果 schema.py 中有注释）。同时更新 `tests/host/test_purge_session.py` 中引用 `audit_record_ref` 的断言注释。
- **修复风险（低）**: 补充清单即可。
- **严重程度（低）**: 不影响代码正确性。

## Open Questions

1. **completed line 是否需要 `deleted_counts_digest`、`precondition_digest`、`deleted_refs_digest`**: plan Section 2.4 在 `purge_completed` 中包含这三个 tombstone 字段。这些字段可以直接从 committed tombstone row 读取。好处是 audit line 可以独立自证（不需要读 SQLite 就能验证 tombstone 一致性），代价是 completed line 字段较多。考虑到这些字段在 tombstone 中已经存在，且 plan 的目标只是修正语义（started ≠ completed），这有轻微过度倾向于"让 JSONL 自包含"的风险。但这是合理的审计最佳实践，不构成真正的过度设计。**建议保持**。

2. **`purge_attempt_ref` 格式 `purge-attempt:{tombstone_id}` 是否必要**: plan Section 2.2 定义了 `purge_attempt_ref`。实质上 `tombstone_id` 已经是全局唯一的（基于 session_id + client_request_id + semantic_digest）。加前缀主要是为了 human-readable 区分。这个字段的必要性偏低但无害。**建议保持**。

## Residual Risks

1. **completed append 失败后，retry 由调用方负责**: plan 依赖调用方在收到 retryable error 后同 key 重试。如果调用方不重试，tombstone 存在但 JSONL 只有 started 没有 completed。helper 函数不会误判（只有 completed 返回 True），但 audit 流水不完整。这是设计上可接受的行为——tombstone 才是 truth。风险追踪：已在 plan Section 12 中声明，无需额外追踪。

2. **`purge_failed` 是 best-effort**: 如果 failed append 也失败，JSONL 只有 started line。helper 不会误判为 completed，但诊断信息缺失。这是 plan 明确的设计选择。风险追踪：已在 plan Section 12 中声明。

3. **tombstone 的 `audit_record_ref/digest` 指向 started line**: 语义变更。实现需要更新所有读取这些字段的代码路径和文档。风险追踪：plan Section 3 和 12 已声明，实现阶段需确保无遗漏。

## Final Plan Review Conclusion

**PASS-WITH-RISKS**

The plan correctly addresses the root cause (completion semantics written to JSONL before SQLite commit). The three-line-kind design (started/completed/failed) is minimal and justified. The plan satisfies all five user-specified criteria:

- **started ≠ completed**: `purge_started` has `source_eventlog_facts_purged: false`; the marks helper only recognizes `purge_completed` with `source_eventlog_facts_purged is True`. PASS.
- **completed only after tombstone commit**: Ordering in Section 4: started → SQLite commit → completed. `purge_completed` references `purge_tombstone_ref` and `purge_tombstone_digest` from committed tombstone. PASS.
- **SQLite failure → no completed**: Transaction rollback, best-effort `purge_failed`, no `purge_completed` written. Test 7.3 verifies this with trigger-based failure injection. PASS.
- **No over-engineering**: No general audit query/analysis API, no durable schema changes, no complex diagnostic framework, `purge_failed` is best-effort only. PASS.
- **Code-generation-ready**: Files, allowed/prohibited changes, three independent slices with verification commands are clearly specified. PASS with one caveat (Finding 01).

The four findings are all low-to-medium severity and addressable via plan text clarification — none require architectural redesign. Finding 01 (retry orchestration mechanism not concretized) is the most material; the recommended fix is to specify that retry should unconditionally attempt completed append, relying on JSONL idempotency.

建议在进入 implementation 前修复 Finding 01，其余三个 findings 可在 implementation 阶段通过 docstring 更新和代码注释解决。
