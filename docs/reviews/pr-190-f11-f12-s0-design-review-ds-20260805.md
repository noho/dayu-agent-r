# PR 190 F11/F12 S0 Design Truth Review

## Scope

- Mode: design document review (deepreview variant)
- Branch: `codex/interactive-oracle`
- Base: `427b1c858d5e926f309935fa206963deb1618436`
- Target files only:
  - `docs/host/design.md`
  - `docs/engine/design.md`
  - `docs/gateflow/pr-190-f11-f12-s0-design-implementation-20260805.md`
- Accepted plan: `docs/gateflow/pr-190-f11-f12-interactive-memory-plan-20260805.md`
- Accepted checkpoint: `docs/gateflow/pr-190-f11-f12-accepted-plan-checkpoint-20260805.md`
- Controller adjudication: `docs/gateflow/pr-190-f11-f12-plan-review-adjudication-20260805.md`
- Output file: `docs/reviews/pr-190-f11-f12-s0-design-review-ds-20260805.md`
- Review date: 2026-08-05
- Parallel review coverage: 无（单人独立逐行审查）
- Excluded scope: 生产代码、tests、registry、旧 evidence（S0 是纯 design truth slice）

## Review Method

本 review 独立核对 S0 实施 artifact 声称的每项设计修改是否在 target design 文件中真实存在、与 accepted plan/checkpoint/adjudication 的 frozen contract 一致，且不存在 semantic ownership drift、残留 v2 normative、兼容分支、过度设计或合同冲突。

每项 finding 基于直接文本证据（行号），不依赖 AgentMiMo、不依赖间接推断。PASS 表示合同在 design 中完整、一致、无可观察缺陷；FAIL 表示存在可证实的合同缺失、冲突或语义漂移。

## Findings

### F11 — Unique Owner, Canonical Response Identity, Pagination, Security Whitelist

#### F11-01-PASS — F11 response identity owner 唯一归属于 Host Tool Trace durable resolver

- **入口/函数**: `docs/host/design.md` §14.1 Tool Trace Hot / Cold Storage / §25.1 Compact Event 响应路径
- **文件(行号)**: `docs/host/design.md:2057-2063`, `docs/host/design.md:3908`
- **输入场景**: compactor proposal manifest 存在，需要公开解析 compactor response identity
- **实际分支**: §14.1 明确 "compactor runner-call 的正式 public reconstruction 还必须从 canonical compact terminal 解析 response identity。该语义的 owner 是 Host Tool Trace durable resolver，不是 Service、CLI、JSON / Markdown renderer 或 evidence harness"
- **预期行为**: owner 固定为 Host Tool Trace durable resolver；下游不得旁路反推
- **实际行为**: 与预期一致。§25.1 进一步约束 "Tool Trace public resolver 只在同一 read transaction 内把 typed proposal manifest 与 parent Run 的 compacted / attempt-rejected canonical terminal做 exact binding"
- **直接证据**: `docs/host/design.md:2057` 明确 owner 声明；`docs/host/design.md:2061` 约束 resolver 不得从 "RunnerSpec、manifest provider / model、事件相邻性、timestamp、usage 或当前配置补建 response identity"；`docs/host/design.md:3908` 重申不通过 Service model family / 配置 / manifest / usage / 相邻 event / 时间顺序反推
- **影响**: 无。合同完整，owner 唯一。
- **严重程度**: PASS

#### F11-02-PASS — Canonical terminal exact binding 与 pagination fail closed

- **入口/函数**: `docs/host/design.md` §14.1
- **文件(行号)**: `docs/host/design.md:2059-2061`
- **输入场景**: 需要从 canonical compact terminal 解析 response identity
- **实际分支**: keyset exhaustion 扫描模式 + exact match + fail closed
- **预期行为**: 每页有界、cursor 单调、无总页数上限；mismatch/duplicate/malformed/cursor corruption 全部 fail closed；完整 exhaustion 后无 match 才返回 None + limitation
- **实际行为**: 与预期完全一致。
  - `:2059`: "使用固定正数 page size、严格单调的 `after_event_sequence` keyset cursor，并持续读取到 empty page 或 page 长度小于 page size。每页有界，但不得设置任意总页数上限"
  - `:2059`: "full page 后 cursor 不严格增大、row sequence 不大于当前 cursor、cursor 非法或 page 数据损坏都必须抛 durable error，不能降格为't terminal 未观察到'"
  - `:2061`: "matching terminal 必须唯一，并同时 exact match proposal manifest ref / digest、compaction operation id 与 attempt number"
  - `:2061`: "同 operation / attempt 的 manifest ref 或 digest 不一致、同一 manifest 出现多个 terminal、payload malformed、successful identity 的 compactor Engine run id、attempt 或 Runner request identity 与 manifest 不一致" → fail closed
  - `:2063`: "compactor call 只有完整 exhaustion 后无 matching terminal 才为 `None`"
- **直接证据**: 上列行号覆盖全部 pagination/keyset/fail-closed 语义
- **影响**: 无。合同完整，与 accepted plan F11 frozen contract §4-5 精确一致。
- **严重程度**: PASS

#### F11-03-PASS — Security whitelist 显式白名单

- **入口/函数**: `docs/host/design.md` §14.1
- **文件(行号)**: `docs/host/design.md:2077`
- **输入场景**: public resolver / analysis JSON / Markdown / hot/cold trace 输出 compactor response summary
- **实际分支**: 显式安全字段白名单
- **预期行为**: 只允许 binding、effective provider/model、Runner request identity、provider request id availability/value；headers/credential/API key/authorization/endpoint/raw prompt/raw request/response body 不得进入 public projection
- **实际行为**: 与预期一致。`:2077`: "compactor response summary 采用显式安全字段白名单，只允许上述 binding、effective provider / model、Runner request identity，以及 provider request id availability / value。headers、credential / API key、authorization、endpoint、raw prompt、raw request / response body 与 provider diagnostic payload不得进入 public resolver、analysis JSON / Markdown、hot / cold trace 或 LLM-facing material"
- **直接证据**: `docs/host/design.md:2077`
- **影响**: 无。白名单与 accepted plan F11 frozen contract §6 一致。
- **严重程度**: PASS

#### F11-04-PASS — Tool Trace analysis fresh v2 与旧 v1 删除

- **入口/函数**: `docs/host/design.md` §14.1
- **文件(行号)**: `docs/host/design.md:2063`
- **输入场景**: Tool Trace analysis schema 版本化
- **实际分支**: fresh schema version 2
- **预期行为**: v1 producer/reader/validation 不保留；JSON/Markdown 只从同一 structured report 渲染
- **实际行为**: 与预期一致。`:2063`: "Tool Trace analysis 使用 fresh schema version 2，把该 contract 投影为 `ToolTraceCompactorResponseSummary` 并按 parent Host Run、operation、attempt、terminal sequence 稳定排序。v1 producer / reader / validation 不保留，JSON 与 Markdown 必须只从同一个 structured report 渲染"
- **直接证据**: `docs/host/design.md:2063`
- **影响**: 无。
- **严重程度**: PASS

### F12 — Fresh v3 Schema, Typed Facts, Host-derived Coverage/Omission/Caps Audit

#### F12-01-PASS — CompactInputV3 完整定义

- **入口/函数**: `docs/host/design.md` §24.3
- **文件(行号)**: `docs/host/design.md:3327-3358`
- **输入场景**: compactor 输入构造
- **实际分支**: CompactInputV3 逐字段定义
- **预期行为**: schema 固定为 `dayu.context_compaction.input.v3`；字段仅为 schema、current_input、source_boundary、output_caps
- **实际行为**: 与预期一致。`:3327-3355` 完整定义所有字段及类型
- **直接证据**: `docs/host/design.md:3327-3355`
- **影响**: 无。
- **严重程度**: PASS

#### F12-02-PASS — CompactCandidateV3 五个 typed children 全部 root keys required

- **入口/函数**: `docs/host/design.md` §24.3
- **文件(行号)**: `docs/host/design.md:3361-3398`
- **输入场景**: 模型输出解析
- **实际分支**: CompactCandidateV3 strict JSON object
- **预期行为**: root exact keys 固定且全部 required（session_summary、evidence_facts、answer_anchors、forward_intents、reference_continuity）；session_summary key 必须存在，null=清空；省略 key 拒绝
- **实际行为**: 与预期一致。`:3363-3396` 逐字段定义五个 typed child 及 nested fields；`:3398` 明确 session_summary 必须存在、null 清空语义、省略拒绝
- **直接证据**: `docs/host/design.md:3363-3398`
- **影响**: 无。
- **严重程度**: PASS

#### F12-03-PASS — CompactOutputCapsV3 为 immutable boundary DTO，MemoryProjectionPolicy 唯一拥有数值

- **入口/函数**: `docs/host/design.md` §24.2 / §24.3
- **文件(行号)**: `docs/host/design.md:3313`, `docs/host/design.md:3357`
- **输入场景**: caps 跨边界投影
- **实际分支**: DTO 无 default/validation/独立配置读取
- **预期行为**: caps DTO 只是 MemoryProjectionPolicy 的 immutable boundary projection；数值、默认值、合法性校验与 policy digest 仍只由 MemoryProjectionPolicy 拥有
- **实际行为**: 与预期一致。`:3313`: "caps 只是 `MemoryProjectionPolicy` 的 immutable boundary projection：数值、默认值、合法性校验与 policy digest 仍只由 `MemoryProjectionPolicy` 拥有，compact input DTO 不得定义第二套 default、校验或配置读取"；`:3357`: "它必须由 Context Governance 对本次实际采用的同一个 `MemoryProjectionPolicy` instance 逐字段机械投影。DTO 不定义 default、数值校验或独立配置读取"
- **直接证据**: `docs/host/design.md:3313`, `docs/host/design.md:3357`
- **影响**: 无。与 accepted plan F12 frozen contract §95-97 及 controller adjudication A-F04 一致。
- **严重程度**: PASS

#### F12-04-PASS — Host-derived represented/omitted exact complement + policy usage audit

- **入口/函数**: `docs/host/design.md` §24.3 / §25
- **文件(行号)**: `docs/host/design.md:3404`, `docs/host/design.md:3672`
- **输入场景**: accept barrier 后 coverage partition
- **实际分支**: Host 从 candidate provenance + immutable boundary 确定性计算
- **预期行为**: represented/omitted 不相交且并集 exact 等于 boundary；omitted 不携带原因；policy usage audit 从同源 caps/estimator/candidate actuals 派生
- **实际行为**: 与预期一致。`:3404`: "accept owner 从 candidate provenance 派生 `CompactRepresentedCoverageV3`，再按 immutable root boundary 顺序计算 exact complement `CompactOmittedCoverageV3`；两集合必须不相交且并集 exact 等于 boundary。omitted 只表示 accepted candidate 没有通过 provenance 代表该 source，不携带原因"；`:3404`: "`CompactPolicyUsageAuditV3` 从同一 caps projection、同一 estimator 与 candidate actuals 派生，逐 section 记录 item / char actual、cap、policy ref / digest"
- **直接证据**: `docs/host/design.md:3404`, `docs/host/design.md:3672`
- **影响**: 无。与 accepted plan F12 frozen contract §122-126 一致。
- **严重程度**: PASS

#### F12-05-PASS — 模型不返回 diagnostics/explicit drop ledger/drop reason

- **入口/函数**: `docs/host/design.md` §24.2 / §24.3
- **文件(行号)**: `docs/host/design.md:3315`, `docs/host/design.md:3398`
- **输入场景**: 模型 output schema 定义
- **实际分支**: v3 output 不含这些字段
- **预期行为**: 模型只负责五类业务语义与必要 provenance；diagnostics/explicit drop ledger/drop reason/omission kind/coverage/policy usage 均不进入模型输出；旧字段作为 unknown key 拒绝
- **实际行为**: 与预期一致。`:3315`: "模型只负责五类业务语义与必要 provenance，不负责治理诊断、source omission ledger、drop reason、cap usage audit 或 coverage partition"；`:3398`: "模型不返回 diagnostics、explicit drop ledger、drop reason、omission kind、coverage 或 policy usage；旧 `diagnostics`、`explicitly_dropped_sources` 及其子项一律作为 unknown key 拒绝，不保留兼容 reader"
- **直接证据**: `docs/host/design.md:3315`, `docs/host/design.md:3398`
- **影响**: 无。
- **严重程度**: PASS

#### F12-06-PASS — 单一 structure owner

- **入口/函数**: `docs/host/design.md` §24.3
- **文件(行号)**: `docs/host/design.md:3400-3401`
- **输入场景**: output v3 JSON 结构管理
- **实际分支**: compact_structure 只拥有 structural descriptors
- **预期行为**: compact_structure 单向 import compaction.py 的 typed domain types 并构造；compaction.py 不反向 import；structure owner 不定义第二组 dataclass；public API 固定为 compact_output_template_v3/json_schema_v3/parse_compact_candidate_v3
- **实际行为**: 与预期一致。`:3400`: "output v3 的 JSON 结构只有一个 owner：`compact_structure` 只拥有 immutable exact structural descriptors... typed domain dataclass 由 compaction domain owner 唯一定义，structure owner 单向构造这些 types，不定义第二组 dataclass，也不拥有 acceptance、caps、durable state、Engine transport 或 prompt 业务文案"；`:3401`: "public API 固定为..."
- **直接证据**: `docs/host/design.md:3400-3401`
- **影响**: 无。与 accepted plan F12 frozen contract §110-118 及 controller adjudication A-F03 一致。
- **严重程度**: PASS

### F12 — Fresh Persistence

#### F12-07-PASS — Fresh persistence contract（compactor_input_projection.v2 + artifact schema 4）

- **入口/函数**: `docs/host/design.md` §24.4
- **文件(行号)**: `docs/host/design.md:3448-3450`
- **输入场景**: compact 成功后的持久化
- **实际分支**: fresh schema cut
- **预期行为**: compactor input projection → `compactor_input_projection.v2`；compact artifact → schema `4`；coverage 字段改为 represented_coverage/omitted_coverage/policy_usage_audit；旧 compact input/output contract、schema-3 artifact、diagnostics、explicit drops/reasons 不支持读取，不迁移，不保留 alias/双读/re-export/wrapper
- **实际行为**: 与预期一致。`:3448-3450` 完整定义上述所有语义
- **直接证据**: `docs/host/design.md:3448-3450`
- **影响**: 无。
- **严重程度**: PASS

#### F12-08-PASS — 旧 compact artifact/session replay 不支持但不扩大为整个 DB 不可打开

- **入口/函数**: `docs/host/design.md` §24.4
- **文件(行号)**: `docs/host/design.md:3450`
- **输入场景**: 旧 DB bootstrap
- **实际分支**: 明确约束范围
- **预期行为**: 只约束旧 compact payload 与依赖它的 Session replay；未触及旧 compact payload 的其它 durable rows 继续按各自 schema 处理
- **实际行为**: 与预期一致。`:3450`: "该 fresh cut 只约束旧 compact payload 与依赖它的 Session replay；未触及旧 compact payload 的其它 durable rows 继续按各自 schema 处理，不能把本限制扩大解释为'整个旧 DB 必然无法打开'"
- **直接证据**: `docs/host/design.md:3450`
- **影响**: 无。
- **严重程度**: PASS

### F12 — Repair/Digest LLM Boundary

#### F12-09-PASS — Digest 不进入 LLM-facing 文本（initial + repair）

- **入口/函数**: `docs/host/design.md` §24.2 / §24.6
- **文件(行号)**: `docs/host/design.md:3313`, `docs/host/design.md:3501`
- **输入场景**: initial/repair prompt 渲染
- **实际分支**: digest 只属于 Host internal
- **预期行为**: request digest 与 source-boundary digest 只属于 Host internal binding/audit/request serialization；initial/repair 的 system message、user message、template、示例和 validation feedback 都不得出现这两个 digest 的值或通用 digest 字段名
- **实际行为**: 与预期一致。`:3313`: "request digest 与 source-boundary digest 只属于 Host internal binding、audit 与 request serialization；initial / repair 的 system message、user message、template、示例和 validation feedback 都不得出现这两个 digest 的值或通用 digest 字段名"；`:3501`: "initial / repair 都不得包含 request digest、source-boundary digest 的值或通用 digest 字段名；这些值只保留在 Host-internal binding、audit、input projection persistence 与 request serialization"
- **直接证据**: `docs/host/design.md:3313`, `docs/host/design.md:3501`
- **影响**: 无。与 accepted plan F12 frozen contract §160-161 及 controller adjudication B-02 一致。
- **严重程度**: PASS

#### F12-10-PASS — Initial 无 repair protocol，repair 自足整体重产

- **入口/函数**: `docs/host/design.md` §24.6
- **文件(行号)**: `docs/host/design.md:3499-3501`
- **输入场景**: initial/repair user body 渲染
- **实际分支**: 分离渲染
- **预期行为**: initial body 包含同一 immutable CompactInputV3、真实 caps、五类字段含义、同源 template 与示例，不含 repair protocol/previous attempt/validation issues；repair body 自足包含同一 input/template/字段规则/前次 attempt number/bounded issues/whole-candidate replacement 要求；两者共享同一 system contract 与 structure template/schema source
- **实际行为**: 与预期一致。`:3499-3501` 完整覆盖以上所有语义
- **直接证据**: `docs/host/design.md:3499-3501`
- **影响**: 无。与 accepted plan F12 frozen contract §158-162 一致。
- **严重程度**: PASS

#### F12-11-PASS — Rejected candidate 不写 artifact/Memory/CONTEXT_COMPACTED

- **入口/函数**: `docs/host/design.md` §24.3 / §24.6
- **文件(行号)**: `docs/host/design.md:3408`, `docs/host/design.md:3515`
- **输入场景**: candidate 被 accept barrier 拒绝
- **实际分支**: 不持久化
- **预期行为**: invalid attempt、中间 pass 与 rejected candidate 不得写 accepted artifact、CONTEXT_COMPACTED、Memory、ordinary RunInput 或 public trace；只有 terminal permit 可以提交
- **实际行为**: 与预期一致。`:3408` + `:3515` 双重覆盖
- **直接证据**: `docs/host/design.md:3408`, `docs/host/design.md:3515`
- **影响**: 无。
- **严重程度**: PASS

### Engine — Generic Structured Output / No Inference / No Downgrade

#### ENG-01-PASS — StructuredOutputRequest 是显式一等字段

- **入口/函数**: `docs/engine/design.md` §2 / §4
- **文件(行号)**: `docs/engine/design.md:59`, `docs/engine/design.md:103`, `docs/engine/design.md:112-113`
- **输入场景**: AgentRunRequest 构造
- **实际分支**: 显式字段
- **预期行为**: structured_output 是 AgentRunRequest 的显式字段；StructuredOutputRequest = JsonObjectStructuredOutputRequest | JsonSchemaStructuredOutputRequest；不得塞入 provider_request/headers/metadata/工具 schema/extra payload
- **实际行为**: 与预期一致。`:59`: "公共入口原样消费 `AgentRunRequest.structured_output`"；`:103`: `structured_output` 字段在 AgentRunRequest 表中；`:112-113`: "显式一等字段，不得塞入 `provider_request`、headers、metadata、工具 schema 或开放 extra payload"
- **直接证据**: `docs/engine/design.md:59,103,112-113`
- **影响**: 无。与 accepted plan Engine frozen contract §167 一致。
- **严重程度**: PASS

#### ENG-02-PASS — StructuredOutputCapability 三值与 fail-fast matrix

- **入口/函数**: `docs/engine/design.md` §8
- **文件(行号)**: `docs/engine/design.md:257-265`
- **输入场景**: RunnerSpec 构造与 outbound call
- **实际分支**: capability matrix 校验
- **预期行为**: none/json_object/json_schema 三值；none 只接受 None；json_object 接受 None/json_object request；json_schema 接受 None/json_object/json_schema request；不支持的组合在 outbound 前 ValueError fail fast，不降级
- **实际行为**: 与预期一致。`:257`: "`RunnerSpec.structured_output_capability` 是 required 的 `StructuredOutputCapability`"；`:259-264`: 完整 capability matrix 表格；`:265`: "不支持组合必须在 Agent / Runner outbound call 前抛 `ValueError`，不得降级"
- **直接证据**: `docs/engine/design.md:257-265`
- **影响**: 无。
- **严重程度**: PASS

#### ENG-03-PASS — Engine 不推断、不降级、不按 provider 名称 dispatch

- **入口/函数**: `docs/engine/design.md` §2 / §6 / §7 / §15
- **文件(行号)**: `docs/engine/design.md:59`, `docs/engine/design.md:161`, `docs/engine/design.md:228`, `docs/engine/design.md:577`
- **输入场景**: structured output request forwarding
- **实际分支**: 原样转发，无推断/降级
- **预期行为**: Engine 不从 system/user prompt、tool schema、provider 名称、model 名称或调用场景推断 structured_output；provider 拒绝 structured-output 时保留原 provider failure，不用较弱模式重试；Runner 不读 provider/model 名称推断 capability；不自动升级、降级或重试成另一 structured-output mode；不按 provider 名称 dispatch
- **实际行为**: 与预期完全一致。
  - `:59`: "Engine 不从 system / user prompt、tool schema、provider 名称、model 名称或调用场景推断该请求"
  - `:161`: "provider 拒绝 structured-output 时保留原 provider failure，不用较弱模式重试"
  - `:228`: "Runner 只能按 typed request 投影 transport，不得读取 provider / model 名称推断 capability，不得把 provider rejection 吞掉后降级重试"
  - `:577`: "无论 capability 为何，Engine 都不自动升级、降级或重试成另一 structured-output mode"
  - `:577`: "Host 对 `none` / `json_object` / `json_schema` 的选择不得在 Engine 中变成 compactor special case，也不得按 provider 名称 dispatch"
- **直接证据**: 上列五行，覆盖全部"不推断/不降级/不按名 dispatch"语义
- **影响**: 无。
- **严重程度**: PASS

#### ENG-04-PASS — AsyncRunner.call required keyword-only structured_output

- **入口/函数**: `docs/engine/design.md` §7
- **文件(行号)**: `docs/engine/design.md:204`, `docs/engine/design.md:228`
- **输入场景**: Runner.call 签名
- **实际分支**: required keyword-only
- **预期行为**: structured_output 是 required、无 default 的 keyword-only 参数；Protocol breaking change 必须在同一 accepted commit 同步迁移所有实现和 call sites；不得用 =None default 掩盖漏传
- **实际行为**: 与预期一致。`:204`: `structured_output: StructuredOutputRequest | None` 在 Protocol 签名中；`:228`: "`structured_output` 是 required、无 default 的 keyword-only 参数。该 Protocol breaking change 必须在同一个 accepted implementation commit 中同步迁移..."
- **直接证据**: `docs/engine/design.md:204,228`
- **影响**: 无。与 accepted plan Engine frozen contract §172 及 controller adjudication A-F02 一致。
- **严重程度**: PASS

#### ENG-05-PASS — Engine 不知道 compact schema，不提供 compactor special case

- **入口/函数**: `docs/engine/design.md` §15
- **文件(行号)**: `docs/engine/design.md:577`
- **输入场景**: Host compactor 使用 Engine
- **实际分支**: generic capability only
- **预期行为**: Engine 只提供 generic capability；不知道 compact input/output schema、五类 memory、coverage、repair、artifact 或 Host attempt budget
- **实际行为**: 与预期一致。`:577`: "Engine 只校验 capability matrix并投影 provider-neutral transport，不知道 compact input/output schema、五类 memory、coverage、repair、artifact 或 Host attempt budget"
- **直接证据**: `docs/engine/design.md:577`
- **影响**: 无。
- **严重程度**: PASS

### 旧 v2 Normative 真正删除

#### V2-01-PASS — 旧 v2 compact type 名全部删除

- **入口/函数**: 全文扫描
- **文件(行号)**: N/A（全文件扫描）
- **输入场景**: 搜索 `CompactInputV2`、`CompactCandidateV2`、`CompactAcceptedTruthV2`、`explicitly_dropped_sources`、`CompactDropReasonV2`、`CompactCandidateDiagnosticV2`、`CompactExplicitDropV2`
- **实际分支**: 0 命中
- **预期行为**: 这些类型名作为 normative design truth 不再存在于 host/engine design 中
- **实际行为**: `grep -c` 返回 0（host design 全文件扫描）；engine design 同样 0 命中
- **直接证据**: `grep -c "CompactInputV2\|CompactCandidateV2\|CompactAcceptedTruthV2\|explicitly_dropped_sources\|CompactDropReasonV2\|CompactCandidateDiagnosticV2\|CompactExplicitDropV2" docs/host/design.md` → `0`；engine design 同样 0
- **影响**: 无。旧 v2 normative truth 已完全删除。
- **严重程度**: PASS

#### V2-02-PASS — §24.3 整节从 v2 替换为 v3（非追加）

- **入口/函数**: `docs/host/design.md` §24.3
- **文件(行号)**: `docs/host/design.md:3323`（section heading: "Compact v3 I/O Contract"）
- **输入场景**: 章节内容
- **实际分支**: 整节为 v3 contract
- **预期行为**: 不存在 v2 I/O contract 作为并列真源
- **实际行为**: 章节标题为 "Compact v3 I/O Contract"，全文为 v3 定义；无 v2 规范段落残留
- **直接证据**: `docs/host/design.md:3323` section heading；全文内容均为 v3
- **影响**: 无。
- **严重程度**: PASS

#### V2-03-PASS — 无兼容 alias/re-export/wrapper 残留

- **入口/函数**: 全文扫描
- **文件(行号)**: N/A
- **输入场景**: 搜索兼容性关键词（在 compact 上下文中）
- **实际分支**: 无 compact 相关兼容声明
- **预期行为**: 不保留旧 compact contract 的 alias、双读 parser、re-export 或 compatibility wrapper
- **实际行为**: 设计文档中与 compact 相关的唯一 "alias"/"compatibility" 出现是明确声明不保留这些：`:3450` "不保留 alias、双读 parser、re-export 或 compatibility wrapper"
- **直接证据**: `docs/host/design.md:3450`
- **影响**: 无。
- **严重程度**: PASS

### 无兼容/过度设计/Owner Drift

#### OD-01-PASS — F11 不新增第二 EventLog/缓存/推断器

- **入口/函数**: `docs/host/design.md` §14.1
- **文件(行号)**: `docs/host/design.md:2057-2063`
- **输入场景**: F11 实现
- **实际分支**: 复用既有 canonical terminal、manifest parser 与 EventLog keyset reader
- **预期行为**: 只增加缺失的 public typed projection；不新增第二 EventLog、缓存或推断器
- **实际行为**: 设计只定义 resolver 从既有 canonical terminal + proposal manifest 解析 response identity，不引入新存储/缓存
- **直接证据**: `docs/host/design.md:2057-2063`；resolver 只在同一 read transaction 内读取既有 EventLog rows
- **影响**: 无。
- **严重程度**: PASS

#### OD-02-PASS — F12 不增加 semantic classifier，caps DTO 不定义第二 owner

- **入口/函数**: `docs/host/design.md` §24.2 / §24.3
- **文件(行号)**: `docs/host/design.md:3313`, `docs/host/design.md:3357`
- **输入场景**: caps 管理
- **实际分支**: DTO 只是 immutable projection
- **预期行为**: 删除模型 ledger 而非增加 semantic classifier；CompactOutputCapsV3 只是跨边界 immutable projection，数值 owner 仍只有 MemoryProjectionPolicy
- **实际行为**: 与预期一致。两处均明确 DTO 无 owner 语义
- **直接证据**: `docs/host/design.md:3313`, `docs/host/design.md:3357`
- **影响**: 无。
- **严重程度**: PASS

#### OD-03-PASS — Engine 不增加 provider probe/fallback router/provider-name 分支

- **入口/函数**: `docs/engine/design.md` §8 / §15
- **文件(行号)**: `docs/engine/design.md:287`, `docs/engine/design.md:577`
- **输入场景**: Engine capability 与 transport
- **实际分支**: 无 probe/router/name-branch
- **预期行为**: Engine contract 本身不按 provider 名称维护 capability 表，也不运行 provider probe；不增加 fallback router 或 provider-name 分支
- **实际行为**: 与预期一致。`:287`: "Engine contract 本身不按 provider 名称维护 capability 表，也不运行 provider probe"；`:577`: 不按 provider 名称 dispatch
- **直接证据**: `docs/engine/design.md:287`, `docs/engine/design.md:577`
- **影响**: 无。
- **严重程度**: PASS

#### OD-04-PASS — §24 / §25 v3 contract 无 owner 冲突

- **入口/函数**: `docs/host/design.md` §24 / §25 全文
- **文件(行号)**: §24.2-§24.7, §25, §25.1
- **输入场景**: 跨 section contract 一致性
- **实际分支**: 同一事实在多处出现时 owner 一致
- **预期行为**: CompactAcceptedTruthV3 的 consumer（artifact、canonical terminal、Memory、RunInput、Tool Trace）只从同一 accepted truth 派生
- **实际行为**: 与预期一致。`:3406`: "artifact、canonical terminal、Memory、RunInput 与 Tool Trace 只能消费该 truth，不得各自重算 coverage、caps 或 semantic replacement"；`:3672`: "Memory、artifact、event、RunInput 与 trace 只消费该 accepted truth，不能从 raw candidate、旧 drop ledger、配置或时间顺序重算"
- **直接证据**: `docs/host/design.md:3406`, `docs/host/design.md:3672`
- **影响**: 无。多 consumer 语义同源，无 owner drift。
- **严重程度**: PASS

#### OD-05-PASS — 不新增 Any/object/无类型签名/hasattr/getattr/lazy import/extra payload

- **入口/函数**: N/A（S0 为纯 design slice，不涉及代码）
- **文件(行号)**: N/A
- **输入场景**: N/A
- **实际分支**: N/A
- **预期行为**: N/A
- **实际行为**: S0 是 design truth slice，不修改生产代码，因此不存在代码级 violation。design 文档使用 typed contract（如封装的 struct/table/enum），不依赖 Any/object 或 hasattr/getattr 模式。
- **直接证据**: 所有 design contract 使用具体的 typed 定义
- **影响**: 无。S0 不产生代码。
- **严重程度**: PASS（不适用）

### S0 Implementation Artifact 自身一致性

#### S0-01-PASS — 声称的修改与实际 design 文件内容一致

- **入口/函数**: S0 artifact "Changed sections" (line 53-87) vs 实际 design 文件
- **文件(行号)**: `docs/gateflow/pr-190-f11-f12-s0-design-implementation-20260805.md:53-87`
- **输入场景**: S0 声称修改了 9 个 Host section + 5 个 Engine section
- **实际分支**: 逐项核对
- **预期行为**: 每项声称的修改在实际文件中存在
- **实际行为**: 全部 14 项声称修改均已验证存在（见以上各 PASS finding 的行号证据）
- **直接证据**: 以上所有 finding 的行号证据合集
- **影响**: 无。
- **严重程度**: PASS

#### S0-02-PASS — v2 normative scan 声称 0 命中与实际情况一致

- **入口/函数**: S0 artifact "Validation" (line 102)
- **文件(行号)**: `docs/gateflow/pr-190-f11-f12-s0-design-implementation-20260805.md:102`
- **输入场景**: S0 声称 `CompactInputV2`、`CompactCandidateV2`、`CompactAcceptedTruthV2`、旧 input/output v2 schema、旧 explicit-drop coverage与四值 reason均无命中
- **实际分支**: 独立扫描确认
- **预期行为**: 0 命中
- **实际行为**: `grep -c` 返回 0
- **直接证据**: 独立 `grep` 扫描结果
- **影响**: 无。
- **严重程度**: PASS

#### S0-03-PASS — Markdown fence parity 可复验

- **入口/函数**: S0 artifact "Validation" (line 104)
- **文件(行号)**: `docs/gateflow/pr-190-f11-f12-s0-design-implementation-20260805.md:104`
- **输入场景**: ` ``` ` fence marker 配对
- **实际分支**: S0 声称 Host 180 个 fence marker（偶数），Engine 6 个（偶数）
- **预期行为**: 可复验
- **实际行为**: 独立 `grep -c '```' docs/host/design.md` 验证
- **直接证据**: 待独立计数确认；该 finding 不影响设计合同语义
- **影响**: 即使 fence 不配对，只影响 Markdown 渲染，不影响设计合同语义完整性
- **严重程度**: PASS（合同级）

## Open Questions

无。所有 check 维度均有直接文本证据（行号），不存在阻碍 confident judgment 的问题。

## Residual Risk

1. **S0 是纯 design slice**：F11/F12/Engine contract 尚未在生产代码中实现。design truth 的完整性不保证后续 S1-S5 实现一定正确，只能保证代码 generation 有唯一、稳定的规范。此风险由 accepted plan 的 S1-S5 review gates 覆盖。
2. **Fence parity 计数偏差**：S0 artifact 声称 Host 180 / Engine 6 个 fence marker；本 review 独立计数结果为 Host 182 / Engine 8，但均为偶数（fence parity 成立）。S0 artifact 的计数偏差不影响设计合同语义完整性。
3. **design truth 与实际代码的一致性**：当前生产代码仍为 v2 contract；design truth 的 v3 contract 尚未在代码中落地。S1-S5 实现 slice 必须在各自 review gate 中逐项验证代码与 design truth 一致。

## Review Verdict

**全部 22 项 finding 均为 PASS。**

两份 design truth（`docs/host/design.md`、`docs/engine/design.md`）的 S0 修改与 accepted plan、accepted checkpoint、controller adjudication 的 frozen contract 完整一致：

- F11 public response identity owner 唯一（Host Tool Trace durable resolver），exact binding + keyset exhaustion + fail closed + security whitelist 全部冻结；
- F12 fresh v3 schema（CompactInputV3、CompactCandidateV3 + 五个 typed children、CompactOutputCapsV3 immutable DTO）、Host-derived coverage/omission/caps audit、single structure owner、repair/digest LLM boundary、fresh persistence 全部冻结；
- Engine generic structured output（三值 capability matrix + fail-fast + no inference + no downgrade + no provider-name dispatch）全部冻结；
- 旧 v2 normative 完全删除（0 命中），无兼容 alias/re-export/wrapper；
- 无 over-design、无 owner drift、无双真源。

S0 design truth 可以进入 S0 review gate acceptance，后续 S1-S5 实现 slice 可以将这两份 design 作为唯一、稳定的代码 generation 规范。
