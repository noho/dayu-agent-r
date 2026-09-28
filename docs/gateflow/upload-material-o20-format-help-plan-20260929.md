# UM-O20-F01：material 格式说明与共享 capability 同源实施计划

- Gate：plan → plan review → fix；原候选 label：`o20-plan-sol-20260929-01`；本次按 MiMo review 与总控裁决修订，待双路 plan re-review。
- 原候选 RUNTIME/PROVIDER/MODEL：`codex/gpt-6-sol/gpt-6-sol-a5354581`；本次 fix：`codex/gpt-6-sol/gpt-6-sol`。
- 工作区：`/private/tmp/dayu-upload-o20`；分支：`codex/upload-material-o20`；检查时 HEAD：`8d8d494fbbce0052372fb1b42097c9f7222cfa28`。
- 输入：本工作区 `AGENTS.md`、已确认 goal `docs/gateflow/upload-material-o20-format-help-goal-20260929.md`、MiMo review `docs/reviews/plan-review-20260929-014020.md`、总控裁决 `docs/gateflow/upload-material-o20-plan-review-adjudication-20260929.md`、主工作区只读 oracle 裁决 `docs/reviews/upload-material-um-o20-oracle-adjudication.md`、只读 E01 `docs/gateflow/upload-material-o20-e01-evidence-20260929.md` 与下列本 HEAD owner 代码。goal、review、裁决及 E01 均不得在本次 fix 改写。
- 当前裁决：goal confirmation=pass；MiMo plan review=fail，Kimi 尚无有效审查。本次仅修订候选 plan；下一 gate 为双路 plan re-review，未通过前不进入 implementation。

## 目标、动机与直接证据

目标是让 material 的 `--files` 和上传工具 `files.description` 从同一 Fins 投影说明：`.json` 仅是 **Docling 格式的 JSON 文档候选**，`.xml/.xbrl` 仅是 **XBRL 财报实例文档候选**；后缀匹配只给出尝试转换的资格，不保证文件内容转换成功。保持现有后缀集合、角色规则和转换流程。成功信号是同一段 material 规则出现在真实 CLI help 与真实构造的 tool schema，batch 继续只按同一 capability 作后缀准入且无独立格式文案，filing 文案逐字不变，相关回归、pyright 和被改生产单文件覆盖率达到项目门槛。

动机成立，但 F01 严重性限于公开说明。`dayu/documents/docling_runtime.py:222-234` 的产品 capability 将 `.xbrl/.xml` 归入 `XML_XBRL`、`.json` 归入 `JSON_DOCLING`。`dayu/fins/upload_format_contract.py:617-630` 的 filing 文案已提示 `.xml`、`.json` 的部分子类型限制，而 material 文案只列扩展名、逐个转换和不保证成功；两者对同一 converter 能力给出不等量信息。`upload_format_contract.py:631-645` 将 `material_files` 原样合入 `upload_tool_files`。本 HEAD 上真实 `python -m dayu.cli upload_material --help` 的 `--files` 段确实没有 Docling JSON/XBRL instance 说明；真实构造的 tool schema `files.description` 等于 owner 投影，但其中 material 段也没有这些说明。因此 F01 根因在 Fins 文案投影。五份冻结负样本不能证明 converter 整体失效或本项目的抽取准确率；E01 的正样本和 XBRL 失败须按各自环境与直接证据解释。

主工作区只读 E01 在**同一 HEAD、主工作区 Python 3.11.15 venv 依赖**下，已用真实 CLI 验证合规 Docling JSON 上传并发布成功，可记为该环境的 validated success，不能外推到任意 JSON、其它依赖版本或抽取准确率。完整 XBRL instance 在当前标准安装真实 CLI 失败，`stored_files=0`；同一输入的直接 Docling 诊断表明首因是缺 `arelle-release`。隔离叠加可解析的 2.44.8 后，默认 taxonomy fetch 仍关闭；进一步只启本地 fetch 的第三方试验遇到 `memberQname=None` 异常，尚不能判定是缺远程 taxonomy 还是独立后端缺陷。E01 未完成项目另列于残余风险。这些事实说明 F02 条件**已触发**，但没有改变 F01 的文案 owner 和已确认范围。

语义 owner 分工：`dayu.documents.docling_runtime.DOCLING_CONVERTER_CAPABILITY` 唯一定义产品 converter 格式和扩展名；`dayu.fins.upload_format_contract.project_fins_upload_format_text` 唯一负责 Fins 角色化、用户及 LLM 可读的格式说明。CLI 的 `dayu/cli/arg_parsing.py:963` 直接读取 `material_files`；工具的 `dayu/fins/tools/upload_tools.py:241` 直接读取 `upload_tool_files`。`dayu/fins/upload_batch.py:418` 只调用相同 Fins capability 的 `accepts_primary` 做后缀准入，没有另一份 material 格式帮助规则；SEC/CN workflow 和 `DoclingUploadService` 消费 `FinsUploadMaterialFiles`，不是文案 owner。无证据支持给 CLI、tool、batch 分别添加字符串或内容探测。

## 唯一行为切片：补足 material 候选子类型说明

**Slice F01-S1；目标/验收对齐：**仅解决上述 material 说明缺口；一次投影改动同时服务 CLI 与 tool。实现前再次确认 HEAD 与基线一致，且 `git status --short` 未出现他人改动。如果不同，停止并重做本 HEAD 证据核对。

**严格允许修改的生产文件：**`dayu/fins/upload_format_contract.py`，只在 `project_fins_upload_format_text` 的 `material_files` 构造处补文案。保留 `FINS_UPLOAD_FORMAT_CAPABILITY`、`DoclingConverterCapability`、所有 suffix/format id、`require_material_path`、文件选择、失败分类、转换与存储逻辑原样。无需新 public API、schema 字段、状态机或数据库迁移；tool schema **描述文本**会变，参数类型、枚举、必填性均不变。

**固定文案与复用位置：**沿用函数中 `suffixes = ", ".join(capability.primary_suffixes)` 的有序列表，不另建后缀清单。`material_files` 现有“后缀通过只表示具备转换资格，不保证文件内容转换成功。”之后、现有“delete 不得提供文件。”之前，**必须逐字插入**以下两句（连写，不插入额外空格）：

> `.json` 仅是 Docling 格式的 JSON 文档候选，不代表任意 JSON 内容可转换。`.xml/.xbrl` 仅是 XBRL 财报实例文档候选，不代表任意 XML 或独立 linkbase 文件可转换。

由此 `material_files` 的最终形式必须是现有首句 + 有序 `suffixes` 句 + 现有转换资格警示句 + 上述两句 + 现有 delete 句，现有文字均逐字保留。新增说明只界定候选内容类型，不声称有效输入或任一部署一定成功；环境失败归因属于 F02。`filing_files` 按 goal 保持现有文本和角色说明**逐字不变**，不把其表述完备性或准确性作为本切片承诺；material 文案由本函数中的 `material_files` **一次生成**，再由 `upload_tool_files` 组合复用，无须在 CLI、tool schema 或 batch 复制。不得写成“普通 JSON/XML 可转换”“linkbase 可独立转换”“有效 Docling JSON/XBRL instance 已在当前产品环境验证成功”或“项目保证抽取准确率”。不通过扩展名猜文件内容，不在下游补 fallback。

**严格允许修改的测试文件：**`tests/fins/test_upload_format_contract.py`、`tests/cli/test_arg_parsing.py`、`tests/fins/test_fins_ingestion_tools.py`。owner 测试更新 `expected_material_text`，按上述最终拼接形式**逐字断言**固定两句与插入位置、现有转换资格警示、suffix 顺序和 `upload_tool_files` 完整复用；filing 预期保持不变。CLI parser/help 测试既断言 `files_action.help` 同源，也捕获格式化后的真正 help 并以同一期望文本断言新增文字按顺序可见。工具测试从 `build_fins_upload_tool(...).schema.function.parameters.properties["files"]["description"]` 断言 material 子段与同一期望串一致，且整体等于 `FINS_UPLOAD_FORMAT_TEXT.upload_tool_files`；现有 filing、`primary`、`maxItems` 断言不变。测试不得把普通 JSON/XML/linkbase 伪装为正样本，也不得只以 mock 文案代替真实 parser/schema 输出。

**只读回归范围：**`tests/fins/test_upload_batch.py`、`tests/fins/test_sec_pipeline_upload_material_stream.py`、`tests/fins/test_cn_pipeline.py`、`tests/fins/test_docling_upload_service.py`。batch 继续按同一 capability 过滤 suffix；无需修改其 code/test，也不把 batch 的 `unsupported_suffix` 提示扩成内容类型诊断。若这些消费者实际存在另一份独立 material 内容格式规则，触发下文停止条件。

**完成信号：**owner、CLI、tool 测试均从唯一投影验证相同 material 语义；真实 CLI `--help` 与真实工具 schema 语义连续可读且相符；batch 入口仅复用同一 capability 进行后缀准入，本无独立内容格式文案，故没有词义漂移面；格式集合与 filing 文案、角色规则逐字不变。只有一个可验证行为增量，不按模块机械拆 gate，也不加入新的解析器或依赖治理，因而没有扩大已确认 goal。

## 验证顺序与预期断言

1. 环境前提：本临时 checkout **没有** `.venv`。实施 gate 在本 checkout 按根 README §1.1 的锁定安装执行 `python3.11 -m venv .venv`、`source .venv/bin/activate`、`python -m pip install -e ".[test,dev,browser]" -c constraints/lock-macos-arm64-py311.txt`（本机 `Darwin arm64`；换平台时使用 README 对应的 `lock-<平台>-py311.txt`）。记录 Python、约束文件及实际安装来源；不可将此前**主工作区 venv + 本 checkout PYTHONPATH** 的基线观察混作本地 `.venv` 实施验证，也不可将 E01 的主工作区依赖环境成功外推到本地环境。若锁定环境不可得，记录 validation blocked，不能宣称测试/pyright pass；不得自由升级依赖求通过。
2. 定向回归：`python -m pytest -q tests/fins/test_upload_format_contract.py tests/cli/test_arg_parsing.py tests/fins/test_fins_ingestion_tools.py tests/fins/test_upload_batch.py tests/fins/test_sec_pipeline_upload_material_stream.py tests/fins/test_cn_pipeline.py tests/fins/test_docling_upload_service.py`。预期 owner、真实 parser help、真实 tool schema、batch capability 准入及 SEC/CN/Docling material 消费回归通过。若完整测试文件有无关外部依赖失败，保留失败并定位，不能以选择性通过替代整文件结果。
3. 单文件覆盖率采用 `tests/README.md` 的 coverage run/report 口径，在同一本地 `.venv` 顺序执行：`coverage erase`；`coverage run -m pytest -q tests/fins/test_upload_format_contract.py tests/cli/test_arg_parsing.py tests/fins/test_fins_ingestion_tools.py tests/fins/test_upload_batch.py tests/fins/test_sec_pipeline_upload_material_stream.py tests/fins/test_cn_pipeline.py tests/fins/test_docling_upload_service.py`；`coverage report --include='dayu/fins/upload_format_contract.py' --fail-under=80`。报告中只记录这套命令所得的被改生产单文件实际比例（目标 ≥80%），不得混入 pytest-cov 数字、改配置或排除行掩盖缺口。
4. 类型：`pyright`（激活本地 `.venv` 后），记录完整结果并确认无新增/扩散报错；触及既有报错时按 AGENTS.md 处理。
5. 真实入口：`python -m dayu.cli upload_material --help` 与 `python -m dayu.cli upload_filing --help`，检查前者 `--files` 的固定两句及后缀警示在现有 argparse 排版上限内语义连续可读，后者 filing 文案逐字不变。另以本 checkout 的 Python import 调用 `DefaultFinsRuntime.create(workspace_root=<隔离临时目录>).get_ingestion_runtime()` 和 `build_fins_upload_tool(runtime)`，从真实 `schema.function.parameters.properties["files"]["description"]` 读取结果；断言其等于 `FINS_UPLOAD_FORMAT_TEXT.upload_tool_files`，且 **material 子段**含固定两句及不保证转换成功。若帮助文本语义确实读不清，只能在已批准固定文案边界内提出断句调整并重新复审；不得擅改 formatter 或文案实质。不要用仅 grep 源码或冻结样本代替此核验。
6. 最后复查 `git diff --check`、HEAD、`git status --short` 与变更文件清单，仅允许本 slice 文件和按下文职责确需的 README；本轮 plan 阶段不运行上述实施验收并不声称 pass。

## README 决策与文件边界

根 `README.md` 是最终用户手册，现有上传章节已有 `upload_material` 示例与 help 指引，且说明了 filing 的 `.xml/.json` 部分限制。此项改变用户可见 CLI 文案并关系 material 输入选择，命中根 README 触发且属于读者职责；实施时允许在上传章节补一段简短的 **material** 候选子类型/后缀非保证说明，格式清单仍指向即时 CLI help，不复制完整清单或宣称端到端成功。修改前复核其 `Agent更新约束` 与当前 CLI 输出，保留既有 filing 段逐字不变；该段的完备性不属于 F01 验收承诺。

`dayu/fins/README.md` 已将 immutable capability 与 Fins 文案 owner、CLI/schema 同源关系写明（约第 67、384 行）；具体帮助句变化不改变开发者稳定架构，按其读者约束无需改。`tests/README.md` 现有 owner/CLI/tool/batch 覆盖说明（约第 473 行）仍成立且未新增测试层级，按其职责无需改。`dayu/README.md`、`dayu/config/README.md`、`dayu/host/README.md`、`dayu/engine/README.md` 均无对应触发。故实施 gate 的**完整写入白名单**仅为上述一个生产文件、三个测试文件及根 `README.md`；若根 README 复核发现现有文字已经完整覆盖 material 行为，可在实施记录中说明而不机械编辑。当前 plan gate 的写入白名单仅为本文件。

## 停止条件、隔离事项与残余风险

- HEAD 不再是 `8d8d494fbbce0052372fb1b42097c9f7222cfa28`，或文案真正 owner 并非上述共享投影：停止修改，记录新 HEAD、代码引用与问题，不沿旧计划推进。
- CLI/tool/batch/其它消费者存在独立且相矛盾的 material 内容规则，必须扩大 goal 才能一致：停止并给出具体调用点；不在下游写特例。
- E01 已证明当前标准安装的完整 XBRL instance 失败并触发独立 F02；这**本身不触发 F01 停止**，因为已确认的 F01 只提供候选资格、不保证转换的文案。若要准确写出本次固定文案**必须先改变** `dayu/documents/docling_runtime.py` 的 capability、Docling 装配或部署依赖，则停止 F01，提供直接环境/代码证据并请求重新裁定；不得在 F01 顺手实施 F02。
- 若新文案只能通过“有效内容必成功”的承诺表达，则停止并重拟非承诺式说明；不能把第三方解析能力或抽取质量归本项目保证。

残余风险按总控裁决登记：

- **R1 → 独立 `UM-O20-F02`，条件已触发**：本 HEAD 当前标准安装的完整 XBRL instance 失败，缺 `arelle-release` 为直接首因；隔离叠加 2.44.8 后仍受 taxonomy fetch 默认关闭阻断，仅启本地 fetch 的第三方试验又遇 `memberQname=None`，该异常的唯一根因尚未判定。F02 独立裁定可解析依赖版本上限、taxonomy 获取策略、输入/文件隔离与 capability 同源，或统一撤回所有公开入口的 `XML_XBRL` 承诺；F01 不装依赖、不删 capability、不改 failure code。filing `.xbrl` 限定缺口、独立 linkbase 边界及 filing/material 的 `XBRL XML`/`XBRL 财报实例文档` 术语一致性，也交 F02 对所有公开入口清算；本次 filing 原文保持不动，不承诺其完备准确。
- **R2 → `UM-O20-E01` 剩余补证**：同一 HEAD/所记录依赖环境下 Docling JSON 已有 validated success，但装可选依赖后的产品路径 XBRL 正样本复测、taxonomy 网络/本地配置快照、SQLite/durable/process 证据及负样本复跑尚未完成；当前 XBRL 不得记 validated success。
- **R3 → 保留历史解释边界**：五份冻结负样本只证明输入不符声明子类型，不代表本 HEAD 正样本验证，也不能推出格式总体失败。
- **R4 → 接受的低风险**：`upload_tool_files` 组合描述变长，LLM token 占用略增，但 schema 参数类型、枚举与必填性不变。
- **R5 → 接受的低风险**：argparse 的 CJK 折行存在既有上限；只验收真实 help 的语义连续可读，不扩大到 formatter 修复。

## 原候选基线与本次 fix 静态核对

- 原候选生成时，`git branch --show-current` → `codex/upload-material-o20`；`git rev-parse HEAD` 两次均为上述 40 位 SHA；当时写计划前 `git status --short` 仅显示未跟踪的 goal 文档。本次 fix 开始时同一 HEAD，另有未跟踪的 plan、MiMo review 与总控裁决；本次只写 plan。
- 阅读了两份指定源代码、CLI parser `dayu/cli/arg_parsing.py`、tool `dayu/fins/tools/upload_tools.py`、batch `dayu/fins/upload_batch.py`、SEC/CN material selection 调用点及三处对应测试；`rg` 的 `FINS_UPLOAD_FORMAT_TEXT` 引用显示 CLI/tool 直接消费同一投影，batch 消费 `FINS_UPLOAD_FORMAT_CAPABILITY.accepts_primary`。
- 此 checkout `ls -ld .venv` 返回不存在。基线只读实际入口使用主工作区虚拟环境解释器，但设置 `PYTHONPATH="$PWD"`、`PYTHONDONTWRITEBYTECODE=1`，命令为 `python -m dayu.cli upload_material --help`；退出码 `0`，当前 `--files` 显示有序 suffix、逐个转换和“不保证文件内容转换成功”，没有 Docling JSON/XBRL instance 子类型。解释器依赖来自主工作区，代码 import 指向当前 checkout；这不是本地 `.venv` 验证，更不是转换补证。
- 同一解释器在本 checkout 调用 `DefaultFinsRuntime.create(...).get_ingestion_runtime()` 与 `build_fins_upload_tool(...)` 构造真实 schema；输出 `schema_equals_owner=True`、`material_has_json_subtype=False`、`material_has_xbrl_subtype=False`。只检查 schema 描述；没有上传文件、运行转换、修改主工作区或运行测试/pyright。
- 原计划的上述 CLI/schema 观察是主工作区 venv 基线，不是本地 `.venv` 验收；E01 后续事实及 MiMo review/总控裁决已在本次修订吸收，历史观察不得冒充本次重新执行。
- 本次 fix 的下一 entry point 是 **双路 plan re-review**；Kimi 尚无有效 plan review 结果，未完成双路复审前不得进入 implementation。

## 实施完成报告格式

报告实际改动文件和 material 固定文案、CLI help/tool schema 的真实输出断言、batch 与 SEC/CN/Docling 回归结果、`upload_format_contract.py` 在本地 `.venv` 的 coverage run/report 单文件覆盖率、pyright、README 取舍及 E01/F02 风险；逐项标记 pass/fail/blocked，区分此前主工作区 venv 基线观察、E01 隔离证据与本地 `.venv` 实施验证。

原候选 CANARY=gpt-6-sol-a5354581
