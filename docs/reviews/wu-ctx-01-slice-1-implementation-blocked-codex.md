# WU-CTX-01 Slice 1 Implementation Blocked

## 1. Status

- work unit：`WU-CTX-01`
- gate：Slice 1 implementation resume
- protected amendment commit：`3f4190ed`
- status：`blocked`
- commit / push：未执行
- `dayu/host/durable/run_transition.py`：零 diff

本轮不能产出 implementation-complete artifact。focused Slice 1 contract 已基本闭合，
但 full Host regression 提供了直接反例：actual request 改为无条件 strict-load
current Attempt 的 candidate/manifest 后，非 reactive 的 startup recovery、steer 和
wait resume 新 Attempt 没有 matching pre-start manifest。修复必须进入这些 Attempt
start 的真实 owner；在 `dispatch.py` start 后补写会违反 manifest-before-start，在
loader 增加 fallback / 二次 assembly 又违反 complete candidate 单一真源与 strict
pairing。

这些 owner 不在 accepted Slice 1 production allowlist。根据用户要求，发现必须越界
后停止实现，不自行修改 plan。

## 2. Direct blocker evidence

当前 isolated reproduction：

```text
pytest -q \
  tests/host/test_open_host_runtime.py::test_open_host_startup_recovery_dispatches_interrupted_run_and_watch_observes_final \
  tests/host/test_public_steer.py::test_steer_running_run_creates_new_attempt_public_path

2 failed
```

两条路径均在真实 worker accept 前失败，根因完全相同：

```text
HostDurableError:
prepared runner-call manifest is missing before dispatch
```

- startup recovery 的新 Attempt 由 `dayu/host/recovery.py` 调用
  `start_recovery_run_with_starting_attempt_in_transaction` 创建；
- steer / wait resume 的新 Attempt 由各自 admission / wait transition owner 创建；
- 这些 transaction 当前都没有 complete candidate / manifest 输入；
- `dispatch.py::_build_frozen_run_input` 正确地按 current
  run/attempt/execution strict-load，不允许从 source、当前 config 或 raw fields
  猜测；
- 因而正确修复点必须是上述新 Attempt 的 pre-start transaction owner，而不是
  worker consumer、测试 fixture 或 loader fallback。

一次完整 Host diagnostic run 的结果为：

```text
2166 passed, 18 failed, 1 skipped, 6 deselected
```

失败除上述 missing-manifest family 外，还包括新 manifest 可见顺序导致的 public
ordering expectation、terminal producer static manifest expectation，以及一条 full
suite 时序下的 memory catch-up failure。它们进一步证明不能只迁移某个局部 fixture。

## 3. Completed partial implementation retained

当前未接受 partial implementation 已继续保留，没有丢弃既有或用户改动：

- `compact_payload.py` / `memory.py`
  - typed compact source boundary；
  - covered old raw pruning；
  - uncovered protected raw、current input 与 post-compact delta 保留。
- `context_budget.py`
  - 4-stage / 12-cell pressure/action；
  - `REACTIVE_POST_COMPACT` normal/soft/hard 保留真实 pressure 并 allow；
  - Engine message interpretation 已收回 `run_input.py` owner，修复 Host import
    boundary。
- `_runner_call_manifest.py` / `run_input.py`
  - strict sizing stage；
  - complete candidate 单一 projection/digest；
  - transaction-local strict loader；
  - public loader 委托；
  - `tool_execution_mode` strict schema/digest；
  - manifest/candidate/sizing/tool snapshot pairing。
- `engine_ingest.py`
  - durable effective config 通过共享 projection helper 还原 typed policy；
  - terminated source candidate strict-load；
  - source frozen policy/tool schema/disable-tools/mode 复用；
  - exact memory catch-up；
  - candidate/manifest-before-reactive-start；
  - same-transaction rollback；
  - matching committed outcome 重入与 winner duplicate no-wake。
- `dispatch.py`
  - ordinary/proactive complete candidate sizing 与 pre-start manifest ordering；
  - actual worker request strict-load frozen candidate。

没有实现 Slice 2 `CONTEXT_BUDGET_EVALUATED` / public projection，也没有实现 Slice 3
anchor resolver / signed delta。

## 4. Supplemental `_CountingTool` judgment

保留 `_CountingTool` fixture 删除 result value 中 `tool_call_id` 的改动，直接证据如下：

1. `_CountingTool` 是 `tests/host/test_dispatch_scheduler.py` 内私有测试工具；
2. 该 fake tool schema 只声明输入参数，没有把 `tool_call_id` 声明为业务返回契约；
3. 相关测试只验证调用次数与 outcome，不消费 result value 内的
   `tool_call_id`；
4. 原 fixture 把 Host governance identity 主动塞进业务 value，随后被 production
   internal-governance-fragment guard 正确拒绝。

该 fixture 判断没有替代 compact source-boundary 修复。独立 owner-level test
`test_accepted_compact_prunes_covered_tool_raw_and_keeps_uncovered_and_new_delta`
直接通过 Conversation Memory owner 证明：

- 被 compact boundary 覆盖的旧 tool raw 从 `selected_recent` 删除；
- 未覆盖的 protected tool evidence 保留；
- current input 保留一次；
- compact 后新 delta 保留；
- incremental、full rebuild 与 persisted reload 同构。

## 5. Verification at stop

- focused affected suite：`596 passed`
- full pyright：`0 errors, 0 warnings, 0 informations`
- full Host diagnostic：`2166 passed, 18 failed, 1 skipped, 6 deselected`
- isolated owner blocker：`2 failed`
- `git diff --check`：通过
- `git diff --exit-code -- dayu/host/durable/run_transition.py`：通过
- README audit：已完整读取 `dayu/host/README.md`、`tests/README.md`；blocked
  状态不发布稳定 contract，因此 README 保持零 diff
- coverage：blocked 前曾达到全部 changed production file line coverage
  `>=80%`，但随后为修复 import owner boundary 移动了 estimator adapter；因此不把
  旧 coverage 数字冒充当前 completion evidence，也不声明 coverage gate 完成

## 6. Changed files

Production partial：

- `dayu/host/_runner_call_manifest.py`
- `dayu/host/compact_payload.py`
- `dayu/host/compaction_operation.py`
- `dayu/host/context_budget.py`
- `dayu/host/context_fallback.py`
- `dayu/host/dispatch.py`
- `dayu/host/durable/schema.py`
- `dayu/host/engine_ingest.py`
- `dayu/host/memory.py`
- `dayu/host/run_input.py`

Tests partial：

- `tests/host/test_context_budget.py`
- `tests/host/test_context_compact_events.py`
- `tests/host/test_dispatch_scheduler.py`
- `tests/host/test_durable_schema.py`
- `tests/host/test_engine_ingest_mapping.py`
- `tests/host/test_memory_projection.py`
- `tests/host/test_run_input_builder.py`
- `tests/host/test_runner_call_hot_payload_contract.py`
- `tests/host/test_tool_trace_projection.py`
- `tests/host/test_tool_trace_queries.py`

`docs/host/issues-implementation-control.md` 是进入本轮前已存在的 Controller diff，本
Agent 未修改。

## 7. Required adjudication

Controller 需要重新冻结以下事项后才能恢复：

1. 是否扩充 Slice 1 production allowlist，使 startup recovery、steer、wait resume
   等所有新 Attempt owner 都能在自己的 start transaction 内接收并写入同一 complete
   candidate/manifest；
2. 若不扩充，必须明确缩窄“actual request 只消费 strict current-attempt candidate”
   contract；这会与当前单一真源、strict pairing 和 manifest-before-start目标冲突，
   不能由 implementation agent自行发明兼容分支；
3. 同步扩充对应 public/recovery/terminal ordering tests 的 allowed test scope。

在该裁决前，继续修改 production 会越界，修改 fixture 只会掩盖真实 public path
regression。
