# Host P1.5 Plan Review

## Review 范围

本轮审查 P1.5 handoff plan：

- `docs/host/phase1_5-plan.md`

参考材料：

- `docs/host/migration-plan.md`
- `docs/host/design.md`
- `AGENTS.md`

审查重点：

- P1.5 是否只固定 Minimal EventLog / RunEventStore，没有偷做 P6 / P7 / P2 / P3 / P4。
- append-before-stream、per-run cursor、exclusive replay 与订阅一致性是否足够可交接。
- canonical / preview 分层是否保护 P3 memory 与 P4 compact 不消费展示 delta。
- public boundary 是否仍围绕 Run，不暴露 EngineWorker / ToolExecutor / store 实现类。
- 类型、分层、runtime dependency 与 README 触发判断是否满足项目约束。

## 初审结论

初审不通过 plan review gate。

动机成立：P1 之后先固定最小事件事实层是必要的，否则 P2-P5 会各自制造旁路事实来源，后续 P6
会被迫倒改。

但初版 plan 仍有关键边界未收束，直接交给迁移 Agent 会导致 public API、cursor 所有权、订阅一致性
和终态事实来源分叉。

## Findings 与修复状态

### 1-已修复-高-public boundary 未决，plan 不具备可直接交接性

问题：

- 初版把 `stream_run_events` / `get_run_result` 写成“内部或 public”，同时放入待确认项。
- 这会直接影响 `contracts.py`、`__init__.py`、README 与 public boundary 测试，不能留给实施阶段临场决定。

修复状态：

- 已在 `docs/host/phase1_5-plan.md` 明确：P1.5 将 `stream_run_events(run_id, after=cursor)` 与
  `get_run_result(run_id)` 作为包根 Run 级 public API 落地。
- 已限定它们只提供补读 / 快照读取，不承诺 P7 Session admission、幂等、取消治理或多进程恢复。

### 2-已修复-高-RunEventStore cursor 所有权与返回类型不自洽

问题：

- 初版 `append(event: RunEvent) -> StoredRunEvent`，但 replay / subscribe 返回 `RunEvent`。
- 同时 plan 又要求 cursor 不绑定 Engine sequence，导致调用方消费的事件类型与 cursor 来源不清楚。

修复状态：

- 已新增 `RunEventDraft` 与 `RunEvent` 分层：translation 产出内部 draft，store append 后返回唯一可消费的
  cursor-bearing `RunEvent`。
- 已明确 cursor 由 Host store 生成，Engine sequence 只能作为 diagnostic source，不能作为 Host cursor。
- 已禁止通过可变字段或隐式替换补 cursor。

### 3-已修复-高-subscribe replay-then-follow 语义不足以排除丢事件窗口

问题：

- 初版只写“先 replay 再等待新 append”，但没有约束 replay 完成和进入 wait 之间的竞态。
- 基于 queue / 两段式注册的实现可能错过通知。

修复状态：

- 已要求 `subscribe` 使用 cursor predicate：在同一 lock / condition 保护下循环检查
  `last_seen_cursor` 之后是否存在事件，只有确认没有新事件时才等待。
- 已新增 lost-wakeup race 测试要求。

### 4-已修复-高-worker 异常路径可能绕过 store，破坏 EventLog 真源

问题：

- 初版允许 worker 异常只通过 iterator exception 暴露，不写 terminal RunEvent。
- 这会使 `RunStream.events`、`get_run_result` 与 terminal 调和绕开 RunEventStore。

修复状态：

- 已要求 worker / proxy 异常且 Engine 未产生 terminal event 时，append Host-owned canonical failure
  RunEvent。
- 已新增 `RunEventSource`、`HostRunFailedData` 方向，并要求 `source_engine_event_id=None` 标明它不是
  Engine 原始事件。
- 已明确该能力只是 P1.5 最小 terminal fact，不代表 P7 完整生命周期治理。

### 5-已修复-中-preview 防污染规则表述偏弱

问题：

- 初版说 preview 不能作为 ContextBuilder、RunResult、outbox、replay、recovery 的“唯一事实来源”，
  该表述可能允许 preview 作为辅助输入进入运行态。

修复状态：

- 已改为 preview 不得被 ContextBuilder、Memory pool、RunInput replay、RunResult、outbox、replay
  或 recovery 消费；只能被 stream 和未来 timeline 展示消费。
- 已要求成功终态 canonical event 携带稳定 final answer 或等价 result payload，不依赖 preview delta
  拼接答案。

### 6-已修复-低-P4 / P11 术语需要标注为未来事件分类而非本期实现

问题：

- 初版分类原则包含 context compaction / suspended，容易被误解为 P1.5 要补 compact、wait 或 resume 治理。

修复状态：

- 已补充说明：这些只是已有或未来事件出现时的分类规则，P1.5 不新增 compact / retry / wait /
  resume 治理行为。

## 复审结论

通过 P1.5 plan review gate。

复审确认：

- `stream_run_events` / `get_run_result` 已明确作为包根 Run 级 public API。
- `RunEventDraft -> append -> cursor-bearing RunEvent` 边界清楚，cursor 所有权归 Host store。
- `subscribe` 已要求 cursor predicate 循环等待，覆盖 replay / follow lost-wakeup 窗口。
- worker / proxy 异常路径已要求 append Host-owned canonical failure event，不再绕过 EventLog。
- preview 防污染规则已收紧为不得进入 ContextBuilder、Memory、RunInput、RunResult、outbox 或 recovery。
- context compaction / suspended 已标明只是分类规则，不代表 P1.5 实现 P4 / P11 治理。

未发现新的阻塞项。当前 plan 保持 P1.5 范围：最小 EventLog / RunEventStore，不偷做 P6 observer、
P7 lifecycle governance、P2 ToolRuntime、P3 Memory 或 P4 compact / retry。

按 `docs/host/migration-plan.md`，plan review 通过后应停止，等待用户人工 review。用户确认后，
才能提交 phase plan / review 文档并进入代码实施。

## 用户人工 Review

用户已确认 P1.5 plan 可以进入实施，并补充以下决策：

- `stream_run_events(run_id, after=cursor)` 与 `get_run_result(run_id)` 应按
  `docs/host/design.md` 作为 Host Run 级 public interface 导出。
- `RunEventKind` 只表达 EventLog 事实层级，不表达业务类型。
- worker / proxy 异常肯定会发生，P1.5 应生成 Host-owned canonical failure RunEvent；该能力不包含
  P7 完整生命周期治理。
- Engine 自身执行路径不应缺失 terminal EngineEvent；若当前缺少相关语义测试，P1.5 实施完成后增加
  临时任务补覆盖。

## 验证记录

本轮只修改迁移计划与 plan review 文档，尚未修改生产代码或测试代码。

已运行：

```bash
source .venv/bin/activate
python -m pyright
```

结果：0 errors, 0 warnings, 0 informations。

未运行 pytest，原因是本轮只修改文档，未修改生产代码或测试代码。
