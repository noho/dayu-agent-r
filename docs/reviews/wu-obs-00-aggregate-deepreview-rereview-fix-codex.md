# WU-OBS-00 Aggregate Deepreview Re-Review Fix Artifact

status=complete

work_unit=WU-OBS-00

gate=aggregate-deepreview-rereview-fix

implementation_agent=AgentCodex

implementation_base=f8d6d669e30a4110efce2910f07ff96f1a3ab556

controller_adjudication=docs/reviews/wu-obs-00-aggregate-deepreview-rereview-controller-adjudication.md

accepted_plan=docs/host/wu-obs-00-plan.md#103-output-publication-and-exit-codes

artifact_path=docs/reviews/wu-obs-00-aggregate-deepreview-rereview-fix-codex.md

allowed_scope=

- `dayu/service/tool_trace_analysis.py`
- `tests/service/test_tool_trace_analysis.py`
- 新建
  `docs/reviews/wu-obs-00-aggregate-deepreview-rereview-fix-codex.md`

next_entry_point=Controller review; AgentCodex stops and never self-advances

## 1. 动机与 owner 判断

`CTRL-RR-01` 动机成立，严重性为低但是真实 contract defect，不是理论性建议：

- accepted plan §10.3 要求任一发布失败都 best-effort 清理本次临时文件；
- 前轮 temp-write phase 已由 Service publication boundary 在任意
  `BaseException` 逃逸前清理；
- replace phase 只捕获 `OSError`，Controller 在第一次 replace 注入
  `KeyboardInterrupt` 后直接复现两个 `.tmp` 残留；
- 因而 temp lifecycle 在同一个 Service publication owner 内不一致。

`dayu.service.tool_trace_analysis` publication boundary 是本次临时文件的创建、pending
集合、逐文件 replace、cleanup 与 typed partial-publication truth 的唯一 owner。修复必须落在
该边界，不能由 Host、CLI、schema、public types、下游 adapter 或测试 fixture 补偿。

本 fix 不引入跨文件事务、journal、回滚、fallback、兼容分支或 loose parsing；JSON 后
Markdown 的固定顺序及双文件非事务语义保持不变。

## 2. Changed files

- `dayu/service/tool_trace_analysis.py`
  - 用同一个 `try` 覆盖完整 JSON→Markdown replace phase，包括 replace 调用及两次调用
    之间的 Python 控制流；
  - `except OSError` 保留现有
    `ServiceToolTraceAnalysisPublishError`、`published_paths`、`failed_path`、
    primary publish detail 与 cleanup secondary detail；
  - 后续 `except BaseException` 仅 best-effort 清理当前
    `pending_temporary_paths`，随后 bare `raise`，保证 `KeyboardInterrupt` /
    `SystemExit` 原实例原样传播；
  - docstring 明确中断清理覆盖 temp-write 与 replace 两个 phase。
- `tests/service/test_tool_trace_analysis.py`
  - 新增可按 replace 序号原样抛出指定 `BaseException` 的 owner-level helper；
  - 新增 first replace interruption test，参数化 `KeyboardInterrupt` /
    `SystemExit`；
  - 新增 second replace interruption test，参数化 `KeyboardInterrupt` /
    `SystemExit`。
- `docs/reviews/wu-obs-00-aggregate-deepreview-rereview-fix-codex.md`
  - 本 gate 的 durable handoff artifact。

前一轮已存在的 working diff 全部保留；没有改写 Controller control/review artifacts。

## 3. CTRL-RR-01 closure evidence

### 3.1 第一次 replace 前中断

Owner test 在第一次 `_replace_temporary_file(...)` 调用抛出原始
`KeyboardInterrupt` / `SystemExit` 实例：

- `raised.value is failure`；
- JSON 精确保持 `old-json`；
- Markdown 精确保持 `old-markdown`；
- 两个尚未 replace 的 pending temp 均被清理，`.tmp=0`。

### 3.2 第二次 Markdown replace 前中断

Owner test 先执行真实 JSON replace，再在第二次
`_replace_temporary_file(...)` 调用抛出原始 `KeyboardInterrupt` /
`SystemExit` 实例：

- `raised.value is failure`；
- JSON 精确为 `new-json`，证明已成功发布的 JSON 未回滚；
- Markdown 精确保持 `old-markdown`；
- JSON temp 已在第一次 replace 成功后从 pending 集合移除，只清理 pending Markdown
  temp，最终 `.tmp=0`。

### 3.3 OSError typed truth non-regression

`except OSError` 仍位于 `except BaseException` 之前，并在同一 replace phase 内：

- 第一次 replace `OSError` 仍产生 `published_paths=()`、
  `failed_path=json_path`；
- 第二次 replace `OSError` 仍产生 `published_paths=(json_path,)`、
  `failed_path=markdown_path`；
- cleanup failure 仍只进入独立 `ServiceToolTraceCleanupFailure` secondary detail，不覆盖
  primary target 或已发布路径；
- 既有 OSError owner tests 全部包含在 focused / affected suite 中并通过。

CTRL-RR-01=closed-by-implementation-and-owner-tests

## 4. Focused tests

```bash
source .venv/bin/activate
pytest -q tests/service/test_tool_trace_analysis.py
```

结果：`19 passed in 0.36s`。

## 5. Affected matrix

沿用前轮 artifact 的 10 文件矩阵：

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

结果：`241 passed, 3 warnings in 5.69s`。三条 warning 均来自既有 `edgar`
第三方 deprecation，不属于本 fix owner。

## 6. Pyright

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

两次命令均另有 pyright `v1.1.409 -> v1.1.411` 更新提示，不是类型诊断。

## 7. Changed-file branch coverage

```bash
source .venv/bin/activate
pytest -q tests/service/test_tool_trace_analysis.py \
  --cov=dayu.service.tool_trace_analysis \
  --cov-branch \
  --cov-report=term-missing
```

结果：

```text
dayu/service/tool_trace_analysis.py  Stmts=166 Miss=10 Branch=28 BrPart=6 Cover=92%
19 passed in 0.48s
```

唯一修改的 production Python 文件 branch coverage 为 `92%`，高于 `80%` 目标。

## 8. Existing workspace analyzer read-only smoke

只运行现有 `tool_trace analyze`。没有运行 prompt、interactive 或 init，没有删除、修复或
改写 `workspace/.dayu`。directory 与 cold-file 两个 output directory 均由 `mktemp`
创建在 `/tmp`：

```bash
source .venv/bin/activate
workspace_output="$(mktemp -d /tmp/wu-obs-00-rr-workspace.XXXXXX)"
cold_output="$(mktemp -d /tmp/wu-obs-00-rr-cold.XXXXXX)"

python -m dayu.cli tool_trace analyze workspace \
  --output-dir "$workspace_output"
python -m json.tool \
  "$workspace_output/tool-trace-analysis.json" >/dev/null
test -s "$workspace_output/tool-trace-analysis.md"

python -m dayu.cli tool_trace analyze \
  workspace/.dayu/artifacts/tool-trace/tool-trace-cold.jsonl \
  --output-dir "$cold_output"
python -m json.tool \
  "$cold_output/tool-trace-analysis.json" >/dev/null
test -s "$cold_output/tool-trace-analysis.md"
```

Authoritative run 的两个 analyzer、JSON parse 与 Markdown non-empty 检查均返回 0：

```text
workspace_output=/tmp/wu-obs-00-rr-workspace.sxH0ct
cold_output=/tmp/wu-obs-00-rr-cold.z74Rz5
cold_sha=06a9d18a369ebfefa6bee815cfa8d4a7fa541c26006bee4450907a6aac2e75f9
db_sha=fe72fbfcdced9006738cd9985702488e8e804cecf077ca97559f83a4d19bf400
tree_content_sha=ef31487cebb23b36b19bd7d5f54b127b11f218dc0bd68978e85e21d18ae3b4b0
tree_files=19
hot_rows=9
payload_descriptors=7
cold_rows=9
inputs_unchanged=true
```

上述值均在调用前后分别采集并逐项 `test before = after`。cold / DB 使用 SHA-256；
tree hash 对 `.dayu` 下稳定排序的全部 19 个文件内容哈希再次 SHA-256；hot /
payload 计数通过 SQLite `-readonly` 查询 owner 表，cold 计数来自只读行数统计。

在 authoritative run 前有一次相同双 smoke 预检，analyzer 与哈希比较均成功，但把
`payload_descriptors` 错误当作文件目录而得到一条只读 `find` warning；该错误计数未作为
验收证据，也未触碰 workspace。随后按 SQLite owner 表重新执行上述无 warning 的
authoritative run。

## 9. Diff / scope checks

实现前 preflight：

```text
branch=work/wu-obs-00
HEAD=f8d6d669e30a4110efce2910f07ff96f1a3ab556
```

实现后执行：

```bash
git diff --check
git status --short
git diff --name-only
```

结果：见本 artifact 最终 scope audit；获准代码/测试路径保留前轮 diff 并增加本 fix，
另仅新增本 artifact。既有 dirty README、control/review artifacts 没有由本 Agent 改写。

最终精确结果：

```text
git diff --check: exit 0
branch=work/wu-obs-00
HEAD=f8d6d669e30a4110efce2910f07ff96f1a3ab556

tracked diff --name-only:
dayu/README.md
dayu/service/README.md
dayu/service/tool_trace_analysis.py
docs/host/issues-implementation-control.md
tests/service/test_tool_trace_analysis.py

本 Agent 相对 preflight 新增的 status path:
docs/reviews/wu-obs-00-aggregate-deepreview-rereview-fix-codex.md
```

`dayu/README.md`、`dayu/service/README.md`、control_doc 与既有 review artifacts 在 preflight
时已经 dirty/untracked；本 Agent 没有写入。相对 preflight，本 Agent 只进一步修改两个获准
tracked 路径，并新增指定 artifact。以下只读真源 SHA-256 与 preflight 采集值逐项完全一致：

```text
0a61eb09bbb5b88078e8c2371dfcf5c338ae717808fddf3078cd044ba7f22ce5  rereview-controller-adjudication
765130e813e3722faf5c20f2181520a3c2cedec13c63ef5e84edfd5cc3fbc47c  prior-fix-codex
2b0050b9b01a0e06da6bc7d85d180f15322c55f2d5e7b06edcd63a70a5aacb9d  prior-fix-controller-adjudication
ebe226bb721c9f7f53767d7e089664d933f74c683ad3bdbf4b6ccdbd53243038  rereview-ds
aeafd18ba595078e7e8e114ebf46356af26562a27e92b2a44cacc38ac4acf6d2  rereview-mimo
a9989e3165f702094b55c76772caa8e3344544c6ea193d7c50a616a60984f72e  issues-implementation-control
```

## 10. README decision

不修改 README。虽然 production/tests 变化通常触发职责检查，但用户对本 gate 明确禁止
README 修改；本修复不改变用户命令、public type、Host contract 或既有双文件非事务文档
语义，仅补齐同一 Service temp lifecycle 的 interruption cleanup。

## 11. Residual risks / uncovered areas

- 两个报告文件仍不构成跨文件事务；第二次 replace 前中断会保留新 JSON 与旧 Markdown。
  这是 accepted plan 明确保留的行为，不是未修复 defect。
- cleanup 仍是 best-effort；若底层文件系统拒绝 unlink，物理 temp 仍可能残留。对
  `KeyboardInterrupt` / `SystemExit` 必须优先保留原始异常 identity，因此本 fix 不新增
  public secondary error carrier。
- 未执行真实信号投递、磁盘满或权限故障等破坏性环境测试；owner-level deterministic
  failure injection 覆盖了要求的控制流、文件内容与 temp lifecycle contract。
- preliminary smoke 的错误 payload 文件目录探测只影响该次辅助计数；authoritative run
  已从 SQLite owner 表纠正且所有前后证据一致。

blocking_open_questions=none

commit=not-created

control_doc=not-modified-by-AgentCodex

review=self-review-not-run

stop_condition=complete-and-wait-for-Controller-review
