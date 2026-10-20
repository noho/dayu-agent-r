# Dayu 公开原始读取 R1–R3 修复计划

日期：2026-10-20。基线：`github/main`，`8bf8daec8a022fd705e6cfe32c4283605f1fe6ca`。工作分支：`fix/public-original-read-r1-r3-20261020`。

## 状态、依据与执行边界

- binding scope 为 [已确认目标](public-original-read-r1-r3-20261020-goal-confirmation.md)。本计划不改变目标、非目标、调用方业务 owner 或 draft PR 边界。
- 首轮计划已经总控核对及双路独立审核；本版仅落实[最终裁决](public-original-read-r1-r3-20261020-plan-adjudication.md)的 accepted P1–P4。**本版尚待双路受影响面复审及总控放行，不是 plan-pass**。current gate / next entry point：`plan` 内的 `fix -> 受影响面 re-review`；放行后才进入一个 `implementation / validation` slice。
- 首轮被审版本 SHA-256 为 `e82cc97f92d6d712fbda151207badececb9521c8aa06f53b447920b135e2c845`，原样保存于 `workspace/tmp/public-original-read-r1-r3-20261020/plan-submitted.md`。本轮只修本文并写 [plan-fix 回执](public-original-read-r1-r3-20261020-plan-fix.md)；goal/control/裁决/首轮审核报告/快照只读，不改代码、测试、README、调用方目录、原件或历史证据；不提交/push，不派 agent，不执行下载、上传、预处理或 live 调用。
- 已阅读根 `AGENTS.md`、Gateflow skill、goal/control/最终裁决和两份首轮审核报告；仅局部查阅修订所需的角色消费者、工具截断、prompt、装配测试及 README 职责。原计划的根因、51 个锚、53 次历史调用及版本绑定沿用 goal 和两份同版审核的保存证据，不重扫全仓、不重新执行历史核验。下列测试及实际 API 复验命令仍为实施验收要求，本轮未运行。

证据根目录（下文记为 `E`）：`/Users/leo/workspace/portfolio-manager-v2/orch/workpapers/g0-refactor-implementation-20261020`。任务书为 `E/dayu-upstream-task.md`；六批输入、cold JSON、模块指纹及原始锚的位置均见 goal 和 `E/api-probe-01…06-plan.json`。不读取调用方其它业务材料。

## 1. 动机与根因：修原文契约，不改报告判断

动机成立。便利章节文本、表格 records/Markdown 和 filing citation 服务导航与分析，但不能证明原生标记、物理边界、非数值事实及读取范围。修复不意味着现有表格能力失效，也不意味着原件损坏或一定丢失某条业务事实。

| 缺陷 | 同源直接证据及根因 | 修复位置 |
| --- | --- | --- |
| R1：缺原始结构、非数值事实和可回读定位 | `result_types.py:129` 的 `SectionContentResult` 只有渲染正文/导航/citation；`dayu/documents/processors/bs_processor.py:1668` 的章节渲染将文字规范空白并以表格占位替代结构。`sec_xbrl_query.py:413` 跳过不可解析数值，数值查询不能冒充非数值原文查询。goal 已核实 ATAT/FUTU 大段连续正文；原始锚有真实 `ix:nonNumeric`。 | 独立的、保留来源位置的原文 processor 能力及其公共结果契约；与便利 processor 共用 snapshot/read runtime。不能从已展平正文重建结构。 |
| R2：静默删减 | `sec_form_section_common.py:1260–1295` 的 `_trim_cover_page_content` 无 TOC 时裁到 5,000 字；`:1456–1474` 仍把原前缀终点记录为 `first_start`。裁剪发生在生产者，公共结果既无删减声明，也无原始续读路径。MSFT/ASML/TSM cold 返回长度均为 5,000；ASML 尾文以 goal 更正及保存 JSON 为准。 | 去掉 producer 的任意字数裁剪；保留按真实 TOC/marker 定义的导航视图。公开原文分段读取拥有精确范围和续读，便利章节不再暗示等同完整原件。 |
| R3：读取对象不可显式选择，filing 身份掩盖资产差别 | `read_runtime.py:3023–3064` 只用 `snapshot.get_primary_source()` 建 processor；`:2580–2632` 的 citation 来自 filing provenance/meta，没有具体资产身份。`repository_protocols.py:733–902` 已有完整 files、revision、primary、`get_source(filename)`，缺的是公开投影和选件。 | storage snapshot 提供同版资产事实，read runtime 提供枚举/显式选择；实际内容与身份在同一 borrow 中返回。 |

R3 的重要反证：首轮计划只读核对了 TSM 指定 source 的相关 meta；`primary_document` 确为 `tsm-ex991_18.htm`，files 同时包含 `tsm-6k_20220812.htm` 和附件，二者 SHA/size 与 `E/tsm-main-vs-attachment.json` 一致。`sec_download_filing_workflow.py:716–747`、`sec_6k_primary_document_repair.py` 明确允许为核心报表提取改选 storage primary。**storage primary 是现有默认阅读/处理入口，不保证是 SEC 提交的原始主件。**本任务不改这套选文，不重写 metadata，不修复下载链；没有证据要求这样做。主件中的真实 `<a href="tsm-ex991_18.htm">` 才是可回读的关系证据。

## 2. 最小充分方案及 owner

采用四个公开方法，挂在现有 `FinsReadRuntime`，统一由 `DefaultFinsRuntime.create(...).get_read_runtime()` 获得。原文 processor 是现有缓存条目内按资产懒建的读取能力，不另建服务、processor registry、文件仓储、持久化索引或版本系统。不能要求所有 PDF/Docling processor 实现 HTML 原文能力。

| 语义 | 唯一 owner / 实现边界 |
| --- | --- |
| canonical ticker、document identity、filing/material namespace、已发布 revision、完整文件清单、storage primary、同版实际文件 bytes/摘要/size、已验证的资产角色声明 | `dayu.fins.storage` 及 `SourceSnapshotProtocol`。runtime 不探测目录、读 raw meta、算 revision 或重新 hash 文件。 |
| CN/HK 唯一显式 original PDF 的业务选择与 exact publication 原件读取 | `project_report_original` / `read_report_pdf`；消费 storage 同一 typed 角色和实际内容身份，仅保留既有业务校验与拒绝，不重新解释 raw 文件角色。 |
| 严格解码、Unicode 原文坐标、原始 token/节点、属性/namespace 作用域、结构关系、非数值节点及 context/target/visibility 的技术证据、解析未决状态 | `dayu.fins.processors` 的原文能力；复用 `source_text.py` 严格 decoder，从 snapshot 的指定 `Source` 读取。原文与节点索引共享同一份文本。 |
| 参数准入、借用同版 snapshot、资产选择、版本预期校验、分页公共结果及错误映射 | `FinsReadRuntime`；typed 数据契约放 Fins domain，公共序列化/projection 由 `tools/result_types.py` 或其同职责小模块持有。不得让 runtime 堆积 HTML/iXBRL 解释。 |
| LLM schema、结果说明、process-backed 调用及 Host 截断声明 | 既有 read tools provider；仅投影同一个 runtime 结果，不补解析、不判断完整性。 |
| 取消触发、接受结果的终态屏障 | Host；Fins 观察 token 并释放本次资源。 |
| 用途选框解释、主体/证券身份、财年、冲突优先级、报告准入 | portfolio-manager 调用方；Dayu 不产生这些结论。 |

### 2.1 资产及版本契约

新增严格 typed 的 `SourceAssetIdentity`（名字按此实现，无兼容别名）：必填 `ticker: str`、`document_id: str`、`source_kind: Literal["filing", "material"]`、`filename: str`、`sha256: str`、`size_bytes: int`。sha256 为实际完整资产 bytes 的 SHA-256，size 为实际 bytes 长度。资产 namespace、filename、实际 sha/size 与 span 足以绑定文件内容版本；不新增公开 storage 治理 revision。它是内容身份，不是业务事实，不替代内部 storage revision。所有原文返回和定位都携带该身份；文件名是业务资产名，不是 filesystem path。

现有 `SourceSnapshotFileDescriptor.sha256/size` 是可选声明值；不能直接把缺失值填空，也不能用 etag 冒充 hash。`_fs_source_snapshot.py:1068–1122` 在 full snapshot 复制时已经计算实际 digest/size 并核对声明，当前未对外保留这一必需事实。最小扩展是在**同一复制过程**保留结果，由 full snapshot 的 typed `get_content_identity(filename)` 暴露必填实际 sha256/size。light snapshot 不承诺该接口可用，调用时明确拒绝。既有声明和实际值有冲突仍由 storage fail closed；无声明时实际值仍可产生。不得在 read runtime、parser 或 verifier 中另建生产 hash/cache 真源。

文件角色只投影 storage 已验证的声明：`is_reading_primary: bool`、可选原件/派生角色、`original_filename`、`derived_from`。若 descriptor 尚未携带角色，由 storage 将既有 integrity inspection 的角色投影为 typed snapshot 字段，不让消费者解析 raw `source_meta.files`。没有原始主件角色声明的 SEC source 明示 `role_status="unrecorded"`；不按名字、列表首项、URL、form 或 incoming metadata 补出 `is_original_main=true`。不新增 durable `original_main` 字段，不把阅读主件重命名为原始主件。

必要直接消费者迁移包含 `dayu/fins/pipelines/report_original_source.py:project_report_original`：它当前直接解释 `snapshot.source_meta.files` 的角色，必须改为消费上述同一 storage typed 投影。保留“显式 original 声明恰好一个，且该资产为 PDF”的业务规则；无角色、多个 original、非 PDF 或声明不可信仍拒绝，不能改成从多个 original 中挑出一个 PDF，也不能以 reading primary、派生件或文件名补位。角色/descriptor/实际身份冲突在 storage owner 边界 fail closed，下游不重算角色或 hash 来补救。`read_report_pdf` 仅在该 typed 角色/实际身份迁移所必需的范围调整；保留 expected publication、同版 meta、实际 locator、非空 PDF、取消与资源释放及既有错误分类，不借此重构下载、CN/HK 报告准入或下载选文。

新方法必须显式传 `source_kind`；同 document ID 跨 filing/material 不混用。沿用现有 ticker canonical/alias route，但新原文 API 的 document ID 只接收列表返回的 exact ID，不复用 accession 等便利别名。filename 必须 exact 命中 snapshot 清单；不取 basename、不大小写纠正、不接受路径、URI、glob 或邻近名字。原始读取后续方法必须传枚举结果的 `expected_sha256`，在同一 active borrow 内比较后才返回内容。

### 2.2 四个公开 API

以下参数均 keyword-only；类型使用严格 dataclass/TypedDict/封闭联合，不增加 `Any`、`object`、裸容器或额外 payload 参数。`cancellation_token: CancellationToken | None = None` 为四方法共用显式参数。

| 方法 | 参数及结果承诺 |
| --- | --- |
| `list_document_assets` | `ticker: str, document_id: str, source_kind: SourceKind`。返回完整有序资产列表、`reading_primary_filename`、每项上述身份/角色及 `content_type: str | None`、`text_supported/structure_supported/inline_facts_supported: bool`。能力按支持的格式表达，不保证内容有效；无论何种格式均可枚举。列表本身不静默截断。 |
| `read_original_text` | 上述身份选择参数，加 `filename: str, expected_sha256: str, start: int = 0, end: int | None = None, max_chars: int = 16384`。`end=None` 表示原文 EOF；返回精确原始文本窗口、请求/实际范围、全文长度、`truncated` 和 `next_start`。用于整件分段读取，也用于按结构/事实定位回读。 |
| `read_original_structure` | 同一资产选择参数，加 `start: int = 0, end: int | None = None, max_nodes: int = 200`。按原文中节点起点落在 `[start,end)` 选择，原文顺序分页；返回 token/节点记录、页面外祖先信息、总匹配数、`truncated`、首个未返回节点的 `next_start`。这是节点集合范围，不是“此段原文已完整输出”；不可用节点条数替代字数。 |
| `query_original_facts` | 同一资产选择参数，加 `concepts: Sequence[ExpandedName]`（非空；每项必填 `namespace_uri: str, local_name: str`）、`offset: int = 0, limit: int = 100`。只查当前资产中的原生非数值 inline 节点，按原始顺序返回全部匹配 occurrence 的分页及原文/context 定位，不按业务值/context 去重。返回匹配总数、`truncated/next_offset` 及独立的解析完整性状态。 |

选择这些接口的理由：枚举解决选件；原文窗口是所有定位的公共回读路径；结构窗口解决物理边界/局部顺序；指定非数值概念查询避免下载一个全文事实包。无需万能 query/factory、语义检索旁路或新的 financial API。既有 `query_xbrl_facts` 保持数值用途，不通过加兼容模式混入不同结果模型。

格式范围：HTML/XHTML 支持结构和 inline facts；XML 支持原始 XML 结构，不把普通 XML fact 冒充 `ix:nonNumeric`；项目现有 UTF-8 文本格式支持严格原文读取。PDF/图片等二进制资产可枚举核验，调用新文本/结构方法明确 `not_supported`；不重跑 OCR、转换或 Docling。已存 Docling JSON 的文本读取只表示 JSON 文件原文，不是 PDF 原始页坐标。已有 A/H 阅读能力仍走原 processor。

分页默认/上限放原文 owner 的具名常量及 `FinsToolLimits` 默认值：文本默认 16,384、上限 65,536 码点；结构默认 200、上限 1,000 节点；facts 默认 100、上限 500 条；正数且拒绝 bool。超限报参数错误，不静默 clamp。本次不向 `dayu/config/tool_discovery.json` 新增 limit 键；若实施事实确需修改 JSON，必须向总控报告理由和影响，并同步纳入 `tests/runtime/test_config_loader.py` 的回归/coverage 实际 argv 与 config README 职责复核，不自行忽略精确配置断言。这些是 transport budget，不是财报业务边界；实现可在审核时按实际内存/输出证据调整预算，不改变范围语义。大字符串属性、祖先、context、continuation 不因条目分页而无限膨胀，使用下述有界 preview + 精确原文引用。

### 2.3 范围与定位：可复验，不伪造物理坐标

- `OriginalSpan` 必填 `asset: SourceAssetIdentity, start: int, end: int`。坐标为**按现有 decoder 严格 UTF-8 解码、仅移除开头 UTF-8 BOM 后的 Unicode 码点**，0 基、左闭右开；不是 bytes、行列、Markdown 下标或浏览器 DOM offset。不做换行/空白/实体/Unicode 规范化，保留 CRLF、原大小写与实体拼写。响应说明 `encoding="utf-8"`、`bom_bytes=0|3`；hash/size 始终覆盖包括 BOM 的实际 bytes。
- 文本返回 `requested_range`（将 end=None 具体化）、`returned_range`、`total_chars`、`text`、`truncated`、`next_start: int | None`。`text == decoded_source[returned_start:returned_end]`；`truncated` 当且仅当本次请求范围未读完，`next_start` 等于实际终点；连读覆盖无间隙/无重复。`start=end` 合法空结果，负数、倒置及超过 EOF 的范围拒绝。读一个局部范围完成，不代表整个文件已读完。
- 结构与 fact 的 span 同样调用 `read_original_text`，重复传完整身份及 expected hash，按返回 `next_start` 读至目标 end；不能用本地私有 helper 才能还原原文。preview 必须同时给出 span、`preview_complete: bool`，不靠末尾省略号表达截断。
- 稳定性承诺只依赖资产 namespace 和实际 bytes。相同 bytes 可跨冷暖缓存/runtime 重开回读；重发相同 bytes、metadata-only revision 变化可重新获取但不改变内容坐标。不同 bytes 必须拒绝旧 expected hash，不能静默重定位。节点展示标签只在该原文内引用，长期定位以资产+span 为准。
- 原件大节点可能横跨多个窗口：节点记录只给其起止 tag/content span 和有界 preview，不将整棵子树复制进每个祖先，也不把整段 table/文本块一次性返回。

## 3. 结构与非数值事实契约

### 3.1 原文结构

解析 owner 直接消费 snapshot 指定资产的严格文本，维护位置保真的词法记录及可证实的父子关系。不能从 BeautifulSoup 重新序列化 HTML 后计算位置；该过程会改大小写、实体、空节点和修复布局。可复用现有库获得候选结构，但必须以原文 token 的位置和关系校验为准；无需为本轮重建浏览器排版器。

`OriginalNode` 至少包含：节点种类（element/text/comment/doctype）、原始 tag QName、expanded namespace/local name 的解析状态、opening/content/closing span（适用时）、parent 定位、同层/原文顺序、原始属性及 namespace 声明。属性保序并保留原名、原始值/引号对应位置；缺失与显式空字符串不同，重复属性保留并标记歧义。原始属性值不以 HTML 反解码值覆盖；若提供解码值，必须是独立命名的技术投影。单个极大 opening tag、属性集合或祖先链使用有界投影并显式标记 `attributes_complete` / `ancestors_complete`；完整 opening span 和 parent span 仍可分别通过公开文本/结构 API 回读，不能以预算为由丢掉原始属性或伪造根节点。

namespace 的公开发现路径就是 `read_original_structure` 的原始命名空间声明及其作用域：先读文件头/相关节点及祖先，取得目标 QName 在定义处绑定的 URI，再构造 facts 查询；局部重绑定以实际作用域为准。若声明投影未取齐，沿已有 span 用公开文本读取补齐。既有 namespace 结构与原文 span 已足够，不为文案澄清新增顶层 namespace 清单、QName 兼容输入或第五 API。

结构至少覆盖 table/tr/td/th 的实际元素关系、rowspan/colspan 原属性，段落/块元素、br、空 inline、注释及文本。物理单元是原始元素边界，不是合并后 DataFrame 单元格，也不是屏幕坐标。跨表格、跨行、跨单元格、跨块的节点不因文本相邻而被合并；内容内部的空 inline 仍是其父节点内的独立节点。表格嵌套和跨窗祖先可定位，不能跳过布局表从而丢掉物理阻隔。不推断选框与标签的业务配对。

HTML 合法 void/可省略结束标签按格式规则处理，区分显式闭合、规则闭合和无法确定；不会把正常 `<br>` 当损坏。XML 保持 QName 大小写和精确 namespace 作用域。对非法错配、缺失、重复 ID 等不能安全确定的关系，返回 `parse_status="partial"`、固定 reason 与原始范围，未知边界为 None；不得伪造完整父链或把错误改为空成功。词法/解析执行失败返回 typed failure，原文窗口仍可单独读取。正常的分页未读完和解析不完整是两个独立维度。

### 3.2 指定非数值 inline fact

按 inline XBRL namespace 识别节点，使用定义处的 namespace 作用域解析 `name` 与 `format`，不依赖 `ix`、`dei`、`ixt` 固定前缀。concept 匹配用 expanded name exact equality；同 local name 不同 URI 不合并，同 URI 不同 prefix 可匹配。返回 `name` 原 QName、resolved URI/local name、原 `format` QName 及其绑定。未绑定前缀等无法判定的候选形成 partial diagnostics，不能据此证明零事实。所给 URI 版本必须来自原文，不从 filing meta 推断。

每条 occurrence 至少交付：原节点和内部原值的 span/有界原文 preview、所有原始属性、原 `contextRef`、原 `target`、`format`、`xml:lang`、`xsi:nil`、`escape`、`continuedAt`（缺失用 None，显式空值保持空字符串）、节点/物理祖先定位、context 解析结果、visibility 证据。`raw_value` 指原节点内部原文，可含实体和 inline 标记；不将 `☒`/`☐` 或 fixed-true/fixed-false 转成业务真假值，不做年度/用途判断。

- **context / target**：技术解析可将缺失 target 映射到 inline 规范的默认目标分组，但同时返回 `target_raw=None`、`target_origin="implicit_default"`；不得把默认来源伪装为显式属性。按目标分组和 ID 解析 context/resources，返回命中的原始 context 元素 span/preview、其原 namespace 与资源目标信息。重复 ID、多候选、缺 contextRef、目标内无匹配分别明确 unresolved/ambiguous reason；不拿另一个 target 的第一个 context 补位。不对 context 的实体、期间、dimension 作业务归纳。跨资产定义不擅自加载，当前资产未解析即明确未决。
- **visibility**：返回是否处于 `ix:hidden` 的原始祖先位置，以及本节点/祖先 HTML hidden、style、class 等原始声明证据；`visibility_status` 只区分已证实隐藏声明与无法确定，后者不能输出 visible=true。明确 `css_evaluated=false`：不执行外部 CSS/脚本，不计算浏览器可见性；需要的 style/class/规则原文可通过结构及全文路径回读。
- **continuation / exclude**：保留原始 `continuedAt` 和 `ix:exclude` 节点，区分本节点正文、exclude 与 continuation。fact 与 continuation 节点都给出下一跳的解析状态和目标 span；调用方以目标起点调用公开结构 API 可取得该节点及其下一跳，以文本 API 读取各段。不要把长链展开成单次返回的无界列表，不增加第五个续读 API。缺目标、循环、多候选明确 partial，不仅取首段并声称值完整；原始片段按链顺序可逐段回读，exclude 范围从结构记录取得。链遍历诊断也检查取消，不能有未声明的链长裁剪。
- **查询完整性**：`total_matches` 是当前资产内指定 expanded concepts 的 occurrence 总数，`next_offset` 只控制分页；`parse_status/reasons` 单独说明解析可信范围。成功的零命中不代表业务事实 false，也不承诺其它资产没有该概念。MSFT 三条 TradingSymbol 必须全部保留，分别带自己的 context 与原文，不能仅按值 MSFT 去重。

给 LLM 的结果同时提供任务可读的原文 preview、范围及下一步读取方式，不仅抛出节点 ID。工具 schema 须自足解释字段名、含义、类型、必填性、允许值、两层续读顺序及至少一个最小例子；facts 最小示例展示先由公开结构取得 URI，再把该返回值用于查询，测试及真实验收实际执行此发现链，不猜年度 URI、不把 URI 写死为夹具知识。字段/范围说明区分 Fins 的页完成状态与 Host 的本页内容截断，面向模型使用“当前读取页”与“本次显示内容”解释；若本次显示内容被截断，须按返回的 `cursor/scope_token` 调用一次 `fetch_more`，省略 `limit` 取得当前读取页全部余量，与可见前缀拼接取齐本页后，再用 `next_start` / `next_offset` 继续下一页。`cursor/scope_token` 只是本次被截内容的续读引用；cursor 成功使用一次后即失效，返回结果不提供新 cursor，不得用小 `limit` 分段并期待后续 cursor 来取齐本页。不得让模型理解内部类名或治理 revision；filename 是枚举所得资产名，sha256 是后续读取时原样传回的内容校验标签，都不是财报推理依据。

## 4. 同版缓存、错误与取消生命周期

### 4.1 复用现有 cache/snapshot，按需拆职责

保留当前 `ProcessorLRUCache`、creation lock、active borrow、retire/close 机制。将缓存条目的 eager convenience processor 收敛成同版 source entry 内的懒建能力：一份 full snapshot、同版 typed meta/provenance、按 filename 建立的原文文本/结构/facts 索引、需要时才建立的既有 primary processor。枚举或原文读取不能以 convenience processor 构造成功为前提；原始主件不能被迫按阅读附件的表单 processor 解析。这是同一缓存容器内的必要职责调整，不新设 source cache 或 parser 服务。

cache key 增加 source_kind，成为 `(canonical ticker, exact document_id, source_kind)`；资产索引在 entry 内以 exact filename 区分。原便利入口仍用一次 storage light snapshot 解析 namespace，保留原有歧义拒绝，再使用其实际 kind 取 key；不由 runtime 分别探测两个目录。缓存是否可复用只比较 storage opaque revision 和 kind，不从 sha、mtime、文件顺序、source fingerprint 重建 publication version。

冷 miss：storage full snapshot → 实际内容身份 → 当前资产的解析能力 → 同 borrow 的结果。暖命中：仍按现有机制向 storage 取 light snapshot 确认 publication；同版复用已完成能力，实际 identity 及 expected hash 比较仍来自 active borrow 所持 full snapshot，不能拿 light descriptor 的可选声明摘要代替。相同资产并发 miss 单构建；两种资产可以共享 snapshot，但不能串用正文、context 或索引。原子发布新 revision 后新调用不得返回旧 entry；旧 active borrow 可完成自洽旧版结果，不强行改贴新版身份。同版缓存复用指同一 Python runtime；现有工具每次 process target 都重新创建/关闭 runtime，不承诺跨工具进程保留索引，不为此新建持久化缓存。

replacement、eviction、clear、runtime close 仍只 retire，最后 borrow release 才清理 snapshot；close 与 cache publication 共用现有线性化点，close 后不能发布新 entry。未完成/失败/取消的解析能力不加入缓存；可保留已经完整成功且仍有效的其它能力。不因失败回退到上次 publication、另一个资产或默认 primary。LRU 淘汰同时回收 entry 中全部原文索引；全件原文/索引是按需解析且按 entry 有界复用，输出始终分页，不承诺只需一个窗口大小的总内存。

### 4.2 错误是公共 contract

| 场景 | 行为 |
| --- | --- |
| ticker/document/filename/范围/limit/concept 形状非法；跨 kind 或身份复用 | 沿用 `FinsReadArgumentError` / `invalid_argument`，指出需要重新从当前 namespace 枚举；不做 loose parsing 或别名兜底。 |
| 合法 namespace 内资源不存在、deleted 或文件不在完整清单 | 明确 `not_found`；空文档正文与不存在区分。storage corruption/不完整 source 不能降级成 not_found。 |
| expected hash 与当前实际资产不同 | 新增 typed `asset_version_mismatch` 业务错误，要求重新枚举/读取；不得给旧坐标套新版内容。比较发生在被借用的实际版本上。 |
| storage 持续 publication 变化或完整性/I/O 失败 | 保留 `source_changed_during_read` 与现有 storage failure 分类。无 stale-cache success；storage 原异常/cleanup cause 保留 operator 诊断，公开文案无路径/私有 key/revision。 |
| 非 UTF-8、BOM/文本解码失败 | 复用 `source_decode_failed`，无 ignore/replace。 |
| 当前格式不支持结构/inline 查询 | `not_supported`，不走便利文本 fallback。 |
| 可保全原文但结构/引用存在未决 | typed partial + reason + 范围；不与分页 truncated 混淆。 |
| parser 本身执行失败 | 新增固定 `original_parse_failed` typed 业务错误，不把失败当零事实。 |

### 4.3 取消与资源收口

四方法在准入前、snapshot 获得前后、能力构建/分页前后和最终返回前观察现有 `CancellationToken`，按既有 Fins 取消路径传播；不把 cancel reason 投影为财报内容。新增原文词法扫描、节点/facts 遍历须按固定工作块检查，检查间隔用具名常量；不在每字节轮询，也不等全部大文档解析完才检查。

不让底层 parser 反向 import tools 层。若必须共享现有 Fins 本地取消异常/检查规则，将其移至 Fins 层中立小模块并迁移现有 imports，不能新增不同语义的取消 helper 或仅透传的兼容 re-export。storage 继续持有自己的 snapshot cleanup；本计划不为已有同步 storage guard/copy 引入第二套取消状态机，单次不可中断 storage 段返回后立即检查并关闭尚未转移的 snapshot。direct Python 的取消是检查点合作式，不承诺阻塞 I/O 的硬时限。

工具仍 process-backed：仅序列化 workspace、标量/JSON 参数、limits；子进程从公开 runtime 重建并在 finally 关闭。Host 原有取消/终态 accept barrier 丢弃 late result，不能因新原文入口改为父进程阻塞处理。对取消、parser 错误和 snapshot cleanup 双失败，保留首要异常，不以清理失败掩盖取消/原错误。取消或 runtime close 与构建竞争不得留下 FD、临时树、active borrow 或后台任务。

## 5. 既有能力、修改范围与 docs decision

一个 implementation slice，同时完成代码、测试、文档及真实 API 验收；没有必须先独立验完才决定后续方案的迁移依赖。多模块不构成拆 slice 理由。

生产范围：

- storage snapshot 协议/实现及其必需 domain identity/角色投影：复用实际复制校验结果，不改 source-meta 持久 schema，不启动 workspace migration。
- `pipelines/report_original_source.py`：将 `project_report_original` 从 raw files 角色解释迁到 storage 同一 typed 角色/身份；`read_report_pdf` 只作这次迁移所需调整，保持 §2.1 的唯一 original PDF、exact publication 和安全拒绝，不扩展为 CN/HK 下载或准入重构。
- Fins domain 原文 typed contract（建议 `dayu/fins/domain/original_read_contract.py`）；Fins processor 中按职责建立原文文本/结构与 inline 非数值读取能力（建议 `original_content.py`、`sec_inline_original.py`），复用 `source_text.py`。不重复实现财务报表解析。
- `tools/read_runtime.py`、`cache.py`、结果/错误投影：四方法、同版资产索引及必要 lazy entry/namespace 调整。局部锁和函数拆分由实现者决定，不用本计划穷举。
- `sec_form_section_common.py`：取消 5,000 字任意裁剪，保留真实 TOC/marker 导航边界。`DocumentSectionsResult`、`SectionContentResult` 增加实际 `source_asset`；章节结果声明 `content_scope="section_view"`，工具说明明确其非完整原件承诺及原始读取路径。不把已渲染 section 的字符下标冒充 original span。
- `tools/fins_tools.py`、`fins_limits.py`、必要 provider 装配：公开四个工具，统一 runtime/projection 和 process target 路由。使用当前 Host `ToolTruncateSpec` 处理额外输出截断，不能让截断的原文 `text` 与 runtime 返回范围不符却仍被当完整：工具层的 Host 截断元信息和 Fins 页范围各自显式保留，只有取回该 runtime 页全部内容后才能按其 `next_start` / `next_offset` 前进。Host `cursor/scope_token` 仅续读当前调用被截内容，Fins `next_start/next_offset` 仅续读同一资产请求范围内的下一页；两者不能互换。新工具说明须明确 cursor 成功使用一次后即失效，不返回新 cursor；取齐本页须用一次省略 `limit` 的 `fetch_more` 取得全部余量，不能传小 `limit` 期待后续 cursor。此行为必须经 §6.1 的实际工具联合测试，不以模型会遵循说明为保证；不增加跨层状态、许可机制或自建 cursor。大属性/context 先在 Fins owner 用 preview/span 控制大小；新预算遵守 §2.2 的默认值边界。
- `dayu/config/prompts/base/tools.md`：只在现有 `fins-read` 指引内补原文四操作流程：`list_documents` → `list_document_assets` 选 exact 文件/hash → `read_original_text` / `read_original_structure`；非数值查询先从公开结构发现定义处 namespace URI，再调用 `query_original_facts`，按 span 回读。说明双层续读时须用一次省略 `limit` 的 `fetch_more` 取齐当前读取页，再按 `next_start/next_offset` 读下一页；cursor 成功使用一次后即失效，不返回新 cursor，不得传小 `limit` 期待后续 cursor。同时说明文件/hash 的引用含义，并把 `has_financial_data` 前提明确限定到财务取数，不能阻止原文枚举/读取/结构/非数值查询。面向模型用“当前读取页”和“本次显示内容”等自解释文本，不要求理解 Host/Fins 内部术语。沿用现有标签/manifest 装配，不新增 scene、治理或 context slot。

原有九种读取能力保留：默认仍用 storage primary；SEC section/table 导航和 ATAT/FUTU records/Markdown 正向语义不退化；A/H PDF→既存 Docling 的 section/page/table 继续工作，不因新 XML/HTML parser 改 registry 优先级。原数值 XBRL 与 financial statement 不改变结果含义。不为这些可能消费 sidecar 的结果笼统添加“全部事实仅来自 primary bytes”的错误承诺；本轮新资产绑定覆盖四个原文 API 和明确的章节/目录读取结果。

测试范围：新增 owner 原文/结构/facts 合同测试、真实 Fs→公开 runtime 集成及实际新工具→Host→`fetch_more` 的联合测试；更新既有 snapshot、角色直接消费者、cache 生命周期、section/provider/process、combined tools 精确工具集和 prompt scene 装配断言。原角色测试随 owner 迁移，不保留“修改 raw meta 后由下游补判”的夹具模型。合成 fixture 验证机制，已有官方原件只读复验验证实际输入；不把 fake parser、固定返回值工具或剪裁后 fixture 冒充真实读取链路。分析辅助验收程序只放 `utils/`，临时证据/副本只落本库 `workspace/tmp/` 或系统 tmp。

已实读相关 README 更新约束，docs decision：

| README | 本次决定及职责理由 |
| --- | --- |
| `dayu/fins/README.md` | 实施后更新：公开 API/工具数量、原文结果/坐标、reading primary 与原件区分、唯一缓存和错误边界属于其已实现 capability/公共契约职责。不能提前把本计划写成落地事实。 |
| `tests/README.md` | 实施后更新实际新增 owner/runtime/process、Host 联合续读及工具/scene 装配回归入口和断言范围；其“README 更新边界”只允许已有测试事实，不记 gate 过程。 |
| `dayu/config/README.md` | 已按其“默认配置、workspace 覆盖、prompts 目录职责”及条件块装配说明复核；实施后在该职责内更新实际原文工具指引/装配说明，不扩写 parser 或 Host 内部机制。新 limits 使用 owner 常量/FinsToolLimits 默认，不宣称 JSON 已有新键；若 JSON 必须变化，按 §2.2 向总控报告影响并同步复核配置说明与 config_loader 测试。 |
| 根 `README.md` | 目前不改：该文件是最终用户操作手册，本任务不增加 CLI 命令、安装/初始化/工作流或排障入口。若实施实际改变用户可见操作，再按约束复核。 |
| `dayu/README.md` | 目前不改：整体层次、装配根、Host/Fins 边界均不变，原文能力属于 Fins 内部。 |
| Engine/Host README | 不触发：计划不改这两个生产包；Host 测试只验证既有截断协议与真实新工具的交互。若实施事实要求改变其生产机制，先由总控判断范围及文档影响；不借 P4 新增 scene 治理。 |

## 6. 验证：owner contract、公开入口、实际版本

### 6.1 必须断言的行为

1. **storage identity / 角色 owner**：full snapshot 实际 hash/size 与原 bytes 一致，包括无声明摘要、BOM、空文件；声明不符失败；light 不伪造实际身份；身份/roles/primary/provenance 同版。filing/material 同 ID 各自可显式读取；缺失 kind 的旧入口保持歧义拒绝。storage owner 测试断言 typed 角色投影与合法声明一致，矛盾在 owner 边界拒绝，不从文件名/primary 猜角色；原文枚举与 `project_report_original` 消费同一 typed 投影，后者仍只接受唯一显式 original 且为 PDF，覆盖缺角色、多 original（包括一 PDF 加另一非 PDF）、派生件、非 PDF 及不可信声明的拒绝。`read_report_pdf` 保留 exact publication/同版 meta/locator/非空/取消资源行为；角色与实际身份测试不得靠下游 fallback、重 hash 或 monkeypatch raw meta 后补救来通过。
2. **范围**：大于 5,000/65,536 码点、CRLF、实体、多字节字符/BOM 分窗逐段拼接等于严格原文；所有 span 可由公开方法精确回读。分页无漏重，局部完成与全文完成区分；范围/预算错误和 EOF 空窗口明确。Section producer 超过 5,000 的前缀不再被字数删除，TOC 导航仍正确。
3. **结构**：同一标签内部空 span 不形成外部阻隔；跨 td/tr/table/block/br 的端点不能合并，嵌套表和 rowspan/colspan 原属性保留。跨页窗口祖先、原顺序、注释、空节点、实体拼写、合法 void/省略闭合及 malformed 未决均有断言；不依赖 BS 重序列化结果。
4. **非数值 owner**：prefix 改名但 URI 相同仍匹配；同 local name 不同 namespace 不混同；namespace 重绑定、format 原值、原空属性/缺失、context/target 默认来源、跨 target 同 ID、重复/缺失 context 均验证。checkbox 原文保留且无业务 bool；MSFT 同值三 occurrence 不去重。ix:hidden/HTML隐藏/style/class 的证据及 CSS unknown、continuedAt/exclude/循环/缺目标和大原值续读均验证；解析 partial/失败不冒充完整零命中。
5. **cache/version**：同版冷暖正文/节点/context/身份一致；暖读取复用已建索引；两个资产绝不串读。真实 Fs 发布 A→B、metadata-only revision、相同 bytes 重发、删除/恢复、版本预期不符及 storage bounded consistency 失败均验证。current result 始终自洽，旧 active borrow 可读 A，后续只能 B；不能仅检查读前后本地 hash 一样。
6. **生命周期/错误**：冷构建取消、解析中取消、return 前取消、runtime close/eviction/clear 与 active borrow、并发初次 miss、snapshot 获得后取消、cleanup 双失败；无未完成索引发布、late success、FD/临时树泄漏。保留既有 process-backed cancel/accept 回归。
7. **保留能力**：六批原正向样例、已有 SEC sections/tables、数值/财务结果，以及真实既存 600660/0700 Docling sections/page/cover；不重新转换。原不支持操作只保留明确不支持，不强迫其成功。工具成功/失败/取消 nested 输出不泄漏 local URI、temp path、private mapping key、storage revision；新公开 filename/hash/span 是有解释的内容标签，不能沿用旧测试一刀禁止。
8. **Host 截断 + Fins 分页联合契约**（新落点 `tests/host/test_fins_original_read_truncation_fetch_more.py`）：使用真实 Fs 资产、实际新 read provider/process-backed 工具及 Host ToolRuntime，不用固定文本假工具或 mock runtime 结果代替。资产至少跨两个 Fins 页；构造合法第一页 `truncated=true`、`next_start=returned_end` 且页文本大于 Host 低截断预算，断言外层 Fins 请求范围/完整页范围/身份不被改写，`text` 的 Host 截断包装另有本页未显示内容及续读引用。对每个被 Host 截断的 Fins 页，测试驱动一次实际 `fetch_more`，省略 `limit` 取得该页全部余量；将可见前缀与返回余量拼接，先断言精确等于该 runtime 页原文，再按其 `next_start` 读下一页直至 EOF。跨全部页拼接必须等于严格解码原文，无缺口/重复；最后 Fins `truncated=false`、`next_start=None`。两种 `truncated` 各述其范围；Host `cursor/scope_token` 是当前调用、既有运行 scope 内的余量引用，不能作资产坐标或下一 Fins 页标识。既有 Host 回归独立保留 scope/token 不符、过期、`limit` 只返回余量前缀、cursor 成功使用一次后即失效且不返回新 cursor 的断言；`limit` 前缀/单次使用回归不混入取齐当前页的联合流程。不修改 Host 生产机制，不新增状态机来追踪或禁止模型跳页。

   若生产选择固定 Host 文本预算覆盖所有合法 Fins 文本页、因而实际配置不会再截 `text`，必须用实际工具断言“所有允许的页预算均不超过有效 Host 文本预算”及最大页完整返回、无 Host 续读引用，再验证 Fins 跨页拼接；不能仅关闭测试截断跳过验证。仍须让长结构/事实实际输出经 Host 截断，并用一次省略 `limit` 的 `fetch_more` 取齐当前页，断言其条目/preview/span、Fins 页续读和 Host 截断语义分别成立。固定预算是否满足此分支以实现及有效配置证据交 code review 判断。
9. **工具发现与 LLM 指引装配**：`tests/tools/test_combined_tools_acceptance.py` 的精确工具集更新为真实九个既有工具加四个新工具，不保留旧列表兼容分支；provider schema 断言字段说明、namespace 发现例子和双层续读顺序自足。`tests/runtime/test_scene_prepare.py` 更新实际工具目录并通过现有 `fins-read` 标签/manifest 装配，断言原文流程、从原文结构取得 URI、内容校验标签及续读顺序进入应选 scene 的最终 prompt，未选标签不引入指引、条件 marker 不泄漏，interactive 仍不选 preprocess/upload。`has_financial_data` 只约束财务取数，不成为原文四操作的前提（覆盖 false 场景）；这些是 schema/实际装配/工具 contract 断言，不声称测试证明模型必然遵循指令。

### 6.2 开发树测试和类型检查命令

在本库执行，每个 shell 先激活 `.venv`。新测试计划落点为 `tests/fins/test_original_read_contract.py`、`tests/fins/test_original_read_runtime.py`、`tests/host/test_fins_original_read_truncation_fetch_more.py`；实现若调整名称，必须同步下面回归/coverage 命令并保存最终实际 argv/退出码/结果，不保留不可执行命令。新测试文件将在实施阶段创建，本次 plan fix 不执行未来测试。

```bash
source .venv/bin/activate
python -m pytest tests/fins/test_original_read_contract.py tests/fins/test_original_read_runtime.py tests/host/test_fins_original_read_truncation_fetch_more.py -q
```

```bash
source .venv/bin/activate
python -m pytest tests/fins/test_fins_storage_atomicity.py tests/fins/test_fins_storage_provider.py tests/fins/test_storage_asset_filename_contract.py tests/fins/test_fins_read_runtime.py tests/fins/test_read_runtime_semantic_ownership_guards.py tests/fins/test_processor_read_consistency.py tests/fins/test_processor_registry.py tests/fins/test_financial_read_contracts.py tests/fins/test_fins_ingestion_runtime.py tests/fins/test_cn_annual_report_source.py tests/fins/test_sec_pipeline_download.py tests/documents/test_processors.py tests/tools/test_combined_tools_acceptance.py tests/host/test_toolruntime_truncation_fetch_more.py tests/runtime/test_scene_prepare.py -q
```

```bash
source .venv/bin/activate
pyright
```

覆盖率用上述两组测试合并的一次运行测量，不能以抽中少量 case 的 aggregate 掩盖文件缺口：

```bash
source .venv/bin/activate
mkdir -p workspace/tmp/public-original-read-r1-r3-20261020/coverage
python -m pytest tests/fins/test_original_read_contract.py tests/fins/test_original_read_runtime.py tests/host/test_fins_original_read_truncation_fetch_more.py tests/fins/test_fins_storage_atomicity.py tests/fins/test_fins_storage_provider.py tests/fins/test_storage_asset_filename_contract.py tests/fins/test_fins_read_runtime.py tests/fins/test_read_runtime_semantic_ownership_guards.py tests/fins/test_processor_read_consistency.py tests/fins/test_processor_registry.py tests/fins/test_financial_read_contracts.py tests/fins/test_fins_ingestion_runtime.py tests/fins/test_cn_annual_report_source.py tests/fins/test_sec_pipeline_download.py tests/documents/test_processors.py tests/tools/test_combined_tools_acceptance.py tests/host/test_toolruntime_truncation_fetch_more.py tests/runtime/test_scene_prepare.py -q --cov=dayu.fins --cov-report=term-missing --cov-report=json:workspace/tmp/public-original-read-r1-r3-20261020/coverage/coverage.json
```

条件性检查：当前保持 `tool_discovery.json` 无新增 limit 键；若实施事实要求 JSON 变更，除向总控报告外，必须把 `tests/runtime/test_config_loader.py` 同时加入上面第二组回归和合并 coverage 的实际 argv，并单独保存该文件结果；不能只改 JSON/默认值却漏掉 loader 精确契约断言。该条件发生时的单文件命令为：

```bash
source .venv/bin/activate
python -m pytest tests/runtime/test_config_loader.py -q
```

实现回执按**每个新增/修改生产文件**列出覆盖率及未覆盖行，单文件目标 ≥80%；新增取消共享模块、storage/domain 文件也计入。低于目标先补有意义的 owner 行为测试，不排除生产行、不缩小分母；确有既有巨大模块缺口须给总控明确证据和补测决定，不能将目标改成全包平均。process child 覆盖若是必要分支，按 tests README 的独占 `concurrency=multiprocessing`/`parallel=true`/`COVERAGE_PROCESS_START` 方案用 `coverage run -m pytest -p no:pytest_cov` 和 `coverage combine --keep` 保存父子原始数据；不用双 collector 冒充覆盖。所有改动必须通过 pyright，触及的既有错误一并修复，不忽略或新增 suppress。

### 6.3 实际输入 API 复验（开发树 gate）

实现阶段提供只读验收程序 `utils/verify_public_original_read_r1_r3.py`（此轮不创建）。其读取内容的唯一入口是 `DefaultFinsRuntime.create(...).get_read_runtime()`；不能直接构造仓储、读取私有 Source path 或运行临时业务 parser 来替代 API。指纹比对可独立只读原文件 bytes，但只是对 API 返回身份的外部验真，不产生产线版本语义。

**运行目录隔离是硬要求。** storage published reader 也会申请 publication lock，不能仅凭 create_directories=False 就保证不触及调用方目录。先把六批 plan/cold 回执所需 source 文档完整文件集（包括主件、附件、既有 PDF/Docling 和同 source 的 sidecars）及其必要 identity/meta/manifest/公司路由、列表导航元数据复制到本库 `workspace/tmp/public-original-read-r1-r3-20261020/input-workspace/` 或系统 tmp；只读接口复现所需依赖，不复制调用方业务输出/对话/config/secrets，不拷贝 staging/locks/jobs。复制保持原 bytes，不裁改 meta、manifest、primary 或 revision 来让测试通过。校验所需仓储依赖时如有缺项，仅补拷贝确证相关的精确依赖；无法形成有效公开 workspace 则记录验证 blocker，不用 fixture 替换真实输入或篡改完整性规则。

验收程序的 `--source-workspace` 参数只用于上述 allowlist 只读复制/指纹核验，实际 runtime 的 workspace 必须是本地副本；`--evidence-root` 只读历史计划/回执。程序为此次验收分析辅助，不是待发布业务 API。建议实际命令固定为：

```bash
source .venv/bin/activate
python utils/verify_public_original_read_r1_r3.py --source-workspace /Users/leo/workspace/portfolio-manager-v2/workspace --workspace-root "$PWD/workspace/tmp/public-original-read-r1-r3-20261020/input-workspace" --evidence-root /Users/leo/workspace/portfolio-manager-v2/orch/workpapers/g0-refactor-implementation-20261020 --output-dir "$PWD/workspace/tmp/public-original-read-r1-r3-20261020/development-api"
```

必要回执及断言：

- 保存实际 Python/module 路径、commit/dirty diff 指纹、相关模块 SHA、依赖版本、命令/开始结束/退出码、每次参数、完整返回/错误、冷暖时间/RSS和原件/副本 before-after SHA/size。cold 指新 runtime 无相关 entry，不声称清除了 OS cache。全部响应必须可取回，历史证据目录不写新文件。
- 重放六批 53 次原公开调用的导航/读取语义，比较正向能力而非要求新增字段后 JSON hash 相等；原 not_supported 仍单独记录。新增四 API 对七份原始锚文件及 TSM 附件验收，原例包括 ATAT `fil_0001104659-26-044551`、FUTU `fil_0001104659-26-043451`、ASML `fil_0001628280-26-011378`、MSFT `fil_0000950170-25-100235`、AAPL `fil_0000320193-25-000057`、TSM `fil_0001564590-22-029201`、YUMC `fil_0000950170-25-014954`；A/H IDs 直接取第三批计划，禁止手抄重造 ID。
- 按 `targeted-original-anchors.json` 的原文片段和 QName 独立回读；新坐标按本文约定验证，不能默认历史锚就是新 API 正确输出。facts 查询前必须实际调用公开 `read_original_structure`，从原始 namespace 声明/定义处作用域取得 URI，必要时沿 span 公开回读；保存发现返回、绑定位置、查询参数及结果的证据链，不能把历史 QName 的 prefix/年度或夹具硬编码 URI 当发现结果。ATAT/FUTU/ASML 用途组只断言原文/属性/context，MSFT 三 TradingSymbol 原样保留及不同 context，不输出准入结论。
- MSFT/ASML/TSM 原文逐页拼接覆盖全文，长度/hash 绑定实际资产；包含 5,000 之后的范围和 EOF，证明不再有未声明窗口删减。大文档至少 ASML 24,864,734 bytes 冷暖/分页读完，记录 RSS/耗时并核缓存复用；不预设未经测量的性能 SLA。
- TSM 明确分别选择 `tsm-6k_20220812.htm`（34,492 bytes，SHA `4e93053855798383ab0c98b5e03f1f5183bf1eed7707c9639738c7192b34d6b1`）与 `tsm-ex991_18.htm`（10,997,629 bytes，SHA `63942e99dfe4e4417ba356e434f84b2c50c3d4b5bbae1a3f8d86f8b9557525dc`）。从主件返回位置回读 `href="tsm-ex991_18.htm"` 和链接文字，并从附件读取其开头；reading primary 仍是附件，身份不能贴成原始主件。
- 新方法同一 runtime 重复调用、close 后新 runtime 复读均一致；版本变更/故障注入只用本库隔离 Fs 测试资产，绝不改真实原件、历史证据或调用方目录。所有 runtime 必须 finally close；结果不能只有 stdout 的 pass。
- 本节公开 Python 原文分页回执不能替代 §6.1-8 / §6.2 的真实工具经 Host 截断与 `fetch_more` 联合回执；两者均为同一 slice 的验收要求。

### 6.4 Merge 后 live sync 是另一个 gate

开发树上述验收通过，仅证明源码树版本通过。本轮不授权 merge，不提前安装/改 live。总控完成代码审核、必要修复/复审、draft PR 交付与 final closeout 后，等待另获 merge 授权。

merge 完成后由总控按任务书 sync live，核 `command -v dayu-cli`、CLI 安装入口和 `/Users/leo/.local/share/uv/tools/dayu-agent/bin/python` 的 distribution/direct_url/module 指纹一致，并以该绝对 Python 从**不将本库源码放入 sys.path 的目录**运行验收程序保存的副本，避免脚本目录/PYTHONPATH/editable import 冒充安装验证。例如把验收程序只读复制到本次系统 tmp，清除 PYTHONPATH 后运行同一参数/断言，结果落本库 `workspace/tmp/.../live-api/`，保存同步命令、merged commit/wheel/module 证据及退出码。复验仍经公开 runtime、仍使用隔离真实输入副本，不新下载/上传/预处理。不能以测试通过或 wheel 版本号没变替代实际模块版本核对。

## 7. Residual risks、未覆盖项与交接

本轮没有实现结果可宣称 fixed。下表为计划阶段分类；`covered by later approved slice` 仅指本计划获审核批准后唯一实施 slice 的必需工作，实施/审核回执必须按实际结果更新，不能把范围内缺陷仅靠分类带过 gate。

| 风险/未覆盖项 | 分类 | owner / destination 与是否阻塞 |
| --- | --- | --- |
| R1–R3、实际 hash 暴露、原文定位、分页、owner contract 和生命周期尚未实现/验证 | covered by later approved slice | Dayu implementation owner → 本计划唯一 slice 及完整 code review；当前不能宣布修复通过。 |
| P1/P2/P4 的 Host 联合续读、typed 角色直接消费者迁移及 prompt/schema 实际装配尚未实现/验证 | covered by later approved slice | tools/storage/pipeline/config 指引 owner → §5/§6 的同一实施 slice、实际回执及 code review；测试失败仍阻塞验收，不能以模型遵循指令或旧夹具成功替代。 |
| concepts 数量预算、暖 identity 取用及固定 Host 文本预算不变量的具体实现 | covered by later approved slice | runtime/provider owner → implementation 参数成本决定必要具名 concepts 上限并验证；code review 核 active borrow 的 full snapshot identity 与有效预算。保持公开参数成本内的最小实现，不新增调度/限流系统；这些局部代码判断不是新计划机制。 |
| malformed 原文、namespace/target/continuation 歧义可能被错误当完整事实；大节点/祖先导致输出膨胀 | covered by later approved slice | 原文 processor owner → partial/error/有界 preview 合同与对抗测试；实际输入若无法交付目标所需信息，属于验收 blocker，不能降格为已接受限制。 |
| ASML 等大件的全量解析/索引内存与速度未经测量；LRU 是 entry 数上限，不是总内存硬上限 | covered by later approved slice | read runtime owner → 大件冷暖/RSS回执、分页/缓存/取消测试和 code review。禁止用静默裁剪降负载；是否需调整内部表示由实际测量决定，无证据不新增全局 cache manager。 |
| 不执行 CSS/脚本，不构建浏览器布局，不处理跨文件 inline document set，不作 XBRL transformation/业务解释 | assigned to later work unit | Fins capability owner → 有新需求时独立 work unit；本轮明确 unknown/未解析及原始证据，保持已确认非业务解释范围，不妨碍当前原始文件目标。无承诺自动创建 issue。 |
| direct Python 在既有同步 storage/第三方阻塞段无法即时物理中断 | assigned to later work unit | Fins/runtime owner → 若未来要求硬时限再单独设计；本 slice 必须做到检查点取消、资源收口及 Host process accept 屏障，不将这个限制用来豁免泄漏/late result。 |
| 调用方 metadata 没有独立原始主件角色；不能仅从 storage primary 自动知道原始主件 | assigned to later work unit | ingestion/storage owner → 若未来要求机器保证原始提交主件角色，再基于 source provenance 设计；当前显式选件与原始 href 回读已经满足目标，不需要 schema 迁移。 |
| 开发树尚未验证，官方样例只保留历史证据，完整复制依赖和 actual verifier 仍待落实 | covered by later approved slice | validation owner → §6 开发树 gate；真实样例失败或输入不可取得必须保持 gate 未通过。 |
| merge、live 安装版本与安装环境能力尚未验证 | requiring new issue or explicit user decision | 总控 → 用户另授 merge 后的 §6.4 live sync/实际 Python 复验；当前 draft PR 边界外，不提前写 live-pass。 |

当前没有需要用户重新决定的 owner/scope/API blocker。下一步由总控对本版实际变更和裁决 P1–P4 安排双路受影响面复审并裁决，未放行前不实施；不重扫未变全仓或重开已确认目标。本文不替代总控的审核裁决、测试回执、代码审核或 PR/live 交付记录。
