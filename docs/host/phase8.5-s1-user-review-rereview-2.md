# P8.5 Slice 1 User Review Narrow Re-review 2

## Conclusion

pass

本次只复核 `docs/host/phase8.5-s1-user-review-rereview.md` 中唯一 finding：provider raw payload 字符串 header 凭证进入 trace。当前 fix 已关闭该 finding，未发现新的范围内问题。

## Findings

无。

## Evidence

- `_scrub_provider_secret()` 已复用同源 credential scrub helper：`dayu/host/_tool_trace_jsonl_sink.py:29-30` import `scrub_explicit_credentials`，`dayu/host/_tool_trace_jsonl_sink.py:90-98` 直接 `return scrub_explicit_credentials(payload)`；原 provider-only key list 已删除。
- 同源规则覆盖字段与字符串 header：`dayu/host/_credential_scrub.py:22-45` 包含 `api_key` / `api key` / `x-api-key` / `authorization` / `cookie` / `client_secret` / `private_key` / `password` 等显式凭证 key 与文本赋值正则；`dayu/host/_credential_scrub.py:58-69` 递归处理 mapping、list 和 string。
- provider raw payload 测试覆盖字段和字符串叶子：`tests/host/test_phase7_tool_trace_jsonl_sink.py:69-104` 覆盖 Authorization / api_key / x-api-key / Cookie / client_secret / private_key / password 字段清洗，并锁定 `openai-organization`、`anthropic-version` 保留；`tests/host/test_phase7_tool_trace_jsonl_sink.py:107-173` 覆盖字符串中的 Authorization / x-api-key / cookie / API key / client_secret / private_key / password 被 scrub，同时 `cursor`、`scope_token`、普通 `token`、`anthropic-version`、`openai-organization` 保留。
- `_credential_scrub.py` 独立测试仍覆盖同一策略：`tests/host/test_phase8_5_credential_scrub.py:15-99` 覆盖嵌套字段、字符串 header、runtime capability 字段保留；`:102-130` 覆盖 outcome success/failure 文本清洗。

## Validation Notes

已实际运行：

```bash
source .venv/bin/activate && python -m pyright dayu/host/ tests/host/test_phase7_tool_trace_jsonl_sink.py tests/host/test_phase8_5_credential_scrub.py
# 0 errors, 0 warnings, 0 informations

source .venv/bin/activate && pytest tests/host/test_phase7_tool_trace_jsonl_sink.py tests/host/test_phase8_5_credential_scrub.py -q
# 11 passed

git diff --check
# passed
```

## Open Questions

无。

## Residual Risk

本轮未复核 Slice 1 其它历史 findings、全仓测试、真实 provider smoke 或多进程 stress；按用户要求只覆盖 provider raw payload 字符串 header scrub finding。
