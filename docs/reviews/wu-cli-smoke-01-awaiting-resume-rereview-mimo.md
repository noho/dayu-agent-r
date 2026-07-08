# Code Review — re-review

## Scope

- Mode: current changes
- Branch: phase/host-issues-control
- Base: main
- Output file: docs/reviews/wu-cli-smoke-01-awaiting-resume-rereview-mimo.md
- Included scope: re-fix 是否关闭 6 个 accepted findings
- Excluded scope: 未涉及 re-fix 的其它改动
- Parallel review coverage: 无
- Input artifacts:
  - docs/reviews/wu-cli-smoke-01-awaiting-resume-review-mimo.md
  - docs/reviews/wu-cli-smoke-01-awaiting-resume-review-ds.md
  - docs/reviews/wu-cli-smoke-01-awaiting-resume-refix-codex.md

## Findings

未发现实质性问题。

以下逐项验证 6 个 accepted findings 的关闭状态：

### Finding 1 — fallback LLM-facing 不再暴露 kind/result/ok wrapper，中文自解释 ✅ 已关闭

- **入口/函数**: `_resume_wait_fallback_message`
- **文件(行号)**: `dayu/host/run_input.py:3894-3912`
- **验证**:
  - fallback 路径调用 `_resume_wait_tool_message_content(payload)` 投影业务结果（第 3901 行），不再 `json.dumps(payload.get("result"))` 直接暴露 result envelope。
  - `_RESUME_GUIDANCE_PREFIX` 已从 `"Resume guidance:"` 改为 `"恢复上下文："`（第 228 行）。
  - fallback 文本只包含：中文前缀、完成状态、工具名、业务结果 JSON 和中文恢复说明。
  - 测试 `test_run_input_builder.py:486-491` 断言 `'工具结果：{"answer": 42}'` 出现，且 `"Resume guidance"` / `'"kind"'` / `'"result"'` / `'"ok"'` 不出现。

### Finding 2 — 旧/异常 wait_created_event_ref / TOOL_AWAITING 缺失或不匹配能安全 fallback ✅ 已关闭

- **入口/函数**: `_resume_wait_accepted_arguments`
- **文件(行号)**: `dayu/host/run_input.py:3915-3952`
- **验证**:
  - `wait_created_event_ref` 缺失时返回 `None`（第 3926-3931 行，使用 `_optional_event_id_from_payload_ref`）。
  - ref 指向 event 不存在时返回 `None`（第 3932-3934 行）。
  - event 类型不匹配 `_EVENT_TYPE_TOOL_AWAITING` 时返回 `None`（第 3935-3936 行）。
  - `accepted_arguments` 缺失时返回 `None`（第 3938-3940 行）。
  - `accepted_arguments_source_digest` 缺失时返回 `None`（第 3944-3946 行）。
  - 保留 fail-closed 边界：`accepted_arguments` 非 object 时抛 `HostDurableError`（第 3941-3942 行）；source digest 非文本时抛异常（第 3947-3948 行）；source digest 与 `normalized_arguments_digest` 不一致时抛异常（第 3949-3951 行）。
  - 测试 `test_run_input_builder.py:501-557` 覆盖 missing / missing_event / wrong_event_type / valid（缺 source digest）四种降级场景。
  - 测试 `test_run_input_builder.py:559-597` 覆盖 digest 不同时 fail closed。

### Finding 3 — LLM replay arguments 递归脱敏敏感 key ✅ 已关闭

- **入口/函数**: `tool_awaiting_payload` → `_llm_safe_replay_arguments` → `redact_sensitive_json_fields`
- **文件(行号)**:
  - `dayu/runtime/json_redaction.py:26-46` — 递归脱敏实现
  - `dayu/host/_event_payload.py:79` — payload 写入脱敏参数
  - `dayu/host/_event_payload.py:118-131` — `_llm_safe_replay_arguments` 调用 `redact_sensitive_json_fields`
- **验证**:
  - `redact_sensitive_json_fields` 递归处理 Mapping 和 list，字段名命中 `api_key` / `password` / `secret` / `token` 片段时替换为 `<redacted>`（第 18-23 行、第 40-42 行）。
  - 字段名匹配统一小写并把 `-` 规范化为 `_`，因此 `api-key` / `client-secret` 等变体均命中（第 57 行）。
  - `tool_awaiting_payload` 第 79 行写入 `_llm_safe_replay_arguments(accepted_arguments)`，原始敏感值不进 EventLog payload。
  - `_PAYLOAD_FIELD_ACCEPTED_ARGUMENTS_SOURCE_DIGEST` 保存原始参数 digest（第 80 行），resume 时通过 `_resume_wait_accepted_arguments` 校验 digest 一致性（第 3949-3951 行）。
  - 测试 `test_wait_awaiting_accept.py:229-274` 验证 `token-raw-value` / `api-key-raw-value` / `password-raw-value` / `secret-raw-value` 不出现在 payload_json 中。
  - 测试 `test_run_input_builder.py:644-705` 验证 resume 重建的 assistant tool call arguments 只含 `<redacted>` 值。

### Finding 4 — continuity 当前用户判断已显式化/加固 ✅ 已关闭

- **入口/函数**: `_continuity_contains_current_user`（原 `_continuity_starts_with_current_user`）
- **文件(行号)**: `dayu/host/run_input.py:3785-3804`
- **验证**:
  - 函数已重命名为 `_continuity_contains_current_user`。
  - docstring 明确说明 `DurableSessionContinuityProvider` 当前只返回 resume 专用 `user -> assistant(tool_call) -> tool` 消息，不拼接 memory 或 snapshot 前缀（第 3791-3792 行）。
  - 实现从只检查首条消息改为遍历 `continuity.messages` 查找 `isinstance(message, UserMessage) and message.content == current_facts.user_prompt`（第 3801-3803 行），未来 provider 组合出现前缀消息时不会重复追加。

### Finding 5 — completed 非 dict value 投影有 Engine 普通路径证据并测试覆盖 ✅ 已关闭

- **入口/函数**: `_resume_wait_completed_tool_content` 与 Engine `_project_tool_success_for_llm`
- **文件(行号)**:
  - `dayu/host/run_input.py:3983-3995`
  - `dayu/engine/agent.py:376-393`
- **验证**:
  - Engine 普通路径 `_project_tool_success_for_llm`（第 386-393 行）：Mapping value 透传 `dict(value)`，非 Mapping value 包为 `{"content": _plain_json_value(value)}`。
  - Host resume 路径 `_resume_wait_completed_tool_content`（第 3992-3995 行）：`isinstance(value, Mapping)` 时 `return dict(value)`，否则 `return {"content": value}`。格式一致。
  - 测试 `test_run_input_builder.py:600-641` 覆盖 completed value 为字符串 `"download finished"` 时，resume tool message content 为 `'{"content": "download finished"}'`。

### Finding 6 — tests/pyright/README 触发充分 ✅ 已满足

- **验证**:
  - pyright `0 errors`（对 `dayu/host/run_input.py`、`dayu/host/_event_payload.py`、`dayu/runtime/json_redaction.py` 验证通过）。
  - re-fix artifact 记录 `227 passed`、`0 errors, 0 warnings, 0 informations`。
  - `dayu/host/README.md` 已更新 resume runner input 边界说明：使用 LLM-safe replay 参数重建工具调用，并用原始参数 digest 关联 accepted truth。
  - `tests/README.md` 已更新 Host 测试覆盖说明：补充 LLM-safe replay 参数、敏感参数不进入 replay payload、旧事件 fallback 与异常引用降级。
  - `dayu/README.md` 已更新 runtime 能力列表：补充 JSON 敏感字段脱敏 helper。
  - `dayu/runtime/__init__.py` docstring 已列出 `dayu.runtime.json_redaction`（第 32 行）。

## Open Questions

无。

## Residual Risk

- 旧库中已存在且没有 `accepted_arguments` / `accepted_arguments_source_digest` 的 `TOOL_AWAITING` fact 仍只能走 fallback guidance，无法 retroactively 重建 assistant tool call——这是旧事实缺字段导致的不可恢复边界，已在 re-fix artifact 中明确记录。
- `_is_sensitive_key` 使用子串匹配（`any(fragment in normalized for fragment in ...)`），可能对非敏感但字段名包含 `token` 等片段的业务字段误脱敏（如 `token_count`、`pagination_token`）。当前 Fins 工具参数不包含此类字段，风险低；若未来工具参数出现误脱敏，需细化匹配策略。
- 本轮仍未运行真实 provider E2E，验证范围为 Host durable facts、RunInputBuilder 投影、wait resolve、Engine ingest、runtime helper 单元与类型检查。

## Conclusion

**Pass**

6 个 accepted findings 全部关闭，re-fix 证据链完整：

1. Fallback LLM-facing 文本已移除 `kind` / `result` / `ok` wrapper，使用中文自解释前缀，测试断言覆盖。
2. 旧/异常 `wait_created_event_ref` / `TOOL_AWAITING` 缺失或不匹配安全降级为 fallback guidance，真实 schema bug（非 object、digest 不一致）仍 fail-closed，测试覆盖 4 种降级 + 1 种 fail-closed。
3. `dayu/runtime/json_redaction.py` 递归脱敏 `api_key` / `password` / `secret` / `token`，EventLog payload 只写入脱敏参数，原始参数通过 digest 关联，测试覆盖写入侧和 resume 读取侧。
4. `_continuity_contains_current_user` 遍历全部 continuity 用户消息而非只检查首条，docstring 显式化 provider 行为约束。
5. Host resume 路径与 Engine `_project_tool_success_for_llm` 格式一致（Mapping 透传、非 Mapping 包 `{"content": value}`），测试覆盖非 dict value 场景。
6. pyright 通过、测试通过、三个 README 已按触发规则更新。
