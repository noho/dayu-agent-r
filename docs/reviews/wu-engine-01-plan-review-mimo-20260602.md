# WU-ENGINE-01 Plan Review — AgentMiMo

## Review Context

- Work unit: WU-ENGINE-01 Runner diagnostic payload audit.
- Gate: plan review。
- Plan artifact: `docs/host/wu-engine-01-runner-diagnostic-payload-audit-plan.md`。
- Design source: `docs/host/design.md`。
- Control doc: `docs/host/host-core-followup-implementation-control.md`。
- Controller evidence: `docs/reviews/wu-engine-01-code-inspection-controller-20260602.md`。
- Reviewer: AgentMiMo (mimo)。

## Review Lenses

### 1. Design Doc Compliance

**结论: PASS**

Plan 正确收窄到 Engine/OpenAI runner 内部 diagnostic payload helper，不触碰 Host 状态机、Host lifecycle、EventLog schema、provider state sealed union。设计真源 `docs/host/design.md:10` 要求 "Engine 只执行单次 AgentRunRequest，不拥有 Session / Run 生命周期"；plan 的所有修改都在 Engine runner 内部，不引入 Host 生命周期逻辑。

设计真源 `docs/host/design.md:2745` 要求 "EventLog 不能包含 API key、headers、完整 raw prompt 或完整 provider payload；大 payload、raw candidate、provider error body 或 repair prompt 如需保留，必须写 artifact / diagnostic ref 并做敏感信息过滤"。Plan 的 bounded + redacted diagnostic payload helper 正是对齐这条约束。

### 2. Control Doc WU-ENGINE-01 Scope

**结论: PASS**

Control doc 定义 WU-ENGINE-01 为 "Runner diagnostic payload audit"，plan 的 motivation section 正确判断 "问题真实存在，但边界比历史标题窄"，不推翻 typed provider state 方向。Plan 明确 disallowed: 不修改 Host 状态机、Host ingest production 行为、EventLog schema、provider state sealed union、provider extension config。Scope 收敛到 OpenAI runner 内部 diagnostic payload helper、相关 parser/runner 写入点、stream/non-stream parity 测试和 Engine README 语义同步。

### 3. Code-Generation-Ready

**结论: PASS with observations**

Plan 的 slices 结构完整：每个 slice 有 objective、allowed files、exact changes、test/validation commands、stop condition、completion signal。File ownership 明确列出 production allowed files、test allowed files 和 explicitly disallowed files。Helper 设计指定常量列表、函数签名、输出字段约束。调用点约束明确要求使用模块级私有常量而非字符串字面量。

Observations（不阻塞）：
- `_SENSITIVE_KEY_FRAGMENTS` 未指定具体 pattern 值（见 Finding M-01）。
- `_DIAGNOSTIC_PAYLOAD_VERSION` 的 versioning / backward compatibility 未说明（见 Finding M-02）。

### 4. Over-design / Over-coupling / Contract Boundary

**结论: PASS**

- Helper 是 OpenAI runner 模块级私有实现，只依赖标准库和 `dayu.contracts.json_value.JsonValue`，不 import Host / Service / UI / Fins。符合 `dayu.runtime` 边界约束（helper 不在 runtime 内，而是在 engine runner 内部）。
- No public contract shape change：三个 `raw_payload: JsonValue | None` 字段形状不变，RunnerEventData / EngineEventData 封闭联合成员不变，Host durable schema 不变。
- 不引入 provider abstraction redesign，不创建兼容 facade。
- Slice 切分合理：Slice 1 覆盖协议错误路径（parser + parity test），Slice 2 覆盖 HTTP 错误路径（runner + host ingest guard），Slice 3 汇总验证。依赖边界清晰。

### 5. AGENTS.md Compliance

**结论: PASS**

- 禁止 `Any` / `object`：Plan §6.9 明确禁止。
- 禁止 `hasattr` / `getattr`：Plan §6.10 明确禁止。
- 禁止 extra payload：Plan §4 explicitly disallowed 列表明确禁止。
- 禁止魔法数字/字符串：Plan §6.3 要求模块级私有常量，§6.5 要求调用点传常量。
- 中文 docstring：Plan §6.1 要求所有函数有完整中文 docstring。
- 禁止兼容 facade：Plan §6.11 明确禁止。
- pyright：Plan §7 slices 都要求 pyright 验证。

### 6. Stream / Non-stream Error Object Consistency 测试覆盖

**结论: PASS**

Plan §8 明确定义了 parity 测试要求：
- 两条路径都产出 `PROVIDER_PROTOCOL_ERROR` + `RUNNER_DONE(ERROR)` 事件序列。
- 两条路径提取同一 provider error message。
- 两条路径的 `raw_payload` 都是 bounded diagnostic payload。
- 两条路径 diagnostic common fields 一致：digest、byte size、error code、error type、error param。
- 两条路径均不把 secret-like 字段值写入 `repr(raw_payload)`。
- 允许 `error_code` 保持 path-specific。

这比当前测试覆盖（只覆盖成功终态 parity）有实质提升。

## Findings

### M-01: `_SENSITIVE_KEY_FRAGMENTS` 未指定具体 pattern 值

**Severity**: medium

**Evidence**: Plan §6.3 定义了常量 `_SENSITIVE_KEY_FRAGMENTS: tuple[str, ...]`，§6.8 要求 "匹配 `_SENSITIVE_KEY_FRAGMENTS` 的字段值不得进入摘要"，但未指定具体 pattern 值。Implementation agent 需要自行决定哪些 key fragment 被视为敏感。

**Impact**: OpenAI error response payload 的典型字段是 `message`、`type`、`code`、`param`、`request_id`，不含明显 secret。但 HTTP error body 可能是任意 JSON，理论上可包含敏感信息。若 pattern 过松，敏感信息可能进入 diagnostic artifact；若过紧，可能误删诊断所需字段。

**建议修正**: 在 plan §6.3 或 §6.8 中补充建议 pattern 值，例如 `("api_key", "secret", "token", "password", "authorization", "credential")`。不要求穷尽，但应给 implementation agent 一个明确起点。

### M-02: `_DIAGNOSTIC_PAYLOAD_VERSION` 的 versioning 和 backward compatibility 未说明

**Severity**: medium

**Evidence**: Plan §6.3 定义 `_DIAGNOSTIC_PAYLOAD_VERSION: int` 为 helper 输出字段之一，但未说明：(1) 初始值应为多少；(2) version 变化时 Host ingest 对已有 artifact 的处理策略；(3) 是否需要 Host ingest 侧的 version-aware 读取逻辑。

**Impact**: 当前 Host ingest (`dayu/host/engine_ingest.py:2400`) 把 `raw_payload` 当作 opaque `JsonValue` 写入 artifact，不解析内容。因此 version 变化不会破坏现有 ingest 路径。但若未来 Host 需要解析 diagnostic payload 内容（例如做聚合诊断），versioning 策略需要提前约定。

**建议修正**: 在 plan 中补充一句说明：初始 version = 1；Host ingest 当前不解析 diagnostic payload 内容，version 变化不影响现有 artifact 写入路径。若未来 Host 需要解析 diagnostic payload，应先设计 version-aware 读取协议。

### L-01: Invalid UTF-8 路径已有 bounded payload，不是 `dict(parsed)`

**Severity**: low

**Evidence**: Plan §3 引用 `sse_parser.py:233` 说 "对 invalid UTF-8 chunk 做 base64，但没有显式最大输出常量"。实际代码（`sse_parser.py:233-234`）构造 `{"chunk_base64": encoded, "final_decode": final_decode}`，不是 `dict(parsed)`。Plan §7.1 Slice 1 的 exact changes 正确描述了替换目标 `invalid_utf8_diagnostic_payload(...)`，但 plan 正文中多处将 invalid UTF-8 与其它 `dict(parsed)` 路径并列讨论，可能造成误解。

**Impact**: 不影响实施正确性，因为 Slice 1 exact changes 明确描述了替换行为。但阅读 plan 时可能误认为 invalid UTF-8 也是 `dict(parsed)` 路径。

**建议修正**: 在 plan §2 或 §3 中明确区分：invalid UTF-8 路径已有自定义 payload（`chunk_base64` + `final_decode`），但缺少 byte size bound；其它路径是 `dict(parsed)` 原样保存。两者问题不同，但修复方案统一收敛到 bounded diagnostic payload helper。

### L-02: Repr masking test 的 secret-like 字段覆盖

**Severity**: low

**Evidence**: Plan §7.1 Slice 1 test changes 要求 "断言 secret-like 字段值不出现在 `repr(raw_payload)`"。但现有测试数据（`test_protocol_error.py:124-126` 和 `test_protocol_error.py:162-164`）不含敏感字段。若测试不构造含敏感字段的 payload，repr masking 断言将 vacuously pass。

**Impact**: 测试可能无法实际验证 redaction 逻辑。Implementation agent 可能需要在测试数据中加入含敏感 key 的字段来触发 redaction。

**建议修正**: 在 plan §7.1 test changes 中补充：测试构造的 provider error object 应包含至少一个匹配 `_SENSITIVE_KEY_FRAGMENTS` 的字段（如 `{"error": {"message": "bad", "api_key": "sk-xxx"}}`），以验证 redaction 逻辑实际生效。

## Conclusion

**PASS — 无 blocking finding。**

Plan 符合 design doc 设计目标（Host 强约束、Engine 只执行单次 AgentRunRequest、不让 Engine 拥有 Host lifecycle/state），符合 control doc WU-ENGINE-01 范围（Engine runner diagnostic payload audit，不重写 provider state），code-generation-ready 程度足够（file ownership、exact changes、slice、tests、stop conditions 均具体），无过度设计或过度耦合，无 AGENTS.md 违规。Stream / non-stream error object consistency 测试覆盖策略明确且比当前测试有实质提升。

2 个 medium finding（`_SENSITIVE_KEY_FRAGMENTS` pattern 值缺失、`_DIAGNOSTIC_PAYLOAD_VERSION` versioning 未说明）和 2 个 low finding（invalid UTF-8 路径描述精度、repr masking test 覆盖），均不要求 plan fix gate，可在 implementation 阶段由 implementation agent 按建议修正处理。

**建议**: 进入 implementation。
