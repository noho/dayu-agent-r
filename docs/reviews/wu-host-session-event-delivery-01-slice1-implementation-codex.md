# WU-HOST-SESSION-EVENT-DELIVERY-01 Slice 1 Implementation

## 元数据

- Work Unit：`WU-HOST-SESSION-EVENT-DELIVERY-01`
- Gate：`implementation-slice-1`
- Agent：`AgentCodex`
- 基线 accepted plan commit：`8b29462c`
- accepted plan amendment commit：`33af05fa`
- Plan：`docs/host/wu-host-session-event-delivery-01-plan.md`
- Amendment adjudication：`docs/reviews/wu-host-session-event-delivery-01-slice1-stop-plan-rereview-controller-adjudication.md`
- Artifact：`docs/reviews/wu-host-session-event-delivery-01-slice1-implementation-codex.md`
- 结论：`PASS`。Slice 1 owner contract、机械传播、验证与 README audit 已完成；没有 blocking open question 或未分类 residual risk。

## Gate scope 与第一性原理裁决

问题动机成立。旧实现把 successful sync factory return 当成 attach 成功，但 durable cursor transaction 实际延迟到首次迭代；同时每 watcher 固定 256 queue、delivery overflow 复用 availability 错误，且没有 per-Session admission owner。这样无法证明 activation、容量、overflow 与 release 的唯一 Host owner。

Slice 1 只收口以下语义：Host public async attach、public closable iterator、item-only policy、per-Session reservation、per-subscription mailbox/in-flight、typed overflow/admission、strict config 与 assembly。Service relay 的删除、causal fence/reconciliation、terminal post-commit port/coordinator、exact-five observation 与 UI executor 均不属于本 slice。

## Owner contract

| 语义 | 唯一 owner | 本 slice 实现 |
|---|---|---|
| public iterator、policy、错误码/detail | `dayu.host.api` | `HostSessionEventIterator`、required `HostSessionEventDeliveryPolicy`、`DELIVERY_INTERRUPTED` / `RESOURCE_EXHAUSTED` 与 closed typed details；包根导出同一 symbols。 |
| reservation、mailbox、唯一 in-flight、overflow、detach、readiness | `dayu.host.transient_delta` | per-Session reservation cap；单 subscription item-bound mailbox；`retained_items = mailbox + in_flight`；prospective check；overflow 先移出 fanout并保留 accepted prefix；幂等 release。 |
| async activation 与 Host lifecycle | `dayu.host.open_host` | public lifecycle check -> reservation -> durable cursor transaction -> owner-loop recheck/attach/iterator allocation -> return；失败、取消、Host close和构造失败释放 reservation；producer owner 停止后关闭 delivery hub。 |
| runtime config schema | `dayu.runtime.config_loader` | required strict `session_event_delivery_policy`；missing/extra/bool/zero/negative/float/string fail closed；runtime 包保持层中立。 |
| packaged defaults | `dayu/config/host_runtime.json` | 精确 `transient_mailbox_max_items=512`、`max_subscriptions_per_session=4`；没有 byte/heap 字段。 |
| Host policy assembly | `dayu.service.host_assembly` | config typed view 一对一构造 Host public policy；没有 scene/run/UI override 或 fallback。 |
| Service public iterator consumption | `dayu.service.entrypoint_runtime` | 只机械传播 async factory/public iterator：移除 Service 私有 closable protocol与 cast，attach/runtime factory显式 async/await；原 relay queue/drain/task/control flow保持不变。 |

## 实际修改文件

除本 artifact 外，implementation-owned diff 共 52 个文件。Controller-owned `docs/host/issues-implementation-control.md` 在开始前已有未提交 bookkeeping diff，本轮没有修改、格式化、stage 或清理该文件。

### Production、config 与 assembly

- `dayu/host/api.py`
- `dayu/host/__init__.py`
- `dayu/host/transient_delta.py`
- `dayu/host/open_host.py`
- `dayu/runtime/config_loader.py`
- `dayu/config/host_runtime.json`
- `dayu/service/host_assembly.py`
- `dayu/service/entrypoint_runtime.py`

### README

- `dayu/host/README.md`
- `dayu/config/README.md`
- `dayu/README.md`
- `tests/README.md`

### Host tests与fixtures

- `tests/host/public_smoke_support.py`
- `tests/host/recovery_support.py`
- `tests/host/test_effective_execution_config.py`
- `tests/host/test_host_activity_event_projection.py`
- `tests/host/test_host_production_stress.py`
- `tests/host/test_open_host_runtime.py`
- `tests/host/test_package_exports.py`
- `tests/host/test_per_run_tool_selection.py`
- `tests/host/test_public_cancel_smoke.py`
- `tests/host/test_public_compact_smoke.py`
- `tests/host/test_public_contracts.py`
- `tests/host/test_public_lifecycle_smoke.py`
- `tests/host/test_public_offline_outbox_smoke.py`
- `tests/host/test_public_open_host_multiturn_smoke.py`
- `tests/host/test_public_open_host_options.py`
- `tests/host/test_public_real_runner_matrix_smoke.py`
- `tests/host/test_public_retry_replay.py`
- `tests/host/test_public_session_api.py`
- `tests/host/test_public_tool_wiring_smoke.py`
- `tests/host/test_purge_session.py`
- `tests/host/test_recovery_multiprocess.py`
- `tests/host/test_storage_maintenance.py`
- `tests/host/test_storage_usage_report.py`
- `tests/host/test_submit_followup_public_contract.py`
- `tests/host/test_transient_delta.py`
- `tests/host/test_transient_delta_stress.py`
- `tests/host/test_watch_session_events.py`

### Runtime、Service 与 CLI tests

- `tests/runtime/test_config_loader.py`
- `tests/service/test_entrypoint_runtime.py`
- `tests/service/test_entrypoint_runtime_prompt_path.py`
- `tests/service/test_entrypoint_runtime_interactive_path.py`
- `tests/service/test_host_admin.py`
- `tests/service/test_host_assembly.py`
- `tests/cli/test_prompt_command.py`
- `tests/cli/test_interactive_command.py`
- `tests/cli/test_transient_slow_consumer_path.py`

### Amendment 授权 utils

- `utils/smoke_host_public_r03_semantic_ownership.py`
- `utils/smoke_host_public_conversation_memory.py`
- `utils/smoke_host_public_conversation_memory_scenarios.py`
- `utils/smoke_host_public_multiturn.py`

4 个文件中的 5 个真实 direct callsites 只增加显式 `await`；smoke 场景、断言、数据流、helper 与其它行为均未改变。

## Stop / amendment 闭环

此前完整 pyright 的 18 个错误分为两类：4 个 utils 文件中 5 个遗漏 direct callsites 产生 10 个错误，已授权 Service/CLI fakes 的宽泛 `__aiter__ -> AsyncIterator[...]` 产生 8 个结构类型错误。Controller 将原 gate 返回 plan fix；原 reviewers re-review 与 Controller adjudication 接受 amendment 后，本轮按 `33af05fa` 恢复 S1。

闭环结果：

- 4 个 utils、5 个调用全部显式 `await`。
- 5 个 Service/CLI fake iterator 的 `__aiter__` 精确返回 public `HostSessionEventIterator`，相关未使用 `AsyncIterator` imports 已删除。
- 生产 Service 私有 closable Protocol 与对应 cast 已删除；未添加 `getattr`、兼容 coroutine识别、同步 factory、lazy attach或 compatibility shim。
- 完整 pyright 为 0 errors。

## S1 复核发现与修复

完整 affected suite 首轮发现 `tests/host/test_purge_session.py::test_public_purge_is_observed_by_independent_process_read_paths` 失败。旧测试在首次 `anext()` 捕获 missing Session；async activation 生效后，`NOT_FOUND` 在 `await host.watch_session_events(...)` 的 cursor transaction 边界抛出，而先前机械传播把 await 留在原 `try` 外。

修复位于测试 caller boundary：复用既有 `_host_api_error_code(...)` 直接 await public factory并断言同一 `HostApiError.code`。没有修改 production error mapping、断言目标、purge 数据流或兼容路径。该单测复跑通过，随后完整 affected suite 全量复跑通过。

## Tests 与 validation

所有命令均在 `source .venv/bin/activate` 后运行。

| 验证 | 结果 |
|---|---|
| S1 focused：plan §8.1 的 9 个 host/runtime/service 文件 | `317 passed` |
| Service/CLI mechanical propagation：3 个 Service entrypoint files、2 个 CLI command files、现有 slow-consumer integration | `142 passed` |
| purge caller regression 单测 | `1 passed` |
| affected suites：`tests/host tests/runtime tests/service tests/cli` | `3405 passed, 8 skipped, 6 deselected` |
| Host production stress | `5 passed` |
| transient delta stress | `1 passed` |
| 4 个 utils `py_compile` | exit `0` |
| 完整 `python -m pyright dayu/ tests/ utils/` | `0 errors, 0 warnings, 0 informations` |
| `git diff --check` | exit `0` |

pytest 仅报告既有 `edgar` 三条 deprecation warnings；pyright 仅报告工具版本提示，均不影响本 slice correctness。

## 单文件 coverage

| Production owner | Coverage | Gate |
|---|---:|---|
| `dayu.host.transient_delta` | `92.03%` | PASS |
| `dayu.host.open_host` | `83.59%` | PASS |
| `dayu.host.api` | `88%` | PASS |
| `dayu.runtime.config_loader` | `96%` | PASS |
| `dayu.service.entrypoint_runtime` | `87%` | PASS |
| `dayu.service.host_assembly` | `95%` | PASS |

全部修改的核心 production 文件均达到单文件 `>=80%` 目标；`dayu.host.__init__` 是符号导出面，`dayu/config/host_runtime.json` 是配置资产，4 个 utils 按 `AGENTS.md` 默认无 coverage 要求。

## Source propagation、stale 与 boundary scans

- Host old-256/availability scan：`_TRANSIENT_WATCH_BUFFER_CAPACITY`、`session_live_stream`、`reason_code="slow_consumer"` 及 byte-accounting词在 Host production/tests/README 中 0 命中。
- 全 owner-path stale scan：只有 `dayu/service/entrypoint_runtime.py` 的 `_ENTRYPOINT_LIVE_EVENT_BUFFER_CAPACITY=256` 定义与 queue allocation 共 2 个预期命中；这是 S1 明确冻结、由 S4 删除的现有 Service relay，不是 Host delivery 残留。
- watch source scan：4 个 utils 的 5 个 direct assignments均显式 await；全仓没有未 await 的 direct assignment/return。测试中仍以 `asyncio.create_task(factory_coroutine)` 构造并随后 await/cancel的 4 个 race call，以及传给 `_host_api_error_code` 后由 helper await 的 1 个 error call，均是显式 coroutine lifecycle consumer，不是同步兼容路径。
- fake contract scan：Service/CLI fake factories均为 async并返回 public iterator；`__aiter__` 不再返回宽泛 `AsyncIterator[...]`。
- runtime boundary scan：`dayu/runtime` 没有实际 `dayu.engine/host/service/ui/fins` import。
- Engine boundary scan：`dayu/engine` 没有 `TerminalPostCommit` 或 `session_event_delivery` contract。
- compatibility scan：production S1 路径没有 private closable protocol、pending cursor future、cursor done callback、lazy attach、batch `drain_nowait`、`getattr` 或 coroutine compatibility branch。
- config/assembly source propagation由 required constructor字段、strict parser tests、packaged exact `512/4` 与完整 pyright共同闭合。

## README trigger audit

修改前完整读取了 `README.md`、`dayu/README.md` 与 `dayu/host/README.md` 各自的 `Agent更新约束【必须遵守】`；`dayu/config/README.md`、`dayu/service/README.md` 与 `tests/README.md` 没有独立同名约束，按仓库 `AGENTS.md` trigger和现有文档职责审计。

| README | 决定 |
|---|---|
| `dayu/host/README.md` | 更新 public async activation、iterator/policy/errors、item-bound mailbox/in-flight、per-Session cap、512/4、无 byte/heap 承诺和 close release顺序。 |
| `dayu/config/README.md` | 更新 required strict policy block、字段语义与 packaged `512/4`。 |
| `dayu/README.md` | 更新 Host delivery owner、Service await attach 与 public iterator跨层边界；明确保留“现有有界 relay”，未宣称 S4 完成。 |
| `tests/README.md` | 更新当前 S1 owner/race/error/coverage测试语义；保留现有 Service relay并明确删除不在本阶段。 |
| `dayu/service/README.md` | 审计后不修改；现有容量 256 relay和 fallback描述在 S1 仍真实，最终 sole-consumer/exact-five只属于 S4。 |
| 根 `README.md` | 不修改；CLI参数、用户配置步骤、最终输出、工作流和排障方式均未变化。 |
| `dayu/engine/README.md` | 不修改；Engine contract未变化。 |

## Scope audit

- 未进入 S2 causal fence / reconciliation。
- 未进入 S3 terminal port / coordinator。
- 未进入 S4 Service relay删除、exact-five、UI executor或测试文件替换。
- 未修改 plan、既有 review/adjudication artifacts、`docs/phaseflow-umbrella-optimization-control.md`。
- Controller-owned `docs/host/issues-implementation-control.md` 保持进入本轮时的同一未提交 bookkeeping diff。
- 未 stage、commit、push或创建 PR。

## Remaining risks 与 stop conditions

### Covered by later approved slices

- S2：same-validation-transaction causal fence、bounded durable reconciliation和跨 opener correctness。
- S3：transaction-local exact terminal fact、local terminal post-commit port/coordinator与promotion barrier。
- S4：删除当前 Service relay、exact-five sole consumer/generation/cleanup、delivery-only recovery和 CLI/UI 专用 callback executor。

这些是 accepted 4-slice dependency graph 中已有 owner/destination，不是 S1 缺陷，也没有在本 slice 提前实现或描述为已完成。

### Existing physical guarantee boundary

- 任意第三方 callback 无限阻塞仍不具备物理终止保证；该边界沿用 accepted plan，不由 S1 引入或扩大。

未发现需要新 issue、用户裁决或越出 updated S1 allowed scope 的 residual risk。Blocking stop conditions：`None`。

## Completion status

`implementation-slice-1: PASS`

当前可进入 Slice 1 code review gate；按用户指令，本轮停在 implementation artifact，不 stage、commit、push或进入 S2-S4。
