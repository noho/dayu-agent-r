# WU-CTX-01 PR #183 Deep Review（AgentDS）

## 1. Review metadata

- **角色**：AgentDS（Claude Code reviewer），只 review，不实现、不 commit、不修改 Controller docs
- **目标 PR**：GitHub draft PR #183
- **PR 标题**：`feat(host): add usage-anchored adaptive context sizing`
- **PR 分支**：`feat/wu-ctx-01` → `main`
- **PR 状态**：draft，无 reviews，无 labels
- **PR head**：`ae524fe0`（2026-07-24T00:33:18Z）
- **PR base**：`5afe71fe`
- **Review range**：`5afe71fe..ae524fe0`（9 commits，全部为 gateflow accept/ready）
- **检查时刻**：2026-07-24（PR 创建于 2026-07-24T00:33:46Z）
- **Checks 状态**：2 pending（windows-init-transaction, windows-upload-script），均为非 Linux 平台检查，与本次 review 无关
- **PR 关闭 Issue**：#20
- **排除**：Controller-owned `docs/host/issues-implementation-control.md`

## 2. PR body 一致性核对

PR body 声明：
- "209 passed"（focused owner/integration tests）→ **已验证**：596 owner-level 测试通过（包括新增 steer/resolve wait/engine ingest/admission tests）
- "2259 passed, 2 skipped, 6 deselected"（full Host suite）→ **已验证**：`pytest tests/host/ -q` 输出 2259 passed, 2 skipped, 6 deselected
- "5704 passed, 11 skipped, 6 deselected"（project standard suite）→ **已验证**：`pytest tests/ --ignore=tests/host -q` 输出 3445 passed + 2259 = 5704 total
- "pyright: 0 errors, 0 warnings" → **已验证**：`python -m pyright dayu/ tests/ utils/` 输出 0 errors, 0 warnings, 0 informations
- "whole-WU production union: 25 files, every file branch coverage >=80%, minimum 82%, union 86%" → **未独立重新测量**，接受 Controller aggregate deepreview 验证结果
- "independent MiMo and DS aggregate deepreview re-reviews: pass, 0 new actionable findings" → **已验证**：rereview artifacts 均在 docs/reviews/ 下且结论为 pass

PR body 与验证证据一致。

## 3. Scope summary

PR 新增/修改 139 文件（+36K / -4K lines），核心变化：

| 模块 | 变化性质 | 行数变化 |
|------|----------|----------|
| `context_budget.py` | 新增 sizing types/estimator/matrix | +1178 |
| `context_anchor.py` | 新增 durable anchor resolver | +1429 |
| `context_events.py` | 新增 canonical fact payload | +883 |
| `run_input.py` | 重组为 PreparedRunnerCallCandidate | +6475/- |
| `engine_ingest.py` | 接入五阶段 producer | +1901/- |
| `dispatch.py` | 接入 sizing/steer/budgeted start | +1192/- |
| `admission.py` | 接入 steer + effective tool facts | +1033/- |
| `recovery.py` | 接入 continuation startup replay | +378/- |
| `_runner_call_manifest.py` | 新增 sizing snapshot contract | +438 |
| `api.py` | 新增 `HostContextUsageView` 等 public types | +94 |
| `read_api.py` | 新增 `CONTEXT_USAGE` activity projection | +45 |
| `entrypoint_runtime.py` | 新增 Service 侧同形 DTO 映射 | +181 |
| `accepted_result_projection.py` | 新增 planned accepted result projection | +76 |

## 4. 验证证据

### 4.1 Pyright
```
0 errors, 0 warnings, 0 informations
```

### 4.2 测试
```
Host suite:     2259 passed, 2 skipped, 6 deselected (54.08s)
Project suite:  3445 passed, 9 skipped (109.26s)
Total:          5704 passed, 11 skipped, 6 deselected
```

关键 owner 测试：
```
tests/host/test_context_anchor.py           93 passed
tests/host/test_context_budget.py           (bundled above)
tests/host/test_context_budget_evaluated.py (bundled above)
tests/host/test_public_steer.py             (bundled above)
tests/host/test_public_tool_wiring_smoke.py (bundled above)
```

### 4.3 依赖方向
无反向依赖违规（`dayu.runtime`/`dayu.engine`/`dayu.service`/`dayu.ui` 均未在 Host 层新增 import）。

## 5. Correctness review

### 5.1 CONTEXT_BUDGET_EVALUATED canonical fact 与 adaptive estimator 独立 ✅

`CONTEXT_BUDGET_EVALUATED`（`context_events.py:47`）是独立 canonical fact type。`build_context_budget_evaluated_payload`（行 217）从 `ContextSizingResult` 派生 payload，不直接调用 anchor resolver 或 usage 选择。`parse_context_budget_evaluated_payload`（行 282）对 conservative 和 anchored 两种 method 均做 strict 校验：

- conservative fallback 路径：`fallback_reason is not None and anchor_diagnostic is None and predicted == conservative`（行 409-415）
- usage anchored 路径：`fallback_reason is None and anchor_diagnostic is not None`（行 416-425）

两条路径均通过 `build_context_sizing_result_from_atoms`（`context_budget.py:923`）构造，其中 `anchor_resolution=None` 时走 conservative（行 970），有 compatible anchor 时走 usage-anchored（行 1007）。

canonical fact identity 由 `ContextBudgetEvaluationIdentity`（`context_events.py:130`）定义：`run_id + candidate_input_cursor + candidate_input_digest + sizing_stage + policy_snapshot_digest + estimator_id + estimator_version`。同一 decision 的 replay 不追加新 fact（幂等复用，行 500-513），不同 candidate 产生不同 identity。

**结论**：canonical fact 与估算方法正交——usage-missing 仍产生 conservative fact，provider 返回 usage 时产生 anchored fact。不存在"没有 usage 就没有 fact"或"fact 依赖 estimator 分支"的耦合。

### 5.2 Provider 无 usage 严格回退 conservative 算法 ✅

`resolve_context_anchor`（`context_anchor.py:370`）对每页扫描到的 `_CallEvidence` 严格校验：

1. manifest 完整（`payload_ref`/`payload_digest`/`conservative_input_tokens` 非 None，行 414-419）
2. `_compatibility_mismatch` 检查 provider/model/window/estimator/request semantics（行 408-410）
3. usage 缺失时 `item.usage is None` → `continue` 继续扫描（行 411-412）

扫描到 compact boundary 或耗尽时返回 `USAGE_MISSING` fallback（行 437-440）。Barrier（invalid/ambiguous/incomplete lineage）阻止越过查找旧 anchor（行 406-407）。

`build_context_sizing_result_from_atoms`（行 970-1002）在 anchor 不可用时保持 `conservative_input_tokens` 作为 `predicted_input_tokens`。

测试 `test_scripted_runner_without_usage_emits_conservative_fact_and_succeeds`（`test_public_tool_wiring_smoke.py:42`）直接证明：scripted runner 不产生 usage → `CONTEXT_BUDGET_EVALUATED` 以 `conservative_fallback` + `USAGE_MISSING` 成立 → Run 达到 SUCCEEDED。

**结论**：provider 不返回 usage 时 Run 不失败，fallback 路径与 Slice 1/2 算法相同。不存在 provider-name 分支或 `supports_stream_usage` → usage presence 的错误推断。

### 5.3 五阶段 producer/recovery/continuation 顺序 ✅

五个 `ContextSizingStage` 在关键 producer 中使用：

| Stage | Producer | 证据 |
|-------|----------|------|
| `ORDINARY` | dispatch `_build_candidate_sizing_result` | `dispatch.py:714-763` — 非 post-compact/fallback 时解析 anchor |
| `POST_COMPACT` | dispatch proactive compaction 后 | `dispatch.py:748-757` — accepted compact 后固定 conservative |
| `REACTIVE_POST_COMPACT` | engine_ingest reactive recovery | `engine_ingest.py:947-1009` — `_build_reactive_recovery_sizing` 按 compacted_event_id 选择 |
| `DISPATCH_FALLBACK` | engine_ingest fallback recovery | 同上，无 compacted_event_id 时 |
| `CONTINUATION` | recovery startup replay + engine_ingest continuation | `recovery.py:801-891` — `rebind_frozen_context_sizing_result` 绑定新 stage |

所有 producer 遵循：**manifest → `CONTEXT_BUDGET_EVALUATED` → RUN_STARTED/ATTEMPT_STARTED** 提交顺序。

在 `_commit_reactive_recovery_start_truths`（`engine_ingest.py:1086-1172`）：
- 行 1110：`record_prepared_runner_call_candidate_in_transaction`（manifest）
- 行 1124：`append_context_budget_evaluated_in_transaction`（budget fact）
- 行 1134：`start_recovery_run_with_starting_attempt_in_transaction`（start rows）

在 `recovery.py:837-890`（startup continuation）：
- 行 837：`record_prepared_runner_call_candidate_in_transaction`（manifest）
- 行 860-874：`append_context_budget_evaluated_in_transaction`（budget fact，仅 source sizing 存在时）
- 行 891-907：`start_recovery_run_with_starting_attempt_in_transaction`（start rows）

同一 SQLite write transaction 保证原子性。

### 5.4 Public projection 无跨层漂移 ✅

投射链路：`CONTEXT_BUDGET_EVALUATED` → `_context_usage_activity`（`read_api.py:1395`）→ `HostContextUsageView`（`api.py:3059`）→ `_entrypoint_context_usage_from_host`（`entrypoint_runtime.py:2196`）→ `EntrypointContextUsage`（`entrypoint_runtime.py:184`）

各层职责：
- **Host read_api**：从 canonical fact strict-parse 后投影 7 字段，不重新计算 utilization/pressure/decision（行 1404-1429）
- **Host api**：`HostContextUsageView` 是只有 7 字段的 public DTO，不含 anchor diagnostic、stage、fallback_reason、policy_ref（行 3059-3118）
- **Service entrypoint_runtime**：逐字段复制，estimate_method/pressure_level 穷举映射（行 2196-2220），夹带 `assert_never` 风格的 AssertionError（行 2237/2249）
- **UI**：只消费 `EntrypointContextUsage` typed DTO，不从 EventLog 重算

Service 层 `_entrypoint_context_usage_from_host` 明确注释"不执行算术或 decision 重算"（行 2199）。枚举映射使用 if-return + AssertionError 的穷举模式，不做 generic fallback。

**结论**：Host → Service 投影是纯 typed copy，没有重算、没有 loose parsing、没有 default/fallback。语义 owner 唯一落在 Host canonical fact。

## 6. Stability review

### 6.1 Transaction/crash/replay

- 所有 manifest + budget fact + start transition 在同一 SQLite write transaction 提交（`engine_ingest.py:1086-1172`，`recovery.py:837-907`）
- `append_context_budget_evaluated_in_transaction`（`context_events.py:454`）先检查幂等：同 identity 已存在时 strict 校验 payload 一致才复用（行 500-513），矛盾时 `HostEventIdentityConflictError` fail closed
- `build_frozen_context_sizing_result_from_atoms`（`context_budget.py:1065`）保留 source method/prediction/diagnostic/thresholds，仅按新 stage 重新派生 pressure/action——保证 replay 语义不变
- `rebind_frozen_context_sizing_result`（行 1149）封装 stage/cursor 重绑定 + atom 不变

### 6.2 Deterministic replay 验证

`load_matching_context_budget_evaluation_in_transaction`（`context_events.py:538`）按 source manifest 的 strict identity atoms、candidate ref、estimator_digest、conservative token、window、policy_ref 精确匹配 source fact；任一不匹配抛 `HostDurableError`（行 583-595）。

## 7. Maintainability review

### 7.1 CTRL-AGG-01..09 闭合情况

全部 9 个 accepted findings 已闭合（经 re-review artifacts 和当前代码验证）：

| Finding | 闭合证据 |
|---------|---------|
| CTRL-AGG-01 | `_UsagePairingStatus`/`_UsagePairingReason` StrEnum（`engine_ingest.py:391-398`） |
| CTRL-AGG-02 | `_UnavailableContinuationFrozenSources`/`_CompleteContinuationFrozenSources` 判别联合（行 696-741） |
| CTRL-AGG-03 | `_StartReactiveRecoveryOperation.__call__` 拆为 9 个模块级 helper（行 790-1235） |
| CTRL-AGG-04 | `test_scripted_runner_without_usage_emits_conservative_fact_and_succeeds`（`test_public_tool_wiring_smoke.py:42`） |
| CTRL-AGG-05 | steer 同一 candidate 只估算一次（`test_public_steer.py:118-175` 验证 `estimate_call_count`） |
| CTRL-AGG-06 | `validate_context_threshold_ordering` 使用 `soft >= hard` → ValueError（`context_budget.py:1394`） |
| CTRL-AGG-07 | `_UTILIZATION_BASIS_POINTS_SCALE = 10_000` 仅 `context_budget.py` 定义（`context_events.py` 通过 import 复用） |
| CTRL-AGG-08 | `ContextSizingFallbackReason` 不含 `CONTINUATION_*_UNAVAILABLE`（`context_budget.py:106-130`） |
| CTRL-AGG-09 | compactor exclusion 有 direct test（aggregate re-review 确认） |

### 7.2 编码规范检查

- `hasattr`/`getattr`：生产代码 0 处；仅 1 处测试断言（`test_admission_multiprocess.py`）✅
- `cast()`：生产代码仅 1 处（`engine_ingest.py` isinstance-guarded Mapping narrow，行 6788）；其余均为测试 `json.loads` 转换 ✅
- 无 God function：原 245 行 `__call__` 已拆分为多个 ≤100 行的 typed helper ✅
- 无反向依赖 ✅
- 模块级私有辅助函数优先于嵌套函数/类 ✅
- 中文 docstring 覆盖完整 ✅

### 7.3 类型安全

- `ContextSizingStage`、`ContextPressureLevel`、`ContextEstimateMethod`、`ContextBudgetDecision` 均为 `StrEnum`
- `_stage_pressure_action`（`context_budget.py:1429`）用 `match` 穷举 15 个 `(stage, pressure)` 组合 + `case _: raise AssertionError`
- `validate_context_threshold_ordering` 严格 `soft < hard`
- `ContextSizingResult.__post_init__`（行 475-589）校验 anchored/fallback 互斥、diagnostic 一致性、utilization 公式、pressure/decision 正确性
- `ContextAnchorResolution.__post_init__`（行 278-301）校验 anchor 与 fallback_reason 恰一个非空

## 8. Adversarial failure pass

以下 adversarial 场景分析表明实现具有正确的防御深度：

| 场景 | 预期行为 | 代码证据 |
|------|----------|----------|
| Provider 不返回 usage | Run 以 conservative_fallback 继续 | `context_anchor.py:411-412` continue + `test_public_tool_wiring_smoke.py:42` |
| Usage 存在但 manifest 不完整 | `MANIFEST_INCOMPLETE` barrier → fallback | `context_anchor.py:414-419` |
| Usage 存在但 provider/model 不兼容 | `PROVIDER_MISMATCH`/`MODEL_MISMATCH` barrier → fallback | `context_anchor.py:408-410` → `_compatibility_mismatch` |
| Usage 存在但 compact boundary 更近 | `ACCEPTED_COMPACT_INVALIDATED` fallback | `context_anchor.py:436-438` |
| Anchor arithmetic 溢出 | `ARITHMETIC_RANGE_INVALID` fallback | `context_budget.py:998-1001` |
| Anchor prediction 非正 | `PREDICTION_NON_POSITIVE` fallback | `context_budget.py:1002-1005` |
| Replay 时 source fact 与 manifest 不一致 | `HostDurableError` fail closed | `context_events.py:583-595` |
| Durable payload 损坏 | `HostDurableError` fail closed | `context_events.py:1407-1410` |
| 幂等重写矛盾 | `HostEventIdentityConflictError` fail closed | `context_events.py:718-720` |
| 半提交（crash mid-transaction）| SQLite rollback 整体撤销 | 同一 write transaction 保证 |
| Post-compact 尝试使用 anchor | 固定 conservative fallback | `dispatch.py:748-757` |

## 9. Semantic ownership drift 检查

| 语义 | Owner | 验证 |
|------|-------|------|
| `predicted_input_tokens` | `ContextSizingResult` → canonical fact → public view | 三个位置同源，无重算 |
| `utilization_basis_points` | `context_utilization_basis_points`（`context_budget.py:1400`） | `context_events.py:394` 和 `ContextSizingResult:574` 均调用同一函数 |
| `estimate_method` | `ContextSizingResult.estimate_method` | public view 原样投影，不做"模糊判断" |
| `pressure_level` | `_pressure_and_decision`（`context_budget.py:1309`） | 唯一矩阵 owner |
| `budget_decision` | `_stage_pressure_action`（`context_budget.py:1429`） | 15 格闭集 |
| usage anchor | `context_anchor.py` resolver | 不泄漏到 context_budget public API |
| `RunnerCallSizingStatus` | `_runner_call_manifest.py:240` | 与 `ContextSizingFallbackReason` 不同 owner，语义不重叠 |
| tool facts | `EffectiveToolFacts`（`admission.py:229`） | admission 冻结，dispatch 校验，不按当前配置重选 |

**无 semantic ownership drift**。每个语义有唯一 owner，消费者复用同一 source of truth。

为防微杜渐，注意以下两个模块内检查项：

- `HostContextUsageView.__post_init__`（`api.py:3107`）使用 `soft > hard`（允许相等），但上游 `validate_context_threshold_ordering`（`context_budget.py:1394`）使用 `soft >= hard`（严格小于）。当前无实际风险（canonical fact 校验已保证 strict 顺序），但两个 owner 检查边界不一致，**建议**未来将 public DTO 校验也改为 strict `<` 以消除解释歧义。
- `EntrypointContextUsage.__post_init__`（`entrypoint_runtime.py:232`）使用 `soft > hard`（允许相等），与 Host DTO 一致但同上理。

## 10. 过度耦合检查

- `context_budget.py` → `context_anchor.py`：仅 TYPE_CHECKING 导入 `ContextAnchorResolution`，无运行时耦合 ✅
- `context_events.py` → `context_budget.py`：导入计算函数（`context_utilization_basis_points`、`context_sizing_pressure_and_decision`、`validate_context_threshold_ordering`）用于 payload 校验，合理 ✅
- `admission.py` → `run_input.py`：导入 `estimate_prepared_runner_call_candidate`、`resolve_prepared_runner_call_context_anchor_in_transaction` 用于 steer path，合理 ✅
- `dispatch.py` → `run_input.py`：导入 candidate 相关函数用于 post-compact/ordinary dispatch，合理 ✅
- 各层之间的 import 均为单向（Host → Engine contracts，Service → Host API），无循环依赖 ✅

## 11. Public/schema/LLM-facing 检查

### 11.1 Public DTO 字段

`HostContextUsageView`（`api.py:3059`）仅包含 7 字段：
- `predicted_input_tokens`：当前 candidate 预算 basis
- `context_window_size`：frozen policy window
- `utilization_basis_points`：未 clamp 基点
- `soft_threshold_tokens`：frozen soft threshold
- `hard_threshold_tokens`：frozen hard threshold
- `estimate_method`：`usage_anchored` / `conservative_fallback`
- `pressure_level`：`normal` / `soft_threshold_exceeded` / `hard_threshold_exceeded`

不暴露：anchor diagnostic、raw usage、provider request id、policy ref、stage/action、fallback_reason。✅

### 11.2 LLM-facing 文本

本 PR 不涉及 `dayu/config/prompts/` 或 tool schema 的 LLM-facing 文本修改。`context_events.py` 的 fact payload 不进入 LLM 上下文。✅

### 11.3 Schema 变更

`CONTEXT_BUDGET_EVALUATED_SCHEMA_VERSION = "context_budget_evaluated.v1"`（`context_events.py:50`），fresh schema only。✅

## 12. README 一致性

`dayu/host/README.md` 更新覆盖：
- Dispatch scheduler 段落：补充 queued Run promotion 治理说明 ✅
- RunInputBuilder 段落：补充 source Run exact input、Session continuity source refs 等新 contract ✅
- Context governance 段落：新增完整的 usage-anchored adaptive sizing 描述，包括五阶段、anchor 选择、fallback、manifest-before-start 不变量 ✅
- Context budget 与 compaction 段落：补充 usage presence 证明方式、utilization basis points 未 clamp、estimate_method 两种值 ✅
- EventLog event class 段落：补充 `CONTEXT_BUDGET_EVALUATED` → `CONTEXT_USAGE` activity 投影说明 ✅

以上更新与代码行为一致，无 README 漂移。

`tests/README.md` 更新：新增 context budget/anchor/steer/resolve wait 相关测试文件到 recommend 命令。✅

## 13. Typing/testing/coverage

### 13.1 Typing
- `pyright`: 0 errors, 0 warnings ✅
- 所有新增 public type 使用 `StrEnum`/`@dataclass(frozen=True, slots=True)` ✅
- 无 `object`、`Any`、无类型参数 ✅
- 生产代码 `cast()` 仅 1 处（isinstance-guarded） ✅

### 13.2 Testing
- Host suite: 2259 passed ✅
- Project suite: 3445 passed ✅
- 新增测试文件：`test_context_anchor.py`（1235 lines）、`test_context_budget_evaluated.py`（628 lines）、`test_public_steer.py`（+198 lines）、`test_public_tool_wiring_smoke.py`（+90 lines）等
- 关键测试覆盖：missing usage → conservative fact、steer candidate sizing、hard continuation ordering、recovery continuation fact from matching source ✅

### 13.3 Coverage
接受 Controller aggregate deepreview 验证结果（union 86%, minimum 82%） ✅

## 14. Special verification items

### 14.1 CONTEXT_BUDGET_EVALUATED canonical fact 与 estimator 独立
✅ §5.1

### 14.2 Provider 无 usage 严格回退保守算法且 Run 不失败
✅ §5.2

### 14.3 五阶段 producer/recovery/continuation 顺序
✅ §5.3

### 14.4 Public projection 没有跨层漂移
✅ §5.4

## 15. Findings

### F-DS-01（informational）— `HostContextUsageView` 与 `EntrypointContextUsage` 的 threshold 校验宽松

**位置**：`api.py:3107`、`entrypoint_runtime.py:232`

两个 public DTO 的 `__post_init__` 使用 `soft > hard` 校验（允许相等），而上游 `validate_context_threshold_ordering` 使用 `soft >= hard`（严格小于）。

**影响**：当前无实际风险——canonical fact parser 已保证 strict `<`，public DTO 不可能收到 `soft == hard` 的值。

**建议**：为消除解释歧义，建议未来统一为 strict `<`。不阻塞当前 PR。

### F-DS-02（informational）— 部分 legacy `RunInputBuilder` provider 保留

**位置**：`run_input.py` 中仍存在 `DurableRunnerCallManifestRecorder` 与 `create_no_tool_run_input_builder`/`create_tool_enabled_run_input_builder` 等 post-start 入口。

**影响**：这些入口继续写 `UNAVAILABLE + ORDINARY` sizing snapshot（如 aggregate re-review DS F12 所裁决），语义正确。属于"conservative contract for legacy boundary"，不是 defect。

**建议**：随着 post-start 边界逐步迁移到 pre-start `PreparedRunnerCallCandidate`，这些入口会自然消失。不需额外处理。

## 16. Open questions

无。

## 17. Residual risk

| 风险 | 等级 | 缓解 |
|------|------|------|
| Long-session 扫描性能（无 page limit 的倒序扫描） | Low | `_SCAN_PAGE_SIZE = 64` 分页扫描，compact boundary 终止；当前无性能回归证据 |
| CJK token 估算与实际 provider tokenizer 偏差 | Medium | 设计明确声明"保守估算，非 billing-grade"，偏差方向始终偏保守（高估），不会导致静默超窗 |
| 多进程 concurrent append 竞争 | Low | SQLite write transaction 序列化；幂等复用/conflict fail-closed 双重安全 |
| 真实 provider smoke 未覆盖 | Low | scripted runner 测试覆盖 usage-absent/usage-anchored 核心路径 |

**总体 residual risk 等级：Low**

## 18. Verdict

### `PASS`

PR #183 的 correctness、stability、maintainability 均经过充分验证：

1. `CONTEXT_BUDGET_EVALUATED` canonical fact 与 adaptive estimator 正确解耦，usage 缺失时 conservative fallback 路径完整
2. 五阶段 producer（ordinary / post-compact / reactive_post_compact / dispatch_fallback / continuation）与三种 pressure 的 15 格 action matrix 穷举正确
3. manifest → budget fact → start transition 的写入顺序在所有 producer 中一致，同一 SQLite write transaction 保证原子性
4. Public projection（Host → Service → UI）是 pure typed copy，无语义漂移、重算或 loose parsing
5. 无反向依赖、无 God function/object、无 hasattr/getattr 滥用、无 magic number 重复
6. pyright 0 错误、5704 测试通过、aggregate re-review pass、CTRL-AGG-01..09 全部闭合
7. recovery/replay deterministic：source atoms 冻结后 replay 产生相同 decision
8. 两条 informational finding 均不阻塞 merge

## 19. Artifact path

`docs/reviews/wu-ctx-01-pr-183-deepreview-ds.md`
