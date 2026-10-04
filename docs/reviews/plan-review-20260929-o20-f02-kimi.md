# UM-O20-F02 XBRL 计划审查（Kimi 独立路）

RUNTIME/PROVIDER/MODEL: claude/kimi/kimi-k3
CANARY=kimi-66c7add8

- 审查时间：2026-09-29 10:42 CST（本机系统时钟）。
- 审查对象：`docs/gateflow/upload-material-o20-xbrl-runtime-plan-20260929.md`，SHA-256 `65c55801fce6432602a7d216f7c18d15c5df57e3228b1b85cc1bf1f830fffd2d`（审查前已用 `shasum -a 256` 复核，匹配）。
- 审查范围：计划全文；结合 goal（`upload-material-o20-xbrl-runtime-goal-20260929.md`）、E01（`upload-material-o20-e01-evidence-20260929.md`）、裁决登记（`upload-material-o20-xbrl-runtime-plan-review-adjudication-20260929.md`）、AGENTS.md、当前仓库代码与当前第三方 API 事实做 adversarial review。聚焦：依赖/taxonomy/安全探针可行性、三平台锁必要性、强制文件/网络边界实测可能性、G0 是否过度、API 签名推迟与可实施性、S1/S2 验收、上游 issue 授权表述。
- 边界遵守：未改计划/产品/测试/依赖/README/goal/裁决；未安装依赖、未下载 taxonomy；未发布上游 issue；未 commit/push/PR；未派发子 Agent。唯一写入物为本 artifact。只读探针均有界（见下）。

## 1. 本审查的独立直接核查（证据基础）

以下事实由本审查独立取得，非转述计划：

1. **计划文件 SHA-256 复核匹配**（`shasum -a 256`，输出与目标一致）。
2. **锁文件无 Arelle**：`constraints/lock-{common,macos-arm64,linux-x64,windows-x64}-py311.txt` 与 `pyproject.toml`、`requirements.txt` 均无 `arelle` 命中；`lock-common-py311.txt` 锁 `docling==2.127.0`、`docling-slim==2.127.0`。计划 §1 的依赖缺口陈述属实。
3. **docling-slim 2.127.0 对 arelle 的允许区间是 `>=2.38.17,<3.0.0`**（本机 venv `importlib.metadata.requires('docling-slim')`，extra `format-xml-xbrl`；`docling` 的 `xbrl` extra 指向 `docling-slim[format-xml-xbrl]==2.127.0`）。即 Docling 侧不排斥 2.45.x。
4. **【关键】arelle-release 2.45.x 的 `jaconv` 声明与 E01 记录矛盾**：PyPI JSON API 版本级元数据显示 2.45.0/2.45.1/2.45.2/2.45.3 与 2.44.8 的 `requires_dist` 均为 `jaconv<1,>=0`；进一步下载 2.45.3 wheel（6.1MB，仅到 `$TMPDIR`，读毕即删，未安装）直接解出 `arelle_release-2.45.3.dist-info/METADATA`，其 `Requires-Dist: jaconv<1,>=0`。该 wheel 上传时间 2026-09-24T21:07，**早于** E01 的观察时刻（2026-09-29 01:13）。jaconv 在 PyPI 全量版本列表最高 0.5.0 属实。E01 称"2.45.3 声明 `jaconv>=1,<2` 不可解"与 pip resolver 真源（wheel METADATA）直接冲突，且按上传时间戳，E01 观察时该 METADATA 应已是当前内容。
5. **Docling 2.127.0 XBRL backend 源码事实**（本机 venv `docling/backend/xml/xbrl_backend.py`）：
   - `XBRLBackendOptions(enable_local_fetch=False, enable_remote_fetch=False, taxonomy: Path|None=None)`，两 fetch 默认均关；backend `__init__` 在两关时抛 `OperationNotAllowed`（第 113-120 行）。计划 §1.2 属实。
   - `taxonomy` 目录经 `shutil.copytree` 整体复制进 `TemporaryDirectory`（第 131 行）；`BytesIO` 输入写成 `tmp/instance.xml`（第 144-146 行）；仅目录**顶层** `.zip` 被收集为 `taxonomyPackages` 传给 `modelManager.load`（第 134-148 行）。计划 §2 属实。
   - `enable_remote_fetch=False` → `cntlr.webCache.workOffline = True`（第 156-157 行）。`enable_local_fetch` 除门禁检查外**不向 Arelle 传递任何本地访问限制**。
   - E01 记录的崩溃点 `dim_value.memberQname.localName` 确在第 344 行。
   - `cntlr = Cntlr.Cntlr()` 在 backend `__init__` 内部构造（第 153 行），Dayu 经 `DocumentConverter.convert()` 调用时**无 cntlr、resolver 或加载钩子的注入点**；加载完成前无法介入。
6. **Arelle 2.44.8 `WebCache.py` 源码语义**（经一手源码核查）：`workOffline` 只在 `getfilename` 内检查两次（缓存 fallback、跳过下载）；`retrieve()`、`getheaders()`、`geturl()` **无条件** `self.opener.open(url, ...)`，不检查 `workOffline`。非 HTTP(S) URL（含 `file://`、本地路径）在 `getfilename` 入口直接 strip 前缀返回，**无 allowlist、无沙箱、无路径校验**，`workOffline` 对本地文件无任何作用。结论：`workOffline=True` 是缓存策略而非网络阻断；Arelle 对 instance 中任意 `file:`/绝对路径/ `../` 引用没有内建隔离。计划对安全边界的怀疑（§1.2 末、§2 第 3 条）被一手源码证实，G0-C 的动机成立。
7. **AAPL fixture 事实**：`tests/fins/fixtures/aapl_xbrl/fil_0000320193-24-000123/aapl-20240928_htm.xml` SHA-256 `1bf6615f...2241c` 与计划一致；`schemaRef` 为相对 `aapl-20240928.xsd`；该 XSD 引用 10 个远程 HTTP(S) schema（xbrl.org×4、xbrl.fasb.org×2、xbrl.sec.gov×4）+ 4 个相对 linkbase。计划 §2 的"正样本候选而非已证离线完整正样本"定性准确。
8. **代码路径事实**：`DOCLING_CONVERTER_CAPABILITY` 将 `.xbrl/.xml` 映射 `XML_XBRL`（`docling_runtime.py:231`）；`convert_pdf_bytes_with_docling` → `run_docling_pdf_conversion` 的二维尝试链**对所有格式生效**（XBRL 失败时会在 2-3 次尝试中重复构造 converter、重复 taxonomy copytree）；`ProcessDoclingConverter` 子进程从独占临时输入读字节（`docling_process_converter.py:414-416`）；`DoclingUploadService._prepare_upload_selection` 对 material 每项都转换（`docling_upload_service.py:1496-1509`）。计划 §2 第 1 条属实。
9. **本仓库无 CI**：无 `.github` 目录、无任何 workflow 文件；未发现锁文件生成/验证的自动化脚本或文档。三平台锁存在（`constraints/`）且 README 第 42-44 行承诺三平台安装路径，但验证手段无自动化载体。
10. **pip dry-run 复核受限**：本审查环境 pip 直连 PyPI 被 SSL 拦截（`OSStatus -26276`），无法复现计划 §2 的 `pip install --dry-run ... arelle-release==2.44.8` exit 0；该记录只能接受计划自报。作为替代，PyPI JSON API 与 wheel 下载经 curl 可达（上述第 4 条）。如实声明：计划的两条 dry run 记录未获独立复现。
11. **F01 文案投影真源**存在：`dayu/fins/upload_format_contract.py` 模块 docstring 与角色化模板与计划 §1 owner 判定一致。

## 2. 测试过的关键假设

| 假设（计划立场） | 核查结果 |
| --- | --- |
| 缺 `arelle-release` 是当前失败首因 | 与 E01、代码、锁文件一致，成立 |
| 2.45.3 不可解，故候选固定 2.44.8 | **不成立/证据矛盾**（§1.4）→ F1 |
| `enable_remote_fetch=False` 不构成安全边界 | 一手源码证实，成立，G0-C 必要 |
| 强制边界可由"底层 resolver 可审计拒绝机制或进程级隔离"实现 | 当前 Docling API 无注入点、Windows 无细粒度等价物，两条路径均有结构性障碍 → F4 |
| 三平台真实 runner 可用于 G0-A | 仓库无 CI，runner 来源未交代 → F2 |
| S2 验收命令可直接复现 | 缺 taxonomy 配置前置，不可复现 → F3 |
| G0 是 goal 细化而非新目标 | 成立：goal 第 1/2/3 条分别要求可锁定依赖、实测引用边界、完整 taxonomy 真实成功；G0-A/B/C 与之一一对应，**G0 不构成过度设计** |
| 推迟 API 签名使计划不可实施 | 不成立为 blocker：安全机制未定前写死签名确不安全，且计划显式把契约冻结安排在 G0 后 plan review；但 S2 验收前置不能一并推迟 → F3 |

## 3. Findings

### F1-未修复-高-Arelle 版本排除建立在与其一手元数据矛盾的记录上，G0-A 缺少复核动作

- **位置**: 计划 §1 第 1 条、§2（dry run 只验 2.44.8）、§3 G0-A（"锁候选先固定 Arelle `2.44.8`"）、§6 残余 owner；上游来源 E01「隔离依赖复试」段。
- **问题类型**: 契约缺失 / 动机证据失真 / root cause 不同源（间接记录替代一手元数据）。
- **当前写法**: "E01 的 `arelle-release 2.45.3` 因声明 `jaconv>=1,<2` 在当时索引不可解；隔离叠层 `2.44.8` 能导入……锁候选先固定 Arelle `2.44.8`……具体版本以完整解析为准，不能照抄 E01 手工叠层。"
- **反例/失败场景**: G0-A 按计划执行，2.44.8 全平台解析通过并写入四份锁；数月后发现 2.45.3 实际可解且含关键修复，锁定版本落后且无记录解释为何跳过最新版。更直接的场景：实施者在 G0-A 中发现 2.45.3 可解，但计划没有授权重新打开版本选择，只能停在 gate 等裁决——计划把本可在 G0-A 内解决的事情变成了计划外中断。
- **为什么有问题**: `jaconv>=1,<2` 这一排除性事实与 pip resolver 真源（wheel METADATA：`jaconv<1,>=0`，上传于 E01 观察之前）矛盾。项目纪律要求"root cause 必须逻辑/数据同源……禁止用间接迹象替代根因判断"；计划把一条与一手证据冲突的二手记录当作版本决策输入，且未在 G0-A 安排"以一手元数据复核最新可解版本并解释与 E01 的矛盾"这一首步动作。"具体版本以完整解析为准"只覆盖传递依赖版本，不覆盖 arelle 本体版本选择的重新打开。
- **直接证据**: 本审查 §1.3（docling-slim 允许 `>=2.38.17,<3.0.0`）、§1.4（2.45.0-2.45.3 版本级 `requires_dist` 与 2.45.3 wheel METADATA 均为 `jaconv<1,>=0`；wheel 上传 2026-09-24T21:07 早于 E01 2026-09-29 01:13 的观察）；E01 原文"再尝试装其声明依赖时解析器报 `jaconv>=1,<2` 无可用版本"未记录完整 argv，无法排除当时命令构造/环境偏差。
- **影响**: 实施 Agent 把矛盾证据固化为锁文件事实 / 锁定非最新版本且无可审计理由 / G0-A 中途意外停摆 / 后续 gate 的证据链被污染。
- **建议改法和验证点**: G0-A 增加显式首步：以一手 wheel/sdist METADATA（而非 E01 转述）复核当前最新 arelle-release（写作时为 2.45.3）的依赖声明与约束内可解析性，书面解释与 E01「`jaconv>=1,<2` 不可解」记录的矛盾归因；在此之后才选定锁定版本，且默认取约束内最新可解版而非默认 2.44.8。验证点：G0-A 决策记录中含逐版本 METADATA 摘要、选取理由与 E01 矛盾的书面归因。
- **修复风险（低/中/高）**: 低（纯计划文本修订，不改变 gate 结构）。
- **严重程度（低/中/高/严重）**: 高。

### F2-未修复-中-G0-A 要求三平台"真实平台 runner"，但仓库无 CI、runner 来源未交代

- **位置**: 计划 §3 G0-A（"分别使用 `lock-macos-arm64-py311.txt`、`lock-linux-x64-py311.txt`、`lock-windows-x64-py311.txt` 的对应真实平台 runner……不以 macOS 结果替代 Linux/Windows……三平台有一个无法解析，则停止安装方案"）。
- **问题类型**: 不可直接实施 / 资源假设缺口。
- **当前写法**: G0-A 把三平台真实安装 + `pip check` 作为通过条件，未说明 Linux/Windows runner 由谁提供、经何流程执行。
- **反例/失败场景**: 实施者在本机完成 macOS arm64 部分后，无任何渠道获得 Linux x64 / Windows x64 真实环境（本仓库无 `.github/workflows`，无 CI；本审查 §1.9），G0-A 按字面永远无法 pass，work unit 停摆；或实施者擅自降级为 `pip --platform win_amd64 --only-binary=:all:` 交叉 dry-run 顶包，违反"不以 macOS 结果替代"的字面要求，产出名义合规、实质未验证的锁。
- **为什么有问题**: 三平台锁本身是 README 承诺（README:42-44），要求三平台验证**不是过度要求**；但计划把验证手段当作既成事实。goal 成功信号 1 要求"选定可在项目支持平台解析并锁定的依赖组合"，其验证资源必须先闭合，否则 gate 不可达。这属于计划必须交代的 sequencing/资源前提，而非实施细节。
- **直接证据**: 本审查 §1.9（无 `.github` 目录、无 CI、无锁生成自动化）；README:42-44 的三平台承诺；计划 §6 自述"本 checkout 没有 `.venv`"、全部已有验证仅在本机 macOS arm64 完成。
- **影响**: G0-A 不可达导致整个条件性 handoff 停摆，或倒逼实施者用不达标手段伪造通过。
- **建议改法和验证点**: 计划明确 G0-A 的平台覆盖裁决路径，二选一或组合：(a) 指定 runner 来源（用户提供的机器/新建 CI workflow/既有发布流程）并把"runner 不可用"列为显式 blocked 出口与待用户裁决项；(b) 把 G0-A 拆为"三平台交叉 resolver 解析（`pip --platform … --only-binary=:all:`，无需真实 runner）+ 单平台真实安装与 `pip check`"，并把其余平台的真实安装验证显式移交发布流程裁决，计划内注明这是与 README 承诺的偏差及其批准人。验证点：G0-A 决策记录中每个平台的验证手段与执行者身份可审计。
- **修复风险（低/中/高）**: 低。
- **严重程度（低/中/高/严重）**: 中。

### F3-未修复-中-S2 验收命令缺少 taxonomy 配置前置，验收不可复现

- **位置**: 计划 §4 Slice S2 的真实 CLI 命令与验收清单；§4 公共契约段（"需要一个显式、类型化的 taxonomy 配置输入，而不是放进 `extra payload`、进程环境的隐式字符串或从上传文件父目录猜测"）。
- **问题类型**: 契约缺失 / 测试缺口（验收欠规格）。
- **当前写法**: S2 直接以 `python -m dayu.cli upload_material --base <fresh-workspace> … --files <instance>` 起跑验收，命令与验收清单中没有任何"管理员受信 taxonomy root 如何进入该 fresh workspace"的前置步骤；配置装载入口（workspace 配置文件？CLI 参数？`dayu-cli init` 流程？）在全文未框定候选形态与 owner。
- **反例/失败场景**: 实施者拿到 S1 pass 后执行 S2：fresh workspace 中没有任何 taxonomy 配置，转换必然失败；为让验收跑通，实施者临时用环境变量/父目录猜测/手工预置文件顶包——正是计划公共契约明文禁止的三条路径，验收在"违规手段"下通过。
- **为什么有问题**: API 签名推迟到 G0 后冻结是合理的（安全机制决定签名形态），但**验收命令的完整前置条件链不是签名细节，而是验收可复现性的组成部分**。goal 成功信号 3 要求"真实 `dayu-cli upload_material` …正常提交"，其前提（受信 taxonomy 已配置）必须在 S2 文本中可执行。当前写法让 S2 的成败取决于实施者临场补一个未裁决的配置入口设计。
- **直接证据**: 计划 §4 S2 命令文本无配置步骤；§4 公共契约禁止三类隐式配置来源；全文（含 §5 evidence 清单）只要求记录"taxonomy 相对布局与 catalog/hash、依赖/配置/网络策略快照"，未要求定义配置装载入口。
- **影响**: S2 验收不可复现 / 实施者被迫在验收环节做未审查的设计决策 / 公共契约（用户可部署性）实际在 implementation 期才被发明。
- **建议改法和验证点**: 在 §4 框定配置入口的候选形态边界（例如"workspace 级管理员配置文件，由 Documents runtime 校验，Fins 不感知具体路径语义"级别的最小约定），并把 S2 命令改写为含显式前置步骤的两段式验收（先配置受信 taxonomy root，再跑上传命令）；若坚持全部推迟到契约冻结 review，则在 S2 文本显式标注"本验收命令的前置配置步骤随冻结契约一并补齐，冻结前 S2 不可执行"。验证点：冻结后的 S2 命令在 fresh 环境按字面可复现。
- **修复风险（低/中/高）**: 低。
- **严重程度（低/中/高/严重）**: 中。

### F4-未修复-中-强制边界的两条候选路径在当前 Docling/Arelle API 与三平台承诺下均有结构性障碍，计划对最可能 blocked 路径无预选决策

- **位置**: 计划 §3 G0-C 安全实施决策段（"必须由底层 resolver 的可审计拒绝机制或进程级文件系统/网络隔离提供最终强制边界……若当前 Docling/Arelle/API/支持平台无法施加强制边界，停下记录该事实与备选方案"）。
- **问题类型**: 架构边界 / 非最优方案风险（对最可能结果的决策树缺失）。
- **当前写法**: 把最终强制边界寄托于两类机制之一，G0-C 不通过则停下；未分析两类机制在当前 API 下的可达性。
- **反例/失败场景**: G0-C 执行时发现——(a) "底层 resolver 可审计拒绝机制"：Docling 的 `XBRLDocumentBackend.__init__` 内部直接 `Cntlr.Cntlr()`（本审查 §1.5），Dayu 经 `DocumentConverter.convert()` 无任何 cntlr/resolver/plugin 注入点，唯一途径是在子进程内 monkeypatch `arelle.WebCache.WebCache.getfilename/retrieve` 等模块级符号——这是脆弱的第三方内部耦合，与项目"禁止胶水 seam、严格类型"约束张力极大，且 Arelle 2.44.8 的本地文件访问不经 WebCache 单点（§1.6：`file://`/本地路径在 `getfilename` 入口直接放行），单点包装无法覆盖全部本地读取路径；(b) "进程级隔离"：macOS 可 `sandbox-exec`（已 deprecated）、Linux 可 `bwrap`/seccomp，但 Windows 无用户态细粒度文件系统沙箱等价物，与 README 三平台承诺直接冲突。两条路径同时受阻是高概率事件而非边缘场景。
- **为什么有问题**: 计划的 stop 条款（"停下记录该事实与备选方案"）兜底了安全性，值得肯定；但对"最可能走到的 blocked 分支"没有预选决策（例如：Windows 上暂不启用 XBRL capability 的分平台 capability 裁决；或把"为 Docling 增加 taxonomy resolver 钩子"列为上游 feature request 路径并复用 F5 的 issue 授权；或接受 monkeypatch 并定义版本守卫测试）。G0-C blocked 时整个 work unit 回 goal 重裁，成本远高于在计划中预演分支。
- **直接证据**: 本审查 §1.5（Docling 无注入点）、§1.6（Arelle 本地路径零限制、`workOffline` 非网络阻断）、README:42-44（三平台承诺）、AGENTS.md 编码硬约束（禁胶水 seam）。
- **影响**: G0-C 高概率 blocked 时无预案，导致 goal 级返工；或实施者为过关而选择 monkeypatch 且缺乏版本守卫，把脆弱耦合引入 owner 模块。
- **建议改法和验证点**: 在 G0-C 补一页分支决策表：对"resolver 机制不可注入 / 进程隔离跨平台不一致 / 两者皆阻"三种结局分别给出预选出口（分平台 capability 降级、上游 feature request、受守卫的 patch 及其版本锁定测试），并标注各出口所需的裁决人。验证点：G0-C 决策记录可直接引用预选分支而非临时发明。
- **修复风险（低/中/高）**: 低。
- **严重程度（低/中/高/严重）**: 中。

### F5-未修复-中-上游 issue 表述与用户既有条件授权冲突，多设一道不存在的授权 gate

- **位置**: 计划 §5 第 4 条（"区分是 Docling 还是 Arelle owner，再准备相应上游 issue 草稿与证据。发布 issue 属后续授权 gate，本轮不发送"）。
- **问题类型**: 目标漂移（流程性）/ 与 goal 合同不一致。
- **当前写法**: 把"发布 issue"整体设为"后续授权 gate"。
- **反例/失败场景**: G0-B/S1 阶段满足全部条件（完整受控 taxonomy 下可复现、最小化保留故障、owner 已区分），实施者按"发布属后续授权 gate"停摆等待一个用户已经给过的授权，闭环被人为推迟；或更糟，实施者把 issue 草稿束之高阁，证据链随时间失真。
- **为什么有问题**: goal 第 5 条与用户裁决均为**条件授权**："若最终直接证据定位为 Docling/Arelle 上游缺陷，保留最小复现并向相应上游提 issue"——条件是证据质量，不是再次授权。裁决登记（`upload-material-o20-xbrl-runtime-plan-review-adjudication-20260929.md` 第 5 条）已明确预判："用户已作条件授权，仍需确认直接证据和目标上游，无需再次索取同一授权"。计划措辞与该登记直接冲突。
- **直接证据**: goal §已确认目标 5；goal 头部用户裁决；裁决登记第 5 条原文。
- **影响**: 条件满足时错误停摆 / 与总控裁决记录不一致导致 gate 争议。
- **建议改法和验证点**: 改为"满足下列条件（完整受控 taxonomy、相同 instance 与精确版本、最小化复现保留故障、owner 已区分）即按用户既有条件授权直接向对应上游提交 issue；条件不满足标记 `needs-more-evidence`。仅在拟提交内容超出'最小复现 + 版本/日志'范围时才回报用户单独确认"。验证点：plan 文本与裁决登记措辞一致。
- **修复风险（低/中/高）**: 低。
- **严重程度（低/中/高/严重）**: 中（流程性，无安全反方向风险）。

### F6-未修复-低-S1 测试矩阵"非法引用五类"与 G0-C"四类引用+另测远程"计数不一致

- **位置**: 计划 §4 S1（"非法引用五类"）对 §3 G0-C（"四类引用：相对目录内正常引用、`file:///...`、绝对本地路径、`../outside-sentinel.xsd`，并另测远程 HTTP(S) URL"，另加"转义/编码变体、符号链接与 taxonomy ZIP/catalog 重定向"三个维度）。
- **问题类型**: 契约缺失（测试边界歧义）。
- **当前写法**: G0-C 的非法场景数为 4（file:、绝对路径、`../`、远程 URL），另有 1 个合法对照与 3 个变体维度；S1 称"非法引用五类"，与任一计数都对不齐。
- **反例/失败场景**: 实施者按"五类"臆造一个 G0-C 未验证的场景（或漏掉远程 URL），owner 测试矩阵与证据 gate 矩阵脱钩，review 时无法对照验收。
- **为什么有问题**: 测试必须断言 owner 级 contract，且 S1 的逃逸矩阵应就是 G0-C 验证过的同一矩阵；计数歧义会让"矩阵"在两个 gate 间漂移。
- **直接证据**: 计划 §3 与 §4 原文对照。
- **影响**: 测试边界歧义 / 验收对照困难。修复极低成本。
- **建议改法和验证点**: S1 改为引用 G0-C 的显式场景清单（"G0-C 逃逸矩阵全量场景"），或把 G0-C 场景枚举成带编号的闭合列表供两处共同引用。验证点：两处清单逐项一一对应。
- **修复风险（低/中/高）**: 低。
- **严重程度（低/中/高/严重）**: 低。

### F7-未修复-低-taxonomy 打包形态（zip+catalog vs 裸目录）未指定，且失败路径在尝试链上放大复制成本

- **位置**: 计划 §3 G0-B（taxonomy 包形态未约束）、§4 S1（未提尝试链与 copytree 交互）。
- **问题类型**: 最佳实践偏离 / 过度耦合（现有 PDF 尝试链对 XBRL 的语义放大）。
- **当前写法**: G0-B 只要求"URL→本地文件/catalog 映射"，未指明以顶层 `.zip` + catalog 还是裸目录交付；全文未提 `run_docling_pdf_conversion` 尝试链对 XBRL 生效的事实。
- **反例/失败场景**: 裸目录形态的完整 us-gaap/FASB/SEC taxonomy 达数百 MB；Docling 每次 backend 构造 `shutil.copytree` 整树（本审查 §1.5），而 Dayu 的 `convert_pdf_bytes_with_docling` 对失败转换会按尝试链重试 2-3 次（§1.8），一次失败的 XBRL 转换放大为 2-3 次整树复制 + 2-3 次完整 Arelle 模型加载，转换超时与磁盘放大风险真实存在。
- **为什么有问题**: 打包形态是 G0-B 的可行性与性能前提（zip 形态由 Arelle 直接挂载，避免整树复制），也是 S1 配置契约的输入；尝试链放大是 owner（`dayu.documents.docling_runtime`）必须回答的设计问题（XBRL 是否应单次尝试、绕过 PDF 二维链）。计划两者均未提及，实施时才会撞上。
- **直接证据**: 本审查 §1.5（copytree/顶层 zip 收集）、§1.8（尝试链全格式生效）、AAPL XSD 的 10 个远程 schema 引用（§1.7，其传递闭包规模即 taxonomy 包规模下限）。
- **影响**: S1 性能/超时风险后置发现；G0-B 证据目录形态可能被实施者随意选择导致返工。
- **建议改法和验证点**: G0-B 增加一句"优先 taxonomy package（`.zip` + catalog）形态并记录选择理由；若用裸目录须测量 copytree 耗时与磁盘占用上限"；S1 允许范围内显式点名"XBRL 转换的尝试次数语义由 Documents runtime owner 决定，不因 PDF 二维链默认放大"。验证点：G0-B 记录含形态选择与规模/耗时数据；S1 设计说明含尝试链处理。
- **修复风险（低/中/高）**: 低。
- **严重程度（低/中/高/严重）**: 低。

## 4. Open Questions

1. G0-C 的引用逃逸矩阵未点名 Windows 特有形态（UNC `\\host\share`、`\\?\` 前缀、盘符绝对路径、8.3 短名）。若最终强制边界落在输入预检或进程隔离，Windows 变体是否纳入矩阵、在何平台验证，需要显式裁决（与 F2/F4 联动）。
2. 完整离线 taxonomy 包的规模与许可闭包未知：AAPL XSD 直接引用 10 个远程 schema，`us-gaap-2024.xsd` 等的传递闭包未盘点；SEC 主机对抓取有 User-Agent 合规要求。G0-B 的"许可/可再分发判断"需要具体清单化目标（哪些域、哪些文件、何种许可条款），当前只是原则句。
3. 计划 §2 的两条 pip dry-run 记录在本审查环境因沙箱 SSL 拦截无法独立复现（本审查 §1.10）；其结论与 PyPI 一手元数据间接一致（2.44.8 依赖集常见且纯 Python 为主），但独立复现缺口如实保留。
4. E01「`jaconv>=1,<2` 不可解」与 wheel METADATA 矛盾的真实归因（当时命令构造、索引缓存或上游元数据短暂异常）未查明；F1 的修复动作应顺带闭环此归因。

## 5. Residual Risks（建议跟踪去向）

- Docling 对 `DocumentStream` 缺 sibling taxonomy 时返回"仅标题 SUCCESS"的静默降级（E01 已证）：即使 S1/S2 全部通过，配置错误的部署仍可能产出空内容成功。计划以"仅标题不能通过"兜底验收，但运行期无内容下限断言。建议跟踪：S1 契约冻结 review 时明确 Docling JSON 最小结构断言的 owner 与阈值；不设财务准确率门槛与 goal 一致，不升格为 finding。
- Arelle `workOffline` 非网络阻断（本审查 §1.6）：即使 G0-C 通过，未来 Arelle 升级改变 `getfilename` 语义会静默改变安全属性。建议跟踪：锁定版本 + 升级时的安全矩阵重跑要求，写入 S1 的 owner 测试。
- 真实 CLI 成功不证明财务数字准确（计划 §5 已声明），残余归属上游 Docling；与 goal 第 5 条一致，不需额外动作。

## 6. 已确认不成立的攻击（记录以防重复质疑）

- **"G0 设计过度"**：不成立。goal 第 1/2/3 条分别要求可锁定依赖、实测引用边界、完整 taxonomy 真实成功；G0-A/B/C 与之对应，§3 末自声明为"证据不足先探针"的细化而非新产品目标，与 Goal-bound minimal design 一致。一手源码核查（§1.5/§1.6）证明安全实测必要性是真实存在的攻击面，非臆想加固。
- **"三平台锁要求本身过度"**：不成立。README:42-44 已承诺三平台安装路径，`constraints/` 四份锁已存在；G0-A 的三平台要求与既有承诺同源（但验证手段缺口见 F2）。
- **"推迟 API 签名使计划不可实施"**：不成立为 blocker。强制机制未定前写死 `Path` 签名确实不安全；计划显式把契约冻结安排在 G0 后 plan review，流程自洽。但验收前置条件不能一并推迟（F3）。
- **"taxonomy copytree/临时目录即可当沙箱"**：计划未犯此错误，且明确禁止（§2、§3）；一手源码证实其禁止正确。

## 7. 结论

**fail**（最小修复后可快速重审）。

计划的动机、owner 判定、架构边界、安全必要性与停损纪律均经独立核查成立；但作为 G0 探针的直接输入，它带着一条与一手证据矛盾的版本排除记录（F1，高），且三个中严重度缺口（F2 平台验证资源、F3 验收前置、F4 blocked 分支无预案）意味着即使按计划字面执行，也会在版本选择、平台验证与 S2 验收上停摆或跑偏。

**最小修复清单**（全部为计划文本修订，不动 gate 结构）：

1. G0-A 增加首步：以一手 wheel/sdist METADATA 复核最新 arelle-release（当前 2.45.3）依赖声明与可解性，书面归因与 E01 记录（`jaconv>=1,<2`）的矛盾后再选定锁定版本（对应 F1）。
2. G0-A 写明三平台验证的执行者/手段与"无 runner"显式出口，或拆分为交叉解析 + 单平台真实安装 + 其余平台移交发布流程裁决（对应 F2）。
3. S2 验收命令补 taxonomy 配置前置步骤的最小形态约定，或显式标注冻结前不可执行（对应 F3）。
4. G0-C 补三种 blocked 结局的预选出口决策表（分平台 capability 降级 / 上游 feature request / 受版本守卫的 patch）（对应 F4）。
5. §5 上游 issue 段改为引用用户既有条件授权，与裁决登记一致（对应 F5）。
6. S1/G0-C 逃逸矩阵计数对齐为同一编号清单；G0-B 指定优先 zip+catalog 形态并记录测量数据（对应 F6/F7）。
