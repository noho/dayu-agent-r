# UM-O20-F02 PR8 P0 计划独立 plan review

RUNTIME/PROVIDER/MODEL: codex/mimo/gpt-5
CANARY=mimo-d3df0beb

- 审查时间：2026-09-29 17:21:14（本机系统时钟 `date +%Y%m%d-%H%M%S` 实测 `20260929-172114`）。用户指定唯一 artifact 路径 `docs/reviews/plan-review-o20-pr8-mimo-20260929.md`；文件名不套用 skill 的 timestamp 文件名模板，是显式任务路径要求，timestamp 仍在本节留证。
- 审查对象：`docs/gateflow/upload-material-o20-xbrl-runtime-plan-20260929.md`，SHA-256 实测 `4b4e18a1cf499a05cec293c3afe334aa5afe5c6ba0358ff62a92722a5f8bd545`；冻结 E01 `docs/gateflow/upload-material-o20-e01-evidence-20260929.md`，SHA-256 实测 `f75a0c9b20e8ad152d5d0f24964b11f4baf87ffb8f11a313671fa69b6fe0401c`。两者均与任务锁定值一致，未触发 SHA 停止条件。
- binding scope contract：`docs/gateflow/upload-material-o20-xbrl-runtime-goal-20260929.md`。
- 已读：`AGENTS.md`、goal、总控 `docs/gateflow/upload-material-o20-xbrl-runtime-plan-review-adjudication-20260929.md`、Sol `docs/gateflow/upload-material-o20-f02-plan-fix-pr8-20260929.md`、上轮 `docs/reviews/plan-review-20260929-164018.md`、冻结 E01，以及本计划引用的 probe 摘要。
- 版本绑定源码：Docling 2.127.0（`/Users/leo/workspace/dayu-agent-r/.venv/lib/python3.11/site-packages/docling`，docling-core 2.96.0）与 Arelle 2.45.3（`/private/tmp/dayu-o20-f02-probe.AdlwrW/arelle2453/arelle`，wheel `arelle_release-2.45.3.dist-info/METADATA`）。实际包解释器为 `/Users/leo/workspace/dayu-agent-r/.venv/bin/python`；该解释器当前 `find_spec("arelle")` 为 `None`，Arelle 源码来自既有隔离 wheel 解包目录，不是生产安装。
- 边界遵守：只读核查；唯一新增物为本 artifact。未修改 plan、goal、E01、probe、旧 review、裁决、产品、依赖、锁、测试、README；未执行 P0 正式验收，未安装依赖，未发 issue，未 commit/push/PR/merge，未派发子 Agent。

## 1. Reviewed Target And Scope

本轮按 `planreview` 对 PR8-F1/F2 修订后的 P0 evidence/probe 计划做 adversarial review，重点反证：

1. 成功加载目标、失败/不可加载请求、原始逐引用事件三集合能否在同次 Docling/Arelle 运行中诚实对账；
2. 重复同目标引用、失败引用、XSD import/include、schemaLocation、zip/catalog entry 是否有逐事件真源，不能由聚合摘要、路径形状或 OS trace 冒充；
3. pipeline 返回 result、invalid-input 返回 result、构造/导入异常无 result 三条采集路径是否与 Docling 2.127.0 源码一致；
4. P0-A 三平台受控依赖、P0-C 强制隔离、真实无 typed 样本、公共能力声明上限和 Docling #4437 边界是否保持。

## 2. Assumptions Tested

### 2.1 PR8-F1 三集合和同次对账边界

**成功目标集合的来源基本准确。** Arelle `ModelDocument.load` 在 `ModelDocument.py:75` 规范化请求 URI，`ModelDocument.py:379` 以该 `normalizedUri` 构造文档，`ModelDocument.py:678` 将其登记到 `urlDocs`；`ModelDocument.uri` 与 `filepath` 分别保留请求身份和映射后目标。因而 `urlDocs` 可证明该次模型已成功登记的目标文档，但不能表示原始引用次数。

**`referencesDocument` 只能是聚合摘要。** `ModelDocument.py:1488-1496` 以目标 `ModelDocument` 为 key；重复同目标只合并 `referenceTypes`，仅在首个 `referringModelObject` 为空时补一个代表元素。它不保存第二个及后续元素、次数或每次 URI。

**成功 href 的重复事件可部分闭合。** `ModelDocument.py:1279-1281` 对 `discoverHref` 的每次成功 `doc` 追加 `(element, doc, id)` 到 `hrefObjects`；即使 `load` 因 `urlDocs` 命中缓存返回同一目标，两个不同来源元素仍各自进入 `hrefObjects`。结合原始 XML 的 `xlink:href` 文本，可对成功 `schemaRef`/`linkbaseRef` 的重复同目标事件核对元素、原始 URI、目标和次数。

**失败引用没有同等逐事件结构。** `ModelDocument.py:79-80` 对已登记失败 URI 直接返回 `None`；`ModelDocument.py:139-148` 只写入按规范化 URI 键控的 `urlUnloadableDocs`；`ModelDocument.py:1280-1281` 仅在 `doc is not None` 时追加 `hrefObjects`。因此失败集合只保存规范化失败请求/标记，不保存每个引用元素、每次尝试或重复失败次数。原始 XML 可列出失败候选，但不能单独证明每个候选在该次运行中实际尝试，也不能恢复被缓存短路的逐次结果。

**XSD import/include 与 schemaLocation 不适用 `hrefObjects` 覆盖外推。** `ModelDocument.py:1065-1105` 的 `importDiscover` 可按 namespace/basename 复用已加载文档或调用 `load`，最终只通过 `addDocumentReference` 聚合；`ModelDocument.py:457-469` 的 schemaLocation loader 返回目标文档但不建立逐元素事件。原始元素、base 和规范化规则可枚举，但当前结构不直接保存“该元素在该次实际解析到哪个目标”的事件边，尤其在 namespace 命中、重复 import/include 或失败时。

**zip/catalog 形状不等于 entry 实际读取。** `FileSource.py:482-492` 明言 `isInArchive(..., checkExistence=False)` 只表示 filepath 形状映射进 archive，不保证文件真实存在；计划要求的 entry 实际读取不能由 `filepath` archive 形状或 OS 对 zip 容器文件的读取证明。

**计划已设置诚实停点。** P0-B 明确把三集合分开，将 `referencesDocument` 降为聚合摘要；任一原始 URI/元素、规范化请求、成功/失败结果或实际目标不能闭合时，向量及 Docling 路径记 `blocked: run evidence unavailable`，禁止聚合摘要、原始 XML 单独推测、重放或 OS trace 补成 pass。这个 blocked 出口避免了 PR8-F1 的旧错误继续产生假通过。

### 2.2 PR8-F2 三条采集路径

**pipeline 阶段失败返回 result，且可保留同次 model。** `BasePipeline.execute` 在 `base_pipeline.py:79-112` 先建 `ConversionResult`，捕获 pipeline 内异常；`raises_on_error=False` 时写 `errors` 并返回。XBRL 使用 `SimplePipeline`，`SimplePipeline._unload` 继承 no-op，且 XBRL backend 在导出前已设置 `model_xbrl`，所以成功和 typed 导出阶段失败可及时快照 result/model。

**`DocumentLoadError` 形成 invalid-input result。** `xbrl_backend.py:111-187` 在 backend 构造中把 taxonomy、加载和导生异常包装为 `DocumentLoadError`；`document.py:303-330` 的 `_init_doc` 只把该类型记录为 `InputRejection`，其他异常重抛。`document_converter.py:835-870` 对 `in_doc.valid=false` 构造 `ConversionResult(status=FAILURE, errors=build_invalid_input_errors(...))`，不假定 `_backend` 或 model 存在。

**构造/导入异常确实可能无 result。** `xbrl_backend.py:95-99` 在 backend `try` 前直接抛 `ImportError`，其 cause 为缺 Arelle 的 `ModuleNotFoundError`；`document.py:322-323` 对非 `DocumentLoadError` 原样重抛。异常可在 `conv_input.docs`/输入构造迭代阶段逃出 `convert`，此时没有 `ConversionResult`。计划要求探针最外层保存异常类型、消息、cause 链、完整 trace、双流和版本并走 blocked，与源码边界一致。

**分类条件应按异常发生阶段理解。** `DocumentLoadError` 只有在 backend 构造/输入拒绝阶段才进入 invalid-input 路径；若未来某个 backend 在 `convert()` 内抛同类型，`BasePipeline` 会把它作为 pipeline error 返回 result。当前 XBRL 2.127.0 的该异常只在构造路径出现，计划的三路在本审查范围内成立。

### 2.3 P0-A、P0-C、真实样本、能力上限与 #4437

- **P0-A 三平台受控依赖**：计划要求 macOS/Linux/Windows 各自 fresh Python 3.11 venv、README 标准 editable 依赖、对应平台 lock、有依赖安装、`pip check` 和证据回读；任一平台无 runner 或失败即整体 blocked，不以 dry-run、交叉解析或 macOS 状态代替，也不提前选择生产 pin。该边界成立且没有把 E01 的 `jaconv` 二手报错恢复为版本真源。
- **P0-C 强制隔离**：计划要求每个真实平台先找到实际 OS/受信隔离机制，再对 C0-C8 做文件/网络 trace；`workOffline`、预扫描、临时目录、应用日志均不作为强制证明；任一平台不可用即 `blocked: isolation unavailable` 并停止产品实现/成功声明。该边界成立，有限矩阵也没有被写成未知读取向量的穷尽证明。
- **真实无 typed 样本**：计划明确要求许可清晰、Arelle 离线合法的真实财报 instance，并检查完整原件 `xbrldi:typedMember` 与 Arelle 加载后的实际 context 维度值；证明范围仅限该样本实际 context、引用形状、taxonomy、版本和配置。当前没有该真实样本，计划没有用合成样本替代，也没有把“taxonomy 中存在 typed 定义”误写成“instance 使用 typed”。
- **公共能力声明上限**：计划要求未来共享 capability 及 CLI/help/tool 同源投影只承诺已验证引用形状、无 typed 范围和部署条件，不能从一个正样本宣称一般 `XML_XBRL` 支持；无法诚实表达时 S1 硬停。这与当前 `dayu/documents/docling_runtime.py` 的 capability 真源和 `dayu/fins/upload_format_contract.py` 的消费边界一致，没有在下游文案补偿。
- **Docling #4437 边界**：计划把合法 typed 微型输入的导出崩溃锁定为 Docling owner，仅跟踪已发纯合成 issue #4437；不把 AAPL、缺 taxonomy explicit 分支或抽取准确率混成同一 bug，也不在本任务发送/评价/更新 issue。边界未漂移。

## 3. Findings

### 1-未修复-中-非 href 逐引用“事件”仍缺少可执行的同次逐边真源
- **位置**: P0-B“原始逐引用事件集合”、XSD import/include/schemaLocation 规则、zip/catalog entry 证据规则及 `blocked: run evidence unavailable` 出口。
- **问题类型**: 契约缺失 / 不可直接实施 / 测试缺口。
- **当前写法**: 计划要求逐个原始 XML/模型元素记录原始 URI、base、规范化 URI、是否成功及实际目标，并要求 XSD import/include、schemaLocation 与 zip entry 各自核对；不能闭合即 blocked。
- **反例/失败场景**: 两个 `xs:import`/`xs:include` 指向同一目标或同一失败 URI 时，Arelle 只在 `referencesDocument` 聚合首个代表元素，`urlUnloadableDocs` 只按 URI 存一次；第二次可能由 `load` 的 `urlDocs`/`urlUnloadableDocs` 缓存短路。此时原始元素清单能列出两个声明，但没有两个“实际尝试→结果→目标”的运行事件。catalog 映射后 `filepath` 也只能说明 archive 形状，不能证明具体 entry 被读取。
- **为什么有问题**: 计划的第三集合名称是“事件”，但其可得来源主要是原始声明清单和有损聚合结构；若执行者把它当完整事件日志，会再次把 multiplicity、失败尝试或 entry 读取写成已证。若严格执行计划的完整性门槛，这些非 href/zip 向量只能 blocked，无法形成正向 pass。
- **直接证据**: `ModelDocument.py:79-80,139-148,1279-1281,1488-1496`；`ModelDocument.py:1065-1105,457-469`；`FileSource.py:482-492`。计划 §5 同时明确禁止用聚合摘要、重放、OS trace 或 archive 形状补证。
- **影响**: P0-B 的绝对 import/linkbase/catalog 向量可能按计划稳定落为 blocked；若实现者绕过 blocked 用代码逻辑重算或 OS trace 猜映射，会产生不可审计的假完整证据并错误推进 capability/产品声明。
- **建议改法和验证点**: 把第三集合明确命名为“原始引用声明清单”，逐项允许 `attempt_observation=unknown`；只有成功 href 且 `hrefObjects` 同次保留元素时才写 `attempt_observation=observed`。对 import/include/schemaLocation、重复失败和 zip entry，要求直接的逐事件/entry 运行记录，否则立即 `blocked: run evidence unavailable`。P0 探针应新增重复失败 import/include 与 catalog entry 对账样本，验证不会把两个声明折叠成一次事件。
- **修复风险（低/中/高）**: 低。
- **严重程度（低/中/高/严重）**: 中。

## 4. Open Questions

1. goal/总控是否接受“非 href、重复失败和 zip entry 因缺少逐事件真源而稳定 blocked”作为 P0 的最终证据能力上限，还是要求在不加产品 hook 的前提下另行授权更高保真采集机制？
2. 真实无 typed 财报 instance 的来源、许可、管理员归档和三平台执行位置由谁提供；若不存在，goal 3 是否允许只形成受控合成机制证据而不形成真实产品成功声明？
3. 三平台各自由哪个可信 runner/受信隔离环境执行 P0-A/P0-C；若只有 macOS，是否由总控正式缩小支持平台承诺，而不是把 P0 长期留在 blocked？

## 5. Residual Risks And Suggested Tracking

- **R1 非 href 逐事件缺口**: 当前 Arelle 结构不能保证 import/include/schemaLocation、重复失败和 zip entry 的逐事件完整关系。跟踪去向：P0-B 按 finding 1 的 strict blocked 规则执行；后续若要 pass，回 goal/总控裁决证据机制或支持范围。
- **R2 P0 正向能力仍全部未证**: 三平台安装、三平台隔离、zip+catalog、真实无 typed instance、真实 CLI/material manifest 和财务内容准确性均未执行。跟踪去向：P0-A/B/C、后续 S1 implementation plan。
- **R3 typed #4437 只覆盖 Docling 导出 owner**: Arelle typed `memberQname=None` 与 Docling `memberQname.localName` 解引用是直接源码链；缺 taxonomy 的 explicit `None` 是另一分支。跟踪去向：#4437 只维护纯合成 typed 复现；其他分支独立验证，不合并归因。
- **R4 跨平台与版本漂移**: 结论绑定 Docling 2.127.0/Arelle 2.45.3 当前源码；Arelle/Docling 升级后必须重跑引用结构、三条 result 路径和隔离矩阵。跟踪去向：P0-A 候选版本记录与后续升级重跑。
- **R5 命令纪律未达到“全部 exit 0”**: 一次 `source .venv/bin/activate` 在当前 `/private/tmp/dayu-upload-o20-f02` 不存在 `.venv`，exit 127；一次 Python 计划检查命令因 zsh 引号错误在执行前 exit 1。后续改用实际包解释器和纠正引号后均 exit 0。两次 self-inflicted failure 未用于事实结论，但按任务要求如实披露。

## 6. Final Plan Review Conclusion

**pass-with-risks**。

本版已实质修复 PR8-F1 的错误证据承诺和 PR8-F2 的错误 result 假设：三集合被拆开，`referencesDocument` 被限制为聚合摘要，缺 `result` 的构造/导入异常进入最外层 blocked；P0-A/P0-C、真实无 typed 上限、公共 capability 边界和 #4437 owner 也未发现 goal drift。计划作为“证据/探针 P0 规格”可以交给执行者，因为它对不能闭合的同次关系明确 blocked，不把聚合摘要、OS trace 或 synthetic sample 冒充完整证据。

但 finding 1 仍是真实能力缺口：Arelle 2.45.3 对 import/include/schemaLocation、重复失败和 zip entry 没有完整的逐元素/逐 entry 运行事件真源，严格按本计划这些正式向量很可能只能 blocked，不能形成 P0-B 正向 pass。因此本结论仅允许进入 P0 取证，不授权 P0 正式验收、S1 产品实现、公开 `XML_XBRL` 能力扩张或 Docling/Arelle 上游问题改写；后续必须由 goal/总控裁决该证据上限和支持范围。

（本文件为本次任务指定唯一 artifact。）
