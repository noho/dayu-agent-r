# P10.5 Aggregate Deepreview — AgentDS

## Gate

P10.5 aggregate deepreview。本 artifact 只做 review，不修改文件、不 commit/push/PR，不进入下一 gate。

## 结论

**PASS。blocking count = 0。P10.5 可以退出 deepreview gate 并进入 ready-to-open-draft-PR。**

## 验证依据

### 验证范围

- 设计真源：`docs/host/design.md`
- 总控文档：`docs/host/implementation-control.md` Phase 10.5 条目
- P10.5 plan：`docs/host/phase10-5-ordinary-local-multiturn-public-contract-plan.md`
- P10.5 discussion/任务清单：`docs/host/post-p10.md`
- Code artifacts：`dayu/host/*`、`tests/host/*`
- Review artifacts：Slice 1-6 全部 code review、re-review、controller adjudication 与 plan review / readiness review

### 当前状态复跑

本次 DS 独立复跑（非引用 controller 记录）：

```bash
$ source .venv/bin/activate && pytest tests/host -q
# 694 passed, 2 skipped in 80.72s

$ source .venv/bin/activate && python -m pyright dayu/host tests/host
# 0 errors, 0 warnings, 0 informations

$ git diff --check
# clean
```

## Coverage Checklist

逐项对照 `docs/host/post-p10.md` S1-S5 smoke matrix 与 G1-G16 gap 清单。

### S1 real-runner no-tool multi-turn smoke

| 项 | 状态 | 证据 |
| --- | --- | --- |
| thin service / open_host 入口 | covered | `tests/host/test_public_open_host_multiturn_smoke.py::test_real_runner_no_tool_two_turn_public_path` — 只 import `open_host` from `dayu.host`，不 import dispatch/scheduler internals |
| public command facade (ensure_session + submit_followup) | covered | 同上，`host.ensure_session()` -> `host.submit_followup(session_id, request)` |
| admission / response shape (accepted_run_id, accepted_run_status) | covered | `first.accepted_run_id` / `first.accepted_run_status` 已作为 FollowupSnapshot 字段使用 |
| per-run tool selection | covered | `test_tool_names_subset_and_empty_freeze` 覆盖 subset 与 empty 语义 |
| scheduler auto-wakeup | covered | `open_host` 内部 wiring，测试不手工唤醒 scheduler |
| pre-start Context Governance allow path | covered | `test_real_runner_no_tool_two_turn_public_path` 经真实 runner 路径，预算未超限时 pre-start governance 直接 allow |
| RunInputBuilder durable input | covered | user prompt 来自 durable `USER_INPUT_ACCEPTED`，测试不直接传 runner |
| LocalProxy / real runner boundary | covered | 真实 runner smoke 使用 `open_host_options(worker_factory=None)` → Host 内部构造真实 Engine worker |
| EngineEvent ingest terminal path | covered | `test_watch_*` 已验证 SUCCEEDED/FAILED/CANCELLED 终端投影 |
| projection / memory catch-up | covered | 第二轮 `submit_followup` 产出答案证明 memory continuity |
| second-turn continuity | covered | 第二轮 prompt 不含第一轮标记，答案仍可从上下文作答 |
| terminal event path (watch_session_events) | covered | `next_terminal_for_run(watcher, accepted_run_id)` 从 typed HostEvent 取 final_answer，不查 payload 表 |
| cancel compatibility | covered | `test_public_cancel_smoke.py` 覆盖 public cancel in opener handle |

### S2 mock-tool wiring smoke

| 项 | 状态 | 证据 |
| --- | --- | --- |
| ToolRuntime schema injection | covered | `mock_tooling_options()` -> `open_host_options(tooling_options=...)` -> Engine request tool_schemas 含 `lookup_mock_fact` |
| per-run tool selector subset/empty | covered | `test_tool_names_subset_and_empty_freeze` |
| tool executor path | covered | worker 通过 Engine `AgentRunRequest.tool_executor` 调用，不直接调 mock tool |
| Host accept barrier | covered | mock tool result 必经 ToolRuntime accept barrier 写入 `TOOL_RESULT_ACCEPTED` |
| tool fact memory projection | covered | `test_mock_tool_fact_enters_memory_and_next_run_input` 验证 verified fact 经 memory projection 进入第二轮 RunInputBuilder |
| tool fact second-turn continuity | covered | 第二轮 `AgentRunRequest.messages` 含 ToolMessage 与 event ref marker |
| mock tool 防作弊 | covered | mock tool 只按参数机械返回结构化结果，不读 expected answer/轮次/run id |

### S3 real-runner matrix smoke

| Provider | 状态 | 证据 |
| --- | --- | --- |
| mimo | covered | `test_mimo_public_real_runner_two_turn_path` — passed |
| deepseek | covered | `test_deepseek_public_real_runner_two_turn_path` — passed |
| gemini | covered (1 skipped) | `test_gemini_public_real_runner_two_turn_path` — skip 因 quota/rate-limit（环境原因），测试文件和 wiring 存在 |
| qwen | covered | `test_qwen_public_real_runner_two_turn_path` — passed |

全部走同一 `open_host` / `submit_followup` / `watch_session_events` terminal path，不做单独 shortcut。skip 仅因 provider 环境不可用。四类 provider 的测试文件 `test_public_real_runner_matrix_smoke.py` 存在。

### S4 compact smoke

| 项 | 状态 | 证据 |
| --- | --- | --- |
| small budget trigger | covered | `_SOFT_CONTEXT_WINDOW_SIZE=110`，`_SOFT_THRESHOLD_PROMPT_CHAR_COUNT=220` |
| real compactor adapter | covered | `_RealLLMContextCompactor` — 真实 LLM compactor，非 `FakeContextCompactor` |
| canonical compact event/artifact | covered | compact 后 `compactor.call_count >= 1`，`compactor.last_summary is not None` |
| memory projection consumption | covered | compact 后第二轮 `HostEvent.final_answer` 非空 |
| subsequent run continuity marker | covered | 第二轮要求输出 `DAYU_COMPACT_OK` |
| compactor execution baseline 独立于 ordinary Run override | covered | `CompactorExecutionBaseline` 独立传入，与 ordinary baseline 分离 |
| provider 不可用时精确 skip | covered | `skip_if_provider_terminal_failed` / `skip_if_provider_exception` 按 503/429/network/rate-limit 精确 skip |
| mock compactor 不计入 success signal | covered | `FakeContextCompactor` 不出现于 compact smoke 主路径 |

### S5 cancel smoke

| 项 | 状态 | 证据 |
| --- | --- | --- |
| public command path | covered | `cancel_run` / `cancel_session_runs` 通过 public handle |
| accepted / queued cancel | covered | `test_cancel_accepted_and_queued_runs_public_path` |
| pre-dispatch cancel | covered | `test_pre_dispatch_cancel_visible_in_watch` |
| active cancel visibility | covered | `test_active_cancel_emits_public_cancel_event` — deterministic worker 路径 |
| session-scope cancel | covered | `test_cancel_session_runs_scoped_to_session` |
| event / read path (watch + get_run) | covered | cancel 结果通过 public `get_run` 与 `watch_session_events` 观察 |
| close boundary | covered | `test_close_session_opener_close_and_cancel_are_distinct` — close_session / opener close / cancel 三个不同动作 |

### Steering / retry / replay / resolve_wait

| 项 | 状态 | 证据 |
| --- | --- | --- |
| steer local | covered | `test_steer_running_run_creates_new_attempt_public_path` — 同一 Run 新 Attempt，`STEER_REQUESTED` + terminal closeout |
| retry FAILED | covered | `test_retry_failed_run_creates_related_run_public_path` — 源 Run immutable，关联新 Run，`(source_run_id, client_request_id)` 幂等 |
| replay SUCCEEDED | covered | `test_replay_succeeded_run_no_tool_public_path` — no-tool 新 Run，不改写源 Run EventLog truth |
| resolve_wait resume | covered | `test_resolve_wait_resumes_through_open_host_and_terminal_event` — WAITING → public resolve_wait → 新 Attempt → terminal HostEvent |

### Coverage Summary

- Covered：S1, S2, S3 (含 1 skip), S4, S5, steer, retry, replay, resolve_wait, multi-client watch, queue idempotency, per-run field-level partial merge, close boundary
- Not covered but accepted：Recovery (Phase 11), Outbox (Phase 13), RemoteProxy (Phase 14), Purge (Phase 15), callback/poller loop (Phase 11+), web tools migration (Phase 12+)
- Blocking gap：无

## Specific Concern Review

### 1. empty final answer -> FAILED

**文件**：`dayu/host/engine_ingest.py:2830-2848`

`_final_answer_plan()` 在校验 `data.content.strip() == ""` 时返回 `_failed_plan(reason=_REASON_EMPTY_FINAL_ANSWER, …)`，拒绝写入 `RUN_SUCCEEDED`。这确保了：
- `RUN_SUCCEEDED` 始终有 displayable content
- `HostEvent` terminal `SUCCEEDED` event 的 `final_answer.content` 非空
- 空白 final answer 被正确投影为 typed `FAILED` HostEvent（含 `host_terminal_status=FAILED`、`failed_reason` 与 `error_code`）

与 design.md §11 要求一致：terminal `HostEvent` final answer view 必须提供可展示 content。验证：`tests/host/test_watch_session_events.py` 中的 `FAILED` host event 断言覆盖了此路径。

**结论：与 design 一致，无问题。**

### 2. provider skip 是否没有 broad skip

**文件**：`tests/host/public_smoke_support.py:87-145`，`skip_if_provider_terminal_failed()` + `skip_if_provider_exception()` + `_skip_if_provider_failure_message()`

skip marker 精确分类：
- `_NETWORK_FAILURE_MARKERS`：`clientconnectorerror`, `timeout`, `connection refused`, `network is unreachable` 等
- `_TEMPORARY_PROVIDER_UNAVAILABLE_MARKERS`：`503`, `server overloaded`, `model is overloaded`, `transient unavailable` 等
- `_EXPLICIT_UNAVAILABLE_MARKERS`：`status=unavailable`, `code=unavailable` 等
- `_TEMPORARY_PROVIDER_RATE_LIMIT_MARKERS`：`429`, `resource_exhausted`, `quota_exceeded`, `rate_limit_exceeded` 等

未匹配到明确 provider environment failure marker 时，非 provider 性失败（如 API schema 错误、public contract failure、Auth 错误）不会触发 skip，会 hard fail。DeepSeek compactor 空摘要仍 hard fail（不 skip）。

**结论：skip 精确，无 broad skip。符合 plan S3/S4 skip condition。**

### 3. 真实 runner / compactor success signal 是否足够

- **Runner**：4 类 provider 全部有 smoke test，使用真实 Engine worker。provider 不可用时精确 skip。mock runner / runner test double 不计入 P10.5 success signal（post-p10.md 要求已落实）。
- **Compactor**：使用 `_RealLLMContextCompactor` adapter，调用真实 LLM 生成摘要。compactor 的 `RunnerSpec` 与 ordinary run 的 `runner_spec` 分离，符合 plan "compactor execution baseline 独立于 ordinary Run override"。`FakeContextCompactor` 不出现于 compact smoke 主路径。

**结论：real runner/compactor success signal 足够。**

### 4. 旧测试迁移是否掩盖回归

`tests/host/test_public_run_api.py` 仍使用 `start_run` / `create_host_command_handle` 从 `dayu.host` 包根导入。这些测试覆盖 admission primitive 的低层行为（accepted pre-start、queue、idempotency、FIFO promotion、cancel）。新的 public service-facing 测试（`test_submit_followup_public_contract.py`、`test_public_open_host_multiturn_smoke.py`、`test_public_cancel_smoke.py` 等）独立覆盖 public `open_host` 路径。

检查旧测试：
- `test_start_run_accepts_and_attach_active_rejects_unstarted_run`：测试 accepted Run 的 attach_active conflict，属于 admission primitive。新 public 路径的 `submit_followup(queue)` -> `ACCEPTED` / `QUEUED` 语义在 `test_submit_followup_public_contract.py` 中已独立覆盖。无回归。
- `test_start_run_idempotent_replay_returns_latest_snapshot_without_events`：幂等重放测试，新路径的 `(session_id, client_request_id)` 幂等在 `test_concurrent_queue_uses_client_request_id_idempotency` 中已独立覆盖。无回归。
- 其余 start_run 测试覆盖 admission internal，对应 public 语义已有独立断言。

**结论：旧测试未掩盖回归。旧测试覆盖 admission primitive 内部路径，新 public 测试独立覆盖 service-facing 路径，两者不互相替代。但旧测试从包根导入低层符号是 residual 需要清理（见 H1）。**

### 5. 未写入 control_doc 的 residual risk

经审核全部 Slice 1-6 controller adjudication 与 re-review：

| 来源 | 描述 | 当前状态 |
| --- | --- | --- |
| Slice 1 N1 | `start_run` / `create_host_command_handle` 仍作为 `dayu.host` 模块属性可导入 | 未清理。Slice 1 adjudication 要求 P10.5 closeout 前重新检查。见 H1。 |
| Slice 1 N5 | `HostCommandHandleOptions` / `HostCommandFacet` 仍在 `__all__` | 未清理。Slice 1 adjudication 接受 deferred。见 H2。 |
| Slice 6 | 跨测试模块私有 helper 重复（MiMo M1、DS M1/M2） | Deferred to Phase 11 test hardening。不阻塞。 |
| Slice 6 | scheduler `_run_pre_start_governance` 私有方法测试依赖（MiMo M2） | Deferred to Phase 11。不阻塞。 |
| Gemini | provider quota/rate-limit 导致 S3 skip | 环境 residual，非 Host public contract residual。已在 Slice 6 re-review 中接受。 |

**无新发现的未写入 residual risk。上述 deferred 项均已记录于对应 controller adjudication，无遗漏。**

## Findings

### Blocking (0)

无。

### High (3)

#### H1 — `start_run` / `create_host_command_handle` 仍作为 `dayu.host` 包根模块属性可导入

**文件**：`dayu/host/__init__.py:89,96`
**来源**：Slice 1 Controller N1，要求在 P10.5 phase closeout 前重新检查
**证据**：

```python
# dayu/host/__init__.py:89
create_host_command_handle,
# dayu/host/__init__.py:96
start_run,
```

这两个符号已从 `__all__` 移除（`test_package_exports.py` 验证通过），但作为模块级属性仍可通过 `from dayu.host import start_run` 直接导入。`tests/host/test_public_run_api.py:39` 仍从包根导入 `start_run`。

**影响**：Service 程序员可能误用 `start_run` 而非 `submit_followup(queue)`。`start_run` 绕过 `open_host(options)` 的 typed baseline 与 scheduler wakeup。

**建议**：在 P11 或下一个 cleanup slice 中将这两个符号从 `__init__.py` 模块属性中移除；旧测试迁移到 `from dayu.host.command import start_run as _start_run` 或等价内部路径。这不阻塞 P10.5 exit，因为：
- 正确使用路径 (`open_host` + `submit_followup`) 完整可用且有 smoke 验证
- `__all__` 已正确过滤
- 旧测试仍需要这些符号做低层 admission 验证

#### H2 — `HostCommandHandleOptions` / `HostCommandFacet` 仍在 `__all__`

**文件**：`dayu/host/__init__.py:40,142`
**来源**：Slice 1 Controller N5
**证据**：`HostCommandHandleOptions` 和 `HostCommandFacet` 是低层 command handle 的构造类型，不应出现在 Service-facing `__all__`。Slice 1 adjudication 接受 deferred 给后续 export cleanup，但 P10.5 closeout 时仍未清理。

**影响**：低层同步 command handle 概念泄漏到 Service-facing 命名空间，可能误导 Service 程序员使用 `create_host_command_handle` + `HostCommandHandleOptions` 替代 `open_host` + `OpenHostOptions`。

**建议**：P11 或 P10.5 follow-up 中从 `__all__` 移除并只保留为内部模块属性。不阻塞 exit，因为正确路径的 `open_host` + `OpenHostOptions` 已有完整 smoke 验证。

#### H3 — `HostLocalExecutionOptions` 仍在 `dayu.host.api.__all__`

**文件**：`dayu/host/api.py`（`__all__` 中含 `HostLocalExecutionOptions`）；`tests/host/test_package_exports.py` 通过 `ROOT_INTERNAL_API_NAMES` 将其从 `host.__all__` 过滤
**证据**：`HostLocalExecutionOptions` 是内部实现类型（plan 明确定义为 internal contract）。它虽然在 `host.__all__` 被过滤（正确），但仍在 `api.__all__` 中（低层代码可直接访问）。`test_package_exports.py` 通过 `ROOT_INTERNAL_API_NAMES` 机制已承认其为 internal。

**影响**：跨模块通过 `dayu.host.api` 直接导入此类型在技术上可行，但实际风险低，因为它不在 Service-facing `dayu.host.__all__` 中。

**建议**：可选 cleanup，不阻塞 exit。

### Medium (4)

#### M1 — `test_public_run_api.py` 仍从包根导入低层符号

**文件**：`tests/host/test_public_run_api.py:13-41`
**证据**：测试从 `dayu.host` 导入 `start_run`、`create_host_command_handle`、`HostCommandHandleOptions`、`HostLocalExecutionOptions` 等低层/内部类型，而非从 `dayu.host.command` / `dayu.host.api` 内部路径导入。

**影响**：使这些类型的模块级属性拆除（H1/H2 fix）需要迁移此测试文件的 import。

**建议**：与 H1/H2 同步修复。不阻塞 exit。

#### M2 — 跨 smoke 测试私有 helper 重复

**来源**：Slice 6 Controller deferred (MiMo M1, DS M1/M2)
**证据**：`FinalAnswerWorkerFactory`、`open_host_options`、`deterministic_runner_spec` 等在多个 smoke test 文件中各自定义或从 `public_smoke_support.py` 引用。`public_smoke_support.py` 承载了 smoke helper、provider case、skip logic、mock tooling 等不相关职责。

**影响**：测试可维护性下降，不影响 Host public contract correctness。

**建议**：Phase 11 或独立 test hardening slice 收口。不阻塞 exit。

#### M3 — `StartRunRequest` 仍在 `api.__all__` 与 `host.__all__`

**文件**：`dayu/host/__init__.py`（`__all__` 含 `StartRunRequest`）
**证据**：`StartRunRequest` 是 `start_run` 的 request type。`start_run` 已从 Service-facing namespace 移除，但其 request type 仍在 `__all__`。这造成 Service 可以 import `StartRunRequest` 但没有 public API 能使用它（`start_run` 不在 `__all__` 中）。

**影响**：轻度误导。无实际风险，因为 Service 不使用 `start_run`。

**建议**：可选 cleanup。不阻塞 exit。

#### M4 — Gemini S3 跳过，S4 compactor 使用 deepseek provider

**证据**：
- S3 Gemini skip 因 quota/rate-limit（环境原因）
- S4 compactor 使用 deepseek provider（`PROVIDER_CASES[1]`，即 deepseek case）

**影响**：当前验证环境至少有 3 个 real runner provider 可用 + 1 个 compactor provider 可用。如果生产环境所有 provider 都不可用，P10.5 success signal 的真实 runner/compactor 证据会缺失。

**建议**：Slice 6 Controller 已接受此 residual risk。如未来 provider 全 skip，需 Controller 决定是否接受。不阻塞 exit。

### Low (3)

#### L1 — `HostEventView` 在 `api.__all__` 但不在 `host.__all__`

**文件**：`dayu/host/api.py`（`__all__` 含 `HostEventView`）
**说明**：`HostEventView` 正确地不在 `host.__all__` 中（通过 `ROOT_INTERNAL_API_NAMES` 过滤），但仍在 `api.__all__`。`dayu/host/README.md` 已明确它是内部 diagnostic DTO。无实际风险。

#### L2 — `HostEventStream` 作为类型别名

**说明**：plan 要求 `HostEventStream` 若保留只能作为内部类型别名。当前实现中它是 `api.py` 中的 `AsyncIterator[HostEvent]` 类型别名，不在 `host.__all__`（被 `ROOT_INTERNAL_API_NAMES` 过滤）。符合 plan 要求。

#### L3 — `HostLocalExecutionOptions` 在 README 中提及为内部类型

**文件**：`dayu/host/README.md:18`
**说明**：README 第 18 行写 `HostLocalExecutionOptions` 是内部本地执行装配类型，不再进入包根 `__all__`。这与代码一致。但 `HostCommandHandleOptions` 在第 17 行被列为 "command handle options" 且仍在 `__all__` — README 表述与 `__all__` 一致。

## 设计一致性审查

对照 `docs/host/design.md`：

| 设计要求 | 实现状态 |
| --- | --- |
| §10.1 Host Handle / Composition Root | `open_host(options)` 已实现，返回 `Host` async handle。内部装配 durable store、scheduler、active registry、memory catch-up、compactor baseline。 |
| §11 Host 公共接口 | async-only `open_host(options)`，handle 方法包括 `ensure_session`/`create_session`/`get_session`/`close_session`、`submit_followup`、`cancel_run`/`cancel_session_runs`、`retry_run`/`replay_run`、`resolve_wait`、`watch_session_events` → `AsyncIterator[HostEvent]`。`start_run` 已从 `__all__` 移除。 |
| §11 terminal HostEvent final answer view | `HostEvent` typed kind union + `HostFinalAnswerView`（`content`、`filtered`、`degraded`、`finish_reason`、terminal_status）。SUCCEEDED/FAILED/CANCELLED 三种 terminal kind 已覆盖。 |
| §11 per-run execution override field-level partial merge | `SubmitFollowupRequest.runner_spec`/`runner_options`/`agent_policy` 各字段独立 optional，省略使用 opener baseline。Smoke 覆盖。 |
| §12 Follow-up / Steer | `submit_followup(steer)` 已实现本地语义，active RUNNING/WAITING 目标 Run，同一 Run 新 Attempt。Smoke 覆盖。 |
| §18 ToolRuntime | Per-run `tool_names` selector（None=all, frozenset()=none, non-empty=subset）已实现，admission validation + effective tool set freeze。Smoke 覆盖。 |
| §21 Retry / Replay | `retry_run` (FAILED → 关联新 Run) 和 `replay_run` (SUCCEEDED → no-tool 关联新 Run) 已实现。 |
| §23 RunInputBuilder | memory catch-up + compact artifact provider 已接入 dispatch path。 |
| §24 Conversation Memory | memory projection catch-up 通过 `catch_up_conversation_memory_projection` 在 dispatch 前执行。 |
| §25 Context Governance | proactive compact（pre-start budget check）与 reactive compact（Engine overflow recovery）均已实现。Compactor execution baseline 独立于 ordinary Run override。 |

**无设计偏离。**

## 总控文档 sync 状态

`docs/host/implementation-control.md` Phase 10.5 条目的退出条件逐项验证：

1. ✅ "普通 Service 只调用 Host public interface / contract，即可完成普通本地多轮会话闭环" — 已验证（S1-S5 smoke）
2. ✅ "submit_followup(steer)、retry_run(...)、replay_run(...) 不再是普通本地语义下的 stable unsupported" — 已验证
3. ✅ "real-runner / mock-tool / real-runner matrix / cancel smoke 均使用同一 open_host / public command / public read path" — 已验证
4. ✅ "P10.5 对普通本地多轮会话 public interface / contract 的冻结结论已写入" — 本 artifact 即为冻结结论
5. ✅ "P10.5 已经把真实生产系统 Service 将来接入所需的 Host 普通多轮生产接线做实" — 已验证
6. ✅ "P11 Recovery 可以在不破坏 P10.5 已冻结普通本地多轮 public contract 的前提下继续实施" — 已验证

## README 同步状态

| README | 状态 | 检查项 |
| --- | --- | --- |
| `dayu/host/README.md` | 已同步 | 描述了 `open_host(options)`、public handle 方法、live watch、terminal final answer view、close/cancel/close_session 边界、内部 demotion 说明 |
| `tests/README.md` | 已同步 | 描述了 P10.5 public-path smoke 分层、real-runner skip 规则、mock-tool vs mock-runner 边界、compact smoke provider gating |
| `docs/host/post-p10.md` | 未机械重写 | 仍保留 P10.5 任务清单/discussion，符合 doc 职责 |
| 根 `README.md` | 未触发 | 无 CLI/entrypoint/config 变化 |

## Residual Risk Summary

| Risk | Owner | Phase |
| --- | --- | --- |
| `start_run`/`create_host_command_handle` 模块属性未清理 | P11 cleanup | Phase 11 |
| `HostCommandHandleOptions`/`HostCommandFacet` 仍在 `__all__` | P11 cleanup | Phase 11 |
| Recovery / positive orphan proof | Phase 11 | Phase 11 |
| ToolsDiscovery / ScenePrepare | Phase 12 | Phase 12 |
| Outbox concrete read/drain / offline terminal delivery | Phase 13 | Phase 13 |
| RemoteProxy | Phase 14 | Phase 14 |
| Purge destructive cleanup | Phase 15 | Phase 15 |
| Provider/compactor 全 skip 风险 | Slice 6 validation → Controller | Already accepted |
| 测试 cross-module helper 重复 | Phase 11 test hardening | Phase 11 |
| Gemini quota/rate-limit skip | Environment | Not Host contract |

## Validation Recap

```bash
# DS 独立复跑
source .venv/bin/activate && pytest tests/host -q
# 694 passed, 2 skipped

source .venv/bin/activate && python -m pyright dayu/host tests/host
# 0 errors, 0 warnings, 0 informations

git diff --check
# clean (无工作区变更)
```

## Closeout

**P10.5 ordinary local multi-turn public contract IS frozen.** 后续真实生产系统 Service 调用 `open_host(options)` + `host.submit_followup()` + `host.watch_session_events()` 即可完成普通本地多轮闭环。后续 P11-P15 仅扩展 Host 能力，不应改变 P10.5 已冻结的普通多轮生产接线。

**本 review 建议：进入 ready-to-open-draft-PR。**
