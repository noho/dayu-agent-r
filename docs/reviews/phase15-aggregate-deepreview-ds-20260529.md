# Phase 15 Aggregate Deepreview — AgentDS

**Date:** 2026-05-29
**Reviewer:** AgentDS (aggregate deepreview specialist)
**Base:** main
**Branch:** feat/host-phase15-retention-purge-hardening
**Plan:** docs/host/phase15-retention-purge-production-hardening-plan.md
**Design source:** docs/host/design.md

## Overall Verdict: **PASS — No Blocker**

全量 1011 tests passed（1 skipped），pyright 0 errors。Phase 15 实现严格按照 plan 的 6 slices 执行，所有 release-blocking 契约已满足，未发现 residual P0/P1 blocker。以下 findings 均非阻塞级。

## Findings by Severity

### Severity: LOW

---

**F1. LOW — `_placeholders()` dead code in `dayu/host/durable/purge.py`**

`purge.py:2301` 定义了 `_placeholders(values)` 但未被模块内任何调用点使用。`_in_clause()` 和 `_delete_allowed_projection_reset_refs()` 使用了内联的 `", ".join("?" for _ in values)`。这是 dead code，不产生 bug，但违反"不写冗余代码"约束。

**Recommendation:** 移除 `_placeholders` 函数（purge.py 第 2301-2311 行）。

---

**F2. LOW — `retryable=True` on OSError audit failure 可能误导调用方**

`command.py:812-817`:
```python
except (OSError, RuntimeFileLockError) as exc:
    raise HostApiError(
        code=HostApiErrorCode.INTERNAL_ERROR,
        message="Host purge audit append failed",
        retryable=True,
    ) from exc
```

OSError 映射为 `retryable=True` 且 `INTERNAL_ERROR`。对于磁盘满（ENOSPC）这类持久性故障，重试大概率持续失败；但对于 transient 文件锁冲突，retry 合理。当前 mapping 偏宽松，不产生 correctness 风险。

**Recommendation:** 当前 retryable=True 行为可保留。后续如果加可观测信号（retry count / retry-after），可将 OSError 分类为 retryable-with-backoff。

---

### Severity: INFO

---

**F3. INFO — `audit_record_ref` 不含文件路径偏移量**

Tombstone 的 `audit_record_ref` 格式为 `audit-jsonl:purge-tombstone:{tombstone_id}`，不包含 audit JSONL 文件路径或字节偏移量。想通过 tombstone row 定位 audit JSONL line 的调用方需要额外知道 audit JSONL 文件路径并做文本扫描。

**Assessment:** 这是 plan 明确的设计决策：`No public payload/tombstone reader in P15`。不构成缺陷，只是后续 audit query helper 需要考虑定位效率。

---

**F4. INFO — Projection reset 白名单硬编码在 purge.py**

`_PURGE_REBUILDABLE_PROJECTION_CONSUMER_IDS` at `purge.py:131` 硬编码了 5 个可重建 consumer id。新增 rebuildable projection consumer（如新的 sink 或 read model）时，需要同步更新此列表，否则 purge 时 `reset_projection_refs_for_deleted_events` 会因"不在白名单"而抛出 `HostDurableError`。

**Assessment:** 这是 plan 明确要求的 hard guard。新增 consumer 时 test 会 catch 到这个异常。建议在 `purge.py` 模块 docstring 中注明此白名单需要与新 consumer 同步。

---

## Invariant Verification (All Passed)

### 1. Purge Tombstone Schema / Codec / Idempotency ✅

- `HOST_SCHEMA_VERSION = 14`，fresh bootstrap 包含 `host_purge_tombstones` table
- Tombstone table **无 FK 到** `event_log` / `host_sessions`（verified by schema test）
- `session_id` UNIQUE index 保证一个 Session 最多一个 tombstone
- Tombstone codec：字段级 validation（sha256 digest 格式、非空文本、非负整数），非法 durable row 解析抛出 `HostDurableError`
- 6-path idempotency replay：
  - PROCEED_TO_PURGE（tombstone 不存在 + idempotency 不存在）
  - REPLAY_TOMBSTONE（tombstone 存在 + 同 key/digest；或 idempotency 存在 + tombstone 有效）
  - IDEMPOTENCY_CONFLICT（同 key + 不同 digest）
  - ALREADY_PURGED_CONFLICT（不同 key + tombstone 已存在）
  - DURABLE_INCONSISTENCY（idempotency 存在但 result_kind 不匹配或 tombstone 缺失）
- Semantic digest 稳定性：仅包含 `session_id`、`reason`、`operation_context_digest/refs`、`request_context`，不含 timestamp，保证 replay 匹配
- Tombstone-only replay（`_decision_for_existing_tombstone`）：tombstone 存在但 idempotency row 缺失时，补写 idempotency 并 replay

### 2. Delete Matrix ✅

FK-safe 删除排序（与 EventLog FK 关系的 child-before-parent 顺序）：

```
audit_sink_markers (FK event_id)
  → outbox_drain_idempotency / outbox_terminal_items (FK event_id, session_id)
  → tool_trace_hot (FK event_id, session_id)
    → memory_diagnostics / memory_items / memory_snapshots (FK event_id, session_id)
    → run_results / session_timeline_items (FK event_id, session_id)
      → projection checkpoints/failures (exact reset by event_id + consumer whitelist)
      → old command idempotency (FK created_event_id/sequence)
        → wait_records (FK event_id, session_id)
          → dispatch_records (FK run_id)
            → attempts (FK run_id)
              → runs (child-before-parent via source_run_id leaf-deletion loop)
                → session_slots (FK session_id)
                  → session (PK)
                    → event_log (PK)
                      → unreferenced payload descriptors → sqlite payloads
```

- 全部测试在 `PRAGMA foreign_keys=ON` 下通过
- Retry/replay 链条 purge：`_delete_runs_child_before_parent` 通过 while-loop 先删叶子 Run（`source_run_id` 不被其他 surviving Run 引用），逐层向根推进。最坏 O(n²) 但对 deep retry chains 正确且安全
- Payload cleanup：ref-count 验证（扫描 8 个 durable 表的 payload ref 列），未被其他 row 引用才删除 descriptor；SQLite payload 同理
- Projection checkpoint/failure reset：精确 DELETE + consumer whitelist guard（`_raise_for_unsupported_projection_reset_refs`），非白名单 consumer 引用 target EventLog 时抛出 `HostDurableError`
- 前置条件使用 Session / Run / Attempt / wait truth，**不含** projecton/memory/outbox

### 3. Public Command / Read-after-Purge ✅

- `purge_session()` 不再返回 `UNSUPPORTED_OPERATION`
- Error mapping：
  - `PurgeSessionInvalidStateError` → `INVALID_STATE`（Session 未关闭 / Run 未终态 / 存在 active wait）
  - `PurgeSessionNotFoundError` → `NOT_FOUND`
  - `PurgeSessionAlreadyPurgedError` → `CONFLICT`（不同 key 请求已 purge Session）
  - `HostIdempotencyConflictError` → `IDEMPOTENCY_CONFLICT`（同 key 不同 digest）
  - `OSError / RuntimeFileLockError` → `INTERNAL_ERROR` + retryable（audit append 失败）
  - 其他 `HostDurableError` → `INTERNAL_ERROR`
- Closed-handle guard 保持（`_raise_if_closed()` 在 purge 入口第一行）
- Read-after-purge：read_api.py **无需变更**——Session/Run rows 物理删除后，现有 `NOT_FOUND` 路径自然覆盖
- `get_session`、`get_run`、`retry_run`、`replay_run` 全部 test-verified 返回 `NOT_FOUND`
- 不同 request id 对已 purge Session 返回 `CONFLICT`（test-verified）
- 不新增 public error code（使用现有 `NOT_FOUND` / `CONFLICT` / `INVALID_STATE`）

### 4. Audit JSONL Fail-Before-Success ✅

执行序列（在同一 SQLite write transaction 内）：

```
1. 删除矩阵（deletes Session/Run/Attempt/EventLog...）
2. payload cleanup
3. _insert_tombstone_and_idempotency():
   a. build tombstone_id (deterministic)
   b. compute deleted_counts_digest
   c. audit_recorder.record_purge_tombstone_audit() ← 追加 JSONL line
   d. validate audit result (ref + sha256 digest)
   e. insert_purge_tombstone()
   f. record_idempotent_result()
4. 返回 PurgeSessionDeleteResult
```

- **Audit append 在 tombstone insert 之前**：若 audit append 抛 OSError，异常传播 → transaction rollback → 所有 deletes 回滚 → public 返回 `INTERNAL_ERROR` + retryable
- **Audit append 成功 + tombstone insert 失败**：transaction rollback → tombstone row 消失 → retry 时 audit JSONL dedup 命中同 tombstone_id + 同 digest → skip append → tombstone 写入成功
- **Audit JSONL dedup with source key guard**：`_jsonl_contains_line` 按 tombstone_id 做 source key 比较，同 source key + 不同 digest 抛出 `HostDurableError` 防冲突
- **No audit-pending success path**：`PurgeTombstoneRow.audit_record_ref` 为 NOT NULL，DB 约束保证 tombstone 没有 audit ref 无法存在
- JSONL 使用 filelock（`RuntimeFileLock`），append-only mode

### 5. Projection / Recovery / Dispatch / Multiprocess Hardening ✅

- **Projection reset**：`reset_projection_refs_for_deleted_events` + 白名单 consumer ids，非白名单 consumer 检测 + 抛出（purge.py `_raise_for_unsupported_projection_reset_refs`）
- **Recovery guard** (`recovery.py:242`)：`read_session_by_id(transaction, run.session_id) is None` → 返回 `NOT_FOUND`，防止 recovery 对已 purge Session 重建 run
- **Dispatch guard**：
  - `dispatch.py:2166-2170`：lane acquired 后 dispatch recheck 增加 `session_exists` 条件（`_is_dispatchable_recheck`）
  - `dispatch.py:3167`：queue promotion `_read_startable_run` 增加 `read_session_by_id is None` guard
- **No multiprocess-specific regression**：existing multiprocess tests 继续通过，purge 后的跨进程行为由 SQLite transaction ordering 决定（commit 后其他进程看到 deleted + tombstone）
- 无 Engine/remote wire protocol 变更（符合 plan non-goal）

### 6. README / Guard Tests ✅

- `dayu/host/README.md`：更新 purge 实现语义，移除 "structured unsupported" 声明，补充前置条件、tombstone、read-after-purge、non-goals 说明
- `tests/README.md`：按计划触发规则无额外变更需要
- Import boundary (`test_import_boundary.py`)：purge durable 模块不得 import engine/service/ui/fins/admission/audit/command/dispatch/open_host/recovery
- Package exports (`test_package_exports.py`)：purge durable symbols 不泄漏到 `dayu.host` root namespace
- Weak typing guard (`test_weak_typing_guard.py`)：purge.py 被全包弱类型扫描覆盖

### 7. 分层边界 ✅

- `dayu/host/durable/purge.py` 只依赖 `dayu.host.durable.*` 和 `dayu.contracts.json_value`
- Audit Recorder Protocol (`PurgeTombstoneAuditRecorder`) 用于接口反向——purge durable 定义写入端口，command layer 提供具体实现（`_PurgeAuditJsonlRecorder`）
- purge durable 不 import command/audit/dispatch/open_host/recovery
- `dayu/engine/`、`dayu/service/`、`dayu/ui/`、`dayu/fins/` 零变更

### 8. Docstring / Typing / Pyright ✅

- 所有新增 module/class/function 提供中文 docstring
- 无 `object`、`Any`、裸 `dict/list/set` 签名
- 无 `hasattr`/`getattr` 逃避类型边界
- 魔法数字全部模块级常量
- Pyright 全量：**0 errors**

### 9. Non-goals 验证 ✅

逐项确认未越界：

| Non-goal | Status |
|---|---|
| 不修改 Host public API shape | ✅ `PurgeSessionRequest`/`PurgeSessionResult` 不变 |
| 不实现 archive_session | ✅ 未实现 |
| 不实现 memory edit/reset/forget | ✅ 只做 session-scope deletion |
| 不实现 public payload reader | ✅ read_api 无变更 |
| 不实现 wait_final_answer/get_run_result | ✅ 未实现 |
| 不做 RemoteProxy/RemoteStub | ✅ 无变更 |
| 不修改 Engine | ✅ engine/ 零变更 |
| 不删除 append-only audit JSONL | ✅ append-only + tombstone audit line |
| 不用 projection/memory/outbox 作 governance truth | ✅ 前置条件只用 Session/Run/Attempt/wait |
| 不写旧 schema 兼容读取/迁移测试 | ✅ schema tests 按 fresh v14 断言 |
| 不新增 public error code | ✅ 使用现有 NOT_FOUND/CONFLICT/INVALID_STATE |
| Audit JSONL 不删除/截断/重写 | ✅ append mode + source key dedup guard |

## Residual Risk Classification

| Risk | Classification | Owner |
|---|---|---|
| audit_record_ref 不含文件路径偏移量 | Follow-up audit query helper | Later audit work unit |
| Projection rebuildable consumer 白名单需要同步 | Doc note + future phase | P15 后续 consumer 作者 |
| `_placeholders` dead code | Housekeeping | P15 作者（清理） |
| OSError retryable=True 对磁盘满永久重试 | Low-risk, acceptable | Host command error taxonomy |
| Run child-before-parent loop O(n²) | Academic, not practical risk | No action needed |

## Summary

Phase 15 aggregate deepreview 通过。所有 release-blocking 契约已实现并通过测试验证：

- **Purge tombstone**：schema/codec/idempotency replay 完整，schema bump 13→14
- **Delete matrix**：FK-safe 排序、payload ref-count cleanup、projection reset with whitelist、child-before-parent run deletion
- **Public command**：purge_session 已从 unsupported 接入，errors mapped to existing codes
- **Read-after-purge**：物理删除 → NOT_FOUND 自然走通，read_api 无需变更
- **Audit JSONL**：fail-before-success（audit append 在 tombstone 前，所有操作在同事务），no audit-pending success path
- **Recovery/dispatch hardening**：3 个 session_exists guard 防止重激活已 purge facts
- **Tests**：1011 passed, 0 pyright errors
- **分层边界**：零反向依赖，symbols 不泄漏到 root namespace
- **Non-goals**：全部未越界

**No blocker. Phase 15 is ready to proceed.**
