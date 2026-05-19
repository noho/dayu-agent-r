# Host README 重写记录

## 任务范围

- 任务对象：重写 `dayu/host/README.md`。
- README 目标职责：作为 Host 开发手册，只写接口、公共契约、架构、边界、执行路径、状态机、事件流、关键机制和扩展点。
- 允许补充产物：创建本文档 `docs/reviews/host-readme-rewrite-codex.md`，记录检查点、变更摘要与验证。
- 明确未做事项：未启动 gateflow，未修改 `AGENTS.md` / `CLAUDE.md`，未 stage，未 commit，未 push，未触碰其它 agent 正在进行的全仓 deepreview。

## 事实来源

- 当前代码：
  - `dayu/host/__init__.py`
  - `dayu/host/api.py`
  - `dayu/host/open_host.py`
  - `dayu/host/admission.py`
  - `dayu/host/dispatch.py`
  - `dayu/host/engine_ingest.py`
  - `dayu/host/run_input.py`
  - `dayu/host/tool_runtime.py`
  - `dayu/host/memory.py`
  - `dayu/host/memory_repair.py`
  - `dayu/host/payload_resolution.py`
  - `dayu/host/terminal_summary_payload.py`
  - `dayu/host/compaction_operation.py`
  - `dayu/host/durable/` 相关模块
- 设计真源：`docs/host/design.md`。
- 总览文档参考：`dayu/README.md`，仅用于对齐整体分层、同名章节写法和文档职责边界。
- 项目约束：用户已修改的 `AGENTS.md` 与 `CLAUDE.md`，用于确认语言、分层、README 职责、禁止过程状态和禁止未来设计写法。

## 已满足的文档约束

- README 全文为中文。
- 已在 README 前部加入 `Agent更新约束【必须遵守】`，并对齐当前代码、`docs/host/design.md`、`dayu/README.md`、`AGENTS.md` / `CLAUDE.md` 的文档边界。
- 已加入 Host 层 `设计意图`，聚焦 Host 是 `UI -> Service -> Host -> Engine` 中的治理边界，没有复制系统总览。
- 已明确 Service-facing public contract：
  - `open_host(options)`
  - `OpenHostOptions`
  - 异步 `Host` handle
  - `ensure_session`
  - `create_session`
  - `get_session`
  - `get_run`
  - `submit_followup`
  - `cancel_run`
  - `cancel_session_runs`
  - `retry_run`
  - `replay_run`
  - `resolve_wait`
  - `close_session`
  - `watch_session_events`
  - `close`
- 已按包根 `dayu.host.__all__` 同步 README 的 public contract 类别说明：
  - 补充 public constants 类别，覆盖 Host event stream limit 常量与 wait / payload 引用字段长度上限常量的类别说明。
  - 在 session / deferred 类别与 `purge_session` 说明中显式覆盖 `PurgeSessionRequest` 与 `PurgeSessionResult`。
  - 在 event / read view 类别中补充 `HostEventClass`。
- 已区分低层 / diagnostic 路径，未把低层 command handle、`start_run`、run-level `stream_run_events`、durable internals、scheduler internals 或 ToolRuntime factory 写成普通 Service-facing contract。
- 已覆盖稳定语义：
  - `EventLog`
  - `Run` / `Attempt` 状态机
  - admission 与 queue / steer
  - dispatch
  - ToolRuntime accept barrier
  - memory projection
  - context compaction
  - payload descriptor
  - terminal summary continuity
- 已清理原 README 中的过程状态、测试清单、文件级流水账、历史迁移说明和未落地能力清单。
- 未写安装运行命令，未写用户手册，未写未来计划，未写实现细节。

## 已做验证命令

```bash
git diff --check
```

结果：通过，无 whitespace / patch 格式问题。

```bash
rg -n -o "Phase|P10|未来|待实现|后续|近期|计划|review|gate" dayu/host/README.md
```

结果：无匹配。

```bash
rg -n "HostHandle|HostInput|CompactorExecutionBaseline" dayu/host/README.md
```

结果：无匹配。

```bash
rg -n "HostHandle|HostInput|CompactorExecutionBaseline|stream_run_events" dayu/host/README.md
```

结果：仅 `stream_run_events` 有匹配，且两处均明确标注为低层 / diagnostic 路径，不是普通 Service-facing public contract。

```bash
git status --short
```

结果：当时仅显示 `AGENTS.md`、`CLAUDE.md`、`dayu/host/README.md` 为 modified；其中 `AGENTS.md` 与 `CLAUDE.md` 是既有用户修改，未触碰。

补充复核修正后再次执行：

```bash
git diff --check
```

结果：通过，无 whitespace / patch 格式问题。

```bash
rg -n -o "Phase|P10|未来|待实现|后续|近期|计划|review|gate" dayu/host/README.md
```

结果：无匹配。

## 未运行测试 / pyright 的原因

- 本次主任务是 README 文档重写，没有修改 Python 生产代码、测试代码、schema 或 public type 定义。
- 用户指定的验证项是 `git diff --check` 和 README 文本残留检查；任务完成后按该要求执行了文档级验证。
- 运行测试或 pyright 对该文档-only 修改不会增加代码行为信号，且可能触碰全仓耗时流程；因此未运行测试与 pyright。

## 剩余风险

- README 是对当前代码和设计真源的人工归纳，仍可能存在表述粒度与某些内部模块最新细节不完全同步的风险。
- 由于未运行测试和 pyright，本记录不证明代码行为或类型状态，只证明文档变更满足指定文本与边界检查。
- `stream_run_events` 在 README 中仍被点名用于说明低层 / diagnostic 边界；若后续要求完全不出现该名称，需要删除这两处说明，但当前用户要求允许在明确低层 / diagnostic 时提及。
