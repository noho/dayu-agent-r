# WU-CTX-01 Aggregate Deepreview Re-Review（AgentDS）

## 1. Re-review metadata

- **角色**：AgentDS（Claude Code reviewer），只 review，不实现、不修改
  production/tests/Controller docs、不 commit。
- **Review range**：`5afe71fe`（WU base）→ 当前 working tree
- **参考文档**：
  - `AGENTS.md`
  - `docs/host/design.md` §25
  - `docs/reviews/wu-ctx-01-aggregate-deepreview-controller-adjudication.md`
  - `docs/reviews/wu-ctx-01-aggregate-deepreview-review-fix-codex.md`
  - `docs/reviews/code-review-20260724-073108.md`（AgentDS 原 aggregate review）
  - `docs/reviews/code-review-20260724-074017.md`（AgentMiMo aggregate review）
  - 各 accepted plan / amendment / Slice artifact
- **排除**：Controller-owned `docs/host/issues-implementation-control.md`
- **纳入**：当前未 commit 的 production/tests/README 与 fix artifact

## 2. CTRL-AGG-01..09 逐项 closure 核对

### CTRL-AGG-01 — usage pairing status/reason 改为封闭类型 ✅

**证据**：`engine_ingest.py:391-398` — `_UsagePairingStatus(StrEnum)` 定义
`COMPLETE` / `UNAVAILABLE`；`_UsagePairingReason(StrEnum)` 定义
`ITERATION_LINK_MISSING`、`ITERATION_LINK_INVALID`、`MANIFEST_INCOMPLETE`。
`_UsageManifestPairing`（行 668-684）的 `status: _UsagePairingStatus`、
`reason: _UsagePairingReason | None`。

**验证**：
- 所有 producer 分支使用 `_UsagePairingStatus.COMPLETE` / `.UNAVAILABLE` 等
  enum identity（行 7727、7759-7760）。
- consumer（行 4242-4257）使用 `pairing.status is _UsagePairingStatus.COMPLETE`。
- durable JSON 边界显式投影 `.value`（StrEnum 自动行为）。
- 旧 `_USAGE_PAIRING_STATUS_*` / `_USAGE_PAIRING_REASON_*` 字符串常量已无命中。
- `pyright` 0 errors — 封闭枚举在编译期捕获非法值。

**结论**：已闭合。

### CTRL-AGG-02 — continuation frozen source 拆为判别联合 ✅

**证据**：`engine_ingest.py:696-741` — `_UnavailableContinuationFrozenSources`
（`unavailable_reason` + tool schema refs/fragments）与
`_CompleteContinuationFrozenSources`（全部字段非 Optional，包括 `context_window_size: int`、
`provider: str`、`model: str`、`request_semantics_digest: str` 等 10 个必填字段）。
联合类型别名 `_ContinuationFrozenSources`。

**验证**：
- 旧 8 处 `cast(str, frozen_sources...)` / `cast(int, frozen_sources...)` 全部消除。
- 仅剩 1 处 `cast(Mapping[str, JsonValue], item)`（行 6788），位于
  `isinstance(item, Mapping)` guard 后，是合法的窄化 cast。
- consumer（行 6837）使用 `isinstance(frozen_sources, _UnavailableContinuationFrozenSources)`
  显式穷举；else 分支自然消费 `_CompleteContinuationFrozenSources` 非可选字段。
- loader（行 6586-6739）继续按 projection → tool schema → policy → request semantics
  优先级失败；complete 返回 `_CompleteContinuationFrozenSources`，
  unavailable 返回 `_UnavailableContinuationFrozenSources`。
- `pyright` 0 errors — 判别联合在类型检查时确保穷举。

**结论**：已闭合。

### CTRL-AGG-03 — 拆分 reactive recovery start God method ✅

**证据**：`engine_ingest.py:790-851` — `_StartReactiveRecoveryOperation.__call__`
现在约 60 行，只做编排。拆分为以下模块级 typed helper：

| Helper | 行号 | 职责 |
|--------|------|------|
| `_load_reactive_recovery_source` | 854-901 | CAS 校验 + strict-load source candidate |
| `_prepare_reactive_recovery_candidate` | 904-944 | 从 source frozen execution truth 组装 candidate |
| `_build_reactive_recovery_sizing` | 947-1009 | 构造同源 sizing result |
| `_close_reactive_fallback_hard_if_required` | 1012-1054 | hard fallback 收口 |
| `_reactive_recovery_start_input` | 1057-1083 | 分配唯一 start identity |
| `_commit_reactive_recovery_start_truths` | 1086-1172 | manifest → fact → start rows 提交 |
| `_reactive_recovery_sizing_snapshot` | 1175-1201 | sizing → manifest snapshot 投影 |
| `_reactive_recovery_started` | 1204-1232 | 构造 transaction-local started 摘要 |
| `_validate_reactive_recovery_outcome_event` | 1235-... | outcome event 校验 |

**验证**：
- 所有写入仍使用同一 `HostTransaction`。
- `_commit_reactive_recovery_start_truths`（行 1086-1172）按
  manifest → budget fact → `RUN_STARTED` / `ATTEMPT_STARTED` 顺序提交：
  - 行 1110：`record_prepared_runner_call_candidate_in_transaction`（manifest）
  - 行 1124：`append_context_budget_evaluated_in_transaction`（budget fact）
  - 行 1134：`start_recovery_run_with_starting_attempt_in_transaction`（start rows）
- CAS rollback 保持：`_ReactiveRecoveryStartCasMissRollback` 在 source 校验（行 883）
  和 start transition 校验（行 1149、1159）两处抛出。
- hard fallback 保持 budget fact → terminal closeout 顺序（`_close_reactive_fallback_hard_if_required`，
  行 1038-1054）。
- 未将 lifecycle policy 下沉到 `context_budget.py`。
- `pyright` 0 errors。

**结论**：已闭合。

### CTRL-AGG-04 — provider 无 usage 的 public Host 成功终态组合测试 ✅

**证据**：`tests/host/test_public_tool_wiring_smoke.py:42-114` —
`test_scripted_runner_without_usage_emits_conservative_fact_and_succeeds`。

**验证**：
- 使用合法 `ToolCallingWorkerFactory` scripted runner，不产生 usage。
- 通过 `open_host` public API 完整生命周期。
- 断言：
  - `terminal.kind is HostEventKind.SUCCEEDED`（行 99）
  - `"USAGE_REPORTED" not in event_types`（行 101）
  - 存在 `CONTEXT_BUDGET_EVALUATED`（行 109）
  - 所有 budget payload 的 `estimate_method is ContextEstimateMethod.CONSERVATIVE_FALLBACK`
    且 `fallback_reason is ContextSizingFallbackReason.USAGE_MISSING`（行 110-113）
- 未依赖真实 provider、provider 名称分支或 monkeypatch resolver 返回值。
- 测试通过（`209 passed` in focused suite）。

**结论**：已闭合。

### CTRL-AGG-05 — steer 同一 candidate 只估算一次 ✅

**证据**：`admission.py:3075-3086` — steer 首次 conservative sizing 保存
`estimate: BudgetEstimate | None = None`，随后 `estimate = estimate_prepared_runner_call_candidate(...)`；
行 3147 — anchor 重算复用同一 `estimate=estimate`。

**验证**：
- `grep -n "estimate_prepared_runner_call_candidate" admission.py` 仅命中两次：
  一次 import（行 162）、一次调用（行 3085）。旧第二次调用（原行 3145）已删除。
- `test_steer_hard_continuation_orders_fact_before_new_attempt`（行 122-252）：
  - monkeypatch 记录 `estimate_call_count`（行 137-151）
  - 记录 steer 前调用数 `calls_before_steer`（行 232）
  - 断言 `estimate_call_count - calls_before_steer == 1`（行 252）
- guard（行 3125）：`if context_budget_policy is None or estimate is None` —
  双重保护，确保不会在未初始化 estimate 的情况下使用。
- `pyright` 0 errors。

**结论**：已闭合。

### CTRL-AGG-06 — soft/hard threshold 严格不变量统一 ✅

**证据**：`context_budget.py:1372-1397` — `validate_context_threshold_ordering`
是唯一校验 owner，使用严格 `soft_threshold_tokens >= hard_threshold_tokens` → `ValueError`，
错误文本 "soft_threshold_tokens must be less than hard_threshold_tokens"。

**验证**：
- 所有 result 构造、decision matrix 与 durable parser 统一调用该 helper：
  - `ContextSizingResult.__post_init__`（行 570）
  - `context_sizing_pressure_and_decision`（行 1360）
  - `parse_context_budget_evaluated_payload`（`context_events.py:390`）
- `test_soft_threshold_must_be_strictly_less_than_hard_across_boundaries`
  （`test_context_budget_evaluated.py:69-100`）：
  - typed `ContextSizingResult` 构造 `soft == hard` → `ValueError("less than")`（行 77-81）
  - decision matrix 传入 `soft == hard` → `ValueError("less than")`（行 82-88）
  - durable parser 篡改 payload `soft == hard` → `ValueError("less than")`（行 99-100）
- stale audit：旧 `must not exceed` / `thresholds are out of order` 文本无命中。
- `pyright` 0 errors。

**结论**：已闭合。

### CTRL-AGG-07 — utilization basis-point 比例单一真源 ✅

**证据**：`context_budget.py:57` — `_UTILIZATION_BASIS_POINTS_SCALE = 10_000`
是唯一常量定义。`context_budget.py:1400-1424` — `context_utilization_basis_points`
是唯一 typed calculation helper。

**验证**：
- `grep -n "10_000" context_budget.py context_events.py`：仅在
  `context_budget.py:57` 命中（单一私有常量）。
- `context_events.py` 导入 `context_utilization_basis_points`（行 32）并在
  durable parser 校验时调用（行 394）。
- result builders（行 574、1052、1136）全部调用 `context_utilization_basis_points`。
- `context_events.py` 不定义同名常量。
- `pyright` 0 errors。

**结论**：已闭合。

### CTRL-AGG-08 — 删除错误 owner 下的 continuation dead fallback reasons ✅

**证据**：`ContextSizingFallbackReason`（`context_budget.py:106-130`）现在
只有 19 个成员，不含任何 `CONTINUATION_*` 成员。

**验证**：
- `grep -n "CONTINUATION_PROJECTION_UNAVAILABLE\|CONTINUATION_TOOL_SCHEMA_UNAVAILABLE\|CONTINUATION_POLICY_UNAVAILABLE\|CONTINUATION_REQUEST_SEMANTICS_UNAVAILABLE" context_budget.py`
  返回零结果。
- 四个名字只存在于正确 owner `RunnerCallSizingUnavailableReason`
  （`_runner_call_manifest.py:252-255`）。
- `_runner_call_manifest.py` 的 producer/consumer 路径不受影响。
- 未新增 consumer 让死枚举"活起来"，未合并两个不同 owner 的 enum。
- `pyright` 0 errors。

**结论**：已闭合。

### CTRL-AGG-09 — compactor manifest 不得成为 usage anchor 的直接测试 ✅

**证据**：`tests/host/test_context_anchor.py:486-531` —
`test_compactor_manifest_usage_is_excluded_without_orphan_barrier`。

**验证**：
- 先构造普通 call（`call_index=0`，`conservative_tokens=6000`，`prompt_tokens=6200`，
  `compactor=False`），再构造更近的 compactor call（`call_index=1`，
  `conservative_tokens=6100`，`prompt_tokens=9900`，`compactor=True`）。
- 断言：
  - `resolution.fallback_reason is None`（成功解析，非 barrier）
  - `resolution.anchor.manifest_event_id == ordinary.manifest.event_id`
    （普通 call 被选中）
  - `resolution.anchor.usage_anchor_tokens == 6200`（普通 call 的 usage）
  - `resolution.anchor.manifest_event_id != compactor.manifest.event_id`
    （compactor manifest 未被选中）
  - `resolution.anchor.usage_event_id != compactor.usage.event_id`
    （compactor usage 未被选中）
- fixture 通过 `_append_call(compactor=True)` 构造合法 `compactor_identity`，
  包含 `parent_host_run_id`、`compaction_operation_id` 等完整字段。
- 不在 resolver 下游或 fixture 中加入测试特例。
- 测试通过。

**结论**：已闭合。

## 3. Adversarial failure pass

以下 adversarial 场景已逐一验证，无需新增修复：

| 场景 | 验证结果 | 证据 |
|------|----------|------|
| `soft == hard` 同时穿透 typed result、decision matrix、durable parser | 三层全部 fail closed | `test_soft_threshold_must_be_strictly_less_than_hard_across_boundaries` |
| compactor manifest 是唯一 evidence 时 resolver 行为 | 已在既有 barrier 测试中覆盖（`MANIFEST_INCOMPLETE`） | `test_context_anchor.py` 的 barrier parametrize |
| steer estimate 初始化失败后 estimate 为 None | guard `estimate is None` 抛出 `HostDurableError` | `admission.py:3125` |
| reactive recovery 中 CAS 竞争（并发 winner 已创建 Attempt） | `_ReactiveRecoveryStartCasMissRollback` 在 source 和 transition 两处抛出 | `engine_ingest.py:883,1149,1159` |
| reactive recovery 中 manifest 写入成功但 budget fact 写入失败 | 同一 `HostTransaction`，整体 rollback | `_commit_reactive_recovery_start_truths` 使用同一 transaction |
| continuation frozen source 的 unavailable 分支字段被误当 complete 消费 | 判别联合在 `isinstance` guard 后自然隔离 | `engine_ingest.py:6837` |
| `_build_reactive_recovery_sizing` 对 DISPATCH_FALLBACK + anchor 不可用 | anchor resolution 返回 barrier → `build_context_sizing_result` 内部 fallback | `context_budget.py` 的 `build_context_sizing_result` |
| 15-cell matrix 新增 stage 或 pressure | `case _:` → `AssertionError` fail closed | `context_budget.py:1508-1509` |

## 4. Semantic ownership drift 检查

| 检查项 | 结果 | 证据 |
|--------|------|------|
| threshold ordering owner 唯一 | ✅ PASS | `context_budget.py:validate_context_threshold_ordering`；`context_events.py` 只导入复用 |
| utilization basis points owner 唯一 | ✅ PASS | `context_budget.py:_UTILIZATION_BASIS_POINTS_SCALE` + `context_utilization_basis_points()`；`context_events.py` 只导入复用 |
| usage pairing status/reason owner | ✅ PASS | `engine_ingest.py` 内 `_UsagePairingStatus` / `_UsagePairingReason`，JSON 边界只投影 `.value` |
| continuation frozen source 字段 ownership | ✅ PASS | `_CompleteContinuationFrozenSources` 全部必填；consumer 不经 `cast` 访问 |
| fallback reason enum ownership | ✅ PASS | `ContextSizingFallbackReason` 不再含 continuation 成员；`RunnerCallSizingUnavailableReason` 保持独立 owner |
| 下游无重算 sizing | ✅ PASS | steer 复用同一 `BudgetEstimate`；未在 projection 或 Service 重算 |
| 无 `hasattr`/`getattr` 滥用 | ✅ PASS | 修改的四个 production 文件中零命中 |
| 无反向依赖 | ✅ PASS | `context_events.py` → `context_budget.py` 方向正确 |
| 无 shared mutable state | ✅ PASS | 全部为 `frozenset`/`int`/`str`/dataclass frozen |

## 5. 过度耦合检查

| 检查项 | 结果 | 证据 |
|--------|------|------|
| `_build_reactive_recovery_sizing` 与 dispatch.py 的 stage→strategy 判定 | ✅ 无新耦合 | 两者各自调用 `context_budget.py` 的 sizing builder，不共享 stage→strategy 中间态 |
| `context_events.py` 对 `context_budget.py` 的依赖 | ✅ 单向且合理 | durable parser 需要校验 owner 级 invariant，导入 `validate_context_threshold_ordering` 和 `context_utilization_basis_points` |
| 新 helper 之间的耦合 | ✅ 无循环 | `_StartReactiveRecoveryOperation.__call__` → helpers → builders/manifest/transition，单向 |

## 6. LLM-facing / README / typing / tests / coverage 证据核对

| 检查项 | 结果 |
|--------|------|
| LLM-facing 文本 | ✅ 本次修改均为内部 typed contract 变更，不影响 LLM-facing prompt/tool schema/message 内容 |
| `tests/README.md` | ✅ 已更新，新增 "context budget / anchor integration" 条目，使用稳定能力标题，不含 WU/aggregate/fix gate 过程措辞 |
| `dayu/host/README.md` | ✅ 无 diff；public API、稳定架构边界、既有 Host 开发契约未变化，按 README 更新触发规则不机械更新 |
| pyright | ✅ `0 errors, 0 warnings, 0 informations` |
| focused tests | ✅ `209 passed in 2.11s` |
| full Host tests | ✅ `2259 passed, 2 skipped, 6 deselected in 54.07s` |
| branch coverage | ✅ whole-WU union 86%，最低单文件 82%（`run_input.py`），全部 ≥80% |

## 7. 新 actionable finding 检查

经 adversarial failure pass、semantic ownership drift 检查、过度耦合检查与
LLM-facing/README/typing/tests/coverage 证据核对，**未发现新的 actionable finding**。

以下为已确认的非 actionable 观察项：

1. **`context_events.py:32` 导入 `context_utilization_basis_points`**：这是 durable parser
   校验 owner 级 invariant 的正确行为，不是跨层耦合。
2. **`engine_ingest.py:6788` 的 `cast`**：位于 `isinstance(item, Mapping)` guard 后，
   是合法的类型窄化，不是 CTRL-AGG-02 修复前的 8 处滥用。
3. **`_build_reactive_recovery_sizing` 对 DISPATCH_FALLBACK 使用 anchor resolution**：
   符合 design.md §25 的 dispatch_fallback sizing 语义——它是 tier 4/5 fallback candidate，
   仍有资格尝试 anchor resolution；fallback 路径在 resolver 返回 barrier 时正确降级。

## 8. Verdict

**`pass`**

所有 9 项 `CTRL-AGG-01..09` 已完全闭合，无 residual actionable finding。
adversarial failure pass、semantic ownership drift、过度耦合、LLM-facing/README/typing/
tests/coverage 证据核对均通过。未重新打开 Controller rejected finding。
未发现新的 actionable finding。

## 9. 验证摘要

```bash
# focused owner/integration tests
pytest -q tests/host/test_context_budget.py tests/host/test_context_budget_evaluated.py \
  tests/host/test_context_anchor.py tests/host/test_engine_ingest_mapping.py \
  tests/host/test_public_steer.py tests/host/test_public_tool_wiring_smoke.py
# → 209 passed in 2.11s

# full Host suite
pytest -q tests/host
# → 2259 passed, 2 skipped, 6 deselected in 54.07s

# pyright
python -m pyright dayu/ tests/ utils/
# → 0 errors, 0 warnings, 0 informations
```

## 10. Residual risk

| 风险 | 严重程度 | 说明 |
|------|----------|------|
| long-session keyset scan performance | 低 | Controller 明确保留，不属于本 gate |
| 真实 provider smoke | 低 | 既有 provider smoke 覆盖；public no-usage 测试使用合法 scripted runner |
| 多进程 budget fact 并发幂等 | 低 | 既有 `test_admission_multiprocess.py` 覆盖基本并发场景；deterministic event_id 保证幂等 |
| stress tests 未显式运行 | 信息 | 6 个 opt-in stress tests 被默认排除；完整 Host suite 全绿 |
