# Plan Review（独立复审）：UM-O04-F01 + UM-O23-F01 material 资产数量与身份规划（第五次修订）

RUNTIME/PROVIDER/MODEL: claude/mimo/mimo-v2.6-pro[1m]
CANARY=mimo-377ca477

- Review label：`assets-plan-rereview5-mimo-20260929-05`；gate：plan review -> fix（独立复审，以源码反证第四轮 MiMo F1–F4 的落实，并复证旧 100/101、CLI exit2、唯一 Docling 命名、filing identity 字节、O25、同源 manifest/资产规划、切片/白名单/覆盖率/pyright/README 未回退）。
- 审查对象：`docs/gateflow/upload-material-assets-plan-20260929.md`（SHA-256 实测 `88b03cd247dc5d6d6c1fa9cb3dc113046a5c796ab40a61083d0c1cd00a049e13`，与任务预期及 `docs/gateflow/upload-material-assets-plan-review-adjudication-20260929.md` 末段记录一致，无版本冲突；核对先于全部审查动作执行）。
- Binding goal：`docs/gateflow/upload-material-assets-goal-20260929.md`（SHA-256 实测 `208d4008caa8e6a0c870a1e1f929e3c706e0bbbdb97ef89f3c6d6c1888f86e36`，与第 2–4 轮 review 记录一致，goal 未变）。
- 核对依据：总控裁决 `docs/gateflow/upload-material-assets-plan-review-adjudication-20260929.md`（MiMo 首轮 F1-F7、Kimi 首轮 F1/F2/F4、第 2–4 轮 MiMo findings 与五次 Sol fix 记录），前轮 `docs/reviews/plan-review-20260929-assets-rereview4-mimo.md`（MiMo 第四轮，F1–F4 为本轮待反证清单）及 `plan-review-20260929-055331-assets-mimo.md`、`plan-review-20260929-051109.md`、`plan-review-20260929-033914.md`、`plan-review-20260929-023619.md`（Kimi 首轮）作 lineage。
- 依据 HEAD：`8d8d494fbbce0052372fb1b42097c9f7222cfa28`（`git rev-parse` 实测一致；工作区仅 8 个未跟踪 gateflow/review 文档，无产品改动；checkout 缺 `.venv` 与待实施新模块）。
- 全部断言直接读取本 HEAD 源码/测试与实测得出，不采信候选 plan 或 Sol 自述；未读 Kimi 同轮 review；未实施任何 fix、未改 plan/goal/adjudication/产品/测试/README/既有 review、未 commit/push/PR、未派发子 Agent、未发外部消息。

## 审查范围

按任务焦点：(1) 以源码反证第四轮 F1——新 usage owner 的命名 240 上界、`_FILE_USAGE_CODES` 归属、工厂 owner 测试迁移与 import 无环；(2) F2——observation 协议两方法与 Service fake 的 validated handoff 触点；(3) F3——三处 storage 控制名成员事实收敛为唯一真源与 dead import 清理；(4) F4——retry hint 当前/新增归属、filing `_MAX_TUPLE_ITEMS` 真源、`test_filing_upload_publication.py` 回归缘由；(5) adversarial 复证旧项不回退：100/101、CLI 缺文件 exit 2、单一 original→Docling 命名函数、filing identity 字节、O25 依赖、同源 manifest/资产规划、单切片/白名单/覆盖率/pyright/README；(6) goal drift、架构边界、过度耦合、执行时序与测试缺口检查。

## Assumptions tested（HEAD 直接证据重证）

| # | Plan / 裁决断言 | 重证结果 | 直接证据 |
| --- | --- | --- | --- |
| A1 | usage 5 符号定义于 `ingestion_runtime.py`，迁移面完整 | 成立 | `ingestion_runtime.py:673` `FinsUploadUsageCode`、`:708` `FinsUploadUsageFailure`、`:743` `FinsUploadUsageError`、`:1027` `_USAGE_MESSAGES`、`:1062` `fins_upload_usage_failure` |
| A2 | `_MAX_TEXT_CHARS=240` 的 usage/非 usage 分界与 plan 归属句一致 | 成立 | `:166` 定义；usage 用途恰两处 `:739`（`FinsUploadUsageFailure.__post_init__` 消息上界）、`:1095`（工厂消息上界）；非 usage 用途 `:1277/:1368/:7106-7107/:7403-7404/:7478/:9000-9002`（fiscal-period、文本截断等），`rg '_MAX_TEXT_CHARS'` 全库无他处 |
| A3 | `_FILE_USAGE_CODES` 为工厂私有伴随件 | 成立 | `:1021-1025` 定义为 `{FILE_NOT_FOUND, FILE_NOT_REGULAR}`；唯一消费点 `:1081` 工厂内部；全库无第二消费点 |
| A4 | 工厂 owner 测试位于 `test_fins_ingestion_runtime.py:1389` 起 | 成立 | `:1389` `test_fins_upload_usage_failure_mapping_is_closed_bounded_and_path_free`、`:1494` `test_upload_usage_failure_fact_rejects_open_code_and_unbounded_message`（自述"240 字符消息上界"），与 plan"随定义迁至 `test_upload_usage_contract.py`"的起点逐字对应 |
| A5 | import 成环动机真实、提议图无环 | 成立 | 现边 `ingestion_runtime.py:133` import `upload_failure`；`upload_failure.py` 头部 import（contracts/direct_events/company_meta_contract/docling_process_converter/storage/`upload_format_contract`/runtime.filelock）无 `ingestion_runtime`——若 usage 文案留原处而 `upload_failure` 回取即成 `upload_failure -> ingestion_runtime -> upload_failure` 环。提议底层链实测无反向边：`upload_format_contract.py:8-22` 仅 import `dayu.documents.docling_runtime` + `dayu.fins.direct_events`（`FinsUploadFormatFailureKind` 在 `:41`）；二者无 `ingestion_runtime`/`upload_failure` 引用（rg 空）；`_fs_identity.py` 仅依赖 stdlib + `ticker_normalization` + `_fs_storage_utils`；`_fs_storage_utils.py` 仅依赖 stdlib + contracts + domain；全库 import `ingestion_runtime` 的模块清单（service/cli/pipelines/tools/tests 等）不含提议底层链任何成员。`upload_usage_contract`/`upload_asset_plan`/`asset_filename_contract` 三新模块均不存在（实测 ls），按停止条件不以不可 import 断言设计必成环，结构反证无环，真实 import smoke 属实施 gate（plan 行 76-77 已配） |
| A6 | 240 命名上界的 per-contract 先例存在 | 成立 | `download_contract.py:43` `FINS_DOWNLOAD_PUBLIC_MAX_TEXT_CHARS: Final[int] = 240`；`upload_failure.py:24` `_MAX_FAILURE_TEXT_CHARS: Final[int] = 240`（校验 failure.message/retry_hint）；`direct_events.py:36` `_MAX_DETAIL_CHARS: Final[int] = 240`——plan 的 `FINS_UPLOAD_USAGE_TEXT_LIMIT: Final[int] = 240` 落入既有命名模式，"不散写裸 240"可执行 |
| A7 | observation 协议触点与 fake 现状 | 成立 | `observation_handle.py:29` import `FinsUploadRequest`，`:240-242`/`:254-256` 两方法均注解 `request: FinsUploadRequest`（= `FinsUploadFilingRequest \| FinsUploadMaterialRequest`，`ingestion_runtime.py:1581`）；`FinsRuntimeUploadRequest` 定义 `:1582`；协议实现/注解点全库恰 4 处：协议本体、`ingestion_runtime.py` 实现（`:3822/:3850`）、`tests/service/test_fins_wait_adapter.py:916/:932` fake（`:81` import）、`tests/fins/test_fins_ingestion_tools.py:603/:619` fake（`:39` import）；isinstance 透传先例 `:4726-4728` |
| A8 | storage 控制名成员判定恰三处字面、两模块常量用途分界 | 成立 | `_fs_storage_utils.py:20` `"meta.json"`、`_fs_identity.py:40` `".identity.json"`；成员集合字面恰三处：`_fs_source_integrity.py:669`（declared 名 exact 拒绝）、`:856`（物理 walker exact 跳过）、`_fs_maintenance_core.py:579-583`（rejected filing artifact 比对跳过）。`_IDENTITY_DESCRIPTOR_FILENAME` 在 `_fs_source_integrity.py` 仅 `:31` import + `:669/:856`，在 `_fs_maintenance_core.py` 仅 `:23` import + `:581-582`——迁集合后 import 确为 dead；`_SOURCE_META_FILENAME` 另有 meta_path 用途（`_fs_source_integrity.py:479`、`_fs_maintenance_core.py:554`）。其它模块（`_fs_source_snapshot.py:935/:939`、`_fs_blob_core.py:78`、`_fs_storage_infra.py`）用 identity 常量做路径/排除，不在"仅供该集合使用"范围 |
| A9 | retry hint 现状：usage 侧无 hint，public failure hint 在 `upload_failure.py` | 成立 | `FinsUploadUsageFailure` 字段仅 `code`+`message`（`:716-717`），无 retry_hint；`upload_failure.py` 既有 hint 内联 `:237-416`（按 code 各一条）+ 字段/校验 `:87/:94/:119-120/:463/:472`；plan"并无 retry hint 字段或旧模板可迁""旧 hint 保持原 owner，不声称迁移或复制"与源码一致 |
| A10 | filing 数量限额真源是 `_MAX_TUPLE_ITEMS` | 成立 | `:167` 定义；filing 静态 admission `:1266` `len(request.files) > _MAX_TUPLE_ITEMS` → `TOO_MANY_FILES`；同常量另用于 alias `:1180`、通用 tuple `:7530`、摘要 `:7874`、metadata `:7912`——plan"filing 传 `_MAX_TUPLE_ITEMS`……不传裸 100"指向正确真源 |
| A11 | `test_filing_upload_publication.py` 不 import usage 类型 | 成立 | import 面（`:34-47`）为 `ingestion_runtime` 请求/校验类型 + `docling_upload_service` 的 `_PendingFileAsset`/`_PreparedFilingAssetMutation`（`:43-44`）；`FinsUploadUsage` 全文件仅 `:107` docstring 提及。plan 修正后的纳入缘由（prepared asset 形状/构造签名可能变 + 无论是否改都跑发布回归）与事实一致 |
| A12 | 100/101 现状与 plan 数量设计一致 | 成立 | material 无 typed 前置：`_validate_upload_file_count`（`:7861-7875`）以裸 `ValueError` 在摘要处触发（`:7874` 用 `_MAX_TUPLE_ITEMS`）；`upload_tools.py:243` 共用 schema `"maxItems": 100`；`_USAGE_MESSAGES[TOO_MANY_FILES]` 文案 "--files 数量不能超过 100 个"（字面 100 待参数化）。plan"不得继续让 material 101 在摘要处以裸 `ValueError` 先失败；摘要只消费 validated handoff 的数量事实"与现状缺口吻合 |
| A13 | CLI 缺文件预检现状与 plan 钉死点一致 | 成立 | `fins.py:98-99` 双模板 `"upload file does not exist: {path}"` / `"upload path is not a file: {path}"`（含解析后全路径）；`_validated_upload_files` 实现 `:1128-1147`（`expanduser().resolve(strict=False)`+`exists()`+`is_file()`→`CliFinsUsageError`）；`CliFinsUsageError`/`FinsUploadUsageError` handler `:186-200` → `EXIT_USAGE_ERROR`（exit 2） |
| A14 | material 命名 stem 冲突动机与 filing identity 字节 | 成立 | `docling_upload_service.py:928-930` original=`file_path.name`、`:1029` derived=`f"{file_path.stem}{DOCLING_FILE_SUFFIX}"`（`deck.txt`/`deck.md` 同名动机成立）；常量 `:78-81`（`_docling.json`、`fins-upload-asset-v1`、`b"\0"`、`original-`）；`_build_filing_original_asset_identity`（`:1511-1535`）guard absolute/normalized，digest 输入 `namespace.encode+b"\0"+as_posix().encode`，输出 `original-<完整 hexdigest><suffix.lower()>`；`_build_filing_derived_asset_identity`（`:1538-1553`）require 前缀后追加 `_docling.json`。plan 行 20 迁移描述逐字吻合 |
| A15 | O25 边界与 material 指纹/primary 现状 | 成立 | material 指纹 payload=name+sha256+size+source 按 name 排序、无 primary 分量（`:1719-1735`）；primary=首个转换产物（`:1032-1033`）；filing `ordered_files.index()` 待删点（`:983` 一带）。plan 行 12/54/87 只稳定名称/pair 身份、O25 只改选择规则、不宣称本单解决，边界保持 |
| A16 | 同源 manifest/资产规划 | 成立 | `material_manifest.json` 在 source root `materials/`（`_fs_storage_infra.py:3168` 一带 `ticker_dir/"materials"/"material_manifest.json"`），非 document 目录控制名——plan"不得放进该集合"正确；meta/manifest/read 沿计划传递（plan 行 54）无下游重算 |
| A17 | 白名单/rg/coverage/pytest 对账完备 | 成立 | 实跑 plan 行 64 的 rg 模式（含 `FinsUploadRequest\|FinsRuntimeUploadRequest`）：`dayu/`+`tests/` 命中恰 12 生产模块 + 11 测试文件 + 2 README（`dayu/fins/README.md`、`dayu/service/README.md`），全部已在 plan 生产/测试白名单或 README 检查句覆盖（`observation_handle.py`、`test_fins_wait_adapter.py` 为本轮 F2 补入项）；coverage 循环 19 文件与生产触点清单逐一对应；pytest 命令 17 文件与测试触点清单（3 新 + 13 更新 + 条件性 `test_filing_upload_publication.py`）一致 |
| A18 | goal/plan/HEAD 一致，无 goal drift | 成立 | plan SHA `88b03cd2…`、goal SHA `208d4008…`、HEAD `8d8d494f…` 均实测一致；goal"100 个以内允许，101 个前置拒绝""一个 original→Docling 函数""转换前 typed 拒绝"未被拔高或缩水；本轮修订全部为前轮 finding 的文本/清单收敛，无新目标、新验收标准或 future-slice 工作混入 |

## 逐项核对：第四轮 F1–F4（源码反证）

| 项 | 第四轮要求 | plan 现文 | 源码反证 | 结论 |
| --- | --- | --- | --- | --- |
| F1 usage 迁移伴随件：命名 240 上界、`_FILE_USAGE_CODES`、工厂测试迁移、import 无环 | usage owner 自持命名上界（禁 import `_MAX_TEXT_CHARS`、禁裸 240）；`_FILE_USAGE_CODES` 随工厂私有化；`test_fins_ingestion_runtime.py:1389` 起工厂 closed/bounded/path-free 测试随迁；补无环验证 | 行 30：`FINS_UPLOAD_USAGE_TEXT_LIMIT: Final[int] = 240` 供 `FinsUploadUsageFailure` 校验与工厂上界共用；`_MAX_TEXT_CHARS` 留 `ingestion_runtime` 服务非 usage 文本，不反向导入、不散写裸 240；"`_FILE_USAGE_CODES` 保持工厂私有集合"；行 68："1389 起的工厂 closed/bounded/path-free owner 测试随定义迁至 `test_upload_usage_contract.py`"；行 76-77 真实 import smoke + 集合 assert | A2/A3/A4/A5/A6 逐项吻合：usage 用途恰 `:739/:1095` 两处、非 usage 7 处留原地；`_FILE_USAGE_CODES` 唯一消费即工厂 `:1081`；两工厂测试实存于 :1389/:1494；成环边 `:133` 真实、提议图底层链无反向边；240 命名先例三处 | **已落实**，无环结构反证成立（真实 import smoke 留实施 gate） |
| F2 observation 协议两方法与 Service fake 的 validated handoff | 协议 request 类型扩至含 validated material；`test_fins_wait_adapter.py` fake 同步；白名单+rg 模式+命令同步 | 行 52：`start_observed_upload`/`prepare_observed_upload` 协议类型改覆盖 validated material 的 `FinsRuntimeUploadRequest`，"`FinsRuntimeUploadRequest` 纳入 `ValidatedFinsUploadMaterialRequest`"，wait_adapter fake 两方法同步改注解，"不能在协议边界拆回 raw 或二次 admission"；行 62/64 白名单含 `observation_handle.py` 与 `test_fins_wait_adapter.py`；行 64 rg 模式含 `FinsUploadRequest\|FinsRuntimeUploadRequest` 且对账句"包含 observation 协议及 fake、monkeypatch、裸别名类型标注" | A7：两方法现注解 raw `FinsUploadRequest`（`:240/:256`），扩型后 `FinsRuntimeUploadRequest` 承载 validated material 与 isinstance 透传先例（`:4726-4728`）自洽；实跑 rg 模式可捞出协议与全部 fake 的裸别名行；pytest/coverage 含两文件与 `observation_handle.py` | **已落实**；`tests/fins/test_fins_ingestion_tools.py:603/:619` 的第二个 fake 未在行 52 点名，但已被必改清单+rg 对账+pyright 三重网覆盖（见残余注 R1） |
| F3 三处 storage 控制名真源与 dead import 清理 | 括号断言改精确：`_IDENTITY_DESCRIPTOR_FILENAME` import 同片删除、`_SOURCE_META_FILENAME` 留 meta_path；三消费点收敛唯一集合 | 行 30："两模块迁走控制名集合后，均同片删除仅供该集合使用的 `_IDENTITY_DESCRIPTOR_FILENAME` 直接 import；`_SOURCE_META_FILENAME` 直接 import 仍供各自 `meta_path` 使用"；行 18 三消费点依次"exact 拒绝/跳过/跳过"；行 70 迁移后 "`_IDENTITY_DESCRIPTOR_FILENAME` 零命中、`_SOURCE_META_FILENAME` 仍供 `meta_path` 使用" | A8：两模块中 identity 常量用途恰为集合字面（迁后 import 即 dead），meta 常量 meta_path 用途在 `:479/:554`——plan 精确到常量级；三处成员字面与 plan 消费点一一对应；`material_manifest.json` 在 source root（A16）不入集合 | **已落实** |
| F4 retry hint 归属、filing 上限真源、`test_filing_upload_publication.py` 缘由 | (a) message 迁移/新 hint 归属二选一钉死；(b) filing 点名 `_MAX_TUPLE_ITEMS`；(c) 改为 prepared asset 形状条件性纳入+无论如何跑发布回归 | 行 47："现有 `FinsUploadUsageFailure`/工厂并无 retry hint 字段或旧模板可迁"；"新 planner reason 的有界中文 message 与新增 retry hint 模板**只**在该低层 usage owner 定义"；"`upload_failure.py` 既有非 planner public failure retry hint 保持原 owner，不声称迁移或复制"；"filing 传 `ingestion_runtime.py` 既有 `_MAX_TUPLE_ITEMS`……不传裸 `100`"；行 64："不 import usage 类型；因 `_PendingFileAsset`/`_PreparedFilingAssetMutation` 的 prepared asset 形状或构造签名可能改变而纳入同切片……无论是否修改该文件都运行发布回归" | A9/A10/A11：usage failure 无 hint 字段属实；hint 现场在 `upload_failure.py:237-416` 属"保持原 owner"对象；filing 限额判定即 `:1266 _MAX_TUPLE_ITEMS`；publication 测试 import 事实（无 usage、有 prepared asset 类型）与新缘由逐字吻合 | **已落实**，三处偏差全部收敛 |

## 前轮高/中项与旧项 adversarial 复证（是否回退）

| 项 | 复证 | 结论 |
| --- | --- | --- |
| 100/101 边界 | A12 + plan 行 16/24/28：`MAX_MATERIAL_UPLOAD_FILES = 100` 归规划 owner、1..100 放行/101 前置 typed 拒绝、`_MAX_TUPLE_ITEMS` 降格为通用 tuple/filing 契约、摘要不再裸 `ValueError` 先失败、schema/message 从真源派生且上限分离登记残余；行 68 owner 级 100/101 两侧必过 + 受控 converter 100 次调度；行 83 真实 CLI 分级（101：exit 2/typed/converter 0/零发布；100：admission 全接受+至少首个 converter 启动、不冒充成功发布；小 N 同 stem 完整发布）与裁决口径逐句保持 | 未回退 |
| CLI 缺文件 exit 2 | A13 + plan 行 51：helper 改只返回预检路径 tuple，保留 exists/is_file、`CliFinsUsageError`、双模板、exit 2、解析后全路径文案，"不要把缺单个文件/目录改判为 `MISSING_FILES`"；行 64/68 新增缺失文件/目录两例（raw request/service/converter 均未启动、文案逐字一致） | 未回退 |
| 单一 original→Docling 命名函数 | A14 + plan 行 20：`docling_storage_name(source_kind, original_storage_name)` 单 owner；material 完整原件名加后缀（不 stem/不序号/不 hash 截断）；filing 保持 `original-` 前缀校验后返回现有身份加同一后缀；identity 路径 namespace/`b"\0"`/digest/suffix 规则迁入并**删除旧函数**，同片迁移服务调用与四处测试导入（行 64 点名 `test_docling_upload_service.py`、`test_fins_ingestion_runtime.py`、`test_sec_pipeline_upload_filing_stream.py`、`test_cn_pipeline.py`），"不留 re-export、wrapper 或双实现窗口" | 未回退 |
| filing identity 字节 | A14：namespace `fins-upload-asset-v1`、separator `b"\0"`、完整 SHA-256 hexdigest、`suffix.lower()`、`original-` guard、derived 追加 `_docling.json` 与 plan 行 20 逐字一致；"filing 原件身份算法不变"；行 69"旧 original/derived identity 逐字一致"回归 | 未回退 |
| raw/validated handoff | plan 行 16（`ValidatedFinsUploadMaterialRequest` 不可变必填 handoff，含 raw request + authoritative `FinsUploadMaterialFiles` + 同一 `UploadAssetPlan`）、行 49-53（raw façade/`upload_material_validated` 分名、每链恰好 admission 一次、runner 传原 handoff 不展开、无 `raw\|validated` 联合/可空 plan/isinstance 双路、旧 scalar 同片消失）；A7 证实协议/透传先例；行 64 迁移断言（admission 次数、对象身份不重入、旧 scalar 全消失） | 未回退 |
| O25 依赖 | A15 + plan 行 12/54/87：只稳定名称映射与 pair 身份；O25 后续只改选择与同源指纹/skip/meta/read；首转换 primary、逆序同指纹记为 O25 依赖"不能将其称为本工作单已解决" | 未回退 |
| 同源 manifest/资产规划 | A16 + plan 行 18/54：`material_manifest.json` 不入 document 控制名集合（source root 事实吻合）；转换、blob/file entry、primary、fingerprint、meta/manifest/read 只消费同一规划事实、消费者不重算 | 未回退 |
| 单切片 | plan 行 60：唯一端到端切片，"拆开 owner 与服务接线会留下 filing 命名双真源或半成品"，一次 review gate——与 MiMo F4/Kimi F2 裁决一致 | 未回退 |
| 白名单/覆盖率/pyright/README | A17：rg 对账实跑全部命中均在清单；coverage 19 文件=生产触点；pytest 17 文件=测试触点；pyright + 双 import smoke 命令（行 75-77）；行 70 README 检查句（fins/tests/根 + 装配边界相关 README，覆盖 `dayu/service/README.md`、`dayu/README.md` 触发）；行 70 逐文件 `--fail-under=80` 与"缺 venv 记验证缺项不称 gate pass" | 未回退 |

## Findings

**本轮无新增 finding。** 第四轮 F1–F4 全部经源码反证收敛为已落实（见逐项核对表），旧高/中项与 goal/plan/HEAD 一致性均未回退。以下为不构成 finding 的实施提示（均已有兜底网或属既有已登记残余）：

- **R1（提示，非 finding）**：plan 行 52 只点名 `tests/service/test_fins_wait_adapter.py` 的 fake 两方法改注解；`tests/fins/test_fins_ingestion_tools.py:603/:619` 存在第二个同签名 fake（A7）。该文件已在必改测试清单，rg 对账模式（含裸别名）可捞出其 `:605/:621`，且协议扩型后 pyright 必然拒绝未放宽的 fake——三重网保证不会漏；实施时两处 fake 注解须同步放宽，勿因行 52 的单点点名而只改一处。
- **R2（提示，非 finding）**：plan 行 52 类名笔误 `FinsProductionUploadRunner`，真实类为 `ProductionFinsUploadRunner`（`service_runtime.py:99`；行 64 已用真名）——第 3/4 轮已登记，维持"实施按真名"即可。
- **R3（提示，非 finding）**：plan 行 70"两处 walker 的 `_IDENTITY_DESCRIPTOR_FILENAME` 零命中"措辞略松（实为两模块三 walker），与行 30"两模块"的精确句并读无歧义；零命中检查按模块执行即可。

## Open questions

无新增 open question。第 2 轮 OQ-1（validated 类型落点）已由 plan 行 30 钉死在 `ingestion_runtime.py`（与 `ValidatedFinsUploadFilingRequest` 同置，planner 不引用 request/usage 类型）；第 3 轮 OQ1–3 与第 4 轮精度残片均已按裁决收敛。

## Residual risks 与建议追踪去向

| 风险 | Plan 既有处置 | 本复审意见与追踪去向 |
| --- | --- | --- |
| F-R1 `NFC+casefold+NFC` 保守键多拒；不证明全部平台 alias | 已披露；storage 最终完整性兜底；文件系统反例触发硬停止 | 维持；closeout residual |
| F-R5 `TOO_MANY_FILES` 文案/schema 双绑定（material 常量 vs filing `_MAX_TUPLE_ITEMS`） | plan 行 28/88 登记"上限分离时须同源重审 schema/message 绑定" | 维持；closeout residual |
| usage 文本上界的多契约常量（本 owner `FINS_UPLOAD_USAGE_TEXT_LIMIT`、`upload_failure._MAX_FAILURE_TEXT_CHARS`、`direct_events._MAX_DETAIL_CHARS`、download_contract 先例，均 240） | 各契约自持命名常量，plan"不散写裸 240" | 既有 per-contract 模式，无漂移风险；若未来公共文本上界调整须同审各契约命名常量 |
| `tests/fins/test_fins_ingestion_tools.py` 第二 fake（R1） | 必改清单+rg 对账+pyright 兜底 | 实施 evidence 确认两处 fake 注解同步 |
| plan 行 52 类名笔误（R2） | 前轮已记 | 实施按 `ProductionFinsUploadRunner` 真名 |
| material 指纹因派生名修正发生一次性变化 | 已披露，实施 evidence 如实记录 | 维持 |
| F-R6 O25：首转换 primary、指纹不含 primary、逆序同指纹 | 明确留 O25 | 维持；追踪于 O25 work unit |
| F-R7 公司 meta 提前副作用（O34） | 非目标，plan 行 10 声明 | UM-O34 work unit |
| F-R8 facade 直调 symlink 末组件 basename 变为目标名 | 已披露（plan 行 56），按新规范路径契约更新断言 | 维持 |
| F-R9 目标卷 `NAME_MAX<255` 退化为迟 `OSError` | 已披露；actual limit 归 storage filename owner | 维持 |
| F-R10 TOCTOU（admission 与读取间路径变化） | 已披露，完整性防线兜底 | 维持 |
| F-R11 冻结 F20/F21/F22/S19/S20 不作修复后测试 | 已声明 | 维持 |
| 逐文件不存在/非普通文件 typed 统一 | 登记 `fins-material-file-existence-admission` 后续 WU；本片保留 CLI 预检文案 | 维持 |
| 真实 import smoke（checkout 缺 `.venv`/新模块） | plan 行 75-77 为实施 gate 命令 | 实施时必须实跑；本轮以结构反证代替，不冒充已验证 |

## 结论

**pass-with-risks**。

第四轮 F1–F4 全部以 HEAD 源码反证收敛：F1 的 `FINS_UPLOAD_USAGE_TEXT_LIMIT: Final[int] = 240` 命名上界、`_MAX_TEXT_CHARS` 留守非 usage 用途、`_FILE_USAGE_CODES` 工厂私有化、工厂 owner 测试（`test_fins_ingestion_runtime.py:1389/:1494`）随迁与 import 无环结构反证（成环边 `ingestion_runtime.py:133` 真实、底层链无反向边、三新模块按停止条件不以不可 import 定罪）均成立；F2 的 observation 协议两方法（`observation_handle.py:240/:254`）扩型 `FinsRuntimeUploadRequest`、wait_adapter fake 同步、白名单/rg 模式/命令三同步经实跑对账成立；F3 的三处控制名成员字面（`_fs_source_integrity.py:669/:856`、`_fs_maintenance_core.py:579-583`）收敛唯一集合、`_IDENTITY_DESCRIPTOR_FILENAME` dead import 同片删除、`_SOURCE_META_FILENAME` 留 meta_path 与源码用途逐字吻合；F4 的 retry hint（无旧模板可迁、新 hint 归 usage owner、旧 hint 留 `upload_failure.py`）、filing 限额真源 `_MAX_TUPLE_ITEMS`、`test_filing_upload_publication.py` 的 prepared-asset 条件性纳入+无条件发布回归三处全部钉死。旧项 100/101、CLI 缺文件 exit 2、单一 original→Docling 命名函数、filing identity 字节、O25 依赖、同源 manifest/资产规划、单切片/白名单/覆盖率/pyright/README 逐项复证无回退；plan/goal/HEAD 三者一致，无 goal drift，本轮零新增 finding。

残余均为既有登记项或实施提示（R1–R3 有兜底网）。按 Gateflow 约束，Kimi/MiMo 有效双路 re-review 通过前不实施、不提交；候选 plan 不得冒充已实施代码。

CANARY=mimo-377ca477
