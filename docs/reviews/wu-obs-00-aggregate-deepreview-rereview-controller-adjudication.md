# WU-OBS-00 Aggregate Deepreview Re-Review Controller Adjudication

status=complete

work_unit=WU-OBS-00

gate=aggregate-deepreview-dual-rereview

decision=needs-fix

review_artifacts=

- docs/reviews/wu-obs-00-aggregate-deepreview-rereview-mimo.md
- docs/reviews/wu-obs-00-aggregate-deepreview-rereview-ds.md

## Verdict reconciliation

AgentMiMo 与 AgentDS 均给出 `verdict=pass`，并确认 `CTRL-AGG-01..02` 的原始复现路径已经
关闭。但 AgentDS 同时报告 replace phase 的中断窗口可能泄漏尚未 replace 的本次临时文件。
reviewer 的“非阻塞”标签不是事实 owner；Controller 依据 accepted plan 与直接复现接受该项，
因此本 gate 不得推进。

## CTRL-RR-01 — replace phase 中断泄漏 pending temp

severity=low

owner=dayu.service.tool_trace_analysis publication boundary

accepted=true

accepted plan §10.3 明确：

- 任一发布失败时 best-effort 清理本次临时文件；
- 不删除调用方既有 report；
- JSON→Markdown 顺序逐文件 replace，双文件不构成事务。

当前 `_publish_report_pair(...)` 只在 replace phase 捕获 `OSError`。若
`_replace_temporary_file(...)` 或两次 replace 之间收到 `KeyboardInterrupt` / `SystemExit`，
异常直接逃逸，`pending_temporary_paths` 未被清理。

Controller 隔离复现把第一次 `_replace_temporary_file` 注入为
`KeyboardInterrupt("replace-interrupt")`，结果：

```text
caught=True
json=old-json
markdown=old-md
temps=['.tool-trace-analysis-4a4c7azj.tmp',
       '.tool-trace-analysis-v9xa6kus.tmp']
```

这是实际 temp lifecycle contract 违反，不因窗口短或数据文件未损坏而变成 non-defect。

修复边界：

- replace phase 任意 `BaseException` 逃逸前，best-effort 清理
  `pending_temporary_paths`；
- 既有 `OSError -> ServiceToolTraceAnalysisPublishError` primary/secondary typed truth 保持；
- `KeyboardInterrupt` / `SystemExit` cleanup 后原样传播，不转换；
- JSON replace 已成功、Markdown replace 前中断时，不回滚新 JSON，不删除旧 Markdown，只清理
  pending Markdown temp；
- 增加 first replace 与 second replace 的 interruption owner tests，断言异常 identity、
  published/old final files 与 `.tmp=0`；
- 不修改 Host、CLI、schema、public types、README wording、control_doc 或真实 workspace。

## Other findings

- `CTRL-AGG-01`：原始 strict UTF-8 temp-write path 已关闭，保持 closed。
- `CTRL-AGG-02`：双文件非事务措辞已关闭，保持 closed。
- DS-R1：`NamedTemporaryFile` 构造失败时无已返回 temp path；属于确认性说明，无 defect，reject。
- aggregate 初审被 Controller 驳回的 findings 无新直接证据，保持驳回。

blocking_open_questions=none

next_entry_point=AgentCodex CTRL-RR-01 fix; never self-advance
