RUNTIME/PROVIDER/MODEL: claude/mimo/mimo-v2.6-pro[1m]
CANARY=mimo-a85e8c44

# UM-O20-F02 PR9 P0 计划修复性独立 plan review（MiMo/Claude 重试路）

- 审查时间：2026-09-29 18:15:06 CST。按 `planreview` 要求由本机系统时钟执行 `date +%Y%m%d-%H%M%S`，实测 `20260929-181506`。用户指定唯一 artifact 路径 `docs/reviews/plan-review-o20-pr9-mimo-claude-retry-20260929.md`，不套用 skill 的 timestamp 文件名模板；这是显式任务路径要求，timestamp 在本节留证。
- 审查对象：`docs/gateflow/upload-material-o20-xbrl-runtime-plan-20260929.md`。写前 `shasum -a 256` 实测 `9d99f7bdc7bb0feb103bee9f71a7d6097cb10ee0a3a7d782c9fda4b33c58906c`，与任务锁定值一致，未触发 SHA 停止条件。
- binding scope contract：`docs/gateflow/upload-material-o20-xbrl-runtime-goal-20260929.md`。已读 `AGENTS.md`、goal、总控裁决 `docs/gateflow/upload-material-o20-xbrl-runtime-plan-review-adjudication-20260929.md`、Sol PR9 fix `docs/gateflow/upload-material-o20-f02-plan-fix-pr9-20260929.md`、Sol PR8 fix `docs/gateflow/upload-material-o20-f02-plan-fix-pr8-20260929.md`，以及前次 MiMo 内容审查 `docs/reviews/plan-review-o20-pr9-mimo-20260929.md`（该路 JSONL 有失败事件未计 gate，本轮不复制其结论，全部事实另行独立核实）。
- 源码绑定：Arelle 2.45.3（`/private/tmp/dayu-o20-f02-probe.AdlwrW/arelle2453/arelle_release-2.45.3.dist-info`，实读 `ModelDocument.py`、`FileSource.py`、`ModelInstanceObject.py`）与 Docling 2.127.0（`/Users/leo/workspace/dayu-agent-r/.venv/lib/python3.11/site-packages/docling-2.127.0.dist-info`，实读 `backend/xml/xbrl_backend.py`、`datamodel/document.py`、`pipeline/base_pipeline.py`、`pipeline/simple_pipeline.py`、`document_converter.py`）。
- 边界遵守：只读核查并新增本 artifact；未修改 plan、goal、E01、旧 review、裁决、产品、依赖、锁、测试、README，未执行 P0，未安装依赖，未发/评/更新 issue（含 #4437），未 commit/push/PR/merge，未派发子 Agent，未调用 Goal tool 或进程列表。

## 1. Reviewed Target And Scope

本轮按 `planreview` 对 PR9-F1 修订后的 P0 evidence/probe 规格做修复性 adversarial review。任务指定重点反证四域：

1. **原始声明与 observed 同次逐元素证据**：第三集合是否仍可被静态声明冒称运行事件；`attempt_observation=observed` 是否只允许同次、逐元素、直接可对账证据；Arelle 2.45.3 的 `hrefObjects`/`urlUnloadableDocs`/`referencesDocument`/`importDiscover` 语义与计划的观察边界是否一致。
2. **重复失败 import/include/catalog entry blocked**：小探针是否对应真实源码行为（URI 失败缓存早退、namespace 短路、`isInArchive` 映射语义）；缺同次逐边/逐 entry 记录时是否硬性 `blocked: run evidence unavailable`。
3. **PR8 三集合及异常路径**：成功加载目标、失败请求、原始引用声明清单三集合分离；三条 result/无 result 异常路径是否与 Docling 2.127.0 源码一致。
4. **P0-A/C 与 #4437/真实样本边界**：逐平台安装与生产 pin gate、OS 强制隔离与 trace、typed 与 explicit 分支分离、真实无 typed 正样本范围限定与公共 capability 声明上限是否保持，无范围漂移。

## 2. Assumptions Tested

### 2.1 第三集合与 observed 门槛（重点域 1）

**原问题真实存在，PR9 修订方向与源码一致。** 独立实读确认：

- `ModelDocument.load`（`ModelDocument.py:75-79`）先按规范化 URI 查 `urlDocs` 成功缓存或 `urlUnloadableDocs` 失败缓存并早退；失败登记按 URI 存布尔标记（`:104`、`:146`），均非逐元素事件表。
- `discoverHref`（`:1255-1283`）仅在 `doc is not None` 时把 `(element, doc, id)` 逐元素追加 `hrefObjects`（`:1279-1281`）；失败 href 返回 tuple 但不进入该结构。
- `addDocumentReference`（`:1488-1496`）以目标 `ModelDocument` 为 key；同目标重复引用只合并 `referenceTypes` 并只保留首个 `referringModelObject`，multiplicity 与后续元素丢失。
- `importDiscover`（`:1065-1105`）对 include/redefine 取 `self.targetNamespace`，可因 namespace 为空而不发起加载；成功路径可按 `namespaceDocs`/URI 命中短路，仅进聚合 `addDocumentReference`，不产生逐元素 load 事件。
- `loadSchemalocatedSchemas`（`:1118-1134`）按 namespace 命中 `namespaceDocs` 即跳过，schemaLocation 声明同样无通用逐元素事件表。
- `FileSource.isInArchive(..., checkExistence=False)`（`FileSource.py:482-492`）源码注释明示 `True only means that the filepath maps into the archive, not that the file is really there`；`load` 在 `isInArchive(mappedUri)` 时直接把 archive 形状路径赋给 `filepath`（`ModelDocument.py` load 中段），不证明 entry 内容已读。

**observed 门槛写法闭合了伪造路径。** 计划 §5 已把第三集合命名为“原始引用声明清单”，逐条携带 `attempt_observation=observed|unknown`；只有同次直接事件可与该声明元素逐项对账才填已观察状态，`observed` 不承诺目标内容或 zip entry 已读。失败 href、重复失败、非 href 机制与 zip entry 缺直接记录时，禁止从 `urlUnloadableDocs`、`referencesDocument`、路径形状、静态 XML、重放或 OS zip 容器访问反推 observed；`referencesDocument` 明确降级为聚合摘要且不得作 `attempt_observation` 真源。静态声明冒充运行事件的口子在文本层面已闭合，未触发“观察语义仍可由静态声明冒充”的停止条件。

### 2.2 重复失败与 catalog entry 小探针（重点域 2）

计划新增小探针与源码行为精确对应：两个不同 `xs:import`/`xs:include` 同指不存在目标时，第一次尝试进入 `urlUnloadableDocs` URI 表，第二次经 `load` 失败缓存早退（`ModelDocument.py:77-79`）不产生新事件，import 另有 namespace 短路（`:1087-1099`）；探针明确“不能把一个 `urlUnloadableDocs` 项分配成两次已观察失败”。catalog entry 探针分记 catalog 声明、映射目标形状、同次具体 entry 读取记录三者，并禁止以 `filepath` archive 形状或 OS 对 zip 容器访问推断 entry 已读——与 `isInArchive` 注释语义一致。小探针只检验采集能力、不降低正式向量门槛；缺同次逐边/逐 entry 记录即 `blocked: run evidence unavailable` 的硬出口存在。该域处置正确；非 href 成功边的采集缺口见 Finding 1。

### 2.3 PR8 三集合（重点域 3）

三集合分离经源码复核成立：成功加载目标集合遍历 `model_xbrl.urlDocs`（key 为规范化请求 URI，`filepath` 为映射目标或 archive-entry 形状，不代表引用次数或 entry 读取）；失败/不可加载请求集合存 `urlUnloadableDocs`（URI 聚合、无完整元素、且 skipLoading 等路径不登记，确实不保证记录全部未加载尝试）；第三集合是静态声明清单加有证据约束的观察字段。`referencesDocument` 仅为按目标聚合摘要。未发现三集合互相冒充或由聚合结构补齐 multiplicity 的写法。收集范围问题见 Finding 1(b)。

### 2.4 PR8-F2 三条异常采集路径（重点域 3）

Docling 2.127.0 源码独立验证三路划分：

1. `SimplePipeline._build_document`（`simple_pipeline.py:29-44`）直接调用 `backend.convert()` 且无局部捕获；typed 导出 `AttributeError`（`xbrl_backend.py:344` 对 `dim_value.memberQname.localName` 无 None 防护）冒泡到 `BasePipeline.execute`（`base_pipeline.py:83-108`），`raises_on_error=False` 时记 PIPELINE `ErrorItem`、`status=FAILURE` 并返回 `ConversionResult`；`SimplePipeline` 不覆写 `_unload`（基类 `base_pipeline.py:185-186` 为 `pass`），`self.model_xbrl`（`xbrl_backend.py:181`）在返回后仍可及时快照。
2. `XBRLDocumentBackend.__init__` 把构造期异常包成 `DocumentLoadError`（`xbrl_backend.py:183-187`）；`InputDocument._init_doc`（`datamodel/document.py:303-330`）只捕获该类型形成 BACKEND_FAILURE rejection（保留 `original_error`），`_execute_pipeline` 无效输入分支返回带 `build_invalid_input_errors` 的失败 result（`document_converter.py:861-870`），卸载用 `getattr(in_doc, "_backend", None)`，不假定 `_backend`/模型存在。
3. 缺 Arelle 的 `ImportError` 在包装 try 之前抛出（`xbrl_backend.py:95-99`），`_init_doc` 对非 `DocumentLoadError` 原样重抛（`document_converter` 输入构造期逃出 `convert`），无 result；探针最外层须记录异常链/traceback/双流，不得读取虚构的 `result.errors`。

计划明确 `raises_on_error=False` 不是构造期全局非抛出保证、三类由运行时观察分类，与源码一致。

### 2.5 P0-A/C、真实样本与 #4437 边界（重点域 4）

- **P0-A**：逐平台 fresh Python 3.11 实装、`pip check`、证据回读分别记 pass/`blocked: runner unavailable`/`blocked: install/check failed`/`blocked: evidence unavailable`；macOS dry-run 不顶替安装，生产 pin 需三平台全 pass，无任意超期、不自行缩小支持范围。无漂移。
- **P0-C**：每平台先找到实际生效的 OS/受信隔离机制，再以有限矩阵 + 每个已尝试向量的 OS 文件/网络 trace 验证；`workOffline`、status、应用日志、预扫描均不算通过；失败记 `blocked: isolation unavailable` 回 goal/总控。无漂移。
- **typed/explicit 分支**：`ModelInstanceObject.py:1503-1513` 实读确认 `memberQname` 仅在 `isExplicit and xValid >= VALID` 时返回值，typed 按设计为 None，失验 explicit member 同样为 None——计划 §1 把两支分开归因、禁止合并，与源码一致；#4437 只覆盖 typed 导出崩溃，计划未把失验 explicit/taxonomy 问题并入。
- **真实正样本**：Arelle 离线 `--validate --validationExitCode` exit0 且留证先行，再同 instance 跑 Docling Path/Stream；无 typed 结论限于该 instance 实际 context/维度值、引用形状、taxonomy、版本与配置；AAPL typed、合成探针、空标题 `DocumentStream SUCCESS` 均不可替代真实 CLI/material manifest 成功。S1 公共 capability/CLI/help/tool 投影以上限诚实表达、无法表达则硬停重新双路复审。无漂移。
- **#4437 与授权**：总控已按条件授权用纯合成证据提交上游 issue，本轮不发/评/更；后续补证先复核并对账，不重开。与裁决一致。

## 3. Findings

### 1-未修复-中-同次直接事件的允许来源与收集范围未闭合，import 边将结构性 blocked

- **位置**: 计划 §5 P0-B 当次模型证据探针段（“内部属性链 … 仅为版本绑定的 P0 探针入口”“`referencesDocument` … 不得用作逐声明事件、次数或 `attempt_observation` 真源”“重复失败、非 href 的 import/include/schemaLocation 或 zip entry 若缺对应的同次逐边/逐 entry 运行记录，该向量及该 Docling 路径记 `blocked: run evidence unavailable`”）；§5 混合引用图与真实样本步骤。
- **问题类型**: 契约缺失 / 不可直接实施（证据采集路径欠规格）
- **当前写法**: ①允许的同次直接事件源事实上被收窄为五个内部属性（`result.input._backend.model_xbrl`、`urlDocs`、`urlUnloadableDocs`、`hrefObjects`、`referencesDocument`）加 OS trace，其中 `referencesDocument` 被全禁作观察真源、`urlDocs` 命中不得推断逐声明调用 `load`；②非 href 的 import/include/schemaLocation 缺逐边记录即整向量 blocked；③`hrefObjects` 与 `referencesDocument` 未写明须按每个来源文档（各 `ModelDocument` 实例属性，`ModelDocument.py:681,683`）遍历收集。
- **反例/失败场景**: Arelle 2.45.3 对成功 `xs:import` 边没有任何逐元素事件源（`importDiscover` 短路后只进聚合 `addDocumentReference`，唯一逐元素痕迹 `referringModelObject` 又被计划全禁）；探针侧若按字面只用五个属性，混合引用图（XSD 绝对 URL import → catalog 包内 XSD，即 AAPL 同构形态、PR2-F1 修复的核心验证对象）与任何真实财报（DTS 闭包普遍含 `xs:import`）的 Docling 路径将**必然**记 `blocked: run evidence unavailable`，不是“证据碰巧不可得”而是契约预先判死；P0-B 无法回答“同根散文件+catalog zip 组合布局是否可用”这一本 slice 的核心问题，goal 3 亦被证据契约而非机制事实阻断。附带：vector ② 的 appinfo 绝对 `linkbaseRef` 的 href 事件保存在**该 XSD 文档**的 `hrefObjects`，若实现者只读入口 instance 文档的 `hrefObjects`，会把可对账事件误判缺失。
- **为什么有问题**: PR8-F1/PR9-F1 的裁决措辞是“若逐边完整来源不可得则 blocked”，把可得性当作 P0 实证问题；但源码事实使 import 成功边的不可得是静态可判的，计划却未在规格里作出对应处置（允许替代采集源，或显式接受该类向量 blocked 并限定 P0-B 只回答 href/catalog 形态问题）。两种处置都不破坏反伪造纪律，但缺任何一种，实施 Agent 只能机械产出 blocked，随后按 §5/§6 触发回 plan/fix 与 S1 硬停，多烧一轮 gate 周期；若总控把 blocked 误读为机制不可达，还会错误收缩接口承诺。
- **直接证据**: `ModelDocument.py:1065-1105`（importDiscover 短路与聚合写入）、`:1488-1496`（`addDocumentReference` 保首个 `referringModelObject`、丢 multiplicity）、`:681,683`（`referencesDocument`/`hrefObjects` 为 `ModelDocument` 实例属性而非 `model_xbrl` 级）、`:1279-1281`（hrefObjects 仅成功 href 逐元素）；计划 §5 第 60、62 段原文（“`referencesDocument` … 不得用作逐声明事件、次数或 `attempt_observation` 真源”“内部属性链 … 仅为版本绑定的 P0 探针入口”“非 href 的 import/include/schemaLocation … 该向量及该 Docling 路径记 blocked”）。
- **影响**: P0-B 核心向量与真实样本向量被契约性判死、后续返工与 S1 硬停风险后移；执行者可能误把“无允许来源”写成“机制不可达”，驱动错误的 capability 收缩。
- **建议改法和验证点**: 二选一并写进 §5：(a) 明确同进程调用级拦截（探针侧对 `load`/`discoverHref`/`importDiscover` 记录 referringElement、URI、返回值的当次日志）属于允许的“进程内可核加载/映射记录”，且它不是产品 hook；同时把 `referencesDocument` 的禁用范围收窄为“不得作次数/multiplicity/第二元素真源”，允许其 `referringModelObject` 作为唯一成功边的逐元素事件源；(b) 明确接受 import/include/schemaLocation 成功边无事件源、含此类边的向量（含混合引用图与真实样本 Docling 路径）预期结果就是 blocked，并把 P0-B 可回答的问题限定为 href 与 catalog/zip 形态。另补一句：`hrefObjects`/`referencesDocument` 须按 `urlDocs` 中每个来源文档分别收集。验证点：小探针增一个**成功**单 `xs:import` 样本，实测声明元素与事件的可对账性，按选定处置断言 `observed` 或预期 blocked。
- **修复风险（低/中/高）**: 低（纯 P0 规格文字，不动产品/依赖）。
- **严重程度（低/中/高/严重）**: 中

## 4. Open Questions

1. 失败 href 样本在 Docling 路径落在采集路径①还是②取决于运行时事实：若 Arelle 把 `FileNotLoadable` 记入 `model.errors`，`xbrl_backend.py:178-179` 会以 `ValueError` 走 `DocumentLoadError`、无 model 可快照；若错误未入 `model.errors`（PR8 探针记录的 SUCCESS+`errors=[]`+`urlUnloadableDocs` 条目即此形态），则可在①快照。探针必须按运行时观察分类，不得静态预设；该分歧不影响计划文本的 blocked 出口。
2. 原始 XML 元素与 Arelle `ModelObject` 的稳定对账键如何在快照前形成并独立回读；不能唯一对账时必须保持 `unknown`/blocked，不得用 URI、位置近似或元素顺序补证。
3. Finding 1 的处置（允许调用级拦截记录 / 接受 import 边预期 blocked）由谁裁决：按 §5“回 plan/fix”惯例应由总控在下一 fix 轮裁决，不应由 P0 执行者自行放宽。
4. Linux/Windows 可信 runner、三平台强制隔离机制、真实无 typed 合规样本与管理员 taxonomy provenance 归档的提供方仍未定；缺任一项继续 P0/goal/总控 blocked，不自行缩小产品范围。

## 5. Residual Risks And Suggested Tracking

- **R1 非 href 证据能力上限**：即使采纳 Finding 1 的 (a) 处置，Arelle/Docling 2.45.3/2.127.0 也没有内建的 import/include/schemaLocation/zip-entry 逐事件真源，采集依赖版本绑定的探针手段。跟踪去向：P0-B 小探针实测与 goal/总控证据机制裁决。
- **R2 P0 仍未执行**：三平台安装、隔离、zip+catalog、真实无 typed instance、真实 CLI/material manifest 均未证。跟踪去向：P0-A/B/C 与后续 S1 implementation plan，不因本 review 转 pass。
- **R3 版本绑定漂移**：`hrefObjects`/`urlDocs`/`urlUnloadableDocs`/`referencesDocument`、`result.input._backend.model_xbrl` 与 SimplePipeline 不卸载行为均绑定当前版本。跟踪去向：P0-A 候选记录；升级 Docling/Arelle 后重跑采集探针。
- **R4 typed 与 explicit 分支混淆**：#4437 只覆盖 typed；`xValid<VALID` 的 explicit member 同样 `memberQname=None`，必须独立对照完整 taxonomy，不合并归因。跟踪去向：独立 P0-B 对照。
- **R5 元素对账实现风险**：若执行者把 URI、source position 或列表顺序当直接事件，可能错误标 observed。跟踪去向：P0-B 小探针先验证 identity 对账，不能闭合即 blocked。
- **R6 模型快照时序**：`XBRLDocumentBackend.__init__` 的 `TemporaryDirectory` 在构造完成即清理，模型 `filepath` 指向的临时树事后不可重读；快照必须在 `convert` 返回后、释放结果/模型前完成。跟踪去向：P0-B 探针实现按计划“及时快照”执行。

## 6. Command And Tool Audit

按失败/部分异常口径完整披露：

| 命令/工具 | 结果 | 是否影响结论 |
| --- | --- | --- |
| Bash（读取 `ModelDocument.py` schemaLocation/importDiscover 段的并行调用） | 未执行即失败：auto-mode 安全分类器超时（`mimo-v2.6-pro[1m] is temporarily unavailable (timed out)`），命令未运行 | 不影响；改用只读 Read 工具取得同一源码段，内容完整 |
| `find /private/tmp /Users/leo/workspace/dayu-agent-r -maxdepth 6 -name 'ModelDocument.py'` 等 | exit 0，命中 Arelle 2.45.3 解包目录；此前一次 `find -maxdepth 3/5` 无匹配（深度不足） | 不影响；扩大深度后定位成功 |
| 其余只读命令（`ls`/`shasum`/`wc`/`grep`/`sed`/`date`） | exit 0 | 无 |

披露说明：本轮另有一次工具编排未遂（上述分类器超时）之外无其它失败工具；未执行测试或 pyright（本轮只读、无产品/测试代码修改，且任务禁止执行 P0 与安装依赖）；未调用 Goal tool 或进程列表；未派发子 Agent。GitHub issue #4437 未读取（本轮仅核计划边界文本与裁决一致性，且用户禁止发/评/更 issue），相关事实以总控裁决登记为准。

## 7. Final Plan Review Conclusion

**pass-with-risks**。

本结论仅表示 PR9 修订后的 P0 evidence/probe 规格在反伪造纪律上已闭合、可交给 P0 取证执行；Finding 1（中，未修复）要求下一 fix 轮在 §5 明确同次直接事件的允许来源/收集范围，或显式接受 import 边预期 blocked 并限定 P0-B 回答范围，否则混合引用图与真实样本的 Docling 路径将被契约性判死、白烧一轮 gate。本结论不表示 P0 已通过，不授权 S1/S2 产品实现、生产 pin、公开 `XML_XBRL` 能力扩张、taxonomy 安全边界已生效或真实上传成功。任务停止条件未触发：SHA 匹配；静态声明不能冒充 observed（observed 须同次逐元素直接事件，静态清单一律 `unknown`，重复失败/非 href/zip entry 缺记录即 blocked）；本结论不要求无证据 pass。执行者必须保留 strict blocked 语义，不得用静态 XML、聚合摘要、重放、OS zip 容器访问或推断性元素匹配补成通过。

（本文件为本次任务指定唯一新增 artifact。）
