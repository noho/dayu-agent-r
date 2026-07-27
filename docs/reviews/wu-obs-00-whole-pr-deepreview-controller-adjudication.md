# WU-OBS-00 Whole-PR Deepreview Controller Adjudication

status=complete

work_unit=WU-OBS-00

gate=whole-PR-dual-deepreview

decision=needs-fix

pr=https://github.com/noho/dayu-agent-r/pull/186

review_base=9588ee7a1801f2e88352368fe920fe881612d7fb

review_head=9519b029

review_artifacts=

- docs/reviews/wu-obs-00-whole-pr-deepreview-mimo.md
- docs/reviews/wu-obs-00-whole-pr-deepreview-ds.md

## Verdict reconciliation

AgentMiMo 给出 `pass`，AgentDS 给出 `needs-fix`。Controller 不按票数裁决：DS Finding 1
由代码与隔离复现证明为真实 primary-error masking；Finding 2 没有错误路径或语义漂移证据，
其建议会扩大 internal dataset contract。

## PR-CTRL-01 — cold read failure 被 close failure 覆盖

severity=medium

owner=dayu.host.tool_trace_analysis_input cold snapshot lifecycle

accepted=true

当前 `_capture_cold_prefix(...)` 在 exact-prefix read / identity check 的
`ToolTraceAnalysisInputError` 正在传播时进入 `finally`。若 `handle.close()` 同时抛
`OSError`，finally 再抛新的 `ToolTraceAnalysisInputError`，导致 operator 看见“关闭 cold
snapshot handle 失败”，而不是“无法读取完整 prefix”。

Controller 使用真实 cold file descriptor、注入 read/close 双失败，得到：

```text
reason=cold_snapshot_read_failed
summary=关闭 cold snapshot handle 失败。
cause=secondary-close-failed
context=secondary-close-failed
```

主读取失败与其直接 cause 已从 public primary error 中消失。这违反项目 root-cause 必须由直接
逻辑/数据证据表达的约束。

修复语义：

- read / fstat identity failure 与 close failure 同时发生：保留 read/identity failure 为
  primary `ToolTraceAnalysisInputError`，summary 与 cause 指向直接读取失败；
- prefix read 成功、只有 close failure：close failure 继续 fatal，保持 accepted plan
  §7.4 与既有 `test_cold_handle_close_failure_is_fatal`；
- 不把所有 close failure 改成 best-effort，不记录日志替代 typed error，不新增 public schema；
- owner test 同时注入 read 与 close failure，断言 reason、read summary/direct cause 未被
  close 覆盖；既有 close-only fatal test 增强为断言 close summary。

## DS Finding 2 — rules 导入 lock-path owner helper

disposition=reject-nondefect

`_tool_trace_cold_lock_path` 的语义 owner 仍是 `dayu.host.tool_trace`。rules 没有复制 suffix、
从 raw field 推断或创建第二真源，而是在 Host 内部直接复用 owner helper；helper 未从
`dayu.host` root 导出，Service/CLI 也未调用。plan 所称 producer / Analyzer reader 是必要
consumer 集合与层级边界，不是禁止同一 Host Analyzer 的 report builder 为 hot-only expected
path 调用唯一 owner。

建议把 `expected_cold_lock_path` 塞入 `ToolTraceAnalysisDataset` 会扩大 Slice 1 internal
dataset contract，仅为隐藏同包私有 import 增加字段和传递链；当前无 path 错误、owner drift
或测试失败证据，因此不实施。

## Other observations

- MiMo 的 `open_host.py` 同包私有 helper import 与上述理由相同，reject-nondefect。
- MiMo 的 Markdown section 固定索引是冻结模块私有表与 renderer 同处的维护观察，无当前错误
  证据，reject-nondefect。
- CI 未配置、#64 native correlation limited signal、超大 cold file成本与双文件非事务继续作为
  已有明确 owner 的 residual，不进入本 fix。

blocking_open_questions=none

next_entry_point=AgentCodex PR-CTRL-01 fix; never self-advance
