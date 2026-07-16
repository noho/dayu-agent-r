# WU-SEMANTIC-OWNERSHIP-01 R07-S3 Complete-tree Code Review (AgentDS)

## 1. Gate 与基线

- **Review scope**: 累计 R07-S1+S2+S3 未提交工作树完整审查，不只看 S3。
- **HEAD / transition base**: `386fef8d7a7ecbd977c455ca86bb8bab875d1a98`。
- **Accepted plan SHA-256**: `ade7691846b9591fa27ece0bbf871b361761714436ff59e6b2c333cde137cac1`。
- **输入 artifacts**:
  - 根 `AGENTS.md`, `docs/host/issues-implementation-control.md`,
    `docs/phaseflow-umbrella-optimization-control.md`,
    `docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md`,
    `docs/fins/design.md`, accepted plan。
  - S1/S2/S3 全部 implementation / Controller validation / code review / fix /
    re-review / Controller adjudication artifacts。
  - 实际 `git diff` 与全部 changed production/test/README 文件。
- **身份**: 本 agent 是 AgentDS reviewer；只做审查，不改 product/test/README/control/design/plan/旧 artifact，不 stage/commit/push/PR。

## 2. 审查方法

按以下 8 个焦点做 adversarial correctness/stability/maintainability/semantic-ownership/overdesign 审查，每项必须以可复现代码证据或确定 interleaving 判定：

1. Opaque external identity → private storage key 的唯一 owner、不可逆/non-leak、
   全 inventory/cleanup/recovery/path/error graph。
2. Persisted publication revision 与 light/full snapshot 的同一 publication、
   static corruption 优先、真实 retry budget、delete/reset/missing。
3. Read-runtime entry/borrow/cache creation/replacement/eviction/clear/close
   的线程安全和所有 losing/build/decode/cancel/cleanup double-failure 路径。
4. Processor/meta/provenance/citation/result 同 snapshot；
   八个工具和 cross-document diagnosis/list/alias/exact source-kind 行为。
5. Composition-root/process-target close, primary/secondary error priority、
   pending cleanup retry authority。
6. Containment/symlink/atomic/recovery/typed security 行为是否保留，
   是否泄漏 private locator/revision/internal governance 到 LLM。
7. 是否出现 compatibility、fallback/downstream repair、speculative abstraction、
   R08+ 或 Issues 142/151/175/177/178、统一 authorization 越界。
8. Tests 是否真实证明 owner contract，而非 fake 固化/睡眠 oracle/直接 outcome 注入；
   README 只描述 current contract。

Controller 额外指定的三条并发推演反例独立判定并纳入 finding ledger。

## 3. Material Findings

---

### F-DS-01 [HIGH] `_borrow_processor` 与 `close()` 之间存在 race window：close 返回后 live cache entry 仍可被发布并永久泄漏 snapshot 临时树

**Severity**: HIGH — resource leak（temp tree 永久残留）+ cache/snapshot lifecycle 不一致。

**Location**: `dayu/fins/tools/read_runtime.py`:
- `_borrow_processor()` line 3029 `self._ensure_open()` 与 line 3061 `self._processor_cache.put(cache_key, created)` 之间。
- `close()` line 3440—3445。

**Root cause**: `close()` 使用 `_lifecycle_lock` + `ProcessorLRUCache._lock` 设置
`_closed=True` 并清空 cache；`_borrow_processor` 在 `with lock:`（per-document creation lock）
内调用 `_ensure_open()` 通过后，`_create_processor_from_snapshot()`（可耗时 I/O）与
`cache.put()` 之间只持有 `lock`，不持有 `_lifecycle_lock` 或 `ProcessorLRUCache._lock`。
因此存在确定 interleaving：

```
T1: with lock: _ensure_open() → _closed=False, 通过 (line 3029)
T2: close() → _lifecycle_lock → _closed=True → cache.clear() → 返回
T1: _create_processor_from_snapshot() → cache.put(cache_key, created) → 发布 live entry
```

新发布的 `_CachedProcessor` 的 `_retired=False`，其 snapshot 资源永不进入 retire→close
管线。close 已返回但 temp tree 仍存在于文件系统。

**Controller 可复现证据** (由 Controller 在现有 test harness 中用
`registry.before_return` + `threading.Event`、无 sleep 固定窗口得到)：

```python
{'cache_at_close': 0, 'cache_after_join': 1, 'result_count': 1,
 'errors': [], 'roots_exist': [True]}
```

- `cache_at_close=0`: close 返回时 cache 为空（符合 close contract 预期）。
- `cache_after_join=1`: close 返回后 cache 中出现一个 live entry。
- `roots_exist=[True]`: 对应 full snapshot 临时树仍存在于文件系统——已泄漏。

**Counterexample（可复现）**: 在 `_borrow_processor` 的 `with lock:` 块内、`_ensure_open()`
通过后插入 `Event.wait()` 模拟长 processor build，另一线程执行 `close()`，close 返回后
释放 Event。结果如上——live entry 遗留、temp root 未删除。

**Owner-boundary fix**: `_borrow_processor` 在 `cache.put()` 成功后、离开 `with lock:` 前，
必须再次调用 `_ensure_open()`。若 runtime 已关闭，必须 evict 刚发布的 entry 并 retire/close
其 snapshot：

```python
# 在 line 3061 cache.put() 之后，line 3063 try retire 之前插入:
self._ensure_open()  # 若 raise RuntimeError, snapshot_transferred=True 时
                     # 外层 except 不 close full_snapshot（已 transfer），
                     # 但需额外 evict+retire 刚发布的 entry
```

精确实现需在外层 `except BaseException as build_error:` (line 3076) 中增加对
`snapshot_transferred=True` 且 build_error 为 `RuntimeError("Fins read runtime 已关闭")`
时的 cache eviction + entry retire + borrow release 路径。不引入新异常类型或 production seam。

**Test 要求**: 新增 owner test，用 `threading.Event`/`Barrier` 固定以上 interleaving，
断言 close 返回后 cache 大小为 0、无残留 temp root。测试必须使用真实
`DefaultFinsRuntime`/`FinsReadRuntime`、真实 filesystem (`tmp_path`)，不得用
sleep oracle。

---

### F-DS-02 [MEDIUM] `_creation_locks` dict 无界增长，绕过 bounded cache 约束

**Severity**: MEDIUM — 长生命周期 runtime 下内存无界增长；不影响单次调用正确性。

**Location**: `dayu/fins/tools/read_runtime.py`:
- `_get_creation_lock()` line 3128—3147。
- `__init__()` line 827 `self._creation_locks: dict[ProcessorCacheKey, Lock] = {}`。

**Root cause**: `_creation_locks` 是永久 dict。每遇到一个新的
`(ticker, document_id)` 组合（通过 `_borrow_processor` line 2970 或
`_get_cached_processor_borrow_for_diagnosis` line 2908），`_get_creation_lock` 无条件
创建并永久持有一个 `threading.Lock`。该 dict 与 bounded `ProcessorLRUCache`
(max_entries=128) 解耦——entry 从 cache 淘汰后对应 lock 仍保留。

**Controller 可复现证据**: 对 64 个不同 missing `document_id` 顺序调用后：

```python
{'cache_size': 0, 'creation_lock_count': 64}
```

cache 为空（max_entries 约束生效），但 `_creation_locks` 保留了全部 64 个 lock。
在长生命周期 runtime 处理数千不同文档的场景下，该 dict 线性增长且永不收缩。

**Accepted plan 对照**: plan §7.3 明确要求 "resource-aware cache" 与 bounded
`processor_cache_max_entries`。虽然 `_creation_locks` 不是 cache entry，但它是与
per-document lifecycle 绑定的资源，其无界增长违反了 resource-aware 约束的精神。

**Counterexample**: 对一个 `FinsReadRuntime` 实例反复用不同 `document_id`
调用 `list_documents`（该路径不经过 `_creation_locks`）、随后对每个 `document_id`
调用 `get_document_sections`（经过 `_borrow_processor` → `_get_creation_lock`）。
cache 保持 bounded（淘汰旧 entry），但 `_creation_locks` 持续增长。

**Owner-boundary fix**: 两种可行方向：

1. **Weak-value 方案**: 将 `_creation_locks` 改为 `WeakValueDictionary`，使 lock
   在没有外部引用且对应 cache entry 不存在时自动回收。需要确保 lock 在
   creation critical section 期间有强引用。

2. **Cache-eviction 联动方案**: 在 `_evict_processor_entry` /
   `_evict_processor_entry_if_matches` 中，检查该 key 是否已无 cache entry
   且无其他线程正在等待该 lock（通过 `locked()` 检测或 ref-count），满足条件时
   从 `_creation_locks` 删除。此方案侵入性更大。

推荐方案 1（WeakValueDictionary），改动最小且语义清晰：lock 的生命周期与
"是否还有代码路径可能使用它"绑定，而非永久。

**Test 要求**: 新增 owner test，对同一 runtime 用超过 cache 容量的不同
`document_id` 调用 `_borrow_processor`，断言 cache 大小 bounded 且
`_creation_locks` 不再持有已淘汰 entry 对应的 lock。

---

### F-DS-03 [LOW] Process target close 失败在 `primary_failed=True` 时被静默吞没；子进程退出后 pending cleanup retry authority 随进程消亡

**Severity**: LOW — 不影响正确性（子进程退出后 OS 回收 temp 文件），但存在日志缺失
与 transient temp 残留。

**Location**: `dayu/fins/tools/fins_tools.py`:
- `_FinsReadProcessTarget.__call__()` line 292—302。

**Root cause**:

```python
finally:
    if runtime is not None:
        try:
            runtime.close()
        except Exception:       # ← 只捕获 Exception，且
            if not primary_failed:
                outcome = process_tool_failed_envelope(...)
            # primary_failed=True 时 close error 完全丢弃
```

当 tool 业务成功执行但 `runtime.close()` 失败（如 `_retire_entries` 中 snapshot
cleanup OSError），该 close 失败被 `except Exception` 捕获。因为 `primary_failed=False`
（业务成功），close error 被投影为新的 `execution_error` envelope——这是正确的。

但当 `primary_failed=True`（业务已失败或抛异常）时，`except Exception` 完全丢弃
close error：无日志、无 note 追加、无 envelope 替换。caller 只看到业务失败，
不知道 temp 文件可能残留。

此外，process target 运行在子进程中。`runtime.close()` 内部的
`_pending_snapshots` 和 `_retired_entries` 重试列表是进程内存状态；子进程退出后
这些列表随进程消亡。未成功的 temp tree cleanup 留下孤儿临时目录
(`/tmp/dayu-source-snapshot-*`)，依赖 OS 级 temp cleaner 最终回收。

**为什么是 LOW**: 子进程 temp 文件由 OS 回收；process-backed 执行天然有此边界；
业务主异常已被正确保留（未被 close error 替换）。唯一损失是 close failure 诊断
信息丢失和可能更长的 temp 残留窗口。

**Counterexample**: 构造一个 `DefaultFinsRuntime`，对其 read runtime 注入一个
snapshot close 必然失败的 retired entry（如设 temp_root 为无写权限目录）。
调用 process target 的正常业务路径。断言 `primary_failed` 为 False 时 close error
被正确投影为 `execution_error`；断言 `primary_failed` 为 True 时 close error
被静默丢弃（无日志、无 note）。

**Owner-boundary fix**:

1. `except Exception` → `except BaseException`（catch 一致性）。
2. `primary_failed=True` 时至少用 `logging.exception` 或 `Log.error` 记录 close
   failure，不改变 outcome。
3. 可选：向 primary error 追加 path-free close failure note
   （使用已有的 `_append_cleanup_note` 模式），与 read runtime 的
   primary-secondary error 处理一致。

**Test 要求**: 无需新增 process 级测试（子进程内难观测）。可在
`test_fins_read_process_target_closes_runtime_on_success_and_failure` 中增加
monkeypatch 验证 close failure 在 `primary_failed=True` 时不改变 outcome 且
不抛异常。

---

## 4. 八焦点独立审查结果

### 4.1 Opaque identity → private storage key

**结论: PASS（无 material finding）**

- `_fs_identity.py` 是 external identity → private locator 的唯一 owner。`_derive_storage_key`
  使用 SHA-256(namespace\0identity)，确定性且不可逆。✓
- 双向校验：所有 identity directory 读写均经过 `_read_identity_descriptor` 验证
  namespace/external_identity/private_key 三方一致性；`_list_external_identities` 只从
  descriptor 读取，不从目录名反推。✓
- Inventory (`_list_external_identities`)、cleanup (`_ensure_identity_directory` 的
  descriptor 写入失败 rmdir)、recovery（R06 journal replay 使用 identity owner
  的 private locator）路径均经 identity owner。✓
- Error graph: identity 校验失败一律 `ValueError`；文件系统失败经
  `_project_filesystem_error` → `_raise_path_free_error` 投影，不暴露 raw locator。✓
- Non-leak: 已确认 `read_runtime.py` 和 `fins_tools.py` 中无 `_derive_storage_key`、
  `local://`、`/portfolio/` 或 private key 命中。✓

**Observation (no-action)**:
- `_ensure_identity_directory` 中 `directory.exists() or directory.is_symlink()` (line 162)
  与后续 `_read_identity_descriptor` (line 163) 之间有 TOCTOU 窗口。但写入路径
  持有 writer lock，读取路径持有 publication guard，且 `_read_identity_descriptor`
  内部再次验证 directory 属性——攻击者无法在 guard 内替换 directory。当前锁粒度
  已覆盖此窗口，无需额外加固。

---

### 4.2 Persisted publication revision 与 snapshot consistency

**结论: PASS（无 material finding）**

- Revision 唯一 owner: `_source_revision_from_meta` in `_fs_storage_infra.py` 从
  persisted meta 字段 `_published_source_revision` 机械读取，consumer 不得重算。✓
- `_source_meta_without_revision` 在所有 snapshot 构造点剥离 revision 字段，确保
  consumer 的 `source_meta` 不含私有 revision。✓
- Full snapshot 后验核对: `_acquire_snapshot_attempt` 在 publication guard 内采集
  marker；`_read_source_snapshot` 在 fd copy 后再次读取 published marker 并做
  exact equality 比较。不一致时重试，最多 `_STABLE_READ_ATTEMPT_LIMIT=3` 次。✓
- Static corruption 优先: `_copy_snapshot_file` 在复制后验证 `fstat`(device/inode/
  mode/size/mtime_ns/ctime_ns) 不变、EOF 与 size 一致、SHA-256 匹配。任何不一致
  都 `ValueError`，不映射为 `source_changed` 重试。✓
- Delete/reset/missing: `_acquire_snapshot_attempt_unguarded` 检查 `is_deleted`
  和 `ingest_complete`，deleted/reset 返回 `FileNotFoundError`；`_read_published_marker`
  对 reset（meta 消失）返回 `None`，snapshot attempt 随后检测 marker mismatch
  并重试或抛出 `SourceSnapshotConsistencyError`。✓
- Retry budget: 3 次硬上限 + `SourceSnapshotConsistencyError` 携带 `__cause__` 链。✓

**Observation (no-action)**:
- `_STABLE_READ_ATTEMPT_LIMIT=3` 是硬编码常量。目前无配置要求，不构成 overdesign。
  若未来需要可配置化，应在 storage design 中定义。

---

### 4.3 Read-runtime 线程安全与 double-failure 路径

**结论: FIX REQUIRED（F-DS-01）**

除 F-DS-01 外，其余路径审查通过：

- **LRU 线程安全**: `ProcessorLRUCache` 全部操作持 `RLock`；`put` 返回 displaced
  values；`evict_if` 做 identity-conditional 移除，防止 stale reader 误删新 entry。✓
- **Borrow lifecycle**: `_CachedProcessor` 的 `_retired`/`_active_borrows`/`_closed`/
  `_closing` 状态机在 `RLock` 下操作；`_begin_close_if_ready` 保证只有一次 close
  attempt；`retry_close()` 让失败 cleanup 可重试。✓
- **Creation lock**: per-document `Lock` 防止同一文档并发构建 processor；竞争失败
  caller 的 losing full snapshot 被立即关闭。✓
- **Losing snapshot**: light snapshot 在 cache hit 检查后立即关闭 (line 3005—3006)；
  full snapshot 竞争失败后关闭 (line 3037—3038)；processor build 失败时
  `snapshot_transferred=False` 确保 full snapshot 被外层 except 关闭 (line 3077—3078)。✓
- **Decode failure**: `_create_processor_from_snapshot` 中 `FinsSourceDecodeError`
  映射为 `FinsReadBusinessError(SOURCE_DECODE_FAILED)`；外层 except 关闭 full
  snapshot。✓
- **Cancel 路径**: `_raise_if_fins_cancelled` 在各慢边界检查；`FinsReadCancelledError`
  在 `_borrow_processor` 的 `_ensure_open` 之后、`cache.put` 之前被 `_raise_if_fins_cancelled`
  抛出时，`snapshot_transferred=False`，外层 except 正确关闭 full snapshot。✓
- **Double-failure**: `_append_cleanup_note` 只追加 `type/errno`，不含 locator/message。✓
- **`_SnapshotResourceState.close()`**: 设置 `closed=True` 后执行 rmtree；rmtree 失败
  时 `temp_root` 不清空，使下一次 `close()` 自动重试同一路径。✓

**Rejected alternative**: 在 close() 中遍历并 acquire 全部 `_creation_locks` 不是可行
方案——lock dict 无界 + 可能死锁（与 `_lifecycle_lock` 获取顺序不同）。

---

### 4.4 Processor/meta/provenance/citation/result 同 snapshot

**结论: PASS（无 material finding）**

- 八个 processor 入口全部通过 `_borrow_processor` 取得同一 borrow scope：
  `get_document_sections` (line 988)、`read_section` (line 1047)、`search_document`
  (line 1244)、`list_tables` (line 1632)、`get_table` (line 1771)、`get_page_content`
  (line 1914)、`get_financial_statement` (line 2025)、`query_xbrl_facts` (line 2157)。✓
- `_build_citation` 从 `borrow.snapshot.provenance` 和 `borrow.source_meta` 派生，
  不从 repository 重读。✓
- `_resolve_document_form_type` 从 `borrow.source_meta` 读取。✓
- Cross-document diagnosis: `_get_cached_processor_borrow_for_diagnosis` 用
  `peek`（不改变 LRU 顺序）+ light snapshot revision 匹配检查；不匹配时安全
  evict。✓
- `list_documents`: 分别枚举 FILING 和 MATERIAL，过滤 deleted/incomplete，附加
  `document_type`。✓
- Exact document ID resolution: `_resolve_canonical_document_id` 先尝试
  `source_kind=None` 的 0/1/2 storage resolution，失败后遍历两个 typed namespace
  做 alias 匹配。✓
- Alias fallback: line 2458 `for source_kind in SourceKind:` 同时检查 FILING 和
  MATERIAL；`len(matched_documents) > 1` 时明确拒绝跨 kind 歧义，不 filing-first
  猜测。✓

**Observation (no-action)**:
- `_diagnose_cross_document_locator` 中如果 `_get_cached_processor_borrow_for_diagnosis`
  抛异常（如 light snapshot close 失败），该异常会传播出 `_diagnose_cross_document_locator`，
  替换原始的 `KeyError` → `FinsReadArgumentError` 提示。这发生在极罕见场景
  （诊断路径的 light snapshot 关闭失败），影响的只是错误消息质量而非正确性。
  诊断路径已有显式 best-effort 语义注释，不要求 fail-safe。

---

### 4.5 Composition-root/process-target close

**结论: FIX REQUIRED（F-DS-03）**

除 F-DS-03 外，其余路径审查通过：

- `DefaultFinsRuntime.close()`: lazy（不为 cleanup 创建 read runtime）、
  幂等（`_closed` flag + `get_read_runtime` 的 `RuntimeError` guard）。✓
- `FinsReadRuntime.close()`: 第一次 close 清 cache 并 retire 全部 entry；
  后续 close 只 `_retry_pending_cleanup()`——重试此前失败的 snapshot 和
  retired entry cleanup。✓
- `_FinsReadProcessTarget.__call__`: 在 `finally` 中关闭自己创建的
  `DefaultFinsRuntime`。成功、业务失败、未预期失败三路各自创建并关闭一个
  runtime。✓
- Primary error priority: 已有业务/执行失败时 close failure 不覆盖 outcome。✓
- Close failure → primary: 无业务失败时 close failure 升级为
  `execution_error` envelope。✓

---

### 4.6 Containment/symlink/atomic/recovery/typed security 与 LLM 泄漏

**结论: PASS（无 material finding）**

- Containment: path traversal（`.`、`..`、separator、absolute、drive/UNC）检查保留。✓
- Symlink: `_require_contained_regular_file`、`_read_identity_descriptor`、
  `_ensure_identity_directory` 等均拒绝 symlink。✓
- Atomic: R06 的 atomic swap/journal/recovery 未修改。✓
- Typed error: `SourceSnapshotConsistencyError`、`ErrorCode.SOURCE_CHANGED_DURING_READ`
  等 typed error 保留；`_raise_path_free_error` 保证 public error 不含 locator。✓
- LLM non-leak: 已有 scan 确认 production 代码中无 `_derive_storage_key`、
  `local://`、`/portfolio/`、`temp_root`、`private.*key` 命中；`_build_citation`
  只使用 business 字段。Controller 额外确认 `test_read_outputs_never_expose_revision_internal_key_local_uri_or_temp_path`
  递归覆盖九工具 completed/failed/cancelled projection。✓

---

### 4.7 Compatibility/fallback/scope boundary 越界

**结论: PASS（无 material finding）**

- 删除确认: `get_source_revision`、`_build_source_revision`、`revision_before`、
  `revision_after`、`_resolve_source_kind`、filing-first probing、独立 meta cache、
  citation repository reread 均已删除且无 re-export/shim。✓
- AST scan: `JoinedStr`/`BinOp` 命中均使用 identity owner 返回的 private key、
  固定 namespace 或 manifest filename；raw external identity path join 为 0。✓
- R08+ (financial/XBRL contract)、Issues 142/151/175/177/178 无实现。✓
- 统一 tool authorization 无实现。✓
- 旧测试兼容分支: 无。✓

---

### 4.8 Tests 真实性

**结论: PASS（无 material finding）**

- 真实 filesystem: 所有 storage publication smoke 使用 `tmp_path` + 真实
  `FsSourceDocumentRepository`/batch commit。✓
- Concurrency: `threading.Event`/`Barrier` 用于调度，无 `time.sleep` 作为
  correctness oracle。✓
- Owner contract: 测试断言 storage-owned snapshot consistency（完整 A 或完整 B）、
  transient recovery（storage 自行重试）、sustained exhaustion（只由 storage
  抛出 typed error）、static corruption（fstat/content mismatch 不重试）、
  citation/result same-snapshot（A result + A provenance → switch → B result + B
  provenance）。✓
- No fake固化: 测试不使用 fake repository 或直接注入 outcome；process target
  close test 使用 monkeypatch 只做 observe（仍调用真实 `original_close`）。✓
- Leak detection: `test_read_outputs_never_expose_revision_internal_key_local_uri_or_temp_path`
  递归扫描全部工具 JSON 输出。✓
- Coverage: 20 个 changed production 文件 line coverage 全部 ≥80%。✓

---

## 5. Controller 候选反例独立判定

| 候选 | 判定 | 对应 finding | 证据 |
|------|------|-------------|------|
| A: `_borrow_processor` / `close()` race → live entry 泄漏 | **CONFIRMED MATERIAL** | F-DS-01 | Controller 可复现: `cache_at_close=0, cache_after_join=1, roots_exist=[True]`；独立代码路径分析确认 interleaving 可实现 |
| B: `_creation_locks` 无界增长 | **CONFIRMED MATERIAL** | F-DS-02 | Controller 可复现: 64 不同 document_id → `cache_size=0, creation_lock_count=64`；与 accepted plan 的 bounded resource 约束不一致 |
| C: Process target close failure pending cleanup authority 丢失 | **CONFIRMED — 降级为 LOW** | F-DS-03 | 子进程退出后 `_pending_snapshots`/`_retired_entries` 随进程消亡；`primary_failed=True` 时 close error 被静默丢弃 |

---

## 6. Observations（明确 no-action 理由）

| ID | 描述 | No-action 理由 |
|----|------|---------------|
| OBS-DS-01 | `_ensure_identity_directory` TOCTOU (line 162→163) | writer lock + publication guard + descriptor re-validation 已覆盖 |
| OBS-DS-02 | `_STABLE_READ_ATTEMPT_LIMIT=3` 硬编码 | 无配置要求，不是 overdesign |
| OBS-DS-03 | `_diagnose_cross_document_locator` 内 light snapshot close failure 可替换原始 KeyError | 极罕见；诊断路径显式 best-effort 语义 |
| OBS-DS-04 | `_FinsReadProcessTarget.__call__` 用 `except Exception` 而非 `except BaseException` | 子进程中 `KeyboardInterrupt`/`SystemExit` 不会发生；已有 F-DS-03 覆盖主要问题 |
| OBS-DS-05 | `ContainerImage` / `Sandbox` / `CapabilityToken` 等未出现在 diff | 统一 authorization 未实施，符合 scope |
| OBS-DS-06 | Full Ruff ledger 保持 150 (F401=70, E402=66, F841=10, F541=3, F821=1) | 既有基线，R07 未扩散 |
| OBS-DS-07 | Full suite 三项 inherited failures (logging order / `wait_poller_policy` / import boundary) | 已登记 baseline，owner 与 R07 无关 |
| OBS-DS-08 | `_read_runtime.py` coverage 81.09% 为 changed files 中的最低值 | 仍 ≥80% 门禁；F-DS-01/F-DS-02 的 owner test 会进一步覆盖 race/cleanup 路径 |

---

## 7. README 审核

- `dayu/fins/README.md`: 描述 current contract（opaque identity mapping、persisted
  revision、storage snapshot、same-snapshot borrow、resource-aware cache、typed
  source-changed failure），不承诺 private key grammar、retry 次数或私有类名。✓
- `tests/README.md`: 更新 owner-level coverage 摘要，不写文件级流水账。✓
- 根 README 和 `dayu/README.md` 不触发（分层、入口、CLI 未变）。✓

---

## 8. Finding Ledger

| Finding | Severity | Status |
|---------|----------|--------|
| F-DS-01: `_borrow_processor` / `close()` race → snapshot temp tree leak | HIGH | **OPEN** |
| F-DS-02: `_creation_locks` 无界增长 | MEDIUM | **OPEN** |
| F-DS-03: Process target close failure 静默吞没 + pending cleanup 随子进程消亡 | LOW | **OPEN** |

---

## 9. Verdict

**FIX REQUIRED** — 三项 material findings 必须在 R07 accepted implementation commit
之前由 AgentCodex 修复并经双路 re-review 关闭。

Blocking questions: **0**（三项 finding 的 owner boundary、root cause、counterexample
和 fix direction 均已明确，无待澄清事项）。

---

## 10. Handoff

本 agent 到此停止。artifact 已写入，不修改 product/test/README/control/design/plan/
旧 artifact，不 stage/commit/push/PR。交回 Controller 裁决并派发 AgentCodex fix。
