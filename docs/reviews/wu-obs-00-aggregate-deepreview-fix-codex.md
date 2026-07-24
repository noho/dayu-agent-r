# WU-OBS-00 Aggregate Deepreview Fix Artifact

status=complete

work_unit=WU-OBS-00

gate=aggregate-deepreview-fix

implementation_agent=AgentCodex

implementation_base=f8d6d669e30a4110efce2910f07ff96f1a3ab556

controller_adjudication=docs/reviews/wu-obs-00-aggregate-deepreview-controller-adjudication.md

accepted_plan=docs/host/wu-obs-00-plan.md

artifact_path=docs/reviews/wu-obs-00-aggregate-deepreview-fix-codex.md

next_entry_point=Controller review; AgentCodex stops and never self-advances

## 1. Scope 与 owner 判断

本 fix 只关闭 Controller accepted findings `CTRL-AGG-01` 与 `CTRL-AGG-02`。
Service publication boundary 是临时文件创建、strict UTF-8 写入、逐文件替换与 cleanup
语义的唯一 owner，因此修复落在 `dayu/service/tool_trace_analysis.py`，没有修改 Host
report schema、renderer、Analyzer rules/input、producer、CLI behavior 或 public type name。

问题动机成立：

- `_write_temporary_text(...)` 原实现只在成功返回后才把 temp path 交给调用方；
- strict UTF-8 对未配对 surrogate 抛出 `UnicodeEncodeError`，它不是 `OSError`；
- `_publish_report_pair(...)` 原 temp-write catch 只覆盖 `OSError`；
- 因此当前正在写入的 temp 在该异常路径不可由调用方发现并清理。

Controller rejected reviewer findings 均未进入本 fix，也未新增 compatibility、loose parsing、
replacement/ignore encoding、Host fallback 或下游补偿。

## 2. Changed files 与 diff

允许范围内的功能 diff（写本 artifact 前）：

```text
dayu/README.md                            |   4 +-
dayu/service/README.md                    |   8 +-
dayu/service/tool_trace_analysis.py       |  42 +++--
tests/service/test_tool_trace_analysis.py | 250 +++++++++++++++++++++++++++++-
4 files changed, 284 insertions(+), 20 deletions(-)
```

实际修改：

- `dayu/service/tool_trace_analysis.py`
  - temp helper 在取得真实 temp path 后，对写入、flush、close 期间逃逸的任意异常先
    best-effort 清理当前 temp，再原样传播；
  - publication owner 对任一 temp-write 异常再清理此前成功写入的 temp；
  - `KeyboardInterrupt` / `SystemExit` 不包装为
    `ServiceToolTraceAnalysisPublishError`；
  - strict UTF-8 与 `errors="strict"` 保持不变；
  - publication docstring 纠正为 JSON→Markdown 逐文件原子替换，双文件不构成事务。
- `tests/service/test_tool_trace_analysis.py`
  - 覆盖首个 JSON temp strict UTF-8 `UnicodeEncodeError`；
  - 覆盖第二个 Markdown temp strict UTF-8 `UnicodeEncodeError`；
  - 覆盖第二个 temp write 的 `OSError`、`KeyboardInterrupt`、`SystemExit`；
  - 每条路径都断言异常类型/实例不被转换、旧 JSON/Markdown 保持、当前及此前 temp
    均无泄漏。
- `dayu/service/README.md`
  - publication owner 的准确 contract 统一为：同目录 temp + `os.replace`，按
    JSON→Markdown 固定顺序逐文件原子替换，双文件不构成事务。
- `dayu/README.md`
  - 只修正总揽级跨层 publication 措辞，不展开 Service 内部实现。
- `docs/reviews/wu-obs-00-aggregate-deepreview-fix-codex.md`
  - 本 fix gate 的 durable handoff artifact。

未修改 Controller 的 dirty control/review artifacts，未提交 commit，未更新 control_doc。

## 3. Finding closure evidence

### CTRL-AGG-01 — fixed

实现闭环：

1. `_write_temporary_text(...)` 在 `NamedTemporaryFile(delete=False)` 成功后立即保存
   `temporary_path`。
2. strict UTF-8 write、flush 或 context close 传播任意异常时，helper 对当前 temp 调用
   `_cleanup_temporary_paths(...)`，随后 bare `raise` 原样传播。
3. `_publish_report_pair(...)` 的 temp-write phase 捕获 `BaseException`，对列表中此前已成功
   写入的 temp 执行 best-effort cleanup，随后 bare `raise`。
4. replace phase 与 typed partial-publication truth 未改变。

Owner-level evidence：

- `first-json`：首个 JSON 文本含未配对 surrogate，实际 strict UTF-8 写入抛
  `UnicodeEncodeError`；旧双报告保持，`.tmp=0`。
- `second-markdown`：首个 JSON temp 成功、第二个 Markdown strict UTF-8 写入失败；
  当前 Markdown temp 与此前 JSON temp 均清理，旧双报告保持，`.tmp=0`。
- second-temp injected failures：`OSError`、`KeyboardInterrupt`、`SystemExit` 均以同一异常
  实例传播；当前及此前 temp 均清理，旧双报告保持。

### CTRL-AGG-02 — fixed

代码模块说明、publication function/docstring、Service README 与 Dayu 总揽 README 已统一为：

```text
JSON→Markdown 固定顺序；
每个目标在同目录写 strict UTF-8 temp，再以 os.replace 单文件原子替换；
两个报告文件不构成事务。
```

没有改变 `ServiceToolTraceAnalysisPublishError` 等 public type name，没有回滚已成功 JSON，
也没有新增 transaction/journal。

## 4. Tests

Focused owner suite：

```bash
source .venv/bin/activate
pytest -q tests/service/test_tool_trace_analysis.py
```

结果：`15 passed in 0.34s`。

Full affected matrix：

```bash
source .venv/bin/activate
pytest -q \
  tests/host/test_tool_trace_projection.py \
  tests/host/test_tool_trace_queries.py \
  tests/host/test_durable_connection.py \
  tests/host/test_tool_trace_analysis_input.py \
  tests/host/test_tool_trace_analysis_rules.py \
  tests/host/test_tool_trace_analysis.py \
  tests/service/test_tool_trace_analysis.py \
  tests/cli/test_tool_trace_command.py \
  tests/cli/test_arg_parsing.py \
  tests/cli/test_import_boundary.py
```

结果：`237 passed, 3 warnings in 5.00s`。三条 warning 均来自既有 `edgar` 第三方
deprecation，不属于本 fix owner。

## 5. Pyright

Targeted：

```bash
source .venv/bin/activate
python -m pyright \
  dayu/service/tool_trace_analysis.py \
  tests/service/test_tool_trace_analysis.py
```

结果：`0 errors, 0 warnings, 0 informations`。

Full：

```bash
source .venv/bin/activate
python -m pyright dayu/ tests/ utils/
```

结果：`0 errors, 0 warnings, 0 informations`。

## 6. Changed-file branch coverage

```bash
source .venv/bin/activate
pytest -q tests/service/test_tool_trace_analysis.py \
  --cov=dayu.service.tool_trace_analysis \
  --cov-branch \
  --cov-report=term-missing
```

结果：

```text
dayu/service/tool_trace_analysis.py  Stmts=162 Miss=10 Branch=28 BrPart=6 Cover=92%
15 passed in 0.42s
```

唯一修改的 production Python 文件 branch coverage 为 `92%`，高于 `80%` 目标。

## 7. Existing workspace analyzer read-only smoke

只运行现有 analyzer，没有运行 `dayu-cli prompt`、interactive 或 init，没有删除、修复或改写
`workspace/.dayu`。两个 output directory 均由 `mktemp` 创建在 `/tmp`：

```bash
source .venv/bin/activate
python -m dayu.cli tool_trace analyze workspace \
  --output-dir /tmp/wu-obs-00-agg-workspace.ww191y
python -m json.tool \
  /tmp/wu-obs-00-agg-workspace.ww191y/tool-trace-analysis.json >/dev/null
test -s /tmp/wu-obs-00-agg-workspace.ww191y/tool-trace-analysis.md

python -m dayu.cli tool_trace analyze \
  workspace/.dayu/artifacts/tool-trace/tool-trace-cold.jsonl \
  --output-dir /tmp/wu-obs-00-agg-file.CoOaxd
python -m json.tool \
  /tmp/wu-obs-00-agg-file.CoOaxd/tool-trace-analysis.json >/dev/null
test -s /tmp/wu-obs-00-agg-file.CoOaxd/tool-trace-analysis.md
```

两种 mode 均返回 `0`，JSON 可解析且 JSON/Markdown 非空。调用前后只读证明：

```text
cold_sha=06a9d18a369ebfefa6bee815cfa8d4a7fa541c26006bee4450907a6aac2e75f9
db_sha=fe72fbfcdced9006738cd9985702488e8e804cecf077ca97559f83a4d19bf400
.dayu_tree_content_sha=ef31487cebb23b36b19bd7d5f54b127b11f218dc0bd68978e85e21d18ae3b4b0
hot_rows=9
payload_descriptors=7
cold_rows=9
inputs_unchanged=true
```

## 8. Docs decision

- `dayu/service/README.md`：publication contract 属于 Service reader-facing owner，必须修正。
- `dayu/README.md`：已有跨层 Tool Trace publication 说明包含错误事务暗示，按其
  `Agent更新约束` 仅修正总揽级边界。
- 根 `README.md`、`dayu/host/README.md`、`tests/README.md` 未修改：本 fix 不改变用户命令、
  Host public contract 或测试入口，且不在允许文件范围内。

## 9. Residual risks / uncovered areas

- 两个普通报告文件仍不构成跨文件事务；这是 accepted plan 明确保留的 operator-file
  residual，第二次 replace 失败继续由 typed `published_paths` / `failed_path` 表达。
- cleanup 是 best-effort；若底层文件系统拒绝 unlink，无法保证物理删除。本 fix 未把 cleanup
  failure 伪装成成功，也未以 loose encoding 绕过 primary write failure。
- 未执行真实磁盘满或权限故障的破坏性环境测试；owner-level `OSError` failure injection 已覆盖
  相同 cleanup/传播 contract。
- Controller rejected findings 保持 rejected，不属于本 fix 的 residual 或后续实现项。

blocking_open_questions=none

commit=not-created

control_doc=not-modified-by-AgentCodex

review=self-review-not-run

stop_condition=complete-and-wait-for-Controller-review
