# UM-O20-F02 受控 XBRL Docling 转换能力计划 —— MiMo 独立 plan review

RUNTIME/PROVIDER/MODEL: claude/mimo/mimo-v2.6-pro

CANARY=mimo-6d51405a

- 审查对象：`docs/gateflow/upload-material-o20-xbrl-runtime-plan-20260929.md`，仅审查 SHA-256 `65c55801fce6432602a7d216f7c18d15c5df57e3228b1b85cc1bf1f830fffd2d`。本机 `shasum -a 256` 实测一致，SHA 核对通过。
- 审查方式：`$planreview` adversarial plan review；结合 goal（`upload-material-o20-xbrl-runtime-goal-20260929.md`）、E01（`upload-material-o20-e01-evidence-20260929.md`）、AGENTS.md（与 CLAUDE.md 逐字一致）、当前代码、锁/依赖声明与第三方 Docling 2.127.0 / Arelle 2.44.8 源码与 wheel 元数据。
- 范围：只审计划本身的真实性、可执行性、语义 owner、goal drift 与成功边界；不改计划/产品/测试/依赖/README/goal/裁决，不安装依赖、不下载 taxonomy、不对外发布 issue。本轮只读探针均为有界本地读取（源码/夹具/元数据/E01 证据目录），无安装、无网络写入。
- binding scope contract：goal confirmation（`upload-material-o20-xbrl-runtime-goal-20260929.md`，「当前 Gateflow：goal confirmation pass」）为本轮 binding scope。裁决登记 `upload-material-o20-xbrl-runtime-plan-review-adjudication-20260929.md` 已预审待双路反证，本文件是其中 Kimi/MiMo 同版 plan review 一路。

## 1. 审查基线事实（已直接核对）

1. **能力与依赖缺口属实**：`dayu/documents/docling_runtime.py:222-234` 的 `DOCLING_CONVERTER_CAPABILITY` 将 `.xbrl/.xml` 列为 `XML_XBRL`；`pyproject.toml` 有 `docling>=2.127.0,<3.0.0`、`docling-core>=2.96.0,<3.0.0`，无 Arelle；`constraints/` 四份锁文件（common/linux-x64/macos-arm64/windows-x64）均无 `arelle`/`jaconv`。
2. **第三方契约事实属实**（Docling 2.127.0 源码，主工作区 venv site-packages）：
   - `docling/backend/xml/xbrl_backend.py:112-121`：`enable_local_fetch` 与 `enable_remote_fetch` 均为 False 时抛 `OperationNotAllowed`；`:283-284` 默认 XBRL option 双关。
   - `xbrl_backend.py:125-149`：`taxonomy` 必须是目录，`shutil.copytree` 复制进临时目录；`BytesIO` 流固定写为 `tmp/instance.xml`。
   - `xbrl_backend.py:156-157`：`enable_remote_fetch=False` 仅映射 `cntlr.webCache.workOffline=True`，无本地文件访问沙箱。
   - `docling/datamodel/backend_options.py:505-518`：`XBRLBackendOptions.taxonomy` 语义与计划 §2 描述一致（目录 + 可选 `.zip` taxonomy package + `catalog.xml`）。
   - `docling_slim-2.127.0.dist-info/METADATA`：`format-xml-xbrl` extra 要求 `arelle-release<3.0.0,>=2.38.17`。
3. **依赖版本事实属实**：E01 证据目录 `arelle-deps.stderr` 明确 `arelle-release 2.45.3` 要求 `jaconv>=1,<2`，索引可见最高 `0.5.0`，不可解；`optional244/arelle_release-2.44.8.dist-info/METADATA` 要求 `jaconv>=0,<1`，可解。计划「锁候选先固定 2.44.8」与官方 extra 区间相容。
4. **E01 观察与计划引用一致**：真实 CLI 对 AAPL instance 返回 `content/docling_converter_execution`、`stored_files=0`、无 material manifest；直调 Docling 首因 `ModuleNotFoundError: arelle`；`optional244` 叠层下 `OperationNotAllowed`；显式 `XBRLFormatOption(enable_local_fetch=True, enable_remote_fetch=False, taxonomy=<fixture 目录>)` 后在 `xbrl_backend.py:344` `dim_value.memberQname` 为 `None` 抛 `AttributeError`；`DocumentStream` 缺 sidecar 时可返回仅标题的 `SUCCESS`。
5. **输入链路属实**：`dayu/fins/pipelines/docling_upload_service.py:914` 读原件字节，`:1003-1008` 仅以 `bytes + file_path.name` 调 `convert_to_json_bytes`；`docling_process_converter.py:278-287` 子进程从独占临时 `input.bin` 读字节后走 `convert_pdf_bytes_with_docling` → `DocumentStream(BytesIO)`。sibling `.xsd/.xml/linkbase` 无自然随流通道——计划 §1.3 判断正确。
6. **material selection 语义属实**：`docling_upload_service.py:1500-1507` material 的 `converter_inputs = selection.files`，即每个 `--files` 材料项都独立转换；任一转换失败对 material 直接抛错（`:1009-1011`）。
7. **AAPL 夹具事实**：`tests/fins/fixtures/aapl_xbrl/fil_0000320193-24-000123/aapl-20240928_htm.xml` SHA-256 实测 `1bf6615f47d53f87b10fd036b647fbb4e9ad59db51667761b42ee6666bb2241c`（与计划一致），`schemaRef` 为相对 `aapl-20240928.xsd`；同名 XSD 有 10 处 `http(s)://` 远程 import（fasb.org / xbrl.org / xbrl.sec.gov）。**夹具含 8 处 `xbrldi:typedMember`**（如 `us-gaap:RevenueRemainingPerformanceObligationExpectedTimingOfSatisfactionStartDateAxis`），462 处 `explicitMember`。
8. **F01 文案投影属实**：`dayu/fins/upload_format_contract.py:622,631` 为唯一业务文案投影，计划不动其范围，无 goal drift。

## 2. Assumptions tested（逐项证伪结果）

| # | 计划隐含假设 | 结果 |
| --- | --- | --- |
| A1 | AAPL 夹具是可达的「有效财报正样本」，S1/S2 完成信号在完整 taxonomy 下可达 | **证伪**，见 F1 |
| A2 | `memberQname=None` 只能「归因不明」，须待完整 taxonomy 才能定性 | **证伪/过度保守**，见 F1 |
| A3 | G0-C 要求的「强制机制」可在 Docling/Arelle API 内找到 | **证伪**，见 F3 |
| A4 | S2 真实 CLI 流程存在明确的 sidecar/taxonomy 资源输入通道 | **证伪**，见 F2 |
| A5 | 「确切 API 签名与输入树结构推迟到 G0 之后冻结」不损害可实施性 | **证伪**，见 F2 |
| A6 | G0-A 三平台「对应真实平台 runner」可达 | **未证**，见 F4 |
| A7 | 上游 issue 发布需要「后续授权 gate」 | **与 goal/裁决冲突**，见 F5 |
| A8 | Docling 2.127.0 XBRL option/backend 行为如计划 §2 所述 | 证实（源码一致） |
| A9 | 依赖/锁事实如计划 §1 所述（无 Arelle；2.45.3 不可解、2.44.8 可解） | 证实（元数据一致） |
| A10 | 切片不重开 F01 固定文案、不动 manifest/财报事实格式 | 证实（与 goal 非目标一致） |

## 3. Findings

### 1-未修复-[高]-AAPL 正样本含 typed dimension，Docling 导出路径结构性崩溃，S1/S2 成功边界不可达且归因被低估

- **位置**: §1 第 4 点「现有证据不能唯一归因」；§3 G0-B「不得把 `memberQname=None` 定性为上游缺陷」；§4 Slice S1 完成信号「对有效 instance 输出可序列化 Docling JSON」；§4 Slice S2「以单个完整有效 XBRL instance 跑 …… 若完整有效 instance 仍失败，退回 G0-B 归因」；§5 上游 issue 前置「在完整受控 taxonomy …… 下仍可复现」。
- **问题类型**: 不可直接实施 / 测试缺口 / open question 未收敛（成功边界与已知正样本脱节）
- **当前写法**: 计划把 `dim_value.memberQname=None` 列为「缺远程 taxonomy 的后果，或 Docling/Arelle 独立缺陷，现有证据不能唯一归因」，要求取得完整离线 taxonomy 后复测才能定性；S1/S2 的完成信号均以「完整有效 instance 转换出可序列化 Docling JSON」为准，指定的正样本候选即 AAPL 夹具。
- **反例/失败场景**: G0-B 历经许可审查、下载、hash、catalog 映射取得完整 SEC/FASB taxonomy 后，对同一 AAPL instance 直调 Docling 仍会在 `xbrl_backend.py:344` 抛 `AttributeError`：Arelle `ModelDimensionValue.memberQname` 对 typed dimension **按设计返回 `None`**（`arelle/ModelInstanceObject.py:1504-1513`，`isExplicit` 为假时 `_memberQname = None`；`ModelXbrl.py:701` 注释亦明言 `memberQname  # None if typed dimension`）；Docling 2.127.0 该行 `dim_value.memberQname.localName` 无 None 防护。AAPL 夹具含 8 处 `xbrldi:typedMember`，任一携带 typed 维度的数值事实进入单元格装配即崩溃。E01 已实测走到该行。于是 S1/S2 按写法必然停在「仍失败、归因不明→退回 G0-B」的循环，或迫使实施 Agent 临场换正样本、重定义成功判据。
- **为什么有问题**: 与 goal 成功信号 3（「完整、有效、具备所需 taxonomy 的 XBRL instance 真实 upload_material 从 Docling 转换成功」）的可达性冲突：目标正样本按第三方源码语义结构性不可达。同时计划 §1.4 低估了已有直接证据：Docling 源码 + Arelle 语义 + 夹具 typedMember 三者同源，已足以定性「typed 维度触发导出崩溃」这一与 taxonomy 完整性**无关**的独立触发条件；把该失败整体挂到「完整 taxonomy 后再归因」会造成 G0-B 为已定性的缺陷空耗取证成本，且延误上游 issue 的最小复现准备。
- **直接证据**: `docling/backend/xml/xbrl_backend.py:344`（`f"{dim_qname.localName}: {dim_value.memberQname.localName}"`，无 None 分支）；`optional244/arelle/ModelInstanceObject.py:1498-1513`（typed → `memberQname is None` by design）；AAPL 夹具 `grep typedMember` 计 8 处；E01 `xbrl-local-taxonomy.stderr` 观察栈停在该行。
- **影响**: 实施 Agent 按计划执行 G0-B/S1/S2 将在不可达的完成信号上消耗全部预算；上游 issue 证据链被不必要地推迟；goal 成功信号 3 可能被误判为「Dayu 实现失败」而非第三方导出缺陷。
- **建议改法和验证点**:
  1. 计划 §1.4/§5 把 typed 维度触发的导出崩溃单列为**已定性的第三方缺陷触发条件**（不依赖 taxonomy 完整性），与「explicit 成员因缺 taxonomy 而 `xValid<VALID` 另致 `memberQname=None`」的未定性分支分开表述。
  2. 上游 issue 的最小复现不要以完整 taxonomy 为前置：以自包含微型 taxonomy（E01 已有 `simple.xsd` 机制探针可扩展）+ 一个 typed dimension 复现 `memberQname=None` 崩溃，属合成最小复现，恰合 §5「缩减为不依赖 Dayu 的最小合法 instance」要求；完整 taxonomy 只用于「缺远程 taxonomy 致 explicit 成员失验」那条未定性分支。
  3. 重新定义 S1/S2 正样本与完成信号：要么改用无 typed dimension 的真实合规 instance（并写明选样标准），要么明示 goal 信号 3 的真实财报正样本以该上游缺陷修复为前置、本 work unit 只交付「无 typed 维度样本的受控转换闭环 + 上游 issue 闭环」，交用户/总控裁决后再实施。
- **修复风险（低/中/高）**: 低（改计划表述、补最小复现路径、重定完成信号，不动产品代码）。
- **严重程度（低/中/高/严重）**: 高。

### 2-未修复-[高]-taxonomy sidecar 输入通道与 typed 配置接口整体后置，S1/S2 不可直接实施，S2 命令按计划自身规则无法成功

- **位置**: §4「公共契约」段（「需要一个显式、类型化的 taxonomy 配置输入」「确切 API 签名和输入树结构须由 G0-C 验证过的强制机制确定后冻结在 plan review，不在本文件凭空指定」）；§4 Slice S1 允许改 `docling_runtime.py`/`docling_process_converter.py`；§4 Slice S2 命令 `upload_material …… --files <instance>`（单文件）。
- **问题类型**: 契约缺失 / 不可直接实施 / 过度耦合（把接口设计、机制选择、实施挤进同一后置点）
- **当前写法**: 计划正确禁止「放进 extra payload、进程环境隐式字符串、从上传文件父目录猜测」，但把「显式类型化 taxonomy 配置」的字段、构造者、输入树组装规则整体推迟到 G0-C 之后「冻结在 plan review」；同时 S1/S2 切片已按「改动白名单」形式写好，且 `docling_upload_service.py` 在 S1（「如必须」）与 S2（「允许按实际 owner 最小修改」）双处被许可改动。
- **反例/失败场景**: 实施 Agent 进入 S1 时面对三个未决设计：(a) sidecar 资源从哪来——`--files` 单文件通道没有配套资源入口；把 xsd/linkbase 作为 `--files` 附加项又会被 material「每项都转换」语义各自转换并在 xsd 上失败（`docling_upload_service.py:1500-1507` + `:1009-1011`）；(b) 资源绑定规则——实例的相对 `schemaRef`（如 `aapl-20240928.xsd`）在「不猜父目录」前提下如何解析到管理员 taxonomy root 中的对应文件（catalog 映射？按名匹配？整树复制？Docling `taxonomy` option 本身已整树 copytree，Dayu 自建「受控输入树」与之关系不明）；(c) typed 配置的类型与传递路径——`DoclingConversionConfig` 是闭合 dataclass（`docling_process_converter.py:99-128`），taxonomy 配置进入闭合配置还是独立参数、如何过 pickle 进子进程，均未定。结果是 S1 名为切片、实为一次现场设计；S2 的成功命令 `--files <instance>` 在计划自设规则下取不到 sidecar，`requested_files=1 stored_files=1` 的成功判据按现设计无输入来源，不可能达成。
- **为什么有问题**: Gateflow plan 的交付标准是 code-generation-ready；计划把唯 central 新契约推迟到未来一次「plan review 冻结」，等于承认当前文档不能交给 implementation agent，与 §4「条件通过后的最小设计与实施切片」的实施承诺自相矛盾。且 S1/S2 对同一文件的修改许可重叠，切片边界（计划自称「按可验证行为增量」）在 owner 层面并不闭合。
- **直接证据**: 计划 §4 原文两处（禁父目录猜测 / API 推迟冻结）；`docling_upload_service.py:1003-1008`（只传 bytes+name）、`:1500-1507`（material 全量转换）；`docling_process_converter.py:99-128`（闭合配置）、`:265-268`（`_DoclingProcessTarget` 跨进程字段）；E01「字节流缺原 sibling taxonomy 仍可返回只有标题的成功状态」。
- **影响**: 实施 Agent 重新设计核心契约 → 跨层返工；或各自发明 sidecar 通道 → 违反「语义唯一 owner」；S2 验收必然失败或被降级解释。
- **建议改法和验证点**: 在 plan 层最小冻结三件事（不必等 G0-C）：(1) taxonomy 配置的 typed 形状（字段、校验 owner=`dayu.documents.docling_runtime`、传递路径 Fins→共享进程的显式参数位）；(2) sidecar 绑定机制的产品语义（管理员 taxonomy root 如何按实例 schemaRef/catalog 提供相对资源；明确不猜父目录后这是唯一来源）；(3) S2 成功命令与该机制一致（配置如何随 CLI/workspace 提供）。机制的**安全强制手段**可继续留待 G0-C，但接口轮廓与输入树组装规则必须先冻结；`docling_upload_service.py` 的修改许可收敛到单一 slice。
- **修复风险（低/中/高）**: 中（需要一轮设计决策，但避免实施期现场发明）。
- **严重程度（低/中/高/严重）**: 高。

### 3-未修复-[高]-G0-C 假定存在可验证的「强制机制」，但 Docling/Arelle 契约内无任何引用沙箱，实施范围在「配置管道」与「OS 级沙箱工程」之间未定

- **位置**: §3 G0-C「必须由底层 resolver 的可审计拒绝机制或进程级文件系统/网络隔离提供最终强制边界」「若当前 Docling/Arelle/API/支持平台无法施加强制边界，停下记录该事实与备选方案」；§4「仅为把已验证的 taxonomy 强制边界……落在 owner 处」。
- **问题类型**: 过度设计 / 不可直接实施 / open question 未收敛
- **当前写法**: 计划正确否定「预检即隔离」「`workOffline` 即沙箱」「Python XML 扫描器冒充隔离」，要求最终强制边界只能来自「底层 resolver 的可审计拒绝机制」或「进程级文件系统/网络隔离」，并在 G0-C 用 OS 级访问轨迹验证逃逸矩阵（`file:`、绝对路径、`../`、编码变体、symlink、ZIP/catalog 重定向、远程 URL）。
- **反例/失败场景**: 直接源码核查表明 Docling/Arelle 现有 API **不存在**「resolver 可审计拒绝机制」：`xbrl_backend.py` 全文无沙箱/路径约束，`enable_local_fetch=True` 即放行 Arelle 本地解析，`workOffline` 只影响 webCache。于是 G0-C 的「强制机制」唯一现实候选是进程级 OS 隔离——但 macOS（sandbox-exec 已废弃）、Linux（namespaces/landlock/seccomp）、Windows（受限 token/AppContainer）三端实现成本与能力差异巨大，而项目承诺三平台。计划未在 plan 层列出候选机制与逐平台可行性，实施范围在「几行 option 传递」与「跨平台沙箱子工程」之间悬空；G0-C 大概率以「无法施加强制边界」收场，随后「备选方案」无预置候选，只能再开一轮裁定。
- **为什么有问题**: goal 成功信号 2（「实测引用不能越过所承诺边界」）本身 binding，不算 drift；问题在计划把「验证机制」（G0-C）排在「选定机制」之前，且把机制存在性当作待验证事实而非待决策事项。与 AGENTS.md「不做过度设计，以最小化满足需求为标准」并置，会走向两个极端：要么为本地 CLI 引入重沙箱工程，要么安全目标整体停摆、XML_XBRL 能力悬置而无处置方案。裁决登记「强制本地引用/网络边界是否可在当前 API 与支持平台实现，是否存在过度设计」的预审问题，计划未给出可裁决的答案。
- **直接证据**: `xbrl_backend.py:122-169`（临时目录 + copytree + workOffline，无引用拦截）；`backend_options.py:25-28`（仅两个 bool 开关）；计划 §2 自认「复制目录和关闭 web cache 均不是本地文件访问沙箱」；README 平台承诺含 Windows x64 锁文件。
- **影响**: S1 范围不可估计、不可验收；G0-C 成为预定结论的空转 gate；安全边界与能力声明的处置（含撤回 XML_XBRL）无预置路径。
- **建议改法和验证点**: plan 层先做机制决策树：(1) 列出强制机制候选（转换子进程 OS 隔离、Arelle 插件级 URI 拦截、只读挂载/受限输入树 + 进程降权等）及逐平台可行性证据；(2) 明确「可证明的承诺边界」的最小集合（例如：远程零请求 + 逃逸引用有界失败可证；绝对 `file:` 读取是否在承诺内），让 G0-C 验证承诺边界而非发明机制；(3) 写明机制不可得时的能力处置候选（撤回/文档化限制/管理员显式 opt-in）供 goal 级裁决。验证点：机制候选各附至少一条可执行的验证命令轮廓。
- **修复风险（低/中/高）**: 中（需要决策与少量调研，但把不可控范围收敛为可控选项）。
- **严重程度（低/中/高/严重）**: 高。

### 4-未修复-[中]-G0-A 要求三平台「真实平台 runner」，仓库无 CI/runner 证据，gate 可能整体不可执行

- **位置**: §3 G0-A「分别使用 `constraints/lock-macos-arm64-py311.txt`、`lock-linux-x64-py311.txt`、`lock-windows-x64-py311.txt` 的对应真实平台 runner」。
- **问题类型**: 不可直接实施
- **当前写法**: 要求在 macOS arm64 / Linux x64 / Windows x64 三个真实平台 runner 上做有依赖 resolver/安装与 `pip check`，任一平台不可解则停安装方案、做平台裁决。
- **反例/失败场景**: 仓库无 `.github/`、无任何 CI workflow（已核实根目录无 `.github/workflows`、无 yaml CI 配置），`utils/` 无跨平台锁生成工具，计划也未说明 Linux/Windows runner 来源（自备机器/云 CI/用户执行）。在当前环境只能跑 macOS dry-run 的现实下，G0-A 按写法无法启动，S1 前置永久阻塞；或者实施 Agent 以 macOS 结果冒充三平台——恰是计划自己禁止的。
- **为什么有问题**: goal 成功信号 1 要求「项目支持平台」上可解析并锁定、且与 capability 声明一致；执行载体缺失使该信号无法验证。计划 §2 的 dry-run 自认「只验证本机单包 resolver」，诚实但未补执行路径。
- **直接证据**: `ls -a` 根目录无 `.github`；`constraints/` 三平台锁文件在（历史生成方式无记录）；计划 G0-A 原文；README 明列三平台安装承诺。
- **影响**: gate 空转或被变相绕过；平台承诺与验证脱节。
- **建议改法和验证点**: plan 写明 runner 来源与责任分工（如用户/总控提供 Windows、Linux 环境逐项跑并回传证据，或先在 Linux 容器近似 + 明示 Windows 待补）；或把 G0-A 收敛为「macOS 先行 + 平台矩阵裁决点」，将「不以 macOS 替代其它平台」保留为硬边界；验证点为每平台证据包含完整 argv/exit/`pip freeze`。
- **修复风险（低/中/高）**: 低（补执行路径说明即可）。
- **严重程度（低/中/高/严重）**: 中。

### 5-未修复-[低]-上游 issue 授权表述与既有条件授权冲突

- **位置**: §5「发布 issue 属后续授权 gate，本轮不发送」。
- **问题类型**: 目标漂移（对授权状态的语义表述错误）
- **当前写法**: 把「发布上游 issue」描述为需要再次索取的后续授权 gate。
- **反例/失败场景**: goal 已写明「若最终直接证据定位为 Docling/Arelle 上游，保留最小复现及版本/日志、按用户授权向对应上游提 issue」；裁决登记亦明言「用户已作条件授权，仍需确认直接证据和目标上游，无需再次索取同一授权」。按计划字面执行会在证据齐备后再次停等授权，把已授予的条件授权当缺口；或在 gateflow 记录里误记「无授权」。
- **为什么有问题**: 与 binding goal 的授权事实不一致；正确语义是「条件授权已存在，发布前仍须验证直接证据与目标上游（Docling 还是 Arelle）」。本轮不发送的结论正确，理由错误。
- **直接证据**: goal §已确认目标 5；裁决登记第 3 段「须纠正」；任务输入亦确认「用户已条件授权上游 issue」。
- **影响**: 流程停等与授权状态记录失真。
- **建议改法和验证点**: §5 该句改为「上游 issue 发布的用户条件授权已具备；发布前仍须完成最小复现、锁定目标上游（Docling/Arelle 择一）与证据包复核，本 work unit 不发送」。验证点：gateflow 记录的授权状态与 goal 一致。
- **修复风险（低/中/高）**: 低。
- **严重程度（低/中/高/严重）**: 低。

## 4. Open Questions

- OQ1：G0-A 的 Linux x64 / Windows x64「真实平台 runner」由谁提供？（对应 F4；用户/总控需给执行载体或接受平台承诺收窄。）
- OQ2：SEC/FASB/XBRL taxonomy 的离线再分发许可是否成立？若不成立，goal 成功信号 3 的「完整离线 taxonomy」前提落空，XML_XBRL 公开能力的处置（撤回 / 文档化限制 / 仅管理员显式配置）需 goal 级裁决（goal 非目标已注明撤回须独立裁定）。
- OQ3：G0-C 的「OS 级访问轨迹」跨平台取证工具（macOS `fs usage`/dtrace、Linux strace/audit、Windows ETW）证据等价性是否接受？影响安全矩阵的验收口径。
- OQ4：若 typed 维度缺陷短期无上游修复，goal 信号 3 的「真实财报正样本」是否允许降级为「无 typed 维度的真实合规 instance」或「结构合规合成 instance + 真实财报样本延后」？（对应 F1；需用户/总控裁决，不得由实施 Agent 自定。）

## 5. Residual Risks（建议跟踪去向）

- **R1 依赖索引脆弱性**：`arelle-release 2.45.3` 的 `jaconv>=1,<2` 在当前索引不可解是外部状态，未来 jaconv 发布 1.x 会改变可解性与候选版本。建议跟踪：G0-A 完整解析产物 + 公共锁精确 pin；不要按「最新可解」浮动。
- **R2 Docling 版本语义漂移**：全部第三方行为结论基于 Docling 2.127.0 / docling-core 2.96.0；升级可能改变 XBRL backend 行为。建议跟踪：锁文件钉住精确版本，升级时重跑 G0-B/C 探针。
- **R3 `memberQname=None` 影响面更宽**：Arelle 对 explicit 成员在 `xValid<VALID`（如缺 taxonomy 致成员失验）时同样返回 `None`，typed 维度只是最确定的触发条件。建议跟踪：上游 issue 附两分支说明；完整 taxonomy 复测仍保留（覆盖第二分支），但不作为第一分支的前置。
- **R4 开启 local fetch 后的本地引用面**：`file:`/绝对路径/`../` 引用在 Arelle 下可读任意本地文件（F3 已述无沙箱）；即便承诺边界收窄为「远程零请求」，本地读取面也需在能力文档中如实表述。建议跟踪：F3 机制决策落地后的安全矩阵测试与 README 受控配置说明。
- **R5 夹具/机制探针命名冲突**：Docling `taxonomy` 目录 copytree 后 `instance.xml` 固定写入同树，若 taxonomy 根自带 `instance.xml` 会被静默覆盖。建议跟踪：受控输入树组装规则明确保留名冲突校验（可并入 F2 的接口冻结）。

## 6. 最小修复汇总（按实施顺序）

1. **F1**：计划改写 `memberQname=None` 归因——typed 维度崩溃单列已定性（最小复现不依赖完整 taxonomy，自包含微型 taxonomy 即可）；重定 S1/S2 正样本与完成信号，或明示 goal 信号 3 以上游修复为前置并交裁决。
2. **F2**：plan 层最小冻结 taxonomy typed 配置形状、sidecar 绑定机制的产品语义（管理员 taxonomy root 为唯一来源）与 S2 命令一致性；`docling_upload_service.py` 修改许可收敛到单一切片。
3. **F3**：列出强制机制候选与逐平台可行性，G0-C 改为验证「已承诺边界」；预置机制不可得时的能力处置候选。
4. **F4**：写明三平台 runner 来源，或收敛 G0-A 为分阶段验证并保留「不以 macOS 替代」硬边界。
5. **F5**：把上游 issue 表述改为「条件授权已具备，发布前复核证据与目标上游」。

以上修订完成后应重新走 plan review；当前计划不应直接进入 implementation。

## 7. 结论

**fail**。

理由（按 planreview 判定口径）：F1 使计划指定的正样本与 S1/S2 完成信号在第三方源码语义下结构性不可达，且计划低估了已有直接证据的归因能力；F2 使核心新契约（typed 配置、sidecar 通道、输入树）整体后置，S1/S2 不能作为 code-generation-ready 切片交付，S2 成功命令按计划自身规则取不到输入；F3 使安全强制边界的存在性被当成待验证事实，实施范围在最小管道改造与跨平台沙箱工程之间悬空。三者均绑定具体计划位置与代码/第三方源码事实，属真实可执行性与成功边界问题，非风格偏好。计划对第三方契约、依赖事实、E01 观察的引用经核对属实，条件性停损姿态诚实（A8/A9 证实部分），但以当前形态交给 implementation agent 会导致空转 gate、临场设计或不可达验收，故整体 fail；按 §6 最小修复修订后可复审。

（本文件为指定唯一 artifact；本轮未改任何计划/产品/测试/依赖/README/goal/裁决文件，未安装依赖、未下载 taxonomy、未对外发布 issue。）
