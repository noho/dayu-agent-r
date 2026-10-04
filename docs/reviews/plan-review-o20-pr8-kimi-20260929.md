# UM-O20-F02 PR8 修订后 P0 计划独立 plan review（Kimi 路）

RUNTIME/PROVIDER/MODEL: codex/kimi/gpt-5
CANARY=kimi-681946f1

- 审查时间：2026-09-29 17:32:54 CST（本机系统时钟 `date` 实测 `20260929-173254`）；artifact 路径为本任务指定唯一新增物 `docs/reviews/plan-review-o20-pr8-kimi-20260929.md`，此前不存在（Python 存在性检查实测为 False 并记录）。
- 审查对象：`docs/gateflow/upload-material-o20-xbrl-runtime-plan-20260929.md`，SHA-256 实测 `4b4e18a1cf499a05cec293c3afe334aa5afe5c6ba0358ff62a92722a5f8bd545`；冻结 E01 `docs/gateflow/upload-material-o20-e01-evidence-20260929.md`，SHA-256 实测 `f75a0c9b20e8ad152d5d0f24964b11f4baf87ffb8f11a313671fa69b6fe0401c`。两者与任务锁定值一致，**未触发 SHA 停止条件**。
- binding scope contract：`docs/gateflow/upload-material-o20-xbrl-runtime-goal-20260929.md`。已读 `AGENTS.md`、goal、总控 `docs/gateflow/upload-material-o20-xbrl-runtime-plan-review-adjudication-20260929.md`（含 PR8-F1/F2 裁决末节）、Sol `docs/gateflow/upload-material-o20-f02-plan-fix-pr8-20260929.md`、MiMo 上轮 `docs/reviews/plan-review-20260929-164018.md`、冻结 E01、`docs/gateflow/upload-material-o20-f02-probe-20260929.md`。
- 版本绑定事实来源（独立核证，不照抄任一 reviewer）：Docling 2.127.0 实际安装源码 `/Users/leo/workspace/dayu-agent-r/.venv/lib/python3.11/site-packages/docling/`（`document_converter.py`、`pipeline/base_pipeline.py`、`backend/xml/xbrl_backend.py`、`datamodel/document.py`、`docling_slim-2.127.0.dist-info/METADATA`）；Arelle 2.45.3 隔离安装源码 `/private/tmp/dayu-o20-f02-probe.AdlwrW/arelle2453/arelle/`（`ModelDocument.py`、`ModelInstanceObject.py`、`ModelXbrl.py`、`WebCache.py`、`arelle_release-2.45.3.dist-info/METADATA`）。未执行 P0、转换、taxonomy 加载、依赖安装或产品测试。
- 边界遵守：只读核查加本 artifact 一次写入；未修改 plan、goal、E01、probe、旧 review、裁决、产品、依赖、锁、测试、README；未发/评/更 issue（#4437 仅只读核对）；未 commit/push/PR/merge；未派发子 Agent；未使用 Goal 工具与进程列表。
- 模型声明：运行时自述为基于 GPT-5 的 Codex；精确部署版本号未向本 agent 暴露，不作虚构。

## 1. Reviewed Target And Scope

按 `planreview` 对 PR8-F1/F2 修订后的 P0 evidence/probe 规格（plan SHA `4b4e18a1...`）做 adversarial review。本版仅是待同版双路复审的 P0 规格，自称"不是 implementation handoff 或 plan pass"，本 review 的范围与之匹配。任务指定重点反证：

1. **PR8-F1**：成功加载目标、失败/不可加载请求、原始逐引用事件三集合能否同次对账；重复同目标引用、失败引用、XSD import/include、zip/catalog entry 四类难点；blocked 出口是否拒绝把聚合摘要或 OS trace 冒充完整证据。
2. **PR8-F2**：pipeline 阶段错误、`DocumentLoadError` invalid-input、构造/导入异常无 result 三条互斥采集路径与最外层异常留证是否闭合。
3. P0-A 三平台受控依赖、P0-C 强制隔离、真实无 typed 样本与公共能力声明上限、上游 #4437 边界是否漂移。

## 2. Assumptions Tested（逐项独立核证）

### 2.1 PR8-F1：三集合语义与 Arelle 2.45.3 实际结构一致

**成功目标集合 = `urlDocs`，语义核实成立。** `ModelDocument.py:75` 先以 `webCache.normalizeUrl(uri, base)` 规范化请求 URI；`:76-78` 命中缓存即早退返回既有 `ModelDocument`；`:127-148` 经 catalog/package/disclosure 映射得 `mappedUri`，archive 内目标保留 archive-entry 形状 `filepath`（`isInArchive` 分支），否则经 `webCache.getfilename` 落本地路径；`:678` `urlDocs[uri] = self` 登记。故计划"key 是规范化请求 URI、`filepath` 是映射后目标"与源码一致。

**失败请求集合 = `urlUnloadableDocs`，语义及其不完整性与计划表述一致。** 失败仅在真正尝试 `load` 时记录（`:139-148`、`:221`、`:248`、`:262`、`:279`，value 为 bool）；`skipLoading` 命中时 `:113-114` 直接 `return None` 不记录任何结构。计划明写"它没有完整原始引用元素、也不保证记录全部未加载尝试"，准确。

**成功 href 的逐元素事件可由 `hrefObjects` 对账，失败 href 不能，计划的分流正确。** `discoverHref`（`:1255-1281`）构造 `(element, doc, id)` 三元组，仅当 `doc is not None` 才 append 到 `hrefObjects`（`:683` 类型为逐元素 list）。`schemaRef` 与 `linkbaseRef` 均经 `schemaLinkbaseRefsDiscover`→`schemaLinkbaseRefDiscover`→`discoverHref`（`:1136-1146` 起），linkbase 内 `roleRef/arcroleRef` 亦走 `discoverHref`。因此重复同目标（如 `typed.xsd` 与 `./typed.xsd`）两个元素都会留存、可恢复 multiplicity；失败 href 不在 `hrefObjects`，只能如计划所写"从原始元素补齐并与 `urlUnloadableDocs`/errors 逐项对账"。Sol PR8 探针的运行观察（`hrefObjects` 保留 index 2、3；`urlUnloadableDocs` 有规范化 `missing.xsd: true`）与该静态语义吻合。

**`referencesDocument` 确实只是聚合摘要。** `addDocumentReference`（`:1488-1496`）以目标 `ModelDocument` 为 key，同目标再次引用只并入 `referenceTypes` 且仅在原值为 None 时填 `referringModelObject`——第二引用元素与次数永久丢失。计划将其限定为"仅另存为按目标文档聚合的摘要，不得用作逐引用事件或 multiplicity 真源"，正确。

**XSD import/include 不在 href 覆盖内，计划未外推，处置可执行。** `importDiscover`（`:1065-1106`）对 `xs:import/xs:include/xs:redefine` 先按 `namespaceDocs[importNamespace]` 短路：namespace 已加载且 basename 匹配时不再 `load`，该次引用的实际目标即为既有文档；仅在未匹配时才 `load`，失败进 `urlUnloadableDocs`，成功只调聚合的 `addDocumentReference`——Arelle 内部没有 import 的逐元素成功清单。逐元素事件源须由探针枚举受控合成输入的原始 `xs:import/xs:include` 元素再与 `urlDocs`/`urlUnloadableDocs` 对账。计划明确"XSD import/include、schemaLocation 及其他发现机制须各自核对其原始元素、规范化规则和同次目标；不能把 href 结构的覆盖范围外推到它们"，且对闭合失败给出 `blocked: run evidence unavailable`。P0-B 三个合成向量均为探针自控输入，逐元素枚举可行；namespace 短路这类不可闭合形态会被 blocked 出口捕获而非冒充 pass。

**zip/catalog entry 的证据限度表述与源码一致。** Docling `xbrl_backend.py:122-168`：`taxonomy` 必须是目录（否则 `ValueError`，:127-130），`shutil.copytree` 整树复制进 `TemporaryDirectory`（:131-133），仅收集复制后顶层合法 `.zip`（`zipfile.is_zipfile` 过滤，:133-143），作为 `taxonomyPackages` 传给 `modelManager.load`（:168）；`BytesIO` 固定写 `instance.xml`（:146-147）；临时目录在 `with` 退出即清理。计划"`filepath` archive 形状与 OS 文件 trace 不单独证明 entry 内容读取""模型所载临时 `filepath` 只能作为当次映射记录，不能事后重读补证"，与该结构吻合。

**blocked 出口纪律核实。** 计划原文"不得以聚合摘要、原始 XML 单独推测、重放或 OS trace 补成 pass""OS trace 仅能证明其实际记录的文件访问""独立 Arelle 重放只单列'重放证据'……不能冒充 Docling 当次读取/映射记录"，正面满足裁决"不能把聚合摘要冒称事件日志"的接受条件。

### 2.2 PR8-F2：三条互斥采集路径与 Docling 2.127.0 实际控制流一致

**路径①（pipeline 阶段错误返回 result）成立。** `XBRLFormatOption` 绑定 `SimplePipeline`+`XBRLDocumentBackend`（`document_converter.py:242-245`）；`BasePipeline.execute`（`base_pipeline.py:79-112`）先建 `ConversionResult`，转换异常置 `FAILURE`，`raises_on_error=False` 时追加 error item 并返回 result；`_unload` 为 no-op（`:185-186`）。`xbrl_backend.py:181` 在导出循环（`:344` `dim_value.memberQname.localName`）之前已 `self.model_xbrl = model`，故 typed 崩溃后同次 model 仍可快照。计划"typed 失败不得改记成功"与 `_determine_status`/errors 语义兼容。

**路径②（`DocumentLoadError` → invalid-input result，不假定 backend）成立。** backend load 阶段异常统一包成 `DocumentLoadError`（`xbrl_backend.py:183-188`）；`InputDocument` 仅对 `DocumentLoadError` 记 `valid=False`+`BACKEND_FAILURE` 拒绝（`datamodel/document.py:317-323`），其他异常原样 `raise`；`_process_document`（`document_converter.py:836-875`）对 invalid input 返回带 `build_invalid_input_errors` 的 FAILURE result，不构造 backend。Sol PR8 探针实测坏 taxonomy 正是此路径（`FAILURE`、`input.valid=false`、无 `_backend`）。

**路径③（构造/导入异常逃出 `convert`，无 result）成立且为直接源码反例的修复。** 缺 Arelle 的 `ImportError` 在 `XBRLDocumentBackend.__init__` 顶部、任何 try 之前抛出（`xbrl_backend.py:95-99`）；经 `document.py:321-322` 重抛后，在 `_convert` 迭代 `conv_input.docs(...)` 构造 `InputDocument` 时逃出（`document_converter.py:741-780`），根本不进入 `pipeline.execute` 的 try，故无 `ConversionResult`。计划第三条要求"探针最外层捕获并记录异常类型、消息、cause 链、完整 traceback、双流、Docling/Arelle 版本及输入/配置哈希，直接按同一 blocked 出口处理，不能读取虚构的 `result.errors`"，并明写"`raises_on_error=False` 不是构造期全局非抛出保证"，闭合了 MiMo PR8-F2。

### 2.3 P0-A 三平台受控依赖：诚实 blocked，无越界承诺

Arelle 2.45.3 wheel `METADATA` 实测 `Version: 2.45.3`、`Requires-Python: >=3.10`、`Requires-Dist: jaconv<1,>=0`；docling-slim 2.127.0 `METADATA` 实测 `arelle-release<3.0.0,>=2.38.17; extra == 'format-xml-xbrl'`——2.44.8 与 2.45.3 均在允许区间，计划"重开两者选择、不选生产 pin"有依据。P0-A 要求 Python 3.11 fresh venv 有依赖实装+`pip check`、逐平台 pass/blocked 四态、禁止交叉移植状态、三平台全 pass 才定 pin；Linux/Windows 记 `blocked: runner unavailable`。未发现把 macOS dry-run 冒充安装的把柄。

### 2.4 P0-C 强制隔离：`workOffline` 非边界的判断经源码证实

`WebCache.py:187` `workOffline` 只是配置布尔；`getfilename`（`:545-610`）对非 HTTP(S) URL（含 `file:`）直接返回本地路径、无任何边界判断，`workOffline` 仅在 `:604/:610` 挡下载；`getheaders`（`:1029-1038`）、`geturl`（`:1041-1050`）、`retrieve`（`:1053-1064`）均无条件 `self.opener.open(url...)`；`WebCache.TransformURL` 插件 hook 只出现在 `getfilename`（`:556`）。Docling 侧 `enable_remote_fetch=False` 仅置 `workOffline=True` 并**关闭** `validateDisclosureSystem`（`xbrl_backend.py:154-158`），连 disclosure 阻断也一并关掉。计划"`workOffline`、预扫描、Docling 临时目录、普通子进程或 monkeypatch 均不能单独证明强制边界"逐条有据。E01/probe 的 `file:` 根外 sentinel 加载观察与此一致。P0-C 以真实平台机制为先决、有限矩阵+逐向量 OS trace 为验证、`blocked: isolation unavailable` 为出口，且明示"有限矩阵只检验样本覆盖，零出站和文件边界的保证由 OS/受信隔离规则提供"，无不实承诺。

### 2.5 真实无 typed 样本与公共能力声明上限

P0-B 要求真实样本先过 Arelle `--validate --validationExitCode` 合法性门槛并留存原始证据后才跑 Docling 两路；无 typed 须以"完整原件全部 context 的 `xbrldi:typedMember` 检查 + Arelle 加载后实际 context 维度值检查"双证，且声明范围限于该 instance 实际 context/引用形状/版本/配置，不外推含 typed 财报；不可得则 goal 3 blocked。§5 末段把 S1 共享 capability 真源及其 CLI/help/tool 同源投影的公开声明上限钉在"无 typed 真实正样本的已验证引用形状、无 typed 范围和部署条件"，含 typed 支持须待上游修复+重测；投影无法诚实表达则 S1 硬停回双路复审。与 goal 1/3 的成功信号一致，未见能力声明漂移。

### 2.6 上游 #4437 边界

只读核对 GitHub `docling-project/docling` issue #4437：存在、open、创建于 2026-09-29，标题 "XBRL typed dimension crashes conversion at memberQname.localName"，正文为纯合成 `typed.xsd`/`typed.xml` 最小复现，版本与环境逐条列出，且结尾自行声明 "This report concerns the typed dimension branch only; an invalid explicit member caused by missing taxonomy may reach the same line for a different reason."。计划 §6"对账该 issue，不重开同一问题""Arelle explicit/缺 taxonomy 支仍需独立验证，不能写成同一已证 bug""本轮用户明确禁止发送、评价或更新"与该实际边界一致，未漂移。

### 2.7 附带事实核验

worktree HEAD 实测 `9735800cb55a40336469593fa2fddae43c9c69ad`，与计划/goal 声明一致；worktree 无 `.venv`（Python 存在性检查实测为 False 并记录），与计划 §7 声明一致。

## 3. Findings

无新增 material findings。理由：PR8-F1/F2 的修订文本与 Docling 2.127.0/Arelle 2.45.3 实际源码逐条吻合（§2.1/§2.2），三集合拆分、import/include 不外推、zip entry 证据限度、blocked 出口纪律均可执行且诚实；§2.3-§2.6 指定的五个复查面未发现回退或漂移。既往各轮 finding（PR1-PR8）的当前处置与总控裁决一致，本路无证据推翻。

## 4. Open Questions

1. P0-B 实测时，`hrefObjects` 对 linkbaseRef/roleRef/arcroleRef 的逐元素保留是否在所有正式向量上都闭合（源码支持 schemaRef/linkbaseRef，其余需运行时确认）；不闭合即按计划 blocked，不构成计划缺陷。
2. import/include 向量中若出现"namespace 已加载导致不再 load"的短路形态，探针选择重构样本避开还是在报告中接受该事件无独立加载记录，留给 P0 执行记录，不影响规格可执行性。
3. zip entry 的"同次文件源/模型中可核的 entry 记录"在 Arelle 2.45.3 实际可取到何种粒度（`urlDocs` archive 形状 `filepath`+解析成功是否足够），待 P0-B zip 向量实测回答。

## 5. Residual Risks And Tracking

- **R1** 三平台 runner、真实安装/`pip check`、真实无 typed 合规样本、三平台强制隔离、zip+catalog 实测均未证：计划内已逐项 blocked，跟踪去向为 P0-A/B/C 执行与 goal/总控裁决，不因本 review 转 pass。
- **R2** 内部属性链（`result.input._backend.model_xbrl`、`urlDocs`、`urlUnloadableDocs`、`hrefObjects`、`referencesDocument`）版本绑定 2.127.0/2.45.3，升级即漂移：跟踪去向为 P0-A 版本候选确定后按 §5 重跑采集探针。
- **R3** E01 `jaconv>=1,<2` 当时成因因原 argv 缺失永久不可唯一判定：计划与探针已按一手 wheel METADATA+resolver 纠偏，跟踪去向为 P0-A 留存完整 argv/report 防复发。
- **R4** 本路一条复合命令（`git rev-parse HEAD` 与两个预期缺失路径的 `ls` 串联）整体 exit 1：`HEAD` 值已取得，两个"预期不存在"检查随后按要求在 Python 内复测并记录为 True，语义不受影响；按"所有命令自身 exit0"口径如实披露。

## 6. Final Plan Review Conclusion

**pass**（限定：仅指本 P0 evidence/probe 规格可交付 P0 执行，不构成 P0 pass、产品实现批准或能力声明）。

理由：PR8-F1 的三集合对账规格（成功目标 `urlDocs`、失败请求 `urlUnloadableDocs`、原始逐引用事件以 `hrefObjects`+原始元素补齐、`referencesDocument` 降级为聚合摘要）与 Arelle 2.45.3 实际语义一致，重复同目标/失败引用/import-include/zip entry 四类难点各有可执行采集或明确 blocked；PR8-F2 的三条互斥采集路径与 Docling 2.127.0 实际控制流一致，最外层异常留证闭合。P0-A/P0-C 保持诚实 blocked，无 typed 样本与 capability 上限未漂移，#4437 边界与实际 issue 一致。上一停止条件（同次逐边证据规格不可执行）已解除；本路未发现新的结构不安全。

（本文件为本次任务指定唯一新增 artifact；未改任何 plan/goal/E01/probe/旧 review/裁决/产品/依赖/锁/测试/README，未执行 P0、未安装依赖、未加载 taxonomy、未发/评/更 issue，未 commit/push/PR/merge，未派发子 Agent。）
