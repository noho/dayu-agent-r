# UF-FIX06 Slice 3 implementation

## Gate 元数据

- Work unit：`UF-FIX06 converter-capability-owner`
- Slice：3（让 Service 与 workflows 消费 typed roles）
- Gate：implementation fix
- 日期：2026-08-15
- 基线：`affa665b0592aec54564d31b0cfeb4055dd7bd8a`
- 分支：`codex/upload-filing-oracle`
- 状态：`CODE FIX COMPLETE / RE-REVIEW PENDING`
- 下一入口：Slice 3 code re-review
- Commit：未创建；用户明确禁止 commit
- Artifact：`docs/gateflow/uf-fix06-slice3-implementation-20260815.md`
- Fix artifact：`docs/gateflow/uf-fix06-slice3-code-fix-20260815.md`

## Scope 与 owner 决策

- 严格只修改 Slice 3 allowed production/test files，并新增 implementation/fix artifacts。
- `dayu.fins.upload_format_contract` 继续唯一产生 filing/material typed selection；本 slice 不复制 suffix 规则。
- `DoclingUploadService` 只消费 closed typed union，拥有 original/converter preparation 与明确
  `primary_document`；storage publication owner、原子 batch、取消和 rollback 协议保持不变。
- `dayu.fins.upload_failure` 唯一投影格式异常为 public workflow failure；SEC/CN/HK workflow 只消费该投影。
- 未修改 README、registry、oracle/scenario、design document 或冻结 evidence；未运行 UF-PF06/UF-PF12。

## 实现结果

1. `DoclingUploadService.prepare_upload` 将 raw `files` 精确替换为
   `FinsUploadFilingFiles | FinsUploadMaterialFiles`，先校验 selection concrete type 与
   `SourceKind`，再双向校验 action/emptiness。所有非法组合在 exists/read、converter 与 batch
   publication 前以 `ValueError` 拒绝。
2. 删除 `SUPPORTED_UPLOAD_SUFFIXES` 与 `_pick_primary_docling_file`。Service 仍校验 exists/regular，
   并先读取全部 originals；filing 只把 primary 送入 converter，material 把全部 selection 逐项送入。
3. prepared asset mutation 显式携带第一次实际转换直接产生的 `primary_document`，store 路径不再从
   stored entry 名称或顺序反推。filing companions 只产生 source=`original` 的 `file_uploaded`，
   不产生 `conversion_started` 或 Docling 派生资产。
4. SEC 与 CN/HK filing workflow 原样传递 fresh validation 的非 Optional `file_selection`。material
   workflow 在既有 `try` 内、published-state read/company staging/file read/converter/batch 前构造
   typed selection；显式 delete 使用 material typed empty。
5. failure owner 新增 closed `USAGE/UNSUPPORTED_UPLOAD_FORMAT`，三个 role-specific
   `FinsUploadFormatError` 统一投影为固定 bounded/path-free message、retry hint 与 owner 产生的
   safe basename。JSON parser 使用 code-to-kind 完整映射，未知 code 与 kind/code 错配继续 fail closed。
6. 测试迁移到 owner-level contract，覆盖 HTML+XSD、DOCX+XLSX+DOCX、损坏 primary、空 companion、
   material 多文件全转换、selection/source/action 非法矩阵、fresh selection、SEC/CN/tool material
   非法 suffix 零副作用、strict failure JSON round-trip，以及既有 atomic/cancel/rollback regression。

## Accepted review findings 修复

1. A1：`FinsUploadFailureReason` 的 kind 文档补齐 closed `usage`，与 enum 和 JSON contract 一致。
2. A2：`_build_pending_assets` 的 Raises 分开声明 prepare cancellation、filing wrapped failure、material
   原样 `DoclingConversionError` 与缺失 primary 的 invariant failure。
3. A3：新增两项 material 的 prepare cancellation 反例；首项转换完成后，第二项前 token 翻转，断言
   cancelled、空 events、partial plan 丢弃、零 batch、零 source/blob 发布。
4. A4：新增 `[ok.pdf, corrupt.docx]` 第 N 项 typed failure；Service 断言异常 identity 与零 batch，SEC
   workflow 断言 closed content failure、`file_label=None`、零 stored count 和零 material source 发布。
5. A5：`FinsUploadFailureReason.__post_init__` 自身校验 enum 具体类型和 kind/code 唯一映射；closed code
   分组在 import-time 显式验证 kind 完整、code 互斥与完整，parser 继续消费同一 mapping；测试覆盖 direct
   mismatch、open enum value 与 mapping contract。

## 验证

### 测试

- 计划 focused suite：`1235 passed, 1 skipped, 3 warnings`，24.86 秒。
- skip 是需显式设置 `DAYU_RUN_DOCLING_UPLOAD_INTEGRATION=1` 的真实 Docling 集成测试。
- warnings 是 3 条既有 edgar deprecated-module warning。
- 为覆盖 `cn_pipeline.py` 同文件的下载职责，追加运行现有
  `test_cn_download_runtime.py` 与 `test_cn_download_workflow.py`：`103 passed`。
- 未运行 UF-PF06、UF-PF12。

### Coverage

使用临时 coverage data file，计划 focused suite 加现有 CN download tests 后为
`1338 passed, 1 skipped, 3 warnings`；逐文件结果：

| Production file | Coverage |
|---|---:|
| `dayu/cli/arg_parsing.py` | 99% |
| `dayu/cli/commands/fins.py` | 86% |
| `dayu/documents/docling_runtime.py` | 91% |
| `dayu/fins/ingestion_runtime.py` | 92% |
| `dayu/fins/pipelines/cn_pipeline.py` | 94% |
| `dayu/fins/pipelines/docling_upload_service.py` | 89% |
| `dayu/fins/pipelines/sec_upload_workflow.py` | 95% |
| `dayu/fins/tools/upload_tools.py` | 92% |
| `dayu/fins/upload_batch.py` | 96% |
| `dayu/fins/upload_failure.py` | 95% |
| `dayu/fins/upload_format_contract.py` | 93% |
| 合计 | 92% |

首轮只运行计划 focused matrix 时 `cn_pipeline.py` 为 69%；直接证据显示未覆盖部分属于同文件的
下载职责。追加现有 CN download tests 后达到 94%，没有为覆盖率新增越界生产逻辑、pragma 或测试替身。

### 静态与变更审计

- Changed-file Pyright：`0 errors, 0 warnings, 0 informations`。
- Ruff：全部通过。
- Black `--check`：全部通过。
- `git diff --check`：通过。
- `FINS_UPLOAD_FILE_SUFFIXES|SUPPORTED_UPLOAD_SUFFIXES`：全仓 Python 零引用。
- `_pick_primary_docling_file`：全仓 Python 零引用。
- 新增 diff 无 `hasattr/getattr`、`Any/object` 签名。
- registry、oracle/scenario、Host/Engine design、README diff 均为空。

## Docs decision

本 slice 不修改 README。用户明确禁止 README，且 approved plan 将最终用户/开发者文档同步归属 Slice 4。
本轮文档仅包含 Slice 3 implementation artifact 与 accepted findings 的 code-fix artifact。

## Residual risks 与未覆盖项

- `delete + files` 历史不一致：用户明确排除，assigned to other upload work unit。
- duplicate、basename/derived-name collision、显式 primary 与 batch association：assigned to UF-FIX07/
  后续 work unit；本实现未增加 fallback 或碰撞修复。
- 真实全格式 fixture 与 mandatory scenario：covered by UF-PF06/UF-PF12；本轮按约束未运行。
- README 职责更新：covered by approved Slice 4。
- 真实 Docling service integration：测试存在但默认显式 skip；真实格式矩阵由 UF-PF06 owner 验证。
- 未分类 residual risk：无。

## Completion signal

Slice 3 exact changes、accepted A1-A5 与测试矩阵完成，全部计划 production files 覆盖率达到 80% 以上，
静态审计通过，没有触发 storage schema、原子 batch、public explicit-primary 或 collision stop condition。
当前下一入口为 Slice 3 code re-review；本 implementation agent 按用户要求停止，不 commit、不自行裁决 review。
