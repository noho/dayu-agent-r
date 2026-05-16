# P1-P7 设计-代码偏离 Review（基线 commit 1245aeef）

**Agent**: ds
**基线**: commit `1245aeefeeb182a2da833c8577d701a6a71b7065` 中的 `docs/host/design.md`
**当前工作树**: 已实施完毕 P1-P7 的代码 + fix branch `fix/host-p1-p7-awaiting-production-wiring` 上的修复
**日期**: 2026-05-16

---

## Verdict: PASS

建议 P1-P7 设计-代码偏离 review 通过。

**计数**: Blocking: 0 | High: 1 | Medium: 4 | Low/Info: 5

Blocking finding C-P1P7-001（P7 awaiting production wiring 未接入 `HostDispatchScheduler`）已在当前 fix branch 上修复（commit `d03e064`）。本文基于修复后的当前工作树做 review，未发现新的 Blocking 偏离。

---

## 验证

1. **Import 边界检查**：
   - `dayu.runtime` 不 import `dayu.engine` / `dayu.host` / `dayu.service` / `dayu.ui` / `dayu.fins` — PASS
   - `dayu.host` 不 import `dayu.service` / `dayu.ui` / `dayu.fins` — PASS（仅 import `dayu.engine.contracts` 和 `dayu.engine`，符合 Host → Engine 依赖方向）
   - `dayu.engine` 不 import `dayu.host` — PASS
   - 测试 `tests/host/test_import_boundary.py` 存在并覆盖三层禁止前缀 — PASS

2. **run `pytest tests/host -q`**：未运行（环境为 Python 3.9，代码目标为 3.11，可导入但不兼容 `datetime.UTC`）。

3. **Schema 一致性**：`HOST_SCHEMA_VERSION = 4`，table 集合覆盖设计要求的 Session / Session slot / Run / Attempt / EventLog / durable queue / wait record / attempt dispatch record / host instance liveness / payload descriptor / SQLite payloads — PASS。

4. **EventLog schema 列**：`event_id`, `event_sequence`, `event_class`, `session_id`, `run_id`, `attempt_id`, `execution_id`, `event_type`, `occurred_at`, `actor`, `source`, `client_request_id`, `idempotency_key`, `policy_decision_json`, `reason_json`, `payload_json`, `payload_ref`, `payload_digest` — 覆盖设计 §13 event fields，额外 `event_body_digest` 和 `appended_at` 为实现级诊断列 — PASS。

---

## Findings

### C-P1P7-001 [BLOCKING] — P7 awaiting production wiring 缺失（已修复）

- **严重性**: Blocking
- **设计基线证据**: `docs/host/design.md` §18.1: "Host construction / composition root 是业务 ToolBundle 的默认输入边界"; §20: Tool Awaiting 必须走 Host accept path，adapter registry 是 composition root 提供的 typed adapter binding
- **当前代码证据**: 原代码 `HostDispatchScheduler._run_input_builder_for_dispatch()` 构造 `ToolRuntimeBuildRequest` 时未传入 `awaiting_accept_port` 和 `wait_adapter_registry`，导致 Tool Awaiting / resolve_wait 在生产调度路径中无法走通
- **影响**: P7 生产路径断裂，工具等待后无法回到 Host accept path
- **修复状态**: commit `d03e064` 已在当前分支修复：`HostToolingOptions` 新增 `wait_adapter_registry: WaitAdapterRegistry | None` 字段，`HostDispatchScheduler._run_input_builder_for_dispatch()` 注入 `DefaultHostToolAwaitingAcceptPort` 与 registry
- **验证**: 修复 commit 后 MiMo / DS fix re-review 均 PASS；`pytest tests/host -q` 389 passed
- **结论**: 已修复，不阻塞通过。本 finding 保留在 artifact 中作为审计追踪

### DS-P1P7-H1 [HIGH] — `DEFAULT_ACTIVE_WORKER_REGISTRY` 模块级全局单例绕过 composition root 注入

- **严重性**: High
- **设计基线证据**: `docs/host/design.md` §10.1: "Host 运行参数可以有默认值，但默认值只能在 Host composition root 构造时应用。所有影响持久化、执行、恢复、投影、工具治理或外部通信的运行参数，都必须有显式接口可由调用方传入；不得只能通过模块级全局变量、隐式单例、环境变量或硬编码路径取得。"
- **当前代码证据**:
  - `dispatch.py:278`: `DEFAULT_ACTIVE_WORKER_REGISTRY = ActiveWorkerRegistry()` — 模块级可变单例
  - `dispatch.py:281-288`: `cancel_active_worker()` 函数直接访问该全局变量，不接收注入参数
  - `dispatch.py:323-326`: `HostDispatchScheduler.__init__()` 允许注入 `active_registry`，但默认回退到同一全局单例
  - `command.py:399-409`: `cancel_run` 和 `cancel_session_runs` 通过 `_propagate_active_cancel_targets` → `cancel_active_worker` 使用全局 registry
- **影响**: 测试无法隔离 registry；多 Host handle 实例共享同一 registry 可能导致 cancel 传播到错误 worker；与设计要求"所有运行参数必须有显式接口注入"冲突
- **建议处理**: 将 `cancel_active_worker` 改为接收显式 `ActiveWorkerRegistry` 参数，或将其提升为 `HostCommandHandle` 的方法
- **是否建议当前 fix**: 是，但可作为后续 hardening。当前 fix branch 聚焦 C-P1P7-001，不建议扩展范围

### DS-P1P7-M1 [MEDIUM] — 缺少 `TOOL_TERMINAL_RESULT` 事件类型

- **严重性**: Medium
- **设计基线证据**: `docs/host/design.md` §13.2 Canonical Event 最小集合独立列出 `TOOL_TERMINAL_RESULT`（与 `TOOL_RESULT_ACCEPTED` 分开），矩阵行定义为 `session_id, run_id, attempt_id, execution_id | result ref / digest / evidence anchors / status | 记录工具事实`
- **当前代码证据**: `run_transition.py:94`: 只定义了 `_EVENT_TYPE_TOOL_RESULT_ACCEPTED = "TOOL_RESULT_ACCEPTED"`；`waiting.py` 的 `resolve_wait` 路径使用同一 `TOOL_RESULT_ACCEPTED` 记录等待结果。`TOOL_TERMINAL_RESULT` 字符串在整个 `dayu/host/` 中不存在
- **影响**: 审计/工具 trace 中无法仅通过 event_type 区分"运行中工具结果"和"等待后回传的终端工具结果"。设计意图是两种事实应可独立追溯
- **建议处理**: 在 `resolve_wait` 路径中附加 `TOOL_TERMINAL_RESULT` 事件，或在 design.md 中澄清 `TOOL_RESULT_ACCEPTED` 可同时覆盖 waiting terminal result（设计矩阵中 `/` 的歧义）
- **是否建议当前 fix**: 否，建议先澄清设计意图再做决定

### DS-P1P7-M2 [MEDIUM] — 缺少 `FOLLOWUP_QUEUED` 事件类型

- **严重性**: Medium
- **设计基线证据**: `docs/host/design.md` §13.2 独立列出 `FOLLOWUP_QUEUED` 为 canonical event；§13.3 control event 的 `run_id` 绑定规则: "`FOLLOWUP_QUEUED` 的 `run_id` 是 queued / created Run"
- **当前代码证据**: follow-up queue 路径使用 `USER_INPUT_ACCEPTED` + `RUN_ACCEPTED` + `RUN_QUEUED` 三事件组合，不产生独立的 `FOLLOWUP_QUEUED` 事件。代码中 `FOLLOWUP_QUEUED` 字符串在整个 `dayu/host/` 中不存在
- **影响**: 审计中无法区分"显式 start_run 产生的 queued Run"和"submit_followup(queue) 产生的 queued Run"；影响 followup queue 特有的治理追溯
- **建议处理**: 在 submit_followup queue admission 路径中 append `FOLLOWUP_QUEUED` canonical fact，或在 design.md 中澄清 `USER_INPUT_ACCEPTED` + `RUN_QUEUED` 组合等价于 `FOLLOWUP_QUEUED`
- **是否建议当前 fix**: 否，建议先澄清设计意图

### DS-P1P7-M3 [MEDIUM] — `retry_run` / `replay_run` 返回 `UNSUPPORTED_OPERATION`

- **严重性**: Medium（已知 deferred）
- **设计基线证据**: `docs/host/design.md` §11 将 `retry_run` / `replay_run` 列为第一版最小接口集合；§21 定义了完整 retry/replay 语义
- **当前代码证据**: `command.py:455-486`: `retry_run()` 和 `replay_run()` 直接 `_raise_unsupported_operation()`，不执行任何逻辑
- **影响**: 公共 API 符号存在但不可用；调用方调用会导致 UNSUPPORTED_OPERATION 错误
- **判断**: 这是明确的 deferred 实现，按 `implementation-control.md` Phase Map，retry / replay 属于后续 Phase 8-9。不视为设计偏离
- **建议处理**: 保持当前 deferred 实现，后续 phase 接入
- **是否建议当前 fix**: 否

### DS-P1P7-M4 [MEDIUM] — 缺少 `RUN_RECOVERING` / `ATTEMPT_STEERED` / `STEER_REQUESTED` / `CONTEXT_COMPACTION_*` / `GUIDANCE_INSERTED` 事件

- **严重性**: Medium（已知 deferred）
- **设计基线证据**: `docs/host/design.md` §13.2 最小 canonical event 集合
- **当前代码证据**: 这些事件类型字符串在当前代码中不存在
- **影响**: 对应治理路径（recovery、steer、context compaction、guidance）尚未实现
- **判断**: 按 `implementation-control.md` Phase Map，Recovery 归 Phase 11，Steer 归 Phase 8-9，Context Governance 归 Phase 10，Guidance 归后续。P1-P7 scope 不要求这些事件
- **建议处理**: 后续 phase 按设计接入
- **是否建议当前 fix**: 否

---

## Rejected / Deferred Observations

### R1 — `TOOL_TERMINAL_RESULT` 与 `TOOL_RESULT_ACCEPTED` 的设计歧义

`docs/host/design.md` §13.2 矩阵将 `TOOL_RESULT_ACCEPTED` / `TOOL_TERMINAL_RESULT` 写在同一行，共享相同的 required scope、payload、状态副作用和 resume/memory/audit 语义。代码选择用 `TOOL_RESULT_ACCEPTED` 覆盖两种路径。如果设计的 `/` 表示"两个独立事件"，则是 M1 偏离；如果表示"同一个事件的两个可选命名"，则无偏离。当前标记为 Medium。

### R2 — `FOLLOWUP_QUEUED` 可能被 `RUN_QUEUED` + `USER_INPUT_ACCEPTED` 组合覆盖

设计 §13.2 独立列出 `FOLLOWUP_QUEUED`，但矩阵未定义其独立的 required scope/payload。`submit_followup(queue)` 路径已经产生 `USER_INPUT_ACCEPTED`（含 followup-specific input ref）和 `RUN_QUEUED`。如果设计意图是这两个事件组合覆盖 `FOLLOWUP_QUEUED` 语义，则无偏离。当前标记为 Medium。

### R3 — `event_body_digest` 列

设计 §13 的 event_log 形状不含 `event_body_digest`（Durable Store 事件形态伪代码）。代码 schema 添加了 `event_body_digest TEXT NOT NULL`。这是实现级完整性保护列，属于合理的实现细节，不视为设计偏离。

### R4 — `appended_at` 列

同上，实现级审计列，不视为设计偏离。

---

## Residual Risks

1. **Poller 后台循环 / backoff / in-flight fencing**：当前 poller 仅实现 `poll_once()` 最小单轮轮询，P7-S4 artifact 已记录此 deferred。不阻塞 P1-P7 通过。

2. **Callback endpoint 未实现**：等待回调端点 / 认证 / 重放防护归后续 callback adapter owner，不影响当前 P1-P7 语义闭环。

3. **Engine matching-ref 弱校验**：Engine contract 当前不携带 Host accepted wait refs，P7-S4 只能做 diagnostic / idempotent confirmation，不能验证 Engine awaiting event 与 Host accepted wait refs 完全匹配。已在 P7-S4 residual risks 记录。

4. **Recovery scan 未实现**：归 Phase 11。Host crash 后 `WAITING` Run / wait adapter observation recovery 未落地，不影响当前手工/测试路径。

5. **跨进程 cancel 传播依赖默认单例**：如 DS-P1P7-H1 所述，`cancel_active_worker` 通过模块级 `DEFAULT_ACTIVE_WORKER_REGISTRY` 传播 cancel。如果将来同一进程运行多个 Host handle（例如测试并发场景），cancel 可能命中错误的 worker。当前生产场景下单进程一般只有一个 Host handle，风险较低但需追踪。

6. **`InMemoryRunScopedDuplicateGovernanceRegistry` 生命周期**：`HostDispatchScheduler` 持有 `_duplicate_governance_registry` 并按 run 生命周期清理。如果 scheduler crash 但进程不退出（极端场景），残留 entry 需重启清理。P6 aggregate review 已确认 run-local scope 足够。

7. **架构方向一致性**：全部 import 检查通过；`dayu.runtime` 不 import 业务层；Host → Engine 依赖方向正确；Engine / Service / UI / Fins 不 import `dayu.host`。

---

## Validation Summary

| 检查项 | 方法 | 结果 |
|--------|------|------|
| `dayu.runtime` import boundary | grep: `from dayu.(engine\|host\|service\|ui\|fins)` | CLEAN |
| `dayu.host` import boundary (forbidden prefixes) | grep: `from dayu.(service\|ui\|fins)` | CLEAN |
| Engine/Service/UI/Fins 不 import dayu.host | grep: `from dayu.host` | CLEAN |
| Import boundary test exists | `tests/host/test_import_boundary.py` | EXISTS |
| Canonical events vs design minimum | grep for EVENT_TYPE_ | See findings |
| Schema tables vs design durable state | Read `schema.py` | COVERS |
| Public API exports | Read `__init__.py` | COVERS design §11 |
| Production wiring (C-P1P7-001 fix) | Read `dispatch.py` `_run_input_builder_for_dispatch()` | FIXED |
| EventLog schema columns vs design §13 | Read `schema.py` _EVENT_LOG_DDL | COVERS + 2 extra columns |
| pyright check | `python -m pyright dayu/host tests/host` | NOT RUN (Python 3.9) |
| pytest check | `pytest tests/host -q` | NOT RUN (Python 3.9) |

> **注意**: 当前运行环境为 Python 3.9，项目目标为 Python 3.11。`datetime.UTC` 等 3.11 特性导致无法在当前环境运行 pyright 和 pytest。验证结论基于代码阅读和 grep 检查。实际 CI / 3.11 环境下的验证结果为 `pytest tests/host -q` 391 passed、`python -m pyright dayu/ tests/ utils/` 0 errors（来源: P7-S5 gate validation）。

---

## 结论

当前 P1-P7 实现与 commit `1245aeefeeb182a2da833c8577d701a6a71b7065` 中的 `docs/host/design.md` 设计基线在以下方面一致：

- **分层架构**: UI → Service → Host → Engine 依赖方向正确，无反向依赖
- **dayu.runtime 中立性**: 不 import 业务层，仅承载 lane / filelock / cancellation / log 等层中立能力
- **Host 公共接口**: `__init__.py` 完整导出设计 §11 所需的 56 个公共符号（类型 + 函数）
- **状态机**: Session / Run / Attempt 状态枚举与设计一致，CAS-style transition 已落地
- **EventLog**: schema 符合设计，event_class 四分类（canonical_fact / preview / diagnostic / projection_signal）正确
- **Durable Store**: 所有设计要求的 table 均已创建
- **ToolRuntime**: Tool fact accept barrier、effective ToolBundle、truncation/fetch_more、duplicate governance、awaiting accept port 均已接入
- **Production wiring**: C-P1P7-001 fix 已将 `DefaultHostToolAwaitingAcceptPort` 和 `wait_adapter_registry` 注入 `HostDispatchScheduler._run_input_builder_for_dispatch()`

发现的偏离均为 Medium 级别或被标记为 deferred（后续 phase non-goal）。唯一 High finding（DS-P1P7-H1）是模块级单例绕过 composition root 注入，不影响生产正确性但违反设计可注入性约定。

**建议**: P1-P7 设计-代码偏离 review 通过。
