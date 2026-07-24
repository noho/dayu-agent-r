# WU-OBS-00 Aggregate Deepreview Fix Controller Adjudication

status=complete

work_unit=WU-OBS-00

gate=aggregate-deepreview-fix-controller-review

decision=pass-to-dual-rereview

implementation_base=f8d6d669e30a4110efce2910f07ff96f1a3ab556

implementation_artifact=docs/reviews/wu-obs-00-aggregate-deepreview-fix-codex.md

controller_finding_source=docs/reviews/wu-obs-00-aggregate-deepreview-controller-adjudication.md

## Scope 与 owner

AgentCodex 只修改了 Controller 允许的 Service publication owner、对应 owner-level tests、
Service/Dayu README，并新增指定 fix artifact；没有修改 Host contract、Analyzer schema/rules、
CLI behavior、control_doc、既有 review artifact 或真实 workspace 数据。

`CTRL-AGG-01` 的根因属于 `dayu.service.tool_trace_analysis` 的临时文件生命周期：
`NamedTemporaryFile(delete=False)` 成功后，只有该 owner 能在 strict UTF-8 write、flush 或
close 失败前持有并清理本次路径。修复位置正确，没有把错误下推到 Host renderer/schema，也没有
通过 loose encoding 掩盖错误文本。

## Finding closure

### CTRL-AGG-01 — fixed

- `_write_temporary_text(...)` 在 temp 创建成功后立即保存路径，并在 write/flush/close 逃逸的
  任意异常上 best-effort 清理当前 temp 后原样传播。
- `_publish_report_pair(...)` 在第二个 temp 写入失败时继续清理此前已成功写入但尚未 replace 的
  temp，再原样传播。
- replace phase 与 typed partial-publication contract 未改变。
- owner tests 以真实 strict UTF-8 编码覆盖首个 JSON 与第二个 Markdown 未配对 surrogate；
  两路都断言旧 JSON/Markdown 保持且 `.tmp=0`。
- 注入的第二个 temp `OSError`、`KeyboardInterrupt`、`SystemExit` 均验证同一异常实例传播、
  当前及此前 temp 清理、旧报告保持。

Controller 核对后未发现异常被转换、temp path 丢失、旧报告被提前替换或 Host/CLI semantic owner
漂移。

### CTRL-AGG-02 — fixed

module/docstring、Service README 与 Dayu 总揽 README 已统一为：

- JSON→Markdown 固定顺序；
- 每个目标通过同目录 temp + `os.replace` 单文件原子替换；
- 两个输出文件不构成事务。

public type name、replace 顺序与第二次 replace 失败时的 partial-publication behavior 均未改变。
accepted plan 是受保护历史 artifact，不在本 fix 中反向改写。

## Verification evidence

AgentCodex 已记录并通过：

- focused owner tests：`15 passed`；
- full affected matrix：`237 passed`；
- full pyright：`0 errors / 0 warnings`；
- changed production file branch coverage：`92%`；
- workspace 与 cold-file analyzer 两种只读 smoke 均返回 0；
- smoke 前后 cold/SQLite/tree hashes 与 hot/payload/cold=`9/7/9` 均不变；
- `git diff --check` 通过。

Controller 直接检查 production diff、owner tests、README wording 与 artifact，确认修改范围和证据
闭环。真实 `workspace/.dayu` 未被删除或改写，也未运行 prompt、interactive 或 init。

## Residual

- JSON/Markdown 双文件不具备跨文件事务性；这是 accepted plan 的显式 residual，并由 typed
  partial-publication truth 与文档准确表达。
- cleanup 仍是 best-effort；底层拒绝 unlink 时可能留下 temp。该限制不改变 primary failure，
  且不是本修复可承诺的文件系统事务。
- aggregate 初审中被 Controller 驳回的 findings 保持驳回，不允许借 re-review 扩张本 fix。

blocking_open_questions=none

next_entry_point=AgentMiMo / AgentDS dual aggregate re-review; never self-advance
