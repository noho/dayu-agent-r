# P12.6 Slice 5 Implementation Artifact

## 基本信息

- gate：P12.6 Slice 5 implementation
- role：AgentCodex implementation specialist
- base checkpoint：410a620 gateflow: accept P12.6 slice 4
- scope：Proactive / Reactive Context Governance 接线与 reactive multi-pass single-operation durable semantics
- 非目标：不提交 commit，不 push，不修改 `docs/host/implementation-control.md`，不修改 Engine runner retry，不新增 Run / Attempt state，不做 durable schema change

## 动机判断

动机成立，严重性没有被高估。直接证据是 `docs/host/design.md` §25 要求 compaction request 输入边界固定为 compact material pack，reactive overflow 必须冻结 ordinary input material list，reactive multi-pass 必须在同一个 operation 内共享 proposal attempt budget，并且只能提交一个最终 `CONTEXT_COMPACTED` 或一个最终 `CONTEXT_COMPACTION_FAILED`。Slice 4 后 `dispatch.py` / `engine_ingest.py` 仍存在从 Session 起点收集 compaction evidence/material 的路径，`run_compaction_operation(...)` 也只有单 pass attempt loop，无法表达上述 durable 语义。

## 改动文件

- `dayu/host/dispatch.py`
- `dayu/host/engine_ingest.py`
- `dayu/host/compaction_operation.py`
- `dayu/host/context_events.py`
- `dayu/host/README.md`
- `tests/host/test_dispatch_scheduler.py`
- `tests/host/test_engine_ingest_mapping.py`
- `tests/host/test_compaction_operation.py`

## 实现摘要

- proactive pre-dispatch compact 不再调用 Session 起点 range collector，改为基于当前 accepted Run 冻结的 ordinary material block view 生成 selected segment 与 material pack，保持 Slice 1 的 `CompactionRequest(material_pack=..., segment_selection=...)` shape。
- reactive context recovery 在 request 写入前冻结 overflow ordinary material list，计算并保存 `frozen_material_list_digest` 与 `frozen_material_refs`，`_reactive_compaction_request(...)` 只消费该冻结列表构造 selected segment 与 material pack。
- `run_compaction_operation(...)` 新增 `pass_queue`，空队列保持单 pass 旧语义；multi-pass 按顺序调用 compactor，所有 pass 共享 `max_compaction_attempts_per_operation`，全部成功后合并为一个 accepted candidate。
- reactive compact 后继续不使用估算 hard threshold 阻断 recovery dispatch；proactive compact 后仍保留 hard threshold gate。
- stale/cancel/failure 路径不写 partial `CONTEXT_COMPACTED`；reactive failure 保持一个最终 failed event 并让 Run `FAILED`，不进入 `LOST`。

## 测试结果

- `source .venv/bin/activate && pytest tests/host/test_dispatch_scheduler.py tests/host/test_engine_ingest_mapping.py tests/host/test_compaction_operation.py tests/host/test_context_budget.py -q`
  - 结果：139 passed
- `source .venv/bin/activate && python -m pyright dayu/host/dispatch.py dayu/host/engine_ingest.py dayu/host/compaction_operation.py dayu/host/context_budget.py tests/host/test_dispatch_scheduler.py tests/host/test_engine_ingest_mapping.py tests/host/test_compaction_operation.py tests/host/test_context_budget.py`
  - 结果：0 errors, 0 warnings, 0 informations
- `git diff --check`
  - 结果：passed

## README 决策

触发 `dayu/host/` README 规则。已更新 `dayu/host/README.md` 的 Context Governance 稳定语义，补充 reactive operation 内 multi-pass 共享 proposal attempt budget、成功后只提交 merged `CONTEXT_COMPACTED`、失败时只提交一个 `CONTEXT_COMPACTION_FAILED`。

## 风险与未覆盖项

- proactive 发生在 `RUN_STARTED` / `ATTEMPT_STARTED` 之前，当前实现只能使用 accepted Run 已冻结的 current input anchor 形成 pre-start ordinary material view；完整 AttemptDispatchSnapshot 级 RunInputBuilder material view 仍只适用于已启动 Attempt / reactive path。
- reactive multi-pass 的中间产物当前只在 operation 内存中合并，没有新增 transient artifact durable schema；这符合本 slice 停止条件，未引入超出现有 artifact store 语义的 schema change。
- 本 slice 未修改 Engine runner retry；provider/transport retry 仍归 Engine runner 边界。
- `docs/host/implementation-control.md` 未修改；工作区中该文件已有外部 dirty 状态，本实现未触碰。
