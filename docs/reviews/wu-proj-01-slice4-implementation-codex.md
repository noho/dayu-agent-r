# WU-PROJ-01 Slice 4 Implementation - AgentCodex

## 元数据

- Work unit：`WU-PROJ-01`
- Slice：Slice 4 accepted compact -> Conversation Memory -> ordinary RunInput regression
- Gate：implementation
- 日期：2026-06-11
- 执行者：AgentCodex
- 分支：`wu-proj-01`

## 动机判断

动机成立，严重性没有被高估。

Slice 1-3 已把 compact material truth 和 bounded memory catch-up / rebuild 的生产路径收敛到正确 owner，但仍需要端到端回归证明 accepted `CONTEXT_COMPACTED` 经过 Conversation Memory projection 后，会成为 ordinary RunInput 可读的五类 memory section。否则 accepted compact 只停留在 EventLog / artifact truth，后续普通 Run 可能读不到 session summary、facts、answer anchors、forward intents 或 reference continuity。

失败 compact fallback 的负向回归也成立：failed compact 不是 accepted compact fact，不能物化 Conversation Memory snapshot，也不能生成或污染 compact artifact。代码核对显示 production `ConversationMemoryProjectionConsumer` 的 event filter 不消费 `CONTEXT_COMPACTION_FAILED`，因此本 slice 不需要改生产代码，只需要用 durable ProjectionRunner 回归固定该行为。

## 改动摘要

- `tests/host/test_memory_projection.py`
  - 扩展 durable ProjectionRunner accepted compact 测试，断言五类 memory section 均被物化，并断言 memory snapshot cursor 与 projection checkpoint 同步推进到 `CONTEXT_COMPACTED`。
  - 新增 failed compact negative regression：`CONTEXT_COMPACTION_FAILED` 被 projection runner 扫描并推进 checkpoint，但不命中 memory consumer、不写 snapshot、不写 memory items。
- `tests/host/test_run_input_builder.py`
  - 扩展 ordinary RunInput regression，断言 projection catch-up 后的 accepted compact memory 被渲染进最终 one-system-message envelope 的五个业务 section：Conversation Summary、Verified Evidence and Facts、Prior Answer Anchors、Open Follow-up Context、Reference Continuity。
- `tests/host/test_dispatch_scheduler.py`
  - 扩展 proactive compact failure fallback 测试，显式注入 compact artifact root 并断言 fallback dispatch 后没有 compact artifact 文件。

未修改生产代码；本 slice 没有发现 Slice 1-3 真实生产 bug。

## 验证结果

- `source .venv/bin/activate && python -m pytest tests/host/test_memory_projection.py tests/host/test_run_input_builder.py::test_run_input_memory_messages_include_context_compacted_projection tests/host/test_dispatch_scheduler.py::test_pre_start_governance_compact_failure_is_attempt_free`
  - 18 passed
- `source .venv/bin/activate && python -m pytest tests/host/test_run_input_builder.py`
  - 45 passed
- `source .venv/bin/activate && python -m pytest tests/host/test_dispatch_scheduler.py -k "compact_failure_is_attempt_free or compact or governance"`
  - 16 passed, 51 deselected
- `source .venv/bin/activate && python -m pytest tests/host/test_memory_projection.py tests/host/test_run_input_builder.py tests/host/test_dispatch_scheduler.py -k "compact_failure_is_attempt_free or compact or governance"`
  - 25 passed, 103 deselected
- `source .venv/bin/activate && pyright`
  - 0 errors, 0 warnings, 0 informations

## README 决策

已阅读 `tests/README.md`。本 slice 只增强既有 Host memory projection、RunInputBuilder 与 dispatch scheduler 测试入口的回归断言，没有新增测试层级、运行方式或维护约定，因此不更新 README。

未修改 `dayu/host/` 生产代码，不触发 `dayu/host/README.md` 更新。

## S3-R1 覆盖情况

`WU-PROJ-01-S3-R1` 是 dispatch before-worker catch-up happy path 独立集成测试缺口。本 slice 的自然 fixture 主要覆盖 accepted compact projection、ordinary RunInput 读取和 failed compact fallback artifact negative regression，没有新增独立 before-worker catch-up happy path。该 residual risk 未自然关闭，仍保留给后续 Host dispatch test hardening。

## 残余风险

- `WU-PROJ-01-S3-R1`：仍为 deferred-with-owner；当前 slice 未硬造脆弱 dispatch catch-up happy path。
- 本 slice 未运行完整 `tests/host/test_dispatch_scheduler.py` 全文件，只运行 compact / governance 相关子集；完整文件仍可作为后续更大范围 gate 验证。
