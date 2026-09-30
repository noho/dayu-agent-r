# UM-O09-F01 + UM-O10-F01 计划第四轮独立复审（MiMo 路）

RUNTIME/PROVIDER/MODEL: claude/mimo/mimo-v2.6-pro[1m]

CANARY=mimo-823d05db

- 复审对象：`docs/gateflow/upload-material-fiscal-plan-20260929.md`（Sol 按第三轮 MiMo 两项 finding 与总控裁决修订后的候选计划，SHA-256 `5c3bbee5cd65d86cf92f90d5d977250264eabfbaf07a51a9d86b94c9c68e81a5`，预检实测匹配）。
- 任务标签：`fiscal-plan-rereview4-mimo-20260929-01`（第四轮 MiMo 独立 `$planreview`）。artifact 文件名按任务显式指令使用 `plan-review-fiscal-rereview4-mimo-20260929.md`，覆盖 skill 的 timestamp 命名惯例。
- 范围：只读 plan 与代码做 adversarial plan review；不改 plan/产品/测试/README/goal/旧 review/总控裁决；不实施、不提交、不派发子 Agent、不安装依赖。
- 基线：workspace `/private/tmp/dayu-upload-fiscal`，branch `codex/upload-material-fiscal`，HEAD `8d8d494fbbce0052372fb1b42097c9f7222cfa28`（停止条件核对通过）；plan SHA 与任务给定一致；`git status --short` 仅 6 个未跟踪 gateflow/review 文档。
- 范围合同（binding）：goal `docs/gateflow/upload-material-fiscal-goal-20260929.md`、总控裁决 `docs/gateflow/upload-material-fiscal-plan-review-adjudication-20260929.md`、用户裁决 `docs/reviews/upload-material-um-o09-oracle-adjudication.md` 与 `upload-material-um-o10-oracle-adjudication.md`（主工作区只读）、O05/O06（`upload-material-um-o01-o06-oracle-adjudication.md`）/O07/O11/O16 裁决（主工作区只读）、总控队列 `docs/gateflow/upload-material-issue-198-repair-sequence-20260928.md`、上三轮复审 `plan-review-20260929-020741/031057/035228.md`、AGENTS.md（=CLAUDE.md）。

## 结论摘要

**pass-with-risks**。停止条件未触发。任务指定的两个重点攻击面均未攻破：共用 tool `fiscal_period` schema 的三分句（filing 必填、material 可省略/`null`、两者空串/纯白参数层拒绝）与 `_required_text`/`_optional_nullable_text` 真实行为逐句一致且互相隔离；旧逐字测试迁移清单 `tests/fins/test_fins_ingestion_tools.py:1718-1723` 经全仓 grep 证实恰为仅有的两处 schema description 逐字断言，清单准确无需追加。1800..2100、六枚举、legacy seed/manifest 同源、独立 venv/覆盖率/pyright gate、O05/O11/O16 合流登记逐条重证成立。新发现 2 个 finding：合流登记漏了 O07-F01/F02（中——O09/O10 用户裁决原文即声明与 UM-O07-F02 同一语义 owner，且 O07-F01 要删的请求字段/工具 schema/校验函数正落在本计划改动面上）；新增 `INVALID_MATERIAL_FISCAL_YEAR` 文案的通道中立性未被计划钉住（低）。均为 plan 文本一行/一行级收敛，不构成结构性返工。

## 重点攻击面核查（任务指定）

### 攻击一：共用 tool `fiscal_period` schema 是否逐句自足（filing 必填 / material 可省略·null / 两者空串·纯白拒绝）

**结论：逐句自足成立，上一轮 finding 的反例已被本轮计划文字封死。** 逐句对照真实代码：

| 计划要求的 schema 语句 | tool 参数层真实行为 | 判定 |
| --- | --- | --- |
| filing 分句：财期必填，省略或传 `null` 均按必填错误拒绝，且只支持 `FY/H1/Q1/Q2/Q3/Q4` | filing 请求读取用 `_required_text(arguments, "fiscal_period")`：缺失/`null`/空串/纯白统一抛 `ValueError("fiscal_period must be a non-empty string")` → `invalid_argument`；非空值通过后由 filing admission `normalize_fiscal_period` 做 trim/upper/枚举校验（`ingestion_runtime.py:1274-1287`） | 成立 |
| material 分句：财期可省略或传 `null` 表示未提供，非空文本去首尾空白并转大写后只支持这六个值 | material 请求读取用 `_optional_nullable_text`：缺失/`null` → `None`（即未提供），非空 strip 后进入 admission，`normalize_fiscal_period`（`filing_semantics.py:300-321`）trim/upper/空→`None`/非枚举 `ValueError` | 成立 |
| 共享句：空字符串或纯空白在 tool 参数层均以 `invalid_argument` 拒绝，不能写成 material 的"未提供" | 两上下文均在 `_ingestion_tool_helpers.py:111-117/138-157` 抛 `ValueError` → `upload_tools.py:115-120` 映射 `_ERROR_INVALID_ARGUMENT`，发生在 `prepare_observed_upload` 之前 | 成立 |
| 显式禁止：不把 material 的省略/`null` 规则写成共享参数的全局规则 | 上一轮 finding 01 的反例（共享总述句使 filing 省略被误述为"未提供"）被该禁止句与分句结构双重封死；S1 测试契约另有「filing 省略或 `null` 的 period 因必填在 tool 参数层返回 `invalid_argument`」的钉死断言 | 成立 |

补充事实（更正上一轮复审的一处不准确反例）：第三轮 finding 01 曾假设「LLM 在 filing 上传中省略 `fiscal_period` 将撞 `MISSING_FISCAL_PERIOD`」——对 **tool 路径不成立**。tool 的 filing 分支用 `_required_text` 在参数层即拒（`upload_tools.py:343`），`MISSING_FISCAL_PERIOD` 只在 CLI（argparse 缺省 `None` 经 `_optional_stripped_text`）/Service/owner 路径经 Fins admission 可达（`ingestion_runtime.py:1274-1275`）。现行计划把 filing 省略/`null` 钉为「tool 参数层 `invalid_argument`」，比该反例更贴近代码事实。`fiscal_year` 的对偶规则（filing `_required_int` 必填、material `_optional_int` 可选、bool/非整数参数层拒绝、越界进 Fins admission）与计划文字一致（`upload_tools.py:342/359`、`_ingestion_tool_helpers.py:224-256`）。tool 层无 jsonschema 强校验，`null` 可直达 `_optional_nullable_text`，「传 `null` 表示未提供」可实现；总控裁决的逐字口径可落实。

### 攻击二：旧逐字测试迁移清单是否准确

**结论：清单准确。** `tests/fins/test_fins_ingestion_tools.py:1718-1723` 恰为 `fiscal_year`/`fiscal_period` schema description 的两处 `==` 逐字断言（1718-1720、1721-1723），全仓 grep 该两条文案在 `tests/` 内仅此两处，无其它文件、无片段断言、无整 schema 快照断言引用它们。同函数内 1724-1731 的 `filing_date`/`report_date` 逐字断言归 O11（计划未要求迁移，正确）；1732-1737 的 `exact_messages` 钉 filing `INVALID_FISCAL_YEAR` 等三个文案，本项保持 filing 文案原样故不受影响（`test_fins_ingestion_tools.py:1370-1371`、`tests/cli/test_fins_commands.py:1535/1541`、`tests/fins/test_fins_ingestion_runtime.py:1448/3216/3227` 均为 filing 语境断言，不需迁移）。material 侧既有 fixture 全为域内值（`test_docling_upload_service.py:5006-5027` 2024/`FY`；`test_cn_pipeline.py:135-136/2206-2207` 2024/`FY`；`test_sec_pipeline_upload_material_stream.py` 无 fiscal fixture），`_normalize_optional_upload_fiscal_period` 无任何测试引用，删除无测试面。计划「不为保住旧断言回退生产 schema」的处置方向与 AGENTS.md「测试跟着实现边界迁移」一致。

## Assumptions tested（逐条独立重证）

Sol 修订 run 按协议记 `agent_status=failed`（`git diff --no-index` 对新文件返回 1），以下全部按候选独立重证于 HEAD `8d8d494f`，未依赖任何他人实测输出：

| plan 主张 | 重证结果 | 直接证据 |
| --- | --- | --- |
| 年域 1800..2100 闭区间、bool 不作整数、`-1/0/1799/2101/10000` 拒绝 | 成立且与用户裁决逐字一致 | O09 裁决「合法财年域为 1800–2100（用户裁决值，含端点），拒绝负、0 与超出该域的整数」；goal 成功信号 1；plan 成功信号 1/契约第 1 条 |
| 期域六枚举、复用 filing 真源、长度被枚举吸收 | 成立且与用户裁决一致 | O10 裁决「FY/H1/Q1/Q2/Q3/Q4」「不设独立长度上限」；`filing_semantics.py:39`（`FiscalPeriod` 为 str `Literal`）、`:100-101`、`:300-321`（含 `field_name` 形参，plan 的 `normalize_fiscal_period(..., field_name="fiscal_period")` 调用形态成立） |
| filing 年域 1000..9999 与 material 分离，不复用 filing usage code，不改 filing 文案 | 成立 | `filing_semantics.py:48-51`、`407-428`（`normalize_fiscal_year`/`parse_calendar_year` 为 filing 域）；`ingestion_runtime.py:1041` 文案「1000..9999」；plan 契约第 2 条新增独立 code |
| `FinsUploadMaterialRequest` 两字段可选、frozen；material 分支只替换 action | 成立 | `ingestion_runtime.py:1571-1572`、`:7694-7713`（`replace(request, action=action)`，`_admit_fins_upload_ticker_identity` 已先行） |
| 三入口先 `_validate_runtime_upload_request` 再创建 producer/observation/job | 成立 | `ingestion_runtime.py:3672`（upload）、`:3869`（prepare_observed_upload）、`:4686`（legacy start_upload）；`start_upload` 在 `:4693` 摘要、`:4705-4709` create/submit 之前完成校验 |
| `build_material_ids` 年 `str()` 直入 seed、period 仅 trim/uppercase；合法 seed 结构/前缀/hash 不变 | 成立 | `docling_upload_service.py:1820-1856`（seed `form\|name[\|year][\|period]`、SHA-1、`mat_` 前缀）；`:2027-2043` 私有 helper 无域检查；`FiscalPeriod` 是 str Literal，canonical 值入 seed 逐字符不变 |
| `_normalize_optional_upload_fiscal_period` 无兼容残留可删 | 成立 | 全仓仅 `docling_upload_service.py:1844/2027` 两处引用，测试零引用 |
| 显式 ID 受稳定 ID 一致性校验；legacy 不可再寻址因果链成立 | 成立 | `docling_upload_service.py:1859-1889`（`validate_material_upload_ids`）；seed 含 fiscal 输入 + 新 admission 拒旧值 + 显式 ID 必须等于稳定 ID；`build_material_ids` 调用点仅 `sec_upload_workflow.py:475`、`cn_pipeline.py:1091`，无 stored-meta 重放/读回旁路，读取面不受影响 |
| US/CN/HK 各自 `str(...).strip().upper()` 后同值投影 ID/事件/meta/result | 成立 | `sec_upload_workflow.py:474-480`（ID）、`:512-513`、`:553-554`（meta）、`:585-586`/`:615-616`（completed/failed result）；`cn_pipeline.py:1090-1095`、`:1128-1129`、`:1169`、`:1201-1202`/`:1231-1232` 同构；HK 共用 `CnPipeline`（`service_runtime.py:251-252`）；plan「ID builder、UPLOAD_STARTED、prepare_upload(meta=...)、completed/failed result 均取同一 canonical 局部值」覆盖全部使用点 |
| manifest 不投影 fiscal 字段、`document_id/internal_document_id` 与 source meta 同源 | 成立 | `document_models.py:1029-1085`（`MaterialManifestItem` 无 fiscal 字段，`from_source_meta` 从 meta 投影两 ID） |
| CLI 只转发、`--forms`/`--material-name`/`--fiscal-year`/`--fiscal-period` 基线 argv 正确、空文本→`None`、usage 错误 exit 2、非整数 year 归 argparse | 成立 | `dayu/cli/commands/fins.py:706-736`（`args.forms`、`args.fiscal_year`、`_optional_stripped_text(args.fiscal_period)`）、`:1263-1276`、`:198-200`；`arg_parsing.py:1145`；plan 真实 CLI 矩阵的 flag 拼写与真实入口一致 |
| tool 请求构造仅 tool/Service 两处，无旁路；tool 域值错误可达同一 Fins usage message | 成立 | `upload_tools.py:351`、`dayu/service/fins_direct.py:341`；`FinsUploadUsageError(ValueError)`（`ingestion_runtime.py:743-765`，`super().__init__(failure.message)`）被 `upload_tools.py:117-123` 的 `except ValueError` 以 `str(exc)` 投影 |
| 新 import 方向不成环 | 成立 | `ingestion_runtime.py:95/120-125` 已 import `filing_semantics`/`docling_upload_service`；workflow 已 import `ingestion_runtime`；调用全沿既有边 |
| 独立 venv/覆盖率/pyright gate 可执行 | 成立 | `.venv` 缺失与 plan 声明一致；`python3.11` 可用（3.11.15）；`constraints/lock-macos-arm64-py311.txt`+`lock-common-py311.txt` 链存在；`pyproject.toml` extras `test/dev/browser` 存在；README §1.1 安装命令与 plan 验证块逐字一致；5 个 `--cov` 目标 = 5 个被改生产文件，双口径（六文件定向子集定位 + `tests/` 全量单文件判定）与 AGENTS.md「单文件 ≥80%」对齐，无预填数字 |
| O05/O11/O16 合流登记与各自裁决一致 | 成立 | O05-F01（form/name 无条件必填、生命周期前拒绝、不先输出 upload.started——plan 行「共用 material admission，汇入时串行复核校验顺序、usage code 与 replace(request, ...)」）；O11-F01（日期真源 `parse_iso_calendar_date`、Fins 前置边界、「仅在 docling_upload_service 后段校验不足以保证」——plan 行「共用 runtime 前置边界，汇入时串行合并并核对同一 canonical 请求」+「日期空文本 shape 归 O11 WU 验收」与总控裁决一致）；O16-F01（action/files 共享前置、优先级不被遮蔽——plan 行一致） |
| O07 合流边界登记 | **不成立，见 finding 01** | plan 残余表登记 O05/O11/O16/O17 而无 O07；goal 非目标明文「不处理 O05/O06 form/name、O07 ID 输入、O17 form canonical 或 action/files」 |
| 新增 material usage 文案的通道中立性被钉住 | **不成立，见 finding 02** | plan 契约第 2 条仅「字段明确、1800..2100」；既有 business-neutral 测试只覆盖三个 code |

## Findings

### 01-未修复-[中]-合流登记漏 O07-F01/F02：同一语义 owner 与同一请求/校验面的邻居未列串行合并条件
- **位置**: plan「依赖、residual 与修复项登记」表（O05/O11/O16/O17 四行有合并条件、无 O07 行）；「范围、直接代码证据与 owner」唯一语义 owner 段；goal 非目标行。
- **问题类型**: 范围漂移（合流边界登记缺失）/ 过度耦合风险（同文件同函数冲突面未约定）。
- **当前写法**: plan 对 O05（「共用 material admission，汇入时串行复核校验顺序、usage code 与 `replace(request, ...)`」）、O11（「共用 runtime 前置边界，汇入时串行合并并核对同一 canonical 请求」）、O16（「优先级与 typed usage 不被本项遮蔽」）逐项登记串行合并条件；对 O07 只在 goal 非目标提「不处理……O07 ID 输入」，残余表与 residual 段均无 O07 去向。
- **反例/失败场景**: `UM-O07-F01`（移除 material 公开 `internal_document_id` 输入）与 `UM-O07-F02`（document_id 不匹配的字段级错误投影与校验边界）随后实施时：(a) O07-F02 要求「由身份 owner 或其直接上游输入校验边界识别不匹配……尽可能在开始上传生命周期前完成校验，并保持零持久化副作用」——正是本计划 `admit_fins_upload_material_fiscal` + validate-before-create 占住的同一边界；无登记则 O07 可能另立第二个 admit/校验顺序，且「fiscal 域错误与 ID 不匹配同时存在时哪个 typed code 先报」无合并依据，错误优先级两 WU 各说各话；(b) O07-F01 要删 `FinsUploadMaterialRequest.internal_document_id`（本计划 `replace(request, ...)` 所在同一 frozen dataclass）、删 `upload_tools.py` 同一 schema 块的输入项（本计划第 4 条重写同一块）、改 `validate_material_upload_ids` 及两 workflow 调用点（紧邻本计划改动的 `build_material_ids` 调用与 canonical 局部值注入点），冲突面密集却无「汇入时串行复核」约定。
- **为什么有问题**: 本 gateflow 的既有实践是把每个共用 admission/身份边界的邻居 WU 的合并条件写进残余表；漏登 O07 会让下一个 WU 失去复核基线，可能产生第二套前置规则或顺序分叉——恰是 goal「不能在 CLI/US/CN/HK/仓储各写一套校验」「O05/O11/O16 同 admission 修改要串行集成，后者复核先前 HEAD，不保留第二套规则」要防的失败模式。更关键的是 O09/O10 用户裁决（binding）原文就声明共享 owner：O09「语义 owner：`docling_upload_service.py` 的 material identity builder/validator（**与 UM-O07-F02 同一 owner**）」；O10「（**与 UM-O07-F02、UM-O09-F01 同一 owner**）」。总控队列 `upload-material-issue-198-repair-sequence-20260928.md` 也把「O05/O06/O07/O09/O10/O11/O12/O17」列为同一前置校验 cohort（「必须在身份生成、`upload.started` 和公司/材料业务提交前给出同源规范化及校验」）。
- **直接证据**: plan 残余表 89-98 行（无 O07 行）；goal 14 行（非目标含「O07 ID 输入」）；`upload-material-um-o07-oracle-adjudication.md`（F01「移除 `dayu-cli upload_material --internal-document-id` 与对应用户输入透传。同步移除 LLM upload tool 的 material `internal_document_id` 输入能力，以及 material 用户请求链路的冗余输入字段」；F02 校验边界与零副作用原则）；O09/O10 裁决同 owner 句；`docling_upload_service.py:1859-1889`（`validate_material_upload_ids` 与本计划 builder 同文件同邻域）；`upload_tools.py:357`（material 请求构造含 `internal_document_id`，与 249-257 schema 块同文件）；`ingestion_runtime.py:1571-1572` 附近（同一请求 dataclass）。
- **影响**: O07 汇入时返工或产生第二套 admission/顺序规则；错误优先级（fiscal 域错 vs ID 不匹配）无验收依据；review 不可对照验收两个 WU 的合并正确性。
- **建议改法和验证点**: 残余表补一行 `UM-O07-F01/F02`：注明与本项共用 material admission/identity owner（O09/O10 裁决同 owner 句为依据），汇入时串行复核（1）fiscal admission 与 ID 一致性校验的先后与 typed code 优先级；（2）`validate_material_upload_ids` 与 `admit_fins_upload_material_fiscal` 是否收敛为同一前置链而不留两套规则；（3）`internal_document_id` 字段移除对 `replace(request, ...)`、两 workflow 注入点与 tool schema 重写块的合并方式；（4）O07-F02 的字段级错误投影不遮蔽本项 fiscal typed usage。验证点：O07 的 plan/实现 review 以该行为对照清单。顺带在同一行或相邻行注明 O06-F01（material name 长度上限）同落 `build_material_ids` 名称处理邻域（O06 裁决「在名称参与身份生成、持久化及 LLM-facing 投影之前统一校验」），其阈值未决细节不属本项。
- **修复风险（低）**: 仅补登记文字，不改本项实现。
- **严重程度（低/中/高/严重）**: 中（binding 裁决明文共享 owner + 同 dataclass 字段移除 + 同文件密集冲突面；后果是集成期返工/规则分叉而非本 S1 代码错误，故不评为高）。

### 02-未修复-[低]-新增 `INVALID_MATERIAL_FISCAL_YEAR` 文案的通道中立性未被计划钉住
- **位置**: plan「最小实现契约与数据流」第 2 条（「增加独立 `FinsUploadUsageCode.INVALID_MATERIAL_FISCAL_YEAR` 与文案（字段明确、1800..2100）」）；S1 测试契约 tool 段（只断言「同一 Fins usage message」）。
- **问题类型**: LLM-facing 文本准确性风险 / 测试缺口。
- **当前写法**: 新文案只要求「字段明确、1800..2100」，未要求业务中立（无入口术语）；S1 对该 message 只断言跨路径一致，不断言文案风格；既有 `test_upload_tool_calendar_year_schema_and_usage_messages_are_business_neutral` 的 `"--" not in message` 断言只覆盖 `INVALID_FISCAL_YEAR`/`INVALID_FILING_DATE`/`INVALID_REPORT_DATE` 三个 code。
- **反例/失败场景**: `_USAGE_MESSAGES` 里多数文案是 `--flag` 风格（如 `MISSING_FISCAL_YEAR: "--fiscal-year 不能为空"`）；实施者就近模式匹配写出 `--fiscal-year 必须是 1800..2100` 类文案，该 message 经 `FinsUploadUsageError` 直投 LLM（`upload_tools.py:117-123`），新造一条带入口术语的 LLM-facing 文本且无测试拦截；`fins-upload-usage-message-channel-neutral` 登记时该文案还不存在，纯属本 WU 新增债务。
- **为什么有问题**: AGENTS.md LLM-facing 硬约束要求投影给 LLM 的错误说明不使用入口实现术语、对无状态模型自足；本项在该通道新造文本就应一次写对，而不是先欠再清。相邻的 `INVALID_FISCAL_YEAR` 文案「财年（fiscal_year）必须是 1000..9999 的整数」正是业务中立范本，plan 却未指定跟随。
- **直接证据**: `ingestion_runtime.py:1027-1056`（`_USAGE_MESSAGES` 条目风格分布；`INVALID_FISCAL_YEAR` 中立 vs `MISSING_FISCAL_YEAR`/`UNSUPPORTED_FISCAL_PERIOD` 带 `--`）；`test_fins_ingestion_tools.py:1732-1737`（neutrality 断言仅三个 code）；plan 契约第 2 条与 S1 测试契约相应句。
- **影响**: 新 LLM-facing 文案可能带 CLI flag 术语并通过全部 gate；后续 `fins-upload-usage-message-channel-neutral` 需返工清理本 WU 新增文本。
- **建议改法和验证点**: 契约第 2 条补一句：新文案按 `INVALID_FISCAL_YEAR` 的业务中立风格书写（字段名 + 1800..2100，无 `--flag` 等入口术语）；S1 测试对新 code 同样断言 `"--" not in message` 与逐字文案。验证点：business-neutral 断言面覆盖新 code。
- **修复风险（低）**: 低——一行措辞 + 一条断言。
- **严重程度（低/中/高/严重）**: 低。
- **残余**: material period 域值错误复用 `UNSUPPORTED_FISCAL_PERIOD`（文案含 `--fiscal-period`）是总控裁决明确接受的现状，归 `fins-upload-usage-message-channel-neutral` 清理，不在本项扩散。

## Open questions

1. **O06-F01 是否随 finding 01 一并登记**：O06（material name 长度上限）的裁决 owner 是「material metadata/identity 的名称校验真源」，落点邻近 `build_material_ids` 的名称处理（本计划契约第 1 条改动面内），goal 非目标把 O05/O06 并列。任务本轮聚焦点名 O07；O06 是否同表登记由总控裁决一行定夺（建议登记，阈值未决细节仍归 O06 WU）。
2. **Kimi 第二路**：总控裁决记录 Kimi 403 两轮缺位；本 artifact 只构成 MiMo 单路结论，按停止条件不作为 plan gate 通过，双路有效性由总控判定。

## Residual risks 与去向

| 风险 | 去向 |
| --- | --- |
| 旧非法 fiscal 身份不可再寻址（seed 含旧值；新 admission 拒旧值；换值/省略变 seed；显式旧 ID 被 `validate_material_upload_ids` 拒绝；本轮重证无 stored-meta 重放路径，读取面不受破坏） | plan 已登记 `fins-material-legacy-invalid-fiscal-identity-recovery`（独立待裁决）；与 `fins-material-legacy-identity-seed-disposition` 归属由总控集成前核对；维持现状 |
| 复用 `UNSUPPORTED_FISCAL_PERIOD` 文案含 `--fiscal-period`，tool 投 LLM 通道不纯 | 总控裁决已接受并登记 `fins-upload-usage-message-channel-neutral`；finding 02 只要求新文案不新增同类债务 |
| filing schema 分句未说明大小写/首尾空白归一化（filing 实际也走 trim+upper 归一，`ingestion_runtime.py:1276-1287`），与 material 分句的显式 trim/upper 不对称 | 行为影响极小（模型只会发 canonical 值，多接受不误拒）；如追求两句完全对称可在实现时顺手补半句，不作本轮 finding |
| plan schema 规格把 filing 的省略/`null` 与空串/纯白描述成两种错误样式，tool 实际是同一 `invalid_argument`/同一文案（`_required_text` 一处抛） | S1 测试钉实际码与零副作用即可验收；实现 review 对照行为测试，不以 schema 文案的错误分类为 contract |
| `" q1 "` 与 `Q1` 的 CLI 稳定 ID 对比句未写明预期关系（相等）；owner 层「相同 canonical 输入得到相同稳定 ID」已钉 | 实现 review 核对 CLI 对比场景的断言方向为相等 |
| 下游 `ProcessedManifestItem` 含 fiscal 字段且由 `_build_processed_meta(source_meta=...)` 从 source meta 派生（`ingestion_runtime.py:8509` 附近）；S1 未覆盖 process 链路投影 | 维持第一轮 review 记录：实现 review 抽查 process 链路读 source meta 断言，或归后续 process 链路 WU |
| Sol 修订 run 按 sub-agents 严格协议 `agent_status=failed`（`git diff --no-index` 返回 1） | 本轮已对计划 SHA 与全部关键代码事实独立重证；执行协议状态由总控另行处置 |
| 全量覆盖率、真实 CLI 矩阵、锁定 venv 安装均未实测（本 gate 只静态核对） | implementation gate 按 plan 验证节执行并逐文件抄录实测数字；plan 已有不虚报口径 |
| 冻结场景不是修复后证据 | implementation / review gate 补跑 O09/O10 待补跑清单（与 plan 真实 CLI 矩阵一致） |

## 验证记录（本轮执行）

- 预检：plan SHA-256 实测 = `5c3bbee5…81a5`（与任务给定一致）；HEAD = `8d8d494f`；canary 文件已读。
- 文档核对：goal、总控裁决、O05/O06/O07/O09/O10/O11/O16 用户裁决（主工作区只读）、总控队列 repair-sequence、上三轮复审、AGENTS.md、plan 全文。
- 代码核对（file:line 独立重证）：`_required_text`/`_optional_nullable_text`/`_optional_int`/`_required_int` 参数层行为；`_upload_request_from_arguments` filing/material 分支；`normalize_fiscal_period`/`normalize_fiscal_year`/`FiscalPeriod`；`_USAGE_MESSAGES`；三入口 validate-before-create 顺序（3672/3869/4686/4693/4705）；`build_material_ids`/`validate_material_upload_ids`/`_normalize_optional_upload_fiscal_period` 及全部调用点；US/CN/HK workflow 全部 fiscal 投影点（512/553/585/615；1128/1169/1201/1231）；`MaterialManifestItem.from_source_meta`；CLI `upload_material` 参数与 `_optional_stripped_text`。
- 迁移清单核查：`tests/fins/test_fins_ingestion_tools.py:1718-1723` 逐字断言定位精确；全仓 grep 该文案与 `1000..9999`/`时可选`/`build_material_ids`/非法 fiscal fixture，确认无遗漏迁移对象、无固化宽松 material 行为的既有测试。
- 环境核查：`.venv` 缺失属实；`python3.11` 3.11.15；constraints 链与 extras 存在；README §1.1 安装命令与 plan 一致；tool 层无 jsonschema 强校验（`null` 可达参数读取层）。
- 反证尝试未得手：schema 三分句与逐句行为对照、迁移清单完备性、1800..2100/六枚举对用户裁决逐字对照、seed/manifest 同源链、O05/O11/O16 登记与裁决对照、覆盖率口径与 AGENTS.md 对齐、真实 CLI flag 拼写。
- 未执行：全量测试、覆盖率实测、真实 CLI、venv 安装（均属 implementation gate）；未读另一模型同轮复审；未派发子 Agent；除本 artifact 外未改任何文件。

## Final plan review conclusion

`pass-with-risks`。

两个任务指定攻击面（共用 `fiscal_period` schema 逐句自足、旧逐字测试迁移清单）均经代码直接证据核实成立，且计划文字已封死上一轮的语境错位反例；核心方案（owner 划分、同源数据流、filing 边界、零副作用顺序、真实 CLI/tool 验证矩阵、独立 venv 与双口径覆盖率 gate）无 goal drift、无过度设计。新增 finding 01（O07 合流登记缺失，中）与 finding 02（新 usage 文案中立性未钉，低）均为 plan 文本级收敛项；其中 finding 01 依据 binding 用户裁决的同 owner 声明与同文件冲突面，应在实施前补登记。本结论为 MiMo 单路 plan review，不构成 plan gate 通过；仍待 Kimi/MiMo 双路有效复审。

CANARY=mimo-823d05db
