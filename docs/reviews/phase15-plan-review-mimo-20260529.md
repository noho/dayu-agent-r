# Phase 15 Plan Review — AgentMiMo

## Reviewer

AgentMiMo (plan review specialist)。

## Review Scope

- Plan artifact: `docs/host/phase15-retention-purge-production-hardening-plan.md`
- Design source: `docs/host/design.md`
- Control doc: `docs/host/implementation-control.md`
- Design discussion artifact: `docs/reviews/phase15-design-discussion-controller-20260529.md`
- Schema source: `dayu/host/durable/schema.py` (HOST_SCHEMA_VERSION = 13)

## Review Lens

以 design doc 的设计目标和 Phase 15 scope 为最高依据，严格审查 plan 是否 handoff-ready / code-generation-ready。重点：动机、scope、public API 不变性、分层架构、FK 安全删除顺序、idempotency 设计、tombstone 设计、schema v14 fresh DB、slice 粒度、tests 覆盖。

## Conclusion

**PASS（附 3 个中等 finding、2 个低 severity finding）**

Plan 总体 handoff-ready。动机成立、scope 清晰、slice 切分合理、public API 不变性有明确约束、tests 覆盖范围充分。发现 5 个 non-blocking 问题，均不影响 plan 可执行性，但建议在 S2 实现前修复其中 3 个中等 finding 以避免实现返工。

---

## Findings

### 1-未修复-中-S2 delete order 缺少 FK 依赖图显式验证

- Plan位置: Slice P15-S2 "Delete in FK-safe order" steps 1-14
- 问题类型: 实现精确性 / 可验证性
- 计划当前写法: 以编号列表给出删除顺序，未附带 FK 依赖图或显式验证说明
- 为什么有问题: FK 在 `transaction.py:364` 显式启用（`PRAGMA foreign_keys=ON`），违反 FK 约束会导致 transaction 失败。plan 的删除顺序经审查实际是正确的（所有 event_log 直接依赖表在 step 13 之前删除），但 plan 未向 implementation agent 传递 FK 依赖图，导致实现者需要自行从 schema 推导，增加出错风险
- 直接证据:
  - `schema.py:186`: `payload_descriptors` FK -> `host_sqlite_payloads`
  - `schema.py:228`: `event_log` FK -> `payload_descriptors`
  - `schema.py:255-256`: `idempotency_records` FK -> `event_log(created_event_id/sequence)`
  - `schema.py:326-328`: `host_session_slots` FK -> `host_sessions`, `event_log`
  - `schema.py:371-381`: `host_runs` FK -> `host_sessions`, `event_log` (6 columns)
  - `schema.py:445-449`: `host_attempts` FK -> `host_runs`, `event_log`
  - `schema.py:495-504`: `host_attempt_dispatch_records` FK -> `host_runs`, `host_attempts`, `event_log`
  - `schema.py:624-631`: `host_wait_records` FK -> `host_sessions`, `host_runs`, `host_attempts`, `event_log`
  - `schema.py:664`: `host_projection_checkpoints` FK -> `event_log`
  - `schema.py:684`: `host_projection_failures` FK -> `event_log`
  - `schema.py:703-706`: `host_run_results` FK -> `host_runs`, `host_sessions`, `event_log`
  - `schema.py:733-736`: `host_session_timeline_items` FK -> `host_sessions`, `host_runs`, `event_log`
  - `schema.py:759`: `host_memory_snapshots` FK -> `event_log`
  - `schema.py:805-808`: `host_memory_items` FK -> `host_memory_snapshots` (CASCADE), `event_log`
  - `schema.py:843-844`: `host_memory_diagnostics` FK -> `host_memory_snapshots` (CASCADE)
  - `schema.py:854-855`: `host_audit_sink_markers` FK -> `event_log`
  - `schema.py:892-893`: `host_tool_trace_hot` FK -> `event_log`
  - `schema.py:931-932`: `host_outbox_terminal_items` FK -> `event_log`
  - `transaction.py:364`: `connection.execute("PRAGMA foreign_keys=ON")`
- 影响: 实现者可能误解删除顺序，导致 FK violation 和 transaction rollback
- 建议改法和验证点:
  - 在 S2 删除顺序前增加 FK 依赖图摘要（ASCII 或表格形式），列出每张表的 FK 依赖目标
  - 在 S2 的 Expected assertions 中增加 "DELETE order does not violate any FK constraint" 断言
  - 验证点：实现后在测试中开启 `PRAGMA foreign_keys=ON` 并执行完整 purge，确认无 FK violation
- 修复风险（低/中/高）: 低
- 严重程度（低/中/高/严重）: 中

### 2-未修复-中-S2 idempotency replay 路径 tombstone-only 场景未覆盖

- Plan位置: Slice P15-S1 "Exact allowed changes" -> "record_or_read_purge_idempotency(...)"
- 问题类型: 边界覆盖缺失
- 计划当前写法: S1 定义了 `record_or_read_purge_idempotency(...)` helper，S2 定义了 idempotency replay 路径。但只覆盖了 tombstone 存在且 idempotency 存在、tombstone 不存在但 idempotency 存在、两者都不存在三种场景
- 为什么有问题: 存在 tombstone 存在但 idempotency record 不存在的合法场景（idempotency_records 行可独立于 tombstone 被清理或因 DB 手动干预缺失）。此场景未定义返回行为
- 直接证据:
  - Plan line 187-195: idempotency replay 路径描述覆盖了 tombstone 存在 + idempotency 存在、tombstone 不存在 + idempotency 存在、两者都不存在
  - 未覆盖: tombstone 存在 + idempotency 不存在
  - `schema.py:243-261`: `idempotency_records` 是独立表，无 CASCADE 到 tombstone
- 影响: 实现者需要自行决定此场景行为，可能导致不一致的错误码或意外创建新 idempotency record
- 建议改法和验证点:
  - 在 S1 的 `record_or_read_purge_idempotency(...)` 或 S2 的 idempotency replay 路径中补充：tombstone 存在 + idempotency 不存在时，返回 tombstone 对应的 replay result（tombstone 是更强的事实源）
  - 补充测试断言：构造 tombstone 存在但 idempotency 缺失的 DB 状态，验证 purge_session 返回正确 replay result
- 修复风险（低/中/高）: 低
- 严重程度（低/中/高/严重）: 中

### 3-未修复-中-S4 audit append 失败策略存在内部矛盾

- Plan位置: Slice P15-S4 "Error handling"
- 问题类型: 设计歧义
- 计划当前写法:
  > Audit append failure must not silently report purge fully compliant. Either return retryable internal failure before public success, or persist tombstone with explicit audit pending diagnostic and make implementation report justify. Preferred release-blocking behavior: fail command before returning success if purge audit line cannot be appended.
- 为什么有问题: 给出了两个选项（fail command vs persist with diagnostic）并指定 preferred，但未明确裁决。implementation agent 需要在两个路径间选择，可能导致不同 slice 实现者做出不同决策
- 直接证据:
  - Plan line 545-546: "Either return retryable internal failure before public success, or persist tombstone with explicit audit pending diagnostic"
  - Plan line 546: "Preferred release-blocking behavior: fail command before returning success"
  - Design doc line 387: "purge 必须写入 purge tombstone audit record"（"必须"是强约束）
- 影响: 实现歧义可能导致 audit retention invariant 在某些 edge case 被违反
- 建议改法和验证点:
  - 明确裁决为 "fail command before returning success"（与 design doc 的"必须"一致）
  - 删除 "or persist tombstone with explicit audit pending diagnostic" 选项
  - 补充测试断言：mock audit append 失败时，purge_session 返回 INTERNAL_ERROR 且 tombstone 不写入（或 tombstone 写入但 public result 报告失败）
  - 若选择保留双路径，必须在 plan 中明确每条路径的触发条件和测试覆盖
- 修复风险（低/中/高）: 低
- 严重程度（低/中/高/严重）: 中

### 4-未修复-低-precondition_digest 计算方法未指定

- Plan位置: "Tombstone Design" -> "Minimum fields" -> "precondition_digest"
- 问题类型: 实现细节缺失
- 计划当前写法:
  > `precondition_digest`：基于 purge 前 Session status、Run ids/statuses、terminal event refs、wait record statuses、max event sequence 等 stable facts
- 为什么有问题: "等 stable facts" 暗示字段列表不完整。implementation agent 需要自行决定哪些字段纳入 digest 输入，不同实现可能导致 digest 不可重现
- 直接证据:
  - Plan line 221: "等 stable facts" 未穷举
  - `sha256_digest_json` 的输入需要精确、稳定、可重现
- 影响: 低。precondition_digest 主要用于 tombstone 完整性校验，不影响 idempotency replay（replay 用 semantic_request_digest）
- 建议改法和验证点:
  - 穷举 precondition_digest 的输入字段列表，或明确引用一个将定义此 helper 的 slice
  - 验证点：同一 precondition 输入产生相同 digest
- 修复风险（低/中/高）: 低
- 严重程度（低/中/高/严重）: 低

### 5-未修复-低-S5 multiprocess 测试 scope 需明确

- Plan位置: Slice P15-S5 "Exact allowed changes" -> "Add local multiprocess test"
- 问题类型: 测试 scope 歧义
- 计划当前写法:
  > Add local multiprocess test where one process/handle purges closed terminal Session and another handle cannot read/recover/watch it
- 为什么有问题: "another handle" 未明确是同一进程的另一个 Host handle 还是不同进程。真正的 multiprocess 测试需要独立进程，实现复杂度显著高于同进程多 handle 测试
- 直接证据:
  - Plan line 599: "one process/handle" 和 "another handle" 措辞模糊
  - `test_recovery_multiprocess.py` 和 `test_admission_multiprocess.py` 使用 `multiprocessing` 模块
- 影响: 低。若实现为同进程多 handle 测试，仍能验证 SQLite 并发行为；但不能验证文件锁 / 进程隔离场景
- 建议改法和验证点:
  - 明确为 "同进程多 handle + 不同 connection" 测试（与现有 multiprocess 测试模式一致）
  - 或明确为 "不同进程" 测试并指定进程间通信方式
  - 验证点：一个 handle purge 后，另一个 handle 的 get_session/get_run 返回 NOT_FOUND
- 修复风险（低/中/高）: 低
- 严重程度（低/中/高/严重）: 低

---

## Non-blocking Observations

1. **Slice 粒度合理**: 6 个 slice 从 schema 到 command 到 audit 到 projection 到 docs，每 slice 可独立 review/commit，符合 plan review gate 要求。

2. **Public API 不变性约束明确**: plan 多处强调不修改 `PurgeSessionRequest`、`PurgeSessionResult`、`Host` methods、`OpenHostOptions`、`watch_session_events`，与 design doc 和 implementation-control 一致。

3. **Schema fresh DB 设计清晰**: `HOST_SCHEMA_VERSION` 13->14 bump、`host_purge_tombstones` 新表、不写旧库兼容迁移，符合 CLAUDE.md schema 变更约束。

4. **Tombstone 不参与 governance truth**: plan 明确 tombstone 不参与 resume/retry/replay/memory/RunInputBuilder/Run 状态迁移，与 design doc 一致。

5. **idempotency_records 复用设计合理**: `scope_kind='purge_session'`、`created_event_id/sequence=NULL` 利用 SQLite NULL FK 豁免机制，避免 schema 变更。但 plan 未显式提到 SQLite NULL FK 豪免这一关键实现细节，建议在 S1 注释中补充。

6. **Audit JSONL append-only invariant 保护**: plan 多处强调不删除/截断/重写既有 JSONL，只追加 purge tombstone audit line，与 design doc 一致。

7. **Projection 不作为 truth**: plan 明确 "projection cleanup 只能删除或 reset 派生表，不得用 projection checkpoint 证明 purge 前置条件"，与架构硬约束一致。

8. **Implementation-control 建议 slice 切分 vs plan 实际切分**: implementation-control 建议 4 个 slice（delete matrix + tombstone audit, projection rebuild, multiprocess/recovery, docs），plan 实际切为 6 个 slice（更细粒度），这是改进而非偏离。

9. **Residual risk 分类完整**: plan 区分了 release-blocking、covered by later slice、follow-up owner，与 implementation-control 要求一致。

---

## Residual Risks

1. **FK 依赖图复杂度**: 22 张表的 FK 网络复杂，S2 实现时需要仔细验证删除顺序。建议 S2 实现后增加 FK violation 专项测试。

2. **Audit JSONL 文件 I/O 失败**: plan 选择 "fail command before success" 策略，但文件 I/O 失败（磁盘满、权限）在 production 中可能发生。需要确保失败路径不留下 orphan tombstone。

3. **Cold artifact 文件清理**: plan 明确 commit 后执行文件删除，失败只记录 residual cleanup risk。这是合理的，但需要确保 diagnostic 足够详细以便后续清理。

4. **Projection checkpoint reset 范围**: plan 说 "only for consumers whose rows are rebuildable from remaining EventLog"，但未定义如何判断 "rebuildable"。实现者需要理解每个 projection consumer 的 rebuild 能力。
