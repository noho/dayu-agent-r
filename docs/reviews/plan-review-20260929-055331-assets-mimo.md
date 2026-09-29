# Plan Review（独立复审）：UM-O04-F01 + UM-O23-F01 material 资产数量与身份规划（第三次修订）

RUNTIME/PROVIDER/MODEL: claude/mimo/mimo-v2.6-pro[1m]

- Review label：`assets-plan-re-review-mimo-20260929-03`；gate：plan review -> fix（独立复审，核对总控对第二轮 MiMo F1-F4 的裁决落实与第三次 Sol 修订）。
- 审查对象：`docs/gateflow/upload-material-assets-plan-20260929.md`（SHA-256 实测 `e7034db68ca4f4b2b2e901a898861f6c27d6f170562c4f9d6b1e7fdac856cfe0`，与任务预期及 `docs/gateflow/upload-material-assets-plan-review-adjudication-20260929.md` 末行记录一致，无版本冲突）。
- Binding goal：`docs/gateflow/upload-material-assets-goal-20260929.md`（SHA-256 实测 `208d4008caa8e6a0c870a1e1f929e3c706e0bbbdb97ef89f3c6d6c1888f86e36`，与前轮 review 记录一致，goal 未变）。
- 核对依据：总控裁决 `docs/gateflow/upload-material-assets-plan-review-adjudication-20260929.md`（MiMo 首轮 F1-F7、Kimi 首轮 F1/F2/F4、第二轮 MiMo F1-F4 与两次/三次 Sol fix 记录），前轮 `docs/reviews/plan-review-20260929-051109.md`（MiMo 第二轮）与 `docs/reviews/plan-review-20260929-033914.md`、`docs/reviews/plan-review-20260929-023619.md` 作为待复证 finding 清单。
- 依据 HEAD：`8d8d494fbbce0052372fb1b42097c9f7222cfa28`（审查开始时 `git rev-parse` 实测一致；工作区仅 6 个未跟踪 gateflow/review 文档，无产品改动）。
- 全部断言直接读取本 HEAD 源码/测试与实测得出，不采信候选 plan 或 Sol 自述；未实施任何 fix、未改 plan/goal/adjudication/产品/测试/README/既有 review、未 commit/push/PR、未派发子 Agent。

## 审查范围

按任务焦点：(1) 逐项核对总控 F1-F4（必改测试触点完整性、storage 控制名唯一集合与两 walker 共用的无环性与行为不变、`MISSING_FILES` 空列表与文件不存在独立 WU 的 scope 边界、filing/material path normalize/duplicate helper 同源且 filing 合法行为/错误不漂）；(2) adversarial 复证前轮高/中项未回退：100/101、全局碰撞、NFC/casefold、原件→Docling 名唯一函数、filing 原 identity 字节、raw/validated handoff、public typed reason、真实 CLI 分级、O25 依赖；(3) goal drift、架构边界、过度耦合、执行时序与测试缺口检查。

## Assumptions tested（HEAD 直接证据重证）

| # | Plan / 裁决断言 | 重证结果 | 直接证据 |
| --- | --- | --- | --- |
| A1 | material 派生名 stem 拼接、original 名 `file_path.name`，`deck.txt`/`deck.md` 同名冲突动机成立 | 成立 | `dayu/fins/pipelines/docling_upload_service.py:928`（`file_path.name`）、`:1029`（`f"{file_path.stem}{DOCLING_FILE_SUFFIX}"`）、`:78` `DOCLING_FILE_SUFFIX = "_docling.json"` |
| A2 | filing original/derived identity 算法与 plan 迁移描述字节一致 | 成立 | `docling_upload_service.py:1511-1535`：namespace `fins-upload-asset-v1`、separator `b"\0"`、digest 输入 `normalized_path.as_posix().encode("utf-8")`、输出 `original-<完整 hexdigest><suffix.lower()>`，且要求 `is_absolute` 且 `resolve(strict=False)==normalized_path`；`:1538-1553` derived 校验 `original-` 前缀后追加 `_docling.json` |
| A3 | identity helper 生产/测试消费面 = 计划白名单 | 成立 | 生产仅 `docling_upload_service.py`；测试恰 4 文件：`test_docling_upload_service.py`（含 `:1866` monkeypatch 目标字符串）、`test_fins_ingestion_runtime.py:131`、`test_cn_pipeline.py:46`、`test_sec_pipeline_upload_filing_stream.py:50`；`rg` 全库无第 5 处，plan 的 rg 对账模式可覆盖 monkeypatch 字符串 |
| A4 | `_validate_source_files` 只查 exists/is_file，`FileNotFoundError` 消息带全路径 | 成立 | `docling_upload_service.py:1592-1613`（`f"上传文件不存在: {file_path}"`） |
| A5 | `_normalize_filename` 会 `strip()`、无保留名/长度校验 | 成立 | `dayu/fins/storage/_fs_storage_utils.py:29-52,71-84`（`_normalize_path_component` strip 后校验分隔符/绝对路径）；全文件无保留名/`NAME_MAX` 规则 |
| A6 | document 目录控制名成员判定的真实表达点 | 成立（**新增发现第三处**） | `_fs_storage_utils.py:20` `_SOURCE_META_FILENAME="meta.json"`；`_fs_identity.py:40` `_IDENTITY_DESCRIPTOR_FILENAME=".identity.json"`；成员判定内联集合恰三处：`_fs_source_integrity.py:669`（declared 名 exact 拒绝）、`:856`（物理 walker exact 跳过）、**`_fs_maintenance_core.py:579-583`（rejected filing artifact 物理/声明比对时跳过同两名）**；`material_manifest.json` 在 source root（`_fs_storage_infra.py:3137/:3168` 一带），不与 original 同层 |
| A7 | `NAME_MAX=255`、新模块名空缺、13 字节后缀蕴含关系 | 成立 | `getconf NAME_MAX .` = 255（实测）；`dayu/fins/upload_asset_plan.py`、`dayu/fins/storage/asset_filename_contract.py` 均不存在；`len("_docling.json")==13`，254+13=267 反例成立 |
| A8 | material 数量迟至摘要裸 `ValueError`；`_MAX_TUPLE_ITEMS=100` 通用；tool schema `maxItems:100` 共用 | 成立 | `ingestion_runtime.py:7861-7875` `_validate_upload_file_count` 抛 `ValueError`，由 `_upload_request_summary`（`:7797`）与 `_upload_started_progress_payload`（`:8186`）调用；`:167` `_MAX_TUPLE_ITEMS=100`；filing 静态限额 `len(request.files) > _MAX_TUPLE_ITEMS`（`:1266`）；`upload_tools.py:243` `maxItems: 100`（filing/material 共用 schema）；`:1033` TOO_MANY_FILES 文案 "…不能超过 100 个" |
| A9 | 两套 closed code 现状与 plan 表一致；classifier 对 planner typed error 无分支；分组互斥/完备断言存在 | 成立 | `ingestion_runtime.py:673-706`（含 `TOO_MANY_FILES/MISSING_FILES/DUPLICATE_FILE_PATH` 及 `INVALID_FILE_BASENAME/FILE_NOT_FOUND/FILE_NOT_REGULAR`）；`upload_failure.py:179-181` `_USAGE_FAILURE_CODES` 仅 `UNSUPPORTED_UPLOAD_FORMAT`，`:196-210` 互斥/完备断言，`:214-286` 分类器末行 `UNEXPECTED_RUNTIME` |
| A10 | CLI 丢 selection、exit 2 handler、filing validated handoff 先例 | 成立 | `fins.py:728` `files=_validated_upload_files(args.files).files`；`:1128-1147` `_validated_upload_files`（expanduser().resolve + exists/is_file + `CliFinsUsageError(_MISSING_UPLOAD_FILE_TEMPLATE)` 全路径英文文案）；`:198-200` `FinsUploadUsageError` → `EXIT_USAGE_ERROR`；`ingestion_runtime.py:755-766` `ValidatedFinsUploadFilingRequest` 先例 |
| A11 | 入口现状（scalar/可空 files/流内 selection/runner 展开/company_id 兼容字段）与 plan 迁移点一一对应 | 成立 | `sec_upload_workflow.py:419-433` `files: list[Path] \| None`、`:433/:454` `company_id` 自述"可选兼容字段…不作为身份真源"、`:493` 流内 `FinsUploadMaterialFiles.from_upsert_paths(tuple(file_list))`；`cn_pipeline.py:1109` 同构；`service_runtime.py:201-265` `_run_material_upload` 以 `files=list(request.files)` 展开调用 SEC/CN scalar；`fins_direct.py:299-362` scalar `upload_material` 直构 raw request；`sec_pipeline.py:799/:870` scalar+`company_id: Optional[str]`；`upload_tools.py:103-105` observation 前无 admission；`.upload_material(` 全库调用点恰为 `service_runtime.py:230/251`、`fins.py:725` 及测试，无隐藏 UI 调用方 |
| A12 | validated handoff 可全程内存原样传递；`_validate_runtime_upload_request` 有 isinstance 透传先例 | 成立 | `ingestion_runtime.py:4714-4748`（`isinstance(request, ValidatedFinsUploadFilingRequest): return request`），返回类型 `ValidatedFinsUploadFilingRequest \| FinsUploadMaterialRequest`；`start_upload` 把对象闭包进 `executor.submit`（`:4705-4710`），record 仅 `request_summary` |
| A13 | material 指纹不含 primary、首转换文件 primary、`ordered_files.index()` 待删 | 成立 | `docling_upload_service.py:1719-1735`（material payload=name+sha256+size+source 按 name 排序）、`:1032-1033`（`primary_document` 取首个转换产物）、`:983-988`（filing `ordered_files.index()`） |
| A14 | 100/101 分级真实 CLI 口径与裁决一致，未回退 | 成立 | plan §验证矩阵与 §硬停止文本：101 侧 exit 2/typed/converter 0/零发布；100 侧 admission 全接受 + 至少首个真实 converter 启动、不冒充成功发布；受控 converter 承担 100 次调度；小 N 同 stem 真实完整发布；与裁决「Sol 第二次 plan fix 候选」句逐项吻合；goal "100 个以内允许，101 个前置拒绝"用语未被拔高 |
| A15 | `canonicalize_fins_public_file_label` 为唯一 label 真源 | 成立 | `dayu/fins/direct_events.py:1080` |
| A16 | filing 路径规范化/重复判定/helper 消费面与 plan 的 F4 同源方案兼容 | 成立 | `ingestion_runtime.py:1215-1221` `_normalize_fins_upload_path`（`expanduser().resolve(strict=False)`，`OSError/RuntimeError` → `FILE_NOT_FOUND`）、`:1224-1239` `_fins_upload_path_identity`（`str(path)` exact）、`:923-952` `_project_fins_upload_filing_selection`（set 长度判重 → `DUPLICATE_FILE_PATH`，identity 兼作 primary 匹配）、`:1035/:1049` 文案（重复无文件标签、MISSING_FILES="create/update 上传必须提供 --files" 空列表语义）；`FinsUploadMaterialFiles`/`FinsUploadFilingFiles` 在 `upload_format_contract.py:314/:455`（低于 ingestion_runtime，planner 可引用不成环） |
| A17 | 声明 import 图无环 | 成立 | `_fs_identity.py` 只依赖 `_fs_storage_utils.py`/ticker_normalization；`_fs_storage_utils.py` 只依赖 domain；`_fs_source_integrity.py` 依赖 `_fs_identity`/`_fs_storage_utils`/公共 `source_integrity`；`_fs_maintenance_core.py` 同底层；`upload_format_contract.py` 依赖 `dayu.documents.docling_runtime`/`dayu.fins.direct_events`（二者均不 import `ingestion_runtime`，`rg` 全库 `ingestion_runtime` 导入方清单不含 planner 依赖链任何模块）；`SourceKind` 在 `dayu.fins.domain.enums`。`upload_asset_plan.py -> {storage.asset_filename_contract, upload_format_contract, domain}` 与 `ingestion_runtime/upload_failure/docling_upload_service -> upload_asset_plan` 单向，图无环 |
| A18 | 测试触点 rg 对账完备 | 成立 | 按 plan 模式 `upload_material\(|upload_material_stream\(|FinsUploadMaterialRequest|_normalize_fins_upload_path|_fins_upload_path_identity|_build_filing_original_asset_identity|_build_filing_derived_asset_identity` 扫 `tests/` 恰 9 文件，全部已列入 plan 测试白名单；`test_upload_failure.py`、`test_docling_upload_service_integration.py`、`test_fins_storage_atomicity.py` 亦列入；pytest 命令 15 个文件与触点清单一致；coverage 逐文件循环 14 个生产文件与生产触点清单逐一对应 |

## 逐项核对：总控第二轮 F1-F4

| 项 | 裁决要求 | 本复审核实 | 结论 |
| --- | --- | --- | --- |
| F1 必改测试触点完整 | 显列 `tests/service/test_fins_direct.py`、`tests/fins/test_fins_service_runtime.py`、`tests/fins/test_fins_ingestion_tools.py`，条件性 `test_filing_upload_publication.py`，全仓对账旧 scalar/request/导入，命令同步 | plan §测试触点已显列三必改 + 条件性第四文件 + 11 个更新文件 + 2 新文件；A18 实测 rg 模式结果恰被清单覆盖（含 monkeypatch 字符串）；pytest/逐文件 coverage 命令与清单同步；`_PendingFileAsset` 条件性判据（pair 结构/构造签名改变）明确 | **已落实** |
| F2 控制名唯一集合与两 walker 共用、无环、行为不变 | storage 契约导出唯一集合，`_fs_source_integrity.py` 两处 walker 同片消费、行为不变；循环则重排底层常量 | 集合由 `_SOURCE_META_FILENAME`/`_IDENTITY_DESCRIPTOR_FILENAME` 构造（A6 常量同源）；两 walker 现语义为 exact `name in set` / `child.name in set`（`:669`/`:856`），frozenset 替换字面集合语义不变；A17 实测 import 图无环（含 `_fs_identity`→`_fs_storage_utils` 真实方向、`ingestion_runtime` 导入方清单） | **已落实**，但"唯一"成员事实仍有第三处字面表达，见 Finding 01 |
| F3 `MISSING_FILES` 空列表与文件不存在独立 WU 的 scope 边界 | 只校验数量/身份；`MISSING_FILES`=upsert 空列表；不存在/非普通文件不映 `MISSING_FILES`，登记 `fins-material-file-existence-admission`；不把不存在映成 `MISSING_FILES` | plan §typed 失败："`MISSING_FILES` 严格只指 material upsert 的空 `files`，绝不指某个已列文件不存在或不是普通文件"；"当前切片不得借 `MISSING_FILES` 或新增 fallback 处理它"；独立 WU 已登记并声明真源（`FILE_NOT_FOUND`/`FILE_NOT_REGULAR` + Fins 公共文件标签）；"不含绝对路径"只承诺新 planner reason 投影，CLI 旧文案不修复；filing 空列表语义与 `:1049` 现文案一致 | **已落实**；CLI 侧预检落点残留精度缺口，见 Finding 02 |
| F4 filing/material path helper 同源、filing 行为/错误不漂 | 规范化/重复身份 helper 归资产规划 owner，filing 静态 admission 共用；迁移 filing 测试；无兼容 re-export | plan 给出具体签名 `normalize_upload_asset_path`（`expanduser().resolve(strict=False)`，与 `:1215-1221` 逐字同语义）、`upload_asset_path_identity`（exact 字符串，与 `:1224-1239` 同）、`has_duplicate_upload_asset_paths`（与 `:952` set 长度判重同真值语义，重复错误文案无文件标签故无标签漂移）；filing runtime 保留异常→`FILE_NOT_FOUND`、重复→`DUPLICATE_FILE_PATH` 投影与自身文件数/selector/角色/存在/格式规则；"不保留旧 `_normalize_fins_upload_path`/`_fins_upload_path_identity` 的兼容转发或第二份 set 判定"；filing 测试回归随 helper 迁移；A16/A17 证实语义与 import 方向可行 | **已落实** |

## 前轮高/中项 adversarial 复证（是否回退）

| 项 | 复证 | 结论 |
| --- | --- | --- |
| 100/101 边界 | `MAX_MATERIAL_UPLOAD_FILES = 100` 归 `upload_asset_plan.py`（plan 行 16/22/26）；1..100 放行、101 前置 typed 拒绝；owner 级 100/101 两侧必过；真实 CLI 分级与裁决口径一致（A14）；`_MAX_TUPLE_ITEMS` 明确不得成为 material 真源，摘要不再以裸 `ValueError` 先失败（"摘要只消费 validated handoff 的数量事实"） | 未回退 |
| 全局碰撞 | 对**所有 original 与所有 derived** 检查 original-original、derived-derived、original-derived 及对控制名碰撞（`a.txt`/`a.txt_docling.json` 交叉反例进矩阵）；`material_manifest.json` 明确排除出 document 控制名集合；保序 `ordered_pairs`/`converter_pairs` | 未回退 |
| NFC/casefold | `NFC(casefold(NFC(name)))` 保守键统一作用，保存/显示/持久化名逐字不变；`Deck.txt`/`deck.txt`、NFC/NFD 在 converter 前拒绝；保守多拒与平台 alias 列残余；文件系统反例触发硬停止再裁决 | 未回退 |
| 原件→Docling 名唯一函数 | `docling_storage_name(source_kind, original_storage_name)` 单一 owner；material 完整名加后缀不 stem/不序号/不 hash 截断；filing 保留 `original-` 前缀校验并逐字保留身份算法；filing 路径 namespace/`b"\0"`/digest/suffix 规则迁入并删除旧函数，四处测试导入同切片改向，不留 re-export/双实现窗口 | 未回退 |
| filing 原 identity 字节 | A2 逐字核对：`original-<sha256(fins-upload-asset-v1 + b"\0" + as_posix())><suffix.lower()>` + `_docling.json`；输入守卫（absolute、`resolve(strict=False)==self`）随规则迁移；"旧 original/derived identity 逐字一致"测试进验证矩阵 | 未回退 |
| raw/validated handoff | raw façade `upload_material(request)`/`upload_material_stream(request)` 与必填 validated 方法分名（`upload_material_validated`）；每链 admission 恰好一次；runner 传原 handoff 不展开 `files=list(...)`；无 `raw\|validated` 联合、无可空 plan、无 isinstance 双路补救；旧 scalar 同切片迁移；A11/A12 证实触点与内存传递可行 | 未回退 |
| public typed reason | 封闭 `FinsUploadAssetPlanReason`→双 closed code 映射表逐项落地（复用/新增同名）；`_USAGE_FAILURE_CODES` 登记 + 互斥/完备断言保持；`fins_upload_failure_from_exception` 显式分类 planner typed error，独立 pipeline catch-all 不再落 `UNEXPECTED_RUNTIME`；单一文案投影双消费、不新增第三套字符串分支；label 走 `canonicalize_fins_public_file_label(Path.name)`、数量不附标签、不含绝对路径/派生内部名/原始异常文本 | 未回退 |
| 真实 CLI 分级 | 101：exit 2/typed/converter 0/零 source 发布；100：admission 全接受 + 至少首个真实 converter 启动、记录实际启动数、不冒充 100 成功发布；受控 converter 100 次调度兜底；小 N 同 stem 真实转换/双流 exit 0/完整发布；硬停止条款排除 100 次启动补跑；100 侧内容/资源失败如实分类不构成停止 | 未回退 |
| O25 依赖 | 只稳定 original→derived 映射与 pair 身份；O25 后续只改 primary **选择规则**与同源指纹/skip；首转换 primary 与逆序同指纹风险明确记为 O25 依赖、不宣称本单解决；不升格为公开业务契约 | 未回退 |

## Findings

### 01-未修复-低-document 控制名成员判定在 `_fs_maintenance_core.py` 仍有第三份字面集合，"唯一集合"未覆盖同义成员事实
- **位置**: §唯一 owner 与纯规划契约（storage 纯判定入口句、import 图句）；§一个端到端可验收切片及文件范围（生产触点白名单）
- **问题类型**: 语义所有权 / 重复逻辑
- **当前写法**: 新 `asset_filename_contract.py` 从 `_SOURCE_META_FILENAME`/`_IDENTITY_DESCRIPTOR_FILENAME` 构造并导出**唯一** `DOCUMENT_SOURCE_CONTROL_FILENAMES`；`_fs_source_integrity.py` 两 walker 同切片消费；import 图与生产白名单只含 `_fs_source_integrity.py`，不含 `_fs_maintenance_core.py`。
- **反例/失败场景**: storage 布局将来新增/移除 document 目录控制名（历史上已有 `_PROCESSED_META_FILENAME`、`_download_rejections.json` 类扩展）时，只改契约+walker 不改 `_fs_maintenance_core.py:579-583` 的内联集合：rejected filing artifact 校验会把新控制名当业务文件比对 → "rejected filing meta.files 与物理文件不双向一致"误拒；或反向误跳。正是 MiMo 第二轮 F2 的漂移类，只是 blast radius 从 planner 收窄到 maintenance 校验。
- **为什么有问题**: CLAUDE.md 语义所有权要求同一业务事实（"哪些名字是 document 目录控制名、不属业务文件"）只有一个 source of truth；plan 钉了集合成员单源与两 walker 消费，却留下第三处同义成员表达。总控 F2 完成信号虽只要求两 walker，但 plan 自称"唯一集合"，当前写法下该声称不完全成立。
- **直接证据**: `_fs_maintenance_core.py:575-586`（`child.name in {_IDENTITY_DESCRIPTOR_FILENAME, _SOURCE_META_FILENAME}` 跳过后比对 `physical_files != expected_files`）；全库成员判定内联集合恰三处（`_fs_source_integrity.py:669/:856` + 该处）；plan import 图/白名单无 `_fs_maintenance_core.py`；A17 证实该模块改为消费契约集合同样无环（它已 import 同层 `_fs_identity`/`_fs_storage_utils`，契约只依赖这两个底层）。
- **影响**: 控制名集合演进失同步（F2 类残余）；契约/walker 的 owner 测试发现不了该处漂移。
- **建议改法和验证点**: 同切片让 `_fs_maintenance_core.py:581` 改为消费 `DOCUMENT_SOURCE_CONTROL_FILENAMES`（扩一行生产白名单，行为不变），或 plan 明示该处语义不在集合范围内并登记 residual。验证点：新增一个控制名常量做演练，三处消费点的测试应同红/同绿。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 02-未修复-低-CLI 逐文件存在/普通文件预检在 scalar→validated 迁移后的落点未钉死，验证矩阵无回归断言
- **位置**: §typed 失败和跨入口 handoff 第 1 条（CLI 迁移句）；§验证矩阵（"用真实存在的普通文件作为其它资产规划样本"）
- **问题类型**: 契约缺失 / 测试缺口
- **当前写法**: "`_validated_upload_files(...).files` 的丢 selection 路径删除"；同时承诺"逐文件存在性和普通文件错误**保留当前行为**""CLI 的既有缺失路径文案也不由本项修复"；但未写明该预检（含 `_MISSING_UPLOAD_FILE_TEMPLATE` 全路径文案）在新链路中由谁承担；验证矩阵的资产样本全部要求"真实存在的普通文件"。
- **反例/失败场景**: 实施 Agent 按"丢 selection 路径删除""旧 scalar 调用全部消失"把 `_validated_upload_files` 整体移除，raw request 直接由 `args.files` 构造进唯一 admission——admission 按 plan 不查逐文件存在性；缺失文件穿透 `_validate_source_files` 的 `FileNotFoundError`（`docling_upload_service.py:1610-1611`）落入 CLI 未知失败分支（`fins.py:211-218` 泛 `Exception` → `_FINS_DIRECT_UNKNOWN_FAILURE_MESSAGE`，exit 1），替代今天的 exit 2 + "upload file does not exist: {path}"。计划内测试（101 typed 早于 converter、旧 scalar 消失、小 N 发布、owner 级样本）全部照常通过，回归无感放行。
- **为什么有问题**: 与 plan 自设的"保留当前行为"承诺直接冲突；`tests/cli/test_fins_commands.py` 对 material 缺失文件消息零断言（实测 `rg "upload file does not exist|upload path is not a file" tests/` 无命中，`test_fins_commands.py:1654/:1670` 的中文缺失消息断言属 filing 路径），行为保持既无接线位置也无测试钉；且"当前切片不得借 `MISSING_FILES` 或新增 fallback 处理它"排除了把它顺手并入 planner 的替代路径。
- **直接证据**: `fins.py:1128-1147`（`_validated_upload_files` 的 exists/is_file + `CliFinsUsageError`）、`:98-99` 文案模板、`:211-218` 兜底 handler；plan 两处句子原文；A18/本项 rg 实测。
- **影响**: 用户可见 CLI 行为回归（exit 2 明确文案 → exit 1 未知失败）且验证矩阵放行；后续 `fins-material-file-existence-admission` WU 还要先补回被删行为。
- **建议改法和验证点**: plan 补一句钉死——CLI raw request 构造前保留现有逐文件存在/普通文件预检与文案（属直接上游输入校验，不进 planner、不映 `MISSING_FILES`），`_validated_upload_files` 只随 selection 投影删除、不随检查删除；并在 `tests/cli/test_fins_commands.py` 增补 material 缺失文件/目录路径的 exit 2 文案断言作回归钉。验证点：迁移后跑 CLI 缺失文件用例，exit 码与文案逐字不变。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Open questions

1. **OQ-1（三个复用 code 的 message 真源）**：`MISSING_FILES`/`TOO_MANY_FILES`/`DUPLICATE_FILE_PATH` 同时被 filing 既有 `_USAGE_MESSAGES`（`ingestion_runtime.py:1029-1052`，每 code 单条文案）与 planner 新投影消费。plan 要求"单一纯投影……不各存一套新模板"，但未写明这三条的 message 归属：planner 投影成为这些 code 的唯一文案（filing 消费同一文案），还是 filing 保留旧文案而 planner 另出一套（即"同 code 双文案"）。另 `TOO_MANY_FILES` 文案按 plan "从 `MAX_MATERIAL_UPLOAD_FILES` 派生"后，filing 侧展示将被绑到 material 常量而 filing 限额仍是 `_MAX_TUPLE_ITEMS`（F-R5 类绑定的具体化）。建议一行钉死归属并把绑定写进残余。
2. **OQ-2（planner 对 action 的输入形状）**：行为合同已钉（delete 空 selection/空 plan 免检、upsert 空 `files` → `MISSING_FILES`），但"planner 只接收路径/selection、source kind 等低层输入"未写明 upsert/delete 判定由 planner 的哪个输入（action 参数 vs admission 分支）承载，实施者二选一即可，建议一句收敛。
3. **OQ-3（控制名 case 变体的 reason 归属）**：`META.JSON` 等 case 变体经保守键命中控制名集合时归 `RESERVED_CONTROL_NAME` 还是 `ASSET_NAME_COLLISION` 未钉；两者都在 converter 前 typed 拒绝且双 code 投影完整，测试断言任选其一钉住即可。

以上均为一句文案可收敛的实现精度，不构成"owner/时序留给实施者发明"级缺口：规划 owner（`upload_asset_plan.py`）、storage 布局 owner（`asset_filename_contract.py`）、admission 时机（各入口首个生命周期事件前恰好一次）、执行内层（必填 validated handoff）、双 closed code 映射与 O25 边界均已被 plan 钉死。

## Residual risks 与建议追踪去向

| 风险 | Plan 既有处置 | 本复审意见与追踪去向 |
| --- | --- | --- |
| F-R1 `NFC+casefold+NFC` 保守键多拒；不证明全部平台 alias | 已披露；storage 最终完整性兜底；文件系统反例触发硬停止 | 维持；closeout residual |
| F-R5 `TOO_MANY_FILES` 文案/schema 同时绑 `_MAX_TUPLE_ITEMS` 与 `MAX_MATERIAL_UPLOAD_FILES` | plan 行 26 承诺派生 + "将来分离再处理共用 schema 表达" | 本轮 message 派生使绑定具体化（OQ-1）；上限分离时同改 message/schema；closeout residual |
| CLI 逐文件存在预检落点（Finding 02） | "保留当前行为"但未钉落点 | plan 一句 + 一条 CLI 回归断言；或登记 follow-up |
| 控制名集合第三处字面（Finding 01） | 未处置 | 同片扩白名单一行或登记 follow-up |
| material 指纹因派生名修正发生一次性变化，同内容旧 source 重传不命中 skip | 已披露（plan 残余节要求实施 evidence 如实记录） | 维持；第二轮 F-R4 已闭合 |
| F-R6 O25：首转换 primary、指纹不含 primary、逆序同指纹 | 明确留 O25 | 维持；追踪于 O25 work unit |
| F-R7 公司 meta 提前副作用（O34） | 非目标，plan 行 10 声明 | UM-O34 work unit |
| F-R8 facade 直调 symlink 末组件 basename 变为目标名 | 已披露（plan 行 52），按新规范路径契约更新断言 | 维持；实施时核对固定链接名的测试 |
| F-R9 目标卷 `NAME_MAX<255` 退化为迟 `OSError` | 已披露；actual limit 归 storage filename owner 裁决 | 维持；跨平台 closeout residual |
| F-R10 TOCTOU（admission 与读取间路径变化） | 已披露，完整性防线兜底 | 维持 |
| F-R11 冻结 F20/F21/F22/S19/S20 不作修复后测试 | 已声明 | 维持，lineage 保留 |
| plan 行 48 类名笔误：写 `FinsProductionUploadRunner`，实际类为 `ProductionFinsUploadRunner`（`dayu/fins/service_runtime.py:99`，`run_upload`/`_run_material_upload` 方法名正确） | — | rg 对账模式不受影响；实施时按真实类名即可，无需改 plan |

## 结论

**pass-with-risks**。

总控第二轮 F1-F4 已按裁决落实：测试触点显列+全仓 rg 对账+命令同步（A18）；storage 控制名集合单源供两 walker 共用且实测 import 图无环、exact 语义不变（A6/A17）；`MISSING_FILES` 收窄为空 upsert、逐文件存在性登记独立 `fins-material-file-existence-admission` WU；filing/material 路径规范化/重复判定 helper 同源签名与现有语义逐字一致、filing 错误投影与限额/selector/格式规则保持。前轮高/中项（100/101、全局碰撞、NFC/casefold、唯一 Docling 命名函数、filing identity 字节、raw/validated handoff、双 closed code/分类器、真实 CLI 分级、O25 边界）逐项以 HEAD 证据复证无回退；goal SHA/plan SHA 与记录一致，无 goal drift。

剩余 2 项低严重度 finding（控制名成员事实第三处字面表达；CLI 逐文件存在预检落点与回归断言缺失）与 3 项 open question 均为 plan 文本级精度问题，各一句话可收敛；接口设计、owner 归属与 admission 时序未留给实施者发明。按 Gateflow 约束，Kimi/MiMo 有效双路 re-review 通过前不实施、不提交。

CANARY=mimo-308aec55
