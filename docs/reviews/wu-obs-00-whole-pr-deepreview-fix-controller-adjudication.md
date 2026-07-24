# WU-OBS-00 Whole-PR Deepreview Fix Controller Adjudication

status=complete

work_unit=WU-OBS-00

gate=whole-PR-deepreview-fix-controller-review

decision=needs-fix

implementation_artifact=docs/reviews/wu-obs-00-whole-pr-deepreview-fix-codex.md

## PR-CTRL-01 progress

read `OSError` 与 close `OSError` 双失败时，当前 working diff 已正确保留 read summary 与
direct cause；close-only failure 也继续 fatal。原 finding 的两条 OSError 路径已闭合。

## PR-FIX-CTRL-01 — 非 OSError 逃逸不再关闭 cold handle

severity=medium

owner=dayu.host.tool_trace_analysis_input cold snapshot lifecycle

accepted=true

为拆分 read/close OSError，working diff 删除原 `finally`，只捕获 read phase 的 `OSError`，
随后才调用 `handle.close()`。若 `_read_exact_prefix`、`os.fstat` 或 identity control flow 抛出
`KeyboardInterrupt`、`SystemExit`、`MemoryError` 等非 `OSError`，函数在 close 前逃逸。

Controller 直接注入 `_read_exact_prefix -> KeyboardInterrupt("read-interrupt")`，得到：

```text
caught=True
handle_closed=False
```

这是 fix 引入的 handle lifecycle 回归；不能为了保留 OSError primary 而丢失任意异常路径上的
mandatory close。

修复语义：

- read/identity phase 捕获本次任意 `BaseException` 作为 operation primary，之后始终尝试
  `handle.close()`；
- primary 是 `OSError`：close 后映射为既有 read
  `ToolTraceAnalysisInputError`，direct cause 指向 read；
- primary 是非 `OSError`：close 后原异常实例原样传播；
- 无 operation primary、close `OSError`：保持 close-only typed fatal；
- operation primary 与 close failure 同时发生：operation primary 优先，close 是 secondary，
  不得覆盖；
- 增加 `KeyboardInterrupt` / `SystemExit` owner tests，证明 close 被调用、异常 identity 不变；
  至少一条同时注入 close failure，证明 secondary close 不覆盖中断；
- 既有 read+close OSError 与 close-only tests 保持。

不得通过重新引入一个会在 finally 中覆盖 primary 的 raise 修复；不得吞掉非 OSError、改 public
schema、添加日志 fallback 或实施已驳回的 lock-path contract扩张。

blocking_open_questions=none

next_entry_point=AgentCodex PR-FIX-CTRL-01 correction; never self-advance
