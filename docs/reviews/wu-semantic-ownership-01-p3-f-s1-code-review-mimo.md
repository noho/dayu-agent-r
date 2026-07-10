# Code Review

## Scope

- Mode: current changes
- Branch: `phaseflow/host-issues-control`
- Base: `main`
- Output file: `docs/reviews/wu-semantic-ownership-01-p3-f-s1-code-review-mimo.md`
- Included scope: WU-SEMANTIC-OWNERSHIP-01 P3-F S1 未提交改动（17 files, +633/-24）
- Excluded scope: `docs/cli_ci.md`, `docs/cli_ci_oracles.json`, `docs/cli_ci_scenarios.json`, `docs/reviews/code-review-20260710-135625.md`, `docs/reviews/code-review-20260710-141049.md`
- Parallel review coverage: 无

## Findings

### 001-未修复-中-`_build_citation` 对同一 meta.json 做两次冗余文件 I/O

- **入口/函数**: `FinsReadRuntime._build_citation(...)` (`dayu/fins/tools/read_runtime.py:1707-1709`)
- **文件(行号)**: `dayu/fins/tools/read_runtime.py:1708-1709`
- **输入场景**: 任何 citation 构建路径（9 个调用点）
- **实际分支**: 每次 `_build_citation` 先调 `get_source_meta(...)` 读 meta.json，再调 `get_source_document_provenance(...)`——后者内部也调 `get_source_meta(...)` 读同一个文件（`_fs_source_document_core.py:360`）
- **预期行为**: 每次 citation 构建只对同一 meta.json 做一次文件 I/O
- **实际行为**: 同一 `meta.json` 被读取两次；`get_source_document_provenance` 内部已调用 `get_source_meta` 返回原始 meta，外层又独立调用一次
- **直接证据**: `_build_citation` line 1708 (`meta = self._source_repository.get_source_meta(...)`) 和 line 1709 (`provenance = self._source_repository.get_source_document_provenance(...)`)；`get_source_document_provenance` 实现 line 360 (`meta = self.get_source_meta(...)`)
- **影响**: 每次 citation 构建多一次文件 I/O；在批量 list/search 场景下放大为 O(n) 冗余读取。correctness 不受影响。
- **建议改法和验证点**: 让 `get_source_document_provenance` 同时返回 `(SourceDocumentProvenance, DocumentMeta)` 或在 `_build_citation` 中只调 `get_source_document_provenance` 后从同一 meta 剩余字段提取 citation business fields。验证：修改后 `_build_citation` 只有一次 source meta 读取；现有测试全部通过。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### 002-未修复-低-`_build_citation` 对 staging `ingest_complete=False` 文档无防护

- **入口/函数**: `FinsReadRuntime._build_citation(...)` (`dayu/fins/tools/read_runtime.py:1707-1709`)
- **文件(行号)**: `dayu/fins/tools/read_runtime.py:1707-1709`
- **输入场景**: 如果 S2 staging 写入了 `ingest_complete=False` 的 source meta，且上游 list/search/read 工具未过滤该 document_id
- **实际分支**: `_resolve_source_kind` 只检查 source handle 是否存在（`get_source_handle`），不检查 `ingest_complete`；staging 文件和完成文件在同一路径
- **预期行为**: staging 文档不应产出 citation（plan 明确要求 "staging source documents are explicitly excluded from read/list tools"）
- **实际行为**: 当前 `_build_citation` 不检查 `provenance.ingest_complete`；如果上游未过滤，staging 文档会产出完整 citation
- **直接证据**: `_resolve_source_kind` line 2079-2093 只做 `get_source_handle` 存在性检查；`_build_citation` line 1709-1713 不检查 `provenance.ingest_complete`
- **影响**: S1 当前无实际风险（S1 不写 staging 文档到生产路径）。S2 staging 上线后，若上游过滤遗漏，staging 文档会被当作完成文档产出 citation。
- **建议改法和验证点**: 在 `_build_citation` 中增加 `if not provenance.ingest_complete: raise FileNotFoundError(...)` 守卫。验证：构造 `ingest_complete=False` 的 source meta，调用 `_build_citation` 应抛出 `FileNotFoundError`。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 003-未修复-低-测试未覆盖 staging 文档在 `_build_citation` 中的行为

- **入口/函数**: `test_read_runtime_citation_projects_provider_owned_source_types` (`tests/fins/test_fins_storage_provider.py`)
- **文件(行号)**: `tests/fins/test_fins_storage_provider.py` - 新增测试
- **输入场景**: `_build_read_runtime_with_provenance_documents` 构造的所有文档均为 `ingest_complete=True`
- **实际分支**: 测试只覆盖完成态文档的 citation 投影
- **预期行为**: plan 要求 "read runtime excludes staging `ingest_complete=False`"；测试应证明该行为
- **实际行为**: 无测试构造 `ingest_complete=False` 文档并验证 `_build_citation` 拒绝或上游过滤
- **直接证据**: `_create_source_document_for_provenance` helper 固定设置 `ingest_complete=True`
- **影响**: S2 上线后缺乏回归保护；当前 S1 无 correctness 风险。
- **建议改法和验证点**: 增加一个测试：构造 `ingest_complete=False` 的 source document，验证 `_build_citation` 或上游调用拒绝产出 citation。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 004-未修复-低-`_staging_stable_fields_match` 跳过 `None` 值字段比较

- **入口/函数**: `_staging_stable_fields_match(...)` (`dayu/fins/storage/_fs_source_document_core.py:1022`)
- **文件(行号)**: `dayu/fins/storage/_fs_source_document_core.py:1051-1054`
- **输入场景**: 重复 staging 请求中某个 stable field 在 req.meta 中为 `None`，但 existing meta 中有不同值
- **实际分支**: `if requested_value is None: continue` 跳过比较
- **预期行为**: plan 规定 "repeated call when existing meta has `ingest_complete=False`: return the same SourceHandle idempotently only if stable request fields match"
- **实际行为**: 请求中 `None` 值的 stable field 不参与匹配检查；如果 existing meta 中该字段有非空值但请求省略，仍视为匹配
- **直接证据**: line 1051 `if requested_value is None: continue`
- **影响**: 当前 S1 skeleton 不写 staging 文档，无实际影响。S2 上线后，如果调用方在重复 staging 时省略了之前写入的 stable field（如 `source_fingerprint`），不会触发冲突检测。
- **建议改法和验证点**: S2 评估是否需要对已知必需 stable field 做双向匹配（existing 非空 + request 也非空但不同 = 冲突）。当前 S1 skeleton 的宽松匹配对 S1 scope 是可接受的。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Open Questions

- 无。

## Residual Risk

- **覆盖率未测量**: pytest-cov 在本地因 numpy/pandas import 问题无法收集覆盖率。所有 76 个测试和 pyright 均通过，但单文件覆盖率数据缺失。
- **S2 接口就绪**: S1 skeleton 的 `stage_source_document` 和 `_staging_stable_fields_match` 为 S2 提供了协议签名和基本冲突检测，但 S2 需要将其接入 blob 写入守卫和 SEC/upload 工作流编排，可能需要调整实现细节。
- **fixture 迁移**: 已迁移的 `tests/fins/fixtures/aapl_xbrl/fil_0000320193-24-000123/meta.json` 增加了 `source_provider: "sec_edgar"`；其余已完成态 fixture 通过 `_build_fins_workspace` 和 `_build_fins_financial_html_workspace` helper 在测试中动态构造，均已包含 `source_provider`。
