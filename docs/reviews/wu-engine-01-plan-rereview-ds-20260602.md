# WU-ENGINE-01 Plan Re-Review — AgentDS

## Gate / Role

- Gate: `plan re-review`。
- Role: independent plan review agent (AgentDS)，不是 controller，不修改 source/tests，不 commit/push/创建 PR。
- Review target: `docs/host/wu-engine-01-runner-diagnostic-payload-audit-plan.md` (post plan-fix)。
- Plan fix artifact: `docs/reviews/wu-engine-01-plan-fix-codex-20260602.md`。
- Original review artifact: `docs/reviews/wu-engine-01-plan-review-ds-20260602.md`。
- Controller adjudication: `docs/reviews/wu-engine-01-plan-review-controller-adjudication-20260602.md`。

## Scope

只复核 controller accepted findings 是否已修入 plan。不重新扩大范围。

## Per-Finding Verification

### MIMO-M-01 / DS-FIND-02 / DS-FIND-03 / DS-FIND-04 / DS-FIND-05 / DS-RR-02 — FIXED

Controller required: 补 `_SENSITIVE_KEY_FRAGMENTS` 初始值与匹配策略、独立 `test_diagnostic_payload.py`、provider error sub-object 提取规则、fallback 优先级、两种 missing choices reason 常量。

| Sub-item | Plan 位置 | 状态 |
|---|---|---|
| `_SENSITIVE_KEY_FRAGMENTS` 初始值 | Section 6 item 3: `("api_key", "secret", "token", "password", "authorization", "credential")` | ✓ |
| 匹配策略 case-insensitive substring | Section 6 item 11 | ✓ |
| 独立 `test_diagnostic_payload.py` | Section 4 allowed files (line 52), Slice 1 allowed files (line 142), exact changes (lines 159-165) | ✓ |
| provider error sub-object 提取 | Section 6 item 10: `payload["error"]` 子对象提取 `code`/`type`/`param` | ✓ |
| fallback 优先级 | Section 6 item 12: 三步固定顺序 (截断 preview → 最小结构 → warning log) | ✓ |
| 两种 missing choices reason 常量 | Section 7 lines 153-156: `_MISSING_CHOICES_AND_USAGE_REASON` / `_NO_VALID_CHOICE_OBJECT_REASON` + 使用点 | ✓ |

### MIMO-M-02 — FIXED

Controller required: version 初值 + Host 不解析策略。

| Sub-item | Plan 位置 | 状态 |
|---|---|---|
| initial version = 1 | Section 6 item 7 | ✓ |
| Host ingest opaque 写入，不 version-aware read | Section 6 item 7 | ✓ |
| 未来解析需独立 design | Section 6 item 7 | ✓ |

### DS-FIND-01 — FIXED

Controller required: SSE invalid UTF-8 error_code 常量提升。

| Sub-item | Plan 位置 | 状态 |
|---|---|---|
| `_INVALID_UTF8_CODE` / `_TRUNCATED_UTF8_TAIL_CODE` 提升 | Section 7 Slice 1 exact changes line 149 | ✓ |

### DS-FIND-06 — FIXED

Controller required: non-stream `_INVALID_UTF8_CODE` 模块级私有常量。

| Sub-item | Plan 位置 | 状态 |
|---|---|---|
| `non_stream_parser.py` `_INVALID_UTF8_CODE` 提升 | Section 7 Slice 1 exact changes line 150 | ✓ |

### MIMO-L-01 — FIXED

Controller required: motivation / direct evidence 区分 invalid UTF-8 custom payload 与 `dict(parsed)`。

| Sub-item | Plan 位置 | 状态 |
|---|---|---|
| Motivation 区分 | Section 2 lines 19-20: "SSE invalid UTF-8 路径不是 `dict(parsed)`" | ✓ |
| Direct evidence 区分 | Section 3 line 31: "custom payload：`chunk_base64` + `final_decode`" | ✓ |

### MIMO-L-02 / DS-FIND-07 — FIXED

Controller required: redaction 测试用 `json.dumps` 或递归叶子检查，不用 `repr`。

| Sub-item | Plan 位置 | 状态 |
|---|---|---|
| Slice 1 test_protocol_error 要求 | Section 7 line 170 | ✓ |
| Slice 2 test_http_error_event 要求 | Section 7 line 224 | ✓ |
| Section 8 consistency 要求 | Section 8 line 293 | ✓ |

### DS-FIND-08 — FIXED

Controller required: 术语区分 provider-level `code` 与 runner-level `error_code`。

| Sub-item | Plan 位置 | 状态 |
|---|---|---|
| Section 6 item 17 区分 | `RunnerProtocolErrorData.error_code` 明确命名 | ✓ |
| Section 8 区分 | "provider error object 内的 `code`/`type`/`param` 字段" | ✓ |
| Slice 1 区分 | "bounded provider error object 内的 `code` 或 `type`" | ✓ |
| Slice 1 parity 区分 | "provider error object 内的 `code` / `type` 等 common fields" | ✓ |

### DS-FIND-09 / DS-RR-01 — FIXED

Controller required: canonical byte size 使用 local `json.dumps` 算法。

| Sub-item | Plan 位置 | 状态 |
|---|---|---|
| 明确算法 | Section 6 item 8: `json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))` | ✓ |
| 不依赖 runtime | Section 6 item 8: "不依赖 `dayu.runtime`" | ✓ |
| 不与 durable 一致 | Section 6 item 8: "不要求与 Host durable canonicalization 一致" | ✓ |

### DS-FIND-10 — FIXED

Controller required: HTTP 测试新名称。

| Sub-item | Plan 位置 | 状态 |
|---|---|---|
| 新测试名 | Section 7 Slice 2 line 220: `test_http_json_object_error_body_produces_bounded_diagnostic_payload` | ✓ |

## 新增问题检查

对 plan fix 引入的新内容做一次快速扫描，确认未引入新的 blocking issue：

- **Section 6 item 10**: `provider_error_diagnostic_payload` 必须做 `payload["error"]` 子对象提取。若 `payload` 没有 `"error"` 键会触发 `KeyError`。实现时需要防御 `"error" not in payload`。这不属于 plan 级别的 blocker — implementation agent 应当在 `isinstance(payload.get("error"), dict)` 检查时自然处理。无需修改 plan。
- **Section 6 item 11**: case-insensitive substring match 可能对短片段（如 `"token"` 匹配 `"token_count"`）产生误杀。但这属于 diagnostic payload redaction 的可接受假阳性 — redaction 宁可多 redact 也不漏。无需修改 plan。
- **Slice 1 validation command**: 已包含 `test_diagnostic_payload.py`（line 182）。Slice 2（line 236）和 Slice 3（line 271）也已包含。✓

## Conclusion

**PASS** — 0 remaining findings。

Controller adjudication 中全部 10 组 accepted findings 均已正确修入 plan artifact。Plan 现在包含:
- 明确的 `_SENSITIVE_KEY_FRAGMENTS` 初始值与匹配策略
- 独立的 `test_diagnostic_payload.py` 及覆盖范围
- provider error sub-object 提取规则
- `_DIAGNOSTIC_PAYLOAD_MAX_BYTES` 三步 fallback 顺序
- SSE missing choices 两种 reason 常量
- diagnostic payload version = 1 及 Host opaque 策略
- SSE / non-stream invalid UTF-8 模块级常量提升
- motivation/direct evidence 中 invalid UTF-8 custom payload 与 `dict(parsed)` 区分
- redaction 测试全部改用 `json.dumps` / 递归叶子检查
- provider-level `code`/`type`/`param` 与 `RunnerProtocolErrorData.error_code` 术语区分
- canonical byte size 算法明确为 local `json.dumps`
- HTTP 测试重命名为 `test_http_json_object_error_body_produces_bounded_diagnostic_payload`

未发现 plan fix 引入新的 scope creep、架构越界或编码约束违反。

## Recommendation

建议进入 **accepted plan commit → implementation gate**。
