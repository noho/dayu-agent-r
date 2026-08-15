# UF-FIX06 Plan Re-Review

## Review Metadata

- **Reviewed target**: `docs/gateflow/uf-fix06-converter-capability-owner-plan-20260815.md`（plan review fix 后修订版）
- **Reviewer**: AgentMiMo（re-review）
- **Timestamp**: 2026-08-15T14:13:58+08:00（系统时钟生成）
- **Baseline commit**: `a3d584fcf1444fcf5d633f2dd8bdb83eaf5adab9`
- **Review scope**: 逐项验证 Controller 裁决的 9 个 findings（M1/M2/D1–D5/O1/O2）是否在修订 plan 中真正修复；adversarial 检查 typed delete empty state、静态产品 suffix owner、material tool/service 前置准入、batch 边界、事件语义与测试闭合
- **输入 artifacts**（均已完整读取至 EOF）:
  - Plan fix 后修订版: `docs/gateflow/uf-fix06-converter-capability-owner-plan-20260815.md`（464 行）
  - Plan fix 记录: `docs/gateflow/uf-fix06-converter-capability-owner-plan-fix-20260815.md`（78 行）
  - MiMo 原 review: `docs/reviews/plan-review-20260815-135206.md`（132 行）
  - DS 原 review: `docs/reviews/plan-review-20260815-135414.md`（111 行）
  - Controller 裁决: `docs/reviews/uf-fix06-plan-review-adjudication-20260815.md`（60 行）
- **Binding scope contract**: goal confirmation SHA-256 `2e2729c3…`、oracle `88b04ca4…`、scenario `a357e5a1…`、frozen UF-O12 `fe3029cd…`/`e2d3b589…`——均已按 SHA-256 定位并复核一致
- **Lenses applied**: goal-bound minimal design / architecture boundary / best-practice / optimal-solution / overengineering / overcoupling

## 1. 逐项验证：Controller accepted findings 修复状态

### M1 — help projection 懒加载边界（原 MiMo medium）

**Controller 裁决**: 明确 capability 使用模块级不可变产品声明；help/schema 只读该声明，不 import Docling；converter construction 才 lazy import 并验证。

**修订 plan 中的修复证据**:

- §5.1: "`DOCLING_CONVERTER_CAPABILITY`：唯一模块级实例；它只包含稳定字符串 format id 与明确选定的归一化 suffix tuple，模块初始化不 import Docling。CLI help 与 tool schema 只读该静态对象。"
- §5.1: "私有解析/校验 helper：只在现有 converter construction path 被调用时 lazy import Docling，把稳定 format id 解析成 `InputFormat`，并逐项校验"
- §5.1: "help/schema 投影只能读取上述模块级轻量静态 capability，不得在参数解析/模块导入阶段加载 Docling"
- Slice 1 Stop condition: "若任一 consumer 要求 help/schema 通过 import Docling 动态产生 suffix，停止并回到 owner 设计；正确路径已冻结为'静态产品声明 + construction-time lazy 子集校验'"
- Slice 1 Tests: "help 所需静态投影不触发 Docling import"

**裁决**: **已修复**。两阶段设计（模块级静态声明 + 构造期 lazy 校验）已明确冻结，stop condition 不再要求 implementation agent 自行设计。

**residual note**: plan 未显式说明 suffix tuple 是模块级字面量 hardcode 还是从某处派生。鉴于"模块初始化不 import Docling"的约束，实现 agent 只能选择 hardcode 字面量——设计路径已收敛，但 plan 若补充一句"suffix tuple 为模块级字面量"可消除最后的歧义。不构成 finding。

### M2 — XML 后缀歧义 help 文案（原 MiMo low）

**Controller 裁决**: help/schema 必须把 `.xml` 说明为 XBRL XML candidate，明确 suffix 不保证内容成功。

**修订 plan 中的修复证据**:

- §5.2 projection helper: "对 `.xml` 使用 XBRL candidate 限定文案；不得泄漏内部 enum/id"
- §5.2 projection helper 自足说明: "`.xml` 仅是 XBRL XML candidate，suffix 通过不代表任意 XML 或内容必然转换成功"
- §6.2: "`.xml` 仅是 XBRL XML candidate"
- Slice 2 Tests: "`.xml` 文案不得宣称任意 XML"
- Slice 4 Tests: "逐面对照 CLI `upload filing --help`、LLM-facing upload tool schema 与根 README，断言三者一致承诺…`.xml` 仅为 XBRL candidate"

**裁决**: **已修复**。三面（CLI help、tool schema、README）一致的 `.xml` XBRL 限定文案已明确要求，Slice 4 有逐面对照断言。

### D1 — material suffix admission owner 空洞（原 DS high）

**Controller 裁决**: Fins upload format contract 同时提供 filing 与 material 的 typed selection；material tool/Service 路径在 converter 前调用同一 owner。

**修订 plan 中的修复证据**:

- §3.1 #8: "material 上传在 CLI 与 tool/Service 入口都由同一 Fins owner 构造 typed selection 并完成 suffix admission"
- §5.2: `FinsUploadMaterialFiles` 定义——"upsert 构造入口要求非空，用 converter product suffix 投影逐项校验"
- §5.3: "material 不经 filing request validator，但不得因此绕过 admission：CLI `_validated_upload_files` 与 tool/Service workflow 都必须在任何 converter call 前调用 `FinsUploadMaterialFiles` 的同一 owner 构造入口。tool/Service 路径要在 SEC material company staging 或 CN/HK 等价业务 mutation 前完成该构造；非法 suffix 以 typed/bounded usage 语义失败，不进入 converter，不发布 company/source state。Service 保留现有 exists/regular/empty-content 检查，但删除 Service-local suffix 常量与重复 suffix 规则。"
- §6.2: "CLI material 校验复用 `FinsUploadMaterialFiles` 的同一 owner 构造入口；tool/Service material workflow 也在业务 mutation 和 converter 前构造该 selection"
- §6.2: "tool runtime 仍构造 raw request；filing 进入同一 Fins validator，material 进入同一 Fins material selection owner，均不建立旁路"
- Slice 3 Tests: "material 两文件仍转换两次…CLI 与'LLM upload tool raw request -> `ProductionFinsUploadRunner` -> material workflow -> Service'路径上的非法 suffix 必须在 company/source mutation、文件读取和 converter call 前以 typed/bounded usage 语义失败，且 converter call 为 0"

**裁决**: **已修复**。material admission owner 已明确为 `FinsUploadMaterialFiles` 的同一构造入口，CLI 和 tool/Service 两条路径均覆盖，tool 路径的准入时机（mutation 前）和失败语义（typed/bounded usage）均有明确规定和测试断言。

### D2 — `prepare_upload` 严格签名不明确（原 DS medium）

**Controller 裁决**: 冻结为单一 closed union 参数 `FinsUploadFilingFiles | FinsUploadMaterialFiles`，校验 selection kind 与 `SourceKind` 一致。

**修订 plan 中的修复证据**:

- §5.4: 精确签名 `selection: FinsUploadFilingFiles | FinsUploadMaterialFiles`，其他关键字参数不变
- §5.4: "Service 入口首先校验 `source_kind is SourceKind.FILING` 必须对应 `FinsUploadFilingFiles`，`source_kind is SourceKind.MATERIAL` 必须对应 `FinsUploadMaterialFiles`；不匹配立即抛 `ValueError`，不读文件、不调 converter、不开 batch"
- §5.4: "禁止 raw list 与 role selection 双输入，禁止 `None`/default/fallback 分支"
- §7 #11: "`prepare_upload` 只接收 filing/material closed typed union，selection 必须与 `SourceKind` 一致"
- Slice 3 Tests: "`source_kind=filing` + material selection 与 `source_kind=material` + filing selection 都在 Service 入口以 `ValueError` 拒绝，且零文件读取、零 converter、零 batch"

**裁决**: **已修复**。签名、类型约束、一致性校验、非法组合的拒绝语义均有明确规定，implementation agent 无需自行设计。

### D3 — 精确相等校验反向锁定（原 DS medium）

**Controller 裁决**: 产品 suffix 是最小子集；construction-time 校验每个声明 suffix 属于对应第三方格式映射，缺失 fail-fast；第三方新增 suffix 不自动进入 contract。

**修订 plan 中的修复证据**:

- §5.1: "真实构造时 lazy 校验每个 suffix 受对应 `FormatToExtensions` 支持"
- §5.1 特别约束: "若第三方 format id 缺失或任一已声明 suffix 不再被对应映射支持，立即抛出已有 typed runtime initialization error；不得静默缩减、扩大或 fallback 到 Docling 默认全格式"
- §5.1: "第三方新增的 suffix 不是产品 contract，不进入 help/schema，也不导致构造失败"
- Slice 1 Tests: "format id 缺失或已声明 suffix 被第三方删除均产生 typed `DoclingRuntimeInitializationError`，不 fallback；第三方新增 suffix 时构造继续成功且 help 不扩面"
- §10 Capability residual: "第三方可能删除产品已声明 suffix 或 format id → Slice 1 构造期对'产品 suffix ⊆ 第三方映射'做 fail-fast"
- §11: "产品 suffix 只是第三方映射的受控最小子集；构造期只做 lazy 支持性校验"

**裁决**: **已修复**。从双向精确相等改为单向子集校验（产品 suffix ∈ 第三方映射），方向明确：缺失 fail-fast，新增不扩面。`allowed_formats` 仍与产品 format ids 精确同源——这是 format id 级的同源，不是 suffix 级的精确相等。

### D4 — batch companion 语义未声明（原 DS medium）

**Controller 裁决**: `upload_filings_from` 保持单文件命令，`.xsd` 稳定 skip，不做同目录归组。direct `upload_filing --files primary companion...` 是本轮 companion 目标入口。

**修订 plan 中的修复证据**:

- §6.2: "`upload_filings_from` 继续按单文件生成独立 upload 命令，每个候选只消费 owner 的 `accepts_primary`。`.xsd` companion-only 文件必须稳定地以 `unsupported_suffix` skip，不作为 standalone candidate，也不自动与同目录 HTML/XBRL 归组。自动归组明确 deferred 到后续 batch association / UF-FIX07 类 work unit。"
- §6.2: "本轮 XBRL companion 的产品目标入口是 direct `upload_filing --files primary companion...`"
- Slice 2 Tests: "batch 扫描包含 HTML/XBRL + `.xsd` 的目录时，`.xsd` 稳定 `unsupported_suffix` skip，不生成 standalone command、不自动归组，且 batch 不再引用旧 allow-list"
- Slice 2 Stop condition: "若 batch 实现需要将 companion 与 primary 自动关联，停止并记入后续 batch association / UF-FIX07 类 work unit"
- §10 Batch association residual: 明确归入后续 work unit

**裁决**: **已修复**。batch 的 companion 语义边界已明确声明（skip + deferred），direct upload 是本轮目标入口，测试固化 skip 行为。

### D5 — companion 事件契约缺失（原 DS low）

**Controller 裁决**: companion 不产生 `conversion_started` 或伪转换事件，只产生 source=`original` 的正常 `file_uploaded`。

**修订 plan 中的修复证据**:

- §5.4: "filing companion 不产生 `conversion_started` 或任何伪转换事件；它只沿现有 original publication 路径产生正常 `file_uploaded` 事件，事件的 source 保持 `original`，不新增 event type"
- §7 #12: "filing companions 无 `conversion_started`，只有 original `file_uploaded`；不伪造转换事实"
- Slice 3 Tests: "XSD 没有 `conversion_started`，仅有 source=`original` 的 `file_uploaded`"
- Slice 3 Exact changes #5: "companions 仅作为 originals 进入同一 pending batch；不对 companion 发 `conversion_started`，只保留 source=`original` 的正常 `file_uploaded`，不新增 event type"

**裁决**: **已修复**。事件序列规则、禁止项和测试断言均已明确。

### O1 — 用户可见首文件规则（原 DS open question → accepted）

**Controller 裁决**: Slice 2/4 明确断言 CLI help、LLM-facing schema、README 三面一致说明首文件 primary、后续 raw companions。

**修订 plan 中的修复证据**:

- §5.2 projection helper: "自足说明 filing 首文件 primary、后续 raw companions、primary 必须实际转换成功、companions 不转换"
- §6.2: "CLI `upload filing --help`、upload tool 的 LLM-facing schema 与根 README 三面必须使用一致的业务文案：首文件是 primary 且必须实际转换成功；后续文件是仅原样保存、不转换的 companions"
- Slice 2 Tests: "`--help` 和 LLM-facing schema 自足说明角色、实际转换要求、raw companion 与静态产品投影的确切 suffix"
- Slice 4 Tests: "逐面对照 CLI `upload filing --help`、LLM-facing upload tool schema 与根 README，断言三者一致承诺'首文件 primary、后续 raw companions、companions 不转换、`.xml` 仅为 XBRL candidate、suffix 不保证内容成功'"

**裁决**: **已修复**。三面一致的用户可见承诺已明确要求，Slice 4 有逐面对照断言。

### O2 — 多 converter-capable 输入 fixture（原 DS open question → accepted）

**Controller 裁决**: 增加 owner/service 级测试：DOCX + XLSX + DOCX 只转换首项，其余原样存储。

**修订 plan 中的修复证据**:

- Slice 3 Tests: "DOCX + XLSX + DOCX：converter 只收到首个 DOCX；XLSX 与第二个 DOCX 作为 raw companions 原样存储；只有首项的一个 Docling 派生资产；`primary_document` 指向首项转换结果；requested/stored 都为 3，该两个 companion 均无 `conversion_started`"

**裁决**: **已修复**。测试 fixture 的输入、converter 调用、存储、计数和事件断言均已明确。

## 2. Adversarial 检查

### 2.1 Typed delete empty state

**plan 规定**:

- §5.2: `FinsUploadFilingFiles` 的 `for_delete` 是唯一合法空状态——`primary=None, companions=()`
- §5.2: "`from_upsert_paths` 接收非空 path tuple…`for_delete` 唯一合法空状态是 `primary=None, companions=()`"
- §5.2: "`FinsUploadMaterialFiles`…upsert 构造入口要求非空…为保持现有 delete 不需文件的语义，两个 selection 均提供明确的 empty-for-delete 构造入口"
- §5.4: "delete 只消费对应 source kind 的 empty-for-delete selection，并在读取文件前按现有 delete 分支返回"
- §5.4: "create/update 有文件时必须得到非空 selection；delete 保持 `None`"
- §7 #11: "`prepare_upload` 只接收 filing/material closed typed union"
- Slice 3 Tests: "delete empty selection 的类型一致性与既有无文件 delete 行为同时回归"

**评估**: delete empty state 设计严密。两个 selection 均有明确的 empty-for-delete 入口，Service 校验 selection 与 `SourceKind` 一致，create/update 要求非空。禁止 raw list、`None`、默认值或双输入参数表示空状态——实现 agent 没有歧义空间。

**风险**: 无。

### 2.2 静态产品 suffix owner

**plan 规定**:

- §4 owner table: converter capability 唯一 owner 是 `dayu.documents.docling_runtime`
- §5.1: "`DOCLING_CONVERTER_CAPABILITY`：唯一模块级实例；它只包含稳定字符串 format id 与明确选定的归一化 suffix tuple，模块初始化不 import Docling"
- §5.1: "CLI help 与 tool schema 只读该静态对象"
- §5.2: "`FinsUploadFormatCapability`：持有 `DoclingConverterCapability`…primary 集合始终从 converter capability 投影"
- Slice 1: capability owner 独立 slice，help 静态投影不触发 Docling import

**评估**: owner 链路清晰——`DOCLING_CONVERTER_CAPABILITY`（模块级静态声明）→ `FinsUploadFormatCapability`（投影）→ CLI help / tool schema（只读）。Fins 不复制 converter allow-list，只投影。

**residual note**: plan 未显式写"suffix tuple 为模块级字面量 hardcode"。鉴于"模块初始化不 import Docling"的约束，实现 agent 只能选 hardcode。设计路径已收敛，但显式写明可消除最后歧义。不构成 finding。

### 2.3 Material tool/service 前置准入

**plan 规定**:

- §5.3: "material 不经 filing request validator，但不得因此绕过 admission：CLI `_validated_upload_files` 与 tool/Service workflow 都必须在任何 converter call 前调用 `FinsUploadMaterialFiles` 的同一 owner 构造入口"
- §5.3: "tool/Service 路径要在 SEC material company staging 或 CN/HK 等价业务 mutation 前完成该构造；非法 suffix 以 typed/bounded usage 语义失败，不进入 converter，不发布 company/source state"
- §5.4: Service 入口校验 selection 与 `SourceKind` 一致
- §6.2: "tool runtime 仍构造 raw request；filing 进入同一 Fins validator，material 进入同一 Fins material selection owner，均不建立旁路"
- Slice 3 Tests: "CLI 与'LLM upload tool raw request -> `ProductionFinsUploadRunner` -> material workflow -> Service'路径上的非法 suffix 必须在 company/source mutation、文件读取和 converter call 前以 typed/bounded usage 语义失败，且 converter call 为 0"

**评估**: material admission 覆盖 CLI 和 tool/Service 两条路径，准入时机（mutation 前）、失败语义（typed/bounded usage）和测试断言（mutation/read/converter 均为 0）均已明确。这是 D1 的核心修复——原 review 发现 tool 路径无 admission owner，现已收敛。

**风险**: 无。

### 2.4 Batch 边界

**plan 规定**:

- §6.2: "`upload_filings_from` 继续按单文件生成独立 upload 命令，每个候选只消费 owner 的 `accepts_primary`。`.xsd` companion-only 文件必须稳定地以 `unsupported_suffix` skip"
- §6.2: "自动归组明确 deferred 到后续 batch association / UF-FIX07 类 work unit"
- §3.2 非目标: "不为 `upload_filings_from` 设计同目录 HTML/XBRL 与 `.xsd` 的自动关联/归组规则"
- Slice 2 Tests: batch 扫描含 HTML/XBRL + XSD 目录的 skip 行为
- Slice 2 Stop condition: 自动关联需停止并记入 UF-FIX07

**评估**: batch 边界明确——`.xsd` 在 batch 模式下稳定 skip，不自动归组，direct upload 是本轮 companion 入口。非目标和 stop condition 双重约束防止 implementation agent 越界。

**风险**: 无。

### 2.5 事件语义

**plan 规定**:

- §5.4: "filing companion 不产生 `conversion_started` 或任何伪转换事件；它只沿现有 original publication 路径产生正常 `file_uploaded` 事件，事件的 source 保持 `original`，不新增 event type"
- §7 #12: "filing companions 无 `conversion_started`，只有 original `file_uploaded`；不伪造转换事实"
- Slice 3 Tests: HTML+XSD 和 DOCX+XLSX+DOCX 两个 fixture 均断言 companion 事件序列

**评估**: 事件契约明确——companion 只产生 source=`original` 的 `file_uploaded`，禁止 `conversion_started` 和新 event type。两个 fixture 覆盖不同场景。满足 LLM-facing 文本约束（"不得把未发生的动作伪装成事实"）。

**风险**: 无。

### 2.6 测试闭合

**plan 规定的测试矩阵**:

| 场景 | 断言要点 | 覆盖 finding |
|---|---|---|
| HTML primary + XSD companion | converter 只收到 HTML；两个 originals 均存储；唯一 Docling 派生资产；primary_document 指向首文件；requested/stored=2；XSD 无 conversion_started | D4, D5, O1 |
| DOCX + XLSX + DOCX | converter 只收到首项 DOCX；XLSX 与第二 DOCX 原样存储；唯一派生资产；primary_document 指向首项；requested/stored=3；companions 无 conversion_started | O2, D5 |
| corrupt primary + valid companion | typed content failure、converter 只调用一次、零 storage publication | 不变式 |
| companion 读取/空内容失败 | batch commit 前零发布 | 不变式 |
| material 两文件 | 转换两次、保持既有 primary/result 行为 | D1 |
| material 非法 suffix（CLI + tool） | mutation/read/converter 均为 0，typed/bounded usage 失败 | D1 |
| source_kind 不匹配 selection | ValueError + 零文件读取/converter/batch | D2 |
| delete empty selection 类型一致性 | 与既有无文件 delete 行为回归 | D2 |
| batch 扫描含 XSD 目录 | `.xsd` stable unsupported_suffix skip | D4 |
| legacy DOC/PPT/XLS/ZIP 作为 primary | role-specific usage error 拒绝 | — |
| `.xsd` 作为首文件失败 | 角色校验拒绝 | — |
| --help / schema / README 三面一致 | 首文件 primary、companions 不转换、`.xml` XBRL candidate | M2, O1 |

**验证计划**:

- §9 覆盖: focused tests、static owner audit（`rg` 检查 `FINS_UPLOAD_FILE_SUFFIXES`/`SUPPORTED_UPLOAD_SUFFIXES`/`_pick_primary_docling_file` 均无结果）、coverage ≥80%、pyright、readonly change audit
- Slice 4 Stop condition: "任一旧 allow-list、consumer-side suffix set、per-file filing conversion 或生成名 primary 推断仍存在，即本 work unit 不得判定完成"

**评估**: 测试矩阵覆盖全部 9 个 findings 的验证需求，验证计划包含 static owner audit 和 coverage 门控。闭合。

## 3. Findings

无 material finding。修订 plan 对全部 9 个 Controller accepted findings 的修复均基于直接 plan 文本证据，设计决策已明确冻结，implementation agent 无需自行裁决。

## 4. Open Questions

无。plan §10 "没有未分类风险，没有需要实现 agent 自行猜测的 open question"——经本轮逐项验证，该声明成立。

## 5. Residual Risks

| # | 风险 | 分类 | Owner / destination |
|---|---|---|---|
| R1 | suffix tuple 为模块级字面量 hardcode（plan 未显式写明，但设计约束已收敛） | 实现歧义极低 | implementation agent 自行确认；建议 plan 补充一句 |
| R2 | Docling 版本升级可能导致 `FormatToExtensions` 变化 | capability residual | plan §10 已覆盖：subset fail-fast + 测试固化 |
| R3 | 非 PDF 格式实际转换成功率未经 UF-PF06 证明 | content residual | UF-PF06 |
| R4 | `.xsd` 以外的 companion-only XBRL 附件类型未知 | companion residual | 后续产品需求 |
| R5 | batch companion 自动归组 | assigned to later work unit | UF-FIX07 |
| R6 | 显式 primary、重复路径、basename/derived-name collision | UF-FIX07 | UF-FIX07 |
| R7 | 137 条 full-real mandatory matrix 未重跑 | PF residual | UF-PF12 |

## 6. Conclusion

**pass**

修订 plan 对 Controller 裁决的 9 个 findings（M1/M2/D1–D5/O1/O2）全部实现真正修复：

1. **M1**（help 懒加载）: 两阶段设计明确冻结——模块级静态声明不 import Docling，构造期 lazy 子集校验。stop condition 不再要求 implementation agent 自行设计。
2. **M2**（XML 歧义）: 三面文案一致要求 `.xml` XBRL candidate 限定，Slice 4 有逐面对照断言。
3. **D1**（material admission owner）: `FinsUploadMaterialFiles` 同一构造入口覆盖 CLI 和 tool/Service 两条路径，准入时机和失败语义明确，测试断言 mutation/read/converter 均为 0。
4. **D2**（`prepare_upload` 签名）: 单一 closed union 参数 `FinsUploadFilingFiles | FinsUploadMaterialFiles`，`SourceKind` 一致性校验，非法组合 `ValueError` 拒绝。
5. **D3**（suffix 校验策略）: 从双向精确相等改为单向子集校验（产品 suffix ∈ 第三方映射），缺失 fail-fast，新增不扩面。
6. **D4**（batch companion）: `.xsd` 稳定 skip，自动归组 deferred，direct upload 是本轮入口，测试固化。
7. **D5**（companion 事件）: companion 只产生 source=`original` 的 `file_uploaded`，禁止 `conversion_started`，两个 fixture 断言。
8. **O1**（三面文案一致）: Slice 4 要求 CLI help、tool schema、README 逐面对照。
9. **O2**（多 converter-capable fixture）: DOCX+XLSX+DOCX 测试明确覆盖。

Adversarial 检查的 6 个维度（typed delete empty state、静态产品 suffix owner、material tool/service 前置准入、batch 边界、事件语义、测试闭合）均通过。

无 material finding，无 open question。residual risks 均已明确 owner 和 destination。

plan 可进入 implementation。
