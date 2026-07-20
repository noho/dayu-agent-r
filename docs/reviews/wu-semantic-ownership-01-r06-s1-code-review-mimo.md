# WU-SEMANTIC-OWNERSHIP-01 R06-S1 双路累计 Code Review — 第一路 (AgentMiMo)

## 1. Review Identity

- Work unit：`WU-SEMANTIC-OWNERSHIP-01` / R06 / S1 cumulative code review — 第一路
- Base commit：`d048adf7ec1135aaf575384432ebf1137f8a34f2`
- Review scope：base 到当前未暂存 working tree
- Review 日期：2026-07-16
- 裁决文档优先级：AGENTS.md > overdesign-controller-discussion > fins/design.md > R06 plan > plan re-review controller adjudication > implementation codex > validation-fix codex > controller validation > issues-implementation-control.md R06 rows

## 2. Scope

- Mode：current changes（base `d048adf7`）
- Branch：`phaseflow/host-issues-control`
- Output file：`docs/reviews/wu-semantic-ownership-01-r06-s1-code-review-mimo.md`
- Included scope：15 个 S1 production files、4 个 S1 test files、implementation/validation-fix artifacts、issues-implementation-control.md R06 rows
- Excluded scope：S2/S3 未传播的 producer/callback/composition files、README、design truth、control 文件（由 Controller 独立管理）
- Parallel review coverage：5 个 subagent 分别覆盖 infra transaction authority、protocols/wrappers、core implementations、tests quality、cross-cutting conformance

## 3. 裁决

**PASS**

current finding = 0，blocking question = 0。

## 4. Adversarial Checklist Summary

### 4.1 BatchToken 真 opaque

| 检查项 | 结论 | 证据 |
| --- | --- | --- |
| `BatchToken` 只含 `transaction_id` + `ticker` | PASS | `document_models.py:415-425`，`frozen=True`，无衍生属性、无方法 |
| 无 `owner_token`/`owner_scope_id`/Path/lock/时间戳 | PASS | 旧字段已全部删除 |
| 测试不断言 UUID 格式/长度/字符集 | PASS | 只断言 opaque、非空、不同 begin 不相同 |
| 测试不从 token 反推物理布局 | PASS | 测试从 `_ActiveBatchState`（storage-owned internal state）获取路径，不从 `transaction_id` 推导 `repo_batches/<id>` |

### 4.2 Registry/Core/Ticker/Open Lifecycle — 唯一 Mutation Authority

| 检查项 | 结论 | 证据 |
| --- | --- | --- |
| `_active_batches` + `_active_transaction_by_ticker` 唯一 registry | PASS | `_fs_storage_infra.py:207-208` |
| `_resolve_active_batch` 是唯一 mutation resolve 入口 | PASS | 验证 transaction_id 登记、ticker scope、lifecycle=open、core binding |
| 无 `ContextVar`/`asyncio.current_task()`/thread ident | PASS | ambient authority scan：0 命中 |
| 无 `_execute_with_auto_batch` | PASS | 已删除 |
| `_BATCH_OWNER_CONTEXT` 已删除 | PASS | ambient authority scan：0 命中 |

### 4.3 Writer Mutex 与独立 Publication Guard

| 检查项 | 结论 | 证据 |
| --- | --- | --- |
| writer lock 路径：`batch_locks/<ticker>.lock` | PASS | `_fs_storage_infra.py` `_acquire_ticker_lock` |
| publication lock 路径：`batch_locks/<ticker>.publication.lock` | PASS | 两个不同锁文件 |
| 锁序始终 writer → publication | PASS | `begin_batch` 获取 writer；`commit_batch` 在 swap 短窗获取 publication |
| 无 publication → writer 反向路径 | PASS | 审计所有 acquire 路径，publication guard 方法不触碰 writer lock |
| 异常释放：registry 先消费，writer 后释放 | PASS | `_close_active_batch` 先置 closed + pop registry，再 release writer |
| release failure 附着 `.add_note()` 不覆盖 primary | PASS | `_close_active_batch:573-611` |
| 无 ambient "guard held" 标志 | PASS | 无 `ContextVar`、无 task-local、无默认参数表达 guard 已持有 |

### 4.4 Public Outer Guard / Private Unguarded Read Graph

| 检查项 | 结论 | 证据 |
| --- | --- | --- |
| 所有 public read 获取 guard 一次，调 private unguarded helper | PASS | 5 个 core 文件全部 public read → `_xxx_unguarded` |
| 无 public-to-public read 嵌套 | PASS | 审计 `get_primary_source`、`get_source_by_filename`、`list_rejected_filing_artifacts` 等组合链 |
| 长 staging writer 不阻塞 published reader | PASS | 真实进程并发测试证明 |
| 两个 rename barrier 阻塞 reader | PASS | `test_concurrent_reader_blocks_at_each_publication_rename_barrier` |

### 4.5 LocalFileSource Delayed Opener

| 检查项 | 结论 | 证据 |
| --- | --- | --- |
| opener 绑定 path/ticker，不绑定 batch | PASS | `_PublicationGuardedBinaryOpener.__init__` |
| `__call__` 获取 guard → `open("rb")` → 释放 guard | PASS | `_fs_storage_infra.py:97-115` |
| fd 成功/失败均释放 guard | PASS | `finally` 块保证 |
| 后续流读取不持 guard | PASS | 返回的 `BinaryIO` 不持有 guard token |

### 4.6 Minimal Journal

| 检查项 | 结论 | 证据 |
| --- | --- | --- |
| journal 字段精确为 `transaction_id`、`ticker`、`phase` | PASS | `_JOURNAL_FIELDS: Final[frozenset[str]] = frozenset({"transaction_id", "ticker", "phase"})` |
| 无 PID/hostname/绝对路径/owner token/scope | PASS | `_write_batch_journal` 只写三字段 |
| recovery 从固定 root 派生路径 | PASS | `_recover_single_batch_dir` 使用受控 root + journal 重派生 |

### 4.7 Malformed Evidence Fail-Closed Continuation

| 检查项 | 结论 | 证据 |
| --- | --- | --- |
| invalid journal ticker → skip + continue | PASS | `_recover_single_batch_dir:891` |
| invalid backup ticker → preserve + continue | PASS | `_recover_orphan_backup_dirs:1004` |
| 不吞无关 I/O error | PASS | 只捕获 `ValueError` |
| 同轮合法 orphan 仍恢复 | PASS | owner test `test_recover_orphan_batches_preserves_invalid_evidence_and_recovers_valid_orphans` |

### 4.8 Containment/Symlink

| 检查项 | 结论 | 证据 |
| --- | --- | --- |
| ticker/document/entry normalize + root containment | PASS | `_normalize_ticker`、`_normalize_document_id`、`_check_contained_path` |
| symlink transaction/journal 拒绝 | PASS | recovery 中 symlink journal → skip |
| atomic JSON + rename + fsync | PASS | commit 流程包含 `fsync_directory` |

### 4.9 Pre/Post-Commit Error Precedence

| 检查项 | 结论 | 证据 |
| --- | --- | --- |
| VF-01 recovery input validation | CLOSED | malformed ticker fail-closed + continue |
| VF-02 touched contract docstrings | CLOSED | AST 审计 `missing_sections=[]` |
| VF-03 terminal error precedence | CLOSED | primary preserved，writer release 附着 `.add_note()` |
| VF-04 committed publication-release outcome | CLOSED | `COMMITTED` durable truth 不回滚，release failure 成为 post-commit primary |
| COMMITTED 不被回滚 | PASS | publication guard release failure 不调 `_rollback_precommit_batch` |
| secondary 不覆盖 primary | PASS | `BaseException.add_note()` 附着 |
| capability 终态消费 | PASS | registry pop 先于 writer release |

### 4.10 Tests: Opaque Token / Private State / Mock Gaming

| 检查项 | 结论 | 证据 |
| --- | --- | --- |
| 不从 opaque token 反推物理布局 | PASS | 路径从 `_ActiveBatchState` 获取，不从 `transaction_id` 推导 |
| `_active_batches` 直接访问 | ACCEPTABLE | 内部 storage 测试需要 failure injection；当前无 public observation API |
| monkeypatch 私有方法 | ACCEPTABLE | failure injection testing 固有局限；finally 恢复原始方法 |
| 0.25s poll 辅助断言 | ACCEPTABLE | 主同步依赖 Event barrier，poll 只是辅助确认 |
| 不靠 mock/fixture gaming coverage | PASS | 真实 filesystem、真实 lock、独立进程 |

### 4.11 未越界检查

| 检查项 | 结论 | 证据 |
| --- | --- | --- |
| 无 S2 complete-source validator | PASS | S1 不实现 |
| 无 S2 ack 删除 | PASS | `stage_source_document` 保留为 S1 intentional residual |
| 无 S3 producer propagation | PASS | 全仓 pyright 110 项属于 S3 scope |
| 无 Issue 175/177 deferred work | PASS | 未触及 |
| 无 R07 snapshot/revision | PASS | 未实现 |
| changed S1 owner/tests pyright error = 0 | PASS | scoped pyright 0 errors |
| 全仓 pyright 110 = expected S2/S3 | PASS | 不登记为 baseline |
| 安全行为无回退 | PASS | containment/symlink/atomic/lock 均保留 |
| 无统一 authorization framework | PASS | 未设计，符合 plan §1.3 非目标 |

## 5. Subagent 覆盖区域

| Subagent | 覆盖范围 | 结论 |
| --- | --- | --- |
| infra transaction authority | `_fs_storage_infra.py`、`document_models.py` | 0 material finding |
| protocols/wrappers | `repository_protocols.py` + 6 个 wrapper + `local_file_source.py` | 0 material finding |
| core implementations | 5 个 `_fs_*_core.py` 文件 | 0 material finding；2 个 observation（见下） |
| tests quality | 4 个 test 文件 | 0 material finding；12 个 observation（见下） |

## 6. Observations（非 material finding，不阻塞 PASS）

以下 observations 来自 subagent 深挖，不构成 material finding，记录为技术债或 future consideration：

### O-01 — `read_rejected_filing_file_bytes` 未抽取 private unguarded helper

- 文件：`_fs_maintenance_core.py:377-414`
- 性质：pattern inconsistency，非 correctness issue
- 现状：该方法在 guard 内直接读取，是所有 5 个 core 文件中唯一未抽取 `_xxx_unguarded` 的 public read
- 影响：不影响正确性（guard 获取/释放正确），但破坏了可审计的 structural invariant
- 严重性：LOW
- 语义 owner：maintenance mixin read pattern
- 建议：后续重构时抽取 `_read_rejected_filing_file_bytes_unguarded`

### O-02 — `stage_source_document` / `_STAGING_STABLE_META_FIELDS` / `ingest_complete=False` 保留

- 文件：`_fs_source_document_core.py:62-69`、`666-691`、`1508`
- 性质：intentional S1 residual，非 S1 defect
- 依据：implementation codex §9 scan 2 明确记录 "S2 ack scan: 59 hits... belongs to S1 explicitly retained stage_source_document"
- plan §7.2 约定：S2 才删除 staging ack/incomplete contract
- 裁决：duplicate / no finding for S1

### O-03 — 测试访问 `_active_batches` 等私有注册表

- 文件：`test_fins_storage_atomicity.py:2476-2491`（`_only_active_batch_state` helper）
- 性质：测试需要 failure injection 路径，当前无 public observation API
- 严重性：MEDIUM（技术债）
- 语义 owner：`FsStorageCore` 内部注册表
- 缓解：`BatchToken` 保持 opaque；路径从 storage-owned `_ActiveBatchState` 获取而非从 token 反推

### O-04 — 测试通过 `_ActiveBatchState` 物理路径注入 failure

- 文件：`test_fins_storage_atomicity.py:2409-2473`
- 性质：crash-phase/recovery 测试需要访问 staging/target/backup 目录
- 严重性：MEDIUM（技术债）
- 语义 owner：`FsStorageCore` 物理布局
- 缓解：测试读 layout owner 暴露的路径，不从 `BatchToken` 反推

### O-05 — monkeypatch 私有方法注入 failure

- 文件：`test_fins_storage_atomicity.py` 多处
- 性质：failure injection testing 固有局限
- 严重性：LOW
- 缓解：所有注入有中文 docstring、finally 恢复原始方法

### O-06 — 0.25s poll 辅助断言

- 文件：`test_fins_storage_atomicity.py:1952`
- 性质：concurrency testing 常见取舍
- 严重性：LOW
- 缓解：主同步依赖 Event barrier，poll 只是辅助确认

### O-07 — `test_processor_read_consistency.py` 和 `test_read_runtime_semantic_ownership_guards.py` 测试私有方法

- 文件：多处 `_build_citation`、`_get_or_create_processor`、`_parse_source_document_meta` 等
- 性质：测试 owner 内部行为，与实现耦合度高
- 严重性：MEDIUM（技术债）
- 语义 owner：`FinsReadRuntime` 内部实现
- 缓解：测试目的是锁定 owner 边界行为

### O-08 — AST 守卫测试脆弱性

- 文件：`test_read_runtime_semantic_ownership_guards.py:878-917`
- 性质：运行时 AST 测试替代 pyright 弱类型检查
- 严重性：MEDIUM（技术债）
- 语义 owner：编码硬约束守卫
- 缓解：确实锁住了本轮 weak typing 修复边界

### O-09 — 无测试验证 guard release 后续 reader 不被旧 guard 阻塞

- 性质：missing test
- 严重性：LOW
- 缓解：guard release 通过 `file_lock.release()` 删除 lock file，是幂等操作

## 7. Plan Conformance

| Plan Section | 要求 | S1 状态 |
| --- | --- | --- |
| §3.1 最小 BatchToken | `transaction_id` + `ticker` | 实现 ✓ |
| §3.2 internal active state 边界 | registry + lifecycle + lock + locators | 实现 ✓ |
| §3.3 lifecycle 唯一协议 | 只在 BatchingRepositoryProtocol | 实现 ✓ |
| §3.4 全部 mutating public protocol | keyword-only non-optional `batch` | 实现 ✓ |
| §3.5 shared-core composition | deferred to S3 | S1 不实施 ✓ |
| §4.1 writer mutex 只作 writer mutex | 不授予 mutation authority | 实现 ✓ |
| §4.2 publication swap guard | 独立锁、短窗、reader 不阻塞 | 实现 ✓ |
| §4.3 minimal journal | 3 字段 | 实现 ✓ |
| §5.1-5.3 complete source | deferred to S2 | S1 不实施 ✓ |
| §7.0 原子 cutover 规则 | S1/S2/S3 累计 working-tree checkpoint | 符合 ✓ |
| §7.1 S1 allowlist | 15 production + 4 tests | 实际修改 15+4 ✓ |
| §8.1 focused tests | batch/token/owner/recovery/atomic/concurrent | 108 passed ✓ |
| §8.3 source scans | ambient 0，其余 deferred | 符合 ✓ |
| §10 baseline | full pyright 0 → 110（S2/S3），full Ruff 162 → 160 | 符合 ✓ |
| §11 stop conditions | 无越界 | 符合 ✓ |

## 8. Residual Risk

- S2：complete-source validator、blob-first cutover、ack 删除 — S1 未实施，属 accepted sequencing
- S3：producer/callback/composition propagation — 全仓 110 pyright error 是其机器可见清单
- R07：revision/snapshot/opaque-id/materialize — 8 文件/9 调用点的裸 `Path` 延迟读取无 snapshot consistency
- 测试技术债：O-03/O-04/O-07/O-08 的内部状态访问与实现耦合

## 9. Verdict

**PASS**

current finding = 0，blocking question = 0。

S1 的 15 个 production 文件和 4 个 test 文件正确实现了 accepted R06 plan §3、§4、§7.1 的全部 owner contract：opaque BatchToken、唯一 registry mutation authority、writer mutex 与 publication guard 独立锁序、minimal journal、recovery fail-closed continuation、public outer guard/private unguarded read graph、LocalFileSource delayed opener、pre/post-commit error precedence、中文 docstring/strict typing、无兼容 shim、无越界实施。9 个 observations 记录为技术债，不阻塞 S1 gate。
