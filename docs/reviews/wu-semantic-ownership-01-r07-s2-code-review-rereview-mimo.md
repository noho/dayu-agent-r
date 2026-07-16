# WU-SEMANTIC-OWNERSHIP-01 R07-S2 cumulative S1+S2 code re-review — AgentMiMo

## 1. Gate 与输入

- Active WU：`WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation。
- Internal remediation sub-WU：R07；checkpoint：累计 S1+S2 code re-review（fix 后）。
- AgentCodex fix artifact：`docs/reviews/wu-semantic-ownership-01-r07-s2-code-review-fix-codex.md`。
- Controller fix validation：`docs/reviews/wu-semantic-ownership-01-r07-s2-code-review-fix-controller-validation.md`，结论 `PASS / READY_FOR_DUAL_COMPLETE_CUMULATIVE_S1+S2_RE-REVIEW`。
- Accepted finding：`R07-S2-CR-F01`（consumer snapshot close failure masks active primary failure）。
- Base HEAD：`386fef8d`（`docs: enter R07 opaque identity implementation`）。
- 本 artifact 是 Controller validation 之后的双路 re-review 之一，覆盖完整累计 S1+S2 product/test/README tree，不只 narrow 看 fix。

## 2. 验证矩阵

| 检查 | 结果 |
|---|---|
| 五文件累计 pytest（含 `test_processor_read_consistency.py`） | `401 passed, 3 warnings`（独立验证 23.38s） |
| Owner-level context lifecycle 双失败节点 | `3 passed in 0.36s` |
| full pyright | `0 errors, 0 warnings, 0 informations` |
| scoped Ruff（15 production + 5 test） | `All checks passed!` |
| full Ruff baseline | 既有 `152`：`72 F401 / 66 E402 / 10 F841 / 3 F541 / 1 F821`，未扩散 |
| `git diff --check` | PASS |
| S3/R08+/Issue 142/151/175/177/178/统一 authorization 偷带 | 0 |
| production `snapshot.close()` 残留 | 0（全部 consumer 已切换 context manager） |
| consumer `sys.exc_info` / `_append_secondary_error_note` 残留 | 0 |
| `/tmp/dayu-source-snapshot-*` 残留 | 0 |

## 3. R07-S2-CR-F01 关闭验证

### 3.1 Protocol contract

`repository_protocols.py:SourceSnapshotProtocol`（L86-124）：

- `__enter__` 返回 `SourceSnapshotProtocol`；docstring 声明 `RuntimeError` 在 snapshot 已关闭时抛出。
- `__exit__` 返回 `Literal[False]`（L109），类型和运行时均明确不压制 lifecycle body exception。
- `__exit__` 参数为标准 `exc_type`/`exc`/`traceback` 三元组。

### 3.2 Private implementation

`_fs_source_snapshot.py:_FsSourceSnapshot`（L255-352）：

- `__enter__`（L302-316）：调用 `self._state.require_open()` 确认可读后返回 `self`。
- `__exit__`（L318-352）：
  1. `del exc_type, traceback` 显式忽略不需要的参数。
  2. `try: self.close()` 执行资源释放。
  3. `except BaseException as close_error:` 捕获 close 任意失败。
  4. `if exc is None: raise` — 无 active primary 时 close failure 作为 path-free 主异常正常传播。
  5. 有 active primary 时：`_append_secondary_error_note(exc, close_error, action=_SNAPSHOT_CONTEXT_CLOSE_ACTION)` — 只追加 `action` + `error_type` + 可选 `errno`，不保留 raw message/cause/context/traceback/locator。
  6. `return False` — 明确不压制 lifecycle body 异常。

### 3.3 `_SnapshotResourceState.close()` 幂等/重试

`_fs_source_snapshot.py`（L160-181）：

- `self.closed = True` 先阻止后续读取。
- `temp_root = self.temp_root` 保留 cleanup locator。
- `_remove_snapshot_temp_root(temp_root)` 执行删除；失败时 `temp_root` 保留。
- `self.temp_root = None` 只在删除成功后清空。
- 全部在 `self.lock` 内，线程安全。
- 失败后下一次 `close()` 可重试同一 temp root。

### 3.4 Consumer 切换验证

**ingestion_runtime.py**（L4138-4194）：

```python
with self.source_repository.read_source_snapshot(
    ticker, document_id, source_kind, materialize_files=True,
) as snapshot:
    # ... processor work ...
# context exit 后：
commit_started = True
self.batching_repository.commit_batch(batch)
```

- `with snapshot` 替代了旧 `finally: snapshot.close()`。
- close-before-commit 顺序保留：context exit（触发 `__exit__` → `close()`）在 `commit_started = True` 之前。
- rollback 语义不变：`finally: if not commit_started: _rollback_batch_before_commit(...)` 仍覆盖 context exit 异常。
- 无 consumer-local `sys.exc_info`、`_append_secondary_error_note` 或 `snapshot.close()`。

**sec_fiscal_fields.py**（L280-294）：

```python
try:
    snapshot = source_repository.read_source_snapshot(...)
except Exception:
    return None, None
with snapshot:
    return _extract_download_fiscal_from_snapshot(...)
```

- acquisition 失败仍按 best-effort 返回 `(None, None)`。
- `with snapshot` 管理 lifecycle；close failure 不被 acquisition catch 吞掉。
- 提取算法不变。

**sec_6k_primary_document_repair.py**（L109-134）：

```python
with source_repository.read_source_snapshot(
    ticker, document_id, SourceKind.FILING, materialize_files=True,
) as snapshot:
    # ... candidate assessment ...
# context exit 后：
if outcome is None:
    return None
_update_active_6k_primary_document(...)
```

- `with snapshot` 管理 lifecycle。
- source mutation 仍在 context exit 后执行。
- caller-owned batch commit/rollback 语义不变。

### 3.5 Production `snapshot.close()` 残留扫描

`grep -rn "snapshot\.close()" dayu/fins/` 结果：**0**。

Test 文件中的 `snapshot.close()` 调用全部属于显式测试 close contract（幂等、重试、cleanup root 保留），不是 consumer 遗留。

### 3.6 测试覆盖

| 测试 | 覆盖行为 |
|---|---|
| `test_snapshot_context_preserves_active_primary_when_close_fails` | active primary + close secondary → primary identity preserved，只追加 path-free action/type/errno note，exception graph path-free |
| `test_snapshot_context_propagates_close_failure_without_active_primary` | 无 primary + close failure → path-free 主异常传播，`__context__` 为 None，显式 close 可重试 |
| `test_snapshot_close_failure_retains_cleanup_root_for_concurrent_retry` | close 失败后 temp root 保留，并发重试只完成一次删除，后续幂等 |

三个测试均通过真实 filesystem + 真实 storage repositories。

### 3.7 裁决

**R07-S2-CR-F01 确认关闭。** Protocol、private implementation、三个 consumer 与 owner-level 测试完整满足 Controller 裁决的四条最小修复边界。

---

## 4. S1 Accepted Findings 保持关闭确认

### R07-S1-CR-F01 — destructive cleanup complete preflight — **保持关闭**

Production evidence 与初始 review 一致：`_validate_complete_source_kind_tree`、`_preflight_filing_cleanup`、`_preflight_processed_cleanup` 均在删除前完成只读完整校验。S2 fix 不涉及 destructive cleanup 路径。

### R07-S1-CR-F02 — `begin_batch` primary-error preservation — **保持关闭**

`begin_batch` state machine 未被 S2 fix 修改。

### R07-S1-CR-F03（含 CR-CV-F01）— path-free filesystem error producer boundary — **保持关闭**

`_fs_storage_utils.py` 投影链未被 S2 fix 修改。S2 新增的 context lifecycle 复用同一 `_append_secondary_error_note`。

---

## 5. S2 Accepted Findings 保持关闭确认

### R07-S2-CV-F01 — `_read_published_marker` guard release 次失败 — **保持关闭**

`_read_published_marker` 三态保留模式未被 S2 fix 修改。

### R07-S2-CV-F02 — snapshot `close()` temp-root cleanup locator — **保持关闭**

`_SnapshotResourceState.close()` 的 locator 保留/重试逻辑未被 S2 fix 修改；context lifecycle 在其上层委托。

### R07-S2-CV-F03 — initial fstat stream close 次失败 — **保持关闭**

`_acquire_snapshot_attempt_unguarded` 的 fstat 主异常保留逻辑未被 S2 fix 修改。

---

## 6. S2 Persisted Opaque Revision 与 Atomic Publication — 无回退

S2 fix 不修改 revision 生成、meta 持久化、`commit_batch` publication、publication guard、recovery journal 或 identity descriptor 逻辑。所有 S2 initial review 验证的 contract 保持完整。

---

## 7. Deferred 边界确认

- S3 read-runtime cache/borrow/citation/file-kind：未进入。
- R08+、Issue 142/151/175/177/178：未进入。
- 统一 authorization：未进入。
- `dayu/fins/tools/read_runtime.py` 中既有 `revision_before`/`revision_after` 与 cache 使用仍属 deferred S3。
- `_resolve_source_kind` filing-first probe 仍属 deferred S3。

无 scope creep。

---

## 8. LLM-facing / README / Security 扫描

- tool schema/description/result/citation 不暴露 `revision`、`storage_key`、`internal_key`、`local://`、`repo_batches`、`repo_backups`、`batch_locks`、absolute temp path。
- `ErrorCode.SOURCE_CHANGED_DURING_READ` 保留既有 code 值，message/hint 不暴露 token/key/path。
- `SourceSnapshotConsistencyError` message 不含 revision 或 locator。
- README trigger：S2 fix 未改变稳定用户/业务 contract，不新增 README 修改。
- 安全行为保持：containment、symlink rejection、filename/URI escape rejection、atomic write/fsync、writer mutex/publication guard/journal recovery 均未删除。

---

## 9. Observations（非 blocker，无需修复）

### 9.1 R07-S2-RR-O01: test `snapshot.close()` 调用属于 contract 测试

Test 文件中的 `snapshot.close()` 调用（`test_fins_storage_atomicity.py` 6 处、`test_fins_storage_provider.py` 1 处）全部用于显式验证 close 幂等、重试、cleanup root 保留等 owner contract 行为，不是 consumer 遗留。Consumer 的 context manager 切换已由 `test_snapshot_context_preserves_active_primary_when_close_fails` 和 `test_snapshot_context_propagates_close_failure_without_active_primary` 覆盖。

### 9.2 R07-S2-RR-O02: `_SNAPSHOT_CONTEXT_CLOSE_ACTION` 常量 private

常量定义在 `_fs_source_snapshot.py`（L61），以 `_` 开头，只在 `_FsSourceSnapshot.__exit__` 中使用。未暴露到 protocol、public API、tool schema 或 LLM-facing text。

### 9.3 R07-S2-RR-O03: fiscal best-effort 不被 context lifecycle 改变

`sec_fiscal_fields.py` 的 acquisition 失败仍返回 `(None, None)`；context lifecycle 的 close failure 不被 acquisition catch 吞掉。这符合 plan "不改 fiscal 推断算法"。

---

## 10. Verdict

**Verdict: PASS**

- **R07-S2-CR-F01**: CLOSED（fix 完整、consumer 切换正确、owner-level 测试覆盖）
- **S1 accepted findings** (CR-F01, CR-F02, CR-F03, CR-CV-F01): 全部保持 CLOSED
- **S2 accepted findings** (CV-F01, CV-F02, CV-F03): 全部保持 CLOSED
- **New material findings**: 0
- **New blockers**: 0
- **Observations**: 3（均 non-blocker）
- **Deferred scope**: S3 边界清晰，无 scope creep
- **Security**: 所有机制保留，无回退
- **Tests**: `401 passed, 3 warnings`；owner-level context lifecycle `3 passed`
- **Static**: pyright `0 errors`，scoped Ruff `All checks passed`，full Ruff baseline 未扩散
- **README**: 无需修改

### 10.1 下一 gate

本 re-review 完成后交回 Controller adjudication。Controller 独立验证后裁决是否进入 R07-S2 accepted implementation commit gate。当前不授权 S1/S2 commit、S3、R08+、deferred Issues、统一 authorization、push 或 PR。

---

**审查完成时间**: 2026-07-16
**审查 Agent**: AgentMiMo
**目标**: Controller adjudication
