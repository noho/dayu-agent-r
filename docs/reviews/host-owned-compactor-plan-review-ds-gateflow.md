# Host-owned LLM context compactor public opener contract — Plan Review (AgentDS, Gateflow)

## 结论：pass-with-risks

计划动机成立、证据充分，架构边界与 owner 分配正确，slice 顺序与代码生成切入点明确。以下 residual risks 需要在实现阶段处置，但不构成 blocking reject。

---

## 1. 动机与严重性判断

**通过。** 动机被直接代码和设计真源双重证实，不是表面命名问题。

### 证据

| 泄漏点 | 当前代码证据 | 问题 |
|--------|-------------|------|
| `OpenHostOptions.compactor_baseline` | `dayu/host/api.py:1039` — `compactor_baseline: CompactorExecutionBaseline \| None` | Service-facing opener 接收 `ContextCompactor` instance |
| `CompactorExecutionBaseline.context_compactor` | `dayu/host/api.py:936` — `context_compactor: ContextCompactor \| None` | 核心泄漏：Service 可以构造并注入 Host governance internal port |
| 包根 export | `dayu/host/__init__.py:58,154` — 导出 `CompactorExecutionBaseline` | 误导为 stable public contract |
| LLM call 在 write transaction 内 | `dispatch.py:1063` — `candidate = compactor.compact(request)` 在 `_compact_before_dispatch` 的 write transaction callback 内 | 真实 LLM 调用持有 SQLite write lock |
| 同问题在 reactive path | `engine_ingest.py:1382` — `candidate = compactor.compact(request)` 在 `_compact_reactive_recovery` 的 write transaction callback 内 | 同上 |

### 严重性确认

计划将严重性评估为"中高"，理由是它不立即破坏 EventLog truth（因为 dispatch/ingest 仍由 Host 做 quality check 和 artifact 写入），但会破坏 public contract 长期边界。判断成立。

---

## 2. 架构边界检查

**通过。** Host governance ownership 收口方向正确。

### 通过项

- `LLMContextCompactor` 放入 `dayu/host/llm_compaction.py`，不作为 `dayu.runtime` 能力 — 正确。Runtime 不应理解 `CompactionRequest`/`CompactionCandidate`。
- `CompactorRunnerBaseline` 不包含 prompt、candidate builder、quality callback、repair callback — 正确。
- Service 不传 `policy_ref`、不传 `ContextCompactor` instance — 正确。
- Prompt/scene ownership 归 Host — 正确。
- Candidate 结构 owner 归 Host（LLM 只输出 summary 文本，refs/evidence/pinned patch 由 Host 构造）— 正确。
- Engine retry（provider transport）vs Host semantic repair（脏输出/candidate reject）区分明确 — 正确。

### 残余风险

**R1: HostEvent kind 映射未明确。** 计划写到 `CONTEXT_COMPACTION_REQUESTED` / `CONTEXT_COMPACTED` / `CONTEXT_COMPACTION_FAILED` 应 emit Service-facing HostEvent，repair attempt rejected / retry scheduled 可 emit diagnostic/progress HostEvent。但当前 `HostEventKind` 只有 `PROGRESS`/`SUCCEEDED`/`FAILED`/`CANCELLED`。`CONTEXT_COMPACTION_REQUESTED` 应该按 PROGRESS 还是新 kind 暴露，`CONTEXT_COMPACTION_FAILED` 是否映射到 Run FAILED，计划没有给出映射表。实现时若未对齐，会导致 public watch 无法区分 compact 进度与 Run 终态。

**验证：** 实现 Slice 4 时，检查 `_validate_host_event_terminal_payload` 和 `HostEventKind` 是否需要扩展（例如新增 `COMPACT_PROGRESS` 或把 progress 内部再区分），或确认当前 PROGRESS/SUCCEEDED/FAILED 已足够。

---

## 3. 事务边界检查

**通过，但这是最大实现风险点。** 计划精确识别了当前代码的事务边界问题。

### 当前代码中的问题

```python
# dispatch.py:979-1170 _compact_before_dispatch 是在 write transaction callback 内
# 执行的事实上全流程：
#   - line 1010-1015: append CONTEXT_COMPACTION_REQUESTED ✓
#   - line 1063: compactor.compact(request)  ← LLM call 在 write transaction 内 ✗
#   - line 1064-1170: quality check + artifact write + CONTEXT_COMPACTED ✓
```

同样问题存在于 `engine_ingest.py:1325-1463` 的 `_compact_reactive_recovery`。

### 计划方案

Slice 4 要求拆为三段：(1) transaction 内写 request + `CONTEXT_COMPACTION_REQUESTED`，(2) transaction 外 LLM call + semantic repair，(3) 新 transaction 内 recheck state + 写结果。方案正确。

### 残余风险

**R2: 三段拆分会显著改变 dispatch.py 和 engine_ingest.py 的控制流。** 当前 `_run_pre_start_governance` 是单个 `run_write` callback，compact 路径在 callback 内走完。拆分后需要：

- `_run_pre_start_governance` 在 compact decision 时写 request 后提交（不 compact inside transaction），返回 compact 待办摘要。
- `wake_queue_promotion` 的调用者在 transaction 外运行 compaction operation（含可能多次 LLM call 做 semantic repair）。
- 然后进入新的 write transaction 写结果。

当前 `wake_queue_promotion` (dispatch.py:567-614) 已经部分做了类似结构：governance 后 compact_accepted 路径在 transaction 外 catch up memory，再进入新 transaction start。这个模式可以扩展，但需要把 compact LLM call 从 `_compact_before_dispatch` 内部移到 `_run_pre_start_governance` 返回后的 transaction 外。

对 engine_ingest 同样需要重构 `_handle_context_compaction_requested`。

**建议：** 实现时优先把 `_compact_before_dispatch` 和 `_compact_reactive_recovery` 拆为 (1) write-request-only helper (2) transaction-external compact operation 函数 (3) write-result helper。不要试图保留"在 transaction 内完成"的同步调用便利。

---

## 4. EventLog / HostEvent 语义检查

**通过，但有明确缺口。**

### 通过项

- `CONTEXT_COMPACTION_REQUESTED`、`CONTEXT_COMPACTED`、`CONTEXT_COMPACTION_FAILED` 已有 typed payload builder 和 validator（`context_events.py`）。
- `CONTEXT_COMPACTION_ATTEMPT_REJECTED` 作为新 canonical fact 的设计语义明确：记录 operation id、attempt number、failure category、repairable、diagnostic refs、next policy decision。
- EventLog 不含 API key/headers/完整 prompt/provider payload 的约束在计划中正确传达。

### 残余风险

**R3: `CONTEXT_COMPACTION_ATTEMPT_REJECTED` 的 payload builder 和 validator 不在计划 scope 中。** 计划 Slice 4 step 7 描述了其 payload 语义，但 `context_events.py` 当前没有对应的 `build_context_compaction_attempt_rejected_payload`。实现时需要在 `context_events.py` 追加 builder + validator，并在 EventLog 测试中验证其必填字段。

**R4: 当前 `ContextBudgetPolicy` 没有 `max_compaction_attempts_per_operation` 字段。** 计划 Slice 3 step 1 会添加。当前 field 是 `max_proactive_compactions_per_run` 和 `max_reactive_compactions_per_run`（控制每个 Run 最多启动几个 compaction operation），新 field `max_compaction_attempts_per_operation` 控制一次 operation 内最多几次 LLM proposal（含第一次 + 后续 repair）。两个维度不同，需要清晰区分命名。

---

## 5. Slice 大小与实现可行性

**通过。** 六个 slice 划分合理、顺序正确。

- Slice 1 (API shape 收口) 是纯 breaking change，risk 低，可独立验证。
- Slice 2 (LLMContextCompactor) 是纯新增，不修改现有 governance 路径，可独立测试。
- Slice 3 (open_host 接线) 是连接点，依赖 Slice 1+2。
- Slice 4 (dispatch/ingest 事务边界) 最复杂。计划正确声明"Slice 1-3 必须作为同一 PR 连续变更完成，不接受可合并中间态"。
- Slice 5 (smoke 迁移) 和 Slice 6 (README 同步) 在功能完成后收尾。

### 残余风险

**R5: Slice 4 事务边界拆分可能与 Slice 1-3 的 API 变更耦合。** 如果 Slice 1-3 只改 API shape 和构造，dispatch/ingest 仍沿用 `context_compactor` 内部 seam 但尚未拆分 transaction，中间 PR 无法安全运行真实 LLM compact。计划已经注意到这点并要求 Slice 1-4 都必须在一个实现批次内完成。但作为 plan review 需要明确: 实现顺序应该把 Slice 1-3 先 commit（可编译、pyright 通过、单元测试通过），Slice 4 在同一个 PR 的后续 commit 中推进，而不是拿 Slice 1-3 单独开 PR。

---

## 6. 测试覆盖检查

**通过，覆盖意图完整。**

### 通过项

- Slice 2 `test_llm_compaction.py` 的 5 个测试命名精确覆盖 request shape、candidate mapping、空输出拒绝、refs/evidence 保留、runner retry policy 透传。
- Slice 4 事务边界测试 6 个命名精确：transaction 外 LLM 调用（proactive + reactive）、stale result、repair attempt reject、provider retry 不 emit HostEvent、policy 校验。
- 所有测试都要求 no-network（fake/monkeypatch），符合项目约束。

### 残余风险

**R6: `test_llm_context_compactor_uses_runner_retry_policy_without_owning_semantic_repair` 的测试方式未具体化。** `LLMContextCompactor` 内部调用 `run_agent_and_wait`，如何 monkeypatch `run_agent_and_wait` 来验证 "runner retry 行为由 Engine 层负责，compactor 不做 semantic repair"？如果 monkeypatch 太宽（替换整个函数），可能漏测 compactor 内部对 runner failure 的传播是否正确。建议用 fake `run_agent_and_wait` 注入 `LLMContextCompactor` 构造参数（如果接口允许）或 monkeypatch 后验证 `run_agent_and_wait` 调用参数中的 `RunnerSpec.max_retries` 是否来自 compactor 构造的 runner spec。

---

## 7. 不做事项审计

**通过。** 明确不做列表完整，没有发现遗漏的旧语义残留。

---

## 8. 实现审查聚焦（非阻塞）

以下项目是实现 agent 在逐 slice 推进时应额外注意的，不要求 plan 再修改：

1. `LLMContextCompactor.compact()` 当前 port 不接收 CancellationToken；plan 决定第一版不从 Service 传入。实现时需要在 compactor 内接 Engine runner timeout/retry 做上界控制，返回后 dispatch/ingest 必须 recheck durable Run/Attempt 状态。这个 recheck 逻辑的具体时机和 unreadable run 的 fail path 需要特别注意，防止 stale LLM 输出被误写入。

2. `CompactorRunnerBaseline` 是否需要除 `RunnerSpec` / `RunnerCallOptions` / `artifact_root` 之外的其他字段？当前设计是完整的，但需要确认 `context_budget_policy` 是否属于 constructor context（Host opts 已有 `context_budget_policy`，compactor 不需要重复持有）— 这已经正确处理。

3. `dayu/host/llm_compaction.py` 会 import `run_agent_and_wait` from Engine。需要确认 Engine 的 runner API 没有被 Host context governance 语义污染（不应是问题，因为计划只使用 Engine public runner API）。

4. `README.md` Slice 6 中提到的 manual smoke 描述修改应该注意：`utils/smoke_host_public_multiturn.py` 需要保留 DeepSeek runner `RunnerSpec`/`RunnerCallOptions` 的构造 logic（ordinary run 仍然需要），只删除 DeepSeek compactor adapter 部分。

---

## 风险汇总

| ID | 类别 | 描述 | 影响 |
|----|------|------|------|
| R1 | HostEvent 映射 | CONTEXT_COMPACTION_* 事件如何映射到 HostEventKind 未给出映射表 | 实现时需决策，可能影响 public watch 兼容性 |
| R2 | 事务边界 | dispatch/ingest 三段拆分会显著改变控制流，是最大实现复杂度 | 若拆分不当，回归风险高 |
| R3 | EventLog schema | CONTEXT_COMPACTION_ATTEMPT_REJECTED 的 payload builder/validator 缺少计划 | 实现时需对齐 context_events.py |
| R4 | Policy field | max_compaction_attempts_per_operation 需与 max_*_compactions_per_run 命名区分 | 命名混淆风险 |
| R5 | Slice coupling | Slice 1-4 耦合在事务边界拆分上，不能分开发 PR | 单 PR blast radius 较大 |
| R6 | 测试方案 | LLM compactor 单元测试的 monkeypatch 方式未具体化 | 测试可能漏覆盖 runner failure 传播 |

---

## 验证清单

实现完成后需确认：

- [ ] `dayu.host.__all__` 不导出 `CompactorExecutionBaseline`，导出 `CompactorRunnerBaseline`
- [ ] `OpenHostOptions.compactor_baseline` 改为 `compactor_runner_baseline: CompactorRunnerBaseline | None`
- [ ] `CompactorRunnerBaseline` 不含 `context_compactor`、`policy_ref`、prompt、candidate builder、repair callback
- [ ] `dayu/host/llm_compaction.py` 包含 `LLMContextCompactor(ContextCompactor)`，构造只接收 runner spec/options
- [ ] `open_host.py` 在 `CompactorRunnerBaseline` present 时构造 `LLMContextCompactor` 并注入 `HostLocalExecutionOptions.context_compactor`
- [ ] proactive compact 和 reactive compact 的 LLM 调用均在 write transaction 外
- [ ] `ContextBudgetPolicy.max_compaction_attempts_per_operation` 为正整数字段
- [ ] `CONTEXT_COMPACTION_ATTEMPT_REJECTED` payload builder 存在并有 typed payload contract
- [ ] runner HTTP retry 不 emit HostEvent
- [ ] manual smoke 和 public compact smoke 不实现 `ContextCompactor`
- [ ] `pyright` 0 errors；host tests 全量通过
- [ ] `README.md` 和 `dayu/host/README.md` 不再描述 Service 注入 `ContextCompactor`
