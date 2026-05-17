# P9.5 S3 Host Public Error Taxonomy And Command Handle Encapsulation — Code Review (AgentMiMo)

## Gate

- Role: AgentMiMo, review-only.
- Gate: P9.5 S3 Host Public Error Taxonomy And Command Handle Encapsulation code review.
- Approved plan: `docs/host/p9-5-pre-p10-hardening-plan.md` section S3.
- Implementation artifact: `docs/reviews/p9-5-s3-host-public-error-command-handle-implementation-20260517.md`.
- Reviewed files: `dayu/host/command.py`, `dayu/host/__init__.py`, `dayu/host/read_api.py`, `dayu/host/durable/errors.py` (read for impact), `tests/host/test_command_handle.py`, `tests/host/test_package_exports.py`.
- No code, tests, plan, or artifacts were modified. No commit, push, or PR.

## Review Focus Verification

### 1. durable/internal error → HostApiError 转换是否只在 public 边界发生且不泄漏内部类型

**结论：通过。转换仅在 public 边界发生，不泄漏内部类型。**

- `_host_api_error_from_durable_error()` 是 `command.py` 模块私有函数（`_` 前缀），不出包。
- 所有 public facade（`ensure_session`、`create_session`、`close_session`、`start_run`、`submit_followup`、`cancel_run`、`cancel_session_runs`、`resolve_wait`）均在 public 边界 catch `HostDurableError` 并调用转换 helper。
- `create_host_command_handle` factory 同样在 public 边界转换。
- 映射覆盖 5 个具体 `HostDurableError` 子类型 + 1 个 generic fallback；全部产出 `HostApiError`，无内部类型泄漏。
- `HostApiError` 继承 `Exception`，不继承 `HostDurableError`；public 调用方不可能 catch 到 durable 内部类型。
- 测试 `test_factory_translates_durable_config_error_to_public_error` 和 `test_retryable_durable_transaction_busy_returns_public_error` 直接验证了转换行为。

**Info F1**：`_run_read()` 和 `_run_write()` 存在双重 `HostDurableError` → `HostApiError` 转换。`_transaction_runner()` 已将 `HostDurableError` 转换为 `HostApiError`；外层 `_run_read`/`_run_write` 的 `except HostDurableError` 只能捕获 `run_read()`/`run_write()` 内部的 `HostDurableError`，不能捕获 `_transaction_runner()` 已转换的 `HostApiError`。功能正确（`HostApiError(Exception)` 不匹配 `except HostDurableError`），但阅读时需理解两层转换的分工。不阻断。

### 2. closed HostCommandHandle 是否所有 public facade 都先返回 INVALID_STATE 且不触达 durable/admission

**结论：通过。所有 public facade 在 closed handle 下先返回 `INVALID_STATE`。**

逐 facade 验证：

| Facade | closed guard | 验证 |
|---|---|---|
| `ensure_session` | `host._transaction_runner()` → `_raise_if_closed()` | ✅ |
| `create_session` | `host._transaction_runner()` → `_raise_if_closed()` | ✅ |
| `close_session` | `host._transaction_runner()` → `_raise_if_closed()` | ✅ |
| `start_run` | 显式 `host._raise_if_closed()` | ✅ |
| `submit_followup` | 显式 `host._raise_if_closed()` | ✅ |
| `cancel_run` | 显式 `host._raise_if_closed()` | ✅ |
| `cancel_session_runs` | 显式 `host._raise_if_closed()` | ✅ |
| `retry_run` | 显式 `host._raise_if_closed()` | ✅ |
| `replay_run` | 显式 `host._raise_if_closed()` | ✅ |
| `purge_session` | 显式 `host._raise_if_closed()` | ✅ |
| `resolve_wait` | `host._transaction_runner()` → `_raise_if_closed()` | ✅ |
| `get_session` | `host._run_read()` → `_transaction_runner()` → `_raise_if_closed()` | ✅ |
| `get_run` | `host._run_read()` → `_transaction_runner()` → `_raise_if_closed()` | ✅ |
| `stream_run_events` | `host._run_read()` → `_transaction_runner()` → `_raise_if_closed()` | ✅ |

- `test_session_and_read_facades_fail_closed_before_durable` 验证 session/read facade closed handle + durable row 不增长。
- `test_admission_backed_facades_fail_closed_before_public_branches` 验证 admission facade closed handle + durable row 不增长。
- `test_deferred_public_facades_fail_closed_before_unsupported` 验证 `retry_run`/`replay_run`/`purge_session` closed handle 先返回 `INVALID_STATE`（而非 `UNSUPPORTED_OPERATION`）+ durable row 不增长。

**Info F2**：`resolve_wait` 不显式调用 `_raise_if_closed()`，依赖 `_transaction_runner()` 内部检查。行为正确，但与 `start_run`/`submit_followup`/`cancel_run` 等显式 guard 的风格不一致。不阻断。

### 3. dayu.host 包根是否仍不导出 durable/admission/active registry/ToolRuntime/scheduler 内部

**结论：通过。**

- `dayu/host/__init__.py` 的 `__all__` 只包含 API 类型、command facade、read facade、tooling 类型。
- `test_host_root_does_not_export_internal_services` 验证以下符号不在 `vars(host)` 中：`ActiveWorkerRegistry`、`DefaultToolRuntimeFactory`、`HostAdmissionService`、`HostDispatchScheduler`、`HostDurableStore`、`HostDurableStoreOptions`、`ToolRuntimeBuildRequest`、`ToolRuntimeExecutionScope`、`ToolRuntimeFactory`、`ToolRuntimeHandle`、`open_host_durable_store`。
- `test_host_all_matches_current_public_contracts` 验证 `__all__` 与白名单完全一致。
- `test_exported_symbols_are_same_objects_as_api_symbols` 验证 API 类型直接来自 `dayu.host.api`。
- `test_command_symbols_are_exported_from_package_root_only` 验证 command facade 不进入 `dayu.host.api`。

### 4. 是否违反 docs/host/design.md、docs/host/p9-5-pre-p10-hardening-plan.md、AGENTS.md 硬约束

**结论：通过。无硬约束违反。**

| 约束 | 验证 |
|---|---|
| 不新增 public error code | ✅ 复用既有 `NOT_FOUND`/`INVALID_STATE`/`CONFLICT`/`IDEMPOTENCY_CONFLICT`/`UNSUPPORTED_OPERATION`/`INTERNAL_ERROR` |
| 不暴露 internal service property | ✅ `HostCommandHandle` public 面只有 `host_handle_id` + `close()` |
| 不加兼容 re-export | ✅ 无新 re-export |
| 不加 `Any`/`object`/无类型签名 | ✅ 所有函数有完整类型标注 |
| 函数有完整中文 docstring | ✅ |
| 不引入 P10+ 语义 | ✅ 无 Context Governance、RECOVERING、ToolsDiscovery、Audit 等 |
| 不破坏 Host 分层 | ✅ Host 不 import Service/UI/Fins |
| `_host_api_error_from_durable_error` 是模块私有 | ✅ `_` 前缀，不在 `__all__` |
| `HostCommandHandle` 不暴露 durable store / admission service | ✅ `__slots__` 全部 `_` 前缀 |

## Findings

### F1 [Info] `_run_read` / `_run_write` 双重 durable error 转换

- **File/line**: `dayu/host/command.py:190-193` (`_run_read`), `dayu/host/command.py:202-206` (`_run_write`)
- **Evidence**: `_transaction_runner()` 已将 `HostDurableError` 转为 `HostApiError`；外层 `except HostDurableError` 只能捕获 `run_read()`/`run_write()` 内部抛出的 `HostDurableError`。两层转换分工正确但不直观。
- **Impact**: 无功能影响。阅读代码时需要理解 `HostApiError` 不是 `HostDurableError` 子类才能确认不会双重转换。
- **Blocking**: No.

### F2 [Info] `resolve_wait` closed handle guard 风格不一致

- **File/line**: `dayu/host/command.py:566`
- **Evidence**: `resolve_wait` 依赖 `host._transaction_runner()` 内部的 `_raise_if_closed()`，而 `start_run`/`submit_followup`/`cancel_run` 等 facade 显式调用 `host._raise_if_closed()`。
- **Impact**: 行为正确。`_transaction_runner()` 内部的 `_raise_if_closed()` 在 durable 操作前执行，closed handle 不会触达 durable store。
- **Blocking**: No.

### F3 [Info] durable error 映射覆盖范围

- **File/line**: `dayu/host/command.py:606-649`
- **Evidence**: `_host_api_error_from_durable_error` 映射 5 个具体子类型。以下子类型走 generic fallback 映射为 `INTERNAL_ERROR(retryable=False)`：`HostSchemaMismatchError`、`HostDigestMismatchError`、`HostEventIdentityConflictError`、`HostInstanceIdentityConflictError`、`HostInstanceLifecycleConflictError`、`HostInstanceNotRegisteredError`、`HostPayloadReferenceError`、`HostArtifactWriteError`、`HostAfterCommitError`。
- **Impact**: 当前 generic fallback 足够安全（`INTERNAL_ERROR` + 不可重试）。若后续 durable 层新增需 public 区分的子类型，需在同一 helper 补充映射。实现 artifact 已记录此残余风险。
- **Blocking**: No.

## Scope Adherence Verification

### Confirmed: plan boundaries honored

- 变更文件：`dayu/host/command.py`、`tests/host/test_command_handle.py`、`tests/host/test_package_exports.py`。
- 未修改 `dayu/host/durable/errors.py`（只读确认影响）。
- 未修改 `dayu/host/api.py`、`dayu/host/read_api.py`。
- 未新增 public error code。
- 未暴露 internal service property。
- 未引入兼容 re-export / wrapper。

### Confirmed: no prohibited semantics introduced

- No P10+ semantics (Context Governance, RECOVERING, ToolsDiscovery, etc.)
- No new Host/Engine state-machine states or transitions
- No runner factory/registry
- No compatibility re-export/wrapper
- No `Any`/`object`/untyped signatures
- No extra payload bag

## P9.5 Scope / Non-Goals Check

| Concern | Status |
|---|---|
| Provider public state/contract | Not introduced |
| Retry model redesign | Not introduced |
| Host governance in parser/runner | Not introduced |
| Memory/tool governance in metadata | Not introduced |
| Proactive context governance | Not introduced |
| P10+ semantics | Not introduced |
| `RECOVERING` / Phase 11 | Not introduced |
| God object/function/dataclass | Not introduced |
| Compatibility re-export/wrapper | Not introduced |
| `Any`/`object`/untyped signatures | Not introduced |
| Extra payload bag | Not introduced |

## Summary

- **Blocking findings**: 0
- **Non-blocking findings**: 0
- **Info observations**: 3 (F1–F3)

S3 实现正确达成计划目标：durable/internal error 在 public 边界一致转换为 `HostApiError`，closed handle 下所有 public facade 先返回 `INVALID_STATE`，`dayu.host` 包根不导出 durable/admission/active registry/ToolRuntime/scheduler 内部。无硬约束违反。
