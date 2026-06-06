# WU-TOOLS-01 external blocker reconciliation

角色：AgentCodex
日期：2026-06-06
范围：WU-TOOLS-01 S6 broad validation 剩余 11 个 Host 行为失败的 root-cause 同源核对。

## 结论

| blocker | 当前裁决 | 本轮动作 |
|---|---|---|
| WU-TOOLS-01-S6-R1 proactive compaction missing proposal manifest ref | must-defer-with-owner | 不修改生产代码；保留 7 个失败，交给 Host context governance / compactor seam owner 裁决 |
| WU-TOOLS-01-S6-R2 effective execution config one-system-message mismatch | can-fix-now | 已窄同步 2 个测试断言 |
| WU-TOOLS-01-S6-R3 wait/resume old accepted-result text mismatch | can-fix-now | 已窄同步 2 个测试断言 |

R2/R3 均为测试仍期待旧 LLM-facing 文本；生产语义已经由 one-system-message / LLM-facing internal-id ban 设计与实现接受。本轮只改 `tests/host/*.py` 断言，不改 Host production behavior、durable schema、prompt projection contract 或 wait/resume LLM-facing text contract。

## 复现记录

初始 targeted 复现命令：

```bash
source .venv/bin/activate && pytest \
  tests/host/test_dispatch_scheduler.py::test_pre_start_governance_soft_threshold_compacts_before_attempt \
  tests/host/test_dispatch_scheduler.py::test_proactive_compaction_uses_selected_material_not_session_start_range \
  tests/host/test_dispatch_scheduler.py::test_proactive_material_pack_not_larger_than_ordinary_material_for_same_view \
  tests/host/test_dispatch_scheduler.py::test_wake_queue_promotion_uses_tracked_async_promotion_task \
  tests/host/test_dispatch_scheduler.py::test_proactive_compaction_calls_llm_outside_write_transaction \
  tests/host/test_dispatch_scheduler.py::test_proactive_compaction_retries_quality_rejection_before_accept \
  tests/host/test_dispatch_scheduler.py::test_multi_turn_proactive_compact_feeds_subsequent_run_input \
  tests/host/test_effective_execution_config.py::test_field_level_partial_merge_uses_baseline_for_omitted_fields \
  tests/host/test_effective_execution_config.py::test_descriptor_payload_dispatch_uses_per_run_override \
  tests/host/test_phase7_waiting_integration.py::test_local_awaiting_tool_manual_resolve_resumes_run \
  tests/host/test_resolve_wait_command.py::test_resolve_wait_completed_resumes_run_and_wakes_dispatch -q
```

结果：11 failed。

精确 failure signatures：

- R1 六个 direct promotion tests 在 `dayu/host/dispatch.py:3744` 抛 `RuntimeError: accepted compaction is missing proposal manifest ref`；`test_wake_queue_promotion_uses_tracked_async_promotion_task` 表层为 `AssertionError: event count did not converge: CONTEXT_COMPACTED`，captured log 同样显示 `dispatch.py:3744` 的 RuntimeError。
- R2 两个 tests 断言 `request.messages[0].content == "system slice3"` / `"descriptor system prompt"`，实际内容为 one-system envelope：`## Task Instructions` + 原 system prompt + `## Execution Guidance` + `Tools are disabled for this runner call.`
- R3 两个 tests 的 `any(...)` 为 False，因为 resume messages 不再包含旧 `"Accepted wait result fact:"` 文本，也不暴露 `wait_id`。

R2/R3 修复后 targeted 命令：

```bash
source .venv/bin/activate && pytest \
  tests/host/test_effective_execution_config.py::test_field_level_partial_merge_uses_baseline_for_omitted_fields \
  tests/host/test_effective_execution_config.py::test_descriptor_payload_dispatch_uses_per_run_override \
  tests/host/test_phase7_waiting_integration.py::test_local_awaiting_tool_manual_resolve_resumes_run \
  tests/host/test_resolve_wait_command.py::test_resolve_wait_completed_resumes_run_and_wakes_dispatch -q
```

结果：4 passed。

重跑 11 项后结果：7 failed, 4 passed。剩余 7 项全部属于 R1。

## R1: proactive compaction manifest ref

测试证据：

- `tests/host/test_dispatch_scheduler.py:3613`、`:3690`、`:3725`、`:3757`、`:3890`、`:3967`、`:4257` 覆盖 proactive compaction accepted closeout、material selection、promotion task、transaction boundary、quality retry 和后续 RunInput。
- 这些 tests 注入 `FakeContextCompactor()` 或其子类，例如 `tests/host/test_dispatch_scheduler.py:3630`、`:3773`、`:3907`、`:3986`、`:4269`。
- `tests/host/fake_compaction.py:39-66` 的 `FakeContextCompactor` 只实现 `compact(...)`，不实现 prepared proposal input capability。

生产代码证据：

- `dayu/host/dispatch.py:1173-1187` proactive path 调用 `run_compaction_operation(...)` 时已经传入 `proposal_manifest_recorder=self._compactor_proposal_manifest_recorder()`。
- `dayu/host/dispatch.py:1249-1269` accepted closeout 写 `CONTEXT_COMPACTED` 前强制读取 `accepted_proposal_manifest_ref` / digest。
- `dayu/host/dispatch.py:3734-3758` 在 accepted result 缺少 manifest ref/digest 时 fail closed。
- `dayu/host/compaction_operation.py:133-167` 定义 `CompactorProposalPreparedCompactor` prepared capability。
- `dayu/host/compaction_operation.py:749-776` 只有 compactor 满足 prepared capability 时才 prepare、record manifest、再 run proposal。
- `dayu/host/compaction_operation.py:777-784` generic `ContextCompactor.compact(...)` fallback 返回 `proposal_manifest_reference=None`。
- `dayu/host/compaction_operation.py:673-681` accepted result 直接把 `accepted_manifest_reference is None` 投影为 `accepted_proposal_manifest_ref=None` / digest None。
- `dayu/host/llm_compaction.py:220-285` 的生产 `LLMContextCompactor` 实现 prepared input；`dayu/host/llm_compaction.py:287-320` 执行 prepared proposal。

设计 / accepted 语义证据：

- `docs/host/design.md:3141-3153` 要求 Host-owned compactor proposal call 必须写入 runner-call manifest，且 accepted compact event 必须通过 `accepted_proposal_manifest_ref` / digest 反向引用 accepted proposal manifest。
- `tests/host/test_compaction_operation.py:490-568` 和 `tests/host/test_engine_ingest_mapping.py:273-330` 已有专门 prepared test compactor，说明 prepared 与 generic fake compactor 在测试语义上是显式区分的。
- `docs/reviews/wu-dur-obs-cm-closeout-slice3-rereview-ds.md` 记录 proactive path fail-closed guard 是 accepted 行为。

root cause 同源裁决：

R1 不是 WU-TOOLS provider 迁移导致。直接根因是 proactive accepted closeout 已要求 manifest ref，但这些 Host scheduler tests 仍注入 generic fake compactor；generic fallback 不可能生成 accepted proposal manifest ref。表面上可把 tests 改为 prepared fake，但这会绕过一个真实 Host seam 问题：public/local execution 仍可注入不支持 prepared manifest 的 `ContextCompactor`，然后在 accepted closeout 才 runtime fail closed。

裁决：must-defer-with-owner。

建议 owner：Host context governance / compactor seam owner。需要先裁决生产语义之一：

- opener / scheduler construction 是否应 reject 非 prepared compactor；
- `ContextCompactor` public seam 是否应升级为 prepared-only；
- 或 generic compactor path 是否仍是合法 fallback，若合法则如何生成 durable runner-call manifest。

这些都属于 Host production behavior / compactor projection contract，不在本轮允许范围内。

## R2: effective execution config one-system-message mismatch

测试旧期望证据：

- 初始失败来自 `tests/host/test_effective_execution_config.py:242` 旧断言 `request.messages[0].content == "system slice3"`。
- 初始失败来自 `tests/host/test_effective_execution_config.py:415` 旧断言 `request.messages[0].content == "descriptor system prompt"`。

生产语义证据：

- `docs/host/design.md:2572-2587` 明确 ordinary public RunInput 必须满足 one-system-message hard contract，system envelope 使用固定 section title / 顺序。
- `dayu/host/run_input.py:1724-1751` 当前 scene provider 生成 `Execution Guidance`，包含 `Use the available context and tools under the current run limits.` 与工具可用性说明。
- `dayu/host/run_input.py:4438-4447` 当前 no-tool 路径文本为 `Tools are disabled for this runner call.`
- `tests/host/test_run_input_builder.py:545-590` 已覆盖工具 enabled / disabled guidance。
- `tests/host/test_run_input_builder.py:3741-3753` 的 expected system content 已使用 `## Execution Guidance`。
- `docs/reviews/wu-cm-01-f01-s7-r1-s1-rereview-controller-adjudication.md` 已接受 one-system-message production assembly gate。

修复：

- `tests/host/test_effective_execution_config.py:242-248` 改为断言 one-system envelope 中包含原 `system slice3`、`Execution Guidance` 和 no-tool guidance。
- `tests/host/test_effective_execution_config.py:421-431` 对 descriptor payload path 做同样同步。

裁决：can-fix-now，已关闭。

## R3: wait/resume old accepted-result text mismatch

测试旧期望证据：

- 初始失败来自 `tests/host/test_phase7_waiting_integration.py:342-347`，旧断言查找 `"Accepted wait result fact:"` 且要求 `wait.wait_id` 出现在 LLM-facing resume request messages。
- 初始失败来自 `tests/host/test_resolve_wait_command.py:144-149`，旧断言同样查找 `"Accepted wait result fact:"` 与 `seeded.wait_id`。

生产语义证据：

- `dayu/host/run_input.py:3444-3490` 当前 resume wait projection 生成 `_RESUME_GUIDANCE_PREFIX`，LLM-facing 文本为 `A previous interrupted step has an accepted wait result.`，并包含 `tool_name=...`、`resolution_kind=...`、`tool_fact_kind=...`、`result=...`。
- `docs/host/design.md:2585-2586` 规定 wait-resume / resume guidance 不暴露 wait record id 或内部恢复状态，只写当前继续目标和用户可理解恢复说明。
- `docs/host/design.md:2592-2605` 规定 LLM-facing material 不得暴露 internal refs / ids / ledger 字段。

修复：

- `tests/host/test_phase7_waiting_integration.py:342-349` 改为断言当前 resume guidance、业务 tool name、completed resolution 和结果内容。
- `tests/host/test_resolve_wait_command.py:144-151` 同步为当前 resume guidance、`tool_name=long_tool`、completed resolution 和结果内容。

裁决：can-fix-now，已关闭。

## README 同步判断

本轮只同步既有 Host tests 的断言，不改变测试分层、运行方式、约定或维护规则；`tests/README.md` 职责范围未发生变化，因此不更新。
