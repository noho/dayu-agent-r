# wu-cli-interactive-02 S5 implementation report

## 1. 结论

S5/F13 implementation 已在 accepted HEAD `ce7ef846f7b8aac2d0b942bb487819fe0210b746`、分支
`codex/interactive-oracle` 上完成，未 commit、未 push、未创建 PR。

实现前已确认原 20-file dirty set 的 owner 明确、无其它 dirty/untracked，且
`git diff --binary | shasum -a 256` 为冻结保护值
`d19605477fe3c284e5791f8c8bdfb8272bfaac8bbd1876d7d4518c7eff8beeb9`。实现严格保留该
dirty set，没有丢弃、重做或回退既有工作。

本实现把成功响应身份固定在 Engine 终结成功 Runner call 的 owner boundary，并由 Host compactor
prepared request、proposal、operation result 与 durable event 逐层同源透传。没有新增 default、optional
compatibility、config inference、manifest 反推或下游 fallback。

## 2. Owner 与契约实现

### 2.1 Engine owner

- 新增严格类型 `ProviderRequestIdAvailability` 与 `SuccessfulRunnerResponseIdentity`；provider/model
  必须非空，provider request id 必须与 `PRESENT` / `UNAVAILABLE` 严格配对。
- `_AsyncAgent` 只从当前 `AgentRunRequest.runner_spec`、当前 `_IterationState.request_identity` 与同一
  `RunnerDoneData.provider_request_id` 构造 identity。
- normal final、content-filter、无续写预算 LENGTH、length continuation 的最后一次成功 call、force-answer
  final 均透传实际终结 call identity；failed/cancelled/suspended 不伪造成功身份。
- `FinalAnswerData` 与 `EngineRunOutcomeFinalAnswer` 的 `response_identity` 均为 required typed field；package
  exports 同步收紧。

### 2.2 Host compactor 与 operation owner

- `CompactorProposal` 把 candidate 与成功 response identity 绑定；`ContextCompactor` 及所有 fake/custom
  compactor 按 typed proposal 迁移。
- `LLMContextCompactor` 校验 final identity 与同一个 prepared `AgentRunRequest` 的 Engine run、ordinary
  attempt/execution、effective provider/model 完全一致；LENGTH、parse、schema 等 post-success rejection
  保留该 identity，timeout/transport/Engine no-final 为 `None`。
- 每个 proposal attempt 在 provider call 前记录 manifest；accepted 与 rejected outcome 同时携带 Host
  operation id、Host attempt number、manifest reference、exact compactor Engine final identity。
- `CompactorProposalManifestReference` 移至 durable event owner `context_events.py`，解除
  `context_events -> compaction_operation -> durable schema -> api -> memory -> context_events` 循环，未使用
  lazy import 或 compatibility seam。

### 2.3 Durable schema owner

- `CONTEXT_COMPACTED.successful_response_identity` 为 required strict mapping，accepted proposal manifest ref /
  digest 均为 required non-null。
- `CONTEXT_COMPACTION_ATTEMPT_REJECTED.successful_response_identity` 为 required field：quality/hard-threshold
  rejection 必须为 mapping；cancellation 必须为 `null`；任何非 null identity 必须有 proposal manifest。
- identity 与 nested runner identity 使用 exact field set，canonical client correlation 重新校验；缺失、额外、
  改名、ordinary attempt/execution 与 operation/attempt/compactor-run 串线均 fail closed。
- durable identity 不含 endpoint、credential/ref、Authorization、headers、cookie、secret 或 provider
  request/response payload。

### 2.4 Mechanical closure 与两个 utils

- 完成冻结 33-file mechanical union 的所有 required constructor / typed-return / builder migration。
- `smoke_host_public_awaiting_entrypoint.py` 精确迁移 `FA × 1`。
- `smoke_host_public_conversation_memory_scenarios.py` 精确迁移 `FA × 1 / OA × 2`。
- 两个 utils 均使用 file-local required helper，从同一个 `AgentRunRequest` 取得 run/attempt/execution 与
  provider/model；synthetic single call 显式使用 iteration id、index 0、call 1、`UNAVAILABLE + None`。
  smoke 场景、provider assembly、分支、输出 marker 与 oracle 没有改变。

## 3. Exact changed files

### Production（13）

- `dayu/engine/__init__.py`
- `dayu/engine/agent.py`
- `dayu/engine/contracts/__init__.py`
- `dayu/engine/contracts/agent_run.py`
- `dayu/engine/contracts/engine_events.py`
- `dayu/engine/contracts/runner_identity.py`
- `dayu/host/compact_pipeline.py`
- `dayu/host/compaction.py`
- `dayu/host/compaction_operation.py`
- `dayu/host/context_events.py`
- `dayu/host/dispatch.py`
- `dayu/host/engine_ingest.py`
- `dayu/host/llm_compaction.py`

### Engine tests（7）

- `tests/engine/contracts/test_agent_run.py`
- `tests/engine/contracts/test_runner_identity.py`
- `tests/engine/test_agent_phase2.py`
- `tests/engine/test_agent_phase3_tool_call.py`
- `tests/engine/test_engine_event_contract.py`
- `tests/engine/test_package_exports.py`
- `tests/engine/test_smoke_async_agent_providers.py`

### Host tests/support（30）

- `tests/host/fake_compaction.py`
- `tests/host/public_smoke_support.py`
- `tests/host/recovery_support.py`
- `tests/host/stress_support.py`
- `tests/host/test_active_cancel_dispatch.py`
- `tests/host/test_compact_artifact_store.py`
- `tests/host/test_compact_material.py`
- `tests/host/test_compact_pipeline.py`
- `tests/host/test_compaction_cancellation_scope.py`
- `tests/host/test_compaction_contract.py`
- `tests/host/test_compaction_operation.py`
- `tests/host/test_compaction_terminal.py`
- `tests/host/test_context_compact_events.py`
- `tests/host/test_dispatch_scheduler.py`
- `tests/host/test_effective_execution_config.py`
- `tests/host/test_engine_ingest_mapping.py`
- `tests/host/test_import_boundary.py`
- `tests/host/test_llm_compaction.py`
- `tests/host/test_memory_projection.py`
- `tests/host/test_open_host_runtime.py`
- `tests/host/test_per_run_tool_selection.py`
- `tests/host/test_phase5_local_execution_integration.py`
- `tests/host/test_proactive_compaction_operation.py`
- `tests/host/test_public_compact_smoke.py`
- `tests/host/test_public_retry_replay.py`
- `tests/host/test_recovery_dispatch.py`
- `tests/host/test_run_input_builder.py`
- `tests/host/test_submit_followup_public_contract.py`
- `tests/host/test_watch_session_events.py`
- `tests/host/transient_stream_support.py`

### Service test 与 utils（3）

- `tests/service/test_entrypoint_runtime_interactive_path.py`
- `utils/smoke_host_public_awaiting_entrypoint.py`
- `utils/smoke_host_public_conversation_memory_scenarios.py`

本文件是本次唯一新增 implementation artifact。未修改 README、design、oracle、scenario 或 S6 docs。

## 4. Controller corrections 与 self-review

- `test_compact_pipeline.py`：`payload_input.source_boundary_refs` 与
  `accepted_attempt_number` 两条原断言已恢复到原测试函数内、helper 定义之前；断言语义未变且均可达。
- `test_dispatch_scheduler.py::_append_previous_compacted_event`：在 `_operation` 内只构造一个
  `compactor_agent_request` 与一个 `_HostCancellationToken`；identity 从该 request 构造，manifest 从同一
  request 的 `run_id` 绑定。没有 sibling evidence 重复构造。
- `test_proactive_compaction_operation.py::_rejected_payload`：orphan/incomplete/exhausted 仍为真实
  `quality_check_rejected` 语义，全部使用 file-local、同一显式 `AgentRunRequest` 派生的 typed identity +
  manifest；operation/attempt/compactor Engine run 一致。incomplete/exhausted 先 durable 记录 manifest；
  orphan 使用同源但故意未持久化的 typed reference，仍由原 owner 缺失语义判 invalid。
- `test_phase5_local_execution_integration.py`：最终 diff 只包含 response identity 必要 import、worker request
  state、`bind_dispatch(snapshot, request)` 与 final identity。六处 `run_queue_promotion -> refs = _refs ->
  drain_once/assert` 顺序与 HEAD 完全相同；没有 scheduler/timing 修复。
- AST/diff 审计：compact-pipeline 五条断言行均早于 helper；phase5 diff 不含 `refs`、`drain_once` 或其断言
  变更；dispatch 目标 helper 内 `AgentRunRequest` / token / identity construction / manifest run binding 均各
  一次；两个 utils helper 全部参数 required；新增 `type: ignore` 为 0，compatibility marker 为 0；
  `git diff --check` 通过。

## 5. Inventory proof

最终使用最新版 §10.5 五类 pattern 重跑并通过：

| Closure | Result |
|---|---:|
| `FinalAnswerData(...)` | 37 calls / 21 files |
| `EngineRunOutcomeFinalAnswer(...)` | 6 calls / 4 files |
| ContextCompactor typed-return | 7 files |
| identity union | 27 files |
| accepted builder | 8 calls / 6 files |
| rejected builder | 7 calls / 4 files |
| builder union | 8 files |
| exact overlap | 2 files |
| exact builder-only | 6 files |
| mechanical union | 33 files |

overlap 精确为 `test_compaction_operation.py`、`test_dispatch_scheduler.py`；builder-only 精确为计划冻结的
六文件。第二 amendment 新增 allowed delta 仍为 5，没有改称 6。

## 6. Tests 与类型检查

| Validation | Result |
|---|---|
| CLI focused | 605 passed |
| Service focused | 13 passed |
| Recovery focused | 116 passed |
| S5 compaction focused | 366 passed |
| Engine focused | 172 passed |
| Host focused（含 phase5） | 882 passed, 1 skipped, 6 baseline failures |
| CLI + Service integration | 1181 passed, 7 skipped |
| Host affected integration | 774 passed |
| Full `tests/engine tests/host` | 2955 passed, 1 skipped, 6 deselected, 6 baseline failures |
| Final owner self-review suite | 318 passed |
| Coverage run（排除已证明的单个 phase5 baseline-race 文件） | 2952 passed, 1 skipped, 6 deselected |
| `python -m pyright dayu/ tests/ utils/` | 0 errors, 0 warnings |

六个 full/focused failure 精确为 `test_phase5_local_execution_integration.py` 中的
`drain.dispatched == 0`。Controller 在 `/tmp/dayu-head.VaHH3v` 用 `git archive HEAD=ce7ef846` 的干净
基线独立复现首个测试同样失败；本实现也在 `/tmp/dayu-s5-head.3FtTiv` 复现相同 failure。按 Controller
裁决，这是 pre-existing scheduler race，不是 S5 regression，本次未改变 timing、scheduler 或断言顺序。

## 7. Per-file branch coverage

coverage data：`workspace/tmp/wu-cli-interactive-02-s5.coverage`；JSON：
`workspace/tmp/wu-cli-interactive-02-s5-coverage.json`。

| Production file | percent covered | lines | branches |
|---|---:|---:|---:|
| `dayu/engine/__init__.py` | 100.00% | 6/6 | 0/0 |
| `dayu/engine/agent.py` | 87.51% | 668/747 | 236/286 |
| `dayu/engine/contracts/__init__.py` | 100.00% | 14/14 | 0/0 |
| `dayu/engine/contracts/agent_run.py` | 97.87% | 85/86 | 7/8 |
| `dayu/engine/contracts/engine_events.py` | 97.48% | 221/224 | 11/14 |
| `dayu/engine/contracts/runner_identity.py` | 92.37% | 94/99 | 27/32 |
| `dayu/host/compact_pipeline.py` | 91.75% | 237/253 | 41/50 |
| `dayu/host/compaction.py` | 82.86% | 909/1029 | 237/354 |
| `dayu/host/compaction_operation.py` | 85.62% | 463/519 | 79/114 |
| `dayu/host/context_events.py` | 84.72% | 553/620 | 140/198 |
| `dayu/host/dispatch.py` | 84.05% | 1467/1670 | 325/462 |
| `dayu/host/engine_ingest.py` | 85.35% | 1556/1740 | 373/520 |
| `dayu/host/llm_compaction.py` | 88.96% | 316/342 | 95/120 |

全部受影响生产文件均达到单文件 `percent_covered >= 80`。

## 8. Smoke、registry 与安全扫描

- `memory-reactive-compact`：通过；覆盖 accepting compactor outcome 与 ordinary final。
- `memory-compact-fallback --pressure-mode auto`：通过；覆盖 rejecting compactor outcomes、manifest-present
  rejected attempts、fallback dispatch 与 ordinary final。
- awaiting 11-phase smoke：在 `run_accepted` 前失败于既有
  `callback_execution_port is required when callbacks are set`；clean HEAD archive 运行同样失败。该路径尚未
  到达本次 `FinalAnswerData.response_identity` 迁移点，且本文件 diff 只含冻结 identity 机械变更，因此分类为
  pre-existing smoke harness/public-contract drift，不在 S5 scope 内修复。
- registry 两个 JSON 均通过 `python -m json.tool`。五条冻结 pairwise row 均存在，且两处 precondition 均
  保留；它们的 `parameter:config:default` claim 仍存在，这是计划明确留给 S6 的 docs/registry 工作。本次
  docs diff 为 0。
- 对两个成功 memory smoke 与 awaiting workspace 的目标 EventLog、cold/hot payload descriptor、runner
  manifest、compaction/audit/tool-trace artifact 共扫描 276 个 JSON records：endpoint、credential/ref、
  Authorization、headers、cookie、secret、api key/ref、provider request/response payload key 命中 0；测试
  provider key与 S5 canary value 命中 0。
- 另对 697 个 JSON records 中的 6 个 durable success identity 做 exact nested schema 扫描：schema error
  0；identity 内敏感字段 0。

## 9. Residual risk / deferred evidence

1. phase5 六个 scheduler race 为 accepted HEAD 已有失败；Controller 已明确要求不在 S5 修复。
2. awaiting smoke 的 callback execution port 断裂在 clean HEAD 同样存在；修复会改变冻结 smoke 行为与
   S5 allowed delta，故只记录不修改。
3. registry 中五条 `parameter:config:default` claim 清理与 parser-generated inventory/readiness proof 属于
   S6；本次按要求不改 scenario/oracle/docs。
4. 真实 provider successful compaction evidence、行为项 29 与 G06 仍留 S6；deterministic smoke 不冒充该
   外部证据。

除上述已分类项外，未发现 S5 owner contract、mechanical closure、manifest binding、identity 串线、类型、
覆盖率或敏感信息残余风险。
