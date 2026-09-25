# 美的 000333 2021Q1：旧完整缓存与公开 repair 入口诊断

## 1. 结论与范围

**旧完整缓存确实可能阻碍不同 announcementId 的新候选登记。** 条件是：巨潮新候选已经通过 selection 和日期窗口，且与旧文档具有相同 ticker、财年、财期及 amended 标记；默认 `overwrite=False`。这时它们映射到同一个 document_id，完整性检查通过便直接 skip，不比较新旧 source_id 或 remote_fingerprint，也不写入新候选的来源信息。

这证明的是本地代码的确定性行为。本轮未查询远端，未读取投资目录中的财报存储，也未执行任何下载、repair 或覆盖命令。

收口时用户补充的外部核查证据：已通过隔离公开 CLI 下载并冻结 **9 页正文 source_id=1209870319**；MiMo Raw 已确认三条同日公告，**中文全文 source_id=1209870320**。这些事实由用户提供，本轮未重新提取或独立核验其 Raw、PDF 和缓存，不能据此推断投资目录的当前状态。方案记录位于 [实施计划](../plans/midea-q1-full-report.md)：按 amended、日期、非正文优先、ID/URL 稳定平手排序；**不修改默认 skip，旧缓存通过 overwrite 修复**。本报告据此收口，不扩大调查。

需要分别诊断两道关口：

1. **候选是否选对**：selection 在访问文档缓存之前完成；缓存不参与巨潮同财期公告的选优。因此缓存不能解释上游为什么选错，但可使后续正确候选无法替换旧内容。
2. **选中候选是否登记**：CN 身份按财期槽位分配，完整缓存无来源比较便 skip，旧内容继续存在。现有测试明确覆盖了 source_id 改变仍 skip，见第 6 节。

“缓存完整”是本地文件、元数据及 manifest 的一致性事实，不是“报告全文正确、来源最新”的业务承诺。修复动机成立，但不能只改 selection 后便假定旧工作区会自动更新，也不能把强制覆盖当作上游选优修复。

## 2. 来源、原文证据与审核底稿约定

- 核查日期：2026-09-15，Asia/Shanghai。报告版本：v1。业务定位：000333／2021Q1；无金额、数量计算，单位不适用。
- 代码来源：本地仓库 `/Users/leo/workspace/dayu-agent-r`，HEAD `d30a07c870e3602638d8943ab71a5eaa3e01fc9b`；首次 `git status --short` 为空。收口时另有用户建立的 `docs/plans/`，本轮未修改。
- 先读根目录 `AGENTS.md`。本轮按用户已确认目标执行只读诊断，不重新启动 Gateflow，不改生产代码、测试、README，不提交。
- 查询参数及可复现方式：`git rev-parse HEAD`、`git status --short`；`rg -n` 查指定模块的 `source_id`、`announcementId`、`repair`、`overwrite`、`rebuild`、`supersed`、测试函数；`nl -ba <文件>` 按下文行号读取。CLI 位于 `dayu/cli/`，不是 `dayu/ui/cli/`。
- 四层留痕：原始来源为上述 Git 版本的源码和测试；本节保留关键原文，下面各节为调用链及审核底稿，第 1、7 节为从底稿生成的结论。受“只允许写本文件”约束，不另建 `data/raw`、脚本或测试日志；源码可由 Git 版本及行号复核。本轮无财报逐笔提取，不能提供真实公告 Raw 或将合成例子冒充远端证据。

关键原文摘录（不改原源码；详见后文定位）：

```python
# cn_report_selection.py:456
source_id=announcement.announcement_id,
# cn_form_utils.py:190
seed = f"{normalized_ticker}|{normalized_form}|{fiscal_year}|{normalized_period}|{int(amended)}"
# cn_download_identity.py:28-29
if candidate.provider != "hkexnews":
    return allocated
# cn_download_filing_workflow.py:188
if phase_a_integrity.status is SourceIntegrityStatus.COMPLETE and not overwrite:
# cn_download_filing_workflow.py:785-787
if overwrite or previous_meta is None:
    return None
return previous_meta
```

审核方法：逐一勾稽公告 ID → candidate.source_id → document_id → skip → source commit → repository → manifest，区分 source_id、文档身份、内容版本与 storage revision；对照真实测试断言，不以测试名称代替实现证据。无执行测试或 pyright：本轮无代码修改，且测试会生成临时工作区等文件，不符合唯一写入路径限制。以下“覆盖”均表示已阅读测试代码，不表示本轮运行通过。

## 3. 确切调用链：发现、选择、身份与 skip

### 3.1 原公告到候选

| 调用位置 | 已核实行为 |
| --- | --- |
| `dayu/fins/downloaders/cninfo_downloader.py:825-840` | 将 provider `announcementId` 归一为 `CninfoRawAnnouncement.announcement_id`，保留标题、披露日期、来源 URL；要求 PDF 及必要字段非空。 |
| 同文件 `:280-295` | 按 category 和查询日期取公告，构造 `raw_by_period`，调用 `select_cninfo_report_candidates`。 |
| `dayu/fins/pipelines/cn_report_selection.py:259-283` | 排除标题、推断财年；按 `(period, fiscal_year)` 分组，每组只选一个 best；只对 best 读取 HEAD 并构造 candidate。 |
| 同文件 `:41-80,343-363,409-429` | 排除“摘要”等及财报公告类标题；选优 key 只有“是否修订”及 `announcement_date`。无全文优先权重、无 PDF 大小比较、无 announcementId 排序。等 key 时 `max` 保留输入中先出现项。不能把此规则直接归因为真实美的响应次序。 |
| 同文件 `:454-466` | `announcement_id → candidate.source_id`；保存 title、filing_date、amended、HEAD 元数据。amended 由标题中的更正／修订／补充等标记推断。 |

候选的 HEAD 元数据在选优之后读取，因此不能参与当前 best 的选择；含“正文”而不含 blocklist 词的标题并无专门排除规则。对同日同修订标记的“正文／全文”碰撞，只能确认现有规则可能依赖输入顺序，不能确认真实公告满足这些条件。

### 3.2 workflow 到身份 owner

`CnPipeline.download_stream`（`dayu/fins/pipelines/cn_pipeline.py:731-745`）
→ `run_cn_download_stream_impl`
→ discovery `list_report_candidates`（`cn_download_workflow.py:213-217`）
→ `_select_candidates_for_a4`（`:219-223,512-543`）
→ `_candidate_document_id`（`:224-225,831-850`）
→ `resolve_cn_download_ids`（`cn_download_identity.py:11-29`）
→ `build_cn_filing_ids`（`cn_form_utils.py:155-194`）。

身份种子为 `ticker|form|year|period|int(amended)`，取 SHA-1 后形成内部 `cn_<digest>`、外部 `fil_cn_<digest>`。**provider、source_id、URL、标题、披露日期及 HEAD 指纹均不在 CN 分配种子内。**

对归一化 ticker 为 `000333` 的 2021Q1 非修订候选，种子为 `000333|Q1|2021|Q1|0`；此处仅展示代码公式，不声称实际缓存 ID 已被读取。

| 同财期候选关系 | 当前 CN 身份行为 |
| --- | --- |
| announcementId 不同，amended 相同 | 同一个 document_id，不会自然登记为两份独立文档。 |
| announcementId 不同，amended 不同 | 种子不同，得到不同 document_id；新 ID 缺失时可新增，但旧 ID 不会因此自动退役。 |
| 两份不同修订公告，均 amended=True | 仍落在同一个修订槽位。 |
| 同一公告 ID 的财期或 amended 被重新推断 | CN 没有按 source_id 回查旧身份的绑定逻辑，分配结果可变化。 |

`cn_download_identity.py:30-53` 的 provider/source_id 既有绑定、重复身份拒绝及财期改变冲突处理**仅适用于 hkexnews**。不能根据模块概览或函数 docstring 将其泛化为巨潮行为。

日期窗口过滤在 `cn_download_workflow.py:533-543`；无显式 start 时还有默认财年限制（`:546-568`）。以当前时间回查 2021Q1 应提供适当历史披露日期范围，不能只写 `--forms Q1`；日期是 filing 日期，不是季度结束日。

### 3.3 完整缓存如何跳过

1. `cn_download_workflow.py:227-255`：按选中 document_id 做整个 ticker 的完整性 preflight；没有 repair target 时先发布公司元数据。然后 `:257-292` 对每个候选发 `FILING_STARTED` 并调用 `run_cn_download_single_filing_stream`。因此“source 无写入”不等于整个运行绝对无副作用。
2. `cn_download_filing_workflow.py:163-187`：再次解析同一身份，分类 source integrity，读取旧 meta，计算新 remote_fingerprint。
3. `:188-229`：若 COMPLETE 且非 overwrite，CN 直接输出 `skipped / integrity_complete` 并返回。`:190-213` 的财期不一致保护只用于 HK。**这里没有比较 source_id、source_url、remote_fingerprint、download_version 或新 PDF 内容。**
4. PDF 下载在 `:245-252`，晚于 skip，因此旧完整缓存时不会下载新 PDF，也不会转换或进入 source upsert。此前 discovery、公告请求和 best 的 HEAD 仍可能已经发生；“跳过远端传输”不能解读为零远端请求。
5. `build_remote_fingerprint`（`cn_download_source_upsert.py:81-102`）确实包含 provider、source_id、URL、长度、etag、last_modified，但**计算了指纹不代表将它用作 skip 条件**。
6. `storage/_fs_source_integrity.py:561-600` 从本地角色声明、文件物理检查等事实派生 COMPLETE；它没有输入新 candidate。预检再检查 ticker 聚合状态。不能让 storage 凭物理完整性推断“选对了完整报告”。

另有 Phase B 防并发陈旧写入：`cn_download_filing_workflow.py:593-614` 在 batch 内再次检查；revision 改变则回滚重试，最新 COMPLETE 且非 overwrite 仍 skip。`source_integrity.py:279-287` 的 publication identity 比较最终是同目标 revision 比较，**不是 announcementId 比较**。

## 4. 新内容登记、版本与 supersede

满足未命中 COMPLETE skip、可安全继续、下载和转换成功的条件后：

`run_cn_download_single_filing_stream` 下载 PDF（`:245-287`）、转换或复用 Docling（`:303-338`）
→ `_commit_cn_filing_assets_batch`（`:532`）
→ 开 batch、校验当前 revision（`:593-614`）
→ 旧目标存在则 `reset_source_document`（`:621-627`）
→ `blob_repository.store_file` 写 PDF、Docling（`:645-666`）
→ `commit_cn_filing_source_document(... source_meta_exists=False)`（`:685-701`）
→ `source_repository.create_source_document`（`cn_download_source_upsert.py:192-213`）
→ `FsSourceDocumentRepository.create_source_document` → core `create_filing`（`storage/fs_source_document_repository.py:323-351`）
→ `_upsert_source_document`（`storage/_fs_source_document_core.py:267-268,1732-1802`）
→ 写 meta、upsert filing manifest
→ 同 batch 标记 processed 重处理（`cn_download_source_upsert.py:214-226`）
→ caller `commit_batch`（`cn_download_filing_workflow.py:708-718`）。

虽然 upsert helper 支持 update/create，**这条下载成功路径在 reset 后明确传 False，实际走 create**，不能描述成直接调用 update 覆盖。

- 登记字段：`cn_download_source_upsert.py:187-191,242-272` 写新 `source_id/source_url/source_title`、财期、amended、`ingest_complete=True`、`primary_document`、内容及远端指纹等。`download_version` 为管线常量，与公告修订次数无关。
- 内容版本 helper：`:326-337` 在有 previous_meta 时按 source_fingerprint 决定保留版本或递增；fingerprint 来自 PDF 与 Docling 字节（`:105-121`）。仅公告 ID 变化而内容相同，不会由该 helper 自动加版。
- **overwrite 特例必须说明**：`cn_download_filing_workflow.py:183-186,767-787` 在 overwrite=True 时将 previous_completed_meta 置空。故成功覆盖从 `document_version=v1` 起算，first_ingested_at/created_at 也不能依此 helper 保留旧值（upsert `:259-270,291-296`）。不是“旧 v1 自动升级为 v2”。已有 processed 时会标记需重处理，即使内容未变（`:350-357` 的 previous_meta=None 分支）。
- 非 overwrite 的可修复损坏路径可传入旧 meta，按内容指纹保留或递增版本。不同 amended 的新 document_id 则从 v1 登记。
- **本调用链没有业务 supersede**：同 ID 是 staged reset 后重建；不同 ID 是新增。reset 删除目标 source 目录并移除对应 manifest 条目（`storage/_fs_source_document_core.py:1327-1341,1363-1387`）；upsert 只登记本请求文档（`:1796-1802`）。没有向旧文档写 superseded_by、没有新旧文档关联，也没有按财期使另一 ID 退役。不能把 storage 事务回滚保障当成业务历史版本留存。
- 成功登记不等于 processed 已重算：这里只设 reprocess_required；新来源需要后续预处理才能更新消费产物。

## 5. 公开 CLI repair 的作用与限制

公开命令注册见 `dayu/cli/arg_parsing.py:235-244,869-900`：没有独立 `repair` 子命令或 download `--repair` 参数；相关入口是以下三种行为。

| 入口 | 作用 | 对本问题的限制 |
| --- | --- | --- |
| 普通 `dayu-cli download` | 对唯一、已选中且可安全修复的损坏 source 自动重新获取并修复；无需 overwrite。 | COMPLETE 旧来源不会被视为损坏；不能纠正候选选优。 |
| `dayu-cli download --overwrite` | 对当前 discovery 选中的候选跳过完整缓存复用，重新下载、转换并在同 ID 重建，或向新 ID 登记。 | 仍经过相同 selection；没有 announcementId/URL 定向参数。若上游仍选错，覆盖也会取错。存在第 4 节版本及审计字段重新起算的限制。 |
| `dayu-cli download --rebuild` | 仅从本地 source meta 和文件条目重建下载元数据及 manifest。 | 不访问远端，不调用 Docling，不发现漏选新公告，不替换错误 PDF；不可与 overwrite 同用。 |

公开调用链：`fins.py:_prevalidate_download_request`（`:608-632`）→ typed request；`_download_stream`（`:587-605`）→ `FinsDirectCommandService.download`（`dayu/service/fins_direct.py:163-186`）→ runtime download（`dayu/fins/ingestion_runtime.py:3572-3610`）→ adapter request 保留 overwrite/rebuild（`:5294-5312`）→ CN adapter（`cn_pipeline.py:1335-1370`）→ `CnPipeline.download_stream`（`:731-745`）→ 上述 workflow。mutation mode 冲突由 `download_contract.py:61-83` 校验，不是展示层补救。

普通下载 repair gate：`source_integrity.py:310-325` 拒绝 UNSAFE、多个 repair target、未选中 target 或被拒 target；`cn_download_workflow.py:232-255,332-355` 将唯一目标排到最前，成功后再确认整树 clean、发布公司信息。旧完整 source 不构成 repair target；不完整且不在本次窗口的其它 source 则可能阻断运行。

本地 rebuild 在 `cn_download_workflow.py:118-154` 提前分流返回，未进入 discovery；`cn_download_rebuild.py:82-100` 枚举已有文档，`:153-168` 按来源方式、删除状态、财期、filing_date 筛选；`:209-241` 对缺 PDF/Docling/主文件声明返回失败；`:243-278` 写本地 update，不能生成新 announcementId。

仅作未来操作说明，**本轮未执行**：

```sh
dayu-cli download --ticker 000333 --forms Q1 --start 2021-01-01 --end 2021-12-31 --overwrite
```

这个示例只是显式历史披露窗口，不代表真实公告必在该范围，不是对远端候选的验证；执行前仍应以实际公告证据确认范围和选优规则。仅重建元数据则将 `--overwrite` 换成 `--rebuild`，但后者不能完成“换成完整报告”这一目标。

## 6. 测试证据与最小回归增量

| 已阅读测试 | 实际断言及缺口 |
| --- | --- |
| `tests/fins/test_cn_report_selection.py:267-330` | 排除摘要、英文；跨财年保留、同年修订优先。未覆盖 2021Q1 同日“正文／完整报告”输入顺序交换。 |
| `tests/fins/test_cn_download_workflow.py:1816-1857` | 首次下载后，把 candidate 改为 `source_id=A2, etag=v2`，断言 skipped=1、零新 PDF 传输、没有 source mutation。这已经固化“新公告也 skip”的当前策略，不必再新增完全相同测试。 |
| 同文件 `:3601-3626` | 名称说 uses_remote_fingerprint，实际上只做同候选第二次下载并断言 skip，不能证明指纹参与条件；其名称/说明与实际 skip owner 不符。 |
| 同文件 `:1758-1813,1998-2044,2046-2097` | 覆盖事务边界、失败恢复、A2 overwrite 后新文件与 processed marker 同时可见。成功测试未断言 A2 source_id、版本、审计时间字段和 manifest 一致。 |
| 同文件 `:2541-2598,2601-2648,2651-2764` | 覆盖物理损坏／缺 manifest 的 selected 自动修复、传输失败保护旧状态以及未选中／多目标阻断。不能推导为完整但错误来源会修复。 |
| 同文件 `:2100-2187,2382-2434` | 验证 rebuild 的本地行为和写入边界；不是远端重新发现测试。 |
| `tests/cli/test_fins_commands.py:1076-1153,2379-2428` | 覆盖 help、overwrite/rebuild 参数传递、互斥报错。不能证明公开命令取得美的完整报告。 |

最小建议，留给后续已授权实现阶段；本轮不新增测试：

1. **selection owner 回归**：后续直接复用用户已冻结的三条公告 Raw，核对来源留痕后制作 fixture；交换输入顺序，断言中文全文 1209870320 稳定胜出、HEAD 只读取被选项，并覆盖非正文优先及 ID/URL 稳定平手。保留 amended、日期的更高优先级。此项由 selection 实现负责，不扩大本轮 cache 核查。
2. **扩展现有 A1→A2 完整缓存测试，避免重复**：按确认方案保留 COMPLETE + overwrite=False 的 skip 断言，通过真实仓储进一步断言旧 source_id、URL、PDF 摘要、manifest 和文件清单不变。使用旧正文 1209870319、新全文 1209870320 的候选关系，明确“选中了新候选”不等于“已登记新来源”；不要改变默认 skip，也不要靠篡改 fixture 完整性诱导下载。
3. **扩展现有 overwrite 成功测试**：明确断言 source_id/URL/title 已指向 A2，原 document_id 不变，当前契约下版本为 v1、processed marker 为 True，并核对 manifest 与 source。若未来目标要求递增并保留审计时间，应先修改版本 owner 契约，再修改断言，不能只在 adapter 伪造 v2。
4. **身份／并存回归**：覆盖不同 announcementId 但 amended 相同的同槽位映射，以及 amended 改变得到不同 ID；通过仓储断言旧 ID 是否仍存在，禁止把“新增”误报成 supersede。未来若目标要求取代旧版，必须先明确取代关系 owner。

额外低成本修正是重命名误导性的 fingerprint skip 测试；已有 CLI 参数测试足够证明旗标传递，无需重复新增参数镜像测试。公开端到端验收应复用 A1→A2 fixture，不能触网假设远端结果。

## 7. 风险与所有权裁决

| 语义 / 风险 | owner 与修复边界判断 |
| --- | --- |
| 完整报告候选漏选 | `cn_report_selection` 负责标题资格、财年财期分组和选优；上游 downloader 只归一 provider 事实。应以真实 Raw 证明具体漏选，不能在 CLI、storage 或 LLM prompt 特判美的。 |
| 不同公告被完整缓存挡住 | `cn_download_identity` / `cn_form_utils` 负责文档身份；`cn_download_filing_workflow` 负责候选与已有 source 的复用决定。当前按财期槽位的身份与无来源比较的 skip 共同构成直接原因。不能只在展示层把 skip 改叫 downloaded。 |
| 文件完整不等于业务正确 | storage integrity owner 正确回答本地完整性；不应让它访问远端或判断“正文还是全文”。是否允许复用新候选必须在 filing workflow 边界决定。 |
| 版本、审计与替代关系 | source_upsert 负责来源字段及内容版本；workflow 控制是否保留旧完成态输入。overwrite 重置输入是版本从 v1 起算的直接原因。当前无 supersede contract；若需要新增，必须先明确唯一 owner，不能各消费者按时间或 ID 猜。 |
| 结果与存量来源不一致 | `FILING_STARTED` 携带新 candidate.source_id（workflow `:263-274`），skip 结果的披露日期来自新 candidate（filing workflow `:838-846`），旧 source 却未更新。若 A1/A2 日期不同，结果中的日期可不同于本地旧文档；CN adapter `cn_pipeline.py:1471-1522` 继续投影该日期。应在业务结果 owner 明确“尝试候选”和“实际可用文档”的语义，不能断言本轮真实 UI 已发生此差异。 |
| 修复后消费仍旧 | 下载只标记 processed 重处理；后续是否已预处理，本轮未验证。不同 amended 的两份 source 同时存在时也无自动退役保证。 |

最终判断：**代码与已有 A2 测试直接证明旧完整缓存可阻碍新候选登记。按用户确认方案，保留默认 skip，修正 selection 后通过公开 overwrite 将旧正文换为选中的全文；rebuild 与自动物理 repair 均不能替代该操作。** overwrite 不提供 supersede 或递增版本保证。用户已提供隔离缓存 1209870319 与中文全文 1209870320 的核查结果；本轮未独立重验，未声称覆盖已经完成，也不推测投资目录状态。

交付仅此文件；未修改生产代码、测试或投资目录，未提交。审核例外为未触网、未读取实际财报缓存、未执行测试/pyright；这些限制使本报告可证明代码机制与测试现状，不能证明远端结果或实际工作区已修复。
