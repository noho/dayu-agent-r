# Draft PR Review — WU-AUDIT-01 Purge Audit Reconciliation (PR #99)

## Scope

- Mode: PR review (draft readiness assessment)
- PR: [noho/dayu-agent-r#99](https://github.com/noho/dayu-agent-r/pull/99)
- Title: Host purge audit reconciliation
- Author: noho
- Head: `feat/host-purge-audit-reconciliation`
- Base: `main`
- Output file: `docs/reviews/wu-audit-01-pr-review-ds-20260531.md`
- Included scope:
  - `dayu/host/api.py` — `PurgeSessionResult` docstring 更新
  - `dayu/host/audit.py` — 新 purge started/completed/failed builder / append / marks helper
  - `dayu/host/command.py` — `purge_session` 编排重构，failure_stage 区分
  - `dayu/host/durable/purge.py` — 新 tombstone helper，删除 audit recorder
  - `dayu/host/README.md` — purge audit 语义同步
  - `tests/host/test_purge_session.py` — 新 audit 测试（7 个关键测试）
  - `tests/host/test_audit_sink.py` — 旧测试更新 + 新 audit line 测试
  - `tests/host/test_package_exports.py` — 导出白名单同步
  - `tests/README.md` — 测试覆盖描述同步
  - Plan artifact: `docs/host/wu-audit-01-purge-audit-reconciliation-plan.md`
  - Prior review artifacts: `docs/reviews/wu-audit-01-code-review-ds-20260531.md` 及 rereview
- Excluded scope: 无（全部 diff 已 review）
- Parallel review coverage: 无（单 reviewer 全量走读）
- Verification: 46 tests passed, pyright 0 errors / 0 warnings / 0 infos（独立验证通过）

## Review Method

本 review 在已有 code review（`wu-audit-01-code-review-ds-20260531.md`，F-01/F-02 已修复）的基础上执行：

1. 验证 F-01（failure_stage 统一标签）和 F-02（idempotency conflict 语义边界）修复的 correctness。
2. 对最终 diff 执行 adversarial failure pass，确保没有新引入的 regression 或遗漏的边界条件。
3. 检查 README 同步是否完整且在职责范围内。
4. 检查测试覆盖与计划验收条件之间的 gap。
5. 判断 draft PR readiness。

每条主链路（成功路径、SQLite 失败路径、completed append 失败 + retry 路径）重新走读确认入参 → 分支 → 下游 → 返回值/副作用一致性。

---

## F-01 / F-02 修复验证

### F-01: failure_stage 区分（原 severity: 中）

**修复确认**：

- `command.py:140-144` 定义 5 个模块级常量：`precondition_check`、`already_purged`、`not_found`、`idempotency_conflict`、`sqlite_purge_transaction`
- `_append_purge_failed_best_effort`（`command.py:977`）签名改为 keyword-only `failure_stage: str`，防止调用侧误传位置参数
- 各 except 分支使用对应常量（`command.py:824, 833, 842, 849, 858`）
- 测试 `test_public_purge_session_sqlite_failure_writes_started_and_no_completed`（`test_purge_session.py:2894`）断言 `lines[1]["failure_stage"] == "sqlite_purge_transaction"`
- 异常类型到 failure_stage 的映射完整覆盖 5 种 failure path

**结论: F-01 RESOLVED**

### F-02: idempotency conflict 语义边界（原 severity: 低）

**修复确认**：

- `HostIdempotencyConflictError` 独立 catch 在泛化 `HostDurableError` 之前（`command.py:839-847`），except 顺序正确（子类先于父类）
- idempotency conflict 仍写入 `purge_failed`（附加诊断价值），但 `failure_stage` 现在准确为 `"idempotency_conflict"`
- 不再误导为 `"sqlite_purge_transaction"`

**结论: F-02 RESOLVED**

---

## Adversarial Failure Pass（基于最终 diff）

| 场景 | 行为 | 评判 |
|---|---|---|
| started append 失败（OSError/lock/conflict） | raise retryable HostApiError，不进入 SQLite transaction | 正确 |
| Crash between started append and SQLite transaction | started line 存在，`source_eventlog_facts_purged=False`；retry 幂等跳过 started，重新执行 PROCEED_TO_PURGE | 正确 |
| SQLite transaction 中途 crash | SQLite atomic rollback，started 存在，无 tombstone，无 completed；retry 重新执行完整 delete matrix | 正确 |
| Crash after SQLite commit before completed append | tombstone committed，started 存在，无 completed；retry REPLAY_TOMBSTONE → 无条件 append completed | 正确 |
| completed append 失败（OSError） | raise retryable HostApiError，tombstone 已持久 | 正确 |
| completed append 失败（HostDurableError, source key conflict） | `HostApiError(INTERNAL_ERROR, retryable=False)`；deterministic 输入下不应出现 completed digest 冲突 | 可接受 |
| 并发 purge 同 Session（不同 client_request_id） | ALREADY_PURGED_CONFLICT → `purge_failed(failure_stage="already_purged")` → raise CONFLICT retryable=False | 正确 |
| 并发 purge 同 Session（同 client_request_id retry） | REPLAY_TOMBSTONE → 补写 completed（或幂等跳过） | 正确 |
| `_append_purge_failed_best_effort` 自身失败 | `except Exception` 捕获，`_LOGGER.warning`，不替换原始错误 | 正确 |
| JSONL 中存在旧格式 `purge_tombstone` line（legacy data） | `audit_json_line_marks_purged_source_eventlog_facts` 对 `line_kind != "purge_completed"` 返回 False | 向后兼容 |
| JSONL 中存在 corrupt/malformed line | `_json_object_from_jsonl_line` 返回 None → 跳过 | 正确 |
| `HostDurableError` 在 started append 时抛出（source key conflict） | raise HostApiError（INTERNAL_ERROR 或 IDEMPOTENCY_CONFLICT），不写 failed，不进入 transaction | 正确：这是 append 层问题 |
| Session 无 EventLog facts | `HostDurableError("purge target Session has no EventLog facts")` → `purge_failed(failure_stage="sqlite_purge_transaction")` → raise HostApiError | 可接受：`purge_failed` 标签不完全精确（非 SQLite 事务失败，是数据前置条件），但 plan 明确 `purge_failed` 为 best-effort，不围绕它构建查询系统 |

无新发现严重或高危 correctness 问题。

---

## Architecture Boundary Check（重复审查）

- `dayu/host/audit.py` → `dayu/host.durable.purge`（`PurgeTombstoneRow`）：Host 层内跨模块依赖，`PurgeTombstoneRow` 是 frozen dataclass（纯数据），plan 明确允许
- `dayu/host/command.py` → `dayu/host.audit`：正确的 command → audit 方向依赖
- `dayu/host/durable/purge.py` 不导入任何 audit 类型：符合 plan Slice 1 目标
- 旧 `PurgeTombstoneAuditRecorder` Protocol 已删除：durable 层不再依赖 audit writer port，改为接收纯数据 started audit ref/digest，正确解耦
- 无跨层穿透、反向依赖、循环依赖

---

## README / 文档同步检查

### `dayu/host/README.md`

变更（行 90）：从旧单行 `purge tombstone audit record` 描述更新为三种 line kind 语义描述，明确真源归属（SQLite tombstone 是完成真源）。

**职责符合性**：
- 描述 purge audit 的公共契约语义（三种 line kind 含义与边界）—— 符合 `dayu/host/README.md` 职责（"接口、公共契约、架构、边界"）
- 不包含实现细节（builder 参数、source key 格式、append 逻辑）—— 符合
- 旧术语已全量清理 —— 符合

**结论: 通过**

### `tests/README.md`

变更（行 115）：从 `append-only audit JSONL tombstone record` 更新为 `purge_started / purge_completed / best-effort purge_failed 语义`。

**职责符合性**：描述测试覆盖的 audit 语义范围，属于测试手册职责。术语已更新。

**结论: 通过**

### 总控文档 RR-AUDIT-02

`docs/host/host-core-followup-implementation-control.md` 中 RR-AUDIT-02 仍标记为 `open`。当前 README 已同步，触发条件已满足。建议在 ready-to-open-draft-PR 前将 RR-AUDIT-02 标记为 `closed`。此项不阻塞 draft PR PASS。

---

## Test Coverage Assessment

| 测试 | 覆盖场景 | 状态 |
|---|---|---|
| `test_public_purge_session_appends_tombstone_audit_jsonl` | 成功路径：started + completed，tombstone ref/digest 一致性，marks helper | 覆盖 |
| `test_public_purge_session_audit_append_failure_fails_before_success` | started append 失败：不进入 SQLite，tombstone=None，EventLog 保留 | 覆盖 |
| `test_public_purge_session_sqlite_failure_writes_started_and_no_completed` | SQLite 失败（trigger RAISE(ABORT)）：rollback，JSONL 有 started+failed 无 completed | 覆盖 |
| `test_public_purge_session_completed_append_failure_retries_completed` | completed append 失败 + monkeypatch undo retry 补写：final JSONL 只有 1 started + 1 completed | 覆盖 |
| `test_purge_audit_lines_are_append_only_and_only_completed_marks_purged` | started/failed/completed 幂等去重 + marks helper 正确性 | 覆盖 |
| `test_purge_session_durable_deletes_matrix_and_preserves_replay` | durable 层 replay（`idempotent_replay=True`），tombstone digest/attempt_ref helper | 覆盖 |
| `test_purge_session_durable_rejects_invalid_started_audit_ref_before_delete` | 无效 started audit ref 在删除前被拒绝 | 覆盖 |
| `test_purge_session_durable_rejects_open_session` | Session 未关闭时拒绝，无 tombstone | 覆盖（durable 层） |
| `test_purge_session_durable_rejects_non_terminal_runs`（参数化） | 非终态 Run 拒绝，覆盖全部 6 种 active 状态 | 覆盖（durable 层） |

**未覆盖但不阻塞 draft PR**：
- `purge_failed` append 自身失败路径（被 `_LOGGER.warning` 捕获）—— best-effort 语义下可接受，难以在单元测试中可靠触发且价值有限
- 并发 purge（多进程同时 purge 同一 Session）—— SQLite serializable isolation + idempotency/tombstone check 在事务内裁决，风险可控
- `failure_stage` 的 `precondition_check` / `already_purged` / `not_found` / `idempotency_conflict` 路径在 public `purge_session` 测试中未断言具体 JSONL `failure_stage` 字段值（这些异常路径的测试调用 `purge_session_durable` 直连，不经过 `_append_purge_failed_best_effort`）—— 严重程度低：常量定义具备稳定性保证，代码审查已验证映射正确性

---

## Open Questions

1. 总控文档 RR-AUDIT-02 仍标记为 `open`。README 已同步，建议在 ready-to-open-draft-PR 前关闭。此项不阻塞 correctness。

---

## Residual Risk

- completed append 在 SQLite commit 后失败时，tombstone 已是完成真源；调用方收到 retryable error，需同 `client_request_id` retry 补写 completed line。若调用方不 retry，JSONL 缺少 completed line，但 `audit_json_line_marks_purged_source_eventlog_facts` 不会误判为 completed。plan §12 已记录此风险为 residual
- `purge_failed` 的 `failure_stage` 标签区分度已修正（F-01/F-02 resolved），但 `purge_failed` 本身为 best-effort 诊断；若 failed append 也失败，JSONL 只留 started line。helper 不会误判为 completed，但 audit trail 不完整。plan §12 已记录
- CI 无 checks 报告（`gh pr checks 99` 返回 "no checks reported"）。46 tests + pyright 在本地验证通过，但缺少 CI 自动化验证是本 PR 的环境级 residual risk

---

## Draft Readiness Assessment

| 维度 | 状态 |
|---|---|
| Correctness contract（plan §2-4） | 通过 — started/completed/failed 语义正确，真源归属明确 |
| F-01 / F-02 修复 | RESOLVED — failure_stage 区分，idempotency conflict 独立处理 |
| 测试覆盖（plan §7） | 通过 — 4 个核心验收场景全部覆盖，46 tests pass |
| pyright | 通过 — 0 errors / 0 warnings / 0 infos |
| README 同步 | 通过 — `dayu/host/README.md` 和 `tests/README.md` 已同步 |
| Schema 不变 | 通过 — `host_purge_tombstones` DDL 未修改 |
| 无通用 audit API | 通过 — 不新增通用查询或分析 API |
| 架构边界 | 通过 — 无跨层穿透、反向依赖、循环依赖 |
| CI | 注意 — 无 CI checks 报告，本地验证通过 |

---

## Conclusion

**PASS** — 未发现新的 correctness 阻塞问题。F-01 和 F-02 均已修复。实现严格遵循 accepted plan 的 correctness contract。测试覆盖 4 个核心验收场景，46 tests pass，pyright 0 errors。draft PR ready。

建议在 open draft PR 前将总控文档 RR-AUDIT-02 标记为 closed（README 同步已完成）。
