# PR Review — WU-WAIT-01 Draft PR #163

## Scope

- Mode: PR review
- PR: #163 (https://github.com/noho/dayu-agent-r/pull/163)
- Title: WU-WAIT-01: wait callback endpoint auth replay
- Author: noho
- Head branch: phase/wu-wait-01-issue-89
- Base branch: main
- Output file: docs/reviews/wu-wait-01-pr-review-ds.md
- Included scope: full PR diff (42 files, +6589 −163), with focus on `dayu/host/wait_callback.py`, `dayu/host/command.py`, `dayu/host/durable/wait_resolution_digest.py`, `dayu/service/wait_callback_endpoint.py`, `dayu/host/waiting.py` digest refactor, and tests
- Excluded scope: review artifacts under `docs/reviews/` (already adjudicated), plan document `docs/host/wu-wait-01-callback-endpoint-auth-replay-plan.md` (design input, not implementation to review)
- Parallel review coverage: 无；single-agent deep review

## Verification

- `pytest tests/service/test_wait_callback_endpoint.py tests/service/test_import_boundary.py tests/service/test_weak_typing_guard.py -q` → 47 passed
- `pytest tests/host/test_wait_callback.py tests/host/test_resolve_wait_command.py tests/host/test_wait_cancel_late_result.py tests/host/test_package_exports.py tests/host/test_import_boundary.py -q` → 56 passed
- `pyright dayu/ tests/` → 0 errors, 0 warnings, 0 informations
- `git diff --check` → no output
- No CI checks reported on branch

## Findings

未发现实质性问题。

### 逐项审查结论

以下按用户指定的五个重点审查维度给出逐项结论与直接证据：

#### 1. Callback endpoint 交付形态

**结论：正确。** Service 提供的是 `handle_wait_callback_completion(request, adapter)` 函数式 mapper，不是注册好的 HTTP route。

**直接证据：**
- `dayu/service/wait_callback_endpoint.py` 只定义 `WaitCallbackHttpRequest` / `WaitCallbackHttpResponse` 数据类和 `handle_wait_callback_completion()` 函数（`wait_callback_endpoint.py:169-203`）。
- 模块 `__all__` 不包含 `APIRouter`、`route`、`app` 或任何 Web framework 符号（`wait_callback_endpoint.py:843-850`）。
- Service import boundary 测试 `SERVICE_FORBIDDEN_PREFIXES` 包含 `"fastapi"`, `"flask"`, `"starlette"`, `"django"`, `"aiohttp"`（`test_import_boundary.py:10-20`），并通过 `test_service_does_not_import_forbidden_layers` 验证（47 passed）。
- Host import boundary 测试 `WAIT_CALLBACK_FORBIDDEN_PREFIXES` 同样禁止 Web framework（`test_import_boundary.py:135-143`），并通过 `test_wait_callback_adapter_has_no_service_ui_or_web_framework_dependency` 验证。
- PR body 声明 "not as a registered FastAPI/Flask route" — 与实现一致。

#### 2. Host 仍是 wait lifecycle/auth/replay/durable transition 真源

**结论：成立。** callback 不绕过 `resolve_wait` 管线。

**直接证据：**
- `DefaultWaitCallbackAdapter.resolve_callback()` 构造 `ResolveWaitRequest(source=CALLBACK)`（`wait_callback.py:434-440`），然后通过注入的 `CallbackWaitResolvePort` 进入 command layer。
- `HostCommandWaitCallbackPort.resolve_callback_wait()` 在 command layer 构造 `DefaultHostResolveWaitService` 并调用 `service.resolve_wait(wait_id, request)`（`command.py:854-865`）——与现有 `resolve_wait()` standalone function（`command.py:776`）使用同一 service、同一 state machine。
- Adapter 不直接写入 EventLog、Run、Attempt、wait record 或 projection（`wait_callback.py` 全文无 `append_event_log`、`update_run`、`update_wait_record` 等写入调用）。
- Adapter 的 `state_reader.read_wait_state()` 只做预读用于 stale/late 分类，不用于推断 `resolve_wait` 内部并发 race 结果（plan 第 193-194 行，实现 `wait_callback.py:525-558`）。

#### 3. Auth-before-read、replay idempotency、same-key conflict、digest 同源、stale/late handling、dispatch wakeup 语义

**结论：全部成立。**

**auth-before-read：**
- `resolve_callback()` 先调用 `self._authenticate(envelope.auth)`（`wait_callback.py:407`），认证拒绝立即返回 `AUTH_FAILED`（`wait_callback.py:408-415`），不执行后续 `state_reader.read_wait_state()`。
- 测试 `test_auth_rejected_returns_auth_failed_without_state_read()` 验证了此行为（`test_wait_callback.py` 第 236-262 行）。

**replay idempotency：**
- `wait_resolution_digest(wait_id, idempotency_key, outcome)` 只使用 wait_id、idempotency_key、outcome 计算 digest（`wait_resolution_digest.py:30-48`），`observed_at` 与 `completed_at` 不参与。
- 同一 outcome 的重复 callback 通过 `ResolveWaitRequest` 进入 `resolve_wait`，由 `DefaultHostResolveWaitService._resolve_wait_replay()` 检测为幂等重放并返回 `idempotent_replay=True`。
- 测试 `test_same_callback_replay_returns_replayed_no_new_events()` 验证了 replay 不产生新 EventLog（`test_wait_callback.py` 第 264-342 行）。

**same-key conflict：**
- 同一 idempotency key 但不同 outcome 进入 `resolve_wait` 后，由 `DefaultHostResolveWaitService._resolve_wait_conflict()` 检测并抛出 `HostApiError(code=IDEMPOTENCY_CONFLICT)`。
- Adapter 通过 `_result_from_host_api_error()` 映射为 `IDEMPOTENCY_CONFLICT`（`wait_callback.py:578-583`）。
- 测试 `test_same_key_different_outcome_returns_idempotency_conflict()` 验证（`test_wait_callback.py` 第 344-420 行）。

**digest 同源：**
- `wait_callback.py` 的 `_callback_payload_digest()` 调用 `dayu.host.durable.wait_resolution_digest.wait_resolution_digest()`（`wait_callback.py:518-522`）。
- `waiting.py` 的 `_wait_resolution_digest()` 同样调用 `wait_resolution_digest()`（`waiting.py:1146-1150` diff）。
- 模块 docstring 明确说明"callback adapter 与 direct resolve path 必须复用这里的实现"（`wait_resolution_digest.py:3-6`）。
- 测试 `test_callback_digest_equals_direct_resolve_digest_for_same_outcome()` 验证了 callback 与 direct resolve 路径共享同一 digest material（`test_wait_callback.py` 第 422-482 行）。

**stale/late handling：**
- `_stale_status_or_none()` 使用 wait record 的 `deadline_at`（优先）或 `expires_at`（回退）判断 stale（`wait_callback.py:525-558`）。
- `deadline_at=None` 且 `expires_at=None` 时不判定 stale（`wait_callback.py:540-541`）。
- 无效 deadline/expires 字符串映射为 `INVALID_WAIT_STATE`（`wait_callback.py:544-549`）。
- `_stable_late_status_or_none()` 根据预读 CANCELLED/LOST 状态映射 `LATE_WAIT_CANCELLED` / `LATE_WAIT_LOST`（`wait_callback.py:603-628`）。
- 测试覆盖了 stale deadline、无 deadline、late cancelled、late lost 等路径（`test_wait_callback.py` 第 484-598 行）。

**dispatch wakeup：**
- `HostCommandWaitCallbackPort.resolve_callback_wait()` 在 `result.dispatch_record is not None and not result.idempotent_replay` 时调用 `wake_dispatch()`（`command.py:860-863`）。
- Replay 不重复唤醒。
- 测试 `test_accepted_callback_wakes_dispatch_once()` 和 `test_replay_does_not_wake_dispatch_second_time()` 验证（`test_wait_callback.py` 第 130-170 行）。

#### 4. Service → Host 分层边界、import boundary、LLM-facing 文本约束、README/test 边界

**结论：符合 AGENTS.md。**

**分层边界：**
- Service mapper 通过 `WaitCallbackEndpointAdapter` Protocol 依赖 Host adapter（`wait_callback_endpoint.py:154-166`），从 `dayu.host` 包根导入类型（`wait_callback_endpoint.py:29-43`）——这是正确的跨层依赖方向。
- Host callback adapter 不导入 `dayu.service`、`dayu.ui`、`dayu.fins` 或任何 Web framework（grep 结果为空）。
- Service mapper 不导入 `dayu.host.durable`、`dayu.host.command` 或 HTTP framework（import boundary 测试通过）。

**import boundary：**
- `tests/host/test_import_boundary.py` 新增 `WAIT_CALLBACK_FORBIDDEN_PREFIXES` 与 `test_wait_callback_adapter_has_no_service_ui_or_web_framework_dependency()`（`test_import_boundary.py:135-143, 398-406`）。
- `tests/service/test_import_boundary.py` 的 `test_service_does_not_import_forbidden_layers()` 覆盖 Service 全部模块。

**LLM-facing 文本约束：**
- `wait_callback.py` 和 `wait_callback_endpoint.py` 的 docstring、dataclass 字段说明、函数参数说明均使用业务可读语义，不使用 Host/Engine 内部术语。
- 状态枚举值（`WaitCallbackAdapterStatus`、`WaitCallbackEndpointStatus`）使用自解释字符串值（`"accepted"`, `"transport_rejected"` 等）。

**README/test 边界：**
- `dayu/host/README.md` 新增两段契约说明（`README.md:216-217` diff），符合 AGENTS README 触发规则。
- `dayu/service/README.md` 新增 `wait_callback_endpoint` 说明和边界约束（`README.md:9-10, 29-30` diff）。
- `tests/README.md` 新增 callback 测试命令和覆盖范围说明（`tests/README.md:66, 140, 194` diff）。

#### 5. PR body 与实现一致性

**结论：一致。** PR body 明确声明的非目标均未实现：

- "not as a registered FastAPI/Flask route" → 实现为函数式 mapper ✓
- "intentionally does not add a real route" → 无路由注册 ✓
- "intentionally does not add secret backend" → 只有 `WaitCallbackAuthenticator` Protocol，无 secret store ✓
- "intentionally does not add HMAC/bearer verifier" → `WaitCallbackAuthenticator` 是类型化协议，不做具体验证 ✓
- "intentionally does not add issue-90 poller" → 无 poller ✓
- "intentionally does not add issue-92 physical cancel" → 无 cancel ✓
- "intentionally does not add Engine contract" → Engine 未修改 ✓
- "intentionally does not add UI surface" → UI 未触及 ✓
- PR body 的 validation 命令与 test 结果一致（47 + 56 passed, pyright 0 errors）。→

## Open Questions

无。

## Residual Risk

- **R1 — Adapter exception propagation**：`handle_wait_callback_completion()` 不捕获 `adapter.resolve_callback()` 抛出的异常。`DefaultWaitCallbackAdapter` 内部已捕获 `Exception` 并返回 `INTERNAL_ERROR`，但若提供非标准 adapter 实现且不遵守该契约，异常会穿透 Service mapper。当前无自定义 adapter 实现，风险低；若后续支持第三方 adapter，Service mapper 可增加一层 `except Exception` 兜底。
- **R2 — Race between pre-read and resolve**：Adapter 先通过 `state_reader.read_wait_state()` 预读 wait state 用于 stale/late 分类，再通过 `resolver.resolve_callback_wait()` 进入 `resolve_wait`。若两次操作之间 wait state 被并发修改（例如由 poller 或另一个 callback 触发），预读分类可能过时。当前实现已处理此情况：`_result_from_host_api_error()` 在收到 `INVALID_STATE` 时优先使用预读 stable 状态映射 late status，无法稳定分类时 fallback 到 `INVALID_WAIT_STATE`（`wait_callback.py:585-593`）。这符合 plan 第 477 行描述的 race 容忍语义。风险低，但若后续需要精确 raced late-state 分类，需要结构化 subcode（plan 已将此列为 future work）。
- **R3 — Dispatch wakeup asymmetry with direct resolve path**：`HostCommandWaitCallbackPort.resolve_callback_wait()` 显式调用 `wake_dispatch()`，但命令层 `resolve_wait()` standalone function 不调用 `wake_dispatch()`（`command.py:752-791`）。这表示 direct resolve 路径的 dispatch wakeup 由其他层（poller/admission）处理，callback 路径因绕过 poller 而需自行唤醒。当前语义正确，但两个路径的 wakeup 职责归属不同——若未来 direct resolve path 的 wakeup 机制变更，callback path 需要同步对齐。建议在 `command.py` 的 `HostCommandWaitCallbackPort` class docstring 中补充说明 wakeup 职责归属理由。

以上 residual risks 均为低风险，且均有明确的 future owner 或设计缓解。不构成阻止 merge 的理由。
