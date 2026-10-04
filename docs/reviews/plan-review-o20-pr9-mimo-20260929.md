RUNTIME/PROVIDER/MODEL: codex/mimo/gpt-5
CANARY=mimo-2f7392c2

# UM-O20-F02 PR9 P0 计划独立 plan review（MiMo 路）

- 审查时间：2026-09-29 17:47:42 CST。按 `planreview` 要求由本机系统时钟执行 `date +%Y%m%d-%H%M%S`，实测 `20260929-174742`。用户指定唯一 artifact 路径 `docs/reviews/plan-review-o20-pr9-mimo-20260929.md`，该文件名不套用 skill 的 timestamp 文件名模板；这是显式任务路径要求，timestamp 在本节留证。
- 审查对象：`docs/gateflow/upload-material-o20-xbrl-runtime-plan-20260929.md`。写前 SHA-256 实测 `9d99f7bdc7bb0feb103bee9f71a7d6097cb10ee0a3a7d782c9fda4b33c58906c`，与任务锁定值一致，未触发 SHA 停止条件。
- binding scope contract：`docs/gateflow/upload-material-o20-xbrl-runtime-goal-20260929.md`。已读 `AGENTS.md`、goal、总控 `docs/gateflow/upload-material-o20-xbrl-runtime-plan-review-adjudication-20260929.md`、Sol PR9 fix `docs/gateflow/upload-material-o20-f02-plan-fix-pr9-20260929.md`，以及前轮同版两份 review `docs/reviews/plan-review-o20-pr8-mimo-20260929.md`、`docs/reviews/plan-review-o20-pr8-kimi-20260929.md`。
- 为核对 PR8-F1/F2 的连续性，另只读核对 Sol PR8 fix `docs/gateflow/upload-material-o20-f02-plan-fix-pr8-20260929.md` 与 `docs/reviews/plan-review-o20-f02-rereview3-mimo-20260929.md`。直接源码绑定 Docling 2.127.0 与 Arelle 2.45.3；GitHub issue #4437 只读核对。
- 边界遵守：只读核查并新增本 artifact；未修改 plan、goal、E01、旧 review、裁决、产品、依赖、锁、测试、README，未执行 P0，未安装依赖，未发/评/更 issue，未 commit/push/PR/merge，未派发子 Agent。

## 1. Reviewed Target And Scope

本轮按 `planreview` 对 PR9-F1 修订后的 P0 evidence/probe 规格做 adversarial review。重点反证：

1. 第三集合是否仍把静态引用声明冒称同次运行事件，`attempt_observation=observed` 是否只允许同次、逐元素、直接可对账证据。
2. 重复失败 `xs:import`/`xs:include` 与 catalog/zip entry 小探针是否能暴露缓存、短路、聚合和 entry 读取缺口；不能闭合时是否硬性 `blocked: run evidence unavailable`。
3. PR8-F1 三集合和 PR8-F2 三条 result/无 result 异常路径是否与 Docling 2.127.0/Arelle 2.45.3 源码一致。
4. P0-A/P0-C、真实无 typed 样本、公共 capability 声明上限与 Docling #4437 边界是否保持，未发生 P0 或产品范围漂移。

## 2. Assumptions Tested

### 2.1 静态声明清单与同次逐元素观察

**原问题真实存在，PR9 修订方向正确。** Arelle `ModelDocument.load` 先按规范化 URI 查询 `urlDocs` 或 `urlUnloadableDocs` 并可直接早退；失败表只按 URI 保存布尔标记。它们都不是逐引用元素事件表。`discoverHref` 仅在 `doc is not None` 时把 `(element, doc, id)` 追加到 `hrefObjects`，因此成功 href 的重复元素可逐项保留，失败 href 不进入该结构。`addDocumentReference` 以目标 `ModelDocument` 为 key，重复同目标只合并引用类型并保留首个代表元素。

**当前第三集合不再冒称事件。** 计划 §5 已改名为“原始引用声明清单”，每条显式携带 `attempt_observation=observed|unknown`；只有同次直接事件能与该声明元素逐项对账时才可填 observed。`observed` 只承诺尝试/发现关系，不承诺目标内容或 zip entry 已读；读取仍要求独立直接记录。失败 href、重复失败、非 href import/include/schemaLocation 和 zip entry 缺直接记录时，均不得从 `urlUnloadableDocs`、`referencesDocument`、路径形状、重放或 OS trace 反推为 observed。

**逐元素关系的源码边界与计划一致。** `importDiscover` 可按 namespace/已加载文档短路，成功主要进入聚合 `addDocumentReference`；`loadSchemalocatedSchema` 也没有通用逐元素事件表。`FileSource.isInArchive(..., checkExistence=False)` 的返回值只表示路径映入 archive，源码注释明确不保证文件真实存在，更不证明具体 entry 内容被读取。因此计划要求非 href、重复失败和 catalog entry 在无同次直接记录时 blocked，是必要的保守边界，不是可省略的措辞。

### 2.2 重复失败与 catalog entry 小探针

计划新增两个独立小探针：两个不同 `xs:import` 同指不存在目标、两个不同 `xs:include` 同指不存在目标；以及 catalog 声明、映射目标形状、具体 entry 读取记录三者分开。探针明确检查失败缓存/namespace 短路，禁止把一个 `urlUnloadableDocs` 项分配成两次 observed，也禁止以 `filepath` 或 OS 对 zip 容器的访问推断 entry 已读。

这与 `load` 的 URI 缓存早退、`urlUnloadableDocs` 的 URI 聚合和 `isInArchive` 的映射语义直接对应。小探针只验证采集能力，不降低正式向量门槛；若运行时仍无逐边/逐 entry 真源，计划明确把对应向量及 Docling 路径记为 `blocked: run evidence unavailable`。该处置闭合了 PR9-F1 的核心反例。

### 2.3 PR8-F1 三集合

三集合现已严格分离：`urlDocs` 只证明该次模型登记的成功目标，key 是规范化请求 URI，`filepath` 是映射目标或 archive-entry 形状，不代表引用次数或 entry 读取；`urlUnloadableDocs` 只保存失败/不可加载请求，不保存完整元素和全部尝试；第三集合是静态声明清单加有证据约束的观察字段。`referencesDocument` 被降级为按目标聚合摘要。未发现三集合互相冒充或由聚合结构补齐 multiplicity 的剩余写法。

### 2.4 PR8-F2 三条异常采集路径

Docling 2.127.0 源码支持计划的三路划分：

1. `convert(source, raises_on_error=False)` 下，pipeline 成功或 pipeline 阶段异常返回 `ConversionResult`，可记录 `status`、`errors` 和仍可取得的 backend/model。
2. `XBRLDocumentBackend` 将构造/加载异常包装为 `DocumentLoadError` 时，`InputDocument._init_doc` 只捕获该类型并形成 invalid-input rejection；`_execute_pipeline` 返回带错误的失败 `ConversionResult`，不假定 `_backend` 或模型存在。
3. 缺 Arelle 的 `ImportError` 及其他非 `DocumentLoadError` 会在输入构造期继续抛出，`convert(..., False)` 没有 result。计划要求探针最外层保留异常类型、消息、cause 链、traceback、双流和哈希，并禁止读取虚构的 `result.errors`。

计划还明确 `raises_on_error=False` 不是构造期全局非抛出保证。三条路径由运行时观察分类，不由静态源码假称已经 P0 实测，符合 PR8-F2 的 owner 边界。

### 2.5 P0-A/C、真实无 typed、公共能力上限与 #4437

P0-A 只有 macOS/Linux/Windows 各自 fresh Python 3.11 实装、`pip check` 和证据回读均通过才可选生产 pin；缺 runner 或缺平台证据一律 blocked，未以 macOS 代替其它平台。P0-C 要求每个平台实际 OS/受信隔离机制强制文件与网络边界，并用有限矩阵和 trace 验证；`workOffline`、状态、日志或预扫描不作为安全通过证据。当前 macOS `sandbox-exec` 不可用、无 Linux/Windows runner，计划保持 blocked，无成功声明漂移。

真实正样本必须是许可清晰、Arelle 先验证合法、完整原件无 typed 且引用闭包可审计的财报 instance；无 typed 结论只限该 instance 实际 context/维度值、引用形状、taxonomy、版本和配置。合成样本、AAPL 或空标题 `DocumentStream SUCCESS` 均不能替代真实 CLI/material manifest 成功。公共 capability 及 CLI/help/tool 投影不得超过已验证无 typed 范围和部署条件；含 typed 支持须待上游修复和同等真实重测。

GitHub issue #4437 当前为 open，标题和正文只覆盖合法 typed dimension 在 Docling `memberQname.localName` 的崩溃，并明确 missing taxonomy 导致的 invalid explicit member 是另一原因。计划未把失验 explicit member 或 taxonomy 问题并入该 issue，也未把 #4437 当作 Dayu 产品成功，边界一致。

## 3. Findings

无新增 material findings。

PR9-F1 已把第三集合从“运行事件”纠正为“静态声明清单”，并为 observed 设置同次逐元素直接证据门槛；重复失败 import/include 与 catalog entry 小探针和 strict blocked 出口均存在。PR8-F1/F2、P0-A/C、真实无 typed、公共 capability 上限与 #4437 边界未发现回退。未触发用户给定停止条件。

## 4. Open Questions

1. P0-B 执行时，原始 XML 元素与 Arelle model element 的稳定对账键如何在快照前形成并独立回读；若不能唯一对账，必须保持 `unknown`/blocked。该问题不授权用 URI、位置近似或元素顺序猜测补证。
2. 失败 href、非 href import/include/schemaLocation 与 zip entry 在不加产品 hook 的前提下可取得何种同次直接事件粒度；无直接事件即按计划 blocked，不作为本 plan gate 的隐藏前提。
3. Linux/Windows 可信 runner、三平台强制隔离机制、真实无 typed 合规样本和管理员 taxonomy provenance 归档由谁提供；缺任一项时继续 P0/goal/总控 blocked，不自行缩小产品范围。

## 5. Residual Risks And Suggested Tracking

- **R1 证据能力上限**：Arelle 2.45.3 没有完整的非 href、重复失败和 zip entry 逐事件真源，正式向量可能稳定 blocked。跟踪去向：P0-B 运行记录与 goal/总控证据机制或支持范围裁决。
- **R2 P0 仍未执行**：三平台安装、隔离、zip+catalog、真实无 typed instance、真实 CLI/material manifest 均未证。跟踪去向：P0-A/B/C 与后续 S1 implementation plan，不因本 review 转 pass。
- **R3 版本绑定漂移**：`hrefObjects`、`urlDocs`、`urlUnloadableDocs`、`referencesDocument` 与 Docling result 路径均绑定当前版本。跟踪去向：P0-A 候选记录；升级 Docling/Arelle 后重跑采集探针。
- **R4 typed 与 explicit 分支混淆**：#4437 只覆盖 typed；missing/invalid taxonomy 的 explicit `memberQname=None` 必须独立验证。跟踪去向：独立 P0-B 对照，不合并归因。
- **R5 元素对账实现风险**：若执行者把 URI、source position 或列表顺序当作直接事件，可能错误标 observed。跟踪去向：P0-B 小探针先验证 identity 对账，不能闭合即 blocked。

## 6. Command And Tool Audit

按“非零退出命令”口径完整披露；另有两项 exit 0 的部分异常也列出，避免遗漏。

| 命令/工具 | 结果 | 是否影响结论 |
| --- | --- | --- |
| `get_goal` 工具 | 失败，返回 `Goal tools require a persistent thread.` | 不影响；改读本地 goal artifact，并将其作为 binding scope contract。 |
| `find .venv/lib/python3.11/site-packages -maxdepth 2 -type d \( -name 'docling*' -o -name 'arelle*' \) -print` | exit 1，当前 worktree 不存在 `.venv/lib/python3.11/site-packages` | 不影响；与计划 §7“本 worktree 无 `.venv`”一致，随后直接读取指定版本绑定源码目录。 |
| `rg -n "memberQname\|class ModelDimensionValue\|typedMember\|qnameDims" .../ModelInstanceObject.py .../ModelDimensionValue.py .../ModelXbrl.py` | exit 2，误猜的 `ModelDimensionValue.py` 不存在；同命令仍在 `ModelInstanceObject.py`/`ModelXbrl.py` 返回直接命中 | 不影响；随后直接读取 `ModelInstanceObject.py:1436-1515`，确认 `ModelDimensionValue.memberQname` 定义位置和 typed 返回 None 的分支。 |
| `rg --files docs .agents .codex \| rg '(goal\|adjudicat\|sol\|review\|upload-material-o20\|pr9\|PR9\|p0\|P0\|4437)'` | shell 总 exit 0，但首个 `rg` 报 `.agents`/`.codex` 不存在，且宽匹配输出被截断 | 不影响；后续用定向文件名检索准确找到 goal、裁决、PR9 fix 和 review artifact。 |
| `sed -n '61p' docs/gateflow/upload-material-o20-xbrl-runtime-plan-20260929.md` | exit 0，输出为空行 | 不影响；随后读取 §5 相邻完整段落，未把空行当缺失证据。 |

其余执行的只读命令均 exit 0；GitHub issue 读取工具成功，无其它失败工具。未执行测试或 pyright：本轮没有产品/测试代码修改，且任务明确只读并禁止执行 P0。

## 7. Final Plan Review Conclusion

**pass**。

本结论仅表示 PR9 修订后的 P0 evidence/probe 规格可交给 P0 取证执行。它不表示 P0 已通过，不授权 S1/S2 产品实现、生产 pin、公开 `XML_XBRL` 能力扩张、taxonomy 安全边界已生效或真实上传成功。SHA 停止条件未触发；第三集合没有把声明冒称运行事件；缺直接证据时不能标 observed/pass；P0/产品范围未漂移。执行者必须保留 strict blocked 语义，不能用静态 XML、聚合摘要、重放、OS zip 容器访问或推断性元素匹配补成通过。

（本文件为本次任务指定唯一新增 artifact。）
