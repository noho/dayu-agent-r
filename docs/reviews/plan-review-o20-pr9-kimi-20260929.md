# UM-O20-F02 PR9 P0 计划独立 plan review（Kimi 路）

RUNTIME/PROVIDER/MODEL: codex/kimi/gpt-5
CANARY=kimi-2820b23d

- 审查时间：2026-09-29 17:58:56 CST（本机系统时钟 `date` 实测）。artifact 路径为本任务指定唯一新增物 `docs/reviews/plan-review-o20-pr9-kimi-20260929.md`；文件名不套用 skill 的 timestamp 模板，是显式任务路径要求，timestamp 仍在本节留证。写入前实测该路径不存在。
- 审查对象：`docs/gateflow/upload-material-o20-xbrl-runtime-plan-20260929.md`，SHA-256 实测 `9d99f7bdc7bb0feb103bee9f71a7d6097cb10ee0a3a7d782c9fda4b33c58906c`，与任务锁定值一致；冻结 E01 `docs/gateflow/upload-material-o20-e01-evidence-20260929.md`，SHA-256 实测 `f75a0c9b20e8ad152d5d0f24964b11f4baf87ffb8f11a313671fa69b6fe0401c`，与历代裁决/评审锁定值一致。**未触发 SHA 停止条件**。
- binding scope contract：`docs/gateflow/upload-material-o20-xbrl-runtime-goal-20260929.md`。已读 `AGENTS.md`、goal、总控 `docs/gateflow/upload-material-o20-xbrl-runtime-plan-review-adjudication-20260929.md`（全文，含 PR9-F1 裁决末节）、Sol `docs/gateflow/upload-material-o20-f02-plan-fix-pr9-20260929.md`、前轮两份同版 review `docs/reviews/plan-review-o20-pr8-kimi-20260929.md` 与 `docs/reviews/plan-review-o20-pr8-mimo-20260929.md`、`docs/gateflow/upload-material-o20-f02-probe-20260929.md` 及冻结 E01。
- 版本绑定事实来源（独立核证，不照抄任一 reviewer 或 fix artifact）：Docling 2.127.0 实际安装源码 `/Users/leo/workspace/dayu-agent-r/.venv/lib/python3.11/site-packages/docling/`（METADATA 实测 Version 2.127.0；`backend/xml/xbrl_backend.py`、`document_converter.py`、`pipeline/base_pipeline.py`、`pipeline/simple_pipeline.py`、`datamodel/document.py`）；Arelle 2.45.3 隔离解包源码 `/private/tmp/dayu-o20-f02-probe.AdlwrW/arelle2453/arelle/`（METADATA 实测 arelle-release 2.45.3；`ModelDocument.py`、`ModelInstanceObject.py`、`ModelXbrl.py`、`FileSource.py`、`WebCache.py`、`Cntlr.py`）。
- 边界遵守：只读核查加本 artifact 一次写入；未修改 plan、goal、E01、probe、旧 review、裁决、产品、依赖、锁、测试、README；未执行 P0、转换、taxonomy 加载或依赖安装；未发/评/更 issue（#4437 仅只读 GET 核对）；未 commit/push/PR/merge；未派发子 Agent。
- 模型声明：运行时自述为基于 GPT-5 的 Codex；精确部署版本号未向本 agent 暴露，不作虚构。

## 1. Reviewed Target And Scope

按 `planreview` 对 PR9-F1 修订后的 P0 evidence/probe 规格（plan SHA `9d99f7...`）做 adversarial review。本版自称"仅是待同版复审的 P0 evidence/probe 规格，不是 implementation handoff 或 plan pass"，本 review 范围与之匹配。任务指定重点反证：

1. 静态声明清单与同次观察 `attempt_observation` 的逐元素关系是否仍可把声明冒称运行事件；
2. 重复失败 import/include 与 catalog entry 两个小探针是否有源码依据、采集能力与 blocked 边界是否闭合；
3. PR8-F1/F2 的三集合/三异常路径是否保持；
4. P0-A 三平台依赖、P0-C 强制隔离、真实无 typed 样本、公共能力上限与上游 #4437 边界是否漂移。

## 2. Assumptions Tested（逐项独立核证）

### 2.1 静态声明清单与 `attempt_observation` 语义：与 Arelle 2.45.3 源码一致，未见声明冒称运行事件

- **成功目标集合**：`load` 在 `ModelDocument.py:75` 以 `webCache.normalizeUrl(uri, base)` 规范化请求 URI，`:76-78` 命中 `urlDocs` 缓存即早退；`:379` 以 `normalizedUri` 构造文档，构造器 `:678` 执行 `urlDocs[uri] = self`；archive 分支 `filepath = mappedUri` 保留 archive-entry 形状。计划"key 是规范化请求 URI、`uri`/`filepath` 是请求身份与映射后目标"准确。
- **失败请求集合**：`:79-80` 命中 `urlUnloadableDocs` 缓存即返回 `None` 不记录；`:113-114` `skipLoading` 命中直接返回不记录；仅首个失败在 `:139-148` 等分支登记 `urlUnloadableDocs[normalizedUri]`（`ModelXbrl.py:326` 注释：True 为阻断不可载，False 为可载但告警）。计划"它没有完整原始引用元素、也不保证记录全部未加载尝试"准确。
- **成功 href 逐元素事件**：`discoverHref`（`:1255-1281`）构造 `(element, doc, id)` 三元组，仅 `doc is not None` 时 append 到逐文档 `hrefObjects`（`:683`）；`schemaRef`/`linkbaseRef` 经 `schemaLinkbaseRefsDiscover`→`discoverHref`（`:1136-1146`）。两个不同元素同指一个目标时各自留元组，multiplicity 可恢复；计划"先检验同次 `hrefObjects` 是否按元素保留每次事件，能逐项对账才标 `observed`"有源码依据。
- **聚合降级**：`addDocumentReference`（`:1488-1496`）按目标文档 key 合并 `referenceTypes`、仅在空时补首个 `referringModelObject`；计划把 `referencesDocument` 限定为"按目标文档聚合的摘要，不得用作逐声明事件、次数或 `attempt_observation` 真源"准确。
- **非 href 机制**：`importDiscover`（`:1065-1105`）按 `namespaceDocs[importNamespace]` 短路复用或调用 `load`，成功仅入聚合 `addDocumentReference`；`loadSchemalocatedSchema`（`:457-469`）不建逐元素事件表。计划"不能把 href 结构的覆盖范围外推到它们，也不能以 `urlDocs` 命中推断每条声明实际调用了 `load`"准确。
- **catalog/zip entry**：`FileSource.isInArchive(filepath, checkExistence=False)`（`:482-492`）注释原文"True only means that the filepath maps into the archive, not that the file is really there"；计划"`filepath` archive 形状与 OS 文件 trace 不单独证明 entry 内容读取"准确。
- 结论：第三集合已改名"原始引用声明清单"，每条显式 `attempt_observation=observed|unknown`，`observed` 定义为"该声明有同次直接可对账的尝试/发现事件，不自动证明目标文件或 zip entry 内容已读取"。**未触发"第三集合仍把声明冒称运行事件"停止条件。**

### 2.2 重复失败 import/include 与 catalog entry 小探针：探针目标成立，阻塞语义有源码依据

- 两个 `xs:import` 同指不存在目标（无论同 namespace 或不同 namespace）：`namespaceDocs[ns]` 为空或不含该 URI，两次均落入 `load`；首失败登记 `urlUnloadableDocs`，第二次 `:79-80` 缓存早退，无第二个事件。
- 两个 `xs:include` 同指不存在目标：`isIncluded=True` 时 namespace 复用被显式禁止（`elif isIncluded: doc = None`），除非精确 URI 命中（缺失目标不可能），同样只有首失败一个事件。
- 探针要求"记录各自的静态声明、同次直接事件有无及失败缓存/namespace 短路情形，不能把一个 `urlUnloadableDocs` 项分配成两次已观察失败"，与上述源码行为一一对应。
- catalog 探针要求"分记 catalog 声明、映射目标形状和该次具体 entry 读取记录有无"；`isInArchive` 语义与 `urlDocs` 登记需经 `etree.parse` 成功的事实，支撑"路径形状不证明 entry 已读、须另有同次可核记录"的设计。
- 缺同次逐边/逐 entry 运行记录即 `blocked: run evidence unavailable`，不得以静态 XML、聚合摘要、重放或 OS trace 补成 pass。**未触发"缺直接证据却能标 observed/pass"停止条件。**

### 2.3 PR8-F2 三条互斥异常采集路径：与 Docling 2.127.0 控制流一致

- 路径① pipeline 阶段错误（如 typed 在 `xbrl_backend.py:344` 的 `AttributeError`，该行实测无 None 防护）：`ConvertPipeline.execute`（`base_pipeline.py:98-106`）捕获 `Exception` 置 `FAILURE`，`raises_on_error=False` 时附 `ErrorItem` 返回 result；XBRL 走 `SimplePipeline`（`simple_pipeline.py:19`，继承 `execute`）。
- 路径② `DocumentLoadError`（backend `__init__` 内 `ValueError`/`OperationNotAllowed` 均被包裹，`xbrl_backend.py:184-188`）：`_init_doc`（`datamodel/document.py:317-325`）仅对 `DocumentLoadError` 记 rejection 置 invalid；`_execute_pipeline`（`document_converter.py:860-875`）返回 invalid-input `FAILURE` result 与 `build_invalid_input_errors`。计划"不假定存在 `_backend` 或模型"准确（构造抛错时 `_backend` 从未赋值）。
- 路径③ 构造/导入异常：`xbrl_backend.py:88-94` 缺 Arelle 时 `__init__` 先抛 `ImportError`；`_init_doc` `:322-323` 对非 `DocumentLoadError` 直接 `raise`；`InputDocument.__init__` 只捕获 `FileNotFoundError/OSError/RuntimeError`；`docs()` 生成器（`datamodel/document.py:704`）仅捕获 `OSError/ValueError`；异常遂逃出 `convert`，无 result，`raises_on_error=False` 不是构造期非抛出保证。计划描述准确。

### 2.4 P0-A / P0-C / 真实无 typed / 公共能力上限 / #4437：未见漂移

- P0-A 三平台 fresh venv 有依赖实装、`pip check`、逐平台 pass/blocked、全平台通过才定生产 pin，保持；Linux/Windows runner `blocked: runner unavailable` 保持。
- P0-C C0–C8 矩阵、零出站（含非 taxonomy URL）、逐向量 OS trace、三平台强制机制与 blocked 出口保持。计划 §4 对 Arelle hook 覆盖面的声明经核准确：`WebCache.TransformURL` hook 仅出现在 `getfilename` 的 URL 变换路径（`WebCache.py:556`），`getheaders`/`geturl`/`retrieve` 仍直接 `opener.open`（`:1029-1064`），`workOffline` 仅在 `getfilename` 内被检查（`:604,:610`）。
- 真实无 typed 样本：Arelle `--validate --validationExitCode` 合法性门槛与原始证据留存在前、Docling 两路在后；无 typed 须"完整原件全部 context 的 `xbrldi:typedMember` 检查 + Arelle 加载后实际 context 维度值检查"双证；证明范围限于该 instance 实际 context/引用形状/taxonomy/版本/配置，不外推含 typed 财报；不成立则 goal 3 blocked。保持。
- 公共能力上限：§5 末段 S1 共享 capability 真源及 CLI/help/tool 同源投影的公开声明上限钉在"无 typed 真实正样本的已验证引用形状、无 typed 范围和部署条件"，含 typed 须待上游修复+同等合法性与真实上传重测；投影无法诚实表达则 S1 硬停回双路复审。与 goal 1/3 一致，未见 capability 漂移。**未触发"P0/产品范围漂移"停止条件。**
- #4437：只读 GET 实测存在、open、创建于 2026-09-29、0 评论，标题"XBRL typed dimension crashes conversion at memberQname.localName"，正文为纯合成最小复现并自行声明"This report concerns the typed dimension branch only; an invalid explicit member caused by missing taxonomy may reach the same line for a different reason."。计划"对账该 issue，不重开同一问题""explicit/缺 taxonomy 支独立验证不合并归因""本轮不发/评/更"与实际一致。
- 附带事实：worktree HEAD 实测 `9735800cb55a40336469593fa2fddae43c9c69ad`，与 plan/goal 声明一致；backend 行为（`taxonomy` 仅目录、`copytree` 整树、仅收集顶层合法 `.zip`、`BytesIO` 固定写 `instance.xml`、临时目录在 `convert` 返回前清理、内部 `Cntlr.Cntlr()` 无 resolver 注入点）逐行核实与计划 §3/§5 一致。

## 3. Findings

### 1-未修复-中-P0-B 同次模型快照的指定采集链在 convert 路径下不可达，计划核心取证机制不可直接实施

- **位置**: §5 P0-B 当次模型证据探针（路径①"在本次进程内及时快照可取得的 backend/model"；"对每个正式 Path/Stream 向量也必须在该次转换进程内调用并保留 result，返回后立即、释放结果/模型或清理进程前快照成独立普通数据"；成功集合"遍历 `model_xbrl.urlDocs`"；以及"内部属性链 `result.input._backend.model_xbrl`、`urlDocs`、`urlUnloadableDocs`、`hrefObjects` 和 `referencesDocument` 仅为版本绑定的 P0 探针入口"）。
- **问题类型**: 不可直接实施 / 契约缺失（采集窗口与指定属性链的实际生命周期不匹配）。
- **当前写法**: 计划把同次模型证据（成功集合、失败集合、`hrefObjects` 逐元素对账、catalog entry 记录、重复 href 小探针）的探针入口指定为 `convert(...)` 返回后的 `result.input._backend.model_xbrl`，并要求"返回后立即"快照。
- **反例/失败场景**: Docling 2.127.0 `ConvertPipeline.execute` 的 `finally: self._unload(conv_res)`（`base_pipeline.py:108-110`）无条件调用 `conv_res.input._backend.unload()`（`:405-406`）；`XBRLDocumentBackend.unload` 调用 `model_xbrl.close()`；Arelle `ModelXbrl.close`（`ModelXbrl.py:384-401`）执行 `self.__dict__.clear()`（`isClosed` 即 `__dict__` 为空）并递归 `ModelDocument.close`，后者 `urlDocs.pop(self.uri)`、逐文档 `self.__dict__.clear()`（清掉 `hrefObjects`/`referencesDocument`）并在最外层 `while urlDocs: urlDocs.popitem()[1].close(...)` 清空整个 `urlDocs`（`ModelDocument.py:794-843`）。因此 `convert` 让出 result 时——无论成功还是路径①的 pipeline 失败——`result.input._backend.model_xbrl.urlDocs` 等属性链一律 `AttributeError`。"释放结果/模型"发生在 `convert` 内部的 `finally`，严格先于"返回后"，计划预设的快照窗口不存在；`raises_on_error` 取值、`keep_backend`（仅管 page backend）均不改变该行为。
- **为什么有问题**: 计划的核心正向取证机制（成功集合枚举、`hrefObjects` 逐元素 `observed` 对账、重复 href/catalog entry 小探针、zip entry 读取记录）全部指定在一条 convert 返回后必死的属性链上。实施者照计划执行，第一个模型访问步即失败；按计划自身规则只能把逐向量记 `blocked: run evidence unavailable` 并回 plan/fix——P0-B 的正向证据目标在首轮探针即整体塌缩为 blocked；或者实施者被迫自行重新设计采集方法（例如直接构造 `XBRLDocumentBackend`、绕过 convert 在 `unload()` 前进程内快照），这恰是 planreview 要拦截的"计划不够 code-generation-ready，迫使 implementation agent 重新设计"。
- **直接证据**: `base_pipeline.py:79-110`（`execute` 的 `finally: self._unload`）、`:400-406`（`_unload` 无条件 unload input backend）；`xbrl_backend.py` `unload`（`self.model_xbrl.close()`）；`ModelXbrl.py:384-401`（`close` → `__dict__.clear()`）；`ModelDocument.py:794-843`（递归清空 `urlDocs`/逐文档 `__dict__.clear()`）；计划 §5 上述引文。补充：Arelle 侧兜底事件流也不可用——Docling 以无参 `Cntlr.Cntlr()` 构造（`xbrl_backend.py`），`Cntlr.py:419-445` 显示无 `logHandler`/`logFileName` 时落入默认 logging，探针无法经 convert 路径取得结构化逐元素错误事件；`ModelDocument.py:139-148` 的首失败错误虽携带 `modelObject=referringElement`，但仅以格式化文本进入默认日志，不能作逐元素对账真源。
- **影响**: 照字面执行 → P0-B 正向证据机制首轮即整体 blocked，浪费一轮正式取证后才回 plan/fix；或实施者临场自创采集路径 → 同次归属规则（convert 运行 vs 直接 backend 运行）在计划中没有定义，可能把不同运行的证据混记为"该次"，损害可归因性与 review 可验收性。计划自身的 fail-safe 杜绝了假 pass（故不触发停止条件），但计划作为交付实施的规格在其中心机制上不可直接实施。
- **建议改法和验证点**: 在 §5 P0-B 显式拆分两类采集并分别定约归属：（a）`convert(source, raises_on_error=False)` 运行仅用于三条互斥 result/异常路径分类与 status/errors 记录，不用于任何同次模型结构读取；（b）同次模型证据由探针直接构造 `XBRLDocumentBackend`（同输入、同 options、同版本，探针级、非产品 hook，可经 `InputDocument` 正常构造取得 `_backend` 而不触发 pipeline unload）在 `backend.unload()` 前的进程内窗口快照 `urlDocs`/`urlUnloadableDocs`/`hrefObjects`/`referencesDocument` 为独立普通数据；明文规定直接 backend 运行的证据只标记为该运行自身的当次证据，不得与 convert 运行的 result 语义合并表述为同一运行。验证点：以经 Arelle 合法性验证的无 typed 最小成功样本实测直接 backend 路径下 `urlDocs`/`hrefObjects` 在 `unload()` 前可读、快照后 `unload()` 再访问确实 `AttributeError`，留双向证据；全部 blocked 出口保持不变。
- **修复风险（低/中/高）**: 低。
- **严重程度（低/中/高/严重）**: 中。

### 2-未修复-低-失败 href 的 `observed` 直接事件源未枚举，重复失败场景下实施者判定可能分叉

- **位置**: §5 P0-B"失败 href 可从原始元素列入清单，并与 `urlUnloadableDocs`/errors 对照，但按 URI 聚合的失败项本身不能把每个元素标为 `observed`"。
- **问题类型**: 契约缺失（`observed` 的合格直接事件源未枚举到失败方向）。
- **当前写法**: 计划定义 `observed` 需要"同次直接可对账的尝试/发现事件"，禁止聚合失败项把每个元素标 `observed`，但未列举失败 href 方向哪些记录算合格的逐元素直接事件、哪些不算。
- **反例/失败场景**: Arelle 对每个规范化 URI 的**首个**失败会以 `modelObject=referringElement` 记录错误（`ModelDocument.py:139-148`），重复失败则被 `:79-80` 缓存短路无任何事件。重复失败样本下，元素 1 在格式化错误文本中有出现、元素 2 没有；两位实施者可能分别判"元素 1 observed、元素 2 unknown"与"两者皆 unknown"，产生不可比对的取证结果。
- **为什么有问题**: 危险方向（按 URI 聚合把两个元素都标 observed）虽被明文禁止，且重复失败小探针正是为实证该不对称而设，但计划未明示"默认 logging 的格式化错误文本不是逐元素可对账直接事件源"（以字符串反推元素身份正是计划纪律所禁），判定标准留有解释空间。
- **直接证据**: `ModelDocument.py:79-80,139-148`；`Cntlr.py:419-445`（无参构造下无结构化 log handler）；计划 §5 上述引文。
- **影响**: 小探针结果表述不一致风险；不导致假 pass，不阻塞交付，但应在计划中以一句话钉死判定规则，避免取证结果不可复核。
- **建议改法和验证点**: 在 §5 显式声明：失败方向的 `observed` 仅接受模型/文件源中可按元素身份对账的结构化记录，格式化日志/stderr 文本一律不算逐元素直接事件；重复失败小探针须如实记录首失败有文本、后续失败无事件的不对称原始证据。验证点：重复失败 import/include 与 href 小探针输出中逐元素的直接事件有/无对照表。
- **修复风险（低/中/高）**: 低。
- **严重程度（低/中/高/严重）**: 低。

## 4. Open Questions

1. finding 1 的修复方向（直接 `XBRLDocumentBackend` 构造的 sibling 运行取证及其归属表述）是否被 goal/总控接受；若总控要求模型证据必须与 convert 运行同进程，则当前 Docling 2.127.0 公开 API 下不可达，须回 goal/总控裁决证据机制或支持范围。
2. 失败 href 首失败元素在格式化错误文本中的出现是否一律不得支撑 `observed`（finding 2 的裁决口径）。
3. （承自前轮，仍未收敛）非 href import/include/schemaLocation、重复失败与 zip entry 因缺逐事件真源而稳定 blocked，是否为 P0 的最终证据能力上限（MiMo PR8 OQ1）。

## 5. Residual Risks And Suggested Tracking

- **R1 正向能力仍全部未证**：三平台实装/`pip check`、三平台强制隔离、zip+catalog 实测、真实无 typed 合规样本、真实 CLI/material manifest 成功均未执行。跟踪去向：P0-A/B/C 执行与 goal/总控裁决，不因本 review 转 pass。
- **R2 版本绑定漂移**：全部源码结论绑定 Docling 2.127.0 / Arelle 2.45.3；升级后 pipeline unload、`ModelXbrl.close`、发现/聚合结构均须重核。跟踪去向：P0-A 候选版本确定后按 §5 重跑采集探针。
- **R3 E01 `jaconv>=1,<2` 当时成因**因原 argv 缺失永久不可唯一判定；一手 wheel METADATA+resolver 已纠偏。跟踪去向：P0-A 留存完整 argv/report 防复发。
- **R4 finding 1 修复后仍可能暴露更深层拆除窗口**（例如直接 backend 路径下快照时序、`model.errors` 分支的模型存活差异）。跟踪去向：finding 1 验证点的小样本双向证据。
- **R5 内部属性链仅供 P0 探针**：不进入 Dayu 产品或公开契约；属性失效按 blocked 回 plan/fix，不加产品 hook（计划已明记，本 review 复核保持）。

## 6. 停止条件核对（任务指定）

1. SHA 不符——未触发（plan/E01 实测与锁定值一致）。
2. 第三集合仍把声明冒称运行事件——未触发（§2.1 逐条源码核证，声明清单+`attempt_observation` 语义成立）。
3. 缺直接证据却能标 `observed`/pass——未触发（§2.2；finding 1 的方向相反：计划指定的采集链过严地不可达，只会导致 blocked，不会导致假 observed）。
4. P0/产品范围漂移——未触发（§2.4；公共能力上限、真实无 typed 口径、#4437 边界均保持）。

## 7. 命令与工具披露（含非零/失败项）

- 一次 `exec_command`（读取 Arelle `ModelDocument.py:670-690` 的 `sed`）在工具层失败：`CreateProcess ... No such file or directory (os error 2)`，**未执行任何 shell**；同命令立即重试成功（exit 0），输出已用于 §2.1 核证。对结论无影响。
- 最终存在性检查中的 `ls docs/reviews/plan-review-o20-pr9-kimi-20260929.md` 返回"No such file or directory"（复合命令内该段非零；复合整体 exit 0 由末尾 `date` 决定）。这正是"本 artifact 必须为唯一新增物"的预期核验结果，对结论无影响。
- GitHub `get_issue`（docling-project/docling #4437）为只读 GET，成功；属任务要求的 #4437 兼审，不构成"发/评/更"。
- 其余全部探索命令（`shasum`、`sed`/`awk`/`grep`/`ls`/`head`、`git rev-parse`/`git status --short`、`date`、记忆索引 `grep`）均 exit 0；大目录 `ls` 输出被截断仅影响显示，不影响事实。

## 8. Final Plan Review Conclusion

**fail**（限定：仅针对本 P0 evidence/probe 规格可否交付 P0 执行；不否定其诚实边界与既往修订）。

理由：PR9-F1 的声明清单/`attempt_observation` 修订与 Arelle 2.45.3 源码逐条吻合，重复失败与 catalog entry 小探针目标成立，三异常路径、P0-A/P0-C、真实无 typed、公共能力上限与 #4437 边界均无漂移，四项任务停止条件均未触发。但 finding 1（中）是计划中心取证机制的执行可行性缺陷：同次模型快照被指定在 convert 返回后必被 `close()`/`__dict__.clear()` 拆除的属性链上，照计划字面执行会使 P0-B 正向证据在首轮探针即整体塌缩为 blocked，或迫使实施者临场重新设计采集方法并自担归属风险——计划在其最关键机制上尚不够 code-generation-ready。修复面窄（仅在 §5 P0-B 拆分 convert 分类运行与直接 backend 快照运行并定约归属，外加 finding 2 的一句判定规则），修复后按惯例重新锁 SHA 双路复审。

（本文件为本次任务指定唯一新增 artifact；未改任何 plan/goal/E01/probe/旧 review/裁决/产品/依赖/锁/测试/README，未执行 P0、未安装依赖、未加载 taxonomy、未发/评/更 issue，未 commit/push/PR/merge，未派发子 Agent。）
