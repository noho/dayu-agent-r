# UM-O11-F01：material 日期前置校验实施计划

- Gate：`plan fix`；状态：按 MiMo F1–F5 与总控裁决修订，待双路 plan re-review；下一 gate：Kimi/MiMo 独立双路 `plan re-review`，由总控裁决后才能进入 implementation。
- Work unit：`UM-O11-F01`。本计划依据已确认的 [goal](upload-material-o11-dates-goal-20260929.md) 和主工作区只读 `docs/reviews/upload-material-um-o11-oracle-adjudication.md` 裁决；本轮权限仅限 plan artifact。
- 基线：branch `codex/upload-material-o11`，HEAD `8d8d494fbbce0052372fb1b42097c9f7222cfa28`；写计划前 `git status --short` 只有未跟踪的 goal 文件。冻结 CLI 证据属于 `fac32ecbff9bfe792b63ee9667c8697826b631f4`，不是本 HEAD 验证。
- Artifact：`docs/gateflow/upload-material-o11-dates-plan-20260929.md`。
- 本轮 plan fix 仅允许修改上述 Artifact；修订前已核对 HEAD 和 MiMo 审查所指的原计划 SHA-256 `9478ad432132697bedbf81e83d71ec6511196602e151e96db659f5b1aba7af34`。不得修改产品、测试、goal、review、裁决或其它文件，也不得进入 implementation、commit、push、PR、merge 或外部评论。

## 目标、动机、成功信号与边界

动机成立。冻结 UM-A18/S10/S11 证明非法日期曾成功进入 source meta 和 material manifest；本 HEAD 的直接代码证据是 `FinsUploadMaterialRequest.filing_date/report_date` 仍为 `str | None`，`_normalize_upload_request` 的 material 分支仅归一化 action，没有调用日期校验。`_validate_optional_upload_iso_date` 和字段明确的 `INVALID_FILING_DATE` / `INVALID_REPORT_DATE` 已存在，却只用于 filing 静态准入。错误业务事实应在 request admission 阶段被拒绝，而不是依赖市场流程或仓储补救。

成功信号：material 两个日期字段仅在 `None` 时跳过校验；任何非 `None` 原始文本，包括 `""` 和纯空白，都必须经 `parse_iso_calendar_date` 接受精确 `YYYY-MM-DD` 且实际存在的公历日，否则按字段产生现有 `FinsUploadUsageError.failure.code`，在 producer、observation、job、公司与文档发布前失败。raw request 的空串从目前穿透持久化改为 typed 拒绝，这是本修复纠正的错误行为。合法日期原值在同一 request、result 相关事实、source meta、manifest 间一致。唯一已接受的入口级空值例外是 `dayu-cli upload_material --filing-date ""` 在构造 request 前折叠为 `None`；它仍可成功上传，source meta 与 manifest 投影 `null`，不得把折叠搬进 admission 或 raw request/tool。真实隔离 CLI 验证非法字段各一、合法对照和显式空 filing_date；记录退出状态与 stdout/stderr，不把冻结运行当本 HEAD 结论。

非目标：不修改日期 parser、年份/财期规则、material form/name、ID、schema、manifest 结构、其它上传语义；不把显式空 `report_date` 上升为新 accepted contract；不建立 CLI、tool、US/CN/HK 或 storage 的第二套日期校验；不将 `upload_filings_from` 批量脚本元数据纳入直接上传日期承诺。O05/O16 共享 admission 的变更须串行集成，后集成者基于前者实际 HEAD 重新核对，不在本 work unit 提前实施。

## Owner 与当前调用链的直接证据

| 语义或路径 | 当前 HEAD 证据 | 本计划决定 |
| --- | --- | --- |
| 日期语法和公历存在性 | `dayu/fins/domain/filing_semantics.py:375` 的 `parse_iso_calendar_date` 用 ASCII 全匹配、`datetime.date` 和回写字符串一致性校验；`tests/fins/test_fiscal_normalization_contracts.py` 已覆盖闰日、非补零与不存在日期 | 唯一日期规则 owner；不修改 parser，不复制逻辑 |
| 上传字段级失败 | `dayu/fins/ingestion_runtime.py` 的 `_validate_optional_upload_iso_date` 调用 parser 并把 `ValueError` 映射成传入的 `FinsUploadUsageCode`；现有 code 与文案分别指向两个字段 | material 复用同一 helper 与 typed code；不加新 code、错误格式或 schema |
| material request 准入 | `_validate_runtime_upload_request` 对 material 调用 `_normalize_upload_request`；后者 material 分支目前只 `replace(request, action=action)` | 在该 material 分支对两个日期调用现有 helper，先于返回 normalized request；不让下游重算或清洗已通过的日期 |
| 三种 runtime 入口 | `upload`、`prepare_observed_upload`、`start_upload` 均先调用 `_validate_runtime_upload_request`；`start_observed_upload` 经 `prepare_observed_upload` | 同一失败先于 direct producer、observation 登记及 durable queued job；不新增入口分支 |
| Service、tool、CLI | `FinsDirectCommandService.upload_material` 构造 material request 并调用 `runtime.upload`；`FinsUploadToolCallable` 构造 request 后调用 `runtime.prepare_observed_upload`；CLI `_upload_material_stream` 调用 Service，`run_fins_direct_command` 已捕获 `FinsUploadUsageError` 为 usage 退出 | Service 与 renderer 不改；tool/CLI 只保留各自输入投影职责，typed 业务失败由 Fins 产生 |
| 市场与发布 | `ProductionFinsUploadRunner._run_material_upload` 把同一 request 的日期传到 US `SecPipeline` 或 CN/HK `CnPipeline`，随后由既有 pipeline/storage 发布 source meta、manifest | 不在市场流程及仓储加 fallback；通过 admission 的同一日期字符串继续流向已有投影 |

CLI 当前通过 `_optional_stripped_text` 将空串/纯空白转 `None`，也会把非空日期首尾空白裁掉；tool material 当前 `_optional_nullable_text` 同样裁掉非空日期，tool schema 又仅对 filing 陈述日期格式。为了让**非空原始日期**到达唯一 owner，CLI material 两个日期参数的投影保留现有空值折叠、对非空原文不 trim；tool material 两个日期参数改用已经供 filing 使用的 `_optional_raw_nullable_text`。这两处不解析日期。CLI 显式空 `filing_date` → `None` 是本 goal 唯一接受并须验证的入口例外；其它 CLI 空值折叠只保持现状，不从中推导空 `report_date` 的新增承诺。raw request 的非 `None` 空串/纯空白一律由 admission 拒绝；tool 的省略或 `null` 才表示未提供，空串/纯空白仍拒绝，拒绝结果类别保持 `invalid_argument`，具体错误消息可从参数读取错误变成日期语义错误。tool schema 两个字段的业务说明须与此一致。

公共契约变化限于 material 日期非法时已有 typed usage code 在更多入口可见，且非空带空白原文不会被 CLI/tool 隐式修正；`FinsUploadMaterialRequest` 字段类型、schema、日期规则、direct/observation/job 状态机和 US/CN/HK 发布接口均不变。`SecPipeline` / `CnPipeline` 的直接方法是 runner 下游组件调用点；本 goal 的公开产品入口经 runtime admission。若实施中证实另有受支持的公开入口直接调用这些组件并发布 material，则命中停止条件。

## 单个行为切片：S1 material 日期同源拒绝与投影

- **目标与对应 success signal**：两字段非法在共享 admission 以字段明确的 typed usage 失败；合法日期和 CLI 显式空 filing_date 进入原有 US/CN/HK 发布链。一个可验证行为增量，一次 implementation/review 成本即可覆盖，不按模块拆片。
- **前置条件**：实施时重查 HEAD、branch、dirty ownership；先核对 O05/O16 是否已集成。若 admission、公开入口或空 filing_date 语义已改变，按停止条件重新裁决，不机械套用本计划。
- **允许的生产文件**：`dayu/fins/ingestion_runtime.py`（唯一 material admission）；`dayu/cli/commands/fins.py`（仅 material 日期参数的空值投影和原文转交）；`dayu/fins/tools/upload_tools.py`（仅 material 日期原文转交及两个日期参数的 LLM-facing 描述）。不改 `filing_semantics.py`、Service、runner、pipeline、storage、schema 或 CLI renderer。
- **允许的测试文件**：`tests/fins/test_fins_ingestion_runtime.py`、`tests/fins/test_fins_ingestion_tools.py`、`tests/cli/test_fins_commands.py`。已有 tool 测试把 material padded 日期预先 trim 当作期望，随 owner 边界迁移该断言；不得在生产代码保留旧 trim 以迁就 fixture。
- **允许的文档文件**：实施后按职责检查并在需要时更新 `dayu/fins/README.md` 与根 `README.md`；`tests/README.md` 和 `dayu/README.md` 只依各自触发条件复判，当前计划不预设修改。文档仍属于后续 implementation gate 的允许范围，本轮 plan fix 不修改。
- **实现步骤**：① material 分支先用现有 `_validate_optional_upload_iso_date(request.filing_date, INVALID_FILING_DATE)` 和对应 report code，再返回 `replace(request, action=action)`；helper 仅跳过 `None`，对 raw `""`/纯空白也按字段拒绝，日期字段本身不重写、不折叠。② CLI 用窄的模块级日期输入投影保留现有 `None`/空白转 `None` 行为（已接受的显式空 `--filing-date ""` 例外），非空文本按原样交给 Service；此 helper 只处理 CLI 空值，不解析日期。③ tool material 两字段使用现有 raw nullable 参数读取 helper；`filing_date` 和 `report_date` 的 tool schema 描述各自自足说明披露日期/报告期日期的业务含义、可选文本、`YYYY-MM-DD` 且实际存在的公历日、合法示例 `2024-02-29`、省略或 `null` 表示未提供，以及空串/纯空白/首尾空白均非法且不能用于清空日期，filing/material 同样适用；不用内部 parser/type 名代替模型可执行规则。同步迁移 `tests/fins/test_fins_ingestion_tools.py` 中现有精确 schema 文案断言。各新增/修改函数补齐中文参数、返回、异常 docstring，修改 owner admission 的异常说明需包含 material 日期 typed 失败。
- **状态与失败**：非法值抛 `FinsUploadUsageError`，`failure.code` 分别为 `invalid_filing_date` 或 `invalid_report_date`，message 复用 Fins owner；不创建 direct stream/producer、observation handle、queued job 或 progress；不调用 upload runner；company、source、blob、meta、manifest 均无新增/替换。CLI 只把该 typed usage 投影为现有非零 usage 退出与 stderr；tool 投影既有 `invalid_argument` 失败 outcome，不返回 awaiting handle。合法值不引入新的状态机或持久化字段。
- **完成信号**：owner 测试、tool/CLI 边界测试、现有 US/CN/HK material 发布回归、真实隔离 CLI 场景、pyright 和文件覆盖率通过，README 职责判断落实；否则保留 plan/implementation gate 未通过状态并登记直接证据。

## 验证设计与预期断言

1. `tests/fins/test_fins_ingestion_runtime.py`：按 `filing_date=2025-02-30`、`report_date=not-a-date`、非补零、`""`、纯空白和首尾空白分别构造 material request；在 `upload`、`prepare_observed_upload`、`start_upload`（必要时覆盖 `start_observed_upload` 委托）以 owner 的接受/拒绝、字段明确的 code/message 和入口副作用为主断言：runner 与 executor 未调用、observation registry 空、job 不存在、仓储 workspace tree 与 company/source 发布前快照相同。合法闰日与 `None` 分别断言被接受且原值/缺失值沿三入口传递；parser monkeypatch 仅可作为同源性辅助护栏，不固定调用次数、私有调用步骤或替代 owner 行为断言。以 US/CN/HK ticker 参数化入口测试，确认市场选择不影响准入。
2. `tests/fins/test_fins_ingestion_tools.py`：material 两字段各用无效日期、空串/纯空白及 padded 非空日期，断言 adapter 保留原文，Fins 返回字段明确的 `invalid_argument` message，未产生 observation/job/publish；省略或 `null` 投影为 `None`。同步断言 LLM-facing schema 两字段均完整说明业务含义、可选文本、真实公历 `YYYY-MM-DD`、`2024-02-29`、省略/`null` 与空串/纯空白/首尾空白非法，且 filing/material 同规则；迁移现有精确文案断言。类型错误仍由现有 tool 参数读取边界拒绝，不把它误认成日期解析失败；空串拒绝的具体消息允许随 owner 迁移。
3. `tests/cli/test_fins_commands.py`：fake Service 只检验 CLI 参数投影：显式 `--filing-date ""` 得 `None`；非空 padded 日期原文保持，供 Fins admission 拒绝。此测试不充当 owner 校验或真实 CLI 证据。
4. 运行现有 `tests/fins/test_sec_pipeline_upload_material_stream.py`、`tests/fins/test_cn_pipeline.py` 回归，确认 US 与 CN/HK 发布未退化；不通过对 pipeline 单独调用来证明 admission。真实发布读回使用 Fins repository 对照 source meta、material manifest、成功结果，三者日期来自同一上传请求。
5. 实施后在独立 CI-owned `run_dir` 和每场景 fresh `--base` workspace、同一真实输入文件下运行 `.venv/bin/dayu-cli upload_material`：单独非法 filing、单独非法 report、两个合法日期对照、显式空 filing_date。记录 exact argv、HEAD、运行配置、退出状态、stdout/stderr、before/after 文件树与 digest；非法场景须有字段明确 usage stderr、非零退出、无上传进度、无公司/source/meta/manifest/job 发布；合法场景须成功且 meta/manifest 日期一致；显式空 filing 场景须成功且两处均为 `null`。使用真实 CLI 与实际 Fins storage，不以 fake/mock 或冻结 S09/S10/S11 替代。任何环境/转换失败单独分类，不伪装产品通过。
6. `source .venv/bin/activate` 后运行受影响的 focused pytest：`python -m pytest tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_ingestion_tools.py tests/fins/test_sec_pipeline_upload_material_stream.py tests/fins/test_cn_pipeline.py tests/cli/test_fins_commands.py -q`。运行 `python -m pytest tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_ingestion_tools.py tests/cli/test_fins_commands.py --cov=dayu.fins.ingestion_runtime --cov=dayu.fins.tools.upload_tools --cov=dayu.cli.commands.fins --cov-report=term-missing -q` 并核对每个修改生产文件的单文件覆盖率目标各 `>=80%`；再运行 `python -m pyright dayu/ tests/ utils/`，不得新增、扩散或掩盖类型错误。若补齐受影响 owner 行为测试后仍有文件未达 80%，实施报告必须逐文件登记准确数字、原因和未达标残余，不得静默写通过，也不为指标写镜像测试。

## README 判断、发现登记与残余风险

- `dayu/fins/README.md` 的现有 ingestion admission 说明把 strict date 限于 filing、称 material 保持旧 normalization；实施后属于 Fins 稳定公共契约，**需更新该段**。更新前按其 `Agent更新约束` 复核已实现代码。
- 根 `README.md` 目前将日期输入说明限定在 direct filing；material 非空非法日期（含首尾空白原文）的拒绝收紧，以及既有显式空 `--filing-date ""` → `null` 行为的用户说明，**需在上传章节补一段用户所需说明**，不把该空值行为写成变化，也不写内部 owner/gate。更新前按其 `Agent更新约束` 复核 CLI 实现。
- `tests/README.md`：本切片只扩充现有 Fins、tool、CLI 测试层级及既有命令，不新增测试层级；按其前言与触发规则判断暂不修改。`dayu/README.md`：没有跨层边界/装配变化，暂不修改。若实施事实不同，仅按各 README 职责复判，不能机械同步。
- **发现 D1（纳入本修复，不另开规则）**：tool material 日期 adapter 的 trim 和仅描述 filing 的 schema 使非空原文校验被绕开/LLM-facing 说明滞后；CLI material 日期同样 trim 非空原文。以上入口投影修正是让 Fins 唯一日期 owner 覆盖公开入口的必要上游输入保真，不把校验迁到 adapter。
- **残余 R1，assigned to later work unit**：`upload_filings_from` 的扫描/脚本元数据不是本 direct material 准入目标；其日期预折叠差异保留为独立残余，本切片不顺手修。**残余 R2，requiring explicit user decision**：仅 CLI 显式空 `--filing-date ""` → `None` 是已接受的空值例外；其它 CLI 当前空值折叠不升级为新承诺。raw request 的两日期非 `None` 空串/纯空白在共享 admission 改为 typed 拒绝；tool 省略/`null` 仍为未提供，空串/纯空白的 `invalid_argument` 拒绝结果保持，具体原因允许迁移。是否另行承诺显式空 `report_date` 的产品语义须独立裁决，不由 S09 推导。**残余 R3，assigned to later work unit / 集成 owner**：O05/O16 也修改共享 admission，PR 集成者串行复核真实 HEAD、冲突、action 与日期等多错误字段的优先级及全量 affected tests。
- 当前 blocking open question：无。本轮及后续 gate 若 HEAD 不再是约定的 `8d8d494fbbce0052372fb1b42097c9f7222cfa28`（后续串行集成由总控先重新定基线）、plan 出现并发改动、修订需要扩大已确认 goal 或改变日期 owner，立即停止并报告直接证据，不覆盖他人内容。若实施证据显示任一公开 material 入口绕过共享 admission、保持已接受 CLI 空 filing_date 需要改变语义、或必须新增日期/schema 规则，也立即停止、记录调用链并请求重新裁决；不扩张 slice。任何后来发现的新修复项先在本 artifact 登记 owner、证据、是否属于已确认目标及处置，不直接顺手实现。

## 后续 gate 报告格式

实施/评审报告须列：gate 与 decision、work unit/基线 HEAD、artifact 绝对路径、实际修改文件、各场景原始证据路径和断言、pytest/pyright/单文件覆盖率（未达标须列数字、原因与残余）、README 决定、findings 状态、残余风险及 owner、下一 gate。当前仅修订 plan artifact；F1–F5 待 Kimi/MiMo 双路 plan re-review 与总控裁决，不得把本计划写成已验证修复或直接进入 implementation。
