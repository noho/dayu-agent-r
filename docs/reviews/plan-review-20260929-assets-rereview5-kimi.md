# Plan Review（Kimi 独立复审，第五轮）：UM-O04-F01 + UM-O23-F01 material 资产数量与身份规划

RUNTIME/PROVIDER/MODEL: claude/kimi/kimi-k3[1m]
CANARY=kimi-00ae7455

- Review label：`assets-plan-rereview5-kimi-20260929-01`；gate：plan review -> fix（Kimi/MiMo 双路 re-review 的 Kimi 路，独立复审第五次修订候选）。
- 审查对象：`docs/gateflow/upload-material-assets-plan-20260929.md`，任务预期 SHA-256 `88b03cd247dc5d6d6c1fa9cb3dc113046a5c796ab40a61083d0c1cd00a049e13`，本地 `shasum -a 256` 实测一致，无版本漂移（若漂移本 review 按停止条件立即终止，未触发）。
- Binding goal：`docs/gateflow/upload-material-assets-goal-20260929.md`（SHA-256 实测 `208d4008caa8e6a0c870a1e1f929e3c706e0bbbdb97ef89f3c6d6c1888f86e36`，与 MiMo 第四轮记录一致，goal 未变）。
- 依据 HEAD：`8d8d494fbbce0052372fb1b42097c9f7222cfa28`（`git rev-parse HEAD` 实测一致；工作区仅未跟踪 gateflow/review 文档，无产品改动）。
- 裁决依据：`docs/gateflow/upload-material-assets-plan-review-adjudication-20260929.md`（重点：第四轮 MiMo F1–F4 裁决与 fix5 记录）；前轮 review：`plan-review-20260929-023619.md`（Kimi 首轮）、`plan-review-20260929-assets-rereview4-mimo.md`（MiMo 第四轮，即本轮待复证 finding 的来源）。
- 全部结论直接读取本 HEAD 源码/测试与实测得出，不采信候选 plan 或 Sol 自述。**未读 MiMo 同轮（第五轮）review（磁盘上不存在，仅有第三/四轮 MiMo artifact）；未派发子 Agent；未改 plan/goal/adjudication/产品/测试/README/既有 review；未 commit/push/PR/merge；未发外部消息。**
- 本 checkout 无 `.venv`、三个新模块（`upload_asset_plan.py`/`upload_usage_contract.py`/`asset_filename_contract.py`）尚未创建——plan 是未实施候选，符合预期；import 无环结论基于对现存模块 import 边的静态反证，不声称已运行 import smoke 证明。

## 审查范围与方法

按任务焦点逐项以源码反证第四轮裁决的 F1–F4 是否在第五修订中真实落地且未过度：

1. F1：新 usage owner 的 named 240 上界（`FINS_UPLOAD_USAGE_TEXT_LIMIT`）、`_FILE_USAGE_CODES` 随迁、工厂测试迁移与 import 无环。
2. F2：observation 协议两方法与 Service fake 的 validated handoff 触点。
3. F3：三处 storage 控制名消费共用唯一真源、`_IDENTITY_DESCRIPTOR_FILENAME` dead import 清理与 `_SOURCE_META_FILENAME` meta_path 保留的精度。
4. F4：retry hint 当前/新增归属、filing 上限点名 `_MAX_TUPLE_ITEMS`、`test_filing_upload_publication.py` 纳入缘由。
5. adversarial 复证不回退项：旧 100/101、CLI 缺文件 exit 2、单一 original→Docling 名函数、filing identity 字节、O25 依赖、同源 manifest/资产规划、切片/白名单/覆盖率/pyright/README。

## F1 反证：usage owner 的 named 240 上界、`_FILE_USAGE_CODES` 与工厂测试迁移/import 无环 —— 已修复

| 子项 | plan 文本（行号） | HEAD 源码证据 | 结论 |
| --- | --- | --- | --- |
| named 240 上界 | 行 30：新 owner 自持 `FINS_UPLOAD_USAGE_TEXT_LIMIT: Final[int] = 240`，供 `FinsUploadUsageFailure` 校验与工厂消息上界共用；`_MAX_TEXT_CHARS` 保留给非 usage 文本，不反向导入、不散写裸 `240` | `_MAX_TEXT_CHARS: Final[int] = 240`（`ingestion_runtime.py:166`）被 usage 两处（`:739` `FinsUploadUsageFailure.__post_init__`、`:1095` 工厂）与 7 处非 usage（`:1277` fiscal-period、`:1368` 文本、`:7106-7107` 事件截断、`:7403`、`:7478`、`:9000-9002`）共用——不能整体随迁；per-contract 独立上界先例存在：`download_contract.py:43` `FINS_DOWNLOAD_PUBLIC_MAX_TEXT_CHARS: Final[int] = 240`。plan 的拆解与源码依赖事实一致 | 反证成立 |
| `_FILE_USAGE_CODES` 随迁 | 行 30：六符号迁移清单显列 `_FILE_USAGE_CODES`，"保持工厂私有集合"；不留 `ingestion_runtime.py` 兼容 re-export | `_FILE_USAGE_CODES`（`:1021-1025`，成员 `FILE_NOT_FOUND`/`FILE_NOT_REGULAR`）全库唯一消费点是工厂 `:1081`（rg 实测）；`ingestion_runtime.py:9116-9144` `__all__` 不含任何 usage 符号，无 re-export 拆除义务 | 反证成立 |
| 工厂测试迁移 | 行 68："`test_fins_ingestion_runtime.py:1389` 起的工厂 closed/bounded/path-free owner 测试随定义迁至 `test_upload_usage_contract.py`，并断言新 planner reason 的 message/hint 同源、独立 usage 文本上界及路径安全" | `tests/fins/test_fins_ingestion_runtime.py:1389` 确为 `test_fins_upload_usage_failure_mapping_is_closed_bounded_and_path_free` 起始行，`:1462-1516` 覆盖 closed code 集合、bounded、path-free 与 `FinsUploadUsageFailure` 构造校验；usage 消费测试 5 文件（`:119-128`、`test_fins_ingestion_tools.py:40/43`、`test_fins_service_runtime.py:27-28`、`test_sec_pipeline_upload_filing_stream.py:41-42`、`test_cn_pipeline.py:30-31`）全部在 plan 测试白名单 | 反证成立 |
| 迁移动机真实（不修必成环） | 行 30：为避免 `upload_failure.py -> ingestion_runtime.py -> upload_failure.py` 环而下沉 | 现存边 `ingestion_runtime.py:133-138` `from dayu.fins.upload_failure import (... fins_upload_failure_from_exception ...)`；rg 全库确认 `upload_failure.py` 不 import `ingestion_runtime`——若 usage 文案留在 `ingestion_runtime` 而 `upload_failure` 消费同一文案，恰好成环。动机成立 | 反证成立 |
| 提议 import 图无环 | 行 30：`upload_usage_contract -> {upload_asset_plan, upload_format_contract}`；`upload_asset_plan -> {storage.asset_filename_contract, upload_format_contract/SourceKind}` 且"绝不 import `ingestion_runtime.py`、`upload_failure.py`、`pipelines` 或 Service"；`{ingestion_runtime, upload_failure} -> upload_usage_contract` | 底层链实测不反向引用：`upload_format_contract.py` 仅 import `dayu.documents.docling_runtime` + `dayu.fins.direct_events` + stdlib（rg 对三文件搜 `ingestion_runtime|upload_failure` 零命中）；`_fs_identity.py` 仅 import stdlib + `ticker_normalization` + `._fs_storage_utils`；`_fs_storage_utils.py` 仅 import stdlib + `dayu.contracts.json_value` + `dayu.fins.domain.*`（domain 不依赖 storage，实测空）；全库 import `ingestion_runtime` 的 14 个生产模块与 import `upload_failure` 的 8 个生产模块均不含上述底层链成员。隐含边 `upload_failure -> upload_asset_plan`（行 47 分类 `FinsUploadAssetPlanError` 的 isinstance 所必需）亦无环——plan 明文禁止 `upload_asset_plan` 反向 import `upload_failure` | 反证成立（静态）；运行时 import smoke 属实施 gate（行 76-77），本 checkout 无 venv/新模块，按停止条件不妄言已证 |

## F2 反证：observation 协议两方法与 Service fake 的 validated handoff —— 已修复

| 子项 | plan 文本 | HEAD 源码证据 | 结论 |
| --- | --- | --- | --- |
| 协议触点是真实缺口 | 行 52：`ingestion/observation_handle.py` 的 `start_observed_upload`、`prepare_observed_upload` 协议 request 类型同步改为覆盖 validated material 的 `FinsRuntimeUploadRequest` | 协议 `observation_handle.py:240/:254` 注解窄 `FinsUploadRequest`（`:25-30` TYPE_CHECKING 自 `ingestion_runtime` 导入）；而实现 `ingestion_runtime.py:3820/:3848` 已注解较宽的 `FinsRuntimeUploadRequest`（`:1582` = `FinsUploadRequest \| ValidatedFinsUploadFilingRequest`）。协议窄于实现，validated material handoff 不经协议加宽则 pyright 不过——缺口与触点均真实 | 反证成立 |
| 修法最小且沿先例 | 行 52：`FinsRuntimeUploadRequest` 纳入 `ValidatedFinsUploadMaterialRequest`；行 16/52：validated 类型与 raw、filing validated 类型同置 `ingestion_runtime.py` | 加宽模式与既有 `ValidatedFinsUploadFilingRequest` 入 union 的先例逐字同构；tool 路径 admission 落点在 `prepare_observed_upload` 实现内 `_validate_runtime_upload_request`（`:4714-4748`，含 filing validated isinstance 透传先例），先于 `_prepare_observed_stream` 创建 observation/job——"observation/job 创建前调用同一 admission"属实 | 反证成立 |
| fake 同步与白名单 | 行 52：`tests/service/test_fins_wait_adapter.py` 对应 fake 两方法同步改注解；行 62 生产白名单列 `ingestion/observation_handle.py`（两处协议类型）；行 64 测试白名单首列 `test_fins_wait_adapter.py`（两处 fake 类型） | fake 实测两处：`tests/service/test_fins_wait_adapter.py:916/:932`、另一处 `tests/fins/test_fins_ingestion_tools.py:603/:619`（后者在 plan 必改调用测试清单内），均注解 `FinsUploadRequest` | 反证成立 |
| rg 对账模式补全 | 行 64：模式含 `FinsUploadRequest\|FinsRuntimeUploadRequest` 裸别名 | 别名残余消费点实测：`service_runtime.py:21/:294`、`fins_direct.py:35`、`upload_tools.py:31`——加宽为向后兼容（协议实现已收更宽类型），且均在白名单/对账覆盖内 | 反证成立 |

## F3 反证：三处 storage 控制名真源与 dead import 清理 —— 已修复

| 子项 | plan 文本 | HEAD 源码证据 | 结论 |
| --- | --- | --- | --- |
| 唯一集合与三消费点 | 行 18：`asset_filename_contract.py` 从 `_fs_storage_utils.py` 的 `_SOURCE_META_FILENAME` 与 `_fs_identity.py` 的 `_IDENTITY_DESCRIPTOR_FILENAME` 构造唯一 `DOCUMENT_SOURCE_CONTROL_FILENAMES: Final[frozenset[str]]`，经 `storage/__init__.py` 导出；三处 walker 同片消费，行为序列"exact 拒绝、exact 跳过、exact 跳过" | 常量实测：`_fs_storage_utils.py:20` `"meta.json"`、`_fs_identity.py:40` `".identity.json"`。三处内联集合实测：`_fs_source_integrity.py:669`（declared walker，`name in {...}` → return None 拒绝）、`:856`（物理 walker，`child.name in {...}` → continue 跳过）、`_fs_maintenance_core.py:579-583`（rejected filing artifact walker，同构跳过）。frozenset 替换 set 字面保持 exact membership 语义 | 反证成立 |
| dead import 精度 | 行 30："两模块迁走控制名集合后，均同片删除仅供该集合使用的 `_IDENTITY_DESCRIPTOR_FILENAME` 直接 import；`_SOURCE_META_FILENAME` 直接 import 仍供各自 `meta_path` 使用" | rg 全量命中：`_IDENTITY_DESCRIPTOR_FILENAME` 在两模块的全部用途即迁移集合字面（`_fs_source_integrity.py:31/:669/:856`、`_fs_maintenance_core.py:23/:581-582`），迁后 import 必死；`_SOURCE_META_FILENAME` 另有 meta_path 用途（`_fs_source_integrity.py:479`、`_fs_maintenance_core.py:554`），应留。plan 措辞与事实逐字吻合（第四轮的失实括号断言已消除） | 反证成立 |
| `material_manifest.json` 排除 | 行 18：它是 source root 控制文件，不得放进该集合 | `_fs_storage_infra.py:3168/:3183`：manifest 位于 ticker materials 目录/source root，非 document 目录与 original 同层；`_fs_source_integrity.py:69` 另有独立 `_MATERIAL_MANIFEST_FILENAME` 常量 | 反证成立 |
| `_normalize_filename` 现状断言 | 行 18："现在 `_normalize_filename` 会 `strip()`，并没有保留名或长度校验；不能写成复用既有保留名检查" | `_fs_storage_utils.py:29-52` `_normalize_path_component`：`str(value).strip()` 后仅校验空/dot-segment/分隔符/绝对路径，无保留名、无长度规则 | 反证成立 |
| 无环 | 行 30：`asset_filename_contract -> {_fs_identity -> _fs_storage_utils}`；"第三处改用集合不成环" | `_fs_maintenance_core.py:21 -> _fs_storage_infra.py`、`_fs_storage_infra.py:65 -> _fs_source_integrity.py` 现存链与新契约无交；`_fs_identity`/`_fs_storage_utils` 不 import maintenance/integrity/`__init__` 级符号（实测 import 清单）；`storage/__init__.py`（87 行）新增导出边只触及底层子模块，无回边 | 反证成立（静态） |

## F4 反证：retry hint 归属、filing `_MAX_TUPLE_ITEMS`、publication 回归缘由 —— 已修复

| 子项 | plan 文本 | HEAD 源码证据 | 结论 |
| --- | --- | --- | --- |
| (a) retry hint 非迁来物 | 行 47："现有 `FinsUploadUsageFailure`/工厂并无 retry hint 字段或旧模板可迁"；新 planner reason 的 message+新增 retry hint 模板只在低层 usage owner 定义；"`upload_failure.py` 既有非 planner public failure retry hint 保持原 owner，不声称迁移或复制" | `FinsUploadUsageFailure`（`:708-741`）仅 `code`/`message` 两字段；全部 retry hint 内联于 `upload_failure.py:237-438`（`:237/:245/:253/:261/:269/:277/:306/:328/:350/:372/:394/:416/:438`）；分类器 `fins_upload_failure_from_exception`（`:214` 起）现无 usage/planner 分支——"显式分类 planner typed error"是真实新增分支。usage 侧消费 message、failure 侧消费同源 message/hint、旧 hint 原地不动，归属二选一已钉死为"新 hint 归 usage owner" | 反证成立 |
| (b) filing 上限点名 | 行 47："`TOO_MANY_FILES` 的模板由调用方传入已判 source 上限：material 传 `MAX_MATERIAL_UPLOAD_FILES`，filing 传 `ingestion_runtime.py` 既有 `_MAX_TUPLE_ITEMS`，当前均为 100，输出逐字不变且不传裸 `100`" | filing 限额真源实测 `:1266` `len(request.files) > _MAX_TUPLE_ITEMS`；`TOO_MANY_FILES` 全库唯一产生点 `:1267`；现文案 `:1033` "--files 数量不能超过 100 个"——参数化后两侧逐字保持可行 | 反证成立 |
| (c) publication 测试缘由 | 行 64："`tests/fins/test_filing_upload_publication.py` 不 import usage 类型；因 `_PendingFileAsset`/`_PreparedFilingAssetMutation` 的 prepared asset 形状或构造签名可能改变而纳入同切片，发生变化才迁移其直接构造与断言，无论是否修改该文件都运行发布回归" | 实测该文件无 usage import（仅 `:107` docstring 提及 `FinsUploadUsageError`）；`:34-45` 直接 import `FinsUploadFilingRequest/ValidatedFinsUploadFilingRequest/validate_fins_upload_filing_request` 与 `docling_upload_service` 的 `_PendingFileAsset`、`_PreparedFilingAssetMutation`——条件性纳入缘由与真实依赖一致，第四轮失实理由已删除 | 反证成立 |

## 不回退项 adversarial 复证（全部成立）

| 项 | 直接证据 | 结论 |
| --- | --- | --- |
| 100/101 边界 | plan 行 16/24/28：`MAX_MATERIAL_UPLOAD_FILES = 100` 唯一真源归规划 owner，schema/文案派生；`_MAX_TUPLE_ITEMS`（`:167`）降格为通用 tuple/摘要/filing/alias 用途。现状：material 101 仅在摘要 `_validate_upload_file_count`（`:7861-7875`）以裸 `ValueError` 失败——plan"摘要只消费 validated handoff 的数量事实"将其移除；tool schema `"maxItems": 100`（`upload_tools.py:243`）。分级真实 CLI 证据（行 83：101 侧 exit 2/typed/converter 0/零发布；100 侧 admission 全接受+至少首个 converter 启动、不冒充成功发布；受控 converter 100 次调度；小 N 同 stem 完整发布）与第二/四轮裁决口径逐句一致 | 未回退 |
| CLI 缺文件 exit 2 | plan 行 51：helper 改为只返回预检路径 tuple，保留逐项 `expanduser().resolve(strict=False)`/`exists()`/`is_file()`、`CliFinsUsageError`、双模板与"现有包含解析后路径的文案"，在 raw request 构造前；行 64/68：缺失文件与目录两例断言 raw request/service/converter 均未启动、exit 2、stderr 逐字一致；不把缺单个文件改判 `MISSING_FILES`。现状实测：模板 `fins.py:98-99`、`EXIT_USAGE_ERROR=2`（`exit_codes.py:10`）、`FinsUploadUsageError` handler `fins.py:198-200`、helper `fins.py:1128-1147`、唯一调用点 `:728` | 未回退 |
| 单一 original→Docling 名函数 | plan 行 20：`docling_storage_name(source_kind, original_storage_name)` 单 owner；material 完整原件名加 `_docling.json`；filing 保持 `original-` 前缀校验后身份加后缀；规则迁入并删除旧函数，不留 re-export/wrapper/双实现。现状动机实测：material original `file_path.name`（`docling_upload_service.py:928`）、derived `f"{file_path.stem}{DOCLING_FILE_SUFFIX}"`（`:1029`）→ 同 stem 碰撞真实。迁移面实测：`DOCLING_FILE_SUFFIX`、`_build_filing_derived_asset_identity` 模块外零消费者（rg 空）；`_build_filing_original_asset_identity` 模块外导入恰 4 测试文件（`test_docling_upload_service.py:43`、`test_fins_ingestion_runtime.py:131`、`test_sec_pipeline_upload_filing_stream.py:50`、`test_cn_pipeline.py:46`），与 plan 行 64 点名一致 | 未回退 |
| filing identity 字节 | 常量 `docling_upload_service.py:78-81`（namespace `fins-upload-asset-v1`、`b"\0"` separator、`original-` 前缀）；`:1511-1535` guard（absolute 且 `resolve(strict=False)==normalized`）、digest 输入 `namespace.encode+b"\0"+as_posix().encode`、输出 `original-<完整 hexdigest><suffix.lower()>`；`:1538-1553` 前缀校验后加后缀。plan 行 20"不放宽 filing 的旧失败规则""filing 原件身份算法不变"、行 69"旧 original/derived identity 逐字一致"逐字吻合 | 未回退 |
| O25 依赖 | 现状 primary=首个转换产物（`:1032-1033` `if primary_document is None: primary_document = docling_name`）。plan 行 12（不改选择规则、不升格公开契约）、行 54（O25 只变选择与同源指纹/skip，不另算资产名）、行 86-87（依赖登记、不宣称已解决） | 未回退 |
| 同源 manifest/资产规划 | plan 行 16：validated handoff 含**同一** `UploadAssetPlan`（`ordered_pairs`/`converter_pairs` 指向同一 pair 对象）；行 54：`_build_original_assets`/`_build_pending_assets`/fingerprint/meta/manifest/read 只消费计划，删除 `ordered_files.index()` 与推断；行 22：planner 收显式 `Literal["upsert","delete"]`，delete 空 plan 跳过 upsert 校验 | 未回退 |
| company_id 事实 | plan 行 53："旧 façade 的 `company_id` 参数在 SEC/CN 实现中均未作为身份输入"。实测 `sec_upload_workflow.py:454` docstring"可选兼容字段；上传链路不会把它作为身份真源"，`:472` 与 `cn_pipeline.py:1089` 均以 `build_upload_company_id(normalized_ticker)` 派生 canonical（定义 `upload_company_meta.py:199`） | 未回退 |
| 切片/白名单/命令 | 行 60：单一端到端切片，理由（拆开留双真源）成立；行 62 生产白名单 19 文件、行 64 测试 17 文件，与行 74 pytest、行 78 逐文件 coverage 循环清单逐一对应；行 64 rg 模式含全部旧 scalar/request/usage/helper 符号；行 75-77 pyright + import smoke（含 `DOCUMENT_SOURCE_CONTROL_FILENAMES == frozenset({"meta.json", ".identity.json"})` 断言，与两常量实测一致）；行 70 README 按触发规则检查、`.venv`/coverage 缺失记验证缺项 | 未回退 |

## Findings

无新增 finding。第四轮 F1–F4 全部以源码直接证据复证为已修复且未过度：usage 迁移的伴随常量归属、协议/触点清单、常量级 import 精度、迁移描述三处偏差均已按裁决一句话钉死；owner 归属、import 图、admission 时序、分级证据口径未留给实施者发明。旧高/中/低项无回退，goal/plan/HEAD 三者一致，无 goal drift。

## Residual risks（沿用 plan 自披露与既往裁决，本轮复证维持）

| 风险 | 处置 | 追踪去向 |
| --- | --- | --- |
| `NFC+casefold+NFC` 保守键可能多拒；不证明所有平台 alias | plan 行 24/89 披露；storage 最终完整性兜底；文件系统反例触发硬停止 | closeout residual |
| `NAME_MAX=255` 仅本工作区观测（本轮 `getconf NAME_MAX .` 实测 255 复核一致）；目标卷更小退化为迟 `OSError` | plan 行 26/89；actual limit 归 storage filename owner | closeout residual |
| admission 与读取间 TOCTOU | plan 行 89；既有完整性机制处理 | closeout residual |
| material 派生名修正后同内容重传指纹/skip 一次性变化 | plan 行 89；实施 evidence 如实记录 | 实施 evidence |
| filing/material 上限同值共用 schema/message；将来分离须同源重审 | plan 行 28/89 登记；参数化后两真源分别为 `MAX_MATERIAL_UPLOAD_FILES`/`_MAX_TUPLE_ITEMS` | closeout residual |
| 逐文件不存在/非普通文件的跨入口 typed 统一与 CLI 旧文案 | 已登记独立 WU `fins-material-file-existence-admission`；本片保留 CLI 预检/exit 2/现有文案 | 后续 WU |
| plan 行 52 类名笔误 `FinsProductionUploadRunner`（实际 `ProductionFinsUploadRunner`，`service_runtime.py:99` 实测；行 64 已用真名） | 第四轮已记、裁决维持"实施按真名即可"；第五修订仍未改 | 不阻塞；实施按真名 |
| 隐含边 `upload_failure -> upload_asset_plan`（分类 `FinsUploadAssetPlanError` 所需）未在行 30 import 图句中显式点名 | 行 47 分类器要求已隐含该边；静态反证无环；行 30 硬停止覆盖实施期发现的循环 | 实施 import smoke 复核 |
| 冻结 F20/F21/F22/S19/S20 不作修复后测试 | plan 行 4 声明 | 维持 |
| O25 primary 选择规则 | plan 行 86-87 明确留 O25 | O25 work unit |
| 公司 meta 提前副作用（O34） | plan 行 10 声明非目标 | UM-O34 work unit |

## 验证方式与未覆盖项声明

- 本 review 全部断言来自本 HEAD 工作区源码直读、`shasum`/`getconf`/`rg`/`grep` 实测；plan 与 goal SHA 均先核后审，无漂移。
- 本 checkout 无 `.venv`，未运行 pytest/pyright/import smoke——plan 阶段无代码改动，这些属实施 gate（plan 行 70 亦如此声明）；import 无环结论为对现存 import 边的静态反证，未断言新模块运行时行为。
- 未覆盖：`_DirectUploadProducer` 内部逐行核对（其 request 类型迁移由协议/runner 签名与 rg 对账覆盖）；真实 CLI 证据属实施后 gate，本轮不评价。

## 结论

**pass**。

第四轮裁决的 F1–F4 在第五修订（SHA `88b03cd2…049e13`）中全部落实并经 HEAD 源码独立反证：usage owner 的 `FINS_UPLOAD_USAGE_TEXT_LIMIT` named 上界与 `_FILE_USAGE_CODES` 随迁精确匹配 `_MAX_TEXT_CHARS` 七处非 usage 用途的源码事实，工厂测试迁移锚点 `:1389` 实测准确，提议 import 图静态无环且迁移动机（`ingestion_runtime.py:133` 现存边）真实；observation 协议两方法与两处 fake 的 validated handoff 触点、白名单与 rg 模式已补全且沿 `ValidatedFinsUploadFilingRequest` 先例；三处 storage 控制名 walker 共用唯一集合、`_IDENTITY_DESCRIPTOR_FILENAME` dead import 与 `_SOURCE_META_FILENAME` meta_path 保留的常量级精度与 rg 全量命中一致；retry hint"无旧模板可迁"、filing 传 `_MAX_TUPLE_ITEMS`、`test_filing_upload_publication.py` 条件性纳入缘由三处描述已改为与源码逐字吻合。旧 100/101、CLI 缺文件 exit 2、单一 original→Docling 名函数、filing identity 字节、O25 依赖、同源 manifest/资产规划、切片/白名单/覆盖率/pyright/README 逐项复证无回退。残余均为 plan 自披露并已有追踪去向，无阻塞项。按 Gateflow 约束，本路通过并不单独构成实施许可；仍待 MiMo 同版有效复审。

CANARY=kimi-00ae7455
