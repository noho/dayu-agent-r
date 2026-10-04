# UM-O18-F01：material amended 单一发布事实实施计划

- Gate：plan review -> fix（仅修订候选计划，尚未通过本版双路 re-review、实施或验收）。PR3-F2～F9 与已撤回的 PR3-F1 推断见 `docs/gateflow/upload-material-o18-plan-review-adjudication-20260929.md` 末节。
- 工作区：`/private/tmp/dayu-upload-o18`；分支：`codex/upload-material-o18`；基线：`8d8d494fbbce0052372fb1b42097c9f7222cfa28`。
- Binding goal：`docs/gateflow/upload-material-o18-amended-goal-20260929.md`。上游裁决只读来源：主工作区 `docs/reviews/upload-material-um-o18-oracle-adjudication.md`。目标文件在隔离 checkout，裁决文件在主工作区读取；冻结 A16/A17 是旧 commit 的观察，不能充作本计划状态转换的当前实测。
- 下一 gate：Kimi/MiMo 双路 plan re-review；本文件不代表通过 review。用户本轮只授权写 plan，禁止实施、提交、推送或派发 re-review。O12 accepted plan checkpoint 为 `/private/tmp/dayu-upload-o12/docs/gateflow/upload-material-o12-company-plan-20260929.md`（SHA-256 `48e0598bd8c949e7257b6fd6c6a03adbdca31b0def2d680d4b0cea93f7ed5e60`，总控末节判 plan gate pass），产品尚未实施。O14/O15 共用 state plan 为 `/private/tmp/dayu-upload-state/docs/gateflow/upload-material-state-plan-20260929.md`（SHA-256 `1fe2f5462a0d7a7bdb54edda3985965713a2e87890f5c8dba9b9c823e98778b6`），已存在但本版计划 gate 未双路闭合、产品尚未实施。两者均须以实际集成代码核对，不能把计划文字视为现成 API。

## 1. 目标、动机、边界和成功信号

目标是让 `amended` 表示**当前发布材料是否为修订材料**：所有 material 入口传递精确布尔值，发布准备 owner 校验并决定状态转换，source meta 持久化该事实，storage 从 source meta 投影 manifest；成功事件、结果、摘要和跨命令读取均消费同一已发布事实。稳定 material ID 不含 `amended`；`document_version` 只按现有内容指纹/发布版本规则变化。同内容标记切换须原子更新元数据且不伪造新内容版本。

动机成立。`FinsUploadMaterialRequest.amended`、CLI `--amended`、Service/tool/batch 输入和 ingestion 请求摘要已经存在；`service_runtime._run_material_upload` 到 SEC/CN/HK 的调用未传它，两个 material workflow 的 `prepare_upload(meta=...)` 也不含它。`docling_upload_service._can_skip_upload` 对 material 只看旧 meta 的删除状态、overwrite 与内容指纹；A16/A17 同时改变文件与标记，无法证明标记已生效。`MaterialManifestItem` 目前没有 amended 字段，read runtime 对缺失 `amended` 默认 false。请求、当前发布事实及读侧因此可能分叉。另由当前 `FinsUploadResultSummary` 直接可见，`ok` 强制 `stored_file_count=requested_file_count`，不能借 `ok` 表示零 original 写入的 metadata-only。

成功信号：首发默认 false/v1、首发显式 true/v1；相同 ID 的新内容按既有规则升版且标记取本次请求；同内容仅切标记且无 overwrite 时保持原件、派生文件、fingerprint 与内容版本，并在同一个已提交 batch 中更新 source meta/manifest；overwrite=true 时即使同指纹也重新 Docling 转换并发布，内容版本仍遵守现有同指纹保版规则；相同内容且标记相同、无 overwrite 才可跳过；删除保留最后发布标记，恢复由本次上传标记形成新的 active 事实。US、CN、HK 及 CLI、Service、tool、batch plan 的结果一致，真实 CLI 对照与 owner/入口测试可复核。

非目标：不改 filing amended 身份规则、material 内容抽取/格式、独立的 O13 tombstone 时间幂等、O14/O15 动作准入或 O33 并发故障根因；不迁移旧库，不重写冻结 evidence，不登记新 oracle/readiness。filing identical skip 吞 amended 的独立风险由 `fins-filing-amended-identical-skip` 跟踪，不纳入 material O18。此计划不把上游 work unit 的未实施行为写作当前代码事实。

## 2. 直接证据与 owner 判定

| 事实/边界 | 当前代码直接证据 | 计划中的 owner |
| --- | --- | --- |
| 输入 | `dayu/cli/commands/fins.py`、`dayu/service/fins_direct.py`、`dayu/fins/tools/upload_tools.py`、`dayu/fins/upload_batch.py` 均构造/传递 amended；`dayu/fins/ingestion_runtime.py:FinsUploadMaterialRequest` 默认 false，摘要记录请求值 | 入口仅保真传输；Fins material 请求校验负责精确 bool |
| 市场转送 | `dayu/fins/service_runtime.py:_run_material_upload` 的 US/CN/HK material 调用遗漏 amended；`sec_pipeline.py`、`cn_pipeline.py` 的 material 参数和 workflow 调用也无该值 | 公共 material 上传准备，而非各市场分别解释 |
| 稳定身份 | `docling_upload_service.build_material_ids` 仅用 form、name、可选 fiscal 字段；filing 的 `build_*filing_ids` 另含 amended | 保持既有 material 身份 owner，不改变 filing |
| skip/版本 | `prepare_upload` 在 Docling 前对 material 指纹相同直接返回 skipped；`_can_skip_upload` 的 overwrite 分支禁 skip；material fingerprint payload 取 original asset 的 name/hash/size/source，现行 material 路径 `identical_skip_safe=true`；`_resolve_document_version` 对初次为 v1、不同指纹升版、同指纹保留旧版 | `DoclingUploadService` 的 material preparation/发布状态机；overwrite 决定是否重发，不改版本真源 |
| 原子持久化 | `SourceDocumentRepositoryProtocol.replace_source_meta` 和 `_FsSourceDocumentMixin.replace_source_meta` 能在显式 batch 精确覆盖 meta，并由 `MaterialManifestItem.from_source_meta` 同 batch 更新 manifest；`commit_prepared_upload_batch` 拥有提交/取消边界。但当前普通 meta 读取不暴露 storage 私有 revision，`replace_source_meta` 尚非 O12 的条件提交契约 | source meta 是发布真源，storage 拥有原子写、同版 guard 与 manifest 投影；O18 只消费已集成的 O12 public contract |
| 删除/恢复 | `_toggle_source_deleted` 只更新 deletion 字段、时间及 revision 并重投影 manifest；`_build_upsert_meta` 清 tombstone、保留同指纹版本 | 删除仍归 storage；恢复的 amended 取本次成功上传 |
| 读取 | `dayu/fins/tools/read_runtime.py:list_documents` 从 source meta 投影 amended 至 `documents` 项；`recommended_documents` 仅含 document_id 槽位；`dayu/fins/tools/fins_tools.py:_build_list_documents_definition` 拥有 LLM-facing 工具说明；当前 material 缺字段默认 false | read 只从 source meta 取得当前发布标记；新 material schema 缺失应 fail closed，工具说明归 `fins_tools.py` |
| processed 快照 | `ingestion_runtime.py:_build_processed_meta` 在 preprocess 时复制 source meta；`_fs_processed_core.py` 从该 processed meta 写 processed manifest 的 amended；现行 read 仅从 processed meta 取财务能力标志，不取 amended | processed 的 amended 是 preprocess 时点快照，非当前 source 发布事实；时间语义与重处理/失效策略另由 `fins-material-processed-amended-projection` 审计 |

由此动机成立，但现有同 batch 精确替换**不足以**证明条件 metadata publication 安全。上述 O12 **已过 plan gate、尚未实施**的 §「storage 同版状态与分阶段 guard」要求完整 source business meta + **独立 opaque revision** 的同版 snapshot、每个材料 mutation batch 同时注册 `expected_source_state` 与公司阶段后的 `expected_company_meta`、publication guard 内全值比较，以及无 mutation 的 material skip 在 guard 内只读比较；当前本 O18 HEAD 尚无这些接口。O12 同版 guard 与 O14/O15 共享 action/target 准入必须**实现已集成**，且 O14/O15 本版计划 gate 须先双路闭合，才允许启动 O18 implementation；O12 的实施另以 O16/O05 accepted+integrated 为前置。实施前核对实际 public API、准入逐格回归与真实仓储交错；任一依赖缺席即停 implementation。本轮只在计划中消费上游真源，不复制 O12 guard、不在 O18 发明 O14/O15 动作表或 create-existing 过渡行为。若 O12 最终 public contract 无法表达 material mutation 和 skip 的 expected active/fingerprint/amended、独立 revision、post-company 公司状态两项条件，回到 plan review 裁决最小 storage 扩展，不用普通 `get_source_meta` 猜 revision。

## 3. 新发布契约与状态机

新 material source meta 的 `amended` 必填且类型为精确 `bool`；new material manifest item 的同名字段必填，从该 source meta 严格读取，缺失/整数/字符串一律失败关闭。`MaterialManifestItem.from_source_meta` 是唯一 manifest 投影。请求校验拒绝非精确 bool，CLI 缺 `--amended`、batch entry 缺显式标记的既有公开默认仍为 false。成功内容发布、guard 验证后的 prepare 期 identical skip、metadata-only 与 delete 的 `published_amended` 均取已提交或既有 source meta 的同源 typed publication outcome；失败、取消为 `null`，不得声称请求值已发布。`amended` 不进入 `build_material_ids`、source fingerprint 或版本算法。

三域键名是逐表面合同，不跨域重命名存储字段，也不从请求推断已发布值：

| 表面 | 必须出现 | 禁止出现／保留边界 |
| --- | --- | --- |
| material source meta 与 `material_manifest.json` item（内部持久 schema） | 精确 bool `amended`，manifest 只从 source meta 投影 | `requested_amended`、`published_amended`；新 schema 缺 `amended` 失败关闭 |
| material CLI/Service/tool/batch 输入 | 输入参数 `amended`（省略时现有公开默认 false） | 输入不使用 `requested_amended` 或 `published_amended` 代替参数名 |
| material job 请求摘要、`UPLOAD_STARTED`、runtime `upload.started` | 精确 bool `requested_amended` | 裸 `amended`、`published_amended` |
| material pipeline 终态 JSON、typed summary 的 JSON、direct/CLI/tool/job 终态与 LLM-facing 结果 | 精确 bool 或 JSON null 的 `published_amended`，按下表状态约束 | 裸 `amended`、`requested_amended`；direct/CLI 的中文业务详情只从同一 typed summary 格式化 |
| material `list_documents.documents[]` 的 LLM-facing 输出 | 精确 bool `published_amended`，从严格解析的 active source meta `amended` 投影 | 裸 `amended`、`requested_amended`；内部 `_SourceDocumentMeta` 可保留 `amended` 键，但不能直接透给 LLM |
| `list_documents.recommended_documents` | 维持现有 document_id / null 推荐槽位；不新增 amended 字段 | 不把推荐槽位冒充文档详情，也不重复填入标记说明 |
| processed meta 与 processed manifest item | 既有 `amended` 是 preprocess 时复制 source meta 得到的**时点快照**，可与后来的发布值不同 | 不当作当前发布标记真源，不从它投影 read/tool/结果的 `published_amended`；本项不改 processed writer |
| filing 的请求、身份、read 和结果 | 原有 `amended` 语义及键名保持 | 不加入 material 的 `requested_amended`/`published_amended`；不改变 filing read 输出 |

`list_documents.documents` 若同时包含 material 与 filing，按每个 item 的 `source_kind` 投影：material 仅 `published_amended`，filing 仅原 `amended`；`recommended_documents` 只保留 ID / null 槽位，现行推荐基于过滤前的全量 source 文档。当前没有暴露 amended 的 read「详情」输出；内部 `_SourceDocumentMeta` 不等于 LLM-facing 详情，未来若新增详情须另立契约。测试按以上正反名单分别断言持久 schema、请求、started、各终态、`documents` 混合列表及 `recommended_documents` 形状；不设旧键别名或兼容解析。`fins_tools.py` 的 `list_documents` 工具说明应自足说明 material 的 `published_amended` 是当前 active 发布标记、filing 的 `amended` 保留原义，推荐槽位仅给文档 ID；业务解释写在工具定义一次，不在每个 item 重复塞说明。

material 终态闭集增加 `metadata_updated`：`UploadOperationResult.status`、SEC/CN/HK pipeline JSON `status`、`FinsUploadPipelineResult.status`、`FinsUploadResultSummary.status` 均为此精确字符串，`sec_upload_workflow._resolve_upload_status` / `cn_pipeline._resolve_upload_status` 原样透传，归 `FinsUploadTerminalDisposition.COMPLETED`；仅表示同内容标记变化已提交。pipeline JSON 的 `stored_file_count` 为非负整数（拒绝 bool），`ok` 须 >=1，`metadata_updated`、`skipped`、`deleted`、`failed`、`cancelled` 须为 0。`FinsUploadResultSummary` 的 `requested_file_count` 同样为非负整数：`ok`、`metadata_updated`、`skipped` 须 >=1；`ok` 的 stored=requested；其余终态 stored=0，`deleted` 为无文件请求 0，`failed`/`cancelled` 保留请求实际文件数 0 或更多。metadata-only 不生成 original/转换/文件上传事件，不能复用 `ok` 或 `skipped`；material 外原有状态与计数合同不变。

| material 终态 | pipeline JSON `published_amended` | `FinsUploadResultSummary.published_amended` 与 JSON 摘要 | direct/CLI/tool/LLM-facing 结果 |
| --- | --- | --- | --- |
| `ok`（内容发布） | 必填精确 bool，取新发布 meta | 精确 bool | `status=ok`、requested/stored 均为实际 original 数、已发布 bool |
| `metadata_updated` | 必填精确 bool，取新提交 meta | 精确 bool | `status=metadata_updated`、requested>=1、stored=0、已发布 bool |
| `skipped`（prepare 期拟 identical skip，经 O12 guard 验证后报告） | 必填精确 bool，取既有 active meta | 精确 bool | `status=skipped`、requested>=1、stored=0、既有已发布 bool；本请求无 material 业务写入，独立公司阶段仍按 O12 合同 |
| `deleted` | 必填精确 bool，取 tombstone 上最后发布 meta | 精确 bool | `status=deleted`、stored=0、最后发布 bool |
| `failed` / `cancelled` | 必填 JSON `null` | Python `None`，JSON `null` | `status` 与 requested/stored 保持各自既有规则，stored=0；不展示已发布 bool 结论 |

`FinsUploadPipelineResult.from_pipeline_json(..., source_kind=MATERIAL)` 与 summary owner 要校验表中字段存在、精确类型和状态互斥；`published_amended: bool | None` 是 typed 字段，不藏在 extra payload。material 的 `to_json_summary()` 总有 `published_amended` 键（成功 bool，失败/取消 null）；filing pipeline JSON 禁止该键，filing typed summary 只能 `None`，filing JSON/direct/CLI/tool 投影不含该键，以已知 `source_kind` 精确限制可选投影，filing 状态/身份不变。健康首次/重复 delete 均为 `deleted`、requested=stored=0；`skipped` 只表示有文件的相同内容 upsert 无材料写入。job 请求摘要对 material 使用必填 `requested_amended: bool`；filing 请求摘要保留既有裸 `amended`，不套用 material 发布字段。material pipeline 的 `UPLOAD_STARTED` 和 runtime `upload.started` 若产生，必须回显 `requested_amended: bool`，从已校验请求机械传递；filing started 原字段保持。终态不从 started 回显推断发布值。独立的 direct RESULT 仍遵守其现有 completed/failed/cancelled 治理状态，但 material 业务 `status` 与已发布值从同一 summary 投影；若现有 cancelled durable job 不保存 result summary，不为填字段伪造一份，已有 pipeline/direct 取消结果若出现则 `published_amended=null`。

以下是 **material 摘要中本项字段的最小投影片段**；既有 ID、failure、warnings 等字段仍按现有合同提供，pipeline JSON 没有 `requested_file_count`，由 runtime 用请求文件数形成摘要。请求摘要 `{"source_kind":"material","requested_amended":true}`；内容发布 `{"source_kind":"material","status":"ok","requested_file_count":1,"stored_file_count":1,"published_amended":false}`；同内容仅改标记且无 overwrite `{"source_kind":"material","status":"metadata_updated","requested_file_count":1,"stored_file_count":0,"published_amended":true}`；guard 验证后的 prepare 期 identical skip `{"source_kind":"material","status":"skipped","requested_file_count":1,"stored_file_count":0,"published_amended":true}`；删除 `{"source_kind":"material","status":"deleted","requested_file_count":0,"stored_file_count":0,"published_amended":true}`；失败 `{"source_kind":"material","status":"failed","requested_file_count":1,"stored_file_count":0,"published_amended":null}`（另须带 typed `failure`）；取消结果如有 `{"source_kind":"material","status":"cancelled","requested_file_count":1,"stored_file_count":0,"published_amended":null}`。pipeline JSON 中 metadata-only 的对应核心片段为 `{"status":"metadata_updated","stored_file_count":0,"published_amended":true}`。LLM-facing 工具参数 `amended` 仍是输入名、精确 bool、默认 false；共享 schema 必须按 `upload_kind` 自足说明：material 时是本次请求拟发布的修订标记；同内容仅改标记且无 overwrite 只更新元数据、不增加内容版本，带 overwrite 则重做转换和发布但同指纹仍保留内容版本；filing 时沿用既有修订 filing 身份规则。不能笼统描述为文件版本。

material tool 的结果字段说明、tool 返回的可读文本和 job 投给 LLM 的终态上下文必须自足写明：`status` 是本次动作结果；`published_amended` 是已发布材料是否修订的布尔值，`metadata_updated` 表示本次只改变了该标记且未存入文件，`skipped` 表示本次没有改动并报告原有已发布标记，`deleted` 表示材料已删除且该值是删除前最后发布的标记；`failed`/`cancelled` 时该值为 `null`，不能据此断言当前标记或发布成功，`null` 也不代表 false。失败结果的 `failure` 另说明本次失败原因，不能将其当作已发布事实；若要判断旧材料是否仍发布，应重新读取当前材料。最小 LLM-facing 示例保留 `{"status":"skipped","published_amended":true}` 与 `{"status":"deleted","published_amended":true}`，并在示例旁明说两者都**不表示本请求把标记改为 true**。同一说明用于 read 的 `published_amended`（当前 active 发布事实）；read 不把 tombstone 显示成 active。不得只在本计划表注解释或让模型靠字段名、事件 ID 猜测。

下表先经 O14/O15 共享 action/target 准入；仅列准入后的 active upsert。`vN` 是旧内容版本，`A` 是旧发布 amended，`B` 是本次请求 amended；“同指纹”限现有 `identical_skip_safe=true` 且旧指纹有效，异指纹按现有 `_resolve_document_version` 递增。八格明确区分标记与内容：`overwrite` 不进入版本算法，`amended` 也不进入指纹/版本算法。`ok` 的 stored 是实际 original 文件数且 >=1；`metadata_updated`/`skipped` 的 stored=0。各格稳定 ID 不变，成功发布后 manifest 等于 source meta。

| 新旧指纹 | `B` 对 `A` | `overwrite` | owner 决策与终态 | 新标记／版本／转换和发布 |
| --- | --- | --- | --- | --- |
| 同 | 同 | false | prepare 期拟 identical skip；O12 同版 guard 内只读验证后报 `skipped` | A / vN / 零转换、零 material 发布，material meta/manifest/资产不变；独立公司阶段仍按 O12 合同 |
| 同 | 异 | false | **metadata-only publication**；O12 同版 guard 条件提交后报 `metadata_updated` | B / vN / 零 Docling 转换、零 original/派生文件发布；仅更新 amended、updated_at、storage-owned revision 与同批 manifest，内容字段、首次时间及文件字节不变 |
| 同 | 同 | true | 禁止 identical skip；强制 Docling 转换及完整替换，报 `ok` | A / vN / original 与 Docling 产物重新发布，stored=实际 original 数 |
| 同 | 异 | true | 禁止 metadata-only；强制 Docling 转换及完整替换，报 `ok` | B / vN / original 与 Docling 产物重新发布，stored=实际 original 数 |
| 异 | 同 | false | 转换及完整替换，报 `ok` | A / vN+1 / 新 original 与 Docling 产物发布 |
| 异 | 异 | false | 转换及完整替换，报 `ok` | B / vN+1 / 新 original 与 Docling 产物发布 |
| 异 | 同 | true | 强制转换及完整替换，报 `ok` | A / vN+1 / 新 original 与 Docling 产物发布 |
| 异 | 异 | true | 强制转换及完整替换，报 `ok` | B / vN+1 / 新 original 与 Docling 产物发布 |

| 其它状态 + 请求 | owner 决策 | 新标记／版本／资产 |
| --- | --- | --- |
| O14/O15 已准入的不存在目标 + upsert，省略标记或显式 true | 首次内容发布，不 skip | 分别 false / v1、true / v1；写入新内容 |
| 显式 create / update 的目标存在性、overwrite 与 tombstone 组合 | **由已实施的 O14/O15 共享 action/target owner 先裁决**；active create-existing 无 overwrite 在该 owner 前置 typed conflict，不进入 O18 preparation | O18 不定义过渡 skip、`FileExistsError` 或临时动作表 |
| active `(F,vN,A)` + 首次 delete | storage 写 tombstone；上传请求携带的 amended 不覆盖最后发布事实 | A / vN / 原资产保留；`is_deleted=true` |
| tombstone `(F,vN,A)` + 再次 delete | O13 的幂等时间规则适用；终态仍为 `deleted`，不是零文件 `skipped`；O18 不改写 amended | A / vN / 原资产保留 |
| tombstone `(F,vN,A)` + auto/upsert 同指纹恢复，传 B | 不走 active identical skip；按 O14/O15 准入发布恢复并清 tombstone | B / vN / 指纹不变；original/派生文件按既有恢复路径 |
| tombstone `(F,vN,A)` + auto/upsert 异指纹恢复，传 B | 完整内容发布 | B / vN+1 / 新内容 |

删除后的 material 不是 active；read 列表继续按 `is_deleted` 隐藏，source meta/manifest 的 amended 表示最后一次发布材料的标记，不把 delete 请求解释为新版本。恢复请求省略标记明确为 false，即使 tombstone 上为 true；这是新 active 发布事实。显式 update/create 的存在性和 tombstone 合法性只消费 O14/O15 已实施的准入真源。特别是 state plan 第 103 行明定 material tombstone + `create` 且无 overwrite **保持现有 source upsert/storage 拒绝，不作新 typed O14 接受标准**；O18 不将此格视为 active create，也不虚构新公开错误。现行 material fingerprint 路径 `identical_skip_safe=true`，八格不设“不安全 material 指纹”死例外；未来若 fingerprint owner 改变该性质，须先重审八格和版本规则。

## 4. 数据流、接口和实施决策

1. **实施前硬门槛**：O12 已过 plan gate，但仍须实现集成；O12 的 O16/O05 传递依赖须先 accepted+integrated；O14/O15 共用 state plan 已存在但本版尚未双路闭合，须先闭合并实现集成。再核对 O12 同版 storage snapshot、**所有 material mutation batch** 的 source/post-company 双 precondition、skip 的 guard 内只读比较与 O14/O15 action/target 准入的实际 public 签名，逐参数核对并跑 active/missing × create/update 及 overwrite 相关四象限回归。active create-existing 无 overwrite 必须由共享准入在 O18 preparation 前给 typed conflict；material tombstone create 无 overwrite 保持 state plan 指定的现有 storage 拒绝，不推出新 typed O14 结果；缺任一依赖就停 implementation。`FinsUploadMaterialRequest` 在 Fins 请求边界校验 `type(amended) is bool`；CLI、Service、tool、batch plan 不产生第二个默认/推断逻辑。`service_runtime._run_material_upload` 显式传入 US/CN/HK pipeline，再传 material workflow，`prepare_upload` 的 material typed 输入携带 amended；`previous_meta` 只取 admission 同版 snapshot 的业务 meta。保持 filing 函数签名和身份计算不变。
2. O12 的 admission/workflow 持有同版 `observed_state`，其中完整 source business meta 与 opaque revision 是**分开的 typed 值**；公司阶段先按 O12 完成独立合法发布，`stage` 时用 `CompanyMetaCommitOutcome.company_meta`，`keep/skip` 时用 admission.company_meta 作为材料阶段期望公司状态。metadata-only 与 identical skip 都走这一阶段，后续材料冲突不回滚已合法提交的公司事实。`DoclingUploadService.prepare_upload` 只在 O14/O15 允许的 material upsert 上消费传入的 business `previous_meta` 与本次 amended；active、可安全同指纹、无 overwrite、标记相同则产生**拟 skip**结果，不能在 guard 前对外报告。标记不同且无 overwrite 构造独立 `_PreparedMaterialMetaMutation`，只携稳定身份、业务目标 amended 与构造 staged meta 必需的业务字段；不携、也不从 `previous_meta` 或 raw JSON 推断 opaque revision。它不调用 Docling、不触碰 blob。overwrite=true 无论标记是否变化都走现有完整转换/发布路径；相同指纹恢复也走既有 upsert，版本由 `_resolve_document_version` 决定。不要把 amended 塞进 fingerprint 迫使版本递增。
3. 持有 admission snapshot 与公司阶段 outcome 的 material workflow 是 O12 precondition **注册 owner**。拟 skip 无 mutation 时，workflow 将 admission 的 `expected_source_state`（status、完整业务 meta、独立 opaque revision）及 post-company `expected_company_meta` 交给 O12 同一 storage publication guard **只读比较**；两者都匹配后才以原有 source meta 形成 `skipped/published_amended`，不建空物理 batch、不重发布 ticker tree；任一漂移返回 O12 typed stale/conflict，不报陈旧 skip。**每个 material mutation batch**，包括 metadata-only、delete 与常规/overwrite 内容发布，在材料 batch 同时注册上述两项 typed precondition，再由相应 material publication/`commit_prepared_upload_batch` 使用既有取消、rollback 与 commit 生命周期；metadata-only staging 精确替换 source meta，storage 同批投影 manifest。storage 在提交 guard 内、首次 backup/swap 前比较已发布 source 全值加 revision 与 post-company meta，匹配才提升 staged tree。条件不成立返回 O12 storage owner 的 typed stale/conflict 并丢弃 staging，不能把 A 的旧 `previous_meta` 静默覆盖 B 的发布，也不在 O18 自行重判为 skip。O18 准备期不再分别调用公司/source 普通读取，也不为 revision 重读；只有 O12 storage guard 为权威比较做一次受锁的内部重读。实施前按 O12 **实际** public API 核对三类 mutation 注册形状与 skip 只读 guard；若不能表达 expected active/fingerprint/amended、独立 revision、post-company meta 或 skip 条件，停 implementation 并回 plan review 裁决最小 storage 扩展；不得在 O18 复制 commit hook、靠普通 `get_source_meta` 猜私有 revision，或用异常字符串、时间戳、CLI 重试推断。O33 的 guard 外一般并发重试与底层故障诊断另案处理。
4. `_build_upsert_meta` 对 material 写本次 amended；storage `_prepare_complete_source_meta` 对 material 严格校验必填 bool。`MaterialManifestItem` 增加 `amended: bool` 并严格从 source meta 投影；storage integrity 的 canonical manifest 比较随该类型自然更新。`replace_source_meta` 的同批写入应验证 source meta 与 manifest/资产一致，不能用旧 manifest 单独 patch。不要改 filing manifest。
5. 用上传服务的 typed publication outcome/已发布 source meta 形成 material `UploadOperationResult` 的 `published_amended: bool | None`，SEC/CN/HK completed result、pipeline JSON、direct stream、ingestion summary 机械传递，遵守 §3 的终态表与 source-kind 限制。`UPLOAD_STARTED`、runtime `upload.started` 与 job 请求摘要的 material 标记只叫 `requested_amended`；failed/cancelled 的 `published_amended` 固定 null，不从请求冒充发布事实。read runtime 的内部 material typed meta 严格读取 source meta `amended`，只在 `list_documents.documents[]` 的 material 项投影为 `published_amended`；`recommended_documents` 保持 ID/null 槽位，混合 `documents` 按 item `source_kind` 分支，filing read 键名与规则不改。`dayu/fins/tools/upload_tools.py` 的共享 LLM-facing schema 按 upload kind 说明请求语义；`dayu/fins/tools/fins_tools.py` 的 `list_documents` 定义一次说明 material 当前 active 发布标记与 filing 原义；tool/Job 结果与 read 的 LLM-facing 说明同时包含 §3 的 skip/delete/failure 解释。material direct `RESULT` 对 `ok`、`metadata_updated`、`skipped`、`deleted` 用同一 `FinsUploadResultSummary` 增业务详情“已发布材料是否修订”=`true`/`false`，并按状态说明这是新发布、原有发布或删除前最后发布事实；CLI 沿用 direct 渲染；failed/cancelled 不输出该业务详情。tool/job 的 material 结果摘要用 `published_amended` 的 bool/null；这些投影不得从请求、事件字符串或 processed 快照重算。

## 5. 实施白名单与切片

仅获后续实施 gate 授权时可修改下列路径。若核对调用图发现必需路径不在白名单，先修订 plan 并 review，不顺手扩大范围。

- 生产：`dayu/fins/ingestion_runtime.py`、`dayu/fins/service_runtime.py`、`dayu/fins/pipelines/sec_pipeline.py`、`dayu/fins/pipelines/sec_upload_workflow.py`、`dayu/fins/pipelines/cn_pipeline.py`、`dayu/fins/pipelines/docling_upload_service.py`、`dayu/fins/domain/document_models.py`、`dayu/fins/storage/source_meta_contract.py`、`dayu/fins/storage/_fs_source_document_core.py`、`dayu/fins/storage/_fs_source_integrity.py`、`dayu/fins/tools/read_runtime.py`、`dayu/fins/tools/upload_tools.py`；条件性加入 read tool LLM-facing 定义真 owner `dayu/fins/tools/fins_tools.py`，仅改 `list_documents` 说明。O12 同版 guard/仓储 public contract 是待集成的前置依赖，不列为 O18 自建接口；严格 material schema 若需触及仓储文件，只改上述 owner 路径，不造兼容 facade。`dayu/fins/storage/_fs_processed_core.py` 不在 O18 白名单，本项不改 processed writer。
- 测试：`tests/fins/test_docling_upload_service.py`、`tests/fins/test_docling_upload_service_integration.py`、`tests/fins/test_sec_pipeline_upload_material_stream.py`、`tests/fins/test_cn_pipeline.py`、`tests/fins/test_fins_service_runtime.py`、`tests/fins/test_fins_ingestion_runtime.py`、`tests/fins/test_fins_ingestion_tools.py`（upload tool schema 与结果摘要）、`tests/fins/test_fins_direct_stream.py`（direct 终态详情）、`tests/service/test_fins_direct.py`（Service 保真传递）、`tests/fins/test_upload_batch.py`、`tests/fins/test_fins_storage_provider.py`、`tests/fins/test_fins_storage_atomicity.py`、`tests/fins/test_fins_read_runtime.py`（`documents`/`recommended_documents` 实际结构）、`tests/tools/test_combined_tools_acceptance.py`（现有 read tool definition 装配测试，断言 `list_documents` LLM-facing 说明）、`tests/cli/test_fins_commands.py`。混合列表内容由 read runtime owner 测，tool 定义说明由 definition 装配测试测；若实施时真实测试 owner 变化，先修订 plan。
- README（仅触发且职责相符时）：`dayu/fins/README.md`、`tests/README.md`、根 `README.md`；若实施改变跨包边界，按已读更新约束评估 `dayu/README.md` 并先修订白名单。本轮计划修订不写 README 正文。

**Slice 1：已发布事实与同内容状态转换。** 在 O12/O14/O15 已集成后，修改共同 preparation、typed metadata mutation、source meta/manifest 严格 schema、同批持久化及 read contract。完成信号：owner 测试覆盖八格以及首发、delete/恢复；metadata-only 零转换/文件发布且无版本伪增，overwrite=true 同指纹仍真实转换/发布而版本保持；metadata-only/delete/content 各材料 mutation batch 均消费 O12 source/post-company 双 guard，拟 skip 消费只读 guard，异常/取消回滚与 manifest 同源。该 slice 是可独立验证的行为增量，不按文件机械拆分。

**Slice 2：所有入口传播和真实输出。** 修改 material 请求/市场接口、tool schema 与 `metadata_updated` 闭集/完成结果投影，并在入口测试中覆盖 CLI、Service、tool、batch plan、US/CN/HK。完成信号：相同请求跨入口产生相同 owner 事实，`ok`、`metadata_updated`、`skipped`、`deleted`、`failed`、`cancelled` 的字段类型、计数与投影符合 §3；跨命令 read 与 source meta/manifest 一致。Slice 1 的 owner contract 是前置条件；两 slice 可在一次实施 pass 中合并，若 gate 成本高于分开验证收益，以一次 pass 执行并保留两个行为验收组。

## 6. 验证、真实 CLI 对照与文档

在实现 gate 激活 `.venv` 后执行受影响测试，至少：

```bash
source .venv/bin/activate
python -m pytest tests/fins/test_docling_upload_service.py tests/fins/test_docling_upload_service_integration.py tests/fins/test_sec_pipeline_upload_material_stream.py tests/fins/test_cn_pipeline.py tests/fins/test_fins_service_runtime.py tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_ingestion_tools.py tests/fins/test_fins_direct_stream.py tests/service/test_fins_direct.py tests/fins/test_upload_batch.py tests/fins/test_fins_storage_provider.py tests/fins/test_fins_storage_atomicity.py tests/fins/test_fins_read_runtime.py tests/tools/test_combined_tools_acceptance.py tests/cli/test_fins_commands.py -q
python -m pyright dayu/ tests/ utils/
```

owner 测试必须断言精确 bool、source meta/manifest 同值、ID 与 fingerprint、版本、文件字节、revision/updated_at；八格逐格断言状态、Docling 调用数、original/派生文件实际写入与 stored 计数，尤其无 overwrite 的同指纹异标记零转换/发布，以及 overwrite=true 的两格同指纹真实转换/发布但保版。用真实仓储验证 metadata-only 同 batch 原子性、取消/写入失败 rollback。并做四组**真实仓储交错**：① A 持 O12 同版 admission，完成合法公司阶段并 prepare metadata-only、注册 expected source 与 post-company meta；B 针对同一 material 成功 commit 切换标记；A 随后 commit，必须由 storage typed stale 拒绝，B 的 source meta/manifest/original/派生资产与版本不回退，A 不得报告 `metadata_updated`。② A prepare 时拟 identical skip、B 在 A 报告前成功 toggle 提交；A 经 O12 guard 只读比较 source 与 post-company meta，必须 typed stale 拒绝，不得返回陈旧 `skipped/published_amended`，B 的业务树不变。③ A prepare delete 后，B 对同一 source 提交内容/标记变更，A 的 delete batch 在 source/post-company 双 guard 比较处 typed stale 拒绝；不能把 B 的新发布 tombstone 掉。④ A prepare 常规内容发布（含 overwrite 分支的代表格）后，B 提交同一 source 的标记或内容变化，A 的内容 batch 在双 guard 比较处 typed stale 拒绝，不能覆盖 B 的 source meta/manifest/资产。对①③④分别再令 post-company meta 在 A 公司阶段后漂移，断言同一双 guard 拒绝；每组均以可控 barrier 控制 A prepare→B commit→A guard/commit，失败后 B 的业务树不回退、先前合法公司阶段可保留；单线程 stale 测不能替代。skip ②仅走只读 guard，不建材料 mutation batch。入口测试按 §3 正反名单逐面检查存储、job 请求、started、pipeline/summary/direct/CLI/tool、混合 `documents` 列表及 `recommended_documents` ID/null 形状的键名、bool/null、状态计数和 completed 映射；`tests/tools/test_combined_tools_acceptance.py` 核对 `list_documents` 的 LLM-facing 说明自足区分 material 当前发布值与 filing 原义，filing 键名/身份保持，material read 缺标记失败关闭。`tests/fins/test_fins_ingestion_tools.py` 除 schema 请求语义，还核对 LLM-facing 结果文案自足解释 `skipped/deleted/failed/cancelled`，并对实际结构化结果断言，不只测文字。首次与健康重复 delete 均断言 `deleted`、requested=stored=0、最后发布 amended 保留；不把 O13 时间幂等改作本项验收。新 schema 起库测试只使用 fresh workspace；不加旧库兼容读取或旧 schema fixture。单个新增/修改生产文件均用 `coverage run -m pytest <上述受影响集合>` 后 `coverage report --include='<逐一列出本次修改的生产文件>'` 核对 >=80%；不以合并总覆盖率代替单文件结果。`dayu/render/`、`utils/` 本项不修改。

真实 CLI canary 在**新的隔离临时 workspace**固定 ticker/form/name、输入文件与 SHA-256；每步显式写 `--action`，并在 O14/O15 集成后按其实际合法 argv 核对，不依赖 CLI 默认动作。以下 `auto` 仅用于 O14/O15 允许的目标状态；若其实际共享准入不允许某步，implementation 停下修订配方并 review，不把 create-existing 冲突改成 skip：

| 步骤 | CLI action 与输入 | 期望发布事实 |
| --- | --- | --- |
| 1 | `--action auto`，字节 X，不带 `--amended`、不带 `--overwrite` | 首发 `ok`，false/v1 |
| 2 | `--action auto`，同字节 X，带 `--amended`、不带 `--overwrite` | `metadata_updated`，true/v1，stored=0；零 Docling 转换/文件发布 |
| 3 | `--action auto`，同字节 X，带 `--amended`、不带 `--overwrite` | guard 验证后 `skipped`，true/v1，业务树不变 |
| 4 | `--action update`，同字节 X，不带 `--amended`、不带 `--overwrite` | `metadata_updated`，false/v1，stored=0 |
| 5 | `--action update --overwrite`，同字节 X，带 `--amended` | `ok`，true/v1，Docling 重新转换并发布 original/派生文件，stored=实际 original 数；与步骤 2 对照 |
| 6 | `--action update --overwrite`，同字节 X，带 `--amended` | `ok`，true/v1，再次转换/发布；覆盖同标记 overwrite 格 |
| 7 | `--action update`，新字节 Y，不带 `--amended`、不带 `--overwrite` | `ok`，false/v2，新内容发布 |
| 8 | `--action delete`，无输入文件 | `deleted`，最后发布 false/v2 |
| 9 | `--action auto`，字节 Y，带 `--amended`、不带 `--overwrite` | 恢复 `ok`，true/v2，不走 active skip |
| 10 | `--action update`，新字节 Z，带 `--amended`、不带 `--overwrite` | `ok`，true/v3 |
| 11 | 新 identity，`--action auto`，字节 X，带 `--amended`、不带 `--overwrite` | 首发 `ok`，true/v1 |

另用独立 identity 以固定 `--action auto` 首发 X false/v1，再以 `--action update` 新字节 Y 带 `--amended` 得 true/v2，复跑冻结 A16/A17 形态但不把冻结观察冒充本次实测。每步保存 exact argv、exit、stdout/stderr、输入 SHA-256、before/after tree diff、Docling 转换调用证据、original 与 Docling 文件 hash、source meta、manifest、版本/计数及**跨命令** `list_documents.documents`/`recommended_documents` 读回；步骤 2 与 5 必须直接对照转换/发布和 `documents` 项的 `published_amended`。US/CN/HK 入口至少各有同内容 toggle、同内容 overwrite 与新内容对照，若真实市场依赖不可离线满足则清楚标成未覆盖，不能用单测代替真实 CLI 证据。新补跑 lineage 与冻结 A16/A17 分开。

README 判定：`dayu/fins/README.md` 需记录已实现后的稳定 amended 发布/skip/manifest 契约；根 `README.md` 若用户可见 `--amended`、result 或排障说明变化，按其用户手册边界更新；`tests/README.md` 只有新增测试层级/稳定运行方式时更新，不能机械列文件。修改前再次读各文件的 `Agent更新约束`；本轮只写计划，不改 README。

## 7. 与 O05/O12/O13/O14/O15/O16/O33 的集成边界

- O12 的 accepted plan checkpoint SHA-256 `48e0598bd8c949e7257b6fd6c6a03adbdca31b0def2d680d4b0cea93f7ed5e60` 已过 plan gate，**产品未实施/集成**。其同版 company/source business meta + 独立 opaque revision snapshot、**metadata-only/delete/content 每个材料 mutation batch** 的 expected source/post-company 双 precondition、material skip 的 guard 内只读比较，均是 O18 implementation 硬前提；O18 消费实际 public contract，不建立第二套 guard。O12 自身须待 O16/O05 accepted+integrated；O18 完成报告逐项列 O16/O05/O12 实际集成版本与 owner 复核。若 O12 最终接口不能表达三类材料 batch 或 skip 条件，回 plan review 裁决最小扩展。
- O14/O15 共用 state plan SHA-256 `1fe2f5462a0d7a7bdb54edda3985965713a2e87890f5c8dba9b9c823e98778b6` 已存在，**本版计划 gate 未双路闭合、产品未实施/集成**，闭合并集成才可开始 O18 implementation。active create-existing 无 overwrite 必须在共享准入处 typed conflict，不到 O18 preparation；实施前核对其真源和四象限回归。state plan 第 103 行的 material tombstone create 无 overwrite 仍保持现有 storage 拒绝、不作新 typed O14 标准；O18 不设计过渡行为。
- O13 拥有重复 tombstone 的幂等时间规则。本项保留 `amended`，不借机改变 `deleted_at`、`updated_at`；健康首次/重复 delete 终态均为 `deleted`，不是 `skipped`，合流时核对最后发布标记与恢复。
- O33 拥有同一 identity 并发 auto 的重试策略与 guard 外失败定位。O12 guard 同时保护本项 metadata-only 条件发布和 prepare 期拟 identical skip 的报告前 source/company 同版验证；A 拟 skip、B toggle 提交、A 报告的 stale 窗口已由 O12 关闭，不能再归 O33 或返回陈旧值。其余 success+skip 竞争策略、不同内容冲突及 L06 底层异常诊断仍由 O33 独立处理，不重建第二套 guard。

## 8. 风险、开放点与完成报告

当前最大风险是 preparation snapshot 与实际发布/skip 报告之间状态变化；当前 `replace_source_meta` 仅精确替换，尚不能替代 O12 同版 guard。O16/O05/O12 未按依赖链完成集成、O14/O15 计划 gate 未闭合或产品未集成，或真实交错不能证明 A 的 metadata-only/delete/content stale batch 与拟 skip stale 报告均 typed 拒绝、B 的状态保持时，O18 implementation 停止并回到相应 owner/plan review，不能降低为 best-effort。旧数据缺 amended 时被读侧默认 false 掩盖，本项采用全新 schema 起库并 fail closed，不承诺旧库读取。read tool 说明若需要 `fins_tools.py`/`read_runtime.py` 之外的新 owner，先列实际调用链并停下相关修订，回 plan review 扩白名单，不在结果 item 或 adapter 加说明补偿。

独立审计风险 `fins-material-processed-amended-projection`：`_build_processed_meta` 复制 preprocess 时的 source meta，`_fs_processed_core` 将该值写入 processed manifest；metadata-only 后 processed 中的 `amended` 可仍为旧值。其语义是 preprocess 时点快照，不是当前发布事实；当前 `list_documents` 的 amended 取 source meta，processed meta 仅供财务能力标志。O18 不改 processed writer，不把 processed 的宽松 `bool(...)` 改成发布规则；该 WU 另审时间语义、是否需要失效/重处理和消费者契约。若实施核查发现 processed meta/manifest 或 `DocumentSummary.amended` 的实际消费者把此快照当作当前发布值，**停止 O18 相关实施**，在 artifact 列出从 processed writer 到消费者/LLM-facing 结论的直接调用链，交 processed/source 对应 owner 修复后重审；不得由 read/tool 下游重算或加兼容分支。O13 首次/健康重复 delete 均为 `deleted`，不与有文件 `skipped` 计数合同冲突。以上风险不引入 O18 外的产品修改。

实施完成报告必须列：修改文件及各 owner 的事实、逐状态机实际结果、真实 CLI 原始证据绝对路径与冻结证据区分、逐文件 coverage 百分比、受影响 pytest 和 pyright 结果、README 决定、O16/O05→O12 与 O14/O15 及 O13/O33 的集成版本/owner 重核和未覆盖项、processed 快照审计风险、残余风险及下一 gate。当前状态只完成候选 plan 修订；没有实施测试、pyright 或新 CLI canary，不能将本计划中的预期说成验证通过。候选 plan 完成后停在 Kimi/MiMo 双路 re-review 前。
