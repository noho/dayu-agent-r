# WU-SEMANTIC-OWNERSHIP-01 R07 Complete Cumulative S1+S2+S3 Code Re-Review — AgentDS

## 1. Gate 与基线

- **角色**: AgentDS，执行既有 umbrella `WU-SEMANTIC-OWNERSHIP-01` 的 R07 完整累计 S1+S2+S3 code re-review；不是新 WU，不是 umbrella aggregate deepreview。
- **审查对象**: HEAD `386fef8d7a7ecbd977c455ca86bb8bab875d1a98` 上全部未提交累计 R07-S1+S2+S3 final tree（28 files, +12555/-3758）。
- **Accepted plan SHA-256**: `ade7691846b9591fa27ece0bbf871b361761714436ff59e6b2c333cde137cac1`。
- **Controller finding 真源**: `docs/reviews/wu-semantic-ownership-01-r07-s3-code-review-controller-adjudication.md`。
- **AgentCodex fix artifact**: `docs/reviews/wu-semantic-ownership-01-r07-s3-code-review-fix-codex.md`。
- **Controller fix validation**: `docs/reviews/wu-semantic-ownership-01-r07-s3-code-review-fix-controller-validation.md`。
- **输入 artifacts**: 根 `AGENTS.md`、`docs/fins/design.md`、accepted plan，以及 S1/S2/S3 全部 implementation / Controller validation / review / fix / re-review / Controller adjudication 链条。
- **本 artifact 写入边界**: 只创建/修改本文；不改 production、test、control、design、plan、README、旧 artifacts；不 stage/commit/push/PR。

## 2. 审查方法

按以下 7 个焦点对 final cumulative tree 做 adversarial correctness/stability/maintainability/semantic-ownership 审查：

1. **R07-CR-F01**: close/publication 线性化与两序行为（close-first / publication-first）的 root-cause closure。
2. **R07-CR-F02**: weak creation-lock overlap/reclamation 的 root-cause closure。
3. **R07-CR-F03**: public close follow-up/outcome priority/path-free diagnostics/真实 cleanup retry 的 root-cause closure。
4. **S1 accepted findings 保持关闭**: R07-S1-CR-F01（destructive cleanup preflight）、R07-S1-CR-F02（begin_batch primary error）、R07-S1-CR-F03（path-free error projection）。
5. **S2 accepted findings 保持关闭**: R07-S2-CR-F01（snapshot context-manager lifecycle）。
6. **S3 既有 PASS 领域保持**: opaque identity/snapshot/revision/citation/opaque non-leak、typed errors、security containment/symlink/atomic/recovery、LLM-facing 边界、无 deferred Issues/统一 authorization 越界。
7. **No new regression**: 本 fix gate 是否引入新缺陷、测试是否真实、Event 协调有无 sleep oracle。

每项判定必须以可复现代码证据或确定 interleaving 支撑；不得复述已被 Controller 驳回的 `_close_retired_entry` 错误根因或 OS auto-cleanup 假设。

## 3. R07-CR-F01..03 逐项 root-cause closure 验证

### 3.1 R07-CR-F01 [HIGH] — close 与 cache publication 线性化

**Claimed root cause**: processor build 在 `_borrow_processor` 内通过 `_ensure_open()` 后，可在不持 `_lifecycle_lock` 的情况下发布 cache entry；`close()` 可能先设置 `_closed`、清空 cache 并返回，随后 build 再发布 live entry。

**Claimed fix**: 在 `cache.put()` 前、processor 构建完成后，以 `_lifecycle_lock` 保护最终 `_ensure_open()` + `cache.put()`，使 closed-check 与 publication 与 `close()` 的 `_closed=True` 状态切换共享同一线性化锁。

**DS 独立验证**:

- **production 代码证据** (`dayu/fins/tools/read_runtime.py`):
  - Lines 3062-3067: processor 构建完成后，`with self._lifecycle_lock: self._ensure_open(); displaced = self._processor_cache.put(cache_key, created)`。长 processor 构建（I/O）不持锁，只在最终 publication 临界区持 `_lifecycle_lock`。✓
  - Lines 3445-3449: `close()` 同样在 `_lifecycle_lock` 内设置 `self._closed = True`，然后执行 `cache.clear()`。✓
  - 两个方向共享同一 owner lock：close-first → build 在 `_ensure_open()` 抛 `RuntimeError("Fins read runtime 已关闭")`，`snapshot_transferred=False` 确保 full snapshot 被关闭；publication-first → close 随后 clear/retire，active borrow 继续合法完成。✓
  - 未修改 `_close_retired_entry`，与 Controller 裁决一致。✓

- **owner test 验证**:
  - `test_runtime_close_before_cache_publication_rejects_build_and_cleans_snapshot` (line 1876): 用 `registry.before_return` + `threading.Event`（无 sleep）固定 close-first interleaving，断言 `cache/retired/pending` 全空、full snapshot roots 全部删除。✓
  - `test_cache_publication_before_runtime_close_preserves_active_borrow` (line 2013): 固定 publication-first interleaving，断言 close 后 cache 空但 active snapshot 仍可读，release 后 root 删除且 retired/pending 全空。✓

- **测试执行结果**: 两节点在真实 filesystem 下通过。

**Verdict: CLOSED** — root cause 已由共享 lifecycle owner lock 的线性化消除；两序行为均有真实 Event 测试覆盖；无 sleep oracle；无新 production seam。

**Residual risk**: 低。`_lifecycle_lock` 是 RLock，`_borrow_processor` 在 `with lock:`（per-document creation lock）内嵌套获取 `_lifecycle_lock`；两锁获取顺序在所有路径一致（先 `lock` 后 `_lifecycle_lock`），无死锁风险。

---

### 3.2 R07-CR-F02 [MEDIUM] — creation-lock registry 无界增长

**Claimed root cause**: `_creation_locks` 为永久强引用 `dict`，任意 key（包括 missing）在 snapshot 读取前即创建条目，cache eviction 不回收。

**Claimed fix**: registry 改为 `WeakValueDictionary[ProcessorCacheKey, Lock]`；重叠 same-key caller 通过局部变量 + `with lock` 全程持有强引用共享同一 lock；caller 结束后 registry 不再成为永久 owner。

**DS 独立验证**:

- **production 代码证据** (`dayu/fins/tools/read_runtime.py`):
  - Line 828: `self._creation_locks: WeakValueDictionary[ProcessorCacheKey, Lock] = WeakValueDictionary()`。✓
  - Lines 3146-3152: `_get_creation_lock` 在 `_creation_locks_guard` RLock 下做 get-or-create，返回的 lock 在 caller 的局部变量和 `with lock:` 全程持有强引用。✓
  - `_borrow_processor` line 2967: `lock = self._get_creation_lock(cache_key)` → line 3029: `with lock:` — 局部变量 `lock` 保持强引用直到 `with` 块结束。✓
  - `_get_cached_processor_borrow_for_diagnosis` line 2918: 同样模式。✓
  - 未使用 `locked()` 猜 waiter、sweep、magic threshold、global striped lock 或 cache eviction 下游补偿。✓

- **owner test 验证**:
  - `test_concurrent_initial_cache_miss_builds_one_processor_and_closes_losing_snapshot` (line 1802): 两个重叠 same-key caller 共享同一 lock，只构建/发布一个 processor。✓
  - `test_creation_lock_registry_reclaims_missing_and_evicted_document_keys` (line 1930): 64 个 missing keys → GC → registry=0；12 个 valid keys（cache 容量 4）→ GC → registry=0，cache 严格 bounded。✓

- **测试执行结果**: 两节点通过。

**Verdict: CLOSED** — weak-value 生命周期正确解决无界增长；missing 与超容量 valid key 均验证回收；无新公共契约或 downstream compensation。

**Residual risk**: 低。`WeakValueDictionary` 的回收时机依赖 CPython 引用计数（当前实现为确定性立即回收）；若未来切换到非引用计数 Python 实现，GC 周期可能延迟回收，但不会导致正确性失败（lock 最终仍可回收，只是内存峰值略高）。这不是 R07 需要解决的问题。

---

### 3.3 R07-CR-F03 [LOW] — process target 消费公共 close retry authority

**Claimed root cause**: process target 首次 `DefaultFinsRuntime.close()` 失败后没有再次消费公共幂等 cleanup authority；`primary_failed=True` 时 close failure 被静默丢弃。

**Claimed fix**: 首次 close 失败后固定调用一次 `_follow_up_process_runtime_close(runtime)`（仅再次调用同一 public idempotent `close()`）；completed/typed business/unexpected 三路均保持原 outcome priority；follow-up 仍失败时只记录 path-free `action/type/errno`。

**DS 独立验证**:

- **production 代码证据** (`dayu/fins/tools/fins_tools.py`):
  - Lines 86-111: `_follow_up_process_runtime_close` — 调用 `runtime.close()`，失败时只 `Log.warning` 固定 `action=runtime.close.follow_up type=<type> errno=<value|none>`，不记录 raw message/path/key/revision/cause/traceback。✓
  - Lines 321-332: process target `finally` 块 — 首次 `runtime.close()` 失败时，仅当 `not primary_failed` 才覆盖 outcome；随后固定调用 `_follow_up_process_runtime_close(runtime)`。✓
  - 不访问 `_read_runtime`、`_pending_snapshots`、`_retired_entries` 或 storage private state。✓
  - 没有新增 envelope/schema/cancel 语义，没有捕获 `BaseException`。✓

- **owner test 验证**:
  - `test_fins_read_process_target_closes_runtime_on_success_and_failure` (line 3182): completed、typed business failed、unexpected failed 三个独立 runtime 注入 transient first-close failure；每个 runtime 恰好两次公共 close；outcome 分别保持 `execution_error`、`invalid_argument`、`execution_error`。✓
  - `test_fins_read_process_target_persistent_close_failure_logs_path_free_diagnostic` (line 3261): 两次 close 均抛含敏感 locator/key/revision/cause 的异常；primary outcome 不漂移、close 恰好两次、日志只含 `action/type/errno`。✓
  - `test_default_runtime_public_close_retries_real_snapshot_cleanup` (line 3334): 真实 `DefaultFinsRuntime` + 真实 filesystem snapshot，temp-root 删除首次失败 → 第一次 close 抛异常且 root 保留 → 第二次 close 删除 root → 第三次幂等 close 不触发删除。✓

- **测试执行结果**: 三节点通过。

**Verdict: CLOSED** — 公共幂等 close 的 retry authority 已被 process target 正确消费；三路 outcome priority 均保持；path-free diagnostic 已验证。

**Residual risk**: 低。连续两次 filesystem cleanup 均失败时，process target 保留 primary outcome 并记录 path-free diagnostic；temp root 残留为 bounded orphan/residual。普通 `tempfile.mkdtemp` 目录不会随进程退出自动删除，也不能承诺 OS 回收；未来仅由外部 temp hygiene/运营清理处理。这是 bounded failure contract，不是 open finding；本轮不授权第三次/无限/configurable retry。

---

## 4. S1 accepted findings 保持关闭验证

### 4.1 R07-S1-CR-F01 — destructive cleanup preflight

**验证**: `_fs_maintenance_core.py` line 660: `_clear_filing_documents_impl` 在任何 `rmtree/unlink` 前调用 `_preflight_filing_cleanup`（line 594），该 preflight 依次验证完整 source kind tree、download rejection registry、rejected filing subtree。只有全部 preflight 通过才开始删除。✓

**Verdict: 保持关闭** — preflight-before-mutation 模式未退化。

### 4.2 R07-S1-CR-F02 — begin_batch primary error preservation

**验证**: `_fs_storage_infra.py` lines 536-562: 初始化异常被保存为 `primary_error`；staging cleanup 和 lock release 失败均通过 `_append_secondary_error_note` 追加为次要诊断；最终始终 raise `primary_error`。✓

**Verdict: 保持关闭** — primary error priority 未退化。

### 4.3 R07-S1-CR-F03 — path-free error projection

**验证**: 通过 S1 re-review 与 Controller validation 链条确认已关闭；本 re-review 在累计 tree 中未发现 storage public boundary 新引入 raw locator 泄漏。`test_read_outputs_never_expose_revision_internal_key_local_uri_or_temp_path` (line 3399) 递归扫描九个 tools 的 completed/failed/cancelled projection 确认零泄漏。✓

**Verdict: 保持关闭** — path-free error boundary 未退化。

---

## 5. S2 accepted finding 保持关闭验证

### R07-S2-CR-F01 — snapshot context-manager lifecycle

**验证**: 通过 S2 re-review 与 Controller validation 链条确认已关闭；三个 S2 consumers（`ingestion_runtime.py`、`sec_fiscal_fields.py`、`sec_6k_primary_document_repair.py`）均使用统一 snapshot lifecycle；S3 累计 tree 中未发现三处回退为各自 `try/finally` 模式。✓

**Verdict: 保持关闭** — 统一 context-manager lifecycle 未退化。

---

## 6. S3 既有 PASS 领域保持验证

以下领域在 S3 DS initial review 中已判定 PASS，本 re-review 确认 fix gate 未引入回归：

| 领域 | S3 DS 初版 | 本轮确认 |
|---|---|---|
| Opaque identity → private key 唯一 owner、不可逆、non-leak | PASS | 仍 PASS — 未修改 identity owner |
| Persisted revision + light/full snapshot consistency、static corruption priority、bounded retry | PASS | 仍 PASS — 未修改 snapshot owner |
| Read-runtime borrow lifecycle 线程安全（除 F01 已修复） | PASS with F01 | CLOSED — lifecycle lock 线性化 |
| Processor/meta/provenance/citation/result 同 snapshot | PASS | 仍 PASS — 未修改 borrow scope |
| Eight tools + cross-document diagnosis/list/alias/exact source-kind | PASS | 仍 PASS — 未修改 tool entry |
| Containment/symlink/atomic/recovery/typed security、LLM non-leak | PASS | 仍 PASS — 未修改 security boundary |
| No compatibility/fallback/speculative abstraction、no R08+/deferred Issues/统一 authorization 越界 | PASS | 仍 PASS — diff 仅限 fix allowlist |
| Tests 真实 filesystem/Event/Barrier、无 sleep oracle | PASS | 仍 PASS — 新增 5 个 owner tests 同模式 |

**Verdict: 全部既有 PASS 领域保持** — fix gate 四文件变更范围精确限定，未触碰其余 R07 owner。

---

## 7. 新增回归风险检查

### 7.1 `_lifecycle_lock` 嵌套安全性

`_borrow_processor` 的锁获取顺序为：先 `_creation_locks_guard`（`_get_creation_lock` 内）→ 再 per-document `lock`（`with lock:` 内）→ 最后 `_lifecycle_lock`（`cache.put` 临界区）。

`close()` 的锁获取顺序为：仅 `_lifecycle_lock`。

`_retry_pending_cleanup()` 的锁获取顺序为：`_lifecycle_lock` → 遍历 → per-entry `_close_retired_entry`。

`_retire_entry()` 的锁获取顺序为：`_lifecycle_lock`（add to `_retired_entries`）。

所有路径的 `_lifecycle_lock` 获取均为最内层（或唯一层），无反向嵌套。✓ 无死锁风险。

### 7.2 `WeakValueDictionary` 并发安全性

`_get_creation_lock` 在 `_creation_locks_guard` RLock 下操作 `WeakValueDictionary`；所有 registry get/set 均由该锁串行化，不依赖 `WeakValueDictionary` 自身或 GIL 的线程安全语义。✓

两个重叠 same-key caller 的竞争：caller-1 创建 lock 并存入 dict，释放 `_creation_locks_guard`；caller-2 获取同一 lock；两个 caller 的局部变量均在 `with lock:` 期间持有强引用。如果 caller-1 先离开 `with lock:` 且无其他引用，GC 可能回收 lock 的 dict entry——但 caller-2 仍在 `with lock:` 内持有 lock 对象本身，GC 不会回收仍有强引用的对象。只有两个 caller 都离开后，lock 才变为仅由 weak dict 引用，此时被回收。✓

### 7.3 `close()` → `_retry_pending_cleanup()` 两阶段正确性

`close()` line 3449 调用 `self._retire_entries(self._processor_cache.clear())`。`clear()` 在 `ProcessorLRUCache._lock` 下返回所有旧条目。若其中某个 entry 的 snapshot close 失败，entry 保留在 `_retired_entries`。随后 line 3450 `self._retry_pending_cleanup()` 遍历 `_retired_entries` 重试。若重试仍失败，异常传播到 `close()` 的调用者。

首次 close 失败但 entry 仍在 `_retired_entries` → 下次 `close()` 再次调用 `_retry_pending_cleanup()` 重试。✓ 这是 Controller 确认的既有 cleanup retry authority。

### 7.4 `_follow_up_process_runtime_close` 幂等性

`DefaultFinsRuntime.close()` 是幂等的（`_closed` flag + `RuntimeError` guard on `get_read_runtime()`）。`_follow_up_process_runtime_close` 再次调用同一 public `close()`。若首次 close 已成功（`_closed=True`），第二次 close 进入 `_retry_pending_cleanup()` 路径——遍历已空的 retired/pending 列表，无操作返回。✓

### 7.5 `primary_failed` 与 `outcome` 覆盖优先级

```python
try:
    runtime.close()
except Exception:
    if not primary_failed:
        outcome = process_tool_failed_envelope(...)  # close failure → execution_error
    _follow_up_process_runtime_close(runtime)        # always called
```

- `primary_failed=False` + close succeeds → outcome unchanged (completed) ✓
- `primary_failed=False` + close fails → outcome replaced with `execution_error` ✓
- `primary_failed=True` + close fails → outcome unchanged (primary business failure) ✓
- `primary_failed=True` + close succeeds → outcome unchanged (primary business failure) ✓
- All paths call `_follow_up_process_runtime_close` after first close attempt ✓

**Verdict**: 无新增回归风险。

---

## 8. Finding Ledger

| Finding | Severity | 本轮状态 | 证据摘要 |
|---|---|---|---|
| `R07-CR-F01` post-close publication/temp leak | HIGH | **CLOSED** | 共享 `_lifecycle_lock` 线性化；close-first + publication-first owner tests 通过 |
| `R07-CR-F02` unbounded creation-lock registry | MEDIUM | **CLOSED** | `WeakValueDictionary` + 局部强引用；missing/evicted reclamation tests 通过 |
| `R07-CR-F03` process cleanup retry authority lost | LOW | **CLOSED** | 一次公共 follow-up close；三路 outcome priority + path-free diagnostic + 真实 cleanup retry tests 通过 |
| `R07-S1-CR-F01` destructive cleanup preflight | — | **保持关闭** | `_preflight_filing_cleanup` 在 mutation 前，模式未退化 |
| `R07-S1-CR-F02` begin_batch primary error | — | **保持关闭** | primary error 始终为主异常，secondary 附着为 note，模式未退化 |
| `R07-S1-CR-F03` path-free error projection | — | **保持关闭** | Controller validation 链条确认 + LLM non-leak recursive test |
| `R07-S2-CR-F01` snapshot context-manager lifecycle | — | **保持关闭** | 三个 consumers 均使用统一 lifecycle，模式未退化 |

**Material findings 本轮新增: 0**
**Blockers: 0**
**Deferred: 0**

---

## 9. Open Questions

无。

---

## 10. Residual Risk

- **连续两次 filesystem cleanup 均失败**: process target 按 bounded contract 保留 primary outcome 并记录 path-free diagnostic；temp root 残留为 bounded orphan/residual。普通 `tempfile.mkdtemp` 目录不会随进程退出自动删除，未来仅由外部 temp hygiene/运营清理处理。本轮不授权更多重试。
- **Full suite inherited failures**: `tests/service/test_host_admin.py`（`wait_poller_policy` ConfigFieldError）、`tests/service/test_import_boundary.py`（import boundary violation）、`tests/runtime/test_log.py`（order-dependent StreamHandler assertion）保持与 accepted plan §1.1 相同的 node/type/location/text fingerprint。R07 未扩散。
- **Full Ruff 150 项**: 保持 F401=70、E402=66、F841=10、F541=3、F821=1。R07 fix gate 未新增或扩散。
- **`WeakValueDictionary` 在非 CPython 实现的 GC 延迟**: 见 §3.2 residual risk。当前 CPython 引用计数为确定性立即回收。
- **R08 financial/XBRL contract、R09—R12、Issues 142/151/175/177/178、统一 authorization**: 均未触碰，保持 deferred。

---

## 11. Verdict

**PASS** — R07 complete cumulative S1+S2+S3 final tree 审查通过。

- `R07-CR-F01..03` 三项 root cause 均真实关闭：有直接代码证据、有 owner test 验证、有独立测试执行通过。
- S1 `R07-S1-CR-F01..03` 全部保持关闭。
- S2 `R07-S2-CR-F01` 保持关闭。
- S3 既有 PASS 领域（opaque identity、snapshot consistency、borrow lifecycle、citation provenance、LLM non-leak、security containment、typed errors、no compatibility、no R08+ overreach）无回归。
- 本 fix gate 未引入新 material finding、blocker 或 deferred scope。
- 测试使用真实 filesystem + `threading.Event`/`Barrier` 协调，无 `time.sleep` correctness oracle。

**Material findings: 0**
**Blockers: 0**
**R07-CR-F01..03 状态: 全部 CLOSED**

---

## 12. Handoff

本 agent（AgentDS）到此停止。artifact 已写入 `docs/reviews/wu-semantic-ownership-01-r07-s3-code-review-rereview-ds.md`。未修改 product/test/README/control/design/plan/旧 artifacts，未 stage/commit/push/PR。交回 Controller adjudication。
