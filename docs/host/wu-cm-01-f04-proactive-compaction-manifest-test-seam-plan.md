# WU-CM-01-F04 Proactive Compaction Manifest-producing Test Seam Closeout Plan

## Goal / Motivation / Success Signal

目标：关闭 WU-CM-01 后遗留的 Host proactive scheduler 测试 seam，使 proactive compaction tests 使用能产出 durable proposal manifest ref / digest 的 deterministic prepared compactor，同时保持生产 fail-closed guard 不变。

动机成立。当前失败不是 WU-TOOLS provider migration 的 provider 迁移问题，也不是生产 guard 过严；直接根因是测试 seam 仍使用只返回 compact candidate 的 legacy `FakeContextCompactor`，未走 `CompactorProposalPreparedCompactor` 路径，因此 `run_compaction_operation` 无法为 accepted/rejected attempt 带出 proposal manifest reference。生产 `dispatch.py` 在写 accepted `CONTEXT_COMPACTED` 前要求 manifest ref / digest，是当前 contract 的正确 fail-closed 行为。

成功信号：

- `tests/host/test_dispatch_scheduler.py` 中 proactive compact 相关 focused tests 不再因 `accepted compaction is missing proposal manifest ref` 失败。
- accepted `CONTEXT_COMPACTED` payload 直接断言 `accepted_proposal_manifest_ref` 以 `runner-call-manifest:` 开头，且 `accepted_proposal_manifest_digest` 为非空字符串。
- rejected `CONTEXT_COMPACTION_ATTEMPT_REJECTED` payload 直接断言 `proposal_manifest_ref` / `proposal_manifest_digest`。
- implementation 前已语义枚举 `tests/host/test_dispatch_scheduler.py` 中所有 proactive path 注入 compactor 的使用点，并按 accepted compact、rejected attempt、failed/stale/fallback 分类处理；不能只搜索 `context_compactor=FakeContextCompactor()` 字面量。
- proactive scheduler broad validation 中 compact 相关测试恢复有效信号；若后续仍有非 manifest seam failure，单独归因给后续 owner。
- pyright 0 errors，不新增或扩散类型错误。

## First-principles Judgment and Direct Code Evidence

第一性原理判断：

- accepted compact event 是 durable canonical fact。若无法证明 accepted candidate 对应哪次 durable proposal manifest，Host 后续 trace/audit/memory rebuild 无法同源追溯；因此生产必须 fail closed。
- 测试 seam 的责任是模拟当前 production contract 的 compactor 能力，不应通过放宽 `dispatch.py` 或给 legacy fake 增加兼容 wrapper 来绕过 contract。
- proactive 与 reactive 都由 Host 执行 compaction operation；reactive tests 已有 prepared manifest seam，proactive scheduler tests 应对齐同一 contract。

直接证据：

- `dayu/host/dispatch.py:1264`-`1269` 在 accepted proactive compact 写入前调用 `_required_compactor_manifest_ref(result)` 和 `_required_compactor_manifest_digest(result)`。
- `dayu/host/dispatch.py:1648`-`1671` 将 `accepted_proposal_manifest_ref` / `accepted_proposal_manifest_digest` 写入 `CONTEXT_COMPACTED` payload。
- `dayu/host/dispatch.py:1982`-`2023` 将 `rejected.proposal_manifest_ref` / `rejected.proposal_manifest_digest` 写入 proactive `CONTEXT_COMPACTION_ATTEMPT_REJECTED` payload。
- `dayu/host/dispatch.py:3734`-`3759` 对 accepted result 缺 manifest ref / digest 抛出 `RuntimeError`，这是生产 fail-closed guard。
- `dayu/host/compaction_operation.py:749`-`784` 只有 compactor 实现 `CompactorProposalPreparedCompactor` 时才会 prepare、record manifest，并把 manifest reference 绑定到 proposal attempt；legacy `compact()` 路径 `proposal_manifest_reference=None`。
- `tests/host/test_dispatch_scheduler.py:536`-`559` 的 `_RequestCapturingCompactor` 仍只调用 `FakeContextCompactor().compact()`，不会产出 manifest。
- `tests/host/test_dispatch_scheduler.py:403`-`559` 的 `_TransactionReadableCompactor`、`_StaleMutatingCompactor`、`_RaisingCompactor`、`_QualityRejectOnceCompactor`、`_RequestCapturingCompactor` 均只实现 legacy `compact()` seam；其中只有会写 accepted/rejected manifest event 的 proactive path 需要迁移。
- `tests/host/test_dispatch_scheduler.py:3630`、`3773`、`4341` 等 proactive accepted tests 直接注入 `FakeContextCompactor()`，与当前 accepted manifest contract 不匹配。
- `tests/host/test_compaction_operation.py:490`-`545` 和 `tests/host/test_engine_ingest_mapping.py:273`-`333` 已有 prepared manifest compactor seam 示例。
- `tests/host/test_engine_ingest_mapping.py:631`-`656`、`784`-`810` 已经在 reactive accepted/rejected event 中直接断言 manifest ref / digest。
- 总控文档 `docs/host/issues-implementation-control.md:544`-`570` 将本 work unit 定义为 test seam closeout，明确不放宽 production guard。

## Design Alignment

Host 设计对齐：

- `docs/host/design.md:3225`-`3238` 定义 proactive trigger 是 dispatch Attempt 前的 Host governance：先写 `CONTEXT_COMPACTION_REQUESTED`，事务外执行 bounded compaction operation，再写 `CONTEXT_COMPACTED` 或 `CONTEXT_COMPACTION_FAILED`，随后才 rebuild request 并 dispatch Engine。
- `docs/host/design.md:3263`-`3266` 要求 compact events 记录 operation、attempt、quality/budget/diagnostic 等 durable 信息；当前 manifest ref / digest 是 WU-CM-01 后用于追溯 proposal runner call 的 durable 引用。
- `docs/host/design.md:3268`-`3275` 要求 compact 不改写历史 EventLog、fallback 不提交 `CONTEXT_COMPACTED`、compact 有 policy 上限。本计划只修测试 seam，不改变这些生产不变量。

Engine 设计对齐：

- `docs/engine/design.md:414`-`423` 明确 Engine 不做 proactive threshold compaction、Host budget policy 或 compact/retry；Engine 只在 provider overflow 时发出 reactive compaction request 并以 recoverable failure 收口。
- 因此本 work unit 不应修改 Engine contract、Engine state machine 或 provider behavior。

## Non-goals / Scope Boundary

非目标：

- 不修改 `dayu/host/dispatch.py` 的 accepted compact guard。
- 不新增生产 compactor implementation。
- 不为 `FakeContextCompactor` 增加兼容 wrapper / facade，也不让旧 fake 自动伪造 manifest。
- 不重开 WU-TOOLS provider migration，不处理 Fins/Web/Doc tools。
- 不调整 schema、EventLog payload builder、公有接口或生产状态机。
- 不 commit / push / PR / merge。

本 plan gate 只允许写本 artifact。Implementation gate 计划只触碰 tests，优先限定在 `tests/host/test_dispatch_scheduler.py`；如实现时发现必须跨文件抽取 shared test helper，应先停下交给总控裁决。

## Affected Files / Modules

Plan gate 已写：

- `docs/host/wu-cm-01-f04-proactive-compaction-manifest-test-seam-plan.md`

Implementation gate 预计修改：

- `tests/host/test_dispatch_scheduler.py`

Implementation gate 预计只读/验证：

- `dayu/host/dispatch.py`
- `dayu/host/compaction_operation.py`
- `tests/host/test_compaction_operation.py`
- `tests/host/test_engine_ingest_mapping.py`
- `docs/host/design.md`
- `docs/engine/design.md`
- `docs/host/issues-implementation-control.md`
- `tests/README.md`

## Contract / Schema / State-machine / Public-interface Changes

无 contract 变更。

无 schema 变更。

无生产 state-machine 变更。

无 public interface 变更。

本 work unit 只让 proactive scheduler 测试 seam 实现当前已存在的 prepared compactor capability，并补齐 event payload assertions。

## Implementation Decisions

1. 在 `tests/host/test_dispatch_scheduler.py` 内新增一个私有 deterministic prepared manifest compactor，例如 `_PreparedManifestProactiveCompactor`。
2. 该 helper 显式实现 `prepare_compactor_proposal_run_input(...)` 与 `run_prepared_compactor_proposal(...)`，从而触发 `run_compaction_operation` 的 manifest recorder 路径。
3. helper 不修改、不继承扩展 `FakeContextCompactor` 的 manifest 行为；只在 `run_prepared_compactor_proposal` 中复用 `FakeContextCompactor().compact(...)` 生成 deterministic vNext candidate。
4. `prepare_compactor_proposal_run_input` 使用 `conversation_compact_input_vnext_from_material_pack(request.material_pack)`、`CompactorProposalRunInput`、`runner_role_sequence_digest` 构造 stable prepared input；`AgentRunRequest` 使用测试内 `_runner_spec()`、`RunnerCallOptions(...)`、`_agent_policy(False)`、`NoToolExecutor()` 和 system/user 两条 messages。
5. helper 可带 `fail_run: bool = False`；为 rejected test 模拟 proposal run 失败。失败必须发生在 prepared manifest record 之后，才能验证 rejected payload 的 manifest ref / digest。
6. `_RequestCapturingCompactor` 改为继承或组合该 prepared helper，同时保留 `requests: list[CompactionRequest]` 捕获能力；捕获发生在 prepare 阶段，因为 proactive operation 的 typed request 已在此时冻结。implementation 前必须先 grep `_RequestCapturingCompactor` 全部使用点；在 proactive accepted path 中归入 accepted migration slice，不能留作模糊 residual。
7. `_QualityRejectOnceCompactor` 保留其“第一次返回带 invalid diagnostic candidate，第二次返回合法 candidate”的业务语义，但迁移到 prepared helper 路径，确保第一次 quality rejection 的 rejected event 与第二次 accepted event 都有 manifest。第一次 rejected payload 的 manifest 断言是本 work unit 新增覆盖，不是修复既有断言。
8. `_TransactionReadableCompactor` 必须显式迁移到 prepared helper 路径，并保留“compactor 调用期可开启独立读事务读取 Run”的原测试语义。可通过在 specialized compactor 的 `run_prepared_compactor_proposal(...)` 中执行现有 `transaction_runner.run_read(...)` 检查后再复用 fake compact candidate 实现。
9. `_StaleMutatingCompactor` 明确不迁移。该 test 期望 `CONTEXT_COMPACTED` 为 0，Host stale check 在 accepted guard 前收口为 `CONTEXT_COMPACTION_FAILED`，不会触发 accepted manifest ref/digest guard；迁移反而会额外写 proposal manifest event，干扰 stale failure 语义。
10. `_RaisingCompactor` 所有使用点必须先 grep。若仅 proactive rejected test 使用，则用 prepared helper 的 `fail_run=True` 或等价 prepared failure 替代纯 `compact()` 抛错路径，使 failure 发生在 manifest record 之后；这是有意的 test 语义升级，用于覆盖 post-manifest proposal failure rejected payload，不是把 proposal failure 伪装成 quality rejection。
11. 直接注入 `FakeContextCompactor()` 的 proactive compact accepted tests 改为注入 `_PreparedManifestProactiveCompactor()`。不触碰不经过 compactor、明确在 compaction 前 fail closed、reactive-only，或 fallback/no-compactor 的用例。

## Small Implementation Slices

### Slice 0: implementation 前语义枚举 proactive compactor 使用点

Allowed files/modules:

- 只读 `tests/host/test_dispatch_scheduler.py`

Exact actions:

- 运行或等价执行以下枚举，不能只搜索 `context_compactor=FakeContextCompactor()`：

```bash
rg -n "_RequestCapturingCompactor|_TransactionReadableCompactor|_StaleMutatingCompactor|_RaisingCompactor|_QualityRejectOnceCompactor|context_compactor=|FakeContextCompactor\\(" tests/host/test_dispatch_scheduler.py
```

- 对每个使用点按实际 test 语义分类：
  - accepted proactive compact：期望写 `CONTEXT_COMPACTED`，必须迁移到 manifest-producing prepared seam，并补 accepted payload manifest assertions。
  - rejected proactive attempt：期望写 `CONTEXT_COMPACTION_ATTEMPT_REJECTED`，必须迁移到 manifest-producing prepared seam，并补 rejected payload manifest assertions。
  - stale/fail-before-compact/fallback/no-compact：不因 accepted manifest guard 失败，除非该 test 本身需要 asserted rejected manifest，否则不迁移。
  - reactive path：不纳入本 work unit，除非 focused validation 证明同源 manifest seam failure。

Current inventory that must be confirmed before editing tests:

- accepted proactive compact:
  - `test_pre_start_governance_soft_threshold_compacts_before_attempt`：direct `FakeContextCompactor()`。
  - `test_proactive_compaction_uses_selected_material_not_session_start_range`：`_RequestCapturingCompactor`。
  - `test_proactive_material_pack_not_larger_than_ordinary_material_for_same_view`：`_RequestCapturingCompactor`。
  - `test_wake_queue_promotion_uses_tracked_async_promotion_task`：direct `FakeContextCompactor()`。
  - `test_proactive_compaction_calls_llm_outside_write_transaction`：`_TransactionReadableCompactor`，必须保留独立读事务语义。
  - `test_multi_turn_proactive_compact_feeds_subsequent_run_input`：direct `FakeContextCompactor()`。
- mixed rejected then accepted proactive compact:
  - `test_proactive_compaction_retries_quality_rejection_before_accept`：`_QualityRejectOnceCompactor`，第一次 quality rejection 与第二次 accepted 都必须有 manifest assertions。
- rejected proactive attempts:
  - `test_compaction_repair_attempt_rejection_is_recorded_in_eventlog`：`_RaisingCompactor`。先 grep 所有 `_RaisingCompactor` 使用点；若只有此处使用，迁移为 prepared post-manifest failure。
- excluded:
  - `test_compaction_stale_result_does_not_write_compacted_event`：`_StaleMutatingCompactor`，不迁移，理由是该 test 期望 `CONTEXT_COMPACTED == 0` 且 stale check 在 accepted guard 前写 `CONTEXT_COMPACTION_FAILED`。
  - `test_pre_start_governance_proactive_count_limit_blocks_second_compact`、`test_pre_start_governance_corrupted_compact_count_fails_closed`：direct `FakeContextCompactor()` 但在 compact operation 前 fail closed，不触发 manifest guard。
  - reactive overflow/recovery tests：不是本 proactive seam closeout 范围。

Invariants:

- 如果 grep 发现上述清单外还有 proactive accepted/rejected compactor injection，必须归入 Slice 2 或 Slice 3，而不是留作 residual risk。
- 如果 `_RequestCapturingCompactor` 或 `_RaisingCompactor` 有非 proactive accepted/rejected 使用点，先按使用点语义决定是否需要拆分 helper；不能用一次迁移改变无关 test 的 failure 时序。

### Slice 1: 新增 proactive prepared manifest test seam

Allowed files/modules:

- `tests/host/test_dispatch_scheduler.py`

Exact changes:

- 补充 imports：
  - 从 `dayu.engine.contracts.messages` 增加 `SystemMessage`。
  - 从 `dayu.host.compact_material` 导入 `conversation_compact_input_vnext_from_material_pack`。
  - 从 `dayu.host.compaction_operation` 导入 `CompactorProposalRunInput`、`runner_role_sequence_digest`。
- 优先复用测试文件现有语义 digest 常量 `_CALL_CONTEXT_DIGEST` 作为 prepared input 的 stable digest；若实现时确认没有合适常量，再新增语义明确的模块级私有 digest 常量，禁止内联魔法 digest 字符串。
- 新增 `_proposal_compactor_agent_request(...)` 私有 helper，返回 deterministic `AgentRunRequest`。
- 新增 `_PreparedManifestProactiveCompactor` 私有类：
  - `__init__(*, fail_run: bool = False)` 保存 `fail_run`、`calls`、`prepared_requests`。
  - `prepare_compactor_proposal_run_input(...)` 记录 request，构造 `CompactorProposalRunInput`。
  - `run_prepared_compactor_proposal(...)` 增加 `calls`，`fail_run=True` 时抛 `RuntimeError("prepared proposal failed")`；否则调用 `FakeContextCompactor().compact(self.prepared_request, prepared_input.agent_request.cancellation_token)` 或等价保存的 latest request。

Call paths:

- `HostDispatchScheduler._execute_proactive_compaction`
- `run_compaction_operation`
- `_run_compactor_proposal_attempt`
- `_PreparedManifestProactiveCompactor.prepare_compactor_proposal_run_input`
- `DurableCompactorProposalManifestRecorder.record_compactor_proposal_manifest`
- `_PreparedManifestProactiveCompactor.run_prepared_compactor_proposal`

Invariants:

- 不绕过 `run_compaction_operation` 的 recorder。
- prepared `compaction_request_digest` 必须等于 `request.digest()`。
- `role_sequence_digest` 从真实 prepared messages role sequence 计算。
- helper 只在测试文件内可见，不成为生产或通用 fake 的兼容入口。
- `CompactorProposalPreparedCompactor` 是 runtime-checkable protocol；helper 方法签名、参数名、返回类型必须严格对齐协议，否则 `isinstance(compactor, CompactorProposalPreparedCompactor)` 会走 legacy `compact()` 路径。

Tests:

- Slice 1 后先运行至少一个 focused accepted proactive test，预期不再触发 missing manifest ref。

### Slice 2: 迁移 accepted proactive compact tests 并补 manifest assertions

Allowed files/modules:

- `tests/host/test_dispatch_scheduler.py`

Exact changes:

- 将语义枚举中期望写 `CONTEXT_COMPACTED` 的 proactive tests 改为 `_PreparedManifestProactiveCompactor()` 或迁移后的 specialized compactor：
  - `test_pre_start_governance_soft_threshold_compacts_before_attempt`
  - `test_proactive_compaction_uses_selected_material_not_session_start_range`
  - `test_proactive_material_pack_not_larger_than_ordinary_material_for_same_view`
  - `test_wake_queue_promotion_uses_tracked_async_promotion_task`
  - `test_proactive_compaction_calls_llm_outside_write_transaction`
  - `test_multi_turn_proactive_compact_feeds_subsequent_run_input`
- `_RequestCapturingCompactor` 使用点先 grep 全量确认；上述两个 proactive accepted tests 归入本 slice，迁移后仍断言 captured `CompactionRequest` 的 selected material、material refs、material pack 大小语义。
- `_TransactionReadableCompactor` 显式归入本 slice。迁移后保留 `compactor.calls == 1` 与独立读事务可读 Run 的断言语义；不要把它降级为普通 `_PreparedManifestProactiveCompactor`。
- 不迁移 `_StaleMutatingCompactor`。
- 在 accepted tests 中读取 latest `CONTEXT_COMPACTED` payload，断言：
  - `accepted_proposal_manifest_ref` 是 `str`。
  - `accepted_proposal_manifest_ref.startswith("runner-call-manifest:")`。
  - `accepted_proposal_manifest_digest` 是非空 `str`。
- `RUNNER_CALL_INPUT_ASSEMBLED` count 只能作为 conditional assertion：先在 focused accepted test 中验证该 event 确实由 durable recorder 写入，且不会引入脆弱计数；只有验证成立后才加入 count 断言。核心验收仍是 `CONTEXT_COMPACTED` payload 的 manifest ref/digest。

Call paths:

- proactive run queue promotion / wake queue promotion
- `_execute_proactive_compaction`
- `_append_compacted_event`
- `build_context_compacted_payload`

Invariants:

- event order 断言保持不变：`CONTEXT_COMPACTION_REQUESTED` before `CONTEXT_COMPACTED` before `RUN_STARTED` before `ATTEMPT_STARTED`。
- accepted manifest assertions 不能替代原有状态机、attempt count、run status assertions。
- 不修改 failure/fallback tests 中无 compactor 或 fail-closed 的业务预期。

Tests:

- Focused accepted tests 应证明 `CONTEXT_COMPACTED` payload manifest fields 存在且格式正确。

### Slice 3: 迁移 rejected proactive compact seam 并补 manifest assertions

Allowed files/modules:

- `tests/host/test_dispatch_scheduler.py`

Exact changes:

- 将 `_RaisingCompactor` 或对应 rejected attempt test seam 改为 prepared proposal failure，确保 failure 发生在 manifest record 之后。implementation 前先 grep `_RaisingCompactor` 所有使用点；若只有 `test_compaction_repair_attempt_rejection_is_recorded_in_eventlog` 使用，可直接迁移该 helper 或内联 specialized prepared failing compactor。
- 在 `test_compaction_repair_attempt_rejection_is_recorded_in_eventlog` 中，读取 rejected rows，至少断言最新或全部 rejected payload：
  - `proposal_manifest_ref` 是 `str`。
  - `proposal_manifest_ref.startswith("runner-call-manifest:")`。
  - `proposal_manifest_digest` 是非空 `str`。
- 若 `max_compaction_attempts_per_operation=2`，两个 rejected payload 均应有 manifest ref / digest。
- `RUNNER_CALL_INPUT_ASSEMBLED` count 只能作为 conditional assertion：先在 focused rejected test 中验证该 event 确实由 durable recorder 写入且不会引入脆弱计数；只有验证成立后才断言 count 为 2。
- 对 `_QualityRejectOnceCompactor` 的第一次 quality rejection，补充 rejected payload manifest assertions，证明 semantic quality rejection 也保留 proposal manifest。该断言是新增覆盖。
- `_QualityRejectOnceCompactor` 的第二次 accepted attempt 也应补 accepted payload manifest assertions，或复用 Slice 2 的 accepted assertion helper。

Call paths:

- `run_compaction_operation`
- `_run_compactor_proposal_attempt`
- `_record_compactor_proposal_manifest`
- `_build_rejected_attempt`
- `HostDispatchScheduler._append_compaction_attempt_rejected_event`

Invariants:

- rejected event 的 `operation_id` 仍锚定 `CONTEXT_COMPACTION_REQUESTED.event_id`。
- repair budget / fallback dispatch assertions 保持不变。
- 不把 proposal failure 伪装成 quality rejection；两类 rejected path 的原测试语义分别保留。
- `_RaisingCompactor` 迁移为 prepared post-manifest failure 是有意的 test 语义升级：原 legacy seam 覆盖的是 pre-manifest `compact()` failure，迁移后覆盖 manifest 已记录后的 proposal execution failure rejected payload。

Tests:

- rejected attempt tests 应证明 `CONTEXT_COMPACTION_ATTEMPT_REJECTED` payload manifest fields 存在。

### Slice 4: 恢复 broad Host validation signal

Allowed files/modules:

- `tests/host/test_dispatch_scheduler.py`

Exact changes:

- 复核 Slice 0 的语义枚举结果，确认 `tests/host/test_dispatch_scheduler.py` 内所有 proactive path compactor injection 都已分类，不限于 `context_compactor=FakeContextCompactor()` 字面量。
- 只迁移会实际写 `CONTEXT_COMPACTED` 或 `CONTEXT_COMPACTION_ATTEMPT_REJECTED` 且需要 proposal manifest 的 proactive usages。
- 明确保留 `_StaleMutatingCompactor` legacy seam，不迁移；其验收信号是 `CONTEXT_COMPACTED == 0` 和 `CONTEXT_COMPACTION_FAILED.failure_reason == "stale_compaction_result"`。
- 不迁移 reactive tests，除非同一 focused broad command 明确失败且 root cause 同源；reactive 已有独立 manifest seam 覆盖。

Call paths:

- `run_queue_promotion`
- `wake_queue_promotion`
- proactive scheduler promotion task

Invariants:

- broad command 的 7 个 manifest seam failures 应关闭。
- 若 wake queue promotion 仍 timeout，必须检查 promotion task 是否记录同一 manifest exception；不能把 timeout 当成新 root cause。

Tests:

- 运行用户给定 reproduction/focused command，预期 8 selected 全部通过。

## Tests / Validation Commands and Expected Assertions

Plan gate required validation:

- 已读取并引用相关代码证据；本 gate 不运行全量测试，不修改 production/tests/README。

失败复现命令：

```bash
source .venv/bin/activate && pytest tests/host/test_dispatch_scheduler.py -k "proactive or soft_threshold or wake_queue_promotion_uses_tracked_async_promotion_task"
```

当前已知期望：implementation 前为 8 selected，7 failed，1 passed；失败主因是 `RuntimeError: accepted compaction is missing proposal manifest ref`，wake queue promotion timeout 是 promotion task 记录同一异常后的表象。

修复后 focused validation：

```bash
source .venv/bin/activate && pytest tests/host/test_dispatch_scheduler.py -k "proactive or soft_threshold or wake_queue_promotion_uses_tracked_async_promotion_task"
```

期望：

- 8 selected 全部通过。
- accepted proactive compact payload manifest assertions 通过。
- rejected proactive attempt payload manifest assertions 通过。
- 无 `accepted compaction is missing proposal manifest ref/digest`。

补充 focused validation：

```bash
source .venv/bin/activate && pytest tests/host/test_dispatch_scheduler.py::test_pre_start_governance_soft_threshold_compacts_before_attempt tests/host/test_dispatch_scheduler.py::test_proactive_compaction_retries_quality_rejection_before_accept tests/host/test_dispatch_scheduler.py::test_compaction_repair_attempt_rejection_is_recorded_in_eventlog
```

期望：

- accepted event manifest ref/digest 直接断言通过。
- quality rejected attempt manifest ref/digest 直接断言通过。
- proposal failure rejected attempt manifest ref/digest 直接断言通过。

Pyright：

```bash
source .venv/bin/activate && pyright
```

期望：0 errors；若触及既有 pyright 报错，implementation gate 必须至少不新增、不扩散，并按项目硬约束修复受影响范围内错误。

README decision validation：

- 修改仅限测试 seam 与测试断言，不改变测试分层、运行方式、约定或维护规则。
- 检查 `tests/README.md` 职责后，预期无需更新 README。

## Docs Decision

本 work unit 的 implementation 预计无需修改 README 或设计文档。

理由：

- 生产 contract/schema/state machine/public interface 不变。
- 测试运行方式和测试分层约定不变。
- 根目录用户手册、`dayu/README.md`、Host/Engine/Fins/config README 均无接口或架构说明需要同步。
- `tests/README.md` 的触发条件会因 tests 修改被检查，但本变更不改变测试手册职责范围内的稳定说明。

## Risks / Open Questions

Blocking open questions：无。

Residual risks：

- `tests/host/test_dispatch_scheduler.py` 中可能还有不在给定 `-k` 范围内、但同样使用 legacy proactive compactor seam 并接受或拒绝 compact attempt 的用例。Slice 0 / Slice 4 必须按语义扫描并迁移同源 usages。
- prepared helper 需要小心保持 `_TransactionReadableCompactor`、`_RequestCapturingCompactor`、`_QualityRejectOnceCompactor` 的原测试语义；`_StaleMutatingCompactor` 则必须保持不迁移。
- 如果 `RUNNER_CALL_INPUT_ASSEMBLED` event count 受其它 compact path 影响，断言应限定在单个 test store 内且只在 focused test 验证稳定后加入；否则只断言 compacted/rejected payload manifest ref/digest。
- 如果 pyright 要求 protocol/runtime check 签名完全匹配，helper 方法参数和返回类型必须严格对齐 `CompactorProposalPreparedCompactor`。

## Why Not Over-designed

- 不抽取 shared production abstraction；当前问题是测试 seam 未对齐已有 contract，不是生产能力缺失。
- 不修改 `FakeContextCompactor`，避免让旧 fake 自动具备 manifest 能力并掩盖未来 seam 误用。
- 不新增 compatibility facade；每个迁移后的 proactive test 显式选择 manifest-producing compactor。
- 不改 schema/EventLog builder/dispatch guard；直接利用已有 prepared compactor recorder 路径。
- 不引入 mock file store 或 fake durable recorder；scheduler 已配置 `compact_artifact_root`，生产 recorder 能产出真实 durable manifest ref / digest。

## Completion Report Format

Implementation gate 完成后请按以下格式回复总控：

```text
artifact path: docs/host/wu-cm-01-f04-proactive-compaction-manifest-test-seam-plan.md
plan status: ready
changed files:
- tests/host/test_dispatch_scheduler.py
summary:
- 新增/迁移 proactive manifest-producing prepared compactor seam。
- accepted/rejected compact event 直接断言 proposal manifest ref/digest。
validation:
- source .venv/bin/activate && pytest tests/host/test_dispatch_scheduler.py -k "proactive or soft_threshold or wake_queue_promotion_uses_tracked_async_promotion_task" => ...
- source .venv/bin/activate && pyright => ...
README decision:
- checked tests/README.md trigger; no update needed because test conventions/running instructions unchanged.
residual risks / uncovered areas:
- ...
blocking open questions:
- none
```
