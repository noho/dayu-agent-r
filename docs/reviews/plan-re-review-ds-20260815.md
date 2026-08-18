# Plan Re-Review（第二路 AgentDS）：UF-FIX06 converter-capability-owner 修订后计划

- **Reviewed target**：`docs/gateflow/uf-fix06-converter-capability-owner-plan-20260815.md`（plan fix 后修订版）
- **Reviewer**：AgentDS（原 review `docs/reviews/plan-review-20260815-135414.md` 作者，本轮为 re-review）
- **Timestamp**：2026-08-15 14:19:05 +0800（系统时钟生成）
- **Review inputs**（均已读到 EOF）：
  - 原 plan 修订版：`docs/gateflow/uf-fix06-converter-capability-owner-plan-20260815.md`
  - fix 记录：`docs/gateflow/uf-fix06-converter-capability-owner-plan-fix-20260815.md`
  - 原 review：`docs/reviews/plan-review-20260815-135206.md`（AgentMiMo）、`docs/reviews/plan-review-20260815-135414.md`（AgentDS）
  - Controller 裁决：`docs/reviews/uf-fix06-plan-review-adjudication-20260815.md`
- **Review scope**：只做 review；未改 plan/代码/测试/README/registry/evidence，未 commit，未运行 UF-PF06/UF-PF12。
- **核心判据**：plan 是否 code-generation-ready——九个 Controller accepted findings 是否真正落实，实现 agent 是否仍需在用户可见语义上自行设计。

## 结论先行

**fail**

九个裁决 finding（M1/M2/D1–D5/O1/O2）的方向性修复**全部真实落实**，架构与语义 owner 边界成立，无结构性重写需求。但 plan §12 声称“没有需要实现 agent 自行猜测的 open question”仍不成立，存在两处用户可见语义在实现时才会被决定的缺口：

- **F-B（中）**：material tool 路径的 usage 失败投影未闭合——workflow catch-all 会把新的 `FinsUploadFormatError` 映射为 `UNEXPECTED_RUNTIME` 通用错误，plan 声称的“usage 语义”与 Slice 3 测试按现有映射层不可确定通过；`upload_failure.py` 不在任何 slice 的 allowed files。
- **F-A（中）**：“产品明确选定的最小受控子集”在 plan 中没有枚举——用户可见的 suffix 清单（help/schema/README）与 batch 候选集由实现 agent 在 Slice 1 现场决定。
- **F-C（低）**：delete 空状态的跨层表述张力与 delete+非空 selection 拒绝规则未声明、未测试。

三者均为 plan 文本级修订（各一段声明 + 一条测试）即可收敛，不需要架构重写；修订后即可 pass。

## 一、逐项修复验证（M1/M2/D1–D5/O1/O2）

| ID | Controller 要求 | re-review 结论 | 直接证据 |
|---|---|---|---|
| M1 | 静态产品声明 + 构造期 lazy 校验，help 不 import Docling | **已修复** | plan §5.1 冻结两阶段与模块级实例；`docling_runtime.py:42-48` Docling 仅 TYPE_CHECKING 导入、`375-378` 构造函数内 lazy import——静态声明/help 投影不触发 Docling import 在当前模块结构下可实现，Slice 1 测试“help 不触发 Docling import”可真实通过 |
| M2 | `.xml` 说明为 XBRL XML candidate | **已修复** | plan §5.1 特别约束、§5.2 projection、§6.2 三面文案、Slice 2/4 测试均固化该文案，且明说 suffix 不承诺内容成功 |
| D1 | material 同 owner 前置 admission、全转换 | **部分修复**（admission 已修复；tool 路径 failure 投影未闭合 → 新 finding F-B） | plan §5.2/§5.3/§6.2、Slice 2/3：`FinsUploadMaterialFiles` + `MATERIAL_SUFFIX_UNSUPPORTED`、CLI `_validated_upload_files`（`fins.py:1113-1133`，唯一调用方是 material direct stream `fins.py:713`，迁移范围准确）、workflow 在 company staging 前构造（SEC staging 在 `sec_upload_workflow.py:486-499`，构造点已在 staging 之前指定）。但投影链见 F-B |
| D2 | `prepare_upload` closed union 签名 + `SourceKind` 一致性 | **已修复** | plan §5.4 给出精确签名与入口校验顺序（先类型一致、后非空要求、零副作用）；现有签名 `docling_upload_service.py:241-255` 保留 `action` 参数，delete 分支 `297-303` 在文件校验前早退，与“空 selection + delete 早退”设计吻合；Slice 3 测试断言非法组合 `ValueError` + 零读取/零 converter/零 batch |
| D3 | 子集校验替代精确相等，fail-fast on missing | **已修复**（但子集内容未枚举 → 新 finding F-A） | plan §5.1 改为“产品 suffix ∈ 对应 `FormatToExtensions`”单向子集校验，第三方新增 suffix 不 fail 不公开、已声明缺失 typed fail-fast；constructor `allowed_formats` 与产品 format ids 精确同源；Slice 1 测试三态断言齐备 |
| D4 | batch 边界澄清：单文件命令 + `.xsd` 稳定 skip | **已修复** | plan §6.2/§3.2/Slice 2 测试与 stop condition；`upload_batch.py:436-443` 现状即 `unsupported_suffix` skip，`.xsd` 在新 `accepts_primary` 下行为与现状一致，无需归组改动 |
| D5 | companion 无伪转换事件 | **已修复** | plan §5.4/不变式 12/Slice 3 双 fixture 事件断言；事件名与 source 值经代码证实：`conversion_started` 在 `docling_upload_service.py:760` 逐文件发出、`file_uploaded` 在 `:535` 携带 `asset.source`、`_ASSET_SOURCE_ORIGINAL="original"`（`:75`） |
| O1 | 三面一致承诺首文件 primary | **已修复** | Slice 2 测试（help+schema 自足说明）+ Slice 4“逐面对照”验收固化 |
| O2 | 多 converter-capable fixture | **已修复** | Slice 3 测试新增 DOCX+XLSX+DOCX：只转换首项、后两项原样存储、唯一派生资产与 `primary_document` 同源首项、requested/stored=3、companions 无伪转换事件 |

## 二、六项 adversarial 检查

### 1. typed delete empty state

**结论：基本闭合，一处表述张力 + 一处规则缺口（F-C）。**

- material delete 真实存在：tool schema `action` 字段明确“delete 表示删除匹配的已存源文件，且不能同时提供 files”（`upload_tools.py:231`），故 `FinsUploadMaterialFiles.for_delete` 不是死 API，两个 selection 的 empty-for-delete 构造入口均有真实消费方。
- `prepare_upload` 保留 `action` 参数且 delete 分支在读取/校验文件前早退（`docling_upload_service.py:297-303`），plan §5.4“读取文件前按现有 delete 分支返回”与代码吻合。
- 张力：§5.2 说“不用 raw list、`None`、默认值或双输入参数表示该状态”，§5.3 却用 `file_selection: FinsUploadFilingFiles | None` 的 `None` 表示 delete。跨层双表示本身被 workflow 转换显式指定，不构成 blocker，但两节字面冲突。
- 缺口：§5.4 只规定“create/update 另要求非空 upsert selection”，未规定 **delete + 非空 selection** 的拒绝规则，Slice 3 测试也只回归“空 selection + delete”与“非法类型组合”，无 delete+非空 断言。上游（tool schema/validator）已关闭该输入空间，Service 入口缺防御性规则，属可接受但未闭合。

### 2. 静态产品 suffix owner

**结论：owner 归属成立（documents capability），M1/D3 方向修复真实；但静态声明的**内容**未冻结（F-A）。**

- 模块级静态声明 + 构造期 lazy 子集校验，在当前 `docling_runtime.py` 的 TYPE_CHECKING + 函数内 lazy import 结构下可实现（已核验）。
- plan §5.1 列出 9 个候选 format id、给出排除项（legacy DOC/PPT/XLS、ZIP、`.text/.Rmd/.qmd/.xlsm/.potx` 不自动公开）与停止条件，但**未枚举每个 format 的产品 suffix 最小子集**。证据只锚定了个别成员（如 UF-C06 要求 HTML 集合必须含 `.htm`），HTML 是否含 `.xhtml`、Markdown/text 是否含 `.txt`、XML_XBRL 的 `.xml/.xbrl` 组合等，仍是实现 agent 在 Slice 1 现场决定。而该清单正是 help/schema/README 的精确投影内容与 batch 候选集的判定依据——用户可见契约的内容在实现时才被决定，与 §5.1“产品明确选定的”措辞及 Controller“明确最小子集”的要求不符。

### 3. material tool/service 前置准入

**结论：admission 修复成立；tool 路径 failure 投影链未闭合（F-B）。**

- 同 owner 构造入口、CLI helper 迁移、Service 删除 `SUPPORTED_UPLOAD_SUFFIXES` 但保留 exists/regular/empty-content、workflow 在 company staging 前构造、material 全转换不变——均已在 plan 中闭合，且与代码调用点（`service_runtime.py:195-264`、`sec_upload_workflow.py:486-520`、`fins.py:1113-1133`）逐一吻合。
- 投影缺口：SEC/CN material workflow 均有 catch-all（`sec_upload_workflow.py:564`、`cn_pipeline.py:1179`）→ `fins_upload_failure_from_exception`（`upload_failure.py:172-236`）→ 未知异常一律 `RUNTIME/UNEXPECTED_RUNTIME`（文案“上传执行失败，请检查运行日志后重试”）；`FinsUploadFailureKind` 只有 CONTENT/STORAGE/RUNTIME（`upload_failure.py:27-32`），无 USAGE kind。plan 声称“非法 suffix 以 typed/bounded usage 语义失败”，但：
  - 未指定构造点相对 workflow try/except 的位置（“company staging 前”包含 try 内与 try 外两种落点，两种落点的用户可见结果不同：前者被 catch-all 吞成 RUNTIME 通用错误，后者异常向 service_runtime 传播）；
  - 未说明 `FinsUploadFormatError` 的基类与 tool/engine 层的投影方式；
  - `dayu/fins/upload_failure.py` 不在任何 slice 的 allowed production files。
  - Slice 3 测试“以 typed/bounded usage 语义失败”按现有映射层不可确定通过：若断言失败 kind/message，则 try 内落点必然失败；若只断言异常类型+零副作用，则与 §5.3 的“usage 语义”声称脱钩。两条落点都满足 plan 文本、却给出不同的用户可见语义，实现 agent 被迫自行裁决。

### 4. batch 边界

**结论：D4 修复成立。**

- `.xsd` 稳定 `unsupported_suffix` skip 即现状行为（`upload_batch.py:436-443`），不自动归组、deferred 到 batch association / UF-FIX07 均已显式声明并有测试固化。
- 仅剩影响面：batch 候选集将随 capability 变化（`.xls/.zip` 退出、`.md/.txt` 等可能进入），plan 未枚举该变化且未断言全候选集——计入 F-A 的影响面，不单列 finding。

### 5. 事件语义

**结论：D5 修复成立，无新 finding。**

- plan 规定 companion 不产生 `conversion_started` 或任何伪转换事件，只沿 original publication 路径产生 `file_uploaded`（source=`original`），不新增 event type；不变式 12 与 Slice 3 双 fixture 断言齐备。
- 事件名与 source 取值经代码证实（见上表 D5 行），测试断言不会与真实事件流脱节。

### 6. 测试闭合

**结论：O1/O2 修复成立；F-B/F-C 对应两个测试缺口未闭合。**

- O1 三面一致性验收（Slice 2/4）、O2 多 converter-capable fixture（Slice 3）已固化，material invalid-suffix 端到端断言与零副作用断言已列入。
- 缺口一：material tool 路径“usage 语义”断言按现有映射层不可确定通过（F-B）。
- 缺口二：delete+非空 selection 拒绝无测试（F-C）。
- 其余验证计划（§9 命令清单、逐文件 ≥80% coverage、pyright、静态 owner audit、SHA-256 冻结证据复核）完整可执行。

## 三、Findings

### R1-未修复-中-material tool 路径 usage 失败投影链未闭合（D1 部分修复的残留）

- **位置**：plan §5.3（“非法 suffix 以 typed/bounded usage 语义失败”）、Slice 3 Tests（tool 路径断言）、Slice 2/3 allowed files（无 `dayu/fins/upload_failure.py`）。
- **问题类型**：不可直接实施 / 契约缺失。
- **当前写法**：material workflow 在 company staging 前构造 `FinsUploadMaterialFiles`，失败以“typed/bounded usage 语义”呈现；Slice 3 断言 tool 路径非法 suffix“以 typed/bounded usage 语义失败，且 converter call 为 0”。
- **直接证据**：`sec_upload_workflow.py:564` 与 `cn_pipeline.py:1179` 的 `except Exception` → `upload_failure.py:172-236` 未知异常映射为 `RUNTIME/UNEXPECTED_RUNTIME`；`FinsUploadFailureKind`（`upload_failure.py:27-32`）无 USAGE 成员；`upload_failure.py` 不在任何 slice allowed files；plan 未指定构造点与 workflow try/except 的相对位置，也未指定 `FinsUploadFormatError` 基类与 tool 层投影。
- **为什么有问题**：同一 plan 文本允许两种落点（try 内/外），产生两种不同的用户可见语义（RUNTIME 通用错误 vs usage 异常传播）；Slice 3 的 usage 断言按现有映射层不可确定通过；若实现 agent 选择扩展映射层，则需修改不在 allowed files 内的 failure contract owner，越过 plan 边界。Controller 裁决第 7 条明确要求“使实现 agent 无需自行设计”，此处未达成。
- **影响**：实施 Agent 跑偏或越界改文件 / 用户对 suffix 错误收到误导性“运行失败”文案 / 测试按现文案不可验收。
- **修复要求**（plan 文本级，二选一并冻结）：(a) 明确构造点在 workflow try/except **之前**，`FinsUploadFormatError` 沿 `service_runtime` 既有 usage 异常传播契约（`service_runtime.py:76` 已文档化 `FinsUploadUsageError` 传播）向 tool/engine 层传播，并声明其基类与投影方式；或 (b) 扩展 `fins_upload_failure_from_exception` 增加 USAGE kind/code，并把 `upload_failure.py` 加入对应 slice allowed files。同时把 Slice 3 测试改为断言**投影后**的 failure kind/message（usage 语义）而不仅是零副作用。
- **原 finding 状态**：D1 `accepted`，admission owner 已修复；本 finding 为 D1 的投影链残留。
- **修复风险**：低。**严重程度**：中。

### R2-未修复-中-静态产品声明的“最小受控子集”未枚举，用户可见 suffix 契约由实现 agent 现场决定（D3 的声明内容残留）

- **位置**：plan §5.1（“每个 format id 的 suffix tuple 必须是产品明确选定的最小受控子集”）、Slice 1 Exact changes、§6.2（batch 候选集）、Slice 2/4（精确投影断言）。
- **问题类型**：不可直接实施 / 契约缺失（用户可见面）。
- **当前写法**：plan 给出 9 个候选 format id、排除项与停止条件，但未逐 format 枚举产品 suffix 元组；Slice 1 测试只做相对断言（子集、不扩面），help/schema/README 的精确清单以 capability 为真源。
- **直接证据**：plan §5.1 原文；UF-C06 冻结证据只锚定 HTML 集合必须含 `.htm`；HTML 是否含 `.xhtml`、Markdown/text 的 `.txt`、XML_XBRL 的 `.xml/.xbrl` 组合等在 plan 中无记录；batch 候选集将随之变化（`.xls/.zip` 退出、`.md/.txt` 等可能进入）且无全候选集断言。
- **为什么有问题**：suffix 清单是 CLI help、LLM-facing schema、README 三面的精确投影内容与 batch 候选集的判定依据，属用户可见公共契约；“产品明确选定的”断言与“由实现 agent 在 Slice 1 按约束现场选择”的事实矛盾；Controller 对 D3 的要求是“明确最小子集”，明确性未落到 plan 文本。
- **影响**：实施 Agent 替产品做用户可见决策 / batch 行为变化不可验收 / Slice 2/4“精确”断言缺乏 plan 级锚点。
- **修复要求**：在 §5.1 枚举逐 format 的产品 suffix 元组（至少钉死证据驱动的成员：HTML ⊇ `.htm`（UF-C06）、XML_XBRL = `.xml/.xbrl`，其余按“最小受控”逐项列出），或新增显式 gate：最终静态声明须经 Controller 确认后方可进入 Slice 2/4 投影；并补充 batch 全候选集行为测试（`.xls/.zip` 不再生成命令、新增 suffix 是否生成命令按声明）。
- **原 finding 状态**：D3 `accepted`，校验策略已修复；本 finding 为 D3 的声明内容残留。
- **修复风险**：低。**严重程度**：中。

### R3-未修复-低-delete 空状态跨层表述张力与 delete+非空 selection 拒绝规则未声明

- **位置**：plan §5.2（“不用 raw list、`None`、默认值或双输入参数表示该状态”）vs §5.3（`file_selection: FinsUploadFilingFiles | None`，“delete 保持 `None`”）；§5.4；Slice 3 Tests。
- **问题类型**：契约缺失 / 测试缺口。
- **当前写法**：Service 层 delete 用 empty-for-delete selection，validated request 层 delete 用 `None`，workflow 负责转换；§5.4 只规定 create/update 非空，未规定 delete+非空 selection 的拒绝。
- **直接证据**：plan §5.2/§5.3 原文；`ValidatedFinsUploadFilingRequest`（`ingestion_runtime.py:714`）`resolved_action` 含 `"delete"`；tool schema（`upload_tools.py:237`）已禁止 delete 提供 files。
- **为什么有问题**：两节对同一状态的表示字面冲突，实现 agent 需自行调和；Service 入口对 delete+非空 selection 无防御性拒绝规则与测试，与“禁止 raw list/双输入表示状态”的收紧意图不完全一致。
- **影响**：实现解读分歧（低概率跑偏）/ 入口防御不完整。
- **修复要求**：二选一写清——§5.3 改为 delete 也携带 empty-for-delete selection（`file_selection` 非 Optional），或 §5.2 明确 `None` 仅限 validated request 层的“无文件事实”、Service 层统一 empty-for-delete；并在 §5.4 与 Slice 3 测试补“delete+非空 selection 在 Service 入口拒绝、零副作用”一条。
- **原 finding 状态**：D2 `accepted` 的相关面；D2 主修复成立，本项为其相邻边界。
- **修复风险**：低。**严重程度**：低。

## 四、Open Questions

无新增。R1/R2/R3 均为已定位、可直接修复的 plan 文本级缺口，不需要回到 Controller 重新裁决 goal。

## 五、Residual Risks and suggested tracking destination

| 风险 | 建议去向 |
|---|---|
| batch companion association（同目录归组） | 后续 batch association / UF-FIX07 类 work unit（plan §10 已分类） |
| 真实全格式矩阵与 XBRL companion CLI evidence | UF-PF06（plan 已声明，不重跑） |
| 137 条 full-real mandatory matrix | UF-PF12（plan 已声明，不重跑） |
| 显式 primary、重复输入、basename/derived-name collision | UF-FIX07（plan 已声明） |
| `.xsd` 以外 companion-only 类型 | 后续 Fins/XBRL 产品能力 work unit（plan 已分类） |
| 第三方删除已声明 suffix 时 help 静态展示但运行 fail-fast | plan §10 已定性为有意的安全失败；pinned dependency + owner test 管理 |
| 共享 converter builder 的其他消费者受 `allowed_formats` 收紧影响 | 上一轮已核实：tests/tools/web 不在 scope、CN download 只转换 PDF；维持不计 finding |

## 六、Final plan review conclusion

**fail**

九个 Controller accepted findings 的修复方向**全部真实落实**（逐项代码证据见第一节），架构与语义 owner 边界成立：documents capability 静态声明 + lazy 子集校验在当前模块结构下可实现，closed union 签名与 delete 早退顺序与现有代码吻合，事件名/source 取值经代码证实，batch `.xsd` skip 即现状行为。剩余三个 finding（R1 中、R2 中、R3 低）均为 plan 文本级修订即可收敛：各需一段明确声明（投影链/子集枚举/delete 表述）加一条测试断言，不需要结构性重写，也不需要重新裁决 goal。修订并消除 R1/R2/R3 后，本 work unit 的 plan 可判定 pass 并进入 implementation。

**允许的下一动作**：plan review fix（针对 R1/R2/R3）→ re-review；在 R1/R2/R3 收敛前不建议授权 implementation。
