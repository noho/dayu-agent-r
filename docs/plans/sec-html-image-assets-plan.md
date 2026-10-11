# SEC HTML 图片依赖修复实施计划

## Gate、范围与交接

- Work unit：`sec-html-image-assets`；gate：`fix`（plan review 后的计划修订）；状态：四项 accepted finding **已修复待 re-review**，未实施；不代表总控放行。
- Provider：`gpt-6-sol`；分支：`fix/sec-html-image-assets`；base：`297bfbbc67b7d7468e3dfb6669a3385c4dd10d18`。
- Binding scope / design alignment：以 `docs/plans/sec-html-image-assets-goal.md` 为唯一已确认目标契约；`docs/plans/sec-html-image-assets-control.md` 负责 gate 状态。没有另外的设计文档；本计划细化契约，不扩大五项成功信号。
- 用户已确认目标、非目标、边界及五项成功信号，授权总控按 Gateflow 自动推进至 final closeout。本 fix worker 仅修改本文及 `docs/plans/sec-html-image-assets-plan-fix.md`；不实施、不修改 goal/control/review、生产代码、测试或业务 workspace，不启动 Agent、commit、push 或开 PR，不 clear 会话。
- Preflight：本轮重读根 `AGENTS.md`、Gateflow、已确认 goal、当前 plan、两份原 review 与 `docs/reviews/plan-review-20261011-183624.md` 总控裁决；只补读 A1 mock/断言、A2 skip、HEAD 与资产名 owner 的必要代码段。当前分支为 `fix/sec-html-image-assets`，已有未跟踪 goal/control/plan/review/validation artifacts 为上游状态，保留原样；不重复全仓阅读或 baseline 测试。
- Changed files / artifact paths：`docs/plans/sec-html-image-assets-plan.md`、`docs/plans/sec-html-image-assets-plan-fix.md`。
- Validation（本 gate）：文档结构/范围、必要条目与全文一致性、两artifact whitespace检查退出0；6个合成标准库URL规则断言通过。tracked/index diff为空，goal/control/三review/remote-preflight共6份受保护artifact哈希前后相同。原plan的CLI/README/preflight证据沿用既有artifacts；本轮未运行实现测试、coverage、pyright或真实下载，不将计划内命令记作已执行，也不把上游baseline pass当修复或re-review pass。
- 本 gate decision：保留 **1 个行为 slice S1**、版本/指纹/事务/rebuild 与真实 CLI 矩阵；修订依据为总控上述裁决。下一未完成入口为 `re-review`，由总控登记/派发，本 worker 不改变 control 或通过 gate。

## 目标、动机与成功信号

动机成立。文件内容中存在 `<img src>` 引用，正式下载清单却没有图片；仓储对已声明文件的完整性检查不能证明尚未声明的 HTML 依赖齐全。这是 SEC 下载集合契约与增量状态机的问题，不能在读取工具、渲染、processor 或调用方目录里补偿。

已确认目标保持如下：

1. 正式下载选择的 SEC HTML，其实际引用且属于同申报的图片进入正式下载集合，下载、登记并能通过来源仓储寻址；规则不依赖 ticker、accession、样例文件名或“15 份”集合。
2. 既有漏图来源有明确补齐路径，复用下载版本、远端描述符指纹、文档版本及 processed 重处理规则。
3. 所有接受 HTML 的图片依赖均必要，不判断其是否财务表、logo 或演示页。发现或下载失败不能发布新的完整来源；既有 publication 必须保留。
4. 独立临时 base 验证两个真实 TSM 实例的新下载、正式旧版本来源的增量补齐、仓储/文件/hash 一致、版本/指纹、重复与失败诊断；受影响测试、pyright 通过。
5. 总控完成后续 gate，交付修复 commit、新 draft PR、双路 reviews/裁决、验证证据、风险和实际 CLI 的启用/补齐方法。S1 只为这些 gate 提供可验证代码与证据，不能把 plan 交付称为已实现。

非目标与范围边界：

- 不是通用爬虫或解析器：只给本轮既有选择逻辑决定发布的 HTML 补直接图片依赖，不追踪新 HTML、外站、跨申报、CSS/脚本或图片里的链接，不做 OCR、财务数值解析或图片业务分类。
- 保留现有 primary/XBRL/exhibit/同 filing HTML 的选择及 6-K/SC13 筛选规则，不扩大 HTML 候选集合，不把目录中所有图片拉入。
- 不新增图片数据库、独立 manifest、图片 migration、下游 fallback、兼容 shim、包版本发布或新 CLI 参数；不改其它 provider、Host/Engine/Service/UI 层边界。
- 不为旧 fixture 保留错误的 COMPLETE 无版本跳过行为。旧下载来源补齐是已授权的下载契约升级，不是旧 schema 兼容读取；本计划不改 storage schema。
- `/Users/leo/workspace/portfolio-manager-v2/workspace` 及原证据目录只读，本 slice 无需再读它们；不得读调用方其它业务文件。所有真实下载与故障注入只操作全新临时 base，不能手工补文件或修改 metadata。

## 第一性原理判断与直接代码证据

| 直接证据 | 判断与必要设计 |
| --- | --- |
| `sec_downloader.py:list_filing_files` 仅生成 primary/XBRL/HTML descriptors；`extract_same_filing_linked_html_files` 仅处理 `a[href]` | 缺失依赖事实的 owner 是 SEC downloader；新增有限的图片发现能力，不能把图片强行当 exhibit 或 HTML 链接 |
| `sec_download_filing_workflow.py:run_download_single_filing_stream` Phase A 使用 `_can_skip_fast(...) or "integrity_complete"` | 旧下载版本被 fallback 绕过，必须删除 fallback，使 COMPLETE 与当前下载契约同时成立才可跳过 |
| 同函数 Phase B 在 identity recheck 后直接跳过 COMPLETE + 非 overwrite | 只提升版本或只修 Phase A 会在这里再次丢掉补齐结果；Phase B 必须遵守同一版本/指纹资格 |
| `sec_pipeline.py:_can_skip_fast/_can_skip` 已调用 `has_current_download_version`；`sec_download_state.py:has_current_download_version` 严格相等；rejection registry 同样按版本命中 | 复用现有严格版本门控，不另加“图片已完成”布尔字段或历史版本列表 |
| downloader 的 `_PrefetchedFile` 保存 immutable bytes；workflow 先 transport、再 batch/identity/reset/materialize/upsert/commit | 从这些将实际发布的 HTML bytes 发现图片，保持网络在 batch 外；避免解析一次远端 HTML、发布另一次远端 HTML |
| `build_source_fingerprint` 排序 descriptors，仅组合 name、规范 ETag、Last-Modified，不组合内容 hash、URL 或 remote_size | 将图片 descriptor 纳入同一算法，不另造图片指纹，不把 source_fingerprint 当文件 SHA-256 |
| `sec_download_source_upsert.py` 写当前 download_version、ingest_complete、文件条目并调用文档升版及 processed 标记；`sec_safe_meta_access.py:resolve_document_version` 按 fingerprint 是否改变升版 | 保持该 owner 和既有升版规则；新增依赖集合一般改变指纹，版本标识变化本身不强制内容升版 |
| `sec_rebuild_workflow.py:rebuild_single_local_filing` 没有远端下载，却将 `pipeline_download_version` 写入成功 meta；`_fs_source_document_core.py` 的 update 将请求 meta 合并到同 batch 的既有 meta | 这是同一下载契约的另一写入入口，必须停止本地 rebuild 授予当前下载版本；只由正式下载认证依赖集合，metadata-only rebuild 保留原下载版本 |
| blob/source 仓储接受单组件文件名，source snapshot/manifest/opaque revision 与 batch 同版发布 | 直接图片复用正常来源资产；不把多组件路径交给仓储，也不按 basename 偷偷合并不同资源 |
| `test_sec_earnings_repair.py:_payload/_SecNetwork.respond/_assert_registered` 仅允许 cover/exhibit，三份真实 META cover 分别引用 `meta-20240201_g1.jpg`、`meta-20250129_g1.jpg`、`meta-20260128_g1.jpg` | 新下载契约必然触发这些实际 logo；迁移该测试的 mock 与完整集合断言，不修改真实 HTML/manifest 或用生产筛选特例避开图片（SECIMG-A1） |
| `sec_pipeline.py:_can_skip_fast` 要求非空 fp；`_can_skip` 在当前版本时允许完整远端集合等价；`SecDownloader._http_head` 元数据失败返回 None | 空 fp 状态必须服从新阶段顺序，先 base GET/发现，再等价晚期 skip；保留 optional HEAD 和既有指纹规则，不追加元数据修复（SECIMG-A2） |
| `docs/validation/sec-html-image-assets-remote-preflight.json` 两个 HTML 的远端/本地 hash 相同；2019 有 17 引用/15 去重，2025 有 12 图；只抽查 5 张图片 GET 200 | 足以确认修复动机，不能提前声称全部远端图片可用；全部获取是 S1 真实验证的一部分 |
| 指定 editable `dayu-cli` 的真实 `download --help` 支持 `--base/--ticker/--forms/--start/--end/--overwrite/--rebuild`，没有 accession 参数 | 沿用现有按公司/表单/披露日下载；同日其它匹配申报可被正常处理，不能加样例专用 selector |

不采用“只升 download_version”“统一要求 overwrite”“在读图时补文件”或“先按图片名筛财务页”：前两者不能修复两个无版本 COMPLETE 跳过点，后两者破坏依赖 owner 与成功语义。

## 语义 owner 与公开契约

| 语义 | 唯一 owner / 输入与输出 | 本次变化 |
| --- | --- | --- |
| 被选 HTML 集合、6-K 是否接受、preferred primary | 既有 downloader 选择与 workflow 的既有 `_precheck_6k_filter` / prepared primary reconciliation | 规则不改，图片发现放在接受分支内 |
| HTML 的直接图片候选、srcset 语法、首个 base 真源、同申报地址、去重/命名、发现错误 | `sec_downloader.py` 的有限 HTML 图片 extractor、规范化 helper 和新 `SecDownloader.list_filing_image_files` | 从实际预取 HTML bytes 产生全部候选的图片 descriptors；三种输入共用一个 URL/name owner，无下游重算 |
| UTF-8 正文解码 | 既有 `dayu.fins.processors.source_text.decode_source_bytes` | 新 extractor 直接复用该严格解码能力；不另立 ignore/replace 或字符集猜测规则 |
| 单文件网络/重试/UA/限流/取消、非空 payload | downloader 既有 HEAD、`prefetch_files_stream`、typed events | 图片走相同 transport；不加绕过限流的裸 HTTP 路径 |
| 能否跳过、补齐、失败及最终 complete | SEC filing workflow；版本相等判定复用 `has_current_download_version` 和 `_can_skip_fast/_can_skip` | 两个 COMPLETE 门均要求当前契约资格；任何必要失败禁止新 complete |
| remote descriptor fingerprint | 既有 `build_source_fingerprint` | 完整 descriptor 集合包含图片，算法不改 |
| download_version、document_version、first_ingested_at、processed 重处理 | SEC 版本常量、正式下载 `upsert_downloaded_filing_source_document` 与 `resolve_document_version` | SEC download_version 升为 `sec_pipeline_download_v1.3.0`；本地 rebuild 不再授予新下载版本，其余复用 |
| URI、size、SHA-256、source meta/files、manifest、revision、原子保留旧 publication | 既有 `DocumentBlobRepositoryProtocol`、`SourceDocumentRepositoryProtocol`、`BatchingRepositoryProtocol` | 无接口/schema 变化；图片作为正常 blob/source 文件 |
| 文件失败与 filing 失败投影、typed summary、CLI 诊断/退出码 | 既有 downloader event → download event mapping → SEC adapter → download summary → CLI | 传递 owner 给出的结果；不在 adapter/CLI 推断缺图或修改完成状态 |

### Downloader 新增接口

在 `sec_downloader.py` 增加有实际依赖发现语义的方法，使用直接参数：

```python
async def list_filing_image_files(
    self,
    *,
    cik: str,
    accession_no_dash: str,
    html_payloads: Mapping[str, bytes],
    existing_files: Sequence[RemoteFileDescriptor],
    include_http_metadata: bool,
    cancellation_checker: Callable[[], bool] | None = None,
) -> list[RemoteFileDescriptor]:
    ...
```

- `html_payloads` 只包含已接受 filing 的既有待发布 HTML 文件名及同一次 `_PrefetchedFile.content`；不读取 published HTML，也不重新 GET HTML。
- `existing_files` 是本轮 base descriptors，用于验证 HTML 名称属于该集合及避免与既有资产冲突；返回值仅为新增、排序、去重的图片 descriptors，输入不原地修改。
- archive root `A` 由同一 `ARCHIVES_BASE`、标准化 CIK 与 accession 构造，是允许地址边界；每份 HTML 的文档 URL `D` 由 `A` 加其合法编码文件名得到。HTML 首个 `base[href]` 决定相对候选的解析基准，不能把允许边界误当解析基准或让调用方决定外站根地址。图片无需在 index.json 中出现，HTML 实际候选是必要依赖的真源。
- 返回 descriptor 字段仍为 `name/source_url/http_etag/http_last_modified/remote_size/http_status/sec_document_type/sec_description`；图片不伪造 document type/description，后二者为 `None`。
- `include_http_metadata` 与当前 filing listing 使用同一取值：`previous_meta is not None and not overwrite`。开启时每张图片复用 `_http_head`；失败或缺少 HEAD 元数据不等于 GET 成功/失败，沿用既有 optional metadata 语义。实际 GET 仍必要，不能只因 HEAD 200 就宣布下载成功。
- 新增模块内有限 extractor、srcset 解析与共享 URL/name 校验 helper；不新增通用解析框架、公开候选 schema、callback、factory 或 extra payload。增加有限的 `SecHtmlImageDependencyError`，字段为 `html_name: str`、`reason_code: Literal["html_image_decode_failed", "html_image_reference_invalid", "html_image_asset_collision"]`、`safe_message: str`，不携带 UA、原始正文、任意外部 URL 或本机路径。srcset/base/子目录诊断均使用 `html_image_reference_invalid` 加下述明确安全说明，不扩错误字段。函数/方法/类遵守中文完整 docstring、严格类型与中文意图注释。

### 直接候选与有限 srcset 契约（SECIMG-001）

1. 用标准库 `HTMLParser(convert_charrefs=True)` 收集 `img[src]`、`img[srcset]` 和遍历时处于 `picture` 内的 `source[srcset]`；标签/属性大小写、引号、自闭合与 HTML entity 沿 parser 语义。`picture` 的进入/退出只用于限定 source 的图片上下文，不计算 DOM 布局。picture 外的 source（如 video/audio）不扩为媒体下载；不增加其它 image 标签、CSS/JS 递归或浏览器。先收集该文档的候选和首个 base，再统一解析 URL，因此出现在图片后面的 base 也影响该文档相对候选。
2. img 同时有 src 与 srcset 时，两者取并集；picture 各 source 的所有 srcset 候选也都必要。绝不按 viewport、media、type、sizes、w/x、logo、扩展名或财务用途选择一张或丢候选。同文件、跨属性、跨 picture、跨已选 HTML 的同一 canonical URL 共用去重/name owner。src 缺席/空白与 srcset 缺席/全 ASCII 空白没有远端候选；其它非空 srcset 要么完整解析，要么 typed 失败，不能返回解析成功的前半段。
3. srcset 的空白集合精确为 ASCII space/tab/LF/FF/CR；HTML entity 已由 parser 解码一次。按位置扫描“URL token → 可选 descriptor → 逗号分隔”的有限状态，不使用 `split(',')` 后过滤。普通 URL token 扫至 ASCII 空白；token 尾部的**一个**逗号可以结束无 descriptor 候选（`a.jpg, b.jpg 2x`）；descriptor 后的逗号无需相邻空白（`a.jpg 1x,b.jpg 2x`）。允许一个最终尾逗号；前导逗号、连续逗号/空候选失败。普通 URL token 内部原始逗号（如 `a.jpg,b.jpg` 或 `chart,1.jpg`）分界有歧义，失败，不猜两张或一个文件。文件名中的逗号/空白需先用 `%2C`/`%20` 编码，先分候选再交共享 URL owner 严格解码，不能解码后再切分。
4. 每个候选最多一个 descriptor：`w` 前为十进制数字且整数值 > 0；`x` 前为正、有限十进制数，语法 `(?:[0-9]+(?:\.[0-9]+)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?`，例如 `1x`、`.5x`、`2.0x`；数值按十进制精确校验/比较（用标准库Decimal），不能用文本或float舍入判断 `1x`/`1.0x`是否重复。无 descriptor 为隐含 `1x`。同一属性的候选须是 w 组或 x 组（无 descriptor 属于 x 组）；混组、w 组缺 descriptor、重复的数值 w/x、单候选多 descriptor、零/负数/NaN/Inf、h/未知后缀、引号/括号等超出语法均失败。不同属性之间不比较 descriptor；同 URL 可以用不同合法 descriptor，最终 URL 去重。descriptor 仅验证有限语法，不参与资源选择。
5. data 是内嵌候选，不创建远端 descriptor、不发 HEAD/GET，但不能用它吞掉后续候选。有限支持为无 ASCII 空白的 `data:<metadata>,<payload>`：首个逗号是 data 分隔符，payload 内逗号/空白必须百分号编码；百分号 triplet 必须合法，不解析/解码图像内容。独占整个属性的无 descriptor data，或以空白隔开 descriptor 再用逗号结束的 data（`data:image/png;base64,AA== 1x, a.jpg 2x`）可确定分界。data URL 尾逗号或额外原始逗号（`data:..., a.jpg`、未编码的 payload 逗号）有歧义即失败；不按猜测拆出/丢掉远端候选。src 中 data 仍作为内嵌内容忽略，srcset 的 descriptor/列表合法性也适用于 data 候选。
6. 以上解析不成功为 `html_image_reference_invalid`，安全说明为“图片候选列表（srcset）格式不合法或分界不明确，未发布本次来源。”，附所属 HTML 的安全文件名标签；保留 cause，不输出原属性/正文。所有实际解析出的远端候选再走同一个下述 URL、边界、名称、去重 owner；不能为 srcset 写另一套 basename/宽松 URL 规则。

### HTML base、URL 与名称契约（SECIMG-002）

1. 文档无 `base[href]` 时基准为 `D`；有时取文档顺序中**第一个带 href 属性的 base**（不是第一个校验成功的 base）。无 href 的 base 不占位；href 空串/全 ASCII 空白/无值属性按空串处理，其 `urljoin(D, '')` 为 `D`，之后的 base 一律不覆盖。src/base href先去前后ASCII空白，再检查剩余控制字符、编码分隔、反斜杠等原始不安全输入，不能交给URL parser静默消去内部控制字符；srcset先按其专门分界契约处理。href 的相对/根路径/绝对形式均用标准 URL 解析相对于 `D`，不递归相对于其它 base。保留 base 的 query/fragment 到候选解析阶段，不能预先强行替换成 archive 目录。
2. 安全 base 的 origin 与路径必须属于 `A` 的同申报边界；base 可以是同申报目录或文件，按标准 `urljoin` 的尾 `/` 规则决定相对地址。合法 `./` 与 base 中点段按 URL 解析归一化后再次检查同申报边界；编码点段/分隔、无法解析或归一化后越界均不授予安全 base。base 本身不发网络请求，也不是待存储资产。base 指向同申报子目录不立即失败；相对候选最终落入子目录时按单组件资产边界失败，根路径/绝对候选若最终为直接文件则正常处理。
3. 显式 scheme 的绝对图片 URL 以及 `//host/path`（使用 `D` 的 https scheme）独立于 base 校验；同申报绝对候选不会被外站/跨申报/非法 base 重写。其它候选，包括 root-relative、query-only、fragment-only，以有效 base 作标准 `urljoin`。首个 base 外站、其它 CIK/accession、其它 scheme 或不安全且存在非空、非 data 的相对候选时，**typed 发现失败**：安全说明“文档 base 地址不在本申报安全边界，无法解析相对图片；未发布本次来源。”，绝不回退 `A`/`D` 或采用后续 base。全部候选都是独立绝对 URL/data 时，不使用该 base；仍逐一校验绝对候选。不向外站或跨申报发 HEAD/GET。
4. URL parser 与 POSIX 路径组件共同判定 origin 和 `/Archives/edgar/data/<cik>/<accession_no_dash>/`，不能字符串前缀匹配。允许 origin 为 HTTPS `www.sec.gov`（无凭据，默认/显式 443），输出 canonical URL 统一为 `A` 加编码文件名；支持同目录相对/`./`、同申报 root、同申报绝对/协议相对。显式、可明确识别的外站/跨申报图片属于非目标，不请求；但不安全 base 下的相对候选按上一条失败，不能以“范围外”静默丢掉。
5. 先按 base 解析，再去除最终候选的 query/fragment 以确定 SEC 静态文件身份及 canonical 请求；例如 file base 上的 `?v=2`/`#part` 指向该 base 文件，不能预先丢掉。fragment-only 只有解析后确实指向 `D` 本页时不产生新增依赖；指向另一个同申报 base 文件时照常参与集合。URL path 严格校验 `%HH` 并按 UTF-8 解码一次，支持合法 encoded 文件名；拒绝编码分隔符、反斜杠、NUL/控制字符、多次编码形成的不明确路径，不使用 ignore/replace。图片候选自身的 `..`、本机盘符或不安全路径不修复为同申报文件；不能先 urljoin 丢掉其不安全证据再接受。
6. 正式资产必须是 `A` 的直接子文件及原样合法的单组件业务名，保留大小写，重新 URL 编码生成 canonical 请求。同申报子目录最终候选为 `html_image_reference_invalid`，安全说明“本申报图片引用位于子目录，当前来源资产仅支持单文件名；未发布本次来源，已有来源保持不变。”，不输出 raw URL，不取 basename、不做路径映射/schema、不改 HTML、不静默 complete。沿 SECIMG-003 总控 rejected-with-reason 裁决，无真实目录图证据时不新建目录能力目标；需要目录契约的后续样例交 SEC downloader/Fins storage owner 的独立 work unit。
7. 复用 `storage.asset_filename_contract` 的公开 `source_asset_name_collision_key` / `is_document_source_control_name` 校验，不复制控制名列表。新图片与 base/image 的 NFC/casefold 比较键冲突且不是同一 exact canonical 文件时，`html_image_asset_collision`；控制名冲突同样失败。同一 exact 文件已在 base descriptors 中时复用该 descriptor，不重复 transport/写入；所有输入形态统一按 canonical URL 去重，再按 exact name 排序。
8. extractor 复用严格 UTF-8 解码；失败为 `html_image_decode_failed`，保留 cause，不变成空引用列表。srcset/base/URL/name 任一发现失败不返回“部分完整”descriptors，也不进入 batch 发布；解析/HEAD 均使用原取消契约。

不改变现有 `extract_same_filing_linked_html_files` 的 HTML 选择行为。新方法补全正式 accepted download 的资源集合，`list_filing_files` 仍负责 base 文件选择；在该方法 docstring 明确 base 与完整资源集合的区别。只在真正发布的 HTML 上发现图片，避免拒绝分支为图片失败改变原 6-K 筛选结论。

## 精确调用、状态、事务与错误契约

### 调用与数据流

`SecPipeline.download/download_stream` → `run_download_single_filing_stream`：

1. Phase A `classify_source_integrity`；UNSAFE 原样失败关闭；MISSING 无 previous meta，其它沿既有仓储安全读取。
2. COMPLETE 且非 overwrite 时，只使用 `_can_skip_fast(previous_meta, overwrite)` 的返回值；删除 `or "integrity_complete"`。它要求当前版本及非空既有指纹。命中则本 filing 不做 listing、HTML/图片 transport 或 source mutation。
3. rejection registry、base `list_filing_files`、6-K precheck 和拒绝 artifact 路径保持现有顺序/语义。拒绝路径用 base descriptors 的原 fingerprint，不调用图片发现；不改筛选规则、注册表原因或 processed 行为。版本提升会按既有版本机制使旧 registry 重新判定，不增加其它规则。
4. accepted 分支 unconditional `prefetch_files_stream(base_files, allow_not_modified=False, ...)`，保持既有主文件空内容失败和循环结束取消检查。只从成功的 `_PrefetchedFile` 收集 `.htm/.html` payload；不使用 precheck 那次 GET、旧 published payload 或另一次 GET 进行图片发现。
5. 若 base transport 已有 `_PrefetchFailed`，不进行图片发现，不尝试指纹 skip；继续既有失败 materialization/rollback 路径。不能用缺少成功 HTML payload 的 mapping 假装“没有图片”。取消停止并交给现有 cancelled terminal，不伪造失败。
6. base transport 成功后调用新 `list_filing_image_files`，先完成三种输入的全候选解析、base/URL/name 校验、去重，以及 `include_http_metadata=True` 时新增图片的 HEAD 尝试。任一 typed 发现失败/取消先于 skip，按原终态结束；HEAD 缺元数据沿 optional 规则，不误当必要 GET 失败。将 base 与返回的新增图片组成按 exact name 排序的 `remote_files`，此后接受分支的指纹、文件集合判断、upsert 全部使用这个完整集合。
7. 把原先在 precheck 前的 accepted `_can_skip` 比较移至上述发现（含必要的 HEAD 尝试）**成功之后**；参数是完整 descriptors/fingerprint。此比较只能在 COMPLETE、非 overwrite、当前版本时跳过；旧版本不能因 base 指纹相等、集合等价或完整性 COMPLETE 被跳过。当前版本且空 fp 也必须先走步骤3–6，完整集合等价才返回 `remote_files_equivalent`；base GET/typed 发现失败先返回失败，不能因旧声明可能等价而改成 skip。保留 `_can_skip` 既有算法，不修补空 fp，不重设计远端等价规则。
8. 非 skip 时用同一个 `prefetch_files_stream` unconditional 预取新增图片，追加到原 prefetched events；不重新预取已持有的 HTML。图片包含任意内容用途/扩展名，不遍历图片 payload。传同一 cancel checker，结束再次检查。
9. 在 batch 外完成以上 transport；随后沿既有 begin → Phase B classifier/identity → reset → materialize 全部事件 → 文件失败判定 → primary/fiscal reconciliation → upsert → commit 路径。所有图片和 HTML 属于同一 filing、同一 `BatchToken`。

### Phase A / Phase B 状态表

| 状态及调用 | 行为 / 不变量 |
| --- | --- |
| MISSING | 正常选择/下载 HTML 及图片，完整成功后首次 publication；失败不创建 complete 来源 |
| COMPLETE + 当前版本 + 非空 fingerprint + 非 overwrite | Phase A 返回 `already_downloaded_complete`；source/meta/manifest/revision/文件 hash/时间不变。保留现有避免远端请求的策略 |
| COMPLETE + 当前版本 + 空 fingerprint + 非 overwrite | Phase A/B 无快跳资格。listing/既有 precheck、完整 base GET、直接候选/base/URL 发现及开启时的 HEAD 尝试先发生；成功后完整 descriptors 等价才晚期 `remote_files_equivalent`。skip 时不 GET 新增图片、不 begin、不写回 fp/meta；前置必要失败为 failed，旧 publication 不变 |
| COMPLETE + 旧版本/缺版本 + 非 overwrite | 必须进入 accepted 下载及完整集合重建，不能用 integrity_complete fallback；失败保留旧完整来源 |
| COMPLETE + overwrite | 无条件重新获取选中文档及必要图片；只替换目标，不删除未选其它文档 |
| REPAIR_REQUIRED | 保持既有 selected repair 授权、preflight 与 unconditional replacement；声明图片的物理缺失由 storage classifier 同源发现 |
| UNSAFE | 保持现有 typed preflight failure、零 source reset/blob/upsert；不把本任务升级为修复 unsafe 工作区 |
| Phase B identity 与 Phase A 不同 | rollback、丢弃该轮 HTML/图片/指纹，按既有 `_MAX_SOURCE_IDENTITY_ROUNDS` 从 Phase A 重试；不混合两轮结果，不改预算 |
| Phase B identity 相同、COMPLETE、非 overwrite | 只有再次 `_can_skip_fast(previous_meta, overwrite)` 有返回值才跳过；不得无条件 `integrity_complete`。相同 identity 保证 Phase A 的 previous meta 属于同一 publication，无需增加 staged meta 兼容读取接口 |
| 竞争 writer 已发布新版本且 identity 改变 | 当前 worker 必须先重试；新 Phase A 可按当前完整版本跳过，保留 winner 的整套 publication |
| 竞争 writer 只发布旧版本且 identity 改变 | 重试后仍补齐，不能因为 winner COMPLETE 放弃升级 |

Phase B 的跳过原因使用现有 `_can_skip_fast` 原因与安全文本，不保留“无版本也完整”的语义。源仓储 COMPLETE 仍仅代表当前声明文件的物理一致，SEC 当前下载契约由版本资格负责；不要求 storage 学会 SEC 图片解析。

SECIMG-A2：当前版本但空 fingerprint 是明确测试的边缘输入，不是新增元数据修复目标。它的晚期 skip 晚于完整 base GET 和依赖发现（含开启时的 HEAD）；发生过前置请求仍可以是 skipped，不能断言零 transport。完整集合不等价时继续图片 GET/正式发布；必要 base GET 或发现失败时 failed、保留旧 publication。HEAD 元数据不可用沿既有 optional 语义；如果等价比较在缺少 validators 时仍成立可 skip，不引入 HEAD 必须成功的新资格。6-K precheck 顺序/拒绝分支仍不变。旧版本/缺版本连该远端等价跳过也不满足版本资格。

### 本地 rebuild 的版本认证边界

`SecPipeline._rebuild_download_artifacts` → `sec_rebuild_workflow.rebuild_download_artifacts` → `rebuild_single_local_filing` 不执行远端依赖发现/GET，不能产生新的下载集合认证。因此：

- 删除这两级 rebuild 函数的 `pipeline_download_version` 参数、传递及相关 docstring 项；删除 `SecPipeline` 调用中的对应参数，更新直接调用测试。
- 从 rebuild 的 `meta_payload` 中删除 `download_version` 写入，不改成 `previous_meta.get(..., current_version)` 或旧值 fallback。仓储现有 update merge 保留 staging 内已有字段，字段原先缺席则继续缺席。版本真源始终是最近一次正式下载；不新增 storage API/schema。
- rebuild 的本地文件/指纹/文档版本保留及财政字段重建仍沿原规则；不增加网络、图片解析、processed mutation 或新的失败类别。
- 旧版本经过新代码 rebuild 仍为旧版本，之后普通 download 必须补齐；当前版本经过 rebuild 保持当前版本。这个改动防止同一下载版本真源漂移，属于成功信号2/3的必要条件，不是新的 rebuild feature。

### 失败与事务保留

- 发现错误：workflow 在 begin 前捕获 `SecHtmlImageDependencyError`，产出一次 `FILING_FAILED`，`status="failed"`，完整 filing 身份/日期、明确 `reason_code` 和安全业务说明；说明引用所属 HTML 文件名可用 JSON 转义标签表达，不能输出原文、原始不安全 URL 或 UA。不写 source meta、manifest、版本、processed 标记或 rejection registry，不把它归类为 6-K filtered。
- 图片 GET 的 HTTP/timeout/connection/0 字节：复用 `_PrefetchFailed` → `FILE_FAILED`（name/source_url/reason）→ filing `file_download_failed` 与 `failed_files`。不能捕获后丢掉图片 descriptor、标记 optional、跳过该资产或用旧图片填充新集合。
- 文件失败定位：现有 `_log_filing_download_result` 只记失败数，不能假设 operator log 已保留失败图片名。在 downloader `materialize_prefetched_event` 的 `_PrefetchFailed` 分支，从同一个 typed failure 记录一次安全 warning，至少包含 JSON 转义后的 exact 文件名、reason_code 和现有安全 reason_message；不记录 raw URL/HTTP headers/原异常文本。这是原文件失败事实的日志投影，不新增错误分类、完成状态或公开 schema。
- HEAD 没有 validators 不构成图片成功证据；正式 GET 成功且非空才能 materialize。图片内容按既有 transport 保存原始 bytes，不增加 OCR/图像解码/财务分类。
- base 或图片文件失败：沿既有 batch rollback；无 upsert/commit；旧 source meta、文件声明/bytes、manifest、revision、document_version/download_version、首入库时间及 processed 状态均不变。新来源保持 MISSING。
- reset、blob store、primary/fiscal reconciliation、upsert 等既有 publication 前异常：沿 finally 回滚，保持同样 old-or-new 契约；不得在 published tree 上直接删除旧文件再下载。
- 保持 commit_token 在 commit 前从 caller token 移走的生命周期规则，commit 内异常由 storage owner 恢复，caller 不二次 rollback。不可替换 batch 实现或扩大事务范围。
- 取消：沿现有协作检查与 terminal 规则；新增解析循环、HEAD、图片 prefetch 均传递同一 checker，取消后不标 downloaded/complete。验证新增步骤的 begin 前取消保留旧 publication。
- 文件事件延续既有含义：materialize 事件只说明 staging 写入；只有 batch commit 成功后的 `FILING_COMPLETED(status="downloaded")` 表示 publication 成功。业务 RESULT/CLI 计数只消费同一 filing 结果，不重算文件树。
- CLI 公共诊断保留现有固定前缀 `Fins download diagnostics: ` 和互斥计数。图片 GET 失败的公共 filing 类别仍为 `file_download_failed`，文件名/具体 transport 原因在原文件事件及 operator log；发现失败传递新的明确类别。CLI 现有安全摘要可能使用通用文案，本次不新增公开文件详情 schema。

## 版本、指纹、hash 与 metadata 契约

- 唯一 SEC 下载契约常量在 `sec_pipeline.py`：`sec_pipeline_download_v1.2.0` → **`sec_pipeline_download_v1.3.0`**。提升表示正式下载集合包含接受 HTML 的直接图片依赖及版本跳过规则；不提升 `dayu-agent` 的 `0.1.4`，不使用旧值 + 1、历史版本特判或额外完成字段。
- 只有实际正式下载完成能写入本次版本；本地 rebuild 保留最后下载的版本或其缺席状态，不能使旧漏图来源获得新版本快跳资格。
- 完整集合 `F = base descriptors ∪ deduplicated image descriptors`，调用原 `build_source_fingerprint(F)`：按 name 排序，规范 ETag（包括 weak/gzip transport 变体）及 Last-Modified；仍忽略 remote_size/source_url/content hash。图片 name 或 validators 参与现有指纹。
- 首次下载/overwrite 无 HEAD 的既有策略不变；旧来源普通升级有 HEAD，可能得到不同 metadata 的指纹。因此独立 fresh base 与 upgrade base 不要求 fingerprint 文本完全相同；每个 fingerprint 必须与该次实际 descriptors 的同一算法一致。
- file `sha256` / blob etag / size / URI 来自仓储真实写入的 bytes，HTML 保持原 bytes，不改写 `src/srcset/base`；source `files[].source_url/http_etag/http_last_modified` 来自 descriptor，不能把 HTTP ETag 当内容 hash。
- `upsert_downloaded_filing_source_document` 仍是唯一成功入口：blob-first，然后 files[]、primary、download_version、source_fingerprint、ingest_complete、opaque revision/manifest 在同一 batch 发布。完整 manifest 用仓储 canonical projection，不能手写。
- document_version：首次 `v1`；previous fingerprint 非空且改变时 `increment_document_version`；相同指纹保留原版本。版本标识不同、但完整 descriptor fingerprint 真正相同的升级只更新下载契约元数据，不强制内容升版。
- 图片补齐会扩大 descriptor 集合，正常旧→新必然指纹改变；既有非空旧指纹时版本升一次。已有 processed 则按 source upsert owner 规则标记 `reprocess_required=True`；无 processed 不为了测试创建生产 processed。`first_ingested_at`、`created_at` 保留。
- 完成后的普通重复：Phase A 当前版本快跳，不刷新 HTTP metadata/首入库时间，不换 source revision，不重复新增图片，不再次升版。当前完整来源的远端变更检查继续需要 `--overwrite`；不引入定时远端校验目标。
- 失败/取消没有新的 fingerprint/version/complete 发布；不能把 attempted fingerprint 保存进旧成功 meta。诊断仅表示本次尝试失败，旧 publication 的版本和完整性仍按旧契约存在。

## 实施 slice

### S1：正式 SEC HTML 图片集合与旧来源增量补齐

- Objective：沿生产下载入口发布 HTML 及其直接图片依赖；旧契约 COMPLETE 在普通增量下补齐，失败保留旧 publication。
- Expected outcome：同一实现一次通过新下载、旧来源升级、重复、故障/取消与竞争状态的 owner 验证；为两个真实 CLI 样例提供证据。
- Prerequisites：plan review 经总控接受；分支/base/scope artifacts 归属再次核验；读取本文和相关 README 当前约束。没有额外前置 slice。
- 只有 1 个 slice 的理由：发现集合、版本认证/跳过和原子发布共同决定一次下载能否称完整，拆开任一项会产生仍不可补齐或可假报成功的中间行为。范围是四个生产文件的一个下载行为，无必要按 downloader/workflow/storage 机械拆分。

Allowed files / exact allowed changes：

| 文件/模块 | 允许修改 |
| --- | --- |
| `dayu/fins/downloaders/sec_downloader.py` | 有限 img/src、img/srcset、picture/source/srcset extractor、首个 base 和 srcset 解析、共享同申报 URL/name/collision helpers、typed discovery error及上述新方法；中文契约文档与既有 typed failure 安全文件日志投影；复用 transport，不扩为通用解析器或改 HTML 候选选择 |
| `dayu/fins/pipelines/sec_download_filing_workflow.py` | 修 Phase A/B 跳过；accepted branch 从实际预取 HTML 调 discovery、追加图片 prefetch、使用完整集合指纹；发现失败事件、取消传播；复用既有 reset/materialize/upsert/batch 生命周期 |
| `dayu/fins/pipelines/sec_pipeline.py` | 提升 SEC download_version、删除 rebuild 调用的版本授予参数；必要的已有 owner 文档说明。`_can_skip_fast/_can_skip` 算法无需更改 |
| `dayu/fins/pipelines/sec_rebuild_workflow.py` | 删除两个 rebuild 函数的当前版本参数及写入，复用仓储 update merge 保留正式下载版本；不改其它本地重建逻辑 |
| `tests/fins/test_sec_downloader.py` | 追加/调整 downloader 新契约测试，真实有限 parser 与 MockTransport；既有 HTML selection 测试继续保护 |
| `tests/fins/test_sec_pipeline_download.py`、`tests/fins/test_sec_pipeline_download_stream.py` | 将固化无版本 integrity_complete 的旧断言改为版本资格/重拉/owner publication 断言；固化当前版本空 fp 的 GET/发现/HEAD 在前、等价晚期 skip 与失败优先；只调整触及的 fake transport 契约，不能增加生产兼容分支 |
| `tests/fins/test_sec_earnings_repair.py` | SECIMG-A1：只在该测试文件为三份 META 原 HTML 的实际 logo URL 提供明确标识的确定性测试图片 bytes/响应，迁移 cover(+exhibit)+图片的完整集合、descriptor 指纹及逐文件 hash/size 断言；继续保护 8-K HTML选择/primary、未选来源/快跳与失败原子保留；不修改历史真实 fixture/manifest，不新增伪官方 raw 图片 |
| `tests/fins/test_sec_html_image_assets.py`（新） | 集中验证生产 downloader + workflow + 真实 Fs publication 的本任务 owner 矩阵及 CLI 诊断链 |
| `tests/fins/test_sec_html_image_assets_real_cli.py`（新） | 显式 opt-in 的真实两样例验证；baseline 官方旧入口、新的指定实际 CLI、仓储读回、hash/重复/故障；默认无环境时清楚 skip，不能把 skip 称真实验证通过 |
| `dayu/fins/README.md`、`tests/README.md`、根 `README.md` | 按下述 docs decision 只写实施后事实 |
| `workspace/tmp/sec-html-image-assets-*/` | 验证临时 roots、baseline archive/展开、纯 transport 故障 hook、命令 stdout/stderr/log/exit、coverage；不提交临时脚本/下载文件 |
| `docs/validation/sec-html-image-assets-implementation.json` | 实施验证汇总，记录可复现 argv、base/code origin、断言与证据引用，不保存 UA；总控对应 gate artifacts 另由总控管理 |

不允许更改 goal/control、storage/schema、processors、通用 direct/CLI adapter 或其它业务文件；上表的 owner 能直接满足目标。若实现证据表明需改变这些边界，停止当前修改并把证据交总控裁决，不能自行加后续 slice 或补偿 seam。

Completion signal：下列 owner 测试/coverage/pyright、两个 opt-in 真实样例全部必要验证与 docs decision 完成；所有失败如实记录且风险已分类；提交实施 artifact 给总控进入 `code review`。Stop condition：owner/范围出现阻塞问题、必要成功信号无法验证、真实 baseline 无法建立或样例被既有政策拒绝。普通外部限流只记录实情并等待可执行验证，不伪造 pass，也不修改筛选规则让样例通过。S1 worker 不跳过 review 直接创建 accepted slice commit。

## 自动化测试与断言

测试优先验证 owner，使用真实 `SecDownloader` + `httpx.MockTransport` 与共享真实 Fs repository set。只替换远端响应，不伪造 COMPLETE classifier、downloaded event 或目录文件来让结果通过；单元测试建立旧 publication 时通过正常 blob/upsert/batch API 写旧版本契约，不能直接改已发布 meta。真实旧来源则必须使用下一节的基线 CLI。

| 验证组 | 具体断言 | 对齐成功信号 |
| --- | --- | --- |
| 引用发现 | 混合大小写/引号/entity/BOM/自闭合；17 次引用样式去重但换任意 accession/名字仍成立；src+srcset+picture/source 及跨 HTML 共用 canonical 去重；logo/财务图都保留；media/type/sizes 不选择候选；picture 外 source 不下载；无图片为空；非 UTF-8 明确失败 | 1、3 |
| srcset 有限语法 | ASCII 各种空白、descriptor 后紧邻逗号、合法最终尾逗号、单无 descriptor/隐含1x+2x、整数w/有限正x、%2C/%20 文件名、data 独占/带 descriptor+远端全候选；前导/连续逗号、raw 内部逗号、data 分界歧义、错误百分号、多 descriptor/混组/重复数值/非法w/x/h均 typed 失败，不能发布前半集合 | 1、3 |
| URL/命名 | 相对、`./`、同 archive root/absolute/protocol-relative、query/fragment、有效 encoded basename 同一 canonical 资源；其它 origin/CIK/accession 不请求；目录边界前缀假匹配不接受；遍历/编码分隔/控制名/比较键冲突/同申报子目录明确失败，无 basename flatten | 1、3 |
| base 真源 | 下表最小合成 owner 用例断言完整 canonical URL 集合与确切请求；无/空/相对/绝对/多base、file/dir尾斜杠、root/query/fragment均闭合；不安全首base+相对候选 typed失败，合法绝对候选不被base重写，不发外站/跨申报请求；真实TSM不加base | 1、3 |
| Transport/集合 | 新图片缺于 index 仍下载；只有实际 accepted HTML 进入 parser；base 与图片每资源恰好一次正式 prefetch GET；不为图片再次 GET HTML；MockTransport 对 precheck 与正式 prefetch 返回不同 HTML，最终依赖必须来自后者，且仓储 HTML hash 等于后者 | 1、3 |
| 新发布 | MISSING→COMPLETE；files[]/snapshot.files/blob 列表 exact 集合等于 base ∪ 实际引用；每图仓储 `get_source(..., name).open()` 可读、size/sha256 与 bytes 匹配；primary 保持既有规则、无 orphan/missing；当前 download_version、首版 v1 | 1、4 |
| 无 src 的候选发布/补齐 | 分别用只有 img/srcset、只有 picture/source/srcset（img无src）的 HTML，源中无 fallback src；fresh正式登记所有候选，旧版本COMPLETE普通补齐全部图片，完整F指纹/hash/size/寻址成立；任一候选GET 404/timeout/空bytes均失败，fresh MISSING，upgrade完整旧publication/processed保留，不按media或descriptor另挑成功图 | 1、2、3、4 |
| 两个版本门 | 真实 COMPLETE 旧版本/缺版本不能在 Phase A 或 Phase B skip；升级结果含图片、下载计数正确。当前版本完整/非空 fp 快跳零 filing listing/transport/source mutation。用旧版本、相同指纹场景直接验证下载版本更新不强制升版；不保留旧 integrity_complete 断言 | 2、4 |
| 当前版本+空fp | 通过公开source create/blob/batch建立明确标识的边缘publication（空fp，不伪称正式下载writer输出、不改已发布meta）。请求记录证明 base GET/发现/开启的图片HEAD 在先；完整F等价→remote_files_equivalent，图片GET/begin/upsert零，source/meta/fp/revision/hash不变。base GET失败或非法srcset/base发现失败→failed而非skip，保留旧publication；F多一张候选→继续GET/publish。HEAD缺metadata单独沿optional规则断言 | 2、3、4 |
| rebuild 认证 | 通过正式旧版本 blob/upsert/batch 建来源，再走新 `download(rebuild=True)`：provider零调用，download_version仍为旧值；当前值保持、缺席保持；文件hash/fingerprint/document_version不因rebuild升级；随后普通download真实补图并写新版本。测试断言仓储merge owner行为，不能手工改meta | 2、3 |
| 指纹与升版 | 完整 descriptors 顺序不影响 fp；新增图片 name/validator 改变 fp，weak/gzip ETag/size 变体沿原算法稳定；补齐 v1→v2，first_ingested_at/created_at 保持；已有真实 processed 需重处理；重复版本/hash/revision/meta bytes 不变 | 2、4 |
| 必要失败 | 一个 img 404/timeout/0 字节，其它成功；FILE_FAILED、safe operator log 与 filing failed/failed_files 同源、无 downloaded complete；fresh 无 source，upgrade/overwrite 后 old source/files/manifest/revision/processed bytes 全保留；发现失败 begin/source mutation 为零；HEAD 无 metadata 但 GET 成功可正常发布 | 3、4 |
| 发布失败/取消 | 图片 blob store 故障、upsert 前故障、图片 discovery/HEAD/prefetch 取消，旧发布保留；batch rollback 恰一次，commit 未调用；现有 commit lifecycle 回归不变 | 3、4 |
| 并发 Phase B | Event/barrier 控制 A预取→B真实发布→A begin；B 是当前版本则 A重试后快跳，B旧版本则 A重试补齐；identity churn 预算与 typed abort 保持；不能用 sleep 或 classifier mock | 2、3、4 |
| 8-K真实HTML夹具迁移 | `test_sec_earnings_repair.py` 的三份META cover实际logo均纳入正式集合及读取hash/size，cover(+exhibit)+logo完整descriptors算fp；未选source不变，ordinary current快跳/overwrite补HTML行为保持，primary与EX-99选择不变，附件/必要图失败保留旧publication；真实fixture原hash不变 | 1、2、3、范围边界 |
| 非目标回归 | 6-K rejected 与 preferred primary、8-K EX-99、SC13、未选历史来源、rejection registry 仍符合既有业务契约；图片发现不进入 rejected artifact 分支；其它 provider 不改 | 范围边界 |
| 公共诊断 | 真实 SEC adapter/direct summary/CLI renderer 消费上述失败：互斥计数守恒，failed_documents 含目标和真实 failure category，不把图片失败归 skipped/rejected；固定诊断前缀及全失败/部分失败既有退出码；不可只检查 exit 0 | 3、4 |

### SECIMG-A1：既有 earnings 测试的具体迁移

- 只在 `tests/fins/test_sec_earnings_repair.py` 内声明小型固定 JPEG 测试 bytes，常量/注释显式标识 `SYNTHETIC` 及“确定性测试图片，非 SEC 原图”；三份原 cover 对应上述已证实 logo 文件名的显式测试映射。`_payload` 对 cover/exhibit 仍读原 raw，对映射中的 logo 返回该测试 bytes；未声明 URL 仍断言失败。不能新增 raw 图片、篡改真实 HTML 或两个历史 source manifests，也不能按生产 logo 名称写筛选分支。
- `_SecNetwork.respond` 只放行该 filing 的已声明 logo exact canonical URL；GET 返回固定 bytes，图片 Content-Type 为 image/jpeg；HEAD 的 ETag/size 与同一 bytes 确定一致，失败注入只改变 exact GET 响应。index 中未引用 `chart.jpg` 仍不下载，不能把整个归档目录放开。使用测试映射供数，不在期望断言里调用被测 extractor 反推集合。
- 以所选 base HTML 的 complete descriptor 集合 `F` 驱动 `_assert_registered`：cover-only 时为 cover + 对应 logo（MSFT无图）；含 exhibit 时为 cover + exhibit + 所选 HTML 实际图片。参数化的 before/after、untouched、retry、重复以及 fingerprint 期望全部改为这同一完整集合，不能仅放宽“至少包含cover”。逐文件从正式仓储读 bytes，核对 files[]/manifest/snapshot 的 exact name 集合、size、SHA-256；对真实 HTML 仍比原 raw，对 logo 比明确标识的测试 bytes。fp 调用原 `build_source_fingerprint(F)`，overwrite/fresh metadata=None与升级HEAD取值按该次真实调用一致。
- 8-K cover/exhibit HTML 选择和既有 primary 规则保持原断言，ordinary current快跳、overwrite补exhibit、未选source不变与 processed重处理继续保护。现有失败附件原子保留用例保留，另用 META exact logo GET 故障证明新必要图失败也保留完整旧 publication。不能为夹具改变生产下载契约或增加兼容代码。

### SECIMG-002：最小合成 URL owner 用例

仅在允许的 downloader/HTML图片 owner 测试内构造下列短 HTML，不写入历史真实 fixtures。令 `A=https://www.sec.gov/Archives/edgar/data/42/000000000000000042/`，`D=A+report.htm`，`R=/Archives/edgar/data/42/000000000000000042/`。它们只是测试身份，可换 accession/名字证明无样例特判。表中集合是**新增图片 canonical URL 全集**；成功用例还核对 `F = base ∪ 新增图片` 的 descriptors/name/fingerprint，并用 MockTransport 精确请求匹配及正式仓储读回验证。base 本身从不 HEAD/GET；typed失败用例不得出现图片GET/begin/source mutation，旧publication字节/manifest/revision/版本保持。

| 合成输入（可参数化同一短HTML） | 期望集合/诊断 |
| --- | --- |
| 无base；`img src="plot.jpg?v=1#p"`、`img srcset="./plot.jpg 1x, wide.jpg 2x"` | `{A+plot.jpg, A+wide.jpg}`，共享去重且请求均无query/fragment |
| `<base href="">` 或空白/无值href，之后 `<base href="https://outside.invalid/">`；`src="plot.jpg"` | `{A+plot.jpg}`，首个空href已占位，不能跳到后一个base |
| `<base>` 无href，随后 `<base href="./">`，再有另一个base；`src="plot.jpg"`；分别将有效base放在img前/后 | `{A+plot.jpg}`，无href不占位；全文首个带href生效，与解析位置无关 |
| base分别为 `R`、绝对 `A`、`?seed=1#old`；`src="plot.jpg"` | 各为 `{A+plot.jpg}`；支持root/absolute/query-relative base的正常URL解析 |
| `<base href="anchor.jpg?seed=1#old">`；`src="?v=2"`、`src="#part"`、`src="plot.jpg#p"` | `{A+anchor.jpg, A+plot.jpg}`；query/fragment候选先解析，不能预先丢成无图或把file base当目录 |
| `<base href="sub/">`；`src="R+plot.jpg"`（用实际R字符串）及绝对 `src="A+plot.jpg"` | `{A+plot.jpg}`，root/absolute最终仍为同申报直接文件，不因base含子目录误报 |
| `<base href="sub/">`；`src="plot.jpg"`；以及无base的 `src="sub/plot.jpg"` | `html_image_reference_invalid` + 明确“子目录/单文件名/旧来源保留”说明；不下载 `A+plot.jpg`、不flatten、不完成 |
| 首base为外站或其它CIK/accession；相对、root-relative、query-only、fragment-only候选分别测试；后面放合法base | `html_image_reference_invalid` + base不在本申报安全边界说明；后续base不补救，外站/跨申报/图片transport均零 |
| 首base为外站/跨申报/非法 `%` 编码或其它scheme；候选仅为合法绝对 `A+plot.jpg` 或 `//www.sec.gov+R+plot.jpg` | `{A+plot.jpg}`，绝对候选独立；再加相对候选则全体发现失败，不返回已解析绝对子集 |
| base的accession路径组件前缀假匹配，或base含编码分隔/点段/非法编码；存在相对候选 | `html_image_reference_invalid`，零图片transport，不归档根fallback |
| 显式绝对图片URL为其它accession（含当前accession的前缀假匹配） | 明确范围外，空新增集合，零该资源请求；不误认成同申报 |

补充同一矩阵：`base href="sub/../"` + `src="plot.jpg"` 正常归一化为 `{A+plot.jpg}`；`base href="../"` + 相对图片越出申报则 typed失败；图片候选自身 `../plot.jpg` 始终 typed失败。用例不把 base 请求当图片，也不为真实TSM插入base或srcset。

对应命令（实施后执行，先激活环境；本 plan gate 不运行代码测试）：

```bash
source .venv/bin/activate
pytest -q tests/fins/test_sec_downloader.py tests/fins/test_sec_pipeline_download.py tests/fins/test_sec_pipeline_download_stream.py tests/fins/test_sec_earnings_repair.py tests/fins/test_sec_html_image_assets.py tests/fins/test_download_failure_diagnostics.py tests/fins/test_fins_storage_atomicity.py tests/fins/test_source_manifest_contract.py tests/fins/test_storage_asset_filename_contract.py tests/cli/test_fins_commands.py
```

```bash
source .venv/bin/activate
mkdir -p workspace/tmp
pytest -q tests/fins tests/cli/test_fins_commands.py --cov=dayu.fins.downloaders.sec_downloader --cov=dayu.fins.pipelines.sec_download_filing_workflow --cov=dayu.fins.pipelines.sec_pipeline --cov=dayu.fins.pipelines.sec_rebuild_workflow --cov-report=term-missing --cov-report=json:workspace/tmp/sec-html-image-assets-coverage.json
pyright
```

coverage JSON 必须逐个检查四个实际修改生产文件的 `percent_covered >= 80`，不能只用聚合比例或排除生产行；新增/修改的非临时测试代码同样受全仓 pyright 检查。若 focused 与 broad 集合重叠可一次跑覆盖率命令并保留 focused 结果，不为凑次数重复；失败/新增改动才重跑相关检查。若 pyright 触及既有错误，修复在 allowed scope 内的错误；范围外错误带直接证据交总控，不能加 ignore/Any/排除配置掩盖。

## 真实 CLI 验证：可复现的独立临时 base

### 前提与独立性

- 实际新 CLI 固定 `/Users/leo/workspace/dayu-agent-r/.venv/bin/dayu-cli`，Python 固定本仓库 `.venv/bin/python`。记录它的 resolved executable、版本 `0.1.4`、editable distribution root、导入 `dayu`/`sec_pipeline` 文件路径及 download_version；assert 新代码来自本分支仓库，而不是只看 package version。
- 新建运行根 `workspace/tmp/sec-html-image-assets-<unique>/`，其中 `baseline-code/`、`fresh-2019/`、`fresh-2025/`、`upgrade-2019/`、`upgrade-2025/`、各年份独立的 `failure-fresh-<year>/` / `failure-upgrade-<year>/`、`evidence/` 分离。真实 source bases 开始不存在/为空，不复制原业务 workspace。
- 从 base commit 用 `git archive` 提取 tracked baseline 到 `baseline-code/`；不 checkout 当前分支、不改 editable 安装、不手工搭“旧元数据”。baseline 子进程在 baseline-code cwd，显式设置该根为 import 优先路径，使用同一 venv Python 的 `-m dayu.cli.__main__`。先断言 baseline 导入文件在 baseline-code 且常量是 `sec_pipeline_download_v1.2.0`。这是真正旧生产 CLI 入口，不是当前代码改常量装旧版本。
- SEC_USER_AGENT 仅从 `~/.zshrc` 已有 literal 在内存提取并传 subprocess env；不 source 整份配置，不执行 shell substitution，不输出/保存赋值行、值、env、HTTP headers。只允许报告 `ua_configured=true/false`。literal 不可读则真实验证阻塞，不能编造身份。

### Opt-in 验证测试接口与准备命令

新增 `tests/fins/test_sec_html_image_assets_real_cli.py` 由下列显式环境启用，缺少 `DAYU_SEC_IMAGE_REAL_VALIDATION=1` 时跳过；启用后配置/网络失败是 fail，不可静默 skip：

```bash
source .venv/bin/activate
mkdir -p workspace/tmp
SEC_IMAGE_RUN_ROOT=$(mktemp -d "$PWD/workspace/tmp/sec-html-image-assets-XXXXXX")
mkdir -p "$SEC_IMAGE_RUN_ROOT/baseline-code" "$SEC_IMAGE_RUN_ROOT/evidence"
git archive --format=tar --output="$SEC_IMAGE_RUN_ROOT/baseline.tar" 297bfbbc67b7d7468e3dfb6669a3385c4dd10d18
tar -xf "$SEC_IMAGE_RUN_ROOT/baseline.tar" -C "$SEC_IMAGE_RUN_ROOT/baseline-code"
DAYU_SEC_IMAGE_REAL_VALIDATION=1 DAYU_SEC_IMAGE_RUN_ROOT="$SEC_IMAGE_RUN_ROOT" DAYU_SEC_IMAGE_BASELINE_ROOT="$SEC_IMAGE_RUN_ROOT/baseline-code" DAYU_SEC_IMAGE_CLI="$PWD/.venv/bin/dayu-cli" pytest -q tests/fins/test_sec_html_image_assets_real_cli.py
```

测试用有类型的 helper、中文 docstring；所有临时脚本只在该运行根。测试负责读取 literal、构造子进程 env、保留两通道/退出码以及仓储核验；不新增公开验证 CLI 或要求读调用方业务数据。

### 取得正确日期及执行 argv

- 不猜披露日。准备阶段通过正式 `SecDownloader.resolve_company/fetch_submissions/fetch_json` 和生产 `collect_filings_from_table` 读取 SEC recent/history tables，按 accession 找到 `FilingRecord.filing_date/form_type/primary_document`，记录非敏感 sample descriptors。只查 2019/2025 所需官方 filings 数据，缓存/限流也在本运行根，不读业务工作区。
- 样例作为验证输入而非生产规则：`0001193125-19-110066` 包含 `d733154d6k.htm`，`0001046179-25-000082` 包含 `a2q25presentatione_6kxwm.htm`；ticker TSM，CIK 1046179，form 6-K。assert 官方 accession、日期和该次 CLI 实际结果对应，不能只按文件名推断是哪次申报。
- 每个样例执行下列精确新 argv，其中日期由正式元数据取得，base 为上面的独立子目录：

```text
/Users/leo/workspace/dayu-agent-r/.venv/bin/dayu-cli download --base <fresh-or-upgrade-base> --ticker TSM --forms 6-K --start <filing_date> --end <filing_date> --log-file <evidence/new-log>
```

- 正式旧 argv 是 `<repo>/.venv/bin/python -m dayu.cli.__main__ download --base <upgrade-base> --ticker TSM --forms 6-K --start <filing_date> --end <filing_date> --log-file <evidence/old-log>`，cwd/import root 为 baseline-code。同日其它匹配申报按现有规则处理并记录；不新增 accession 参数或修改筛选。以目标 document_id 的明确成功/失败作为断言，不仅检查全局计数。
- 子进程命令/日志/两通道每次写全新 evidence 文件，保存准确 argv、cwd、code origin、退出码与诊断 JSON；禁止 shell `set -x`、保存完整 env 或 UA。

### 必须完成的真实行为矩阵

1. **Fresh 两例**：分别在 fresh base 用指定新 CLI 下载。检查 fixed-prefix JSON 的 failed_documents/计数与 target disposition，目标必须 downloaded。通过生产 source snapshot 读取目标 HTML，先独立确认这两个真实样例无base/img-srcset/picture-source-srcset，再枚举 `<img src>`（另一简单 HTMLParser 验证器，仅验证真实样例的平铺src，不调用被测production extractor）并计算exact引用/去重集合。2019预期17/15、2025 12/12；数字只属于样例assertion，生产不得写入。若真实输入结构变化，保存证据交总控，不能按旧窄枚举假报全集；新候选/base能力由上述合成owner矩阵证明，不插入伪真实输入。
2. **旧来源播种两例**：baseline CLI 在 upgrade base 正式下载并成功后，仓储分类 COMPLETE、download_version v1.2.0、已有非空 source_fingerprint/document_version、HTML hash 与 preflight 一致，而上述图片集合全未登记/未存。必须先成立这个前置，不能通过 unlink 图片、改 meta、换新代码常量、直接写版本或复制原 workspace 来制造它。
3. **普通补齐两例**：指定新 CLI 对相同 upgrade base/date **不传 overwrite/rebuild**；目标必须 downloaded，图片全部正式可读，metadata/文件集合/hash 一致。旧→新 version 改为 v1.3.0、source_fingerprint 改变、document_version 按旧值升一次、首入库/创建时间保留、旧 primary/HTML bytes 与正常既有规则一致。真实 bases 不需要运行模型/转换来创建 processed；processed 标记由上一节真实 Fs owner 测试覆盖。
4. **哈希与可寻址核验**：用 `read_source_snapshot(materialize_files=True)` 的同版 metadata/files 和 `get_source` 读取所有图片，逐图算 SHA-256/size，assert files[]、snapshot descriptors、仓储 bytes 一致、URI 可读取；存独立逐图 hash manifest。两个 HTML 与 preflight hash 对照；五张已抽查图片与 preflight hash 对照。全部 27 图远端 GET/hash 都在本次验证，不将“抽查 5 图”写成已验证全集；若远端内容改变，保存直接证据并交总控，不强行通过旧 hash 断言。
5. **指纹核验**：保留正式 listing/discovery HEAD 的非敏感 descriptor evidence，用原 `build_source_fingerprint` 重算该次完整集合并与 published meta 一致。子进程测试级 observer 包装该函数记录其参数/返回值，原函数必须执行且结果不得改写；observer 临时文件只写 evidence、没有生产 seam。在 CLI 导入 workflow 前先包装 downloader 模块的函数，避免已经绑定的导入别名绕过 observer；baseline 子进程的 PYTHONPATH 必须仍优先 baseline-code。独立重算算法输入时同时确认图片 descriptors 确实在其中。新 fresh 没有 HEAD与升级有 HEAD的差异如实记录，不能强求两 base 指纹相等。
6. **重复**：对每个已成功 fresh/upgrade base 用同一新 CLI 普通再执行；目标 skipped/current complete。保存前后 snapshot revision/meta/files/hash/首入库/版本，逐项相等；source publication 字节保持，cache/日志/限流临时文件不误当 source 幂等对象。目标文件 transport 不再发生：同一个临时 hook 观察真实 HTTP transport 的 method/canonical URL/status，原 handler 不变，只保存该验证申报的脱敏请求事实，不保存 headers/body；检查目标 archive 的请求为零，不能假设既有日志已包含请求 URL。公司/其它同日申报只按各自正式状态断言，不承诺整个 workspace 所有运行期文件字节不变。
7. **必要图片失败、旧 publication 保留**：为每例另建 failure-upgrade base，由 baseline CLI 再正式播种。新 CLI 普通升级时只对该真实样例一张已证实引用图片的 GET 注入 404，其它网络请求照常执行生产 transport。通过子进程 `PYTHONPATH` 指向临时 `sitecustomize.py` 的 transport-only hook，包装有严格类型的 `httpx.AsyncHTTPTransport.handle_async_request(self, request)`：exact canonical image GET 返回带 request 的 404 Response，其余调用原 handler。只改变远端响应，不能改 pipeline、schema、分类器、metadata、版本、事件或 source 文件。记录 fault target/method/status/call count，避免 fault 实际未命中却宣布失败通过。移除 hook后正常升级必须成功。
8. **Fresh 失败**：独立 failure-fresh base 用同样 exact transport fault；target failed，未发布该 source。upgrade 故障时旧 snapshot/meta/files/hash/revision/manifest/版本全部保留；通过官方仓储重读验证，不能单看目录残留。
9. **真实失败诊断**：解析 stdout 和 stderr 的 fixed-prefix JSON，target 必须在 failed_documents 中，reason_category=`file_download_failed`；operator log/file event必须对应被注入图片的 `provider_http_status`。全局 exit遵守现有 all-failure/partial-failure语义，同日其它候选成功时 exit 0允许，但目标失败不得遗漏。新 complete不出现；图像故障解除后 retry/重复再核验成功与幂等。

真实验收证据在 `docs/validation/sec-html-image-assets-implementation.json` 汇总：代码/CLI来源、baseline commit/版本、样例正式日期与实际所有 argv、每模式 base、每图 hash和metadata/URI、descriptor/fingerprint、版本前后、重复/失败前后与诊断/退出码、tests/coverage/pyright、尚未验证项、原 workspace 零写入声明。UA 只记配置布尔值，不把临时下载文件或 credential 值提交 Git。

## Docs decision

已读三个 README 的当前职责/约束；本 plan 不更新它们。S1 实施后：

- `dayu/fins/README.md`：在现有下载能力/机制章节更新 accepted HTML 的 img/src、img/srcset、picture/source/srcset全候选、首个base解析及共享同申报/单组件资产边界；不安全base+相对候选与子目录明确失败，非picture source不抓媒体。说明当前版本完整性资格、空fp晚期skip的GET/发现前置、旧来源普通升级、本地rebuild保留下载认证版本及必要失败原子保留；只写稳定开发契约，不写命令、测试清单或gate状态。
- `tests/README.md`：没有单独 `Agent更新约束` 标题，开头限定为已有测试分层/运行/维护。补本任务owner矩阵（srcset有限语法、合成base、空fp失败优先、META确定性图片mock与真实raw保持）及opt-in真实CLI运行说明；强调MockTransport/真实baseline/故障注入的证明范围，以及TSM无base/srcset不能作为这些能力的真实证据，不写未执行验证为已通过。
- 根 `README.md`：修正已过时的“已有完整SEC缓存升级都必须overwrite”说明，给普通补齐的公司/表单/披露日期命令；当前版本完整缓存仍保留快跳，需要强制远端重检查时用overwrite。说明必要图片失败查fixed-prefix诊断、operator log，以及rebuild不能补远端依赖；短说明准确包含图片直接候选、同申报base、平铺限制/子目录诊断和CSS/JS非范围；不放srcset文法细节或内部模块/type/治理术语。子目录失败应保留既有来源并向维护者提供安全失败说明以进入独立资产契约需求，不能建议basename/手工补文件作为修复。
- 不改 `dayu/README.md` 或其它层README：本任务无分层/装配变化。

实际CLI启用：editable 0.1.4已指向本仓库，实施后的代码在新CLI进程加载；核验import origin与download_version，不要求无根据地升级包版本。正式补齐时用户对受影响ticker/forms/date使用普通download；本work unit只在临时base执行，不能对原业务workspace直接跑补齐。后续finalcloseout附准确命令、必要图失败说明、以及可选overwrite用途。

## Goal alignment、最小性与 residual risks

本次 plan fix 的 finding 状态是 worker 自检的 **已修复待 re-review**，不是 review 最终验证或 gate pass；依据 `docs/reviews/plan-review-20261011-183624.md`，没有改写其裁决或 finding 状态。

| Finding / decision | 初步修复状态 | 本文修订证据 / 实施owner |
| --- | --- | --- |
| SECIMG-A1 / accepted | 已修复待 re-review | S1 allowed及focused纳入earnings文件；专节定义META mock、完整F/hash/size/fp和8-K原子保留；owner为该测试的明确供数/断言及SEC下载契约 |
| SECIMG-A2 / accepted | 已修复待 re-review | 调用步骤5–7、状态表/专段及owner测试规定GET/发现/HEAD先于等价skip、必要失败优先且不修空fp；owner为SEC filing workflow |
| SECIMG-001 / accepted | 已修复待 re-review | 直接候选/srcset有限契约、共享URL/name及无src发布/升级/失败矩阵；owner为SEC downloader，完整发布仍由workflow/upsert持有 |
| SECIMG-002 / accepted | 已修复待 re-review | 首个base/URL专节及最小合成完整URL矩阵、不安全basetyped失败/绝对候选独立；owner为SEC downloader，不伪造TSM输入 |
| SECIMG-003 / rejected-with-reason | 不纳入修复；保留总控裁决 | 无真实SEC子目录图证据；沿单组件public asset contract typed发现失败及具体安全诊断/保留旧来源；目录映射owner/destination见R4，不修改已确认goal |

| 决策/验证 | 对齐 |
| --- | --- |
| downloader 从待发布bytes发现三类直接候选、有限srcset全候选与首base真源、全部图片用途等价、同申报边界与正常仓储资产 | 成功信号1、3的必要集合正确性；SECIMG-001/002 |
| 版本提升 + Phase A/B同资格 + rebuild不授予下载版本 + 完整descriptor指纹 + upsert原规则 | 成功信号2/3，避免旧COMPLETE吞掉补齐或未下载就认证新完整 |
| earnings完整集合测试迁移、当前版本空fp的GET/发现失败优先 | 成功信号1/2/3/4的必要回归与阶段顺序；SECIMG-A1/A2，不增加生产兼容或空fp修复目标 |
| 批外预取 + 既有batch/identity/reset/rollback + typed失败/取消 | 成功信号3及既有publication安全条件 |
| 1个S1、owner tests/80%/pyright、baseline→new真实CLI与逐图hash/故障 | 成功信号4，提供信号5所需验证证据 |
| 三份README按职责更新、准确CLI启用/补齐说明 | 成功信号2、5 |

方案没有新增schema/存储/调度/下游兼容层；只把必要依赖放回downloader、把新契约资格放回workflow。srcset/picture与base是已确认“实际引用图片”的有限直接语义闭合，不是通用浏览器解析新目标；三种输入复用同一规范化owner及同一次预取payload。没有无证据的新抽象、路径映射或其它image标签；不将外站爬取、CSS/JS递归、浏览器渲染、类型嗅探、空fp元数据修复或额外processed转换变成新验收目标，没有goal drift。

以下分类为Gateflow的归宿分类，并非宣称风险已消除；`covered by later approved slice` 指本plan经review接受后执行的S1，实施/review artifacts须更新真实证据与最终状态。

| ID / residual risk或未覆盖项 | 分类 | Owner / destination / 非阻塞理由 |
| --- | --- | --- |
| R1 两个样例尚未GET全部27张去重图；SEC限流/临时可用性可能阻碍真实验证 | covered by later approved slice | S1实现worker/总控；destination S1真实矩阵及implementation validation JSON。全部必须实际验证才满足成功信号4，当前plan不声称通过；无法获取时该验收阻塞，不能降标准 |
| R2 三类候选/srcset有限语法/首base及URL/decode/去重/碰撞、空fp晚期skip失败优先、earnings测试迁移、两个版本门/rebuild认证、事务/取消/并发尚未实施 | covered by later approved slice | SEC downloader/workflow/rebuild及测试owner；destination S1 owner测试、code review和 `docs/validation/sec-html-image-assets-implementation.json`。四accepted finding的计划规则本轮已修复待re-review，实际行为与测试仍未实现；不另建兼容或hardening slice |
| R3 首次/overwrite与升级HEAD策略不同、远端validator不稳定；当前版本快跳不探测远端新变化 | assigned to later work unit | SEC transport/workflow维护者；destination 后续独立“远端重校验/指纹策略”需求。沿现有算法和overwrite行为，本次明确分别验证descriptor指纹与byte hash；不把改指纹模型纳入本目标 |
| R4 同申报子目录图片不符合现有单组件资产契约；更宽srcset（如含未编码逗号的歧义data）、CSS/JS/browser或legacy非UTF-8需另立有证据的能力需求 | assigned to later work unit | SEC downloader及Fins storage维护者；destination 后续有真实失败样本的独立“目录资产地址契约/其它HTML资源解析”work unit。SECIMG-003已由总控rejected-with-reason；目前无真实目录图证据，不新增映射/schema。三类有限直接候选和base已纳入S1，不再列为延期；子目录、歧义srcset/不可靠解码typed失败及旧publication保留在本S1验证，能力边界不假报完整 |
| R5 外站/跨申报/OCR/数值提取 | assigned to later work unit | 后续需求提出方；destination 后续独立需求。来自已确认非目标，当前不承诺实现 |
| R6 HTTP200非空但非实际图片内容，或远端内容/validators在HEAD与GET间改变 | assigned to later work unit | SEC transport维护者；destination 后续独立“响应内容校验/validator同响应身份”需求。现有raw文件transport契约不做图像解析，本次不扩大；同一HTML bytes的依赖集合一致性仍由S1直接解决 |
| R7 真实bases未执行processor/LLM，因此不证明图片OCR、财报数值或真实processed重算结果 | assigned to later work unit | Fins processor/分析能力维护者；destination 后续独立图片读取/OCR验收。当前只承诺正式来源可寻址，processed重处理标记在S1 owner测试验证 |

Blocking open questions：**无**。真实披露日/全部图片可用性是已指定生产路径的待取证输入，不需要再设计契约或询问用户。若实际代码/远端证据与上述决定矛盾，实施worker交总控裁决，不擅自扩大边界或按样例修改筛选。

## Completion report / 后续gate交接格式

Plan-fix report：仅两份artifact路径、四finding修订要点及blocking open questions（当前无）；初步状态为已修复待re-review，明确未实施、不宣称review pass、不创建commit。总控下一未完成入口为re-review；计划artifact不能代替implementation验证。

S1 implementation artifact 至少记录：gate/work unit/scope、实际changed files、各契约决定及与plan的差异、tests/coverage/pyright命令和退出结果、真实CLI各模式/两实例证据路径、docs decision、finding状态、每项risk分类/owner/destination、未覆盖项、completion status、artifact path。

总控保持Gateflow固定顺序：plan review/fix/re-review后accepted plan checkpoint；S1 implementation/code review/fix/re-review后accepted slice checkpoint；aggregate deepreview及checkpoint；draft PR链中的push/create/PR review及final push；draft-PR-pass后finalcloseout。review使用既定双路provider/skill并由总控裁决。本plan worker不能执行或跳过这些gate。

最终closeout须自足说明改了什么、验证了什么（区分unit/真实CLI/故障注入）、README更新、findings最终状态、风险/owner、修复commit及draft PR URL、实际CLI启用/补齐命令、next entry point。本任务无外部issue，不创建issue/comment；不把draft PR或plan交付当merge/部署完成。
