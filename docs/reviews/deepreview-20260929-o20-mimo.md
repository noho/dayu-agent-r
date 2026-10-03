# Deepreview — UM-O20-F01 aggregate gate（MiMo 独立审查）

- RUNTIME/PROVIDER/MODEL: claude/mimo/mimo-v2.6-pro[1m]
- CANARY=mimo-fcfc3244
- Work unit：`UM-O20-F01`（material 格式说明与共享 capability 同源），Gate：双路 `$deepreview` aggregate gate（本文件为 MiMo 路；与 Kimi 路并行独立，全程未读 Kimi 同轮结果）。
- Review 时间：2026-09-29（本机系统时钟）。

## Scope

- Mode: Gateflow aggregate deepreview，等价 Current Changes Mode；review 对象为**已提交** range `8c9e1d3473e5fd9c8e4509a38539a1a940140070..7870e84a`（单 commit `7870e84a` "gateflow: accept UM-O20-F01 S1"）。
- Branch: `codex/upload-material-o20`。
- Base: `8c9e1d3473e5fd9c8e4509a38539a1a940140070`（accepted plan checkpoint）。HEAD 预检：`git rev-parse HEAD` = `7870e84a412cf79a7d3d4f20b9cc07997787abdd`，与 range 终点一致，无 scope 漂移；`git status --short` 仅有一份未跟踪的 Kimi 同轮 artifact（见 excluded），工作树无未提交产品改动。
- Output file: `docs/reviews/deepreview-20260929-o20-mimo.md`（任务指定路径，覆盖 deepreview 默认 timestamp 命名）。
- Included scope:
  - range 内产品/测试/文档 diff 全部 10 个文件：`dayu/fins/upload_format_contract.py`、`tests/fins/test_upload_format_contract.py`、`tests/cli/test_arg_parsing.py`、`tests/fins/test_fins_ingestion_tools.py`、根 `README.md`、`docs/gateflow/upload-material-o20-s1-implementation-20260929.md`、`docs/gateflow/upload-material-o20-s1-code-review-adjudication-20260929.md`、`docs/reviews/code-review-20260929-030106.md`、`docs/reviews/code-review-20260929-o20-kimi.md`、`docs/reviews/code-review-20260929-o20-mimo.md`。
  - 输入文档（先读）：`AGENTS.md`、goal `docs/gateflow/upload-material-o20-format-help-goal-20260929.md`、accepted plan `docs/gateflow/upload-material-o20-format-help-plan-20260929.md`、plan review 裁决 `docs/gateflow/upload-material-o20-plan-review-adjudication-20260929.md`、S1 implementation、双路 code review（Kimi/MiMo 的 S1 版本）与 S1 总控 adjudication。
  - owner/消费链走读：`dayu/fins/upload_format_contract.py`（`project_fins_upload_format_text`、`FINS_UPLOAD_FORMAT_CAPABILITY`）、`dayu/documents/docling_runtime.py`（`DOCLING_CONVERTER_CAPABILITY`）、`dayu/cli/arg_parsing.py:926-963`、`dayu/fins/tools/upload_tools.py:241,247,392`、`dayu/fins/upload_batch.py:418`、`dayu/fins/ingestion_runtime.py`、`dayu/fins/service_runtime.py`。
  - 验证面：plan 指定七测试文件实跑、单文件覆盖率、pyright、真实 CLI `upload_material/upload_filing --help`、真实构造 tool schema、全库格式文案漂移检索、README 职责核对。
- Excluded scope:
  - `docs/reviews/deepreview-20260929-o20-kimi.md`（Kimi 同轮 deepreview，未跟踪文件，**全程未读**，保持并行独立）。
  - `UM-O20-F02`（XBRL 运行能力/依赖/术语清算）与 `UM-O20-E01`（正样本补证）：已分类独立项，本 review 只核对 F01 未越界宣称其已解决，不复核其环境结论、不裁决其范围。
  - Docling 内容抽取准确率（goal 明确归上游，不在项目职责）。
- Parallel review coverage: 无 subagent（任务禁止派发）；全部走读与验证由本 reviewer 自行完成。
- Review 结论: **pass-with-risks**（无未修复 finding；残余风险均已登记分类，不阻塞放行）。

## Findings

未发现实质性问题。

### 对抗性检查记录（已证伪的攻击面，非 finding；证据均为本 reviewer 在本 checkout `.venv` 自行复跑/机器比对，不采信实施与既有 review 自述）

1. **固定两句逐字、唯一、位置、连写**。plan/裁决冻结文本（`.json` 仅是 Docling 格式的 JSON 文档候选，不代表任意 JSON 内容可转换。`.xml/.xbrl` 仅是 XBRL 财报实例文档候选，不代表任意 XML 或独立 linkbase 文件可转换。）与 `upload_format_contract.py:630-631` 运行时投影机器比对：`fixed_in_material_verbatim=True`、出现次数恰为 1、`fixed_in_filing=0`；索引断言「后缀通过只表示具备转换资格，不保证文件内容转换成功。」< 固定两句 <「delete 不得提供文件。」，两处衔接 gap 均为空串（连写无额外空格）。生产 diff 唯一 hunk 仅此三行文本插入。
2. **filing / capability 不漂**。以 `git show HEAD~1:dayu/fins/upload_format_contract.py`（即 base `8c9e1d34`）动态执行对照：`filing_files`、`filing_primary`、`upload_tool_primary`、`upload_tool_material_primary_failure` 全部逐字不变；`material_rest_preserved=True`（当前 material 文案删除固定两句后与 base 逐字相同）。`DOCLING_CONVERTER_CAPABILITY`（`dayu/documents/docling_runtime.py:222-234`，`.xbrl/.xml→XML_XBRL`、`.json→JSON_DOCLING`）与 `FINS_UPLOAD_FORMAT_CAPABILITY` 在 range 内零改动；固定两句的候选类型表述与该映射一致。
3. **唯一格式说明 owner 与三入口同源**。全库检索格式文案产生点仅 `project_fins_upload_format_text`（`upload_format_contract.py:589`）。消费链实读：CLI `arg_parsing.py:963` `help=FINS_UPLOAD_FORMAT_TEXT.material_files`；tool `upload_tools.py:241` `description=FINS_UPLOAD_FORMAT_TEXT.upload_tool_files`（由 `material_files` 一次生成后组合复用，运行时断言 material 子段嵌入恰一次）；batch `upload_batch.py:418` 仅消费 `FINS_UPLOAD_FORMAT_CAPABILITY.accepts_primary` 做后缀准入，skip 原因为 typed `unsupported_suffix`（"不支持的上传文件后缀: …"），无内容格式承诺，与新文案「后缀通过≠内容可转换」不矛盾。`dayu/service`、`dayu/host`、`dayu/ui`、`dayu/engine`、`dayu/config/prompts` 无独立 material 格式文案；`material_files`/`upload_tool_files` 的消费点仅上述两处。无下游 fallback、特例、重算或第二真源。
4. **真实 CLI help 语义连续**。本 checkout `.venv` 实跑 `python -m dayu.cli upload_material --help`：`--files` 段含完整有序后缀（`.pdf … .xbrl, .xml, .json`，与 capability 顺序一致）、"并逐个实际转换成功"、转换资格警示、固定两句、delete 规则；argparse 折行只落在空格处（「。.json 仅是 / Docling 格式的…」「仅是 / XBRL 财报实例…」「delete / 不得提供文件。」），拼回即 owner 逐字文本。`upload_filing --help` 的 `--files` 段与 base filing 文案逐字一致。
5. **真实 tool schema 同源、参数结构不变**。以隔离临时 workspace（`Path` 入参）实跑 `DefaultFinsRuntime.create(...).get_ingestion_runtime()` + `build_fins_upload_tool(runtime)`：`files.description == FINS_UPLOAD_FORMAT_TEXT.upload_tool_files` 为 `True`，固定两句在 schema 中，material 子段整段嵌入一次；`files.type=array`、`maxItems=100`、`primary.type=string`、`primary` 描述同源，`required=('ticker', 'upload_kind')`（primary 非必填，与原设计一致）。
6. **非承诺句式，F02/E01 边界未越界**。固定两句为「仅是…候选，不代表任意…可转换」资格表述；机器检查 material/tool 文本无「必成功/一定成功/保证转换成功」类承诺片段。implementation 记录与 S1 adjudication 均把 F02（XBRL 运行能力，条件已触发但独立裁定）、E01（正样本补证剩余）明确登记为未解决独立项；本 commit 的 docs 无「F02/E01 已解决」表述。diff 未触碰依赖、装配、capability、失败分类、仓储。
7. **测试断言 owner 级 contract，未弱化、未固化偶然行为**。owner 测试（`test_upload_format_contract.py:305-345`）对六个投影字段整体逐字相等断言（固定两句插入位置由此钉死），filing 预期保持原文；suffix 清单 `_PRIMARY_SUFFIXES` 与 `FINS_UPLOAD_FORMAT_CAPABILITY.primary_suffixes` 交叉断言（`:65`），无第二后缀真源。CLI 测试断言 `files_action.help == FINS_UPLOAD_FORMAT_TEXT.material_files`（owner 原文逐字）并经 `_capture_help`（真实 `build_parser()` + argparse 渲染，非 mock）对格式化 help 做空白归一后断言完整 material 文本连续可见 + 固定两句有序片段。tool 测试从真实构造 schema 断言整体等于 owner 投影、固定三句尾段逐字、整段 material 嵌入。三层形成「冻结字面量（owner 测试）→ help/schema 等于 owner 投影 → 渲染输出含 owner 文本」的闭环，任一环节漂移均可测出。
8. **越界与过度耦合检查**。diff 白名单与 plan 一致：1 生产 + 3 测试 + 根 README；另 5 份 gate/review 文档属 "gateflow: accept" 提交的流程产物（与本分支既有 accept 提交模式一致），非实施写入。无新 public API/schema 字段/状态机/迁移（tool schema 仅描述文本变化，不触发起库条款）；无 F02 顺手改动；CLI/tool/batch 只依赖稳定投影或 capability，一次投影改动即服务三入口，无跨层穿透或隐性字符串协议。
9. **LLM-facing 自足性**。新增文本为业务可读规则（候选内容类型 + 不保证转换），无内部类型名/模块名/format id；"Docling" 与既有用户可见文案（filing 段、README）用语一致。"linkbase" 为 XBRL 领域词、未加短释——但该措辞是 plan/裁决冻结的用户裁决文本，且「独立 linkbase 文件可转换与否」的操作性规则清晰；术语与边界清算已登记 F02，不在本切片改写（改写反而违反逐字冻结要求）。
10. **README 职责与残留检查**。根 README 命中「用户可见 CLI 文案」触发，新 4 行段位于上传章节、面向最终用户、只写候选/非保证语义、后缀清单指向即时 CLI help、未复制完整清单、未宣称端到端成功，符合 plan 的 README 取舍与该文件 `Agent更新约束`；既有 filing 段逐字未动（diff 仅插入）。`dayu/fins/README.md`、`tests/README.md`、`dayu/README.md` 无会过期的 material 逐字引用（检索零命中），"无需修改"判断成立。旧拼接形式「转换成功。delete 不得提供文件」在 dayu/tests/README 零残留（仅存于历史 review 文档引文中）。

### diff 白名单核对

| 文件 | plan 白名单 | 实际 diff | 结果 |
| --- | --- | --- | --- |
| `dayu/fins/upload_format_contract.py` | 唯一允许生产文件 | `material_files` +3 行文本（固定两句插入） | 一致 |
| `tests/fins/test_upload_format_contract.py` | 允许 | `expected_material_text` 更新为最终拼接形式 | 一致 |
| `tests/cli/test_arg_parsing.py` | 允许 | help 同源 + 归一全文/固定两句断言 | 一致 |
| `tests/fins/test_fins_ingestion_tools.py` | 允许 | schema material 尾段 + 整段嵌入断言 | 一致 |
| 根 `README.md` | 允许（上传章节短说明） | 4 行 material 候选/非保证段，指向即时 CLI help | 一致 |
| 其它生产/测试/README | 禁止 | 无 | 一致 |
| gate/review 文档 ×5 | 流程产物（accept 提交） | implementation、S1 adjudication、3 份 review artifact | 与分支 accept 模式一致 |

`git diff --check`（range）退出 0。

## 验证证据（本 reviewer 在本 checkout `.venv` 自行复跑，非采信实施/既有 review 自述）

- **venv 身份**：`.venv` 存在于本 checkout；`python 3.11.15`，`sys.executable=/private/tmp/dayu-upload-o20/.venv/bin/python`，`dayu.__file__=/private/tmp/dayu-upload-o20/dayu/__init__.py`；`python -m pip check` 无破依赖。
- **定向回归**（plan 指定七文件：owner/CLI tool/batch/SEC material stream/CN/Docling upload service）：`python -m pytest -q` → `779 passed, 3 warnings in 12.33s`，退出 0（警告为 edgartools 废弃 API，与本切片无关）。
- **单文件覆盖率**（tests/README 口径）：`coverage erase` + `coverage run -m pytest -q` 同七文件（779 passed）+ `coverage report --include='dayu/fins/upload_format_contract.py' --fail-under=80` → `165 Stmts / 12 Miss / 93% Cover`，退出 0，≥80%。
- **pyright**：`0 errors, 0 warnings, 0 informations`，退出 0。
- **真实入口**：`python -m dayu.cli upload_material --help` / `upload_filing --help` 均退出 0（见对抗性检查 4）；真实 tool schema 构造断言全过（见对抗性检查 5）。
- **机器比对**：固定两句逐字/位置/连写、filing 四字段与 base 逐字一致、material 去句后与 base 逐字一致、无承诺片段（见对抗性检查 1-2、6）。

## Open Questions

- 无。

## Residual Risk

- **R1 / `UM-O20-F02`（已登记独立项，条件已触发，未解决）**：当前标准安装下完整 XBRL instance 转换能力待独立裁定（缺 `arelle-release` 为首因，taxonomy fetch 默认关闭、第三方 `memberQname=None` 未定根因）；filing `.xbrl` 限定缺口、独立 linkbase 边界、filing/material 术语不一致（filing「XBRL XML 候选 / Docling JSON 候选」vs material「XBRL 财报实例文档候选 / Docling 格式的 JSON 文档候选」）交 F02 对所有公开入口清算。本切片 filing 逐字未动，该不一致面是既有状态而非本次引入；**不得把 F01 文案修复理解为 F02 已解决**。
- **R2 / `UM-O20-E01`（证据缺口，未解决）**：Docling JSON 正样本 validated success 属 E01 记录环境（主工作区依赖）；本切片与本 review 均未做端到端上传/抽取准确率补证，XBRL 不得记 validated success；五份冻结负样本只证明输入不符声明子类型（R3），不构成能力结论。**不得把 F01 修复理解为 E01 已闭环**。
- **R-LLM-facing 术语（低）**：固定两句中「linkbase」为未短释领域词；措辞为用户裁决冻结文本，规则本身操作性清晰，术语一致性清算归 F02。
- **R-README 摘要漂移（低）**：根 README 新段为人工摘要（「后缀符合要求不保证文件内容转换成功」与 owner「后缀通过只表示具备转换资格，…」意译），语义忠实且以即时 CLI help 为权威指引，符合 plan 取舍；owner 文案未来变更时需人工同步。
- **R-叙述文案手工同步（既有模式，低）**：投影中「Docling 格式的 JSON 文档 / XBRL 财报实例文档」为叙述性描述，内部 format id（`JSON_DOCLING`/`XML_XBRL`）变更时需手工同步；filing 同模式既有，本切片未扩大其结构面。
- **R4/R5（plan 已接受）**：`upload_tool_files` 描述变长的少量 LLM token 增量；argparse 既有 CJK 折行上限（本次固定两句折行落空格处，语义连续可读）。
- **验证边界**：按 plan 范围复跑 7 个定向测试文件，未运行全仓测试套件；range 为单 commit（S1），O20-F01 计划仅此一个行为切片，无其它已提交切片遗漏；`docs/reviews/deepreview-20260929-o20-kimi.md` 未读、未核对。

## 项目指令（AGENTS.md）检查

- 分层与依赖：文案真源在 `dayu.fins`，CLI/tool 只消费投影，batch 只消费 capability；无反向依赖、无跨层穿透、无胶水 seam。符合。
- 语义所有权：格式说明唯一 owner 一处生成、多处复用；测试断言 owner 级 contract。符合。
- LLM-facing 约束：新增文本业务可读、自足、非承诺；无内部治理标识暴露（linkbase 术语见残余）。符合。
- schema 变更：仅 tool schema 描述文本，无持久化 schema/枚举/必填性变化，不触发起库迁移条款。符合。
- 测试与验证：定向回归 779 passed、被改生产单文件覆盖 93%（≥80%）、pyright 干净、真实 CLI help 与真实 tool schema 核验。符合。
- README 触发：根 README 已按触发规则与读者职责更新；其余 README 经职责判定无需改。符合。

## 结论

**pass-with-risks**。UM-O20-F01 S1（本 range 唯一行为切片）与 goal/accepted plan/裁决逐字对齐：固定两句在唯一文案 owner 处一次插入（逐字、连写、位置正确），filing 与 capability 不漂，CLI/tool 同源消费、batch 仅复用 capability 后缀准入，LLM-facing 非承诺自足，测试三层闭环且未弱化，覆盖率/pyright/真实入口全部独立复跑通过，diff 白名单吻合。**无未修复 finding**。残余风险均已登记分类：F02（XBRL 运行能力与术语清算）与 E01（正样本补证）为独立未解决项，不得计为 F01 已解决；其余为已接受低风险或人工同步项。可按 gateflow 汇合双路结果进入总控裁决。
