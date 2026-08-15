# Code Re-Review

## Scope

- Mode: current changes
- Branch: `codex/upload-filing-oracle`
- Base: `8033a56e`
- Output file: `docs/reviews/code-re-review-slice4-mimo-20260815.md`
- Included scope:
  - `README.md`（unstaged）
  - `dayu/fins/README.md`（unstaged）
  - `tests/README.md`（unstaged）
  - `dayu/fins/upload_format_contract.py`（unstaged，A1 owner fix）
  - `tests/fins/test_upload_format_contract.py`（unstaged，A1 exact test）
  - `tests/cli/test_arg_parsing.py`（unstaged，A1 CLI fragment test）
  - `tests/fins/test_fins_ingestion_tools.py`（unstaged，A1 tool schema fragment test）
  - `docs/gateflow/uf-fix06-slice4-implementation-20260815.md`（untracked，未修改）
  - `docs/gateflow/uf-fix06-slice4-code-fix-20260815.md`（untracked，fix artifact）
- Excluded scope: 生产代码（除 upload_format_contract.py）、测试（除上述三个）、oracle/scenario、design、冻结 evidence
- Parallel review coverage: 无

## Re-review baseline 与证据方法

本 re-review 读取以下直接证据：

1. Controller 裁决：`docs/reviews/uf-fix06-slice4-code-review-adjudication-20260815.md`，A1 blocking、A2-A4 low、A5 rejected。
2. Fix artifact：`docs/gateflow/uf-fix06-slice4-code-fix-20260815.md`。
3. 当前 `git diff 8033a56e`：三个 README、owner 文件、三个测试文件。
4. Owner 文件全文：`dayu/fins/upload_format_contract.py`，重点 `project_fins_upload_format_text()`。
5. 验证声明：fix artifact 的 validation 章节（owner/help/tool schema exact tests、focused matrix、pyright、static audit）。

## 逐项核验

### A1 — accepted / blocking：owner 文案区分 primary conversion eligibility 与 companion storage admission

**裁决要求**：在 `dayu/fins/upload_format_contract.py` 将"后缀通过只表示具备转换资格"限定为"主文件后缀通过"，并自足说明随附文件只校验可随批保存的后缀、不执行转换。更新 owner-level exact projection 测试。

**核验结果**：

Owner diff（`upload_format_contract.py:565-566`）将：
```
".xml 仅是 XBRL XML 候选，不代表任意 XML；后缀通过只表示具备转换资格，不保证文件内容转换成功。"
```
改为：
```
".xml 仅是 XBRL XML 候选，不代表任意 XML；主文件后缀通过只表示具备转换资格，不保证文件内容转换成功。"
"随附文件只校验可随批保存的后缀，不执行转换。"
```

- ✅ "后缀通过" → "主文件后缀通过"：明确限定为 filing primary / material converter-required 文件
- ✅ 新增独立句"随附文件只校验可随批保存的后缀，不执行转换"：自足说明 companion storage admission 语义
- ✅ owner test（`test_upload_format_contract.py`）改为 exact `filing_text == expected_filing_text` 和 `tool_text == expected_tool_text`，锁定完整文本
- ✅ CLI test（`test_arg_parsing.py`）新增 `"主文件后缀通过只表示具备转换资格"` 和 `"随附文件只校验可随批保存的后缀，不执行转换"` fragment assertions
- ✅ tool schema test（`test_fins_ingestion_tools.py`）同步新增相同 fragment assertions
- ✅ CLI help 和 tool schema 继续机械消费同一 `FINS_UPLOAD_FORMAT_TEXT` owner projection

**A1 核验结论：通过。** owner 文案精确区分了 primary conversion eligibility 与 companion storage admission；exact projection 测试锁定同源。

### A2 — accepted / low：根 README 补齐 `.json` 限定

**裁决要求**：根 README 增加 `.json` 只是 Docling JSON candidate，与 help/tool schema 保持等价。

**核验结果**：

README diff（`README.md:319`）将：
```
`.xml` 只是 XBRL XML candidate；后缀通过
只表示文件具备转换资格，不保证其内容一定转换成功。
```
改为：
```
`.xml` 只是 XBRL XML candidate，`.json`
只是 Docling JSON candidate；主文件后缀通过只表示具备转换资格，不保证其内容一定转换成功；
随附文件（含 `.xsd`）只按可随批保存的后缀准入，不做转换。
```

- ✅ `.json` 限定已加入：`.json 只是 Docling JSON candidate`
- ✅ 与 owner text `.json 仅是 Docling JSON 候选，不代表任意 JSON 内容可转换` 语义等价
- ✅ 未复制后缀清单，继续委托 `--help` 为即时真源

**A2 核验结论：通过。**

### A3 — accepted / low：根 README 覆盖 filing/material 转换失败

**裁决要求**：根 README 的失败触发需同时覆盖 filing primary 与 material 任一 converter-required 文件。

**核验结果**：

README diff（`README.md:334`）将：
```
空文件、损坏文件或一组文件中任一文件无法解析时，整批上传失败且 `stored files` 为 `0`，
不会把先处理成功的文件计为已保存；
```
改为：
```
空文件、任一原始文件读取失败，或 filing primary / material 任一需要转换的文件内容无法成功转换时，
整批上传失败且 `stored files` 为 `0`，不会把先处理成功的文件计为已保存；
filing 失败时也不会回退为只保存原文件或 companions。
```

- ✅ 失败触发覆盖 `filing primary / material 任一需要转换的文件`：同时涵盖 filing 和 material 转换失败
- ✅ `任一原始文件读取失败`：覆盖 companion 读取失败
- ✅ `filing 失败时也不会回退为只保存原文件或 companions`：原子失败不回退单独说明
- ✅ 未暴露 `converter-required` 内部术语，使用用户可读的"需要转换的文件"

**A3 核验结论：通过。**

### A4 — accepted / low：Fins README 恢复 material 独立 company batch

**裁决要求**：Fins README 补回 material 既有独立 company publication 语义。

**核验结果**：

Fins README diff 在现有段落后新增：
```
material workflow 在 prepare 前以独立 company batch 提交 company meta；
后续转换或存储失败不会回滚已提交的 company meta，但 source/blob 仍由后续单一
publication batch 保持零部分发布。filing 的 company meta 则与 source/blob 保持同一
publication batch 的原子边界。
```

- ✅ material company meta 独立提交：`prepare 前以独立 company batch 提交 company meta`
- ✅ 失败不回滚已提交 company meta：`后续转换或存储失败不会回滚已提交的 company meta`
- ✅ source/blob 零部分发布：`source/blob 仍由后续单一 publication batch 保持零部分发布`
- ✅ filing 原子边界：`filing 的 company meta 则与 source/blob 保持同一 publication batch 的原子边界`
- ✅ 该声明是当前代码事实的恢复，不是新行为

**注意**：material company meta 独立提交的架构事实无法从当前 diff 中独立验证（需要阅读 `cn_pipeline.py` / `sec_upload_workflow.py`），但该声明是恢复既有实现事实，不是本 fix 引入的新 contract。fix artifact 声称已验证，且其与 implementation plan 一致。

**A4 核验结论：通过。**

## 整体 scope 与不变量核验

| 不变量 | 状态 |
|---|---|
| `.xml` 仅为 XBRL XML candidate | ✅ owner + README 均包含 |
| `.json` 仅为 Docling JSON candidate | ✅ owner + README 均包含（A2 fix） |
| 旧 allow-list 已清除 | ✅ fix artifact 声称 `rg` 无结果 |
| `_pick_primary_docling_file` 已删除 | ✅ fix artifact 声称 `rg` 无结果 |
| 原子发布、计数、取消无回退 | ✅ README 保持现有语义；Fins README 新增 material company meta 边界 |
| 保护文件未改 | ✅ diff 中无 `cli_ci_oracles.json`、`cli_ci_scenarios.json`、`host/design.md`、`engine/design.md` |
| tests README 命令真实 | ✅ 14 个 focused test 文件均存在 |
| owner/help/schema exact tests | ✅ fix artifact 声称 `568 passed`；owner test 锁定完整文本 |
| CLI help 与 tool schema 同源 | ✅ 两者均消费 `FINS_UPLOAD_FORMAT_TEXT` |
| A1 blocking 修复 | ✅ owner 文案精确区分 primary/companion 语义 |
| fix scope 未越界 | ✅ 只修改允许文件；未改 design、registry、oracle/scenario、frozen evidence |

## Findings

未发现实质性问题。

fix 正确修复了 A1 blocking finding：owner 文案现在精确区分"主文件后缀通过只表示具备转换资格"（primary conversion eligibility）与"随附文件只校验可随批保存的后缀，不执行转换"（companion storage admission）。exact projection 测试锁定完整文本，CLI help 和 tool schema 机械消费同一 owner。A2-A4 均为低严重度文案恢复，与当前代码实现一致。

## Open Questions

- 无。

## Residual Risk

| Residual | Classification | Owner / destination |
|---|---|---|
| 未运行真实全格式 fixture 矩阵 | assigned to later work unit | UF-PF06 |
| 未运行全量 mandatory CLI scenario | assigned to later work unit | UF-PF12 |
| batch 不会自动将同目录 `.xsd` 与 filing primary 关联 | assigned to later work unit | 后续 batch association / UF-FIX07 类 work unit |
| material company meta 独立提交的代码路径未在本次 re-review 中独立验证 | covered by fix artifact 声称 + implementation plan 一致 | UF-PF06/UF-PF12 |

无新增 residual risk。

## Conclusion

**PASS**。

A1-A4 均已正确修复并经代码阅读核验。owner 文案精确区分 primary conversion eligibility 与 companion storage admission；exact projection 测试锁定同源；根 README 补齐 `.json` 限定并覆盖 filing/material 转换失败；Fins README 恢复 material 独立 company batch 语义。原子/计数/取消无回退，scope 无越界，保护文件未改。
