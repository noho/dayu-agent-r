# WU-AUDIT-01 Aggregate Deep Review

## Scope

- Mode: current changes
- Branch: feat/host-purge-audit-reconciliation
- Base: main
- Output file: docs/reviews/wu-audit-01-aggregate-deepreview-ds-20260531.md
- Included scope:
  - Plan artifact: docs/host/wu-audit-01-purge-audit-reconciliation-plan.md
  - Control doc: docs/host/host-core-followup-implementation-control.md (rename + WU-AUDIT-01 section)
  - Implementation: dayu/host/audit.py, dayu/host/command.py, dayu/host/durable/purge.py, dayu/host/api.py
  - Tests: tests/host/test_purge_session.py, tests/host/test_audit_sink.py, tests/host/test_package_exports.py
  - README sync: dayu/host/README.md
  - Prior review artifacts: 10 review files under docs/reviews/
  - Other control doc cross-ref additions: docs/host/issues-implementation-control.md, docs/host/maintainability-implementation-control.md, docs/host/ui-implementation-control.md
- Excluded scope:
  - Gateflow checkpoint commits (no code content)
  - Slice1 implementation handoff docs (historical record)
- Parallel review coverage: 无（单 reviewer 全量走读）

## Review Methodology

本次 aggregate review 按以下路径逐行走读：

1. Plan artifact → 对 implementation diff 做 contract conformance check。
2. Control doc rename / status / residual risk → 确认当前 gate 状态准确。
3. Implementation 主路径：
   - `purge_session` command path (`command.py:769-897`)
   - audit builder/append 函数 (`audit.py:470-663`)
   - durable purge helper (`purge.py:690-788`)
   - replay/幂等判定链路 (`purge.py:622-687, 826-853`)
4. Failure paths：started append 失败、SQLite transaction 失败、purge_completed append 失败、purge_failed append 失败。
5. Adversarial failure pass：concurrency、replay、retry、partial state、idempotency、source key conflict。
6. Test coverage analysis。
7. README sync 检查。
8. Over-design 检查：通用 audit query/analyze API、过度抽象。

## Findings

### 1-未修复-低-`_PurgeAuditInputs.operation_context_digest` 类型与实际 contract 不一致

- **入口/函数**: `_build_purge_audit_inputs` → `PurgeStartedAuditRecordRequest`
- **文件(行号)**: `dayu/host/command.py:757` (`operation_context_digest: str`) vs `dayu/host/audit.py:194` (`operation_context_digest: str | None`)
- **输入场景**: 任何 purge_session 调用
- **实际分支**: `command.py:950` 始终从 `sha256_digest_json(operation_context_refs)` 计算 digest，该函数始终返回 `str`
- **预期行为**: `_PurgeAuditInputs.operation_context_digest` 是内部中间结构，其类型应精确反映它始终非空
- **实际行为**: 模块内部类型 `str` 比 audit contract 类型 `str | None` 更窄；当前调用链安全（`str` 可赋值给 `str | None`），但 audit contract 的 `str | None` 对合法 purge attempt 实际不存在 `None` 情况
- **直接证据**: `command.py:950` 始终调用 `sha256_digest_json(...)` 且 OperationContext 始终存在 7 个字段（即使为空字符串也会产生稳定 JSON）
- **影响**: 最低。类型不一致不产生运行时错误，仅反映 contract 表达与实际调用模式之间的语义 gap；若未来有直接调用 `PurgeStartedAuditRecordRequest` 的外部代码传入 `None`，才会触发行为差异
- **建议改法和验证点**: 可保持现状，或将 `_PurgeAuditInputs.operation_context_digest` 改为 `str | None` 并补充防御性 None 检查。当前实现已正确，无需立即修改
- **修复风险（低）**: 若修改为 `str | None`，command path 需补充 None 处理分支
- **严重程度（低）**: 无运行时影响

### 2-未修复-低-test SQLite trigger 未显式清理（无跨测试风险）

- **入口/函数**: `test_public_purge_session_sqlite_failure_writes_started_and_no_completed`
- **文件(行号)**: `tests/host/test_purge_session.py:2855`
- **输入场景**: 测试运行
- **实际分支**: `_InstallTombstoneInsertFailureTriggerOperation` (line 734-752) 创建 `BEFORE INSERT ON host_purge_tombstones` trigger
- **预期行为**: trigger 应在测试事务中创建且随事务结束失效，或在测试后显式 DROP
- **实际行为**: trigger 直接在 fresh DB 上创建，但每个测试使用独立 `tmp_path`，trigger 不会污染其他测试
- **直接证据**: 测试使用 `_options(tmp_path)` 创建独立数据库，且未与其他测试共享 DB 文件
- **影响**: 无跨测试影响。唯一风险是同一测试函数内后续操作若有 tombstone insert 也会触发 trigger
- **建议改法和验证点**: 可保持现状；如需增加防御性，在测试 finally 中 DROP trigger
- **修复风险（低）**: 仅需加清理步骤
- **严重程度（低）**: 无运行时影响

## Open Questions

无。

## Residual Risk

1. **RR-AUDIT-03**: `purge_completed` append 在 SQLite commit 后失败时，调用方收到 retryable `INTERNAL_ERROR`，tombstone 已是完成真源。同 key retry 会补写 completed audit line。但如果调用方不 retry，JSONL 中会永远保留 started 而无 completed。这不是 correctness 问题（tombstone 才是真源），但 audit 完整性的最佳观测窗口取决于调用方 retry 策略。当前已通过 `test_public_purge_session_completed_append_failure_retries_completed` 覆盖 retry 路径，但调用方不 retry 的路径已在 test plan 中被标记为 "residual risk accepted"。

2. **RR-AUDIT-04**: `purge_failed` 是 best-effort；如果 failed audit append 也失败（例如 JSONL 文件系统满），只会留下 `purge_started` line。由于 `audit_json_line_marks_purged_source_eventlog_facts` 对 started line 返回 `False`，不会误判为完成。此风险已在 plan 第 12 节明确记录为 accepted residual risk。

3. **测试未覆盖**: `purge_failed` audit append 本身失败时的 warning 日志输出。`_append_purge_failed_best_effort` 中 `except Exception` 分支（command.py:1012-1018）缺少针对性测试。在当前测试中 `purge_failed` 总是写成功。此 gap 影响低，因为该路径只是 logging，不影响 control flow 或 correctness。

4. **跨版本 JSONL schema 兼容**: 旧版 `purge_tombstone` line（pre-WU-AUDIT-01）可能仍存在于已部署环境的 JSONL 文件中。`audit_json_line_marks_purged_source_eventlog_facts` 不再识别旧 line kind，这是预期行为（旧 line 的 `source_eventlog_facts_purged=True` 与 SQLite 实际状态可能不一致）。但 audit 消费者若依赖旧 line kind 需要知晓此 breaking change。此项已在 plan 中明确声明不加兼容 wrapper。

## Control Doc Verification

- **Rename**: `docs/host/followup-implementation-control.md` → `docs/host/host-core-followup-implementation-control.md`。新文件名更精确地表达文档职责范围。
- **WU-AUDIT-01 section** (lines 192-214): 背景、目标、非目标、验收信号完整。状态跟踪 (line 169-172) 显示：
  - RR-AUDIT-01 (slice boundary): closed，controller 已裁决合并实现
  - RR-AUDIT-02 (docs sync): closed，README 已同步
- **Current gate status**: active work unit = WU-AUDIT-01, next entry point = aggregate deepreview。状态准确。

## Plan Conformance

逐项对照 plan contract：

| Plan Contract | Implementation | Status |
|---|---|---|
| 三类 purge audit line: started/completed/failed | `audit.py:93-95` | CONFORM |
| started `source_eventlog_facts_purged=false` | `audit.py:503` | CONFORM |
| completed `source_eventlog_facts_purged=true` | `audit.py:566` | CONFORM |
| failed `source_eventlog_facts_purged=false` | `audit.py:625` | CONFORM |
| JSONL source key `(line_kind, purge_attempt_ref)` | `audit.py:747-757` | CONFORM |
| `audit_json_line_marks_purged_source_eventlog_facts` 只认 completed | `audit.py:660-663` | CONFORM |
| started → SQLite → completed 顺序 | `command.py:792-891` | CONFORM |
| SQLite 失败后 best-effort failed | `command.py:824-874` | CONFORM |
| completed append 失败 retry 补写 | `command.py:877-891` + `purge.py:826-853` replay | CONFORM |
| 不修改 `host_purge_tombstones` schema | Schema 未改 | CONFORM |
| 不加兼容 wrapper | 旧 `PurgeTombstoneAuditRecordRequest` 等已完全删除 | CONFORM |
| 无通用 audit query/analyze API | 仅新增 purge 专用 builder/append 函数 | CONFORM |
| `build_purge_tombstone_digest` 不含 completed line 信息 | `purge.py:574-608` 只覆盖 tombstone 持久字段 | CONFORM |
| tombstone `audit_record_ref/digest` 指向 started line | `command.py:819-820` 传入 `started_audit_record_ref/digest` | CONFORM |

## Over-Design Check

- 无通用 audit analyze/query API
- 无 reconciliation report/framework
- 无 audit 状态机或分类系统
- 新增的 6 个 builder/append 函数和 4 个 request/result dataclass 均为 plan 要求的必要最小集
- 未引入新抽象层或 middleware

## Review Conclusion

**PASS** — 未发现实质性问题。

WU-AUDIT-01 的 plan 与 implementation 之间 contract conformance 完整。purge audit 三阶段（started/completed/failed）语义正确，source key 幂等设计可靠，故障路径处理符合 plan 规范。测试覆盖 happy path、failure injection、retry/replay、SQLite rollback 和跨进程 purge 后读路径。README 已同步新 audit 语义。无过度设计或通用 audit API 泄漏。两个低严重度 findings 均不产生运行时影响。
