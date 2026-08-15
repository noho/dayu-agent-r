# Code Review

## Scope

- Mode: current changes
- Branch: `codex/upload-filing-oracle`
- Base: `8033a56e`
- Output file: `docs/reviews/code-review-slice4-mimo-20260815.md`
- Included scope:
  - `README.md`（unstaged）
  - `dayu/fins/README.md`（unstaged）
  - `tests/README.md`（unstaged）
  - `docs/gateflow/uf-fix06-slice4-implementation-20260815.md`（untracked）
- Excluded scope: 生产代码、测试、oracle/scenario、Host/Engine design、frozen evidence
- Parallel review coverage: 无

## Review baseline 与证据方法

reviewer 读取了以下直接证据：

1. 三个 README 的 `git diff 8033a56e` 与完整文件的相关区段。
2. `docs/gateflow/uf-fix06-slice4-implementation-20260815.md` 全文。
3. `docs/gateflow/uf-fix06-converter-capability-owner-plan-20260815.md` 全文（作为 contract 对照基线）。
4. 生产代码：`dayu/fins/upload_format_contract.py`、`dayu/documents/docling_runtime.py`（converter capability 定义）、`dayu/fins/pipelines/docling_upload_service.py`（`_prepare_upload_selection`、`_build_pending_assets`、`_PreparedAssetMutation`）、`dayu/fins/upload_batch.py`（`accepts_primary` 消费点）、`dayu/cli/arg_parsing.py`（`FINS_UPLOAD_FORMAT_TEXT` 消费点）、`dayu/fins/tools/upload_tools.py`（`FINS_UPLOAD_FORMAT_TEXT` 消费点）、`dayu/fins/upload_failure.py`（`USAGE/UNSUPPORTED_UPLOAD_FORMAT` 映射）、`dayu/fins/ingestion_runtime.py`（`file_selection` 字段）。
5. 静态审计：`rg -n 'FINS_UPLOAD_FILE_SUFFIXES|SUPPORTED_UPLOAD_SUFFIXES'`、`rg -n '_pick_primary_docling_file'`、`rg -n 'hasattr|getattr'`。

## Findings

### 1-未修复-低-根 README 缺少 `.json` 限定文案，与 help/tool schema 不完全一致

- **入口/函数**: `README.md` 新增 `--files` 段落 vs `project_fins_upload_format_text()` 产出的 `filing_files`
- **文件(行号)**: `README.md:317-321` vs `dayu/fins/upload_format_contract.py:561-566`
- **输入场景**: 最终用户同时阅读根 README 和 `--help`/tool schema
- **实际分支**: 根 README 只写 `.xml 仅是 XBRL XML candidate`，未提及 `.json 仅是 Docling JSON candidate`
- **预期行为**: 帮助文本 `.xml 仅是 XBRL XML 候选，不代表任意 XML；后缀通过只表示具备转换资格，不保证文件内容转换成功。.json 仅是 Docling JSON 候选，不代表任意 JSON 内容可转换。` 中 `.xml` 和 `.json` 的限定文案应同步出现在根 README
- **实际行为**: 根 README 只有 `.xml` 限定文案；`.json` 被隐含在"当前支持的格式清单以 `--help` 为准"中
- **直接证据**: `README.md:319` 只写 `.xml 只是 XBRL XML candidate`；`upload_format_contract.py:565` 同时包含 `.xml 仅是 XBRL XML 候选` 和 `.json 仅是 Docling JSON 候选`
- **影响**: 用户可能误认为 `.json` 文件内容必然可转换；但因 README 同时声明以 `--help` 为准，实际误导程度低
- **建议改法和验证点**: 在根 README `.xml` 限定文案后追加 `.json 仅是 Docling JSON candidate` 一句；或合并为 `.xml/.json 分别仅是 XBRL XML/Docling JSON candidate`。验证：diff 与 `project_fins_upload_format_text().filing_files` 语义对齐
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 2-未修复-低-implementation artifact 验证声明为自报告，reviewer 无法独立复核

- **入口/函数**: `docs/gateflow/uf-fix06-slice4-implementation-20260815.md` §Validation
- **文件(行号)**: `docs/gateflow/uf-fix06-slice4-implementation-20260815.md:76-159`
- **输入场景**: code reviewer 试图复核 implementation artifact 的验证结论
- **实际分支**: artifact 声明 `1338 passed, 1 skipped`、`0 errors, 0 warnings`、`README/help/tool schema semantic comparison: PASS`、静态审计 `rg` 无结果
- **预期行为**: 验证声明应可由 reviewer 通过运行相同命令独立复核
- **实际行为**: 该 artifact 是 implementation agent 的自报告；reviewer 已通过代码阅读确认关键 contract（converter capability、FINS_UPLOAD_FORMAT_TEXT 同源、`_prepare_upload_selection` filing/material 分流、`accepts_primary` 消费、`hasattr/getattr` 扫描无结果）与声明一致，但无法独立复核具体测试数量、coverage 数字和 pyright 结果
- **直接证据**: artifact 全文无外部 CI 或第三方验证引用；reviewer 读取的生产代码与声明一致，但具体数字依赖 implementation 环境
- **影响**: 不影响 reviewer 对 contract 一致性的判断；但具体数字（1338 passed、92% aggregate coverage）应由后续 PF 或 CI 独立验证
- **建议改法和验证点**: 无需修改 artifact；后续 UF-PF06/UF-PF12 运行时复核即可
- **修复风险（低/中/高）**: 无
- **严重程度（低/中/高/严重）**: 低

## 已验证的关键 contract

以下 contract 已通过代码阅读独立确认：

| Contract | 代码证据 |
|---|---|
| converter capability 唯一 owner 是 `dayu.documents.docling_runtime` | `docling_runtime.py:220-230`：`DOCLING_CONVERTER_CAPABILITY` 冻结 9 format id、13 suffix |
| Fins role overlay 唯一 owner 是 `dayu.fins.upload_format_contract` | `upload_format_contract.py:307-310`：`FINS_UPLOAD_FORMAT_CAPABILITY` 持有 converter capability + companion-only `{.xsd}` |
| CLI help 与 tool schema 消费同一 `FINS_UPLOAD_FORMAT_TEXT` | `arg_parsing.py:14,924` 和 `upload_tools.py:34,238` 均从 `upload_format_contract` 导入 |
| batch scanner 消费 `FINS_UPLOAD_FORMAT_CAPABILITY.accepts_primary` | `upload_batch.py:20,418` |
| filing 只转换 primary | `docling_upload_service.py:1020`：`converter_inputs = (selection.require_primary(),)` |
| material 全部转换 | `docling_upload_service.py:1030`：`converter_inputs = selection.files` |
| `primary_document` 由首文件转换结果显式产生 | `docling_upload_service.py:805-806` |
| `_pick_primary_docling_file` 已删除 | `rg` 无结果 |
| `FINS_UPLOAD_FILE_SUFFIXES` / `SUPPORTED_UPLOAD_SUFFIXES` 已删除 | `rg` 无结果 |
| `hasattr/getattr` 不在关键 upload 模块中 | `grep` 无结果（fins 包中的 `getattr` 仅在 processors 中操作第三方对象） |
| `USAGE/UNSUPPORTED_UPLOAD_FORMAT` 存在 | `upload_failure.py:31,40,175-186,226-227` |
| `file_selection: FinsUploadFilingFiles` 是必需非 Optional 字段 | `ingestion_runtime.py:763` |
| Service 双向 source_kind/selection 类型校验 | `docling_upload_service.py:1016-1032` |
| 保护文件未改 | `git diff --exit-code -- docs/cli_ci_oracles.json docs/cli_ci_scenarios.json docs/host/design.md docs/engine/design.md`：无变更 |

## Open Questions

- 无。

## Residual Risk

| Residual | Classification | Owner / destination |
|---|---|---|
| 未运行真实全格式 fixture 矩阵 | assigned to later work unit | UF-PF06 |
| 未运行全量 mandatory CLI scenario | assigned to later work unit | UF-PF12 |
| batch 不会自动将同目录 `.xsd` 与 filing primary 关联 | assigned to later work unit | 后续 batch association / UF-FIX07 类 work unit |
| tests README 中 14 个 focused test 文件的断言内容无法从代码阅读独立验证 | covered by later PF | UF-PF06/UF-PF12 |
| implementation artifact 中 coverage 数字为自报告 | covered by later PF | UF-PF06/UF-PF12 |

## Conclusion

**PASS**（附 1 个低严重程度 finding）。

三个 README 的文档更新与生产代码 contract 一致：converter capability、Fins role overlay、CLI help/tool schema 同源、filing 只转换 primary、material 全转换、原子发布、计数语义、取消语义均与代码实现对齐。旧 allow-list 和 `_pick_primary_docling_file` 已完全清除。保护文件未被修改。implementation artifact 的验证声明与 reviewer 代码阅读结论一致。

唯一实质性 finding 是根 README 缺少 `.json` 限定文案（与 help/tool schema 不完全一致），严重程度低，修复成本极低。
