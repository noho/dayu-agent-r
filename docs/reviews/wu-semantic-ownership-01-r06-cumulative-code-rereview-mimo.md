# WU-SEMANTIC-OWNERSHIP-01 R06 累计 code re-review 第一路 (MiMo)

## Review 身份

- Umbrella WU：`WU-SEMANTIC-OWNERSHIP-01`
- 内部 remediation sub-WU：R06 Fins 显式 batch authority 与完整 source publication
- Gate：累计 S1+S2+S3 双路 complete code re-review 第一路
- 实现基线：`d048adf7ec1135aaf575384432ebf1137f8a34f2`（当前 HEAD，working tree 未提交变更）
- Review 日期：2026-07-16
- Reviewer：AgentMiMo

## Scope

- Mode: current changes（d048adf7 到当前 working tree 完整未提交变更）
- Branch: `phaseflow/host-issues-control`
- Base: `d048adf7ec1135aaf575384432ebf1137f8a34f2`
- Included scope: 57 个变更文件，10712 行插入，3614 行删除
- Parallel review coverage: 6 个 subagents 并行审查（F01/F02/F03/F04/smuggling/S1-S2 regression），主 reviewer 独立验证并整合

## Verdict

**PASS / 0 个新 material findings / 0 个 blocking questions。R06-CR-F01..F04 全部 CLOSED。Ready for Controller adjudication。**

## R06-CR-F01..F04 Closure Ledger

| Finding | Status | 证据摘要 |
|---|---|---|
| R06-CR-F01 | **CLOSED** | `_recover_single_batch_dir()` 对不可解析/非 object JSON 抛 `ValueError` 被 `except ValueError` 捕获，归类为稳定 `unparseable_journal` reason，skip 且保留 evidence 目录；`_recover_orphan_batch_dirs()` 逐目录独立循环，单个 skip 不阻断后续合法 orphan 恢复。测试 `test_unparseable_journal_preserves_evidence_and_later_orphan_recovers` 参数化覆盖 `"{"`, `""`, `"[]"` 三种场景。 |
| R06-CR-F02 | **CLOSED** | `rebuild_single_local_filing()` 的 `try` 只包裹 mutation，`except BaseException` 内 `rollback_batch` 调用恰好一次；`commit_batch` 在 `try/except` 之后，commit 后无 rollback 路径。取消类 `BaseException` 原样 re-raise；rollback 失败时原 operation error 为主异常、rollback 为 `__cause__`、诊断 note 稳定。测试覆盖 KeyboardInterrupt/SystemExit re-raise、dual-failure identity/cause/note、ordinary failure + successful rollback。 |
| R06-CR-F03 | **CLOSED** | `_rollback_batch_before_commit` 模块级私有 helper 供三条 mutation path 复用；`sys.exception()` 捕获主异常，rollback 失败时 `raise operation_error from rollback_error`，诊断 note 使用 `_ROLLBACK_FAILURE_NOTE_PREFIX` 常量。测试覆盖 `_store_rejected_filing_artifact` 和 `_preprocess_one_document` 的 dual-failure owner test。 |
| R06-CR-F04 | **CLOSED** | child 在 `_PublicationGuardAcquireSignal` 中 patch `core._acquire_publication_guard`，在实际 public reader 即将获取 guard 的调用点发送 `b"publication_acquire_entered"` 后进入真实 blocking acquire；parent 收到信号后尝试非阻塞 acquire 并 assert 失败，证明结果尚未发布，再释放 rename barrier。两个 barrier 参数均通过，最终断言只能观察完整 new/old 集合。 |

## S1/S2/S3 Accepted Findings 回归检查

| Finding | Status | 证据摘要 |
|---|---|---|
| R06-S1-CR-F01 maintenance private unguarded read helper | **CLOSED** | `_fs_maintenance_core.py` 的 `read_rejected_filing_file_bytes` 已收敛为标准 outer guard / private unguarded helper graph，无 ambient marker、重入锁或 public compatibility 参数 |
| R06-S1-CR-F02 processed meta 不存在 fallback 描述删除 | **CLOSED** | processed meta contract 只承诺 published `tool_snapshot_meta.json`，无虚构 fallback；tests 从 storage owner 行为证明 legacy 文件不被读取 |
| R06-S1-CR-F03 mark reprocess 返回 protocol-owned None | **CLOSED** | protocol/wrapper/shared core/private impl 返回语义统一为 `None`，`required=False`/existing/missing 副作用正确，生产调用无返回消费者 |
| R06-S2-CR-F01 explicit primary mismatch 返回 None、不猜 first file | **CLOSED** | `_resolve_primary_uri` 唯一 owner 关闭：missing/mismatch → None、exact hit 保留、无 caller/validator 补偿 |
| R06-S3-CV-F01 preprocess completion 缺失分支缺少直接测试 | **CLOSED** | Controller 独立验证通过，直接测试已补充 |
| 显式唯一 BatchToken authority | **CLOSED** | 72 个 `batch=` 调用点显式传递 token；`_resolve_active_batch` 验证 transaction_id 非空、已注册、canonical token identity、ticker match、OPEN lifecycle |
| 完整 source 单次发布 | **CLOSED** | CN/SEC/Docling 均 blob-first（store_file 在 source meta 之前）+ 单次 commit_batch |
| Commit/recovery/publication guard | **CLOSED** | 7 条 begin_batch/commit_batch 路径均使用 `commit_started` fence；publication guard 提供跨进程 fence；journal-based recovery 处理 orphans |
| Cancellation/primary-error | **CLOSED** | `_rollback_batch_before_commit` 保留主异常；`save_failed_or_cancelled_if_active` 优先 cancelled；upload path 在 6 个 stage boundary 检查 cancellation |
| Shared-core composition | **CLOSED** | 4 个 production composition root（CnPipeline、SecPipeline、DefaultFinsRuntime、standalone 6-K repair）创建单一 `_FsRepositorySet` 传递给所有 FS repository |
| Reader old/new 原子性 | **CLOSED** | publication guard（per-ticker blocking lock）在 physical swap 期间持有；所有 reader 获取同一 guard，确保只见旧完整或新完整 |

## Rejected/Deduplicated/Deferred Findings 偷带检查

| Finding | 裁决 | 偷带状态 | 证据 |
|---|---|---|---|
| R06-CR-MIMO-F01 | REJECTED | **未偷带** | journal phase 序列仍为 `started -> backed_up_target -> swapped_target -> committed -> rolled_back`，`SWAPPED_TARGET` 仍为 pre-commit phase |
| R06-CR-MIMO-F03 | REJECTED | **未偷带** | lock release 通过 `_release_lock_token` 的 `token.release()`，publication guard 在 `finally` 块中正常 cleanup，无 force-release |
| R06-CR-MIMO-F05 | REJECTED | **未偷带** | BatchToken 收窄为 `(transaction_id, ticker)` 是 plan §1.1/§1.2 明确要求；plan §2 表格明确"staging/backup/journal locator 不进入 public token"。subagent 的"偷带"判断是误读 rejection——rejection 是关于"opaque 不等于 hidden"，不是禁止收窄字段 |
| R06-CR-MIMO-F06 | REJECTED | **未偷带** | 无 format/grammar validation 代码；`_validate_complete_source_tree` 是 structural integrity validation，不是 document content format/grammar |
| R06-CR-MIMO-F07 | REJECTED | **未偷带** | `_upsert_processed_manifest` 使用标准 `ProcessedManifestItem.to_dict()` 投影，无变更 |
| R06-CR-MIMO-F08 | REJECTED | **未偷带** | `DocumentSummary.from_dict` 的 `source_kind` 默认值未变 |
| R06-CR-MIMO-F09 | REJECTED | **未偷带** | `list_rejected_filing_artifacts` 保留 same skip-on-error pattern，仅增加 publication guard 包裹 |
| R06-CR-MIMO-F10 | REJECTED | **未偷带** | `_upsert_processed` 接收 caller 的 `_ActiveBatchState`，未实现自己的 transaction |
| R06-CR-MIMO-F11 | REJECTED | **未偷带** | `_validate_complete_source_tree` 只迭代 `SourceKind.FILING` 和 `SourceKind.MATERIAL`，不验证 processed/company/maintenance |
| R06-CR-MIMO-F12 | REJECTED | **未偷带** | 无 touched tracking 代码 |
| R06-CR-DS-F03 | REJECTED | **未偷带** | explicit batch injection 是 plan §1.1 的核心要求；CnPipeline/SecPipeline 仍为 default composition root，内部创建 `build_fs_repository_set()`。rejection 是关于"不得把默认 root 改成 required external batching facade"，当前实现保持 pipelines 为默认 root |
| R06-CR-DS-F04 | REJECTED | **未偷带** | 新测试 `test_batch_registry_rejects_unknown_altered_closed_ticker_and_cross_core_tokens` 测试新 validation 逻辑，不是重复不可能状态测试 |
| R06-CR-DS-F05 | REJECTED | **未偷带** | pipeline 文件使用 host 提供的 shared `batching_repository`，无重复断言 |
| R06-CR-DS-F06 | DEFERRED | **未偷带** | 无 revision/snapshot/opaque-id/retry/cache 代码 |

## Adversarial Failure Pass

### 检查项

1. **auth/permissions/trust boundaries**: BatchToken authority 由 `_resolve_active_batch` 在 owner boundary 统一校验，无绕过路径
2. **data loss/corruption**: recovery 只在所有 validation 通过后删除 staging 目录；malformed evidence 始终保留
3. **rollback safety**: 所有 rollback 路径恰好调用一次；dual-failure 时保留主异常
4. **race conditions**: publication guard 提供 per-ticker 互斥；commit-start fence 防止 commit 后 rollback
5. **empty-state/null/timeout**: unparseable journal 被正确分类并 skip；recovery 循环继续处理后续 orphan
6. **duplicate requests/already-terminal state**: `_resolve_active_batch` 拒绝非 OPEN 状态的 token

### 未发现实质性问题

## Semantic Ownership Drift Pass

### 检查项

1. **下游补齐上游 contract**: 未发现。所有 mutation 通过显式 `batch=` 获取 authority，无 fallback/特例/loose parsing
2. **多个可写真源**: 未发现。batch lifecycle 由 `BatchingRepositoryProtocol` 独立管理
3. **多消费者反推语义**: 未发现。所有 consumer 通过 protocol 获取 BatchToken
4. **状态多处隐式修改**: 未发现。batch state 由 `_ActiveBatchState` 集中管理
5. **返回成功但状态半提交**: 未发现。commit/recovery 通过 journal 和 publication guard 保证原子性

### 未发现实质性问题

## 过度耦合检查

### 检查项

1. **跨层穿透**: 未发现。storage 层通过 protocol 对外暴露，pipeline 通过 protocol 调用
2. **双向依赖**: 未发现。依赖方向为 pipeline -> protocol -> storage core
3. **共享可变状态**: 未发现。batch state 由 per-ticker registry 管理
4. **过宽公共契约**: 未发现。BatchToken 只暴露 transaction_id 和 ticker

### 未发现实质性问题

## 测试真实性检查

### 检查项

1. **测试覆盖真实行为**: 是。测试使用真实 filesystem、独立 process、真实 blocking acquire
2. **测试覆盖 failure paths**: 是。覆盖 unparseable journal、dual-failure rollback、cancellation re-raise
3. **测试覆盖 boundary conditions**: 是。参数化覆盖多种 journal 格式、两种 barrier 类型
4. **assertions 未被削弱**: 是。断言 exception identity、cause chain、note content、rollback count

### 未发现实质性问题

## README 检查

- `dayu/fins/README.md`: 已更新，反映新的 batch authority 和 storage 架构
- `tests/README.md`: 已更新，反映新的测试职责

### 未发现实质性问题

## 安全边界检查

### 检查项

1. **symlink attacks**: `_is_contained_recovery_path` 检查整个路径链的 `is_symlink()`
2. **containment violations**: token_dir、target_dir、backup_dir、staging_dir、journal_path 均检查 containment
3. **lock safety**: publication guard 通过 fd lock 实现，进程终止时自动释放

### 未发现实质性问题

## 验证结果

- **pyright**: 0 errors, 0 warnings（`dayu/fins/` 全模块）
- **test_fins_storage_atomicity.py**: 110 passed
- **test_sec_pipeline_download.py**: 50 passed
- **test_fins_ingestion_runtime.py**: 85 passed

## Open Questions

无

## Residual Risk

1. **publication lock release syscall operational residual**: 极低概率 unlock syscall failure 时进程内存活风险由 `dayu.runtime.filelock` owner 承担；安全恢复点是进程终止释放 fd，不在 Fins recovery 伪造 force-release。此为 accepted S1 contract 已确认的 operational residual，不是 current finding。
2. **R07 独占 multi-read snapshot/revision residual**: 跨多次 read / processor cache 的 revision-change-after-build 是 accepted plan 明确交给 R07 的唯一 residual；R06 不得提前实现或用测试冻结 R07 contract。此为 deferred R07 scope，不是 current finding。

## 结论

R06 累计 code re-review 第一路 **PASS**。四个 accepted fix groups 全部正确实现并关闭；S1/S2 accepted findings 保持关闭无回归；rejected/deduplicated/deferred findings 未偷带；adversarial failure pass、semantic ownership drift、过度耦合、测试真实性、README 和安全边界检查均未发现实质性问题。Ready for Controller adjudication。
