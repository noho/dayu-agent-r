# WU-CTX-01 Slice 1 Implementation Handoff

- status: `blocked`
- implement agent: `AgentCodex`
- accepted plan commit: `06c143f2492da063e0b96e67ff346b181be0d19e`
- slice: `Slice 1 — Exact candidate、estimator identity 与 manifest v2 direct pairing foundation`
- next entry point: 仅交回 Gateflow Controller 重新裁决；未进入 review、commit、push 或 PR

## 1. Blocker

实现已命中 accepted plan §8.2 的显式 stop condition：

> candidate refactor改变memory/evidence/LLM-facing内容而非只改变组装时点/复用方式。

直接运行 proactive compact 回归时，identity-free complete candidate 在 accepted
compact 前后仍保持相同 conservative size。为排除“当前输入本身不可压缩”的夹具
干扰，曾临时把 soft 场景改为“24 字符当前输入 + 600 字符历史输入”并加入只读 debug
观测；观测结果为：

- compact 前：`estimated_input_tokens=287`
- accepted compact 后重新 freeze exact candidate：
  `estimated_input_tokens=287`
- decision 前后均为 `compact_soft_threshold`
- 因 allow 条件不成立，未分配 Attempt identity，未写 ordinary manifest，也未 start

临时阈值、历史输入和 debug 改动已撤回，不留在当前 diff。

根因有同源代码证据：

1. `dayu/host/memory.py` 的 `CONTEXT_COMPACTED` projection 更新 summary/facts/anchors/
   intents 与 `latest_compaction_event_ref`，但不移除或替换此前
   `selected_recent_window`。
2. `dayu/host/run_input.py::_memory_messages` 无条件把整个
   `selected_recent_window` 渲染为 LLM messages。
3. pre-start candidate 又按 `memory.messages + protected raw tail` 组装上下文。
   因而 accepted compact 没有从 exact runner request 中移除已被 compact 覆盖的
   recent messages；post-compact exact sizing不会下降。

修正该问题至少需要在 memory projection owner 或 run-input 的 LLM projection
boundary 定义“哪些 pre-compact selected recent items 已被 compact 覆盖、哪些仅作为
protected raw tail 保留”。无论修改 `dayu/host/memory.py`，还是只在
`dayu/host/run_input.py` 过滤，它都会改变实际 LLM-facing messages / memory语义；
前者还越出 Slice 1 allowed production files。按用户 stop instruction，本 Agent
不得自行选择语义，因此停止。

当前 partial implementation 还会在 post-compact exact candidate 仍为 soft/hard 时
返回无 dispatch；Run 可停留在 accepted 状态。该行为不能作为完成结果提交。

## 2. Allowed scope 与 changed files

当前 Agent 修改的 production files 均位于 Slice 1 allowlist：

- `dayu/host/context_budget.py`
- `dayu/host/_runner_call_manifest.py`
- `dayu/host/run_input.py`
- `dayu/host/dispatch.py`
- `dayu/host/context_fallback.py`
- `dayu/host/compaction_operation.py`
- `dayu/host/engine_ingest.py`
- `dayu/host/durable/schema.py`

当前 Agent 修改的 tests 均位于 Slice 1 allowlist：

- `tests/host/test_dispatch_scheduler.py`
- `tests/host/test_durable_schema.py`
- `tests/host/test_engine_ingest_mapping.py`
- `tests/host/test_runner_call_hot_payload_contract.py`
- `tests/host/test_tool_trace_projection.py`
- `tests/host/test_tool_trace_queries.py`

本 artifact 是唯一新增文件：

- `docs/reviews/wu-ctx-01-slice-1-implementation-codex.md`

明确未修改：

- `dayu/host/durable/run_transition.py`：`git diff --exit-code` 为 0。
- README：用户明确禁止，本 slice 未修改。
- plan/review artifacts：未修改。
- `docs/host/issues-implementation-control.md`：worktree 中原有 Controller
  bookkeeping diff 为 `3 insertions / 3 deletions`；Agent 未编辑，必须继续保留。

## 3. 已完成但尚未通过最终 gate 的 owner/contracts

以下均为 partial implementation，尚未完成完整 focused tests、coverage、full pyright
与 review，不应直接 commit：

### 3.1 Estimator owner

- 冻结 estimator id/version/range contract。
- 增加 identity-free complete candidate adapter。
- conservative estimator digest改为由 candidate input、estimator contract与固定公式
  常量派生，不混入 policy threshold。
- 当前所有 sizing method 仍为 conservative fallback；未实现 anchor/signed delta。

### 3.2 Candidate 与 actual request owner

- 增加 identity-free `PreparedRunnerCallCandidate`。
- pre-start transaction 内冻结 messages、selected tool schemas、policy snapshot、
  request semantics、memory/compact/fallback refs与source cursor。
- 增加 Host-private candidate payload descriptor与严格 reload/validation。
- actual worker request改为读取 frozen candidate并绑定当前 Attempt runtime；不再调用
  material providers重新组装第二份 logical input。
- tool schema selection 与 Attempt-scoped runtime/executor handle 构造已分离。

### 3.3 Manifest v2 owner

- schema直接切到 `runner_call_input_manifest.v2`；无 v1 compatibility branch。
- `sizing_snapshot`支持严格 closed状态：
  `complete`、`unavailable`、`not_applicable`。
- ordinary budgeted allow写 complete conservative snapshot。
- `policy=None`写
  `unavailable(context_policy_unavailable)`。
- compactor proposal写 `not_applicable`。
- continuation按 projection、tool schema、policy、request semantics 四个 frozen source
  构造；缺失时按固定顺序写对应 closed unavailable reason。

### 3.4 Dispatch identity / transaction owner

- `PreparedRunnerCallCandidate` 不包含 Attempt/execution/dispatch identity。
- allow后才构造唯一 `StartGovernedRunInput`。
- manifest producer与 unchanged durable start transition消费同一个 start input。
- commit helper固定顺序为
  `RUNNER_CALL_INPUT_ASSEMBLED -> RUN_STARTED -> ATTEMPT_STARTED`。
- `BudgetedDispatchStart | NoBudgetDispatchStart`是 closed tagged union。
- soft/hard path不生成 manifest或 Attempt identity。
- private `_StartCandidateCasMissRollback`请求整笔 transaction rollback；
  low-level `CAS_LOST`仍保留 `HostDurableError`传播边界。
- candidate freeze 前先做有明确 EventLog upper bound 的 memory catch-up。

### 3.5 Usage direct pairing owner

- 删除 `_estimate_usage_observation_input`。
- usage ingest只通过 accepted exact iteration link读取 strict v2 manifest。
- pairing projection记录 manifest/link/input digest/observation digest。
- `provider_request_id`不参与 pairing predicate。
- diagnostic context pressure只使用 manifest内 conservative estimate，不从当前 policy
  或 `USER_INPUT_ACCEPTED.display_text`重建。

未实现且未越界：

- `CONTEXT_BUDGET_EVALUATED`
- Host/Service public context usage
- context anchor resolver
- signed-delta sizing
- Issue #119 Tool Trace correlation变更

## 4. 当前 event/state/data flow

已实现的 intended allow flow：

```text
bounded memory catch-up
  -> BEGIN IMMEDIATE
  -> read startable Run + freeze identity-free exact candidate
  -> conservative sizing
  -> allow 后生成一次 StartGovernedRunInput
  -> persist frozen candidate payload
  -> RUNNER_CALL_INPUT_ASSEMBLED(v2)
  -> unchanged start transition consumes same input
  -> RUN_STARTED
  -> ATTEMPT_STARTED
  -> dispatch row
  -> COMMIT
  -> worker reloads and validates frozen candidate
  -> AgentRunRequest only binds Attempt runtime
```

`policy=None`走 `NoBudgetDispatchStart`，manifest sizing为 unavailable，且不产生 sizing
fact/activity。soft/hard在 allow identity分配前结束，因此无 manifest/Attempt identity。

blocked data flow：

```text
accepted compact
  -> memory projection保留pre-compact selected_recent_window
  -> exact candidate继续渲染相同recent messages
  -> post-compact conservative sizing不下降
  -> decision仍为soft/hard
  -> no identity / no start
```

## 5. Commands 与结果

### 5.1 Tests

已运行的关键 dispatch focused命令：

```bash
source .venv/bin/activate
pytest -q tests/host/test_dispatch_scheduler.py --maxfail=20 --tb=short
```

结果：`77 passed, 20 failed`，到达 `--maxfail=20` 后停止。失败包含两类：

- 已确认的 blocker：accepted compact后exact candidate仍非allow，导致预期 start 的
  proactive/post-compact tests无 Attempt。
- 尚未收敛的 partial implementation / fixture migration：
  pre-start helper接口、旧 memory catch-up断言、历史 compact fixture lineage等。

为定位 blocker另运行：

```bash
source .venv/bin/activate
pytest -q \
  tests/host/test_dispatch_scheduler.py::test_pre_start_governance_soft_threshold_compacts_before_attempt \
  --log-cli-level=DEBUG --tb=short
```

结果：`1 failed`；确认 initial candidate触发soft、compact accepted、post-compact没有
dispatch。

临时 direct instrumentation probe运行：

```bash
source .venv/bin/activate
pytest -q \
  tests/host/test_dispatch_scheduler.py::test_pre_start_governance_soft_threshold_compacts_before_attempt \
  --log-cli-level=DEBUG --tb=short
```

结果：`1 failed`；同一运行数据明确显示 compact前后均为 `287` tokens。探测代码随后
撤回。

此前已做过 scoped production pyright与部分 targeted tests，但本 blocked artifact
不把它们视为 completion evidence；完整14文件 Slice 1 focused suite未通过、未重跑。

### 5.2 Type check

- scoped production pyright：此前逐步检查返回 0。
- full command
  `python -m pyright dayu/ tests/ utils/`：因命中 stop condition，未执行。
- 结论：不能声明 full pyright通过。

### 5.3 Coverage

因 focused tests未通过且命中 stop condition，未生成可接受的 coverage data。
所有 changed production Python files的 per-file line coverage状态均为
`not measured / blocked`，不能声明任何文件达到 `>=80%`：

- `_runner_call_manifest.py`
- `compaction_operation.py`
- `context_budget.py`
- `context_fallback.py`
- `dispatch.py`
- `engine_ingest.py`
- `run_input.py`
- `durable/schema.py`

### 5.4 Diff 与 static audits

- `git diff --check`：通过。
- `git diff --exit-code -- dayu/host/durable/run_transition.py`：通过，零 diff。
- `rg -n "runner_call_input_manifest\\.v1" dayu tests`：零命中。
- changed production files上的 `hasattr(`/`getattr(` audit：零命中。
- `dayu/engine`导入`dayu.host`：零命中。
- `dayu/service`代码导入`dayu.host.durable`：零命中；仅README治理文字命中。
- `_estimate_usage_observation_input`：零命中。
- plan给出的组合
  `USER_INPUT_ACCEPTED.*display_text` audit仍命中合法 memory fixtures、
  read-model说明和 dispatch input parser；未发现 usage estimator consumer，但该组合
  grep本身不是严格零命中查询。
- direct manifest/link consumer列表已覆盖：
  `_runner_call_manifest.py`、`run_input.py`、`engine_ingest.py`、
  `compaction_operation.py`、`proactive_compaction.py`、`tool_trace.py`、
  `durable/tool_trace.py`、`lifecycle_events.py`、`durable/schema.py`及对应tests/docs。
- §7.4 semantic ordering integration suite尚未完成，不能声明 audit gate通过。

## 6. README decision

用户明确禁止本 Slice 修改 README，因此零README diff。由于实现被blocked且不存在
可交付contract，未执行 README 内容同步；该决定不等价于 Slice完成后的README audit。

## 7. Stop conditions / findings

- `BLOCKING`：exact post-compact candidate无法在不改变 memory/LLM-facing projection
  的前提下体现accepted compact带来的输入收缩。
- `BLOCKING`：一种修复路径需要修改allowlist外的 `dayu/host/memory.py`。
- `BLOCKING`：另一种路径虽可只改allowlist内 `run_input.py`，仍会改变实际
  LLM-facing messages，明确命中 stop condition。
- 未发现必须修改 `run_transition.py`、transaction runner、Engine Host-policy语义、
  Service public contract或Issue #119 correlation的证据。

Controller需要裁决以下语义 owner后才能恢复实现：

1. accepted compact是否拥有“覆盖并从future runner input移除哪些
   selected_recent_window items”的明确 contract；
2. 该contract owner位于 durable memory projection，还是 run-input LLM projection；
3. protected recent floor与compact覆盖范围如何唯一组合，避免 memory messages与
   protected raw tail双计；
4. post-compact exact sizing仍为soft/hard时，Run应fail closed、进入fallback，还是
   允许新的治理循环。

## 8. Residual risks

- 当前代码是未完成 partial implementation，不应commit。
- post-compact soft/hard可能让accepted Run无dispatch且无terminal transition。
- private precondition miss与low-level CAS_LOST的零孤立payload/event/state测试尚未完成。
- strict v2的v1/unknown/partial rejection matrix尚未补齐。
- continuation四类 frozen-source unavailable矩阵尚未补齐。
- exact candidate与actual `AgentRunRequest`全atom同源、无双计断言尚未完整。
- policy-none无sizing fact/activity的owner-level集成断言尚未完整。
- usage missing/mismatch/ambiguous direct pairing矩阵尚未完整。
- Tool Trace/public stream/projection/recovery/outbox/terminal ordering integration尚未完整。
- full pyright、14-file focused suite与逐文件coverage均未完成。

## 9. Controller handoff

请 Controller先裁决上述 compact覆盖语义与owner/scope。若允许改变LLM-facing memory
projection或扩展production allowlist，应形成新的明确contract与测试期望后再恢复
Slice 1 implementation。若不允许，则当前 accepted plan中“post-compact exact
candidate继续完成dispatch”的目标与现有memory/request语义不能同时满足。

本 Agent未修改control doc，未进入review，未commit、push或创建PR。
