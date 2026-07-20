# WU-SEMANTIC-OWNERSHIP-01 / R03 Plan Review — AgentDS

## 0. Review 身份与边界

- **review 目标**：`docs/host/wu-semantic-ownership-01-r03-accepted-call-evidence-llm-projection-plan.md`
- **umbrella WU**：`WU-SEMANTIC-OWNERSHIP-01`
- **internal remediation**：`R03 — accepted call 语义与 opaque provenance 的单一 LLM 投影`
- **review 类型**：adversarial plan review（本 gate 不授权 implementation）
- **裁决优先级**：controller discussion 与已接受决定 > design truth > remediation plan > 当前直接代码/数据证据 > 原始 overdesign review
- **immutable target**：本 review 不编辑 plan、control、production、tests、README、design truth 或 prior artifacts
- **写入**：仅本文 `docs/reviews/wu-semantic-ownership-01-r03-plan-review-ds.md`

### 已完整读取的输入

1. `AGENTS.md` — 项目约束全集
2. `docs/host/issues-implementation-control.md` — umbrella gate 状态（分段读取 R03 相关段落）
3. `docs/phaseflow-umbrella-optimization-control.md` — 流程成本控制
4. `docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md` — Topic 3/4 最终产品裁决
5. `docs/host/design.md` — Host 设计真源
6. `docs/engine/design.md` — Engine 设计真源
7. `docs/tool/design.md` — Tool 设计真源
8. `docs/fins/design.md` — Fins 设计真源
9. `docs/ui/design.md` — UI 设计真源
10. `docs/host/wu-semantic-ownership-01-overdesign-remediation-plan.md` §10（R03 umbrella baseline）
11. `docs/reviews/wu-semantic-ownership-01-r01-doc-complete-input-completion.md` §11（R01 handoff inventory）
12. `docs/reviews/wu-semantic-ownership-01-r03-plan-controller-validation.md`（controller 预检）
13. 当前代码直接证据：`tool_runtime.py`、`waiting.py`、`_event_payload.py`、`accepted_result_projection.py`、`payload_resolution.py`、`evidence.py`、`run_input.py`、`tool_trace.py`、`json_redaction.py`、`read_runtime.py`

### Assumptions tested

1. ordinary/awaiting 可在同一 transaction 内安全写入 `TOOL_CALL_REQUESTED` 与 `TOOL_AWAITING` 并建立 event ref link
2. `result.value.citation` 是当前 accepted outcome 中 citation 的精确 JSON 路径
3. `json_redaction` 模块仅由 `_event_payload.py` 和 `tool_trace.py` 两个 R03 下游 repair 路径消费
4. 四个 LLM-facing consumer（RunInput/Memory/Compact/Tool Trace）的当前传播路径已全部识别
5. 人工逐文件 inventory 覆盖所有 LLM-facing source
6. R01 §11 handoff 的 30 rows 已被完整消费
7. real public-run smoke 可在实现时实际执行

---

## 1. Material Findings

### DS-F01 — 未修复 — 中 — TOOL_AWAITING ref link 的 transaction 内 sequencing 未显式指定

- **位置**：§4.2 writer 签名、§6.3 item 4
- **问题类型**：状态机漏洞 / 不可直接实施
- **当前写法**：
  - §4.2 writer 签名为 `build_tool_call_requested_event_request(transaction, *, atom, event_id, occurred_at, origin) -> EventLogAppendRequest`
  - §6.3 item 4 说 `_tool_awaiting_event_request` "接收已写 request row"
  - §4.4 说 `TOOL_AWAITING.tool_call_requested_event_ref={event_id,event_sequence}`

- **反例/失败场景**：
  implementation agent 可能：
  1. 在调用 writer 前预生成 `event_id`，但 `event_sequence` 只能由 EventLog store 在 append 时分配
  2. 试图在 writer 内部通过 transaction 查询下一个 sequence（这不可行，因为 append 才是 sequence 的分配点）
  3. 同时构造 `TOOL_CALL_REQUESTED` 和 `TOOL_AWAITING` 两个 append request，但没有先 append 第一个再读回 `event_sequence`

- **为什么有问题**：
  计划正确识别了需要真实 row ref，但 writer 签名把 `event_id` 作为**输入参数**而非**返回值的一部分**，未说明 `event_sequence` 的来源是 `append_event().row.event_sequence`。当前代码（`tool_runtime.py:2463-2471` 与 `waiting.py:620-629`）已经示范了正确模式：先 `append_event` 拿到 `.row`，再把 row 的 field 传给后续 event。计划应显式写出这个 sequencing contract。

- **直接证据**：
  - `tool_runtime.py:2463-2471`：ordinary accept 先 `append_event(_tool_call_requested_event_request(...)).row` 得到 `requested`，再把 `requested` 传给 governed/result event
  - `waiting.py:620-629`：awaiting accept 当前先 `append_event` 得到 `tool_call_requested`，再 `append_event` 得到 `tool_awaiting`，但 `_tool_awaiting_event_request` 当前**不接受** `tool_call_requested` row 参数——这正是计划要修复的缺陷
  - 计划 §4.2 writer 返回 `EventLogAppendRequest`，但 append 的返回值（`EventLogRow` with `event_sequence`）由 EventLog store 产生，不在 writer 控制范围内

- **影响**：实施 Agent 可能写出表面上通过类型检查但实际 event_sequence 为虚构值或硬编码 `0` 的代码，导致 resume 时 ref link 校验静默失败或误通过

- **建议改法和验证点**：
  在 §6.3 item 4 显式补充 sequencing contract：
  ```
  4. awaiting _accept_in_transaction:
     a. 先调用 shared writer 构造 TOOL_CALL_REQUESTED append request
     b. append_event(request) 拿到 row（含 event_id + event_sequence）
     c. 用 row.event_id 和 row.event_sequence 构造 tool_call_requested_event_ref
     d. 把 ref 传入 _tool_awaiting_event_request
     e. append_event 写入 TOOL_AWAITING
  ```
  S1 tests 必须断言 `TOOL_AWAITING` payload 中的 `tool_call_requested_event_ref.event_sequence` 等于同事务 `TOOL_CALL_REQUESTED` row 的 `event_sequence`（而非 0、null 或虚构值）。

- **修复风险**：低 — 当前代码已有正确模式，只需在 plan 中显式写出
- **严重程度**：中 — 不修复可能导致 implementation 写出语义正确但字段值错误的代码

---

### DS-F02 — 未修复 — 中 — citation 精确 JSON 路径未经当前 accepted outcome 序列化链路验证

- **位置**：§4.6 source contract、§3.4 当前 source-owner 审计
- **问题类型**：契约缺失 / 不可直接实施
- **当前写法**：
  - §4.6：Host 读取 `kind=completed -> result.ok=true -> result.value -> citation`
  - §3.4：`dayu/fins/tools/read_runtime.py::_build_citation` 由 `Citation.to_dict()` 输出 producer-owned business citation

- **反例/失败场景**：
  Fins `_build_citation` 返回 `{"source_type": ..., "ticker": ..., ...}` 并嵌入 result JSON 为 `{"citation": {...}}`。但 plan 期望的路径 `result.value.citation` 取决于：
  1. `ToolResultSuccess.value` 的 JSON 序列化结构
  2. `accepted_tool_outcome_json` 如何包裹 `ToolCompletedOutcome`
  3. `TOOL_RESULT_ACCEPTED` 的 `raw_tool_outcome` payload 如何存储这个 JSON

  如果实际路径是 `result.citation`（citation 在 result 顶层而非 `result.value.citation`），或 citation 被嵌套在 `result.value.result.citation` 中，plan 的机械读取路径就会在运行时返回 source-unavailable，而所有测试可能因 mock fixture 使用了与 plan 一致但不匹配真实序列化的路径而通过。

- **为什么有问题**：
  计划没有给出从 `_build_citation` → `ToolResultSuccess` → `accepted_tool_outcome_json` → `raw_tool_outcome` → Host 读取的完整路径追踪。plan §3.4 只证明了 "citation 存在"，未证明 "citation 在 `result.value.citation` 这个精确路径上"。

- **直接证据**：
  - `read_runtime.py:2170`：`return citation.to_dict()` — citation 是 dict
  - `read_runtime.py:778,923,1135,1284,1389,1487,1568,1646`：citation 嵌入为 `"citation": citation`
  - 但 `accepted_tool_outcome_json` 的序列化路径未经本 review 追踪到 `raw_tool_outcome` 的精确 JSON 结构

- **影响**：实施 Agent 按 plan 写的路径可能在真实 Fins result 上永远读不到 citation，全部 fallback 到 source-unavailable，而测试用 fake citation 放在 `result.value.citation` 路径全部通过

- **建议改法和验证点**：
  1. 追踪一条真实 Fins read → `ToolCompletedOutcome` → `accepted_tool_outcome_json` → `raw_tool_outcome` 的完整序列化链路
  2. 在 plan §4.6 中写出 citation 在 `raw_tool_outcome` JSON 中的精确 JSONPath
  3. S3 tests 必须使用真实 Fins result payload（非手写 fixture）验证 citation 路径

- **修复风险**：低 — 只需追踪现有序列化链路并写出精确路径
- **严重程度**：中 — 路径错误会导致整个 citation 传播链静默失效

---

### DS-F03 — 未修复 — 低 — real public-run smoke 的环境依赖与 plan 的 stop condition 形成死锁

- **位置**：§12 真实 public-run smoke、§16 stop conditions
- **问题类型**：open question 未收敛
- **当前写法**：
  - §12.2：smoke 需要真实 provider credential、可访问 Web 网络、真实 Fins source/processed fixture
  - §12.2："缺任一前置条件时不能把 smoke 标成 skipped/pass，也不能用 fake tool 替代；R03 completion 停止并报告未满足前置条件"
  - §16："real public-run smoke 只能靠 fake/scripted provider 或伪 awaiting result 才能通过" → stop

- **反例/失败场景**：
  S1/S2 的代码实现和单元测试全部完成并通过，但 smoke 环境（provider credential、Fins fixture）在实现时不可用。按 plan，completion 必须停止且不能宣称 R03 完成。这意味着：
  1. S1/S2 的 owner contract、corruption matrix、LLM-facing inventory 的代码级验证已经完成
  2. 但一个外部环境依赖阻止了整个 R03 的 closure
  3. 代码变更本身是正确的，只是在等待运维环境

- **为什么有问题**：
  这并非 plan 设计错误，但 plan 没有区分"代码 contract 正确性验证"和"端到端集成环境验证"。如果 smoke 环境在 code review 和 deepreview 之后才就绪，所有 review 需要重做。plan 可以考虑：S1/S2 的单元/集成测试 closure 是否可以独立 accept，而 smoke 作为 aggregate gate 的准入条件而非 block-everything 条件。

- **直接证据**：
  - plan §12.2 的 smoke 前置条件列表
  - plan §16 的 stop condition："real public-run smoke 只能靠 fake/scripted provider 或伪 awaiting result 才能通过"
  - 当前 `utils/smoke_host_public_awaiting_entrypoint.py` 使用 deterministic mock awaiting tool，plan 明确说它不能替代 R03 smoke

- **影响**：低 — 这是流程/环境风险，不是设计或正确性风险；smoke 设计本身是正确的

- **建议改法和验证点**：
  建议在 plan §12.2 增加一个 minimal smoke path：至少 Doc ordinary run 不依赖外部网络/Fins fixture，仅依赖本地文件系统，可以在任何有 provider credential 的环境执行。Doc 路径可以覆盖 ordinary request atom、query projection、citation source-unavailable、opaque ref absence 四个 contract，提供独立于 Fins/Web 环境的 smoke 证据。Web 和 Fins smoke 保留为完整环境就绪后的 aggregate gate。

- **修复风险**：低 — 不改变任何 contract，仅为 smoke 增加分层
- **严重程度**：低 — 非阻塞性流程改进建议

---

### DS-F04 — 未修复 — 低 — `dayu/runtime/__init__.py` 的精确修改内容未指定

- **位置**：§7.2 允许文件、§7.3 删除项、§13.3 coverage table
- **问题类型**：不可直接实施
- **当前写法**：
  - §7.3："`dayu/runtime/json_redaction.py` 全模块和 `dayu/runtime.__init__` 的模块清单引用"
  - §13.3 coverage table 对 `dayu/runtime/__init__.py` 设 `>=80%` 覆盖率目标

- **反例/失败场景**：
  implementation agent 不知道 `__init__.py` 中哪些行引用 `json_redaction`，可能：
  1. 只删除一行 docstring 引用
  2. 或者过度修改，删除不相关的模块引用
  `__init__.py` 的覆盖率目标 ≥80% 对一个可能只改一行的文件过于激进，可能迫使 agent 新增无意义测试

- **为什么有问题**：
  当前 `dayu/runtime/__init__.py:32` 的 `dayu.runtime.json_redaction` 出现在模块 docstring 的列表项中。修改内容可能只是删除这一行文本。对该文件设 80% 覆盖率不合理——它是一个 package `__init__.py`，主要包含 docstring 和 import。

- **直接证据**：
  - `dayu/runtime/__init__.py:32`：``dayu.runtime.diagnostic_text``、``dayu.runtime.json_redaction``、
  - `dayu/runtime/json_redaction.py` 在 grep 中的唯一外部引用是 `_event_payload.py:20` 和 `tool_trace.py:81` 的 import

- **影响**：低 — agent 不会写错，但可能浪费时间满足不合理的覆盖率目标

- **建议改法和验证点**：
  1. 在 plan §7.3 显式写出 `__init__.py` 中需要删除的具体行
  2. 将 `dayu/runtime/__init__.py` 的覆盖率目标降为 N/A（仅删除引用，不新增逻辑），或将目标改为"不引入新 uncovered line"
  3. 确认 `__init__.py` 中没有其它 `json_redaction` 引用（如 re-export）

- **修复风险**：低
- **严重程度**：低 — 不影响正确性

---

## 2. Non-Blocking Notes

### DS-N01 — `_event_payload.py` 中 `redact_sensitive_json_fields` import 的 S1 删除时机

plan §6.3 item 4 正确指出 S1 从 `_event_payload.py` 删除 `llm_safe_replay_arguments` 及 redaction import。当前 `_event_payload.py` 仅在两处使用 `redact_sensitive_json_fields`：(1) import at line 20，(2) call at line 130 inside `llm_safe_replay_arguments`。S1 删除该函数后 import 成为 unused，删除是正确的。S2 在 `tool_trace.py` 停止使用 `_redacted_json` 后删除整个 `json_redaction.py` 模块。这个两阶段删除是正确的，plan 无需修改。

### DS-N02 — `_INTERNAL_SOURCE_REF_KINDS` 当前值覆盖范围

当前 `accepted_result_projection.py:61-71` 的 `_INTERNAL_SOURCE_REF_KINDS` 包含 `{"tool_call_event", "tool_result_event", "event", "eventlog", "payload", "artifact", "digest"}`。plan §11.3 item 2 正确要求删除该常量及 `_readable_ref_text`。但 plan 的 sentinel 测试（§11.4）使用 `ref_kind="eventlog"` 和 `ref_kind="fliing-typo"`——前者恰好在当前 denylist 中，后者拼写错误恰好不在。建议 sentinel 也覆盖一个当前 denylist 中但拼写变体的值（如 `eventlogg`），确保删除 denylist 后 typo 不会通过其它分支泄漏。

### DS-N03 — 旧测试删除清单的完整性

plan §6.4 列出了要删除的旧测试名称。这些名称在当前测试文件中确实存在（如 `test_awaiting_accept_persists_only_llm_safe_replay_arguments` at `test_wait_awaiting_accept.py:232`）。但 plan 未列出所有断言 `_INTERNAL_SOURCE_REF_KINDS` 行为的旧测试。建议 S2/S3 implementation 前用 `rg '_INTERNAL_SOURCE_REF_KINDS|_readable_ref_text|filing:MSFT-10K' tests/` 做完整扫描并逐条决定 delete/rewrite。

### DS-N04 — `AcceptedToolCallRequestAtomInput` 的 `tool_identity_digest` 字段

plan §4.2 的 `AcceptedToolCallRequestAtomInput` 包含 `tool_identity_digest: str` 字段。当前代码中 `ToolDefinition` 的 identity digest 计算在 `dayu/runtime/tools_discovery.py`，但 plan 未说明这个值如何从 accept candidate 传递到 atom input。这是 implementation detail，不影响 plan 正确性，但值得在 S1 implementation 时确认调用方可以可靠提供此值。

### DS-N05 — Tool Trace readable summary 的 request 部分

plan §4.7 说 "descriptor-backed request 的 request-event readable summary不得展示 payload ref/digest；可给业务中性'参数正文由 accepted-result 同源投影提供'"。这个中文文案需要与 `AGENTS.md` LLM-facing 文本约束对齐——它不应让模型困惑"同源投影"是什么。建议 plan 明确这句文案的 exact text，或要求 S2/S3 completion 中记录 final text。

---

## 3. 已验证通过的项

以下 plan claim 经当前代码证据直接核验，未发现反例：

1. **ordinary/awaiting 双写问题真实存在**：`tool_runtime.py:4315` 的 `_tool_call_requested_event_request` 与 `waiting.py:2323` 的 `_tool_call_requested_event_request` 是两个独立实现；`waiting.py:2336` 调用 `llm_safe_replay_arguments` 改写参数。plan §3.1/§3.2 的 call path 分析准确。

2. **`llm_safe_replay_arguments` 的调用链**：`_event_payload.py:120` 定义 → `_event_payload.py:79` 在 `tool_awaiting_payload` 内调用 → `waiting.py:24` import → `waiting.py:2336` 使用。plan 的删除路径覆盖全部调用点。

3. **`_contains_unsafe_argument_key` 的分类逻辑**：`accepted_result_projection.py:553-575` 递归扫描 key name，命中即隐藏整个 query。plan 正确识别了 false positive/negative 风险。

4. **`OpaqueEvidenceRef` 的 source guessing**：`accepted_result_projection.py:61-71` 的 denylist + `_readable_ref_text` (L681-689) 对 unknown kind 返回 `kind:id` 文本。plan 正确识别了 typo/unknown pass-through 风险。

5. **`json_redaction` 的消费者范围**：仅 `_event_payload.py:20` 和 `tool_trace.py:81` 两个生产 import。Engine `diagnostic_payload.py:26` 的 `_SENSITIVE_KEY_FRAGMENTS` 是独立定义，不 import `dayu.runtime.json_redaction`。plan 的删除不会误伤 Engine diagnostic 脱敏。

6. **R01 §11 handoff 完整性**：plan §9 消费了 R01 completion §11 的全部 30 rows（5 descriptions + 5 parameter groups + 5 error/message/hint groups + 5 result key groups + 10 other sources）。每个 row 都有 explicit R03 disposition。

7. **人工 inventory 覆盖**：plan §8.1 覆盖 37 prompt assets，§8.2 覆盖 23 production tool schema/result/error sources，§8.3 覆盖 15 test/smoke fixtures，§8.4 覆盖 61 executable-Python constructor scan paths。总计 136 个逐文件 disposition，无遗漏类别。

8. **三 slice 依赖的合理性**：S1 建立 durable identity → S2 在 stable atom 上做 source/projection audit → S3 在 stable material 上做 propagation closure。依赖链不可颠倒，且每片有独立 review 边界。

9. **非目标边界清晰**：Issue #177、#178、统一授权、BusinessSource、Fins reverse dependency 均被显式排除且有 stop condition 防护。

10. **Engine no-diff 证据**：`dayu/engine/agent.py::_project_tool_outcome_for_llm` 与 `dayu/engine/runners/openai/payload.py` 只做机械 typed serialization，plan 正确判定 no-diff。

---

## 4. Open Questions

无。所有不确定点已转化为上述 findings 或 notes。

---

## 5. Residual Risks

| 风险 | 分类 | 建议跟踪 |
| --- | --- | --- |
| real smoke 环境不可用导致 R03 completion 阻塞 | 流程/运维 | 见 DS-F03；建议 controller 在 S1/S2 code review 后决策是否可分层 accept |
| 非 Fins tool 当前无 explicit citation 导致全部 source-unavailable | 已由 plan §4.6 接受 | controller 确认这是 acceptable product behavior |
| `fetch_more` schema 修正后 Issue #177 仍未完整 wiring | 已由 plan §1.4 排除 | Issue #177 |
| 未来 tool schema 新增真实 credential 参数 | 已由 plan §16 stop condition 覆盖 | plan §16 row 1 |

---

## 6. Final Plan Review Conclusion

**PASS-WITH-FINDINGS**

plan 的 owner boundary、data flow、corruption matrix、delete/retain contract、LLM-facing inventory、R01 §11 consumption、三 slice sequencing 和 allowlist 均达到 code-generation-ready 水平。三个 material findings（DS-F01/F02/F03）均不构成结构性阻塞：

- **DS-F01**（transaction sequencing）：plan 的意图正确，当前代码已验证可行模式，只需在 plan 中显式写出 sequencing contract。修复风险低。
- **DS-F02**（citation 路径验证）：plan 的方向正确，只需追踪一条真实序列化链路确认精确 JSONPath。修复风险低。
- **DS-F03**（smoke 环境依赖）：流程改进建议，不影响 plan 正确性。

三个 findings 修复后 plan 可达 **PASS**。non-blocking notes 不影响 implementation 启动。

controller 可在 accepted DS-F01/DS-F02 修复后授权进入 implementation，DS-F03 可作为 aggregate gate 的流程决策独立处理。
