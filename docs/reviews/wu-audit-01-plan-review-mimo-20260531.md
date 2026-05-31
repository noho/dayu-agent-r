# WU-AUDIT-01 Plan Review

## Review Target

- **Plan**: `docs/host/wu-audit-01-purge-audit-reconciliation-plan.md`
- **Design source**: `docs/host/design.md`
- **Control doc**: `docs/host/host-core-followup-implementation-control.md`
- **Review focus**: 过度设计、必要 audit 最小化、purge_started/completed/failed 语义、SQLite 失败路径、code-generation-ready 程度

## Assumptions Tested

1. `purge_started` 不表示 purge 完成。
2. `purge_completed` 仅在 SQLite tombstone commit 后写入，并引用 tombstone id/digest。
3. SQLite 失败路径不会产生 `purge_completed`。
4. 不引入过度设计。
5. plan 足够 code-generation-ready。

## Code Facts Verified

- `dayu/host/durable/purge.py:1461-1537` (`_insert_tombstone_and_idempotency`)：当前在 SQLite transaction 内调用 `request.audit_recorder.record_purge_tombstone_audit()`，将 completion audit 写入前置到 commit 前。这是 root cause。
- `dayu/host/audit.py:374-443` (`build_purge_tombstone_audit_json_line` / `append_purge_tombstone_audit_record`)：当前 `source_eventlog_facts_purged` 固定为 `True`，line_kind 固定为 `purge_tombstone`。
- `dayu/host/command.py:731-853` (`purge_session` / `_PurgeSessionOperation` / `_PurgeAuditJsonlRecorder`)：当前整个 purge 在单个 write transaction 内完成，audit recorder 作为 Protocol port 传入 durable helper。
- `tests/host/test_purge_session.py:2749-2770`：已有 audit failure 回滚 tombstone 测试。
- `tests/host/test_purge_session.py:2773-2817`：已有 public purge 成功后 JSONL 包含 purge line 的测试。
- `docs/host/design.md:385`：设计真源已明确定义 `purge_started` / `purge_completed` / `purge_failed` 三类 audit line 语义。

## Findings

### 01-未修复-中-重放路径未处理 completed 补写

- **位置**: Section 4 (Transaction And Failure Ordering)、Section 5.3 (command.py)、Section 6 Slice 3
- **问题类型**: 状态机漏洞 / 不可直接实施
- **当前写法**: Section 4 step 4 写道"completed append 失败时...同 `client_request_id` retry 应 replay tombstone 并重试 completed append"。Section 5.3 允许 command.py "completed append 失败时返回 retryable error；同 key retry replay tombstone 后重试 completed append"。但 Section 6 Slice 3 的验收只写"成功路径 JSONL 至少包含 started 与 completed"、"completed 引用 committed tombstone id/digest"、"SQLite 失败路径没有 completed"，没有覆盖重放路径。
- **反例/失败场景**: 首次 purge：SQLite commit 成功 → `purge_completed` append 失败 → 返回 retryable error。此时 JSONL 只有 `purge_started`。调用方用同 `client_request_id` 重试 → 进入 `purge_session_durable` → `record_or_read_purge_idempotency` 检测到 tombstone 已存在 → 返回 `REPLAY_TOMBSTONE` → 当前代码直接返回 `PurgeSessionDeleteResult(idempotent_replay=True)`。`purge_session` command 构造 `PurgeSessionResult(purged=True, ...)` 返回。**`purge_completed` 永远不会被写入**，尽管 purge 实际已完成（tombstone 已提交）。
- **为什么有问题**: plan 的核心语义是"只有 `purge_completed` 可以表达 purge complete"。如果重放路径不补写 `purge_completed`，则成功 purge 后 JSONL 中只有 `purge_started`，`audit_json_line_marks_purged_source_eventlog_facts` 返回 `False`，与 tombstone 存在矛盾。这是 plan 声称要修复的同一类 orphan 问题的另一种表现形式。
- **直接证据**: `dayu/host/command.py:780-785` 当前 purge_session 在 `purge_session_durable` 返回后直接构造 result，不检查是否需要补写 completed。`dayu/host/durable/purge.py:803-811` `_result_for_replay_decision` 返回 replay result 时不做任何 audit 写入。
- **影响**: 实施 agent 无法从 plan 中得知重放路径需要补写 `purge_completed`。实施后，completed append 失败 + 重试的路径会留下 orphan audit 状态，与 plan 设计目标矛盾。
- **建议改法和验证点**:
  1. Section 4 step 4 补充：replay path 也需要检查 `purge_completed` 是否存在，不存在则补写。
  2. Section 5.3 明确：`purge_session` 在 replay 返回后，若 JSONL 中无 `purge_completed`，需补写并返回结果。
  3. Section 6 Slice 3 验收补充："replay 路径若无 `purge_completed`，补写后返回"。
  4. Section 7 补充测试：首次 purge 成功但 completed append 失败 → 同 key retry → 断言 JSONL 最终包含 `purge_completed`。
- **修复风险（低/中/高）**: 中
- **严重程度（低/中/高/严重）**: 中

### 02-未修复-低-build_purge_tombstone_digest helper 规格不足

- **位置**: Section 3 (Durable Schema Decision)
- **问题类型**: 不可直接实施
- **当前写法**: "需要新增最小 helper：`build_purge_tombstone_digest(tombstone: PurgeTombstoneRow) -> str`。`build_purge_tombstone_digest` 只对 tombstone row 已持久字段计算 digest，不包含 completed audit line，避免循环依赖。"
- **反例/失败场景**: 实施 agent 不确定"已持久字段"具体包含哪些字段、是否包含 `audit_record_ref/digest`（此时指向 started line）、是否包含 `purged_at`、是否包含 `request_context_json`。不同理解会导致 `purge_completed` 中的 `purge_tombstone_digest` 与独立读取 tombstone 计算的 digest 不一致。
- **为什么有问题**: `purge_completed` 必须引用 `purge_tombstone_digest`，且该 digest 必须能从已提交 tombstone row 独立复算。如果 helper 的字段集不明确，completed line 的 digest 与后续验证逻辑可能不一致。
- **直接证据**: `dayu/host/durable/purge.py:2474-2519` (`_validate_tombstone`) 已有 tombstone 全字段校验逻辑，可参考确定 digest 字段集。`dayu/host/durable/codec.py` 提供 `sha256_digest_json`。
- **影响**: 实施 agent 需要自行决定 digest 字段集，可能导致实现与 plan 意图不一致或后续 review 返工。
- **建议改法和验证点**: Section 3 明确 `build_purge_tombstone_digest` 的字段集，例如"对 `PurgeTombstoneRow` 除 `audit_record_ref` 和 `audit_record_digest` 外的所有持久字段计算 canonical JSON digest"，或"对全部持久字段计算 digest"。附带验证点：`purge_completed` 中的 `purge_tombstone_digest` 等于独立 `build_purge_tombstone_digest(tombstone)` 的结果。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 03-未修复-低-新 request dataclass 字段未显式列出

- **位置**: Section 5.2 (audit.py)
- **问题类型**: 不可直接实施
- **当前写法**: "新增最小 request/result dataclass：`PurgeStartedAuditRecordRequest`、`PurgeCompletedAuditRecordRequest`、`PurgeFailedAuditRecordRequest`、`PurgeAuditRecordResult`"。Section 2.3-2.5 列出了三类 line 的字段，但未明确哪些字段进入 request dataclass、哪些由 builder 内部派生。
- **反例/失败场景**: 实施 agent 需要从 Section 2.2-2.5 的字段列表推导每个 request dataclass 的字段集。例如 `purge_attempt_ref` 在 Section 2.2 是共同字段，但 `PurgeStartedAuditRecordRequest` 是否需要 `tombstone_id`（用于构造 `purge_attempt_ref`）还是直接传 `purge_attempt_ref`？`schema_version`、`line_kind`、`audit_record_ref`、`line_digest` 是由 builder 内部生成还是由 request 携带？
- **为什么有问题**: 增加实施 agent 的推导负担，可能导致 request 字段设计与 plan 意图不一致。
- **直接证据**: `dayu/host/durable/purge.py:305-335` (`PurgeTombstoneAuditRecordRequest`) 已有完整的 request dataclass 示例，字段集明确。新 request dataclass 应参照此模式。
- **影响**: 低。实施 agent 可从现有代码和 Section 2 推导，但显式定义更安全。
- **建议改法和验证点**: Section 5.2 补充每个 request dataclass 的字段列表，区分"request 携带"和"builder 内部生成"。至少说明 `schema_version`、`line_kind`、`audit_record_ref`、`line_digest` 由 builder 生成，`purge_attempt_ref` 由 request 携带 `tombstone_id` 后由 builder 构造。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Architecture Boundary Review

Plan 正确地将 audit 写入从 durable transaction 中分离：
- `purge.py` 不再 import `audit.py`（Section 5.1 禁止改动）。
- `command.py` 负责编排 started → SQLite transaction → completed/failed（Section 5.3）。
- `PurgeSessionDeleteRequest` 改为接收 started audit ref/digest，不再持有 audit recorder port（Section 5.1）。

这是正确的分层方向：durable 层不依赖 audit writer，command 层负责跨介质编排。

## Overengineering Review

- `purge_failed` 是 best-effort 诊断 line，plan 明确不为它引入查询框架或状态机（Section 2.5）。这是合理的。
- 三个 request dataclass（started/completed/failed）对三类 line kind，不是过度设计——每类 line 的可用数据不同（started 没有 deleted_counts，completed 有，failed 有 failure_stage）。
- 不新增通用审计查询或分析 API（Section 5.2 禁止改动）。正确。
- 不修改 `host_purge_tombstones` schema（Section 3）。正确——tombstone 已经是完成真源。

**结论**：plan 没有过度设计。每个新增项都有直接必要性。

## Optimal-Solution Review

当前方案是 credible alternatives 中最实际的路径：
- 替代方案 A（把 audit 和 SQLite 放在同一 durable transaction）：不可行，因为 JSONL 不是 SQLite。
- 替代方案 B（只修 `audit_json_line_marks_purged_source_eventlog_facts` 识别逻辑，不改 audit line 结构）：不能解决 root cause——JSONL 中已有错误的 completion 语义。
- 替代方案 C（引入通用审计管道）：过度设计，plan 正确拒绝。

当前方案直接修复 root cause（完成语义过早写入 JSONL），最小必要改动。

## Overcoupling Review

Plan 没有引入过度耦合：
- `purge.py` 和 `audit.py` 之间的依赖被削弱（purge 不再 import audit）。
- `command.py` 作为编排层连接两者，这是正确的依赖方向。
- 新 helper（`build_purge_tombstone_id`、`build_purge_attempt_ref`、`build_purge_tombstone_digest`）放在 `purge.py`，因为它们操作 durable 数据类型。
- JSONL 幂等 source key 使用 `(line_kind, purge_attempt_ref)`，不引入跨层状态。

## Open Questions

无。

## Residual Risks

| Risk | Owner | Tracking |
|---|---|---|
| completed append 失败 + 重试路径的 `purge_completed` 补写 | WU-AUDIT-01 implementation | finding 01，需在 plan 中补充 |
| `build_purge_tombstone_digest` 字段集需明确 | WU-AUDIT-01 implementation | finding 02，需在 plan 中补充 |

## Final Plan Review Conclusion

**pass-with-risks**

Plan 的动机成立、架构方向正确、没有过度设计、满足 purge_started/completed/failed 核心语义要求。有 1 个中等 severity finding（重放路径未处理 completed 补写）和 2 个低 severity findings（helper 规格和 dataclass 字段未显式定义）。中等 finding 需要在 plan 中补充后方可进入 implementation；低 findings 实施 agent 可从现有代码推导，但显式定义更安全。

Plan 在修复 finding 01 后可达到 code-generation-ready。
