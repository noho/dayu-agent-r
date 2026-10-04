# Plan Re-Review：UM-O17-F01 material form canonical 实施计划 PR5 修订版（Kimi 独立 adversarial 复审）

RUNTIME/PROVIDER/MODEL: codex/kimi/gpt-5-codex

CANARY=kimi-0704836b

- 审查对象：`docs/gateflow/upload-material-o17-form-plan-20260929.md`，SHA-256 `7b37c7279183bf56af2acfe722062f4b768a1f2e868eb96db37721d2578dbe24`（本 checkout 以 `shasum -a 256` 按文件字节独立核验，与任务锁定值一致）。基线 HEAD `8d8d494fbbce0052372fb1b42097c9f7222cfa28`，分支 `codex/upload-material-o17`；`git status --porcelain` 实证工作树仅含未跟踪 gateflow/review 文档，无产品改动。
- 工作区：`/private/tmp/dayu-upload-o17`（隔离 checkout）。复审本机时间 2026-09-29 18:09 CST（`date` 实测）。
- 审查方式：planreview 独立 adversarial 复审；全程只读代码、冻结证据与文档；唯一新增文件为本 artifact；不修改 plan/goal/产品/测试/README/旧 review/裁决；不实施 O17/O09/O05；不安装依赖；不 commit/push/PR/merge；不派发子 Agent。
- 文件名使用任务指定的固定名 `plan-review-o17-pr5-kimi-20260929.md`，覆盖 planreview skill 的通用 timestamp 命名建议（沿用 PR4 Kimi 先例）；未另行生成 timestamp artifact。
- 审查重点（任务指定）：反证 form 唯一函数在 batch override、filename routing、CLI `--material-forms` 解析、生成 `--forms` 与 runner request 的同源；特别检查 `_normalized_text_tuple` 当前会 strip，计划的 raw 候选保留能否保持空值/多值错误时点；兼审 O09 before-seed、PR4-F2 事件/result、O05 缺失值、历史 raw、逐文件 coverage 和 README。
- 依据文档：
  - Goal Confirmation（binding scope contract）：`docs/gateflow/upload-material-o17-form-goal-20260929.md`。
  - 总控裁决：`docs/gateflow/upload-material-o17-plan-review-adjudication-20260929.md`（含 PR5-F1 accepted/未修复记录与 Sol PR5 候选核验结论；裁决明示「实施时须验证 `_normalized_text_tuple` 当前会 strip，不可调用该函数后声称返回原始空白；plan 已明确改为保留原始候选，review 应查其可实现性」）。
  - Sol PR5 修复记录：`docs/gateflow/upload-material-o17-plan-fix-pr5-20260929.md`；Sol PR4 修复记录：`docs/gateflow/upload-material-o17-plan-fix-pr4-20260929.md`。
  - 前轮同 SHA 族 review：Kimi PR4（SHA `7c818f9d...`）`docs/reviews/plan-review-o17-pr4-kimi-20260929.md`、MiMo PR4 `docs/reviews/plan-review-o17-pr4-mimo-20260929.md`（Finding 01 即 PR5-F1 来源）、MiMo 第三轮（SHA `37d1c13e...`）`docs/reviews/plan-review-o17-rereview3-mimo-20260929.md`。
  - O09 用户裁决（本 checkout 存在）：`docs/reviews/upload-material-um-o09-oracle-adjudication.md`。
  - O17 用户裁决（本 checkout 缺失，`ls` 实证 `No such file or directory`，与 plan 声明一致）：plan 自述以 goal 与冻结原始证据为边界，前轮 Kimi 已从主工作区只读核对内容支持 goal 引用；本轮不重复越区读取。
  - 本 checkout `AGENTS.md`、当前 HEAD 的 `dayu/fins` / `dayu/cli` 代码与 `tests/fins` / `tests/cli` 测试。
- 独立重证方式：不沿用前轮 Kimi/MiMo 结论，对 PR5 修订点与六项兼审点重新读当前 HEAD 代码（行号为本 HEAD 实读）。

## 停止条件裁决（先行结论）

逐条核对任务给定四个停止条件：

1. **SHA 不符**：不触发。`shasum -a 256` 实算与任务锁定值 `7b37c727...dbe24` 完全一致。
2. **batch 与 material canonical 仍双真源**：不触发。plan 白名单第 4/5 项把 batch `_validated_material_form` 的文本规范化改为复用唯一 `normalize_material_form_type`，封闭 routing 集合校验保留为 batch owner 的独立业务约束（非文本规范化）；filename routing table 三个字面值本身即 canonical 常量（`upload_batch.py:82-91`）；CLI `_single_batch_material_form` 删除独立 `.upper()`。文本规范化单真源成立；`_MATERIAL_FORM_TYPES` 是路由允许域而非第二套规范化规则，不构成同一事实的双真源。
3. **CLI raw 候选承诺不可执行**：不触发。`_single_batch_material_form` 可在不调用会 strip 的 `_normalized_text_tuple` 的前提下实现 raw 候选保留（本地 split/基数/空白判定或抽取 raw-split helper）；regeneration argv 经 `shlex.join`（`dayu/cli/upload_script.py:173`，Windows 侧 `_quote_windows_batch_argument` `:206`）正确 quoting，含两端空白的 raw 候选可存活脚本注释 round-trip。可执行性成立，实现精度见 Open Question 1/2。
4. **改变既定失败时序**：不触发（附一个实现陷阱，见 Open Question 1）。plan 明示 CLI 保留 `--material-forms` 逗号/重复值基数与空白错误（`CliFinsUsageError`、CLI 阶段），batch 保留空白/不支持值的 `UploadBatchPlanUsageError`（batch request 校验阶段，`upload_batch.py:270` 位于 source_dir 检查与文件扫描之前），admission 的 `None`/空白沿用现有下游边界。失败类型与阶段在 plan 文本中均有钉住。

## PR5-F1 专项核验：batch/CLI 同源链独立重证

任务要求反证「form 唯一函数在 batch override、filename routing、CLI `--material-forms` 解析、生成 `--forms` 与 runner request 的同源」。逐链落实读：

| 链环节 | 当前 HEAD 代码事实 | plan 修订后语义 | 同源判定 |
| --- | --- | --- | --- |
| batch override | `_validated_material_form`（`upload_batch.py:799-814`）：`None`→`None`；`value.strip().upper()`；不在 `_MATERIAL_FORM_TYPES` 抛 `UploadBatchPlanUsageError(f"unsupported material form: {value}")`（`:813`）；`cast(MaterialFormType, normalized)`（`:814`）。调用点 `:270`，位于 ticker/action/period 校验之后、source_dir 检查与目录扫描之前 | 复用唯一函数做文本规范化，封闭集合校验与错误分类、校验顺序保留 | **成立**（空白转换机制待钉，OQ2） |
| filename routing | `_MATERIAL_ROUTING_TABLE`（`:82-87`）三个 pattern → `FINANCIAL_STATEMENTS/EARNINGS_CALL/EARNINGS_PRESENTATION` 字面值；`_MATERIAL_FORM_TYPES`（`:88-91`）为派生 frozenset；`_match_material_form`（`:500-510`）首命中返回字面值 | 字面值已是 canonical，不增第二个文本规范化函数；允许域与路由优先级仍归 batch owner | **成立** |
| override 覆盖范围 | `generate_upload_batch_plan`（`:294-310`）：仅当 `_match_material_form` 命中时 override 才替代 routed 值进入 `_build_material_entry`；未命中走 filing 路径 | plan 表述「override 只覆盖已路由 material」与代码一致 | **成立** |
| typed entry | `UploadBatchMaterialEntry.form_type: MaterialFormType`（`:224`）；`MaterialFormType = Literal[三类别]`（`:23-27`） | typed entry 只存 canonical form | **成立** |
| CLI `--material-forms` 解析 | `_single_batch_material_form`（`fins.py:1193-1208`）：`_normalized_text_tuple(field_name="--material-forms")`（`:1203`，split 逗号、逐项 strip、空白抛 `CliFinsUsageError`）；>1 抛 `_MULTIPLE_BATCH_MATERIAL_FORMS_MESSAGE`（`:1204-1205`）；返回 `normalized[0].upper()`（`:1208`）。argparse 定义 `--material-forms nargs="+"`（`arg_parsing.py:998`），重复出现后者覆盖前者（argparse 既有语义，修订前后一致） | 仅解析基数与空白、保留唯一原始 item（含两端空白）传给 `UploadBatchPlanRequest.material_form`，删除 `.upper()` | **成立但破既有测试**（Finding 01） |
| 生成 `--forms` | `_upload_batch_command_argv`（`fins.py:387-414`）：material entry 机械投影 `--forms entry.form_type`（`:413-414`） | 保持机械生成，不添加 CLI canonical helper | **成立** |
| regeneration | `_upload_batch_regeneration_argv`（`fins.py:449-507`）：`:500` 把 `material_form` 嵌入 `--material-forms`；渲染经 `shlex.join` quoting（`upload_script.py:173`） | regeneration 继续带原始候选供 batch owner 处理；raw 空白可 round-trip | **成立**（docstring 陈旧，OQ3） |
| runner request | 生成的 `--forms` 值为 canonical typed entry；单条 `upload_material` 链经 `_single_optional_form`（`fins.py:1175-1190`，strip 不 upper）→ `FinsUploadMaterialRequest.form_type`（`ingestion_runtime.py:1567`，`str \| None`）→ `_normalize_upload_request`（`:7694-7715`，当前 material 分支仅 `replace(request, action=action)`）→ 修订后 admission 对有效文本产生 canonical → runner 收同值 | slice 10 锁 typed entry → argv → runner request 同值（`EARNINGS_CALL`），用真实准入链 recording runner | **成立** |

依赖方向实证：`upload_batch.py` 当前仅 import `dayu.fins.domain.filing_semantics` 与 `dayu.fins.upload_format_contract`（`:16-20`）；`dayu.fins.upload_batch` 模块全库仅被 `dayu/cli/commands/fins.py:70` 与两个测试文件 import；`docling_upload_service.py` 的 `upload_batch` 字样仅来自 `commit_prepared_upload_batch`/`rollback_prepared_upload_batch` 函数名，无模块 import。plan 新增的 `upload_batch → docling_upload_service` 单向边不成环，与同包既有 import 先例（`filing_semantics`）形态一致。

## `_normalized_text_tuple` strip 与 raw 候选保留专项

任务指定检查点，逐句钉死：

- **当前行为**：`_normalized_text_tuple`（`fins.py:1150-1172`）对 argparse 列表逐值 split 逗号、逐项 `item.strip()`，空白项抛 `CliFinsUsageError`（`--forms` 用 `_EMPTY_FORM_MESSAGE`，其余字段 `{field_name} must not contain empty item`），返回**已 strip** 元组。`_single_batch_material_form` 当前经它取值后再 `.upper()`。
- **裁决关注点成立**：若实施继续调用 `_normalized_text_tuple`，返回值必然已去两端空白，「保留唯一原始 item（含两端空白）」不可成立。plan 文本（白名单第 5 项）与 PR5 fix 记录均明示 raw 候选保留，因此实施必须让 `_single_batch_material_form` 脱离该 helper 或重构 helper 分层（raw-split + strip 两层），二者皆可执行。
- **空值/多值错误时点可保持**：多值（逗号或重复值展开后 >1）仍由 `_single_batch_material_form` 在 CLI 阶段抛 `_MULTIPLE_BATCH_MATERIAL_FORMS_MESSAGE`；空白项仍须在 CLI 阶段抛同一 `CliFinsUsageError`——plan 白名单第 5 项「仅解析 `--material-forms` 的逗号/重复值基数与空白错误」与「保留现有 CLI 错误类型与校验时序」钉住了这一点。argparse 层 `nargs="+"` 的重复覆盖语义不变。
- **实现陷阱（不阻塞，须钉住）**：脱离 helper 后空白判定必须保持 strip 语义（`item.strip() == ""`）。若误写为 `item == ""`，`--material-forms " "` 会穿透 CLI 直达 batch，canonical 函数抛 `ValueError("form_type 不能为空")`，batch 再转 `UploadBatchPlanUsageError`——失败从 CLI 阶段的 `CliFinsUsageError` 漂移到 batch 阶段，**既定失败时序与错误类型双双改变**。slice 10 的「空值 CLI 错误」测试若只写空字符串用例而漏 whitespace-only（`" "`）用例，该漂移会漏网。见 Open Question 1。

## 兼审六项

1. **O09 before-seed（PR4-F1）——成立**：plan 串行集成段登记 O09-F01 的 `fiscal_year` 1800–2100（含端点）域校验与 O17 同属 `build_material_ids` 的 material identity builder/validator、须在 ID seed 前完成、实施 gate 按最终 HEAD 复核合入先后，O17 不预支。代码实证：`build_material_ids`（`docling_upload_service.py:1820-1856`）当前对 `fiscal_year` 仅 `str()` 入 seed（`:1850-1851`），无域校验；O09 裁决文件本 checkout 存在且 owner/域/未实施状态与 plan 一致。
2. **PR4-F2 事件/result 断言面——成立**：plan 白名单第 9 项锁 tool 入口 runner 实际收到的准入后 request、真实 US/CN/HK material 事件流与 pipeline 结果 JSON 中确有的 `form_type`，并明文排除 `FinsObservationSnapshot`/`FinsUploadResultSummary`/`_upload_result_details`。字段实证：US started payload `sec_upload_workflow.py:509`、成功/失败结果 `:582/:610`；CN/HK `cn_pipeline.py:1125/:1198/:1226`；`FinsObservationSnapshot`（`observation_handle.py:136-152`）字段仅 handle/status/message/result/error_kind/retry_after_seconds，全文件无 `form` 字样。
3. **O05 缺失值边界——成立**：plan 明示 admission 仅对有效非空文本 `replace(request, form_type=canonical)`，`None`/空白原样留 request 沿既有后续边界失败，不改失败类型/时序/durable 副作用，不预支 O05 typed usage。代码实证：`_normalize_upload_request`（`ingestion_runtime.py:7694-7715`）当前 material 分支仅替换 action；`form_type: str | None = None`（`:1567`）。
4. **历史 raw——成立**：plan 验收句把同源验收限定为「本修复后新写、或此前已由同版代码写入的 material」，历史已发布 raw form 的 skip/delete 跨代分叉归 `fins-material-legacy-identity-seed-disposition` 独立处置，不迁移、不 fallback、不把旧不一致写成通过合同。与总控裁决一致。
5. **逐文件 coverage——成立（风险已登记）**：plan 验证第 2 条要求对每个实际改动生产 `.py` 逐文件 `--cov` >=80%、基线先行、不用总包均值抵扣、失败如实报未完成；PR5 fix 第 4 项明示 batch/CLI 新生产文件同受门槛。新增白名单生产文件体量实测：`fins.py` 1283 行、`upload_batch.py` 905 行，逐文件达标不确定性与既有 `ingestion_runtime.py`（9144 行）同级，沿用已登记 residual risk 处理。
6. **README——成立**：plan 白名单第 11 项为条件白名单，`dayu/fins/README.md` 职责命中已列明并授权实施时更新；根 `README.md` 条件更新；`tests/README.md`/`dayu/README.md` 预判不变但留职责命中出口。与 AGENTS.md 触发规则及裁决口径一致。本 plan gate 不改 README，符合。

## Assumptions tested（本轮独立重证摘要）

| # | plan 声称 | 重证结果 |
| --- | --- | --- |
| 1 | 三处当前分别独立规范化：`build_material_ids` strip().upper()、batch override strip().upper()、CLI `.upper()` | **属实**（`docling_upload_service.py:1842`、`upload_batch.py:810`、`fins.py:1208`） |
| 2 | batch typed entry 原样成为生成命令 `--forms` | **属实**（`fins.py:413-414`） |
| 3 | routing table 只产三个封闭类别、override 仅覆盖已路由 material | **属实**（`upload_batch.py:82-91/:294-310/:500-510`） |
| 4 | `docling_upload_service.py` 与 `upload_batch.py` 当前无相互导入，单向复用不成环 | **属实**（`upload_batch.py:16-20`；模块引用方穷举仅 CLI 与测试） |
| 5 | `_normalized_text_tuple` 会 strip | **属实**（`fins.py:1162-1171`） |
| 6 | 空白/不支持值现有公开错误分类：CLI `CliFinsUsageError`、batch `UploadBatchPlanUsageError` | **属实**（`fins.py:1167-1169`、`upload_batch.py:813`） |
| 7 | 两市场事件/结果含 `form_type`，snapshot/summary/details 无 | **属实**（行号见兼审第 2 项） |
| 8 | O09 同 owner before-seed 未实施 | **属实**（`docling_upload_service.py:1850-1851` + O09 裁决文件） |
| 9 | plan 验收限定新写/同版，历史 raw 归独立 WU | **属实**（plan 验收段与串行集成段文本） |

## 新反例主动狩猎（本轮新增攻击面与结论）

1. batch 空白 override 经 canonical 函数 `ValueError` 穿透改变公开错误分类 → plan 白名单第 4 项明文「不让 canonical 函数的异常改变公开错误分类」，但转换机制未指定，落 Open Question 2 而非 finding。
2. `--material-forms " "` whitespace-only 穿透 CLI → 实现陷阱真实存在，但 plan 文本已钉 CLI 空白错误归属，slice 10 测试措辞可收口，落 Open Question 1。
3. regeneration argv 嵌 raw 空白后脚本注释 round-trip 失真 → `shlex.join`/Windows quoting helper 实证可保真，不成立。
4. `upload_batch → pipelines.docling_upload_service` 新边成环 → 引用方穷举无环，不成立（方向选择已经裁决，不重审）。
5. 重复 `--material-forms` 标志语义漂移 → argparse `nargs="+"` 后者覆盖前者为既有语义，修订前后一致，不成立。
6. **既有 CLI 命令测试锁定旧 `.upper()` 行为且文件不在白名单** → **成立，记 Finding 01**。

## Findings

### 01-未修复-中-计划测试白名单遗漏 `tests/cli/test_upload_filings_from_command.py`，实施即确定性破坏既有用例

- **位置**: plan 白名单第 10 项（测试归属 `tests/fins/test_upload_batch.py`、`tests/cli/test_fins_commands.py`）与收尾段「除上述 11 项列出的生产、测试与条件 README 路径外，不因 PR5-F1 扩展文件」。
- **问题类型**: 测试缺口 / 不可直接实施（白名单完整性）。
- **当前写法**: slice 10 把 `--material-forms` 单值原样传 batch、空值/多值 CLI 错误、regeneration 原值、typed entry → `--forms` → runner request 同值等 CLI 侧断言全部放进 `tests/cli/test_fins_commands.py`；白名单未列 `tests/cli/test_upload_filings_from_command.py`。
- **反例/失败场景**: 实施按 plan 删除 `_single_batch_material_form` 的 `.upper()` 并保留 raw 候选后，既有用例 `test_material_form_candidate_reaches_fins_owner_and_maps_usage_exit`（`tests/cli/test_upload_filings_from_command.py:197-236`）确定性失败：该用例经 `_capture_request_then_generate_plan`（`:64-75`，记录后调真实 `generate_upload_batch_plan`）以 `--material-forms " esg_report "`（`:227-228`）驱动，当前断言 `request.material_form == ["ESG_REPORT"]`（`:233-235`）与 stderr 含 `unsupported material form: ESG_REPORT`（`:236`）。实施后 request 携带 raw `" esg_report "`、batch 错误消息 echo raw 值（`upload_batch.py:813` 模板 `f"unsupported material form: {value}"`），两处断言同时破裂；实施 Agent 在「白名单外不改」约束下只能停或违例改非白名单测试。
- **为什么有问题**: plan 自述 code-generation-ready 且白名单外不改；遗漏的文件恰是 batch CLI 命令（`upload_filings_from`）用例的既有归属地，而 plan 选择的 `tests/cli/test_fins_commands.py` 是 direct 命令套件、全文件无任何 `--material-forms` 用例（本轮 rg 实证零匹配）。这不是实现自由度问题，而是计划文本与既有测试事实的硬冲突。
- **直接证据**: `tests/cli/test_upload_filings_from_command.py:197-236`（docstring「CLI 必须传播规范化候选」即被删除行为）、`:64-75`；plan 白名单第 10 项与收尾段文本；`fins.py:1208` 待删 `.upper()`；`upload_batch.py:813` 消息模板。
- **影响**: 实施 gate 跑到受影响 CLI 测试即红，被迫中止回流的概率高；若实施 Agent 擅自改非白名单测试则破坏 gate 纪律。另注意伴随的用户可见 stderr 变化（不支持类别错误消息从 echo 大写值变为 echo raw 输入）需要在该用例中一并锁定新预期。
- **建议改法和验证点**: 白名单第 10 项增列 `tests/cli/test_upload_filings_from_command.py` 并写明断言 delta：`request.material_form` 断言改为 raw 候选（含两端空白）、stderr 断言改为 `unsupported material form:  esg_report `（echo raw）；新 CLI 断言优先与该文件同址 colocate（batch 命令用例的既有归属），`tests/cli/test_fins_commands.py` 仅在承担 direct 入口同值断言时保留。验证点：修订后计划文本指明该文件与新断言值，实施 gate 先跑该文件确认基线绿、实施后确认新断言绿。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

## Open Questions

1. **`_single_batch_material_form` 脱离 `_normalized_text_tuple` 的实现 seam**：本地 split/基数/空白判定，还是抽取 raw-split helper 并把 `_normalized_text_tuple` 重构为其上的 strip 层。两种皆可，但空白判定必须保持 strip 语义，且 slice 10 须显式锁 whitespace-only（`" "`）CLI 用例而非仅空字符串，否则空白拒绝从 CLI 漂移到 batch、既定失败时序与错误类型改变（陷阱机制见专项节）。不构成阻塞。
2. **`_validated_material_form` 的空白转换机制**：canonical 函数对空白抛 `ValueError("form_type 不能为空")`（plan owner 节），batch 须保持 `UploadBatchPlanUsageError` 分类与既有消息（`upload_batch.py:813`）。先判空白再调用，或 try/except 转换，plan 未指定；建议实施时以一行注释声明该转换只是公开错误分类保持，不是第二套 usage 语义。不构成阻塞。
3. **两处 docstring 随 raw 语义变陈旧**：`_single_batch_material_form` 返回值说明「规范化的单一 material form 候选」（`fins.py:1199`）与 `_upload_batch_regeneration_argv` 参数说明「已规范化单一 material form 候选」（`:461` 附近）在实施后将不再准确；同文件已在白名单内，实施时一并更新。不构成阻塞。
4. **slice 9/10 的 capture seam**：tool 入口与 CLI→runner 同值断言所需的真实准入链 recording runner 的具体挂接形式未指定（沿前轮 open question，已被「不以 fake 替代」约束钉住行为）。不构成阻塞。

## Residual Risks（含跟踪去向）

1. **历史 raw form 跨代分叉**：skip/delete 碰历史 raw meta 时新事件/结果 canonical 而旧 meta/manifest 保持 raw（裁决已接受的范围风险）。**跟踪**：`fins-material-legacy-identity-seed-disposition` 独立 work unit。
2. **逐文件 coverage gate 可能阻塞**：新增白名单生产文件 `fins.py`（1283 行）、`upload_batch.py`（905 行）与既有 `ingestion_runtime.py`（9144 行）同受逐文件 >=80% 门槛，基线未知。**跟踪**：实施 gate 按 plan 验证第 2 条基线先行、不足扩测、失败如实报未完成；「报告阻塞」是合法终态。
3. **storage `_fs_source_document_core.py:1771` 的 `or` fallback 死分支**：material 路径恒走显式分支；未来绕过 `prepare_upload` 的写入可能复活旧值（沿前轮）。**跟踪**：O07/O10 同 owner 串行时顺带核对或独立 storage 整洁性 issue。
4. **读侧既有归一化语义独立**：`read_runtime_helpers` 别名表、`_normalize_form_value`、processed 精确匹配过滤对 raw 查询 + canonical 新数据组合不保证命中（沿前轮）。**跟踪**：UM read 侧语义既有 owner，不扩本项。
5. **两 CLI flag 空白处理不一致**：`--forms` 经 `_normalized_text_tuple` strip、`--material-forms` 保留 raw；两条链终点均 canonical，属解析层定位差异而非事实分叉（沿前轮「CLI 边界先 strip」扩展）。**跟踪**：closeout 解读 CLI 配对结论时注意配对只证明 CLI 可见合同。
6. **成功信号依赖实施后的真实 CLI 配对**：冻结 A14/A15 只证明旧偏差（沿前轮）。**跟踪**：实施 gate 验证第 3 条。

## 探索命令与退出状态披露

- 结论依据命令均回读退出码：`shasum -a 256` 目标 plan、各 `sed`/`rg` 代码与文档实读、`git log`/`git status`、`date`、`wc -l` 均为 exit 0。
- 预期失败/无匹配已如实记录并仅作存在性/缺失性证据：`ls docs/reviews/upload-material-um-o17-oracle-adjudication.md ...` 组合命令整体 exit 0，其中 ls 子命令对 O17 裁决文件报 `No such file or directory`（预期，核对 plan 声明）；`ls docs/reviews/plan-review-o17-pr5-kimi-20260929.md` exit 1（写入前 PATH_FREE）；`rg "material.forms|_single_batch_material_form|MATERIAL_FORMS" tests/cli/test_fins_commands.py` 输出为空（零匹配，作为该文件无既有 `--material-forms` 覆盖的证据）；`rg "form" dayu/fins/ingestion/observation_handle.py` 输出为空（零匹配，作为 snapshot 无 form 字段的旁证）。
- 失败命令如实披露 1 条：`rg -rn "def render_upload_script" dayu/` 误加 `-r` 替换旗标，exit 0 但输出失真（匹配被替换为 `n`），未用于任何结论；随后以 `rg -n "def render_upload_script" dayu/ --type py` 重跑完成核验。
- 未运行任何测试、coverage 或 pyright（只读 plan review，无产品代码变更）；未修改 plan/goal/产品/测试/README/旧 review/裁决；未 commit/push/PR/merge；未派发子 Agent。

## Final Plan Review Conclusion

**pass-with-risks**

- 停止条件逐条核验不触发：SHA 与任务锁定值一致；batch/CLI/identity 的 form 文本规范化在 plan 中单真源化、无残留双真源；CLI raw 候选承诺可执行且空值/多值错误时点可保持；既定失败时序在 plan 文本中有钉住。
- PR5-F1 修订方向经当前 HEAD 独立重证成立：batch override、filename routing、CLI 解析、生成 `--forms`、regeneration、runner request 全链同源，依赖方向无环，封闭 routing 集合与 canonical 函数的 owner 边界划分清晰。
- 兼审六项（O09 before-seed、PR4-F2 事件/result、O05 缺失值、历史 raw、逐文件 coverage、README）全部成立，与总控裁决口径一致。
- 本轮新发现 1 条 finding（中）：测试白名单遗漏 `tests/cli/test_upload_filings_from_command.py`，实施即确定性破坏既有用例；修复风险低，按前轮模式交总控裁决修计划后再进实施。
- 另有 4 条实现精度级 open questions 与 6 条已登记 residual risks，建议实施任务下达时随附。
- 本复审仅覆盖 plan gate，不构成实施授权；下一 gate 按总控流程裁决。
