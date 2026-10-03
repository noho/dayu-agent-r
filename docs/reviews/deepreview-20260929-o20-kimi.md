# Deep Review — UM-O20-F01 全切片 aggregate gate（Kimi 独立审查）

- RUNTIME/PROVIDER/MODEL: claude/kimi/kimi-k3[1m]
- CANARY=kimi-205a7ff1
- Review 时间：2026-09-29（本机系统时钟）
- Gate：`$deepreview` aggregate（S1 accepted commit 之后的全切片审查）
- Work unit：`UM-O20-F01`（material 格式说明与共享 capability 同源），Slice F01-S1 已提交。

## Scope

- Mode: committed range review
- Branch: `codex/upload-material-o20`
- Range: `8c9e1d3473e5fd9c8e4509a38539a1a940140070..7870e84a`（恰含 S1 accepted commit `7870e84a` 一个提交）
- HEAD 核验：`git rev-parse HEAD` = `7870e84a412cf79a7d3d4f20b9cc07997787abdd`，与 range 上界一致；其父提交为 range 下界 `8c9e1d34`；`git status --short` 为空。**range/HEAD 无漂移，未触发停止条件。**
- Output file: `docs/reviews/deepreview-20260929-o20-kimi.md`
- Included scope:
  - 治理链文档：goal `docs/gateflow/upload-material-o20-format-help-goal-20260929.md`、accepted plan `docs/gateflow/upload-material-o20-format-help-plan-20260929.md`、plan 裁决 `docs/gateflow/upload-material-o20-plan-review-adjudication-20260929.md`、实施记录 `docs/gateflow/upload-material-o20-s1-implementation-20260929.md`、S1 code review 裁决 `docs/gateflow/upload-material-o20-s1-code-review-adjudication-20260929.md`。
  - 双路 code review：`docs/reviews/code-review-20260929-o20-kimi.md`（pass）、`docs/reviews/code-review-20260929-o20-mimo.md`（pass-with-risks，无未修复 finding）；旧补充审查 `docs/reviews/code-review-20260929-030106.md`（同候选早期 MiMo 审查，裁决已定性为不代替双路）。
  - plan review 链抽验：MiMo 首轮 fail `plan-review-20260929-014020.md`、MiMo 复审 pass `plan-review-20260929-020447.md`、Kimi 复审 pass `plan-review-20260929-023440.md`（canary `kimi-7806732a`）。
  - 切片分类注册：`docs/gateflow/upload-material-issue-198-repair-sequence-20260928.md`（F01=共享 capability 公开说明；F02 条件项，前置 E01）。
  - 生产/测试/README diff 与消费链：`dayu/fins/upload_format_contract.py`、`dayu/cli/arg_parsing.py:963`、`dayu/fins/tools/upload_tools.py:241,247,392`、`dayu/fins/upload_batch.py:418`、`dayu/fins/ingestion_runtime.py:1320`、`dayu/documents/docling_runtime.py:222-234`、根 `README.md` 及其 `Agent更新约束`、`dayu/fins/README.md`、`tests/README.md`。
  - 本 checkout 本地 `.venv` 独立重跑：7 文件回归、单文件 coverage、pyright、真实 CLI help、真实 tool schema 构造。
- Excluded scope:
  - MiMo 同轮 deepreview：本 gate 不存在该 artifact（`docs/reviews` 无 `deepreview-20260929-o20-mimo*`），无可读对象，本审查全部结论由本 reviewer 独立重跑得出，未采信 Sol 实施自述与既有 review 结论。
  - F02 XBRL 运行能力与 E01 正样本证据：已分类独立项，本 review 只核对 F01 是否越界暗示，不复核其环境结论。
  - 转换、后缀准入、失败分类、仓储等非目标代码：仅走读与文案 owner 的接壤面。
- Parallel review coverage: 无（任务禁止派发子 Agent；全部走读与验证由本 reviewer 自行完成）。

## 治理链一致性核对（独立抽验，非采信自述）

1. goal confirmation=pass，动机由当前代码事实成立：共享 converter capability（`docling_runtime.py:222-234`，`.xbrl/.xml→XML_XBRL`、`.json→JSON_DOCLING`）对 filing/material 公开说明信息量不等；严重性限于公开文案。
2. plan 经 MiMo 首轮 fail → 修订 → MiMo/Kimi 双路复审 pass → 总控裁决 plan gate pass；固定两句在 plan 引用块与裁决中逐字一致。本 reviewer 程序化提取 plan 引用块（去 markdown 反引号）与生产运行时文本比对：`plan_quote_equals_fixed: True`。
3. Sol 实施派发按协议 `agent_status=failed`，实施记录仅作候选陈述；双路 code review 已用各自独立重跑取代其自述证据，本 reviewer 再次独立重跑（见下），三方结果一致。
4. S1 code review 裁决：Kimi pass、MiMo pass-with-risks 且**无未修复 finding**，总控判 gate pass，随后 accepted commit `7870e84a`。治理链完整，无跳 gate。

## 独立验证证据（本 reviewer 在本 checkout `.venv` 亲自执行）

venv 身份：`python 3.11.15`，`sys.executable=/private/tmp/dayu-upload-o20/.venv/bin/python`，`dayu.__file__=/private/tmp/dayu-upload-o20/dayu/__init__.py`，未借用主工作区解释器。

| 验证 | 命令/方法 | 结果 |
| --- | --- | --- |
| 固定两句逐字与位置 | 程序化比对 plan 引用块 vs `FINS_UPLOAD_FORMAT_TEXT.material_files` | 逐字相等；在 material 中**恰好 1 次**；位置 `后缀警示句 < 句一 < 句二 < delete 句`；与警示句**连写无额外空格**；不出现在 filing |
| filing 不变 | 提取父提交与当前 `filing_files` 源码块字节比对 | `filing_unchanged_head: True`（生产 diff 唯一 hunk 只触及 `material_files`，`upload_format_contract.py:626-633`） |
| capability 不变 | range diff 文件清单 + `docling_runtime.py:222-234` 走读 | diff 未触及 `dayu/documents/`；`XML_XBRL=(.xbrl,.xml)`、`JSON_DOCLING=(.json)` 原样 |
| 唯一 owner / 无第二份文案 | 全仓 `rg "转换资格\|不保证文件内容转换成功\|仅是 Docling\|仅是 XBRL\|Docling 格式的 JSON\|XBRL 财报实例"` | 生产代码仅命中 `upload_format_contract.py`（filing 2 处 + material 3 处）；测试仅命中被改 3 文件 |
| 消费链同源 | `rg FINS_UPLOAD_FORMAT_TEXT/FINS_UPLOAD_FORMAT_CAPABILITY` | CLI `arg_parsing.py:963` 直接消费 `material_files`；tool `upload_tools.py:241` 消费 `upload_tool_files`（material 一次生成、组合复用）；batch `upload_batch.py:418` 仅 `accepts_primary` 后缀准入（拒绝原因 typed `unsupported_suffix`）；`ingestion_runtime.py:1320` 仅 `require_filing_path`。无下游 fallback/特例/重算 |
| 定向回归 | `pytest -q` plan 指定 7 文件 | `779 passed, 3 warnings in 12.33s`，退出 0；警告均来自 edgartools 废弃 API，与本切片无关 |
| 单文件覆盖率 | `coverage erase` → 同 7 文件 `coverage run -m pytest -q` → `coverage report --include='dayu/fins/upload_format_contract.py' --fail-under=80` | `165 Stmts / 12 Miss / 93% Cover`，退出 0，≥80% |
| pyright | 激活 `.venv` 后 `pyright` | `0 errors, 0 warnings, 0 informations`，退出 0 |
| 真实 CLI help | `python -m dayu.cli upload_material --help` / `upload_filing --help` | material `--files` 段含有序后缀（与 capability 顺序一致）、转换资格警示、固定两句、delete 规则；argparse 折行只落在既有空格处（`成功。.json 仅是 / Docling 格式的…`、`delete / 不得提供文件。`），语义连续可读；filing `--files` 段逐字保持原文案 |
| 真实 tool schema | 隔离临时目录 `DefaultFinsRuntime.create(workspace_root=Path(...)).get_ingestion_runtime()` + `build_fins_upload_tool(runtime)` | `files.description == FINS_UPLOAD_FORMAT_TEXT.upload_tool_files` 为 `True`；`upload_kind=material 时，{material_files}` 逐字内嵌；固定两句在 description 中恰好 1 次；`files.type=array`、`maxItems=100`；`required=['ticker','upload_kind']` 不变 |
| diff 白名单与空白 | `git diff --name-only 8c9e1d34..7870e84a -- dayu/`；`git diff --check` | `dayu/` 下仅 `upload_format_contract.py`；range 全量恰为 plan 白名单（1 生产 + 3 测试 + 根 README）加 gate 文档/双路 review artifact；`--check` 退出 0 |

## 对抗性检查（已证伪的攻击面，非 finding）

1. **跨切片遗漏**：`FINS_UPLOAD_FORMAT_TEXT` 生产消费点恰为 CLI 3 处 + tool 3 处；`FINS_UPLOAD_FORMAT_CAPABILITY` 消费点为 batch/ingestion_runtime 的后缀准入。`dayu/ui`、`dayu/service`、`dayu/host`、`dayu/engine`、`dayu/config` 无 material 格式文案；SEC/CN workflow 与 `DoclingUploadService` 消费 typed selection 而非文案，已由回归文件覆盖。`upload_filings_from` batch 入口 help 不内嵌格式文案，无第三份说明可漂移。
2. **semantic ownership drift**：文案语义唯一 owner 仍是 `project_fins_upload_format_text`；格式真源仍是 `DOCLING_CONVERTER_CAPABILITY`。本次改动只在 owner 的 `material_files` 构造处一次投影，CLI/tool/batch 继续复用同一投影/capability，未产生第二真源、未把显示语义与持久化语义拆分。
3. **过度耦合**：三入口对 owner 的依赖是稳定的公共投影/typed capability，无字符串协议外传；测试断言 owner 级 contract（owner 全文逐字相等、真实 parser help 归一后整段+有序片段、真实 schema 整体等于投影），未固化偶然行为，未出现要求多处同步的隐性耦合。
4. **adversarial failure——"承诺有效输入必成功"**：固定两句为"仅是…候选，不代表任意…可转换"非承诺句式，前接"后缀通过只表示具备转换资格，不保证文件内容转换成功"；未声称 XBRL/Docling JSON 在当前部署验证成功，未把第三方抽取准确率归本项目。停止条件 4（只能以承诺式文案表达）未触发。
5. **adversarial failure——F02 偷渡**：range diff 无依赖、装配、converter、capability、failure code、仓储改动；`rg arelle` 方向未被动过。F02/E01 边界完好。
6. **既有措辞并置观察（非本次引入）**：material 首句"并逐个实际转换成功"是处理要求（逐个执行转换、失败即上传失败），与后文"不保证文件内容转换成功"（后缀/子类型命中不预先保证结果）语义不同层；该并置先于 F01 存在，本次未改动这些句子。
7. **README 职责**：根 README `Agent更新约束` 定位为最终用户手册；新增 4 行位于上传章节、material 范围明确、明示后缀清单以即时 CLI help 为准、未宣称端到端成功，命中"用户可见 CLI 文案"触发且属其读者职责；既有 filing 段逐字未动。`dayu/fins/README.md:384` 与 `tests/README.md:205-207` 只陈述 owner/同源架构与覆盖口径，不引用会过时的逐字 material 句子，"无需修改"判断成立。
8. **LLM-facing 自足性**：新增文本为业务可读自足语义，无内部类型名/模块名/治理标识；"Docling"与既有用户可见文案（filing 段、README"Docling 转换"）一致。

## F02/E01 边界声明（必须不被误读）

- `UM-O20-F02`（XBRL 运行能力）：当前标准安装下完整 XBRL instance 端到端失败（首因缺 `arelle-release`；叠加可解析版本后 taxonomy fetch 默认关闭；仅启本地 fetch 的第三方试验遇 `memberQname=None`，根因未裁决）。**F01 未解决、未声称解决该项**；本切片只提供候选资格文案，不改 capability/依赖/转换器。
- `UM-O20-E01`（正样本证据）：Docling JSON 的 validated success 属主工作区所记录环境，不能外推；XBRL 不得记 validated success。**F01 未做、未声称做过端到端补证**。
- 切片注册直接证据：`docs/gateflow/upload-material-issue-198-repair-sequence-20260928.md:15`（`UM-O20-F01`=共享 capability 的公开说明）、`:17`（`UM-O20-F02` 条件项，前置 `UM-O20-E01`）。

## Findings

未发现实质性问题。双路 code review 亦无未修复 finding，本 reviewer 独立重跑结果与之一致。

## Open Questions

- 无。

## Residual Risk

- **R-F02（独立项，条件已触发，不阻塞 F01）**：XBRL instance 运行能力待独立裁定；filing 文案缺 `.xbrl` 限定、filing「XBRL XML 候选 / Docling JSON 候选」与 material「XBRL 财报实例文档候选 / Docling 格式的 JSON 文档候选」术语不一致，已登记由 F02 对所有公开入口清算。该不一致面是既有状态，非本次引入；本次 filing 逐字未动符合 goal/裁决。
- **R-E01（独立项）**：Docling JSON 正样本结论的记录环境边界与 XBRL 补证缺口同上，留 E01。
- **R3（已登记）**：五份冻结负样本只证明输入不符声明子类型，不构成本次能力结论。
- **R4/R5（已接受低风险）**：tool schema 描述变长的少量 LLM token 增量（schema 参数类型/枚举/必填性不变）；argparse 既有 CJK 折行上限（真实 help 已验证语义连续可读，formatter 修复不在本切片）。
- **R-README 转述（低）**：根 README 新段为人工简述（「后缀符合要求不保证文件内容转换成功」对 owner「后缀通过只表示具备转换资格…」的等价意译），plan 明确授权简述且该段指向即时 help 为权威；owner 文案未来变更时需人工同步。
- **R-叙述文案与 format id 手工同步（低，既有模式）**：投影以叙述文字描述 `JSON_DOCLING`/`XML_XBRL` 能力，format id 变更需手工同步文案；filing 文案同模式既有，本次 material 新增同类叙述使该同步面略有扩大，但模式与 owner 边界未变。
- **验证边界**：按 plan 范围重跑 7 个定向测试文件 + 全仓 pyright；未运行全仓 pytest（plan 未要求）。

## 结论

**pass**。UM-O20-F01 全切片（goal → plan → 双路 plan review → 裁决 → 实施 → 双路 code review → 裁决 → accepted commit）治理链完整；当前提交 `7870e84a` 的实际 diff 与 accepted plan 白名单及固定两句逐字对齐；格式说明唯一 owner、CLI/tool/batch 同源消费、filing 与 capability 不漂、LLM-facing 自足、根 README 职责合规均经本 reviewer 在当前 HEAD 独立反证；7 文件回归 779 passed、单文件 coverage 93%、pyright 0、真实 CLI help 与真实 tool schema 均在本 checkout 本地 `.venv` 复跑通过。F02 XBRL 运行能力与 E01 正样本证据为已分类独立项，本切片未解决也未声称解决。无未修复 finding，残余风险均已登记。可进入 gateflow 下一 gate。
