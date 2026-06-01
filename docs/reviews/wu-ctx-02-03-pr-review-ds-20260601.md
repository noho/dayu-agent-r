# WU-CTX-02 + WU-CTX-03 PR Review — AgentDS

## 结论

**Accepted**。无 blocking findings。PR 自洽、设计对齐、测试完备、type-safe，可保持 draft-PR-pass。

## 审查范围与证据

- PR：#105（https://github.com/noho/dayu-agent-r/pull/105）
- 分支：`feat/host-ctx-compact-failure-overflow` → `main`
- Diff：63 文件，+6092/-108 行（含 52 个 docs/reviews gate artifact 文件）
- 设计真源：`docs/host/design.md` 第 1 节、第 25 节
- 计划真源：`docs/host/wu-ctx-02-03-compact-failure-overflow-plan.md`
- 总控文档：`docs/host/host-core-followup-implementation-control.md`
- 前置 aggregate review：`docs/reviews/wu-ctx-02-03-aggregate-controller-adjudication-20260601.md`

## 验证命令

```bash
source .venv/bin/activate
pytest tests/host/test_context_policy.py tests/runtime/test_config_loader.py \
  tests/runtime/test_scene_assets_migration.py tests/service/test_host_assembly.py \
  tests/host/test_context_compact_events.py tests/host/test_run_input_builder.py \
  tests/host/test_engine_ingest_mapping.py tests/host/test_dispatch_scheduler.py -q
# → 249 passed

python -m pyright dayu/ tests/ utils/
# → 0 errors, 0 warnings, 0 informations
```

## Findings

### F-PR-1 — INFO / 非阻塞

**文件**: `dayu/host/context_events.py:196`, `dayu/host/dispatch.py:231`, `dayu/host/engine_ingest.py:230`

**问题**: `_FALLBACK_ACTION_NOT_APPLICABLE = "not_applicable"` 在三个模块各自定义为私有常量，值相同。

**影响**: 三处值一致，当前无 correctness 风险。已在 aggregate review 中作为 RR-CTX-SLICED-01 由 controller 裁决为 `deferred-with-owner`，owner 为 WU-LAYER-02 shared helper consolidation。

**建议**: 不在当前 WU 处理。后续 WU-LAYER-02 收敛 fallback action 枚举值。

**阻塞 draft-PR-pass**: 否。

---

### F-PR-2 — INFO / 非阻塞

**文件**: `dayu/host/dispatch.py:989-1012`

**问题**: `hard_threshold_before_dispatch` 路径写入 `CONTEXT_COMPACTION_FAILED` 但无前置 `CONTEXT_COMPACTION_REQUESTED`。当前使用合成 `operation_id`（`precondition:hard_threshold_before_dispatch:<digest>`）区分该场景。

**影响**: EventLog 序列缺少 `CONTEXT_COMPACTION_REQUESTED`。该路径本质是 pre-dispatch budget estimate 直接拒绝，不是 compaction operation 失败。当前通过 `failure_reason` 和 `attempt_count=0` 明确表达语义。已在 aggregate review 中作为 AGG-F2 由 controller 裁决为 `Accepted as intentional behavior / no fix`。

**建议**: 当前行为符合 plan。若未来设计真源引入 `failed 必须引用 requested` 的 EventLog invariant，再单独调整。

**阻塞 draft-PR-pass**: 否。

---

### F-PR-3 — INFO / 非阻塞

**文件**: `dayu/host/context_fallback.py:38-42`, `dayu/host/dispatch.py:1688-1789`, `dayu/host/engine_ingest.py:3231-3266`

**问题**: `RecentWindowFallbackAction` 枚举在 `context_fallback.py` 中定义为 `StrEnum`，但 `dispatch.py` 中 `_append_compaction_failed_with_proactive_fallback` 的 `fallback_action` 局部变量和 `engine_ingest.py` 中 `_ReactiveFallbackDecision.action` 均使用 `str` 类型，不直接引用该枚举。

**影响**: `RecentWindowFallbackAction` 枚举当前只在 `build_selection_failure_budget_payload` 中使用一次（`RecentWindowFallbackAction.FAIL_CLOSED.value`）。其它调用点绕过枚举直接用字符串常量 `FALLBACK_ACTION_DISPATCH` / `FALLBACK_ACTION_FAIL_CLOSED`。语义一致，不会导致漂移，但枚举未被充分使用。

**建议**: 不阻塞当前 PR。后续 WU-LAYER-02 或 fallback action 常量收敛时，可考虑将枚举作为 fallback action 的单一真源，替换模块级字符串常量。

**阻塞 draft-PR-pass**: 否。

---

### F-PR-4 — VERIFIED / 生产变更自洽性

逐项检查 5 个 Slice 是否在最终 diff 中完整落地：

| 计划要求 | 生产代码 | 验证 |
|---|---|---|
| Slice A: 默认 attempts 对齐 5 | `context_policy.py:22` → `DEFAULT_MAX_COMPACTION_ATTEMPTS_PER_OPERATION = 5` | ✓ |
| Slice A: packaged profiles 对齐 5 | `execution_profiles.json` 全部 4 个 profile | ✓ |
| Slice A: scene/model 对齐 flash-tier | `conversation_compaction.json` → `deepseek-v4-flash` | ✓ |
| Slice A: test assertions 对齐 | `test_context_policy.py`, `test_config_loader.py`, `test_scene_assets_migration.py`, `test_host_assembly.py` | ✓ |
| Slice B: failed payload 诊断字段 | `context_events.py` 新增 5 个字段，含 fallback 一致性校验 | ✓ |
| Slice B: builder/validator 调用点更新 | `dispatch.py`/`engine_ingest.py` 全部 append 点传齐字段 | ✓ |
| Slice C: context_fallback.py 新增 | 完整 selection / digest / estimate / budget / provider 实现 | ✓ |
| Slice C: RunInputBuilder fallback 集成 | `run_input.py` 新增 `ContextFallbackProvider` protocol + rendering | ✓ |
| Slice C: proactive fallback dispatch | `dispatch.py` → `_append_compaction_failed_with_proactive_fallback` | ✓ |
| Slice D: reactive fallback recovery | `engine_ingest.py` → `_reactive_fallback_decision` + `_ReactiveRecoveryAccepted` None 支持 | ✓ |
| Slice D: compacted_event None → skip memory | `_complete_reactive_recovery` 条件跳过 memory projection catchup | ✓ |
| Slice E: continuous overflow E2E | `test_dispatch_scheduler.py` → `_RepeatedReactiveOverflowWorkerFactory` | ✓ |
| Slice E: README sync | `dayu/host/README.md` 描述 fallback 语义；`tests/README.md` 记录 fallback 覆盖 | ✓ |

变更自洽，无遗漏。

**阻塞 draft-PR-pass**: 否。

---

### F-PR-5 — VERIFIED / 状态机合规性

逐一核对 plan 规定的 5 条状态转换与代码实现：

| 路径 | Plan 规定 | 代码实现 | 合规 |
|---|---|---|---|
| Proactive fallback dispatch | `ACCEPTED/QUEUED -> FAILED(fallback=dispatch) -> STARTED(start_reason=initial)` | `dispatch.py:1694-1697` → `_start_governed_in_transaction(transaction, run)` | ✓ |
| Proactive fallback fail closed | `-> FAILED(fallback=fail_closed) -> RUN_FAILED` | `dispatch.py:1629-1692` → fallback_action != dispatch → return None；`_fail_unstarted_in_transaction` 写入 RUN_FAILED | ✓ |
| Reactive fallback dispatch | `RUNNING -> ATTEMPT_FAILED -> RECOVERING -> FAILED(fallback=dispatch) -> STARTED(recovery) -> ATTEMPT_STARTED` | `engine_ingest.py:1603-1628` → `_ReactiveRecoveryAccepted(compacted_event_id=None)` | ✓ |
| Reactive fallback fail closed | `-> FAILED(fallback=fail_closed) -> RUN_FAILED` | `engine_ingest.py:1629-1640` → `_fail_recovering_run` | ✓ |
| Continuous overflow limit | `max_reactive_compactions_per_run` 上限后 `RUN_FAILED`，不写 `RUN_LOST` | `test_dispatch_scheduler.py:4004-4040` → 断言 Attempt 数=1+policy.max_reactive，不写 LOST | ✓ |

全部合规。key invariants 验证通过：
- fallback 不写 `CONTEXT_COMPACTED`
- fallback 不写 compact artifact
- fallback 不投影 memory stable facts
- reactive compact failure 不进入 `RUN_LOST`
- proactive failure 不进入 `RECOVERING`

**阻塞 draft-PR-pass**: 否。

---

### F-PR-6 — VERIFIED / AGENTS.md 合规性

对变更的生产文件逐项检查：

| 检查项 | 结果 |
|---|---|
| 中文 docstring（函数/类/模块） | ✓ 全部生产文件均有完整中文 docstring，含参数、返回值、异常 |
| 禁止 `Any` / `object` | ✓ 变更代码无 `Any`/`object` 类型签名；`context_fallback.py` 中 "object" 只出现在 docstring 描述文本中 |
| 禁止 `hasattr` / `getattr` 滥用 | ✓ 变更代码无使用 |
| 禁止魔法数字 | ✓ fallback 常量全部命名（`FALLBACK_ACTION_DISPATCH` 等）；`_NO_EVENT_SEQUENCE = -1` 等内部哨兵也命名 |
| 禁止 `extra payload` 传参 | ✓ 所有参数通过 typed dataclass（`RecentWindowFallbackSelection`、`ActiveRecentWindowFallback` 等）传递 |
| 禁止兼容性 re-export / wrapper | ✓ 无兼容性代码 |
| `dayu.runtime` import 边界 | ✓ 变更代码无 `import dayu.runtime` |
| `dayu.fins.storage` 约束 | ✓ 变更代码无财报文档存取操作 |
| 分层边界 | ✓ ContextFallbackProvider 在 `run_input.py` 中定义为 Protocol，`EventLogContextFallbackProvider` 在 `context_fallback.py` 中实现，通过 `scheduler._build_run_input_builder` 装配；Engine 不感知 |
| 测试覆盖 README 同步 | ✓ `dayu/host/README.md` 和 `tests/README.md` 已更新（见 F-PR-4） |

**阻塞 draft-PR-pass**: 否。

---

### F-PR-7 — VERIFIED / 测试覆盖矩阵

对照 plan 第 8 节验证命令，全部测试通过：

```bash
# Slice A 测试
pytest tests/host/test_context_policy.py tests/runtime/test_config_loader.py \
  tests/runtime/test_scene_assets_migration.py tests/service/test_host_assembly.py -q
# → passed

# Slice B 测试
pytest tests/host/test_context_compact_events.py tests/host/test_run_input_builder.py -q
# → passed (含 fallback selection / estimate / rendering 测试)

# Slice C 测试
#   test_run_input_builder.py 已在上步覆盖

# Slice D 测试
pytest tests/host/test_engine_ingest_mapping.py -q
# → passed

# Slice E 测试
pytest tests/host/test_dispatch_scheduler.py -q
# → passed
```

测试质量评估：
- 无 brittle sleep/race（使用 `asyncio.Condition` 确定性同步 + `asyncio.wait_for` 超时保护）
- 断言对象是 durable EventLog / Run 状态 / Attempt 计数 / EventLog 序列
- `_context_compaction_assertions.py` 封装共享断言，减少重复
- `_RepeatedReactiveOverflowWorkerFactory` 确定性构造连续 overflow 场景

未覆盖的合理场景（已在 aggregate review 确认不纳入当前 WU）：
- `context_budget_policy_missing` / `input_event_missing` reactive precondition 的集成 E2E（需破坏 durable invariant 构造脆弱测试）
- `hard_threshold_before_dispatch` + fallback dispatch 的独立测试（间接覆盖于 `test_pre_start_governance_compact_failure_is_attempt_free`）

**阻塞 draft-PR-pass**: 否。

---

### F-PR-8 — VERIFIED / EventLog payload schema

`CONTEXT_COMPACTION_FAILED` payload 完整字段矩阵：

| 字段 | Plan 要求 | 实现 | 校验 |
|---|---|---|---|
| `operation_id` | required | `context_events.py:453` — required text | `_required_text` |
| `failure_reason` | required | existed + preserved | `_required_text` |
| `policy_decision` | required | existed + preserved | `_required_text` |
| `retryable` | required | existed + preserved | `_required_bool` |
| `attempt_count` | required | 新增 — non-negative int | `_required_non_negative_int` |
| `retry_repair_budget_exhausted` | required | 新增 — bool | `_required_bool` |
| `diagnostic_refs` | required | existed + preserved | `_required_text_list` |
| `budget_after_attempted_compact` | optional | existed + preserved | `_optional_non_negative_int` |
| `fallback_policy_decision` | optional | 新增 — nullable text | conditional |
| `fallback_input_window` | optional | 新增 — nullable object | conditional |
| `fallback_input_digest` | optional | 新增 — nullable text | conditional |
| `fallback_budget_result` | optional | 新增 — nullable object | conditional |
| `fallback_action` | required | 新增 — `dispatch`/`fail_closed`/`not_applicable` | enum check |

一致性校验 `_validate_failed_fallback_fields`：
- `fallback_action=not_applicable` → 4 个 fallback 诊断字段必须全部为 null ✓
- 其它 action → 4 个 fallback 诊断字段必须全部 non-null ✓

**阻塞 draft-PR-pass**: 否。

---

### F-PR-9 — VERIFIED / residual risks 追踪

| ID | 状态 | 裁决 |
|---|---|---|
| RR-CTX-SLICEB-01 | closed | aggregate review 已验证 precondition failure 路径由 `_fail_reactive_recovery_without_request` 收口 |
| RR-CTX-SLICED-01 | deferred-with-owner (WU-LAYER-02) | `not_applicable` 常量三地重复，值一致，不影响 correctness |
| RR-CTX-PLAN-01 | closed | fallback policy contract 边界已在 plan 中明确 |
| RR-CTX-PLAN-02 | closed | post-compact estimator 兼容性已在 Slice C 验证 |
| RR-CTX-PLAN-03 | closed | 连续 overflow E2E 确定性已在 Slice E 验证 |

无新 residual risk。所有 tracked items 处于 `closed` 或 `deferred-with-owner`。

**阻塞 draft-PR-pass**: 否。

---

## 残余风险

| ID | 风险 | 状态 | Owner | 建议 |
|---|---|---|---|---|
| RR-CTX-SLICED-01 | `not_applicable` 常量三地重复 | deferred-with-owner | WU-LAYER-02 shared helper consolidation | 后续 cleanup 时收敛 |
| F-PR-3 | `RecentWindowFallbackAction` 枚举未充分使用 | info | future | 不影响 correctness；可后续 alignment |

## 下一 gate 建议

PR 自洽，可保持 **draft-PR-pass**。建议下一 gate：
- 用户授权后 → merge / ready-for-review / reviewer request

## 变更摘要

改了什么：
1. 默认 `max_compaction_attempts_per_operation` 从 2/3 统一提升到 5（常量 + 4 个 packaged profile）
2. `conversation_compaction` scene 默认 model 从 high-spec 改为 flash-tier（`deepseek-v4-flash`）
3. `CONTEXT_COMPACTION_FAILED` payload 新增 5 个字段：`operation_id`, `attempt_count`, `retry_repair_budget_exhausted`, `fallback_policy_decision`, `fallback_input_window`, `fallback_input_digest`, `fallback_budget_result`, `fallback_action`
4. 新增 `context_fallback.py`（744 行）：deterministic recent-window fallback selection、预算重估、diagnostic payload 构造
5. `dispatch.py`：proactive compact failure 统一走 `_append_compaction_failed_with_proactive_fallback`，预算通过则 fallback dispatch
6. `engine_ingest.py`：reactive compact failure 统一走 `_reactive_fallback_decision`，预算通过则创建 recovery Attempt
7. `run_input.py`：新增 `ContextFallbackProvider` protocol + `EventLogContextFallbackProvider`，fallback view rendering
8. 测试：新增/更新 ~1200 行测试，覆盖 fallback selection 稳定性、fallback estimate normal/empty/over-budget、fallback rendering、proactive/reactive fallback dispatch/fail closed、连续 reactive overflow fail closed
9. README：`dayu/host/README.md` 新增 fallback 语义描述；`tests/README.md` 记录 fallback 和 overflow E2E 覆盖

验证了什么：
- pytest 受影响测试集合：249 passed
- pyright：0 errors, 0 warnings, 0 informations
- 5 条状态转换路径全部代码对齐
- 13 字段 EventLog payload schema 完整并有一致性校验
- 无 `Any`/`object`/`hasattr`/`getattr` 违规
- 无 runtime import 边界违规
- 无魔法数字
- 中文 docstring 完整
