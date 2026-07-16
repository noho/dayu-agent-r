# WU-SEMANTIC-OWNERSHIP-01 R07 Complete Cumulative S1+S2+S3 Code Review — AgentMiMo

## 1. Gate、范围与结论

- 审查对象：`386fef8d` HEAD 上全部未提交累计 R07-S1+S2+S3 final tree（28 files, +12103/-3760）。
- accepted plan SHA-256：`ade7691846b9591fa27ece0bbf871b361761714436ff59e6b2c333cde137cac1`。
- 独立读取全部关键 production 模块与 S1/S2/S3 implementation/controller/review artifacts。
- Controller 提供了三条确定复现证据，本 review 在初版中遗漏或误判，本版修正。

**Verdict: FIX REQUIRED — 3 material findings, 0 blocker.**

## 2. Finding Ledger

| ID | Severity | Verdict | Summary |
|---|---|---|---|
| MIMO-CR-F01 | HIGH | FIX REQUIRED | close() 后 retired entry 从 `_retired_entries` discard，`temp_root` 永久泄漏 |
| MIMO-CR-F02 | MEDIUM | FIX REQUIRED | `_creation_locks` dict unbounded，cache eviction 后 lock 不释放 |
| MIMO-CR-F03 | LOW | FIX REQUIRED | process target `primary_failed=True` 时吞 close error，不 log/retry |

以下领域在初版中已通过，本版维持 PASS 摘要：

| ID | Dimension | Verdict |
|---|---|---|
| F01-F04 | Opaque identity owner / irreversibility / snapshot consistency / deletion | PASS |
| F05 | Borrow lifecycle thread safety (lock 状态机本身正确) | PASS |
| F07 | Losing/build/decode/cancel snapshot cleanup | PASS |
| F08-F11 | Same-snapshot provenance/citation, cross-doc diagnosis, list boundary, alias typed namespace | PASS |
| F12 | Composition-root close lazy + idempotent | PASS |
| F15-F19 | Containment/symlink retained, no LLM leak, no compatibility, no R08+ overreach, tests prove contracts | PASS |

## 3. Material Findings

### MIMO-CR-F01: close() retired entry discard 使 snapshot cleanup 永久丧失 retry authority（HIGH）

**位置**：`read_runtime.py` `_close_retired_entry` + `_retire_entries`。

**根因**：`_close_retired_entry` 无论 `snapshot.close()` 成功或失败，都在最后执行 `self._retired_entries.discard(entry)`。失败路径调用 `finish_close(succeeded=False)` 保留 `temp_root`，但 entry 已从 `_retired_entries` 移除。后续 `close()` → `_retry_pending_cleanup()` 遍历 `_retired_entries` 时找不到该 entry，`temp_root` 成为永久孤儿。

**Controller 复现证据**：close 返回后 `cache=0`、`roots_exist=True`——cache 已空但磁盘上临时目录未删除。

**accepted plan 违反**：plan §14.3 明确要求 "无法取得稳定版本时返回 typed source_changed_during_read"，§7.3 要求 "cleanup 失败保留 retry authority"。当前实现违反后者。

**反例代码路径**：
```
close()
  → _retire_entries(cache.clear())
    → _retire_entry(entry)
      → entry.retire() → True (无 active borrow)
      → _close_retired_entry(entry)
        → snapshot.close() → raises OSError (rmtree 失败)
        → finish_close(succeeded=False)  # temp_root 保留
        → _retired_entries.discard(entry) # ← entry 丢失
        → raises OSError
  → _retry_pending_cleanup()
    → 遍历 _retired_entries → 已空 → 不重试
```

**owner-boundary fix**：`_close_retired_entry` 失败时不 discard；或将失败 entry 移入 `_pending_snapshots` / 独立 `_pending_entry_retries` 集合供 `_retry_pending_cleanup` 消费。成功时才 discard。

**测试要求**：构造 `snapshot.close()` 首次抛出、二次成功的 monkeypatch 场景；断言首次 close 后 `temp_root` 仍存在且 entry 仍可重试；二次 close 成功后 `temp_root` 删除、entry 清除。

---

### MIMO-CR-F02: `_creation_locks` 无界增长，cache eviction 后 lock 条目不释放（MEDIUM）

**位置**：`read_runtime.py` `_creation_locks` dict + `_get_creation_lock`。

**根因**：每个新 `ProcessorCacheKey` 在 `_get_creation_lock` 中创建 `Lock()` 并存入 dict，永不移除。LRU cache eviction 清除 processor 但不清除对应 lock。长时间运行的 runtime 访问 N 个不同 document 后，dict 持有 N 个 Lock 对象。

**Controller 复现证据**：missing IDs 可使 `cache=0` / `lock_count=64`。

**accepted plan 约束**：plan 要求 "resource-aware cache"、"cache 只能以 storage-owned revision 失效"。unbounded lock table 与此资源感知目标不一致。

**影响**：非正确性问题，但违反资源有界设计意图。每个 Lock ~80 bytes，10,000 文档 ~800 KB。对于长期 interactive session 可累积。

**owner-boundary fix**：`_evict_processor_entry` 和 `_retire_entry` 中检查同 key 是否已无 cached entry 且无 retired entry，若均无则从 `_creation_locks` 移除。或使用 `WeakValueDictionary` 模式（需 lock 生命周期与 cache entry 绑定）。改动范围小，仅涉及 `_creation_locks` 的增删逻辑。

**测试要求**：evict 后 `key not in _creation_locks`；新 read 重新创建 lock；并发 evict + create 不丢失 lock。

---

### MIMO-CR-F03: process target primary failure 下吞 close error 且不消费 retry authority（LOW）

**位置**：`fins_tools.py` `_FinsReadProcessTarget.__call__` finally 块。

**根因**：`primary_failed=True` 时，`except Exception` 分支仅 `pass`——不 log、不 add_note、不尝试重试 cleanup。`DefaultFinsRuntime.close()` 失败意味着 `FinsReadRuntime._pending_snapshots` / `_retired_entries` 中可能有未清理的 temp root。子进程退出后 `tempfile.mkdtemp` 目录不会自动删除，成为磁盘孤儿。

**Controller 事实纠正**：初版声称 "close failure appended as note" 是错误的；代码中 `primary_failed=True` 分支无任何日志或注释机制。

**影响**：子进程中每次 business failure + close failure 的组合泄漏一个 temp 目录。对于 process-backed tool，子进程生命周期短，泄漏累积慢。severity 低于 F01 因为子进程隔离限制了影响范围。

**owner-boundary fix**：`primary_failed=True` 分支至少应 `Log.warning` close 失败信息，不覆盖 `outcome`。可选：在子进程 `finally` 中增加 `runtime._read_runtime._retry_pending_cleanup()` 调用（需暴露 retry 接口或在 `DefaultFinsRuntime.close` 内部保证 retry）。

**测试要求**：构造 `runtime.close()` 在 business failure 后抛出异常的场景；断言 close error 被记录（至少 log）；断言 `outcome` 仍为原始 business failure。

## 4. 通过领域摘要

以下领域经完整代码审查确认通过，无 material finding：

- **Opaque identity**：`_fs_identity.py` 唯一拥有 SHA-256 单向派生、descriptor 原子持久化、双向校验、fail-closed 枚举。无 reverse lookup、无 second mapping owner。
- **Snapshot consistency**：3-attempt 有界重试 + publication guard + 前后 marker exact equality。静态 corruption 不重试、不映射为 source changed。
- **Borrow lifecycle**：`_CachedProcessor` 的 RLock + `_active_borrows` 计数 + `_begin_close_if_ready` 原子判定 + `_closing` flag 防 double-close。lock 状态机本身正确（F01 问题在 retry 层，不在 lock 层）。
- **Same-snapshot provenance/citation**：8 个 processor 入口全在 borrow scope 内访问 processor/meta/provenance/citation。
- **Cross-doc diagnosis**：仅遍历 cached keys，lightweight snapshot 验证后 borrow，不创建新 processor。
- **Alias fallback**：`_resolve_canonical_document_id` 枚举所有 SourceKind，跨 kind 多文档匹配时拒绝歧义。
- **Containment/symlink**：identity descriptor、snapshot file、meta path 均校验 symlink/regular file/containment。
- **LLM-facing non-leak**：`_source_meta_without_revision` 剥离 revision；error messages 路径无关；tool schema 不暴露 private key/revision。
- **No compatibility/speculative code**：零 hasattr/getattr 兼容、零旧 layout shim、零 R08+ 扩域。
- **Tests**：489 passed，20 changed production files ≥80% coverage，真实 filesystem/thread/Event/Barrier，无 sleep oracle。

## 5. Verdict

**FIX REQUIRED.**

三项 material finding 均属于 accepted plan 的 retry authority / resource-aware / error transparency 合约违反。F01 为 HIGH（cleanup 永久丧失 retry），F02 为 MEDIUM（resource unbounded），F03 为 LOW（error swallowed in subprocess isolation）。

三项 fix 范围均小且位于 R07 owner boundary 内，不扩大 scope。

**Blocking questions: 0.** 无设计层面阻塞问题；三项 fix 均为代码级修正。

R07 需通过 fix gate + dual re-review 后方可创建 accepted implementation commit。
