# Gateflow Code Review: Host P4-S2 Session Public APIs And Snapshots

- **gate**: Phase 4 implementation
- **slice**: P4-S2 Session Public APIs And Snapshots
- **review type**: adversarial code review (independent, not derived from AgentMiMo)
- **target**: workspace uncommitted diff
- **baseline**: `b1e6eec` (accepted P4-S1 slice)
- **accepted plan**: `docs/host/phase4-public-api-command-path-plan.md`, Slice P4-S2
- **design truth**: `docs/host/design.md`
- **review date**: 2026-05-14
- **reviewer**: AgentDS

---

## 验证结果

```bash
source .venv/bin/activate && pytest tests/host/test_command_handle.py tests/host/test_public_session_api.py tests/host/test_session_lifecycle.py -q
# 19 passed

source .venv/bin/activate && pytest tests/host/test_package_exports.py tests/host/test_import_boundary.py tests/host/test_weak_typing_guard.py -q
# 8 passed

source .venv/bin/activate && python -m pyright dayu/host tests/host
# 0 errors, 0 warnings, 0 informations

git diff --check
# no whitespace errors
```

---

## Findings

### Finding 1 — [MEDIUM] create_session 静默丢弃 request.metadata 持久化

**文件**: `dayu/host/command.py:339-356`

**事实**:

`_request_without_create_metadata()` 将 `CreateSessionRequest.metadata` 清空为 `()` 后传给 durable lifecycle。结果：

1. EventLog `SESSION_CREATED` 的 `payload_json.metadata_digest` 始终是空元组的 digest。
2. Session row 的 `metadata_json` 始终是 `"[]"`（空数组 canonical JSON）。
3. `ensure_session` 直接传递原始 request，metadata 被持久化；`create_session` 行为不对称。

```python
# command.py:339-356
def _request_without_create_metadata(
    request: CreateSessionRequest,
) -> CreateSessionRequest:
    return CreateSessionRequest(
        context=request.context,
        client_request_id=request.client_request_id,
        bind_slot=request.bind_slot,
        scope=request.scope,
        slot_key=request.slot_key,
        metadata=(),  # <-- 原 request.metadata 被丢弃
    )
```

**分析**:

Plan P4-S2 要求 "public semantic digest 只使用显式 request 字段与 context digest，不包含 metadata bag"。当前实现满足此要求——public digest（`_create_session_public_semantic_digest`）不包含 metadata。但实现用了更彻底的手段：不仅从 public digest 中排除 metadata，还**修改了传给 durable lifecycle 的 request 对象**，导致 metadata 完全不进入 durable store。

这不是 metadata 是否影响 idempotency 的问题——durable `_create_session_semantic_digest` 已经包含了 `metadata_digest`，可以通过 `metadata_digest` 独立于 public `caller_semantic_digest` 参与 durable 层幂等判断。当前实现相当于在 durable 层也永远写入空 metadata digest，两端都丢失了信息。

**严重性判断**:

- Plan 明确要求 metadata 不参与 public semantic digest——当前实现满足。
- Plan 未明确要求 metadata 必须持久化或禁止持久化。
- `HostMetadataEntry` 在 design.md 中被描述为 "中性附加说明，不承载显式请求字段"——这暗示 metadata 不是治理关键字段，丢失不违反核心语义。
- 但是，`CreateSessionRequest.metadata` 字段对调用方面向存在、可传入、有校验（`_require_metadata_entries`），却在 public facade 内被静默丢弃——调用方无法通过返回值或错误感知此行为。
- 这属于**语义契约不透明**，不是 root-cause 数据损坏。

**结论**: 非阻塞 finding。当前行为满足 P4-S2 scope 要求，但需在 `create_session` docstring 或 README 中标注 metadata 不持久化。若后续需要 metadata 持久化语义，应通过显式 design/plan 决定 metadata 是：
- (a) 仅在 public digest 中排除，仍持久化到 durable store（需修改 `_request_without_create_metadata`），或
- (b) 永久丢弃（当前行为，需对调用方公开文档说明）。

**建议修复方向**: 在 `create_session` 或 `_request_without_create_metadata` 的 docstring 中注明 metadata 不持久化，并在 Host README 的 public session command path 节注明此限制。

---

### Finding 2 — [LOW] 语义摘要中 call_context_digest 重复参与哈希

**文件**: `dayu/host/command.py:293-313`, `dayu/host/durable/session_lifecycle.py:558-578`

**事实**:

public facade 的 `_create_session_public_semantic_digest` 包含 `call_context_digest`；该 digest 作为 `caller_semantic_digest` 传入 durable lifecycle。durable 的 `_create_session_semantic_digest` 又直接将 `_call_context_digest(request.context)` 纳入外层 digest。`call_context_digest` 在两层均被计算并参与最终 semantic digest。

`close_session` 同理：`command.py:316-336` 与 `session_lifecycle.py:581-598`。

**分析**:

- 不导致功能缺陷或语义错误——digest 仍然唯一标识语义输入。
- 多余一层哈希不改变冲突检测正确性。
- 增加摘要计算步骤的冗余，未来若 `HostCallContext` 结构变更，需同步修改三处（public facade 摘要、durable 摘要、摘要 JSON 构造 helper）。

**结论**: 低严重性，非阻塞。不要求修复，但建议后续 slice 收口统一。

---

### Finding 3 — [LOW] HostCommandHandle 持有未使用的 _admission_service 依赖

**文件**: `dayu/host/command.py:62-66, 171-177`

**事实**:

`create_host_command_handle` 在 construction 期间调用 `create_host_admission_service(durable_store.transaction_runner)` 创建 admission service 并存入 handle。P4-S2 不暴露任何 Run admission facade，admission service 在 slice 内未使用。

**分析**:

- 创建 admission service 不触发副作用——它只是对 transaction runner 的引用封装。
- P4-S3 将使用该依赖。
- 实现 artifact 已将此记录为 residual risk。

**结论**: 低严重性，非阻塞。P4-S3 实现后消失。

---

### Finding 4 — [INFO] HostTransactionRunner.run_read 使用 BEGIN (deferred) 而非 BEGIN IMMEDIATE

**文件**: `dayu/host/durable/transaction.py:266-288`

**事实**:

`run_read` 使用 `connection.execute("BEGIN")` 启动读事务。SQLite 中这是 deferred transaction——事务在实际需要读锁时才获取。这与 `run_write` 使用 `BEGIN IMMEDIATE`（立即获取写锁）不同。

**分析**:

- 对纯读操作，`BEGIN` (deferred) 是正确选择：读事务不需要排他锁，deferred 行为避免了不必要的锁竞争。
- 当前 P4-S2 在单连接上工作（所有 transaction 通过同一 `HostTransactionRunner`），因此不存在并发读写的隔离问题。
- 如果后续引入连接池或多连接并发访问（例如后台 supervisor 连接），需评估读事务隔离级别是否满足业务需求。

**结论**: 信息级，非阻塞。当前实现正确，无需修改。

---

### Finding 5 — [INFO] 重复校验：HostCommandHandleOptions → HostSQLiteStoragePolicy 双重 post_init

**文件**: `dayu/host/api.py:558-619`, `dayu/host/durable/options.py:96-124`

**事实**:

`HostCommandHandleOptions.__post_init__` 校验所有数值字段边界（正数/非负）；`HostSQLiteStoragePolicy.__post_init__` 再次校验相同字段。`_durable_options_from_public_options` 映射过程中字段被校验两次。

**分析**:

- 双重校验不导致错误，且单次校验成本极低。
- 两次校验的路径不同（public layer vs durable layer），各层独立保证自己的不变量是正确的防御性做法。
- 不违反 plan 或 design 约束。

**结论**: 信息级，非阻塞。不要求去重。

---

## Scope 检查

逐项确认 P4-S2 scope 边界：

| 检查项 | 结果 |
|--------|------|
| HostCommandHandle / factory 实现 | ✅ `command.py:54-180` |
| ensure_session | ✅ `command.py:184-196` |
| create_session | ✅ `command.py:199-217` |
| get_session | ✅ `read_api.py:22-59` |
| close_session | ✅ `command.py:220-243` |
| 无 Run admission | ✅ 所有 Run 相关 symbol（start_run, cancel_run 等）未导出 |
| 无 EventLog stream | ✅ stream_run_events 未导出，不在 changed files |
| 无 purge | ✅ PurgeSessionRequest 已定义在 api.py（P4-S1），但 purge_session 函数未实现 |
| 无 background supervisor | ✅ 仅创建 admission service 依赖，不启动后台任务 |
| 无 policy provider | ✅ 不在 changed files |
| 无 dispatch/scheduler | ✅ 不在 changed files |

**scope 结论**: 严格限在 P4-S2 范围内。

---

## HostCommandHandle 封装检查

逐项确认 public handle 不暴露内部依赖：

| 暴露面 | 结果 |
|--------|------|
| `host_handle_id` (public property) | ✅ 稳定公开 |
| `close()` (public method) | ✅ 幂等公开 |
| `_transaction_runner()` (private method) | ✅ 下划线私有，仅同包 read_api 访问 |
| `_run_read()` (private method) | ✅ 下划线私有 |
| `_run_write()` (private method) | ✅ 下划线私有 |
| `_raise_if_closed()` (private method) | ✅ 下划线私有 |
| `_durable_store` (private attr) | ✅ 双下划线私有 |
| `_admission_service` (private attr) | ✅ 双下划线私有 |
| `_closed` (private attr) | ✅ 双下划线私有 |

测试 `test_public_handle_does_not_expose_internal_mutable_dependencies` 验证 `dir(command_handle)` 的非下划线名字只有 `host_handle_id` 和 `close`。

**封装结论**: 满足 plan stop condition——public handle 不暴露 durable transaction runner、admission service、store connection 或其他内部 mutable dependency。

---

## create_host_command_handle 映射完整性

`_durable_options_from_public_options()` (command.py:246-278) 映射检查：

| public 字段 | 映射到 | 结果 |
|-------------|--------|------|
| `db_path` | `HostDurableStoreOptions.db_path` | ✅ |
| `artifact_root` | `PayloadStoragePolicy.artifact_root` | ✅ |
| `payload_inline_threshold_bytes` | `PayloadStoragePolicy.payload_inline_threshold_bytes` | ✅ |
| `create_parent_dirs` | `PayloadStoragePolicy.create_artifact_root` | ✅ |
| `create_parent_dirs` | `HostDurableStoreOptions.create_parent_dirs` | ✅ |
| `sqlite_busy_timeout_seconds` | `HostSQLiteStoragePolicy.busy_timeout_seconds` | ✅ |
| `sqlite_write_busy_retry_count` | `HostSQLiteStoragePolicy.write_busy_retry_count` | ✅ |
| `sqlite_write_retry_initial_delay_seconds` | `HostSQLiteStoragePolicy.write_retry_initial_delay_seconds` | ✅ |
| `sqlite_write_retry_backoff_multiplier` | `HostSQLiteStoragePolicy.write_retry_backoff_multiplier` | ✅ |
| `sqlite_write_retry_max_delay_seconds` | `HostSQLiteStoragePolicy.write_retry_max_delay_seconds` | ✅ |

失败路径：`create_host_command_handle()` 在 `open_host_durable_store()` 成功后、`create_host_admission_service()` 或 `HostCommandHandle()` constructor 失败时，执行 `durable_store.close()` (command.py:179-181)。

**映射结论**: 完整，失败路径正确关闭 store。

---

## close 幂等性与关闭后 facade 行为

- `HostCommandHandle.close()` (command.py:101-110): 首次调用 `_durable_store.close()` + 设 `_closed = True`；再次调用直接 return。
- `_raise_if_closed()` (command.py:142-154): 抛出 `HostApiError(INVALID_STATE, retryable=False)`。
- 测试 `test_handle_close_is_idempotent_and_facade_fails_after_close`: 确认 close 可重复调用且关闭后 facade 抛出稳定错误。

**结论**: 正确。

---

## get_session 实现

- 使用 `host._run_read()` (read transaction) → `HostTransactionRunner.run_read()`。
- durable truth: 读取 `SessionRow`、`SessionSlotRow`、active Run id、queued Run ids。
- missing → `HostApiError(NOT_FOUND, retryable=False)`。
- 不使用 projection、in-memory cache 或 client-side state。

**结论**: 满足 plan 要求。

---

## public semantic digest

`_create_session_public_semantic_digest()` (command.py:293-313):
- 包含: `operation`, `bind_slot`, `scope`, `slot_key`, `call_context_digest`。
- 不包含: `metadata`, runtime-only objects, admission service refs, durable transaction refs。
- `_call_context_digest()` (command.py:359-366) 排除 `request_id`（tracing-only）。

`HostCallContext` JSON value 构造 (command.py:369-385): actor, source, authorization_claims, operation_context——所有字段均为 `HostCallContext` 的持久化字段，不含运行时注记。

**结论**: 满足 plan "canonical JSON over explicit request fields and context digest" 要求。

---

## 编码规范检查

| 检查项 | 结果 |
|--------|------|
| 中文 docstring | ✅ 所有公开/私有函数、类、模块均有完整中文 docstring |
| 严格类型（无 Any/object） | ✅ pyright 0 errors |
| 无 getattr/hasattr 滥用 | ✅ `command.py` 和 `read_api.py` 未使用 getattr/hasattr |
| 无 magic string 散落 | ✅ 模块级常量集中定义 (`_GENERATED_HANDLE_ID_PREFIX`, `_OPERATION_CREATE_SESSION`, `_OPERATION_CLOSE_SESSION`) |
| 无兼容 wrapper/god bag | ✅ 无 re-export wrapper，无 god object |
| 禁止反向依赖 | ✅ Host command path 不 import engine/fins/service/ui（有测试验证） |

---

## README 同步检查

- `dayu/host/README.md`: 更新了 public command path 描述、Session facade 声明、当前实现/未实现清单、验证命令。
- `tests/README.md`: 新增 command handle / public session API 测试覆盖说明，更新验证命令。
- 文档更新反映当前代码事实，无 "未来设计" 或旧术语残留。

**结论**: README 同步正确。

---

## 最终结论

**accepted / no blocking findings**

- blocking findings: **0**
- medium findings: **1** (create_session 元数据静默丢弃——语义契约不透明，但不违反 plan)
- low findings: **2** (call_context_digest 重复哈希、unused admission_service)
- info findings: **2** (run_read deferred transaction、双重校验)

**scope**: 严格限在 P4-S2，无越界。

**风险**:
- Finding 1 的 metadata 静默丢弃是当前 slice 内最值得关注的点。建议在 create_session docstring 中注明此行为，或在后续 design iteration 中明确 metadata 的持久化语义。
- 其余 low/info findings 不需要 P4-S2 内修复。

**未覆盖项**: Run admission (P4-S3)、EventLog stream (P4-S4)、purge、background supervisor、policy provider、WorkerProxy——均为后续 slice scope，不在本次 review 范围。
