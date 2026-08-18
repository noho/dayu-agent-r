# UF-FIX06 Slice 4 code fix artifact

## Gate metadata

- Work unit: `UF-FIX06 converter-capability-owner`
- Slice: `Slice 4 - 文档、全局审计与验证收口`
- Gate: `code review -> fix`
- Date: `2026-08-15`
- Baseline commit: `8033a56eb0f44ae5664c510b84ebe448050888eb`
- Adjudication: `docs/reviews/uf-fix06-slice4-code-review-adjudication-20260815.md`
- Status: `FIX COMPLETE / RE-REVIEW PENDING`
- Next entry point: `code re-review`
- Commit: 未创建；用户明确禁止 commit。
- Artifact path: `docs/gateflow/uf-fix06-slice4-code-fix-20260815.md`

## Scope and owner decision

A1 的动机成立且属于 blocking LLM-facing 语义错误。直接代码证据是：

- `FinsUploadFormatCapability.accepts_primary()` 只消费 converter capability；
- `accepts_companion()` 还接纳 companion-only `.xsd`；
- filing 的 `converter_inputs` 只包含 typed primary，companions 不进入转换循环；
- 原 owner 文案却把未限定的“后缀通过”统一描述为转换资格。

因此正确 owner 是 `dayu/fins/upload_format_contract.py` 的文本投影，而不是 README、CLI adapter 或
tool schema consumer。本 fix 只在 owner 修复语义，并让 CLI help/tool schema 继续机械消费同一文本。
A2-A4 只恢复当前实现事实，不改变 schema、selection、转换、存储或状态机。

本 fix 修改：

- `dayu/fins/upload_format_contract.py`
- `tests/fins/test_upload_format_contract.py`
- `tests/cli/test_arg_parsing.py`
- `tests/fins/test_fins_ingestion_tools.py`
- `README.md`
- `dayu/fins/README.md`
- `docs/gateflow/uf-fix06-slice4-implementation-20260815.md`
- `docs/gateflow/uf-fix06-slice4-code-fix-20260815.md`

`tests/README.md` 保留原 Slice 4 implementation 更新，本 fix 无需再改。三个 review artifacts 是 preflight
时已存在的只读输入，本 fix 未修改。design、registry、oracle/scenario、冻结 evidence 与其它生产/测试文件均未修改。

## Accepted finding fixes

| Finding | Decision | Fix 状态 | 处理 |
|---|---|---|---|
| A1 | accepted / blocking | 已修复 | owner 改为“主文件后缀通过只表示具备转换资格”，并明确随附文件只校验可随批保存的后缀、不执行转换；owner/CLI/schema tests 锁定 exact projection 与两类 admission |
| A2 | accepted / low | 已修复 | 根 README 增加 `.json` 只是 Docling JSON candidate，不复制后缀清单 |
| A3 | accepted / low | 已修复 | 根 README 覆盖 filing primary 与 material 任一需要转换的文件失败；filing 不回退为 originals/companions 单独说明 |
| A4 | accepted / low | 已修复 | Fins README 恢复 material 在 prepare 前独立提交 company meta batch、失败不回滚该 meta，而 source/blob 仍零部分发布 |
| A5 | rejected as fix requirement | 证据失效 | 不修改 review 自报告措辞；按裁决独立重跑全部要求的 fix 验证 |

## Documentation decision

- 根 README 继续只写最终用户完成上传与判断失败所需的语义；使用“material 任一需要转换的文件”，
  不暴露 `converter-required` 内部 contract 术语。
- Fins README 记录 owner/data flow 和 material company/source/blob publication 边界，属于其开发者职责。
- tests README 的现有 focused 命令与 coverage 声明仍准确，本 fix 不机械更新。
- `dayu/README.md` 不更新：分层与装配方式未变化。

## Validation

### Owner/help/tool schema exact tests

```text
pytest -q tests/fins/test_upload_format_contract.py tests/cli/test_arg_parsing.py tests/fins/test_fins_ingestion_tools.py
568 passed, 3 warnings
```

退出码 `0`。owner test 断言完整 `filing_files` 与 `upload_tool_files` 文本；CLI action help 和 tool
`files` description 分别与同一 owner 精确相等，并断言 primary conversion eligibility 与 companion
storage admission 的自足说明。

### Original 14-file focused matrix

```text
1235 passed, 1 skipped, 3 warnings
```

退出码 `0`。本 fix 未重新采集 coverage，因此没有追加两个 CN download tests；implementation 阶段已按
Controller 裁决追加这两个既有职责测试并记录 11 个目标生产文件均 `>=80%`、aggregate `92%`。

### Type checking

```text
python -m pyright dayu/ tests/ utils/
0 errors, 0 warnings, 0 informations
```

### README/help/tool schema in-process comparison

- argparse `upload_filing --files` action help 精确等于 `FINS_UPLOAD_FORMAT_TEXT.filing_files`；
- LLM-facing upload tool `files` description 精确等于 `FINS_UPLOAD_FORMAT_TEXT.upload_tool_files`；
- 根 README 同时包含 primary conversion eligibility、companion storage admission、`.xml` / `.json`
  candidate、filing/material 转换失败边界，且不包含 `converter-required`；
- 结果：`README/help/tool schema semantic comparison: PASS`；未启动真实 CLI。

### Static and protected audit

- `FINS_UPLOAD_FILE_SUFFIXES|SUPPORTED_UPLOAD_SUFFIXES`：`dayu tests` Python 文件中无结果；
- `_pick_primary_docling_file`：`dayu tests` Python 文件中无结果；
- owner-specific 代码对照：upload service 遍历 typed `converter_inputs`，并从首次转换结果直接赋值
  `primary_document`，没有从生成文件集合、basename、stem 或偶然顺序反推 primary；
- consumer 扫描未发现新增 suffix allow-list；现有命中仅为 JSON contract import、job 文件扩展名和
  Docling 派生文件名常量，不是 upload admission owner；
- `git diff --check`：通过；
- protected diff：`docs/cli_ci_oracles.json`、`docs/cli_ci_scenarios.json`、`docs/host/design.md`、
  `docs/engine/design.md` 无 diff；
- 未运行 UF-PF06、UF-PF12、真实 CLI evidence，也未读取或写入 workspace 外冻结 evidence。

审计期间一条过宽的实验性正则曾命中合法的 `primary_document = docling_name` 直接赋值及其它 download/rebuild
路径；该正则不等价于裁决要求，未修改任何文件。随后用 owner-specific 检查确认旧 picker 消失且 typed primary
数据流成立，最终静态审计通过。

## Residual risks and uncovered areas

| Residual | Classification | Owner / destination |
|---|---|---|
| 未运行真实全格式 fixture 矩阵 | assigned to later work unit | UF-PF06 |
| 未运行全量 mandatory CLI scenario | assigned to later work unit | UF-PF12 |
| batch 不会自动将同目录 `.xsd` 与 filing primary 关联 | assigned to later work unit | 后续 batch association / UF-FIX07 类 work unit |
| 显式 primary selector、重复输入与 basename/derived-name collision | assigned to later work unit | UF-FIX07 |
| focused matrix 的一个既有 node skip | covered by current deterministic matrix | 矩阵整体退出 `0`，不是本 fix 新增缺口 |

无未分类 residual risk，无 blocking open question。

## Completion decision

A1-A4 均已修复并完成裁决要求的全部验证。当前 fix 不等于 code review 通过；下一入口严格为双路
code re-review。按用户指令不 commit，并在此停止。

Final status: `FIX COMPLETE / RE-REVIEW PENDING`.
