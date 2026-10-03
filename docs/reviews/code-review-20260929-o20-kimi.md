# Code Review

- RUNTIME/PROVIDER/MODEL: claude/kimi/kimi-k3[1m]
- CANARY=kimi-17994cb4
- Review 时间：2026-09-29 09:32:10 CST（本机系统时钟）
- Work unit：`UM-O20-F01`，Slice F01-S1（material 格式说明与共享 capability 同源），已实施未提交。

## Scope

- Mode: current changes（未提交 workspace 改动，相对当前 HEAD）
- Branch: `codex/upload-material-o20`
- Base: HEAD `8c9e1d3473e5fd9c8e4509a38539a1a940140070`（accepted plan checkpoint；本 review 范围为该 HEAD 之上的全部未提交改动）
- Output file: `docs/reviews/code-review-20260929-o20-kimi.md`
- Included scope:
  - 输入文档：F01 goal `docs/gateflow/upload-material-o20-format-help-goal-20260929.md`、accepted plan `docs/gateflow/upload-material-o20-format-help-plan-20260929.md`、裁决 `docs/gateflow/upload-material-o20-plan-review-adjudication-20260929.md`、实施记录 `docs/gateflow/upload-material-o20-s1-implementation-20260929.md`、`AGENTS.md`。
  - 生产改动：`dayu/fins/upload_format_contract.py`（`project_fins_upload_format_text` 的 `material_files`）。
  - 测试改动：`tests/fins/test_upload_format_contract.py`、`tests/cli/test_arg_parsing.py`、`tests/fins/test_fins_ingestion_tools.py`。
  - 文档改动：根 `README.md`（上传章节 material 说明段）。
  - 消费链走读：`dayu/cli/arg_parsing.py:963`、`dayu/fins/tools/upload_tools.py:241,247,392`、`dayu/fins/upload_batch.py:418`、capability 真源 `dayu/documents/docling_runtime.py`（`DOCLING_CONVERTER_CAPABILITY`）、`dayu/fins/service_runtime.py:328`（真实 schema 构造入口）。
  - README 职责核对：根 `README.md` 的 `Agent更新约束`（第 9 行起）、`dayu/fins/README.md`（第 67、384 行）、`tests/README.md`（coverage 口径与第 207 行同源说明）。
- Excluded scope:
  - `docs/reviews/code-review-20260929-030106.md`：工作区中同轮另一路 review artifact，按派发要求未读取，以保持本路独立。
  - 主工作区 E01 证据与 XBRL 部署能力事实：属独立 `UM-O20-E01`/`UM-O20-F02`，本 review 只核对 F01 是否越界暗示，不复核其环境结论。
  - 转换、后缀准入、失败分类、仓储等 F01 非目标代码：仅走读其与文案 owner 的接壤面，未做全量审查。
- Parallel review coverage: 无（单路 reviewer 全程自行走读与重跑验证；未派发子 Agent）。

## Findings

未发现实质性问题。

以下为支撑该结论的对抗性检查要点（均为直接证据，已在本 checkout 本地 `.venv` 下独立重跑，未采信实施记录自述）：

1. **固定两句逐字一致**。从 accepted plan 引用块与裁决中文引号段程序化提取固定文案，二者逐字相等，且均逐字嵌入生产 `FINS_UPLOAD_FORMAT_TEXT.material_files`：`.json 仅是 Docling 格式的 JSON 文档候选，不代表任意 JSON 内容可转换。`.xml/.xbrl 仅是 XBRL 财报实例文档候选，不代表任意 XML 或独立 linkbase 文件可转换。`（`dayu/fins/upload_format_contract.py:630-631`）。插入位置经索引断言为「后缀警示句 < 句一 < 句二 < delete 句」，两句各出现恰好一次，且不出现在 `filing_files`。
2. **filing 与 capability 逐字/逐位不变**。生产 diff 唯一 hunk 只触及 `material_files`（`upload_format_contract.py:626-633`），`filing_files`（`:617-625`）、`FINS_UPLOAD_FORMAT_CAPABILITY`、`DOCLING_CONVERTER_CAPABILITY`（`docling_runtime.py:222-234`，`.xbrl/.xml→XML_XBRL`、`.json→JSON_DOCLING`）均无改动；真实 `upload_filing --help` 输出与未改动的 owner filing 文案一致。
3. **唯一格式说明 owner 成立**。全仓检索「转换资格 / 转换器支持的后缀 / 逐个实际转换成功」仅命中 owner 模块与两个测试文件；CLI（`arg_parsing.py:963` `help=FINS_UPLOAD_FORMAT_TEXT.material_files`）与 tool（`upload_tools.py:241` `description=FINS_UPLOAD_FORMAT_TEXT.upload_tool_files`）直接消费同一投影，batch（`upload_batch.py:418`）只调用 `FINS_UPLOAD_FORMAT_CAPABILITY.accepts_primary` 做后缀准入，无第二份 material 格式文案，无下游 fallback/特例/重算。`upload_tool_files` 经程序化验证等于 `upload_kind=filing 时，{filing_files}upload_kind=material 时，{material_files}每个路径必须指向已存在、非空的普通文件。`，material 段恰好嵌入一次。
4. **真实 CLI help 可读且 tool schema 同源**（本 checkout `.venv` 实跑）。`python -m dayu.cli upload_material --help` 的 `--files` 段含完整有序后缀（`.pdf … .xbrl, .xml, .json`，与 capability 顺序一致）、转换资格警示、固定两句与 delete 规则；argparse CJK 折行处（如「成功。.json 仅是 / Docling 格式的…」）语义连续可读。以隔离临时 workspace 真实构造 `DefaultFinsRuntime.create(...).get_ingestion_runtime()` 与 `build_fins_upload_tool(runtime)`：`files.description == FINS_UPLOAD_FORMAT_TEXT.upload_tool_files` 为 `True`，material 子段含固定两句，`maxItems=100`，`primary.description` 同源。
5. **测试断言 owner 级 contract 且未弱化**。owner 测试逐字断言 material 最终拼接形式（含插入位置）与 `upload_tool_files` 完整组合，filing 期望保持原文；CLI 测试断言 `files_action.help == FINS_UPLOAD_FORMAT_TEXT.material_files` 并以空白归一后的整段 owner 文案 + 有序片段断言真实格式化 help（符合裁决接受的归一口径，不会把终端折行当误报）；tool 测试断言真实 `schema.function.parameters.properties["files"]["description"]` 整体等于 owner 投影且含逐字 material 子段。三处均从唯一投影验证同一语义，无 mock 文案替代真实 parser/schema。
6. **F01 未暗示「有效 XBRL/Docling JSON 必成功」**。两句均为「仅是…候选，不代表任意…可转换」的非承诺表述；README 新增段同样只写候选资格并指向即时 help；capability、依赖、failure code 未动，F02 边界未被暗改。
7. **LLM-facing 约束**。新增文本为业务可读自足语义，无内部类型名/模块名；「Docling」一词与既有用户可见文案（filing 段、README「Docling 转换」）一致。
8. **diff 白名单核对**。已跟踪修改恰为 plan 白名单：1 个生产文件 + 3 个测试文件 + 根 `README.md`；未跟踪文件为实施记录（gateflow 预期产物）与另一路 review artifact（非本 slice 实施物）。`git diff --check` 通过。
9. **README 职责**。根 README 命中「用户可见 CLI 文案/最终用户工作流」触发，新增段位于上传章节、面向最终用户、material 范围明确、后缀清单指向即时 CLI help、未复制完整清单、未宣称端到端成功，符合其 `Agent更新约束`；既有 filing 段逐字未动。`dayu/fins/README.md:384` 与 `tests/README.md:207` 只描述 owner/同源关系与覆盖层级，未引用会因此次文案变化而过时的逐字 material 句子，「无需修改」判断成立。
10. **venv 身份与验证复跑**。本 checkout 存在本地 `.venv`：`python=3.11.15`、`sys.executable=/private/tmp/dayu-upload-o20/.venv/bin/python`、`dayu.__file__=/private/tmp/dayu-upload-o20/dayu/__init__.py`；以下均在该 venv 激活后由本 reviewer 独立重跑：
    - 定向回归（7 个测试文件）：`779 passed, 3 warnings in 14.30s`，退出 0；警告来自 edgartools 废弃 API，与改动无关。
    - 单文件覆盖率（tests/README 的 coverage run/report 口径）：`coverage erase` + 同 7 文件 `coverage run -m pytest -q`（`779 passed`）+ `coverage report --include='dayu/fins/upload_format_contract.py' --fail-under=80` → `165 Stmts / 12 Miss / 93% Cover`，退出 0。
    - `pyright`：`0 errors, 0 warnings, 0 informations`，退出 0。

## Open Questions

- 无。

## Residual Risk

- **R1（已登记，独立 `UM-O20-F02`，条件已触发）**：当前标准安装下完整 XBRL instance 端到端失败（首因缺 `arelle-release`，后续 taxonomy fetch 与 `memberQname=None` 未裁决）。F01 文案只声明候选资格，未将该能力表述为已验证成功；filing `.xbrl` 限定缺口、独立 linkbase 边界与 filing/material 术语不一致（filing 作「XBRL XML 候选 / Docling JSON 候选」，material 作「XBRL 财报实例文档候选 / Docling 格式的 JSON 文档候选」）按裁决留交 F02 对所有公开入口清算。本 review 复核确认 F01 未越界改写 filing 或 capability。
- **R2（已登记，`UM-O20-E01` 剩余补证）**：Docling JSON 的 validated success 属主工作区所记录环境；本 slice 未在本地做真实上传转换补证，XBRL 不得记 validated success。
- **R3（已登记）**：五份冻结负样本只证明输入不符声明子类型，不构成本次能力结论。
- **R4/R5（已接受的低风险）**：tool schema 描述变长带来的少量 LLM token 增量；argparse 既有 CJK 折行上限。本次真实 help 已人工复核语义连续可读。
- **观察项（非 finding）**：根 README 新增段对「不保证转换成功」为意译（「后缀符合要求不保证文件内容转换成功」），与 owner 原文（「后缀通过只表示具备转换资格…」）语义等价，且该段明示后缀清单以即时 CLI help 为准，与既有 filing 段的文档模式一致；plan 明确允许简短 paraphrase，未构成第二真源。
- **验证边界**：按 plan 范围重跑 7 个定向测试文件，未运行全仓测试套件；`docs/reviews/code-review-20260929-030106.md` 未读取、未核对。

## 结论

**pass**。F01-S1 实施与 accepted plan/裁决逐字对齐：唯一文案 owner 处一次投影、CLI/tool 同源消费、batch 仅复用 capability 后缀准入；filing 与 capability 不变；固定两句不承诺有效输入必成功，F02/E01 边界未被侵入；受影响测试、单文件覆盖率 93%（≥80%）、pyright、真实 CLI help 与真实 tool schema 均在本 checkout 本地 `.venv` 独立复跑通过；diff 白名单吻合。可按 gateflow 进入下一 gate（与另一路 review 汇合裁决）。
