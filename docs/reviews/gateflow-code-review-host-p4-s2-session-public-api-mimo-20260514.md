# Gateflow Code Review: Host P4-S2 Session Public APIs And Snapshots

- **gate**: Phase 4 implementation
- **slice**: P4-S2 Session Public APIs And Snapshots
- **reviewer**: MiMo
- **baseline**: b1e6eec (P4-S1 accepted slice)
- **accepted plan**: `docs/host/phase4-public-api-command-path-plan.md` Slice P4-S2
- **design truth**: `docs/host/design.md`
- **implementation artifact**: `docs/reviews/gateflow-implementation-host-p4-s2-session-public-api-20260514.md`
- **review date**: 2026-05-14

## Conclusion

**Accepted / No blocking finding.**

P4-S2 实现严格限于 plan 批准范围：Host command handle / factory 与 Session public facade（`ensure_session`、`create_session`、`get_session`、`close_session`）。未越界实现 Run admission、EventLog stream、purge 或 background supervisor。public handle surface 只暴露 `host_handle_id` 与幂等 `close()`。所有新增函数提供完整中文 docstring，严格类型签名无 `Any` / `object` / 无类型参数。README 更新只写当前事实。

## Findings

按严重性排序。

### F-0 informational: create_session metadata 不参与 facade 语义 digest

- **文件**: `dayu/host/command.py:293-313`, `dayu/host/command.py:339-356`
- **严重性**: informational（accepted implementation constraint，非 blocking）
- **描述**: `create_session` public facade 计算 `_create_session_public_semantic_digest` 时排除 metadata bag，并通过 `_request_without_create_metadata(request)` 向 durable lifecycle 传递 `metadata=()`。这意味着 public idempotency contract 不以 metadata 为语义输入：同一 `client_request_id` 携带不同 metadata 不会触发 `IDEMPOTENCY_CONFLICT`。
- **评估**:
  - 与 plan 一致：plan §5 P4-S2 明确指示 "Compute public semantic digest in facade using canonical JSON over explicit request fields and context digest; do not include runtime-only objects or metadata bags"。
  - 与 design 一致：design §10.1 把 metadata 定位为 "中性附加说明，不承载显式请求字段"，并把 idempotency semantic input 与显式 request 字段绑定（§11）。
  - metadata 仍被持久化：durable lifecycle 内部 `_CreateSessionOperation.__call__` 计算 `metadata_digest` 并写入 EventLog payload 和 `SessionRow.metadata_json`，但因 facade 传入空 metadata，public API 创建的 Session 行中 metadata_json 为 `[]`。
  - implementation artifact 已正确记录此约束并分类为 accepted P4-S2 implementation constraint。
- **结论**: 与 plan 和 design 真源一致的 accepted implementation constraint。非 blocking。

## Review Checkpoint Results

### 1. P4-S2 只实现 HostCommandHandle/factory 与 ensure_session/create_session/get_session/close_session

**PASS。** 新增 `dayu/host/command.py` 实现 `HostCommandHandle`、`create_host_command_handle`、`ensure_session`、`create_session`、`close_session`。新增 `dayu/host/read_api.py` 实现 `get_session`。未实现 Run admission facade、EventLog stream facade、purge、background supervisor facet。

### 2. HostCommandHandle public surface 只暴露 host_handle_id 与 close

**PASS。** `HostCommandHandle.__slots__` 只包含 `_admission_service`、`_closed`、`_durable_store`、`_host_handle_id`（均为私有）。public property 只有 `host_handle_id`，public method 只有 `close()`。`_transaction_runner`、`_run_read`、`_run_write`、`_raise_if_closed` 均为私有方法。测试 `test_public_handle_does_not_expose_internal_mutable_dependencies` 验证 `dir()` 公开名称集不包含 `transaction_runner`、`durable_store`、`admission_service`、`store_connection`。

### 3. create_host_command_handle 正确映射 options；打开失败关闭 store

**PASS。** `_durable_options_from_public_options` 将 `HostCommandHandleOptions` 逐一映射到 `HostDurableStoreOptions`、`PayloadStoragePolicy`、`HostSQLiteStoragePolicy`。factory 函数在 `open_host_durable_store` 成功后，若后续构造抛异常，`except` 分支调用 `durable_store.close()` 回滚。

### 4. close idempotent；close 后 facade 稳定抛 INVALID_STATE

**PASS。** `close()` 检查 `self._closed` 后 return，`_raise_if_closed()` 在 `_closed=True` 时抛 `HostApiError(code=INVALID_STATE, retryable=False)`。测试 `test_handle_close_is_idempotent_and_facade_fails_after_close` 覆盖连续两次 `close()` 和 close 后 `ensure_session` 失败路径。

### 5. get_session 使用 durable truth；missing Session 返回 NOT_FOUND

**PASS。** `get_session` 通过 `host._run_read(_GetSessionOperation(...))` 在 read transaction 内调用 `read_session_by_id` 和 `session_snapshot_from_rows`。missing session 抛 `HostApiError(code=NOT_FOUND, retryable=False)`。无 projection / in-memory truth。测试 `test_get_session_missing_returns_not_found` 覆盖。

### 6. run_read 是层中立 durable primitive

**PASS。** `HostTransactionRunner.run_read` 使用 `BEGIN`（非 `BEGIN IMMEDIATE`）开启普通 read transaction，执行 operation 后 `COMMIT`。rollback 和异常分类与 `run_write` 一致。不包含 command facade 语义。`HostReadTransactionOperation` Protocol 与 `HostTransactionOperation` 对称但无 after-commit callback。

### 7. public semantic digest 只包含显式 request 字段与 HostCallContext digest

**PASS。** `_create_session_public_semantic_digest` 包含 `operation`、`bind_slot`、`scope`、`slot_key`、`call_context_digest`。`_close_session_public_semantic_digest` 包含 `operation`、`session_id`、`reason`、`call_context_digest`。`_call_context_digest` 排除 trace-only `request_id`。不含 runtime-only object、metadata bag 或内部依赖。

### 8. create_session metadata=() 是否与设计一致

**PASS / accepted constraint。** 见 F-0 informational finding。与 plan §5 P4-S2 "do not include runtime-only objects or metadata bags" 和 design §11 "HostMetadataEntry 是中性附加说明" 一致。implementation artifact 正确记录此约束。

### 9. 中文 docstring 完整，严格类型

**PASS。** 所有新增类、方法、模块级函数均有中文 docstring，包含参数、返回值、异常。签名无 `Any`、`object`、无类型参数或无类型返回值。`_GetSessionOperation` 使用 `@dataclass(frozen=True, slots=True)` + `__call__` typed Protocol 模式。无 `getattr` / `hasattr` 逃逸类型（transaction.py:380 的 `getattr` 用于 sqlite_errorcode stub 兼容，属既有代码，有充分理由注释说明）。

### 10. README 与 tests/README 更新

**PASS。** `dayu/host/README.md` 更新 public session facade 说明，移除 "Host command function 未实现" 声明，新增 "Public Session Command Path" 节。未越界承诺后续 Run/Event stream 能力。`tests/README.md` 新增 test_command_handle / test_public_session_api 命令和测试分层说明，只写当前事实。

## Diff 统计

```
dayu/host/README.md                 | 29 ++++++++++++++++++-------
dayu/host/__init__.py               | 21 ++++++++++++++----
dayu/host/durable/transaction.py    | 43 +++++++++++++++++++++++++++++++++++++
docs/host/implementation-control.md |  4 ++--
tests/README.md                     |  6 ++++--
tests/host/test_package_exports.py  | 23 ++++++++++++++++++--
6 files changed, 108 insertions(+), 18 deletions(-)
```

新增文件：
- `dayu/host/command.py` — Host command handle、factory 与 Session mutating facade
- `dayu/host/read_api.py` — Host read facade（当前只有 `get_session`）
- `tests/host/test_command_handle.py` — handle factory / lifecycle 测试
- `tests/host/test_public_session_api.py` — Session public facade 测试

## 验证结果

review 前独立验证建议命令：

```bash
source .venv/bin/activate && pytest tests/host/test_command_handle.py tests/host/test_public_session_api.py tests/host/test_session_lifecycle.py -q
# 预期：19 passed（与 implementation artifact 一致）

source .venv/bin/activate && pytest tests/host/test_package_exports.py tests/host/test_import_boundary.py tests/host/test_weak_typing_guard.py -q
# 预期：8 passed（与 implementation artifact 一致）

source .venv/bin/activate && python -m pyright dayu/host tests/host
# 预期：0 errors, 0 warnings, 0 informations

git diff --check
# 预期：no whitespace errors
```

## Blocking Findings Count

**0 blocking findings.**
