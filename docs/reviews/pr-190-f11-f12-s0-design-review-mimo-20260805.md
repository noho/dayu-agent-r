# S0 Design Truth Review — PR 190 F11/F12

## Scope

- Mode: current changes (design-only slice)
- Branch: `codex/interactive-oracle`
- Base: `427b1c858d5e926f309935fa206963deb1618436`
- Output file: `docs/reviews/pr-190-f11-f12-s0-design-review-mimo-20260805.md`
- Review date: 2026-08-05
- Included scope: `docs/host/design.md`、`docs/engine/design.md`、`docs/gateflow/pr-190-f11-f12-s0-design-implementation-20260805.md`
- Excluded scope: 生产代码、tests、prompts、README（S0 是纯 design slice）
- Parallel review coverage: 无

## Review inputs

- Accepted plan: `docs/gateflow/pr-190-f11-f12-interactive-memory-plan-20260805.md`
- Accepted checkpoint: `docs/gateflow/pr-190-f11-f12-accepted-plan-checkpoint-20260805.md`
- S0 implementation artifact: `docs/gateflow/pr-190-f11-f12-s0-design-implementation-20260805.md`
- AGENTS.md: 项目约束
- 当前 owner 代码状态: 通过 subagent 读取 11 个关键文件确认 v2/v3 状态

## Findings

未发现实质性问题。

以下逐项验证均 PASS，无 FAIL finding。

---

## 逐项验证矩阵

### F11: Public compactor response identity

#### 1. Unique owner

- **验证项**: Tool Trace durable resolver 是 canonical terminal response identity 的唯一 public owner
- **证据**: `docs/host/design.md` 新增段落明确："该语义的 owner 是 Host Tool Trace durable resolver，不是 Service、CLI、JSON / Markdown renderer 或 evidence harness"
- **代码状态**: `dayu/host/durable/tool_trace.py::RunnerCallResolvedProjection` 当前只有 4 个字段（signal, manifest, runner_input_projection, selected_tool_schema_snapshot），不含 `compactor_response_identity`。`resolve_runner_call_projection_from_signal` 不做 terminal scan。设计正确描述了待实现的 public contract。
- **判定**: **PASS** — owner 声明清晰，代码缺口属于 S1 实现范围。

#### 2. Canonical response identity exact binding

- **验证项**: matching terminal 必须同时 exact match proposal manifest ref/digest、compaction operation id 与 attempt number
- **证据**: `docs/host/design.md` 明确："matching terminal 必须唯一，并同时 exact match proposal manifest ref / digest、compaction operation id 与 attempt number"
- **代码状态**: `dayu/host/context_events.py::build_context_compacted_payload`（line 1136）已绑定 proposal manifest、operation、attempt 与 `SuccessfulRunnerResponseIdentity`。`_runner_call_manifest.py::RunnerCallCompactorIdentity`（line 483）已持久化 parent_host_run_id、operation、attempt、engine_run、request_digest 与 input_projection_ref。
- **判定**: **PASS** — durable binding 已存在，public resolver 的 exact match 逻辑属于 S1。

#### 3. Pagination fail closed

- **验证项**: keyset exhaustion 无总页数 cap，corruption/mismatch fail closed
- **证据**: `docs/host/design.md`："每页有界，但不得设置任意总页数上限；full page 后 cursor 不严格增大、row sequence 不大于当前 cursor、cursor 非法或 page 数据损坏都必须抛 durable error"
- **判定**: **PASS** — fail closed 规则明确，无 scan cap，无降格为 missing 的路径。

#### 4. 安全白名单

- **验证项**: compactor response summary 只允许 binding、provider/model、request identity、provider request id
- **证据**: `docs/host/design.md`："headers、credential / API key、authorization、endpoint、raw prompt、raw request / response body 与 provider diagnostic payload 不得进入 public resolver、analysis JSON / Markdown、hot / cold trace 或 LLM-facing material"
- **判定**: **PASS** — 白名单封闭，secret/credential 泄漏路径被显式禁止。

#### 5. Fresh analysis schema v2

- **验证项**: Tool Trace analysis 使用 fresh schema version 2，v1 不保留
- **证据**: `docs/host/design.md`："Tool Trace analysis 使用 fresh schema version 2，把该 contract 投影为 `ToolTraceCompactorResponseSummary`…v1 producer / reader / validation 不保留，JSON 与 Markdown 必须只从同一个 structured report 渲染"
- **判定**: **PASS** — fresh cut 明确，无兼容 reader/adapter。

---

### F12: Fresh compact v3

#### 6. Fresh v3 schema — input

- **验证项**: `CompactInputV3` 替代 `CompactInputV2`，含真实 output caps
- **证据**: `docs/host/design.md` §24.3 完整定义 `CompactInputV3`（schema `dayu.context_compaction.input.v3`），root exact keys 为 `schema`、`current_input`、`source_boundary`、`output_caps`。`CompactOutputCapsV3` 定义 9 个 cap 字段。
- **代码状态**: `dayu/host/compaction.py` 仍使用 `CompactInputV2`（line 1040）和 `COMPACT_INPUT_SCHEMA_V2`（line 29）。无 v3 代码。属于 S3 实现范围。
- **判定**: **PASS** — 设计 contract 完整，代码缺口属于计划内 S3。

#### 7. Fresh v3 schema — output

- **验证项**: `CompactCandidateV3` 替代 `CompactCandidateV2`，删除 diagnostics/explicit drops
- **证据**: `docs/host/design.md` §24.3 定义 `CompactCandidateV3`（schema `dayu.context_compaction.output.v3`），root exact keys 为 `schema`、`session_summary`、`evidence_facts`、`answer_anchors`、`forward_intents`、`reference_continuity`。明确："旧 `diagnostics`、`explicitly_dropped_sources` 及其子项一律作为 unknown key 拒绝"
- **代码状态**: `dayu/host/compaction.py` 仍使用 `CompactCandidateV2`（line 1383）含 `diagnostics` 和 `explicitly_dropped_sources`。属于 S3 实现范围。
- **判定**: **PASS** — v2 normative 在设计文件中已完全删除，v3 定义完整。

#### 8. Typed facts — 五类子项

- **验证项**: 五个 typed child 定义完整，字段精确
- **证据**: `docs/host/design.md` §24.3 逐字段定义 `CompactSessionSummaryV3(text, source_labels)`、`CompactEvidenceFactV3(claim, support_labels, context_labels)`、`CompactAnswerAnchorV3(title, detail, source_labels)`、`CompactForwardIntentV3(intent_type, text, status, source_labels)`、`CompactReferenceContinuityV3(text, reason, source_labels)`。
- **判定**: **PASS** — 字段集完整，`CompactForwardIntentStatusV3` 保留 `open/blocked/superseded` 但明确禁止用 `superseded` 伪装 drop reason。

#### 9. Host-derived coverage/omission/caps audit

- **验证项**: represented/omitted 是 Host 从 immutable boundary + accepted provenance 的 exact partition，caps audit 同源
- **证据**: `docs/host/design.md`："accept owner 从 candidate provenance 派生 `CompactRepresentedCoverageV3`，再按 immutable root boundary 顺序计算 exact complement `CompactOmittedCoverageV3`；两集合必须不相交且并集 exact 等于 boundary"。`CompactPolicyUsageAuditV3` "从同一 caps projection、同一 estimator 与 candidate actuals 派生"。
- **判定**: **PASS** — coverage/omission/audit 全部 Host-derived，不依赖模型输出。

#### 10. Repair/digest LLM boundary

- **验证项**: request digest 与 source-boundary digest 不进入 LLM-facing text
- **证据**: `docs/host/design.md`："request digest 与 source-boundary digest 只属于 Host internal binding、audit 与 request serialization；initial / repair 的 system message、user message、template、示例和 validation feedback 都不得出现这两个 digest 的值或通用 digest 字段名"。§24.6 再次确认："initial / repair 都不得包含 request digest、source-boundary digest 的值或通用 digest 字段名"
- **判定**: **PASS** — digest 泄漏防护在设计层面完整，§24.7 要求 owner test 做反泄漏断言。

#### 11. Persistence — fresh cut

- **验证项**: artifact schema 4，旧 schema-3 不兼容
- **证据**: `docs/host/design.md` §24.4："compactor input projection 使用 `compactor_input_projection.v2`…compact artifact 的整数 schema version 固定为 `4`…旧 compact input/output contract、schema-3 compact artifact、diagnostics、explicit drops / reasons 以及依赖这些 payload 的旧 Session replay 不支持读取，不迁移，也不保留 alias、双读 parser、re-export 或 compatibility wrapper"
- **代码状态**: `dayu/host/compact_payload.py::COMPACT_ARTIFACT_SCHEMA_VERSION_VNEXT = 3`（当前 artifact schema）。属于 S3 迁移范围。
- **判定**: **PASS** — fresh persistence contract 完整，旧 artifact 不兼容边界明确。

#### 12. Single structure owner

- **验证项**: `compact_structure.py` 只拥有 JSON 结构，不拥有 domain dataclass
- **证据**: `docs/host/design.md`："output v3 的 JSON 结构只有一个 owner：`compact_structure` 只拥有 immutable exact structural descriptors…typed domain dataclass 由 compaction domain owner 唯一定义，structure owner 单向构造这些 types，不定义第二组 dataclass"
- **判定**: **PASS** — ownership 边界清晰，单向依赖，无 god schema compiler。

#### 13. Caps DTO — immutable projection

- **验证项**: `CompactOutputCapsV3` 不是 caps 第二 owner
- **证据**: `docs/host/design.md`："caps 只是 `MemoryProjectionPolicy` 的 immutable boundary projection：数值、默认值、合法性校验与 policy digest 仍只由 `MemoryProjectionPolicy` 拥有，compact input DTO 不得定义第二套 default、校验或配置读取"
- **判定**: **PASS** — DTO 只是机械投影，policy owner 不漂移。

---

### Engine: Generic structured output

#### 14. Engine generic structured output / no inference / no downgrade

- **验证项**: `structured_output` 是 provider-neutral 一等 request，不推断、不降级
- **证据**: `docs/engine/design.md`："公共入口原样消费 `AgentRunRequest.structured_output`…Engine 不从 system / user prompt、tool schema、provider 名称、model 名称或调用场景推断该请求"。"Agent 不根据本轮 tools、finish reason、provider error、provider / model 名称或历史响应改变 request；provider 拒绝 structured-output 时保留原 provider failure，不用较弱模式重试"
- **代码状态**: `dayu/engine/contracts/agent_run.py::AgentRunRequest`（line 74）无 `structured_output` 字段。`runner.py::AsyncRunner.call`（line 25）无 `structured_output` 参数。`runner_spec.py::RunnerSpec`（line 250）无 `structured_output_capability`。属于 S2 实现范围。
- **判定**: **PASS** — 设计 contract 完整，代码缺口属于计划内 S2。

#### 15. Capability matrix fail fast

- **验证项**: 不支持组合在 outbound call 前抛 ValueError
- **证据**: `docs/engine/design.md`："不支持组合必须在 Agent / Runner outbound call 前抛 `ValueError`，不得降级"
- **判定**: **PASS** — fail fast 矩阵明确，无隐式 fallback。

#### 16. Host compactor 不变 Engine special case

- **验证项**: Host compactor 不在 Engine 中变成 special case
- **证据**: `docs/engine/design.md`："Host 对 `none` / `json_object` / `json_schema` 的选择不得在 Engine 中变成 compactor special case，也不得按 provider 名称 dispatch。无论 capability 为何，Engine 都不自动升级、降级或重试成另一 structured-output mode"
- **判定**: **PASS** — Engine 只提供 generic capability，不知道 compact schema。

---

### 旧 v2 normative 删除

#### 17. 旧 v2 normative 真删除

- **验证项**: 设计文件中无残留 v2 normative 引用
- **证据**: 对 `docs/host/design.md` 和 `docs/engine/design.md` 执行全量 grep：
  - `CompactInputV2` → 0 命中
  - `CompactCandidateV2` → 0 命中
  - `CompactAcceptedTruthV2` → 0 命中
  - `dayu.context_compaction.input.v2` → 0 命中
  - `dayu.context_compaction.output.v2` → 0 命中
  - `CompactExplicitDropV2` → 0 命中
  - `CompactDropReasonV2` → 0 命中
  - `diagnostics` 作为 compact output field → 0 命中（仅 snapshot read model 的同名字段保留，非 compact output）
  - `explicitly_dropped_sources` → 仅出现在 v3 删除指令中
  - 四值 drop reason → 仅出现在 v3 禁止声明中
- **判定**: **PASS** — v2 normative 已完全删除，无双设计真源。

---

### 无兼容 / 过度设计 / owner drift

#### 18. 无兼容性设计

- **验证项**: 无 fallback reader、兼容 alias、re-export、wrapper
- **证据**: 设计文件明确："v1 producer / reader / validation 不保留"、"旧…不迁移，也不保留 alias、双读 parser、re-export 或 compatibility wrapper"、"不保留兼容 reader"
- **判定**: **PASS**

#### 19. 无过度设计

- **验证项**: 每个设计元素有明确 root cause
- **证据**:
  - F11: 复用既有 canonical terminal + manifest parser，只增加 public typed projection，无第二 EventLog/缓存/推断器
  - F12: 删除模型无法严格履约的 ledger 而非增加 semantic classifier；caps DTO 只是跨边界 immutable projection
  - `compact_structure.py`: 只解决 template/schema/parser 结构同源，不承载 domain dataclass/governance/persistence/transport
  - Engine: 只提供三值 generic capability，不增加 provider probe/fallback router/provider-name branch
- **判定**: **PASS**

#### 20. 无 semantic owner drift

- **验证项**: 每个语义有唯一 owner，无下游 fallback 补齐
- **证据**: owner 链固定为：
  - compact structure → template/schema/parser
  - compaction domain → typed dataclass
  - Context Governance → accept/coverage/partition
  - MemoryProjectionPolicy → caps 数值/default/validation/digest
  - Tool Trace resolver → public response projection
  - Engine → generic structured-output capability/transport
  - compact event owner → canonical terminal parsing
  - 设计无 `hasattr/getattr`、loose parsing、重复计算、兼容 shim
- **判定**: **PASS**

---

### Engine 设计与确认 contract 一致性

#### 21. AsyncRunner.call breaking change 声明

- **验证项**: Protocol breaking change 要求同 commit 迁移
- **证据**: `docs/engine/design.md`："该 Protocol breaking change 必须在同一个 accepted implementation commit 中同步迁移 `AsyncRunner` Protocol、所有 Runner 实现、Agent 调用点与全部 fake / stub / direct call sites；不得用 `=None` default 掩盖漏传"
- **判定**: **PASS**

#### 22. OpenAI-compatible payload projection

- **验证项**: `response_format` 只按 typed request 投影，不从 provider/model 补值
- **证据**: `docs/engine/design.md`："OpenAI-compatible payload builder 只按 typed request 写 `response_format`…schema request 的 name、strict 与实际 schema 必须原样投影，不从 `provider_request` 或配置补值"
- **判定**: **PASS**

#### 23. capability evidence 归属

- **验证项**: capability evidence 与 catalog 选择属于 Engine 上游装配
- **证据**: `docs/engine/design.md`："model / runtime config 可以把已验证的 capability 机械投影到 `RunnerSpec`，但 capability evidence 与 catalog 选择属于 Engine 上游装配；Engine contract 本身不按 provider 名称维护 capability 表，也不运行 provider probe"
- **判定**: **PASS**

---

## Open Questions

无。

## Residual Risk

1. **S0 设计尚未实现**: F11 resolver、F12 compact v3、Engine structured output 的生产代码仍为 v2 状态。设计 contract 已冻结，代码缺口属于 S1-S3 计划内工作。
2. **Tool Trace analysis schema v2 breaking change**: 仓外 consumer 风险留到后续实现与 PR closeout 明确。
3. **schema-3 compact artifact 与旧 Session replay 不兼容**: 设计明确不支持、不迁移；如产品要求迁移，owner 是独立 migration work unit。
4. **S0 implementation artifact 正确声明**: "S0 尚未经过 plan 要求的独立 review / re-review，也没有 accepted slice commit" — 本 review 是该 gate 的第一步。

---

## Conclusion

**PASS**。S0 design truth slice 的 23 项验证全部通过。两份设计文件中 v2 normative 已完全删除，v3 contract 定义完整且与 accepted plan 一致。F11 public resolver、F12 fresh compact v3、Engine generic structured output 的 unique owner、exact binding、fail closed、安全白名单、typed facts、Host-derived coverage/omission/caps audit、repair/digest LLM boundary、fresh persistence、无兼容/过度设计/owner drift 均已验证。生产代码仍为 v2 状态是预期行为，属于 S1-S3 实现范围。
