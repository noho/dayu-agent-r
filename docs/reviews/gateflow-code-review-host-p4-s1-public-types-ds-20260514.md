# Host P4-S1 Public Types Code Review (AgentDS)

- **review type**: code review
- **gate**: Phase 4 implementation
- **slice**: P4-S1 Public Types, Error Detail, Handle Options And Constants
- **approved plan**: `docs/host/phase4-public-api-command-path-plan.md`，Slice P4-S1
- **implementation artifact**: `docs/reviews/gateflow-implementation-host-p4-s1-public-types-20260514.md`
- **reviewer**: AgentDS
- **artifact path**: `docs/reviews/gateflow-code-review-host-p4-s1-public-types-ds-20260514.md`
- **conclusion**: accepted

## 1. Scope Verification

已确认 diff 范围严格限于 5 个文件，与 plan §Slice P4-S1 "Allowed files/modules" 完全一致：

- `dayu/host/api.py`
- `dayu/host/__init__.py`
- `tests/host/test_public_contracts.py`
- `tests/host/test_package_exports.py`
- `dayu/host/README.md`

未触及 `admission.py`、`durable/*`、`command.py`、`read_api.py` 或其它模块。未涉足 Engine / Fins / Service / UI / runtime。

## 2. P4-S1 Plan Item Completeness

### 2.1 UNSUPPORTED_OPERATION

| Requirement | Status | Evidence |
|---|---|---|
| `HostApiErrorCode.UNSUPPORTED_OPERATION = "unsupported_operation"` | pass | `api.py:266` |
| 进入 `api.__all__` | pass | `api.py:1411-1453` |
| 进入 `host.__all__` | pass | `__init__.py:63-111` |
| 测试覆盖枚举值 | pass | `test_public_contracts.py:226-234` |

### 2.2 SteerConflictDetail

| Requirement | Status | Evidence |
|---|---|---|
| frozen / slots dataclass | pass | `api.py:270-300`；`test_dataclasses_are_frozen_and_slots` 覆盖 |
| `target_run_id: str` | pass | `api.py:282` |
| `target_run_status: RunStatus \| None` | pass | `api.py:283` |
| `current_active_run_id: str \| None` | pass | `api.py:284` |
| `current_active_run_status: RunStatus \| None` | pass | `api.py:285` |
| `__post_init__` 校验 `target_run_id` 非空 | pass | `api.py:294-296` |
| `__post_init__` 校验 `current_active_run_id` 可选非空 | pass | `api.py:297-300` |

### 2.3 HostApiErrorDetail

| Requirement | Status | Evidence |
|---|---|---|
| 显式 TypeAlias = `SteerConflictDetail` | pass | `api.py:303` |
| 第一版成员仅 `SteerConflictDetail` | pass | 第二成员不存在 |
| 未引入 dict / JsonValue / Any / object / extra payload | pass | 纯 dataclass union |

### 2.4 HostApiError.detail

| Requirement | Status | Evidence |
|---|---|---|
| `detail: HostApiErrorDetail \| None = None` | pass | `api.py:1383, 1391` |
| 保留原有 code/message/retryable/str 行为 | pass | `test_host_api_error_carries_structured_fields` 验证 detail=None 与 detail=SteerConflictDetail 两路径 |
| 未引入 extra / payload / metadata / dict bag | pass | `vars(detail_error)` 只有 4 个字段 |

### 2.5 FollowupSnapshot accepted-run shape

| Requirement | Status | Evidence |
|---|---|---|
| `accepted_input_ref: str` | pass | `api.py:1214` |
| `behavior: FollowupBehavior` | pass | `api.py:1215` |
| `accepted_run_id: str` | pass | `api.py:1216` |
| `accepted_run_status: RunStatus` | pass | `api.py:1217` |
| `current_cursor: HostStreamCursor` | pass | `api.py:1218` |
| `queued_run_id: str \| None` | pass | `api.py:1219` |
| `target_run_id: str \| None` | pass | `api.py:1220` |
| queue 分支 `target_run_id` 必须 None | pass | `api.py:1243-1247` |
| queue + QUEUED 时 `queued_run_id == accepted_run_id` | pass | `api.py:1248-1253` |
| queue + RUNNING 时 `queued_run_id` 必须 None | pass | `api.py:1254-1259` |
| queue 分支只允许 QUEUED / RUNNING | pass | `api.py:1260-1264` |
| steer 分支不要求 `queued_run_id` | pass | 无 steer 分支额外校验 |

### 2.6 Stream Constants

| Requirement | Status | Evidence |
|---|---|---|
| `HOST_EVENT_STREAM_DEFAULT_LIMIT = 100` | pass | `api.py:18` |
| `HOST_EVENT_STREAM_MAX_LIMIT = 1000` | pass | `api.py:19` |
| 进入 `api.__all__` | pass | `api.py:1422-1423` |
| 进入 `host.__all__` | pass | `__init__.py:76-77` |
| 测试验证值及 DEFAULT <= MAX | pass | `test_event_stream_limit_constants_are_stable` |

### 2.7 HostCommandHandleOptions

| Requirement | Status | Evidence |
|---|---|---|
| `host_handle_id: str \| None` | pass | `api.py:547` |
| `db_path: pathlib.Path` | pass | `api.py:548` |
| `artifact_root: pathlib.Path` | pass | `api.py:549` |
| `create_parent_dirs: bool` | pass | `api.py:550` |
| `sqlite_busy_timeout_seconds: float` | pass | `api.py:551` |
| `sqlite_write_busy_retry_count: int` | pass | `api.py:552` |
| `sqlite_write_retry_initial_delay_seconds: float` | pass | `api.py:553` |
| `sqlite_write_retry_backoff_multiplier: float` | pass | `api.py:554` |
| `sqlite_write_retry_max_delay_seconds: float` | pass | `api.py:555` |
| `payload_inline_threshold_bytes: int` | pass | `api.py:556` |
| 可选 handle id 校验非空 | pass | `api.py:566-569` |
| Path 字段类型校验 | pass | `api.py:570-576` |
| Bool 字段类型校验 | pass | `api.py:577-579` |
| Timeout / delay / backoff / threshold 正数校验 | pass | `api.py:581-619` |
| 写重试次数非负校验 | pass | `api.py:587-592` |
| Bool 混入数值字段拒绝 | pass | `_require_non_negative_int` / `_require_positive_int` / `_require_positive_float` 均含 `isinstance(value, bool)` 拒绝 |
| 无魔法数字散落 | pass | 所有校验值通过 module-level helper 函数实现，无数值字面量散落 |

### 2.8 Exports

| Requirement | Status | Evidence |
|---|---|---|
| `api.__all__` 包含所有新增公共符号 | pass | 与 `EXPECTED_API_EXPORTS` frozenset 完全一致 |
| `host.__all__` 包含 api + tooling 符号 | pass | 与 `EXPECTED_HOST_EXPORTS` frozenset 完全一致 |
| api 符号直接来自 `dayu.host.api`（同一对象） | pass | `test_exported_symbols_are_same_objects_as_api_symbols` 验证 identity |

### 2.9 Tests

| Plan test requirement | Status | Coverage |
|---|---|---|
| Enum values include UNSUPPORTED_OPERATION | pass | `test_status_and_error_enum_values_are_stable` |
| HostApiError stores detail=None and SteerConflictDetail | pass | `test_host_api_error_carries_structured_fields` |
| FollowupSnapshot queue QUEUED shape | pass | `test_followup_snapshot_queue_accepts_queued_run_shape` |
| FollowupSnapshot queue RUNNING shape | pass | `test_followup_snapshot_queue_accepts_running_run_shape` |
| FollowupSnapshot rejects running Run in queued_run_id | pass | `test_followup_snapshot_queue_rejects_running_queued_run_id` |
| FollowupSnapshot rejects queue + target_run_id | pass | `test_followup_snapshot_queue_rejects_target_run_id` |
| FollowupSnapshot rejects queue + QUEUED without queued_run_id | pass | `test_followup_snapshot_queue_rejects_missing_queued_run_id` |
| FollowupSnapshot rejects unsupported status for queue | pass | `test_followup_snapshot_queue_rejects_unsupported_status` |
| Stream constants exported with DEFAULT <= MAX | pass | `test_event_stream_limit_constants_are_stable` |
| HostCommandHandleOptions rejects empty handle id | pass | `test_host_command_handle_options_rejects_empty_handle_id` |
| HostCommandHandleOptions rejects invalid paths | pass | `test_host_command_handle_options_rejects_invalid_paths` |
| HostCommandHandleOptions rejects invalid bool | pass | `test_host_command_handle_options_rejects_invalid_bool` |
| HostCommandHandleOptions rejects non-positive / negative numeric | pass | `test_host_command_handle_options_rejects_invalid_numeric_values` |
| Package exports match expected symbols | pass | `test_host_all_matches_phase1_public_contracts` etc. |

### 2.10 README

| Requirement | Status | Evidence |
|---|---|---|
| 仅写当前事实 | pass | 未写入 command facade / 运行时实现声明 |
| 新增 stream constants 说明 | pass | `README.md:11` |
| 新增 HostCommandHandleOptions 说明 | pass | `README.md:15` |
| 新增 typed error detail / UNSUPPORTED_OPERATION | pass | `README.md:18, 83` |
| 新增 FollowupSnapshot accepted-run 校验规则 | pass | `README.md:80` |
| 当前未实现清单保留 | pass | `README.md:99-104` |

## 3. Hard Constraint Verification

### 3.1 中文 docstring

所有新增/修改类型、函数均有完整中文 docstring，包含参数、返回值、异常说明。通过。

### 3.2 无 Any / object / 无类型签名

逐一检查 `api.py` 全部类型签名，确认无 `Any`、`object`、无类型参数、无类型返回值。通过。

### 3.3 无 getattr / hasattr 逃避类型

全文件搜索 `getattr` / `hasattr`，无匹配。通过。

### 3.4 无无结构 payload / god bag

- `HostApiError.detail` 为 typed union，不承载 dict / JsonValue。
- `HostApiErrorDetail` 是显式 TypeAlias，第一版成员只有 `SteerConflictDetail`。
- `HostCommandHandleOptions` 是显式字段 dataclass，不是 bag。
- `FollowupSnapshot` 每个字段都是定类型。
- 通过。

### 3.5 无兼容 wrapper / re-export

- `HostApiErrorDetail` 是 TypeAlias（语义别名），不是旧符号的 re-export。
- 无 wrapper function、facade 方法仅透传。
- 通过。

### 3.6 无反向依赖

`dayu.host.api` 依赖：`pathlib`、`dataclasses`、`enum`、`typing`、`dayu.contracts.json_value`。无 `dayu.engine`、`dayu.fins`、`dayu.service`、`dayu.ui` 引用。通过。

### 3.7 无 magic number 散落

所有校验值通过 module-level private helper 函数（`_require_*`）实现。Stream constants 为 module-level 公共常量。无硬编码数值散落方法体。通过。

### 3.8 其它

- 无 schema 迁移或旧库兼容代码。通过。
- `dayu.runtime` 未被触及。通过。

## 4. Adversarial Failure Pass

### 4.1 FollowupSnapshot steer 分支 target_run_id 验证

**发现**: `FollowupSnapshot.__post_init__` 对 steer 分支不要求 `target_run_id` 必填。`_require_optional_non_empty` 允许 `target_run_id=None`。

**评估**: 非缺陷。plan §3 明确："validation may still allow future steer shape, but it must not require queued_run_id"。Phase 4 steer 不会产生 FollowupSnapshot，当前 shape 允许未来扩展是正确的。

### 4.2 HostApiError 不是 dataclass

**发现**: `HostApiError` 继承 `Exception`，字段通过 `__init__` 直接赋值，不走 `dataclass(frozen=True)`。因此它不在 `PUBLIC_HOST_DATACLASS_TYPES` 元组中，也不是 frozen/slots dataclass。

**评估**: 非缺陷。`HostApiError` 是异常类，不是数据载体；直接继承 `Exception` 是合理设计。`vars()` 可读字段已在测试中验证。

### 4.3 _require_positive_float 参数类型标注与实际运行时行为不一致

**发现**: `_require_positive_float(value: float, ...)` 标注参数为 `float`，但实际 runtime 检查允许 `int | float`（通过 `isinstance(value, int | float)`）。

**评估**: 非缺陷。这是防御性校验：dataclass 字段标注为 `float` 但 Python 运行时不强制类型，调用方可能传入 `int`。拒绝 `bool`（`bool` 是 `int` 子类，被显式 `isinstance(value, bool)` 拦截）是正确且必要的。

### 4.4 SteerConflictDetail 不校验 status 字段

**发现**: `SteerConflictDetail.__post_init__` 仅校验 `target_run_id` 和 `current_active_run_id` 的非空性，不校验 `target_run_status` 和 `current_active_run_status` 的合法性。

**评估**: 非缺陷。这两个字段类型为 `RunStatus | None`，`None` 语义是"Run 不存在或无法读取状态"，是合法的。多余校验会限制合理语义。

### 4.5 HostCommandHandleOptions 不校验跨字段约束

**发现**: 不校验 `sqlite_write_retry_max_delay_seconds >= sqlite_write_retry_initial_delay_seconds` 等跨字段关系。

**评估**: 非缺陷。plan §3 未要求跨字段校验。这类约束属于后续 command handle factory slice（P4-S2）的负责范围，届时 factory 可做额外合理性检查。

### 4.6 测试覆盖边界

逐一核查 plan §Slice P4-S1 "Tests" 段落所列全部测试点，均被至少一个测试用例覆盖。无遗漏。

## 5. Findings Summary

### Blocking

无 blocking finding。

### Informational

无 informational finding。

## 6. Validation Results (Independent Re-run)

```
source .venv/bin/activate && pytest tests/host/test_public_contracts.py tests/host/test_package_exports.py -q
→ 30 passed in 0.05s

source .venv/bin/activate && python -m pyright dayu/host/api.py dayu/host/__init__.py tests/host/test_public_contracts.py tests/host/test_package_exports.py
→ 0 errors, 0 warnings, 0 informations

git diff --check
→ 无输出
```

## 7. Conclusion

**accepted**。P4-S1 完整实现了 plan 规定的所有 public type change：`UNSUPPORTED_OPERATION`、`SteerConflictDetail`、`HostApiErrorDetail`、`HostApiError.detail`、`FollowupSnapshot` accepted-run shape、stream constants、`HostCommandHandleOptions`，以及对应的 exports、tests 和 README 更新。所有项目硬约束通过。无 blocking finding。
