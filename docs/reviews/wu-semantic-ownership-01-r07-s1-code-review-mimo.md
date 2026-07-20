# R07-S1 Adversarial Code Review — AgentMiMo

## Scope

- Mode: current changes (working tree diff from transition HEAD)
- Branch: `phaseflow/host-issues-control`
- Base: `386fef8d7a7ecbd977c455ca86bb8bab875d1a98` (R07-S1 transition HEAD)
- Output file: `docs/reviews/wu-semantic-ownership-01-r07-s1-code-review-mimo.md`
- Included scope: 9 production files + 4 test files (S1 allowlist), plus new `_fs_identity.py`
- Excluded scope: S2/S3, R08+, Issues 142/151/175/177/178, unified authorization, README, design, control
- Parallel review coverage: 4 subagents — identity module, storage infra, remaining cores, test coverage

## 结论: PASS-WITH-FINDINGS

S1 核心设计（descriptor 作为唯一 round-trip truth、opaque identity 到 private key 的确定性映射、R06 4-phase atomicity 保持、fail-closed descriptor 校验、company inventory breaking cutover、private key non-leak）整体健全。发现 5 个 material findings 和 2 个 low-severity observations。

---

## Findings

### R07-S1-MIMO-F01 — 未修复 — 中 — `_cleanup_stale_filing_documents_impl` 中 `startswith("fil_")` 格式假设违反 opaque identity 契约

- **入口/函数**: `FsFilingMaintenanceRepository.cleanup_stale_filing_documents` → `_cleanup_stale_filing_documents_impl`
- **文件(行号)**: `dayu/fins/storage/_fs_maintenance_core.py:616`
- **输入场景**: 任何 filing document 的 external identity 不以 `"fil_"` 开头时
- **实际分支**: line 616 `if not external_document_id.startswith("fil_"): continue` 跳过该 document
- **预期行为**: `_read_identity_descriptor` 在 line 612-614 已验证 descriptor 的 `namespace` 为 `_FILING_IDENTITY_NAMESPACE`，确认该目录是 filing document。后续应直接信任 namespace，不再对 external identity 做格式假设
- **实际行为**: 在 namespace 已验证后，额外对 external identity 做 `startswith("fil_")` 检查。这是一个目录命名惯例（pipeline 中 `document_id = f"fil_{accession_number}"`），不是 opaque identity 契约的一部分。若未来 document_id 格式变化或有非 `fil_` 前缀的 filing，stale cleanup 将静默跳过
- **直接证据**:
  - `sec_download_filing_workflow.py:217`: `document_id = f"fil_{internal_document_id}"` — 当前 pipeline 惯例
  - `sec_rebuild_workflow.py:328`: `document_id[4:] if document_id.startswith("fil_") else document_id` — rebuild 已处理两种格式
  - `_fs_maintenance_core.py:612-616`: `_read_identity_descriptor` 验证 namespace 后，额外 `startswith("fil_")` 检查
- **影响**: 维护性风险。当前 pipeline 全部使用 `fil_` 前缀所以不会触发，但违反了 opaque identity 的核心契约——storage 不应对 external identity 做格式假设。若 document_id 格式演进，stale cleanup 静默失效导致数据积累
- **建议改法和验证点**: 删除 line 616-617 的 `startswith("fil_")` 检查。`_read_identity_descriptor` 已通过 namespace 验证确认是 filing document，无需额外格式过滤。补充测试用非 `fil_` 前缀的 filing document_id（如纯 accession number）验证 stale cleanup 正确执行
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### R07-S1-MIMO-F02 — 未修复 — 中 — `_clear_filing_documents_impl` 和 `_clear_processed_documents_impl` 跳过 descriptor 校验直接删除

- **入口/函数**: `FsFilingMaintenanceRepository.clear_filing_documents` → `_clear_filing_documents_impl`; `FsProcessedDocumentRepository.clear_processed_documents` → `_clear_processed_documents_impl`
- **文件(行号)**: `dayu/fins/storage/_fs_maintenance_core.py:530-538`; `dayu/fins/storage/_fs_processed_core.py:373-381`
- **输入场景**: 批量清理 ticker 下所有 filing/processed 文档时
- **实际分支**: `for child in filings_dir.iterdir(): if child.is_dir(): shutil.rmtree(child)` — 不读取 descriptor，不验证 identity
- **预期行为**: 与 `_cleanup_stale_filing_documents_impl`（line 612-614 读取 descriptor）保持一致，至少验证每个子目录是合法的 identity directory 后再删除
- **实际行为**: 直接遍历并删除所有子目录和文件。若存在非 identity 目录（如手动创建的调试目录、symlink 残留、或 descriptor 损坏的目录），会被静默删除
- **直接证据**:
  - `_fs_maintenance_core.py:534-538`: `for child in filings_dir.iterdir(): if child.is_dir(): shutil.rmtree(child)`
  - `_fs_processed_core.py:377-381`: 同样逻辑
  - 对比 `_fs_maintenance_core.py:612-614`: `_cleanup_stale_filing_documents_impl` 先读 descriptor 再决策
- **影响**: 设计不一致。`clear_*` 是 "清除全部" 操作且在 batch capability 内，blast radius 受控。但与 `_cleanup_stale_filing_documents_impl` 的 descriptor-first 模式不一致，暗示这可能是遗漏而非有意设计
- **建议改法和验证点**: 在 `shutil.rmtree` 前增加 descriptor 校验（至少验证目录是合法 identity directory）。或者在 docstring 中显式说明 "clear all" 的语义是有意跳过 descriptor 校验（需要设计确认）
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### R07-S1-MIMO-F03 — 未修复 — 中 — `_require_external_identity` 不拒绝 null byte、控制字符和纯空白字符串

- **入口/函数**: `_require_external_identity`
- **文件(行号)**: `dayu/fins/storage/_fs_identity.py:38-58`
- **输入场景**: external identity 包含 `\0`、C0/C1 控制字符（`\x01`-`\x1f`、`\x7f`-`\x9f`）、Unicode 控制字符（`​` 零宽空格、`﻿` BOM）、或纯空白字符串（`"  "`、`"\t\n"`）
- **实际分支**: `value == ""` 检查通过（非空），`value.encode("utf-8")` 成功（合法 UTF-8），函数返回原值
- **预期行为**: identity validator 应拒绝语义无效的输入——null byte 会污染 `_derive_storage_key` 的 `\0` 分隔符语义（`namespace\0identity` 中 identity 内嵌 `\0` 导致分隔符歧义）；控制字符在日志/终端中不可见；纯空白字符串语义无意义
- **实际行为**: 仅检查空字符串和 UTF-8 可编码性，允许所有上述输入通过
- **直接证据**:
  - `_fs_identity.py:52-57`: `if value == "": raise ...; value.encode("utf-8")` — 仅两个检查
  - `_fs_identity.py:79-82`: `digest.update(namespace.encode("utf-8")); digest.update(b"\0"); digest.update(identity.encode("utf-8"))` — `\0` 分隔符设计
- **影响**: 防御纵深不足。当前所有调用方传入的 ticker（如 `"AAPL"`、`"600519"`）和 document_id（如 `"fil_0000320193-24-000123"`）都是正常业务值，不会触发此问题。但作为 storage identity boundary 的唯一 validator，应拒绝语义无效输入
- **建议改法和验证点**: 增加 `value.strip() == ""` 检查拒绝纯空白；增加 `\0` 检查拒绝 null byte；可选增加 C0/C1 控制字符检查。补充参数化测试覆盖 `"  "`、`"a\0b"`、`"\x01"` 等边界值
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### R07-S1-MIMO-F04 — 未修复 — 低 — `_fs_identity.py` 无直接单元测试

- **入口/函数**: `_fs_identity.py` 模块级（`_derive_storage_key`、`_require_external_identity`、`_ensure_identity_directory`、`_read_identity_descriptor`、`_identity_directory_for_read`、`_list_external_identities`）
- **文件(行号)**: `dayu/fins/storage/_fs_identity.py`（全文件 313 行）
- **输入场景**: 所有 `_fs_identity.py` 导出函数的直接调用
- **实际分支**: 所有测试通过 `_fs_storage_infra.py` 和更高层 repository 间接调用
- **预期行为**: 项目约束要求单文件测试覆盖率 >= 80%。`_fs_identity.py` 作为 S1 的核心新增模块（sole owner of opaque-to-private mapping），应有直接单元测试覆盖其边界行为
- **实际行为**: `grep -rn "_fs_identity\|_derive_storage_key\|_require_external_identity\|_ensure_identity_directory\|_read_identity_descriptor\|_list_external_identities" tests/` 返回零结果。所有行为仅通过集成测试间接覆盖
- **直接证据**: grep 结果为空；Controller validation 报告的 82.52%-96.08% 覆盖率是按 production 文件统计，`_fs_identity.py` 的覆盖率来自集成测试的间接调用路径
- **影响**: F01-F03 中发现的校验缺口（null byte、控制字符、纯空白）没有直接测试守护。若集成测试的调用方恰好不传入这些边界值，回归不会被发现
- **建议改法和验证点**: 为 `_fs_identity.py` 创建 `tests/fins/test_fs_identity.py`，直接测试：(1) `_derive_storage_key` 的确定性和碰撞隔离；(2) `_require_external_identity` 的拒绝边界；(3) `_ensure_identity_directory` 的 descriptor-first 创建和失败清理；(4) `_read_identity_descriptor` 的双向校验；(5) `_list_external_identities` 的 descriptor-only 枚举
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### R07-S1-MIMO-F05 — 未修复 — 低 — `_fs_storage_infra.py` 导入未使用的 `SourceDocumentRevision`

- **入口/函数**: 模块级 import
- **文件(行号)**: `dayu/fins/storage/_fs_storage_infra.py:29`
- **输入场景**: N/A
- **实际分支**: `SourceDocumentRevision` 被导入但未在 `_fs_storage_infra.py` 中使用。实际使用在 `_fs_source_document_core.py` 的 `_build_source_revision`
- **预期行为**: 不导入未使用的符号
- **实际行为**: `from dayu.fins.domain.document_models import (..., SourceDocumentRevision, ...)` 在 `_fs_storage_infra.py` 中无对应使用
- **直接证据**: grep 确认 `_fs_storage_infra.py` 中无 `SourceDocumentRevision` 使用（仅在 `_fs_source_document_core.py:64` 使用）
- **影响**: 无功能影响。增加不必要的模块间耦合
- **建议改法和验证点**: 从 `_fs_storage_infra.py` 的 import 中删除 `SourceDocumentRevision`
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/低/严重）**: 低

---

## Open Questions

- **`_clear_*` 的设计意图**: `_clear_filing_documents_impl` 和 `_clear_processed_documents_impl` 跳过 descriptor 校验是有意的 "clear all" 语义，还是实现遗漏？需要设计确认。若有意为之，应在 docstring 中显式说明

## Residual Risk

1. **Unicode hierarchy separators**: `_normalize_path_component`（`_fs_storage_utils.py`）的路径分隔符检测基于 `os.sep`、`"/"` 和 `"\\"`，未覆盖 Unicode 行分隔符（U+2028、U+2029、U+0085）。Python 的 `pathlib` 在大多数平台上不将这些字符视为路径分隔符，但若未来平台行为变化，可能成为 containment bypass
2. **`_ensure_identity_directory` TOCTOU 窗口**: line 155 的存在性检查与 line 162 的 `mkdir` 之间存在理论性 TOCTOU 窗口。需要对工作区 root 有写权限才能利用，实际风险极低
3. **`_list_external_identities` O(n) 重复检测**: line 309 `if identity in identities` 对 list 做线性查找。当前 ticker/document 数量级（数百）不构成性能问题，但若规模增长应改用 set
4. **Test fixture 使用 `fil_` 前缀 document_id**: `test_stale_filing_cleanup_uses_descriptor_external_id_in_opaque_layout` 使用 `"fil_保留/2025\\Q1"` 和 `"fil_过期/2024\\Q4"` 作为 document_id，恰好满足 `startswith("fil_")` 检查。未测试非 `fil_` 前缀的 filing document_id（如纯 SEC accession number）
5. **`_read_identity_descriptor` 中 `raw_namespace` 未做 `isinstance(str)` 检查**: 若 descriptor JSON 中 namespace 为 `null` 或整数，`raw_namespace != namespace` 在 Python 中返回 True（不同类型比较），不会抛异常。当前所有 descriptor 由 `_ensure_identity_directory` 写入，namespace 来自 `Literal` 类型常量，实际不会触发

## 覆盖确认

| 检查维度 | 结论 |
|---------|------|
| descriptor 是否为唯一 round-trip truth | ✅ 所有 point lookup/listing/recovery 通过 descriptor 校验，无目录名推断 |
| expected_storage_key 所有 caller 绑定真实 target/backup locator | ✅ 逐调用方验证通过 |
| R06 4-phase/锁顺序/primary error/old-new atomicity | ✅ 保持完整 |
| source/material/processed/rejected/blob descriptor 双向 fail-closed | ✅ 缺失/损坏/不匹配均 fail-closed |
| Unicode/separator/drive/dot/dotdot opaque id containment | ✅ 核心路径安全；Unicode hierarchy separator 为 residual |
| company alias 与 storage identity 分权 | ✅ alias resolution 为只读，不修改 storage path |
| CompanyMetaInventoryEntry breaking cutover 无兼容 | ✅ `directory_name` 已删除，lock-only 返回 `ticker=None` |
| 115-hit inventory 与 _remove_manifest_items | ✅ `_normalize_document_id`/`_list_directory_names`/`_published_ticker_directory_names` 零残留 |
| 无 S2/S3/R08+/Issue 142/151/175/177/178/统一 authorization 偷带 | ✅ 仅 S1 allowlist 文件变更 |
