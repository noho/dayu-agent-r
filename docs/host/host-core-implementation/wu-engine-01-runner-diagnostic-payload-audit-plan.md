# WU-ENGINE-01 Runner Diagnostic Payload Audit Plan

## 1. Gate / Role / Scope

- Gate: `planning`。
- Role: planning agent；本 artifact 只提供 code-generation-ready plan，不启动完整 Gateflow workflow，不提交、不 push、不创建 PR。
- Work unit: `WU-ENGINE-01`。
- 分支: `refactor/wu-engine-01-runner-diagnostic-payload-audit`。
- 设计真源: `docs/host/design.md`。
- 总控文档: `docs/host/host-core-followup-implementation-control.md`。
- Controller code-inspection artifact: `docs/reviews/wu-engine-01-code-inspection-controller-20260602.md`。

## 2. Motivation / Root Cause 判断

问题真实存在，但边界比历史标题窄。

直接证据显示，现有代码已经使用 typed provider state / sealed union；本 work unit 不应推翻这条方向，也不应把 provider state 退回 raw JSON / metadata bag。当前真实风险是 Engine runner diagnostic error payload 的治理边界：多个 OpenAI-compatible parser 分支把 provider 返回的 JSON object 原样放进 `raw_payload`，随后 Engine Agent 原样提升到 `ProviderProtocolErrorData`，Host ingest 再把它写入 diagnostic raw payload artifact。

Root cause 是诊断载荷生成点缺少统一的有界、脱敏、摘要化 owner，而不是 Host 状态机或 provider state contract 设计错误。HTTP 错误体读取已有 `_HTTP_ERROR_BODY_MAX_BYTES` 字节上限，但 HTTP JSON object 仍被作为 `raw_payload` 保存；non-stream provider error object、SSE provider error object、SSE missing choices / no valid choice object 等协议错误路径还存在 `raw_payload=dict(parsed)`。SSE invalid UTF-8 路径不是 `dict(parsed)`：它已有 `chunk_base64` / `final_decode` custom payload，但缺少显式 byte-size bound。stream / non-stream provider error object 的诊断语义也缺少 parity 测试。

因此最佳方案是：在 OpenAI runner 内部新增一个私有 bounded diagnostic payload helper，把所有 diagnostic `raw_payload` 写入点收敛为同一套摘要/脱敏/大小约束；保持 public dataclass 字段形状不变。

## 3. Direct Evidence

- `dayu/engine/contracts/runner_events.py:147` 定义 `RunnerProtocolErrorData.raw_payload: JsonValue | None`；`dayu/engine/contracts/runner_events.py:168` 定义 `RunnerHTTPErrorData.raw_payload: JsonValue | None`。
- `dayu/engine/contracts/engine_events.py:290` 定义 `ProviderProtocolErrorData.raw_payload: JsonValue | None`。
- `dayu/engine/runners/openai/runner.py:86` 定义 `_HTTP_ERROR_BODY_MAX_BYTES = 65_536`；`dayu/engine/runners/openai/runner.py:900` 通过 `_safe_read_error_body_bytes` 有界读取 HTTP error body；`dayu/engine/runners/openai/runner.py:893` 仍把 JSON object 作为 `raw_payload`。
- `dayu/engine/runners/openai/non_stream_parser.py:218` 在顶层 `error` 存在时产出 `RunnerProtocolErrorData`；`dayu/engine/runners/openai/non_stream_parser.py:227` 当前使用 `raw_payload=dict(parsed)`。
- `dayu/engine/runners/openai/sse_parser.py:330` 在 SSE provider error object 分支产出协议错误；`dayu/engine/runners/openai/sse_parser.py:338` 当前使用 `raw_payload=dict(parsed)`。
- `dayu/engine/runners/openai/sse_parser.py:354` / `dayu/engine/runners/openai/sse_parser.py:391` 的 missing choices / invalid choice object 分支也使用 `raw_payload=dict(parsed)`。
- `dayu/engine/runners/openai/sse_parser.py:233` 对 invalid UTF-8 chunk 使用 custom payload：`chunk_base64` + `final_decode`；该路径不是 `dict(parsed)`，但缺少显式最大输出常量和 byte-size bound。
- `tests/engine/runners/openai/test_protocol_error.py:102` 与 `tests/engine/runners/openai/test_protocol_error.py:132` 当前断言 SSE / non-stream provider error object 的 `raw_payload` 精确保留。
- `tests/engine/runners/openai/test_stream_non_stream_terminal_parity.py:60` 和 `tests/engine/runners/openai/test_stream_non_stream_terminal_parity.py:127` 覆盖成功终态 parity，但未覆盖 provider error object parity。
- `dayu/engine/agent.py:1234` 把 `RunnerProtocolErrorData` 提升为 `ProviderProtocolErrorData`；`dayu/engine/agent.py:1259` 原样透传 `raw_payload`。
- `dayu/host/engine_ingest.py:2400` 写入 `ProviderProtocolErrorData.raw_payload` 的 artifact descriptor；`tests/host/test_engine_ingest_mapping.py:1526` 只断言 provider protocol error 是 diagnostic 且有 `raw_payload_ref`，不要求原始 JSON 内容。

## 4. Affected Files / Modules

Production allowed files:

- `dayu/engine/runners/openai/diagnostic_payload.py`：新增 OpenAI runner 内部诊断载荷 helper。
- `dayu/engine/runners/openai/non_stream_parser.py`：替换 provider error object 的 `raw_payload=dict(parsed)`。
- `dayu/engine/runners/openai/sse_parser.py`：替换 provider error、missing choices、invalid choice object、invalid UTF-8 的 raw diagnostic payload。
- `dayu/engine/runners/openai/runner.py`：HTTP JSON error body 的 `raw_payload` 通过同一 helper 摘要化；保留 `_HTTP_ERROR_BODY_MAX_BYTES` 读取上限。
- `dayu/engine/contracts/runner_events.py`：仅更新中文 docstring，把 `raw_payload` 说明从“原始载荷”改为“有界诊断载荷”。
- `dayu/engine/contracts/engine_events.py`：仅更新中文 docstring，同步 `ProviderProtocolErrorData.raw_payload` 语义。
- `dayu/engine/README.md`：仅当实现确实改变稳定 developer contract 说明时，增加一条简短说明：runner/provider diagnostic `raw_payload` 是有界、脱敏、摘要化 JSON，不保证保留 provider 原始 payload。

Test allowed files:

- `tests/engine/runners/openai/test_protocol_error.py`。
- `tests/engine/runners/openai/test_diagnostic_payload.py`。
- `tests/engine/runners/openai/test_stream_non_stream_terminal_parity.py`。
- `tests/engine/runners/openai/test_http_error_event.py`。
- `tests/host/test_engine_ingest_mapping.py`。

Explicitly disallowed:

- 不修改 Host 状态机、Host ingest production 行为、EventLog schema、provider state sealed union、provider extension config、reasoning/tool call state 投影。
- 不新增兼容 facade / wrapper / re-export。
- 不把显式参数塞进 `extra payload` / metadata bag。

## 5. Contract / Schema / Public Interface Decision

No public contract shape change.

保持以下字段、dataclass、union、event type 形状不变：

- `RunnerProtocolErrorData.raw_payload: JsonValue | None`
- `RunnerHTTPErrorData.raw_payload: JsonValue | None`
- `ProviderProtocolErrorData.raw_payload: JsonValue | None`
- `RunnerEventData` / `EngineEventData` 封闭联合成员不变。
- Host durable schema 与 Host event type 不变。

允许且必须做的语义澄清：

- `raw_payload` 字段仍承载 diagnostic JSON，但不再承诺保存 provider 原始 JSON object。
- OpenAI-compatible runner 写入该字段时必须使用有界、脱敏、摘要化 payload。
- `message`、`error_code`、`provider_request_id` 继续作为显式字段承载核心错误事实，不放进 opaque diagnostic bag。

## 6. Implementation Decisions

1. 新增 `dayu/engine/runners/openai/diagnostic_payload.py`，模块提供中文概览 docstring。所有函数必须有完整中文 docstring，包含参数、返回值、异常。
2. helper 只依赖标准库和 `dayu.contracts.json_value.JsonValue`，不得 import Host / Service / UI / Fins。
3. helper 使用模块级私有常量，禁止散落魔法数字/魔法字符串。建议常量：
   - `_DIAGNOSTIC_PAYLOAD_VERSION: int = 1`
   - `_DIAGNOSTIC_PAYLOAD_MAX_BYTES: int`
   - `_DIAGNOSTIC_KEYS_MAX_ITEMS: int`
   - `_DIAGNOSTIC_SCALAR_MAX_CHARS: int`
   - `_DIAGNOSTIC_CHUNK_PREFIX_MAX_BYTES: int`
   - `_SENSITIVE_KEY_FRAGMENTS: tuple[str, ...] = ("api_key", "secret", "token", "password", "authorization", "credential")`
4. helper public-to-module API 使用直接参数，不使用 callback/factory/profile/query。建议函数：
   - `provider_error_diagnostic_payload(payload: dict[str, JsonValue], *, source: str) -> JsonValue`
   - `protocol_object_diagnostic_payload(payload: dict[str, JsonValue], *, source: str, reason: str) -> JsonValue`
   - `invalid_utf8_diagnostic_payload(chunk: bytes, *, final_decode: bool) -> JsonValue`
   - `http_error_diagnostic_payload(payload: dict[str, JsonValue]) -> JsonValue`
5. `source` / `reason` 不允许调用点直接写字符串字面量。调用点必须传已有模块级错误码常量或新增模块级私有常量：
   - `non_stream_parser.py` provider error 使用现有 `_PROVIDER_ERROR_CODE`。
   - `sse_parser.py` provider error 使用现有 `_PROVIDER_ERROR_CODE`。
   - `sse_parser.py` missing choices 使用现有 `_MISSING_CHOICES_CODE`。
   - `sse_parser.py` invalid UTF-8 使用 `_INVALID_UTF8_CODE` / `_TRUNCATED_UTF8_TAIL_CODE` 私有常量；若当前代码只有局部字符串，先提升为模块级私有常量。
   - `runner.py` HTTP error body 使用 helper 内部固定 source，不在调用点传字符串。
6. helper 输出必须是 JSON object 形态的 `JsonValue`，且序列化后不超过 `_DIAGNOSTIC_PAYLOAD_MAX_BYTES`。如果某次摘要仍超过上限，helper 必须继续删除低价值字段或截断 bounded preview，而不是返回原 payload。
7. version 策略：initial diagnostic payload version 必须为 `1`。Host ingest 当前只把 `raw_payload` 当 opaque `JsonValue` 写入 artifact descriptor，不做 version-aware read，不解析该 payload。未来若 Host、projection 或分析工具需要解析 diagnostic payload，必须作为独立 design 重新定义 version-aware read / migration / compatibility 规则。
8. canonical byte size / digest 使用 helper 本地算法：`json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))` 得到 canonical text，UTF-8 encode 后计算 byte size 与 SHA-256 digest。不依赖 `dayu.runtime`，不要求与 Host durable canonicalization 一致；该 digest 只服务 diagnostic，不是 durable truth。
9. helper 不保存完整 provider payload。建议输出字段只包含：
   - diagnostic schema version；
   - source / kind；
   - 原 payload canonical JSON byte size；
   - 原 payload SHA-256 digest；
   - bounded top-level keys；
   - provider error object 内的 bounded `code` / `type` / `param` 等低风险短字段；
   - invalid UTF-8 的 chunk byte size、chunk SHA-256、bounded prefix base64、`final_decode`。
10. `provider_error_diagnostic_payload` 必须固定查找 `payload["error"]` 子对象：当该值是 dict 时，从子对象内提取 `code` / `type` / `param` 等低风险短字段，并对每个字符串值应用 `_DIAGNOSTIC_SCALAR_MAX_CHARS` 上限；同时仍保留 bounded top-level keys。不得从顶层把完整 `error` 子对象写入 diagnostic payload。
11. 对敏感字段采用 key-fragment redaction。匹配策略是 case-insensitive substring match：把 key 转为 lowercase 后，只要包含 `_SENSITIVE_KEY_FRAGMENTS` 任一片段，就认为该 key 敏感。敏感字段值不得进入摘要；摘要中可以保留字段名或 redacted marker，但不得保留 secret 值。
12. 超出 `_DIAGNOSTIC_PAYLOAD_MAX_BYTES` 的 fallback 顺序必须固定：
   - 先截断 bounded preview / scalar preview。
   - 仍超限时，删除 preview 与 top-level keys，仅保留最小结构：`version`、`source`、`kind`、`canonical_byte_size`、`sha256_digest`。
   - 如果最小结构理论上仍超限，记录 warning 日志并返回最小结构；不得无限循环或返回原始 payload。
13. 不使用 `Any`、`object`、无类型参数、无类型返回值。处理 `json.loads` 结果时必须尽快通过 `isinstance(..., dict)` 收窄到 `dict[str, JsonValue]`，再交给 helper。
14. 不使用 `hasattr` / `getattr` 逃避类型边界。
15. 不引入 provider-specific 兼容 facade；OpenAI-compatible runner 内部 helper 是诊断归一 owner，不是 provider abstraction redesign。
16. `RunnerHTTPErrorData.message` 仍保留 `_HTTP_ERROR_BODY_MAX_BYTES` 内的文本诊断；只把 HTTP JSON object 的 `raw_payload` 改为摘要化 diagnostic payload。
17. stream / non-stream provider error object 的 `RunnerProtocolErrorData.error_code` 可以继续保持 path-specific：`sse_provider_error` 与 `non_stream_provider_error`。parity 测试应断言事件序列、message、done terminal、provider request id、diagnostic payload common fields 一致，而不是强行统一 runner-level error code。

## 7. Slices

### Slice 1: Protocol Diagnostic Payload Helper + Parser 收口

Objective:

- 关闭 `RunnerProtocolErrorData.raw_payload` 中的无界/原样 provider JSON 保存路径。
- 为 stream / non-stream provider error object 增加 diagnostic payload consistency 测试。

Allowed files:

- `dayu/engine/runners/openai/diagnostic_payload.py`
- `dayu/engine/runners/openai/non_stream_parser.py`
- `dayu/engine/runners/openai/sse_parser.py`
- `dayu/engine/contracts/runner_events.py`
- `dayu/engine/contracts/engine_events.py`
- `tests/engine/runners/openai/test_diagnostic_payload.py`
- `tests/engine/runners/openai/test_protocol_error.py`
- `tests/engine/runners/openai/test_stream_non_stream_terminal_parity.py`

Exact changes:

- 新增 diagnostic payload helper，按第 6 节 decisions 实现。
- 在 `sse_parser.py` 将 `_handle_invalid_utf8` 的局部 error code 字符串提升为模块级私有常量：`_INVALID_UTF8_CODE = "invalid_utf8"` 与 `_TRUNCATED_UTF8_TAIL_CODE = "truncated_utf8_tail"`。
- 在 `non_stream_parser.py` 将 decode 失败路径的局部 `error_code="invalid_utf8"` 提升为模块级私有常量 `_INVALID_UTF8_CODE = "invalid_utf8"`。该文件本 slice 已触及，按 controller preference 一并收口魔法字符串。
- `non_stream_parser.py` 中 `raw_payload=dict(parsed)` 替换为 `provider_error_diagnostic_payload(parsed, source=_PROVIDER_ERROR_CODE)`。
- `sse_parser.py` 中 provider error object 的 `raw_payload=dict(parsed)` 替换为 `provider_error_diagnostic_payload(parsed, source=_PROVIDER_ERROR_CODE)`。
- 在 `sse_parser.py` 新增两种 missing choices reason 常量：`_MISSING_CHOICES_AND_USAGE_REASON` 表示既无有效 choices 也无有效 usage；`_NO_VALID_CHOICE_OBJECT_REASON` 表示 choices list 存在但没有可解析 object choice。
- `sse_parser.py` 中 missing choices / invalid choice object 的 `raw_payload=dict(parsed)` 替换为 `protocol_object_diagnostic_payload(...)`：
  - 既无有效 choices 也无有效 usage：`source=_MISSING_CHOICES_CODE, reason=_MISSING_CHOICES_AND_USAGE_REASON`。
  - choices list 全部不是 object：`source=_MISSING_CHOICES_CODE, reason=_NO_VALID_CHOICE_OBJECT_REASON`。
- `sse_parser.py` 中 invalid UTF-8 的 full chunk base64 替换为 `invalid_utf8_diagnostic_payload(...)`，必须显式记录 byte size / digest / bounded prefix。
- 更新 `RunnerProtocolErrorData` 与 `ProviderProtocolErrorData` 中文 docstring：`raw_payload` 是有界诊断载荷，不承诺原始 provider payload。
- 新增 `tests/engine/runners/openai/test_diagnostic_payload.py`，直接覆盖 helper：
  - 正常输出结构包含 version/source/kind/canonical_byte_size/sha256_digest。
  - serialized diagnostic payload 不超过 `_DIAGNOSTIC_PAYLOAD_MAX_BYTES`。
  - redaction 使用包含敏感字段的输入，至少覆盖 `api_key`、`secret`、`token`、`password`、`authorization`、`credential` 中的多个片段。
  - 超大 payload 的 fallback 顺序可观测，最小结构仍保留 version/source/kind/canonical_byte_size/sha256_digest。
  - provider error sub-object 提取 `payload["error"]["code"]` / `type` / `param`，同时保留 bounded top-level keys。
  - canonical byte size / digest 与 local `json.dumps(..., sort_keys=True, ensure_ascii=False, separators=(",", ":"))` 算法一致。
- 更新 `test_protocol_error.py`：
  - 删除 provider error object raw_payload 精确保留断言；
  - 断言 diagnostic payload 是 dict-like JSON object；
  - 断言包含 digest / byte size / bounded provider error object 内的 `code` 或 `type`；
  - redaction 测试必须构造敏感字段；断言使用 `json.dumps(raw_payload, ensure_ascii=False)` 或递归叶子值检查，不使用 `repr(raw_payload)`；
  - 增加大 payload 测试，断言 serialized diagnostic payload byte size 不超过 helper 常量。
- 更新 `test_stream_non_stream_terminal_parity.py`：
  - 新增 provider error object consistency 测试；
  - 构造语义等价的 SSE 与 non-stream error object；
  - 断言两条路径事件序列均为 `PROVIDER_PROTOCOL_ERROR` + `RUNNER_DONE(ERROR)`；
  - 断言 `message` 相同、`provider_request_id` 分别保留、diagnostic payload 的 digest / provider error object 内的 `code` / `type` 等 common fields 一致；
  - 允许 `error_code` 仍为 path-specific。

Tests / validation commands:

```bash
source .venv/bin/activate && pytest -q tests/engine/runners/openai/test_diagnostic_payload.py tests/engine/runners/openai/test_protocol_error.py tests/engine/runners/openai/test_stream_non_stream_terminal_parity.py
source .venv/bin/activate && pyright
```

Stop condition:

- 如果 helper 需要改变 `RunnerProtocolErrorData` / `ProviderProtocolErrorData` 字段形状、增加 public event type、或要求 Host production 改写 raw payload artifact 语义，立即停止并交回 controller。
- 如果 pyright 要求使用 `Any` / `object` 才能通过，应停止并重新收敛类型边界。

Completion signal:

- 协议错误 raw payload 不再有 `dict(parsed)`。
- stream / non-stream provider error object consistency 测试存在并通过。
- invalid UTF-8 diagnostic payload 显式有界。
- helper 单元测试直接覆盖结构、大小上限、redaction、fallback、provider error sub-object 提取、canonical byte size/digest。

### Slice 2: HTTP Error Raw Payload 摘要化 + Host 诊断映射守卫

Objective:

- 在已有 HTTP error body byte cap 基础上，避免 HTTP JSON object 作为 exact raw payload 写入 runner diagnostic。
- 验证 Host ingest 继续只把 provider protocol error 当 diagnostic，不引入状态机变化。

Allowed files:

- `dayu/engine/runners/openai/diagnostic_payload.py`
- `dayu/engine/runners/openai/runner.py`
- `dayu/engine/contracts/runner_events.py`
- `tests/engine/runners/openai/test_http_error_event.py`
- `tests/host/test_engine_ingest_mapping.py`
- `dayu/engine/README.md`

Exact changes:

- `runner.py` 的 `_safe_read_error_body` 中，`decoded` 为 dict 时不再直接返回 `decoded`，改为 `http_error_diagnostic_payload(decoded)`。
- 保留 `_HTTP_ERROR_BODY_MAX_BYTES` 和 `_safe_read_error_body_bytes` 行为，不扩大为 response body streaming redesign。
- 更新 `RunnerHTTPErrorData` 中文 docstring：HTTP `raw_payload` 是从有界 HTTP body 派生的有界诊断载荷；非 JSON 或解析失败仍为 `None`。
- 更新 `test_http_error_event.py`：
  - `test_http_json_object_error_body_preserved_as_raw_payload` 改名为 `test_http_json_object_error_body_produces_bounded_diagnostic_payload`；
  - 不再断言 exact payload；
  - 断言 provider request id 仍只来自 header；
  - 断言 diagnostic payload 含 digest / byte size / provider error object 内的 `code` 或 `type`；
  - 增加敏感字段输入；断言使用 `json.dumps(raw_payload, ensure_ascii=False)` 或递归叶子值检查，不使用 `repr(raw_payload)`；
  - 保留 `test_http_error_body_is_capped_before_decode`，并额外断言 raw payload 不保存超大原始 JSON。
- 更新 `tests/host/test_engine_ingest_mapping.py`：
  - `test_provider_protocol_error_is_diagnostic_without_state_change` 保持状态机断言；
  - 若测试数据要更贴近新语义，把 `raw_payload={"raw": "payload"}` 改为 helper-like diagnostic JSON object；仍只断言 `raw_payload_ref` 存在和 Run / Attempt 状态不变。
- 更新 `dayu/engine/README.md`：
  - 只增加稳定 contract 级别说明；
  - 不写实现细节、不写未来计划、不写 changelog。

Tests / validation commands:

```bash
source .venv/bin/activate && pytest -q tests/engine/runners/openai/test_diagnostic_payload.py tests/engine/runners/openai/test_http_error_event.py tests/host/test_engine_ingest_mapping.py
source .venv/bin/activate && pyright
```

Stop condition:

- 如果 HTTP message 文本也需要改变或引入新 public HTTP error dataclass 字段，停止并交回 controller。
- 如果 Host ingest production 需要变更状态机、EventLog schema 或 artifact writer 才能通过测试，停止；这超出本 work unit。

Completion signal:

- HTTP JSON error body 不再作为 exact raw payload 保存。
- HTTP error body byte cap 测试仍通过。
- Host provider protocol diagnostic ingest 仍不改变 active Run / Attempt 状态。

### Slice 3: Full Validation / Docs Sync

Objective:

- 汇总验证本 work unit 的所有受影响边界。

Allowed files:

- `dayu/engine/README.md`
- 本 work unit 已允许的 source/test 文件；不得新增 scope。

Exact changes:

- 只在 Slice 1 / Slice 2 尚未完成 README 同步时补齐 `dayu/engine/README.md`。
- 不更新 `docs/host/design.md`：本计划不改变 Host 架构真源、状态机、公共接口或 durable schema。
- 不更新根目录 README、`dayu/host/README.md`、`tests/README.md`，除非 implementation 实际改变了对应文档职责内的稳定说明。

Validation commands:

```bash
source .venv/bin/activate && pytest -q tests/engine/runners/openai/test_diagnostic_payload.py tests/engine/runners/openai/test_protocol_error.py tests/engine/runners/openai/test_stream_non_stream_terminal_parity.py tests/engine/runners/openai/test_http_error_event.py tests/host/test_engine_ingest_mapping.py
source .venv/bin/activate && pyright
```

Stop condition:

- 如果 full validation 暴露非本 work unit 的既有 pyright 错误，implementation report 必须区分“既有错误”与“本次新增/扩散”；若本次触及文件导致错误继续扩散，必须在本 work unit 内修复。

Completion signal:

- 受影响测试通过。
- pyright 无新增或扩散报错。
- docs decision 已完成。

## 8. Stream / Non-stream Error Object Consistency 测试要求

必须新增或更新测试覆盖以下行为：

- stream 和 non-stream provider error object 都产出 `PROVIDER_PROTOCOL_ERROR` 后紧跟 `RUNNER_DONE(ERROR)`。
- 两条路径提取同一 provider error message。
- 两条路径的 `raw_payload` 都是 bounded diagnostic payload，不保留完整原始 provider JSON。
- 两条路径对同一 provider error object 产出的 diagnostic common fields 一致：payload digest、payload byte size、provider error object 内的 `code` 字段、provider error object 内的 `type` 字段、provider error object 内的 `param` 字段。
- 两条路径均不把 secret-like 字段值写入 diagnostic payload；测试必须构造敏感字段，并用 `json.dumps(raw_payload, ensure_ascii=False)` 或递归叶子值检查。
- 允许 `RunnerProtocolErrorData.error_code` 保持 path-specific：`sse_provider_error` / `non_stream_provider_error`。

## 9. Docs Decision

需要更新 `dayu/engine/README.md`，但只能窄更新。

理由：本 work unit 不改变 public contract shape，但会改变稳定 developer contract 说明：`raw_payload` 不再表示 provider 原始 JSON 精确保留，而是 bounded / redacted / summarized diagnostic JSON。`dayu/engine/README.md` 是 Engine 开发手册，说明 Engine 公共契约、RunnerEvent / EngineEvent 边界和扩展点；该语义属于它的职责范围。

不更新 `docs/host/design.md`：Host 架构、状态机、public command、durable schema、EventLog 语义不变。

不更新 `dayu/host/README.md`：Host production 行为不变，Host 仍只消费 `ProviderProtocolErrorData.raw_payload` 并写 diagnostic artifact ref。

## 10. Required Validation Commands

Targeted tests:

```bash
source .venv/bin/activate && pytest -q tests/engine/runners/openai/test_diagnostic_payload.py tests/engine/runners/openai/test_protocol_error.py tests/engine/runners/openai/test_stream_non_stream_terminal_parity.py tests/engine/runners/openai/test_http_error_event.py tests/host/test_engine_ingest_mapping.py
```

Type check:

```bash
source .venv/bin/activate && pyright
```

Implementation agent 必须在报告中明确：

- 哪些命令已运行；
- 是否通过；
- 若失败，失败是否由本 slice 引入；
- 是否存在既有 pyright 报错，以及本次是否新增/扩散。

## 11. Review Gates

- Plan review 必须核查：是否仍误把问题扩大成 provider state 重构；slice 是否可直接实施；是否明确 no public contract shape change；测试是否覆盖 stream / non-stream error object consistency；docs decision 是否符合 README 职责。
- Code review 必须核查：是否仍存在 `raw_payload=dict(parsed)`；helper 是否真的有大小上限；secret-like 字段值是否可进入 diagnostic payload；是否引入 `Any` / `object` / getattr / extra payload；是否违反 OpenAI runner 层边界。
- Re-review 必须复核 accepted findings 的最终状态，并确认未引入 Host 状态机或 schema 变更。

## 12. Residual Risks / Open Questions

Blocking questions: none.

Residual risks: none requiring deferral. 本计划已把当前直接证据支撑的风险收敛到 Engine/OpenAI runner diagnostic payload helper、相关 parser/runner 写入点、stream/non-stream parity 测试和 Engine README 语义同步。

## 13. Completion Report Format

Implementation agent 完成每个 slice 后必须报告：

- Slice id / objective。
- Changed files。
- Implemented plan items。
- Tests / pyright commands and results。
- Docs decision and updated README path if applicable。
- Residual risks / uncovered areas；若无，写 `none`。
- Stop condition status；若未触发，写 `not triggered`。
