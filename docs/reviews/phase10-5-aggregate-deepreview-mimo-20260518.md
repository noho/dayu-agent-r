# P10.5 Aggregate Deepreview

## Gate

P10.5 aggregate deepreview。审查整个 P10.5 phase 是否可退出并进入 ready-to-open-draft-PR。

## 审查输入

- 设计真源：`docs/host/design.md` §10.1, §11, §21
- 总控文档：`docs/host/implementation-control.md`
- P10.5 plan：`docs/host/phase10-5-ordinary-local-multiturn-public-contract-plan.md`
- P10.5 discussion：`docs/host/post-p10.md`
- Accepted commits：plan `f38540b`；slice1 `d0e79a6`；slice2 `79f7b44`；slice3 `8e6f352`；slice4 `73db9f0`；slice5 `7282463`；slice6 `91b41fc`；latest checkpoint `983e93c`
- 工作区：clean

## 验证复跑结果

独立复跑以下命令，结果与 controller 记录一致：

| 验证项 | 结果 |
| --- | --- |
| `pytest tests/host -q` | 695 passed, 1 skipped (44.19s) |
| `pyright dayu/host tests/host` | 0 errors, 0 warnings, 0 informations |
| `git diff --check HEAD` | 无输出（无 whitespace 错误） |
| `git status` | clean working tree |

唯一 skip：`test_gemini_public_real_runner_two_turn_path`（Gemini API key 不可用，per-provider skip，符合 plan skip 规则）。

## 1. Public Contract Freeze 对照 design.md

### 1.1 `open_host(options)` async context manager

- design.md §11 要求：async-only opener，construction-time typed options，不引入 ConfigLoader / service locator
- 实现：`dayu/host/open_host.py` 定义 `open_host(options)` async context manager，接收 `OpenHostOptions` frozen dataclass
- **PASS**

### 1.2 Host public handle

- design.md §11 要求：只暴露 Service 需要的方法，不暴露 store / scheduler / registry / dispatch internals
- 实现：`Host` Protocol 在 `dayu/host/api.py` 定义，暴露 `ensure_session`、`create_session`、`get_session`、`close_session`、`submit_followup`、`get_run`、`cancel_run`、`cancel_session_runs`、`retry_run`、`replay_run`、`resolve_wait`、`watch_session_events`、`close`
- `open_host.py` 中 `PublicHostHandle` 实现该协议，内部持有 `_command_handle`、`_scheduler`、`_active_registry` 等，不暴露给 Service
- **PASS**

### 1.3 `HostClosedError` lifecycle exception

- design.md §11 要求：独立 lifecycle exception，不写 EventLog，不与业务状态混淆
- 实现：`api.py:2628` 定义 `class HostClosedError(Exception)`，不继承 `HostApiError`
- 测试：`test_package_exports.py` 验证在 `__all__` 中；`test_public_lifecycle_smoke.py` 验证 close 后抛出
- **PASS**

### 1.4 `HostEvent` terminal final answer view

- design.md §11 要求：terminal `SUCCEEDED` inline `HostFinalAnswerView`，字段 `content`、`filtered`、`degraded`、`finish_reason`、terminal status
- 实现：`api.py` 定义 `HostFinalAnswerView` frozen dataclass 含上述字段；`_validate_host_event_terminal_payload` 强制 `SUCCEEDED` 时 `final_answer is not None`
- 测试：`test_public_host_event.py`、`test_watch_session_events.py` 验证
- **PASS**

### 1.5 empty final answer -> FAILED

- design.md 未定义 empty content 特殊处理规则
- 实现：`test_watch_session_events.py::test_empty_final_answer_terminal_projects_as_failed_event` 验证 `content=""` 时 terminal kind 映射为 `HostEventKind.FAILED`，`error_message` 含 `"no displayable content"`
- 这是 display safety 守卫，不违反 design（design 只要求 SUCCEEDED 时有 final_answer view，不要求 Engine 必须产出非空 content）
- **PASS（合理实现，非 design 偏离）**

### 1.6 `close_session` / Host opener close / cancel 边界

- design.md §5/§11 要求：三者是不同动作；close_session 只关新输入；opener close 只关 runtime；cancel 写 cancel facts
- 实现：`test_public_lifecycle_smoke.py::test_close_session_opener_close_and_cancel_are_distinct` 显式断言三者分离
- **PASS**

### 1.7 Compactor baseline 独立于 ordinary Run override

- design.md §11 要求：compactor 模型/参数由 `open_host(options)` 独立 typed construction-time baseline 传入，不受 `SubmitFollowupRequest` override 影响
- 实现：`OpenHostOptions` 含 `compactor_baseline: CompactorExecutionBaseline | None`；`compactor_baseline=None` 时 fail-closed
- 测试：`test_public_compact_smoke.py` 使用 `_RealLLMContextCompactor`，验证 compactor 独立于 ordinary override
- **PASS**

### 1.8 `HostEventView` / `stream_run_events` 降级

- design.md §11 要求：不从 `dayu.host` public namespace 导出
- 实现：`__all__` 不含 `HostEventView`、`stream_run_events`
- README 已说明 "低层同步 command handle、run-level event 补读与本地执行装配仍保留在内部模块路径"
- **PASS**

## 2. Unified Coverage Table 对照

| Coverage | Owner slice | 测试名 | Public-path 断言 | 状态 |
| --- | --- | --- | --- | --- |
| S1 real-runner no-tool multi-turn | Slice 6 | `test_public_open_host_multiturn_smoke.py::test_real_runner_no_tool_two_turn_public_path` | open_host, submit_followup, HostEvent.final_answer | covered |
| S1 multi-client watch | Slice 3+4+6 | `test_two_watchers_observe_same_terminal_event` | 两个 watcher 独立观察同一 terminal event | covered |
| S1 per-run execution override | Slice 3+6 | `test_submit_followup_field_level_execution_override_freezes_effective_config` | field-level partial merge | covered |
| S1 WAITING public resume | Slice 5 | `test_resolve_wait_resumes_through_open_host_and_terminal_event` | public resolve_wait, after-commit wakeup | covered |
| S1 steer / retry / replay | Slice 5 | `test_steer_running_run_creates_new_attempt_public_path`; `test_retry_failed_run_creates_related_run_public_path`; `test_replay_succeeded_run_no_tool_public_path` | public handle, event visible, source relation | covered |
| S2 mock-tool wiring | Slice 3+6 | `test_mock_tool_fact_enters_memory_and_next_run_input`; `test_tool_names_subset_and_empty_freeze` | ToolBundle from opener, tool_names subset/empty, memory continuity | covered |
| S3 real-runner matrix | Slice 6 | `test_public_real_runner_matrix_smoke.py::{mimo,deepseek,gemini,qwen}` | 四类 provider per-provider skip | covered (gemini skipped: API key unavailable) |
| S4 compact real compactor | Slice 1+2+6 | `test_real_compactor_public_opener_compacts_and_preserves_continuity` | real compactor adapter, canonical events, memory projection | covered |
| S5 cancel accepted/queued/pre-dispatch | Slice 5 | `test_cancel_accepted_and_queued_runs_public_path`; `test_pre_dispatch_cancel_visible_in_watch` | public cancel commands only | covered |
| S5 active/session-scope cancel | Slice 5+6 | `test_active_cancel_emits_public_cancel_event`; `test_cancel_session_runs_scoped_to_session` | shared registry, session-scope isolation | covered |
| S5 close boundary | Slice 2+5 | `test_close_session_opener_close_and_cancel_are_distinct` | 三者分离 | covered |
| S1 per-run tool selection | Slice 3+6 | `test_tool_names_subset_and_empty_freeze` | None=all, empty=disable, subset filter, unknown rejected | covered |
| S1 concurrent queue idempotency | Slice 3+6 | `test_concurrent_queue_uses_client_request_id_idempotency` | (session_id, client_request_id) 幂等 | covered |

**not covered but accepted：**

| 项目 | 理由 | Owner |
| --- | --- | --- |
| LOST/RECOVERING retry | Phase scope 裁剪 | Phase 11 |
| Active cancel watchdog / stuck CANCELLING | Recovery 范围 | Phase 11 |
| Outbox offline terminal delivery | Phase 13 范围 | Phase 13 |
| Purge destructive cleanup | Phase 15 范围 | Phase 15 |
| Real Service / CLI / GUI 接入 | P10.5 non-goal | P11+ Service |

**blocking gap：无。**

## 3. Accepted Commits 审查

| Commit | 内容 | Review artifacts |
| --- | --- | --- |
| `f38540b` plan | handoff plan | plan-review-mimo, plan-review-ds, plan-review-codex, plan-rereview-mimo, plan-rereview-ds, controller adjudication x2 |
| `d0e79a6` slice1 | public opener types, export boundary, options | code-review-mimo, code-review-ds, code-review-controller |
| `79f7b44` slice2 | production composition root, handle lifecycle, wakeup | code-review-mimo, code-review-ds, rereview-mimo, rereview-ds, controller adjudication x2 |
| `8e6f352` slice3 | public request contract, effective config, tool set freeze | code-review-mimo, code-review-ds, followup-rereview-mimo, followup-rereview-ds, controller adjudication x2 |
| `73db9f0` slice4 | session-level live HostEvent, terminal final answer view | code-review-mimo, code-review-ds, controller adjudication |
| `7282463` slice5 | steer, retry, replay, resolve_wait, cancel | code-review-mimo, code-review-ds, controller adjudication |
| `91b41fc` slice6 | public-path smoke matrix, real runner matrix, real compactor, docs | code-review-mimo, code-review-ds, rereview-mimo, rereview-ds, controller adjudication x2 |

每个 slice 均经历 implementation -> code review (MiMo + DS) -> fix -> re-review -> controller adjudication 完整闭环。review artifacts 均在 `docs/reviews/` 下。

## 4. 重点关注项

### 4.1 empty final answer -> FAILED

- 实现：`HostEvent` 映射层对 `content=""` 的 SUCCEEDED terminal 映射为 `FAILED` kind，`error_message` 含 `"no displayable content"`
- 测试：`test_watch_session_events.py::test_empty_final_answer_terminal_projects_as_failed_event`
- design.md 未定义 empty content 特殊规则；此为 display safety 守卫，不违反 design
- **PASS**

### 4.2 provider skip 是否 broad skip

- S3 real-runner matrix：每个 provider（mimo/deepseek/gemini/qwen）有独立 test function，调用 `api_key_or_skip(case)` 检查 provider-specific env var
- `skip_if_provider_terminal_failed` 过滤 network failure、503、429 等，skip reason 包含 provider 和缺失条件
- 当前验证：gemini skip（API key 不可用），其余三个 provider 测试存在且通过条件正确
- **PASS（per-provider skip，非 broad skip）**

### 4.3 真实 runner/compactor success signal

- S1 real-runner：`test_public_open_host_multiturn_smoke.py` 走 `open_host` -> `submit_followup` -> `watch_session_events` terminal path
- S3 real-runner matrix：四类 provider 均走同一 public path
- S4 real compactor：`_RealLLMContextCompactor` 内部调用 `run_agent_and_wait` 真实 Engine runner，非 `FakeContextCompactor`
- **PASS**

### 4.4 旧测试迁移是否掩盖回归

- `test_public_run_api.py`：已更新为新 `ACCEPTED` 语义（非旧 `RUNNING` 语义）
- `test_admission_queue.py`：已适配新的 admission + scheduler governance 流程
- `test_command_handle.py`：已有 `_start_run` 内部引用
- `test_package_exports.py`：验证 `start_run` 不在 `__all__`
- 695 passed, 0 failed，无回归
- **PASS**

### 4.5 未写入 control_doc 的 residual risk

- S5 active cancel watchdog / stuck CANCELLING：plan 已标记归 Phase 11，control_doc Phase 11 前置条件中已提及
- Real runner matrix 全 skip 风险：当前至少 mimo/deepseek/qwen 三个 provider 有测试文件且 skip 条件独立；gemini 单独 skip 不阻塞
- **PASS（residual 已在 plan 和 control_doc 中追踪）**

## 5. Findings

### Blocking (0)

无。

### High (0)

无。

### Medium (2)

#### M1. `__all__` 包含应降级的内部类型

- 文件：`dayu/host/__init__.py:153`
- 问题：`HostLocalExecutionOptions` 在 `__all__` 中导出。plan 明确要求 "HostLocalExecutionOptions 降级为内部 implementation contract；Service 不理解这些名字"，且 README 已写 "HostLocalExecutionOptions 是内部本地执行装配类型，不再进入包根 __all__"
- 证据：`__init__.py` line 47 import，line 153 in `__all__`；README line 17 说明不再进入 `__all__`
- 影响：`from dayu.host import HostLocalExecutionOptions` 合法且符合 `__all__` 语义，违反 plan 的降级意图
- 建议：从 `__all__` 移除（保留 import 供内部模块使用）
- Owner：aggregate fix

#### M2. 三个降级符号仍从包根 import 可达

- 文件：`dayu/host/__init__.py:89,96,47`
- 问题：`start_run`（line 96）、`create_host_command_handle`（line 89）、`HostLocalExecutionOptions`（line 47）仍从 `dayu.host.command` / `dayu.host.api` import 到包根。虽不在 `__all__`，Python 模块属性仍可直接访问
- 证据：`from dayu.host import start_run` 实际可成功执行
- 影响：`__all__` 是 `from dayu.host import *` 的边界，但 `from dayu.host import start_run` 仍绕过。这不是 breaking change，但削弱了 plan 的降级意图
- 建议：删除这三行 import，需要使用的内部测试改从 `dayu.host.command` 直接导入
- Owner：aggregate fix

### Low (2)

#### L1. 测试辅助断言直接读取 internal durable state

- 文件：`test_watch_session_events.py`（`_event_log_count`）、`test_public_retry_replay.py`（`_event_type_count`）、`test_effective_execution_config.py`（`open_host_durable_store`）
- 问题：部分测试为辅助断言直接查询 SQLite event_log 表，而非通过 public API
- 影响：这些是 assertion-only 读取，不驱动控制流或绕过 public path；不影响 correctness 证明
- 建议：如后续有 public `get_run_events()` 等 API 可迁移；当前不阻塞
- Owner：后续 phase（如有 public event read API）

#### L2. `HostCommandHandleOptions` / `HostCommandFacet` 仍在 `__all__`

- 文件：`dayu/host/__init__.py:143,142`
- 问题：plan 要求 `create_host_command_handle(...)` 降为内部 / 低层测试 primitive，但其关联类型 `HostCommandHandleOptions` 和 `HostCommandFacet` 仍在 `__all__`
- 影响：README 已写 "低层 command handle factory 不再由包根作为普通 Service-facing 入口导出"，但类型仍在 public namespace
- 建议：低优先级，可后续 phase 清理
- Owner：后续 phase

## 6. Coverage Checklist

| 检查项 | 状态 | 证据 |
| --- | --- | --- |
| P10.5 冻结 ordinary local multi-turn public contract | covered | `open_host(options)` + public handle + `HostEvent` terminal view + all control commands |
| S1-S5 全部覆盖 | covered | 见 §2 Unified Coverage Table |
| real-runner matrix 四类 provider | covered | per-provider skip，当前 gemini skip（API key），其余通过条件存在 |
| real compactor | covered | `_RealLLMContextCompactor` 真实调用 runner |
| mock tool wiring | covered | `MockFactTool` 按参数机械返回，不按 expected answer |
| live watch | covered | `watch_session_events(session_id) -> AsyncIterator[HostEvent]` |
| steer/retry/replay/resolve_wait/cancel | covered | 各有独立 public-path 测试 |
| close boundary | covered | `test_close_session_opener_close_and_cancel_are_distinct` |
| memory catch-up / compact opener contract | covered | opener 注入 compactor baseline，memory projection catch-up on close |
| empty final answer -> FAILED | covered | display safety 守卫，test 验证 |
| 旧测试迁移 | covered | 695 passed, 0 failed |
| README 同步 | covered | `dayu/host/README.md` 和 `tests/README.md` 已更新 |
| pyright | covered | 0 errors, 0 warnings, 0 informations |
| git diff --check | covered | 无 whitespace 错误 |

## 7. Residual Risks

| 风险 | Owner | 阻塞 P10.5？ |
| --- | --- | --- |
| Real runner matrix 可能全 skip（API key / 网络） | Slice 6 validation；Controller 决定 | 否（当前至少 3 provider 有测试文件） |
| Active cancel watchdog / stuck CANCELLING | Phase 11 | 否 |
| Outbox offline terminal delivery | Phase 13 | 否 |
| Purge destructive cleanup | Phase 15 | 否 |
| `__all__` 含应降级类型（M1） | aggregate fix | 否（不阻塞 contract freeze 语义） |

## 8. 结论

**PASS。blocking count = 0。**

P10.5 已冻结 ordinary local multi-turn public contract：`open_host(options)` async opener、typed `OpenHostOptions`、`Host` / `HostHandle` async protocol、`HostClosedError` lifecycle exception、`HostEvent` terminal typed view with `HostFinalAnswerView`、`watch_session_events(session_id) -> AsyncIterator[HostEvent]`、`submit_followup(queue/steer)`、`retry_run`、`replay_run`、`resolve_wait`、`cancel_run`、`cancel_session_runs`、`close_session`。所有 public-path smoke 通过（S1-S5），pyright 零错误，695 测试全通过。

有 2 个 medium finding（`__all__` 含应降级类型、import 泄漏）可在 aggregate fix 中一并修复，不阻塞 draft PR gate。

建议下一步：执行 aggregate fix 修复 M1/M2 后，进入 ready-to-open-draft-PR gate。
