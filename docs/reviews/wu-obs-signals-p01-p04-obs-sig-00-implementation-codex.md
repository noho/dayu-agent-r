# WU-OBS-SIGNALS-01 / OBS-SIG-00 实现记录

## Gate 信息

- Work unit：`WU-OBS-SIGNALS-01`
- Gate：`implementation`
- Slice：`OBS-SIG-00 Shared Tool Trace Signal Foundation`
- Artifact 路径：`docs/reviews/wu-obs-signals-p01-p04-obs-sig-00-implementation-codex.md`
- 已检查设计真源：`docs/host/design.md`、`docs/engine/design.md`
- 已检查批准计划：`docs/host/wu-obs-signals-p01-p04-plan.md`
- 范围边界：只实现 shared Tool Trace signal foundation；未实现 `OBS-SIG-01/P01`、`OBS-SIG-02/P02`、`OBS-SIG-03/P03`、`OBS-SIG-04/P04` 或 `OBS-SIG-05`。

## 动机判断

切片动机成立。Tool Trace 已经通过 hot `trace_summary_json` 和 cold JSONL `trace_summary` 承载结构化 projection summary，因此四类可选 signal object 可以进入现有 summary，不需要改 SQLite schema、public query API、Engine public contract、EventLog producer 或 ToolRuntime 执行语义。

本实现没有从现有 source payload 字段推导 signal 值，只验证并复制已经存在的 signal object。

## 修改文件

- `dayu/host/tool_trace.py`
- `tests/host/test_tool_trace_projection.py`
- `docs/reviews/wu-obs-signals-p01-p04-obs-sig-00-implementation-codex.md`

`docs/host/issues-implementation-control.md` 在 preflight 时已经是 dirty，本轮 implementation 未修改该文件。

## 精确实现内容

- 新增四个私有 Tool Trace signal 字段常量：
  - `context_pressure`
  - `tool_timing`
  - `failure_metadata`
  - `partial_tool_call_signal`
- 新增私有 `_TraceSummarySignals` grouped carrier，使用严格类型签名并提供中文 docstring。
- `_trace_summary` 改为接收 grouped carrier，没有新增四个独立 optional 参数。
- 新增 `_trace_summary_signals` 与 `_optional_signal_object` helper。
- canonical、diagnostic、usage 三条 Tool Trace extract 路径会复制已经存在的 signal object 到 `trace_summary`。
- 保持 hot/cold 同源：cold JSONL 继续写入 `extracted.trace_summary`，与 hot row 使用同一份 summary。
- 未计算 P01-P04 signal 值，未读取 source payload 的其它字段来推导 signal，未改 producer。

## 测试变更

- 新增 projection 测试：四类 optional signal object 会进入 hot row 和 cold JSONL 的 `trace_summary`。
- 新增 projection 测试：缺失或显式 `null` 的 signal 字段不会进入 `trace_summary`，避免表达不存在的事实。
- 新增 projection 测试：命名 signal 字段存在但不是 JSON object 或 `null` 时，以 `HostDurableError` fail closed。
- 既有 runner-call 与 provider query 测试保持不变并通过。

## 验证结果

命令：

```bash
source .venv/bin/activate && pytest tests/host/test_tool_trace_projection.py tests/host/test_tool_trace_queries.py
```

结果：通过，`21 passed in 0.45s`。

命令：

```bash
source .venv/bin/activate && pyright
```

结果：通过，`0 errors, 0 warnings, 0 informations`。

## README 决策

- 已阅读 `dayu/host/README.md` 的 Agent 更新约束。
- 已阅读 `tests/README.md` 的 README 更新边界。
- 本轮未更新 README。

原因：本切片只增加 Tool Trace 内部 summary carrier wiring 和对应测试；未改变 Host public API、稳定架构边界、开发者可见 package contract、测试层级、测试运行命令或维护规则。

## Residual Risks

- 风险：实际 signal payload 仍为空，直到后续 P01-P04 producer / extraction slices 填充值。
  - Owner/destination：已由后续批准切片 `OBS-SIG-01/P01` 到 `OBS-SIG-04/P04` 覆盖。
- 风险：`trace_summary_json` 内的 JSON 字段没有索引，大规模 analyzer 聚合可能较慢。
  - Owner/destination：已由批准计划记录为后续 analyzer/query performance 风险；`OBS-SIG-00` 不具备新增 schema 的必要性。
- 风险：runner-call 专用 summary 路径不是 P01-P04 的批准 signal source，本轮未改该路径。
  - Owner/destination：分类为当前切片非目标；若未来设计把 signal source 扩展到 runner-call，应进入新的批准切片或 work unit。

## 完成状态

只实现了 `OBS-SIG-00`。

未执行 analyzer、SQLite schema migration、新 query API、Engine public contract extension、ToolRuntime execution semantic change、review gate、commit、push、PR 或 merge。
