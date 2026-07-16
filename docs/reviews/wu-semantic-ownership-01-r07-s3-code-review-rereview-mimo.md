# WU-SEMANTIC-OWNERSHIP-01 R07 complete cumulative S1+S2+S3 code re-review — AgentMiMo

## 1. Gate、范围与结论

- **审查对象**：既有 umbrella `WU-SEMANTIC-OWNERSHIP-01` 的累计 R07-S1+S2+S3 final tree；不是新 WU。
- **HEAD / transition base**：`386fef8d7a7ecbd977c455ca86bb8bab875d1a98`。
- **accepted plan SHA-256**：`ade7691846b9591fa27ece0bbf871b361761714436ff59e6b2c333cde137cac1`。
- **本轮重点真源**：
  - `docs/reviews/wu-semantic-ownership-01-r07-s3-code-review-controller-adjudication.md`
  - `docs/reviews/wu-semantic-ownership-01-r07-s3-code-review-fix-codex.md`
  - `docs/reviews/wu-semantic-ownership-01-r07-s3-code-review-fix-controller-validation.md`
- **身份**：本 agent 是 AgentMiMo reviewer；只做审查，不改 product/test/README/control/design/plan/旧 artifact，不 stage/commit/push/PR。

**Verdict: PASS — 0 material findings, 0 blocker.**

## 2. R07-CR-F01..03 Root-Cause Closure 验证

### R07-CR-F01 [HIGH] processor build 可在 runtime close 返回后发布 live cache entry — **已关闭**

**Root cause**：processor build 在 document creation lock 内通过一次 `_ensure_open()` 后，可以在不持 read-runtime lifecycle owner lock 的情况下构建并发布 cache entry；`close()` 因而可能先设置 closed、清空 cache 并返回，随后 build 再发布 live entry。

**修复验证**：

- **Production evidence**：`read_runtime.py:3064-3066` 在 `_lifecycle_lock` 内执行最终 `_ensure_open()` 与 `ProcessorLRUCache.put()`，使 closed-check + publication 与 `close()` 的 closed-state transition 形成同一线性化顺序。
- **close-first path**：close 先取得 `_lifecycle_lock` 时，build 在最终 `_ensure_open()` 以既有 `RuntimeError("Fins read runtime 已关闭")` 结束，未向 cache 发布 entry，unowned snapshot 被删除。
- **publication-first path**：publication 先取得 `_lifecycle_lock` 时，close 随后 clear/retire entry，已接受的 active borrow 可继续完成，最后释放 snapshot。
- **没有修改 `_close_retired_entry`**：Controller 已裁决该处不是本 finding 根因，既有 cleanup retry authority 保持不变。

**Test evidence**：

- `test_runtime_close_before_cache_publication_rejects_build_and_cleans_snapshot`：用真实 filesystem、`registry.before_return` 和两个 `threading.Event` 固定 close-first interleaving，无 sleep；断言 worker 完成、既有 close-state error、cache/retired/pending 全空且全部 full snapshot roots 删除。
- `test_cache_publication_before_runtime_close_preserves_active_borrow`：固定 publication/borrow-first 顺序；断言 close 后 cache 已空但 active snapshot 仍可读，调用完成后 root 删除且 retired/pending 全空。

**裁决**：R07-CR-F01 闭合。lifecycle linearized final check/publication 完整满足 Controller 裁决的 owner boundary。

---

### R07-CR-F02 [MEDIUM] per-document creation-lock registry 无界增长 — **已关闭**

**Root cause**：`_creation_locks` 原为永久强引用 `dict`，任意 missing key 在 snapshot read 前即创建条目，cache eviction 也不回收，因此长期 runtime 的历史 key 数量可无界增长。

**修复验证**：

- **Production evidence**：`read_runtime.py:828` 改为 `WeakValueDictionary[ProcessorCacheKey, Lock]`，lock 在没有外部引用时自动回收。
- **registry guard**：`_creation_locks_guard` 继续串行化 registry get/create；重叠 same-key caller 的局部变量和 `with lock` 全程持有强引用，因此共同取得同一个 lock。
- **caller 结束后**：registry 不再成为 lock 的永久 owner；新一轮非重叠调用可按需创建新 lock。
- **没有使用 `locked()` 猜 waiter、sweep、阈值、全局 striped lock 或 cache eviction 下游补偿**。

**Test evidence**：

- `test_concurrent_initial_cache_miss_builds_one_processor_and_closes_losing_snapshot`：两个重叠 same-key caller 共用同一强引用 lock、只构建/发布一个 processor，losing full snapshot 删除。
- `test_creation_lock_registry_reclaims_missing_and_evicted_document_keys`：顺序访问 64 个 missing IDs，再访问 12 个真实 document IDs（cache 容量 4）；必要 GC 后两阶段 registry 均为 0，cache 仍严格为 0/4，evicted roots 删除、runtime close 后全部 roots 删除。

**裁决**：R07-CR-F02 闭合。weak-value lifecycle 完整满足 Controller 裁决的 bounded resource 约束。

---

### R07-CR-F03 [LOW] process target 在已有 primary failure 时吞掉 close failure 并丢失公开 retry authority — **已关闭**

**Root cause**：process target 首次 `DefaultFinsRuntime.close()` 失败后没有再次消费公共幂等 cleanup authority；已有 primary failure 时还会静默吞掉 cleanup failure。

**修复验证**：

- **Production evidence**：`fins_tools.py:86-111` 定义 `_follow_up_process_runtime_close(runtime)`，在首次 close 失败后调用 `runtime.close()` 一次。
- **follow-up implementation**：`fins_tools.py:332` 在 `finally` 块中，首次 close 失败后调用 `_follow_up_process_runtime_close(runtime)`。
- **outcome priority**：completed 首次 cleanup failure 仍投影 `execution_error`；typed business primary 与 unexpected primary outcome 均不被 secondary cleanup failure 覆盖。
- **persistent failure diagnostic**：follow-up 仍失败时，仅用 `Log.warning` 记录 `action=runtime.close.follow_up type=<type> errno=<value|none>`；不记录 raw message、path、key、revision、cause 或 traceback。
- **没有新增 envelope/schema/cancel 语义**，没有捕获 `BaseException` 或引入可配置/无限 retry policy。

**Test evidence**：

- `test_fins_read_process_target_closes_runtime_on_success_and_failure`：对 completed、typed/business failed、unexpected failed 三个独立 runtime 注入 transient first-close failure；每个 runtime 都发生恰好两次公共 close，真实第二次 close 完成，outcome 分别保持 `execution_error`、`invalid_argument`、`execution_error`。
- `test_fins_read_process_target_persistent_close_failure_logs_path_free_diagnostic`：让两次 close 都抛出含敏感 locator/key/revision/cause 的异常；断言 primary business outcome 不漂移、公共 close 恰好两次、日志只含 action/type/errno。
- `test_default_runtime_public_close_retries_real_snapshot_cleanup`：使用真实 `DefaultFinsRuntime` 和真实 filesystem snapshot，使 temp-root 删除首次失败；第一次公共 close 抛出且 root 保留，第二次公共 close 删除 root，第三次幂等 close 不再触发删除，证明 retry authority 已清空。

**裁决**：R07-CR-F03 闭合。one public follow-up close + three outcome priorities + path-free persistent diagnostic + real cleanup retry 完整满足 Controller 裁决的 cleanup owner contract。

---

## 3. S1/S2/S3 所有既有 Accepted Findings 保持关闭确认

### S1 Accepted Findings

| Finding | 最终状态 | 验证 |
|---|---|---|
| `R07-S1-CR-F01` destructive cleanup complete preflight | **保持关闭** | `_validate_complete_source_kind_tree`、`_preflight_filing_cleanup`、`_preflight_processed_cleanup` 均在删除前完成只读完整校验。S3 fix 不涉及 destructive cleanup 路径。 |
| `R07-S1-CR-F02` `begin_batch` primary-error preservation | **保持关闭** | `begin_batch` state machine 未被 S3 fix 修改。 |
| `R07-S1-CR-F03`（含 CR-CV-F01）path-free filesystem error producer boundary | **保持关闭** | `_fs_storage_utils.py` 投影链未被 S3 fix 修改。 |
| `R07-S1-CR-CV-F01` complete exception graph leakage | **保持关闭** | raw cause/context 不再可达；path-free cause 保留 subclass/errno category。 |

### S2 Accepted Findings

| Finding | 最终状态 | 验证 |
|---|---|---|
| `R07-S2-CV-F01` `_read_published_marker` guard release 次失败 | **保持关闭** | 三态保留模式未被 S3 fix 修改。 |
| `R07-S2-CV-F02` snapshot `close()` temp-root cleanup locator | **保持关闭** | `_SnapshotResourceState.close()` 的 locator 保留/重试逻辑未被 S3 fix 修改。 |
| `R07-S2-CV-F03` initial fstat stream close 次失败 | **保持关闭** | `_acquire_snapshot_attempt_unguarded` 的 fstat 主异常保留逻辑未被 S3 fix 修改。 |
| `R07-S2-CR-F01` consumer snapshot close failure masks active primary failure | **保持关闭** | Protocol、private implementation、三个 consumer 与 owner-level 测试完整满足 Controller 裁决。 |

### S3 Accepted Findings

| Finding | 最终状态 | 验证 |
|---|---|---|
| `R07-CR-F01` post-close processor publication/temp leak | **已修复 / 关闭** | lifecycle-linearized final check/publication；close-first + publication-first owner tests |
| `R07-CR-F02` unbounded creation-lock registry | **已修复 / 关闭** | weak-value lifecycle；same-key identity/build + missing/over-capacity reclamation tests |
| `R07-CR-F03` process cleanup retry authority lost | **已修复 / 关闭** | one public follow-up close；三 outcome priority、persistent diagnostic、真实 snapshot cleanup tests |

---

## 4. Identity/Snapshot/Revision/Citation/Opaque Non-Leak 验证

### 4.1 Opaque identity owner

- `_fs_identity.py` 是 external identity → private locator 的唯一 owner。`_derive_storage_key` 使用 SHA-256(namespace\0identity)，确定性且不可逆。
- 双向校验：所有 identity directory 读写均经过 `_read_identity_descriptor` 验证 namespace/external_identity/private_key 三方一致性；`_list_external_identities` 只从 descriptor 读取，不从目录名反推。
- Error graph: identity 校验失败一律 `ValueError`；文件系统失败经 `_project_filesystem_error` → `_raise_path_free_error` 投影，不暴露 raw locator。

### 4.2 Persisted opaque revision

- Revision 唯一 owner: `_source_revision_from_meta` 从 persisted meta 字段 `_published_source_revision` 机械读取，consumer 不得重算。
- `_source_meta_without_revision` 在所有 snapshot 构造点剥离 revision 字段，确保 consumer 的 `source_meta` 不含私有 revision。
- `SourceDocumentRevision.token` 只接受非空字符串并做 opaque equality，不校验/承诺 `sha256:` 或任何其它 grammar。

### 4.3 Stable snapshot

- Full snapshot 后验核对: `_acquire_snapshot_attempt` 在 publication guard 内采集 marker；`_read_source_snapshot` 在 fd copy 后再次读取 published marker 并做 exact equality 比较。不一致时重试，最多 `_STABLE_READ_ATTEMPT_LIMIT=3` 次。
- Static corruption 优先: `_copy_snapshot_file` 在复制后验证 `fstat` 不变、EOF 与 size 一致、SHA-256 匹配。任何不一致都 `ValueError`，不映射为 `source_changed` 重试。

### 4.4 Same-snapshot processor/meta/provenance/citation/result

- 八个 processor 入口全部通过 `_borrow_processor` 取得同一 borrow scope。
- `_build_citation` 从 `borrow.snapshot.provenance` 和 `borrow.source_meta` 派生，不从 repository 重读。
- Cross-document diagnosis: 仅遍历 cached keys，lightweight snapshot 验证后 borrow，不创建新 processor。
- `list_documents`: 分别枚举 FILING 和 MATERIAL，过滤 deleted/incomplete，附加 `document_type`。

### 4.5 LLM-facing non-leak

- `_source_meta_without_revision` 剥离 revision；error messages 路径无关；tool schema 不暴露 private key/revision。
- `ErrorCode.SOURCE_CHANGED_DURING_READ` 保留既有 code 值，message/hint 不暴露 token/key/path。
- `test_read_outputs_never_expose_revision_internal_key_local_uri_or_temp_path` 递归覆盖九工具 completed/failed/cancelled projection。

---

## 5. Security Containment/Symlink/Atomic/Recovery 验证

- **Containment**: path traversal（`.`、`..`、separator、absolute、drive/UNC）检查保留。
- **Symlink**: identity descriptor、snapshot file、meta path 均校验 symlink/regular file/containment。
- **Atomic**: R06 的 atomic swap/journal/recovery 未修改。
- **Typed error**: `SourceSnapshotConsistencyError`、`ErrorCode.SOURCE_CHANGED_DURING_READ` 等 typed error 保留；`_raise_path_free_error` 保证 public error 不含 locator。
- **Writer mutex/publication guard**: R06 writer mutex、complete-source validator 与 publication guard 是 R07 的直接基础，未删除或削弱。

---

## 6. Typed Errors 验证

- `SourceSnapshotConsistencyError`: storage 专用 typed consistency error，保留 cause 但不携带 Path/key/revision。
- `FinsReadBusinessError(ErrorCode.SOURCE_CHANGED_DURING_READ)`: read runtime 单点 catch storage consistency exhaustion 并映射。
- `FinsReadBusinessError(ErrorCode.SOURCE_DECODE_FAILED)`: processor build 失败映射。
- `_raise_path_free_error`: 保证 public error 不含 locator，有意义 subclass、errno 与 path-free 因果类别保留。

---

## 7. Deferred Issues/统一 Authorization 越界验证

- **R08+ (financial/XBRL contract)**: 未进入。
- **Issues 142/151/175/177/178**: 未进入。
- **统一 authorization**: 未进入。
- **S1/S2 intermediate commit**: 未创建（accepted plan §10.2 明确 S1/S2 为累计 checkpoint，没有 S1/S2 intermediate commit）。

---

## 8. 验证矩阵

| 检查 | 结果 |
|---|---|
| 八个累计 test files | `494 passed, 3 warnings`（24.76s） |
| R07-CR-F01..03 owner nodes | `7 passed, 3 warnings`（1.15s） |
| full pyright | `0 errors, 0 warnings, 0 informations` |
| scoped Ruff（20 production + 8 tests） | `All checks passed!` |
| full Ruff baseline | 既有 `150`：`70 F401 / 66 E402 / 10 F841 / 3 F541 / 1 F821`，未扩散 |
| `git diff --check` | PASS |
| revision/source scan | 唯一命中仍是 `tests/README.md` 的层中立 UTF-8 文本 digest 说明 |
| `_resolve_source_kind` / filing-first probe | 0 |
| `fins_tools.py` 对 `_read_runtime`、`_pending_snapshots`、`_retired_entries` 的 private access | 0 |
| LLM-facing scan | tool schema/description/result/citation/error message 不暴露 token/key/path |
| S3 fix 新增 `time.sleep` / `sleep(...)` | 0 |
| formal directory full suite | `4883 passed, 3 failed, 3 skipped, 5 deselected, 3 warnings`；三项 failure 与 accepted inherited ledger 的 node/type/location/text fingerprint 精确一致，没有新增 failure |

---

## 9. Observations（非 blocker，无需修复）

### OBS-1 — `_fs_storage_infra.py::_require_copyable_ticker_tree` 中 `rglob("*")` 未在函数内直接投影 OSError

- **文件(行号)**: `_fs_storage_infra.py:2101`
- **场景**: `ticker_dir.rglob("*")` 是 `begin_batch` 调用链中唯一的裸 `Path` 迭代器，其 `OSError` 未在函数内直接捕获和投影。
- **缓解**: `begin_batch` 的外层 `except Exception` 会捕获并投影所有 OSError，因此实际不会泄漏路径。
- **风险**: 低。属于防御深度不一致，非 correctness 问题。

### OBS-2 — `_fs_storage_utils.py::_write_json` 参数 `payload: Any` 违反编码硬约束

- **文件(行号)**: `_fs_storage_utils.py:701`
- **约束**: CLAUDE.md 编码硬约束禁止使用 `Any`。
- **缓解**: 此为既有模式（同文件 `_read_json` 返回 `dict[str, Any] | list[Any]`、`_extract_file_payloads` 参数 `meta: dict[str, Any]` 等均有类似用法）。项目已有 `JsonValue` 类型可替代但属于 pre-existing debt。
- **风险**: 低。pyright 通过，功能无影响。与 R07-CR-F01/F02/F03 无关。

---

## 10. Open Questions

无。

---

## 11. Residual Risk

1. **`_fs_identity.py` 无直接单元测试**: 6 个函数的覆盖率来自集成测试间接路径（Controller 验证 80.00%）。S1 test allowlist 约束下无法新增 test file。
2. **`_fs_storage_utils.py` error projection 函数无直接单元测试**: `_project_filesystem_error`、`_raise_path_free_error`、`_append_secondary_error_note` 的覆盖率来自上层集成路径（83.82%）。同上约束。
3. **legacy Ruff 150 fingerprint**: 既有 `70 F401 / 66 E402 / 10 F841 / 3 F541 / 1 F821`，未扩散。不属于 R07 owner。
4. **`edgar` 3 个 deprecation warning**: 既有安装环境问题，未扩散。
5. **formal suite 三项 inherited failure**: 与 accepted plan §1.1 的 node/type/location/text fingerprint 精确一致，由既有 owner 处理，不属于 R07。

以上 residual 均不阻塞 re-review gate。

---

## 12. Finding Ledger

| Finding | Severity | Status |
|---|---|---|
| `R07-CR-F01` post-close processor publication/temp leak | HIGH | **已修复 / 关闭** |
| `R07-CR-F02` unbounded creation-lock registry | MEDIUM | **已修复 / 关闭** |
| `R07-CR-F03` process cleanup retry authority lost | LOW | **已修复 / 关闭** |
| S1 accepted findings (CR-F01, CR-F02, CR-F03, CR-CV-F01) | — | **保持关闭** |
| S2 accepted findings (CV-F01, CV-F02, CV-F03, CR-F01) | — | **保持关闭** |
| new material finding | — | **0** |
| blocker | — | **0** |

最终 ledger：`0 open / 0 deferred / 0 blocker`。

---

## 13. Verdict

**PASS**

- **R07-CR-F01**: CLOSED — lifecycle linearized final check/publication + close-first / publication-first exact owner tests
- **R07-CR-F02**: CLOSED — weak-value owner lifecycle + same-key identity/build + missing/over-capacity reclamation tests
- **R07-CR-F03**: CLOSED — one public follow-up close + three outcome priorities + path-free persistent diagnostic + real cleanup retry
- **S1/S2/S3 all accepted findings**: CLOSED / REMAIN CLOSED
- **New material findings**: 0
- **Blockers**: 0
- **Security**: 所有机制保留，无回退
- **Tests**: `494 passed, 3 warnings`；R07-CR-F01..03 owner nodes `7 passed`
- **Static**: pyright `0 errors`，scoped Ruff `All checks passed`，full Ruff baseline 未扩散

---

**审查完成时间**: 2026-07-17
**审查 Agent**: AgentMiMo
**目标**: Controller adjudication

---

## 14. Final Finding Ledger 与 Handoff

| Finding | Severity | Final status | Evidence |
|---|---|---|---|
| `R07-CR-F01` post-close publication/temp leak | HIGH | **已修复 / 关闭** | lifecycle-linearized final check/publication；close-first + publication-first owner tests |
| `R07-CR-F02` unbounded creation-lock registry | MEDIUM | **已修复 / 关闭** | weak-value lifecycle；same-key identity/build + missing/over-capacity reclamation tests（7 个 owner nodes 全部通过） |
| `R07-CR-F03` process cleanup retry authority lost | LOW | **已修复 / 关闭** | one public follow-up close；三 outcome priority、persistent diagnostic、真实 snapshot cleanup tests |

最终 ledger：`0 open / 0 deferred / 0 blocker`。

下一 entry point：**Controller adjudication**。本 agent 到此停止；不得由本 gate 进入 accepted implementation commit、R08、stage、commit、push 或 PR。
