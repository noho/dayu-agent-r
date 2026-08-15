# UF-FIX06 Slice 4 implementation artifact

## Gate metadata

- Work unit: `UF-FIX06 converter-capability-owner`
- Slice: `Slice 4 - 文档、全局审计与验证收口`
- Gate: `implementation -> code review -> fix`
- Date: `2026-08-15`
- Baseline commit: `8033a56eb0f44ae5664c510b84ebe448050888eb`
- Status: `FIX COMPLETE / RE-REVIEW PENDING`
- Next entry point: `code re-review`
- Commit: 未创建；本 Slice 明确禁止 commit。
- Artifact path: `docs/gateflow/uf-fix06-slice4-implementation-20260815.md`

## Scope

Slice 4 原 implementation 只修改以下文档：

- `README.md`
- `dayu/fins/README.md`
- `tests/README.md`
- `docs/gateflow/uf-fix06-slice4-implementation-20260815.md`

code review 裁决接受 A1-A4 后，fix gate 最小重开以下 owner 与直接 contract tests，并新增 fix artifact：

- `dayu/fins/upload_format_contract.py`
- `tests/fins/test_upload_format_contract.py`
- `tests/cli/test_arg_parsing.py`
- `tests/fins/test_fins_ingestion_tools.py`
- `docs/gateflow/uf-fix06-slice4-code-fix-20260815.md`

生产文件只修改 LLM-facing 文本投影，不改变格式 capability、selection、转换、存储或状态行为。
未修改 review artifact、design、registry、oracle/scenario、其它生产/测试文件或冻结 evidence。
未更新 `dayu/README.md`，因为本 Slice 没有改变分层关系或装配方式。

## First-principles judgment and owner evidence

文档更新动机成立：生产代码已将转换能力与 filing/material 角色建模收敛到明确 owner，
旧 README 仍保留重复 allow-list 真源声明，且未向用户说明 primary/companion 的不同转换语义。
直接代码证据如下：

- `dayu.documents.docling_runtime` 的 immutable converter capability 定义产品选定的格式与有序后缀，
  并将同一格式集合传入实际 converter `allowed_formats`。
- `dayu.fins.upload_format_contract` 是 Fins role overlay：filing 首项是必须转换的 primary，
  后续项是仅原样保存的 companions；`.xsd` 只作为 companion-only overlay；material 每项都要转换。
- CLI `--files` help 与 LLM-facing upload tool schema 都直接消费
  `FINS_UPLOAD_FORMAT_TEXT`，不自行重建格式或角色语义。
- `DoclingUploadService` 将 filing converter inputs 收窄为唯一 `selection.require_primary()`，
  读取全部 originals，并从 primary 转换结果显式产生 `primary_document`。

本 Slice 只投影已落地 contract，未新增格式 registry、MIME/content sniffing、显式 primary selector、
batch companion 自动关联或兼容分支，因此没有过度设计。

## Documentation decisions

### Root README

- 只记录最终用户语义：`--files` 首项是必须实际转换成功的 primary，后续项是只原样保存、
  不执行 Docling 的 companions。
- 说明 XBRL companion 可随同一批保存；`.xml` / `.json` 分别只是 XBRL XML / Docling JSON
  candidate；主文件后缀通过只表示转换资格，随附文件只按可随批保存后缀准入且不转换。
- 不复制格式清单，即时清单以 `dayu-cli upload_filing --help` 为准；不宣称 legacy
  DOC/PPT/XLS 或 ZIP 受支持。
- 说明读取、filing primary 或 material 任一需要转换的文件转换失败时 source/blob 零部分发布；
  filing 不回退为只保存 originals/companions。

### Fins README

- 记录 Documents converter capability 是产品格式与实际 converter allowed formats 的 owner。
- 记录 Fins role overlay 是 filing primary/companion 与 material typed selection 的 owner。
- 更新 typed data flow：workflow fresh validation/selection -> 读取全部 originals -> filing 只转换
  primary，material 转换全部文件 -> 单一 storage batch 原子发布。
- 删除 `FINS_UPLOAD_FILE_SUFFIXES` 是 upload 后缀真源的旧声明，改为 batch scanner 消费
  Fins primary capability 投影。
- 明确 requested/stored 仍只统计 originals，原子发布与取消语义不变。
- 恢复 material 在 prepare 前独立提交 company meta batch 的既有语义：后续转换/存储失败不回滚
  company meta，但 source/blob 仍保持零部分发布。

### Tests README

- 增加可直接运行的 upload converter capability / Fins role owner focused 命令。
- 记录 Documents capability、Fins role selection、help/schema/batch 同源、filing 单次 primary 转换、
  material 全转换、全 originals 原子发布、零部分发布失败边界与 original-only 计数范围。
- 明确 deterministic owner-level 回归不替代真实全格式 fixture 矩阵或全量 CLI scenario evidence。

## Validation

### Original focused matrix

按计划运行原 14 个 focused test 文件：

- Result: `1235 passed, 1 skipped, 3 warnings`
- Exit code: `0`
- 未运行 UF-PF06、UF-PF12 或真实 CLI evidence。
- 3 个 warning 均是已安装 `edgar` 包的 deprecation warning。

### First production coverage attempt and Controller adjudication

首轮 coverage 仅使用原 14 文件矩阵，测试仍为 `1235 passed, 1 skipped`，但
`dayu/fins/pipelines/cn_pipeline.py` 只有 `69%`，低于 `>=80%` stop condition。当时立即停止，
未继续 pyright、后续审计或 artifact closeout。

Controller 裁决该缺口是原 14 文件未包含既有同文件职责测试，允许在不修改生产代码或测试的前提下追加：

- `tests/fins/test_cn_download_runtime.py`
- `tests/fins/test_cn_download_workflow.py`

### Supplemental production coverage matrix

追加上述两个既有职责测试后：

- Test result: `1338 passed, 1 skipped, 3 warnings`
- Exit code: `0`

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

- Aggregate coverage: `92%`
- Decision: 全部 11 个目标生产文件均 `>=80%`，coverage stop condition 已解除。

### Type checking

```text
python -m pyright dayu/ tests/ utils/
0 errors, 0 warnings, 0 informations
```

### Static owner audit

- `rg -n 'FINS_UPLOAD_FILE_SUFFIXES|SUPPORTED_UPLOAD_SUFFIXES' dayu tests -g '*.py'`：无结果。
- `rg -n '_pick_primary_docling_file' dayu tests -g '*.py'`：无结果。
- 目标 upload consumers 的 consumer-local suffix collection 扫描：无结果。
- 11 个目标生产文件的 `hasattr/getattr` 扫描：无结果。
- Service 代码证据确认 filing `converter_inputs` 只由 `selection.require_primary()` 产生，
  转换循环只遍历该 typed projection，不按每个 filing original 转换。

审计中一次 consumer-local suffix `rg` 的字符类书写错误导致命令本身报错；随后只修正该正则并重跑，
修正后命令退出 `0` 且无结果。

### README / help / tool schema comparison

使用纯进程内对象对照，未启动真实 CLI：

- argparse `upload_filing --files` action help 精确等于 `FINS_UPLOAD_FORMAT_TEXT.filing_files`。
- LLM-facing upload tool `files` schema description 精确等于
  `FINS_UPLOAD_FORMAT_TEXT.upload_tool_files`。
- help/schema 同时包含首文件 primary、必须实际转换成功、后续 raw companions 不转换、
  `.xml` 只是 XBRL XML candidate，以及后缀不保证内容转换成功。
- 根 README 包含等价用户语义、XBRL companion 原样保存、即时 `--help` 真源、
  legacy DOC/PPT/XLS/ZIP 非支持声明与原子失败不回退。
- Result: `README/help/tool schema semantic comparison: PASS`

### Final scope and whitespace audit

- `git diff --check`: 通过。
- `git diff --exit-code -- docs/cli_ci_oracles.json docs/cli_ci_scenarios.json docs/host/design.md docs/engine/design.md`:
  退出 `0`，无变更。
- 写入 artifact 前 `git diff --name-only` 只包含三个允许的 README。
- 冻结 evidence 位于 workspace 外；本 Slice 未读取或写入该 bundle，也未生成任何替代 evidence。

### Code review fix revalidation

根据 `docs/reviews/uf-fix06-slice4-code-review-adjudication-20260815.md` 接受的 A1-A4 完成修复后：

- owner/help/tool schema 三文件回归：`568 passed, 3 warnings`，退出 `0`。
- 原 14 文件 focused matrix：`1235 passed, 1 skipped, 3 warnings`，退出 `0`。
- 本 fix 未重新采集 coverage，因此按裁决不追加两个 CN download tests；上文 implementation 阶段的
  追加 CN tests coverage 证据保持 `92%` aggregate、11 个目标生产文件均 `>=80%`。
- 全量 `python -m pyright dayu/ tests/ utils/`：`0 errors, 0 warnings, 0 informations`。
- 纯进程内 README/help/tool schema 三面对照：`PASS`；argparse action help 与 owner 精确相等，
  tool `files` description 与 owner 精确相等，并明确区分 primary conversion eligibility 与
  companion storage admission；未启动真实 CLI。
- 静态旧 allow-list 与旧 `_pick_primary_docling_file` 扫描均无结果；owner-specific 代码对照确认
  upload service 从 typed `converter_inputs` 的首次转换结果直接产生 `primary_document`，未从生成文件集合反推。
- `git diff --check` 与 protected diff audit 通过；oracle/scenario 与 Host/Engine design 无 diff。
- 未运行 UF-PF06、UF-PF12 或真实 CLI evidence。

## Findings

| Finding | 裁决 | Fix 状态 | 修复证据 |
|---|---|---|---|
| A1 | accepted / blocking | 已修复 | owner 将转换资格限定为主文件，并自足说明随附文件只按可保存后缀准入且不转换；三处 exact tests 通过 |
| A2 | accepted / low | 已修复 | 根 README 增加 `.json` Docling JSON candidate 限定 |
| A3 | accepted / low | 已修复 | 根 README 同时覆盖 filing primary 与 material 任一需要转换文件失败，filing fallback 单独说明 |
| A4 | accepted / low | 已修复 | Fins README 恢复 material 独立 company batch 与 source/blob 零部分发布边界 |
| A5 | rejected as fix requirement | 证据失效 | Controller 明确无需修改；本轮已独立重跑要求的验证 |

Deferred findings: 无。Needs-more-evidence findings: 无。Blocking open questions: 无。

## Residual risks and uncovered areas

| Residual | Classification | Owner / destination |
|---|---|---|
| 未运行真实全格式 fixture 矩阵 | assigned to later work unit | UF-PF06 |
| 未运行全量 mandatory CLI scenario | assigned to later work unit | UF-PF12 |
| batch 不会自动将同目录 `.xsd` 与 filing primary 关联 | assigned to later work unit | 后续 batch association / UF-FIX07 类 work unit |
| 显式 primary selector、重复输入与 basename/derived-name collision | assigned to later work unit | UF-FIX07 |
| 一个 focused node 在当前环境 skip | covered by current deterministic matrix | 两轮矩阵整体退出 `0`，未产生 blocking failure |

无未分类 residual risk。

## Completion decision

Slice 4 的 A1-A4 fix、文档投影、focused regression、既有补充 production coverage、全量 pyright、
静态 owner audit、README/help/tool schema 三面对照和最终范围审计均已完成。文本 owner 与直接
contract tests 的最小重开严格遵守 code review 裁决，没有改变生产行为。

Final implementation status: `FIX COMPLETE / RE-REVIEW PENDING`.
