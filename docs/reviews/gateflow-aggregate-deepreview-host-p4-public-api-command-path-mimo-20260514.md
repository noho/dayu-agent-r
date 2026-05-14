# Aggregate Deepreview: Host Phase 4 Public API / Command Path

- **Reviewer**: MiMo
- **Date**: 2026-05-14
- **Branch**: `docs/host-phase4-control-state`
- **Design truth**: `docs/host/design.md`
- **Control doc**: `docs/host/implementation-control.md`
- **Plan truth**: `docs/host/phase4-public-api-command-path-plan.md`
- **Commits reviewed**: `e004031`, `9828fd1`, `b1e6eec`, `2958715`, `190d905`, `ee16e00`, `af61fe9`, `673a8db`, `34b1207`, `87fe87c`, plus current uncommitted tree
- **Scope**: P4-S1 through P4-S4 cumulative, cross-slice interactions, residual risk

## Verdict

**0 blocking findings. Phase 4 public API / command path is accepted.** 6 advisory / informational findings for future-phase awareness.

## Validation Results

```
pytest tests/host -q                          → 201 passed
python -m pyright dayu/host tests/host        → 0 errors, 0 warnings, 0 informations
git diff --check                              → clean
```

## Findings (ordered by severity)

### F-1 [Advisory] cancel_run deferred state mapping 的 Phase 归属未在公共文档中明确标注

**文件**: `dayu/host/command.py:776-812`, `dayu/host/README.md:48`

**问题**: `_is_deferred_cancel_state` 将 `WAITING`、`CANCELLING`、`RECOVERING` 映射为 `UNSUPPORTED_OPERATION`，并将 RUNNING + non-pre-dispatch 也映射为 `UNSUPPORTED_OPERATION`。`cancel_session_runs` 的 docstring 明确标注了各状态的 Phase 归属（Phase 5/7/11），但 `cancel_run` 的 docstring 和 README 只说"后续 owner 能力映射为 `UNSUPPORTED_OPERATION`"，没有逐状态标注 Phase。

**对比**:
- `cancel_session_runs` docstring (`command.py:393-395`): "dispatching / active worker、``WAITING``、``RECOVERING`` 分别由 Phase 5、Phase 7、Phase 11 负责"
- `cancel_run` docstring (`command.py:356-362`): 只说 "deferred 状态未支持"

**建议**: 在 `cancel_run` docstring 和 README L48 中补充各 deferred 状态的 Phase 归属，与 `cancel_session_runs` 保持一致。这不是代码问题，是文档可维护性问题——后续 Phase 实现者需要知道哪个 Phase 负责解锁哪个状态。

**用户要求 #2 合规性**: `cancel_session_runs` 的 Phase 5/7/11 提醒已充分覆盖（README L49、L113，command.py docstring L393-395，implementation-control.md L508、L1312）。`cancel_run` 的提醒需要补充。

---

### F-2 [Advisory] cancel_session_runs 不触发 queue promotion 未被测试显式验证

**文件**: `tests/host/test_public_cancel_session_runs.py:205-231`

**问题**: `test_cancel_session_runs_cancels_queued_and_predispatch_subset` 验证了 cancelled 状态和 `active_run_id is None`，但没有显式断言 "cancel 后没有新 Run 被 promote 为 active"。当前断言 `snapshot.active_run_id is None` 隐含了这一点（因为如果 promote 发生，active_run_id 不会是 None），但这个语义依赖于实现细节。

**当前行为**: 正确。`cancel_session_runs` 不调用 `promote_next_queued_run`，测试隐式覆盖。

**建议**: 可选——添加显式注释或断言说明 "cancel 后无 promote 发生"。非 blocking，当前隐式覆盖足够。

---

### F-3 [Advisory] _is_deferred_cancel_state 中 WAITING / CANCELLING / RECOVERING 路径无直接测试

**文件**: `dayu/host/command.py:804-809`

**问题**: `_is_deferred_cancel_state` 中 `run.status in (WAITING, CANCELLING, RECOVERING)` 的返回 True 路径没有直接测试。Phase 4 无法通过 public API 创建这些状态的 Run。`_mark_attempt_running` helper 只模拟了 RUNNING + non-pre-dispatch 路径。

**当前覆盖**:
- RUNNING + non-pre-dispatch Attempt: 通过 `test_cancel_session_runs_unsupported_non_terminal_has_no_partial_mutation` 覆盖
- RUNNING + no current_attempt_id: 防御性路径，Phase 4 不可达
- WAITING / CANCELLING / RECOVERING: Phase 4 不可达

**建议**: Phase 5/7/11 实现这些状态时，必须同步添加 `cancel_run` 和 `cancel_session_runs` 的 deferred state 测试。当前 Phase 4 无法覆盖，不是 Phase 4 的遗漏。

---

### F-4 [Informational] RunSnapshot 的 source_run_id / source_run_relation 在 Phase 4 始终为 None

**文件**: `dayu/host/read_api.py:209-238`, `dayu/host/api.py:1144-1196`

**问题**: `RunSnapshot` 包含 `source_run_id` 和 `source_run_relation` 字段，用于 retry/replay 场景。Phase 4 不实现 retry/replay，这些字段始终为 `None`。`run_snapshot_from_row` 不设置这些字段。

**当前行为**: 正确。Phase 4 non-goal 明确排除 retry/replay execution。

**建议**: README 已文档化 Phase 4 的 status-only terminal summary 限制。`source_run_id` / `source_run_relation` 的 Phase 5 retry/replay 实现时自然会填充。无需额外文档。

---

### F-5 [Informational] HostApiError.detail 的 TypeAlias 当前只有 SteerConflictDetail 一个成员

**文件**: `dayu/host/api.py:303`

**问题**: `HostApiErrorDetail: TypeAlias = SteerConflictDetail` 当前只有一个成员。设计文档说 "detail 是 explicit typed union（first version: SteerConflictDetail），no unstructured bag"。Phase 4 的 `UNSUPPORTED_OPERATION` 使用 `detail=None`，不使用 `SteerConflictDetail`。

**当前行为**: 正确。`SteerConflictDetail` 用于 `submit_followup(steer)` 冲突（Phase 4 返回 UNSUPPORTED_OPERATION 而非 conflict）。后续 Phase 可能需要更多 detail 成员。

**建议**: 无需变更。TypeAlias 随 Phase 扩展自然增长。

---

### F-6 [Informational] Phase 4 累积代码约 8,074 行，架构边界清洁

**文件**: `dayu/host/` 全部, `tests/host/` 全部

**验证结果**:
- `dayu.host` 不 import `dayu.engine` / `dayu.fins` / `dayu.service` / `dayu.ui` ✅
- 无 `Any` 类型注解 ✅
- 无 `object` 类型签名 ✅
- `getattr` 仅用于 `sqlite_errorcode` 兼容（有充分理由）✅
- 无兼容性 wrapper / re-export ✅
- 所有公共 dataclass 使用 `frozen=True, slots=True` ✅
- 所有枚举使用 `StrEnum` ✅
- 所有函数有完整中文 docstring ✅
- 包根导出白名单测试精确匹配 ✅

## Cross-Slice Interaction Matrix

| API | 调用路径 | 幂等 | EventLog 写入 | cancel 状态映射 |
|-----|----------|------|---------------|-----------------|
| `ensure_session` | `session_lifecycle` | slot PK | SESSION_CREATED | N/A |
| `create_session` | `session_lifecycle` | client_request_id + digest | SESSION_CREATED | N/A |
| `close_session` | `session_lifecycle` | client_request_id + digest | SESSION_CLOSED | N/A |
| `get_session` | `read_api` | 只读 | 无 | N/A |
| `start_run` | `admission` | client_request_id + digest | RUN_ACCEPTED + RUN_QUEUED/RUN_STARTED | N/A |
| `submit_followup(queue)` | `admission` | client_request_id + digest | FOLLOWUP_QUEUED / RUN_ACCEPTED | N/A |
| `submit_followup(steer)` | `command` 直接拒绝 | N/A | 无 | N/A |
| `get_run` | `read_api` | 只读 | 无 | N/A |
| `stream_run_events` | `read_api` | 只读 | 无 | N/A |
| `cancel_run` | `admission` | client_request_id + digest | CANCEL_REQUESTED + RUN_CANCELLED | queued/pre-dispatch: supported; WAITING/CANCELLING/RECOVERING/non-predispatch RUNNING: UNSUPPORTED |
| `cancel_session_runs` | `admission` | session-scope | batch CANCEL_REQUESTED + RUN_CANCELLED | queued/pre-dispatch: supported; any unsupported: fail-fast UNSUPPORTED |
| `retry_run` | `command` 直接拒绝 | N/A | 无 | UNSUPPORTED |
| `replay_run` | `command` 直接拒绝 | N/A | 无 | UNSUPPORTED |
| `resolve_wait` | `command` 直接拒绝 | N/A | 无 | UNSUPPORTED |
| `purge_session` | `command` 直接拒绝 | N/A | 无 | UNSUPPORTED |

## Phase 5/7/11 Reminder Compliance (User Requirement #2)

| 提醒位置 | 文件:行 | 内容 | 状态 |
|----------|---------|------|------|
| README `cancel_session_runs` 描述 | `dayu/host/README.md:49` | Phase 4 子集 + UNSUPPORTED 对 dispatching/active/WAITING/RECOVERING | ✅ |
| README Internal Admission | `dayu/host/README.md:113` | Phase 5/7/11 分别负责 | ✅ |
| command.py `cancel_session_runs` docstring | `command.py:393-395` | Phase 5/7/11 归属 | ✅ |
| implementation-control.md slice 定义 | `implementation-control.md:508` | 子集 + 追踪到 Phase 5/7/11 | ✅ |
| implementation-control.md 风险追踪 | `implementation-control.md:1312-1313` | Phase 5/7/11 owner 必须补齐 | ✅ |
| README `cancel_run` 描述 | `dayu/host/README.md:48` | "后续 owner 能力映射为 UNSUPPORTED_OPERATION" | ⚠️ 未逐状态标注 Phase（见 F-1） |

## Test Coverage Summary

| 测试文件 | 测试数 | 覆盖范围 |
|----------|--------|----------|
| `test_public_contracts.py` | 12 | P4-S1 类型契约、枚举值、校验 |
| `test_package_exports.py` | 5 | 包根导出白名单 |
| `test_command_handle.py` | 5 | handle factory/lifecycle/import boundary |
| `test_public_session_api.py` | 5 | Session facade 幂等/冲突/NOT_FOUND |
| `test_public_run_api.py` | 10 | start/followup/cancel/get_run/deferred |
| `test_public_cancel_session_runs.py` | 4 | session-scope cancel 子集/幂等/unsupported |
| `test_public_event_stream.py` | 7 | stream cursor/filtering/limit/validation |
| 其它 host 测试 | 153 | durable 层、admission 层、多进程 |
| **总计** | **201** | |

## Residual Risk Tracking

| 风险项 | 来源 | 状态 |
|--------|------|------|
| `cancel_session_runs` Phase 4 子集不是最终语义 | plan L539 | ✅ 已追踪到 Phase 5/7/11 |
| `stream_run_events.limit` 是 scan-window 而非返回事件数 | plan L540 | ✅ 设计决定，Phase 8 可加 read-model API |
| terminal summary 只有 status-only fallback | plan L541 | ✅ Phase 4 限制，已文档化 |
| `HostCommandHandleOptions` 与 durable storage policy 字段重复 | plan L539 | ✅ 设计意图，一处映射 |
| Phase 5/7/11 cancel 能力未实现 | control L1312 | ✅ 已追踪，README/docstring 已标注 |
