# P1-P7 Design Goals Fix Review — AgentDS — 2026-05-16

## Gate

- Gate: fix review
- Reviewer: AgentDS
- Controller Decision: `docs/reviews/p1-p7-design-goals-controller-decision-20260516.md`
- Codex Fix Artifact: `docs/reviews/p1-p7-design-goals-fix-codex-20260516.md`
- Branch: `fix/host-p1-p7-awaiting-production-wiring`
- Design Source: `docs/host/design.md`

## Review Scope

审查当前未提交 diff，对照 controller decision D2–D6 逐项验证，并检查公共 API 破坏、反向依赖、`dayu.runtime` 污染、弱类型与测试伪覆盖。

## Verification Results

### Pyright

```
0 errors, 0 warnings, 0 informations
```

### Tests

- Affected file tests: `tests/host/test_resolve_wait_command.py tests/host/test_active_cancel_dispatch.py tests/host/test_command_handle.py tests/host/test_dispatch_scheduler.py tests/host/test_phase5_local_execution_integration.py` — 45 passed
- Full host suite: `tests/host -q` — 394 passed

### Residual Symbol Check

- `DEFAULT_ACTIVE_WORKER_REGISTRY`: 源代码中零引用；仅在历史 review artifact 中出现。`dayu/host/dispatch.py` 已删除该模块级单例及对应 `__all__` 导出。
- `cancel_active_worker()`: 同上，源代码中零引用。
- `TOOL_TERMINAL_RESULT` / `FOLLOWUP_QUEUED`: 源代码中零引用；`docs/host/design.md` 中仅保留否定性说明（解释为何不引入独立 canonical event）。

---

## Verdict: PASS

All D2–D6 decisions are correctly implemented. No blocking or high findings.

---

## Findings

### DS-P1P7-M1 [Medium] — `implementation-control.md` 残留已解决的 risk tracking 条目

- **证据**: `docs/host/implementation-control.md:1651` 与 `:2041` 仍列出 `DEFAULT_ACTIVE_WORKER_REGISTRY` module-level singleton 的多 handle cancel 边界风险，标记为 "Host dispatch lifecycle hardening"。
- **影响**: 该 risk 已通过 D2 fix 解决（模块级单例已删除，改为显式注入），但 control doc 未同步更新。后续 phase 可能基于过期风险条目做错误决策。
- **建议**: 将 implementation-control.md 中该 risk 条目标记为 resolved/closed，引用本次 fix commit 作为关闭证据。
- **注意**: 这属于 control document 维护问题，不影响代码正确性。

### DS-P1P7-L1 [Low] — `ActiveWorkerRegistry` 未从 `dayu.host` 顶层包 re-export

- **证据**: `dayu/host/__init__.py` 未导入 `ActiveWorkerRegistry`；该类型仅从 `dayu.host.dispatch` 导出。`create_host_command_handle(options, active_registry=None)` 的签名中包含该类型，但 composition root 作者需额外 `from dayu.host.dispatch import ActiveWorkerRegistry`。
- **影响**: 轻微 discoverability 问题。不影响类型检查（pyright 正常）。
- **建议**: 可考虑从 `dayu.host` re-export `ActiveWorkerRegistry` 以降低 composition root 装配的学习成本。非强制。

### DS-P1P7-L2 [Low] — `_propagate_active_cancel_targets` 直接访问 `host._active_registry` 私有属性

- **证据**: `dayu/host/command.py:853` — `host._active_registry.cancel(target)`，其中 `_active_registry` 按命名约定为 `HostCommandHandle` 的私有属性。该访问发生在同模块的模块级辅助函数中。
- **影响**: 当前无功能影响（同模块访问 Python 允许）。若未来 `HostCommandHandle` 的 active registry 访问逻辑需要变更（例如添加 audit 日志），调用方散落在模块级函数中会增加重构成本。
- **建议**: 可考虑将 active cancel propagation 封装为 `HostCommandHandle` 的方法（如 `_propagate_active_cancel`），或暴露只读 property `active_registry`。

### DS-P1P7-L3 [Low] — `_wait_late_rejection_digest` 仍包含 `observed_at` / `source`，与 D3 口径存在张力

- **证据**: `dayu/host/waiting.py:1102-1131` — `_wait_late_rejection_digest()` 的 digest 包含 `source`、`observed_at`、`wait_status`、`rejection_reason` 等字段。这意味着同一 late result 在不同时间重放会触发 `IDEMPOTENCY_CONFLICT` 而非幂等重放。
- **影响**: late rejection scope（`_WAIT_LATE_REJECTION_SCOPE_KIND`）与 resolution scope（`_WAIT_RESOLUTION_SCOPE_KIND`）行为不一致。对于 diagnostic 事件，包含 `observed_at` 可被理解为保守策略（每次晚到提交都被视为独立事实），但缺少明确设计说明。
- **建议**: 在 `docs/host/design.md` 中明确 late rejection idempotency 的口径（保守 vs outcome-based），或统一为与 D3 一致的 outcome-based 策略。非本轮强制修改。

### DS-P1P7-I1 [Info] — design.md 的 `TOOL_RESULT_ACCEPTED` 表格行可进一步细化 wait-specific field 列表

- **证据**: `docs/host/design.md:1357` — `TOOL_RESULT_ACCEPTED` 的必需 payload 列写为 "result ref / digest / evidence anchors / status；wait terminal result 通过 wait-specific fields 表达来源与状态"，未列出具体区分字段（如 `wait_id`、`resolution_kind`、`resolution_source`）。
- **影响**: 不影响设计目标的达成。当前表述已足够理解设计意图，但缺少可被工具链消费的字段级契约。
- **建议**: 可延后在 Phase 7 stable 时补充字段级说明。

### DS-P1P7-I2 [Info] — 测试辅助函数 `_open_scheduler` 参数风格在测试文件间不完全一致

- **证据**: 
  - `tests/host/test_active_cancel_dispatch.py:558-567` 的 `_open_scheduler` 将 `worker_factory`、`lane_timeout_seconds`、`active_registry` 全部设为 keyword-only。
  - `tests/host/test_phase5_local_execution_integration.py:1061-1067` 的 `_open_scheduler` 仅将 `active_registry` 设为 keyword-only。
  - `tests/host/test_dispatch_scheduler.py` 的 `_open_scheduler` 签名不同（自有约定）。
- **影响**: 测试代码内部不一致，不影响生产行为。
- **建议**: 后续可统一测试 helper 签名风格。

---

## Per-Decision Detailed Assessment

### D2 — active worker registry 注入

**Verdict: PASS**

- `DEFAULT_ACTIVE_WORKER_REGISTRY` 模块级单例已删除 (`dispatch.py:275-289` removed)。
- `cancel_active_worker()` public helper 已删除，对应 `__all__` 条目已移除 (`dispatch.py:1266-1271`)。
- `HostCommandHandle.__init__` 接收 `active_registry: ActiveWorkerRegistry` 必填参数 (`command.py:114-137`)。
- `create_host_command_handle(options, *, active_registry=None)` 默认值创建 fresh `ActiveWorkerRegistry()` (`command.py:232-240`)。
- `HostDispatchScheduler.__init__` 默认值从 `DEFAULT_ACTIVE_WORKER_REGISTRY` 改为 `ActiveWorkerRegistry()` (`dispatch.py:310-312`)。
- `_propagate_active_cancel_targets` 现在接收 `host: HostCommandHandle` 参数，通过 `host._active_registry.cancel(target)` 传播 (`command.py:841-853`)。
- `cancel_run` 和 `cancel_session_runs` 传递 `host` 给 `_propagate_active_cancel_targets` (`command.py:414,456`)。
- 测试覆盖：
  - `test_factory_default_active_registry_is_handle_local` — 两个默认 handle 不共享 registry。
  - `test_default_active_registry_is_scheduler_local` — 两个默认 scheduler 不共享 registry。
  - `test_cancel_run_active_worker_propagates_and_closes_cancelled` — 注入共享 registry 时 cancel 能传播到 scheduler 注册的 active worker。
  - `test_cancel_session_replay_repropagates_active_without_new_facts` — session cancel replay 通过共享 registry 重放。
- 设计 doc §10.1 已同步：command handle 持有 active worker cancel registry，默认值只能在 composition root 构造时创建 fresh registry (`design.md:710`)。

### D3 — resolve_wait 幂等 digest

**Verdict: PASS**

- `_wait_resolution_digest()` 只包含 `wait_id`、`idempotency_key` 与 typed outcome JSON (`waiting.py:1085-1098`)；`source` 和 `observed_at` 已移除。
- `source` / `observed_at` 仍保留在首次提交的 EventLog payload 中（`tool_result_wait_resolution_payload` 仍接收并写入这些字段，`waiting.py:1307-1367`）。
- 同 key + 同 outcome + 不同 `observed_at` 重放：返回首次结果，不创建新 Attempt，不追加新 EventLog，不追加新 `TOOL_RESULT_ACCEPTED`。
- 同 key + 不同 outcome：仍返回 `IDEMPOTENCY_CONFLICT`。
- 测试覆盖：`test_resolve_wait_same_key_same_outcome_replays_with_different_observed_at` 验证 `observed_at` 变化不影响幂等重放，且 `TOOL_RESULT_ACCEPTED` 事件不重复。
- README 已同步：幂等 digest 说明更新为 "只反映 wait id、幂等键与 outcome 身份" (`dayu/host/README.md:69`)。

### D4 — TOOL_TERMINAL_RESULT 设计口径

**Verdict: PASS**

- `docs/host/design.md` 中 canonical event type list 已移除 `TOOL_TERMINAL_RESULT` (`design.md:1327-1328`)。
- Canonical event contract matrix 表格行已从 `TOOL_RESULT_ACCEPTED / TOOL_TERMINAL_RESULT` 改为仅 `TOOL_RESULT_ACCEPTED`，并说明 wait terminal result 通过 wait-specific fields 表达 (`design.md:1357`)。
- EventLog 规则已更新：明确 P1-P7 accepted waiting terminal result 使用 `TOOL_RESULT_ACCEPTED` 作为唯一 accepted tool result canonical event (`design.md:1929`)。
- audit/Host event stream/RunInputBuilder/memory 可解释性：`TOOL_RESULT_ACCEPTED` 的 payload 中包含 `wait_id`、`resolution_source`、`resolution_kind`、`resolution_idempotency_key` 等 wait-specific 字段，下游消费者可通过这些字段区分普通工具结果与 wait terminal result。不削弱可解释性。
- 无代码变更（controller decision 明确要求 "修改 design，不修代码"）。

### D5 — FOLLOWUP_QUEUED 设计口径

**Verdict: PASS**

- `docs/host/design.md` 中 canonical event type list 已移除 `FOLLOWUP_QUEUED` (`design.md:1318-1319`)。
- Canonical event contract matrix 表格行已移除 `FOLLOWUP_QUEUED` (`design.md:1354`)。
- Control event `run_id` 绑定规则新增 `submit_followup(queue)` 的 canonical 表达说明：`USER_INPUT_ACCEPTED` + `RUN_ACCEPTED` + 按竞态结果 `RUN_QUEUED` 或 `RUN_STARTED` (`design.md:1369`)。
- 现有代码已按此模式工作：`submit_followup` 通过 `USER_INPUT_ACCEPTED` 记录输入，后续 `RUN_ACCEPTED` / `RUN_QUEUED` / `RUN_STARTED` 记录 Run admission facts。
- audit/Host event stream/RunInputBuilder/memory 可解释性：follow-up queue 的完整生命周期可通过 `USER_INPUT_ACCEPTED` → `RUN_ACCEPTED` → (`RUN_QUEUED` | `RUN_STARTED`) 事件链重建，不削弱可解释性。
- 无代码变更（controller decision 明确要求 "修改 design，不修代码"）。

### D6 — WAITING cancel docstring

**Verdict: PASS**

- `cancel_run` docstring 已从 "``WAITING`` 取消由 Phase 7 负责" 改为 "active worker 与 ``WAITING``" (`command.py:383-384`)。
- `cancel_session_runs` docstring 已从 "``WAITING``、``RECOVERING`` 分别由 Phase 7、Phase 11 负责" 改为 "active worker 与 ``WAITING``；``RECOVERING`` 取消由 Phase 11 负责" (`command.py:436-438`)。
- 实际行为未改变：`admission.py` 中 `_cancel_waiting()` 已在 Phase 7 实现，docstring 仅修正为反映当前实现状态。

---

## Cross-Cutting Checks

### Public API 破坏

- `create_host_command_handle(options)` → `create_host_command_handle(options, *, active_registry=None)` — 向后兼容（新增 keyword-only 可选参数）。
- `HostDispatchScheduler.open()` 签名未变（已有 `active_registry` 参数，仅默认行为从共享模块级单例改为创建 scheduler-local registry）。
- `DEFAULT_ACTIVE_WORKER_REGISTRY` 和 `cancel_active_worker()` 从 `dayu.host.dispatch.__all__` 移除 — 技术性破坏变更，但是 controller decision 明确要求的修复。
- `dayu.host` 顶层 `__all__` 未变 — 该包根从未导出 dispatch 内部符号。

### 反向依赖 / dayu.runtime 污染

- 无新增跨层 import。`dayu.host.dispatch` 对 `dayu.runtime.lane` 的依赖为已有依赖（Phase 5），未变更。
- 无 `dayu.engine`、`dayu.service`、`dayu.ui`、`dayu.fins` 进入 Host 层。

### Any / object / 弱类型

- 无新增 `Any`、`object`、无类型参数或裸容器类型。
- 新增类型 `ActiveWorkerRegistry` 全部字段与方法签名完整类型标注。

### 过度设计

- 无。`ActiveWorkerRegistry` 是最小化设计（register / unregister / cancel），无多余抽象层。
- `create_host_command_handle` 的 `active_registry` 参数是解决模块级单例问题的最小侵入方案。

### 测试伪覆盖

- 新增测试均验证具体行为（registry 隔离、cancel 传播、幂等重放不追加事件），非仅覆盖行号。
- `_events_by_type` helper 提供精确的 EventLog 类型级断言，提升测试质量。

---

## Recommendation

建议进入 controller final adjudication。所有 Blocking/High 级别问题已通过 Codex fix 解决，本轮 review 无新增 Blocking 或 High finding。

剩余 Medium/Low/Info 条目建议：
- DS-P1P7-M1（implementation-control.md 残留条目）：在 controller final adjudication 中决定是否同步关闭。
- DS-P1P7-L1/L2/L3：可在后续 phase 中渐进改善，不阻塞本分支合入。
