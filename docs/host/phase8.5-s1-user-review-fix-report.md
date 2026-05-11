# P8.5 Slice 1 User Additional Review Fix Report

## Scope

- Gate：Slice 1 user additional code review fix。
- 分支：`migration/host-p8-5-stabilization`。
- 边界：只修 Controller 接受的 Slice 1 人工 review findings；不提交、不进入 Slice 2。

## Findings Status

| Finding | Status | Files |
| --- | --- | --- |
| unknown strategy `_build_chunk` 无限循环风险 | fixed | `dayu/host/_runtime_truncate_manager.py`, `tests/host/test_phase2_tool_runtime_truncation.py` |
| `RuntimeTruncateManager` shared state 并发保护 | fixed | `dayu/host/_runtime_truncate_manager.py`, `tests/host/test_phase2_tool_runtime_truncation.py` |
| credential scrub key/text coverage | fixed | `dayu/host/_credential_scrub.py`, `dayu/host/_tool_trace_jsonl_sink.py`, `tests/host/test_phase8_5_credential_scrub.py`, `tests/host/test_phase6_run_event_serializer.py`, `tests/host/test_phase7_tool_trace_projection.py`, `tests/host/test_phase7_tool_trace_jsonl_sink.py`, `docs/host/design.md` |
| dead echo marker | fixed | `dayu/host/_event_translation.py` |
| `_credential_scrub.py` 独立单测 | fixed | `tests/host/test_phase8_5_credential_scrub.py` |
| trace analyzer ordinary `fetch_more` 诊断回归 | fixed | `utils/analyze_tool_trace_host.py`, `tests/utils/test_analyze_tool_trace_host.py` |
| `RUN_INPUT_CONTEXT_SNAPSHOT_BUILT` retry path docstring | fixed | `dayu/host/_run_harness.py` |
| `FrameworkToolSet` definition caching | fixed | `dayu/host/_framework_tools.py`, `tests/host/test_phase2_tool_runtime_truncation.py` |
| `ConversationToolFact` structured fields always `None` | fixed | `dayu/host/_conversation_memory.py`, `tests/host/test_phase3_conversation_memory_projection.py` |
| `ToolTraceObserver` 二次 scrub 裁决 | kept as idempotent defense-in-depth | `dayu/host/_tool_trace_projection.py` |
| re-review: provider raw payload 字符串 header 凭证泄漏 | fixed | `dayu/host/_credential_scrub.py`, `dayu/host/_tool_trace_jsonl_sink.py`, `tests/host/test_phase7_tool_trace_jsonl_sink.py`, `tests/host/test_phase8_5_credential_scrub.py`, `dayu/host/README.md` |

## Notes

- `fetch_more` 对未知 truncate strategy 返回普通 failed outcome：`unsupported_truncate_strategy`，并移除旧 cursor，避免签发 next cursor 或形成 `has_more` 循环。
- cursor registry 增加 `threading.RLock` 保护 `_records_by_cursor` / `_cursor_by_fingerprint` 的读写与 cleanup；原 `asyncio.Lock` 继续保留同 cursor `fetch_more` single-use 语义。
- credential scrub 保持窄定义：清洗 API key / Authorization / x-api-key / cookie / client secret / private key / password / explicit credential；不清洗 `cursor`、`scope_token`、普通 `token`、`anthropic-version`、`openai-organization`。`docs/host/design.md` 已移除 `openai-organization` 的凭证表述。
- `ToolTraceObserver` 继续复用 `dayu.host._credential_scrub` 的同一 helper 做幂等防御，并已用中文注释说明 trace projection 可能被测试 / repair / backfill 直接喂未 scrub data。
- re-review remaining finding 已关闭：`_scrub_provider_secret()` 不再维护第二套 provider key 集合，改为直接复用 `scrub_explicit_credentials()`；provider raw payload 内的字符串形式 `Authorization` / `x-api-key` / `cookie` / API key / `client_secret` / `private_key` / `password` 会被清洗，同时 `cursor`、`scope_token`、普通 `token`、`anthropic-version`、`openai-organization` 保留。
- analyzer 新格式以 ordinary `tool_name == "fetch_more"` record 的 `arguments_json.cursor` / `arguments_json.scope_token` 为补读事实源；旧 `fetch_more_consumed_cursor` 仅保留为 historical input handling。
- Conversation memory 只保存 raw cursor 的短 fingerprint 与 `has_more`，不写 raw cursor / raw `scope_token`。

## Validation

```bash
source .venv/bin/activate && python -m pyright dayu/host/ dayu/contracts/ tests/host/ tests/contracts/ utils/analyze_tool_trace_host.py tests/utils/test_analyze_tool_trace_host.py
# 0 errors, 0 warnings, 0 informations
```

```bash
source .venv/bin/activate && pytest tests/host/test_phase2_tool_runtime_truncation.py tests/host/test_phase6_run_event_serializer.py tests/host/test_phase7_tool_trace_projection.py tests/host/test_phase8_tool_runtime_fencing.py tests/utils/test_analyze_tool_trace_host.py tests/host/test_phase8_5_credential_scrub.py tests/host/test_phase7_tool_trace_jsonl_sink.py tests/host/test_phase3_conversation_memory_projection.py -q
# 84 passed
```

```bash
source .venv/bin/activate && pytest tests/contracts/test_tool_declaration.py tests/contracts/test_tool_result_envelope.py tests/contracts/test_package_exports.py -q
# 9 passed
```

Re-review remaining finding 修复后追加验证：

```bash
source .venv/bin/activate && python -m pyright dayu/host/ tests/host/test_phase7_tool_trace_jsonl_sink.py tests/host/test_phase8_5_credential_scrub.py
# 0 errors, 0 warnings, 0 informations
```

```bash
source .venv/bin/activate && pytest tests/host/test_phase7_tool_trace_jsonl_sink.py tests/host/test_phase8_5_credential_scrub.py -q
# 11 passed
```

```bash
git diff --check
# passed
```

## Residual Risk

- 未运行全仓测试、真实 provider smoke 或多进程 stress；本轮验证覆盖 Controller 指定命令、credential scrub 新单测、trace JSONL provider scrub 与 conversation memory truncation 结构化字段。
