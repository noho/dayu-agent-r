# UF-FIX11 Deep Review: State/Owner 专项

## Scope

- Mode: current changes (专项 review)
- Branch: codex/upload-filing-oracle
- Base: 94182a0c
- HEAD: 91dbf843
- Output file: docs/reviews/uf-fix11-deepreview-state-owner-mimo-20260817.md
- Included scope: authoritative company identity decision, publication-lock reread, atomic publish/rollback, alias merge/collision, fresh/stale metadata, skip/preserve-intent, concurrency/cancellation/kill/recovery
- Excluded scope: CLI 投影细节、UI 层、tool schema
- Parallel review coverage: 无

## Findings

未发现实质性问题。

以下为逐维度走读结论与直接证据。

---

### 维度 1: Authoritative Company Identity Decision

**决策链路**: `resolve_upload_company_meta_decision()` (upload_company_meta.py:47) → `UploadCompanyMetaDecision` → `stage_upload_company_meta_decision()` → storage `stage_company_meta_intent()` → commit-time `merge_company_meta_for_commit()` (company_meta_contract.py:187)

**走读结论**: 决策 owner 清晰。`upload_company_meta.py` 拥有"是否需要 stage"的纯决策；`company_meta_contract.py` 拥有 commit-time 合并规则；`_fs_storage_infra.py` 拥有 commit-time identity guard 与 publication-lock 内重读。

**直接证据**:
- `resolve_upload_company_meta_decision` 在 validation 时基于 `existing_meta` 快照做出 keep/skip/stage 决策 (upload_company_meta.py:91-125)
- `_prepare_company_identity_commit` 在 commit-time publication guard 内重读 `current_published` (fs_storage_infra.py:767)，然后调用 `merge_company_meta_for_commit` (fs_storage_infra.py:768-772)
- `merge_company_meta_for_commit` 用 `CompanyMetaNonIdentitySnapshot` 做乐观前置条件检查 (company_meta_contract.py:239)

**语义所有权**: 决策在 `upload_company_meta.py`，合并规则在 `company_meta_contract.py`，commit-time 重读与 guard 在 `_fs_storage_infra.py`。无漂移。

---

### 维度 2: Publication-Lock Reread

**走读结论**: `_read_current_company_meta_for_commit` 在 publication guard 内读取 authoritative CompanyMeta，然后在同一 identity guard 内完成合并与唯一性校验。

**直接证据**:
- `_commit_batch_with_identity_guards` 按固定锁序：recovery lock → company identity lock → `_prepare_company_identity_commit` → publication guard (fs_storage_infra.py:635-674)
- `_prepare_company_identity_commit` 内部调用 `_read_current_company_meta_for_commit` (fs_storage_infra.py:767)，该方法在 publication guard 内读取 (fs_storage_infra.py:812)
- 读取后立即调用 `merge_company_meta_for_commit` (fs_storage_infra.py:768)，合并发生在 identity guard 内
- 合并后扫描全量 published identities 做唯一性校验 (fs_storage_infra.py:778-791)

**并发安全**: company identity guard 是全局锁，序列化所有 company meta mutation。publication guard 是 per-ticker 锁，保护 physical swap。两层锁序固定，无死锁风险。

---

### 维度 3: Atomic Publish/Rollback

**走读结论**: `batch_terminal_started` 模式确保 exactly-once rollback/commit。commit 分为 identity guard + publication guard 两阶段，每阶段失败都有独立 rollback 路径。

**直接证据**:
- `execute_prepared_filing_publication` 使用 `batch_terminal_started` flag (filing_upload_publication.py:695)
- 所有 terminal 路径（cancel、conflict、skip、publish）都设置 `batch_terminal_started = True` 后才转交 capability
- `finally` 块检查 `if not batch_terminal_started` 执行 rollback (filing_upload_publication.py:846-851)
- `commit_prepared_upload_batch` 内部同样使用 `batch_terminal_started` 模式 (docling_upload_service.py:1410-1437)
- `_commit_batch_with_publication_guard` 使用 journal 记录 phase (started → backed_up_target → swapped_target → committed)，失败时 `_rollback_precommit_batch` 恢复 (fs_storage_infra.py:676-735)

**rollback 失败处理**: `_raise_failure_after_rollback` 保留 primary failure，rollback failure 附着为 note (filing_upload_publication.py:567-593)。`rollback_prepared_upload_batch` 同样保留 primary error (docling_upload_service.py:1440-1468)。

---

### 维度 4: Alias Merge/Collision

**走读结论**: alias union 在 `merge_company_meta_for_commit` 中完成，uniqueness 校验在 `_prepare_company_identity_commit` 中完成。

**直接证据**:
- `merge_company_meta_for_commit` 合并 aliases: `(*current_published.ticker_identity.accepted_aliases, *intent.proposed_identity.accepted_aliases)` (company_meta_contract.py:213-216)
- `build_company_ticker_identity` 内部去重并校验 (ticker_normalization.py)
- `_prepare_company_identity_commit` 扫描全量 published identities 构建 unique index (fs_storage_infra.py:778-779)
- 对 `final_meta.ticker_identity.lookup_tickers()` 中每个 lookup ticker 检查是否已被其它 corpus 占用 (fs_storage_infra.py:783-791)
- 冲突时抛出 `CompanyTickerAliasConflictError`，携带 alias、existing_canonical、incoming_canonical (repository_protocols.py:321-359)

**边界**: `CompanyTickerAliasConflictError.__init__` 校验所有 ticker 必须是 normalized (repository_protocols.py:349-355)。

---

### 维度 5: Fresh/Stale Metadata

**走读结论**: freshness 由 `resolver_version` 比较决定。fresh 时 preserve_published，stale 时 refresh_if_stale。

**直接证据**:
- `_existing_company_meta_is_fresh` 比较 `existing_meta.resolver_version == resolver_version` (upload_company_meta.py:276-290)
- fresh + identity/name unchanged → "keep" (upload_company_meta.py:99-100)
- fresh + identity/name changed → "stage" with `preserve_published` (upload_company_meta.py:101-112)
- stale → "stage" with `refresh_if_stale` (upload_company_meta.py:113-125)
- commit-time: `_company_meta_from_published` 保留 published 非身份事实 (company_meta_contract.py:351-378)
- commit-time: `_company_meta_from_refresh` 使用显式 refresh facts (company_meta_contract.py:381-412)

**并发 stale 检测**: `merge_company_meta_for_commit` 中，若乐观前置条件失效 (snapshot 不匹配) 但 resolver_version 相同，回退到 published facts (company_meta_contract.py:245-250)；若 resolver_version 不同，抛出 `CompanyMetaConcurrentUpdateError` (company_meta_contract.py:252)。

---

### 维度 6: Skip/Preserve-Intent

**走读结论**: skip 裁决分两层：preparation owner 的 `initial_skip_disposition` 和 batch arbitration 的 `_canonical_skip_requirements_are_met`。

**直接证据**:
- `_can_skip_upload` 在 preparation 时检查 source_fingerprint 相同 (docling_upload_service.py:1615-1647)
- filing 场景设置 `FilingInitialSkipDisposition.IDENTICAL_PUBLICATION` (docling_upload_service.py:485-487)
- `arbitrate_filing_upload_publication` 在 stable observation 下检查 `initial_skip_disposition` 和 `_canonical_skip_requirements_are_met` (filing_upload_publication.py:493-498)
- `_canonical_skip_requirements_are_met` 要求: fresh COMPLETE + publication identity 匹配 + company decision 为 keep 或 preserve_published (filing_upload_publication.py:426-456)
- metadata-only skip 路径: stage company meta → commit batch → return skip result with company_meta_commit_outcome (filing_upload_publication.py:781-799)

**preserve_published 意图**: 当 company decision 为 "stage" 且 `merge_mode == "preserve_published"` 时，commit-time 合并保留 published 非身份事实，只更新 identity (company_meta_contract.py:221-228)。

---

### 维度 7: Concurrency/Cancellation/Kill/Recovery

**走读结论**: 多层取消 checkpoint + journal-based recovery + orphan cleanup。

**直接证据**:
- `execute_prepared_filing_publication` 有两处取消 checkpoint: batch acquire 后 (filing_upload_publication.py:697) 和 arbitration 后 (filing_upload_publication.py:745)
- `_store_upload_assets` 在每个文件写入前检查取消 (docling_upload_service.py:721)，source document 创建前后各检查一次 (docling_upload_service.py:759, 775)
- `commit_prepared_upload_batch` 在 publish 完成后、commit 前做最终取消检查 (docling_upload_service.py:1417)
- journal 记录 phase: started → backed_up_target → swapped_target → committed → rolled_back (fs_storage_infra.py:103-120)
- `recover_orphan_batches` 根据 journal phase 决定恢复策略 (fs_storage_infra.py:742-755)
- `_rollback_precommit_batch` 在 commit 失败时恢复 (fs_storage_infra.py:709-716)
- `KeyboardInterrupt` 和 `SystemExit` 在 rollback 时原样传播 (filing_upload_publication.py:557-558)

**kill 恢复**: 进程 kill 后，`recover_orphan_batches` 扫描 orphan batch 目录，根据 journal phase 决定 restore 或 delete。recovery lock 防止并发 recovery (fs_storage_infra.py:635-638)。

---

## Open Questions

无。

## Residual Risk

1. **`UploadOperationResult` 的 `file_events` 字段为 mutable list**: 虽然 `frozen=True` 阻止字段重赋值，但 list 本身可变。当前实践中 list 在构造后不被修改，但缺少 `tuple` 类型约束来强制不可变。属于设计层面的 maintainability 风险，不影响当前 correctness。

2. **`RESOLVER_VERSION` 为模块级常量**: 若 resolver 逻辑变更但未 bump 版本号，stale metadata 可能被误判为 fresh。当前版本 `market_resolver_v1.0.0` 正确，但需在 resolver 逻辑变更时同步更新。

3. **测试覆盖**: 当前测试覆盖了 arbitration closed table、concurrent update、alias conflict、skip/preserve、cancel/rollback 等关键路径。`test_filing_upload_publication.py` 有 23+ 个测试函数，`test_company_meta_contract.py` 有 13+ 个测试函数。未发现明显 test gap。

## Covered Areas

| 维度 | 覆盖状态 | 关键文件 |
|------|----------|----------|
| Authoritative company identity decision | covered | upload_company_meta.py, company_meta_contract.py |
| Publication-lock reread | covered | _fs_storage_infra.py (commit-time identity guard) |
| Atomic publish/rollback | covered | filing_upload_publication.py, docling_upload_service.py |
| Alias merge/collision | covered | company_meta_contract.py, _fs_storage_infra.py |
| Fresh/stale metadata | covered | upload_company_meta.py, company_meta_contract.py |
| Skip/preserve-intent | covered | filing_upload_publication.py, docling_upload_service.py |
| Concurrency/cancellation/kill/recovery | covered | filing_upload_publication.py, _fs_storage_infra.py |

## Not Covered

- CLI 投影层（按 scope 排除）
- `dayu/fins/pipelines/sec_upload_workflow.py` 和 `cn_pipeline.py` 的 pipeline 装配细节（未深入，但与本专项 scope 的 state/owner 语义无直接关联）
- `dayu/cli/output.py` 的 warning 文案投影（按 scope 排除）
