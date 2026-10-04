# UM-O20-F02：PR10-F1/F2 的 P0 计划预备 proposal

RUNTIME/PROVIDER/MODEL: codex/gpt-6-sol/gpt-6
CANARY=gpt-6-sol-2d49f6b0

- label：`pr197-xbrl-p0-plan-preparation-sol-20261001-01`；只读准备，未实施、未裁决新 findings、未推进 accepted gate。
- 状态：供 root 未来正式 plan rebind / 同版 double review 使用；不是正式 plan pass、P0 pass、产品支持或实现授权。
- branch：`codex/upload-material-oracle`；head `3a836a463aab3eeffb050facd592e614801d6ca9`；base `fac32ecbff9bfe792b63ee9667c8697826b631f4`。
- freeze：`workspace/tmp/pr197-xbrl-p0-plan-preparation-sol-20261001-01/freeze.json`，SHA-256 `0d3be37713f29c192b85b6cd47e699918c235de562b2f3f161c74d5f29341c7b`。
- 13 件 pinned 文件的 freeze/hash 与精确 head 的 Git blob 全部一致；只读 pinned 项目材料，没有读可变项目代码或在途报告。
- 证据目录：`workspace/tmp/pr197-xbrl-p0-plan-preparation-sol-20261001-01/evidence/`；`source-index.json` 记录来源、版本、SHA、字节数与 pin 核验。

## 1. 第一性原理：动机、必要性与 owner

已批准“按受控 XBRL 支持推进”保持有效，不要求用户重述或降低目标。候选文件仍经 Docling；财报内容准确性归上游。
真实缺口是部署/边界/成功承诺：pinned `docling_runtime.py:222–234` 声明 XML_XBRL 候选，`pyproject.toml:51–52` 依赖没有 xbrl extra。
本机 METADATA 确认 Docling / slim 2.127.0、core 2.96.0；slim 的 format-xml-xbrl extra 要求 `arelle-release>=2.38.17,<3.0.0`。
本机 site-packages 未找到 Arelle 包/对应 metadata。三份锁文件只窄查上述特定包，无匹配；这不是安装解析或三平台成功证据。
PR10-F1 的生命周期断点和 PR10-F2 的证据身份缺口确实会使旧 P0 采集方案无效；只补取证合同有必要。
当前 goal 必需：同次转换证据可核、未知不冒充已观察、三平台安装/边界验证、合法真实 instance 与成功 manifest。
未证必要：为每个元素建立产品事件总线、泛化 resolver/hook、第二套 parser、财报纠错、主动升级依赖或任选平台限制；本轮均不提出实施。

| 语义 | 唯一 owner / 本轮边界 |
| --- | --- |
| XBRL 加载、URI 规范化、模型与导出 | Docling/Arelle；以精确源码认定生命周期，不在 Dayu 下游补偿。 |
| 本产品 capability、taxonomy options、转换进程内完整性 | Documents runtime；未来 S1 才闭合输入/强制接口。 |
| 支持平台依赖与 lock | 项目安装契约；P0-A 三平台实装证据未取得，生产 pin 未定。 |
| workspace 边界、typed content failure、原子发布与 manifest | Fins/storage 公共契约；消费转换 outcome，不猜解析语义或制造成功。 |
| CLI/help/tool 候选文案 | `upload_format_contract` 从共享 capability 投影；不单入口改词掩盖部署条件。 |
| P0 同次身份、快照、分级与原始证据 | 独立 P0 探针/证据 owner；限探针作用域，绝不进入产品。 |

## 2. 本轮直接源码证据及其限度

安装源码只作为字节读取/复制，未 import Docling、未初始化模型。以下行号以证据副本为准。
- D1：`installed/docling/pipeline/base_pipeline.py:79–112,400–408`：execute 的 finally 先卸载，再返回；SimplePipeline 继承 ConvertPipeline。
- D2：`installed/docling/backend/xml/xbrl_backend.py:198–202`：unload 调用 model.close；其 SHA-256 为 `79d4fe812b8ed92e0fc4e9870227da56362165c271c5b60ada6f9905d0a09191`。
- A1：官方 `https://raw.githubusercontent.com/Arelle/Arelle/2.45.3/arelle/ModelXbrl.py:384–400`：close 清空 `__dict__`；SHA-256 `0cf0e4a94c6f85f64f1d55357071e6c65d950c482a58ab7bb8fb95a1678f3699`。
- A2：同版本 ModelDocument.py:73–82：urlDocs/失败 URI 缓存先短路；1255–1283：仅成功 doc 才追加 hrefObjects；1488–1497：referencesDocument 按目标聚合。
- A3：ModelDocument.py:1065–1106：import/include 有 namespace/URI 复用与条件 load；209–222：失败调用 error 并置 URI 聚合标记。
- A4：ModelXbrl.py:1085–1106、ErrorManager.py:124–141,239–251、Cntlr.py:419–452：日志可以带 refs，errors 保留代码；文本输出不是逐元素结构化事件。
- A5：FileSource.py:544–584 在 zip 分支读取具体 entry；未见该段保存每次 entry 成功读取账本。路径形状/访问 zip 容器不证明 entry 已读。
- D3：XBRL backend:111–188：默认 local/remote 均关，内部创建 Cntlr，复制 taxonomy 到临时目录；构造期可因 model.errors 拒绝，模型仅之后赋给 backend。
- D4/A6：XBRL backend:337–347 直接访问 memberQname.localName；官方 ModelInstanceObject.py:1498–1513 对 typed 返回 None。是源码分支证据，本轮没有重现。

Arelle 2.45.3 全部来自官方版本路径，只是源码证据，不冒称现装版本或预选生产 pin；其它文件 SHA/URL 见 source-index.json，关键摘录见 owner-source-excerpts.md。
原 rootadju 只采用最新 PR10-F1/F2 与相关机制要求，保持 accepted／未修复的旧裁决；本 proposal 不接受或关闭 finding。
上游 #4437 OPEN、无 comment、closedAt=null 是任务提供的 root 已核状态，本轮未重复查询/发送；不作为当前执行成功证据。

## 3. 修正合同一：PR10-F1 同次卸载前快照

旧计划“convert 返回后读 result.input._backend.model_xbrl”撤出未来采集方案；模型清空与临时目录清理均不能靠及时返回后读取补救。
仅提议在独立、单进程、无并发的 P0 探针中，对该精确版本 XBRL backend 的 unload 做作用域内包装：
1. 保存原方法身份；绑定本次入口 Path/Stream、唯一运行身份、PID/时间窗、输入与 taxonomy/package 哈希、实际配置、版本/源码 SHA。
2. 原 unload 调用前，将可得模型资料复制成独立普通值：成功目标集合、失败 URI 聚合集、来源文档/原始元素声明、实际可得结构化关系。
3. 不留 model/element/fileSource 活引用，不事后读已删除临时文件；快照只承诺其捕获的普通值与直接关系。
4. 快照异常独立归档为采集失败；仍执行原 unload 一次，不延迟关闭、不吞转换/清理异常，不把采集失败改成业务成功。
5. 最外层 finally 恢复原方法；分别记录快照、原 unload、恢复的完成/异常及身份核验；恢复未证或不能安全取得记录即 blocked。
6. convert 返回后只读 result 的 status/errors 等稳定结果并关联已保存快照；“卸载前记录”和“转换结果”各自有来源，不能互相推断。

最小未来同次验证（全部 not-run）：
- 一份自足合法无 typed 小 instance，先经独立 Arelle 离线合法性验证并留原始证据，再分别运行 Docling Path/Stream。
- 每一路只取该次卸载前快照，证实模型可读；原 unload 后核实模型已关闭、原方法恢复、快照仍可独立回读；保存完整 argv/双流/exit/异常与哈希。
- 合法 typed 已知失败候选仅检查 pipeline 失败也走卸载/恢复，不记成功；在同一失败运行中关联捕获点与结果。
- 坏 taxonomy 的构造期拒绝与缺 Arelle 的构造/导入异常分别检验采集出口；缺包探针只能在未来批准的隔离环境中做，不动共享 venv。

失败出口：有 result 时如实记 status/errors；DocumentLoadError 输入拒绝不假定 backend/model 存在；异常逃出时无 result，只记 cause/traceback/双流。
若构造期未保存模型、包装未触发、快照/恢复失败或关系不完整，对应 Docling 路径 `blocked: run evidence unavailable`。
独立 backend sibling / Arelle 重放只能标自己的运行身份，帮助研究机制；真实 Docling 同次证据仍 blocked，不冒称重放就是同次。
此合同解决采集窗口提案，不证明 wrapper 可行、目标实际读取、转换成功或安全边界，也不关闭 PR10-F1。

## 4. 修正合同二：PR10-F2 声明、聚合与直接事件分开

保持旧 PR9 strict blocked；不把一次失败文本、错误代码或 URI 缓存项分摊给多个元素。日志内存在 refs 的源码可能性不等于本次捕获了完整事件。
每条声明记录来源文档/元素身份及位置、引用机制、原始 URI、base 与适用规则；规范化/解析候选明确标为静态信息。
`attempt_observation=observed` 仅在该次模型/文件源中有能逐元素对账的结构化直接记录时填写，并附记录来源与同次关联。
仅声明、文本 logging/stderr、错误码、urlUnloadableDocs 聚合或 referencesDocument 摘要：`attempt_observation=unknown`。
urlDocs 表示模型登记的成功目标；hrefObjects 的成功发现关系须逐元素实测后才能用；observed 不自动证明内容读取。
具体 zip entry 读取另需该次可核的 entry 记录；catalog 声明、filepath archive 形状、OS 访问 zip 容器均不够。

| 最小未来探针（均 not-run） | 同次核验 | 失败出口 |
| --- | --- | --- |
| 两个不同 href 元素：`s.xsd` / `./s.xsd`，同目标成功 | 声明数、逐元素 hrefObjects、规范化 URI、目标身份；对照聚合 referencesDocument | 不能逐元素对账则 unknown；所需关系缺失则该路径 blocked。 |
| 首次缺失 href 与两个不同元素重复失败 href | 各声明、结构化记录有无、URI 聚合、原始文本分列；检查缓存短路 | 文本不能升级 observed；重复失败缺真事件即 unknown/blocked。 |
| 两个失败 xs:import；独立两个失败 xs:include | 各自声明、namespace/URI 短路与实际结构化记录，不能借用成功 href 的覆盖范围 | 任一必须核对元素缺真事件即 unknown/blocked。 |
| catalog 到 zip 内 entry 的最小向量 | 分列 catalog/映射声明、模型目标形状与具体 entry 读取记录 | entry 真记录缺失即 unknown/blocked，不用 OS 容器 trace 补 pass。 |

失败负向探针由合法基线最小变更，并记录预期缺失；不强求负样本合法性 exit0，也不拿其失败归因有效财报能力。
Docling 构造期可能不返回失败模型；此时不升级为更多产品 hook，不承诺从卸载包装取到该事件。
不把 schemaLocation/import/include/非 href 机制的证据覆盖视为已经完成；正式向量仍须逐项关系闭合。
OS trace 只陈述实际可见访问；独立 Arelle 重放只陈述其自身运行，均不补成 Docling 元素身份/entry 事件。
任一正式向量在任一路所需关系缺失，向量与路径均 `blocked: run evidence unavailable`；回 root 的证据机制/计划裁决。
此合同使未知可审计，不是 PR10-F2 已修复实测，也不要求产品化每元素事件/hook。

## 5. prior goal 映射、资源与下一步

| 原批准目标 / 旧 P0 | 本 proposal 保留的工作与资源状态 | 下一步与停止点 |
| --- | --- | --- |
| goal 1 / P0-A | Python3.11，macOS arm64/Linux x64/Windows x64 按标准安装+各 lock 的 fresh venv 实装、pip check、留存回读；2.44.8/2.45.3 选择重开，生产 pin 未定 | 本轮 not-run；平台 runner/安装执行资源待 root 核，三平台均 pass 才能 P0-A pass，不代选删平台/升级。 |
| goal 2 / P0-B | 保留同根散文件+可选顶层 catalog zip、混合引用图、独立绝对 schemaRef 与 XSD 内绝对 linkbaseRef；每份先合法性，再同输入 Path/Stream | 本轮 not-run；F1/F2 采集可行性尚未验证，真实 taxonomy 闭包/provenance/许可归档未取得；缺任一必需关系 blocked。 |
| goal 2 / P0-C | 保留三平台强制文件/网络边界、原 C0–C8 与平台专属项、取消/清理/子进程继承；workOffline 不是强制隔离 | 本轮 not-run；实际平台机制/trace 待 root 提供验证资源，不沿旧 sandbox 失败故事推定当前平台不可用。 |
| goal 3 / 后续 S1/S2 | 合法、完整 taxonomy 的真实财报 instance，真实 CLI 上传、原件/Docling 派生/source meta/权威 manifest 读回 | 当前 blocked；未冻结真实命令/产品接口。失败 typed content、stored_files=0、无本请求成功 manifest；不设财务准确率门槛。 |
| goal 4 / 证据归档 | 保留原 P0 主档/第二份逐文件哈希、大小、回读与遮蔽临时源后独立回读；同磁盘不是灾备，重启抽查未做 | 旧已删 Raw/临时输入不可恢复即如实缺项；将来新采集另标新运行，不冒称旧复现。真实私有资源仅管理员指定受控归档。 |
| goal 5 / 上游 | #4437 已有 issue；源码仍有 typed None 分支风险，旧 AAPL typed 仅复现候选 | 无新发/评论/补丁；有效真实无 typed 正样本未取得，或上游修复版本未验证则成功 blocked，不自选升级。 |

本轮已能做且已做：pin 来源/hash 核验、第三方 METADATA/源码读取、官方精确版本源证据留存、两个取证合同的只读修正 proposal。
本轮未取得：同次原型执行结果、三平台实装/锁解析、真实受信 taxonomy/合法财报与许可归档、平台强制隔离/trace、真实 CLI/manifest。
上述原型、转换、Arelle 验证、安装/dry-run、taxonomy 网络采集、pytest/pyright/cov 全部 not-run；没有产品/tests/README/依赖/旧控制文档变更。
旧 AAPL typed fixture 只沿 pinned final-ci 材料视为 #4437 复现候选，未打开输入、未确认现存内容、不算 positive。
root 所需资源决策列为：三平台可执行 runner/受控安装；可信完整 taxonomy 与财报来源/许可/持久归档；各支持平台强制隔离与审计条件。
证据机制若仍取不到必需真事件，仅列明确 blocked 供 root 裁决，不偷偷降低 prior goal/矩阵/同次要求或造升级代码。

## 6. S1 尚未冻结的边界与保留成功信号

原 taxonomy 形态草案不等于已批准 API。S1 必须明确 workspace 外/管理员受信根与 provenance 校验的唯一 owner、显式输入、可信传递与强制点。
Fins 持有 workspace 边界；Documents runtime 负责转换进程内完整性复验；管理员归档 owner 提供可核 provenance。校验到复制的变更窗口仍须闭合。
不能猜父目录、塞 extra payload、靠 CLI 文案/默认值补语义；OS 隔离 API 与 capability 的受控范围必须在直接验证后经同版 double review 冻结。
真实无 typed 样本仅证明其版本/配置/引用形状；公开声明不得外推一般 XBRL 或 typed 支持，内容准确性仍属上游。
最终成功保留：标准受控部署与公开候选声明一致、引用不越承诺边界、合法真实 instance 经 Docling 并正常提交、权威 storage 读回成功 manifest。
单个 ConversionStatus.SUCCESS、合成样本、标题文档、快照或 review 共识均不替代上述信号。

## 7. 本轮交付停点

只新增本 proposal 与独占证据；不触 Sol90509 F5 writer 或 Sol64454 G1 准备，不读取其在途产物、不派发子 Agent。
root 可在 F5 闭环后按原排程并行其它准备，另行正式 plan rebind 与同版 double review；本轮到此停止，不推进任何 gate。
PR197 保持现有 draft、由用户 merge；本轮没有 Git/PR/branch/worktree 状态变更。
