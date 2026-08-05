# PR 190 F11/F12 Interactive Memory 收口实施计划

## Gate metadata

- Gate：`plan`
- Work unit：PR 190 当前 work unit；F11 public compactor response identity 与 F12 fresh compact v3 收口
- PR：https://github.com/noho/dayu-agent-r/pull/190
- Branch：`codex/interactive-oracle`
- Plan base：`3087b1b983a97ce5012d54e818795f4755434a98`
- Goal Confirmation：用户已确认；本计划不得重新解释或缩减已确认的 F11/F12、registry、evidence 与 gate 要求
- Plan status：`ready-for-plan-rereview`
- Current gate after this artifact：`plan re-review`
- Next entry point：两路原 reviewer 对本次 controller fix 做独立 re-review；本轮明确停在 plan gate，不进入 implementation、registry update、stage、commit 或 push
- Blocking open questions：无
- Artifact path：`docs/gateflow/pr-190-f11-f12-interactive-memory-plan-20260805.md`

## Durable inputs and preservation

以下输入是本计划的只读真源；本 plan gate 不修改它们：

| 真源 | 当前 SHA-256 | 用途 |
|---|---|---|
| `docs/host/design.md` | `67de9dd53e958170d0d98072408e0a57f20adc4f7ee3728356089902ff2e1310` | Host owner、compaction state machine、canonical terminal 与 identity binding |
| `docs/engine/design.md` | `999eda3213ce1367937e924e7f83998adfd29b915e334c8cf9828a0ab1553fc3` | Engine stateless boundary、Runner request/terminal contract |
| `docs/reviews/wu-interactive-memory-postfix-readiness.md` | `39cd2d7e28c951791e540afa5d7db63b8ede312b7d3c5d59cffff85527bf0abb` | F11/F12 finding、用户裁决与 readiness controller |
| `/Users/leo/workspace/.dayu-cli-ci/interactive-memory-postfix-20260804TV7mSm6/evidence/observed-behavior-postfix.md` | `a12c1311686a8fadf7a40e5fa6c5f4468fded05f8951e8aaa585f839f28d85fc` | #57-#64 旧 post-fix 观察证据 |
| `docs/reviews/plan-review-20260805-144305.md` | `d9358fe2621e70ffc1790af2ad71678ccaccb2105df4cfc9833336b6005fcfd6` | 第一份独立 plan review，F01-F10 与 open questions |
| `docs/reviews/plan-review-20260805-144405.md` | `e2bb882149f5e0de0528e99d6ee96f30fd6073a4ad2d64b214e99a7d968bace4` | 第二份独立 plan review，findings 1-7 与 open questions |

旧 evidence bundle 永久只读，不覆盖、不追加、不用新结果回填。后续真实取证必须创建新 run directory、报告与 digest。`docs/reviews/wu-interactive-memory-postfix-readiness.md` 保持 Oracle/controller 的用户裁决语义；只有最后收口 slice 可在新证据和用户裁决后补最终状态，不能改写既有 finding、观察事实或裁决原文。

Plan gate continuation preflight 已确认：当前分支不是受保护分支；工作树包含本 plan、用户已有 finding baseline 与两份只读 review。所有后续 gate 都必须把 review 与 finding baseline 视为外部输入，除本计划明确允许的最终状态补记外不得纳入实现 checkpoint。

本轮 controller 的逐 finding 裁决、直接证据与 plan delta 记录在 `docs/gateflow/pr-190-f11-f12-plan-review-adjudication-20260805.md`；该 artifact 与本计划共同构成 plan fix gate 输出。

## First-principles judgment

### F11 动机与 root cause

F11 真实存在且是公开可观测性 contract 缺口，不是 canonical identity 缺失：

- `dayu/host/context_events.py` 已把 `SuccessfulRunnerResponseIdentity` 写入 canonical `CONTEXT_COMPACTED`，并在 post-success `CONTEXT_COMPACTION_ATTEMPT_REJECTED` 中保存同一强类型 identity；builder 已校验 operation、attempt 与 Engine run binding。
- `dayu/host/_runner_call_manifest.py` 已持久化 proposal manifest 的 exact ref/digest、`compaction_operation_id`、`compaction_attempt_number` 与 `compactor_engine_run_id`。
- `dayu/host/durable/tool_trace.py::resolve_runner_call_projection_from_signal` 目前只返回 manifest、input projection 和 tool schema snapshot；`dayu/host/tool_trace_analysis_*` 因此无法通过正式 public resolver 取得 response/provider/model identity。

因此 owner-level 修复应位于 Host Tool Trace durable resolver 及其 typed analysis projection；不能在 CLI/Service/Markdown renderer 从 raw EventLog、配置、时间戳、日志或 provider 名称反推。

### F12 动机与 root cause

F12 真实存在，且当前严重性不是 parser 不够宽松，而是 v2 把确定性治理错误分配给无状态模型：

- `CompactCandidateV2` 要求模型产出 diagnostics、`explicitly_dropped_sources` 与四种主观 drop reason。
- `accept_compact_candidate_v2` 已能从 candidate provenance 求 represented，但又要求模型补齐 exact drop partition；真实证据显示 `policy_limit` 很难稳定形成 accepted branch。
- caps 的真实 owner 是 `MemoryProjectionPolicy` 与 Host estimator；initial prompt 却不携带真实 caps，并总是携带 repair protocol。
- strict parser、accept barrier、bounded repair、single terminal、Memory 不污染和 fallback 本身是正确边界，应保留而非放宽。

正确修复是 fresh input/output v3：模型只生成五类业务语义及必要 provenance；Host 从 immutable source boundary 与已接受 provenance 派生 represented/omitted，并持久化 cap/usage audit。不能在 Memory、CLI、测试 fake 或 provider adapter 增加 fallback/loose parsing。

### 对给定路径的校正

F11 与 F12 不得合并为一个“compactor helper”。F11 owner 是 Tool Trace 对 canonical terminal 的公开、严格投影；F12 owner 链是 Host compact structure contract、Context Governance、durable accepted truth 与 Engine 的通用 transport capability。二者只在真实 conformance evidence 与最终 registry 收口处汇合。

## Frozen target contracts

### F11 — public Host Tool Trace response resolution

1. 在 `dayu/host/durable/tool_trace.py` 增加公开封闭 enum `CompactorResponseDisposition`：`ACCEPTED`、`ATTEMPT_REJECTED`。
2. 增加公开 dataclass `ResolvedCompactorResponseIdentity`，字段固定为：
   - `disposition: CompactorResponseDisposition`
   - `terminal_event_id: str`
   - `terminal_event_sequence: int`
   - `compaction_operation_id: str`
   - `compaction_attempt_number: int`
   - `proposal_manifest_ref: str`
   - `proposal_manifest_digest: str`
   - `successful_response_identity: SuccessfulRunnerResponseIdentity | None`
3. `RunnerCallResolvedProjection` 增加 `compactor_response_identity: ResolvedCompactorResponseIdentity | None`。普通 runner call 固定为 `None`；compactor call 未观察到 matching terminal 时也只能为 `None`，analysis 必须附加明确的 `compactor-response-terminal-not-observed` limitation，不能把缺失解释为失败、成功或 provider 不可用。
4. `resolve_runner_call_projection_from_signal` 在同一 caller-owned read transaction 中：
   - 先通过现有 strict manifest resolver 得到 typed `RunnerCallInputManifest.compactor_identity`；
   - 复用 `compaction_terminal` / `proactive_compaction` 的有限 event-type keyset exhaustion 模式，使用固定正数 page size 与 `after_event_sequence` 单调 cursor，读取 manifest 中 `parent_host_run_id` 的 canonical `CONTEXT_COMPACTED` 与 `CONTEXT_COMPACTION_ATTEMPT_REJECTED`，直到返回 page 长度小于 page size 才算完整 exhaustion；
   - 不设任意“最多 N 页”总扫描上限。每页有界，但必须读尽该 parent Run 的两类 canonical rows；empty page或short page只表示正常exhaustion，empty/invalid cursor、full page后cursor不严格增大或reader返回sequence不大于cursor时抛`HostDurableError`，不得把未完成扫描当作terminal missing；
   - 只接受 proposal manifest ref/digest、operation id、attempt number 全部与当前 manifest exact match 的唯一 terminal；
   - 对同 operation/attempt 发现 ref/digest mismatch、同 manifest 多 terminal、malformed payload、identity 的 Engine run id/attempt/request identity 不一致时抛 `HostDurableError`，整个 resolver fail closed；
   - 只有完整 exhaustion 后确实没有 matching terminal 且没有冲突 terminal时才返回 `None`；不新增 scan-cap limitation，不得从 `RunnerSpec`、manifest provider/model、事件相邻性或时间戳补 identity。
5. canonical terminal 字段的 strict parsing 仍由 `dayu/host/context_events.py` 拥有；将当前 private successful-response parser 收口成一个 public typed parser供 builder/parser 与 Tool Trace 共用，不能复制 JSON key 读取逻辑。
6. `dayu/host/tool_trace_analysis_contracts.py` 增加 `ToolTraceCompactorResponseSummary`，只投影上述 binding、provider、model、Runner request identity、provider request id availability/value；禁止 headers、credential、authorization、raw response、prompt/body。
7. `ToolTraceAnalysisReport` 升为 fresh `schema_version=2` 并增加按 `(parent_host_run_id, operation, attempt, terminal sequence)` 稳定排序的 `compactor_responses`。删除 v1 reader/validation，不保留双读、兼容 parser 或 adapter；所有 producer、JSON renderer、Markdown renderer、evidence harness consumer 与 tests 在 S1 同步切到 v2。JSON 与 Markdown 只从同一 structured report 渲染；Service 继续只负责调用与发布。

### F12 — fresh compact input/output v3

#### 模型可见 input

- `CompactInputV3.schema` 固定为 `dayu.context_compaction.input.v3`。
- 字段仅为 `schema`、`current_input`、`source_boundary`、`output_caps`。
- `CompactOutputCapsV3` 是 immutable boundary DTO，不是 caps 第二 owner。`MemoryProjectionPolicy` 继续唯一拥有数值、default、校验和 policy digest；DTO 不得定义 default、数值校验或独立配置读取，只能由同一 `MemoryProjectionPolicy` instance 经 `context_governance.py::compact_output_caps_v3_from_memory_policy(policy)` 机械构造。`compaction.py`只定义DTO，`memory.py`继续可消费compaction domain types，二者不互相import；已经同时依赖两者的Context Governance作为直接上游投影边界，避免memory↔compaction循环依赖。字段固定为：
  `session_summary_char_cap`、`evidence_fact_item_cap`、`evidence_fact_char_cap`、`answer_anchor_item_cap`、`answer_anchor_char_cap`、`forward_intent_item_cap`、`forward_intent_char_cap`、`reference_continuity_item_cap`、`reference_continuity_char_cap`。
- cap 不通过 prompt 常量、provider 分支或 repair message 反推；input digest 覆盖完整 caps 与 immutable source boundary。owner test 必须逐字段证明 DTO 与同一 policy instance 一一相等，并证明 DTO 无 default/validation ownership。

#### 模型输出

- `CompactCandidateV3.schema` 固定为 `dayu.context_compaction.output.v3`。
- root exact keys 固定为 `schema`、`session_summary`、`evidence_facts`、`answer_anchors`、`forward_intents`、`reference_continuity`。
- `dayu/host/compaction.py` 唯一拥有 `CompactCandidateV3` 与全部 typed children；字段固定为：`CompactSessionSummaryV3(text, source_labels)`、`CompactEvidenceFactV3(claim, support_labels, context_labels)`、`CompactAnswerAnchorV3(title, detail, source_labels)`、`CompactForwardIntentV3(intent_type, text, status, source_labels)`、`CompactReferenceContinuityV3(text, reason, source_labels)`。`CompactForwardIntentStatusV3` 保留 `open/blocked/superseded`，但该 status 只描述待办自身状态，严禁用 `superseded` 伪装 evidence correction/drop reason。
- JSON Schema 的 root `required` 必须包含全部六个 root keys；`session_summary` 必填且 type 为 object-or-null。所有 nested object 同样 exact required 且 `additionalProperties=false`。
- `session_summary: null` 含义是完整 replacement 接受后清空旧 summary，不影响同一 candidate 的其它四类语义；省略该 key 必须被 schema/parser拒绝。
- 删除 `diagnostics`、`explicitly_dropped_sources`、`CompactCandidateDiagnosticV2`、`CompactExplicitDropV2`、`CompactDropReasonV2` 及四种 reason；fresh parser 对这些旧 key 一律 unknown-key reject，不兼容读取。
- 不恢复 model-produced `superseded` 关系、不增加 `omission_kind`、不让 Host 做自然语言或 subject matching 推断。rolling correction 只通过 accepted current replacement provenance 与 old labels 的 Host-derived omission表达。

#### 单一 structure owner

- 新模块 `dayu/host/compact_structure.py` 只拥有 output v3 的 JSON 结构，不拥有 typed domain dataclass、acceptance、caps、durable state、Engine transport 或 prompt 业务文案。它单向 import `compaction.py` 的 v3 typed domain contract并构造它；`compaction.py` 不 import `compact_structure.py`。
- 固定 public API：
  - `compact_output_template_v3() -> Mapping[str, JsonValue]`
  - `compact_output_json_schema_v3() -> Mapping[str, JsonValue]`
  - `parse_compact_candidate_v3(text: str) -> CompactCandidateV3`
- 模块内部以一组 immutable exact structural descriptors 作为结构真源；template、JSON Schema 的 `properties/required/additionalProperties=false` 与 parser 的 exact-key checks 必须从这些 descriptors 派生。字段业务类型最终构造成 `compaction.py` 的 `CompactCandidateV3` 及其 typed children，不引入第二组 dataclass、`Any`、`object` 或通用 god schema compiler。
- JSON Schema 必须以 immutable canonical JSON value 暴露；固定 schema name `dayu_context_compaction_output_v3`，`compact_output_json_schema_digest_v3()` 使用 Host canonical JSON serialization计算 SHA-256。`JsonSchemaStructuredOutputRequest.name/schema`、captured runner input manifest记录的 schema digest与 transport payload必须来自同一次 structure projection；manifest digest必须等于对 request中实际 schema重算的 owner digest，不能分别重建。
- owner tests 必须证明 template、schema 与 parser 的 root/nested key 集完全一致，schema name/digest 与 transport同源且输入 mutation不能改变 owner-held schema；新增/删除任一 key 时三者不能漂移。

#### Host acceptance 与 durable truth

- `accept_compact_candidate_v3(compact_input, candidate, memory_policy)` 是唯一 accept owner。
- Host 从 candidate provenance 得到 `CompactRepresentedCoverageV3`；按 root boundary 顺序计算补集 `CompactOmittedCoverageV3`，不生成原因、不做财报语义推断。
- `CompactPolicyUsageAuditV3` 记录与 `output_caps` 同源的各 section item/char actual、cap、policy ref/digest。cap 校验失败仍返回 strict `CompactValidationReportV3`，不得先 accept 再由 Memory 丢弃。
- `CompactAcceptedTruthV3` 只可由 governance permit 构造，包含 candidate、immutable boundary、represented、omitted、policy usage audit、current input ref；其不变量是 represented 与 omitted 不相交且并集 exact 等于 boundary。
- `covered_source_refs` 从同一 accepted partition 派生；artifact、canonical terminal、Memory、RunInput、Tool Trace 都读取这个 accepted truth，不能各自重算。

#### Fresh persistence

- compactor input projection 升为 `compactor_input_projection.v2`，持久化 v3 input、真实 caps、repair binding（如有）与现有 provenance descriptor。
- compact artifact 升为整数 schema `4`；accepted candidate 是 output v3，coverage 字段改为 `represented_coverage`、`omitted_coverage`、`policy_usage_audit`。
- 删除 artifact/event parser 中 diagnostics、explicit drops/reasons 的字段与 v2 读取分支；不支持旧 compact contract、旧 schema-3 compact artifact与依赖它们的旧 Session replay，不迁移、不保留 alias/re-export/wrapper。该限制不等于整个旧 DB bootstrap 必然无法打开；未触及旧 compact payload的其它 durable rows仍按各自现有 schema处理。
- `CONTEXT_COMPACTED` 继续保存 accepted proposal manifest ref/digest 与 successful response identity；只替换 accepted semantic payload 为 v3 truth。rejected/failure terminal 与 single-terminal owner 不变。

#### Initial/repair state machine

```text
immutable v3 input + actual caps
        |
        v
initial request（无 repair protocol）
        |
   strict structure parse
        |
        +-- valid + governance accept --> one CONTEXT_COMPACTED --> artifact/Memory
        |
        +-- invalid/reject --> CONTEXT_COMPACTION_ATTEMPT_REJECTED
                                  |
                                  +-- budget remains --> self-contained repair
                                  |                     same Host-internal request digest
                                  |                     same Host-internal boundary digest
                                  |                     whole candidate replay
                                  |
                                  +-- exhausted --> one CONTEXT_COMPACTION_FAILED
                                                      --> existing fallback
```

- initial 与 repair 共用同一个 packaged system contract，以及同一次 `compact_structure.py` 生成的 concrete template/schema source。Host 分别渲染 initial user body 与 repair user body，禁止复制第二份手写 output shape。
- initial user body 必须包含同一 immutable v3 input、真实 caps、五类字段含义、nullable clear semantics、provenance 规则、同源 template与最小完整示例；实际渲染内容不得包含 repair protocol、previous attempt或validation issues。
- repair user body 必须自足包含同一 immutable v3 input、同源完整 template/字段规则、前次 attempt number、bounded/redacted issues与 whole-candidate replacement要求；不得只发 patch 指令或依赖 initial调用的隐式上下文。
- request digest 与 source-boundary digest只存在于 Host内部 `CompactionRequest` binding、audit和request serialization；二者绝不进入 LLM-facing initial/repair system或user文本。owner test必须对 captured runner input做反泄漏断言，证明 exact digest values 与 generic digest字段名均不存在。
- repair 继续受 `MAX_COMPACT_REPAIR_ISSUES`、单 issue chars、总 feedback chars 与 attempt budget 限制；切换 boundary 或 digest 必须拒绝旧 feedback。
- rejected candidate 不写 artifact、不写 `CONTEXT_COMPACTED`、不进入 Memory；迟到结果不产生第二 terminal；budget 耗尽保持现有 tier fallback。

### Engine generic structured-output contract

1. 新建 `dayu/engine/contracts/structured_output.py`：
   - `StructuredOutputCapability(StrEnum)`：`NONE="none"`、`JSON_OBJECT="json_object"`、`JSON_SCHEMA="json_schema"`；
   - `JsonObjectStructuredOutputRequest`；
   - `JsonSchemaStructuredOutputRequest(name: str, schema: Mapping[str, JsonValue], strict: bool)`；
   - `StructuredOutputRequest: TypeAlias = JsonObjectStructuredOutputRequest | JsonSchemaStructuredOutputRequest`。
2. `RunnerSpec` 增加必填 `structured_output_capability`；`AgentRunRequest` 增加显式 `structured_output: StructuredOutputRequest | None`；`AsyncRunner.call` 增加 required、无 default 的 keyword-only `structured_output`。这是 Protocol breaking change：S2 同一 accepted commit 必须同步更新 `AsyncRunner` Protocol、唯一实现 `AsyncOpenAIRunner.call/_call_impl`、`Agent` 调用点、所有 test fake/stub/call sites；不得用 `=None` default 隐藏漏传。不得进入 `provider_request_extension`、headers 或 extra payload。
3. compatibility matrix 固定：
   - `NONE` 只接受 `None`；
   - `JSON_OBJECT` 只接受 `None` 或 `JsonObjectStructuredOutputRequest`；
   - `JSON_SCHEMA` 接受 `None`、json-object request 或 json-schema request；
   - 不支持的组合在 Agent/Runner 调用前 `ValueError` fail fast，不降级。
4. OpenAI-compatible payload builder只按 typed request 投影 `response_format`：json object 为 `{type:"json_object"}`；json schema 为 `{type:"json_schema", json_schema:{name,strict,schema}}`。不读取 provider/model 名称，不吞 provider rejection 后重试成较弱模式。
5. `ModelConfig` 增加 required `structured_output_capability` 并机械投影到 `RunnerSpec`。package catalog 的本 work unit 固定矩阵：DeepSeek base records=`json_object`；Mimo base records=`none`；其余当前 base records 全部=`none`。继承项只继承父值，不重复写。DeepSeek 的依据是官方 [JSON Output guide](https://api-docs.deepseek.com/guides/json_mode/) 与 [Create Chat Completion reference](https://api-docs.deepseek.com/api/create-chat-completion) 对 `response_format={"type":"json_object"}` 的明确支持；S4仍须验证本仓库 endpoint/model/options的真实装配。Mimo=`none` 表示 capability unknown时的保守值，不是“实测不支持”。
6. 当前 package catalog 不标任何 `json_schema` model。OpenAI 官方 [Structured Outputs guide](https://developers.openai.com/api/docs/guides/structured-outputs) 只作为 generic `json_object`/`json_schema` transport shape、all-fields-required、nullable union与 `additionalProperties=false` 的设计证据，不证明当前 catalog 的具体 provider/model支持；`json_schema` transport由 provider-neutral synthetic owner tests覆盖，未来只有取得目标 model直接 capability证据后才单独改 catalog。
7. `LLMContextCompactor` 只按 `RunnerSpec.structured_output_capability` 选择：none→无 request，json_object→object request，json_schema→使用 `compact_output_json_schema_v3()`；不按 provider 名称分支。

## Implementation slices

### S0 — 先更新设计真源

Objective：先把已确认 contract 写入设计真源，保证后续代码 generation 有唯一、稳定的规范。

Allowed files：

- `docs/host/design.md`
- `docs/engine/design.md`
- 新的 S0 implementation/review artifacts under `docs/gateflow/`

Exact Host design edit list：

1. §14.1 `Tool Trace Hot / Cold Storage` 的 runner-call reconstruction段：补正式 public resolver从 canonical compacted/rejected terminal解析 response identity、proposal manifest/operation/attempt/Engine-run exact binding、有限 page + keyset exhaustion、mismatch fail closed与secret whitelist；不加入scan cap。
2. §24.2 `LLM-facing Compact I/O 硬边界`：删除模型产出diagnostics、explicit drop ledger/reason和隐式caps的要求；改为v3五类业务语义+必要provenance、真实caps输入、digest不进入LLM文本。
3. §24.3 `Compact v2 I/O Contract`：整节替换为`Compact v3 I/O Contract`，逐字段定义`CompactInputV3`、`CompactOutputCapsV3` boundary DTO、五个typed child、`CompactCandidateV3`、all-root-keys-required/null summary、单一structure owner以及旧key strict reject。
4. §24.4 `Snapshot Typed Schema`：把accepted payload/artifact从represented+explicit drops改为represented+Host-derived omitted+policy usage audit；写明旧compact artifact/session replay不支持但不扩大成整个DB不可打开。
5. §24.5 `五类 Session Semantic Memory`：删除任何从drop reason消费语义的描述；Memory只消费`CompactAcceptedTruthV3`，rolling correction以current retained provenance + old omitted labels表达。
6. §24.6 `Prompt Assembly`：写明shared system contract、同一structure template/schema source、initial/repair两种Host-rendered user body、自足repair、digest反泄漏。
7. §24.7 `测试与评测边界`：增加template/schema/parser同源、policy→DTO逐字段、pagination exhaustion、prompt反泄漏、fresh v2 rejection与real-provider observation边界。
8. §25 `Context Governance`：将accept owner、coverage partition、caps/usage audit、repair binding与single-terminal路径全部切到v3；删除四类drop reason和model-owned cap ledger。
9. §25.1 `Compact Event 响应路径`：保持proposal manifest与`SuccessfulRunnerResponseIdentity`既有真源，补F11 public projection；不得改写canonical terminal ownership。

Exact Engine design edit list：

1. §2 `公共入口` 与 §4 `AgentRunRequest`：增加显式`StructuredOutputRequest | None`。
2. §6 `Agent 推理循环`：每次Runner call原样转发同一request，不推断、不降级。
3. §7 `Runner 协议`：把required keyword-only参数写入Protocol并声明所有实现/call sites同commit迁移。
4. §8 `RunnerSpec 与 RunnerCallOptions`：定义`none/json_object/json_schema` capability、合法组合与fail-fast matrix；structured output不进入provider extension。
5. §15 `Context Compaction`：只说明Host可消费generic capability，Engine不知道compactor业务schema；不得写provider-name dispatch。

S0必须删除或替换所有与新contract冲突的v2 normative文字，不能仅在后文追加v3导致双设计真源。

Tests：design terminology/static links、`git diff --check`。完成信号是两份设计之间无 ownership 冲突，且代码 slice 不再需要自行发明 contract。

### S1 — F11 Host Tool Trace typed resolver 与 analysis projection

Prerequisite：S0 accepted commit。

Allowed production files：

- `dayu/host/context_events.py`
- `dayu/host/durable/tool_trace.py`
- `dayu/host/tool_trace_analysis_input.py`
- `dayu/host/tool_trace_analysis_contracts.py`
- `dayu/host/tool_trace_analysis_rules.py`
- `dayu/host/tool_trace_analysis.py`
- `dayu/host/__init__.py`（只导出真正 public typed resolver contract；禁止兼容 re-export）

Allowed tests/docs：

- `tests/host/test_context_compact_events.py`
- `tests/host/test_tool_trace_queries.py`
- `tests/host/test_tool_trace_analysis_input.py`
- `tests/host/test_tool_trace_analysis_rules.py`
- `tests/host/test_tool_trace_analysis.py`
- `dayu/host/README.md`
- `tests/README.md`（仅当测试职责说明实际变化）
- S1 gate artifacts

Call/data flow：`RUNNER_CALL_INPUT_ASSEMBLED hot signal -> strict manifest/payload resolver -> typed compactor manifest identity -> parent Host run canonical terminal page -> exact manifest/operation/attempt/Engine-run validation -> ResolvedCompactorResponseIdentity -> ToolTraceJoinedRecord -> ToolTraceAnalysisReport v2 -> JSON/Markdown`。

Owner tests必须覆盖：accepted identity；post-success rejected identity；no-success rejection 的 nullable identity；ordinary runner None；完整 exhaustion 后 terminal not observed limitation；目标terminal位于一个及多个full page之后仍可解析；full page后cursor严格推进；empty page结束；注入重复/倒退cursor或不推进page fail closed；不存在任意page-count提前截断或scan-cap limitation；wrong ref、wrong digest、wrong operation、wrong attempt、wrong Engine run、duplicate terminal、malformed identity 全部 fail closed；fresh analysis v2 producer/JSON/Markdown/tests同切且v1构造/读取失败；JSON/Markdown provider/model/request ids 同源；secret-like extra field拒绝且输出不含 credential/header/raw payload。Service 不增加语义测试。

### S2 — Engine generic structured output 与 config capability

Prerequisite：S0 accepted commit；可与 S1 在实现顺序上独立，但 checkpoint 必须串行。

Allowed production/config files：

- `dayu/engine/contracts/structured_output.py`（new）
- `dayu/engine/contracts/agent_run.py`
- `dayu/engine/contracts/runner.py`
- `dayu/engine/contracts/runner_spec.py`
- `dayu/engine/contracts/__init__.py`
- `dayu/engine/agent.py`
- `dayu/engine/runners/openai/payload.py`
- `dayu/engine/runners/openai/runner.py`
- `dayu/engine/__init__.py`
- `dayu/runtime/config_loader.py`
- `dayu/service/host_assembly.py`
- `dayu/host/_execution_config_projection.py`
- `dayu/config/models.json`
- `docs/cli_init_workspace_manifest_v1.json`
- `tests/cli/test_smoke_cli_init_provider_matrix.py`（只同步最终 manifest digest constant）

Allowed owner tests/docs：相关 `tests/engine/contracts/test_agent_run.py`、`test_runner_spec.py`、`tests/engine/test_protocols_surface.py`、`tests/engine/runners/openai/test_payload_build.py`、`test_protocol_surface.py`、`tests/engine/test_config_models.py`、`tests/runtime/test_config_loader.py`、`tests/service/test_host_assembly.py`、`dayu/engine/README.md`、`dayu/config/README.md`、`dayu/README.md`（仅跨层公开 request flow 需要更新）、S2 artifacts。

Exact migration sequence：先改`StructuredOutputRequest`/`RunnerSpec`/`AgentRunRequest` typed contracts；紧接着在同一未提交diff中同步`AsyncRunner` Protocol、`AsyncOpenAIRunner.call/_call_impl`、`Agent`唯一生产call site以及全仓所有runner fake/stub/direct call；最后接OpenAI-compatible payload与config projection。任何call site仍依赖旧signature时S2不得进入review。

Error paths：unsupported capability/request 组合在 outbound HTTP 前失败；unknown/missing config enum fail fast；provider 返回不支持 response format 时保持原 provider failure，不 retry/downgrade；structured-output request 不进入 trace extra bag。Tests 用 provider-neutral synthetic specs 分别锁定三种 mode 与 exact payload，显式断言required参数缺失由pyright/typed fixture暴露、DeepSeek catalog投影为json_object、Mimo为保守none、当前catalog无json_schema、actual request schema name/digest与owner canonical schema同源。

### S3 — F12 Host compact v3 纵向切换

Prerequisite：S0、S2 accepted commits。该 slice 必须作为一个原子 contract migration 完成，避免 accepted checkpoint 出现 v2/v3 双 owner、兼容 alias 或 durable state 半迁移。

Allowed production files：

- `dayu/host/compact_structure.py`（new）
- `dayu/host/compaction.py`
- `dayu/host/context_governance.py`
- `dayu/host/llm_compaction.py`
- `dayu/host/compact_material.py`
- `dayu/host/compact_pipeline.py`
- `dayu/host/compaction_operation.py`
- `dayu/host/compact_artifact.py`
- `dayu/host/compact_payload.py`
- `dayu/host/context_events.py`
- `dayu/host/dispatch.py`
- `dayu/host/engine_ingest.py`
- `dayu/host/memory.py`
- `dayu/host/run_input.py`
- `dayu/host/__init__.py`
- `dayu/config/prompts/scenes/conversation_compaction.md`
- `dayu/config/prompts/scenes/conversation_compaction_user.md`
- `docs/cli_init_workspace_manifest_v1.json`
- `tests/cli/test_smoke_cli_init_provider_matrix.py`（只同步最终 manifest digest constant）

Allowed tests/docs：

- `tests/host/fake_compaction.py` 与 `tests/host/_context_compaction_assertions.py`（迁移到 v3 contract，不能模拟不存在的兼容行为）
- `tests/host/test_compaction_contract.py`
- `tests/host/test_llm_compaction.py`
- `tests/host/test_compact_material.py`
- `tests/host/test_compact_pipeline.py`
- `tests/host/test_compaction_operation.py`
- `tests/host/test_compact_artifact_store.py`
- `tests/host/test_context_compact_events.py`
- `tests/host/test_memory_projection.py`
- `tests/host/test_run_input_builder.py`
- `tests/host/test_public_compact_smoke.py`
- `tests/host/test_context_budget.py`
- `tests/host/test_proactive_compaction_operation.py`
- `tests/host/test_compaction_terminal.py`
- `tests/host/test_compaction_cancellation_scope.py`
- `tests/runtime/test_scene_assets_migration.py`
- `tests/runtime/test_config_loader.py`
- `tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py`
- `tests/service/test_host_assembly.py`
- `dayu/host/README.md`、`dayu/config/README.md`、`tests/README.md`
- `dayu/README.md` 仅在核对后确有跨层 stable contract 变化时更新；根 `README.md` 不更新，因用户命令、参数、输出位置与 workflow 不变
- S3 artifacts

S3保持一个accepted原子vertical migration，不拆成可运行accepted checkpoints。理由：任何S3a式checkpoint都会保留v2 active owner同时引入未消费v3 contract，或让parser/prompt/persistence不同步；这违反fresh schema与单一owner，比审查大diff风险更严重。

Worktree内部实施顺序固定：

1. 在`compaction.py`建立全部v3 typed domain types/DTO与policy机械投影，在`compact_structure.py`建立同源structure descriptors/template/schema/parser；此时不checkpoint、不review、不commit。
2. 同一未提交diff中一次切换governance、operation、artifact/event、Memory、RunInput、dispatch/ingest及所有fakes/tests，再切换shared system + initial/repair user rendering，确保typed consumer、parser、prompt和persistence一致。
3. 全仓删除v2 contract、diagnostics、explicit drops/reasons及旧parser分支；用`rg`证明无生产引用、无兼容alias/re-export/wrapper。
4. 最后稳定prompt/models assets，更新publication hashes，运行focused coverage、full tests、pyright与diff checks；只有全部通过后才进入两路review。

Rollback strategy：S3在review acceptance前没有任何checkpoint；若中间方向失败或无法在allowed scope内收口，保留durable implementation diagnostic后丢弃**仅该slice尚未提交的intended diff**，恢复到S2 accepted commit，再返回plan/implementation gate。不得部分保留v3文件、不得触碰用户dirty files、不得用兼容层维持半迁移。大diff审查成本记录为residual risk，不是语义blocker。

Owner tests除所有 strict shape/provenance/cap 路径外，必须有以下 counterexamples：五个typed child字段精确；所有root keys required且summary required nullable；template/schema/parser key集同源；schema immutable/canonical且name/digest/transport同源；旧 diagnostics/drop key reject；unknown/duplicate/missing keys reject；empty semantics reject；summary null 清旧 summary；represented/omitted exact complement；candidate 伪造 omission/cap/usage key reject；policy→`CompactOutputCapsV3`逐字段相等且DTO无default/validation；Host cap actual 的字符算法与 Memory estimator同源；initial/repair共用system contract与同一structure template/schema；initial有真实caps且无repair protocol；repair自足并含same input/template/previous attempt/bounded issues/whole-candidate要求；captured initial/repair均不含request/boundary digest value或字段名；Host内部digest/boundary/attempt binding exact；repair整体重产；rejected candidate不污染Memory；attempt exhausted单terminal+fallback；rolling correction只证明retained current provenance、old labels Host-derived omitted、Memory/RunInput/reconnect无旧结论，不持久化主观reason，也不滥用forward-intent superseded。

### S4 — 新 real-provider conformance evidence

Prerequisite：S1/S2/S3 accepted commits。此 slice 只允许 evidence harness、测试与新 evidence output；不得以取证需要改生产 contract。若真实行为暴露产品 bug，停止 evidence gate，回到新的 implementation slice修 owner，完成双 review 后重新从干净 run 取证。

Allowed repository files：

- `utils/smoke_host_public_conversation_memory.py`
- `utils/smoke_host_public_conversation_memory_scenarios.py`
- `tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py`
- 新的 S4 gate artifact

New external output root：`/Users/leo/workspace/.dayu-cli-ci/<new-interactive-memory-v3-run-id>/`；不得复用 `interactive-memory-postfix-20260804TV7mSm6`。

Mandatory evidence：

1. 真实 Mimo（capability=`none`）首先运行；证明**本仓库装配**没有 structured-output payload、v3 initial prompt 含真实 caps且不含 repair protocol、accepted/fallback 都无 schema downgrade 猜测。该观察不宣称Mimo实测不支持structured output，只证明unknown capability采用保守none。
2. 真实 DeepSeek（capability=`json_object`）运行；证明本仓库实际model/endpoint/options的outbound response format来自typed capability/request，provider/model/response identity与canonical terminal一致，并记录官方文档依据与实际response/empty-content/provider-error结果。当前catalog无json_schema row，因此不虚构real json_schema observation。
3. F11 #59 必须只经 public Host Tool Trace resolver 与 analysis JSON/Markdown观察；再用 canonical EventLog/manifest 做 equality oracle，不允许报告代码旁路读取后伪装为 public output。
4. fresh v3 至少观察：`session_summary:null` clear、五类业务语义 persistence、rolling correction replacement、Host-derived omitted、cap-constrained memory replacement、bounded same-boundary repair、budget-exhausted fallback、single terminal、reconnect后 Memory/RunInput同源。rolling correction replacement 的required evidence精确为：新口径/current replacement provenance被retained；旧口径source labels出现在Host-derived omitted；compact artifact、Memory、post-compact RunInput与跨进程reconnect均不再包含旧结论。不得要求或生成subjective `superseded` reason。
5. 对每个 attempt 保存 proposal manifest ref/digest、operation/attempt/Engine run binding；mismatch injection 只可在 deterministic owner tests，不污染真实 evidence。
6. 扫描 screen/log/report/Tool Trace/evidence 全树中的 credential exact values、Authorization/Bearer/API-key patterns；报告扫描文件数、secret sources 数与 0 finding。Host SQLite 中允许的受限 resolved credential snapshot 不得被复制到 evidence。
7. 报告明确 provider unavailable/rejection/timeout 与产品 contract failure；Mimo不可用时不能用 DeepSeek结果冒充 Mimo coverage，DeepSeek不可用也不能用 mock关闭 mandatory row。

### S5 — Oracle/registry、PR body 与最终状态收口

Prerequisite：S4 已完成所有可执行mandatory observation、报告缺失/失败分类且secret scan通过。S5不等待未来Oracle controller adjudication；它可以完成implementation/evidence closeout，但不得把replacement scenarios、registry readiness或Oracle readiness宣称为accepted/ready。

Allowed files：

- `docs/cli_ci_oracles.json`
- `docs/cli_ci_scenarios.json`
- `docs/cli_ci.md`（仅同步当前 registry 使用说明/版本关系）
- `docs/reviews/wu-interactive-memory-postfix-readiness.md`（只补最终 status、new evidence refs/digests 与用户 adjudication identity）
- 新的 S5 implementation/review/closeout artifacts
- PR 190 body（仅在该 gate acceptance 后通过 GitHub 更新；不是 repository file）

Registry lifecycle delta固定为“保留旧内容、更新生命周期、追加fresh replacement”：

1. 旧`cli.interactive.core-execution@1`只把`status`改为`superseded`并设置`superseded_by="cli.interactive.core-execution@2"`；既有predicates、authority、observed evidence与user adjudication原文不改。
2. append `cli.interactive.core-execution@2`，`status="accepted"`、`supersedes="cli.interactive.core-execution@1"`；authority basis必须记录用户在`2026-08-05`明确确认F11/F12新design contract。v2保留仍有效predicate的稳定`predicate_id`，并就地替换`interactive.29-compactor-output-accept-repair-fallback`与`interactive.30-compaction-semantic-memory-closure`中model-produced ledger/policy_limit要求为fresh v3 Host-owned omission/cap/repair/public trace contract。
3. 旧`interactive.interactive.g06.tool-trace-formal@1`、`drop-superseded@1`、`drop-policy-limit@1`只把`status`改为`superseded`并分别设置`superseded_by`到以下fresh scenario；旧required evidence、observed evidence、user adjudication与coverage claims不改。
4. append `interactive.interactive.g06.tool-trace-formal@2`，`supersedes="interactive.interactive.g06.tool-trace-formal@1"`，required evidence为public resolver/analysis response identity与canonical equality/secret scan。
5. append `interactive.interactive.g06.rolling-correction-replacement@1`，`supersedes="interactive.interactive.g06.drop-superseded@1"`；required evidence固定为retained current replacement provenance + Host-derived omitted old labels + artifact/Memory/RunInput/reconnect无旧结论，不要求subjective reason。
6. append `interactive.interactive.g06.cap-constrained-memory-replacement@1`，`supersedes="interactive.interactive.g06.drop-policy-limit@1"`；required evidence固定为真实caps输入、Host cap/usage audit、accepted provenance/omitted complement、repair/fallback与reconnect同源，不要求`policy_limit` reason。
7. 三个fresh scenario在S4 observation后：mandatory evidence完整则`status="unadjudicated"`；仍有真实证据缺口则`status="needs-more-evidence"`并记录gap owner。它们在后续Oracle controller用户裁决前绝不标`accepted`；这不阻塞本work unit的implementation/evidence final closeout。
8. 两个registry顶层继续为`calibration`；S5/PR body/readiness artifact分别报告`implementation=PASS|FAIL`、`real_observation=complete|partial`、`oracle=pending`，不得合并为单一ready。

Stable predicate resolution contract：当前direct query显示有611个scenario records的`accepted_oracle_refs`历史指向`core-execution@1`，共768个`oracle_predicate_refs`、29个unique stable predicate ids。不得批量改写611个frozen scenario的历史`accepted_oracle_refs`；该字段保留“裁决时依据版本”。当前verdict必须对每个`oracle_predicate_refs`按stable predicate id连接到**唯一**`status=accepted`且未被supersede的oracle version，因此core@1 superseded后全部当前解析自然落到core@2。S5 validation必须证明611条记录的768个refs各命中恰好一个current accepted predicate，0 dangling、0 duplicate current owner；不得按旧accepted_oracle_refs继续执行superseded contract。

Removed-ledger dependency scan：实施时扫描所有scenario的`required_evidence`、`correctness_surfaces`、`coverage_claims`、`precondition`、`invocation`与所有oracle predicates。当前代码真源已确认直接依赖removed ledger的scenario只有`drop-superseded@1`与`drop-policy-limit@1`；oracle predicate只有稳定ids`interactive.29-compactor-output-accept-repair-fallback`和`interactive.30-compaction-semantic-memory-closure`含represented/explicit-drop、四reason或policy_limit语义。`tool-trace-formal@1`因F11 public response projection版本化而supersede，不属于removed-ledger依赖。若S5 scan发现其它直接依赖，必须列入artifact并为其建立明确replacement/lifecycle，不能静默保留accepted unsatisfiable contract。

PR body 更新必须列出 accepted commits、new evidence run/report/digests、secret scan、registry replacements、full validation、implementation/observation/oracle三态与residual risks；不得把oracle pending写成ready，不得 mark ready、merge、approve 或请求 reviewer。PR body gate 后执行 `gh pr view 190` 回读校验正文与目标 PR。若后续Oracle controller拒绝某项观察，另开明确owner的follow-up WU；不回写本WU已经完成的implementation/evidence事实。

## Review, fix, re-review, and commit protocol

S0-S5 每个 slice 都执行以下固定闭环，不得合并或省略：

1. implementation agent 只改该 slice allowed files并产出 implementation artifact；
2. Reviewer A 独立做 correctness/state-machine/error-path review；
3. Reviewer B 独立做 architecture/semantic-ownership/LLM-facing/typing/test-gap review；
4. controller 逐 finding 以 direct code/data evidence 裁决；有 accepted finding 时由 implementation owner修复；
5. A、B 对修复后的完整 slice 独立 re-review；两路均明确 accepted 才可形成 slice acceptance artifact；
6. accepted 后只 stage slice intended files，检查 staged diff，再 commit；push 仅在 Gateflow 对应 accepted checkpoint允许时执行；
7. 任一 reviewer 与 implementation agent 不得互相代签，不能用 aggregate review 代替 slice review。

所有 slice accepted 后仍必须运行一次 `$deepreview` aggregate review；finding 修复后 re-review accepted。随后必须执行 PR-level review（包括完整 PR diff、PR body、commits/checks）；aggregate deepreview 与 PR review 是两个不同 gate，均不得省略。最后才可进入 final closeout；本 plan gate 不执行其中任何一步。

## Validation and coverage matrix

### Per-slice minimum

- S0：design link/term scan、`git diff --check`。
- S1：上述 5 个 Tool Trace/context event test files；modified production modules 单文件 coverage 均 `>=80%`。
- S2：Engine contracts/agent/OpenAI payload、runtime config、Service assembly focused tests；modified production modules 单文件 coverage 均 `>=80%`。
- S3：全部 listed Host compact tests、runtime/service assembly tests、publication manifest tests；modified production modules 单文件 coverage 均 `>=80%`。
- S4：harness deterministic tests先通过，再运行真实 provider；evidence digest、secret scan、public/canonical equality检查通过。
- S5：`python -m json.tool`/typed registry loader、scenario inventory、supersedes graph无环/无dangling ref、旧entry除`status/superseded_by`外内容digest preservation、611 records/768 predicate refs唯一current accepted owner、removed-ledger全registry scan、文档链接检查。

### Mandatory aggregate commands

```bash
source .venv/bin/activate
pytest tests/contracts tests/cli tests/documents tests/fins tests/tools tests/host tests/runtime tests/service tests/engine -q
python -m pyright dayu/ tests/ utils/
git diff --check
git status --short
```

Coverage 使用 `coverage run --branch -m pytest <slice focused tests>` 与 `coverage report --include='<modified production files>'`；任一修改生产文件低于 80% 时补 owner-level tests，不通过 `# pragma: no cover`、ignore 或宽泛 integration 覆盖掩盖。

Hash 更新顺序固定：先稳定 `models.json` 与两个 compactor prompt assets，逐个计算 raw-byte SHA-256并更新 `docs/cli_init_workspace_manifest_v1.json` 对应 entries；保存 manifest 后重算其 SHA-256并只更新 `tests/cli/test_smoke_cli_init_provider_matrix.py::FROZEN_MANIFEST_SHA256`；随后由真实 init publication tests复核。不得更新历史 artifact 中记录的旧 digest。

## Invariants and stop conditions

- Host 生命周期、attempt budget、canonical terminal 与 fallback 仍是强约束真源；Engine 不持久化、不治理 compaction。
- F11 只能读取 canonical event + proposal manifest graph；任何 mismatch 都 fail closed，任何缺失都显式标 unavailable/limitation。
- F11 canonical terminal scan只允许每页有界的keyset exhaustion；不得加入任意总页数cap，不得把cursor不推进、未完整exhaustion或损坏page降格为missing/limitation。
- F12 的模型语义、Host coverage、cap/usage audit、artifact、Memory、RunInput 只能从一个 `CompactAcceptedTruthV3` 派生。
- initial 与 repair 请求必须可通过实际 captured runner input证明，不用源文件文本猜测最终 prompt。
- request/source-boundary digest只属于Host binding/audit/serialization，绝不进入LLM-facing initial/repair消息。
- 不新增 `Any`/`object`/无类型签名、`hasattr/getattr`、lazy import、extra payload、provider-name猜测、兼容 alias/re-export/wrapper。
- 发现需要修改 slice allowed-files 之外的 production contract时立即返回 plan gate；不得“顺手”扩 scope。
- durable input digest 意外变化、工作树出现不明 overlapping edits、真实 evidence 缺 mandatory provider、secret scan非零、focused/full tests或 pyright失败时不得声明 ready。

## README decisions

- S1/S3 修改 `dayu/host/`，必须核对并更新 `dayu/host/README.md` 中已经落地的 public Tool Trace、compact v3、repair与Memory projection contract；不写未来计划。
- S2 修改 `dayu/engine/`，必须更新 `dayu/engine/README.md` 的 `AgentRunRequest -> AsyncRunner.call -> provider payload` structured-output public contract。
- S2/S3 修改 `dayu/config/`，必须更新 `dayu/config/README.md` 的 required model capability field、inheritance与 compactor prompt职责。
- tests 的新增 owner/harness职责若超出现有说明，更新 `tests/README.md`；只增加同层断言则不机械更新。
- `dayu/README.md` 只有在最终代码形成新的跨层 stable request flow时更新；预计 structured-output 显式 request值得补一条跨层摘要，但不得展开 Host内部机制。
- 根 `README.md` 无用户可见命令、参数、workspace位置、输出通道或排障流程变化，判定不更新。

## Open questions

Blocking open questions：无。以下已由 Goal Confirmation 冻结，不再作为实现时自由选择：

- Mimo=`none`，DeepSeek=`json_object`，其它未证明 model=`none`；不为了展示功能擅自标 `json_schema`。
- omitted 是 Host 对 immutable boundary 与 accepted provenance 的补集审计，不携带模型主观 reason。
- registry采用新version/replacement entry；旧contract内容冻结，只允许按`docs/cli_ci.md`更新`status/superseded_by`生命周期。
- core-execution@2由用户2026-08-05 design-contract裁决直接accepted；三个replacement scenarios在新evidence后仍为unadjudicated或needs-more-evidence，Oracle controller未来裁决不阻塞implementation/evidence closeout。
- S3保持单一accepted原子vertical migration；只在未提交worktree中按固定内部顺序迭代，失败时丢弃该slice intended diff回S2 accepted commit。
- DeepSeek是否在当前temperature/stream/options组合下稳定返回JSON由S4真实观察回答；官方capability只授权发送json_object，不替代运行证据。
- Mimo未来若取得structured-output直接能力证据，只需后续独立catalog配置变更；本WU不加入probe机制或预留provider分支。
- Oracle controller未来若拒绝replacement observation，创建follow-up WU处理其明确finding；不倒推本WU已验证的implementation事实，也不把scenario标accepted。

## Residual risks

1. 没有 schema enforcement 的 Mimo 仍可能频繁产生 malformed output；这是预期 provider capability限制，必须由 strict parser、bounded repair/fallback和真实失败率证据呈现，不能静默升级或降级。
2. Host-derived omission不证明被省略内容“业务上不重要”；它只证明模型未通过 accepted provenance代表该 source。真实 rolling/cap behavior仍需要 Agent-in-the-loop证据和用户裁决。
3. fresh artifact schema不支持旧compact contract、schema-3 artifact与依赖它们的旧Session replay；本work unit不做migration/compatibility，但不声称整个旧DB bootstrap必然失败。若产品发布要求旧compact history升级，必须另立migration work unit。
4. Tool Trace analysis schema v2 会改变下游 JSON consumers；本仓库 owner tests与 README可关闭已知消费者，仓外消费者风险只能在 PR body中明确。
5. 真实 provider输出和可用性有外部波动；mandatory row缺失不能由 deterministic test或另一 provider替代。
6. Mimo=`none`是unknown capability的保守配置，不是“不支持”的实测结论；未来有直接能力证据时由独立catalog change处理。
7. S3原子vertical migration的review surface较大；通过固定内部顺序、未提交diff回滚、两路独立review与aggregate deepreview缓解，分类为本work unit内已接受工程风险。
8. replacement scenarios在本WU结束时仍可能是unadjudicated/needs-more-evidence；owner是后续Oracle controller，不影响implementation/evidence事实，但registry readiness必须保持pending。

## Why this is not over-designed

- F11复用既有canonical terminal、manifest parser与EventLog keyset reader，只增加缺失的public typed projection；没有第二EventLog、缓存或推断器。
- F12删除模型无法严格履约的ledger而非增加semantic classifier；`CompactOutputCapsV3`只是跨边界immutable projection，数值owner仍只有`MemoryProjectionPolicy`。
- `compact_structure.py`只解决用户明确要求的template/schema/parser结构同源，不承载domain dataclass、governance、persistence或transport。
- Engine只提供三值generic capability与显式request；当前catalog不虚标json_schema，不增加provider probe、fallback router或provider-name分支。
- S3保持一个原子accepted migration是为了避免双owner/半schema；风险通过worktree内部顺序、未提交diff回滚与两路review处理，不用兼容代码换取表面小commit。

## Completion report format

每个slice artifact与最终closeout至少报告：实际changed files；实现的owner/contract；focused/full tests、单文件coverage与pyright结果；README/design/hash决策；两路review及finding状态；new evidence/provider/secret-scan状态；registry lifecycle与oracle pending状态；residual risks及owner；accepted commit hash。最终报告必须把`implementation`、`real observation`、`oracle readiness`三态分列，不能用一个“ready”概括。

## Readiness decision

- Plan readiness：**PASS（controller fix complete）**。两份review的全部finding/open question已有裁决与plan delta；目标、owner、类型、call/data flow、state machine、allowed files、error paths、fresh persistence、hash/init assets、README、tests/coverage/pyright/full suite、real-provider evidence、secret scan、registry、PR body与commit gates均已冻结，足以进入plan re-review。
- Implementation readiness：**FAIL（按 gate 顺序预期）**。尚未完成两路plan re-review acceptance；不得开始实现。
- Conformance/registry readiness：**FAIL**。F11/F12尚未实现，新real-provider evidence与三个replacement scenario的用户adjudication尚不存在；旧frozen evidence不能关闭新contract。core-execution@2的design authority已由用户在2026-08-05确认，但不等于scenario readiness。
- Final closeout readiness：**FAIL**。slice reviews、accepted commits、aggregate deepreview、PR review、PR body回读与implementation/evidence closeout尚未完成；未来Oracle controller可保持pending，不是本work unit final closeout的前置。
