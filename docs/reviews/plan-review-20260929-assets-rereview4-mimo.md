# Plan Review（独立复审）：UM-O04-F01 + UM-O23-F01 material 资产数量与身份规划（第四次修订）

RUNTIME/PROVIDER/MODEL: claude/mimo/mimo-v2.6-pro[1m]
CANARY=mimo-96bbb6d7

- Review label：`assets-plan-rereview4-mimo-20260929-04`；gate：plan review -> fix（独立复审，核对总控对第三轮 MiMo F5/F6/OQ1–3 的裁决落实与第四次 Sol 修订，并专项反证新 `upload_usage_contract.py` 迁移是否过度或成环）。
- 审查对象：`docs/gateflow/upload-material-assets-plan-20260929.md`（SHA-256 实测 `e1d9151a97c11cbf1b2f5552cb3ca2880a28fde89e9f3a7179883f16baa98c66`，与任务预期及 `docs/gateflow/upload-material-assets-plan-review-adjudication-20260929.md` 末段记录一致，无版本冲突）。
- Binding goal：`docs/gateflow/upload-material-assets-goal-20260929.md`（SHA-256 实测 `208d4008caa8e6a0c870a1e1f929e3c706e0bbbdb97ef89f3c6d6c1888f86e36`，与前轮 review 记录一致，goal 未变）。
- 核对依据：总控裁决 `docs/gateflow/upload-material-assets-plan-review-adjudication-20260929.md`（MiMo 首轮 F1-F7、Kimi 首轮 F1/F2/F4、第二轮 MiMo F1-F4、第三轮 MiMo F5/F6/OQ1–3 与四次 Sol fix 记录），前轮 `docs/reviews/plan-review-20260929-055331-assets-mimo.md`（MiMo 第三轮）及 `plan-review-20260929-051109.md`、`plan-review-20260929-033914.md`、`plan-review-20260929-023619.md` 作为待复证 finding 清单。
- 依据 HEAD：`8d8d494fbbce0052372fb1b42097c9f7222cfa28`（审查开始时 `git rev-parse` 实测一致；工作区仅 7 个未跟踪 gateflow/review 文档，无产品改动）。
- 全部断言直接读取本 HEAD 源码/测试与实测得出，不采信候选 plan 或 Sol 自述；未实施任何 fix、未改 plan/goal/adjudication/产品/测试/README/既有 review、未 commit/push/PR、未派发子 Agent、未发外部消息。

## 审查范围

按任务焦点：(1) 逐项核对第三轮裁决落实——F5 第三处 storage 控制名 consumer（`_fs_maintenance_core.py` rejected filing artifact walker）、F6 CLI 文件预检 exit 2 落点与回归断言、OQ1 Fins usage message 唯一 owner 的 `upload_usage_contract.py` 迁移是否过度或成环、OQ2 显式 upsert/delete 模式、OQ3 `META.JSON` reserved reason 归属；(2) 按源码枚举 usage contract 全体符号的定义点、imports/调用方、循环反例与白名单/测试覆盖，找最小反例；(3) adversarial 复证旧高/中项不回退：100/101、唯一 Docling 派生命名函数、filing identity 字节、raw/validated handoff、O25 边界；(4) goal drift、架构边界、过度耦合、执行时序与测试缺口检查。

## Assumptions tested（HEAD 直接证据重证）

| # | Plan / 裁决断言 | 重证结果 | 直接证据 |
| --- | --- | --- | --- |
| A1 | usage 迁移 5 符号均定义于 `ingestion_runtime.py` | 成立 | `ingestion_runtime.py:673` `FinsUploadUsageCode`、`:708` `FinsUploadUsageFailure`、`:743` `FinsUploadUsageError`、`:1027` `_USAGE_MESSAGES`、`:1062` `fins_upload_usage_failure`；导出列表（`:9120-9144` 一带）不含 usage 符号，无 `__all__` 迁移义务 |
| A2 | usage 符号全体消费面 = 生产 3 处 + 测试 5 文件 | 成立（`test_filing_upload_publication.py` 例外，见 Finding 04c） | 生产：`dayu/cli/commands/fins.py:60/:198`（import + catch）、`dayu/fins/pipelines/_filing_upload_fresh_validation.py:13-17`（import `FinsUploadUsageError` + request 类型）、`dayu/fins/pipelines/filing_upload_publication.py:22-23`（import `FinsUploadUsageCode/Error` + request 类型）；`service_runtime.py:77` 仅 docstring 提及，无 import。测试：`test_fins_ingestion_runtime.py:119-128`、`test_fins_ingestion_tools.py:40/:43`、`test_fins_service_runtime.py:27-28`、`test_sec_pipeline_upload_filing_stream.py:41-42`、`test_cn_pipeline.py:30-31`。`rg 'FinsUploadUsage(Code\|Error\|Failure)\|fins_upload_usage_failure\|_USAGE_MESSAGES' dayu/ tests/ utils/` 全库除此无他处 |
| A3 | 环风险真实存在，迁移动机成立 | 成立 | `ingestion_runtime.py:133-138` `from dayu.fins.upload_failure import (...fins_upload_failure_from_exception, upload_failure_reason_from_json...)`；`upload_failure.py` 头部 import 无 `ingestion_runtime`（现况无环）；故 `upload_failure` 若需 usage 文案而回 import `ingestion_runtime` 即成 `upload_failure -> ingestion_runtime -> upload_failure` 环——plan 的环陈述与源码一致 |
| A4 | 提议 import 图（usage owner 下沉）无环 | 成立 | `upload_usage_contract -> upload_asset_plan + upload_format_contract`；`upload_format_contract.py:8-22` 仅 import `dayu.documents.docling_runtime` + `dayu.fins.direct_events` + stdlib；`direct_events.py`/`docling_runtime.py` 无 `ingestion_runtime`/`upload_failure` 引用（rg 实测空）；全库引用 `ingestion_runtime` 的模块清单（20 个，含 README）不含上述底层链任何成员；`FinsUploadFormatFailureKind` 定义于 `upload_format_contract.py:41`（非 `upload_failure.py`），`FinsUploadUsageFailure.code` 的 union 依赖不成环 |
| A5 | 迁移粒度不过度 | 成立 | 5 符号为内聚单元：message map 以 `FinsUploadUsageCode` 为键、failure dataclass 校验 code union、异常携带 failure、工厂格式化 map；拆分（如模板与 enum 分居）会新增 `upload_usage_contract -> ingestion_runtime` 取 enum 的环边或 stringly 键。最小替代（保持在 `ingestion_runtime`）在 A3 下不可行 |
| A6 | F5 三消费点现状与 exact 语义 | 成立 | `_fs_storage_utils.py:20` `_SOURCE_META_FILENAME="meta.json"`；`_fs_identity.py:40` `_IDENTITY_DESCRIPTOR_FILENAME=".identity.json"`；成员判定内联集合恰三处：`_fs_source_integrity.py:669`（declared 名 exact 拒绝，return None）、`:856`（物理 walker exact 跳过）、`_fs_maintenance_core.py:579-583`（rejected filing artifact 物理/声明比对 exact 跳过后 `physical_files != expected_files` 判不一致）；frozenset 替换 set 字面语义不变 |
| A7 | F5 括号断言"两模块原有直接 import 底层常量仍供其它规则使用" | **部分不成立** | `_IDENTITY_DESCRIPTOR_FILENAME` 在两模块的全部用途即上述迁移集合字面（`_fs_source_integrity.py:31/:669/:856`、`_fs_maintenance_core.py:23/:581-582`），迁移后 import 成 dead；`_SOURCE_META_FILENAME` 确有其它用途（`_fs_source_integrity.py:479`、`_fs_maintenance_core.py:554` 的 meta_path）。见 Finding 03 |
| A8 | F6 现状落点与 plan 钉死一致 | 成立 | `_validated_upload_files` 唯一调用方 `fins.py:728`（material raw request 构造处）；实现 `fins.py:1128-1147`（`expanduser().resolve(strict=False)` + `exists()` + `is_file()`，`CliFinsUsageError(_MISSING_UPLOAD_FILE_TEMPLATE)`）；模板 `fins.py:98-99`（英文 `"upload file does not exist: {path}"` / `"upload path is not a file: {path}"`，含解析后全路径）；`FinsUploadUsageError` handler `fins.py:198-200` → `EXIT_USAGE_ERROR`（exit 2）；`rg 'upload file does not exist\|upload path is not a file' tests/` 零命中——F6 新增两例确为新回归钉 |
| A9 | OQ2 显式模式输入域完整 | 成立 | raw `FinsUploadMaterialRequest.action: str = _UPLOAD_ACTION_AUTO`（`ingestion_runtime.py:660/:1565`），合法域 auto/create/update/delete（`_USAGE_MESSAGES[INVALID_ACTION]` `:1032`、校验 `:1265`）；resolved 判定 owner 为 `docling_upload_service.py:1892` `resolve_upload_action`（`cn_pipeline.py:1116`、`sec_upload_workflow.py:29` 消费）；delete 禁携 files/primary（`:1291-1295`）。plan 将 auto/create/update→upsert、delete→delete 显式传 planner，覆盖合法域全集 |
| A10 | OQ3 分类归属已钉 | 成立 | plan 行 45：exact 控制名及其 case/Unicode 变体经保守键命中统一归 `RESERVED_CONTROL_NAME`（例 `META.JSON`），真实业务 original/derived 相撞归 `ASSET_NAME_COLLISION`，"控制名分类不依赖原件遍历顺序" |
| A11 | 100/101 与 `_MAX_TUPLE_ITEMS` 边界未回退 | 成立 | `MAX_MATERIAL_UPLOAD_FILES = 100` 归 `upload_asset_plan.py`（plan 行 16/24）；1..100 放行、101 前置 typed 拒绝；`_MAX_TUPLE_ITEMS=100`（`:167`）5 处用途：`:1180` alias、`:1266` filing files、`:7530` 通用 tuple、`:7874` material 摘要计数、`:7912` metadata——plan"保留给通用 tuple/摘要及既有 filing/alias 用途，不得成为 material 数量真源"与实况吻合；`_validate_upload_file_count`（`:7861-7875`）现以裸 `ValueError("upload_files 元素数量超出上限")` 在摘要触发，plan"摘要只消费 validated handoff 的数量事实"将其移除；tool schema `maxItems: 100`（`upload_tools.py:243`）共用，plan 登记 F-R5 类残余 |
| A12 | filing identity 字节未回退 | 成立 | 常量 `docling_upload_service.py:78-81`：`DOCLING_FILE_SUFFIX="_docling.json"`、`_FILING_ASSET_IDENTITY_NAMESPACE="fins-upload-asset-v1"`、`_FILING_ASSET_IDENTITY_SEPARATOR=b"\0"`、`_FILING_ORIGINAL_ASSET_PREFIX="original-"`；`_build_filing_original_asset_identity`（`:1511-1535`）guard `is_absolute` 且 `resolve(strict=False)==normalized_path`，digest 输入 `namespace.encode("utf-8")+b"\0"+as_posix().encode("utf-8")`，输出 `original-<完整 hexdigest><suffix.lower()>`；`_build_filing_derived_asset_identity`（`:1538-1553`）require `original-` 前缀后追加 `_docling.json`。plan 行 20 的迁移描述逐字吻合，且"迁入此 owner 并删除旧函数" |
| A13 | 唯一命名函数动机与迁移面成立 | 成立 | `docling_upload_service.py:928-930` material original 名 `file_path.name`；`:1029` 派生名 `f"{file_path.stem}{DOCLING_FILE_SUFFIX}"`（stem 冲突动机成立）；identity helper 模块外导入恰 4 测试文件（`test_docling_upload_service.py`、`test_fins_ingestion_runtime.py:131`、`test_cn_pipeline.py:46`、`test_sec_pipeline_upload_filing_stream.py:50`），plan 行 64 点名一致；统一函数 `docling_storage_name(source_kind, original_storage_name)` 单 owner、material 完整名+后缀、filing 前缀校验+身份加后缀（plan 行 20） |
| A14 | raw/validated handoff 链路与 plan 接线对应 | 成立（observation 协议触点缺列，见 Finding 02） | raw `FinsUploadMaterialRequest.files: tuple[Path, ...] = ()`（`:1567`）——"用预检 tuple 构造 raw material request"类型成立；`FinsRuntimeUploadRequest = FinsUploadRequest \| ValidatedFinsUploadFilingRequest`（`:1582`）；`_validate_runtime_upload_request` isinstance 透传先例（`:4714-4748`）；`upload_tools.py:101-105` 现状 `_upload_request_from_arguments` → `runtime.prepare_observed_upload(request, ...)` 无 admission；协议 `ingestion/observation_handle.py:240/:254` `start_observed_upload/prepare_observed_upload(request: FinsUploadRequest, ...)`，实现 `ingestion_runtime.py:3820/:3848`，fake `tests/service/test_fins_wait_adapter.py:916/:932`、`tests/fins/test_fins_ingestion_tools.py:603/:619` |
| A15 | `_MAX_TEXT_CHARS`/`_FILE_USAGE_CODES` 是迁移伴随件 | 成立（plan 未列，见 Finding 01） | `_MAX_TEXT_CHARS=240`（`:166`）：usage 用途 `:739`（failure message 上界）、`:1095`（工厂 message 上界）；非 usage 用途 `:1277/:1368/:7106-7107/:7403/:7478/:9000-9002` 共 7 处。`_FILE_USAGE_CODES`（`:1021-1025`，`FILE_NOT_FOUND/FILE_NOT_REGULAR`）仅 `:1081` 工厂消费。`download_contract.py:43` 有 per-contract 240 常量先例 `FINS_DOWNLOAD_PUBLIC_MAX_TEXT_CHARS` |
| A16 | O25 边界未回退 | 成立 | plan 行 12（不改 O25 primary 选择规则、首转换 primary 不升格公开契约）、行 54（"O25 后续只能变选择与相应指纹/skip 事实，不能另算资产名"）、行 86（O25 依赖与"不能将其称为本工作单已解决"） |
| A17 | `_normalize_filename` 会 `strip()`、无保留名/长度校验 | 成立 | `_fs_storage_utils.py:29-52`（`_normalize_path_component` strip 后校验分隔符/绝对路径）、`:71` `_normalize_filename`；plan 行 18"现在 `_normalize_filename` 会 `strip()`，并**没有**保留名或长度校验；不能写成复用既有保留名检查"表述准确 |
| A18 | goal/plan/HEAD 三者一致，无 goal drift | 成立 | plan SHA `e1d9151a…98c66`、goal SHA `208d4008…6e36`、HEAD `8d8d494f…` 均实测一致；plan 行 3 记录 HEAD 与候选状态吻合；goal 的"100 个以内允许，101 个前置拒绝""一个 original→Docling 函数"等成功信号未被拔高或缩水 |

## 逐项核对：第三轮 F5/F6/OQ1–3

| 项 | 裁决要求 | 本复审核实 | 结论 |
| --- | --- | --- | --- |
| F5 第三处 storage 控制名 consumer | `_fs_maintenance_core.py:579-583` 同切片消费唯一集合，精确进生产白名单与 storage 测试，exact 行为不变、无环 | plan 行 18 三消费点行为序列"exact `name in set` 拒绝、exact `child.name in set` 跳过、exact `child.name in set` 跳过"与 A6 实况逐一对应；生产白名单含 `_fs_maintenance_core.py`（行 62"三处都只消费唯一控制名集合，exact 行为不变"）；测试句（行 64）覆盖"三个消费点对 exact 控制名分别维持原拒绝/跳过结果"；import 图含 `_fs_maintenance_core.py -> asset_filename_contract.py` 且"第三处改用集合不成环"（A4 证实可行）；但括号断言对 `_IDENTITY_DESCRIPTOR_FILENAME` 失实（A7） | **已落实**，见 Finding 03 |
| F6 CLI 文件预检 exit 2 | raw request 构造前保留 exists/is_file 预检与既有文案/exit 2，helper 不再构造 selection，补 material 缺失文件/目录两例断言 | plan 行 51 钉死 helper 改为"只返回预检路径 tuple"（逐项 `expanduser().resolve(strict=False)`、`exists()`、`is_file()`），保持 `CliFinsUsageError`、双模板、exit 2、"现有包含解析后路径的文案"，"不在该 helper 构造会丢失的 `FinsUploadMaterialFiles` selection"，"用预检 tuple 构造 raw material request"；行 64/68 两例断言"raw request/service/converter 均未启动、exit 2、stderr 与现有 CLI 英文模板和解析后完整路径逐字一致"，且"不要把缺单个文件/目录改判为 `MISSING_FILES`"；A8 证实模板/调用方/空测试缺口均与钉死点吻合 | **已落实** |
| OQ1 usage message 唯一 owner | 三个复用 code 文案由唯一 owner 提供，planner 只产 typed fact；100 上限绑定登记残余；不暗改 filing 文案 | plan 行 30/47/68：`MISSING_FILES`/`TOO_MANY_FILES`/`DUPLICATE_FILE_PATH`"必须复用原有 usage 文案"，`TOO_MANY_FILES` 模板由调用方传入已判 source 上限（material= `MAX_MATERIAL_UPLOAD_FILES`、filing=其现有 100 上限），"当前输出逐字一致"（A11 证实 filing 当前文案 "--files 数量不能超过 100 个" 参数化后逐字保持）；`ingestion_runtime` usage 构造与 `upload_failure` planner 分类"调用这一 owner 的 typed 投影取同一文案/retry hint，不复制模板"；上限分离残余登记（行 28/88）。**迁移本身不过度、不成环**（A3/A4/A5），但迁移清单的伴随件与措辞精度留有最小反例 | **已落实**，见 Finding 01/04 |
| OQ2 显式 upsert/delete 模式 | planner 收显式已判定模式及原始路径/selection，不从 auto/空 files/源状态猜；delete 空 plan 绕过 upsert 校验 | plan 行 22："Fins admission 唯一将 raw action 判为资产操作模式 `Literal["upsert", "delete"]`，连同原始路径/selection 显式传给 planner"；"planner 不从 `auto`、空 files 或既有 source 状态猜模式"；"delete 生成唯一空 selection/空 plan，跳过 upsert 的文件数、命名和碰撞检查，仍保持既有 delete/action 校验"；A9 证实 action 域与既有 delete 校验边界；验证矩阵（行 68）"显式 upsert…显式 delete 生成空 plan 且不触发 upsert 校验，`auto/create/update` 仅由 Fins admission 判为 upsert" | **已落实** |
| OQ3 `META.JSON` reserved reason | case/Unicode 变体归 `RESERVED_CONTROL_NAME`，业务相撞归 `ASSET_NAME_COLLISION`，测试钉 `META.JSON`，顺序无关 | plan 行 45 逐句落实（A10）；验证矩阵"控制名 `meta.json`/`.identity.json` 及其 case 变体均在 converter 前拒绝，`META.JSON` 明确归 `RESERVED_CONTROL_NAME`…分类不随遍历顺序变化" | **已落实** |

## 前轮高/中项 adversarial 复证（是否回退）

| 项 | 复证 | 结论 |
| --- | --- | --- |
| 100/101 边界 | A11：常量归规划 owner、1..100/101 前置拒绝、`_MAX_TUPLE_ITEMS` 降格、摘要消费 validated 数量事实、真实 CLI 分级（101 typed/converter 0/零发布；100 侧 admission 全接受+至少首个 converter 启动、不冒充成功发布；受控 converter 100 次调度；小 N 同 stem 完整发布）与第二轮裁决口径逐句保持（plan 行 82/90） | 未回退 |
| 唯一 Docling 派生命名函数 | A13：`docling_storage_name(source_kind, original_storage_name)` 单一 owner；material 完整原件名加后缀（不 stem/不序号/不 hash 截断）；filing 前缀校验+身份加后缀；身份规则迁入并删除旧函数、四处测试导入同切片改向、"不留 re-export、wrapper 或双实现窗口" | 未回退 |
| filing identity 字节 | A12：namespace/`b"\0"`/完整 SHA-256/`suffix.lower()`/`_docling.json` 逐字保持；"旧 original/derived identity 逐字一致"测试在验证矩阵（行 69）；"filing 原件身份算法不变" | 未回退 |
| raw/validated handoff | A14 + plan 行 16/49-53：raw façade 与必填 `upload_material_validated` 分名、每链 admission 恰好一次、runner 传原 handoff 不展开、无 `raw\|validated` 联合/可空 plan/isinstance 双路补救、旧 scalar 同切片消失；唯一残留缺口是 observation 协议类型触点未列名（Finding 02），handoff 语义本身未回退 | 未回退 |
| O25 边界 | A16：只稳定名称映射与 pair 身份；O25 后续只改选择规则与同源指纹/skip/meta/read；首转换 primary 风险记为依赖不宣称解决 | 未回退 |

## 专项：usage contract 全体 imports/调用方枚举与循环反证

**定义面（5 符号 + 2 伴随件）**：全部定义于 `ingestion_runtime.py`（A1）。伴随件 `_FILE_USAGE_CODES`（`:1021`）被工厂 `:1081` 消费，自然随迁；`_MAX_TEXT_CHARS`（`:166`）被 usage 处（`:739/:1095`）与 7 处非 usage 共用，不能整体随迁——见 Finding 01。

**生产消费面（3 个模块 + 1 处 docstring）**：`fins.py`（import+catch+exit 2 投影）、`_filing_upload_fresh_validation.py`（import + `:62` catch）、`filing_upload_publication.py`（import + `:71-76` code 集合 + `:746` catch）、`service_runtime.py:77`（仅 docstring）。前三者均已列 plan 生产白名单（"后两者仅迁移 usage 类型的 import"属实：两文件的 `ingestion_runtime` import 中 request/validate 类型不迁移）。

**测试消费面（5 文件）**：`test_fins_ingestion_runtime.py`、`test_fins_ingestion_tools.py`、`test_fins_service_runtime.py`、`test_sec_pipeline_upload_filing_stream.py`、`test_cn_pipeline.py`——全部在 plan 测试白名单。`test_filing_upload_publication.py` 无 usage import（仅 `:107` docstring），plan 纳入理由失实（Finding 04c）；`test_filing_upload_publication.py:34-38` 的 import 是 `FinsUploadFilingRequest/ValidatedFinsUploadFilingRequest/validate_fins_upload_filing_request`，不在迁移面。

**循环反证**：现况边 `ingestion_runtime -> upload_failure`（`:133`，`fins_upload_failure_from_exception`/`upload_failure_reason_from_json` 在 `:4511/:4994/:1773` 消费）使"usage 文案留在 `ingestion_runtime` 且 `upload_failure` 取同一文案"必然成环（A3）。下沉后提议图 `upload_usage_contract -> {upload_asset_plan, upload_format_contract}`、`upload_failure -> {upload_usage_contract, upload_asset_plan}`（后者为分类 `FinsUploadAssetPlanError` 所必需）、`ingestion_runtime -> {upload_usage_contract, upload_asset_plan}`——全部单向，底层链（`upload_format_contract -> docling_runtime/direct_events`、`asset_filename_contract -> _fs_identity -> _fs_storage_utils`）经 rg 证实不反向引用 `ingestion_runtime`/`upload_failure`（A4）。`_MAX_TEXT_CHARS` 若被实现者从 `ingestion_runtime` 取用会新增一条未在图上的短环——这是本轮唯一实测到的最小成环反例，plan 现文本未排除（Finding 01）。

**最小反例汇总**：(1) `_MAX_TEXT_CHARS` 随迁边界 → 短环或双常量（Finding 01）；(2) `FinsUploadRequest`/`FinsRuntimeUploadRequest` 裸别名消费者（`observation_handle.py`、`test_fins_wait_adapter.py` 等）不在 rg 对账模式与白名单内（Finding 02）；(3) `_IDENTITY_DESCRIPTOR_FILENAME` 迁移后 dead import 与 plan 断言相反（Finding 03）；(4) retry hint"迁来物"不存在、filing 上限参数未点名、`test_filing_upload_publication.py` 理由失实（Finding 04）。

## Findings

### 01-未修复-低-`upload_usage_contract` 迁移的伴随长度常量 `_MAX_TEXT_CHARS` 归属未钉，存在最小 import 环/双常量反例
- **位置**: §唯一 owner 与纯规划契约（"现有 `FinsUploadUsageCode`、`FinsUploadUsageFailure`、`FinsUploadUsageError`、`_USAGE_MESSAGES` 与 `fins_upload_usage_failure` 的**定义**迁至新的低层 Fins usage owner……该模块只依赖 `upload_asset_plan.py` 的 typed reason/参数和既有底层格式类型"句）
- **问题类型**: 语义所有权 / import 图完整性
- **当前写法**: 迁移清单恰为 5 个符号；usage owner 依赖被限定为 planner typed reason/参数 + 底层格式类型。
- **反例/失败场景**: `FinsUploadUsageFailure.__post_init__`（`ingestion_runtime.py:739`）与 `fins_upload_usage_failure`（`:1095`）都引用 `_MAX_TEXT_CHARS`（定义 `:166`，值 240）。该常量另有 7 处非 usage 用途（`:1277` fiscal-period 长度、`:1368` 文本长度、`:7106-7107` 事件 message 截断、`:7403/:7478/:9000-9002` 文本截断），不能整体随迁。实现者若从 `ingestion_runtime` import 它，即成 `ingestion_runtime -> upload_usage_contract -> ingestion_runtime` 短环（`ingestion_runtime:133` 已引 `upload_failure`，环一旦出现触发 plan 硬停止"Fins usage message 无法无环单源"，切片中断）；若就地复制 240，形成双常量，违反"重复逻辑必须抽取/禁止魔法值"。同理 `_FILE_USAGE_CODES`（`:1021`，工厂 `:1081` 消费）须随工厂迁入但未列名。
- **为什么有问题**: plan 自称"该模块只依赖……"，但迁移单元的真实依赖含该常量；CLAUDE.md 语义所有权要求消息长度上界这类 contract 不变量只有唯一 owner。`download_contract.py:43` `FINS_DOWNLOAD_PUBLIC_MAX_TEXT_CHARS: Final[int] = 240` 已有 per-contract 独立上界先例，plan 未援引也未指定归属。
- **直接证据**: `rg '_MAX_TEXT_CHARS|_FILE_USAGE_CODES' dayu/ tests/` 命中如上；`ingestion_runtime.py:133-138`；`test_fins_ingestion_runtime.py:1389-1520` 的工厂 owner 测试（closed/bounded/path-free）现挂在旧模块测试文件，迁移后归属未定。
- **影响**: 实施中 import 环（硬停止）或静默双常量；工厂 owner 测试可能滞留旧测试文件，违反"测试必须跟着实现边界迁移"。
- **建议改法和验证点**: plan 一句钉死——usage message 长度上界由 `upload_usage_contract` 持有独立 named 常量（对齐 download_contract 的 per-contract 先例），禁止从 `ingestion_runtime` 取 `_MAX_TEXT_CHARS` 或复制裸值，`_MAX_TEXT_CHARS` 留在 `ingestion_runtime` 服务其非 usage 用途；`_FILE_USAGE_CODES` 随 `fins_upload_usage_failure` 迁入 usage owner 作私有成员；`test_fins_ingestion_runtime.py:1389` 起的工厂 closed/bounded/path-free 测试随迁 `tests/fins/test_upload_usage_contract.py`。验证点：pyright 全绿且 `python -c 'import dayu.fins.upload_usage_contract'` 无环；`rg '_MAX_TEXT_CHARS' dayu/fins/upload_usage_contract.py` 零命中。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 02-未修复-低-observation 协议是 validated handoff 必经类型触点，生产/测试白名单与 rg 对账模式均未覆盖
- **位置**: §typed 失败和跨入口 handoff 第 2 条（"Tool `upload_tools.py` 与其它非 CLI runtime 入口在 observation/job 创建前调用同一 admission……若已 validated 直接传同一对象"）；§一个端到端可验收切片及文件范围（生产/测试白名单与 rg 对账模式）
- **问题类型**: 契约缺失 / 迁移面缺列
- **当前写法**: tool 在 observation/job 创建前调用 admission，随后 handoff"原样"进入 runtime 链；生产白名单 18 文件、测试白名单 16 文件、rg 模式 `upload_material\(|upload_material_stream\(|FinsUploadMaterialRequest|FinsUploadUsage(Code|Error|Failure)|fins_upload_usage_failure|_normalize_fins_upload_path|_fins_upload_path_identity|_build_filing_original_asset_identity|_build_filing_derived_asset_identity`。
- **反例/失败场景**: `upload_tools.py:101-105` 现状为 `_upload_request_from_arguments(...)` → `self.runtime.prepare_observed_upload(request, ...)`。admission 产出的 `ValidatedFinsUploadMaterialRequest` 要"原样传同一 handoff"，必须进入 `prepare_observed_upload`——但协议签名 `observation_handle.py:240/:254` 为 `request: FinsUploadRequest`（= `FinsUploadFilingRequest | FinsUploadMaterialRequest`，`ingestion_runtime.py:1581`），不含 validated material，pyright 直接不过。合法出路只有加宽协议类型（真实触点 `dayu/fins/ingestion/observation_handle.py`，未列生产白名单）；错误绕行（在协议边界丢 handoff、重建 request 或二次 admission）恰好撞上 plan 明令禁止的"不展开……后丢 plan""每条调用链只 admission 一次"。协议 fake `tests/service/test_fins_wait_adapter.py:916/:932` 同签名（`:81/:918/:934` 用 `FinsUploadRequest` 标注），须同步，未列测试白名单。且 rg 对账模式不含 `FinsUploadRequest|FinsRuntimeUploadRequest` 裸别名，`observation_handle.py:29/242/256`、`test_fins_wait_adapter.py`、`service_runtime.py:21/294`、`fins_direct.py:35`、`upload_tools.py:31`、`test_fins_ingestion_tools.py:39` 等别名消费点不会被"逐条对账全部旧 scalar/request/usage 导入调用（包含 fake、monkeypatch、类型标注）"捞出。
- **为什么有问题**: plan 的对账完备性声称以该模式为凭；模式漏掉 handoff 必经的协议层与 fake，白名单自纠条款（"实际必要测试触点若超出此清单……"）因 rg 不命中而不会被触发，实施者只能靠 pyright 事后发现。
- **直接证据**: A14 全部行号；`rg 'FinsUploadRequest\b|FinsRuntimeUploadRequest' dayu/ tests/` 命中清单；rg 对账模式原文（plan 行 64）。
- **影响**: 白名单/命令清单缺文件（coverage 循环 18 文件与 pytest 16 文件均不含上述）；错误绕行会破坏"一次 admission、同一 handoff"合同。
- **建议改法和验证点**: 生产白名单加 `dayu/fins/ingestion/observation_handle.py`（`start_observed_upload`/`prepare_observed_upload` 的 request 类型改为含 `ValidatedFinsUploadMaterialRequest` 的显式 union 或复用改后的 `FinsRuntimeUploadRequest`）；测试白名单加 `tests/service/test_fins_wait_adapter.py`；rg 对账模式追加 `FinsUploadRequest|FinsRuntimeUploadRequest`；pytest/coverage 命令同步。验证点：对账输出中 `observation_handle.py` 与 `test_fins_wait_adapter.py` 可见，pyright 无协议不匹配。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 03-未修复-低-F5 落地句"两模块原有直接 import 底层常量仍供其它规则使用"对 `_IDENTITY_DESCRIPTOR_FILENAME` 不成立
- **位置**: §唯一 owner 与纯规划契约（import 图句括号"（两模块原有直接 import 底层常量仍供其它规则使用）"）
- **问题类型**: 文本失实 / 死代码风险
- **当前写法**: `_fs_source_integrity.py`、`_fs_maintenance_core.py` 改为消费 `DOCUMENT_SOURCE_CONTROL_FILENAMES` 后"原有直接 import 底层常量仍供其它规则使用"。
- **反例/失败场景**: `_IDENTITY_DESCRIPTOR_FILENAME` 在两模块的全部用途就是待迁移的集合字面（`_fs_source_integrity.py:31/:669/:856`、`_fs_maintenance_core.py:23/:581-582`）；迁移后这两个 import 成为 dead。plan 按字面执行会保留死 import（pyright 默认不报 unused import，`pyrightconfig.json` 无 `reportUnusedImport`），或让实施者误以为还有隐含消费点而迟疑。真正保留的只有 `_SOURCE_META_FILENAME`（`_fs_source_integrity.py:479`、`_fs_maintenance_core.py:554` 的 meta_path）。
- **为什么有问题**: 与 plan 自身"最小 import/不留无用件"标准冲突；语义所有权上"document 控制名成员"迁走后，底层常量的直接引用只剩 meta_path 一项，断言应精确到常量级。
- **直接证据**: A7 行号；`rg '_SOURCE_META_FILENAME|_IDENTITY_DESCRIPTOR_FILENAME' dayu/fins/storage/_fs_source_integrity.py dayu/fins/storage/_fs_maintenance_core.py` 全量命中如上，无第 4 处用途。
- **影响**: 死 import 残留或实施迟疑；不影响行为正确性。
- **建议改法和验证点**: 括号断言改为点名——`_SOURCE_META_FILENAME` import 保留（meta_path 用途），`_IDENTITY_DESCRIPTOR_FILENAME` import 同片删除；或删去该断言只保留"exact 行为不变"。验证点：迁移后 `rg '_IDENTITY_DESCRIPTOR_FILENAME' dayu/fins/storage/_fs_source_integrity.py dayu/fins/storage/_fs_maintenance_core.py` 零命中，`_SOURCE_META_FILENAME` 仍有 meta_path 命中。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 04-未修复-低-usage 迁移描述三处与源码事实偏差（retry hint 非迁来物、filing 上限参数未点名、`test_filing_upload_publication.py` 纳入理由失实）
- **位置**: §唯一 owner 与纯规划契约 / §typed 失败（"持有迁来的唯一 message/retry hint 模板……filing 传其现有 100 上限"）；§一个端到端可验收切片及文件范围（"`tests/fins/test_filing_upload_publication.py` 因 usage import 迁移纳入同切片"）
- **问题类型**: 文本精度 / 契约归属含糊
- **当前写法与反例**:
  - (a) "持有迁来的唯一 message/retry hint 模板"：可"迁来"的只有 `_USAGE_MESSAGES`（message-only）。`FinsUploadUsageFailure` 无 retry_hint 字段（`:708-741`）；现有 retry hint 全部内联于 `upload_failure.py:237-416`（按 code 各一条）。新 reason 的 retry hint 模板是**新增**内容，plan 未明说归属：若归 usage owner，则 retry hint 文案按 code 类别分居两模块（usage 类在 usage owner、其余在 `upload_failure`）；若归 `upload_failure`，则"取同一 usage message/retry hint"中 retry hint 不应由 usage owner 提供、测试"同源 retry hint"需收窄为 message 同源。二选一必须钉死。
  - (b) "filing 传其现有 100 上限"未点名常量：filing 限额判定真源是 `_MAX_TUPLE_ITEMS`（`:1266`）。实现若传字面 `100`，限额演进时 message 与真源漂移（F-R5 类绑定的具体化反向）。
  - (c) "`tests/fins/test_filing_upload_publication.py` 因 usage import 迁移纳入同切片"失实：全文件无 usage 符号 import（仅 `:107` docstring 提及 `FinsUploadUsageError`；`:34-38` import 的 `FinsUploadFilingRequest/ValidatedFinsUploadFilingRequest/validate_fins_upload_filing_request` 不迁移）。该文件的纳入实际依据是 plan 自己的条件性条款（`_PendingFileAsset`/`_PreparedFilingAssetMutation` 结构变化才改，且"即使不修改也执行"）。
- **为什么有问题**: 三处都会误导实施者对"迁移物/真源/触点"的判断；(a) 若二选一不钉，实施者可能在 `upload_failure` 复制 usage 文案模板（违反"不复制模板"）。
- **直接证据**: A2/A15；`rg 'retry_hint' dayu/fins/upload_failure.py`（`:87/:94/:119-120/:237-:416` 等）与 `rg 'FinsUploadUsage' tests/fins/test_filing_upload_publication.py`（仅 `:107`）。
- **影响**: 实施精度；三处均为一句话可收敛，不改变已定 owner 结构。
- **建议改法和验证点**: (a) 明写"message 模板自 `_USAGE_MESSAGES` 迁移；planner 新 reason 的 retry hint 模板为新增并在 `upload_usage_contract` 定义（或明写归 `upload_failure` 并把测试收窄为 message 同源）"；(b) 改为"filing 传 `_MAX_TUPLE_ITEMS`"；(c) 改为"`test_filing_upload_publication.py` 因 `_PendingFileAsset`/`_PreparedFilingAssetMutation` 条件性纳入，即使不修改也执行"，删去 usage import 理由。验证点：plan 文本与 `rg` 事实一致；实施后 retry hint 单源可由 owner 测试断言。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Open questions

无新增 open question。第三轮 OQ1–3 均已按裁决收敛（见逐项核对表）；本轮 Finding 01/04 是 OQ1 收尾文本的精度残片，属一句话可钉死项，不构成"owner/时序留给实施者发明"级缺口。

## Residual risks 与建议追踪去向

| 风险 | Plan 既有处置 | 本复审意见与追踪去向 |
| --- | --- | --- |
| F-R1 `NFC+casefold+NFC` 保守键多拒；不证明全部平台 alias | 已披露；storage 最终完整性兜底；文件系统反例触发硬停止 | 维持；closeout residual |
| F-R5 `TOO_MANY_FILES` 文案/schema 双绑定（material 常量 vs filing `_MAX_TUPLE_ITEMS`） | plan 行 28/88 登记"上限分离时须同源重审 schema/message 绑定" | 本轮参数化使其具体化（Finding 04b）；closeout residual |
| usage 迁移伴随件（Finding 01） | 未处置 | plan 一句钉死归属；或 closeout 前确认 `rg '_MAX_TEXT_CHARS' dayu/fins/upload_usage_contract.py` 零命中 |
| observation 协议触点（Finding 02） | 白名单扩展条款兜底，但 rg 模式捞不出 | plan 补白名单+模式；或实施 evidence 中列直接调用证据 |
| `_IDENTITY_DESCRIPTOR_FILENAME` dead import（Finding 03） | 未处置 | plan 括号句改精确；代码健康项 |
| retry hint 归属与 test_filing_upload_publication 理由（Finding 04） | 未处置 | plan 一句话收敛 |
| material 指纹因派生名修正发生一次性变化 | 已披露，实施 evidence 如实记录 | 维持 |
| F-R6 O25：首转换 primary、指纹不含 primary、逆序同指纹 | 明确留 O25 | 维持；追踪于 O25 work unit |
| F-R7 公司 meta 提前副作用（O34） | 非目标，plan 行 10 声明 | UM-O34 work unit |
| F-R8 facade 直调 symlink 末组件 basename 变为目标名 | 已披露（plan 行 56），按新规范路径契约更新断言 | 维持 |
| F-R9 目标卷 `NAME_MAX<255` 退化为迟 `OSError` | 已披露；actual limit 归 storage filename owner | 维持 |
| F-R10 TOCTOU（admission 与读取间路径变化） | 已披露，完整性防线兜底 | 维持 |
| F-R11 冻结 F20/F21/F22/S19/S20 不作修复后测试 | 已声明 | 维持 |
| plan 行 52 类名笔误 `FinsProductionUploadRunner`（实际 `ProductionFinsUploadRunner`，`service_runtime.py:99`；行 64 已用真名） | 前轮已记 | 仍维持"实施按真名即可"，不阻塞 |
| `MISSING_FILES` 复用文案 "create/update 上传必须提供 --files" 对 material 上下文沿用旧 CLI 措辞 | plan 行 47 钉"必须复用原有 usage 文案" | 可见结果与 filing 一致，非本片范围；若后续觉得对 LLM 不友好，随 `fins-material-file-existence-admission` WU 一并裁决文案 |

## 结论

**pass-with-risks**。

第三轮 F5/F6/OQ1–3 已按裁决落实：F5 第三消费点 `_fs_maintenance_core.py` 同切片消费唯一控制名集合、exact 行为不变且实测无环；F6 CLI 预检落点钉死在 raw request 构造前并补两例 exit 2 逐字回归；OQ1 的 `upload_usage_contract.py` 迁移经源码枚举反证——动机真实（`ingestion_runtime.py:133` → `upload_failure` 现边使不迁移必成环）、迁移单元内聚不过度、提议图无环、全体生产/测试消费方均在白名单；OQ2 显式 upsert/delete 模式与 OQ3 `META.JSON` reserved 归属均已钉死。旧高/中项（100/101、唯一 Docling 命名函数、filing identity 字节、raw/validated handoff、O25 边界）逐项以 HEAD 证据复证无回退；plan/goal/HEAD 三者一致，无 goal drift。

本轮新增 4 项低严重度 finding，全部为 plan 文本级精度/触点清单缺口，各一句话可收敛：迁移伴随常量 `_MAX_TEXT_CHARS`（及 `_FILE_USAGE_CODES`）归属未钉（唯一实测最小成环反例）；observation 协议类型触点与 `FinsUploadRequest`/`FinsRuntimeUploadRequest` 裸别名不在白名单与 rg 对账模式内；F5 括号断言对 `_IDENTITY_DESCRIPTOR_FILENAME` 失实；usage 迁移描述三处偏差（retry hint 非迁来物、filing 上限常量未点名、`test_filing_upload_publication.py` 理由失实）。接口设计、owner 归属与 admission 时序未留给实施者发明。按 Gateflow 约束，Kimi/MiMo 有效双路 re-review 通过前不实施、不提交；候选 plan 不得冒充已实施代码。

CANARY=mimo-96bbb6d7
