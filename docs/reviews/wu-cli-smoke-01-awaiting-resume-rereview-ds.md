# Code Review — Re-review (AgentDS)

## Scope

- Mode: re-review of re-fix against accepted findings
- Branch: `phase/host-issues-control`
- Base: `main`
- Output file: `docs/reviews/wu-cli-smoke-01-awaiting-resume-rereview-ds.md`
- Input artifacts:
  - `docs/reviews/wu-cli-smoke-01-awaiting-resume-review-mimo.md` (MiMo initial review)
  - `docs/reviews/wu-cli-smoke-01-awaiting-resume-review-ds.md` (DS review, 4 findings)
  - `docs/reviews/wu-cli-smoke-01-awaiting-resume-refix-codex.md` (Codex re-fix)
- Re-review scope: 仅审查 re-fix 是否闭环以下 6 项 accepted findings；不扩展审查范围
- Included scope: `dayu/host/run_input.py`, `dayu/host/_event_payload.py`, `dayu/runtime/json_redaction.py`, `dayu/engine/agent.py` (交叉验证), `tests/host/test_run_input_builder.py`, `tests/host/test_wait_awaiting_accept.py`, `dayu/host/README.md`, `tests/README.md`, `dayu/README.md`, `dayu/runtime/__init__.py`
- Excluded scope: 本轮 diff 中与这 6 项无关的文件（CLI、Fins、Service、Config 等）
- Parallel review coverage: 无

## Findings

### 逐项闭环判定

#### 1. Fallback LLM-facing 不再暴露 kind/result/ok wrapper，中文自解释 ✅ 已闭环

- **验证路径**: `_resume_wait_fallback_message` → `_resume_wait_tool_message_content` → `_resume_wait_completed_tool_content`
- **直接证据**:
  - `dayu/host/run_input.py:3901`: fallback 不再 `json.dumps(payload["result"])`，改为调用 `_resume_wait_tool_message_content(payload)` 提取业务结果。
  - `dayu/host/run_input.py:3955-3980`: `_resume_wait_tool_message_content` 从 result envelope 中剥离 `kind` 字段做分支，只投影 body 业务内容。
  - `dayu/host/run_input.py:228`: `_RESUME_GUIDANCE_PREFIX` 从英文 `"Resume guidance:"` 改为中文 `"恢复上下文："`。
  - `dayu/host/run_input.py:2673-2677`: system message section 路由已同步适配新前缀。
  - `tests/host/test_run_input_builder.py:486-496`: 断言 fallback 消息包含 `工具结果：{"answer": 42}`，且不包含 `"Resume guidance"`、`"kind"`、`"result"`、`"ok"` 及 `sha256:`、`event-tool-result-resume` 等内部引用。
- **判定**: 已闭环。LLM-facing fallback 文本为纯中文自解释，无内部 wrapper 字段泄漏。

#### 2. 旧/异常 wait_created_event_ref / TOOL_AWAITING 缺失或不匹配能安全 fallback，真实 schema bug 仍 fail-closed ✅ 已闭环

- **验证路径**: `_resume_wait_messages_from_current_start` → `_resume_wait_accepted_arguments` → `_optional_event_id_from_payload_ref`
- **直接证据**:
  - `dayu/host/run_input.py:3915-3952`: `_resume_wait_accepted_arguments` 对以下场景返回 `None`（安全 fallback）：
    - `wait_created_event_ref` 缺失（行 3930-3931）
    - ref 指向的 event 不存在（行 3932-3934）
    - ref 指向的 event 不是 `TOOL_AWAITING`（行 3935-3936）
    - `TOOL_AWAITING` 缺少 `accepted_arguments`（行 3938-3940）
    - `TOOL_AWAITING` 缺少 `accepted_arguments_source_digest`（行 3944-3946）
  - 对真实 schema bug 仍抛 `HostDurableError`（fail-closed）：
    - `accepted_arguments` 字段存在但非 object（行 3941-3942）
    - `source_digest` 字段存在但非文本（行 3947-3948）
    - `source_digest` != `normalized_arguments_digest`（行 3950-3951）
  - `dayu/host/run_input.py:4057-4072`: `_optional_event_id_from_payload_ref` — 字段缺失返回 `None`；字段存在但结构非法仍抛 `HostDurableError`。
  - `dayu/host/run_input.py:3867-3868`: `accepted_arguments is None` 时返回 `_resume_wait_fallback_message(payload)` 作为单条 SystemMessage，不阻塞 resume。
  - `tests/host/test_run_input_builder.py:501-557`: 参数化测试覆盖 missing ref、missing event、wrong event type、missing source digest — 全部降级到 fallback guidance。
  - `tests/host/test_run_input_builder.py:559-597`: digest 不一致时 fail-closed，抛出 `HostDurableError("digest mismatch")`。
- **判定**: 已闭环。旧/异常事件安全降级，真实 schema 编码错误不静默吞掉。

#### 3. LLM replay arguments 递归脱敏 token/api_key/password/secret 等敏感 key，原始敏感值不进 EventLog/LLM replay/log ✅ 已闭环

- **验证路径**: `tool_awaiting_payload` → `_llm_safe_replay_arguments` → `redact_sensitive_json_fields`；resume 时 `_resume_wait_accepted_arguments` 读取脱敏参数。
- **直接证据**:
  - `dayu/runtime/json_redaction.py:18-23`: 敏感片段列表 `api_key`、`password`、`secret`、`token`。
  - `dayu/runtime/json_redaction.py:26-46`: `redact_sensitive_json_fields` 递归脱敏 object 敏感字段为 `<redacted>`，非敏感字段和数组元素继续递归；字段名匹配统一小写并把 `-` 规范化为 `_`。
  - `dayu/host/_event_payload.py:118-131`: `_llm_safe_replay_arguments` 调用 `redact_sensitive_json_fields(accepted_arguments)` 后存入 EventLog。
  - `dayu/host/_event_payload.py:79`: EventLog payload 的 `accepted_arguments` 字段存脱敏投影。
  - `dayu/host/_event_payload.py:80`: `accepted_arguments_source_digest` 存原始参数 digest（`normalized_arguments_digest`），用于读取端同源校验。
  - `dayu/host/run_input.py:3944-3951`: 读取端校验 `source_digest` 与 `TOOL_AWAITING.normalized_arguments_digest` 一致。
  - `tests/host/test_wait_awaiting_accept.py:229-274`: 断言 `token-raw-value`、`api-key-raw-value`、`password-raw-value`、`secret-raw-value` 不进入 EventLog payload；payload 中只有 `<redacted>` 和非敏感业务字段；`accepted_arguments_source_digest` 与原始 digest 一致。
  - `tests/host/test_run_input_builder.py:644-705`: 断言 resume assistant tool call 的 replay arguments 只有 `<redacted>`，原始敏感值不出现在 replay text 中。
- **边界说明**: `json_redaction.py` 是层中立 helper（`dayu/runtime/`），不 import 任何业务层；`dayu/runtime/__init__.py:32` 已文档化。通用 import 边界扫描 `test_runtime_does_not_import_business_layers` 已覆盖 `json_redaction.py`（`_iter_python_files()` 自动包含所有 `.py` 文件）。
- **判定**: 已闭环。敏感字段递归脱敏，原始值不进入 EventLog payload、LLM replay 或 log。digest 机制保证 replay 参数与原始参数关联可验证。

#### 4. Continuity 当前用户判断已显式化/加固 ✅ 已闭环

- **验证路径**: `_current_user_tail_messages` → `_continuity_contains_current_user`
- **直接证据**:
  - `dayu/host/run_input.py:3785-3804`: 函数从 `_continuity_starts_with_current_user` 重命名为 `_continuity_contains_current_user`。
  - docstring（行 3791-3794）显式记录了 `DurableSessionContinuityProvider` 当前只返回 resume 专用 `user -> assistant(tool_call) -> tool` 消息，不拼接 memory/snapshot 前缀。
  - 实现从只检查 `continuity.messages[0]` 改为遍历所有 `continuity.messages`（行 3801-3803），查找任一 `UserMessage` 匹配 `current_facts.user_prompt`。
  - `dayu/host/run_input.py:3775`: `_current_user_tail_messages` 调用 `_continuity_contains_current_user` 决定是否追加当前用户消息。
- **判定**: 已闭环。隐式 `[0]` 假设已消除；docstring 显式记录了 provider 契约；O(n) 遍历（n 极小，3 条消息）让未来 provider 组合变更不会导致用户消息重复追加。

#### 5. Completed 非 dict value 投影有 Engine 普通路径证据并测试覆盖 ✅ 已闭环

- **验证路径**: Engine `_project_tool_success_for_llm` vs Host `_resume_wait_completed_tool_content`
- **直接证据**:
  - Engine 侧 `dayu/engine/agent.py:376-393`: `_project_tool_success_for_llm` — Mapping value → dict comprehension；非 Mapping → `{"content": _plain_json_value(value)}`。
  - Engine 侧 `dayu/engine/agent.py:2046-2053`: 该投影写入 `ToolMessage.content`。
  - Host 侧 `dayu/host/run_input.py:3983-3995`: `_resume_wait_completed_tool_content` — Mapping value → `dict(value)`；非 Mapping → `{"content": value}`。
  - 两条路径格式一致：Mapping 透传，非 Mapping 包 `{"content": value}`。
  - `tests/host/test_run_input_builder.py:600-641`: 覆盖 `completed_value="download finished"`（字符串）时，resume ToolMessage content 为 `'{"content": "download finished"}'`。
- **判定**: 已闭环。Engine 路径已交叉验证，Host resume 路径一致，非 dict value 有测试覆盖。

#### 6. Tests/pyright/README 触发充分 ✅ 已闭环

- **直接证据**:
  - **pyright**: `0 errors, 0 warnings, 0 informations`（对 `dayu/host/run_input.py`、`dayu/host/_event_payload.py`、`dayu/runtime/json_redaction.py`、`dayu/engine/agent.py` 执行）。
  - **tests**: `tests/host/test_run_input_builder.py`、`tests/host/test_resolve_wait_command.py`、`tests/host/test_wait_awaiting_accept.py`、`tests/host/test_engine_ingest_mapping.py`、`tests/host/test_wait_adapter_polling.py` — 215 passed。
  - **dayu/host/README.md**: 第 592-594 行更新 resume runner input 边界，说明使用 LLM-safe replay 参数重建工具调用，并用原始参数 digest 关联 accepted truth。
  - **tests/README.md**: 第 206 行更新 Host 测试覆盖，包含 LLM-safe replay 参数、敏感参数不进入 replay payload、旧事件 fallback 与异常引用降级。
  - **dayu/README.md**: 第 86 行更新 runtime 能力列表，包含 JSON 敏感字段脱敏。
  - **dayu/runtime/__init__.py**: 第 32 行 docstring 列出 `dayu.runtime.json_redaction`。
- **判定**: 已闭环。pyright 0 错误，215 测试通过，三个 README 按触发规则更新。

## Open Questions

无。

## Residual Risk

- `tests/runtime/test_import_boundary.py` 缺少针对 `json_redaction.py` 的显式 `test_runtime_import_boundary_scan_covers_json_redaction_module` 测试（其他 runtime 模块如 `lane.py`、`filelock.py`、`config_loader.py` 等均有对应显式覆盖断言）。但 `test_runtime_does_not_import_business_layers` 通过 `_iter_python_files()` 自动扫描所有 `.py` 文件，已间接覆盖 `json_redaction.py` 的 import 边界。这是极低风险的测试覆盖风格不一致，不阻塞。
- 旧库中已存在且没有 `accepted_arguments` / `accepted_arguments_source_digest` 的 `TOOL_AWAITING` fact 仍只能走 fallback guidance（上一轮 DS review 和 Codex re-fix 均已记录为不可恢复边界）。
- LLM-safe replay 参数含 `<redacted>` 标记，resume 协议中的 assistant tool call arguments 不一定与原始工具调用逐字一致——它只服务 LLM 上下文闭环，不服务重新执行（Codex re-fix 已记录）。
- 本轮仍未运行真实 provider + SEC/Fins 网络 E2E。

## Conclusion

**Pass**

6 项 accepted findings 全部由 re-fix 闭环，逐项验证通过：

| # | Finding | 状态 |
|---|---------|------|
| 1 | Fallback LLM-facing 不再暴露 kind/result/ok wrapper | ✅ 已闭环 |
| 2 | 旧/异常 event 安全 fallback，真实 schema bug fail-closed | ✅ 已闭环 |
| 3 | LLM replay arguments 递归脱敏敏感 key | ✅ 已闭环 |
| 4 | Continuity 当前用户判断显式化/加固 | ✅ 已闭环 |
| 5 | Completed 非 dict value 投影 Engine 路径证据+测试覆盖 | ✅ 已闭环 |
| 6 | Tests/pyright/README 触发充分 | ✅ 已闭环 |

无 Blocked 项，无新增未闭环 finding。
