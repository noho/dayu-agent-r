# WU-ENGINE-01 Plan Re-Review — AgentMiMo

## Review Context

- Work unit: WU-ENGINE-01 Runner diagnostic payload audit.
- Gate: plan re-review。
- Updated plan: `docs/host/wu-engine-01-runner-diagnostic-payload-audit-plan.md`。
- Plan fix artifact: `docs/reviews/wu-engine-01-plan-fix-codex-20260602.md`。
- Original review: `docs/reviews/wu-engine-01-plan-review-mimo-20260602.md`。
- Controller adjudication: `docs/reviews/wu-engine-01-plan-review-controller-adjudication-20260602.md`。
- Reviewer: AgentMiMo (mimo)。

## 任务范围

只复核 controller accepted findings 是否已修入 plan。不重新扩大范围。

## Per-finding 复核

### MIMO-M-01 / DS-FIND-02 / DS-FIND-03 / DS-FIND-04 / DS-FIND-05 / DS-RR-02

**要求**: 补 `_SENSITIVE_KEY_FRAGMENTS` 初始值与匹配策略、独立 `test_diagnostic_payload.py`、provider error sub-object 提取规则、fallback 优先级、两种 missing choices reason 常量。

**Plan 状态**: 全部已修入。

- `_SENSITIVE_KEY_FRAGMENTS` 初始值: §6.3 行 91 `("api_key", "secret", "token", "password", "authorization", "credential")`。
- 匹配策略: §6.11 行 115 "case-insensitive substring match：把 key 转为 lowercase 后，只要包含 `_SENSITIVE_KEY_FRAGMENTS` 任一片段"。
- `test_diagnostic_payload.py`: §4 行 52 已列为 test allowed file；§7.1 行 159-165 明确 helper 单测覆盖范围。
- Provider error sub-object 提取: §6.10 行 114 明确 `payload["error"]` 子对象查找与 `code` / `type` / `param` 提取；§7.1 行 164 明确测试覆盖。
- Fallback 优先级: §6.12 行 116-119 明确三级 fallback（截断 preview → 删除 preview 保留最小结构 → warning + 最小结构）。
- Reason 常量: §7.1 行 153 明确 `_MISSING_CHOICES_AND_USAGE_REASON` 与 `_NO_VALID_CHOICE_OBJECT_REASON`。

**结论**: fixed。

### MIMO-M-02

**要求**: 写明 initial version = 1；Host ingest 当前 opaque 写入，不做 version-aware read。

**Plan 状态**: 已修入。

- §6.3 行 86: `_DIAGNOSTIC_PAYLOAD_VERSION: int = 1`。
- §6.7 行 104: "Host ingest 当前只把 `raw_payload` 当 opaque `JsonValue` 写入 artifact descriptor，不做 version-aware read，不解析该 payload。未来若 Host、projection 或分析工具需要解析 diagnostic payload，必须作为独立 design 重新定义 version-aware read / migration / compatibility 规则。"

**结论**: fixed。

### DS-FIND-01

**要求**: Slice 1 exact changes 增加 `sse_parser.py` 的 `_INVALID_UTF8_CODE` / `_TRUNCATED_UTF8_TAIL_CODE` 模块级私有常量。

**Plan 状态**: 已修入。

- §6.5 行 101: "sse_parser.py invalid UTF-8 使用 `_INVALID_UTF8_CODE` / `_TRUNCATED_UTF8_TAIL_CODE` 私有常量；若当前代码只有局部字符串，先提升为模块级私有常量。"
- §7.1 行 149: "在 `sse_parser.py` 将 `_handle_invalid_utf8` 的局部 error code 字符串提升为模块级私有常量：`_INVALID_UTF8_CODE = \"invalid_utf8\"` 与 `_TRUNCATED_UTF8_TAIL_CODE = \"truncated_utf8_tail\"`。"

代码验证: `sse_parser.py:222` 确认 `error_code = "truncated_utf8_tail" if final_decode else "invalid_utf8"` 是局部字符串。

**结论**: fixed。

### DS-FIND-06

**要求**: Slice 1 exact changes 增加 non-stream `_INVALID_UTF8_CODE` 模块级私有常量。

**Plan 状态**: 已修入。

- §7.1 行 150: "在 `non_stream_parser.py` 将 decode 失败路径的局部 `error_code=\"invalid_utf8\"` 提升为模块级私有常量 `_INVALID_UTF8_CODE = \"invalid_utf8\"`。该文件本 slice 已触及，按 controller preference 一并收口魔法字符串。"

代码验证: `non_stream_parser.py:125` 确认 `error_code="invalid_utf8"` 是局部字符串。该路径 `raw_payload=None`（行 128），不涉及 diagnostic payload helper 调用，只做常量提升。

**结论**: fixed。

### MIMO-L-01

**要求**: 更新 motivation / direct evidence wording，区分 invalid UTF-8 的已有 custom payload 与 `dict(parsed)` 原样路径。

**Plan 状态**: 已修入。

- §2 行 19: "SSE invalid UTF-8 路径不是 `dict(parsed)`：它已有 `chunk_base64` / `final_decode` custom payload，但缺少显式 byte-size bound。"
- §3 行 31: "对 invalid UTF-8 chunk 使用 custom payload：`chunk_base64` + `final_decode`；该路径不是 `dict(parsed)`，但缺少显式最大输出常量和 byte-size bound。"

**结论**: fixed。

### MIMO-L-02 / DS-FIND-07

**要求**: redaction 测试改为构造敏感字段，用 `json.dumps(..., ensure_ascii=False)` 或递归叶子检查，不使用 `repr(raw_payload)`。

**Plan 状态**: 已修入。

- §7.1 行 162: "redaction 使用包含敏感字段的输入，至少覆盖 `api_key`、`secret`、`token`、`password`、`authorization`、`credential` 中的多个片段。"
- §7.1 行 170: "redaction 测试必须构造敏感字段；断言使用 `json.dumps(raw_payload, ensure_ascii=False)` 或递归叶子值检查，不使用 `repr(raw_payload)`。"
- §8 行 293: "测试必须构造敏感字段，并用 `json.dumps(raw_payload, ensure_ascii=False)` 或递归叶子值检查。"
- §7.2 行 224: HTTP 测试同样要求 "增加敏感字段输入；断言使用 `json.dumps(raw_payload, ensure_ascii=False)` 或递归叶子值检查，不使用 `repr(raw_payload)`。"

**结论**: fixed。

### DS-FIND-08

**要求**: 区分 "provider error object 内的 `code` 字段" 与 "`RunnerProtocolErrorData.error_code`"。

**Plan 状态**: 已修入。

- §6.9 行 112: "provider error object 内的 bounded `code` / `type` / `param` 等低风险短字段"。
- §6.17 行 124: "`RunnerProtocolErrorData.error_code` 可以继续保持 path-specific"。
- §8 行 292: "provider error object 内的 `code` 字段、provider error object 内的 `type` 字段、provider error object 内的 `param` 字段"。

**结论**: fixed。

### DS-FIND-09 / DS-RR-01

**要求**: 明确 canonical byte size / digest 使用 local `json.dumps(..., sort_keys=True, ensure_ascii=False, separators=(',', ':'))`，不依赖 `dayu.runtime`。

**Plan 状态**: 已修入。

- §6.8 行 105: "canonical byte size / digest 使用 helper 本地算法：`json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(\",\", \":\"))` 得到 canonical text，UTF-8 encode 后计算 byte size 与 SHA-256 digest。不依赖 `dayu.runtime`，不要求与 Host durable canonicalization 一致；该 digest 只服务 diagnostic，不是 durable truth。"
- §7.1 行 165: "canonical byte size / digest 与 local `json.dumps(..., sort_keys=True, ensure_ascii=False, separators=(',', ':'))` 算法一致。"

**结论**: fixed。

### DS-FIND-10

**要求**: HTTP 测试新名称 `test_http_json_object_error_body_produces_bounded_diagnostic_payload`。

**Plan 状态**: 已修入。

- §7.2 行 220: "`test_http_json_object_error_body_preserved_as_raw_payload` 改名为 `test_http_json_object_error_body_produces_bounded_diagnostic_payload`。"

**结论**: fixed。

## 新引入问题检查

逐项检查 plan fix 是否引入新 blocker：

1. **`_SENSITIVE_KEY_FRAGMENTS` case-insensitive substring match**: 合理，不引入过度设计。
2. **`protocol_object_diagnostic_payload` 两种 reason**: 不扩大 scope，只区分 missing choices 语义。
3. **`non_stream_parser.py` `_INVALID_UTF8_CODE` 常量提升**: 该路径 `raw_payload=None`（行 128），只做常量提升，不涉及 helper 调用，不引入新行为。
4. **canonical byte size 本地算法**: 明确不依赖 `dayu.runtime`，不引入跨层耦合。
5. **Fallback 三级顺序**: 最小结构（version/source/kind/canonical_byte_size/sha256_digest）理论大小远低于 `_DIAGNOSTIC_PAYLOAD_MAX_BYTES`，无死循环风险。
6. **Redaction test method**: `json.dumps(..., ensure_ascii=False)` 或递归叶子检查是合理替代，不引入 `repr` 依赖。

未发现新引入 blocker。

## Conclusion

**PASS — 无 remaining finding。**

Controller adjudication 中全部 10 项 accepted findings 已修入 updated plan。Plan fix 未引入新 blocker。Plan code-generation-ready 程度充分。

**建议**: 进入 accepted plan commit / implementation。
