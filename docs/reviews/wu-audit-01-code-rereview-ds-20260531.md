# Re-review — WU-AUDIT-01 F-01/F-02 修复与 README 同步

## Scope

- 基准 review: `docs/reviews/wu-audit-01-code-review-ds-20260531.md`
- 重审范围: `F-01` / `F-02` 修复验证 + `dayu/host/README.md` / `tests/README.md` 最小文档同步检查
- 不重复审查已 PASS 的 correctness contract

---

## F-01 修复验证（failure_stage 统一标签）

**原状**: `_append_purge_failed_best_effort` 对所有 failure type 硬编码 `failure_stage="sqlite_purge_transaction"`（`command.py:972`）。

**现况**: 新增 5 个模块级常量（`command.py:137-141`）:

```python
_PURGE_FAILURE_STAGE_PRECONDITION_CHECK = "precondition_check"
_PURGE_FAILURE_STAGE_ALREADY_PURGED = "already_purged"
_PURGE_FAILURE_STAGE_NOT_FOUND = "not_found"
_PURGE_FAILURE_STAGE_IDEMPOTENCY_CONFLICT = "idempotency_conflict"
_PURGE_FAILURE_STAGE_SQLITE_TRANSACTION = "sqlite_purge_transaction"
```

`_append_purge_failed_best_effort` 签名改为 keyword-only `failure_stage` 参数（`command.py:918`）:

```python
def _append_purge_failed_best_effort(
    options: LogAuditSinkOptions,
    audit_inputs: _PurgeAuditInputs,
    *,
    failure_stage: str,
    error: Exception,
) -> None:
```

各 except 分支映射:

| 异常类型 | failure_stage | 行号 |
|---|---|---|
| `PurgeSessionInvalidStateError` | `precondition_check` | 815 |
| `PurgeSessionAlreadyPurgedError` | `already_purged` | 824 |
| `PurgeSessionNotFoundError` | `not_found` | 833 |
| `HostIdempotencyConflictError` | `idempotency_conflict` | 842 |
| `HostDurableError` (泛化) | `sqlite_purge_transaction` | 849 |

**测试覆盖**: `test_public_purge_session_sqlite_failure_writes_started_and_no_completed`（行 2894）断言 `lines[1]["failure_stage"] == "sqlite_purge_transaction"`。

**结论: F-01 RESOLVED**。诊断精度显著提升，keyword-only 参数防止调用侧误传。

---

## F-02 修复验证（idempotency conflict 路径的 purge_failed 语义边界）

**原状**: `HostIdempotencyConflictError` 被泛化 `except HostDurableError` 捕获，统一以 `"sqlite_purge_transaction"` 写入 `purge_failed`。

**现况**: 新增独立 `except HostIdempotencyConflictError as exc:` 分支（`command.py:839-847`），在泛化 `HostDurableError` 之前：

```python
except HostIdempotencyConflictError as exc:
    _append_purge_failed_best_effort(
        audit_sink_options,
        audit_inputs,
        failure_stage=_PURGE_FAILURE_STAGE_IDEMPOTENCY_CONFLICT,
        error=exc,
    )
    raise _host_api_error_from_durable_error(exc) from exc
except HostDurableError as exc:
    ...
```

**except 顺序验证**: `HostIdempotencyConflictError` 是 `HostDurableError` 的子类，必须在泛化 catch 之前。当前顺序正确。

**结论: F-02 RESOLVED**。idempotency conflict 仍写入 `purge_failed`（额外诊断价值），但 `failure_stage` 标签现在准确区分 `"idempotency_conflict"` 与 `"sqlite_purge_transaction"`，不再误导。

---

## README 文档同步检查

### `dayu/host/README.md`

**变更**: 行 90 从旧描述:

> 成功 purge 会写入 purge tombstone audit record，并把 audit record ref / digest 写入 tombstone

改为:

> purge audit JSONL 只记录 destructive 操作流水：`purge_started` 表示 purge attempt 已发起，不表示完成；`purge_completed` 只在 SQLite tombstone commit 成功后写入，并引用 tombstone id / digest；`purge_failed` 是失败路径的 best-effort 诊断。tombstone 中的 audit record ref / digest 指向 `purge_started` 行；purge 完成真源仍是 SQLite tombstone。

**职责符合性检查**（对照 CLAUDE.md 中 `dayu/host/README.md` 职责: "接口、公共契约、架构、边界、执行路径、状态机、事件流、关键机制、扩展点"）:

- 描述的是 purge audit 的公共契约语义（三种 line kind 的含义与边界）——符合
- 明确真源归属（SQLite tombstone 是完成真源）——符合
- 不包含实现细节（不描述 builder 参数、source key 格式、append helper 内部逻辑）——符合
- 不写未来设计或版本记录——符合
- 旧术语已全量清理（"purge tombstone audit record" 已替换为三种 line kind）——符合

**结论: 通过** — 最小同步，职责内更新，无越界内容。

### `tests/README.md`

**变更**: 行 115 从:

> append-only audit JSONL tombstone record

改为:

> append-only audit JSONL 的 `purge_started` / `purge_completed` / best-effort `purge_failed` 语义

**职责符合性检查**（对照 CLAUDE.md 中 `tests/README.md` 职责: "测试分层、运行方式、约定与维护规则"）:

- 描述的是 purge 测试覆盖的 audit 语义范围——符合（测试覆盖描述属于测试手册职责）
- 使用新术语（`purge_started` / `purge_completed` / `purge_failed`）——符合
- 不包含实现细节——符合

**结论: 通过** — 最小同步，职责内更新。

### 其他 README 检查

- `dayu/host/README.md` 行 88（tombstone replay 幂等重放描述）和行 86（purge 删除矩阵描述）未变更，语义仍准确——无需更新
- `tests/README.md` 行 124 描述 "`dayu.host.durable.purge` 不依赖上层、runtime、public command owner 或 audit / dispatch owner"——仍准确（purge 模块已移除 audit 依赖），无需更新
- 搜索全量 README，无残留 "purge tombstone audit record" 或旧 `purge_tombstone` line kind 描述

---

## 总控文档 RR-AUDIT-02 状态

`docs/host/host-core-followup-implementation-control.md` 中 RR-AUDIT-02 仍标记为 `open`:

> code review 后检查 `dayu/host/README.md` 是否仍描述旧 purge tombstone audit line；如命中职责范围则当前 work unit 内同步

当前 `dayu/host/README.md` 已同步（不再描述旧单行 purge tombstone audit line），RR-AUDIT-02 的触发条件已满足。建议在 ready-to-open-draft-PR 前将 RR-AUDIT-02 更新为 `closed`。

_注：用户指示不要修改文件，此项仅标记注意，不阻塞 re-review PASS。_

---

## 残留测试缺口

- `failure_stage` 的 `precondition_check` / `already_purged` / `not_found` / `idempotency_conflict` 路径在 public `purge_session` 测试中未断言具体的 JSONL `failure_stage` 字段值。这些异常路径的 public command 测试（如 `test_purge_session_durable_rejects_open_session`）调用了 `purge_session_durable` 直连而非 public `purge_session`，因此不经过 `_append_purge_failed_best_effort`。
- 严重程度低：`failure_stage` 标签的常量定义已具备稳定性保证（模块级常量），代码审查已验证映射正确性；且 plan 明确 `purge_failed` 为 best-effort，不围绕它构建查询系统。

---

## Conclusion

**PASS** — F-01 和 F-02 均已修复。README 同步符合各自职责边界，无越界内容或残留旧术语。

| 项目 | 状态 |
|---|---|
| F-01 (`failure_stage` 标签) | RESOLVED |
| F-02 (idempotency conflict 语义边界) | RESOLVED |
| `dayu/host/README.md` | 通过 — 最小同步，职责内 |
| `tests/README.md` | 通过 — 最小同步，职责内 |
| RR-AUDIT-02 (控制文档) | 注意 — README 已同步，控制文档条目待关闭 |
| 新 correctness 问题 | 无 |
