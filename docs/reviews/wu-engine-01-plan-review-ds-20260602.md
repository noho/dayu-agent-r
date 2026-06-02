# WU-ENGINE-01 Plan Review — AgentDS

## Gate / Role

- Gate: `plan review`。
- Role: independent plan review agent (AgentDS)，不是 controller，不修改 source/tests，不 commit/push/创建 PR。
- Review target: `docs/host/wu-engine-01-runner-diagnostic-payload-audit-plan.md`。
- Design source: `docs/host/design.md`。
- Control doc: `docs/host/host-core-followup-implementation-control.md`。
- Controller evidence: `docs/reviews/wu-engine-01-code-inspection-controller-20260602.md`。

## Review Summary

**结论: PASS** — 无 blocking finding。

Plan 正确将 work unit 收窄为 Engine/OpenAI runner diagnostic payload audit，未越界到 Host 状态机、provider state sealed union 或 public contract shape change。Slice 切分合理，stop conditions 明确，non-goals 与 allowed/disallowed files 清晰。6 条 medium findings 和 4 条 low findings 均可在 plan fix 或 implementation 阶段解决，不阻塞进入 implementation gate。

---

## Findings

### FIND-01 [Medium] invalid_utf8 error_code 常量提升在 Slice 1 exact changes 中遗漏

**证据**:
- Plan Section 6 item 5 明确要求: "sse_parser.py invalid UTF-8 使用 _INVALID_UTF8_CODE / _TRUNCATED_UTF8_TAIL_CODE 私有常量；若当前代码只有局部字符串，先提升为模块级私有常量。"
- 当前 `sse_parser.py:222` 使用局部字符串字面量:
  ```python
  error_code = "truncated_utf8_tail" if final_decode else "invalid_utf8"
  ```
- Plan Section 7 Slice 1 exact changes 只写了 "sse_parser.py 中 invalid UTF-8 的 full chunk base64 替换为 invalid_utf8_diagnostic_payload(...)"，未显式列出"将 error_code 局部字符串提升为模块级 `_INVALID_UTF8_CODE` / `_TRUNCATED_UTF8_TAIL_CODE` 常量"。

**建议**: 在 Slice 1 exact changes 中增加一条: "sse_parser.py 中 `_handle_invalid_utf8` 的局部 error_code 字符串提升为模块级私有常量 `_INVALID_UTF8_CODE = 'invalid_utf8'` / `_TRUNCATED_UTF8_TAIL_CODE = 'truncated_utf8_tail'`"。

---

### FIND-02 [Medium] diagnostic_payload.py 缺少独立单元测试文件

**证据**:
- Plan Section 7 的 allowed test files 包括 `test_protocol_error.py`、`test_stream_non_stream_terminal_parity.py`、`test_http_error_event.py`、`test_host_engine_ingest_mapping.py`，全部是集成/映射层测试。
- Plan Section 6 定义了 4 个 public-to-module 函数，各自有独立的边界条件（大小上限、敏感字段脱敏、digest 计算、类型收窄），但没有对应的 `tests/engine/runners/openai/test_diagnostic_payload.py`。
- CLAUDE.md 要求单文件测试覆盖率 >= 80%；新模块若无独立测试，覆盖率只能依赖集成测试间接覆盖。

**建议**: 在 Slice 1 allowed files 中增加 `tests/engine/runners/openai/test_diagnostic_payload.py`，覆盖:
- 各 helper 函数的正常输出结构。
- `_DIAGNOSTIC_PAYLOAD_MAX_BYTES` 上限截断行为。
- `_SENSITIVE_KEY_FRAGMENTS` 脱敏行为。
- 超大 payload 经截断后仍超上限的 fallback。
- `JsonValue` 类型收窄（非 dict 输入行为）。

---

### FIND-03 [Medium] provider error sub-object 提取规则不明确

**证据**:
- Plan Section 6 item 7 列出 diagnostic payload 应包含的字段: "provider error object 中的 bounded code / type / param 等低风险短字段"。
- 但 helper 函数签名 `provider_error_diagnostic_payload(payload: dict[str, JsonValue], *, source: str) -> JsonValue` 接收的是完整顶层 parsed JSON dict。
- 当前 provider error 的 JSON 结构为 `{"error": {"message": "...", "type": "...", "code": "..."}}` — `code`/`type`/`param` 在 `error` 子对象内，不在顶层。
- Plan 未说明 helper 是否应:
  1. 固定查找 `"error"` 子键并提取 `code`/`type`/`param`；还是
  2. 仅列出顶层 keys（此时顶层只有 `"error"` 一个 key，诊断价值有限）。

**建议**: 明确 `provider_error_diagnostic_payload` 的提取规则: 若 payload 顶层存在 `"error"` 键且值为 dict，从中提取 `code`/`type`/`param` 字段（各自受 `_DIAGNOSTIC_SCALAR_MAX_CHARS` 约束），同时仍保留顶层 keys 列表作为 bounded top-level keys。

---

### FIND-04 [Medium] 超出 `_DIAGNOSTIC_PAYLOAD_MAX_BYTES` 上限后的 fallback 行为未充分指定

**证据**:
- Plan Section 6 item 6: "如果某次摘要仍超过上限，helper 必须继续删除低价值字段或截断 bounded preview，而不是返回原 payload。"
- "继续删除低价值字段" 未定义优先级顺序。可能的 fallback 链:
  1. 先截断 bounded top-level keys / bounded preview。
  2. 若仍超限，是否删除 bounded top-level keys 而仅保留 digest + byte_size + version？
  3. 若连 digest + byte_size + version 都超限（极端情况），应返回什么？
- 实现可能写出不一致的 fallback 逻辑或无限截断循环。

**建议**: 定义明确的 fallback 优先级:
1. 先截断 bounded preview 到 `_DIAGNOSTIC_PAYLOAD_MAX_BYTES`。
2. 仍超限时，删除所有 bounded preview / bounded top-level keys，仅保留 `version` + `source` + `canonical_byte_size` + `sha256_digest`。
3. 若最小诊断仍超限（仅理论可能），记录 warning 日志并返回最小结构，不做无限截断。

---

### FIND-05 [Medium] `protocol_object_diagnostic_payload` 的 `reason` 参数常量未定义

**证据**:
- Plan Section 6 item 4 定义 `protocol_object_diagnostic_payload(payload: dict[str, JsonValue], *, source: str, reason: str) -> JsonValue`。
- Plan Section 7 Slice 1 exact changes: "sse_parser.py 中 missing choices / invalid choice object 的 raw_payload=dict(parsed) 替换为 protocol_object_diagnostic_payload(parsed, source=_MISSING_CHOICES_CODE, reason=_MISSING_CHOICES_CODE)；若 invalid choice object 需要更细 reason，先定义模块级私有常量，不在调用点写字符串字面量。"
- 当前 sse_parser.py 有两个 `_MISSING_CHOICES_CODE` 使用点:
  - Line 354-369: choices 缺失且 usage 缺失 → error_code=`_MISSING_CHOICES_CODE`
  - Line 391-404: choices 为 list 但无可解析 choice → error_code=`_MISSING_CHOICES_CODE`
- 两处的语义不同（前者是既无 choices 也无 usage，后者是有 choices list 但无可解析对象），但 plan 中 `reason` 都用 `_MISSING_CHOICES_CODE`，丢失了区分度。

**建议**: 为两种情况定义不同的 reason 常量，例如 `_MISSING_CHOICES_AND_USAGE_REASON` 与 `_NO_VALID_CHOICE_OBJECT_REASON`，或在 plan 中明确承认当前 `reason=_MISSING_CHOICES_CODE` 对这两种情况是充分区分度（因为 `source` 已承载 `_MISSING_CHOICES_CODE`，调用点上下文可从日志/error_code 区分）。

---

### FIND-06 [Low] `test_http_json_object_error_body_preserved_as_raw_payload` 重命名后新名称未指定

**证据**:
- Plan Section 7 Slice 2 exact changes: "test_http_json_object_error_body_preserved_as_raw_payload 改名为 diagnostic payload 语义测试"。
- 未给出具体新测试名，implementation agent 可能随意命名导致后续 grep/review 困难。

**建议**: 给出建议测试名，例如 `test_http_json_object_error_body_produces_bounded_diagnostic_payload`。

---

### FIND-07 [Low] `repr(raw_payload)` 断言脆弱

**证据**:
- Plan Section 7 Slice 1 exact changes: "断言 secret-like 字段值不出现在 repr(raw_payload)"。
- Plan Section 8: "两条路径均不把 secret-like 字段值写入 repr(raw_payload)"。
- `repr()` 依赖 `dataclass.__repr__` 实现，若 dataclass 字段名或 `__repr__` 实现变化，`repr()` 断言可能漏过或误报。
- 更可靠的断言是直接检查 diagnostic payload JSON 序列化后的字符串: `json.dumps(raw_payload)` 或递归检查 payload dict 的所有叶子值。

**建议**: 改为断言 `json.dumps(raw_payload, ensure_ascii=False)` 不含 secret-like 值，或递归遍历 `raw_payload` dict 的所有 str 叶子值并断言不含敏感片段。

---

### FIND-08 [Low] stream/non-stream parity 测试中 "provider error code" 术语与 `RunnerProtocolErrorData.error_code` 存在歧义

**证据**:
- Plan Section 8: "两条路径对同一 provider error object 产出的 diagnostic common fields 一致：payload digest、payload byte size、provider error code、provider error type、provider error param"。
- Plan Section 6 item 13: "stream / non-stream provider error object 的 error_code 可以继续保持 path-specific"。
- "provider error code" 在 Section 8 中指的是 provider 返回的 error object 内的 `code` 字段（如 `"context_length_exceeded"`），而 Section 6 item 13 中的 `error_code` 指的是 `RunnerProtocolErrorData.error_code`（如 `"sse_provider_error"`）。同一文档中 "error_code" 指代两个不同概念。

**建议**: 在 Section 8 中将 "provider error code" 改为 "provider error object 内的 `code` 字段" 或 "provider-level error code"，与 `RunnerProtocolErrorData.error_code`（runner-level error code）明确区分。

---

### FIND-09 [Low] canonical JSON byte size 计算方式未说明

**证据**:
- Plan Section 6 item 7: diagnostic payload 包含 "原 payload canonical JSON byte size"。
- `dayu.runtime` 已有 `canonical_json_bytes` 或等价 helper；但 `diagnostic_payload.py` 按 Section 6 item 2 "只依赖标准库和 `dayu.contracts.json_value.JsonValue`"，不得 import `dayu.runtime`。
- 实现需要自行做 `json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(',', ':'))` 后取 `len()`，但这与 runtime 的 canonicalization 可能不一致。

**建议**: 若 `dayu.runtime` 已有 canonical JSON helper，应评估是否允许 `diagnostic_payload.py` 依赖 `dayu.runtime`（`dayu.runtime` 是层中立基础设施，符合架构约束）。否则在 plan 中明确 byte size 计算使用 `json.dumps(..., sort_keys=True, separators=(',', ':'))` 即可，不要求与 durable canonicalization 一致（diagnostic 不是 durable truth）。

---

### FIND-10 [Low] `non_stream_parser.py` 的 `error_code="invalid_utf8"` 是局部字符串字面量

**证据**:
- `non_stream_parser.py:125`: `error_code="invalid_utf8"` — 模块级无对应常量。
- Plan Section 6 item 5 要求 "调用点必须传已有模块级错误码常量或新增模块级私有常量"，但此处的 `error_code` 赋值不在 plan 的修改范围内（因为 `raw_payload=None`，不需要 diagnostic payload helper）。
- 不修复不会扩散问题，但与 plan 的"无魔法字符串"原则不一致。

**建议**: 可选在 Slice 1 或 Slice 2 中将 `"invalid_utf8"` 提升为 `non_stream_parser.py` 模块级常量 `_INVALID_UTF8_CODE`（注意与 sse_parser 的同名常量区分，各自模块私有）。若认为超出本 work unit 范围，在 plan 中明确 non-goal。

---

## Review Lens 逐项检查

### 1. 是否符合 design_doc 设计目标

**PASS**。Plan 明确:
- Engine 只执行单次 `AgentRunRequest`，diagnostic payload helper 是 OpenAI runner 内部私有模块，不拥有 Host lifecycle/state。
- 不修改 Host 状态机、EventLog schema、durable schema。
- 不把 Host 状态机逻辑下沉到 Engine。

### 2. 是否符合 control_doc WU-ENGINE-01 范围

**PASS**。Plan 严格对齐 control doc 的三项目标:
1. Engine runner diagnostic payload audit: 核查 raw_payload 边界/脱敏/安全性/大小约束 — Section 6 提供了完整的约束设计。
2. 补 stream/non-stream error object consistency 测试 — Section 8 提供了具体测试要求。
3. 不重写 provider state — Section 4 和 Section 5 明确 disallowed。

### 3. Plan 是否 code-generation-ready

**PASS with findings**。三个 slice 均有:
- 明确的 allowed files。
- 具体的 exact changes（FIND-01 指出一处遗漏，但不影响整体可实施性）。
- 验证命令和 stop conditions。
- completion signals。

FIND-02（缺独立单元测试）、FIND-03（provider error 提取规则）、FIND-04（fallback 行为）、FIND-05（reason 常量）均属于可在一个 plan fix 中解决的细化问题，不阻塞 implementation。

### 4. 是否有过度设计、过度耦合、public contract 越界

**PASS**。Plan:
- Public contract shape 不变（Section 5 明确 no public contract shape change）。
- Helper 只依赖标准库和 `dayu.contracts.json_value`，不引入跨层依赖。
- 不创建 provider abstraction redesign（Section 1: "不推翻 typed provider state"）。
- 不引入兼容 facade / wrapper / re-export（Section 4 disallowed）。
- 4 个 helper 函数职责清晰、无 god function 倾向。

### 5. 是否违反 CLAUDE.md 编码约束

**PASS**。Plan 明确要求:
- 无 `Any`/`object`/无类型参数（Section 6 item 9）。
- 无 `hasattr`/`getattr` 逃避类型边界（Section 6 item 10）。
- 无魔法数字/魔法字符串 — 模块级私有常量（Section 6 item 3）；FIND-01 和 FIND-10 指出了当前代码和 plan 中的残留魔法字符串，但不构成违反 plan 设计意图的 blocking issue。
- 中文 docstring（Section 6 item 1）。
- 无兼容 facade / extra payload（Section 4 disallowed）。
- pyright 验证命令已包含在每个 slice 中。

### 6. Stream / Non-stream Error Object Consistency 测试覆盖

**PASS**。Plan Section 8 定义了 6 项 consistency 断言:
1. 事件序列均为 `PROVIDER_PROTOCOL_ERROR` + `RUNNER_DONE(ERROR)`。
2. 同一 provider error message。
3. 两条路径 raw_payload 都是 bounded diagnostic payload。
4. Common fields 一致: digest、byte_size、provider error code、provider error type、provider error param。
5. 不含 secret-like 字段值。
6. 允许 `error_code` 保持 path-specific。

FIND-08 指出 "provider error code" 术语歧义，但不影响测试的实际覆盖意图。

---

## Residual Risk / Open Questions

- **RR-01**: `diagnostic_payload.py` 的 `canonical_json_bytes` 计算与 `dayu.runtime` canonicalization 的一致性。若未来 `dayu.runtime` 变更 canonical JSON 算法，diagnostic payload 中的 byte_size 不会自动同步。风险低 — diagnostic 不是 durable truth。
- **RR-02**: `_SENSITIVE_KEY_FRAGMENTS` 的匹配策略（substring / case-insensitive / exact）未定义。若匹配过宽，可能误杀非敏感字段；若过窄，可能漏过。建议在 helper 中明确定义匹配策略并测试。

---

## Recommendation

**建议进入 plan fix**。6 条 medium findings 应在 plan fix 中解决（主要是补充细节，不需要架构改动），之后可进入 implementation gate。所有 findings 均不涉及 scope 重新定义、架构边界变更或 Host/Engine 契约重谈。

- Plan review artifact: `docs/reviews/wu-engine-01-plan-review-ds-20260602.md`
- 结论: **PASS** (0 blocking, 6 medium, 4 low)
- 建议: 进入 plan fix → plan re-review → implementation
