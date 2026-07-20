# WU-SEMANTIC-OWNERSHIP-01 / R06-S2 第一路 Cumulative Code Review（AgentMiMo）

## Scope

- Mode: current changes
- Branch: `phaseflow/host-issues-control`
- Base: `d048adf7ec1135aaf575384432ebf1137f8a34f2`（Controller transition base）
- Output file: `docs/reviews/wu-semantic-ownership-01-r06-s2-code-review-mimo.md`
- Included scope: 20 files changed（15 production + 4 tests + 1 control），累计 S1+S2 diff
- Excluded scope: S3 producer propagation files、R07+、Issue 142/151/175/177/178
- Parallel review coverage: 3 subagents（storage infra validator、source/blob/protocols、test coverage）

### Review 基础文档

已完整读取：
- `AGENTS.md`（项目约束）
- `docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md`（9 topic 最终裁决）
- `docs/host/wu-semantic-ownership-01-r06-fins-transaction-complete-publication-plan.md`（R06 plan）
- `docs/reviews/wu-semantic-ownership-01-r06-s2-implementation-codex.md`（S2 implementation artifact）
- `docs/reviews/wu-semantic-ownership-01-r06-s2-controller-validation.md`（Controller validation PASS）
- S1 初始 review + re-review + controller adjudication（CR-F01..03 全部 CLOSED）

### S1 accepted findings 状态

- **CR-F01**（maintenance public read → private unguarded helper）：**CLOSED**，未被 S2 回退。
- **CR-F02**（processed meta docstring 删除虚构 fallback）：**CLOSED**，未被 S2 回退。
- **CR-F03**（mark_processed_reprocess_required 统一 `-> None`）：**CLOSED**，未被 S2 回退。

## Findings

未发现实质性问题。

以下为 subagent 审查中发现但经主 reviewer 裁决后不属于 S2 defect 的项目，记录为 observations。

### O-01 — commit_batch publication guard release 的 unreachable `else` 分支

- **入口/函数**: `commit_batch` → inner finally → publication guard release
- **文件(行号)**: `_fs_storage_infra.py:379-380`
- **输入场景**: 不可达路径
- **实际分支**: `else: commit_error = release_error`
- **预期行为**: 此分支应覆盖 `commit_error is None` 且 `state.phase != _PHASE_COMMITTED` 的组合
- **实际行为**: inner try 的最后一步是 `_write_batch_journal(state, _PHASE_COMMITTED)`（line 354）。成功时 `state.phase` 必为 `_PHASE_COMMITTED` 且 `commit_error` 为 `None`；失败时 `commit_error` 已被设置。不存在"inner try 正常退出但 phase 不是 COMMITTED"的路径
- **直接证据**: line 345-354 的 try body 顺序、line 355-358 的 except 设置 `commit_error`
- **影响**: 无——dead code，不影响运行时行为。可作为防御性代码保留以应对未来重构
- **严重程度（低/中/高/严重）**: 信息级（非 defect）

### O-02 — `_prepare_complete_source_meta` 对缺失 `ingest_complete` 默认 `True`

- **入口/函数**: `_prepare_complete_source_meta`
- **文件(行号)**: `_fs_source_document_core.py:1447`
- **输入场景**: producer meta dict 不含 `ingest_complete` 字段
- **实际分支**: `meta.get("ingest_complete", True)` → 默认 `True` → 通过 `is not True` 检查
- **预期行为**: 按 plan §5.1，"producer 不再写 false"，但未明确要求 producer 必须显式写 `True`
- **实际行为**: 缺失字段默认为 `True`，语义上等同于 producer 声明"已完成"。commit validator 通过 `SourceDocumentProvenance.from_meta` 再次确认 `ingest_complete=True`
- **直接证据**: line 1447 `meta.get("ingest_complete", True)`、line 1454 `normalized["ingest_complete"] = True`
- **影响**: 无——最终值必为 `True`，双层校验（写边界 + commit validator）均生效。若 producer 遗漏该字段，storage owner 的默认值语义正确
- **严重程度（低/中/高/严重）**: 信息级（非 defect，owner contract 内的合理默认）

### O-03 — S3 producer 仍调用 `stage_source_document` / 设置 `ingest_complete=False`

- **入口/函数**: `sec_download_source_upsert.py:126`、`docling_upload_service.py:565` 及对应测试
- **文件(行号)**: S3 allowlist 文件
- **输入场景**: S3 producer 执行路径
- **预期行为**: S3 propagation 将这些调用迁移到 `create_source_document`/`update_source_document` 并删除 `ingest_complete=False`
- **实际行为**: 当前 working tree 中这些调用仍存在，是 S2→S3 的已知中间态 residual
- **直接证据**: `grep -rn 'stage_source_document' dayu/fins/pipelines/ tests/fins/` 命中 S3 文件
- **影响**: 无——108 full pyright errors 精确归属 S3 propagation（implementation codex §9.2），不在 S2 owner 修复边界
- **严重程度（低/中/高/严重）**: 信息级（accepted S3 residual，非 S2 defect）

### O-04 — validator 6 个独立失败分支未被 22-case grid 覆盖

- **入口/函数**: `_validate_complete_source_kind_tree`、`_validate_complete_source_files`
- **文件(行号)**: `_fs_storage_infra.py:493-494`（symlink child）、`:507-508`（非目录条目）、`:682-683`（file entry 非 Mapping）、`:684-686`（file.name 非 str）、`:706-708`（size 非 int）、`:712-714`（sha256 非 str）
- **输入场景**: malformed staged tree
- **实际行为**: 这 6 个分支在代码中存在但未被测试直接覆盖
- **直接证据**: 22-case grid 的 `_corrupt_staged_complete_source` 不注入这 6 种 corruption
- **影响**: 测试覆盖 gap，非 production defect。validator 代码逻辑正确，只是输入路径未被测试证明
- **严重程度（低/中/高/严重）**: 信息级（test gap，可在 S2/S3 间补充）

### O-05 — 测试通过 `_active_batches` private 字段获取物理路径

- **入口/函数**: `_corrupt_staged_complete_source`
- **文件(行号)**: `test_fins_storage_provider.py:3354-3356`
- **输入场景**: failure grid fixture 构造
- **实际行为**: `core._active_batches` 和 `_ActiveBatchState` 是 private API，测试直接访问以获取 staging ticker dir 路径
- **直接证据**: `states = tuple(core._active_batches.values())`
- **影响**: 测试与 private 实现耦合，内部重构可能在无行为漂移时 break 测试
- **严重程度（低/中/高/严重）**: 信息级（tech debt，S1 O-03/O-04 同类模式的延续）

## Open Questions

无。

## Residual Risk

1. **S3 propagation residual**: 108 full pyright errors、`stage_source_document` 调用残留、`ingest_complete=False` 设置残留均精确归属 accepted S3 producer propagation，不在 S2 边界。
2. **README 旧叙述**: `dayu/fins/README.md` 和 `tests/README.md` 仍描述 pre-cutover acknowledgement，有意保留到 S3/final cumulative tree。
3. **validator 6 个未覆盖分支**: 代码逻辑正确但测试未直接覆盖，可在后续补充。
4. **R07 snapshot/revision**: 跨多个 repository call 或长生命周期 processor 的同版本 snapshot 仍由 R07 独占，不削弱 R06 的一次 published read/open 完整性。
5. **LocalFileSource.delayed opener**: `materialize()` 的 8 个 production 文件/9 个调用点在取得裸 `Path` 后的延迟读取无 snapshot consistency，是 R07 显式 residual。

## Verdict

**PASS / 0 findings / 0 blockers**

### S1 accepted findings 状态

- CR-F01: **CLOSED**（未回退）
- CR-F02: **CLOSED**（未回退）
- CR-F03: **CLOSED**（未回退）

### 逐维度裁决

| 审查维度 | 结果 |
|---------|------|
| 唯一显式 batch authority | PASS：`_resolve_active_batch` 通过 registry + ticker + lifecycle + canonical token 校验，无 ContextVar/task/thread/ambient authority |
| blob-first / final-source 单发布 | PASS：SourceHandle blob-first 不要求 meta，ProcessedHandle 仍要求；final source 强制 `ingest_complete=True`；`stage_source_document` 从 protocol/wrapper/core 删除 |
| full staged-tree validator 双向 contract | PASS：validator 固定遍历完整 staged ticker tree，source↔manifest 双向 identity/provenance/completion exact projection，22-case grid + 独立测试覆盖 |
| commit failure token 消费 / old 保留 | PASS：validator failure → precommit rollback → token 消费；post-commit failure → capability 终态消费；old published 不变 |
| publication guard / recovery / containment 不回退 | PASS：writer mutex 与 publication guard 严格分离；recovery 先 ticker lock 后 publication guard；containment/symlink 检查完整 |
| loose parsing / fallback / 下游补偿 | PASS：无 hasattr/getattr、无 compat shim、无 consumer 反推 |
| S3/R07/Issue 175/177 越界 | PASS：108 pyright errors 精确归属 S3；未实施 R07 selector/snapshot；未触碰 Issue 175/177 |
| 测试覆盖 owner contract | PASS（有 observations）：核心 contract 全覆盖；6 个 validator 分支未直接覆盖（O-04）；private API 耦合（O-05） |
