# UM-O20-F02 P0 计划独立复审（MiMo rereview3，同版双路之 MiMo 路）

RUNTIME/PROVIDER/MODEL: claude/mimo/mimo-v2.6-pro[1m]
CANARY=mimo-6b5c4df5

- 审查时间：2026-09-29 12:41:49 CST（本机系统时钟）。artifact 文件名按本次任务指定的 gateflow 命名 `plan-review-o20-f02-rereview3-mimo-20260929.md`，不使用 `planreview` skill 的时间戳命名格式。
- 审查对象：`docs/gateflow/upload-material-o20-xbrl-runtime-plan-20260929.md`，SHA-256 `b2723237bb528bfb873add47370b8344b7daa814a1e852857b6ccc9df1f043b4`（审查前 `shasum -a 256` 实测与任务指定值一致，未触发 SHA 停止条件）；HEAD `9735800cb55a40336469593fa2fddae43c9c69ad`（`git rev-parse HEAD` 实测）。
- 审查范围：P0 修订计划全文（§1 owner、§2 F1–F7 处置表、§3 taxonomy/sidecar 接口轮廓、§4 三平台强制边界、§5 P0-A/B/C evidence slice 与停点、§6 单一矩阵/成本/上游 issue、§7 验证与未证清单）。binding scope contract 为 `docs/gateflow/upload-material-o20-xbrl-runtime-goal-20260929.md`。
- 已读直接证据源：冻结 E01 `docs/gateflow/upload-material-o20-e01-evidence-20260929.md`、probe `docs/gateflow/upload-material-o20-f02-probe-20260929.md`、MiMo PR2 review `docs/reviews/plan-review-20260929-120634.md`（对计划 SHA `4d01db55…2f9deb`，结论 fail）、总控 adjudication `docs/gateflow/upload-material-o20-xbrl-runtime-plan-review-adjudication-20260929.md`、Sol PR2 fix artifact `docs/gateflow/upload-material-o20-f02-plan-fix-pr2-20260929.md`，以及本机真实 Docling 2.127.0 / Arelle 2.45.3 / Dayu 调用路径源码与仓库 fixture。
- 边界遵守：未修改计划、goal、E01、probe、总控裁决、产品、依赖、锁、测试、README；未安装依赖、未加载任何 taxonomy、未对外网络/issue 操作、未 commit/push/PR/merge、未派发子 Agent。全部核查为有界只读。唯一新增物为本 artifact。

## 1. 审查基线事实（独立直接核查，区分已实证 / 计划 / 外部阻断）

### 1.1 流程与冻结完整性（已实证）

1. 计划 SHA 与任务指定一致；`git status --porcelain` 只有 9 个 untracked gateflow/review 文档，无任何 modified 产品文件，与计划 §7「本轮仅改文档」一致；worktree 无 `.venv`、无 `.github/workflows`、`constraints/` 下存在 `lock-macos-arm64-py311.txt` / `lock-linux-x64-py311.txt` / `lock-windows-x64-py311.txt` / `lock-common-py311.txt`（三平台 lock 载体在盘）。
2. 冻结 E01 当前 SHA-256 `f75a0c9b20e8ad152d5d0f24964b11f4baf87ffb8f11a313671fa69b6fe0401c`，与总控 adjudication OQ3 登记的 digest 逐字一致——冻结完整性成立，且 P0「不覆盖冻结 E01」有可校验基线。
3. probe 原始产物目录 `/private/tmp/dayu-o20-f02-probe.AdlwrW/`（30+ 原始双流/样本/wheel）、`/private/tmp/dayu-o20-e01.1NAhyk/`、`/private/tmp/dayu-o20-full-resolver-20260929/` 均在盘——即 P0 证据迁移的源材料当前可取，但均在 `/private/tmp`，易失性判断与计划 §5/§7 一致。

### 1.2 F1 同根引用图可达性所依赖的源码事实（已实证）

1. **Docling 2.127.0 `docling/backend/xml/xbrl_backend.py`（实读 ~95–180 行）**：`taxonomy` 非目录即 `ValueError`；`shutil.copytree(taxonomy, tmp_path, dirs_exist_ok=True)` 把受控树**内容复制进与 instance 同一临时目录**（相对 `schemaRef`/linkbaseRef 以该目录为基解析，与散文件布局吻合）；`taxonomy_path.iterdir()` 仅收集**顶层**合法 `.zip` 作为 `taxonomyPackages`；`BytesIO` 输入固定写为 `tmp_path / "instance.xml"`（同名覆盖风险与计划「root 中同名文件须拒绝」方向一致）；`Cntlr.Cntlr()` 裸构造，`workOffline` 仅由 `enable_remote_fetch=False` 映射，`modelManager.load(..., taxonomyPackages=zip_paths)` 传递包。
2. **Docling `docling/datamodel/backend_options.py`（实读 ~505–521 行）**：`XBRLBackendOptions.taxonomy` 描述为「相对位置的 xsd/linkbase **加可选** catalog 映射绝对 URL 的 zip 包」——同一目录混合形态，与计划 §3「散文件与可选顶层 catalog zip 同根组合」同源，PR2-F1 的互斥 layout 缺陷在本版被消除。
3. **Arelle 2.45.3 `arelle/packages/_package_manager.py`（实读关键行）**：`:126` 由 `taxonomyPackage.xml` 同位取 `catalog.xml`；`:341-342` 解析 OASIS `rewriteSystem`/`rewriteURI`（`systemIdStartString`/`uriStartString` → `rewritePrefix`）；`:517/:580-582` 要求并支持包根级 `META-INF/taxonomyPackage.xml`；`ModelDocument.py:115-120` 在加载路径消费 `fileSource.isMappedUrl/mappedUrl`——「绝对 import 由 catalog 映射」在真实加载路径上**可表达**。zip 实际运行可用性计划已标 blocked 待 P0-B 复测，属实，未越权承诺。
4. **AAPL fixture 引用图（实读）**：`tests/fins/fixtures/aapl_xbrl/fil_0000320193-24-000123/aapl-20240928_htm.xml:16` 相对 `schemaRef`；`aapl-20240928.xsd:7-16` 10 个绝对 `schemaLocation` import（含 `http://` 与 `https://` 混合 scheme、`xbrl.org`/`www.xbrl.org` 混合 host）；`:19-22` 4 个相对 `linkbaseRef`——「相对散文件 + 绝对 import」混合形态属实，P0-B 合成探针的 AAPL 同构定位正确。

### 1.3 Dayu 调用路径与 owner 事实（已实证）

1. `dayu/documents/docling_runtime.py:231` capability `XML_XBRL`；`:554-605` `build_docling_pdf_converter` 只注入 PDF format option，非 PDF 由 Docling 默认 option 装配（当前产品 XBRL 路径双 fetch 关 → 快速失败，无现存读取绕过窗口）；`:603` 全仓唯一 `DocumentConverter` 构造点；`:737-830` `run_docling_pdf_conversion` 按尝试链逐次 `_build_attempt_converter` 重建 converter——对 XBRL 即每次尝试一次整树 `copytree`，计划 §6 成本警示属实；`:856+` `convert_pdf_bytes_with_docling` 经 `DocumentStream` 喂 Docling（产品路径命名固定 `instance.xml`）。
2. `dayu/fins/pipelines/docling_process_converter.py:98-128` `DoclingConversionConfig` 为闭合 frozen dataclass（仅 PDF 语义字段）；`:256` `_DoclingProcessTarget` 为可 pickle 单次转换子进程目标（input_path/output_path/stream_name/config 显式字段），计划 §3「显式进入共享 `_DoclingProcessTarget`」引用真实符号，且与 AGENTS.md「禁止显式参数进 extra payload」一致。
3. `dayu/fins/pipelines/docling_upload_service.py:1500-1505` material 转换 `converter_inputs = selection.files` 逐文件进行——「附加 XSD 不能代替配置」属实；`dayu/fins/upload_format_contract.py:626-631` 为 O20-F01 候选文案真源（`.xml/.xbrl` 仅实例候选、不承诺独立 linkbase），与计划「CLI/tool 公开文案沿 O20-F01 唯一投影」一致。
4. `.gitignore:3-4` `workspace`/`workspace/` 命中——`workspace/evidence/upload-material-o20-f02/` 作为不进 PR 的归档位置成立（但见 finding 3 的易失性残余）。

### 1.4 上游 issue 与状态口径（已实证 / 外部阻断的划分）

上游 docling-project/docling [issue #4437](https://github.com/docling-project/docling/issues/4437) 由总控按用户条件授权以纯合成 typed 复现提交（adjudication 登记），**只跟踪 Docling typed member 导出崩溃**。计划 §5「不能以合成样本代替真实财报 CLI 成功」、§6「此 issue 不重开、不代替 Dayu taxonomy 输入/隔离/验收」——计划未把 #4437 当 Dayu 支持完成，口径正确。Docling 修复时间未知属**外部阻断**；Dayu 侧受控依赖、taxonomy 输入、强制边界、CLI 验收均是**计划**，无一已实证为产品能力。

## 2. Assumptions tested（PR2-F1–F7 处置闭合性逐项证伪结果）

| # | 假设（本版计划立场） | 结果 |
| --- | --- | --- |
| A1 | PR2-F1 已闭合：`taxonomy_root + catalog_zip_name` 同根组合可表达 AAPL 形态引用图，解析分工明确 | **成立**（§1.2 源码同源；残余见 finding 2：绝对入口引用向量未覆盖） |
| A2 | PR2-F2 已闭合：逐平台 pass/blocked 词表、候选版≠生产 pin、blocked 即回 goal/总控、无 macOS 充数 | **成立**（词表闭合、升级出口即时触发；三平台 lock 载体在盘，「相应 lock 可验证」有对象） |
| A3 | PR2-F3 已闭合：证据位置、owner、清单字段、旧→新映射、不覆盖 E01、留存失败不记 pass | **基本成立**（残余见 finding 3：备份落点与跨清理/重启回读判据未定义） |
| A4 | PR2-F4 已闭合：自足裸目录与混合 zip 探针先于许可盘点，外部阻断不吞内部结果 | **成立**（§5 P0-B 句序实读确认；残余见 finding 4） |
| A5 | PR2-F5 已闭合：承诺统一为转换进程及子进程零出站（含非 taxonomy URL），与 C4/平台表同源 | **成立**（§4 首段与 §6 C4 强度一致；workOffline/预扫描/临时目录均被明确排除出强制证据） |
| A6 | PR2-F6 已闭合：C8 非 schemaRef 向量 + 逐向量 OS trace + 有限矩阵免责 | **成立**（OQ1 留少量未点名向量；不变量由 OS 边界承担，口径正确） |
| A7 | PR2-F7 已闭合：root 绝对/规范/workspace 外 fail-closed、provenance owner、TOCTOU 延后有 owner | **部分证伪**（finding 1：「workspace 外」校验点与所需输入不闭合、清单通道未定义） |
| A8 | P0-A/B/C 作为 evidence/probe slice 可执行，blocked 出口不导致不可审计状态 | **成立**（各步有命令轮廓、状态词与停点；停止条件「无 P0 切片仍宣支持」未触发——计划明确撤下 S1/S2、不自宣 pass） |

## 3. Findings

### 1-未修复-中-§3「workspace 外 fail-closed」不变量的可执行校验点与所需输入未闭合，provenance 清单通道未定义
- **位置**: 计划 §3 第二段「root 必须为绝对、已规范化且解析后仍在用户可写 workspace 外…均 fail closed，不靠 CLI 文案或操作者自觉」与「Documents runtime 是输入信任边界 owner，转换进程内按该清单校验并拒绝不匹配」；§1 owner 划分句；§3 typed 值 `XbrlTaxonomyInput(taxonomy_root, catalog_zip_name)` 与 CLI 拟参。
- **问题类型**: 契约缺失 / 语义 owner 漂移风险。
- **当前写法**: 「落入 workspace 或解析后越界均 fail closed」写成运行时强制不变量，owner 归 Documents runtime；但 typed 值只有 `taxonomy_root` 与 `catalog_zip_name` 两字段，Documents runtime（`dayu.documents.docling_runtime` 转换 API 只收 bytes/name/转换参数，无 workspace 概念）拿不到「用户可写 workspace」边界，无法执行该比较；「按该清单校验」的清单（逐文件 SHA-256/root 清单）由管理员归档 owner 保留，但清单以何种通道进入转换进程未定义。
- **反例/失败场景**: 实施者按 owner 句把校验全塞进 Documents runtime，却无 workspace 输入，只能加默认值/宽松判断（例如仅查绝对路径）——「workspace 外」不变量实际无人校验；或实施者被迫把 workspace 概念反向传入 `dayu.documents`，污染层中立转换库；冒充管理员的调用把 `--xbrl-taxonomy-root` 指进用户可写 workspace，校验形同虚设，随后用户改写树内容。
- **为什么有问题**: 与 AGENTS.md 语义所有权硬约束直接冲突：不变量必须有唯一可执行 owner，禁止下游补救；校验点（CLI/Service/Fins 边界 vs Documents runtime 二次校验）与校验所需输入（workspace 路径或管理员受控根 allowlist）不闭合时，实施 Agent 只能自选落点，正是 PR2-F7 要消除的漂移形态。与「不靠 CLI 文案或操作者自觉」的自我要求也不一致——祈使句仍无强制点。
- **直接证据**: 计划 §3 两段原文；`dayu/documents/docling_runtime.py` 转换入口签名（实读：bytes/stream_name/转换参数，无 workspace 或受信根 allowlist 参数）；`dayu/fins/pipelines/docling_process_converter.py:256-263` `_DoclingProcessTarget` 字段（实读：无 taxonomy 相关字段，本版计划待加显式 typed 值）。
- **影响**: 信任边界绕过（用户可写树冒充受信 taxonomy）/ owner 漂移 / 实施期重开接口或以 fallback 补校验。
- **建议改法和验证点**: 二选一写明：(a)「workspace 外」比较放在唯一持有 workspace 概念的 Fins/CLI 输入校验边界（显式参数传入已解析 workspace 路径，拒绝即 fail closed），Documents runtime 二次校验绝对/规范/清单匹配/文件类型；(b) 把不变量改写为「root ∈ 管理员受控根 allowlist」，allowlist 作为 Documents runtime 显式输入。并定义清单通道（例如 root 内固定名清单文件 + 管理员侧清单 digest 另路提供）。验证点：未来实施计划的校验契约测试断言拒绝分支落在 owner 层，且 typed 值字段覆盖校验所需全部输入。
- **修复风险（低/中/高）**: 低（文本定约，不改产品）。
- **严重程度（低/中/高/严重）**: 中。
- **残余 owner**: `dayu.documents.docling_runtime`（输入信任边界校验）+ Fins/CLI（workspace 概念 owner）；修复落点为 P0 之后的实施计划 typed 输入契约。

### 2-未修复-低-§3 引用解析分工与 P0-B 合成引用图未覆盖绝对 schemaRef/绝对 linkbaseRef 经 catalog 直接映射的向量
- **位置**: 计划 §3「相对 `schemaRef`/linkbaseRef 由散文件布局解析，绝对 import 由 catalog 映射」；§5 P0-B 合成混合引用图三段式；§5 真实样本步骤「真实财报如有相对 schemaRef 加绝对 import」。
- **问题类型**: 测试缺口 / 契约缺失（解析分工未覆盖全部引用形状）。
- **当前写法**: 分工句只分配「相对 schemaRef/linkbaseRef」与「绝对 import」两类；绝对入口引用（instance 的绝对 `schemaRef`、绝对 `linkbaseRef`）未被分配解析路径，合成探针与真实样本步骤也都只锚定 AAPL 形态（相对 schemaRef + 绝对 import + 相对 linkbaseRef）。
- **反例/失败场景**: 某真实 instance 的 `schemaRef` 本身是绝对 URL、依赖 catalog 映射进包内（入口点式引用在 taxonomy 包生态常见）。Arelle `ModelDocument.py:115-120` 的 mappedUrl 对任意 URL 生效，但 Docling→Arelle 的实际解析行为未被探针覆盖；一旦该形状在组合布局下失败，P0-B 会把接口/映射闭包缺陷记成「当前 Docling 仍失败 → goal 3 blocked」，重演 PR2-F1 揭露的误归因模式（接口缺陷伪装成样本/转换失败）。
- **为什么有问题**: PR2-F1 的修复原则是「不可把接口缺陷误报为真实样本不合格」；同根组合的可达性证明只覆盖三种引用形状，解析分工句对绝对入口引用留白，goal 3 主路径的证据链仍可被未测形状污染。
- **直接证据**: 计划 §3 分工句与 §5 探针句原文（均无绝对 schemaRef/linkbaseRef 项）；`aapl-20240928_htm.xml:16` / `aapl-20240928.xsd:19-22` 实读（AAPL 全部入口引用为相对，故探针形状贴合 fixture 但不代表全部真实样本）；`_package_manager.py:341-342` rewriteURI/rewriteSystem 映射按 URL 前缀对任意引用机制生效（实读）。
- **影响**: 未测形状的假性 blocked 归因 / goal 3 证据链污染 / 实施期重开解析分工。
- **建议改法和验证点**: §3 分工句补「绝对 schemaRef/linkbaseRef 同样经 catalog 映射」；P0-B 合成引用图增测两个向量（绝对 schemaRef→catalog、绝对 linkbaseRef→catalog）；真实样本步骤写明按样本实际引用形状选散文件/catalog 组合，不以 AAPL 形状为限。验证点：新增向量各自 Arelle 离线 `--validate --validationExitCode` exit 0 后再进 Docling 对照，结果独立记录。
- **修复风险（低/中/高）**: 低。
- **严重程度（低/中/高/严重）**: 低。
- **残余 owner**: P0-B 执行者（探针矩阵）+ Documents runtime（解析分工契约）。

### 3-未修复-低-P0 证据备份落点与「跨清理/重启回读」判据未定义，抗清理副本仍是整条证据链单点
- **位置**: 计划 §5「P0 证据归档前置」段：「P0 开始前证据 owner 必须建立受控留存与备份、确认可跨清理/重启回读，不能仅凭 `.gitignore` 或目录名声称持久」。
- **问题类型**: 契约缺失（可执行判据未定）。
- **当前写法**: 主归档位置（`workspace/evidence/upload-material-o20-f02/`）与清单字段已定义，但「备份」目标位置未指定，「跨清理/重启回读」的验收动作未定义；worktree 与主归档同处 `/private/tmp`，一次清理/重启同时抹掉主归档、probe 源目录与文档所引用路径。
- **反例/失败场景**: 备份若同样落在 `/private/tmp` 或 worktree 内，「已备份」被记录为完成，机器重启后主档、备份、probe 源同灭——E01 argv 丢失式争议在 P0 重演；「跨重启」若要等真实重启才能证明，P0 前置永远无法勾选，或被草率勾选后失效。
- **为什么有问题**: 本轮全部动机链是「E01 缺 argv/report 致矛盾不可考」→ 强调一手证据；证据前置条款若缺唯一落点与可操作判据，留存纪律仍停留在祈使句。PR2-F3 的修复要求「留存位置与 owner」，位置主档已给，备份落点恰是抗清理语义的关键一半。
- **直接证据**: 计划 §5 该段原文；本审查实测 `ls` 确认 `/private/tmp/dayu-o20-f02-probe.AdlwrW/` 等源目录与 worktree 同在 `/private/tmp`；PR2 finding 3 原文要求「可在 review 时从非临时路径直接取回」。
- **影响**: 证据链单点易失 / 前置条款不可验收或假验收 / 上游 #4437 补证与后续争议复核失去原件。
- **建议改法和验证点**: 指定备份落点为管理员指定的持久目录（workspace 外、非 `/private/tmp`），写明回读判据：迁移完成后遮蔽/删除源副本，从备份按清单逐文件 SHA-256 回读比对通过，才算留存成立；「跨重启」以备份落点的持久性声明 + 时间戳记录 + 真实重启后抽查回读补证，不作为前置硬门槛。验证点：P0 第一步产出「源→主档→备份」双映射清单与回读结果，留存失败即按既定规则不记 pass。
- **修复风险（低/中/高）**: 低。
- **严重程度（低/中/高/严重）**: 低。
- **残余 owner**: 本 work unit 证据 owner（归档与回读）+ 管理员归档 owner（备份落点授权）。

### 4-未修复-低-P0-B 自称「零出站条件下」运行，但该步只有配置级离线手段，与 §4 自证的强制边界口径不一致
- **位置**: 计划 §5 P0-B 首句「先在零外部 taxonomy 下载、零出站条件下重跑本轮自包含裸目录相对样本」；对照 §4「`workOffline`、预扫描、Docling 临时目录、普通子进程或 monkeypatch 均不能单独证明强制边界」与 probe P3 `WebCache.py` 事实。
- **问题类型**: 契约缺失 / 表述强度漂移（条件声称强于该步手段）。
- **当前写法**: P0-B 要求在「零出站条件」下跑探针，但 OS 级出站观测（trace/本地端点）按 §5 属 P0-C；P0-B 可用的只有 `enable_remote_fetch=False`/`workOffline` 与自包含输入——计划自己已证这些不是强制/证明边界。
- **反例/失败场景**: 合成混合引用图的 catalog 映射若配置不当，Arelle 对 `example.invalid` 绝对 import 的解析可能走非 webCache 的 `opener.open` 路径尝试出站（probe P3 已证该类路径存在）；P0-B 无出站观测，「零出站条件下完成」只能凭配置推断——按 AGENTS.md「禁止用间接迹象替代根因判断」，这与把 workOffline 当隔离证据是同一类错误的弱化版。
- **为什么有问题**: §4/§6 的零出站语义由 OS 边界 + trace 承担（正确）；P0-B 措辞却把「零出站」写成已成立的运行条件。同一语义两个强度版本，后续执行者可能据 P0-B 文本把配置级离线记成零出站证据。
- **直接证据**: 计划 §5 P0-B 首句 vs §4 第二段原文；probe P3「`workOffline` 也不能单独充当所有网络 API 的强制沙箱」。
- **影响**: 配置级离线被误记为零出站证据 / 探针期静默出站未被发现 / 声明-验证漂移。
- **建议改法和验证点**: P0-B 措辞改为「自包含输入 + 配置级离线；OS 级零出站证明归 P0-C」，或要求 P0-B 探针同时挂本地端点监听/出站观测并留证（成本低，且 C4 已有同型手段）。验证点：P0-B 产物中零出站的证据类型被显式标注为「配置级」或「OS 级」，不允许混记。
- **修复风险（低/中/高）**: 低。
- **严重程度（低/中/高/严重）**: 低。
- **残余 owner**: P0-B 执行者（措辞与观测）+ P0-C 安全 owner（OS 级零出站真源）。

## 4. Open Questions

- OQ1：C8 未点名向量的归属——`xsi:schemaLocation` hint、`<?xml-stylesheet?>` PI、DTD 参数实体等是否落入「样式或链接导入 / DOCTYPE/外部 ENTITY」既有条目，还是需要显式点名；矩阵有限性已由计划免责句覆盖，但点名成本低（并入 finding 2 的探针增测一并处理最省）。
- OQ2：C7/reparse 等平台专属用例在 P0-C 与后续 owner 测试的逐平台用例表未定（承接 PR2 OQ1，仍未收敛）。
- OQ3：无 typed 维度的真实合规财报 instance 存在性与选样标准（承接 PR2 OQ5）；长期取不到时 goal 3 处置需 goal 级裁决——与「#4437 不等于 Dayu 支持完成」口径一致，不由实施者自定。
- OQ4：「管理员受控归档」的最小可操作定义（访问控制、保留期限、回读授权的具体形态）尚未成文；P0-B 的 `blocked: evidence archive unavailable` 判据依赖该定义。

## 5. Residual Risks（建议跟踪去向）

- **R1 E01 `jaconv>=1,<2` 矛盾根因永久不可考**（argv/report 未留）：计划诚实标注、拒绝臆测。跟踪去向：P0-A 决策记录存档。
- **R2 typed 缺陷使 goal 3 对含 typed 真实财报结构性 blocked**：#4437 只跟踪 Docling typed member 崩溃，修复时间未知，**不构成 Dayu 受控支持完成**；合成样本不能替代真实 CLI 成功。跟踪去向：goal/总控 capability 裁决 + 无 typed 样本搜索（OQ3）。
- **R3 Docling/Arelle 版本语义漂移**：结论钉在 Docling 2.127.0 / Arelle 2.45.3。跟踪去向：P0-A 候选/生产 pin + 升级时强制重跑 §6 矩阵。
- **R4 无 sidecar Stream「仅标题 SUCCESS」静默空成功**（E01/probe 已证）。跟踪去向：未来实施计划的输出最小断言（不设财务准确率门槛）。
- **R5 taxonomy 校验→copytree TOCTOU**：计划已定由后续实施计划以受控快照/再校验闭合并实测（与 PR2 R6 一致）。跟踪去向：未来实施计划 staging 语义，owner 为 Documents runtime。
- **R6 zip+catalog 同根组合运行可用性未测**：计划明示「未测 zip 不承诺可用」。跟踪去向：P0-B 合成探针（本版 finding 2 增测向量后一并覆盖）。
- **R7 平台强制机制可能三平台均不可得**（sandbox-exec 本环境已拒、无 Docker daemon、无 Linux/Windows runner）。跟踪去向：goal/总控分平台 capability / 受信隔离部署裁决（计划 §4 出口清单）。

## 6. 结论

**pass-with-risks**。

理由：

1. 七项 PR2 findings 的处置经本机真实源码逐项核验，六项闭合或基本闭合：PR2-F1 的互斥 layout 结构性缺陷已消除（同根组合与 Docling 原生单目录混合能力同源，Arelle catalog 映射在加载路径实在）；PR2-F2 的 pin 二义已由闭合词表 + blocked 即时升级 + 禁 macOS 充数消除，三平台 lock 载体在盘；PR2-F3/PR2-F4 的证据与顺序纪律落实到可校验条款；PR2-F5 零出站承诺已统一到 OS 强制口径；PR2-F6 C8 向量与有限矩阵免责已补齐；PR2-F7 的 provenance owner 与 TOCTOU 延后归属明确。仅 PR2-F7 残余一个中等级 owner 边界缺口（finding 1）与三个低等级缺口（findings 2–4）。
2. 计划的已实证 / 计划 / 外部阻断划分诚实：S1/S2 产品承诺已撤下，P0 只是 evidence/probe 规格，§7 未证清单与 blocked 词表一致；未把上游 #4437 当 Dayu 支持完成，未把 workOffline/预扫描/临时目录当 OS 隔离证据，未以 macOS 冒充 Linux/Windows。任务停止条件（无强制隔离机制却宣称支持通过 / 无可执行 P0 切片）**未触发**。
3. P0-A（fresh venv 实装 + `pip check` + 证据归档）、P0-B（自足混合引用图探针）、P0-C（平台机制搜索 + 矩阵）均有可执行步骤与明确停点，findings 均不阻断 P0-A 与证据归档前置的启动；finding 1 只约束 P0 之后的实施计划 typed 契约，findings 2–4 可在 P0 执行中按建议文本吸收。
4. 按 planreview 口径不给 fail：不存在「在核心验收路径产假证据」的结构性缺陷；findings 是可跟踪的契约与措辞收口。建议总控将 findings 1–4 登记为 P0 执行前/执行中的文本修订项（或并入 P0 执行记录），finding 1 必须在冻结实施接口前闭合。

（本文件为本次任务指定唯一 artifact；本轮未改任何计划/产品/测试/依赖/锁/README/goal/E01/probe/裁决文件，未安装依赖、未加载 taxonomy、未对外发布 issue，未 commit/push/PR/merge，未派发子 Agent。）
