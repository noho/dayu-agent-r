# Code Review

## Scope

- Mode: PR
- PR: #163 — "WU-WAIT-01: wait callback endpoint auth replay"
- Author: noho
- Base: main
- Head: phase/wu-wait-01-issue-89
- URL: https://github.com/noho/dayu-agent-r/pull/163
- Output file: docs/reviews/wu-wait-01-pr-review-mimo.md
- Included scope: PR #163 相对 main 的完整 diff；design docs、plan、control doc、focused tests、pyright、git diff --check
- Excluded scope: 无
- Parallel review coverage: 无

## Review Checklist

### 1. Callback Endpoint 交付形态

**结论：符合要求。**

`dayu/service/wait_callback_endpoint.py` 是 framework-neutral mapper，不注册真实 HTTP route。`handle_wait_callback_completion(request, adapter)` 接收已解析的 `WaitCallbackHttpRequest` 和注入的 `WaitCallbackEndpointAdapter`，输出 `WaitCallbackHttpResponse`。模块 docstring 明确声明不注册路由、不写 durable state、不依赖具体 Web framework。Service README 更新正确描述了边界。

### 2. Host 仍是 wait lifecycle/auth/replay/durable transition 真源

**结论：符合要求。**

Callback 完整链路：

```text
Service mapper → WaitCallbackCompletionEnvelope
  → DefaultWaitCallbackAdapter.resolve_callback()
    → authenticate (injected protocol)
    → read_wait_state (injected port, reads durable wait record)
    → stale/digest preflight
    → ResolveWaitRequest(source=CALLBACK)
    → CallbackWaitResolvePort.resolve_callback_wait()
      → HostCommandWaitCallbackPort (command layer)
        → DefaultHostResolveWaitService.resolve_wait() (existing pipeline)
        → dispatch wakeup (non-replay only)
```

`DefaultWaitCallbackAdapter` 不直接调用 `DefaultHostResolveWaitService`；它通过注入的 `CallbackWaitResolvePort` 协议桥接到 command layer。`HostCommandWaitCallbackPort` 在 command.py 中实现，复用现有 `DefaultHostResolveWaitService`，保留 dispatch wakeup 语义。callback 不绕过 common resolve_wait pipeline。

### 3. Auth-before-read

**结论：符合要求。**

`DefaultWaitCallbackAdapter.resolve_callback()` 第一步调用 `self._authenticate(envelope.auth)`。认证拒绝时立即返回 `AUTH_FAILED`，不读取 wait state，不调用 resolver。测试 `test_auth_rejection_returns_auth_failed_without_resolver_call` 验证 `reader.calls == 0` 和 `resolver.calls == 0`。

### 4. Replay Idempotency

**结论：符合要求。**

- 同 `(wait_id, idempotency_key)` 且同 outcome digest：resolve_wait 返回 `idempotent_replay=True`，adapter 返回 `REPLAYED`。
- dispatch wakeup：`HostCommandWaitCallbackPort.resolve_callback_wait` 在 `result.dispatch_record is not None and not result.idempotent_replay` 时才唤醒 dispatch。测试 `test_callback_accept_wakes_dispatch_once_and_replay_does_not_wake_again` 验证 `wakeup.dispatch_wakes == 1`。
- EventLog：测试 `test_callback_replay_does_not_append_new_event_log` 验证 replay 不追加新 event。

### 5. Same-key Conflict

**结论：符合要求。**

测试 `test_callback_same_key_changed_outcome_returns_idempotency_conflict` 验证同 idempotency key 不同 outcome 返回 `IDEMPOTENCY_CONFLICT`，不追加新 EventLog。

### 6. Digest 同源

**结论：符合要求。**

`dayu/host/durable/wait_resolution_digest.py` 集中维护 outcome JSON 投影。`waiting.py` 的 `_wait_resolution_digest` 现在调用 `wait_resolution_digest(wait_id, request.idempotency_key, request.outcome)`，callback adapter 的 `_callback_payload_digest` 调用同一函数。测试 `test_callback_digest_matches_resolve_wait_digest_for_completed_and_lost` 直接验证两者 produce identical digest。

### 7. Stale/Late Handling

**结论：符合要求。**

- Stale：`_stale_status_or_none` 比较 `completed_at > boundary`（deadline_at 或 expires_at）。无 deadline/expires 时不判 stale。非法持久化 deadline 返回 `INVALID_WAIT_STATE`。测试覆盖所有场景。
- Late cancelled/lost：预读 wait state 时发现已 cancelled/lost 返回 `LATE_WAIT_CANCELLED`/`LATE_WAIT_LOST`。测试覆盖。
- INVALID_STATE fallback：`_result_from_host_api_error` 对 `INVALID_STATE` 先尝试 stable late classification，不能分类时返回 `INVALID_WAIT_STATE`。符合 plan 描述的"concurrent races may safely collapse to INVALID_WAIT_STATE"。

### 8. Service → Host 分层边界 / Import Boundary

**结论：符合要求。**

- `wait_callback_endpoint.py` 只 import `dayu.host` 公共 API（`__init__.py` exports）。不 import `dayu.host.durable`、`dayu.host.command`、`dayu.host.waiting` 等内部模块。
- `wait_callback.py` import boundary 测试 `test_wait_callback_adapter_has_no_service_ui_or_web_framework_dependency` 验证无 Service/UI/Web framework 依赖。
- Service import boundary 测试 `test_service_does_not_import_forbidden_layers` 通过。
- `HostCommandWaitCallbackPort` 在 `command.py` 中实现，正确 import 了 host 内部模块（`durable.schema`、`durable.transaction`），这是 command layer 的合法行为。

### 9. LLM-facing 文本约束

**结论：符合要求。**

- 所有 dataclass 和 Protocol 有完整中文 docstring。
- tool schema 不涉及（本 PR 不新增 tool）。
- diagnostic message 使用人类可读英文（"callback payload digest does not match outcome"、"wait record not found" 等），不包含内部模块名或实现术语。
- response body 不回显 outcome payload。测试 `test_response_body_does_not_echo_outcome_result_payload` 验证。

### 10. README / Test 边界

**结论：符合要求。**

- `dayu/host/README.md` 更新了公共契约列表，描述 callback 相关类型和端口契约。
- `dayu/service/README.md` 更新了 `handle_wait_callback_completion` 描述和边界约束。
- `tests/README.md` 在 diff 中（未修改内容，仅 touch）。
- 新增 `tests/host/test_wait_callback.py` 和 `tests/service/test_wait_callback_endpoint.py`。
- import boundary 测试新增 `WAIT_CALLBACK_FORBIDDEN_PREFIXES` 常量和对应测试。

### 11. PR Body 与实现一致性

**结论：符合要求。**

PR body 明确声明：
- ✅ "Provided as `handle_wait_callback_completion(request, adapter)` ... not as a registered FastAPI/Flask route"
- ✅ "This PR intentionally does not add a real route, secret backend, HMAC/bearer verifier, issue-90 poller, issue-92 physical cancel, Engine contract, or UI surface"
- 实现与声明一致。

### 12. Resolve_wait Digest Refactoring

**结论：安全重构。**

`waiting.py` 中删除了 `_resolve_outcome_json`、`_tool_success_json`、`_tool_failure_json`、`_tool_cancelled_json`、`_tool_lost_json`、`_tool_result_meta_json`、`_host_payload_ref_json`、`_provider_status_ref_json` 等函数，统一迁移到 `dayu/host/durable/wait_resolution_digest.py`。`waiting.py` 通过 import alias 保持内部常量名不变（`_TOOL_FACT_KIND_COMPLETED` 等）。`_wait_resolution_digest` 函数调用 `wait_resolution_digest()` 替代原来的 `sha256_digest_json({...})`。现有 `test_resolve_wait_command.py` 和 `test_wait_cancel_late_result.py` 全部通过（15 passed），验证重构无回归。

## Findings

未发现实质性问题。

## Open Questions

无。

## Residual Risk

- `WaitCallbackAuthenticator` Protocol 当前只有 `_AcceptingAuthenticator` 和 `_RejectingAuthenticator` 两个测试实现。真实 bearer/HMAC secret backend 实现属于后续 WU（Service/Web composition root）。本 PR 正确地只定义了 typed protocol。
- `expires_at` 字段在当前 schema 中存在但通常为 `None`。stale classification 当前只在 `deadline_at` 存在时生效。Plan 明确这是已知限制，不是缺陷。
- `HostCommandWaitCallbackPort` 未从 `dayu.host` package root 导出，只从 `dayu.host.command` 导出。测试通过直接 import `dayu.host.command.HostCommandWaitCallbackPort` 使用。如果未来 Service 层需要构造 adapter，需要在 composition root 中组装。这是正确的分层设计，不是遗漏。

## Validation

- `pytest tests/host/test_wait_callback.py tests/service/test_wait_callback_endpoint.py tests/host/test_import_boundary.py tests/service/test_import_boundary.py tests/host/test_package_exports.py` → **87 passed**
- `pytest tests/host/test_resolve_wait_command.py tests/host/test_wait_cancel_late_result.py` → **15 passed**（现有 resolve_wait 测试无回归）
- `pyright dayu/host/wait_callback.py dayu/host/command.py dayu/host/durable/wait_resolution_digest.py dayu/host/waiting.py dayu/service/wait_callback_endpoint.py` → **0 errors, 0 warnings, 0 informations**
- `pyright`（full）→ **0 errors, 0 warnings, 0 informations**
- `git diff --check` → **passed**
