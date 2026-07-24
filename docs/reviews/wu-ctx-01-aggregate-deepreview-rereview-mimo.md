# WU-CTX-01 Aggregate Deepreview Re-Review（AgentMiMo）

## 1. Gate metadata

- Work Unit：`WU-CTX-01`
- WU base：`5afe71fe`
- accepted tip（fix 前）：`fad15d39`
- re-review range：`5afe71fe..working-tree`（含 Codex fix，未 commit）
- 本 artifact：`docs/reviews/wu-ctx-01-aggregate-deepreview-rereview-mimo.md`
- Controller adjudication：`docs/reviews/wu-ctx-01-aggregate-deepreview-controller-adjudication.md`
- Codex fix artifact：`docs/reviews/wu-ctx-01-aggregate-deepreview-review-fix-codex.md`
- 原 MiMo review：`docs/reviews/code-review-20260724-074017.md`
- 原 DS review：`docs/reviews/code-review-20260724-073108.md`
- 排除：`docs/host/issues-implementation-control.md`（Controller-owned）
- 角色：AgentMiMo，只 review，不实现

## 2. Verdict

**`pass`**

九项 accepted findings（CTRL-AGG-01..09）全部 closure verified。未发现新 actionable finding。reactive recovery refactor 保持单事务 / CAS / manifest→fact→start 顺序；判别联合完整且 source priority 未漂移；no-usage public Host test 确实不发 usage 且成功终态；strict soft<hard 与 basis-point 均为唯一 owner；compactor exclusion 有 direct test；steer 单次 estimate。adversarial failure pass、semantic ownership drift、过度耦合、LLM-facing / README / typing / tests / coverage evidence 均通过。

## 3. CTRL-AGG-01..09 Closure 逐项核对

### CTRL-AGG-01 — usage pairing status/reason 改为封闭类型 ✓

- **验证**：`engine_ingest.py:391-403` 定义 `_UsagePairingStatus(StrEnum)` 与 `_UsagePairingReason(StrEnum)`；`_UsageManifestPairing` 使用枚举类型而非 `str`；生产分支使用 enum identity 比较（`pairing.status is _UsagePairingStatus.COMPLETE`）；durable JSON 边界显式输出 `.value`。
- **旧 finding 来源**：MiMo F01。
- **Closure**：complete。

### CTRL-AGG-02 — continuation frozen source 判别联合 ✓

- **验证**：`engine_ingest.py:696-741` 定义 `_UnavailableContinuationFrozenSources`（`unavailable_reason: RunnerCallSizingUnavailableReason`）与 `_CompleteContinuationFrozenSources`（所有字段非 Optional）；类型别名为 `Union`；consumer 使用 `isinstance` 判别，不使用 `cast`。全文件 `cast()` 残留仅一处（`engine_ingest.py:6788`），是 `Mapping[str, JsonValue]` 类型窄化，与 frozen source 无关。
- **旧 finding 来源**：MiMo F02。
- **Closure**：complete。

### CTRL-AGG-03 — reactive recovery refactor ✓

- **验证**：`engine_ingest.py:799-851` `__call__` 现为 52 行编排方法，调用六个模块级私有 helper：`_load_reactive_recovery_source`、`_prepare_reactive_recovery_candidate`、`_build_reactive_recovery_sizing`、`_close_reactive_fallback_hard_if_required`、`_commit_reactive_recovery_start_truths`、`_reactive_recovery_started`。
- **事务顺序**：`_commit_reactive_recovery_start_truths`（`engine_ingest.py:1096-1163`）保持 manifest（`record_prepared_runner_call_candidate_in_transaction`）→ budget fact（`append_context_budget_evaluated_in_transaction`）→ start rows（`start_recovery_run_with_starting_attempt_in_transaction`）顺序。CAS rollback 语义不变。
- **旧 finding 来源**：MiMo F03。
- **Closure**：complete。

### CTRL-AGG-04 — no-usage public Host 成功终态组合测试 ✓

- **验证**：`test_public_tool_wiring_smoke.py:42-114` `test_scripted_runner_without_usage_emits_conservative_fact_and_succeeds`：
  - 使用 `ToolCallingWorkerFactory` scripted runner，不产生 usage event。
  - 断言 Run 终态为 `SUCCEEDED`。
  - 断言无 `USAGE_REPORTED` event。
  - 解析所有 `CONTEXT_BUDGET_EVALUATED` payload，断言 `estimate_method=CONSERVATIVE_FALLBACK`、`fallback_reason=USAGE_MISSING`。
  - 不依赖真实 provider、不 monkeypatch resolver。
- **旧 finding 来源**：MiMo F04。
- **Closure**：complete。

### CTRL-AGG-05 — steer 同一 candidate 只估算一次 ✓

- **验证**：`admission.py:3085-3098` `_create_steer_attempt_result` 中 `estimate_prepared_runner_call_candidate` 仅调用一次，结果存入 `estimate` 变量，后续 `build_conservative_context_sizing_result`、`record_prepared_runner_call_candidate_in_transaction`、`build_context_sizing_result` 全部复用同一对象。无第二次调用。
- **旧 finding 来源**：MiMo F07。
- **Closure**：complete。

### CTRL-AGG-06 — soft/hard threshold 严格不变量统一 ✓

- **验证**：`context_budget.py:1372-1397` 定义 `validate_context_threshold_ordering`，条件为 `soft_threshold_tokens >= hard_threshold_tokens` 时 raise `ValueError`（即强制 `soft < hard`）。三个 consumer 统一调用该 helper：
  - `ContextSizingResult.__post_init__`（`context_budget.py:570-573`）
  - `context_sizing_pressure_and_decision`（`context_budget.py:1360-1363`）
  - `parse_context_budget_evaluated_payload`（`context_events.py:390-393`）
- 无残留 `>` 或 `>=` 独立比较。错误文本统一为"soft 必须小于 hard"。
- **旧 finding 来源**：DS F01、F04（合并为一个 finding）。
- **Closure**：complete。

### CTRL-AGG-07 — utilization basis-point 比例单一真源 ✓

- **验证**：`context_budget.py:57` 定义 `_UTILIZATION_BASIS_POINTS_SCALE = 10_000`，是全代码库唯一定义。`context_utilization_basis_points` helper（`context_budget.py:1400-1426`）被 `build_context_sizing_result_from_atoms`、`build_frozen_context_sizing_result_from_atoms` 和 `context_events.py:394`（通过 import）复用。`context_events.py` 中无独立 `10_000` 常量。
- **旧 finding 来源**：DS F02。
- **Closure**：complete。

### CTRL-AGG-08 — 删除错误 owner 下的 continuation dead fallback reasons ✓

- **验证**：`context_budget.py:106-129` `ContextSizingFallbackReason` 枚举中无 `CONTINUATION_*_UNAVAILABLE` 成员。`RunnerCallSizingUnavailableReason`（`_runner_call_manifest.py:252-255`）保留该四个成员，作为正确的 manifest sizing unavailable 原因 owner。两个枚举边界清晰。
- **旧 finding 来源**：DS F03。
- **Closure**：complete。

### CTRL-AGG-09 — compactor manifest 不得成为 usage anchor 的直接测试 ✓

- **验证**：`test_context_anchor.py:486-531` `test_compactor_manifest_usage_is_excluded_without_orphan_barrier`：
  - 写入 ordinary call（call_index=0）和 compactor call（call_index=1，`compactor=True`）。
  - 断言 anchor 选中 ordinary call 而非 compactor。
  - 断言 compactor usage 未被选为 anchor。
  - 断言 compactor exclusion 不形成 orphan barrier。
- **旧 finding 来源**：DS F11。
- **Closure**：complete。

## 4. Adversarial Failure Pass

### 4.1 Reactive recovery 事务原子性

**验证**：`_commit_reactive_recovery_start_truths` 在同一 `HostTransaction` 内写 manifest、budget fact、RUN_STARTED、ATTEMPT_STARTED 和 dispatch row。异常时整体 rollback。Controller 已 rejected MiMo F08（"impossible partial commit scenario"），本 re-review 确认该 rejection 仍然成立——修复未引入新事务拆分。

### 4.2 判别联合穷举性

**验证**：consumer（`engine_ingest.py:6837`）使用 `isinstance(frozen_sources, _UnavailableContinuationFrozenSources)` 判断 unavailable 分支，else 处理 complete 分支。两成员 union 的 isinstance 判别在 pyright 下等价于穷举。无遗漏分支。

### 4.3 Source priority 一致性

**验证**：continuation frozen source loader 仍按 projection → tool schema → policy → request semantics 的失败优先级（`_load_reactive_recovery_source` docstring 明确记录）。`RunnerCallSizingUnavailableReason` 仍为 manifest sizing unavailable 原因 owner，未与 `ContextSizingFallbackReason` 混淆。

### 4.4 No-usage test 真实性

**验证**：`test_scripted_runner_without_usage_emits_conservative_fact_and_succeeds` 使用 `ToolCallingWorkerFactory` 构造 scripted runner，该 runner 正常返回 assistant message 但不产生 `USAGE_REPORTED` event。测试通过 `open_host` 走完整 public Host lifecycle（submit → wait → terminal），未 monkeypatch resolver 或 inject mock。

### 4.5 Strict soft < hard 无遗漏

**验证**：`grep -rn "soft_threshold.*hard_threshold\|hard_threshold.*soft_threshold" dayu/host/context_budget.py dayu/host/context_events.py` 确认所有比较均通过 `validate_context_threshold_ordering` helper。无独立 `>` 或 `>=` 比较残留。

### 4.6 Basis-point 单一常量

**验证**：`grep -rn "10_000" dayu/host/context_budget.py dayu/host/context_events.py` 仅命中 `context_budget.py:57` 的 `_UTILIZATION_BASIS_POINTS_SCALE`。`context_events.py` 通过 import helper 使用。

### 4.7 Steer 单次 estimate

**验证**：`grep -n "estimate_prepared_runner_call_candidate" dayu/host/admission.py` 在 `_create_steer_attempt_result` 范围内仅命中一次。

## 5. Semantic Ownership Drift 检查

| 检查项 | 结果 | 说明 |
|--------|------|------|
| usage pairing status/reason owner | ✓ | `engine_ingest.py` 持有 StrEnum 定义与 durable projection |
| frozen source union owner | ✓ | `engine_ingest.py` 持有类型定义，consumer 使用 isinstance 判别 |
| threshold ordering owner | ✓ | `context_budget.py` 持有 `validate_context_threshold_ordering`，event parser 调用该 owner |
| basis-point owner | ✓ | `context_budget.py` 持有常量与 helper，`context_events.py` import 复用 |
| CONTINUATION enum boundary | ✓ | `ContextSizingFallbackReason` 不含 continuation 成员；`RunnerCallSizingUnavailableReason` 持有 |
| reactive recovery transaction owner | ✓ | `engine_ingest.py` 持有事务编排，未下沉到 `context_budget.py` |
| steer estimate owner | ✓ | `admission.py` 持有 sizing，不重复调用 estimator |
| compactor exclusion owner | ✓ | `context_anchor.py` 持有 exclusion 逻辑，test 直接验证 contract |

无语义所有权漂移。

## 6. 过度耦合检查

| 检查项 | 结果 | 说明 |
|--------|------|------|
| context_budget ↔ engine_ingest 耦合 | ✓ | 仅通过 typed result / enum / helper 调用，无反向依赖 |
| context_budget ↔ context_events 耦合 | ✓ | event parser import budget helper，单向依赖 |
| admission ↔ context_budget 耦合 | ✓ | admission 调用 sizing builder，无反向 |
| reactive recovery helper 拆分 | ✓ | 六个 helper 均为模块级私有函数，无嵌套类/函数 |

无过度耦合引入。

## 7. LLM-facing / README / Typing / Tests / Coverage Evidence 核对

### 7.1 LLM-facing 文本

本次 fix 不涉及 prompt、tool schema 或 LLM-facing projection 变更。`ContextSizingFallbackReason` 枚举值名称删除了四个 dead members，这些名称不进入 LLM 上下文（它们是 Host 内部 diagnostic）。无 LLM-facing 文本违规。

### 7.2 README

- `tests/README.md` 已更新，补充了三个新增测试能力的描述（compactor exclusion、no-usage conservative fallback、steer single estimate）。
- `dayu/host/README.md` 无 diff——本次 fix 未改变 public API、稳定架构边界或既有 Host 开发契约。符合 README 触发规则。
- 未修改两路 review artifact、Controller adjudication 或 `docs/host/issues-implementation-control.md`。

### 7.3 Typing

pyright 对四个 changed production 文件输出 `0 errors, 0 warnings, 0 informations`。判别联合消除了旧 `cast()` 调用；`validate_context_threshold_ordering` 统一了类型校验路径。

### 7.4 Tests

- **Focused suite**：`209 passed in 2.15s`（6 个 owner/integration 测试文件）
- **Full host suite**：`2259 passed, 2 skipped, 6 deselected in 64.54s`
- 无失败、无新增 skip 或 deselect。

### 7.5 Coverage

Codex fix artifact 报告 whole-WU union branch coverage 86%（25 个 production Python 文件），最低 82%（`run_input.py`）。每个文件均 >= 80%。本 re-review 不重复执行 coverage run——Codex artifact 的 coverage 数据来自同一 working tree，与本次验证的测试结果一致。

## 8. Rejected Finding 复核

Controller 裁决的 10 个 rejected findings（MiMo F05/F06/F08、DS F05/F06/F07/F08/F09/F10/F12）在本 re-review 中不重新打开——未给出新的当前直接 failure evidence。具体复核：

- **MiMo F05**（type annotation）：Controller 确认 `HostTransaction.fetchall()` 精确签名已是 `tuple[HostRow, ...]`，pyright 0 errors。维持 rejected。
- **MiMo F06**（stage→strategy 抽象）：Controller 判定两个 producer 复用 sizing builder 而非同一 lifecycle state machine，抽到 `context_budget.py` 会扩大耦合。维持 rejected。
- **MiMo F08**（partial commit）：Controller 判定同一 SQLite write transaction 保证原子性。fix 未引入事务拆分。维持 rejected。
- **DS F05..F12**：Controller 已逐项给出 rejection 理由，fix 未改变相关代码路径的前提条件。维持 rejected。

## 9. 新 Finding 清单

**无新 actionable finding。**

Adversarial failure pass、semantic ownership drift、over-coupling、LLM-facing、README、typing 和 test coverage 核对均未发现可被直接证据支撑的新 defect。

## 10. Residual Risk

| 风险 | 严重程度 | 说明 |
|------|----------|------|
| 长期 Session anchor scan 性能 | 低 | 非本 WU regression，非 blocking |
| 多进程 concurrent budget fact append 幂等 | 低 | 非本 WU regression |
| 真实 provider usage 差异 | 信息 | 由既有 provider smoke / matrix 覆盖 |
| opt-in stress tests 未显式运行 | 信息 | 默认 pytest 配置排除，完整 Host suite 全绿 |

以上 residual risks 均非本 fix gate 引入，不转化为 blocking obligation。

## 11. 验证命令与结果汇总

```bash
# Focused owner/integration tests
pytest -q tests/host/test_context_budget.py tests/host/test_context_budget_evaluated.py \
  tests/host/test_context_anchor.py tests/host/test_engine_ingest_mapping.py \
  tests/host/test_public_steer.py tests/host/test_public_tool_wiring_smoke.py
# → 209 passed in 2.15s

# Full host tests
pytest -q tests/host
# → 2259 passed, 2 skipped, 6 deselected in 64.54s

# Pyright (changed production files)
python -m pyright dayu/host/admission.py dayu/host/context_budget.py \
  dayu/host/context_events.py dayu/host/engine_ingest.py
# → 0 errors, 0 warnings, 0 informations

# Basis-point single source audit
grep -rn "10_000" dayu/host/context_budget.py dayu/host/context_events.py
# → only context_budget.py:57

# Dead enum audit
grep -rn "CONTINUATION.*UNAVAILABLE" dayu/host/context_budget.py
# → no results

# Cast on frozen sources audit
grep -rn "cast(" dayu/host/engine_ingest.py | grep -i "frozen_source"
# → no results
```

## 12. Decision

**`pass`**

CTRL-AGG-01..09 全部 closure verified，无新 actionable finding。可以进入 Controller final aggregate adjudication。
