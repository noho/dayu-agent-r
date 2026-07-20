# WU-SEMANTIC-OWNERSHIP-01 R06-S1 双路累计 Code Re-Review — 第一路 (AgentMiMo)

## 1. Review Identity

- Work unit：`WU-SEMANTIC-OWNERSHIP-01` / R06 / S1 cumulative code re-review — 第一路
- Base commit：`d048adf7ec1135aaf575384432ebf1137f8a34f2`
- Review scope：base 到当前完整未暂存 working tree（含 CR-F01..03 fix）
- Review 日期：2026-07-16T06:19:21
- 裁决文档优先级：AGENTS.md > overdesign-controller-discussion > fins/design.md > R06 plan > plan re-review controller adjudication > implementation codex > validation-fix codex > controller validation > controller adjudication (CR-F01..03) > fix codex > fix controller validation > issues-implementation-control.md R06 rows

## 2. Scope

- Mode：current changes（base `d048adf7`）
- Branch：`phaseflow/host-issues-control`
- Output file：`docs/reviews/wu-semantic-ownership-01-r06-s1-code-rereview-mimo.md`
- Included scope：15 个累计 S1 production files、4 个 S1 test files、CR-F01..03 fix 涉及的 2 个 production owner 与 1 个 test 文件、issues-implementation-control.md R06 rows
- Excluded scope：S2/S3 未传播的 producer/callback/composition files、README、design truth、control 文件
- Parallel review coverage：3 个 subagent 分别覆盖 infra transaction authority（`_fs_storage_infra.py` + `document_models.py`）、cores/wrappers/protocols（5 core + 6 wrapper + protocols + `local_file_source.py`）、tests quality（4 test files）；主 reviewer 独立运行全部验证命令并整合/去重/复核

## 3. Verdict

**PASS**

current finding = 0，blocking question = 0。

## 4. CR-F01..03 CLOSED/OPEN 裁决

### R06-S1-CR-F01 — maintenance public read private unguarded helper

**CLOSED**

| 检查项 | 结论 | 直接证据 |
| --- | --- | --- |
| public entry 只做 normalize → acquire → delegate → release | PASS | `_fs_maintenance_core.py:401-411`：`_normalize_ticker` (401)、`_normalize_document_id` (402)、`_acquire_publication_guard` (403)、`_read_rejected_filing_file_bytes_unguarded` (405)、`_release_lock_token` (411) |
| private helper 唯一拥有 path containment/missing/directory/bytes I/O | PASS | `_fs_maintenance_core.py:413-445`：`_rejected_filing_file_path_for_read` (436-440)、存在性检查 (441)、目录检查 (443)、`read_bytes()` (445) |
| 无 ambient marker / 重入锁 / public compatibility 参数 | PASS | 无 `ContextVar`、无 "guard held" flag、无默认参数；public entry 不保留第二套路径/I/O 语义 |
| AST public self-call scan | PASS | 全部 `_fs_*_core.py` 的 `self.<public>(...)` 调用为 `[]`；maintenance entry 闭集精确为 `_normalize_ticker`、`_normalize_document_id`、`_acquire_publication_guard`、`_read_rejected_filing_file_bytes_unguarded`、`_release_lock_token` |
| tests 真实覆盖 owner behavior | PASS | monkeypatch 证明 whitespace-padded 输入被 normalize 为 `AAPL`/`fil_rejected` 并精确委托 (line 530-584)；success/missing/directory 三条路径覆盖 (line 477-499) |

### R06-S1-CR-F02 — processed meta contract

**CLOSED**

| 检查项 | 结论 | 直接证据 |
| --- | --- | --- |
| docstring 只承诺 `tool_snapshot_meta.json` | PASS | `_fs_processed_core.py:184`："只读取 published `tool_snapshot_meta.json`"；line 194：`FileNotFoundError` 只描述该唯一文件 |
| 无 `meta.json` fallback 描述 | PASS | `优先读取|回退|fallback|两种元数据` scan = 0 |
| 实现只读一个路径 | PASS | `_processed_meta_path_for_read(...)` 只从 `_PROCESSED_META_FILENAME = "tool_snapshot_meta.json"` 派生；`_get_processed_meta_unguarded` 只解析该路径 |
| protocol/wrapper docstring 一致 | PASS | `repository_protocols.py:662-678` 与 `fs_processed_document_repository.py:127-144` 均无 fallback 描述 |
| tests 从 storage owner 行为证明而非只断言字符串 | PASS | 同目录放冲突 legacy `meta.json` 后读取仍返回 `tool_snapshot_meta.json` 内容 (line 389-396)；删除 tool snapshot 后即使 legacy 保留也精确 `FileNotFoundError match="tool_snapshot_meta.json"` (line 397-399) |

### R06-S1-CR-F03 — reprocess marker return semantics

**CLOSED**

| 检查项 | 结论 | 直接证据 |
| --- | --- | --- |
| shared core 返回 `-> None` | PASS | `_fs_processed_core.py:234` 声明 `-> None`；`required=False` 时 bare `return` (line 260)；target 缺失时 bare `return` (line 289) |
| private impl 返回 `-> None` | PASS | `_fs_processed_core.py:263` 声明 `-> None`；无 `return True`/`return False` |
| protocol/wrapper 已准确声明 `-> None` | PASS | `repository_protocols.py:736` 与 `fs_processed_document_repository.py:205` 均 `-> None`，未改动 |
| 生产调用无返回消费者 | PASS | AST 调用扫描：7 个 `mark_processed_reprocess_required` call 全为 `Expr` statement；`production_return_consumers=[]` |
| tests 证明 owner behavior 而非只断言类型 | PASS | `required=False` 后 commit 前后 meta 完全相等 (line 319-331)；`required=True` 存在目标写入 `reprocess_required=True` (line 347-374)；缺失目标不创建 meta (line 356-377)；private impl 返回 `None` 且副作用成立 (line 365-375) |

## 5. 原 S1 全量 Adversarial Checklist

### 5.1 Opaque BatchToken

| 检查项 | 结论 | 直接证据 |
| --- | --- | --- |
| `BatchToken` 只含 `transaction_id` + `ticker` | PASS | `document_models.py:414-425`，`frozen=True`，无方法、无 `__post_init__`、无衍生属性 |
| 测试不断言 UUID 格式/长度/字符集 | PASS | 只断言 `fields(BatchToken) == ("transaction_id", "ticker")` |
| 测试不从 token 反推物理布局 | PASS | 路径从 `_ActiveBatchState`（storage-owned internal state）取得，不从 `transaction_id` 推导 |

### 5.2 Registry-Only Mutation Authority

| 检查项 | 结论 | 直接证据 |
| --- | --- | --- |
| `_resolve_active_batch` 是唯一 mutation resolve 入口 | PASS | `_fs_storage_infra.py:531-571`：registry membership、canonical token match、ticker match、lifecycle=open、core binding |
| 无 `ContextVar` / `asyncio.current_task()` / thread ident | PASS | ambient authority scan = 0 |
| 无 `_execute_with_auto_batch` | PASS | 已删除，scan = 0 |
| child task/thread mutation 成功 | PASS | `test_explicit_batch_allows_child_task_mutation_on_shared_core` + `test_explicit_batch_allows_worker_thread_mutation_on_shared_core` |
| unknown/altered/closed/ticker mismatch/cross-core 拒绝 | PASS | `test_batch_registry_rejects_unknown_altered_closed_ticker_and_cross_core_tokens` 覆盖全部 5 条拒绝路径 |

### 5.3 Writer Mutex 与独立 Publication Guard

| 检查项 | 结论 | 直接证据 |
| --- | --- | --- |
| 两个不同锁文件 | PASS | writer: `batch_locks/<ticker>.lock` (line 670-683)；publication: `batch_locks/<ticker>.publication.lock` (line 685-699) |
| 锁序始终 writer → publication | PASS | `begin_batch` 获取 writer (line 257)；`commit_batch` 在 swap 短窗获取 publication (line 319)；recovery 先 writer 后 publication；审计无反向路径 |
| 无 ambient "guard held" 标志 | PASS | 无 `ContextVar`、无 task-local、无默认参数 |
| 异常释放：registry 先消费，writer 后释放 | PASS | `_close_active_batch` line 593-597 先 pop registry，line 599 释放 writer；release failure 附着 `.add_note()` 不覆盖 primary |
| COMMITTED 不被回滚 | PASS | `state.phase == _PHASE_COMMITTED` 时 publication release failure 设置 `post_commit_error`，不调 `_rollback_precommit_batch` |

### 5.4 Public Outer Guard / Private Unguarded Read Graph

| 检查项 | 结论 | 直接证据 |
| --- | --- | --- |
| 所有 public read 获取 guard 一次，调 private unguarded helper | PASS | 全部 5 core 文件的 23 个 public read 方法均有对应 `_*_unguarded` private helper |
| 无 public-to-public read 嵌套 | PASS | AST public self-call scan = 0 |
| `_ticker_dir_for_read` 只路由 published tree | PASS | `_fs_storage_infra.py:1562-1575` 只返回 `self._target_ticker_dir` |
| 长 staging writer 不阻塞 published reader | PASS | `test_concurrent_published_read_ignores_long_writer_staging_and_sees_old` 使用独立 `multiprocessing.Process` (spawn) 证明 |
| 两个 rename barrier 阻塞 reader | PASS | `test_concurrent_reader_blocks_at_each_publication_rename_barrier` parametrized 两个 barrier，使用 `threading.Event` 同步，child process 验证阻塞与终态 |

### 5.5 LocalFileSource Delayed Opener

| 检查项 | 结论 | 直接证据 |
| --- | --- | --- |
| opener 绑定 path/ticker，不绑定 batch | PASS | `_PublicationGuardedBinaryOpener.__init__` 只接受 `lock_path: Path` |
| `__call__` acquires guard → open → finally release | PASS | `_fs_storage_infra.py:97-115`：`finally` 块保证释放 |
| fd 成功/失败均释放 guard | PASS | `finally` 块在 `try` 之后无条件执行 |
| 后续流读取不持 guard | PASS | 返回的 `BinaryIO` 不持有 guard token |

### 5.6 Minimal Journal

| 检查项 | 结论 | 直接证据 |
| --- | --- | --- |
| 精确三字段 | PASS | `_JOURNAL_FIELDS = frozenset({"transaction_id", "ticker", "phase"})` (line 64) |
| 无 PID/hostname/绝对路径/owner token | PASS | `_write_batch_journal` payload 只含三字段 (line 802-822)；`hostname|PID|os.getpid|socket.gethostname|owner_token` scan = 0 |
| recovery 从固定 root 派生路径 | PASS | `_recover_single_batch_dir` 使用受控 root + journal 重派生，先过 containment/symlink 校验 |

### 5.7 Recovery Fail-Closed Continuation (VF-01)

| 检查项 | 结论 | 直接证据 |
| --- | --- | --- |
| invalid journal ticker → skip + continue | PASS | `_fs_storage_infra.py:887-893`：`ValueError` 单独捕获，`reason=invalid_journal_ticker` |
| invalid backup ticker → preserve + continue | PASS | `_fs_storage_infra.py:1001-1007`：`ValueError` 单独捕获，`reason=invalid_backup_ticker` |
| 不吞无关 I/O error | PASS | 只捕获 `ValueError` |
| 同轮合法 orphan 仍恢复 | PASS | `test_invalid_journal_ticker_preserves_evidence_and_later_orphan_recovers` + `test_invalid_orphan_backup_ticker_preserves_evidence_and_later_backup_recovers` |

### 5.8 Pre/Post-Commit Error Precedence (VF-03, VF-04)

| 检查项 | 结论 | 直接证据 |
| --- | --- | --- |
| VF-03 primary preserved，writer release 附着 note | PASS | `_close_active_batch` line 573-611：registry 先消费，release failure 用 `add_note()` |
| VF-04 COMMITTED 后 publication release 成为 post-commit primary | PASS | `commit_batch` line 344-351：`post_commit_error` 不调 rollback |
| 双重/三重 failure-injection tests 保持 primary identity | PASS | `test_commit_primary_failure_survives_writer_release_failure`、`test_commit_batch_publication_release_failure_preserves_committed_truth`、`test_rollback_journal_failure_survives_writer_release_failure` |

### 5.9 Containment/Symlink

| 检查项 | 结论 | 直接证据 |
| --- | --- | --- |
| ticker/document/entry normalize + root containment | PASS | `_normalize_ticker`、`_normalize_document_id`、`_normalize_entry_name`、`_resolve_handle_child_path` 用 `relative_to` 拒绝越界 |
| symlink transaction/journal 拒绝 | PASS | recovery 中 `is_symlink()` 检查 (line 841, 865, 992) |
| atomic JSON + rename + fsync | PASS | `_write_json` 先写 temp → fsync → `os.replace` → fsync parent |

### 5.10 安全行为与未越界检查

| 检查项 | 结论 | 直接证据 |
| --- | --- | --- |
| 无 S2 complete-source validator | PASS | 未实现 |
| 无 S2 ack 删除 | PASS | S2 ack scan = 59，全部 deferred |
| 无 S3 producer propagation | PASS | 全仓 pyright 110 = S2/S3 residual |
| 无 R07 snapshot/revision | PASS | `LocalFileSource` 只做 delayed opener guard |
| 无 Issue 175/177/178 | PASS | 未触及 |
| 无统一 authorization framework | PASS | 未设计 |
| 安全行为无回退 | PASS | containment/symlink/atomic/lock 均保留 |
| changed S1 files scoped pyright = 0 | PASS | 15 production + 4 tests = 0 errors |
| full pyright 110 = expected S2/S3 | PASS | 不登记为 S1 baseline |

## 6. Verification Evidence Summary

| 证据类型 | 结果 |
|---|---|
| Focused tests (plan §7.1 keyword filter) | `109 passed, 61 deselected, 3 warnings` |
| 四个 S1 test 文件完整运行 | `207 passed, 3 warnings` |
| Scoped pyright (15 production + 4 tests) | `0 errors, 0 warnings, 0 informations` |
| Full pyright | `110 errors`（全部 S2/S3，changed owner 0） |
| Scoped Ruff | `All checks passed!` |
| Full Ruff | `160 errors`（baseline 不变） |
| Ambient authority scan | `0` |
| S2 ack scan | `59`（全部 deferred） |
| Lifecycle scan | `170` |
| Mutation propagation scan | `165` |
| Locator scan | `118` |
| Public core read self-call AST | `[]` |
| Maintenance public call graph | 只含 normalize/acquire/delegate/release 五类 |
| Processed fallback wording scan | `0` |
| Production reprocess return consumers | `[]` |
| `git diff --check` | pass |
| Staged diff | 空 |
| Allowlist | 15 production + 4 tests + control doc（精确） |
| Changed file coverage | 全部 ≥ 80%（82%-100%） |

## 7. Subagent 覆盖区域

| Subagent | 覆盖范围 | 结论 |
| --- | --- | --- |
| infra transaction authority | `_fs_storage_infra.py`、`document_models.py`；10 项 adversarial 全量 | 0 material finding；10/10 PASS |
| cores/wrappers/protocols | 5 core + 6 wrapper + `repository_protocols.py` + `local_file_source.py`；8 维度审查含 CR-F01..03 | 0 material finding；全部 PASS |
| tests quality | 4 test files；11 项覆盖/质量/行为证明 | 0 material finding；11/11 PASS |

主 reviewer 独立运行全部验证命令、CR-F01..03 specific evidence scan、AST scan，并整合/去重/复核三路 subagent 结论。无冲突。

## 8. New Finding Ledger

**当前新 material finding = 0。**

全部 S1 owner contract（opaque BatchToken、explicit mutation authority、writer/publication lock 分离、public outer guard/private unguarded read graph、LocalFileSource delayed opener、minimal journal、recovery fail-closed continuation、pre/post-commit error precedence VF-01..04、containment/symlink、中文 docstring/strict typing）经三路 subagent 与主 reviewer 独立代码走读、测试运行、typing/lint/scan/AST 验证后确认成立。

CR-F01..03 全部在正确 owner boundary 闭合，fix 未引入新 defect。

## 9. Observations（非 material finding，不阻塞 PASS）

### O-01 — `read_rejected_filing_file_bytes` 已收敛（原 MiMo O-01 已关闭）

CR-F01 fix 已将该方法收敛为标准 outer guard / private unguarded graph。原 observation 不再适用。

### O-02 — `stage_source_document` / `ingest_complete=False` 保留（S2 intentional residual）

不变。S2 才删除 staging ack/incomplete contract。

### O-03 — 测试访问 `_ActiveBatchState` 等私有注册表

不变。accepted 测试策略，failure injection 需要。

### O-04 — 测试通过 `_ActiveBatchState` 物理路径注入 failure

不变。crash-phase/recovery 测试需要。

### O-05 — monkeypatch 私有方法注入 failure

不变。failure injection testing 固有局限。

### O-06 — 0.25s poll 辅助断言

不变。主同步依赖 Event barrier。

### O-07 — owner/AST guard 测试与实现耦合

不变。维护成本，非 correctness issue。

### O-08 — `_select_primary_document` 的 `previous_primary: Any`

不变。既有 JSON 反序列化边界，未触及。

### O-09 — 无测试验证 guard release 后续 reader 不被旧 guard 阻塞

不变。guard release 通过 `file_lock.release()` 删除 lock file，是幂等操作。

## 10. Plan Conformance

| Plan Section | 要求 | S1 状态 |
| --- | --- | --- |
| §3.1 最小 BatchToken | `transaction_id` + `ticker` | 实现 ✓ |
| §3.2 internal active state 边界 | registry + lifecycle + lock + locators | 实现 ✓ |
| §3.3 lifecycle 唯一协议 | 只在 BatchingRepositoryProtocol | 实现 ✓ |
| §3.4 全部 mutating public protocol | keyword-only non-optional `batch` | 实现 ✓ |
| §4.1 writer mutex 只作 writer mutex | 不授予 mutation authority | 实现 ✓ |
| §4.2 publication swap guard | 独立锁、短窗、outer guard + private unguarded | 实现 ✓ |
| §4.3 minimal journal | 3 字段 | 实现 ✓ |
| §7.1 S1 allowlist | 15 production + 4 tests | 实际修改 15+4 ✓ |
| §8.1 focused tests | batch/token/owner/recovery/atomic/concurrent | 109 passed ✓ |
| §8.3 source scans | ambient 0，其余 deferred | 符合 ✓ |
| §10 baseline | full pyright 0 → 110（S2/S3），full Ruff 162 → 160 | 符合 ✓ |
| §11 stop conditions | 无越界 | 符合 ✓ |
| CR-F01..03 controller adjudication | 三项均在 owner boundary 闭合 | 实现 ✓ |

## 11. Residual Risk

- S2：complete-source validator、blob-first cutover、ack 删除 — S1 未实施，属 accepted sequencing
- S3：producer/callback/composition propagation — 全仓 110 pyright error 是其机器可见清单
- R07：revision/snapshot/opaque-id/materialize — 8 文件/9 调用点的裸 `Path` 延迟读取无 snapshot consistency
- 测试技术债：O-03/O-04/O-07 的内部状态访问与实现耦合

## 12. Final Verdict

**PASS**

current finding = 0，blocking question = 0。

S1 的 15 个 production 文件和 4 个 test 文件正确实现了 accepted R06 plan §3、§4、§7.1 的全部 owner contract，并正确闭合了 CR-F01..03 三项 review finding：

- **CR-F01**：maintenance public read 已收敛为标准 outer guard / private unguarded helper graph，无 ambient marker、重入锁或 public compatibility 参数。
- **CR-F02**：processed meta contract 只承诺 published `tool_snapshot_meta.json`，无虚构 fallback；tests 从 storage owner 行为证明 legacy 文件不被读取。
- **CR-F03**：protocol/wrapper/shared core/private impl 返回语义统一为 `None`，`required=False`/existing/missing 副作用正确，生产调用无返回消费者。

三路 subagent 与主 reviewer 独立验证结论一致，无冲突。9 个 observations 记录为技术债，不阻塞 S1 gate。

**READY_FOR_S1_CONTROLLER_ACCEPTANCE**
