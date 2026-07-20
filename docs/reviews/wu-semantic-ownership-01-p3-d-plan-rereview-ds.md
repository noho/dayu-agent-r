# WU-SEMANTIC-OWNERSHIP-01 P3-D Plan Re-Review — AgentDS

## Scope

- **Review type**: Plan-fix re-review (gate: plan-rereview → implementation-ready)
- **Work unit**: `WU-SEMANTIC-OWNERSHIP-01 / P3-D`
- **Revised plan**: `docs/host/wu-semantic-ownership-01-p3-d-engine-provider-protocol-normalization-plan.md`
- **Original plan reviews**: `docs/reviews/wu-semantic-ownership-01-p3-d-plan-review-mimo.md`, `docs/reviews/wu-semantic-ownership-01-p3-d-plan-review-ds.md`
- **Controller adjudication**: `docs/reviews/wu-semantic-ownership-01-p3-d-plan-review-controller-adjudication.md`
- **Fix artifact**: `docs/reviews/wu-semantic-ownership-01-p3-d-plan-fix-codex.md`
- **Reviewer**: AgentDS (re-review)
- **Date**: 2026-07-10
- **Output file**: `docs/reviews/wu-semantic-ownership-01-p3-d-plan-rereview-ds.md`
- **Included scope**: Revised plan text, fix artifact claims, all 12 P3-D-PF items
- **Excluded scope**: Production code, test code, implementation verification, other P3 sub-work-units
- **Verification method**: Direct plan-text evidence cross-referenced against each PF requirement from controller adjudication

## Verdict

**PASS** — 所有 12 项 P3-D-PF 均已在修后 plan 中闭合。Plan 具备代码生成就绪条件，无阻塞性问题。无新增 finding。

---

## PF-by-PF Verification

### P3-D-PF-01 — Host diagnostic event contract — CLOSED

**Controller 要求**: 命名 EventLog event_type、选择 EventClass、决定是否复用 `_EVENT_TYPE_ENGINE_EVENT_DIAGNOSTIC`、明确 engine_ingest dispatch、Tool Trace / read_api / outbox / memory 投影行为、design doc 更新范围。

**修后 plan 直接证据**:

| 要求 | Plan 位置 | 证据 |
| --- | --- | --- |
| EventLog event_type 命名 | line 222 | `PROVIDER_DIAGNOSTIC`，`EventClass.DIAGNOSTIC` |
| 不复用 fatal event type | line 223 | 明确不复用 `_EVENT_TYPE_PROVIDER_PROTOCOL_ERROR`；默认新 `_EVENT_TYPE_PROVIDER_DIAGNOSTIC`；不复用 `_EVENT_TYPE_ENGINE_EVENT_DIAGNOSTIC` 除非实现证明可区分 |
| engine_ingest dispatch | line 224 | 持久化 bounded payload（diagnostic_code/severity/message/provider_request_id/diagnostic_source/payload_ref/payload_digest），不更新 Run/Attempt 终态，不写 failure metadata |
| Tool Trace 行为 | line 225 | 加入 diagnostic event allowlist，仅用于 diagnostic display；不转为 failure_kind/provider_error_code/terminal failure metadata |
| read_api 行为 | line 226 | 投影为 activity，复用或扩展 `HostActivityKind.PROVIDER_DIAGNOSTIC`；title/summary 标识为非致命，不暗示 run failure |
| outbox 行为 | line 227 | `EventClass.DIAGNOSTIC` 被现有 terminal canonical-fact outbox filter 自动排除；要求新增或更新测试证明不被 emit |
| memory/evidence/compact 排除 | line 111 | Memory、final answer、accepted evidence material、compact material、prompt assembly 不得消费 provider diagnostic payloads；S2/S3 验证必须 scan 这些路径 |
| design doc 更新 | lines 247-257 | 列出 `docs/engine/design.md`、`docs/host/design.md`、`dayu/engine/README.md`、`dayu/host/README.md`、`tests/README.md` 各需更新的具体 section |

**判定**: CLOSED。所有子要求均有明确 plan 文本支撑，无歧义。

---

### P3-D-PF-02 — Context-overflow provenance 完整链路 — CLOSED

**Controller 要求**: 追踪 typed `ContextOverflowDetection` 从 `error_classifier.py` → `runner.py` → `_AttemptFailedTerminal` 或 `RunnerHTTPErrorData` → Agent → Engine diagnostic → Host diagnostic → `context_compaction_requested`；`runner.py` 必须列入 candidate file；测试验证 marker-fallback provenance 到达 diagnostic 而不成为 business truth。

**修后 plan 直接证据**:

| 要求 | Plan 位置 | 证据 |
| --- | --- | --- |
| error_classifier.py 返回 typed result | line 232 | "Refactor context-overflow detection to return a typed result, for example `ContextOverflowDetection(kind=STRUCTURED_CODE \| MESSAGE_MARKER_FALLBACK \| NOT_OVERFLOW, diagnostic=...)`, rather than a bare bool." |
| runner.py 打包进异常/数据 | line 233 | "runner.py stores it in `_AttemptFailedTerminal` or directly in `RunnerHTTPErrorData.context_overflow_detection`" |
| Agent 读取并投影 | line 233 | "Agent reads that field when consuming `RunnerHTTPErrorData`; Agent emits `context_compaction_requested` only from typed `RunnerHTTPErrorCode.CONTEXT_LENGTH_EXCEEDED`; if provenance is `MESSAGE_MARKER_FALLBACK`, Agent also emits a non-fatal Engine provider diagnostic before terminal closeout" |
| Host 持久化 | line 233 | "Host persists that diagnostic as `PROVIDER_DIAGNOSTIC`" |
| runner.py 列入 candidate file | line 200 | `dayu/engine/runners/openai/runner.py` 在 S2 candidate files 列表中 |
| 测试验证不成为 business truth | line 234 | "the same run must have canonical `CONTEXT_COMPACTION_REQUESTED` from typed HTTP code, a non-fatal `PROVIDER_DIAGNOSTIC` with source `message_marker_fallback`, no raw marker text in memory/final answer/evidence/compact prompt material, and no diagnostic-driven status transition" |

**判定**: CLOSED。完整 provenance 链路已逐段描述，`runner.py` 已列入 candidate file，测试要求覆盖 marker-fallback 不作为 business truth 的验证。

---

### P3-D-PF-03 — Log-only adapter warnings 与 RunnerProtocolErrorData warnings 区分 — CLOSED

**Controller 要求**: 拆分当前来源为 tool-call aggregation 中已有的 `RunnerProtocolErrorData` warnings 和 log-only warnings（malformed usage、missing content type）；显式覆盖流式和非流式 missing content type；包含 `usage.py` 或精确 parser 调用点为 candidate file。

**修后 plan 直接证据**:

| 要求 | Plan 位置 | 证据 |
| --- | --- | --- |
| 两类来源拆分 | lines 227-229 | 明确两组："existing `RunnerProtocolErrorData` warnings from tool-call aggregation, such as unknown provider namespace/key, must become non-fatal Runner diagnostics" 和 "current log-only adapter warnings, such as malformed usage in `sse_parser.py`/`non_stream_parser.py` and missing `Content-Type` in `runner.py`, must start emitting typed non-fatal diagnostics" |
| 流式和非流式 Content-Type | line 230 | "Missing `Content-Type` diagnostics must cover both streaming and non-streaming HTTP 200 responses. Streaming may still use the existing SSE fallback; non-streaming must keep the JSON parse path but emit a diagnostic for the missing/empty header." |
| usage.py 列入 candidate file | line 202 | `dayu/engine/runners/openai/usage.py` 在 S2 candidate files 中 |
| 传播分析表区分 | line 100 | 传播分析表 non-fatal provider diagnostic 行明确："Some tool-call warnings are currently stored as `RunnerProtocolErrorData`; usage malformed and missing content type are currently log-only warnings." |
| source scan 覆盖 | lines 242-244 | `rg -n "runner\.http\.missing_content_type\|usage_field_malformed" dayu/engine/runners/openai` |

**判定**: CLOSED。两类来源已明确拆分，流式/非流式 Content-Type 均已覆盖，`usage.py` 已列入 candidate file。

---

### P3-D-PF-04 — SSE/non-stream multi-choice 语义分离 — CLOSED

**Controller 要求**: 分别定义流式 chunk 拒绝时机、"valid assistant choice"、usage-only empty-choice 语义、非流式响应语义；测试覆盖非流式 multi-choice、SSE multi-choice chunk、empty-choice usage-only chunk、empty delta + valid delta、conflicting content/tool-call choices。

**修后 plan 直接证据**:

| 要求 | Plan 位置 | 证据 |
| --- | --- | --- |
| SSE 与 non-stream 分离 | lines 115-116 | Contract Decision #1 标题为 SSE multi-choice policy；Contract Decision #2 标题为 Non-stream choice policy。两条独立定义 |
| SSE 拒绝时机 | line 147 | "validate choices inside `_handle_chunk_object()` before merging content/tool state. Reject immediately when..." |
| Non-stream 拒绝时机 | line 148 | "validate response-level `choices` before selecting a choice. Reject missing/non-list/empty/multi-choice responses and explicit non-zero `index`" |
| valid assistant choice 定义 | line 115 | "A valid assistant choice is a choice object whose `delta` contains at least one non-null semantic field used by the adapter, such as `role`, `content`, `reasoning_content`, `tool_calls`, or `finish_reason`; an object with empty `delta={}` and no `finish_reason` is not a valid assistant choice but still counts as malformed if it carries a non-zero `index` or invalid shape." |
| usage-only empty-choice 语义 | line 115 | "A usage-only SSE chunk with `choices=[]` and valid usage remains legal" — 明确 scope 为 SSE |
| 测试覆盖 | lines 157-162 | 列出：non-stream multi-choice rejection、SSE multi-choice chunk immediate rejection、SSE usage-only chunk valid、SSE empty-delta + valid delta rule、conflicting content/tool-call choices fatal |

**判定**: CLOSED。SSE 和 non-stream 语义已完全分离，valid assistant choice 已明确定义，测试矩阵覆盖所有要求的边界场景。

---

### P3-D-PF-05 — Finish_reason 非字符串/空/null/缺失/冲突全覆盖 — CLOSED

**Controller 要求**: 明确 unknown non-empty string、non-string values、empty string、null/missing、cross-chunk conflicting finish reasons 的行为；增加显式负向测试。

**修后 plan 直接证据**:

| 要求 | Plan 位置 | 证据 |
| --- | --- | --- |
| unknown non-empty string | line 117 | "Unknown non-empty strings... are fatal provider protocol errors" |
| non-string values (bool, number, array, object) | line 117 | "non-string non-null values, empty strings, arrays, objects, and booleans are fatal provider protocol errors" |
| empty string | line 117 | "empty strings... are fatal" |
| null/missing | line 117 | "`null` and missing `finish_reason` are treated as absent, not as `STOP`" |
| cross-chunk conflict | line 117 | "Cross-chunk conflicting terminal finish reasons are fatal" |
| 负向测试列表 | lines 163-167 | 逐项列出：unknown non-empty fatal、non-string (int, bool, array, object) fatal、empty-string fatal、null/missing as absent（独立于 unknown string 测试）、conflicting terminal fatal |

**判定**: CLOSED。所有 finish_reason 边界值均已明确行为，负向测试列表完整。

---

### P3-D-PF-06 — S1/S2 依赖与中间态描述 — CLOSED

**Controller 要求**: 显式声明 S2 depends on S1；描述 S1 后 S2 前 unknown finish_reason 的中间 fatal 状态。

**修后 plan 直接证据**:

| 要求 | Plan 位置 | 证据 |
| --- | --- | --- |
| 显式依赖声明 | line 184 | "S2 depends on S1." |
| 中间态描述 | lines 184-185 | "After S1 and before S2, invalid/unknown `finish_reason` is already fatal but still travels through the existing fatal provider-protocol error path. S2 only splits remaining non-fatal diagnostics from fatal protocol errors; it must not reclassify invalid `finish_reason` back into a warning." |

**判定**: CLOSED。依赖关系已显式声明，中间态行为已清楚描述，且明确 S2 不得将已 fatal 的 finish_reason 重新归类为 warning。

---

### P3-D-PF-07 — S3 原子性论证 — CLOSED

**Controller 要求**: 拆分 S3 或提供显式原子性论证。

**修后 plan 直接证据**:

| 要求 | Plan 位置 | 证据 |
| --- | --- | --- |
| 原子性论证 | lines 268-269 | "The public dataclass field type change touches Engine contracts, Agent constructors, Engine run outcomes, Host ingest, Host read projections, Tool Trace, outbox/public events, tests, docs, and source-scan guard in one semantic contract. The project forbids compatibility facades, old aliases, and old string-only constructors; splitting contract typing from all in-repo callers would require either a compatibility layer or a temporarily broken main branch." |
| 非目标明确 | lines 273-275 | 明确不做 fake global enum、不做 Host 按 provider-specific code 分支、不做兼容 wrapper |

**判定**: CLOSED。原子性论证充分：类型变更跨 contract-behavior-docs 三层，项目禁止兼容 facade，拆分会导致临时 broken main branch 或被迫引入兼容层。论证基于项目实际约束，合理。

---

### P3-D-PF-08 — Error-code 传播矩阵与完整 source scan — CLOSED

**Controller 要求**: 包含当前静态传播矩阵；扫描覆盖 `EngineRunOutcomeFailed(...)`、`RunFailedData(...)`、`ProviderProtocolErrorData(...)`、`RunnerProtocolErrorData(...)`、`engine_ingest.py`、`read_api.py`、`tool_trace.py`、outbox/public events、`provider_error_code` 和 `failure_metadata`。

**修后 plan 直接证据**:

| 要求 | Plan 位置 | 证据 |
| --- | --- | --- |
| 当前静态传播分析 | lines 97-103 | 5 行传播分析表：fatal protocol error code、non-fatal diagnostic、context-overflow classification、Engine-owned run failure code、provider/runner extension code。每行列出当前 producer/transition 和当前 durable/projection consumer |
| S3 传播矩阵 | lines 316-327 | 10 行矩阵：RunnerProtocolErrorData、ProviderProtocolErrorData、RunFailedData、EngineRunOutcomeFailed、Agent constants/constructors、Host ingest、Read API、Tool Trace、outbox/public events、memory/compact/evidence。每行列当前 shape 和 S3 action |
| source scan 覆盖 EngineRunOutcomeFailed | line 338 | `rg -n "RunFailedData\(\|EngineRunOutcomeFailed\(\|ProviderProtocolErrorData\(\|RunnerProtocolErrorData\(" dayu/engine tests/engine` |
| source scan 覆盖 Host consumers | line 339 | `rg -n "error_code\|provider_error_code\|failure_metadata" dayu/host/engine_ingest.py dayu/host/read_api.py dayu/host/tool_trace.py dayu/host/outbox.py tests/host` |
| source scan 覆盖 provider_error_code | line 341 | `rg -n "_ERROR_\|runner_error_done_without_detail\|context_compaction_required\|provider_error_code" dayu/engine dayu/host tests` |

**判定**: CLOSED。传播矩阵覆盖所有构造点和 Host 消费端，source scan 已扩展到 `EngineRunOutcomeFailed` 和所有 Host consumer 文件。

---

### P3-D-PF-09 — Weak-typing guard 具体化 — CLOSED

**Controller 要求**: 明确 guard 机制（test/script/source scan/CI command）和确切失败条件。

**修后 plan 直接证据**:

| 要求 | Plan 位置 | 证据 |
| --- | --- | --- |
| 机制指定 | line 308 | "Minimum acceptable mechanism: a checked-in pytest or validation script invoked by tests/CI" |
| 失败条件 1 | line 309 | "`error_code: str` in `dayu/engine/contracts/`" |
| 失败条件 2 | line 310 | "`RunFailedData(`, `EngineRunOutcomeFailed(`, `ProviderProtocolErrorData(`, or `RunnerProtocolErrorData(` with literal string `error_code="..."`" |
| 失败条件 3 | line 311 | "Host consumers reading typed Engine error-code objects without calling the serializer at ingest/public projection boundary" |

**判定**: CLOSED。Guard 机制已具体化为 pytest/validation script + CI 调用；三个确切失败条件覆盖 contract 定义、构造点、Host 消费端。

---

### P3-D-PF-10 — RunnerSpecificErrorCode empty/serialization 语义 — CLOSED

**Controller 要求**: 定义空值 fail-closed 或 fallback、wrapper shape、bounded validation、source field、单一 durable/public 序列化格式。

**修后 plan 直接证据**:

| 要求 | Plan 位置 | 证据 |
| --- | --- | --- |
| wrapper shape | line 303 | `RunnerSpecificErrorCode(value: str, source: RunnerSpecificErrorSource)` |
| bounded validation | line 304 | "trim and validate non-empty bounded text; reject whitespace-only and overly long values" |
| 空值 fail-closed | line 304 | "Explicit empty provider/runner codes fail closed at the producer" |
| 缺失 fallback | line 304 | "Missing provider detail must use an Engine-owned fallback enum value, not an empty wrapper and not a fabricated provider code" |
| 单一序列化 helper | line 305 | "serialize only through the shared helper" |
| Contract Decision 详细定义 | line 121 | "validates trimmed non-empty bounded text, for example 1-128 characters, and a closed source enum such as `RUNNER_PROTOCOL`, `HTTP_PROVIDER`, or `ADAPTER`" |
| 序列化 helper 命名 | line 121 | "`serialize_engine_error_code(code) -> str`, not ad hoc `.value` or raw strings scattered through consumers" |
| 测试覆盖 | line 335 | "valid provider-specific value serializes once; empty string and whitespace-only values are rejected; missing provider detail uses an Engine enum fallback; overly long values are rejected; Host durable JSON contains the serializer output, not a dataclass repr" |

**判定**: CLOSED。Wrapper shape、validation、empty fail-closed、fallback、序列化 helper 和测试要求均已完整定义。

---

### P3-D-PF-11 — Design/README 更新范围 section-specific — CLOSED

**Controller 要求**: 列出每个 doc 可能触及的具体 section。

**修后 plan 直接证据**:

| 要求 | Plan 位置 | 证据 |
| --- | --- | --- |
| S2 docs/engine/design.md | line 253 | "update `docs/engine/design.md` RunnerEvent and EngineEvent tables/sections that describe fatal protocol errors and diagnostics" |
| S2 docs/host/design.md | line 254 | "update `docs/host/design.md` EngineEvent ingest and diagnostic/canonical matrix sections to add `PROVIDER_DIAGNOSTIC`, state `EventClass.DIAGNOSTIC`, and state outbox/memory exclusion" |
| S2 dayu/engine/README.md | line 255 | "update `dayu/engine/README.md` only if its contract overview documents Runner/Engine events or provider adapter behavior" |
| S2 dayu/host/README.md | line 256 | "update `dayu/host/README.md` only if its Agent update constraints say diagnostic projection or EventLog mapping belongs there" |
| S2 tests/README.md | line 257 | "update `tests/README.md` if new contract tests, Host projection tests, or source-scan validation rules become part of the test organization" |
| S3 docs/engine/design.md | line 349 | "update `docs/engine/design.md` EngineEvent/Agent run outcome sections that name `RunFailedData`, `ProviderProtocolErrorData`, or runner protocol error data" |
| S3 docs/host/design.md | line 350 | "update `docs/host/design.md` EngineEvent ingest and Host terminal payload sections only if they describe `error_code` / `provider_error_code` source semantics" |
| S3 dayu/engine/README.md | line 351 | "update `dayu/engine/README.md` if it documents public contract exports or Engine failure code semantics" |
| S3 dayu/host/README.md | line 352 | "update `dayu/host/README.md` if it documents Host diagnostic/terminal payload behavior" |
| S3 tests/README.md | line 353 | "update `tests/README.md` if the weak-typing guard is added as a test/scenario class" |

**判定**: CLOSED。S2 和 S3 均列出每个 doc 的具体 section/topic；条件性更新（"only if"）避免了机械同步。

---

### P3-D-PF-12 — No-LLM-facing diagnostic leakage 验证 — CLOSED

**Controller 要求**: 增加验证 scan/test 确保 provider diagnostics 不进入 memory、final answer、accepted evidence material、compact material 或 LLM-facing prompts。

**修后 plan 直接证据**:

| 要求 | Plan 位置 | 证据 |
| --- | --- | --- |
| Non-goal 声明 | line 35 | "Do not expose provider diagnostic internals to LLM-facing messages." |
| Owner boundary 声明 | line 79 | "LLM-facing messages must not contain provider diagnostic internals." |
| Host consumer notes | line 111 | "Memory, final answer, accepted evidence material, compact material, and prompt assembly must not consume provider diagnostic payloads. S2/S3 validation must scan these paths and add tests or assertions where a projection path exists." |
| S2 测试验证 | line 234 | "no raw marker text in memory/final answer/evidence/compact prompt material, and no diagnostic-driven status transition" |
| S3 传播矩阵 | line 327 | "Add validation that typed error codes and provider diagnostics do not enter LLM-facing material except through approved user-visible terminal summaries." |
| Validation Summary 具体 scan | lines 370-373 | 两个具体 `rg` 命令：`rg -n "PROVIDER_DIAGNOSTIC\|message_marker_fallback\|provider diagnostic\|provider_diagnostic" dayu/config dayu/host dayu/engine tests` 和 `rg -n "memory\|compact\|evidence\|prompt\|FINAL_ANSWER\|final_answer" dayu/host dayu/engine tests`；要求 "explain any hits as internal diagnostics only or fix them" |
| Explicit Prohibitions | line 391 | "Do not put provider diagnostics into memory, final answer, evidence material, or LLM-facing prompt text." |

**判定**: CLOSED。从 Non-goal、Owner boundary、Host consumer notes、S2 测试、S3 传播矩阵、Validation Summary scan 到 Explicit Prohibitions，no-LLM-facing diagnostic leakage 约束在 plan 中形成了多层防护。Validation Summary 中的具体 scan 命令使约束可验证。

---

## 专项验证

### Host PROVIDER_DIAGNOSTIC / EventClass / ingest / Tool Trace / read_api / outbox / memory exclusion

- **EventLog event_type**: `PROVIDER_DIAGNOSTIC`（line 222）
- **EventClass**: `DIAGNOSTIC`（line 222）
- **engine_ingest dispatch**: 新增 `_EVENT_TYPE_PROVIDER_DIAGNOSTIC` handler，不更新 Run/Attempt 终态（line 224）
- **Tool Trace**: 加入 diagnostic allowlist，不转为 failure_kind（line 225）
- **read_api**: 复用或扩展 `HostActivityKind.PROVIDER_DIAGNOSTIC`，title/summary 不暗示 run failure（line 226）
- **outbox**: `EventClass.DIAGNOSTIC` 被现有 filter 自动排除；需新增测试证明（line 227）
- **memory/evidence/compact**: 明确不得消费 diagnostic payloads；S2/S3 验证必须 scan（line 111）

✅ 各项均计划清楚。

### Context-overflow provenance 完整链路

```
error_classifier.py (line 232: ContextOverflowDetection typed result)
  → runner.py (line 233: _AttemptFailedTerminal or RunnerHTTPErrorData.context_overflow_detection)
  → Agent (line 233: reads field, emits context_compaction_requested from typed HTTP code; if MESSAGE_MARKER_FALLBACK also emits non-fatal diagnostic)
  → Engine diagnostic (line 233: non-fatal provider diagnostic event)
  → Host PROVIDER_DIAGNOSTIC (line 233: persistence)
```

✅ 完整链路已逐段描述。`runner.py` 已列入 S2 candidate files（line 200）。

### Log-only warnings、SSE/non-stream choice policy、finish_reason 负面边界、S1/S2 依赖

| 专项 | Plan 位置 | 状态 |
| --- | --- | --- |
| log-only warnings 拆分 | lines 227-230 | ✅ 两类来源明确拆分；流式/非流式 Content-Type 均覆盖 |
| SSE choice policy | line 115 | ✅ 独立 Contract Decision #1；逐 chunk 即时拒绝 |
| Non-stream choice policy | line 116 | ✅ 独立 Contract Decision #2；响应级校验 |
| finish_reason 全边界 | line 117 | ✅ unknown non-empty string、non-string (bool/number/array/object)、empty string、null/missing、cross-chunk conflict 全部定义 |
| S1/S2 依赖 | lines 184-185 | ✅ 显式声明；中间态描述清楚；S2 不得重新分类 fatal finish_reason |

### S3 atomicity、error-code propagation matrix、source scans、weak typing guard、RunnerSpecificErrorCode wrapper、docs sections、no LLM-facing leakage

| 专项 | Plan 位置 | 状态 |
| --- | --- | --- |
| S3 原子性 | lines 268-269 | ✅ 基于项目禁止兼容 facade 的论证充分 |
| error-code propagation matrix | lines 316-327 | ✅ 10 行矩阵覆盖所有构造点和 Host 消费端 |
| source scans | lines 337-341 | ✅ 覆盖 EngineRunOutcomeFailed、Host consumers、provider_error_code、failure_metadata |
| weak typing guard | lines 308-311 | ✅ pytest/validation script + CI；3 个确切失败条件 |
| RunnerSpecificErrorCode wrapper | lines 121, 303-305 | ✅ shape、validation、empty fail-closed、fallback、serialization helper 完整 |
| docs sections | lines 247-257, 343-353 | ✅ S2/S3 各 doc 的 section-specific 更新范围 |
| no LLM-facing leakage | lines 35, 79, 111, 234, 327, 370-373, 391 | ✅ 多层防护，Validation Summary 含具体 scan 命令 |

---

## Open Questions

无。原始 AgentDS review 的 4 个 open question 已在修后 plan 中解决：

1. `_EVENT_TYPE_ENGINE_EVENT_DIAGNOSTIC` 复用问题 → plan line 223 明确默认不复用，新建 `_EVENT_TYPE_PROVIDER_DIAGNOSTIC`
2. SSE finish_reason=None + `or STOP` 审查时机 → plan line 117 已做 plan 级决策（absent 不视为 STOP）
3. Non-stream 缺失 finish_reason 处理 → plan line 117 已决策（content success without terminal finish_reason is fatal unless adapter-owned invariant）
4. RunnerSpecificErrorCode 序列化格式 → plan line 121 已委托给 `serialize_engine_error_code(code) -> str` helper，格式为实现细节

---

## Residual Risk

以下风险属于实现期风险，非 plan 缺陷，无需在 plan 阶段修复：

1. **S3 上下文容量风险**: S3 涉及 14+ 文件跨 Engine/Host 两个包。Plan 已给出原子性论证（lines 268-269），且将 weak-typing guard 和 propagation audit 定位为同一切片的验证步骤而非独立实现。但如果实现 agent 上下文窗口不足以稳定承载全量变更，需由实现 agent 在 S3 启动前主动声明并建议拆分策略。此项风险由实现 agent 承担，不由 plan 承担。

2. **Contract Decision #3 的 conditional escape hatch**: "Content success without a terminal finish reason is fatal unless S1 documents a specific adapter-owned invariant proving it is an intermediate chunk." 这个条件句将部分决策权委托给 S1 实现。边界场景（如 tool-call 完成后、function_call 完成后无 finish_reason）的具体行为由 S1 实现中的代码证据决定。Plan 已给出默认 fatal，实现 agent 如需使用 escape hatch 必须在 S1 completion report 中记录 invariant 证据。

3. **S2 新 `PROVIDER_DIAGNOSTIC` Engine event 的 Agent 侧实现复杂度**: Agent 当前将所有 `RunnerProtocolErrorData` 统一设为 `failure_candidate`（`agent.py:1359-1392`）。S2 需要 Agent 区分 fatal protocol error 和 non-fatal diagnostic，这在 plan 中有描述（line 221: "Agent must project Runner diagnostics to Engine diagnostics without setting failure_candidate"），但具体代码变更（可能涉及 `_consume_runner_event()` 的 dispatch 逻辑重构）由实现 agent 承担。

---

## 验证运行状态

| 验证 | 状态 |
| --- | --- |
| 修后 plan 全文阅读 | ✅ 已运行 |
| P3-D-PF-01 ~ P3-D-PF-12 逐项 plan 文本证据交叉验证 | ✅ 已运行 — 12/12 CLOSED |
| Host PROVIDER_DIAGNOSTIC / EventClass / ingest / Tool Trace / read_api / outbox / memory exclusion 专项检查 | ✅ 已运行 — 各项计划清楚 |
| context-overflow provenance 完整链路追踪 | ✅ 已运行 — 逐段确认 |
| log-only warnings / SSE/non-stream choice / finish_reason 边界 / S1-S2 依赖专项检查 | ✅ 已运行 — 均清楚 |
| S3 atomicity / propagation matrix / source scans / weak typing guard / wrapper / docs / no-LLM leakage 专项检查 | ✅ 已运行 — 均足够可执行 |
| 原始 AgentDS F-1~F-9 闭合验证 | ✅ 已运行 — 全部通过 PF 闭合 |
| 原始 AgentMiMo P3-D-PR-001~P3-D-PR-010 闭合验证 | ✅ 已运行 — 全部通过 PF 闭合 |
| Controller adjudication 全部 12 项 PF 闭合验证 | ✅ 已运行 — 全部 CLOSED |
| 修后 plan 内部一致性检查（Contract Decision ↔ S1/S2/S3 Required Changes ↔ Testing matrix ↔ Source scans） | ✅ 已运行 — 无矛盾 |
| 新增问题扫描 | ✅ 已运行 — 未发现新增 gap |
| 测试文件存在性验证 | ❌ 未运行 — 非本 gate 范围（plan 级 review，不验证测试文件内容） |
| pyright 运行 | ❌ 未运行 — 非本 gate 范围（无代码变更） |
| 代码修改或测试执行 | ❌ 未运行 — 非本 gate 范围 |
