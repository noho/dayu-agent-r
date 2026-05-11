# P8.5 Slice 1 User Additional Review Fix Re-review

## Conclusion

fail

前序 user additional review 的多数 accepted findings 已关闭，指定验证命令全部通过；但 credential scrub 仍存在一个直接 trace 泄漏路径：provider protocol raw payload 内的字符串形式 Authorization / x-api-key / cookie header 不会被 `_tool_trace_jsonl_sink._scrub_provider_secret()` 清洗，与当前 design/test docs 的 trace 凭证边界不一致。

## Findings

### 1-未修复-中-provider raw payload 的字符串 header 凭证仍会进入 trace

- **入口/函数**: `ToolTraceObserver._emit_provider_protocol_error()` -> `_scrub_provider_secret()`
- **文件(行号)**: `dayu/host/_tool_trace_projection.py:380-406`; `dayu/host/_tool_trace_jsonl_sink.py:107-128`; `docs/host/design.md:921-923`; `tests/README.md:106-108`
- **输入场景**: provider protocol error 的 `raw_payload` 是 JSON object，里面的某个普通字符串字段包含 header 文本，例如 `{"message": "Authorization: Bearer sk-live"}` 或 `{"debug": "x-api-key: sk-live"}`。
- **实际分支**: `_emit_provider_protocol_error()` 对 `data.raw_payload` 调用 `_scrub_provider_secret()`；该 helper 只在 `dict` key 命中 `_PROVIDER_SECRET_KEYS` 时替换值，对 `str` 叶子节点直接原样返回。
- **预期行为**: 当前设计写明 provider secret、Authorization header、API key、cookie 不得进入 trace；tests README 也把 credential scrub 覆盖描述为字段 / 字符串 header 两类。provider raw payload 作为 trace 输出路径，不应比普通 tool payload 弱。
- **实际行为**: `raw_payload_json` 会保留字符串中的 `Authorization: Bearer sk-live`。实测同一字符串经 `_credential_scrub.scrub_explicit_credentials()` 会变为 `Authorization: ***`，但 provider raw payload scrub 没有复用该文本规则。
- **直接证据**:
  - `dayu/host/_tool_trace_projection.py:383-384` 将 `_scrub_provider_secret(data.raw_payload)` 的结果 JSON dump 到 trace record。
  - `dayu/host/_tool_trace_jsonl_sink.py:115-128` 只递归处理 dict/list，最后 `return payload`，字符串不会进入文本 header scrub。
  - `tests/host/test_phase7_tool_trace_jsonl_sink.py:69-104` 只覆盖 Authorization / x-api-key / Cookie 作为字段 key 的情况，未覆盖字符串 header。
  - `docs/host/design.md:921-923` 要求 provider secret / Authorization header / API key / cookie 不得进入 trace。
- **影响**: provider adapter 或协议错误把 header dump 成字符串字段时，显式凭证会进入 `provider_protocol_error.raw_payload_json` trace，违反 P8.5 “保留 cursor/scope_token，但 scrub 明确凭证”的边界。
- **建议改法和验证点**: 让 `_scrub_provider_secret()` 对字符串叶子也复用 `_credential_scrub` 的显式凭证文本清洗规则，或把 provider raw payload scrub 统一收敛到同源 helper；补充 `tests/host/test_phase7_tool_trace_jsonl_sink.py` 或 trace projection 测试，覆盖 `{"message": "Authorization: Bearer sk-live\nx-api-key: sk"}` 被清洗，同时 `cursor`、`scope_token`、普通 `token`、`anthropic-version`、`openai-organization` 保留。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

## Verified Closed Items

- `_build_chunk` unknown strategy：`dayu/host/_runtime_truncate_manager.py:337-344` 在 chunk 构造失败时返回普通 `unsupported_truncate_strategy` failed outcome，`dayu/host/_runtime_truncate_manager.py:339-340` 移除旧 cursor；`tests/host/test_phase2_tool_runtime_truncation.py:623-669` 覆盖非法 strategy 不签发 next cursor，旧 cursor 再用返回 `cursor_not_found`。
- cursor registry 并发保护：`dayu/host/_runtime_truncate_manager.py:234-238` 增加 `_state_lock` 并保留 `_read_lock`；`apply_truncation()` 在 `:262-268` 持锁 build/commit；`fetch_more()` 在 `:296-371` 保持 single-use read lock，并用 `_state_lock` 保护 registry 读写；`tests/host/test_phase2_tool_runtime_truncation.py:689-763` 覆盖 apply/fetch 并发与同 cursor single-use。
- 普通 tool payload credential scrub：`dayu/host/_credential_scrub.py:22-45` 覆盖 Authorization / x-api-key / cookie / anthropic-api-key / client_secret / private_key / password 与字符串 header；`tests/host/test_phase8_5_credential_scrub.py:15-127` 覆盖独立单测，并锁定 `cursor`、`scope_token`、普通 `token`、`anthropic-version`、`openai-organization` 不被误清洗。
- ToolTraceObserver 二次 scrub：`dayu/host/_tool_trace_projection.py:226-228` 明确注释为 repair/backfill/test 的防御性幂等清洗，并复用 `dayu.host._credential_scrub` helper，没有分叉规则。
- dead echo marker：`dayu/host/_event_translation.py:51-68` 已无 `toolresulttruncateddata(`；production grep 无旧专用 RunEventType / data class 残留。
- analyzer ordinary fetch_more：`utils/analyze_tool_trace_host.py:464-497` 解析 `tool_name=="fetch_more"` 的 `arguments_json.cursor/scope_token`；`:534-579` 用 ordinary fetch_more 判断 truncation gap；`:582-675` 覆盖 unknown cursor、wrong scope、duplicate cursor、failed outcome；`tests/utils/test_analyze_tool_trace_host.py:237-444` 有对应测试。
- FrameworkToolSet caching：`dayu/host/_framework_tools.py:34-53` 在 `__post_init__` 缓存 `ToolDefinition`，闭包仍绑定同一 `manager`；`tests/host/test_phase2_tool_runtime_truncation.py:672-685` 覆盖 definition identity 与 schema projection。
- ConversationToolFact safe structured fields：`dayu/host/_conversation_memory.py:622-639` 只从 raw cursor 派生短 fingerprint 与 `has_more`，不保存 raw cursor / `scope_token`；`tests/host/test_phase3_conversation_memory_projection.py:298-345` 覆盖 memory summary 不含 raw cursor/scope。
- RUN_INPUT retry path docstring-only：`dayu/host/_run_harness.py:2250-2275` 仅说明 `request` 是 engine-visible request；本次 diff 未发现行为改动。

## Validation Notes

已实际运行：

```bash
source .venv/bin/activate && python -m pyright dayu/host/ dayu/contracts/ tests/host/ tests/contracts/ utils/analyze_tool_trace_host.py tests/utils/test_analyze_tool_trace_host.py
# 0 errors, 0 warnings, 0 informations

source .venv/bin/activate && pytest tests/host/test_phase2_tool_runtime_truncation.py tests/host/test_phase6_run_event_serializer.py tests/host/test_phase7_tool_trace_projection.py tests/host/test_phase8_tool_runtime_fencing.py tests/utils/test_analyze_tool_trace_host.py tests/host/test_phase8_5_credential_scrub.py tests/host/test_phase7_tool_trace_jsonl_sink.py tests/host/test_phase3_conversation_memory_projection.py -q
# 84 passed

source .venv/bin/activate && pytest tests/contracts/test_tool_declaration.py tests/contracts/test_tool_result_envelope.py tests/contracts/test_package_exports.py -q
# 9 passed

git diff --check
# passed
```

额外复核：

```bash
_scrub_provider_secret({"message": "Authorization: Bearer sk-live", "headers": {"Authorization": "Bearer sk-live"}})
# {"message": "Authorization: Bearer sk-live", "headers": {"Authorization": "***"}}

scrub_explicit_credentials("Authorization: Bearer sk-live")
# "Authorization: ***"
```

## Open Questions

- provider raw payload scrub 是否应完全复用 `_credential_scrub` 的文本规则，还是只扩展 `_scrub_provider_secret()` 的字符串叶子处理？从当前 design 的 “Authorization header 不得进入 trace” 看，至少字符串 header 需要被覆盖。

## Residual Risk

- 未运行全仓测试、真实 provider smoke 或多进程 stress；本轮覆盖了 controller 指定命令和 user additional review 涉及的关键路径。
